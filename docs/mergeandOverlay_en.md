[[中文](mergeandOverlay.md)]


# Merge / Mux / Picture-in-Picture page

The Merge page (Mux / Merge / PiP) is one of the core modules. It combines multiple video, audio and subtitle streams into one output file. Three main modes:

- **Mux mode** — merge a main video with external audio/subtitles; re-encode or stream-copy. Like mkvtoolnix.
- **Picture-in-Picture (PiP)** — overlay one or more sub-videos (or images) on the main video, with position, size, opacity, chroma-key, loop, etc.
- **Concat mode** — join several videos head-to-tail, stream-copy (fast) or re-encode (compatible). **In re-encode mode each segment supports a full independent filter chain** (crop, rotate, flip, deinterlace, enhance, trim, reverse, speed), with forced uniform specs to ensure a clean join.
  (If you don't enable PiP or Concat, it's plain mux mode.)

---

## 1. Common functions

### 1.1 Main video & track management
- **Main video** — the base video file.
- **Track list (Treeview)** — all added tracks (video/audio/subtitle) with enabled state, type, spec (resolution/duration/codec…), encode settings. Double-click to edit a track; drag-and-drop to add (auto type detection). Toolbar: enable/disable, edit, preview, move up/down, delete, clear, sort (by name or mtime), save/load project. Right-click menu on selected tracks: copy/paste/reset filter settings, copy/paste trim·speed·reverse (V→A), enable/disable, edit, preview (incl. snapshot/live), contact sheet, move up/down, clone, **Replace source**, delete, reset column widths — full list in §7.4.

### 1.2 Add external tracks
- **External audio** — `mp3`, `aac`, `wav`, `flac`, `opus`, `ac3`…
- **External subtitle** — `srt`, `ass`, `ssa`, `vtt`, `idx`, `sup`…
- **External video** — in PiP or Concat mode, as a sub-video or concat segment.

### 1.3 Mode selection & params

**Mux mode**
- Merge main video with external audio/subtitles; stream-copy or re-encode. Main video can take full filters (crop, scale, rotate, enhance…), **including subtitle burn-in** ("Burn subtitles" checkbox + character encoding; restored 2026-08-28; copy auto-switches to re-encode). Audio tracks set codec, bitrate, sample rate, volume independently.
- Has a separate **audio-only** mode (left of the "start merge" button) — different from the transcode page's audio-only; here it simply mixes a few audios (e.g. narration + main) into one track.

**Enable PiP**
- All video streams are force re-encoded; output duration defaults to the main video's.
- Each sub-video sets position, size, opacity, chroma-key, loop independently.
- Sub-videos support all independent filters (crop, rotate, flip, deinterlace, enhance, trim, reverse, speed).
- Essentially the transcode-page watermark feature, strengthened: watermark allows one sub-picture, PiP allows N. (PiP was implemented first; batch watermarking came later.)
- Despite the name, PiP isn't only for small-over-big — it can tile several pictures (e.g. 3 portrait videos in 3 columns). See the **PiP main-video offset page** below.
- Smart tiling auto-arranges multiple sub-videos.

**Concat mode (head-to-tail)**
- Two sub-modes:

**Stream-copy mode**
- Triggered when main video and audio encoders are both `copy` **and** all input videos have identical params (resolution, fps, pixel format, codec).
- Uses the `concat demuxer` (`-f concat -safe 0 -i filelist.txt`) — binary-level join.
- Extremely fast (≈ file copy), no re-encode, so **no filter takes effect** (including the main video's); pure concatenation only.
- Requires strict param match or you get artifacts / A/V desync. Any per-track filter/trim setting is ignored.

**Re-encode mode**
- Triggered when the main video or audio encoder is not `copy` (e.g. `libx264`).
- Uses the `concat` filter in `filter_complex`; **each segment (main + sub) now supports a full independent filter chain**:
  - **Video**: crop, rotate, flip, deinterlace, enhance (denoise/sharpen/color), trim, reverse, speed.
  - **Audio**: trim, reverse, speed, silence generation (auto-fill).
  - **Forced uniform at each segment's end**: resolution, pixel format, fps, SAR (from the main video) — so concat never errors.
  - **Global stage (after join) keeps only**: subtitle burn-in (main video), text watermark (drawtext, main video). To drop a segment's audio in Concat mode, don't uncheck enable — choose **generate silent stream** in that video's audio-binding tab. (2026-08-28 restored: the mux page's burn-in UI is fully back — all three modes support burn-in + charenc.)

When the main video encoder is non-`copy`, every video track (main + all subs) is double-click editable with these independent filters:

**Video features**
- **Crop**, **Rotate** (90/180/270°), **Flip** (H/V), **Deinterlace** (`yadif`/`bwdif`…), **Enhance** (denoise/sharpen/color, inside the segment), **Trim**, **Reverse**, **Speed** (synced with audio).

**Audio features**
- **Trim** — synced with video; duration auto-matched.
- **Reverse** — only "external" audio tracks can check it independently in the audio-track settings; a video's embedded audio no longer follows the video reverse (fully unlinked).
- **Speed** — only external audio can set it independently (`atempo` chain); embedded audio no longer follows video speed.
- **Silence** — if a segment has no audio (or you choose), a silence stream of matching duration is auto-generated.

**⚠️ Forced uniform (auto-override)**
After each segment, the chain forcibly appends:
- `scale={main W}x{main H}`, `format={main pixfmt}`, `fps={main fps}`, `setsar=1`, `setpts=PTS-STARTPTS`.

These guarantee identical specs before `concat` — no join errors.

**Global stage (after join)**
- **Video**: only the main video's subtitle burn-in (if any, with charenc) and text watermark (drawtext). **Burn-in restored 2026-08-28**: the mux burn-in UI is fully back — normal-mux / PiP / serial-concat all support it.
- **Audio**: volume control removed; Concat mode offers no overall or per-track volume.

### 1.7 End handling (multi-view split / end concat / border, since 2026-08-25, border 2026-08-27)

