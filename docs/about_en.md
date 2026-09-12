# About this project: main line, side features, and update rhythm

## One-line positioning

This project has one main line: **batch transcoding + a watermarking workflow**.

## Main line vs. side features

The feature list looks scattered, but its origin is simple: I started digging into FFmpeg's `overlay` filter because I wanted to watermark videos. Almost everything else — the visual position/rotate/scale editor, dynamic trajectories, masks, chroma-key, canvas, picture-in-picture, start/end dual-state editing — grew out of pushing that one goal further.

| Module | Role | Notes |
|--------|------|-------|
| Batch transcoding | Main line | A GUI for roughly 90% of HandBrake's transcoding/filter features; the most stable part of the project |
| Watermark overlay | Main line | The reason this project exists; I've spent more time on it than on transcoding itself |
| Picture-in-picture / muxing / stream extraction | Side feature | Shares the same filter chain and position editor as the watermark |
| Visual editors (crop / position / trajectory / canvas) | Side feature | GUI tools serving the watermark, PiP and crop workflows |

Using these side features for other purposes (localized mosaic, motion overlays, lightweight NLE-style work) is perfectly fine — they work and are maintained. They are just **not the design goal**: a bonus if you need them, harmless if you don't.

## Why I built this

Before this tool, my workflow was: batch conversion and cropping via .bat scripts, complex edits in Shotcut.

The turning point was jobs like side-by-side tiling: in Shotcut you change the project resolution, pin the left video's position to 0, set the right video's x to the left video's width — every step by hand, and it compounds fast with more clips. So I built this: drop two videos in, align height (or width), tile, export.

It's been a long time since I last opened Shotcut.

## Update rhythm

- **If you only do batch transcoding, there is no need to chase every update.** Most changelog entries polish the watermark / PiP side features; the transcoding core stays stable. Check back once in a while (every month or two) to see if a fix matters to you — there is no need to swap files after every commit.
- **Bundled builds lag behind on purpose.** The source ships with automated build scripts; fork and build as needed. If you have Python installed, running the script directly is the recommended way.
- The author personally runs it **as a plain script** (the .pyw with a single `dnd2` drag-and-drop dependency — no other third-party libraries, by design) and does not distribute packaged builds, so build freshness is not a signal of project activity.

## When something breaks

The transcoding core has barely changed; real bugs tend to live in edge cases (unusual container/codec combinations). Side features iterate under one rule: features must compose, never conflict — and every change is verified against "the transcode pipeline must not regress". When filing an issue, include the full FFmpeg command line and its error output; that makes fixes much faster.
