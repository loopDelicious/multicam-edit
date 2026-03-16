"""
Generate Premiere Pro-compatible FCP 7 XML from cut list and synced sources.
Places clips on parallel video/audio tracks with correct in/out and sync offsets.
"""
from __future__ import annotations

import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote

# Default 23.976 for cinematic 24p-style timeline
DEFAULT_FPS = 23.976


def _timebase(fps: float) -> int:
    """Integer timebase for XML/EDL (24 for 23.976, 30 for 29.97/30)."""
    if abs(fps - 24) < 0.5 or abs(fps - 23.976) < 0.01:
        return 24
    if abs(fps - 30) < 0.5 or abs(fps - 29.97) < 0.01:
        return 30
    return int(round(fps))


def probe_file(path: Path) -> dict:
    """Get duration_sec, fps, width, height, has_video, has_audio via ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    format_info = data.get("format", {})
    streams = data.get("streams", [])
    duration_sec = float(format_info.get("duration", 0) or 0)
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fps = DEFAULT_FPS
    width = height = 1920
    if video:
        fps_str = video.get("r_frame_rate") or video.get("avg_frame_rate") or "30/1"
        if "/" in fps_str:
            n, d = fps_str.split("/")
            fps = float(n) / float(d) if float(d) else DEFAULT_FPS
        else:
            fps = float(fps_str)
        width = int(video.get("width", 1920))
        height = int(video.get("height", 1080))
    return {
        "duration_sec": duration_sec,
        "fps": fps,
        "width": width,
        "height": height,
        "has_video": video is not None,
        "has_audio": audio is not None,
    }


def sec_to_frames(sec: float, fps: float) -> int:
    return int(round(sec * fps))


def _sec_to_tc(sec: float, fps: float = 23.976) -> str:
    """Seconds to CMX3600 timecode HH:MM:SS:FF. Uses integer display rate (24 for 23.976)."""
    total_frames = int(round(sec * fps))
    tb = _timebase(fps)
    h = total_frames // (3600 * tb)
    remainder = total_frames % (3600 * tb)
    m = remainder // (60 * tb)
    remainder = remainder % (60 * tb)
    s = remainder // tb
    f = remainder % tb
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def build_edl(
    cutlist: List[dict],
    reference_name: str,
    output_path: Path,
    fps: float = DEFAULT_FPS,
) -> None:
    """
    Write CMX3600 EDL for the cut list (single video track from reference).
    Premiere Pro can import EDL via File > Import; you will be prompted to link
    the reel to the source file.
    """
    # Reel name: up to 8 chars (CMX3600), alphanumeric
    reel = "".join(c for c in reference_name[:8] if c.isalnum() or c in "._-") or "REEL01"
    if len(reel) > 8:
        reel = reel[:8]
    lines = [
        "TITLE: Multicam Edit",
        "FCM: NON-DROP FRAME",
        "",
    ]
    rec_start = 0.0
    for i, cut in enumerate(cutlist, 1):
        start_sec = cut["start"]
        end_sec = cut["end"]
        dur = end_sec - start_sec
        src_in = _sec_to_tc(start_sec, fps)
        src_out = _sec_to_tc(end_sec, fps)
        rec_in = _sec_to_tc(rec_start, fps)
        rec_out = _sec_to_tc(rec_start + dur, fps)
        edit_num = f"{i:03d}"
        # Video and audio events so Premiere links both when you link the reel
        lines.append(f"{edit_num}  {reel:<8}  V     C        {src_in} {src_out} {rec_in} {rec_out}")
        lines.append(f"{edit_num}  {reel:<8}  A     C        {src_in} {src_out} {rec_in} {rec_out}")
        rec_start += dur
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _pathurl(path: Path) -> str:
    """FCP 7 pathurl: URL-encoded, file:/// on Mac to avoid parser issues with spaces/localhost."""
    p = path.resolve().as_posix()
    if not p.startswith("/"):
        p = "/" + p
    # Encode spaces and other chars so Premiere's parser doesn't choke
    encoded = quote(p, safe="/")
    return "file://" + encoded


