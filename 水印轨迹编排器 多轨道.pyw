import tkinter as tk
from tkinter import ttk, messagebox
import re
import subprocess
import shlex
import os
import ctypes

# 5x5 点位生成
def generate_positions(rows=5, cols=5):
    pos = {}
    for r in range(rows):
        for c in range(cols):
            label = f"({r+1},{c+1})"
            x_expr = f"10+(W-w-20)*{c}/({cols-1})" if cols > 1 else "10"
            y_expr = f"10+(H-h-20)*{r}/({rows-1})" if rows > 1 else "10"
            pos[label] = (x_expr, y_expr)
    return pos

POSITIONS = generate_positions(5, 5)


class SegmentEditor(tk.Toplevel):
    """编辑每段时长和模式的弹窗（高级段控制）"""
    def __init__(self, parent, track_frame):
        super().__init__(parent)
        self.track = track_frame
        self.title(f"编辑段控制 - {track_frame['text']}")
        # 居中
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        width, height = 330, 400
        x = parent_x + (parent_w - width) // 2
        y = parent_y + (parent_h - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.resizable(False, False)

        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # ---- 按钮区（顶部） ----
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(0, 5))
        ttk.Button(btn_frame, text="保存", command=self.save_and_close).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side="left", padx=5)

        # ---- 表头 ----
        head_frame = ttk.Frame(main_frame)
        head_frame.pack(fill="x", pady=2)
        ttk.Label(head_frame, text="段", width=12).pack(side="left")
        ttk.Label(head_frame, text="模式", width=12).pack(side="left")
        ttk.Label(head_frame, text="时长(秒)", width=10).pack(side="left")

        # ---- 滚动列表 ----
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)

        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.rows = []
        self.refresh_entries(scrollable)

    def refresh_entries(self, parent):
        for widget in parent.winfo_children():
            widget.destroy()
        self.rows.clear()

        trajectory = self.track.trajectory
        if len(trajectory) < 2:
            ttk.Label(parent, text="至少需要2个轨迹点").pack()
            return

        n = len(trajectory) - 1
        while len(self.track.segment_modes) < n:
            self.track.segment_modes.append('stay_jump')
        while len(self.track.segment_durations) < n:
            self.track.segment_durations.append(1.0)
        self.track.segment_modes = self.track.segment_modes[:n]
        self.track.segment_durations = self.track.segment_durations[:n]

        for i in range(n):
            frame = ttk.Frame(parent)
            frame.pack(fill="x", pady=2)
            label = ttk.Label(frame, text=f"{trajectory[i]} → {trajectory[i+1]}", width=12)
            label.pack(side="left")
            mode_var = tk.StringVar(value=self.track.segment_modes[i])
            mode_combo = ttk.Combobox(frame, textvariable=mode_var,
                                      values=["stay_jump", "move"], state="readonly", width=10)
            mode_combo.pack(side="left", padx=5)
            dur_var = tk.DoubleVar(value=self.track.segment_durations[i])
            dur_entry = ttk.Entry(frame, textvariable=dur_var, width=8)
            dur_entry.pack(side="left", padx=5)
            dur_var.trace('w', lambda *args: self.track.refresh_advanced_cycle())
            self.rows.append((mode_var, dur_var))

    def save_and_close(self):
        new_modes = []
        new_durations = []
        for mode_var, dur_var in self.rows:
            try:
                dur = dur_var.get()
                if dur <= 0:
                    raise ValueError
                new_modes.append(mode_var.get())
                new_durations.append(dur)
            except:
                messagebox.showerror("错误", "时长必须为正数！")
                return
        self.track.segment_modes = new_modes
        self.track.segment_durations = new_durations
        self.track.refresh_advanced_cycle()
        self.destroy()


