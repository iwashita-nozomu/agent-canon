"""Tests for dependency header validation."""

# @dependency-start
# contract test
# responsibility Tests changed-file dependency header detection.
# upstream design ../../documents/dependency-contract-kinds.toml registered dependency header contract kinds
# upstream implementation ../../tools/agent_tools/check_dependency_headers.py changed-file checks
# upstream implementation ../../tools/agent_tools/graph_client.py validates persisted graph responses
# @dependency-end

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.agent_tools import check_dependency_headers as graph_checker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "check_dependency_headers.py"


class DependencyHeaderCheckTest(unittest.TestCase):
    """Exercise dependency header checks through the CLI."""

    def test_accepts_markdown_dependency_manifest(self) -> None:
        """Markdown files may declare dependency manifest markers near the top."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            doc = Path(tmp_dir) / "doc.md"
            doc.write_text(
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "<!--",
                        "@dependency-start",
                        "contract design",
                        "responsibility Documents a markdown file under test.",
                        "upstream design README.md repo overview",
                        "@dependency-end",
                        "-->",
                        "",
                        "Body.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(doc)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_accepts_skill_frontmatter_before_dependency_manifest(self) -> None:
        """SKILL.md may keep YAML frontmatter before the dependency manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            skill = Path(tmp_dir) / "SKILL.md"
            skill.write_text(
                "\n".join(
                    [
                        "---",
                        "name: demo-skill",
                        "description: Demonstrates frontmatter before the dependency manifest.",
                        "---",
                        "<!--",
                        "@dependency-start",
                        "contract skill",
                        "responsibility Documents a skill under test.",
                        "upstream design README.md repo overview",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--allow-frontmatter", str(skill)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_rejects_missing_contract_kind(self) -> None:
        """Manifest-bearing files declare exactly one registered contract kind."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            doc = Path(tmp_dir) / "doc.md"
            doc.write_text(
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "<!--",
                        "@dependency-start",
                        "responsibility Documents a markdown file under test.",
                        "upstream design README.md repo overview",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(doc)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly one contract line", result.stdout)
            self.assertIn("fix: add 'contract <registered-kind>'", result.stdout)
            self.assertIn("documents/dependency-contract-kinds.toml", result.stdout)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)

    def test_rejects_unregistered_contract_kind(self) -> None:
        """Contract kinds come from the registry rather than per-file invention."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            doc = Path(tmp_dir) / "doc.md"
            doc.write_text(
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "<!--",
                        "@dependency-start",
                        "contract invented-kind",
                        "responsibility Documents a markdown file under test.",
                        "upstream design README.md repo overview",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(doc)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unregistered dependency contract kind", result.stdout)
            self.assertIn("fix: use an existing allowed_kinds entry", result.stdout)
            self.assertIn("documents/dependency-contract-kinds.toml", result.stdout)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)

    def test_rejects_missing_dependency_manifest(self) -> None:
        """Checkable text files must declare dependency manifest markers near the top."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            script = Path(tmp_dir) / "tool.py"
            script.write_text(
                "\n".join(
                    [
                        '"""Missing dependency header."""',
                        "",
                        "from __future__ import annotations",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(script)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)
            self.assertIn("missing top dependency manifest block", result.stdout)

    def test_rejects_legacy_dependency_files_block(self) -> None:
        """Legacy Dependency Files blocks are no longer sufficient."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            doc = Path(tmp_dir) / "doc.md"
            doc.write_text(
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "Dependency Files:",
                        "- README.md",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(doc)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DEPENDENCY_HEADERS=fail", result.stdout)

    def test_skips_commentless_json(self) -> None:
        """JSON files are skipped because adding a comment header would break syntax."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            data = Path(tmp_dir) / "data.json"
            data.write_text('{"ok": true}\n', encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(data)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)

    def test_skips_reports_artifacts(self) -> None:
        """Generated reports are not source manifest targets."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            artifact = root / "reports" / "some-run" / "generated_summary.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("README.md\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "reports/some-run/generated_summary.md",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADERS=pass", result.stdout)


class FakeDependencyGraphClient:
    """Provide already-materialized dependency facts without producer execution."""

    def __init__(
        self,
        _root: Path,
        *,
        status: str = "fresh",
        nodes: list[dict[str, object]] | None = None,
    ) -> None:
        self._status = status
        self._nodes = nodes or []

    def status(self) -> SimpleNamespace:
        return SimpleNamespace(
            status=self._status,
            exit_code=0 if self._status == "fresh" else 2,
        )

    def query(self, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            status=self._status,
            exit_code=0 if self._status == "fresh" else 2,
            payload={"nodes": self._nodes},
        )


class DependencyHeaderGraphConsumerTest(unittest.TestCase):
    """Exercise consume-only dependency facts and freshness refusal."""

    def run_main(
        self,
        root: Path,
        graph: FakeDependencyGraphClient,
        *paths: str,
    ) -> tuple[int, str]:
        output = io.StringIO()
        argv = ["check_dependency_headers.py", "--root", str(root), *paths]
        with (
            patch.object(sys, "argv", argv),
            patch.object(graph_checker, "GraphClient", lambda _root: graph),
            contextlib.redirect_stdout(output),
        ):
            result = graph_checker.main()
        return result, output.getvalue()

    def test_consumes_fresh_manifest_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").mkdir()
            (root / "doc.md").write_text("# doc\n", encoding="utf-8")
            graph = FakeDependencyGraphClient(
                root,
                nodes=[
                    {
                        "id": "node:doc",
                        "path": "doc.md",
                        "payload": {
                            "manifest_present": True,
                            "contract_kind": "design",
                        },
                    }
                ],
            )
            result, output = self.run_main(root, graph, "doc.md")
            self.assertEqual(result, 0, output)
            self.assertIn("DEPENDENCY_HEADERS=pass", output)

    def test_missing_graph_manifest_fact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").mkdir()
            (root / "doc.md").write_text("# doc\n", encoding="utf-8")
            result, output = self.run_main(
                root,
                FakeDependencyGraphClient(root),
                "doc.md",
            )
            self.assertNotEqual(result, 0)
            self.assertIn("missing top dependency manifest block", output)

    def test_stale_graph_snapshot_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".git").mkdir()
            (root / "doc.md").write_text("# doc\n", encoding="utf-8")
            result, output = self.run_main(
                root,
                FakeDependencyGraphClient(root, status="stale"),
                "doc.md",
            )
            self.assertNotEqual(result, 0)
            self.assertIn("graph snapshot is not fresh", output)


if __name__ == "__main__":
    unittest.main()
