-- ============================================================
-- multi_cut.lua - 视频片段标记与切割工具（增强版）
-- ============================================================
-- 配置方法（在 script-opts/multi_cut.conf 中）：
--   ffmpeg_path=D:\ffmpeg\bin\ffmpeg.exe
--   log_dir=D:\cut_logs
--   use_bom=yes
--   prefer_copy=yes
--   enable_external_copy=yes   （控制非标记模式下 n 键是否被脚本占用）
--   log_enabled=yes            （是否写入日志文件，默认 yes）
--   keybind_toggle=Ctrl+m      （切换标记模式，始终全局有效）
--   keybind_n=n                （标记/复制时间）
--   keybind_cut=c              （常规切割：优先无损复制，失败回退转码）
--   keybind_transcode=t        （精确转码：直接使用 libx265 CRF 28 编码）
--   keybind_export=Ctrl+n      （导出时间参数，仅标记模式内）
--   keybind_exit=Esc           （退出标记模式，仅标记模式内）
--   osd_font_size=24           （持久 OSD 字体大小）
-- ============================================================

-- 日志输出内容说明（按操作模式）
-- 
-- 1. 常规无损切割模式（对应 `keybind_cut`，默认 `c`）
--    - 若启用 `prefer_copy`（默认 true）：
--      尝试无损复制：
--        成功 → 记录一条：
--          [执行成功(无损)] <完整 ffmpeg 命令>
--        失败 → 自动回退转码：
--          转码成功 → 记录一条：
--            [执行成功(转码)] <完整 ffmpeg 命令>
--          转码失败 → 记录一条：
--            [执行失败(转码)] stderr: <错误信息>
--    - 无论成功失败会加一条精确转码模式的<完整 ffmpeg 参考命令> 方便后期手动精确转码
-- 
-- 2. 精确转码模式（对应 `keybind_transcode`，默认 `t`）
--    - 强制使用 `libx265 crf 28` 转码，不尝试无损。
--    - 每个片段：
--        成功 → 记录一条：
--          [执行成功(精确转码)] <完整 ffmpeg 命令>
--        失败 → 记录一条：
--          [执行失败(精确转码)] stderr: <错误信息>
-- 
-- 3. 导出时间参数模式（对应 `keybind_export`，默认 `Ctrl+n`）
--    - 不执行切割，仅为每个有效片段生成一条建议的精确转码命令。
--    - 每条格式：
--         [精确命令 i] <完整 ffmpeg 命令>
--      （其中 i 为片段序号）
--    - 同时，时间参数（`-ss` 和 `-t`）会合并复制到系统剪贴板（仅时间值，不含其他参数）。
-- 总之日志里会尽可能的保存 FFmpeg 命令供后续重复使用
-- 不想记录的 设置 log_enabled = false
local utils = require 'mp.utils'
local options = require 'mp.options'
local assdraw = require 'mp.assdraw'

-- ====================== 配置选项 ======================
local o = {
    ffmpeg_path = 'ffmpeg.exe',   --指定 FFmpeg 可执行文件的完整路径。如果 FFmpeg 已在系统 PATH 中，可只写文件名。
    log_dir = '',                 -- 日志文件 cutlog.txt 的存放目录。如果不设置或设为空，则日志会与源文件放在同一文件夹。
    use_bom = true,
    prefer_copy = true,
    enable_external_copy = true,  -- true: 非标记模式下 n 键复制时间；false: 不占用 n 键
    log_enabled = true,           -- 日志开关
    -- ====== 快捷键集中配置 ======
    keybind_toggle = "Ctrl+m",    -- 切换标记模式（始终全局有效）
    keybind_n      = "n",         -- 标记/复制时间
    keybind_cut    = "c",         -- 常规切割（优先无损）
    keybind_transcode = "t",      -- 精确转码（直接编码）
    keybind_export = "Ctrl+n",    -- 导出时间参数     供 FFmpegLiteGUI 的分段拼接导入用
    keybind_exit   = "Esc",       -- 退出标记模式
    -- OSD 设置
    osd_font_size = 24,
}
options.read_options(o, 'multi_cut')

-- ====================== 状态变量 ======================
local marking_mode = false
local segments = {}
local current_segment_start = nil
local temp_message = ""
local temp_timer = nil

