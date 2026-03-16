"""
Multi-camera sync by matching audio waveforms (cross-correlation).
Results cached in .sync_offsets.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import numpy as np
from scipy import signal

from .audio import load_audio_segment, ANALYSIS_SR


def compute_offset_seconds(
    reference_audio: np.ndarray,
    other_audio: np.ndarray,
    sample_rate: int = ANALYSIS_SR,
) -> float:
    """
    Find offset in seconds by which 'other' is delayed relative to reference.
    Positive = other starts later. Uses cross-correlation.
    """
    ref = reference_audio.astype(np.float64)
    other = other_audio.astype(np.float64)
    # Match length: pad shorter
    if len(ref) < len(other):
        ref = np.pad(ref, (0, len(other) - len(ref)))
    elif len(other) < len(ref):
        other = np.pad(other, (0, len(ref) - len(other)))
    corr = signal.correlate(ref, other, mode="full")
    lag_arr = signal.correlation_lags(ref.size, other.size, mode="full")
    best = np.argmax(np.abs(corr))
    lag_samples = lag_arr[best]
    return float(lag_samples) / sample_rate


def compute_sync_offsets(
    reference_path: Path,
    other_paths: List[Path],
    project_dir: Path,
    cache_file: Path | None = None,
    max_analysis_sec: float = 600,
) -> Dict[str, float]:
    """
    Return dict: path_str -> offset_seconds (for each file; reference has 0).
    Paths are normalized for cache key. Cached to project_dir/.sync_offsets.json.
    """
    cache_file = cache_file or project_dir / ".sync_offsets.json"
    all_paths = [reference_path] + list(other_paths)
    path_keys = [str(Path(p).resolve()) for p in all_paths]

    # Try load cache (same set of files)
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                data = json.load(f)
            if data.get("paths") == path_keys:
                return data.get("offsets", {})
        except Exception:
            pass

    ref_audio = load_audio_segment(reference_path, max_sec=max_analysis_sec)
    offsets: Dict[str, float] = {path_keys[0]: 0.0}

    for path in other_paths:
        key = str(Path(path).resolve())
        other_audio = load_audio_segment(path, max_sec=max_analysis_sec)
        offset = compute_offset_seconds(ref_audio, other_audio)
        offsets[key] = offset

    with open(cache_file, "w") as f:
        json.dump({"paths": path_keys, "offsets": offsets}, f, indent=2)
    return offsets