def build_fcp7_xml(
    project_dir: Path,
    source_paths: List[Path],
    cutlist: List[dict],
    sync_offsets: Dict[str, float],
    output_path: Path,
    sequence_name: str = "Multicam Assembly",
    fps: float = DEFAULT_FPS,
) -> None:
    """
    Build FCP 7-style XML for Premiere: bin with master clips (unique file ids),
    sequence under project/children, clipitems reference masters via masterclipid.
    """
    timebase = _timebase(fps)
    root = ET.Element("xmeml", version="4")
    project = ET.SubElement(root, "project")
    ET.SubElement(project, "name").text = "MulticamEdit"
    children = ET.SubElement(project, "children")

    # Bin with one master clip per source (each file defined once, unique id)
    bin_el = ET.SubElement(children, "bin")
    ET.SubElement(bin_el, "name").text = "Multicam Sources"
    bin_children = ET.SubElement(bin_el, "children")
    file_infos: List[dict] = []
    for idx, src_path in enumerate(source_paths):
        info = probe_file(Path(src_path))
        file_infos.append(info)
        master_id = f"master-{idx}"
        file_id = f"file-{idx}"
        clip = ET.SubElement(bin_children, "clip", id=master_id)
        ET.SubElement(clip, "name").text = Path(src_path).name
        dur_frames = sec_to_frames(info["duration_sec"], fps)
        ET.SubElement(clip, "duration").text = str(dur_frames)
        rate = ET.SubElement(clip, "rate")
        ET.SubElement(rate, "timebase").text = str(timebase)
        ET.SubElement(rate, "ntsc").text = "FALSE"
        ET.SubElement(clip, "enabled").text = "TRUE"
        ET.SubElement(clip, "in").text = "0"
        ET.SubElement(clip, "out").text = str(dur_frames)
        ET.SubElement(clip, "ismasterclip").text = "TRUE"
        file_el = ET.SubElement(clip, "file", id=file_id)
        ET.SubElement(file_el, "name").text = Path(src_path).name
        ET.SubElement(file_el, "pathurl").text = _pathurl(Path(src_path))
        r = ET.SubElement(file_el, "rate")
        ET.SubElement(r, "timebase").text = str(timebase)
        ET.SubElement(r, "ntsc").text = "FALSE"
        ET.SubElement(file_el, "duration").text = str(dur_frames)
        if info["has_video"]:
            ET.SubElement(file_el, "width").text = str(info["width"])
            ET.SubElement(file_el, "height").text = str(info["height"])

    # Sequence under project/children (required by FCP 7 DTD)
    seq_duration_frames = sec_to_frames(sum(c["end"] - c["start"] for c in cutlist), fps)
    sequence = ET.SubElement(children, "sequence", id="seq-1")
    ET.SubElement(sequence, "name").text = sequence_name
    ET.SubElement(sequence, "duration").text = str(seq_duration_frames)
    rate = ET.SubElement(sequence, "rate")
    ET.SubElement(rate, "timebase").text = str(timebase)
    ET.SubElement(rate, "ntsc").text = "FALSE"
    ET.SubElement(sequence, "in").text = "0"
    ET.SubElement(sequence, "out").text = str(seq_duration_frames)
    tc = ET.SubElement(sequence, "timecode")
    tc_r = ET.SubElement(tc, "rate")
    ET.SubElement(tc_r, "timebase").text = str(timebase)
    ET.SubElement(tc_r, "ntsc").text = "FALSE"
    ET.SubElement(tc, "string").text = "00:00:00:00"
    ET.SubElement(tc, "frame").text = "0"
    ET.SubElement(tc, "source").text = "source"
    ET.SubElement(tc, "displayformat").text = "NDF"

    media = ET.SubElement(sequence, "media")
    video = ET.SubElement(media, "video")
    ET.SubElement(video, "format")

    # Only add video tracks for sources that have video (Premiere can fail silently on audio-only on video track)
    video_sources = [(i, p) for i, p in enumerate(source_paths) if file_infos[i]["has_video"]]
    for track_idx, src_path in video_sources:
        track = ET.SubElement(video, "track")
        ET.SubElement(track, "enabled").text = "TRUE"
        ET.SubElement(track, "locked").text = "FALSE"
        src_path_resolved = str(Path(src_path).resolve())
        offset_sec = sync_offsets.get(src_path_resolved, 0.0)
        info = file_infos[track_idx]
        duration_frames = sec_to_frames(info["duration_sec"], fps)
        timeline_pos = 0
        for cut in cutlist:
            start_sec = cut["start"]
            end_sec = cut["end"]
            in_sec = start_sec - offset_sec
            out_sec = end_sec - offset_sec
            if in_sec < 0 or out_sec > info["duration_sec"]:
                in_sec = max(0, in_sec)
                out_sec = min(info["duration_sec"], out_sec)
                if out_sec <= in_sec:
                    continue
            in_frames = sec_to_frames(in_sec, fps)
            out_frames = sec_to_frames(out_sec, fps)
            clip_dur = out_frames - in_frames
            clip_el = ET.SubElement(track, "clipitem", id=f"clip-v{track_idx}-{timeline_pos}")
            ET.SubElement(clip_el, "name").text = Path(src_path).name
            ET.SubElement(clip_el, "enabled").text = "TRUE"
            ET.SubElement(clip_el, "duration").text = str(duration_frames)
            ET.SubElement(clip_el, "start").text = str(timeline_pos)
            ET.SubElement(clip_el, "end").text = str(timeline_pos + clip_dur)
            ET.SubElement(clip_el, "in").text = str(in_frames)
            ET.SubElement(clip_el, "out").text = str(out_frames)
            ET.SubElement(clip_el, "masterclipid").text = f"master-{track_idx}"
            timeline_pos += clip_dur

    audio_el = ET.SubElement(media, "audio")
    ET.SubElement(audio_el, "format")
    track_audio = ET.SubElement(audio_el, "track")
    ET.SubElement(track_audio, "enabled").text = "TRUE"
    ET.SubElement(track_audio, "locked").text = "FALSE"
    ref_path = source_paths[0]
    ref_resolved = str(Path(ref_path).resolve())
    ref_offset = sync_offsets.get(ref_resolved, 0.0)
    ref_info = file_infos[0]
    ref_dur_frames = sec_to_frames(ref_info["duration_sec"], fps)
    tl = 0
    for cut in cutlist:
        start_sec = cut["start"]
        end_sec = cut["end"]
        in_sec = start_sec - ref_offset
        out_sec = end_sec - ref_offset
        in_sec = max(0, in_sec)
        out_sec = min(ref_info["duration_sec"], out_sec)
        if out_sec <= in_sec:
            continue
        in_f = sec_to_frames(in_sec, fps)
        out_f = sec_to_frames(out_sec, fps)
        clip_dur = out_f - in_f
        clip_a = ET.SubElement(track_audio, "clipitem", id=f"clip-a0-{tl}")
        ET.SubElement(clip_a, "name").text = Path(ref_path).name
        ET.SubElement(clip_a, "enabled").text = "TRUE"
        ET.SubElement(clip_a, "duration").text = str(ref_dur_frames)
        ET.SubElement(clip_a, "start").text = str(tl)
        ET.SubElement(clip_a, "end").text = str(tl + clip_dur)
        ET.SubElement(clip_a, "in").text = str(in_f)
        ET.SubElement(clip_a, "out").text = str(out_f)
        ET.SubElement(clip_a, "masterclipid").text = "master-0"
        tl += clip_dur

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(
        output_path,
        encoding="unicode",
        default_namespace="",
        method="xml",
    )
    content = output_path.read_text(encoding="utf-8")
    if not content.lstrip().startswith("<?xml"):
        content = '<?xml version="1.0" encoding="UTF-8"?>\n' + content
        output_path.write_text(content, encoding="utf-8")
