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
- **Track list (Treeview)** — all added tracks (video/audio/subtitle) with enabled state, type, spec (resolution/duration/codec…), encode settings. Double-click to edit a track; drag-and-drop to add (auto type detection). Toolbar: enable/disable, edit, preview, move up/down, delete, clear, sort (by name or mtime), save/load project.

### 1.2 Add external tracks
- **External audio** — `mp3`, `aac`, `wav`, `flac`, `opus`, `ac3`…
- **External subtitle** — `srt`, `ass`, `ssa`, `vtt`, `idx`, `sup`…
- **External video** — in PiP or Concat mode, as a sub-video or concat segment.

### 1.3 Mode selection & params

**Mux mode**
- Merge main video with external audio/subtitles; stream-copy or re-encode. Main video can take full filters (crop, scale, rotate, enhance…). Audio tracks set codec, bitrate, sample rate, volume independently.
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
  - **Global stage (after join) keeps only**: subtitle burn-in (video). To drop a segment's audio in Concat mode, don't uncheck enable — choose **generate silent stream** in that video's audio-binding tab.

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
- **Video**: only the main video's subtitle burn-in (if any).
- **Audio**: volume control removed; Concat mode offers no overall or per-track volume.

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

- **Save / load project** — all tracks, settings, layout to a `.fflgproject` file (JSON inside; editable in a text editor).
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
- **"Copy trim/spd/rev (V→A)"** — copy the selected video track's trim/speed/reverse (enabled only when a video track is selected).
- **"Paste trim/spd/rev (V→A)"** — apply those to selected audio tracks (enabled only with a clipboard; includes out-of-range safety guard).
- **"Batch src-audio→video T/S/R (V → A)"** — see §6.3.
- **"One-click fade in/out (all) / One-click transition (all)" buttons** — see §7.3 (now buttons + their own duration boxes inside the "Fade in/out" tab, not a right-click menu).

---

## 9. Mask / transparent overlay

The mask is a standalone feature (not a toggle on some filter). It applies to the **sub-video** and **text watermark** on the Mux page, making part of the sub-video transparent so the main video (or canvas) shows through. Entry point: on the video-track editor's **"Loop / Chroma"** tab, the **"Mask"** button to the right of the **Transparency** checkbox (spaced `padx=25` from it).

### 9.1 Open the mask dialog
- Click **Mask** to open the settings box: an **Enable mask** checkbox, mask direction, rectangle coordinates (x / y / width / height, original frame), and Save/Cancel buttons.
- Coordinates share the same source as the **Crop** editor: click **"📋 Copy coords from crop"** to fill in one click (values match the original frame; the mask block is placed before the crop filter).

### 9.2 Mask direction
- **Outside the mask (show only rectangle)**: black background, white rectangle — opaque inside the rectangle, transparent outside; the main video shows through outside the rectangle.
- **Inside the mask (rectangle transparent)**: white background, black rectangle — rectangle transparent, everything else normal; the main video shows through the rectangle hole.

### 9.3 Scope & implementation
- The mask applies to both **PiP sub-videos** and **text watermarks** (both share the same "Loop / Chroma" editor).
- Internally uses `alphamerge`: writes the grayscale mask into the alpha channel (white = opaque, black = transparent). The bundled ffmpeg has no `mask` filter, so it goes `split=2[a][m];[m]format=gray,drawbox…;[a][msk]alphamerge`.
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

## Appendix — filter independence/linkage across the four modes (incl. Transcode)

Four working modes: ① Transcode ② Mux ③ PiP ④ Concat. Below, video filters, audio creative filters, audio reverse, and the intentionally-global filters.

| Filter class | Transcode | Mux | PiP | Concat |
|--------------|-----------|-----|-----|--------|
| Video filters (crop/scale/rotate/enhance/deint/speed/reverse…) | single video, own settings | main video own ✅ independent | main + each sub own ✅ independent | each segment own ✅ independent (+forced normalize) |
| Audio creative (volume/EQ/fade/denoise/loudness/channel/speed) | own ✅ independent | per-track own ✅ independent | per-track own ✅ independent | per-track own ✅ independent |
| Audio reverse | independent checkbox ✅ (not following video) | ✅ fully independent (no fallback to main) | ✅ fully independent | ✅ fully independent (external track independent; embedded audio only trims/resets, no longer follows video reverse/speed) |
| Subtitle burn-in `subtitles` | single video | global (final picture) | main video only (global) | main video only (global) |
| Text watermark `drawtext` | single video | global | global (main) | global (main) |
| Forced spec normalize (scale/format/fps/sar) | none | none | none | ✅ intentional global (join required) |

**① Transcode — fully independent**
- One video, one (or zero) audio. Video reverse, audio reverse, audio speed, volume, EQ, fade… each its own checkbox/slider, no linkage. Audio reverse ("Audio reverse (independent of video)") defaults off; video reverse affects picture only. Check both to reverse together. No master "link/unlink" switch (by design — simplest). Intentional globals: subtitle burn-in & text watermark act on the only video; preview disables reverse (player limit).

**② Mux**
- Video: main video own settings, independent. Audio: each external track's codec/volume/EQ/speed/fade/reverse is per-track independent; "Audio reverse (independent of video, this track only)" controls itself only. Intentional globals: subtitle burn-in (`subtitles=`), text watermark (`drawtext`). Tooltip notes "sub-videos can apply all filters except subtitle".

**③ PiP**
- Video: main + each sub own filter chain, independent. Audio: each track fully independent; audio reverse pure-independent. Intentional globals: only main video's subtitle burn-in & text watermark (sub-videos can't burn subtitles — a compositing-layer limit, not an omission).

**④ Concat**
- Video: each segment (main + subs) own filter chain; at each segment's end, scale/format/fps/setsar are forcibly appended (from main video) — an intentional global required for join compatibility, no exception.
- Audio: **external tracks** per-track independent (reverse/speed pure-independent, set in audio-track settings). **Embedded audio** is fully independent — only trim & base PTS reset, **no longer follows the segment video's reverse/speed**. If you reverse/speed a segment's video and want its embedded audio synced, add a separate audio track and check reverse/speed there; otherwise embedded audio plays forward at normal speed.
- Intentional globals: subtitle burn-in (main only), text watermark (main only), forced spec normalize.

**Summary**
- Video & audio creative filters: all four modes are per-track independent.
- Audio reverse / speed: all four modes are now fully independent — no "audio follows video" fallback remains (Mux dropped "audio reverse falls back to main"; Concat dropped "embedded audio falls back to segment video reverse/speed"). Each audio track's reverse/speed is decided solely by its own audio-track settings.
- The only remaining "following" is the intentional global: subtitle burn-in, text watermark, and Concat's forced spec normalize. These are meant to be global, not linkage.
