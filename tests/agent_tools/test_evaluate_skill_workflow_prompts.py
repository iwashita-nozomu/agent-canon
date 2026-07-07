# @dependency-start
# contract test
# responsibility Tests skill and workflow prompt eval automation.
# upstream implementation ../../tools/agent_tools/evaluate_skill_workflow_prompts.py helper  # noqa: E501
# upstream design ../../evidence/agent-evals/skill_workflow_prompt_eval.toml eval manifest
# @dependency-end
"""Tests for skill and workflow prompt evals."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import cast

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "evaluate_skill_workflow_prompts.py"
EXPECTED_SKILL_SHIM_COUNT = 55
EXPECTED_HUMAN_SKILL_DOC_COUNT = 56
EXPECTED_INTERNAL_ROUTINE_DOC_COUNT = 21
EXPECTED_WORKFLOW_DOC_COUNT = 21
EXPECTED_CANONICAL_DOC_COUNT = 6
EXPECTED_CODEX_AGENT_PROMPT_COUNT = 33
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from eval_manifest_paths import resolve_eval_manifest  # noqa: E402
from runtime_log_paths import mounted_log_archive_root  # noqa: E402


def run_eval(*args: str, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    """Run the prompt eval helper."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def load_toml_document(path: Path) -> dict[str, object]:
    """Load one TOML document with a concrete table type for strict pyright."""
    return cast(
        dict[str, object],
        tomllib.loads(  # pyright: ignore[reportUnknownMemberType]
            path.read_text(encoding="utf-8")
        ),
    )


