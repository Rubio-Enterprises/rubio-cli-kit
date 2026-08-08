from __future__ import annotations

import importlib.metadata
import inspect
from collections.abc import Callable
from typing import Annotated, NoReturn, cast

import pytest
import typer
from rich.text import Text
from typer.core import TyperCommand
from typer.main import get_command
from typer.testing import CliRunner

from rubio_cli_kit import _logging
from rubio_cli_kit._cli import fail, make_app, make_single_command_app

runner = CliRunner()


def _uppercase(value: str) -> str:
    return value.upper()


def _debug_from_callback(value: str) -> str:
    _logging.get_logger("example").debug("parameter callback", value=value)
    return value


def _fail_from_callback(value: str) -> NoReturn:
    fail(f"callback failed for {value}")


def _make_app_from_package(
    factory: Callable[..., typer.Typer],
    *,
    package: str = "rubio_cli_kit.examples",
    name: str = "example",
    **factory_kwargs: object,
) -> typer.Typer:
    namespace = {
        "__package__": package,
        "factory": factory,
        "factory_kwargs": factory_kwargs,
        "name": name,
    }
    exec(
        'app = factory(name=name, help_text="Example command.", **factory_kwargs)',
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
    assert "Example command." in help_text
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
    assert "Example command." in help_text
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


@pytest.mark.parametrize(
    "factory",
    [make_app, make_single_command_app],
    ids=["subcommand", "single-command"],
)
def test_apps_keep_their_own_distribution_metadata(
    monkeypatch: pytest.MonkeyPatch,
    factory: Callable[..., typer.Typer],
) -> None:
    versions = {"first_tool": "1.0.0", "second_tool": "2.0.0"}
    monkeypatch.setattr(importlib.metadata, "version", versions.__getitem__)
    first = _make_app_from_package(factory, package="first_tool.commands")
    second = _make_app_from_package(factory, package="second_tool.commands")

    @first.command()
    def first_command() -> None:
        pass

    @second.command()
    def second_command() -> None:
        pass

    result = runner.invoke(first, ["--version"])

    assert result.exit_code == 0
    assert result.stdout == "1.0.0\n"


def test_fail_prefix_uses_the_invoked_app_name() -> None:
    first = _make_app_from_package(make_app, name="first")

    @first.command()
    def broken() -> None:
        fail("broken")

    _make_app_from_package(make_app, name="second")

    result = runner.invoke(first, ["broken"])

    assert result.exit_code == 1
    assert Text.from_ansi(result.stderr).plain == "first: broken\n"


def test_default_command_runs_option_callbacks() -> None:
    app = _make_app_from_package(make_app, default_command="status")

    @app.command()
    def status(
        mode: Annotated[str, typer.Option("--mode", callback=_uppercase)] = "human",
    ) -> None:
        typer.echo(mode)

    result = runner.invoke(app, [])

    assert result.exit_code == 0, (result.stdout, result.stderr, result.exception)
    assert result.stdout == "HUMAN\n"


def test_single_command_binds_identity_before_parameter_callbacks() -> None:
    first = _make_app_from_package(make_single_command_app, name="first")

    @first.command()
    def first_command(
        value: Annotated[str, typer.Option("--value", callback=_fail_from_callback)],
    ) -> None:
        typer.echo(value)

    second = _make_app_from_package(make_single_command_app, name="second")

    @second.command()
    def second_command(value: Annotated[str, typer.Argument()]) -> None:
        typer.echo(value)

    assert runner.invoke(second, ["ready"]).exit_code == 0

    result = runner.invoke(first, ["--value", "broken"])

    assert result.exit_code == 1
    assert Text.from_ansi(result.stderr).plain == "first: callback failed for broken\n"


def test_single_command_configures_verbose_before_parameter_callbacks() -> None:
    _logging.configure(verbose=False)
    app = _make_app_from_package(make_single_command_app)

    @app.command()
    def main(
        value: Annotated[str, typer.Option("--value", callback=_debug_from_callback)],
    ) -> None:
        typer.echo(value)

    result = runner.invoke(app, ["--value", "ready", "--verbose"])

    assert result.exit_code == 0
    assert "parameter callback" in Text.from_ansi(result.stderr).plain


def test_single_command_rejects_custom_command_classes() -> None:
    app = _make_app_from_package(make_single_command_app)

    with pytest.raises(TypeError, match="custom command classes"):

        @app.command(cls=TyperCommand)
        def main() -> None:
            pass


def test_single_command_rejects_a_second_registration() -> None:
    app = _make_app_from_package(make_single_command_app)

    @app.command()
    def first() -> None:
        pass

    with pytest.raises(TypeError, match="exactly one command"):

        @app.command()
        def second() -> None:
            pass


def test_single_command_honors_the_option_terminator() -> None:
    _logging.configure(verbose=False)
    app = _make_app_from_package(make_single_command_app)

    @app.command()
    def main(
        value: Annotated[str, typer.Argument(callback=_debug_from_callback)],
    ) -> None:
        typer.echo(value)

    result = runner.invoke(app, ["--", "--verbose"])

    assert result.exit_code == 0
    assert result.stdout == "--verbose\n"
    assert "parameter callback" not in Text.from_ansi(result.stderr).plain


@pytest.mark.parametrize(
    "factory",
    [make_app, make_single_command_app],
    ids=["subcommand", "single-command"],
)
def test_distribution_name_uses_installed_package_mapping(
    monkeypatch: pytest.MonkeyPatch,
    factory: Callable[..., typer.Typer],
) -> None:
    monkeypatch.setattr(
        importlib.metadata,
        "packages_distributions",
        lambda: {"acme": ["acme-cli"]},
    )
    _patch_version(monkeypatch, expected_distribution="acme-cli")
    app = _make_app_from_package(factory, package="acme.commands")

    @app.command()
    def main() -> None:
        pass

    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0


def test_subcommand_app_rejects_additional_callbacks() -> None:
    app = _make_app_from_package(make_app)

    with pytest.raises(TypeError, match="additional callbacks"):

        @app.callback()
        def custom_callback() -> None:
            pass


def test_subcommand_version_respects_resilient_parsing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unexpected_version_lookup(_distribution: str) -> str:
        raise AssertionError("resilient parsing must not resolve the version")

    monkeypatch.setattr(importlib.metadata, "version", unexpected_version_lookup)
    app = _make_app_from_package(make_app)
    command = get_command(app)

    with command.make_context(
        "example",
        ["--version"],
        resilient_parsing=True,
    ):
        pass

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_single_command_rejects_callbacks() -> None:
    app = _make_app_from_package(make_single_command_app)

    with pytest.raises(TypeError, match="do not support callbacks"):

        @app.callback()
        def custom_callback() -> None:
            pass


def test_single_command_does_not_treat_an_option_value_as_verbose() -> None:
    _logging.configure(verbose=False)
    app = _make_app_from_package(make_single_command_app)

    @app.command()
    def main(
        message: Annotated[str, typer.Option("--message", callback=_debug_from_callback)],
    ) -> None:
        typer.echo(message)

    result = runner.invoke(app, ["--message", "--verbose"])

    assert result.exit_code == 0
    assert result.stdout == "--verbose\n"
    assert "parameter callback" not in Text.from_ansi(result.stderr).plain


def test_nested_invocation_restores_the_outer_app_identity() -> None:
    inner = _make_app_from_package(make_app, name="inner")

    @inner.command()
    def done() -> None:
        pass

    inner_command = get_command(inner)
    outer = _make_app_from_package(make_app, name="outer")

    @outer.command()
    def run() -> None:
        inner_command.main(args=["done"], prog_name="inner", standalone_mode=False)
        fail("after inner")

    result = runner.invoke(outer, ["run"])

    assert result.exit_code == 1
    assert Text.from_ansi(result.stderr).plain == "outer: after inner\n"
