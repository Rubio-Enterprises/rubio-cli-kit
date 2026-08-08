from __future__ import annotations

from pathlib import Path

import pytest

from rubio_cli_kit._paths import xdg_dir


def test_xdg_dir_prefers_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", "/custom/state")

    assert xdg_dir("XDG_STATE_HOME", ".local", "state") == Path("/custom/state")


def test_xdg_dir_falls_back_below_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", "/home/example")

    assert xdg_dir("XDG_STATE_HOME", ".local", "state") == Path("/home/example/.local/state")
