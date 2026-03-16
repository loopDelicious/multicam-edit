"""
Generate Premiere Pro-compatible FCP 7 XML and CMX3600 EDL from cut list
and synced sources.
"""
from __future__ import annotations

import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote

DEFAULT_FPS = 23.976


def _timebase(fps: float) -> int:
    """Integer timebase for XML/EDL (24 for 23.976, 30 for 29.97, etc.)."""
    if abs(fps - 23.976) < 0.01 or abs(fps - 24) < 0.3:
        return 24
    if abs(fps - 29.97) < 0.01 or abs(fps - 30) < 0.3:
        return 30
    if abs(fps - 59.94) < 0.01 or abs(fps - 60) < 0.3:
        return 60
    return int(round(fps))


def _is_ntsc(fps: float) -> bool:
    """True for NTSC pulldown rates: 23.976, 29.97, 59.94."""
    return any(abs(fps - r) < 0.01 for r in (23.976, 29.97, 59.94))


def _add_rate(parent: ET.Element, fps: float) -> ET.Element:
    """Append a <rate> sub-element with correct timebase and ntsc flag."""
    rate = ET.SubElement(parent, "rate")
    ET.SubElement(rate, "timebase").text = str(_timebase(fps))
    ET.SubElement(rate, "ntsc").text = "TRUE" if _is_ntsc(fps) else "FALSE"
    return rate


def probe_file(path: Path) -> dict:
    """Get duration_sec, fps, width, height, has_video, has_audio via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
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
    width, height = 1920, 1080
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
    """Seconds to CMX3600 timecode HH:MM:SS:FF."""
    total_frames = int(round(sec * fps))
    tb = _timebase(fps)
    h = total_frames // (3600 * tb)
    remainder = total_frames % (3600 * tb)
    m = remainder // (60 * tb)
    remainder %= 60 * tb
    s = remainder // tb
    f = remainder % tb
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


# ---------------------------------------------------------------------------
# EDL
# ---------------------------------------------------------------------------

def build_edl(
    cutlist: List[dict],
    reference_path: Path,
    output_path: Path,
    fps: float = DEFAULT_FPS,
) -> None:
    """
    Write CMX3600 EDL with short reel names and FROM CLIP NAME comments
    so Premiere Pro can relink to the correct source media.
    """
    reel = "REEL0001"
    clip_name = Path(reference_path).name
    clip_path = str(Path(reference_path).resolve())

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
        lines.append(
            f"{edit_num}  {reel}  V     C        "
            f"{src_in} {src_out} {rec_in} {rec_out}"
        )
        lines.append(f"* FROM CLIP NAME: {clip_name}")
        lines.append(f"* SOURCE FILE: {clip_path}")
        lines.append(
            f"{edit_num}  {reel}  A     C        "
            f"{src_in} {src_out} {rec_in} {rec_out}"
        )
        lines.append(f"* FROM CLIP NAME: {clip_name}")
        lines.append(f"* SOURCE FILE: {clip_path}")
        rec_start += dur
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# FCP 7 XML
# ---------------------------------------------------------------------------

def _pathurl(path: Path) -> str:
    """file:/// URL suitable for FCP 7 XML on macOS."""
    p = path.resolve().as_posix()
    if not p.startswith("/"):
        p = "/" + p
    return "file://" + quote(p, safe="/")


def _add_video_sample_chars(
    parent: ET.Element, fps: float, width: int, height: int,
) -> None:
    """Append <samplecharacteristics> for a video format/media element."""
    sc = ET.SubElement(parent, "samplecharacteristics")
    _add_rate(sc, fps)
    ET.SubElement(sc, "width").text = str(width)
    ET.SubElement(sc, "height").text = str(height)
    ET.SubElement(sc, "anamorphic").text = "FALSE"
    ET.SubElement(sc, "pixelaspectratio").text = "square"
    ET.SubElement(sc, "fielddominance").text = "none"


