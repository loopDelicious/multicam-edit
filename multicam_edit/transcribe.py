"""
Transcription using faster-whisper (local). Produces timestamped SRT.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Optional

from faster_whisper import WhisperModel


def seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: List[dict]) -> str:
    """Convert list of {start, end, text} to SRT string."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = seg["start"]
        end = seg["end"]
        text = (seg.get("text") or "").strip()
        lines.append(f"{i}")
        lines.append(f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).strip()


def transcribe_to_srt(
    audio_path: Path,
    model_size: str = "base",
    language: Optional[str] = None,
    device: str = "auto",
    compute_type: str = "default",
) -> str:
    """
    Run faster-whisper on an audio file and return SRT content.
    audio_path can be video or audio; we use the first audio stream.
    """
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    # faster_whisper can accept a path to audio/video
    segments_generator, info = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=False,
        vad_filter=True,
    )
    segments_list = []
    for s in segments_generator:
        segments_list.append({"start": s.start, "end": s.end, "text": (s.text or "").strip()})
    return segments_to_srt(segments_list)


def transcribe_media_to_srt(
    media_path: Path,
    model_size: str = "base",
    language: Optional[str] = None,
    device: str = "auto",
    compute_type: str = "default",
    sample_rate: int = 16000,
) -> str:
    """
    Transcribe a video/audio file. If not raw audio, we need to extract to WAV first
    because faster_whisper works best with a file path; FFmpeg can decode.
    faster_whisper accepts video paths and uses ffmpeg internally in some builds,
    but to be safe we extract to temp WAV.
    """
    from .audio import extract_audio_to_wav

    path = Path(media_path)
    if path.suffix.lower() in (".wav", ".wave"):
        return transcribe_to_srt(path, model_size=model_size, language=language, device=device, compute_type=compute_type)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = Path(f.name)
    try:
        extract_audio_to_wav(path, wav_path, sample_rate=sample_rate)
        return transcribe_to_srt(wav_path, model_size=model_size, language=language, device=device, compute_type=compute_type)
    finally:
        wav_path.unlink(missing_ok=True)