class SkillWorkflowPromptEvalTest(unittest.TestCase):
    """Verify prompt eval behavior."""

    def test_default_manifest_passes(self) -> None:
        """The canonical prompt eval manifest passes on current prompts."""
        result = run_eval("--manifest", "evidence/agent-evals/skill_workflow_prompt_eval.toml")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("EVAL_STATUS=pass", result.stdout)
        self.assertIn("EVAL_CRITICAL_FAILED=0", result.stdout)
        self.assertIn("EVAL_AUDIT_STATUS=pass", result.stdout)
        self.assertIn("EVAL_GROWTH_CANDIDATES=0", result.stdout)
        self.assertIn("EVAL_RUN_ID=skill-eval-", result.stdout)

    def test_legacy_manifest_path_forwards_even_if_stale_old_file_exists(self) -> None:
        """Old manifest paths warn and resolve canonical even when stale files exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            canonical = root / "evidence" / "agent-evals" / "skill_workflow_prompt_eval.toml"
            legacy = root / "agents" / "evals" / "skill_workflow_prompt_eval.toml"
            canonical.parent.mkdir(parents=True)
            legacy.parent.mkdir(parents=True)
            canonical.write_text("canonical\n", encoding="utf-8")
            legacy.write_text("stale legacy\n", encoding="utf-8")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                resolved = resolve_eval_manifest(root, "agents/evals/skill_workflow_prompt_eval.toml")

        self.assertEqual(resolved, canonical)
        warning = stderr.getvalue()
        self.assertIn("EVAL_MANIFEST_FORWARDER=deprecated", warning)
        self.assertIn("old=agents/evals/skill_workflow_prompt_eval.toml", warning)
        self.assertIn("new=evidence/agent-evals/skill_workflow_prompt_eval.toml", warning)

    def test_default_manifest_includes_required_global_target_globs(self) -> None:
        """The canonical manifest covers every skill and workflow prompt family."""
        manifest = PROJECT_ROOT / "evidence" / "agent-evals" / "skill_workflow_prompt_eval.toml"
        data = load_toml_document(manifest)
        evals = cast(list[dict[str, object]], data["evals"])

        globs = {
            entry.get("target_glob"): entry.get("expected_count")
            for entry in evals
        }

        self.assertEqual(globs[".agents/skills/*/SKILL.md"], EXPECTED_SKILL_SHIM_COUNT)
        self.assertEqual(globs["agents/skills/*.md"], EXPECTED_HUMAN_SKILL_DOC_COUNT)
        self.assertEqual(
            globs["agents/internal-routines/*.md"], EXPECTED_INTERNAL_ROUTINE_DOC_COUNT
        )
        self.assertEqual(globs["agents/workflows/*.md"], EXPECTED_WORKFLOW_DOC_COUNT)
        self.assertEqual(globs["agents/canonical/*.md"], EXPECTED_CANONICAL_DOC_COUNT)
        self.assertEqual(globs[".codex/agents/*.toml"], EXPECTED_CODEX_AGENT_PROMPT_COUNT)

    def test_default_manifest_includes_convention_compliance_eval_coverage(
        self,
    ) -> None:
        """The canonical manifest verifies workflow convention gates and skill calls."""
        manifest = PROJECT_ROOT / "evidence" / "agent-evals" / "skill_workflow_prompt_eval.toml"
        data = load_toml_document(manifest)
        evals = cast(list[dict[str, object]], data["evals"])
        by_id = {str(entry["id"]): entry for entry in evals}
        workflow_eval = by_id["all-workflow-docs"]
        workflow_check_ids = {
            str(item["id"])
            for item in cast(list[dict[str, object]], workflow_eval["checklist"])
        }

        self.assertIn("CONVENTION-WORKFLOW-1", workflow_check_ids)
        self.assertEqual(
            by_id["agent-orchestration-skill-call-routing"]["target"],
            ".agents/skills/agent-orchestration/SKILL.md",
        )
        self.assertEqual(
            by_id["codex-task-workflow-convention-gate"]["target"],
            ".agents/skills/codex-task-workflow/SKILL.md",
        )
        for eval_id in (
            "agent-orchestration-skill-call-routing",
            "codex-task-workflow-convention-gate",
        ):
            checklists = cast(list[dict[str, object]], by_id[eval_id]["checklist"])
            self.assertTrue(all(bool(item["critical"]) for item in checklists))

    def test_default_manifest_includes_validation_failure_response_eval_coverage(
        self,
    ) -> None:
        """The canonical manifest covers test-design validation failure response."""
        manifest = PROJECT_ROOT / "evidence" / "agent-evals" / "skill_workflow_prompt_eval.toml"
        data = load_toml_document(manifest)
        evals = cast(list[dict[str, object]], data["evals"])
        by_id = {str(entry["id"]): entry for entry in evals}

        for eval_id, target_glob in (
            (
                "test-design-validation-failure-response-shim",
                ".agents/skills/test-design/SKILL.md",
            ),
            (
                "test-design-validation-failure-response-doc",
                "agents/skills/test-design.md",
            ),
        ):
            self.assertEqual(by_id[eval_id]["target_glob"], target_glob)
            self.assertEqual(by_id[eval_id]["expected_count"], 1)
            checklists = cast(list[dict[str, object]], by_id[eval_id]["checklist"])
            self.assertTrue(all(bool(item["critical"]) for item in checklists))

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

    def test_forbidden_pattern_fails(self) -> None:
        """A forbidden prompt route produces a matched-forbidden failure."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "prompt.md"
            manifest = root / "eval.toml"
            target.write_text(
                "required-marker\nDo not run check_convention_compliance.py.\n",
                encoding="utf-8",
            )
            manifest.write_text(
                textwrap.dedent(
                    """
                    # @dependency-start
                    # responsibility Defines forbidden prompt evals.
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
                    description = "requires marker and forbids bad route"
                    required_regex = ["required-marker"]
                    forbidden_regex = ["Do not run check_convention_compliance"]
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = run_eval("--root", str(root), "--manifest", "eval.toml")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("EVAL_STATUS=fail", result.stdout)
            self.assertIn("EVAL_MATCHED_FORBIDDEN", result.stdout)

    def test_report_out_writes_markdown(self) -> None:
        """The runner writes a Markdown eval artifact."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report = Path(tmp_dir) / "report.md"

            result = run_eval(
                "--manifest",
                "evidence/agent-evals/skill_workflow_prompt_eval.toml",
                "--report-out",
                str(report),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            text = report.read_text(encoding="utf-8")
            self.assertIn("# Skill Workflow Prompt Eval", text)
            self.assertIn("eval_run_id:", text)
            self.assertIn("EVAL_STATUS=pass", text)
            self.assertIn("## Run Manifest", text)
            self.assertIn("git_commit:", text)

    def test_compact_out_limits_stdout_and_writes_summary(self) -> None:
        """Compact mode writes stats to JSON and keeps stdout bounded."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            compact = Path(tmp_dir) / "compact.json"

            result = run_eval(
                "--manifest",
                "evidence/agent-evals/skill_workflow_prompt_eval.toml",
                "--compact-out",
                str(compact),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("EVAL_STATUS=pass", result.stdout)
            self.assertIn("EVAL_COMPACT_OUT=", result.stdout)
            self.assertNotIn("EVAL_CHECK eval=", result.stdout)
            payload = json.loads(compact.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["critical_failed"], 0)
            self.assertGreater(payload["checks_total"], 0)

    def test_existing_report_out_gets_unique_sibling(self) -> None:
        """An existing report path should not be overwritten."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report = Path(tmp_dir) / "report.md"
            report.write_text("keep me\n", encoding="utf-8")

            result = run_eval(
                "--manifest",
                "evidence/agent-evals/skill_workflow_prompt_eval.toml",
                "--report-out",
                str(report),
                "--skill-used",
                "agent-orchestration",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(report.read_text(encoding="utf-8"), "keep me\n")
            sibling_reports = sorted(report.parent.glob("report-skill-eval-*.md"))
            self.assertEqual(len(sibling_reports), 1)
            self.assertIn("EVAL_REPORT_OUT=", result.stdout)
            self.assertIn("agent-orchestration", sibling_reports[0].read_text(encoding="utf-8"))

    def test_accumulate_writes_unique_agentcanon_report(self) -> None:
        """Accumulated prompt evals should create durable unique result files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            result = run_eval(
                "--root",
                str(PROJECT_ROOT),
                "--manifest",
                "evidence/agent-evals/skill_workflow_prompt_eval.toml",
                "--accumulate",
                "--results-dir",
                str(root / "results"),
                "--run-id",
                "run-123",
                "--skill-used",
                "agent-orchestration",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("EVAL_ACCUMULATED_REPORT=", result.stdout)
            reports = sorted((root / "results").glob("skill-eval-*-pass-agent-orchestration.md"))
            self.assertEqual(len(reports), 1)
            text = reports[0].read_text(encoding="utf-8")
            self.assertIn("run_id: `run-123`", text)
            self.assertIn("used_skills: `agent-orchestration`", text)
            self.assertIn("tools/agent_tools/evaluate_skill_workflow_prompts.py", text)
            self.assertIn("skill_workflow_prompt_eval.toml", text)
            self.assertIn("## Run Manifest", text)

    def test_accumulate_records_workflow_monitoring_event(self) -> None:
        """Accumulated prompt evals should append behavior-eval evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            report_dir = root / "reports" / "agents" / "run-123"

            result = run_eval(
                "--root",
                str(PROJECT_ROOT),
                "--manifest",
                "evidence/agent-evals/skill_workflow_prompt_eval.toml",
                "--accumulate",
                "--results-dir",
                str(root / "results"),
                "--run-id",
                "run-123",
                "--skill-used",
                "agent-orchestration",
                "--report-dir",
                str(report_dir),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            monitor = report_dir / "workflow_monitoring.md"
            self.assertTrue(monitor.is_file())
            text = monitor.read_text(encoding="utf-8")
            self.assertIn("tool_call=evaluate_skill_workflow_prompts.py", text)
            self.assertIn("EVAL_RUN_ID=skill-eval-", text)
            self.assertIn("EVAL_USED_SKILLS=agent-orchestration", text)
            self.assertIn("EVAL_ACCUMULATED_REPORT=", text)
            self.assertIn("EVAL_GIT_COMMIT=", text)

    def test_accumulated_report_dependencies_resolve_through_root_symlinks(
        self,
    ) -> None:
        """Reports written through a wrapper root should reference canon paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            canon_root = tmp_root / "canon"
            wrapper_root = tmp_root / "wrapper"
            eval_dir = canon_root / "evidence" / "agent-evals"
            tools_dir = canon_root / "tools" / "agent_tools"
            eval_dir.mkdir(parents=True)
            tools_dir.mkdir(parents=True)
            archive_root = mounted_log_archive_root(canon_root)
            archive_root.mkdir(parents=True)
            wrapper_root.mkdir()
            (wrapper_root / "agents").symlink_to(canon_root / "agents")
            (wrapper_root / "evidence").symlink_to(canon_root / "evidence")
            (wrapper_root / "tools").symlink_to(canon_root / "tools")
            (tools_dir / "evaluate_skill_workflow_prompts.py").write_text(
                "# placeholder for dependency header validation\n",
                encoding="utf-8",
            )
            (eval_dir / "prompt.md").write_text("required-marker\n", encoding="utf-8")
            (eval_dir / "skill_workflow_prompt_eval.toml").write_text(
                textwrap.dedent(
                    """
                    # @dependency-start
                    # responsibility Defines prompt evals for symlink wrapper tests.
                    # upstream design prompt.md test prompt
                    # @dependency-end
                    version = 1

                    [[evals]]
                    id = "sample"
                    target = "evidence/agent-evals/prompt.md"
                    kind = "workflow"
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

            result = run_eval(
                "--root",
                str(wrapper_root),
                "--manifest",
                "evidence/agent-evals/skill_workflow_prompt_eval.toml",
                "--accumulate",
                "--run-id",
                "run-symlink",
                "--skill-used",
                "agent-orchestration",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            reports = sorted(
                (archive_root / "eval-results" / "skill-workflow-prompt").glob(
                    "skill-eval-*-pass-agent-orchestration.md"
                )
            )
            self.assertEqual(len(reports), 1)
            text = reports[0].read_text(encoding="utf-8")
            header = text.split("-->", 1)[0]
            self.assertIn("tools/agent_tools/evaluate_skill_workflow_prompts.py", header)
            self.assertIn("evidence/agent-evals/skill_workflow_prompt_eval.toml", header)
            self.assertNotIn("wrapper", header)

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
            self.assertIn(
                "must define exactly one of target or target_glob",
                result.stderr,
            )

    def test_duplicate_eval_id_fails_manifest_audit(self) -> None:
        """Duplicate eval IDs are rejected before prompt scoring."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "a.md").write_text("required-marker\n", encoding="utf-8")
            (root / "b.md").write_text("required-marker\n", encoding="utf-8")
            manifest = root / "eval.toml"
            manifest.write_text(
                textwrap.dedent(
                    """
                    # @dependency-start
                    # responsibility Defines duplicate eval id prompt evals.
                    # upstream design a.md test prompt
                    # upstream design b.md test prompt
                    # @dependency-end
                    version = 1

                    [[evals]]
                    id = "duplicate"
                    target = "a.md"

                    [[evals.checklist]]
                    id = "A1"
                    critical = true
                    required_regex = ["required-marker"]

                    [[evals]]
                    id = "duplicate"
                    target = "b.md"

                    [[evals.checklist]]
                    id = "B1"
                    critical = true
                    required_regex = ["required-marker"]
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = run_eval("--root", str(root), "--manifest", "eval.toml")

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("manifest audit failed", result.stderr)
            self.assertIn("duplicate eval id: duplicate", result.stderr)

    def test_duplicate_explicit_target_fails_manifest_audit(self) -> None:
        """Duplicate explicit targets are rejected to force eval consolidation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "prompt.md").write_text("required-marker\n", encoding="utf-8")
            manifest = root / "eval.toml"
            manifest.write_text(
                textwrap.dedent(
                    """
                    # @dependency-start
                    # responsibility Defines duplicate target prompt evals.
                    # upstream design prompt.md test prompt
                    # @dependency-end
                    version = 1

                    [[evals]]
                    id = "first"
                    target = "prompt.md"

                    [[evals.checklist]]
                    id = "A1"
                    critical = true
                    required_regex = ["required-marker"]

                    [[evals]]
                    id = "second"
                    target = "prompt.md"

                    [[evals.checklist]]
                    id = "B1"
                    critical = true
                    required_regex = ["required-marker"]
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = run_eval("--root", str(root), "--manifest", "eval.toml")

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("manifest audit failed", result.stderr)
            self.assertIn("duplicate explicit target: prompt.md", result.stderr)

    def test_duplicate_checklist_id_fails_manifest_audit(self) -> None:
        """Duplicate checklist IDs in one eval are rejected before scoring."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "prompt.md").write_text("required-marker\n", encoding="utf-8")
            manifest = root / "eval.toml"
            manifest.write_text(
                textwrap.dedent(
                    """
                    # @dependency-start
                    # responsibility Defines duplicate checklist prompt evals.
                    # upstream design prompt.md test prompt
                    # @dependency-end
                    version = 1

                    [[evals]]
                    id = "sample"
                    target = "prompt.md"

                    [[evals.checklist]]
                    id = "A1"
                    critical = true
                    required_regex = ["required-marker"]

                    [[evals.checklist]]
                    id = "A1"
                    critical = true
                    required_regex = ["required-marker"]
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = run_eval("--root", str(root), "--manifest", "eval.toml")

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("manifest audit failed", result.stderr)
            self.assertIn("duplicate checklist id: sample:A1", result.stderr)


if __name__ == "__main__":
    unittest.main()
