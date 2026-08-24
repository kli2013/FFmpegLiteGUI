import tkinter as tk
from tkinter import ttk, messagebox
import re
import subprocess
import shlex
import os
import ctypes
import threading
import math

# ================== 画板尺寸常量（可调） ==================
MAX_CANVAS_SIZE = 960   # 画板长边像素

# ================== Ramer–Douglas–Peucker 抽稀算法 ==================
def perpendicular_distance(p, a, b):
    x0, y0 = p
    x1, y1 = a
    x2, y2 = b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((x0 - x1) ** 2 + (y0 - y1) ** 2) ** 0.5
    t = ((x0 - x1) * dx + (y0 - y1) * dy) / (dx * dx + dy * dy)
    if t < 0:
        return ((x0 - x1) ** 2 + (y0 - y1) ** 2) ** 0.5
    elif t > 1:
        return ((x0 - x2) ** 2 + (y0 - y2) ** 2) ** 0.5
    else:
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        return ((x0 - proj_x) ** 2 + (y0 - proj_y) ** 2) ** 0.5

def ramer_douglas_peucker(points, epsilon):
    if len(points) < 3:
        return points
    dmax = 0
    index = 0
    for i in range(1, len(points) - 1):
        d = perpendicular_distance(points[i], points[0], points[-1])
        if d > dmax:
            index = i
            dmax = d
    if dmax > epsilon:
        rec1 = ramer_douglas_peucker(points[:index + 1], epsilon)
        rec2 = ramer_douglas_peucker(points[index:], epsilon)
        return rec1[:-1] + rec2
    else:
        return [points[0], points[-1]]

# ================== 5x5 点位生成（仍用于网格点） ==================
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

# ================== 段编辑弹窗 ==================
class SegmentEditor(tk.Toplevel):
    def __init__(self, parent, track_frame):
        super().__init__(parent)
        self.track = track_frame
        self.title(f"编辑段控制 - {track_frame['text']}")
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        width, height = 330, 420
        x = parent_x + (parent_w - width) // 2
        y = parent_y + (parent_h - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.resizable(True, True)
        self.minsize(330, 300)

        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(0, 5))
        ttk.Button(btn_frame, text="保存", command=self.save_and_close).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side="left", padx=5)

        head_frame = ttk.Frame(main_frame)
        head_frame.pack(fill="x", pady=2)
        ttk.Label(head_frame, text="段", width=12).pack(side="left")
        ttk.Label(head_frame, text="模式", width=12).pack(side="left")
        ttk.Label(head_frame, text="时长(秒)", width=10).pack(side="left")

        # ---- 可滚动的段列表（固定窗口 + 垂直滚动条，点数再多也能看全） ----
        list_container = ttk.Frame(main_frame)
        list_container.pack(fill="both", expand=True)

        # 显式指定 canvas 宽度：Tk Canvas 默认请求宽度约 10cm（高 DPI 下可达 400+px），
        # 超过 330px 的窗口宽度时会先把滚动条挤出可视区，必须设一个合适值
        canvas = tk.Canvas(list_container, width=280, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        # 用 tags 标记内部内容窗，方便跟随 canvas 宽度
        canvas.create_window((0, 0), window=scrollable, anchor="nw", tags=("inner",))
        canvas.configure(yscrollcommand=scrollbar.set)

        def _sync_region(e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_width(e):
            # 让内部内容宽度跟随 canvas 可视宽度，避免被裁切
            canvas.itemconfigure("inner", width=e.width)

        scrollable.bind("<Configure>", _sync_region)
        canvas.bind("<Configure>", _sync_width)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        # 只绑 canvas 不够：Windows 下滚轮事件发给“键盘焦点控件”，
        # 鼠标停在行内的下拉框/输入框上时 canvas 收不到事件，
        # 必须递归绑定到列表里的每个子控件（含 Combobox、Entry）
        def _bind_wheel_recursive(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            for child in widget.winfo_children():
                _bind_wheel_recursive(child)

        canvas.bind("<MouseWheel>", _on_mousewheel)
        self._bind_wheel_recursive = _bind_wheel_recursive

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.seg_count_var = tk.StringVar(value="")
        count_label = ttk.Label(main_frame, textvariable=self.seg_count_var, foreground="#666666")
        count_label.pack(fill="x", pady=(4, 0))

        self.rows = []
        self.refresh_entries(scrollable)
        # 窗口映射后再校准一次滚动区域，确保初始就正确
        self.after(60, _sync_region)

    def refresh_entries(self, parent):
        for widget in parent.winfo_children():
            widget.destroy()
        self.rows.clear()

        trajectory = self.track.trajectory
        if len(trajectory) < 2:
            ttk.Label(parent, text="至少需要2个轨迹点").pack()
            self.seg_count_var.set("至少需要2个轨迹点")
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
            label = ttk.Label(frame, text=f"点{i} → 点{i+1}", width=12)
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

        # 行控件是动态重建的，重建后必须重新递归绑定滚轮
        self._bind_wheel_recursive(parent)

        self.seg_count_var.set(f"共 {n} 段　（超出窗口可用右侧滚动条或鼠标滚轮查看）")

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

# ================== 自由路径绘制弹窗 ==================
class FreePathEditor(tk.Toplevel):
    def __init__(self, parent, track_frame, app):
        super().__init__(parent)
        self.track_frame = track_frame
        self.app = app
        self.title("自由路径绘制")
        self.max_canvas = MAX_CANVAS_SIZE

        w_ratio, h_ratio = self.app.aspect_ratio
        if w_ratio >= h_ratio:
            self.canvas_w = self.max_canvas
            self.canvas_h = int(self.max_canvas * h_ratio / w_ratio)
        else:
            self.canvas_h = self.max_canvas
            self.canvas_w = int(self.max_canvas * w_ratio / h_ratio)

        win_w = self.canvas_w + 40
        win_h = self.canvas_h + 100
        self.geometry(f"{win_w}x{win_h}")
        self.resizable(False, False)

        self.canvas = tk.Canvas(self, width=self.canvas_w, height=self.canvas_h,
                                bg='white', highlightthickness=1, highlightcolor='gray')
        self.canvas.pack(padx=20, pady=10)

        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="清空", command=self.clear_path).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="撤销", command=self.undo_last).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="确认", command=self.apply_path).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side="left", padx=5)

        self.points = []
        self.drawing = False
        self.current_line = None
        self._redraw_restored_path()

    def on_mouse_down(self, event):
        self.drawing = True
        # 开始新绘制前，清除已显示的旧路径（包括上次恢复的路径）
        if self.current_line:
            self.canvas.delete(self.current_line)
            self.current_line = None
        self.points = [(event.x, event.y)]
        self.current_line = self.canvas.create_line(event.x, event.y, event.x, event.y,
                                                    fill='blue', width=2)

    def on_mouse_move(self, event):
        if self.drawing:
            self.points.append((event.x, event.y))
            flat = [coord for point in self.points for coord in point]
            self.canvas.coords(self.current_line, *flat)

    def on_mouse_up(self, event):
        if self.drawing:
            self.drawing = False
            self.points.append((event.x, event.y))
            flat = [coord for point in self.points for coord in point]
            self.canvas.coords(self.current_line, *flat)

    def clear_path(self):
        self.points.clear()
        if self.current_line:
            self.canvas.delete(self.current_line)
            self.current_line = None

    def undo_last(self):
        if self.points:
            self.points.pop()
            if self.points:
                flat = [coord for point in self.points for coord in point]
                self.canvas.coords(self.current_line, *flat)
            else:
                self.canvas.delete(self.current_line)
                self.current_line = None

    def apply_path(self):
        if len(self.points) < 2:
            messagebox.showinfo("提示", "至少需要两个点")
            return
        epsilon = self.app.get_epsilon()
        simplified = ramer_douglas_peucker(self.points, epsilon)
        if len(simplified) < 2:
            simplified = [self.points[0], self.points[-1]]
        ratio_pts = [(x / self.canvas_w, y / self.canvas_h) for x, y in simplified]
        self.track_frame.set_free_path(ratio_pts)
        self.destroy()

    def _redraw_restored_path(self):
        # 打开弹窗时，若轨道已存在上次绘制的自由路径，则把它画出来
        prev = getattr(self.track_frame, 'free_path_ratio', None)
        if not prev:
            return
        px = [int(rx * self.canvas_w) for rx, ry in prev]
        py = [int(ry * self.canvas_h) for rx, ry in prev]
        if len(px) < 2:
            return
        flat = []
        for x, y in zip(px, py):
            flat.extend((x, y))
        self.points = list(zip(px, py))
        self.current_line = self.canvas.create_line(*flat, fill='blue', width=2)

