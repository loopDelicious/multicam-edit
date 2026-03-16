"""
Parse SRT into segments; interactive or file-based cut list.
Cut list = ordered list of {start, end, label?} defining timeline cuts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.table import Table

try:
    import questionary
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False


def srt_time_to_seconds(s: str) -> float:
    """Parse SRT timestamp HH:MM:SS,mmm or HH:MM:SS.mmm to seconds."""
    s = s.strip().replace(",", ".")
    parts = s.split(":")
    if len(parts) != 3:
        return 0.0
    h, m, sec = float(parts[0]), float(parts[1]), float(parts[2])
    return h * 3600 + m * 60 + sec


def parse_srt(content: str) -> List[dict]:
    """Parse SRT content into list of {index, start, end, text}."""
    blocks = re.split(r"\n\s*\n", content.strip())
    segments = []
    for block in blocks:
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        if len(lines) < 3:
            continue
        # Line 0: index; Line 1: time range; Rest: text
        try:
            idx = int(lines[0])
        except ValueError:
            continue
        time_line = lines[1]
        m = re.match(r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})", time_line)
        if not m:
            continue
        start = srt_time_to_seconds(m.group(1))
        end = srt_time_to_seconds(m.group(2))
        text = " ".join(lines[2:])
        segments.append({"index": idx, "start": start, "end": end, "text": text})
    return segments


def segments_to_cutlist(segments: List[dict]) -> List[dict]:
    """Convert SRT segments to cut list entries (start, end, label)."""
    return [
        {"start": s["start"], "end": s["end"], "label": (s.get("text") or "")[:80]}
        for s in segments
    ]


def load_cutlist(path: Path) -> List[dict]:
    """Load cut list from JSON file."""
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return data.get("cuts", data.get("cutlist", []))


def save_cutlist(path: Path, cutlist: List[dict]) -> None:
    """Save cut list to JSON."""
    with open(path, "w") as f:
        json.dump(cutlist, f, indent=2)


def run_interactive_cutlist(
    srt_path: Path,
    cutlist_path: Path,
    console: Optional[Console] = None,
) -> List[dict]:
    """
    Parse SRT, show segments, let user confirm or edit, then save cut list.
    If questionary is not available, just generate default cutlist from SRT and save.
    """
    console = console or Console()
    content = srt_path.read_text(encoding="utf-8", errors="replace")
    segments = parse_srt(content)
    if not segments:
        console.print("[yellow]No segments found in SRT. Create cutlist.json manually.[/yellow]")
        return []

    default_cutlist = segments_to_cutlist(segments)

    if not HAS_QUESTIONARY:
        save_cutlist(cutlist_path, default_cutlist)
        console.print(f"[green]Saved default cut list ({len(default_cutlist)} cuts) to {cutlist_path}[/green]")
        return default_cutlist

    # Show table
    table = Table(title="SRT segments (will become cut list)")
    table.add_column("#", style="dim")
    table.add_column("Start", style="cyan")
    table.add_column("End", style="cyan")
    table.add_column("Label", style="green")
    for s in segments[:50]:  # cap display
        table.add_row(str(s["index"]), f"{s['start']:.1f}s", f"{s['end']:.1f}s", (s.get("text") or "")[:60])
    if len(segments) > 50:
        table.add_row("...", "", "", f"... and {len(segments) - 50} more")
    console.print(table)

    choice = questionary.select(
        "Use these segments as cut list?",
        choices=["Yes, use as-is", "Yes, then I'll edit the JSON file", "No, I'll provide cutlist.json myself"],
    ).ask()
    if choice is None:
        choice = "Yes, use as-is"
    if "use as-is" in choice or "edit the JSON" in choice:
        save_cutlist(cutlist_path, default_cutlist)
        console.print(f"[green]Saved cut list to {cutlist_path}[/green]")
        if "edit the JSON" in choice:
            console.print("Edit that file, then re-run with --no-transcribe to export XML.")
        return default_cutlist
    return []


def _print_outline(cuts: List[dict], console: Console, max_preview: int = 50) -> None:
    """Print numbered outline of the cut list."""
    table = Table(title="Current outline (cut list)")
    table.add_column("#", style="dim", width=4)
    table.add_column("Start", style="cyan", width=8)
    table.add_column("End", style="cyan", width=8)
    table.add_column("Label", style="green")
    for i, c in enumerate(cuts[:max_preview], 1):
        start_s = f"{c['start']:.1f}s"
        end_s = f"{c['end']:.1f}s"
        label = (c.get("label") or "")[:55]
        table.add_row(str(i), start_s, end_s, label)
    if len(cuts) > max_preview:
        table.add_row("...", "", "", f"... and {len(cuts) - max_preview} more")
    console.print(table)
    console.print(f"[dim]Total: {len(cuts)} segments[/dim]")


def run_outline_conversation(
    srt_path: Path,
    cutlist_path: Path,
    console: Optional[Console] = None,
) -> List[dict]:
    """
    Propose an outline from the SRT, then loop: accept commands to merge, split,
    reorder, or delete segments. Type 'a' or 'accept' when done.
    """
    console = console or Console()
    content = srt_path.read_text(encoding="utf-8", errors="replace")
    segments = parse_srt(content)
    if not segments:
        console.print("[yellow]No segments found in SRT.[/yellow]")
        return []
    cuts = segments_to_cutlist(segments)

    console.print("[bold]Proposed outline from transcript:[/bold]")
    _print_outline(cuts, console)
    console.print(
        "\n[bold]Commands (hit Enter after each):[/bold]\n"
        "  [cyan]a[/cyan] or [cyan]accept[/cyan]  – use this outline and continue\n"
        "  [cyan]m n1 n2[/cyan]  – merge segments n1 through n2 (e.g. m 3 6)\n"
        "  [cyan]s n sec[/cyan]  – split segment n at time in seconds (e.g. s 2 45.5)\n"
        "  [cyan]r n1 n2 ...[/cyan] – reorder by new indices (e.g. r 2 1 3 4)\n"
        "  [cyan]d n[/cyan]  – delete segment n\n"
        "  [cyan]p[/cyan]  – print outline again\n"
        "  [cyan]?[/cyan]  – show this help\n"
    )

    while True:
        try:
            line = input("Outline> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/yellow]")
            return []
        if not line:
            continue
        parts = line.split()
        cmd = (parts[0] or "").lower()
        args = parts[1:]

        if cmd in ("a", "accept"):
            save_cutlist(cutlist_path, cuts)
            console.print(f"[green]Saved outline ({len(cuts)} segments) to {cutlist_path}[/green]")
            return cuts

        if cmd == "p":
            _print_outline(cuts, console)
            continue

        if cmd == "?":
            console.print(
                "  a / accept  – done\n"
                "  m n1 n2    – merge segments n1–n2\n"
                "  s n sec    – split segment n at sec\n"
                "  r n1 n2 …  – reorder\n"
                "  d n        – delete segment n\n"
                "  p          – print outline\n"
            )
            continue

        if cmd == "m" and len(args) >= 2:
            try:
                n1, n2 = int(args[0]), int(args[1])
                if n1 < 1 or n2 < 1 or n1 > len(cuts) or n2 > len(cuts) or n1 > n2:
                    console.print("[red]Invalid segment numbers.[/red]")
                    continue
                merged = {
                    "start": cuts[n1 - 1]["start"],
                    "end": cuts[n2 - 1]["end"],
                    "label": " | ".join((cuts[i - 1].get("label") or "")[:30] for i in range(n1, n2 + 1)),
                }
                cuts = cuts[: n1 - 1] + [merged] + cuts[n2:]
                console.print(f"[green]Merged segments {n1}–{n2} into one.[/green]")
            except ValueError:
                console.print("[red]Usage: m n1 n2 (e.g. m 3 6)[/red]")
            continue

        if cmd == "s" and len(args) >= 2:
            try:
                n, at = int(args[0]), float(args[1])
                if n < 1 or n > len(cuts):
                    console.print("[red]Invalid segment number.[/red]")
                    continue
                c = cuts[n - 1]
                if at <= c["start"] or at >= c["end"]:
                    console.print("[red]Split time must be between start and end.[/red]")
                    continue
                left = {"start": c["start"], "end": at, "label": (c.get("label") or "")[:40] + " (1)"}
                right = {"start": at, "end": c["end"], "label": (c.get("label") or "")[:40] + " (2)"}
                cuts = cuts[: n - 1] + [left, right] + cuts[n:]
                console.print(f"[green]Split segment {n} at {at}s.[/green]")
            except ValueError:
                console.print("[red]Usage: s n sec (e.g. s 2 45.5)[/red]")
            continue

        if cmd == "r" and len(args) >= 1:
            try:
                indices = [int(x) for x in args]
                if not all(1 <= i <= len(cuts) for i in indices) or len(set(indices)) != len(cuts):
                    console.print("[red]Supply each segment number 1..N exactly once (e.g. r 2 1 3 4).[/red]")
                    continue
                cuts = [cuts[i - 1] for i in indices]
                console.print("[green]Reordered.[/green]")
            except ValueError:
                console.print("[red]Usage: r n1 n2 ... (e.g. r 2 1 3 4)[/red]")
            continue

        if cmd == "d" and len(args) == 1:
            try:
                n = int(args[0])
                if n < 1 or n > len(cuts):
                    console.print("[red]Invalid segment number.[/red]")
                    continue
                cuts.pop(n - 1)
                console.print(f"[green]Deleted segment {n}.[/green]")
            except ValueError:
                console.print("[red]Usage: d n[/red]")
            continue

        console.print("[yellow]Unknown command. Type ? for help.[/yellow]")
