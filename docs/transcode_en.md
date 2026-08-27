[[中文](transcode.md)]


# Transcoding page

The Transcoding page is the main workspace. It combines full encoding configuration, filter processing, task management and run monitoring — from a simple format conversion to a complex filter-chain composition, with batch processing of many files.

---

## 1. Input / output

### Input file
- Pick a video via the **Browse** button or drag-and-drop (drag-and-drop needs `tkinterdnd2`, which the packaged build already includes).
- Dropping onto the input box auto-fills the input path and sets the output folder to the same location.
- The input path is the source for all generated commands.

### Output directory
- Choose or drag a folder. Dropping a folder extracts its path.
- The output file name is decided by the **output suffix** and the **full custom name**.

### File name control
- **Output suffix** — appended after the original name (e.g. `_new`): `input.mp4` → `input_new.mp4`.
- **Full custom name** — overrides the suffix with a complete name (a container extension is added automatically if omitted).
- **Output container** — `mp4`, `mkv`, `mov`, `avi`, `webm`, `gif`, `webp`.

### Clear input / output
- One click clears both (with confirmation).

---

## 2. Preset management

Presets save and reuse common parameter sets so you don't reconfigure every time.

- **Preset list** — dropdown of all saved presets (loaded from `ffmpeg_presets.json`); selecting one loads its params.
- **Save current as preset** — name prompt; on save, params equal to defaults are auto-stripped so the preset stays compact. Watermark, segment-join and trim dynamic params are excluded to avoid pollution.
- **Delete preset** — select then delete (with confirmation).
- **Export all presets (backup)** — dump the whole library to JSON.
- **Import presets (restore)** — from JSON, choose replace or merge.

---

## 3. Encoding parameters (tabs)

### 3.1 Video encoding & quality

**Encoder** — stream copy (`copy`), software (`libx264`, `libx265`, `libvpx-vp9`, `libsvtav1`, `mpeg4`, `libxvid`, `libtheora`), hardware (`NVIDIA NVENC`, `Intel QSV`, `AMD AMF`, `VAAPI`, `VideoToolbox`), pro formats (`ProRes`, `DNxHD`, `FFV1`), and image/animated (`GIF`, `WebP`). The rate-control and preset options switch automatically with the encoder.

**Preset** — speed vs. compression (`ultrafast`…`veryslow`; hardware uses `p1`…`p7`). The available list adapts to the encoder.

**Rate control**
- **CRF** (software): 0–51, lower = better (recommended 18–28).
- **CQ** (NVENC): 0–51, like CRF.
- **Global Quality** (QSV): 1–51.
- **Fixed bitrate**: e.g. `2000k`.

**Advanced (expandable)**
- **tune** — `film`, `animation`, `grain`, `stillimage`, `psnr`, `ssim`, `fastdecode`, `zerolatency`, `vmaf`, `screen`.
- **profile** — H.264: `baseline`/`main`/`high`; HEVC: `main`/`main10`/…; AV1: `main`/`high`/`professional`…
- **level** — e.g. `4.0`, `4.1`, `5.1`.
- **maxrate** / **bufsize** (kbps).

**GIF options** (shown when encoder = `gif`)
- loop count (0 = infinite), dither algorithm (`none`/`bayer`/`floyd_steinberg`/`sierra2_4a`), bayer scale, palette size (`max_colors` 2–256).

### 3.2 Video filters

**Frame rate** — keep source or set a custom value.

**Scale** — three modes: width (height auto), height (width auto), exact W×H (may stretch). A swap (⇄) button exchanges the two values.

**Crop**
- Enable then set width / height / left / top.
- Supports `iw` (input width), `ih` (input height) and arithmetic (e.g. `iw/2`).
- **Auto black-bar removal** — `cropdetect` auto-fills crop params (configurable analysis frames and round value).
- **Visual crop** — separate window shows the first (or a chosen) frame; drag a rectangle, params auto-fill. Time jump supported.

**Rotate / flip** — 0° / 90° CW / 180° / 90° CCW; vertical and horizontal flip.

**Advanced enhancement** (separate window)
- **Denoise (algorithm selectable, since 2026-08-27)**: spatial & temporal strength.
  - **`hqdn3d` (light)** — spatio-temporal denoise, very fast; for mild/compression noise.
  - **`nlmeans` (high quality)** — non-local means, strongest denoise (low-light/high-ISO footage) but 10–50× slower, noticeably slow at 1080p; only spatial strength applies (temporal ignored).
