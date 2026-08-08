# rubio-cli-kit

<!-- badges: start -->
<!-- badges: end -->

> One-sentence description.

## What it is

2–3 sentence elevator pitch: what problem does this solve? Who uses it? What's the operational status (experimental / internal / production = `internal`)?

## Install / quickstart

```bash
# Copy-pasteable install command(s)
```

## Usage

```bash
# Smallest runnable example
```

## Configuration

Environment variables:

- `LOG_LEVEL` — `debug` | `info` | `warn` | `error` (default `info`)
- `LOG_FORMAT` — `json` | `console` (default `json` for services, `console` for CLIs)
- `SERVICE_NAME` — kebab-case, defaults to `rubio-cli-kit`

Config file location (if applicable): _document here_.

## Development

```bash
git clone <repo-url>
cd rubio-cli-kit
mise install                       # install pinned tools + runtimes (.mise.toml, plus .tool-versions where rendered)
uv sync
lefthook install                  # register git hooks
mise run lint
mise run test
```

## License

MIT — see `LICENSE`.
