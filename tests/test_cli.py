from __future__ import annotations

import importlib.metadata
import inspect
from collections.abc import Callable
from typing import Annotated, cast

import pytest
import typer
from rich.text import Text
from typer.testing import CliRunner

from rubio_cli_kit import _logging
from rubio_cli_kit._cli import make_app, make_single_command_app

runner = CliRunner()


def _make_app_from_package(
    factory: Callable[..., typer.Typer],
    *,
    package: str = "rubio_cli_kit.examples",
) -> typer.Typer:
    namespace = {"__package__": package, "factory": factory}
    exec(
        'app = factory(name="example", help_text="Example command.")',
        namespace,
    )
    return cast("typer.Typer", namespace["app"])


def _patch_version(
    monkeypatch: pytest.MonkeyPatch,
    *,
    expected_distribution: str,
    version: str = "1.2.3",
) -> None:
    def fake_version(distribution_name: str) -> str:
        assert distribution_name == expected_distribution
        return version

    monkeypatch.setattr(importlib.metadata, "version", fake_version)


def test_subcommand_shape_has_complete_root_options_and_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_version(monkeypatch, expected_distribution="rubio_cli_kit")
    app = _make_app_from_package(make_app)

    @app.command()
    def greet(name: Annotated[str, typer.Argument()]) -> None:
        _logging.get_logger("example").debug("greeting", name=name)
        typer.echo(f"hello {name}")

    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    help_text = Text.from_ansi(help_result.stdout).plain
    for option in ("-h", "--help", "--version", "--verbose"):
        assert option in help_text

    version_result = runner.invoke(app, ["--version"])
    assert version_result.exit_code == 0
    assert version_result.stdout == "1.2.3\n"
    assert version_result.stderr == ""

    verbose_result = runner.invoke(app, ["--verbose", "greet", "Ada"])
    assert verbose_result.exit_code == 0
    assert verbose_result.stdout == "hello Ada\n"
    assert "greeting" in verbose_result.stderr
    assert "Ada" in verbose_result.stderr


def test_single_command_shape_has_complete_root_options_and_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_version(monkeypatch, expected_distribution="rubio_cli_kit")
    app = _make_app_from_package(make_single_command_app)

    @app.command()
    def main(name: Annotated[str, typer.Argument()]) -> None:
        _logging.get_logger("example").debug("greeting", name=name)
        typer.echo(f"hello {name}")

    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    help_text = Text.from_ansi(help_result.stdout).plain
    for option in ("-h", "--help", "--version", "--verbose"):
        assert option in help_text

    version_result = runner.invoke(app, ["--version"])
    assert version_result.exit_code == 0
    assert version_result.stdout == "1.2.3\n"
    assert version_result.stderr == ""

    verbose_result = runner.invoke(app, ["--verbose", "Ada"])
    assert verbose_result.exit_code == 0
    assert verbose_result.stdout == "hello Ada\n"
    assert "greeting" in verbose_result.stderr
    assert "Ada" in verbose_result.stderr


@pytest.mark.parametrize(
    "factory",
    [make_app, make_single_command_app],
    ids=["subcommand", "single-command"],
)
def test_distribution_name_comes_from_importing_package(
    monkeypatch: pytest.MonkeyPatch,
    factory: Callable[..., typer.Typer],
) -> None:
    _patch_version(monkeypatch, expected_distribution="example_tool")
    app = _make_app_from_package(factory, package="example_tool.commands")

    if factory is make_single_command_app:

        @app.command()
        def main() -> None:
            raise AssertionError("--version must exit before the command runs")

    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout == "1.2.3\n"
    assert result.stderr == ""


def test_factories_do_not_accept_distribution_metadata() -> None:
    for factory in (make_app, make_single_command_app):
        assert "dist_name" not in inspect.signature(factory).parameters