- **Sharpen (algorithm selectable)**: strength.
  - **`unsharp` (USM)** — classic, all-round.
  - **`cas` (contrast adaptive)** — more natural details, great after upscaling/frame interpolation.
- **IVTC** — 60i → 24p (`fieldmatch`+`decimate`).
- **Deblock** — strength dropdown `weak` / `medium` / `strong` + block-size dropdown `4` / `8` (maps to ffmpeg `deblock=filter=strong:block=8` etc.; old numeric strength maps to weak).
- **Color matrix** (`colormatrix`): `bt709:bt2020`, `bt2020:bt709`, `bt601:bt709`, `bt709:bt601`.
- **Color correction** (`eq`): brightness / contrast / saturation / gamma sliders.
- **Hue** (`hue`): hue angle and color saturation.

**Remove logo / blur** (separate window)
- **`delogo`** — smart-interpolation logo/watermark removal. Frame the region with the visual crop tool, then "Copy coordinates from crop" fills `x:y:w:h` in one click.
- **Local blur** (region only) — `boxblur` / `gblur` on a chosen rectangle. The tool builds the `split → crop → blur → overlay` chain automatically; a "🎯 Local blur" button enables it and copies crop coordinates. Coordinates are in the **original frame** space (the chain is placed before other filters).
- **Global blur** — enable blur but do **not** check "region only".
- **Multi-region list (2026-08-26: handle several watermarks/blur regions at once)** — the delogo/blur window can hold **multiple items** (mixed `delogo` / `boxblur` / `gblur`), for frames with several logos/subtitle watermarks at once. Each item sets type, region coords (x/y/w/h, original frame) and strength independently; a Treeview list + form with live write-back (add/delete/reorder). Command generation iterates the list and emits one filter per item (several delogo / local-blur chains auto-stitched). Old data is auto-migrated: without a list, the old single-region fields are used (old presets/snapshots unaffected).

**Deinterlace** — `none`, `bwdif`, `yadif`, `kerndeint`, `pp=lb`, `fieldorder`.

**Pixel format** — optional `yuv420p` (default, for compatibility), `yuv422p`, `yuv444p`, various 10-bit. You can disable the default.

**Speed** — custom multiplier (any positive, e.g. `0.5` slow, `2.0` fast). Audio gets an automatic `atempo` chain (works beyond 2× / below 0.5×).

**Reverse**
- **Video reverse** — only the picture.
- **Audio reverse (independent of video)** — a separate checkbox on the audio tab; checking it reverses audio alone, no longer following the main video. Check both to reverse audio+video together.

