# Multicam Edit Pipeline

A command-line tool that takes raw video/audio from a project directory, transcribes the clearest track with **faster-whisper** (local), syncs multi-camera clips by audio waveform, and exports **Premiere Pro–compatible EDL/XML** so you get a rough multicam sequence ready for switching, mixing, and grading.

All processing is **local**; no external APIs. All assets live in the same project directory.

## Requirements

- **Python 3.9+**
- **FFmpeg** and **FFprobe** on your PATH
- Optional: CUDA for faster Whisper (faster-whisper will use it if available)

## Install

Clone the repo, then from the repo root:

```bash
cd path/to/multicam-edit-pipeline   # your clone
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

To run the tool from a **project directory** (where your media lives), either run from the repo and pass the project path, or copy the `multicam_edit` folder into your project. Examples:

```bash
# From repo: run on a project elsewhere
python -m multicam_edit /path/to/your/project

# Or cd to your project (if it contains this repo or multicam_edit)
cd /path/to/your/project
python -m multicam_edit
```

## Punchlist: SRT → AI outline → cut list → EDL → Premiere

Use this section as your single reference. Replace **`/path/to/your/project`** with the directory that contains your media (e.g. `~/Videos/MyShortFilm`). Replace **`TalkingHead.mp4`** with your reference video filename (the clip used for transcription and as the main timeline source).

---

**1. Generate the transcript and sync (one-time)**

In Terminal:

```bash
cd /path/to/your/project
source .venv/bin/activate   # or: path/to/repo/.venv/bin/activate if venv is in the repo
python -m multicam_edit --no-interactive
```

You get **`transcript.srt`** and **`.sync_offsets.json`** (and a default `cutlist.json` + `output.edl`). The cut list from this run will be replaced in step 3.

---

**2. Upload the SRT and get a cut list from AI**

In Cursor (or any AI chat), upload or paste **`transcript.srt`**, then send this prompt (edit the bracketed part to your edit goal):

```text
I'm editing a multicam video. The attached/pasted file is a timestamped SRT transcript (times are in the SRT format; convert to seconds for the cut list).

I need a cut list as a JSON file. Format: a single JSON array. Each segment must be exactly:
{ "start": <seconds>, "end": <seconds>, "label": "<short label>" }
Times in seconds (e.g. 120 = 2 minutes). Order of segments = order on the timeline.

My edit goal: [e.g. "One 10-minute video: keep intro 0–2 min, skip to 25–33 min, then 35–42 min Q&A, then 45–50 min closing" or "Three 5-minute videos: Act 1 = 0–5 min, Act 2 = 15–20 min, Act 3 = 40–45 min"].

