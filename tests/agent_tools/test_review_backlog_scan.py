"""Tests for the integrated review backlog scan wrapper."""

# @dependency-start
# contract test
# responsibility Tests integrated review backlog scan reporting behavior.
# upstream implementation ../../tools/agent_tools/review_backlog_scan.sh runs scan wrapper
# upstream implementation ../../tools/agent_tools/file_surface_inventory.py writes inventory reports
# upstream design ../../tools/static_analysis/common/README.md documents scan entrypoint
# @dependency-end

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REVIEW_SCAN = PROJECT_ROOT / "tools" / "agent_tools" / "review_backlog_scan.sh"


class ReviewBacklogScanTest(unittest.TestCase):
    """Verify integrated backlog scan behavior."""

    def test_inventory_check_writes_json_markdown_and_summary(self) -> None:
        """The inventory check should produce machine and human reports."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "parent"
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            fixture_tools = root / "tools" / "agent_tools"
            fixture_tools.mkdir(parents=True)
            for tool_name in ("file_surface_inventory.py", "surface_manifest.py"):
                shutil.copy2(
                    PROJECT_ROOT / "tools" / "agent_tools" / tool_name,
                    fixture_tools / tool_name,
                )
            report_dir = root / "reports"
            configured_target = root / ".agent-canon" / "cache" / "cargo-target"
            result = subprocess.run(
                [
                    "bash",
                    str(REVIEW_SCAN),
                    "--root",
                    str(root),
                    "--report-dir",
                    str(report_dir),
                    "--root-only",
                    "--check",
                    "inventory",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_PARENT_ROOT": str(root.parent / "untrusted-parent"),
                    "AGENT_CANON_REVIEW_SCAN_TARGET_DIR": str(configured_target),
                },
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REVIEW_BACKLOG_SCAN=pass", result.stdout)
            self.assertTrue((report_dir / "file_surface_inventory.json").is_file())
            self.assertTrue((report_dir / "file_surface_inventory.md").is_file())
            self.assertFalse(configured_target.exists())
            summary = (report_dir / "review_backlog_scan.md").read_text(encoding="utf-8")
            self.assertIn("| inventory | 0 |", summary)

    def test_stale_search_excludes_git_paths(self) -> None:
        """The stale search should not read .git object databases."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            git_object = root / ".git" / "objects" / "aa" / "leak.txt"
            git_object.parent.mkdir(parents=True)
            git_object.write_text("subtree legacy format\n", encoding="utf-8")
            (root / "README.md").write_text("# Clean\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            report_dir = root / "reports"

            result = subprocess.run(
                [
                    "bash",
                    str(REVIEW_SCAN),
                    "--root",
                    str(root),
                    "--report-dir",
                    str(report_dir),
                    "--root-only",
                    "--check",
                    "stale",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            stale_output = (report_dir / "stale_wording_search.txt").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("leak.txt", stale_output)
            self.assertIn("STALE_WORDING_SEARCH=no-matches", stale_output)

    def test_review_target_override_rejects_outside_without_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            report_dir = root / "reports"
            outside_target = root.parent / "outside-review-target"
            result = subprocess.run(
                [
                    "bash",
                    str(REVIEW_SCAN),
                    "--root",
                    str(root),
                    "--report-dir",
                    str(report_dir),
                    "--root-only",
                    "--check",
                    "inventory",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_REVIEW_SCAN_TARGET_DIR": str(outside_target),
                },
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PARENT_ROOT_SIDE_EFFECT_ERROR", result.stderr)
            self.assertFalse(outside_target.exists())
            self.assertFalse(report_dir.exists())

    def test_semantic_index_check_writes_review_artifacts(self) -> None:
        """Semantic review check should write merge, thin-doc, and search JSONL."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            fake_bin = root / "fake-bin"
            docs = root / "documents"
            docs.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            repeated = (
                "# Duplicate\n"
                "semantic review responsibility candidate phrase\n"
                "semantic review responsibility candidate phrase\n"
                "semantic review responsibility candidate phrase\n"
            )
            (docs / "one.md").write_text(repeated, encoding="utf-8")
            (docs / "two.md").write_text(repeated, encoding="utf-8")
            query = root / "query.txt"
            query.write_text("semantic review responsibility candidate", encoding="utf-8")
            report_dir = root / "reports"
            fake_bin.mkdir()
            stale_agent_canon = fake_bin / "agent-canon"
            stale_agent_canon.write_text(
                "#!/usr/bin/env bash\n"
                "if [ \"$1\" = 'semantic-index' ] && [ \"$2\" = 'help' ]; then\n"
                "  echo 'usage: agent-canon semantic-index <build|search|similar|merge-candidates|thin-docs|eval>'\n"
                "  exit 0\n"
                "fi\n"
                "echo stale agent-canon should not be selected >&2\n"
                "exit 2\n",
                encoding="utf-8",
            )
            stale_agent_canon.chmod(0o755)
            fake_cargo = fake_bin / "cargo"
            fake_cargo.write_text(
                "#!/usr/bin/env bash\n"
                "set -eu\n"
                "while [ \"$#\" -gt 0 ] && [ \"$1\" != '--' ]; do shift; done\n"
                "shift\n"
                "case \"$1 $2\" in\n"
                "  'semantic-index build')\n"
                "    while [ \"$#\" -gt 0 ]; do\n"
                "      if [ \"$1\" = '--db' ]; then : >\"$2\"; exit 0; fi\n"
                "      shift\n"
                "    done ;;\n"
                "  'semantic-index merge-candidates')\n"
                "    printf '%s\\n' '{\"semantic_index_pairs\":[],\"candidate_bucket\":[],\"responsibility_bucket\":[]}' ;;\n"
                "  'semantic-index thin-docs') printf '%s\\n' '{\"thin_docs\":[]}' ;;\n"
                "  'semantic-index search') printf '%s\\n' '{\"query_chars\":42}' ;;\n"
                "  'semantic-index eval-output')\n"
                "    while [ \"$#\" -gt 0 ]; do\n"
                "      if [ \"$1\" = '--report' ]; then\n"
                "        printf '%s\\n' '{\"semantic_index_output_eval\":\"pass\"}' >\"$2\"\n"
                "        printf '%s\\n' 'SEMANTIC_INDEX_OUTPUT_EVAL=pass'\n"
                "        exit 0\n"
                "      fi\n"
                "      shift\n"
                "    done ;;\n"
                "esac\n"
                "exit 2\n",
                encoding="utf-8",
            )
            fake_cargo.chmod(0o755)

            result = subprocess.run(
                [
                    "bash",
                    str(REVIEW_SCAN),
                    "--root",
                    str(root),
                    "--report-dir",
                    str(report_dir),
                    "--root-only",
                    "--check",
                    "semantic-index",
                    "--semantic-query-file",
                    str(query),
                    "--semantic-top-k",
                    "5",
                    "--semantic-min-score",
                    "0.80",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_REVIEW_SCAN_TARGET_DIR": str(root / "cargo-target"),
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                },
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(
                (report_dir / "semantic_index_root.sqlite").is_file(),
                result.stdout
                + result.stderr
                + "\nartifacts="
                + repr(sorted(path.name for path in report_dir.iterdir()))
                + "\nlogs="
                + repr(
                    {
                        path.name: path.read_text(encoding="utf-8", errors="replace")
                        for path in report_dir.iterdir()
                        if path.is_file()
                    }
                ),
            )
            merge_jsonl = (
                report_dir / "semantic_index_merge_candidates_root.jsonl"
            ).read_text(encoding="utf-8")
            self.assertIn("semantic_index_pairs", merge_jsonl)
            self.assertIn("candidate_bucket", merge_jsonl)
            self.assertIn("responsibility_bucket", merge_jsonl)
            self.assertTrue((report_dir / "semantic_index_thin_docs_root.jsonl").is_file())
            search_jsonl = (report_dir / "semantic_index_search_root.jsonl").read_text(
                encoding="utf-8"
            )
            self.assertIn('"query_chars"', search_jsonl)
            self.assertNotIn("semantic review responsibility candidate phrase", search_jsonl)
            output_eval = (report_dir / "semantic_index_output_eval_root.json").read_text(
                encoding="utf-8"
            )
            self.assertIn('"semantic_index_output_eval":"pass"', output_eval)
            output_eval_summary = (
                report_dir / "semantic_index_output_eval_root.txt"
            ).read_text(encoding="utf-8")
            self.assertIn("SEMANTIC_INDEX_OUTPUT_EVAL=pass", output_eval_summary)
            self.assertTrue((root / "cargo-target").is_dir())


if __name__ == "__main__":
    unittest.main()