# ================== 轨道控件 ==================
class TrackFrame(ttk.LabelFrame):
    def __init__(self, master, index, name, app):
        super().__init__(master, text=name)
        self.app = app
        self.index = index
        self.trajectory = []          # 存储 (x_expr, y_expr) 元组
        self.free_path_ratio = []     # 记录上次自由路径的原始比例点，供再次打开时恢复显示
        self.static_x = None
        self.static_y = None
        self.filter_parts = []
        self.segment_modes = []
        self.segment_durations = []
        # blend 混合模式（parse 时从命令识别，normal=普通叠加；非 normal 时生成区域化 blend 子图）
        self.blend_mode = "normal"

        # 特效（旋转 / delogo / 遮罩）—— 与主程序新近加的子视频能力保持对齐
        self.spin_enabled_var = tk.BooleanVar(value=False)
        self.spin_speed_var = tk.StringVar(value="60")
        self.delogo_enabled_var = tk.BooleanVar(value=False)
        self.delogo_x = tk.StringVar(value="0")
        self.delogo_y = tk.StringVar(value="0")
        self.delogo_w = tk.StringVar(value="100")
        self.delogo_h = tk.StringVar(value="100")
        self.mask_enabled_var = tk.BooleanVar(value=False)
        self.mask_x = tk.StringVar(value="0")
        self.mask_y = tk.StringVar(value="0")
        self.mask_w = tk.StringVar(value="100")
        self.mask_h = tk.StringVar(value="100")
        self.mask_mode = tk.StringVar(value="outside")  # outside=只露矩形(矩形外透明); inside=矩形透明(矩形外正常)

        # ---- 轨迹按钮 ----
        btn_frame = ttk.Frame(self)
        btn_frame.pack(padx=5, pady=5, anchor="w")
        for i, pos_name in enumerate(POSITIONS.keys()):
            btn = ttk.Button(btn_frame, text=pos_name, width=6,
                             command=lambda n=pos_name: self.add_point(n))
            btn.grid(row=i // 5, column=i % 5, padx=2, pady=2)
        ttk.Button(btn_frame, text="自由路径", command=self.open_free_path_editor).grid(row=0, column=5, padx=10, pady=2, rowspan=5)

        # ---- 操作按钮 ----
        action_frame = ttk.Frame(self)
        action_frame.pack(fill="x", padx=5, pady=2, anchor="w")
        ttk.Button(action_frame, text="撤销上一个", command=self.undo_point).pack(side="left", padx=2)
        ttk.Button(action_frame, text="清空轨迹", command=self.clear_trajectory).pack(side="left", padx=2)

        # ---- 透明度 ----
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

        # ---- 缩放 ----
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

        # ---- 特效（旋转 / delogo / 遮罩） ----
        fx_frame = ttk.Frame(self)
        fx_frame.pack(fill="x", padx=5, pady=2, anchor="w")
        ttk.Checkbutton(fx_frame, text="旋转", variable=self.spin_enabled_var,
                        command=self.toggle_fx).pack(side="left")
        ttk.Label(fx_frame, text="转速:").pack(side="left", padx=(4, 2))
        self.spin_speed_entry = ttk.Entry(fx_frame, width=5, textvariable=self.spin_speed_var,
                                         state="disabled")
        self.spin_speed_entry.pack(side="left")
        ttk.Label(fx_frame, text="°/秒").pack(side="left")
        self.delogo_chk = ttk.Checkbutton(fx_frame, text="delogo", variable=self.delogo_enabled_var,
                                          command=self.toggle_fx)
        self.delogo_chk.pack(side="left", padx=(10, 2))
        self.delogo_btn = ttk.Button(fx_frame, text="区域…", command=lambda: self.open_rect_dialog("delogo"),
                                     state="disabled", width=6)
        self.delogo_btn.pack(side="left", padx=2)
        self.mask_chk = ttk.Checkbutton(fx_frame, text="遮罩", variable=self.mask_enabled_var,
                                        command=self.toggle_fx)
        self.mask_chk.pack(side="left", padx=(10, 2))
        self.mask_btn = ttk.Button(fx_frame, text="区域…", command=lambda: self.open_rect_dialog("mask"),
                                   state="disabled", width=6)
        self.mask_btn.pack(side="left", padx=2)
        self.fx_summary = ttk.Label(fx_frame, text="", foreground="#666666")
        self.fx_summary.pack(side="left", padx=(8, 0))

        # ---- 时间控制第一行 ----
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

        # ---- 第二行 ----
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

        # ---- 滤镜显示 ----
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill="x", padx=5, pady=2, anchor="w")
        ttk.Label(filter_frame, text="预处理滤镜顺序:", font=("Microsoft YaHei", 9, "bold")).pack(side="left")
        self.filter_display = ttk.Entry(filter_frame, font=("Consolas", 9), state="readonly")
        self.filter_display.pack(side="left", fill="x", expand=True, padx=5)

        # ---- 轨迹显示 ----
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
        x_expr, y_expr = POSITIONS[name]
        self.trajectory.append((x_expr, y_expr))
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
            self.traj_text.insert(tk.END, f"轨迹 ({len(self.trajectory)}个点)")
        else:
            if self.static_x is not None and self.static_y is not None:
                self.traj_text.insert(tk.END, f"(静态位置: x={self.static_x}, y={self.static_y})")
            else:
                self.traj_text.insert(tk.END, "(空)")
        self.traj_text.config(state="disabled")

    # ---------- 自由路径 ----------
    def open_free_path_editor(self):
        FreePathEditor(self.winfo_toplevel(), self, self.app)

    def set_free_path(self, ratio_points):
        # 关键点封顶：超过上限时按索引均匀重采样，从源头压短命令
        cap = self.app.get_max_keyframes() if hasattr(self.app, 'get_max_keyframes') else 200
        pts = list(ratio_points)
        if len(pts) > cap:
            idxs = [round(i * (len(pts) - 1) / (cap - 1)) for i in range(cap)]
            seen, capped = set(), []
            for i in idxs:
                if i not in seen:
                    seen.add(i)
                    capped.append(pts[i])
            pts = capped if len(capped) >= 2 else [pts[0], pts[-1]]
        self.free_path_ratio = list(pts)
        self.trajectory.clear()
        self.segment_modes.clear()
        self.segment_durations.clear()
        for rx, ry in pts:
            x_expr = f"{rx} * W"
            y_expr = f"{ry} * H"
            self.trajectory.append((x_expr, y_expr))
        self.update_traj_display()
        if self.advanced_var.get():
            self._init_segments()
            self.refresh_advanced_cycle()
        elif self.jump_mode_var.get():
            self.refresh_cycle()

    # ---------- 其它方法 ----------
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

    # ---------- 特效：旋转 / delogo / 遮罩 ----------
    def toggle_fx(self):
        """根据勾选启用/禁用对应的控件和入口按钮，并刷新摘要。"""
        self.spin_speed_entry.config(state="normal" if self.spin_enabled_var.get() else "disabled")
        self.delogo_btn.config(state="normal" if self.delogo_enabled_var.get() else "disabled")
        self.mask_btn.config(state="normal" if self.mask_enabled_var.get() else "disabled")
        self.update_fx_summary()

    def update_fx_summary(self):
        parts = []
        if self.spin_enabled_var.get():
            try:
                sp = float(self.spin_speed_var.get())
                parts.append(f"旋转 {sp:g}°/秒")
            except (ValueError, TypeError):
                parts.append("旋转 (转速无效)")
        if self.delogo_enabled_var.get():
            parts.append(f"delogo {self.delogo_x.get()},{self.delogo_y.get()} "
                         f"{self.delogo_w.get()}×{self.delogo_h.get()}")
        if self.mask_enabled_var.get():
            mode = self.mask_mode.get()
            parts.append(f"遮罩[{mode}] {self.mask_x.get()},{self.mask_y.get()} "
                         f"{self.mask_w.get()}×{self.mask_h.get()}")
        self.fx_summary.config(text=" · ".join(parts))

    def open_rect_dialog(self, kind):
        RectSettingsDialog(self.winfo_toplevel(), self, kind)

    def set_spin(self, enabled, speed):
        self.spin_enabled_var.set(bool(enabled))
        self.spin_speed_var.set(f"{speed:g}" if isinstance(speed, (int, float)) else str(speed))
        self.toggle_fx()

    def set_delogo(self, enabled, x=None, y=None, w=None, h=None):
        self.delogo_enabled_var.set(bool(enabled))
        if x is not None: self.delogo_x.set(str(x))
        if y is not None: self.delogo_y.set(str(y))
        if w is not None: self.delogo_w.set(str(w))
        if h is not None: self.delogo_h.set(str(h))
        self.toggle_fx()

    def set_mask(self, enabled, x=None, y=None, w=None, h=None, mode=None):
        self.mask_enabled_var.set(bool(enabled))
        if x is not None: self.mask_x.set(str(x))
        if y is not None: self.mask_y.set(str(y))
        if w is not None: self.mask_w.set(str(w))
        if h is not None: self.mask_h.set(str(h))
        if mode is not None: self.mask_mode.set(mode)
        self.toggle_fx()

