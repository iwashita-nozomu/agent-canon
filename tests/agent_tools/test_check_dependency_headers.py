"""Tests for dependency header validation."""

# @dependency-start
# contract test
# responsibility Tests source-owned changed-file dependency header detection.
# upstream design ../../documents/design/dependency-contract-kinds.toml registered dependency header contract kinds
# upstream design ../../documents/design/source-owned-dependency-validation.md tracked source authority boundary
# upstream implementation ../../tools/agent_tools/check_dependency_headers.py changed-file checks
# upstream implementation ../../tools/agent_tools/visualization_contract.py canonical visualization contract dependency target
# downstream implementation ../../tools/ci/run_standalone_static_gate_unit.sh runs this source regression
# @dependency-end

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.agent_tools import check_dependency_headers as header_checker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "check_dependency_headers.py"
VISUALIZATION_QUEUE_PATHS = (
    "agents/skills/algorithm-flowchart.md",
    "agents/skills/catalog.yaml",
    ".agents/skills/algorithm-flowchart/SKILL.md",
    ".agents/skills/dependency-analysis/SKILL.md",
    ".agents/skills/prose-reasoning-graph/SKILL.md",
    "agents/skills/structure-refactor.md",
    ".agents/skills/structure-refactor/SKILL.md",
    "agents/skills/structure-planning.md",
    ".agents/skills/structure-planning/SKILL.md",
    "agents/skills/report-writing.md",
    ".agents/skills/report-writing/SKILL.md",
    "agents/skills/long-form-writing.md",
    ".agents/skills/long-form-writing/SKILL.md",
    "agents/skills/html-output.md",
    ".agents/skills/html-output/SKILL.md",
    "agents/skills/formal-proof-workflow.md",
    ".agents/skills/formal-proof-workflow/SKILL.md",
    "agents/skills/md-style-check.md",
    ".agents/skills/md-style-check/SKILL.md",
    "agents/skills/README.md",
    "tools/agent_tools/skill_route_catalog.py",
    "tools/agent_tools/capability_route.py",
    "tests/agent_tools/test_render_dependency_manifest_graph.py",
    "tools/catalog.yaml",
    "tools/agent_tools/tool_catalog.py",
    "tools/README.md",
    "documents/tools/README.md",
    "documents/tools/tool-docs.toml",
    "tests/agent_tools/test_tool_catalog.py",
    "tests/agent_tools/test_dependency_manifest_tools.py",
    "tests/agent_tools/test_check_dependency_headers.py",
    "rust/agent-canon/src/docs.rs",
    "rust/agent-canon/src/main.rs",
    "tests/tools/test_fix_mermaid.py",
    "agents/workflows/implementation-waterfall-workflow.md",
    "agents/workflows/agent-canon-pr-workflow.md",
)


def manifest(
    *,
    contract: str | None = "design",
    responsibility: str = "Documents a source fixture.",
) -> str:
    """Return one valid source manifest, optionally without a contract line."""
    lines = ["<!--", "@dependency-start"]
    if contract is not None:
        lines.append(f"contract {contract}")
    lines.extend(
        [
            f"responsibility {responsibility}",
            "upstream design README.md repository overview",
            "@dependency-end",
            "-->",
            "",
        ]
    )
    return "\n".join(lines)


def run_cli(root: Path, *paths: str, allow_frontmatter: bool = False) -> subprocess.CompletedProcess[str]:
    """Run the production CLI against one explicit repository root."""
    command = [sys.executable, str(SCRIPT), "--root", str(root)]
    if allow_frontmatter:
        command.append("--allow-frontmatter")
    command.extend(paths)
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class DependencyHeaderCheckTest(unittest.TestCase):
    """Exercise source-owned dependency header checks through the CLI."""

    def test_accepts_markdown_dependency_manifest(self) -> None:
        """Accept a Markdown file with one valid dependency manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "doc.md").write_text("# Doc\n\n" + manifest(), encoding="utf-8")

            result = run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_external_provenance_stays_outside_dependency_manifest(self) -> None:
        """Keep external provenance below, rather than inside, the manifest."""
        path = PROJECT_ROOT / "agents" / "skills" / "agent-log-analysis.md"
        text = path.read_text(encoding="utf-8")
        header = text.split("@dependency-start", 1)[1].split("@dependency-end", 1)[0]
        provenance = "https://github.com/iwashita-nozomu/agent-canon-log/pull/4"

        self.assertNotIn(provenance, header)
        self.assertIn(provenance, text.split("@dependency-end", 1)[1])

    def test_visualization_completion_queue_has_canonical_contract_edges(self) -> None:
        """Require visualization queue files to expose canonical contract edges."""
        patterns = header_checker.declared_surface_patterns(PROJECT_ROOT)
        for relative_path in VISUALIZATION_QUEUE_PATHS:
            with self.subTest(path=relative_path):
                header = "\n".join(
                    (PROJECT_ROOT / relative_path)
                    .read_text(encoding="utf-8")
                    .splitlines()[:80]
                )
                self.assertIn("@dependency-start", header)
                self.assertIn("@dependency-end", header)
                if header_checker.matches_declared_surface(relative_path, patterns):
                    self.assertTrue(
                        "code-visualization.md" in header
                        or "visualization_contract.py" in header
                        or "visualization_contract.md" in header,
                        relative_path,
                    )

    def test_accepts_skill_frontmatter_before_dependency_manifest(self) -> None:
        """Accept skill frontmatter before a valid dependency manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
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
            (root / "doc.md").write_text(manifest(contract=None), encoding="utf-8")

            result = run_cli(root, "doc.md")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly one contract line", result.stdout)
            self.assertIn("fix: add 'contract <registered-kind>'", result.stdout)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)

    def test_rejects_unregistered_contract_kind(self) -> None:
        """Reject a manifest that names an unknown contract kind."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
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
            (root / "tool.py").write_text('"""Missing dependency header."""\n', encoding="utf-8")

            result = run_cli(root, "tool.py")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing top dependency manifest block", result.stdout)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)

    def test_rejects_legacy_dependency_files_block(self) -> None:
        """Reject the retired Dependency Files block format."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "doc.md").write_text(
                "# Doc\n\nDependency Files:\n- README.md\n", encoding="utf-8"
            )

            result = run_cli(root, "doc.md")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)

    def test_skips_commentless_json(self) -> None:
        """Skip commentless JSON that cannot carry a dependency manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "data.json").write_text('{"ok": true}\n', encoding="utf-8")

            result = run_cli(root, "data.json")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_skips_reports_artifacts(self) -> None:
        """Skip generated report artifacts from header enforcement."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            artifact = root / "reports" / "some-run" / "generated_summary.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("README.md\n", encoding="utf-8")

            result = run_cli(root, "reports/some-run/generated_summary.md")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)


