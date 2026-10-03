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
- **"Multi-stream sync reference"** — open the multi-track waveform alignment window and export each track's `-ss/-to` trim times, or write them straight back into the tracks' trim settings (see Chapter 16).

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

The same **Loop / Chroma** tab also has a per-sub-video **"Audio:"** mode dropdown (Default / Ignore / Mix / Replace) controlling how that sub-video's audio is handled — see §17.

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

## 16. Multi-stream sync reference (multi-track waveform alignment → trim-time export, 2026-09-13)

Say you have several versions of the same content (different cameras, different recording start points, re-uploads at different quality) and want to cut **exactly the same segment** out of each — trying time codes by hand for every file is painful. **Multi-stream sync reference** solves this: it overlays each track's audio waveform on one shared timeline, aligns them, and computes every track's `-ss/-to` trim times in one pass.

### 1. The window at a glance

- **Entry**: track-list right-click **"Multi-stream sync reference"** (right after "Create thumbnail"). Accepts 2–6 video tracks; each track gets its own waveform lane, stacked vertically, all sharing one timeline (x-axis = reference track time).
- **Read-only by default**: the window only displays and copies times and **will not touch track data on its own**. Use the times on the Transcode page, or hit **"Write back times"** (bottom right, with a confirmation dialog) to push them straight into each track's trim settings — see Step 4 below.
- **Waveform gain**: each track is auto-normalized to be visible (96th-percentile baseline, shown as "Display gain ×N" on the lane header). On long videos with a large loudness range some sections may still look like a flat line — type a multiplier into the lane header's "Gain ×" box (**press Enter to apply**, leave empty to return to auto), or click "Regenerate waveforms" at the top to re-decode. Gain affects display only, never data.
- **Per-lane header buttons**: `Play` / `Time preview` / `Sync cursors` / `Set start (all)` / `Set end (all)`. "Align by cursors", "Grab current frame" and "Read back from trim" sit at the bottom of the window; "Copy time" and "Write back times" at the bottom right.
- **Sync cursors** (2026-09-14, left of "Set start (all)" on every lane): moves **every other track's cursor** to the same moment as this track's current cursor (same offset back-calculation as "Set start (all)") — **cursors only: no anchor written, offsets untouched, drift not recomputed**. Workflow: click the event on this track → "Sync cursors" → check all waveforms land on the same instant → only then click "Set start (all)" to actually mark. Negative times clamp to 0.
- **Grab current frame** (right of "Align by cursors", 2026-09-14): grabs the frame at **each track's own cursor** and tiles them into a grid for side-by-side comparison — if the alignment is right, every tile should show the same instant. Scaling keeps the original aspect ratio (portrait clips are pillarboxed, never stretched) and the whole window always fits on screen. The window stays open: move cursors and hit "Re-grab" inside it.
- **Copy time** (left of "Write back times"): copies just the `-ss X -to Y` of the **selected table row** (no track name), ready to paste into a trim window or command line. With nothing selected it falls back to the "current track" row.
- **Write back times** (bottom right, 2026-09-14): writes the current "Start"/"End" anchors **back into each track's trim settings** (`trim_enabled` / `precise_trim` / `trim_start` / `trim_end`; video tracks and their same-source audio tracks share the same keys), after a confirmation dialog; the main window's track list and command preview refresh immediately. This is the only action in this window that modifies track data — see Step 4.
- **Read back from trim** (2026-09-14): reads each track's existing trim values (`trim_start`/`trim_end`) into the "Start"/"End" slots and recomputes offsets as "reference start − own start". Last session's result can therefore be recovered straight from the tracks — perfect for continuing where you left off.
- **Saving alignment state** (2026-09-14): "Save alignment…" / "Load alignment…" on the top row export/import a JSON of offsets, cursors, start-end anchors and the reference track. Closing the window also autosaves to `sync_ref_last.json` in the config folder, and reopening the window with **the same tracks** restores it automatically (matched by **file path + occurrence index**: changing the selection order still matches, and when the **same file appears several times** — e.g. several clips cut from one source — the k-th occurrence pairs with the k-th, so each one lines up on its own; partial matches restore what they can and say so). So there is no need to stash the copied times in a scratch file any more.
- **Not always on top**: the window deliberately does not pin itself over the main window, so you can freely switch to the main window (e.g. to paste times). Tick **"Always on top"** on the top row when you do want it pinned.

