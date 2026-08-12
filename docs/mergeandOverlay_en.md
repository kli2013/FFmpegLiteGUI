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
- **Delete sources after merge**: use with care (confirmation).
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
