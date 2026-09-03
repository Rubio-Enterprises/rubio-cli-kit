"""Public data types for the table-driven CLI contract harness."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rubio_cli_kit.testing import CliSandbox

CommandSetup = Callable[['CliSandbox'], None]


def _empty_setup(sandbox: CliSandbox) -> None:
    del sandbox


@dataclass(frozen=True)
class CommandContract:
    """External invocations required to exercise one non-hook console script."""

    name: str
    help_paths: tuple[tuple[str, ...], ...]
    json_args: tuple[str, ...] | None
    usage_error_args: tuple[str, ...]
    runtime_error_args: tuple[str, ...]
    setup: CommandSetup = _empty_setup
    runtime_error_setup: CommandSetup | None = None
    darwin_only: bool = False
    default_command: str | None = None
