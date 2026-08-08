from __future__ import annotations

from pathlib import Path

import pytest

from rubio_cli_kit._contract_project import ContractProject


def _write_project(
    root: Path,
    *,
    name: str = "example-tool",
    dependencies: tuple[str, ...] = ("rubio-cli-kit", "typer>=0.26.8"),
    scripts: tuple[tuple[str, str], ...] = (("example", "example.cli:app"),),
    catalog: str | None = None,
) -> ContractProject:
    dependency_lines = "\n".join(f'  "{dependency}",' for dependency in dependencies)
    script_lines = "\n".join(f'{script} = "{target}"' for script, target in scripts)
    (root / "pyproject.toml").write_text(
        f"""[project]
name = "{name}"
version = "1.2.3"
dependencies = [
{dependency_lines}
]

[project.scripts]
{script_lines}
"""
    )
    package = root / "src" / name.replace("-", "_")
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "cli.py").write_text("from __future__ import annotations\n")
    if catalog is not None:
        (package / "catalog.toml").write_text(catalog)
    return ContractProject.from_root(root)


def test_consumer_must_declare_typer_directly(tmp_path: Path) -> None:
    project = _write_project(tmp_path, dependencies=("rubio-cli-kit",))

    with pytest.raises(AssertionError, match="declare typer directly"):
        project.assert_typer_declared()


def test_catalog_requires_purpose_and_use_when_for_non_hooks(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        catalog="""[[command]]
name = "example"
purpose = "Do the example thing."
""",
    )

    with pytest.raises(AssertionError, match="use_when"):
        project.load_catalog()


def test_catalog_hooks_may_omit_trigger_metadata(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        scripts=(("example-hook", "example_tool.cli:main"),),
        catalog="""[[command]]
name = "example-hook"
hook = true
""",
    )

    catalog = project.load_catalog()

    assert catalog.commands[0].hook is True


def test_catalog_and_contract_rows_cover_every_entry_point(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        scripts=(
            ("example", "example_tool.cli:app"),
            ("example-hook", "example_tool.hook:main"),
        ),
        catalog="""[[command]]
name = "example"
purpose = "Do the example thing."
use_when = "Use when an example is needed."

[[command]]
name = "example-hook"
hook = true
""",
    )

    project.assert_command_coverage(contract_names={"example"})

    with pytest.raises(AssertionError, match="contract rows"):
        project.assert_command_coverage(contract_names=set())


def test_hook_import_check_follows_local_modules(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        scripts=(("example-hook", "example_tool.cli:main"),),
        catalog="""[[command]]
name = "example-hook"
hook = true
""",
    )
    package = tmp_path / "src" / "example_tool"
    (package / "cli.py").write_text(
        "from example_tool import helper\n\ndef main() -> None:\n    del helper\n"
    )
    (package / "helper.py").write_text("import typer\n")

    with pytest.raises(AssertionError, match="typer"):
        project.assert_hook_stdlib_only("example-hook")


def test_hook_import_check_accepts_stdlib_and_local_stdlib_modules(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        scripts=(("example-hook", "example_tool.cli:main"),),
        catalog="""[[command]]
name = "example-hook"
hook = true
""",
    )
    package = tmp_path / "src" / "example_tool"
    (package / "cli.py").write_text(
        "from example_tool import helper\n\ndef main() -> None:\n    helper.run()\n"
    )
    (package / "helper.py").write_text("import json\n\ndef run() -> None:\n    json.dumps({})\n")

    project.assert_hook_stdlib_only("example-hook")


def test_hook_import_check_includes_package_initializers(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        scripts=(("example-hook", "example_tool.cli:main"),),
        catalog="""[[command]]
name = "example-hook"
hook = true
""",
    )
    package = tmp_path / "src" / "example_tool"
    (package / "__init__.py").write_text("import typer\n")
    (package / "cli.py").write_text("import json\n\ndef main() -> None:\n    json.dumps({})\n")

    with pytest.raises(AssertionError, match="typer"):
        project.assert_hook_stdlib_only("example-hook")


def test_hook_import_check_follows_local_modules_shadowing_stdlib(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        scripts=(("example-hook", "example_tool.cli:main"),),
        catalog="""[[command]]
name = "example-hook"
hook = true
""",
    )
    package = tmp_path / "src" / "example_tool"
    (package / "cli.py").write_text("import json\n\ndef main() -> None:\n    json.run()\n")
    (tmp_path / "src" / "json.py").write_text("import typer\n\ndef run() -> None:\n    pass\n")

    with pytest.raises(AssertionError, match="typer"):
        project.assert_hook_stdlib_only("example-hook")