The **"End handling"** button on the mux page toolbar (the Transcode page's Advanced tab and queue task editing have the same dialog; the three settings are independent) processes the **very end of the filter chain** — this is **not** the same as "serial concat" above: serial concat stitches multiple **input** segments in order; end handling operates on the **current output**. Three independent blocks, combinable:

1. **Multi-view split grid** — split the output into 2–5 cells: rows×cols (e.g. 1×3 horizontal, 2×2 grid). ffmpeg `split` + `hstack`/`vstack`.
2. **End concat (append image/video)** — append an image (QR code / end card, display seconds) or a video. Images auto-scale with black bars; video should be pre-matched. **Forces re-encode.**
3. **Border (pad canvas expand)** — top/bottom/left/right margins (px) + color (`#RRGGBB` or name). **Border position** dropdown: `after split (grid outer frame, default)` / `before split (border per cell)` — the latter borders each cell before stitching (cell borders back-to-back, visually a 2× margin line); identical when split is off. ffmpeg `pad` (HandBrake Pad); odd sizes round up to even; pure-copy auto-switches to re-encode.

**Preview support**: text command preview always reflects it; the mux page live preview (mpv lavfi) supports the full grid + border (incl. multi-row grids); the Transcode play preview supports border and single-row/column grids (multi-row grids hint to use complex/live preview).

### 1.4 Chapters & metadata
- **Copy source chapters** — keep the main video's chapter marks (`-map_chapters 0`).
- **Import external chapter file** — FFmetadata format (`-i meta.txt -map_chapters N`).
- **Segment chapter labels** (Concat) — each track's metadata tab has a "chapter label" box; blank → default ("Segment 1"…).
- **Generate chapters** (Concat) — builds an FFmetadata temp file from labels + durations and injects chapters; preview mode skips the temp file.

### 1.5 Output settings
- **Container**: MKV, MP4, WebM (auto-recommended by mode).
- **Output path**: custom location.
- **Delete source files**: after merge, move sources to the Recycle Bin / Trash (soft delete, **not** permanent) — with confirmation. Tooltip notes it's a soft delete.
- **Verify output**: integrity check after merge.

### 1.6 Command preview & control
- **Live preview** (editable, but doesn't affect the real command — just a copyable temp edit).
- **Refresh**, **Copy**, **Start merge** (live progress log).

---

## 2. PiP main-video offset page

With PiP enabled, editing the main video track opens a window with an **"Overlay / Offset"** tab, split into two columns:

- **Left**: main video canvas offset (`pad` filter).
- **Right**: batch ops and smart tiling for all sub-videos.

### Left — main video canvas offset
- **Enable canvas offset** — place the main video on a larger black canvas.
- **Canvas W/H** — manual canvas size.
- **Offset X/Y** — main video position on the canvas (negative allowed).
- **Get size** — read resolution from the file.
- **Visual canvas-offset editor** — drag a blue rectangle to position the main video.

### Right — sub-video batch ops & smart tiling

| Button | What it does |
|--------|--------------|
| **Clear sub-video scale/crop** | uncheck scale & crop on all sub-videos (back to original size). For tiling or manual adjust. |
| **Unify height** | set all tracks' height to a value; width scales by ratio (enables scale, "height-first"). |
| **Unify width** | same, width-first. |
| **Change sub-video codec** | set all sub-videos to `libx264` (just silences the "copy ignored" log; no real effect). |
| **Restore to copy** | set all sub-videos back to stream-copy (for switching PiP→Concat or keeping original codec). |
| **Compute tiling** | **core**: from each video's current rendered size (scale/crop/rotate considered), auto-compute the best grid layout and update each sub-video's overlay position and the main video's canvas size. |

**"Compute tiling" params**
- **Per row / per column** — base unit count for row- or column-first.
- **Direction** — auto / row-first / column-first. Auto picks the closer-to-16:9 direction.

**How it works**
1. Get main video's current rendered size (live from filter settings).
2. Get each sub-video's current rendered size (its own scale/crop considered).
3. Arrange into a grid; compute total canvas W/H.
4. Update main canvas (`pad`) and each sub-video's `overlay` coords.
5. All changes reflect live in the track list and command preview.

> Tip: for best tiling, first "Clear sub-video scale/crop" (or set each manually), then "Compute tiling", to avoid messy layouts from mismatched sizes.

---

## 3. Other conveniences

- **Save / load project** — all tracks, settings, layout to a `.fflgproject` file (JSON inside; editable in a text editor). **Not interchangeable with the Transcode page's "Export / import project"**: the mux-page project file carries no `project_type` key, while the Transcode one carries `project_type = "convert"`. Opening the wrong kind shows a hint to use the other page instead of silently loading wrong data.
- **Sort** — by name or mtime (Concat mode only).
- **Drag-and-drop add** — auto type detection.
- **Track edit** — double-click any track for video filters, audio params, subtitle language/title. In Concat re-encode mode, sub-video crop/scale/rotate filters now work, but speed/reverse/subtitle are global.

---

## 4. Typical workflows

**Scenario 1 — plain mux (one video + external audio/subtitle)**
1. Pick main video. 2. Add external audio/subtitle (mux mode). 3. Adjust main video filters if needed. 4. Set output, "Start merge".

**Scenario 2 — PiP (multi-video overlay)**
1. Enable PiP. 2. Add main + sub-videos. 3. Double-click each sub-video: crop/scale/chroma/loop. 4. For batch layout: "Clear sub-video scale/crop", then "Compute tiling". 5. Preview & adjust position. 6. Merge.

**Scenario 3 — Concat (multi-segment join, uniform specs)**
1. Enable Concat. 2. Add segments in order. 3. For per-segment crop/rotate/enhance/trim/reverse/speed, double-click to set. 4. Set main video encoder to non-`copy`. 5. Specs auto-unified & joined. 6. Set output, merge.

---

## 5. Notes

- **Stream-copy mode** ignores all filters; only usable when all inputs match exactly.
- **PiP mode** — all sub-video filters work, but no stream-copy (force encode).
- **Concat re-encode** — enhance/speed/reverse act inside each segment; no jump at the join.
- **Volume** is removed in Concat; keep input levels similar or pre-process.
- **Chroma-key / loop** only show in PiP with a visible sub-video; auto-hidden in Concat.

---

## 6. Audio & subtitle track advanced settings

Double-click any audio or subtitle track in the list to open its detailed settings dialog. Besides basic codec / volume (audio) / language / title, these advanced features were recently added:

### 6.1 Audio track time offset (delay seconds)
- The audio-track dialog has a new **"Time offset align (delay seconds)"** frame.
- A positive value N makes that track start **N seconds later** (e.g. when dubbing lags the original by N seconds); implemented with the `adelay` filter (leading silence padding).
- 0 or blank = no offset. Note: enabling offset forces audio re-encode (`copy` codec auto-switches to `aac`).

### 6.2 Default track (disposition)
- Both audio and subtitle dialogs have a new **"Default track:"** dropdown: `default` / `none` / `forced` / `hearing_impaired` / `visual_impaired`; blank → first track defaults to `default`.
- Maps to `-disposition:a:N` / `-disposition:s:N` — for bilingual subtitles, forced subtitles (player shows them by default), hearing/visual-impaired subtitles, etc.

### 6.3 Apply source video to audio (V→A)
- Applies to **source-linked audio tracks** — audio added via "Add audio" when dropping a video (its `file_path` matches the source video). Externally dropped pure-audio files have no linked video.
- Dialog button **"Apply src video trim/spd/rev (V→A)"**: one click copies the linked video's trim/speed/reverse into this audio track (writes explicit values, freely reversible).
- Right-click **"Batch src-audio→video T/S/R (V → A)"**: batch-applies to the source-linked audio among the **selected tracks** only; out-of-range auto-clamped with a one-time summary.
- Refreshes the track list and command preview live.

### 6.4 Audio independent trim (no split — Concat mode only)
- In the segment editor (SegmentEditor) window, between the segment list and "Split segment", a new **"Audio independent trim"** frame appears.
- When enabled, set start/end times: the audio is trimmed to that range while the video still joins by segments — handy when music only needs head/tail trimming to match total length (middle stays intact).
- Editable only when enabled; the window shows a live "total segment video duration" reference (includes per-segment speed).

### 6.5 Volume
- The audio-track dialog offers an **"Enable volume adjust"** toggle + volume slider, independent of codec / bitrate / sample rate.

---

## 7. Clip fade in/out & serial transition (xfade)

### 7.1 Video-track "Fade in/out" tab
- Double-click a video track (Concat re-encode mode) to open settings; the **"Fade in/out"** tab lets you check "Enable fade in/out" and set fade-in / fade-out durations (seconds, on one row).
- Implemented with `fade=t=in` / `fade=t=out` (gradual black at clip ends); if duration is unknown, fade-out is skipped but fade-in still applies.

### 7.2 Serial transition (xfade, per-track resident attribute)
- Transition is now a **per-track resident attribute** (attached to "this clip": this clip controls the transition between itself and the next), no longer a global switch on the merge page.
- In Concat mode, every video track's "Fade in/out" tab has an **"Enable serial transition"** checkbox + a **transition-type dropdown** + a **"Transition duration (s)"** box.
- **The last clip has no next clip, so its transition row is greyed out** (checkbox/dropdown disabled) and the toggle is ignored.
- Transition type (ffmpeg `xfade` `transition`) is independently selectable per track: fade / fadeblack / fadewhite / fadegrays (fades), wipeleft / wiperight / wipeup / wipedown (wipes), slideleft / slideright / slideup / slidedown (slides), smoothleft / smoothright / smoothup / smoothdown (smooth slides), circlecrop / circleclose / circleopen / zoomin (shapes & zoom), dissolve / pixelize / radial (others).
- Transition duration is auto-clamped to half the shorter of the two adjacent clips.
- **Mutually exclusive with fade in/out (per track)**: this clip's fade-out is replaced by its own transition; the next clip's fade-in is replaced by the previous clip's transition; **first clip's fade-in / last clip's fade-out still apply** as the whole output's head/tail fade. Adjacent clips without a transition still hard-cut, independently.
- **Audio follows automatically**: audio clips map 1:1 to video clips and follow the corresponding video clip's transition toggle via `acrossfade` (duration matches the video transition) — no separate audio transition setting needed.

### 7.3 "One-click fade in/out (all)" & "One-click transition (all)" buttons (main video's "Fade in/out" tab)
- In Concat mode, the main video's "Fade in/out" tab shows two batch buttons side by side at the bottom, each with its own "Duration (s):" box (default 1.0 s, freely editable):
  - **One-click fade in/out (all)**: writes fade in/out to every enabled video/audio track (short clips auto-clamped to `min(1.0, dur*0.4)`).
  - **One-click transition (all)**: enables serial transition on every enabled video track (except the last); type comes from the current dropdown, duration from this row's box, last clip auto-skipped.
- The two duration boxes are **fully decoupled**.
- Clicking also refreshes the currently-open edit window's checkboxes / dropdown / duration boxes, so "Save" won't overwrite the just-applied settings.

### 7.4 Right-click menu operations overview

> Invoked by right-clicking any row of the track list. Complete list below, grouped by function. Most items act on the **selected track(s)** (multi-select supported).

**① Filter settings — copy / paste / reset**
- **"Copy filter settings"** — copies filter params from the first selected track (a "copy all by default, explicit exclusions" strategy; only non-cross-transferable items are skipped).
- **"Paste filter settings"** — applies the clipboard filter settings to the selected tracks (greyed out when the clipboard is empty).
- **"Reset filter settings"** — resets the selected tracks' filters to defaults (clears all filters).

**② Trim / speed / reverse (V→A)**
- **"Copy trim/spd/rev (V→A)"** — copy the selected video track's trim/speed/reverse (enabled only when a video track is selected).
- **"Paste trim/spd/rev (V→A)"** — apply those to selected audio tracks (enabled only with a clipboard; includes out-of-range safety guard).
- **"Batch src-audio→video T/S/R (V → A)"** — batch-applies to the source-linked audio among the selected tracks; out-of-range auto-clamped with a one-time summary (see §6.3).

**③ Playback, preview & thumbnails**
- **"Enable/Disable"** — toggle the selected tracks' enabled state.
- **"Edit track"** — open the selected track's settings dialog (same as double-clicking the row).
- **"Preview track"** — preview the selected track.
- **"Preview track (snapshot – PiP composite)"** — render a still of the PiP-composited frame.
- **"Live preview (PiP, may stutter)"** — mpv real-time composite preview (PiP mode only).
- **"Create thumbnail"** — generate a contact sheet for the first selected video track (for the main video, simulates the composited / concatenated frame per the current mode).

**④ Track order & structure**
- **"Move up" / "Move down"** — reorder the selected tracks in the list.
- **"Clone track"** — deep-copies the selected track (all filters / trim / overlay / transition settings) right after it; clones the first when several are selected.
- **"Replace source"** — swaps **only the source file**, keeping layout & filters intact (see below).
- **"Delete track"** — delete the selected tracks.
- **"Reset column widths"** — restore the track list's default column widths.

**⑤ Replace source (added 2026-09-11)**
- **Core semantics: swap the source file only.** Select a track → right-click **"Replace source"** → pick a new file; only the track's source path changes — **position / scale / rotate / crop / filters / trim / transition (the whole encode-settings block) is preserved, with no automatic adaptation** (the CapCut-style "re-fit on swap" is deliberately NOT done).
- **Main-video double write:** if you replace the main video track, the main-video variable is updated too, avoiding "self-overlay" or a path mismatch.
- **Report-only, never mutate params:** after swapping, the new media is validated and findings are surfaced as **log lines only** (no popup, no parameter changes):
  - the new source lacks the required stream type (video track with no video stream / audio track with no audio stream);
  - a video track whose audio source is itself, but the new source has no audio stream (the command may fail);
  - the track has chroma-key enabled (key colour / similarity need re-tuning for the new footage);
  - the new source's duration differs (transition / fade / trajectory **absolute-second params are NOT auto-adapted**);
  - the trim end exceeds the new source's duration (output gets silently truncated).
- If the file does not exist or equals the current source → a single log line, no change.
- Why the layout survives: sub-video positions default to relative expressions and crop sizes default relative to the source, so they adapt to the new size automatically.

> Note: "One-click fade in/out (all) / One-click transition (all)" is no longer a right-click item — it lives as buttons inside the main video's "Fade in/out" tab (see §7.3).

### 7.5 Appendix — the 24 transition types in detail (xfade transition)

> The transition-type dropdown has 24 entries in 6 families. Below, what each looks like on screen, so you can pick by intent.

**1. Fade**
These control opacity or colour to cross over smoothly.

- **fade** — the basic cross-fade. The previous picture fades out while the next fades in; the two overlap and blend during the transition.
- **fadeblack** — fade through black. The previous picture dims to full black, then the next brightens out of the black.
- **fadewhite** — fade through white. The previous picture brightens to full white, then the next emerges from the white.
- **fadegrays** — fade through grey. Like the above but the previous picture dissolves to grey and the next emerges from the grey.

**2. Wipe**
Simulates a physical wiper sweeping across the screen: the previous picture is pushed away / wiped off, revealing the next.

- **wipeleft** — wipe right-to-left. The previous picture exits to the left, the next appears in its wake.
- **wiperight** — wipe left-to-right. The previous picture exits to the right.
- **wipeup** — wipe bottom-to-top. The previous picture exits upward from the bottom.
- **wipedown** — wipe top-to-bottom. The previous picture exits downward from the top.

**3. Slide**
Similar to wipe, but the slide family keeps each picture intact — like two cards sliding to swap places.

- **slideleft** — slide left. The previous picture slides off to the left; the next slides in from the right.
- **slideright** — slide right. The previous picture slides off to the right; the next slides in from the left.
- **slideup** — slide up. The previous picture slides off upward; the next slides in from the bottom.
- **slidedown** — slide down. The previous picture slides off downward; the next slides in from the top.

**4. Smooth slide**
Adds an ease-in/ease-out curve on top of a plain slide, so it accelerates and decelerates — visually more natural and fluid.

- **smoothleft / smoothright / smoothup / smoothdown** — left / right / up / down smooth slides; same motion as the slide family but with a smoother rhythm.

**5. Shape & zoom**
These use a geometric shape or a zoom to switch content.

- **circlecrop** — circular crop transition. A circular region grows or shrinks to reveal or hide the picture.
- **circleclose** — circle closing. A circle contracts from the screen edges toward the centre, closing to switch to the next picture (or the next expands from a centre circle).
- **circleopen** — circle opening. The reverse of circleclose: a circle grows from the centre outward, gradually revealing the next picture.
- **zoomin** — zoom transition. The previous picture zooms in fast until it fills the screen, then switches to the next.

**6. Others**
- **dissolve** — the previous picture's pixels scatter away like sand or noise while the next surfaces — a dreamy / old-film feel.
- **pixelize** — the previous picture turns into mosaic blocks until it is fully blocky, then resolves into the next.
- **radial** — radial transition. From the screen centre, a radar-sweep / fan expansion gradually reveals the next picture.

---

## 9. Mask / transparent overlay

The mask is a standalone feature (not a toggle on some filter). It applies to the **sub-video** and **text watermark** on the Mux page, making part of the sub-video transparent so the main video (or canvas) shows through. Entry point: on the video-track editor's **"Loop / Chroma"** tab, the **"Mask"** button to the right of the **Transparency** checkbox (spaced `padx=25` from it).

### 9.1 Open the mask dialog
- Click **Mask** to open the settings box. **Since 2026-09-11 this is a single delogo-style dialog (list on top, params below)** that can hold several shapes (see §15): top **Enable mask** master switch → shape list (enabled / type / direction / coord summary; click the "enabled" cell to toggle one row) → edit-selected-shape panel (direction radio / X·Y·W·H + 🎯 visual region picker / edge feather / external shape image / time window / trajectory) → Save / Cancel.
- Coordinate space = the sub-video's **final rendered frame** (after crop→rotate→scale), identical to the dialog's canvas — zero conversion. The old **"📋 Copy coords from crop"** button is gone (replaced by an independent region picker inside the list).
- ⚠️ The master **"Enable mask"** switch must be checked and **Save** clicked for the mask block to enter the command; if the shape list is empty, Save auto-turns the master switch off (avoids a 0-size rectangle blacking out the whole frame).

### 9.2 Mask direction
- **Outside the mask (show only rectangle)**: black background, white rectangle — opaque inside the rectangle, transparent outside; the main video shows through outside the rectangle.
- **Inside the mask (rectangle transparent)**: white background, black rectangle — rectangle transparent, everything else normal; the main video shows through the rectangle hole.

### 9.3 Scope & implementation
- The mask applies to both **PiP sub-videos** and **text watermarks** (both share the same "Loop / Chroma" editor).
- Internally uses `alphamerge`: writes the grayscale mask into the alpha channel (white = opaque, black = transparent). The bundled ffmpeg has no `mask` filter, so it goes `format=rgba,split=2[a][m];[m]format=gray,drawbox…[msk];[a][msk]alphamerge`. `format=rgba` before the split locks the main input's pixel format — otherwise the matte's `format=gray` lets ffmpeg's auto format negotiation downgrade the scale output to gray, greying out the whole frame (fixed 2026-09-10).
- When the mask is enabled, the sub-video pipeline forces `format=rgba` to keep alpha; the transparent area is shown through by the main video/canvas during overlay — **no mov/alpha muxing needed** (transparency is consumed by the main video at composite time).

### 9.4 Note
- The mask belongs to the Mux page's per-track settings. The Transcode page (single-file) has no such setting and it never appears in the Transcode task queue.

## 10. Sub-video free layout (unbounded)

On the sub-video overlay page (PiP), a new **"Free layout"** checkbox sits to the right of the **Blend mode** dropdown, lifting the clamp on the sub-video position/size.

### 10.1 Behavior
- When checked: the sub-video may be larger than the main video and dragged fully outside the main frame (the visual editor does not scroll; overflow simply exits the frame).
- Position/size are passed to ffmpeg as-is (`overlay` itself supports negative/out-of-range/larger-than-main; overflow is clipped by the main frame).
- Final output canvas = main video; when the main video uses offset/pad, the base = pad canvas.

### 10.2 Scope
- Applies to both the **sub-video overlay** and **text-watermark visual editor**; the checkbox state is saved with the per-track settings (`overlay_free_layout`).

---

## 11. Trajectory control (dynamic watermark)

Besides static positioning, a watermark / PiP sub-video can also **move along a looping trajectory over time**. Entry: the **「Trajectory...」** button on the right of the "Continuous rotation" row in the sub-video settings window (same component in the Transcode page's image-watermark settings).

### 11.1 Four preset trajectories

| Preset | Behavior | Parameters |
|---|---|---|
| Left-right sweep | Watermark sweeps the **full width** (left edge 0 → right edge W) back and forth; y uses your set coordinate (controls the top margin) | Cycle (controls speed) |
| Up-down sweep | Sweeps the **full height** (0 → H) back and forth; x uses your set coordinate (controls the left margin) | Cycle |
| Tilted diamond loop | Follows the 4 grid points `(4,1)→(1,2)→(2,5)→(5,4)` of the trajectory editor's 5×5 grid — a tilted diamond, **constant speed** (each segment's duration is proportional to its length) | Cycle |
| Corner hopping | Jumps between the four screen corners (inset by margin), dwells at each corner, then teleports to the next | Dwell per corner + margin |

### 11.2 Parameters

- **Cycle (sec)**: controls **speed** — shorter cycle = faster movement. Sweep = one back-and-forth; diamond = one full loop. Corner hopping ignores this cycle (use "Dwell per corner" instead).
- **Dwell per corner (sec)**: how long the watermark stays at each corner when corner hopping.
- **Margin**: distance of the watermark from screen edges when corner hopping — pixel value (e.g. `20`) or relative expression (e.g. `W*0.03` = 3% of main width).

### 11.3 Relation to other features

- **No conflict with loop control (show window / cycle show / loop count)**: trajectory controls *position* (overlay `x/y` expressions), loop control governs *visibility* (`enable` expression) — they are **orthogonal dimensions** and can be freely combined. E.g. corner hopping + show window 5–10s = hopping only during seconds 5–10.
- **Blend modes don't support dynamic trajectories**: when using overlay/screen/multiply etc. blend modes, the trajectory setting is ignored (falls back to the base position) and the program informs you.
- **Stackable with continuous rotation**: spin + movement are independent.
- **Implementation**: x/y use `t`-based ffmpeg eval expressions (triangle wave / piecewise linear interpolation / st-ld variable slots) — no external trajectory editor needed; the base coordinates `overlay_x/overlay_y` are preserved, so you can switch back to static at any time.

### 11.4 List waypoints (time-segment table, embedded panel since 2026-08-27)

Besides the four presets, the trajectory dialog has an **"Enable list waypoints"** checkbox (when checked, the preset dropdown above is ignored — list waypoints take priority). When checked, the embedded panel enables; **each row = one time segment on the video timeline**, rows follow in time order for second-level control of the watermark's behavior:

- **Time segment** — each row's start + duration (or start/end); the end row can only be the last one (static positioning, no segment).
- **Move** — per row: start coords → end coords (canvas absolute pixels); the watermark moves linearly from start to end during that segment; the row-end position auto-becomes the next row's start (continuous, smooth).
- **Hide** — when checked, the watermark is fully hidden during that segment (overlay not rendered — not black/frozen).
- **Self-rotation** — spin while moving (overrides the global rotation); each segment can set its own speed.
- **End action** — e.g. freeze at segment end (position stops, sub-video/self-rotation keeps going).
- Row coords can be set by dragging in the visual editor via the "start/end" buttons; the panel shows total duration with a red vertical line marking the end row.
- **Max 15 rows** (far below ffmpeg's long-expression crash threshold of ~95–100 segments); over-limit is warned.

**Implementation**: `build_waypoint_expr` compiles the whole table into overlay x/y eval expressions (per-frame `t` evaluation, `lt`/`mod` segmentation, `st`/`ld` variable slots) — no temp files; blend mode also supports it (dynamic crop window follows). **Orthogonal to loop control (show window / cycle show)**: the table governs "where/when-hidden", loop control governs "when-visible" — combinable.

---

## 12. New per-track parameters (2026-09-07 ~ 2026-09-10)

The mux page's video-track editor (double-click main or sub video → **Filters** tab) **shares the same filter panel as the Transcode page**, so everything below is available per track — one independent copy for the main video and for each sub-video. Output color marks and GOP are injected on both the main-video and sub-video output-parameter paths.

### 12.1 GOP / keyframe interval (2026-09-09)
- Location: the `GOP:` box + "frames" on the same row as **Frame rate**; maps to ffmpeg `-g`.
- Blank = encoder default (x264/x265 ≈ 250 frames). For random seeking enter `fps × target seconds` (30 fps → 30–60 for a keyframe every 1–2 s).
- Smaller = more accurate seeking but bigger file. Re-encode only; ignored with `copy`.

### 12.2 Output color marks (2026-09-09)
- Location: **"Output color marks"** block in the right column of the "Advanced enhancement" window: four dropdowns **primaries / transfer / matrix / range**, writing the output file's color **metadata** (`-color_primaries` / `-color_trc` / `-colorspace` / `-color_range`).
- **Follow source = don't touch it** (inherit the source tags; if the source has none or wrong ones, the output inherits the same gap). Not re-stamping marks after a re-encode is a common cause of HDR clips looking washed out / off-color in some players.
- Marks only — no pixel conversion (use the "Color matrix" filter for that).
- Measured pitfall: libx264 / libx265 / libsvtav1 **silently drop** `-color_primaries` / `-color_trc`, so those three go through private params (`-x264-params colorprim=:transfer=` / `-x265-params` / `-svtav1-params color-primaries=:transfer-characteristics=`) which reliably land; matrix / range use the generic options.

### 12.3 HDR→SDR tone mapping (2026-09-09)
- Location: **"HDR→SDR tone mapping"** block in the right column of the "Advanced enhancement" window: enable checkbox + algorithm dropdown `hable` (good all-rounder) / `mobius` (keeps highlight detail) / `reinhard` (softer contrast).
- Chain: `zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=<algo>:desat=0,zscale=tin=linear:t=bt709:m=bt709:p=bt709:r=tv,format=<pix_fmt>`.
- **Requires HDR10 (PQ) / HLG tags on the source**; untagged HDR sources can't be force-converted with this build (zimg "no path between colorspaces"). A source already tagged SDR passes through with no side effect.
- With tone mapping on, clicking "Save and close" fills any still-"Follow source" color mark with bt709 primaries / bt709 transfer / bt709 matrix / tv range; manually changed values are left alone.

### 12.4 Region-effect family (2026-09-07: delogo-family registry + bleed padding)
The type dropdown in the video track's **"Remove logo / blur"** window gained a whole family of **region effects** beyond `delogo` / `boxblur` / `gblur`, driven by the `_REGION_EFFECT_FILTERS` registry (adding a type touches only the registry and the UI constant, not the generation logic):

| Type | Effect | Strength param | Class |
|------|--------|----------------|-------|
| `negate` | local negative | none | point |
| `hflip` / `vflip` | local horizontal / vertical mirror (often more natural than delogo interpolation when covering a watermark) | none | point |
| `swapuv` | local U/V swap (chroma glitch look) | none | point |
| `desat` | local desaturate `hue=s=0` | none | point |
| `eq_bright` | local brightness `eq=brightness=` | brightness (default −0.3) | point |
| `black` / `white` | local solid black / white cover `lutyuv=` | none | point |
| `unsharp` | local sharpen | strength (default 1.5) | neighborhood (convolution) |
| `avgblur` | local average blur | radius (default 5) | neighborhood (convolution) |
| `median` | local median (removes small specks / tiny logos) | radius (default 3) | neighborhood (convolution) |

- **Region / full frame: one switch** — check "Apply to selected region only" to act inside the coordinate box (`delogo` is always local, switch greyed out); leave it unchecked for a full-frame + show-window **time-segment effect**. Orthogonal to "show window / cycle show", freely combinable.
- **Bleed padding** — convolution types running on a cropped sub-image can't reach a real neighborhood at the border: the result differs from the full-frame run by 11.2 dB (visible square edge). Expanding by k px first (24 for blurs, 8 for unsharp/median) and cropping back drops it to 64.9 dB. Edge-touching / full-frame regions use `max(x−k,0)` / `min(…, iw−bx)` expressions so ffmpeg clamps — no shift, no out-of-range crop failure. Point operations have no seam and skip padding.
- Parameterless filters need an **equals sign** for `enable` (`hflip=enable='…'`); only filters with parameters accept a colon — the program decides automatically.

### 12.5 Division of labour with the Transcode page
Enqueue precheck / post-encode verify / size estimate, and the Transcode page's "Export / import project", **exist only on the Transcode page queue** (the mux page has no task queue). Items 12.1–12.4 above are the same shared panel on both pages.

---

## 13. Mask trajectory & edge feather (2026-09-10)

The "Mask / transparent overlay" dialog (see §9) gained two blocks: **edge feather** and **mask trajectory**. Together they turn the formerly static rectangle into a **moving "reveal shutter"**.

### 13.1 Unified mental model: the rectangle is a shutter pressed on the sub-video

The mask rectangle is no longer just a fixed transparent region — it is **a shutter that can move**. Its size × direction decides the effect:

| Rectangle size | Direction | Effect as it moves along a trajectory |
|---|---|---|
| Full screen (canvas size) | rectangle transparent (inside) | the shutter moves away, **permanently revealing** the sub-video where it passed (cumulative wipe) |
| Small rectangle (window size) | show only rectangle (outside) | only inside the box is the sub-video visible (**searchlight**) |
| Full screen | show only rectangle (outside) | reversed: from fully shown it gradually disappears |
| Small rectangle | rectangle transparent (inside) | reversed: the box is cut out, showing the main video |

> This model needs no "history accumulation" mechanism: occlusion is decided by the shutter's **current position**, so moving away undoes it — under a monotonic trajectory the visual result is equivalent to accumulation.

### 13.2 Parameters

- **Edge feather** (px, 0 = hard edge): 8–40 recommended; the larger, the softer the edge — visually a "gradual reveal". Implemented by appending `gblur=sigma=N` after the matte is built.
  - ⚠️ For a full-screen shutter wipe, make the rectangle **slightly larger** than the frame (about 2× the feather on each side), or the frame edges leak semi-transparency from the start.
- **Enable trajectory** + **Edit waypoints…**: reuses the same waypoint list as PiP (`build_waypoint_expr`) to give the shutter a movement path.
  - ⚠️ A wipe requires the trajectory to be **monotonic** (always moving the same way): if it doubles back, the sub-video is covered again where the shutter returns.
  - The list's **"Start coords… / End coords…"** open the visual editor to drag the shutter position directly; it uses `free_layout`, so the shutter can be dragged outside the canvas (a wipe inherently needs its start or end off-screen). Changing the shutter size in the editor is converted back into the rectangle W/H above.
    > Implementation note: when `_trajectory_dialog`'s `edit_cb` is `None`, these two buttons are **permanently greyed out** (independent of whether "Enable list waypoints" is checked). The mask hookup once missed passing it; `_mask_edit_cb` was added, plus a static audit `tests/_test_traj_editcb_audit.py` to prevent regression.
- Coordinates are always the **final rendered frame** of the sub-video (after crop→rotate→scale) — the local coords of "the sub-video you actually see". To do a full-screen wipe, scale the sub-video to the main video's size (then local coords ≡ frame coords).
- **Waypoint canvas = sub-video final rendered size** (after crop→rotate→scale, computed by `compute_final_size_with_order`, consistent with "single source of truth = final_render_size"): waypoints, shutter W/H, and the visual canvas share **one coordinate system**, so dragged coords are the final coords. The window shows the current canvas size (e.g. "canvas 1920×1080"); if it says "fallback", the sub-video size wasn't probed — pick the sub-video file first.
  - That size is saved with the waypoints into the project (`mask_traj_canvas_w/h`). At filter-build time the mask already sits after crop/rotate/scale, so `W`/`H` exactly equal this canvas size → the restore ratio is always 1 and the travel matches precisely; only old projects or an unprobed size fall back to 1280×720.
    > ⚠️ **Exception (2026-09-12)**: with **canvas mode** on, the mask segment no longer stays at the tail of the chain — it is appended **after the canvas composite** (see the note in §13.3), so the coordinate basis becomes the canvas size.

### 13.3 Filter chain

Without a trajectory it is still the original double-`drawbox` static matte — behaviour unchanged, word for word (zero regression). With a trajectory it becomes a dynamic matte:

> The mask filter's position in the sub-video chain **moved from "before crop (original-frame coords)" to "after crop→rotate→scale, before format=rgba"** (corrected 2026-09-10). Reason: the mask coordinate space must match the "final rendered frame", or the canvas (final size) and the filter (original frame) disagree and the dragged shutter position shifts wholesale. The static rectangle's `mask_x/y/w/h` and the trajectory waypoints now both land on the final rendered frame, isomorphic with `open_mask_dialog`'s canvas.

> ⚠️ **Canvas-mode exception (corrected 2026-09-12)**: the rule above — "the mask always sits after crop/rotate/scale" — does **not** hold in **canvas mode**.
> Canvas mode pastes the content onto a larger canvas (`build_canvas_filtergraph`), while the mask used to stay at the **tail of the pre-chain** →
> the mask acted while the content was still cropped to its original size, yet its coordinates were written back in terms of the **final canvas size** →
> the symptom was "turning canvas mode on makes the mask stop working / the shutter shifts wholesale".
>
> Fix: the former tail mask block was extracted into `_build_mask_filter_block()` (optional in/out labels; with both `None` it is byte-for-byte identical to before),
> and in canvas mode `build_canvas_filtergraph` **appends the mask segment after the canvas overlay**:
> `… → {out}_pre` (canvas composite) → `_build_mask_filter_block` → `{out}`. The mask coordinate basis thus equals the canvas size, matching what the editor shows.
>
> The predicate is centralised in `_canvas_defers_mask(settings)` (`canvas_mode and canvas_segments and mask_enabled`);
> `build_video_filter_chain(..., include_mask=False)` is the escape hatch that skips the tail mask.
> ⚠️ Both consumers must **always agree**, or you get a "double mask" or a "lost mask".
>
> Verified by `tests/_verify_canvas_mask_merge.py` (old vs new module diffed in one process — 5 non-canvas scenarios byte-identical = zero regression)
> plus `tests/_verify_canvas_mask_ffmpeg.py` (real ffmpeg: alpha=255 inside the rectangle, 0 outside; the old version reads luma 0 at the same point = bug reproduced).
> Known boundary: if the sub-video canvas has a "second-pass render scale", the mask still precedes that scale.

```
split=3[a][b][c];
[b]format=gray,drawbox=full-screen base colour[bg];
[c]crop='min(W,iw)':'min(H,ih)':0:0,format=gray,drawbox=inverse colour[bx];
[bg][bx]overlay=x='(<traj x>*W/canvas W)':y='(<traj y>*H/canvas H)'[,gblur=sigma=N][mk];
[a][mk]alphamerge
```

> Why not keep using `drawbox` for positioning? Measured: `drawbox`'s x/y expressions have **no time variable** — `t` is the value of the *thickness* option, and `T` / `n` report `Undefined constant`. A dynamic matte must move to `overlay` (x/y explicitly accept `t`).
>
> ⚠️ `overlay`'s x/y expressions likewise have **no `iw` / `ih`** (measured `Undefined constant or missing '('`); the main input's size uses **`W` / `H`** (= `main_w` / `main_h`). Here the main input is that full-size grey base, so `W`/`H` are exactly the sub-video frame size.

Timeline conversion matches "simple position" `crop_pos` and the watermark list trajectory: take the main video's trim/speed (`motion_trim_start`/`motion_speed_factor`, else `_trim_speed_from_settings`), segment time = main-video original time → converted to the output timeline.

---

## 14. Mask shape image (2026-09-10)

The "Mask / transparent overlay" dialog gained a **shape image**: load a custom shape (heart, star, any polygon — **any format**: png/jpg/jpeg/bmp/webp/gif/tif, the `movie` filter eats them all) to use as the matte instead of a rectangle. It shares the rectangle's "rectangle coords" (the shape bounding box), the 🎯 visual region picker, and edge feather. **Checking "Enable trajectory" makes the shape move along the trajectory** (heart searchlight / wipe; waypoints = the shape's top-left corner, with the same proportional restore and time conversion as the rectangle shutter).

### 14.1 Two matte routes (single-choice material type, auto-detected on load)

- **Black/white luminance image**: `format=gray` takes luminance — white = show, black = transparent. jpg/bmp naturally take this route.
- **Transparent-background block**: `format=rgba,alphaextract` takes the shape from the **alpha channel's opacity** — opaque = shape, transparent = background; **the block's colour is arbitrary** (a black block on a transparent background is the canonical asset).
- Auto-detection: on load, ffprobe reads `pix_fmt`; with an alpha channel (rgba/bgra/gbrap/ya8/yuva* etc., see `_MASK_SHAPE_ALPHA_PIXFMTS`) → "transparent-background block"; otherwise "black/white luminance". If detection is wrong (e.g. an 8-bit palette pal8 may or may not carry tRANS — conservatively treated as luminance) you can change the radio manually.
- **Invert black/white**: check when the asset's black/white semantics are reversed (applies `negate` to the shape route as a whole).

### 14.2 Filter chain

```
format=rgba,split=2[a][m];
[m]format=gray,lutyuv=y=0|255[bg];                     ← outside=0(black base) / inside=255(white base)
movie=<shape image>[pg];                                ← path: \ -> forward slash, : double-escaped \:,
[pg]format=rgba,alphaextract|format=gray                  with [ ] ' , ; -> hardlink rename in same dir
    [,negate(invert)][,negate(inside)],scale=W:H,format=gray[shp];
[bg][shp]overlay=x=X:y=Y[,gblur=sigma=N],format=gray[msk];   ← with trajectory, X/Y = trajectory expr
[a][msk]alphamerge                                              same as rectangle: '(<traj x>)*main_w/canvas W'
```

Implementation notes (all measured pitfalls — see `tests/_verify_mask_png.py`):
- **Use `lutyuv` for the base colour, not `drawbox`**: once `movie` introduces an rgb source, format negotiation drags `drawbox` into `yuva420p`, and drawbox's black on yuv = limited 16 → a full ring of alpha=16 leaks outside the shape; `lutyuv` is a LUT filter that stays gray, so 0 stays 0.
- **After the movie's single-frame EOF, overlay defaults to `eof_action=repeat`** and holds still (measured: alpha unchanged at t=2.5 s) — no `loop` needed.
- **Double colon escaping**: the filtergraph layer and the movie arg layer each eat one escape, so `C:/x.png` must be written as `movie=C\:/x.png` (the `\:`); the actual construction uses `.replace(":", "\\\\:")` (Python literal `\\:`); single escaping gets truncated by `avformat_open_input 'C'`.
- Path sanitizing: `_mask_shape_movie_path` (module-level, since `build_video_filter_chain` can't reach `self._movie_path_safe`) — backslash→forward slash + double colon escape + hardlink fallback for special chars, registered in `_PREVIEW_LINKS` and cleaned up on exit.
- Setting fields: `mask_png_enabled / mask_png_path / mask_png_invert / mask_png_type` (`type` participates in route selection → canonical English `bw|alpha`, a UI iron rule).

---

## 15. Mask multi-shape list (2026-09-11)

The "Mask / transparent overlay" dialog was rebuilt as a **delogo-style single dialog**: a **shape list** on top, the **selected shape's params** below; the former standalone "Multi-shape list…" dialog is gone. A sub-video can stack any number of shapes (plain rectangles or external shape images), each with its own coords, direction, time window / trajectory, and feather.

```
+ Mask / transparent overlay --------------------------+
| [x] Enable mask (applies to the current sub-video)   |
| + Shape list (add several; click "enabled" cell) --+ |
| | on | type | dir  | coords / summary              | |
| | v  | rect | only | 100x80@(0,0) [all]            | |
| | v  | ext  | thru | heart.png [3~8s]              | |
| +--------------------------------------------------+ |
| [Add][Delete][Up][Down]      click "enabled" cell    |
| -- Edit selected shape ---------------------------- |
| Direction: (o)only rectangle  ( )rectangle thru      |
| Coords (x / y / W / H, final frame) X[]Y[]W[]H[]     |
|                    [Visual region...]                |
| Edge feather:[   ]px (0=hard edge)                   |
| External shape image [path.........][Load][Clear]    |
|   material type (o)bw luminance ( )alpha block hint  |
|   [ ]Invert black/white (when semantics reversed)    |
| Time window: [  ] ~ [  ] s (end=0/blank = always)    |
| [x] Trajectory (move along path)   [Edit waypoints]  |
|                                      [Save] [Cancel] |
+------------------------------------------------------+
```

Editing works on a **local copy**: opening / cancelling doesn't touch stored data; on first open, if the list is empty but the old single-shape fields have values, they're migrated into one row; on Save, **row 0 is mirrored back into the old single-shape fields** (compat for old saves / old paths).

### 15.1 Type: auto-determined, no choice

- The "external shape image" field **blank** → plain rectangle (`color=` solid block).
- With a path → external shape image (`movie=` loads the image).
- The list's "type" column is display-only; there's no dropdown.

### 15.2 Direction: per row

Each row independently picks "only rectangle (outside)" or "rectangle transparent (inside)"; they can be mixed. The list's "direction" column mirrors it.

### 15.3 Time window: shapes are **parallel**, never truncated (key point, most misunderstood)

**Each shape's time window is independent; when windows overlap both shapes are active at once (parallel) — a later shape's window does NOT shorten an earlier one.**

Example (real ffmpeg per-pixel probe `tests/_probe_mask_time_overlap.py`) — A = left rectangle 0~3s, B = right rectangle 2~4s:

| Sample time | Left (A) | Right (B) | Note |
|---|---|---|---|
| t = 0.5s | 255 (bright) | 0 | only A |
| t = 2.5s | **255** | **255** | **A and B both visible** ← parallel, not A cut to 2s |
| t = 3.5s | 0 | 255 | only B (A ended on time) |
| t = 4.5s | 0 | 0 | both ended |

How overlaps composite → decided by **direction + list order** (**later row over earlier**, reorder with Up/Down):

- **All "only rectangle"**: visible area is the **union** (all blocks bright).
- **All "rectangle transparent"**: holes are the **union** (whole frame visible, each hole cut separately).
- **Mixed**: later row over earlier. E.g. A "only" 0~3s + B "rectangle transparent" 2~4s → during 2~4s, B **punches a hole** in A's visible area (probe t=2.5 shows alpha=0 at the hole).

> A single shape's **internals** (with a trajectory on) have their own rule: in the waypoint list, the first segment whose "end action ≠ keep" is the termination point; waypoints after it all go dead (see `build_waypoint_expr`). That's the shape's own business and doesn't affect others.

### 15.4 Time window and trajectory are mutually exclusive

- Checking **"Trajectory (move along path)"** makes that row's **time window ignored** and greys both boxes (visibility is delegated to the waypoints).
- Essentially a "time window" is the degenerate special case of a "trajectory": one static waypoint + end-action hide. Hence they sit adjacent (both at the bottom).

### 15.5 External shape image: the coords' **W / H are the render size** (the image is scaled)

- For a **rectangle**: W/H = the rectangle size.
- For an **external shape image**: the loaded image is **scaled to W × H** (`scale=W:H`), with the image's top-left at (x, y).
- So swapping in a differently sized image, if W/H stay the same, **the on-screen size stays the same**; to keep the image's own aspect ratio, fill W/H by the image's aspect (no auto aspect-fit).
- Probe-verified: load a 60×30 image with W/H = 40×20 → it occupies exactly **40×20** (alpha=0 beyond 40 wide / 20 high, including positions the original 30-high image would have hit).
- "Material type" (bw luminance / alpha block — which channel the shape is taken from) is in §14; the 🎯 visual region picker and edge feather also apply to shape images.

### 15.6 Implementation notes (fixes this round)

- ⚠️ **An external shape image leaks `alpha=16` (≈6% tint, a faint sub-video layer over the whole frame) outside the shape**: as soon as a `movie=` (rgb source) appears in the graph, ffmpeg's format negotiation routes the trailing `format=gray` through limited-range RGB→Y, turning black into 16. Fix: after drawing the base colour add **`extractplanes=g`** (byte-exact copy of the G plane; black = 0 exactly), the same fix as the old single-shape PNG path (reproduced and fixed via probe on 2026-09-11).
- The base is still **one matte**: `format=rgba,split=3` → base matte (base colour from the first shape's direction) + main alpha + shape sources; shapes `overlay` onto the same matte in list order (later over earlier) → one `format=gray` + `blend=all_mode=multiply` + `alphamerge`. The filter segment is generated by `_build_mask_multi_shape_filters`; an empty list falls back to the old single-shape logic (old projects keep working).

---

## Appendix — filter independence/linkage across the four modes (incl. Transcode)

Four working modes: ① Transcode ② Mux ③ PiP ④ Concat. Below, video filters, audio creative filters, audio reverse, and the intentionally-global filters.

| Filter class | Transcode | Mux | PiP | Concat |
|--------------|-----------|-----|-----|--------|
| Video filters (crop/scale/rotate/enhance/deint/speed/reverse…) | single video, own settings | main video own ✅ independent | main + each sub own ✅ independent | each segment own ✅ independent (+forced normalize) |
| Audio creative (volume/EQ/fade/denoise/loudness/channel/speed) | own ✅ independent | per-track own ✅ independent | per-track own ✅ independent | per-track own ✅ independent |
| Audio reverse | independent checkbox ✅ (not following video) | ✅ fully independent (no fallback to main) | ✅ fully independent | ✅ fully independent (external track independent; embedded audio only trims/resets, no longer follows video reverse/speed) |
| Subtitle burn-in `subtitles` | single video | global (main video, final picture) | main video only (global) | main video only (global) |
| Text watermark `drawtext` | single video | global | global (main) | global (main) |
| Forced spec normalize (scale/format/fps/sar) | none | none | none | ✅ intentional global (join required) |

**① Transcode — fully independent**
- One video, one (or zero) audio. Video reverse, audio reverse, audio speed, volume, EQ, fade… each its own checkbox/slider, no linkage. Audio reverse ("Audio reverse (independent of video)") defaults off; video reverse affects picture only. Check both to reverse together. No master "link/unlink" switch (by design — simplest). Intentional globals: subtitle burn-in & text watermark act on the only video; preview disables reverse (player limit).

**② Mux**
- Video: main video own settings, independent. Audio: each external track's codec/volume/EQ/speed/fade/reverse is per-track independent; "Audio reverse (independent of video, this track only)" controls itself only. Intentional globals: subtitle burn-in (`subtitles=`, main video, into the final picture), text watermark (`drawtext`). Tooltip notes "sub-videos can apply all filters except subtitle". (2026-08-28 restored: normal mux also supports main-video burn-in + charenc.)

**③ PiP**
- Video: main + each sub own filter chain, independent. Audio: each track fully independent; audio reverse pure-independent. Intentional globals: only main video's subtitle burn-in & text watermark (sub-videos can't burn subtitles — a compositing-layer limit, not an omission).

**④ Concat**
- Video: each segment (main + subs) own filter chain; at each segment's end, scale/format/fps/setsar are forcibly appended (from main video) — an intentional global required for join compatibility, no exception.
- Audio:
  - **External tracks**: per-track independent; audio reverse / speed are pure-independent (set in the audio-track settings).
  - **Embedded audio**: **fully independent** — only trim and base PTS reset, **no longer follows that segment video's reverse/speed**. If you reverse/speed a segment's video and want its embedded audio synced, set reverse/speed yourself in a separate audio track; otherwise embedded audio plays forward at normal speed.
  - **Per-segment audio duration clamp (prevents cumulative drift)**: concat joins in sequence, so each audio segment occupies = its processed duration. When a segment's audio gets "time offset align" (`adelay`, padding N s of silence at the head to lengthen it), speed, or trim, without a tail fix the A/V cumulative difference at each boundary grows with segment count (the more segments, the more skewed). So at the end of every audio segment's chain, append `atrim=0:T_i,apad=whole_dur=T_i` (`T_i` = the matching video segment's processed duration): over-long tails are cut, short ones padded with silence to exactly `T_i`, making **each audio segment's total duration identical to its video segment's** — cumulative drift gone. Both the external-track path and the (fallback) embedded-track path do this clamp; embedded audio also follows its video segment's speed/reverse so its natural duration already equals the video segment, avoiding silent truncation.
    - **Audio transition (acrossfade)**: audio segments map 1:1 to video segments and follow the matching video segment's transition toggle via `acrossfade` (duration matching the video transition); the transition region is A/V-synced with no seam; adjacent audio segments without a transition stay hard-cut. Total audio duration = Σ video segment durations − Σ transition durations, fully aligned with video.
  - **Global background music (BGM)**: only the **main video (first segment)**'s "Audio binding" tab offers a "Mix background music" toggle + file picker + volume slider (default 0.3). When enabled, the external audio **loops to fill the entire merged output**, lowered to the set volume, and **mixed under the existing audio** via `amix` (normalize=0, doesn't duck the original). Concat mode no longer uses 1:1 segment mapping for "independent external tracks" — that binding semantics was never implemented and a track/segment count mismatch would drop audio from some segments; it is now replaced by this global BGM.
- Intentional globals: subtitle burn-in (main only), text watermark (main only), plus the forced spec normalize above.

**Summary**
- Video & audio creative filters: all four modes are per-track independent.
- Audio reverse / speed: all four modes are now fully independent — no "audio follows video" fallback remains (Mux dropped "audio reverse falls back to main"; Concat dropped "embedded audio falls back to segment video reverse/speed"). Each audio track's reverse/speed is decided solely by its own audio-track settings.
- The only remaining "following" is the intentional global: subtitle burn-in, text watermark, and Concat's forced spec normalize. These are meant to be global, not linkage. All three mux-page modes (normal-mux / PiP / serial-concat) support subtitle burn-in with charenc (restored & completed 2026-08-28).
