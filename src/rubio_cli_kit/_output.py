"""The stdout=data / stderr=status discipline, as helpers.

stdout carries data only, written with plain ``typer.echo``. Rich is reserved
for stderr, where humans read status, warnings, and errors.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import typer
from rich.console import Console

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_stderr = Console(stderr=True, highlight=False, markup=False, soft_wrap=True)


def emit_text(text: str) -> None:
    """Write human-readable data to stdout without wrapping it."""
    typer.echo(text)


def emit_json(payload: object) -> None:
    """Write machine-clean JSON data to stdout."""
    typer.echo(json.dumps(payload, indent=2))


def status(message: str) -> None:
    """Write human progress or informational chatter to stderr."""
    _stderr.print(message)


def warn(message: str) -> None:
    """Write a human-facing warning to stderr."""
    _stderr.print(f"warning: {message}", style="yellow")


def error(message: str) -> None:
    """Write a human-facing error to stderr."""
    _stderr.print(message, style="bold red")


def render_table(
    rows: Sequence[Mapping[str, str]],
    columns: Sequence[tuple[str, str]],
) -> str:
    """Align rows into a plain-text table suitable for stdout."""
    widths = {key: len(header) for key, header in columns}
    for row in rows:
        for key, _ in columns:
            widths[key] = max(widths[key], len(row.get(key, "")))
    lines = ["  ".join(f"{header:<{widths[key]}}" for key, header in columns).rstrip()]
    lines.extend(
        "  ".join(f"{row.get(key, ''):<{widths[key]}}" for key, _ in columns).rstrip()
        for row in rows
    )
    return "\n".join(lines)
