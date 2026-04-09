"""
Batch-transcribe a directory of video/audio files.

Produces:
  - One .srt per input file  (e.g. interview_01.srt)
  - A combined transcripts.md ready for upload to Claude / any LLM
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from .transcribe import transcribe_media_to_srt

MEDIA_EXTS = {".mp4", ".mov", ".mxf", ".avi", ".mkv", ".wav", ".aiff", ".m4a", ".mp3", ".webm"}


def find_media(directory: Path) -> List[Path]:
    """Return sorted list of media files in *directory* (non-recursive)."""
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in MEDIA_EXTS
    )


def srt_to_plain_text(srt: str) -> str:
    """Strip SRT index lines and timestamps, returning just the spoken text."""
    lines: list[str] = []
    for line in srt.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.isdigit():
            continue
        if "-->" in line:
            continue
        lines.append(line)
    return " ".join(lines)


def batch_transcribe(
    directory: Path,
    output_dir: Optional[Path] = None,
    model: str = "base",
    language: Optional[str] = None,
    device: str = "auto",
    compute_type: str = "default",
    plain_text: bool = True,
) -> Path:
    """
    Transcribe every media file in *directory*.

    Returns the path to the combined transcripts.md.
    """
    console = Console()
    directory = directory.resolve()
    if not directory.is_dir():
        console.print(f"[red]Not a directory: {directory}[/red]")
        raise SystemExit(1)

    out = (output_dir or directory).resolve()
    out.mkdir(parents=True, exist_ok=True)

    files = find_media(directory)
    if not files:
        console.print(f"[red]No media files found in {directory}[/red]")
        raise SystemExit(1)

    console.print(f"[green]Found {len(files)} media file(s) in {directory}[/green]")
    console.print(f"[dim]Model: {model} | Language: {language or 'auto-detect'} | Output: {out}[/dim]\n")

    results: list[tuple[str, str, str]] = []  # (filename, srt, plain)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Transcribing", total=len(files))

        for media_path in files:
            progress.update(task, description=f"[cyan]{media_path.name}[/cyan]")
            t0 = time.monotonic()

            srt_content = transcribe_media_to_srt(
                media_path,
                model_size=model,
                language=language,
                device=device,
                compute_type=compute_type,
            )

            elapsed = time.monotonic() - t0
            srt_out = out / f"{media_path.stem}.srt"
            srt_out.write_text(srt_content, encoding="utf-8")

            plain = srt_to_plain_text(srt_content) if plain_text else ""
            results.append((media_path.name, srt_content, plain))

            progress.console.print(
                f"  [green]✓[/green] {media_path.name} → {srt_out.name}  [dim]({elapsed:.1f}s)[/dim]"
            )
            progress.advance(task)

    md_path = out / "transcripts.md"
    md_lines = ["# Transcripts\n"]
    for filename, srt_content, plain in results:
        md_lines.append(f"## {filename}\n")
        if plain_text:
            md_lines.append(plain)
        else:
            md_lines.append(f"```\n{srt_content}\n```")
        md_lines.append("")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    console.print(f"\n[green bold]Done.[/green bold]  Combined file: [bold]{md_path}[/bold]")
    console.print(f"[dim]Upload {md_path.name} to Claude and ask it to catalog by topic.[/dim]")
    return md_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-transcribe a directory of videos and produce a combined transcript for LLM upload.",
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory containing MP4/video files to transcribe",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write .srt files and transcripts.md (default: same as input directory)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="base",
        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
        help="Whisper model size (default: base)",
    )
    parser.add_argument(
        "--language",
        type=str,
        default=None,
        help="Language hint for Whisper (e.g. en, es, fr). Default: auto-detect.",
    )
    parser.add_argument(
        "--srt-only",
        action="store_true",
        help="Include full SRT (with timestamps) in transcripts.md instead of plain text",
    )
    args = parser.parse_args()

    batch_transcribe(
        directory=args.directory,
        output_dir=args.output_dir,
        model=args.model,
        language=args.language,
        plain_text=not args.srt_only,
    )


if __name__ == "__main__":
    main()
