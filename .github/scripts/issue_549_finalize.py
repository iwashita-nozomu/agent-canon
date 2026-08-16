#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Performs the one-time final assembly for Issue #549 and removes itself from the published branch tree.
# upstream design ../../documents/design/responsibility-scope-management.md canonical path ownership relation
# upstream design ../../documents/design/dependency-contract-kinds.toml dependency-owned header surface relation
# downstream implementation ../../tools/agent_tools/responsibility_scope.py validates total single-owner classification
# downstream implementation ../../tests/agent_tools/test_responsibility_scope.py validates ownership regressions
# @dependency-end
"""Assemble and normalize the final Issue #549 branch tree."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

ROOT = Path.cwd()
DESIGN_PARTS = tuple(ROOT / f".issue-549-design.part-{index:02d}" for index in range(4))
DESIGN_PATH = ROOT / "documents" / "design" / "parent-repository-audit.md"
EXPECTED_DESIGN_SHA256 = "11690482006b371a6c979307e4c0e78e443b2ea36da13ef59d46e17a7a89a8cf"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "issue-549-finalize.yml"
SELF_PATH = Path(__file__).resolve()


def replace_once(path: str, old: str, new: str) -> None:
    """Replace one exact occurrence or fail closed."""
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one replacement in {path}, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_section(path: str, start: str, end: str, replacement: str) -> None:
    """Replace a delimited source section while retaining the end marker."""
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    target.write_text(text[:start_index] + replacement + text[end_index:], encoding="utf-8")


def assemble_design() -> None:
    """Assemble the canonical design document from the temporary transport parts."""
    payload = b"".join(part.read_bytes() for part in DESIGN_PARTS)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_DESIGN_SHA256:
        raise RuntimeError(f"design digest mismatch: {digest} != {EXPECTED_DESIGN_SHA256}")
    DESIGN_PATH.write_bytes(payload)


def normalize_python_sources() -> None:
    """Apply bounded source and test normalizations."""
    replace_once(
        "tests/agent_tools/test_parent_repository_audit.py",
        "from parent_repository_audit import _load_units  # noqa: E402",
        "from parent_repository_audit import _load_units",
    )
    replace_once(
        "tests/agent_tools/test_parent_repository_audit.py",
        '"documents/parent-repository-audit/audit-unit/"\n'
        '                    "environment-containers.md"',
        '"documents/parent-repository-audit/audit-unit/environment-containers.md"',
    )
    replace_once(
        "tests/agent_tools/test_responsibility_scope.py",
        "from responsibility_scope import scope_covers, scope_from_mapping  # noqa: E402",
        "from responsibility_scope import scope_covers, scope_from_mapping",
    )
    replace_once(
        "tools/agent_tools/repo_structure_contract.py",
        'raise ValueError(f"missing profile list in structure contract: {path}")',
        'raise TypeError(f"missing profile list in structure contract: {path}")',
    )


def normalize_dependency_consumers() -> None:
    """Route all dependency-header selection through the dependency registry."""
    checker_path = ROOT / "tools" / "agent_tools" / "check_dependency_headers.py"
    checker = checker_path.read_text(encoding="utf-8")
    checker = checker.replace(
        'RESPONSIBILITY_SCOPE_MANIFEST = Path("responsibility-scope.toml")\n',
        "",
        1,
    )
    checker = checker.replace(
        "declared responsibility-scope surfaces",
        "declared dependency-contract surfaces",
    )
    checker_path.write_text(checker, encoding="utf-8")
    replace_section(
        "tools/agent_tools/check_dependency_headers.py",
        "def declared_surface_patterns(root: Path) -> tuple[str, ...]:",
        "\n\ndef matches_declared_surface",
        '''def declared_surface_patterns(root: Path) -> tuple[str, ...]:
    """Read dependency-owned opt-in header surfaces from the existing registry."""
    registry = contract_registry_path(root)
    if not registry.is_file():
        raise ValueError(
            f"dependency contract registry is missing: {registry}; "
            "restore dependency-contract-kinds.toml before using --changed or no-path mode"
        )
    try:
        raw = tomllib.loads(registry.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(
            f"dependency contract registry is invalid: {registry}: {error}"
        ) from error
    if raw.get("schema") != "agent_canon.dependency_contract_kinds.v1":
        raise ValueError(
            f"dependency contract registry has an unsupported schema: {registry}"
        )
    values = raw.get("header_surfaces")
    if not isinstance(values, list) or not values:
        raise ValueError(
            f"dependency contract registry has no declared header surfaces: {registry}; "
            "add a non-empty header_surfaces list"
        )
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError(
            f"dependency contract registry contains an invalid header surface: {registry}; "
            "each header_surfaces entry must be a non-empty string"
        )
    return tuple(value for value in values if isinstance(value, str))
''',
    )

    shell_surface_loader = '''load_declared_surfaces() {
  local registry="${DEPENDENCY_CONTRACT_KIND_REGISTRY:-}"
  if [[ -z "$registry" && -f "$ROOT_DIR/documents/design/dependency-contract-kinds.toml" ]]; then
    registry="$ROOT_DIR/documents/design/dependency-contract-kinds.toml"
  elif [[ -z "$registry" && -f "$ROOT_DIR/vendor/agent-canon/documents/design/dependency-contract-kinds.toml" ]]; then
    registry="$ROOT_DIR/vendor/agent-canon/documents/design/dependency-contract-kinds.toml"
  elif [[ -z "$registry" ]]; then
    local script_path script_dir
    script_path="$(readlink -f "${BASH_SOURCE[0]}")"
    script_dir="$(cd "$(dirname "$script_path")" && pwd)"
    registry="$(realpath -m "$script_dir/../../documents/design/dependency-contract-kinds.toml")"
  fi
  [[ -f "$registry" ]] || return 0
  awk '\''
    /^header_surfaces[[:space:]]*=[[:space:]]*\[/ { in_block = 1; next }
    in_block && /^[[:space:]]*\]/ { exit }
    in_block {
      line = $0
      while (match(line, /"[^"]+"/)) {
        print substr(line, RSTART + 1, RLENGTH - 2)
        line = substr(line, RSTART + RLENGTH)
      }
    }
  '\'' "$registry"
}
'''
    for shell_path in (
        "tools/agent_tools/scan_dependency_headers.sh",
        "tools/agent_tools/check_dependency_header_format.sh",
    ):
        replace_section(
            shell_path,
            "load_declared_surfaces() {",
            "mapfile -t DECLARED_SURFACES",
            shell_surface_loader,
        )


def normalize_dependency_tests() -> None:
    """Move dependency-header fixtures from ownership scope to the registry."""
    test_path = ROOT / "tests" / "agent_tools" / "test_check_dependency_headers.py"
    text = test_path.read_text(encoding="utf-8")
    helper = '''

def write_contract_registry(root: Path, declaration: str) -> None:
    """Write one dependency registry fixture with header selection and kinds."""
    registry = root / "documents" / "design" / "dependency-contract-kinds.toml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        'schema = "agent_canon.dependency_contract_kinds.v1"\\n'
        'allowed_kinds = [\\n'
        '  "tool",\\n'
        ']\\n'
        + declaration,
        encoding="utf-8",
    )
'''
    marker = "\n\nclass DependencyHeaderCheckTest"
    if "def write_contract_registry" not in text:
        text = text.replace(marker, helper + marker, 1)

    old_fixture = '''            (root / "responsibility-scope.toml").write_text(
                'dependency_header_surfaces = ["scoped.py"]\\n', encoding="utf-8"
            )'''
    new_fixture = '''            write_contract_registry(
                root,
                'header_surfaces = ["scoped.py"]\\n',
            )'''
    if text.count(old_fixture) != 2:
        raise RuntimeError("expected two dependency surface fixture replacements")
    text = text.replace(old_fixture, new_fixture)

    old_loop_fixture = '''                (root / "responsibility-scope.toml").write_text(
                    declaration, encoding="utf-8"
                )'''
    if text.count(old_loop_fixture) != 1:
        raise RuntimeError("expected one invalid registry fixture replacement")
    text = text.replace(
        old_loop_fixture,
        "                write_contract_registry(root, declaration)",
        1,
    )
    text = text.replace("dependency_header_surfaces", "header_surfaces")
    text = text.replace(
        "test_changed_mode_fails_closed_for_invalid_or_empty_scope",
        "test_changed_mode_fails_closed_for_invalid_or_empty_registry",
    )
    text = text.replace("responsibility scope manifest", "dependency contract registry")
    text = text.replace("scope manifest", "dependency contract registry")

    fallback_pattern = re.compile(
        r"    def test_changed_mode_fails_closed_without_scope_manifest\(self\) -> None:\n"
        r".*?(?=\n    def test_changed_mode_fails_closed_for_invalid_or_empty_registry)",
        re.DOTALL,
    )
    fallback_test = '''    def test_changed_mode_uses_canonical_registry_without_parent_copy(self) -> None:
        """Consume AgentCanon's dependency registry without mirroring it into a parent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").mkdir()
            changed = root / "tools" / "agent_tools" / "scoped.py"
            changed.parent.mkdir(parents=True)
            changed.write_text(
                "# scoped\\n" + manifest(contract="tool"), encoding="utf-8"
            )

            result, output = self.run_main(
                root,
                ["--root", str(root), "--changed"],
                changed=[changed],
            )

            self.assertEqual(result, 0, output)
            self.assertIn("DEPENDENCY_HEADERS=pass", output)
