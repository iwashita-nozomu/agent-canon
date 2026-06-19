# @dependency-start
# contract test
# responsibility Tests semantic provider HTML report rendering.
# upstream implementation ../../tools/agent_tools/semantic_provider_html_report.py renders semantic provider comparison HTML
# upstream design ../../agents/skills/html-experiment-report.md defines HTML experiment report workflow
# upstream design ../../documents/semantic_index.md defines semantic provider comparison authority boundaries
# @dependency-end
"""Tests for semantic provider HTML reports."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "semantic_provider_html_report.py"


def sample_compare_report() -> dict[str, object]:
    """Return a minimal compare-providers report."""
    return {
        "semantic_index_provider_compare": "ok",
        "db": "reports/semantic-index.sqlite",
        "top_k": 10,
        "min_score": 0.82,
        "left": {
            "provider": "deterministic-dense-v1",
            "model": "hash-token-char-v1",
            "dim": 128,
            "nodes": 20,
            "merge_candidates": 4,
        },
        "right": {
            "provider": "llama-server-embedding",
            "model": "embeddinggemma",
            "dim": 768,
            "nodes": 20,
            "merge_candidates": 5,
        },
        "merge_candidates": {
            "left_count": 4,
            "right_count": 5,
            "shared_count": 2,
            "overlap_ratio": 0.4,
            "shared": ["documents/a.md:document:1-20|documents/b.md:document:1-20"],
            "left_only": ["documents/left.md:document:1-8|documents/<script>.md:document:1-8"],
            "right_only": ["documents/right.md:document:2-9|documents/peer.md:document:1-7"],
        },
        "search": {
            "query_chars": 42,
            "left_count": 3,
            "right_count": 3,
            "shared_count": 1,
            "overlap_ratio": 1 / 3,
            "left_top": [
                {
                    "rank": 1,
                    "score": 0.91,
                    "path": "documents/a.md",
                    "node_kind": "document",
                    "line_start": 1,
                    "line_end": 20,
                }
            ],
            "right_top": [
                {
                    "rank": 1,
                    "score": 0.93,
                    "path": "documents/c.md",
                    "node_kind": "document",
                    "line_start": 2,
                    "line_end": 18,
                }
            ],
            "left_only": ["documents/a.md:document:1-20"],
            "right_only": ["documents/c.md:document:2-18"],
        },
    }


class SemanticProviderHtmlReportTest(unittest.TestCase):
    """Verify semantic provider report rendering."""

    def test_render_html_report(self) -> None:
        """The CLI renders a self-contained HTML report with escaped evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            compare_json = root / "compare.json"
            output = root / "report.html"
            compare_json.write_text(
                json.dumps(sample_compare_report()),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--compare-json",
                    str(compare_json),
                    "--output",
                    str(output),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SEMANTIC_PROVIDER_HTML_REPORT=", result.stdout)
            html = output.read_text(encoding="utf-8")
            self.assertIn("Provider Delta To Shared Candidate Logic", html)
            self.assertIn("deterministic-dense-v1", html)
            self.assertIn("llama-server-embedding", html)
            self.assertIn("candidate_logic_authority=shared_responsibility_bucket", html)
            self.assertIn("documents/&lt;script&gt;.md", html)
            self.assertNotIn("documents/<script>.md", html)

    def test_missing_search_section_is_allowed(self) -> None:
        """A compare report without query search still renders."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            report = sample_compare_report()
            report["search"] = None
            compare_json = root / "compare.json"
            output = root / "report.html"
            compare_json.write_text(json.dumps(report), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--compare-json",
                    str(compare_json),
                    "--output",
                    str(output),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            html = output.read_text(encoding="utf-8")
            self.assertIn("search not recorded", html)
            self.assertIn("search comparison was not recorded", html)


if __name__ == "__main__":
    unittest.main()
