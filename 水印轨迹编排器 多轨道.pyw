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


class TrackFrame(ttk.LabelFrame):
    def __init__(self, master, index, name):
        super().__init__(master, text=name)
        self.index = index
        self.trajectory = []
        self.original_pre_filters = None
        self.static_x = None
        self.static_y = None

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

        # 独立时间控制（周期、延迟、显示时长）
        time_frame = ttk.Frame(self)
        time_frame.pack(fill="x", padx=5, pady=2, anchor="w")
        ttk.Label(time_frame, text="轨迹运动周期(秒):").pack(side="left")
        self.cycle_entry = ttk.Entry(time_frame, width=6)
        self.cycle_entry.pack(side="left", padx=2)
        self.cycle_entry.insert(0, "")

        ttk.Label(time_frame, text="延迟(秒):").pack(side="left", padx=(10, 2))
        self.delay_entry = ttk.Entry(time_frame, width=6)
        self.delay_entry.pack(side="left", padx=2)
        self.delay_entry.insert(0, "0")

        ttk.Label(time_frame, text="显示时长(秒):").pack(side="left", padx=(10, 2))
        self.duration_entry = ttk.Entry(time_frame, width=6)
        self.duration_entry.pack(side="left", padx=2)
        self.duration_entry.insert(0, "")

        # 额外滤镜显示
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill="x", padx=5, pady=2, anchor="w")
        ttk.Label(filter_frame, text="需要保留的预处理滤镜:", font=("Microsoft YaHei", 9, "bold")).pack(side="left")
        self.filter_display = ttk.Entry(filter_frame, font=("Consolas", 9), state="readonly")
        self.filter_display.pack(side="left", fill="x", expand=True, padx=5)

        # 轨迹文本
        self.traj_text = tk.Text(self, height=2, font=("Microsoft YaHei", 9), wrap="word")
        self.traj_text.pack(fill="x", padx=5, pady=5, anchor="w")
        self.update_traj_display()

    # ---------- 透明度 ----------
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

    # ---------- 缩放 ----------
    def toggle_scale(self):
        state = "normal" if self.use_scale_var.get() else "disabled"
        self.scale_w_entry.config(state=state)
        self.scale_h_entry.config(state=state)

    def set_scale(self, w, h):
        self.use_scale_var.set(True)
        self.scale_w_entry.config(state="normal")
        self.scale_h_entry.config(state="normal")
        self.scale_w_entry.delete(0, tk.END)
        self.scale_w_entry.insert(0, w)
        self.scale_h_entry.delete(0, tk.END)
        self.scale_h_entry.insert(0, h)

    def on_scale_entry_change(self, event=None):
        """智能补全 -2：当其中一个为空时，自动设为 -2"""
        if not self.use_scale_var.get():
            return
        w_val = self.scale_w_entry.get().strip()
        h_val = self.scale_h_entry.get().strip()
        if not w_val and not h_val:
            return
        # W 空，H 有值 => W = -2
        if not w_val and h_val:
            self.scale_w_entry.config(state="normal")
            self.scale_w_entry.delete(0, tk.END)
            self.scale_w_entry.insert(0, "-2")
            if not self.use_scale_var.get():
                self.scale_w_entry.config(state="disabled")
        # H 空，W 有值 => H = -2
        elif w_val and not h_val:
            self.scale_h_entry.config(state="normal")
            self.scale_h_entry.delete(0, tk.END)
            self.scale_h_entry.insert(0, "-2")
            if not self.use_scale_var.get():
                self.scale_h_entry.config(state="disabled")

    # ---------- 静态坐标 ----------
    def set_static_position(self, x, y):
        self.static_x = x
        self.static_y = y

    # ---------- 额外滤镜 ----------
    def set_original_filters(self, filters_str):
        self.original_pre_filters = filters_str
        self.filter_display.config(state="normal")
        self.filter_display.delete(0, tk.END)
        if filters_str:
            self.filter_display.insert(0, filters_str)
        else:
            self.filter_display.insert(0, "(无额外滤镜)")
        self.filter_display.config(state="readonly")

    # ---------- 轨迹操作 ----------
    def add_point(self, name):
        self.trajectory.append(name)
        self.update_traj_display()

    def undo_point(self):
        if self.trajectory:
            self.trajectory.pop()
            self.update_traj_display()
        else:
            messagebox.showinfo("提示", "当前轨道已经是空的了！")

    def clear_trajectory(self):
        if self.trajectory:
            self.trajectory.clear()
            self.update_traj_display()
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


class MultiTrackWatermarkGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FFmpeg 多轨道水印轨迹编排器 v15.5")

        win_width, win_height = 1100, 850
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - win_width) // 2
        y = (screen_height - win_height) // 2
        self.root.geometry(f"{win_width}x{win_height}+{x}+{y}")

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

        # 全局参数
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

        # 右侧轨道列表
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

    # ---------- 短路径转换 ----------
    def get_short_path(self, path):
        try:
            buffer = ctypes.create_unicode_buffer(260)
            length = ctypes.windll.kernel32.GetShortPathNameW(path, buffer, 260)
            if length > 0:
                return buffer.value
        except Exception:
            pass
        return path

    # ---------- 获取主视频时长 ----------
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

    # ---------- 解析命令生成轨道 ----------
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

        # 提取每个子视频的滤镜串
        raw_filters_map = {}
        if filter_complex:
            pattern = r'\[(\d+):v\]([^\[]+?)(?=\s*\[|$)'
            matches = re.findall(pattern, filter_complex)
            for idx, filters in matches:
                raw_filters_map[int(idx)] = filters.strip(',')

        # 提取透明度
        alpha_pattern = re.compile(r'\[v_sub_(\d+)\]colorchannelmixer=aa=([0-9.]+)')
        alpha_map = {}
        if filter_complex:
            for m in alpha_pattern.finditer(filter_complex):
                alpha_map[int(m.group(1))] = float(m.group(2))

        # ===== 增强的静态坐标提取 =====
        static_coords = []
        if filter_complex:
            # 1) 尝试匹配带引号的 x='...' y='...'
            pattern1 = r"overlay=x='([^']*)':y='([^']*)'"
            matches1 = re.findall(pattern1, filter_complex)
            if matches1:
                static_coords = [(x.strip(), y.strip()) for x, y in matches1]
            else:
                # 2) 尝试匹配 x=...:y=...（无引号）
                pattern2 = r"overlay=x=([^:]*):y=([^:]*)(?=[:]|$)"
                matches2 = re.findall(pattern2, filter_complex)
                if matches2:
                    static_coords = [(x.strip(), y.strip()) for x, y in matches2]
                else:
                    # 3) 尝试匹配 overlay=参数:参数 这种无前缀形式
                    # 使用正则 overlay=([^:]+):([^:]+) 并过滤掉 enable/shortest
                    overlay_pattern = re.compile(r'overlay=([^:]+):([^:]+)')
                    for m in overlay_pattern.finditer(filter_complex):
                        x = m.group(1).strip()
                        y = m.group(2).strip()
                        # 如果 x 或 y 是 enable、shortest 等，则跳过
                        if x.lower() in ('enable', 'shortest') or y.lower() in ('enable', 'shortest'):
                            continue
                        static_coords.append((x, y))
                    # 如果还没有匹配，可能 overlay 只有一个参数（比如只有 x 或只有 y），忽略

        # 创建轨道
        for idx, file_path in enumerate(inputs[1:], start=1):
            file_name = file_path.split("/")[-1].split("\\")[-1]
            track = TrackFrame(self.scrollable_frame, idx, file_name)
            track.pack(fill="x", padx=5, pady=5)

            # 原始滤镜提取
            raw_filters = raw_filters_map.get(idx, "")
            scale_w = scale_h = None
            clean_filters = []
            if raw_filters:
                parts = raw_filters.split(',')
                for part in parts:
                    part = part.strip()
                    m = re.match(r'^scale=([^:]+):([^:,]+)', part)
                    if m:
                        scale_w, scale_h = m.group(1), m.group(2)
                    else:
                        clean_filters.append(part)
            clean_str = ','.join(clean_filters) if clean_filters else None
            if clean_str:
                clean_str = re.sub(r',?format=[a-zA-Z0-9]+', '', clean_str)
                clean_str = re.sub(r',?null', '', clean_str)
                clean_str = re.sub(r',?colorchannelmixer=[^,]*', '', clean_str)
                clean_str = clean_str.strip(',')
                if not clean_str:
                    clean_str = None

            track.set_original_filters(clean_str)

            # 透明度
            if (idx-1) in alpha_map:
                track.set_alpha(alpha_map[idx-1])

            # 缩放
            if scale_w is not None and scale_h is not None:
                track.set_scale(scale_w, scale_h)

            # ===== 静态坐标：按顺序对应 =====
            if idx-1 < len(static_coords):
                x, y = static_coords[idx-1]
                track.set_static_position(x, y)

            self.tracks.append(track)

        messagebox.showinfo("解析成功", f"成功识别到 {len(inputs)-1} 个子视频轨道！")

    # ---------- 构建单轴运动表达式 ----------
    def build_axis_expr(self, trajectory, global_duration, axis_idx,
                        loop=True, mode="跳跃循环",
                        track_cycle=None, track_delay=0.0):
        num_segments = len(trajectory) - 1
        if num_segments <= 0:
            return POSITIONS[trajectory[0]][axis_idx]

        if track_cycle and track_cycle.strip():
            try:
                effective_duration = float(track_cycle.strip())
            except ValueError:
                effective_duration = global_duration
        else:
            effective_duration = global_duration

        seg_dur = effective_duration / num_segments
        delay = float(track_delay) if track_delay else 0.0

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

        # 解析原始命令提取输入
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

        # ========== 构建 filter_complex ==========
        filter_chain = []
        filter_chain.append("[0:v]format=yuv420p[v_main]")
        current_base = "[v_main]"
        output_counter = 0

        for track in self.tracks:
            has_trajectory = len(track.trajectory) >= 1
            has_static = (track.static_x is not None and track.static_y is not None)
            if not has_trajectory and not has_static:
                continue

            # 读取时间参数
            cycle = track.cycle_entry.get().strip() or None
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

            if cycle and cycle.strip():
                try:
                    effective_duration = float(cycle.strip())
                except ValueError:
                    effective_duration = global_duration
            else:
                effective_duration = global_duration

            idx = track.index

            if has_trajectory:
                x_expr = self.build_axis_expr(track.trajectory, global_duration, 0, loop, mode, cycle, delay_val)
                y_expr = self.build_axis_expr(track.trajectory, global_duration, 1, loop, mode, cycle, delay_val)
            else:
                x_expr = track.static_x
                y_expr = track.static_y

            sub_stream = f"[{idx}:v]"
            sub_temp_label = f"v_sub_{idx}"
            out_stream = f"[v_out_{output_counter}]"

            # 缩放 + 额外滤镜
            scale_part = ""
            if track.use_scale_var.get():
                w = track.scale_w_entry.get().strip()
                h = track.scale_h_entry.get().strip()
                if not w or not h:
                    messagebox.showerror("错误", f"轨道 {track['text']} 启用了缩放但未填写宽或高！")
                    return
                scale_part = f"scale={w}:{h}"

            filters = []
            if scale_part:
                filters.append(scale_part)
            if track.original_pre_filters:
                filters.append(track.original_pre_filters)

            if filters:
                sub_pipeline = f"{sub_stream}{','.join(filters)}[{sub_temp_label}]"
            else:
                sub_pipeline = f"{sub_stream}null[{sub_temp_label}]"

            format_pipeline = f"[{sub_temp_label}]format=rgba[{sub_temp_label}_rgba]"

            # ===== 构建 enable 表达式 =====
            if delay_val > 0:
                enable_parts = [f"gte(t,{delay_val})"]
            else:
                enable_parts = ["1"]

            if not loop and end_behavior == "立即消失" and has_trajectory:
                end_time = delay_val + effective_duration
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

        # 输出路径
        first_path = input_entries[0][1]
        base_dir = os.path.dirname(first_path)
        base_name = os.path.splitext(os.path.basename(first_path))[0]
        output_file = os.path.join(base_dir, f"{base_name}_watermarked.mp4")
        output_file = output_file.replace('\\', '/')
        output_file = self.get_short_path(output_file)

        # ========== 使用列表构建命令 ==========
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
