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


_PROG = ContextVar('rubio_cli_kit_prog', default='command')


def prog_name() -> str:
    """Return the console-script name used for error prefixes."""
    return _PROG.get()


def fail(message: str, *, code: ExitCode = ExitCode.RUNTIME) -> NoReturn:
    """Write a runtime or domain error to stderr and exit."""
    _output.error(f'{prog_name()}: {message}')
    raise typer.Exit(code)


def _importing_distribution_name() -> str:
    frame = inspect.currentframe()
    try:
        caller = frame.f_back.f_back if frame is not None and frame.f_back is not None else None
        package = caller.f_globals.get('__package__') if caller is not None else None
    finally:
        del frame
    if not isinstance(package, str) or not package:
        raise RuntimeError('CLI apps must be constructed from an importable package')
    top_level_package = package.partition('.')[0]
    distributions = importlib.metadata.packages_distributions().get(top_level_package)
    if not distributions:
        return top_level_package
    if len(distributions) > 1:
        candidates = ', '.join(sorted(distributions))
        raise RuntimeError(
            f'import package {top_level_package!r} is provided by multiple distributions: '
            f'{candidates}'
        )
    return distributions[0]


def _set_app_identity(*, name: str) -> Callable[[], None]:
    prog_token = _PROG.set(name)

    def reset() -> None:
        _PROG.reset(prog_token)

    return reset


def _bind_app_identity(ctx: typer.Context, *, name: str) -> None:
    ctx.call_on_close(_set_app_identity(name=name))


def _bind_logging(ctx: typer.Context, *, verbose: bool) -> None:
    previous = _logging.configure(verbose=verbose)
    ctx.call_on_close(
        lambda: _logging.configure(
            verbose=previous.verbose,
            json_output=previous.json_output,
        )
    )


def _print_version(requested: bool, *, distribution: str) -> None:
    if requested:
        _output.emit_text(importlib.metadata.version(distribution))
        raise typer.Exit(ExitCode.OK)


class _SubcommandTyper(typer.Typer):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._callback_registered = False

    def callback(  # type: ignore[override]
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Callable[..., Any]:
        if self._callback_registered:
            raise TypeError('subcommand apps do not support additional callbacks')
        self._callback_registered = True
        return super().callback(*args, **kwargs)


def make_app(
    *,
    name: str,
    help_text: str,
    default_command: str | None = None,
) -> typer.Typer:
    """Build a subcommand application with the complete shared root shape."""
    distribution = _importing_distribution_name()
    app = _SubcommandTyper(
        name=name,
        help=help_text,
        no_args_is_help=default_command is None,
        add_completion=False,
        context_settings={'help_option_names': ['-h', '--help']},
        pretty_exceptions_enable=False,
    )

    def print_app_version(ctx: typer.Context, requested: bool) -> None:
        if ctx.resilient_parsing:
            return
        _print_version(requested, distribution=distribution)

    @app.callback(invoke_without_command=default_command is not None)
    def _root(
        ctx: typer.Context,
        version: bool = typer.Option(
            False,
            '--version',
            help='Print the package version and exit.',
            callback=print_app_version,
            is_eager=True,
        ),
        verbose: bool = typer.Option(
            False,
            '--verbose',
            help='Enable DEBUG diagnostics on stderr.',
        ),
    ) -> None:
        del version
        _bind_app_identity(ctx, name=name)
        _bind_logging(ctx, verbose=verbose)
        if default_command is None or ctx.invoked_subcommand is not None:
            return
        lookup = getattr(ctx.command, 'get_command', None)
        command = lookup(ctx, default_command) if lookup is not None else None
        if command is None:
            raise RuntimeError(f'default command is not registered: {default_command}')
        make_context = getattr(command, 'make_context', None)
        invoke = getattr(command, 'invoke', None)
        if not callable(make_context) or not callable(invoke):
            raise RuntimeError(f'default command cannot be invoked: {default_command}')
        subcontext = cast('typer.Context', make_context(default_command, [], parent=ctx))
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
            _output.emit_text(importlib.metadata.version(distribution))
            ctx.exit(ExitCode.OK)

    def verbose_callback(
        ctx: typer.Context,
        _param: Any,
        verbose: bool,
    ) -> None:
        if not ctx.resilient_parsing:
            _logging.configure(verbose=verbose)

    class SingleCommand(TyperCommand):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            reserved_options = {'--verbose', '--version'}
            declared_options = {
                option for param in self.params for option in getattr(param, 'opts', ())
            }
            collisions = sorted(reserved_options & declared_options)
            if collisions:
                raise TypeError(
                    'single-command apps have reserved root options: ' + ', '.join(collisions)
                )
            self.params.extend(
                [
                    TyperOption(
                        param_decls=['--version'],
                        is_flag=True,
                        is_eager=True,
                        expose_value=False,
                        callback=version_callback,
                        help='Print the package version and exit.',
                    ),
                    TyperOption(
                        param_decls=['--verbose'],
                        is_flag=True,
                        is_eager=True,
                        expose_value=False,
                        callback=verbose_callback,
                        help='Enable DEBUG diagnostics on stderr.',
                    ),
                ]
            )

        def parse_args(  # type: ignore[override]
            self,
            ctx: typer.Context,
            args: list[str],
        ) -> list[str]:
            if ctx.resilient_parsing:
                return super().parse_args(ctx, args)

            reset_identity = _set_app_identity(name=name)
            previous_logging = _logging.configure(verbose=False)
            try:
                remaining = super().parse_args(ctx, args)
            except Exception:
                reset_identity()
                _logging.configure(
                    verbose=previous_logging.verbose,
                    json_output=previous_logging.json_output,
                )
                raise

            ctx.call_on_close(reset_identity)
            ctx.call_on_close(
                lambda: _logging.configure(
                    verbose=previous_logging.verbose,
                    json_output=previous_logging.json_output,
                )
            )
            return remaining

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
        self._command_registered = False

    def callback(  # type: ignore[override]
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Callable[..., Any]:
        del args, kwargs
        raise TypeError('single-command apps do not support callbacks')

    def command(  # type: ignore[override]
        self,
        name: str | None = None,
        **kwargs: Any,
    ) -> Callable[[CommandFunction], CommandFunction]:
        if self._command_registered:
            raise TypeError('single-command apps require exactly one command')
        if 'cls' in kwargs:
            raise TypeError('single-command apps do not support custom command classes')
        kwargs['cls'] = self._command_type
        kwargs.setdefault('help', self._help_text)
        decorator = super().command(name, **kwargs)

        def register(function: CommandFunction) -> CommandFunction:
            result = decorator(function)
            self._command_registered = True
            return result

        return register


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
        context_settings={'help_option_names': ['-h', '--help']},
        pretty_exceptions_enable=False,
    )
