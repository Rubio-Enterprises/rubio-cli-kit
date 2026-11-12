# Agent context

First command in a fresh checkout: `just build`.
Never install toolchains on the host — all project commands run in the dev image through `just`.

```bash
just build
just setup
just check
just fmt
just check-pr
just test
just shell
just exec <cmd...>
```

Single test: `just exec uv run pytest path::test` (Python); otherwise prefix the underlying runner with `just exec`.

## Repository context

- **Architecture decisions**: an ADR records why a rule exists. Before changing a decision, check
  `docs/adr/` for an accepted ADR; reversing one needs a superseding ADR. Write one only if a
  person approved it: in the session, or in an approved plan or `spec:agent` issue that
  names the ADR. Otherwise the PR description is the record. Follow
  [the format](docs/adr/0001-record-architecture-decisions.md), which states the ADR test.

This public library is the shared runtime dependency for the per-tool CLI repositories extracted
from `Rubio-Enterprises/dotfiles` under dotfiles issue #316. The initial helper implementation was
copied from dotfiles commit `aadd937066c508b47b1a0f3df9b7f22dfa4833e4`: the `_cli`, `_logging`,
`_output` and `_paths` modules of its `local_bin_scripts` package (under
`home/dot_local/share/local-bin-scripts/` in that repository).

The kit owns Rich and structlog. Consumer command modules declare and import Typer directly, but must
not import Rich or structlog. `make_app` and `make_single_command_app` are the two sanctioned CLI
shapes; both must retain `-h`/`--help`, `--version`, `--verbose`, and structured diagnostics. The
distribution name is derived from the importing package and must not become a consumer parameter.

The distribution also registers `rubio_cli_kit.pytest_plugin` as a `pytest11` plugin. Consumer repos
provide only a `contract_table.py` in their `tests` folder plus `src/<package>/catalog.toml`; the contract type,
subprocess sandbox, fixtures, and test driver live here. The plugin enforces console-script/catalog/
contract-row parity, the external CLI wire contract, direct Typer declaration, and recursively
stdlib-only imports for catalog rows marked `hook = true`. This repo must never ship a
`catalog.toml`, because the installed kit shares every consumer's site-packages discovery directory.
