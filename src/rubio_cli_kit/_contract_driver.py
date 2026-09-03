"""External-behavior assertions used by the pytest contract collector."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from rubio_cli_kit.contracts import CommandContract
from rubio_cli_kit.testing import CliSandbox


class ContractDriver:
    """Drive installed console scripts through the fleet CLI contract."""

    def __init__(self, *, expected_version: str) -> None:
        self.expected_version = expected_version

    def assert_root_options(self, contract: CommandContract, sandbox: CliSandbox) -> None:
        short_help = sandbox.run(contract.name, '-h')
        long_help = sandbox.run(contract.name, '--help')
        verbose_help = sandbox.run(contract.name, '--verbose', '--help')
        for label, result in (
            ('-h', short_help),
            ('--help', long_help),
            ('--verbose --help', verbose_help),
        ):
            assert result.returncode == 0, f'{contract.name} {label} failed: {result.stderr}'
            assert 'Usage' in result.stdout
            assert result.stderr == ''
        for option in ('-h', '--help', '--version', '--verbose'):
            assert option in long_help.stdout, f'{contract.name} help omits {option}'

        version = sandbox.run(contract.name, '--version')
        assert version.returncode == 0, version.stderr
        assert version.stdout == f'{self.expected_version}\n'
        assert version.stderr == ''

    def assert_help_paths(self, contract: CommandContract, sandbox: CliSandbox) -> None:
        for path in contract.help_paths:
            result = sandbox.run(contract.name, *path, '--help')
            assert result.returncode == 0, f'--help failed at path {path}: {result.stderr}'
            assert 'Usage' in result.stdout
            assert result.stderr == ''

    def assert_bare_invocation(self, contract: CommandContract, sandbox: CliSandbox) -> None:
        if contract.default_command is not None:
            contract.setup(sandbox)
            with tempfile.TemporaryDirectory(dir=sandbox.home.parent) as temporary:
                baseline = Path(temporary) / 'home'
                shutil.copytree(sandbox.home, baseline)
                bare = sandbox.run(contract.name)
                if sandbox.home.exists():
                    shutil.rmtree(sandbox.home)
                shutil.copytree(baseline, sandbox.home)
                explicit = sandbox.run(contract.name, contract.default_command)
            assert bare.returncode == explicit.returncode
            assert bare.stdout == explicit.stdout
            assert bare.stderr == explicit.stderr
            return

        result = sandbox.run(contract.name)
        assert result.returncode == 2
        assert 'Usage' in (result.stdout + result.stderr)

    def assert_json_wire(self, contract: CommandContract, sandbox: CliSandbox) -> None:
        if contract.json_args is None:
            result = sandbox.run(contract.name, '--json')
            assert result.returncode == 2
            assert result.stdout == ''
            assert result.stderr != ''
            return

        contract.setup(sandbox)
        result = sandbox.run(contract.name, *contract.json_args)
        assert result.returncode == 0, result.stderr
        json.loads(result.stdout)
        assert result.stderr == ''

    def assert_usage_error(self, contract: CommandContract, sandbox: CliSandbox) -> None:
        result = sandbox.run(contract.name, *contract.usage_error_args)
        assert result.returncode == 2
        assert result.stdout == ''
        assert result.stderr != ''

    def assert_runtime_error(self, contract: CommandContract, sandbox: CliSandbox) -> None:
        if contract.runtime_error_setup is not None:
            contract.runtime_error_setup(sandbox)
        result = sandbox.run(contract.name, *contract.runtime_error_args)
        assert result.returncode == 1
        assert result.stdout == ''
        assert result.stderr != ''