Output only valid JSON: an array of { "start", "end", "label" } objects, no markdown or explanation.
```

For multiple videos, ask for separate arrays and save each as its own file (e.g. `cutlist_act1.json`, `cutlist_act2.json`).

---

**3. Save the cut list in the project directory**

Copy the AI’s JSON from the chat (⌘C), then in Terminal run:

```bash
cd /path/to/your/project
pbpaste > cutlist.json
```

That writes the clipboard contents to **`cutlist.json`**. (Mac: `pbpaste` is built-in. Windows: use an editor and paste, or PowerShell: `Get-Clipboard | Set-Content cutlist.json`.)

If you prefer to create the file and paste in an editor:

```bash
touch cutlist.json
```

Then open `cutlist.json`, paste, and save. Valid shape:

```json
[
  { "start": 0.0, "end": 120.0, "label": "Intro" },
  { "start": 1500.0, "end": 1980.0, "label": "Main" }
]
```

---

**4. Generate the EDL (and XML)**

In Terminal (same project path and venv):

```bash
cd /path/to/your/project
source .venv/bin/activate
python -m multicam_edit --no-transcribe --no-sync --no-interactive --cutlist cutlist.json -o output.xml
```

This writes **`output.edl`** and **`output.xml`** in that project folder.

For a different cut list or output name:

```bash
python -m multicam_edit --no-transcribe --no-sync --no-interactive --cutlist cutlist_10min.json -o output_10min.xml
```

For multiple acts (run once per output):

```bash
python -m multicam_edit --no-transcribe --no-sync --no-interactive --cutlist cutlist_act1.json -o output_act1.xml
python -m multicam_edit --no-transcribe --no-sync --no-interactive --cutlist cutlist_act2.json -o output_act2.xml
python -m multicam_edit --no-transcribe --no-sync --no-interactive --cutlist cutlist_act3.json -o output_act3.xml
```

---

**5. Import the EDL into Premiere Pro**

- **File → Import**. Set file type to **All Files**. Select **`output.edl`** in your project folder.
- When asked to **link the reel**, choose your reference video (e.g. **TalkingHead.mp4** in that folder).
- When asked for **video standard**, choose **24P**.
- If you see “Media offline”, use **File → Link Media** and point to the same reference video.

---

**6. Finish in Premiere**

Add other angles on V2/V3 if needed, mix audio, color grade, export.

---

## What to put on GitHub

Include these in your repo:

| Include | Purpose |
|--------|---------|
| **`README.md`** | This file. |
| **`requirements.txt`** | Python dependencies. |
| **`multicam_edit/`** | The package (all `.py` files: `cli.py`, `cutlist.py`, `audio.py`, `transcribe.py`, `sync.py`, `xml_export.py`, `__init__.py`, `__main__.py`). |
| **`.gitignore`** | So generated files and `.venv` are not committed. |
| **`PREMIERE_IMPORT.md`** | Optional: short Premiere import/relink notes. |

Do **not** commit:

- **`.venv/`** – Virtual environment (recreate with `pip install -r requirements.txt`).
- **`transcript.srt`**, **`cutlist.json`**, **`output.edl`**, **`output.xml`**, **`.sync_offsets.json`** – Generated per project (in `.gitignore`).
- **`raw/`** or any **media files** (e.g. `.mp4`, `.mov`, `.wav`) – Excluded via `.gitignore`. The repo is code-only; video/audio are large and project-specific, so keep them local and add your own media when you use the tool.

Clone the repo, create a venv, install from `requirements.txt`, then run the tool against any folder that contains your media.

## Project layout

- **`raw/`** – Put your source video/audio files here (or pass `--sources`).
- **`transcript.srt`** – Generated timestamped SRT (or provide your own and use `--no-transcribe`).
- **`cutlist.json`** – Ordered list of `{ "start", "end", "label" }` (seconds). Generated from SRT or edited by hand.
- **`.sync_offsets.json`** – Cached sync offsets (created automatically).
- **`output.xml`** – FCP 7 XML to import into Premiere Pro.

## Usage

Activate the venv, then run from the project directory (or pass a path):

```bash
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m multicam_edit
```

Or run without activating: `.venv/bin/python -m multicam_edit`

This will:

1. Find media in `raw/` (or current dir).
2. Pick the “clearest” audio track as reference.
3. Transcribe it → `transcript.srt`.
4. Sync other cameras by audio → `.sync_offsets.json`.
5. **Propose an outline** from the transcript and start an **interactive conversation**: you can merge, split, reorder, or delete segments, then type `a` or `accept` when done. (Use `--no-outline` for the simple 3-option prompt instead.)
6. Build `output.xml` and `output.edl` with synced clips and cuts.

**Import `output.xml` in Premiere Pro** (File → Import, or drag) to get a sequence with all angles and cuts in place.

### Options

| Option | Description |
|--------|-------------|
| `project_dir` | Project folder (default: current directory). |
| `--sources PATH [PATH ...]` | Override: list of video/audio files. |
| `--model tiny\|base\|small\|medium\|large-v3` | Whisper model (default: `base`). |
| `--language LANG` | Language hint (e.g. `en`). |
| `--no-transcribe` | Skip transcription; use existing `transcript.srt`. |
| `--no-sync` | Skip sync; use existing `.sync_offsets.json`. |
| `--cutlist PATH` | Cut list JSON (default: `project_dir/cutlist.json`). |
| `--output PATH` | Output XML path (default: `project_dir/output.xml`). |
| `--no-interactive` | Don't prompt; build default cut list from SRT and continue. |
| `--no-outline` | Use simple 3-option prompt instead of interactive outline commands. |
| `--fps` | Timeline frame rate (default: 23.976). |

### Examples

```bash
# Default: current dir, interactive cut list
python -m multicam_edit

# Specific project dir
python -m multicam_edit /path/to/my/project