### 2. Recommended workflow

#### Step 1: find a landmark, align by cursors

1. On **one waveform**, click "Play" and pick a sonically distinctive moment that also exists in the other tracks (a drum hit, a line of dialogue, a door slam), and park the red cursor on it.
2. Move to each other waveform, find **the same landmark** — play back and forth as often as needed to confirm — and park its cursor on the same spot.
3. Once every track's cursor is placed, click **"Align by cursors"** at the bottom: each track shifts by "reference cursor − own cursor", and the waveforms line up in columns.

> Too lazy to click track by track? Use a lane's **"Auto-find point"** (on the "cursor −1 frame / +1 frame" row): it takes the 0.3 s of audio at the current track's cursor as a template and cross-correlates it against the other tracks, accurate to about 0.1 ms.
>
> **Search range = the dropdown right of the button, ±45 s by default**: it searches in the small window first and stops as soon as it finds a "good enough" match; only if none is good enough does it widen step by step (`±5 → ±15 → ±45 → ±120`).
> Already roughly aligned with a tiny offset → pick **5** (fastest and sharpest); off by tens of seconds with no idea where → pick **45** or **120** (slower, so check twice).
>
> On a hit the status bar states **"matched within ±N s, similarity X"** — a low similarity (<0.35), or another equally plausible candidate region, is flagged separately as "match not unique" for you to verify. A hit **only moves the cursor — it never writes anchors**: confirm, then click that lane's "Set start (all) / Set end (all)".
>
> ⚠️ **The cursor must sit on actual sound.** Landing on silence fails outright (it reports "the current track's cursor is almost silent (level x/32768)") — silence only matches silence, so the result would necessarily be wrong; better not to run it at all.

#### Step 2: set the start point (all)

1. Find the track that sits **furthest to the left** (the one with the smallest start time — track 1 in the example below). After alignment all tracks point at the same content; the one with the smallest source time is the start baseline.
2. Use its very beginning (0 s) as the start; or if the opening should be skipped (say a 6-second intro), open that track's **"Time preview"**, jump past the intro and click **"Set as start"** — the cursor moves to 6 s.
3. On that track's lane header click **"Set start (all)"**: using that track's cursor as the baseline, a start point is written for **every track** via the already-aligned offsets.

#### Step 3: set the end point (all)

1. Pick the track to serve as the **end reference** (track 2, say), open its "Time preview", find the end time and click **"Set as end"** to move the cursor there.
2. On that track 2's lane header click **"Set end (all)"**: the end point is likewise written for all tracks.

#### Step 4: write back the times

