from __future__ import annotations

import json

import pytest

from rubio_cli_kit import _output


def test_data_helpers_keep_stdout_machine_clean(capsys: pytest.CaptureFixture[str]) -> None:
    _output.emit_text("plain text")
    _output.emit_json({"result": "ok"})

    captured = capsys.readouterr()
    assert captured.out.startswith("plain text\n")
    assert json.loads(captured.out.removeprefix("plain text\n")) == {"result": "ok"}
    assert captured.err == ""


def test_status_helpers_write_only_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    _output.status("working")
    _output.warn("careful")
    _output.error("failed")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "working" in captured.err
    assert "warning: careful" in captured.err
    assert "failed" in captured.err


def test_render_table_returns_unwrapped_plain_text() -> None:
    table = _output.render_table(
        [{"name": "alpha", "state": "ready"}, {"name": "beta", "state": "blocked"}],
        [("name", "NAME"), ("state", "STATE")],
    )

    assert table == "NAME   STATE\nalpha  ready\nbeta   blocked"
