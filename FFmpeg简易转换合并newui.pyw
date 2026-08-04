#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
import subprocess
import os
import threading
import re
import copy
import json
import sys
import shutil
import ctypes
import concurrent.futures
from typing import List, Tuple, Optional, Dict, Any, Callable
import shlex
import tempfile



# --- 依赖检测 ---
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False
    root_temp = tk.Tk()
    root_temp.withdraw()
    messagebox.showwarning("功能受限提示", "未检测到 tkinterdnd2 库，当前不支持文件拖拽功能！\n\n如需使用拖拽，请在终端运行：pip install tkinterdnd2")
    root_temp.destroy()

# ================== 公共工具函数 ==================

def format_cmd_for_display(cmd_list: List[str]) -> str:
    """
    将命令列表转换为适合显示/复制的字符串，带必要的引号。
    Windows 使用 subprocess.list2cmdline，Unix 使用 shlex.quote 逐个转义。
    """
    if sys.platform == "win32":
        return subprocess.list2cmdline(cmd_list)
    else:
        return ' '.join(shlex.quote(arg) for arg in cmd_list)

def normalize_path(path: str) -> str:
    """统一路径分隔符为正斜杠"""
    return path.replace('\\', '/')

def quote_path(path: str) -> str:
    """为路径添加双引号，用于命令行（仅用于显示，实际执行使用列表）"""
    return f'"{path}"'

def get_script_dir() -> str:
    """获取脚本所在目录（支持打包后）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

def find_resource(filename: str) -> Optional[str]:
    """
    在脚本目录及其所有一级子目录中查找指定文件（不要求可执行权限）。
    返回找到的第一个完整路径，未找到则返回 None。
    """
    script_dir = get_script_dir()
    
    # 1. 脚本目录本身
    path = os.path.join(script_dir, filename)
    if os.path.isfile(path):
        return path

    # 2. 脚本目录的一级子目录（无论是否打包都扫描）
    try:
        for entry in os.listdir(script_dir):
            sub_dir = os.path.join(script_dir, entry)
            if os.path.isdir(sub_dir):
                candidate = os.path.join(sub_dir, filename)
                if os.path.isfile(candidate):
                    return candidate
    except OSError:
        pass

    # 3. PyInstaller one-file 模式下的临时解压目录 (_MEIPASS)
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidate = os.path.join(meipass, filename)
            if os.path.isfile(candidate):
                return candidate

    return None


def find_executable(name: str) -> Optional[str]:
    candidate = find_resource(name)
    if candidate and os.access(candidate, os.X_OK):
        return candidate
    # 未在脚本目录找到，回退到系统 PATH
    return shutil.which(name)

def get_dpi_scaling(root: tk.Tk) -> float:
    """获取系统 DPI 缩放因子"""
    try:
        return root.winfo_fpixels('1i') / 96.0
    except:
        return 1.0

def center_window(win: tk.Toplevel, width: int, height: int, offset_y: int = 0):
    """
    在屏幕中央显示窗口（忽略父窗口），避免闪烁。
    前提：窗口创建后已调用 withdraw()，此处只负责定位和显示。
    """
    # 强制更新布局，确保几何信息准确
    win.update_idletasks()
    win.update()

    screen_width = win.winfo_screenwidth()
    screen_height = win.winfo_screenheight()
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2 - offset_y
    x = max(0, x)
    y = max(0, y)

    win.geometry(f"{width}x{height}+{x}+{y}")
    win.deiconify()   # 显示窗口
    win.lift()
    win.focus_force()
    win.update_idletasks()


def safe_eval_expr(expr: str, context: Dict[str, int]) -> Optional[int]:
    """
    安全计算数学表达式，支持 + - * / ( ) 以及 context 中的变量。
    使用严格白名单防止注入，返回整数，失败返回 None。
    """
    if not expr:
        return None
    expr = expr.strip()
    # 只允许数字、运算符、括号、空格、小数点、变量名（字母数字下划线）
    if not re.match(r'^[0-9+\-*/()\.\sA-Za-z_]+$', expr):
        return None
    # 替换变量（完整单词）
    for var, val in context.items():
        expr = re.sub(r'\b' + re.escape(var) + r'\b', str(val), expr)
    # 禁止任何函数调用、属性访问、内置名称
    if re.search(r'[._\[\]"\']', expr):
        return None
    try:
        # 编译后检查引用的名称是否只包含上下文变量
        code = compile(expr, "<string>", "eval")
        for name in code.co_names:
            if name not in context and name not in ("abs", "round"):
                return None
        # 使用空 __builtins__ 执行
        return int(round(eval(code, {"__builtins__": {}}, context)))
    except:
        return None

def fix_bitrate_value(bitrate_str: str) -> str:
    """将纯数字比特率转换为数字+k 格式"""
    val = bitrate_str.strip()
    if not val:
        return "1000k"
    if re.match(r'^\d+$', val):
        return val + "k"
    return val

def is_valid_timestamp(ts: str) -> bool:
    """验证时间戳格式 (HH:MM:SS[.mmm] 或 数字)"""
    if not ts:
        return True
    pattern = r'^(\d{1,2}:)?\d{1,2}:\d{1,2}(\.\d{1,3})?$'
    if re.match(pattern, ts):
        return True
    if ts.replace('.', '', 1).isdigit():
        return False
    return False

def seconds_to_time(sec):
    """秒数转 HH:MM:SS.ms"""
    if sec is None:
        return ""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:06.3f}"
    else:
        return f"{m:02d}:{s:06.3f}"




# ================== 预设管理 ==================
class PresetManager:
    # 默认预设模板（精简版）
    DEFAULT_PRESET_TEMPLATE = {
        "TEST 裁一半保留右边": {
            "vcodec": "libx265",
            "rate_control_type": "crf",
            "crf_value": 25,
            "frame_rate_type": "keep",
            "frame_rate_custom": "24",
            "crop_enabled": True,
            "crop_left": "iw/2",
            "crop_top": "0",
            "crop_width": "iw/2",
            "crop_height": "ih",
        },
        "TEST 裁一半保留左边": {
            "vcodec": "libx265",
            "rate_control_type": "crf",
            "crf_value": 25,
            "frame_rate_type": "keep",
            "frame_rate_custom": "24",
            "crop_enabled": True,
            "crop_left": "0",
            "crop_top": "0",
            "crop_width": "iw/2",
            "crop_height": "ih",
        },
        "TEST 缩放 600宽": {
            "vcodec": "libx265",
            "rate_control_type": "crf",
            "crf_value": 25,
            "frame_rate_type": "keep",
            "frame_rate_custom": "24",
            "scale_enabled": True,
            "scale_width": "600",
            "scale_height": "",
            "scale_method": "width",
        },
        "TEST 横1920": {
            "vcodec": "libx265",
            "rate_control_type": "crf",
            "crf_value": 25,
            "frame_rate_type": "custom",
            "frame_rate_custom": "30",
            "scale_enabled": True,
            "scale_width": "1920",
            "scale_height": "-2",
            "scale_method": "width",
        },
        "TEST 竖1920": {
            "vcodec": "libx265",
            "rate_control_type": "crf",
            "crf_value": 25,
            "frame_rate_type": "custom",
            "frame_rate_custom": "30",
            "scale_enabled": True,
            "scale_width": "-2",
            "scale_height": "1920",
            "scale_method": "height",
        },
        "无损复制流": {
            "encoder": "copy",
            "audio_codec": "copy",
        },
        "H264 Fast 1080p30 (通用高清)": {
            "encoder": "libx264",
            "preset": "fast",
            "rate_control_type": "crf",
            "crf_value": 23,
            "frame_rate_type": "custom",
            "frame_rate_custom": "30",
            "scale_enabled": True,
            "scale_width": "1920",
            "scale_height": "1080",
            "scale_method": "exact",
        },
        "H264 Fast 720p30 (通用标清)": {
            "encoder": "libx264",
            "preset": "fast",
            "rate_control_type": "crf",
            "crf_value": 23,
            "frame_rate_type": "custom",
            "frame_rate_custom": "30",
            "scale_enabled": True,
            "scale_width": "1280",
            "scale_height": "720",
            "scale_method": "exact",
        },
        "H264 Very Fast 1080p30 (极速高清)": {
            "encoder": "libx264",
            "preset": "veryfast",
            "rate_control_type": "crf",
            "crf_value": 23,
            "frame_rate_type": "custom",
            "frame_rate_custom": "30",
            "scale_enabled": True,
            "scale_width": "1920",
            "scale_height": "1080",
            "scale_method": "exact",
        },
        "H264 HQ 1080p30 (高质量)": {
            "encoder": "libx264",
            "preset": "slow",
            "rate_control_type": "crf",
            "crf_value": 20,
            "frame_rate_type": "custom",
            "frame_rate_custom": "30",
            "scale_enabled": True,
            "scale_width": "1920",
            "scale_height": "1080",
            "scale_method": "exact",
        },
        "H265 HEVC 1080p (高效压缩)": {
            "encoder": "libx265",
            "preset": "medium",
            "rate_control_type": "crf",
            "crf_value": 24,
            "frame_rate_type": "keep",
            "frame_rate_custom": "30",
            "scale_enabled": True,
            "scale_width": "1920",
            "scale_height": "1080",
            "scale_method": "exact",
        },
        "H265 HEVC 4K (高质量)": {
            "encoder": "libx265",
            "preset": "slow",
            "rate_control_type": "crf",
            "crf_value": 22,
            "frame_rate_type": "keep",
            "frame_rate_custom": "30",
            "scale_enabled": True,
            "scale_width": "3840",
            "scale_height": "2160",
            "scale_method": "exact",
        }
    }
    def __init__(self, preset_path: str, app_name: str = "FFLiteGUI"):
        self.preset_path = preset_path
        self.user_data_dir = os.path.join(os.path.expanduser("~"), f".{app_name}")
        os.makedirs(self.user_data_dir, exist_ok=True)
#        self._ensure_default_preset()

    def _ensure_default_preset(self):
        if os.path.exists(self.preset_path):
            return
    
        # 尝试从内置资源复制
        bundled = find_resource("ffmpeg_presets.json")
        if bundled:
            try:
                shutil.copy2(bundled, self.preset_path)
                print(f"首次运行，已从内部释放默认配置到：{self.preset_path}")
                return
            except Exception as e:
                print(f"释放配置文件失败: {e}")
    
        # 没有内置预设，写入精简默认模板
        try:
            with open(self.preset_path, 'w', encoding='utf-8') as f:
                json.dump(self.DEFAULT_PRESET_TEMPLATE, f, indent=4, ensure_ascii=False)
            print(f"首次运行，已创建精简预设模板：{self.preset_path}")
        except Exception as e:
            print(f"创建预设文件失败: {e}")

    def load_all(self) -> Dict[str, Any]:
        """加载所有预设，返回字典 {预设名: 设置字典}，不含播放器设置"""
        if not os.path.exists(self.preset_path):
            return {}
        try:
            with open(self.preset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {k: v for k, v in data.items() if k != "player_settings"}
        except:
            return {}

    def save_preset(self, name: str, settings: Dict[str, Any]):
        """保存预设，保留已有的播放器设置，采用原子写入防止文件损坏"""
        data = self.load_all()
        player_cfg = {}
        if os.path.exists(self.preset_path):
            try:
                with open(self.preset_path, 'r', encoding='utf-8') as f:
                    full = json.load(f)
                player_cfg = full.get("player_settings", {})
            except:
                pass
        data[name] = settings
        data["player_settings"] = player_cfg
    
        # 原子写入：先写入临时文件，再替换原文件
        dir_name = os.path.dirname(self.preset_path)
        try:
            with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False, encoding='utf-8') as tf:
                json.dump(data, tf, indent=4, ensure_ascii=False)
                temp_name = tf.name
            os.replace(temp_name, self.preset_path)  # 原子替换
        except Exception as e:
            # 如果发生错误，尝试删除临时文件
            if 'temp_name' in locals() and os.path.exists(temp_name):
                os.unlink(temp_name)
            raise e
     
    def delete_preset(self, name: str) -> bool:
       """删除预设，采用原子写入防止文件损坏"""
       data = self.load_all()
       if name not in data:
           return False
       del data[name]
       player_cfg = {}
       if os.path.exists(self.preset_path):
           try:
               with open(self.preset_path, 'r', encoding='utf-8') as f:
                   full = json.load(f)
               player_cfg = full.get("player_settings", {})
           except:
               pass
       data["player_settings"] = player_cfg
   
       # 原子写入
       dir_name = os.path.dirname(self.preset_path)
       try:
           with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False, encoding='utf-8') as tf:
               json.dump(data, tf, indent=4, ensure_ascii=False)
               temp_name = tf.name
           os.replace(temp_name, self.preset_path)
           return True
       except Exception as e:
           if 'temp_name' in locals() and os.path.exists(temp_name):
               os.unlink(temp_name)
           raise e


    def load_player_settings(self) -> Dict[str, Any]:
        if not os.path.exists(self.preset_path):
            return {}
        try:
            with open(self.preset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("player_settings", {})
        except:
            return {}

    def save_player_settings(self, settings: Dict[str, Any]):
        data = self.load_all()
        data["player_settings"] = settings
        with open(self.preset_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)



def time_to_seconds(timestr: str) -> Optional[float]:
    """将 HH:MM:SS[.mmm] 或 MM:SS[.mmm] 或纯数字转换为秒数"""
    if not timestr:
        return None
    timestr = timestr.strip()
    parts = timestr.split(':')
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        else:
            return float(timestr)
    except ValueError:
        return None

# ================== 滤镜链构建 ==================
def build_video_filter_chain(settings: Dict[str, Any], include_subtitle: bool = True, include_speed: bool = True,
                              include_trim: bool = True, include_format: bool = True, enhance_settings=None, reverse=False) -> str:
    """
    从设置字典构建视频滤镜链。
    include_subtitle: 是否包含字幕滤镜
    include_speed: 是否包含变速滤镜
    include_trim: 是否包含精准截取（trim+setpts）滤镜
    include_format: 是否包含像素格式转换（format）滤镜
    enhance_settings:高级一点的滤镜
    顺序优化：
    精准截取 → 裁剪 → 旋转/翻转 → 缩放 → IVTC（反胶卷过带） → 反交错 → 
    去块滤波 → 降噪 → 锐化 → 色彩空间转换 → 颜色校正+色相 → 像素格式 → 变速 → 倒放
    """
    filters = []
    
    # ----- 精准截取（trim + setpts）-----
    if include_trim and settings.get("precise_trim", False) and settings.get("trim_enabled", False):
        start = settings.get("trim_start", "").strip()
        end = settings.get("trim_end", "").strip()
        start_sec = time_to_seconds(start) if start else None
        end_sec = time_to_seconds(end) if end else None
        if start_sec is not None or end_sec is not None:
            trim_parts = []
            if start_sec is not None:
                trim_parts.append(f"start={start_sec}")
            if end_sec is not None:
                trim_parts.append(f"end={end_sec}")
            if trim_parts:
                filters.append(f"trim={':'.join(trim_parts)}")
                filters.append("setpts=PTS-STARTPTS")
    
    # ----- 裁剪 -----
    if settings.get("crop_enabled", False):
        w = settings.get("crop_width", "").strip()
        h = settings.get("crop_height", "").strip()
        left = settings.get("crop_left", "0").strip()
        top = settings.get("crop_top", "0").strip()
        if w and h:
            filters.append(f"crop={w}:{h}:{left}:{top}")

    # ----- 旋转/翻转 -----
    rot = settings.get("rotate", "none")
    if rot == "90":
        filters.append("transpose=1")
    elif rot == "180":
        filters.append("transpose=2,transpose=2")
    elif rot == "270":
        filters.append("transpose=2")
    if settings.get("vflip", False):
        filters.append("vflip")
    if settings.get("hflip", False):
        filters.append("hflip")

    # ----- 缩放 -----
    if settings.get("scale_enabled", False):
        method = settings.get("scale_method", "width")
        w = settings.get("scale_width", "").strip()
        h = settings.get("scale_height", "").strip()
        if method == "width" and w:
            filters.append(f"scale={w}:-2")
        elif method == "height" and h:
            filters.append(f"scale=-2:{h}")
        elif method == "exact" and w and h:
            filters.append(f"scale={w}:{h}")
    
    # ----- IVTC（反胶卷过带）----- 
    ivtc_enabled = enhance_settings and enhance_settings.get("ivtc_enabled", False)
    if ivtc_enabled:
        filters.append("fieldmatch,decimate")
    
    # ----- 反交错（仅当 IVTC 未启用时执行） -----
    if not ivtc_enabled:  # 添加条件
        deint = settings.get("deinterlace_filter", "none")
        if deint != "none":
            filters.append(deint)
    
    # ----- 去块滤波 -----
    if enhance_settings and enhance_settings.get("deblock_enabled", False):
        strength = enhance_settings.get("deblock_strength", 4)
        filters.append(f"deblock=filter=weak:block={strength}")
    
    # ----- 降噪 -----
    if enhance_settings and enhance_settings.get("denoise_enabled", False):
        spatial = enhance_settings.get("denoise_spatial", 4.0)
        temporal = enhance_settings.get("denoise_temporal", 3.0)
        # hqdn3d 参数：空间亮度, 空间色度, 时间亮度, 时间色度
        filters.append(f"hqdn3d={spatial:.1f}:{spatial*0.75:.1f}:{temporal:.1f}:{temporal*0.75:.1f}")
    
    # ----- 锐化 -----
    if enhance_settings and enhance_settings.get("sharpen_enabled", False):
        strength = enhance_settings.get("sharpen_strength", 1.0)
        # unsharp 参数：luma_msize_x:luma_msize_y:luma_amount:chroma_msize_x:chroma_msize_y:chroma_amount
        filters.append(f"unsharp=5:5:{strength:.2f}:5:5:{strength*0.5:.2f}")
    

    
    # ----- 色彩空间转换 -----
    if enhance_settings and enhance_settings.get("colorspace_enabled", False):
        matrix = enhance_settings.get("colorspace_matrix", "bt709:bt2020")
        filters.append(f"colormatrix={matrix}")

    # ----- 颜色校正（eq）-----
    if enhance_settings:
        eq_parts = []
        b = enhance_settings.get("eq_brightness", 0.0)
        if b != 0.0:
            eq_parts.append(f"brightness={b:.2f}")
        c = enhance_settings.get("eq_contrast", 1.0)
        if c != 1.0:
            eq_parts.append(f"contrast={c:.2f}")
        s = enhance_settings.get("eq_saturation", 1.0)
        if s != 1.0:
            eq_parts.append(f"saturation={s:.2f}")
        g = enhance_settings.get("eq_gamma", 1.0)
        if g != 1.0:
            eq_parts.append(f"gamma={g:.2f}")
        if eq_parts:
            filters.append(f"eq={':'.join(eq_parts)}")

    # ----- 色相调整（hue）-----
    if enhance_settings:
        hue_parts = []
        h_angle = enhance_settings.get("hue_angle", 0.0)
        if h_angle != 0.0:
            hue_parts.append(f"H={h_angle:.1f}")
        h_sat = enhance_settings.get("hue_saturation", 0.0)
        if h_sat != 0.0:
            hue_parts.append(f"s={h_sat:.2f}")
        if hue_parts:
            filters.append(f"hue={':'.join(hue_parts)}")


    # ----- 像素格式 -----
    if include_format and settings.get("pix_fmt_enabled", True):
        filters.append(f"format={settings.get('pix_fmt', 'yuv420p')}")
    
    # ----- 变速 -----
    if include_speed and settings.get("speed_enabled", False):
        try:
            factor = float(settings.get("speed_factor", "1.0"))
            if factor > 0 and factor != 1.0:
                filters.append(f"setpts={1.0/factor}*PTS")
        except ValueError:
            pass
    
    # ----- 字幕烧录 -----
    if include_subtitle and settings.get("subtitle_enabled", False):
        sub_path = settings.get("subtitle_path", "").strip()
        if sub_path:
            sub_path = sub_path.replace('\\', '/')
            sub_path = sub_path.replace(':', '\\:')
            sub_path = sub_path.replace("'", "\\'")
            filters.append(f"subtitles='{sub_path}'")

    # ----- 倒放 -----
    if reverse:
        filters.append("reverse")

    return ",".join(filters) if filters else "null"

def build_preview_filter_chain(settings: Dict[str, Any], target_height: int = 960, reverse: bool = False) -> str:
    """生成预览用的滤镜链，强制缩放到指定高度"""
    enhance_settings = settings.get("enhance", {})
    vf = build_video_filter_chain(
        settings,
        include_subtitle=True,
        include_speed=True,
        enhance_settings=enhance_settings,
        reverse=reverse
    )
    if vf != "null":
        return f"{vf},scale=-2:{target_height}"
    else:
        return f"scale=-2:{target_height}"

def build_atempo_chain(factor: float) -> str:
    """构建音频变速滤镜链，支持大于2倍或小于0.5倍的场景"""
    if factor <= 0 or factor == 1.0:
        return ""
    chain = []
    r = factor
    while r > 2.0:
        chain.append(2.0)
        r /= 2.0
    while r < 0.5:
        chain.append(0.5)
        r /= 0.5
    if abs(r - 1.0) > 1e-6:
        chain.append(r)
    if not chain:
        return ""
    atempo_filters = [f"atempo={v:.10f}".rstrip('0').rstrip('.') for v in chain]
    return ",".join(atempo_filters)

# ================== 视频尺寸计算 ==================
def get_video_dimensions(ffprobe_cmd: str, file_path: str) -> Tuple[Optional[int], Optional[int]]:
    """获取视频原始宽高（不考虑旋转）"""
    if not ffprobe_cmd or not os.path.exists(file_path):
        return None, None
    cmd = [ffprobe_cmd, "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height", "-of", "csv=p=0", file_path]
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=flags)
        if result.returncode == 0 and ',' in result.stdout.strip():
            w_str, h_str = result.stdout.strip().split(',')
            return int(w_str), int(h_str)
    except:
        pass
    return None, None

def get_video_rotated_dimensions(ffprobe_cmd: str, file_path: str, settings: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    """获取考虑元数据旋转和用户旋转后的尺寸"""
    w, h = get_video_dimensions(ffprobe_cmd, file_path)
    if w is None:
        return None, None
    # 检测元数据旋转
    if ffprobe_cmd:
        cmd = [ffprobe_cmd, "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=side_data_list", "-of", "json", file_path]
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=flags)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                streams = data.get("streams", [])
                if streams:
                    side_data = streams[0].get("side_data_list", [])
                    for sd in side_data:
                        if sd.get("rotation") is not None:
                            rot = int(sd.get("rotation"))
                            if rot % 180 == 90:
                                w, h = h, w
                            break
        except:
            pass
    # 用户旋转
    rotate = settings.get("rotate", "none")
    if rotate in ("90", "270"):
        w, h = h, w
    return w, h

def compute_rendered_size(original_w: int, original_h: int, settings: Dict[str, Any]) -> Tuple[int, int]:
    """根据设置（裁剪、缩放）计算最终渲染尺寸"""
    w, h = original_w, original_h

    # --- 防御性检查，避免除零 ---
    if w == 0 or h == 0:
        return 0, 0

    # 裁剪
    if settings.get("crop_enabled", False):
        crop_w = settings.get("crop_width", "").strip()
        crop_h = settings.get("crop_height", "").strip()
        if crop_w and crop_h:
            def eval_crop(expr):
                if not expr:
                    return None
                expr2 = expr.replace('iw', str(w)).replace('ih', str(h))
                result = safe_eval_expr(expr2, {})
                return result if result is not None else None
            cw = eval_crop(crop_w)
            ch = eval_crop(crop_h)
            if cw and ch and cw > 0 and ch > 0:
                w, h = cw, ch
    # 缩放
    if settings.get("scale_enabled", False):
        method = settings.get("scale_method", "width")
        sw = settings.get("scale_width", "").strip()
        sh = settings.get("scale_height", "").strip()
        try:
            if method == "width" and sw:
                target_w = int(float(sw))
                target_h = int(round(target_w * h / w))
                w, h = target_w, target_h
            elif method == "height" and sh:
                target_h = int(float(sh))
                target_w = int(round(target_h * w / h))
                w, h = target_w, target_h
            elif method == "exact" and sw and sh:
                w, h = int(float(sw)), int(float(sh))
        except:
            pass
    return w, h

# ================== 子进程执行封装 ==================
def run_ffmpeg_command(cmd: List[str], on_output_line: Optional[Callable] = None, timeout: Optional[float] = None) -> Tuple[int, str]:
    """
    执行 FFmpeg 命令，实时输出行。返回 (返回码, 完整stderr文本)
    cmd: 列表形式的命令参数
    """
    full_output = []
    try:
        proc = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8', errors='replace',
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        for line in proc.stdout:
            full_output.append(line)
            if on_output_line:
                on_output_line(line)
        proc.wait(timeout=timeout)
        return proc.returncode, "".join(full_output)
    except subprocess.TimeoutExpired:
        proc.kill()
        return -1, "进程超时被终止"
    except Exception as e:
        return -1, str(e)

def ffprobe_json(ffprobe_cmd: str, file_path: str) -> Optional[Dict[str, Any]]:
    """调用 ffprobe 获取媒体信息的 JSON 格式"""
    if not ffprobe_cmd or not os.path.exists(file_path):
        return None
    cmd = [ffprobe_cmd, "-v", "error", "-print_format", "json", "-show_streams", file_path]
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=flags, timeout=10)
        if res.returncode != 0:
            return None
        data = json.loads(res.stdout)
        if "streams" not in data:
            return None
        return data
    except:
        return None

def detect_crop(ffmpeg_cmd: str, input_file: str, timeout: float = 15) -> Optional[Tuple[int, int, int, int]]:
    """自动检测黑边，返回 (w, h, x, y) 或 None"""
    if not ffmpeg_cmd or not os.path.exists(input_file):
        return None
    cmd = [
        ffmpeg_cmd, "-i", input_file,
        "-t", "5",
        "-vf", "cropdetect=limit=0.1:round=2",
        "-f", "null", "-"
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding='utf-8', errors='replace',
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        _, stderr = proc.communicate(timeout=timeout)
        pattern = re.compile(r'crop=(\d+):(\d+):(\d+):(\d+)')
        matches = pattern.findall(stderr)
        if not matches:
            return None
        w, h, x, y = map(int, matches[-1])
        return w, h, x, y
    except:
        return None

# ================== 播放器预览 ==================
def launch_player(file_path: str, filters: str = "", audio_only: bool = False, volume: int = 10,
                  extra_args: Optional[List[str]] = None,
                  use_mpv: bool = False, mpv_path: str = "mpv", ffplay_path: Optional[str] = None):
    """安全启动播放器预览，列表模式 + 等号参数（兼容 mpv）"""
    file_path = normalize_path(file_path)
    extra_args = extra_args or []

    if audio_only:
        if use_mpv:
            player = mpv_path.strip() or "mpv"
            cmd = [player, file_path]
        else:
            if not ffplay_path:
                return
            cmd = [ffplay_path, "-nodisp", "-autoexit", "-volume", str(volume), file_path]
    else:
        if use_mpv:
            player = mpv_path.strip() or "mpv"
            cmd = [player, file_path]
            if filters and filters.strip():
                cmd.append(f"--vf={filters}")
            if extra_args:
                cmd.extend(extra_args)
        else:
            if not ffplay_path:
                return
            cmd = [ffplay_path, "-i", file_path]
            if filters and filters.strip():
                cmd.extend(["-vf", filters])
            cmd.extend(["-volume", str(volume)])
            if extra_args:
                cmd.extend(extra_args)
            if "-window_title" not in cmd:
                cmd.extend(["-window_title", f"预览: {os.path.basename(file_path)}"])

    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    except Exception as e:
        print(f"预览失败: {e}")

# ================== FFmpeg 编码器选项 ==================
ALL_VIDEO_ENCODERS = [
    "copy", "libx264", "libx265", "libvpx-vp9", "libsvtav1", "mpeg4", "libxvid", "libtheora",
    "h264_nvenc", "hevc_nvenc", "av1_nvenc",
    "h264_qsv", "hevc_qsv", "av1_qsv",
    "h264_amf", "hevc_amf", "av1_amf",
    "h264_vaapi", "hevc_vaapi",
    "h264_videotoolbox", "hevc_videotoolbox",
    "prores_ks", "prores_aw", "dnxhdenc", "ffv1", "libopenjpeg", "gif", "libwebp"
]

ALL_AUDIO_ENCODERS = ["copy", "aac", "libmp3lame", "opus", "ac3", "eac3",
                      "flac", "alac", "pcm_s16le", "libfdk_aac"]

HARDWARE_DECODER_OPTIONS = [
    "无",
    "auto (自动通用)",
    "cuda (NVIDIA通用)",
    "h264_cuvid (NVIDIA H.264)",
    "hevc_cuvid (NVIDIA HEVC)",
    "vp9_cuvid (NVIDIA VP9)",
    "av1_cuvid (NVIDIA AV1)",
    "qsv (Intel通用)",
    "h264_qsv (Intel H.264)",
    "hevc_qsv (Intel HEVC)",
    "vaapi (Linux VAAPI)",
    "videotoolbox (macOS)"
]

DECODER_MAP = {
    "auto (自动通用)": "auto",
    "cuda (NVIDIA通用)": "cuda",
    "h264_cuvid (NVIDIA H.264)": "h264_cuvid",
    "hevc_cuvid (NVIDIA HEVC)": "hevc_cuvid",
    "vp9_cuvid (NVIDIA VP9)": "vp9_cuvid",
    "av1_cuvid (NVIDIA AV1)": "av1_cuvid",
    "qsv (Intel通用)": "qsv",
    "h264_qsv (Intel H.264)": "h264_qsv",
    "hevc_qsv (Intel HEVC)": "hevc_qsv",
    "vaapi (Linux VAAPI)": "vaapi",
    "videotoolbox (macOS)": "videotoolbox",
    "无": "none"
}

# ----- 提示类 -----
class ToolTip:
    def __init__(self, widget, text, offset_x=15, offset_y=15, wraplength=400):
        self.widget = widget
        self.text = text
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.wraplength = wraplength
        self.tip_window = None
        widget.bind('<Enter>', self.show_tip)
        widget.bind('<Leave>', self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window:
            self.hide_tip()
        mouse_x = self.widget.winfo_pointerx()
        mouse_y = self.widget.winfo_pointery()
        ideal_x = mouse_x + self.offset_x
        ideal_y = mouse_y + self.offset_y
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{ideal_x}+{ideal_y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         wraplength=self.wraplength)
        label.pack()
        tw.update_idletasks()
        win_width = tw.winfo_width()
        win_height = tw.winfo_height()
        screen_width = tw.winfo_screenwidth()
        screen_height = tw.winfo_screenheight()
        x = max(0, min(ideal_x, screen_width - win_width))
        y = max(0, min(ideal_y, screen_height - win_height))
        if x <= mouse_x <= x + win_width and y <= mouse_y <= y + win_height:
            dx = 10 if ideal_x < screen_width // 2 else -10
            dy = 10 if ideal_y < screen_height // 2 else -10
            x = max(0, min(ideal_x + dx, screen_width - win_width))
            y = max(0, min(ideal_y + dy, screen_height - win_height))
        tw.wm_geometry(f"+{x}+{y}")

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None




# ================== 参数校验器 ==================
class ParamValidator:
    @staticmethod
    def validate_crf(value, encoder):
        if encoder in ("libx264", "libx265", "libvpx-vp9", "libsvtav1", "mpeg4", "libxvid"):
            if not 0 <= value <= 51:
                return False, "CRF 值必须在 0~51 之间"
        return True, ""

    @staticmethod
    def validate_cq(value):
        if not 0 <= value <= 51:
            return False, "CQ 值必须在 0~51 之间"
        return True, ""

    @staticmethod
    def validate_global_quality(value):
        if not 1 <= value <= 51:
            return False, "Global Quality 值必须在 1~51 之间"
        return True, ""

    @staticmethod
    def validate_bitrate(value):
        s = value.strip().lower()
        if s.endswith('k'):
            s = s[:-1]
        if s.isdigit():
            return True, ""
        return False, "比特率格式应为纯数字或数字+k，例如 1900 或 1900k"

    @staticmethod
    def validate_settings(settings):
        errors = []
        rc = settings.get("rate_control_type")
        encoder = settings.get("encoder")
        if rc == "crf":
            ok, msg = ParamValidator.validate_crf(settings.get("crf_value", 25), encoder)
            if not ok: errors.append(msg)
        elif rc == "cq":
            ok, msg = ParamValidator.validate_cq(settings.get("cq_value", 35))
            if not ok: errors.append(msg)
        elif rc == "global_quality":
            ok, msg = ParamValidator.validate_global_quality(settings.get("global_quality", 28))
            if not ok: errors.append(msg)
        elif rc == "bitrate":
            ok, msg = ParamValidator.validate_bitrate(settings.get("bitrate_video", "1900k"))
            if not ok: errors.append(msg)
        audio_bitrate = settings.get("audio_bitrate", "")
        if audio_bitrate:
            ok, msg = ParamValidator.validate_bitrate(audio_bitrate)
            if not ok:
                errors.append(f"音频比特率: {msg}")
        return errors

# ================== 编码器策略 ==================
class EncoderStrategy:
    def build_params(self, cmd_list: List[str], settings: Dict[str, Any]) -> List[str]:
        raise NotImplementedError

class SoftwareEncoderStrategy(EncoderStrategy):
    def build_params(self, cmd_list: List[str], settings: Dict[str, Any]) -> List[str]:
        vcodec = settings["encoder"]
        rc = settings["rate_control_type"]
        preset = settings.get("preset", "medium")
        cmd_list.extend(["-c:v", vcodec, "-preset", preset])
        
        # 高级参数
        tune = settings.get("tune", "").strip()
        if tune and tune != "无":
            cmd_list.extend(["-tune", tune])
        
        profile = settings.get("profile", "").strip()
        if profile and profile != "无":
            cmd_list.extend(["-profile:v", profile])
        
        level = settings.get("level", "").strip()
        if level and level != "无":
            cmd_list.extend(["-level:v", level])

        maxrate = settings.get("maxrate", "").strip()
        if maxrate:
            cmd_list.extend(["-maxrate", maxrate + "k"])
        bufsize = settings.get("bufsize", "").strip()
        if bufsize:
            cmd_list.extend(["-bufsize", bufsize + "k"])
        
        if rc == "crf":
            cmd_list.extend(["-crf", str(settings['crf_value'])])
        elif rc == "bitrate":
            bitrate = fix_bitrate_value(settings["bitrate_video"])
            cmd_list.extend(["-b:v", bitrate or '1000k'])
        return cmd_list

class NVENCEncoderStrategy(EncoderStrategy):
    def build_params(self, cmd_list: List[str], settings: Dict[str, Any]) -> List[str]:
        vcodec = settings["encoder"]
        preset = settings.get("preset", "p4")
        rc = settings["rate_control_type"]
        cmd_list.extend(["-c:v", vcodec, "-preset", preset])
        if rc == "cq":
            cmd_list.extend(["-cq", str(settings['cq_value'])])
        elif rc == "bitrate":
            bitrate = fix_bitrate_value(settings["bitrate_video"])
            cmd_list.extend(["-b:v", bitrate or '1000k'])
        

        maxrate = settings.get("maxrate", "").strip()
        if maxrate:
            cmd_list.extend(["-maxrate", maxrate + "k"])
        bufsize = settings.get("bufsize", "").strip()
        if bufsize:
            cmd_list.extend(["-bufsize", bufsize + "k"])
        return cmd_list

class QSVEncoderStrategy(EncoderStrategy):
    def build_params(self, cmd_list: List[str], settings: Dict[str, Any]) -> List[str]:
        vcodec = settings["encoder"]
        preset = settings.get("preset", "p4")
        rc = settings["rate_control_type"]
        cmd_list.extend(["-c:v", vcodec, "-preset", preset])
        if rc == "global_quality":
            cmd_list.extend(["-global_quality", str(settings['global_quality'])])
        elif rc == "bitrate":
            bitrate = fix_bitrate_value(settings["bitrate_video"])
            cmd_list.extend(["-b:v", bitrate or '1000k'])
        
        maxrate = settings.get("maxrate", "").strip()
        if maxrate:
            cmd_list.extend(["-maxrate", maxrate + "k"])
        bufsize = settings.get("bufsize", "").strip()
        if bufsize:
            cmd_list.extend(["-bufsize", bufsize + "k"])
        return cmd_list

class OtherEncoderStrategy(EncoderStrategy):
    def build_params(self, cmd_list: List[str], settings: Dict[str, Any]) -> List[str]:
        vcodec = settings["encoder"]
        bitrate = fix_bitrate_value(settings["bitrate_video"])
        cmd_list.extend(["-c:v", vcodec, "-b:v", bitrate or '1000k'])
        
        # 预设参数（不同编码器不同）
        preset = settings.get("preset", "").strip()
        if preset:
            if vcodec in ("h264_amf", "hevc_amf", "av1_amf"):
                cmd_list.extend(["-quality", preset])
            elif vcodec in ("h264_vaapi", "hevc_vaapi"):
                cmd_list.extend(["-compression_level", preset])
            elif vcodec in ("h264_videotoolbox", "hevc_videotoolbox"):
                cmd_list.extend(["-quality", preset])
            elif vcodec in ("prores_ks", "prores_aw"):
                pass
            else:
                cmd_list.extend(["-preset", preset])
        

        maxrate = settings.get("maxrate", "").strip()
        if maxrate:
            cmd_list.extend(["-maxrate", maxrate + "k"])
        bufsize = settings.get("bufsize", "").strip()
        if bufsize:
            cmd_list.extend(["-bufsize", bufsize + "k"])
        return cmd_list

def get_encoder_strategy(encoder: str) -> EncoderStrategy:
    if encoder in ("libx264", "libx265", "libvpx-vp9", "libsvtav1", "mpeg4", "libxvid", "libtheora"):
        return SoftwareEncoderStrategy()
    elif encoder in ("h264_nvenc", "hevc_nvenc", "av1_nvenc"):
        return NVENCEncoderStrategy()
    elif encoder in ("h264_qsv", "hevc_qsv", "av1_qsv"):
        return QSVEncoderStrategy()
    else:
        return OtherEncoderStrategy()

# ================== 视频编码与质量组件 ==================
class VideoEncoderFrame(ttk.LabelFrame):

    ENCODER_PROFILES = {
        # 软件编码
        "libx264":    ["无", "baseline", "main", "high", "high10", "high422", "high444"],
        "libx265":    ["无", "main", "main10", "main422-10", "main444-8", "main444-10"],
        "libvpx-vp9": ["无", "0", "1", "2", "3"],
        "libsvtav1":  ["无", "main", "high", "professional"],
        "mpeg4":      ["无"],
        "libxvid":    ["无"],
        "libtheora":  ["无"],

        # NVIDIA NVENC
        "h264_nvenc": ["无", "baseline", "main", "high"],
        "hevc_nvenc": ["无", "main", "main10"],
        "av1_nvenc":  ["无", "main", "high", "professional"],

        # Intel QSV
        "h264_qsv":   ["无", "baseline", "main", "high"],
        "hevc_qsv":   ["无", "main", "main10"],
        "av1_qsv":    ["无", "main", "high", "professional"],

        # AMD AMF
        "h264_amf":   ["无", "baseline", "main", "high"],
        "hevc_amf":   ["无", "main", "main10"],
        "av1_amf":    ["无", "main", "high", "professional"],

        # VAAPI
        "h264_vaapi": ["无", "baseline", "main", "high"],
        "hevc_vaapi": ["无", "main", "main10"],

        # VideoToolbox
        "h264_videotoolbox": ["无", "baseline", "main", "high"],
        "hevc_videotoolbox": ["无", "main", "main10"],

        # 专业格式
        "prores_ks":  ["无", "proxy", "lt", "standard", "hq", "4444", "4444xq"],
        "prores_aw":  ["无", "standard", "hq", "4444"],
        "dnxhdenc":   ["无"],
        "ffv1":       ["无"],
        "libopenjpeg":["无"],

        # 图片/动图
        "gif":        ["无"],
        "libwebp":    ["无"],
    }
    DEFAULT_PROFILES = ["无"]

    ENCODER_PRESETS = {
        # 软件编码（libx264/libx265 等）
        "libx264":    ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
        "libx265":    ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
        "libvpx-vp9": ["good", "best", "rt"],   # VP9 的预设
        "libsvtav1":  ["0", "1", "2", "3", "4", "5", "6", "7", "8"],   # SVT-AV1 预设 0~8，速度从快到慢
        "mpeg4":      ["medium"],
        "libxvid":    ["medium"],
        "libtheora":  ["medium"],

        # NVENC
        "h264_nvenc": ["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
        "hevc_nvenc": ["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
        "av1_nvenc":  ["p1", "p2", "p3", "p4", "p5", "p6", "p7"],

        # Intel QSV
        "h264_qsv":   ["veryfast", "faster", "fast", "medium", "slow", "slower"],
        "hevc_qsv":   ["veryfast", "faster", "fast", "medium", "slow", "slower"],
        "av1_qsv":    ["veryfast", "faster", "fast", "medium", "slow", "slower"],

        # AMD AMF (常用)
        "h264_amf":   ["quality", "speed", "balanced"],
        "hevc_amf":   ["quality", "speed", "balanced"],
        "av1_amf":    ["quality", "speed", "balanced"],

        # VAAPI (Linux)
        "h264_vaapi": ["7", "1"],
        "hevc_vaapi": ["7", "1"],

        # VideoToolbox (macOS)
        "h264_videotoolbox": ["default", "quality", "speed"],
        "hevc_videotoolbox": ["default", "quality", "speed"],

        # 专业格式/无损（一般无预设或只支持默认）
        "prores_ks":  ["standard", "hq", "4444", "4444xq"],
        "prores_aw":  ["standard", "hq", "4444"],
        "dnxhdenc":   ["medium"],
        "ffv1":       ["medium"],
        "libopenjpeg":["medium"],
        "gif":        ["medium"],
        "libwebp":    ["default", "photo", "picture", "drawing", "icon", "text"],
    }
    DEFAULT_PRESETS = ["medium"]   # 未知编码器 fallback


    def __init__(self, parent, app, refresh_callback=None, **kwargs):
        super().__init__(parent, text="视频编码与质量", padding="5", **kwargs)
        self.app = app                     # 保存主界面引用
        self.refresh_callback = refresh_callback
        self._suppress_update = False
        self._last_encoder = None          # 用于记录上次编码器
        self._suppress_copy_hint = False   # 加载预设时禁止提示
        self.create_widgets()
        self.setup_bindings()

    def create_widgets(self):
        self.encoder_label = ttk.Label(self, text="编码器:")
        self.encoder_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ToolTip(self.encoder_label,
                "【编码器分类说明】\n"
                "• 流复制: copy (直接复制流，不重新编码)\n"
                "• 软件编码: libx264, libx265, libvpx-vp9, libsvtav1, mpeg4, libxvid, libtheora\n"
                "  兼容性好，画质优，适合通用场景\n"
                "• NVIDIA NVENC: h264_nvenc, hevc_nvenc, av1_nvenc\n"
                "  硬件加速，编码速度快，适合实时处理\n"
                "• Intel QSV: h264_qsv, hevc_qsv, av1_qsv\n"
                "  Intel 集显硬件加速，低功耗\n"
                "• AMD AMF: h264_amf, hevc_amf, av1_amf\n"
                "  AMD 显卡硬件加速\n"
                "• 其他硬件: h264_vaapi, hevc_vaapi (Linux VAAPI),\n"
                "  h264_videotoolbox, hevc_videotoolbox (macOS)\n"
                "• 专业/无损格式: prores_ks, prores_aw, dnxhdenc, ffv1, libopenjpeg\n"
                "• 图片/动图: gif, libwebp\n"
                "提示: 硬件编码速度快但画质可能略逊，软件编码兼容性最佳。\n"
                "• 硬件编码还需要 FFmpeg 版本和显卡 API 对应。\n",
                wraplength=600)

        self.vcodec = tk.StringVar(value="libx265")
        self.vcodec_combo = ttk.Combobox(self, textvariable=self.vcodec,
                                         values=ALL_VIDEO_ENCODERS, state="readonly", width=18)
        self.vcodec_combo.grid(row=0, column=1, sticky="w", padx=5, pady=2)

        preset_frame = ttk.Frame(self)
        preset_frame.grid(row=0, column=2, sticky="w", padx=5, pady=2)
        preset_label = ttk.Label(preset_frame, text="编码预设:")
        preset_label.pack(side=tk.LEFT, padx=(0,5))
        ToolTip(preset_label,
                "编码预设控制速度与压缩效率的平衡，推荐保持默认 medium。\n\n"
                "• 软件编码器：ultrafast ~ veryslow（速度递减，画质/压缩率递增）\n"
                "• NVENC 硬件：p1 ~ p7（p1 最快，p7 画质最好）\n"
                "• QSV 硬件：veryfast ~ slower（类似软件预设）\n"
                "• AMF 硬件：quality / speed / balanced\n"
                "• 其他编码器请参考 FFmpeg 文档",
                wraplength=500)

        self.preset = tk.StringVar(value="medium")
        self.preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset,
                                         values=[],          # ← 初始为空
                                         state="readonly", width=12)
        self.preset_combo.pack(side=tk.LEFT)


        ttk.Label(self, text="码率控制:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.rate_control_type = tk.StringVar(value="crf")
        rc_frame = ttk.Frame(self)
        rc_frame.grid(row=2, column=1, columnspan=2, sticky="w", padx=5, pady=2)
        for text, val in [("CRF (CPU编码)", "crf"), ("CQ (NVENC)", "cq"),
                          ("Global Quality (QSV)", "global_quality"), ("固定比特率", "bitrate")]:
            ttk.Radiobutton(rc_frame, text=text, variable=self.rate_control_type,
                            value=val).pack(side=tk.LEFT, padx=2)

        self.dynamic_frame = ttk.Frame(self)
        self.dynamic_frame.grid(row=3, column=0, columnspan=3, sticky="we", pady=0, padx=5)

        self.crf_value = tk.IntVar(value=25)
        self.cq_value = tk.IntVar(value=35)
        self.global_quality = tk.IntVar(value=28)
        self.bitrate_video = tk.StringVar(value="1900k")

        self.update_dynamic_controls()

        # GIF 选项按钮（初始隐藏）
        self.gif_btn_frame = ttk.Frame(self)
        self.gif_btn_frame.grid(row=4, column=0, columnspan=3, sticky="we", pady=5, padx=5)
        self.gif_btn_frame.grid_remove()  # 默认隐藏
        
        self.gif_options_btn = ttk.Button(self.gif_btn_frame, text="GIF 输出选项...", command=self.open_gif_options)
        self.gif_options_btn.pack(side=tk.LEFT)

        # 高级选项面板
        self.advanced_frame = ttk.Frame(self)
        self.advanced_frame.grid(row=4, column=0, columnspan=3, sticky="we", pady=5, padx=5)
        # 默认隐藏
        self.advanced_frame.grid_remove()

        # 在 advanced_frame 中添加控件
        row1 = ttk.Frame(self.advanced_frame)
        row1.pack(fill=tk.X, pady=2)
        
        # tune
        tune_label = ttk.Label(row1, text="tune:")
        tune_label.pack(side=tk.LEFT)
        ToolTip(tune_label,
                "针对特定内容类型优化编码参数（主要适用于软件编码器）：\n"
                "• film: 高画质电影/真人视频 (H.264)\n"
                "• animation: 卡通/动画 (H.264)\n"
                "• grain: 保留胶片颗粒感 (H.264/H.265)\n"
                "• stillimage: 幻灯片/静态画面 (H.264)\n"
                "• psnr: 优化 PSNR 指标 (H.264/H.265)\n"
                "• ssim: 优化 SSIM 指标 (H.264/H.265)\n"
                "• fastdecode: 加速解码 (H.264/H.265)\n"
                "• zerolatency: 最低延迟 (H.264/H.265)\n"
                "• vmaf: 优化 VMAF 分数 (H.264)\n"
                "• screen: 屏幕内容/录屏优化 (H.264)\n"
                "提示：硬件编码器及 AV1 通常不支持 tune，请保持默认。",
                wraplength=500)
        self.tune_var = tk.StringVar(value="无")
        tune_combo = ttk.Combobox(row1, textvariable=self.tune_var,
                                  values=["无", "film","animation","grain","stillimage","psnr","ssim","fastdecode","zerolatency","vmaf", "screen"],
                                  state="readonly", width=10)
        tune_combo.pack(side=tk.LEFT, padx=5)

        
        # profile
        profile_label = ttk.Label(row1, text="profile:")
        profile_label.pack(side=tk.LEFT, padx=(10,0))
        ToolTip(profile_label,
                "如无特殊兼容性要求，建议保持默认（无）。\n\n"
                "H.264 配置文件：\n"
                "• baseline: 最广兼容（移动设备）\n"
                "• main: 主流（电视/广播）\n"
                "• high: 高清/蓝光（最佳画质）\n"
                "• high10/high422/high444: 专业/高色深\n\n"
                "HEVC (H.265) 配置文件：\n"
                "• main10：10-bit 色深，HDR 视频常用\n"
                "• main422-10：4:2:2 色度采样，10-bit，专业制作\n"
                "• main444-8：4:4:4 色度采样，8-bit，无损或高质量\n"
                "• main444-10：4:4:4 色度采样，10-bit，最高质量\n\n"
                "AV1 配置文件：\n"
                "• main: 基本兼容\n"
                "• high: 支持更高色深和色度采样\n"
                "• professional: 支持最高质量（10-bit/4:4:4）\n\n"
                "提示：请根据所选编码器选择对应的 Profile，否则可能报错。",
                wraplength=500)
        self.profile_var = tk.StringVar(value="无")
        self.profile_combo = ttk.Combobox(
            row1,
            textvariable=self.profile_var,
            values=[],   # 初始为空，由更新函数填充
            state="readonly",
            width=10
        )
        self.profile_combo.pack(side=tk.LEFT, padx=5)

        
        # level
        level_label = ttk.Label(row1, text="level:")
        level_label.pack(side=tk.LEFT, padx=(10,0))
        ToolTip(level_label,
                "必须配合 Profile 使用！不确定请保持「无」让系统自动匹配。\n\n"
                "H.264 级别（限制码率、分辨率、帧率）：\n"
                "• 3.0 ~ 4.2: 720p/1080p 常用\n"
                "• 5.0 ~ 5.2: 4K 或高码率\n"
                "• 6.0+: 8K/超高码率\n"
                "选择过高可能导致设备不兼容，\n"
                "选择过低可能无法播放高分辨率视频。\n\n"
                "不同编码格式（H.265/AV1 等）级别规则有所差异，请参考 FFmpeg 文档",
                wraplength=500)
        self.level_var = tk.StringVar(value="无")
        level_combo = ttk.Combobox(row1, textvariable=self.level_var,
                                   values=["无", "1.0","1b","1.1","1.2","1.3","2.0","2.1","2.2",
                                           "3.0","3.1","3.2","4.0","4.1","4.2",
                                           "5.0","5.1","5.2","6.0","6.1","6.2"],
                                   state="readonly", width=6)
        level_combo.pack(side=tk.LEFT, padx=5)

        
        # 第二行：maxrate, bufsize
        row2 = ttk.Frame(self.advanced_frame)
        row2.pack(fill=tk.X, pady=2)
        maxrate_label = ttk.Label(row2, text="最大比特率 (kbps):")
        maxrate_label.pack(side=tk.LEFT)
        ToolTip(maxrate_label,
                "设置最大比特率（kbps），用于限制峰值码率。\n"
                "适用于流媒体或网络传输，避免瞬间码率过高。",
                wraplength=400)
        self.maxrate_var = tk.StringVar(value="")
        maxrate_entry = ttk.Entry(row2, textvariable=self.maxrate_var, width=8)
        maxrate_entry.pack(side=tk.LEFT, padx=5)

        
        bufsize_label = ttk.Label(row2, text="缓冲区大小 (kbps):")
        bufsize_label.pack(side=tk.LEFT, padx=(10,0))
        ToolTip(bufsize_label,
                "编码器缓冲区大小（kbps）。\n"
                "通常设为最大比特率的 2 倍左右，\n"
                "用于控制码率波动的平滑度。",
                wraplength=400)
        self.bufsize_var = tk.StringVar(value="")
        bufsize_entry = ttk.Entry(row2, textvariable=self.bufsize_var, width=8)
        bufsize_entry.pack(side=tk.LEFT, padx=5)


        # GIF 参数变量（存储实际值）
        self.gif_loop = tk.IntVar(value=0)
        self.gif_dither = tk.StringVar(value="bayer")
        self.gif_bayer_scale = tk.IntVar(value=2)
        self.gif_max_colors = tk.IntVar(value=256)
        
        self._on_gif_codec_toggle()
        self._update_profile_options()
        self._update_preset_options()


    def _update_preset_options(self, *args):
        """根据当前编码器动态更新 preset 下拉选项"""
        encoder = self.vcodec.get()
        presets = self.ENCODER_PRESETS.get(encoder, self.DEFAULT_PRESETS)
        self.preset_combo['values'] = presets
    
        # 如果当前选中的值不在新列表中，自动设为列表第一个
        current = self.preset.get()
        if current not in presets:
            self.preset.set(presets[0] if presets else "medium")

    def _update_profile_options(self, *args):
        """根据当前编码器动态更新 profile 下拉选项"""
        encoder = self.vcodec.get()
        profiles = self.ENCODER_PROFILES.get(encoder, self.DEFAULT_PROFILES)
        self.profile_combo['values'] = profiles
    
        # 如果当前选中的值不在新列表中，自动设为 "无"
        current = self.profile_var.get()
        if current not in profiles:
            self.profile_var.set("无")

    def _on_gif_codec_toggle(self, *args):
        if self.vcodec.get() == "gif":
            self.gif_btn_frame.grid()
            self.advanced_frame.grid_remove()
        else:
            self.gif_btn_frame.grid_remove()
            self.advanced_frame.grid()

    def setup_bindings(self):
        self.vcodec.trace_add("write", self.auto_set_rate_control_by_codec)
        self.rate_control_type.trace_add("write", self.on_rate_control_change)
        self.vcodec.trace_add("write", self._on_gif_codec_toggle)
        self.vcodec.trace_add("write", self._update_profile_options)
        self.vcodec.trace_add("write", self._update_preset_options)
        self.vcodec.trace_add("write", self._on_encoder_changed_for_copy_hint)


    def _on_encoder_changed_for_copy_hint(self, *args):
        """当编码器发生变化时，检测是否切换为 copy，仅在用户交互时提示"""
        if self._suppress_copy_hint:
            self._suppress_copy_hint = False
            return
    
        new_encoder = self.vcodec.get()
        old_encoder = getattr(self, '_last_encoder', None)
        if old_encoder is None:
            self._last_encoder = new_encoder
            return
    
        if new_encoder == "copy" and old_encoder != "copy":
            self._show_copy_hint()
        self._last_encoder = new_encoder
    
    def _show_copy_hint(self):
        """输出 copy 提示到主界面日志"""
        if self.app:
            self.app._append_info_ui("当前编码器为 copy，视频滤镜、帧率、像素格式等设置将被忽略。")

    def open_gif_options(self):
        win = tk.Toplevel(self)
        win.title("GIF 输出选项")
        win.transient(self)
        win.grab_set()
        win.withdraw()
        width, height = 380, 230  # 高度缩小（去掉一行）
        center_window(win, width, height)
    
        main = ttk.Frame(win, padding="10")
        main.pack(fill=tk.BOTH, expand=True)
    
        # 循环次数
        row1 = ttk.Frame(main)
        row1.pack(fill=tk.X, pady=5)
        ttk.Label(row1, text="循环次数 (0=无限):").pack(side=tk.LEFT)
        loop_var = tk.IntVar(value=self.gif_loop.get())
        ttk.Spinbox(row1, from_=0, to=1000, width=6, textvariable=loop_var).pack(side=tk.LEFT, padx=5)
    
        # 抖动算法 + bayer_scale
        row2 = ttk.Frame(main)
        row2.pack(fill=tk.X, pady=5)
        ttk.Label(row2, text="抖动算法:").pack(side=tk.LEFT)
        dither_var = tk.StringVar(value=self.gif_dither.get())
        dither_combo = ttk.Combobox(row2, textvariable=dither_var,
                                    values=["none", "bayer", "floyd_steinberg", "sierra2_4a"],
                                    state="readonly", width=15)
        dither_combo.pack(side=tk.LEFT, padx=5)
    
        bayer_frame = ttk.Frame(row2)
        bayer_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(bayer_frame, text="Bayer Scale:").pack(side=tk.LEFT)
        bayer_scale_var = tk.IntVar(value=self.gif_bayer_scale.get())
        bayer_spin = ttk.Spinbox(bayer_frame, from_=0, to=5, width=4, textvariable=bayer_scale_var)
        bayer_spin.pack(side=tk.LEFT, padx=2)
    
        def on_dither_change(*args):
            if dither_var.get() == "bayer":
                bayer_frame.pack(side=tk.LEFT, padx=5)
            else:
                bayer_frame.pack_forget()
        dither_var.trace_add("write", on_dither_change)
        on_dither_change()
    
        # 调色板大小
        row3 = ttk.Frame(main)
        row3.pack(fill=tk.X, pady=5)
        ttk.Label(row3, text="调色板大小 (max_colors):").pack(side=tk.LEFT)
        max_colors_var = tk.IntVar(value=self.gif_max_colors.get())
        ttk.Spinbox(row3, from_=2, to=256, width=6, textvariable=max_colors_var).pack(side=tk.LEFT, padx=5)
    
        # 提示信息
        info_label = ttk.Label(main, text="提示：GIF 速度和大小由「视频滤镜」中的帧率控制。", foreground="gray")
        info_label.pack(pady=5)
    
        # 按钮
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=10)
        def save():
            self.gif_loop.set(loop_var.get())
            self.gif_dither.set(dither_var.get())
            self.gif_bayer_scale.set(bayer_scale_var.get())
            self.gif_max_colors.set(max_colors_var.get())
            if self.refresh_callback:
                self.refresh_callback()
            win.destroy()
        def cancel():
            win.destroy()
        ttk.Button(btn_frame, text="保存", command=save).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=cancel).pack(side=tk.LEFT, padx=10)
        win.wait_window()


    def update_dynamic_controls(self):
        for widget in self.dynamic_frame.winfo_children():
            widget.destroy()
        rc = self.rate_control_type.get()
        if rc == "crf":
            frame = ttk.Frame(self.dynamic_frame)
            frame.pack(fill=tk.X, expand=True)
            ttk.Label(frame, text="CRF (0~51，越小质量越好):").pack(side=tk.LEFT)
            self.crf_slider = ttk.Scale(frame, from_=0, to=51, variable=self.crf_value, orient=tk.HORIZONTAL)
            self.crf_slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            self.crf_label = ttk.Label(frame, text=str(self.crf_value.get()), width=4)
            self.crf_label.pack(side=tk.LEFT)
            self.crf_slider.configure(command=lambda v: self.crf_label.config(text=str(int(float(v)))))
        elif rc == "cq":
            frame = ttk.Frame(self.dynamic_frame)
            frame.pack(fill=tk.X, expand=True)
            ttk.Label(frame, text="CQ (0~51，越小质量越好，NVENC):").pack(side=tk.LEFT)
            self.cq_slider = ttk.Scale(frame, from_=0, to=51, variable=self.cq_value, orient=tk.HORIZONTAL)
            self.cq_slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            self.cq_label = ttk.Label(frame, text=str(self.cq_value.get()), width=4)
            self.cq_label.pack(side=tk.LEFT)
            self.cq_slider.configure(command=lambda v: self.cq_label.config(text=str(int(float(v)))))
        elif rc == "global_quality":
            frame = ttk.Frame(self.dynamic_frame)
            frame.pack(fill=tk.X, expand=True)
            ttk.Label(frame, text="Global Quality (1~51，越小质量越好，QSV):").pack(side=tk.LEFT)
            self.gq_slider = ttk.Scale(frame, from_=1, to=51, variable=self.global_quality, orient=tk.HORIZONTAL)
            self.gq_slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            self.gq_label = ttk.Label(frame, text=str(self.global_quality.get()), width=4)
            self.gq_label.pack(side=tk.LEFT)
            self.gq_slider.configure(command=lambda v: self.gq_label.config(text=str(int(float(v)))))
        elif rc == "bitrate":
            frame = ttk.Frame(self.dynamic_frame)
            frame.pack(fill=tk.X, expand=True)
            ttk.Label(frame, text="固定比特率:").pack(side=tk.LEFT)
            self.bitrate_entry = ttk.Entry(frame, textvariable=self.bitrate_video, width=12)
            self.bitrate_entry.pack(side=tk.LEFT, padx=5)
            self.bitrate_entry.bind("<FocusOut>", self.fix_bitrate_value)

    def fix_bitrate_value(self, event=None):
        val = self.bitrate_video.get().strip()
        if not val:
            self.bitrate_video.set("1000k")
        elif re.match(r'^\d+$', val):
            self.bitrate_video.set(val + "k")

    def on_rate_control_change(self, *args):
        if getattr(self, '_suppress_update', False):
            return
        self.update_dynamic_controls()
        self.auto_set_codec_by_rate_control()
        rc = self.rate_control_type.get()
        # 根据码率控制类型推荐预设，但需检查是否存在
        if rc in ("crf", "global_quality"):
            recommended = "medium"
        elif rc == "cq":
            recommended = "p4"
        else:
            recommended = "medium"
        # 获取当前预设列表，若推荐值不在列表中，则设为列表第一个
        available = self.preset_combo['values']
        if available and recommended in available:
            self.preset.set(recommended)
        elif available:
            self.preset.set(available[0])

    def auto_set_codec_by_rate_control(self):
        current = self.vcodec.get()
        if current == "copy":
            return  # 不要自动改变 copy
        rc = self.rate_control_type.get()
        if rc == "crf":
            if current not in ("libx264", "libx265", "libvpx-vp9", "libsvtav1", "mpeg4", "libxvid"):
                self.vcodec.set("libx265")
        elif rc == "cq":
            if current not in ("h264_nvenc", "hevc_nvenc", "av1_nvenc"):
                self.vcodec.set("hevc_nvenc")
                self.preset.set("p4")
        elif rc == "global_quality":
            if current not in ("h264_qsv", "hevc_qsv", "av1_qsv"):
                self.vcodec.set("hevc_qsv")

    def auto_set_rate_control_by_codec(self, *args):
        codec = self.vcodec.get()
        old_rc = self.rate_control_type.get()
        new_rc = None
        if codec in ("libx264", "libx265", "libvpx-vp9", "libsvtav1", "mpeg4", "libxvid", "libtheora"):
            new_rc = "crf"
        elif codec in ("h264_nvenc", "hevc_nvenc", "av1_nvenc"):
            new_rc = "cq"
        elif codec in ("h264_qsv", "hevc_qsv", "av1_qsv"):
            new_rc = "global_quality"
        elif codec in ("h264_amf", "hevc_amf", "av1_amf", "h264_vaapi", "hevc_vaapi",
                       "h264_videotoolbox", "hevc_videotoolbox", "prores_ks", "prores_aw",
                       "dnxhdenc", "ffv1", "libopenjpeg", "gif"):
            new_rc = "bitrate"
        if new_rc and new_rc != old_rc:
            self.rate_control_type.set(new_rc)

    def get_settings(self):
        return {
            "encoder": self.vcodec.get(),
            "preset": self.preset.get(),
            "rate_control_type": self.rate_control_type.get(),
            "crf_value": self.crf_value.get(),
            "cq_value": self.cq_value.get(),
            "global_quality": self.global_quality.get(),
            "bitrate_video": self.bitrate_video.get(),
            # GIF 参数
            "gif_loop": self.gif_loop.get(),
            "gif_dither": self.gif_dither.get(),
            "gif_bayer_scale": self.gif_bayer_scale.get(),
            "gif_max_colors": self.gif_max_colors.get(),

            "tune": self.tune_var.get(),
            "profile": self.profile_var.get(),
            "level": self.level_var.get(),
            "maxrate": self.maxrate_var.get(),
            "bufsize": self.bufsize_var.get(),
        }

    def set_settings(self, settings):
        self._suppress_update = True
        self._suppress_copy_hint = True
        try:
            # 安全获取 preset，若缺失则根据码率控制类型推断默认值
            preset_val = settings.get("preset")
            if preset_val is None or preset_val == "":
                rc = settings.get("rate_control_type", "crf")
                if rc == "cq":
                    preset_val = "p4"
                elif rc == "global_quality":
                    preset_val = "medium"
                else:
                    preset_val = "medium"
            self.preset.set(preset_val)
    
            self.vcodec.set(settings.get("encoder", "libx265"))
            self._update_profile_options()
            self._update_preset_options()
            self.rate_control_type.set(settings.get("rate_control_type", "crf"))
            self.crf_value.set(settings.get("crf_value", 26))
            self.cq_value.set(settings.get("cq_value", 35))
            self.global_quality.set(settings.get("global_quality", 26))
            self.bitrate_video.set(settings.get("bitrate_video", "1900k"))
    
            # GIF 参数
            self.gif_loop.set(settings.get("gif_loop", 0))
            self.gif_dither.set(settings.get("gif_dither", "bayer"))
            self.gif_bayer_scale.set(settings.get("gif_bayer_scale", 2))
            self.gif_max_colors.set(settings.get("gif_max_colors", 256))
            self._on_gif_codec_toggle()
    
            # 高级参数
            self.tune_var.set(settings.get("tune", "无") or "无")
            self.profile_var.set(settings.get("profile", "无") or "无")
            self.level_var.set(settings.get("level", "无") or "无")
            self.maxrate_var.set(settings.get("maxrate", ""))
            self.bufsize_var.set(settings.get("bufsize", ""))
    
        finally:
            self._suppress_update = False
            self._suppress_copy_hint = False
            self._last_encoder = self.vcodec.get()
            self.update_dynamic_controls()

# ================== 视频滤镜组件 ==================
class VideoFilterFrame(ttk.LabelFrame):
    PIX_FMTS = [
        "yuv420p", "yuv422p", "yuv444p",
        "yuv420p10le", "yuv422p10le", "yuv444p10le",
        "p010le", "p016le", "nv12", "nv16",
        "gbrp", "gbrp10le", "gray", "gray10le", "ya8", "yuva420p"
    ]




    def __init__(self, parent, app, preview_callback=None, **kwargs):
        super().__init__(parent, text="视频滤镜 (裁剪/旋转/缩放/反交错/像素格式/变速/倒放)", padding="5", **kwargs)
        self.app = app
        self.current_file = None
        self.current_track = None
        self.override_settings = None
        self.get_trim_settings_callback = None
        self._preview_callback = preview_callback
        self._visual_crop_start_time = None
        self.create_widgets()

        # 用于控制裁剪提取线程的取消
        self._crop_extract_thread = None
        self._crop_cancel_event = threading.Event()

        self.enhance_settings = {
            "denoise_enabled": False,
            "denoise_spatial": 4.0,
            "denoise_temporal": 3.0,
            "sharpen_enabled": False,
            "sharpen_strength": 1.0,
            "ivtc_enabled": False,
            "deblock_enabled": False,
            "deblock_strength": 4,
            "colorspace_enabled": False,
            "colorspace_matrix": "bt709:bt2020",
            "eq_brightness": 0.0,
            "eq_contrast": 1.0,
            "eq_saturation": 1.0,
            "eq_gamma": 1.0,
            "hue_angle": 0.0,
            "hue_saturation": 0.0,
        }


    def create_widgets(self):
        main_pane = ttk.Frame(self)
        main_pane.pack(fill=tk.BOTH, expand=True)
    
        left_frame = ttk.Frame(main_pane)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,5))
    
        # 帧率行
        line1 = ttk.Frame(left_frame)
        line1.pack(fill=tk.X, pady=2)
        ttk.Label(line1, text="帧率:").pack(side=tk.LEFT)
        self.frame_rate_type = tk.StringVar(value="keep")
        self.frame_rate_custom = tk.StringVar(value="30")
        ttk.Radiobutton(line1, text="保持源", variable=self.frame_rate_type,
                        value="keep").pack(side=tk.LEFT, padx=(5, 0))
        ttk.Radiobutton(line1, text="指定", variable=self.frame_rate_type,
                        value="custom").pack(side=tk.LEFT, padx=5)
        self.fps_combo = ttk.Combobox(
            line1,
            textvariable=self.frame_rate_custom,
            width=9,
            values=["30", "29.970030", "23.976024", "24", "25", "48", "59.940060", "60", "50", "10", "12"]
        )
        self.fps_combo.pack(side=tk.LEFT, padx=(0, 2))
        ttk.Label(line1, text="fps").pack(side=tk.LEFT, padx=(0, 10))
    
        self.subtitle_enabled = tk.BooleanVar(value=False)
        self.subtitle_path = tk.StringVar()

        subtitle_label = ttk.Label(line1, text="烧录字幕:")
        subtitle_label.pack(side=tk.LEFT, padx=(2, 5))
        ToolTip(subtitle_label, 
                "将字幕永久嵌入视频画面（硬烧录），需重新编码。\n"
                "若希望保留独立字幕轨道（流复制），请在「封装/合并」页面添加外部字幕。")
        self.subtitle_entry = ttk.Entry(line1, textvariable=self.subtitle_path,
                                        width=30, state="disabled")
        self.subtitle_entry.pack(side=tk.LEFT, padx=5)
        self.browse_subtitle_btn = ttk.Button(line1, text="浏览字幕",
                                              command=self.browse_subtitle, width=9)
        self.browse_subtitle_btn.pack(side=tk.LEFT)
        if not self.subtitle_enabled.get():
            self.subtitle_entry.config(state="disabled")
            self.browse_subtitle_btn.config(state="disabled")
    
        scale_frame = ttk.Frame(left_frame)
        scale_frame.pack(fill=tk.X, pady=2)
        self.scale_enabled = tk.BooleanVar(value=False)
        self.scale_width = tk.StringVar(value="")
        self.scale_height = tk.StringVar(value="")
        self.scale_method = tk.StringVar(value="width")
        scale_check = ttk.Checkbutton(scale_frame, text="启用缩放", variable=self.scale_enabled)
        scale_check.pack(side=tk.LEFT)
        ToolTip(scale_check,
                "启用视频缩放功能。\n"
                "• 宽度(高度自动)：指定宽度，高度按比例自动计算。\n"
                "• 高度(宽度自动)：指定高度，宽度按比例自动计算。\n"
                "• 精确宽×高：自定义宽度和高度，可能拉伸画面。\n"
                "提示：缩放会重新编码视频，编码器为 copy 时无效。",
                wraplength=400)
        ttk.Radiobutton(scale_frame, text="宽度(高度自动)", variable=self.scale_method, value="width").pack(side=tk.LEFT, padx=(10,0))
        ttk.Entry(scale_frame, textvariable=self.scale_width, width=6).pack(side=tk.LEFT)

        ttk.Radiobutton(scale_frame, text="高度(宽度自动)", variable=self.scale_method, value="height").pack(side=tk.LEFT, padx=10)
        ttk.Entry(scale_frame, textvariable=self.scale_height, width=6).pack(side=tk.LEFT)

        ttk.Radiobutton(scale_frame, text="精确宽×高", variable=self.scale_method, value="exact").pack(side=tk.LEFT, padx=10)
        ttk.Entry(scale_frame, textvariable=self.scale_width, width=6).pack(side=tk.LEFT)
        ttk.Label(scale_frame, text="×").pack(side=tk.LEFT)
        ttk.Entry(scale_frame, textvariable=self.scale_height, width=6).pack(side=tk.LEFT)
        ttk.Button(scale_frame, text="⇄", command=self._swap_width_height, width=3).pack(side=tk.LEFT, padx=2)
    
        crop_frame = ttk.Frame(left_frame)
        crop_frame.pack(fill=tk.X, pady=2)
        self.crop_enabled = tk.BooleanVar(value=False)
        self.crop_left = tk.StringVar(value="0")
        self.crop_top = tk.StringVar(value="0")
        self.crop_width = tk.StringVar(value="iw/2")
        self.crop_height = tk.StringVar(value="ih")
        crop_check = ttk.Checkbutton(crop_frame, text="启用裁剪", variable=self.crop_enabled)
        crop_check.pack(side=tk.LEFT)
        ToolTip(crop_check, 
                "裁剪滤镜 (crop) 使用说明：\n"
                "格式：crop=宽:高:左:上\n"
                "支持表达式：iw(原宽), ih(原高), 算术运算(如 iw/2, ih-100)\n"
                "\n"
                "注意事项：\n"
                "• 宽和高 必须为正整数或运算结果为正数！\n"
                "• 宽/高 不能为 0 或负数，也不支持 -2 自动计算（与 scale 不同）\n"
                "• 左/上 可以为 0 或正整数，超出视频边缘会报错\n"
                "• 例如裁剪右半部分：宽=iw/2, 左=iw/2, 高=ih, 上=0\n"
                "• 例如裁剪上半部分：宽=iw, 高=ih/2, 左=0, 上=0\n"
                "• 如果宽高为奇数，FFmpeg 会自动向下取整，一般不影响播放",
                wraplength=400)
        ttk.Label(crop_frame, text="宽:").pack(side=tk.LEFT)
        ttk.Entry(crop_frame, textvariable=self.crop_width, width=6).pack(side=tk.LEFT)
        ttk.Label(crop_frame, text="高:").pack(side=tk.LEFT)
        ttk.Entry(crop_frame, textvariable=self.crop_height, width=6).pack(side=tk.LEFT)
        ttk.Label(crop_frame, text="左:").pack(side=tk.LEFT, padx=(10,0))
        ttk.Entry(crop_frame, textvariable=self.crop_left, width=6).pack(side=tk.LEFT)
        ttk.Label(crop_frame, text="上:").pack(side=tk.LEFT)
        ttk.Entry(crop_frame, textvariable=self.crop_top, width=6).pack(side=tk.LEFT)

        # 自动检测黑边按钮
        auto_crop_btn = ttk.Button(crop_frame, text="自动去黑边",
                                   command=self.auto_detect_crop, width=9)
        auto_crop_btn.pack(side=tk.LEFT, padx=(10,0))
        ToolTip(auto_crop_btn,
                "自动分析当前输入文件，获取裁剪参数（去除四周黑边）。\n"
                "参数说明：\n"
                "• 分析帧数：检测多少帧画面（默认10帧）。帧数越多越准确，但耗时稍长；\n"
                "• round：裁剪宽/高对齐数值（默认2，保证偶数）。设为16可满足旧编码器兼容性；\n"
                "• 检测从第1帧开始（skip=0）。若第一帧为黑屏，请手动增加分析帧数或跳过片头。\n"
                "可根据截取起始时间或者可视化窗口内自定义时间获取需要片段的黑边参数。\n"
                "检测仅需约0.5秒，可快速尝试调整参数。",
                wraplength=600)

        # 增加分析帧数和round设置
        ttk.Label(crop_frame, text="帧:").pack(side=tk.LEFT, padx=(5,0))
        self.crop_detect_frames = tk.StringVar(value="10")
        frames_spin = ttk.Spinbox(crop_frame, from_=1, to=100, width=3, textvariable=self.crop_detect_frames)
        frames_spin.pack(side=tk.LEFT, padx=2)
        ttk.Label(crop_frame, text="Rd:").pack(side=tk.LEFT, padx=(5,0))
        self.crop_detect_round = tk.StringVar(value="2")
        round_spin = ttk.Spinbox(crop_frame, from_=1, to=16, width=3, textvariable=self.crop_detect_round)
        round_spin.pack(side=tk.LEFT, padx=2)

        crop_edit_btn = ttk.Button(crop_frame, text="可视化",
                                   command=self.open_crop_editor, width=7)
        crop_edit_btn.pack(side=tk.LEFT, padx=(10,0))
        ToolTip(crop_edit_btn,
                "打开可视化裁剪窗口：\n"
                "• 显示视频首帧画面，可用鼠标拖拽绘制矩形选区\n"
                "• 选区参数会回填到「启用裁剪」的各项输入框中\n"
                "• 仍保留「自动检测黑边」功能，可辅助定位",
                wraplength=500)

        rot_frame = ttk.Frame(left_frame)
        rot_frame.pack(fill=tk.X, pady=2)
        rot_label = ttk.Label(rot_frame, text="旋转:")
        rot_label.pack(side=tk.LEFT)
        ToolTip(rot_label,
                "旋转画面方向（90°/180°/270°）。\n"
                "上下/左右翻转可镜像画面。\n"
                "提示：旋转和翻转需重新编码视频，编码器为 copy 时无效。"
                "    当前旋转是实体旋转，不是元数据旋转。",
                wraplength=500)
        self.rotate = tk.StringVar(value="none")
        for text, val in [("无", "none"), ("90°顺时针", "90"), ("180°", "180"), ("90°逆时针", "270")]:
            ttk.Radiobutton(rot_frame, text=text, variable=self.rotate, value=val).pack(side=tk.LEFT, padx=2)



        self.vflip = tk.BooleanVar(value=False)
        self.hflip = tk.BooleanVar(value=False)
        ttk.Checkbutton(rot_frame, text="上下翻转", variable=self.vflip).pack(side=tk.LEFT, padx=(40,0))
        ttk.Checkbutton(rot_frame, text="左右翻转", variable=self.hflip).pack(side=tk.LEFT, padx=5)


        self.enhance_btn = ttk.Button(rot_frame, text="高级增强", 
                                      command=self.open_enhance_window, width=10)
        self.enhance_btn.pack(side=tk.LEFT, padx=(20,0))



        hybrid_frame = ttk.Frame(left_frame)
        hybrid_frame.pack(fill=tk.X, pady=2)
        self.speed_enabled = tk.BooleanVar(value=False)
        self.speed_factor = tk.StringVar(value="1.0")
        speed_check = ttk.Checkbutton(hybrid_frame, text="启用变速", variable=self.speed_enabled)
        speed_check.pack(side=tk.LEFT)
        ToolTip(speed_check, 
            "启用变速后，可自定义速度倍数（支持任意正数，例如 0.5x 慢放、2.0x 快放）。\n"
            "注意：过高（>10）或过低（<0.1）的倍数会串联多个 atempo 音频滤镜计算，可能加重解码负担。\n"
            "推荐范围：0.1 ~ 10 倍，一般使用 0.25 ~ 4.0 已足够。")
        ttk.Entry(hybrid_frame, textvariable=self.speed_factor, width=6).pack(side=tk.LEFT, padx=5)


        self.reverse_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(hybrid_frame, text="启用倒放", variable=self.reverse_enabled).pack(side=tk.LEFT, padx=(10, 0))


        deint_label = ttk.Label(hybrid_frame, text="反交错:")
        deint_label.pack(side=tk.LEFT, padx=(10,0))
        ToolTip(deint_label, 
                "反交错滤镜选项：\n"
                "yadif - 常用反交错，适合大多数隔行扫描内容\n"
                "bwdif - 运动自适应，比yadif更锐利\n"
                "kerndeint - 基于内核，适合电影模式\n"
                "pp=lb - 行混合，柔和去拉丝\n"
                "fieldorder - 仅调整场序，不反交错",
                wraplength=400)
        self.deinterlace_filter = tk.StringVar(value="none")
        deinterlace_combo = ttk.Combobox(hybrid_frame, textvariable=self.deinterlace_filter,
                                         values=["none", "bwdif", "yadif", "kerndeint", "pp=lb", "fieldorder"],
                                         state="readonly", width=10)
        deinterlace_combo.pack(side=tk.LEFT, padx=2)
    
        self.pix_fmt_enabled = tk.BooleanVar(value=self.app.pix_fmt_enabled_default.get())
        self.pix_fmt = tk.StringVar(value="yuv420p")
        pix_label = ttk.Label(hybrid_frame, text="像素格式:")
        pix_label.pack(side=tk.LEFT, padx=(20,0))
        ToolTip(pix_label,
            "像素格式决定视频的色彩采样和位深。\n\n"
            "• yuv420p：最通用，兼容所有设备和播放器，文件小。\n"
            "• yuv422p：色度采样更高，适合专业剪辑，兼容性稍差。\n"
            "• yuv444p：无色彩压缩，画质最高，兼容性最差，文件大。\n"
            "• yuv420p10le：10-bit 色深，HDR 视频常用，需 HEVC/AV1 编码。\n"
            "• p010le：10-bit YUV 4:2:0，硬件解码友好（NVIDIA/Intel）。\n"
            "• nv12：4:2:0 平面交错，硬件编码常用格式。\n\n"
            "一般视频推荐保持默认 yuv420p 以保证最佳兼容性。",
            wraplength=400)
        
        ttk.Checkbutton(hybrid_frame, text="指定", variable=self.pix_fmt_enabled).pack(side=tk.LEFT)
        self.pix_fmt_combo = ttk.Combobox(hybrid_frame, textvariable=self.pix_fmt, 
                                          values=self.PIX_FMTS, width=12, state="normal")
        self.pix_fmt_combo.pack(side=tk.LEFT, padx=5)
        
        self.pix_fmt_enabled.trace_add("write", self._on_pix_fmt_changed)

    def _on_pix_fmt_changed(self, *args):
        if getattr(self, '_loading_settings', False):
            return
        self.app.pix_fmt_enabled_default.set(self.pix_fmt_enabled.get())
        self.app.save_player_settings()


    def _swap_width_height(self):
        """交换宽度和高度数值"""
        w = self.scale_width.get().strip()
        h = self.scale_height.get().strip()
        self.scale_width.set(h)
        self.scale_height.set(w)

    def extract_video_frame_scaled(self, input_file, output_png_path, frame_sec=0.0,
                                    target_width=None, target_height=None):
        """
        使用 FFmpeg 提取视频帧，并缩放到目标尺寸，输出为 PNG。
        若 target_width 或 target_height 为 None，则保持原始比例（自动计算）。
        返回 (实际宽度, 实际高度) 或 (None, None) 若失败。
        """
        if not self.app.ffmpeg_cmd:
            return None, None
    
        # 构建 scale 滤镜
        scale_filter = ""
        if target_width is not None and target_height is not None:
            scale_filter = f"scale={target_width}:{target_height}"
        elif target_width is not None:
            scale_filter = f"scale={target_width}:-2"
        elif target_height is not None:
            scale_filter = f"scale=-2:{target_height}"
        # 若两者都为 None，则不加 scale（输出原始尺寸）
    
        cmd = [
            self.app.ffmpeg_cmd,
            "-ss", str(frame_sec),
            "-i", input_file,
            "-vframes", "1",
            "-f", "image2pipe",
            "-vcodec", "png",
            "-y",
            output_png_path
        ]
        # 如果 scale_filter 非空，插入 -vf 参数（放在 -i 之后，-vframes 之前）
        if scale_filter:
            # 找到 -vframes 的位置并插入
            vframes_idx = cmd.index("-vframes")
            cmd.insert(vframes_idx, "-vf")
            cmd.insert(vframes_idx + 1, scale_filter)
    
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.run(cmd, check=True, capture_output=True, creationflags=flags, timeout=10)

#             if os.path.exists(output_png_path):
#                 size_kb = os.path.getsize(output_png_path) / 1024
#                 self.app._append_info_ui(f"[裁剪] PNG临时文件大小: {size_kb:.1f} KB")
            # 读取 PNG 获取尺寸（使用内置函数解析头）
            w, h = self._get_png_dimensions(output_png_path)
            return w, h
        except Exception as e:
            self.app._append_info_ui(f"[裁剪辅助] 提取缩放帧失败: {e}")
            return None, None
    
    
    def _get_png_dimensions(self, png_path):
        """读取 PNG 文件头获取宽高（无依赖）"""
        import struct
        try:
            with open(png_path, 'rb') as f:
                # 检查 PNG 签名
                if f.read(8) != b'\x89PNG\r\n\x1a\n':
                    return None, None
                # 寻找 IHDR 块
                while True:
                    length_data = f.read(4)
                    if len(length_data) < 4:
                        break
                    length = struct.unpack('>I', length_data)[0]
                    chunk_type = f.read(4)
                    if chunk_type == b'IHDR':
                        data = f.read(length)
                        if len(data) >= 8:
                            width, height = struct.unpack('>II', data[:8])
                            return width, height
                        else:
                            return None, None
                    else:
                        # 跳过数据 + CRC
                        f.seek(length + 4, os.SEEK_CUR)
                return None, None
        except Exception:
            return None, None



    def set_track(self, track):
        """设置当前编辑的轨道，用于获取截取设置"""
        self.current_track = track
        if track:
            self.current_file = track.file_path

    def set_override_settings(self, settings):
        """设置外部传入的设置字典，用于读取截取起始时间"""
        self.override_settings = settings

    def set_get_trim_settings_callback(self, callback):
        """设置一个回调函数，用于获取当前的截取设置（由编辑窗口提供）"""
        self.get_trim_settings_callback = callback

    def get_enhance_settings(self):
     #   print(f"[get_enhance_settings] 返回 = {self.enhance_settings}")
        return self.enhance_settings.copy()
    
    def set_enhance_settings(self, settings):
        self.enhance_settings.update(settings)
        # 如果当前有打开增强窗口，可以更新控件，但为了简单，仅更新存储


    def open_enhance_window(self):
        win = tk.Toplevel(self)
        win.title("高级增强滤镜")
        win.transient(self)
        win.grab_set()
        center_window(win, 650, 430)  # 宽度稍宽，高度降低
    
        main = ttk.Frame(win, padding="10")
        main.pack(fill=tk.BOTH, expand=True)
    
        # ---- 左右分栏 ----
        paned = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
    
        # ---- 左栏：画质修复 ----
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
    
        # 降噪
        denoise_frame = ttk.LabelFrame(left_frame, text="降噪 (hqdn3d)", padding="5")
        denoise_frame.pack(fill=tk.X, pady=5)
        self.denoise_enabled = tk.BooleanVar(value=self.enhance_settings.get("denoise_enabled", False))
        ttk.Checkbutton(denoise_frame, text="启用降噪", variable=self.denoise_enabled).pack(anchor=tk.W)
        row1 = ttk.Frame(denoise_frame); row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="空间强度 (0~10):").pack(side=tk.LEFT)
        self.denoise_spatial = tk.DoubleVar(value=self.enhance_settings.get("denoise_spatial", 4.0))
        ttk.Scale(row1, from_=0, to=10, variable=self.denoise_spatial, orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT, padx=5)
        ttk.Label(row1, textvariable=self.denoise_spatial, width=4).pack(side=tk.LEFT)
        row2 = ttk.Frame(denoise_frame); row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="时间强度 (0~10):").pack(side=tk.LEFT)
        self.denoise_temporal = tk.DoubleVar(value=self.enhance_settings.get("denoise_temporal", 3.0))
        ttk.Scale(row2, from_=0, to=10, variable=self.denoise_temporal, orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT, padx=5)
        ttk.Label(row2, textvariable=self.denoise_temporal, width=4).pack(side=tk.LEFT)
    
        # 锐化
        sharpen_frame = ttk.LabelFrame(left_frame, text="锐化 (unsharp)", padding="5")
        sharpen_frame.pack(fill=tk.X, pady=5)
        self.sharpen_enabled = tk.BooleanVar(value=self.enhance_settings.get("sharpen_enabled", False))
        ttk.Checkbutton(sharpen_frame, text="启用锐化", variable=self.sharpen_enabled).pack(anchor=tk.W)
        row3 = ttk.Frame(sharpen_frame); row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="锐化强度 (0~5):").pack(side=tk.LEFT)
        self.sharpen_strength = tk.DoubleVar(value=self.enhance_settings.get("sharpen_strength", 1.0))
        ttk.Scale(row3, from_=0, to=5, variable=self.sharpen_strength, orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT, padx=5)
        ttk.Label(row3, textvariable=self.sharpen_strength, width=4).pack(side=tk.LEFT)
    
        # IVTC（反胶卷过带）
        ivtc_frame = ttk.LabelFrame(left_frame, text="反胶卷过带 (IVTC)", padding="5")
        ivtc_frame.pack(fill=tk.X, pady=5)
        self.ivtc_enabled = tk.BooleanVar(value=self.enhance_settings.get("ivtc_enabled", False))
        chk_ivtc = ttk.Checkbutton(ivtc_frame, text="启用 IVTC (适用于 60i -> 24p)", variable=self.ivtc_enabled)
        chk_ivtc.pack(anchor=tk.W)

    
        # 去块滤波
        deblock_frame = ttk.LabelFrame(left_frame, text="去块滤波 (deblock)", padding="5")
        deblock_frame.pack(fill=tk.X, pady=5)
        self.deblock_enabled = tk.BooleanVar(value=self.enhance_settings.get("deblock_enabled", False))
        ttk.Checkbutton(deblock_frame, text="启用去块", variable=self.deblock_enabled).pack(anchor=tk.W)
        row4 = ttk.Frame(deblock_frame); row4.pack(fill=tk.X, pady=2)
        ttk.Label(row4, text="强度 (1~8):").pack(side=tk.LEFT)
        self.deblock_strength = tk.IntVar(value=self.enhance_settings.get("deblock_strength", 4))
        ttk.Scale(row4, from_=1, to=8, variable=self.deblock_strength, orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT, padx=5)
        ttk.Label(row4, textvariable=self.deblock_strength, width=4).pack(side=tk.LEFT)
    
        # ---- 右栏：色彩调整 ----
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)
    
        # 色彩空间转换
        colorspace_frame = ttk.LabelFrame(right_frame, text="色彩空间转换", padding="5")
        colorspace_frame.pack(fill=tk.X, pady=5)
        self.colorspace_enabled = tk.BooleanVar(value=self.enhance_settings.get("colorspace_enabled", False))
        ttk.Checkbutton(colorspace_frame, text="启用转换", variable=self.colorspace_enabled).pack(anchor=tk.W)
        row5 = ttk.Frame(colorspace_frame); row5.pack(fill=tk.X, pady=2)
        ttk.Label(row5, text="目标色彩矩阵:").pack(side=tk.LEFT)
        self.colorspace_matrix = tk.StringVar(value=self.enhance_settings.get("colorspace_matrix", "bt709:bt2020"))
        ttk.Combobox(row5, textvariable=self.colorspace_matrix,
                     values=["bt709:bt2020", "bt2020:bt709", "bt601:bt709", "bt709:bt601"],
                     state="readonly", width=15).pack(side=tk.LEFT, padx=5)
    
        # 颜色校正（eq + hue）
        color_frame = ttk.LabelFrame(right_frame, text="颜色校正 (eq / hue)", padding="5")
        color_frame.pack(fill=tk.X, pady=5)
    
        eq_brightness_var = tk.DoubleVar(value=self.enhance_settings.get("eq_brightness", 0.0))
        eq_contrast_var = tk.DoubleVar(value=self.enhance_settings.get("eq_contrast", 1.0))
        eq_saturation_var = tk.DoubleVar(value=self.enhance_settings.get("eq_saturation", 1.0))
        eq_gamma_var = tk.DoubleVar(value=self.enhance_settings.get("eq_gamma", 1.0))
        hue_angle_var = tk.DoubleVar(value=self.enhance_settings.get("hue_angle", 0.0))
        hue_saturation_var = tk.DoubleVar(value=self.enhance_settings.get("hue_saturation", 0.0))
    
        def make_slider_row(parent, label, var, from_, to, resolution, fmt="{:.2f}"):
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=label, width=10).pack(side=tk.LEFT)
            slider = ttk.Scale(row, from_=from_, to=to, variable=var,
                               orient=tk.HORIZONTAL, length=150)
            slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            val_label = ttk.Label(row, text=fmt.format(var.get()), width=6)
            val_label.pack(side=tk.LEFT)
            def update_label(*args):
                val_label.config(text=fmt.format(var.get()))
            var.trace_add("write", update_label)
            return row
    
        make_slider_row(color_frame, "亮度", eq_brightness_var, -1.0, 1.0, 0.01)
        make_slider_row(color_frame, "对比度", eq_contrast_var, -2.0, 2.0, 0.01)
        make_slider_row(color_frame, "饱和度", eq_saturation_var, 0.0, 3.0, 0.01)
        make_slider_row(color_frame, "伽马", eq_gamma_var, 0.1, 10.0, 0.01)
        make_slider_row(color_frame, "色相", hue_angle_var, -180, 180, 1, fmt="{:.0f}")
        make_slider_row(color_frame, "色饱和度", hue_saturation_var, -1.0, 1.0, 0.01)
    
        reset_btn = ttk.Button(color_frame, text="重置默认值",
                               command=lambda: [eq_brightness_var.set(0.0), eq_contrast_var.set(1.0),
                                                eq_saturation_var.set(1.0), eq_gamma_var.set(1.0),
                                                hue_angle_var.set(0.0), hue_saturation_var.set(0.0)])
        reset_btn.pack(pady=5)
    
        # ---- 底部按钮 ----
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(5,10))
    
        def save_and_close():
            self.enhance_settings.update({
                "denoise_enabled": self.denoise_enabled.get(),
                "denoise_spatial": self.denoise_spatial.get(),
                "denoise_temporal": self.denoise_temporal.get(),
                "sharpen_enabled": self.sharpen_enabled.get(),
                "sharpen_strength": self.sharpen_strength.get(),
                "ivtc_enabled": self.ivtc_enabled.get(),
                "deblock_enabled": self.deblock_enabled.get(),
                "deblock_strength": self.deblock_strength.get(),
                "colorspace_enabled": self.colorspace_enabled.get(),
                "colorspace_matrix": self.colorspace_matrix.get(),
                "eq_brightness": eq_brightness_var.get(),
                "eq_contrast": eq_contrast_var.get(),
                "eq_saturation": eq_saturation_var.get(),
                "eq_gamma": eq_gamma_var.get(),
                "hue_angle": hue_angle_var.get(),
                "hue_saturation": hue_saturation_var.get(),
            })
            if self.app:
                self.app.update_command_preview()
            if hasattr(self, '_preview_callback') and self._preview_callback:
                self._preview_callback()
            win.destroy()
    
        ttk.Button(btn_frame, text="保存并关闭", command=save_and_close).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=win.destroy).pack(side=tk.LEFT, padx=5)




    def open_crop_editor(self):
        """可视化裁剪窗口 - 拖拽绘制矩形，支持时间跳转重新取帧，初始时间自动从主界面或者当前编辑窗口的截取起始时间获取"""
        input_file = getattr(self, 'current_file', None)
        if not input_file or not os.path.exists(input_file):
            input_file = self.app.input_file.get().strip()
        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("错误", "请先选择一个有效的输入文件")
            return
    
        ffmpeg = self.app.ffmpeg_cmd
        if not ffmpeg:
            messagebox.showerror("错误", "未找到 ffmpeg，无法提取视频帧")
            return
    
        # ----- 从当前轨道或主界面获取截取起始时间 未启用则为0秒 -----
        initial_time = 0.0
        if hasattr(self, 'get_trim_settings_callback') and self.get_trim_settings_callback is not None:
            trim_settings = self.get_trim_settings_callback()
            if trim_settings.get("trim_enabled", False):
                start_str = trim_settings.get("trim_start", "").strip()
                if start_str:
                    sec = time_to_seconds(start_str)
                    if sec is not None and sec >= 0:
                        initial_time = sec
                        self.app._append_info_ui(f"[裁剪] 使用当前编辑窗口的截取起始时间: {sec:.2f}s")
        elif self.override_settings is not None:
            if self.override_settings.get("trim_enabled", False):
                start_str = self.override_settings.get("trim_start", "").strip()
                if start_str:
                    sec = time_to_seconds(start_str)
                    if sec is not None and sec >= 0:
                        initial_time = sec
                        self.app._append_info_ui(f"[裁剪] 使用外部设置的截取起始时间: {sec:.2f}s")
        elif self.current_track is not None:
            enc = self.current_track.enc_settings
            if enc.get("trim_enabled", False):
                start_str = enc.get("trim_start", "").strip()
                if start_str:
                    sec = time_to_seconds(start_str)
                    if sec is not None and sec >= 0:
                        initial_time = sec
                        self.app._append_info_ui(f"[裁剪] 使用轨道截取起始时间: {sec:.2f}s")
        else:
            if self.app.trim_frame.trim_enabled.get():
                start_str = self.app.trim_frame.trim_start.get().strip()
                if start_str:
                    sec = time_to_seconds(start_str)
                    if sec is not None and sec >= 0:
                        initial_time = sec
                        self.app._append_info_ui(f"[裁剪] 使用主界面截取起始时间: {sec:.2f}s")
    
        current_time = initial_time
    
        # ----- 获取原始视频尺寸（用于计算显示比例） -----
        orig_w, orig_h = self.app._get_video_dimensions_cached(input_file)
        if orig_w is None or orig_h is None:
            # 降级：使用固定默认值
            orig_w, orig_h = 1920, 1080
            self.app._append_info_ui("[裁剪] 无法获取原始尺寸，使用默认值")
    
        # ----- 计算显示尺寸 -----
        screen_w = self.app.root.winfo_screenwidth()
        screen_h = self.app.root.winfo_screenheight()
        max_w = int(screen_w * 0.9)
        max_h = int(screen_h * 0.9)
        RIGHT_PANEL_WIDTH = 280
        EXTRA_HEIGHT = 10
        PADDING = 10           # 图片外边距
        WINDOW_MARGIN = 20     # 右边菜单控件和图片区的间隔
        avail_w = max_w - RIGHT_PANEL_WIDTH - WINDOW_MARGIN - PADDING * 2
        avail_h = max_h - EXTRA_HEIGHT - PADDING * 2
    
        scale = min(1.0, avail_w / orig_w, avail_h / orig_h)
        disp_w = int(orig_w * scale)
        disp_h = int(orig_h * scale)
        if disp_w < 1:
            disp_w = 1
        if disp_h < 1:
            disp_h = 1
        self.app._append_info_ui(f"[裁剪] 原始尺寸: {orig_w}x{orig_h}, 显示尺寸: {disp_w}x{disp_h}")
    
        # ----- 坐标缩放因子（用于坐标系转换） -----
        scale_x = orig_w / disp_w
        scale_y = orig_h / disp_h

        # ----- 初始化闭包变量（必须在嵌套函数之前定义） -----
        scaled_temp_path = None   # 当前显示的临时文件路径
        img = None                # Tkinter 图像对象
        points = []               # 矩形坐标（原始坐标）
        rect_id = None            # 矩形画布 ID
        drag_rect_id = None       # 拖拽辅助矩形 ID
        drag_start_display = None # 拖拽起始点（显示坐标）
        img_w, img_h = disp_w, disp_h   # 图像实际尺寸（通常与 disp 一致）
    
        # ----- 临时文件管理 -----
        temp_file_info = {"path": None}
    
        def cleanup_temp_file():
            if temp_file_info["path"] and os.path.exists(temp_file_info["path"]):
                try:
                    os.unlink(temp_file_info["path"])
                except Exception:
                    pass
                temp_file_info["path"] = None
    
        # ----- 窗口布局 -----
        canvas_w = disp_w + PADDING * 2
        canvas_h = disp_h + PADDING * 2
        total_w = canvas_w + RIGHT_PANEL_WIDTH + WINDOW_MARGIN
        total_h = canvas_h + EXTRA_HEIGHT
        total_w = min(total_w, max_w)
        total_h = min(total_h, max_h)
        if total_w < 400:
            total_w = 400
    
        with self.app.SafeToplevel(self.app.root) as win:
            win.title(f"可视化裁剪 - 拖拽绘制矩形 (显示 {disp_w}x{disp_h}, 原始 {orig_w}x{orig_h})")
            win.transient(self.app.root)
            center_window(win, total_w, total_h, offset_y=15)
    
            # 窗口关闭时清理临时文件
            def on_window_close():
                cleanup_temp_file()
                win.destroy()
            win.protocol("WM_DELETE_WINDOW", on_window_close)
    
            main_pane = ttk.Frame(win)
            main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
            right_frame = ttk.Frame(main_pane, width=RIGHT_PANEL_WIDTH)
            right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
            right_frame.pack_propagate(False)
    
            canvas_frame = ttk.Frame(main_pane)
            canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
            canvas = tk.Canvas(canvas_frame, bg='gray', width=canvas_w, height=canvas_h,
                               highlightthickness=0)
            canvas.pack(fill=tk.BOTH, expand=True)
            canvas.config(scrollregion=(0, 0, canvas_w, canvas_h))
    
            # ----- 坐标转换函数 -----
            def canvas_to_display(cx, cy):
                x = canvas.canvasx(cx) - PADDING
                y = canvas.canvasy(cy) - PADDING
                return max(0, min(x, disp_w)), max(0, min(y, disp_h))
    
            def display_to_original(dx, dy):
                return int(dx * scale_x), int(dy * scale_y)
    
            def original_to_display(ox, oy):
                return ox / scale_x, oy / scale_y
    
            # ----- 信息显示 -----
            info_var = tk.StringVar(value="👉 在图像上按住左键拖拽（可从边缘外开始）以绘制裁剪矩形")
            info_label = tk.Label(right_frame, textvariable=info_var, wraplength=RIGHT_PANEL_WIDTH - 20,
                                  justify=tk.LEFT, bg="#FFFFCC", relief=tk.SUNKEN, padx=5, pady=5)
            info_label.pack(pady=5, fill=tk.X)
    
            def update_info():
                if len(points) == 2:
                    x1, y1 = points[0]
                    x2, y2 = points[1]
                    x = min(x1, x2)
                    y = min(y1, y2)
                    w = abs(x2 - x1)
                    h = abs(y2 - y1)
                    info_var.set(f"✅ 矩形已确定\n左上: ({x}, {y})  宽: {w}  高: {h}\n"
                                 f"裁剪参数: crop={w}:{h}:{x}:{y}\n"
                                 "👉 可继续拖拽新矩形覆盖")
                else:
                    info_var.set("👉 在图像上按住左键拖拽（可从边缘外开始）以绘制裁剪矩形")
    
            # ----- 拖拽事件 -----
            def on_drag_start(event):
                nonlocal drag_start_display, drag_rect_id
                dx, dy = canvas_to_display(event.x, event.y)
                drag_start_display = (dx, dy)
                if drag_rect_id:
                    canvas.delete(drag_rect_id)
                    drag_rect_id = None
                if rect_id:
                    canvas.delete(rect_id)
    
            def on_drag_motion(event):
                nonlocal drag_start_display, drag_rect_id
                if drag_start_display is None:
                    return
                cur_dx, cur_dy = canvas_to_display(event.x, event.y)
                if drag_rect_id:
                    canvas.delete(drag_rect_id)
                sx, sy = drag_start_display
                drag_rect_id = canvas.create_rectangle(
                    sx + PADDING, sy + PADDING,
                    cur_dx + PADDING, cur_dy + PADDING,
                    outline='yellow', width=2, dash=(4, 2)
                )
    
            def on_drag_end(event):
                nonlocal drag_start_display, drag_rect_id, points, rect_id
                if drag_start_display is None:
                    return
                ex, ey = canvas_to_display(event.x, event.y)
                sx, sy = drag_start_display
                ox1, oy1 = display_to_original(sx, sy)
                ox2, oy2 = display_to_original(ex, ey)
                if abs(ox2 - ox1) > 0 and abs(oy2 - oy1) > 0:
                    points = [(ox1, oy1), (ox2, oy2)]
                    if rect_id:
                        canvas.delete(rect_id)
                    dx1, dy1 = original_to_display(ox1, oy1)
                    dx2, dy2 = original_to_display(ox2, oy2)
                    rect_id = canvas.create_rectangle(
                        dx1 + PADDING, dy1 + PADDING,
                        dx2 + PADDING, dy2 + PADDING,
                        outline='red', width=2
                    )
                    update_info()
                else:
                    if rect_id:
                        canvas.delete(rect_id)
                        rect_id = None
                    points = []
                    update_info()
                if drag_rect_id:
                    canvas.delete(drag_rect_id)
                    drag_rect_id = None
                drag_start_display = None
    
            canvas.bind("<ButtonPress-1>", on_drag_start)
            canvas.bind("<B1-Motion>", on_drag_motion)
            canvas.bind("<ButtonRelease-1>", on_drag_end)
    
            # ----- 清除矩形 -----
            def clear_rect():
                nonlocal points, rect_id, drag_start_display, drag_rect_id
                points = []
                if rect_id:
                    canvas.delete(rect_id)
                    rect_id = None
                if drag_rect_id:
                    canvas.delete(drag_rect_id)
                    drag_rect_id = None
                drag_start_display = None
                update_info()
    
            # ----- 应用裁剪 -----
            def apply_crop():
                if len(points) != 2:
                    messagebox.showwarning("提示", "请先拖拽绘制一个裁剪矩形")
                    return
                x1, y1 = points[0]
                x2, y2 = points[1]
                x = min(x1, x2)
                y = min(y1, y2)
                w = abs(x2 - x1)
                h = abs(y2 - y1)
                if w <= 0 or h <= 0:
                    messagebox.showerror("错误", "矩形尺寸无效")
                    return
                # 保证偶数
                if w % 2:
                    if x + w + 1 <= orig_w:
                        w += 1
                    else:
                        w -= 1
                if h % 2:
                    if y + h + 1 <= orig_h:
                        h += 1
                    else:
                        h -= 1
                if x + w > orig_w:
                    w = orig_w - x
                if y + h > orig_h:
                    h = orig_h - y
                if w <= 0 or h <= 0:
                    messagebox.showerror("错误", "修正后矩形无效")
                    return
                self.crop_enabled.set(True)
                self.crop_width.set(str(int(w)))
                self.crop_height.set(str(int(h)))
                self.crop_left.set(str(int(x)))
                self.crop_top.set(str(int(y)))
                self.app._append_info_ui(f"[裁剪] 应用 crop={int(w)}:{int(h)}:{int(x)}:{int(y)}")
                win.destroy()
    
            # ----- 自动检测黑边 -----
            def auto_detect():
                # ---- 获取当前时间输入框的值 ----
                time_str = time_var.get().strip()
                if time_str:
                    sec = parse_time_str(time_str)
                    if sec is not None:
                        self._visual_crop_start_time = sec
                    else:
                        self._visual_crop_start_time = 0.0
                else:
                    self._visual_crop_start_time = 0.0
    
                self.crop_detect_frames.set(frames_var.get())
                self.crop_detect_round.set(round_var.get())
                old = self.current_file
                self.current_file = input_file
                try:
                    self.auto_detect_crop()
                finally:
                    self.current_file = old
                if self.crop_enabled.get():
                    try:
                        w = int(self.crop_width.get())
                        h = int(self.crop_height.get())
                        x = int(self.crop_left.get())
                        y = int(self.crop_top.get())
                        nonlocal points, rect_id
                        if rect_id:
                            canvas.delete(rect_id)
                        points = [(x, y), (x + w, y + h)]
                        dx1, dy1 = original_to_display(x, y)
                        dx2, dy2 = original_to_display(x + w, y + h)
                        rect_id = canvas.create_rectangle(
                            dx1 + PADDING, dy1 + PADDING,
                            dx2 + PADDING, dy2 + PADDING,
                            outline='red', width=2
                        )
                        update_info()
                    except:
                        pass
    
            # ----- 时间跳转和重新获取画面 -----
            time_var = tk.StringVar(value=str(initial_time))
            time_entry = ttk.Entry(right_frame, textvariable=time_var, width=12)
            time_entry.pack(pady=(10, 2), fill=tk.X)
    
            def parse_time_str(s):
                return time_to_seconds(s)
    
            def on_refresh_click():
                nonlocal current_time, img, scaled_temp_path, img_w, img_h
                nonlocal points, rect_id, drag_start_display, drag_rect_id
            
                time_str = time_var.get().strip()
                if not time_str:
                    messagebox.showwarning("提示", "请输入时间")
                    return
                sec = parse_time_str(time_str)
                if sec is None:
                    messagebox.showerror("错误", f"无效的时间格式: {time_str}\n支持格式: 秒数 (如 10.5) 或 HH:MM:SS[.mmm]")
                    return
                total_duration = self.app._get_media_duration(input_file)
                if total_duration is not None and sec > total_duration:
                    messagebox.showwarning("警告", f"输入时间 {sec:.2f}s 超过视频总时长 {total_duration:.2f}s，将跳转到末尾")
                    sec = total_duration
                current_time = sec
            
                refresh_btn.config(state=tk.DISABLED, text="提取中...")
                info_var.set("⏳ 正在提取画面，请稍候...")
                win.update_idletasks()
            
                # --- 取消旧线程 ---
                if self._crop_extract_thread and self._crop_extract_thread.is_alive():
                    self._crop_cancel_event.set()
                    self._crop_extract_thread.join(timeout=0.5)
                self._crop_cancel_event.clear()
            
                # 定义提取线程
                def extract_thread():
                    fd_new, new_png = tempfile.mkstemp(suffix='.png', prefix='ffgui_crop_')
                    os.close(fd_new)
            
                    # 如果取消标志被设置，则清理并返回
                    if self._crop_cancel_event.is_set():
                        if os.path.exists(new_png):
                            os.unlink(new_png)
                        return
            
                    try:
                        w, h = self.extract_video_frame_scaled(
                            input_file, new_png,
                            frame_sec=sec,
                            target_width=disp_w,
                            target_height=disp_h
                        )
                        # 再次检查取消标志
                        if self._crop_cancel_event.is_set():
                            if os.path.exists(new_png):
                                os.unlink(new_png)
                            return
            
                        if w is None or h is None:
                            if os.path.exists(new_png):
                                os.unlink(new_png)
                            self.app.root.after(0, lambda: on_extract_failed("提取帧失败，请检查文件是否支持"))
                            return
                        self.app.root.after(0, lambda: on_extract_success(new_png, w, h))
                    except Exception as e:
                        if os.path.exists(new_png):
                            os.unlink(new_png)
                        self.app.root.after(0, lambda: on_extract_failed(f"提取异常: {e}"))
            
                # 启动新线程
                self._crop_extract_thread = threading.Thread(target=extract_thread, daemon=True)
                self._crop_extract_thread.start()
    
                def on_extract_success(new_scaled_path, new_orig_w, new_orig_h):
                    nonlocal img, scaled_temp_path, img_w, img_h
                    nonlocal points, rect_id, drag_start_display, drag_rect_id
                    try:
                        new_img = tk.PhotoImage(file=new_scaled_path)
                    except Exception as e:
                        # 加载失败，删除临时文件
                        if os.path.exists(new_scaled_path):
                            os.unlink(new_scaled_path)
                        on_extract_failed(f"加载缩放后的图像失败: {e}")
                        return
    
                    # 删除旧临时文件
                    if temp_file_info["path"] and os.path.exists(temp_file_info["path"]):
                        try:
                            os.unlink(temp_file_info["path"])
                        except Exception:
                            pass
                    temp_file_info["path"] = new_scaled_path  # 保存新路径
    
                    # 更新图像
                    canvas.delete("bg_img")
                    canvas.create_image(PADDING, PADDING, anchor=tk.NW, image=new_img, tags="bg_img")
                    canvas.image = new_img
                    img = new_img
    
                    # 重置选择状态
                    if rect_id:
                        canvas.delete(rect_id)
                        rect_id = None
                    if drag_rect_id:
                        canvas.delete(drag_rect_id)
                        drag_rect_id = None
                    points = []
                    drag_start_display = None
                    update_info()
                    info_var.set(f"✅ 已更新画面 (时间: {current_time:.2f}s) 请重新拖拽裁剪")
                    self.app._append_info_ui(f"[裁剪] 跳转到 {current_time:.2f}s，原始尺寸 {orig_w}x{orig_h}，显示尺寸 {disp_w}x{disp_h}")
                    refresh_btn.config(state=tk.NORMAL, text="重新获取画面")
    
                def on_extract_failed(err_msg):
                    # 清理可能残留的临时文件
                    cleanup_temp_file()
                    info_var.set(f"❌ {err_msg}")
                    self.app._append_info_ui(f"[裁剪] 提取失败: {err_msg}")
                    refresh_btn.config(state=tk.NORMAL, text="重新获取画面")
    
                threading.Thread(target=extract_thread, daemon=True).start()
    
            refresh_btn = ttk.Button(right_frame, text="重新获取画面", command=on_refresh_click)
            refresh_btn.pack(pady=2, fill=tk.X)
    
            ttk.Label(right_frame, text="支持格式: 秒数 (如 10.5) 或 HH:MM:SS[.mmm]", foreground="gray",
                      wraplength=RIGHT_PANEL_WIDTH - 20).pack(pady=(2, 10))
    
            # ----- 其他按钮 -----
            btn_frame = ttk.Frame(right_frame)
            btn_frame.pack(fill=tk.X, pady=5)
    
            ttk.Button(btn_frame, text="自动检测黑边", command=auto_detect).pack(fill=tk.X, pady=2)
    
            param_frame = ttk.Frame(btn_frame)
            param_frame.pack(fill=tk.X, pady=5)
            row = ttk.Frame(param_frame)
            row.pack(fill=tk.X)
    
            frames_container = ttk.Frame(row)
            frames_container.pack(side=tk.LEFT, padx=(0, 10))
            ttk.Label(frames_container, text="分析帧数:").pack(side=tk.LEFT)
            frames_var = tk.StringVar(value=self.crop_detect_frames.get())
            ttk.Spinbox(frames_container, from_=1, to=100, width=5, textvariable=frames_var, state="normal").pack(side=tk.LEFT, padx=5)
            frames_var.trace_add("write", lambda *a: self.crop_detect_frames.set(frames_var.get()))
    
            round_container = ttk.Frame(row)
            round_container.pack(side=tk.LEFT)
            ttk.Label(round_container, text="round:").pack(side=tk.LEFT)
            round_var = tk.StringVar(value=self.crop_detect_round.get())
            ttk.Spinbox(round_container, from_=1, to=16, width=5, textvariable=round_var, state="normal").pack(side=tk.LEFT, padx=5)
            round_var.trace_add("write", lambda *a: self.crop_detect_round.set(round_var.get()))
    
            ttk.Button(btn_frame, text="清除矩形", command=clear_rect).pack(fill=tk.X, pady=2)
            ttk.Button(btn_frame, text="保存并应用裁剪", command=apply_crop).pack(fill=tk.X, pady=2)
            ttk.Button(btn_frame, text="取消", command=on_window_close).pack(fill=tk.X, pady=2)
    
            tip = "按住左键拖拽绘制矩形（可从边缘外开始），松开确定。黄色虚线为辅助，红色为最终选区。"
            ttk.Label(right_frame, text=tip, foreground="gray", wraplength=RIGHT_PANEL_WIDTH - 20).pack(pady=10)
    
            # ----- 若已有裁剪参数，自动加载矩形 -----
            if self.crop_enabled.get():
                try:
                    w = int(self.crop_width.get())
                    h = int(self.crop_height.get())
                    x = int(self.crop_left.get())
                    y = int(self.crop_top.get())
                    points = [(x, y), (x + w, y + h)]
                    dx1, dy1 = original_to_display(x, y)
                    dx2, dy2 = original_to_display(x + w, y + h)
                    rect_id = canvas.create_rectangle(
                        dx1 + PADDING, dy1 + PADDING,
                        dx2 + PADDING, dy2 + PADDING,
                        outline='red', width=2
                    )
                    update_info()
                except:
                    pass
    
            # ----- 初始加载图像 -----
            def initial_load():
                fd, png_path = tempfile.mkstemp(suffix='.png', prefix='ffgui_crop_')
                os.close(fd)
                try:
                    w, h = self.extract_video_frame_scaled(
                        input_file, png_path,
                        frame_sec=initial_time,
                        target_width=disp_w,
                        target_height=disp_h
                    )
                    if w is None or h is None:
                        # 失败，删除临时文件
                        if os.path.exists(png_path):
                            os.unlink(png_path)
                        messagebox.showerror("错误", "无法提取初始帧")
                        win.destroy()
                        return
                    # 加载图像
                    img_obj = tk.PhotoImage(file=png_path)
                    canvas.create_image(PADDING, PADDING, anchor=tk.NW, image=img_obj, tags="bg_img")
                    canvas.image = img_obj
                    nonlocal img, scaled_temp_path
                    img = img_obj
                    temp_file_info["path"] = png_path  # 保存路径以便清理
                except Exception as e:
                    if os.path.exists(png_path):
                        os.unlink(png_path)
                    messagebox.showerror("错误", f"加载初始帧失败: {e}")
                    win.destroy()
    
            # 调用初始加载
            initial_load()
    
            # 等待窗口关闭
            win.wait_window()

    def auto_detect_crop(self):
        input_file = getattr(self, 'current_file', None)
        if not input_file or not os.path.exists(input_file):
            input_file = self.app.input_file.get().strip()
        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("错误", "请先选择一个有效的输入文件")
            return
    
        ffmpeg = self.app.ffmpeg_cmd
        if not ffmpeg:
            messagebox.showerror("错误", "未找到 ffmpeg，无法检测黑边")
            return
    
        try:
            frames = int(self.crop_detect_frames.get())
            round_val = int(self.crop_detect_round.get())
        except ValueError:
            messagebox.showerror("错误", "分析帧数和 round 必须为整数")
            return
    
        # ---- 获取截取起始时间 ----
        start_sec = 0.0
        # 优先使用可视化裁剪窗口传入的时间
        if hasattr(self, '_visual_crop_start_time') and self._visual_crop_start_time is not None:
            start_sec = self._visual_crop_start_time
            # 用完即清理，避免影响其他调用
            self._visual_crop_start_time = None
        else:
            # 原有的优先级逻辑（回调 -> 覆盖设置 -> 轨道 -> 主界面）
            if self.get_trim_settings_callback is not None:
                trim_settings = self.get_trim_settings_callback()
                if trim_settings.get("trim_enabled", False):
                    start_str = trim_settings.get("trim_start", "").strip()
                    if start_str:
                        sec = time_to_seconds(start_str)
                        if sec is not None:
                            start_sec = sec
            elif self.override_settings is not None:
                if self.override_settings.get("trim_enabled", False):
                    start_str = self.override_settings.get("trim_start", "").strip()
                    if start_str:
                        sec = time_to_seconds(start_str)
                        if sec is not None:
                            start_sec = sec
            elif self.current_track is not None:
                enc = self.current_track.enc_settings
                if enc.get("trim_enabled", False):
                    start_str = enc.get("trim_start", "").strip()
                    if start_str:
                        sec = time_to_seconds(start_str)
                        if sec is not None:
                            start_sec = sec
            else:
                if self.app.trim_frame.trim_enabled.get():
                    start_str = self.app.trim_frame.trim_start.get().strip()
                    if start_str:
                        sec = time_to_seconds(start_str)
                        if sec is not None:
                            start_sec = sec
    
        # 禁用按钮防止重复点击
        for child in self.winfo_children():
            if isinstance(child, ttk.Button) and "自动检测黑边" in child.cget("text"):
                child.config(state=tk.DISABLED)
                break
    
        def detect():
            try:
                cmd = [ffmpeg, "-i", input_file]
                # 如果起始时间 > 0，添加 -ss 快速跳转
                if start_sec > 0:
                    cmd.insert(1, "-ss")
                    cmd.insert(2, f"{start_sec:.3f}")
                # 添加 cropdetect 参数
                cmd.extend([
                    "-vframes", str(frames),
                    "-vf", f"cropdetect=limit=0.1:round={round_val}:skip=0",  # skip=0 因为已用 -ss 跳转
                    "-f", "null", "-"
                ])
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding='utf-8', errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                _, stderr = proc.communicate(timeout=15)
    
                pattern = re.compile(r'crop=(\d+):(\d+):(\d+):(\d+)')
                matches = pattern.findall(stderr)
                if not matches:
                    self.app._append_info_ui("[黑边检测] 未检测到明显的黑边，请手动调整。")
                    return
    
                w, h, x, y = matches[-1]
                self.app.root.after(0, lambda: self.crop_width.set(w))
                self.app.root.after(0, lambda: self.crop_height.set(h))
                self.app.root.after(0, lambda: self.crop_left.set(x))
                self.app.root.after(0, lambda: self.crop_top.set(y))
                self.app.root.after(0, lambda: self.crop_enabled.set(True))
                self.app._append_info_ui(f"[黑边检测] 推荐裁剪参数: crop={w}:{h}:{x}:{y}，已自动填入并启用裁剪。")
            except subprocess.TimeoutExpired:
                self.app._append_info_ui("[黑边检测] 检测超时，请检查 ffmpeg 是否正常。")
            except Exception as e:
                self.app._append_info_ui(f"[黑边检测] 出错: {e}")
            finally:
                def enable_btn():
                    for child in self.winfo_children():
                        if isinstance(child, ttk.Button) and "自动检测黑边" in child.cget("text"):
                            child.config(state=tk.NORMAL)
                            break
                self.app.root.after(0, enable_btn)
    
        threading.Thread(target=detect, daemon=True).start()

    def toggle_subtitle(self):
        enabled = self.subtitle_enabled.get()
        state = tk.NORMAL if enabled else tk.DISABLED
        self.subtitle_entry.config(state=state)
        self.browse_subtitle_btn.config(state=state)

    def browse_subtitle(self):
        if not self.subtitle_enabled.get():
            self.subtitle_enabled.set(True)
            self.toggle_subtitle()
        path = filedialog.askopenfilename(title="选择字幕文件", filetypes=[("字幕文件", "*.srt *.ass *.ssa *.vtt")])
        if path:
            self.subtitle_path.set(normalize_path(path))

    def get_settings(self):
        return {
            "frame_rate_type": self.frame_rate_type.get(),
            "frame_rate_custom": self.frame_rate_custom.get(),
            "scale_enabled": self.scale_enabled.get(),
            "scale_width": self.scale_width.get(),
            "scale_height": self.scale_height.get(),
            "scale_method": self.scale_method.get(),
            "crop_enabled": self.crop_enabled.get(),
            "crop_left": self.crop_left.get(),
            "crop_top": self.crop_top.get(),
            "crop_width": self.crop_width.get(),
            "crop_height": self.crop_height.get(),
            "rotate": self.rotate.get(),
            "vflip": self.vflip.get(),
            "hflip": self.hflip.get(),
            "speed_enabled": self.speed_enabled.get(),
            "speed_factor": self.speed_factor.get(),
            "deinterlace_filter": self.deinterlace_filter.get(),
            "pix_fmt_enabled": self.pix_fmt_enabled.get(),
            "pix_fmt": self.pix_fmt.get(),
            "subtitle_enabled": self.subtitle_enabled.get(),
            "subtitle_path": self.subtitle_path.get(),
            "reverse_enabled": self.reverse_enabled.get(),
        }

    def set_settings(self, settings):
        self.frame_rate_type.set(settings.get("frame_rate_type", "keep"))
        self.frame_rate_custom.set(settings.get("frame_rate_custom", "30"))
        self.scale_enabled.set(settings.get("scale_enabled", False))
        self.scale_width.set(settings.get("scale_width", ""))
        self.scale_height.set(settings.get("scale_height", ""))
        self.scale_method.set(settings.get("scale_method", "width"))
        self.crop_enabled.set(settings.get("crop_enabled", False))
        self.crop_left.set(settings.get("crop_left", "0"))
        self.crop_top.set(settings.get("crop_top", "0"))
        self.crop_width.set(settings.get("crop_width", "iw/2"))
        self.crop_height.set(settings.get("crop_height", "ih"))
        self.rotate.set(settings.get("rotate", "none"))
        self.vflip.set(settings.get("vflip", False))
        self.hflip.set(settings.get("hflip", False))
        self.speed_enabled.set(settings.get("speed_enabled", False))
        self.speed_factor.set(settings.get("speed_factor", "1.0"))
        self.deinterlace_filter.set(settings.get("deinterlace_filter", "none"))
        self.pix_fmt_enabled.set(settings.get("pix_fmt_enabled", True))
        self.pix_fmt.set(settings.get("pix_fmt", "yuv420p"))
        self.subtitle_enabled.set(settings.get("subtitle_enabled", False))
        self.subtitle_path.set(settings.get("subtitle_path", ""))
        self.toggle_subtitle()
        self.reverse_enabled.set(settings.get("reverse_enabled", False))


# ================== 音频组件 ==================
class AudioFrame(ttk.LabelFrame):
    def __init__(self, parent, enable_checkbox=False, **kwargs):
        super().__init__(parent, text="音频", padding="5", **kwargs)
        self.enable_checkbox = enable_checkbox
        self.create_widgets()

    def create_widgets(self):
        inner = ttk.Frame(self)
        inner.pack(fill=tk.X, expand=True)
    
        top_row = ttk.Frame(inner)
        top_row.pack(fill=tk.X, pady=(0,5))

        if self.enable_checkbox:
            self.audio_enabled = tk.BooleanVar(value=True)
            chk = ttk.Checkbutton(top_row, text="保留音频", variable=self.audio_enabled)
            chk.pack(side=tk.LEFT)

        self.only_audio = tk.BooleanVar(value=False)
        self.only_audio_cb = ttk.Checkbutton(top_row, text="仅提取音频", variable=self.only_audio)
        self.only_audio_cb.pack(side=tk.LEFT, padx=(50,2))

        ttk.Label(top_row, text="输出容器:").pack(side=tk.LEFT, padx=(12,2))
        self.audio_format = tk.StringVar(value="m4a")
        audio_format_combo = ttk.Combobox(top_row, textvariable=self.audio_format,
                                          values=["mp3", "aac", "m4a", "flac", "opus", "wav", "ac3"],
                                          state="readonly", width=6)
        audio_format_combo.pack(side=tk.LEFT, padx=2)
        ToolTip(self.only_audio_cb, "勾选后，将只输出音频文件（自动添加 -vn 忽略视频），\n输出容器将使用右边选择的音频格式", wraplength=440, offset_x=0, offset_y=5)
    
        controls_frame = ttk.Frame(inner)
        controls_frame.pack(fill=tk.X, expand=True, pady=(5,0))
        ttk.Label(controls_frame, text="编码器:").pack(side=tk.LEFT)
        self.audio_codec = tk.StringVar(value="aac")
        ttk.Combobox(controls_frame, textvariable=self.audio_codec,
                     values=ALL_AUDIO_ENCODERS, state="readonly", width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(controls_frame, text="比特率:").pack(side=tk.LEFT)
        self.audio_bitrate = tk.StringVar(value="128k")
        bitrate_combo = ttk.Combobox(controls_frame, textvariable=self.audio_bitrate, width=6, values=["64k","96k", "128k", "192k", "256k", "320k"], state='readonly')
        bitrate_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(controls_frame, text="采样率:").pack(side=tk.LEFT)
        self.audio_samplerate = tk.StringVar(value="44100")
        samplerate_combo = ttk.Combobox(controls_frame, textvariable=self.audio_samplerate, width=8, values=["8000","12000","16000","22050","32000", "44100", "48000", "96000"], state='readonly')
        samplerate_combo.pack(side=tk.LEFT, padx=5)

        volume_frame = ttk.Frame(inner)
        volume_frame.pack(fill=tk.X, pady=(2,0))
        self.volume_enabled = tk.BooleanVar(value=False)
        chk_volume = ttk.Checkbutton(volume_frame, text="启用音量调整", variable=self.volume_enabled)
        chk_volume.pack(side=tk.LEFT, padx=(0,5))
        ToolTip(chk_volume, "勾选后启用音量倍数调整，可拖动滑块设置倍数（0.1~3.0）\n\n1.0=原始音量", wraplength=400)
        ttk.Label(volume_frame, text="倍数:").pack(side=tk.LEFT, padx=(5,0))
        self.volume_value = tk.DoubleVar(value=1.0)
        self.volume_slider = ttk.Scale(volume_frame, from_=0.1, to=3.0, variable=self.volume_value,
                                       orient=tk.HORIZONTAL, length=150, state=tk.DISABLED)
        self.volume_slider.pack(side=tk.LEFT, padx=5)
        self.volume_label = ttk.Label(volume_frame, text="1.0", width=5)
        self.volume_label.pack(side=tk.LEFT)
        self.volume_slider.configure(command=lambda v: self.volume_label.config(text=f"{float(v):.2f}"))
        
        def on_volume_enabled(*args):
            state = tk.NORMAL if self.volume_enabled.get() else tk.DISABLED
            self.volume_slider.config(state=state)
        self.volume_enabled.trace_add("write", on_volume_enabled)

    def get_settings(self):
        volume = self.volume_value.get()
        if volume < 0.1:
            volume = 0.1
        elif volume > 3.0:
            volume = 3.0
        res = {
            "audio_codec": self.audio_codec.get(),
            "audio_bitrate": self.audio_bitrate.get(),
            "audio_samplerate": self.audio_samplerate.get(),
            "only_audio": self.only_audio.get(),
            "audio_format": self.audio_format.get(),
            "volume": volume,
            "volume_enabled": self.volume_enabled.get()
        }
        if self.enable_checkbox:
            res["audio_enabled"] = self.audio_enabled.get()
        return res
    
    def set_settings(self, settings):
        if self.enable_checkbox and "audio_enabled" in settings:
            self.audio_enabled.set(settings["audio_enabled"])
        self.audio_codec.set(settings.get("audio_codec", "aac"))
        self.audio_bitrate.set(settings.get("audio_bitrate", "128k"))
        self.audio_samplerate.set(settings.get("audio_samplerate", "44100"))
        self.only_audio.set(settings.get("only_audio", False))
        self.audio_format.set(settings.get("audio_format", "m4a"))
        vol = settings.get("volume", 1.0)
        self.volume_value.set(vol)
        self.volume_label.config(text=f"{vol:.2f}")
        enabled = settings.get("volume_enabled", False)
        self.volume_enabled.set(enabled)


# ================== 截取片段组件 ==================
class TrimFrame(ttk.LabelFrame):
    def __init__(self, parent, show_combo_seek=True, update_callback=None, **kwargs):
        kwargs.pop('update_callback', None)
        super().__init__(parent, text="截取片段", padding="5", **kwargs)
        self.show_combo_seek = show_combo_seek
        self.update_callback = update_callback
        self.combo_check = None
        self._setting = False
        self.create_widgets()

    def create_widgets(self):
        self.trim_enabled = tk.BooleanVar(value=False)
        top_line = ttk.Frame(self)
        top_line.pack(fill=tk.X, pady=(0,5))
        
        self.trim_check = ttk.Checkbutton(top_line, text="启用截取片段", variable=self.trim_enabled,
                                          command=self.on_trim_toggle)
        self.trim_check.pack(side=tk.LEFT, padx=5)
        
        info_label = ttk.Label(top_line, text="示例: 01:23:45 或 01:23:45.500 (留空表示到文件末尾)", 
                               foreground="gray")
        info_label.pack(side=tk.LEFT, padx=5)
        ToolTip(self.trim_check, 
                "默认是 -ss 在 -i 之前的快速模式，快速无损截取请把音频视频都改为Copy\n\n"
                "截取功能在普通转码模式下（无水印/画中画）表现稳定，支持快速截取（基于关键帧）和精准截取（基于解码帧）两种方式。\n\n"
                "当同时启用了「水印」或「画中画（子视频）」时：\n"
                "  主视频截取：\n"
                "    · 推荐使用「精准截取」模式（勾选“精准到帧”），可确保水印时长精确匹配主视频截取时长。\n"
                "    · 快速模式下因基于关键帧，结束时间可能有几帧偏差（通常可忽略）。\n\n"
                "  子视频（水印/画中画）截取：\n"
                "    · 子视频启用截取后，截取的片段会通过 loop 滤镜循环播放，直至主视频结束。\n"
                "    · 若循环次数有限（自定义次数），通过 enable 表达式限制显示时间，水印会在显示指定次数后消失，主视频继续播放。\n"
                "    · 若循环为无限或次数总时长超过主视频，水印将持续显示到视频结束。\n\n"
                "若您不希望水印循环或需要更精细控制，建议先在「视频转码」标签页单独处理好子视频，再导入作为水印/画中画素材。",
                wraplength=700)

        time_frame = ttk.Frame(self)
        time_frame.pack(fill=tk.X, pady=2)
        ttk.Label(time_frame, text="开始时间 (HH:MM:SS[.mmm]):").pack(side=tk.LEFT)
        self.trim_start = tk.StringVar(value="0")
        self.trim_start_entry = ttk.Entry(time_frame, textvariable=self.trim_start, width=12)
        self.trim_start_entry.pack(side=tk.LEFT, padx=5)
    
        time_frame2 = ttk.Frame(self)
        time_frame2.pack(fill=tk.X, pady=2)
        ttk.Label(time_frame2, text="结束时间 (HH:MM:SS[.mmm]):").pack(side=tk.LEFT)
        self.trim_end = tk.StringVar(value="")
        self.trim_end_entry = ttk.Entry(time_frame2, textvariable=self.trim_end, width=12)
        self.trim_end_entry.pack(side=tk.LEFT, padx=5)
    
        # 精准到帧
        precise_frame = ttk.Frame(self)
        precise_frame.pack(fill=tk.X, pady=5)
        self.precise_trim = tk.BooleanVar(value=False)
        self.precise_check = ttk.Checkbutton(
            precise_frame, 
            text="精准到帧（需重新编码，速度慢）", 
            variable=self.precise_trim,
            command=self.on_precise_toggle
        )
        self.precise_check.pack(side=tk.LEFT, padx=5)
        ToolTip(self.precise_check,
                "勾选后，截取将精确到帧，但必须重新编码视频。\n"
                "若编码器为「copy」将自动提示。\n"
                "取消勾选则为快速截取（基于关键帧），可能不精确但速度快。",
                wraplength=400)

        # ---------- 组合跳转控件（根据 show_combo_seek 决定是否显示） ----------
        if self.show_combo_seek:
            combo_frame = ttk.Frame(self)
            combo_frame.pack(fill=tk.X, pady=2)
            
            self.combo_seek = tk.BooleanVar(value=False)
            self.combo_threshold = tk.IntVar(value=30)

            self.combo_seek.trace_add('write', self._on_combo_changed)
            self.combo_threshold.trace_add('write', self._on_combo_changed)

            self.combo_check = ttk.Checkbutton(
                combo_frame, 
                text="组合跳转（加速长视频精确截取）", 
                variable=self.combo_seek,
                command=self._on_combo_toggle
            )
            self.combo_check.pack(side=tk.LEFT, padx=5)
            
            ttk.Label(combo_frame, text="后置微调阈值(秒):").pack(side=tk.LEFT, padx=(10,0))
            spin = ttk.Spinbox(combo_frame, from_=1, to=120, width=5, 
                               textvariable=self.combo_threshold)
            spin.pack(side=tk.LEFT, padx=2)
            
            ToolTip(self.combo_check,
                "⚡ 组合跳转模式（仅推荐用于单个纯净视频转码）\n\n"
                "原理：先快速跳到目标时间点之前的关键帧（输入跳转），\n"
                "      再精确解码到目标帧（输出跳转），兼顾速度与精度。\n\n"
                "阈值含义：\n"
                "  例如：起始时间 3600s，阈值 30s → 前置跳 3570s，后置微调 30s\n\n"
                "适用场景：\n"
                "  ✅ 单个视频文件，无叠加、无水印、无画中画\n"
                "  ✅ 需要从长视频中间位置开始截取（如从1小时处开始）\n"
                "  ✅ 编码器非 copy（必须重新编码）\n\n"
                "何时启用：\n"
                "  📌 当视频总时长 > 2分钟 且 截取起始时间 > 30秒 时，推荐开启此模式；\n"
                "  📌 若视频较短（<5分钟）或起始时间非常靠前（<10秒），提升不明显，\n\n"
                "不适用场景：\n"
                "  ❌ 启用「水印」或「画中画」（自动禁用）\n"
                "     原因：前后双 -ss 的后置 -ss 无法区分是针对主视频还是从视频，\n"
                "           容易误作用于其他输入，导致截取错位。\n"
                "  ❌ 启用「精准到帧」模式（互斥，勾选后自动取消）\n"
                "  ❌ 仅提取音频（only_audio）\n\n"
                "性能提升参考（2小时电影，从1小时处截取）：\n"
                "  • 软件解码：省去约15~30分钟的解码时间\n"
                "  • 硬件解码（cuda/qsv）：省去约5~10分钟\n"
                "  • 精准的trim模式需要慢慢把前面的全解码在丢弃，所以慢\n\n"
                "阈值建议：默认30秒足以覆盖绝大多数关键帧间隔（1~10秒），\n"
                "         无需调大，调大反而增加解码耗时。\n"
                "若起始时间小于阈值，则自动跳过前置跳转，仅执行后置微调。",
                wraplength=500)
        else:
            # 不显示组合跳转时，创建内部变量但强制为 False
            self.combo_seek = tk.BooleanVar(value=False)
            self.combo_threshold = tk.IntVar(value=30)
            self.combo_check = None



        self.on_trim_toggle()


    def _on_combo_changed(self, *args):
        """组合跳转相关控件变化时，触发外部刷新"""
        if not self._setting and self.update_callback:
            self.update_callback()

    # ---------- 新增：组合跳转切换回调 ----------
    def _on_combo_toggle(self):
        if self.combo_seek.get():
            # 启用组合跳转时，禁用精准模式（互斥）
            self.precise_trim.set(False)
            self.precise_check.config(state='disabled')
        else:
            self.precise_check.config(state='normal')
        if not self._setting and self.update_callback:
            self.update_callback()

    # ---------- 修改：精准模式切换回调（增加互斥） ----------
    def on_precise_toggle(self):
        if self.precise_trim.get() and self.show_combo_seek and self.combo_seek.get():
            # 如果精准模式被启用，但组合跳转已启用，则禁用组合跳转
            self.combo_seek.set(False)
            if self.combo_check:
                self.combo_check.config(state='normal')
        # 原有逻辑（如有）保留
        pass

    def on_trim_toggle(self):
        state = tk.NORMAL if self.trim_enabled.get() else tk.DISABLED
        self.trim_start_entry.config(state=state)
        self.trim_end_entry.config(state=state)

    # ---------- 修改：get_settings 增加组合跳转字段 ----------
    def get_settings(self):
        res = {
            "trim_enabled": self.trim_enabled.get(),
            "trim_start": self.trim_start.get(),
            "trim_end": self.trim_end.get(),
            "precise_trim": self.precise_trim.get(),
        }
        if self.show_combo_seek:
            res["combo_seek"] = self.combo_seek.get()
            res["combo_threshold"] = self.combo_threshold.get()
        else:
            # 在不显示的场景下强制为 False
            res["combo_seek"] = False
            res["combo_threshold"] = 30
        return res

    # ---------- 修改：set_settings 增加组合跳转字段 ----------
    def set_settings(self, settings):
        self._setting = True
        try:
            self.trim_enabled.set(settings.get("trim_enabled", False))
            self.trim_start.set(settings.get("trim_start", "0"))
            self.trim_end.set(settings.get("trim_end", ""))
            self.precise_trim.set(settings.get("precise_trim", False))
            if self.show_combo_seek:
                self.combo_seek.set(settings.get("combo_seek", False))
                self.combo_threshold.set(settings.get("combo_threshold", 30))
                self._on_combo_toggle()
            else:
                self.combo_seek.set(False)
            self.on_trim_toggle()
        finally:
            self._setting = False

# ================== 公共组件：循环与绿幕 ==================
class LoopChromaFrame(ttk.LabelFrame):
    """循环播放与绿幕抠像设置组件 - 左右并排（grid布局）"""
    def __init__(self, master, **kwargs):
        super().__init__(master, text="循环/绿幕控制", padding="5", **kwargs)
        self._create_widgets()

    def _create_widgets(self):
        # 使用 grid 布局，将窗口分为左右两列，权重相等
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        # ----- 左侧：循环播放（列0） -----
        loop_frame = ttk.LabelFrame(self, text="循环播放", padding="5")
        loop_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        loop_frame.columnconfigure(0, weight=1)

        self.loop_enabled = tk.BooleanVar(value=False)
        chk = ttk.Checkbutton(loop_frame, text="启用循环控制 (不启用=无限循环)", variable=self.loop_enabled)
        chk.grid(row=0, column=0, sticky="w", pady=(0,5))
        ToolTip(chk, 
                "勾选后可设置显示次数或仅显示一次。\n"
                "注意：图片文件时长就1帧，若选择“一次”会导致瞬间消失，\n"
                "您可复制生成的命令，手动修改 enable 表达式中的时间值以达到预期效果。",
                wraplength=500)

        # 次数控制区域（始终显示，但默认禁用）
        self.count_frame = ttk.Frame(loop_frame)
        self.count_frame.grid(row=1, column=0, sticky="w", padx=10, pady=2)

        ttk.Label(self.count_frame, text="显示次数:").pack(side=tk.LEFT)
        self.loop_count = tk.IntVar(value=3)
        self.count_spinbox = ttk.Spinbox(
            self.count_frame,
            from_=1, to=100,
            width=5,
            textvariable=self.loop_count,
            state="readonly"  # 初始为禁用（但实际禁用应设为 "disabled"）
        )
        # 初始禁用
        self.count_spinbox.config(state="disabled")
        self.count_spinbox.pack(side=tk.LEFT, padx=5)
        ttk.Label(self.count_frame, text="次").pack(side=tk.LEFT)

        # 时长显示标签
        self.duration_label = ttk.Label(loop_frame, text="", foreground="gray")
        self.duration_label.grid(row=2, column=0, sticky="w", padx=10, pady=(5,0))

        # 初始化 loop_mode
        self.loop_mode = tk.StringVar(value="infinite")

        # 绑定事件
        def on_loop_enabled_changed(*args):
            if self.loop_enabled.get():
                # 启用循环 → 次数输入可修改，loop_mode 设为 count
                self.count_spinbox.config(state="readonly")
                self.loop_mode.set("count")
            else:
                # 未启用 → 次数输入禁用，loop_mode 设为 infinite
                self.count_spinbox.config(state="disabled")
                self.loop_mode.set("infinite")
        self.loop_enabled.trace_add("write", on_loop_enabled_changed)

        # ----- 右侧：绿幕抠像（列1） -----
        chroma_frame = ttk.LabelFrame(self, text="绿幕抠像 (色度键)", padding="5")
        chroma_frame.grid(row=0, column=1, sticky="nsew", padx=(2, 0))
        chroma_frame.columnconfigure(0, weight=1)
        chroma_frame.columnconfigure(1, weight=1)

        top_row = ttk.Frame(chroma_frame)
        top_row.grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=2)

        self.chroma_enabled = tk.BooleanVar(value=False)
        chk = ttk.Checkbutton(top_row, text="启用绿幕抠像", variable=self.chroma_enabled)
        chk.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(chk,
                "勾选后，将使用选择的抠像算法去除纯色背景（绿幕/蓝幕/纯色）。",
                wraplength=400)

        # 滤镜类型：chromakey 和 colorkey 单选按钮
        self.chroma_filter_type = tk.StringVar(value="chromakey")
        rb_chroma = ttk.Radiobutton(top_row, text="chromakey", 
                                    variable=self.chroma_filter_type, value="chromakey")
        rb_chroma.pack(side=tk.LEFT, padx=2)
        ToolTip(rb_chroma,
                "基于色相/饱和度（HSV）抠像，适合视频绿幕/蓝幕，\n"
                "对颜色渐变和光照变化有较好抗性。推荐用于视频素材。",
                wraplength=400)

        rb_color = ttk.Radiobutton(top_row, text="colorkey", 
                                   variable=self.chroma_filter_type, value="colorkey")
        rb_color.pack(side=tk.LEFT, padx=2)
        ToolTip(rb_color,
                "基于 RGB 颜色距离抠像，适合静态图片、GIF、纯色背景（白/黑），\n"
                "对索引色（如 GIF）更稳定。若 chromakey 效果不佳可尝试此项。",
                wraplength=400)


        color_row = ttk.Frame(chroma_frame)
        color_row.grid(row=1, column=0, sticky="w", pady=2)

        ttk.Label(color_row, text="抠除颜色:").pack(side=tk.LEFT)
        self.chroma_color = tk.StringVar(value="#3fff08")
        color_combo = ttk.Combobox(color_row, textvariable=self.chroma_color,
                                   values=["#3fff08", "#00CFFD", "black", "white"], state="readonly", width=10)
        color_combo.pack(side=tk.LEFT, padx=5)
        self.color_swatch = tk.Label(color_row, width=4, height=1, relief=tk.SUNKEN, bg=self.chroma_color.get())
        self.color_swatch.pack(side=tk.LEFT, padx=5)
        self.chroma_color.trace_add("write", lambda *a: self.color_swatch.config(bg=self.chroma_color.get()))

        # 吸管取色（Windows）
        def pick_color():
            if sys.platform != "win32":
                messagebox.showinfo("提示", "吸管取色仅支持 Windows")
                return
            import ctypes
            import ctypes.wintypes
            def get_pixel_color(x, y):
                hdc = ctypes.windll.user32.GetDC(0)
                pixel = ctypes.windll.gdi32.GetPixel(hdc, x, y)
                ctypes.windll.user32.ReleaseDC(0, hdc)
                r = pixel & 0xFF
                g = (pixel >> 8) & 0xFF
                b = (pixel >> 16) & 0xFF
                return f"#{r:02x}{g:02x}{b:02x}"
            mask = tk.Toplevel(self)
            mask.attributes('-fullscreen', True)
            mask.attributes('-alpha', 0.3)
            mask.configure(bg='black', cursor='crosshair')
            mask.attributes('-topmost', True)
            tip = tk.Label(mask, text="点击屏幕任意位置取色 (ESC 取消)", font=("Microsoft YaHei", 16, "bold"),
                           fg="white", bg="black", padx=20, pady=10)
            tip.pack(expand=True)
            def on_click(event):
                mask.withdraw()
                mask.update_idletasks()
                hex_color = get_pixel_color(event.x_root, event.y_root)
                mask.destroy()
                self.chroma_color.set(hex_color)
            def on_escape(event):
                mask.destroy()
            mask.bind("<Button-1>", on_click)
            mask.bind("<Escape>", on_escape)
            self.wait_window(mask)

        ttk.Button(color_row, text="🔍吸取颜色", command=pick_color).pack(side=tk.LEFT, padx=5)
        ttk.Button(color_row, text="标准色盘", command=self._pick_standard_color).pack(side=tk.LEFT, padx=5)

        # 相似度
        sim_frame = ttk.Frame(chroma_frame)
        sim_frame.grid(row=2, column=0, sticky="we", pady=2)
        sim_label = ttk.Label(sim_frame, text="相似度 (0~1):")
        sim_label.pack(side=tk.LEFT)
        ToolTip(sim_label,
                "【绿幕/蓝幕】推荐 0.3 左右，可适当调整。\n如果觉得转换后的对象发虚透明，降低相似度重试。",
                wraplength=400)
        self.chroma_similarity = tk.DoubleVar(value=0.3)
        sim_slider = ttk.Scale(sim_frame, from_=0.0, to=1.0, variable=self.chroma_similarity,
                               orient=tk.HORIZONTAL, length=100)
        sim_slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.sim_entry_var = tk.StringVar(value="0.3000")
        sim_entry = ttk.Entry(sim_frame, textvariable=self.sim_entry_var, width=8)
        sim_entry.pack(side=tk.LEFT, padx=5)
        def sim_slider_changed(val):
            self.sim_entry_var.set(f"{float(val):.4f}")
        sim_slider.configure(command=sim_slider_changed)
        def sim_entry_changed(*args):
            try:
                val = float(self.sim_entry_var.get())
                if 0.0 <= val <= 1.0:
                    self.chroma_similarity.set(val)
                else:
                    raise ValueError
            except:
                self.sim_entry_var.set(f"{self.chroma_similarity.get():.4f}")
        self.sim_entry_var.trace_add("write", sim_entry_changed)

        # 混合度
        blend_frame = ttk.Frame(chroma_frame)
        blend_frame.grid(row=3, column=0, sticky="we", pady=2)
        ttk.Label(blend_frame, text="混合度/平滑 (0~1):").pack(side=tk.LEFT)
        self.chroma_blend = tk.DoubleVar(value=0.1)
        blend_slider = ttk.Scale(blend_frame, from_=0.0, to=1.0, variable=self.chroma_blend,
                                 orient=tk.HORIZONTAL, length=100)
        blend_slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.blend_entry_var = tk.StringVar(value="0.10")
        blend_entry = ttk.Entry(blend_frame, textvariable=self.blend_entry_var, width=8)
        blend_entry.pack(side=tk.LEFT, padx=5)
        def blend_slider_changed(val):
            self.blend_entry_var.set(f"{float(val):.2f}")
        blend_slider.configure(command=blend_slider_changed)
        def blend_entry_changed(*args):
            try:
                val = float(self.blend_entry_var.get())
                if 0.0 <= val <= 1.0:
                    self.chroma_blend.set(val)
                else:
                    raise ValueError
            except:
                self.blend_entry_var.set(f"{self.chroma_blend.get():.2f}")
        self.blend_entry_var.trace_add("write", blend_entry_changed)

        # 透明度控制（行1，横跨两列）
        alpha_frame = ttk.Frame(self)
        alpha_frame.grid(row=1, column=0, columnspan=2, sticky="we", pady=5)
        
        self.alpha_enabled = tk.BooleanVar(value=False)
        alpha_cb = ttk.Checkbutton(alpha_frame, text="透明度", variable=self.alpha_enabled)
        alpha_cb.pack(side=tk.LEFT, padx=(0,5))
        
        self.alpha_value = tk.DoubleVar(value=1.0)
        alpha_scale = ttk.Scale(alpha_frame, from_=0.0, to=1.0, variable=self.alpha_value,
                                orient=tk.HORIZONTAL, length=100)
        alpha_scale.pack(side=tk.LEFT, fill=tk.X, expand=False, padx=5)
        
        self.alpha_spinbox_var = tk.StringVar(value="1.0")
        alpha_spin = ttk.Spinbox(alpha_frame, from_=0.0, to=1.0, increment=0.1,
                                 textvariable=self.alpha_spinbox_var, width=6)
        alpha_spin.pack(side=tk.LEFT, padx=5)
        
        # 滑块 → Spinbox 同步
        def alpha_slider_changed(val):
            self.alpha_spinbox_var.set(f"{float(val):.1f}")
        alpha_scale.configure(command=alpha_slider_changed)
        
        # Spinbox → 滑块同步（手动输入时）
        def alpha_spin_changed(*args):
            try:
                val = float(self.alpha_spinbox_var.get())
                if 0.0 <= val <= 1.0:
                    self.alpha_value.set(val)
                else:
                    raise ValueError
            except:
                self.alpha_spinbox_var.set(f"{self.alpha_value.get():.1f}")
        self.alpha_spinbox_var.trace_add("write", alpha_spin_changed)



    def _pick_standard_color(self):
        from tkinter import colorchooser
        color_code = colorchooser.askcolor(title="选择抠像颜色", parent=self, initialcolor=self.chroma_color.get())[1]
        if color_code:
            self.chroma_color.set(color_code)

    def get_settings(self):
        return {
            "loop_enabled": self.loop_enabled.get(),
            "loop_mode": self.loop_mode.get(),
            "loop_count": self.loop_count.get(),
            "chroma_enabled": self.chroma_enabled.get(),
            "chroma_color": self.chroma_color.get(),
            "chroma_similarity": self.chroma_similarity.get(),
            "chroma_blend": self.chroma_blend.get(),
            # 新增透明度
            "alpha_enabled": self.alpha_enabled.get(),
            "alpha_value": self.alpha_value.get(),
            "chroma_filter_type": self.chroma_filter_type.get(),
        }
    
    def set_settings(self, settings):
        self.loop_enabled.set(settings.get("loop_enabled", False))
        self.loop_mode.set(settings.get("loop_mode", "infinite"))
        self.loop_count.set(settings.get("loop_count", 3))
        self.chroma_enabled.set(settings.get("chroma_enabled", False))
        self.chroma_color.set(settings.get("chroma_color", "#3fff08"))
        sim = settings.get("chroma_similarity", 0.3)
        if sim <= 0:
            sim = 0.3
        self.chroma_similarity.set(sim)
        self.sim_entry_var.set(f"{sim:.4f}")
        blend = settings.get("chroma_blend", 0.1)
        self.chroma_blend.set(blend)
        self.blend_entry_var.set(f"{blend:.2f}")
        self.chroma_filter_type.set(settings.get("chroma_filter_type", "chromakey"))
        self.color_swatch.config(bg=self.chroma_color.get())
        self._update_loop_state()
    
        # 新增透明度恢复
        self.alpha_enabled.set(settings.get("alpha_enabled", False))
        val = settings.get("alpha_value", 1.0)
        self.alpha_value.set(val)
        self.alpha_spinbox_var.set(f"{val:.1f}")

    def set_duration_info(self, duration_sec: Optional[float]):
        """设置时长显示信息"""
        if duration_sec is not None and duration_sec > 0:
            # 格式化为 时:分:秒.毫秒
            hours = int(duration_sec // 3600)
            minutes = int((duration_sec % 3600) // 60)
            seconds = duration_sec % 60
            if hours > 0:
                text = f"视频时长: {hours:02d}:{minutes:02d}:{seconds:05.2f}"
            else:
                text = f"视频时长: {minutes:02d}:{seconds:05.2f}"
            self.duration_label.config(text=text)
        else:
            self.duration_label.config(text="")

    def _update_loop_state(self):
        if self.loop_enabled.get():
            self.count_spinbox.config(state="readonly")
            self.loop_mode.set("count")
        else:
            self.count_spinbox.config(state="disabled")
            self.loop_mode.set("infinite")

# ================== 公共组件：叠加位置与画布偏移（仅轨道模式） ==================
class OverlayPositionFrame(ttk.LabelFrame):
    """
    叠加位置（子视频）或画布偏移（主视频）设置组件。
    仅用于画中画或水印模式，始终显示控件。
    """
    def __init__(self, master, app, mode='sub', track_idx=None, track_obj=None,
                 filt_frame=None, visual_callback=None, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app
        self.mode = mode
        self.track_idx = track_idx
        self.track_obj = track_obj
        self.filt_frame = filt_frame
        self.visual_callback = visual_callback
        self._controls = []
        self._create_controls()

    def _create_controls(self):
        if self.mode == 'sub':
            self._create_sub_controls()
        else:
            self._create_main_controls()

    def _create_sub_controls(self):
        """子视频叠加位置控件"""
        self.overlay_enabled = tk.BooleanVar(value=True)
        cb = ttk.Checkbutton(self, text="启用叠加", variable=self.overlay_enabled)
        cb.pack(anchor=tk.W, pady=(0,5))
        self._controls.append(cb)

        ttk.Label(self, text="X 位置 (支持表达式，如 W-w-10):").pack(anchor=tk.W)
        self.overlay_x = tk.StringVar(value="W-w-10")
        entry = ttk.Entry(self, textvariable=self.overlay_x, width=40)
        entry.pack(fill=tk.X, pady=2)
        self._controls.append(entry)

        ttk.Label(self, text="Y 位置 (支持表达式):").pack(anchor=tk.W)
        self.overlay_y = tk.StringVar(value="H-h-10")
        entry = ttk.Entry(self, textvariable=self.overlay_y, width=40)
        entry.pack(fill=tk.X, pady=2)
        self._controls.append(entry)

        # 快速预设
        preset_frame = ttk.LabelFrame(self, text="快速预设", padding="3")
        preset_frame.pack(fill=tk.X, pady=5)
        self._controls.append(preset_frame)

        positions = {
            "左上角": ("10", "10"),
            "右上角": ("W-w-10", "10"),
            "左下角": ("10", "H-h-10"),
            "右下角": ("W-w-10", "H-h-10"),
            "居中": ("(W-w)/2", "(H-h)/2")
        }
        def set_position(x_val, y_val):
            self.overlay_x.set(x_val)
            self.overlay_y.set(y_val)
        for text, (x_val, y_val) in positions.items():
            btn = ttk.Button(preset_frame, text=text,
                             command=lambda x=x_val, y=y_val: set_position(x, y))
            btn.pack(side=tk.LEFT, padx=2, pady=2)
            self._controls.append(btn)

        # 可视化编辑
        def open_visual():
            if not self.overlay_enabled.get():
                messagebox.showinfo("提示", "请先勾选「启用叠加」再使用可视化编辑功能。")
                return
            if self.visual_callback is not None:
                self.visual_callback()
            elif self.app and self.track_idx is not None:
                parent_win = self.winfo_toplevel()
                self.app.open_visual_overlay_editor(
                    self.track_idx,
                    ov_x_var=self.overlay_x,
                    ov_y_var=self.overlay_y,
                    filt_frame=self.filt_frame,
                    parent=parent_win
                )
            else:
                messagebox.showinfo("提示", "无法启动可视化编辑：缺少轨道索引或回调")
        btn = ttk.Button(preset_frame, text="🎨 可视化编辑坐标", command=open_visual)
        btn.pack(side=tk.LEFT, padx=5, pady=2)
        self._controls.append(btn)

    def _create_main_controls(self):
        """主视频画布偏移控件 - 左右分栏（左侧偏移设置，右侧快捷操作）"""
        # 主容器：水平分割
        main_container = ttk.Frame(self)
        main_container.pack(fill=tk.BOTH, expand=True)
    
        # ---------- 左容器：偏移设置 ----------
        left_frame = ttk.Frame(main_container)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, expand=False)
    
        self.pad_enabled = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(left_frame, text="启用画布偏移", variable=self.pad_enabled)
        cb.pack(anchor=tk.W, pady=(0,5))
        self._controls.append(cb)
    
        w_frame = ttk.Frame(left_frame)
        w_frame.pack(fill=tk.X, pady=2)
        ttk.Label(w_frame, text="画布宽度:").pack(side=tk.LEFT)
        self.pad_width = tk.StringVar(value="")
        entry = ttk.Entry(w_frame, textvariable=self.pad_width, width=10)
        entry.pack(side=tk.LEFT, padx=5)
        self._controls.extend([w_frame, entry])
    
        if self.app:
            def fetch_size():
                main_file = self.app.merge_video.get().strip() if self.app.merge_video else ""
                if not main_file or not os.path.exists(main_file):
                    main_file = self.app.input_file.get().strip() if self.app.input_file else ""
                if not main_file or not os.path.exists(main_file):
                    messagebox.showerror("错误", "未找到主视频文件，请先设置主视频")
                    return
                w, h = self.app._get_video_dimensions_cached(main_file)
                if w is not None and h is not None:
                    self.pad_width.set(str(w))
                    self.pad_height.set(str(h))
                    self.app._append_info_ui(f"[尺寸获取] 获取到主视频尺寸: {w}x{h}")
                else:
                    messagebox.showerror("错误", f"无法获取视频尺寸，请检查 ffprobe 是否可用或文件是否正常。")
            btn = ttk.Button(w_frame, text="获取尺寸", command=fetch_size)
            btn.pack(side=tk.LEFT, padx=5)
            self._controls.append(btn)
    
        h_frame = ttk.Frame(left_frame)
        h_frame.pack(fill=tk.X, pady=2)
        ttk.Label(h_frame, text="画布高度:").pack(side=tk.LEFT)
        self.pad_height = tk.StringVar(value="")
        entry = ttk.Entry(h_frame, textvariable=self.pad_height, width=10)
        entry.pack(side=tk.LEFT, padx=5)
        self._controls.extend([h_frame, entry])
    
        ox_frame = ttk.Frame(left_frame)
        ox_frame.pack(fill=tk.X, pady=2)
        ttk.Label(ox_frame, text="偏移 X:").pack(side=tk.LEFT)
        self.offset_x = tk.StringVar(value="0")
        entry = ttk.Entry(ox_frame, textvariable=self.offset_x, width=10)
        entry.pack(side=tk.LEFT, padx=5)
        self._controls.extend([ox_frame, entry])
    
        oy_frame = ttk.Frame(left_frame)
        oy_frame.pack(fill=tk.X, pady=2)
        ttk.Label(oy_frame, text="偏移 Y:").pack(side=tk.LEFT)
        self.offset_y = tk.StringVar(value="0")
        entry = ttk.Entry(oy_frame, textvariable=self.offset_y, width=10)
        entry.pack(side=tk.LEFT, padx=5)
        self._controls.extend([oy_frame, entry])
    
        def open_pad_editor():
            if not self.pad_enabled.get():
                messagebox.showinfo("提示", "请先勾选「启用画布偏移」再使用可视化编辑功能。")
                return
            if self.app and self.track_idx is not None:
                parent_win = self.winfo_toplevel()
                self.app.open_visual_pad_editor(
                    self.track_idx,
                    self.pad_width,
                    self.pad_height,
                    self.offset_x,
                    self.offset_y,
                    live_filt_frame=self.filt_frame, 
                    parent=parent_win
                )
            else:
                messagebox.showinfo("提示", "无法启动可视化编辑：缺少轨道索引")
        btn = ttk.Button(left_frame, text="🎨 可视化编辑画布偏移", command=open_pad_editor)
        btn.pack(anchor=tk.W, pady=5)
        self._controls.append(btn)
    
        # ---------- 右容器：快捷操作 ----------
        right_frame = ttk.Frame(main_container)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
    

        row1 = ttk.Frame(right_frame)
        row1.pack(anchor=tk.W, fill=tk.X, pady=(0, 5))
        
        # --- 取消子视频缩放/裁剪 ---
        btn_reset_sub = ttk.Button(
            row1,
            text="取消子视频缩放/裁剪",
            command=self._reset_sub_video_filters,
            width=18
        )
        btn_reset_sub.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(btn_reset_sub,
                "将所有子视频（非主视频）的「启用缩放」和「启用裁剪」复选框取消勾选，\n"
                "恢复子视频为原始尺寸。")

        row2 = ttk.Frame(right_frame)
        row2.pack(anchor=tk.W, fill=tk.X, pady=(0, 5))

        # --- 统一高度 ---
        self.unify_height_var = tk.StringVar(value="")
        btn_unify_h = ttk.Button(
            row2,
            text="统一高度",
            command=self._apply_unified_height,
            width=10
        )
        btn_unify_h.pack(side=tk.LEFT)
        spin_h = ttk.Spinbox(row2, from_=1, to=9999, width=6, textvariable=self.unify_height_var)
        spin_h.pack(side=tk.LEFT, padx=2)
        
        # --- 统一宽度 ---
        self.unify_width_var = tk.StringVar(value="")
        btn_unify_w = ttk.Button(
            row2,
            text="统一宽度",
            command=self._apply_unified_width,
            width=10
        )
        btn_unify_w.pack(side=tk.LEFT, padx=2)
        spin_w = ttk.Spinbox(row2, from_=1, to=9999, width=6, textvariable=self.unify_width_var)
        spin_w.pack(side=tk.LEFT, padx=2)
    

        # ---- 修改子视频编码 ----
        row3 = ttk.Frame(right_frame)
        row3.pack(anchor=tk.W, fill=tk.X, pady=(0, 5))
        btn_set_sub_encoder = ttk.Button(
            row3,
            text="修改子视频编码",
            command=self._set_sub_video_encoder,
            width=18
        )
        btn_set_sub_encoder.pack(side=tk.LEFT, padx=(0,5))
        ToolTip(btn_set_sub_encoder,
                "将所有子视频（非主视频）的编码器统一设置为 libx264 (H.264)。\n"
                "此操作仅修改轨道设置，消除日志的copy自动转libx265提示。\n"
                "提示：画中画模式中，子视频的编码无意义，最终编码只和主视频选择有关。")
        
        btn_reset_copy = ttk.Button(
            row3,
            text="恢复为copy",
            command=self._reset_sub_encoder_to_copy,
            width=14
        )
        btn_reset_copy.pack(side=tk.LEFT, padx=5)
        ToolTip(btn_reset_copy,
                "将所有子视频（非主视频）的编码器恢复为「copy」（流复制）。\n"
                "注意：恢复 copy 是为了给串行模式使用，如果你要更改模式的话。")


        def smart_tile():
            if self.track_idx is not None:
                orient_map = {
                    "自动": "auto",
                    "横排优先": "horizontal",
                    "竖排优先": "vertical"
                }
                orientation = orient_map.get(self.tile_orientation.get(), "auto")
                self.app.merge_smart_tile(
                    self.track_idx,
                    pad_enabled_var=self.pad_enabled,
                    pad_width_var=self.pad_width,
                    pad_height_var=self.pad_height,
                    items_per_row=self.tile_cols.get(),
                    items_per_col=self.tile_rows.get(),
                    orientation=orientation,
                    filt_frame=self.filt_frame
                )
            else:
                messagebox.showinfo("提示", "无法获取主视频轨道索引")

        tile_btn = ttk.Button(right_frame, text="计算平铺", command=smart_tile, width=8)
        tile_btn.pack(anchor=tk.W)
        ToolTip(tile_btn,
                "画中画模式下，拖入的子视频默认会缩放到320宽（便于快速预览）。\n"
                "提示：若视频尺寸一致且希望以原始大小排列，\n"
                "    可先使用「取消子视频缩放/裁剪」批量恢复原始尺寸，再执行平铺。\n"
                "    或者先去每个子视频重新裁剪缩放为需要的画面，再执行平铺。\n\n"
                "「计算平铺」会根据子视频当前的实际尺寸（包括已应用的缩放和裁剪），\n"
                "    自动计算最佳平铺布局，将多个画面整齐排列在画布中。\n\n"
                "支持三种排列方向：\n"
                "• 自动：根据画面宽高比智能选择横向或纵向优先。\n"
                "• 横排优先：按行排列，适合宽屏显示器。\n"
                "• 竖排优先：按列排列，适合竖屏或手机视频。\n\n"
                "典型用途：\n"
                "• 多机位舞台合成（演唱会、访谈等）。\n"
                "• 分屏对比（画质、色彩、动作同步）。\n"
                "• 监控画面拼接。",
                wraplength=700)




        param_row = ttk.Frame(right_frame)
        param_row.pack(anchor=tk.W, fill=tk.X, pady=5)
        
        ttk.Label(param_row, text="每行:").pack(side=tk.LEFT)
        self.tile_cols = tk.IntVar(value=4)
        ttk.Spinbox(param_row, from_=1, to=10, width=3, textvariable=self.tile_cols).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(param_row, text="每列:").pack(side=tk.LEFT, padx=(10,0))
        self.tile_rows = tk.IntVar(value=4)
        ttk.Spinbox(param_row, from_=1, to=10, width=3, textvariable=self.tile_rows).pack(side=tk.LEFT, padx=2)

        ttk.Label(param_row, text="方向:").pack(side=tk.LEFT)
        self.tile_orientation = tk.StringVar(value="自动")
        orientation_combo = ttk.Combobox(param_row, textvariable=self.tile_orientation,
                                         values=["自动", "横排优先", "竖排优先"],
                                         state="readonly", width=8)
        orientation_combo.pack(side=tk.LEFT, padx=2)
        
#         # 第四行：小提示（左对齐）
#         tip_label = ttk.Label(right_frame, text="先取消缩放/裁剪，再平铺，效果更佳",
#                               foreground="gray", font=("", 8))
#         tip_label.pack(anchor=tk.W, pady=(5,0))


    def _apply_unified_height(self):
        val_str = self.unify_height_var.get().strip()
        if not val_str:
            messagebox.showwarning("提示", "请先输入要统一的高度数值")
            return
        try:
            target = int(val_str)
            if target <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "请输入有效的正整数作为高度值")
            return
        self._apply_unified_dimension('height', target)
    
    def _apply_unified_width(self):
        val_str = self.unify_width_var.get().strip()
        if not val_str:
            messagebox.showwarning("提示", "请先输入要统一的宽度数值")
            return
        try:
            target = int(val_str)
            if target <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "请输入有效的正整数作为宽度值")
            return
        self._apply_unified_dimension('width', target)
    
    def _apply_unified_dimension(self, mode, target):
        """
        统一设置所有视频轨道的高度或宽度，并同步更新主视频的编辑对话框控件。
        :param mode: 'height' 或 'width'
        :param target: 目标像素值
        """
        if not self.app:
            return
        tracks = self.app.merge_tracks
        if not tracks:
            return
    
        # 确认操作
        if not messagebox.askyesno(
            "确认统一尺寸",
            f"此操作将把所有视频轨道（包括主视频）的{mode}统一设置为 {target}px，\n"
            "宽度或高度将按原比例自动缩放。\n\n"
            "确定继续吗？"
        ):
            return
    
        # 确定主视频索引（用于判断当前编辑的是否为主视频）
        main_idx = self.track_idx
        if main_idx is None:
            for i, t in enumerate(tracks):
                if t.type == "video" and t.enabled:
                    main_idx = i
                    break
    
        modified = 0
        for i, track in enumerate(tracks):
            if track.type != "video" or not track.enabled:
                continue
            # 获取原始尺寸
            orig_w, orig_h = get_video_dimensions(self.app.ffprobe_cmd, track.file_path)
            if orig_w is None or orig_h is None:
                continue  # 无法获取尺寸，跳过
            # 启用缩放
            track.enc_settings["scale_enabled"] = True
            if mode == 'height':
                track.enc_settings["scale_method"] = "height"
                track.enc_settings["scale_height"] = str(target)
                track.enc_settings["scale_width"] = ""
            else:  # width
                track.enc_settings["scale_method"] = "width"
                track.enc_settings["scale_width"] = str(target)
                track.enc_settings["scale_height"] = ""
            modified += 1
    
            # ---- 同步编辑对话框控件（如果当前编辑的是主视频） ----
            if (self.filt_frame is not None and main_idx is not None and i == main_idx):
                self.filt_frame.scale_enabled.set(True)
                self.filt_frame.scale_method.set(mode)
                if mode == 'height':
                    self.filt_frame.scale_height.set(str(target))
                    self.filt_frame.scale_width.set("")
                else:
                    self.filt_frame.scale_width.set(str(target))
                    self.filt_frame.scale_height.set("")
                # 触发编辑对话框的预览刷新（如果存在）
                if hasattr(self.filt_frame, '_preview_callback') and self.filt_frame._preview_callback:
                    self.filt_frame._preview_callback()
    
        if modified:
            self.app.merge_update_track_list()
            self.app.merge_update_command_preview()
            self.app._append_info_ui(f"[统一尺寸] 已将 {modified} 个视频的{mode}统一设为 {target}px")
        else:
            self.app._append_info_ui("[统一尺寸] 没有可修改的视频轨道")

    def _reset_sub_encoder_to_copy(self):
        """将所有子视频（非主视频）的编码器恢复为 copy（流复制）"""
        self._set_sub_video_encoder(encoder="copy", force_clear=True)
    
    def _set_sub_video_encoder(self, encoder="libx264", force_clear=False):
        """
        将所有子视频（非主视频）的编码器设置为指定编码器。
        :param encoder: 编码器名称，默认 libx264
        :param force_clear: 若为 True，则清除可能冲突的质量参数（用于 copy）
        """
        if not self.app:
            return
        tracks = self.app.merge_tracks
        if not tracks:
            return
    
        # 二次确认（仅当 encoder 不是 copy 时提示，或者统一提示）
        if not messagebox.askyesno(
            "确认修改编码",
            f"此操作将所有子视频（非主视频）的编码器统一设置为 {encoder}。\n"
            f"确定要继续吗？"
        ):
            return
    
        # 确定主视频轨道
        main_idx = self.track_idx
        if main_idx is None:
            for i, t in enumerate(tracks):
                if t.type == "video" and t.enabled:
                    main_idx = i
                    break
        if main_idx is None:
            self.app._append_info_ui("[子视频编码] 未找到主视频轨道")
            return
    
        modified = 0
        for i, track in enumerate(tracks):
            if i == main_idx:
                continue
            if track.type != "video" or not track.enabled:
                continue
            # 修改编码器
            track.enc_settings["encoder"] = encoder
            # 如果是 copy，清除质量相关参数，避免冲突
            if encoder.lower() == "copy":
                track.enc_settings.pop("crf_value", None)
                track.enc_settings.pop("cq_value", None)
                track.enc_settings.pop("global_quality", None)
                track.enc_settings.pop("bitrate_video", None)
                track.enc_settings.pop("rate_control_type", None)
            else:
                # 非 copy，设置合理的默认值
                if track.enc_settings.get("rate_control_type") not in ("crf", "bitrate"):
                    track.enc_settings["rate_control_type"] = "crf"
                if "crf_value" not in track.enc_settings:
                    track.enc_settings["crf_value"] = 23
            modified += 1
    
        if modified:
            self.app.merge_update_track_list()
            self.app.merge_update_command_preview()
            self.app._append_info_ui(f"[子视频编码] 已将 {modified} 个子视频的编码器设为 {encoder}")
        else:
            self.app._append_info_ui("[子视频编码] 没有需要修改的子视频")

    def _reset_sub_video_filters(self):
        """取消所有子视频（非主视频）的缩放和裁剪勾选"""
        if not self.app:
            return
        tracks = self.app.merge_tracks
        if not tracks:
            return
    
        # 确定主视频轨道（根据 self.track_idx 或第一个视频）
        main_idx = self.track_idx
        if main_idx is None:
            # 如果 track_idx 未传入，则取第一个启用的视频作为主视频
            for i, t in enumerate(tracks):
                if t.type == "video" and t.enabled:
                    main_idx = i
                    break
        if main_idx is None:
            self.app._append_info_ui("[取消子视频滤镜] 未找到主视频轨道")
            return
    
        modified = 0
        for i, track in enumerate(tracks):
            if i == main_idx:
                continue   # 跳过主视频
            if track.type != "video" or not track.enabled:
                continue
            # 取消缩放和裁剪
            track.enc_settings["scale_enabled"] = False
            track.enc_settings["crop_enabled"] = False
            # 如果轨道对象有同步属性，也更新（可选）
            # track.scale_enabled = False  # 若存在此类属性
            # track.crop_enabled = False
            modified += 1

        if modified:
            self.app.merge_update_track_list()
            self.app.merge_update_command_preview()
            self.app._append_info_ui(f"[取消子视频滤镜] 已取消 {modified} 个子视频的缩放和裁剪")
        else:
            self.app._append_info_ui("[取消子视频滤镜] 没有需要修改的子视频")


    def get_settings(self):
        if self.mode == 'sub':
            return {
                "overlay_enabled": self.overlay_enabled.get(),
                "overlay_x": self.overlay_x.get().strip(),
                "overlay_y": self.overlay_y.get().strip(),
            }
        else:
            return {
                "pad_enabled": self.pad_enabled.get(),
                "pad_width": self.pad_width.get().strip(),
                "pad_height": self.pad_height.get().strip(),
                "offset_x": self.offset_x.get().strip(),
                "offset_y": self.offset_y.get().strip(),
            }

    def set_settings(self, settings):
        if self.mode == 'sub':
            self.overlay_enabled.set(settings.get("overlay_enabled", True))
            self.overlay_x.set(settings.get("overlay_x", "W-w-10"))
            self.overlay_y.set(settings.get("overlay_y", "H-h-10"))
        else:
            self.pad_enabled.set(settings.get("pad_enabled", False))
            self.pad_width.set(settings.get("pad_width", ""))
            self.pad_height.set(settings.get("pad_height", ""))
            self.offset_x.set(settings.get("offset_x", "0"))
            self.offset_y.set(settings.get("offset_y", "0"))


# ================== 高级选项组件 ==================
class AdvancedFrame(ttk.LabelFrame):
    def __init__(self, parent, update_callback=None, app=None, show_adaptive=True, watermark_dict=None, **kwargs):
        super().__init__(parent, text="高级选项 (硬件解码/自定义参数)", padding="5", **kwargs)
        self.update_callback = update_callback
        self.app = app
        self.show_adaptive = show_adaptive
        # 设置水印字典：若传入则使用，否则使用 app 的全局设置
        if watermark_dict is not None:
            self.watermark_dict = watermark_dict
        else:
            self.watermark_dict = self.app.watermark_settings


        self.wm_preset_var = tk.StringVar()
        self.wm_templates = {}  # 缓存所有水印模板
        # 获取主预设目录（与主预设 ffmpeg_presets.json 同目录）
        if self.app and hasattr(self.app, 'preset_file_path'):
            preset_dir = os.path.dirname(self.app.preset_file_path)
        else:
            # 极罕见情况：回退到用户目录
            preset_dir = os.path.join(os.path.expanduser("~"), ".FFLiteGUI")
        
        # 确保目录存在
        os.makedirs(preset_dir, exist_ok=True)
        
        self.wm_preset_file = os.path.join(preset_dir, "watermark_templates.json")
        self._load_wm_templates()  # 加载现有模板


        self.create_widgets()



    def create_widgets(self):
        # 硬件解码
        hw_frame = ttk.Frame(self)
        hw_frame.pack(fill=tk.X, pady=2)
        self.hwaccel_enabled = tk.BooleanVar(value=False)
        hw_check = ttk.Checkbutton(hw_frame, text="启用硬件解码", variable=self.hwaccel_enabled,
                                   command=self._on_hw_toggle)
        hw_check.pack(side=tk.LEFT)
        ToolTip(hw_check,
            "【NVIDIA推荐】\n1.cuda（首选）：自动识别H264/HEVC/AV1，支持全程显存加速。\n2.auto：传统模式，兼容性好但效率略低。\n\n【Intel推荐】\n3.qsv：Intel通用模式，自动适配格式并直通显存。\n\n【手动指定】\n仅在全自动失败时使用。HEVC即H.265，AV1需新显卡支持。",
            offset_x=0, offset_y=0, wraplength=500)
        self.hwaccel_decoder = tk.StringVar(value="无")
        self.decoder_combo = ttk.Combobox(hw_frame, textvariable=self.hwaccel_decoder,
                                          values=HARDWARE_DECODER_OPTIONS,
                                          state="readonly", width=22)
        self.decoder_combo.pack(side=tk.LEFT, padx=5)
        self.decoder_combo.bind("<<ComboboxSelected>>", lambda e: self._trigger_update())

        # 自定义参数
        custom_frame = ttk.Frame(self)
        custom_frame.pack(fill=tk.X, pady=5)

        label = ttk.Label(custom_frame, text="自定义FFmpeg参数 (追加到命令末尾，会覆盖界面生成的对应设置):")
        label.pack(anchor=tk.W)
        ToolTip(label, 
                "可直接添加 FFmpeg 命令行参数，它们会追加到命令末尾。\n\n"
                "【注意】\n"
                "• 如果添加了 -vf / -filter_complex / -af / -map 等，会覆盖界面生成的对应设置（滤镜、音频滤镜、流映射）。\n"
                "  如需保留界面生成的滤镜链，请在自定义参数中复制完整的 -vf 链（可从预览区复制）并扩展。\n\n"
                "• 界面上已单独提供的参数（如 tune、profile、level、maxrate、bufsize）请勿重复添加，以免冲突。\n\n"
                "• 追加自定义 -t 时间 可作为应急措施，强制限制输出时长，防止因滤镜循环或参数不当导致输出无限延长（主水印模式）。\n"
                "   或者手动 -t 10 输出10秒片段查看结果，程序的预览命令功能不一定传递了所有滤镜，特别是水印只有占位框。\n\n"
                "• 新手建议：仅添加界面未提供的高级选项（如 -x264-params、-bsf 等），避免覆盖关键设置。\n"
                "• 参数 setsar=1 强制覆盖 SAR 比例1:1，配合正方形缩放：比如400x400 可以正确压缩 16:9 画面",
                wraplength=800)
        self.custom_args = tk.StringVar(value="")
        self.custom_entry = ttk.Entry(custom_frame, textvariable=self.custom_args, width=50)
        self.custom_entry.pack(fill=tk.X, pady=2)
        self.custom_args.trace_add("write", lambda *a: self._trigger_update())

        # ---- 水印文件选择与设置 ----
        wm_frame = ttk.Frame(self)
        wm_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(wm_frame, text="水印文件 (图片/视频):").pack(side=tk.LEFT, padx=(0,5))
        
        self.wm_path_var = tk.StringVar(value=self.watermark_dict.get("file_path", ""))
        wm_entry = ttk.Entry(wm_frame, textvariable=self.wm_path_var, width=40)
        wm_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        def browse_wm():
            path = filedialog.askopenfilename(title="选择水印文件", filetypes=[("媒体", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.mp4 *.mkv *.avi *.mov")])
            if path:
                self.wm_path_var.set(normalize_path(path))
        ttk.Button(wm_frame, text="浏览", command=browse_wm, width=6).pack(side=tk.LEFT, padx=2)

        def clear_wm():
            self.wm_path_var.set("")
        ttk.Button(wm_frame, text="清除", command=clear_wm, width=6).pack(side=tk.LEFT, padx=2)
        

        self.adaptive_var = tk.BooleanVar(value=self.watermark_dict.get("adaptive", False))
        chk_adaptive = ttk.Checkbutton(wm_frame, text="自适应", variable=self.adaptive_var)
        chk_adaptive.pack(side=tk.LEFT, padx=5)
        ToolTip(
            chk_adaptive,
            "勾选后，水印的大小和位置会根据当前模板里*水印和载入视频*的比例为基准。\n\n"
            "自动在新添加视频命令里缩放大小和调整边距。\n\n"
            "取消勾选则保持原始像素值，不进行任何缩放。\n\n"
            "**单个任务编辑框里勾选取消是更改当前任务(主界面要有基准)**",
            wraplength=600
        )
            
        def update_adaptive(*args):
            self.watermark_dict["adaptive"] = self.adaptive_var.get()
            if self.update_callback:
                self.update_callback()
        self.adaptive_var.trace_add("write", update_adaptive)
        
        # ---- 水印设置按钮 ----
        self.watermark_btn = ttk.Button(wm_frame, text="水印叠加设置", command=self.open_watermark_editor)
        self.watermark_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(
            self.watermark_btn,
            "打开独立窗口配置水印（支持缩放、裁剪、旋转、绿幕抠像、透明度、位置调整等）。\n\n"
            "注意：\n"
            "• 水印会叠加在主视频之上，水印自身的音频将被忽略。\n"
            "• 水印不支持变速功能（为避免时长计算混乱），如需变速请先单独预处理水印文件。\n"
            "• 循环控制通过启用截取并设置循环次数实现，可用于视频水印的重复播放。\n"
            "• 勾选「自适应」可根据主视频尺寸自动缩放水印大小和位置。\n"
            "• 此变速限制同样适用于画中画（子视频）模式，若子视频需变速，请先预处理。",
            wraplength=500
        )
        
        # 保留探测时长按钮和时长标签变量（隐藏），以免其他代码引用报错
        self.wm_duration_label = ttk.Label(wm_frame, text="", foreground="gray")
        # 不pack，即不显示
        
        # 绑定路径变化更新
        self.wm_path_var.trace_add("write", lambda *a: self._on_wm_path_changed())

        # ---- 水印预设管理 ----
        preset_row = ttk.Frame(self)
        preset_row.pack(fill=tk.X, pady=2)
        
        ttk.Label(preset_row, text="水印预设:").pack(side=tk.LEFT, padx=(0,5))
        self.wm_preset_combo = ttk.Combobox(
            preset_row,
            textvariable=self.wm_preset_var,
            state="readonly",
            width=20
        )
        self.wm_preset_combo.pack(side=tk.LEFT, padx=2)
        # 绑定选择事件
        self.wm_preset_combo.bind("<<ComboboxSelected>>", lambda e: self.load_wm_preset())
        
        ttk.Button(preset_row, text="保存模板", command=self.save_wm_preset).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_row, text="删除模板", command=self.delete_wm_preset).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_row, text="加载模板", command=self.load_wm_preset).pack(side=tk.LEFT, padx=2)
        
        # 刷新下拉列表
        self._refresh_wm_preset_list()



    def _on_wm_path_changed(self, *args):
        path = self.wm_path_var.get().strip()
        self.watermark_dict["file_path"] = path
        self.watermark_dict["enabled"] = bool(path)
        if not path:
            # 水印被清除，重置提示标志
            self.app._watermark_precise_hint_shown = False
        self._auto_detect_watermark_duration()
        if self.update_callback:
            self.update_callback()
    
    def _auto_detect_watermark_duration(self):
        path = self.wm_path_var.get().strip()
        if not path or not os.path.exists(path):
            self.watermark_dict["duration"] = None
            return
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'):
            self.watermark_dict["duration"] = None
            return
        duration = self.app._get_media_duration(path)
        self.watermark_dict["duration"] = duration if duration is not None else None




    def _on_hw_toggle(self):
        if self.hwaccel_enabled.get() and self.hwaccel_decoder.get() == "无":
            self.hwaccel_decoder.set("auto (自动通用)")
        self._trigger_update()

    def _trigger_update(self):
        if self.update_callback:
            self.update_callback()

    def open_watermark_editor(self):
        """打开水印参数编辑窗口，使用正确的尺寸计算顺序"""
        if self.app is None:
            return
        file_path = self.watermark_dict.get("file_path", "")
        if not file_path or not os.path.exists(file_path):
            messagebox.showwarning("提示", "请先选择一个有效的水印文件")
            return
    
        # 获取主界面当前完整设置（包含裁剪、旋转、缩放等）
        main_file = self.app.input_file.get().strip()
        main_video_size = None
        if main_file and os.path.exists(main_file):
            main_settings = self.app.get_current_settings()
            # 直接获取原始尺寸（不含任何旋转）
            orig_w, orig_h = get_video_dimensions(self.app.ffprobe_cmd, main_file)
            if orig_w is not None and orig_h is not None:
                # 使用新函数按实际顺序计算最终尺寸
                main_w, main_h = self.app.compute_final_size_with_order(orig_w, orig_h, main_settings)
                if main_w > 0 and main_h > 0:
                    main_video_size = (main_w, main_h)
    
        self.app.edit_video_settings(
            title="水印参数编辑",
            initial_settings=self.watermark_dict.copy(),
            on_save=lambda new: self._on_watermark_saved(new),
            file_path=file_path,
            is_watermark=True,
            track_idx=None,
            pip_enabled_var=None,
            overlay_mode='sub',
            parent=self,
            track_obj=None,
            main_video_size=main_video_size  # 传入正确的最终尺寸
        )
    
    def _on_watermark_saved(self, new_settings):
        self.watermark_dict.update(new_settings)
        self.wm_path_var.set(self.watermark_dict.get("file_path", ""))
        self._auto_detect_watermark_duration()
        if self.update_callback:
            self.update_callback()


    def _get_wm_templates_path(self):
        return self.wm_preset_file
    
    def _load_wm_templates(self):
        """从 JSON 文件加载所有水印模板"""
        if os.path.exists(self.wm_preset_file):
            try:
                with open(self.wm_preset_file, 'r', encoding='utf-8') as f:
                    self.wm_templates = json.load(f)
                if not isinstance(self.wm_templates, dict):
                    self.wm_templates = {}
            except:
                self.wm_templates = {}
        else:
            self.wm_templates = {}
    
    def _save_wm_templates(self):
        """将模板字典保存到 JSON 文件"""
        try:
            with open(self.wm_preset_file, 'w', encoding='utf-8') as f:
                json.dump(self.wm_templates, f, indent=4, ensure_ascii=False)
        except Exception as e:
            messagebox.showerror("保存失败", f"无法保存水印模板: {e}")
    
    def _refresh_wm_preset_list(self):
        """刷新下拉框列表"""
        self._load_wm_templates()
        names = list(self.wm_templates.keys())
        self.wm_preset_combo['values'] = names
        if names:
            self.wm_preset_var.set(names[0])  # 默认选中第一个
        else:
            self.wm_preset_var.set("")

    def save_wm_preset(self):
        """保存当前水印设置为一个新模板"""
        # 获取当前水印设置（深拷贝，避免引用问题）
        current = copy.deepcopy(self.watermark_dict)
        # 移除 file_path，避免路径失效
        current.pop("file_path", None)
        # 移除可能存在的基准尺寸，因为模板不应该绑定特定视频尺寸
        current.pop("base_width", None)
        current.pop("base_height", None)
        
        # 弹出对话框输入模板名称
        name = simpledialog.askstring("保存水印模板", "请输入模板名称:", parent=self)
        if not name:
            return
        
        # 如果已存在同名，询问是否覆盖
        if name in self.wm_templates:
            if not messagebox.askyesno("覆盖确认", f'模板 "{name}" 已存在，是否覆盖？'):
                return
        
        # 保存
        self.wm_templates[name] = current
        self._save_wm_templates()
        self._refresh_wm_preset_list()
        self.app._append_info_ui(f"✅ 水印模板 '{name}' 已保存")
        messagebox.showinfo("成功", f'水印模板 "{name}" 已保存')
    
    def load_wm_preset(self):
        """加载选中的模板到当前水印设置"""
        name = self.wm_preset_var.get()
        if not name:
            messagebox.showinfo("提示", "请先选择一个水印模板")
            return
        
        if name not in self.wm_templates:
            messagebox.showerror("错误", f'模板 "{name}" 不存在')
            return
        
        template = self.wm_templates[name]
        # 更新当前水印设置（保留 file_path，避免覆盖已有文件路径）
        # 但也要注意：如果模板中不包含 file_path，则保留当前文件路径
        # 如果模板中包含 file_path，则使用模板的（但我们已经移除了，所以这里不会覆盖）
        for key, value in template.items():
            self.watermark_dict[key] = value
        # 同步界面控件
        self.wm_path_var.set(self.watermark_dict.get("file_path", ""))
        if hasattr(self, 'adaptive_var'):
            self.adaptive_var.set(self.watermark_dict.get("adaptive", False))
        # 如果有其他界面控件需要同步，例如缩放、裁剪、绿幕等，需要进一步更新
        # 但因为我们当前的水印设置界面只有文件路径、自适应、以及叠加设置按钮（打开独立编辑器）
        # 所以只需更新路径和自适应，其他参数在编辑器中打开时会加载
        # 为了完整，我们可以触发更新回调
        if self.update_callback:
            self.update_callback()
        self.app._append_info_ui(f"✅ 已加载水印模板 '{name}'")
        messagebox.showinfo("成功", f'水印模板 "{name}" 已加载')
    
    def delete_wm_preset(self):
        """删除选中的模板"""
        name = self.wm_preset_var.get()
        if not name:
            messagebox.showinfo("提示", "请先选择一个水印模板")
            return
        if not messagebox.askyesno("确认删除", f'确定要删除水印模板 "{name}" 吗？'):
            return
        if name in self.wm_templates:
            del self.wm_templates[name]
            self._save_wm_templates()
            self._refresh_wm_preset_list()
            self.app._append_info_ui(f"🗑️ 已删除水印模板 '{name}'")
            messagebox.showinfo("成功", f'水印模板 "{name}" 已删除')
        else:
            messagebox.showerror("错误", f'模板 "{name}" 不存在')


    def get_settings(self):
        return {
            "hwaccel_enabled": self.hwaccel_enabled.get(),
            "hwaccel_decoder": self.hwaccel_decoder.get(),
            "custom_args": self.custom_args.get()
        }

    def set_settings(self, settings):
        self.hwaccel_enabled.set(settings.get("hwaccel_enabled", False))
        self.hwaccel_decoder.set(settings.get("hwaccel_decoder", "无"))
        self.custom_args.set(settings.get("custom_args", ""))
        if hasattr(self, 'adaptive_var'):
            self.adaptive_var.set(self.watermark_dict.get("adaptive", False))
        self._on_hw_toggle()




class Task:
    def __init__(self, input_path, output_path, settings, cmd_list):
        self.input = input_path
        self.output = output_path
        self.settings = copy.deepcopy(settings)
        self.cmd = cmd_list
        self.status = "等待"
        self.error_msg = ""
        self.progress = 0
        self.current_sec = 0
        self.total_sec = 0
        self._task_list_update_after = None   # 任务列表刷新去抖 ID
        self.stopped_by_user = False
        self.is_custom = False

    def get_short_cmd(self):
        """生成简短显示命令（隐藏路径细节）"""
        if not self.cmd:
            return ""
        full_cmd = format_cmd_for_display(self.cmd)
        in_quoted = re.escape(self.input)
        out_quoted = re.escape(self.output)
        short = re.sub(rf'(["\']?){in_quoted}\1', r'{input}', full_cmd)
        short = re.sub(rf'(["\']?){out_quoted}\1', r'{output}', short)
        return short




# ================== Track 类 ==================
class Track:
    def __init__(self, index, typ, codec, file_path, enabled=True, enc_settings=None):
        self.index = index
        self.type = typ
        self.codec = codec
        self.file_path = file_path
        self.enabled = enabled
        # 字幕专用字段
        self.language = ""
        self.title = ""
        
        if enc_settings is None:
            if typ == "video":
                # 初始化视频轨道的 enc_settings 和属性（兼容旧代码）
                self.overlay_enabled = False
                self.overlay_x = "W-w-10"
                self.overlay_y = "H-h-10"
                self.pad_enabled = False
                self.pad_width = ""
                self.pad_height = ""
                self.offset_x = "0"
                self.offset_y = "0"
                self.enc_settings = {
                    "encoder": "copy",
                    "rate_control_type": "crf", "crf_value": 26, "cq_value": 35,
                    "global_quality": 26, "bitrate_video": "1900k",
                    "frame_rate_type": "keep", "frame_rate_custom": "30",
                    "scale_enabled": False, "scale_width": "", "scale_height": "", "scale_method": "width",
                    "crop_enabled": False, "crop_left": "0", "crop_top": "0", "crop_width": "iw/2", "crop_height": "ih",
                    "rotate": "none", "vflip": False, "hflip": False,
                    "speed_enabled": False, "speed_factor": "1.0", "deinterlace_filter": "none",
                    "pix_fmt_enabled": True, "pix_fmt": "yuv420p",
                    "subtitle_enabled": False, "subtitle_path": "",
                    # 新增的叠加/偏移/循环/绿幕字段（默认值）
                    "overlay_enabled": False,
                    "overlay_x": "W-w-10",
                    "overlay_y": "H-h-10",
                    "pad_enabled": False,
                    "pad_width": "",
                    "pad_height": "",
                    "offset_x": "0",
                    "offset_y": "0",
                    "loop_enabled": False,
                    "loop_mode": "infinite",
                    "loop_count": 3,
                    "chroma_enabled": False,
                    "chroma_color": "#3fff08",
                    "chroma_similarity": 0.3,
                    "chroma_blend": 0.1,
                    "alpha_enabled": False,
                    "chroma_filter_type": "chromakey",   # 默认 chromakey
                    "alpha_value": 1.0,
                    "audio_source_type": "self",      # "self" | "silence" | "external"
                    "external_audio_path": "",
                    "external_audio_stream": "0:a:0",
                    "enhance": {
                        "denoise_enabled": False,
                        "denoise_spatial": 4.0,
                        "denoise_temporal": 3.0,
                        "sharpen_enabled": False,
                        "sharpen_strength": 1.0,
                        "ivtc_enabled": False,
                        "deblock_enabled": False,
                        "deblock_strength": 4,
                        "colorspace_enabled": False,
                        "colorspace_matrix": "bt709:bt2020",
                    }
                }
            elif typ == "audio":
                self.enc_settings = {
                    "encoder": "copy",
                    "bitrate": "128k",
                    "samplerate": "44100",
                    "trim_enabled": False,
                    "trim_start": "",
                    "trim_end": "",
                    "precise_trim": False,
                    "mix_enabled": False,
                    "volume": 1.0,
                }
            else:  # subtitle
                self.enc_settings = {"encoder": "copy"}
        else:
            self.enc_settings = copy.deepcopy(enc_settings)
            # 读取字幕元数据
            self.language = self.enc_settings.get("language", "")
            self.title = self.enc_settings.get("title", "")

            # 对于视频，从 enc_settings 恢复属性（兼容旧代码）
            if typ == "video":
                self.overlay_enabled = self.enc_settings.get("overlay_enabled", False)
                self.overlay_x = self.enc_settings.get("overlay_x", "W-w-10")
                self.overlay_y = self.enc_settings.get("overlay_y", "H-h-10")
                self.pad_enabled = self.enc_settings.get("pad_enabled", False)
                self.pad_width = self.enc_settings.get("pad_width", "")
                self.pad_height = self.enc_settings.get("pad_height", "")
                self.offset_x = self.enc_settings.get("offset_x", "0")
                self.offset_y = self.enc_settings.get("offset_y", "0")
            # 注意：音频轨道没有额外的叠加属性

    def is_encoding(self):
        return self.enc_settings.get("encoder") != "copy"

# ================== 主界面类 ==================
class FFmpegBatchGUI:
    # ---------- SafeToplevel 上下文管理器 ----------
    class SafeToplevel:
        """安全的 Toplevel 上下文管理器，确保异常时销毁窗口并释放 grab"""
        def __init__(self, master, **kwargs):
            self.master = master
            self.kwargs = kwargs
            self.window = None

        def __enter__(self):
            self.window = tk.Toplevel(self.master, **self.kwargs)
            self.window.withdraw()  # 先隐藏
            if self.master and self.master.winfo_exists():
                self.window.transient(self.master)
            self.window.grab_set()
            return self.window

        def __exit__(self, exc_type, exc_val, exc_tb):
            # 无论销毁是否成功，都要释放 grab
            try:
                if self.window and self.window.winfo_exists():
                    self.window.destroy()
            except Exception:
                # 忽略销毁过程中的异常，继续清理
                pass
            finally:
                if self.master:
                    try:
                        self.master.grab_release()
                    except Exception:
                        # 忽略 grab 释放时的异常（如主窗口已销毁）
                        pass


    
    # ================== 语言映射 ==================
    # ISO 639-2/B 标准三字母码映射表（短码 → 标准码）
    LANGUAGE_MAP = {
        # 中文
        "zh": "chi", "zho": "chi", "chi": "chi",
        "cn": "chi", "chs": "chi", "cht": "chi",
        # 英语
        "en": "eng", "eng": "eng", "en-us": "eng", "en-gb": "eng",
        # 日语
        "ja": "jpn", "jp": "jpn", "jpn": "jpn",
        # 韩语
        "ko": "kor", "kr": "kor", "kor": "kor",
        # 法语
        "fr": "fre", "fra": "fre", "fre": "fre",
        # 德语
        "de": "ger", "deu": "ger", "ger": "ger",
        # 西班牙语
        "es": "spa", "spa": "spa",
        # 意大利语
        "it": "ita", "ita": "ita",
        # 葡萄牙语
        "pt": "por", "por": "por",
        # 俄语
        "ru": "rus", "rus": "rus",
        # 阿拉伯语
        "ar": "ara", "ara": "ara",
        # 印地语
        "hi": "hin", "hin": "hin",
        # 泰语
        "th": "tha", "tha": "tha",
        # 越南语
        "vi": "vie", "vie": "vie",
        # 印尼语
        "id": "ind", "ind": "ind",
        # 马来语
        "ms": "may", "may": "may", "msa": "may",
        # 他加禄语/菲律宾语
        "tl": "tgl", "tgl": "tgl", "fil": "fil",
        "nan": "chi",
        # 其他常用
        "nl": "dut", "nld": "dut", "dut": "dut",
        "sv": "swe", "swe": "swe",
        "da": "dan", "dan": "dan",
        "fi": "fin", "fin": "fin",
        "no": "nor", "nor": "nor",
        "pl": "pol", "pol": "pol",
        "tr": "tur", "tur": "tur",
        "cs": "cze", "ces": "cze", "cze": "cze",
        "hu": "hun", "hun": "hun",
        "ro": "rum", "ron": "rum", "rum": "rum",
        "el": "gre", "ell": "gre", "gre": "gre",
        "he": "heb", "heb": "heb",
        "uk": "ukr", "ukr": "ukr",
        "und": "und",
    }
    
    # 常用语言下拉列表（显示名, ISO码）
    COMMON_LANGUAGES = [
        ("粤语 (yue)",        "yue"),
        ("普通话 (cmn)",      "cmn"),
        ("中文 (chi)",        "chi"),
        ("英语 (eng)",        "eng"),
        ("日语 (jpn)",        "jpn"),
        ("韩语 (kor)",        "kor"),
        ("法语 (fre)",        "fre"),
        ("德语 (ger)",        "ger"),
        ("西班牙语 (spa)",    "spa"),
        ("意大利语 (ita)",    "ita"),
        ("葡萄牙语 (por)",    "por"),
        ("俄语 (rus)",        "rus"),
        ("阿拉伯语 (ara)",    "ara"),
        ("印地语 (hin)",      "hin"),
        ("泰语 (tha)",        "tha"),
        ("越南语 (vie)",      "vie"),
        ("印尼语 (ind)",      "ind"),
        ("马来语 (may)",      "may"),
        ("荷兰语 (dut)",      "dut"),
        ("瑞典语 (swe)",      "swe"),
        ("波兰语 (pol)",      "pol"),
        ("土耳其语 (tur)",    "tur"),
        ("泰米尔语 (tam)",    "tam"),
        ("未指定 (und)",      "und"),
    ]






    def __init__(self, root):
        self.root = root
        self.root.withdraw()
        self.root.title("FFmpeg 多功能工具")
        self._set_window_icon()
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        self.scaling = get_dpi_scaling(root)

        base_width = 1420
        base_height = 900
        width = min(base_width, int(screen_width * 0.95))
        height = min(base_height, int(screen_height * 0.95))
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        root.geometry(f"{width}x{height}+{x}+{y}")

        # 查找 FFmpeg 工具
        self.ffmpeg_cmd = find_executable("ffmpeg.exe") or find_executable("ffmpeg")
        self.ffplay_cmd = find_executable("ffplay.exe") or find_executable("ffplay")
        self.ffprobe_cmd = find_executable("ffprobe.exe") or find_executable("ffprobe")

        # 自定义 FFmpeg 目录设置
        self.ffmpeg_dir_enabled = tk.BooleanVar(value=False)
        self.ffmpeg_dir_path = tk.StringVar(value="")
        # 初始化路径（需在 load_player_settings 之前调用）
        self._update_ffmpeg_paths()


        # 基本变量
        self.input_file = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.output_suffix = tk.StringVar(value="")
        self.custom_output_name = tk.StringVar(value="")
        self.output_container = tk.StringVar(value="mp4")
        
        self.log_enabled_var = tk.BooleanVar(value=True)
        default_log_path = normalize_path(os.path.join(get_script_dir(), "editlog.txt"))
        self.log_path_var = tk.StringVar(value=default_log_path)

        self.tasks = []
        self.is_processing = False
        self.stop_flag = False
        self.pending_tasks = []
        self.running_futures = set()
        self.executor = None

        self.current_hw_encoding_count = 0
        self.max_hw_parallel = tk.IntVar(value=2)

        # 合并模块变量
        self.merge_video = tk.StringVar()
        self.merge_tracks = []
        self.merge_container = tk.StringVar(value="mkv")
        self.merge_output = tk.StringVar()
        self.merge_delete_source = tk.BooleanVar(value=False)
        self.merge_verify = tk.BooleanVar(value=True)

        self.copy_chapters = tk.BooleanVar(value=True)
        self.chapter_file = tk.StringVar(value="")

        self.use_mpv = tk.BooleanVar(value=False)
        self.mpv_path = tk.StringVar(value="mpv")
        
        self.overwrite_policy = tk.StringVar(value='ask')    # 可选值: 'ask', 'rename', 'overwrite'
        self._loading_preset = False      # 加载预设标志
        self._updating_preview = False    # 防重入锁标志
        self._batch_update = False        # 批量更新模式标志，用于抑制多次预览刷新
        self._trim_precise_hint_shown = False
        self._watermark_precise_hint_shown = False
        self._preview_after_id = None   # after 回调 ID
        self._preview_pending = False   # 是否有待处理的刷新
        self._pip_reverse_audio_hint_shown = False
        self.pix_fmt_enabled_default = tk.BooleanVar(value=True)
        

        self.preview_editable_var = tk.BooleanVar(value=False)



        self.extract_custom_dir = tk.BooleanVar(value=False)   # 流提取 是否启用自定义输出目录
        self.extract_output_dir = tk.StringVar(value="")       # 流提取 自定义输出目录路径
        self.current_preview_file = None
        self.auto_match_subtitle_ext = tk.BooleanVar(value=True)
        self.auto_match_audio_ext = tk.BooleanVar(value=True)
        self.extract_keep_chapters = tk.BooleanVar(value=True)
        self.extract_clear_metadata = tk.BooleanVar(value=False)
        self.extract_file_list = []
        self._suppress_save = False

        self._stream_info_cache = {}
        self._suppress_main_video_trace = False
        
        self._concat_params_cache = {}
        
        self._merge_preview_after_id = None   # 合并命令预览防抖 ID


        # ffprobe 并发数量计算
        cpu_count = os.cpu_count() or 4
        if cpu_count <= 16:
            default_parallel = max(1, cpu_count - 4)
        else:
            default_parallel = 16
        self.ffprobe_parallel = tk.IntVar(value=default_parallel)

        # 流提取相关
        self.extract_parser_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.ffprobe_parallel.get()
        )


        self._running_tasks = []  # 存储 (proc, task)
        
        self.cmd_output_path = tk.StringVar(value="")

        self._duration_cache = {}
        self._dimension_cache = {}




        self._proc_lock = threading.Lock()
        self.running_procs = []  # 存储当前正在运行的 FFmpeg 进程对象（subprocess.Popen）

        self.segment_enabled = tk.BooleanVar(value=False)
        self.segments = []

        # ---------- 水印设置 ----------
        self.watermark_settings = {
            "enabled": False,
            "file_path": "",
            "loop_enabled": False,
            "loop_mode": "infinite",
            "loop_count": 3,
            "encoder": "libx264",
            "preset": "medium",
            "rate_control_type": "crf",
            "crf_value": 25,
            "cq_value": 28,
            "global_quality": 23,
            "bitrate_video": "2000k",
            "scale_enabled": False,
            "scale_width": "",
            "scale_height": "",
            "scale_method": "width",
            "crop_enabled": False,
            "crop_left": "0",
            "crop_top": "0",
            "crop_width": "iw/2",
            "crop_height": "ih",
            "rotate": "none",
            "vflip": False,
            "hflip": False,
            "deinterlace_filter": "none",
            "pix_fmt_enabled": True,
            "pix_fmt": "yuv420p",
            "trim_enabled": False,
            "trim_start": "",
            "trim_end": "",
            "chroma_enabled": False,
            "chroma_color": "#3fff08",
            "chroma_similarity": 0.3,
            "chroma_blend": 0.1,
            "overlay_enabled": True,
            "overlay_x": "W-w-10",
            "overlay_y": "H-h-10",
            "pad_enabled": False,
            "pad_width": "",
            "pad_height": "",
            "offset_x": "0",
            "offset_y": "0",
            "alpha_enabled": False,
            "alpha_value": 1.0,
            "adaptive": False,
        }
        # ---------------------------------

        # 预设管理
        local_preset = os.path.join(get_script_dir(), "ffmpeg_presets.json")
        if os.path.exists(local_preset):
            self.preset_file_path = local_preset
        else:
            user_dir = os.path.join(os.path.expanduser("~"), ".FFLiteGUI")
            os.makedirs(user_dir, exist_ok=True)
            self.preset_file_path = os.path.join(user_dir, "ffmpeg_presets.json")
        self.preset_manager = PresetManager(self.preset_file_path)

        self._loading_settings = True
        self.load_player_settings()
        self._loading_settings = False

        # ---------- 加载快速命令模板 ----------
        preset_dir = os.path.dirname(self.preset_file_path)          # 主预设所在目录
        self.cmd_templates_path = os.path.join(preset_dir, "quick_cmds.json")
        self.cmd_templates = {}
        self._load_cmd_templates()
        
        self._initialized = False   # 标记 UI 已创建但未完成文件加载

        # 创建界面组件
        self.create_widgets()
        
        self.default_settings = self.get_current_settings()

        # 启动后台初始化（文件释放和加载）
        self.root.after(100, self._delayed_init)   # 延迟 100ms 让窗口先显示



        # 处理命令行参数（支持从资源管理器“发送到”打开文件）
        if len(sys.argv) > 1:
            # 取第一个非脚本参数作为文件路径
            file_path = sys.argv[1]
            if os.path.exists(file_path):
                self.input_file.set(normalize_path(file_path))
                if not self.output_dir.get():
                    self.output_dir.set(os.path.dirname(file_path))
                self._append_info_ui(f"已从命令行加载文件: {os.path.basename(file_path)}")
                self.update_command_preview()
            else:
                self._append_info_ui(f"命令行参数文件不存在: {file_path}")

        self.update_task_list()
        self.update_command_preview()

        # 拖拽支持
        if DND_AVAILABLE:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self.on_files_dropped)

        self.show_quick_warning()

        self.root.update_idletasks()
        self.root.deiconify()



    def _delayed_init(self):
        """在后台线程中释放预设文件和命令模板，避免阻塞 UI"""
        def worker():
            # 1. 确保预设文件存在
            if not os.path.exists(self.preset_file_path):
                self.preset_manager._ensure_default_preset()
            
            # 2. 确保快速命令模板文件存在且有效
            if not os.path.exists(self.cmd_templates_path):
                # 文件不存在，创建默认模板
                self.cmd_templates = self._get_default_cmd_templates()
                self._save_cmd_templates()
            else:
                # 文件存在，尝试加载
                self._load_cmd_templates()
                # 如果加载后为空（可能文件损坏），则重建
                if not self.cmd_templates:
                    self._append_info_ui("快速命令模板文件损坏或为空，将重建默认模板")
                    self.cmd_templates = self._get_default_cmd_templates()
                    self._save_cmd_templates()
                    self._load_cmd_templates()  # 重新加载
            
            # 3. 回到主线程更新 UI
            self.root.after(0, self._finish_delayed_init)
        
        threading.Thread(target=worker, daemon=True).start()
    
    def _finish_delayed_init(self):
        """延迟初始化完成后的 UI 更新"""
        self.load_preset_list()
        self._refresh_cmd_preset_list()
        self.update_player_status()      # 延迟显示状态检测信息
        self._initialized = True
#        self._append_info_ui("预设和快速命令模板已就绪")


    def _ensure_main_video(self, disable_scale=False):
        """确保 self.merge_video 已设置：若未设置，则从列表中取第一个启用的视频轨道。
        如果 disable_scale=True，则将该视频轨道的缩放禁用（仅当自动设置时）。
        """
        if not self.merge_video.get().strip():
            enabled_videos = [t for t in self.merge_tracks if t.enabled and t.type == "video"]
            if enabled_videos:
                # 临时禁用 trace，避免触发 merge_load_video_info
                self._suppress_main_video_trace = True
                self.merge_video.set(enabled_videos[0].file_path)
                self._suppress_main_video_trace = False
    
                if disable_scale:
                    # 禁用主视频的缩放
                    main_track = enabled_videos[0]
                    main_track.enc_settings["scale_enabled"] = False
             #       main_track.enc_settings["scale_width"] = ""
             #       main_track.enc_settings["scale_height"] = ""
                    # 刷新列表，显示变化
                    self.merge_update_track_list()
    
                self._append_info_ui(f"[自动] 主视频未设置，自动设为: {os.path.basename(enabled_videos[0].file_path)}")
                return True
            else:
                self.merge_video.set("")
                return False
        return True


    def _set_window_icon(self):
        icon_path = find_resource("35.ico")
        if icon_path:
            try:
                self.root.iconbitmap(default=icon_path)
                print(f"窗口图标加载成功: {icon_path}")
                return
            except Exception as e:
                print(f"加载图标失败 {icon_path}: {e}")
        else:
            print("未找到窗口图标文件 35.ico")

    # 流提取相关
    def add_custom_task(self, input_path: str, output_path: str, cmd_list: List[str], settings: dict = None):
        """
        直接添加自定义命令的任务（跳过命令生成逻辑）。
        input_path, output_path 仅用于显示和冲突检测。
        """
        if settings is None:
            settings = {}
        # 处理冲突，获得最终路径
        final_output = self._resolve_path_conflict(output_path, show_dialog=True)
        if final_output is None:
            return False
        # 更新命令列表中的输出路径（假设输出文件是最后一个参数）
        if cmd_list and cmd_list[-1] == output_path:
            cmd_list[-1] = final_output
        else:
            # 更安全的做法：若最后一个参数不是原输出路径，则尝试替换所有匹配项
            # 但通常最后一个就是输出，这里做兼容处理
            for i, arg in enumerate(cmd_list):
                if arg == output_path:
                    cmd_list[i] = final_output
                    break
            else:
                # 如果没找到，直接追加到最后？但可能破坏命令结构，此处警告
                self._append_info_ui(f"警告：未在命令中找到输出路径 {output_path}，已忽略路径更新")
        task = Task(input_path, final_output, settings, cmd_list)
        task.is_custom = True
        self.tasks.append(task)
        self.update_task_list()
        self._append_info_ui(f"✅ 已添加提取任务: {os.path.basename(input_path)} -> {final_output}")
        return True


    def update_progress(self, current=0, total=0, task=None, log_progress=True):
        """
        更新转码进度。
        - task: 队列任务对象（用于更新任务列表）
        - log_progress: 是否在日志中输出进度（单文件/合并使用）
        """
        # 重置
        if total == 0:
            if task is not None:
                task.progress = 0
                self._schedule_task_list_update()
            if log_progress:
#                self._update_log_progress("转码结束")
#            self.root.title("FFmpeg 多功能工具")
                pass   #  上面2句注释空了 所以需要pass占位
            self._last_logged_percent = -1
            return
    
        percent = int(100 * current / total)
    
        # 更新任务列表（队列任务）
        if task is not None:
            task.progress = percent
            task.current_sec = current
            task.total_sec = total
            self._schedule_task_list_update()
    
        # 更新日志和标题（单文件/合并）
        if log_progress:
            # 每5%更新一次（0%, 5%, 10%, ... 100%）
            if not hasattr(self, '_last_logged_percent'):
                self._last_logged_percent = -1
            if percent == 0 or percent == 100 or (percent - self._last_logged_percent >= 5):
                self._last_logged_percent = percent
#                self.root.title(f"FFmpeg 多功能工具 - 转码中 {percent}%")
                self._update_log_progress(f"{percent}% ({current}/{total} 秒)")
    
    def _schedule_task_list_update(self):
        """去抖刷新任务列表"""
        if hasattr(self, '_task_list_update_after') and self._task_list_update_after is not None:
            self.root.after_cancel(self._task_list_update_after)
        self._task_list_update_after = self.root.after(100, self._update_task_list_ui_safe)
    
    def _update_task_list_ui_safe(self):
        """安全刷新任务列表"""
        self._task_list_update_after = None
        self.update_task_list()
    
    def _update_log_progress(self, text):
        """更新日志进度行（替换最后一行）"""
        info = self.info_text
        try:
            last_line_start = info.index("end-2l linestart")
            last_line = info.get(last_line_start, "end-1c")
            if "[进度]" in last_line:
                info.delete(last_line_start, "end-1c")
        except:
            pass
        info.insert(tk.END, f"[进度] {text}\n")
        info.see(tk.END)

    


    # 过滤转换日志的无用信息
    @staticmethod
    def _is_ffmpeg_banner_line(line: str) -> bool:
        """判断是否为 FFmpeg 启动时的编译信息行，应被忽略"""
        line = line.strip()
#         if line.startswith("ffmpeg version"):
#             return True
        if line.startswith("built with"):
            return True
        if line.startswith("configuration:"):
            return True
        if line.startswith(("libav", "libsw", "libpostproc")):
            return True
        if "Press [q] to stop" in line:
            return True
        return False

    def _update_ffmpeg_paths(self):
        """根据自定义目录设置更新 ffmpeg/ffprobe/ffplay 路径，并统一斜杠"""
        if self.ffmpeg_dir_enabled.get() and self.ffmpeg_dir_path.get().strip():
            base_dir = normalize_path(self.ffmpeg_dir_path.get().strip())
            ext = ".exe" if sys.platform == "win32" else ""
            ffmpeg = normalize_path(os.path.join(base_dir, f"ffmpeg{ext}"))
            ffprobe = normalize_path(os.path.join(base_dir, f"ffprobe{ext}"))
            ffplay = normalize_path(os.path.join(base_dir, f"ffplay{ext}"))
            if os.path.exists(ffmpeg):
                self.ffmpeg_cmd = ffmpeg
                self.ffprobe_cmd = ffprobe if os.path.exists(ffprobe) else None
                self.ffplay_cmd = ffplay if os.path.exists(ffplay) else None
                if not self.ffprobe_cmd:
                    self._append_info_ui("警告：指定 FFmpeg 目录下未找到 ffprobe，部分功能可能受限")
                if not self.ffplay_cmd:
                    self._append_info_ui("警告：指定 FFmpeg 目录下未找到 ffplay，预览功能可能受限")
                return
            else:
                self._append_info_ui("警告：指定 FFmpeg 目录下未找到 ffmpeg，将使用系统 PATH 中的版本")
        # 回退到系统 PATH，并规范化路径
        ffmpeg = find_executable("ffmpeg.exe") or find_executable("ffmpeg")
        ffprobe = find_executable("ffprobe.exe") or find_executable("ffprobe")
        ffplay = find_executable("ffplay.exe") or find_executable("ffplay")
        self.ffmpeg_cmd = normalize_path(ffmpeg) if ffmpeg else None
        self.ffprobe_cmd = normalize_path(ffprobe) if ffprobe else None
        self.ffplay_cmd = normalize_path(ffplay) if ffplay else None

    def stop_all_transcodes(self):
        """停止所有转码进程（发送 q 信号，并标记任务为已停止）"""
        self.stop_flag = True  # 标记全局停止，阻止新任务启动
        with self._proc_lock:
            # 清理已结束的进程和任务映射
            self.running_procs = [p for p in self.running_procs if p.poll() is None]
            self._running_tasks = [(p, t) for (p, t) in self._running_tasks if p.poll() is None]
            if not self.running_procs:
                self.root.after(0, lambda: messagebox.showinfo("提示", "当前没有正在运行的转码进程"))
                return
    
        # 确认是否继续
        if not messagebox.askyesno("确认停止", f"将停止 {len(self.running_procs)} 个正在运行的转码进程，确定吗？"):
            return
    
        # 标记任务为已停止
        for _, task in self._running_tasks:
            task.stopped_by_user = True
    
        # 发送 'q' 给每个进程
        procs = list(self.running_procs)  # 快照
        for proc in procs:
            if proc.poll() is None and proc.stdin:
                try:
                    proc.stdin.write('q\n')
                    proc.stdin.flush()
                    self._append_info_ui(f"[停止] 已向进程 {proc.pid} 发送停止指令")
                except Exception as e:
                    self._append_info_ui(f"[停止] 发送 q 到进程 {proc.pid} 失败: {e}")
    
        # 3 秒后检查并强制终止
        self.root.after(3000, lambda: self._check_and_terminate(procs))
    
    def _check_and_terminate(self, procs):
        still_alive = [p for p in procs if p.poll() is None]
        if not still_alive:
            self._append_info_ui("[停止] 所有进程已正常退出")
            return
    
        for p in still_alive:
            try:
                p.terminate()
                self._append_info_ui(f"[停止] 已 terminate 进程 {p.pid}")
            except Exception as e:
                self._append_info_ui(f"[停止] terminate 进程 {p.pid} 失败: {e}")
    
        # 最终 kill
        self.root.after(3000, lambda: self._kill_remaining(still_alive))
    
    def _kill_remaining(self, procs):
        for p in procs:
            if p.poll() is None:
                try:
                    p.kill()
                    self._append_info_ui(f"[停止] 已 kill 进程 {p.pid}")
                except Exception as e:
                    self._append_info_ui(f"[停止] kill 进程 {p.pid} 失败: {e}")
    

    def _load_cmd_templates(self):
        """仅从文件加载快速命令模板，若文件不存在则保留空字典（不创建）"""
        self.cmd_templates = {}
        if os.path.exists(self.cmd_templates_path):
            try:
                with open(self.cmd_templates_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.cmd_templates = data
            except Exception as e:
                self._append_info_ui(f"加载快速命令模板失败: {e}")
        # 如果文件不存在，则 cmd_templates 保持为空字典，稍后由后台线程创建
    
    def _get_default_cmd_templates(self):
        """返回默认的命令模板字典"""
        return {
            "生成静音音频 (anullsrc)": 'ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=stereo -t 10 "{output_dir}silence.wav"',
            "提取关键帧 (关键帧截图)": 'ffmpeg -y -i "{input}" -vf "select=eq(pict_type\\\\,I)" -vsync vfr "{output_dir}thumb_%04d.png"',
            "查看媒体信息 (ffprobe)": 'ffprobe -v error -show_format -show_streams "{input}"',
            "快速转码测试 (10秒)": 'ffmpeg -y -i "{input}" -c:v libx264 -preset ultrafast -t 10 "{output_dir}output_test.mp4"',
            "生成测试视频 (彩条)": 'ffmpeg -y -f lavfi -i testsrc=duration=10:size=640x480:rate=30 -c:v libx264 "{output_dir}test.mp4"',
            "生成测试视频 (动态)": 'ffmpeg -y -f lavfi -i testsrc2=duration=10:size=640x480:rate=30 -c:v libx264 "{output_dir}test2.mp4"',
            "生成黑色背景视频": 'ffmpeg -y -f lavfi -i color=c=black:s=vga:r=25 -c:v libx264 -t 10 "{output_dir}out_color.mp4"',
            "生成雪花视频": 'ffmpeg -y -f lavfi -i "nullsrc=s=640x480:r=25,geq=random(1)*255:128:128" -c:v libx264 -t 10 "{output_dir}out_snow.mp4"',
            "生成滴一声": 'ffmpeg -y -f lavfi -i "sine=frequency=1000:duration=0.2,apad=pad_dur=0.3" "{output_dir}beep.wav"',
            "生成滴持续": 'ffmpeg -y -f lavfi -i "sine=frequency=900:duration=10" "{output_dir}beeplong.wav"',
            "生成分形曼德博图案": 'ffmpeg -y -f lavfi -i "mandelbrot=s=640x480:r=25" -c:v libx264 -t 10 "{output_dir}mandelbrot.mp4"',
            "生成透明纯色视频(ProRes)": 'ffmpeg -y -f lavfi -i "color=c=#00000000:s=640x480:r=25,format=rgba" -c:v prores_ks -t 10 "{output_dir}transparent_bg.mov"',
            "元胞自动机": 'ffmpeg -y -f lavfi -i cellauto -vf format=yuv420p -c:v libx264 -t 10 "{output_dir}cellauto.mp4"',
            "生命活动": 'ffmpeg -y -f lavfi -i life -vf format=yuv420p -c:v libx264 -t 10 "{output_dir}life.mp4"',
            "生成白噪音 (静电噪音)": 'ffmpeg -y -f lavfi -i "anoisesrc=duration=10:colour=white" "{output_dir}white_noise.wav"',
            "生成粉噪音 (柔和噪声)": 'ffmpeg -y -f lavfi -i "anoisesrc=duration=10:colour=pink" "{output_dir}pink_noise.wav"',
            "生成正弦波音频": 'ffmpeg -y -f lavfi -i "aevalsrc=sin(440*2*PI*t)" -t 5 "{output_dir}sin_noise.wav"',
            "按帧率提取图片 (30)": 'ffmpeg -y -i "{input}" -vf "fps=30" "{output_dir}output_frame_%04d.jpg"',
            "元数据旋转90° (仅MP4)": 'ffmpeg -y -i "{input}" -c copy -metadata:s:v rotate="90" "{output_dir}rotated.mp4"',
            "元数据旋转180° (仅MP4)": 'ffmpeg -y -i "{input}" -c copy -metadata:s:v rotate="180" "{output_dir}rotated.mp4"',
            "元数据旋转270° (仅MP4)": 'ffmpeg -y -i "{input}" -c copy -metadata:s:v rotate="270" "{output_dir}rotated.mp4"',
            "音视频倒放(reverse)": 'ffmpeg -y -i "{input}" -vf reverse -af areverse "{output_dir}reverse.mp4"',
            "视频四周加边框 (pad)": 'ffmpeg -y -i \"{input}\" -vf \"pad=iw+20:ih+20:10:10:color=red\" -c:a copy \"{output_dir}bordered.mp4\"',
            "简易英文文字水印(drawtext)": 'ffmpeg -y -i "{input}" -vf "drawtext=text=\'Hello\':fontsize=30:fontcolor=white:x=10:y=10" -c:a copy "{output_dir}text.mp4"',
            "绘制矩形标记 (drawbox)": 'ffmpeg -y -i "{input}" -vf "drawbox=x=10:y=10:w=100:h=100:color=red@0.5:thickness=5" -c:a copy "{output_dir}box.mp4"',
            "简易音频降噪 (afftdn)": 'ffmpeg -y -i "{input}" -af "afftdn" -c:v copy "{output_dir}denoised.wav"',

            "视频半速 + 60帧插值": 'ffmpeg -y -i \"{input}\" -filter_complex \"[0:v]setpts=2*PTS,minterpolate=\'mi_mode=mci:mc_mode=aobmc:vsbmc=1:fps=60\'[v];[0:a]atempo=0.5[a]\" -map \"[v]\" -map \"[a]\" \"{output_dir}half_speed_60fps.mp4\"',
            "60帧插值": 'ffmpeg -y -i \"{input}\" -filter_complex \"[0:v]minterpolate=\'mi_mode=mci:mc_mode=aobmc:vsbmc=1:fps=60\'\" \"{output_dir}60fps_interpolated.mp4\"',
            "设置画面比例": 'ffmpeg -y -i \"{input}\" -aspect 16:9 \"{output_dir}aspect_16x9.mp4\"',
            "视频流时间戳偏移": 'ffmpeg -y -itsoffset 1 -i \"{input}\" -c copy -map 0:v -map 1:a \"{output_dir}offset_video.mp4\"',
            "提取画面内容不同的帧(0.1-0.3)": 'ffmpeg -y -i \"{input}\" -vf \"select=gt(scene\\,0.1)\" -vsync 0 \"{output_dir}%04d.jpg\"',
            "静态图像制作视频": 'ffmpeg -y -loop 1 -i \"{input}\" -i audio.mp3 -c:v libx264 -tune stillimage -c:a aac -shortest \"{output_dir}still_video.mp4\"',
            "音频响度标准化": 'ffmpeg -y -i \"{input}\" -filter:a \"loudnorm=I=-23:LRA=7:TP=-2\" -c:v copy \"{output_dir}normalized.mp4\"',
            "静音特定音频通道": 'ffmpeg -y -i \"{input}\" -af \"pan=stereo|c0=c0|c1=0*c1\" -c:v copy \"{output_dir}right_channel_muted.mp4\"',
            "交换左右音频通道": 'ffmpeg -y -i \"{input}\" -af \"pan=stereo|c0=c1|c1=c0\" -c:v copy \"{output_dir}swapped_channels.mp4\"',
            "合并两个音频流": 'ffmpeg -y -i \"{input}\" -i input2.mp3 -filter_complex \"[0:a][1:a]amerge=inputs=2[a]\" -map \"[a]\" \"{output_dir}merged.mp4\"',
            "提取内置封面 (cover art)": 'ffmpeg -y -i "{input}" -map 0:v:0? -c:v copy "{output_dir}cover.jpg"',
            "提取第一帧截图": 'ffmpeg -y -i "{input}" -vframes 1 "{output_dir}thumb.jpg"',
            "提取指定时间帧 (需改 -ss)": 'ffmpeg -y -i "{input}" -ss 00:00:05 -vframes 1 "{output_dir}thumb.jpg"',



        }
    
    def _save_cmd_templates(self):
        """保存命令模板到 JSON 文件（覆盖写入）"""
        os.makedirs(os.path.dirname(self.cmd_templates_path), exist_ok=True)
        try:
            with open(self.cmd_templates_path, 'w', encoding='utf-8') as f:
                json.dump(self.cmd_templates, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self._append_info_ui(f"保存快速命令模板失败: {e}")
    
    def _refresh_cmd_preset_list(self):
        """刷新命令预设下拉列表"""
        if hasattr(self, 'cmd_preset_combo'):
            names = list(self.cmd_templates.keys())
            self.cmd_preset_combo['values'] = names
            if names:
                self.cmd_preset_var.set(names[0])
            else:
                self.cmd_preset_var.set("")



    def _add_hwaccel_params(self, cmd_list: List[str], settings: dict):
        """添加硬件解码相关参数（若启用）"""
        if not settings.get("hwaccel_enabled", False):
            return
        decoder_display = settings.get("hwaccel_decoder", "无")
        decoder_key = DECODER_MAP.get(decoder_display, "none")
        if decoder_key == "none":
            return
    
        # 专用解码器（如 h264_cuvid）
        if decoder_key in ("h264_cuvid", "hevc_cuvid", "vp9_cuvid", "av1_cuvid",
                           "h264_qsv", "hevc_qsv"):
            cmd_list.extend(["-c:v", decoder_key])
        # 通用硬件加速
        elif decoder_key in ("auto", "cuda", "qsv", "vaapi", "videotoolbox"):
            if decoder_key == "auto":
                cmd_list.extend(["-hwaccel", "auto"])
            elif decoder_key == "cuda":
                cmd_list.extend(["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"])
            elif decoder_key == "qsv":
                cmd_list.extend(["-hwaccel", "qsv", "-hwaccel_output_format", "qsv"])
            elif decoder_key == "vaapi":
                cmd_list.extend(["-hwaccel", "vaapi", "-hwaccel_output_format", "vaapi"])
            elif decoder_key == "videotoolbox":
                cmd_list.extend(["-hwaccel", "videotoolbox"])

    def _add_trim_params(self, cmd_list: List[str], settings: dict):
        """从设置字典中添加截取参数（-ss, -to）到命令列表"""
        if settings.get("trim_enabled", False):
            start = settings.get("trim_start", "").strip()
            end = settings.get("trim_end", "").strip()
            if start:
                cmd_list.extend(["-ss", start])
            if end:
                cmd_list.extend(["-to", end])


    def _enforce_reencode_for_precise_trim(self, settings: dict, only_audio: bool = False):
        """精准模式下强制重新编码"""
        if settings.get("precise_trim", False) and not only_audio:
            if settings.get("encoder") == "copy":
                settings["encoder"] = "libx265"
                self._append_info_ui("精准截取模式下，编码器不能为 copy，已自动改为 libx265。")

    def _calculate_trim_duration(self, settings: dict, input_path: str) -> Tuple[Optional[float], Optional[float]]:
        """
        根据设置计算精准截取的起始时间（start_sec）和输出时长（duration）。
        :param settings: 设置字典（需包含 trim_start, trim_end, precise_trim）
        :param input_path: 输入文件路径（用于获取总时长）
        :return: (start_sec, duration)，若无法计算则对应为 None
        """
        if not settings.get("trim_enabled", False):
            return None, None
        start = settings.get("trim_start", "").strip()
        end = settings.get("trim_end", "").strip()
        start_sec = time_to_seconds(start) if start else 0.0
        end_sec = time_to_seconds(end) if end else None
        if start_sec is None:
            return None, None
        duration = None
        total_duration = self._get_media_duration(input_path)
        if end_sec is not None:
            duration = end_sec - start_sec
        elif total_duration is not None:
            duration = total_duration - start_sec
        return start_sec, duration





    def _get_video_framerate(self, file_path: str) -> Optional[float]:
        """获取视频文件的平均帧率（fps），失败返回 None"""
        if not self.ffprobe_cmd or not os.path.exists(file_path):
            return None
        cmd = [self.ffprobe_cmd, "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=avg_frame_rate", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=flags)
            if result.returncode == 0 and result.stdout.strip():
                num, den = result.stdout.strip().split('/')
                return float(num) / float(den) if float(den) != 0 else None
        except:
            pass
        return None

    def _get_media_duration(self, file_path):
        """获取媒体文件时长（秒），带缓存，失败返回 None"""
        if not file_path or not os.path.exists(file_path):
            return None
        # 获取文件修改时间作为缓存键的一部分
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            mtime = None
        cache_key = (file_path, mtime)
        if cache_key in self._duration_cache:
            return self._duration_cache[cache_key]
        
        # 原有 ffprobe 调用
        if not self.ffprobe_cmd:
            return None
        cmd = [self.ffprobe_cmd, "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", file_path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5,
                                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            if result.returncode == 0 and result.stdout.strip():
                duration = float(result.stdout.strip())
                self._duration_cache[cache_key] = duration
                return duration
        except:
            pass
        return None
    
    
    def _get_video_dimensions_cached(self, file_path):
        """获取视频原始宽高（不考虑旋转），带缓存"""
        if not file_path or not os.path.exists(file_path):
            return None, None
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            mtime = None
        cache_key = (file_path, mtime)
        if cache_key in self._dimension_cache:
            return self._dimension_cache[cache_key]
        
        w, h = get_video_dimensions(self.ffprobe_cmd, file_path)
        if w is not None and h is not None:
            self._dimension_cache[cache_key] = (w, h)
        return w, h


    def _build_video_encoding_params(self, cmd_list: List[str], settings: dict) -> List[str]:
        vcodec = settings.get("encoder", "libx265")
        if vcodec == "copy":
            cmd_list.extend(["-c:v", "copy"])
            return cmd_list
    
        strategy = get_encoder_strategy(vcodec)
        cmd_list = strategy.build_params(cmd_list, settings)
    
        if settings.get("frame_rate_type") == "custom" and settings.get("frame_rate_custom"):
            cmd_list.extend(["-r", settings['frame_rate_custom']])

        # 为 WebP 动图默认添加无限循环
        if vcodec == "libwebp":
            cmd_list.extend(["-loop", "0"])

        return cmd_list
    
    def _build_audio_encoding_params(self, cmd_list: List[str], settings: dict) -> List[str]:
        if not settings.get("audio_enabled", True):
            cmd_list.append("-an")
            return cmd_list
    
        speed_factor = float(settings.get("speed_factor", "1.0"))
        audio_needs_speed = settings.get("speed_enabled", False) and speed_factor != 1.0
        volume = settings.get("volume", 1.0)
        volume_enabled = settings.get("volume_enabled", False)
        audio_needs_volume = volume_enabled and volume != 1.0
    
        acodec = settings.get("audio_codec", "aac")
        audio_filters = []
        if audio_needs_volume:
            audio_filters.append(f"volume={volume:.2f}")
        if audio_needs_speed:
            atempo = build_atempo_chain(speed_factor)
            if atempo:
                audio_filters.append(atempo)
    
        need_reencode = len(audio_filters) > 0
        if need_reencode and acodec == "copy":
            acodec = "aac"
            self._append_info_ui("[音频] 由于应用了音量/变速滤镜，编码器自动从 copy 改为 aac")
    
        if acodec == "copy":
            cmd_list.extend(["-c:a", "copy"])
        else:
            cmd_list.extend(["-c:a", acodec])
            cmd_list.extend(["-b:a", settings.get("audio_bitrate", "128k")])
            cmd_list.extend(["-ar", settings.get("audio_samplerate", "44100")])

        if settings.get('reverse_enabled', False):
            audio_filters.append("areverse")

        if audio_filters:
            cmd_list.extend(["-af", ",".join(audio_filters)])
    
        return cmd_list

    def _apply_audio_trim_and_encode(self, cmd_list: List[str], settings: dict,
                                      input_path: str, start_sec: float, duration: float,
                                      map_audio: bool = False) -> List[str]:
        """
        为音频流应用精准截取（atrim + asetpts）并设置编码参数。
        :param cmd_list: 命令列表
        :param settings: 设置字典（包含音频编码器、比特率、采样率等）
        :param input_path: 音频来源文件路径（用于获取总时长，但这里我们已经传入了 duration，所以不需要）
        :param start_sec: 起始时间（秒）
        :param duration: 截取时长（秒）
        :param map_audio: 是否添加 -map 0:a:0（水印模式需要）
        :return: 修改后的 cmd_list
        """
        if map_audio:
            cmd_list.extend(["-map", "0:a:0"])
    
        # 强制重新编码
        acodec = settings.get("audio_codec", "aac")
        if acodec == "copy":
            acodec = "aac"
            self._append_info_ui("音频截取启用，编码器已从 copy 改为 aac")
    
        # 构建音频滤镜
        af_filters = []
        if start_sec is not None and duration > 0:
            af_filters.append(f"atrim=start={start_sec:.3f}:duration={duration:.3f}")
            af_filters.append("asetpts=PTS-STARTPTS")
    
        # 合并其他音频滤镜（音量、变速等）
        speed_factor = float(settings.get("speed_factor", "1.0"))
        if settings.get("speed_enabled", False) and speed_factor != 1.0:
            atempo = build_atempo_chain(speed_factor)
            if atempo:
                af_filters.append(atempo)
        volume = settings.get("volume", 1.0)
        if settings.get("volume_enabled", False) and volume != 1.0:
            af_filters.append(f"volume={volume:.2f}")
    
        if af_filters:
            cmd_list.extend(["-af", ",".join(af_filters)])
    
        # 编码参数
        cmd_list.extend(["-c:a", acodec])
        cmd_list.extend(["-b:a", settings.get("audio_bitrate", "128k")])
        cmd_list.extend(["-ar", settings.get("audio_samplerate", "44100")])
    
        return cmd_list


    def _adapt_sub_settings(self, sub_settings, current_w, current_h):
        """
        根据当前视频尺寸，从基准尺寸缩放位置和大小。
        返回新的设置字典（含 base_width/height 和缩放后的像素值）。
        基准尺寸从 sub_settings 中读取，若不存在则用当前尺寸初始化。
        """
        if not sub_settings:
            return {}
        import copy
        new_settings = copy.deepcopy(sub_settings)
    
        # 获取基准尺寸
        base_w = new_settings.get("base_width")
        base_h = new_settings.get("base_height")
        if base_w is None or base_h is None:
            # 首次设置，用当前尺寸作为基准
            base_w = current_w
            base_h = current_h
            new_settings["base_width"] = base_w
            new_settings["base_height"] = base_h
            # 基准就是当前尺寸，缩放比例为1，所以无需改变数值
            # 但为了统一，仍然保留原有数值（可能都是数字）
            return new_settings
    
        # 计算缩放比例
        scale_w = current_w / base_w
        scale_h = current_h / base_h
    
        # 处理位置坐标（必须是纯数字）
        for field in ['overlay_x', 'overlay_y']:
            val = new_settings.get(field, '').strip()
            if val:
                try:
                    num = float(val)
                    if field == 'overlay_x':
                        new_val = int(round(num * scale_w))
                    else:
                        new_val = int(round(num * scale_h))
                    new_settings[field] = str(new_val)
                except ValueError:
                    # 非纯数字（如表达式）保持不变，但建议只使用数字
                    pass
    
        # 处理缩放尺寸（scale_width / scale_height）
        for field in ['scale_width', 'scale_height']:
            val = new_settings.get(field, '').strip()
            if val:
                try:
                    num = float(val)
                    if field == 'scale_width':
                        new_val = int(round(num * scale_w))
                    else:
                        new_val = int(round(num * scale_h))
                    new_settings[field] = str(new_val)
                except ValueError:
                    # 非纯数字（如 "iw/2"）保持不变，建议用户使用数字
                    pass
    
        return new_settings

    def _generate_segment_concat_command(self, input_path: str, output_path: str, settings: dict) -> List[str]:
        """
        生成分段拼接的 FFmpeg 命令，支持仅音频、硬件解码、增强滤镜等。
        """
        segments = settings.get("segments", [])
        if not segments:
            raise ValueError("片段列表为空")
    
        input_path = normalize_path(input_path)
        output_path = normalize_path(output_path)
    
        # 检测仅音频模式
        only_audio = settings.get("only_audio", False)
        disable_audio = not settings.get("audio_enabled", True)
    
        cmd = [self.ffmpeg_cmd, "-y"]

        self._add_hwaccel_params(cmd, settings)
    
        cmd.extend(["-i", input_path])

        # ----- 检测输入文件是否包含音频流  -----
        has_input_audio = False
        info = ffprobe_json(self.ffprobe_cmd, input_path)
        if info:
            has_input_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
    
        # ----- 构建 filter_complex -----
        n = len(segments)
        v_filters = []
        a_filters = []
    
        for i, seg in enumerate(segments):
            start = time_to_seconds(seg["start"])
            end = time_to_seconds(seg["end"])
            if start is None or end is None:
                raise ValueError(f"片段 {i+1} 时间无效: start={seg['start']}, end={seg['end']}")
            if start >= end:
                raise ValueError(f"片段 {i+1} 开始时间必须小于结束时间")
    
            flip = seg.get("flip", "无")
            flip_filter = ""
            if flip == "水平翻转":
                flip_filter = ",hflip"
            elif flip == "垂直翻转":
                flip_filter = ",vflip"
            elif flip == "水平+垂直":
                flip_filter = ",hflip,vflip"
    
            # 视频trim（仅非仅音频模式）
            if not only_audio:
                v_filters.append(f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS{flip_filter}[v{i}]")
    
            # 音频trim（除非完全禁用音频 且 源文件有音频）
            if not disable_audio and has_input_audio:
                a_filters.append(f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]")
    
        filter_parts = []
    
        # 视频处理
        if not only_audio and v_filters:
            filter_parts.extend(v_filters)
            v_concat = f"[{']['.join(f'v{i}' for i in range(n))}]concat=n={n}:v=1:a=0[vout]"
            filter_parts.append(v_concat)
    
            # ----- 全局视频滤镜（缩放、裁剪、旋转、翻转、帧率、像素格式、增强） -----
            global_filters = []
    
            # 缩放
            if settings.get("scale_enabled", False):
                method = settings.get("scale_method", "width")
                w = settings.get("scale_width", "").strip()
                h = settings.get("scale_height", "").strip()
                if method == "width" and w:
                    global_filters.append(f"scale={w}:-2")
                elif method == "height" and h:
                    global_filters.append(f"scale=-2:{h}")
                elif method == "exact" and w and h:
                    global_filters.append(f"scale={w}:{h}")
    
            # 裁剪
            if settings.get("crop_enabled", False):
                cw = settings.get("crop_width", "").strip()
                ch = settings.get("crop_height", "").strip()
                cx = settings.get("crop_left", "0").strip()
                cy = settings.get("crop_top", "0").strip()
                if cw and ch:
                    global_filters.append(f"crop={cw}:{ch}:{cx}:{cy}")
    
            # 旋转
            rotate = settings.get("rotate", "none")
            if rotate == "90":
                global_filters.append("transpose=1")
            elif rotate == "180":
                global_filters.append("transpose=2,transpose=2")
            elif rotate == "270":
                global_filters.append("transpose=2")
    
            # 翻转（全局）
            if settings.get("vflip", False):
                global_filters.append("vflip")
            if settings.get("hflip", False):
                global_filters.append("hflip")
    
            # 帧率
            if settings.get("frame_rate_type") == "custom":
                fps = settings.get("frame_rate_custom", "").strip()
                if fps:
                    global_filters.append(f"fps={fps}")
    
            # 像素格式
            if settings.get("pix_fmt_enabled", True):
                pix = settings.get("pix_fmt", "yuv420p")
                if pix:
                    global_filters.append(f"format={pix}")
    
            # 增强滤镜（降噪、锐化、颜色校正等）
            enhance_settings = settings.get("enhance", {})
            if enhance_settings:
                temp_settings = {
                    "crop_enabled": False,
                    "scale_enabled": False,
                    "rotate": "none",
                    "vflip": False,
                    "hflip": False,
                    "speed_enabled": False,
                    "deinterlace_filter": "none",
                    "pix_fmt_enabled": False,
                    "subtitle_enabled": False,
                    "reverse_enabled": False,
                    "enhance": enhance_settings,
                }
                enhance_filter = build_video_filter_chain(
                    temp_settings,
                    include_subtitle=False,
                    include_speed=False,
                    include_trim=False,
                    include_format=False,
                    enhance_settings=enhance_settings
                )
                if enhance_filter and enhance_filter != "null":
                    global_filters.append(enhance_filter)
    
            if global_filters:
                global_filter_str = ",".join(global_filters)
                filter_parts.append(f"[vout]{global_filter_str}[final_v]")
                map_v = "[final_v]"
            else:
                map_v = "[vout]"
    
        # 音频 concat（如果存在音频片段）
        if a_filters:
            filter_parts.extend(a_filters)
            a_concat = f"[{']['.join(f'a{i}' for i in range(n))}]concat=n={n}:v=0:a=1[aout]"
            filter_parts.append(a_concat)
    
        all_filters = ";".join(filter_parts)
        if all_filters:
            cmd.extend(["-filter_complex", all_filters])
    
        # ----- 映射流 -----
        if only_audio:
            cmd.extend(["-map", "[aout]"])
            cmd.append("-vn")
        else:
            if v_filters:
                # 视频流已处理
                cmd.extend(["-map", map_v])
                if a_filters:
                    cmd.extend(["-map", "[aout]"])
            else:
                # 不应该发生，因为至少有一个视频片段，但若没有则报错
                raise ValueError("没有视频片段")
            # 视频编码参数
            vcodec = settings.get("encoder", "libx265")
            if vcodec == "copy":
                self._append_info_ui("分段拼接模式不支持 copy，自动改为 libx265")
                vcodec = "libx265"
                settings["encoder"] = vcodec
            strategy = get_encoder_strategy(vcodec)
            cmd = strategy.build_params(cmd, settings)
    
        # 音频编码参数（如果启用且不是仅音频模式时，音频编码单独处理）
        if not disable_audio:
            if only_audio:
                # 仅音频模式，直接输出音频
                acodec = settings.get("audio_codec", "aac")
                abitrate = settings.get("audio_bitrate", "128k")
                arate = settings.get("audio_samplerate", "44100")
                cmd.extend(["-c:a", acodec, "-b:a", abitrate, "-ar", arate])
            else:
                # 视频模式，音频编码（如果有音频）
                if a_filters:
                    acodec = settings.get("audio_codec", "aac")
                    abitrate = settings.get("audio_bitrate", "128k")
                    arate = settings.get("audio_samplerate", "44100")
                    cmd.extend(["-c:a", acodec, "-b:a", abitrate, "-ar", arate])
        else:
            cmd.append("-an")
    
        # 自定义参数
        custom = settings.get("custom_args", "").strip()
        if custom:
            try:
                cmd.extend(shlex.split(custom))
            except ValueError:
                self._append_info_ui(f"警告：自定义参数格式错误，已忽略：{custom}")
    
        # 容器优化
        container = settings.get("output_container", "mp4").lower()
        if container in ("mp4", "mov"):
            cmd.extend(["-movflags", "+faststart"])
    
        cmd.append(output_path)
        return cmd

    def _build_overlay_filter_complex(self, main_idx: int, main_settings: dict,
                                       sub_infos: List[Tuple[int, str, dict]],
                                       include_subtitle_main: bool = False,
                                       enhance_settings: Optional[dict] = None,
                                       reverse: bool = False) -> Tuple[str, str]:
        """
        构建主视频 + 多个子视频（画中画/水印）的 filter_complex 字符串。
        注意：此函数不会在 overlay 中添加 shortest=1，避免子视频流结束导致输出提前截断。
        输出结束由全局 -shortest 控制。
        """
        filter_parts = []
        main_vf = build_video_filter_chain(
            main_settings,
            include_subtitle=include_subtitle_main,
            include_speed=True,
            enhance_settings=enhance_settings,
            reverse=reverse
        )
        # 主视频滤镜
        main_vf = build_video_filter_chain(main_settings, include_subtitle=include_subtitle_main,include_speed=True,reverse=main_settings.get('reverse_enabled', False), enhance_settings=enhance_settings)
        if main_vf and main_vf != "null":
            filter_parts.append(f"[{main_idx}:v]{main_vf}[v_main_proc]")
            current_v = "v_main_proc"
        else:
            filter_parts.append(f"[{main_idx}:v]null[v_main_proc]")
            current_v = "v_main_proc"
    
        # 主视频画布偏移
        pad_enabled = main_settings.get('pad_enabled', False)
        if pad_enabled:
            pw = main_settings.get('pad_width', '').strip()
            ph = main_settings.get('pad_height', '').strip()
            if pw and ph:
                ox = main_settings.get('offset_x', '0').strip() or '0'
                oy = main_settings.get('offset_y', '0').strip() or '0'
                filter_parts.append(f"color=c=black:s={pw}x{ph}[canvas]")
                filter_parts.append(f"[canvas][{current_v}]overlay={ox}:{oy}[v_main_pad]")
                current_v = "v_main_pad"
    
        # 处理每个子视频
        for i, (sub_idx, sub_file, sub_settings) in enumerate(sub_infos):
            # 判断是否使用 loop 滤镜：只要截取了且循环模式不是 once，就使用 loop
            use_loop = sub_settings.get("trim_enabled", False)
            if use_loop:
                if sub_settings.get("loop_enabled", False) and sub_settings.get("loop_mode") == "once":
                    use_loop = False
    

            # 获取子视频的增强设置
            sub_enhance = sub_settings.get("enhance", {})
        
            # 获取基础滤镜（不含 trim 和 format）
            base_vf = build_video_filter_chain(
                sub_settings,
                include_subtitle=False,
                include_speed=False,
                include_trim=False,
                include_format=False,
                reverse=sub_settings.get('reverse_enabled', False),
                enhance_settings=sub_enhance
            )
            if base_vf == "null":
                base_vf = ""
    
            if use_loop:
                # 获取帧率
                fps = self._get_video_framerate(sub_file)
                if fps is None:
                    use_loop = False
                else:
                    start_str = sub_settings.get("trim_start", "0").strip()
                    end_str = sub_settings.get("trim_end", "").strip()
                    start_sec = time_to_seconds(start_str) if start_str else 0.0
                    end_sec = time_to_seconds(end_str) if end_str else None
                    if end_sec is not None and end_sec > start_sec:
                        duration = end_sec - start_sec
                    else:
                        raw_duration = self._get_media_duration(sub_file)
                        if raw_duration is not None:
                            duration = raw_duration - start_sec
                        else:
                            use_loop = False
                    if use_loop:
                        size = int(round(duration * fps))
                        if size <= 0:
                            use_loop = False
    
            # 构建子视频滤镜串
            if use_loop:
                loop_param = "-1"
                # 动态构建 trim 参数
                trim_parts = []
                if start_sec is not None:
                    trim_parts.append(f"start={start_sec}")
                if end_sec is not None:
                    trim_parts.append(f"end={end_sec}")
                trim_str = f"trim={':'.join(trim_parts)}" if trim_parts else ""
            
                vf_parts = []
                if trim_str:
                    vf_parts.append(trim_str)
                vf_parts.append("setpts=PTS-STARTPTS")
                vf_parts.append(f"loop=loop={loop_param}:size={size}:start=0")

                if base_vf:
                    vf_parts.append(base_vf)
                vf_parts.append("format=rgba")
                sub_vf = ",".join(vf_parts)
                filter_parts.append(f"[{sub_idx}:v]{sub_vf}[v_temp_{i}]")
                current_sub = f"v_temp_{i}"
            else:
                # 直接使用 base_vf（已含增强），然后加 format=rgba
                if base_vf:
                    sub_vf = f"{base_vf},format=rgba"
                else:
                    sub_vf = "format=rgba"
                filter_parts.append(f"[{sub_idx}:v]{sub_vf}[v_temp_{i}]")
                current_sub = f"v_temp_{i}"
    
            # 绿幕/纯色抠像
            if sub_settings.get("chroma_enabled", False):
                color = sub_settings.get("chroma_color", "green")
                if color.startswith("#"):
                    color = "0x" + color[1:].upper()
                similarity = sub_settings.get("chroma_similarity", 0.3)
                if similarity <= 0:
                    similarity = 0.00001
                blend = sub_settings.get("chroma_blend", 0.1)
                filter_type = sub_settings.get("chroma_filter_type", "chromakey")  # 默认 chromakey
                
                # 强制转换格式为 rgb24 提升兼容性（两种滤镜都适用）
                if filter_type == "colorkey":
                    filter_parts.append(f"[{current_sub}]format=rgb24,colorkey={color}:{similarity}:{blend}[v_sub_{i}]")
                else:
                    # chromakey 可保持原格式，也可加上 format 以确保一致（但 chromakey 支持多种格式，可省略）
                    filter_parts.append(f"[{current_sub}]chromakey={color}:{similarity}:{blend}[v_sub_{i}]")
                current_sub = f"v_sub_{i}"
            else:
                filter_parts.append(f"[{current_sub}]null[v_sub_{i}]")
                current_sub = f"v_sub_{i}"
    
            # 透明度
            alpha_enabled = sub_settings.get("alpha_enabled", False)
            alpha_val = sub_settings.get("alpha_value", 1.0)
            if alpha_enabled and 0.0 <= alpha_val <= 1.0:
                filter_parts.append(f"[{current_sub}]colorchannelmixer=aa={alpha_val:.2f}[v_alpha_{i}]")
                current_sub = f"v_alpha_{i}"
    
            # 叠加（不添加 shortest=1）
            if sub_settings.get('overlay_enabled', True):
                x = sub_settings.get('overlay_x', '0').strip() or '0'
                y = sub_settings.get('overlay_y', '0').strip() or '0'
                duration = self._get_media_duration(sub_file)
                enable_expr = self._calc_enable_expr(sub_settings, duration)
                overlay_filter = f"overlay={x}:{y}:enable='{enable_expr}'"
                filter_parts.append(f"[{current_v}][{current_sub}]{overlay_filter}[v_out_{i}]")
                current_v = f"v_out_{i}"
            else:
                filter_parts.append(f"[{current_v}]null[{current_v}]")
    
        complex_filter = ";".join(filter_parts)
        return complex_filter, f"[{current_v}]"

    def _get_effective_duration(self, settings: dict, raw_duration: Optional[float] = None, input_path: str = None) -> Optional[float]:
        """
        计算有效时长（考虑截取设置）。
        若传入 raw_duration 则直接使用，否则从 input_path 获取。
        返回秒数，失败返回 None。
        """
        # 获取原始时长
        if raw_duration is None and input_path:
            raw_duration = self._get_media_duration(input_path)
        if raw_duration is None:
            return None
    
        if not settings.get("trim_enabled", False):
            return raw_duration
    
        start_str = settings.get("trim_start", "").strip()
        end_str = settings.get("trim_end", "").strip()
        start_sec = time_to_seconds(start_str) if start_str else 0.0
        end_sec = time_to_seconds(end_str) if end_str else None
    
        if end_sec is not None and end_sec > start_sec:
            effective = end_sec - start_sec
        else:
            effective = raw_duration - start_sec
    
        return effective if effective > 0 else None

    def _calc_segments_total_duration(self, settings: dict) -> float:
        """计算分段拼接模式下所有片段的总时长（秒）"""
        segments = settings.get("segments", [])
        if not segments:
            return 0.0
        total = 0.0
        for seg in segments:
            start = time_to_seconds(seg.get("start", ""))
            end = time_to_seconds(seg.get("end", ""))
            if start is not None and end is not None and end > start:
                total += (end - start)
            else:
                # 如果某个片段时间无效，返回0（后续会回退到原始逻辑）
                return 0.0
        return total

    def _calc_enable_expr(self, enc_settings: dict, duration: Optional[float]) -> str:
        loop_enabled = enc_settings.get("loop_enabled", False)
        if not loop_enabled:
            return "1"
    
        # 使用公共方法获取有效时长
        effective_duration = self._get_effective_duration(enc_settings, duration)
        if effective_duration is None:
            # 无法计算有效时长时，降级为原始总时长或无限
            effective_duration = duration
    
        loop_mode = enc_settings.get("loop_mode", "infinite")
        loop_count = enc_settings.get("loop_count", 3)
    
        if loop_mode == "infinite":
            return "1"
        elif loop_mode == "once":
            if effective_duration is not None and effective_duration > 0:
                return f"lte(t,{effective_duration})"
            else:
                self._append_info_ui("[循环] 无法获取视频时长，将一直显示")
                return "1"
        else:  # count
            if effective_duration is not None and effective_duration > 0:
                total = effective_duration * max(1, loop_count)
                return f"lte(t,{total})"
            else:
                self._append_info_ui("[循环] 无法获取视频时长，将按次数显示但无法精确")
                return "1"


    # ---------- 播放器设置相关方法 ----------
    def load_player_settings(self):
        self._loading_settings = True
        try:
            settings = self.preset_manager.load_player_settings()
            self.use_mpv.set(settings.get("use_mpv", False))
            self.mpv_path.set(settings.get("mpv_path", "mpv"))
            # 读取日志设置，缺失时使用默认值
            self.log_enabled_var.set(settings.get("log_enabled", True))
            log_path = settings.get("log_path", os.path.join(get_script_dir(), "editlog.txt"))
            self.log_path_var.set(normalize_path(log_path))
            self.overwrite_policy.set(settings.get("overwrite_policy", "ask"))
            cmd_path = settings.get("cmd_output_path", "")
            if cmd_path:
                self.cmd_output_path.set(cmd_path)
            # 读取 FFmpeg 目录设置
            ffmpeg_dir_enabled = settings.get("ffmpeg_dir_enabled", False)
            ffmpeg_dir_path = settings.get("ffmpeg_dir_path", "")
            self.ffmpeg_dir_enabled.set(ffmpeg_dir_enabled)
            self.ffmpeg_dir_path.set(ffmpeg_dir_path)
    
            preview_editable = settings.get("preview_editable", False)
            self.preview_editable_var.set(preview_editable)
    
            pix_fmt_default = settings.get("pix_fmt_enabled_default", False)
            self.pix_fmt_enabled_default.set(pix_fmt_default)
    
            # 流提取相关
            self.extract_custom_dir.set(settings.get("extract_custom_dir", False))
            self.extract_output_dir.set(settings.get("extract_output_dir", ""))
            self.auto_match_subtitle_ext.set(settings.get("auto_match_subtitle_ext", True))
            self.auto_match_audio_ext.set(settings.get("auto_match_audio_ext", True))
            self.extract_keep_chapters.set(settings.get("extract_keep_chapters", True))
            self.extract_clear_metadata.set(settings.get("extract_clear_metadata", False))
    
    
            parallel = settings.get("ffprobe_parallel")
            if parallel is not None and parallel > 0:
                self.ffprobe_parallel.set(parallel)
            else:
                # 如果预设中没有值，则保存当前计算值（确保预设中有记录）
                pass
        finally:
            self._loading_settings = False

        # 更新路径
        self._update_ffmpeg_paths()

    def save_player_settings(self):
        if getattr(self, '_suppress_save', False) or getattr(self, '_loading_settings', False):
            return
        self.preset_manager.save_player_settings({
            "use_mpv": self.use_mpv.get(),
            "mpv_path": self.mpv_path.get(),
            "log_enabled": self.log_enabled_var.get(),
            "log_path": self.log_path_var.get(),
            "overwrite_policy": self.overwrite_policy.get(),
            "cmd_output_path": self.cmd_output_path.get(),
            "ffmpeg_dir_enabled": self.ffmpeg_dir_enabled.get(),
            "ffmpeg_dir_path": self.ffmpeg_dir_path.get(),
            "preview_editable": self.preview_editable_var.get(),
            "pix_fmt_enabled_default": self.pix_fmt_enabled_default.get(),

            # 流提取相关
            "extract_custom_dir": self.extract_custom_dir.get(),
            "extract_output_dir": self.extract_output_dir.get().strip(),
            "auto_match_audio_ext": self.auto_match_audio_ext.get(),
            "auto_match_subtitle_ext": self.auto_match_subtitle_ext.get(),

            "ffprobe_parallel": self.ffprobe_parallel.get(),
        })

    def preview_with_player(self, input_path, filters=None, audio_only=False, volume=10,
                            extra_args=None, start_time=None, duration=None):
        """
        启动播放器预览
        :param start_time: 起始时间（秒或时间字符串），仅 ffplay 使用，mpv 通过 extra_args 传递 --start
        :param duration: 播放时长（秒），仅 ffplay 使用
        """
        file_path = normalize_path(input_path)
        extra_args = extra_args or []
    
        if audio_only:
            if self.use_mpv.get():
                player = self.mpv_path.get().strip() or "mpv"
                cmd = [player, file_path]
                if start_time is not None:
                    cmd.append(f"--start={start_time}")
                if duration is not None:
                    cmd.append(f"--length={duration}")
            else:
                if not self.ffplay_cmd:
                    self._append_info_ui("未找到 ffplay，无法预览。")
                    return
                cmd = [self.ffplay_cmd, "-nodisp", "-autoexit", "-volume", str(volume)]
                if start_time is not None:
                    cmd.extend(["-ss", str(start_time)])
                if duration is not None:
                    cmd.extend(["-t", str(duration)])
                cmd.append(file_path)
        else:
            if self.use_mpv.get():
                player = self.mpv_path.get().strip() or "mpv"
                cmd = [player, file_path]
                if filters:
                    cmd.append(f"--vf={filters}")
                if start_time is not None:
                    cmd.append(f"--start={start_time}")
                if duration is not None:
                    cmd.append(f"--length={duration}")
                if extra_args:
                    cmd.extend(extra_args)
            else:
                if not self.ffplay_cmd:
                    self._append_info_ui("未找到 ffplay，无法预览。")
                    return
                cmd = [self.ffplay_cmd]
                if start_time is not None:
                    cmd.extend(["-ss", str(start_time)])
                if duration is not None:
                    cmd.extend(["-t", str(duration)])
                cmd.extend(["-i", file_path])
                if filters:
                    cmd.extend(["-vf", filters])
                cmd.extend(["-volume", str(volume)])
                if extra_args:
                    cmd.extend(extra_args)
                if "-window_title" not in cmd:
                    cmd.extend(["-window_title", f"预览: {os.path.basename(file_path)}"])
    
        self._append_info_ui("执行命令: " + format_cmd_for_display(cmd))
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        except Exception as e:
            self._append_info_ui(f"预览失败: {e}")
    
    def _preview_with_settings(self, file_path: str, settings: dict):
        """
        预览：禁用倒放，变速仅 ffplay 支持，视频自适应缩放，
        截取通过播放器原生跳转参数（-ss/--start）实现。
        """
        if not file_path or not os.path.exists(file_path):
            self._append_info_ui(f"文件不存在: {file_path}")
            return
    
        # ---- 禁用倒放 ----
        reverse_enabled = settings.get('reverse_enabled', False)
        if reverse_enabled:
            self._append_info_ui("[预览] 预览不支持倒放，已忽略 reverse。")
            settings = settings.copy()
            settings['reverse_enabled'] = False
    
        # ----- 1. 构建基础视频滤镜（不含变速、倒放） -----
        enhance_settings = settings.get("enhance", {})
        base_vf = build_video_filter_chain(
            settings,
            include_subtitle=True,
            include_speed=False,
            include_trim=False,
            enhance_settings=enhance_settings,
            reverse=False
        )
        filter_parts = []
        if base_vf and base_vf != "null":
            filter_parts.append(base_vf)
    
        # ----- 2. 水印虚拟框 -----
        wm_settings = settings.get("watermark", {})
        if wm_settings.get("enabled", False) and wm_settings.get("file_path", "").strip():
            wm_file = wm_settings.get("file_path", "").strip()
            main_w, main_h = self._get_video_dimensions_cached(file_path)
            if main_w is None or main_h is None:
                self._append_info_ui("[预览] 无法获取视频尺寸，跳过水印虚拟框")
            else:
                if wm_settings.get("adaptive", False):
                    adapted_wm = self._adapt_sub_settings(wm_settings, main_w, main_h)
                else:
                    adapted_wm = wm_settings
                orig_w, orig_h = get_video_rotated_dimensions(self.ffprobe_cmd, wm_file, adapted_wm)
                if orig_w is None or orig_h is None:
                    orig_w, orig_h = 320, 240
                wm_w, wm_h = compute_rendered_size(orig_w, orig_h, adapted_wm)
                if wm_w <= 0 or wm_h <= 0:
                    wm_w, wm_h = orig_w, orig_h
                ctx = {"W": main_w, "H": main_h, "w": wm_w, "h": wm_h}
                x_expr = adapted_wm.get("overlay_x", "W-w-10")
                y_expr = adapted_wm.get("overlay_y", "H-h-10")
                x_val = safe_eval_expr(x_expr, ctx)
                y_val = safe_eval_expr(y_expr, ctx)
                if x_val is None:
                    x_val = main_w - wm_w - 10
                if y_val is None:
                    y_val = main_h - wm_h - 10
                x_val = max(0, min(x_val, main_w - wm_w))
                y_val = max(0, min(y_val, main_h - wm_h))
                drawbox = f"drawbox=x={x_val}:y={y_val}:w={wm_w}:h={wm_h}:color=red@0.3:t=3"
                filter_parts.append(drawbox)
                self._append_info_ui(f"[预览] 水印虚拟框: 位置({x_val}, {y_val}) 尺寸{wm_w}x{wm_h}")
    
        # ----- 3. 自适应缩放 -----
        orig_w, orig_h = get_video_rotated_dimensions(self.ffprobe_cmd, file_path, settings)
        if orig_w is None or orig_h is None:
            orig_w, orig_h = self._get_video_dimensions_cached(file_path)
            if orig_w is None or orig_h is None:
                orig_w, orig_h = 1280, 720
    
        final_w, final_h = compute_rendered_size(orig_w, orig_h, settings)
    
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        margin = 80
        max_w = screen_w - margin
        max_h = screen_h - margin
    
        if final_w > max_w or final_h > max_h:
            scale = min(max_w / final_w, max_h / final_h)
            target_w = int(final_w * scale)
            target_h = int(final_h * scale)
            target_w = target_w if target_w % 2 == 0 else target_w - 1
            target_h = target_h if target_h % 2 == 0 else target_h - 1
            if target_w < 2: target_w = 2
            if target_h < 2: target_h = 2
            filter_parts.append(f"scale={target_w}:{target_h}")
            self._append_info_ui(f"[预览] 视频尺寸 {final_w}x{final_h} 超出屏幕，缩放到 {target_w}x{target_h}")
        else:
            self._append_info_ui(f"[预览] 视频尺寸 {final_w}x{final_h} 适合屏幕，保持原始")
    
        # ----- 构建最终滤镜链（空则留空，不用 "null"） -----
        filter_chain = ",".join(filter_parts) if filter_parts else ""
    
        # ----- 4. 音频变速（仅 ffplay） -----
        extra_args = []
        af_filters = []
        if settings.get("speed_enabled", False):
            try:
                factor = float(settings.get("speed_factor", "1.0"))
                if factor != 1.0 and factor > 0:
                    atempo = build_atempo_chain(factor)
                    if atempo:
                        af_filters.append(atempo)
            except ValueError:
                pass
        if af_filters:
            if self.use_mpv.get():
                self._append_info_ui("[预览] mpv 预览不支持音频变速，已忽略。")
            else:
                af_chain = ",".join(af_filters)
                extra_args.extend(["-af", af_chain])
    
        # ----- 5. 截取参数 -----
        start_sec = None
        duration = None
        if settings.get("trim_enabled", False):
            start_str = settings.get("trim_start", "").strip()
            end_str = settings.get("trim_end", "").strip()
            start_sec = time_to_seconds(start_str) if start_str else None
            end_sec = time_to_seconds(end_str) if end_str else None
            if start_sec is not None and end_sec is not None and end_sec > start_sec:
                duration = end_sec - start_sec
            # 只有开始时间，播放到末尾
    
        # ----- 6. 调用播放器 -----
        self.preview_with_player(
            file_path,
            filter_chain,
            volume=10,
            extra_args=extra_args,
            start_time=start_sec,
            duration=duration
        )




    # ---------- 输出路径生成与命令构建 ----------
    def _sanitize_filename(self, filename: str) -> str:
        """移除 Windows 非法字符，替换为下划线"""
        # Windows 非法字符: \ / : * ? " < > |
        illegal_chars = r'[\\/:*?"<>|]'
        return re.sub(illegal_chars, '_', filename)
    
    def generate_output_path(self, input_path, settings):
        dir_path = settings.get("output_dir") or os.path.dirname(input_path)
        dir_path = normalize_path(dir_path)
        base_name = os.path.basename(input_path)
        name, _ = os.path.splitext(base_name)
        if settings.get("only_audio", False):
            container = settings.get("audio_format", "m4a")
        else:
            container = settings.get("output_container", "mp4")
        custom_name = settings.get("custom_output_name", "").strip()
        if custom_name:
            custom_name = os.path.basename(custom_name)
            # --- 清理非法字符 ---
            custom_name = self._sanitize_filename(custom_name)
            forbidden = {'.', '..', 'CON', 'PRN', 'AUX', 'NUL',
                         'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
                         'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'}
            if not custom_name or custom_name in forbidden or (sys.platform == "win32" and custom_name.upper() in forbidden):
                self._append_info_ui("警告：自定义文件名无效（空或保留名），已忽略")
                custom_name = ""
        if custom_name:
            out_name = custom_name
            if not os.path.splitext(out_name)[1]:
                out_name += f".{container}"
        else:
            suffix = settings.get("output_suffix", "").strip()
            in_dir = os.path.dirname(os.path.abspath(input_path))
            out_dir = os.path.abspath(dir_path)
            if not suffix and in_dir == out_dir:
                suffix = "_new"
            out_name = f"{name}{suffix}.{container}"

        # GIF 强制扩展名
        if settings.get("encoder") == "gif":
            base, ext = os.path.splitext(out_name)
            if ext.lower() != ".gif":
                out_name = base + ".gif"

        # WebP 强制扩展名
        if settings.get("encoder") == "libwebp":
            base, ext = os.path.splitext(out_name)
            if ext.lower() != ".webp":
                out_name = base + ".webp"

        return os.path.join(dir_path, out_name).replace('\\', '/')

    def _generate_gif_command(self, input_path, output_path, settings):
        """
        生成 GIF 编码的 FFmpeg 命令（使用 filter_complex）。
        帧率控制改用 fps 滤镜，而非 -r 选项。
        """
        cmd_list = [self.ffmpeg_cmd, "-y", "-fflags", "+genpts"]
    
        # 快速截取（非精准）在命令行添加 -ss/-to
        if not settings.get("precise_trim", False):
            self._add_trim_params(cmd_list, settings)
    
        # 硬件解码（一般不用于 GIF，但保留）
        self._add_hwaccel_params(cmd_list, settings)
    
        # 输入文件
        cmd_list.extend(["-i", input_path])
    
        # ---- 读取帧率设置 ----
        fps_type = settings.get("frame_rate_type", "keep")
        fps_value = settings.get("frame_rate_custom", "30")
        fps_filter = f"fps={fps_value}" if fps_type == "custom" else ""
        enhance_settings = settings.get("enhance", {})
    
        # 构建预处理滤镜（不含 format 和 subtitle）
        vf = build_video_filter_chain(settings, include_subtitle=False, include_speed=True,reverse=settings.get('reverse_enabled', False),enhance_settings=enhance_settings)
        if vf and vf != "null":
            filters = [f.strip() for f in vf.split(",") if f.strip() and not f.startswith("format=")]
            if fps_filter:
                filters.insert(0, fps_filter)
            pre_vf = ",".join(filters) if filters else ""
        else:
            pre_vf = fps_filter  # 只有帧率滤镜
    
        # ---- 读取 GIF 参数 ----
        loop = settings.get("gif_loop", 0)          # 0=无限循环
        dither = settings.get("gif_dither", "bayer")
        bayer_scale = settings.get("gif_bayer_scale", 2)
        max_colors = settings.get("gif_max_colors", 256)
    
        # 构建 dither 选项
        if dither == "none":
            dither_opt = "none"
        elif dither == "bayer":
            dither_opt = f"bayer:bayer_scale={bayer_scale}"
        else:
            dither_opt = dither
    
        # ---- 构建 filter_complex（增加 RGB 转换） ----
        if pre_vf:
            complex_filter = (
                f"[0:v]{pre_vf}[v];"
                f"[v]split[v1][v2];"
                f"[v2]format=rgb24[v2_rgb];"
                f"[v1]palettegen=max_colors={max_colors}[palette];"
                f"[v2_rgb][palette]paletteuse=dither={dither_opt}[out]"
            )
        else:
            complex_filter = (
                f"[0:v]split[v1][v2];"
                f"[v2]format=rgb24[v2_rgb];"
                f"[v1]palettegen=max_colors={max_colors}[palette];"
                f"[v2_rgb][palette]paletteuse=dither={dither_opt}[out]"
            )
    
        cmd_list.extend(["-filter_complex", complex_filter])
        cmd_list.extend(["-map", "[out]"])
        cmd_list.extend(["-c:v", "gif"])
    
        # 循环设置（如果 loop != 0，则添加 -loop，否则默认无限循环）
        if loop != 0:
            cmd_list.extend(["-loop", str(loop)])
    
        # 忽略音频
        cmd_list.append("-an")
    
        # 输出文件
        cmd_list.append(output_path)
    
        return cmd_list

    def generate_ffmpeg_command(self, input_path: str, output_path: str, settings: dict) -> List[str]:
        if settings.get("segment_enabled", False) and settings.get("segments", []):
            return self._generate_segment_concat_command(input_path, output_path, settings)
        if not self.ffmpeg_cmd:
            raise ValueError("未找到 ffmpeg 可执行文件。")
        errors = ParamValidator.validate_settings(settings)
        if errors:
            raise ValueError("参数错误:\n" + "\n".join(errors))
    
        input_path = normalize_path(input_path)
        output_path = normalize_path(output_path)
        only_audio = settings.get("only_audio", False)
        precise_trim = settings.get("precise_trim", False)
    
        # ----- 组合跳转设置（仅用于普通视频转码，水印/GIF 单独处理） -----
        combo_seek = False
        combo_threshold = 30
        if not only_audio and not settings.get("watermark", {}).get("enabled", False) and settings.get("encoder") != "gif":
            combo_seek = settings.get("combo_seek", False)
            combo_threshold = settings.get("combo_threshold", 30)
            # 互斥：组合跳转时强制禁用精准模式
            if combo_seek:
                precise_trim = False
                settings["precise_trim"] = False
    
        # 精准模式下强制重新编码（视频）
        self._enforce_reencode_for_precise_trim(settings, only_audio)
    
        # ---------- IVTC 与反交错冲突检测 ----------
        enhance_settings = settings.get("enhance", {})
        if enhance_settings.get("ivtc_enabled", False) and settings.get("deinterlace_filter", "none") != "none":
            self._append_info_ui("已启用 IVTC，反交错滤镜将被忽略（IVTC 本身包含反交错功能）。")

    
        # ---------- 检查水印 ----------
        wm_settings = settings.get("watermark", {})
        wm_enabled = wm_settings.get("enabled", False) and wm_settings.get("file_path", "").strip()
        wm_file = wm_settings.get("file_path", "").strip() if wm_enabled else None
    
        if wm_file and not only_audio:
            # 水印模式强制禁用组合跳转
            settings["combo_seek"] = False
            return self._generate_command_with_watermark(input_path, output_path, settings, wm_settings)
    
        # 检查是否 GIF 编码（且非仅音频）
        if settings.get("encoder") == "gif" and not only_audio:
            return self._generate_gif_command(input_path, output_path, settings)
    
        # ---------- 普通模式（无复杂水印） ----------
        cmd_list = [self.ffmpeg_cmd, "-y", "-fflags", "+genpts"]
    
        # ----- 计算截取时长（仅在精准模式或组合跳转时需要） -----
        start_sec = None
        duration_for_audio = None
        if precise_trim or combo_seek:
            start_sec, duration_for_audio = self._calculate_trim_duration(settings, input_path)
    
        used_combo = False
    
        # ---------- 组合跳转分支 ----------
        if combo_seek and settings.get("trim_enabled", False) and start_sec is not None and start_sec > 0:
            threshold = combo_threshold
            pre_seek = max(0, start_sec - threshold)
            post_seek = start_sec - pre_seek  # 即 min(start_sec, threshold)
            # 前置跳转
            cmd_list.extend(["-ss", f"{pre_seek:.3f}"])
            # 硬件解码（放在 -i 之前）
            if not only_audio:
                self._add_hwaccel_params(cmd_list, settings)
            # 输入文件
            cmd_list.extend(["-i", input_path])
            # 后置微调
            cmd_list.extend(["-ss", f"{post_seek:.3f}"])
            # 输出时长
            if duration_for_audio is not None and duration_for_audio > 0:
                cmd_list.extend(["-t", f"{duration_for_audio:.3f}"])
            used_combo = True
        else:
            # ---------- 非组合跳转（正常模式） ----------
            # 快速模式（非精准）才在命令行添加 -ss/-to
            if not precise_trim:
                self._add_trim_params(cmd_list, settings)
    
            if not only_audio:
                self._add_hwaccel_params(cmd_list, settings)
    
            cmd_list.extend(["-i", input_path])
    
        # ----- 视频处理 -----
        if only_audio:
            cmd_list.append("-vn")
        else:
            vcodec = settings.get("encoder", "libx265")
            if vcodec == "copy" and not precise_trim and not used_combo:
                # 纯流复制，忽略所有视频处理
                cmd_list.extend(["-c:v", "copy"])
            else:
                # 构建视频滤镜（包含字幕、变速等），组合跳转时跳过 trim
                enhance_settings = settings.get("enhance", {})
                vf = build_video_filter_chain(
                    settings,
                    include_subtitle=True,
                    include_speed=True,
                    include_trim=(not used_combo),   # 组合跳转时不加 trim
                    enhance_settings=enhance_settings,
                    reverse=settings.get('reverse_enabled', False),
                )
                if vf != "null":
                    cmd_list.extend(["-vf", vf])
    
                cmd_list = self._build_video_encoding_params(cmd_list, settings)
    
        # ----- 音频处理 -----
        if settings.get("audio_enabled", True):
            if used_combo:
                # 组合跳转已用 -ss 截取整个流，音频直接编码（不使用 atrim）
                cmd_list = self._build_audio_encoding_params(cmd_list, settings)
            elif precise_trim and settings.get("trim_enabled", False) and duration_for_audio is not None and duration_for_audio > 0:
                self._apply_audio_trim_and_encode(cmd_list, settings, input_path, start_sec, duration_for_audio, map_audio=False)
            else:
                cmd_list = self._build_audio_encoding_params(cmd_list, settings)
        else:
            cmd_list.append("-an")
    
        custom = settings.get("custom_args", "").strip()
        if custom:
            try:
                cmd_list.extend(shlex.split(custom))
            except ValueError:
                self._append_info_ui(f"警告：自定义参数格式错误，已忽略：{custom}")
    
        if not only_audio:
            container = settings.get("output_container", "mp4").lower()
            if container in ("mp4", "mov"):
                cmd_list.extend(["-movflags", "+faststart"])
    
        cmd_list.append(output_path)
        return cmd_list



    def _add_infinite_loop_params(self, cmd_list: List[str], file_path: str, is_sub_video: bool = True, framerate: str = "30"):
        """
        为输入文件添加无限循环参数（用于子视频/水印）。
        视频：-stream_loop -1
        图片：-loop 1 -framerate <fps>
        
        :param cmd_list: 命令列表（会被修改）
        :param file_path: 文件路径
        :param is_sub_video: 是否仅为子视频（True）或水印（True），实际上逻辑相同，保留参数供扩展
        :param framerate: 图片帧率，默认30
        """
        ext = os.path.splitext(file_path)[1].lower()
        is_image = ext in ('.png', '.jpg', '.jpeg', '.bmp', '.webp')   # 不包括 .gif
        is_gif = ext == '.gif'
        
        if is_gif:
            cmd_list.extend(["-stream_loop", "-1"])
        elif is_image:
            cmd_list.extend(["-loop", "1", "-framerate", framerate])
        else:
            # 普通视频
            cmd_list.extend(["-stream_loop", "-1"])


    def _generate_command_with_watermark(self, input_path: str, output_path: str, settings: dict, wm_settings: dict) -> List[str]:
        main_w, main_h = self._get_video_dimensions_cached(input_path)
        # 强制禁用组合跳转
        settings["combo_seek"] = False
        vcodec = settings.get("encoder", "libx265")
        if vcodec == "copy":
            settings["encoder"] = "libx265"
            self._append_info_ui("水印模式必须重新编码，已将编码器自动改为 libx265。")
        if main_w is not None and main_h is not None:
            if wm_settings.get("adaptive", False):
                adapted_wm = self._adapt_sub_settings(wm_settings, main_w, main_h)
            else:
                adapted_wm = wm_settings.copy()
        else:
            adapted_wm = copy.deepcopy(wm_settings)
    
        # ---- 开始构建命令 ----
        cmd_list = [self.ffmpeg_cmd, "-y", "-fflags", "+genpts"]
    
        wm_file = adapted_wm.get("file_path", "").strip()
        ext = os.path.splitext(wm_file)[1].lower()
        is_image = ext in ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
        loop_mode = adapted_wm.get("loop_mode", "infinite")
        loop_count = adapted_wm.get("loop_count", 3)
        loop_enabled = adapted_wm.get("loop_enabled", False)
    
        # ---------- 强制精准截取（水印模式） ----------
        settings["precise_trim"] = True
        
        # --- 检测源文件是否有音频流 ---
        has_input_audio = False
        info = ffprobe_json(self.ffprobe_cmd, input_path)
        if info:
            has_input_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
        
        # --- 强制音频编码 ---
        if settings.get("audio_enabled", True):
            if settings.get("audio_codec") == "copy":
                if has_input_audio:
                    settings["audio_codec"] = "aac"
                    self._append_info_ui("水印模式下为确保同步，音频编码器已自动设为 aac")
                else:
                    # 源文件无音频，禁用音频
                    settings["audio_enabled"] = False
                    self._append_info_ui("源文件无音频流，已自动禁用音频输出")
        
        self._enforce_reencode_for_precise_trim(settings, only_audio=False)
    

        self._add_hwaccel_params(cmd_list, settings)
    
        # 主视频输入
        cmd_list.extend(["-i", input_path])
    
        # ----- 计算主视频有效时长（截取或总时长） -----
        start_sec, duration_for_sub = self._calculate_trim_duration(settings, input_path)
        main_duration = None
        if settings.get("trim_enabled", False):
            if settings.get("precise_trim", False):  # 强制为 True
                main_duration = duration_for_sub if duration_for_sub is not None else None
            else:
                start = settings.get("trim_start", "").strip()
                end = settings.get("trim_end", "").strip()
                start_sec_calc = time_to_seconds(start) if start else 0.0
                end_sec_calc = time_to_seconds(end) if end else None
                if end_sec_calc is not None:
                    main_duration = end_sec_calc - start_sec_calc
                else:
                    total_dur = self._get_media_duration(input_path)
                    if total_dur is not None:
                        main_duration = total_dur - start_sec_calc
        else:
            total_dur = self._get_media_duration(input_path)
            if total_dur is not None:
                main_duration = total_dur
    
        # ---- 水印普通截取（非精准） ----
        # 注：水印自身的截取由 wm_trim_enabled 控制，不影响主视频
        wm_trim_enabled = adapted_wm.get("trim_enabled", False)
        wm_precise = adapted_wm.get("precise_trim", False)

    
        # ---- 判断是否在滤镜中使用 loop ----
        use_loop_in_filter = wm_trim_enabled  # 只要截取了，就用 loop 滤镜
    
        # ---- 计算水印单次有效时长（用于循环总时长判断） ----
        wm_single_duration = None
        if wm_trim_enabled:
            # 计算截取时长
            start = adapted_wm.get("trim_start", "0").strip()
            end = adapted_wm.get("trim_end", "").strip()
            start_sec_calc = time_to_seconds(start) if start else 0.0
            end_sec_calc = time_to_seconds(end) if end else None
            if end_sec_calc is not None and end_sec_calc > start_sec_calc:
                wm_single_duration = end_sec_calc - start_sec_calc
            else:
                # 只有开始没有结束，用总时长 - 开始
                raw_duration = self._get_media_duration(wm_file)
                if raw_duration is not None:
                    wm_single_duration = raw_duration - start_sec_calc
        else:
            # 无截取，使用原始总时长（视频）
            if not is_image:
                wm_single_duration = self._get_media_duration(wm_file)
            else:
                # 图片没有时长，视为无限
                wm_single_duration = None
    
        # ---- 添加水印输入（及循环参数） ----
        if not is_image:
            if use_loop_in_filter:
                # 循环由滤镜中的 loop 处理，不添加 -stream_loop
                cmd_list.extend(["-i", wm_file])
            else:
                # 使用 -stream_loop -1
                cmd_list.extend(["-stream_loop", "-1"])
                cmd_list.extend(["-i", wm_file])
        else:
            # 图片水印（静态图片或 GIF）
            ext = os.path.splitext(wm_file)[1].lower()
            if ext == '.gif':
                # GIF 本身是动画，不能使用 -loop，用 -stream_loop -1 确保循环
                cmd_list.extend(["-stream_loop", "-1"])
            else:
                fps = settings.get("frame_rate_custom", "30") if settings.get("frame_rate_type") == "custom" else "30"
                cmd_list.extend(["-loop", "1", "-framerate", fps])
            cmd_list.extend(["-i", wm_file])
    
        # ---- 构建叠加滤镜 ----
        sub_infos = [(1, wm_file, adapted_wm)]
        enhance_settings = settings.get("enhance", {})
        complex_filter, final_v_label = self._build_overlay_filter_complex(
            0, settings, sub_infos, include_subtitle_main=True,
            enhance_settings=enhance_settings
        )
        cmd_list.extend(["-filter_complex", complex_filter])
        cmd_list.extend(["-map", final_v_label])
    
        # ---- 视频编码参数 ----
        cmd_list = self._build_video_encoding_params(cmd_list, settings)
        cmd_list.extend(["-vsync", "cfr"])
    
        # ---- 音频处理 ----
        # 使用 ffprobe_json 检测主视频是否有音频流
        info = ffprobe_json(self.ffprobe_cmd, input_path)
        has_audio = info and any(s.get("codec_type") == "audio" for s in info.get("streams", []))

        if not has_audio:
            if settings.get("audio_enabled", True):
                self._append_info_ui("[水印] 主视频无音频流，已自动禁用音频输出。")
                settings["audio_enabled"] = False
            cmd_list.append("-an")
        elif settings.get("audio_enabled", True):
            if settings.get("precise_trim", False) and settings.get("trim_enabled", False) and duration_for_sub is not None and duration_for_sub > 0:
                self._apply_audio_trim_and_encode(cmd_list, settings, input_path, start_sec, duration_for_sub, map_audio=True)
            else:
                cmd_list.extend(["-map", "0:a:0"])
                cmd_list = self._build_audio_encoding_params(cmd_list, settings)
        else:
            cmd_list.append("-an")
    
        # ---- 自定义参数与容器优化 ----
        custom = settings.get("custom_args", "").strip()
        if custom:
            try:
                cmd_list.extend(shlex.split(custom))
            except ValueError:
                self._append_info_ui(f"警告：自定义参数格式错误，已忽略：{custom}")
    
        container = settings.get("output_container", "mp4").lower()
        if container in ("mp4", "mov"):
            cmd_list.extend(["-movflags", "+faststart"])
    
        # ---- 时长控制：有音频时用 -shortest，无音频时用 -t ----
        # 检查主视频是否包含音频流（可复用已有的 ffprobe 信息）
        has_audio_stream = False
        if input_path and os.path.exists(input_path):
            info = ffprobe_json(self.ffprobe_cmd, input_path)
            if info and any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
                has_audio_stream = True
    
        if settings.get("audio_enabled", True) and has_audio_stream:
            cmd_list.append("-shortest")
        else:
            if main_duration and main_duration > 0:
                cmd_list.extend(["-t", f"{main_duration:.3f}"])
            else:
                cmd_list.append("-shortest")
                self._append_info_ui("[水印] 警告：无法计算主视频时长，使用 -shortest 控制输出。")
    
        cmd_list.append(output_path)
        return cmd_list




    def get_current_settings(self):
        settings = {}
        settings.update(self.video_encoder.get_settings())
        settings.update(self.video_filter.get_settings())
        settings.update(self.audio_frame.get_settings())
        settings.update(self.trim_frame.get_settings())
        settings.update(self.adv_frame.get_settings())
        settings["output_dir"] = self.output_dir.get()
        settings["output_suffix"] = self.output_suffix.get()
        settings["custom_output_name"] = self.custom_output_name.get()
        settings["output_container"] = self.output_container.get()
        settings["pip_enabled"] = self.pip_enabled.get()
        settings["segment_enabled"] = self.segment_enabled.get()
        settings["segments"] = copy.deepcopy(self.segments)
        # 添加水印设置（深拷贝）
        wm = copy.deepcopy(self.watermark_settings)
        if "adaptive" not in wm:
            wm["adaptive"] = False
        settings["watermark"] = wm
        # 记录当前输入文件的尺寸作为水印基准
        input_file = self.input_file.get().strip()
        if input_file and os.path.exists(input_file):
            w, h = self._get_video_dimensions_cached(input_file)
            if w is not None and h is not None:
                settings["watermark"]["base_width"] = w
                settings["watermark"]["base_height"] = h
        settings["enhance"] = self.video_filter.get_enhance_settings()
        return settings


    def load_settings_into_ui(self, settings):
        self._loading_preset = True
        try:
            self.output_dir.set(settings.get("output_dir", ""))
            self.output_suffix.set(settings.get("output_suffix", ""))
            self.custom_output_name.set(settings.get("custom_output_name", ""))
            self.output_container.set(settings.get("output_container", "mp4"))
            self.video_encoder.set_settings(settings)
            self.video_filter.set_settings(settings)
            self.audio_frame.set_settings(settings)
            self.trim_frame.set_settings(settings)
            self.adv_frame.set_settings(settings)
            self.pip_enabled.set(settings.get("pip_enabled", False))
#             # 恢复水印设置
#             if "watermark" in settings:
#                 self.watermark_settings = copy.deepcopy(settings["watermark"])
#             else:
#                 # 保持默认值（已在 __init__ 中定义）
#                 pass
            self.toggle_only_audio_mode()
            if "enhance" in settings:
                self.video_filter.set_enhance_settings(settings["enhance"])
        finally:
            self._loading_preset = False
            self.update_command_preview()  # 最后统一刷新一次

    # ---------- 可视化编辑器公共辅助方法（用于合并模块）----------
    def _get_enabled_video_tracks(self):
        return [t for t in self.merge_tracks if t.enabled and t.type == "video"]
    
    def compute_final_size_with_order(self, orig_w: int, orig_h: int, settings: dict) -> Tuple[int, int]:
        """
        按滤镜链顺序（crop -> rotate -> scale）计算最终输出尺寸。
        orig_w, orig_h: 原始视频宽高（不含任何旋转）。
        settings: 包含 crop、rotate、scale 等设置的字典。
        """
        w, h = orig_w, orig_h
    
        # 1. 裁剪（基于原始尺寸）
        if settings.get("crop_enabled", False):
            crop_w = settings.get("crop_width", "").strip()
            crop_h = settings.get("crop_height", "").strip()
            crop_left = settings.get("crop_left", "0").strip()
            crop_top = settings.get("crop_top", "0").strip()
            if crop_w and crop_h:
                # 支持 iw/ih 表达式
                cw = safe_eval_expr(crop_w, {"iw": w, "ih": h})
                ch = safe_eval_expr(crop_h, {"iw": w, "ih": h})
                if cw and ch and cw > 0 and ch > 0:
                    w, h = cw, ch
    
        # 2. 用户旋转（交换宽高）
        rotate = settings.get("rotate", "none")
        if rotate in ("90", "270"):
            w, h = h, w
    
        # 3. 缩放
        if settings.get("scale_enabled", False):
            method = settings.get("scale_method", "width")
            sw = settings.get("scale_width", "").strip()
            sh = settings.get("scale_height", "").strip()
            try:
                if method == "width" and sw:
                    target_w = int(float(sw))
                    target_h = int(round(target_w * h / w))
                    w, h = target_w, target_h
                elif method == "height" and sh:
                    target_h = int(float(sh))
                    target_w = int(round(target_h * w / h))
                    w, h = target_w, target_h
                elif method == "exact" and sw and sh:
                    w, h = int(float(sw)), int(float(sh))
            except:
                pass
    
        return w, h
    
    def _get_canvas_size(self, main_track):
        """
        获取主视频最终画布尺寸（考虑 pad 或 裁剪/旋转/缩放后的实际尺寸）。
        """
        # 检查是否启用画布偏移（pad）
        pad_enabled = main_track.enc_settings.get('pad_enabled', False)
        if pad_enabled:
            try:
                w = int(main_track.enc_settings.get('pad_width', '').strip())
                h = int(main_track.enc_settings.get('pad_height', '').strip())
                if w > 0 and h > 0:
                    return w, h
            except (ValueError, TypeError):
                pass
    
        # 未启用 pad 或 pad 尺寸无效，使用主视频实际渲染尺寸（按正确顺序计算）
        # 先获取原始尺寸（不含旋转）
        w, h = get_video_dimensions(self.ffprobe_cmd, main_track.file_path)
        if w is None or h is None:
            w, h = 1280, 720  # 降级默认值
    
        # 使用新函数按 crop -> rotate -> scale 顺序计算
        return self.compute_final_size_with_order(w, h, main_track.enc_settings)
    
    def _get_video_render_size(self, track, filt_frame=None):
        """
        获取视频轨道在应用了裁剪、旋转、缩放后的最终渲染尺寸。
        若提供了 filt_frame，则从该控件读取设置，否则从 track.enc_settings 读取。
        """
        if filt_frame is not None:
            settings = {
                "crop_enabled": filt_frame.crop_enabled.get(),
                "crop_width": filt_frame.crop_width.get(),
                "crop_height": filt_frame.crop_height.get(),
                "scale_enabled": filt_frame.scale_enabled.get(),
                "scale_method": filt_frame.scale_method.get(),
                "scale_width": filt_frame.scale_width.get(),
                "scale_height": filt_frame.scale_height.get(),
                "rotate": filt_frame.rotate.get()
            }
        else:
            settings = track.enc_settings
    
        # 获取原始尺寸（不含任何旋转，直接从 ffprobe 获取）
        w, h = get_video_dimensions(self.ffprobe_cmd, track.file_path)
        if w is None:
            return None, None
    
        # 使用统一顺序计算（crop -> rotate -> scale）
        return self.compute_final_size_with_order(w, h, settings)
    
    def _to_canvas_coords(self, x, y, scale):
        return int(x * scale), int(y * scale)
    
    def _to_real_coords(self, cx, cy, scale):
        return int(round(cx / scale)), int(round(cy / scale))
    
    def _draw_background(self, canvas, canvas_w, canvas_h, scale, main_track, sub_tracks,
                         offset_x, offset_y, main_render_size, current_edit_track=None, tag="bg"):
        canvas.delete(tag)
        if main_render_size:
            main_w, main_h = main_render_size
        else:
            main_w, main_h = canvas_w, canvas_h
        left = offset_x
        top = offset_y
        right = offset_x + main_w
        bottom = offset_y + main_h
        vis_left = max(0, left)
        vis_top = max(0, top)
        vis_right = min(canvas_w, right)
        vis_bottom = min(canvas_h, bottom)
        if vis_right > vis_left and vis_bottom > vis_top:
            cx1, cy1 = self._to_canvas_coords(vis_left, vis_top, scale)
            cx2, cy2 = self._to_canvas_coords(vis_right, vis_bottom, scale)
            canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="deepskyblue", width=2, dash=(4, 4), fill="", tags=tag)
            canvas.create_text(cx1 + 5, cy1 + 5, anchor="nw", text="主视频", fill="deepskyblue", font=("Arial", 9), tags=tag)
        sub_order = {sub: idx+1 for idx, sub in enumerate(sub_tracks)}
        for sub in sub_tracks:
            if current_edit_track and sub == current_edit_track:
                continue
            # 从 enc_settings 读取 overlay 状态
            if not sub.enc_settings.get('overlay_enabled', True):
                continue
            size = self.get_rendered_size(sub)
            if not size:
                continue
            sw, sh = size
            x_expr = sub.enc_settings.get('overlay_x', '0')
            y_expr = sub.enc_settings.get('overlay_y', '0')
            x_val = safe_eval_expr(x_expr, {"W": canvas_w, "H": canvas_h, "w": sw, "h": sh})
            y_val = safe_eval_expr(y_expr, {"W": canvas_w, "H": canvas_h, "w": sw, "h": sh})
            if x_val is None or y_val is None:
                continue
            x_val = max(0, min(x_val, canvas_w - sw))
            y_val = max(0, min(y_val, canvas_h - sh))
            cx1, cy1 = self._to_canvas_coords(x_val, y_val, scale)
            cx2, cy2 = self._to_canvas_coords(x_val + sw, y_val + sh, scale)
            canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="lightgreen", width=2, dash=(4, 4), fill="", tags=tag)
            canvas.create_text(cx1 + 5, cy1 + 5, anchor="nw", text=str(sub_order[sub]),
                               fill="red", font=("Arial", 10, "bold"), tags=tag)




    # ---------- 通用公共位置可视化编辑器函数 ----------
    def _generic_overlay_editor(self, parent, canvas_w, canvas_h,
                                rect_x, rect_y, rect_w, rect_h,
                                on_apply, title="可视化编辑位置",
                                aspect_ratio=None, bg_draw_func=None,
                                allow_resize=True,
                                show_canvas_controls=False,
                                coord_mode='top_left',
                                allow_negative_offset=False,
                                rect_color='red',
                                extra_info="",   #子视频的额外主视频偏移信息
                                rect_label='',   # 单独的方框显示名
                                min_visible_pixels=0,  # 主视频偏移限制 至少留10  默认传0
                                show_scale_tip=False   # 子视频和水印的 新绘制操作提示
                                ):
        """
        通用叠加/偏移可视化编辑器（核心重构函数）
        
        支持三种主要使用模式：
        
        1. 主视频画布偏移（pad）模式
           - allow_negative_offset=True
           - rect_color='deepskyblue'
           - show_canvas_controls=True（允许调整画布尺寸）
           - 允许矩形超出画布（负偏移）
           - 用于调整主视频内容在更大画布中的位置
        
        2. 子视频/画中画叠加模式
           - allow_negative_offset=False（默认）
           - rect_color='red'
           - allow_resize=True（支持绘制新矩形调整大小）
           - 矩形必须限制在画布内
           - 用于调整画中画、水印等子视频的位置和大小
        
        3. 水印专用模式（通过 open_watermark_overlay_editor 调用）
           - 与子视频模式类似，但额外支持回写缩放尺寸到滤镜框架和 watermark_dict
        
        参数说明：
            on_apply: 回调函数，签名 on_apply(new_x, new_y, new_w, new_h, new_canvas_w, new_canvas_h)
            bg_draw_func: 可选，背景绘制回调，用于画其他子视频的虚线框
            aspect_ratio: 绘制新矩形时是否强制保持宽高比（水印/叠加常用）
            coord_mode: 'top_left'（左上角坐标）或 'offset'（偏移量）
        """
        max_display_w, max_display_h = 800, 600
        scale = min(max_display_w / canvas_w, max_display_h / canvas_h, 1.0)
        disp_w = int(canvas_w * scale)
        disp_h = int(canvas_h * scale)
    
        win = tk.Toplevel(parent)
        win.title(title)
        win.transient(parent)
        win.grab_set()
        win.withdraw()
    
        # ---- 内部状态 ----
        current_x, current_y, current_w, current_h = rect_x, rect_y, rect_w, rect_h
        current_canvas_w, current_canvas_h = canvas_w, canvas_h
        rect_id = None
        text_id = None
        draw_rect_temp = None
        draw_start = None
        draw_mode_active = False
        dragging = False
        drag_start_x = 0
        drag_start_y = 0
        drag_mouse_start = (0, 0)
    
        # ---- 辅助函数 ----
        def to_canvas(ox, oy):
            return int(ox * scale), int(oy * scale)
    
        def to_real(cx, cy):
            return int(round(cx / scale)), int(round(cy / scale))
    
        def clamp_rect():
            nonlocal current_x, current_y, current_w, current_h
            if allow_negative_offset and min_visible_pixels > 0:
                # 允许负偏移，但至少保留 min_visible_pixels 像素可见
                current_x = max(-current_w + min_visible_pixels, 
                                min(current_x, current_canvas_w - min_visible_pixels))
                current_y = max(-current_h + min_visible_pixels, 
                                min(current_y, current_canvas_h - min_visible_pixels))
            elif allow_negative_offset:
                # 完全放开，无任何限制
                pass
            else:
                # 严格限制在画布内（子视频/水印模式）
                current_x = max(0, min(current_x, current_canvas_w - current_w))
                current_y = max(0, min(current_y, current_canvas_h - current_h))
                current_w = min(current_w, current_canvas_w)
                current_h = min(current_h, current_canvas_h)
    
        def create_rect():
            nonlocal rect_id, text_id
            cx1, cy1 = to_canvas(current_x, current_y)
            cx2, cy2 = to_canvas(current_x + current_w, current_y + current_h)
            rid = canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=rect_color, width=2,
                                          fill=rect_color, stipple="gray50", tags="rect")
            tid = canvas.create_text(cx1 + 5, cy1 + 5, anchor="nw", text=rect_label,
                                     fill="white", font=("Arial", 9), tags="rect")
            return rid, tid
    
        def update_rect_position():
            cx1, cy1 = to_canvas(current_x, current_y)
            cx2, cy2 = to_canvas(current_x + current_w, current_y + current_h)
            canvas.coords(rect_id, cx1, cy1, cx2, cy2)
            canvas.coords(text_id, cx1 + 5, cy1 + 5)
            update_coord_display()
    
        def update_coord_display():
            if coord_mode == 'offset':
                coord_var.set(f"偏移: X={current_x}, Y={current_y}")
            else:
                coord_var.set(f"左上角: ({current_x}, {current_y})  宽: {current_w}  高: {current_h}")
    
        # ---- 画布尺寸应用 ----
        def _apply_canvas_size():
            nonlocal current_canvas_w, current_canvas_h, scale, disp_w, disp_h, rect_id, text_id
            try:
                new_w = int(canvas_w_var.get())
                new_h = int(canvas_h_var.get())
                if new_w <= 0 or new_h <= 0:
                    raise ValueError
                current_canvas_w, current_canvas_h = new_w, new_h
                scale = min(max_display_w / current_canvas_w, max_display_h / current_canvas_h, 1.0)
                disp_w = int(current_canvas_w * scale)
                disp_h = int(current_canvas_h * scale)
                win.geometry(f"{disp_w + 20}x{disp_h + 240}")
                canvas.config(width=disp_w, height=disp_h)
                canvas.delete("all")
                if bg_draw_func:
                    bg_draw_func(canvas, scale)
                clamp_rect()
                if rect_id:
                    canvas.delete(rect_id)
                    canvas.delete(text_id)
                rect_id, text_id = create_rect()
                update_coord_display()
                status_var.set(f"画布已调整为 {current_canvas_w}x{current_canvas_h}")
                win.update_idletasks()
                # 重新居中窗口
                x = self.root.winfo_x() + (self.root.winfo_width() - win.winfo_width()) // 2
                y = self.root.winfo_y() + (self.root.winfo_height() - win.winfo_height()) // 2
                win.geometry(f"+{x}+{y}")
            except:
                messagebox.showerror("错误", "画布尺寸无效")
    
        # ---- 矩形拖拽事件 ----
        def start_move(event):
            nonlocal drag_start_x, drag_start_y, drag_mouse_start, dragging
            if draw_mode_active:
                return
            cx, cy = event.x, event.y
            bbox = canvas.bbox(rect_id)
            if bbox and bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]:
                drag_start_x = current_x
                drag_start_y = current_y
                drag_mouse_start = (cx, cy)
                dragging = True
                status_var.set("拖拽移动矩形")
    
        def on_move(event):
            nonlocal current_x, current_y, dragging
            if not dragging or draw_mode_active:
                return
            dx_pixel = event.x - drag_mouse_start[0]
            dy_pixel = event.y - drag_mouse_start[1]
            dx = dx_pixel / scale
            dy = dy_pixel / scale
            new_x = int(drag_start_x + dx)
            new_y = int(drag_start_y + dy)
            if new_x != current_x or new_y != current_y:
                current_x, current_y = new_x, new_y
                clamp_rect()   # 应用边界约束（根据 allow_negative_offset 和 min_visible_pixels）
                update_rect_position()
    
        def stop_move(event):
            nonlocal dragging
            dragging = False
            status_var.set("拖拽完成，可调整或应用")
    
        # ---- 绘制新矩形（仅当 allow_resize=True 时可用） ----
        def start_draw(event):
            nonlocal draw_start, draw_rect_temp, draw_mode_active
            if not draw_mode_active:
                return
            if draw_rect_temp:
                canvas.delete(draw_rect_temp)
                draw_rect_temp = None
            draw_start = to_real(event.x, event.y)
    
        def on_draw_move(event):
            nonlocal draw_rect_temp, draw_start, draw_mode_active
            if not draw_mode_active or draw_start is None:
                return
            cur = to_real(event.x, event.y)
            x1 = min(draw_start[0], cur[0])
            y1 = min(draw_start[1], cur[1])
            x2 = max(draw_start[0], cur[0])
            y2 = max(draw_start[1], cur[1])
            w = x2 - x1
            h = y2 - y1
            if w == 0 or h == 0:
                return
            if aspect_ratio is not None:
                if w / h > aspect_ratio:
                    new_w = h * aspect_ratio
                    x2 = x1 + new_w
                else:
                    new_h = w / aspect_ratio
                    y2 = y1 + new_h
            draw_x = x1
            draw_y = y1
            draw_w = x2 - x1
            draw_h = y2 - y1
            # 边界裁剪（保持矩形在画布内，不超出）
            if draw_x < 0:
                draw_w += draw_x
                draw_x = 0
            if draw_y < 0:
                draw_h += draw_y
                draw_y = 0
            if draw_x + draw_w > current_canvas_w:
                draw_w = current_canvas_w - draw_x
                if aspect_ratio is not None:
                    draw_h = draw_w / aspect_ratio
            if draw_y + draw_h > current_canvas_h:
                draw_h = current_canvas_h - draw_y
                if aspect_ratio is not None:
                    draw_w = draw_h * aspect_ratio
            if draw_w <= 0 or draw_h <= 0:
                return
            cx1, cy1 = to_canvas(draw_x, draw_y)
            cx2, cy2 = to_canvas(draw_x + draw_w, draw_y + draw_h)
            if draw_rect_temp:
                canvas.coords(draw_rect_temp, cx1, cy1, cx2, cy2)
            else:
                draw_rect_temp = canvas.create_rectangle(cx1, cy1, cx2, cy2,
                                                         outline="yellow", width=2, dash=(2, 2))
    
        def end_draw(event):
            nonlocal draw_mode_active, draw_start, draw_rect_temp, current_x, current_y, current_w, current_h, rect_id, text_id
            if not draw_mode_active or draw_start is None:
                return
            if draw_rect_temp:
                coords = canvas.coords(draw_rect_temp)
                if len(coords) == 4:
                    cx1, cy1, cx2, cy2 = coords
                    x1, y1 = to_real(cx1, cy1)
                    x2, y2 = to_real(cx2, cy2)
                    new_w = x2 - x1
                    new_h = y2 - y1
                    if new_w > 0 and new_h > 0:
                        current_x, current_y = x1, y1
                        current_w, current_h = new_w, new_h
                        clamp_rect()  # 应用边界限制（根据 allow_negative_offset 和 min_visible_pixels）
                        canvas.delete(rect_id)
                        canvas.delete(text_id)
                        rect_id, text_id = create_rect()
                        update_coord_display()
                        status_var.set("新矩形已创建，可拖拽移动或应用")
                if draw_rect_temp:
                    canvas.delete(draw_rect_temp)
                    draw_rect_temp = None
            draw_mode_active = False
            if allow_resize:
                draw_btn.config(state="normal")
                draw_abort_btn.config(state="disabled")
            draw_start = None
    
        def abort_draw():
            nonlocal draw_mode_active, draw_rect_temp, draw_start
            draw_mode_active = False
            if allow_resize:
                draw_btn.config(state="normal")
                draw_abort_btn.config(state="disabled")
            if draw_rect_temp:
                canvas.delete(draw_rect_temp)
                draw_rect_temp = None
            draw_start = None
            status_var.set("已取消绘制")
    
        def enter_draw_mode():
            nonlocal draw_mode_active
            if draw_mode_active:
                return
            draw_mode_active = True
            draw_btn.config(state="disabled")
            draw_abort_btn.config(state="normal")
            status_var.set("绘制模式：按住左键拖拽绘制新矩形（保持宽高比），松开后自动替换")
    
        # ---- 重置位置 ----
        def reset_position():
            nonlocal current_x, current_y
            # 如果是主视频模式（允许负偏移且为蓝色），重置到左上角 (0,0)
            if allow_negative_offset and rect_color == 'deepskyblue':
                current_x = 0
                current_y = 0
            else:
                # 否则（子视频/水印）重置到右下角（保留 10px 边距）
                current_x = current_canvas_w - current_w - 10
                current_y = current_canvas_h - current_h - 10
            clamp_rect()
            update_rect_position()
            status_var.set("已重置位置")
    
        # ---- 应用与取消 ----
        def apply():
            clamp_rect()
            on_apply(current_x, current_y, current_w, current_h,
                     current_canvas_w, current_canvas_h)
            win.destroy()
    
        def cancel():
            win.destroy()
    
        # ---- 创建 GUI 控件 ----
        canvas = tk.Canvas(win, width=disp_w, height=disp_h, bg="black", highlightthickness=1)
        canvas.pack(pady=10)
    
        if bg_draw_func:
            bg_draw_func(canvas, scale)
    
        status_var = tk.StringVar(value="红色矩形可拖拽移动。")
        ttk.Label(win, textvariable=status_var, justify=tk.LEFT).pack(pady=5)
    
        coord_var = tk.StringVar(value="")
        coord_label = ttk.Label(win, textvariable=coord_var, font=("", 10))
        coord_label.pack(pady=2)
        if extra_info:
            extra_label = ttk.Label(win, text=extra_info, foreground="orange")
            extra_label.pack(pady=2)
    
        # 画布尺寸控件（主视频模式）
        if show_canvas_controls:
            canvas_ctrl_frame = ttk.Frame(win)
            canvas_ctrl_frame.pack(pady=5)
            ttk.Label(canvas_ctrl_frame, text="画布宽度:").pack(side=tk.LEFT)
            canvas_w_var = tk.StringVar(value=str(canvas_w))
            ttk.Entry(canvas_ctrl_frame, textvariable=canvas_w_var, width=8).pack(side=tk.LEFT, padx=5)
            ttk.Label(canvas_ctrl_frame, text="画布高度:").pack(side=tk.LEFT)
            canvas_h_var = tk.StringVar(value=str(canvas_h))
            ttk.Entry(canvas_ctrl_frame, textvariable=canvas_h_var, width=8).pack(side=tk.LEFT, padx=5)
            ttk.Button(canvas_ctrl_frame, text="应用画布尺寸", command=_apply_canvas_size).pack(side=tk.LEFT, padx=5)
    
        # 绘制矩形控件（子视频/水印模式）
        if allow_resize:
            draw_btn_frame = ttk.Frame(win)
            draw_btn_frame.pack(pady=5)
            draw_btn = ttk.Button(draw_btn_frame, text="绘制新矩形", command=enter_draw_mode)
            draw_btn.pack(side=tk.LEFT, padx=5)
            draw_abort_btn = ttk.Button(draw_btn_frame, text="取消绘制", command=abort_draw, state="disabled")
            draw_abort_btn.pack(side=tk.LEFT, padx=5)
    
        # 通用操作按钮
        action_frame = ttk.Frame(win)
        action_frame.pack(pady=10)
        ttk.Button(action_frame, text="应用", command=apply).pack(side=tk.LEFT, padx=10)
        ttk.Button(action_frame, text="取消", command=cancel).pack(side=tk.LEFT, padx=10)
        ttk.Button(action_frame, text="重置位置", command=reset_position).pack(side=tk.LEFT, padx=10)

        if show_scale_tip:
            tip_text = "提示：重新绘制矩形时，如果比例不对，请先返回上一个界面取消「缩放」的勾选，已保存的上一次缩放会干扰裁剪属性。"
            tip_label = ttk.Label(win, text=tip_text, foreground="gray", 
                                  justify=tk.LEFT, wraplength=win.winfo_width() - 30)
            tip_label.pack(fill=tk.X, padx=10, pady=5)
            def update_wraplength(event):
                tip_label.config(wraplength=win.winfo_width() - 30)
            win.bind("<Configure>", update_wraplength)

        # 绑定事件
        canvas.tag_bind("rect", "<Button-1>", start_move)
        canvas.tag_bind("rect", "<B1-Motion>", on_move)
        canvas.tag_bind("rect", "<ButtonRelease-1>", stop_move)
        canvas.bind("<Button-1>", start_draw, add=True)
        canvas.bind("<B1-Motion>", on_draw_move, add=True)
        canvas.bind("<ButtonRelease-1>", end_draw, add=True)
    
        # 初始化
        clamp_rect()
        rect_id, text_id = create_rect()
        update_coord_display()
        if rect_color == 'deepskyblue':
            status_var.set("拖拽蓝色矩形移动，调整主视频内容在画布中的位置。")
        else:
            status_var.set("红色矩形可拖拽移动。")
        if not allow_resize and 'draw_btn_frame' in locals():
            draw_btn_frame.pack_forget()
    
        center_window(win, disp_w + 20, disp_h + 240)
        win.wait_window()
        parent.lift()
        parent.focus_force()


    # ---------- 主视频位置可视化编辑器 ----------
    def open_visual_pad_editor(self, track_idx, pad_w_var, pad_h_var, off_x_var, off_y_var,
                               live_filt_frame=None, parent=None):
        track = self.merge_tracks[track_idx]
        if track.type != "video":
            return
    
        enabled_videos = self._get_enabled_video_tracks()
        if not enabled_videos:
            messagebox.showerror("错误", "没有启用的视频轨道")
            return
        main_track = enabled_videos[0]
        sub_tracks = enabled_videos[1:]
    
        # ---- 主视频渲染尺寸：优先使用 live_filt_frame 的实时值 ----
        if live_filt_frame is not None:
            main_settings = {
                "crop_enabled": live_filt_frame.crop_enabled.get(),
                "crop_width": live_filt_frame.crop_width.get(),
                "crop_height": live_filt_frame.crop_height.get(),
                "scale_enabled": live_filt_frame.scale_enabled.get(),
                "scale_method": live_filt_frame.scale_method.get(),
                "scale_width": live_filt_frame.scale_width.get(),
                "scale_height": live_filt_frame.scale_height.get(),
                "rotate": live_filt_frame.rotate.get()
            }
            orig_w, orig_h = get_video_dimensions(self.ffprobe_cmd, main_track.file_path)
            if orig_w is None or orig_h is None:
                orig_w, orig_h = 1280, 720
            main_render_w, main_render_h = self.compute_final_size_with_order(orig_w, orig_h, main_settings)
        else:
            main_render_w, main_render_h = self._get_video_render_size(main_track)
            if main_render_w is None:
                messagebox.showerror("错误", "无法获取主视频渲染尺寸")
                return
    
        # 获取当前画布尺寸
        try:
            canvas_w = int(pad_w_var.get().strip()) if pad_w_var.get().strip() else 0
            canvas_h = int(pad_h_var.get().strip()) if pad_h_var.get().strip() else 0
            if canvas_w <= 0 or canvas_h <= 0:
                raise ValueError
        except:
            canvas_w, canvas_h = main_render_w, main_render_h
            pad_w_var.set(str(canvas_w))
            pad_h_var.set(str(canvas_h))
    
        # 获取当前偏移
        try:
            off_x = int(off_x_var.get()) if off_x_var.get().strip() else 0
            off_y = int(off_y_var.get()) if off_y_var.get().strip() else 0
        except:
            off_x, off_y = 0, 0
    
        # 定义应用回调
        def apply_pad(new_x, new_y, new_w, new_h, new_canvas_w, new_canvas_h):
            # 更新轨道设置
            track.enc_settings['pad_enabled'] = True
            track.enc_settings['pad_width'] = str(new_canvas_w)
            track.enc_settings['pad_height'] = str(new_canvas_h)
            track.enc_settings['offset_x'] = str(new_x)
            track.enc_settings['offset_y'] = str(new_y)
            # 同步属性
            track.pad_enabled = True
            track.pad_width = str(new_canvas_w)
            track.pad_height = str(new_canvas_h)
            track.offset_x = str(new_x)
            track.offset_y = str(new_y)
            # 更新界面变量
            pad_w_var.set(str(new_canvas_w))
            pad_h_var.set(str(new_canvas_h))
            off_x_var.set(str(new_x))
            off_y_var.set(str(new_y))
            self.merge_update_track_list()
            self.merge_update_command_preview()
            self._append_info_ui(f"[可视化-主] 已设置画布 {new_canvas_w}x{new_canvas_h}, 偏移 ({new_x}, {new_y})")
    
        # 背景绘制函数（显示其他子视频虚线框）
        def draw_bg(canvas, scale):
            # 主视频内容矩形（用于绘制主视频边界）
            main_render_size = (main_render_w, main_render_h)
            self._draw_background(canvas, canvas_w, canvas_h, scale, main_track, sub_tracks,
                                  off_x, off_y, main_render_size, current_edit_track=None, tag="bg")
    
        # 调用通用编辑器
        self._generic_overlay_editor(
            parent=parent or self.root,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
            rect_x=off_x,
            rect_y=off_y,
            rect_w=main_render_w,
            rect_h=main_render_h,
            on_apply=apply_pad,
            title="可视化编辑画布偏移 - 拖拽蓝色矩形",
            aspect_ratio=None,
            bg_draw_func=draw_bg,
            allow_resize=False,
            show_canvas_controls=True,
            coord_mode='offset',
            allow_negative_offset=True,   # 允许负偏移
            rect_color='deepskyblue',      # 蓝色
            rect_label='主视频',
            min_visible_pixels=10
        )

    # ---------- 水印位置可视化编辑器 ----------
    def open_watermark_overlay_editor(self, canvas_w, canvas_h, wm_w, wm_h, x_var, y_var,
                                      scale_enabled_var=None, scale_w_var=None, scale_h_var=None,
                                      watermark_dict=None, filt_frame=None, parent=None):
        """
        水印可视化编辑器，支持回写位置和缩放尺寸，以及更新水印字典和滤镜框架。
        """
        # 解析当前坐标
        rect_x = safe_eval_expr(x_var.get(), {"W": canvas_w, "H": canvas_h, "w": wm_w, "h": wm_h})
        if rect_x is None:
            rect_x = canvas_w - wm_w - 10
        rect_y = safe_eval_expr(y_var.get(), {"W": canvas_w, "H": canvas_h, "w": wm_w, "h": wm_h})
        if rect_y is None:
            rect_y = canvas_h - wm_h - 10
        rect_x = max(0, min(rect_x, canvas_w - wm_w))
        rect_y = max(0, min(rect_y, canvas_h - wm_h))
    
        def on_apply(new_x, new_y, new_w, new_h, new_canvas_w, new_canvas_h):
            # 更新位置变量
            x_var.set(str(new_x))
            y_var.set(str(new_y))
            # 更新缩放控件
            if scale_enabled_var is not None:
                scale_enabled_var.set(True)
            if scale_w_var is not None:
                scale_w_var.set(str(new_w))
            if scale_h_var is not None:
                scale_h_var.set(str(new_h))
            # 更新水印设置字典（如果提供）
            if watermark_dict is not None:
                watermark_dict["scale_width"] = str(new_w)
                watermark_dict["scale_height"] = str(new_h)
                watermark_dict["scale_method"] = "exact"
                watermark_dict["scale_enabled"] = True
            # 同步滤镜框架的缩放控件（如果提供）
            if filt_frame is not None:
                filt_frame.scale_enabled.set(True)
                filt_frame.scale_method.set("exact")
                filt_frame.scale_width.set(str(new_w))
                filt_frame.scale_height.set(str(new_h))
            self._append_info_ui(f"[可视化-水] 已保存位置: ({new_x}, {new_y}) 尺寸: {new_w}x{new_h}")
    
        title = "可视化编辑水印位置及大小"
        aspect = None
        if wm_h and wm_h > 0:
            aspect = wm_w / wm_h
        self._generic_overlay_editor(parent or self.root, canvas_w, canvas_h,
                                     rect_x, rect_y, wm_w, wm_h,
                                     on_apply, title, aspect, bg_draw_func=None,rect_label='水印',
                                     min_visible_pixels=0,show_scale_tip=True)
    
    # ---------- 从视频位置可视化编辑器 ----------
    def open_visual_overlay_editor(self, track_idx, ov_x_var=None, ov_y_var=None, filt_frame=None, parent=None):
        """
        画中画子视频叠加位置/大小可视化编辑器（保留背景虚线框）
        """
        track = self.merge_tracks[track_idx]
        if track.type != "video":
            return
    
        enabled_videos = self._get_enabled_video_tracks()
        if not enabled_videos:
            messagebox.showerror("错误", "没有启用的视频轨道")
            return
        main_track = enabled_videos[0]
    
        curr_w, curr_h = self._get_video_render_size(track, filt_frame)
        if curr_w is None:
            messagebox.showerror("错误", "无法获取视频渲染尺寸")
            return
    
        canvas_w, canvas_h = self._get_canvas_size(main_track)
    
        # 计算当前矩形位置
        x_expr = track.enc_settings.get('overlay_x', '0')
        y_expr = track.enc_settings.get('overlay_y', '0')
        rect_x = safe_eval_expr(x_expr, {"W": canvas_w, "H": canvas_h, "w": curr_w, "h": curr_h})
        if rect_x is None:
            rect_x = canvas_w - curr_w - 10
        rect_y = safe_eval_expr(y_expr, {"W": canvas_w, "H": canvas_h, "w": curr_w, "h": curr_h})
        if rect_y is None:
            rect_y = canvas_h - curr_h - 10
        rect_x = max(0, min(rect_x, canvas_w - curr_w))
        rect_y = max(0, min(rect_y, canvas_h - curr_h))
    
        def on_apply(new_x, new_y, new_w, new_h, new_canvas_w, new_canvas_h):
            # 更新轨道设置
            track.enc_settings['overlay_x'] = str(new_x)
            track.enc_settings['overlay_y'] = str(new_y)
            track.overlay_x = str(new_x)
            track.overlay_y = str(new_y)
            if ov_x_var is not None:
                ov_x_var.set(str(new_x))
            if ov_y_var is not None:
                ov_y_var.set(str(new_y))
            track.enc_settings["scale_enabled"] = True
            track.enc_settings["scale_width"] = str(new_w)
            track.enc_settings["scale_height"] = str(new_h)
            track.enc_settings["scale_method"] = "exact"
            track.overlay_enabled = True
            if filt_frame is not None:
                filt_frame.scale_enabled.set(True)
                filt_frame.scale_method.set("exact")
                filt_frame.scale_width.set(str(new_w))
                filt_frame.scale_height.set(str(new_h))
            self.merge_update_track_list()
            self.merge_update_command_preview()
            self._append_info_ui(f"[可视化-从] 已保存位置: ({new_x}, {new_y}) 大小: {new_w}x{new_h}")
    
        main_pad_enabled = main_track.enc_settings.get('pad_enabled', False)
        if main_pad_enabled:
            off_x_expr = main_track.enc_settings.get('offset_x', '0')
            off_y_expr = main_track.enc_settings.get('offset_y', '0')
            offset_x = safe_eval_expr(off_x_expr, {"W": canvas_w, "H": canvas_h}) or 0
            offset_y = safe_eval_expr(off_y_expr, {"W": canvas_w, "H": canvas_h}) or 0
        else:
            offset_x, offset_y = 0, 0
        extra_info = f"主视频偏移: X={offset_x}, Y={offset_y}"

        # ----- 定义背景绘制函数（现在内部只需使用 offset_x/offset_y 而不需定义 extra_info）-----
        def draw_bg(canvas, scale):
            # 获取主视频渲染尺寸
            main_render_size = self._get_video_render_size(main_track)
            if main_render_size is None:
                main_render_size = (canvas_w, canvas_h)
            sub_tracks = enabled_videos[1:]
            self._draw_background(canvas, canvas_w, canvas_h, scale, main_track, sub_tracks,
                                  offset_x, offset_y, main_render_size, current_edit_track=track, tag="bg")
    
        title = f"可视化编辑叠加位置 - {os.path.basename(track.file_path)}"
        aspect = None
        if curr_w and curr_h > 0:
            aspect = curr_w / curr_h
        self._generic_overlay_editor(
            parent or self.root,
            canvas_w, canvas_h,
            rect_x, rect_y, curr_w, curr_h,
            on_apply,
            title,
            aspect,
            bg_draw_func=draw_bg,
            extra_info=extra_info,
            rect_label='当前子视频',
            min_visible_pixels=0,
            show_scale_tip=True
        )

    # ---------- 预设管理 ----------
    def load_preset_list(self):
        presets = self.preset_manager.load_all()
        preset_names = list(presets.keys())
        self.preset_combo['values'] = preset_names

    def _clean_settings(self, settings: dict, defaults: dict = None) -> dict:
        """
        递归清洗设置字典，移除与默认值相同的字段。
        """
        if defaults is None:
            defaults = self.default_settings
        cleaned = {}
        for key, value in settings.items():
            if key not in defaults:
                # 如果键不在默认字典中，保留（通常不会发生）
                cleaned[key] = value
                continue
            default_value = defaults[key]
            if isinstance(value, dict) and isinstance(default_value, dict):
                # 递归处理子字典，并传入对应的默认值
                sub_cleaned = self._clean_settings(value, default_value)
                if sub_cleaned:  # 只有子字典非空才保留
                    cleaned[key] = sub_cleaned
            elif value != default_value:
                cleaned[key] = value
            # 值相同则忽略
        return cleaned

    def save_preset(self):
        preset_name = simpledialog.askstring("保存预设", "请输入预设名称:", parent=self.root)
        if not preset_name:
            return
        preset_settings = self.get_current_settings()

        # ---- 移除水印设置（不保存到预设文件） ----
        preset_settings.pop("watermark", None)
        # ---- 移除分段拼接数据（如果您也不希望保存） ----
        preset_settings.pop("segment_enabled", None)
        preset_settings.pop("segments", None)
        # ---- 移除截取参数 ----
        preset_settings.pop("trim_enabled", None)
        preset_settings.pop("trim_start", None)
        preset_settings.pop("trim_end", None)
        preset_settings.pop("precise_trim", None)
        preset_settings.pop("combo_seek", None)
        preset_settings.pop("combo_threshold", None)
    
        # 清洗
#        print("原始设置:", preset_settings)
        cleaned = self._clean_settings(preset_settings)
 #       print("清洗后:", cleaned)
        self.preset_manager.save_preset(preset_name, cleaned)
        self.load_preset_list()
        messagebox.showinfo("成功", f"预设“{preset_name}”已保存到:\n{self.preset_file_path}")

    def load_preset(self, preset_name):
        if not preset_name:
            return
        presets = self.preset_manager.load_all()
        if preset_name not in presets:
            return
        self.load_settings_into_ui(presets[preset_name])
        messagebox.showinfo("成功", f"已加载预设“{preset_name}”")

    def delete_preset(self):
        preset_name = self.preset_name.get()
        if not preset_name:
            messagebox.showwarning("警告", "请先选择一个预设")
            return
        if not messagebox.askyesno("确认删除", f"确定要删除预设“{preset_name}”吗？"):
            return
        if self.preset_manager.delete_preset(preset_name):
            self.load_preset_list()
            self.preset_name.set("")
            messagebox.showinfo("成功", f"预设“{preset_name}”已删除")
        else:
            messagebox.showerror("错误", "删除失败")

    def export_all_presets(self):
        if not os.path.exists(self.preset_file_path):
            if messagebox.askyesno("提示", "当前没有预设文件，是否创建一个空的预设文件并导出？"):
                with open(self.preset_file_path, 'w', encoding='utf-8') as f:
                    json.dump({}, f, indent=4)
            else:
                return
        save_path = filedialog.asksaveasfilename(
            title="导出全部预设 (备份)",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialfile="ffmpeg_presets_backup.json"
        )
        if not save_path:
            return
        try:
            shutil.copy2(self.preset_file_path, save_path)
            self._append_info_ui(f"✅ 全部预设已备份到: {save_path}")
            messagebox.showinfo("导出成功", f"预设库已导出至:\n{save_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def import_presets(self):
        import_path = filedialog.askopenfilename(
            title="导入预设库",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if not import_path:
            return
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                imported = json.load(f)
        except Exception as e:
            messagebox.showerror("读取失败", f"无法读取文件:\n{e}")
            return
        if not isinstance(imported, dict):
            messagebox.showerror("格式错误", "导入的文件必须是 JSON 对象（键为预设名称，值为设置字典）")
            return
        for preset_name, settings in imported.items():
            if isinstance(settings, dict) and "custom_args" in settings:
                custom = settings["custom_args"].strip()
                if re.search(r'[;&|`$]', custom):
                    self._append_info_ui(f"警告：预设 '{preset_name}' 中的自定义参数包含危险字符，已清空")
                    settings["custom_args"] = ""
        current = self.preset_manager.load_all()
        player_cfg = self.preset_manager.load_player_settings()
        answer = messagebox.askyesno(
            "导入方式",
            f"当前有 {len(current)} 个预设，导入文件包含 {len(imported)} 个预设。\n"
            "是否替换整个预设库？\n（选“是”将完全替换；选“否”则合并，同名预设将被覆盖）"
        )
        if answer:
            new_presets = imported
        else:
            new_presets = current.copy()
            new_presets.update(imported)
        full_data = new_presets.copy()
        full_data["player_settings"] = player_cfg
        try:
            with open(self.preset_file_path, 'w', encoding='utf-8') as f:
                json.dump(full_data, f, indent=4, ensure_ascii=False)
            self.load_preset_list()
            self._append_info_ui(f"预设库已更新，共 {len(new_presets)} 个预设")
            messagebox.showinfo("导入成功", f"预设库已更新，当前共 {len(new_presets)} 个预设")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    # ---------- 预览与 UI 辅助 ----------
    def preview_current_file(self):
        path = self.input_file.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("错误", "请先选择一个有效的输入文件")
            return
        settings = self.get_current_settings()
        self._preview_with_settings(path, settings)

    def preview_selected_task(self):
        selected = self.task_tree.selection()
        if not selected:
            messagebox.showwarning("警告", "请先选中一个任务")
            return
        idx = int(selected[0])
        task = self.tasks[idx]
        if not os.path.exists(task.input):
            messagebox.showerror("错误", f"输入文件不存在: {task.input}")
            return
        self._preview_with_settings(task.input, task.settings)

    def toggle_only_audio_mode(self):
        state = tk.DISABLED if self.audio_frame.only_audio.get() else tk.NORMAL
        self._set_recursive_state(self.video_encoder, state)
        self._set_recursive_state(self.video_filter, state)
        self.update_command_preview()
    
    def _set_recursive_state(self, widget, state):
        try:
            widget.config(state=state)
        except:
            pass
        for child in widget.winfo_children():
            self._set_recursive_state(child, state)


    def open_segment_editor(self):
        if not self.segment_enabled.get():
            messagebox.showinfo("提示", "请先勾选「启用分段拼接模式」再打开设置窗口。")
            return
        import copy
        initial_segments = copy.deepcopy(self.segments)
        editor = SegmentEditor(self.root, initial_segments, self)
        self.root.wait_window(editor.window)
        if editor.result is not None:
            self.segments = editor.result
            self.update_command_preview()


    def update_command_preview(self, *args):
        """防抖版刷新命令预览"""
        if self._preview_after_id:
            self.root.after_cancel(self._preview_after_id)
            self._preview_after_id = None
        self._preview_after_id = self.root.after(50, self._do_update_command_preview)

    def _do_update_command_preview(self):
        """实际执行命令刷新的函数"""
        self._preview_after_id = None
        if getattr(self, '_loading_preset', False):
            return
        if hasattr(self, '_updating_preview') and self._updating_preview:
            return
        self._updating_preview = True
        try:
            # ---- 水印/画中画禁用组合跳转 ----
            watermark_enabled = self.watermark_settings.get("enabled", False)
            pip_enabled = self.pip_enabled.get()
            if watermark_enabled or pip_enabled:
                if self.trim_frame.show_combo_seek and self.trim_frame.combo_seek.get():
                    self.trim_frame.combo_seek.set(False)
                    self._append_info_ui("[提示] 水印/画中画模式下已自动禁用组合跳转。")
                    if self.trim_frame.combo_check:
                        self.trim_frame.combo_check.config(state='disabled')
            else:
                if self.trim_frame.show_combo_seek and self.trim_frame.combo_check:
                    self.trim_frame.combo_check.config(state='normal')
            # -------------------------------------------------
    
            input_file = self.input_file.get()
            try:
                if not input_file:
                    cmd_list = self.generate_ffmpeg_command("{input}", "{output}", self.get_current_settings())
                else:
                    settings = self.get_current_settings()
                    output_path = self.generate_output_path(input_file, settings)
                    cmd_list = self.generate_ffmpeg_command(input_file, output_path, settings)
                cmd_str = format_cmd_for_display(cmd_list)
            except Exception as e:
                cmd_str = f"生成命令时出错: {e}"
    
            # 更新预览区（根据全局开关控制状态）
            preview = self.cmd_preview
            preview.config(state='normal')
            preview.delete(1.0, tk.END)
            preview.insert(tk.END, cmd_str)
            if hasattr(self, 'preview_editable_var') and self.preview_editable_var.get():
                preview.config(state='normal')
            else:
                preview.config(state='disabled')
    
            # ---- 同步精准截取 ----
            try:
                watermark_enabled = self.watermark_settings.get("enabled", False)
                if (watermark_enabled or self.pip_enabled.get()) and self.trim_frame.trim_enabled.get():
                    if not self.trim_frame.precise_trim.get():
                        self.trim_frame.precise_trim.set(True)
                    self.trim_frame.precise_check.config(state='disabled')
                    if not self._watermark_precise_hint_shown:
                        self._append_info_ui("[水印/画中画] 已自动启用精准截取（确保叠加对齐）。")
                        self._watermark_precise_hint_shown = True
                else:
                    self.trim_frame.precise_check.config(state='normal')
            except Exception as e:
                pass
        finally:
            self._updating_preview = False


    # ---------- 同名文件处理 ----------
    def _unique_path(self, path: str) -> str:
        """生成不冲突的唯一路径（自动加序号）"""
        dirname = os.path.dirname(path)
        basename, ext = os.path.splitext(os.path.basename(path))
        counter = 1
        new_path = path
        # 检查文件系统存在或任务列表中已占用
        while os.path.exists(new_path) or any(t.output == new_path for t in self.tasks):
            new_path = os.path.join(dirname, f"{basename} ({counter}){ext}")
            counter += 1
        return new_path

    def _resolve_path_conflict(self, output_path: str, show_dialog: bool = True):
        """
        根据当前策略处理同名文件冲突，返回最终路径。
        若策略为 'ask' 且用户取消覆盖，则自动重命名。
        永远不会返回 None。
        """
        if not output_path:
            return output_path
        policy = self.overwrite_policy.get()
        
        def conflict(path):
            return os.path.exists(path) or any(t.output == path for t in self.tasks)
        
        if policy == "overwrite":
            return output_path
        elif policy == "rename":
            return self._unique_path(output_path)
        else:  # "ask"
            if not show_dialog:
                # 预览模式：直接重命名，不弹窗
                return self._unique_path(output_path)
            else:
                if conflict(output_path):
                    if messagebox.askyesno("文件已存在", f"输出文件已存在:\n{output_path}\n\n是否覆盖？"):
                        return output_path
                    else:
                        return self._unique_path(output_path)
                return output_path


    # ---------- 任务管理 ----------
    def is_duplicate_task(self, input_path, output_path):
        """检查输出路径是否已被已有任务占用（无论输入是否相同）"""
        norm_out = normalize_path(output_path)
        for task in self.tasks:
            if normalize_path(task.output) == norm_out:
                return True
        return False


    def add_task(self, input_path, settings=None):
        if settings is None:
            settings = self.get_current_settings()
    
        # 如果水印未启用（路径为空），则移除 watermark 键，避免残留参数污染任务
        if not settings.get("watermark", {}).get("enabled", False) or not settings.get("watermark", {}).get("file_path", "").strip():
            settings.pop("watermark", None)
    
        # 分段拼接设置：尊重调用方传入的值，否则使用界面当前值
        if "segment_enabled" not in settings:
            settings["segment_enabled"] = self.segment_enabled.get()
        if "segments" not in settings:
            settings["segments"] = copy.deepcopy(self.segments)
    
        try:
            output_path = self.generate_output_path(input_path, settings)
            self._append_info_ui(f"生成输出路径: {output_path}")
        except Exception as e:
            err_msg = f"生成输出路径失败: {e}"
            self._append_info_ui(err_msg)
            import traceback
            self._append_info_ui(traceback.format_exc())
            messagebox.showerror("错误", err_msg)
            return False
    
        output_path = self._resolve_path_conflict(output_path)
        if output_path is None:
            self._append_info_ui("添加任务已取消")
            return False
    
        try:
            cmd_list = self.generate_ffmpeg_command(input_path, output_path, settings)
            self._append_info_ui(f"命令生成成功，参数个数: {len(cmd_list)}")
        except Exception as e:
            err_msg = f"命令生成错误: {e}"
            self._append_info_ui(err_msg)
            import traceback
            self._append_info_ui(traceback.format_exc())
            messagebox.showerror("命令生成错误", err_msg)
            return False
    
        task = Task(input_path, output_path, settings, cmd_list)
        self.tasks.append(task)
        self.update_task_list()
        self._append_info_ui(f"✅ 已添加任务: {os.path.basename(input_path)} -> {output_path}")
        return True

    def add_current_as_task(self):
        input_path = self.input_file.get()
        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("错误", "请先在输入文件中选择一个有效的文件")
            return
        self.add_task(input_path)

    def update_task_list(self):
        """刷新任务列表，状态列显示进度（转码中时）"""
        # 清空现有列表
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)
    
        for i, task in enumerate(self.tasks):
            seq = i + 1
            tag = 'odd' if i % 2 == 0 else 'even'
            # 状态显示：转码中显示进度百分比
            if task.status == "转码中":
                if task.total_sec > 0:
                    status_display = f"转码中 {task.progress}% ({task.current_sec}/{task.total_sec} 秒)"
                else:
                    status_display = f"转码中 {task.progress}%"
            else:
                status_display = task.status
    
            self.task_tree.insert("", tk.END, iid=str(i), values=(
                seq,
                os.path.basename(task.input),
                task.output,
                task.get_short_cmd(),
                status_display,
                task.error_msg[:100] if task.error_msg else ""
            ), tags=(tag,))

    def remove_selected_tasks(self):
        selected = self.task_tree.selection()
        if not selected: return
        indices = sorted([int(iid) for iid in selected], reverse=True)
        for idx in indices:
            if 0 <= idx < len(self.tasks):
                if self.tasks[idx].status == "转码中":
                    messagebox.showwarning("无法删除", f"任务 {os.path.basename(self.tasks[idx].input)} 正在转码中，请先停止队列")
                    continue
                del self.tasks[idx]
        self.update_task_list()

    def clear_all_tasks(self):
        if self.is_processing:
            messagebox.showwarning("警告", "请先停止队列或等待完成后再清空")
            return
        self.tasks.clear()
        self.update_task_list()

    def clear_finished_tasks(self):
        self.tasks = [t for t in self.tasks if t.status not in ("完成", "失败")]
        self.update_task_list()

    def stop_queue(self):
        self.stop_flag = True
        self._append_info_ui("收到停止信号，当前正在运行的任务将继续完成，不再启动新任务")
        self.root.after(100, self._check_and_finish_if_idle)
    
    def _check_and_finish_if_idle(self):
        if self.stop_flag and not self.running_futures:
            self._finish_queue()

    # ---------- 并行队列处理 ----------
    @staticmethod
    def is_hardware_encoder(encoder):
        hw_keywords = ('nvenc', 'qsv', 'amf', 'vaapi', 'videotoolbox')
        encoder_lower = encoder.lower()
        return any(kw in encoder_lower for kw in hw_keywords)

    def start_queue(self):
        if self.is_processing:
            if not self.running_futures and not self.pending_tasks:
                self._finish_queue()
            else:
                messagebox.showinfo("提示", "队列已在运行中")
            return
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None
        self.pending_tasks = [t for t in self.tasks if t.status == "等待"]
        if not self.pending_tasks:
            messagebox.showinfo("提示", "没有等待中的任务")
            return
        self.is_processing = True
        self.stop_flag = False
        max_workers = self.max_parallel.get()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._append_info_ui(f"启动并行队列，最大并行任务数: {max_workers}，硬件编码最大并发: {self.max_hw_parallel.get()}")
        self._submit_next_batch()

    def _submit_next_batch(self):
        if not self.is_processing or self.executor is None:
            return
    
        # ---- 停止信号处理 ----
        if self.stop_flag:
            # 如果有正在运行的任务，让它们继续运行，但不启动新任务
            if not self.running_futures:
                self._finish_queue()   # 所有任务已完成，结束队列
            return
    
        if not self.pending_tasks and not self.running_futures:
            self._finish_queue()
            return
    
        max_total = self.max_parallel.get()
        max_hw = self.max_hw_parallel.get()
    
        if len(self.running_futures) >= max_total:
            return
    
        # 查找可提交的任务
        to_submit_idx = None
        for idx, task in enumerate(self.pending_tasks):
            if task.status != "等待":
                continue
            encoder = task.settings.get("encoder", "")
            is_hw = self.is_hardware_encoder(encoder)
            if is_hw and self.current_hw_encoding_count >= max_hw:
                continue
            else:
                to_submit_idx = idx
                break

        if to_submit_idx is None:
            return

        task = self.pending_tasks.pop(to_submit_idx)
        if task.status != "等待":
            return

        future = self.executor.submit(self._process_single_task, task)
        self.running_futures.add(future)
        if self.is_hardware_encoder(task.settings.get("encoder", "")):
            self.current_hw_encoding_count += 1
        future.add_done_callback(self._on_task_done)

        self.root.after(10, self._submit_next_batch)

    def safe_append_detail(self, text):
        self.root.after(0, lambda: self.append_detail(text))



    def _process_single_task(self, task):
        """处理单个任务（队列模式）"""
        task.status = "转码中"
        self._update_task_list_ui()
        self._append_info_ui(f"\n========== 开始转码: {os.path.basename(task.input)} ==========")
        cmd_str = format_cmd_for_display(task.cmd)
        self._append_info_ui(f">>> {cmd_str}")
        self.ensure_output_dir(task.output)
    
        # 获取视频总时长用于进度
        total_duration = 0
        if task.settings.get("segment_enabled", False) and task.settings.get("segments"):
            # 分段拼接模式：计算所有片段时长之和
            segments = task.settings.get("segments", [])
            total_duration = 0.0
            for seg in segments:
                start = time_to_seconds(seg.get("start", "0"))
                end = time_to_seconds(seg.get("end", "0"))
                if start is not None and end is not None and end > start:
                    total_duration += (end - start)
            # 如果片段总时长计算失败，回退到原始方式
            if total_duration <= 0:
                raw_duration = self._get_media_duration(task.input)
                total_duration = self._get_effective_duration(task.settings, raw_duration) if raw_duration is not None else 0
        else:
            raw_duration = self._get_media_duration(task.input)
            total_duration = self._get_effective_duration(task.settings, raw_duration) if raw_duration is not None else 0
        if total_duration is None:
            total_duration = 0
    
        proc = None
        try:
            proc = subprocess.Popen(
                task.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            with self._proc_lock:
                self.running_procs.append(proc)
                self._running_tasks.append((proc, task))
    
            for line in proc.stdout:
                if not self._is_ffmpeg_banner_line(line):
                    self.safe_append_detail(line)
                    if total_duration > 0 and "time=" in line:
                        match = re.search(r'time=(\d+):(\d+):(\d+\.?\d*)', line)
                        if match:
                            h, m, s = match.groups()
                            current_sec = int(h) * 3600 + int(m) * 60 + float(s)
                            self.update_progress(current=int(current_sec), total=int(total_duration), task=task, log_progress=False)
    
            retcode = proc.wait()
            # 优先判断用户停止
            if task.stopped_by_user:
                task.status = "已停止"
                self._append_info_ui(f"⏹️ 任务已停止: {os.path.basename(task.input)}")
            elif retcode == 0:
                task.status = "完成"
                self._append_info_ui(f"✅ 任务完成: {os.path.basename(task.input)}")
                self._log_command_to_file(cmd_str)
            else:
                task.status = "失败"
                task.error_msg = f"返回码 {retcode}"
                self._append_info_ui(f"任务失败: {os.path.basename(task.input)} (返回码 {retcode})")
            self._update_task_list_ui()
        except Exception as e:
            self._append_info_ui(f"任务异常: {e}")
            task.status = "失败"
            task.error_msg = str(e)
            self._update_task_list_ui()
        finally:
            with self._proc_lock:
                if proc in self.running_procs:
                    self.running_procs.remove(proc)
                self._running_tasks = [(p, t) for (p, t) in self._running_tasks if p != proc]
            self.update_progress(current=0, total=0, task=task, log_progress=False)
        return task

    def _on_task_done(self, future):
        task = future.result()
        if self.is_hardware_encoder(task.settings.get("encoder", "")):
            self.current_hw_encoding_count -= 1
            self.current_hw_encoding_count = max(0, self.current_hw_encoding_count)
        self.running_futures.discard(future)
        self.root.after(100, self._submit_next_batch)

    def _finish_queue(self):
        if not self.is_processing:
            return
        self.is_processing = False
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None
        self.current_hw_encoding_count = 0
        self.stop_flag = False
        if self.stop_flag:
            self._append_info_ui("\n队列已停止")
        else:
            self._append_info_ui("\n所有任务处理完成")
        self.stop_flag = False

    def _update_task_list_ui(self):
        self.root.after(0, self.update_task_list)

    def _append_info_ui(self, text: str):
        self.root.after(0, lambda: self.append_info(text))

    def _log_command_to_file(self, cmd_str: str):
        """将成功执行的命令记录到日志文件（受开关控制）"""
        if not self.log_enabled_var.get():
            return
        log_path = self.log_path_var.get().strip()
        if not log_path:
            return
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{cmd_str}\n")
        except Exception as e:
            self._append_info_ui(f"无法写入命令日志: {e}")


    def transcode_single(self):
        input_file = self.input_file.get()
        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("错误", "请选择有效的输入文件")
            return
        settings = self.get_current_settings()
        output_file = self.generate_output_path(input_file, settings)
        # ---- 新增：处理冲突 ----
        output_file = self._resolve_path_conflict(output_file)
        self.ensure_output_dir(output_file)
        try:
            cmd_list = self.generate_ffmpeg_command(input_file, output_file, settings)
        except ValueError as e:
            messagebox.showerror("命令生成错误", str(e))
            return
        threading.Thread(target=self._run_single_transcode, args=(cmd_list, input_file, settings), daemon=True).start()

    def refresh_with_reset(self):
        """点击刷新按钮时：先重置列宽，再刷新命令预览"""
        self.reset_task_tree_columns()
        self.update_command_preview()   #刷新

    def reset_task_tree_columns(self):
        """重置任务列表列宽为默认值（与创建时一致）"""
        if hasattr(self, 'task_tree'):
            self.task_tree.column("序号", width=25)
            self.task_tree.column("文件名", width=75)
            self.task_tree.column("输出路径", width=100)
            self.task_tree.column("命令 (简洁) 双击编辑", width=410)
            self.task_tree.column("状态", width=52)
            self.task_tree.column("错误信息", width=30)

    def _run_single_transcode(self, cmd_list, input_name, settings):
        """单文件转码（非队列）"""
        self._append_info_ui(f"\n========== 当前选择转码: {os.path.basename(input_name)} ==========")
        cmd_str = format_cmd_for_display(cmd_list)
        self._append_info_ui(f">>> {cmd_str}")
    
        total_duration = 0
        if settings.get("segment_enabled", False):
            total_duration = self._calc_segments_total_duration(settings)
            if total_duration <= 0:
                raw_duration = self._get_media_duration(input_name)
                if raw_duration is not None:
                    total_duration = raw_duration
        else:
            raw_duration = self._get_media_duration(input_name)
            total_duration = self._get_effective_duration(settings, raw_duration) if raw_duration is not None else 0
        if total_duration is None:
            total_duration = 0
    
        proc = None
        try:
            proc = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            with self._proc_lock:
                self.running_procs.append(proc)
    
            for line in proc.stdout:
                if not self._is_ffmpeg_banner_line(line):
                    self.safe_append_detail(line)
    
                    if total_duration > 0 and "time=" in line:
                        match = re.search(r'time=(\d+):(\d+):(\d+\.?\d*)', line)
                        if match:
                            h, m, s = match.groups()
                            current_sec = int(h) * 3600 + int(m) * 60 + float(s)
                            self.update_progress(current=int(current_sec), total=int(total_duration), task=None, log_progress=True)
    
            retcode = proc.wait()
            if retcode == 0:
                self._append_info_ui(f"✅ 当前选择转码完成: {os.path.basename(input_name)}")
                self._log_command_to_file(cmd_str)
            else:
                self._append_info_ui(f"当前选择转码失败，返回码 {retcode}")
        except Exception as e:
            self._append_info_ui(f"转码异常: {e}")
        finally:
            with self._proc_lock:
                if proc in self.running_procs:
                    self.running_procs.remove(proc)
            self.update_progress(current=0, total=0, task=None, log_progress=True)

    def ensure_output_dir(self, output_path):
        dirname = os.path.dirname(output_path)
        if dirname and not os.path.exists(dirname):
            if sys.platform == "win32":
                root_dirs = ('C:\\', 'C:/')
                if dirname.upper() in root_dirs:
                    raise ValueError(f"禁止将输出文件直接写入C盘根目录: {dirname}")
            os.makedirs(dirname, exist_ok=True)

    # ---------- 导出脚本、编辑任务 ----------
    def export_script(self):
        if not self.tasks:
            messagebox.showinfo("提示", "任务列表为空，无法导出")
            return
        file_path = filedialog.asksaveasfilename(
            title="导出脚本",
            defaultextension=".bat",
            filetypes=[("Windows批处理", "*.bat"), ("Linux/macOS Shell", "*.sh"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
        try:
            if file_path.lower().endswith(".sh"):
                script_lines = ["#!/bin/bash", "# FFmpeg batch script", ""]
                enc = "utf-8"
            else:
                script_lines = ["@echo off", ":: FFmpeg batch script", "", "chcp 65001 >nul"]
                enc = "utf-8-sig"
            for task in self.tasks:
                script_lines.append(f"echo Processing: {os.path.basename(task.input)}")
                script_lines.append(format_cmd_for_display(task.cmd))
                script_lines.append("")
            script_lines.append("echo All tasks completed.")
            with open(file_path, 'w', encoding=enc) as f:
                f.write("\n".join(script_lines))
            messagebox.showinfo("成功", f"脚本已导出到:\n{file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def edit_task(self, task, task_index):
        if task.status not in ("等待", "失败", "完成"):
            messagebox.showwarning("无法编辑", f"任务状态为“{task.status}”，只能编辑等待、失败或已完成的任务。")
            return
    
        with self.SafeToplevel(self.root) as win:
            win.title(f"编辑任务 - {os.path.basename(task.input)}")
            center_window(win, 800, 460)
            
            notebook = ttk.Notebook(win)
            notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
            # 输入/输出页面
            page_io = ttk.Frame(notebook)
            notebook.add(page_io, text="输入/输出")
            out_dir_var = tk.StringVar(value=task.settings.get("output_dir", ""))
            suffix_var = tk.StringVar(value=task.settings.get("output_suffix", ""))
            custom_var = tk.StringVar(value=task.settings.get("custom_output_name", ""))
            container_var = tk.StringVar(value=task.settings.get("output_container", "mp4"))
            ttk.Label(page_io, text="输出目录:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
            ttk.Entry(page_io, textvariable=out_dir_var, width=60).grid(row=0, column=1, padx=5, pady=5)
            
            ttk.Button(page_io, text="浏览", command=lambda: out_dir_var.set(normalize_path(filedialog.askdirectory() or out_dir_var.get()))).grid(row=0, column=2, padx=5)
            ttk.Label(page_io, text="文件名后缀:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
            ttk.Entry(page_io, textvariable=suffix_var, width=30).grid(row=1, column=1, sticky="w", padx=5)
            ttk.Label(page_io, text="自定义完整名称:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
            ttk.Entry(page_io, textvariable=custom_var, width=60).grid(row=2, column=1, padx=5)
            ttk.Label(page_io, text="输出容器:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
            ttk.Combobox(page_io, textvariable=container_var, values=["mp4","mkv","mov","avi","webm","gif","webp"], state="readonly", width=8).grid(row=3, column=1, sticky="w", padx=5)
    
            # 视频编码页面
            page_enc = ttk.Frame(notebook)
            notebook.add(page_enc, text="视频编码")
            enc_frame = VideoEncoderFrame(page_enc, app=self)
            enc_frame.pack(fill=tk.X, padx=5, pady=5)
            enc_frame.set_settings(task.settings)
            
            # 视频滤镜页面
            page_filt = ttk.Frame(notebook)
            notebook.add(page_filt, text="视频滤镜")
            filt_frame = VideoFilterFrame(page_filt, app=self)
            filt_frame.current_file = task.input
            filt_frame.set_override_settings(task.settings)
            filt_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            filt_frame.set_settings(task.settings)
            if "enhance" in task.settings:
                filt_frame.set_enhance_settings(task.settings["enhance"])

            filt_frame.set_get_trim_settings_callback(lambda: trim_frame.get_settings())

            # 音频页面
            page_audio = ttk.Frame(notebook)
            notebook.add(page_audio, text="音频")
            container = ttk.Frame(page_audio)
            container.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
            audio_frame = AudioFrame(container, enable_checkbox=True)
            audio_frame.pack(fill=tk.X)
            audio_frame.set_settings(task.settings)
            audio_frame.volume_value.trace_add("write", lambda *a: update_preview())
            audio_frame.volume_enabled.trace_add("write", lambda *a: update_preview())
    
            # 截取片段页面
            page_trim = ttk.Frame(notebook)
            notebook.add(page_trim, text="截取片段")
            trim_frame = TrimFrame(page_trim)
            trim_frame.pack(fill=tk.X, padx=5, pady=5)
            trim_frame.set_settings(task.settings)
            
            filt_frame.set_get_trim_settings_callback(lambda: trim_frame.get_settings())
            trim_frame.precise_trim.trace_add("write", lambda *a: update_preview())


            # ----- 分段拼接页面 -----
            page_segment = ttk.Frame(notebook)
            notebook.add(page_segment, text="分段拼接")
            
            # 从任务设置中读取
            seg_enabled = task.settings.get("segment_enabled", False)
            segments = copy.deepcopy(task.settings.get("segments", []))
            
            # 局部变量（用于编辑）
            seg_enabled_var = tk.BooleanVar(value=seg_enabled)
            seg_enabled_var.trace_add("write", lambda *args: update_preview())
            seg_list = segments  # 直接引用，修改后保存到 task
            
            seg_control_frame = ttk.Frame(page_segment)
            seg_control_frame.pack(fill=tk.X, pady=10)
            
            ttk.Checkbutton(seg_control_frame, text="启用分段拼接模式 (将忽略『截取片段』设置)",
                            variable=seg_enabled_var).pack(side=tk.LEFT, padx=5)
            
            def open_task_segment_editor():
                if not seg_enabled_var.get():
                    messagebox.showinfo("提示", "请先勾选「启用分段拼接模式」再打开设置窗口。")
                    return
                # 打开编辑器，传入 seg_list 和 seg_enabled_var 的引用
                editor = SegmentEditor(win, seg_list, self)  # 注意：这里的 self 是主程序
                self.root.wait_window(editor.window)
                if editor.result is not None:
                    seg_list.clear()
                    seg_list.extend(editor.result)
                    # 更新预览
                    update_preview()
            
            ttk.Button(seg_control_frame, text="打开分段设置...",
                       command=open_task_segment_editor).pack(side=tk.LEFT, padx=10)
            

            ttk.Label(
                page_segment,
                text="勾选启用后，视频将按片段列表裁剪并拼接，所有片段使用相同的全局编码/滤镜设置。\n\n"
                     "   建议使用（mpv、PotPlayer）等播放器打开视频，定位并获取精确到毫秒的时间。\n\n"
                     "   典型用途：简单混剪、去中间广告、提取精华片段等。",
                foreground="grey",
                wraplength=800,
                justify=tk.LEFT
            ).pack(anchor=tk.W, padx=10, pady=(5,0))


            # 高级选项页面
            page_adv = ttk.Frame(notebook)
            notebook.add(page_adv, text="高级选项")
            

            
            # ---- AdvancedFrame，并传入 update_callback ----
            watermark_dict = task.settings.get("watermark", {})   # 防止 KeyError
            adv_frame = AdvancedFrame(
                page_adv,
                update_callback=None,
                app=self,
                show_adaptive=True,
                watermark_dict=watermark_dict
            )
            task.settings["watermark"] = adv_frame.watermark_dict
            adv_frame.pack(fill=tk.X, padx=5, pady=5)
            adv_frame.set_settings(task.settings)



            # 水印编辑按钮新命令
            def open_task_watermark():
                task_watermark = task.settings.get("watermark", {})
                if not task_watermark.get("file_path"):
                    messagebox.showwarning("提示", "请先在任务设置中输入水印文件路径")
                    return
            
                def on_save(new_wm):
                    adv_frame.watermark_dict.update(new_wm)
                    adv_frame.wm_path_var.set(adv_frame.watermark_dict.get("file_path", ""))
                    if hasattr(adv_frame, 'adaptive_var'):
                        adv_frame.adaptive_var.set(adv_frame.watermark_dict.get("adaptive", False))
                    update_preview()
                    self.update_task_list()
                    self._append_info_ui("任务水印已更新")
            
                # 计算主视频的最终渲染尺寸（严格按 crop → rotate → scale 顺序）
                main_video_size = None
                if task.input and os.path.exists(task.input):
                    main_settings = task.settings
                    # 直接获取原始尺寸（不含旋转）
                    orig_w, orig_h = get_video_dimensions(self.ffprobe_cmd, task.input)
                    if orig_w is not None and orig_h is not None:
                        main_w, main_h = self.compute_final_size_with_order(orig_w, orig_h, main_settings)
                        if main_w > 0 and main_h > 0:
                            main_video_size = (main_w, main_h)
            
                self.edit_video_settings(
                    title="编辑任务水印",
                    initial_settings=task_watermark,
                    on_save=on_save,
                    file_path=task_watermark.get("file_path"),
                    is_watermark=True,
                    parent=win,
                    track_obj=None,
                    canvas_file=task.input,
                    main_video_size=main_video_size
                )
            
            # 替换 水印按钮的命令
            if hasattr(adv_frame, 'watermark_btn'):
                adv_frame.watermark_btn.config(command=open_task_watermark)
            

            # ---- 命令预览区和 update_preview 函数 ----
            preview_frame = ttk.LabelFrame(win, text="新命令预览", padding="5")
            preview_frame.pack(fill=tk.X, pady=5, padx=5)
            preview_text = scrolledtext.ScrolledText(preview_frame, height=10, wrap=tk.WORD)
            preview_text.pack(fill=tk.BOTH, expand=True)
            
            # 根据全局开关设置初始状态
            if hasattr(self, 'preview_editable_var') and self.preview_editable_var.get():
                preview_text.config(state='normal')
            else:
                preview_text.config(state='disabled')
            
            def update_preview(*args):

                current_state = preview_text.cget('state')
                if task.is_custom:
                    # 直接显示保存的命令   # 流提取相关
                    cmd_str = format_cmd_for_display(task.cmd)
                    preview_text.config(state='normal')
                    preview_text.delete(1.0, tk.END)
                    preview_text.insert(tk.END, cmd_str)
                    preview_text.config(state=current_state)
                    return

                new_settings = {}
                new_settings.update(enc_frame.get_settings())
                new_settings.update(filt_frame.get_settings())
                new_settings.update(audio_frame.get_settings())
                new_settings.update(trim_frame.get_settings())
                new_settings.update(adv_frame.get_settings())  # 这里 adv_frame 将在后面创建，但函数定义时不会执行，所以没问题
                new_settings["output_dir"] = out_dir_var.get()
                new_settings["output_suffix"] = suffix_var.get()
                new_settings["custom_output_name"] = custom_var.get()
                new_settings["output_container"] = container_var.get()
                # 保留水印设置
                new_settings["watermark"] = task.settings.get("watermark", self.watermark_settings.copy())
                new_out = self.generate_output_path(task.input, new_settings)
                new_settings["enhance"] = filt_frame.get_enhance_settings()

                new_settings["segment_enabled"] = seg_enabled_var.get()
                new_settings["segments"] = copy.deepcopy(seg_list)
              #  print(f"[edit_task update_preview] 获取到 enhance = {new_settings['enhance']}")
                try:
                    new_cmd_list = self.generate_ffmpeg_command(task.input, new_out, new_settings)
                    new_cmd_str = format_cmd_for_display(new_cmd_list)
                except ValueError as e:
                    new_cmd_str = f"参数错误: {e}"
            
                # 更新预览，保持用户状态
                current_state = preview_text.cget('state')
                preview_text.config(state='normal')
                preview_text.delete(1.0, tk.END)
                preview_text.insert(tk.END, new_cmd_str)
                preview_text.config(state=current_state)

            filt_frame._preview_callback = update_preview
            adv_frame.update_callback = update_preview
            trim_frame.update_callback = update_preview

    
            # 绑定各种事件
            enc_frame.vcodec.trace_add("write", update_preview)
            enc_frame.rate_control_type.trace_add("write", update_preview)
            enc_frame.crf_value.trace_add("write", update_preview)
            enc_frame.cq_value.trace_add("write", update_preview)
            enc_frame.global_quality.trace_add("write", update_preview)
            enc_frame.bitrate_video.trace_add("write", update_preview)
            enc_frame.preset.trace_add("write", lambda *a: update_preview())
            filt_frame.frame_rate_type.trace_add("write", update_preview)
            filt_frame.frame_rate_custom.trace_add("write", update_preview)
            filt_frame.scale_enabled.trace_add("write", update_preview)
            filt_frame.scale_width.trace_add("write", update_preview)
            filt_frame.scale_height.trace_add("write", update_preview)
            filt_frame.scale_method.trace_add("write", update_preview)
            filt_frame.crop_enabled.trace_add("write", update_preview)
            filt_frame.crop_left.trace_add("write", update_preview)
            filt_frame.crop_top.trace_add("write", update_preview)
            filt_frame.crop_width.trace_add("write", update_preview)
            filt_frame.crop_height.trace_add("write", update_preview)
            filt_frame.rotate.trace_add("write", update_preview)
            filt_frame.vflip.trace_add("write", update_preview)
            filt_frame.hflip.trace_add("write", update_preview)
            filt_frame.speed_enabled.trace_add("write", update_preview)
            filt_frame.speed_factor.trace_add("write", update_preview)
            filt_frame.deinterlace_filter.trace_add("write", update_preview)
            filt_frame.pix_fmt_enabled.trace_add("write", update_preview)
            filt_frame.pix_fmt.trace_add("write", update_preview)
            filt_frame.subtitle_enabled.trace_add("write", update_preview)
            filt_frame.subtitle_path.trace_add("write", update_preview)
            audio_frame.audio_enabled.trace_add("write", update_preview)
            audio_frame.audio_codec.trace_add("write", update_preview)
            audio_frame.audio_bitrate.trace_add("write", update_preview)
            audio_frame.audio_samplerate.trace_add("write", update_preview)
            audio_frame.only_audio.trace_add("write", update_preview)
            audio_frame.audio_format.trace_add("write", update_preview)


            trim_frame.trim_enabled.trace_add("write", update_preview)
            trim_frame.trim_start.trace_add("write", update_preview)
            trim_frame.trim_end.trace_add("write", update_preview)
            adv_frame.hwaccel_enabled.trace_add("write", update_preview)
            adv_frame.hwaccel_decoder.trace_add("write", update_preview)
            adv_frame.custom_args.trace_add("write", update_preview)
            out_dir_var.trace_add("write", update_preview)
            suffix_var.trace_add("write", update_preview)
            custom_var.trace_add("write", update_preview)
            container_var.trace_add("write", update_preview)

            enc_frame.tune_var.trace_add("write", update_preview)
            enc_frame.profile_var.trace_add("write", update_preview)
            enc_frame.level_var.trace_add("write", update_preview)
            enc_frame.maxrate_var.trace_add("write", update_preview)
            enc_frame.bufsize_var.trace_add("write", update_preview)

            update_preview()

            def save_changes():
                # 流提取相关
                if task.is_custom:
                    messagebox.showinfo("提示", "此任务为流提取生成的自定义任务，不支持修改参数。")
                    win.destroy()
                    return
                new_settings = {}
                new_settings.update(enc_frame.get_settings())
                new_settings.update(filt_frame.get_settings())
                new_settings.update(audio_frame.get_settings())
                new_settings.update(trim_frame.get_settings())
                new_settings.update(adv_frame.get_settings())
                new_settings["output_dir"] = out_dir_var.get()
                new_settings["output_suffix"] = suffix_var.get()
                new_settings["custom_output_name"] = custom_var.get()
                new_settings["output_container"] = container_var.get()

                new_settings["watermark"] = adv_frame.watermark_dict.copy()  # 或直接引用
                new_output = self.generate_output_path(task.input, new_settings)
                new_settings["enhance"] = filt_frame.get_enhance_settings()


                new_settings["segment_enabled"] = seg_enabled_var.get()
                new_settings["segments"] = copy.deepcopy(seg_list)
                try:
                    new_cmd_list = self.generate_ffmpeg_command(task.input, new_output, new_settings)
                except ValueError as e:
                    messagebox.showerror("参数错误", str(e))
                    return
                task.settings = new_settings
                task.output = new_output
                task.cmd = new_cmd_list
                task.status = "等待"
                self.update_task_list()
                win.destroy()
                self._append_info_ui(f"已编辑任务: {os.path.basename(task.input)}")
    
            btn_frame = ttk.Frame(win)
            btn_frame.pack(pady=(5,10))
            ttk.Button(btn_frame, text="保存修改", command=save_changes).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="取消", command=win.destroy).pack(side=tk.LEFT, padx=5)


            win.wait_window()

    def _on_task_watermark_saved(self, task, new_wm):
        old_adaptive = task.settings.get("watermark", {}).get("adaptive", True)
        new_wm["adaptive"] = old_adaptive
        task.settings["watermark"] = new_wm
        self.update_task_list()
        self._append_info_ui("任务水印已更新")

    def on_task_double_click(self, event):
        selected = self.task_tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        self.edit_task(self.tasks[idx], idx)

    # ==================== 封装/合并模块 ====================
    def create_merge_tab(self, parent):
        # 主视频文件行
        f1 = ttk.Frame(parent)
        f1.pack(fill=tk.X, pady=5)
        ttk.Label(f1, text="主视频文件:").pack(side=tk.LEFT)
        ttk.Entry(f1, textvariable=self.merge_video).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(f1, text="浏览", command=self.merge_select_video).pack(side=tk.RIGHT, padx=(2,15))
    
        if DND_AVAILABLE:
            label_text = "轨道列表（可双击编辑单独设置编码参数，支持批量拖拽添加文件）"
        else:
            label_text = "轨道列表（可双击编辑单独设置编码参数）"
        ttk.Label(parent, text=label_text).pack(anchor=tk.W, pady=(0,2))
    
        # 轨道列表（Treeview）
        list_container = ttk.Frame(parent)
        list_container.pack(fill=tk.BOTH, expand=True, padx=(5,0), pady=(0,0))
#         list_container.pack_propagate(False)
#         min_height = int(400 * self.scaling)
#         list_container.config(height=min_height)
    
        # 工具栏
        tool_frame = ttk.Frame(list_container)
        tool_frame.pack(fill=tk.X, pady=2)
        ttk.Button(tool_frame, text="启用/禁用", command=self.merge_toggle_selected, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="编辑", command=self.merge_edit_selected, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="预览", command=self.merge_preview_selected, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="上移", command=self.merge_move_up_selected, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="下移", command=self.merge_move_down_selected, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="删除", command=self.merge_delete_selected, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="清空", command=self.merge_clear_tracks, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="恢复列宽", command=self.merge_reset_column_widths, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="按文件名排序", command=self.merge_sort_by_filename).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="按修改时间排序", command=self.merge_sort_by_mtime).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="💾 保存项目", command=self.save_merge_project).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="📂 加载项目", command=self.load_merge_project).pack(side=tk.LEFT, padx=2)
    
        # 自定义样式
        merge_style = ttk.Style()
        merge_style.configure("Merge.Treeview", background="#f0f0f0", fieldbackground="#f0f0f0", rowheight=int(22 * self.scaling))
        merge_style.configure("Merge.Treeview.Heading", background="#d9d9d9")
    
        # 创建 Treeview（只一次）
        columns = ("序号", "启用", "类型", "规格", "编码", "来源", "编码设置 双击编辑")
        self.merge_tree = ttk.Treeview(list_container, columns=columns, show="headings",
                                       height=8, style="Merge.Treeview")
        self.merge_tree.heading("序号", text="序号")
        self.merge_tree.heading("启用", text="启用")
        self.merge_tree.heading("类型", text="类型")
        self.merge_tree.heading("规格", text="规格")
        self.merge_tree.heading("编码", text="编码")
        self.merge_tree.heading("来源", text="来源")
        self.merge_tree.heading("编码设置 双击编辑", text="编码设置 双击编辑")
        self.merge_tree.column("序号", width=5, anchor="center")
        self.merge_tree.column("启用", width=5, anchor="center")
        self.merge_tree.column("类型", width=20)
        self.merge_tree.column("规格", width=100)
        self.merge_tree.column("编码", width=20)
        self.merge_tree.column("来源", width=495)
        self.merge_tree.column("编码设置 双击编辑", width=80)
        self.merge_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
        # 滚动条
        vbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.merge_tree.yview)
        self.merge_tree.configure(yscrollcommand=vbar.set)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
    
        # 绑定双击编辑
        self.merge_tree.bind("<Double-1>", self.merge_on_tree_double_click)
    

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="添加外部音轨", command=lambda: self.merge_add_external("audio")).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="添加外部字幕", command=lambda: self.merge_add_external("subtitle")).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="清空轨道", command=self.merge_clear_tracks).pack(side=tk.LEFT, padx=2)
        self.pip_enabled = tk.BooleanVar(value=False)
        pip_chk = ttk.Checkbutton(btn_frame, text="启用画中画", variable=self.pip_enabled)
        pip_chk.pack(side=tk.LEFT, padx=5)
        ToolTip(pip_chk,
                "「画中画」可将多个视频/图片叠加到主画面上，适合：\n"
                "• 多机位舞台合成（多角度同屏）\n"
                "• 制作对比演示、分镜效果或画中画解说\n"
                "• 图片作为背景或角标（动态图片支持循环）\n\n"
                "启用后，所有视频流将强制重新编码（无法使用 copy），\n"
                "    输出时长默认由主视频决定，您也可以开启「手动时长」精确控制。\n\n"
                "提示：每个视频轨道都可独立设置位置、大小、透明度、绿幕抠像等。\n"
                "    画中画模式每个音频的倒放是独立的。\n",
                wraplength=700)

        self.concat_enabled = tk.BooleanVar(value=False)
        concat_chk = ttk.Checkbutton(btn_frame, text="串行合并（首尾拼接）", variable=self.concat_enabled)
        concat_chk.pack(side=tk.LEFT, padx=5)
        ToolTip(concat_chk,
                "将多个视频按顺序首尾拼接，适用于合并剧集、连续片段等。\n\n"
                "【流复制模式（编码器 = copy）】\n"
                "• 此模式要求所有输入视频的编码参数【完全一致】，包括：\n"
                "  - 视频编码格式（如 H.264 / HEVC）、分辨率（宽×高）、帧率（fps）\n"
                "  - 像素格式（如 yuv420p）、采样纵横比（SAR）、时间基（timebase）\n"
                "• 若参数不一致，可能出现：\n"
                "  - 拼接处播放速度异常（过快/过慢）\n"
                "  - 音画不同步、画面花屏或卡顿、部分播放器无法正常播放\n"
                "• 适合流复制模式的常见情况：\n"
                "  - 同一设备或软件连续录制的分段文件（如 GoPro、行车记录仪）\n"
                "  - 同一来源压制、参数相同的剧集或系列视频\n"
                "  - 同一个视频文件的循环拼接（如片头/背景）\n"
                "• 建议：若不确定文件参数是否一致，或者串接后不满意，请使用【重新编码模式】。\n\n"
                "【重新编码模式（编码器 ≠ copy）】\n"
                "• 系统会对所有视频进行重新编码，强制统一参数，拼接后播放流畅。\n"
                "• 为提高兼容性，建议所有源文件分辨率保持一致；若不同，系统会自动尝试缩放，但可能影响画质。\n"
                "• 该模式下，您也可以额外应用滤镜（如裁剪、缩放、旋转等）到整个拼接结果。\n\n"
                "• 若文件数量众多，重新编码会消耗较多时间，建议预先用 FFmpeg 统一转码后再使用流复制模式。",
                wraplength=700)

        ttk.Button(btn_frame, text="添加外部视频（画中画/串行）", 
            command=self.merge_add_external_video).pack(side=tk.LEFT, padx=2)

        # ----- 手动时长控制 -----
        # 变量定义
        self.merge_manual_duration_enabled = tk.BooleanVar(value=False)
        self.merge_manual_duration = tk.StringVar(value="")
        # UI 控件
        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=(20,5))
        chk_manual = ttk.Checkbutton(btn_frame, text="手动时长", 
                                     variable=self.merge_manual_duration_enabled,
                                     command=lambda: self.merge_update_command_preview())
        chk_manual.pack(side=tk.LEFT, padx=2)

        ToolTip(chk_manual,
            "勾选后，将使用您输入的时长作为输出总时长（手动 -t）。\n\n"
            "主要用途：作为应急保险，防止因滤镜循环或参数不当导致输出无限延长（尤其是画中画模式）。\n\n"
            "次要用途：可以手动设置 -t 10 转换个10秒片段查看结果，预览命令里水印只有占位框。\n\n"
            "「视频转码」页面可使用自定义参数 -t 实现同功能。",
            wraplength=600
        )


        self.merge_manual_duration_entry = ttk.Entry(btn_frame, 
                                                     textvariable=self.merge_manual_duration,
                                                     width=8)
        self.merge_manual_duration_entry.pack(side=tk.LEFT, padx=2)
        ttk.Label(btn_frame, text="秒 (覆盖自动时长)").pack(side=tk.LEFT, padx=0)



        # 绑定输入变化刷新预览
        self.merge_manual_duration.trace_add('write', lambda *a: self.merge_update_command_preview())



        chapter_frame = ttk.LabelFrame(parent, text="章节处理", padding="3")
        chapter_frame.pack(fill=tk.X, pady=5)
        chapter_row = ttk.Frame(chapter_frame)
        chapter_row.pack(fill=tk.X, padx=5, pady=(0,2))
        ttk.Checkbutton(
            chapter_row, text="从源文件复制章节 (map_chapters)", 
            variable=self.copy_chapters
        ).pack(side=tk.LEFT, padx=(0, 15))
        right_area = ttk.Frame(chapter_row)
        right_area.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(right_area, text="导入外部章节文件 (FFmetadata):").pack(side=tk.LEFT)
        chapter_entry = ttk.Entry(right_area, textvariable=self.chapter_file)
        chapter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(
            right_area, text="浏览...", command=self.browse_chapter_file, width=10
        ).pack(side=tk.LEFT, padx=(0, 5))

        row_frame = ttk.Frame(parent)
        row_frame.pack(fill=tk.X, pady=2)
        left_container = ttk.Frame(row_frame)
        left_container.pack(side=tk.LEFT, padx=(5, 5))
        ttk.Label(left_container, text="输出容器:").pack(side=tk.LEFT)
        container_combo = ttk.Combobox(
            left_container, textvariable=self.merge_container,
            values=["mkv", "mp4", "webm"], state="readonly", width=8
        )
        container_combo.pack(side=tk.LEFT, padx=5)
        container_combo.bind("<<ComboboxSelected>>", lambda e: self.merge_update_output_preview())
        
        right_container = ttk.Frame(row_frame)
        right_container.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(right_container, text="输出文件:").pack(side=tk.LEFT)
        ttk.Entry(right_container, textvariable=self.merge_output).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=5
        )
        ttk.Button(
            right_container, text="浏览...",
            command=self.merge_select_output, width=10
        ).pack(side=tk.LEFT, padx=(0, 15))

        opt_action_frame = ttk.Frame(parent)
        opt_action_frame.pack(fill=tk.X, pady=2)
        
        ttk.Checkbutton(
            opt_action_frame, text="合并成功后删除源文件", variable=self.merge_delete_source
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Checkbutton(
            opt_action_frame, text="验证输出文件", variable=self.merge_verify
        ).pack(side=tk.LEFT, padx=5)

        self.merge_only_audio = tk.BooleanVar(value=False)
        self.only_audio_checkbox = ttk.Checkbutton(
            opt_action_frame, 
            text="仅音频", 
            variable=self.merge_only_audio,
            command=self.merge_update_command_preview
        )
        self.only_audio_checkbox.pack(side=tk.LEFT, padx=(5,50))
        ToolTip(
            self.only_audio_checkbox,
            "仅音频（简易实现）：输出纯音频文件（无视频流）。\n\n"
            "核心目的：将多个音频轨道进行混合（amix），各轨道仍可单独调节音量、截取或倒放。\n"
            "    若只需提取单音轨，请使用转码页面的仅音频功能。\n\n"
            "使用说明：\n"
            "• 本功能依赖「主视频」作为参数占位（简易实现，未完全重构生成逻辑），\n"
            "  您可随意拖入一个视频文件作为占位，并删除或禁用其音频轨道，\n"
            "  然后添加需要处理的音频轨道，待所有音频设置完成后再勾选此选项执行。\n"
            "  注意：请记得修改输出文件名。\n\n"
            "• 仅普通封装模式（非画中画/串行合并）下可用；\n"
            "  若勾选画中画或串行合并，此选项会自动禁用并取消勾选。\n\n"
            "• 输出文件扩展名将自动调整为 .m4a（或根据所选容器生成）。\n"
            "  若扩展名不符，可手动修改后复制到快速命令区运行。",
            wraplength=600
        )
        
        # 增加状态联动：当画中画或串行合并模式变化时，禁用/启用该复选框
        def _update_only_audio_state(*args):
            if self.pip_enabled.get() or self.concat_enabled.get():
                self.merge_only_audio.set(False)
                self.only_audio_checkbox.config(state='disabled')
                self._append_info_ui("[封装] 画中画/串行合并模式下不支持仅音频，已自动禁用")
            else:
                self.only_audio_checkbox.config(state='normal')
            # 仅当主视频已设置时才刷新预览
            if self.merge_video.get().strip():
                self.root.after(40, self.merge_update_command_preview)
        
        self.pip_enabled.trace_add('write', _update_only_audio_state)
        self.concat_enabled.trace_add('write', _update_only_audio_state)


        self.merge_btn = tk.Button(opt_action_frame, text="开始合并", command=self.merge_start,
                                   height=1, width=12, bg="#4CAF50", fg="white")
        self.merge_btn.pack(side=tk.LEFT, padx=5)

        btn_refresh_merge = tk.Button(opt_action_frame, text="刷新命令", 
                                      command=self.merge_update_command_preview,
                                      height=1, width=12, relief=tk.RAISED)
        btn_refresh_merge.pack(side=tk.LEFT, padx=5)
        
        btn_copy = tk.Button(opt_action_frame, text="复制命令", command=self.merge_copy_command,
                             height=1, width=12, relief=tk.RAISED)
        btn_copy.pack(side=tk.LEFT, padx=5)

        preview_frame = ttk.LabelFrame(parent, text="即将执行的命令预览", padding="0")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=(5,0), pady=5)
        content_frame = ttk.Frame(preview_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        self.merge_cmd_preview = scrolledtext.ScrolledText(
            content_frame, height=1, wrap=tk.WORD, font=("Microsoft YaHei", 9)
        )
        self.merge_cmd_preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=0)


        self.merge_video.trace_add("write", lambda *a: self.merge_load_video_info())
        self.merge_container.trace_add("write", lambda *a: self.merge_update_command_preview())
        self.merge_output.trace_add("write", lambda *a: self.merge_update_command_preview())
        self.copy_chapters.trace_add("write", lambda *a: self.merge_update_command_preview())
        self.chapter_file.trace_add("write", lambda *a: self.merge_update_command_preview())

        self.pip_enabled.trace_add('write', self._on_pip_toggle)
        self.concat_enabled.trace_add('write', self._on_concat_toggle)


    def merge_smart_tile(self, main_track_idx, pad_enabled_var=None, pad_width_var=None, pad_height_var=None,
                         items_per_row=4, items_per_col=4, orientation='auto', filt_frame=None):
        """
        智能平铺：所有视频（主视频+子视频）统一按行列排列。
        :param items_per_row: 横向优先时，每行视频数
        :param items_per_col: 纵向优先时，每列视频数
        :param orientation: 'auto' / 'horizontal' / 'vertical'
        :param filt_frame: 可选，主视频的 VideoFilterFrame 控件，用于读取未保存的缩放/裁剪设置
        """
        if main_track_idx is None or main_track_idx >= len(self.merge_tracks):
            messagebox.showerror("错误", "无效的主视频轨道索引")
            return
    
        main_track = self.merge_tracks[main_track_idx]
        if main_track.type != "video":
            messagebox.showerror("错误", "选中的不是视频轨道")
            return
    
        # 获取所有启用的视频轨道（排除主视频自身）
        sub_tracks = [t for t in self.merge_tracks if t.type == "video" and t.enabled and t != main_track]
        # 强制启用所有子视频的叠加
        for t in sub_tracks:
            t.enc_settings['overlay_enabled'] = True
            t.overlay_enabled = True
    
        # 构建总视频列表：主视频 + 子视频
        all_tracks = [main_track] + sub_tracks
        n = len(all_tracks)
        if n == 1:
            messagebox.showinfo("提示", "没有可用于平铺的视频（至少需要一个子视频）")
            return
    
        # ---- 获取主视频渲染尺寸：优先从 filt_frame 读取实时值 ----
        if filt_frame is not None:
            main_settings = {
                "crop_enabled": filt_frame.crop_enabled.get(),
                "crop_width": filt_frame.crop_width.get(),
                "crop_height": filt_frame.crop_height.get(),
                "scale_enabled": filt_frame.scale_enabled.get(),
                "scale_method": filt_frame.scale_method.get(),
                "scale_width": filt_frame.scale_width.get(),
                "scale_height": filt_frame.scale_height.get(),
                "rotate": filt_frame.rotate.get()
            }
            orig_w, orig_h = get_video_dimensions(self.ffprobe_cmd, main_track.file_path)
            if orig_w is None or orig_h is None:
                orig_w, orig_h = 1280, 720
            main_w, main_h = self.compute_final_size_with_order(orig_w, orig_h, main_settings)
        else:
            main_w, main_h = self._get_video_render_size(main_track)
            if main_w is None or main_h is None:
                main_w, main_h = 1280, 720
    
        # ---- 获取所有子视频的渲染尺寸（仍从 enc_settings 读取） ----
        infos = [(main_w, main_h, main_track)]
        for t in sub_tracks:
            w, h = self._get_video_render_size(t)
            if w is None or h is None:
                orig_w, orig_h = get_video_dimensions(self.ffprobe_cmd, t.file_path)
                if orig_w and orig_h:
                    w, h = compute_rendered_size(orig_w, orig_h, t.enc_settings)
                else:
                    w, h = 320, 240
            infos.append((w, h, t))
    
        # ---- 核心改进：方向决策与智能排列 ----
        def calculate_layout(is_horizontal):
            """内部函数：根据方向计算布局及画布比例"""
            if is_horizontal:
                cols = items_per_row
                rows = (n + cols - 1) // cols
                row_groups = []
                for r in range(rows):
                    start = r * cols
                    end = min(start + cols, n)
                    row_groups.append(infos[start:end])
            else:
                rows = items_per_col
                cols = (n + rows - 1) // rows
                col_groups = []
                for c in range(cols):
                    start = c * rows
                    end = min(start + rows, n)
                    col_groups.append(infos[start:end])
                # 转置为行组（因为最终画布是按行排列的）
                row_groups = []
                for r in range(rows):
                    row_items = []
                    for c in range(cols):
                        if r < len(col_groups[c]):
                            row_items.append(col_groups[c][r])
                    if row_items:
                        row_groups.append(row_items)
            # 计算该布局下的画布真实宽高
            c_w = max(sum(w for w, h, t in row) for row in row_groups) if row_groups else 0
            c_h = sum(max(h for w, h, t in row) for row in row_groups) if row_groups else 0
            return row_groups, c_w, c_h
    
        if orientation == 'auto':
            h_groups, h_w, h_h = calculate_layout(True)
            h_ratio = h_w / h_h if h_h > 0 else float('inf')
            v_groups, v_w, v_h = calculate_layout(False)
            v_ratio = v_w / v_h if v_h > 0 else float('inf')
            target_ratio = 16 / 9
            h_diff = abs(h_ratio - target_ratio)
            v_diff = abs(v_ratio - target_ratio)
            if h_diff <= v_diff:
                horizontal_priority = True
                row_groups, canvas_w, canvas_h = h_groups, h_w, h_h
            else:
                horizontal_priority = False
                row_groups, canvas_w, canvas_h = v_groups, v_w, v_h
        else:
            horizontal_priority = (orientation == 'horizontal')
            row_groups, canvas_w, canvas_h = calculate_layout(horizontal_priority)
    
        if canvas_w == 0 or canvas_h == 0:
            messagebox.showerror("错误", "计算画布尺寸失败")
            return

        # 偶数保险：向下取整为偶数
        if canvas_w % 2 != 0:
            canvas_w -= 1
        if canvas_h % 2 != 0:
            canvas_h -= 1
        canvas_w = max(2, canvas_w)
        canvas_h = max(2, canvas_h)
    
        # ---- 更新主视频的 pad 设置 ----
        main_track.enc_settings['pad_enabled'] = True
        main_track.enc_settings['pad_width'] = str(canvas_w)
        main_track.enc_settings['pad_height'] = str(canvas_h)
        main_track.enc_settings['offset_x'] = "0"
        main_track.enc_settings['offset_y'] = "0"
        main_track.pad_enabled = True
        main_track.pad_width = str(canvas_w)
        main_track.pad_height = str(canvas_h)
        main_track.offset_x = "0"
        main_track.offset_y = "0"
        if pad_enabled_var is not None:
            pad_enabled_var.set(True)
        if pad_width_var is not None:
            pad_width_var.set(str(canvas_w))
        if pad_height_var is not None:
            pad_height_var.set(str(canvas_h))
    
        # ---- 计算每行的高度（用于垂直偏移） ----
        row_heights = []
        for row in row_groups:
            if row:
                row_heights.append(max(h for w, h, t in row))
            else:
                row_heights.append(0)
    
        # ---- 更新所有视频的叠加位置 ----
        y_offset = 0
        for row_idx, row in enumerate(row_groups):
            x_offset = 0
            row_h = row_heights[row_idx]
            for w, h, t in row:
                if t != main_track:
                    t.enc_settings['overlay_x'] = str(x_offset)
                    t.enc_settings['overlay_y'] = str(y_offset)
                    t.overlay_x = str(x_offset)
                    t.overlay_y = str(y_offset)
                x_offset += w
            y_offset += row_h
    
        # ---- 刷新界面 ----
        self.merge_update_track_list()
        self.merge_update_command_preview()
        direction_str = "横向" if horizontal_priority else "纵向"
        self._append_info_ui(f"✅ 智能平铺完成（{direction_str}优先）：画布 {canvas_w}x{canvas_h}，总视频 {n} 个")
        messagebox.showinfo("成功", f"智能平铺完成\n方向: {direction_str}优先\n画布: {canvas_w}×{canvas_h}\n总视频数: {n}")
    



    def save_merge_project(self):
        """手动保存合并项目到 .fflgproject 文件"""
        file_path = filedialog.asksaveasfilename(
            title="保存合并项目",
            defaultextension=".fflgproject",
            filetypes=[("fflgproject 项目文件", "*.fflgproject"), ("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
        
        # 构造状态字典（复用之前的序列化逻辑）
        state = self._build_merge_state_dict()
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            self._append_info_ui(f"✅ 项目已保存到: {os.path.basename(file_path)}")
        except Exception as e:
            self._append_info_ui(f"❌ 保存项目失败: {e}")
            messagebox.showerror("保存失败", str(e))
    
    def _build_merge_state_dict(self):
        state = {
            "version": "1.0",
            "merge_video": self.merge_video.get(),
            "merge_output": self.merge_output.get(),
            "merge_container": self.merge_container.get(),
            "pip_enabled": self.pip_enabled.get(),
            "concat_enabled": self.concat_enabled.get(),
            "merge_only_audio": self.merge_only_audio.get(),
            "merge_manual_duration_enabled": self.merge_manual_duration_enabled.get(),
            "merge_manual_duration": self.merge_manual_duration.get(),
            "copy_chapters": self.copy_chapters.get(),
            "chapter_file": self.chapter_file.get(),
            "merge_verify": self.merge_verify.get(),
            "merge_delete_source": self.merge_delete_source.get(),
            "tracks": []
        }
        for track in self.merge_tracks:
            if track.enc_settings.get("_placeholder", False):
                continue
            enc_settings_copy = track.enc_settings.copy()
            enc_settings_copy.pop("_file_path", None)  # 移除临时字段
            track_dict = {
                "type": track.type,
                "codec": track.codec,
                "file_path": track.file_path,
                "index": track.index,
                "enabled": track.enabled,
                "language": track.language,
                "title": track.title,
                "enc_settings": enc_settings_copy
            }
            state["tracks"].append(track_dict)
        return state

    def load_merge_project(self):
        """从 .fflgproject 文件加载合并项目"""
        # 如果有未保存的更改，提示是否保存当前项目
        if self.merge_tracks and messagebox.askyesno("未保存的项目", "当前有轨道，是否先保存当前项目？\n（选“是”保存，选“否”直接加载新项目）"):
            self.save_merge_project()
            # 用户可能取消保存，但继续加载，没问题
        
        file_path = filedialog.askopenfilename(
            title="加载合并项目",
            filetypes=[("fflgproject 项目文件", "*.fflgproject"), ("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except Exception as e:
            self._append_info_ui(f"❌ 读取项目文件失败: {e}")
            messagebox.showerror("读取失败", str(e))
            return
        
        # 恢复状态
        self._restore_merge_state_dict(state)
        self._append_info_ui(f"✅ 项目已加载: {os.path.basename(file_path)}")

    def _restore_merge_state_dict(self, state):
        self._suppress_main_video_trace = True
        self._batch_update = True          # 抑制所有中间刷新
        try:
            # 恢复基本设置（先恢复 merge_video 和 merge_output）
            self.merge_video.set(state.get("merge_video", ""))
            self.merge_output.set(state.get("merge_output", ""))   # 直接保存的路径
            self.merge_container.set(state.get("merge_container", "mkv"))
            self.pip_enabled.set(state.get("pip_enabled", False))
            self.concat_enabled.set(state.get("concat_enabled", False))
            self.merge_only_audio.set(state.get("merge_only_audio", False))
            self.merge_manual_duration_enabled.set(state.get("merge_manual_duration_enabled", False))
            self.merge_manual_duration.set(state.get("merge_manual_duration", ""))
            self.copy_chapters.set(state.get("copy_chapters", True))
            self.chapter_file.set(state.get("chapter_file", ""))
            self.merge_verify.set(state.get("merge_verify", True))
            self.merge_delete_source.set(state.get("merge_delete_source", False))
    
            # 恢复轨道
            self.merge_tracks = []
            for track_dict in state.get("tracks", []):
                track = Track(
                    track_dict["index"],
                    track_dict["type"],
                    track_dict["codec"],
                    track_dict["file_path"],
                    track_dict["enabled"],
                    copy.deepcopy(track_dict["enc_settings"])
                )
                track.file_path = track_dict["file_path"]
                track.language = track_dict.get("language", "")
                track.title = track_dict.get("title", "")
                if track.type == "video":
                    track.overlay_enabled = track.enc_settings.get("overlay_enabled", False)
                    track.overlay_x = track.enc_settings.get("overlay_x", "W-w-10")
                    track.overlay_y = track.enc_settings.get("overlay_y", "H-h-10")
                    track.pad_enabled = track.enc_settings.get("pad_enabled", False)
                    track.pad_width = track.enc_settings.get("pad_width", "")
                    track.pad_height = track.enc_settings.get("pad_height", "")
                    track.offset_x = track.enc_settings.get("offset_x", "0")
                    track.offset_y = track.enc_settings.get("offset_y", "0")
                self.merge_tracks.append(track)
    
        finally:
            self._suppress_main_video_trace = False
            self._batch_update = False
    
        # 手动刷新（不调用 merge_update_output_preview，避免覆盖 merge_output）
        self.merge_update_track_list()
        self.merge_update_command_preview()

    def merge_sort_tracks(self, key_func):
        """按文件分组排序轨道（同一文件的所有轨道保持在一起）"""
        if not self.merge_tracks:
            self._append_info_ui("[排序] 轨道列表为空，无需排序")
            return
    
        # 按文件路径分组
        file_groups = {}
        for track in self.merge_tracks:
            file_path = track.file_path
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(track)
    
        # 对文件排序
        sorted_files = sorted(file_groups.keys(), key=key_func)
    
        # 重建轨道列表
        new_tracks = []
        for f in sorted_files:
            new_tracks.extend(file_groups[f])
    
        self.merge_tracks = new_tracks
        self.merge_update_track_list()
        self.merge_update_command_preview()
        self._append_info_ui(f"[排序] 已按选择顺序重新排序，共 {len(self.merge_tracks)} 个轨道")
    
    def merge_sort_by_filename(self):
        """按文件名自然排序（仅在串联模式下可用）"""
        if not self.concat_enabled.get():
            messagebox.showinfo("提示", "排序功能仅在「串行合并（首尾拼接）」模式下可用。\n请先勾选「串行合并（首尾拼接）」选项。")
            return
    
        def natural_key(text):
            parts = [p for p in re.split(r'(\d+)', text) if p]  # 过滤空字符串
            def convert(part):
                return int(part) if part.isdigit() else part.lower()
            return [convert(p) for p in parts]
    
        self.merge_sort_tracks(key_func=lambda p: natural_key(os.path.basename(p)))
    
    def merge_sort_by_mtime(self):
        """按修改时间排序（仅在串联模式下可用）"""
        if not self.concat_enabled.get():
            messagebox.showinfo("提示", "排序功能仅在「串行合并（首尾拼接）」模式下可用。\n请先勾选「串行合并（首尾拼接）」选项。")
            return
        def get_mtime(p):
            try:
                return os.path.getmtime(p)
            except OSError:
                return 0
        self.merge_sort_tracks(key_func=get_mtime)


    def _on_pip_toggle(self, *args):
        if self.pip_enabled.get() and self.concat_enabled.get():
            self.concat_enabled.set(False)
        # 当画中画被禁用时（切回普通模式），重置水印提示
        if not self.pip_enabled.get():
            self._trim_precise_hint_shown = False
            self._pip_reverse_audio_hint_shown = False
        self.merge_update_command_preview()
        self.merge_update_track_list()

    def _on_concat_toggle(self, *args):
        if self.concat_enabled.get() and self.pip_enabled.get():
            self.pip_enabled.set(False)
        if not self.concat_enabled.get():
            self._trim_precise_hint_shown = False
            self._pip_reverse_audio_hint_shown = False
        self.merge_update_command_preview()
        self.merge_update_track_list()

    def _add_pip_video_forced(self, path, add_audio=True):
        """
        强制添加视频作为画中画（不弹出询问对话框）。
        - add_audio: 是否同时添加该文件的所有音频流
        """
        if os.path.isdir(path):
            self._append_info_ui(f"[封装] 忽略文件夹: {os.path.basename(path)}，请选择文件")
            return
        info = self._get_cached_stream_info(path)
        if not info:
            self._append_info_ui(f"[封装] 无法解析文件: {path}")
            return

    
        # 检测是否为图片
        img_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
        is_image = os.path.splitext(path)[1].lower() in img_exts
    
        if is_image:
            track = Track(0, "video", "image2", path, True)
            track.enc_settings["scale_enabled"] = True
            track.enc_settings["scale_width"] = "320"
            track.enc_settings["scale_height"] = ""
            track.enc_settings["scale_method"] = "width"
            track.enc_settings["overlay_enabled"] = True
            track.enc_settings["overlay_x"] = "W-w-10"
            track.enc_settings["overlay_y"] = "H-h-10"
            track.overlay_enabled = True
            self.merge_tracks.append(track)
            self._append_info_ui(f"[封装] 已添加图片水印: {os.path.basename(path)}")
            return
    
        # 视频处理
        video_streams = [s for s in info["streams"] if s.get("codec_type") == "video"]
        if not video_streams:
            self._append_info_ui("[封装] 所选文件不包含视频流")
            return
    
        # 添加视频轨道
        s = video_streams[0]
        track = Track(s["index"], "video", s.get("codec_name", "unknown"), path, True)
        track.enc_settings["scale_enabled"] = True
        track.enc_settings["scale_width"] = "320"
        track.enc_settings["scale_height"] = ""
        track.enc_settings["scale_method"] = "width"
        track.enc_settings["overlay_enabled"] = True
        track.enc_settings["overlay_x"] = "W-w-10"
        track.enc_settings["overlay_y"] = "H-h-10"
        track.overlay_enabled = True
        self.merge_tracks.append(track)
        self._append_info_ui(f"[封装] 已添加画中画视频: {os.path.basename(path)}")
    
        # 添加音频（如果 add_audio 为 True）
        if add_audio:
            audio_streams = [s for s in info["streams"] if s.get("codec_type") == "audio"]
            for s_audio in audio_streams:
                audio_track = Track(s_audio["index"], "audio", s_audio.get("codec_name", "unknown"), path, True)
                self.merge_tracks.append(audio_track)
                self._append_info_ui(f"[封装] 已添加音频流: {s_audio.get('codec_name', 'unknown')}")
    
    
    def _add_concat_video_forced(self, path):
        """
        强制添加视频作为串联片段（不弹出询问对话框，自动添加所有音频和字幕流）
        """
        if os.path.isdir(path):
            self._append_info_ui(f"[封装] 忽略文件夹: {os.path.basename(path)}，请选择文件")
            return
        info = self._get_cached_stream_info(path)
        if not info:
            self._append_info_ui(f"[封装] 无法解析文件: {path}")
            return

    
        # 添加所有视频流（通常只有一个）
        video_streams = [s for s in info["streams"] if s.get("codec_type") == "video"]
        for s in video_streams:
            track = Track(s["index"], "video", s.get("codec_name", "unknown"), path, True)
            # 串联模式不需要 overlay 属性
            self.merge_tracks.append(track)
            self._append_info_ui(f"[封装] 已添加串联视频流: {os.path.basename(path)}")
    
        # 添加所有音频流
        audio_streams = [s for s in info["streams"] if s.get("codec_type") == "audio"]
        for s_audio in audio_streams:
            audio_track = Track(s_audio["index"], "audio", s_audio.get("codec_name", "unknown"), path, True)
            self.merge_tracks.append(audio_track)
            self._append_info_ui(f"[封装] 已添加音频流: {s_audio.get('codec_name', 'unknown')}")
    
        # 添加所有字幕流
        subtitle_streams = [s for s in info["streams"] if s.get("codec_type") == "subtitle"]
        for s_sub in subtitle_streams:
            sub_track = Track(s_sub["index"], "subtitle", s_sub.get("codec_name", "unknown"), path, True)
            self.merge_tracks.append(sub_track)
            self._append_info_ui(f"[封装] 已添加字幕流: {s_sub.get('codec_name', 'unknown')}")
    
    
    def _handle_drop_pip_mode(self, files):
        """
        画中画模式下的拖拽处理 —— 瞬间添加占位，后台解析，无卡顿。
        - 视频文件：先添加占位轨道，后台解析后替换为真实流。
        - 图片文件：直接添加为图片水印（无需解析，但为了统一也可占位）。
        - 音频文件：直接添加为独立音轨（无需解析）。
        """
        if not files:
            return
    
        # 分离文件类型
        video_files = []
        audio_files = []
        image_files = []
        other_files = []
        video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.ts', '.webm')
        img_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
        audio_exts = ('.mp3', '.aac', '.m4a', '.wav', '.flac', '.ogg', '.opus', '.ac3', '.dts')
    
        for f in files:
            if os.path.isdir(f):
                self._append_info_ui(f"[封装] 忽略文件夹: {os.path.basename(f)}，请选择文件")
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in video_exts:
                video_files.append(f)
            elif ext in img_exts:
                image_files.append(f)
            elif ext in audio_exts:
                audio_files.append(f)
            else:
                other_files.append(f)
    
        # ---- 立即添加占位轨道（仅对视频文件） ----
        original_batch = self._batch_update
        self._batch_update = False
        try:
            # 图片直接添加（无需占位）
            for img in image_files:
                self._add_pip_video_forced(img, add_audio=False)
            # 音频直接添加
            for audio in audio_files:
                self.merge_add_external("audio", audio)
            # 视频：添加占位轨道
            for vf in video_files:
                track = Track(0, "video", "unknown", vf, True)
                track.enc_settings["_placeholder"] = True
                # 画中画默认启用叠加并缩放到320宽（与原有行为一致）
                track.enc_settings["scale_enabled"] = True
                track.enc_settings["scale_width"] = "320"
                track.enc_settings["scale_height"] = ""
                track.enc_settings["scale_method"] = "width"
                track.enc_settings["overlay_enabled"] = True
                track.enc_settings["overlay_x"] = "W-w-10"
                track.enc_settings["overlay_y"] = "H-h-10"
                track.overlay_enabled = True
                self.merge_tracks.append(track)
            # 立即刷新列表
            self.merge_update_track_list()
            if video_files:
                self._append_info_ui(f"[封装] 已添加 {len(video_files)} 个视频文件（正在后台解析…）")
            if image_files:
                self._append_info_ui(f"[封装] 已添加 {len(image_files)} 个图片水印")
            if audio_files:
                self._append_info_ui(f"[封装] 已添加 {len(audio_files)} 个音频轨道")
            if other_files:
                self._append_info_ui(f"[拖拽] 忽略不支持的文件类型: {', '.join(os.path.basename(f) for f in other_files)}")
        finally:
            self._batch_update = original_batch
    
        # ---- 如果有视频文件，启动后台解析 ----
        if video_files:
            # 询问是否添加音频（仅一次）
            if len(video_files) > 1:
                add_audio = messagebox.askyesno(
                    "添加音频",
                    f"是否同时添加这 {len(video_files)} 个视频文件的音频流？\n选“是”将添加所有音频流，选“否”仅添加视频作为水印。"
                )
            else:
                add_audio = messagebox.askyesno(
                    "添加音频",
                    f"是否同时添加文件「{os.path.basename(video_files[0])}」的音频流？\n选“是”将添加音频，选“否”仅添加视频作为水印。"
                )
    
            def parse_and_add():
                try:
                    self._parse_files_concurrently(video_files, description="画中画视频文件")
                    self.root.after(0, lambda: self._finish_drop_pip(video_files, add_audio))
                except Exception as e:
                    self.root.after(0, lambda: self._append_info_ui(f"[封装] 解析异常: {e}"))
    
            threading.Thread(target=parse_and_add, daemon=True).start()
    
    def _finish_drop_pip(self, video_files, add_audio):
        """
        画中画模式后台解析完成后的回调：删除视频占位轨道，添加真实视频流，并根据 add_audio 添加音频。
        增强：错误处理、路径规范化、错误标记。
        """
        self._batch_update = True
        try:
            # 1. 删除本次添加的视频占位轨道（使用规范化路径比较）
            normalized_video_files = [normalize_path(f) for f in video_files]
            to_remove = []
            for idx, track in enumerate(self.merge_tracks):
                if (normalize_path(track.file_path) in normalized_video_files and 
                    track.enc_settings.get("_placeholder", False)):
                    to_remove.append(idx)
            for idx in reversed(to_remove):
                del self.merge_tracks[idx]
    
            # 2. 添加真实视频流和（可选）音频流
            for vf in video_files:
                info = self._get_cached_stream_info(vf)
                if not info:
                    # 解析失败：添加错误标记轨道
                    error_track = Track(0, "video", "error", vf, True)
                    error_track.enc_settings["_error"] = "解析失败"
                    self.merge_tracks.append(error_track)
                    self._append_info_ui(f"[封装] 文件 {os.path.basename(vf)} 解析失败，已标记为错误")
                    continue
    
                # 添加视频流（取第一个视频流）
                video_streams = [s for s in info['streams'] if s.get('codec_type') == 'video']
                if video_streams:
                    s = video_streams[0]
                    track = Track(s['index'], "video", s.get('codec_name', 'unknown'), vf, True)
                    # 保留画中画默认设置（与占位一致）
                    track.enc_settings["scale_enabled"] = True
                    track.enc_settings["scale_width"] = "320"
                    track.enc_settings["scale_height"] = ""
                    track.enc_settings["scale_method"] = "width"
                    track.enc_settings["overlay_enabled"] = True
                    track.enc_settings["overlay_x"] = "W-w-10"
                    track.enc_settings["overlay_y"] = "H-h-10"
                    track.overlay_enabled = True
                    # 检查是否已存在相同视频轨道（去重）
                    exists = any(t.file_path == vf and t.index == s['index'] and t.type == 'video' for t in self.merge_tracks)
                    if not exists:
                        self.merge_tracks.append(track)
                        self._append_info_ui(f"[封装] 已解析并添加画中画视频: {os.path.basename(vf)}")
                    else:
                        self._append_info_ui(f"[封装] 视频流已存在，跳过: {os.path.basename(vf)}")
                else:
                    self._append_info_ui(f"[封装] {os.path.basename(vf)} 不包含视频流，跳过")
    
                # 如果需要添加音频
                if add_audio:
                    audio_streams = [s for s in info['streams'] if s.get('codec_type') == 'audio']
                    for s_audio in audio_streams:
                        # 检查是否已存在相同音频轨道（避免重复）
                        exists = any(t.file_path == vf and t.index == s_audio['index'] and t.type == 'audio' for t in self.merge_tracks)
                        if not exists:
                            audio_track = Track(s_audio['index'], "audio", s_audio.get('codec_name', 'unknown'), vf, True)
                            self.merge_tracks.append(audio_track)
                            self._append_info_ui(f"[封装] 已添加音频流: {s_audio.get('codec_name', 'unknown')}")
    
        finally:
            self._batch_update = False
            # 刷新列表和预览
            self.merge_update_track_list()
            self.merge_auto_recommend_container()
            self._ensure_main_video(disable_scale=True)
            self.merge_update_output_preview()
            self.merge_update_command_preview()
            self._append_info_ui("[封装] 画中画文件解析完成，轨道列表已更新")
            

    
    def _handle_drop_concat_mode(self, files):
        """
        串行合并模式拖拽 —— 瞬间添加占位，后台解析，无卡顿。
        """
        if not files:
            return
    
        video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.ts', '.webm')
        audio_exts = ('.mp3', '.aac', '.m4a', '.wav', '.flac', '.ogg', '.opus', '.ac3', '.dts')
        subtitle_exts = ('.srt', '.ass', '.ssa', '.vtt', '.idx', '.sup')
    
        video_files = []
        other_files = []
        for f in files:
            if os.path.isdir(f):
                self._append_info_ui(f"[封装] 忽略文件夹: {os.path.basename(f)}，请选择文件")
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in video_exts:
                video_files.append(f)
            else:
                other_files.append(f)
    
        if not video_files:
            self._append_info_ui("[封装] 未检测到视频文件")
            return
    
        # ========== 关键修改：强制立即刷新 ==========
        # 保存原有批处理标志，临时关闭以确保立即刷新
        original_batch = self._batch_update
        self._batch_update = False
        try:
            for vf in video_files:
                track = Track(0, "video", "unknown", vf, True)
                track.enc_settings["_placeholder"] = True
                self.merge_tracks.append(track)
            # 立即刷新列表（此时会显示“解析中…”）
            self.merge_update_track_list()
            self._append_info_ui(f"[封装] 已添加 {len(video_files)} 个视频文件（正在后台解析…）")
        finally:
            self._batch_update = original_batch
    
        # ========== 后台解析线程 ==========
        def parse_and_add():
            try:
                self._parse_files_concurrently(video_files, description="串联视频文件")
                self.root.after(0, lambda: self._finish_drop_concat(video_files, other_files))
            except Exception as e:
                self.root.after(0, lambda: self._append_info_ui(f"[封装] 解析异常: {e}"))
    
        threading.Thread(target=parse_and_add, daemon=True).start()
    
    
    def _finish_drop_concat(self, video_files, other_files):
        """
        串联模式后台解析完成后的回调：删除占位，添加真实流，处理错误。
        """
        audio_exts = ('.mp3', '.aac', '.m4a', '.wav', '.flac', '.ogg', '.opus', '.ac3', '.dts')
        subtitle_exts = ('.srt', '.ass', '.ssa', '.vtt', '.idx', '.sup')
    
        self._batch_update = True
        try:
            # 1. 删除占位轨道（使用规范化路径比较）
            normalized_video_files = [normalize_path(f) for f in video_files]
            to_remove = []
            for idx, track in enumerate(self.merge_tracks):
                if normalize_path(track.file_path) in normalized_video_files and track.enc_settings.get("_placeholder", False):
                    to_remove.append(idx)
            for idx in reversed(to_remove):
                del self.merge_tracks[idx]
    
            # 2. 添加真实流（视频、音频、字幕）
            for vf in video_files:
                info = self._get_cached_stream_info(vf)
                if not info:
                    # 解析失败：添加错误标记轨道
                    error_track = Track(0, "video", "error", vf, True)
                    error_track.enc_settings["_error"] = "解析失败"
                    self.merge_tracks.append(error_track)
                    self._append_info_ui(f"[封装] 文件 {os.path.basename(vf)} 解析失败，已标记为错误")
                    continue
    
                streams = info.get('streams', [])
                for s in streams:
                    st = s.get('codec_type')
                    if st not in ('video', 'audio', 'subtitle'):
                        continue
                    # 检查是否已存在相同轨道（去重）
                    exists = any(t.file_path == vf and t.index == s['index'] for t in self.merge_tracks)
                    if exists:
                        continue
                    track = Track(s['index'], st, s.get('codec_name', 'unknown'), vf, True)
                    self.merge_tracks.append(track)
                self._append_info_ui(f"[封装] 已解析并添加串联视频: {os.path.basename(vf)}")
    
            # 3. 处理其他文件（音频/字幕）
            for f in other_files:
                ext = os.path.splitext(f)[1].lower()
                if ext in audio_exts:
                    self._add_external_streams_silent(f, "audio")
                elif ext in subtitle_exts:
                    self._add_external_streams_silent(f, "subtitle")
                else:
                    self._append_info_ui(f"[拖拽] 忽略不支持的文件: {os.path.basename(f)}")
    
        finally:
            self._batch_update = False
            # 刷新列表
            self.merge_update_track_list()
            self.merge_auto_recommend_container()
            self._ensure_main_video()
            self.merge_update_output_preview()
            self.merge_update_command_preview()
            self._append_info_ui("[封装] 所有文件解析完成，轨道列表已更新")
    
    
    def _add_external_streams_silent(self, file_path, stream_type):
        """
        静默添加外部音频/字幕流（不触发刷新）。
        """
        info = self._get_cached_stream_info(file_path)
        if not info:
            self._append_info_ui(f"[封装] 无法解析外部文件: {os.path.basename(file_path)}")
            return
        added = 0
        for s in info.get('streams', []):
            if s.get('codec_type') != stream_type:
                continue
            exists = any(t.file_path == file_path and t.index == s['index'] for t in self.merge_tracks)
            if exists:
                continue
            track = Track(s['index'], stream_type, s.get('codec_name', 'unknown'), file_path, True)
            self.merge_tracks.append(track)
            added += 1
        if added:
            self._append_info_ui(f"[封装] 已添加 {added} 条{stream_type}轨道: {os.path.basename(file_path)}")
        else:
            self._append_info_ui(f"[封装] 未添加新轨道: {os.path.basename(file_path)}")
    
    

    
    







    def merge_add_external_video(self):
        if self.concat_enabled.get():
            self._add_concat_video()
        elif self.pip_enabled.get():
            self._add_pip_video()
        else:
            messagebox.showinfo("提示", "请先勾选「串行合并」或「启用画中画」")


    def _add_pip_video(self):
        path = filedialog.askopenfilename(
            title="选择视频或图片文件（画中画）",
            filetypes=[
                ("媒体文件", "*.mp4 *.mkv *.avi *.mov *.flv *.webm *.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                ("视频文件", "*.mp4 *.mkv *.avi *.mov *.flv *.webm"),
                ("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif *.webp")
            ]
        )
        if not path:
            return


        info = ffprobe_json(self.ffprobe_cmd, path)
        if not info:
            self._append_info_ui(f"[封装] 无法解析文件: {path}")
            return
    
        # 检测是否为图片
        img_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
        is_image = os.path.splitext(path)[1].lower() in img_exts
    
        if is_image:
            # 图片直接添加（无音频）
            self._add_pip_video_forced(path, add_audio=False)
            self._append_info_ui(f"[封装] 已添加图片水印: {os.path.basename(path)}")
        else:
            # 视频：询问是否添加音频
            add_audio = messagebox.askyesno(
                "添加音频",
                f"是否同时添加文件「{os.path.basename(path)}」的音频流？\n选“是”将添加音频，选“否”仅添加视频作为水印。"
            )
            self._add_pip_video_forced(path, add_audio=add_audio)
            self._append_info_ui(f"[封装] 已添加画中画视频: {os.path.basename(path)}")
    
        # 统一更新界面
        self.merge_update_track_list()
        self.merge_auto_recommend_container()
        self.merge_update_output_preview()

    
    def _add_concat_video(self):
        path = filedialog.askopenfilename(
            title="选择视频文件（串联）",
            filetypes=[("媒体文件", "*.mp4 *.mkv *.avi *.mov *.flv *.webm")]
        )
        if not path:
            return


        info = ffprobe_json(self.ffprobe_cmd, path)
        if not info:
            self._append_info_ui(f"[封装] 无法解析文件: {path}")
            return
    
        # 串联模式：直接添加所有流（不询问）
        self._add_concat_video_forced(path)
        self._append_info_ui(f"[封装] 已添加串联视频: {os.path.basename(path)}")
    
        # 统一更新界面
        self.merge_update_track_list()
        self.merge_auto_recommend_container()
        self.merge_update_output_preview()




    def browse_chapter_file(self):
        path = filedialog.askopenfilename(title="选择章节文件", filetypes=[("FFmetadata", "*.txt *.chapters")])
        if path:
            self.chapter_file.set(normalize_path(path))
            if path:
                self.copy_chapters.set(False)

    def merge_copy_command(self):
        cmd_str = self.merge_cmd_preview.get(1.0, tk.END).strip()
        if cmd_str:
            self.root.clipboard_clear()
            self.root.clipboard_append(cmd_str)
            self._append_info_ui("[封装] 命令已复制到剪贴板")
        else:
            self._append_info_ui("[封装] 无命令可复制")


    def _prepare_tracks_and_inputs(self, enabled_tracks):
        """准备输入文件、文件索引，并计算所有轨道的 _type_index"""
        input_files = []
        for t in enabled_tracks:
            if t.file_path not in input_files:
                input_files.append(t.file_path)

        file_index = {f: i for i, f in enumerate(input_files)}

        # 文件流映射 + 类型索引
        file_stream_map = {}
        for f in input_files:
            info = ffprobe_json(self.ffprobe_cmd, f)
            if info:
                streams = info.get('streams', [])
                video_indices = [s['index'] for s in streams if s.get('codec_type') == 'video']
                audio_indices = [s['index'] for s in streams if s.get('codec_type') == 'audio']
                subtitle_indices = [s['index'] for s in streams if s.get('codec_type') == 'subtitle']
                file_stream_map[f] = {
                    'video': video_indices,
                    'audio': audio_indices,
                    'subtitle': subtitle_indices,
                }
            else:
                file_stream_map[f] = {'video': [0], 'audio': [0], 'subtitle': [0]}

        def get_type_index(track):
            typ = track.type
            file_path = normalize_path(track.file_path)
            indices = file_stream_map.get(file_path, {}).get(typ, [])
            try:
                return indices.index(track.index)
            except ValueError:
                return 0

        for t in enabled_tracks:
            t._type_index = get_type_index(t)

        return input_files, file_index


    def _add_input_options(self, cmd, input_files, main_video, sub_videos=None):
        """添加 -i 及前置参数（-ss/-to、循环等）"""
        main_video_path = normalize_path(main_video.file_path)
        sub_paths = [normalize_path(sv.file_path) for sv in (sub_videos or [])]

        for f in input_files:
            f_norm = normalize_path(f)

            if f_norm == main_video_path:                                   # 主视频截取
                if (main_video.enc_settings.get("trim_enabled", False) and
                    not main_video.enc_settings.get("precise_trim", False)):
                    start = main_video.enc_settings.get("trim_start", "").strip()
                    end = main_video.enc_settings.get("trim_end", "").strip()
                    if start:
                        cmd.extend(["-ss", start])
                    if end:
                        cmd.extend(["-to", end])

            elif sub_videos and f_norm in sub_paths:                        # 子视频循环
                sv = next((sv for sv in sub_videos if normalize_path(sv.file_path) == f_norm), None)
                if sv and not sv.enc_settings.get("trim_enabled", False):
                    ext = os.path.splitext(f_norm)[1].lower()
                    if ext == '.gif':
                        # GIF 动画，使用 -stream_loop -1 保证无限循环，不加 -loop 和 -framerate
                        cmd.extend(["-stream_loop", "-1"])
                    elif ext in ('.png', '.jpg', '.jpeg', '.bmp', '.webp'):
                        # 静态图片，使用 image2 循环
                        fps = main_video.enc_settings.get("frame_rate_custom", "30") \
                              if main_video.enc_settings.get("frame_rate_type") == "custom" else "30"
                        cmd.extend(["-loop", "1", "-framerate", fps])
                    else:
                        # 其他视频
                        cmd.extend(["-stream_loop", "-1"])

            cmd.extend(["-i", f_norm])
        return cmd


    def _handle_audio_trim(self, cmd, audio, audio_map_count: int) -> bool:
        """处理音频截取，返回是否已处理"""
        if not audio.enc_settings.get("trim_enabled", False):
            return False

        start_str = audio.enc_settings.get("trim_start", "").strip()
        end_str = audio.enc_settings.get("trim_end", "").strip()
        start_sec = time_to_seconds(start_str) if start_str else 0.0
        end_sec = time_to_seconds(end_str) if end_str else None

        total_duration = self._get_media_duration(audio.file_path)
        duration = (end_sec - start_sec) if end_sec is not None else \
                   (total_duration - start_sec if total_duration is not None else None)

        if duration is None or duration <= 0:
            return False

        enc = audio.enc_settings.get("encoder", "aac")
        if enc == "copy":
            enc = "aac"
            self._append_info_ui(f"音频截取启用，轨道 {audio_map_count+1} 编码器已从 copy 改为 {enc}")

        af_filter = f"atrim=start={start_sec:.3f}:duration={duration:.3f},asetpts=PTS-STARTPTS"
        cmd.extend([f"-af:a:{audio_map_count}", af_filter])
        cmd.extend([f"-c:a:{audio_map_count}", enc])
        cmd.extend([f"-b:a:{audio_map_count}", audio.enc_settings.get("bitrate", "128k")])
        cmd.extend([f"-ar:a:{audio_map_count}", audio.enc_settings.get("samplerate", "44100")])
        return True


    def _add_audio_tracks(self, cmd, enabled_tracks, file_index, reverse_enabled=False):
        audio_tracks = [t for t in enabled_tracks if t.type == "audio"]
        audio_map_count = 0
        for audio in audio_tracks:
            a_idx = file_index[audio.file_path]
            cmd.extend(["-map", f"{a_idx}:a:{audio._type_index}"])
            audio.enc_settings["_file_path"] = audio.file_path
    
            # 独立倒放优先，否则使用全局
            track_reverse = audio.enc_settings.get("audio_reverse", None)
            if track_reverse is None:
                track_reverse = reverse_enabled
    
            af_str = self._build_audio_filters(
                audio.enc_settings,
                include_trim=True,
                include_volume=True,
                include_speed=False,
                include_reverse=track_reverse
            )
            enc = audio.enc_settings.get("encoder", "copy")
            if af_str:
                if enc == "copy":
                    enc = "aac"
                    self._append_info_ui(f"音频轨 {audio_map_count+1} 应用了滤镜，编码器自动改为 aac")
                cmd.extend([f"-af:a:{audio_map_count}", af_str])
            if enc == "copy":
                cmd.extend([f"-c:a:{audio_map_count}", "copy"])
            else:
                cmd.extend([
                    f"-c:a:{audio_map_count}", enc,
                    f"-b:a:{audio_map_count}", audio.enc_settings.get("bitrate", "128k"),
                    f"-ar:a:{audio_map_count}", audio.enc_settings.get("samplerate", "44100")
                ])
            audio_map_count += 1
        if audio_map_count == 0:
            cmd.append("-an")
        else:
            cmd.extend(["-disposition:a:0", "default"])
        return cmd


    def _add_subtitles_and_chapters(self, cmd, enabled_tracks, file_index, input_files):
        """字幕 + 章节处理"""
        # 字幕
        subtitle_tracks = [t for t in enabled_tracks if t.type == "subtitle"]
        container = self.merge_container.get().lower()
        sub_map_count = 0
        first_sub_default = False

        for sub in subtitle_tracks:
            s_idx = file_index[sub.file_path]
            cmd.extend(["-map", f"{s_idx}:s:{sub._type_index}"])

            enc = sub.enc_settings.get("encoder", "copy")
            if container == "mp4":
                if enc == "copy":
                    orig_codec = getattr(sub, 'codec', '').lower()
                    if orig_codec not in ("mov_text", "mp4s"):
                        enc = "mov_text"
                        self._append_info_ui(f"[封装] 字幕格式 {orig_codec} 不兼容 MP4，自动转换为 mov_text")
                elif enc not in ("mov_text", "mp4s"):
                    enc = "mov_text"
                    self._append_info_ui(f"[封装] 字幕编码 {enc} 不兼容 MP4，自动转换为 mov_text")

            cmd.extend([f"-c:s:{sub_map_count}", enc])

            if lang := sub.enc_settings.get("language", ""):
                cmd.extend([f"-metadata:s:s:{sub_map_count}", f"language={lang}"])
            if title := sub.enc_settings.get("title", ""):
                cmd.extend([f"-metadata:s:s:{sub_map_count}", f"title={title}"])

            if not first_sub_default:
                cmd.extend([f"-disposition:s:{sub_map_count}", "default"])
                first_sub_default = True
            sub_map_count += 1

        # 章节
        if self.copy_chapters.get() and input_files:
            cmd.extend(["-map_chapters", "0"])

        chapter_file = self.chapter_file.get().strip()
        if chapter_file and os.path.exists(chapter_file):
            chapter_file_norm = normalize_path(chapter_file)
            try:
                first_i = cmd.index("-i")
                pos = first_i + 2
                cmd.insert(pos, "-i")
                cmd.insert(pos + 1, chapter_file_norm)
                cmd.extend(["-map_chapters", "1"])
            except ValueError:
                cmd.extend(["-i", chapter_file_norm, "-map_chapters", "1"])


    def _add_container_optimization(self, cmd):
        """容器优化"""
        if self.merge_container.get().lower() in ("mp4", "mov"):
            cmd.extend(["-movflags", "+faststart"])


    def _add_pip_duration_control(self, cmd, main_video, enabled_tracks):
        """PIP 时长控制：根据主音频和子视频音频存在情况选择 -shortest 或 -t"""
        # 如果启用了手动时长，则跳过内部时长控制
        if self.merge_manual_duration_enabled.get():
            dur_str = self.merge_manual_duration.get().strip()
            if dur_str and time_to_seconds(dur_str) is not None:
                # 可选：打印一次提示（但每次刷新会重复，可改为只在第一次或使用标志）
                self._append_info_ui("[封装] 手动时长已启用，将使用用户指定的时长。")
                return
        sub_videos = [t for t in enabled_tracks if t.type == "video"][1:]
        if not sub_videos:
            return  # 没有子视频，无需时长控制
    
        # 判断主视频是否包含音频
        main_video_path = normalize_path(main_video.file_path)
        has_main_audio = any(
            normalize_path(t.file_path) == main_video_path and t.type == "audio"
            for t in enabled_tracks
        )
    
        # 判断子视频是否包含音频（任何子视频有音频即认为有子音频）
        sub_paths = [normalize_path(sv.file_path) for sv in sub_videos]
        has_sub_audio = any(
            normalize_path(t.file_path) in sub_paths and t.type == "audio"
            for t in enabled_tracks
        )
    
        if has_main_audio and not has_sub_audio:
            # 只有主视频有音频，子视频无音频 → -shortest 精确
            cmd.append("-shortest")
            self._append_info_ui("[封装] 只有主音频，使用 -shortest 控制输出时长。")
        else:
            # 其他情况：有子音频或无主音频 → 优先 -t 避免无限输出
            raw_duration = self._get_media_duration(main_video.file_path)
            main_duration = None
            if main_video.enc_settings.get("trim_enabled", False):
                start = main_video.enc_settings.get("trim_start", "0").strip()
                end = main_video.enc_settings.get("trim_end", "").strip()
                start_sec = time_to_seconds(start) if start else 0.0
                end_sec = time_to_seconds(end) if end else None
                if end_sec and end_sec > start_sec:
                    main_duration = end_sec - start_sec
                elif raw_duration:
                    main_duration = raw_duration - start_sec
            else:
                main_duration = raw_duration
    
            if main_duration and main_duration > 0:
                cmd.extend(["-t", f"{main_duration:.3f}"])
                if has_sub_audio:
                    self._append_info_ui(f"[封装] 检测到子视频音频，使用 -t {main_duration:.3f}s 控制输出时长。")
                else:
                    self._append_info_ui(f"[封装] 主视频无音频，使用 -t {main_duration:.3f}s 控制输出时长。")
            else:
                # 无法计算时长，回退 -shortest
                cmd.append("-shortest")
                self._append_info_ui("[封装] 无法计算主视频时长，使用 -shortest 控制输出。")

    def _build_audio_filters(self, track_settings, include_trim=True, include_volume=True,
                             include_speed=True, include_reverse=False):
        """
        根据单个音频轨道的设置构建音频滤镜链（不含 -af 前缀）。
        返回滤镜字符串，若无滤镜则返回空字符串。
        include_reverse 作为默认倒放标志，若轨道有 audio_reverse 则优先使用。
        """
        filters = []
        # 截取
        if include_trim and track_settings.get("trim_enabled", False):
            start = track_settings.get("trim_start", "").strip()
            end = track_settings.get("trim_end", "").strip()
            start_sec = time_to_seconds(start) if start else 0.0
            end_sec = time_to_seconds(end) if end else None
            file_path = track_settings.get("_file_path", "")
            total = self._get_media_duration(file_path) if file_path else None
            if end_sec is not None:
                duration = end_sec - start_sec
            elif total is not None:
                duration = total - start_sec
            else:
                duration = None
            if duration is not None and duration > 0:
                filters.append(f"atrim=start={start_sec:.3f}:duration={duration:.3f}")
                filters.append("asetpts=PTS-STARTPTS")
    
        # 音量
        if include_volume and track_settings.get("volume_enabled", False):
            vol = track_settings.get("volume", 1.0)
            if vol != 1.0:
                filters.append(f"volume={vol:.2f}")
    
        # 变速
        if include_speed and track_settings.get("speed_enabled", False):
            factor = float(track_settings.get("speed_factor", "1.0"))
            if factor != 1.0 and factor > 0:
                atempo = build_atempo_chain(factor)
                if atempo:
                    filters.append(atempo)
    
        # 倒放：优先使用轨道独立设置，否则使用传入的 include_reverse
        track_reverse = track_settings.get("audio_reverse")
        if track_reverse is None:
            track_reverse = include_reverse
        if track_reverse:
            filters.append("areverse")
    
        return ",".join(filters) if filters else ""
    
    def _build_normal_cmd(self, enabled_tracks, output_norm, only_audio=False):
        """
        普通封装模式：支持视频滤镜、多音频/字幕、音频截取、音频混合（amix）与音量调整。
        若 only_audio=True，则仅处理音频流，忽略视频和字幕。
        """
        cmd = [self.ffmpeg_cmd, "-y", "-fflags", "+genpts"]
    
        # 获取所有音频轨道（无论是否仅音频模式）
        audio_tracks = [t for t in enabled_tracks if t.type == "audio"]
    
        if only_audio:
            input_files = []
            file_index = {}
            audio_tracks = [t for t in enabled_tracks if t.type == "audio"]
            for audio in audio_tracks:
                if audio.file_path not in file_index:
                    file_index[audio.file_path] = len(input_files)
                    input_files.append(audio.file_path)
            # 为每个音频轨道设置 _type_index
            for audio in audio_tracks:
                info = self._get_cached_stream_info(audio.file_path)
                if info:
                    audio_indices = [s['index'] for s in info['streams'] if s.get('codec_type') == 'audio']
                    try:
                        audio._type_index = audio_indices.index(audio.index)
                    except ValueError:
                        audio._type_index = 0
                else:
                    audio._type_index = 0
            # 然后添加输入
            for f in input_files:
                cmd.extend(["-i", normalize_path(f)])
            main_video = None
            video_reverse = False
            video_tracks = []
        else:
            # 完整模式
            input_files, file_index = self._prepare_tracks_and_inputs(enabled_tracks)
            video_tracks = [t for t in enabled_tracks if t.type == "video"]
            if not video_tracks:
                self._append_info_ui("[封装] 没有启用的视频轨道")
                return []
            main_video = video_tracks[0]
    
            # 在添加输入之前插入硬件解码参数（使用主视频设置）
            self._add_hwaccel_params(cmd, main_video.enc_settings)
    
            # 准备输入文件和索引
            input_files, file_index = self._prepare_tracks_and_inputs(enabled_tracks)
    
            # 添加输入选项（-i 及前置 -ss/-to）
            cmd = self._add_input_options(cmd, input_files, main_video)
    
            # 视频处理
            v_idx = file_index[main_video.file_path]
            cmd.extend(["-map", f"{v_idx}:v:{main_video._type_index}"])
            v_settings = main_video.enc_settings
            vcodec = v_settings.get("encoder", "copy")
            video_reverse = v_settings.get("reverse_enabled", False)
            if vcodec == "copy" and video_reverse:
                video_reverse = False
                self._append_info_ui("[封装] 主视频为流复制模式，已自动禁用视频倒放")
    
            if vcodec == "copy":
                cmd.extend(["-c:v", "copy"])
            else:
                video_filters = build_video_filter_chain(
                    v_settings,
                    include_subtitle=False,
                    include_speed=False,
                    enhance_settings=v_settings.get("enhance", {}),
                    reverse=video_reverse
                )
                if video_filters and video_filters != "null":
                    cmd.extend(["-vf", video_filters])
                strategy = get_encoder_strategy(vcodec)
                cmd = strategy.build_params(cmd, v_settings)
    
                # ---- 视频元数据 ----
                lang = main_video.language
                title = main_video.title
                if lang:
                    cmd.extend(["-metadata:s:v:0", f"language={lang}"])
                if title:
                    cmd.extend(["-metadata:s:v:0", f"title={title}"])
    
        # ---- 音频处理（所有模式） ----
        mix_tracks = [t for t in audio_tracks if t.enc_settings.get("mix_enabled", False)]
    
        if not mix_tracks:
            audio_map_count = 0
            for audio in audio_tracks:
                a_idx = file_index[audio.file_path]
                cmd.extend(["-map", f"{a_idx}:a:{audio._type_index}"])
                audio.enc_settings["_file_path"] = audio.file_path
                track_reverse = audio.enc_settings.get("audio_reverse")
                if track_reverse is None:
                    track_reverse = video_reverse
                af_str = self._build_audio_filters(
                    audio.enc_settings,
                    include_trim=True,
                    include_volume=True,
                    include_speed=True,
                    include_reverse=track_reverse
                )
                enc = audio.enc_settings.get("encoder", "copy")
                if af_str:
                    if enc == "copy":
                        enc = "aac"
                        self._append_info_ui(f"音频轨 {audio_map_count+1} 应用了滤镜，编码器自动改为 aac")
                    cmd.extend([f"-af:a:{audio_map_count}", af_str])
                if enc == "copy":
                    cmd.extend([f"-c:a:{audio_map_count}", "copy"])
                else:
                    cmd.extend([
                        f"-c:a:{audio_map_count}", enc,
                        f"-b:a:{audio_map_count}", audio.enc_settings.get("bitrate", "128k"),
                        f"-ar:a:{audio_map_count}", audio.enc_settings.get("samplerate", "44100")
                    ])
    
                # ---- 音频元数据 ----
                lang_audio = audio.language
                title_audio = audio.title
                if lang_audio:
                    cmd.extend([f"-metadata:s:a:{audio_map_count}", f"language={lang_audio}"])
                if title_audio:
                    cmd.extend([f"-metadata:s:a:{audio_map_count}", f"title={title_audio}"])
                    cmd.extend([f"-metadata:s:a:{audio_map_count}", f"handler_name={title_audio}"])
    
                audio_map_count += 1
            if audio_map_count == 0:
                cmd.append("-an")
            else:
                cmd.extend(["-disposition:a:0", "default"])
        else:
            if len(mix_tracks) == 1:
                audio = mix_tracks[0]
                a_idx = file_index[audio.file_path]
                cmd.extend(["-map", f"{a_idx}:a:{audio._type_index}"])
                audio.enc_settings["_file_path"] = audio.file_path
                af_str = self._build_audio_filters(
                    audio.enc_settings,
                    include_trim=True,
                    include_volume=True,
                    include_speed=True,
                    include_reverse=audio.enc_settings.get("audio_reverse", video_reverse)
                )
                enc = audio.enc_settings.get("encoder", "copy")
                if af_str:
                    if enc == "copy":
                        enc = "aac"
                        self._append_info_ui("单流混合（音量/截取/倒放）强制编码为 aac")
                    cmd.extend(["-af", af_str])
                if enc == "copy":
                    cmd.extend(["-c:a", "copy"])
                else:
                    cmd.extend([
                        "-c:a", enc,
                        "-b:a", audio.enc_settings.get("bitrate", "128k"),
                        "-ar", audio.enc_settings.get("samplerate", "44100")
                    ])
                # ---- 混合音频元数据 ----
                lang = audio.language
                title = audio.title
                if lang:
                    cmd.extend(["-metadata:s:a:0", f"language={lang}"])
                if title:
                    cmd.extend(["-metadata:s:a:0", f"title={title}"])
                    cmd.extend(["-metadata:s:a:0", f"handler_name={title}"])
                cmd.extend(["-disposition:a:0", "default"])
            else:
                filter_parts = []
                inputs = len(mix_tracks)
                for i, audio in enumerate(mix_tracks):
                    a_idx = file_index[audio.file_path]
                    audio.enc_settings["_file_path"] = audio.file_path
                    af_str = self._build_audio_filters(
                        audio.enc_settings,
                        include_trim=True,
                        include_volume=True,
                        include_speed=False,
                        include_reverse=audio.enc_settings.get("audio_reverse", video_reverse)
                    )
                    if af_str:
                        filter_parts.append(f"[{a_idx}:a]{af_str}[a{i}]")
                    else:
                        filter_parts.append(f"[{a_idx}:a]asetpts=PTS-STARTPTS[a{i}]")
                amix_filter = f"{' '.join(f'[a{i}]' for i in range(inputs))}amix=inputs={inputs}:duration=longest[aout]"
                filter_parts.append(amix_filter)
                cmd.extend(["-filter_complex", ";".join(filter_parts)])
                cmd.extend(["-map", "[aout]"])
                first_mix = mix_tracks[0]
                enc = first_mix.enc_settings.get("encoder", "aac")
                if enc == "copy":
                    enc = "aac"
                    self._append_info_ui("[封装] 混合模式下编码器不能为 copy，已自动改为 aac")
                cmd.extend([
                    "-c:a", enc,
                    "-b:a", first_mix.enc_settings.get("bitrate", "128k"),
                    "-ar", first_mix.enc_settings.get("samplerate", "44100")
                ])
                # ---- 混合音频元数据（使用第一个混合轨道的元数据） ----
                lang = first_mix.language
                title = first_mix.title
            if lang:
                cmd.extend(["-metadata:s:a:0", f"language={lang}"])
            if title:
                cmd.extend(["-metadata:s:a:0", f"title={title}"])
                cmd.extend(["-metadata:s:a:0", f"handler_name={title}"])
                cmd.extend(["-disposition:a:0", "default"])
    
        if only_audio:
            cmd.append("-vn")
    
        # 字幕与章节（仅非仅音频模式）
        if not only_audio:
            self._add_subtitles_and_chapters(cmd, enabled_tracks, file_index, input_files)
    
        # 容器优化
        container = self.merge_container.get().lower()
        if container in ("mp4", "mov") and not only_audio:
            cmd.extend(["-movflags", "+faststart"])
    
        cmd.append(output_norm)
        return cmd
    
    
    def _build_pip_cmd(self, enabled_tracks, output_norm):
        """画中画模式（叠加多个视频）"""
        # 强制禁用组合跳转
        for track in enabled_tracks:
            if track.type == "video":
                track.enc_settings["combo_seek"] = False
    
        cmd = [self.ffmpeg_cmd, "-y", "-fflags", "+genpts"]
        input_files, file_index = self._prepare_tracks_and_inputs(enabled_tracks)
        video_tracks = [t for t in enabled_tracks if t.type == "video"]
        if not video_tracks:
            self._append_info_ui("[封装-画] 没有启用的视频轨道")
            return []
        main_video = video_tracks[0]
        sub_videos = video_tracks[1:]
    
        # 画中画模式下强制使用精准截取（由滤镜处理）
        self._add_hwaccel_params(cmd, main_video.enc_settings)
        main_video.enc_settings["precise_trim"] = True
        cmd = self._add_input_options(cmd, input_files, main_video, sub_videos)

        main_idx = file_index[main_video.file_path]

        
        # ---- 构建子视频信息列表（临时复制设置，避免修改原轨道） ----
        sub_infos = []
        for sv in sub_videos:
            sv_settings = sv.enc_settings.copy()   # 复制一份，不影响原轨道
            
            if sv_settings.get("encoder") == "copy":
                sv_settings["encoder"] = "libx265"
                self._append_info_ui(f"[封装-画] 从视频 {os.path.basename(sv.file_path)} copy 已临时改为 libx265（画中画必须重新编码）")
            
            sub_infos.append((file_index[sv.file_path], sv.file_path, sv_settings))
    
        # 获取倒放标志，同时检测视频编码器（画中画强制重新编码，但为保险仍做检测）
        vcodec = main_video.enc_settings.get("encoder", "libx265")
        reverse_flag = main_video.enc_settings.get("reverse_enabled", False)
        if vcodec == "copy" and reverse_flag:
            reverse_flag = False
        #    self._append_info_ui("[封装] 画中画模式视频为 copy（理论上不会发生），已禁用音频倒放")
            # 但画中画模式已经强制将 copy 改为 libx265，所以此分支通常不会执行
    
        # 构建叠加滤镜（传递 reverse_flag 用于视频倒放） 检查主视频是否启用字幕烧录
        include_subtitle_main = main_video.enc_settings.get("subtitle_enabled", False) and bool(main_video.enc_settings.get("subtitle_path", "").strip())
        complex_filter, final_v_label = self._build_overlay_filter_complex(
            main_idx, main_video.enc_settings, sub_infos,
            include_subtitle_main=include_subtitle_main,
            enhance_settings=main_video.enc_settings.get("enhance", {}),
            reverse=reverse_flag
        )
        cmd.extend(["-filter_complex", complex_filter])
        cmd.extend(["-map", final_v_label])
    
        # 视频编码（PIP强制不使用 copy）
        if vcodec == "copy":
            self._append_info_ui("[封装-画] 画中画模式不支持 copy，自动改为 libx265")
            vcodec = "libx265"
            main_video.enc_settings["encoder"] = vcodec
        strategy = get_encoder_strategy(vcodec)
        cmd = strategy.build_params(cmd, main_video.enc_settings)
    
        # 音频处理（传入修正后的 reverse_flag）   
        # 新改动 画中画音频独立控制 所以传入 False
        self._add_audio_tracks(cmd, enabled_tracks, file_index, reverse_enabled=False)
    
        self._add_subtitles_and_chapters(cmd, enabled_tracks, file_index, input_files)
        self._add_pip_duration_control(cmd, main_video, enabled_tracks)
        self._add_container_optimization(cmd)
        cmd.append(output_norm)
        return cmd



    def _build_concat_cmd(self, enabled_tracks, output_norm, preview=False):
        """
        生成串行合并（Concat）命令。
        支持两种模式：
        1. 流复制模式（最高效，使用 concat demuxer）
        2. 重新编码模式（使用 filter_complex concat）
        """
        video_tracks = [t for t in enabled_tracks if t.type == "video"]
        if not video_tracks:
            self._append_info_ui("[串联] 没有启用的视频轨道")
            return []

        audio_tracks = [t for t in enabled_tracks if t.type == "audio"]
        main_video = video_tracks[0]

        # 判断使用哪种模式
        vcodec = main_video.enc_settings.get("encoder", "copy")
        acodec = audio_tracks[0].enc_settings.get("encoder", "copy") if audio_tracks else "copy"

        use_copy_mode = (vcodec == "copy") and (acodec == "copy" or not audio_tracks)

        cmd = [self.ffmpeg_cmd, "-y", "-fflags", "+genpts"]

        # 硬件解码参数（流复制模式通常无需，但保留以兼容）
        if video_tracks:
            self._add_hwaccel_params(cmd, video_tracks[0].enc_settings)

        if use_copy_mode:
            if not self._check_video_params_consistent(video_tracks, silent=True):  # silent=True 避免内部打印
                self._append_info_ui("[串联] 检测到视频参数不一致，可在规格列查看，自动切换到重新编码模式以确保兼容性。")
                use_copy_mode = False
        
        if use_copy_mode:
            return self._build_concat_copy_mode(cmd, video_tracks, audio_tracks, output_norm, preview=preview)
        else:
            return self._build_concat_reencode_mode(cmd, video_tracks, audio_tracks, main_video, output_norm)


    def _build_concat_copy_mode(self, cmd, video_tracks, audio_tracks, output_norm, preview=False):
        """流复制模式 - 使用 concat demuxer（最高性能）"""
        import tempfile
    
        if preview:
            # 预览模式：使用占位符，不创建实际文件
            list_path = "concat_random.txt"
            self._append_info_ui("[串联-流] 预览命令，txt列表使用占位名，点击开始合并后随机生成")
        else:
            # 实际执行：创建临时文件
            fd, list_path = tempfile.mkstemp(suffix='.txt', prefix='concat_', text=True)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    for track in video_tracks:
                        safe_path = normalize_path(track.file_path).replace("'", "'\\''")
                        f.write(f"file '{safe_path}'\n")
            except Exception as e:
                self._append_info_ui(f"[串联-流] 生成文件列表失败: {e}")
                os.close(fd) if 'fd' in locals() else None
                return []
            # 存储真实路径以便后续清理
            if not hasattr(self, '_temp_concat_lists'):
                self._temp_concat_lists = []
            self._temp_concat_lists.append(list_path)
    
        cmd.extend(["-f", "concat", "-safe", "0", "-i", list_path])
        cmd.extend(["-c:v", "copy"])
        if audio_tracks:
            cmd.extend(["-c:a", "copy"])
        else:
            cmd.append("-an")
    
        self._add_container_optimization(cmd)
        cmd.append(output_norm)
    
        self._append_info_ui("[串联-流] 使用流复制模式（concat demuxer）")
        return cmd


    def _build_concat_reencode_mode(self, cmd, video_tracks, audio_tracks, main_video, output_norm):
        """
        重新编码模式 - 使用 filter_complex concat，支持每个视频独立音频源，
        并统一应用主视频设置的视频滤镜（裁剪、缩放、旋转、颜色校正等）和音频滤镜（音量、变速、倒放）。
        """
        # 为每个视频轨道单独添加 -i（允许重复文件）
        for track in video_tracks:
            cmd.extend(["-i", normalize_path(track.file_path)])
    
        n = len(video_tracks)
        filter_parts = []
    
        # 获取主视频设置中的增强参数
        enhance_settings = main_video.enc_settings.get("enhance", {})
        reverse_flag = main_video.enc_settings.get("reverse_enabled", False)
    
        # ---- 构建每个片段的预处理（截取、设置 PTS） ----
        for i, track in enumerate(video_tracks):
            # 视频：只设置 PTS（截取已在输入时通过 -ss/-to 处理）
            filter_parts.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")
    
            # 音频源处理
            audio_source = track.enc_settings.get("audio_source_type", "self")
            if audio_source == "self":
                filter_parts.append(f"[{i}:a]asetpts=PTS-STARTPTS[a{i}]")
            elif audio_source == "silence":
                # 生成静音流，时长匹配视频片段
                start_str = track.enc_settings.get("trim_start", "").strip()
                end_str = track.enc_settings.get("trim_end", "").strip()
                start_sec = time_to_seconds(start_str) if start_str else 0.0
                end_sec = time_to_seconds(end_str) if end_str else None
                total_duration = self._get_media_duration(track.file_path)
                if end_sec is not None:
                    duration = end_sec - start_sec
                elif total_duration is not None:
                    duration = total_duration - start_sec
                else:
                    duration = 10.0
                duration = max(0.1, duration)
                filter_parts.append(f"anullsrc=r=44100:cl=stereo:duration={duration}[a{i}]")
            else:
                self._append_info_ui(f"[串联-编] 音频源类型 '{audio_source}' 未知，降级使用视频自身音频")
                filter_parts.append(f"[{i}:a]asetpts=PTS-STARTPTS[a{i}]")
    
        # ---- 视频 concat ----
        v_concat = f"[{']['.join(f'v{i}' for i in range(n))}]concat=n={n}:v=1:a=0[vout]"
        filter_parts.append(v_concat)
    
        # ---- 音频 concat ----
        a_concat = f"[{']['.join(f'a{i}' for i in range(n))}]concat=n={n}:v=0:a=1[aout]"
        filter_parts.append(a_concat)
    
        # ---- 应用视频滤镜到合并后的视频流 ----
        video_filters = build_video_filter_chain(
            main_video.enc_settings,
            include_subtitle=False,
            include_speed=True,          # 变速会影响时长，但会在 concat 之后应用，普通模式也如此
            include_trim=False,          # 已截取
            include_format=True,         # 像素格式
            enhance_settings=enhance_settings,
            reverse=reverse_flag
        )
    
        if video_filters and video_filters != "null":
            filter_parts.append(f"[vout]{video_filters}[vfinal]")
            vmap = "[vfinal]"
            self._append_info_ui("[串联-编] 已应用视频滤镜到合并结果")
        else:
            vmap = "[vout]"
    
        # ---- 应用音频滤镜到合并后的音频流 ----
        audio_filters = []
        # 音量
        if main_video.enc_settings.get("volume_enabled", False):
            vol = main_video.enc_settings.get("volume", 1.0)
            if vol != 1.0:
                audio_filters.append(f"volume={vol:.2f}")
        # 变速
        if main_video.enc_settings.get("speed_enabled", False):
            factor = float(main_video.enc_settings.get("speed_factor", "1.0"))
            if factor != 1.0 and factor > 0:
                atempo = build_atempo_chain(factor)
                if atempo:
                    audio_filters.append(atempo)
        # 倒放
        if reverse_flag:
            audio_filters.append("areverse")
    
        if audio_filters:
            afilter_str = ",".join(audio_filters)
            filter_parts.append(f"[aout]{afilter_str}[afinal]")
            amap = "[afinal]"
            self._append_info_ui("[串联-编] 已应用音频滤镜到合并结果")
        else:
            amap = "[aout]"
    
        # 组合 filter_complex
        cmd.extend(["-filter_complex", ";".join(filter_parts)])
        cmd.extend(["-map", vmap, "-map", amap])
    
        # ---- 视频编码参数 ----
        v_settings = main_video.enc_settings.copy()
        vcodec = v_settings.get("encoder", "libx265")
        if vcodec == "copy":
            self._append_info_ui("[串联-编] 重新编码模式下视频编码器自动改为 libx265")
            vcodec = "libx265"
            v_settings["encoder"] = "libx265"
        strategy = get_encoder_strategy(vcodec)
        cmd = strategy.build_params(cmd, v_settings)
    
        # ---- 音频编码参数 ----
        if audio_tracks:
            a_settings = audio_tracks[0].enc_settings
            enc = a_settings.get("encoder", "aac")
            if enc == "copy":
                enc = "aac"
                self._append_info_ui("[串联-编] 重新编码模式下音频自动从 copy 改为 aac")
            cmd.extend([
                "-c:a", enc,
                "-b:a", a_settings.get("bitrate", "128k"),
                "-ar", a_settings.get("samplerate", "44100")
            ])
        else:
            cmd.extend(["-c:a", "aac", "-b:a", "128k", "-ar", "44100"])
    
        self._add_container_optimization(cmd)
        cmd.append(output_norm)
        self._append_info_ui(f"[串联-编] 使用 filter_complex 重新编码模式（{n} 个片段）")
        return cmd
    
    def merge_build_cmd_list(self, output_override=None, preview=False) -> List[str]:
        """
        根据当前模式生成合并/封装的 FFmpeg 命令列表。
        """
        if any(t.enc_settings.get("_placeholder", False) for t in enabled_tracks):
            self._append_info_ui("[封装] 存在占位轨道，命令生成被推迟")
            return []

        if not self.ffmpeg_cmd:
            self._append_info_ui("未找到 ffmpeg，无法生成合并命令。")
            return []
    
        if output_override is not None:
            output = output_override
        else:
            output = self.merge_output.get().strip()
        if not output:
            return []
    
        only_audio = self.merge_only_audio.get() if hasattr(self, 'merge_only_audio') else False
        enabled_tracks = [t for t in self.merge_tracks if t.enabled]
        if not enabled_tracks:
            self._append_info_ui("[封装] 没有启用的轨道")
            return []
    
        output_norm = normalize_path(output)
    
        # ---- 仅音频模式：强制普通封装，并自动调整输出扩展名 ----
        if only_audio:
            self._append_info_ui("[封装] 已切换为仅音频模式（忽略视频和字幕）")
            if self.pip_enabled.get() or self.concat_enabled.get():
                self._append_info_ui("[封装] 仅音频模式已自动切换到普通封装模式")
            # 如果扩展名不是常见音频格式，改为 .m4a
            base, ext = os.path.splitext(output_norm)
            if ext.lower() not in ('.m4a', '.mp3', '.flac', '.wav', '.aac', '.opus', '.ac3', '.ogg'):
                output_norm = base + ".m4a"
                self._append_info_ui(f"[封装] 仅音频模式，输出扩展名自动改为 .m4a")
            cmd_list = self._build_normal_cmd(enabled_tracks, output_norm, only_audio=True)
        else:
            # 根据模式选择命令生成函数
            if self.pip_enabled.get():
                cmd_list = self._build_pip_cmd(enabled_tracks, output_norm)
            elif self.concat_enabled.get():
                cmd_list = self._build_concat_cmd(enabled_tracks, output_norm, preview=preview)
            else:
                cmd_list = self._build_normal_cmd(enabled_tracks, output_norm)
    
        if not cmd_list:
            self._append_info_ui("[封装] 命令生成失败，请检查设置")
            return []
    
        # ---- 手动时长覆盖（最高优先级） ----
        if self.merge_manual_duration_enabled.get():
            dur_str = self.merge_manual_duration.get().strip()
            if dur_str:
                dur_sec = time_to_seconds(dur_str)
                if dur_sec is not None and dur_sec > 0:
                    # 移除已有的 -t 和 -shortest 及其参数
                    new_cmd = []
                    skip_next = False
                    for i, arg in enumerate(cmd_list):
                        if skip_next:
                            skip_next = False
                            continue
                        if arg in ('-t', '-shortest'):
                            if arg == '-t':
                                if i+1 < len(cmd_list) and not cmd_list[i+1].startswith('-'):
                                    skip_next = True
                            continue
                        new_cmd.append(arg)
                    if new_cmd and new_cmd[-1] != '-t':
                        output_path = new_cmd.pop()
                        new_cmd.extend(['-t', f'{dur_sec:.3f}'])
                        new_cmd.append(output_path)
                    cmd_list = new_cmd
                else:
                    self._append_info_ui("警告：手动时长格式无效，已忽略")
    
        return cmd_list
    
    
    def _check_video_params_consistent(self, video_tracks, silent=False) -> bool:
        """
        检查所有视频轨道的编码参数是否一致（用于串联 copy 模式）。
        对比参数包括编码器名称 (codec_name)、分辨率 (高宽)、像素格式 (pix_fmt)、时间基 (time_base)、帧率 (avg_frame_rate 或 r_frame_rate)、
        这些参数是 流复制模式下 concat 要求一致的关键参数。缺少任一项都可能导致输出异常（如花屏、音画不同步、无法播放）。
        使用缓存避免重复检查，缓存键基于所有文件的路径+修改时间。
        返回 True 表示参数一致，False 表示不一致（建议切换到重新编码模式）。
        """
        if len(video_tracks) < 2:
            return True
    
        # ---- 构建缓存键 ----
        # 使用 (文件路径, 修改时间) 元组列表作为键
        cache_key_parts = []
        for track in video_tracks:
            path = track.file_path
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0
            cache_key_parts.append((path, mtime))
        cache_key = tuple(cache_key_parts)  # 元组可哈希
    
        # 检查缓存
        if not hasattr(self, '_concat_params_cache'):
            self._concat_params_cache = {}
        if cache_key in self._concat_params_cache:
            return self._concat_params_cache[cache_key]
    
        # ---- 实际检查 ----
        ref_track = video_tracks[0]
        ref_info = self._get_cached_stream_info(ref_track.file_path)
        if not ref_info:
            self._concat_params_cache[cache_key] = False
            return False
    
        ref_stream = None
        for s in ref_info.get('streams', []):
            if s.get('codec_type') == 'video':
                ref_stream = s
                break
        if not ref_stream:
            self._concat_params_cache[cache_key] = False
            return False
    
        # 提取参考参数
        ref_codec = ref_stream.get('codec_name')          #编码器名称
        ref_w = ref_stream.get('width')                   #宽度
        ref_h = ref_stream.get('height')
        ref_pix_fmt = ref_stream.get('pix_fmt')           #像素格式
        ref_time_base = ref_stream.get('time_base')       #时间基
        ref_frame_rate = ref_stream.get('avg_frame_rate') or ref_stream.get('r_frame_rate')     #帧率
    
        # 逐个比较后续轨道
        for track in video_tracks[1:]:
            info = self._get_cached_stream_info(track.file_path)
            if not info:
                self._concat_params_cache[cache_key] = False
                return False
    
            stream = None
            for s in info.get('streams', []):
                if s.get('codec_type') == 'video':
                    stream = s
                    break
            if not stream:
                self._concat_params_cache[cache_key] = False
                return False
    
            # 比较关键参数
            if stream.get('codec_name') != ref_codec:
                self._concat_params_cache[cache_key] = False
                return False
            if stream.get('width') != ref_w or stream.get('height') != ref_h:
                self._concat_params_cache[cache_key] = False
                return False
            if stream.get('pix_fmt') != ref_pix_fmt:
                self._concat_params_cache[cache_key] = False
                return False
            if stream.get('time_base') != ref_time_base:
                self._concat_params_cache[cache_key] = False
                return False
    
            frame_rate = stream.get('avg_frame_rate') or stream.get('r_frame_rate')
            if frame_rate != ref_frame_rate:
                self._concat_params_cache[cache_key] = False
                return False
    
        # 所有参数一致
        self._concat_params_cache[cache_key] = True
        return True  
    
    
    


    def merge_update_command_preview(self, output_override=None):
        # 取消之前排队的更新
        if hasattr(self, '_merge_preview_after_id') and self._merge_preview_after_id:
            self.root.after_cancel(self._merge_preview_after_id)
            self._merge_preview_after_id = None
    
        # 延迟执行真正的更新（100ms 足够覆盖连续操作）
        self._merge_preview_after_id = self.root.after(100, self._do_merge_update_command_preview, output_override)
    
    def _do_merge_update_command_preview(self, output_override=None):
        self._merge_preview_after_id = None
        if self._batch_update:
            return

        # ===== 检测是否有占位轨道 =====
        has_placeholder = any(
            t.enc_settings.get("_placeholder", False)
            for t in self.merge_tracks
            if t.type == "video"
        )
        if has_placeholder:
            current_state = self.merge_cmd_preview.cget('state')
            self.merge_cmd_preview.config(state='normal')
            self.merge_cmd_preview.delete(1.0, tk.END)
            self.merge_cmd_preview.insert(tk.END, "正在解析文件信息，命令预览将在解析完成后生成...")
            self.merge_cmd_preview.config(state=current_state)
            return

        # 临时启用以便更新内容
        current_state = self.merge_cmd_preview.cget('state')
        self.merge_cmd_preview.config(state='normal')
    
        # 清空并填充
        self.merge_cmd_preview.delete(1.0, tk.END)
        cmd_list = self.merge_build_cmd_list(output_override=output_override, preview=True)
        if not cmd_list:
            self.merge_cmd_preview.insert(tk.END, "参数不完整，无法生成命令")
        else:
            cmd_str = format_cmd_for_display(cmd_list)
            self.merge_cmd_preview.insert(tk.END, cmd_str)
    
        # 恢复用户设置的编辑状态
        self.merge_cmd_preview.config(state=current_state)

    def _get_cached_stream_info(self, path):
        """
        获取媒体流信息，带缓存。
        缓存键 = (normalize_path(path), mtime)，文件修改后自动失效。
        """
        norm_path = normalize_path(path)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        key = (norm_path, mtime)
        if key in self._stream_info_cache:
            return self._stream_info_cache[key]
        info = ffprobe_json(self.ffprobe_cmd, path)
        if info:
            self._stream_info_cache[key] = info
        return info

    def merge_get_media_info(self, path):
        return self._get_cached_stream_info(path)

    def merge_load_video_info(self):
        if self._suppress_main_video_trace:
            return

        path = self.merge_video.get().strip()
        if not path or not os.path.exists(path):
            self.merge_tracks = []
            self.merge_update_track_list()
            self.merge_update_output_preview()
            return
    
        self._batch_update = True
        try:
            ext = os.path.splitext(path)[1].lower().lstrip('.')
            self.original_container = ext if ext in ['mp4', 'mkv', 'mov', 'avi', 'webm'] else 'mp4'
            info = self._get_cached_stream_info(path)
            if not info:
                self._append_info_ui(f"[封装] 无法解析媒体信息: {path}，可能 ffprobe 失败")
                self.merge_tracks = []
                self.merge_update_track_list()
                self.merge_update_output_preview()
                return
            streams = info.get("streams", [])
            if not streams:
                self._append_info_ui(f"[封装] {path} 中没有发现任何流")
                return
            self.merge_tracks = []
            for s in streams:
                st = s.get("codec_type")
                if st not in ("video","audio","subtitle"):
                    continue
                track = Track(s["index"], st, s.get("codec_name", "unknown"), path, True)
                self.merge_tracks.append(track)
            if not self.merge_tracks:
                self._append_info_ui(f"[封装] {path} 中未找到视频/音频/字幕轨道")
            self.merge_update_track_list()
            self.merge_auto_recommend_container()
            self.merge_update_output_preview()
        finally:
            self._batch_update = False
            self.merge_update_track_list()
            self.merge_update_command_preview()  # 最终统一刷新一次

    def merge_update_track_list(self):
        if self._batch_update:
            return
    
        # 清空现有行
        for item in self.merge_tree.get_children():
            self.merge_tree.delete(item)
    
        # 配置标签颜色（主视频、子视频、音频、字幕）
        # 每种类型有两套：偶数行和奇数行（交替）
        self.merge_tree.tag_configure('even_main', background='#d9e8f7')
        self.merge_tree.tag_configure('odd_main', background='#85C1E9')
        self.merge_tree.tag_configure('even_pip', background='#d9f0d9')
        self.merge_tree.tag_configure('odd_pip', background='#bde0bd')
        self.merge_tree.tag_configure('even_concat', background='#fdebd0')
        self.merge_tree.tag_configure('odd_concat', background='#fad7a5')
        self.merge_tree.tag_configure('even_audio', background='#f0f0f0')
        self.merge_tree.tag_configure('odd_audio', background='#e0e0e0')
        self.merge_tree.tag_configure('even_subtitle', background='#e8e0f0')
        self.merge_tree.tag_configure('odd_subtitle', background='#d8cfe8')
        self.merge_tree.tag_configure('even_video', background='#f0f0f0')
        self.merge_tree.tag_configure('odd_video', background='#e0e0e0')
    
        # 确定主视频
        enabled_video_tracks = [t for t in self.merge_tracks if t.enabled and t.type == "video"]
        main_video = enabled_video_tracks[0] if enabled_video_tracks else None
    
        for i, track in enumerate(self.merge_tracks):
            # 根据轨道类型和模式确定标签
            if track.type == "video":
                if track == main_video:
                    tag = 'even_main' if i % 2 == 0 else 'odd_main'
                elif self.pip_enabled.get():
                    tag = 'even_pip' if i % 2 == 0 else 'odd_pip'
                elif self.concat_enabled.get():
                    tag = 'even_concat' if i % 2 == 0 else 'odd_concat'
                else:
                    tag = 'even_video' if i % 2 == 0 else 'odd_video'
            elif track.type == "audio":
                tag = 'even_audio' if i % 2 == 0 else 'odd_audio'
            elif track.type == "subtitle":
                tag = 'even_subtitle' if i % 2 == 0 else 'odd_subtitle'
            else:
                tag = 'even' if i % 2 == 0 else 'odd'  # fallback
    
            # 显示内容
            enabled_text = "✓" if track.enabled else "✗"
            enc_text = "复制流" if not track.is_encoding() else track.enc_settings.get("encoder", "?")
            display_type = track.type
            if track.type == "video" and track == main_video:
                display_type = "视频(主)"
            elif track.type == "video":
                if self.pip_enabled.get():
                    display_type = "视频(画)"
                elif self.concat_enabled.get():
                    display_type = "视频(串)"
                else:
                    display_type = "视频(从)"
    
            # ---- 规格 ----
            if track.type == "video":
                if track.enc_settings.get("_placeholder", False):
                    detail = "解析中…"
                elif track.enc_settings.get("_error"):
                    detail = "❌ 解析失败"
                else:
                    orig_w, orig_h = self._get_video_dimensions_cached(track.file_path)
                    if orig_w and orig_h:
                        if track.enc_settings.get("scale_enabled", False):
                            method = track.enc_settings.get("scale_method", "width")
                            sw = track.enc_settings.get("scale_width", "").strip()
                            sh = track.enc_settings.get("scale_height", "").strip()
                            if method == "width" and sw:
                                scale_str = f"{sw}x-2"
                            elif method == "height" and sh:
                                scale_str = f"-2x{sh}"
                            elif method == "exact" and sw and sh:
                                scale_str = f"{sw}x{sh}"
                            else:
                                scale_str = ""
                            if scale_str:
                                detail = f"{orig_w}x{orig_h} → {scale_str}"
                            else:
                                detail = f"{orig_w}x{orig_h}"
                        else:
                            detail = f"{orig_w}x{orig_h}"
                    else:
                        detail = "未知"
                    # 追加时长
                    dur = self._get_media_duration(track.file_path)
                    if dur is not None:
                        detail += f" ({seconds_to_time(dur)})"
            elif track.type == "audio":
                info = self._get_cached_stream_info(track.file_path)
                if info:
                    streams = info.get('streams', [])
                    for s in streams:
                        if s.get('codec_type') == 'audio' and s.get('index') == track.index:
                            bitrate = s.get('bit_rate')
                            if bitrate:
                                try:
                                    bitrate_kbps = int(bitrate) // 1000
                                    detail = f"{bitrate_kbps} kbps"
                                except:
                                    detail = s.get('codec_name', '音频')
                            else:
                                # 构建备选信息
                           #     codec_name = s.get('codec_name', '')
                                sample_rate = s.get('sample_rate')
                                channels = s.get('channels')
                                parts = []
                      #          if codec_name:
                      #              parts.append(codec_name)
                                if sample_rate:
                                    parts.append(f"{int(sample_rate)//1000}kHz")
                                if channels:
                                    parts.append(f"{channels}ch")
                                detail = " ".join(parts) if parts else "-"
                            dur = self._get_media_duration(track.file_path)
                            if dur is not None:
                                detail += f" ({seconds_to_time(dur)})"
                            break
                    else:
                        detail = "-"
                else:
                    detail = "-"
            elif track.type == "subtitle":
                info = self._get_cached_stream_info(track.file_path)
                lang = ""
                if info:
                    streams = info.get('streams', [])
                    for s in streams:
                        if s.get('codec_type') == 'subtitle' and s.get('index') == track.index:
                            tags = s.get('tags', {})
                            lang = tags.get('language', '')
                            break
                detail = f"{lang}" if lang else "-"
            else:
                detail = "-"
    
            values = (
                i + 1,
                enabled_text,
                display_type,
                detail,
                track.codec[:10],
                os.path.basename(track.file_path) if track.file_path else "外部",
                enc_text
            )
            iid = f"track_{i}"
            self.merge_tree.insert("", tk.END, iid=iid, values=values, tags=(tag,))
    
        if not self.merge_tracks:
            self.merge_tree.insert("", tk.END, values=("", "未加载轨道", "", "", ""))

    def _get_selected_track_indices(self):
        """获取选中行的轨道索引列表（按实际列表顺序）"""
        selected = self.merge_tree.selection()
        indices = []
        for iid in selected:
            idx = int(iid.split('_')[1])
            if 0 <= idx < len(self.merge_tracks):
                indices.append(idx)
        return sorted(indices)
    
    def merge_toggle_selected(self):
        indices = self._get_selected_track_indices()
        if not indices:
            messagebox.showinfo("提示", "请先选中轨道")
            return
        # 如果所有选中的都启用，则全部禁用；否则全部启用
        all_enabled = all(self.merge_tracks[idx].enabled for idx in indices)
        new_state = not all_enabled
        for idx in indices:
            self.merge_tracks[idx].enabled = new_state
        self.merge_update_track_list()
        self.merge_update_command_preview()
    
    def merge_edit_selected(self):
        indices = self._get_selected_track_indices()
        if not indices:
            messagebox.showinfo("提示", "请先选中轨道")
            return
        # 只编辑第一个选中项
        self.merge_edit_track_settings(indices[0])
    
    def merge_preview_selected(self):
        indices = self._get_selected_track_indices()
        if not indices:
            messagebox.showinfo("提示", "请先选中轨道")
            return
        self.merge_preview_track(indices[0])
    
    def merge_move_up_selected(self):
        indices = self._get_selected_track_indices()
        if not indices:
            return
        self._move_selected_tracks(indices, direction=-1)
    
    def merge_move_down_selected(self):
        indices = self._get_selected_track_indices()
        if not indices:
            return
        self._move_selected_tracks(indices, direction=1)
    
    def _move_selected_tracks(self, indices, direction):
        """
        将选中的轨道整体上移（direction=-1）或下移（direction=1）。
        仅当选中轨道连续时支持整体移动，否则只移动第一个选中项。
        """
        if not indices:
            return
    
        # 排序
        indices = sorted(indices)
        min_idx = indices[0]
        max_idx = indices[-1]
    
        # 检查是否连续
        if max_idx - min_idx + 1 != len(indices):
            # 不连续：只移动第一个
            self._append_info_ui("[提示] 选中轨道不连续，仅移动第一个。请选择连续轨道以整体移动。")
            idx = indices[0]
            if direction == -1:
                if idx > 0:
                    self.merge_tracks[idx], self.merge_tracks[idx-1] = self.merge_tracks[idx-1], self.merge_tracks[idx]
            else:
                if idx < len(self.merge_tracks) - 1:
                    self.merge_tracks[idx], self.merge_tracks[idx+1] = self.merge_tracks[idx+1], self.merge_tracks[idx]
            new_selection = str(idx + direction)  # 移动后的索引
            self.merge_update_track_list()
            if 0 <= idx + direction < len(self.merge_tracks):
                self.merge_tree.selection_set(f"track_{idx + direction}")
            return
    
        # 连续：整体移动
        if direction == -1:
            if min_idx == 0:
                self._append_info_ui("[提示] 已在顶部，无法上移")
                return
            # 将选中的块整体上移一位
            block = self.merge_tracks[min_idx:max_idx+1]
            before = self.merge_tracks[min_idx-1]
            # 重新赋值：将 before 插入到块末尾，块整体前移
            self.merge_tracks[min_idx-1:max_idx+1] = block + [before]
            new_min = min_idx - 1
            new_max = max_idx - 1
        else:  # direction == 1
            if max_idx == len(self.merge_tracks) - 1:
                self._append_info_ui("[提示] 已在底部，无法下移")
                return
            block = self.merge_tracks[min_idx:max_idx+1]
            after = self.merge_tracks[max_idx+1]
            self.merge_tracks[min_idx:max_idx+2] = [after] + block
            new_min = min_idx + 1
            new_max = max_idx + 1
    
        # 刷新列表并恢复选中状态
        self.merge_update_track_list()
        for i in range(new_min, new_max + 1):
            self.merge_tree.selection_add(f"track_{i}")
        self.merge_update_command_preview()
        self._append_info_ui(f"[移动] 已整体{'上移' if direction == -1 else '下移'} {len(indices)} 个轨道")
    
    def merge_delete_selected(self):
        indices = self._get_selected_track_indices()
        if not indices:
            messagebox.showinfo("提示", "请先选中轨道")
            return
        # 从大到小删除
        for idx in reversed(indices):
            removed = self.merge_tracks.pop(idx)
            self._append_info_ui(f"[封装] 已删除轨道: {removed.type} - {os.path.basename(removed.file_path)}")
        self.merge_update_track_list()
        self.merge_update_command_preview()
    
    def merge_clear_tracks(self):
        if self.merge_tracks and messagebox.askyesno("确认", "确定清空所有轨道吗？"):
            self.merge_tracks.clear()
            self.merge_video.set("")
            self.merge_output.set("")
            self.merge_update_track_list()
            self.merge_auto_recommend_container()
            self.merge_update_command_preview()
            self.merge_reset_column_widths()    #调用恢复列宽
            self._append_info_ui("[封装] 已清空所有附加轨道")



    def merge_on_tree_double_click(self, event):
        """双击编辑第一个选中的轨道"""
        self.merge_edit_selected()

    def merge_reset_column_widths(self):
        """恢复合并页面 Treeview 各列的默认宽度"""
        # 原创建时的列宽设置
        self.merge_tree.column("序号", width=5)
        self.merge_tree.column("启用", width=5)
        self.merge_tree.column("类型", width=20)
        self.merge_tree.column("规格", width=100)
        self.merge_tree.column("编码", width=20)
        self.merge_tree.column("来源", width=495)
        self.merge_tree.column("编码设置 双击编辑", width=80)
        self._append_info_ui("[布局] 已恢复合并列表的列宽")



    def merge_move_track_up(self, idx):
        if idx <= 0:
            return
        self.merge_tracks[idx], self.merge_tracks[idx-1] = self.merge_tracks[idx-1], self.merge_tracks[idx]
        self.merge_update_track_list()
        self.merge_update_command_preview()

    def merge_move_track_down(self, idx):
        if idx >= len(self.merge_tracks)-1:
            return
        self.merge_tracks[idx], self.merge_tracks[idx+1] = self.merge_tracks[idx+1], self.merge_tracks[idx]
        self.merge_update_track_list()
        self.merge_update_command_preview()



    def merge_remove_track(self, track_idx):
        if 0 <= track_idx < len(self.merge_tracks):
            removed = self.merge_tracks.pop(track_idx)
            self._append_info_ui(f"[封装] 已删除轨道: {removed.type} - {os.path.basename(removed.file_path)}")
            self.merge_update_track_list()
            self.merge_auto_recommend_container()
            self.merge_update_command_preview()



    def evaluate_expression(self, expr, main_w, main_h, box_w, box_h):
        return safe_eval_expr(expr, {"W": main_w, "H": main_h, "w": box_w, "h": box_h})

    def get_rendered_size(self, track):
        w, h = get_video_rotated_dimensions(self.ffprobe_cmd, track.file_path, track.enc_settings)
        if w is None:
            return None
        return compute_rendered_size(w, h, track.enc_settings)

    def merge_preview_track(self, track_idx):
        """预览单个轨道，禁用倒放，变速仅 ffplay，自适应缩放（边距 自定义）"""
        track = self.merge_tracks[track_idx]
        if not os.path.exists(track.file_path):
            self._append_info_ui(f"[预览] 文件不存在: {track.file_path}")
            return
    
        if track.type == "video":
            reverse_enabled = track.enc_settings.get("reverse_enabled", False)
            if reverse_enabled:
                self._append_info_ui("[预览] 预览不支持倒放，已忽略 reverse。")
                temp_settings = track.enc_settings.copy()
                temp_settings['reverse_enabled'] = False
            else:
                temp_settings = track.enc_settings
    
            # ---- 视频滤镜（不含自适应缩放） ----
            enhance = temp_settings.get("enhance", {})
            filters = build_video_filter_chain(
                temp_settings,
                include_subtitle=False,
                include_speed=False,
                enhance_settings=enhance,
                reverse=False
            )
    
            # ---- 画中画模式：为主视频绘制子视频虚拟框 ----
            pip_enabled = self.pip_enabled.get()
            enabled_video_tracks = [t for t in self.merge_tracks if t.enabled and t.type == "video"]
            is_main_video = (enabled_video_tracks and enabled_video_tracks[0] == track)
            if pip_enabled and is_main_video:
                sub_videos = enabled_video_tracks[1:]
                if sub_videos:
                    main_w, main_h = self._get_video_render_size(track)
                    if main_w is None:
                        self._append_info_ui("[预览] 无法获取主视频尺寸，使用默认 1280x720")
                        main_w, main_h = 1280, 720
                    drawboxes = []
                    for sub in sub_videos:
                        if not sub.enc_settings.get('overlay_enabled', True):
                            continue
                        rendered = self.get_rendered_size(sub)
                        if rendered:
                            box_w, box_h = rendered
                        else:
                            box_w, box_h = 200, 150
                            self._append_info_ui(f"[预览] 无法获取从视频渲染尺寸，使用默认 {box_w}x{box_h}")
                        x_expr = sub.enc_settings.get('overlay_x', '0')
                        y_expr = sub.enc_settings.get('overlay_y', '0')
                        x_val = self.evaluate_expression(x_expr, main_w, main_h, box_w, box_h)
                        y_val = self.evaluate_expression(y_expr, main_w, main_h, box_w, box_h)
                        drawbox = f"drawbox=x={x_val}:y={y_val}:w={box_w}:h={box_h}:color=red@0.5:t=2"
                        drawboxes.append(drawbox)
                        self._append_info_ui(f"[预览] 从视频 {os.path.basename(sub.file_path)} 实际渲染尺寸: {box_w}x{box_h}, 位置: ({x_val}, {y_val})")
                    if drawboxes:
                        drawbox_chain = ",".join(drawboxes)
                        if filters and filters != "null":
                            filters = f"{filters},{drawbox_chain}"
                        else:
                            filters = drawbox_chain
    
            # ---- 自适应缩放（固定边距） ----
            orig_w, orig_h = get_video_rotated_dimensions(self.ffprobe_cmd, track.file_path, track.enc_settings)
            if orig_w is None or orig_h is None:
                orig_w, orig_h = 1280, 720
            final_w, final_h = compute_rendered_size(orig_w, orig_h, track.enc_settings)
    
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            margin = 80
            max_w = screen_w - margin
            max_h = screen_h - margin
    
            if final_w > max_w or final_h > max_h:
                scale = min(max_w / final_w, max_h / final_h)
                target_w = int(final_w * scale)
                target_h = int(final_h * scale)
                target_w = target_w if target_w % 2 == 0 else target_w - 1
                target_h = target_h if target_h % 2 == 0 else target_h - 1
                if target_w < 2: target_w = 2
                if target_h < 2: target_h = 2
                scale_filter = f"scale={target_w}:{target_h}"
                if filters and filters != "null":
                    filters = f"{filters},{scale_filter}"
                else:
                    filters = scale_filter
                self._append_info_ui(f"[预览] 缩放到 {target_w}x{target_h}")
            else:
                self._append_info_ui(f"[预览] 保持原始尺寸 {final_w}x{final_h}")
    
            # ---- 音频变速（仅 ffplay） ----
            extra_args = []
            af_filters = []
            if is_main_video and track.enc_settings.get("speed_enabled", False):
                try:
                    factor = float(track.enc_settings.get("speed_factor", "1.0"))
                    if factor != 1.0 and factor > 0:
                        atempo = build_atempo_chain(factor)
                        if atempo:
                            af_filters.append(atempo)
                except ValueError:
                    pass
            if af_filters:
                if self.use_mpv.get():
                    self._append_info_ui("[预览] mpv 预览不支持音频变速，已忽略。")
                else:
                    af_chain = ",".join(af_filters)
                    extra_args.extend(["-af", af_chain])
    
            # ---- 截取参数 ----
            start_sec = None
            duration = None
            if track.enc_settings.get("trim_enabled", False):
                start_str = track.enc_settings.get("trim_start", "").strip()
                end_str = track.enc_settings.get("trim_end", "").strip()
                start_sec = time_to_seconds(start_str) if start_str else None
                end_sec = time_to_seconds(end_str) if end_str else None
                if start_sec is not None and end_sec is not None and end_sec > start_sec:
                    duration = end_sec - start_sec
    
            # ---- 调用播放器 ----
            self.preview_with_player(track.file_path, filters or "", volume=10, extra_args=extra_args,
                                     start_time=start_sec, duration=duration)
            if pip_enabled and is_main_video and sub_videos:
                self._append_info_ui("[预览] 占位框尺寸为从视频实际渲染大小")
    
        elif track.type == "audio":
            self.preview_with_player(track.file_path, audio_only=True, volume=10)
        else:
            self._append_info_ui("[预览] 不支持预览字幕轨")

    def merge_edit_track_settings(self, track_idx):
        track = self.merge_tracks[track_idx]
        if track.type == "video":
            self.merge_edit_video_track(track_idx)
        elif track.type == "audio":
            self.merge_edit_audio_track(track_idx)
        else:
            self.merge_edit_subtitle_track(track_idx)


    def edit_video_settings(self, title, initial_settings, on_save, file_path=None,
                            is_watermark=False, track_idx=None, pip_enabled_var=None,
                            overlay_mode='sub', parent=None, show_loop_chroma=True,
                            track_obj=None, is_concat_mode=False, canvas_file=None,
                            main_video_size=None):
        if parent is None:
            parent = self.root
        with self.SafeToplevel(parent) as win:
            win.title(title)
            notebook = ttk.Notebook(win)
            notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            # ---- 页面1：编码器与质量 ----
            page_enc = ttk.Frame(notebook)
            notebook.add(page_enc, text="编码器与质量")
            enc_frame = VideoEncoderFrame(page_enc, app=self)
            enc_frame.pack(fill=tk.X, padx=5, pady=5)
            enc_frame.set_settings(initial_settings)

            # ---- 页面2：视频滤镜 ----
            page_filt = ttk.Frame(notebook)
            notebook.add(page_filt, text="视频滤镜")
            filt_frame = VideoFilterFrame(page_filt, app=self)
            if file_path:
                filt_frame.current_file = file_path
            # 设置轨道或覆盖设置
            if track_obj is not None:
                filt_frame.set_track(track_obj)
            else:
                # 如果传入的设置中包含 trim 相关键，则认为独立设置
                if "trim_enabled" in initial_settings or "trim_start" in initial_settings:
                    filt_frame.set_override_settings(initial_settings)


            filt_frame.pack(fill=tk.X, padx=5, pady=5)
            filt_frame.set_settings(initial_settings)

            if "enhance" in initial_settings:
                filt_frame.set_enhance_settings(initial_settings["enhance"])


            # ---- 页面3：截取片段 ----
            page_trim = ttk.Frame(notebook)
            notebook.add(page_trim, text="截取片段")
            trim_frame = TrimFrame(page_trim, show_combo_seek=False)
            trim_frame.pack(fill=tk.X, padx=5, pady=5)
            trim_frame.set_settings(initial_settings)

            # 水印或画中画模式下，强制启用精准截取
            if is_watermark or (pip_enabled_var is not None and pip_enabled_var.get()):
                trim_frame.precise_trim.set(True)
                trim_frame.precise_check.config(state='disabled')
                if not self._trim_precise_hint_shown:
                    self._append_info_ui("[设置] 水印/画中画模式下已自动启用精准截取。")
                    self._trim_precise_hint_shown = True
            else:
                trim_frame.precise_check.config(state='normal')
               # trim_frame.precise_trim.set(False)

            # 设置回调（此时 trim_frame 已存在）
            filt_frame.set_get_trim_settings_callback(lambda: trim_frame.get_settings())

            # ---- 页面4：循环/绿幕控制（仅在需要时显示） ----
            loop_chroma_frame = None  # 占位，确保变量始终存在
            if show_loop_chroma:
                page_loop = ttk.Frame(notebook)
                notebook.add(page_loop, text="循环/绿幕控制")
                loop_chroma_frame = LoopChromaFrame(page_loop)
                loop_chroma_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                loop_chroma_frame.set_settings(initial_settings)
                if file_path and os.path.exists(file_path):
                    raw_duration = self._get_media_duration(file_path)
                    effective_duration = self._get_effective_duration(initial_settings, raw_duration)
                    if hasattr(loop_chroma_frame, 'set_duration_info'):
                        loop_chroma_frame.set_duration_info(effective_duration)
                else:
                    if hasattr(loop_chroma_frame, 'set_duration_info'):
                        loop_chroma_frame.set_duration_info(None)

            def update_duration_on_trim_change(*args):
                if loop_chroma_frame is None:
                    return
                # 获取当前截取设置（直接从 trim_frame 读取）
                settings_snapshot = trim_frame.get_settings()
                if file_path and os.path.exists(file_path):
                    raw_duration = self._get_media_duration(file_path)
                    effective_duration = self._get_effective_duration(settings_snapshot, raw_duration)
                    if hasattr(loop_chroma_frame, 'set_duration_info'):
                        loop_chroma_frame.set_duration_info(effective_duration)
                else:
                    if hasattr(loop_chroma_frame, 'set_duration_info'):
                        loop_chroma_frame.set_duration_info(None)
            
            # 绑定 trace
            trim_frame.trim_enabled.trace_add('write', update_duration_on_trim_change)
            trim_frame.trim_start.trace_add('write', update_duration_on_trim_change)
            trim_frame.trim_end.trace_add('write', update_duration_on_trim_change)


            # ---- 页面5：叠加/偏移（仅在画中画或水印模式下显示） ----
            overlay_frame = None
            show_overlay = is_watermark or (pip_enabled_var is not None and pip_enabled_var.get())
            if show_overlay:
                page_overlay = ttk.Frame(notebook)
                notebook.add(page_overlay, text="叠加/偏移")

                if is_watermark:
                    # 水印模式，使用 visual_callback
                    def watermark_visual_callback():
                        main_file = canvas_file or self.input_file.get().strip()
                        if not main_file or not os.path.exists(main_file):
                            messagebox.showwarning("提示", "请先选择一个有效的输入文件作为画布")
                            return
                    
                        # 获取主视频尺寸（优先使用传入的 main_video_size）
                        if main_video_size is not None:
                            main_w, main_h = main_video_size
                        else:
                            # 从 filt_frame 读取主视频设置计算
                            main_settings = {
                                "crop_enabled": filt_frame.crop_enabled.get(),
                                "crop_width": filt_frame.crop_width.get(),
                                "crop_height": filt_frame.crop_height.get(),
                                "scale_enabled": filt_frame.scale_enabled.get(),
                                "scale_method": filt_frame.scale_method.get(),
                                "scale_width": filt_frame.scale_width.get(),
                                "scale_height": filt_frame.scale_height.get(),
                                "rotate": filt_frame.rotate.get()
                            }
                            orig_w, orig_h = get_video_dimensions(self.ffprobe_cmd, main_file)
                            if orig_w is None or orig_h is None:
                                orig_w, orig_h = 1280, 720
                            main_w, main_h = self.compute_final_size_with_order(orig_w, orig_h, main_settings)
                    
                        wm_file = initial_settings.get("file_path", "")
                        if not wm_file or not os.path.exists(wm_file):
                            messagebox.showwarning("提示", "水印文件未设置或不存在")
                            return
                    
                        # 从 filt_frame 获取当前水印的滤镜设置（因为用户可能已修改）
                        # 注意：filt_frame 是主视频的滤镜框架，但在水印编辑模式下，它被用于水印设置
                        wm_settings = {
                            "crop_enabled": filt_frame.crop_enabled.get(),
                            "crop_width": filt_frame.crop_width.get(),
                            "crop_height": filt_frame.crop_height.get(),
                            "scale_enabled": filt_frame.scale_enabled.get(),
                            "scale_method": filt_frame.scale_method.get(),
                            "scale_width": filt_frame.scale_width.get(),
                            "scale_height": filt_frame.scale_height.get(),
                            "rotate": filt_frame.rotate.get(),
                            "vflip": filt_frame.vflip.get(),
                            "hflip": filt_frame.hflip.get(),
                            # 其他增强滤镜不影响尺寸，不需要
                        }
                    
                        orig_w, orig_h = get_video_dimensions(self.ffprobe_cmd, wm_file)
                        if orig_w is None or orig_h is None:
                            orig_w, orig_h = 320, 240
                    
                        # 计算水印渲染尺寸（包含旋转）
                        wm_w, wm_h = self.compute_final_size_with_order(orig_w, orig_h, wm_settings)
                        if wm_w <= 0 or wm_h <= 0:
                            wm_w, wm_h = orig_w, orig_h
                    
                        # 打开编辑器
                        self.open_watermark_overlay_editor(
                            main_w, main_h,
                            wm_w, wm_h,
                            overlay_frame.overlay_x,
                            overlay_frame.overlay_y,
                            scale_enabled_var=filt_frame.scale_enabled,   # 用于回写缩放
                            scale_w_var=filt_frame.scale_width,
                            scale_h_var=filt_frame.scale_height,
                            watermark_dict=initial_settings,  # 用于回写水印设置
                            filt_frame=filt_frame,
                            parent=win
                        )
                    overlay_frame = OverlayPositionFrame(
                        page_overlay,
                        app=self,
                        mode='sub',
                        track_idx=None,
                        track_obj=None,
                        filt_frame=filt_frame,
                        visual_callback=watermark_visual_callback
                    )
                else:
                    # 画中画模式（或主视频偏移）
                    overlay_frame = OverlayPositionFrame(
                        page_overlay,
                        app=self,
                        mode=overlay_mode,
                        track_idx=track_idx,
                        track_obj=None,
                        filt_frame=filt_frame,
                        visual_callback=None
                    )
                overlay_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                overlay_frame.set_settings(initial_settings)

            # ---- 页面6：轨道元数据（仅视频轨道非水印） ----
            if track_obj is not None and not is_watermark:
                page_meta = ttk.Frame(notebook)
                notebook.add(page_meta, text="轨道元数据")
                meta_frame = ttk.Frame(page_meta, padding="10")
                meta_frame.pack(fill=tk.X, pady=5)
            
                # 语言选择（下拉框 + 自定义输入）
                ttk.Label(meta_frame, text="语言:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
                lang_var = tk.StringVar(value=track_obj.language)
                # 下拉框显示友好名称
                lang_combo = ttk.Combobox(meta_frame, textvariable=lang_var,
                                          values=[display for display, code in self.COMMON_LANGUAGES],
                                          state="normal", width=20)
                lang_combo.grid(row=0, column=1, padx=5, pady=5, sticky="w")
            
                # 自定义输入框（用于输入未列出的代码）
                ttk.Label(meta_frame, text="或手动输入:").grid(row=0, column=2, padx=5, pady=5)
                custom_lang_var = tk.StringVar(value=track_obj.language)  # 初始同步
                custom_lang_entry = ttk.Entry(meta_frame, textvariable=custom_lang_var, width=10)
                custom_lang_entry.grid(row=0, column=3, padx=5, pady=5, sticky="w")
            
                # 绑定事件：从下拉框选择时，自动填充自定义框（填入标准码）
                def on_lang_select(event):
                    selected = lang_var.get()
                    for display, code in self.COMMON_LANGUAGES:
                        if display == selected:
                            custom_lang_entry.delete(0, tk.END)
                            custom_lang_entry.insert(0, code)
                            break
                lang_combo.bind("<<ComboboxSelected>>", on_lang_select)
            
                # 轨道标题（不变）
                ttk.Label(meta_frame, text="轨道标题:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
                title_var = tk.StringVar(value=track_obj.title)
                title_entry = ttk.Entry(meta_frame, textvariable=title_var, width=30)
                title_entry.grid(row=1, column=1, columnspan=3, padx=5, pady=5, sticky="w")
            
                # 提示信息
                ttk.Label(meta_frame, text="从下拉框选择常用语言，或直接输入 ISO 639-2/B 代码（如 cmn、yue）",
                          foreground="gray").grid(row=2, column=0, columnspan=4, sticky="w", padx=5, pady=2)

            # ================== 页面7：音频绑定 ==================
            # 仅在串接模式下显示此页（水印无音频绑定需求）
            if is_concat_mode and not is_watermark and track_obj is not None and track_obj.type == "video":
                page_audio_binding = ttk.Frame(notebook)
                notebook.add(page_audio_binding, text="音频绑定")
    
                bind_frame = ttk.Frame(page_audio_binding, padding="10")
                bind_frame.pack(fill=tk.BOTH, expand=True)
    
                ttk.Label(bind_frame, text="音频源类型:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
                audio_source_type_var = tk.StringVar(value=initial_settings.get("audio_source_type", "self"))
                source_frame = ttk.Frame(bind_frame)
                source_frame.grid(row=0, column=1, sticky="w", padx=5)
    
                rb_self = ttk.Radiobutton(source_frame, text="使用视频自身音频", 
                                          variable=audio_source_type_var, value="self")
                rb_silence = ttk.Radiobutton(source_frame, text="生成静音流", 
                                             variable=audio_source_type_var, value="silence")
                # 外部音频暂时隐藏，可后续启用
                # rb_external = ttk.Radiobutton(source_frame, text="从外部文件导入", variable=audio_source_type_var, value="external")
                rb_self.pack(side=tk.LEFT, padx=5)
                rb_silence.pack(side=tk.LEFT, padx=5)
    
                ttk.Label(
                    bind_frame,
                    text="静音流时长自动匹配视频片段时长。\n"
                         "此功能用于解决串接时因视频缺少音频流导致的音画错位问题。\n"
                         "注意：此功能会强制重新编码视频（无法使用流复制）。\n"
                         "如需快速拼接且保留原始编码，可提前用命令生成静音音频文件，\n"
                         "例如：ffmpeg -f lavfi -i anullsrc=r=44100:cl=stereo -t 10 silence.wav\n"
                         "然后将该音频流 copy 无损封装到视频中，最后再使用 copy 模式进行串接。",
                    foreground="gray",
                    justify=tk.LEFT
                ).grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=10)
    
                # 预留外部文件控件（暂时隐藏）
                # external_frame = ttk.Frame(bind_frame)
                # external_frame.grid(row=2, column=0, columnspan=2, sticky="we", padx=5, pady=5)
                # external_frame.grid_remove()
    
            # ================== 新增结束 ==================



            # ---- 窗口居中 ----
            center_window(win, 700, 300)

            # ---- 保存按钮 ----
            def save():
                try:
                    new_settings = {}
                    new_settings.update(enc_frame.get_settings())
                    new_settings.update(filt_frame.get_settings())
                    new_settings.update(trim_frame.get_settings())
                    if loop_chroma_frame is not None:
                        new_settings.update(loop_chroma_frame.get_settings())
                    if overlay_frame is not None:
                        new_settings.update(overlay_frame.get_settings())
                    if is_watermark:
                        new_settings["enabled"] = True
                        new_settings["file_path"] = initial_settings.get("file_path", "")
                        new_settings["duration"] = initial_settings.get("duration", None)
                    else:
                        # 仅在串行模式下收集音频绑定设置
                        if is_concat_mode and track_obj is not None and track_obj.type == "video":
                            new_settings["audio_source_type"] = audio_source_type_var.get()
                            # 以下两项暂不支持，留作未来扩展
                            # new_settings["external_audio_path"] = ""
                            # new_settings["external_audio_stream"] = "0:a:0"

                    new_settings["enhance"] = filt_frame.get_enhance_settings()

                    if track_obj is not None and not is_watermark:
                        # 优先使用自定义输入框，否则使用下拉框值
                        raw_lang = custom_lang_var.get().strip() or lang_var.get().strip()
                        # 尝试映射为标准码
                        if raw_lang:
                            # 如果下拉框选了显示名，但自定义框为空，这里 raw_lang 可能是显示名，需要映射
                            # 我们只对纯代码进行映射，显示名通过下拉框关联
                            # 但为了安全，先尝试从 COMMON_LANGUAGES 反向查找
                            found_code = None
                            for display, code in self.COMMON_LANGUAGES:
                                if display == raw_lang:
                                    found_code = code
                                    break
                            if found_code:
                                new_settings["language"] = found_code
                            else:
                                # 否则视为代码，应用映射表
                                new_settings["language"] = self.LANGUAGE_MAP.get(raw_lang.lower(), raw_lang)
                        else:
                            new_settings["language"] = ""
                        new_settings["title"] = title_var.get().strip()

                    on_save(new_settings)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    messagebox.showerror("保存错误", f"发生错误：{e}\n请查看控制台详细错误。")
                finally:
                    try:
                        win.destroy()
                    except:
                        pass

            ttk.Button(win, text="保存", command=save).pack(pady=10)
            win.wait_window()




    def merge_edit_video_track(self, track_idx):
        track = self.merge_tracks[track_idx]
        enabled_videos = [t for t in self.merge_tracks if t.enabled and t.type == "video"]
        is_main = (enabled_videos and enabled_videos[0] == track)
        overlay_mode = 'main' if is_main else 'sub'
        # 主视频不显示循环/绿幕
        show_loop = not is_main

        initial_settings = track.enc_settings.copy()
        if "enhance" not in initial_settings:
            initial_settings["enhance"] = {
                "denoise_enabled": False,
                "denoise_spatial": 4.0,
                "denoise_temporal": 3.0,
                "sharpen_enabled": False,
                "sharpen_strength": 1.0,
                "ivtc_enabled": False,
                "deblock_enabled": False,
                "deblock_strength": 4,
                "colorspace_enabled": False,
                "colorspace_matrix": "bt709:bt2020",
            }

        self.edit_video_settings(
            title=f"视频轨道设置 - {track.codec}",
            initial_settings=initial_settings,
            on_save=lambda new: self._update_track_enc(track_idx, new),
            file_path=track.file_path,
            is_watermark=False,
            track_idx=track_idx,
            pip_enabled_var=self.pip_enabled,
            overlay_mode=overlay_mode,
            parent=self.root,
            show_loop_chroma=show_loop,
            track_obj=track,   # 传递轨道对象
            is_concat_mode=self.concat_enabled.get()
        )
    
    
    def _update_track_enc(self, idx, new_settings):
        track = self.merge_tracks[idx]  # 先获取 track 对象
        old_encoder = track.enc_settings.get("encoder")
        new_encoder = new_settings.get("encoder")
        track.enc_settings = new_settings
        # 更新字幕元数据
        track.language = new_settings.get("language", "")
        track.title = new_settings.get("title", "")

        # 画中画模式下，视频倒放时提示音频倒放为独立的
        if self.pip_enabled.get() and new_settings.get("reverse_enabled", False) and not self._pip_reverse_audio_hint_shown:
            self._pip_reverse_audio_hint_shown = True
            messagebox.showinfo(
                "音频倒放独立控制",
                "您已为当前视频轨道启用倒放。\n\n"
                "在画中画模式下，视频倒放与音频倒放是独立的。\n"
                "若需要此视频的音频也倒放，请单独编辑对应的音频轨道，\n"
                "在音频设置中勾选「音频倒放（独立于视频）」。"
            )
            self._append_info_ui("[提示] 画中画模式下音频倒放独立，请至音频轨道单独设置。")

        if "enhance" in new_settings:
            track.enc_settings["enhance"] = new_settings["enhance"]
        # 同步属性（兼容旧代码）

        track.overlay_enabled = new_settings.get("overlay_enabled", False)
        track.overlay_x = new_settings.get("overlay_x", "W-w-10")
        track.overlay_y = new_settings.get("overlay_y", "H-h-10")
        track.pad_enabled = new_settings.get("pad_enabled", False)
        track.pad_width = new_settings.get("pad_width", "")
        track.pad_height = new_settings.get("pad_height", "")
        track.offset_x = new_settings.get("offset_x", "0")
        track.offset_y = new_settings.get("offset_y", "0")

        # 检测是否切换为 copy（仅在视频轨道且编码器变化时）
        if track.type == "video" and old_encoder != new_encoder:
            if new_encoder == "copy":
                self._append_info_ui("[封装] 该视频轨道编码器已设为 copy，视频滤镜将被忽略。")

        self.merge_update_track_list()
        self.merge_update_command_preview()


    def merge_edit_audio_track(self, track_idx):
        track = self.merge_tracks[track_idx]
        with self.SafeToplevel(self.root) as win:
            win.title(f"音频轨道设置 - {track.codec}")
            center_window(win, 500, 600)
            win.transient(self.root)
    
            main_frame = ttk.Frame(win, padding="10")
            main_frame.pack(fill=tk.BOTH, expand=True)
    
            # ---- 编码参数（水平布局） ----
            enc_frame = ttk.LabelFrame(main_frame, text="编码参数", padding="5")
            enc_frame.pack(fill=tk.X, pady=5)
    
            row = ttk.Frame(enc_frame)
            row.pack(fill=tk.X, pady=2)
    
            ttk.Label(row, text="编码器:").pack(side=tk.LEFT, padx=5)
            encoder_var = tk.StringVar(value=track.enc_settings.get("encoder", "copy"))
            encoder_combo = ttk.Combobox(row, textvariable=encoder_var, values=ALL_AUDIO_ENCODERS, state="readonly", width=12)
            encoder_combo.pack(side=tk.LEFT, padx=5)
    
            ttk.Label(row, text="比特率:").pack(side=tk.LEFT, padx=5)
            bitrate_var = tk.StringVar(value=track.enc_settings.get("bitrate", "128k"))
            bitrate_entry = ttk.Entry(row, textvariable=bitrate_var, width=8)
            bitrate_entry.pack(side=tk.LEFT, padx=5)
    
            ttk.Label(row, text="采样率:").pack(side=tk.LEFT, padx=5)
            samplerate_var = tk.StringVar(value=track.enc_settings.get("samplerate", "44100"))
            samplerate_entry = ttk.Entry(row, textvariable=samplerate_var, width=8)
            samplerate_entry.pack(side=tk.LEFT, padx=5)
    
            # ---- 轨道元数据（语言下拉+自定义输入，标题） ----
            meta_frame = ttk.LabelFrame(main_frame, text="轨道元数据", padding="5")
            meta_frame.pack(fill=tk.X, pady=5)
    
            # 语言部分：下拉框 + 手动输入框
            lang_row = ttk.Frame(meta_frame)
            lang_row.pack(fill=tk.X, pady=2)
    
            ttk.Label(lang_row, text="语言:").pack(side=tk.LEFT, padx=5)
            
            lang_display_var = tk.StringVar()
            # 显示名列表
            lang_display_list = [display for display, code in self.COMMON_LANGUAGES]
            lang_combo = ttk.Combobox(lang_row, textvariable=lang_display_var,
                                      values=lang_display_list,
                                      state="normal", width=18)
            lang_combo.pack(side=tk.LEFT, padx=5)
    
            # 手动输入框（用于输入未列出的代码，如 "cmn"）
            ttk.Label(lang_row, text="或输入代码:").pack(side=tk.LEFT, padx=(10,2))
            custom_lang_entry = ttk.Entry(lang_row, width=10)
            custom_lang_entry.pack(side=tk.LEFT, padx=2)
            
            # 从现有语言值初始化（track.language 可能是标准码）
            current_lang = track.language or ""
            if current_lang:
                # 查找是否在映射表中
                found_display = None
                for display, code in self.COMMON_LANGUAGES:
                    if code == current_lang:
                        found_display = display
                        break
                if found_display:
                    lang_display_var.set(found_display)
                    custom_lang_entry.delete(0, tk.END)
                    custom_lang_entry.insert(0, current_lang)
                else:
                    # 未找到，直接填入手动输入框
                    custom_lang_entry.insert(0, current_lang)
                    # 尝试在下拉框中匹配显示名（可能为"未指定 (und)"等）
                    for display, code in self.COMMON_LANGUAGES:
                        if code == "und":
                            lang_display_var.set(display)
                            break
    
            # 绑定下拉选择事件：自动填充自定义框
            def on_lang_select(event):
                selected = lang_display_var.get()
                for display, code in self.COMMON_LANGUAGES:
                    if display == selected:
                        custom_lang_entry.delete(0, tk.END)
                        custom_lang_entry.insert(0, code)
                        break
            lang_combo.bind("<<ComboboxSelected>>", on_lang_select)
    
            # 标题
            title_row = ttk.Frame(meta_frame)
            title_row.pack(fill=tk.X, pady=2)
            ttk.Label(title_row, text="标题:").pack(side=tk.LEFT, padx=5)
            title_var = tk.StringVar(value=track.title)
            title_entry = ttk.Entry(title_row, textvariable=title_var, width=40)
            title_entry.pack(side=tk.LEFT, padx=5)
    
            # 获取模式标志
            is_pip = self.pip_enabled.get()
            is_concat = self.concat_enabled.get()
    
            # ---- 音量控制（仅普通和画中画模式） ----
            if not is_concat:
                volume_frame = ttk.LabelFrame(main_frame, text="音量调整", padding="5")
                volume_frame.pack(fill=tk.X, pady=5)
    
                vol_enabled_var = tk.BooleanVar(value=track.enc_settings.get("volume_enabled", False))
                vol_value_var = tk.DoubleVar(value=track.enc_settings.get("volume", 1.0))
    
                vol_check = ttk.Checkbutton(volume_frame, text="启用音量调整", variable=vol_enabled_var)
                vol_check.pack(anchor=tk.W, pady=(0,5))
    
                vol_control_frame = ttk.Frame(volume_frame)
                vol_control_frame.pack(fill=tk.X)
    
                ttk.Label(vol_control_frame, text="倍数:").pack(side=tk.LEFT)
                vol_slider = ttk.Scale(vol_control_frame, from_=0.1, to=3.0, variable=vol_value_var,
                                       orient=tk.HORIZONTAL, length=150, state=tk.DISABLED)
                vol_slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
                vol_label = ttk.Label(vol_control_frame, text="1.0", width=5)
                vol_label.pack(side=tk.LEFT)
                vol_slider.configure(command=lambda v: vol_label.config(text=f"{float(v):.2f}"))
    
                def on_vol_enabled(*args):
                    state = tk.NORMAL if vol_enabled_var.get() else tk.DISABLED
                    vol_slider.config(state=state)
                vol_enabled_var.trace_add("write", on_vol_enabled)
                on_vol_enabled()
            else:
                vol_enabled_var = tk.BooleanVar(value=False)
                vol_value_var = tk.DoubleVar(value=1.0)
    
            # ---- 音频混合（仅普通封装模式可用） ----
            if not is_pip and not is_concat:
                mix_frame = ttk.LabelFrame(main_frame, text="音频混合 (amix)", padding="5")
                mix_frame.pack(fill=tk.X, pady=5)
                mix_enabled_var = tk.BooleanVar(value=track.enc_settings.get("mix_enabled", False))
                mix_cb = ttk.Checkbutton(mix_frame, text="参与混合 (启用后，该流将与其它勾选流合并为单音轨)",
                                         variable=mix_enabled_var)
                mix_cb.grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=2)
                ToolTip(mix_cb,
                        "勾选后，该音频流将参与混合。\n"
                        "如果至少一个轨道勾选，则所有勾选的流会通过 amix 滤镜合并为单音轨输出。\n"
                        "未勾选的流将被丢弃（不输出）。\n"
                        "若只有一个轨道勾选，则无需混合，直接输出该流。",
                        wraplength=500)
            else:
                mix_enabled_var = tk.BooleanVar(value=False)
    
            # ---- 音频倒放（独立于视频，普通和画中画模式可用） ----
            if not is_concat:
                reverse_frame = ttk.Frame(main_frame)
                reverse_frame.pack(fill=tk.X, pady=5)
                audio_reverse_var = tk.BooleanVar(value=track.enc_settings.get("audio_reverse", False))
                chk_reverse = ttk.Checkbutton(
                    reverse_frame,
                    text="音频倒放（独立于视频，仅当前轨道）",
                    variable=audio_reverse_var
                )
                chk_reverse.pack(anchor=tk.W, padx=5)
                ToolTip(chk_reverse, "勾选后，此音频流将单独倒放，不影响其他轨道。")
            else:
                audio_reverse_var = tk.BooleanVar(value=False)
    
            # ---- 截取设置 ----
            trim_frame = ttk.LabelFrame(main_frame, text="音频截取（精确到毫秒）", padding="5")
            trim_frame.pack(fill=tk.X, pady=5)
    
            trim_enabled_var = tk.BooleanVar(value=track.enc_settings.get("trim_enabled", False))
            chk = ttk.Checkbutton(trim_frame, text="启用截取", variable=trim_enabled_var)
            chk.grid(row=0, column=0, columnspan=3, sticky="w", padx=5, pady=5)
            ToolTip(chk,
                    "注意：若截取时长短于主视频，输出将以音频为准提前结束，导致主视频内容丢失。\n"
                    "建议截取时长 ≥ 主视频时长，或保持不截取。",
                    wraplength=500)
            ttk.Label(trim_frame, text="开始时间 (HH:MM:SS[.mmm]):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
            trim_start_var = tk.StringVar(value=track.enc_settings.get("trim_start", "0"))
            ttk.Entry(trim_frame, textvariable=trim_start_var, width=15).grid(row=1, column=1, sticky="w", padx=5, pady=5)
    
            ttk.Label(trim_frame, text="结束时间 (HH:MM:SS[.mmm]):").grid(row=2, column=0, sticky="w", padx=5, pady=5)
            trim_end_var = tk.StringVar(value=track.enc_settings.get("trim_end", ""))
            ttk.Entry(trim_frame, textvariable=trim_end_var, width=15).grid(row=2, column=1, sticky="w", padx=5, pady=5)
            ttk.Label(trim_frame, text="结束时间 (留空到末尾)").grid(row=2, column=2, sticky="w", padx=5, pady=5)
    
            precise_trim_var = tk.BooleanVar(value=track.enc_settings.get("precise_trim", False))
            ttk.Checkbutton(trim_frame, text="精准模式（精确到帧）", variable=precise_trim_var).grid(row=3, column=0, columnspan=3, sticky="w", padx=5, pady=5)
    
            ttk.Label(trim_frame, text="注意：启用截取后，编码器将自动改为非 copy 格式（如 aac）", foreground="gray").grid(row=4, column=0, columnspan=3, sticky="w", padx=5, pady=5)
    
            # ---- 保存按钮 ----
            def save():
                enc = encoder_var.get()
                # 如果截取启用且编码器为 copy，强制改 aac
                if trim_enabled_var.get() and enc == "copy":
                    enc = "aac"
                    self._append_info_ui("音频截取启用，编码器已从 copy 改为 aac")
                # 混合启用时同样强制改 aac（普通模式）
                if not is_pip and not is_concat and mix_enabled_var.get() and enc == "copy":
                    enc = "aac"
                    self._append_info_ui("音频混合启用，编码器已从 copy 改为 aac")
    
                track.enc_settings.update({
                    "encoder": enc,
                    "bitrate": bitrate_var.get(),
                    "samplerate": samplerate_var.get(),
                    "trim_enabled": trim_enabled_var.get(),
                    "trim_start": trim_start_var.get().strip(),
                    "trim_end": trim_end_var.get().strip(),
                    "precise_trim": precise_trim_var.get(),
                    "mix_enabled": mix_enabled_var.get(),
                    "volume": vol_value_var.get(),
                    "volume_enabled": vol_enabled_var.get(),
                })
                if not is_concat:
                    track.enc_settings["audio_reverse"] = audio_reverse_var.get()
                else:
                    track.enc_settings.pop("audio_reverse", None)
                if is_concat:
                    # 串联模式强制禁用音量
                    track.enc_settings["volume_enabled"] = False
                    track.enc_settings["volume"] = 1.0
                else:
                    track.enc_settings["volume_enabled"] = vol_enabled_var.get()
                    track.enc_settings["volume"] = vol_value_var.get()


                # 获取语言：优先手动输入，其次下拉框
                lang_code = custom_lang_entry.get().strip()
                if not lang_code:
                    # 从下拉框获取显示名，转为代码
                    display = lang_display_var.get().strip()
                    if display:
                        for d, code in self.COMMON_LANGUAGES:
                            if d == display:
                                lang_code = code
                                break
                    else:
                        lang_code = ""
                # 映射标准化
                if lang_code:
                    lang_code = self.LANGUAGE_MAP.get(lang_code.lower(), lang_code)
                else:
                    lang_code = ""

                track.language = lang_code
                track.title = title_var.get().strip()
                track.enc_settings["language"] = track.language
                track.enc_settings["title"] = track.title
    
                self.merge_update_track_list()
                self.merge_update_command_preview()
                win.destroy()
    
            ttk.Button(main_frame, text="保存", command=save).pack(pady=10)
            win.wait_window()

    def merge_edit_subtitle_track(self, track_idx):
        track = self.merge_tracks[track_idx]
        with self.SafeToplevel(self.root) as win:
            win.title(f"字幕轨道设置 - {track.codec}")
            center_window(win, 450, 270)
            win.transient(self.root)
            
            ttk.Label(win, text="编码器:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
            encoder_var = tk.StringVar(value=track.enc_settings.get("encoder", "copy"))
            combo = ttk.Combobox(win, textvariable=encoder_var, values=["copy", "mov_text", "srt"], state="readonly")
            combo.grid(row=0, column=1, padx=5, pady=5, sticky="w")
            ToolTip(win.grid_slaves(row=0, column=0)[0], 
                    "对于 ASS/SSA 字幕，推荐使用 MKV 容器并选择「copy」流，\n"
                    "MP4 容器支持不佳（会丢失样式），MP4 必须用 mov_text",
                    wraplength=500)
            
            # ---- 语言：下拉+自定义 ----
            ttk.Label(win, text="语言:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
            lang_frame = ttk.Frame(win)
            lang_frame.grid(row=1, column=1, sticky="w", padx=5)
            
            lang_display_var = tk.StringVar()
            lang_combo = ttk.Combobox(lang_frame, textvariable=lang_display_var,
                                      values=[display for display, code in self.COMMON_LANGUAGES],
                                      state="normal", width=18)
            lang_combo.pack(side=tk.LEFT)
            
            ttk.Label(lang_frame, text="或输入代码:").pack(side=tk.LEFT, padx=(10,2))
            custom_lang_entry = ttk.Entry(lang_frame, width=10)
            custom_lang_entry.pack(side=tk.LEFT)
            
            current_lang = track.language or ""
            if current_lang:
                found_display = None
                for display, code in self.COMMON_LANGUAGES:
                    if code == current_lang:
                        found_display = display
                        break
                if found_display:
                    lang_display_var.set(found_display)
                    custom_lang_entry.delete(0, tk.END)
                    custom_lang_entry.insert(0, current_lang)
                else:
                    custom_lang_entry.insert(0, current_lang)
                    for display, code in self.COMMON_LANGUAGES:
                        if code == "und":
                            lang_display_var.set(display)
                            break
            
            def on_lang_select(event):
                selected = lang_display_var.get()
                for display, code in self.COMMON_LANGUAGES:
                    if display == selected:
                        custom_lang_entry.delete(0, tk.END)
                        custom_lang_entry.insert(0, code)
                        break
            lang_combo.bind("<<ComboboxSelected>>", on_lang_select)
            
            # 标题
            ttk.Label(win, text="轨道标题:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
            title_var = tk.StringVar(value=track.title)
            title_entry = ttk.Entry(win, textvariable=title_var, width=30)
            title_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")
            
            def save():
                lang_code = custom_lang_entry.get().strip()
                if not lang_code:
                    display = lang_display_var.get().strip()
                    if display:
                        for d, code in self.COMMON_LANGUAGES:
                            if d == display:
                                lang_code = code
                                break
                    else:
                        lang_code = ""
                if lang_code:
                    lang_code = self.LANGUAGE_MAP.get(lang_code.lower(), lang_code)
                else:
                    lang_code = ""
                    
                track.enc_settings["encoder"] = encoder_var.get()
                track.language = lang_code
                track.title = title_var.get().strip()
                track.enc_settings["language"] = track.language
                track.enc_settings["title"] = track.title
                self.merge_update_track_list()
                self.merge_update_command_preview()
                win.destroy()
            
            ttk.Button(win, text="保存", command=save).grid(row=3, column=0, columnspan=2, pady=10)
            win.wait_window()

    def merge_set_track_enabled(self, idx, enabled):
        self.merge_tracks[idx].enabled = enabled
        self.merge_auto_recommend_container()
        self.merge_update_command_preview()

    def merge_auto_recommend_container(self):
        main_video = self.merge_video.get()
        if not main_video:
            return
        original_ext = os.path.splitext(main_video)[1].lower().lstrip('.')
        if original_ext not in ['mp4', 'mkv', 'mov', 'avi', 'webm']:
            original_ext = 'mp4'
        current_enabled = [t for t in self.merge_tracks if t.enabled]
        need_encode = any(t.is_encoding() for t in current_enabled)
        has_external = any(t.file_path != main_video for t in current_enabled)
        rec = "mkv" if (need_encode or has_external) else original_ext
        if self.merge_container.get() != rec:
            self.merge_container.set(rec)
            self._append_info_ui(f"[封装] 自动推荐容器: {rec.upper()}")
   #         self.merge_update_output_preview()

    def merge_add_external(self, ftype, path=None):
        # 1. 如果未传入有效路径，弹出文件选择对话框
        if not path:  # 处理 None 或空字符串
            if ftype == "audio":
                types = [("音频", "*.mp3 *.aac *.m4a *.wav *.flac *.ogg *.opus *.ac3 *.dts *.mka")]
            else:
                types = [("字幕", "*.srt *.ass *.ssa *.vtt *.idx *.sup")]
            path = filedialog.askopenfilename(filetypes=types)
            if not path:  # 用户取消
                return
    
        # 2. 现在 path 肯定是一个非空字符串，可以安全地检查是否为目录
        if os.path.isdir(path):
            self._append_info_ui(f"[封装] 忽略文件夹: {os.path.basename(path)}，请选择文件")
            return
    
        # 3. 检查主视频是否已设置
        if not self.merge_video.get():
            self._append_info_ui("[封装] 请先设置主视频")
            return

        info = self._get_cached_stream_info(path)
        if not info:
            self._append_info_ui(f"[封装] 无法解析: {path}")
            return
        expected = "audio" if ftype=="audio" else "subtitle"
        def do_add():
            added = 0
            for s in info["streams"]:
                if s.get("codec_type") != expected:
                    continue
                exists = any(t.file_path == path and t.index == s["index"] for t in self.merge_tracks)
                if exists:
                    self._append_info_ui(f"[封装] 跳过重复轨道: {os.path.basename(path)} 流 #{s['index']} ({expected})")
                    continue
                track = Track(s["index"], expected, s.get("codec_name","unknown"), path, True)
                self.merge_tracks.append(track)
                added += 1
            if added:
                self._append_info_ui(f"[封装] 已添加 {added} 条{expected}轨道: {os.path.basename(path)}")
            else:
                self._append_info_ui(f"[封装] 未添加新轨道: {os.path.basename(path)}")
            self.merge_update_track_list()
            self.merge_auto_recommend_container()
            self.merge_update_command_preview()
        self.root.after(0, do_add)

    def merge_update_output_preview(self):
        video = self.merge_video.get().strip()
        if not video:
            self.merge_output.set("")
            return
        dirname = os.path.dirname(video)
        basename = os.path.splitext(os.path.basename(video))[0]
        ext = "." + self.merge_container.get()
        output_path = normalize_path(os.path.join(dirname, f"{basename}_merged{ext}"))
        self.merge_output.set(output_path)
        self.merge_update_command_preview()

    def merge_select_video(self):
        path = filedialog.askopenfilename(title="选择视频", filetypes=[("媒体","*.mp4 *.mkv *.avi *.mov *.flv *.ts *.webm")])
        if path:
            self.merge_video.set(normalize_path(path))

    def merge_select_output(self):
        path = filedialog.asksaveasfilename(defaultextension="."+self.merge_container.get())
        if path:
            self.merge_output.set(normalize_path(path))
            self.merge_update_command_preview()

    def merge_start(self):
        if any(t.enc_settings.get("_placeholder", False) for t in self.merge_tracks if t.enabled):
            messagebox.showwarning("提示", "仍有文件正在解析，请稍候再开始合并。")
            return
        if not self.merge_video.get() or not self.merge_output.get():
            messagebox.showerror("错误", "请选择主视频和输出路径")
            return
        if not [t for t in self.merge_tracks if t.enabled]:
            messagebox.showerror("错误", "没有启用的轨道")
            return
        if not self._check_pip_video_encoders():
            return
    
        output = self.merge_output.get().strip()
        final_output = self._resolve_path_conflict(output, show_dialog=True)
        self.merge_update_command_preview(output_override=final_output)  # 这个调用可能仍是预览模式，可保留或删除
    
        # 生成实际执行的命令（preview=False）
        cmd_list = self.merge_build_cmd_list(output_override=final_output, preview=False)
        if not cmd_list:
            self._append_info_ui("[封装] 无法生成命令，请检查设置")
            return
    
        self.merge_btn.config(state="disabled")
        threading.Thread(target=self.merge_do_merge, args=(cmd_list, final_output), daemon=True).start()  
    
    
    def merge_do_merge(self, cmd_list, final_output):
        """
        执行合并/转码命令，并实时显示进度。
        """
        if not cmd_list:
            self._append_info_ui("[封装] 命令列表为空，无法执行")
            self.root.after(0, lambda: self.merge_btn.config(state="normal"))
            return
    
        self._append_info_ui("[封装] 开始合并/转码...")
        output_file = final_output
        source_files = set()
        source_files.add(self.merge_video.get().strip())
        for t in self.merge_tracks:
            if t.enabled and t.file_path not in source_files:
                source_files.add(t.file_path)
    
        # 获取主视频总时长用于进度
        main_video = self.merge_video.get().strip()
        total_duration = self._get_media_duration(main_video) if main_video else 0
        if total_duration is None:
            total_duration = 0
    
        proc = None
        try:
            proc = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=0x08000000 if sys.platform == "win32" else 0
            )
            with self._proc_lock:
                self.running_procs.append(proc)
    
            for line in proc.stdout:
                self.safe_append_detail(line)
                # 解析进度
                if total_duration > 0 and "time=" in line:
                    match = re.search(r'time=(\d+):(\d+):(\d+\.?\d*)', line)
                    if match:
                        h, m, s = match.groups()
                        current_sec = int(h) * 3600 + int(m) * 60 + float(s)
                        self.update_progress(current=int(current_sec), total=int(total_duration), task=None, log_progress=True)
    
            ret = proc.wait()
            if ret == 0:
                self._append_info_ui("[封装] ✅ 处理完成")
                cmd_str = format_cmd_for_display(cmd_list)
                self._log_command_to_file(cmd_str)
                if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                    if self.merge_delete_source.get():
                        self.root.after(0, lambda: self._confirm_delete_sources(source_files, output_file))
                    else:
                        self._append_info_ui("[封装] 未勾选删除源文件，保留原文件")
                else:
                    self._append_info_ui(f"[封装] 警告：输出文件 {output_file} 可能无效（不存在或大小为0），源文件未被删除")
            else:
                self._append_info_ui(f"[封装] 处理失败，返回码 {ret}，源文件未被删除")
        except Exception as e:
            self._append_info_ui(f"[封装] 异常: {e}")
        finally:
            with self._proc_lock:
                if proc in self.running_procs:
                    self.running_procs.remove(proc)
            # 重置进度（转码结束或失败）
            self.update_progress(current=0, total=0, task=None, log_progress=True)
            self.root.after(0, lambda: self.merge_btn.config(state="normal"))

    def _confirm_delete_sources(self, source_files, output_file):
        if not messagebox.askyesno("确认删除", f"是否确定删除 {len(source_files)} 个源文件？\n此操作不可恢复！"):
            self._append_info_ui("[封装] 取消删除源文件")
            return
        deleted_count = 0
        for sf in source_files:
            abs_sf = os.path.abspath(sf)
            safe_prefixes = (os.path.abspath('.'), os.path.dirname(os.path.abspath(output_file)))
            if not any(abs_sf.startswith(p) for p in safe_prefixes):
                self._append_info_ui(f"跳过删除 {sf}：不在安全目录内")
                continue
            try:
                os.remove(abs_sf)
                self._append_info_ui(f"[封装] 已删除源文件: {os.path.basename(sf)}")
                deleted_count += 1
            except Exception as e:
                self._append_info_ui(f"[封装] 删除失败 {os.path.basename(sf)}: {e}")
        if deleted_count > 0:
            self._append_info_ui(f"[封装] 共删除 {deleted_count} 个源文件")

    def _check_pip_video_encoders(self):
        """检查画中画模式下各视频轨道的编码器设置，仅给出必要警告，不阻止执行。"""
        if not self.pip_enabled.get():
            return True
    
        enabled_videos = [t for t in self.merge_tracks if t.enabled and t.type == "video"]
        if not enabled_videos:
            return True
    
        # 查找主视频（第一个视频轨道）
        main_video = enabled_videos[0]
        main_encoder = main_video.enc_settings.get("encoder", "copy")
    
        # 检查从视频是否设为 copy
        copy_tracks = [t for t in enabled_videos[1:] if t.enc_settings.get("encoder") == "copy"]
        if copy_tracks:
            # 构建警告信息（润色版）
            warning_lines = [
                "画中画模式下，所有视频流必须通过滤镜重新编码，「copy」设置将被忽略。",
                f"输出视频的编码格式将由主视频的编码器「{main_encoder}」统一决定。",
                "您无需手动修改从视频的编码器设置，系统会自动处理。",
                "以下从视频轨道的「copy」设置已忽略："
            ]
            for t in copy_tracks:
                warning_lines.append(f"  - {os.path.basename(t.file_path)}")
            self._append_info_ui("\n".join(warning_lines))
    
        # 无论如何都返回 True，不中断合并操作
        return True

    # -------------------- 拖放处理 --------------------
    def on_files_dropped(self, event):
        """根窗口拖放：仅处理添加到队列（输入/输出框由独立回调处理）"""
        files = self.root.tk.splitlist(event.data)
        self._append_info_ui(f"拖拽了 {len(files)} 个文件/文件夹")
        current_tab = self.notebook.index(self.notebook.select())
    
        if current_tab == 0:
            # 转码标签页：添加到任务队列
            # 定义视频扩展名列表
            video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.ts', '.webm', '.m2ts', '.mpg', '.mpeg', '.wmv', '.3gp')
            for item in files:
                if os.path.isfile(item):
                    # 如果是视频文件，直接添加
                    if os.path.splitext(item)[1].lower() in video_exts:
                        self.add_task(item)
                    else:
                        self._append_info_ui(f"忽略非视频文件: {os.path.basename(item)}")
                elif os.path.isdir(item):
                    # 如果是目录，递归扫描所有视频文件
                    self._append_info_ui(f"扫描目录: {item}")
                    for root_dir, _, filenames in os.walk(item):
                        for filename in filenames:
                            file_path = os.path.join(root_dir, filename)
                            if os.path.splitext(file_path)[1].lower() in video_exts:
                                self.add_task(file_path)
                    self._append_info_ui(f"目录扫描完成: {item}")
                else:
                    self._append_info_ui(f"忽略无效路径: {item}")
        else:
            # 封装/合并标签页的处理保持不变
            if self.pip_enabled.get():
                self._handle_drop_pip_mode(files)
            elif self.concat_enabled.get():
                self._handle_drop_concat_mode(files)
            else:
                if len(files) >= 2:
                    self.merge_handle_batch_dropped(files)
                else:
                    for file in files:
                        if os.path.exists(file):
                            self.merge_handle_dropped_file(file)

    def on_input_drop(self, event):
        """拖放到输入文件框：设置输入文件，并自动设置输出目录"""
        files = self.root.tk.splitlist(event.data)
        if not files:
            return
        first_file = files[0]
        if os.path.exists(first_file):
            self.input_file.set(normalize_path(first_file))
            if not self.output_dir.get():
                self.output_dir.set(os.path.dirname(first_file))
            self._append_info_ui(f"已设置输入文件: {os.path.basename(first_file)}")
            self.update_command_preview()
        else:
            self._append_info_ui(f"文件不存在: {first_file}")
        return "break"  # 阻止事件冒泡到根窗口
    
    def on_output_drop(self, event):
        """拖放到输出目录框：设置输出目录（若为文件则取其目录）"""
        files = self.root.tk.splitlist(event.data)
        if not files:
            return
        path = files[0]
        if os.path.isdir(path):
            self.output_dir.set(normalize_path(path))
            self._append_info_ui(f"已设置输出目录: {path}")
        else:
            self.output_dir.set(normalize_path(os.path.dirname(path)))
            self._append_info_ui(f"已提取输出目录: {os.path.dirname(path)}")
        self.update_command_preview()
        return "break"

    def merge_handle_dropped_file(self, path):
        def process():
            if os.path.isdir(path):
                self._append_info_ui(f"[封装] 忽略文件夹: {os.path.basename(path)}，请选择文件")
                return
            video_exts = ['.mp4','.mkv','.avi','.mov','.flv','.ts','.webm']
            ext = os.path.splitext(path)[1].lower()
            if ext in video_exts:
                if not self.merge_video.get():
                    self.merge_video.set(path)
                else:
                    if messagebox.askyesno("选择操作", f"将 {os.path.basename(path)} 设为主视频？\n【否】= 仅添加音频和字幕轨道"):
                        self.merge_video.set(path)
                    else:
                        self.merge_add_external("audio", path)
                        self.merge_add_external("subtitle", path)
            else:
                if not self.merge_video.get():
                    self._append_info_ui(f"[封装] 请先拖入视频文件作为主视频，然后才能添加字幕/音频: {os.path.basename(path)}")
                    return
                audio_exts = ['.mp3','.aac','.m4a','.wav','.flac','.ogg','.opus','.ac3','.dts']
                if ext in audio_exts:
                    self.merge_add_external("audio", path)
                else:
                    self.merge_add_external("subtitle", path)
        self.root.after(0, process)

    def _parse_files_concurrently(self, file_paths, max_workers=4, description="文件"):
        """
        并发解析文件，结果自动存入 _stream_info_cache（通过 merge_get_media_info）。
        返回成功解析的文件路径列表。
        """
        if max_workers is None:
            max_workers = self.ffprobe_parallel.get()
        if max_workers < 1:
            max_workers = 1
        if not file_paths:
            return []
        successful = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {executor.submit(self.merge_get_media_info, f): f for f in file_paths}
            for future in concurrent.futures.as_completed(future_to_path):
                f = future_to_path[future]
                try:
                    info = future.result()
                    if info:
                        successful.append(f)
                    else:
                        self._append_info_ui(f"[封装] 无法解析{description}: {os.path.basename(f)}")
                except Exception as e:
                    self._append_info_ui(f"[封装] 解析{description} {os.path.basename(f)} 异常: {e}")
        return successful
    
    def _add_tracks_from_cache(self, file_paths, track_types=('audio', 'subtitle')):
        """
        从缓存中读取指定文件列表的流信息，添加轨道到 merge_tracks（自动去重）。
        返回成功添加的轨道数量。
        """
        added = 0
        for f in file_paths:
            info = self._get_cached_stream_info(f)
            if not info:
                continue
            streams = info.get('streams', [])
            for s in streams:
                st = s.get('codec_type')
                if st not in track_types:
                    continue
                # 检查是否已存在相同轨道（避免重复）
                exists = any(t.file_path == f and t.index == s['index'] for t in self.merge_tracks)
                if exists:
                    continue
                track = Track(s['index'], st, s.get('codec_name', 'unknown'), f, True)
                self.merge_tracks.append(track)
                added += 1
        return added

    def merge_handle_batch_dropped(self, files):
        """
        批量拖拽文件到合并标签页时的处理（普通模式）
        """
        # 分类文件
        files_sorted = sorted(files, key=lambda x: os.path.basename(x).lower())
        video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.ts', '.webm', '.m2ts', '.mpg', '.mpeg', '.wmv')
        video_files = []
        other_files = []
        for f in files_sorted:
            if os.path.isdir(f):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in video_exts:
                video_files.append(f)
            else:
                other_files.append(f)
    
        # ---- 没有视频文件 ----
        if not video_files:
            if self.merge_video.get().strip():
                # 已有主视频，直接添加音频/字幕
                self._batch_update = True
                try:
                    # 并发解析其他文件
                    self._parse_files_concurrently(other_files, description="音频/字幕文件")
                    # 从缓存添加轨道
                    self._add_tracks_from_cache(other_files)
                finally:
                    self._batch_update = False
                    self.merge_update_track_list()
                    self.merge_auto_recommend_container()
                    self.merge_update_command_preview()
                    self._append_info_ui(f"[封装] 已添加 {len(other_files)} 个音频/字幕文件")
                return
            else:
                messagebox.showinfo("提示", "未检测到视频文件，请先拖入或选择视频作为主视频")
                return
    
#         # ---- 有视频文件 ----
#         if len(video_files) > 10:
#             result = messagebox.askyesno(
#                 "批量处理提示",
#                 f"您正在普通模式下拖拽 {len(video_files)} 个视频文件，解析可能较慢。\n\n"
#                 "建议：\n"
#                 "• 若文件数超过 10 个，推荐使用「串行合并」模式批量添加。\n"
#                 "  这个模式无多余解析，添加速度快，可添加完后切换回普通模式增删。\n\n"
#                 "是否继续使用普通模式？\n（选“是”继续，选“否”取消本次操作）",
#                 icon='warning'
#             )
#             if not result:
#                 self._append_info_ui("[封装] 用户取消批量添加，请切换到串行或画中画模式重试。")
#                 return
    
        # 后台解析视频文件
        def run_in_thread():
            self._parse_files_concurrently(video_files, description="视频文件")
            self.root.after(0, self._show_main_video_selection_dialog, video_files, other_files)
    
        threading.Thread(target=run_in_thread, daemon=True).start()
    
    def _show_main_video_selection_dialog(self, video_files, other_files):
        """
        显示选择主视频的对话框（在主线程中执行）
        """
        root_tk = self.root
        dialog = tk.Toplevel(root_tk)
        dialog.title("批量处理选项")
        height = min(350 + len(video_files) * 25, 600) + 40
        center_window(dialog, 600, height)
        dialog.transient(root_tk)
        dialog.grab_set()
    
        has_main = bool(self.merge_video.get().strip())
        info_text = "请选择操作：\n\n• [All] 按钮：仅添加音频（不改变主视频）\n• 点击下方视频按钮：设为主视频，其余添加音频"
        tk.Label(dialog, text=info_text, justify=tk.LEFT).pack(pady=10, padx=10)
    
        def all_action():
            def do_all():
                self._batch_update = True
                try:
                    if not has_main and video_files:
                        main = video_files[0]
                        self.merge_video.set(main)
                        self._append_info_ui(f"[封装] 自动设置主视频: {os.path.basename(main)}")
                        start_idx = 1
                    else:
                        start_idx = 0
                    # 添加除主视频外的其他视频的音频/字幕
                    self._add_tracks_from_cache(video_files[start_idx:])
                    # 处理其他文件（音频/字幕）
                    for f in other_files:
                        self.merge_handle_dropped_file(f)
                finally:
                    self._batch_update = False
                    self.merge_update_track_list()
                    self.merge_auto_recommend_container()
                    self.merge_update_output_preview()
                    self.merge_update_command_preview()
                dialog.destroy()
            self.root.after(0, do_all)
    
        btn_all = tk.Button(dialog, text="[All] 仅音频", command=all_action,
                            bg="#4CAF50", fg="white", width=22, wraplength=300)
        btn_all.pack(pady=5, padx=10)
    
        # 视频选择列表
        canvas_frame = ttk.Frame(dialog)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
    
        def select_main_video(idx):
            def do_select():
                self._batch_update = True
                try:
                    main = video_files[idx]
                    self.merge_video.set(main)
                    self._append_info_ui(f"[封装] 设置主视频为: {os.path.basename(main)}")
                    # 添加除主视频外的其他视频的音频/字幕
                    other_videos = [f for i, f in enumerate(video_files) if i != idx]
                    self._add_tracks_from_cache(other_videos)
                    # 处理其他文件（音频/字幕）
                    for f in other_files:
                        self.merge_handle_dropped_file(f)
                finally:
                    self._batch_update = False
                    self.merge_update_track_list()
                    self.merge_auto_recommend_container()
                    self.merge_update_output_preview()
                    self.merge_update_command_preview()
                dialog.destroy()
            self.root.after(0, do_select)
    
        for i, vf in enumerate(video_files):
            btn = tk.Button(scrollable_frame, text=f"{i+1}. {os.path.basename(vf)}",
                            wraplength=550, anchor="w", justify=tk.LEFT,
                            command=lambda idx=i: select_main_video(idx))
            btn.pack(fill=tk.X, pady=2, padx=5)
    
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tk.Button(dialog, text="取消", command=dialog.destroy).pack(pady=10)

    def clear_input_output(self):
        """清空输入文件和输出目录（带确认）"""
        if messagebox.askyesno("确认清空", "确定要清空输入文件和输出目录吗？"):
            self.input_file.set("")
            self.output_dir.set("")
            self.update_command_preview()
            self._append_info_ui("已清空输入文件和输出目录")


    # ---------- 播放器设置标签页 ----------
    def create_player_settings_tab(self, parent):
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        self.mpv_check = ttk.Checkbutton(frame, text="启用 mpv 作为预览播放器（推荐，支持进度条等）",
                                         variable=self.use_mpv,
                                         command=self.on_player_changed)
        self.mpv_check.pack(anchor=tk.W, pady=0)
        path_frame = ttk.Frame(frame)
        path_frame.pack(fill=tk.X, pady=5)
        ttk.Label(path_frame, text="mpv 可执行文件路径:").pack(side=tk.LEFT, padx=(0,5))
        self.mpv_path_entry = ttk.Entry(path_frame, textvariable=self.mpv_path, width=40)
        self.mpv_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(path_frame, text="浏览", command=self.browse_mpv).pack(side=tk.LEFT, padx=5)

        # ---- 日志记录控制 ----
        log_frame = ttk.Frame(frame)
        log_frame.pack(fill=tk.X, pady=0)
        chk_log = ttk.Checkbutton(log_frame, text="记录成功命令到日志", variable=self.log_enabled_var)
        chk_log.pack(side=tk.LEFT)
        log_entry = ttk.Entry(log_frame, textvariable=self.log_path_var, width=30)
        log_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(log_frame, text="浏览", command=self.browse_log_file).pack(side=tk.LEFT, padx=5)

        # ---- FFmpeg 版本目录（自定义） ----
        ffmpeg_row = ttk.Frame(frame)
        ffmpeg_row.pack(fill=tk.X, pady=5)

        chk = ttk.Checkbutton(ffmpeg_row, text="启用自定义 FFmpeg 目录", variable=self.ffmpeg_dir_enabled,
                              command=self._on_ffmpeg_dir_changed)
        chk.pack(side=tk.LEFT, padx=0)

        # 添加 ToolTip
        ToolTip(chk,
            "硬件编码需要 FFmpeg 版本与显卡驱动 API 兼容。\n"
            "常见对应关系：\n"
            "• NVIDIA: FFmpeg 6.1 需 NVENC API 12.1；FFmpeg 7.0 需 NVENC SDK 13.0\n"
            "• AMD: FFmpeg 要求 AMF SDK 版本 ≥ 1.4.23 (较新版本要求可能更高)\n"
            "• Intel QSV / Apple VideoToolbox 由系统框架决定\n"
            "若遇到编码器初始化失败（如 API 版本不匹配），\n"
            "可尝试切换 FFmpeg 版本或更新显卡驱动。",
            wraplength=700
        )

        entry = ttk.Entry(ffmpeg_row, textvariable=self.ffmpeg_dir_path, width=40)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        ttk.Button(ffmpeg_row, text="浏览", command=self._browse_ffmpeg_dir).pack(side=tk.LEFT, padx=5)

        self.ffmpeg_dir_path.trace_add('write', self._on_ffmpeg_dir_changed)



        # ---- 水平布局：同名文件处理 + 预览编辑权限 ----
        horizontal_frame = ttk.Frame(frame)
        horizontal_frame.pack(fill=tk.X, pady=5)
        
        # 左：同名文件处理策略
        policy_frame = ttk.LabelFrame(horizontal_frame, text="全局同名文件处理策略", padding="5")
        policy_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        ttk.Label(policy_frame, text="当输出文件已存在时:").pack(side=tk.LEFT)
        policy_combo = ttk.Combobox(
            policy_frame,
            textvariable=self.overwrite_policy,
            values=["ask", "rename", "overwrite"],
            state="readonly",
            width=12
        )
        policy_combo.pack(side=tk.LEFT, padx=5)
        desc = ttk.Label(policy_frame, text="询问/自动重命名/直接覆盖", foreground="gray")
        desc.pack(side=tk.LEFT, padx=5)
        self.overwrite_policy.trace_add("write", lambda *a: self.save_player_settings())
        
        # 右：预览编辑权限控制
        edit_frame = ttk.LabelFrame(horizontal_frame, text="预览区编辑权限", padding="5")
        edit_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.preview_edit_check = ttk.Checkbutton(
            edit_frame,
            text="允许编辑预览命令（修改不影响实际转码）",
            variable=self.preview_editable_var,
            command=self._update_preview_edit_state
        )
        self.preview_edit_check.pack(anchor=tk.W, padx=5, pady=5)
        ToolTip(self.preview_edit_check, "勾选后，所有命令预览区可编辑，方便修改后复制命令，不会影响实际转码，改错后只需刷新命令就会还原。")



        # ---- 停止所有转码按钮 ----
        stop_frame = ttk.Frame(frame)
        stop_frame.pack(fill=tk.X, pady=5)
        
        stop_btn = tk.Button(
            stop_frame,
            text="停止所有转码",
            command=self.stop_all_transcodes,
            bg="#f44336",
            fg="white",
            font=("", 10, "bold")
        )
        stop_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(
            stop_frame,
            text="（向所有正在运行的 FFmpeg 进程发送停止信号，主要用于紧急停止因水印/画中画循环参数截断失效而无限延伸的转码，无需手动去任务管理器结束进程）",
            foreground="gray"
        ).pack(side=tk.LEFT, padx=10)



        # ---- 快速命令工具 ----
        cmd_tool_frame = ttk.LabelFrame(frame, text="快速命令工具", padding="5")
        cmd_tool_frame.pack(fill=tk.X, pady=5)

        # 顶部：预设下拉 + 输出目录 + 清空
        top_frame = ttk.Frame(cmd_tool_frame)
        top_frame.pack(fill=tk.X, pady=(0,2))

        preset_label1 = ttk.Label(top_frame, text="预设命令:")
        preset_label1.pack(side=tk.LEFT)
        
        ToolTip(preset_label1,
                "从下拉列表选择预设命令，自动填充到下方编辑框。\n\n"
                "您也可以自定义命令，编辑以下文件：\n"
                f"• {self.cmd_templates_path}\n\n"
                "格式为：{\"显示名称\": \"命令模板\"}\n\n"
                "支持占位符：\n"
                "• {input}    → 主界面「输入文件」的路径\n"
                "• {output_dir} → 右边「输出目录」的路径\n\n"
                "示例：\n"
                'ffmpeg -i "{input}" -c copy "{output_dir}output.mp4"\n\n'
                "编辑后点击右侧的「重载」按钮重新加载。\n"
                "如果编辑错误导致读取异常，可以删除该json文件后重启程序。",
                wraplength=500)

        self.cmd_preset_var = tk.StringVar()


        self.cmd_preset_combo = ttk.Combobox(
            top_frame,
            textvariable=self.cmd_preset_var,
            state="readonly",
            width=25,
            height=20
        )
        self.cmd_preset_combo['values'] = list(self.cmd_templates.keys())
        self.cmd_preset_combo.pack(side=tk.LEFT, padx=5)
        self.cmd_preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        ttk.Button(top_frame, text="重载", command=self._reload_cmd_templates, width=4).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_frame, text="清空", command=self._clear_cmd_input, width=4).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="获取", command=self._fetch_cmd_from_preview, width=4).pack(side=tk.LEFT, padx=2)

        # 输出目录（与当前工作目录结合）
        output_frame = ttk.Frame(top_frame)
        output_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(15,0))
        ttk.Label(output_frame, text="输出目录:").pack(side=tk.LEFT)
        entry = ttk.Entry(output_frame, textvariable=self.cmd_output_path)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(output_frame, text="浏览", command=self._browse_cmd_output).pack(side=tk.LEFT, padx=2)



        # 命令编辑框（多行）
        self.cmd_input = scrolledtext.ScrolledText(cmd_tool_frame, height=4, wrap=tk.WORD,
                                                   font=("", 9))
        self.cmd_input.pack(fill=tk.X, pady=5)

        # 底部：运行按钮 + 提示
        btn_frame = ttk.Frame(cmd_tool_frame)
        btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="运行命令", command=self._run_custom_command).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="复制到剪贴板", command=self._copy_custom_command).pack(side=tk.LEFT, padx=5)
        ttk.Label(btn_frame, text="（命令在独立线程执行，输出显示在日志区域）",
                  foreground="gray").pack(side=tk.LEFT, padx=10)




        status_frame = ttk.LabelFrame(frame, text="状态检测", padding="5")
        status_frame.pack(fill=tk.X, pady=(0, 5))
        self.status_text = tk.Text(status_frame, height=20, width=80, wrap=tk.WORD,
                                   bg="#f8f8f8", relief=tk.FLAT)
        self.status_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
        self.status_text.config(state=tk.DISABLED)
        btn_frame = ttk.Frame(status_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(btn_frame, text="在文件管理器中打开预设文件夹",
                   command=self.open_preset_folder).pack(side=tk.LEFT, padx=5)
        tip = ttk.Label(frame, text="提示：mpv 支持进度条、拖拽等交互，且兼容 FFmpeg 大部分滤镜。\n"
                                     "请确保已安装 mpv 并正确设置路径（例如 C:\\mpv\\mpv.exe 或直接输入 mpv）。\n"
                                     "未启用时使用 ffplay 预览。",
                        foreground="gray", wraplength=500, justify=tk.LEFT)
        tip.pack(anchor=tk.W, pady=(10,0))


        self.update_mpv_path_state()
        self.use_mpv.trace_add("write", lambda *a: self.update_player_status())
        self.mpv_path.trace_add("write", lambda *a: self.update_player_status())
 #       self.update_player_status()    #放到延迟里运行


    def _update_preview_edit_state(self):
        if getattr(self, '_loading_settings', False):
            return
        editable = self.preview_editable_var.get()
        # 更新转码预览区（如果存在）
        if hasattr(self, 'cmd_preview'):
            self.cmd_preview.config(state='normal' if editable else 'disabled')
        # 更新合并预览区（如果存在）
        if hasattr(self, 'merge_cmd_preview'):
            self.merge_cmd_preview.config(state='normal' if editable else 'disabled')
        # 仅在初始化完成后保存设置
        if hasattr(self, '_initialized') and self._initialized:
            self.save_player_settings()

    def _fetch_cmd_from_preview(self):
        """从预览区获取命令（转换或合并）到快速命令区"""
        # 询问用户选择
        result = messagebox.askyesno(
            "获取命令",
            "是否从转换预览区获取命令？\n（点击“是”获取转换命令，点击“否”获取合并命令）"
        )
        if result is None:  # 用户关闭对话框
            return
        if result:
            source = self.cmd_preview
            source_name = "转换"
        else:
            source = self.merge_cmd_preview
            source_name = "合并"
        
        cmd_str = source.get(1.0, tk.END).strip()
        if not cmd_str:
            self._append_info_ui(f"{source_name}预览区无命令")
            messagebox.showinfo("提示", f"{source_name}预览区为空")
            return
        
        self.cmd_input.delete(1.0, tk.END)
        self.cmd_input.insert(tk.END, cmd_str)
        self._append_info_ui(f"已从{source_name}预览区获取命令")
        self.cmd_input.focus_set()


    def _reload_cmd_templates(self):
        """重新加载命令模板（用户编辑 JSON 后调用）"""
        self._load_cmd_templates()
        self._append_info_ui("✅ 已重新加载快速命令模板")

    def _browse_ffmpeg_dir(self):
        path = filedialog.askdirectory(title="选择 FFmpeg 所在目录")
        if path:
            self.ffmpeg_dir_path.set(normalize_path(path))
            self.ffmpeg_dir_enabled.set(True)
            self._on_ffmpeg_dir_changed()
    
    def _on_ffmpeg_dir_changed(self):
        if getattr(self, '_loading_settings', False):
            return
        self._update_ffmpeg_paths()
        self.save_player_settings()
        # 刷新命令预览（因为 ffmpeg 路径改变了）
        self.update_command_preview()
        self.update_player_status()


    def _browse_cmd_output(self):
        path = filedialog.askdirectory(title="选择命令执行目录")
        if path:
            self.cmd_output_path.set(normalize_path(path).rstrip('/'))
            self.save_player_settings()
    
    
    def _on_preset_selected(self, event=None):
        preset_name = self.cmd_preset_var.get()
        if preset_name not in self.cmd_templates:
            return
    
        template = self.cmd_templates[preset_name]
        input_file = self.input_file.get().strip()
        if not input_file:
            input_file = "input.mp4"
    
        output_dir = self.cmd_output_path.get().strip()
        if output_dir:
            # 规范化路径，去除尾部斜杠，添加一个 / 作为分隔符
            output_dir = normalize_path(output_dir).rstrip('/') + "/"
        else:
            output_dir = ""   # 空字符串，文件将生成在当前工作目录
    
        cmd = template.replace("{input}", input_file).replace("{output_dir}", output_dir)
    
        self.cmd_input.delete(1.0, tk.END)
        self.cmd_input.insert(tk.END, cmd)

    def _clear_cmd_input(self):
        """清空命令文本框"""
        self.cmd_input.delete(1.0, tk.END)

    def _copy_custom_command(self):
        """复制快速命令工具中的命令到剪贴板"""
        cmd_str = self.cmd_input.get(1.0, tk.END).strip()
        if cmd_str:
            self.root.clipboard_clear()
            self.root.clipboard_append(cmd_str)
            self._append_info_ui("快速命令已复制到剪贴板")
        else:
            self._append_info_ui("命令文本框为空，无内容可复制")


    def _run_custom_command(self):
        """执行命令文本框中的命令，在独立线程中运行，支持全局停止"""
        cmd_str = self.cmd_input.get(1.0, tk.END).strip()
        if not cmd_str:
            messagebox.showwarning("提示", "请输入要执行的命令")
            return
    
        if not messagebox.askyesno("确认执行", f"将执行以下命令：\n\n{cmd_str}\n\n确定吗？"):
            return
    
        # 获取输出目录
        cwd = self.cmd_output_path.get().strip()
        if not cwd or not os.path.exists(cwd):
            cwd = os.getcwd()
            self.cmd_output_path.set(cwd)
    
        # 在独立线程中执行，避免阻塞UI
        def run_thread():
            self._append_info_ui(f"\n========== 快速命令开始 ==========")
            self._append_info_ui(f">>> {cmd_str}")
            self._append_info_ui(f"工作目录: {cwd}")
    
            proc = None
            try:
                proc = subprocess.Popen(
                    cmd_str,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,          # 启用 stdin 以便发送 q
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    shell=True,
                    cwd=cwd,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                # 添加到进程列表（加锁）
                with self._proc_lock:
                    self.running_procs.append(proc)
    
                # 逐行读取输出
                for line in proc.stdout:
                    self.safe_append_detail(line)
    
                retcode = proc.wait()
                if retcode == 0:
                    self._append_info_ui(f"✅ 命令执行成功 (返回码 {retcode})")
                else:
                    self._append_info_ui(f"❌ 命令执行失败 (返回码 {retcode})")
            except Exception as e:
                self._append_info_ui(f"❌ 命令执行异常: {e}")
            finally:
                # 从进程列表移除（加锁）
                with self._proc_lock:
                    if proc in self.running_procs:
                        self.running_procs.remove(proc)
                self._append_info_ui("========== 快速命令结束 ==========\n")
    
        # 启动线程
        threading.Thread(target=run_thread, daemon=True).start()

    def open_preset_folder(self):
        folder = os.path.dirname(self.preset_file_path)
        if not os.path.exists(folder):
            folder = get_script_dir()
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            self._append_info_ui(f"打开文件夹失败: {e}")


    def browse_log_file(self):
        path = filedialog.asksaveasfilename(
            title="选择日志文件",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if path:
            self.log_path_var.set(normalize_path(path))
            self.save_player_settings()

    def update_player_status(self):
        if not hasattr(self, 'status_text'):
            return
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete(1.0, tk.END)
    
        # 预设信息
        preset_path = normalize_path(self.preset_file_path)
        if os.path.exists(preset_path):
            preset_status = "✓ 文件存在"
        else:
            preset_status = "✗ 文件不存在（将自动创建）"
        local_preset = normalize_path(os.path.join(get_script_dir(), "ffmpeg_presets.json"))
        if preset_path == local_preset:
            source = "脚本目录（便携模式）"
        else:
            source = "用户目录（%USERPROFILE%\\.FFLiteGUI）"
        self.status_text.insert(tk.END, f"预设配置文件: {preset_path}\n")
        self.status_text.insert(tk.END, f"配置来源: {source}  | 状态: {preset_status}\n\n")
    
        # mpv 预览状态
        if self.use_mpv.get():
            mpv_path = normalize_path(self.mpv_path.get().strip())
            self.status_text.insert(tk.END, "mpv 预览: 已启用\n")
            if mpv_path:
                if os.path.exists(mpv_path) and os.access(mpv_path, os.X_OK):
                    self.status_text.insert(tk.END, f"  mpv 路径: {mpv_path}  →  ✓ 有效\n")
                else:
                    self.status_text.insert(tk.END, f"  mpv 路径: {mpv_path}  →  ✗ 无效（文件不存在或不可执行）\n")
                    self.status_text.insert(tk.END, "  请检查路径是否正确，或重新安装 mpv。\n")
            else:
                self.status_text.insert(tk.END, "  mpv 路径未设置，预览将失败。\n")
        else:
            self.status_text.insert(tk.END, "预览播放器: ffplay（未启用 mpv）\n")
            if self.ffplay_cmd and os.path.exists(self.ffplay_cmd):
                self.status_text.insert(tk.END, f"  ffplay 路径: {normalize_path(self.ffplay_cmd)}  →  ✓ 可用\n")
            else:
                self.status_text.insert(tk.END, f"  ffplay 未找到，请将 ffplay.exe 放在脚本目录或添加到 PATH。\n")
    
        # ---- 当前 FFmpeg 全家桶路径（实际使用） ----
        self.status_text.insert(tk.END, "\n--- 当前 FFmpeg 全家桶路径（实际使用） ---\n")
        tools = [('ffmpeg', self.ffmpeg_cmd), ('ffprobe', self.ffprobe_cmd), ('ffplay', self.ffplay_cmd)]
        for name, path in tools:
            if path:
                # 规范化路径显示
                display_path = normalize_path(path)
                # 判断来源
                if self.ffmpeg_dir_enabled.get() and self.ffmpeg_dir_path.get().strip():
                    base_dir = normalize_path(self.ffmpeg_dir_path.get().strip())
                    if os.path.dirname(display_path) == base_dir:
                        source_str = "自定义"
                    else:
                        source_str = "系统PATH"
                else:
                    source_str = "系统PATH"
                self.status_text.insert(tk.END, f"  {name}: {display_path}  →  {source_str}\n")
            else:
                self.status_text.insert(tk.END, f"  {name}: 未找到\n")
    
        # ---- 环境变量 PATH 中的 FFmpeg 全家桶检测（只显示存在的） ----
        self.status_text.insert(tk.END, "\n--- 环境变量 PATH 中的 FFmpeg 全家桶检测 ---\n")
        tools = ['ffmpeg', 'ffplay', 'ffprobe']
        script_dir = get_script_dir()
        self.status_text.insert(tk.END, f"当前目录 ({normalize_path(script_dir)}):\n")
        found_any = False
        for tool in tools:
            exe_name = tool + ".exe" if sys.platform == "win32" else tool
            local_path = os.path.join(script_dir, exe_name)
            if os.path.isfile(local_path) and os.access(local_path, os.X_OK):
                self.status_text.insert(tk.END, f"  {exe_name}: ✓ 存在 → {local_path}\n")
                found_any = True
        if not found_any:
            self.status_text.insert(tk.END, "  无\n")
    
        if getattr(sys, 'frozen', False):
            internal_dir = os.path.join(script_dir, '_internal')
            if os.path.isdir(internal_dir):
                self.status_text.insert(tk.END, f"\n_internal 目录 ({internal_dir}):\n")
                found_any = False
                for tool in tools:
                    exe_name = tool + ".exe" if sys.platform == "win32" else tool
                    internal_path = os.path.join(internal_dir, exe_name)
                    if os.path.isfile(internal_path) and os.access(internal_path, os.X_OK):
                        self.status_text.insert(tk.END, f"  {exe_name}: ✓ 存在 → {internal_path}\n")
                        found_any = True
                if not found_any:
                    self.status_text.insert(tk.END, "  无\n")
    
        self.status_text.insert(tk.END, "环境变量 PATH:\n")
        import shutil
        found_any = False
        for tool in tools:
            path_in_path = shutil.which(tool)
            if path_in_path:
                self.status_text.insert(tk.END, f"  {tool}: ✓ 找到 → {normalize_path(path_in_path)}\n")
                found_any = True
        if not found_any:
            self.status_text.insert(tk.END, "  无\n")
        self.status_text.insert(tk.END, "（提示：FFmpeg 全家桶用于编码、解码、预览等核心功能，建议确保 ffmpeg、ffplay、ffprobe 三者均可访问）\n")
    
        self.status_text.config(state=tk.DISABLED)

    def on_player_changed(self):
        self.update_mpv_path_state()
        self.save_player_settings()
        self.update_player_status()

    def update_mpv_path_state(self):
        state = tk.NORMAL if self.use_mpv.get() else tk.DISABLED
        self.mpv_path_entry.config(state=state)

    def browse_mpv(self):
        path = filedialog.askopenfilename(title="选择 mpv 可执行文件", filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")])
        if path:
            self.mpv_path.set(normalize_path(path))
            self.save_player_settings()
            self.update_player_status()

    # ---------- 基本界面输入方法 ----------
    def select_input(self):
        path = filedialog.askopenfilename(title="选择视频文件")
        if path:
            path = normalize_path(path)
            self.input_file.set(path)
            if not self.output_dir.get():
                self.output_dir.set(os.path.dirname(path))
            self.update_command_preview()

    def select_output_dir(self):
        dirpath = filedialog.askdirectory()
        if dirpath:
            dirpath = normalize_path(dirpath)
            self.output_dir.set(dirpath)
            self.update_command_preview()

    def append_info(self, text):
        self.info_text.insert(tk.END, text + "\n")
        self.info_text.see(tk.END)

    def append_detail(self, text):
        self.detail_text.insert(tk.END, text)
        self.detail_text.see(tk.END)

    def save_log(self, text_widget):
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("文本文件", "*.txt")])
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(text_widget.get(1.0, tk.END))
                self._append_info_ui(f"日志已保存到 {file_path}")
            except Exception as e:
                messagebox.showerror("保存失败", str(e))

    def check_ffmpeg_dependencies(self):
        return self.ffmpeg_cmd, self.ffplay_cmd, self.ffprobe_cmd

    def show_quick_warning(self):
        missing = []
        if not self.ffmpeg_cmd: missing.append("ffmpeg")
        if not self.ffplay_cmd: missing.append("ffplay")
        if not self.ffprobe_cmd: missing.append("ffprobe")
        if missing:
            missing_str = "、".join(missing)
            self._append_info_ui("必要组件缺失: " + missing_str)
            self._append_info_ui("请确保 FFmpeg 已正确安装。快捷方法：")
            self._append_info_ui("  ① 将 ffmpeg.exe、ffplay.exe、ffprobe.exe 放在本脚本同一目录下（推荐，绿色便携）")
            self._append_info_ui("  ② 或者将它们所在文件夹的路径添加到系统 Path 环境变量中")
            self._append_info_ui("推荐下载 FFmpeg 的 **shared** 版本（体积小，节约空间）：")
            self._append_info_ui("下载地址: https://github.com/BtbN/FFmpeg-Builds/releases")
            self._append_info_ui("选择文件名中包含 'shared' 的版本，例如: ffmpeg-master-latest-win64-gpl-shared.zip")
            self._append_info_ui("解压后，将 bin 文件夹内的三个 exe 文件复制到本脚本目录，或添加 bin 路径到 Path。")
            self._append_info_ui("提示：您可以在此日志框中直接选中上面的链接文字，右键复制。")

    def copy_command(self):
        cmd_str = self.cmd_preview.get(1.0, tk.END).strip()
        if cmd_str:
            self.root.clipboard_clear()
            self.root.clipboard_append(cmd_str)
            self._append_info_ui("[封装] 命令已复制到剪贴板")
        else:
            self._append_info_ui("[封装] 无命令可复制")

    # 流提取页面创建
    def create_extract_tab(self, parent):
        main_frame = ttk.Frame(parent, padding="0")
        main_frame.pack(fill=tk.BOTH, expand=True)
    
        # ---- 独立的标签行（显示提示文本） ----
        if DND_AVAILABLE:
            label_text = "输入文件列表 - 支持拖拽添加文件"
        else:
            label_text = "输入文件列表"
        ttk.Label(main_frame, text=label_text).pack(anchor=tk.W, padx=5, pady=(0, 0))
    
        # ---- 文件列表容器（无边框） ----
        list_container = ttk.Frame(main_frame)
        list_container.pack(fill=tk.BOTH, expand=True, padx=(5,0), pady=2)
    
        # ---- 工具栏（只包含按钮，不再重复显示标题） ----
        tree_toolbar = ttk.Frame(list_container)
        tree_toolbar.pack(fill=tk.X, pady=3)
    
        ttk.Button(tree_toolbar, text="添加文件", command=self.extract_add_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(tree_toolbar, text="清空列表", command=self.extract_clear_files).pack(side=tk.LEFT, padx=2)
        ttk.Button(tree_toolbar, text="删除选中", command=self.extract_delete_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(tree_toolbar, text="预览选中", command=self.extract_preview_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(tree_toolbar, text="发送选中", command=self.extract_send_selected).pack(side=tk.LEFT, padx=2)
        ttk.Label(tree_toolbar, text="（双击行预览当前文件）").pack(side=tk.LEFT, padx=10)
    
        # ---- Treeview 与滚动条 ----
        extract_style = ttk.Style()
        extract_style.configure("Extract.Treeview", background="#f0f0f0", fieldbackground="#f0f0f0", rowheight=int(22 * self.scaling))
        extract_style.configure("Extract.Treeview.Heading", background="#d9d9d9")
    
        columns = ("文件名", "完整路径")
        self.extract_tree = ttk.Treeview(list_container, columns=columns, show="headings",
                                         height=8, style="Extract.Treeview")
        self.extract_tree.heading("文件名", text="文件名")
        self.extract_tree.heading("完整路径", text="完整路径")
        self.extract_tree.column("文件名", width=200, minwidth=100)
        self.extract_tree.column("完整路径", width=400, minwidth=200)
        self.extract_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
        vbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.extract_tree.yview)
        self.extract_tree.configure(yscrollcommand=vbar.set)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
    
        # 双击预览
        self.extract_tree.bind("<Double-1>", self.extract_on_tree_double_click)
    
        # ---- 拖拽绑定（确保只在此页面生效） ----
        if DND_AVAILABLE:
            list_container.drop_target_register(DND_FILES)
            list_container.dnd_bind('<<Drop>>', self.extract_on_drop)
    
        # ---- 提取选项（保持不变） ----
        opt_frame = ttk.LabelFrame(main_frame, text="提取选项", padding="5")
        opt_frame.pack(fill=tk.X, pady=5)
        opt_frame.columnconfigure(3, weight=0)
    
        self.extract_video = tk.BooleanVar(value=True)
        self.extract_audio = tk.BooleanVar(value=True)
        self.extract_subtitle = tk.BooleanVar(value=True)
        self.extract_only_first = tk.BooleanVar(value=False)
        self.extract_subfolders = tk.BooleanVar(value=False)
    
        # 第一行：视频
        chk_video = ttk.Checkbutton(opt_frame, text="提取视频流", variable=self.extract_video)
        chk_video.grid(row=0, column=0, sticky="w", padx=10)
        ttk.Label(opt_frame, text="输出容器: ").grid(row=0, column=1, padx=(20,0))
        self.extract_video_container = tk.StringVar(value="mkv")
        ttk.Combobox(opt_frame, textvariable=self.extract_video_container,
                     values=["mkv", "mp4", "mov"], state="readonly", width=6).grid(row=0, column=2, sticky="w")

        chk_chapters = ttk.Checkbutton(opt_frame, text="保留章节", variable=self.extract_keep_chapters)
        chk_chapters.grid(row=0, column=3, sticky="w", padx=(0,10))
        ToolTip(chk_chapters,
                "勾选后，提取视频流音频流时会保留章节标记（-map_chapters 0）。\n\n"
                "支持的格式：\n"
                "• 视频：MKV、MP4、MOV 等主流容器均支持章节。\n"
                "• 音频：M4A / M4B（推荐）、MKA 原生支持；MP3 / FLAC / OGG 虽也支持但播放器兼容性较差。\n\n"
                "重要提示（音频提取）：\n"
                "如果您希望保留专辑分轨或有声书章节，请关闭「自动匹配」，并手动选择输出格式为 M4A 或 MKA，以确保章节信息被完整保留。自动匹配可能根据编码扩展名选择不支持章节的格式（如 .mp3），导致章节丢失。")
        self.extract_keep_chapters.trace_add('write', lambda *a: self.save_player_settings())


        # 第二行：音频 + 自动匹配
        chk_audio = ttk.Checkbutton(opt_frame, text="提取音频流", variable=self.extract_audio)
        chk_audio.grid(row=1, column=0, sticky="w", padx=10)
        ttk.Label(opt_frame, text="输出格式: ").grid(row=1, column=1, padx=(20,0))
        self.extract_audio_format = tk.StringVar(value="mka")
        self.extract_audio_format_combo = ttk.Combobox(opt_frame, textvariable=self.extract_audio_format,
                                                        values=["m4a", "mp3", "flac", "wav", "aac", "mka"], state="readonly", width=6)
        self.extract_audio_format_combo.grid(row=1, column=2, sticky="w", padx=(0,5))
        chk_auto_audio = ttk.Checkbutton(opt_frame, text="自动匹配", variable=self.auto_match_audio_ext,
                                         command=self._on_auto_audio_toggle)
        chk_auto_audio.grid(row=1, column=3, sticky="w", padx=(0,10))
        ToolTip(chk_auto_audio, "根据检测到的音频编码自动选择输出扩展名（如 AAC→.m4a, MP3→.mp3, FLAC→.flac）")

        self.auto_match_audio_ext.trace_add('write', lambda *a: self.save_player_settings())

        # 第三行：字幕 + 自动匹配
        chk_sub = ttk.Checkbutton(opt_frame, text="提取字幕流", variable=self.extract_subtitle)
        chk_sub.grid(row=2, column=0, sticky="w", padx=10)
        ttk.Label(opt_frame, text="输出格式: ").grid(row=2, column=1, padx=(20,0))
        self.extract_subtitle_format = tk.StringVar(value="srt")
        self.extract_subtitle_format_combo = ttk.Combobox(opt_frame, textvariable=self.extract_subtitle_format,
                                                          values=["srt", "ass", "vtt", "mov_text"], state="readonly", width=6)
        self.extract_subtitle_format_combo.grid(row=2, column=2, sticky="w", padx=(0,5))
        chk_auto_ext = ttk.Checkbutton(opt_frame, text="自动匹配", variable=self.auto_match_subtitle_ext,
                                       command=self._on_auto_ext_toggle)
        chk_auto_ext.grid(row=2, column=3, sticky="w", padx=(0,10))
        ToolTip(chk_auto_ext, "根据检测到的字幕编码自动选择输出扩展名（如 ASS→.ass, SRT→.srt）")

        self.auto_match_subtitle_ext.trace_add('write', lambda *a: self.save_player_settings())


        # 第四行：仅第一轨、分文件夹
        chk_only_first = ttk.Checkbutton(opt_frame, text="仅提取第一轨（取消则提取全部匹配轨）",
                                         variable=self.extract_only_first)
        chk_only_first.grid(row=3, column=0, sticky="w", padx=10, pady=5)
        ToolTip(chk_only_first,
                "勾选后，每种流类型仅提取第一个轨道（如第一条音频、第一条字幕）。\n"
                "取消勾选则提取该类型的所有轨道。\n\n"
                "如需更精确的选择（如提取第三条字幕），请先将任务添加到队列，然后在任务列表中手动删除不需要的任务。\n\n"
                "每种类型流从 0 开始计算，所以对应需要 -1，比如第三音频轨会是 audio_2 那一条任务。\n\n"
                "或者直接在预览区复制想单独提取那一条的命令手动运行。",
                wraplength=700)
    
        ttk.Checkbutton(opt_frame, text="按流类型分文件夹存放（video/audio/subtitle）",
                        variable=self.extract_subfolders).grid(row=3, column=1, columnspan=2, sticky="w", padx=10, pady=5)

        chk_metadata = ttk.Checkbutton(opt_frame, text="清除元数据", variable=self.extract_clear_metadata)
        chk_metadata.grid(row=3, column=3, sticky="w", padx=10, pady=5)
        ToolTip(chk_metadata, "勾选后，输出文件将不包含任何元数据（如作者、专辑等），适用于铃声或素材提取。")


        self.extract_clear_metadata.trace_add('write', lambda *a: self.save_player_settings())

        # 初始化自动匹配状态
        self._suppress_save = True
        self._on_auto_ext_toggle()
        self._on_auto_audio_toggle()
        self._on_extract_custom_dir_toggle()
        self._suppress_save = False
    
        # ---- 输出目录 ----
        out_frame = ttk.Frame(main_frame)
        out_frame.pack(fill=tk.X, pady=5)
    
        btn_send = tk.Button(out_frame, text="发送所有到任务队列", command=self.extract_add_to_queue,
                             bg="#4CAF50", fg="white", font=("", 10, "bold"),
                             relief=tk.RAISED, padx=10, pady=2)
        btn_send.pack(side=tk.LEFT, padx=(5, 25))
    
        chk_custom = ttk.Checkbutton(out_frame, text="输出到自定义目录", variable=self.extract_custom_dir,
                                     command=self._on_extract_custom_dir_toggle)
        chk_custom.pack(side=tk.LEFT, padx=5)
        self.extract_output_entry = ttk.Entry(out_frame, textvariable=self.extract_output_dir, width=30, state='disabled')
        self.extract_output_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.extract_browse_btn = ttk.Button(out_frame, text="浏览", command=self.extract_browse_output, state='disabled')
        self.extract_browse_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(chk_custom,
                "勾选后，输出文件将保存到下方指定的目录（路径会被自动记忆）。\n"
                "不勾选时，输出文件默认保存在输入文件所在目录。")

    
        # ---- 命令预览区 ----
        preview_frame = ttk.LabelFrame(main_frame, text="命令预览（点击行预览按钮查看对应文件）", padding="0")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.extract_preview_text = scrolledtext.ScrolledText(preview_frame, height=8, wrap=tk.WORD)
        self.extract_preview_text.pack(fill=tk.BOTH, expand=True, padx=(5,0))
    
        # 绑定选项变更事件，自动刷新当前预览
        self.extract_video.trace_add('write', self._on_extract_option_changed)
        self.extract_audio.trace_add('write', self._on_extract_option_changed)
        self.extract_subtitle.trace_add('write', self._on_extract_option_changed)
        self.extract_only_first.trace_add('write', self._on_extract_option_changed)
        self.extract_subfolders.trace_add('write', self._on_extract_option_changed)
        self.extract_video_container.trace_add('write', self._on_extract_option_changed)
        self.extract_audio_format.trace_add('write', self._on_extract_option_changed)
        self.extract_subtitle_format.trace_add('write', self._on_extract_option_changed)
        self.auto_match_subtitle_ext.trace_add('write', self._on_extract_option_changed)
        self.auto_match_audio_ext.trace_add('write', self._on_extract_option_changed)
        self.extract_keep_chapters.trace_add('write', lambda *a: self._on_extract_option_changed())
        self.extract_clear_metadata.trace_add('write', lambda *a: self._on_extract_option_changed())


        # 初始化列表

        self._refresh_extract_file_list()

    def _on_extract_option_changed(self, *args):
        # 如果预览文本控件尚未创建，则直接返回
        if not hasattr(self, 'extract_preview_text'):
            return
        # 如果当前有预览文件且在列表中，刷新它
        if self.current_preview_file and self.current_preview_file in self.extract_file_list:
            self._extract_preview_file(self.current_preview_file)
        elif self.extract_file_list:
            # 否则预览第一个文件
            self.current_preview_file = self.extract_file_list[0]
            self._extract_preview_file(self.current_preview_file)
        else:
            # 列表为空，清空预览
            self.extract_preview_text.delete(1.0, tk.END)
            self.extract_preview_text.insert(tk.END, "文件列表为空")

    def extract_remove_file(self, file_path):
        if file_path in self.extract_file_list:
            self.extract_file_list.remove(file_path)
            # 如果删除的是当前预览文件，清除预览
            if self.current_preview_file == file_path:
                self.current_preview_file = None
            self._refresh_extract_file_list()
            self._append_info_ui(f"[流提取] 已删除: {os.path.basename(file_path)}")

    def _refresh_extract_file_list(self):
        """刷新流提取文件列表（Treeview），交替行颜色"""
        for item in self.extract_tree.get_children():
            self.extract_tree.delete(item)
    
        # 配置交替行标签（不会影响其他 Treeview）
        self.extract_tree.tag_configure('odd', background='#D9F0D9')
        self.extract_tree.tag_configure('even', background='#FDEBD0')
    
        for i, path in enumerate(self.extract_file_list):
            tag = 'odd' if i % 2 == 0 else 'even'
            self.extract_tree.insert("", tk.END, iid=f"file_{i}",
                                     values=(os.path.basename(path), path),
                                     tags=(tag,))
    
        # 自动预览第一个文件
        if self.extract_file_list:
            self.current_preview_file = self.extract_file_list[0]
            self._extract_preview_file(self.current_preview_file)
        else:
            self.current_preview_file = None
            self.extract_preview_text.delete(1.0, tk.END)
            self.extract_preview_text.insert(tk.END, "文件列表为空")

    def extract_delete_selected(self):
        """删除选中的文件"""
        selected = self.extract_tree.selection()
        if not selected:
            return
        # 按索引从大到小删除，避免越界
        indices = sorted([int(item.split('_')[1]) for item in selected], reverse=True)
        for idx in indices:
            if 0 <= idx < len(self.extract_file_list):
                removed = self.extract_file_list.pop(idx)
                self._append_info_ui(f"[流提取] 已删除: {os.path.basename(removed)}")
        self._refresh_extract_file_list()
    
    def extract_preview_selected(self):
        """预览选中的第一个文件"""
        selected = self.extract_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选中一个文件")
            return
        iid = selected[0]
        idx = int(iid.split('_')[1])
        if 0 <= idx < len(self.extract_file_list):
            self._extract_preview_file(self.extract_file_list[idx])
    
    def extract_send_selected(self):
        """发送选中的文件到任务队列"""
        selected = self.extract_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选中文件")
            return
        files = []
        for iid in selected:
            idx = int(iid.split('_')[1])
            if 0 <= idx < len(self.extract_file_list):
                files.append(self.extract_file_list[idx])
        if files:
            self._process_send_files_to_queue(files)
    

    
    def extract_on_tree_double_click(self, event):
        """双击行预览该文件"""
        item = self.extract_tree.selection()
        if item:
            self.extract_preview_selected()


    def _extract_preview_file(self, file_path):
        """预览指定文件的全部提取命令（根据当前选项），自动添加轨道语言和标题"""
        self.current_preview_file = file_path
        stream_indices = self.extract_get_stream_indices(file_path)
        if not any(stream_indices.values()):
            self.extract_preview_text.delete(1.0, tk.END)
            self.extract_preview_text.insert(tk.END, f"文件 {os.path.basename(file_path)} 未检测到任何流")
            return
    
        options = {
            'video': self.extract_video.get(),
            'audio': self.extract_audio.get(),
            'subtitle': self.extract_subtitle.get(),
            'only_first': self.extract_only_first.get(),
            'video_container': self.extract_video_container.get(),
            'audio_format': self.extract_audio_format.get(),
            'subtitle_format': self.extract_subtitle_format.get(),
            'subfolders': self.extract_subfolders.get(),
            'auto_match': self.auto_match_subtitle_ext.get(),
            'auto_match_audio': self.auto_match_audio_ext.get(),
            'keep_chapters': self.extract_keep_chapters.get(),
            'clear_metadata': self.extract_clear_metadata.get(),
        }
    
        if self.extract_custom_dir.get() and self.extract_output_dir.get().strip():
            base_output_dir = self.extract_output_dir.get().strip()
        else:
            base_output_dir = os.path.dirname(file_path)
    
        base = os.path.splitext(os.path.basename(file_path))[0]
        cmd_list_lines = []
    
        # ---- 视频流 ----
        if options['video'] and stream_indices['video']:
            indices = stream_indices['video'][:1] if options['only_first'] else stream_indices['video']
            for idx in indices:
                tags = self._get_stream_tags(file_path, 'video', idx)
                lang = tags.get('language', '')
                title = tags.get('title', '')
                name_suffix = f"_{idx}" if len(indices) > 1 else ""
                if lang:
                    name_suffix += f"_{lang}"
                subdir = "video" if options['subfolders'] else ""
                out_dir = os.path.join(base_output_dir, subdir) if subdir else base_output_dir
                ext = options['video_container']
                out_path = normalize_path(os.path.join(out_dir, f"{base}_video{name_suffix}.{ext}"))
                cmd = [self.ffmpeg_cmd, "-y", "-i", file_path,
                       "-map", f"0:v:{idx}?", "-c:v", "copy"]
                if options.get('keep_chapters', False):
                    cmd.extend(["-map_chapters", "0"])
                if options.get('clear_metadata', False):
                    cmd.extend(["-map_metadata", "-1"])
                else:
                    if lang:
                        cmd.extend(["-metadata:s:0", f"language={lang}"])
                    if title:
                        cmd.extend(["-metadata:s:0", f"title={title}"])
                cmd.append(out_path)
                cmd_list_lines.append(format_cmd_for_display(cmd))
    
        # ---- 音频流 ----
        if options['audio'] and stream_indices['audio']:
            indices = stream_indices['audio'][:1] if options['only_first'] else stream_indices['audio']
            for idx in indices:
                tags = self._get_stream_tags(file_path, 'audio', idx)
                lang = tags.get('language', '')
                title = tags.get('title', '')
                if options.get('auto_match_audio', True):
                    codec = self._get_stream_codec(file_path, 'audio', idx)
                    ext = self._map_audio_codec_to_ext(codec)
                else:
                    ext = options['audio_format']
                if not ext:
                    ext = 'm4a'
                name_suffix = f"_{idx}" if len(indices) > 1 else ""
                if lang:
                    name_suffix += f"_{lang}"
                subdir = "audio" if options['subfolders'] else ""
                out_dir = os.path.join(base_output_dir, subdir) if subdir else base_output_dir
                out_path = normalize_path(os.path.join(out_dir, f"{base}_audio{name_suffix}.{ext}"))
                cmd = [self.ffmpeg_cmd, "-y", "-i", file_path,
                       "-map", f"0:a:{idx}?", "-c:a", "copy"]
                if options.get('keep_chapters', False):
                    cmd.extend(["-map_chapters", "0"])
                if options.get('clear_metadata', False):
                    cmd.extend(["-map_metadata", "-1"])
                else:
                    if lang:
                        cmd.extend(["-metadata:s:0", f"language={lang}"])
                    if title:
                        cmd.extend(["-metadata:s:0", f"title={title}"])
                cmd.append(out_path)
                cmd_list_lines.append(format_cmd_for_display(cmd))
    
        # ---- 字幕流 ----
        if options['subtitle'] and stream_indices['subtitle']:
            indices = stream_indices['subtitle'][:1] if options['only_first'] else stream_indices['subtitle']
            for idx in indices:
                tags = self._get_stream_tags(file_path, 'subtitle', idx)
                lang = tags.get('language', '')
                title = tags.get('title', '')
                if options['auto_match']:
                    codec = self._get_stream_codec(file_path, 'subtitle', idx)
                    ext = self._map_codec_to_ext(codec)
                else:
                    ext = options['subtitle_format']
                if not ext:
                    ext = 'srt'
                name_suffix = f"_{idx}" if len(indices) > 1 else ""
                if lang:
                    name_suffix += f"_{lang}"
                subdir = "subtitle" if options['subfolders'] else ""
                out_dir = os.path.join(base_output_dir, subdir) if subdir else base_output_dir
                out_path = normalize_path(os.path.join(out_dir, f"{base}_sub{name_suffix}.{ext}"))
                cmd = [self.ffmpeg_cmd, "-y", "-i", file_path,
                       "-map", f"0:s:{idx}?", "-c:s", "copy"]
                # 字幕通常不保留章节，但保留元数据清除
                if options.get('clear_metadata', False):
                    cmd.extend(["-map_metadata", "-1"])
                else:
                    if lang:
                        cmd.extend(["-metadata:s:0", f"language={lang}"])
                    if title:
                        cmd.extend(["-metadata:s:0", f"title={title}"])
                cmd.append(out_path)
                cmd_list_lines.append(format_cmd_for_display(cmd))
    
        self.extract_preview_text.delete(1.0, tk.END)
        if not cmd_list_lines:
            self.extract_preview_text.insert(tk.END, f"文件 {os.path.basename(file_path)} 不包含用户勾选的任何流")
        else:
            preview_text = f"--- 预览文件: {os.path.basename(file_path)} ---\n\n"
            preview_text += "\n\n".join(cmd_list_lines)
            self.extract_preview_text.insert(tk.END, preview_text)

    def _on_auto_ext_toggle(self):
        if getattr(self, '_loading_settings', False):
            return
        if self.auto_match_subtitle_ext.get():
            # 禁用字幕格式下拉框，并清空提示（可选）
            self.extract_subtitle_format_combo.config(state='disabled')
            self.extract_subtitle_format.set("")  # 或保留当前值但实际不生效
        else:
            self.extract_subtitle_format_combo.config(state='readonly')
            # 若当前为空，则设置默认值
            if not self.extract_subtitle_format.get():
                self.extract_subtitle_format.set("srt")

    def _on_auto_audio_toggle(self):
        if getattr(self, '_loading_settings', False):
            return
        if self.auto_match_audio_ext.get():
            self.extract_audio_format_combo.config(state='disabled')
            self.extract_audio_format.set("")  # 清空显示，表示自动
        else:
            self.extract_audio_format_combo.config(state='readonly')
            if not self.extract_audio_format.get():
                self.extract_audio_format.set("mka")
        self.save_player_settings()

    def _on_extract_custom_dir_toggle(self):
        if getattr(self, '_loading_settings', False):
            return
        """自定义目录开关切换时，启用/禁用输入框和浏览按钮，并自动保存设置"""
        enabled = self.extract_custom_dir.get()
        state = 'normal' if enabled else 'disabled'
        # 确保控件已创建
        if hasattr(self, 'extract_output_entry') and hasattr(self, 'extract_browse_btn'):
            self.extract_output_entry.config(state=state)
            self.extract_browse_btn.config(state=state)
        # 保存设置（使状态持久化）
        self.save_player_settings()
        self._on_extract_option_changed()



    # ---------- 流提取标签页方法 ----------
    def extract_add_file(self, path=None):
        if path is None:
            paths = filedialog.askopenfilenames(title="选择文件", filetypes=[("所有文件", "*.*")])
            if not paths:
                return
        else:
            paths = [path]
    
        # 批量模式下禁止重绘
        self._batch_update = True
        try:
            for p in paths:
                self._add_file(p)   # 注意 _add_file 内部仍然会刷新，需要改造
        finally:
            self._batch_update = False
            self._refresh_extract_file_list()   # 最终刷新一次
    
    def _add_file(self, path):
        if os.path.isdir(path):
            return
        if path in self.extract_file_list:
            self._append_info_ui(f"[流提取] 文件已在列表中: {os.path.basename(path)}")
            return
        self.extract_file_list.append(path)
        self._refresh_extract_file_list()   # 刷新 Treeview
        self._append_info_ui(f"[流提取] 已添加: {os.path.basename(path)}")
    


    def extract_clear_files(self):
        if self.extract_file_list and messagebox.askyesno("确认", "确定清空所有文件吗？"):
            self.extract_file_list.clear()
            self._stream_info_cache.clear()
            self._refresh_extract_file_list()
            self._append_info_ui("[流提取] 已清空文件列表")
    
    def extract_on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        self._batch_update = True
        try:
            for f in files:
                if os.path.exists(f):
                    self._add_file(f)
        finally:
            self._batch_update = False
            self._refresh_extract_file_list()
        return "break"
    
    def extract_browse_output(self):
        if not self.extract_custom_dir.get():
            return  # 按钮已禁用，实际不会触发
        dirpath = filedialog.askdirectory()
        if dirpath:
            self.extract_output_dir.set(normalize_path(dirpath))
            # 路径变化自动触发保存（已在 trace 中处理，或可在此主动保存）
            self.save_player_settings()
            self._on_extract_option_changed()
    
    def _get_stream_tags(self, file_path: str, stream_type: str, index: int) -> Dict[str, str]:
        data = self._get_stream_data(file_path)
        if not data:
            return {}
        streams = data.get('streams', [])
        count = 0
        for s in streams:
            if s.get('codec_type') == stream_type:
                if count == index:
                    tags = s.get('tags', {})
                    # ------ 新增语言映射 ------
                    if 'language' in tags:
                        raw = tags['language'].lower().strip()
                        tags['language'] = self.LANGUAGE_MAP.get(raw, raw)
                    # --------------------------
                    return tags
                count += 1
        return {}
    
    def _get_stream_data(self, file_path: str) -> Optional[Dict[str, Any]]:
        """获取文件的 ffprobe 流信息（带缓存）"""
        if file_path not in self._stream_info_cache:
            self._stream_info_cache[file_path] = ffprobe_json(self.ffprobe_cmd, file_path)
        return self._stream_info_cache[file_path]
    
    def extract_get_stream_info(self, file_path: str) -> dict:
        data = self._get_stream_data(file_path)
        if not data:
            return {'video': False, 'audio': False, 'subtitle': False}
        streams = data.get('streams', [])
        has_video = any(s.get('codec_type') == 'video' for s in streams)
        has_audio = any(s.get('codec_type') == 'audio' for s in streams)
        has_subtitle = any(s.get('codec_type') == 'subtitle' for s in streams)
        return {'video': has_video, 'audio': has_audio, 'subtitle': has_subtitle}
    
    def extract_get_stream_indices(self, file_path: str) -> dict:
        """
        获取文件中各类型的流索引（该类型在文件中的顺序索引，从0开始）。
        返回: {'video': [0,1,...], 'audio': [0,1,...], 'subtitle': [0,1,...]}
        """
        data = self._get_stream_data(file_path)
        if not data:
            return {'video': [], 'audio': [], 'subtitle': []}
        streams = data.get('streams', [])
        indices = {'video': [], 'audio': [], 'subtitle': []}
        video_count = audio_count = subtitle_count = 0
        for s in streams:
            typ = s.get('codec_type')
            if typ == 'video':
                indices['video'].append(video_count)
                video_count += 1
            elif typ == 'audio':
                indices['audio'].append(audio_count)
                audio_count += 1
            elif typ == 'subtitle':
                indices['subtitle'].append(subtitle_count)
                subtitle_count += 1
        return indices

    def _get_stream_codec(self, file_path: str, stream_type: str, index: int) -> Optional[str]:
        """
        获取指定文件、流类型、类型内索引的编码名称（如 'ass', 'subrip'）。
        返回 None 若找不到。
        """
        data = self._get_stream_data(file_path)
        if not data:
            return None
        streams = data.get('streams', [])
        count = 0
        for s in streams:
            typ = s.get('codec_type')
            if typ == stream_type:
                if count == index:
                    return s.get('codec_name')
                count += 1
        return None

    def _map_codec_to_ext(self, codec_name: Optional[str]) -> str:
        if not codec_name:
            return 'srt'
        mapping = {
            'ass': 'ass', 'ssa': 'ass',
            'subrip': 'srt', 'srt': 'srt',
            'webvtt': 'vtt', 'vtt': 'vtt',
            'mov_text': 'mov_text',
            'dvd_subtitle': 'sup',
            'hdmv_pgs_subtitle': 'sup',
            # 其他可根据需要扩展
        }
        return mapping.get(codec_name, 'srt')

    def _map_audio_codec_to_ext(self, codec_name: Optional[str]) -> str:
        if not codec_name:
            return 'mka'
        mapping = {
            'aac': 'm4a',
            'mp3': 'mp3',
            'mp2': 'mp2',
            'mp1': 'mp3',
            'flac': 'flac',
            'opus': 'opus',
            'vorbis': 'ogg',
            'ac3': 'ac3',
            'eac3': 'eac3',
            'dts': 'dts',
            'pcm_s16le': 'wav',
            'pcm_s24le': 'wav',
            'pcm_s32le': 'wav',
            'alac': 'm4a',
            'libfdk_aac': 'm4a',
            'truehd': 'truehd',  # 或 .mlp
            'mlp': 'mlp',
            'wmav2': 'wma',
            'wmapro': 'wma',
            # 其他常见
        }
        return mapping.get(codec_name, 'mka')


    def _process_send_files_to_queue(self, file_list):
        """
        将指定的文件列表按当前选项发送到任务队列（支持单文件/批量）
        自动添加轨道语言和标题到元数据，文件名中加入语言代码
        """
        if not file_list:
            return
        if not self.extract_video.get() and not self.extract_audio.get() and not self.extract_subtitle.get():
            messagebox.showwarning("提示", "请至少勾选一种流类型")
            return
    
        single_mode = len(file_list) == 1
        if self.extract_custom_dir.get() and self.extract_output_dir.get().strip():
            base_output_dir = self.extract_output_dir.get().strip()
        else:
            base_output_dir = os.path.dirname(file_list[0])
    
        options = {
            'video': self.extract_video.get(),
            'audio': self.extract_audio.get(),
            'subtitle': self.extract_subtitle.get(),
            'only_first': self.extract_only_first.get(),
            'video_container': self.extract_video_container.get(),
            'audio_format': self.extract_audio_format.get(),
            'subtitle_format': self.extract_subtitle_format.get(),
            'subfolders': self.extract_subfolders.get(),
            'auto_match': self.auto_match_subtitle_ext.get(),
            'auto_match_audio': self.auto_match_audio_ext.get(),
            'keep_chapters': self.extract_keep_chapters.get(),
            'clear_metadata': self.extract_clear_metadata.get(),
        }
    
        total_count = 0
        for path in file_list:
            stream_indices = self.extract_get_stream_indices(path)
            if not any(stream_indices.values()):
                self._append_info_ui(f"[流提取] 警告: {os.path.basename(path)} 未检测到任何流，跳过")
                continue
    
            base = os.path.splitext(os.path.basename(path))[0]
    
            # ---- 视频流 ----
            if options['video'] and stream_indices['video']:
                indices = stream_indices['video'][:1] if options['only_first'] else stream_indices['video']
                for idx in indices:
                    tags = self._get_stream_tags(path, 'video', idx)
                    lang = tags.get('language', '')
                    title = tags.get('title', '')
                    name_suffix = f"_{idx}" if len(indices) > 1 else ""
                    if lang:
                        name_suffix += f"_{lang}"
                    subdir = "video" if options['subfolders'] else ""
                    out_dir = os.path.join(base_output_dir, subdir) if subdir else base_output_dir
                    ext = options['video_container']
                    out_path = normalize_path(os.path.join(out_dir, f"{base}_video{name_suffix}.{ext}"))
                    cmd = [self.ffmpeg_cmd, "-y", "-i", path,
                           "-map", f"0:v:{idx}?", "-c:v", "copy"]
                    if options.get('keep_chapters', False):
                        cmd.extend(["-map_chapters", "0"])
                    if options.get('clear_metadata', False):
                        cmd.extend(["-map_metadata", "-1"])
                    else:
                        if lang:
                            cmd.extend(["-metadata:s:0", f"language={lang}"])
                        if title:
                            cmd.extend(["-metadata:s:0", f"title={title}"])
                    cmd.append(out_path)
                    self.add_custom_task(path, out_path, cmd)
                    total_count += 1
    
            # ---- 音频流 ----
            if options['audio'] and stream_indices['audio']:
                indices = stream_indices['audio'][:1] if options['only_first'] else stream_indices['audio']
                for idx in indices:
                    tags = self._get_stream_tags(path, 'audio', idx)
                    lang = tags.get('language', '')
                    title = tags.get('title', '')
                    if options.get('auto_match_audio', True):
                        codec = self._get_stream_codec(path, 'audio', idx)
                        ext = self._map_audio_codec_to_ext(codec)
                    else:
                        ext = options['audio_format']
                    if not ext:
                        ext = 'mka'
                    name_suffix = f"_{idx}" if len(indices) > 1 else ""
                    if lang:
                        name_suffix += f"_{lang}"
                    subdir = "audio" if options['subfolders'] else ""
                    out_dir = os.path.join(base_output_dir, subdir) if subdir else base_output_dir
                    out_path = normalize_path(os.path.join(out_dir, f"{base}_audio{name_suffix}.{ext}"))
                    cmd = [self.ffmpeg_cmd, "-y", "-i", path,
                           "-map", f"0:a:{idx}?", "-c:a", "copy"]
                    if options.get('keep_chapters', False):
                        cmd.extend(["-map_chapters", "0"])
                    if options.get('clear_metadata', False):
                        cmd.extend(["-map_metadata", "-1"])
                    else:
                        if lang:
                            cmd.extend(["-metadata:s:0", f"language={lang}"])
                        if title:
                            cmd.extend(["-metadata:s:0", f"title={title}"])
                    cmd.append(out_path)
                    self.add_custom_task(path, out_path, cmd)
                    total_count += 1
    
            # ---- 字幕流 ----
            if options['subtitle'] and stream_indices['subtitle']:
                indices = stream_indices['subtitle'][:1] if options['only_first'] else stream_indices['subtitle']
                for idx in indices:
                    tags = self._get_stream_tags(path, 'subtitle', idx)
                    lang = tags.get('language', '')
                    title = tags.get('title', '')
                    if options['auto_match']:
                        codec = self._get_stream_codec(path, 'subtitle', idx)
                        ext = self._map_codec_to_ext(codec)
                    else:
                        ext = options['subtitle_format']
                    if not ext:
                        ext = 'srt'
                    name_suffix = f"_{idx}" if len(indices) > 1 else ""
                    if lang:
                        name_suffix += f"_{lang}"
                    subdir = "subtitle" if options['subfolders'] else ""
                    out_dir = os.path.join(base_output_dir, subdir) if subdir else base_output_dir
                    out_path = normalize_path(os.path.join(out_dir, f"{base}_sub{name_suffix}.{ext}"))
                    cmd = [self.ffmpeg_cmd, "-y", "-i", path,
                           "-map", f"0:s:{idx}?", "-c:s", "copy"]
                    if options.get('clear_metadata', False):
                        cmd.extend(["-map_metadata", "-1"])
                    else:
                        if lang:
                            cmd.extend(["-metadata:s:0", f"language={lang}"])
                        if title:
                            cmd.extend(["-metadata:s:0", f"title={title}"])
                    cmd.append(out_path)
                    self.add_custom_task(path, out_path, cmd)
                    total_count += 1
    
        if total_count == 0:
            if single_mode:
                self._append_info_ui(f"[流提取] 文件 {os.path.basename(file_list[0])} 不包含用户勾选的任何流")
            else:
                self._append_info_ui("[流提取] 未添加任何任务，请检查文件是否包含所勾选的流类型")
        else:
            if single_mode:
                self._append_info_ui(f"[流提取] 已为 {os.path.basename(file_list[0])} 添加 {total_count} 个任务到队列")
            else:
                self._append_info_ui(f"[流提取] 共添加 {total_count} 个提取任务到队列")
        self.update_task_list()

    def extract_add_to_queue(self):
        if not self.extract_file_list:
            messagebox.showwarning("提示", "文件列表为空")
            return
        self._process_send_files_to_queue(self.extract_file_list)
    
    def _extract_send_single_to_queue(self, file_path):
        self._process_send_files_to_queue([file_path])
    
    def extract_preview_command(self):
        children = self.extract_tree.get_children()
        if not children:
            self.extract_preview_text.delete(1.0, tk.END)
            self.extract_preview_text.insert(tk.END, "文件列表为空")
            return
        first_path = self.extract_tree.item(children[0], "values")[1]
    
        # 确定输出目录（与队列逻辑一致）
        if self.extract_custom_dir.get() and self.extract_output_dir.get().strip():
            base_output_dir = self.extract_output_dir.get().strip()
        else:
            base_output_dir = os.path.dirname(first_path)
    
        stream_indices = self.extract_get_stream_indices(first_path)
        if not any(stream_indices.values()):
            self.extract_preview_text.delete(1.0, tk.END)
            self.extract_preview_text.insert(tk.END, "该文件未检测到任何流，无法预览命令")
            return
    
        options = {
            'video': self.extract_video.get(),
            'audio': self.extract_audio.get(),
            'subtitle': self.extract_subtitle.get(),
            'only_first': self.extract_only_first.get(),
            'video_container': self.extract_video_container.get(),
            'audio_format': self.extract_audio_format.get(),
            'subtitle_format': self.extract_subtitle_format.get(),
            'subfolders': self.extract_subfolders.get(),
        }
    
        cmd = [self.ffmpeg_cmd, "-y", "-i", first_path]
        base = os.path.splitext(os.path.basename(first_path))[0]
    
        # 预览仅展示第一个文件的第一条流（若存在）
        if options['video'] and stream_indices['video']:
            idx = stream_indices['video'][0]
            sub = "video/" if options['subfolders'] else ""
            out_path = normalize_path(os.path.join(base_output_dir, sub, f"{base}_video_{idx}.{options['video_container']}"))
            cmd.extend(["-map", f"0:v:{idx}?", "-c:v", "copy", out_path])
    
        if options['audio'] and stream_indices['audio']:
            idx = stream_indices['audio'][0]
            sub = "audio/" if options['subfolders'] else ""
            out_path = normalize_path(os.path.join(base_output_dir, sub, f"{base}_audio_{idx}.{options['audio_format']}"))
            cmd.extend(["-map", f"0:a:{idx}?", "-c:a", "copy", out_path])
    
        if options['subtitle'] and stream_indices['subtitle']:
            idx = stream_indices['subtitle'][0]
            # 确定扩展名（预览也使用自动匹配逻辑）
            if self.auto_match_subtitle_ext.get():
                codec = self._get_stream_codec(first_path, 'subtitle', idx)
                ext = self._map_codec_to_ext(codec)
            else:
                ext = options['subtitle_format']
            if not ext:
                ext = 'srt'
            sub = "subtitle/" if options['subfolders'] else ""
            out_path = normalize_path(os.path.join(base_output_dir, sub, f"{base}_sub_{idx}.{ext}"))
            cmd.extend(["-map", f"0:s:{idx}?", "-c:s", "copy", out_path])
    
        if len(cmd) == 3:  # 只有 ffmpeg -y -i file
            cmd_str = "文件不包含用户勾选的任何流类型，无法生成预览命令"
        else:
            cmd_str = format_cmd_for_display(cmd)
    
        self.extract_preview_text.delete(1.0, tk.END)
        self.extract_preview_text.insert(tk.END, cmd_str)
    


    # -------------------- 界面创建 --------------------
    def create_widgets(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)
    
        self.main_paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)
    
        # ======== 左侧容器 ========
        base_width = int(1155 * self.scaling)
        left_container = ttk.Frame(self.main_paned, width=base_width)
        left_container.pack_propagate(False)
        self.left_container = left_container
        self.main_paned.add(left_container, weight=1)
  
        # ======== 左侧所有内容 ========
        left_vpane = ttk.PanedWindow(left_container, orient=tk.VERTICAL)
        left_vpane.pack(fill=tk.BOTH, expand=True)
        self.notebook = ttk.Notebook(left_vpane)
        left_vpane.add(self.notebook, weight=1)
    
        # ---- 视频转码标签页 ----
        transcode_tab = ttk.Frame(self.notebook)
        self.notebook.add(transcode_tab, text="视频转码")
        transcode_vpane = ttk.Frame(transcode_tab)
        transcode_vpane.pack(fill=tk.BOTH, expand=True)
    
        settings_frame = ttk.Frame(transcode_vpane)
        settings_frame.pack(side=tk.TOP, fill=tk.X, expand=False, pady=(0,5))
    
        # 输入/输出框架
        io_frame = ttk.LabelFrame(settings_frame, text="输入 / 输出", padding="5")
        io_frame.pack(fill=tk.X, pady=5)
        io_frame.columnconfigure(1, weight=1)
    
        ttk.Label(io_frame, text="输入文件:").grid(row=0, column=0, sticky="w")
        self.input_entry = ttk.Entry(io_frame, textvariable=self.input_file)
        self.input_entry.grid(row=0, column=1, padx=5, sticky="ew")
        if DND_AVAILABLE:
            self.input_entry.drop_target_register(DND_FILES)
            self.input_entry.dnd_bind('<<Drop>>', self.on_input_drop)
        ttk.Button(io_frame, text="浏览", command=self.select_input).grid(row=0, column=2)
        ttk.Button(io_frame, text="添加到任务列表", command=self.add_current_as_task).grid(row=0, column=3, padx=5)
    
        ttk.Label(io_frame, text="输出目录:").grid(row=1, column=0, sticky="w")
        self.output_entry = ttk.Entry(io_frame, textvariable=self.output_dir)
        self.output_entry.grid(row=1, column=1, padx=5, sticky="ew")
        if DND_AVAILABLE:
            self.output_entry.drop_target_register(DND_FILES)
            self.output_entry.dnd_bind('<<Drop>>', self.on_output_drop)
        ttk.Button(io_frame, text="浏览", command=self.select_output_dir).grid(row=1, column=2)
        ttk.Button(io_frame, text="清空", command=self.clear_input_output, width=12).grid(row=1, column=3, padx=5)
    
        suffix_frame = ttk.Frame(io_frame)
        suffix_frame.grid(row=2, column=0, columnspan=4, sticky="w", pady=2)
        ttk.Label(suffix_frame, text="输出文件名后缀 (如 _new):").pack(side=tk.LEFT)
        ttk.Entry(suffix_frame, textvariable=self.output_suffix, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Label(suffix_frame, text="完整自定义名称 (覆盖后缀):").pack(side=tk.LEFT, padx=(20,0))
        ttk.Entry(suffix_frame, textvariable=self.custom_output_name, width=30).pack(side=tk.LEFT, padx=5)
        ttk.Label(suffix_frame, text="输出容器:").pack(side=tk.LEFT, padx=(20,0))
        container_combo = ttk.Combobox(suffix_frame, textvariable=self.output_container,
                                       values=["mp4", "mkv", "mov", "avi", "webm","gif","webp"], state="readonly", width=6)
        container_combo.pack(side=tk.LEFT, padx=5)
    
        # 预设框架
        preset_frame = ttk.LabelFrame(settings_frame, text="参数预设", padding="5")
        preset_frame.pack(fill=tk.X, pady=(0,5))
        ttk.Label(preset_frame, text="预设名称:").pack(side=tk.LEFT)
        self.preset_name = tk.StringVar()
        self.preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_name, width=25, height=20, state="readonly")
        self.preset_combo.pack(side=tk.LEFT, padx=5)
        self.preset_combo.bind("<<ComboboxSelected>>", lambda e: self.load_preset(self.preset_name.get()))
        btn_save = ttk.Button(preset_frame, text="保存当前参数为预设", command=self.save_preset)
        btn_save.pack(side=tk.LEFT, padx=5)
        btn_delete = ttk.Button(preset_frame, text="删除预设", command=self.delete_preset)
        btn_delete.pack(side=tk.LEFT, padx=5)
        btn_export = ttk.Button(preset_frame, text="导出所有预设(备份)", command=self.export_all_presets)
        btn_export.pack(side=tk.LEFT, padx=5)
        btn_import = ttk.Button(preset_frame, text="导入预设(恢复)", command=self.import_presets)
        btn_import.pack(side=tk.LEFT, padx=5)
    
        # 参数笔记本
        param_notebook = ttk.Notebook(settings_frame)
        param_notebook.pack(fill=tk.BOTH, expand=True, pady=5)
    
        # 视频编码页
        video_enc_page = ttk.Frame(param_notebook)
        param_notebook.add(video_enc_page, text="视频编码")
        self.video_encoder = VideoEncoderFrame(video_enc_page, app=self, refresh_callback=self.update_command_preview)
        self.video_encoder.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
        # 视频滤镜页
        filter_page = ttk.Frame(param_notebook)
        param_notebook.add(filter_page, text="视频滤镜")
        self.video_filter = VideoFilterFrame(filter_page, app=self)
        self.video_filter.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
        # 音频页
        audio_page = ttk.Frame(param_notebook)
        param_notebook.add(audio_page, text="音频")
        self.audio_frame = AudioFrame(audio_page, enable_checkbox=True)
        self.audio_frame.pack(fill=tk.X, padx=5, pady=5)
    
        # 截取片段页
        trim_page = ttk.Frame(param_notebook)
        param_notebook.add(trim_page, text="截取片段")
        self.trim_frame = TrimFrame(trim_page, update_callback=self.update_command_preview)
        self.trim_frame.pack(fill=tk.X, padx=5, pady=5)
    
        # 分段拼接页
        segment_tab = ttk.Frame(param_notebook)
        param_notebook.add(segment_tab, text="分段拼接")
        seg_control_frame = ttk.Frame(segment_tab)
        seg_control_frame.pack(fill=tk.X, pady=10)
        ttk.Checkbutton(seg_control_frame, text="启用分段拼接模式 (将忽略『截取片段』设置)",
                        variable=self.segment_enabled).pack(side=tk.LEFT, padx=5)
        ttk.Button(seg_control_frame, text="打开分段设置...",
                   command=self.open_segment_editor).pack(side=tk.LEFT, padx=10)
        ttk.Label(segment_tab, text="勾选启用后，视频将按片段列表裁剪并拼接，所有片段使用相同的全局编码/滤镜设置。\n\n"
                                   "   建议使用（mpv、PotPlayer）等播放器打开视频，定位并获取精确到毫秒的时间。\n\n"
                                   "   典型用途：简单混剪、去中间广告、提取精华片段等。",
                  foreground="grey", wraplength=1100, justify=tk.LEFT).pack(anchor=tk.W, padx=10, pady=(5,0))
    
        # 高级选项页
        adv_page = ttk.Frame(param_notebook)
        param_notebook.add(adv_page, text="高级选项")
        self.adv_frame = AdvancedFrame(adv_page, update_callback=self.update_command_preview, app=self)
        self.adv_frame.pack(fill=tk.X, padx=5, pady=5)
    
        # 底部按钮
        bottom_btn_frame = ttk.Frame(settings_frame)
        bottom_btn_frame.pack(fill=tk.X, pady=(0,5))
        btn_height = 1 if self.scaling >= 1.4 else 2
    
        btn_single = tk.Button(bottom_btn_frame, text="开始编码", command=self.transcode_single,
                               height=btn_height, width=18, relief=tk.RAISED,
                               bg="#4CAF50", fg="white", font=("",12,"bold"))
        btn_single.pack(side=tk.LEFT, padx=5, pady=5)
    
        btn_preview = tk.Button(bottom_btn_frame, text="预览当前命令", command=self.preview_current_file,
                                height=btn_height, width=18, relief=tk.RAISED,
                                bg="#2196F3", fg="white", font=("",12,"bold"))
        btn_preview.pack(side=tk.LEFT, padx=5, pady=5)
    
        btn_refresh = tk.Button(bottom_btn_frame, text="刷新命令", command=self.refresh_with_reset,
                                height=btn_height, width=12, relief=tk.RAISED)
        btn_refresh.pack(side=tk.LEFT, padx=5, pady=5)
        ToolTip(btn_refresh, "刷新命令或重置队列区列宽")
    
        btn1_copy = tk.Button(bottom_btn_frame, text="复制命令", command=self.copy_command,
                              height=btn_height, width=12, relief=tk.RAISED)
        btn1_copy.pack(side=tk.LEFT, padx=5)
    
        # 命令预览
        if DND_AVAILABLE:
            preview_label_text = "当前命令模板 - 拖拽文件可以按当前模板添加到队列"
        else:
            preview_label_text = "当前命令模板"
        preview_frame = ttk.LabelFrame(settings_frame, text=preview_label_text, padding="1")
        preview_frame.pack(fill=tk.X, pady=0)
        self.cmd_preview = scrolledtext.ScrolledText(preview_frame, height=4, wrap=tk.WORD, font=("Microsoft YaHei",9))
        self.cmd_preview.pack(fill=tk.BOTH, expand=True, padx=(4,0))
        self.cmd_preview.insert(tk.END, "请选择输入文件，或调整参数...")
    
        # 任务列表区域
        tasks_frame = ttk.Frame(transcode_vpane)
        tasks_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 0))
    
        # 工具栏（水平滚动）
        toolbar_height = max(20, int(30 * self.scaling))
        tool_canvas = tk.Canvas(tasks_frame, height=toolbar_height, highlightthickness=0)
        tool_canvas.pack(side=tk.TOP, fill=tk.X, pady=(0, 2))
        h_scrollbar = ttk.Scrollbar(tasks_frame, orient=tk.HORIZONTAL, command=tool_canvas.xview)
        h_scrollbar.pack(side=tk.TOP, fill=tk.X)
        tool_canvas.configure(xscrollcommand=h_scrollbar.set)
        tool_container = ttk.Frame(tool_canvas)
        tool_canvas.create_window((0, 0), window=tool_container, anchor='nw')
        def configure_tool_canvas(event):
            tool_canvas.configure(scrollregion=tool_canvas.bbox('all'))
        tool_container.bind('<Configure>', configure_tool_canvas)
    
        btn_start = tk.Button(tool_container, text="开始队列", command=self.start_queue,
                              bg="#4CAF50", fg="white", width=12, relief=tk.RAISED)
        btn_start.pack(side=tk.LEFT, padx=5)
    
        label_parallel = ttk.Label(tool_container, text="并行任务:")
        label_parallel.pack(side=tk.LEFT, padx=(10, 2))
        ToolTip(label_parallel, "同时运行的任务数量，建议不超过3以避免资源过度占用")
        self.max_parallel = tk.IntVar(value=1)
        self.parallel_spin = ttk.Spinbox(tool_container, from_=1, to=5, width=3,
                                         textvariable=self.max_parallel, state="readonly")
        self.parallel_spin.pack(side=tk.LEFT, padx=2)
    
        label_hw = ttk.Label(tool_container, text="硬编并发限制:")
        label_hw.pack(side=tk.LEFT, padx=(10, 2))
        ToolTip(label_hw, "同时进行的硬件编码〔NVENC/QSV/AMF等〕任务的最大数量，推荐不超过2，显存里可能数据打架")
        self.max_hw_parallel = tk.IntVar(value=2)
        self.max_hw_spin = ttk.Spinbox(tool_container, from_=1, to=4, width=3,
                                       textvariable=self.max_hw_parallel, state="readonly")
        self.max_hw_spin.pack(side=tk.LEFT, padx=2)
    
        for text, cmd in [("移除选中任务", self.remove_selected_tasks),
                          ("清空全部任务", self.clear_all_tasks),
                          ("清空已完成/失败任务", self.clear_finished_tasks),
                          ("停止队列", self.stop_queue),
                          ("导出为脚本", self.export_script),
                          ("预览选中任务", self.preview_selected_task)]:
            ttk.Button(tool_container, text=text, command=cmd).pack(side=tk.LEFT, padx=5)
    
        # 任务列表 Treeview
        list_container = ttk.Frame(tasks_frame)
        list_container.pack(fill=tk.BOTH, expand=True, padx=(5,0), pady=(0, 0))
    
        Batch_style = ttk.Style()
        Batch_style.configure("Batch.Treeview", background="#f0f0f0", fieldbackground="#f0f0f0", rowheight=int(22 * self.scaling))
        Batch_style.configure("Batch.Treeview.Heading", background="#d9d9d9")
    
        columns = ("序号", "文件名", "输出路径", "命令 (简洁) 双击编辑", "状态", "错误信息")
        self.task_tree = ttk.Treeview(list_container, columns=columns, show="headings",
                                       height=8, style="Batch.Treeview")
        self.task_tree.heading("序号", text="序号")
        self.task_tree.heading("文件名", text="文件名")
        self.task_tree.heading("输出路径", text="输出路径")
        self.task_tree.heading("命令 (简洁) 双击编辑", text="命令 (简洁) 双击编辑")
        self.task_tree.heading("状态", text="状态")
        self.task_tree.heading("错误信息", text="错误信息")
        self.task_tree.column("序号", width=25, minwidth=20)
        self.task_tree.column("文件名", width=75, minwidth=20)
        self.task_tree.column("输出路径", width=100, minwidth=20)
        self.task_tree.column("命令 (简洁) 双击编辑", width=410, minwidth=20)
        self.task_tree.column("状态", width=72, minwidth=20)
        self.task_tree.column("错误信息", width=30, minwidth=20)
        self.task_tree.tag_configure('odd', background='#e8e8e8')
        self.task_tree.tag_configure('even', background='#ffffff')
    
        vbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=vbar.set)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.task_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
        self.task_tree.bind("<Double-1>", self.on_task_double_click)
    
        # ---- 合并标签页 ----
        merge_tab = ttk.Frame(self.notebook)
        self.notebook.add(merge_tab, text="封装/合并/画中画")
        self.create_merge_tab(merge_tab)
    
        # ---- 流提取标签页 ----
        extract_tab = ttk.Frame(self.notebook)
        self.notebook.add(extract_tab, text="流提取")
        self.create_extract_tab(extract_tab)
    
        # ---- 信息与播放器标签页 ----
        player_tab = ttk.Frame(self.notebook)
        self.notebook.add(player_tab, text="信息与播放器")
        self.create_player_settings_tab(player_tab)
    
        # ======== 右侧容器 ========
        right_panel = ttk.Frame(self.main_paned)
        self.main_paned.add(right_panel, weight=1)
        self.right_panel = right_panel
    

        self._sash_set = False
        
        def _delayed_set_sash():
            if self._sash_set:
                return
            self.main_paned.update_idletasks()
            total = self.main_paned.winfo_width()
            if total <= 1:
                # 窗口还没准备好，100ms 后再试
                self.main_paned.after(100, _delayed_set_sash)
                return
            # 目标：右边占 30%（sash 在 70% 位置）
            target = int(total * 0.7)
            # 保险：即使计算出来很小，sash 也至少留出 260px 给左边
            target = max(target, 260)
            self.main_paned.sashpos(0, target)
            self._sash_set = True
            # 恢复自适应，让左侧面板可以随窗口缩放正常调整
            left_container.pack_propagate(True)
        
        # 双保险触发：idle 后立即执行，如果 missed 再用 after
        self.main_paned.after_idle(_delayed_set_sash)
        self.main_paned.after(300, _delayed_set_sash)
    
    
        # 关键信息日志区
        info_frame = ttk.LabelFrame(right_panel, text="关键信息", padding="1")
        info_frame.pack(fill=tk.BOTH, expand=True, pady=(0,5))
        info_top = ttk.Frame(info_frame)
        info_top.pack(fill=tk.X, pady=(0,2))
        ttk.Button(info_top, text="清空日志", command=lambda: self.info_text.delete(1.0, tk.END)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(info_top, text="保存日志", command=lambda: self.save_log(self.info_text)).pack(side=tk.RIGHT, padx=2)
        self.info_text = scrolledtext.ScrolledText(info_frame, bg='#EAF4FC', fg='black',
                                                   selectbackground='#CCF09C', selectforeground='black',
                                                   font=("Microsoft YaHei",9,"normal"), wrap=tk.WORD)
        self.info_text.pack(fill=tk.BOTH, expand=True)
    
        # 转换进程信息日志区
        detail_frame = ttk.LabelFrame(right_panel, text="转换进程信息", padding="1")
        detail_frame.pack(fill=tk.BOTH, expand=True)
        detail_top = ttk.Frame(detail_frame)
        detail_top.pack(fill=tk.X, pady=(0,2))
        ttk.Button(detail_top, text="清空日志", command=lambda: self.detail_text.delete(1.0, tk.END)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(detail_top, text="保存日志", command=lambda: self.save_log(self.detail_text)).pack(side=tk.RIGHT, padx=2)
        self.detail_text = scrolledtext.ScrolledText(detail_frame, bg='#EAF4FC', fg='black',
                                                     selectbackground='#CCF09C', selectforeground='black',
                                                     font=("Microsoft YaHei",8,"normal"), wrap=tk.WORD)
        self.detail_text.pack(fill=tk.BOTH, expand=True)
    
        # 绑定各种控件刷新命令预览
        self.video_encoder.vcodec.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.rate_control_type.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.crf_value.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.cq_value.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.global_quality.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.bitrate_video.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.preset.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.frame_rate_type.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.frame_rate_custom.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.scale_enabled.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.scale_width.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.scale_height.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.scale_method.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.crop_enabled.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.crop_left.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.crop_top.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.crop_width.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.crop_height.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.rotate.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.vflip.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.hflip.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.speed_enabled.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.speed_factor.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.deinterlace_filter.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.pix_fmt_enabled.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.pix_fmt.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.subtitle_enabled.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.subtitle_path.trace_add("write", lambda *a: self.update_command_preview())
        self.video_filter.reverse_enabled.trace_add("write", lambda *a: self.update_command_preview())
        self.audio_frame.audio_enabled.trace_add("write", lambda *a: self.update_command_preview())
        self.audio_frame.audio_codec.trace_add("write", lambda *a: self.update_command_preview())
        self.audio_frame.audio_bitrate.trace_add("write", lambda *a: self.update_command_preview())
        self.audio_frame.audio_samplerate.trace_add("write", lambda *a: self.update_command_preview())
        self.audio_frame.volume_value.trace_add("write", lambda *a: self.update_command_preview())
        self.audio_frame.volume_enabled.trace_add("write", lambda *a: self.update_command_preview())
        self.trim_frame.trim_enabled.trace_add("write", lambda *a: self.update_command_preview())
        self.trim_frame.trim_start.trace_add("write", lambda *a: self.update_command_preview())
        self.trim_frame.trim_end.trace_add("write", lambda *a: self.update_command_preview())
        self.trim_frame.precise_trim.trace_add("write", lambda *a: self.update_command_preview())
        self.adv_frame.hwaccel_enabled.trace_add("write", lambda *a: self.update_command_preview())
        self.adv_frame.hwaccel_decoder.trace_add("write", lambda *a: self.update_command_preview())
        self.adv_frame.custom_args.trace_add("write", lambda *a: self.update_command_preview())
        self.audio_frame.only_audio.trace_add("write", lambda *a: self.update_command_preview())
        self.audio_frame.audio_format.trace_add("write", lambda *a: self.update_command_preview())
        self.output_dir.trace_add("write", lambda *a: self.update_command_preview())
        self.output_suffix.trace_add("write", lambda *a: self.update_command_preview())
        self.custom_output_name.trace_add("write", lambda *a: self.update_command_preview())
        self.output_container.trace_add("write", lambda *a: self.update_command_preview())
        self.audio_frame.only_audio.trace_add("write", lambda *a: self.toggle_only_audio_mode())

        self.video_encoder.tune_var.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.profile_var.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.level_var.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.maxrate_var.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.bufsize_var.trace_add("write", lambda *a: self.update_command_preview())

        self.segment_enabled.trace_add("write", lambda *a: self.update_command_preview())
    
        self._update_preview_edit_state()
        self._initialized = True


class EditSegmentDialog(simpledialog.Dialog):
    """用于编辑片段的起始时间、结束时间和翻转"""
    def __init__(self, parent, title, start, end, flip):
        self.start = start
        self.end = end
        self.flip = flip
        super().__init__(parent, title=title)

    def body(self, master):
        ttk.Label(master, text="开始时间:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.start_entry = ttk.Entry(master, width=15)
        self.start_entry.grid(row=0, column=1, padx=5, pady=5)
        self.start_entry.insert(0, self.start)

        ttk.Label(master, text="结束时间:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.end_entry = ttk.Entry(master, width=15)
        self.end_entry.grid(row=1, column=1, padx=5, pady=5)
        self.end_entry.insert(0, self.end)

        ttk.Label(master, text="翻转:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.flip_var = tk.StringVar(value=self.flip)
        self.flip_combo = ttk.Combobox(master, textvariable=self.flip_var,
                                       values=["无", "水平翻转", "垂直翻转", "水平+垂直"],
                                       state="readonly", width=12)
        self.flip_combo.grid(row=2, column=1, padx=5, pady=5)

        return self.start_entry

    def apply(self):
        self.start = self.start_entry.get().strip()
        self.end = self.end_entry.get().strip()
        self.flip = self.flip_var.get()

class SegmentEditor:
    """分段拼接设置窗口"""
    def __init__(self, parent, segments, app):
        self.parent = parent
        self.app = app          # 主程序引用，用于获取时长等信息
        self.segments = copy.deepcopy(segments)  # 深拷贝，独立修改
        self.result = None      # 返回结果

        self.window = tk.Toplevel(parent)
        self.window.title("分段拼接设置")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.geometry("900x600")
        center_window(self.window, 900, 600)

        self.create_widgets()
        self.refresh_tree()
        self.window.protocol("WM_DELETE_WINDOW", self.on_cancel)

    # ---------- 界面创建 ----------
    def create_widgets(self):
        main = ttk.Frame(self.window, padding="10")
        main.pack(fill=tk.BOTH, expand=True)

        paned = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # ---- 左栏：片段列表 ----
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=3)

        tool_frame = ttk.Frame(left_frame)
        tool_frame.pack(fill=tk.X, pady=2)

        ttk.Label(tool_frame, text="开始:").pack(side=tk.LEFT)
        self.start_entry = ttk.Entry(tool_frame, width=12)
        self.start_entry.pack(side=tk.LEFT, padx=2)
        self.start_entry.insert(0, "0")

        ttk.Label(tool_frame, text="结束:").pack(side=tk.LEFT, padx=(10,0))
        self.end_entry = ttk.Entry(tool_frame, width=12)
        self.end_entry.pack(side=tk.LEFT, padx=2)

        flip_label = ttk.Label(tool_frame, text="翻转:")
        flip_label.pack(side=tk.LEFT, padx=(10,0))
        ToolTip(flip_label, 
                "此翻转仅作用于当前选中的片段内部（水平/垂直翻转）\n"
                "不影响主界面「视频滤镜」中的全局旋转/翻转设置。",
                wraplength=400)

        self.flip_var = tk.StringVar(value="无")
        self.flip_combo = ttk.Combobox(tool_frame, textvariable=self.flip_var,
                                       values=["无", "水平翻转", "垂直翻转", "水平+垂直"],
                                       state="readonly", width=12)
        self.flip_combo.pack(side=tk.LEFT, padx=2)

        ttk.Button(tool_frame, text="添加片段", command=self.add_segment).pack(side=tk.LEFT, padx=5)

        # 表格
        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ("序号", "开始", "结束", "时长", "翻转")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=8)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100, minwidth=60)
        self.tree.column("序号", width=50)
        self.tree.column("翻转", width=100)

        vbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)

        op_frame = ttk.Frame(left_frame)
        op_frame.pack(fill=tk.X, pady=2)
        ttk.Button(op_frame, text="删除选中", command=self.delete_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(op_frame, text="上移", command=self.move_up).pack(side=tk.LEFT, padx=2)
        ttk.Button(op_frame, text="下移", command=self.move_down).pack(side=tk.LEFT, padx=2)
        ttk.Button(op_frame, text="清空所有", command=self.clear_all).pack(side=tk.LEFT, padx=2)

        # ---- 右栏：外部命令输入 ----
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)

        cmd_frame = ttk.LabelFrame(right_frame, text="输入外部命令或时间 - 提示", padding="5")
        cmd_frame.pack(fill=tk.BOTH, expand=True)

        ToolTip(cmd_frame,
                "在此粘贴 FFmpeg 截取命令（每行一条），程序自动提取 -ss 和 -t/-to 时间参数。\n\n"
                "支持的格式：\n"
                "• 单 -ss + -to/-t：\n"
                "    -ss 10.5 -to 20.3\n"
                "    -ss 00:01:30 -t 5\n"
                "• 双 -ss（组合跳转）：提取最后一个 -ss 与 -to/-t 组合\n"
                "    -ss 5 -i input.mp4 -ss 10 -to 15\n\n"
                "时间格式：秒数（如 10.5）或 HH:MM:SS.ms\n\n"
                "不支持解析：\n"
                "• -vf 或 -filter_complex 中的 trim 滤镜参数\n"
                "• -ss 出现在 -i 之后且不带 -to/-t（无法确定结束时间）\n\n"
                "提示：此为高级功能，普通用户可直接在左侧手动添加片段。\n"
                "每行以 # 开头的行将被忽略。",
                wraplength=500
        )

        self.cmd_input = scrolledtext.ScrolledText(cmd_frame, height=15, wrap=tk.NONE,
                                                   font=("Consolas", 9))
        self.cmd_input.pack(fill=tk.BOTH, expand=True, pady=5)

        cmd_btn_frame = ttk.Frame(cmd_frame)
        cmd_btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(cmd_btn_frame, text="解析并导入所有片段", command=self.import_from_commands).pack(side=tk.LEFT, padx=2)
        ttk.Button(cmd_btn_frame, text="清空输入", command=lambda: self.cmd_input.delete(1.0, tk.END)).pack(side=tk.LEFT, padx=2)

        # ---- 底部按钮 ----
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=10)
        
        label = tk.Label(btn_frame, text="分段切割:", fg="blue", font=("", 10, "bold"))
        label.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(label,
                "额外功能：生成可执行的 FFmpeg 分段切割脚本，或直接发送到任务队列。\n"
                "• 快速 (copy)：流复制截取，不重新编码，速度极快。\n"
                "      流复制截取的片段不准确，适合作为预处理片段，或者无所谓精确的存档。\n"
                "• 精确 (含滤镜)：应用主界面全部滤镜设置，需重新编码，帧级精准。\n"
                "两种模式均可：\n"
                "  - 导出脚本：保存为 .bat/.sh 文件，手动运行。\n"
                "  - 发送到队列：自动添加到任务列表，一键执行。\n"
                "发送到队列/导出脚本的精确模式会弹出选择框，让您决定使用 trim 滤镜还是双 -ss（组合跳转）加速。\n"
                "双 -ss 适合长视频，能显著提升截取速度。\n"
                "输出文件自动命名为：原文件名_seg序号.mp4。",
                wraplength=800
        )


        ttk.Label(btn_frame, text="发送到队列").pack(side=tk.LEFT, padx=(10, 5))
        ttk.Button(btn_frame, text="快速", command=self.send_quick_to_queue, width=6).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="精确", command=self.send_precise_to_queue, width=6).pack(side=tk.LEFT, padx=5)

        ttk.Label(btn_frame, text=" 导出为脚本").pack(side=tk.LEFT, padx=(10, 5))
        quick_btn = ttk.Button(btn_frame, text="快速", command=self.export_quick_script, width=6)
        quick_btn.pack(side=tk.LEFT, padx=5)
        precise_btn = ttk.Button(btn_frame, text="精确", command=self.export_precise_script, width=6)
        precise_btn.pack(side=tk.LEFT, padx=5)



        ttk.Button(btn_frame, text="取消", command=self.on_cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="确定", command=self.on_ok).pack(side=tk.RIGHT, padx=5)


        self.window.after(100, lambda: self._set_initial_pane_size(paned))

    def _set_initial_pane_size(self, paned):
        total_width = self.window.winfo_width()
        if total_width > 100:
            paned.sashpos(0, int(total_width * 0.75))

        # 绑定双击编辑
        self.tree.bind("<Double-1>", self.on_tree_double_click)


    def send_quick_to_queue(self):
        input_file = self.app.input_file.get().strip()
        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("错误", "请先在主界面选择输入文件")
            return
        if not self.segments:
            messagebox.showinfo("提示", "片段列表为空")
            return
    
        # 获取完整设置，并强制为 copy 模式
        base_settings = self.app.get_current_settings()
        base_settings.pop("watermark", None)          # 移除水印
        base_settings["encoder"] = "copy"             # 强制流复制
        # 禁用所有可能影响 copy 的滤镜
        base_settings["scale_enabled"] = False
        base_settings["crop_enabled"] = False
        base_settings["rotate"] = "none"
        base_settings["vflip"] = False
        base_settings["hflip"] = False
        base_settings["subtitle_enabled"] = False
        base_settings["pix_fmt_enabled"] = False
        base_settings["speed_enabled"] = False
        base_settings["reverse_enabled"] = False
        base_settings["audio_codec"] = "copy"         # 音频也复制
        base_settings["audio_enabled"] = True
    
        output_dir = self.app.output_dir.get().strip()
        if not output_dir or not os.path.exists(output_dir):
            output_dir = os.path.dirname(input_file)
        basename = os.path.splitext(os.path.basename(input_file))[0]
        container = base_settings.get("output_container", "mp4")
        count = 0
    
        for i, seg in enumerate(self.segments, start=1):
            settings = base_settings.copy()
            settings["trim_enabled"] = True
            settings["trim_start"] = seg["start"]
            settings["trim_end"] = seg["end"]
            settings["precise_trim"] = False
            settings["output_dir"] = output_dir
            settings["custom_output_name"] = f"{basename}_seg{i:03d}.{container}"
            # 关键：禁用分段拼接模式
            settings["segment_enabled"] = False
            settings.pop("segments", None)
    
            if self.app.add_task(input_file, settings):
                count += 1
    
        self.app.update_task_list()
        self.app._append_info_ui(f"已添加 {count} 个快速分段任务到队列")
        messagebox.showinfo("成功", f"已添加 {count} 个快速分段任务到队列")
    
    def send_precise_to_queue(self):
        input_file = self.app.input_file.get().strip()
        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("错误", "请先在主界面选择输入文件")
            return
        if not self.segments:
            messagebox.showinfo("提示", "片段列表为空")
            return
    
        use_combo = messagebox.askyesno(
            "选择截取模式",
            "精确模式支持两种截取方式：\n\n"
            "• 是 (Yes)  → 双 -ss（组合跳转）\n"
            "  先快速跳转到目标附近，再精确微调，适合长视频，解码速度快。\n\n"
            "• 否 (No)  → trim 滤镜\n"
            "  完全基于解码帧截取，精度更高，但解码较慢。\n\n"
            "请选择是否使用双 -ss 加速？",
            icon='question'
        )
    
        base_settings = self.app.get_current_settings()
        base_settings.pop("watermark", None)   # 移除水印（保留其他滤镜）
    
        output_dir = self.app.output_dir.get().strip()
        if not output_dir or not os.path.exists(output_dir):
            output_dir = os.path.dirname(input_file)
        basename = os.path.splitext(os.path.basename(input_file))[0]
        container = base_settings.get("output_container", "mp4")
        count = 0
    
        for i, seg in enumerate(self.segments, start=1):
            settings = base_settings.copy()
            settings["trim_enabled"] = True
            settings["trim_start"] = seg["start"]
            settings["trim_end"] = seg["end"]
            if use_combo:
                settings["combo_seek"] = True
                settings["precise_trim"] = False
                settings["combo_threshold"] = 30
            else:
                settings["combo_seek"] = False
                settings["precise_trim"] = True
            settings["output_dir"] = output_dir
            settings["custom_output_name"] = f"{basename}_seg{i:03d}.{container}"
            # 禁用拼接模式
            settings["segment_enabled"] = False
            settings.pop("segments", None)
    
            self.app._append_info_ui(f"[分段] 片段 {i} 模式: {'双-ss' if use_combo else 'trim'}, start={seg['start']}")
    
            if self.app.add_task(input_file, settings):
                count += 1
    
        self.app.update_task_list()
        mode_str = "双 -ss" if use_combo else "trim"
        self.app._append_info_ui(f"已添加 {count} 个精确分段任务到队列（模式：{mode_str}）")
        messagebox.showinfo("成功", f"已添加 {count} 个精确分段任务到队列（模式：{mode_str}）")

    def export_quick_script(self):
        input_file = self.app.input_file.get().strip()
        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("错误", "请先在主界面选择输入文件")
            return
        if not self.segments:
            messagebox.showinfo("提示", "片段列表为空")
            return
    
        # 选择保存路径
        save_path = filedialog.asksaveasfilename(
            title="保存快速切割脚本",
            defaultextension=".bat" if sys.platform == "win32" else ".sh",
            filetypes=[("批处理文件", "*.bat"), ("Shell脚本", "*.sh")]
        )
        if not save_path:
            return
    
        output_dir = self.app.output_dir.get().strip()
        if not output_dir or not os.path.exists(output_dir):
            output_dir = os.path.dirname(input_file)
        basename = os.path.splitext(os.path.basename(input_file))[0]
        lines = []
        # 添加文件头
        if save_path.endswith(".sh"):
            lines.append("#!/bin/bash")
        else:
            lines.append("@echo off")
            lines.append("chcp 65001 >nul")
        lines.append("")
    
        for i, seg in enumerate(self.segments, start=1):
            start = seg["start"]
            end = seg["end"]
            out_name = f"{basename}_seg{i:03d}.mp4"
            out_path = os.path.join(output_dir, out_name)
            # 转义路径中的空格和特殊字符（Windows用双引号，Unix用单引号或转义）
            # 这里使用双引号简单处理
            cmd = f'ffmpeg -ss {start} -to {end} -i "{input_file}" -c copy "{out_path}"'
            lines.append(cmd)
    
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
    
        messagebox.showinfo("成功", f"脚本已保存到:\n{save_path}")
    
    
    def export_precise_script(self):
        input_file = self.app.input_file.get().strip()
        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("错误", "请先在主界面选择输入文件")
            return
        if not self.segments:
            messagebox.showinfo("提示", "片段列表为空")
            return
    
        choice = messagebox.askyesno(
            "选择截取模式",
            "导出精确脚本支持两种截取方式：\n\n"
            "• 是 (Yes)  → 双 -ss（组合跳转）\n"
            "  先快速跳转到目标附近，再精确微调，适合长视频，解码速度快。\n\n"
            "• 否 (No)  → trim 滤镜\n"
            "  完全基于解码帧截取，精度更高，但解码较慢。\n\n"
            "请选择是否使用双 -ss 加速？",
            icon='question'
        )
    
        save_path = filedialog.asksaveasfilename(
            title="保存精确切割脚本",
            defaultextension=".bat" if sys.platform == "win32" else ".sh",
            filetypes=[("批处理文件", "*.bat"), ("Shell脚本", "*.sh")]
        )
        if not save_path:
            return
    
        base_settings = self.app.get_current_settings()
        base_settings.pop("watermark", None)   # 移除水印
        output_dir = self.app.output_dir.get().strip()
        if not output_dir or not os.path.exists(output_dir):
            output_dir = os.path.dirname(input_file)
        basename = os.path.splitext(os.path.basename(input_file))[0]
        lines = []
        if save_path.endswith(".sh"):
            lines.append("#!/bin/bash")
        else:
            lines.append("@echo off")
            lines.append("chcp 65001 >nul")
        lines.append("")
    
        for i, seg in enumerate(self.segments, start=1):
            settings = base_settings.copy()
            settings["trim_enabled"] = True
            settings["trim_start"] = seg["start"]
            settings["trim_end"] = seg["end"]
            if choice:
                settings["combo_seek"] = True
                settings["precise_trim"] = False
                settings["combo_threshold"] = 30
            else:
                settings["combo_seek"] = False
                settings["precise_trim"] = True
            # 禁用拼接
            settings["segment_enabled"] = False
            settings.pop("segments", None)
    
            out_name = f"{basename}_seg{i:03d}.mp4"
            out_path = os.path.join(output_dir, out_name)
    
            try:
                cmd_list = self.app.generate_ffmpeg_command(input_file, out_path, settings)
                cmd_str = format_cmd_for_display(cmd_list)
            except Exception as e:
                cmd_str = f"# 错误：{e}"
            lines.append(cmd_str)
    
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
    
        mode_str = "双 -ss" if choice else "trim"
        messagebox.showinfo("成功", f"精确切割脚本已保存到:\n{save_path}\n模式：{mode_str}")


    # ---------- 片段管理核心方法（已优化浮点误差） ----------
    def add_segment_with_time(self, start_sec, end_sec, flip="无"):
        """直接使用浮点数添加片段（用于外部命令导入）"""
        if start_sec is None or end_sec is None:
            return False
        if start_sec >= end_sec:
            return False

        # 检查是否超出总时长（容差 0.001 秒，自动修正）
        if self.app and self.app.input_file.get():
            dur = self.app._get_media_duration(self.app.input_file.get())
            if dur is not None:
                if abs(end_sec - dur) <= 0.001:
                    end_sec = dur
                if end_sec > dur + 0.001:
                    self.app._append_info_ui(f"[分段] 片段超出总时长，已跳过")
                    return False

        start_str = seconds_to_time(start_sec)
        end_str = seconds_to_time(end_sec)
        self.segments.append({"start": start_str, "end": end_str, "flip": flip})
        self.refresh_tree()
        return True

    def add_segment(self):
        """
        从界面输入添加片段。
        若结束时间为空，自动补全为视频总时长（直接使用浮点数，避免往返转换误差）。
        """
        start = self.start_entry.get().strip()
        end = self.end_entry.get().strip()

        if not start:
            messagebox.showwarning("提示", "请填写开始时间")
            return

        start_sec = time_to_seconds(start)
        if start_sec is None:
            messagebox.showerror("错误", "开始时间格式无效，请使用 HH:MM:SS.ms 或秒数")
            return

        # 如果结束时间为空，自动补全为视频总时长
        if not end:
            if self.app and self.app.input_file.get():
                dur = self.app._get_media_duration(self.app.input_file.get())
                if dur is not None:
                    end_sec = dur                     # 直接使用浮点数
                    end = seconds_to_time(dur)        # 仅用于显示
                    self.app._append_info_ui(f"[分段] 结束时间自动设为总时长: {end}")
                else:
                    messagebox.showerror("错误", "无法获取视频总时长，请手动填写结束时间")
                    return
            else:
                messagebox.showerror("错误", "未指定输入文件，无法自动获取结束时间，请手动填写")
                return
        else:
            end_sec = time_to_seconds(end)
            if end_sec is None:
                messagebox.showerror("错误", "结束时间格式无效")
                return

        if start_sec >= end_sec:
            messagebox.showerror("错误", "开始时间必须小于结束时间")
            return

        # 仅对手动输入的结束时间进行超时检查（自动补全的已保证不超）
        if end:  # 用户手动输入
            if self.app and self.app.input_file.get():
                dur = self.app._get_media_duration(self.app.input_file.get())
                if dur is not None:
                    if abs(end_sec - dur) <= 0.001:
                        end_sec = dur
                        end = seconds_to_time(dur)
                    if end_sec > dur + 0.001:
                        self.app._append_info_ui(f"[分段] 片段超出总时长: {start}->{end}，已跳过")
                        return

        flip_value = self.flip_combo.get()
        self.segments.append({"start": start, "end": end, "flip": flip_value})
        self.refresh_tree()

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        del self.segments[idx]
        self.refresh_tree()

    def move_up(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        if idx == 0:
            return
        self.segments[idx], self.segments[idx-1] = self.segments[idx-1], self.segments[idx]
        self.refresh_tree()
        self.tree.selection_set(str(idx-1))

    def move_down(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        if idx == len(self.segments)-1:
            return
        self.segments[idx], self.segments[idx+1] = self.segments[idx+1], self.segments[idx]
        self.refresh_tree()
        self.tree.selection_set(str(idx+1))

    def clear_all(self):
        if self.segments and messagebox.askyesno("确认", "确定清空所有片段吗？"):
            self.segments.clear()
            self.refresh_tree()

    def refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, seg in enumerate(self.segments):
            start = seg["start"]
            end = seg["end"]
            dur = time_to_seconds(end) - time_to_seconds(start)
            dur_str = seconds_to_time(dur) if dur is not None else "?"
            self.tree.insert("", tk.END, iid=str(i), values=(i+1, start, end, dur_str, seg["flip"]))

    # ---------- 双击编辑 ----------
    def on_tree_double_click(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        seg = self.segments[idx]

        dialog = EditSegmentDialog(self.window, "编辑片段",
                                   start=seg["start"], end=seg["end"], flip=seg["flip"])
        if dialog.start is not None and dialog.end is not None:
            start_sec = time_to_seconds(dialog.start)
            end_sec = time_to_seconds(dialog.end)
            if start_sec is None or end_sec is None:
                messagebox.showerror("错误", "时间格式无效")
                return
            if start_sec >= end_sec:
                messagebox.showerror("错误", "开始时间必须小于结束时间")
                return

            start_display = seconds_to_time(start_sec)
            end_display = seconds_to_time(end_sec)

            # 检查并修正接近总时长的时间
            if self.app and self.app.input_file.get():
                dur = self.app._get_media_duration(self.app.input_file.get())
                if dur is not None:
                    if abs(end_sec - dur) <= 0.001:
                        end_sec = dur
                        end_display = seconds_to_time(end_sec)
                    if end_sec > dur + 0.001:
                        self.app._append_info_ui(f"[分段] 片段超出总时长: {start_display}->{end_display}，已跳过")
                        return

            # 存储用户输入的原始字符串（以便显示时与输入一致）
            seg["start"] = dialog.start
            seg["end"] = dialog.end
            seg["flip"] = dialog.flip
            self.refresh_tree()

    # ---------- 外部命令导入 ----------
    def import_from_commands(self):
        text = self.cmd_input.get(1.0, tk.END).strip()
        if not text:
            messagebox.showinfo("提示", "请先在右侧粘贴 FFmpeg 命令")
            return
    
        lines = text.splitlines()
        parsed_count = 0
        skipped_count = 0
        errors = []
    
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
    
            # 匹配 -ss 时间（支持 10.5 或 00:00:10.500 或 00:10.500）
            ss_match = re.search(r'-ss\s+([\d:.]+)', line, re.IGNORECASE)
            if not ss_match:
                skipped_count += 1
                errors.append(f"未找到 -ss: {line[:80]}...")
                continue
    
            start_str = ss_match.group(1)
            start_sec = time_to_seconds(start_str)
            if start_sec is None:
                skipped_count += 1
                errors.append(f"无效的开始时间: {start_str}，跳过")
                continue
    
            # 匹配 -t 或 -to
            t_match = re.search(r'-t\s+([\d:.]+)', line, re.IGNORECASE)
            to_match = re.search(r'-to\s+([\d:.]+)', line, re.IGNORECASE)
    
            if t_match:
                duration_str = t_match.group(1)
                duration_sec = time_to_seconds(duration_str)
                if duration_sec is None:
                    skipped_count += 1
                    errors.append(f"无效的持续时间: {duration_str}，跳过")
                    continue
                end_sec = start_sec + duration_sec
            elif to_match:
                end_str = to_match.group(1)
                end_sec = time_to_seconds(end_str)
                if end_sec is None:
                    skipped_count += 1
                    errors.append(f"无效的结束时间: {end_str}，跳过")
                    continue
            else:
                skipped_count += 1
                errors.append(f"未找到 -t 或 -to: {line[:80]}...")
                continue
    
            if end_sec <= start_sec:
                skipped_count += 1
                errors.append(f"结束时间必须大于开始时间: {start_str}->{end_str}，跳过")
                continue
    
            # 检查是否重复
            start_display = seconds_to_time(start_sec)
            end_display = seconds_to_time(end_sec)
            if any(seg["start"] == start_display and seg["end"] == end_display for seg in self.segments):
                skipped_count += 1
                errors.append(f"重复片段: {start_display}->{end_display}，已跳过")
                continue
    
            # 尝试添加片段（可能会检查总时长等）
            if self.add_segment_with_time(start_sec, end_sec, flip="无"):
                parsed_count += 1
            else:
                skipped_count += 1
                errors.append(f"添加失败（可能超出总时长）: {start_display}->{end_display}")
    
        msg = f"成功导入 {parsed_count} 个片段"
        if skipped_count > 0:
            msg += f"，{skipped_count} 行被跳过"
            if errors:
                # 只显示前10条错误
                error_preview = "\n".join(errors[:10])
                if len(errors) > 10:
                    error_preview += f"\n... 还有 {len(errors)-10} 条错误"
                messagebox.showwarning("导入警告", msg + "\n\n错误详情：\n" + error_preview)
            else:
                messagebox.showinfo("导入完成", msg)
        else:
            messagebox.showinfo("导入完成", msg)

    # ---------- 确定/取消 ----------
    def on_ok(self):
        self.result = self.segments
        self.window.destroy()

    def on_cancel(self):
        self.result = None
        self.window.destroy()

# ================== 主入口 ==================
if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, Exception):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = FFmpegBatchGUI(root)
    root.mainloop()
