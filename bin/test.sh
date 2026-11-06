#!/bin/sh
set -eu
uv run --frozen pytest --junitxml=reports/test/junit.xml "$@"
