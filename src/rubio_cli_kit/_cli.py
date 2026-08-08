"""Construct Typer applications with the shared CLI contract.

Both sanctioned shapes expose ``-h``/``--help``, ``--version``, and
``--verbose``. The distribution reported by ``--version`` is derived from the
package that constructs the app, so consumers never duplicate package metadata.
"""

from __future__ import annotations

import importlib.metadata
import inspect
from collections.abc import Callable
from contextvars import ContextVar
from enum import IntEnum
from typing import Any, NoReturn, cast

import typer
from typer.core import TyperCommand, TyperOption

from rubio_cli_kit import _logging, _output


class ExitCode(IntEnum):
    """The CLI contract: success 0, runtime error 1, usage error 2."""

    OK = 0
    RUNTIME = 1
    USAGE = 2


_PROG = ContextVar("rubio_cli_kit_prog", default="command")
_DIST = ContextVar("rubio_cli_kit_dist", default="rubio-cli-kit")


def prog_name() -> str:
    """Return the console-script name used for error prefixes."""
    return _PROG.get()


def fail(message: str, *, code: ExitCode = ExitCode.RUNTIME) -> NoReturn:
    """Write a runtime or domain error to stderr and exit."""
    _output.error(f"{prog_name()}: {message}")
    raise typer.Exit(code)


def _importing_distribution_name() -> str:
    frame = inspect.currentframe()
    try:
        caller = frame.f_back.f_back if frame is not None and frame.f_back is not None else None
        package = caller.f_globals.get("__package__") if caller is not None else None
    finally:
        del frame
    if not isinstance(package, str) or not package:
        raise RuntimeError("CLI apps must be constructed from an importable package")
    return package.partition(".")[0]


def _bind_app_identity(*, name: str, distribution: str) -> None:
    _PROG.set(name)
    _DIST.set(distribution)


def _print_version(requested: bool, *, distribution: str | None = None) -> None:
    if requested:
        _output.emit_text(importlib.metadata.version(distribution or _DIST.get()))
        raise typer.Exit(ExitCode.OK)


def print_version(requested: bool) -> None:
    """Print the current distribution's version for an eager Typer option."""
    _print_version(requested)


def make_app(
    *,
    name: str,
    help_text: str,
    default_command: str | None = None,
) -> typer.Typer:
    """Build a subcommand application with the complete shared root shape."""
    distribution = _importing_distribution_name()
    app = typer.Typer(
        name=name,
        help=help_text,
        no_args_is_help=default_command is None,
        add_completion=False,
        context_settings={"help_option_names": ["-h", "--help"]},
        pretty_exceptions_enable=False,
    )

    def print_app_version(requested: bool) -> None:
        _bind_app_identity(name=name, distribution=distribution)
        _print_version(requested, distribution=distribution)

    @app.callback(invoke_without_command=default_command is not None)
    def _root(
        ctx: typer.Context,
        version: bool = typer.Option(
            False,
            "--version",
            help="Print the package version and exit.",
            callback=print_app_version,
            is_eager=True,
        ),
        verbose: bool = typer.Option(
            False,
            "--verbose",
            help="Enable DEBUG diagnostics on stderr.",
        ),
    ) -> None:
        del version
        _bind_app_identity(name=name, distribution=distribution)
        _logging.configure(verbose=verbose)
        if default_command is None or ctx.invoked_subcommand is not None:
            return
        lookup = getattr(ctx.command, "get_command", None)
        command = lookup(ctx, default_command) if lookup is not None else None
        if command is None:
            raise RuntimeError(f"default command is not registered: {default_command}")
        make_context = getattr(command, "make_context", None)
        invoke = getattr(command, "invoke", None)
        if not callable(make_context) or not callable(invoke):
            raise RuntimeError(f"default command cannot be invoked: {default_command}")
        subcontext = cast("typer.Context", make_context(default_command, [], parent=ctx))
        with subcontext:
            invoke(subcontext)

    return app


def _single_command_type(*, name: str, distribution: str) -> type[TyperCommand]:
    def version_callback(
        ctx: typer.Context,
        _param: Any,
        requested: bool,
    ) -> None:
        if requested and not ctx.resilient_parsing:
            _bind_app_identity(name=name, distribution=distribution)
            _output.emit_text(importlib.metadata.version(distribution))
            ctx.exit(ExitCode.OK)

    def verbose_callback(
        ctx: typer.Context,
        _param: Any,
        verbose: bool,
    ) -> None:
        if not ctx.resilient_parsing:
            _bind_app_identity(name=name, distribution=distribution)
            _logging.configure(verbose=verbose)

    class SingleCommand(TyperCommand):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.params.extend(
                [
                    TyperOption(
                        param_decls=["--version"],
                        is_flag=True,
                        is_eager=True,
                        expose_value=False,
                        callback=version_callback,
                        help="Print the package version and exit.",
                    ),
                    TyperOption(
                        param_decls=["--verbose"],
                        is_flag=True,
                        expose_value=False,
                        callback=verbose_callback,
                        help="Enable DEBUG diagnostics on stderr.",
                    ),
                ]
            )

        def parse_args(  # type: ignore[override]
            self,
            ctx: typer.Context,
            args: list[str],
        ) -> list[str]:
            if not ctx.resilient_parsing:
                _bind_app_identity(name=name, distribution=distribution)
                _logging.configure(verbose="--verbose" in args)
            return super().parse_args(ctx, args)

    return SingleCommand


CommandFunction = Callable[..., Any]


class _SingleCommandTyper(typer.Typer):
    def __init__(
        self,
        *,
        command_type: type[TyperCommand],
        help_text: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._command_type = command_type
        self._help_text = help_text

    def command(  # type: ignore[override]
        self,
        name: str | None = None,
        **kwargs: Any,
    ) -> Callable[[CommandFunction], CommandFunction]:
        if "cls" in kwargs:
            raise TypeError("single-command apps do not support custom command classes")
        kwargs["cls"] = self._command_type
        kwargs.setdefault("help", self._help_text)
        return super().command(name, **kwargs)


def make_single_command_app(*, name: str, help_text: str) -> typer.Typer:
    """Build a root-argument command with the complete shared root shape."""
    distribution = _importing_distribution_name()
    return _SingleCommandTyper(
        command_type=_single_command_type(name=name, distribution=distribution),
        help_text=help_text,
        name=name,
        help=help_text,
        no_args_is_help=True,
        add_completion=False,
        context_settings={"help_option_names": ["-h", "--help"]},
        pretty_exceptions_enable=False,
    )
