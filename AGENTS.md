# Agent context

This repo follows Rubio-Enterprises standards. Run `/audit-standards` from a Claude Code session to check conformance, or `/onboard-repo` for greenfield setup.

## Repository context

This public library is the shared runtime dependency for the per-tool CLI repositories extracted
from `Rubio-Enterprises/dotfiles` under dotfiles issue #316. The initial helper implementation was
copied from dotfiles commit `aadd937066c508b47b1a0f3df9b7f22dfa4833e4`:

- `home/dot_local/share/local-bin-scripts/src/local_bin_scripts/_cli.py`
- `home/dot_local/share/local-bin-scripts/src/local_bin_scripts/_logging.py`
- `home/dot_local/share/local-bin-scripts/src/local_bin_scripts/_output.py`
- `home/dot_local/share/local-bin-scripts/src/local_bin_scripts/_paths.py`

The kit owns Rich and structlog. Consumer command modules declare and import Typer directly, but must
not import Rich or structlog. `make_app` and `make_single_command_app` are the two sanctioned CLI
shapes; both must retain `-h`/`--help`, `--version`, `--verbose`, and structured diagnostics. The
distribution name is derived from the importing package and must not become a consumer parameter.

The distribution also registers `rubio_cli_kit.pytest_plugin` as a `pytest11` plugin. Consumer repos
provide only `tests/contract_table.py` plus `src/<package>/catalog.toml`; the contract type,
subprocess sandbox, fixtures, and test driver live here. The plugin enforces console-script/catalog/
contract-row parity, the external CLI wire contract, direct Typer declaration, and recursively
stdlib-only imports for catalog rows marked `hook = true`. This repo must never ship a
`catalog.toml`, because the installed kit shares every consumer's site-packages discovery directory.
