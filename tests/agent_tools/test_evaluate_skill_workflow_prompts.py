# @dependency-start
# responsibility Tests skill and workflow prompt eval automation.
# upstream implementation ../../tools/agent_tools/evaluate_skill_workflow_prompts.py tests target
# upstream design ../../agents/evals/skill_workflow_prompt_eval.toml default prompt eval manifest
# @dependency-end
"""Tests for skill and workflow prompt evals."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "evaluate_skill_workflow_prompts.py"


def run_eval(*args: str, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    """Run the prompt eval helper."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


class SkillWorkflowPromptEvalTest(unittest.TestCase):
    """Verify prompt eval behavior."""

    def test_default_manifest_passes(self) -> None:
        """The canonical prompt eval manifest passes on current prompts."""
        result = run_eval("--manifest", "agents/evals/skill_workflow_prompt_eval.toml")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("EVAL_STATUS=pass", result.stdout)
        self.assertIn("EVAL_CRITICAL_FAILED=0", result.stdout)

    def test_default_manifest_includes_required_global_target_globs(self) -> None:
        """The canonical manifest covers every skill and workflow prompt family."""
        manifest = PROJECT_ROOT / "agents" / "evals" / "skill_workflow_prompt_eval.toml"
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))

        globs = {
            entry.get("target_glob"): entry.get("expected_count") for entry in data["evals"]
        }

        self.assertEqual(globs[".agents/skills/*/SKILL.md"], 25)
        self.assertEqual(globs[".claude/skills/*/SKILL.md"], 25)
        self.assertEqual(globs["agents/skills/*.md"], 47)
        self.assertEqual(globs["agents/workflows/*.md"], 15)
        self.assertEqual(globs["agents/canonical/*.md"], 6)
        self.assertEqual(globs[".codex/agents/*.toml"], 29)

    def test_missing_required_pattern_fails(self) -> None:
        """A target missing required prompt language fails."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "prompt.md"
            manifest = root / "eval.toml"
            target.write_text("plain prompt without required term\n", encoding="utf-8")
            manifest.write_text(
                textwrap.dedent(
                    """
                    # @dependency-start
                    # responsibility Defines test prompt evals.
                    # upstream design prompt.md test prompt
                    # @dependency-end
                    version = 1

                    [[evals]]
                    id = "sample"
                    target = "prompt.md"
                    kind = "skill"
                    description = "sample"

                    [[evals.checklist]]
                    id = "S1"
                    critical = true
                    description = "requires marker"
                    required_regex = ["required-marker"]
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = run_eval("--root", str(root), "--manifest", "eval.toml")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("EVAL_STATUS=fail", result.stdout)
            self.assertIn("EVAL_MISSING_REQUIRED", result.stdout)

    def test_report_out_writes_markdown(self) -> None:
        """The runner writes a Markdown eval artifact."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report = Path(tmp_dir) / "report.md"

            result = run_eval(
                "--manifest",
                "agents/evals/skill_workflow_prompt_eval.toml",
                "--report-out",
                str(report),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            text = report.read_text(encoding="utf-8")
            self.assertIn("# Skill Workflow Prompt Eval", text)
            self.assertIn("EVAL_STATUS=pass", text)

    def test_target_glob_expands_to_each_matching_file(self) -> None:
        """A target_glob eval applies the same checklist to every matching prompt."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prompt_dir = root / "prompts"
            prompt_dir.mkdir()
            (prompt_dir / "a.md").write_text("# A\nrequired-marker\n", encoding="utf-8")
            (prompt_dir / "b.md").write_text("# B\nrequired-marker\n", encoding="utf-8")
            manifest = root / "eval.toml"
            manifest.write_text(
                textwrap.dedent(
                    """
                    # @dependency-start
                    # responsibility Defines glob prompt evals.
                    # upstream design prompts/a.md test prompt
                    # upstream design prompts/b.md test prompt
                    # @dependency-end
                    version = 1

                    [[evals]]
                    id = "glob-sample"
                    target_glob = "prompts/*.md"
                    kind = "workflow"
                    description = "sample"

                    [[evals.checklist]]
                    id = "G1"
                    critical = true
                    description = "requires marker"
                    required_regex = ["required-marker"]
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = run_eval("--root", str(root), "--manifest", "eval.toml")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("EVAL_CHECKS_TOTAL=2", result.stdout)
            self.assertIn("glob-sample:prompts/a.md", result.stdout)
            self.assertIn("glob-sample:prompts/b.md", result.stdout)

    def test_target_glob_expected_count_mismatch_fails_closed(self) -> None:
        """A glob count mismatch forces the eval manifest to be updated."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prompt_dir = root / "prompts"
            prompt_dir.mkdir()
            (prompt_dir / "a.md").write_text("required-marker\n", encoding="utf-8")
            manifest = root / "eval.toml"
            manifest.write_text(
                textwrap.dedent(
                    """
                    # @dependency-start
                    # responsibility Defines count-locked prompt evals.
                    # upstream design prompts/a.md test prompt
                    # @dependency-end
                    version = 1

                    [[evals]]
                    id = "glob-sample"
                    target_glob = "prompts/*.md"
                    expected_count = 2
                    kind = "workflow"
                    description = "sample"

                    [[evals.checklist]]
                    id = "G1"
                    critical = true
                    description = "requires marker"
                    required_regex = ["required-marker"]
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = run_eval("--root", str(root), "--manifest", "eval.toml")

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("expected_count=2 actual_count=1", result.stderr)

    def test_eval_with_both_target_and_target_glob_fails_closed(self) -> None:
        """A manifest entry cannot define both target variants."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "prompt.md").write_text("required-marker\n", encoding="utf-8")
            manifest = root / "eval.toml"
            manifest.write_text(
                textwrap.dedent(
                    """
                    # @dependency-start
                    # responsibility Defines invalid prompt evals.
                    # upstream design prompt.md test prompt
                    # @dependency-end
                    version = 1

                    [[evals]]
                    id = "invalid"
                    target = "prompt.md"
                    target_glob = "*.md"

                    [[evals.checklist]]
                    id = "G1"
                    critical = true
                    required_regex = ["required-marker"]
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = run_eval("--root", str(root), "--manifest", "eval.toml")

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("must define exactly one of target or target_glob", result.stderr)


if __name__ == "__main__":
    unittest.main()
