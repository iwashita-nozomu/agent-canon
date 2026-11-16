# @dependency-start
# contract test
# responsibility Tests Codex agent role eval automation.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/codex_agent_role_eval/mod.rs native producer
# upstream design ../../eval/definitions/README.md role eval contract
# upstream reference ../fixtures/model_profiles/README.md reviewed role hash provenance
# @dependency-end
"""Tests for Codex agent role eval automation."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "bin" / "agent-canon"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))


FIRST_RUNTIME_TOKENS = 100
FIRST_RUNTIME_LATENCY_MS = 25
SECOND_RUNTIME_TOKENS = 50
SECOND_RUNTIME_LATENCY_MS = 15
EXPECTED_RUNTIME_TOKENS = FIRST_RUNTIME_TOKENS + SECOND_RUNTIME_TOKENS
EXPECTED_LIVE_ROLE_METADATA = {
    "artifact_reviewer": {
        "name": "artifact_reviewer",
        "description": "Read-only reviewer for code, scripts, raw results, environment capture, and artifact-readiness.",
        "nickname_candidates": ["artifact_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "benchmark_reviewer": {
        "name": "benchmark_reviewer",
        "description": "Read-only reviewer for fairness, confounders, and benchmark anti-patterns.",
        "nickname_candidates": ["benchmark_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "citation_evidence_reviewer": {
        "name": "citation_evidence_reviewer",
        "description": "Read-only reviewer for paper claims, citations, figures, tables, and evidence traceability.",
        "nickname_candidates": ["citation_evidence_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "cpp_reviewer": {
        "name": "cpp_reviewer",
        "description": "Read-only reviewer for C and C++ diffs, build/test evidence, ABI-boundary changes, and native-code regressions.",
        "nickname_candidates": ["cpp_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "detailed_design_reviewer": {
        "name": "detailed_design_reviewer",
        "description": "Read-only reviewer for detailed design docs, implementation readiness, side-effect mapping, reuse-first discipline, and style continuity.",
        "nickname_candidates": ["detailed_design_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "detailed_designer": {
        "name": "detailed_designer",
        "description": "Detailed-design authoring agent for writing implementation-ready design docs with reuse-first, side-effect mapping, and style-continuity guidance.",
        "nickname_candidates": ["detailed_designer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "diff_triage_reviewer": {
        "name": "diff_triage_reviewer",
        "description": "Read-only reviewer for bounded diffs before escalation to broad review.",
        "nickname_candidates": ["diff_triage_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "docs_workflow_steward": {
        "name": "docs_workflow_steward",
        "description": "Docs and workflow steward for canonical instructions, notes, and agent workflows.",
        "nickname_candidates": ["docs_workflow_steward"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "document_flow_reviewer": {
        "name": "document_flow_reviewer",
        "description": "Read-only reviewer for top-down document coherence, section order, term introduction order, and first-reader comprehension.",
        "nickname_candidates": ["document_flow_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "execution_planner": {
        "name": "execution_planner",
        "description": "Execution-planning agent for stage order, subagent assignment, validation sequence, and rollback-aware task plans.",
        "nickname_candidates": ["execution_planner"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "experiment_runner": {
        "name": "experiment_runner",
        "description": "Execution-only agent for running bounded experiments and summarizing logs.",
        "nickname_candidates": ["experiment_runner"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "explorer": {
        "name": "explorer",
        "description": "Read-only agent for tracing code paths, docs, and workflow state.",
        "nickname_candidates": ["explorer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "fair_data_reviewer": {
        "name": "fair_data_reviewer",
        "description": "Read-only reviewer for metadata quality, naming, reuse, and FAIR-style data organization.",
        "nickname_candidates": ["fair_data_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "literature_researcher": {
        "name": "literature_researcher",
        "description": "Read-only agent for paper search, prior-art mapping, and contradictory-source hunting.",
        "nickname_candidates": ["literature_researcher"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "logic_gap_reviewer": {
        "name": "logic_gap_reviewer",
        "description": "Read-only reviewer for academic-argument continuity, claim-to-evidence links, hidden assumptions, and unsupported inferential jumps.",
        "nickname_candidates": ["logic_gap_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "long_form_writer": {
        "name": "long_form_writer",
        "description": "Long-form document author for README, workflow, guide, migration, and other reader-facing documents that need roadmap-first drafting.",
        "nickname_candidates": ["long_form_writer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "manager_reviewer": {
        "name": "manager_reviewer",
        "description": "Read-only requirements reviewer for scope, source buckets, accumulated-context resolution, and escalation discipline.",
        "nickname_candidates": ["manager_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "ml_science_reviewer": {
        "name": "ml_science_reviewer",
        "description": "Read-only reviewer for assumptions, limitations, uncertainty, and reader-facing scientific reporting.",
        "nickname_candidates": ["ml_science_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "notation_definition_reviewer": {
        "name": "notation_definition_reviewer",
        "description": "Read-only reviewer for symbol, abbreviation, terminology, unit, and definition-before-use discipline in academic documents.",
        "nickname_candidates": ["notation_definition_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "oop_readability_reviewer": {
        "name": "oop_readability_reviewer",
        "description": "Read-only reviewer that documents mechanical OOP readability reports without changing their verdicts.",
        "nickname_candidates": ["oop_readability_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "plan_reviewer": {
        "name": "plan_reviewer",
        "description": "Read-only reviewer for execution plans, stage order, reviewer separation, validation sequencing, and rollback readiness.",
        "nickname_candidates": ["plan_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "project_reviewer": {
        "name": "project_reviewer",
        "description": "Read-only reviewer for repo-wide inventory, workflow health, and tooling health.",
        "nickname_candidates": ["project_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "prompt_config_reviewer": {
        "name": "prompt_config_reviewer",
        "description": "Read-only reviewer for prompt, routing, and subagent-config drift.",
        "nickname_candidates": ["prompt_config_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "python_reviewer": {
        "name": "python_reviewer",
        "description": "Read-only reviewer for Python diffs, type boundaries, and parent-selected validation evidence.",
        "nickname_candidates": ["python_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "report_reviewer": {
        "name": "report_reviewer",
        "description": "Read-only reviewer for experiment reports and evidence traceability.",
        "nickname_candidates": ["report_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "reproducibility_reviewer": {
        "name": "reproducibility_reviewer",
        "description": "Read-only reviewer for provenance, seeds, commands, environments, and rerunability.",
        "nickname_candidates": ["reproducibility_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "requirements_organizer": {
        "name": "requirements_organizer",
        "description": "Requirements-organizing agent for turning user intent and local precedent into concrete scope, acceptance criteria, and reuse targets.",
        "nickname_candidates": ["requirements_organizer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "reviewer": {
        "name": "reviewer",
        "description": "Read-only review agent for diffs, regressions, and documentation alignment.",
        "nickname_candidates": ["reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "scientific_computing_reviewer": {
        "name": "scientific_computing_reviewer",
        "description": "Read-only reviewer for incremental change, testing, automation, and prototype discipline in research code.",
        "nickname_candidates": ["scientific_computing_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "ship_reviewer": {
        "name": "ship_reviewer",
        "description": "High-assurance read-only reviewer for final clause coverage and release readiness.",
        "nickname_candidates": ["ship_reviewer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "xhigh",
    },
    "skill_evaluator": {
        "name": "skill_evaluator",
        "description": "Fresh read-only evaluator for explicit empirical skill scenarios.",
        "nickname_candidates": ["skill_evaluator"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "medium",
    },
    "spark_worker": {
        "name": "spark_worker",
        "description": "Low-latency implementation agent for bounded code, docs, tests, or mechanical cleanup slices derived from the Abstract Design Frame and design trace.",
        "nickname_candidates": ["spark_worker"],
        "sandbox_mode": "workspace-write",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "low",
    },
    "terra": {
        "name": "terra",
        "description": "Conditional read-only cross-cutting specialist for owner closure, context reconstruction, and adversarial contradiction validation.",
        "nickname_candidates": ["terra"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-astra",
        "model_reasoning_effort": "high",
    },
    "test_designer": {
        "name": "test_designer",
        "description": "Read-only agent for post-implementation static analysis when an explicit unresolved oracle, specification, regression, or failure-mode risk remains beyond existing validation.",
        "nickname_candidates": ["test_designer"],
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "high",
    },
    "worker": {
        "name": "worker",
        "description": "Implementation agent for bounded code, docs, or test changes.",
        "nickname_candidates": ["worker"],
        "sandbox_mode": "workspace-write",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "xhigh",
    },
    "integration_executor": {
        "name": "integration_executor",
        "description": "Workspace-write child for candidate branch merge, conflict resolution, and integration readback.",
        "nickname_candidates": ["integration_executor"],
        "sandbox_mode": "workspace-write",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "xhigh",
    },
    "publisher": {
        "name": "publisher",
        "description": "Workspace-write child for authorized Issue/PR publication and remote readback.",
        "nickname_candidates": ["publisher"],
        "sandbox_mode": "workspace-write",
        "approval_policy": "never",
        "model": "gpt-6-luna",
        "model_reasoning_effort": "xhigh",
    },
}

EXPECTED_STATIC_ROLE_VIEW_SHA256 = {
    "artifact_reviewer": "a0419cd6054db1c14c869438c02f107863eea4f06d84ccbc99f905358da72506",
    "benchmark_reviewer": "575eb79b1a82e48aa342aedf436fc2c28ec7ab5b14e61547b6ef1cd7971dd263",
    "citation_evidence_reviewer": "834e8c5712bffcf1fabf1701de2f2c87bd4abf75f77d1ba851a5f92c796c4619",
    "cpp_reviewer": "2d29a34a7a81507075c6518f498e277d32693870ad6d8854de34a71fa92d5d29",
    "detailed_design_reviewer": "67ba1ed5dab411168a3eb0f0621c44b9811717ee306f60e154b59d6406217022",
    "detailed_designer": "f98924b64bc35ba1bb78ce0fe906855ff74666be544eead61e4ad465748dac17",
    "diff_triage_reviewer": "cd54457c40079d06236a817b0b0eb232b045582cd782ba0be5cc041ce3439028",
    "docs_workflow_steward": "01ad33e9212a317e369c6b180ac4cc6e496227cdeaed0c7b7b000fc378e71a16",
    "document_flow_reviewer": "9ca29f90f6c62a4fac1cb37ca20baded8f681684a23c03f5d089defc39161034",
    "execution_planner": "f508162187a60a320d40a832617c63c34a4561f30e8d38536f21ef835c8b489e",
    "experiment_runner": "185e2108ab9b2e4e3edc243ea45b9b8ed17a7bdd62334d5fef3d77c144aa0dc2",
    "explorer": "1e717928ebf7b793e50b497bdaa6dd2f6084ec95bd2897ceb78eb388e9cf681a",
    "fair_data_reviewer": "30adde38e432581b7bc73801682cd1ea5b5f26051ec391f5fa08706077fb9245",
    "integration_executor": "27c3e4939102ed1ba6f85e8594b020b0e83970ba91636e00cde4aef344c3de99",
    "literature_researcher": "252fb89ad4301e935733830f12a3bb515eccb45a599cd81dda420186866b0f84",
    "logic_gap_reviewer": "a7ed8e566810ddae1ec1baf8b87e5a5d0eb982c8b2a11d312b4b716dd4280148",
    "long_form_writer": "2a03cfa1a3aad01db012c7e4229a7eac233668783e6b21d253cdd6bc742ad483",
    "manager_reviewer": "8375c4b3562aa44b616fd69196edcf0d0b8f8ecf45c02994edcbcb547ac01a81",
    "ml_science_reviewer": "9920f99658139a9d57b52357ad21a9c5f2608e23395b3aa9697011e06e227dc6",
    "notation_definition_reviewer": "8bb5145693edf047a7362b63bf7d19aee378066998a50fb4bdafb014bd2a33db",
    "oop_readability_reviewer": "e79c1e8a547c96408ab9276aa07e1da1b7025341bcaf36a0d1d2a74465ca663b",
    "plan_reviewer": "feb73fe7b7b2a15b707324f9aef6ca025c405b5d605beb46fc5bf9674353c562",
    "project_reviewer": "5daffa53bf40e4e28fa5e34ca0b862904049dfa9a2ce5c4700ecaea6df8ba440",
    "prompt_config_reviewer": "8513c8770a82007d8c181e2679eb9135db8a08a67260fb372c2bb84e23ab72b7",
    "publisher": "0067702a09e7f3fc85eee7de74cb99385ee61d956bce55773f94fa247d5fda21",
    "python_reviewer": "932cfb6c491dcedd0a882effc01ad3abb9f860e5ebc2cb25af8664a8d9765f29",
    "report_reviewer": "75a5ad188b26268a912d3bb0d623257337fbab70d0fa1d41e59559e200f30db3",
    "reproducibility_reviewer": "ade5a51fa28e94f7d1f5097b53adf3cf7576f7fa7d0029919448ec96e0debd7c",
    "requirements_organizer": "23fc25ffad691be38efd0930cb31e7aaf4ac7ef06af8476bb65f17493aab5af4",
    "reviewer": "13c8986f19e20b32ec50e39d19933c9d0b6f4823ff1a7d5ea3b0bc3229f6e7a2",
    "scientific_computing_reviewer": "0442a95241c89db365c834ea9ebae11ff2872c59cee7c019c03634531b3cbd31",
    "ship_reviewer": "2461457b7e3544c6121f1dd3137666859df4a6a28391d479fa3b1a137e71e021",
    "skill_evaluator": "7e6e97836919a3afcc095c2380d735940777adcecf0437e7b78427200fbdbc5c",
    "spark_worker": "7a7df5e0f66723cd7177b0a65c6bd1fec37a3f6a72311d25fb92daa3ff033cb1",
    "terra": "cc72489f1df3cd4f91d17302125a8cf9b25ccbceb4aaac599101b4d519f909ab",
    "test_designer": "9fb8b554bd07be84d0c37c4a67eca1d3b83fde576d5326c758cc289f838f34ee",
    "worker": "139551d9771644af328ddbc8aaa02a0c7d565d1dea798257761fe8ec00ecc6a5",
}


def run_eval(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the role eval helper."""
    return subprocess.run(
        [str(SCRIPT), "evaluate-codex-agent-roles", *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def external_runtime(root: Path) -> Path:
    """Return an explicit runtime directory outside the source fixture."""
    runtime = root.parent / f"{root.name}-agent-canon-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime


def copy_eval_root(root: Path) -> None:
    """Copy the runtime surfaces needed by the role evaluator."""
    shutil.copytree(PROJECT_ROOT / ".codex" / "agents", root / ".codex" / "agents")
    (root / ".codex").mkdir(exist_ok=True)
    shutil.copy2(
        PROJECT_ROOT / ".codex" / "config.toml", root / ".codex" / "config.toml"
    )
    (root / "agents").mkdir()
    shutil.copy2(
        PROJECT_ROOT / "agents" / "agents_config.json",
        root / "agents" / "agents_config.json",
    )
    shutil.copy2(
        PROJECT_ROOT / "agents" / "task_catalog.yaml",
        root / "agents" / "task_catalog.yaml",
    )
    shutil.copy2(
        PROJECT_ROOT / "agents" / "model_profiles.toml",
        root / "agents" / "model_profiles.toml",
    )


class CodexAgentRoleEvalTest(unittest.TestCase):
    """Verify Codex custom agent role eval behavior."""

    def test_default_role_eval_passes(self) -> None:
        """The canonical role eval should pass on checked-in agent config."""
        result = run_eval()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CODEX_AGENT_ROLE_EVAL=pass", result.stdout)
        self.assertIn("CODEX_AGENT_ROLE_FINDINGS=0", result.stdout)
        self.assertIn("ROLE_RUNTIME_METRICS_STATUS=missing", result.stdout)
        self.assertIn("skill_evaluator:gpt-6-luna:medium", result.stdout)
        self.assertIn("worker:gpt-6-luna:xhigh", result.stdout)
        self.assertIn("diff_triage_reviewer:gpt-6-luna:high", result.stdout)
        self.assertIn("experiment_runner:gpt-6-luna:high", result.stdout)
        self.assertIn("explorer:gpt-6-luna:high", result.stdout)
        matrix = next(
            line
            for line in result.stdout.splitlines()
            if line.startswith("ROLE_MODEL_MATRIX=")
        )
        self.assertEqual(
            [
                entry
                for entry in matrix.split("=", 1)[1].split(";")
                if entry.startswith("skill_evaluator:")
            ],
            ["skill_evaluator:gpt-6-luna:medium"],
        )
        self.assertIn("manager_reviewer:gpt-6-luna:high", result.stdout)
        self.assertIn("plan_reviewer:gpt-6-luna:high", result.stdout)
        self.assertIn("spark_worker:gpt-6-luna:low", result.stdout)
        self.assertIn("ship_reviewer:gpt-6-luna:xhigh", result.stdout)

    def test_evaluator_policy_is_read_only_and_fresh(self) -> None:
        """The role evaluator rejects an unsafe empirical evaluator policy."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            evaluator = root / ".codex" / "agents" / "skill_evaluator.toml"
            text = evaluator.read_text(encoding="utf-8")
            evaluator.write_text(
                text.replace(
                    'sandbox_mode = "read-only"', 'sandbox_mode = "workspace-write"'
                ).replace(
                    'approval_policy = "never"', 'approval_policy = "on-request"'
                ),
                encoding="utf-8",
            )

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn("evaluator-not-read-only", result.stdout)
            self.assertIn("evaluator-approval-policy-not-never", result.stdout)
            self.assertIn("source-divergence-sandbox_mode", result.stdout)
            self.assertIn("source-divergence-approval_policy", result.stdout)

    def test_missing_skill_evaluator_toml_is_reported_without_traceback(self) -> None:
        """A copied root reports a missing target TOML as a structured finding."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            (root / ".codex" / "agents" / "skill_evaluator.toml").unlink()

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=registration:skill_evaluator:missing-toml",
                result.stdout,
            )
            self.assertNotIn("Traceback", result.stderr)

    def test_role_candidate_order_comes_from_target_team_config(self) -> None:
        """The native role evaluator rejects a changed canonical candidate order."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            baseline = run_eval("--root", str(root), "--format", "json")
            self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)
            team_path = root / "agents" / "agents_config.json"
            team = json.loads(team_path.read_text(encoding="utf-8"))
            implementer = next(
                role
                for role in team["always_on_roles"] + team["specialist_roles"]
                if role["id"] == "implementer"
            )
            implementer["codex_agents"] = ["spark_worker", "worker"]
            team_path.write_text(json.dumps(team, indent=2) + "\n", encoding="utf-8")

            changed = run_eval("--root", str(root), "--format", "json")
            self.assertEqual(changed.returncode, 1)
            self.assertIn("role-candidate-order-expected-", changed.stdout)

    def test_evaluator_grammar_is_packet_driven_and_parent_scored(self) -> None:
        """Evaluator execution is a closed view generated from canonical profile truth."""
        evaluator_path = PROJECT_ROOT / ".codex" / "agents" / "skill_evaluator.toml"
        evaluator_text = evaluator_path.read_text(encoding="utf-8")
        evaluator = tomllib.loads(evaluator_text)
        self.assertIn("generated role view: generated_role_view_v1", evaluator_text)
        for producer_prefix in (
            "agents/skills/",
            "agents/model_profiles.toml",
            "tools/agent_tools/",
            "../../agents/",
            "../../tools/",
        ):
            self.assertNotIn(producer_prefix, evaluator_text)
        self.assertEqual(evaluator["model"], "gpt-6-luna")
        self.assertEqual(evaluator["model_reasoning_effort"], "medium")
        self.assertIn(
            "explicit evidence and typed outputs", evaluator["developer_instructions"]
        )
        self.assertNotIn("R<integer>", evaluator_text)
        self.assertNotIn("score_percent=", evaluator_text)

    def test_live_role_views_match_reviewed_baseline_for_all_37_roles(self) -> None:
        """Native live generation matches reviewed metadata and assignment bytes."""
        assignment_hashes: dict[str, str] = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "root"
            copy_eval_root(root)
            generated = run_eval(
                "--root",
                str(root),
                "--generate-role-views",
                "--projection",
                "live",
            )
            self.assertEqual(
                generated.returncode, 0, generated.stdout + generated.stderr
            )
            views = {
                path.stem: tomllib.loads(path.read_text(encoding="utf-8"))
                for path in (root / ".codex/agents").glob("*.toml")
            }
            for role_id in views:
                assignment_body = (
                    "\n".join(
                        line
                        for line in (root / ".codex/agents" / f"{role_id}.toml")
                        .read_text(encoding="utf-8")
                        .splitlines()
                        if line.strip() and not line.lstrip().startswith("#")
                    )
                    + "\n"
                )
                assignment_hashes[role_id] = hashlib.sha256(
                    assignment_body.encode("utf-8")
                ).hexdigest()
        self.assertEqual(set(views), set(EXPECTED_LIVE_ROLE_METADATA))
        self.assertEqual(len(views), 37)
        fields = (
            "name",
            "description",
            "nickname_candidates",
            "sandbox_mode",
            "approval_policy",
            "model",
            "model_reasoning_effort",
        )
        expected_assignment_sha256 = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/model_profiles/live_assignment_sha256.json"
            ).read_text(encoding="utf-8")
        )
        for role_id, golden in EXPECTED_LIVE_ROLE_METADATA.items():
            view = views[role_id]
            self.assertEqual(
                {field: view[field] for field in fields},
                golden,
                role_id,
            )
            self.assertIn(
                f"You are acting as {role_id}", view["developer_instructions"]
            )
            self.assertEqual(
                assignment_hashes[role_id],
                expected_assignment_sha256[role_id],
                role_id,
            )

    def test_committed_consumer_static_role_view_bytes_match_reviewed_baseline(
        self,
    ) -> None:
        """The 37 committed static role files retain their independent byte hashes."""
        role_root = PROJECT_ROOT / ".codex/agents"
        self.assertEqual(
            {path.stem for path in role_root.glob("*.toml")},
            set(EXPECTED_STATIC_ROLE_VIEW_SHA256),
        )
        for role_id, expected in EXPECTED_STATIC_ROLE_VIEW_SHA256.items():
            path = role_root / f"{role_id}.toml"
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), expected, role_id
            )

    def test_role_eval_rejects_tier_and_service_tier_profile_keys(self) -> None:
        """Repository agent TOMLs must not introduce tier selectors."""
        for key in ("tier", "service_tier"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                copy_eval_root(root)
                worker = root / ".codex" / "agents" / "worker.toml"
                worker.write_text(
                    worker.read_text(encoding="utf-8") + f'\n{key} = "unsupported"\n',
                    encoding="utf-8",
                )

                result = run_eval("--root", str(root))

                self.assertEqual(result.returncode, 1)
                self.assertIn(
                    f"CODEX_AGENT_ROLE_FINDING=schema:worker:unsupported-profile-key-{key}",
                    result.stdout,
                )

    def test_role_eval_rejects_non_explicit_evaluator_registration(self) -> None:
        """The evaluator must be registered only on the explicit evaluation task."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            catalog_path = root / "agents" / "task_catalog.yaml"
            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
            comprehensive = next(
                family
                for family in catalog["workflow_families"]
                if family["id"] == "comprehensive_development"
            )
            comprehensive["roles"]["specialists"].append("skill_evaluator")
            t12 = next(task for task in catalog["tasks"] if task["id"] == "T12")
            t12["specialists"].append("skill_evaluator")
            catalog_path.write_text(yaml.safe_dump(catalog), encoding="utf-8")

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=registration:skill_evaluator:must-be-only-in-explicit-evaluation-task",
                result.stdout,
            )

    def test_role_eval_rejects_evaluator_in_non_evaluation_family(self) -> None:
        """The role evaluator must enforce the shared family-membership policy."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            catalog_path = root / "agents" / "task_catalog.yaml"
            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
            comprehensive = next(
                family
                for family in catalog["workflow_families"]
                if family["id"] == "comprehensive_development"
            )
            comprehensive["roles"]["specialists"].append("skill_evaluator")
            catalog_path.write_text(yaml.safe_dump(catalog), encoding="utf-8")

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=routing:comprehensive_development:"
                "skill-evaluator-only-in-skill-evaluation",
                result.stdout,
            )

    def test_routing_rejects_unknown_task_and_default_pack_roles(self) -> None:
        """Unknown roles remain invalid instead of being removed from the evaluation."""
        for source in ("task", "default_pack"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                copy_eval_root(root)
                path = root / "agents" / "task_catalog.yaml"
                catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
                if source == "task":
                    task = next(task for task in catalog["tasks"] if task["id"] == "T1")
                    task["specialists"].append("ghost_role")
                    expected = "not declared in family"
                else:
                    pack = next(
                        pack
                        for pack in catalog["review_packs"]
                        if pack["id"] == "research_perspective_triage"
                    )
                    pack["default_for_tasks"] = ["T1"]
                    pack["specialists"].append("ghost_role")
                    expected = "unknown role: ghost_role"
                path.write_text(yaml.safe_dump(catalog), encoding="utf-8")
                result = run_eval("--root", str(root))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(expected, result.stderr)

    def test_routing_rejects_non_string_specialist_entries(self) -> None:
        """Malformed role list items are rejected before role lookup."""
        for source in ("task", "default_pack"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                copy_eval_root(root)
                path = root / "agents" / "task_catalog.yaml"
                catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
                if source == "task":
                    next(task for task in catalog["tasks"] if task["id"] == "T1")[
                        "specialists"
                    ].append(7)
                else:
                    pack = next(
                        pack
                        for pack in catalog["review_packs"]
                        if pack["id"] == "research_perspective_triage"
                    )
                    pack["default_for_tasks"] = ["T1"]
                    pack["specialists"].append(7)
                path.write_text(yaml.safe_dump(catalog), encoding="utf-8")
                result = run_eval("--root", str(root))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("entries must be strings", result.stderr)

    def test_runtime_metrics_are_aggregated(self) -> None:
        """Optional JSONL runtime metrics should be summarized by agent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime = external_runtime(Path(tmp_dir) / "source")
            log_path = runtime / "roles.jsonl"
            log_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "agent": "python_reviewer",
                                "tokens": FIRST_RUNTIME_TOKENS,
                                "latency_ms": FIRST_RUNTIME_LATENCY_MS,
                                "retry_count": 1,
                                "output_used": True,
                            }
                        ),
                        json.dumps(
                            {
                                "agent": "python_reviewer",
                                "total_tokens": SECOND_RUNTIME_TOKENS,
                                "latency_ms": SECOND_RUNTIME_LATENCY_MS,
                                "parent_intervention": True,
                                "format_violation": True,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_eval(
                "--runtime-root", str(runtime), "--runtime-log", str(log_path)
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ROLE_RUNTIME_METRICS_STATUS=observed", result.stdout)
            self.assertIn(
                f"ROLE_RUNTIME_METRIC=python_reviewer:calls=2:tokens={EXPECTED_RUNTIME_TOKENS}",
                result.stdout,
            )
            self.assertIn("parent_interventions=1", result.stdout)
            self.assertIn("format_violations=1", result.stdout)
            self.assertIn("output_used=1", result.stdout)

    def test_compact_out_limits_stdout_and_writes_summary(self) -> None:
        """Compact mode writes role stats to JSON and keeps stdout bounded."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime = external_runtime(Path(tmp_dir) / "source")
            compact = runtime / "roles.json"

            result = run_eval(
                "--runtime-root", str(runtime), "--compact-out", str(compact)
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CODEX_AGENT_ROLE_EVAL=pass", result.stdout)
            self.assertIn("CODEX_AGENT_ROLE_COMPACT_OUT=", result.stdout)
            self.assertNotIn("ROLE_MODEL_MATRIX=", result.stdout)
            payload = json.loads(compact.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["finding_count"], 0)
            self.assertEqual(
                payload["model_counts"],
                {"gpt-6-astra": 1, "gpt-6-luna": 36},
            )

    def test_accumulate_writes_role_eval_report(self) -> None:
        """Role evals should accumulate through the shared eval result contract."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime = external_runtime(Path(tmp_dir) / "source")
            results_dir = runtime / "role-results"

            result = run_eval(
                "--runtime-root",
                str(runtime),
                "--accumulate",
                "--results-dir",
                str(results_dir),
                "--run-id",
                "test-run",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "CODEX_AGENT_ROLE_EVAL_RUN_ID=codex-agent-role-eval-", result.stdout
            )
            self.assertIn("CODEX_AGENT_ROLE_EVAL_ACCUMULATED_REPORT=", result.stdout)
            reports = tuple(results_dir.glob("codex-agent-role-eval-*-pass.md"))
            self.assertEqual(len(reports), 1)
            text = reports[0].read_text(encoding="utf-8")
            self.assertIn("CODEX_AGENT_ROLE_EVAL_RUN_ID=codex-agent-role-eval-", text)
            self.assertIn("run_id: `test-run`", text)

    def test_runtime_metrics_report_invalid_numeric_values(self) -> None:
        """Malformed metric values should produce findings instead of tracebacks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime = external_runtime(Path(tmp_dir) / "source")
            log_path = runtime / "roles.jsonl"
            log_path.write_text(
                json.dumps(
                    {
                        "agent": "python_reviewer",
                        "tokens": "100.5",
                        "latency_ms": "n/a",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_eval(
                "--runtime-root", str(runtime), "--runtime-log", str(log_path)
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("CODEX_AGENT_ROLE_FINDING=runtime-log:", result.stdout)
            self.assertIn("invalid-int-metric", result.stdout)
            self.assertNotIn("Traceback", result.stderr)

    def test_root_argument_uses_target_task_catalog(self) -> None:
        """--root should validate the target checkout's routing, not the script checkout."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            task_catalog = (PROJECT_ROOT / "agents" / "task_catalog.yaml").read_text(
                encoding="utf-8"
            )
            (root / "agents" / "task_catalog.yaml").write_text(
                task_catalog.replace(
                    "family: owner_bounded_change", "family: scoped_change", 1
                ),
                encoding="utf-8",
            )

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=routing:T1:must-use-owner-bounded-change",
                result.stdout,
            )

    def test_routing_reports_t14_normal_delivery_route(self) -> None:
        """T14 must not use the comprehensive worker/reviewer route."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            catalog_path = root / "agents" / "task_catalog.yaml"
            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
            comprehensive = next(
                family
                for family in catalog["workflow_families"]
                if family["id"] == "comprehensive_development"
            )
            comprehensive["roles"]["specialists"].append("skill_evaluator")
            t14 = next(task for task in catalog["tasks"] if task["id"] == "T14")
            t14["family"] = "comprehensive_development"
            catalog_path.write_text(yaml.safe_dump(catalog), encoding="utf-8")

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=routing:T14:must-use-skill-evaluation-family",
                result.stdout,
            )

    def test_routing_reports_stale_implementation_role_family(self) -> None:
        """The catalog implementation family must prefer worker."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            catalog_path = root / "agents" / "task_catalog.yaml"
            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
            catalog["role_topology_defaults"]["role_families"]["implementation"] = [
                "spark_worker",
                "worker",
            ]
            catalog_path.write_text(yaml.safe_dump(catalog), encoding="utf-8")

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "implementation-role-family-order",
                result.stdout,
            )

    def test_routing_reports_t12_overdefault_specialist(self) -> None:
        """T12 should not default evidence-gated specialist roles."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            catalog_path = root / "agents" / "task_catalog.yaml"
            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
            t12 = next(task for task in catalog["tasks"] if task["id"] == "T12")
            t12["specialists"].append("python_reviewer")
            catalog_path.write_text(yaml.safe_dump(catalog), encoding="utf-8")

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn("t12-overdefault-specialist", result.stdout)

    def test_routing_reports_bad_candidate_order(self) -> None:
        """Ordered codex_agents lists should preserve default candidate semantics."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            config_path = root / "agents" / "agents_config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            implementer = next(
                role
                for role in config["always_on_roles"]
                if role["id"] == "implementer"
            )
            implementer["codex_agents"] = ["spark_worker", "worker"]
            config_path.write_text(json.dumps(config), encoding="utf-8")

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn("role-candidate-order", result.stdout)

    def test_routing_rejects_skill_evaluator_candidate_on_ordinary_role(self) -> None:
        """The static evaluator rejects a trailing evaluator fallback."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            config_path = root / "agents" / "agents_config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            experimenter = next(
                role
                for role in config["specialist_roles"]
                if role["id"] == "experimenter"
            )
            experimenter["codex_agents"].append("skill_evaluator")
            config_path.write_text(json.dumps(config), encoding="utf-8")

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=registration:experimenter:"
                "skill-evaluator-candidate-reserved-for-skill-evaluator-role",
                result.stdout,
            )

    def test_spark_profile_effort_must_match_the_role_binding(self) -> None:
        """Spark's low-effort profile must not replace a reviewer's binding."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            explorer = root / ".codex" / "agents" / "explorer.toml"
            explorer.write_text(
                explorer.read_text(encoding="utf-8").replace(
                    'model_reasoning_effort = "high"',
                    'model_reasoning_effort = "low"',
                ),
                encoding="utf-8",
            )

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=profile-attribution:explorer:"
                "runtime-view-divergence",
                result.stdout,
            )
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=model-settings:explorer:"
                "expected-high-reasoning",
                result.stdout,
            )

    def test_review_role_profile_effort_must_match_binding(self) -> None:
        """A reviewer cannot use the evaluator's medium-effort profile."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            python_reviewer = root / ".codex" / "agents" / "python_reviewer.toml"
            python_reviewer.write_text(
                python_reviewer.read_text(encoding="utf-8").replace(
                    'model_reasoning_effort = "high"',
                    'model_reasoning_effort = "medium"',
                ),
                encoding="utf-8",
            )

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=profile-attribution:python_reviewer:"
                "runtime-view-divergence",
                result.stdout,
            )
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=model-settings:python_reviewer:expected-high-reasoning",
                result.stdout,
            )

    def test_deprecated_codex_models_are_reported(self) -> None:
        """Deprecated Codex model slugs should stay out of role TOML."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            worker = root / ".codex" / "agents" / "worker.toml"
            worker.write_text(
                worker.read_text(encoding="utf-8").replace(
                    'model = "gpt-6-luna"',
                    'model = "gpt-5.3-codex"',
                ),
                encoding="utf-8",
            )

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=model-settings:worker:deprecated-model-gpt-5.3-codex",
                result.stdout,
            )


if __name__ == "__main__":
    unittest.main()
