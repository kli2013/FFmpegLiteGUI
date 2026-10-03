# 撤销 / 重做 系统说明

本工具内置两套相互独立的撤销机制：

1. **主窗口撤销/重做引擎** —— 覆盖转换页、封装合并页、任务队列的高危操作，支持**多步历史 + 重做 + 页面归属**（每个页面对应独立栈，跨页互不覆盖）。
2. **对话框内自包含栈** —— 章节编辑器、水印编辑器、分段编辑器各自持有独立栈，**关窗即弃**，不污染主窗口历史。

> 源码文件：`FFmpeg简易转换合并 safe5.pyw`（base 版）。本文档以**方法名 / scope 名 / 按钮文字**为稳定锚点（行号会随编辑漂移，不在此罗列）。

---

## 一、主窗口撤销/重做引擎

### 1. 数据结构

在 `FFmpegBatchGUI.__init__` 中初始化：

```python
self._undo_stacks = {"convert": [], "merge": [], "tasks": [], "chapter": [], "watermark": []}
self._redo_stacks = {k: [] for k in self._undo_stacks}
self._active_undo_scope = None   # 当前页面对应的 scope（共享栏按钮据此刷新）
```

- 五个 scope：`convert`（视频转码页）、`merge`（封装合并页）、`tasks`（任务队列）、`chapter`/`watermark`（占位，实际未接入主引擎，由对话框自包含栈接管）。
- 每个 scope 一套独立的「撤销栈 + 重做栈」，互不干扰。

### 2. 引擎 API

| 方法 | 职责 |
|---|---|
| `_push_history(scope, label, undo_fn, redo_fn)` | 登记一次可撤销操作：把 `{label, undo_fn, redo_fn}` 压入对应 scope 的撤销栈，**并清空同 scope 的重做栈**（标准编辑语义：新操作使重做失效）。不改动 `_active_undo_scope`。 |
| `_do_undo(scope=None)` | 执行撤销：取 scope（默认当前活动页）栈顶条目，调用其 `undo_fn` 还原前态，条目移入重做栈。失败会放回栈顶并弹错，数据安全不丢。 |
| `_do_redo(scope=None)` | 执行重做：取 scope 重做栈顶条目，调用 `redo_fn` 重放后态，移回撤销栈。 |
| `_refresh_undo_buttons()` | 按当前活动 scope 刷新共享栏按钮；同时独立刷新任务队列工具栏按钮。栈空则按钮置灰。 |
| `_on_main_tab_changed(event=None)` | 主 notebook 切页回调，重映射 `_active_undo_scope`（视频转码页→`convert` / 封装合并页→`merge` / 其它→`None`），并刷新按钮。绑定在 `<<NotebookTabChanged>>` 上。 |

撤销 = `restore(前态)`；重做 = `restore(后态)`。引擎只存「前后态两个闭包」，零额外状态逻辑。

### 3. 快照机制（还原粒度）

不同页面用不同的整页状态字典做快照，保证还原精确：

- **转换页**：`_build_convert_state_dict()` 拍整页参数 → 套用/导入后拍后态供重做；删除预设走 `preset_manager.load_all()` 整库快照。
- **封装合并页**：`_build_merge_state_dict()` 拍整页轨道列表（含主视频路径、各轨 `enc_settings`）。
- **任务队列**：`_snapshot_tasks()` 拍任务列表；还原时判 `_after is not None` 防 `None` 入栈。

所有登记点都在操作**前**拍前态、`_push_history` 时把「前态闭包 + 后态闭包」一并传入，避免二次计算漂移。

### 4. 页面归属（scope 绑定）

- 共享信息栏的「↶ 撤销 / ↷ 重做」按钮跟随当前页 scope：在视频转码页只显示/操作 `convert` 栈，切到封装合并页自动切到 `merge` 栈。
- 任务队列工具栏有**独立**的「↶ 撤销 / ↷ 重做」按钮，固定 `scope="tasks"`，不占用共享栏，即使焦点不在任务页也能操作。

### 5. UI 按钮位置

| 按钮 | 说明 |
|---|---|
| 共享栏 `↶ 撤销` | `command=self._do_undo`（取当前活动 scope） |
| 共享栏 `↷ 重做` | `command=self._do_redo` |
| 任务队列工具栏 `↶ 撤销` | `command=lambda: self._do_undo("tasks")` |
| 任务队列工具栏 `↷ 重做` | `command=lambda: self._do_redo("tasks")` |

