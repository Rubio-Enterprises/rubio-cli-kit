"""Project, catalog, and hook-import validation for the contract harness."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from rubio_cli_kit.contracts import CommandContract

KIT_DISTRIBUTION = "rubio-cli-kit"
_DEPENDENCY_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _normalize_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _require_string(value: object, *, field: str, command: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssertionError(f"catalog command {command!r} requires non-empty {field}")
    return value


@dataclass(frozen=True)
class ProjectManifest:
    name: str
    dependencies: tuple[str, ...]
    scripts: dict[str, str]

    @property
    def dependency_names(self) -> set[str]:
        names: set[str] = set()
        for dependency in self.dependencies:
            match = _DEPENDENCY_NAME.match(dependency)
            if match is not None:
                names.add(_normalize_distribution(match.group(1)))
        return names

    def declares(self, distribution: str) -> bool:
        return _normalize_distribution(distribution) in self.dependency_names


@dataclass(frozen=True)
class CatalogCommand:
    name: str
    hook: bool
    purpose: str | None
    use_when: str | None


@dataclass(frozen=True)
class Catalog:
    path: Path
    commands: tuple[CatalogCommand, ...]


@dataclass(frozen=True)
class ContractProject:
    root: Path
    manifest: ProjectManifest

    @staticmethod
    def participates(root: Path) -> bool:
        """Return whether this project should receive synthetic contract tests."""
        pyproject = root / "pyproject.toml"
        with pyproject.open("rb") as file:
            data = tomllib.load(file)
        project = data.get("project")
        if not isinstance(project, dict):
            return False
        name = project.get("name")
        if isinstance(name, str) and _normalize_distribution(name) == KIT_DISTRIBUTION:
            return True
        dependencies = project.get("dependencies")
        if not isinstance(dependencies, list):
            return False
        return any(
            isinstance(dependency, str)
            and (match := _DEPENDENCY_NAME.match(dependency)) is not None
            and _normalize_distribution(match.group(1)) == KIT_DISTRIBUTION
            for dependency in dependencies
        )

    @classmethod
    def from_root(cls, root: Path) -> ContractProject:
        pyproject = root / "pyproject.toml"
        with pyproject.open("rb") as file:
            data = tomllib.load(file)
        project = data.get("project")
        if not isinstance(project, dict):
            raise AssertionError("pyproject.toml must declare [project]")
        name = project.get("name")
        if not isinstance(name, str) or not name:
            raise AssertionError("pyproject.toml [project].name must be a non-empty string")
        raw_dependencies = project.get("dependencies", [])
        if not isinstance(raw_dependencies, list) or not all(
            isinstance(item, str) for item in raw_dependencies
        ):
            raise AssertionError("pyproject.toml [project].dependencies must be a string array")
        raw_scripts = project.get("scripts", {})
        if not isinstance(raw_scripts, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in raw_scripts.items()
        ):
            raise AssertionError("pyproject.toml [project.scripts] must map names to targets")
        return cls(
            root=root,
            manifest=ProjectManifest(
                name=name,
                dependencies=tuple(raw_dependencies),
                scripts=dict(raw_scripts),
            ),
        )

    @property
    def is_kit(self) -> bool:
        return _normalize_distribution(self.manifest.name) == KIT_DISTRIBUTION

    @property
    def is_consumer(self) -> bool:
        return self.manifest.declares(KIT_DISTRIBUTION)

    def assert_typer_declared(self) -> None:
        assert self.manifest.declares("typer"), (
            f"{self.manifest.name} must declare typer directly in [project].dependencies; "
            "the kit's transitive dependency is not the consumer contract"
        )

    def assert_command_import_ownership(self, command_name: str) -> None:
        target = self.manifest.scripts[command_name]
        module_name = target.partition(":")[0]
        entry_path = self._resolve_module(module_name)
        assert entry_path is not None, (
            f"cannot resolve command entry point module {module_name!r} "
            "under src/ or the project root"
        )
        tree = ast.parse(entry_path.read_text(), filename=str(entry_path))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.partition(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.partition(".")[0])
        assert "typer" in imports, (
            f"non-hook command {command_name!r} must import typer directly in {module_name}"
        )
        forbidden = sorted(imports & {"rich", "structlog"})
        assert not forbidden, (
            f"non-hook command {command_name!r} must not import {', '.join(forbidden)} directly; "
            "use rubio-cli-kit helpers"
        )

    def _catalog_paths(self) -> tuple[Path, ...]:
        source = self.root / "src"
        if not source.is_dir():
            return ()
        return tuple(sorted(source.glob("*/catalog.toml")))

    def load_catalog(self) -> Catalog:
        paths = self._catalog_paths()
        assert len(paths) == 1, (
            f"{self.manifest.name} must ship exactly one src/<package>/catalog.toml; "
            f"found {len(paths)}"
        )
        path = paths[0]
        with path.open("rb") as file:
            data = tomllib.load(file)
        raw_commands = data.get("command")
        assert isinstance(raw_commands, list) and raw_commands, (
            f"{path.relative_to(self.root)} must declare at least one [[command]]"
        )
        commands: list[CatalogCommand] = []
        seen: set[str] = set()
        for raw_command in raw_commands:
            assert isinstance(raw_command, dict), "each [[command]] must be a TOML table"
            raw_name = raw_command.get("name")
            name = _require_string(raw_name, field="name", command="<unnamed>")
            assert name not in seen, f"catalog command {name!r} is duplicated"
            seen.add(name)
            hook = raw_command.get("hook", False)
            assert isinstance(hook, bool), f"catalog command {name!r} hook must be a boolean"
            purpose = raw_command.get("purpose")
            use_when = raw_command.get("use_when")
            if hook:
                if purpose is not None:
                    _require_string(purpose, field="purpose", command=name)
                if use_when is not None:
                    _require_string(use_when, field="use_when", command=name)
            else:
                purpose = _require_string(purpose, field="purpose", command=name)
                use_when = _require_string(use_when, field="use_when", command=name)
            commands.append(
                CatalogCommand(
                    name=name,
                    hook=hook,
                    purpose=purpose if isinstance(purpose, str) else None,
                    use_when=use_when if isinstance(use_when, str) else None,
                )
            )
        return Catalog(path=path, commands=tuple(commands))

    def assert_command_coverage(self, *, contract_names: set[str]) -> None:
        catalog = self.load_catalog()
        script_names = set(self.manifest.scripts)
        catalog_names = {command.name for command in catalog.commands}
        assert catalog_names == script_names, (
            "catalog command names must exactly match [project.scripts]: "
            f"catalog-only={sorted(catalog_names - script_names)}, "
            f"scripts-only={sorted(script_names - catalog_names)}"
        )
        expected_contracts = {command.name for command in catalog.commands if not command.hook}
        assert contract_names == expected_contracts, (
            "contract rows must exactly cover non-hook commands: "
            f"rows-only={sorted(contract_names - expected_contracts)}, "
            f"missing={sorted(expected_contracts - contract_names)}"
        )

    def load_contracts(self) -> tuple[CommandContract, ...]:
        table = self.root / "tests" / "contract_table.py"
        assert table.is_file(), "consumers must provide tests/contract_table.py"
        digest = hashlib.sha256(str(table).encode()).hexdigest()[:16]
        module_name = f"_rubio_cli_contract_table_{digest}"
        spec = importlib.util.spec_from_file_location(module_name, table)
        if spec is None or spec.loader is None:
            raise AssertionError(f"cannot import {table}")
        module = importlib.util.module_from_spec(spec)
        search_paths = [str(table.parent), str(self.root / "src")]
        sys.path[:0] = search_paths
        try:
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        finally:
            del sys.path[: len(search_paths)]
            sys.modules.pop(module_name, None)
        commands = getattr(module, "COMMANDS", None)
        assert isinstance(commands, (tuple, list)), (
            "contract_table.COMMANDS must be a tuple or list"
        )
        assert all(isinstance(command, CommandContract) for command in commands), (
            "every contract_table.COMMANDS row must be a CommandContract"
        )
        names = [command.name for command in commands]
        assert len(names) == len(set(names)), "contract command names must be unique"
        return tuple(commands)

    def assert_hook_stdlib_only(self, command_name: str) -> None:
        target = self.manifest.scripts[command_name]
        module_name = target.partition(":")[0]
        entry_path = self._resolve_module(module_name)
        assert entry_path is not None, (
            f"cannot resolve hook entry point module {module_name!r} under src/ or the project root"
        )
        external = self._external_imports(module_name, entry_path)
        assert not external, (
            f"hook entry point {command_name!r} imports non-stdlib modules: "
            f"{', '.join(sorted(external))}"
        )

    def assert_kit_has_no_catalog(self) -> None:
        catalogs = sorted((self.root / "src").glob("**/catalog.toml"))
        assert not catalogs, (
            "rubio-cli-kit must not ship catalog.toml because it would match inside every consumer"
        )

    def _source_roots(self) -> tuple[Path, ...]:
        return (self.root / "src", self.root)

    def _resolve_module(self, module_name: str) -> Path | None:
        parts = module_name.split(".")
        for source_root in self._source_roots():
            module = source_root.joinpath(*parts).with_suffix(".py")
            if module.is_file():
                return module
            package = source_root.joinpath(*parts, "__init__.py")
            if package.is_file():
                return package
        return None

    def _is_local_package(self, module_name: str) -> bool:
        parts = module_name.split(".")
        return any(source_root.joinpath(*parts).is_dir() for source_root in self._source_roots())

    def _module_import_targets(self, module_name: str, path: Path) -> list[tuple[str, Path]]:
        targets: list[tuple[str, Path]] = []
        parts = module_name.split(".")
        for length in range(1, len(parts)):
            package_name = ".".join(parts[:length])
            package_path = self._resolve_module(package_name)
            if package_path is not None and package_path.name == "__init__.py":
                targets.append((package_name, package_path))
        targets.append((module_name, path))
        return targets

    def _external_imports(self, module_name: str, path: Path) -> set[str]:
        pending = self._module_import_targets(module_name, path)
        visited: set[Path] = set()
        external: set[str] = set()
        stdlib = set(sys.stdlib_module_names) | set(sys.builtin_module_names) | {"__future__"}
        while pending:
            current_module, current_path = pending.pop()
            resolved_path = current_path.resolve()
            if resolved_path in visited:
                continue
            visited.add(resolved_path)
            tree = ast.parse(current_path.read_text(), filename=str(current_path))
            for imported in self._imports_from_tree(tree, current_module, current_path):
                root_name = imported.partition(".")[0]
                local_path = self._resolve_module(imported)
                if local_path is not None:
                    pending.extend(self._module_import_targets(imported, local_path))
                    continue
                if self._is_local_package(imported):
                    continue
                parent_module = imported.rpartition(".")[0]
                if parent_module and self._resolve_module(parent_module) is not None:
                    continue
                if root_name in stdlib:
                    continue
                external.add(root_name)
        return external

    @staticmethod
    def _imports_from_tree(
        tree: ast.AST,
        current_module: str,
        current_path: Path,
    ) -> set[str]:
        imports: set[str] = set()
        importlib_aliases = {"importlib"}
        builtins_aliases = {"builtins"}
        import_module_names: set[str] = set()
        builtin_import_names = {"__import__"}
        nodes = tuple(ast.walk(tree))
        for node in nodes:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "importlib":
                        importlib_aliases.add(alias.asname or alias.name)
                    elif alias.name == "builtins":
                        builtins_aliases.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                for alias in node.names:
                    if node.module == "importlib" and alias.name == "import_module":
                        import_module_names.add(alias.asname or alias.name)
                    elif node.module == "builtins" and alias.name == "__import__":
                        builtin_import_names.add(alias.asname or alias.name)

        def is_dynamic_import_reference(expression: ast.expr) -> bool:
            if isinstance(expression, ast.Name):
                return expression.id in import_module_names | builtin_import_names
            if isinstance(expression, ast.Attribute) and isinstance(expression.value, ast.Name):
                return (
                    expression.attr == "import_module" and expression.value.id in importlib_aliases
                ) or (expression.attr == "__import__" and expression.value.id in builtins_aliases)
            if not isinstance(expression, ast.Call):
                return False
            if not isinstance(expression.func, ast.Name) or expression.func.id != "getattr":
                return False
            if len(expression.args) < 2 or not isinstance(expression.args[0], ast.Name):
                return False
            attribute = expression.args[1]
            if not isinstance(attribute, ast.Constant) or not isinstance(attribute.value, str):
                return False
            return (
                attribute.value == "import_module" and expression.args[0].id in importlib_aliases
            ) or (attribute.value == "__import__" and expression.args[0].id in builtins_aliases)

        changed = True
        while changed:
            changed = False
            for node in nodes:
                targets: list[ast.expr]
                value: ast.expr | None
                if isinstance(node, ast.Assign):
                    targets = list(node.targets)
                    value = node.value
                elif isinstance(node, ast.AnnAssign):
                    targets = [node.target]
                    value = node.value
                else:
                    continue
                if value is None or not is_dynamic_import_reference(value):
                    continue
                for target in targets:
                    if isinstance(target, ast.Name) and target.id not in import_module_names:
                        import_module_names.add(target.id)
                        changed = True

        package_parts = current_module.split(".")
        if current_path.name != "__init__.py":
            package_parts = package_parts[:-1]

        def dynamic_import_target(node: ast.Call) -> str:
            if (
                not node.args
                or not isinstance(node.args[0], ast.Constant)
                or not isinstance(node.args[0].value, str)
            ):
                return "<dynamic import>"
            target = node.args[0].value
            if not target:
                return "<dynamic import>"
            if not target.startswith("."):
                return target
            package_args = list(node.args[1:])
            package_args.extend(
                keyword.value for keyword in node.keywords if keyword.arg == "package"
            )
            if len(package_args) != 1:
                return "<dynamic import>"
            package_arg = package_args[0]
            if isinstance(package_arg, ast.Name) and package_arg.id == "__package__":
                package = ".".join(package_parts)
            elif isinstance(package_arg, ast.Constant) and isinstance(package_arg.value, str):
                package = package_arg.value
            else:
                return "<dynamic import>"
            try:
                return importlib.util.resolve_name(target, package)
            except ImportError:
                return "<dynamic import>"

        for node in nodes:
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
                continue
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    keep = len(package_parts) - node.level + 1
                    base_parts = package_parts[: max(keep, 0)]
                    if node.module:
                        base_parts.extend(node.module.split("."))
                    base = ".".join(base_parts)
                else:
                    base = node.module or ""
                if base:
                    imports.add(base)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    candidate = ".".join(part for part in (base, alias.name) if part)
                    imports.add(candidate)
                continue
            if not isinstance(node, ast.Call):
                continue
            if not is_dynamic_import_reference(node.func):
                continue
            imports.add(dynamic_import_target(node))
        return imports