# ================== 矩形/遮罩设置对话框（delogo & mask 共用） ==================
class RectSettingsDialog(tk.Toplevel):
    """delogo / 遮罩 区域设置对话框。delogo 不需要 mode 字段；mask 才有 mode。"""
    def __init__(self, parent, track, kind):
        # kind: "delogo" 或 "mask"
        super().__init__(parent)
        self.track = track
        self.kind = kind
        self.transient(parent)
        self.resizable(False, False)
        self.title("delogo 区域设置" if kind == "delogo" else "遮罩设置")

        # 复制当前值（保存时才写回 track）
        if kind == "delogo":
            self.x = tk.StringVar(value=track.delogo_x.get())
            self.y = tk.StringVar(value=track.delogo_y.get())
            self.w = tk.StringVar(value=track.delogo_w.get())
            self.h = tk.StringVar(value=track.delogo_h.get())
        else:
            self.x = tk.StringVar(value=track.mask_x.get())
            self.y = tk.StringVar(value=track.mask_y.get())
            self.w = tk.StringVar(value=track.mask_w.get())
            self.h = tk.StringVar(value=track.mask_h.get())
            self.mode = tk.StringVar(value=track.mask_mode.get())

        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame,
                  text=("delogo 在缩放/裁剪前的原始帧上生效；坐标按子视频原始宽高。" if kind == "delogo"
                        else "遮罩在缩放/裁剪前的原始帧上生效；坐标按子视频原始宽高。"),
                  foreground="#666666").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        ttk.Label(main_frame, text="x:").grid(row=1, column=0, sticky="w", padx=(0, 2), pady=2)
        ttk.Entry(main_frame, textvariable=self.x, width=8).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(main_frame, text="y:").grid(row=1, column=2, sticky="w", padx=(8, 2), pady=2)
        ttk.Entry(main_frame, textvariable=self.y, width=8).grid(row=1, column=3, sticky="w", pady=2)

        ttk.Label(main_frame, text="w:").grid(row=2, column=0, sticky="w", padx=(0, 2), pady=2)
        ttk.Entry(main_frame, textvariable=self.w, width=8).grid(row=2, column=1, sticky="w", pady=2)
        ttk.Label(main_frame, text="h:").grid(row=2, column=2, sticky="w", padx=(8, 2), pady=2)
        ttk.Entry(main_frame, textvariable=self.h, width=8).grid(row=2, column=3, sticky="w", pady=2)

        cur_row = 3
        if kind == "mask":
            ttk.Label(main_frame, text="模式:").grid(row=cur_row, column=0, sticky="w", padx=(0, 2), pady=(4, 2))
            ttk.Combobox(main_frame, textvariable=self.mode,
                         values=["outside", "inside"], state="readonly", width=10).grid(
                row=cur_row, column=1, columnspan=3, sticky="w", pady=(4, 2))
            ttk.Label(main_frame,
                      text="outside=只露矩形（矩形外透明）  inside=矩形透明（矩形外正常）",
                      foreground="#666666").grid(row=cur_row+1, column=0, columnspan=4, sticky="w", pady=(2, 6))
            cur_row += 2

        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=cur_row, column=0, columnspan=4, pady=(6, 0))
        ttk.Button(btn_frame, text="保存", command=self.save_and_close).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side="left", padx=5)

        self.grab_set()

    def save_and_close(self):
        if self.kind == "delogo":
            self.track.delogo_x.set(self.x.get().strip() or "0")
            self.track.delogo_y.set(self.y.get().strip() or "0")
            self.track.delogo_w.set(self.w.get().strip() or "100")
            self.track.delogo_h.set(self.h.get().strip() or "100")
        else:
            self.track.mask_x.set(self.x.get().strip() or "0")
            self.track.mask_y.set(self.y.get().strip() or "0")
            self.track.mask_w.set(self.w.get().strip() or "100")
            self.track.mask_h.set(self.h.get().strip() or "100")
            self.track.mask_mode.set(self.mode.get())
        self.track.update_fx_summary()
        self.destroy()


# ================== 滤镜串切分（引号感知） ==================
def split_filters_aware(text):
    """按顶层逗号切分滤镜串，忽略单引号内的逗号。

    旋转等滤镜表达式带引号逗号（如 rotate=angle='60*PI/180*t':ow='hypot(iw,ih)'），
    直接 str.split(',') 会把它们拆成碎片混进 filter_parts；这里只在引号外切。
    """
    parts = []
    cur = []
    in_quote = False
    for ch in text:
        if ch == "'":
            in_quote = not in_quote
        if ch == ',' and not in_quote:
            parts.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append(''.join(cur))
    return [p.strip() for p in parts if p.strip()]


