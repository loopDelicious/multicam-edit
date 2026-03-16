"""
Audio extraction and "clearest track" selection.
Uses FFmpeg for extraction and librosa for analysis.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

import librosa
import numpy as np


# Sample rate used for analysis (Whisper-friendly)
ANALYSIS_SR = 16000
# Max duration to load for analysis (seconds) to keep memory reasonable
MAX_ANALYSIS_DURATION = 600  # 10 minutes


def extract_audio_to_wav(
    media_path: Path,
    output_path: Path | None = None,
    sample_rate: int = ANALYSIS_SR,
    mono: bool = True,
    max_duration_sec: float | None = MAX_ANALYSIS_DURATION,
) -> Path:
    """Extract audio from a video/audio file to a WAV file using FFmpeg."""
    out = output_path or Path(tempfile.mkstemp(suffix=".wav")[1])
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(media_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        "1" if mono else "2",
    ]
    if max_duration_sec is not None:
        cmd.extend(["-t", str(max_duration_sec)])
    cmd.append(str(out))
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def load_audio_segment(path: Path, sr: int = ANALYSIS_SR, max_sec: float | None = MAX_ANALYSIS_DURATION) -> np.ndarray:
    """Load audio from a media file (via temp WAV if not WAV) for analysis."""
    path = Path(path)
    if path.suffix.lower() in (".wav", ".wave"):
        y, _ = librosa.load(str(path), sr=sr, duration=max_sec, mono=True)
        return y
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = Path(f.name)
    try:
        extract_audio_to_wav(path, wav_path, sample_rate=sr, max_duration_sec=max_sec)
        y, _ = librosa.load(str(wav_path), sr=sr, mono=True)
        return y
    finally:
        wav_path.unlink(missing_ok=True)


def compute_loudness_rms(y: np.ndarray, frame_length: int = 2048, hop_length: int = 512) -> float:
    """Average RMS (loudness) over the signal."""
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    return float(np.mean(rms)) if rms.size else 0.0


def compute_noise_estimate(y: np.ndarray, top_db: float = 20.0) -> float:
    """Rough noise level: energy in quieter segments (bottom percentile of frame energy)."""
    frame_length = 2048
    hop_length = 512
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    if rms.size < 10:
        return 0.0
    # Noise ~ low percentile of RMS
    noise_rms = float(np.percentile(rms, 10))
    return noise_rms


def compute_snr_db(loudness_rms: float, noise_rms: float) -> float:
    """SNR in dB; higher is cleaner."""
    if noise_rms <= 0:
        return 60.0  # cap
    return float(20 * np.log10((loudness_rms + 1e-10) / (noise_rms + 1e-10)))


def score_audio_clarity(y: np.ndarray) -> float:
    """
    Single score: higher = clearer (louder, less noise).
    Used to pick the best reference track.
    """
    loudness = compute_loudness_rms(y)
    noise = compute_noise_estimate(y)
    snr = compute_snr_db(loudness, noise)
    # Prefer some loudness; avoid clipping penalty by capping
    loudness_score = min(loudness * 50, 10.0)
    return loudness_score + snr * 0.1


def select_clearest_audio(
    media_paths: List[Path],
    max_analysis_sec: float = MAX_ANALYSIS_DURATION,
) -> Tuple[Path, List[Path]]:
    """
    From a list of video/audio files, return (reference_path, all_paths_ordered)
    with the clearest as reference (first). Order is: reference first, then rest by score descending.
    """
    if not media_paths:
        raise ValueError("No media paths provided")
    if len(media_paths) == 1:
        return media_paths[0], list(media_paths)

    scores: List[Tuple[float, Path]] = []
    for path in media_paths:
        try:
            y = load_audio_segment(path, max_sec=max_analysis_sec)
            if y.size < 1000:
                scores.append((-1e9, path))
                continue
            sc = score_audio_clarity(y)
            scores.append((sc, path))
        except Exception:
            scores.append((-1e9, path))

    scores.sort(key=lambda x: -x[0])
    ordered = [p for _, p in scores]
    return ordered[0], ordered
