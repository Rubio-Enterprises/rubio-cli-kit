from __future__ import annotations

import json
from pathlib import Path

from rubio_cli_kit._contract_driver import ContractDriver
from rubio_cli_kit.contracts import CommandContract
from rubio_cli_kit.testing import CliSandbox


def _fake_command(scripts_dir: Path) -> None:
    command = scripts_dir / 'example'
    command.write_text(
        """#!/bin/sh
case "$*" in
  "-h"|"--help"|"--verbose --help")
    cat <<'EOF'
Usage: example [OPTIONS] COMMAND

Options:
  -h, --help
  --version
  --verbose
EOF
    ;;
  "--version") printf '%s\\n' '1.2.3' ;;
  "show --help") printf '%s\\n' 'Usage: example show [OPTIONS]' ;;
  "show --json") printf '%s\\n' '{"ok":true}' ;;
  "--bad") printf '%s\\n' 'bad usage' >&2; exit 2 ;;
  "explode") printf '%s\\n' 'runtime failure' >&2; exit 1 ;;
  "") printf '%s\\n' 'Usage: example [OPTIONS] COMMAND'; exit 2 ;;
  *) printf '%s\\n' "unexpected: $*" >&2; exit 64 ;;
esac
"""
    )
    command.chmod(0o755)


def _stateful_default_command(scripts_dir: Path) -> None:
    command = scripts_dir / 'stateful'
    command.write_text(
        """#!/bin/sh
case "$*" in
  ""|"show")
    if [ -e "$HOME/used" ]; then
      printf '%s\n' 'dirty'
    else
      printf '%s\n' 'clean'
    fi
    touch "$HOME/used"
    ;;
  *) exit 64 ;;
esac
"""
    )
    command.chmod(0o755)


def _contract() -> CommandContract:
    return CommandContract(
        name='example',
        help_paths=(('show',),),
        json_args=('show', '--json'),
        usage_error_args=('--bad',),
        runtime_error_args=('explode',),
    )


def test_driver_enforces_external_cli_contract(tmp_path: Path) -> None:
    scripts_dir = tmp_path / 'bin'
    scripts_dir.mkdir()
    _fake_command(scripts_dir)
    home = tmp_path / 'home'
    home.mkdir()
    sandbox = CliSandbox(home=home, scripts_dir=scripts_dir)
    driver = ContractDriver(expected_version='1.2.3')
    contract = _contract()

    driver.assert_root_options(contract, sandbox)
    driver.assert_help_paths(contract, sandbox)
    driver.assert_bare_invocation(contract, sandbox)
    driver.assert_json_wire(contract, sandbox)
    driver.assert_usage_error(contract, sandbox)
    driver.assert_runtime_error(contract, sandbox)


def test_default_invocations_use_identical_initial_state(tmp_path: Path) -> None:
    scripts_dir = tmp_path / 'bin'
    scripts_dir.mkdir()
    _stateful_default_command(scripts_dir)
    home = tmp_path / 'home'
    home.mkdir()
    sandbox = CliSandbox(home=home, scripts_dir=scripts_dir)
    contract = CommandContract(
        name='stateful',
        help_paths=(),
        json_args=None,
        usage_error_args=('--bad',),
        runtime_error_args=('explode',),
        default_command='show',
    )

    ContractDriver(expected_version='1.2.3').assert_bare_invocation(contract, sandbox)


def test_driver_rejects_non_json_stdout(tmp_path: Path) -> None:
    scripts_dir = tmp_path / 'bin'
    scripts_dir.mkdir()
    _fake_command(scripts_dir)
    command = scripts_dir / 'example'
    command.write_text(command.read_text().replace('{"ok":true}', 'not-json'))
    home = tmp_path / 'home'
    home.mkdir()
    sandbox = CliSandbox(home=home, scripts_dir=scripts_dir)

    try:
        ContractDriver(expected_version='1.2.3').assert_json_wire(_contract(), sandbox)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError('non-JSON stdout should fail the wire assertion')
