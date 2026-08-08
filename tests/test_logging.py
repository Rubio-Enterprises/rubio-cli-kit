from __future__ import annotations

import json

import pytest

from rubio_cli_kit import _logging


def test_verbose_mode_enables_debug_diagnostics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = _logging.get_logger("example")

    _logging.configure(verbose=False, json_output=False)
    log.debug("hidden")
    assert capsys.readouterr().err == ""

    _logging.configure(verbose=True)
    log.debug("visible", answer=42)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "visible" in captured.err
    assert "42" in captured.err


def test_json_mode_keeps_diagnostics_structured(capsys: pytest.CaptureFixture[str]) -> None:
    _logging.configure(verbose=False, json_output=True)
    _logging.get_logger("example").warning("careful", code=7)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "code": 7,
        "event": "careful",
        "level": "warning",
    }