def test_hook_import_check_rejects_literal_dynamic_third_party_imports(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        scripts=(("example-hook", "example_tool.cli:main"),),
        catalog="""[[command]]
name = "example-hook"
hook = true
""",
    )
    package = tmp_path / "src" / "example_tool"
    (package / "cli.py").write_text(
        "import importlib\n\ndef main() -> None:\n    importlib.import_module('typer')\n"
    )

    with pytest.raises(AssertionError, match="typer"):
        project.assert_hook_stdlib_only("example-hook")


def test_hook_import_check_follows_dynamic_import_callable_aliases(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        scripts=(("example-hook", "example_tool.cli:main"),),
        catalog="""[[command]]
name = "example-hook"
hook = true
""",
    )
    package = tmp_path / "src" / "example_tool"
    (package / "cli.py").write_text(
        "import importlib\n\nloader = importlib.import_module\n\ndef main() -> None:\n"
        "    loader('typer')\n"
    )

    with pytest.raises(AssertionError, match="typer"):
        project.assert_hook_stdlib_only("example-hook")


def test_hook_import_check_resolves_literal_relative_dynamic_imports(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        scripts=(("example-hook", "example_tool.cli:main"),),
        catalog="""[[command]]
name = "example-hook"
hook = true
""",
    )
    package = tmp_path / "src" / "example_tool"
    (package / "cli.py").write_text(
        "import importlib\n\ndef main() -> None:\n"
        "    importlib.import_module('.helper', __package__)\n"
    )
    (package / "helper.py").write_text("import json\n")

    project.assert_hook_stdlib_only("example-hook")


def test_hook_import_check_resolves_keyword_relative_dynamic_imports(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        scripts=(("example-hook", "example_tool.cli:main"),),
        catalog="""[[command]]
name = "example-hook"
hook = true
""",
    )
    package = tmp_path / "src" / "example_tool"
    (package / "cli.py").write_text(
        "import importlib\n\ndef main() -> None:\n"
        "    importlib.import_module('.helper', package=__package__)\n"
    )
    (package / "helper.py").write_text("import json\n")

    project.assert_hook_stdlib_only("example-hook")


def test_hook_import_check_rejects_computed_dynamic_imports(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        scripts=(("example-hook", "example_tool.cli:main"),),
        catalog="""[[command]]
name = "example-hook"
hook = true
""",
    )
    package = tmp_path / "src" / "example_tool"
    (package / "cli.py").write_text(
        "from importlib import import_module\n\ndef load(name: str) -> None:\n"
        "    import_module(name)\n"
    )

    with pytest.raises(AssertionError, match="dynamic import"):
        project.assert_hook_stdlib_only("example-hook")


def test_hook_import_check_allows_symbols_from_local_stdlib_modules(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        scripts=(("example-hook", "example_tool.cli:main"),),
        catalog="""[[command]]
name = "example-hook"
hook = true
""",
    )
    package = tmp_path / "src" / "example_tool"
    (package / "cli.py").write_text(
        "from example_tool.helper import VALUE\n\ndef main() -> None:\n    str(VALUE)\n"
    )
    (package / "helper.py").write_text("import json\n\nVALUE = json.dumps({})\n")

    project.assert_hook_stdlib_only("example-hook")


def test_hook_import_check_accepts_local_namespace_packages(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        scripts=(("example-hook", "acme.cli:main"),),
        catalog="""[[command]]
name = "example-hook"
hook = true
""",
    )
    namespace = tmp_path / "src" / "acme"
    namespace.mkdir()
    (namespace / "cli.py").write_text(
        "from acme import helper\n\ndef main() -> None:\n    helper.run()\n"
    )
    (namespace / "helper.py").write_text("import json\n\ndef run() -> None:\n    json.dumps({})\n")

    project.assert_hook_stdlib_only("example-hook")


def test_kit_must_not_ship_a_catalog_fragment(tmp_path: Path) -> None:
    project = _write_project(
        tmp_path,
        name="rubio-cli-kit",
        dependencies=("typer>=0.26.8",),
        scripts=(),
        catalog="""[[command]]
name = "wrong"
purpose = "Should not exist."
use_when = "Never."
""",
    )

    with pytest.raises(AssertionError, match="must not ship"):
        project.assert_kit_has_no_catalog()
