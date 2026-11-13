set positional-arguments
set shell := ["bash", "-euo", "pipefail", "-c"]

export RUBIO_BUILD_GITHUB_TOKEN := env('GH_TOKEN', env('GITHUB_TOKEN', ''))
export REPO_DIR := justfile_directory()
export COMPOSE_PROJECT_NAME := "repo-" + sha256(justfile_directory())
export GIT_COMMON_DIR := `git rev-parse --path-format=absolute --git-common-dir`

_run := if path_exists('/opt/standards') == 'true' { '' } else { 'docker compose run --rm -T dev' }
interactive := if path_exists('/opt/standards') == 'true' { '' } else { 'docker compose run --rm dev' }

# Show available recipes
_default:
    @just --list

# Build dev container image
build:
    @if [ ! -d /opt/standards ]; then bin/build.sh; fi

# Build the dev image, sync dependencies into volumes, and install git hooks
setup: build
    {{_run}} bin/setup.sh </dev/null
    {{_run}} /opt/standards/bin/install-hooks </dev/null

# Run standards checks inside the container
check:
    {{_run}} standards check </dev/null

# Run formatters and fixers inside the container
fmt:
    {{_run}} standards fmt </dev/null

# Run pull-request conventions check inside the container
check-pr:
    {{_run}} standards check-pr </dev/null

# Open interactive shell inside the dev container
shell:
    {{interactive}} bash

# Execute arbitrary command inside the dev container
exec *args:
    {{_run}} "$@" </dev/null

test *args:
    {{_run}} bin/test.sh "$@" </dev/null
