"""
Command-line interface for the multicam edit pipeline.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from .audio import select_clearest_audio
from .cutlist import load_cutlist, run_interactive_cutlist, run_outline_conversation, save_cutlist, parse_srt, segments_to_cutlist
from .sync import compute_sync_offsets
from .transcribe import transcribe_media_to_srt
from .xml_export import build_edl, build_fcp7_xml


def collect_media_paths(project_dir: Path, sources_override: Optional[List[str]]) -> List[Path]:
    """Gather video/audio files from project dir or --sources."""
    if sources_override:
        paths = [Path(p) for p in sources_override if Path(p).exists()]
        return paths
    raw = project_dir / "raw"
    if raw.exists():
        candidates = list(raw.glob("*"))
    else:
        candidates = list(project_dir.glob("*"))
    exts = {".mp4", ".mov", ".mxf", ".avi", ".mkv", ".wav", ".aiff", ".m4a", ".mp3"}
    return [p for p in candidates if p.suffix.lower() in exts and p.is_file()]


def run(
    project_dir: Path,
    sources: Optional[List[str]] = None,
    model: str = "base",
    language: Optional[str] = None,
    no_transcribe: bool = False,
    no_sync: bool = False,
    cutlist_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    interactive: bool = True,
    fps: float = 23.976,
    use_outline: bool = True,
) -> None:
    console = Console()
    project_dir = Path(project_dir).resolve()
    if not project_dir.is_dir():
        console.print(f"[red]Project directory does not exist: {project_dir}[/red]")
        return

    media_paths = collect_media_paths(project_dir, sources)
    if not media_paths:
        console.print("[red]No video/audio files found. Add files to project_dir/raw or use --sources.[/red]")
        return

    console.print(f"[green]Found {len(media_paths)} media file(s).[/green]")
    reference_path, ordered_paths = select_clearest_audio(media_paths)
    console.print(f"[green]Reference (clearest audio): {reference_path.name}[/green]")

    # Paths
    srt_path = project_dir / "transcript.srt"
    cutlist_file = cutlist_path or project_dir / "cutlist.json"
    out_xml = output_path or project_dir / "output.xml"
    cache_file = project_dir / ".sync_offsets.json"

    # 1) Transcribe
    if not no_transcribe:
        console.print("[cyan]Transcribing reference audio...[/cyan]")
        srt_content = transcribe_media_to_srt(reference_path, model_size=model, language=language)
        srt_path.write_text(srt_content, encoding="utf-8")
        console.print(f"[green]Saved transcript to {srt_path}[/green]")
    else:
        if not srt_path.exists():
            console.print("[red]--no-transcribe set but transcript.srt not found.[/red]")
            return
        console.print("[dim]Skipping transcription (using existing transcript.srt).[/dim]")

    # 2) Sync
    other_paths = [p for p in ordered_paths if p != reference_path]
    if other_paths:
        if not no_sync:
            console.print("[cyan]Computing sync offsets...[/cyan]")
            sync_offsets = compute_sync_offsets(reference_path, other_paths, project_dir, cache_file=cache_file)
            console.print("[green]Sync offsets saved.[/green]")
        else:
            import json
            if not cache_file.exists():
                console.print("[red]--no-sync set but .sync_offsets.json not found.[/red]")
                return
            sync_offsets = json.loads(cache_file.read_text()).get("offsets", {})
    else:
        sync_offsets = {str(reference_path.resolve()): 0.0}
    # Ensure all paths in sync_offsets use resolved paths for lookup
    resolved_offsets = {}
    for p in ordered_paths:
        key = str(Path(p).resolve())
        resolved_offsets[key] = sync_offsets.get(key, 0.0)

    # 3) Cut list
    if cutlist_file.exists():
        cutlist = load_cutlist(cutlist_file)
        console.print(f"[green]Loaded cut list from {cutlist_file} ({len(cutlist)} cuts).[/green]")
    else:
        if interactive:
            if use_outline:
                # Propose outline, then accept commands: merge, split, reorder, delete
                cutlist = run_outline_conversation(srt_path, cutlist_file, console=console)
            else:
                cutlist = run_interactive_cutlist(srt_path, cutlist_file, console=console)
        else:
            # Default: one cut per SRT segment
            content = srt_path.read_text(encoding="utf-8", errors="replace")
            segments = parse_srt(content)
            cutlist = segments_to_cutlist(segments)
            save_cutlist(cutlist_file, cutlist)
            console.print(f"[green]Saved default cut list to {cutlist_file}[/green]")
    if not cutlist:
        console.print("[yellow]No cut list. Create cutlist.json or run interactively.[/yellow]")
        return

    # 4) Export XML and EDL
    console.print(f"[cyan]Building Premiere XML and EDL ({fps} fps)...[/cyan]")
    build_fcp7_xml(
        project_dir=project_dir,
        source_paths=ordered_paths,
        cutlist=cutlist,
        sync_offsets=resolved_offsets,
        output_path=out_xml,
        fps=fps,
    )
    out_edl = project_dir / "output.edl"
    build_edl(cutlist=cutlist, reference_name=reference_path.stem, output_path=out_edl, fps=fps)
    console.print(f"[green]Done.[/green]")
    console.print(f"  XML: [bold]{out_xml}[/bold]")
    console.print(f"  EDL: [bold]{out_edl}[/bold]")
    console.print(
        "[dim]If XML import fails: use File > Import and choose output.edl, "
        "then link the reel to your reference video when prompted.[/dim]"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multicam edit pipeline: transcribe → sync → cut list → Premiere XML (local only)."
    )
    parser.add_argument(
        "project_dir",
        type=Path,
        nargs="?",
        default=Path.cwd(),
        help="Project directory (raw files, transcript.srt, cutlist.json, output.xml)",
    )
    parser.add_argument(
        "--sources",
        type=str,
        nargs="+",
        default=None,
        help="Override: paths to video/audio files (default: project_dir/raw or project_dir)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="base",
        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
        help="Whisper model size (default: base)",
    )
    parser.add_argument("--language", type=str, default=None, help="Language hint for Whisper (e.g. en)")
    parser.add_argument("--no-transcribe", action="store_true", help="Use existing transcript.srt")
    parser.add_argument("--no-sync", action="store_true", help="Use existing .sync_offsets.json")
    parser.add_argument("--cutlist", type=Path, default=None, help="Cut list JSON path (default: project_dir/cutlist.json)")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output XML path (default: project_dir/output.xml)")
    parser.add_argument("--no-interactive", action="store_true", help="Do not prompt; use default cut list from SRT")
    parser.add_argument("--no-outline", action="store_true", help="Use simple 3-option prompt instead of interactive outline commands")
    parser.add_argument("--fps", type=float, default=23.976, help="Timeline frame rate (default: 23.976 for 24p cinematic)")
    args = parser.parse_args()
    run(
        project_dir=args.project_dir,
        sources=args.sources,
        model=args.model,
        language=args.language,
        no_transcribe=args.no_transcribe,
        no_sync=args.no_sync,
        cutlist_path=args.cutlist,
        output_path=args.output,
        interactive=not args.no_interactive,
        fps=args.fps,
        use_outline=not args.no_outline,
    )


if __name__ == "__main__":
    main()