-- 绑定名称常量
local EXTERNAL_BIND_NAME = "external_copy_time"
local INTERNAL_BIND_NAME = "mark_current_time"

-- ====================== 持久 OSD 绘制 ======================
local function update_osd()
    if not marking_mode then
        mp.set_osd_ass(0, 0, "")
        return
    end

    local window_w, window_h = mp.get_osd_size()
    local ass = assdraw.ass_new()
    ass:new_event()
    ass:append("{\\an7}")  -- 左上对齐
    ass:pos(10, 10)
    ass:append("{\\fs" .. tostring(o.osd_font_size) .. "}")

    -- 第一行：快捷键提示
    local hint = string.format("标记模式  [%s:标记] [%s:常规切割] [%s:精确转码] [%s:导出] [%s:退出]",
        o.keybind_n, o.keybind_cut, o.keybind_transcode, o.keybind_export, o.keybind_exit)
    ass:append(hint .. "\\N")

    -- 第二行：标记状态（动态）
    local status = ""
    if #segments == 0 then
        status = "尚未标记任何片段"
    else
        status = string.format("已标记 %d 个片段", #segments)
        local last = segments[#segments]
        if last.start and last.end_ then
            status = status .. string.format("  (最后: %.3fs - %.3fs)", last.start, last.end_)
        elseif last.start and not last.end_ then
            status = status .. string.format("  (当前起点: %.3fs)", last.start)
        end
    end
    ass:append(status .. "\\N")

    -- 第三行：临时消息（如果有）
    if temp_message ~= "" then
        ass:append(temp_message)
    end

    mp.set_osd_ass(window_w, window_h, ass.text)
end

-- 显示临时消息（几秒后自动清除）
local function show_temp_message(msg, duration)
    temp_message = msg
    update_osd()
    if temp_timer then
        temp_timer:stop()
        temp_timer = nil
    end
    temp_timer = mp.add_timeout(duration or 2, function()
        temp_message = ""
        update_osd()
        temp_timer = nil
    end)
end

-- ====================== 日志写入 ======================
local function write_cut_log(content, log_file_path)
    if not o.log_enabled then
        return   -- 日志已禁用，直接返回
    end
    if not log_file_path then return end
    local f = io.open(log_file_path, 'a')
    if not f then
        mp.msg.warn("无法写入日志文件: " .. log_file_path)
        return
    end
    if o.use_bom then
        local size = f:seek("end")
        if size == 0 then
            f:write('\xef\xbb\xbf')
        end
    end
    f:write(content .. '\n')
    f:flush()
    f:close()
end

-- ====================== 章节标记 ======================
local function update_chapter_marks()
    local chapters = {}
    for i, seg in ipairs(segments) do
        if seg.start then
            table.insert(chapters, {
            -- 为了在 uosc 进度条上高亮显示每个标记的片段区间，
            -- 我们将章节标题前缀设为 "op"，以匹配 uosc 内置的 openings 规则。
            -- 同时需要在 uosc.conf 中添加：
            --   chapter_ranges=openings:0000FF
            -- 这样每个从该标记点到下一个标记点的区域就会显示为彩色。
            -- 上一个结尾点时间 <= 下一个起始点时间时，显示区域可能出错，请忽略
            --  Seg%d 开始 %.3fs
                title = string.format("op Seg%d %.3fs", i, seg.start),
                time = seg.start
            })
        end
        if seg.end_ then
            table.insert(chapters, {
            -- Seg%d 结束 %.3fs
                title = string.format("ed Seg%d %.3fs", i, seg.end_),
                time = seg.end_
            })
        end
    end
    mp.set_property_native("chapter-list", chapters)
end

-- ====================== 内部快捷键绑定/解绑 ======================
local function bind_internal_keys()
    mp.add_forced_key_binding(o.keybind_n, INTERNAL_BIND_NAME, mark_current_time)
    mp.add_forced_key_binding(o.keybind_cut, "cut_segments", run_cut)
    mp.add_forced_key_binding(o.keybind_transcode, "transcode_segments", run_cut_transcode)
    mp.add_forced_key_binding(o.keybind_export, "export_times", export_commands_only)
    mp.add_forced_key_binding(o.keybind_exit, "exit_mark", function()
        if marking_mode then toggle_marking_mode() end
    end)
end

local function unbind_internal_keys()
    mp.remove_key_binding(INTERNAL_BIND_NAME)
    mp.remove_key_binding("cut_segments")
    mp.remove_key_binding("transcode_segments")
    mp.remove_key_binding("export_times")
    mp.remove_key_binding("exit_mark")
end

-- ====================== 模式切换 ======================
function toggle_marking_mode()
    if not marking_mode then
        -- 进入标记模式
        if o.enable_external_copy then
            mp.remove_key_binding(EXTERNAL_BIND_NAME)
        end
        marking_mode = true
        segments = {}
        current_segment_start = nil
        temp_message = ""
        update_chapter_marks()
        update_osd()
        bind_internal_keys()
        show_temp_message("已进入标记模式", 2)
    else
        -- 退出标记模式
        marking_mode = false
        segments = {}
        current_segment_start = nil
        temp_message = ""
        update_chapter_marks()
        unbind_internal_keys()
        if o.enable_external_copy then
            mp.add_key_binding(o.keybind_n, EXTERNAL_BIND_NAME, external_copy_time)
        end
        update_osd()  -- 清空 OSD
        show_temp_message("已退出标记模式", 2)
    end
end

-- ====================== 剪贴板复制 ======================
local clipboard_cmd = nil

local function init_clipboard()
    local platform = mp.get_property("platform")
    if platform == "windows" then
        clipboard_cmd = function(text)
            local escaped = text:gsub('"', '\\"'):gsub('\n', '`n')
            utils.subprocess({
                args = { "powershell", "-command", "Set-Clipboard -Value \"" .. escaped .. "\"" },
                cancellable = false
            })
        end
    elseif platform == "linux" then
        local has_xclip = (utils.subprocess({ args = { "which", "xclip" }, cancellable = false }).status == 0)
        local clip_cmd = has_xclip and "xclip -selection clipboard" or "xsel -b -i"
        clipboard_cmd = function(text)
            utils.subprocess({
                args = { "sh", "-c", "echo '" .. text .. "' | " .. clip_cmd },
                cancellable = false
            })
        end
    elseif platform == "darwin" then
        clipboard_cmd = function(text)
            utils.subprocess({
                args = { "sh", "-c", "echo '" .. text .. "' | pbcopy" },
                cancellable = false
            })
        end
    else
        clipboard_cmd = function() end
    end
end
init_clipboard()

local function copy_to_clipboard(text)
    if clipboard_cmd then
        clipboard_cmd(text)
    end
end

-- ====================== 外部复制时间（非标记模式） ======================
function external_copy_time()
    if marking_mode then return end
    local pos = mp.get_property_number("time-pos")
    if pos then
        local hours = math.floor(pos / 3600)
        local minutes = math.floor((pos % 3600) / 60)
        local seconds = pos % 60
        local time_str = string.format("%02d:%02d:%06.3f", hours, minutes, seconds)
        copy_to_clipboard(time_str)
        show_temp_message("已复制时间: " .. time_str, 3)
    else
        show_temp_message("无法获取当前播放时间", 2)
    end
end

-- ====================== 内部标记时间（标记模式） ======================
function mark_current_time()
    if not marking_mode then return end
    local pos = mp.get_property_number("time-pos")
    if not pos then
        show_temp_message("无法获取当前位置", 2)
        return
    end

    if not current_segment_start then
        current_segment_start = pos
        table.insert(segments, { start = pos })
        show_temp_message(string.format("✓ 开始点: %.3f", pos), 2)
    else
        local n = #segments
        segments[n].end_ = pos
        current_segment_start = nil
        show_temp_message(string.format("✓ 结束点: %.3f (片段 %d)", pos, n), 2)
    end
    update_chapter_marks()
    update_osd()
end

-- ====================== 构建命令字符串 ======================
local function need_quote(arg)
    return arg:match("[ \t]") or arg:match('"') or arg == ""
end

local function quote_arg(arg)
    if need_quote(arg) then
        return '"' .. arg:gsub('"', '""') .. '"'
    else
        return arg
    end
end

local function build_ffmpeg_command(ffmpeg_path, args)
    local parts = { quote_arg(ffmpeg_path) }
    for _, a in ipairs(args) do
        table.insert(parts, quote_arg(a))
    end
    return table.concat(parts, " ")
end

-- ====================== 公共函数 ======================
local function get_valid_segments()
    local open_segments = {}
    for i, s in ipairs(segments) do
        if s.start and not s.end_ then
            table.insert(open_segments, i)
        end
    end
    if #open_segments > 0 then
        local warn_msg = string.format("⚠ 有 %d 个片段未标记终点（片段 %s），将被忽略",
            #open_segments, table.concat(open_segments, ", "))
        show_temp_message(warn_msg, 5)
        mp.msg.warn(warn_msg)
    end

    local valid = {}
    for _, s in ipairs(segments) do
        if s.start and s.end_ and s.start < s.end_ then
            table.insert(valid, s)
        end
    end
    return valid
end

-- 获取文件信息：路径、目录、文件名、基础名、扩展名、输出扩展名
local function get_file_info()
    local path = mp.get_property("path")
    if not path or path == "" then
        return nil, "无法获取文件路径"
    end
    local dir, filename = utils.split_path(path)
    if not dir then dir = "" end
    local base = filename:match("(.+)%.[^%.]+$") or "output"
    local ext = filename:match("(%.[^%.]+)$") or ".mp4"
    local out_ext = (ext:lower() == ".ts" or ext:lower() == ".flv") and ".mp4" or ext
    return path, dir, filename, base, ext, out_ext
end

-- 获取日志文件路径（若指定了 log_dir 则使用，否则与源文件同目录）
local function get_log_file_path(dir)
    local log_file
    if o.log_dir and o.log_dir ~= "" then
        log_file = utils.join_path(o.log_dir, "cutlog.txt")
        utils.subprocess({ args = { "cmd", "/c", "mkdir", o.log_dir, "/p" }, cancellable = false, playback_only = false })
    else
        log_file = utils.join_path(dir, "cutlog.txt")
    end
    return log_file
end

-- 写入日志头部（时间、源文件、模式描述）
local function write_log_header(log_file, path, mode_desc)
    write_cut_log("=====================================", log_file)
    write_cut_log("切割时间: " .. os.date("%Y-%m-%d %H:%M:%S"), log_file)
    write_cut_log("源文件: " .. path, log_file)
    write_cut_log("模式: " .. mode_desc, log_file)
    write_cut_log("-------------------------------------", log_file)
end

-- 测试 ffmpeg 是否可用
local function check_ffmpeg(ffmpeg)
    local test_res = utils.subprocess({ args = { ffmpeg, "-version" }, cancellable = false, playback_only = false })
    return test_res.status == 0
end

-- ====================== 构建精确转码参数（用于日志记录） ======================
local function build_precise_args(ffmpeg, path, seg, out)
    local duration = seg.end_ - seg.start
    return {
        ffmpeg,
        "-accurate_seek",
        "-i", path,
        "-ss", string.format("%.3f", seg.start),
        "-t", string.format("%.3f", duration),
        "-vf", "format=yuv420p",
        "-c:v", "libx265",
        "-preset", "medium",
        "-crf", "28",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-map_metadata", "0",
        "-movflags", "+faststart",
        "-ignore_unknown",
        "-avoid_negative_ts", "make_zero",
        "-y", out
    }
end
-- ====================== 常规切割 ======================
function run_cut()
    if not marking_mode or #segments == 0 then
        show_temp_message("没有标记片段", 3)
        return
    end

    local valid = get_valid_segments()
    if #valid == 0 then
        show_temp_message("没有有效片段", 3)
        return
    end

    local path, dir, filename, base, ext, out_ext = get_file_info()
    if not path then
        show_temp_message(dir, 3)
        return
    end

    local log_file = get_log_file_path(dir)
    write_log_header(log_file, path, "无损切割 + 精确命令参考")

    local ffmpeg = o.ffmpeg_path or 'ffmpeg.exe'
    if not check_ffmpeg(ffmpeg) then
        local err_msg = "FFmpeg 不可用，请检查路径： " .. ffmpeg
        show_temp_message(err_msg, 5)
        write_cut_log("错误: " .. err_msg, log_file)
        write_cut_log("-------------------------------------\n", log_file)
        return
    end

    for i, seg in ipairs(valid) do
        local duration = seg.end_ - seg.start
        local s_str = string.format("%.3f", seg.start):gsub("%.", "-")
        local e_str = string.format("%.3f", seg.end_):gsub("%.", "-")
        local out = utils.join_path(dir, string.format("%s_cut_seg%d_%s-%s%s", base, i, s_str, e_str, out_ext))

        show_temp_message(string.format("正在处理片段 %d/%d ...", i, #valid), 2)

        -- 生成并记录精确转码命令（始终写入日志）
        local precise_args = build_precise_args(ffmpeg, path, seg, out)
        local precise_cmd = build_ffmpeg_command(ffmpeg, precise_args)
        write_cut_log("[精确命令参考 " .. i .. "] " .. precise_cmd, log_file)
        local success = false

        -- 尝试无损复制
        if o.prefer_copy then
            local copy_args = {
                ffmpeg,
                "-ss", string.format("%.3f", seg.start),
                "-i", path,
                "-t", string.format("%.3f", duration),
                "-c", "copy",
                "-map_metadata", "0",
                "-movflags", "+faststart",
                "-ignore_unknown",
                "-avoid_negative_ts", "make_zero",
                "-y", out
            }
            local res = utils.subprocess({ args = copy_args, cancellable = false, playback_only = false })
            if res.status == 0 then
                success = true
                show_temp_message(string.format("片段 %d 无损完成", i), 2)
                local exec_cmd = build_ffmpeg_command(ffmpeg, copy_args)
                write_cut_log("[执行成功(无损)] " .. exec_cmd, log_file)
            else
                local err = res.stderr or "无错误输出"
                mp.msg.warn("片段 %d 无损复制失败，尝试转码... stderr: %s", i, err:sub(1, 200))
            end
        end

        -- 若无损失败或未启用，则转码
        if not success then
            local transcode_args = {
                ffmpeg,
                "-ss", string.format("%.3f", seg.start),
                "-i", path,
                "-t", string.format("%.3f", duration),
                "-map_metadata", "0",
                "-movflags", "+faststart",
                "-ignore_unknown",
                "-avoid_negative_ts", "make_zero",
                "-y", out
            }
            -- 根据扩展名选择编码器
            if out_ext:lower() == ".webm" then
                local vp9 = { "-c:v", "libvpx-vp9", "-crf", "23", "-b:v", "0", "-c:a", "libopus" }
                for _, v in ipairs(vp9) do table.insert(transcode_args, v) end
            else
                local x264 = { "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "128k" }
                for _, v in ipairs(x264) do table.insert(transcode_args, v) end
            end
            local res = utils.subprocess({ args = transcode_args, cancellable = false, playback_only = false })
            if res.status == 0 then
                success = true
                show_temp_message(string.format("片段 %d 转码完成", i), 2)
                local exec_cmd = build_ffmpeg_command(ffmpeg, transcode_args)
                write_cut_log("[执行成功(转码)] " .. exec_cmd, log_file)
            else
                local err = res.stderr or "无错误输出"
                mp.msg.error("片段 %d 转码失败，stderr: %s", i, err:sub(1, 200))
            end
        end
    end

    write_cut_log("-------------------------------------\n", log_file)
    show_temp_message(string.format("✅ 常规切割完成！共 %d 个片段\n日志: %s", #valid, log_file or "无"), 6)
end

-- ====================== 精确转码切割（直接使用 libx265 CRF 28） ======================
function run_cut_transcode()
    if not marking_mode or #segments == 0 then
        show_temp_message("没有标记片段", 3)
        return
    end

    local valid = get_valid_segments()
    if #valid == 0 then
        show_temp_message("没有有效片段", 3)
        return
    end

    local path, dir, filename, base, ext, out_ext = get_file_info()
    if not path then
        show_temp_message(dir, 3)
        return
    end

    local log_file = get_log_file_path(dir)
    write_log_header(log_file, path, "精确转码切割（libx265 CRF 28）")

    local ffmpeg = o.ffmpeg_path or 'ffmpeg.exe'
    if not check_ffmpeg(ffmpeg) then
        local err_msg = "FFmpeg 不可用，请检查路径： " .. ffmpeg
        show_temp_message(err_msg, 5)
        write_cut_log("错误: " .. err_msg, log_file)
        write_cut_log("-------------------------------------\n", log_file)
        return
    end

    for i, seg in ipairs(valid) do
        local duration = seg.end_ - seg.start
        local s_str = string.format("%.3f", seg.start):gsub("%.", "-")
        local e_str = string.format("%.3f", seg.end_):gsub("%.", "-")
        local out = utils.join_path(dir, string.format("%s_exact_seg%d_%s-%s%s", base, i, s_str, e_str, out_ext))

        show_temp_message(string.format("精确转码片段 %d/%d ...", i, #valid), 2)

        -- 生成并记录精确转码命令（始终写入日志）
        local precise_args = build_precise_args(ffmpeg, path, seg, out)
        local precise_cmd = build_ffmpeg_command(ffmpeg, precise_args)
        write_cut_log("[精确命令参考 " .. i .. "] " .. precise_cmd, log_file)

        -- 直接转码（使用与日志相同的参数）
        local res = utils.subprocess({ args = precise_args, cancellable = false, playback_only = false })
        if res.status == 0 then
            show_temp_message(string.format("片段 %d 精确转码完成", i), 2)
            -- 已经通过 precise_args 记录了命令，无需重复写入
        else
            local err = res.stderr or "无错误输出"
            mp.msg.error("片段 %d 精确转码失败，stderr: %s", i, err:sub(1, 200))
            write_cut_log("[执行失败(精确转码)] stderr: " .. err, log_file)
        end
    end

    write_cut_log("-------------------------------------\n", log_file)
    show_temp_message(string.format("✅ 精确转码完成！共 %d 个片段\n日志: %s", #valid, log_file or "无"), 6)
end

-- ====================== 导出时间参数 ======================
function export_commands_only()
    if not marking_mode or #segments == 0 then
        show_temp_message("没有标记片段", 3)
        return
    end

    local valid = get_valid_segments()
    if #valid == 0 then
        show_temp_message("没有有效片段", 3)
        return
    end

    local path, dir, filename, base, ext, out_ext = get_file_info()
    if not path then
        show_temp_message(dir, 3)
        return
    end

    local log_file = get_log_file_path(dir)
    write_log_header(log_file, path, "仅导出精确命令（未执行切割）")

    local ffmpeg = o.ffmpeg_path or 'ffmpeg.exe'
    local time_lines = {}

    for i, seg in ipairs(valid) do
        local duration = seg.end_ - seg.start
        local s_str = string.format("%.3f", seg.start):gsub("%.", "-")
        local e_str = string.format("%.3f", seg.end_):gsub("%.", "-")
        local out = utils.join_path(dir, string.format("%s_exact_seg%d_%s-%s%s", base, i, s_str, e_str, out_ext))

        -- 构建命令（与精确转码相同）
        local precise_args = build_precise_args(ffmpeg, path, seg, out)
        local precise_cmd = build_ffmpeg_command(ffmpeg, precise_args)
        write_cut_log("[精确命令 " .. i .. "] " .. precise_cmd, log_file)

        table.insert(time_lines, string.format("-ss %.3f -t %.3f", seg.start, duration))
    end

    write_cut_log("-------------------------------------\n", log_file)

    if #time_lines > 0 then
        local all_times = table.concat(time_lines, "\n")
        copy_to_clipboard(all_times)
        show_temp_message(string.format("✅ 时间参数已复制到剪贴板（%d 条）\n日志完整命令已保存至: %s", #time_lines, log_file), 5)
    else
        show_temp_message("没有有效的时间参数可导出", 3)
    end
end

-- ====================== 全局快捷键绑定 ======================
-- 1. 切换模式（始终有效）
mp.add_key_binding(o.keybind_toggle, "toggle_marking_mode", toggle_marking_mode)

-- 2. 外部 n 键（仅当 enable_external_copy 为 true 时注册）
if o.enable_external_copy then
    mp.add_key_binding(o.keybind_n, EXTERNAL_BIND_NAME, external_copy_time)
end

mp.msg.verbose("multi_cut 脚本已加载。按 " .. o.keybind_toggle .. " 切换标记模式。")
if o.enable_external_copy then
    mp.msg.verbose("外部 n 键已启用（复制时间）。")
else
    mp.msg.verbose("外部 n 键已禁用，非标记模式下该键不会被脚本占用。")
end
if o.log_enabled then
    mp.msg.verbose("日志记录已启用。")
else
    mp.msg.verbose("日志记录已禁用。")
end