# ================== 主程序 ==================
class MultiTrackWatermarkGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FFmpeg 多轨道水印轨迹编排器 v18.1")

        # 屏幕自适应
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        target_width = min(1100, int(screen_width * 0.9))
        target_height = min(850, int(screen_height * 0.9))
        target_width = max(target_width, 800)
        target_height = max(target_height, 600)
        x = (screen_width - target_width) // 2
        y = (screen_height - target_height) // 2
        self.root.geometry(f"{target_width}x{target_height}+{x}+{y}")

        self.aspect_ratio = (16, 9)
        self.video_resolution = None

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

        # 自由路径：关键点封顶 + 简化容差（同一行，均可随时修改）
        param_row = ttk.Frame(left_panel)
        param_row.pack(fill="x", pady=5, padx=5)

        cap_frame = ttk.Frame(param_row)
        cap_frame.pack(side="left")
        ttk.Label(cap_frame, text="自由路径点封顶:").pack(side="left")
        self.max_keyframes_var = tk.StringVar(value="200")
        self.max_keyframes_entry = ttk.Entry(cap_frame, width=5, textvariable=self.max_keyframes_var)
        self.max_keyframes_entry.pack(side="left", padx=3)
        ttk.Label(cap_frame, text="个(单表达式上限约95段)").pack(side="left")

        ttk.Label(param_row, text="   ").pack(side="left")

        eps_frame = ttk.Frame(param_row)
        eps_frame.pack(side="left")
        ttk.Label(eps_frame, text="自由路径简化容差:").pack(side="left")
        self.epsilon_var = tk.StringVar(value="1.0")
        self.epsilon_entry = ttk.Entry(eps_frame, width=5, textvariable=self.epsilon_var)
        self.epsilon_entry.pack(side="left", padx=3)
        ttk.Label(eps_frame, text="(越小越丝滑, 推荐0.2~2)").pack(side="left")

        # sendcmd 开关：用 sendcmd 命令文件驱动 overlay 位置，彻底突破单表达式段数上限（默认开）
        self.use_sendcmd_var = tk.BooleanVar(value=True)
        sc_chk = ttk.Checkbutton(left_panel, text="自由路径用 sendcmd（突破表达式段数上限，推荐开）",
                                 variable=self.use_sendcmd_var, command=self._update_cap_status)
        sc_chk.pack(anchor="w", padx=5, pady=(2, 0))

        self.cap_status = ttk.Label(left_panel, text="", foreground="#c00000")
        self.cap_status.pack(fill="x", padx=5)
        self.max_keyframes_var.trace('w', self._update_cap_status)
        self.use_sendcmd_var.trace('w', self._update_cap_status)
        self._update_cap_status()

        ttk.Button(left_panel, text="生成多轨道叠加命令", command=self.generate_command).pack(fill="x", pady=5, padx=5)

        ttk.Label(left_panel, text="生成的命令:", font=("Microsoft YaHei", 10, "bold")).pack(anchor="w", pady=(10,0), padx=5)
        self.cmd_text = tk.Text(left_panel, height=8, font=("Microsoft YaHei", 9), wrap="word")
        self.cmd_text.pack(fill="both", expand=True, pady=5, padx=5)
        btn_row = ttk.Frame(left_panel)
        btn_row.pack(fill="x", pady=5, padx=5)
        ttk.Button(btn_row, text="运行命令", command=self.run_command).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(btn_row, text="一键复制到剪贴板", command=self.copy_to_clipboard).pack(side="left", fill="x", expand=True, padx=(2, 0))

        right_panel = ttk.Frame(paned)
        paned.add(right_panel, weight=2)

        ttk.Label(right_panel, text="自动识别的子视频轨道:", font=("Microsoft YaHei", 10, "bold")).pack(anchor="w", padx=5)

        # 显式指定 canvas 宽度，避免默认 10cm 请求宽度挤掉右侧滚动条
        canvas = tk.Canvas(right_panel, width=480)
        scrollbar = ttk.Scrollbar(right_panel, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self.canvas_window = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.bind("<Configure>", self._on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_wheel_recursive(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            for child in widget.winfo_children():
                _bind_wheel_recursive(child)

        canvas.bind("<MouseWheel>", _on_mousewheel)
        # 轨道是解析命令时动态生成的，解析完成后用这个函数递归绑定滚轮
        self._bind_track_wheel = _bind_wheel_recursive

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

    def get_video_resolution(self, video_path):
        ffprobe_cmd = "ffprobe"
        original_cmd = self.input_cmd.get("1.0", tk.END).strip()
        if original_cmd:
            try:
                args = shlex.split(original_cmd, posix=False)
                if args and (args[0].endswith('.exe') or args[0].lower() in ('ffmpeg', 'ffmpeg.exe')):
                    dirname = os.path.dirname(args[0])
                    if dirname:
                        possible = os.path.join(dirname, "ffprobe.exe")
                        if os.path.exists(possible):
                            ffprobe_cmd = possible
            except:
                pass
        cmd = [ffprobe_cmd, "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height", "-of", "csv=p=0", video_path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore',
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                out = result.stdout.strip()
                if out:
                    w, h = map(int, out.split(','))
                    return w, h
        except:
            pass
        return None

    def get_video_duration(self, video_path):
        ffprobe_cmd = "ffprobe"
        original_cmd = self.input_cmd.get("1.0", tk.END).strip()
        if original_cmd:
            try:
                args = shlex.split(original_cmd, posix=False)
                if args and (args[0].endswith('.exe') or args[0].lower() in ('ffmpeg', 'ffmpeg.exe')):
                    dirname = os.path.dirname(args[0])
                    if dirname:
                        possible = os.path.join(dirname, "ffprobe.exe")
                        if os.path.exists(possible):
                            ffprobe_cmd = possible
            except:
                pass
        try:
            cmd = [ffprobe_cmd, "-v", "error", "-show_entries", "format=duration",
                   "-of", "default=noprint_wrappers=1:nokey=1", video_path]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore',
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except:
            pass
        return None

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

    def _extract_sub_chain(self, filter_complex, idx):
        """从 filter_complex 中提取第 idx 个子视频的整条子链（含 ';' 子图）。

        返回语句列表。子链结束于「overlay 两输入语句」或下一个 [N:v] 主流语句。
        之前的正则 [N:v]([^[]+) 在首个 [ 处截断，会丢掉 split=2 之后的
        遮罩子图甚至整个子链；这里按 ';' 拆语句后从 [idx:v] 起收集，直到遇到
        overlay 语句（或下个子流语句），能完整保留含 ';' 的多语句链。
        """
        if not filter_complex:
            return []
        stmts = [s.strip() for s in filter_complex.split(';') if s.strip()]
        start_token = f"[{idx}:v]"
        out = []
        started = False
        two_input_re = re.compile(r'^\[[^\]]+\]\[[^\]]+\][a-zA-Z]')
        for s in stmts:
            if not started:
                if s.startswith(start_token):
                    started = True
                    out.append(s)
                continue
            # 两输入语句：overlay/混合/amix 等。alphamerge 是遮罩子图的正常环节，留住。
            if two_input_re.match(s) and 'overlay' in s:
                break
            if two_input_re.match(s) and 'alphamerge' in s:
                out.append(s)
                continue
            if two_input_re.match(s):
                # 其它两输入滤镜（mix、xfade 等）属于主链而非子视频，保守停
                break
            out.append(s)
        return out

    def _apply_scale_dims(self, w, h, scale_str):
        """把缩放滤镜 `scale=W:H` 应用到 (w,h) 上，返回新尺寸。
        仅支持常见写法：纯数字、一侧 -1 / -2（保持比例）；其余表达式无法求值则返回原值。
        """
        if not scale_str or w is None or h is None:
            return w, h
        m = re.match(r'^scale=([^:]+):([^:,]+)', scale_str.strip())
        if not m:
            return w, h
        sw, sh = m.group(1).strip(), m.group(2).strip()

        def num(s):
            try:
                return float(s)
            except (ValueError, TypeError):
                return None

        nw, nh = num(sw), num(sh)
        if nw is not None and nh is not None and nw > 0 and nh > 0:
            return int(round(nw)), int(round(nh))
        # 单边等比（-1 / -2：-2 取偶数）
        try:
            if nw is not None and nw > 0 and (nh is None or nh <= 0):
                nh2 = h * nw / w if w else nw
                nh2 = int(round(nh2))
                if str(sh).strip() == '-2' and nh2 % 2:
                    nh2 += 1
                return int(nw), nh2
            if nh is not None and nh > 0 and (nw is None or nw <= 0):
                nw2 = w * nh / h if h else nh
                nw2 = int(round(nw2))
                if str(sw).strip() == '-2' and nw2 % 2:
                    nw2 += 1
                return nw2, int(nh)
        except Exception:
            pass
        return w, h

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

        first_video = inputs[0]
        res = self.get_video_resolution(first_video)
        if res:
            w, h = res
            self.aspect_ratio = (w, h)
            self.video_resolution = (w, h)

        raw_filters_map = {}
        # 旧版用「首个 [ 处截断」的正则匹配整条子链；遇到 mask 之类的 ';' 子图
        # 会被截掉，旋转/delogo 也丢到 filter_parts 后被跳过。现改用 _extract_sub_chain
        # 拆 ';' 语句，能完整保留含子图的多语句链，再做特效识别。
        if filter_complex:
            pattern = r'\[(\d+):v\]([^\[]+?)(?=\s*\[|$)'
            matches = re.findall(pattern, filter_complex)
            for idx, filters in matches:
                raw_filters_map[int(idx)] = filters.strip(',')

        # blend 混合模式识别：主程序区域化 blend 子图形如
        #   [mcr0][rgx0b]blend=all_mode=multiply[blx0r]
        # mcr 后数字 = 子视频序号（0 起，与 -i 顺序对应）。按出现顺序兜底。
        blend_map = {}
        if filter_complex:
            for _bm in re.finditer(r"\[mcr(\d+)\]\[rgx\1b\]blend=all_mode=([a-z0-9]+)", filter_complex):
                blend_map[int(_bm.group(1))] = _bm.group(2)
            if not blend_map:
                _bms = re.findall(r"blend=all_mode=([a-z0-9]+)", filter_complex)
                if _bms:
                    blend_map = {j: bm for j, bm in enumerate(_bms)}

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
            track = TrackFrame(self.scrollable_frame, idx, file_name, self)
            track.pack(fill="x", padx=5, pady=5)

            # 用 chain 提取拿到整条子链（包含 ';' 子图），从中识别 spin/delogo/mask/alpha/scale
            chain_stmts = self._extract_sub_chain(filter_complex or "", idx)
            chain_str = ";".join(chain_stmts)

            # spin 持续旋转：匹配 `rotate=angle='N*PI/180*t'`
            spin_m = re.search(r"rotate=angle='([0-9.\-]+)\*PI/180\*t'", chain_str)
            if spin_m:
                try:
                    track.set_spin(True, float(spin_m.group(1)))
                except ValueError:
                    track.set_spin(True, spin_m.group(1))

            # delogo：匹配 `delogo=x=..:y=..:w=..:h=..`
            delogo_m = re.search(r"delogo=x=([^:]+):y=([^:]+):w=([^:]+):h=([^:]+)", chain_str)
            if delogo_m:
                track.set_delogo(True, delogo_m.group(1), delogo_m.group(2),
                                  delogo_m.group(3), delogo_m.group(4))

            # 遮罩：匹配 `format=gray,drawbox=0:0:iw:ih:color=WHITE_OR_BLACK:t=fill,
            #  drawbox=x=X:y=Y:w=W:h=H:color=WHITE_OR_BLACK:t=fill`
            # 第二个 drawbox 的 color 决定 mode（black=inside 矩形透明 / white=outside 只露矩形）
            mask_m = re.search(
                r"format=gray,drawbox=x=0:y=0:w=iw:h=ih:color=(\w+):t=fill,"
                r"drawbox=x=([^:]+):y=([^:]+):w=([^:]+):h=([^:]+):color=(\w+):t=fill",
                chain_str
            )
            if mask_m:
                rect_color = mask_m.group(6)
                mode = "inside" if rect_color == "black" else "outside"
                track.set_mask(True, mask_m.group(2), mask_m.group(3),
                                mask_m.group(4), mask_m.group(5), mode)

            # alpha：在整条子链里搜 `colorchannelmixer=aa=N`
            alpha_m = re.search(r"colorchannelmixer=aa=([0-9.]+)", chain_str)
            if alpha_m:
                try:
                    track.set_alpha(float(alpha_m.group(1)))
                except ValueError:
                    pass

            # blend 混合模式：mcr 后数字 = 子视频序号（0 起，= idx-1）。识别后：
            # ① filter_parts 摊平时跳过 blend 残留（采样 crop/alphaextract，子图生成时重建）；
            # ② generate_command 走区域化 blend 子图（不再普通叠加）。
            track.blend_mode = str(blend_map.get(idx - 1, "normal") or "normal").strip().lower()

            # scale 和其它 filter_parts：跨语句摊平扫描。
            # 注意：scale 不一定在第一条 statement —— 主程序带遮罩时形如
            #   [1:v]split=2[mks1a][mks1m];[mks1m]format=gray,drawbox=...[mks1msk];
            #   [mks1a][mks1msk]alphamerge,scale=360:642,format=rgba[v_temp_0];...
            # scale 落在 alphamerge 同句里，只扫第一条会丢 → 这里遍历整条链的每条
            # statement，剥掉输入标签前缀（单/双输入）和尾部输出标签后按 ',' 拆，
            # 跳过已识别的特效，把剩余部分按顺序摊平为 filter_parts。
            filter_parts = []
            scale_w = scale_h = None
            for stmt in (chain_stmts or [raw_filters_map.get(idx, "")]):
                body = stmt
                # 剥输入标签前缀：[x] 单输入 或 [x][y] 双输入（alphamerge 子图）
                body = re.sub(r'^(\[[^\]]+\])(\[[^\]]+\])?', '', body)
                # 剥尾部输出标签
                body = re.sub(r'(\[[^\]]+\])+$', '', body)
                for part in split_filters_aware(body):
                    if part.startswith('format=') or part.startswith('colorchannelmixer='):
                        continue
                    if part == 'null' or part.startswith('split=') or part.startswith('alphamerge'):
                        continue  # 占位/遮罩子图已识别
                    if part.startswith('drawbox='):
                        continue
                    if part.startswith('rotate=') and '*PI/180*t' in part:
                        continue  # 持续旋转已识别
                    if part.startswith('delogo='):
                        continue
                    if part.startswith('scale='):
                        m = re.match(r'^scale=([^:]+):([^:,]+)', part)
                        if m:
                            scale_w, scale_h = m.group(1), m.group(2)
                        continue
                    if part.startswith('alphaextract'):
                        continue  # blend 子图残留（子图在生成时重建）
                    if track.blend_mode != "normal" and part.startswith('crop='):
                        # blend 子视频的采样 crop（主区域+子区域两处，含静态数字与动态表达式两种）；
                        # 区域 blend 子图在 generate 时重建，残留只会造成错位双裁剪。
                        # 已知限制：blend 模式下用户自带的裁剪 crop 一并忽略（如需裁剪请用 scale）。
                        continue
                    filter_parts.append(part)

            track.set_filter_parts(filter_parts)

            if scale_w is not None and scale_h is not None:
                track.set_scale(scale_w, scale_h)

            if idx-1 < len(static_coords):
                x, y = static_coords[idx-1]
                track.set_static_position(x, y)

            self.tracks.append(track)

        # 轨道全部生成后递归绑定滚轮，保证鼠标在轨道内任意控件上都能上下滚动
        self._bind_track_wheel(self.scrollable_frame)

        messagebox.showinfo("解析成功", f"成功识别到 {len(inputs)-1} 个子视频轨道！")

    # ---------- 核心表达式构建 ----------
    def get_max_keyframes(self):
        # 读取左侧“自由路径点封顶”编辑框，随时可调（不再硬限制，由用户自行测试）
        # 注意：ffmpeg 单个 overlay 表达式约 95~100 段会崩溃（嵌套/扁平都一样），
        # 这里只返回用户输入值；超过上限时由 _update_cap_status 提示，不自动钳制。
        try:
            v = int(self.max_keyframes_var.get())
        except (ValueError, AttributeError):
            v = 200
        return max(2, v)

    def _update_cap_status(self, *args):
        # 实时提示：启用 sendcmd 后位置由命令文件驱动，不再受单表达式段数上限限制；
        # 未启用时，填入值超过约 95 段可能运行失败（不自动钳制，由用户自行测试决定）
        # 实测：嵌套/扁平写法都在 ~95~100 段处崩溃，扁平更省字符故能画更长路径
        if getattr(self, 'use_sendcmd_var', None) is not None and self.use_sendcmd_var.get():
            self.cap_status.config(
                text="✓ 已启用 sendcmd：位置由命令文件驱动，不再受单表达式段数上限限制")
            return
        try:
            v = int(self.max_keyframes_var.get())
        except (ValueError, AttributeError):
            v = 200
        if v > 95:
            self.cap_status.config(
                text=f"⚠ 填入 {v} 超过 ffmpeg 单表达式约 95 段上限，运行可能失败(可勾选 sendcmd 突破)")
        else:
            self.cap_status.config(text="")

    def get_epsilon(self):
        # 读取左侧“自由路径简化容差”编辑框，随时可调
        try:
            v = float(self.epsilon_var.get())
        except (ValueError, AttributeError):
            v = 1.0
        if v <= 0:
            v = 1.0
        return min(v, 50.0)  # 上限保护，避免过大反而丢光细节

    def build_axis_expr(self, trajectory, global_duration, axis_idx,
                        loop=True, mode="跳跃循环",
                        track_cycle=None, track_delay=0.0,
                        jump_mode=False, dwell=1.0,
                        advanced=False, seg_modes=None, seg_durations=None):
        N = len(trajectory)
        if N == 0:
            return "0"
        if N == 1:
            return trajectory[0][axis_idx]

        delay = float(track_delay) if track_delay else 0.0

        # ---- 高级段控制（扁平累加式，避免嵌套爆炸） ----
        if advanced and seg_modes and seg_durations and len(seg_modes) == N-1:
            if mode == "跳跃循环":
                seq = list(range(N-1))
            else:
                seq = list(range(N-1)) + list(range(N-2, -1, -1))

            segment_info = []
            current_time = 0.0
            for i, seg_idx in enumerate(seq):
                dur = seg_durations[seg_idx]
                seg_mode = seg_modes[seg_idx]
                if i < N-1:
                    start_node = seg_idx
                    end_node = seg_idx + 1
                else:
                    start_node = seg_idx + 1
                    end_node = seg_idx
                segment_info.append((start_node, end_node, current_time, dur, seg_mode))
                current_time += dur
            period = current_time

            if not loop:
                t_shift = f"if(lt(t,{delay}),{delay},if(lt(t,{delay+period}),t,{delay+period}))"
                mod_var = f"({t_shift}-{delay})"
            else:
                t_shift = f"if(lt(t,{delay}),{delay},t)"
                mod_var = f"mod({t_shift}-{delay},{period})"

            # 扁平化：纯 move 用紧凑累加式（更短）；含 dwell 段用"局部值×激活窗"（正确处理停留/跳变）
            has_dwell = any(seg[4] == 'dwell' for seg in segment_info)
            if not has_dwell:
                base = trajectory[segment_info[0][0]][axis_idx]
                terms = [base]
                for start_node, end_node, start_time, dur, seg_mode in segment_info:
                    s_pos = trajectory[start_node][axis_idx]
                    e_pos = trajectory[end_node][axis_idx]
                    frac = f"clip(({mod_var}-{start_time})/{dur},0,1)"
                    terms.append(f"(({e_pos})-({s_pos}))*({frac})")
                expr = "+".join(terms)
            else:
                terms = []
                for start_node, end_node, start_time, dur, seg_mode in segment_info:
                    s_pos = trajectory[start_node][axis_idx]
                    e_pos = trajectory[end_node][axis_idx]
                    if seg_mode == 'move':
                        local = f"({s_pos})+(({e_pos})-({s_pos}))*clip(({mod_var}-{start_time})/{dur},0,1)"
                    else:
                        local = f"({s_pos})"
                    active = f"if(lt({mod_var},{start_time}),0,1)*if(lt({mod_var},{start_time}+{dur}),1,0)"
                    terms.append(f"({local})*({active})")
                expr = "+".join(terms)

            if delay > 0:
                start_pos = trajectory[0][axis_idx]
                expr = f"if(lt(t,{delay}),{start_pos},{expr})"
            return expr

        # ---- 简单跳跃（扁平累加式 step） ----
        if jump_mode:
            if mode == "跳跃循环":
                seq = list(range(N))
            else:
                seq = list(range(N)) + list(range(N-2, -1, -1))
            segments = []
            current_time = 0.0
            for node_idx in seq:
                coord = trajectory[node_idx][axis_idx]
                segments.append((coord, current_time))
                current_time += dwell
            period = current_time
            tau = f"mod(if(lt(t,{delay}),{delay},t)-{delay},{period})"
            # 扁平：x = c0 + Σ_{k>=1} (c_k - c_{k-1}) * if(lt(tau, T_k), 0, 1)
            terms = [segments[0][0]]
            for k in range(1, len(segments)):
                c_prev = segments[k-1][0]
                c_k = segments[k][0]
                T_k = segments[k][1]
                step = f"if(lt({tau},{T_k}),0,1)"
                terms.append(f"(({c_k})-({c_prev}))*({step})")
            expr = "+".join(terms)
            if delay > 0:
                start_pos = trajectory[0][axis_idx]
                expr = f"if(lt(t,{delay}),{start_pos},{expr})"
            return expr

        # ---- 连续移动（扁平累加式 lerp） ----
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

        # 扁平累加：x = p0 + Σ (p_{i+1} - p_i) * clip((t_var - t_i)/seg_dur, 0, 1)
        terms = [trajectory[0][axis_idx]]
        for i in range(num_segments):
            start_val = trajectory[i][axis_idx]
            end_val = trajectory[i+1][axis_idx]
            seg_start_time = i * seg_dur
            delta = f"(({end_val})-({start_val}))"
            frac = f"clip(({t_var}-{seg_start_time})/{seg_dur},0,1)"
            terms.append(f"{delta}*({frac})")
        expr = "+".join(terms)

        if delay > 0:
            start_pos = trajectory[0][axis_idx]
            expr = f"if(lt(t,{delay}),{start_pos},{expr})"

        return expr

    # ---------- sendcmd 数值求值（忠实复现 build_axis_expr 输出） ----------
    def _eval_axis_expr(self, expr, t, W=1.0, H=1.0, w=1.0, h=1.0):
        # build_axis_expr 只用 clip/mod/if/lt + 四则运算，这里用同一套语义求值，
        # 不重新实现轨迹数学，避免与表达式逻辑漂移。
        #
        # 关键修正：表达式里经常含 w / h（如网格点位 `10+(W-w-20)*c/(cols-1)`），
        # 它们是「子视频渲染后」的宽/高——非送进 eval 之前的 w/h 无法确定，因此
        # 调用方必须把主视频真实宽高 W/H 与子视频真实宽高 w/h 传进来；缺失时
        # 这些变量在 ffmpeg overlay 上下文里可用，sendcmd 求值也必须可用，否则
        # 整条轨迹塌到 (0,0) → 水印永远在左上角不动。
        env = {
            'W': float(W) if W else 1.0,
            'H': float(H) if H else 1.0,
            'w': float(w) if w else 0.0,
            'h': float(h) if h else 0.0,
            't': float(t),
            'clip': lambda x, a, b: max(a, min(b, x)),
            'mod': lambda a, b: a - b * math.floor(a / b),
            'lt': lambda a, b: 1.0 if a < b else 0.0,
            'iff': lambda c, a, b: a if c != 0 else b,
            'abs': abs, 'floor': math.floor, 'ceil': math.ceil,
            'max': max, 'min': min, 'pow': pow, 'sqrt': math.sqrt,
        }
        e = expr.replace('if(', 'iff(')  # if 是 Python 关键字，改名后安全求值
        return float(eval(e, {'__builtins__': {}}, env))

    def _write_sendcmd_file(self, track, x_expr, y_expr, horizon, idx, base_dir,
                            main_w=1.0, main_h=1.0, sub_w=1.0, sub_h=1.0,
                            overlay_name="overlay", crop_name=None):
        # 沿时间采样轨迹位置，写出 sendcmd 命令文件驱动 overlay 的 x/y。
        # crop_name（如 "crop@cr0"）非 None 时，同一份采样额外输出 crop 的 x/y 命令：
        # blend 区域化时 crop 窗口必须与 overlay 位置同步（"走到哪混到哪"）。crop 上下文
        # 只有 iw/ih（无 W/H）→ 表达式前缀换 iw/ih，overlay 上下文用 W/H，两者同步采样。
        #
        # 命令格式（实测可用）：「time target command value;」——目标滤镜名放第二列，
        # 末尾以分号结束一条命令（缺分号报 "Missing separator"）。
        #
        # 【关键实测坑（ffmpeg n8.1.2）】sendcmd 的 target 必须与滤镜实例名**完全一致**：
        #   * 无别名 overlay → target 写 `overlay`           ✓ 有效
        #   * 别名 overlay@ov1 → target 写 `overlay@ov1`      ✓ 有效（完整名，含 @ 前缀）
        #   * 别名 overlay@ov1 → target 写 `ov1`              ✗ 无效（只写 @ 后部分找不到滤镜）
        # 因此多轨道时给每个 overlay 起唯一别名 `overlay@ov{idx}`，sendcmd target 写
        # 同样的完整 `overlay@ov{idx}`，即可精确驱动各自轨道（实测双轨各自到位）。
        # 调用方必须把完整的 `overlay@{ov_alias}` 传进来，不能只传 ov_alias。
        #
        # 求值：表达式里常含 w/h（如网格点位 `10+(W-w-20)*c/(cols-1)`），
        # 必须用主/子视频真实宽高代入。求出的 kx 是像素值，再除以 W_px 归一化——
        # sendcmd 的值在 overlay 上下文跑会再乘 W_px，等价回原像素值。kx/ky
        # 钳到 [-0.5, 1.5]：网格点位规范在 [0,1]、自由路径在 [0,1]，溢出说明
        # 子视频分辨率求值异常，钳住避免飞屏（探不到子视频尺寸时仍能基本可见）。
        # horizon 覆盖整段主视频时长（循环时探测主视频时长），循环轨迹即可全程复现。
        target_hz = 60.0
        n = int(horizon * target_hz) + 1
        MAX_PTS = 4000
        if n < 2:
            n = 2
        if n > MAX_PTS:
            n = MAX_PTS
        dt = horizon / (n - 1) if n > 1 else horizon

        # 主视频 W/H 防 0
        mw = float(main_w) if (main_w and main_w > 0) else 1.0
        mh = float(main_h) if (main_h and main_h > 0) else 1.0

        samples = []
        prev = (0.0, 0.0)
        for i in range(n):
            t_i = i * dt
            try:
                kx = self._eval_axis_expr(x_expr, t_i, mw, mh, sub_w, sub_h) / mw
                ky = self._eval_axis_expr(y_expr, t_i, mw, mh, sub_w, sub_h) / mh
                # 溢出钳位：保护网格点位/自由路径的合法范围
                kx = max(-0.5, min(1.5, kx))
                ky = max(-0.5, min(1.5, ky))
            except Exception:
                # 单点求值失败则沿用上一点，避免整条轨迹塌到 (0,0) 左上角
                kx, ky = prev
            prev = (kx, ky)
            samples.append((t_i, kx, ky))

        lines = []
        for i in range(n - 1):
            t_i, kx_i, ky_i = samples[i]
            _, kx_j, ky_j = samples[i + 1]
            sx = (kx_j - kx_i) / dt if dt > 0 else 0.0
            sy = (ky_j - ky_i) / dt if dt > 0 else 0.0
            x_cmd = f"W*({kx_i:.6f}+({sx:.6f})*(t-{t_i:.3f}))"
            y_cmd = f"H*({ky_i:.6f}+({sy:.6f})*(t-{t_i:.3f}))"
            if crop_name:
                # crop 上下文无 W/H（只有 iw/ih）→ 同一条插值换前缀；值与 overlay 完全同步
                lines.append(f"{t_i:.3f} {crop_name} x "
                             f"{x_cmd.replace('W*', 'iw*').replace('H*', 'ih*')}, "
                             f"{crop_name} y "
                             f"{y_cmd.replace('W*', 'iw*').replace('H*', 'ih*')};")
            lines.append(f"{t_i:.3f} {overlay_name} x {x_cmd}, {overlay_name} y {y_cmd};")
        # 末尾保持最后位置，避免上一段在区间外线性外推
        t_last, kx_last, ky_last = samples[-1]
        if crop_name:
            lines.append(f"{t_last:.3f} {crop_name} x iw*({kx_last:.6f}), "
                         f"{crop_name} y ih*({ky_last:.6f});")
        lines.append(f"{t_last:.3f} {overlay_name} x W*({kx_last:.6f}), "
                     f"{overlay_name} y H*({ky_last:.6f});")

        content = "\n".join(lines) + "\n"
        fname = f"ff_sendcmd_track{idx}.txt"
        path = os.path.normpath(os.path.join(base_dir, fname))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        # 只返回文件名：滤镜图里用相对名，运行时以 base_dir 为 cwd 启动 ffmpeg，
        # 这样既避开路径中的冒号（绝对路径冒号在滤镜图选项解析里会泄漏），又能稳定找到文件。
        return fname

    # ---------- 生成命令 ----------
    def generate_command(self):
        self._last_cmd = None
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

        # sendcmd 命令文件输出目录（与输出视频同目录）
        base_dir = os.path.dirname(os.path.normpath(input_entries[0][1]))
        sendcmd_files = []

        loop = self.loop_var.get()
        mode = self.loop_mode_var.get() if loop else "跳跃循环"
        end_behavior = self.end_behavior_var.get() if not loop else "停留在结束点"

        filter_chain = []
        filter_chain.append("[0:v]format=yuv420p[v_main]")
        current_base = "[v_main]"
        output_counter = 0

        # ---- 多 blend 轨道区域隔离（与主程序 _use_regional 一致）----
        # ≥2 个 blend 轨道时，主视频 split 出原始帧副本，每个 blend 从自己的副本裁区域
        # → 重叠区互不干涉（blend A 的结果不会被 blend B 当作背景再混一次）。
        # 单 blend / 全普通叠加不 split（零行为变化）。split 是帧引用（零拷贝）。
        _blend_plan = []
        for _t in self.tracks:
            _ht = len(_t.trajectory) >= 1
            _hs = (_t.static_x is not None and _t.static_y is not None)
            if not _ht and not _hs:
                continue
            _bm = str(getattr(_t, "blend_mode", "normal") or "normal").strip().lower()
            if _bm not in ("", "normal"):
                _blend_plan.append(_t)
        use_regional = len(_blend_plan) >= 2
        if use_regional:
            _n = len(_blend_plan)
            _labs = "".join(f"[bl_base{j}]" for j in range(_n))
            filter_chain.append(f"[v_main]split={_n + 1}[v_main]{_labs}")
        _blend_seq = 0  # blend 轨道序号（对应 bl_baseN）

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
            ov_alias = f"ov{idx}"  # 给 overlay 起别名，多轨道时让 sendcmd 按名定向

            # ---- 收集子视频真实尺寸（送 sendcmd 数值求值用）----
            sub_path = input_entries[idx][1]
            sub_native_w, sub_native_h = None, None
            try:
                _probe = self.get_video_resolution(sub_path)
                if _probe:
                    sub_native_w, sub_native_h = _probe
            except Exception:
                pass

            # 主视频 W/H（覆盖粘贴命令时可能没探测到的情况）
            if self.video_resolution and self.video_resolution[0] and self.video_resolution[1]:
                main_w, main_h = self.video_resolution
            else:
                _mp = self.get_video_resolution(input_entries[0][1])
                main_w, main_h = (_mp if _mp else (1, 1))

            # ---- 构建 filter_parts ----
            filter_parts = track.filter_parts[:]
            # delogo 排最前（去水印在裁剪/旋转/缩放之前，坐标按原始帧，与主程序一致）
            if track.delogo_enabled_var.get():
                _dx = track.delogo_x.get().strip() or "0"
                _dy = track.delogo_y.get().strip() or "0"
                _dw = track.delogo_w.get().strip() or "100"
                _dh = track.delogo_h.get().strip() or "100"
                filter_parts.insert(0, f"delogo=x={_dx}:y={_dy}:w={_dw}:h={_dh}")
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

            # ---- 取本次生效的 scale 字符串，用于下面求子视频渲染尺寸 ----
            active_scale = None
            for _p in filter_parts:
                if _p.startswith('scale='):
                    active_scale = _p  # 用最后一个 scale 的尺寸

            # ---- 子视频渲染后宽高（用于 sendcmd 数值求值）----
            sub_w, sub_h = sub_native_w, sub_native_h
            if sub_w and sub_h and active_scale:
                sub_w, sub_h = self._apply_scale_dims(sub_w, sub_h, active_scale)

            # spin 开启时 overlay 输入 w/h 是对角线正方形（与主程序旋转盒一致）
            try:
                _sp_val = float(track.spin_speed_var.get())
            except (ValueError, TypeError):
                _sp_val = 60.0
            spin_on = bool(track.spin_enabled_var.get()) and _sp_val != 0
            # 静态旋转（filter_parts 里的 rotate= 非持续旋转）同样输出 hypot 正方形画布
            # （rotate=..:ow=hypot(iw,ih):oh=hypot(iw,ih):c=black@0），blend 区域必须用对角线
            has_static_rotate = any(
                p.startswith('rotate=') and '*PI/180*t' not in p for p in filter_parts)
            if (spin_on or has_static_rotate) and sub_w and sub_h:
                _d = int(round((sub_w * sub_w + sub_h * sub_h) ** 0.5))
                sub_w = sub_h = _d

            # ---- 构建滤镜图：delogo 已经在 filter_parts 里；
            # mask 在原始帧上（filter_parts 之前），子图：split→format=gray,drawbox→alphamerge
            cur_input = sub_stream

            if track.mask_enabled_var.get():
                _mx = track.mask_x.get().strip() or "0"
                _my = track.mask_y.get().strip() or "0"
                _mw = track.mask_w.get().strip() or "100"
                _mh = track.mask_h.get().strip() or "100"
                _mode = track.mask_mode.get() if track.mask_mode.get() in ("inside", "outside") else "outside"
                if _mode == "inside":
                    _draw = (f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill,"
                             f"drawbox=x={_mx}:y={_my}:w={_mw}:h={_mh}:color=black:t=fill")
                else:
                    _draw = (f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill,"
                             f"drawbox=x={_mx}:y={_my}:w={_mw}:h={_mh}:color=white:t=fill")
                _mka, _mkm, _mkmsk, _mkout = f"mk{idx}a", f"mk{idx}m", f"mk{idx}msk", f"mk{idx}out"
                filter_chain.append(f"{cur_input}split=2[{_mka}][{_mkm}]")
                filter_chain.append(f"[{_mkm}]format=gray,{_draw}[{_mkmsk}]")
                filter_chain.append(f"[{_mka}][{_mkmsk}]alphamerge[{_mkout}]")
                cur_input = f"[{_mkout}]"

            # 预处理滤镜（delogo、scale、crop、rotate=静态角度 等）
            if filter_parts:
                filter_str = ','.join(filter_parts)
                filter_chain.append(f"{cur_input}{filter_str}[{sub_temp_label}]")
                cur_input = f"[{sub_temp_label}]"

            # ---- 计算总周期 ----
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

            # ---- enable 表达式 ----
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

            # ---- 决定是否需要 rgba ----
            # 透明度 <1.0、遮罩、旋转 任一开启都需要 alpha 通道
            try:
                _av = float(track.alpha_var.get())
            except (ValueError, TypeError):
                _av = 1.0
            need_rgba = (
                (track.use_alpha_var.get() and 0.0 <= _av < 1.0)
                or track.mask_enabled_var.get()
                or spin_on
            )
            if need_rgba:
                filter_chain.append(f"{cur_input}format=rgba[{sub_temp_label}_rgba]")
                cur_input = f"[{sub_temp_label}_rgba]"

            # ---- alpha 透明度（在遮罩之后 / 旋转之前，与主程序顺序一致）----
            if track.use_alpha_var.get() and 0.0 <= _av < 1.0:
                _alpha_label = f"v_alpha_{idx}"
                filter_chain.append(f"{cur_input}colorchannelmixer=aa={_av:.2f}[{_alpha_label}]")
                cur_input = f"[{_alpha_label}]"

            # ---- 持续旋转（需要 rgba；用对角线正方形画布）----
            if spin_on:
                _spin_label = f"v_spin_{idx}"
                filter_chain.append(
                    f"{cur_input}rotate=angle='{_sp_val}*PI/180*t':"
                    f"ow='hypot(iw,ih)':oh='hypot(iw,ih)':c=black@0[{_spin_label}]"
                )
                cur_input = f"[{_spin_label}]"

            # ---- 构建 overlay（sendcmd 模式：位置由命令文件驱动）----
            blend_mode = str(getattr(track, "blend_mode", "normal") or "normal").strip().lower()
            is_blend = blend_mode not in ("", "normal")
            use_sc = self.use_sendcmd_var.get() and has_trajectory

            if is_blend:
                # ================= 区域化 blend（与主程序 _make_blend_region 同构） =================
                # 区域尺寸 = 子视频渲染尺寸（spin/静态旋转已是对角线正方形），偶数化
                _bw, _bh = int(sub_w or 0), int(sub_h or 0)
                if _bw < 2 or _bh < 2:
                    messagebox.showerror(
                        "错误", f"轨道 {track['text']} 无法确定子视频尺寸（blend 需要精确区域），"
                                f"请确认缩放尺寸有效或检查视频可读性")
                    return
                if _bw % 2:
                    _bw -= 1
                if _bh % 2:
                    _bh -= 1
                _bw = max(2, _bw); _bh = max(2, _bh)
                # 唯一 label / 别名（多轨道不撞名）
                _cr = f"cr{idx}"
                _mc, _ap, _rg, _ae, _br, _bx = (f"b{idx}{x}" for x in ("mc", "ap", "rg", "ae", "br", "bx"))
                # 主区域来源：区域隔离时用 bl_base{_blend_seq}（原始帧副本，重叠区互不干涉），
                # 否则用当前合成主干（单 blend 直接与当前画面混合）
                if use_regional:
                    _src = f"[bl_base{_blend_seq}]"
                else:
                    _src = current_base
                _blend_seq += 1

                if has_trajectory and use_sc:
                    # ---- sendcmd：crop 窗口与 overlay 位置由同一份命令文件同步驱动 ----
                    if loop:
                        vdur = self.get_video_duration(input_entries[0][1])
                        horizon = vdur if (vdur and vdur > 0) else max(global_duration, delay_val + 0.001)
                    else:
                        horizon = delay_val + total_period
                    if horizon <= 0:
                        horizon = max(global_duration, 0.001)
                    cmdfile = self._write_sendcmd_file(track, x_expr, y_expr, horizon, idx, base_dir,
                                                        main_w, main_h, _bw, _bh,
                                                        overlay_name=f"overlay@{ov_alias}",
                                                        crop_name=f"crop@{_cr}")
                    sendcmd_files.append(cmdfile)
                    sc_label = f"{sub_temp_label}_sc"
                    filter_chain.append(f"{cur_input}sendcmd=f='{cmdfile}'[{sc_label}]")
                    cur_input = f"[{sc_label}]"
                    # crop 初始占位 0:0（sendcmd 首命令 t=0 即覆盖；crop 的 x/y 由命令文件按 iw/ih 驱动）
                    filter_chain.append(f"{_src}crop@{_cr}={_bw}:{_bh}:0:0,format=rgb24[{_mc}]")
                    overlay_opts = "x=-1:y=-1"
                elif has_trajectory:
                    # ---- 表达式：crop 用 iw/ih 变体（W/H→iw/ih + 独立 w/h→区域尺寸），overlay 用 W/H 原样 ----
                    # （正则 \bw\b/\bh\b 防误伤 iw/ih 里的 w/h，与主程序 _blend_crop_exprs 一致）
                    xc = re.sub(r"\bw\b", str(_bw), x_expr.replace("W", "iw").replace("H", "ih"))
                    xc = re.sub(r"\bh\b", str(_bh), xc)
                    yc = re.sub(r"\bw\b", str(_bw), y_expr.replace("W", "iw").replace("H", "ih"))
                    yc = re.sub(r"\bh\b", str(_bh), yc)
                    filter_chain.append(f"{_src}crop={_bw}:{_bh}:x='{xc}':y='{yc}',format=rgb24[{_mc}]")
                    overlay_opts = f"x='{x_expr}':y='{y_expr}'"
                else:
                    # ---- 静态位置：基准坐标求值（可能含 W/H/w/h 表达式）+ clamp 到画布内 ----
                    try:
                        _sxv = self._eval_axis_expr(x_expr, 0, main_w, main_h, _bw, _bh)
                        _syv = self._eval_axis_expr(y_expr, 0, main_w, main_h, _bw, _bh)
                    except Exception:
                        _sxv, _syv = 0, 0
                    _sxv = int(max(0, min(_sxv, main_w - _bw)))
                    _syv = int(max(0, min(_syv, main_h - _bh)))
                    filter_chain.append(f"{_src}crop={_bw}:{_bh}:{_sxv}:{_syv},format=rgb24[{_mc}]")
                    overlay_opts = f"{_sxv}:{_syv}"

                # ---- 子视频采样 + RGBA 剥离（blend 纯 RGB 空间运算，alpha 单独提取后合并回）----
                filter_chain.append(f"{cur_input}crop={_bw}:{_bh}:0:0,format=rgba,split=2[{_ap}][{_rg}]")
                filter_chain.append(f"[{_ap}]alphaextract[{_ae}]")
                filter_chain.append(f"[{_rg}]format=rgb24[{_rg}b]")
                filter_chain.append(f"[{_mc}][{_rg}b]blend=all_mode={blend_mode}[{_br}]")
                filter_chain.append(f"[{_br}][{_ae}]alphamerge,format=rgba[{_bx}]")
                # blend overlay 不带 enable（与主程序一致：blend 按像素重算，不响应显示时段）
                overlay = f"{current_base}[{_bx}]overlay@{ov_alias}={overlay_opts}:shortest=1{out_stream}"
                filter_chain.append(overlay)
                current_base = out_stream
                output_counter += 1
                continue

            # ---- 普通叠加（既有逻辑）----
            if use_sc:
                # 计算采样时间跨度 horizon：循环时覆盖整段主视频（探测主视频时长，
                # 让轨迹在整段视频里按周期复现）；不循环时只覆盖"延迟+单周期"这一段。
                if loop:
                    vdur = self.get_video_duration(input_entries[0][1])
                    horizon = vdur if (vdur and vdur > 0) else max(global_duration, delay_val + 0.001)
                else:
                    horizon = delay_val + total_period
                if horizon <= 0:
                    horizon = max(global_duration, 0.001)
                cmdfile = self._write_sendcmd_file(track, x_expr, y_expr, horizon, idx, base_dir,
                                                    main_w, main_h, sub_w or 0, sub_h or 0,
                                                    overlay_name=f"overlay@{ov_alias}")
                sendcmd_files.append(cmdfile)
                sc_label = f"{sub_temp_label}_sc"
                filter_chain.append(f"{cur_input}sendcmd=f='{cmdfile}'[{sc_label}]")
                cur_input = f"[{sc_label}]"
                overlay_opts = f"x=-1:y=-1"
            else:
                overlay_opts = f"x='{x_expr}':y='{y_expr}'"
            if enable_expr != "1":
                overlay_opts += f":enable='{enable_expr}'"
            # 用 overlay@ov{idx}=... 给每个轨道唯一别名，避免 sendcmd 多轨道同名撞车
            overlay = f"{current_base}{cur_input}overlay@{ov_alias}={overlay_opts}:shortest=1{out_stream}"
            filter_chain.append(overlay)

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

        self._last_cmd = {
            'ffmpeg_exe': ffmpeg_exe,
            'input_entries': input_entries,
            'final_filter': final_filter,
            'map_parts': map_parts,
            'output_file': output_file,
            'full_cmd': final_cmd,
            'sendcmd_files': sendcmd_files,
            'base_dir': base_dir,
        }

        self.cmd_text.delete("1.0", tk.END)
        self.cmd_text.insert(tk.END, final_cmd)
    # ---------- 运行命令（长命令自动落脚本文件，避免 cmd 长度限制） ----------
    def run_command(self):
        # 先按当前界面配置重新生成命令（预览框照常更新）
        self.generate_command()
        comp = getattr(self, '_last_cmd', None)
        if not comp:
            return

        full_cmd = comp['full_cmd']
        # 命令（含滤镜串）超过阈值时，把 -filter_complex 内容写入脚本文件，
        # 改用 ffmpeg 的 -filter_complex_script 读取，绕过命令行长度限制
        use_script = len(full_cmd) > 25000
        if use_script:
            out_dir = os.path.dirname(os.path.normpath(comp['output_file']))
            filter_file = os.path.normpath(os.path.join(out_dir, "ff_filter_complex.txt"))
            try:
                with open(filter_file, 'w', encoding='utf-8') as f:
                    f.write(comp['final_filter'])
            except Exception as e:
                messagebox.showerror("写入失败", f"无法写入滤镜脚本文件：\n{e}")
                return
            comp = dict(comp)
            comp['filter_file'] = filter_file

        sc_files = comp.get('sendcmd_files') or []
        if sc_files:
            # sendcmd 模式：自由路径位置由命令文件驱动，不存在单表达式段数/命令长度限制，
            # 不再提示"未超过阈值"之类无意义的信息
            info = (f"sendcmd 模式：自由路径由 {len(sc_files)} 个位置命令文件驱动，"
                    f"不受单表达式段数上限与命令长度限制。\n")
            if use_script:
                info += (f"滤镜串较长（{len(full_cmd)} 字符），已自动写入脚本文件：{filter_file}\n")
        elif use_script:
            info = (f"命令长度 {len(full_cmd)} 字符，已超过 25000，已自动改用脚本文件方式运行。\n"
                    f"滤镜串已保存到：{filter_file}\n")
        else:
            info = f"命令长度 {len(full_cmd)} 字符，未超过阈值，直接运行。\n"

        self._run_ffmpeg(comp, use_script, info)

    def _run_ffmpeg(self, comp, use_script, info):
        # 用参数列表（argv）方式构造命令，避免引号与命令行长度问题
        ffmpeg_exe = comp['ffmpeg_exe'].replace('\\', '/')
        argv = [ffmpeg_exe, '-y', '-fflags', '+genpts']
        for opts, path in comp['input_entries']:
            if opts:
                argv.extend(opts)
            argv.extend(['-i', path])
        if use_script:
            argv.extend(['-filter_complex_script', comp['filter_file']])
        else:
            argv.extend(['-filter_complex', comp['final_filter']])
        argv.extend(comp['map_parts'])
        argv.append(comp['output_file'])

        # 日志窗口
        log_win = tk.Toplevel(self.root)
        log_win.title("FFmpeg 运行日志")
        log_win.geometry("760x460")
        log_win.transient(self.root)
        log_win.update_idletasks()
        px = self.root.winfo_x() + (self.root.winfo_width() - 760) // 2
        py = self.root.winfo_y() + (self.root.winfo_height() - 460) // 2
        log_win.geometry(f"+{px}+{py}")

        top_frame = ttk.Frame(log_win)
        top_frame.pack(fill="x", padx=8, pady=(8, 2))
        status_label = ttk.Label(top_frame, text="状态：运行中…", foreground="blue")
        status_label.pack(side="left")
        ttk.Button(top_frame, text="关闭", command=log_win.destroy).pack(side="right", padx=4)

        info_text = tk.Text(log_win, height=3, font=("Microsoft YaHei", 9), wrap="word")
        info_text.pack(fill="x", padx=8, pady=2)
        info_text.insert(tk.END, info + f"输出文件：{comp['output_file']}\n")
        info_text.config(state="disabled")

        log_text = tk.Text(log_win, font=("Consolas", 9), wrap="word")
        scroll = ttk.Scrollbar(log_win, orient="vertical", command=log_text.yview)
        log_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        log_text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=(2, 8))

        def append_log(line):
            log_text.insert(tk.END, line)
            log_text.see(tk.END)

        def set_status(text, color):
            status_label.config(text=f"状态：{text}", foreground=color)

        def worker():
            try:
                proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        creationflags=subprocess.CREATE_NO_WINDOW,
                                        encoding='utf-8', errors='ignore', bufsize=1,
                                        cwd=comp.get('base_dir'))
            except Exception as e:
                self.root.after(0, lambda: append_log(f"启动失败：{e}\n"))
                self.root.after(0, lambda: set_status("启动失败", "red"))
                return
            try:
                for line in iter(proc.stdout.readline, ''):
                    if not line:
                        break
                    self.root.after(0, lambda l=line: append_log(l))
            except Exception:
                pass
            proc.stdout.close()
            rc = proc.wait()
            self.root.after(0, lambda: append_log(f"\n===== 进程结束，返回码：{rc} =====\n"))
            if rc == 0:
                self.root.after(0, lambda: set_status("完成（成功）", "green"))
                self.root.after(0, lambda: append_log(f"输出文件已生成：{comp['output_file']}\n"))
            else:
                self.root.after(0, lambda: set_status(f"失败（返回码 {rc}）", "red"))

        threading.Thread(target=worker, daemon=True).start()

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