class DependencyHeaderSourceSelectionTest(unittest.TestCase):
    """Verify selection and validation use source bytes without graph runtime state."""

    def run_main(
        self,
        root: Path,
        argv: list[str],
        *,
        changed: list[Path] | None = None,
    ) -> tuple[int, str]:
        """Run the checker entry point with optional changed-path selection."""
        output = io.StringIO()
        patches = [patch.object(sys, "argv", ["check_dependency_headers.py", *argv])]
        if changed is not None:
            patches.append(
                patch.object(header_checker, "changed_paths", lambda _root: changed)
            )
        with contextlib.ExitStack() as stack:
            for active_patch in patches:
                stack.enter_context(active_patch)
            with contextlib.redirect_stdout(output):
                result = header_checker.main()
        return result, output.getvalue()

    def test_source_manifest_passes_without_graph_executable_or_state(self) -> None:
        """Validate source headers without graph runtime state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").mkdir()
            (root / "doc.md").write_text(manifest(), encoding="utf-8")

            result, output = self.run_main(
                root,
                ["--root", str(root), "doc.md"],
            )

            self.assertEqual(result, 0, output)
            self.assertIn("DEPENDENCY_HEADERS=pass", output)
            self.assertFalse((root / ".agent-canon").exists())

    def test_missing_source_manifest_fails_closed(self) -> None:
        """Fail closed when the selected source manifest is absent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").mkdir()
            (root / "doc.md").write_text("# doc\n", encoding="utf-8")

            result, output = self.run_main(
                root,
                ["--root", str(root), "doc.md"],
            )

            self.assertNotEqual(result, 0)
            self.assertIn("missing top dependency manifest block", output)

    def test_changed_mode_takes_precedence_over_positional_paths(self) -> None:
        """Prefer changed-path selection when changed mode is requested."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").mkdir()
            (root / "responsibility-scope.toml").write_text(
                'dependency_header_surfaces = ["scoped.py"]\n', encoding="utf-8"
            )
            scoped = root / "scoped.py"
            scoped.write_text("# scoped\n" + manifest(contract="tool"), encoding="utf-8")

            result, output = self.run_main(
                root,
                ["--root", str(root), "--changed", "missing.py"],
                changed=[scoped],
            )

            self.assertEqual(result, 0, output)
            self.assertIn("DEPENDENCY_HEADERS=pass", output)

    def test_no_path_mode_uses_changed_untracked_selection(self) -> None:
        """Use changed untracked selection when no explicit path is provided."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").mkdir()
            (root / "responsibility-scope.toml").write_text(
                'dependency_header_surfaces = ["scoped.py"]\n', encoding="utf-8"
            )
            (root / "scoped.py").write_text("# no header\n", encoding="utf-8")

            result, output = self.run_main(
                root,
                ["--root", str(root)],
                changed=[],
            )

            self.assertEqual(result, 0, output)
            self.assertIn("DEPENDENCY_HEADERS=pass", output)

    def test_changed_mode_fails_closed_without_scope_manifest(self) -> None:
        """Fail closed when changed mode lacks a responsibility scope manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").mkdir()
            changed = root / "scoped.py"
            changed.write_text("# scoped\n", encoding="utf-8")

            result, output = self.run_main(
                root,
                ["--root", str(root), "--changed"],
                changed=[changed],
            )

            self.assertNotEqual(result, 0)
            self.assertIn("scope manifest is missing", output)

    def test_changed_mode_fails_closed_for_invalid_or_empty_scope(self) -> None:
        """Fail closed for invalid or empty changed-path scope declarations."""
        for declaration in (
            "dependency_header_surfaces = [\n",
            "dependency_header_surfaces = []\n",
        ):
            with self.subTest(declaration=declaration), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                (root / ".git").mkdir()
                (root / "responsibility-scope.toml").write_text(
                    declaration, encoding="utf-8"
                )
                changed = root / "scoped.py"
                changed.write_text("# scoped\n", encoding="utf-8")

                result, output = self.run_main(
                    root,
                    ["--root", str(root), "--changed"],
                    changed=[changed],
                )

                self.assertNotEqual(result, 0)
                self.assertIn("scope manifest", output)


if __name__ == "__main__":
    unittest.main()
