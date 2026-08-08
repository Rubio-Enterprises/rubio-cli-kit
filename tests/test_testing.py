from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rubio_cli_kit.testing import CliSandbox, FakeHttpServer


def _sandbox(tmp_path: Path, command_body: str) -> CliSandbox:
    scripts_dir = tmp_path / "bin"
    scripts_dir.mkdir()
    command = scripts_dir / "example"
    command.write_text(f"#!/bin/sh\n{command_body.rstrip()}\n")
    command.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    return CliSandbox(home=home, scripts_dir=scripts_dir)


def test_fake_path_is_added_to_the_cli_environment(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path, "helper")
    fake_path = sandbox.fake_path()
    fake_path.executable("helper", "printf '%s\\n' fake-helper")

    result = sandbox.run("example")

    assert result.returncode == 0
    assert result.stdout == "fake-helper\n"


def test_cli_execution_has_an_overridable_timeout(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path, "sleep 1")

    with pytest.raises(subprocess.TimeoutExpired):
        sandbox.run("example", timeout=0.01)


def test_fake_http_server_rejects_unsupported_methods() -> None:
    fake = FakeHttpServer()
    try:
        with pytest.raises(ValueError, match="unsupported HTTP method"):
            fake.route("/resource", "ok", method="PUT")
    finally:
        fake.close()