'''
    text, count = fallback_pattern.subn(fallback_test, text, count=1)
    if count != 1:
        raise RuntimeError("canonical registry fallback test replacement failed")
    test_path.write_text(text, encoding="utf-8")


def document_boundary() -> None:
    """Record the distinct ownership and dependency path relations."""
    path = ROOT / "documents" / "design" / "responsibility-scope-management.md"
    text = path.read_text(encoding="utf-8")
    marker = (
        "filesystem kind are separate facts and must be declared only in the structure\n"
        "contract.\n\n"
    )
    paragraph = (
        "Dependency-header selection is a separate finite path relation owned by\n"
        "`documents/design/dependency-contract-kinds.toml`. It is consumed by the\n"
        "dependency-header tools and is not stored in the ownership manifest.\n\n"
    )
    if paragraph not in text:
        if marker not in text:
            raise RuntimeError("responsibility scope boundary insertion point missing")
        text = text.replace(marker, marker + paragraph, 1)
    path.write_text(text, encoding="utf-8")


def restore_executable_modes() -> None:
    """Restore executable modes lost through contents-API assembly commits."""
    for relative in (
        "tools/agent_tools/responsibility_scope.py",
        "tools/agent_tools/repo_structure_contract.py",
        "tools/agent_tools/parent_repository_audit.py",
        "tools/agent_tools/check_dependency_headers.py",
        "tools/agent_tools/scan_dependency_headers.sh",
        "tools/agent_tools/check_dependency_header_format.sh",
    ):
        path = ROOT / relative
        os.chmod(path, path.stat().st_mode | 0o111)


def remove_temporary_surfaces() -> None:
    """Remove transport and finalizer surfaces from the final branch tree."""
    paths = [
        *(part.relative_to(ROOT).as_posix() for part in DESIGN_PARTS),
        WORKFLOW_PATH.relative_to(ROOT).as_posix(),
        SELF_PATH.relative_to(ROOT).as_posix(),
    ]
    subprocess.run(["git", "rm", *paths], cwd=ROOT, check=True)


def main() -> None:
    """Perform the bounded one-time branch transformation."""
    assemble_design()
    normalize_python_sources()
    normalize_dependency_consumers()
    normalize_dependency_tests()
    document_boundary()
    restore_executable_modes()
    remove_temporary_surfaces()


if __name__ == "__main__":
    main()
