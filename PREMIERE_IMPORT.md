# Importing into Premiere Pro

The pipeline writes **output.xml** (FCP 7) and **output.edl** (CMX3600). If XML fails or doesn’t show in Import, use the EDL.

---

## Option 1: Import EDL (recommended if XML fails)

1. **File → Import** (or ⌘I).
2. In the Import dialog, set the **file type** dropdown at the bottom to **“All Files”** or **“All Documents”** if you don’t see `.edl` files.
3. Select **output.edl** and click Open.
4. When Premiere asks to **link the reel** to a source file, point it to your **reference video** (e.g. your reference clip: `TalkingHead.mp4` or the main video file). The EDL uses one reel for the cut list; all edits come from that file.
5. When asked for **video standard**, choose **24P** (the EDL is 23.976 fps for a cinematic timeline; use NTSC for 30 fps, PAL for 25 fps).
6. A new sequence is created with the cuts on one video track. You can then add other camera angles to extra tracks and use multicam or switch as needed.

---

## Option 2: Import XML (when it works)

- **If the XML doesn’t appear:** In the Import dialog, change the **Format** / **Enable** / file type dropdown at the **bottom** of the window to **“All Files”** or **“All Documents”** so `.xml` is listed.
- **If you can drag the XML:** Dragging **output.xml** onto the Project panel should trigger the same import. If you get an empty “File Import Failure” message, Premiere is rejecting the XML; use the EDL (Option 1) instead.

---

## After import: what to do next

You have a sequence with **one video track** (your reference clip) and all cuts already placed. From here:

### 1. **Review the cut**
- Scrub or play the sequence. The timeline is your rough cut from the transcript.
- Trim or delete clips, drag to reorder, split if needed. This is your **edit**.

### 2. **Add other cameras (optional)**
- **Option A – Multicam:** Drag your other synced clips (e.g. JoyceTrim, zoomTrim) from the Project panel onto **V2, V3**, etc. Line them up with the timeline (use the sync offsets from `.sync_offsets.json` if you need to nudge). Then right‑click the sequence → **Multi-Camera** → **Enable** so you can switch angles during playback.
- **Option B – B-roll:** Keep the current track as the main angle and add other clips as cutaways on V2 when you want to switch.

### 3. **Audio**
- The EDL only brings in the reference **video** track. If your reference clip has audio, it should be on the sequence already. If not, drag the reference (or your main audio file) onto A1 and align it to the timeline. Add other mics on A2, A3 and mix levels.

### 4. **Finish**
- Add titles, color grade, and export when you’re happy. Your rough assembly is done; the rest is normal Premiere editing.