**Subtitle burn-in** — check "Burn subtitles" to enable, then pick an external subtitle (`srt`/`ass`/`ssa`/`vtt`) and burn it into the picture (hard subtitle). **Character encoding** dropdown (2026-08-27): `auto` (UTF-8) / `utf-8` / `gb18030` / `gbk` / `big5`. SRT files saved by Chinese Windows Notepad are usually GBK/GB18030 — pick the matching encoding or the text will be garbled (maps to ffmpeg `subtitles` filter's `charenc`; `auto` injects nothing). Requires re-encode; copy mode won't work. To keep subtitles as a separate stream, use the mux page instead — the mux page also offers burn-in (all three modes' video-stream editors have the "Burn subtitles" row, restored 2026-08-28); tracks and burn-in can coexist.

### 3.3 Audio (tab "Audio")

**Basic**
- **Keep audio** (default on).
- **Extract audio only** — output audio only; container switches to an audio format (`mp3`, `aac`, `m4a`, `flac`, `opus`, `wav`, `ac3`). Auto-checks "keep audio"; unchecking restores the previous state.
- **Output container** — audio wrapper format.

**Encode params**
- Encoder: `copy`, `aac`, `libmp3lame`, `opus`, `ac3`, `flac`, `alac`, `pcm_s16le`…
- Bitrate (64k–320k), sample rate (8000–96000 Hz).

**Volume** — slider 0.1×–3.0×.

**Audio reverse (independent of video)** — separate checkbox; fully independent of the main video. All transcode-page audio filters (volume, speed, fade, EQ, denoise, loudness, channels, reverse) are independent and do not follow the video.

### 3.4 Trim (tab "Trim")

- **Enable trim** — set start / end (`HH:MM:SS.ms`, `MM:SS.ms`, or plain seconds). Start defaults to `0`; empty end means to the file end.
- **Frame-accurate** — `trim`+`setpts` for frame precision, but forces re-encode (copy → `libx265`). Off = fast mode (`-ss` before `-i`, keyframe-based, less precise).
- **Combined seek** (fast precise trim for long videos) — for a single clean video (no overlay/watermark/PiP). Jumps to the keyframe before the target, then decodes precisely to the target frame. A post-seek threshold (default 30 s) is adjustable. Exclusive with frame-accurate; auto-disabled with watermark/PiP (multiple `-i` would misplace the second `-ss`).
- **Simple time preview (built-in, pure ffmpeg, no external player)** — the trim tab's "Simple time preview" button opens a built-in preview window that does **not** depend on MPV/PotPlayer. Play/pause the picture; at the target frame click **"Set start"** / **"Set end"** and it auto-fills the start/end times above (millisecond precision, main-video timeline) — no manual time typing. Keyframe jumps (forward/back) with a status bar showing the current time. The same built-in preview also appears in the delogo/blur window, text-watermark window, sub-video settings and segment join (each fills back its own times).

  > ⚠️ **Multi-input `-ss` trap:** with one input, a trailing `-ss` works; with two inputs, the second `-ss` becomes the *second* input's leading `-ss`.
  > ```bash
  > # ✅ one input: trailing -ss works
  > -ss 55 -i file1.mp4 -ss 30 rest…
  > # ❌ two inputs: second -ss becomes file2's leading -ss
  > -ss 55 -i file1.mp4 -ss 30 -i file2.mp4 rest…
  > ```

### 3.5 Segment join (tab "Segment join") — hidden segment-cut tool at bottom-left

Cuts and rejoins one video by multiple time ranges (e.g. remove mid-roll ads). Checking it ignores the Trim tab and uses the segment list.

- **Segment editor** (button "Open segment settings…")
  - **Add segment** — start/end time (seconds or `HH:MM:SS.ms`), optional flip (H/V/H+V).
  - **List ops** — delete selected, move up/down, clear all.
  - **Double-click** — edit a segment's times, flip, speed and reverse.
  - **Per-segment speed** — independent multiplier (auto builds video/audio speed filters).
  - **Per-segment reverse** — independent video/audio reverse (`reverse`/`areverse`).
  - **Import external command** — paste an FFmpeg command with `-ss` and `-t`/`-to`; parsed and imported (supports the double-`-ss` combined-seek format).
  - **Export / send to queue** — *fast* (stream copy, no re-encode) or *precise* (applies all main-page filters, re-encode, frame-accurate; choose `trim` filter or double-`-ss`).

### 3.6 Advanced (tab "Advanced")

**Hardware decode** — enable then pick decoder: `none`, `cuda` (NVIDIA), `qsv` (Intel), `vaapi`, `amf` (AMD), `videotoolbox`. Uses `-hwaccel <api> -hwaccel_output_format <api>` + native decoder. Old `auto` and dedicated decoders (`h264_cuvid`…) were removed (they conflicted with `-hwaccel_output_format`). On the same row: a **Filter acceleration** dropdown and a **Device** box (see below).

**Custom FFmpeg params** — appended at the end of the command, overriding the UI-generated equivalents (`-vf`, `-filter_complex`, `-af`, `-map`…). You can copy the generated filter chain, add your own args, and paste back to override. Useful for params the UI doesn't expose (`-x264-params`, `-bsf`…).

**Filter acceleration (hardware filter switching)** — on the Advanced tab's hardware-decode row. A dropdown + device box control whether filters run in software or hardware. Replaces the old two-checkbox approach.

- **Software (CPU)** — all CPU filters; best compatibility.
- **NVIDIA CUDA** — pure-hardware (`scale_cuda`) stays on GPU; others auto-wrapped with `hwdownload → … → hwupload_cuda`.
- **Intel QSV** — scale/rotate/flip/crop/deinterlace/denoise/color map to `vpp_qsv` (pure hardware); others auto-wrapped.
- **AMD VAAPI / AMF** — scale maps to `scale_vaapi`; others auto-wrapped.

Selecting a hardware item **auto-syncs** the hardware-decode and video-encoder dropdowns to the matching API (`cuda`→`hevc_nvenc`, `qsv`→`hevc_qsv`, AMD→`hevc_amf`), keeping your original software encoder and restoring it when you switch back to Software. It does **not** auto-check "enable hardware decode" — that's your choice; if unchecked, the chain falls back to pure software (no error).

**Device box (optional)** — only for multi-GPU or explicit binding; single-GPU is usually left blank.
- NVIDIA single: `cuda=cu` (blank = no `0`); multi: `0` → `-init_hw_device cuda=cu:0`.
- Intel QSV (iGPU): fixed `-init_hw_device qsv=hw`; multi-GPU Windows: DirectX adapter number (`1`) → `qsv=hw,child_device=1`, Linux: DRM node (`/dev/dri/renderD128`).
- AMD VAAPI (Linux): DRM node → `vaapi=amd:/dev/dri/renderD128`.

> As long as Filter acceleration is CUDA/QSV/VAAPI, the program injects the matching `-init_hw_device` (device box need not be filled). Internal paths (preview, PiP, GIF) force software filters to avoid mixing hardware filters with external players / `overlay` / `filter_complex`.

**Watermark** — overlay an image or video on the main video (same logic as a PiP sub-video).
- **Watermark file** — image (`png`/`jpg`/`bmp`/`webp`/`gif`) or video (`mp4`/`mkv`/`avi`/`mov`/`flv`/`webm`).
- **Adaptive** — evaluates `W`/`H`/`w`/`h` expressions to concrete numbers (two passes: render size then overlay position); unchecking restores the expression.
- **Overlay settings** (separate window) — independent crop / scale / rotate / flip / opacity / chroma-key / loop (same as a normal video track); visual position/size editing.
- **Watermark preset** — save current watermark params as a template.
- Watermark mode forces frame-accurate trim and switches copy → `libx265` (must re-encode).
- **Text watermark** — content, font, size, color, opacity, stroke, show window / loop (`enable`). Its position editor is independent from the image/video watermark editor.

**End handling** (since 2026-08-25; border since 2026-08-27) — the **"End handling"** button on the Advanced tab (the same button in queue task editing applies to that task) opens a window with three independent blocks processed at the **very end of the filter chain**:

1. **Multi-view split grid** — split the output into 2–5 cells: rows×cols (e.g. 1×3 horizontal, 2×2 grid). Implemented with ffmpeg `split` + `hstack`/`vstack` (rows stitched then stacked).
2. **End concat (append image/video)** — append an image (e.g. QR code / end card, display seconds configurable) or a video to the end of the output. Images auto-scale to the output size with black bars centered; video should be pre-matched. **Forces re-encode** (filters required).
3. **Border (pad canvas expand)** — add a border around the final canvas; combinable with split/concat. Top/bottom/left/right margins independent (pixels); color `#RRGGBB` or a color name. **Border position** dropdown: `after split (grid outer frame, default)` = one border around the whole grid; `before split (border per cell)` = each cell bordered first then stitched (cell borders back-to-back, visually a 2× margin line); identical when split is off. Implemented with ffmpeg `pad` (same as HandBrake Pad); odd output sizes round up to even (yuv420p); pure-copy encoding auto-switches to re-encode.

**Preview support**: the text command preview always reflects it; the play preview (mpv/ffplay) and snapshot preview show the border and single-row/column grids; multi-row grids (e.g. 2×2) in the normal play preview show a hint — use complex preview / live preview to see them.

---

## 4. Task management & queue

- **Add to task list** — current config becomes a task. Or drop several videos; the queue uses the preview command as a template. A task holds input, output, full command and settings. States: waiting / encoding / done / failed / stopped.
- **Task list ops** — start queue (parallel, with max parallel count; hardware encoding has its own concurrency cap), stop queue (no new tasks, running ones finish), remove selected, clear all, clear done/failed. Export to `.bat` (Windows) / `.sh` (Linux/macOS). Preview selected (applies filters & trim, but **disables reverse**). **Double-click** edits a task (all params; saved changes update it).
- **Parallel & hardware limits** — parallel tasks 1–5; hardware concurrency 1–4.
- **Stop all** — sends `q` to every running FFmpeg; force-kills after 3 s if still alive. For emergency stops on runaway encodes.

---

## 5. Command preview & single-file encode

- **Current command template** — generated FFmpeg command (editable, but only for copy; doesn't affect the real command).
- **Refresh** — regenerate; also resets queue column widths.
- **Copy** — to clipboard.
- **Preview current command** — play with mpv/ffplay (filters & trim applied, reverse disabled, auto-scaled to screen).
- **Start encode** — encode the current input immediately (non-queue), with live progress.

---

## 6. Right-side log panel

- Operation log (adds, preset load/save, errors) and the FFmpeg subprocess output (progress, errors). Clear and save-to-file supported.

---

## 7. Typical workflow

1. Pick input → set output folder & name.
2. Configure encoder, rate control, preset.
3. Apply filters (crop, scale, rotate, enhance, speed…).
4. Set trim or segment join (optional).
5. Add watermark (optional).
6. Preview command, or "Preview current command".
7. Add to task list, or "Start encode".
8. Watch the log for progress.
9. For batches, add many files as tasks and run the queue in parallel.

---

## Appendix — hardware acceleration parameter map (Intel QSV / NVIDIA NVENC-CUDA / AMD VAAPI-AMF)

### 1. Device init & decode

| Step | Intel (QSV) | NVIDIA (NVENC/CUDA) | AMD (VAAPI/AMF) |
| :--- | :--- | :--- | :--- |
| Init virtual device | `-init_hw_device qsv=hw` | `-init_hw_device cuda=cu` *(opt)* | `-init_hw_device vaapi=amd:/dev/dri/renderD128` *(Linux)* |
| HW decode | `-hwaccel qsv -hwaccel_output_format qsv` | `-hwaccel cuda -hwaccel_output_format cuda` | `-hwaccel vaapi -hwaccel_output_format vaapi` *(or `-hwaccel amf -hwaccel_output_format amf`)* |
| Decode out fmt | `-hwaccel_output_format qsv` | `-hwaccel_output_format cuda` | `-hwaccel_output_format vaapi` |

### 2. Filter chain: HW ↔ SW

| Case | Intel (QSV) | NVIDIA (NVENC/CUDA) | AMD (VAAPI/AMF) |
| :--- | :--- | :--- | :--- |
| HW → SW | `hwdownload,format=nv12` | `hwdownload,format=nv12` | `hwdownload,format=nv12` |
| SW → HW | `hwupload=derive_device=qsv,extra_hw_frames=64` | `hwupload_cuda` *(or `hwupload`)* | `hwupload` |
| Pure-HW scale | `scale_qsv=w=1280:h=720` / `vpp_qsv=w=1280:h=720` | `scale_cuda=w=1280:h=720` | `scale_vaapi=w=1280:h=720` |
| Pure-HW rotate | `vpp_qsv=transpose=clock` *(clock/cclock/reversal, no numbers)* | *(none, fall back to SW)* | *(none, fall back to SW)* |
| Pure-HW crop | `vpp_qsv=cw=1280:ch=720:cx=0:cy=0` | *(none, fall back to SW)* | *(none, fall back to SW)* |

### 3. HW encoders & common params

| Step | Intel (QSV) | NVIDIA (NVENC) | AMD (AMF/VAAPI) |
| :--- | :--- | :--- | :--- |
| H.264 | `-c:v h264_qsv` | `-c:v h264_nvenc` | `-c:v h264_amf` *(or `h264_vaapi`)* |
| HEVC | `-c:v hevc_qsv` | `-c:v hevc_nvenc` | `-c:v hevc_amf` *(or `hevc_vaapi`)* |
| Quality | `-global_quality 26` | `-cq 26` *(or `-rc constqp -qp 26`)* | `-rc_mode CQP -qp 26` *(VAAPI)* |
| Preset | `-preset medium` | `-preset p4` *(or `medium`)* | `-quality balanced` |

### 💡 Key takeaways
1. **Pure-HW chain** (e.g. Intel `vpp_qsv`): data stays on GPU, fastest, no `hwdownload`/`hwupload` needed.
2. **Mixed chain**: any software filter (`transpose`, `crop`, `drawtext`…) needs `hwdownload` to RAM, then `hwupload` back.
3. **NVIDIA `hwupload`**: in a pure-CUDA chain, plain `hwupload` suffices; across APIs (e.g. OpenCL→CUDA) use `hwupload_cuda`.
4. **AMD device binding**: on Linux, VAAPI often fails to find a device — always add `-init_hw_device vaapi=…`.
