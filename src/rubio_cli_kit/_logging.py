"""structlog configuration shared by every command.

Diagnostics always go to stderr. Warning is the default level, debug is enabled
by ``--verbose``, and JSON output keeps diagnostics structured for machines.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

import structlog


@dataclass
class _LogState:
    verbose: bool = False
    json_output: bool = False


_STATE = _LogState()


def configure(*, verbose: bool | None = None, json_output: bool | None = None) -> None:
    """Configure logging, retaining the current value of omitted options."""
    if verbose is not None:
        _STATE.verbose = verbose
    if json_output is not None:
        _STATE.json_output = json_output

    processors: list[structlog.typing.Processor] = [structlog.processors.add_log_level]
    if _STATE.json_output:
        processors += [structlog.processors.format_exc_info, structlog.processors.JSONRenderer()]
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if _STATE.verbose else logging.WARNING
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.typing.FilteringBoundLogger:
    """Return a named logger honoring the current configuration."""
    return structlog.get_logger(name)


configure()
