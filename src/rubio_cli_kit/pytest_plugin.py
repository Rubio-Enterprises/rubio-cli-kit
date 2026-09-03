"""Pytest plugin that auto-collects the Rubio CLI contract in consumer repos."""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from rubio_cli_kit._contract_driver import ContractDriver
from rubio_cli_kit._contract_project import ContractProject
from rubio_cli_kit.contracts import CommandContract
from rubio_cli_kit.testing import CliSandbox, FakeHttpServer, FakePath

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """Give each CLI test an empty throwaway HOME."""
    path = tmp_path / 'home'
    path.mkdir()
    return path


@pytest.fixture
def cli_env(home: Path) -> Iterator[CliSandbox]:
    """Return a subprocess sandbox with package scripts on PATH."""
    sandbox = CliSandbox(home=home, scripts_dir=Path(sys.executable).parent)
    try:
        yield sandbox
    finally:
        sandbox.close()


@pytest.fixture
def cli(cli_env: CliSandbox) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Run a console script against the test's hermetic HOME and XDG roots."""
    return cli_env.run


@pytest.fixture
def fake_path(cli_env: CliSandbox) -> FakePath:
    """Create fake external binaries under a PATH-prepend directory."""
    return cli_env.fake_path()


@pytest.fixture
def fake_http_server() -> Iterator[FakeHttpServer]:
    """Start a local HTTP fake and tear it down after the test."""
    server = FakeHttpServer()
    try:
        yield server
    finally:
        server.close()


def _function(
    parent: pytest.Collector,
    *,
    name: str,
    call: Callable[..., None],
) -> pytest.Function:
    call.__name__ = name.replace(':', '_').replace('-', '_')
    return pytest.Function.from_parent(parent, name=name, callobj=call)


def _failure(error: BaseException) -> Callable[[], None]:
    def fail() -> None:
        raise error

    return fail


def _platform_check(contract: CommandContract, call: Callable[[CliSandbox], None]) -> Callable:
    def check(cli_env: CliSandbox) -> None:
        if contract.darwin_only and sys.platform != 'darwin':
            pytest.skip(f'{contract.name} is darwin-only')
        call(cli_env)

    return check


class ContractFile(pytest.File):
    """Synthetic collector anchored to the consumer's root pyproject.toml."""

    def collect(self) -> Iterator[pytest.Item]:
        project = ContractProject.from_root(self.path.parent)
        if project.is_kit:

            def no_catalog() -> None:
                project.assert_kit_has_no_catalog()

            yield _function(self, name='contract:kit:no-catalog', call=no_catalog)
            return
        if not project.is_consumer:
            return

        def typer_declared() -> None:
            project.assert_typer_declared()

        yield _function(self, name='contract:manifest:typer-declared', call=typer_declared)

        try:
            catalog = project.load_catalog()
            contracts = project.load_contracts()
        # Consumer modules can fail arbitrarily; report that as a contract test.
        except (Exception, SystemExit) as error:
            yield _function(
                self,
                name='contract:configuration:valid',
                call=_failure(error),
            )
            return

        def catalog_valid() -> None:
            project.load_catalog()

        yield _function(self, name='contract:catalog:valid', call=catalog_valid)

        def coverage() -> None:
            contract_names = {contract.name for contract in contracts}
            project.assert_command_coverage(contract_names=contract_names)

        yield _function(self, name='contract:commands:covered', call=coverage)

        for command in catalog.commands:
            if command.hook:

                def hook_stdlib_only(command_name: str = command.name) -> None:
                    project.assert_hook_stdlib_only(command_name)

                yield _function(
                    self,
                    name=f'contract:{command.name}:stdlib-only',
                    call=hook_stdlib_only,
                )
                continue

            def command_import_ownership(command_name: str = command.name) -> None:
                project.assert_command_import_ownership(command_name)

            yield _function(
                self,
                name=f'contract:{command.name}:import-ownership',
                call=command_import_ownership,
            )

        checks = (
            ('root-options', ContractDriver.assert_root_options),
            ('help-paths', ContractDriver.assert_help_paths),
            ('bare-invocation', ContractDriver.assert_bare_invocation),
            ('json-wire', ContractDriver.assert_json_wire),
            ('usage-error', ContractDriver.assert_usage_error),
            ('runtime-error', ContractDriver.assert_runtime_error),
        )
        for contract in contracts:
            for suffix, assertion in checks:

                def run_check(
                    sandbox: CliSandbox,
                    *,
                    row: CommandContract = contract,
                    check: Callable[
                        [ContractDriver, CommandContract, CliSandbox], None
                    ] = assertion,
                ) -> None:
                    driver = ContractDriver(
                        expected_version=importlib.metadata.version(project.manifest.name)
                    )
                    check(driver, row, sandbox)

                yield _function(
                    self,
                    name=f'contract:{contract.name}:{suffix}',
                    call=_platform_check(contract, run_check),
                )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(
    session: pytest.Session,
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Append the synthetic contract independently of pytest's configured test paths."""
    manifest = Path(config.rootpath) / 'pyproject.toml'
    if not manifest.is_file():
        return
    collector = ContractFile.from_parent(session, path=manifest)
    try:
        if not ContractProject.participates(manifest.parent):
            return
        collected = list(collector.collect())
    # Collection failures must become visible test failures, not INTERNALERRORs.
    except (Exception, SystemExit) as error:
        items.append(
            _function(
                collector,
                name='contract:configuration:valid',
                call=_failure(error),
            )
        )
        return
    items.extend(collected)
