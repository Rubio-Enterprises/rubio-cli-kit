# CLI Toolkit Library

`rubio-cli-kit` (package `src/rubio_cli_kit`) is the public library that every per-tool CLI repository depends on at runtime. These repositories were split out of `Rubio-Enterprises/dotfiles` under dotfiles issue #316. The library has two jobs:

- **Runtime:** it provides the two sanctioned Typer application shapes, the exit codes, diagnostics, output rules, and XDG paths that consumer commands use.
- **Contract testing:** it registers a `pytest11` plugin that checks every consumer repository against the same external CLI contract. Consumers do not need to write any test code for this.

The kit owns Rich and structlog. Consumer command modules declare and import Typer directly, but they must not import Rich or structlog. The kit derives the distribution name from the importing package, so consumers never pass it as a parameter. The kit must never ship a `catalog.toml`, because the installed kit shares site-packages with every consumer.

## Architecture

```mermaid
graph TD
    subgraph Consumer["Consumer CLI repository"]
        CMD["Command modules<br/>(import typer + rubio_cli_kit)"]
        CAT["src/&lt;package&gt;/catalog.toml"]
        TABLE["tests/contract_table.py<br/>COMMANDS"]
        SCRIPTS["Installed console scripts"]
    end

    subgraph Kit["rubio_cli_kit"]
        subgraph Runtime["CLI runtime"]
            CLI["_cli.py<br/>make_app / make_single_command_app<br/>ExitCode / fail / prog_name"]
            LOG["_logging.py<br/>configure / get_logger"]
            OUT["_output.py<br/>emit_text / emit_json / status / warn / error"]
            PATHS["_paths.py<br/>xdg_dir"]
        end
        subgraph Contract["Contract testing (pytest11)"]
            PLUG["pytest_plugin.py<br/>fixtures + ContractFile"]
            PROJ["_contract_project.py<br/>ContractProject / Catalog"]
            DRV["_contract_driver.py<br/>ContractDriver"]
            CC["contracts.py<br/>CommandContract"]
            SB["testing.py<br/>CliSandbox / FakePath / FakeHttpServer"]
        end
    end

    subgraph ThirdParty["Third-party libraries owned by the kit"]
        TYPER["typer"]
        RICH["rich"]
        STRUCT["structlog"]
    end

    CMD --> CLI
    CMD --> OUT
    CMD --> LOG
    CMD --> PATHS
    CMD --> TYPER
    CLI --> LOG
    CLI --> OUT
    CLI --> TYPER
    LOG --> STRUCT
    OUT --> RICH

    PLUG --> PROJ
    PLUG --> DRV
    PLUG --> SB
    PROJ --> CAT
    PROJ --> TABLE
    TABLE --> CC
    DRV --> CC
    DRV --> SB
    SB --> SCRIPTS
    SCRIPTS -. "built with" .-> CLI
```

The CLI runtime produces the external behaviour: help flags, `--version`, `--verbose`, exit codes, and the stdout/stderr split. The contract-testing plugin checks that behaviour from outside. It runs each installed console script in a hermetic subprocess sandbox.

```mermaid
flowchart LR
    A["pytest session in a consumer repo"] --> B["pytest11 plugin loads automatically"]
    B --> C["Static checks<br/>typer declared, catalog valid,<br/>scripts = catalog = contract rows"]
    B --> D["Import checks<br/>hook rows: stdlib-only (recursive)<br/>other rows: typer, no rich/structlog"]
    B --> E["Driver checks per contract row<br/>root options, help paths, bare invocation,<br/>JSON wire, usage error (2), runtime error (1)"]
```

## Core components

| Component | Files | Summary | Documentation |
| --- | --- | --- | --- |
| CLI runtime | `_cli.py`, `_logging.py`, `_output.py`, `_paths.py` | Application factories, `ExitCode` and `fail`, structlog configuration on stderr, stdout data helpers, and XDG directory resolution | [CLI Runtime](cli_toolkit_library/cli_runtime.md) |
| Contract testing | `contracts.py`, `testing.py`, `_contract_project.py`, `_contract_driver.py`, `pytest_plugin.py` | `CommandContract` rows, sandbox and fakes, project and catalog validation, the contract driver, and pytest fixtures | [Contract Testing](cli_toolkit_library/contract_testing.md) |

Key references:

- [The shared CLI contract](cli_toolkit_library/cli_runtime.md#the-shared-cli-contract) describes the behaviour that both `make_app` and `make_single_command_app` guarantee.
- [Distribution discovery](cli_toolkit_library/cli_runtime.md#distribution-discovery) explains how `--version` finds the consumer's distribution without a parameter.
- [Consumer inputs](cli_toolkit_library/contract_testing.md#consumer-inputs) covers the `catalog.toml` and `contract_table.py` files that a consumer provides.
- [Generated test items](cli_toolkit_library/contract_testing.md#generated-test-items) lists every synthetic contract test.
- [Fixtures](cli_toolkit_library/contract_testing.md#fixtures) lists `home`, `cli_env`, `cli`, `fake_path`, and `fake_http_server`, which consumers can use in their own tests.

## Related modules

- Build tooling and dev environment: `pyproject.toml` declares the runtime dependencies (`typer`, `rich`, `structlog`) and the `pytest11` entry point.
- CI workflows: they run the test gate and the release-please pipeline that publishes the kit. In the kit's own repository, the plugin generates only the `contract:kit:no-catalog` check.
