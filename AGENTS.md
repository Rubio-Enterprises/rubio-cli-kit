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
