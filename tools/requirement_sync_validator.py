#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides requirement sync validator repository automation.
# upstream design README.md shared automation index
# @dependency-end

"""
要件同期検証スクリプト。

コード内で使用されているパッケージが requirements.txt に記載されているか確認。
使用されていないパッケージを検出。
セキュリティアップデートの提案。
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path


PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+")


def normalize_package_name(name: str) -> str:
    """Normalize one Python package name for manifest comparisons."""
    return name.lower().replace("-", "_")


def requirement_name(requirement: str) -> str | None:
    """Return the normalized package name from one requirement string."""
    stripped = requirement.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if "#" in stripped:
        stripped = stripped.split("#", 1)[0].strip()
    if not stripped:
        return None
    match = PACKAGE_NAME_RE.match(stripped)
    if match is None:
        return None
    return normalize_package_name(match.group(0))


def _stdlib_modules() -> set[str]:
    modules = set(getattr(sys, "stdlib_module_names", set()))
    modules.update(
        {
            "__future__",
            "collections",
            "concurrent",
            "contextlib",
            "copy",
            "dataclasses",
            "functools",
            "http",
            "importlib",
            "itertools",
            "json",
            "logging",
            "math",
            "multiprocessing",
            "os",
            "pathlib",
            "pickle",
            "random",
            "re",
            "runpy",
            "subprocess",
            "tempfile",
            "textwrap",
            "threading",
            "time",
            "traceback",
            "typing",
            "urllib",
            "warnings",
        }
    )
    return modules


def _local_modules() -> set[str]:
    modules: set[str] = set()
    python_root = Path("python")
    for entry in python_root.rglob("*"):
        if any(part.startswith(".") or part == "__pycache__" for part in entry.parts):
            continue
        if entry.is_dir():
            modules.add(entry.name)
        elif entry.suffix == ".py":
            modules.add(entry.stem)
    modules.update({"python", "scripts"})
    return modules


def extract_dockerfile_packages() -> set[str]:
    """Dockerfile で直接インストールするパッケージを抽出。"""
    dockerfile = Path("docker/Dockerfile")
    if not dockerfile.exists():
        return set()

    content = dockerfile.read_text(encoding="utf-8")
    packages: set[str] = set()
    for match in re.finditer(r"pip install[^\n]*\s([\"'][^\"']+[\"']|\S+)", content):
        token = match.group(1).strip("\"'")
        if token.startswith("-") or "requirements.txt" in token:
            continue
        pkg_name = token.split("[", 1)[0].split("=", 1)[0].lower().replace("-", "_")
        packages.add(pkg_name)
    return packages


class ImportCollector(ast.NodeVisitor):
    """Python コード内のインポートを収集。"""

    def __init__(self):
        self.imports = set()
        self.from_imports = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            module = alias.name.split(".")[0]
            self.imports.add(module)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            module = node.module.split(".")[0]
            self.from_imports.add(module)
        self.generic_visit(node)


def extract_imports_from_codebase() -> set[str]:
    """プロジェクトコード内で使用されているパッケージを抽出。"""
    imports = set()

    stdlib_modules = _stdlib_modules()
    local_modules = _local_modules()

    for py_file in Path("python").rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
            collector = ImportCollector()
            collector.visit(tree)

            imports.update(collector.imports)
            imports.update(collector.from_imports)
        except (SyntaxError, ValueError):
            pass

    return {imp for imp in imports if imp not in stdlib_modules and imp not in local_modules}


def extract_requirements() -> dict[str, str]:
    """requirements.txt からパッケージ名とバージョンを抽出。"""
    req_file = Path("docker/requirements.txt")
    packages = {}

    if not req_file.exists():
        print("❌ docker/requirements.txt not found")
        return packages

    content = req_file.read_text(encoding="utf-8")
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # パッケージと version を分割
        if "#" in line:
            line = line.split("#", 1)[0].strip()
        if not line:
            continue

        match = PACKAGE_NAME_RE.match(line)
        if match:
            pkg_token = match.group(0)
            pkg_name = normalize_package_name(pkg_token)
            version_spec = line[len(pkg_token) :]
            packages[pkg_name] = version_spec

    return packages


def extract_pyproject_dependency_groups() -> dict[str, set[str]]:
    """Extract normalized dependency names grouped by pyproject owner field."""
    pyproject = Path("pyproject.toml")
    if not pyproject.exists():
        return {}
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    groups: dict[str, set[str]] = {}

    project = data.get("project", {})
    if isinstance(project, dict):
        dependencies = project.get("dependencies", [])
        if isinstance(dependencies, list):
            groups["project.dependencies"] = {
                name
                for item in dependencies
                if isinstance(item, str)
                for name in [requirement_name(item)]
                if name is not None
            }
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for group_name, dependencies in sorted(optional.items()):
                if not isinstance(dependencies, list):
                    continue
                groups[f"project.optional-dependencies.{group_name}"] = {
                    name
                    for item in dependencies
                    if isinstance(item, str)
                    for name in [requirement_name(item)]
                    if name is not None
                }

    dependency_groups = data.get("dependency-groups", {})
    if isinstance(dependency_groups, dict):
        for group_name, dependencies in sorted(dependency_groups.items()):
            if not isinstance(dependencies, list):
                continue
            groups[f"dependency-groups.{group_name}"] = {
                name
                for item in dependencies
                if isinstance(item, str)
                for name in [requirement_name(item)]
                if name is not None
            }

    return groups


def check_pyproject_docker_contract(
    pyproject_groups: dict[str, set[str]],
    docker_requirements: dict[str, str],
) -> list[str]:
    """Return hard dependency-contract issues between pyproject and docker manifests."""
    issues: list[str] = []
    runtime_dependencies = pyproject_groups.get("project.dependencies", set())
    docker_packages = set(docker_requirements)
    for package_name in sorted(runtime_dependencies - docker_packages):
        issues.append(
            f"pyproject project dependency '{package_name}' missing from docker/requirements.txt"
        )
    return issues


def print_pyproject_docker_summary(
    pyproject_groups: dict[str, set[str]],
    docker_requirements: dict[str, str],
    issues: list[str],
) -> None:
    """Print machine-readable dependency-manifest ownership summary lines."""
    runtime_dependencies = pyproject_groups.get("project.dependencies", set())
    all_pyproject_dependencies = set().union(*pyproject_groups.values()) if pyproject_groups else set()
    docker_packages = set(docker_requirements)
    docker_only = docker_packages - all_pyproject_dependencies
    status = "fail" if issues else "pass"
    print(f"PYPROJECT_DOCKER_DEPENDENCY_SUMMARY={status}")
    print(f"PYPROJECT_DEPENDENCY_GROUPS={len(pyproject_groups)}")
    print(f"PYPROJECT_RUNTIME_DEPENDENCIES={len(runtime_dependencies)}")
    print(f"PYPROJECT_ALL_DEPENDENCIES={len(all_pyproject_dependencies)}")
    print(f"DOCKER_REQUIREMENTS_PACKAGES={len(docker_packages)}")
    print(f"PYPROJECT_DOCKER_RUNTIME_MISSING={len(runtime_dependencies - docker_packages)}")
    print(f"DOCKER_REQUIREMENTS_NOT_IN_PYPROJECT={len(docker_only)}")


def check_missing_imports(
    used: set[str],
    required: dict[str, str],
    dockerfile_packages: set[str],
) -> list[str]:
    """requirements.txt に無い使用パッケージを検出。"""
    issues = []
    installed = set(required) | dockerfile_packages

    # パッケージ名のマッピング（pip name vs import name）
    mapping = {
        "pyyaml": "yaml",
        "pillow": "pil",
        "attrs": "attr",
        "beautifulsoup4": "bs4",
    }
    transitive_ok = {
        "numpy": {"jax", "scipy"},
    }

    for pkg in sorted(used):
        req_name = mapping.get(pkg, pkg)
        if req_name in installed:
            continue
        providers = transitive_ok.get(req_name, set())
        if providers & installed:
            continue
        if req_name not in installed:
            issues.append(f"used package '{pkg}' not in requirements.txt")

    return issues


def check_unused_packages(used: set[str], required: dict[str, str]) -> list[str]:
    """requirements.txt に あるが未使用のパッケージを検出。"""
    issues = []

    # パッケージ名のマッピング（逆方向）
    mapping = {
        "yaml": "pyyaml",
        "pil": "pillow",
        "attr": "attrs",
        "bs4": "beautifulsoup4",
    }

    for req_pkg_name in sorted(required.keys()):
        import_name = mapping.get(req_pkg_name, req_pkg_name)
        if import_name not in used and req_pkg_name not in used:
            # 開発ツール（pytest, ruff など）は除外
            dev_tools = {"pytest", "ruff", "pyright", "black", "mdformat"}
            if req_pkg_name not in dev_tools:
                issues.append(f"package '{req_pkg_name}' in requirements.txt but not used")

    return issues


def check_version_pins(requirements: dict[str, str]) -> list[str]:
    """version pinning の確認。"""
    issues = []

    for pkg_name, version_spec in requirements.items():
        if not version_spec.startswith("=="):
            # 柔軟なバージョン指定が使用されている場合
            if ">=" in version_spec or "<" in version_spec:
                issues.append(
                    f"package '{pkg_name}' uses range specification (not pinned): {version_spec}"
                )

    return issues


def main() -> int:
    """要件同期検証メイン。"""
    print("🔍 Checking requirement synchronization...\n")

    all_issues = []

    # コード内の使用パッケージを抽出
    print("1️⃣ Extracting imports from codebase...")
    used_packages = extract_imports_from_codebase()
    print(f"   Found {len(used_packages)} external packages")

    # requirements.txt を解析
    print("\n2️⃣ Loading requirements.txt...")
    required_packages = extract_requirements()
    print(f"   Loaded {len(required_packages)} packages")
    dockerfile_packages = extract_dockerfile_packages()
    if dockerfile_packages:
        print(f"   Dockerfile direct installs: {', '.join(sorted(dockerfile_packages))}")

    # 不足しているパッケージ
    print("\n3️⃣ Checking missing imports...")
    issues = check_missing_imports(used_packages, required_packages, dockerfile_packages)
    for issue in issues:
        print(f"   ⚠️ {issue}")
        all_issues.append(issue)

    # 未使用パッケージ
    print("\n4️⃣ Checking unused packages...")
    issues = check_unused_packages(used_packages, required_packages)
    for issue in issues:
        print(f"   ⓘ {issue}")
        all_issues.append(issue)

    # Version pinning
    print("\n5️⃣ Checking version pinning...")
    issues = check_version_pins(required_packages)
    for issue in issues:
        print(f"   ℹ️ {issue}")
        all_issues.append(issue)

    # pyproject / docker manifest contract
    print("\n6️⃣ Checking pyproject/docker dependency contract...")
    pyproject_groups = extract_pyproject_dependency_groups()
    issues = check_pyproject_docker_contract(pyproject_groups, required_packages)
    print_pyproject_docker_summary(pyproject_groups, required_packages, issues)
    for issue in issues:
        print(f"   ⚠️ {issue}")
        all_issues.append(issue)

    print(f"\n📊 Summary: {len(all_issues)} issues found")
    hard_issue_prefixes = (
        "used package",
        "pyproject project dependency",
    )
    return 1 if any(i.startswith(hard_issue_prefixes) for i in all_issues) else 0


if __name__ == "__main__":
    sys.exit(main())