按钮文字动态显示下一步动作，例如 `↶ 撤销：套用预设`、`↷ 重做：替换素材(轨道2)`；栈空时显示纯 `↶ 撤销` / `↷ 重做` 并置灰。

### 6. 已登记的操作清单（入口总表）

| scope | 操作 | 快照点（前态） | 备注 |
|---|---|---|---|
| `convert` | 套用预设 | `_build_convert_state_dict()` | 整页参数覆盖 |
| `convert` | 删除预设 | `preset_manager.load_all()` 整库 | 删除后还原选中名 |
| `convert` | 导入预设库 | 整库 `deepcopy` | `askyesnocancel`：是=替换/否=合并/取消=放弃 |
| `convert` | 导入项目 | `_build_convert_state_dict()` | 整页参数覆盖 |
| `convert` | 编辑视频水印 | 编辑器打开前 `_wm_edit_undo_snap` | 应用写回后与快照比对（含自适应时长连锁改动）；仅主界面模式 |
| `convert` | 应用水印模板 | `load_wm_preset` 写入前拍 | 模板整组覆盖视频+文字水印 |
| `convert` | 载入水印文件 | `browse_wm` 选文件后 set 前 | 经 `_on_wm_path_changed` 连锁（enabled/duration）一并还原 |
| `convert` | 清除水印 | `clear_wm` 清空前拍 | 路径已空时判等守卫不入栈 |
| `tasks` | 移除任务 | `_snapshot_tasks()` | 失败静默降级为不登记 |
| `tasks` | 清空任务 | 同上 | 同上 |
| `tasks` | 清除已完成任务 | 同上 | 同上 |
| `tasks` | 用命令模板更新任务 | 同上 | 整页参数同步到选中任务（2026-09-29 补登记） |
| `tasks` | 用命令模板更新全部任务 | 同上 | 同上（跳过流提取自定义任务） |
| `tasks` | 应用水印到选中任务 | 同上 | 批量水印盖印，见下方「批量水印」说明 |
| `tasks` | 应用水印到全部任务 | 同上 | 同上 |
| `merge` | 加载项目 | `_build_merge_state_dict()` | 整页轨道覆盖 |
| `merge` | 排序轨道 | 前后快照判等 | 重排整条轨道列表 |
| `merge` | 添加视频/图片 | 前后快照判等 | 添加后登记 |
| `merge` | 编辑轨道 | 前后快照判等 | 整块覆盖 `enc_settings` |
| `merge` | 替换素材 | 前后快照判等 | 含主视频路径 |
| `merge` | 删除轨道 | `_build_merge_state_dict()` | — |
| `merge` | 清空轨道 | 同上 | — |
| `merge` | 添加其他轨 | 前后快照判等 | `f"添加{expected}轨道"` |

> 对 merge 系列操作，采用「操作前拍 `_undo_snap` → 操作后拍 `_after_snap` → 若 `_undo_snap != _after_snap` 才入栈」的判等守卫，避免「点了但没变化」产生空撤销项。

### 转换页水印撤销的边界

- **仅主界面模式登记**：判据 `watermark_dict is app.watermark_settings`。队列任务编辑窗口里改水印写的是任务自身设置，不入主窗历史。
- **路径框手动打字不登记**：`wm_path_var` 的 trace 每敲一键触发一次，登记会刷屏撤销栈；只有按钮类一次性动作（浏览/清除/模板/编辑器应用）才登记。
- **编辑视频水印的后态含连锁改动**：应用后会触发自适应时长自动探测（回写 `duration`），登记点在方法末尾，保证 undo→redo 往返状态一致。

### 批量水印盖印（任务队列右键）

入口：任务列表右键菜单「应用当前水印到选中任务 / 应用当前水印到全部任务」（`_apply_watermark_to_tasks`）。

- **语义**：把主界面当前水印状态整体照搬到任务（与加任务时拷贝全局水印同构）；视频水印整体替换，自适应基准 `base_width/base_height` 按各任务**自己的输入视频**重算。
- **文字水印智能跳过**：主界面文字水印无内容（未启用且文本为空、items 列表为空）时**不盖**文字水印，避免把任务里已单独开启的文字水印抹掉；有内容则与视频水印一起盖。
- 流提取生成的自定义任务自动跳过；盖印后重新生成任务命令，撤销走 `tasks` 快照。

---

## 二、对话框内自包含撤销栈（关窗即弃）

三类对话框不接入主窗口引擎，各自在对象内部持有独立栈。对话框关闭、对象销毁时栈随之消失，**绝不污染主窗口历史**。

### 通用模式

每个对话框类在 `__init__` 中声明：

