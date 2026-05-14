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
import concurrent.futures

# --- 优化：自动检测拖拽依赖，缺失时仅提示而不退出 ---
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True  # 标记拖拽库可用
except ImportError:
    DND_AVAILABLE = False # 标记拖拽库不可用
    # 弹出普通警告提示框，告知用户当前无法使用拖拽
    root_temp = tk.Tk()
    root_temp.withdraw() 
    messagebox.showwarning("功能受限提示", "未检测到 tkinterdnd2 库，当前不支持文件拖拽功能！\n\n如需使用拖拽，请在终端运行：pip install tkinterdnd2")
    root_temp.destroy()
# ----------------------------------------

def get_script_dir():
    """获取脚本所在的目录（兼容打包后的 exe）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

def find_executable(name):
    """
    优先在脚本目录下查找可执行文件，再查找系统 PATH。
    返回完整的可执行文件路径，如果都没找到则返回 None。
    """
    # 1. 脚本目录下查找
    local_path = os.path.join(get_script_dir(), name)
    if os.path.isfile(local_path) and os.access(local_path, os.X_OK):
        return local_path
    # 2. 系统 PATH 中查找
    return shutil.which(name)


PRESET_FILE = "ffmpeg_presets.json"
CUSTOM_PRESET_PATH = None       # None 用上面的本地目录json，硬编码d:\123.json 就用具体路径

# 2. 你的智能路径处理逻辑
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

APP_NAME = "FFLiteGUI"
USER_DATA_DIR = os.path.join(os.path.expanduser("~"), f".{APP_NAME}")
os.makedirs(USER_DATA_DIR, exist_ok=True)

if CUSTOM_PRESET_PATH:
    FINAL_PRESET_PATH = CUSTOM_PRESET_PATH
else:
    FINAL_PRESET_PATH = os.path.join(USER_DATA_DIR, PRESET_FILE)

# 释放默认配置（如果用户目录下还没有）
bundled_default_config = os.path.join(BUNDLE_DIR, PRESET_FILE)
if not os.path.exists(FINAL_PRESET_PATH) and os.path.exists(bundled_default_config):
    try:
        shutil.copy2(bundled_default_config, FINAL_PRESET_PATH)
        print(f"首次运行，已从内部释放默认配置到：{FINAL_PRESET_PATH}")
    except Exception as e:
        print(f"释放配置文件失败: {e}")



# ================== FFmpeg 编码器选项 ==================
ALL_VIDEO_ENCODERS = [
    "libx264", "libx265", "libvpx-vp9", "libsvtav1", "mpeg4", "libxvid", "libtheora",
    "h264_nvenc", "hevc_nvenc", "av1_nvenc",
    "h264_qsv", "hevc_qsv", "av1_qsv",
    "h264_amf", "hevc_amf", "av1_amf",
    "h264_vaapi", "hevc_vaapi",
    "h264_videotoolbox", "hevc_videotoolbox",
    "prores_ks", "prores_aw", "dnxhdenc", "ffv1", "libopenjpeg", "gif", "copy"
]

ALL_AUDIO_ENCODERS = ["aac", "libmp3lame", "opus", "ac3", "eac3",
                      "flac", "alac", "pcm_s16le", "libfdk_aac", "copy"]

# ================== 硬件解码器选项 ==================
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

# 映射选项到实际的 ffmpeg 参数格式
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

#-----提示类-----
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

        # Clamp 坐标到屏幕内
        x = max(0, min(ideal_x, screen_width - win_width))
        y = max(0, min(ideal_y, screen_height - win_height))

        # 防止窗口遮挡鼠标（可选增强）
        if x <= mouse_x <= x + win_width and y <= mouse_y <= y + win_height:
            # 简单反方向偏移 10 像素
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
            ok, msg = ParamValidator.validate_global_quality(settings.get("global_quality", 25))
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

# ================== 编码器策略==================
class EncoderStrategy:
    def build_params(self, settings, parts):
        raise NotImplementedError

class SoftwareEncoderStrategy(EncoderStrategy):
    def build_params(self, settings, parts):
        vcodec = settings["encoder"]
        rc = settings["rate_control_type"]
        preset = settings.get("preset", "medium")
        parts.append(f"-c:v {vcodec} -preset {preset}")
        if rc == "crf":
            parts.append(f"-crf {settings['crf_value']}")
        elif rc == "bitrate":
            bitrate = settings["bitrate_video"].strip()
            bitrate = bitrate + "k" if bitrate.isdigit() else bitrate
            parts.append(f"-b:v {bitrate or '1000k'}")
        return parts

class NVENCEncoderStrategy(EncoderStrategy):
    def build_params(self, settings, parts):
        vcodec = settings["encoder"]
        preset = settings.get("preset", "p4")
        rc = settings["rate_control_type"]
        parts.append(f"-c:v {vcodec} -preset {preset}")
        if rc == "cq":
            parts.append(f"-cq {settings['cq_value']}")
        elif rc == "bitrate":
            bitrate = settings["bitrate_video"].strip()
            bitrate = bitrate + "k" if bitrate.isdigit() else bitrate
            parts.append(f"-b:v {bitrate or '1000k'}")
        return parts

class QSVEncoderStrategy(EncoderStrategy):
    def build_params(self, settings, parts):
        vcodec = settings["encoder"]
        preset = settings.get("preset", "p4")
        rc = settings["rate_control_type"]
        parts.append(f"-c:v {vcodec} -preset {preset}")
        if rc == "global_quality":
            parts.append(f"-global_quality {settings['global_quality']}")
        elif rc == "bitrate":
            bitrate = settings["bitrate_video"].strip()
            bitrate = bitrate + "k" if bitrate.isdigit() else bitrate
            parts.append(f"-b:v {bitrate or '1000k'}")
        return parts

class OtherEncoderStrategy(EncoderStrategy):
    def build_params(self, settings, parts):
        vcodec = settings["encoder"]
        bitrate = settings["bitrate_video"].strip()
        bitrate = bitrate + "k" if bitrate.isdigit() else bitrate
        parts.append(f"-c:v {vcodec} -b:v {bitrate or '1000k'}")
        return parts

def get_encoder_strategy(encoder):
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
    def __init__(self, parent, **kwargs):
        super().__init__(parent, text="视频编码与质量", padding="5", **kwargs)
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
        self.dynamic_frame.grid(row=3, column=0, columnspan=3, sticky="we", pady=5, padx=5)

        self.crf_value = tk.IntVar(value=25)
        self.cq_value = tk.IntVar(value=35)
        self.global_quality = tk.IntVar(value=25)
        self.bitrate_video = tk.StringVar(value="1900k")

        self.update_dynamic_controls()

    def setup_bindings(self):
        self.vcodec.trace_add("write", self.auto_set_rate_control_by_codec)
        self.rate_control_type.trace_add("write", self.on_rate_control_change)

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
            ttk.Label(frame, text="固定比特率 (单位 kbps，例如 1900k 或 1900):").pack(side=tk.LEFT)
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
        self.update_dynamic_controls()
        self.auto_set_codec_by_rate_control()
        rc = self.rate_control_type.get()
        if rc == "crf" or rc == "global_quality":
            self.preset.set("medium")
        elif rc == "cq":
            self.preset.set("p4")

    def auto_set_codec_by_rate_control(self):
        rc = self.rate_control_type.get()
        current = self.vcodec.get()
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
            "bitrate_video": self.bitrate_video.get()
        }

    def set_settings(self, settings):
        self.vcodec.set(settings.get("encoder", "libx265"))
        self.preset.set(settings.get("preset", "p4"))
        self.rate_control_type.set(settings.get("rate_control_type", "crf"))
        self.crf_value.set(settings.get("crf_value", 26))
        self.cq_value.set(settings.get("cq_value", 35))
        self.global_quality.set(settings.get("global_quality", 26))
        self.bitrate_video.set(settings.get("bitrate_video", "1900k"))


# ================== 视频滤镜组件 ==================
class VideoFilterFrame(ttk.LabelFrame):
    PIX_FMTS = [
        "yuv420p", "yuv422p", "yuv444p",
        "yuv420p10le", "yuv422p10le", "yuv444p10le",
        "p010le", "p016le", "nv12", "nv16",
        "gbrp", "gbrp10le", "gray", "gray10le", "ya8", "yuva420p"
    ]

    def __init__(self, parent, **kwargs):
        super().__init__(parent, text="视频滤镜 (缩放/裁剪/旋转/变速)", padding="5", **kwargs)
        self.create_widgets()

    def create_widgets(self):
        # 创建左右分栏的主容器
        main_pane = ttk.Frame(self)
        main_pane.pack(fill=tk.BOTH, expand=True)
    
        left_frame = ttk.Frame(main_pane)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
    
        right_frame = ttk.LabelFrame(main_pane, text="截取片段", padding="5")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
    
        # ========== 左侧：原有所有控件 ==========
        # 第一行：帧率 + 烧录字幕（放在同一行）
        line1 = ttk.Frame(left_frame)
        line1.pack(fill=tk.X, pady=2)
    
        # 帧率部分
        ttk.Label(line1, text="帧率:").pack(side=tk.LEFT)
        self.frame_rate_type = tk.StringVar(value="keep")
        self.frame_rate_custom = tk.StringVar(value="30")
        ttk.Radiobutton(line1, text="保持源", variable=self.frame_rate_type,
                        value="keep").pack(side=tk.LEFT, padx=(5, 0))
        ttk.Radiobutton(line1, text="指定", variable=self.frame_rate_type,
                        value="custom").pack(side=tk.LEFT, padx=5)
        self.fps_combo = ttk.Combobox(
            line1,
            textvariable=self.frame_rate_custom,   # 仍使用原来的变量
            width=9,
            values=["30", "29.970030", "23.976024", "24", "25", "48", "59.940060", "60", "50"]  # 常用帧率
        )
        self.fps_combo.pack(side=tk.LEFT, padx=(0, 2))
        ttk.Label(line1, text="fps").pack(side=tk.LEFT, padx=(0, 10))
    
        # 烧录字幕部分（放在同一行，紧跟在 fps 后面）
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
    
        # 初始状态（字幕未启用）
        if not self.subtitle_enabled.get():
            self.subtitle_entry.config(state="disabled")
            self.browse_subtitle_btn.config(state="disabled")
    
        # 缩放、裁剪、旋转、变速等原有控件保持不变（从下一行开始）
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
        ttk.Checkbutton(crop_frame, text="启用裁剪", variable=self.crop_enabled).pack(side=tk.LEFT)
        ttk.Label(crop_frame, text="宽:").pack(side=tk.LEFT)
        ttk.Entry(crop_frame, textvariable=self.crop_width, width=8).pack(side=tk.LEFT)
        ttk.Label(crop_frame, text="高:").pack(side=tk.LEFT)
        ttk.Entry(crop_frame, textvariable=self.crop_height, width=8).pack(side=tk.LEFT)
        ttk.Label(crop_frame, text="左:").pack(side=tk.LEFT, padx=(10,0))
        ttk.Entry(crop_frame, textvariable=self.crop_left, width=6).pack(side=tk.LEFT)
        ttk.Label(crop_frame, text="上:").pack(side=tk.LEFT)
        ttk.Entry(crop_frame, textvariable=self.crop_top, width=6).pack(side=tk.LEFT)
    
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
    
        # ========== 右侧：截取模块 ==========
        self.trim_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(right_frame, text="启用截取片段", variable=self.trim_enabled,
                        command=self.on_trim_toggle).pack(anchor=tk.W, pady=(0,10))
    
        time_frame = ttk.Frame(right_frame)
        time_frame.pack(fill=tk.X, pady=2)
        ttk.Label(time_frame, text="开始时间 (HH:MM:SS[.mmm]):").pack(side=tk.LEFT)
        self.trim_start_v = tk.StringVar(value="0")
        self.trim_start_entry = ttk.Entry(time_frame, textvariable=self.trim_start_v, width=12)
        self.trim_start_entry.pack(side=tk.LEFT, padx=5)
    
        time_frame2 = ttk.Frame(right_frame)
        time_frame2.pack(fill=tk.X, pady=2)
        ttk.Label(time_frame2, text="结束时间 (HH:MM:SS[.mmm]):").pack(side=tk.LEFT)
        self.trim_end_v = tk.StringVar(value="")
        self.trim_end_entry = ttk.Entry(time_frame2, textvariable=self.trim_end_v, width=12)
        self.trim_end_entry.pack(side=tk.LEFT, padx=5)
    
        info_label = ttk.Label(right_frame, text="示例: 01:23:45 或 01:23:45.500 (留空表示到文件末尾)", foreground="gray")
        info_label.pack(anchor=tk.W, pady=(5,0))
    
        self.on_trim_toggle()

    def on_trim_toggle(self):
        state = tk.NORMAL if self.trim_enabled.get() else tk.DISABLED
        self.trim_start_entry.config(state=state)
        self.trim_end_entry.config(state=state)

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
            self.subtitle_path.set(self.normalize_path(path))

    def normalize_path(self, path):
        return path.replace('\\', '/')

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
            "trim_enabled": self.trim_enabled.get(),
            "trim_start": self.trim_start_v.get(),
            "trim_end": self.trim_end_v.get()
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
        # 兼容旧预设
        if "deinterlace" in settings and not "deinterlace_filter" in settings:
            self.deinterlace_filter.set("yadif" if settings["deinterlace"] else "none")
        self.pix_fmt_enabled.set(settings.get("pix_fmt_enabled", True))
        self.pix_fmt.set(settings.get("pix_fmt", "yuv420p"))
        self.subtitle_enabled.set(settings.get("subtitle_enabled", False))
        self.subtitle_path.set(settings.get("subtitle_path", ""))
        # 截取片段设置
        self.trim_enabled.set(settings.get("trim_enabled", False))
        self.trim_start_v.set(settings.get("trim_start", "0"))
        self.trim_end_v.set(settings.get("trim_end", ""))
        self.toggle_subtitle()
        self.on_trim_toggle()   # 控制输入框的启用/禁用状态

# ================== 音频组件 ==================
class AudioFrame(ttk.LabelFrame):
    def __init__(self, parent, enable_checkbox=False, **kwargs):
        super().__init__(parent, text="音频", padding="5", **kwargs)
        self.enable_checkbox = enable_checkbox
        self.create_widgets()

    def create_widgets(self):
        inner = ttk.Frame(self)
        inner.pack(fill=tk.X, expand=True)

    def create_widgets(self):
        inner = ttk.Frame(self)
        inner.pack(fill=tk.X, expand=True)
    
        # 第一行：保留音频和仅提取音频顺序左对齐
        top_row = ttk.Frame(inner)
        top_row.pack(fill=tk.X, pady=(0,5))

        if self.enable_checkbox:
            self.audio_enabled = tk.BooleanVar(value=True)
            chk = ttk.Checkbutton(top_row, text="保留音频", variable=self.audio_enabled)
            chk.pack(side=tk.LEFT)

        self.only_audio = tk.BooleanVar(value=False)
        self.only_audio_cb = ttk.Checkbutton(top_row, text="仅提取音频", variable=self.only_audio)
        self.only_audio_cb.pack(side=tk.LEFT, padx=(50,2))   # 左侧加一点间距，不要太大

        ttk.Label(top_row, text="输出容器:").pack(side=tk.LEFT, padx=(12,2))
        self.audio_format = tk.StringVar(value="mp3")
        audio_format_combo = ttk.Combobox(top_row, textvariable=self.audio_format,
                                          values=["mp3", "aac", "m4a", "flac", "opus", "wav", "ac3"],
                                          state="readonly", width=6)
        audio_format_combo.pack(side=tk.LEFT, padx=2)
        ToolTip(self.only_audio_cb, "勾选后，将只输出音频文件（自动添加 -vn 忽略视频），输出容器将使用右边选择的音频格式", offset_x=0, offset_y=5)
    
        # 第二行：编码器、比特率、采样率
        controls_frame = ttk.Frame(inner)
        controls_frame.pack(fill=tk.X, expand=True, pady=(5,0))
        ttk.Label(controls_frame, text="编码器:").pack(side=tk.LEFT)
        self.audio_codec = tk.StringVar(value="aac")
        ttk.Combobox(controls_frame, textvariable=self.audio_codec,
                     values=ALL_AUDIO_ENCODERS, state="readonly", width=10).pack(side=tk.LEFT, padx=5)
        # 比特率下拉
        ttk.Label(controls_frame, text="比特率:").pack(side=tk.LEFT)
        self.audio_bitrate = tk.StringVar(value="128k")
        bitrate_combo = ttk.Combobox(controls_frame, textvariable=self.audio_bitrate, width=6, values=["64k","96k", "128k", "192k", "256k", "320k"], state='readonly')
        bitrate_combo.pack(side=tk.LEFT, padx=5)
        
        # 采样率下拉
        ttk.Label(controls_frame, text="采样率:").pack(side=tk.LEFT)
        self.audio_samplerate = tk.StringVar(value="44100")
        samplerate_combo = ttk.Combobox(controls_frame, textvariable=self.audio_samplerate, width=8, values=["8000","12000","16000","22050","32000", "44100", "48000", "96000"], state='readonly')
        samplerate_combo.pack(side=tk.LEFT, padx=5)

    def get_settings(self):
        res = {
            "audio_codec": self.audio_codec.get(),
            "audio_bitrate": self.audio_bitrate.get(),
            "audio_samplerate": self.audio_samplerate.get(),
            "only_audio": self.only_audio.get(),
            "audio_format": self.audio_format.get()
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

# ================== Task 类 ==================
class Task:
    def __init__(self, input_path, output_path, settings, cmd):
        self.input = input_path
        self.output = output_path
        self.settings = copy.deepcopy(settings)
        self.cmd = cmd
        self.status = "等待"
        self.error_msg = ""

    def get_short_cmd(self):
        short = self.cmd
        short = re.sub(r'(-i\s+)(["\'])(.*?)\2', r'\1{input}', short)
        short = re.sub(r'(["\'][^"\']+\.mp4["\'])$', r'{output}', short)
        return short

# ================== Track 类 ==================
class Track:
    def __init__(self, index, typ, codec, file_path, enabled=True, enc_settings=None):
        self.index = index
        self.type = typ
        self.codec = codec
        self.file_path = file_path
        self.enabled = enabled
        if enc_settings is None:
            if typ == "video":
                # 从视频叠加位置（表达式，例如 "W-w-10"）
                self.overlay_enabled = False         # 是否叠加到主画布上
                self.overlay_x = "W-w-10"
                self.overlay_y = "H-h-10"
                # 主视频偏移属性（仅当该轨道是主视频时使用）
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
                    "subtitle_enabled": False, "subtitle_path": ""
                }
            elif typ == "audio":
                self.enc_settings = {"encoder": "copy", "bitrate": "128k", "samplerate": "44100"}
            else:
                self.enc_settings = {"encoder": "copy"}
        else:
            self.enc_settings = copy.deepcopy(enc_settings)

    def is_encoding(self):
        return self.enc_settings.get("encoder") != "copy"

# ================== 主界面 ==================
class FFmpegBatchGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FFmpeg 多功能工具")
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        width = 1600
        height = 940
        x = (screen_width - width) // 2
        y = (screen_height - height) // 3
        root.geometry(f"{width}x{height}+{x}+{y}")

        self.ffmpeg_cmd = find_executable("ffmpeg.exe") or find_executable("ffmpeg")
        self.ffplay_cmd = find_executable("ffplay.exe") or find_executable("ffplay")
        self.ffprobe_cmd = find_executable("ffprobe.exe") or find_executable("ffprobe")

        self.input_file = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.output_suffix = tk.StringVar(value="")
        self.custom_output_name = tk.StringVar(value="")
        self.output_container = tk.StringVar(value="mp4")

        self.tasks = []
        self.is_processing = False
        self.stop_flag = False
        self.pending_tasks = []
        self.running_futures = set()
        self.executor = None

        self.current_hw_encoding_count = 0
        self.max_hw_parallel = tk.IntVar(value=2)

        self.merge_video = tk.StringVar()
        self.merge_tracks = []
        self.merge_container = tk.StringVar(value="mkv")
        self.merge_output = tk.StringVar()
        self.merge_delete_source = tk.BooleanVar(value=False)
        self.merge_verify = tk.BooleanVar(value=True)

        # 硬件解码相关变量
        self.hwaccel_enabled = tk.BooleanVar(value=False)
        self.hwaccel_decoder = tk.StringVar(value="无")  # 存储用户选择的显示文本

        self.custom_args = tk.StringVar(value="")

        self.copy_chapters = tk.BooleanVar(value=True)
        self.chapter_file = tk.StringVar(value="")



        self.create_widgets()
        self.update_task_list()
        self.update_command_preview()

        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<Drop>>', self.on_files_dropped)

        #============核心程序检查============
        self.show_quick_warning()

    def check_ffmpeg_dependencies(self):
        """检查 ffmpeg, ffplay, ffprobe 是否存在（优先本地目录，再查 PATH）"""
        ffmpeg = find_executable("ffmpeg.exe") or shutil.which("ffmpeg")
        ffplay = find_executable("ffplay.exe") or shutil.which("ffplay")
        ffprobe = find_executable("ffprobe.exe") or shutil.which("ffprobe")
        return ffmpeg, ffplay, ffprobe

    def show_quick_warning(self):
        """检查 FFmpeg 组件，若缺失则输出提示到右侧日志（不弹窗）"""
        missing = []
        if not self.ffmpeg_cmd: missing.append("ffmpeg")
        if not self.ffplay_cmd: missing.append("ffplay")
        if not self.ffprobe_cmd: missing.append("ffprobe")
        if missing:
            missing_str = "、".join(missing)
            self.append_info("⚠️ 必要组件缺失: " + missing_str)
            self.append_info("请确保 FFmpeg 已正确安装。快捷方法：")
            self.append_info("  ① 将 ffmpeg.exe、ffplay.exe、ffprobe.exe 放在本脚本同一目录下（推荐，绿色便携）")
            self.append_info("  ② 或者将它们所在文件夹的路径添加到系统 Path 环境变量中")
            self.append_info("推荐下载 FFmpeg 的 **shared** 版本（体积小，节约空间）：")
            self.append_info("下载地址: https://github.com/BtbN/FFmpeg-Builds/releases")
            self.append_info("选择文件名中包含 'shared' 的版本，例如: ffmpeg-master-latest-win64-gpl-shared.zip")
            self.append_info("解压后，将 bin 文件夹内的三个 exe 文件复制到本脚本目录，或添加 bin 路径到 Path。")
            self.append_info("提示：您可以在此日志框中直接选中上面的链接文字，右键复制。")
    #============核心程序检查结束============


    def center_window(self, win, width, height):
        """将 Toplevel 窗口居中显示"""
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        win.geometry(f"{width}x{height}+{x}+{y}")

    # ---------- 辅助方法 ----------
    def normalize_path(self, path):
        return path.replace('\\', '/')

    def quote_path(self, path):
        return f'"{path}"'

    def ensure_output_dir(self, output_path):
        dirname = os.path.dirname(output_path)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname, exist_ok=True)

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
                self.append_info(f"日志已保存到 {file_path}")
            except Exception as e:
                messagebox.showerror("保存失败", str(e))

    def get_current_settings(self):
        settings = {}
        settings.update(self.video_encoder.get_settings())
        settings.update(self.video_filter.get_settings())
        settings.update(self.audio_frame.get_settings())
        settings["output_dir"] = self.output_dir.get()
        settings["output_suffix"] = self.output_suffix.get()
        settings["custom_output_name"] = self.custom_output_name.get()
        settings["output_container"] = self.output_container.get()
        settings["hwaccel_enabled"] = self.hwaccel_enabled.get()
        settings["hwaccel_decoder"] = self.hwaccel_decoder.get()   # 存储显示文本
        settings["custom_args"] = self.custom_args.get().strip()
        settings["pip_enabled"] = self.pip_enabled.get()

        return settings

    def load_settings_into_ui(self, settings):
        self.output_dir.set(settings.get("output_dir", ""))
        self.output_suffix.set(settings.get("output_suffix", ""))
        self.custom_output_name.set(settings.get("custom_output_name", ""))
        self.output_container.set(settings.get("output_container", "mp4"))
        self.video_encoder.set_settings(settings)
        self.video_filter.set_settings(settings)
        self.audio_frame.set_settings(settings)
        self.hwaccel_enabled.set(settings.get("hwaccel_enabled", False))
        self.pip_enabled.set(settings.get("pip_enabled", False))
        # 兼容旧版预设：如果 old style 存在则转换
        old_type = settings.get("hwaccel_type")
        new_decoder = settings.get("hwaccel_decoder")
        if old_type and not new_decoder:
            # 尝试映射旧值到新选项
            mapping = {
                "auto": "auto (自动通用)",
                "cuvid": "cuda (NVIDIA通用)",
                "qsv": "qsv (Intel通用)",
                "vaapi": "vaapi (Linux VAAPI)",
                "videotoolbox": "videotoolbox (macOS)"
            }
            self.hwaccel_decoder.set(mapping.get(old_type, "无"))
        else:
            self.hwaccel_decoder.set(settings.get("hwaccel_decoder", "无"))
        self.custom_args.set(settings.get("custom_args", ""))
        self.toggle_hwaccel()
        self.toggle_only_audio_mode()  # 根据加载的预设同步控件禁用状态

    def build_filter_chain(self, settings):
        filters = []
        if settings.get("crop_enabled", False):
            w = settings.get("crop_width", "").strip()
            h = settings.get("crop_height", "").strip()
            left = settings.get("crop_left", "").strip()
            top = settings.get("crop_top", "").strip()
            if w and h:
                left = left or "0"
                top = top or "0"
                filters.append(f"crop={w}:{h}:{left}:{top}")
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
        deint = settings.get("deinterlace_filter", "none")
        if deint != "none":
            filters.append(deint)
        if settings.get("pix_fmt_enabled", True):
            filters.append(f"format={settings.get('pix_fmt','yuv420p')}")
        if settings.get("speed_enabled", False):
            try:
                factor = float(settings.get("speed_factor", "1.0"))
                if factor > 0 and factor != 1.0:
                    filters.append(f"setpts={1.0/factor}*PTS")
            except ValueError:
                pass
        if settings.get("subtitle_enabled", False) and settings.get("subtitle_path", "").strip():
            sub_path = settings["subtitle_path"].strip()
            if sub_path.startswith('"') and sub_path.endswith('"'):
                sub_path = sub_path[1:-1]
            sub_path = sub_path.replace('\\', '/')
            sub_path = sub_path.replace(':', '\\:')
            sub_path = sub_path.replace("'", "\\'")
            filters.append(f"subtitles='{sub_path}'")
        return ",".join(filters) if filters else ""

    def generate_output_path(self, input_path, settings):
        dir_path = settings.get("output_dir") or os.path.dirname(input_path)
        dir_path = self.normalize_path(dir_path)
        base_name = os.path.basename(input_path)
        name, _ = os.path.splitext(base_name)
        # 仅音频模式优先使用 audio_format，否则使用 output_container
        if settings.get("only_audio", False):
            container = settings.get("audio_format", "mp3")
        else:
            container = settings.get("output_container", "mp4")
        custom_name = settings.get("custom_output_name", "").strip()
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
        return os.path.join(dir_path, out_name).replace('\\', '/')

    def generate_ffmpeg_command(self, input_path, output_path, settings):
        if not self.ffmpeg_cmd:
            raise ValueError("未找到 ffmpeg 可执行文件。请将 ffmpeg.exe 放在脚本目录或添加到 PATH。")
        errors = ParamValidator.validate_settings(settings)
        if errors:
            raise ValueError("参数错误:\n" + "\n".join(errors))
    
        input_path = self.normalize_path(input_path)
        output_path = self.normalize_path(output_path)
        parts = [self.ffmpeg_cmd, "-y", "-fflags", "+genpts"]
    
        only_audio = settings.get("only_audio", False)   # <-- 提前定义
    
        # 截取参数（放在 -i 之前，实现快速 seek）
        if not only_audio and settings.get("trim_enabled", False):
            start = settings.get("trim_start", "").strip()
            end = settings.get("trim_end", "").strip()
            if start:
                parts.extend(["-ss", start])
            if end:
                parts.extend(["-to", end])
    
        # 硬件解码 (仅当不只有音频时才有意义)
        if not only_audio and settings.get("hwaccel_enabled", False):
            decoder_display = settings.get("hwaccel_decoder", "无")
            decoder_key = DECODER_MAP.get(decoder_display, "none")
            if decoder_key != "none":
                if decoder_key in ("h264_cuvid", "hevc_cuvid", "vp9_cuvid", "av1_cuvid",
                                   "h264_qsv", "hevc_qsv"):
                    parts.extend(["-c:v", decoder_key])
                elif decoder_key in ("auto", "cuda", "qsv", "vaapi", "videotoolbox"):
                    if decoder_key == "auto":
                        parts.extend(["-hwaccel", "auto"])
                    elif decoder_key == "cuda":
                        parts.extend(["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"])
                    elif decoder_key == "qsv":
                        parts.extend(["-hwaccel", "qsv", "-hwaccel_output_format", "qsv"])
                    elif decoder_key == "vaapi":
                        parts.extend(["-hwaccel", "vaapi", "-hwaccel_output_format", "vaapi"])
                    elif decoder_key == "videotoolbox":
                        parts.extend(["-hwaccel", "videotoolbox"])

        parts.extend(["-i", self.quote_path(input_path)])

        # 仅音频模式：添加 -vn，跳过所有视频相关参数
        if only_audio:
            parts.append("-vn")
        else:
            # 视频滤镜
            vf = self.build_filter_chain(settings)
            if vf:
                parts.append(f"-vf {vf}")
            # 帧率
            if settings.get("frame_rate_type") == "custom" and settings.get("frame_rate_custom"):
                parts.append(f"-r {settings['frame_rate_custom']}")
            # 视频编码器参数
            vcodec = settings["encoder"]
            strategy = get_encoder_strategy(vcodec)
            parts = strategy.build_params(settings, parts)

        # 音频参数 (保持不变)
        try:
            speed_val = float(settings.get("speed_factor", "1.0"))
            if speed_val <= 0:
                speed_val = 1.0
        except ValueError:
            speed_val = 1.0
        audio_needs_speed = settings.get("speed_enabled", False) and speed_val != 1.0
        factor = speed_val

        if not settings.get("audio_enabled", True):
            parts.append("-an")
        else:
            acodec = settings["audio_codec"]
            if acodec == "copy":
                if audio_needs_speed:
                    parts.append("-c:a aac")
                    parts.append(f"-b:a {settings['audio_bitrate']}")
                    parts.append(f"-ar {settings['audio_samplerate']}")
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
                    if chain:
                        af_filters = [f"atempo={self._format_atempo(v)}" for v in chain]
                        parts.append(f"-af {','.join(af_filters)}")
                else:
                    parts.append("-c:a copy")
            else:
                parts.append(f"-c:a {acodec}")
                parts.append(f"-b:a {settings['audio_bitrate']}")
                parts.append(f"-ar {settings['audio_samplerate']}")
                if audio_needs_speed:
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
                    if chain:
                        af_filters = [f"atempo={self._format_atempo(v)}" for v in chain]
                        parts.append(f"-af {','.join(af_filters)}")

        # 自定义参数
        custom = settings.get("custom_args", "").strip()
        if custom:
            try:
                import shlex
                parts.extend(shlex.split(custom))
            except:
                parts.extend(custom.split())

        # 容器优化 (仅当不是仅音频模式或者仅音频模式但容器为 mp4/mov 时？一般只对视频容器添加 faststart，纯音频通常不需要，但仍可保留，无大碍)
        if not only_audio:
            container = settings.get("output_container", "mp4").lower()
            if container in ("mp4", "mov"):
                parts.extend(["-movflags", "+faststart"])

        parts.append(self.quote_path(output_path))
        return " ".join(parts)

    @staticmethod
    def _format_atempo(factor):
        """格式化 atempo 参数，去掉多余的小数点和尾随零"""
        s = f"{factor:.10f}".rstrip('0').rstrip('.')
        return s

    # ---------- 预览功能 ----------
    def preview_current_file(self):
        path = self.input_file.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("错误", "请先选择一个有效的输入文件")
            return
        settings = self.get_current_settings()
        filter_chain = self.build_filter_chain(settings)
        self._play_with_ffplay(path, filter_chain)

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
        filter_chain = self.build_filter_chain(task.settings)
        self._play_with_ffplay(task.input, filter_chain)

    def _play_with_ffplay(self, path, filter_chain=None):
        if not self.ffplay_cmd:
            self.append_info("❌ 未找到 ffplay，无法预览。请将 ffplay.exe 放在脚本目录或添加到 PATH。")
            return

        try:
            # 构建视频滤镜：原始 filter_chain + 强制缩放到高度 960（宽度自动）
            if filter_chain and filter_chain.strip():
                final_vf = f"{filter_chain},scale=-2:960"
            else:
                final_vf = "scale=-2:960"
            
            # 基础命令
            cmd = [self.ffplay_cmd, "-i", path, "-vf", final_vf, "-volume", "10"]
    
            # 添加音频变速滤镜（如果启用）
            settings = self.get_current_settings()
            if settings.get("speed_enabled", False):
                try:
                    factor = float(settings.get("speed_factor", "1.0"))
                    if factor > 0 and factor != 1.0:
                        # 分解因子到 [0.5, 2.0] 区间
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
            
                        if chain:
                            af_filters = [f"atempo={self._format_atempo(v)}" for v in chain]
                            cmd.extend(["-af", ",".join(af_filters)])
                except Exception:
                    pass  # 忽略错误，不影响预览
    
            subprocess.Popen(cmd)
            self.append_info(f"正在预览: {path}")
        except Exception as e:
            messagebox.showerror("错误", f"无法启动 ffplay:\n{str(e)}")

    def toggle_hwaccel(self):
        # 如果启用时用户选择的是"无"，则自动切换到"auto (自动通用)"
        if self.hwaccel_enabled.get() and self.hwaccel_decoder.get() == "无":
            self.hwaccel_decoder.set("auto (自动通用)")
        self.update_command_preview()

    def toggle_only_audio_mode(self):
        state = tk.DISABLED if self.audio_frame.only_audio.get() else tk.NORMAL
        # 禁用/启用视频相关控件
        for child in self.video_encoder.winfo_children():
            if isinstance(child, (ttk.Combobox, ttk.Entry, ttk.Scale, tk.Button, ttk.Radiobutton, ttk.Checkbutton)):
                try:
                    child.config(state=state)
                except:
                    pass
        for child in self.video_filter.winfo_children():
            if isinstance(child, (ttk.Combobox, ttk.Entry, ttk.Checkbutton, ttk.Radiobutton, tk.Button)):
                try:
                    child.config(state=state)
                except:
                    pass
        self.update_command_preview()

    def update_command_preview(self, *args):
        input_file = self.input_file.get()
        try:
            if not input_file:
                cmd = self.generate_ffmpeg_command("{input}", "{output}", self.get_current_settings())
            else:
                settings = self.get_current_settings()
                output_path = self.generate_output_path(input_file, settings)
                cmd = self.generate_ffmpeg_command(input_file, output_path, settings)
        except Exception as e:
            cmd = f"生成命令时出错: {e}"
        
        self.cmd_preview.delete(1.0, tk.END)
        self.cmd_preview.insert(tk.END, cmd)

    # ---------- 任务管理 ----------
    def is_duplicate_task(self, input_path, output_path):
        norm_in = self.normalize_path(input_path)
        norm_out = self.normalize_path(output_path)
        for task in self.tasks:
            if self.normalize_path(task.input) == norm_in and self.normalize_path(task.output) == norm_out:
                return True
        return False

    def add_task(self, input_path, settings=None):
        if settings is None:
            settings = self.get_current_settings()
        output_path = self.generate_output_path(input_path, settings)
        if self.is_duplicate_task(input_path, output_path):
            messagebox.showwarning("重复任务", f"任务已存在:\n输入: {input_path}\n输出: {output_path}")
            return False
        try:
            cmd = self.generate_ffmpeg_command(input_path, output_path, settings)
        except ValueError as e:
            messagebox.showerror("命令生成错误", str(e))
            return False
        task = Task(input_path, output_path, settings, cmd)
        self.tasks.append(task)
        self.update_task_list()
        self.append_info(f"已添加任务: {os.path.basename(input_path)} -> {output_path}")
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
            short_cmd = task.get_short_cmd()
            self.task_tree.insert("", tk.END, iid=str(i), values=(
                os.path.basename(task.input), task.output, short_cmd, task.status,
                task.error_msg[:100] if task.error_msg else ""
            ))

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
        self.append_info("收到停止信号，当前正在运行的任务将继续完成，不再启动新任务")
        self.root.after(100, self._check_and_finish_if_idle)
    
    def _check_and_finish_if_idle(self):
        if self.stop_flag and not self.running_futures:
            self._finish_queue()

    def start_queue(self):
        if self.is_processing:
            if not self.running_futures and not self.pending_tasks:
                self._finish_queue()
            else:
                messagebox.showinfo("提示", "队列已在运行中")
            return
        self.pending_tasks = [t for t in self.tasks if t.status == "等待"]
        if not self.pending_tasks:
            messagebox.showinfo("提示", "没有等待中的任务")
            return
        self.is_processing = True
        self.stop_flag = False
        max_workers = self.max_parallel.get()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.append_info(f"🚀 启动并行队列，最大并行任务数: {max_workers}，硬件编码最大并发: {self.max_hw_parallel.get()}")
        self._submit_next_batch()

    @staticmethod
    def is_hardware_encoder(encoder):
        hw_keywords = ('nvenc', 'qsv', 'amf', 'vaapi', 'videotoolbox')
        encoder_lower = encoder.lower()
        return any(kw in encoder_lower for kw in hw_keywords)

    def _submit_next_batch(self):
        # 如果设置了停止标志且没有正在运行的任务 -> 结束队列
        if self.stop_flag and not self.running_futures:
            self._finish_queue()
            return

        # 正常完成：没有待处理任务且没有正在运行的任务 -> 自动结束队列
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

    def _process_single_task(self, task):
        task.status = "转码中"
        self._update_task_list_ui()
        self._append_info_ui(f"\n========== 开始转码: {os.path.basename(task.input)} ==========")
        self._append_info_ui(f">>> {task.cmd}")
        self.ensure_output_dir(task.output)
        try:
            proc = subprocess.Popen(task.cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    universal_newlines=True, encoding='utf-8', errors='replace')
            for line in proc.stdout:
                self._append_detail_ui(line)
            proc.wait()
            if proc.returncode == 0:
                task.status = "完成"
                self._append_info_ui(f"✅ 任务完成: {os.path.basename(task.input)}")
            else:
                task.status = "失败"
                task.error_msg = f"返回码 {proc.returncode}"
                self._append_info_ui(f"❌ 任务失败: {os.path.basename(task.input)} (返回码 {proc.returncode})")
        except Exception as e:
            task.status = "失败"
            task.error_msg = str(e)
            self._append_info_ui(f"⚠️ 执行异常: {e}")
        finally:
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
            self.append_info("\n队列已停止")
        else:
            self.append_info("\n所有任务处理完成")
        self.stop_flag = False

    def _update_task_list_ui(self):
        self.root.after(0, self.update_task_list)

    def _append_info_ui(self, text):
        self.root.after(0, lambda: self.append_info(text))

    def _append_detail_ui(self, text):
        self.root.after(0, lambda: self.append_detail(text))

    def transcode_single(self):
        input_file = self.input_file.get()
        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("错误", "请选择有效的输入文件")
            return
        settings = self.get_current_settings()
        output_file = self.generate_output_path(input_file, settings)
        self.ensure_output_dir(output_file)
        try:
            cmd = self.generate_ffmpeg_command(input_file, output_file, settings)
        except ValueError as e:
            messagebox.showerror("命令生成错误", str(e))
            return
        threading.Thread(target=self._run_single_transcode, args=(cmd, input_file), daemon=True).start()

    def _run_single_transcode(self, cmd, input_name):
        self.append_info(f"\n========== 当前选择转码: {os.path.basename(input_name)} ==========")
        self.append_info(f">>> {cmd}")
        try:
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    universal_newlines=True, encoding='utf-8', errors='replace')
            for line in proc.stdout:
                self.append_detail(line)
            proc.wait()
            if proc.returncode == 0:
                self.append_info(f"✅ 当前选择转码完成: {os.path.basename(input_name)}")
            else:
                self.append_info(f"❌ 当前选择转码失败，返回码 {proc.returncode}")
        except Exception as e:
            self.append_info(f"⚠️ 执行异常: {e}")

    # ---------- 预设管理 ----------
    def get_preset_path(self):
        return FINAL_PRESET_PATH   # 直接使用全局变量

    def load_preset_list(self):
        FINAL_PRESET_PATH = self.get_preset_path()
        presets = {}
        if os.path.exists(FINAL_PRESET_PATH):
            try:
                with open(FINAL_PRESET_PATH, 'r', encoding='utf-8') as f:
                    presets = json.load(f)
            except: pass
        self.preset_combo['values'] = list(presets.keys())

    def save_preset(self):
        preset_name = simpledialog.askstring("保存预设", "请输入预设名称:", parent=self.root)
        if not preset_name: return
        preset_settings = self.get_current_settings()
        FINAL_PRESET_PATH = self.get_preset_path()
        presets = {}
        if os.path.exists(FINAL_PRESET_PATH):
            try:
                with open(FINAL_PRESET_PATH, 'r', encoding='utf-8') as f:
                    presets = json.load(f)
            except: pass
        presets[preset_name] = preset_settings
        with open(FINAL_PRESET_PATH, 'w', encoding='utf-8') as f:
            json.dump(presets, f, indent=4, ensure_ascii=False)
        self.load_preset_list()
        messagebox.showinfo("成功", f"预设“{preset_name}”已保存到:\n{FINAL_PRESET_PATH}")

    def load_preset(self, preset_name):
        if not preset_name: return
        FINAL_PRESET_PATH = self.get_preset_path()
        if not os.path.exists(FINAL_PRESET_PATH): return
        with open(FINAL_PRESET_PATH, 'r', encoding='utf-8') as f:
            presets = json.load(f)
        if preset_name not in presets: return
        self.load_settings_into_ui(presets[preset_name])
        messagebox.showinfo("成功", f"已加载预设“{preset_name}”")

    def delete_preset(self):
        preset_name = self.preset_name.get()
        if not preset_name:
            messagebox.showwarning("警告", "请先选择一个预设")
            return
        if not messagebox.askyesno("确认删除", f"确定要删除预设“{preset_name}”吗？"):
            return
        FINAL_PRESET_PATH = self.get_preset_path()
        if not os.path.exists(FINAL_PRESET_PATH): return
        with open(FINAL_PRESET_PATH, 'r', encoding='utf-8') as f:
            presets = json.load(f)
        if preset_name in presets:
            del presets[preset_name]
            with open(FINAL_PRESET_PATH, 'w', encoding='utf-8') as f:
                json.dump(presets, f, indent=4, ensure_ascii=False)
            self.load_preset_list()
            self.preset_name.set("")
            messagebox.showinfo("成功", f"预设“{preset_name}”已删除")

    def export_script(self):
        if not self.tasks:
            messagebox.showinfo("提示", "任务列表为空，无法导出")
            return
        file_path = filedialog.asksaveasfilename(title="导出脚本", defaultextension=".bat",
            filetypes=[("Windows批处理", "*.bat"), ("Linux/macOS Shell", "*.sh"), ("所有文件", "*.*")])
        if not file_path: return
        try:
            if file_path.lower().endswith(".sh"):
                script_lines = ["#!/bin/bash", "# FFmpeg batch script", ""]
                enc = "utf-8"
            else:
                script_lines = ["@echo off", ":: FFmpeg batch script", "", "chcp 65001 >nul"]
                enc = "utf-8-sig"
            for task in self.tasks:
                script_lines.append(f"echo Processing: {os.path.basename(task.input)}")
                script_lines.append(task.cmd)
                script_lines.append("")
            script_lines.append("echo All tasks completed.")
            with open(file_path, 'w', encoding=enc) as f:
                f.write("\n".join(script_lines))
            messagebox.showinfo("成功", f"脚本已导出到:\n{file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # ---------- 任务编辑 ----------
    def edit_task(self, task, task_index):
        if task.status not in ("等待", "失败"):
            messagebox.showwarning("无法编辑", f"任务状态为“{task.status}”，只能编辑等待或失败的任务。")
            return

        win = tk.Toplevel(self.root)
        win.title(f"编辑任务 - {os.path.basename(task.input)}")
        win.geometry("1000x800")
        win.transient(self.root)
        win.grab_set()

        notebook = ttk.Notebook(win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        page_io = ttk.Frame(notebook)
        notebook.add(page_io, text="输入/输出")
        out_dir_var = tk.StringVar(value=task.settings.get("output_dir", ""))
        suffix_var = tk.StringVar(value=task.settings.get("output_suffix", ""))
        custom_var = tk.StringVar(value=task.settings.get("custom_output_name", ""))
        container_var = tk.StringVar(value=task.settings.get("output_container", "mp4"))
        ttk.Label(page_io, text="输出目录:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(page_io, textvariable=out_dir_var, width=60).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(page_io, text="浏览", command=lambda: out_dir_var.set(self.normalize_path(filedialog.askdirectory() or out_dir_var.get()))).grid(row=0, column=2, padx=5)
        ttk.Label(page_io, text="文件名后缀:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(page_io, textvariable=suffix_var, width=30).grid(row=1, column=1, sticky="w", padx=5)
        ttk.Label(page_io, text="自定义完整名称:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(page_io, textvariable=custom_var, width=60).grid(row=2, column=1, padx=5)
        ttk.Label(page_io, text="输出容器:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        ttk.Combobox(page_io, textvariable=container_var, values=["mp4","mkv","mov","avi","webm"], state="readonly", width=8).grid(row=3, column=1, sticky="w", padx=5)

        page_enc = ttk.Frame(notebook)
        notebook.add(page_enc, text="视频编码")
        enc_frame = VideoEncoderFrame(page_enc)
        enc_frame.pack(fill=tk.X, padx=5, pady=5)
        enc_frame.set_settings(task.settings)

        page_filt = ttk.Frame(notebook)
        notebook.add(page_filt, text="视频滤镜")
        filt_frame = VideoFilterFrame(page_filt)
        filt_frame.pack(fill=tk.X, padx=5, pady=5)
        filt_frame.set_settings(task.settings)

        page_audio = ttk.Frame(notebook)
        notebook.add(page_audio, text="音频")
        audio_frame = AudioFrame(page_audio, enable_checkbox=True)
        audio_frame.pack(fill=tk.X, padx=5, pady=5)
        audio_frame.set_settings(task.settings)

        page_adv = ttk.Frame(notebook)
        notebook.add(page_adv, text="高级")
        adv_frame = ttk.Frame(page_adv)
        adv_frame.pack(fill=tk.X, padx=5, pady=5)
        hw_var = tk.BooleanVar(value=task.settings.get("hwaccel_enabled", False))
        ttk.Checkbutton(adv_frame, text="硬件解码", variable=hw_var).pack(anchor=tk.W)
        # 使用新的解码器选项
        hw_decoder_var = tk.StringVar(value=task.settings.get("hwaccel_decoder", "无"))
        ttk.Combobox(adv_frame, textvariable=hw_decoder_var, values=HARDWARE_DECODER_OPTIONS, state="readonly").pack(anchor=tk.W, padx=20, pady=5)
        ttk.Label(adv_frame, text="自定义参数:").pack(anchor=tk.W, pady=(10,0))
        custom_entry = ttk.Entry(adv_frame, textvariable=self.custom_args, width=70)
        custom_entry.pack(fill=tk.X, pady=5)

        preview_frame = ttk.LabelFrame(win, text="新命令预览", padding="5")
        preview_frame.pack(fill=tk.X, pady=10, padx=5)
        preview_text = scrolledtext.ScrolledText(preview_frame, height=6, wrap=tk.WORD)
        preview_text.pack(fill=tk.BOTH, expand=True)

        def update_preview(*args):
            new_settings = {}
            new_settings.update(enc_frame.get_settings())
            new_settings.update(filt_frame.get_settings())
            new_settings.update(audio_frame.get_settings())
            new_settings["output_dir"] = out_dir_var.get()
            new_settings["output_suffix"] = suffix_var.get()
            new_settings["custom_output_name"] = custom_var.get()
            new_settings["output_container"] = container_var.get()
            new_settings["hwaccel_enabled"] = hw_var.get()
            new_settings["hwaccel_decoder"] = hw_decoder_var.get()
            new_settings["custom_args"] = self.custom_args.get()
            new_settings["only_audio"] = task.settings.get("only_audio", False)  # 任务编辑时不显示，保持原值
            new_settings["audio_format"] = task.settings.get("audio_format", "mp3")
            new_out = self.generate_output_path(task.input, new_settings)
            try:
                new_cmd = self.generate_ffmpeg_command(task.input, new_out, new_settings)
            except ValueError as e:
                new_cmd = f"参数错误: {e}"
            preview_text.delete(1.0, tk.END)
            preview_text.insert(tk.END, new_cmd)

        enc_frame.vcodec.trace_add("write", update_preview)
        filt_frame.frame_rate_type.trace_add("write", update_preview)
        audio_frame.audio_enabled.trace_add("write", update_preview)
        out_dir_var.trace_add("write", update_preview)
        hw_var.trace_add("write", update_preview)
        hw_decoder_var.trace_add("write", update_preview)
        self.custom_args.trace_add("write", update_preview)
        update_preview()

        def save_changes():
            new_settings = {}
            new_settings.update(enc_frame.get_settings())
            new_settings.update(filt_frame.get_settings())
            new_settings.update(audio_frame.get_settings())
            new_settings["output_dir"] = out_dir_var.get()
            new_settings["output_suffix"] = suffix_var.get()
            new_settings["custom_output_name"] = custom_var.get()
            new_settings["output_container"] = container_var.get()
            new_settings["hwaccel_enabled"] = hw_var.get()
            new_settings["hwaccel_decoder"] = hw_decoder_var.get()
            new_settings["custom_args"] = self.custom_args.get()
            new_settings["only_audio"] = task.settings.get("only_audio", False)
            new_settings["audio_format"] = task.settings.get("audio_format", "mp3")
            new_output = self.generate_output_path(task.input, new_settings)
            try:
                new_cmd = self.generate_ffmpeg_command(task.input, new_output, new_settings)
            except ValueError as e:
                messagebox.showerror("参数错误", str(e))
                return
            task.settings = new_settings
            task.output = new_output
            task.cmd = new_cmd
            task.status = "等待"
            self.update_task_list()
            win.destroy()
            self.append_info(f"已编辑任务: {os.path.basename(task.input)}")

        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="保存修改", command=save_changes).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=win.destroy).pack(side=tk.LEFT, padx=5)

    def on_task_double_click(self, event):
        selected = self.task_tree.selection()
        if not selected: return
        idx = int(selected[0])
        self.edit_task(self.tasks[idx], idx)

    # ---------- 界面创建 ----------
    def create_widgets(self):
        main_hpane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_hpane.pack(fill=tk.BOTH, expand=True)

        left_container = ttk.Frame(main_hpane)
        main_hpane.add(left_container, weight=2)

        right_panel = ttk.Frame(main_hpane)
        main_hpane.add(right_panel, weight=1)

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
        transcode_vpane = ttk.PanedWindow(transcode_tab, orient=tk.VERTICAL)
        transcode_vpane.pack(fill=tk.BOTH, expand=True)

        settings_frame = ttk.Frame(transcode_vpane)
        transcode_vpane.add(settings_frame, weight=1)
        tasks_frame = ttk.Frame(transcode_vpane)
        transcode_vpane.add(tasks_frame, weight=2)

        io_frame = ttk.LabelFrame(settings_frame, text="输入 / 输出", padding="5")
        io_frame.pack(fill=tk.X, pady=5)
        ttk.Label(io_frame, text="输入文件:").grid(row=0, column=0, sticky="w")
        ttk.Entry(io_frame, textvariable=self.input_file, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(io_frame, text="浏览", command=self.select_input).grid(row=0, column=2)
        ttk.Button(io_frame, text="添加到任务列表", command=self.add_current_as_task).grid(row=0, column=3, padx=5)
        ttk.Label(io_frame, text="输出目录:").grid(row=1, column=0, sticky="w")
        ttk.Entry(io_frame, textvariable=self.output_dir, width=50).grid(row=1, column=1, padx=5)
        ttk.Button(io_frame, text="浏览", command=self.select_output_dir).grid(row=1, column=2)
        suffix_frame = ttk.Frame(io_frame)
        suffix_frame.grid(row=2, column=0, columnspan=4, sticky="w", pady=2)
        ttk.Label(suffix_frame, text="输出文件名后缀 (如 _new):").pack(side=tk.LEFT)
        ttk.Entry(suffix_frame, textvariable=self.output_suffix, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Label(suffix_frame, text="完整自定义名称 (覆盖后缀):").pack(side=tk.LEFT, padx=(20,0))
        ttk.Entry(suffix_frame, textvariable=self.custom_output_name, width=30).pack(side=tk.LEFT, padx=5)
        ttk.Label(suffix_frame, text="输出容器:").pack(side=tk.LEFT, padx=(20,0))
        container_combo = ttk.Combobox(suffix_frame, textvariable=self.output_container,
                                       values=["mp4", "mkv", "mov", "avi", "webm"], state="readonly", width=6)
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

        enc_adv_frame = ttk.Frame(settings_frame)
        enc_adv_frame.pack(fill=tk.X, pady=5)
        enc_adv_frame.columnconfigure(0, weight=55)
        enc_adv_frame.columnconfigure(1, weight=45)

        self.video_encoder = VideoEncoderFrame(enc_adv_frame)
        self.video_encoder.grid(row=0, column=0, sticky="nsew", padx=(0,5))

        adv_frame = ttk.LabelFrame(enc_adv_frame, text="高级选项 (硬件解码/自定义参数)", padding="5")
        adv_frame.grid(row=0, column=1, sticky="nsew", padx=(5,0))

        hw_frame = ttk.Frame(adv_frame)
        hw_frame.pack(fill=tk.X, pady=2)
        self.hwaccel_check = ttk.Checkbutton(hw_frame, text="启用硬件解码",
                                             variable=self.hwaccel_enabled,
                                             command=self.toggle_hwaccel)
        self.hwaccel_check.pack(side=tk.LEFT)
        ToolTip(self.hwaccel_check,
        "【NVIDIA推荐】\n1.cuda（首选）：自动识别H264/HEVC/AV1，支持全程显存加速。\n2.auto：传统模式，兼容性好但效率略低。\n\n【Intel推荐】\n3.qsv：Intel通用模式，自动适配格式并直通显存。\n\n【手动指定】\n仅在全自动失败时使用。HEVC即H.265，AV1需新显卡支持。",
        offset_x=0, offset_y=0, wraplength=500)
        # 新的解码器下拉列表
        self.hwaccel_decoder_combo = ttk.Combobox(hw_frame, textvariable=self.hwaccel_decoder,
                                                  values=HARDWARE_DECODER_OPTIONS,
                                                  state="readonly", width=22)
        self.hwaccel_decoder_combo.pack(side=tk.LEFT, padx=5)
        self.hwaccel_decoder_combo.bind("<<ComboboxSelected>>", lambda e: self.update_command_preview())

        custom_frame = ttk.Frame(adv_frame)
        custom_frame.pack(fill=tk.X, pady=5)
        ttk.Label(custom_frame, text="自定义FFmpeg参数 (例如: -tune grain -profile:v high):").pack(anchor=tk.W)
        self.custom_entry = ttk.Entry(custom_frame, textvariable=self.custom_args, width=50)
        self.custom_entry.pack(fill=tk.X, pady=2)

        self.video_filter = VideoFilterFrame(settings_frame)
        self.video_filter.pack(fill=tk.X, pady=5)

        audio_row = ttk.Frame(settings_frame)
        audio_row.pack(fill=tk.X, pady=5)
        audio_row.columnconfigure(0, weight=1)
        audio_row.columnconfigure(1, weight=1)
        
        self.audio_frame = AudioFrame(audio_row, enable_checkbox=True)
        self.audio_frame.grid(row=0, column=0, sticky="nsew", padx=(0,5))
        self.audio_frame.only_audio.trace_add("write", lambda *a: self.toggle_only_audio_mode())
        
        btn_container = ttk.Frame(audio_row)
        btn_container.grid(row=0, column=1, sticky="ew", padx=(5,0))

        
        
        # 按钮组（开始转码、预览、刷新）
        btn_container = ttk.Frame(audio_row)
        btn_container.grid(row=0, column=1, sticky="ew", padx=(5,0))
        btn_container.columnconfigure(0, weight=1)
        btn_container.columnconfigure(1, weight=0)
        btn_container.columnconfigure(2, weight=0)
        btn_container.columnconfigure(3, weight=0)
        btn_container.columnconfigure(4, weight=1)
        
        btn_single = tk.Button(btn_container, text="开始转码",
                               command=self.transcode_single,
                               height=2, width=18, relief=tk.RAISED,
                               bg="#4CAF50", fg="white", font=("",12,"bold"))
        btn_single.grid(row=0, column=1, padx=5, pady=10)
        ToolTip(btn_single, "开始当前浏览选择的文件转码", offset_x=0, offset_y=5)
        
        btn_preview = tk.Button(btn_container, text="预览当前命令",
                                command=self.preview_current_file,
                                height=2, width=18, relief=tk.RAISED,
                                bg="#2196F3", fg="white", font=("",12,"bold"))
        btn_preview.grid(row=0, column=2, padx=5, pady=10)
        
        btn_refresh = tk.Button(btn_container, text="刷新命令",
                                command=self.update_command_preview,
                                height=2, width=12, relief=tk.RAISED)
        btn_refresh.grid(row=0, column=3, padx=5, pady=10)

        preview_frame = ttk.LabelFrame(settings_frame, text="当前命令模板", padding="5")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.cmd_preview = scrolledtext.ScrolledText(preview_frame, height=8, wrap=tk.WORD, font=("Microsoft YaHei",9))
        self.cmd_preview.pack(fill=tk.BOTH, expand=True)
        self.cmd_preview.insert(tk.END, "请选择输入文件，或调整参数...")

        task_control_frame = ttk.Frame(tasks_frame)
        task_control_frame.pack(fill=tk.X, pady=5)
        btn_start = tk.Button(task_control_frame, text="开始队列", command=self.start_queue,
                              bg="#4CAF50", fg="black", width=12, relief=tk.RAISED)
        btn_start.pack(side=tk.LEFT, padx=5)

        self.max_parallel = tk.IntVar(value=1)
        label_parallel = ttk.Label(task_control_frame, text="并行任务:")
        label_parallel.pack(side=tk.LEFT, padx=(10,2))
        ToolTip(label_parallel, "同时运行的任务数量，建议不超过3以避免资源过度占用")
        self.parallel_spin = ttk.Spinbox(task_control_frame, from_=1, to=5, width=3, textvariable=self.max_parallel, state="readonly")
        self.parallel_spin.pack(side=tk.LEFT, padx=2)

        label_hw = ttk.Label(task_control_frame, text="硬编并发限制:")
        label_hw.pack(side=tk.LEFT, padx=(10,2))
        ToolTip(label_hw, "同时进行的硬件编码〔NVENC/QSV/AMF等〕任务的最大数量，推荐不超过2")
        self.max_hw_spin = ttk.Spinbox(task_control_frame, from_=1, to=4, width=3, textvariable=self.max_hw_parallel, state="readonly")
        self.max_hw_spin.pack(side=tk.LEFT, padx=2)

        for text, cmd in [("移除选中任务", self.remove_selected_tasks), ("清空全部任务", self.clear_all_tasks),
                          ("清空已完成/失败任务", self.clear_finished_tasks), ("停止队列", self.stop_queue),
                          ("导出为脚本", self.export_script), ("预览选中任务", self.preview_selected_task)]:
            ttk.Button(task_control_frame, text=text, command=cmd).pack(side=tk.LEFT, padx=5)

        columns = ("文件名", "输出路径", "命令 (简洁)", "状态", "错误信息")
        self.task_tree = ttk.Treeview(tasks_frame, columns=columns, show="headings", height=12)
        widths = {"文件名":150, "输出路径":200, "命令 (简洁)":400, "状态":80, "错误信息":200}
        for col in columns:
            self.task_tree.heading(col, text=col)
            self.task_tree.column(col, width=widths.get(col,100))
        self.task_tree.pack(fill=tk.BOTH, expand=True, pady=5)
        self.task_tree.bind("<Double-1>", self.on_task_double_click)

        merge_tab = ttk.Frame(self.notebook)
        self.notebook.add(merge_tab, text="封装/合并/画中画")
        self.create_merge_tab(merge_tab)

        # 绑定事件刷新预览（增加新解码器变量的跟踪）
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
        self.hwaccel_enabled.trace_add("write", lambda *a: self.update_command_preview())
        self.hwaccel_decoder.trace_add("write", lambda *a: self.update_command_preview())
        self.custom_args.trace_add("write", lambda *a: self.update_command_preview())
        # 仅音频模式变量跟踪
        self.audio_frame.only_audio.trace_add("write", lambda *a: self.update_command_preview())
        self.audio_frame.audio_format.trace_add("write", lambda *a: self.update_command_preview())

    def select_input(self):
        path = filedialog.askopenfilename(title="选择视频文件")
        if path:
            path = self.normalize_path(path)
            self.input_file.set(path)
            if not self.output_dir.get():
                self.output_dir.set(os.path.dirname(path))
            self.update_command_preview()

    def select_output_dir(self):
        dirpath = filedialog.askdirectory()
        if dirpath:
            dirpath = self.normalize_path(dirpath)
            self.output_dir.set(dirpath)
            self.update_command_preview()
            
    #---导出预设
    def export_all_presets(self):
        """导出整个预设库到外部 JSON 文件（备份）"""
        FINAL_PRESET_PATH = self.get_preset_path()
        if not os.path.exists(FINAL_PRESET_PATH):
            # 如果预设文件不存在，可以创建一个空预设文件再导出
            if messagebox.askyesno("提示", "当前没有预设文件，是否创建一个空的预设文件并导出？"):
                with open(FINAL_PRESET_PATH, 'w', encoding='utf-8') as f:
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
            shutil.copy2(FINAL_PRESET_PATH, save_path)
            self.append_info(f"✅ 全部预设已备份到: {save_path}")
            messagebox.showinfo("导出成功", f"预设库已导出至:\n{save_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
    
    
    def import_presets(self):
        """从外部 JSON 文件导入预设库（可选择合并或替换）"""
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
    
        # 读取当前预设库
        FINAL_PRESET_PATH = self.get_preset_path()
        current_presets = {}
        if os.path.exists(FINAL_PRESET_PATH):
            try:
                with open(FINAL_PRESET_PATH, 'r', encoding='utf-8') as f:
                    current_presets = json.load(f)
            except:
                pass
    
        # 询问操作方式
        answer = messagebox.askyesno(
            "导入方式",
            f"当前有 {len(current_presets)} 个预设，导入文件包含 {len(imported)} 个预设。\n"
            "是否替换整个预设库？\n"
            "（选“是”将完全替换；选“否”则合并，同名预设将被覆盖）"
        )
    
        if answer:
            # 替换模式
            new_presets = imported
            self.append_info(f"🔄 替换模式：使用导入的 {len(imported)} 个预设替换现有预设库")
        else:
            # 合并模式：更新或添加
            new_presets = current_presets.copy()
            overlapped = [name for name in imported if name in new_presets]
            new_presets.update(imported)
            if overlapped:
                self.append_info(f"✏️ 合并模式：覆盖了 {len(overlapped)} 个同名预设，新增 {len(imported) - len(overlapped)} 个预设")
            else:
                self.append_info(f"➕ 合并模式：新增 {len(imported)} 个预设")
    
        # 保存到预设文件
        try:
            with open(FINAL_PRESET_PATH, 'w', encoding='utf-8') as f:
                json.dump(new_presets, f, indent=4, ensure_ascii=False)
            self.load_preset_list()   # 刷新下拉列表
            self.append_info(f"✅ 预设库已更新，共 {len(new_presets)} 个预设")
            messagebox.showinfo("导入成功", f"预设库已更新，当前共 {len(new_presets)} 个预设")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))



    # -------------------- 封装/合并模块--------------------
    def create_merge_tab(self, parent):
        f1 = ttk.Frame(parent)
        f1.pack(fill=tk.X, pady=5)
        ttk.Label(f1, text="主视频文件:").pack(side=tk.LEFT)
        ttk.Entry(f1, textvariable=self.merge_video).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(f1, text="浏览", command=self.merge_select_video).pack(side=tk.RIGHT, padx=(2,15))

        ttk.Label(parent, text="轨道列表（可单独设置编码参数）").pack(anchor=tk.W, pady=(10,2))
        self.merge_track_frame = ttk.Frame(parent, relief=tk.SUNKEN, borderwidth=1)
        self.merge_track_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="添加外部音轨", command=lambda: self.merge_add_external("audio")).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="添加外部字幕", command=lambda: self.merge_add_external("subtitle")).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="清空轨道", command=self.merge_clear_tracks).pack(side=tk.LEFT, padx=2)
        self.pip_enabled = tk.BooleanVar(value=False)
        pip_chk = ttk.Checkbutton(btn_frame, text="启用画中画", variable=self.pip_enabled)
        pip_chk.pack(side=tk.LEFT, padx=5)
        ToolTip(pip_chk, "开启后可将多个视频叠加（视频必须重新选择编码，不能copy了），关闭时仅使用第一个视频轨道并复制流")
        ttk.Button(btn_frame, text="添加外部视频（画中画）", 
            command=self.merge_add_external_video).pack(side=tk.LEFT, padx=2)

        # ========== 章节处理（改为一行） ==========
        chapter_frame = ttk.LabelFrame(parent, text="章节处理", padding="3")
        chapter_frame.pack(fill=tk.X, pady=5)
        
        # 水平容器
        chapter_row = ttk.Frame(chapter_frame)
        chapter_row.pack(fill=tk.X, padx=5, pady=2)
        
        # 左侧：复制章节复选框
        ttk.Checkbutton(
            chapter_row, text="从源文件复制章节 (map_chapters)", 
            variable=self.copy_chapters
        ).pack(side=tk.LEFT, padx=(0, 15))
        
        # 右侧：导入章节文件（标签+输入框+浏览按钮）
        right_area = ttk.Frame(chapter_row)
        right_area.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(right_area, text="导入外部章节文件 (FFmetadata):").pack(side=tk.LEFT)
        chapter_entry = ttk.Entry(right_area, textvariable=self.chapter_file)
        chapter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(
            right_area, text="浏览...", command=self.browse_chapter_file
        ).pack(side=tk.LEFT)
        
        # ========== 输出容器 + 输出文件（同一行，保持原有） ==========
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
        
        # ========== 选项 ==========
        opt_frame = ttk.Frame(parent)
        opt_frame.pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(
            opt_frame, text="合并成功后删除源文件", variable=self.merge_delete_source
        ).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(
            opt_frame, text="验证输出文件", variable=self.merge_verify
        ).pack(side=tk.LEFT, padx=5)
        
        # ========== 命令预览框（固定较大高度，不自动垂直扩展） ==========
        preview_frame = ttk.LabelFrame(parent, text="即将执行的命令预览", padding="5")
        preview_frame.pack(fill=tk.X, pady=5)          # 仅水平填充，不垂直扩展
        
        content_frame = ttk.Frame(preview_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        self.merge_cmd_preview = scrolledtext.ScrolledText(
            content_frame, height=8, wrap=tk.WORD, font=("Microsoft YaHei", 9)  # 高度从6增加到8
        )
        self.merge_cmd_preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        btn_copy = ttk.Button(
            content_frame, text="复制命令\n到剪贴板", width=10, command=self.merge_copy_command
        )
        btn_copy.pack(side=tk.RIGHT, padx=(5, 0))

        self.merge_btn = tk.Button(parent, text="开始合并", command=self.merge_start, height=1,width=14,
                                  bg="#4CAF50", fg="white", font=("", 12, "bold"))
        self.merge_btn.pack(pady=10)

        self.merge_video.trace_add("write", lambda *a: self.merge_load_video_info())
        self.merge_container.trace_add("write", lambda *a: self.merge_update_command_preview())
        self.merge_output.trace_add("write", lambda *a: self.merge_update_command_preview())
        self.copy_chapters.trace_add("write", lambda *a: self.merge_update_command_preview())
        self.chapter_file.trace_add("write", lambda *a: self.merge_update_command_preview())
        
    def merge_add_external_video(self):
        """添加外部视频作为画中画（需要启用画中画模式）"""
        if not self.pip_enabled.get():
            messagebox.showwarning("提示", "请先勾选「启用画中画」后再添加外部视频作为画中画层。\n注意给视频流选择重新编码，不能使用copy了。\n普通模式下只能有一个主视频轨道。")
            return
        if not self.merge_video.get():
            self.append_info("[封装] 请先设置主视频")
            return
        path = filedialog.askopenfilename(
            title="选择视频文件（画中画）",
            filetypes=[("视频文件", "*.mp4 *.mkv *.avi *.mov *.flv *.webm")]
        )
        if not path:
            return
        info = self.merge_get_media_info(path)
        if not info:
            self.append_info(f"[封装] 无法解析视频文件: {path}")
            return
        # 添加视频流
        video_streams = [s for s in info["streams"] if s.get("codec_type") == "video"]
        if not video_streams:
            self.append_info("[封装] 所选文件不包含视频流")
            return
        s = video_streams[0]
        track = Track(s["index"], "video", s.get("codec_name", "unknown"), path, True)
        # 默认启用缩放并缩放到较小尺寸
        track.enc_settings["scale_enabled"] = True
        track.enc_settings["scale_width"] = "320"
        track.enc_settings["scale_height"] = ""
        # 启用叠加
        track.overlay_enabled = True
        track.overlay_x = "W-w-10"
        track.overlay_y = "H-h-10"
        self.merge_tracks.append(track)
        # 询问是否添加音频
        audio_streams = [s for s in info["streams"] if s.get("codec_type") == "audio"]
        if audio_streams and messagebox.askyesno("添加音频", f"是否同时将文件中的音频流添加为独立音轨？\n{os.path.basename(path)}"):
            for s_audio in audio_streams:
                audio_track = Track(s_audio["index"], "audio", s_audio.get("codec_name", "unknown"), path, True)
                self.merge_tracks.append(audio_track)
        self.merge_update_track_list()
        self.merge_auto_recommend_container()
        self.merge_update_command_preview()
        self.append_info(f"[封装] 已添加画中画视频: {os.path.basename(path)}")

    def browse_chapter_file(self):
        path = filedialog.askopenfilename(title="选择章节文件", filetypes=[("FFmetadata", "*.txt *.chapters")])
        if path:
            self.chapter_file.set(self.normalize_path(path))
            if path:
                self.copy_chapters.set(False)

    def merge_copy_command(self):
        cmd = self.merge_cmd_preview.get(1.0, tk.END).strip()
        if cmd:
            self.root.clipboard_clear()
            self.root.clipboard_append(cmd)
            self.append_info("[封装] 命令已复制到剪贴板")
        else:
            self.append_info("[封装] 无命令可复制")

    def merge_build_cmd_list(self):
        if not self.ffmpeg_cmd:
            self.append_info("❌ 未找到 ffmpeg，无法生成合并命令。")
            return []

        """生成合并/封装命令，支持普通单视频封装和画中画叠加模式"""
        output = self.merge_output.get().strip()
        if not output:
            return []
    
        enabled_tracks = [t for t in self.merge_tracks if t.enabled]
        if not enabled_tracks:
            return []
    
        # 收集所有输入文件（去重）
        input_files = []
        for t in enabled_tracks:
            if t.file_path not in input_files:
                input_files.append(t.file_path)
    
        def normalize_win_path(p):
            if sys.platform != "win32":
                return p
            try:
                import ctypes
                GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
                GetShortPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
                GetShortPathNameW.restype = ctypes.c_uint
                buf_len = GetShortPathNameW(p, None, 0)
                if buf_len == 0:
                    return p
                buf = ctypes.create_unicode_buffer(buf_len)
                GetShortPathNameW(p, buf, buf_len)
                return buf.value
            except Exception:
                return p
    
        input_files_norm = [normalize_win_path(f) for f in input_files]
        output_norm = normalize_win_path(output)
    
        cmd = [self.ffmpeg_cmd, "-y", "-fflags", "+genpts"]
        
        # 为每个输入文件确定是否需要添加截取参数
        # 遍历所有启用的视频轨道，收集每个文件的截取设置（以一个文件一个为准，如有冲突取第一个）
        file_trim = {}  # key: 文件路径, value: (start, end)
        for track in enabled_tracks:
            if track.type == "video":
                # 从 enc_settings 中读取截取设置
                trim_enabled = track.enc_settings.get("trim_enabled", False)
                if trim_enabled:
                    start = track.enc_settings.get("trim_start", "").strip()
                    end = track.enc_settings.get("trim_end", "").strip()
                    if start or end:
                        # 如果同一个文件有多个视频轨道（罕见），后添加的会覆盖前面的，这里简单处理
                        file_trim[track.file_path] = (start, end)
        
        # 添加输入文件，同时为需要截取的文件在 -i 前加上 -ss 和 -to
        for f in input_files_norm:
            if f in file_trim:
                start, end = file_trim[f]
                if start:
                    cmd.extend(["-ss", start])
                if end:
                    cmd.extend(["-to", end])
            cmd.extend(["-i", f])
    
        # 分离轨道
        video_tracks = [t for t in enabled_tracks if t.type == "video"]
        audio_tracks = [t for t in enabled_tracks if t.type == "audio"]
        subtitle_tracks = [t for t in enabled_tracks if t.type == "subtitle"]
    
        if not video_tracks:
            self.append_info("[封装] 没有启用的视频轨道")
            return []

        # ========== 画中画模式 ==========
        if self.pip_enabled.get():
            # 第一个视频为主视频，其余为从视频（叠加）
            main_video = video_tracks[0]
            sub_videos = video_tracks[1:]

            filter_parts = []
            main_idx = input_files_norm.index(normalize_win_path(main_video.file_path))

            # 主视频自身滤镜
            main_filters = self.build_video_filter_chain(main_video.enc_settings)
            if main_filters and main_filters != "null":
                filter_parts.append(f"[{main_idx}:v]{main_filters}[v_main_proc]")
                current_v = "v_main_proc"
            else:
                filter_parts.append(f"[{main_idx}:v]null[v_main_proc]")
                current_v = "v_main_proc"

            # 主视频偏移
            if getattr(main_video, 'pad_enabled', False) and main_video.pad_width and main_video.pad_height:
                pw = main_video.pad_width.strip()
                ph = main_video.pad_height.strip()
                ox = main_video.offset_x.strip() if main_video.offset_x else "0"
                oy = main_video.offset_y.strip() if main_video.offset_y else "0"
                filter_parts.append(f"nullsrc=size={pw}x{ph}[canvas]")
                filter_parts.append(f"[canvas][{current_v}]overlay={ox}:{oy}:shortest=1[v_main_pad]")
                current_v = "v_main_pad"

            # 依次叠加从视频
            for i, sv in enumerate(sub_videos):
                sv_idx = input_files_norm.index(normalize_win_path(sv.file_path))
                sv_filters = self.build_video_filter_chain(sv.enc_settings)
                if sv_filters and sv_filters != "null":
                    filter_parts.append(f"[{sv_idx}:v]{sv_filters}[v_sub_{i}]")
                    sub_src = f"v_sub_{i}"
                else:
                    filter_parts.append(f"[{sv_idx}:v]null[v_sub_{i}]")
                    sub_src = f"v_sub_{i}"
                if getattr(sv, 'overlay_enabled', True):
                    x = sv.overlay_x.strip() if sv.overlay_x else "0"
                    y = sv.overlay_y.strip() if sv.overlay_y else "0"
                    filter_parts.append(f"[{current_v}][{sub_src}]overlay={x}:{y}[v_out_{i}]")
                    current_v = f"v_out_{i}"
                else:
                    filter_parts.append(f"[{current_v}]null[{current_v}]")

            complex_filter = ";".join(filter_parts)
            cmd.extend(["-filter_complex", complex_filter])
            cmd.extend(["-map", f"[{current_v}]"])

            # 视频编码参数（画中画模式必须重新编码）
            v_settings = main_video.enc_settings
            vcodec = v_settings.get("encoder", "libx265")
            rc = v_settings.get("rate_control_type", "crf")
            preset = v_settings.get("preset", "medium")
            cmd.extend(["-c:v", vcodec, "-preset", preset])
            if rc == "crf":
                cmd.extend(["-crf", str(v_settings.get("crf_value", 26))])
            elif rc == "cq":
                cmd.extend(["-cq", str(v_settings.get("cq_value", 35))])
            elif rc == "global_quality":
                cmd.extend(["-global_quality", str(v_settings.get("global_quality", 26))])
            elif rc == "bitrate":
                bitrate = v_settings.get("bitrate_video", "1900k")
                cmd.extend(["-b:v", bitrate])
            if v_settings.get("frame_rate_type") == "custom":
                cmd.extend(["-r", v_settings.get("frame_rate_custom", "30")])
            if v_settings.get("pix_fmt_enabled", True):
                cmd.extend(["-pix_fmt", v_settings.get("pix_fmt", "yuv420p")])

            # ========== 音频处理（画中画模式也支持多音轨）==========
            audio_map_count = 0
            for audio in audio_tracks:
                a_idx = input_files_norm.index(normalize_win_path(audio.file_path))
                enc = audio.enc_settings.get("encoder", "copy")
                cmd.extend(["-map", f"{a_idx}:a:0"])
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

            # ========== 字幕处理（画中画模式也支持）==========
            sub_map_count = 0
            first_sub_default = False
            for sub in subtitle_tracks:
                s_idx = input_files_norm.index(normalize_win_path(sub.file_path))
                enc = sub.enc_settings.get("encoder", "copy")
                container = self.merge_container.get().lower()
                if container == "mp4":
                    if enc == "copy":
                        orig_codec = sub.codec.lower()
                        if orig_codec not in ("mov_text", "mp4s"):
                            enc = "mov_text"
                            self.append_info(f"[封装] 字幕格式 {orig_codec} 不兼容 MP4，自动转换为 mov_text")
                    elif enc not in ("mov_text", "mp4s"):
                        enc = "mov_text"
                        self.append_info(f"[封装] 字幕编码 {enc} 不兼容 MP4，自动转换为 mov_text")
                cmd.extend(["-map", f"{s_idx}:s:0", f"-c:s:{sub_map_count}", enc])
                if not first_sub_default:
                    cmd.extend([f"-disposition:s:{sub_map_count}", "default"])
                    first_sub_default = True
                sub_map_count += 1
    
        else:
            # ========== 普通模式：只有一个视频轨道（已限制添加额外视频）==========
            # 取第一个视频轨道
            video_track = video_tracks[0]
            v_idx = input_files_norm.index(normalize_win_path(video_track.file_path))
            cmd.extend(["-map", f"{v_idx}:v:0"])
    
            # 视频编码：根据用户设置决定是复制还是重新编码
            v_settings = video_track.enc_settings
            vcodec = v_settings.get("encoder", "copy")
            if vcodec == "copy":
                cmd.extend(["-c:v", "copy"])
            else:
                rc = v_settings.get("rate_control_type", "crf")
                preset = v_settings.get("preset", "medium")
                cmd.extend(["-c:v", vcodec, "-preset", preset])
                if rc == "crf":
                    cmd.extend(["-crf", str(v_settings.get("crf_value", 26))])
                elif rc == "cq":
                    cmd.extend(["-cq", str(v_settings.get("cq_value", 35))])
                elif rc == "global_quality":
                    cmd.extend(["-global_quality", str(v_settings.get("global_quality", 26))])
                elif rc == "bitrate":
                    bitrate = v_settings.get("bitrate_video", "1900k")
                    cmd.extend(["-b:v", bitrate])
                if v_settings.get("frame_rate_type") == "custom":
                    cmd.extend(["-r", v_settings.get("frame_rate_custom", "30")])
                if v_settings.get("pix_fmt_enabled", True):
                    cmd.extend(["-pix_fmt", v_settings.get("pix_fmt", "yuv420p")])
    
            # 音频处理（多轨，每个可独立编码）
            audio_map_count = 0
            for audio in audio_tracks:
                a_idx = input_files_norm.index(normalize_win_path(audio.file_path))
                enc = audio.enc_settings.get("encoder", "copy")
                cmd.extend(["-map", f"{a_idx}:a:0"])
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
    
            # 字幕处理
            sub_map_count = 0
            first_sub_default = False
            for sub in subtitle_tracks:
                s_idx = input_files_norm.index(normalize_win_path(sub.file_path))
                enc = sub.enc_settings.get("encoder", "copy")
                container = self.merge_container.get().lower()
                if container == "mp4":
                    if enc == "copy":
                        orig_codec = sub.codec.lower()
                        if orig_codec not in ("mov_text", "mp4s"):
                            enc = "mov_text"
                            self.append_info(f"[封装] 字幕格式 {orig_codec} 不兼容 MP4，自动转换为 mov_text")
                    elif enc not in ("mov_text", "mp4s"):
                        enc = "mov_text"
                        self.append_info(f"[封装] 字幕编码 {enc} 不兼容 MP4，自动转换为 mov_text")
                cmd.extend(["-map", f"{s_idx}:s:0", f"-c:s:{sub_map_count}", enc])
                if not first_sub_default:
                    cmd.extend([f"-disposition:s:{sub_map_count}", "default"])
                    first_sub_default = True
                sub_map_count += 1
    
        # ========== 公共部分：章节处理 ==========
        if self.copy_chapters.get() and input_files_norm:
            cmd.extend(["-map_chapters", "0"])
        chapter_file = self.chapter_file.get().strip()
        if chapter_file and os.path.exists(chapter_file):
            chapter_file_norm = normalize_win_path(chapter_file)
            cmd.insert(1, "-i")
            cmd.insert(2, chapter_file_norm)
            cmd.extend(["-map_chapters", "1"])
    
        # 容器优化
        container = self.merge_container.get().lower()
        if container in ("mp4", "mov"):
            cmd.extend(["-movflags", "+faststart"])
    
        cmd.append(output_norm)
        return cmd

    def build_video_filter_chain(self, settings):
        """根据 VideoFilterFrame 的设置生成滤镜字符串（用于 filter_complex）"""
        filters = []
        # 裁剪
        if settings.get("crop_enabled", False):
            w = settings.get("crop_width", "").strip()
            h = settings.get("crop_height", "").strip()
            left = settings.get("crop_left", "0").strip()
            top = settings.get("crop_top", "0").strip()
            if w and h:
                filters.append(f"crop={w}:{h}:{left}:{top}")
        # 缩放
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
        # 旋转
        rot = settings.get("rotate", "none")
        if rot == "90":
            filters.append("transpose=1")
        elif rot == "180":
            filters.append("transpose=2,transpose=2")
        elif rot == "270":
            filters.append("transpose=2")
        # 翻转
        if settings.get("vflip", False):
            filters.append("vflip")
        if settings.get("hflip", False):
            filters.append("hflip")
        # 反交错
        deint = settings.get("deinterlace_filter", "none")
        if deint != "none":
            filters.append(deint)
        # 注意：像素格式一般不在这里设置，避免影响叠加，由编码参数中的 -pix_fmt 控制
        return ",".join(filters) if filters else "null"

    def merge_update_command_preview(self):
        cmd_list = self.merge_build_cmd_list()
        if not cmd_list:
            self.merge_cmd_preview.delete(1.0, tk.END)
            self.merge_cmd_preview.insert(tk.END, "参数不完整，无法生成命令")
            return
        readable = []
        i = 0
        while i < len(cmd_list):
            arg = cmd_list[i]
            if arg in ('-map', '-c:v', '-c:a', '-c:s', '-filter:v', '-crf:v', '-cq:v', '-global_quality:v', '-b:v', '-r:v', '-b:a', '-ar:a', '-map_chapters'):
                if i+1 < len(cmd_list):
                    readable.append(f"{arg} {cmd_list[i+1]}")
                    i += 2
                    continue
            if ('/' in arg or '\\' in arg) and (' ' in arg or '#' in arg or '&' in arg):
                arg = f'"{arg}"'
            readable.append(arg)
            i += 1
        cmd_str = " ".join(readable)
        self.merge_cmd_preview.delete(1.0, tk.END)
        self.merge_cmd_preview.insert(tk.END, cmd_str)

    def merge_get_media_info(self, path):
        if not self.ffprobe_cmd:
            self.append_info("❌ 未找到 ffprobe，无法获取媒体信息。")
            return None
            
        if not path or not os.path.exists(path):
            return None
    
        cmd = [self.ffprobe_cmd, "-v", "error", "-print_format", "json", "-show_streams", path]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                 creationflags=0x08000000 if sys.platform == "win32" else 0)
            if res.returncode != 0:
                self.root.after(0, lambda: self.append_info(f"[ffprobe] 执行失败，返回码 {res.returncode}，错误输出: {res.stderr}"))
                return None
            data = json.loads(res.stdout)
            if "streams" not in data:
                self.root.after(0, lambda: self.append_info(f"[ffprobe] 输出中无 streams 字段"))
                return None
            return data
        except Exception as e:
            self.root.after(0, lambda: self.append_info(f"[ffprobe] 异常: {e}"))
            return None

    def merge_load_video_info(self):
        path = self.merge_video.get().strip()
        if not path or not os.path.exists(path):
            self.merge_tracks = []
            self.merge_update_track_list()
            self.merge_update_output_preview()
            return

        ext = os.path.splitext(path)[1].lower().lstrip('.')
        self.original_container = ext if ext in ['mp4', 'mkv', 'mov', 'avi', 'webm'] else 'mp4'

        info = self.merge_get_media_info(path)
        if not info:
            self.root.after(0, lambda: self.append_info(f"[封装] 无法解析媒体信息: {path}，可能 ffprobe 失败"))
            self.merge_tracks = []
            self.merge_update_track_list()
            return

        streams = info.get("streams", [])
        if not streams:
            self.root.after(0, lambda: self.append_info(f"[封装] {path} 中没有发现任何流"))
            return

        self.merge_tracks = []
        for s in streams:
            st = s.get("codec_type")
            if st not in ("video","audio","subtitle"):
                continue
            track = Track(s["index"], st, s.get("codec_name", "unknown"), path, True)
            self.merge_tracks.append(track)

        if not self.merge_tracks:
            self.root.after(0, lambda: self.append_info(f"[封装] {path} 中未找到视频/音频/字幕轨道"))

        self.merge_update_track_list()
        self.merge_auto_recommend_container()
        self.merge_update_output_preview()

    def merge_update_track_list(self):
        for w in self.merge_track_frame.winfo_children():
            w.destroy()

        if not self.merge_tracks:
            tk.Label(self.merge_track_frame, text="未加载轨道").pack()
            return

        container = self.merge_track_frame
        main_video = self.merge_video.get().strip()

        # 彩色备份
#         col_bg_headers = ["#e0e0e0", "#cce5ff", "#ffcccc", "#e6f2e6", "#e0e0e0", "#e0e0e0", "#e0e0e0", "#e0e0e0", "#e0e0e0"]
#         ROW_BG_EVEN = ["#f5f5f5", "#e6f3ff", "#ffe6f0", "#f0fcf0", "#ffffff", "#ffffff", "#ffffff", "#ffffff", "#ffffff"]
#         ROW_BG_ODD  = ["#e6f3ff", "#f5f5f5", "#f0fcf0", "#ffe6f0", "#ffffff", "#ffffff", "#ffffff", "#ffffff", "#ffffff"]
        # 表头背景（固定）
        col_bg_headers = ["#cccccc", "#e0e0e0", "#cccccc", "#e0e0e0", "#cccccc", "#e0e0e0", "#cccccc", "#e0e0e0", "#cccccc"]
        # 行交错背景（偶数行 / 奇数行）
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
        self.append_info("[封装] 已清空所有附加轨道")

    def merge_remove_track(self, track_idx):
        if 0 <= track_idx < len(self.merge_tracks):
            removed = self.merge_tracks.pop(track_idx)
            self.append_info(f"[封装] 已删除轨道: {removed.type} - {os.path.basename(removed.file_path)}")
            self.merge_update_track_list()
            self.merge_auto_recommend_container()
            self.merge_update_command_preview()

    def get_video_dimensions(self, file_path):
        if not self.ffprobe_cmd:
            return None, None
        cmd = [self.ffprobe_cmd, "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height", "-of", "csv=p=0", file_path]
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=flags)
            if result.returncode == 0 and ',' in result.stdout.strip():
                w_str, h_str = result.stdout.strip().split(',')
                return int(w_str), int(h_str)
        except Exception:
            pass
        return None, None

    def get_video_dimensions_rotated(self, file_path, enc_settings):
        dim = self.get_video_rotated_dimensions(file_path, enc_settings)
        if dim:
            return dim
        return self.get_video_dimensions(file_path)

    def evaluate_expression(self, expr, main_w, main_h, box_w, box_h):
        if not expr:
            return 0
        expr = expr.replace('W', str(main_w)).replace('H', str(main_h))
        expr = expr.replace('w', str(box_w)).replace('h', str(box_h))
        try:
            return int(eval(expr, {"__builtins__": {}}, {}))
        except Exception:
            self.append_info(f"[预览] 表达式计算失败: {expr}")
            return 0

    def eval_crop_expr(self, expr, iw, ih):
        if not expr:
            return None
        expr = expr.strip()
        try:
            expr = expr.replace('iw', str(iw)).replace('ih', str(ih))
            val = eval(expr, {"__builtins__": {}}, {})
            return int(val)
        except Exception:
            return None
    
    def get_rendered_size(self, track):
        dim = self.get_video_rotated_dimensions(track.file_path, track.enc_settings)
        if not dim:
            return None
        w, h = dim
    
        settings = track.enc_settings
        crop_enabled = settings.get("crop_enabled", False)
        if crop_enabled:
            crop_w_str = settings.get("crop_width", "").strip()
            crop_h_str = settings.get("crop_height", "").strip()
            crop_left_str = settings.get("crop_left", "0").strip()
            crop_top_str = settings.get("crop_top", "0").strip()

            crop_w = self.eval_crop_expr(crop_w_str, w, h) if crop_w_str else None
            crop_h = self.eval_crop_expr(crop_h_str, w, h) if crop_h_str else None
            if crop_w is not None and crop_h is not None and crop_w > 0 and crop_h > 0:
                w, h = crop_w, crop_h
            else:
                self.append_info(f"[预览] 无法解析裁剪尺寸: {crop_w_str}x{crop_h_str}，使用原尺寸 {w}x{h}")
    
        if settings.get("scale_enabled", False):
            method = settings.get("scale_method", "width")
            scale_w_str = settings.get("scale_width", "").strip()
            scale_h_str = settings.get("scale_height", "").strip()
            try:
                if method == "width" and scale_w_str:
                    target_w = int(scale_w_str)
                    target_h = int(round(target_w * h / w))
                    return target_w, target_h
                elif method == "height" and scale_h_str:
                    target_h = int(scale_h_str)
                    target_w = int(round(target_h * w / h))
                    return target_w, target_h
                elif method == "exact" and scale_w_str and scale_h_str:
                    target_w = int(scale_w_str)
                    target_h = int(scale_h_str)
                    return target_w, target_h
            except (ValueError, ZeroDivisionError):
                pass
        return w, h

    def get_video_rotated_dimensions(self, file_path, enc_settings):
        if not self.ffprobe_cmd:
            return None, None
        cmd = [self.ffprobe_cmd, "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height,side_data_list", "-of", "json", file_path]
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=flags)
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            if not streams:
                return None
            w = streams[0].get("width")
            h = streams[0].get("height")
            if w is None or h is None:
                return None
            
            rotation = 0
            side_data = streams[0].get("side_data_list", [])
            for sd in side_data:
                if sd.get("rotation") is not None:
                    rotation = int(sd.get("rotation"))
                    break
            
            rotate_val = enc_settings.get("rotate", "none")
            if rotate_val == "90":
                rotation = 90
            elif rotate_val == "270":
                rotation = 270
            elif rotate_val == "180":
                rotation = 180
            
            if rotation % 180 == 90:
                w, h = h, w
            return w, h
        except Exception:
            return None
    
    def merge_preview_track(self, track_idx):
        track = self.merge_tracks[track_idx]
        if not os.path.exists(track.file_path):
            self.append_info(f"[预览] 文件不存在: {track.file_path}")
            return
            
        if not self.ffplay_cmd:
            self.append_info("❌ 未找到 ffplay，无法预览。请将 ffplay.exe 放在脚本目录或添加到 PATH。")
            return

        if track.type == "video":
            filters = self.build_video_filter_chain(track.enc_settings)
            pip_enabled = self.pip_enabled.get()
            enabled_video_tracks = [t for t in self.merge_tracks if t.enabled and t.type == "video"]
            is_main_video = (enabled_video_tracks and enabled_video_tracks[0] == track)
            if pip_enabled and is_main_video:
                sub_videos = enabled_video_tracks[1:]
                if sub_videos:
                    main_w, main_h = self.get_video_dimensions_rotated(track.file_path, track.enc_settings)
                    if main_w is None:
                        self.append_info("[预览] 无法获取主视频尺寸，使用默认 1280x720")
                        main_w, main_h = 1280, 720
                    
                    drawboxes = []
                    for sub in sub_videos:
                        if not getattr(sub, 'overlay_enabled', True):
                            continue
                        rendered = self.get_rendered_size(sub)
                        if rendered:
                            box_w, box_h = rendered
                        else:
                            box_w, box_h = 200, 150
                            self.append_info(f"[预览] 无法获取从视频渲染尺寸，使用默认 {box_w}x{box_h}")
                        
                        x_expr = sub.overlay_x if hasattr(sub, 'overlay_x') else "0"
                        y_expr = sub.overlay_y if hasattr(sub, 'overlay_y') else "0"
                        x_val = self.evaluate_expression(x_expr, main_w, main_h, box_w, box_h)
                        y_val = self.evaluate_expression(y_expr, main_w, main_h, box_w, box_h)
                        drawbox = f"drawbox=x={x_val}:y={y_val}:w={box_w}:h={box_h}:color=red@0.5:t=2"
                        drawboxes.append(drawbox)
                        self.append_info(f"[预览] 从视频 {os.path.basename(sub.file_path)} 实际渲染尺寸: {box_w}x{box_h}, 位置: ({x_val}, {y_val})")
                    
                    if drawboxes:
                        drawbox_chain = ",".join(drawboxes)
                        if filters and filters != "null":
                            filters = f"{filters},{drawbox_chain}"
                        else:
                            filters = drawbox_chain
    
            if filters and filters != "null":
                full_filters = f"{filters},scale=-2:960"
            else:
                full_filters = "scale=-2:960"
    
            cmd = [self.ffplay_cmd, "-i", track.file_path, "-vf", full_filters,
                   "-volume", "10", "-window_title", f"预览: {os.path.basename(track.file_path)}"]
    
            self.append_info(f"[预览] 执行命令: {' '.join(cmd)}")
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                self.append_info(f"[预览] 启动 ffplay 失败: {e}")
                return
    
            if pip_enabled and is_main_video and sub_videos:
                self.append_info("[预览] 占位框尺寸为从视频实际渲染大小")
    
        elif track.type == "audio":
            cmd = [self.ffplay_cmd, "-i", track.file_path, "-nodisp", "-autoexit", "-volume", "10",
                   "-window_title", f"预览音频: {os.path.basename(track.file_path)}"]
            self.append_info(f"[预览音频] 执行命令: {' '.join(cmd)}")
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                self.append_info(f"[预览音频] 启动 ffplay 失败: {e}")
    
        else:
            self.append_info("[预览] 不支持预览字幕轨")

    def merge_edit_track_settings(self, track_idx):
        track = self.merge_tracks[track_idx]
        if track.type == "video":
            self.merge_edit_video_track(track_idx)
        elif track.type == "audio":
            self.merge_edit_audio_track(track_idx)
        else:
            self.merge_edit_subtitle_track(track_idx)

    def merge_edit_video_track(self, track_idx):
        track = self.merge_tracks[track_idx]
        win = tk.Toplevel(self.root)
        win.title(f"视频轨道设置 - {track.codec}")
        # 先设置窗口大小，再居中
        self.center_window(win, 1000, 300)
        win.transient(self.root)
        win.grab_set()

        notebook = ttk.Notebook(win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        page_enc = ttk.Frame(notebook)
        notebook.add(page_enc, text="编码器与质量")
        enc_frame = VideoEncoderFrame(page_enc)
        enc_frame.pack(fill=tk.X, padx=5, pady=5)
        enc_frame.set_settings(track.enc_settings)

        page_filt = ttk.Frame(notebook)
        notebook.add(page_filt, text="视频滤镜")
        filt_frame = VideoFilterFrame(page_filt)
        filt_frame.pack(fill=tk.X, padx=5, pady=5)
        filt_frame.set_settings(track.enc_settings)

        page_overlay = ttk.Frame(notebook)
        notebook.add(page_overlay, text="叠加/偏移")

        if not self.pip_enabled.get():
            msg = "当前未启用画中画模式。\n如需调整叠加/偏移参数，请先在主界面勾选“启用画中画”。\n注意给视频流选择重新编码，不能使用copy了。"
            label = tk.Label(page_overlay, text=msg, justify="center", fg="gray", 
                             font=("Microsoft YaHei", 14, "bold"))
            label.pack(expand=True, pady=50)
        else:
            enabled_video_tracks = [t for t in self.merge_tracks if t.enabled and t.type == "video"]
            is_main = (enabled_video_tracks and enabled_video_tracks[0] == track)

            if is_main:
                pad_frame = ttk.LabelFrame(page_overlay, text="主视频画布偏移", padding="5")
                pad_frame.pack(fill=tk.X, pady=5)

                pad_enabled_var = tk.BooleanVar(value=getattr(track, 'pad_enabled', False))
                ttk.Checkbutton(pad_frame, text="启用画布偏移", variable=pad_enabled_var).pack(anchor=tk.W)

                w_frame = ttk.Frame(pad_frame)
                w_frame.pack(fill=tk.X, pady=2)
                ttk.Label(w_frame, text="画布宽度:").pack(side=tk.LEFT)
                pad_w_var = tk.StringVar(value=getattr(track, 'pad_width', ''))
                ttk.Entry(w_frame, textvariable=pad_w_var, width=10).pack(side=tk.LEFT, padx=5)

                def fetch_size():
                    w, h = self.get_video_dimensions(track.file_path)
                    if w is not None:
                        pad_w_var.set(str(w))
                        pad_h_var.set(str(h))
                        self.append_info(f"获取主视频尺寸成功: {w}x{h}")
                    else:
                        self.append_info("获取主视频尺寸失败")
                ttk.Button(w_frame, text="获取主视频尺寸", command=fetch_size).pack(side=tk.LEFT, padx=5)

                h_frame = ttk.Frame(pad_frame)
                h_frame.pack(fill=tk.X, pady=2)
                ttk.Label(h_frame, text="画布高度:").pack(side=tk.LEFT)
                pad_h_var = tk.StringVar(value=getattr(track, 'pad_height', ''))
                ttk.Entry(h_frame, textvariable=pad_h_var, width=10).pack(side=tk.LEFT, padx=5)

                ox_frame = ttk.Frame(pad_frame)
                ox_frame.pack(fill=tk.X, pady=2)
                ttk.Label(ox_frame, text="偏移 X:").pack(side=tk.LEFT)
                off_x_var = tk.StringVar(value=getattr(track, 'offset_x', '0'))
                ttk.Entry(ox_frame, textvariable=off_x_var, width=10).pack(side=tk.LEFT, padx=5)

                oy_frame = ttk.Frame(pad_frame)
                oy_frame.pack(fill=tk.X, pady=2)
                ttk.Label(oy_frame, text="偏移 Y:").pack(side=tk.LEFT)
                off_y_var = tk.StringVar(value=getattr(track, 'offset_y', '0'))
                ttk.Entry(oy_frame, textvariable=off_y_var, width=10).pack(side=tk.LEFT, padx=5)

                tip_label = ttk.Label(pad_frame, text="⚠ 预览模式下无法体现主视频偏移效果，请转码后查看 ⚠",
                                      foreground="red", font=("", 12, "bold"))
                tip_label.pack(fill=tk.X, pady=(10, 0))

            else:
                ov_frame = ttk.LabelFrame(page_overlay, text="画中画叠加位置", padding="5")
                ov_frame.pack(fill=tk.X, pady=5)

                ov_enabled_var = tk.BooleanVar(value=getattr(track, 'overlay_enabled', True))
                ttk.Checkbutton(ov_frame, text="启用叠加", variable=ov_enabled_var).pack(anchor=tk.W)

                ttk.Label(ov_frame, text="X 位置 (支持表达式，如 W-w-10):").pack(anchor=tk.W)
                ov_x_var = tk.StringVar(value=getattr(track, 'overlay_x', 'W-w-10'))
                x_entry = ttk.Entry(ov_frame, textvariable=ov_x_var, width=30)
                x_entry.pack(fill=tk.X, pady=2)

                ttk.Label(ov_frame, text="Y 位置 (支持表达式):").pack(anchor=tk.W)
                ov_y_var = tk.StringVar(value=getattr(track, 'overlay_y', 'H-h-10'))
                y_entry = ttk.Entry(ov_frame, textvariable=ov_y_var, width=30)
                y_entry.pack(fill=tk.X, pady=2)

                preset_frame = ttk.LabelFrame(ov_frame, text="快速预设", padding="3")
                preset_frame.pack(fill=tk.X, pady=5)
                positions = {
                    "左上角": ("10", "10"),
                    "右上角": ("W-w-10", "10"),
                    "左下角": ("10", "H-h-10"),
                    "右下角": ("W-w-10", "H-h-10"),
                    "居中": ("(W-w)/2", "(H-h)/2")
                }
                def set_position(x_val, y_val):
                    ov_x_var.set(x_val)
                    ov_y_var.set(y_val)
                    self.merge_update_command_preview()
                for text, (x_val, y_val) in positions.items():
                    btn = ttk.Button(preset_frame, text=text,
                                     command=lambda x=x_val, y=y_val: set_position(x, y))
                    btn.pack(side=tk.LEFT, padx=2, pady=2)

        def save():
            new_settings = {}
            new_settings.update(enc_frame.get_settings())
            new_settings.update(filt_frame.get_settings())
            track.enc_settings = new_settings

            if self.pip_enabled.get():
                if is_main:
                    track.pad_enabled = pad_enabled_var.get()
                    track.pad_width = pad_w_var.get().strip()
                    track.pad_height = pad_h_var.get().strip()
                    track.offset_x = off_x_var.get().strip()
                    track.offset_y = off_y_var.get().strip()
                else:
                    track.overlay_enabled = ov_enabled_var.get()
                    track.overlay_x = ov_x_var.get().strip()
                    track.overlay_y = ov_y_var.get().strip()

            self.merge_update_track_list()
            self.merge_update_command_preview()
            win.destroy()

        ttk.Button(win, text="保存", command=save).pack(pady=10)

    def merge_edit_audio_track(self, track_idx):
        track = self.merge_tracks[track_idx]
        win = tk.Toplevel(self.root)
        win.title(f"音频轨道编码设置 - {track.codec}")
        self.center_window(win, 400, 200)
        win.transient(self.root)
        win.grab_set()
        ttk.Label(win, text="编码器:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        encoder_var = tk.StringVar(value=track.enc_settings.get("encoder", "copy"))
        ttk.Combobox(win, textvariable=encoder_var, values=ALL_AUDIO_ENCODERS, state="readonly", width=15).grid(row=0, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(win, text="比特率:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        bitrate_var = tk.StringVar(value=track.enc_settings.get("bitrate", "128k"))
        ttk.Entry(win, textvariable=bitrate_var, width=10).grid(row=1, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(win, text="采样率:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        samplerate_var = tk.StringVar(value=track.enc_settings.get("samplerate", "44100"))
        ttk.Entry(win, textvariable=samplerate_var, width=10).grid(row=2, column=1, sticky="w", padx=5, pady=5)

        def save():
            track.enc_settings = {"encoder": encoder_var.get(), "bitrate": bitrate_var.get(), "samplerate": samplerate_var.get()}
            self.merge_update_track_list()
            self.merge_update_command_preview()
            win.destroy()
        ttk.Button(win, text="保存", command=save).grid(row=3, column=0, columnspan=2, pady=10)

    def merge_edit_subtitle_track(self, track_idx):
        track = self.merge_tracks[track_idx]
        win = tk.Toplevel(self.root)
        win.title(f"字幕轨道设置 - {track.codec}")
        self.center_window(win, 300, 100)
        win.transient(self.root)
        win.grab_set()
        encoder_var = tk.StringVar(value=track.enc_settings.get("encoder", "copy"))
        ttk.Combobox(win, textvariable=encoder_var, values=["copy", "mov_text", "srt"], state="readonly").pack(pady=5)
        def save():
            track.enc_settings = {"encoder": encoder_var.get()}
            self.merge_update_track_list()
            self.merge_update_command_preview()
            win.destroy()
        ttk.Button(win, text="保存", command=save).pack(pady=5)

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
            self.append_info(f"[封装] 自动推荐容器: {rec.upper()}")

    def merge_add_external(self, ftype, path=None):
        if not self.merge_video.get():
            self.append_info("[封装] 请先设置主视频")
            return
        if not path:
            if ftype == "audio":
                types = [("音频", "*.mp3 *.aac *.m4a *.wav *.flac *.ogg *.opus *.ac3 *.dts *.mka")]
            else:
                types = [("字幕", "*.srt *.ass *.ssa *.vtt *.idx *.sup")]
            path = filedialog.askopenfilename(filetypes=types)
            if not path: return
        info = self.merge_get_media_info(path)
        if not info:
            self.append_info(f"[封装] 无法解析: {path}")
            return
        expected = "audio" if ftype=="audio" else "subtitle"
        def do_add():
            added = 0
            for s in info["streams"]:
                if s.get("codec_type") != expected:
                    continue
                exists = any(t.file_path == path and t.index == s["index"] for t in self.merge_tracks)
                if exists:
                    self.append_info(f"[封装] 跳过重复轨道: {os.path.basename(path)} 流 #{s['index']} ({expected})")
                    continue
                track = Track(s["index"], expected, s.get("codec_name","unknown"), path, True)
                self.merge_tracks.append(track)
                added += 1
            if added:
                self.append_info(f"[封装] 已添加 {added} 条{expected}轨道: {os.path.basename(path)}")
            else:
                self.append_info(f"[封装] 未添加新轨道: {os.path.basename(path)}")
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
        output_path = self.normalize_path(os.path.join(dirname, f"{basename}_merged{ext}"))
        self.merge_output.set(output_path)
        self.merge_update_command_preview()

    def merge_select_video(self):
        path = filedialog.askopenfilename(title="选择视频", filetypes=[("媒体","*.mp4 *.mkv *.avi *.mov *.flv *.ts *.webm")])
        if path:
            self.merge_video.set(self.normalize_path(path))

    def merge_select_output(self):
        path = filedialog.asksaveasfilename(defaultextension="."+self.merge_container.get())
        if path:
            self.merge_output.set(self.normalize_path(path))
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
    
        self.merge_btn.config(state="disabled")
        threading.Thread(target=self.merge_do_merge, daemon=True).start()

    def merge_do_merge(self):
        cmd_list = self.merge_build_cmd_list()
        if not cmd_list:
            self.append_info("[封装] 无法生成命令，请检查设置")
            self.root.after(0, lambda: self.merge_btn.config(state="normal"))
            return

        self.append_info("[封装] 开始合并/转码...")
        output_file = self.merge_output.get().strip()
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
                self.append_detail(line)
            ret = proc.wait()
            if ret == 0:
                self.append_info("[封装] ✅ 处理完成")
                if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                    if self.merge_delete_source.get():
                        deleted_count = 0
                        for sf in source_files:
                            if os.path.exists(sf):
                                try:
                                    os.remove(sf)
                                    self.append_info(f"[封装] 已删除源文件: {os.path.basename(sf)}")
                                    deleted_count += 1
                                except Exception as e:
                                    self.append_info(f"[封装] 删除失败 {os.path.basename(sf)}: {e}")
                        if deleted_count > 0:
                            self.append_info(f"[封装] 共删除 {deleted_count} 个源文件")
                    else:
                        self.append_info("[封装] 未勾选删除源文件，保留原文件")
                else:
                    self.append_info(f"[封装] 警告：输出文件 {output_file} 可能无效（不存在或大小为0），源文件未被删除")
            else:
                self.append_info(f"[封装] 处理失败，返回码 {ret}，源文件未被删除")
        except Exception as e:
            self.append_info(f"[封装] 异常: {e}")
        finally:
            self.root.after(0, lambda: self.merge_btn.config(state="normal"))

    def _check_pip_video_encoders(self):
        if not self.pip_enabled.get():
            return True
    
        enabled_videos = [t for t in self.merge_tracks if t.enabled and t.type == "video"]
        if not enabled_videos:
            return True
    
        copy_tracks = [t for t in enabled_videos if t.enc_settings.get("encoder") == "copy"]
        if copy_tracks:
            self.append_info("❌ 画中画模式错误：所有视频轨道都必须重新编码，不能使用「复制流」。")
            self.append_info("   以下视频轨道当前编码器为「copy」，请编辑它们并改为其他编码器（如 libx264、hevc_nvenc 等）：")
            for t in copy_tracks:
                self.append_info(f"     - {os.path.basename(t.file_path)}")
            self.append_info("   已中止合并操作。")
            return False
        return True

    # -------------------- 拖放处理 --------------------
    def on_files_dropped(self, event):
        files = self.root.tk.splitlist(event.data)
        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 0:
            for file in files:
                if os.path.exists(file):
                    self.add_task(file)
        else:
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
                    if messagebox.askyesno("选择操作", f"将 {os.path.basename(path)} 设为主视频？\n【否】= 仅添加音频轨道"):
                        self.merge_video.set(path)
                    else:
                        self.merge_add_external("audio", path)
            else:
                if not self.merge_video.get():
                    self.append_info(f"[封装] 请先拖入视频文件作为主视频，然后才能添加字幕/音频: {os.path.basename(path)}")
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
            height = min(350 + len(video_files) * 25, 600)
            dialog.geometry(f"600x{height}")
            dialog.transient(root_tk)
            dialog.grab_set()

            has_main = bool(self.merge_video.get().strip())

            info_text = "请选择操作：\n\n• [All] 按钮：仅添加音频（不改变主视频）\n• 点击下方视频按钮：设为主视频，其余添加音频"
            tk.Label(dialog, text=info_text, justify=tk.LEFT).pack(pady=10, padx=10)

            def all_action():
                if not has_main and video_files:
                    main = video_files[0]
                    self.root.after(0, lambda: self.merge_video.set(main))
                    self.root.after(0, lambda: self.append_info(f"[封装] 自动设置主视频: {os.path.basename(main)}"))
                    for f in video_files[1:]:
                        self.root.after(0, lambda f=f: self.merge_add_external("audio", f))
                else:
                    for f in video_files:
                        self.root.after(0, lambda f=f: self.merge_add_external("audio", f))
                for f in other_files:
                    self.root.after(0, lambda f=f: self.merge_handle_dropped_file(f))
                dialog.destroy()
                self.root.after(200, self.merge_update_track_list)
                self.root.after(200, self.merge_auto_recommend_container)
                self.root.after(200, self.merge_update_command_preview)

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
                main = video_files[idx]
                self.root.after(0, lambda: self.merge_video.set(main))
                self.root.after(0, lambda: self.append_info(f"[封装] 设置主视频为: {os.path.basename(main)}"))
                for i, f in enumerate(video_files):
                    if i != idx:
                        self.root.after(0, lambda f=f: self.merge_add_external("audio", f))
                for f in other_files:
                    self.root.after(0, lambda f=f: self.merge_handle_dropped_file(f))
                dialog.destroy()
                self.root.after(200, self.merge_update_track_list)
                self.root.after(200, self.merge_auto_recommend_container)
                self.root.after(200, self.merge_update_command_preview)

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


if __name__ == "__main__":
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()  # 有库，创建支持拖拽的窗口
    else:
        root = tk.Tk()          # 没库，创建普通窗口，保证程序能正常跑起来
    app = FFmpegBatchGUI(root)
    root.mainloop()
