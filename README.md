# rubio-cli-kit

Shared runtime helpers for the Rubio-Enterprises Typer CLI fleet.

## What it is

`rubio-cli-kit` provides the four modules used by fleet CLI packages for application construction,
structured diagnostics, stdout/stderr discipline, and XDG path resolution. It sanctions two complete
CLI shapes: subcommand applications created with `make_app`, and root-argument applications created
with `make_single_command_app`.

Both shapes provide `-h`/`--help`, `--version`, and `--verbose`. The version is resolved from the
package constructing the app, so consumers do not pass or duplicate distribution metadata. Rich and
structlog are implementation dependencies of the kit; consumer command modules import and declare
Typer directly, but do not import Rich or structlog.

## Install

The kit is distributed from its public Git repository. Pin a released tag in the consuming package:

```toml
[project]
dependencies = [
  "rubio-cli-kit",
  "typer>=0.26.8",
]

[tool.uv.sources]
rubio-cli-kit = { git = "https://github.com/Rubio-Enterprises/rubio-cli-kit", tag = "v1.0.0" }
```

## Usage

### Subcommand application

```python
from typing import Annotated

import typer

from rubio_cli_kit import _logging
from rubio_cli_kit._cli import make_app

app = make_app(name="example", help_text="Example commands.")


@app.command()
def greet(name: Annotated[str, typer.Argument()]) -> None:
    _logging.get_logger("example").debug("greeting", name=name)
    typer.echo(f"hello {name}")
```

### Single-command application

```python
from typing import Annotated

import typer

from rubio_cli_kit import _logging
from rubio_cli_kit._cli import make_single_command_app

app = make_single_command_app(name="example", help_text="Print a greeting.")


@app.command()
def main(name: Annotated[str, typer.Argument()]) -> None:
    _logging.get_logger("example").debug("greeting", name=name)
    typer.echo(f"hello {name}")
```

The single-command factory adds `--version` and `--verbose` to the root command without forcing the
consumer to repeat those parameters in its callback signature.

## Helper modules

- `rubio_cli_kit._cli` — Typer factories, exit codes, command-name prefixes, and runtime failures.
- `rubio_cli_kit._logging` — structlog configuration for console or JSON diagnostics on stderr.
- `rubio_cli_kit._output` — plain stdout data helpers and Rich stderr status helpers.
- `rubio_cli_kit._paths` — XDG environment-variable resolution with HOME-relative fallbacks.

## Development

```bash
git clone git@github.com:Rubio-Enterprises/rubio-cli-kit.git
cd rubio-cli-kit
mise install
uv sync
lefthook install
mise run lint
mise run test
```

## License

MIT — see `LICENSE`.
