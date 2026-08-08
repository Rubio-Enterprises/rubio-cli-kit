from __future__ import annotations

import os
import signal
import subprocess
import time
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


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_fake_path_is_added_to_the_cli_environment(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path, "helper")
    fake_path = sandbox.fake_path()
    fake_path.executable("helper", "printf '%s\\n' fake-helper")

    result = sandbox.run("example")

    assert result.returncode == 0
    assert result.stdout == "fake-helper\n"


def test_recording_executable_preserves_argument_boundaries(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path, "helper 'a b' c")
    argv_log = tmp_path / "argv.bin"
    sandbox.fake_path().recording_executable("helper", argv_log)

    first = sandbox.run("example")
    (sandbox.scripts_dir / "example").write_text("#!/bin/sh\nhelper a 'b c'\n")
    second = sandbox.run("example")

    assert first.returncode == 0
    assert second.returncode == 0
    assert argv_log.read_bytes() == b"2\x00a b\x00c\x002\x00a\x00b c\x00"


def test_cli_execution_runs_from_the_throwaway_home(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path, "pwd\ntouch relative-output")

    result = sandbox.run("example")

    assert result.returncode == 0
    assert result.stdout == f"{sandbox.home}\n"
    assert (sandbox.home / "relative-output").is_file()


def test_cli_execution_has_an_overridable_timeout(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path, "sleep 1")

    with pytest.raises(subprocess.TimeoutExpired):
        sandbox.run("example", timeout=0.01)


def test_cli_timeout_terminates_spawned_child_processes(tmp_path: Path) -> None:
    sandbox = _sandbox(
        tmp_path,
        'sleep 30 &\necho "$!" > child.pid\nwait',
    )

    with pytest.raises(subprocess.TimeoutExpired):
        sandbox.run("example", timeout=0.5)

    child_pid = int((sandbox.home / "child.pid").read_text())
    deadline = time.monotonic() + 1
    while _process_exists(child_pid) and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        assert not _process_exists(child_pid)
    finally:
        if _process_exists(child_pid):
            os.kill(child_pid, signal.SIGKILL)


def test_fake_http_server_rejects_unsupported_methods() -> None:
    fake = FakeHttpServer()
    try:
        with pytest.raises(ValueError, match="unsupported HTTP method"):
            fake.route("/resource", "ok", method="PUT")
    finally:
        fake.close()