Once alignment and anchoring are confirmed, click **"Write back times"** (bottom right) — it writes each track's "Start"/"End" into that track's **trim settings** (`trim_enabled` / `precise_trim` / `trim_start` / `trim_end`), covering **video tracks and their same-source audio tracks** (audio tracks of the same file) together; tracks missing a start or an end are skipped and listed. A confirmation dialog appears first (this is the only action in this window that rewrites the mux page's track data); afterwards the main window's track list and command preview refresh immediately.

> To check manually, or to take the times elsewhere, click **"Copy time"** instead: it copies just the `-ss X -to Y` of the **selected table row** (no track name), ready to paste into a trim window or command line.
> Table columns: track name / trim times / segment length / start diff / end diff / drift (diffs = this track − base, positive = the event happens later on this track; the base row is always "—"). Matching segment lengths and 0.000 drift mean the start/end points are clean. (Labels follow the UI language — "基准" in Chinese, "Base" in English.)

```
Base · 123.mp4	-ss 93.815 -to 171.207	77.392	—	—	—
Cmp1 · 321.mp4	-ss 6.567 -to 83.959	77.392	-87.248	-87.248	+0.000
Cmp2 · 1234.mp4	-ss 181.141 -to 258.533	77.392	+87.326	+87.326	+0.000
```

#### Step 5: verify on the Transcode page

1. Switch to the Transcode page and double-click a track to open its **Trim segment** window — the start/end times are already the values written back in Step 4, and **"Frame-accurate"** has been ticked too (frame-precise trimming; switches to re-encoding).
2. If you prefer to do it by hand, you can still click **"Import times"** there to read `-ss start -to end` from the clipboard and fill the start/end boxes.
3. Just start the conversion. Repeat per track.
---

## 17. Loop/Chroma page sub-video audio mode (Default / Ignore / Mix / Replace, 2026-09-18)

On the Loop / Chroma control tab (the sub-video settings window), an **"Audio:" dropdown** sits to the right of the Transparency / Mask row. It controls **how that one sub-video's own sound is handled** — each sub-video is set independently, with no effect on the others.

### 1. Choosing one of the four modes

| Mode | Effect | When to use |
|------|--------|-------------|
| **Default** | The sub-video's sound is kept as an **independent audio track** (exactly the old behaviour). | You just want to overlay the sub-video and keep its sound as its own separate track. |
| **Ignore** | Drops the sub-video's sound, keeps only the picture. | Silent watermark / silent corner logo — you do not want the sub-video to make any sound. |
| **Mix** | The sub-video's sound is **mixed into the main audio** instead of becoming a separate track. | You want the sub-video's narration / sound effect to blend naturally into the main audio. |
| **Replace** | On top of the main audio: **while the sub-video is displayed, the main audio is muted and the sub audio takes over**; once that stretch ends, the main audio returns. | You want to "cover" the main audio while the sub-video is on screen and hear only the sub-video (e.g. inserting a voice-over). |

**The key point — only two of the four are "sound and picture come and go together":**

- **Mix / Replace**: the sound follows this sub-video's **display range** exactly — audible inside the range, muted outside it. The range is the start ~ end of the "display period" on the same page (the loop count decides how long the range is). The picture appears, the sound starts; the picture disappears, the sound stops.
- **Default**: this one is **keep an independent track** (exactly as before) — the sound **does not follow the display range and is not synchronized with the picture**: it starts at 0 s and, following the sub-video's own looping, runs to the end of the movie. So if the display period does not start at 0, you get "the sound is already playing before the picture appears"; and after the picture is long gone, the sound is still playing. **If you want sound and picture to come and go together, choose Mix or Replace.**
- **Ignore**: there is no sound at all, so there is no range to speak of.

### 2. How it works with background music (BGM)

If you also enabled "Background music (BGM)" on the main video:

- **Replace**: the main audio is muted inside the display range, but **BGM keeps playing underneath** — during that stretch you hear "the sub-video's sound + BGM", not dead silence. (With BGM off, only the sub-video's sound is heard inside the range.)
- **Mix**: BGM is layered together with the mixed main + sub audio, still one audio track in the end.
- **Default / Ignore**: BGM stays under the main audio as usual; in Default mode that sub-video's independent track is an **extra** one and is not folded into the BGM track.

### 3. Things handled automatically

- **The sub-video has no audio track**: Mix / Replace automatically degrade to "Ignore" — no error, and the main audio is not muted.
- **Several sub-videos using Mix / Replace at once**: each is active during its own display range; overlapping parts simply add up and never "eat" each other. Mix on one and Replace on another behaves the same way: the main audio is muted over the Replace range, and the Mix sub still stacks on top.
- **The main video itself has no sound**: Mix / Replace use a silent bed, so the output contains only the sub audio (plus BGM if enabled) — no error.
- **Mismatched sample rate / channels**: everything that joins the mix is normalized to one spec automatically, avoiding clipping or channel misalignment.

### 4. How many audio tracks you get

| Mode chosen for this sub-video | Change in output audio tracks |
|---|---|
| **Mix / Replace** | Folded into the main audio track (BGM is in that same track too) — **no extra track** |
| **Default** | **+1** independent track (one per such sub-video) |
| **Ignore** | **no extra track** |

### 5. One-sentence summary

**The "Audio" dropdown picks, for this sub-video: while it is on screen, is its sound gone for good (Ignore), its own separate track (Default), blended into the main audio (Mix), or taking over the main audio (Replace)?** For Mix / Replace the range follows the picture — nothing extra to set up.

---

## 18. PiP transitions (cross-dissolve between clips) & audio alignment (2026-09-25)

> This chapter covers the three things added recently: **transition (cross-dissolve)**, **transition alignment**, and **audio follows transition**.
> The preconditions are spelled out in as much detail as possible, because **none of them takes effect on its own** — miss even one and it silently does nothing (the command line shows no transition, so it looks like the feature is broken).

### 0. Start with the model: this is a "real timeline"

To make sense of every rule below, fix the mental model first. **The PiP capability is, at heart, a real timeline (the Shotcut kind)** — not the old PiP where a small window floats on top of the main video:

- **Every clip sits on one shared timeline**, and each one's own "Display start / end" (or the window derived from a finite loop count) decides **which stretch of the timeline it occupies** — that is that material's in / out point.
- **The main video is the first clip**: the timeline is measured from it; when later materials are placed beyond it, the tool automatically pads the bottom with black frames (the timeline extends to the latest clip's end).
- **The picture hands off according to the windows**: previous clip's end ≈ next clip's start ⇒ the picture switches over naturally; overlapping windows mean two clips on screen at once (small window or full screen, whichever you placed — overlap is a legitimate state of a real timeline, not an error).
- **A transition is not part of the model itself; it is an optional effect added at the seam.** If the clips butt head-to-tail and both durations are detectable, a fade / wipe etc. is inserted at the cut; if they do not, it falls back to a hard cut. That is where all those preconditions come from — the tool has to be able to **lay out the timeline** (how long each clip is, where it starts and ends) before a transition can be attached at the seam.
- The three features each cover one thing in the model: **transition** = the effect at the seam; **transition alignment** = placing the in-point exactly at the seam (the start number = the real switch moment); **audio follows transition** = making this clip's sound follow the seam (picture and sound cut at the same instant).

> Implementation note (does not affect usage): underneath it all this is overlay compositing plus black-frame padding at the end of the main video, **not a concat filter chain** — so it is more expressive than serial concat (clips may overlap, may be small windows, position is preserved per clip). **Serial concat / Concat mode** is the real concatenation; keep the two apart. For our purposes, just remember the name **"real timeline"**.

In one sentence: **use it as a real timeline first (arrange the clips, butt them together), and only think about a dissolve once you want one.** The triggers, the alignment formula and the audio follow below are all details of that model.

### 1. What the three are, and where you see them

| Feature | What it is | Where (PiP only; serial concat has its own) |
|---|---|---|
| **Transition (cross-dissolve)** | A fade / wipe / slide etc. between the previous clip's picture and the next one, instead of a hard cut | The "Enable transition" checkbox on each video track's **Fade in/out** tab (greyed out on the last clip) |
| **Transition alignment** | A button that computes a clip's "display start" as the exact moment the picture really switches to it | **Sub-video only** (not the main video), on the **Fade in/out** tab; the main video tab also has "One-click transition (all)", which aligns every clip while it goes |
| **Audio follows transition** | A checkbox that makes this clip's sound follow the transition, frame-accurate against the picture, and still gives only one audio track | **Sub-video only** (not the main video), on the **Fade in/out** tab — **off by default** |

> Note: all three only appear / take effect **in PiP mode**. Serial concat mode has its own transitions (ch. 8 §2, similar mechanism, but the concatenation rules differ) and is not affected by the alignment / audio-follow rules of this chapter.

---

### 2. ⚠️ When a transition really takes effect (chaining) — all four conditions

Tick a checkbox and the effect is not guaranteed. **All** of the following must hold, otherwise the tool silently skips it (no transition in the command line — it looks like nothing happened):

1. **It must be PiP mode.** (Blunt, but let's state it.)
2. **The previous clip must have "Transition" ticked** — the transition hangs on the *previous* clip and controls the "previous → this" dissolve.
   - Example: for clip1 → clip2 to dissolve, tick **clip1**'s transition box (clip2's box controls clip2 → clip3).
   - Ticking transition on the main video makes it the head of the chain, and it dissolves with the sub-video whose display start ≈ the main video's duration.
3. **The two clips must butt head-to-tail on screen**: the previous clip's "display end" ≈ this clip's "display start" (differences of no more than half a frame).
   - A gap in the middle, or two overlapping clips ⇒ no chaining; each clip displays on its own, independent of the other (hard cut).
4. **Both the previous and this clip need a finite display duration.** Any one of these:
   - ① A "Display end" time filled in on the **Loop/Chroma control** tab (both start and end filled ⇒ the window is bounded);
   - ② or "Enable loop control" ticked with a **finite** loop count (not "loop forever").
   - If a clip has "no end filled in + loop forever", the tool cannot detect its length ⇒ no chaining ⇒ the transition silently does nothing.

Additional automatic rules:

- The transition duration is automatically clamped to **half the duration of the shorter** of the two neighbouring clips (so it is never so short that it errors).
- The transition "eats" its own duration: the next clip appears **earlier** by that many seconds than where you placed it on screen (the picture has already cut over). That is what transition alignment exists to fix (see §3).
- **Position / trajectory / rotation are preserved across the transition**: each sub-video taking part first bakes its picture (with your overlay position, trajectory motion, rotation offset, scaling) into a transparent canvas the same size as the main video, and only then transitions —
  - you place both sub-videos in the bottom-right ⇒ the transition happens in the bottom-right, and the main video shows through the transparent area outside the small window;
  - no stretching either: the sub-video keeps the size you set, and the surplus is transparent;
  - the same holds when the main video has a transition ticked (the main video joins the chain): the main picture dissolves into "the sub-video in the bottom-right corner", and the position is not lost;
  - exception: a sub-video in **blend mode does not take part in transitions** (it needs to be computed pixel by pixel against the main video, and a transition chain is an independent picture that cannot do that). Everything else (rotation / trajectory / sub-canvas) can join the chain.

> **In one sentence:** for clip A → clip B to have a transition, tick transition on clip A, make A and B butt head-to-tail, and give both a finite display window.

---

### 3. Transition alignment — how to use it, and when it applies

- **It is a manual button; it never runs by itself.** The command generator does not call it — it only applies when you click. "Don't click anything" = exactly as before, with no effect on any existing project.
- **The formula (at a glance)**:
  ```
  this clip's start = previous clip's start + previous clip's length − previous clip's transition duration
  ```
  - Example: main video 12 s, transition 2 s ⇒ the first sub-video starts at 12 − 2 = **10 s** (the picture cuts over at 10 s, not 12 s).
  - For the next one: keep accumulating from the "new start" computed for the previous clip.
- **Which clip it refers to**: always the **clip immediately before it in the track list** (in the order you added the files) — **not** the order the clips sit on screen. Otherwise, when you drag some clip later, the tool would take the clip *after* it to be the "previous" one (a bug we hit before: aligning #2 used #3's timing).
- **Precondition**: the previous clip must have a detectable display length (start and end filled, or a finite loop count). If it cannot be detected, a message pops up asking you to set it first.
- **The "end" moves along with it; the clip length does not change**: shifting only the start would stretch the clip, so the end moves by the same amount.
- **One-click transition (all)**: clicked on the main video's **Fade in/out** tab, it turns on transitions for every clip at once and performs the alignment as it goes (no dialog, log lines only).

---

### 4. Audio follows transition — how to use it, and when it applies

- It is a checkbox on the sub-video's **Fade in/out** tab — **off by default**.
- Once ticked, it **automatically switches the "Audio:" dropdown on the Loop/Chroma control tab to "Mix"** — so you don't need to tick Mix yourself; from then on everything is mixed into a single audio track on output (same rule as audio-follow in serial concat mode).
- It drops this clip's sound **exactly at the moment the picture really cuts to it** (the cross point of the transition), so picture and sound are frame-aligned — no more "the picture cut early while the sound is still sitting where it was".
- **Preconditions (on the video side; all must hold, or this checkbox does nothing)**:
  1. The previous clip has a transition on and butts head-to-tail with this one (i.e. "chained", as in §2);
  2. This clip has a finite display window (same as §2 condition 4: display end, or a finite loop count).
  - If it is not chained, ticking it changes nothing; the sound stays at its original display position (identical to not ticking it).
- **You do not trim the audio yourself**: it is cut and positioned automatically from this clip's display window (start + end, or the finite loop count); adjusting the display window is adjusting the audio window.
  - If you want that "picture and sound separate, audio offset independently" kind of freedom (like Shotcut), that is a different feature and is not implemented yet; for now audio is bound to the display window.

---

### 5. How this differs from before the upgrade (when PiP had no transitions at all) (key point)

> "Before the upgrade" here means **versions in which PiP had no transition capability at all** — back then clips could only hard-cut: no dissolve, no alignment, no audio follow. It is not a comparison against some intermediate version.

| Scenario | Before (PiP had no transitions) | After (now) |
|---|---|---|
| How clips switch | **Hard cut only**: the instant the previous picture ends, the next frame is immediately the next clip — no effect whatsoever | A "Transition" checkbox (hangs on the previous clip); once ticked, a fade etc. plays **between** the two (preconditions: butt head-to-tail + both have a finite display window) |
| Where the start goes | No transitions, so the "off by one transition duration" problem did not exist; the clip started wherever you placed it | With transitions the start is easy to mis-place ⇒ a "Transition alignment" button, plus one-click transition aligning everything as it goes; the start number = the real switch moment |
| Sub-video audio | The "Audio:" dropdown existed (Default / Ignore / Mix / Replace), but you had to **select Mix by hand** for it to join the main sound | The dropdown is still there and its default behaviour is **unchanged**; additionally "Audio follows transition": ticking it **automatically** switches audio to Mix **and** aligns it to the transition cross point — no more manual Mix |
| Sound once a transition is on | Not applicable (there were no transitions then) | With a transition on but **"Audio follows transition" left unticked**, the sound stays at its original display position and drifts from the picture across the dissolve; only with it ticked are picture and sound frame-aligned |
| Sub-video position / trajectory / rotation | Always worked (no transition ever touched them) | Still **all work** (participating clips bake into a unified canvas before transitioning, position kept per clip); the only exception is a blend-mode sub-video, which does not take part in transitions |
| Configuring nothing | Auto-loop and end at the main video's duration | **Exactly the same** (every new feature needs a click / tick; the defaults change nothing for existing projects) |

> The key point: **all the new capabilities are "only after you click / tick", and the defaults keep the old behaviour.** Carrying on as before with auto-loop and ending at the main video's duration is perfectly fine; the output only changes once you actually use transitions / alignment / audio follow.

#### One level deeper: what the real-timeline model itself brings (before the model → after)

The table above compares "transition capability or not". Here we go one level further and compare with **the old PiP, before the real-timeline model existed** (main video as the bottom layer, output duration always equal to the main video's duration). Back then, placing a sub-video's start beyond the main video's duration meant the tool **would not extend the output duration by itself, nor auto-fill the related parameters**; the concrete differences:

| What you want | Before the model (old PiP) | After the model (now) |
|---|---|---|
| Place a sub-video's start beyond the main video's duration | **The output duration does not extend**: the total is still computed from the main video; and because "the main input ends = the whole output ends" for overlay, `-t` can be as large as you like and you still get no frames ⇒ **the sub-material disappears completely**, with not a word of warning | It scans every clip's window end and takes the largest ⇒ the main video's tail is **automatically padded with black frames** (`tpad=stop_mode=add`, exact to zero error), the total duration uses the new value and the sub-material appears in full |
| A dissolve between two clips | PiP had no transitions; even if you hand-craft `xfade` into the command, clips with **different size / frame rate / SAR fail outright** (`size ... do not match` / `timebase ... do not match`), so you had to add the `scale` + `setsar` + `fps` trio yourself, compute `offset` by hand and clamp the transition duration to half the shorter clip — miss one step and it errors or degrades | Just tick a transition: participating clips are **normalized automatically** (with the unified canvas you don't even need resizing), `offset` is computed for you and the duration clamped for you; clips without a transition get zero normalization |
| Warnings for clipped / infinite windows | **Total silence**: clips with an infinite window cannot be measured, get cut wholesale, and cannot chain with their neighbours — not a word in the log | The log calls them out: when a clip's start lies beyond the output duration but its window is infinite, it warns "Did you forget to give this material a finite duration?" (see ch. 18 §7, first FAQ) |

> One sentence: before the model, "placing it outside the main video = placing it for nothing", and a dissolve meant hand-crafting filters and filling in every parameter; after the model the timeline extends by itself and every transition parameter is filled in for you — your remaining job is "give each clip a finite window + tick transitions".

---

### 6. Recommended order of operations (to avoid pitfalls)

1. Switch to PiP mode, add the main video and the sub-videos.
2. For each clip: on the **Loop/Chroma control** tab, give it a **finite display window** (fill "Display end", or tick "Enable loop control" with a finite count).
   → If you are unsure whether the timeline has gaps / overlaps, open 【ch. 20, Timeline overview】 and see it all at once (right-click menu → "Timeline overview").
3. Tick "Transition" clip by clip (main video → sub 1 → sub 2 …); pick the type and duration as you like.
4. On each sub-video's **Fade in/out** tab: first click "Transition alignment" (start computed from the previous clip), then tick "Audio follows transition" (auto-mix + positioned).
   - Or take the lazy route: click "One-click transition (all)" on the main video tab to turn everything on and align in one go, then tick "Audio follows transition" per sub-video.
5. Preview / export.

### 7. FAQ (why nothing happened when I clicked)

- **Q: I ticked the transition but the command did not change?**
  → Most likely: an infinite window (no end filled + loop forever), or the previous clip has no transition, or the two clips do not butt head-to-tail. Go back to §2's four conditions and check them one by one.
  → Since 2026-09-25 the log calls it out: when a clip's start lies beyond the output duration but its window is infinite, it warns "Did you forget to give this material a finite duration?" — seeing that line means condition 4 (finite display window) is not met.
- **Q: I ticked audio follow but still get several audio tracks / the sound is still off?**
  → It has to be "chained" first (previous clip transitions + head-to-tail) for the tick to do anything; not chained it is a no-op, and the sound stays at its original display position (same as not ticking). When you tick it you should see the "Audio:" field on the **Loop/Chroma control** tab flip to "Mix" automatically; if it did not, it is not chained.
- **Q: The sound is still earlier / later than the picture?**
  → That means it is not chained and the audio is at its original display position. First confirm that a transition really appears in the command (chaining succeeded), then tick audio follow.
- **Q: Aligning clip 2 used clip 3's timing / clip 3 treated itself as clip 2?**
  → An old bug that has been fixed: alignment always takes the clip immediately before it in the **track list order**, and no longer sorts by the times you placed on screen. If it still misbehaves, make sure you have not messed up the clip order.
- **Q: I set an overlay position / trajectory / rotation on a sub-video, and after enabling transitions all of that is gone?**
  → Not since 2026-09-25 (the unified-canvas approach): every sub-video taking part bakes its picture (position / trajectory / rotation) into the unified transparent canvas before transitioning, so position is kept per clip, size is not stretched, and the main video shows through the transparent parts. If a position still gets lost, check that you have not put that sub-video in blend mode (blend does not take part in transitions).

---

## 19. Nodes: Video node / Audio node (2026-09-25 / 2026-09-26)

> This chapter covers two entries: **Video node** and **Audio node**, both in the right-click menu.
> One-line purpose: **treat some position in the middle of the processing chain as an independent piece of material, and give it its own set of effects.**

### 1. First, what a "node" is

A PiP / serial concat command is internally one processing chain, with several intermediate outputs on it (for example, a new branch created after `[1:v]` has been scaled and cropped). **A "node" is the position of one of those intermediate outputs.**

- Select a node → a set of effects is applied to **everything after** it (picture / audio); nothing in front of it is affected.
- The effects are keyed by a "position fingerprint" in `node_fx`, and **every time the command is regenerated they are automatically re-inserted after that node** — no manual command edits, no intermediate files.

### 2. The two entries and their scope

| Entry | Available in | Editing window it opens |
|------|---------|-------------|
| **Video node** | **PiP only** (greyed out outside PiP) | "Video track settings", treated like an ordinary video track: crop / rotate / trajectory / the region-effect family… |
| **Audio node** | **PiP + serial concat** (greyed out in plain mux) | "Audio track settings": volume / loudness normalization / channels… |

The two **do not overlap**: the video-node list only shows picture segments, the audio-node list only audio segments.

### 3. Video node: how to pick and configure

1. **Right-click** → "Video node" → the command preview refreshes once automatically to pull out the current processing chain.
2. A "Video node" window pops up: a two-level tree on the left (level 1 = processing stage: main chain / sub chain / overlay / transition / final; level 2 = nodes), each row showing index, last filter, size and **mounted effects**.
3. Select a node → the right pane shows, **inside the window**, that node's real picture at the "frame-grab time" and its real size (including effects already mounted in front of it). Frame grabbing goes through an in-memory pipe, **nothing is written to disk**, and the list stays clickable while grabbing.
4. Confirm → the "Video track settings" window opens, and you configure it just like an ordinary video track.
5. Save → "N node effects recorded"; the command preview refreshes along with it.

**Typical scenario (de-logo / watermark removal)**:

1. **The problem**: the logo occupies a whole corner, so applying `delogo` directly is still harsh — two edges have no suitable reference pixels.
2. **Overlay a layer to supply reference pixels**: overlay one layer on the video — **crop a suitable background and stretch it into that corner**, to give those two edges some reference pixels; alternatively overlay a pre-prepared PNG.
3. **At this point the main video and this overlay layer are still separate** (the overlay is its own branch; it does not modify the main video's original pixels there).
4. **Before, this program could only do it in two passes**: export once, reload the output file, then apply `delogo` to that.
5. **Now**: apply `delogo` once more directly on the **right node** — **one pass**, small picture loss.

### 4. Audio node

Same flow as the video node, except you pick an audio intermediate node and the "Audio track settings" window opens.
Common use: **add one loudness normalization at the last node** (`loudnorm` and friends), so a single pass brings every clip to the same loudness. Middle audio nodes have very few usable filters anyway.

### 5. Positioning mechanism, and re-picking when a node is missed (important)

- Nodes are **not located by label name**; they are located by the fingerprint "**clip index + last filter name**".
- The upside: with cascaded PiP, every `amix` output may be named the same, and by name you would grab the wrong one; the fingerprint hits the exact spot.
- The cost: **if the processing chain changes** (a stage added / removed / toggled), the position may no longer be found → the tool **skips it and warns**; it will never quietly apply it in the wrong place. Go back to "Video node / Audio node" and pick the node again.
- Labels sharing a name get a "n/m same name" suffix to tell them apart; after selecting one, the panel below shows "Original label: [real name]".

### 6. Known limits

- **Branches are not offered**: only nodes with a "single output label" appear in the list (a node fanning out to several streams has unclear semantics; out of scope this round).
- Node effects only work in the **PiP / serial concat** chains; plain mux mode has no intermediate nodes.
- Several effects can be mounted on one node; the "Mounted effects" column shows a summary.

---

## 20. Timeline overview (PiP only, 2026-09-27)

> This chapter is the **visual counterpart** of the "real timeline" in **ch. 18**: one timeline shows every clip at a glance, and you can drag them.
> Details are not repeated here — every button / gesture also exists as a same-named control on the mux page's **"Loop/Chroma control"**, **"Fade in/out"** and **"Sub-video control"** tabs, and hovering the mouse over them gives the full description. **This chapter only lists what is different from those other places.**

**What it is**: every PiP video track has a "display period (display start / display end)", which is easy to miss when you edit them one by one; this window draws all the clips on one timeline so you can drag them directly, and redraws automatically after each change.

- It only reads / writes each video track's "display period", from the same source as the command side's `_resolve_display_window` / `_pip_timeline_extent` — what you see is what the command will produce.
- To open: PiP mode + at least 2 video tracks; entry point is the right-click menu → "Timeline overview".
- Different thing from the position editor: **what you drag here is "time"**; where the small window sits is not changed here.

**Four things that are different from other places**:

| Elsewhere | What this adds |
|---|---|
| You can only edit numbers one at a time | Dragging to coarsely adjust + **auto-snapping** (to another material's edge / the main video's start and end / the end of the timeline / a manual `-t`; hold **Shift** while dragging = force snap) |
| One clip at a time | **Multi-select** (Ctrl / Shift + click) + **moving a whole group** (relative gaps unchanged, stops together when it hits 0) + "Ends snap" (the selected clips are butted head-to-tail in turn) |
| Batch buttons must be hunted for track by track | The **same batch of buttons** along the bottom — the only difference being that the timeline is **redrawn automatically** once they have run (same implementation as everywhere else): one-click fade in/out (all) / one-click transition (all) / one-click reset / one-click set start / transition alignment / one-click finite loop (all) / one-click mix (all) |
| The filename alone doesn't tell you which source it is | The **"Preview source"** button on the right (new in 2026-09-27): select any clip and click it to play that clip's **original source file** — video plays from the clip's display start (with "End" filled, only this segment; otherwise to the end of the source), images stay for the "image display duration"; the button greys out automatically when nothing / several clips are selected. ⚠️ Plays the raw source only — **no** overlay / crop / speed / transition or other per-segment processing — to see the composited result use the PiP live preview |

> One sentence: **this is the "arranging time" gesture tool (coarse adjustment)**; precise numbers are still edited on the **Loop/Chroma control** tab. Its main uses are checking at a glance whether the timeline has gaps / overlaps, and re-aligning the starts after a batch of transitions has swallowed them.
