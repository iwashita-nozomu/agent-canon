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
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest import mock

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "evaluate_skill_workflow_prompts.py"
TEST_TEMP_ROOT = PROJECT_ROOT / ".agent-canon" / "validation"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
import evaluate_skill_workflow_prompts as evaluator  # noqa: E402
from eval_manifest_paths import resolve_eval_manifest  # noqa: E402
from parent_root_side_effects import (  # noqa: E402
    ParentRootSideEffectBoundary,
    public_session,
    session_environment,
)
from runtime_log_paths import mounted_log_archive_root  # noqa: E402


def run_eval(*args: str, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    """Run the prompt eval helper through one signed public session."""
    invocation_script = TEST_TEMP_ROOT / "evaluate-skill-workflow-session.py"
    invocation_script.write_text(
        "# signed prompt-evaluation fixture runner\n", encoding="utf-8"
    )
    previous_cwd = Path.cwd()
    previous_environment = dict(os.environ)
    os.chdir(PROJECT_ROOT)
    try:
        with public_session(
            invocation_script=invocation_script,
            purpose="skill-workflow-test-eval",
        ) as session:
            environment = session_environment(session, previous_environment)
            return subprocess.run(
                [sys.executable, str(SCRIPT), *args],
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
    finally:
        os.chdir(previous_cwd)
        invocation_script.unlink(missing_ok=True)


def load_toml_document(path: Path) -> dict[str, object]:
    """Load one TOML document with a concrete table type for strict pyright."""
    return cast(
        dict[str, object],
        tomllib.loads(  # pyright: ignore[reportUnknownMemberType]
            path.read_text(encoding="utf-8")
        ),
    )


def t14_report_text(
    scenario_id: str = "OOP-TYPE-SCENARIO-01",
    iteration: int = 1,
    *,
    requirement_id: str = "R101",
    requirement_status: str = "pass",
    retry_count: int = 0,
    ambiguity: str = "none",
    provenance: str = "fresh",
    evaluation_status: str = "pass",
) -> str:
    """Build the fixed five-section report used by parser tests."""
    return textwrap.dedent(
        f"""\
        Output:
        command=python3 tools/agent_tools/route.py --capability oop_type_design
        artifacts=none
        authority=parent
        route=explicit capability
        Requirement Results:
        {requirement_id}={requirement_status}: observed
        Telemetry:
        retry_count={retry_count}
        ambiguity={ambiguity}
        extra_refs=none
        Result Metadata:
        scenario_id={scenario_id}
        iteration={iteration}
        provenance={provenance}
        Evaluation Status:
        evaluation_status={evaluation_status}
        feedback_actions_resolved=no
        learning_capture_complete=no
        """
    )


def t14_parser_fixture(
    report_text: str | None = None,
    *,
    iteration: int = 1,
    attempt: int = 0,
    scenario_id: str = "OOP-TYPE-SCENARIO-01",
) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
    """Create one isolated raw-report parser fixture."""
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    raw = root / f"iteration-{iteration}" / f"attempt-{attempt}" / f"{scenario_id}.md"
    raw.parent.mkdir(parents=True)
    raw.write_text(report_text or t14_report_text(scenario_id, iteration), encoding="utf-8")
    return tmp, raw, raw


def assert_t14_error(test: unittest.TestCase, function: object, code: str) -> None:
    """Assert one fixed T14 error code."""
    with test.assertRaises((evaluator.SkillEvaluatorReportParseError, evaluator.T14EvaluationError)) as raised:
        cast(object, function)()
    test.assertEqual(getattr(raised.exception, "code"), code)


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

        target_globs = {entry.get("target_glob") for entry in evals}
        for required_glob in (
            ".agents/skills/*/SKILL.md",
            "agents/skills/*.md",
            "agents/internal-routines/*.md",
            "agents/workflows/*.md",
            "agents/canonical/*.md",
            ".codex/agents/*.toml",
        ):
            self.assertIn(required_glob, target_globs)

    def test_codex_agent_generic_provenance_is_consumer_static_and_path_free(self) -> None:
        """The generic Codex prompt check owns only static marker/digest provenance."""
        manifest = PROJECT_ROOT / "evidence" / "agent-evals" / "skill_workflow_prompt_eval.toml"
        data = load_toml_document(manifest)
        evals = cast(list[dict[str, object]], data["evals"])
        role_eval = next(entry for entry in evals if entry.get("id") == "all-codex-subagent-prompts")
        checklist = next(
            item
            for item in cast(list[dict[str, object]], role_eval["checklist"])
            if item.get("id") == "CODEX-AGENT-GENERIC-1"
        )

        self.assertEqual(
            set(cast(list[str], checklist["required_regex"])),
            {
                "generated role view: generated_role_view_v1",
                "(?m)^# source canonical digest: [0-9a-f]{64}$",
            },
        )
        self.assertEqual(
            set(cast(list[str], checklist["forbidden_regex"])),
            {
                "agents/skills/",
                "agents/model_profiles\\.toml",
                "tools/agent_tools/",
                "\\.\\./\\.\\./agents/",
                "\\.\\./\\.\\./tools/",
            },
        )

    def test_default_manifest_routes_convention_and_toolcall_eval_coverage(
        self,
    ) -> None:
        """Generic workflows stay structural while owner shims test tool routing."""
        manifest = PROJECT_ROOT / "evidence" / "agent-evals" / "skill_workflow_prompt_eval.toml"
        data = load_toml_document(manifest)
        evals = cast(list[dict[str, object]], data["evals"])
        by_id = {str(entry["id"]): entry for entry in evals}
        workflow_eval = by_id["all-workflow-docs"]
        workflow_check_ids = {
            str(item["id"])
            for item in cast(list[dict[str, object]], workflow_eval["checklist"])
        }

        self.assertEqual(
            workflow_check_ids,
            {"WORKFLOW-GENERIC-1", "WORKFLOW-GENERIC-2"},
        )
        self.assertEqual(
            by_id["agent-orchestration-skill-call-routing"]["target"],
            ".agents/skills/agent-orchestration/SKILL.md",
        )
        self.assertEqual(
            by_id["codex-task-workflow-convention-gate"]["target"],
            ".agents/skills/codex-task-workflow/SKILL.md",
        )
        orchestration_check_ids = {
            str(item["id"])
            for item in cast(
                list[dict[str, object]],
                by_id["agent-orchestration-skill-call-routing"]["checklist"],
            )
        }
        self.assertEqual(
            orchestration_check_ids,
            {
                "ORCH-SHIM-POINTER-1",
                "ORCH-SHIM-TOOLCALL-1",
                "ORCH-SHIM-DISCOVERY-1",
            },
        )
        orchestration_checks = cast(
            list[dict[str, object]],
            by_id["agent-orchestration-skill-call-routing"]["checklist"],
        )
        pointer_check = next(
            item for item in orchestration_checks if item["id"] == "ORCH-SHIM-POINTER-1"
        )
        pointer_required = set(cast(list[str], pointer_check["required_regex"]))
        self.assertTrue(
            {
                "semantic decision-sufficiency record",
                "structured handoff or tool result is sufficient",
                "durable packet reference only for coordination or resumption",
            }.issubset(pointer_required)
        )
        self.assertNotIn("owner-produced `DecisionSufficiencyPacket`", pointer_required)
        for eval_id in (
            "agent-orchestration-skill-call-routing",
            "codex-task-workflow-convention-gate",
        ):
            checklists = cast(list[dict[str, object]], by_id[eval_id]["checklist"])
            self.assertTrue(all(bool(item["critical"]) for item in checklists))

    def test_default_manifest_contains_exact_decision_sufficiency_scenarios(
        self,
    ) -> None:
        """The canonical DSV owner carries the six semantic contract evals."""
        manifest = PROJECT_ROOT / "evidence" / "agent-evals" / "skill_workflow_prompt_eval.toml"
        data = load_toml_document(manifest)
        evals = cast(list[dict[str, object]], data["evals"])
        owner_eval = next(
            entry
            for entry in evals
            if entry.get("target") == "agents/skills/agent-orchestration.md"
        )
        checklist = cast(list[dict[str, object]], owner_eval["checklist"])
        dsv_ids = {
            str(item["id"])
            for item in checklist
            if str(item["id"]).startswith("DSV-")
        }

        self.assertEqual(
            dsv_ids,
            {
                "DSV-ZERO-VALUE-1",
                "DSV-BRANCH-NAMING-1",
                "DSV-SPARK-FAST-PATH-1",
                "DSV-IRRELEVANT-UNKNOWN-POSITIVE-1",
                "DSV-IRRELEVANT-UNKNOWN-NEGATIVE-1",
                "DSV-NO-THRESHOLD-1",
            },
        )
        checks_by_id = {str(item["id"]): item for item in checklist}
        expected_required_patterns = {
            "DSV-ZERO-VALUE-1": {
                "same owner, unit, mechanism, and validation\\s+route",
                "Additional reads, searches, reviews, and checks are justified only\\s+when they can change",
                "do not manufacture a zero-value investigation, packet, or review stage",
            },
            "DSV-BRANCH-NAMING-1": {
                "each unresolved branch that could change the owner, unit, mechanism, or route",
                "changes_next_decision",
            },
            "DSV-SPARK-FAST-PATH-1": {
                "固定 Spark implementation route",
                "parent packet が.*--select-agent-type implementer=spark_worker:<evidence>",
                "one owning review gate",
                "Validation is static/targeted first",
            },
            "DSV-IRRELEVANT-UNKNOWN-POSITIVE-1": {
                "\\\"blocking\\\": false",
                "\\\"serialized_in_decision_packet\\\": true",
                "Unknowns that cannot change the next decision are non-blocking\\s+and may remain in local context",
            },
            "DSV-IRRELEVANT-UNKNOWN-NEGATIVE-1": {
                "Unknowns that cannot change the next decision are non-blocking",
                "Do not convert missing artifact fields, counts, or digests into\\s+a new mandatory gate",
            },
            "DSV-NO-THRESHOLD-1": {
                "\\\"threshold_policy\\\": \\\"none\\\"",
                "No artifact shape, digest, count, or fixed stage sequence is a substitute",
                "no hypothesis-space or read-count form is\\s+required",
            },
        }
        for check_id, expected in expected_required_patterns.items():
            required = set(cast(list[str], checks_by_id[check_id]["required_regex"]))
            self.assertTrue(expected.issubset(required), check_id)
        for check_id in dsv_ids:
            required = set(cast(list[str], checks_by_id[check_id]["required_regex"]))
            self.assertNotIn("h in H", required)
            self.assertNotIn("possible_branches", required)
        self.assertTrue(
            all(
                item["critical"] is True
                for item in checklist
                if str(item["id"]).startswith("DSV-")
            )
        )

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

    def test_default_manifest_uses_stable_code_visualization_omission_oracle_contract(
        self,
    ) -> None:
        """The manifest requires canonical typed omission/readback semantics."""
        manifest = PROJECT_ROOT / "evidence" / "agent-evals" / "skill_workflow_prompt_eval.toml"
        data = load_toml_document(manifest)
        evals = cast(list[dict[str, object]], data["evals"])
        by_id = {str(entry["id"]): entry for entry in evals}
        code_vis_eval = by_id["code-visualization-skill"]
        checklists = cast(list[dict[str, object]], code_vis_eval["checklist"])
        check_by_id = {str(item["id"]): item for item in checklists}
        omission = check_by_id["CODE-VISUALIZATION-4"]
        required = set(cast(list[str], omission["required_regex"]))
        expected_semantics = {
            "literal user scope",
            "source-owner and dependency\\s+closure",
            "VisualizationSourceUniverse",
            "ProjectionCoverageManifest",
            "canonical owner ToolCall",
            "agent_canon\\.visualization\\.coverage",
            "agent_canon\\.visualization\\.arguments\\.coverage\\.v1",
            "mandatory format",
            "final-artifact readback|post-format readback",
            "source_counts",
            "rendered_counts",
            "readback_counts",
            "coverage_digest",
            "final_token_readback",
            "clustering",
            "zoom",
            "filtering",
            "view[- ]only|reversible view[- ]state",
            "typed renderer-capacity blocker|typed renderer-capacity rejection",
        }

        self.assertIs(omission["critical"], True)
        self.assertEqual(required, expected_semantics)

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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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

    def test_target_glob_reads_one_canonical_owner_for_each_shim(self) -> None:
        """Globbed thin shims can share one canonical owner in checklist text."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prompt_dir = root / "prompts"
            prompt_dir.mkdir()
            (prompt_dir / "a.md").write_text("shim\n", encoding="utf-8")
            (root / "canonical.md").write_text("canonical-marker\n", encoding="utf-8")
            manifest = root / "eval.toml"
            manifest.write_text(
                textwrap.dedent(
                    """
                    version = 1

                    [[evals]]
                    id = "glob-canonical"
                    target_glob = "prompts/*.md"
                    expected_count = 1
                    canonical_target = "canonical.md"
                    kind = "skill"
                    description = "sample"

                    [[evals.checklist]]
                    id = "GC1"
                    critical = true
                    description = "requires canonical owner"
                    required_regex = ["canonical-marker"]
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            result = run_eval("--root", str(root), "--manifest", "eval.toml")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("EVAL_CHECKS_TOTAL=1", result.stdout)

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


class T14EvaluatorContractTest(unittest.TestCase):
    """Verify the parent-owned T14 parser and accumulator contract."""

    requirement_ids = ("R101",)

    def setUp(self) -> None:
        """Bind each T14 test to one signed public session."""
        self._t14_previous_cwd = Path.cwd()
        self._t14_previous_environment = dict(os.environ)
        self._t14_invocation_script = (
            PROJECT_ROOT / ".agent-canon" / "tmp" / "t14-session-runner.py"
        )
        self._t14_invocation_script.parent.mkdir(parents=True, exist_ok=True)
        (PROJECT_ROOT / ".agent-canon" / "validation").mkdir(
            parents=True, exist_ok=True
        )
        self._t14_invocation_script.write_text(
            "# t14 signed-session fixture runner\n", encoding="utf-8"
        )
        os.chdir(PROJECT_ROOT)
        self._t14_session_context = public_session(
            invocation_script=self._t14_invocation_script,
            purpose="t14-test-session",
        )
        self._t14_session = self._t14_session_context.__enter__()
        os.environ.clear()
        os.environ.update(
            session_environment(self._t14_session, self._t14_previous_environment)
        )
        self.addCleanup(self._close_t14_session)

    def _close_t14_session(self) -> None:
        """Restore the process after the signed T14 session closes."""
        try:
            os.environ.clear()
            os.environ.update(self._t14_previous_environment)
        finally:
            try:
                self._t14_session_context.__exit__(None, None, None)
            finally:
                os.chdir(self._t14_previous_cwd)
                self._t14_invocation_script.unlink(missing_ok=True)

    def parse(self, raw: Path, expected: Path, *, iteration: int = 1, attempt: int = 0):
        return evaluator.parse_skill_evaluator_report(
            raw,
            expected,
            self.requirement_ids,
            "OOP-TYPE-SCENARIO-01",
            iteration,
            attempt,
        )

    def test_parse_valid_five_section_report(self) -> None:
        tmp, raw, expected = t14_parser_fixture()
        with tmp:
            report = self.parse(raw, expected)
        self.assertEqual(report.requirement_results[0][:2], ("R101", "pass"))

    def test_parse_skill_evaluator_report_rejects_invalid_utf8(self) -> None:
        tmp, raw, expected = t14_parser_fixture()
        with tmp:
            raw.write_bytes(b"\xff")
            assert_t14_error(self, lambda: self.parse(raw, expected), "t14-report-invalid-utf8")

    def test_parse_skill_evaluator_report_rejects_path_mismatch(self) -> None:
        tmp, raw, _ = t14_parser_fixture()
        with tmp:
            assert_t14_error(
                self,
                lambda: self.parse(raw, raw.with_name("other.md")),
                "t14-report-path-mismatch",
            )

    def test_parse_skill_evaluator_report_rejects_iteration_path_mismatch(self) -> None:
        tmp, raw, expected = t14_parser_fixture(iteration=2)
        with tmp:
            assert_t14_error(
                self,
                lambda: self.parse(raw, expected, iteration=1),
                "t14-report-iteration-path-mismatch",
            )

    def test_parse_skill_evaluator_report_rejects_attempt_path_mismatch(self) -> None:
        tmp, raw, expected = t14_parser_fixture(attempt=1)
        with tmp:
            assert_t14_error(
                self,
                lambda: self.parse(raw, expected, attempt=0),
                "t14-report-attempt-path-mismatch",
            )

    def test_parse_skill_evaluator_report_rejects_heading_error(self) -> None:
        tmp, raw, expected = t14_parser_fixture(t14_report_text().replace("Output:", "Output"))
        with tmp:
            assert_t14_error(self, lambda: self.parse(raw, expected), "t14-report-heading")

    def test_parse_skill_evaluator_report_rejects_field_order(self) -> None:
        text = t14_report_text().replace(
            "command=python3 tools/agent_tools/route.py --capability oop_type_design\nartifacts=none",
            "artifacts=none\ncommand=python3 tools/agent_tools/route.py --capability oop_type_design",
        )
        tmp, raw, expected = t14_parser_fixture(text)
        with tmp:
            assert_t14_error(self, lambda: self.parse(raw, expected), "t14-report-field-order")

    def test_parse_skill_evaluator_report_rejects_missing_field(self) -> None:
        tmp, raw, expected = t14_parser_fixture(t14_report_text().replace("route=explicit capability\n", ""))
        with tmp:
            assert_t14_error(self, lambda: self.parse(raw, expected), "t14-report-missing-field")

    def test_parse_skill_evaluator_report_rejects_duplicate_field(self) -> None:
        tmp, raw, expected = t14_parser_fixture(t14_report_text().replace("artifacts=none\n", "artifacts=none\nartifacts=none\n"))
        with tmp:
            assert_t14_error(self, lambda: self.parse(raw, expected), "t14-report-duplicate-field")

    def test_parse_skill_evaluator_report_rejects_unknown_field(self) -> None:
        tmp, raw, expected = t14_parser_fixture(t14_report_text().replace("command=", "unknown=x\ncommand=", 1))
        with tmp:
            assert_t14_error(self, lambda: self.parse(raw, expected), "t14-report-unknown-field")

    def test_parse_skill_evaluator_report_rejects_requirement_id_errors(self) -> None:
        tmp, raw, expected = t14_parser_fixture(t14_report_text().replace("R101=pass", "R999=pass"))
        with tmp:
            assert_t14_error(self, lambda: self.parse(raw, expected), "t14-report-requirement-id")

    def test_parse_skill_evaluator_report_rejects_metadata_error(self) -> None:
        tmp, raw, expected = t14_parser_fixture(t14_report_text().replace("scenario_id=OOP-TYPE-SCENARIO-01", "scenario_id=wrong"))
        with tmp:
            assert_t14_error(self, lambda: self.parse(raw, expected), "t14-report-metadata")

    def test_parse_skill_evaluator_report_rejects_invalid_enum(self) -> None:
        tmp, raw, expected = t14_parser_fixture(t14_report_text(ambiguity="token").replace("ambiguity=token", "ambiguity=maybe"))
        with tmp:
            assert_t14_error(self, lambda: self.parse(raw, expected), "t14-report-enum")

    def test_parse_skill_evaluator_report_rejects_lexical_value(self) -> None:
        tmp, raw, expected = t14_parser_fixture(t14_report_text().replace("artifacts=none", "artifacts=none="))
        with tmp:
            assert_t14_error(self, lambda: self.parse(raw, expected), "t14-report-lexical-value")

    def test_parse_skill_evaluator_report_rejects_free_text(self) -> None:
        tmp, raw, expected = t14_parser_fixture(t14_report_text().replace("Requirement Results:\n", "free text\nRequirement Results:\n"))
        with tmp:
            assert_t14_error(self, lambda: self.parse(raw, expected), "t14-report-free-text")

    def test_compute_t14_packet_digest_normalizes_canonical_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet = Path(tmp_dir) / "packet.md"
            packet.write_bytes(b"packet\r\n")
            expected = "sha256:" + __import__("hashlib").sha256(b"packet\n").hexdigest()
            self.assertEqual(evaluator.compute_t14_packet_digest(packet), expected)

    def record_fixture(self, *, run_id: str = "test-run", attempt: int = 0, packet_digest: str | None = None):
        configured_parent = os.environ.get("AGENT_CANON_SIDE_EFFECT_PARENT_ROOT", "").strip()
        if not configured_parent:
            configured_parent = str(PROJECT_ROOT)
        parent_root = Path(configured_parent)
        fixture_parent = parent_root / ".agent-canon" / "validation" / "t14-fixtures"
        fixture_parent.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=fixture_parent)
        root = Path(tmp.name)
        packet = root / "packet.md"
        packet.write_text("packet\n", encoding="utf-8")
        report_bytes = t14_report_text().encode("utf-8")
        raw = root / "reports" / "agents" / run_id / "evaluator_artifacts" / "iteration-1" / f"attempt-{attempt}" / "OOP-TYPE-SCENARIO-01.md"
        return_artifact = parent_root / ".agent-canon" / "tmp" / "agentcanon-type-design-workspaces" / run_id / "iteration-1" / f"attempt-{attempt}" / "OOP-TYPE-SCENARIO-01" / "evaluator_return.bin"
        return_artifact.parent.mkdir(parents=True, exist_ok=True)
        return_artifact.write_bytes(report_bytes)
        boundary = ParentRootSideEffectBoundary()
        attestation = self._t14_session.attestation
        return_root = parent_root / ".agent-canon" / "tmp" / "agentcanon-type-design-workspaces" / run_id

        def cleanup_return_artifact() -> None:
            if return_root.exists():
                receipt = boundary.resolve_parent_owned_path(
                    attestation, return_root, "t14-test-cleanup", create=False
                )
                boundary.remove_parent_owned_tree(
                    attestation, receipt, "t14-test-cleanup"
                )

        self.addCleanup(cleanup_return_artifact)
        parent = root / "reports" / "agents" / run_id / "agent_evaluation.md"
        digest = packet_digest or evaluator.compute_t14_packet_digest(packet)
        return tmp, report_bytes, raw, parent, packet, digest, return_artifact

    def test_record_t14_evaluation_rejects_packet_digest_mismatch(self) -> None:
        fixture = self.record_fixture(run_id="digest-mismatch")
        with fixture[0]:
            assert_t14_error(
                self,
                lambda: evaluator.record_t14_evaluation("digest-mismatch", fixture[1], fixture[2], fixture[2], self.requirement_ids, "OOP-TYPE-SCENARIO-01", 1, 0, fixture[4], "sha256:" + "0" * 64, fixture[3]),
                "t14-packet-digest-mismatch",
            )

    def test_record_t14_evaluation_requires_parent_receipt_before_read(self) -> None:
        """T14 establishes one parent capability before any receipt-bound read."""
        fixture = self.record_fixture(run_id="receipt-order")
        with fixture[0]:
            capability_established = False
            original_capability = evaluator._parent_capability

            def observe_capability(purpose: str):
                nonlocal capability_established
                result = original_capability(purpose)
                capability_established = True
                return result

            original_read = ParentRootSideEffectBoundary.read_parent_owned_file

            def observe_read(boundary, receipt):
                self.assertTrue(capability_established)
                return original_read(boundary, receipt)

            with mock.patch.object(
                evaluator, "_parent_capability", side_effect=observe_capability
            ), mock.patch.object(
                ParentRootSideEffectBoundary,
                "read_parent_owned_file",
                observe_read,
            ):
                report = evaluator.record_t14_evaluation(
                    "receipt-order",
                    fixture[1],
                    fixture[2],
                    fixture[2],
                    self.requirement_ids,
                    "OOP-TYPE-SCENARIO-01",
                    1,
                    0,
                    fixture[4],
                    fixture[5],
                    fixture[3],
                )
            self.assertEqual(report.scenario_id, "OOP-TYPE-SCENARIO-01")

    def test_record_t14_evaluation_preserves_verbatim_raw_bytes(self) -> None:
        fixture = self.record_fixture(run_id="verbatim")
        with fixture[0]:
            report = evaluator.record_t14_evaluation("verbatim", fixture[1], fixture[2], fixture[2], self.requirement_ids, "OOP-TYPE-SCENARIO-01", 1, 0, fixture[4], fixture[5], fixture[3])
            self.assertEqual(fixture[2].read_bytes(), fixture[1])
            self.assertEqual(report.raw_report_path, fixture[2])

    def test_record_t14_evaluation_rejects_raw_path_collision(self) -> None:
        fixture = self.record_fixture(run_id="collision")
        with fixture[0]:
            fixture[2].parent.mkdir(parents=True, exist_ok=True)
            fixture[2].write_bytes(b"existing")
            assert_t14_error(self, lambda: evaluator.record_t14_evaluation("collision", fixture[1], fixture[2], fixture[2], self.requirement_ids, "OOP-TYPE-SCENARIO-01", 1, 0, fixture[4], fixture[5], fixture[3]), "t14-raw-report-exists")

    def test_record_t14_evaluation_uses_attempt_path_for_malformed_retry(self) -> None:
        fixture = self.record_fixture(run_id="malformed-retry", attempt=0)
        with fixture[0]:
            invalid = b"malformed\n"
            fixture[2].parent.mkdir(parents=True, exist_ok=True)
            fixture[2].write_bytes(invalid)
            with self.assertRaises(evaluator.SkillEvaluatorReportParseError):
                evaluator.parse_skill_evaluator_report(fixture[2], fixture[2], self.requirement_ids, "OOP-TYPE-SCENARIO-01", 1, 0)
            second = self.record_fixture(run_id="malformed-retry", attempt=1)
            with second[0]:
                prior = second[2].parent.parent / "attempt-0" / second[2].name
                prior.parent.mkdir(parents=True, exist_ok=True)
                prior.write_bytes(invalid)
                report = evaluator.record_t14_evaluation("malformed-retry", second[1], second[2], second[2], self.requirement_ids, "OOP-TYPE-SCENARIO-01", 1, 1, second[4], second[5], second[3])
                self.assertEqual(report.attempt, 1)

    def test_record_t14_evaluation_rejects_attempt_order(self) -> None:
        fixture = self.record_fixture(run_id="attempt-order", attempt=1)
        with fixture[0]:
            assert_t14_error(self, lambda: evaluator.record_t14_evaluation("attempt-order", fixture[1], fixture[2], fixture[2], self.requirement_ids, "OOP-TYPE-SCENARIO-01", 1, 1, fixture[4], fixture[5], fixture[3]), "t14-attempt-order")

    def test_record_t14_evaluation_rejects_iteration_order(self) -> None:
        fixture = self.record_fixture(run_id="iteration-order")
        with fixture[0]:
            assert_t14_error(self, lambda: evaluator.record_t14_evaluation("iteration-order", fixture[1], fixture[2], fixture[2], self.requirement_ids, "OOP-TYPE-SCENARIO-01", 2, 0, fixture[4], fixture[5], fixture[3]), "t14-iteration-order")

    def test_record_t14_evaluation_rejects_duplicate_scenario(self) -> None:
        fixture = self.record_fixture(run_id="duplicate-scenario")
        with fixture[0]:
            evaluator.record_t14_evaluation("duplicate-scenario", fixture[1], fixture[2], fixture[2], self.requirement_ids, "OOP-TYPE-SCENARIO-01", 1, 0, fixture[4], fixture[5], fixture[3])
            second_raw = fixture[2].parent.parent / "attempt-1" / fixture[2].name
            second_raw.parent.mkdir(parents=True, exist_ok=True)
            second_artifact = PROJECT_ROOT / ".agent-canon" / "tmp" / "agentcanon-type-design-workspaces" / "duplicate-scenario" / "iteration-1" / "attempt-1" / "OOP-TYPE-SCENARIO-01" / "evaluator_return.bin"
            second_artifact.parent.mkdir(parents=True, exist_ok=True)
            second_artifact.write_bytes(fixture[1])
            assert_t14_error(self, lambda: evaluator.record_t14_evaluation("duplicate-scenario", fixture[1], second_raw, second_raw, self.requirement_ids, "OOP-TYPE-SCENARIO-01", 1, 1, fixture[4], fixture[5], fixture[3]), "t14-duplicate-scenario")

    def test_record_t14_evaluation_rejects_unexpected_iteration(self) -> None:
        fixture = self.record_fixture(run_id="unexpected-iteration")
        with fixture[0]:
            assert_t14_error(self, lambda: evaluator.record_t14_evaluation("unexpected-iteration", fixture[1], fixture[2], fixture[2], self.requirement_ids, "OOP-TYPE-SCENARIO-01", 3, 0, fixture[4], fixture[5], fixture[3]), "t14-unexpected-iteration")

    def test_record_t14_evaluation_rejects_retry_count_mismatch(self) -> None:
        fixture = self.record_fixture(run_id="retry-mismatch")
        with fixture[0]:
            fixture[3].parent.mkdir(parents=True, exist_ok=True)
            fixture[3].write_text(evaluator._T14_PARENT_HEADER.format(run_id="retry-mismatch") + "\n## Scenario OOP-TYPE-SCENARIO-01\nretry_count=4\nmalformed_attempts=1\nevaluator_retry_count=1\n", encoding="utf-8")
            assert_t14_error(self, lambda: evaluator.record_t14_evaluation("retry-mismatch", fixture[1], fixture[2], fixture[2], self.requirement_ids, "OOP-TYPE-SCENARIO-01", 1, 0, fixture[4], fixture[5], fixture[3]), "t14-retry-count-mismatch")

    def report_set(
        self,
        iteration: int,
        *,
        attempt: int = 0,
        retry_count: int = 0,
        requirement_status: str = "pass",
        ambiguity: str = "none",
        evaluation_status: str = "pass",
        provenance: str = "fresh",
    ) -> tuple[evaluator.SkillEvaluatorReport, ...]:
        """Build the fixed three-scenario parent observation tuple."""
        return tuple(
            evaluator.SkillEvaluatorReport(
                raw_report_path=Path(f"scenario-{index}.md"),
                command="command",
                artifacts=(),
                authority="parent",
                route="route",
                retry_count=retry_count,
                ambiguity=ambiguity,
                extra_refs=(),
                scenario_id=scenario_id,
                iteration=iteration,
                attempt=attempt,
                provenance=provenance,
                evaluation_status=evaluation_status,
                feedback_actions_resolved="no",
                learning_capture_complete="no",
                requirement_results=(("R101", requirement_status, "evidence"),),
            )
            for index, scenario_id in enumerate(evaluator._T14_SCENARIOS, 1)
        )

    def summary_parent(self, run_id: str = "summary") -> tuple[tempfile.TemporaryDirectory[str], Path]:
        """Create a parent evaluation with the exact initial header."""
        tmp = tempfile.TemporaryDirectory(
            dir=PROJECT_ROOT / ".agent-canon" / "validation"
        )
        parent = Path(tmp.name) / "reports" / "agents" / run_id / "agent_evaluation.md"
        parent.parent.mkdir(parents=True)
        parent.write_text(evaluator._T14_PARENT_HEADER.format(run_id=run_id) + "\n", encoding="utf-8")
        return tmp, parent

    def test_append_t14_iteration_summary_records_blocked_incomplete_iteration(self) -> None:
        tmp, parent = self.summary_parent("blocked-incomplete")
        with tmp:
            evaluator.append_t14_iteration_summary(parent, 1, (), {}, Decimal("50"), True, Decimal("0"))
            text = parent.read_text(encoding="utf-8")
        self.assertIn("convergence=blocked", text)
        self.assertIn("convergence_reason=t14-incomplete-iteration", text)

    def test_append_t14_iteration_summary_records_converged(self) -> None:
        tmp, parent = self.summary_parent("converged")
        with tmp:
            reports = self.report_set(1)
            evaluator.append_t14_iteration_summary(parent, 1, reports, {scenario: True for scenario in evaluator._T14_SCENARIOS}, Decimal("98"), True, Decimal("1.25"))
            text = parent.read_text(encoding="utf-8")
        self.assertIn("convergence=converged", text)
        self.assertIn("parent_score_percent=98.00", text)

    def test_append_t14_iteration_summary_records_failed_requirement(self) -> None:
        tmp, parent = self.summary_parent("failed-requirement")
        with tmp:
            evaluator.append_t14_iteration_summary(parent, 1, self.report_set(1, requirement_status="fail"), {scenario: True for scenario in evaluator._T14_SCENARIOS}, Decimal("50"), True, Decimal("0"))
            text = parent.read_text(encoding="utf-8")
        self.assertIn("convergence=not_converged", text)
        self.assertIn("convergence_reason=t14-report-failure", text)

    def test_append_t14_iteration_summary_records_ambiguity(self) -> None:
        tmp, parent = self.summary_parent("ambiguity")
        with tmp:
            evaluator.append_t14_iteration_summary(parent, 1, self.report_set(1, ambiguity="token"), {scenario: True for scenario in evaluator._T14_SCENARIOS}, Decimal("50"), True, Decimal("0"))
            text = parent.read_text(encoding="utf-8")
        self.assertIn("convergence_reason=t14-ambiguity", text)

    def test_append_t14_iteration_summary_records_critical_failure(self) -> None:
        tmp, parent = self.summary_parent("critical-failure")
        with tmp:
            evaluator.append_t14_iteration_summary(parent, 1, self.report_set(1), {scenario: True for scenario in evaluator._T14_SCENARIOS}, Decimal("50"), False, Decimal("0"))
            text = parent.read_text(encoding="utf-8")
        self.assertIn("convergence_reason=t14-critical-failure", text)

    def test_append_t14_iteration_summary_records_graph_failure(self) -> None:
        tmp, parent = self.summary_parent("graph-failure")
        with tmp:
            graph = {scenario: True for scenario in evaluator._T14_SCENARIOS}
            graph[evaluator._T14_SCENARIOS[1]] = False
            evaluator.append_t14_iteration_summary(parent, 1, self.report_set(1), graph, Decimal("50"), True, Decimal("0"))
            text = parent.read_text(encoding="utf-8")
        self.assertIn("convergence_reason=t14-graph-failure", text)

    def test_append_t14_iteration_summary_records_blocked_score_out_of_range(self) -> None:
        tmp, parent = self.summary_parent("blocked-score")
        with tmp:
            evaluator.append_t14_iteration_summary(parent, 1, self.report_set(1), {scenario: True for scenario in evaluator._T14_SCENARIOS}, Decimal("101"), True, Decimal("0"))
            text = parent.read_text(encoding="utf-8")
        self.assertIn("convergence=blocked", text)
        self.assertIn("convergence_reason=t14-score-out-of-range", text)

    def test_append_t14_iteration_summary_quantizes_decimal_scores(self) -> None:
        tmp, parent = self.summary_parent("quantized")
        with tmp:
            evaluator.append_t14_iteration_summary(parent, 1, self.report_set(1), {scenario: True for scenario in evaluator._T14_SCENARIOS}, Decimal("12.345"), True, Decimal("1.234"))
            text = parent.read_text(encoding="utf-8")
        self.assertIn("parent_score_percent=12.35", text)
        self.assertIn("holdout_gap_percent=1.23", text)

    def test_append_t14_iteration_summary_rejects_invalid_iteration(self) -> None:
        tmp, parent = self.summary_parent("invalid-iteration")
        with tmp:
            assert_t14_error(self, lambda: evaluator.append_t14_iteration_summary(parent, 0, (), {}, Decimal("0"), True, Decimal("0")), "t14-iteration-order")

    def test_append_t14_iteration_summary_uses_locked_parent_handle(self) -> None:
        """Summary append reads and writes through one parent-owned handle."""
        fixture = self.record_fixture(run_id="append-parent-handle")
        with fixture[0]:
            fixture[3].parent.mkdir(parents=True, exist_ok=True)
            fixture[3].write_bytes(
                evaluator._T14_PARENT_HEADER.format(run_id="append-parent-handle").encode()
                + b"\n"
            )
            with mock.patch.object(
                Path, "read_text", side_effect=AssertionError("pathname read")
            ):
                evaluator.append_t14_iteration_summary(
                    fixture[3], 1, (), {}, Decimal("50"), True, Decimal("0")
                )
            self.assertIn(
                b"convergence=blocked", fixture[3].read_bytes()
            )

    def finalize_with_summaries(
        self,
        run_id: str,
        *,
        attempt_by_iteration: tuple[int, int] = (0, 0),
        retry_count: int = 0,
        holdout_gap: tuple[Decimal, Decimal] = (Decimal("1"), Decimal("1")),
        requirement_status: str = "pass",
        ambiguity: str = "none",
        critical: bool = True,
    ) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        """Create both iteration summaries for finalization tests."""
        tmp, parent = self.summary_parent(run_id)
        for index, iteration in enumerate((1, 2)):
            evaluator.append_t14_iteration_summary(
                parent,
                iteration,
                self.report_set(iteration, attempt=attempt_by_iteration[index], retry_count=retry_count, requirement_status=requirement_status, ambiguity=ambiguity),
                {scenario: True for scenario in evaluator._T14_SCENARIOS},
                Decimal("90"),
                critical,
                holdout_gap[index],
            )
        return tmp, parent

    def test_finalize_t14_evaluation_rejects_retry_mismatch(self) -> None:
        tmp, parent = self.finalize_with_summaries("final-retry-mismatch", attempt_by_iteration=(0, 1))
        with tmp:
            evaluator.finalize_t14_evaluation(parent)
            self.assertIn("failure_code=t14-retry-mismatch", parent.read_text(encoding="utf-8"))

    def test_finalize_t14_evaluation_rejects_nonzero_retry(self) -> None:
        tmp, parent = self.finalize_with_summaries("final-nonzero-retry", retry_count=1)
        with tmp:
            evaluator.finalize_t14_evaluation(parent)
            self.assertIn("failure_code=t14-nonzero-retry", parent.read_text(encoding="utf-8"))

    def test_finalize_t14_evaluation_rejects_holdout_gap(self) -> None:
        tmp, parent = self.finalize_with_summaries("final-holdout", holdout_gap=(Decimal("15"), Decimal("1")))
        with tmp:
            evaluator.finalize_t14_evaluation(parent)
            self.assertIn("failure_code=t14-holdout-gap", parent.read_text(encoding="utf-8"))

    def test_finalize_t14_evaluation_rejects_duplicate_summary(self) -> None:
        tmp, parent = self.summary_parent("final-duplicate")
        with tmp:
            evaluator.finalize_t14_evaluation(parent)
            assert_t14_error(self, lambda: evaluator.finalize_t14_evaluation(parent), "t14-duplicate-summary")

    def test_finalize_t14_evaluation_records_not_converged_reason(self) -> None:
        tmp, parent = self.finalize_with_summaries("final-not-converged", requirement_status="fail")
        with tmp:
            evaluator.finalize_t14_evaluation(parent)
            self.assertIn("failure_code=t14-iteration-not-converged", parent.read_text(encoding="utf-8"))

    def test_finalize_t14_evaluation_records_score_out_of_range(self) -> None:
        tmp, parent = self.summary_parent("final-score")
        with tmp:
            evaluator.append_t14_iteration_summary(parent, 1, (), {}, Decimal("101"), True, Decimal("0"))
            evaluator.append_t14_iteration_summary(parent, 2, (), {}, Decimal("101"), True, Decimal("0"))
            evaluator.finalize_t14_evaluation(parent)
            self.assertIn("failure_code=t14-score-out-of-range", parent.read_text(encoding="utf-8"))

    def test_finalize_t14_evaluation_uses_locked_parent_handle(self) -> None:
        """Finalization reads and writes through one parent-owned handle."""
        fixture = self.record_fixture(run_id="finalize-parent-handle")
        with fixture[0]:
            fixture[3].parent.mkdir(parents=True, exist_ok=True)
            fixture[3].write_bytes(
                evaluator._T14_PARENT_HEADER.format(run_id="finalize-parent-handle").encode()
                + b"\n"
            )
            for iteration in (1, 2):
                evaluator.append_t14_iteration_summary(
                    fixture[3],
                    iteration,
                    self.report_set(iteration),
                    {scenario: True for scenario in evaluator._T14_SCENARIOS},
                    Decimal("90"),
                    True,
                    Decimal("1"),
                )
            with mock.patch.object(
                Path, "read_text", side_effect=AssertionError("pathname read")
            ):
                evaluator.finalize_t14_evaluation(fixture[3])
            self.assertIn(b"## Parent Summary", fixture[3].read_bytes())


if __name__ == "__main__":
    unittest.main()
