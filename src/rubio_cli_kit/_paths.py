"""XDG base-directory resolution shared by commands."""

from __future__ import annotations

import os
from pathlib import Path


def xdg_dir(env_var: str, *fallback: str) -> Path:
    """Resolve an XDG base directory from the environment or a HOME fallback."""
    override = os.environ.get(env_var)
    if override:
        path = Path(override)
        if path.is_absolute():
            return path
    return Path.home().joinpath(*fallback)
