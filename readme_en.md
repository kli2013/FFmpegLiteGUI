[[中文](readme.md)]


# FFmpegLiteGUI

> **Note:** The bundled build may lag behind the source. Feel free to fork and build it yourself — several automated build scripts are included.

---

## What it is

A lightweight, multi-purpose **FFmpeg GUI** that combines roughly 90% of HandBrake's transcoding and filtering features with **mkvtoolnix-style stream muxing**, plus a **lightweight non-linear editing (NLE)** layer.

FFmpegLiteGUI is only a shell. It needs a real FFmpeg binary — see [Setting up FFmpeg](setupFFmpeg_en.md). The recommended build is `ffmpeg-*-win64-gpl-shared` from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds/releases). The "shared" build keeps the total size small because `ffmpeg`, `ffprobe` and `ffplay` share one set of DLLs; downloading three standalone builds would roughly triple the size.

---

## Core capabilities

| Module | What it does |
|--------|--------------|
| **Transcode (main)** | CPU / hardware encoding, multiple rate-control modes (CRF / CQ / bitrate), presets, advanced params (tune / profile / level), and common filters: scale, crop, rotate, speed, reverse, denoise, sharpen, subtitle burn-in, plus brightness / contrast / saturation / gamma / hue. [Details](transcode_en.md) |
| **Watermark** | Image / video watermark with looping, chroma-key, adaptive sizing & positioning, and a visual position editor you can drag. (The logic mirrors the Picture-in-Picture sub-video described below.) |
| **Mux / Merge (light)** | mkvtoolnix-like stream copy & muxing with flexible multi-audio / multi-subtitle selection by original stream index. Basic for now; professional metadata editing may come later. |
| **Picture-in-Picture & NLE** | Multiple overlaid videos (PiP) with independent scale / crop / rotate / opacity / chroma-key / loop / position. A lightweight non-linear editor. [Details](mergeandOverlay_en.md) |
| **Stream Extract (light)** | Batch-extract video / audio / subtitle streams losslessly, with chapter keeping, metadata stripping, and per-type folder output. [Details](extract_en.md) |
| **Audio** | Multi-track mix (amix), volume, silence fill, trim. |
| **Task manager** | Queue with double-click editing, parallel jobs, global stop (sends `q`), and custom FFmpeg commands. |
| **Presets & tools** | Preset save / load, player preview (mpv / ffplay). |

Most controls have hover tooltips — point at a label or input box to see hints.

When using hardware encoding (encoders with `_nvenc` / `amf` / … suffixes), FFmpeg and the GPU driver API must match. If it fails, try an older FFmpeg or update the GPU driver. A custom FFmpeg-directory option was added for exactly this.

To use **software filters inside a fully hardware encode/decode pipeline**, the filters must be wrapped with the right parameters or it errors out. The "Filter acceleration" control on the Advanced tab switches the whole filter chain automatically — see [Filter acceleration (hardware filter switching)](transcode_en.md#filter-acceleration-hardware-filter-switching).

---

## Design philosophy

FFmpeg itself imposes almost no limits, so the shell shouldn't invent artificial ones either.

---

## Documentation

- [Transcoding page](transcode_en.md)
- [Merge / Mux / Picture-in-Picture](mergeandOverlay_en.md)
- [Stream extraction](extract_en.md)
- [Setting up FFmpeg](setupFFmpeg_en.md)
