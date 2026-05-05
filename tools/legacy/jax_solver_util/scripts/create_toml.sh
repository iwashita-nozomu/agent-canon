#!/bin/bash
# @dependency-start
# responsibility Preserves imported jax_solver_util legacy script for provenance.
# upstream design ../README.md legacy import policy
# @dependency-end
set -euo pipefail

# === 引数 or 環境変数 ===
PKGNAME="${1:-${PKGNAME:-}}"

if [[ -z "${PKGNAME}" ]]; then
  echo "Usage: $0 <package-name>"
  exit 1
fi

# Python import 名として妥当かチェック
if [[ ! "${PKGNAME}" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  echo "ERROR: Invalid Python package name: ${PKGNAME}"
  exit 1
fi

# === パス解決（スクリプト基準） ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# === ディレクトリ作成 ===
mkdir -p "${PROJECT_ROOT}/python/${PKGNAME}"
mkdir -p "${PROJECT_ROOT}/tests"

# === pyproject.toml ===
cat <<EOF > "${PROJECT_ROOT}/pyproject.toml"
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "${PKGNAME}"
version = "0.1.0"
description = "Common Python module: ${PKGNAME}"
readme = "README.md"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "ruff>=0.5",
]

[tool.setuptools]
package-dir = {"" = "python"}

[tool.setuptools.packages.find]
where = ["python"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I"]
EOF

# === __init__.py ===
cat <<EOF > "${PROJECT_ROOT}/python/${PKGNAME}/__init__.py"
__version__ = "0.1.0"

__all__ = ["__version__"]
EOF

# === core.py（最小） ===
cat <<EOF > "${PROJECT_ROOT}/python/${PKGNAME}/core.py"
def hello() -> str:
    return "hello from ${PKGNAME}"
EOF

# === 最小テスト ===
cat <<EOF > "${PROJECT_ROOT}/tests/test_import.py"
def test_import():
    import ${PKGNAME}  # noqa: F401
EOF

# === README ===
cat <<EOF > "${PROJECT_ROOT}/README.md"
# ${PKGNAME}

Common Python module.

## Development
\`\`\`bash
pip install -e ".[dev]"
pytest
ruff check .
\`\`\`
EOF

echo "✔ Project initialized:"
echo "  - pyproject.toml"
echo "  - python/${PKGNAME}/"
echo "  - tests/"
