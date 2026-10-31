# rubio-cli-kit

Shared CLI-contract helpers and pytest11 contract harness for Rubio-Enterprises per-tool CLI repositories

`rubio-cli-kit` provides the four modules used by per-tool CLI packages for application construction,
structured diagnostics, stdout/stderr discipline, and XDG path resolution. It sanctions two complete
CLI shapes: subcommand applications created with `make_app`, and root-argument applications created
with `make_single_command_app`.

Both shapes provide `-h`/`--help`, `--version`, and `--verbose`. The version is resolved from the
package constructing the app, so consumers do not pass or duplicate distribution metadata. Rich and
structlog are implementation dependencies of the kit; consumer command modules import and declare
Typer directly, but do not import Rich or structlog.

## Table of Contents

- [Install](#install)
- [Usage](#usage)
- [Contract harness](#contract-harness)
- [Helper modules](#helper-modules)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

## Install

The kit requires Python 3.14.6 or newer and is distributed from its public Git repository.
Pin a released tag in the consuming package:

```toml
[project]
dependencies = [
  "rubio-cli-kit",
  "typer>=0.27.1",
]

[tool.uv.sources]
rubio-cli-kit = { git = "https://github.com/Rubio-Enterprises/rubio-cli-kit", tag = "v1.2.4" }
```

## Usage

### Subcommand application

```python
from typing import Annotated

import typer

from rubio_cli_kit import _logging
from rubio_cli_kit._cli import make_app

app = make_app(name='example', help_text='Example commands.')


@app.command()
def greet(name: Annotated[str, typer.Argument()]) -> None:
    _logging.get_logger('example').debug('greeting', name=name)
    typer.echo(f'hello {name}')
```

### Single-command application

```python
from typing import Annotated

import typer

from rubio_cli_kit import _logging
from rubio_cli_kit._cli import make_single_command_app

app = make_single_command_app(name='example', help_text='Print a greeting.')


@app.command()
def main(name: Annotated[str, typer.Argument()]) -> None:
    _logging.get_logger('example').debug('greeting', name=name)
    typer.echo(f'hello {name}')
```

The single-command factory adds `--version` and `--verbose` to the root command without forcing the
consumer to repeat those parameters in its callback signature.

## Contract harness

The distribution registers `rubio_cli_kit.pytest_plugin` through the `pytest11` entry-point group.
Pytest therefore loads the contract automatically in any project that declares `rubio-cli-kit`; a
consumer does not add a test driver or `conftest.py`.

A consumer owns two inputs:

1. `tests/contract_table.py`, containing its non-hook command rows and any imperative sandbox setup
   callables.
2. `src/<package>/catalog.toml`, containing one `[[command]]` row for every console script.

```python
# tests/contract_table.py
from rubio_cli_kit.contracts import CommandContract
from rubio_cli_kit.testing import CliSandbox


def _setup(sandbox: CliSandbox) -> None:
    config = sandbox.xdg_config_path('example', 'config.toml')
    config.parent.mkdir(parents=True)
    config.write_text('message = "hello"\n')


COMMANDS = (
    CommandContract(
        name='example',
        help_paths=(('show',),),
        json_args=('show', '--json'),
        usage_error_args=('show', '--unknown'),
        runtime_error_args=('show',),
        setup=_setup,
    ),
)
```

```toml
# src/example/catalog.toml
[[command]]
name = "example"
purpose = "Show the configured example value."
use_when = "Use when the user wants to inspect the example configuration."
```

The generated tests execute the installed console scripts as subprocesses with a temporary HOME,
XDG roots, and hermetic PATH. They enforce external behavior only:

- `-h`, `--help`, `--version`, and `--verbose` at the root of both sanctioned CLI shapes;
- every declared help path;
- usage errors at exit 2 and runtime errors at exit 1, with clean stdout;
- a parseable, chatter-free JSON value when JSON mode is supported;
- exact parity between `[project.scripts]`, catalog rows, and non-hook contract rows;
- a direct `typer` declaration in the consumer manifest;
- direct Typer imports in non-hook command modules, with Rich and structlog kept behind kit helpers.

Catalog rows marked `hook = true` need no `CommandContract` row and may omit `purpose` / `use_when`.
The harness recursively follows their project-local imports and rejects any dependency outside the
Python standard library. This keeps latency-sensitive hook entry points stdlib-only even when their
implementation is split across local modules.

The plugin also exports the `home`, `cli_env`, `cli`, `fake_path`, and `fake_http_server` fixtures for
consumer-specific tests. `CliSandbox`, `FakePath`, and `FakeHttpServer` are public from
`rubio_cli_kit.testing`.

## Helper modules

- `rubio_cli_kit._cli` — Typer factories, exit codes, command-name prefixes, and runtime failures.
- `rubio_cli_kit._logging` — structlog configuration for console or JSON diagnostics on stderr.
- `rubio_cli_kit._output` — plain stdout data helpers and Rich stderr status helpers.
- `rubio_cli_kit._paths` — XDG environment-variable resolution with HOME-relative fallbacks.

## Development

Use mise 2026.10.19 or newer, with `NODE_AUTH_TOKEN` set to a token that can read
`@rubio-enterprises/standards` from GitHub Packages (`export NODE_AUTH_TOKEN="$(gh auth token)"`).

```bash
git clone git@github.com:Rubio-Enterprises/rubio-cli-kit.git
cd rubio-cli-kit
mise trust
mise run setup
mise run check
mise run test
```

`mise run setup` installs the latest `@rubio-enterprises/standards` release into the gitignored
`.standards/`; tool configs and hooks extend it. Repository exceptions belong in each tool's own
config (`ruff.toml`, `biome.jsonc`) or in `lefthook.override.yml`.

## Contributing

Repository changes go through pull requests with a Conventional Commits title and the sections in
[organization PR template](https://github.com/Rubio-Enterprises/.github/blob/main/.github/PULL_REQUEST_TEMPLATE.md): What, Why, How, Testing,
Feedback, and known dependencies (screenshots when relevant). Use repository issues for questions
and bug reports.

Run `mise run check` (lockfile, Ruff, Pyright and the other standards Checks) and `mise run test`
(pytest) before submitting.
Commit hooks also format and check staged Markdown.

## License

[MIT](LICENSE) — Copyright (c) 2026 Rubio Enterprises.
