[[中文](setupFFmpeg.md)]


# FFmpeg setup guide

This tool does **not** bundle the FFmpeg binaries. You must have these three programs available on the system before it works.

| Program | File | Required? | Use |
|---------|------|-----------|-----|
| FFmpeg | `ffmpeg` (`ffmpeg.exe` on Windows) | **Required** | transcode / merge / filters (core) |
| FFprobe | `ffprobe` (`ffprobe.exe`) | **Required** | read media info (duration, resolution, codec, streams) |
| FFplay | `ffplay` (`ffplay.exe`) | Optional | live preview / playback test (transcoding still works without it) |

> Keep the three in the same folder. Without `ffprobe`, media-analysis features are limited; without `ffplay`, only preview/playback is unavailable.

---

## 1. Download FFmpeg

The shell has no codecs of its own — it depends on external FFmpeg.

- **Download**: https://github.com/BtbN/FFmpeg-Builds/releases
- **Recommended**: `ffmpeg-*-win64-gpl-shared` (64-bit) / `ffmpeg-*-win32-gpl-shared` (32-bit).

### Why "shared" build
The three exe files share one set of low-level libraries (`avcodec`, `avformat`, `avutil`…). The **shared** build extracts those libraries into `*.dll` beside the exe; all three share one copy, so the total unpacked size is small. Standalone builds embed the libraries per exe — roughly **2× larger** overall. Shared is the best size/function balance for normal use.

### Download & unpack
1. Get the latest `ffmpeg-*-win64-gpl-shared.zip`.
2. Inside, `bin\` holds `ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe` (and their shared DLLs).
3. Place the whole `bin\` (or its files) per the locations below.

> Mirror: https://www.gyan.dev/ffmpeg/builds/ (pick `ffmpeg-release-essentials.zip`). Either is fine; don't download both.

---

## 2. Three "central" unpack locations

The auto-detection scans these locations in a fixed order; placing files in **any one** works, no extra config. All three are valid, but for the shared build (many DLLs) the tidy approach differs:

- **🌟 Most recommended: system PATH** — configure once, every program on the machine (including this one and others) can use it; for users who already set PATH, just download and run.
- **Recommended structure: `_internal` subfolder, or unpack `bin` next to the exe** — keeps DLLs in a subfolder, main dir clean.
- **Also works: exe's own directory** — shared build scatters dozens of DLLs beside the exe (messy but functionally fine).

### Location 1 — exe's own directory (easiest, but shared scatters DLLs)
Put `ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe` directly in the program's folder.

```
YourApp\
├── FFmpegLiteGUI.exe            ← main
├── ffmpeg.exe                   ← found automatically
├── ffprobe.exe
├── ffplay.exe
└── other *.dll
```
- Pro: zero config; copy the whole folder and it works.
- Note (shared): dozens of DLLs land beside the exe; for tidiness use Location 2.

### Location 2 — `_internal` subfolder, or unpack `bin` next to the exe (recommended, esp. for shared)
**Option A — `_internal` subfolder** (PyInstaller folder-build standard)
```
YourApp\
├── FFmpegLiteGUI.exe
├── _internal\                   ← put ffmpeg here
│   ├── ffmpeg.exe
│   ├── ffprobe.exe
│   └── ffplay.exe (+ dlls)
```
**Option B — `bin` subfolder** (keeps official zip layout, cleanest)
```
YourApp\
├── FFmpegLiteGUI.exe
├── bin\                         ← official zip's bin
│   ├── ffmpeg.exe
│   ├── ffprobe.exe
│   └── ffplay.exe (+ dlls)
```
- The program scans **all first-level subfolders** of its directory; `ffmpeg.exe` inside is found.
- Unpacking the official zip as-is usually creates the `bin\` layout automatically.

### Location 3 — system PATH (🌟 most recommended, configure once, system-wide)
Put the three exe (+ DLLs) in any folder already on `PATH`, or add their folder to `PATH`.

**Steps (Windows 10/11)**
1. Put the three exe (+ DLLs) in a fixed folder, e.g. `C:\Tools\ffmpeg\` (avoid Chinese / spaces).
2. `Win + S` → "Edit the system environment variables" → open.
3. Click "Environment Variables" (bottom-right).
4. In System or User variables, find `Path`, double-click to edit.
5. "New", paste `C:\Tools\ffmpeg\`, OK to save.
6. **Restart** any open command windows and the app so PATH takes effect.

**Verify (cmd / PowerShell)**
```bat
ffmpeg -version
ffprobe -version
```
A version print means PATH works.

- Pro: any program on the machine can call it; upgrading FFmpeg touches one place; for PATH-already-set machines, just download and run.
- Con: the path is deep; easy to forget "restart the app".

---

## 3. Internal lookup order (reference)

At startup, in priority order, the first valid file wins:

1. `ffmpeg.exe` / `ffmpeg` in the program's own directory.
2. First-level subfolders of the program directory (`bin\`, `_internal\`).
3. (Single-file package) see note 4 below.
4. System `PATH` (`shutil.which` fallback).

All three "locations" fall into this chain; anywhere works, independently.

---

## 4. Fourth way: specify a directory inside the app (highest priority)

If you don't want to touch PATH or stuff files into the app folder, set it in the app:

1. Open the **"Info & set"** tab at the top of the main window.
2. Check **"Enable custom FFmpeg dir"**.
3. Browse and select **the folder containing only the three exe** (e.g. `C:\Tools\ffmpeg\` or the unpacked `bin\`).
4. The app prefers that folder's `ffmpeg.exe` / `ffprobe.exe` / `ffplay.exe`.

> Manual directory beats the auto-detection above. The setting is remembered and reapplied next launch.

---

## 5. Verify the app found FFmpeg

After launch:
- The status bar / info area should show the found `ffmpeg` and `ffprobe` paths.
- Drop a video — if duration/resolution/codec parse correctly, `ffprobe` works.
- A simple transcode that outputs successfully means `ffmpeg` works.
- If "ffmpeg / ffprobe not found", re-check any location above, watch for Chinese/spaces in the path, and (PATH) restart the app.

---

## 6. FAQ

**Q1: Only `ffmpeg.exe`?** Transcoding works, but include `ffprobe.exe` or media-analysis UI features are limited / error.

**Q2: Chinese / spaces in the path?** Allowed, but if something weird happens, move FFmpeg to a pure-English, no-space path (e.g. `C:\Tools\ffmpeg\`) first — highest success rate.

**Q3: Multiple FFmpeg versions conflict?** The app takes the **first** hit in the chain; it won't load several. If the version is wrong, check `PATH` for an older entry, or delete old exe next to the app.

**Q4: Portable / USB?** Use Location 1 (exe's own dir) or Location 2 Option B (`bin` subfolder); copy the whole folder, no PATH needed.

**Q5: Single-file exe can't find FFmpeg?** A one-file exe unpacks to a temp dir at runtime, so the "next to exe" method fails. Use Location 1's program directory, Location 3's PATH, or specify the directory inside the app.
