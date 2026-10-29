"""Integration tests for the native selected dependency-header checker."""

# @dependency-start
# contract test
# responsibility Tests selected dependency-header behavior through the native CLI.
# upstream design ../../documents/design/dependency-contract-kinds.toml registered dependency contract kinds
# upstream design ../../documents/design/dependency-manifest-design.md dependency header and edge grammar
# upstream design ../../documents/design/source-owned-dependency-validation.md tracked source authority boundary
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/dependency_headers.rs selected-file command
# downstream implementation ../../tools/validation/ci/runners/run_standalone_static_gate_unit.sh runs this source regression
# @dependency-end

from __future__ import annotations

import fnmatch
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


def manifest(
    *,
    contract: str | None = "design",
    responsibility: str = "Documents a source fixture.",
    comment: str = "html",
) -> str:
    """Return one valid manifest with the selected file's comment syntax."""
    lines = ["@dependency-start"]
    if contract is not None:
        lines.append(f"contract {contract}")
    lines.extend(
        [
            f"responsibility {responsibility}",
            "upstream design README.md repository overview",
            "@dependency-end",
        ]
    )
    if comment == "hash":
        return "\n".join(f"# {line}" for line in lines) + "\n"
    if comment == "slash":
        return "\n".join(f"// {line}" for line in lines) + "\n"
    return "<!--\n" + "\n".join(lines) + "\n-->\n"


