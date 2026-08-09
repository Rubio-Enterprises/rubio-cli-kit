from __future__ import annotations

import importlib.metadata
from pathlib import Path

import pytest

pytest_plugins = ("pytester",)


def test_distribution_registers_pytest_plugin() -> None:
    plugins = {
        entry_point.value for entry_point in importlib.metadata.entry_points(group="pytest11")
    }

    assert "rubio_cli_kit.pytest_plugin" in plugins


def test_plugin_collects_contract_tests_from_command_table(pytester: pytest.Pytester) -> None:
    pytester.makepyprojecttoml(
        """[project]
name = "example-tool"
version = "1.2.3"
dependencies = ["rubio-cli-kit", "typer>=0.26.8"]

[project.scripts]
example = "example_tool.cli:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
"""
    )
    pytester.makefile(
        ".toml",
        **{
            "src/example_tool/catalog": """[[command]]
name = "example"
purpose = "Do the example thing."
use_when = "Use when an example is needed."
"""
        },
    )
    pytester.makepyfile(
        **{
            "tests/contract_table": """from rubio_cli_kit.contracts import CommandContract

COMMANDS = (
    CommandContract(
        name="example",
        help_paths=(),
        json_args=("--json",),
        usage_error_args=("--bad",),
        runtime_error_args=("explode",),
    ),
)
"""
        },
    )

    result = pytester.runpytest_subprocess("--collect-only", "-q")

    result.assert_outcomes()
    output = result.stdout.str()
    assert "contract:manifest:typer-declared" in output
    assert "contract:catalog:valid" in output
    assert "contract:example:import-ownership" in output
    assert "contract:example:root-options" in output
    assert "contract:example:runtime-error" in output


def test_plugin_self_checks_the_kit_without_a_command_table(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyprojecttoml(
        """[project]
name = "rubio-cli-kit"
version = "1.0.0"
dependencies = ["typer>=0.26.8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
"""
    )

    result = pytester.runpytest_subprocess("--collect-only", "-q")

    result.assert_outcomes()
    assert "contract:kit:no-catalog" in result.stdout.str()


def test_plugin_ignores_projects_that_do_not_consume_the_kit(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyprojecttoml(
        """[tool.pytest.ini_options]
testpaths = ["tests"]
"""
    )
    pytester.makepyfile(**{"tests/test_plain": "def test_plain() -> None:\n    assert True\n"})

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1)
    assert "INTERNALERROR" not in result.stderr.str()


def test_plugin_reports_invalid_consumer_manifest_as_a_test_failure(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyprojecttoml(
        """[project]
name = 42
version = "1.2.3"
dependencies = ["rubio-cli-kit", "typer>=0.26.8"]
"""
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(failed=1)
    assert "contract:configuration:valid" in result.stdout.str()
    assert "INTERNALERROR" not in result.stderr.str()


def test_plugin_reports_contract_table_exceptions_as_test_failures(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyprojecttoml(
        """[project]
name = "example-tool"
version = "1.2.3"
dependencies = ["rubio-cli-kit", "typer>=0.26.8"]

[project.scripts]
example = "example_tool.cli:app"
"""
    )
    pytester.makefile(
        ".toml",
        **{
            "src/example_tool/catalog": """[[command]]
name = "example"
purpose = "Do the example thing."
use_when = "Use when an example is needed."
"""
        },
    )
    pytester.makepyfile(
        **{"tests/contract_table": "raise RuntimeError('broken contract table')\n"},
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1, failed=1)
    assert "broken contract table" in result.stdout.str()
    assert "INTERNALERROR" not in result.stderr.str()


def test_plugin_reports_contract_table_system_exit_as_a_test_failure(
    pytester: pytest.Pytester,
) -> None:
    pytester.makepyprojecttoml(
        """[project]
name = "example-tool"
version = "1.2.3"
dependencies = ["rubio-cli-kit", "typer>=0.26.8"]

[project.scripts]
example = "example_tool.cli:app"
"""
    )
    pytester.makefile(
        ".toml",
        **{
            "src/example_tool/catalog": """[[command]]
name = "example"
purpose = "Do the example thing."
use_when = "Use when an example is needed."
"""
        },
    )
    pytester.makepyfile(
        **{"tests/contract_table": "raise SystemExit(2)\n"},
    )

    result = pytester.runpytest_subprocess("-q")

    result.assert_outcomes(passed=1, failed=1)
    assert "contract:configuration:valid" in result.stdout.str()
    assert "INTERNALERROR" not in result.stderr.str()


def test_command_table_location_is_relative_to_project_root(tmp_path: Path) -> None:
    root = tmp_path / "standalone"
    table = root / "tests" / "contract_table.py"
    table.parent.mkdir(parents=True)
    table.write_text("COMMANDS = ()\n")

    assert table.relative_to(root) == Path("tests/contract_table.py")
