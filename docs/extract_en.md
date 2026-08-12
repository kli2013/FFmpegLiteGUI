[[中文](extract.md)]


# Stream extraction page

The Stream Extraction page (the "Stream Extract" tab) **losslessly** pulls individual video, audio and subtitle tracks out of media files — no re-encode, original quality kept. It supports batch processing, smart file naming and metadata retention. A fast tool for splitting multi-track media.

---

## 1. File list management

- **Add files** — button or drag-and-drop (multi-select) one or more media files.
- **Clear list** / **Delete selected** (multi-select) / **Preview selected** (shows the extract command in the preview area, not executed) / **Send selected** (builds a task from current options and adds it to the main queue).
- **Double-click a row** — quick-preview that file's extract command.
- **Stream-info column** — the list's 3rd column shows a stream-count summary per file (e.g. `2V 3A 2S` = 2 video, 3 audio, 2 subtitle), auto-parsed after drop.
- **Right-click → "Select tracks to extract…"** — a dialog lists every stream's type/index/codec/language/title; check exactly which tracks to extract (instead of the coarse "first track only").

> Drag-and-drop is supported and file type is auto-detected (media only).

---

## 2. Extraction options (core config)

These control which streams are extracted and how; they update the preview and task generation live.

| Option | Description |
|--------|-------------|
| **Extract video** | extract video tracks; container `mkv` / `mp4` / `mov`. |
| **Extract audio** | extract audio; format `m4a` / `mp3` / `flac` / `wav` / `aac` / `mka`. With "auto-match", the extension follows the codec (AAC→`.m4a`, FLAC→`.flac`). |
| **Extract subtitle** | extract subtitle; format `srt` / `ass` / `vtt` / `mov_text`. With "auto-match", extension follows codec (ASS→`.ass`, SRT→`.srt`). **Smart codec conversion**: if the chosen format differs from the source codec, the right encoder is used automatically (e.g. source ASS → SRT selects `-c:s srt`), instead of a broken copy. |
| **First track only** | per type, extract only the first track; otherwise all tracks of that type. **Fine selection**: for specific tracks (not all or first), right-click → "Select tracks to extract…". |
| **Extract attachments (fonts / cover art)** | also extract attachment streams and cover images. MKV embedded fonts keep their original file name (`-map 0:t:N? -c copy`); audio cover art is written as `.jpg`/`.png` by its codec. Attachments are a separate task, independent of video/audio/subtitle extraction. |
| **Split by stream type into folders** | video/audio/subtitle go to `video/` / `audio/` / `subtitle/` subfolders; attachments to `attachments/`. |
| **Keep chapters** | keep source chapter marks (`-map_chapters 0`). |
| **Strip metadata** | output carries no metadata (author/album/title…); good for assets or ringtones. |

> With audio auto-match, AAC maps to `.m4a` (not `.aac`) because M4A better preserves chapters & metadata.

---

## 3. Output directory

- **Custom output directory** — browse to choose; otherwise output goes next to the input file.
- The custom path is remembered (in user settings) and restored next launch.

---

## 4. Command preview area

- Shows **the selected file's** extract commands (one per stream) based on current options.
- Includes: input path, extracted stream type & index, output path (auto-named; multiple same-type streams get an index + language code), and metadata keep/strip.
- Handy for checking the rules; you can copy and run manually.

---

## 5. Batch task generation

- **Send all to queue** — for every file in the list, generate all extract commands from current options and add them as tasks.
- Tasks appear in the main task list; start the queue to batch-extract. Each task is independent and can run in parallel.

---

## 6. File name & metadata smarts

- **Auto language code** — if a stream has language info (`language=chi`), `_chi` is appended to the file name.
- **Keep title** — the source stream's `title` metadata is written to the output (unless stripped).
- **Auto extension** — the best container/extension for the codec, avoiding player incompatibility.

---

## 7. Typical scenarios

- **Split multi-audio / multi-subtitle video** — pull several language audio tracks or subtitle files from a movie.
- **Extract video footage** — pull a video stream from a recording for editing.
- **Extract BGM** — pull audio from an MV as a standalone file.
- **Extract subtitle / font / cover** — embedded fonts for ASS subtitles from MKV, or cover art from an audio file.
- **Backup subtitle & convert** — extract embedded ASS as external SRT (auto codec conversion) for editing or reuse.
- **Batch extract** — split a folder of videos into video/audio/subtitle streams at once.

---

The Stream Extraction page, with clear options and live preview, lets you **losslessly, quickly and in batch** strip the tracks you need — a solid helper for multi-track preprocessing, especially combined with the task queue.