```python
self._xxx_undo_stack = []
self._xxx_redo_stack = []
self._xxx_pending_before = None   # 编辑前态快照
```

提供统一方法族（以 `xxx` 为前缀区分）：

| 方法 | 职责 |
|---|---|
| `_xxx_snapshot()` | 取当前列表/条目的完整快照（深拷贝）。 |
| `_xxx_begin_edit()` | 在执行一个会改动的动作**前**记录前态到 `_xxx_pending_before`。 |
| `_xxx_push(label)` | 动作**后**取后态，若 `before == after` 则不入栈（防空项）；否则压入撤销栈并清空重做栈。 |
| `_xxx_do_undo()` | 取撤销栈顶，restore 前态入重做栈。 |
| `_xxx_do_redo()` | 取重做栈顶，restore 后态回撤销栈。 |
| `_xxx_refresh_undo_buttons()` | 刷新对话框内「撤销 / 重做」按钮文字与可用态。 |

按钮统一为「撤销」「重做」一对，`state="disabled"` 初始，位于对话框底部操作区。

### 1. 水印编辑器 `TextWatermarkDialog`

- 按钮：`_tw_undo_btn`、`_tw_redo_btn`，位于水印项列表操作区。
- 方法族：`_tw_snapshot` / `_tw_begin_edit` / `_tw_push` / `_tw_after_restore` / `_tw_do_undo` / `_tw_do_redo` / `_tw_refresh_undo_buttons`。
- 覆盖动作（列表级增删移）：`_add_tw_item` / `_del_tw_item` / `_move_tw_item`。
- 还原粒度：单个水印项列表（文本/位置/样式等），不触碰其它 UI 状态。

### 2. 分段编辑器 `SegmentEditor`

- 按钮：`_seg_undo_btn`、`_seg_redo_btn`，位于操作区，插在「编辑」按钮前。
- 方法族：`_seg_snapshot` / `_seg_begin_edit` / `_seg_push` / `_seg_do_undo` / `_seg_do_redo` / `_seg_refresh_undo_buttons`。
- 覆盖动作：`add_segment_with_time` / `add_segment` / `delete_selected` / `move_up` / `move_down` / `clear_all`。
- **注意**：随机抽段功能有**独立**的撤销通道（`_rnd_backup` 快照、`_undo_random_pick` 方法、对应 `rnd_undo_btn`），与分段列表栈分离，二者互不串扰。

### 3. 章节编辑器 `ChapterEditor`

- 按钮：`_chapter_undo_btn`、`_chapter_redo_btn`，位于底部，插在「应用 / 取消」前。
- 方法族：`_chapter_snapshot` / `_chapter_begin_edit` / `_chapter_push` / `_chapter_do_undo` / `_chapter_do_redo` / `_chapter_refresh_undo_buttons`。
- 覆盖动作：
  - `add_row` / `delete_row` / `move_row`（行级增删移）；
  - `on_double_click`（双击进入单元格编辑：**编辑前** `_chapter_begin_edit`，单元格提交刷新后 `_chapter_push`）；
  - `import_file`（导入章节文件，前后快照判等入栈）。

---

## 三、行为边界与注意事项

- **两套机制完全独立**：对话框栈是对象属性，只在对话框生命周期内存活；主窗口栈按 scope 持久于应用运行期。关掉章节/水印/分段对话框后，其撤销历史一并丢弃。
- **失败安全**：`_do_undo` / `_do_redo` 捕获异常时，会把条目放回原栈顶并弹错误框，不会因还原失败而丢失数据或清空历史。
- **空操作不入栈**：主窗口 merge 系列与对话框均采用「前态==后态则跳过」守卫，单纯点一下但没变化的操作不产生撤销项。
- **不覆盖的场景**：实时预览、播放、波形定位、纯滚动浏览等无状态变更操作不登记撤销（这些不是「会丢数据」的高危动作）。
- **预设库撤销会落盘**：删除/导入预设走 `preset_manager.replace_all` 原子写，撤销时可真正恢复磁盘上的 `ffmpeg_presets.json`，还原/重做均一致。

---

## 四、验证

- `py_compile` 通过（无语法错误）。
- 无头逻辑测试（`$TEMP\_audit_dialog_undo.py`，AST 抽取真实方法体）：
  - ChapterEditor 自包含栈：PASS
  - SegmentEditor 自包含栈：PASS
  - TextWatermarkDialog 自包含栈：PASS
- 主窗口引擎（多步+重做 / scope 独立互不覆盖 / 按钮按 scope 刷新 / 失败放回可重试）此前 4 项测试全过。
