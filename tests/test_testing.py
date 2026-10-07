from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from rubio_cli_kit.testing import CliSandbox, FakeHttpServer


def _sandbox(tmp_path: Path, command_body: str) -> CliSandbox:
    scripts_dir = tmp_path / 'bin'
    scripts_dir.mkdir()
    command = scripts_dir / 'example'
    command.write_text(f'#!/bin/sh\n{command_body.rstrip()}\n')
    command.chmod(0o755)
    home = tmp_path / 'home'
    home.mkdir()
    return CliSandbox(home=home, scripts_dir=scripts_dir)


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_fake_path_is_added_to_the_cli_environment(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path, 'helper')
    fake_path = sandbox.fake_path()
    fake_path.executable('helper', "printf '%s\\n' fake-helper")

    result = sandbox.run('example')

    assert result.returncode == 0
    assert result.stdout == 'fake-helper\n'


def test_recording_executable_preserves_argument_boundaries(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path, "helper 'a b' c")
    argv_log = tmp_path / 'argv.bin'
    sandbox.fake_path().recording_executable('helper', argv_log)

    first = sandbox.run('example')
    (sandbox.scripts_dir / 'example').write_text("#!/bin/sh\nhelper a 'b c'\n")
    second = sandbox.run('example')

    assert first.returncode == 0
    assert second.returncode == 0
    assert argv_log.read_bytes() == b'2\x00a b\x00c\x002\x00a\x00b c\x00'


def test_cli_execution_runs_from_the_throwaway_home(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path, 'pwd\ntouch relative-output')

    result = sandbox.run('example')

    assert result.returncode == 0
    assert result.stdout == f'{sandbox.home}\n'
    assert (sandbox.home / 'relative-output').is_file()


def test_cli_execution_has_an_overridable_timeout(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path, 'sleep 1')

    with pytest.raises(subprocess.TimeoutExpired):
        sandbox.run('example', timeout=0.01)


def test_cli_timeout_terminates_spawned_child_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = _sandbox(
        tmp_path,
        'sleep 30 &\nprintf "child-ready=%s\\n" "$!"\nwait',
    )
    communicate = subprocess.Popen.communicate
    child_pid: int | None = None
    observed_timeouts: list[float | None] = []

    def communicate_after_child_ready(
        process: subprocess.Popen[str],
        input: str | None = None,
        timeout: float | None = None,
    ) -> tuple[str, str]:
        nonlocal child_pid
        if child_pid is None:
            # The timeout tests process-group cleanup, not how quickly macOS
            # starts a freshly written shell script under parallel load. Wait
            # for the real child to exist before starting the SAME 0.5s budget.
            assert process.stdout is not None
            ready = process.stdout.readline().strip()
            assert ready.startswith('child-ready='), f'child did not report readiness: {ready!r}'
            child_pid = int(ready.removeprefix('child-ready='))
        # Keep the real communicate implementation and the sandbox's real
        # TimeoutExpired/killpg path, including its second post-kill drain.
        observed_timeouts.append(timeout)
        return communicate(process, input=input, timeout=timeout)

    monkeypatch.setattr(subprocess.Popen, 'communicate', communicate_after_child_ready)
    with pytest.raises(subprocess.TimeoutExpired):
        sandbox.run('example', timeout=0.5)

    assert child_pid is not None
    assert observed_timeouts == [0.5, None]
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
        with pytest.raises(ValueError, match='unsupported HTTP method'):
            fake.route('/resource', 'ok', method='PUT')
    finally:
        fake.close()