# Skip transcription and sync (already done), just regenerate XML
python -m multicam_edit --no-transcribe --no-sync

# Non-interactive: default cut list from SRT, output to custom path
python -m multicam_edit --no-interactive -o /path/to/export.xml
```

## Interactive outline commands

When you don't have a `cutlist.json` yet, the tool proposes an outline (one segment per SRT line) and waits for commands:

| Command | Example | Description |
|--------|---------|-------------|
| `a` or `accept` | `a` | Use current outline and continue to export. |
| `m n1 n2` | `m 3 6` | Merge segments 3 through 6 into one. |
| `s n sec` | `s 2 45.5` | Split segment 2 at 45.5 seconds. |
| `r n1 n2 ...` | `r 2 1 3 4` | Reorder segments (list new order by number). |
| `d n` | `d 5` | Delete segment 5. |
| `p` | `p` | Print the outline again. |
| `?` | `?` | Show help. |

Type each command and press Enter. When you're happy, type `accept` to save and build the EDL/XML.

## Cut list format

`cutlist.json` is a JSON array of segments in order:

```json
[
  { "start": 0.0, "end": 12.5, "label": "Intro" },
  { "start": 12.5, "end": 45.0, "label": "Scene A" }
]
```

- **start / end** – Time range in seconds (reference timeline).
- **label** – Optional; for your notes.

Order of entries = order of cuts on the timeline.

## Using an AI assistant to define the cut list

For long or complex edits (e.g. 50 minutes of raw → one 10‑minute cut, or three 5‑minute videos), it’s often easier to **decide the edit in a normal AI chat** (e.g. Cursor, ChatGPT) and then **feed that into the script** via `cutlist.json`.

**Workflow:**

1. **Run the pipeline once** (with or without the interactive outline) so you have:
   - `transcript.srt` – timestamped transcript of the reference track  
   - (optional) `cutlist.json` – default one-cut-per-SRT-segment

2. **In Cursor or any AI assistant**, describe what you want, for example:
   - “I have 50 minutes of raw. I want one 10‑minute video: keep the intro (0–2 min), skip 2–25 min, use 25–33 min, skip to Q&A 35–42 min, then closing 45–50 min.”
   - “Same 50 min source: I want three separate 5‑minute videos – Act 1 from 0–5 min, Act 2 from 15–20 min, Act 3 from 40–45 min.”

3. **Give the AI the cut list format** (you can paste this):
   - “The script expects a JSON file: an array of segments. Each segment is `{ "start": <seconds>, "end": <seconds>, "label": "<optional text>" }`. Order of segments = order on the timeline. Times are in seconds (e.g. 120 = 2 minutes).”
   - Optionally attach or paste `transcript.srt` so the AI can suggest exact in/out times from the transcript.

4. **Have the AI output a `cutlist.json`** (or one per output, e.g. `cutlist_10min.json`, `cutlist_act1.json`, …). Save it in your project folder.

5. **Run the script with that cut list** (no transcription, no outline prompts):
   ```bash
   python -m multicam_edit --no-transcribe --no-sync --no-interactive --cutlist cutlist_10min.json -o output_10min.xml
   ```
   For multiple outputs (e.g. three 5‑min videos), run once per cut list with different `--cutlist` and `-o`:
   ```bash
   python -m multicam_edit --no-transcribe --no-sync --no-interactive --cutlist cutlist_act1.json -o output_act1.xml
   python -m multicam_edit --no-transcribe --no-sync --no-interactive --cutlist cutlist_act2.json -o output_act2.xml
   python -m multicam_edit --no-transcribe --no-sync --no-interactive --cutlist cutlist_act3.json -o output_act3.xml
   ```

The script stays the single source of truth for transcribing, syncing, and building EDL/XML; the **conversation** is only for deciding *what* goes into the cut list. You can mix: use the CLI outline for quick tweaks, or use the AI for complex, high-level edits.

## Notes

- **Clearest audio** is chosen by a simple loudness + SNR-style score; reorder files or use `--sources` to force a specific reference.
- **Sync** uses cross-correlation on the first 10 minutes of audio; long clips are analyzed in a window to save memory.
- **Premiere**: If import fails, try opening the XML in a text editor to confirm paths; use absolute paths if needed. Sequence frame rate is 23.976 (24p) by default; use `--fps 30` for 30fps.
