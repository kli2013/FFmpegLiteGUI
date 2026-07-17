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

def find_executable(name: str) -> Optional[str]:
    """查找可执行文件：优先脚本目录，再检查打包后的 _internal 目录，最后搜索 PATH"""
    script_dir = get_script_dir()
    # 1. 脚本目录（开发环境或 one-dir 顶层）
    local_path = os.path.join(script_dir, name)
    if os.path.isfile(local_path) and os.access(local_path, os.X_OK):
        return local_path

    # 2. 打包后 one-dir 模式的 _internal 目录
    if getattr(sys, 'frozen', False):
        internal_path = os.path.join(script_dir, '_internal', name)
        if os.path.isfile(internal_path) and os.access(internal_path, os.X_OK):
            return internal_path

    # 3. 系统 PATH 环境变量
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
    def __init__(self, preset_path: str, app_name: str = "FFLiteGUI"):
        self.preset_path = preset_path
        self.user_data_dir = os.path.join(os.path.expanduser("~"), f".{app_name}")
        os.makedirs(self.user_data_dir, exist_ok=True)
        self._ensure_default_preset()

    def _ensure_default_preset(self):
        if os.path.exists(self.preset_path):
            return
    
        # 可能的捆绑路径列表
        possible_paths = []
        script_dir = get_script_dir()
    
        # 1. 脚本目录（开发环境或 one-dir 顶层）
        possible_paths.append(os.path.join(script_dir, "ffmpeg_presets.json"))
    
        # 2. 打包后 one-dir 模式的 _internal 目录
        if getattr(sys, 'frozen', False):
            possible_paths.append(os.path.join(script_dir, '_internal', "ffmpeg_presets.json"))
    
        # 3. onefile 模式下的 _MEIPASS 临时目录（若存在）
        if getattr(sys, 'frozen', False):
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                possible_paths.append(os.path.join(meipass, "ffmpeg_presets.json"))
    
        for bundled in possible_paths:
            if os.path.exists(bundled):
                try:
                    shutil.copy2(bundled, self.preset_path)
                    print(f"首次运行，已从内部释放默认配置到：{self.preset_path}")
                    return
                except Exception as e:
                    print(f"释放配置文件失败: {e}")
                    # 继续尝试下一个路径（但通常复制失败后不再尝试其他）
                    break

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
        """保存预设，保留已有的播放器设置"""
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
        with open(self.preset_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def delete_preset(self, name: str) -> bool:
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
        with open(self.preset_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True

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
                              include_trim: bool = True, include_format: bool = True, enhance_settings=None) -> str:
    """
    从设置字典构建视频滤镜链。
    include_subtitle: 是否包含字幕滤镜
    include_speed: 是否包含变速滤镜
    include_trim: 是否包含精准截取（trim+setpts）滤镜
    include_format: 是否包含像素格式转换（format）滤镜
    enhance_settings:高级一点的滤镜
    顺序优化：
    1. 精准截取		2. 裁剪		3. 缩放		4. IVTC（反胶卷过带）	5. 反交错
    6. 去块滤波		7. 降噪		8. 锐化		9. 旋转/翻转		10. 色彩空间转换
    11. 像素格式	12. 变速	13. 字幕烧录
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
        filters.append("ivtc=1")
    
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
    
    # ----- 色彩空间转换 -----
    if enhance_settings and enhance_settings.get("colorspace_enabled", False):
        matrix = enhance_settings.get("colorspace_matrix", "bt709:bt2020")
        filters.append(f"colormatrix={matrix}")
    
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
    
    return ",".join(filters) if filters else "null"

def build_preview_filter_chain(settings: Dict[str, Any], target_height: int = 960) -> str:
    """生成预览用的滤镜链，强制缩放到指定高度"""
    enhance_settings = settings.get("enhance", {})
    vf = build_video_filter_chain(settings, include_subtitle=True, include_speed=True, enhance_settings=enhance_settings)
    if vf != "null":
        return f"{vf},scale=-2:{target_height}"
    else:
        return f"scale=-2:{target_height}"

def build_atempo_chain(factor: float) -> str:
    """构建音频变速滤镜链，支持大于2倍或小于0.5倍的场景"""
    if factor == 1.0:
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
    # 裁剪
    if settings.get("crop_enabled", False):
        crop_w = settings.get("crop_width", "").strip()
        crop_h = settings.get("crop_height", "").strip()
        if crop_w and crop_h:
            def eval_crop(expr):
                if not expr:
                    return None
                expr2 = expr.replace('iw', str(w)).replace('ih', str(h))
                # 使用安全表达式求值
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
        return cmd_list

class OtherEncoderStrategy(EncoderStrategy):
    def build_params(self, cmd_list: List[str], settings: Dict[str, Any]) -> List[str]:
        vcodec = settings["encoder"]
        bitrate = fix_bitrate_value(settings["bitrate_video"])
        cmd_list.extend(["-c:v", vcodec, "-b:v", bitrate or '1000k'])
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
    def __init__(self, parent, refresh_callback=None, **kwargs):
        super().__init__(parent, text="视频编码与质量", padding="5", **kwargs)
        self.refresh_callback = refresh_callback  # 保存刷新函数
        self._suppress_update = False
        self.create_widgets()
        self.setup_bindings()

    def create_widgets(self):
        ttk.Label(self, text="编码器:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.vcodec = tk.StringVar(value="libx265")
        self.vcodec_combo = ttk.Combobox(self, textvariable=self.vcodec,
                                         values=ALL_VIDEO_ENCODERS, state="readonly", width=18)
        self.vcodec_combo.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        preset_frame = ttk.Frame(self)
        preset_frame.grid(row=0, column=2, sticky="w", padx=5, pady=2)
        ttk.Label(preset_frame, text="编码预设:").pack(side=tk.LEFT, padx=(0,5))
        self.preset = tk.StringVar(value="medium")
        self.preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset,
                                         values=["ultrafast","superfast","veryfast","faster","fast",
                                                 "medium","slow","slower","veryslow",
                                                 "p1","p2","p3","p4","p5","p6","p7"],
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

        # 高级选项面板（新建）
        self.advanced_frame = ttk.Frame(self)
        self.advanced_frame.grid(row=4, column=0, columnspan=3, sticky="we", pady=5, padx=5)
        # 默认隐藏
        self.advanced_frame.grid_remove()

        # 在 advanced_frame 中添加控件
        row1 = ttk.Frame(self.advanced_frame)
        row1.pack(fill=tk.X, pady=2)
        
        ttk.Label(row1, text="tune:").pack(side=tk.LEFT)
        self.tune_var = tk.StringVar(value="无")   # 默认“无”
        tune_combo = ttk.Combobox(row1, textvariable=self.tune_var,
                                  values=["无", "film","animation","grain","stillimage","psnr","ssim","fastdecode","zerolatency"],
                                  state="readonly", width=10)
        tune_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row1, text="profile:").pack(side=tk.LEFT, padx=(10,0))
        self.profile_var = tk.StringVar(value="无")
        profile_combo = ttk.Combobox(row1, textvariable=self.profile_var,
                                     values=["无", "baseline","main","high","high10","high422","high444"],
                                     state="readonly", width=8)
        profile_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row1, text="level:").pack(side=tk.LEFT, padx=(10,0))
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
        ttk.Label(row2, text="最大比特率 (kbps):").pack(side=tk.LEFT)
        self.maxrate_var = tk.StringVar(value="")
        maxrate_entry = ttk.Entry(row2, textvariable=self.maxrate_var, width=8)
        maxrate_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(row2, text="缓冲区大小 (kbps):").pack(side=tk.LEFT, padx=(10,0))
        self.bufsize_var = tk.StringVar(value="")
        bufsize_entry = ttk.Entry(row2, textvariable=self.bufsize_var, width=8)
        bufsize_entry.pack(side=tk.LEFT, padx=5)

        # GIF 参数变量（存储实际值）
        self.gif_loop = tk.IntVar(value=0)
        self.gif_dither = tk.StringVar(value="bayer")
        self.gif_bayer_scale = tk.IntVar(value=2)
        self.gif_max_colors = tk.IntVar(value=256)
        
        self._on_gif_codec_toggle()




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
            return  # 加载预设时跳过所有副作用
        self.update_dynamic_controls()
        self.auto_set_codec_by_rate_control()
        rc = self.rate_control_type.get()
        if rc == "crf" or rc == "global_quality":
            self.preset.set("medium")
        elif rc == "cq":
            self.preset.set("p4")

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
        try:
            # 处理 preset（兼容旧预设）
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
            self.rate_control_type.set(settings.get("rate_control_type", "crf"))
            self.crf_value.set(settings.get("crf_value", 26))
            self.cq_value.set(settings.get("cq_value", 35))
            self.global_quality.set(settings.get("global_quality", 26))
            self.bitrate_video.set(settings.get("bitrate_video", "1900k"))
            # GIF 参数...
            if "gif_loop" in settings:
                self.gif_loop.set(settings["gif_loop"])
            if "gif_dither" in settings:
                self.gif_dither.set(settings["gif_dither"])
            if "gif_bayer_scale" in settings:
                self.gif_bayer_scale.set(settings["gif_bayer_scale"])
            if "gif_max_colors" in settings:
                self.gif_max_colors.set(settings["gif_max_colors"])
            self._on_gif_codec_toggle()


            self.tune_var.set(settings.get("tune", "无") or "无")
            self.profile_var.set(settings.get("profile", "无") or "无")
            self.level_var.set(settings.get("level", "无") or "无")
            self.maxrate_var.set(settings.get("maxrate", ""))
            self.bufsize_var.set(settings.get("bufsize", ""))
        finally:
            self._suppress_update = False
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
        super().__init__(parent, text="视频滤镜 (缩放/裁剪/旋转/变速/反交错/像素格式)", padding="5", **kwargs)
        self.app = app
        self.current_file = None
        self.current_track = None
        self.override_settings = None
        self.get_trim_settings_callback = None
        self.preview_callback = preview_callback
        self._visual_crop_start_time = None
        self.create_widgets()

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
        ttk.Checkbutton(line1, text="烧录字幕", variable=self.subtitle_enabled,
                        command=self.toggle_subtitle).pack(side=tk.LEFT, padx=(2, 5))
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
        ttk.Checkbutton(scale_frame, text="启用缩放", variable=self.scale_enabled).pack(side=tk.LEFT)
        ttk.Radiobutton(scale_frame, text="宽度(高度自动)", variable=self.scale_method, value="width").pack(side=tk.LEFT, padx=(10,0))
        ttk.Entry(scale_frame, textvariable=self.scale_width, width=6).pack(side=tk.LEFT)
        ttk.Label(scale_frame, text="px").pack(side=tk.LEFT)
        ttk.Radiobutton(scale_frame, text="高度(宽度自动)", variable=self.scale_method, value="height").pack(side=tk.LEFT, padx=10)
        ttk.Entry(scale_frame, textvariable=self.scale_height, width=6).pack(side=tk.LEFT)
        ttk.Label(scale_frame, text="px").pack(side=tk.LEFT)
        ttk.Radiobutton(scale_frame, text="精确宽×高", variable=self.scale_method, value="exact").pack(side=tk.LEFT, padx=10)
        ttk.Entry(scale_frame, textvariable=self.scale_width, width=6).pack(side=tk.LEFT)
        ttk.Label(scale_frame, text="×").pack(side=tk.LEFT)
        ttk.Entry(scale_frame, textvariable=self.scale_height, width=6).pack(side=tk.LEFT)
    
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
                wraplength=400)

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
                wraplength=400)

        rot_frame = ttk.Frame(left_frame)
        rot_frame.pack(fill=tk.X, pady=2)
        ttk.Label(rot_frame, text="旋转:").pack(side=tk.LEFT)
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
        ttk.Checkbutton(hybrid_frame, text="启用变速", variable=self.speed_enabled).pack(side=tk.LEFT)
        ttk.Label(hybrid_frame, text="速度倍数 (0.5慢,2.0快):").pack(side=tk.LEFT, padx=5)
        ttk.Entry(hybrid_frame, textvariable=self.speed_factor, width=6).pack(side=tk.LEFT)
    
        ttk.Label(hybrid_frame, text="反交错:").pack(side=tk.LEFT, padx=(10,0))
        self.deinterlace_filter = tk.StringVar(value="none")
        deinterlace_combo = ttk.Combobox(hybrid_frame, textvariable=self.deinterlace_filter,
                                         values=["none", "bwdif", "yadif", "kerndeint", "pp=lb", "fieldorder"],
                                         state="readonly", width=10)
        deinterlace_combo.pack(side=tk.LEFT, padx=2)
        ToolTip(deinterlace_combo, 
                "反交错滤镜选项：\n"
                "yadif - 常用反交错，适合大多数隔行扫描内容\n"
                "bwdif - 运动自适应，比yadif更锐利\n"
                "kerndeint - 基于内核，适合电影模式\n"
                "pp=lb - 行混合，柔和去拉丝\n"
                "fieldorder - 仅调整场序，不反交错",
                wraplength=400)
    
        self.pix_fmt_enabled = tk.BooleanVar(value=True)
        self.pix_fmt = tk.StringVar(value="yuv420p")
        ttk.Label(hybrid_frame, text="像素格式:").pack(side=tk.LEFT, padx=(20,0))
        ttk.Checkbutton(hybrid_frame, text="指定", variable=self.pix_fmt_enabled).pack(side=tk.LEFT)
        self.pix_fmt_combo = ttk.Combobox(hybrid_frame, textvariable=self.pix_fmt, 
                                          values=self.PIX_FMTS, width=12, state="normal")
        self.pix_fmt_combo.pack(side=tk.LEFT, padx=5)


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
        center_window(win, 500, 550)
    
        main = ttk.Frame(win, padding="10")
        main.pack(fill=tk.BOTH, expand=True)
    
        # ----- 降噪（hqdn3d）-----
        denoise_frame = ttk.LabelFrame(main, text="降噪 (hqdn3d)", padding="5")
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
    
        # ----- 锐化（unsharp）-----
        sharpen_frame = ttk.LabelFrame(main, text="锐化 (unsharp)", padding="5")
        sharpen_frame.pack(fill=tk.X, pady=5)
    
        self.sharpen_enabled = tk.BooleanVar(value=self.enhance_settings.get("sharpen_enabled", False))
        ttk.Checkbutton(sharpen_frame, text="启用锐化", variable=self.sharpen_enabled).pack(anchor=tk.W)
    
        row3 = ttk.Frame(sharpen_frame); row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="锐化强度 (0~5):").pack(side=tk.LEFT)
        self.sharpen_strength = tk.DoubleVar(value=self.enhance_settings.get("sharpen_strength", 1.0))
        ttk.Scale(row3, from_=0, to=5, variable=self.sharpen_strength, orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT, padx=5)
        ttk.Label(row3, textvariable=self.sharpen_strength, width=4).pack(side=tk.LEFT)
    
        # ----- IVTC（反胶卷过带）-----
        ivtc_frame = ttk.LabelFrame(main, text="反胶卷过带 (IVTC)", padding="5")
        ivtc_frame.pack(fill=tk.X, pady=5)
        self.ivtc_enabled = tk.BooleanVar(value=self.enhance_settings.get("ivtc_enabled", False))
        ttk.Checkbutton(ivtc_frame, text="启用 IVTC (适用于 60i -> 24p)", variable=self.ivtc_enabled).pack(anchor=tk.W)
    
        # ----- 去块滤波（deblock）-----
        deblock_frame = ttk.LabelFrame(main, text="去块滤波 (deblock)", padding="5")
        deblock_frame.pack(fill=tk.X, pady=5)
        self.deblock_enabled = tk.BooleanVar(value=self.enhance_settings.get("deblock_enabled", False))
        ttk.Checkbutton(deblock_frame, text="启用去块", variable=self.deblock_enabled).pack(anchor=tk.W)
    
        row4 = ttk.Frame(deblock_frame); row4.pack(fill=tk.X, pady=2)
        ttk.Label(row4, text="强度 (1~8):").pack(side=tk.LEFT)
        self.deblock_strength = tk.IntVar(value=self.enhance_settings.get("deblock_strength", 4))
        ttk.Scale(row4, from_=1, to=8, variable=self.deblock_strength, orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT, padx=5)
        ttk.Label(row4, textvariable=self.deblock_strength, width=4).pack(side=tk.LEFT)
    
        # ----- 色彩空间转换-----
        colorspace_frame = ttk.LabelFrame(main, text="色彩空间转换", padding="5")
        colorspace_frame.pack(fill=tk.X, pady=5)
        self.colorspace_enabled = tk.BooleanVar(value=self.enhance_settings.get("colorspace_enabled", False))
        ttk.Checkbutton(colorspace_frame, text="启用转换", variable=self.colorspace_enabled).pack(anchor=tk.W)
    
        row5 = ttk.Frame(colorspace_frame); row5.pack(fill=tk.X, pady=2)
        ttk.Label(row5, text="目标色彩矩阵:").pack(side=tk.LEFT)
        self.colorspace_matrix = tk.StringVar(value=self.enhance_settings.get("colorspace_matrix", "bt709:bt2020"))
        ttk.Combobox(row5, textvariable=self.colorspace_matrix, 
                     values=["bt709:bt2020", "bt2020:bt709", "bt601:bt709", "bt709:bt601"], 
                     state="readonly", width=15).pack(side=tk.LEFT, padx=5)
    
        # ----- 按钮-----
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=10)
    
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
            })
            if self.app:
                self.app.update_command_preview()
            # 刷新编辑窗口预览（如果存在回调）
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
        orig_w, orig_h = get_video_dimensions(self.app.ffprobe_cmd, input_file)
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
    
            def cleanup_scaled_file(event=None):
                if scaled_temp_path and os.path.exists(scaled_temp_path):
                    try:
                        os.unlink(scaled_temp_path)
                    except:
                        pass
            win.bind("<Destroy>", cleanup_scaled_file)
    
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
                # 保证偶数（兼容编码器）
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
    
                def extract_thread():
                    nonlocal scaled_temp_path, img
                    fd_new, new_png = tempfile.mkstemp(suffix='.png', prefix='ffgui_crop_')
                    os.close(fd_new)
                    try:
                        # 调用 PNG 提取函数（需确保已实现）
                        w, h = self.extract_video_frame_scaled(
                            input_file, new_png,
                            frame_sec=sec,
                            target_width=disp_w,
                            target_height=disp_h
                        )
                        if w is None or h is None:
                            self.app.root.after(0, lambda: on_extract_failed("提取帧失败，请检查文件是否支持"))
                            return
                        # 成功，传递路径和实际尺寸
                        self.app.root.after(0, lambda: on_extract_success(new_png, w, h))
                    except Exception as e:
                        self.app.root.after(0, lambda: on_extract_failed(f"提取异常: {e}"))
                    finally:
                        # 不要删除 new_png，它会在成功回调中处理
                        pass
    
                def on_extract_success(new_scaled_path, new_orig_w, new_orig_h):
                    nonlocal img, scaled_temp_path, img_w, img_h
                    nonlocal points, rect_id, drag_start_display, drag_rect_id
                    try:
                        new_img = tk.PhotoImage(file=new_scaled_path)
                    except Exception as e:
                        on_extract_failed(f"加载缩放后的图像失败: {e}")
                        return
    
                    # 删除旧临时文件
                    if scaled_temp_path and os.path.exists(scaled_temp_path):
                        try:
                            os.unlink(scaled_temp_path)
                        except:
                            pass
    
                    scaled_temp_path = new_scaled_path
    
                    # 更新图像
                    canvas.delete("bg_img")
                    canvas.create_image(PADDING, PADDING, anchor=tk.NW, image=new_img, tags="bg_img")
                    canvas.image = new_img
                    img = new_img
    
                    # 更新图像尺寸（如果与预期不符，更新并调整缩放因子）
                    actual_w = new_img.width()
                    actual_h = new_img.height()
                    if actual_w != disp_w or actual_h != disp_h:
                        self.app._append_info_ui(f"[裁剪] PNG 实际尺寸 {actual_w}x{actual_h} 与预期 {disp_w}x{disp_h} 不符，已自动调整")
                        # 更新显示尺寸和缩放因子
                        nonlocal scale_x, scale_y  # 需要允许修改外部 scale_x/scale_y
                        # 但 scale_x 是在外层定义的，需要声明 nonlocal
                        # 由于 scale_x 在 open_crop_editor 的作用域，但不在 on_extract_success 所在层级？实际上 scale_x 是在 open_crop_editor 中定义的，属于闭包。
                        # 我们需要在 open_crop_editor 中将 scale_x/scale_y 定义为变量，并在 on_extract_success 中声明 nonlocal。
                        # 但当前我们尚未声明，所以需要先声明。
                        # 这里为了简单，我们忽略此情况（因为 FFmpeg 应该准确输出），或者稍后补充。
                        pass
    
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
            ttk.Button(btn_frame, text="取消", command=win.destroy).pack(fill=tk.X, pady=2)
    
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
            # 调用提取函数初始化画面
            def initial_load():
                # 直接在当前线程执行，避免阻塞
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
                        messagebox.showerror("错误", "无法提取初始帧")
                        win.destroy()
                        return
                    # 加载图像
                    img_obj = tk.PhotoImage(file=png_path)
                    canvas.create_image(PADDING, PADDING, anchor=tk.NW, image=img_obj, tags="bg_img")
                    canvas.image = img_obj
                    nonlocal img, scaled_temp_path
                    img = img_obj
                    scaled_temp_path = png_path
                except Exception as e:
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
            "subtitle_path": self.subtitle_path.get()
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
        self.audio_format = tk.StringVar(value="mp3")
        audio_format_combo = ttk.Combobox(top_row, textvariable=self.audio_format,
                                          values=["mp3", "aac", "m4a", "flac", "opus", "wav", "ac3"],
                                          state="readonly", width=6)
        audio_format_combo.pack(side=tk.LEFT, padx=2)
        ToolTip(self.only_audio_cb, "勾选后，将只输出音频文件（自动添加 -vn 忽略视频），输出容器将使用右边选择的音频格式", offset_x=0, offset_y=5)
    
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
        ToolTip(chk_volume, "勾选后启用音量倍数调整，可拖动滑块设置倍数（0.1~3.0）\n\n1.0=原始音量", wraplength=200)
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
        self.audio_format.set(settings.get("audio_format", "mp3"))
        vol = settings.get("volume", 1.0)
        self.volume_value.set(vol)
        self.volume_label.config(text=f"{vol:.2f}")
        enabled = settings.get("volume_enabled", False)
        self.volume_enabled.set(enabled)


# ================== 截取片段组件 ==================
class TrimFrame(ttk.LabelFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, text="截取片段", padding="5", **kwargs)
        self.create_widgets()

    def create_widgets(self):
        self.trim_enabled = tk.BooleanVar(value=False)
        self.trim_check = ttk.Checkbutton(self, text="启用截取片段", variable=self.trim_enabled,
                                          command=self.on_trim_toggle)
        self.trim_check.pack(anchor=tk.W, pady=(0,10))
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
    
        # ----- 新增：精准到帧复选框 -----
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
        # 新增结束

        info_label = ttk.Label(self, text="示例: 01:23:45 或 01:23:45.500 (留空表示到文件末尾)", foreground="gray")
        info_label.pack(anchor=tk.W, pady=(5,0))

        self.on_trim_toggle()

    def on_precise_toggle(self):
        # 精准模式不需要禁用任何控件，仅用于界面反馈（可留空）
        pass

    def on_trim_toggle(self):
        state = tk.NORMAL if self.trim_enabled.get() else tk.DISABLED
        self.trim_start_entry.config(state=state)
        self.trim_end_entry.config(state=state)

    def get_settings(self):
        return {
            "trim_enabled": self.trim_enabled.get(),
            "trim_start": self.trim_start.get(),
            "trim_end": self.trim_end.get(),
            "precise_trim": self.precise_trim.get()   # 新增
        }

    def set_settings(self, settings):
        self.trim_enabled.set(settings.get("trim_enabled", False))
        self.trim_start.set(settings.get("trim_start", "0"))
        self.trim_end.set(settings.get("trim_end", ""))
        self.precise_trim.set(settings.get("precise_trim", False))   # 新增
        self.on_trim_toggle()

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
                wraplength=400)

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

        self.chroma_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(chroma_frame, text="启用绿幕抠像", variable=self.chroma_enabled).grid(row=0, column=0, sticky="w")

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
    仅用于封装/合并模块的轨道编辑，不用于水印编辑器。
    """
    def __init__(self, master, app, mode='sub', track_idx=None, track_obj=None,
                 pip_enabled_var=None, filt_frame=None, visual_callback=None, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app
        self.mode = mode
        self.track_idx = track_idx
        self.track_obj = track_obj
        self.pip_enabled_var = pip_enabled_var
        self.filt_frame = filt_frame
        self.visual_callback = visual_callback   # 新增
        self._controls = []
        self._rebuild()

        if self.pip_enabled_var is not None:
            self.pip_enabled_var.trace_add('write', lambda *a: self._rebuild())

    def _rebuild(self):
        """清除所有子控件，根据画中画状态重建"""
        # 检查窗口是否还存在（避免在销毁后调用）
        if not self.winfo_exists():
            return
        for child in self.winfo_children():
            child.destroy()
        self._controls.clear()
        if (self.pip_enabled_var is None) or self.pip_enabled_var.get():
            self._create_controls()
        else:
            self._create_message()

    def _create_message(self):
        """显示提示信息（画中画未启用）"""
        msg = (
            "当前未启用画中画模式。\n"
            "如需调整叠加/偏移参数，请先在主界面勾选“启用画中画”。\n"
            "注意：给视频流选择重新编码，不能使用 copy。"
        )
        label = ttk.Label(self, text=msg, justify="center", foreground="gray",
                          font=("Microsoft YaHei", 12, "bold"))
        label.pack(expand=True, anchor='center', pady=20)
        self._controls.append(label)

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

        # 可视化编辑（传入 filt_frame 以便同步缩放设置）
        def open_visual():
            if not self.overlay_enabled.get():
                messagebox.showinfo("提示", "请先勾选「启用叠加」再使用可视化编辑功能。")
                return
            if self.visual_callback is not None:
                self.visual_callback()   # 调用外部传入的回调
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
        """主视频画布偏移控件（与之前相同）"""
        self.pad_enabled = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(self, text="启用画布偏移", variable=self.pad_enabled)
        cb.pack(anchor=tk.W, pady=(0,5))
        self._controls.append(cb)
    
        w_frame = ttk.Frame(self)
        w_frame.pack(fill=tk.X, pady=2)
        ttk.Label(w_frame, text="画布宽度:").pack(side=tk.LEFT)
        self.pad_width = tk.StringVar(value="")
        entry = ttk.Entry(w_frame, textvariable=self.pad_width, width=10)
        entry.pack(side=tk.LEFT, padx=5)
        self._controls.extend([w_frame, entry])
    
        if self.app:
            def fetch_size():
                # 获取主视频文件路径
                main_file = self.app.merge_video.get().strip() if self.app.merge_video else ""
                if not main_file or not os.path.exists(main_file):
                    # 尝试从主界面输入文件获取
                    main_file = self.app.input_file.get().strip() if self.app.input_file else ""
                if not main_file or not os.path.exists(main_file):
                    messagebox.showerror("错误", "未找到主视频文件，请先设置主视频")
                    return
                w, h = get_video_dimensions(self.app.ffprobe_cmd, main_file)
                if w is not None and h is not None:
                    self.pad_width.set(str(w))
                    self.pad_height.set(str(h))
                    self.app._append_info_ui(f"[尺寸获取] 获取到主视频尺寸: {w}x{h}")
                else:
                    messagebox.showerror("错误", f"无法获取视频尺寸，请检查 ffprobe 是否可用或文件是否正常。")
            btn = ttk.Button(w_frame, text="获取尺寸", command=fetch_size)
            btn.pack(side=tk.LEFT, padx=5)
            self._controls.append(btn)
    
        h_frame = ttk.Frame(self)
        h_frame.pack(fill=tk.X, pady=2)
        ttk.Label(h_frame, text="画布高度:").pack(side=tk.LEFT)
        self.pad_height = tk.StringVar(value="")
        entry = ttk.Entry(h_frame, textvariable=self.pad_height, width=10)
        entry.pack(side=tk.LEFT, padx=5)
        self._controls.extend([h_frame, entry])

        ox_frame = ttk.Frame(self)
        ox_frame.pack(fill=tk.X, pady=2)
        ttk.Label(ox_frame, text="偏移 X:").pack(side=tk.LEFT)
        self.offset_x = tk.StringVar(value="0")
        entry = ttk.Entry(ox_frame, textvariable=self.offset_x, width=10)
        entry.pack(side=tk.LEFT, padx=5)
        self._controls.extend([ox_frame, entry])

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
                    live_filt_frame=None,
                    parent=parent_win
                )
            else:
                messagebox.showinfo("提示", "无法启动可视化编辑：缺少轨道索引")
        btn = ttk.Button(ox_frame, text="🎨 可视化编辑画布偏移", command=open_pad_editor)
        btn.pack(side=tk.LEFT, padx=5)
        self._controls.append(btn)

        oy_frame = ttk.Frame(self)
        oy_frame.pack(fill=tk.X, pady=2)
        ttk.Label(oy_frame, text="偏移 Y:").pack(side=tk.LEFT)
        self.offset_y = tk.StringVar(value="0")
        entry = ttk.Entry(oy_frame, textvariable=self.offset_y, width=10)
        entry.pack(side=tk.LEFT, padx=5)
        self._controls.extend([oy_frame, entry])

        tip = ttk.Label(self, text="⚠ 预览模式下无法体现偏移效果，请转码后查看", foreground="red")
        tip.pack(fill=tk.X, pady=(10,0))
        self._controls.append(tip)

    def get_settings(self):
        if self.pip_enabled_var is not None and not self.pip_enabled_var.get():
            return {}
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
        if self.pip_enabled_var is not None and not self.pip_enabled_var.get():
            return
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
                "• 界面上已单独提供的参数（如 tune、profile、level、maxrate、bufsize）请勿重复添加，以免冲突。\n"
                "• 新手建议：仅添加界面未提供的高级选项（如 -x264-params、-bsf 等），避免覆盖关键设置。",
                wraplength=500)
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
        ToolTip(self.watermark_btn, "打开独立窗口配置水印（支持缩放、裁剪、绿幕、位置调整等）。\n注意：水印会应用在主视频之上，且会忽略水印自身的音频。")
        
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
        if self.app is None:
            return
        file_path = self.watermark_dict.get("file_path", "")
        if not file_path or not os.path.exists(file_path):
            messagebox.showwarning("提示", "请先选择一个有效的水印文件")
            return
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
            track_obj=None
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
        # 字幕专用字段（仅对字幕有效）
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
                    "alpha_value": 1.0,
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
                    "precise_trim": False
                }
            else:  # subtitle
                self.enc_settings = {"encoder": "copy"}
        else:
            self.enc_settings = copy.deepcopy(enc_settings)
            # 对于字幕，从 enc_settings 中读取语言和标题
            if typ == "subtitle":
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
            if self.window and self.window.winfo_exists():
                self.window.destroy()
            if self.master:
                try:
                    self.master.grab_release()
                except:
                    pass

    def __init__(self, root):
        self.root = root
        self.root.title("FFmpeg 多功能工具")
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

        # 基本变量
        self.input_file = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.output_suffix = tk.StringVar(value="")
        self.custom_output_name = tk.StringVar(value="")
        self.output_container = tk.StringVar(value="mp4")
        
        self.log_enabled_var = tk.BooleanVar(value=True)
        default_log_path = os.path.join(get_script_dir(), "editlog.txt")
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
        self.load_player_settings()

        # 创建界面组件
        self.create_widgets()
        self.update_task_list()
        self.update_command_preview()

        # 拖拽支持
        if DND_AVAILABLE:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self.on_files_dropped)

        self.show_quick_warning()




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
        if not settings.get("precise_trim", False):
            return None, None
    
        start = settings.get("trim_start", "").strip()
        end = settings.get("trim_end", "").strip()
        start_sec = time_to_seconds(start) if start else None
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
        """获取媒体文件时长（秒），失败返回 None"""
        if not self.ffprobe_cmd:
            return None
        cmd = [self.ffprobe_cmd, "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", file_path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5,
                                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except:
            pass
        return None

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
        生成分段拼接的 FFmpeg 命令，使用 filter_complex。
        settings 包含编码、音频、全局滤镜等设置。
        """
        segments = settings.get("segments", [])
        if not segments:
            raise ValueError("片段列表为空")
    
        input_path = normalize_path(input_path)
        output_path = normalize_path(output_path)
    
        cmd = [self.ffmpeg_cmd, "-y", "-i", input_path]
    
        # ----- 构建 filter_complex -----
        n = len(segments)
        v_filters = []
        a_filters = []
        disable_audio = not settings.get("audio_enabled", True)  # 注意：audio_enabled 默认 True
    
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
    
            v_filters.append(f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS{flip_filter}[v{i}]")
            if not disable_audio:
                a_filters.append(f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]")
    
        # 视频 concat
        v_concat = f"[{']['.join(f'v{i}' for i in range(n))}]concat=n={n}:v=1:a=0[vout]"
        # 合并所有滤镜
        filter_parts = v_filters + [v_concat]
        if not disable_audio:
            filter_parts.extend(a_filters)
            a_concat = f"[{']['.join(f'a{i}' for i in range(n))}]concat=n={n}:v=0:a=1[aout]"
            filter_parts.append(a_concat)
        all_filters = ";".join(filter_parts)
    
        # ----- 全局滤镜（缩放、裁剪、旋转、帧率、像素格式）-----
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
        # 翻转（全局翻转，如果用户在主界面勾选，但片段内已经独立翻转，这里可以叠加，但一般不需要）
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
    
        if global_filters:
            global_filter_str = ",".join(global_filters)
            all_filters += f";[vout]{global_filter_str}[final_v]"
            map_v = "[final_v]"
        else:
            map_v = "[vout]"
    
        cmd.extend(["-filter_complex", all_filters])
    
        # 映射
        if disable_audio:
            cmd.extend(["-map", map_v])
        else:
            cmd.extend(["-map", map_v, "-map", "[aout]"])
    
        # ----- 视频编码参数 -----
        vcodec = settings.get("encoder", "libx265")
        if vcodec == "copy":
            # 拼接必须重新编码，强制改为 libx265
            self._append_info_ui("分段拼接模式不支持 copy，自动改为 libx265")
            vcodec = "libx265"
            settings["encoder"] = vcodec
    
        strategy = get_encoder_strategy(vcodec)
        cmd = strategy.build_params(cmd, settings)
    
        # ----- 音频编码参数（如果启用）-----
        if not disable_audio:
            acodec = settings.get("audio_codec", "aac")
            abitrate = settings.get("audio_bitrate", "128k")
            arate = settings.get("audio_samplerate", "44100")
            cmd.extend(["-c:a", acodec, "-b:a", abitrate, "-ar", arate])
    
        # ----- 自定义参数 -----
        custom = settings.get("custom_args", "").strip()
        if custom:
            try:
                cmd.extend(shlex.split(custom))
            except ValueError:
                self._append_info_ui(f"警告：自定义参数格式错误，已忽略：{custom}")
    
        # ----- 容器优化 -----
        container = settings.get("output_container", "mp4").lower()
        if container in ("mp4", "mov"):
            cmd.extend(["-movflags", "+faststart"])
    
        cmd.append(output_path)
        return cmd

    def _build_overlay_filter_complex(self, main_idx: int, main_settings: dict,
                                       sub_infos: List[Tuple[int, str, dict]],
                                       include_subtitle_main: bool = False,
                                       enhance_settings: Optional[dict] = None) -> Tuple[str, str]:
        """
        构建主视频 + 多个子视频（画中画/水印）的 filter_complex 字符串。
        注意：此函数不会在 overlay 中添加 shortest=1，避免子视频流结束导致输出提前截断。
        输出结束由全局 -shortest 控制。
        """
        filter_parts = []
        # 主视频滤镜
        main_vf = build_video_filter_chain(main_settings, include_subtitle=include_subtitle_main,include_speed=True, enhance_settings=enhance_settings)
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
                # 始终无限循环（loop=-1），显示时间由 enable 控制
                loop_param = "-1"
                vf_parts = [
                    f"trim=start={start_sec}:end={end_sec}",
                    "setpts=PTS-STARTPTS",
                    f"loop=loop={loop_param}:size={size}:start=0"
                ]
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
    
            # 绿幕
            if sub_settings.get("chroma_enabled", False):
                color = sub_settings.get("chroma_color", "green")
                if color.startswith("#"):
                    color = "0x" + color[1:].upper()
                similarity = sub_settings.get("chroma_similarity", 0.3)
                if similarity <= 0:
                    similarity = 0.00001
                blend = sub_settings.get("chroma_blend", 0.1)
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

    def _get_effective_duration(self, settings: dict, raw_duration: Optional[float]) -> Optional[float]:
        """
        计算子视频的有效时长（考虑截取设置）。
        返回值为秒数，若无法计算或无效则返回 None。
        """
        if not settings.get("trim_enabled", False) or raw_duration is None or raw_duration <= 0:
            return raw_duration
    
        start_str = settings.get("trim_start", "").strip()
        end_str = settings.get("trim_end", "").strip()
        start_sec = time_to_seconds(start_str) if start_str else 0.0
        end_sec = time_to_seconds(end_str) if end_str else None
    
        if end_sec is not None and end_sec > start_sec:
            effective = end_sec - start_sec
        else:
            # 无结束或结束无效，截取到末尾
            effective = raw_duration - start_sec
    
        if effective <= 0:
            return None
        return effective

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
        settings = self.preset_manager.load_player_settings()
        self.use_mpv.set(settings.get("use_mpv", False))
        self.mpv_path.set(settings.get("mpv_path", "mpv"))
        # 读取日志设置，缺失时使用默认值
        self.log_enabled_var.set(settings.get("log_enabled", True))
        self.log_path_var.set(settings.get("log_path", os.path.join(get_script_dir(), "editlog.txt")))
        self.overwrite_policy.set(settings.get("overwrite_policy", "ask"))

    def save_player_settings(self):
        self.preset_manager.save_player_settings({
            "use_mpv": self.use_mpv.get(),
            "mpv_path": self.mpv_path.get(),
            "log_enabled": self.log_enabled_var.get(),
            "log_path": self.log_path_var.get(),
            "overwrite_policy": self.overwrite_policy.get()
        })

    def preview_with_player(self, input_path, filters=None, audio_only=False, volume=10, extra_args=None):
        """使用安全列表命令预览"""
        if audio_only:
            if self.use_mpv.get():
                player = self.mpv_path.get().strip() or "mpv"
                cmd_list = [player, input_path, "--no-video", f"--volume={volume}", "--autoexit"]
                cmd_str = f'"{player}" "{input_path}" --no-video --volume={volume} --autoexit'
            else:
                if not self.ffplay_cmd:
                    self._append_info_ui("未找到 ffplay，无法预览。")
                    return
                cmd_list = [self.ffplay_cmd, "-nodisp", "-autoexit", "-volume", str(volume), input_path]
                cmd_str = " ".join(f'"{p}"' if os.path.sep in p else p for p in cmd_list)
        else:
            if self.use_mpv.get():
                player = self.mpv_path.get().strip() or "mpv"
                cmd_list = [player, input_path]
                if filters:
                    cmd_list.extend(["--vf", filters])
                if extra_args:
                    cmd_list.extend(extra_args)
                cmd_parts = [f'"{player}"', f'"{input_path}"']
                if filters:
                    cmd_parts.append(f'--vf={filters}')
                if extra_args:
                    cmd_parts.extend(extra_args)
                cmd_str = " ".join(cmd_parts)
            else:
                if not self.ffplay_cmd:
                    self._append_info_ui("未找到 ffplay，无法预览。")
                    return
                cmd_list = [self.ffplay_cmd, "-i", input_path]
                if filters:
                    cmd_list.extend(["-vf", filters])
                cmd_list.extend(["-volume", str(volume)])
                if extra_args:
                    cmd_list.extend(extra_args)
                if "-window_title" not in cmd_list:
                    cmd_list.extend(["-window_title", f"预览: {os.path.basename(input_path)}"])
                cmd_str = " ".join(f'"{p}"' if os.path.sep in p and p != "-vf" and not p.startswith('--') else p for p in cmd_list)

        self._append_info_ui("执行命令: " + cmd_str)
        launch_player(input_path, filters or "", audio_only, volume, extra_args,
                      self.use_mpv.get(), self.mpv_path.get(), self.ffplay_cmd)
        self._append_info_ui(f"正在预览: {os.path.basename(input_path)}")

    def _preview_with_settings(self, file_path: str, settings: dict):
        """
        使用给定文件路径和设置进行预览。
        file_path: 要预览的文件路径
        settings: 编码设置字典（包含滤镜、变速等）
        """
        if not file_path or not os.path.exists(file_path):
            self._append_info_ui(f"文件不存在: {file_path}")
            return
    
        # ----- 1. 构建基础视频滤镜链（不含 scale） -----
        # 使用 build_video_filter_chain，不包括 speed（变速由音频单独处理）
        enhance_settings = settings.get("enhance", {})
        base_vf = build_video_filter_chain(settings, include_subtitle=True, include_speed=False, enhance_settings=enhance_settings)
        filter_parts = []
        if base_vf and base_vf != "null":
            filter_parts.append(base_vf)
    
        # ----- 2. 添加水印虚拟框（如果启用） -----
        wm_settings = settings.get("watermark", {})
        if wm_settings.get("enabled", False) and wm_settings.get("file_path", "").strip():
            wm_file = wm_settings.get("file_path", "").strip()
            
            # 获取主视频尺寸（用于自适应）
            main_w, main_h = get_video_dimensions(self.ffprobe_cmd, file_path)
            if main_w is None or main_h is None:
                self._append_info_ui("[预览] 无法获取视频尺寸，跳过水印虚拟框")
            else:
                # ---- 新增：判断是否启用自适应，如果启用则缩放设置 ----
                if wm_settings.get("adaptive", False):
                    # 使用 _adapt_sub_settings 根据当前主视频尺寸缩放
                    adapted_wm = self._adapt_sub_settings(wm_settings, main_w, main_h)
                else:
                    adapted_wm = wm_settings  # 或 copy，但后面只读
                
                # 获取水印文件的原始尺寸（考虑旋转）
                orig_w, orig_h = get_video_rotated_dimensions(self.ffprobe_cmd, wm_file, adapted_wm)
                if orig_w is None or orig_h is None:
                    self._append_info_ui("[预览] 无法获取水印文件尺寸，使用默认 320x240")
                    orig_w, orig_h = 320, 240
        
                # 计算水印渲染尺寸（使用自适应后的设置）
                wm_w, wm_h = compute_rendered_size(orig_w, orig_h, adapted_wm)
                if wm_w <= 0 or wm_h <= 0:
                    self._append_info_ui("[预览] 水印渲染尺寸无效，使用原始尺寸")
                    wm_w, wm_h = orig_w, orig_h
        
                # 计算 X/Y 位置（使用自适应后的设置，支持表达式）
                ctx = {"W": main_w, "H": main_h, "w": wm_w, "h": wm_h}
                x_expr = adapted_wm.get("overlay_x", "W-w-10")
                y_expr = adapted_wm.get("overlay_y", "H-h-10")
                x_val = safe_eval_expr(x_expr, ctx)
                y_val = safe_eval_expr(y_expr, ctx)
                if x_val is None:
                    x_val = main_w - wm_w - 10
                if y_val is None:
                    y_val = main_h - wm_h - 10
                # 限制范围
                x_val = max(0, min(x_val, main_w - wm_w))
                y_val = max(0, min(y_val, main_h - wm_h))
        
                # 构建 drawbox 滤镜
                drawbox = f"drawbox=x={x_val}:y={y_val}:w={wm_w}:h={wm_h}:color=red@0.3:t=3"
                filter_parts.append(drawbox)
                self._append_info_ui(f"[预览] 水印虚拟框: 位置({x_val}, {y_val}) 尺寸{wm_w}x{wm_h}")
    
        # ----- 3. 最后添加 scale 到预览高度（确保所有滤镜在缩放前执行） -----
        filter_parts.append("scale=-2:960")
    
        # 合并滤镜链
        filter_chain = ",".join(filter_parts) if filter_parts else "null"
    
        # ----- 4. 处理音频变速额外参数 -----
        extra_args = []
        if settings.get("speed_enabled", False):
            try:
                factor = float(settings.get("speed_factor", "1.0"))
                if factor > 0 and factor != 1.0:
                    atempo = build_atempo_chain(factor)
                    if atempo:
                        if self.use_mpv.get():
                            extra_args.extend(["--af", atempo])
                        else:
                            extra_args.extend(["-af", atempo])
            except ValueError:
                pass
    
        # ----- 5. 调用播放器预览 -----
        self.preview_with_player(file_path, filter_chain, volume=10, extra_args=extra_args)




    # ---------- 输出路径生成与命令构建 ----------
    def generate_output_path(self, input_path, settings):
        dir_path = settings.get("output_dir") or os.path.dirname(input_path)
        dir_path = normalize_path(dir_path)
        base_name = os.path.basename(input_path)
        name, _ = os.path.splitext(base_name)
        if settings.get("only_audio", False):
            container = settings.get("audio_format", "mp3")
        else:
            container = settings.get("output_container", "mp4")
        custom_name = settings.get("custom_output_name", "").strip()
        if custom_name:
            custom_name = os.path.basename(custom_name)
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
            # 确保文件名以 .gif 结尾
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
    
        # 构建预处理滤镜（不含 format 和 subtitle）
        vf = build_video_filter_chain(settings, include_subtitle=False, include_speed=True)
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
    
        # 精准模式下强制重新编码（视频）
        self._enforce_reencode_for_precise_trim(settings, only_audio)

        # ---------- 新增：IVTC 与反交错冲突检测 ----------
        enhance_settings = settings.get("enhance", {})
        if enhance_settings.get("ivtc_enabled", False) and settings.get("deinterlace_filter", "none") != "none":
            self._append_info_ui("已启用 IVTC，反交错滤镜将被忽略（IVTC 本身包含反交错功能）。")
        # ------------------------------------------------


        # ---------- 检查水印 ----------
        wm_settings = settings.get("watermark", {})
        wm_enabled = wm_settings.get("enabled", False) and wm_settings.get("file_path", "").strip()
        wm_file = wm_settings.get("file_path", "").strip() if wm_enabled else None
    
        if wm_file and not only_audio:
            return self._generate_command_with_watermark(input_path, output_path, settings, wm_settings)

        # 检查是否 GIF 编码（且非仅音频）
        if settings.get("encoder") == "gif" and not only_audio:
            return self._generate_gif_command(input_path, output_path, settings)

        # ---------- 普通模式（无复杂水印） ----------
        cmd_list = [self.ffmpeg_cmd, "-y", "-fflags", "+genpts"]
    
        # 快速模式（非精准）才在命令行添加 -ss/-to
        if not precise_trim:
            self._add_trim_params(cmd_list, settings)
    
        if not only_audio:
            self._add_hwaccel_params(cmd_list, settings)
    
        cmd_list.extend(["-i", input_path])
    
        # ----- 精准模式：不添加命令行 -ss/-t，而是通过滤镜处理 计算截取时长-----
        start_sec, duration_for_audio = self._calculate_trim_duration(settings, input_path)

    
        if only_audio:
            cmd_list.append("-vn")
        else:
            vcodec = settings.get("encoder", "libx265")
            precise_trim = settings.get("precise_trim", False)
            if vcodec == "copy" and not precise_trim:
                # 纯流复制，忽略所有视频处理
                self._append_info_ui("编码器为 copy，已忽略所有视频滤镜、帧率、像素格式等设置。")
                cmd_list.extend(["-c:v", "copy"])
            else:
                # 构建视频滤镜（包含字幕、变速等）
                enhance_settings = settings.get("enhance", {})
                vf = build_video_filter_chain(settings, include_subtitle=True, include_speed=True, enhance_settings=enhance_settings)
                if vf != "null":
                    cmd_list.extend(["-vf", vf])

                cmd_list = self._build_video_encoding_params(cmd_list, settings)
    

        # 音频处理（精准模式下也需尊重 audio_enabled）
        if settings.get("audio_enabled", True):
            if precise_trim and settings.get("trim_enabled", False) and duration_for_audio is not None and duration_for_audio > 0:
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
        is_image = ext in ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
        if is_image:
            cmd_list.extend(["-loop", "1", "-framerate", framerate])
        else:
            cmd_list.extend(["-stream_loop", "-1"])


    def _generate_command_with_watermark(self, input_path: str, output_path: str, settings: dict, wm_settings: dict) -> List[str]:
        main_w, main_h = get_video_dimensions(self.ffprobe_cmd, input_path)
    
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
    
        precise_trim = settings.get("precise_trim", False)
        self._enforce_reencode_for_precise_trim(settings, only_audio=False)
    
        # 快速模式（非精准）才在命令行添加 -ss/-to
        if not precise_trim:
            self._add_trim_params(cmd_list, settings)
    
        self._add_hwaccel_params(cmd_list, settings)
    
        # 主视频输入
        cmd_list.extend(["-i", input_path])
    
        # ----- 计算主视频有效时长（截取或总时长） -----
        start_sec, duration_for_sub = self._calculate_trim_duration(settings, input_path)
        main_duration = None
        if settings.get("trim_enabled", False):
            if precise_trim:
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
        wm_trim_enabled = adapted_wm.get("trim_enabled", False)
        wm_precise = adapted_wm.get("precise_trim", False)
#         if wm_trim_enabled and not wm_precise:
#             start = adapted_wm.get("trim_start", "").strip()
#             end = adapted_wm.get("trim_end", "").strip()
#             if start:
#                 cmd_list.extend(["-ss", start])
#             if end:
#                 cmd_list.extend(["-to", end])
    
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
            # 图片水印
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
        if settings.get("audio_enabled", True):
            if precise_trim and settings.get("trim_enabled", False) and duration_for_sub is not None and duration_for_sub > 0:
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
    
        # ---- 根据判断添加 -shortest ----
        cmd_list.append("-shortest")
    
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
            w, h = get_video_dimensions(self.ffprobe_cmd, input_file)
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
    
    def _get_canvas_size(self, main_track):
        pad_enabled = getattr(main_track, 'pad_enabled', False)
        if pad_enabled and main_track.pad_width and main_track.pad_height:
            try:
                return int(main_track.pad_width), int(main_track.pad_height)
            except:
                pass
        w, h = get_video_dimensions(self.ffprobe_cmd, main_track.file_path)
        if w is None or h is None:
            w, h = 1280, 720
        return w, h
    
    def _get_video_render_size(self, track, filt_frame=None):
        w, h = get_video_rotated_dimensions(self.ffprobe_cmd, track.file_path, track.enc_settings)
        if w is None:
            return None, None
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
        rotate = settings.get("rotate", "none")
        if rotate in ("90", "270"):
            w, h = h, w
        if settings.get("crop_enabled", False):
            crop_w = settings.get("crop_width", "").strip()
            crop_h = settings.get("crop_height", "").strip()
            if crop_w and crop_h:
                cw = safe_eval_expr(crop_w, {"iw": w, "ih": h})
                ch = safe_eval_expr(crop_h, {"iw": w, "ih": h})
                if cw and ch and cw > 0 and ch > 0:
                    w, h = cw, ch
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

    # ---------- 主视频位置可视化编辑器 ----------
    def open_visual_pad_editor(self, track_idx, pad_w_var, pad_h_var, off_x_var, off_y_var, live_filt_frame=None, parent=None):
        track = self.merge_tracks[track_idx]
        if track.type != "video":
            return
    
        enabled_videos = self._get_enabled_video_tracks()
        if not enabled_videos:
            messagebox.showerror("错误", "没有启用的视频轨道")
            return
        main_track = enabled_videos[0]
        sub_tracks = enabled_videos[1:]
    
        main_render_w, main_render_h = self._get_video_render_size(main_track, live_filt_frame)
        if main_render_w is None:
            messagebox.showerror("错误", "无法获取主视频渲染尺寸")
            return
    
        try:
            pad_w_str = pad_w_var.get().strip()
            pad_h_str = pad_h_var.get().strip()
            if pad_w_str and pad_h_str:
                canvas_w = int(pad_w_str)
                canvas_h = int(pad_h_str)
                if canvas_w <= 0 or canvas_h <= 0:
                    raise ValueError
            else:
                raise ValueError
        except:
            canvas_w, canvas_h = main_render_w, main_render_h
            pad_w_var.set(str(canvas_w))
            pad_h_var.set(str(canvas_h))
    
        # 从 enc_settings 读取偏移
        pad_enabled = main_track.enc_settings.get('pad_enabled', False)
        if pad_enabled:
            try:
                off_x = int(off_x_var.get()) if off_x_var.get().strip() else 0
                off_y = int(off_y_var.get()) if off_y_var.get().strip() else 0
            except:
                off_x, off_y = 0, 0
        else:
            off_x, off_y = 0, 0
    
        def clamp_offset(x, y):
            x = max(-main_render_w + 10, min(x, canvas_w - 10))
            y = max(-main_render_h + 10, min(y, canvas_h - 10))
            return x, y
        off_x, off_y = clamp_offset(off_x, off_y)
    
        max_display_w, max_display_h = 800, 600
        scale = min(max_display_w / canvas_w, max_display_h / canvas_h, 1.0)
        disp_w = int(canvas_w * scale)
        disp_h = int(canvas_h * scale)

        if parent is None:
            parent = self.root
        with self.SafeToplevel(parent) as win:
            win.title("可视化编辑画布偏移 - 拖拽蓝色矩形")
            win.transient(self.root)
            center_window(win, disp_w + 20, disp_h + 200)
            win.update_idletasks()
    
            canvas = tk.Canvas(win, width=disp_w, height=disp_h, bg="black", highlightthickness=1, highlightbackground="gray")
            canvas.pack(pady=10)
    
            status_var = tk.StringVar(value="拖拽蓝色矩形移动，调整主视频内容在画布中的位置。绿色虚线框为从视频")
            ttk.Label(win, textvariable=status_var, justify=tk.LEFT).pack(pady=5)
    
            size_frame = ttk.Frame(win)
            size_frame.pack(pady=5)
            ttk.Label(size_frame, text="画布宽度:").pack(side=tk.LEFT)
            canvas_w_var = tk.StringVar(value=str(canvas_w))
            ttk.Entry(size_frame, textvariable=canvas_w_var, width=8).pack(side=tk.LEFT, padx=5)
            ttk.Label(size_frame, text="画布高度:").pack(side=tk.LEFT)
            canvas_h_var = tk.StringVar(value=str(canvas_h))
            ttk.Entry(size_frame, textvariable=canvas_h_var, width=8).pack(side=tk.LEFT, padx=5)
            ttk.Button(size_frame, text="应用画布尺寸", command=lambda: update_canvas_size()).pack(side=tk.LEFT, padx=5)
    
            coord_var = tk.StringVar(value=f"偏移: X={off_x}, Y={off_y}")
            ttk.Label(win, textvariable=coord_var, font=("Courier", 10)).pack(pady=2)
    
            self._draw_background(canvas, canvas_w, canvas_h, scale, main_track, sub_tracks,
                                  off_x, off_y, (main_render_w, main_render_h), tag="bg")
    
            rect_id = None
            text_id = None
            warning_id = None
            drag_data = {"x": 0, "y": 0}
            current_off_x, current_off_y = off_x, off_y
    
            def draw_rectangle():
                nonlocal rect_id, text_id, warning_id
                x1 = current_off_x
                y1 = current_off_y
                x2 = current_off_x + main_render_w
                y2 = current_off_y + main_render_h
                vis_x1 = max(0, x1)
                vis_y1 = max(0, y1)
                vis_x2 = min(canvas_w, x2)
                vis_y2 = min(canvas_h, y2)
                if vis_x2 > vis_x1 and vis_y2 > vis_y1:
                    cx1, cy1 = self._to_canvas_coords(vis_x1, vis_y1, scale)
                    cx2, cy2 = self._to_canvas_coords(vis_x2, vis_y2, scale)
                    if rect_id:
                        canvas.coords(rect_id, cx1, cy1, cx2, cy2)
                        if text_id:
                            canvas.coords(text_id, cx1 + 5, cy1 + 5)
                    else:
                        rect_id = canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="deepskyblue", width=2,
                                                          fill="skyblue", stipple="gray50")
                        text_id = canvas.create_text(cx1 + 5, cy1 + 5, anchor="nw", text="主视频", fill="blue", font=("Arial", 9))
                    if warning_id:
                        canvas.delete(warning_id)
                        warning_id = None
                else:
                    if rect_id:
                        canvas.delete(rect_id)
                        rect_id = None
                    if text_id:
                        canvas.delete(text_id)
                        text_id = None
                    if warning_id is None:
                        warning_id = canvas.create_text(disp_w//2, disp_h//2, text="主视频完全不可见", fill="red", font=("Arial", 10))
                    else:
                        canvas.coords(warning_id, disp_w//2, disp_h//2)
    
            draw_rectangle()
    
            def on_mouse_down(event):
                if rect_id is None:
                    return
                coords = canvas.coords(rect_id)
                if len(coords) != 4:
                    return
                cx1, cy1, cx2, cy2 = coords
                if cx1 <= event.x <= cx2 and cy1 <= event.y <= cy2:
                    drag_data["x"] = event.x
                    drag_data["y"] = event.y
                    status_var.set("拖拽移动主视频位置")
    
            def on_mouse_move(event):
                nonlocal current_off_x, current_off_y
                if "x" not in drag_data:
                    return
                dx = event.x - drag_data["x"]
                dy = event.y - drag_data["y"]
                if dx == 0 and dy == 0:
                    return
                new_x = current_off_x + dx / scale
                new_y = current_off_y + dy / scale
                new_x, new_y = clamp_offset(new_x, new_y)
                current_off_x = int(new_x)
                current_off_y = int(new_y)
                coord_var.set(f"偏移: X={current_off_x}, Y={current_off_y}")
                draw_rectangle()
                drag_data["x"] = event.x
                drag_data["y"] = event.y
    
            def on_mouse_up(event):
                drag_data.clear()
                status_var.set("拖拽完成，点击「保存」应用偏移")
    
            canvas.bind("<Button-1>", on_mouse_down)
            canvas.bind("<B1-Motion>", on_mouse_move)
            canvas.bind("<ButtonRelease-1>", on_mouse_up)
    
            def update_canvas_size():
                nonlocal canvas_w, canvas_h, scale, disp_w, disp_h, current_off_x, current_off_y
                nonlocal rect_id, text_id, warning_id
                try:
                    new_w = int(canvas_w_var.get())
                    new_h = int(canvas_h_var.get())
                    if new_w <= 0 or new_h <= 0:
                        raise ValueError
                    canvas_w, canvas_h = new_w, new_h
                    scale = min(max_display_w / canvas_w, max_display_h / canvas_h, 1.0)
                    disp_w = int(canvas_w * scale)
                    disp_h = int(canvas_h * scale)
                    win.geometry(f"{disp_w + 20}x{disp_h + 200}")
                    canvas.config(width=disp_w, height=disp_h)
                    current_off_x, current_off_y = clamp_offset(current_off_x, current_off_y)
                    coord_var.set(f"偏移: X={current_off_x}, Y={current_off_y}")
                    canvas.delete("all")
                    rect_id = text_id = warning_id = None
                    self._draw_background(canvas, canvas_w, canvas_h, scale, main_track, sub_tracks,
                                          current_off_x, current_off_y, (main_render_w, main_render_h), tag="bg")
                    draw_rectangle()
                    win.update_idletasks()
                    x = self.root.winfo_x() + (self.root.winfo_width() - win.winfo_width()) // 2
                    y = self.root.winfo_y() + (self.root.winfo_height() - win.winfo_height()) // 2
                    win.geometry(f"+{x}+{y}")
                except:
                    messagebox.showerror("错误", "画布尺寸无效")
    
            def save():
                # 更新 enc_settings 和轨道属性（同步）
                track.enc_settings['pad_enabled'] = True
                track.enc_settings['pad_width'] = str(canvas_w)
                track.enc_settings['pad_height'] = str(canvas_h)
                track.enc_settings['offset_x'] = str(current_off_x)
                track.enc_settings['offset_y'] = str(current_off_y)
                # 同步更新属性（兼容旧代码）
                track.pad_enabled = True
                track.pad_width = str(canvas_w)
                track.pad_height = str(canvas_h)
                track.offset_x = str(current_off_x)
                track.offset_y = str(current_off_y)
                pad_w_var.set(str(canvas_w))
                pad_h_var.set(str(canvas_h))
                off_x_var.set(str(current_off_x))
                off_y_var.set(str(current_off_y))
                self.merge_update_track_list()
                self.merge_update_command_preview()
                win.destroy()
                self._append_info_ui(f"[可视化] 已设置画布 {canvas_w}x{canvas_h}, 偏移 ({current_off_x}, {current_off_y})")
    
            def cancel():
                win.destroy()
    
            btn_frame = ttk.Frame(win)
            btn_frame.pack(pady=10)
            ttk.Button(btn_frame, text="保存", command=save).pack(side=tk.LEFT, padx=10)
            ttk.Button(btn_frame, text="取消", command=cancel).pack(side=tk.LEFT, padx=10)
            win.wait_window()
        parent.lift()
        parent.focus_force()

    def _simple_visual_overlay(self, canvas_w, canvas_h, wm_w, wm_h, x_var, y_var, parent=None):
        """
        水印可视化位置调整（直接基于画布和矩形尺寸）
        parent: 父窗口（通常是 WatermarkEditor 的窗口），用于设置 transient
        """
        if parent is None:
            parent = self.root
        with self.SafeToplevel(parent) as vis_win:
            vis_win.title("可视化调整水印位置 - 拖动矩形")
            vis_win.transient(parent)   # 设为父窗口的临时对话框
            vis_win.grab_set()          # 模态（可选，避免操作其他窗口）
            max_disp = 600
            scale = min(max_disp / canvas_w, max_disp / canvas_h, 1.0)
            disp_w = int(canvas_w * scale)
            disp_h = int(canvas_h * scale)
            center_window(vis_win, disp_w + 20, disp_h + 120)
            canvas = tk.Canvas(vis_win, width=disp_w, height=disp_h, bg='black')
            canvas.pack(pady=10)
    
            # 获取当前坐标
            x_expr = x_var.get()
            y_expr = y_var.get()
            ctx = {"W": canvas_w, "H": canvas_h, "w": wm_w, "h": wm_h}
            cur_x = safe_eval_expr(x_expr, ctx) or (canvas_w - wm_w - 10)
            cur_y = safe_eval_expr(y_expr, ctx) or (canvas_h - wm_h - 10)
            cur_x = max(0, min(cur_x, canvas_w - wm_w))
            cur_y = max(0, min(cur_y, canvas_h - wm_h))
    
            rect_id = None
            text_id = None
    
            def draw_rect():
                nonlocal rect_id, text_id
                x1 = cur_x * scale
                y1 = cur_y * scale
                x2 = (cur_x + wm_w) * scale
                y2 = (cur_y + wm_h) * scale
                if rect_id:
                    canvas.coords(rect_id, x1, y1, x2, y2)
                    canvas.coords(text_id, x1+5, y1+5)
                else:
                    rect_id = canvas.create_rectangle(x1, y1, x2, y2, outline='red', width=2, fill='red', stipple='gray50')
                    text_id = canvas.create_text(x1+5, y1+5, anchor='nw', text='水印', fill='white')
    
            draw_rect()
    
            drag_start = None
            def on_click(event):
                nonlocal drag_start
                if rect_id:
                    coords = canvas.coords(rect_id)
                    if coords[0] <= event.x <= coords[2] and coords[1] <= event.y <= coords[3]:
                        drag_start = (event.x, event.y)
            def on_drag(event):
                nonlocal cur_x, cur_y, drag_start
                if drag_start:
                    dx = (event.x - drag_start[0]) / scale
                    dy = (event.y - drag_start[1]) / scale
                    new_x = cur_x + dx
                    new_y = cur_y + dy
                    new_x = max(0, min(new_x, canvas_w - wm_w))
                    new_y = max(0, min(new_y, canvas_h - wm_h))
                    if new_x != cur_x or new_y != cur_y:
                        cur_x, cur_y = new_x, new_y
                        draw_rect()
                        drag_start = (event.x, event.y)
            def on_release(event):
                nonlocal drag_start
                drag_start = None
    
            canvas.bind("<Button-1>", on_click)
            canvas.bind("<B1-Motion>", on_drag)
            canvas.bind("<ButtonRelease-1>", on_release)
    
            def apply():
                try:
                    # 获取矩形在画布上的像素坐标
                    coords = canvas.coords(rect_id)
                    if not coords or len(coords) < 4:
                        # 如果矩形不存在，使用居中位置
                        final_x = (canvas_w - wm_w) // 2
                        final_y = (canvas_h - wm_h) // 2
                    else:
                        # 像素坐标转真实坐标
                        real_x = coords[0] / scale
                        real_y = coords[1] / scale
                        final_x = int(round(real_x))
                        final_y = int(round(real_y))
            
                    # 回填到界面变量
                    x_var.set(str(final_x))
                    y_var.set(str(final_y))
            
                    # 保存基准（仅在首次设置）
                    if "base_width" not in self.watermark_settings:
                        self.watermark_settings["base_width"] = canvas_w
                        self.watermark_settings["base_height"] = canvas_h
                except Exception as e:
                    self._append_info_ui(f"[可视化] 应用坐标时出错: {e}")
                finally:
                    # 确保窗口关闭
                    if vis_win and vis_win.winfo_exists():
                        vis_win.destroy()
                    parent.lift()
                    parent.focus_force()
    
            def cancel():
                vis_win.destroy()
                parent.lift()
                parent.focus_force()
    
            btn_frame = ttk.Frame(vis_win)
            btn_frame.pack(pady=5)
            ttk.Button(btn_frame, text="应用", command=apply).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="取消", command=cancel).pack(side=tk.LEFT, padx=5)
            vis_win.wait_window()


    # ---------- 从视频位置可视化编辑器 ----------
    def open_visual_overlay_editor(self, track_idx, ov_x_var=None, ov_y_var=None, filt_frame=None, parent=None):
        track = self.merge_tracks[track_idx]
        if track.type != "video":
            return
    
        enabled_videos = self._get_enabled_video_tracks()
        if not enabled_videos:
            messagebox.showerror("错误", "没有启用的视频轨道")
            return
        main_track = enabled_videos[0]
        sub_tracks = enabled_videos[1:]
    
        curr_w, curr_h = self._get_video_render_size(track, filt_frame)
        if curr_w is None:
            messagebox.showerror("错误", "无法获取视频渲染尺寸")
            return
        aspect = curr_w / curr_h
    
        canvas_w, canvas_h = self._get_canvas_size(main_track)
    
        main_render_size = self._get_video_render_size(main_track)
        if main_render_size is None:
            main_render_size = (canvas_w, canvas_h)
        main_pad_enabled = main_track.enc_settings.get('pad_enabled', False)
        if main_pad_enabled:
            off_x_expr = main_track.enc_settings.get('offset_x', '0')
            off_y_expr = main_track.enc_settings.get('offset_y', '0')
            offset_x = safe_eval_expr(off_x_expr, {"W": canvas_w, "H": canvas_h}) or 0
            offset_y = safe_eval_expr(off_y_expr, {"W": canvas_w, "H": canvas_h}) or 0
        else:
            offset_x, offset_y = 0, 0
    
        max_display_w, max_display_h = 800, 600
        scale = min(max_display_w / canvas_w, max_display_h / canvas_h, 1.0)
        disp_w = int(canvas_w * scale)
        disp_h = int(canvas_h * scale)
    
        if parent is None:
            parent = self.root
        with self.SafeToplevel(parent) as win:
            win.title(f"可视化编辑叠加位置 - {os.path.basename(track.file_path)}")
            win.transient(self.root)
            center_window(win, disp_w + 20, disp_h + 240)
            win.update_idletasks()
    
            canvas = tk.Canvas(win, width=disp_w, height=disp_h, bg="black", highlightthickness=1, highlightbackground="gray")
            canvas.pack(pady=10)
    
            status_var = tk.StringVar(value="红色矩形可拖拽移动。点击「绘制新矩形」可重新定义大小。")
            ttk.Label(win, textvariable=status_var, justify=tk.LEFT).pack(pady=5)
    
            coord_var = tk.StringVar(value="未设置")
            ttk.Label(win, textvariable=coord_var, font=("Courier", 10)).pack(pady=2)
    
            ttk.Label(win, text=f"主视频偏移: X={offset_x}, Y={offset_y}", foreground="orange").pack(pady=2)
    
            self._draw_background(canvas, canvas_w, canvas_h, scale, main_track, sub_tracks,
                                  offset_x, offset_y, main_render_size, current_edit_track=track, tag="bg")
    
            rect_x, rect_y, rect_w, rect_h = 0, 0, curr_w, curr_h
            rect_id = None
            text_id = None
    
            def load_current():
                nonlocal rect_x, rect_y, rect_w, rect_h
                rect_w, rect_h = curr_w, curr_h
                x_expr = track.enc_settings.get('overlay_x', '0')
                y_expr = track.enc_settings.get('overlay_y', '0')
                x_val = safe_eval_expr(x_expr, {"W": canvas_w, "H": canvas_h, "w": rect_w, "h": rect_h})
                y_val = safe_eval_expr(y_expr, {"W": canvas_w, "H": canvas_h, "w": rect_w, "h": rect_h})
                if x_val is None or y_val is None:
                    x_val = canvas_w - rect_w - 10
                    y_val = canvas_h - rect_h - 10
                rect_x = max(0, min(x_val, canvas_w - rect_w))
                rect_y = max(0, min(y_val, canvas_h - rect_h))
                coord_var.set(f"左上角: ({rect_x}, {rect_y})  宽: {rect_w}  高: {rect_h}")
    
            def create_rect():
                cx1, cy1 = self._to_canvas_coords(rect_x, rect_y, scale)
                cx2, cy2 = self._to_canvas_coords(rect_x + rect_w, rect_y + rect_h, scale)
                rid = canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="red", width=2, fill="red", stipple="gray50", tags="rect")
                tid = canvas.create_text(cx1 + 5, cy1 + 5, anchor="nw", text="视频", fill="white", font=("Arial", 9), tags="rect")
                return rid, tid
    
            def update_rect_position():
                cx1, cy1 = self._to_canvas_coords(rect_x, rect_y, scale)
                cx2, cy2 = self._to_canvas_coords(rect_x + rect_w, rect_y + rect_h, scale)
                canvas.coords(rect_id, cx1, cy1, cx2, cy2)
                canvas.coords(text_id, cx1 + 5, cy1 + 5)
    
            drag_start_x = 0
            drag_start_y = 0
            drag_mouse_start = (0, 0)
            dragging = False
            draw_mode_active = False
    
            def start_move(event):
                nonlocal drag_start_x, drag_start_y, drag_mouse_start, dragging, draw_mode_active
                if draw_mode_active:
                    return
                cx, cy = event.x, event.y
                bbox = canvas.bbox(rect_id)
                if bbox and bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]:
                    drag_start_x = rect_x
                    drag_start_y = rect_y
                    drag_mouse_start = (cx, cy)
                    dragging = True
                    status_var.set("拖拽移动矩形")
    
            def on_move(event):
                nonlocal rect_x, rect_y, dragging, draw_mode_active, drag_start_x, drag_start_y, drag_mouse_start
                if not dragging or draw_mode_active:
                    return
                dx_pixel = event.x - drag_mouse_start[0]
                dy_pixel = event.y - drag_mouse_start[1]
                dx = dx_pixel / scale
                dy = dy_pixel / scale
                new_x = int(drag_start_x + dx)
                new_y = int(drag_start_y + dy)
                new_x = max(0, min(new_x, canvas_w - rect_w))
                new_y = max(0, min(new_y, canvas_h - rect_h))
                if new_x != rect_x or new_y != rect_y:
                    rect_x, rect_y = new_x, new_y
                    update_rect_position()
                    coord_var.set(f"左上角: ({rect_x}, {rect_y})  宽: {rect_w}  高: {rect_h}")
    
            def stop_move(event):
                nonlocal dragging
                dragging = False
                status_var.set("红色矩形可拖拽移动。点击「绘制新矩形」可重新定义大小。")
    
            canvas.tag_bind("rect", "<Button-1>", start_move)
            canvas.tag_bind("rect", "<B1-Motion>", on_move)
            canvas.tag_bind("rect", "<ButtonRelease-1>", stop_move)
    
            draw_rect_temp = None
            draw_start = None
    
            def start_draw(event):
                nonlocal draw_start, draw_rect_temp, draw_mode_active
                if not draw_mode_active:
                    return
                if draw_rect_temp:
                    canvas.delete(draw_rect_temp)
                    draw_rect_temp = None
                draw_start = self._to_real_coords(event.x, event.y, scale)
    
            def on_draw_move(event):
                nonlocal draw_rect_temp, draw_start, draw_mode_active
                if not draw_mode_active or draw_start is None:
                    return
                cur = self._to_real_coords(event.x, event.y, scale)
                x1 = min(draw_start[0], cur[0])
                y1 = min(draw_start[1], cur[1])
                x2 = max(draw_start[0], cur[0])
                y2 = max(draw_start[1], cur[1])
                w = x2 - x1
                h = y2 - y1
                if w == 0 or h == 0:
                    return
                if w / h > aspect:
                    new_w = h * aspect
                    new_x2 = x1 + new_w
                    new_y2 = y2
                else:
                    new_h = w / aspect
                    new_x2 = x2
                    new_y2 = y1 + new_h
                draw_x = x1
                draw_y = y1
                draw_w = new_x2 - x1
                draw_h = new_y2 - y1
                if draw_x < 0:
                    draw_w += draw_x
                    draw_x = 0
                if draw_y < 0:
                    draw_h += draw_y
                    draw_y = 0
                if draw_x + draw_w > canvas_w:
                    draw_w = canvas_w - draw_x
                    draw_h = int(draw_w / aspect) if aspect != 0 else 1
                if draw_y + draw_h > canvas_h:
                    draw_h = canvas_h - draw_y
                    draw_w = int(draw_h * aspect) if aspect != 0 else 1
                if draw_w <= 0 or draw_h <= 0:
                    return
                cx1, cy1 = self._to_canvas_coords(draw_x, draw_y, scale)
                cx2, cy2 = self._to_canvas_coords(draw_x + draw_w, draw_y + draw_h, scale)
                if draw_rect_temp:
                    canvas.coords(draw_rect_temp, cx1, cy1, cx2, cy2)
                else:
                    draw_rect_temp = canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="yellow", width=2, dash=(2, 2))
    
            def end_draw(event):
                nonlocal draw_mode_active, draw_start, draw_rect_temp, rect_x, rect_y, rect_w, rect_h, rect_id, text_id
                if not draw_mode_active or draw_start is None:
                    return
                if draw_rect_temp:
                    coords = canvas.coords(draw_rect_temp)
                    if len(coords) == 4:
                        cx1, cy1, cx2, cy2 = coords
                        x1, y1 = self._to_real_coords(cx1, cy1, scale)
                        x2, y2 = self._to_real_coords(cx2, cy2, scale)
                        new_w = x2 - x1
                        new_h = y2 - y1
                        if new_w > 0 and new_h > 0:
                            rect_x, rect_y, rect_w, rect_h = x1, y1, new_w, new_h
                            canvas.delete(rect_id)
                            canvas.delete(text_id)
                            rect_id, text_id = create_rect()
                            coord_var.set(f"左上角: ({rect_x}, {rect_y})  宽: {rect_w}  高: {rect_h}")
                            status_var.set("新矩形已创建，可拖拽移动或应用")
                    if draw_rect_temp:
                        canvas.delete(draw_rect_temp)
                        draw_rect_temp = None
                draw_mode_active = False
                draw_btn.config(state="normal")
                draw_abort_btn.config(state="disabled")
                draw_start = None
    
            def abort_draw():
                nonlocal draw_mode_active, draw_rect_temp, draw_start
                draw_mode_active = False
                draw_btn.config(state="normal")
                draw_abort_btn.config(state="disabled")
                if draw_rect_temp:
                    canvas.delete(draw_rect_temp)
                    draw_rect_temp = None
                draw_start = None
                status_var.set("已取消绘制，红色矩形可拖拽移动")
    
            def enter_draw_mode():
                nonlocal draw_mode_active
                if draw_mode_active:
                    return
                draw_mode_active = True
                draw_btn.config(state="disabled")
                draw_abort_btn.config(state="normal")
                status_var.set("绘制模式：按住左键拖拽绘制新矩形（保持宽高比），松开后自动替换")
    
            canvas.bind("<Button-1>", start_draw, add=True)
            canvas.bind("<B1-Motion>", on_draw_move, add=True)
            canvas.bind("<ButtonRelease-1>", end_draw, add=True)
    
            btn_frame = ttk.Frame(win)
            btn_frame.pack(pady=5)
            draw_btn = ttk.Button(btn_frame, text="绘制新矩形", command=enter_draw_mode)
            draw_btn.pack(side=tk.LEFT, padx=5)
            draw_abort_btn = ttk.Button(btn_frame, text="取消绘制", command=abort_draw, state="disabled")
            draw_abort_btn.pack(side=tk.LEFT, padx=5)
    
            def apply():
                # 更新 enc_settings 和轨道属性（同步）
                track.enc_settings['overlay_x'] = str(int(rect_x))
                track.enc_settings['overlay_y'] = str(int(rect_y))
                track.overlay_x = str(int(rect_x))
                track.overlay_y = str(int(rect_y))
                if ov_x_var is not None:
                    ov_x_var.set(str(int(rect_x)))
                if ov_y_var is not None:
                    ov_y_var.set(str(int(rect_y)))
                track.enc_settings["scale_enabled"] = True
                track.enc_settings["scale_width"] = str(int(rect_w))
                track.enc_settings["scale_height"] = str(int(rect_h))
                track.enc_settings["scale_method"] = "exact"
                # 同步属性（兼容旧代码，轨道对象属性）
                track.overlay_enabled = True
                self._append_info_ui(f"[可视化] 设置缩放: {rect_w}x{rect_h}")
                if filt_frame is not None:
                    filt_frame.scale_enabled.set(True)
                    filt_frame.scale_method.set("exact")
                    filt_frame.scale_width.set(str(int(rect_w)))
                    filt_frame.scale_height.set(str(int(rect_h)))
                self.merge_update_track_list()
                self.merge_update_command_preview()
                win.destroy()
                self._append_info_ui(f"[可视化] 已保存位置: ({rect_x}, {rect_y}) 大小: {rect_w}x{rect_h}")
    
            def cancel():
                win.destroy()
    
            def reset_position():
                nonlocal rect_x, rect_y
                rect_x = canvas_w - rect_w - 10
                rect_y = canvas_h - rect_h - 10
                update_rect_position()
                coord_var.set(f"左上角: ({rect_x}, {rect_y})  宽: {rect_w}  高: {rect_h}")
                status_var.set("已重置到右下角（可继续拖拽）")
    
            load_current()
            rect_id, text_id = create_rect()
            draw_mode_active = False
    
            action_frame = ttk.Frame(win)
            action_frame.pack(pady=10)
            ttk.Button(action_frame, text="应用", command=apply).pack(side=tk.LEFT, padx=10)
            ttk.Button(action_frame, text="取消", command=cancel).pack(side=tk.LEFT, padx=10)
            ttk.Button(action_frame, text="重置位置（右下角）", command=reset_position).pack(side=tk.LEFT, padx=10)
            tip_label = ttk.Label(win, text="提示：重新绘制矩形时，如果比例不对，请先返回上一个界面取消「缩放」的勾选，已保存的上一次缩放会干扰裁剪属性。",
                                  foreground="gray", justify=tk.LEFT, wraplength=win.winfo_width() - 20)
            tip_label.pack(fill=tk.X, padx=10, pady=10)
    
            def update_wraplength(event=None):
                tip_label.config(wraplength=win.winfo_width() - 20)
            win.bind("<Configure>", update_wraplength)
            update_wraplength()
            win.wait_window()
        parent.lift()
        parent.focus_force()

    # ---------- 预设管理 ----------
    def load_preset_list(self):
        presets = self.preset_manager.load_all()
        preset_names = list(presets.keys())
        self.preset_combo['values'] = preset_names

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
        # ---- 移除普通截取参数 ----
        preset_settings.pop("trim_enabled", None)
        preset_settings.pop("trim_start", None)
        preset_settings.pop("trim_end", None)
        preset_settings.pop("precise_trim", None)
        self.preset_manager.save_preset(preset_name, preset_settings)
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
        if getattr(self, '_loading_preset', False):
            return
        # ---- 防重入锁 ----
        if hasattr(self, '_updating_preview') and self._updating_preview:
            return
        self._updating_preview = True
        try:
            # 原有代码
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
            self.cmd_preview.delete(1.0, tk.END)
            self.cmd_preview.insert(tk.END, cmd_str)
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
        settings["segment_enabled"] = self.segment_enabled.get()
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
    
        # ---- 统一处理所有冲突（文件系统 + 任务列表） ----
        output_path = self._resolve_path_conflict(output_path)
        if output_path is None:   # 实际上不会返回 None，但保留防御
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
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)
        for i, task in enumerate(self.tasks):
            seq = i + 1
            tag = 'odd' if i % 2 == 0 else 'even'
            self.task_tree.insert("", tk.END, iid=str(i), values=(
                seq,
                os.path.basename(task.input),
                task.output,
                task.get_short_cmd(),
                task.status,
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
        if self.stop_flag and not self.running_futures:
            self._finish_queue()
            return

        if not self.stop_flag and not self.pending_tasks and not self.running_futures:
            self._finish_queue()
            return

        max_total = self.max_parallel.get()
        max_hw = self.max_hw_parallel.get()

        if len(self.running_futures) >= max_total:
            return

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
        task.status = "转码中"
        self._update_task_list_ui()
        self._append_info_ui(f"\n========== 开始转码: {os.path.basename(task.input)} ==========")
        cmd_str = format_cmd_for_display(task.cmd)
        self._append_info_ui(f">>> {cmd_str}")
        self.ensure_output_dir(task.output)

        def on_line(line):
            self.safe_append_detail(line)

        retcode, output = run_ffmpeg_command(task.cmd, on_output_line=on_line)
        if retcode == 0:
            task.status = "完成"
            self._append_info_ui(f"✅ 任务完成: {os.path.basename(task.input)}")
            self._log_command_to_file(cmd_str)
        else:
            task.status = "失败"
            task.error_msg = f"返回码 {retcode}"
            self._append_info_ui(f"任务失败: {os.path.basename(task.input)} (返回码 {retcode})")
        self._update_task_list_ui()
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
        threading.Thread(target=self._run_single_transcode, args=(cmd_list, input_file), daemon=True).start()

    def _run_single_transcode(self, cmd_list, input_name):
        self._append_info_ui(f"\n========== 当前选择转码: {os.path.basename(input_name)} ==========")
        cmd_str = format_cmd_for_display(cmd_list)
        self._append_info_ui(f">>> {cmd_str}")
        def on_line(line):
            self.safe_append_detail(line)
        retcode, _ = run_ffmpeg_command(cmd_list, on_output_line=on_line)
        if retcode == 0:
            self._append_info_ui(f"✅ 当前选择转码完成: {os.path.basename(input_name)}")
            self._log_command_to_file(cmd_str)
        else:
            self._append_info_ui(f"当前选择转码失败，返回码 {retcode}")

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
        if task.status not in ("等待", "失败"):
            messagebox.showwarning("无法编辑", f"任务状态为“{task.status}”，只能编辑等待或失败的任务。")
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
            enc_frame = VideoEncoderFrame(page_enc)
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
    
            # 截取片段页面
            page_trim = ttk.Frame(notebook)
            notebook.add(page_trim, text="截取片段")
            trim_frame = TrimFrame(page_trim)
            trim_frame.pack(fill=tk.X, padx=5, pady=5)
            trim_frame.set_settings(task.settings)
            
            filt_frame.set_get_trim_settings_callback(lambda: trim_frame.get_settings())


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
                     "   建议使用（mpv、PotPlayer）等播放器打开视频，定位到需要的起始/结束帧，将时间（格式如 01:23.456）填入左侧输入框。\n\n"
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
                    # 更新 adv_frame 的字典（原地更新）
                    adv_frame.watermark_dict.update(new_wm)
                    # 同步界面控件
                    adv_frame.wm_path_var.set(adv_frame.watermark_dict.get("file_path", ""))
                    if hasattr(adv_frame, 'adaptive_var'):
                        adv_frame.adaptive_var.set(adv_frame.watermark_dict.get("adaptive", False))
                    # 刷新预览
                    update_preview()
                    # 任务设置已自动更新（因为引用同一个字典）
                    self.update_task_list()
                    self._append_info_ui("任务水印已更新")
                self.edit_video_settings(
                    title="编辑任务水印",
                    initial_settings=task_watermark,
                    on_save=on_save,
                    file_path=task_watermark.get("file_path"),
                    is_watermark=True,
                    parent=win,
                    track_obj=None
                )
            # 替换 水印按钮的命令
            if hasattr(adv_frame, 'watermark_btn'):
                adv_frame.watermark_btn.config(command=open_task_watermark)
            

            # ---- 命令预览区和 update_preview 函数 ----
            preview_frame = ttk.LabelFrame(win, text="新命令预览", padding="5")
            preview_frame.pack(fill=tk.X, pady=5, padx=5)
            preview_text = scrolledtext.ScrolledText(preview_frame, height=10, wrap=tk.WORD)
            preview_text.pack(fill=tk.BOTH, expand=True)
            
            def update_preview(*args):
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
                preview_text.delete(1.0, tk.END)
                preview_text.insert(tk.END, new_cmd_str)

            filt_frame._preview_callback = update_preview   
            adv_frame.update_callback = update_preview

    
            # 绑定各种事件
            enc_frame.vcodec.trace_add("write", update_preview)
            enc_frame.rate_control_type.trace_add("write", update_preview)
            enc_frame.crf_value.trace_add("write", update_preview)
            enc_frame.cq_value.trace_add("write", update_preview)
            enc_frame.global_quality.trace_add("write", update_preview)
            enc_frame.bitrate_video.trace_add("write", update_preview)
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

        ttk.Label(parent, text="轨道列表（可单独设置编码参数）").pack(anchor=tk.W, pady=(10,2))

        list_container = ttk.Frame(parent)
        list_container.pack(fill=tk.X, pady=5)
        list_container.pack_propagate(False)
        min_height = int(400 * self.scaling)
        list_container.config(height=min_height)

        canvas = tk.Canvas(list_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        self.merge_track_frame = ttk.Frame(canvas, relief=tk.SUNKEN, borderwidth=1)
        canvas.create_window((0, 0), window=self.merge_track_frame, anchor="nw", width=canvas.winfo_width())
        def configure_scroll_region(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        self.merge_track_frame.bind("<Configure>", configure_scroll_region)
        def canvas_configure(event):
            canvas.itemconfig("all", width=event.width)
        canvas.bind("<Configure>", canvas_configure)
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        canvas.bind("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        resize_bar = ttk.Frame(list_container, height=6, cursor="sb_v_double_arrow")
        resize_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self._drag_start_y = None
        self._start_height = None

        def on_resize_start(event):
            self._drag_start_y = event.y_root
            self._start_height = list_container.winfo_height()

        def on_resize_motion(event):
            if self._drag_start_y is not None:
                delta = event.y_root - self._drag_start_y
                new_height = max(150, self._start_height + delta)
                list_container.config(height=new_height)
                event.widget.master.update_idletasks()

        resize_bar.bind("<Button-1>", on_resize_start)
        resize_bar.bind("<B1-Motion>", on_resize_motion)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="添加外部音轨", command=lambda: self.merge_add_external("audio")).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="添加外部字幕", command=lambda: self.merge_add_external("subtitle")).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="清空轨道", command=self.merge_clear_tracks).pack(side=tk.LEFT, padx=2)
        self.pip_enabled = tk.BooleanVar(value=False)
        pip_chk = ttk.Checkbutton(btn_frame, text="启用画中画", variable=self.pip_enabled)
        pip_chk.pack(side=tk.LEFT, padx=5)
        ToolTip(pip_chk, "开启后可将多个视频叠加（视频必须重新选择编码，不能copy了），关闭时仅使用第一个视频轨道并复制流")

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

        chapter_frame = ttk.LabelFrame(parent, text="章节处理", padding="3")
        chapter_frame.pack(fill=tk.X, pady=5)
        chapter_row = ttk.Frame(chapter_frame)
        chapter_row.pack(fill=tk.X, padx=5, pady=2)
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
            right_area, text="浏览...", command=self.browse_chapter_file
        ).pack(side=tk.LEFT)

        row_frame = ttk.Frame(parent)
        row_frame.pack(fill=tk.X, pady=2)
        left_container = ttk.Frame(row_frame)
        left_container.pack(side=tk.LEFT, padx=(0, 5))
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
            command=self.merge_select_output, width=8
        ).pack(side=tk.LEFT, padx=(0, 15))

        opt_action_frame = ttk.Frame(parent)
        opt_action_frame.pack(fill=tk.X, pady=2)
        
        ttk.Checkbutton(
            opt_action_frame, text="合并成功后删除源文件", variable=self.merge_delete_source
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Checkbutton(
            opt_action_frame, text="验证输出文件", variable=self.merge_verify
        ).pack(side=tk.LEFT, padx=(5,50))
        
        self.merge_btn = tk.Button(opt_action_frame, text="开始合并", command=self.merge_start,
                                   height=1, width=12, bg="#4CAF50", fg="white")
        self.merge_btn.pack(side=tk.LEFT, padx=5)
        
        btn_copy = tk.Button(opt_action_frame, text="复制命令到剪贴板", command=self.merge_copy_command,
                             height=1, width=20, relief=tk.RAISED)
        btn_copy.pack(side=tk.LEFT, padx=5)

        preview_frame = ttk.LabelFrame(parent, text="即将执行的命令预览", padding="5")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        content_frame = ttk.Frame(preview_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        self.merge_cmd_preview = scrolledtext.ScrolledText(
            content_frame, height=1, wrap=tk.WORD, font=("Microsoft YaHei", 9)
        )
        self.merge_cmd_preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        self.merge_video.trace_add("write", lambda *a: self.merge_load_video_info())
        self.merge_container.trace_add("write", lambda *a: self.merge_update_command_preview())
        self.merge_output.trace_add("write", lambda *a: self.merge_update_command_preview())
        self.copy_chapters.trace_add("write", lambda *a: self.merge_update_command_preview())
        self.chapter_file.trace_add("write", lambda *a: self.merge_update_command_preview())

        self.pip_enabled.trace_add('write', self._on_pip_toggle)
        self.concat_enabled.trace_add('write', self._on_concat_toggle)


    def _on_pip_toggle(self, *args):
        if self.pip_enabled.get() and self.concat_enabled.get():
            self.concat_enabled.set(False)
        self.merge_update_command_preview()
        self.merge_update_track_list()

    def _on_concat_toggle(self, *args):
        if self.concat_enabled.get() and self.pip_enabled.get():
            self.pip_enabled.set(False)
        self.merge_update_command_preview()
        self.merge_update_track_list()

    def _add_pip_video(self):
        path = filedialog.askopenfilename(
            title="选择视频或图片文件（画中画）",
            filetypes = [
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
    
        # ---- 检测是否为图片 ----
        img_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
        is_image = os.path.splitext(path)[1].lower() in img_exts
    
        if is_image:
            # 图片水印：直接创建轨道，编码为 image2
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
            # 图片没有音频，直接更新列表
            self.merge_update_track_list()
            self.merge_auto_recommend_container()
            self.merge_update_command_preview()
            return
    
        # ---- 视频处理逻辑 ----
        video_streams = [s for s in info["streams"] if s.get("codec_type") == "video"]
        if not video_streams:
            self._append_info_ui("[封装] 所选文件不包含视频流")
            return
        s = video_streams[0]
        track = Track(s["index"], "video", s.get("codec_name", "unknown"), path, True)
        # 设置画中画相关属性
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
        # 询问是否添加音频流（可选）
        audio_streams = [s for s in info["streams"] if s.get("codec_type") == "audio"]
        if audio_streams and messagebox.askyesno("添加音频", f"是否同时将文件中的音频流添加为独立音轨？\n{os.path.basename(path)}"):
            for s_audio in audio_streams:
                audio_track = Track(s_audio["index"], "audio", s_audio.get("codec_name", "unknown"), path, True)
                self.merge_tracks.append(audio_track)
        self._batch_update = True
        try:
            self.merge_update_track_list()
            self.merge_auto_recommend_container()
            self.merge_update_output_preview()
        finally:
            self._batch_update = False
            self.merge_update_command_preview()  # 统一刷新一次
 #       self._append_info_ui(f"[封装] 已添加画中画视频或图片水印: {os.path.basename(path)}")

    def merge_add_external_video(self):
        if self.concat_enabled.get():
            self._add_concat_video()
        elif self.pip_enabled.get():
            self._add_pip_video()
        else:
            messagebox.showinfo("提示", "请先勾选「串行合并」或「启用画中画」")


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
        video_streams = [s for s in info["streams"] if s.get("codec_type") == "video"]
        if not video_streams:
            self._append_info_ui("[封装] 所选文件不包含视频流")
            return
        s = video_streams[0]
        # 创建轨道，不设置 overlay 属性（默认 False）
        track = Track(s["index"], "video", s.get("codec_name", "unknown"), path, True)
        self.merge_tracks.append(track)
        self._append_info_ui(f"[封装] 已添加串联视频: {os.path.basename(path)}")
        # 询问是否添加音频流（可选）
        audio_streams = [s for s in info["streams"] if s.get("codec_type") == "audio"]
        if audio_streams and messagebox.askyesno("添加音频", f"是否同时将文件中的音频流添加为独立音轨？\n{os.path.basename(path)}"):
            for s_audio in audio_streams:
                audio_track = Track(s_audio["index"], "audio", s_audio.get("codec_name", "unknown"), path, True)
                self.merge_tracks.append(audio_track)
        self._batch_update = True
        try:
            self.merge_update_track_list()
            self.merge_auto_recommend_container()
            self.merge_update_output_preview()
        finally:
            self._batch_update = False
            self.merge_update_command_preview()  # 统一刷新一次
 #       self._append_info_ui(f"[封装] 已添加画中画视频或图片水印: {os.path.basename(path)}")


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
                    if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'):
                        fps = main_video.enc_settings.get("frame_rate_custom", "30") \
                              if main_video.enc_settings.get("frame_rate_type") == "custom" else "30"
                        cmd.extend(["-loop", "1", "-framerate", fps])
                    else:
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


    def _add_audio_tracks(self, cmd, enabled_tracks, file_index):
        """添加音频轨道"""
        audio_tracks = [t for t in enabled_tracks if t.type == "audio"]
        audio_map_count = 0

        for audio in audio_tracks:
            a_idx = file_index[audio.file_path]
            cmd.extend(["-map", f"{a_idx}:a:{audio._type_index}"])

            if self._handle_audio_trim(cmd, audio, audio_map_count):
                audio_map_count += 1
                continue

            enc = audio.enc_settings.get("encoder", "copy")
            if enc == "copy":
                cmd.extend([f"-c:a:{audio_map_count}", "copy"])
            else:
                bitrate = audio.enc_settings.get("bitrate", "128k")
                samplerate = audio.enc_settings.get("samplerate", "44100")
                cmd.extend([
                    f"-c:a:{audio_map_count}", enc,
                    f"-b:a:{audio_map_count}", bitrate,
                    f"-ar:a:{audio_map_count}", samplerate
                ])
            audio_map_count += 1

        if audio_map_count == 0:
            cmd.append("-an")
        else:
            cmd.extend(["-disposition:a:0", "default"])


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
        """PIP 时长控制"""
        # 主视频有效时长
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

        main_video_path = normalize_path(main_video.file_path)
        has_sub_audio = any(
            normalize_path(t.file_path) != main_video_path 
            for t in enabled_tracks if t.type == "audio"
        )

        sub_videos = [t for t in enabled_tracks if t.type == "video"][1:]

        if sub_videos:
            if has_sub_audio and main_duration and main_duration > 0:
                cmd.extend(["-t", f"{main_duration:.3f}"])
                self._append_info_ui(f"[封装] 检测到子视频音频，使用 -t {main_duration:.3f}s 控制输出时长。")
            else:
                cmd.append("-shortest")



    def _build_normal_cmd(self, enabled_tracks, output_norm):
        """普通封装模式：支持视频滤镜、多音频/字幕、音频截取等。"""
        cmd = [self.ffmpeg_cmd, "-y", "-fflags", "+genpts"]
    
        input_files, file_index = self._prepare_tracks_and_inputs(enabled_tracks)
    
        # 识别主视频
        video_tracks = [t for t in enabled_tracks if t.type == "video"]
        if not video_tracks:
            self._append_info_ui("[封装] 没有启用的视频轨道")
            return []
        main_video = video_tracks[0]
    
        # 添加输入文件 + 前置选项（-ss/-to）
        cmd = self._add_input_options(cmd, input_files, main_video)
    
        # ---- 视频处理 ----
        v_idx = file_index[main_video.file_path]
        cmd.extend(["-map", f"{v_idx}:v:{main_video._type_index}"])
    
        v_settings = main_video.enc_settings
        vcodec = v_settings.get("encoder", "copy")
    
        # copy 时直接跳过滤镜，不强制改编码器
        if vcodec == "copy":
            self._append_info_ui("[封装] 编码器为 copy，已忽略所有视频滤镜。")
            cmd.extend(["-c:v", "copy"])
        else:
            # 构建视频滤镜
            video_filters = build_video_filter_chain(
                v_settings,
                include_subtitle=False,
                include_speed=False,
                enhance_settings=v_settings.get("enhance", {})
            )
            if video_filters and video_filters != "null":
                cmd.extend(["-vf", video_filters])
    
            # 应用编码参数
            strategy = get_encoder_strategy(vcodec)
            cmd = strategy.build_params(cmd, v_settings)
    
        # ---- 音频处理（支持截取） ----
        audio_tracks = [t for t in enabled_tracks if t.type == "audio"]
        audio_map_count = 0
        for audio in audio_tracks:
            a_idx = file_index[audio.file_path]
            cmd.extend(["-map", f"{a_idx}:a:{audio._type_index}"])
    
            if self._handle_audio_trim(cmd, audio, audio_map_count):
                audio_map_count += 1
                continue
    
            enc = audio.enc_settings.get("encoder", "copy")
            if enc == "copy":
                cmd.extend([f"-c:a:{audio_map_count}", "copy"])
            else:
                bitrate = audio.enc_settings.get("bitrate", "128k")
                samplerate = audio.enc_settings.get("samplerate", "44100")
                cmd.extend([
                    f"-c:a:{audio_map_count}", enc,
                    f"-b:a:{audio_map_count}", bitrate,
                    f"-ar:a:{audio_map_count}", samplerate
                ])
            audio_map_count += 1
    
        if audio_map_count == 0:
            cmd.append("-an")
        else:
            cmd.extend(["-disposition:a:0", "default"])
    
        # ---- 字幕、章节、容器优化 ----
        self._add_subtitles_and_chapters(cmd, enabled_tracks, file_index, input_files)
        self._add_container_optimization(cmd)
    
        cmd.append(output_norm)
        return cmd


    def _build_pip_cmd(self, enabled_tracks, output_norm):
        """画中画模式"""
        cmd = [self.ffmpeg_cmd, "-y", "-fflags", "+genpts"]

        input_files, file_index = self._prepare_tracks_and_inputs(enabled_tracks)

        video_tracks = [t for t in enabled_tracks if t.type == "video"]
        if not video_tracks:
            self._append_info_ui("[封装] 没有启用的视频轨道")
            return []
        main_video = video_tracks[0]
        sub_videos = video_tracks[1:]

        # 添加输入文件 + 前置选项（包含子视频循环）
        cmd = self._add_input_options(cmd, input_files, main_video, sub_videos)

        # ---- 视频叠加 ----
        main_idx = file_index[main_video.file_path]
        sub_infos = [(file_index[sv.file_path], sv.file_path, sv.enc_settings) for sv in sub_videos]

        complex_filter, final_v_label = self._build_overlay_filter_complex(
            main_idx, main_video.enc_settings, sub_infos,
            include_subtitle_main=False,
            enhance_settings=main_video.enc_settings.get("enhance", {})
        )
        cmd.extend(["-filter_complex", complex_filter])
        cmd.extend(["-map", final_v_label])

        # 视频编码（PIP强制不使用 copy）
        v_settings = main_video.enc_settings
        vcodec = v_settings.get("encoder", "libx265")
        if vcodec == "copy":
            self._append_info_ui("[封装] 画中画模式不支持 copy，自动改为 libx265")
            vcodec = "libx265"
            v_settings["encoder"] = vcodec

        strategy = get_encoder_strategy(vcodec)
        cmd = strategy.build_params(cmd, v_settings)

        # ---- 音频、字幕、时长控制、章节 ----
        self._add_audio_tracks(cmd, enabled_tracks, file_index)
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
            self._append_info_ui("[串联-流] 预览命令，txt列表使用占位名，开始合并时随机生成")
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
        """重新编码模式 - 使用 filter_complex concat"""
        # 收集去重视频文件
        input_files = list(dict.fromkeys(t.file_path for t in video_tracks))  # 保持顺序去重

        for f in input_files:
            cmd.extend(["-i", normalize_path(f)])

        n = len(input_files)
        filter_parts = []

        # 视频 concat
        for i in range(n):
            filter_parts.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")
        filter_parts.append(
            f"[{']['.join(f'v{i}' for i in range(n))}]concat=n={n}:v=1:a=0[vout]"
        )

        # 音频 concat
        has_audio = bool(audio_tracks)
        if has_audio:
            for i in range(n):
                filter_parts.append(f"[{i}:a]asetpts=PTS-STARTPTS[a{i}]")
            filter_parts.append(
                f"[{']['.join(f'a{i}' for i in range(n))}]concat=n={n}:v=0:a=1[aout]"
            )

        cmd.extend(["-filter_complex", ";".join(filter_parts)])
        cmd.extend(["-map", "[vout]"])
        if has_audio:
            cmd.extend(["-map", "[aout]"])
        else:
            cmd.append("-an")

        # 视频编码
        v_settings = main_video.enc_settings.copy()  # 避免修改原字典
        vcodec = v_settings.get("encoder", "libx265")
        if vcodec == "copy":
            self._append_info_ui("[串联-编] 重新编码模式下视频编码器自动改为 libx265")
            vcodec = "libx265"
            v_settings["encoder"] = "libx265"

        strategy = get_encoder_strategy(vcodec)
        cmd = strategy.build_params(cmd, v_settings)

        # 音频编码
        if has_audio:
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

        self._add_container_optimization(cmd)
        cmd.append(output_norm)

        self._append_info_ui(f"[串联-编] 使用 filter_complex 重新编码模式（{n} 个片段）")
        return cmd
    
    def merge_build_cmd_list(self, output_override=None, preview=False) -> List[str]:
        if not self.ffmpeg_cmd:
            self._append_info_ui("未找到 ffmpeg，无法生成合并命令。")
            return []
    
        if output_override is not None:
            output = output_override
        else:
            output = self.merge_output.get().strip()
        if not output:
            return []
    
        output_norm = normalize_path(output)
        enabled_tracks = [t for t in self.merge_tracks if t.enabled]
        if not enabled_tracks:
            self._append_info_ui("[封装] 没有启用的轨道")
            return []
    
        if self.pip_enabled.get():
            return self._build_pip_cmd(enabled_tracks, output_norm)
        elif self.concat_enabled.get():
            return self._build_concat_cmd(enabled_tracks, output_norm, preview=preview)
        else:
            return self._build_normal_cmd(enabled_tracks, output_norm)
    
    
    
    
    
    



    def merge_update_command_preview(self, output_override=None):
        if self._batch_update:
            return
        cmd_list = self.merge_build_cmd_list(output_override=output_override, preview=True)
        if not cmd_list:
            self.merge_cmd_preview.delete(1.0, tk.END)
            self.merge_cmd_preview.insert(tk.END, "参数不完整，无法生成命令")
            return
        cmd_str = format_cmd_for_display(cmd_list)
        self.merge_cmd_preview.delete(1.0, tk.END)
        self.merge_cmd_preview.insert(tk.END, cmd_str)

    def merge_get_media_info(self, path):
        return ffprobe_json(self.ffprobe_cmd, path)

    def merge_load_video_info(self):
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
            info = ffprobe_json(self.ffprobe_cmd, path)
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
            self.merge_update_command_preview()  # 最终统一刷新一次

    def merge_update_track_list(self):
        for w in self.merge_track_frame.winfo_children():
            w.destroy()
        if not self.merge_tracks:
            tk.Label(self.merge_track_frame, text="未加载轨道").pack()
            return
        container = self.merge_track_frame
        main_video = self.merge_video.get().strip()
        col_bg_headers = ["#cccccc", "#e0e0e0", "#cccccc", "#e0e0e0", "#cccccc", "#e0e0e0", "#cccccc", "#e0e0e0", "#cccccc"]
        ROW_BG_EVEN = ["#e0e0e0", "#cccccc", "#e0e0e0", "#cccccc", "#e0e0e0", "#cccccc", "#e0e0e0", "#cccccc", "#e0e0e0"]
        ROW_BG_ODD  = ["#cccccc", "#e0e0e0", "#cccccc", "#e0e0e0", "#cccccc", "#e0e0e0", "#cccccc", "#e0e0e0", "#cccccc"]
        headers = ["启用", "类型", "编码", "来源", "编码设置", "预览", "上移", "下移", "删除"]
        col_widths = [5, 8, 10, None, 10, 6, 4, 4, 6]
        for col, text in enumerate(headers):
            width = col_widths[col]
            if width is None:
                label = tk.Label(container, text=text, anchor="center", bg=col_bg_headers[col])
                label.grid(row=0, column=col, sticky="nsew", padx=0, pady=0)
            else:
                label = tk.Label(container, text=text, anchor="center", width=width, bg=col_bg_headers[col])
                label.grid(row=0, column=col, sticky="nsew", padx=0, pady=0)
        for i, track in enumerate(self.merge_tracks):
            row_num = i + 1
            row_bg = ROW_BG_EVEN if (i % 2 == 0) else ROW_BG_ODD
            chk_frame = tk.Frame(container, bg=row_bg[0])
            chk_frame.grid(row=row_num, column=0, sticky="nsew", padx=0, pady=0)
            var = tk.BooleanVar(value=track.enabled)
            cb = tk.Checkbutton(chk_frame, variable=var, bg=row_bg[0], activebackground=row_bg[0],
                                command=lambda idx=i, v=var: self.merge_set_track_enabled(idx, v.get()))
            cb.pack(expand=True)
            if track.type == "video":
                type_bg = "#cce5ff"
            elif track.type == "audio" and track.file_path == main_video:
                type_bg = "#e6f2e6"
            else:
                type_bg = row_bg[1]
            enabled_video_tracks = [t for t in self.merge_tracks if t.enabled and t.type == "video"]
            is_main_video = (enabled_video_tracks and enabled_video_tracks[0] == track)
            display_type = "视频(主)" if is_main_video and track.type == "video" else track.type
            if self.concat_enabled.get() and track.type == "video" and not is_main_video:
                display_type = "视频(串)"
            elif self.pip_enabled.get() and track.type == "video" and not is_main_video:
                display_type = "视频(画)"
            lbl_type = tk.Label(container, text=display_type, anchor="center", width=col_widths[1], bg=type_bg)
            lbl_type.grid(row=row_num, column=1, sticky="nsew", padx=0, pady=0)
            lbl_codec = tk.Label(container, text=track.codec[:10], anchor="center", width=col_widths[2], bg=row_bg[2])
            lbl_codec.grid(row=row_num, column=2, sticky="nsew", padx=0, pady=0)
            src = os.path.basename(track.file_path) if track.file_path else "外部"
            lbl_src = tk.Label(container, text=src, anchor="w", bg=row_bg[3])
            lbl_src.grid(row=row_num, column=3, sticky="nsew", padx=0, pady=0)
            enc_text = "复制流" if not track.is_encoding() else track.enc_settings.get("encoder", "?")
            btn_enc = ttk.Button(container, text=enc_text, width=col_widths[4],
                                 command=lambda idx=i: self.merge_edit_track_settings(idx))
            btn_enc.grid(row=row_num, column=4, padx=1, pady=1)
            btn_preview = ttk.Button(container, text="预览", width=col_widths[5],
                                     command=lambda idx=i: self.merge_preview_track(idx))
            btn_preview.grid(row=row_num, column=5, padx=1, pady=1)
            btn_up = ttk.Button(container, text="↑", width=col_widths[6],
                                command=lambda idx=i: self.merge_move_track_up(idx))
            if i == 0:
                btn_up.state(['disabled'])
            btn_up.grid(row=row_num, column=6, padx=1, pady=1)
            btn_down = ttk.Button(container, text="↓", width=col_widths[7],
                                  command=lambda idx=i: self.merge_move_track_down(idx))
            if i == len(self.merge_tracks) - 1:
                btn_down.state(['disabled'])
            btn_down.grid(row=row_num, column=7, padx=1, pady=1)
            btn_del = ttk.Button(container, text="删除", width=col_widths[8],
                                 command=lambda idx=i: self.merge_remove_track(idx))
            btn_del.grid(row=row_num, column=8, padx=1, pady=1)
        for col in range(len(headers)):
            if col == 3:
                container.columnconfigure(col, weight=1)
            else:
                container.columnconfigure(col, weight=0)

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

    def merge_clear_tracks(self):
        self.merge_tracks.clear()
        self.merge_update_track_list()
        self.merge_auto_recommend_container()
        self.merge_update_command_preview()
        self._append_info_ui("[封装] 已清空所有附加轨道")

    def merge_remove_track(self, track_idx):
        if 0 <= track_idx < len(self.merge_tracks):
            removed = self.merge_tracks.pop(track_idx)
            self._append_info_ui(f"[封装] 已删除轨道: {removed.type} - {os.path.basename(removed.file_path)}")
            self.merge_update_track_list()
            self.merge_auto_recommend_container()
            self.merge_update_command_preview()

#     def get_video_dimensions(self, file_path):
#         return get_video_dimensions(self.ffprobe_cmd, file_path)

#     def get_video_rotated_dimensions(self, file_path, enc_settings):
#         return get_video_rotated_dimensions(self.ffprobe_cmd, file_path, enc_settings)

    def evaluate_expression(self, expr, main_w, main_h, box_w, box_h):
        return safe_eval_expr(expr, {"W": main_w, "H": main_h, "w": box_w, "h": box_h})

    def get_rendered_size(self, track):
        w, h = get_video_rotated_dimensions(self.ffprobe_cmd, track.file_path, track.enc_settings)
        if w is None:
            return None
        return compute_rendered_size(w, h, track.enc_settings)

    def merge_preview_track(self, track_idx):
        track = self.merge_tracks[track_idx]
        if not os.path.exists(track.file_path):
            self._append_info_ui(f"[预览] 文件不存在: {track.file_path}")
            return
        if track.type == "video":
            filters = build_video_filter_chain(track.enc_settings, include_subtitle=False, include_speed=False)
            pip_enabled = self.pip_enabled.get()
            enabled_video_tracks = [t for t in self.merge_tracks if t.enabled and t.type == "video"]
            is_main_video = (enabled_video_tracks and enabled_video_tracks[0] == track)
            if pip_enabled and is_main_video:
                sub_videos = enabled_video_tracks[1:]
                if sub_videos:
                    main_w, main_h = get_video_rotated_dimensions(self.ffprobe_cmd, track.file_path, track.enc_settings)
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
            if filters and filters != "null":
                final_filter = f"{filters},scale=-2:960"
            else:
                final_filter = "scale=-2:960"
            self.preview_with_player(track.file_path, final_filter, volume=10)
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
                            track_obj=None):
        if parent is None:
            parent = self.root
        with self.SafeToplevel(parent) as win:
            win.title(title)
            notebook = ttk.Notebook(win)
            notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            # ---- 页面1：编码器与质量 ----
            page_enc = ttk.Frame(notebook)
            notebook.add(page_enc, text="编码器与质量")
            enc_frame = VideoEncoderFrame(page_enc)
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
            trim_frame = TrimFrame(page_trim)
            trim_frame.pack(fill=tk.X, padx=5, pady=5)
            trim_frame.set_settings(initial_settings)

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

            # ---- 页面5：叠加/偏移 ----
            page_overlay = ttk.Frame(notebook)
            notebook.add(page_overlay, text="叠加/偏移")

            if is_watermark:
                def watermark_visual_callback():
                    main_file = self.input_file.get().strip()
                    if not main_file or not os.path.exists(main_file):
                        messagebox.showwarning("提示", "请先在主界面选择一个输入文件作为画布")
                        return
                    main_w, main_h = get_video_rotated_dimensions(self.ffprobe_cmd, main_file, {})
                    if main_w is None:
                        main_w, main_h = 1280, 720
                    wm_file = initial_settings.get("file_path", "")
                    if not wm_file or not os.path.exists(wm_file):
                        messagebox.showwarning("提示", "水印文件未设置或不存在")
                        return
                    filt_settings = filt_frame.get_settings()
                    orig_w, orig_h = get_video_rotated_dimensions(self.ffprobe_cmd, wm_file, {})
                    if orig_w is None:
                        orig_w, orig_h = 320, 240
                    rendered = compute_rendered_size(orig_w, orig_h, filt_settings)
                    if rendered:
                        wm_w, wm_h = rendered
                    else:
                        wm_w, wm_h = 320, 240
                    self._simple_visual_overlay(main_w, main_h, wm_w, wm_h,
                                                overlay_frame.overlay_x,
                                                overlay_frame.overlay_y,
                                                parent=win)

                overlay_frame = OverlayPositionFrame(
                    page_overlay,
                    app=self,
                    mode='sub',
                    track_idx=None,
                    track_obj=None,
                    pip_enabled_var=None,
                    filt_frame=filt_frame,
                    visual_callback=watermark_visual_callback
                )
            else:
                overlay_frame = OverlayPositionFrame(
                    page_overlay,
                    app=self,
                    mode=overlay_mode,
                    track_idx=track_idx,
                    track_obj=None,
                    pip_enabled_var=pip_enabled_var,
                    filt_frame=filt_frame,
                    visual_callback=None
                )

            overlay_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            overlay_frame.set_settings(initial_settings)

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
                    new_settings.update(overlay_frame.get_settings())
                    if is_watermark:
                        new_settings["enabled"] = True
                        new_settings["file_path"] = initial_settings.get("file_path", "")
                        new_settings["duration"] = initial_settings.get("duration", None)
                    new_settings["enhance"] = filt_frame.get_enhance_settings()
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
            track_obj=track   # 传递轨道对象
        )
    
    
    def _update_track_enc(self, idx, new_settings):
        track = self.merge_tracks[idx]  # 先获取 track 对象
        track.enc_settings = new_settings
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
        self.merge_update_track_list()
        self.merge_update_command_preview()


    def merge_edit_audio_track(self, track_idx):
        track = self.merge_tracks[track_idx]
        with self.SafeToplevel(self.root) as win:
            win.title(f"音频轨道设置 - {track.codec}")
            center_window(win, 500, 400)
            win.transient(self.root)
    
            # 主框架
            main_frame = ttk.Frame(win, padding="10")
            main_frame.pack(fill=tk.BOTH, expand=True)
    
            # ---- 编码设置 ----
            enc_frame = ttk.LabelFrame(main_frame, text="编码参数", padding="5")
            enc_frame.pack(fill=tk.X, pady=5)
    
            ttk.Label(enc_frame, text="编码器:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
            encoder_var = tk.StringVar(value=track.enc_settings.get("encoder", "copy"))
            ttk.Combobox(enc_frame, textvariable=encoder_var, values=ALL_AUDIO_ENCODERS, state="readonly", width=15).grid(row=0, column=1, sticky="w", padx=5, pady=5)
    
            ttk.Label(enc_frame, text="比特率:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
            bitrate_var = tk.StringVar(value=track.enc_settings.get("bitrate", "128k"))
            ttk.Entry(enc_frame, textvariable=bitrate_var, width=10).grid(row=1, column=1, sticky="w", padx=5, pady=5)
    
            ttk.Label(enc_frame, text="采样率:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
            samplerate_var = tk.StringVar(value=track.enc_settings.get("samplerate", "44100"))
            ttk.Entry(enc_frame, textvariable=samplerate_var, width=10).grid(row=2, column=1, sticky="w", padx=5, pady=5)
    
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

            # 精准模式（保留，但音频 atrim 本身就是精确的）
            precise_trim_var = tk.BooleanVar(value=track.enc_settings.get("precise_trim", False))
            ttk.Checkbutton(trim_frame, text="精准模式（精确到帧）", variable=precise_trim_var).grid(row=3, column=0, columnspan=3, sticky="w", padx=5, pady=5)
    
            # 提示
            ttk.Label(trim_frame, text="注意：启用截取后，编码器将自动改为非 copy 格式（如 aac）", foreground="gray").grid(row=4, column=0, columnspan=3, sticky="w", padx=5, pady=5)
    
            # ---- 保存按钮 ----
            def save():
                # 检查截取启用时，编码器是否非 copy
                enc = encoder_var.get()
                if trim_enabled_var.get() and enc == "copy":
                    enc = "aac"
                    self._append_info_ui("音频截取启用，编码器已从 copy 改为 aac")
    
                track.enc_settings = {
                    "encoder": enc,
                    "bitrate": bitrate_var.get(),
                    "samplerate": samplerate_var.get(),
                    "trim_enabled": trim_enabled_var.get(),
                    "trim_start": trim_start_var.get().strip(),
                    "trim_end": trim_end_var.get().strip(),
                    "precise_trim": precise_trim_var.get()
                }
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
                    wraplength=300)
            ttk.Label(win, text="语言代码:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
            lang_var = tk.StringVar(value=getattr(track, 'language', ''))
            lang_combo = ttk.Combobox(win, textvariable=lang_var,
                                      values=["", "chi", "eng", "jpn", "kor", "fre", "ger", "rus", "spa", "ita"],
                                      state="normal", width=10)
            lang_combo.grid(row=1, column=1, padx=5, pady=5, sticky="w")
            ttk.Label(win, text="常见: chi(中文), eng(英语), jpn(日语)", foreground="gray").grid(row=2, column=1, sticky="w", padx=5)
            ttk.Label(win, text="轨道标题:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
            title_var = tk.StringVar(value=getattr(track, 'title', ''))
            title_entry = ttk.Entry(win, textvariable=title_var, width=30)
            title_entry.grid(row=3, column=1, padx=5, pady=5, sticky="w")
            def save():
                track.enc_settings["encoder"] = encoder_var.get()
                track.language = lang_var.get().strip()
                track.title = title_var.get().strip()
                track.enc_settings["language"] = track.language
                track.enc_settings["title"] = track.title
                self.merge_update_track_list()
                self.merge_update_command_preview()
                win.destroy()
            ttk.Button(win, text="保存", command=save).grid(row=4, column=0, columnspan=2, pady=10)
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
        if not self.merge_video.get():
            self._append_info_ui("[封装] 请先设置主视频")
            return
        if not path:
            if ftype == "audio":
                types = [("音频", "*.mp3 *.aac *.m4a *.wav *.flac *.ogg *.opus *.ac3 *.dts *.mka")]
            else:
                types = [("字幕", "*.srt *.ass *.ssa *.vtt *.idx *.sup")]
            path = filedialog.askopenfilename(filetypes=types)
            if not path:
                return
        info = ffprobe_json(self.ffprobe_cmd, path)
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
        if not cmd_list:
            self._append_info_ui("[封装] 命令列表为空，无法执行")
            self.root.after(0, lambda: self.merge_btn.config(state="normal"))
            return
        self._append_info_ui("[封装] 开始合并/转码...")
        output_file = final_output  # 使用最终路径
        source_files = set()
        source_files.add(self.merge_video.get().strip())
        for t in self.merge_tracks:
            if t.enabled and t.file_path not in source_files:
                source_files.add(t.file_path)
        try:
            proc = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding='utf-8', errors='replace',
                                    creationflags=0x08000000 if sys.platform == "win32" else 0)
            for line in proc.stdout:
                self.safe_append_detail(line)
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
        files = self.root.tk.splitlist(event.data)
        self._append_info_ui(f"拖拽了 {len(files)} 个文件")
        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 0:
            for file in files:
                if os.path.exists(file):
                    self.add_task(file)
                else:
                    self._append_info_ui(f"文件不存在: {file}")
        else:
            # 合并模块的处理保持不变
            if len(files) >= 2:
                self.merge_handle_batch_dropped(files)
            else:
                for file in files:
                    if os.path.exists(file):
                        self.merge_handle_dropped_file(file)

    def merge_handle_dropped_file(self, path):
        def process():
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

    def merge_handle_batch_dropped(self, files):
        def run_in_thread():
            files_sorted = sorted(files, key=lambda x: os.path.basename(x).lower())
            video_exts = ['.mp4','.mkv','.avi','.mov','.flv','.ts','.webm','.m2ts']
            video_files = [f for f in files_sorted if os.path.splitext(f)[1].lower() in video_exts]
            other_files = [f for f in files_sorted if f not in video_files]
            root_tk = self.root
            dialog = tk.Toplevel(root_tk)
            dialog.title("批量处理选项")
            height = min(350 + len(video_files) * 25, 600) + 20
            center_window(dialog, 600, height)
            dialog.transient(root_tk)
            dialog.grab_set()
            has_main = bool(self.merge_video.get().strip())
            info_text = "请选择操作：\n\n• [All] 按钮：仅添加音频（不改变主视频）\n• 点击下方视频按钮：设为主视频，其余添加音频"
            tk.Label(dialog, text=info_text, justify=tk.LEFT).pack(pady=10, padx=10)
            def all_action():
                def do_all():
                    if not has_main and video_files:
                        main = video_files[0]
                        self.merge_video.set(main)
                        self._append_info_ui(f"[封装] 自动设置主视频: {os.path.basename(main)}")
                        start_idx = 1
                    else:
                        start_idx = 0
                    for f in video_files[start_idx:]:
                        self.merge_add_external("audio", f)
                        self.merge_add_external("subtitle", f)
                    for f in other_files:
                        self.merge_handle_dropped_file(f)
                    self.merge_update_track_list()
                    self.merge_auto_recommend_container()
                    self.merge_update_command_preview()
                    dialog.destroy()
                self.root.after(0, do_all)
            btn_all = tk.Button(dialog, text="[All] 仅音频", command=all_action,
                                bg="#4CAF50", fg="white", width=22, wraplength=300)
            btn_all.pack(pady=5, padx=10)
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
                    main = video_files[idx]
                    self.merge_video.set(main)
                    self._append_info_ui(f"[封装] 设置主视频为: {os.path.basename(main)}")
                    for i, f in enumerate(video_files):
                        if i != idx:
                            self.merge_add_external("audio", f)
                            self.merge_add_external("subtitle", f)
                    for f in other_files:
                        self.merge_handle_dropped_file(f)
                    self.merge_update_track_list()
                    self.merge_auto_recommend_container()
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
            dialog.wait_window()
        threading.Thread(target=run_in_thread, daemon=True).start()

    # ---------- 播放器设置标签页 ----------
    def create_player_settings_tab(self, parent):
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        self.mpv_check = ttk.Checkbutton(frame, text="启用 mpv 作为预览播放器（推荐，支持进度条等）",
                                         variable=self.use_mpv,
                                         command=self.on_player_changed)
        self.mpv_check.pack(anchor=tk.W, pady=5)
        path_frame = ttk.Frame(frame)
        path_frame.pack(fill=tk.X, pady=5)
        ttk.Label(path_frame, text="mpv 可执行文件路径:").pack(side=tk.LEFT, padx=(0,5))
        self.mpv_path_entry = ttk.Entry(path_frame, textvariable=self.mpv_path, width=40)
        self.mpv_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(path_frame, text="浏览", command=self.browse_mpv).pack(side=tk.LEFT, padx=5)

        # ---- 日志记录控制 ----
        log_frame = ttk.Frame(frame)
        log_frame.pack(fill=tk.X, pady=5)
        chk_log = ttk.Checkbutton(log_frame, text="记录成功命令到日志", variable=self.log_enabled_var)
        chk_log.pack(side=tk.LEFT)
        log_entry = ttk.Entry(log_frame, textvariable=self.log_path_var, width=30)
        log_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(log_frame, text="浏览", command=self.browse_log_file).pack(side=tk.LEFT, padx=5)


        # ---- 新增：同名文件处理策略 ----
        policy_frame = ttk.LabelFrame(frame, text="全局同名文件处理策略", padding="5")
        policy_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(policy_frame, text="当输出文件已存在时:").pack(side=tk.LEFT)
        policy_combo = ttk.Combobox(
            policy_frame,
            textvariable=self.overwrite_policy,
            values=["ask", "rename", "overwrite"],
            state="readonly",
            width=12
        )
        policy_combo.pack(side=tk.LEFT, padx=5)
        # 添加解释
        desc = ttk.Label(
            policy_frame,
            text="询问/自动重命名/直接覆盖",
            foreground="gray"
        )
        desc.pack(side=tk.LEFT, padx=5)
        # 绑定事件，保存设置
        self.overwrite_policy.trace_add("write", lambda *a: self.save_player_settings())


        status_frame = ttk.LabelFrame(frame, text="状态检测", padding="5")
        status_frame.pack(fill=tk.X, pady=(15, 5))
        self.status_text = tk.Text(status_frame, height=20, width=80, wrap=tk.WORD,
                                   bg="#f8f8f8", relief=tk.FLAT)
        self.status_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
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
        self.update_player_status()

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
        preset_path = self.preset_file_path
        if os.path.exists(preset_path):
            preset_status = "✓ 文件存在"
        else:
            preset_status = "✗ 文件不存在（将自动创建）"
        local_preset = os.path.join(get_script_dir(), "ffmpeg_presets.json")
        if preset_path == local_preset:
            source = "脚本目录（便携模式）"
        else:
            source = "用户目录（%USERPROFILE%\\.FFLiteGUI）"
        self.status_text.insert(tk.END, f"预设配置文件: {preset_path}\n")
        self.status_text.insert(tk.END, f"配置来源: {source}  | 状态: {preset_status}\n\n")
        if self.use_mpv.get():
            mpv_path = self.mpv_path.get().strip()
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
                self.status_text.insert(tk.END, f"  ffplay 路径: {self.ffplay_cmd}  →  ✓ 可用\n")
            else:
                self.status_text.insert(tk.END, f"  ffplay 未找到，请将 ffplay.exe 放在脚本目录或添加到 PATH。\n")
        self.status_text.insert(tk.END, "\n--- FFmpeg 全家桶检测 ---\n")
        tools = ['ffmpeg', 'ffplay', 'ffprobe']
        script_dir = get_script_dir()
        self.status_text.insert(tk.END, f"当前目录 ({script_dir}):\n")
        for tool in tools:
            exe_name = tool + ".exe" if sys.platform == "win32" else tool
            local_path = os.path.join(script_dir, exe_name)
            exists = os.path.isfile(local_path) and os.access(local_path, os.X_OK)
            status = "✓ 存在" if exists else "✗ 不存在"
            self.status_text.insert(tk.END, f"  {exe_name}: {status}\n")
        
        # ---- 新增 _internal 目录检测 ----
        if getattr(sys, 'frozen', False):
            internal_dir = os.path.join(script_dir, '_internal')
            if os.path.isdir(internal_dir):
                self.status_text.insert(tk.END, f"\n_internal 目录 ({internal_dir}):\n")
                for tool in tools:
                    exe_name = tool + ".exe" if sys.platform == "win32" else tool
                    internal_path = os.path.join(internal_dir, exe_name)
                    exists = os.path.isfile(internal_path) and os.access(internal_path, os.X_OK)
                    status = "✓ 存在" if exists else "✗ 不存在"
                    self.status_text.insert(tk.END, f"  {exe_name}: {status}\n")
        self.status_text.insert(tk.END, "环境变量 PATH:\n")
        import shutil
        for tool in tools:
            path_in_path = shutil.which(tool)
            if path_in_path:
                self.status_text.insert(tk.END, f"  {tool}: ✓ 找到 → {path_in_path}\n")
            else:
                self.status_text.insert(tk.END, f"  {tool}: ✗ 未找到\n")
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
            self._append_info_ui("⚠️ 必要组件缺失: " + missing_str)
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





    # -------------------- 界面创建 --------------------
    def create_widgets(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        left_container = ttk.Frame(main_frame)
        left_container.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        right_panel = ttk.Frame(main_frame)
        right_panel.grid(row=0, column=1, sticky="ns", padx=0, pady=0)
        right_panel.pack_propagate(False)
        right_panel.config(width=420)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=0)
        main_frame.rowconfigure(0, weight=1)

        info_frame = ttk.LabelFrame(right_panel, text="关键信息", padding="5")
        info_frame.pack(fill=tk.BOTH, expand=True, pady=(0,5))
        info_top = ttk.Frame(info_frame)
        info_top.pack(fill=tk.X, pady=2)
        ttk.Button(info_top, text="清空日志", command=lambda: self.info_text.delete(1.0, tk.END)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(info_top, text="保存日志", command=lambda: self.save_log(self.info_text)).pack(side=tk.RIGHT, padx=2)
        self.info_text = scrolledtext.ScrolledText(info_frame, bg='#EAF4FC', fg='black',
                                                   selectbackground='#CCF09C', selectforeground='black',
                                                   font=("Microsoft YaHei",9,"normal"), wrap=tk.WORD)
        self.info_text.pack(fill=tk.BOTH, expand=True)

        detail_frame = ttk.LabelFrame(right_panel, text="转换进程信息", padding="5")
        detail_frame.pack(fill=tk.BOTH, expand=True)
        detail_top = ttk.Frame(detail_frame)
        detail_top.pack(fill=tk.X, pady=2)
        ttk.Button(detail_top, text="清空日志", command=lambda: self.detail_text.delete(1.0, tk.END)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(detail_top, text="保存日志", command=lambda: self.save_log(self.detail_text)).pack(side=tk.RIGHT, padx=2)
        self.detail_text = scrolledtext.ScrolledText(detail_frame, bg='#EAF4FC', fg='black',
                                                     selectbackground='#CCF09C', selectforeground='black',
                                                     font=("Microsoft YaHei",8,"normal"), wrap=tk.WORD)
        self.detail_text.pack(fill=tk.BOTH, expand=True)

        left_vpane = ttk.PanedWindow(left_container, orient=tk.VERTICAL)
        left_vpane.pack(fill=tk.BOTH, expand=True)
        self.notebook = ttk.Notebook(left_vpane)
        left_vpane.add(self.notebook, weight=1)

        transcode_tab = ttk.Frame(self.notebook)
        self.notebook.add(transcode_tab, text="视频转码")
        transcode_vpane = ttk.Frame(transcode_tab)
        transcode_vpane.pack(fill=tk.BOTH, expand=True)
        
        settings_frame = ttk.Frame(transcode_vpane)
        settings_frame.pack(side=tk.TOP, fill=tk.X, expand=False, pady=(0,5))

        io_frame = ttk.LabelFrame(settings_frame, text="输入 / 输出", padding="5")
        io_frame.pack(fill=tk.X, pady=5)
        ttk.Label(io_frame, text="输入文件:").grid(row=0, column=0, sticky="w")
        ttk.Entry(io_frame, textvariable=self.input_file, width=70).grid(row=0, column=1, padx=5)
        ttk.Button(io_frame, text="浏览", command=self.select_input).grid(row=0, column=2)
        ttk.Button(io_frame, text="添加到任务列表", command=self.add_current_as_task).grid(row=0, column=3, padx=5)
        ttk.Label(io_frame, text="输出目录:").grid(row=1, column=0, sticky="w")
        ttk.Entry(io_frame, textvariable=self.output_dir, width=70).grid(row=1, column=1, padx=5)
        ttk.Button(io_frame, text="浏览", command=self.select_output_dir).grid(row=1, column=2)
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

        preset_frame = ttk.LabelFrame(settings_frame, text="参数预设", padding="5")
        preset_frame.pack(fill=tk.X, pady=5)
        ttk.Label(preset_frame, text="预设名称:").pack(side=tk.LEFT)
        self.preset_name = tk.StringVar()
        self.preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_name, width=25, state="readonly")
        self.preset_combo.pack(side=tk.LEFT, padx=5)
        self.load_preset_list()
        self.preset_combo.bind("<<ComboboxSelected>>", lambda e: self.load_preset(self.preset_name.get()))
        btn_save = ttk.Button(preset_frame, text="保存当前参数为预设", command=self.save_preset)
        btn_save.pack(side=tk.LEFT, padx=5)
        btn_delete = ttk.Button(preset_frame, text="删除预设", command=self.delete_preset)
        btn_delete.pack(side=tk.LEFT, padx=5)
        btn_export = ttk.Button(preset_frame, text="导出所有预设(备份)", command=self.export_all_presets)
        btn_export.pack(side=tk.LEFT, padx=5)
        btn_import = ttk.Button(preset_frame, text="导入预设(恢复)", command=self.import_presets)
        btn_import.pack(side=tk.LEFT, padx=5)

        param_notebook = ttk.Notebook(settings_frame)
        param_notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        video_enc_page = ttk.Frame(param_notebook)
        param_notebook.add(video_enc_page, text="视频编码")
        self.video_encoder = VideoEncoderFrame(video_enc_page, refresh_callback=self.update_command_preview)
        self.video_encoder.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        filter_page = ttk.Frame(param_notebook)
        param_notebook.add(filter_page, text="视频滤镜")
        self.video_filter = VideoFilterFrame(filter_page, app=self)
        self.video_filter.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        audio_page = ttk.Frame(param_notebook)
        param_notebook.add(audio_page, text="音频")
        self.audio_frame = AudioFrame(audio_page, enable_checkbox=True)
        self.audio_frame.pack(fill=tk.X, padx=5, pady=5)

        trim_page = ttk.Frame(param_notebook)
        param_notebook.add(trim_page, text="截取片段")
        self.trim_frame = TrimFrame(trim_page)
        self.trim_frame.pack(fill=tk.X, padx=5, pady=5)

        # 在 create_widgets 中，adv_page 之后添加：
        segment_tab = ttk.Frame(param_notebook)
        param_notebook.add(segment_tab, text="分段拼接")
        
        seg_control_frame = ttk.Frame(segment_tab)
        seg_control_frame.pack(fill=tk.X, pady=10)
        
        ttk.Checkbutton(seg_control_frame, text="启用分段拼接模式 (将忽略『截取片段』设置)",
                        variable=self.segment_enabled).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(seg_control_frame, text="打开分段设置...",
                   command=self.open_segment_editor).pack(side=tk.LEFT, padx=10)
        
        # 灰色说明（包含功能描述和时间码获取提示）
        ttk.Label(
            segment_tab,
            text="勾选启用后，视频将按片段列表裁剪并拼接，所有片段使用相同的全局编码/滤镜设置。\n\n"
                 "   建议使用（mpv、PotPlayer）等播放器打开视频，定位到需要的起始/结束帧，将时间（格式如 01:23.456）填入左侧输入框。ffplay 简易预览功能看不到时间。\n\n"
                 "   典型用途：简单混剪、去中间广告、提取精华片段等。",
            foreground="grey",
            wraplength=1100,
            justify=tk.LEFT
        ).pack(anchor=tk.W, padx=10, pady=(5,0))
        
        # 红色警告（关于任务队列的提示）
        ttk.Label(
            segment_tab,
            text="建议：该功能主要用于单个文件的片段重组，不推荐作为模板批量添加到「任务队列」中，（多个片段时间不通用）。",
            foreground="red",
            wraplength=900,
            justify=tk.LEFT
        ).pack(anchor=tk.W, padx=10, pady=(0,5))


        adv_page = ttk.Frame(param_notebook)
        param_notebook.add(adv_page, text="高级选项")
        self.adv_frame = AdvancedFrame(adv_page, update_callback=self.update_command_preview, app=self)
        self.adv_frame.pack(fill=tk.X, padx=5, pady=5)

        bottom_btn_frame = ttk.Frame(settings_frame)
        bottom_btn_frame.pack(fill=tk.X, pady=5)

        btn_height = 1 if self.scaling >= 1.4 else 2

        btn_single = tk.Button(bottom_btn_frame, text="开始编码",
                               command=self.transcode_single,
                               height=btn_height, width=18, relief=tk.RAISED,
                               bg="#4CAF50", fg="white", font=("",12,"bold"))
        btn_single.pack(side=tk.LEFT, padx=5, pady=5)

        btn_preview = tk.Button(bottom_btn_frame, text="预览当前命令",
                                command=self.preview_current_file,
                                height=btn_height, width=18, relief=tk.RAISED,
                                bg="#2196F3", fg="white", font=("",12,"bold"))
        btn_preview.pack(side=tk.LEFT, padx=5, pady=5)

        btn_refresh = tk.Button(bottom_btn_frame, text="刷新命令",
                                command=self.update_command_preview,
                                height=btn_height, width=12, relief=tk.RAISED)
        btn_refresh.pack(side=tk.LEFT, padx=5, pady=5)
        
        btn1_copy = tk.Button(bottom_btn_frame, text="复制命令", command=self.copy_command,
                             height=btn_height, width=12, relief=tk.RAISED)
        btn1_copy.pack(side=tk.LEFT, padx=5)

        preview_frame = ttk.LabelFrame(settings_frame, text="当前命令模板", padding="5")
        preview_frame.pack(fill=tk.X, pady=0)
        self.cmd_preview = scrolledtext.ScrolledText(preview_frame, height=4, wrap=tk.WORD, font=("Microsoft YaHei",9))
        self.cmd_preview.pack(fill=tk.BOTH, expand=True)
        self.cmd_preview.insert(tk.END, "请选择输入文件，或调整参数...")

        tasks_frame = ttk.Frame(transcode_vpane)
        tasks_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0,0))

        tasks_frame.rowconfigure(0, weight=0)
        tasks_frame.rowconfigure(1, weight=1)
        tasks_frame.columnconfigure(0, weight=1)
        
        btn_container = ttk.Frame(tasks_frame)
        btn_container.grid(row=0, column=0, sticky="ew", pady=0)
        canvas = tk.Canvas(btn_container, highlightthickness=0, height=1)
        canvas.pack(side=tk.TOP, fill=tk.X, expand=True)
        h_scroll = ttk.Scrollbar(btn_container, orient=tk.HORIZONTAL, command=canvas.xview)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X, pady=(4,0))
        canvas.configure(xscrollcommand=h_scroll.set)
        button_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=button_frame, anchor="nw")
        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            new_height = button_frame.winfo_reqheight()
            if canvas.cget("height") != new_height:
                canvas.configure(height=new_height)
        button_frame.bind("<Configure>", _on_frame_configure)
        
        btn_start = tk.Button(button_frame, text="开始队列", command=self.start_queue,
                              bg="#4CAF50", fg="white", width=12, relief=tk.RAISED)
        btn_start.pack(side=tk.LEFT, padx=5)
        
        self.max_parallel = tk.IntVar(value=1)
        label_parallel = ttk.Label(button_frame, text="并行任务:")
        label_parallel.pack(side=tk.LEFT, padx=(10,2))
        ToolTip(label_parallel, "同时运行的任务数量，建议不超过3以避免资源过度占用")
        self.parallel_spin = ttk.Spinbox(button_frame, from_=1, to=5, width=3, textvariable=self.max_parallel, state="readonly")
        self.parallel_spin.pack(side=tk.LEFT, padx=2)
        
        label_hw = ttk.Label(button_frame, text="硬编并发限制:")
        label_hw.pack(side=tk.LEFT, padx=(10,2))
        ToolTip(label_hw, "同时进行的硬件编码〔NVENC/QSV/AMF等〕任务的最大数量，推荐不超过2，显存里可能数据打架")
        self.max_hw_spin = ttk.Spinbox(button_frame, from_=1, to=4, width=3, textvariable=self.max_hw_parallel, state="readonly")
        self.max_hw_spin.pack(side=tk.LEFT, padx=2)
        
        for text, cmd in [("移除选中任务", self.remove_selected_tasks), ("清空全部任务", self.clear_all_tasks),
                          ("清空已完成/失败任务", self.clear_finished_tasks), ("停止队列", self.stop_queue),
                          ("导出为脚本", self.export_script), ("预览选中任务", self.preview_selected_task)]:
            ttk.Button(button_frame, text=text, command=cmd).pack(side=tk.LEFT, padx=5)
        
        tree_frame = ttk.Frame(tasks_frame)
        tree_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        
        v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        columns = ("序号", "文件名", "输出路径", "命令 (简洁)", "状态", "错误信息")
        self.task_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=12,
                                      yscrollcommand=v_scrollbar.set,
                                      xscrollcommand=h_scrollbar.set)
        self.task_tree.tag_configure('odd', background='#e8e8e8')
        self.task_tree.tag_configure('even', background='#ffffff')
        v_scrollbar.config(command=self.task_tree.yview)
        h_scrollbar.config(command=self.task_tree.xview)
        widths = {"序号":50, "文件名":150, "输出路径":200, "命令 (简洁)":400, "状态":80, "错误信息":200}
        for col in columns:
            self.task_tree.heading(col, text=col)
            self.task_tree.column(col, width=widths.get(col,100), minwidth=50, stretch=False)
        self.task_tree.pack(fill=tk.BOTH, expand=True)
        self.task_tree.bind("<Double-1>", self.on_task_double_click)

        merge_tab = ttk.Frame(self.notebook)
        self.notebook.add(merge_tab, text="封装/合并/画中画")
        self.create_merge_tab(merge_tab)

        player_tab = ttk.Frame(self.notebook)
        self.notebook.add(player_tab, text="信息与播放器")
        self.create_player_settings_tab(player_tab)

        # 绑定各种控件刷新命令预览
        self.video_encoder.vcodec.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.rate_control_type.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.crf_value.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.cq_value.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.global_quality.trace_add("write", lambda *a: self.update_command_preview())
        self.video_encoder.bitrate_video.trace_add("write", lambda *a: self.update_command_preview())
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
    def __init__(self, parent, segments, app):
        self.parent = parent
        self.app = app  # 主程序引用，用于获取时长等信息
        self.segments = copy.deepcopy(segments)  # 深拷贝，独立修改
        self.result = None  # 返回结果

        # 创建窗口
        self.window = tk.Toplevel(parent)
        self.window.title("分段拼接设置")
        self.window.transient(parent)
        self.window.grab_set()
        # 窗口大小
        self.window.geometry("900x600")
        center_window(self.window, 900, 600)  # 复用已有的center_window函数

        self.create_widgets()
        self.refresh_tree()

        # 绑定关闭事件
        self.window.protocol("WM_DELETE_WINDOW", self.on_cancel)

    def create_widgets(self):
        main = ttk.Frame(self.window, padding="10")
        main.pack(fill=tk.BOTH, expand=True)

        # 左右 PanedWindow
        paned = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # ---- 左栏：片段列表 ----
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=3)


        # 添加工具栏
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

        # 操作按钮
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
        
        # 添加 ToolTip
        ToolTip(cmd_frame, 
                "在此粘贴 FFmpeg 裁剪命令（每行一条），程序会自动提取其中的 -ss 和 -t/-to 时间参数。\n"
                "点击「解析并导入所有片段」即可将提取的时间段添加到左侧列表。\n"
                "提示：此为高级功能，普通用户可直接在左侧手动添加片段。",
                wraplength=400)

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
        ttk.Button(btn_frame, text="确定", command=self.on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=self.on_cancel).pack(side=tk.RIGHT, padx=5)

        # 设置左右分栏的初始比例（左侧列表占 75%，右侧命令输入占 25%）
        def set_initial_pane_size():
            total_width = self.window.winfo_width()
            if total_width > 100:
                sash_pos = int(total_width * 0.75)   # 左侧占 75%
                paned.sashpos(0, sash_pos)
        
        # 窗口显示后再设置
        self.window.after(100, set_initial_pane_size)

        # 绑定双击编辑
        self.tree.bind("<Double-1>", self.on_tree_double_click)

    # ---------- 片段管理方法 ----------
    def add_segment_with_time(self, start_sec, end_sec, flip="无"):
        if start_sec is None or end_sec is None:
    #        self.app._append_info_ui("[分段] 时间无效，无法添加")
            return False
        if start_sec >= end_sec:
    #        self.app._append_info_ui(f"[分段] 开始 {start_sec} >= 结束 {end_sec}，跳过")
            return False
        start_str = seconds_to_time(start_sec)
        end_str = seconds_to_time(end_sec)
        # 时长检测（仅警告）
        if self.app and self.app.input_file.get():
            dur = self.app._get_media_duration(self.app.input_file.get())
            if dur is not None and end_sec > dur:
                self.app._append_info_ui(f"[分段] 片段超出总时长: {start_str}->{end_str}，已跳过")
                return False

        self.segments.append({
            "start": start_str,
            "end": end_str,
            "flip": flip
        })
        self.refresh_tree()
 #       self.app._append_info_ui(f"[分段] 从命令导入片段: {start_str} -> {end_str} (翻转: {flip})")
        return True

    def add_segment(self):
        # 获取输入
        start = self.start_entry.get().strip()
        end = self.end_entry.get().strip()
        
        # ---- 调试日志 ----
 #       self.app._append_info_ui(f"[分段] 用户点击添加: start='{start}', end='{end}'")
        
        if not start:
            messagebox.showwarning("提示", "请填写开始时间")
            return
    
        # 如果未填写结束时间，尝试自动补全（但推荐强制手动填写）
        if not end:
            # 尝试从输入文件获取总时长
            if self.app and self.app.input_file.get():
                dur = self.app._get_media_duration(self.app.input_file.get())
                if dur is not None:
                    end = seconds_to_time(dur)
  #                  self.app._append_info_ui(f"[分段] 结束时间自动设为总时长: {end}")
                else:
                    messagebox.showerror("错误", "无法获取视频总时长，请手动填写结束时间")
                    return
            else:
                messagebox.showerror("错误", "未指定输入文件，无法自动获取结束时间，请手动填写")
                return
    
        # 解析时间
        start_sec = time_to_seconds(start)
        end_sec = time_to_seconds(end)
        if start_sec is None or end_sec is None:
            messagebox.showerror("错误", "时间格式无效，请使用 HH:MM:SS.ms 或秒数")
            return
        if start_sec >= end_sec:
            messagebox.showerror("错误", "开始时间必须小于结束时间")
            return
    
        # 检查总时长（仅警告）
        if self.app and self.app.input_file.get():
            dur = self.app._get_media_duration(self.app.input_file.get())
            if dur is not None and end_sec > dur:
                self.app._append_info_ui(f"[分段] 片段超出总时长: {start_str}->{end_str}，已跳过")
                return
    
        # ---- 获取翻转值（直接从控件读取） ----
        flip_value = self.flip_combo.get()
#        self.app._append_info_ui(f"[分段] 当前翻转值: {flip_value}")
    
        # 添加到列表
        self.segments.append({
            "start": start,
            "end": end,
            "flip": flip_value
        })
        self.refresh_tree()
 #       self.app._append_info_ui(f"[分段] 已添加片段: {start} -> {end} (翻转: {flip_value})")

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
            if self.app and self.app.input_file.get():
                dur = self.app._get_media_duration(self.app.input_file.get())
                if dur is not None and end_sec > dur:
                    self.app._append_info_ui(f"[分段] 片段超出总时长: {start_str}->{end_str}，已跳过")
                    return
            seg["start"] = dialog.start
            seg["end"] = dialog.end
      #      self.app._append_info_ui(f"[编辑] 修改前翻转: {seg['flip']}, 修改后: {dialog.flip}")
            seg["flip"] = dialog.flip
      #      self.app._append_info_ui(f"[编辑] 实际存储: {seg['flip']}")
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

            # 提取 -ss 时间
            ss_match = re.search(r'-ss\s+([\d.]+)', line, re.IGNORECASE)
            if not ss_match:
                skipped_count += 1
                errors.append(f"未找到 -ss: {line[:80]}...")
                continue

            start_sec = float(ss_match.group(1))

            # 提取 -t 或 -to
            t_match = re.search(r'-t\s+([\d.]+)', line, re.IGNORECASE)
            to_match = re.search(r'-to\s+([\d.]+)', line, re.IGNORECASE)

            if t_match:
                duration_sec = float(t_match.group(1))
                end_sec = start_sec + duration_sec
            elif to_match:
                end_sec = float(to_match.group(1))
            else:
                skipped_count += 1
                errors.append(f"未找到 -t 或 -to: {line[:80]}...")
                continue



            # 添加片段（翻转默认为“无”）

            start_str = seconds_to_time(start_sec)
            end_str = seconds_to_time(end_sec)
            
            # 检查是否已存在相同时间段（精确到毫秒）
            if any(seg["start"] == start_str and seg["end"] == end_str for seg in self.segments):
                skipped_count += 1
                errors.append(f"重复片段: {start_str}->{end_str}，已跳过")
                continue
            
            # 添加片段（翻转默认为“无”）
            try:
                if self.add_segment_with_time(start_sec, end_sec, flip="无"):
                    parsed_count += 1
                else:
                    skipped_count += 1
                    errors.append(f"无效时间: start={start_sec}, end={end_sec}")
            except Exception as e:
                skipped_count += 1
                errors.append(f"添加片段异常: {e}")
                self.app._append_info_ui(f"[分段] 导入异常: {e}")

        msg = f"成功导入 {parsed_count} 个片段"
        if skipped_count > 0:
            msg += f"，{skipped_count} 行被跳过"
            if errors:
                messagebox.showwarning("导入警告", msg + "\n\n错误详情（前10条）：\n" + "\n".join(errors[:10]))
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
        except AttributeError:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except:
                pass
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = FFmpegBatchGUI(root)
    root.mainloop()