class TrackFrame(ttk.LabelFrame):
    def __init__(self, master, index, name):
        super().__init__(master, text=name)
        self.index = index
        self.trajectory = []
        self.original_pre_filters = None
        self.static_x = None
        self.static_y = None
        self.filter_parts = []
        self.segment_modes = []      # 'stay_jump' 或 'move'
        self.segment_durations = []  # 每段时长（秒）

        # 轨迹按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(padx=5, pady=5, anchor="w")
        for i, pos_name in enumerate(POSITIONS.keys()):
            btn = ttk.Button(btn_frame, text=pos_name, width=6,
                             command=lambda n=pos_name: self.add_point(n))
            btn.grid(row=i // 5, column=i % 5, padx=2, pady=2)

        # 操作按钮
        action_frame = ttk.Frame(self)
        action_frame.pack(fill="x", padx=5, pady=2, anchor="w")
        ttk.Button(action_frame, text="撤销上一个", command=self.undo_point).pack(side="left", padx=2)
        ttk.Button(action_frame, text="清空轨迹", command=self.clear_trajectory).pack(side="left", padx=2)

        # 透明度
        self.use_alpha_var = tk.BooleanVar(value=False)
        self.alpha_check = ttk.Checkbutton(action_frame, text="透明度:", variable=self.use_alpha_var,
                                           command=self.toggle_alpha)
        self.alpha_check.pack(side="left", padx=(10, 2))
        self.alpha_var = tk.DoubleVar(value=0.8)
        self.alpha_scale = ttk.Scale(action_frame, from_=0.0, to=1.0, variable=self.alpha_var,
                                     orient="horizontal", length=100, state="disabled")
        self.alpha_scale.pack(side="left", padx=2)
        self.alpha_label = ttk.Label(action_frame, text="0.80")
        self.alpha_label.pack(side="left", padx=2)
        self.alpha_scale.config(command=self.update_alpha_label)

        # 缩放控件
        scale_frame = ttk.Frame(self)
        scale_frame.pack(fill="x", padx=5, pady=2, anchor="w")
        self.use_scale_var = tk.BooleanVar(value=False)
        self.scale_check = ttk.Checkbutton(scale_frame, text="缩放:", variable=self.use_scale_var,
                                           command=self.toggle_scale)
        self.scale_check.pack(side="left", padx=(0, 2))
        ttk.Label(scale_frame, text="W:").pack(side="left")
        self.scale_w_entry = ttk.Entry(scale_frame, width=6, state="disabled")
        self.scale_w_entry.pack(side="left", padx=2)
        self.scale_w_entry.bind("<FocusOut>", self.on_scale_entry_change)
        ttk.Label(scale_frame, text="H:").pack(side="left")
        self.scale_h_entry = ttk.Entry(scale_frame, width=6, state="disabled")
        self.scale_h_entry.pack(side="left", padx=2)
        self.scale_h_entry.bind("<FocusOut>", self.on_scale_entry_change)

        # 时间控制第一行：跳跃模式、高级段控制、每点停留
        time_frame = ttk.Frame(self)
        time_frame.pack(fill="x", padx=5, pady=2, anchor="w")

        self.jump_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(time_frame, text="跳跃模式", variable=self.jump_mode_var,
                        command=self.toggle_jump_mode).pack(side="left")

        ttk.Label(time_frame, text="每点停留(秒):").pack(side="left", padx=(10,2))
        self.dwell_var = tk.DoubleVar(value=1.0)
        self.dwell_entry = ttk.Entry(time_frame, width=6, textvariable=self.dwell_var, state="disabled")
        self.dwell_entry.pack(side="left", padx=2)
        self.dwell_var.trace('w', lambda *args: self.refresh_cycle_if_needed())

        self.advanced_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(time_frame, text="高级段控制", variable=self.advanced_var,
                        command=self.toggle_advanced).pack(side="left", padx=(10,2))
        self.edit_segment_btn = ttk.Button(time_frame, text="编辑段", command=self.edit_segments, state="disabled")
        self.edit_segment_btn.pack(side="left", padx=2)

        # 第二行：周期、延迟、显示时长
        time_row = ttk.Frame(self)
        time_row.pack(fill="x", padx=5, pady=2, anchor="w")

        ttk.Label(time_row, text="轨迹运动周期(秒):").pack(side="left")
        self.cycle_entry = ttk.Entry(time_row, width=6)
        self.cycle_entry.pack(side="left", padx=2)
        self.cycle_entry.insert(0, "")
        self._saved_cycle = ""

        ttk.Label(time_row, text="延迟(秒):").pack(side="left", padx=(10,2))
        self.delay_entry = ttk.Entry(time_row, width=6)
        self.delay_entry.pack(side="left", padx=2)
        self.delay_entry.insert(0, "0")

        ttk.Label(time_row, text="显示时长(秒):").pack(side="left", padx=(10,2))
        self.duration_entry = ttk.Entry(time_row, width=6)
        self.duration_entry.pack(side="left", padx=2)
        self.duration_entry.insert(0, "")

        # 滤镜显示
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill="x", padx=5, pady=2, anchor="w")
        ttk.Label(filter_frame, text="预处理滤镜顺序:", font=("Microsoft YaHei", 9, "bold")).pack(side="left")
        self.filter_display = ttk.Entry(filter_frame, font=("Consolas", 9), state="readonly")
        self.filter_display.pack(side="left", fill="x", expand=True, padx=5)

        # 轨迹显示
        self.traj_text = tk.Text(self, height=2, font=("Microsoft YaHei", 9), wrap="word")
        self.traj_text.pack(fill="x", padx=5, pady=5, anchor="w")
        self.update_traj_display()

        self.toggle_jump_mode()
        self.toggle_advanced()

    # ---------- 模式切换 ----------
    def toggle_jump_mode(self):
        if self.jump_mode_var.get():
            self.dwell_entry.config(state="normal")
            self._saved_cycle = self.cycle_entry.get()
            self.cycle_entry.config(state="readonly")
            self.refresh_cycle()
            if self.advanced_var.get():
                self.advanced_var.set(False)
                self.toggle_advanced()
        else:
            self.dwell_entry.config(state="disabled")
            self.cycle_entry.config(state="normal")
            self.cycle_entry.delete(0, tk.END)
            self.cycle_entry.insert(0, self._saved_cycle)

    def toggle_advanced(self):
        if self.advanced_var.get():
            if len(self.trajectory) < 2:
                messagebox.showinfo("提示", "至少需要2个轨迹点才能使用高级段控制")
                self.advanced_var.set(False)
                return
            self.edit_segment_btn.config(state="normal")
            self._init_segments()
            if self.jump_mode_var.get():
                self.jump_mode_var.set(False)
                self.toggle_jump_mode()
            self.cycle_entry.config(state="readonly")
            self.refresh_advanced_cycle()
        else:
            self.edit_segment_btn.config(state="disabled")
            self.cycle_entry.config(state="normal")
            self.cycle_entry.delete(0, tk.END)
            self.cycle_entry.insert(0, self._saved_cycle if not self.jump_mode_var.get() else self._saved_cycle)

    def _init_segments(self):
        n = len(self.trajectory) - 1
        if len(self.segment_modes) != n:
            self.segment_modes = ['stay_jump'] * n
        if len(self.segment_durations) != n:
            self.segment_durations = [1.0] * n

    def edit_segments(self):
        SegmentEditor(self.winfo_toplevel(), self)

    def refresh_cycle_if_needed(self):
        if self.jump_mode_var.get() and not self.advanced_var.get():
            self.refresh_cycle()

    def refresh_cycle(self):
        if self.jump_mode_var.get():
            dwell = self.dwell_var.get()
            n = len(self.trajectory)
            cycle = n * dwell if n >= 2 else 0.0
            self.cycle_entry.config(state="normal")
            self.cycle_entry.delete(0, tk.END)
            self.cycle_entry.insert(0, f"{cycle:.2f}")
            self.cycle_entry.config(state="readonly")

    def refresh_advanced_cycle(self):
        if self.advanced_var.get():
            total = sum(self.segment_durations)
            self.cycle_entry.config(state="normal")
            self.cycle_entry.delete(0, tk.END)
            self.cycle_entry.insert(0, f"{total:.2f}")
            self.cycle_entry.config(state="readonly")

    # ---------- 轨迹操作 ----------
    def add_point(self, name):
        self.trajectory.append(name)
        self.update_traj_display()
        if self.advanced_var.get():
            self._init_segments()
            self.refresh_advanced_cycle()
        elif self.jump_mode_var.get():
            self.refresh_cycle()

    def undo_point(self):
        if self.trajectory:
            self.trajectory.pop()
            self.update_traj_display()
            n = len(self.trajectory) - 1
            if n < 0:
                n = 0
            self.segment_modes = self.segment_modes[:n]
            self.segment_durations = self.segment_durations[:n]
            if self.advanced_var.get():
                self.refresh_advanced_cycle()
            elif self.jump_mode_var.get():
                self.refresh_cycle()
        else:
            messagebox.showinfo("提示", "当前轨道已经是空的了！")

    def clear_trajectory(self):
        if self.trajectory:
            self.trajectory.clear()
            self.segment_modes.clear()
            self.segment_durations.clear()
            self.update_traj_display()
            if self.advanced_var.get():
                self.refresh_advanced_cycle()
            elif self.jump_mode_var.get():
                self.refresh_cycle()
        else:
            messagebox.showinfo("提示", "当前轨道已经是空的了！")

    def update_traj_display(self):
        self.traj_text.config(state="normal")
        self.traj_text.delete("1.0", tk.END)
        if self.trajectory:
            self.traj_text.insert(tk.END, " -> ".join(self.trajectory))
        else:
            if self.static_x is not None and self.static_y is not None:
                self.traj_text.insert(tk.END, f"(静态位置: x={self.static_x}, y={self.static_y})")
            else:
                self.traj_text.insert(tk.END, "(空)")
        self.traj_text.config(state="disabled")

    # ---------- 其他方法 ----------
    def toggle_alpha(self):
        state = "normal" if self.use_alpha_var.get() else "disabled"
        self.alpha_scale.config(state=state)

    def set_alpha(self, value):
        self.use_alpha_var.set(True)
        self.alpha_var.set(value)
        self.alpha_label.config(text=f"{value:.2f}")
        self.alpha_scale.config(state="normal")

    def update_alpha_label(self, val):
        self.alpha_label.config(text=f"{float(val):.2f}")

    def toggle_scale(self):
        state = "normal" if self.use_scale_var.get() else "disabled"
        self.scale_w_entry.config(state=state)
        self.scale_h_entry.config(state=state)

    def set_scale_values(self, w, h):
        self.scale_w_entry.delete(0, tk.END)
        self.scale_w_entry.insert(0, w)
        self.scale_h_entry.delete(0, tk.END)
        self.scale_h_entry.insert(0, h)

    def set_scale(self, w, h):
        self.use_scale_var.set(True)
        self.scale_w_entry.config(state="normal")
        self.scale_h_entry.config(state="normal")
        self.scale_w_entry.delete(0, tk.END)
        self.scale_w_entry.insert(0, w)
        self.scale_h_entry.delete(0, tk.END)
        self.scale_h_entry.insert(0, h)

    def on_scale_entry_change(self, event=None):
        if not self.use_scale_var.get():
            return
        w_val = self.scale_w_entry.get().strip()
        h_val = self.scale_h_entry.get().strip()
        if not w_val and not h_val:
            return
        if not w_val and h_val:
            self.scale_w_entry.config(state="normal")
            self.scale_w_entry.delete(0, tk.END)
            self.scale_w_entry.insert(0, "-2")
        elif w_val and not h_val:
            self.scale_h_entry.config(state="normal")
            self.scale_h_entry.delete(0, tk.END)
            self.scale_h_entry.insert(0, "-2")

    def set_static_position(self, x, y):
        self.static_x = x
        self.static_y = y

    def set_filter_parts(self, parts):
        self.filter_parts = parts[:]
        display_str = ','.join(parts) if parts else "(无额外滤镜)"
        self.filter_display.config(state="normal")
        self.filter_display.delete(0, tk.END)
        self.filter_display.insert(0, display_str)
        self.filter_display.config(state="readonly")


class MultiTrackWatermarkGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FFmpeg 多轨道水印轨迹编排器 v17.3")

        # ===== 屏幕自适应 =====
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        # 目标尺寸：不超过屏幕的90%，同时保留最小尺寸（800x600）以保证界面可用
        target_width = min(1100, int(screen_width * 0.9))
        target_height = min(850, int(screen_height * 0.9))
        target_width = max(target_width, 800)
        target_height = max(target_height, 600)
        x = (screen_width - target_width) // 2
        y = (screen_height - target_height) // 2
        self.root.geometry(f"{target_width}x{target_height}+{x}+{y}")
        # ===== 自适应结束 =====

        style = ttk.Style()
        style.configure(".", font=("Microsoft YaHei", 9))

        paned = ttk.PanedWindow(root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        left_panel = ttk.Frame(paned, width=400)
        paned.add(left_panel, weight=1)

        ttk.Label(left_panel, text="FFmpeg 水印编排器", font=("Microsoft YaHei", 16, "bold")).pack(pady=10, anchor="w", padx=5)

        ttk.Label(left_panel, text="粘贴原始 FFmpeg 命令:").pack(anchor="w", padx=5)
        self.input_cmd = tk.Text(left_panel, height=5, font=("Microsoft YaHei", 9), wrap="word")
        self.input_cmd.pack(fill="x", pady=5, padx=5)

        ttk.Button(left_panel, text="智能解析命令并生成轨道", command=self.parse_and_generate_tracks).pack(fill="x", pady=5, padx=5)

        global_time_frame = ttk.Frame(left_panel)
        global_time_frame.pack(fill="x", pady=10, padx=5)
        ttk.Label(global_time_frame, text="全局循环时长(秒):").pack(side="left")
        self.global_duration_entry = ttk.Entry(global_time_frame, width=6)
        self.global_duration_entry.pack(side="left", padx=5)
        self.global_duration_entry.insert(0, "16")
        ttk.Button(global_time_frame, text="获取主视频时长", command=self.get_main_duration).pack(side="left", padx=5)

        self.loop_var = tk.BooleanVar(value=True)
        self.loop_check = ttk.Checkbutton(global_time_frame, text="轨迹循环", variable=self.loop_var, command=self.toggle_loop_mode)
        self.loop_check.pack(side="left", padx=5)

        self.loop_mode_var = tk.StringVar(value="跳跃循环")
        self.loop_mode_combo = ttk.Combobox(global_time_frame, textvariable=self.loop_mode_var,
                                            values=["跳跃循环", "往复循环"], state="readonly", width=10)
        self.loop_mode_combo.pack(side="left", padx=5)

        self.end_behavior_var = tk.StringVar(value="停留在结束点")
        self.end_behavior_combo = ttk.Combobox(global_time_frame, textvariable=self.end_behavior_var,
                                                values=["停留在结束点", "立即消失"],
                                                state="readonly", width=12)
        self.end_behavior_combo.pack(side="left", padx=5)
        self.toggle_loop_mode()

        ttk.Button(left_panel, text="生成多轨道叠加命令", command=self.generate_command).pack(fill="x", pady=5, padx=5)

        ttk.Label(left_panel, text="生成的命令:", font=("Microsoft YaHei", 10, "bold")).pack(anchor="w", pady=(10,0), padx=5)
        self.cmd_text = tk.Text(left_panel, height=8, font=("Microsoft YaHei", 9), wrap="word")
        self.cmd_text.pack(fill="both", expand=True, pady=5, padx=5)
        ttk.Button(left_panel, text="一键复制到剪贴板", command=self.copy_to_clipboard).pack(fill="x", pady=5, padx=5)

        right_panel = ttk.Frame(paned)
        paned.add(right_panel, weight=2)

        ttk.Label(right_panel, text="自动识别的子视频轨道:", font=("Microsoft YaHei", 10, "bold")).pack(anchor="w", padx=5)

        canvas = tk.Canvas(right_panel)
        scrollbar = ttk.Scrollbar(right_panel, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self.canvas_window = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.bind("<Configure>", self._on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.tracks = []

    def toggle_loop_mode(self):
        if self.loop_var.get():
            self.loop_mode_combo.config(state="readonly")
            self.end_behavior_combo.config(state="disabled")
        else:
            self.loop_mode_combo.config(state="disabled")
            self.end_behavior_combo.config(state="readonly")

    def _on_canvas_configure(self, event):
        canvas = event.widget
        canvas.itemconfig(self.canvas_window, width=canvas.winfo_width())

    def get_short_path(self, path):
        try:
            buffer = ctypes.create_unicode_buffer(260)
            length = ctypes.windll.kernel32.GetShortPathNameW(path, buffer, 260)
            if length > 0:
                return buffer.value
        except Exception:
            pass
        return path

    def get_main_duration(self):
        original_cmd = self.input_cmd.get("1.0", tk.END).strip()
        if not original_cmd:
            messagebox.showwarning("提示", "请先粘贴命令！")
            return
        try:
            args = shlex.split(original_cmd, posix=False)
        except:
            messagebox.showerror("解析错误", "命令格式有误，无法拆分")
            return

        ffmpeg_exe = None
        if args and (args[0].endswith('.exe') or args[0].lower() in ('ffmpeg', 'ffmpeg.exe')):
            ffmpeg_exe = args[0]

        main_video_path = None
        for i, arg in enumerate(args):
            if arg == '-i' and i+1 < len(args):
                raw_path = args[i+1].strip('"').strip("'")
                main_video_path = os.path.normpath(raw_path)
                break
        if not main_video_path:
            messagebox.showerror("错误", "未找到输入文件")
            return

        ffprobe_cmd = "ffprobe"
        if ffmpeg_exe and os.path.dirname(ffmpeg_exe):
            possible_path = os.path.join(os.path.dirname(ffmpeg_exe), "ffprobe.exe")
            if os.path.exists(possible_path):
                ffprobe_cmd = possible_path

        try:
            cmd = [ffprobe_cmd, "-v", "error", "-show_entries", "format=duration",
                   "-of", "default=noprint_wrappers=1:nokey=1", main_video_path]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore',
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode != 0:
                err_msg = (f"执行 {ffprobe_cmd} 失败，返回码：{result.returncode}\n"
                           f"stdout: {repr(result.stdout)}\n"
                           f"stderr: {repr(result.stderr)}\n"
                           f"传入的路径: {repr(main_video_path)}")
                messagebox.showerror("ffprobe 错误", err_msg)
                return
            duration_str = result.stdout.strip()
            if not duration_str:
                messagebox.showerror("错误",
                    f"ffprobe 未返回时长信息。\nstderr: {repr(result.stderr)}\n路径: {repr(main_video_path)}")
                return
            duration = float(duration_str)
            self.global_duration_entry.delete(0, tk.END)
            self.global_duration_entry.insert(0, f"{duration:.2f}")
            messagebox.showinfo("成功", f"已自动获取主视频时长：{duration:.2f} 秒")
        except FileNotFoundError:
            messagebox.showerror("找不到 ffprobe", f"无法找到 {ffprobe_cmd}，请检查路径或添加至 PATH。")
        except Exception as e:
            messagebox.showerror("获取失败", f"发生异常：{str(e)}")

    def parse_and_generate_tracks(self):
        for t in self.tracks:
            t.destroy()
        self.tracks.clear()

        original_cmd = self.input_cmd.get("1.0", tk.END).strip()
        if not original_cmd:
            messagebox.showwarning("提示", "请先粘贴命令！")
            return

        try:
            args = shlex.split(original_cmd, posix=False)
        except ValueError as e:
            messagebox.showerror("解析错误", f"命令格式有误，无法拆分：{e}")
            return

        inputs = []
        filter_complex = None
        i = 0
        while i < len(args):
            if args[i] == '-i':
                if i+1 < len(args):
                    inputs.append(args[i+1])
                    i += 2
                else:
                    i += 1
            elif args[i] == '-filter_complex':
                if i+1 < len(args):
                    filter_complex = args[i+1]
                    i += 2
                else:
                    i += 1
            else:
                i += 1

        if len(inputs) < 2:
            messagebox.showerror("错误", "命令中至少需要包含 2 个 -i 输入文件")
            return

        raw_filters_map = {}
        if filter_complex:
            pattern = r'\[(\d+):v\]([^\[]+?)(?=\s*\[|$)'
            matches = re.findall(pattern, filter_complex)
            for idx, filters in matches:
                raw_filters_map[int(idx)] = filters.strip(',')

        alpha_pattern = re.compile(r'\[v_sub_(\d+)\]colorchannelmixer=aa=([0-9.]+)')
        alpha_map = {}
        if filter_complex:
            for m in alpha_pattern.finditer(filter_complex):
                alpha_map[int(m.group(1))] = float(m.group(2))

        static_coords = []
        if filter_complex:
            pattern1 = r"overlay=x='([^']*)':y='([^']*)'"
            matches1 = re.findall(pattern1, filter_complex)
            if matches1:
                static_coords = [(x.strip(), y.strip()) for x, y in matches1]
            else:
                pattern2 = r"overlay=x=([^:]*):y=([^:]*)(?=[:]|$)"
                matches2 = re.findall(pattern2, filter_complex)
                if matches2:
                    static_coords = [(x.strip(), y.strip()) for x, y in matches2]
                else:
                    overlay_pattern = re.compile(r'overlay=([^:]+):([^:]+)')
                    for m in overlay_pattern.finditer(filter_complex):
                        x = m.group(1).strip()
                        y = m.group(2).strip()
                        if x.lower() in ('enable', 'shortest') or y.lower() in ('enable', 'shortest'):
                            continue
                        static_coords.append((x, y))

        for idx, file_path in enumerate(inputs[1:], start=1):
            file_name = file_path.split("/")[-1].split("\\")[-1]
            track = TrackFrame(self.scrollable_frame, idx, file_name)
            track.pack(fill="x", padx=5, pady=5)

            raw_filters = raw_filters_map.get(idx, "")
            filter_parts = []
            scale_w = scale_h = None

            if raw_filters:
                parts = [p.strip() for p in raw_filters.split(',') if p.strip()]
                for part in parts:
                    if part.startswith('format=') or part.startswith('colorchannelmixer='):
                        continue
                    if part.startswith('scale='):
                        m = re.match(r'^scale=([^:]+):([^:,]+)', part)
                        if m:
                            scale_w, scale_h = m.group(1), m.group(2)
                    filter_parts.append(part)

            track.set_filter_parts(filter_parts)

            if scale_w is not None and scale_h is not None:
                track.set_scale(scale_w, scale_h)

            if (idx-1) in alpha_map:
                track.set_alpha(alpha_map[idx-1])

            if idx-1 < len(static_coords):
                x, y = static_coords[idx-1]
                track.set_static_position(x, y)

            self.tracks.append(track)

        messagebox.showinfo("解析成功", f"成功识别到 {len(inputs)-1} 个子视频轨道！")

    # ---------- 核心：构建单轴表达式 ----------
    def build_axis_expr(self, trajectory, global_duration, axis_idx,
                        loop=True, mode="跳跃循环",
                        track_cycle=None, track_delay=0.0,
                        jump_mode=False, dwell=1.0,
                        advanced=False, seg_modes=None, seg_durations=None):
        N = len(trajectory)
        if N == 0:
            return "0"
        if N == 1:
            return POSITIONS[trajectory[0]][axis_idx]

        delay = float(track_delay) if track_delay else 0.0

        # ---- 高级段控制 ----
        if advanced and seg_modes and seg_durations and len(seg_modes) == N-1:
            # 构建段索引序列（跳跃循环 或 往复循环）
            if mode == "跳跃循环":
                seq = list(range(N-1))  # 0,1,2,...,N-2
            else:  # 往复循环
                # 正向段: 0,1,...,N-2
                # 反向段: N-2, N-3, ..., 0
                seq = list(range(N-1)) + list(range(N-2, -1, -1))

            # 构建 segment_info: (start_node, end_node, start_time, dur, mode)
            segment_info = []
            current_time = 0.0
            # 正向部分：i < N-1 为正向
            for i, seg_idx in enumerate(seq):
                dur = seg_durations[seg_idx]
                seg_mode = seg_modes[seg_idx]
                if i < N-1:  # 正向
                    start_node = seg_idx
                    end_node = seg_idx + 1
                else:  # 反向
                    start_node = seg_idx + 1
                    end_node = seg_idx
                segment_info.append((start_node, end_node, current_time, dur, seg_mode))
                current_time += dur
            period = current_time

            # 时间变量
            if not loop:
                t_shift = f"if(lt(t,{delay}),{delay},if(lt(t,{delay+period}),t,{delay+period}))"
                mod_var = f"({t_shift}-{delay})"
            else:
                t_shift = f"if(lt(t,{delay}),{delay},t)"
                mod_var = f"mod({t_shift}-{delay},{period})"

            # 从后向前构建条件表达式
            # 最后一段的终点坐标作为默认值
            last_start, last_end, last_time, last_dur, last_mode = segment_info[-1]
            default_node = last_end
            expr = POSITIONS[trajectory[default_node]][axis_idx]

            for start_node, end_node, start_time, dur, seg_mode in reversed(segment_info):
                start_pos = POSITIONS[trajectory[start_node]][axis_idx]
                end_pos = POSITIONS[trajectory[end_node]][axis_idx]
                end_time = start_time + dur
                if seg_mode == 'move':
                    segment_expr = f"{start_pos}+(({mod_var}-{start_time})/{dur})*({end_pos}-({start_pos}))"
                else:  # 'stay_jump'
                    segment_expr = start_pos
                expr = f"if(lt({mod_var},{end_time}),{segment_expr},{expr})"

            if delay > 0:
                start_pos = POSITIONS[trajectory[0]][axis_idx]
                expr = f"if(lt(t,{delay}),{start_pos},{expr})"
            return expr

        # ---- 简单跳跃模式 ----
        if jump_mode:
            if mode == "跳跃循环":
                seq = list(range(N))
            else:
                seq = list(range(N)) + list(range(N-2, -1, -1))
            dwell_times = [dwell] * len(seq)
            segments = []
            current_time = 0.0
            for node_idx in seq:
                coord = POSITIONS[trajectory[node_idx]][axis_idx]
                segments.append((coord, current_time))
                current_time += dwell
            period = current_time
            expr = segments[-1][0]
            for coord, start_time in reversed(segments[:-1]):
                expr = f"if(lt(mod(if(lt(t,{delay}),{delay},t)-{delay},{period}),{start_time + dwell}),{coord},{expr})"
            if delay > 0:
                start_pos = POSITIONS[trajectory[0]][axis_idx]
                expr = f"if(lt(t,{delay}),{start_pos},{expr})"
            return expr

        # ---- 连续移动模式 ----
        if track_cycle and track_cycle.strip():
            try:
                effective_duration = float(track_cycle.strip())
            except ValueError:
                effective_duration = global_duration
        else:
            effective_duration = global_duration

        num_segments = N - 1
        seg_dur = effective_duration / num_segments

        if not loop:
            t_shift = f"if(lt(t,{delay}),{delay},if(lt(t,{delay+effective_duration}),t,{delay+effective_duration}))"
            t_var = f"({t_shift}-{delay})"
        else:
            if mode == "往复循环":
                t_shift = f"if(lt(t,{delay}),{delay},t)"
                t_phase = f"mod({t_shift}-{delay},{2*effective_duration})"
                t_var = f"if(lt({t_phase},{effective_duration}), {t_phase}, {2*effective_duration} - {t_phase})"
            else:
                t_shift = f"if(lt(t,{delay}),{delay},t)"
                t_var = f"mod({t_shift}-{delay},{effective_duration})"

        expr = POSITIONS[trajectory[-1]][axis_idx]
        for i in range(num_segments - 1, -1, -1):
            start_val = POSITIONS[trajectory[i]][axis_idx]
            end_val = POSITIONS[trajectory[i+1]][axis_idx]
            seg_start_time = i * seg_dur
            seg_end_time = (i + 1) * seg_dur
            interp = f"{start_val}+(({t_var}-{seg_start_time})/{seg_dur})*({end_val}-({start_val}))"
            expr = f"if(lt({t_var},{seg_end_time}),{interp},{expr})"

        if delay > 0:
            start_pos = POSITIONS[trajectory[0]][axis_idx]
            expr = f"if(lt(t,{delay}),{start_pos},{expr})"

        return expr

    # ---------- 生成最终命令 ----------
    def generate_command(self):
        original_cmd = self.input_cmd.get("1.0", tk.END).strip()
        if not original_cmd:
            messagebox.showwarning("提示", "请先粘贴命令！")
            return

        valid_tracks = [t for t in self.tracks if len(t.trajectory) >= 1 or (t.static_x is not None and t.static_y is not None)]
        if not valid_tracks:
            messagebox.showwarning("提示", "至少需要一个包含轨迹或静态位置的轨道！")
            return

        try:
            global_duration = float(self.global_duration_entry.get())
        except ValueError:
            messagebox.showerror("错误", "全局循环时长必须是数字！")
            return

        try:
            args = shlex.split(original_cmd, posix=False)
        except:
            args = original_cmd.split()

        ffmpeg_exe = None
        if args and (args[0].endswith('.exe') or args[0].lower() in ('ffmpeg', 'ffmpeg.exe')):
            ffmpeg_exe = args[0]
            args = args[1:]
        else:
            ffmpeg_exe = 'ffmpeg'

        global_opt_set = {'-y', '-fflags', '-threads', '-loglevel', '-stats', '-progress'}
        need_arg = {'-fflags':1, '-threads':1, '-loglevel':1, '-progress':1}
        input_entries = []
        pending_opts = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == '-i':
                if i+1 < len(args):
                    path = args[i+1].strip('"')
                    short_path = self.get_short_path(path)
                    input_entries.append((pending_opts[:], short_path))
                    pending_opts = []
                    i += 2
                else:
                    i += 1
            elif arg in global_opt_set:
                if need_arg.get(arg, 0) and i+1 < len(args):
                    i += 2
                else:
                    i += 1
            else:
                if arg.startswith('-') and i+1 < len(args) and not args[i+1].startswith('-'):
                    pending_opts.append(arg)
                    pending_opts.append(args[i+1])
                    i += 2
                else:
                    pending_opts.append(arg)
                    i += 1

        if not input_entries:
            messagebox.showerror("错误", "未找到输入文件")
            return

        loop = self.loop_var.get()
        mode = self.loop_mode_var.get() if loop else "跳跃循环"
        end_behavior = self.end_behavior_var.get() if not loop else "停留在结束点"

        filter_chain = []
        filter_chain.append("[0:v]format=yuv420p[v_main]")
        current_base = "[v_main]"
        output_counter = 0

        for track in self.tracks:
            has_trajectory = len(track.trajectory) >= 1
            has_static = (track.static_x is not None and track.static_y is not None)
            if not has_trajectory and not has_static:
                continue

            delay = track.delay_entry.get().strip()
            if delay and not delay.replace('.', '').isdigit():
                messagebox.showerror("错误", f"轨道 {track['text']} 的延迟必须是数字！")
                return
            delay_val = float(delay) if delay else 0.0

            display = track.duration_entry.get().strip()
            display_val = None
            if display:
                try:
                    display_val = float(display)
                    if display_val <= 0:
                        messagebox.showerror("错误", f"轨道 {track['text']} 的显示时长必须大于0！")
                        return
                except ValueError:
                    messagebox.showerror("错误", f"轨道 {track['text']} 的显示时长必须是数字！")
                    return

            advanced = track.advanced_var.get()
            jump_mode = track.jump_mode_var.get()
            dwell = track.dwell_var.get() if jump_mode else 0.0
            cycle = track.cycle_entry.get().strip() if not advanced and not jump_mode else None

            idx = track.index

            if has_trajectory:
                if advanced:
                    x_expr = self.build_axis_expr(track.trajectory, global_duration, 0, loop, mode, None, delay_val,
                                                  False, 0, True, track.segment_modes, track.segment_durations)
                    y_expr = self.build_axis_expr(track.trajectory, global_duration, 1, loop, mode, None, delay_val,
                                                  False, 0, True, track.segment_modes, track.segment_durations)
                elif jump_mode:
                    x_expr = self.build_axis_expr(track.trajectory, global_duration, 0, loop, mode, None, delay_val,
                                                  True, dwell, False)
                    y_expr = self.build_axis_expr(track.trajectory, global_duration, 1, loop, mode, None, delay_val,
                                                  True, dwell, False)
                else:
                    cycle_val = track.cycle_entry.get().strip()
                    x_expr = self.build_axis_expr(track.trajectory, global_duration, 0, loop, mode, cycle_val, delay_val)
                    y_expr = self.build_axis_expr(track.trajectory, global_duration, 1, loop, mode, cycle_val, delay_val)
            else:
                x_expr = track.static_x
                y_expr = track.static_y

            sub_stream = f"[{idx}:v]"
            sub_temp_label = f"v_sub_{idx}"
            out_stream = f"[v_out_{output_counter}]"

            filter_parts = track.filter_parts[:]
            if track.use_scale_var.get():
                w = track.scale_w_entry.get().strip()
                h = track.scale_h_entry.get().strip()
                if not w or not h:
                    messagebox.showerror("错误", f"轨道 {track['text']} 启用了缩放但未填写宽或高！")
                    return
                new_scale = f"scale={w}:{h}"
                replaced = False
                for i, part in enumerate(filter_parts):
                    if part.startswith('scale='):
                        filter_parts[i] = new_scale
                        replaced = True
                        break
                if not replaced:
                    filter_parts.append(new_scale)
            else:
                filter_parts = [part for part in filter_parts if not part.startswith('scale=')]

            filter_str = ','.join(filter_parts) if filter_parts else "null"
            sub_pipeline = f"{sub_stream}{filter_str}[{sub_temp_label}]"

            format_pipeline = f"[{sub_temp_label}]format=rgba[{sub_temp_label}_rgba]"

            # 总周期（用于立即消失）
            total_period = 0.0
            if advanced:
                total_period = sum(track.segment_durations)
            elif jump_mode:
                total_period = len(track.trajectory) * dwell
            else:
                try:
                    total_period = float(track.cycle_entry.get()) if track.cycle_entry.get().strip() else global_duration
                except:
                    total_period = global_duration

            if delay_val > 0:
                enable_parts = [f"gte(t,{delay_val})"]
            else:
                enable_parts = ["1"]

            if not loop and end_behavior == "立即消失" and has_trajectory:
                end_time = delay_val + total_period
                enable_parts = [f"between(t,{delay_val},{end_time})"]
            elif display_val is not None:
                life_end = delay_val + display_val
                if loop or end_behavior == "停留在结束点" or not has_trajectory:
                    enable_parts = [f"between(t,{delay_val},{life_end})"]

            enable_expr = " && ".join(enable_parts) if len(enable_parts) > 1 else enable_parts[0]
            if enable_expr == "1" and loop and display_val is None and delay_val == 0:
                enable_expr = "1"

            if track.use_alpha_var.get():
                alpha = f"{track.alpha_var.get():.2f}"
                alpha_label = f"v_alpha_{idx}"
                alpha_pipeline = f"[{sub_temp_label}_rgba]colorchannelmixer=aa={alpha}[{alpha_label}]"
                overlay = f"{current_base}[{alpha_label}]overlay=x='{x_expr}':y='{y_expr}':enable='{enable_expr}':shortest=1{out_stream}"
                filter_chain.append(f"{sub_pipeline};{format_pipeline};{alpha_pipeline};{overlay}")
            else:
                overlay = f"{current_base}[{sub_temp_label}_rgba]overlay=x='{x_expr}':y='{y_expr}':enable='{enable_expr}':shortest=1{out_stream}"
                filter_chain.append(f"{sub_pipeline};{format_pipeline};{overlay}")

            current_base = out_stream
            output_counter += 1

        if output_counter == 0:
            messagebox.showwarning("提示", "没有有效轨迹")
            return

        final_filter = ";".join(filter_chain)
        final_output_label = f"[v_out_{output_counter-1}]"
        map_cmd = f'-map {final_output_label} -map 0:a? -c:v libx264 -c:a copy -shortest'

        first_path = input_entries[0][1]
        base_dir = os.path.dirname(first_path)
        base_name = os.path.splitext(os.path.basename(first_path))[0]
        output_file = os.path.join(base_dir, f"{base_name}_watermarked.mp4")
        output_file = output_file.replace('\\', '/')
        output_file = self.get_short_path(output_file)

        cmd_parts = []
        cmd_parts.append(ffmpeg_exe.replace('\\', '/'))
        cmd_parts.extend(['-y', '-fflags', '+genpts'])

        for opts, path in input_entries:
            if opts:
                cmd_parts.extend(opts)
            cmd_parts.extend(['-i', f'"{path}"'])

        cmd_parts.extend(['-filter_complex', f'"{final_filter}"'])

        map_parts = shlex.split(map_cmd, posix=False)
        cmd_parts.extend(map_parts)

        cmd_parts.append(f'"{output_file}"')

        final_cmd = ' '.join(cmd_parts)

        self.cmd_text.delete("1.0", tk.END)
        self.cmd_text.insert(tk.END, final_cmd)

    def copy_to_clipboard(self):
        cmd = self.cmd_text.get("1.0", tk.END).strip()
        if cmd:
            self.root.clipboard_clear()
            self.root.clipboard_append(cmd)
            messagebox.showinfo("成功", "命令已复制到剪贴板！")


if __name__ == "__main__":
    root = tk.Tk()
    app = MultiTrackWatermarkGUI(root)
    root.mainloop()