def run_cli(
    root: Path,
    *paths: str,
    allow_frontmatter: bool = False,
    changed: bool = False,
    surfaces: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    """Run the selected native CLI against one explicit repository root."""
    if AGENT_CANON_CLI is None:
        raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
    command = [AGENT_CANON_CLI, "check-dependency-headers", "--root", str(root)]
    if allow_frontmatter:
        command.append("--allow-frontmatter")
    if changed:
        command.append("--changed")
    for surface in surfaces:
        command.extend(["--surface", surface])
    command.extend(paths)
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_contract_registry(
    root: Path,
    declaration: str = 'header_surfaces = ["scoped.py"]\n',
    *,
    allowed: tuple[str, ...] = ("tool",),
) -> None:
    """Write one dependency registry fixture with header selection and kinds."""
    registry = root / "documents" / "design" / "dependency-contract-kinds.toml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    allowed_text = ", ".join(f'"{kind}"' for kind in allowed)
    registry.write_text(
        '# @dependency-start\n'
        '# contract registry\n'
        '# responsibility Registers dependency header test surfaces and kinds.\n'
        '# @dependency-end\n'
        'schema = "agent_canon.dependency_contract_kinds.v1"\n'
        f"allowed_kinds = [{allowed_text}]\n"
        + declaration,
        encoding="utf-8",
    )


def git(root: Path, *args: str) -> None:
    """Run a Git command in one disposable source fixture."""
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def init_git(root: Path, *tracked: str) -> None:
    """Create a committed baseline so changed and untracked selection is real."""
    git(root, "init", "--quiet")
    git(root, "config", "user.name", "AgentCanon test")
    git(root, "config", "user.email", "agent-canon-test@example.invalid")
    if tracked:
        git(root, "add", "--", *tracked)
    git(root, "commit", "--quiet", "--allow-empty", "-m", "fixture baseline")


class DependencyHeaderCheckTest(unittest.TestCase):
    """Exercise source-owned dependency header checks through the native CLI."""

    def test_accepts_markdown_dependency_manifest(self) -> None:
        """Accept a Markdown file with one valid dependency manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["doc.md"]\n', allowed=("design",))
            (root / "doc.md").write_text("# Doc\n\n" + manifest(), encoding="utf-8")

            result = run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_external_provenance_stays_outside_dependency_manifest(self) -> None:
        """Accept external provenance after, rather than inside, the manifest."""
        provenance = "https://example.invalid/provenance"
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["doc.md"]\n', allowed=("design",))
            path = root / "doc.md"
            source = manifest() + f"External provenance: {provenance}\n"
            path.write_text(source, encoding="utf-8")

            result = run_cli(root, "doc.md")

            self.assertLess(source.index("@dependency-end"), source.index(provenance))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_accepts_skill_frontmatter_before_dependency_manifest_by_default(self) -> None:
        """Accept Skill frontmatter before its comment-wrapped manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["SKILL.md"]\n', allowed=("skill",))
            (root / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: demo-skill",
                        "description: Demonstrates frontmatter before a manifest.",
                        "---",
                        manifest(contract="skill"),
                    ]
                ),
                encoding="utf-8",
            )

            result = run_cli(root, "SKILL.md", allow_frontmatter=True)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_rejects_missing_contract_kind(self) -> None:
        """Reject a manifest that omits its registered contract kind."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["doc.md"]\n')
            (root / "doc.md").write_text(manifest(contract=None), encoding="utf-8")

            result = run_cli(root, "doc.md")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly one contract line", result.stdout)
            self.assertIn("fix: add 'contract <registered-kind>'", result.stdout)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)

    def test_rejects_unregistered_contract_kind(self) -> None:
        """Reject a manifest that names an unknown file-level contract kind."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["doc.md"]\n')
            (root / "doc.md").write_text(
                manifest(contract="invented-kind"), encoding="utf-8"
            )

            result = run_cli(root, "doc.md")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unregistered dependency contract kind", result.stdout)
            self.assertIn("fix: use an existing allowed_kinds entry", result.stdout)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)

    def test_rejects_missing_dependency_manifest(self) -> None:
        """Reject a checkable source file without a dependency manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["tool.py"]\n')
            (root / "tool.py").write_text(
                '"""Missing dependency header."""\n', encoding="utf-8"
            )

            result = run_cli(root, "tool.py")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing top dependency manifest block", result.stdout)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)

    def test_rejects_legacy_dependency_files_block(self) -> None:
        """Reject the retired Dependency Files block format."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["doc.md"]\n', allowed=("design",))
            (root / "doc.md").write_text(
                "# Doc\n\nDependency Files:\n- README.md\n", encoding="utf-8"
            )

            result = run_cli(root, "doc.md")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)

    def test_skips_commentless_json_and_report_artifacts(self) -> None:
        """Skip unsupported JSON and generated report artifacts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["data.json"]\n', allowed=("tool",))
            (root / "data.json").write_text('{"ok": true}\n', encoding="utf-8")
            artifact = root / "reports" / "some-run" / "generated_summary.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("README.md\n", encoding="utf-8")

            result = run_cli(
                root, "data.json", "reports/some-run/generated_summary.md"
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_skips_binary_non_owning_and_raw_nvidia_fixture_inputs(self) -> None:
        """Preserve byte-owned fixture, binary, symlink, and package-marker skips."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["**"]\n', allowed=("tool",))
            package = root / "__init__.py"
            package.write_text('"""Repository-local package namespace."""\n', encoding="utf-8")
            binary = root / "binary.md"
            binary.write_bytes(b"header\x00bytes\n")
            fixture = root / "tests" / "fixtures" / "nvidia" / "raw.txt"
            fixture.parent.mkdir(parents=True)
            fixture.write_text("exact parser fixture bytes\n", encoding="utf-8")
            source = root / "source.md"
            source.write_text(manifest(), encoding="utf-8")
            link = root / "alias.md"
            link.symlink_to(source)

            result = run_cli(
                root,
                "__init__.py",
                "binary.md",
                "tests/fixtures/nvidia/raw.txt",
                "alias.md",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_reports_typed_edge_kind_and_target_path_diagnostics(self) -> None:
        """Expose the shared parser's bad-kind and root-escape diagnostics via CLI."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, allowed=("implementation",))
            bad_kind = root / "tools" / "agent" / "orchestration" / "autonomous_convergence.py"
            bad_kind.parent.mkdir(parents=True)
            bad_kind.write_text(
                manifest(comment="hash").replace(
                    "# upstream design README.md repository overview\n",
                    "# downstream test ../../../tests/agent_tools/test_distributed_guarantee.py exercises the owner-receipt projection.\n",
                ),
                encoding="utf-8",
            )
            escaping = root / "tools" / "a" / "b" / "c" / "d" / "edge.py"
            escaping.parent.mkdir(parents=True)
            escaping.write_text(
                manifest(comment="hash").replace(
                    "# upstream design README.md repository overview\n",
                    "# downstream implementation ../../../../../../outside.py demonstrates root escape.\n",
                ),
                encoding="utf-8",
            )

            result = run_cli(
                root,
                "tools/agent/orchestration/autonomous_convergence.py",
                "tools/a/b/c/d/edge.py",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)
            self.assertIn("manifest-grammar", result.stdout)
            self.assertIn("target-escapes-root", result.stdout)


class DependencyHeaderSourceSelectionTest(unittest.TestCase):
    """Verify selected source paths and registry scope without graph runtime state."""

    def test_source_manifest_passes_without_graph_executable_or_state(self) -> None:
        """Validate an explicit source file without Git or graph runtime state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["doc.md"]\n', allowed=("design",))
            (root / "doc.md").write_text(manifest(), encoding="utf-8")

            result = run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)
            self.assertFalse((root / ".agent-canon").exists())

    def test_missing_source_manifest_fails_closed(self) -> None:
        """Fail closed when the selected source manifest is absent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["doc.md"]\n', allowed=("design",))
            (root / "doc.md").write_text("# doc\n", encoding="utf-8")

            result = run_cli(root, "doc.md")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing top dependency manifest block", result.stdout)

    def test_changed_mode_takes_precedence_over_positional_paths(self) -> None:
        """Prefer changed-path selection over a different invalid positional file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["scoped.py"]\n')
            scoped = root / "scoped.py"
            scoped.write_text(manifest(comment="hash"), encoding="utf-8")
            unrelated = root / "unrelated.py"
            unrelated.write_text("# intentionally not selected\n", encoding="utf-8")
            init_git(
                root,
                "documents/design/dependency-contract-kinds.toml",
                "scoped.py",
                "unrelated.py",
            )
            scoped.write_text(scoped.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")

            result = run_cli(root, "unrelated.py", changed=True)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_no_path_mode_checks_changed_untracked_selected_files(self) -> None:
        """Use changed and untracked paths in declared surfaces, not a full scan."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["scoped.py"]\n')
            init_git(root, "documents/design/dependency-contract-kinds.toml")
            (root / "scoped.py").write_text("# no header\n", encoding="utf-8")

            result = run_cli(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("scoped.py: missing top dependency manifest block", result.stdout)

    def test_surface_flag_adds_to_declared_header_surfaces(self) -> None:
        """Allow an explicitly added surface without widening the registry."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["declared.py"]\n')
            init_git(root, "documents/design/dependency-contract-kinds.toml")
            (root / "extra.py").write_text("# no header\n", encoding="utf-8")

            result = run_cli(root, changed=True, surfaces=("extra.py",))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("extra.py: missing top dependency manifest block", result.stdout)

    def test_surface_character_class_matches_fnmatchcase_caret_semantics(self) -> None:
        """Select paths according to Python fnmatchcase's literal-caret class rule."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_contract_registry(root, 'header_surfaces = ["unselected/**"]\n')
            init_git(root, "documents/design/dependency-contract-kinds.toml")
            paths = ("pkg/a.py", "pkg/^.py", "pkg/b.py")
            for relative in paths:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# no header\n", encoding="utf-8")
            surface = "pkg/[^a].py"
            expected = {
                relative for relative in paths if fnmatch.fnmatchcase(relative, surface)
            }
            self.assertEqual(expected, {"pkg/a.py", "pkg/^.py"})

            result = run_cli(root, changed=True, surfaces=(surface,))

            self.assertNotEqual(result.returncode, 0)
            for relative in expected:
                self.assertIn(f"{relative}: missing top dependency manifest block", result.stdout)
            self.assertNotIn("pkg/b.py: missing top dependency manifest block", result.stdout)

    def test_changed_mode_uses_canonical_registry_without_parent_copy(self) -> None:
        """Resolve AgentCanon's registry when the selected parent has no copy."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            init_git(root)
            scoped = root / "scoped.py"
            scoped.write_text(manifest(contract="tool", comment="hash"), encoding="utf-8")

            result = run_cli(root, changed=True, surfaces=("scoped.py",))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)
            self.assertFalse((root / "documents" / "design" / "dependency-contract-kinds.toml").exists())

    def test_changed_mode_fails_closed_for_invalid_or_empty_registry(self) -> None:
        """Fail closed for malformed or empty changed-path scope declarations."""
        for declaration in (
            "header_surfaces = [\n",
            "header_surfaces = []\n",
        ):
            with (
                self.subTest(declaration=declaration),
                tempfile.TemporaryDirectory() as tmp_dir,
            ):
                root = Path(tmp_dir)
                write_contract_registry(root, declaration)
                init_git(root, "documents/design/dependency-contract-kinds.toml")
                (root / "scoped.py").write_text("# scoped\n", encoding="utf-8")

                result = run_cli(root, changed=True)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("dependency contract registry", result.stdout)


if __name__ == "__main__":
    unittest.main()