def _add_audio_sample_chars(parent: ET.Element) -> None:
    """Append <samplecharacteristics> for an audio format/media element."""
    sc = ET.SubElement(parent, "samplecharacteristics")
    ET.SubElement(sc, "depth").text = "16"
    ET.SubElement(sc, "samplerate").text = "48000"


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
    Build FCP 7 XML that Premiere Pro can import via File > Import.
    Includes bin with master clips (file defs with media blocks),
    and a sequence whose clipitems reference those files by id.
    """
    root = ET.Element("xmeml", version="4")
    project = ET.SubElement(root, "project")
    ET.SubElement(project, "name").text = "MulticamEdit"
    children = ET.SubElement(project, "children")

    # -- Probe all sources ------------------------------------------------
    file_infos: List[dict] = []
    for src_path in source_paths:
        file_infos.append(probe_file(Path(src_path)))

    ref_info = file_infos[0] if file_infos else {
        "width": 1920, "height": 1080,
    }

    # -- Bin with master clips -------------------------------------------
    bin_el = ET.SubElement(children, "bin")
    ET.SubElement(bin_el, "name").text = "Multicam Sources"
    bin_children = ET.SubElement(bin_el, "children")

    for idx, src_path in enumerate(source_paths):
        info = file_infos[idx]
        master_id = f"master-{idx}"
        file_id = f"file-{idx}"
        dur_frames = sec_to_frames(info["duration_sec"], fps)

        clip = ET.SubElement(bin_children, "clip", id=master_id)
        ET.SubElement(clip, "name").text = Path(src_path).name
        ET.SubElement(clip, "duration").text = str(dur_frames)
        _add_rate(clip, fps)
        ET.SubElement(clip, "enabled").text = "TRUE"
        ET.SubElement(clip, "in").text = "0"
        ET.SubElement(clip, "out").text = str(dur_frames)
        ET.SubElement(clip, "ismasterclip").text = "TRUE"

        file_el = ET.SubElement(clip, "file", id=file_id)
        ET.SubElement(file_el, "name").text = Path(src_path).name
        ET.SubElement(file_el, "pathurl").text = _pathurl(Path(src_path))
        _add_rate(file_el, fps)
        ET.SubElement(file_el, "duration").text = str(dur_frames)

        file_media = ET.SubElement(file_el, "media")
        if info["has_video"]:
            fv = ET.SubElement(file_media, "video")
            _add_video_sample_chars(fv, fps, info["width"], info["height"])
        if info["has_audio"]:
            fa = ET.SubElement(file_media, "audio")
            _add_audio_sample_chars(fa)

    # -- Sequence ---------------------------------------------------------
    seq_dur = sec_to_frames(
        sum(c["end"] - c["start"] for c in cutlist), fps,
    )
    sequence = ET.SubElement(children, "sequence", id="seq-1")
    ET.SubElement(sequence, "name").text = sequence_name
    ET.SubElement(sequence, "duration").text = str(seq_dur)
    _add_rate(sequence, fps)
    ET.SubElement(sequence, "in").text = "0"
    ET.SubElement(sequence, "out").text = str(seq_dur)

    tc = ET.SubElement(sequence, "timecode")
    _add_rate(tc, fps)
    ET.SubElement(tc, "string").text = "00:00:00:00"
    ET.SubElement(tc, "frame").text = "0"
    ET.SubElement(tc, "displayformat").text = "NDF"

    media = ET.SubElement(sequence, "media")

    # -- Video tracks -----------------------------------------------------
    video_el = ET.SubElement(media, "video")
    v_fmt = ET.SubElement(video_el, "format")
    _add_video_sample_chars(v_fmt, fps, ref_info["width"], ref_info["height"])

    video_sources = [
        (i, p) for i, p in enumerate(source_paths)
        if file_infos[i]["has_video"]
    ]
    for track_idx, src_path in video_sources:
        track = ET.SubElement(video_el, "track")
        ET.SubElement(track, "enabled").text = "TRUE"
        ET.SubElement(track, "locked").text = "FALSE"

        src_resolved = str(Path(src_path).resolve())
        offset_sec = sync_offsets.get(src_resolved, 0.0)
        info = file_infos[track_idx]
        dur_frames = sec_to_frames(info["duration_sec"], fps)

        timeline_pos = 0
        for cut in cutlist:
            in_sec = cut["start"] - offset_sec
            out_sec = cut["end"] - offset_sec
            if in_sec < 0 or out_sec > info["duration_sec"]:
                in_sec = max(0, in_sec)
                out_sec = min(info["duration_sec"], out_sec)
                if out_sec <= in_sec:
                    continue
            in_frames = sec_to_frames(in_sec, fps)
            out_frames = sec_to_frames(out_sec, fps)
            clip_dur = out_frames - in_frames

            ci = ET.SubElement(
                track, "clipitem", id=f"clip-v{track_idx}-{timeline_pos}",
            )
            ET.SubElement(ci, "masterclipid").text = f"master-{track_idx}"
            ET.SubElement(ci, "name").text = Path(src_path).name
            ET.SubElement(ci, "enabled").text = "TRUE"
            ET.SubElement(ci, "duration").text = str(dur_frames)
            _add_rate(ci, fps)
            ET.SubElement(ci, "start").text = str(timeline_pos)
            ET.SubElement(ci, "end").text = str(timeline_pos + clip_dur)
            ET.SubElement(ci, "in").text = str(in_frames)
            ET.SubElement(ci, "out").text = str(out_frames)
            ET.SubElement(ci, "file", id=f"file-{track_idx}")

            timeline_pos += clip_dur

    # -- Audio tracks (all sources with audio) ----------------------------
    audio_el = ET.SubElement(media, "audio")
    a_fmt = ET.SubElement(audio_el, "format")
    _add_audio_sample_chars(a_fmt)

    audio_sources = [
        (i, p) for i, p in enumerate(source_paths)
        if file_infos[i]["has_audio"]
    ]
    for track_idx, src_path in audio_sources:
        track_audio = ET.SubElement(audio_el, "track")
        ET.SubElement(track_audio, "enabled").text = "TRUE"
        ET.SubElement(track_audio, "locked").text = "FALSE"

        src_resolved = str(Path(src_path).resolve())
        offset_sec = sync_offsets.get(src_resolved, 0.0)
        info = file_infos[track_idx]
        dur_frames = sec_to_frames(info["duration_sec"], fps)

        tl = 0
        for cut in cutlist:
            in_sec = cut["start"] - offset_sec
            out_sec = cut["end"] - offset_sec
            if in_sec < 0 or out_sec > info["duration_sec"]:
                in_sec = max(0, in_sec)
                out_sec = min(info["duration_sec"], out_sec)
                if out_sec <= in_sec:
                    continue
            in_f = sec_to_frames(in_sec, fps)
            out_f = sec_to_frames(out_sec, fps)
            clip_dur = out_f - in_f

            ci = ET.SubElement(
                track_audio, "clipitem", id=f"clip-a{track_idx}-{tl}",
            )
            ET.SubElement(ci, "masterclipid").text = f"master-{track_idx}"
            ET.SubElement(ci, "name").text = Path(src_path).name
            ET.SubElement(ci, "enabled").text = "TRUE"
            ET.SubElement(ci, "duration").text = str(dur_frames)
            _add_rate(ci, fps)
            ET.SubElement(ci, "start").text = str(tl)
            ET.SubElement(ci, "end").text = str(tl + clip_dur)
            ET.SubElement(ci, "in").text = str(in_f)
            ET.SubElement(ci, "out").text = str(out_f)
            ET.SubElement(ci, "file", id=f"file-{track_idx}")
            sourcetrack = ET.SubElement(ci, "sourcetrack")
            ET.SubElement(sourcetrack, "mediatype").text = "audio"
            ET.SubElement(sourcetrack, "trackindex").text = "1"

            tl += clip_dur

    # -- Serialize --------------------------------------------------------
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    xml_str = ET.tostring(root, encoding="unicode")
    output_path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE xmeml>\n' + xml_str,
        encoding="utf-8",
    )
