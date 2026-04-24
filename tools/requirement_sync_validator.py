#!/usr/bin/env python3
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
from pathlib import Path
from typing import Any


PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+")


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
            pkg_name = pkg_token.lower().replace("-", "_")
            version_spec = line[len(pkg_token) :]
            packages[pkg_name] = version_spec

    return packages


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

    print(f"\n📊 Summary: {len(all_issues)} issues found")
    return 1 if any(i for i in all_issues if i.startswith("used package")) else 0


if __name__ == "__main__":
    sys.exit(main())
