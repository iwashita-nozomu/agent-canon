# @dependency-start
# contract test
# responsibility Tests Codex agent role eval automation.
# upstream implementation ../../tools/agent_tools/evaluate_codex_agent_roles.py helper
# upstream design ../../evidence/agent-evals/README.md role eval contract
# @dependency-end
"""Tests for Codex agent role eval automation."""

from __future__ import annotations

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
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "evaluate_codex_agent_roles.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from implementation_dispatch import (  # noqa: E402
    recommended_dynamic_expansion_wave_slots,
    recommended_initial_subagent_wave,
)
from team_config import load_task_catalog, load_team_config, select_roles  # noqa: E402
from model_profile_registry import generate_role_views, load_model_profile_registry  # noqa: E402

FIRST_RUNTIME_TOKENS = 100
FIRST_RUNTIME_LATENCY_MS = 25
SECOND_RUNTIME_TOKENS = 50
SECOND_RUNTIME_LATENCY_MS = 15
EXPECTED_RUNTIME_TOKENS = FIRST_RUNTIME_TOKENS + SECOND_RUNTIME_TOKENS
PRE_CHANGE_LIVE_GOLDEN = {
    'artifact_reviewer': {
        'name': 'artifact_reviewer',
        'description': 'Read-only reviewer for code, scripts, raw results, environment capture, and artifact-readiness.',
        'nickname_candidates': ['artifact_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as artifact_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'benchmark_reviewer': {
        'name': 'benchmark_reviewer',
        'description': 'Read-only reviewer for fairness, confounders, and benchmark anti-patterns.',
        'nickname_candidates': ['benchmark_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as benchmark_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'citation_evidence_reviewer': {
        'name': 'citation_evidence_reviewer',
        'description': 'Read-only reviewer for paper claims, citations, figures, tables, and evidence traceability.',
        'nickname_candidates': ['citation_evidence_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as citation_evidence_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'cpp_reviewer': {
        'name': 'cpp_reviewer',
        'description': 'Read-only reviewer for C and C++ diffs, build/test evidence, ABI-boundary changes, and native-code regressions.',
        'nickname_candidates': ['cpp_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as cpp_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'detailed_design_reviewer': {
        'name': 'detailed_design_reviewer',
        'description': 'Read-only reviewer for detailed design docs, implementation readiness, side-effect mapping, reuse-first discipline, and style continuity.',
        'nickname_candidates': ['detailed_design_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as detailed_design_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'detailed_designer': {
        'name': 'detailed_designer',
        'description': 'Detailed-design authoring agent for writing implementation-ready design docs with reuse-first, side-effect mapping, and style-continuity guidance.',
        'nickname_candidates': ['detailed_designer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as detailed_designer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'diff_triage_reviewer': {
        'name': 'diff_triage_reviewer',
        'description': 'Read-only reviewer for bounded diffs before escalation to broad review.',
        'nickname_candidates': ['diff_triage_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as diff_triage_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions. Review bounded diffs findings-first; route SOLID-sensitive Python boundaries to python_reviewer and require a path-covered OOP readability report, SOLID principle signal counts, and check_solid_evidence.py evidence. Return approve, revise, or escalate, and escalate public API, workflow, runtime, security, dependency, or cross-owner scope.',
    },
    'docs_workflow_steward': {
        'name': 'docs_workflow_steward',
        'description': 'Docs and workflow steward for canonical instructions, notes, and agent workflows.',
        'nickname_candidates': ['docs_workflow_steward'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as docs_workflow_steward with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'document_flow_reviewer': {
        'name': 'document_flow_reviewer',
        'description': 'Read-only reviewer for top-down document coherence, section order, term introduction order, and first-reader comprehension.',
        'nickname_candidates': ['document_flow_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as document_flow_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'execution_planner': {
        'name': 'execution_planner',
        'description': 'Execution-planning agent for stage order, subagent assignment, validation sequence, and rollback-aware task plans.',
        'nickname_candidates': ['execution_planner'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as execution_planner with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'experiment_runner': {
        'name': 'experiment_runner',
        'description': 'Execution-only agent for running bounded experiments and summarizing logs.',
        'nickname_candidates': ['experiment_runner'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as experiment_runner with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'explorer': {
        'name': 'explorer',
        'description': 'Read-only agent for tracing code paths, docs, and workflow state.',
        'nickname_candidates': ['explorer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as explorer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'fair_data_reviewer': {
        'name': 'fair_data_reviewer',
        'description': 'Read-only reviewer for metadata quality, naming, reuse, and FAIR-style data organization.',
        'nickname_candidates': ['fair_data_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as fair_data_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'literature_researcher': {
        'name': 'literature_researcher',
        'description': 'Read-only agent for paper search, prior-art mapping, and contradictory-source hunting.',
        'nickname_candidates': ['literature_researcher'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as literature_researcher with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'logic_gap_reviewer': {
        'name': 'logic_gap_reviewer',
        'description': 'Read-only reviewer for academic-argument continuity, claim-to-evidence links, hidden assumptions, and unsupported inferential jumps.',
        'nickname_candidates': ['logic_gap_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as logic_gap_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'long_form_writer': {
        'name': 'long_form_writer',
        'description': 'Long-form document author for README, workflow, guide, migration, and other reader-facing documents that need roadmap-first drafting.',
        'nickname_candidates': ['long_form_writer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as long_form_writer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'manager_reviewer': {
        'name': 'manager_reviewer',
        'description': 'Read-only requirements reviewer for scope, source buckets, accumulated-context resolution, and escalation discipline.',
        'nickname_candidates': ['manager_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as manager_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'ml_science_reviewer': {
        'name': 'ml_science_reviewer',
        'description': 'Read-only reviewer for assumptions, limitations, uncertainty, and reader-facing scientific reporting.',
        'nickname_candidates': ['ml_science_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as ml_science_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'notation_definition_reviewer': {
        'name': 'notation_definition_reviewer',
        'description': 'Read-only reviewer for symbol, abbreviation, terminology, unit, and definition-before-use discipline in academic documents.',
        'nickname_candidates': ['notation_definition_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as notation_definition_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'oop_readability_reviewer': {
        'name': 'oop_readability_reviewer',
        'description': 'Read-only reviewer that documents mechanical OOP readability reports without changing their verdicts.',
        'nickname_candidates': ['oop_readability_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as oop_readability_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'plan_reviewer': {
        'name': 'plan_reviewer',
        'description': 'Read-only reviewer for execution plans, stage order, reviewer separation, validation sequencing, and rollback readiness.',
        'nickname_candidates': ['plan_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as plan_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'project_reviewer': {
        'name': 'project_reviewer',
        'description': 'Read-only reviewer for repo-wide inventory, workflow health, and tooling health.',
        'nickname_candidates': ['project_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as project_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'prompt_config_reviewer': {
        'name': 'prompt_config_reviewer',
        'description': 'Read-only reviewer for prompt, routing, and subagent-config drift.',
        'nickname_candidates': ['prompt_config_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as prompt_config_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'python_reviewer': {
        'name': 'python_reviewer',
        'description': 'Read-only reviewer for Python diffs, type boundaries, and parent-selected validation evidence.',
        'nickname_candidates': ['python_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as python_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions. Review Python diffs findings-first for behavior, types, tests, and public boundaries. Follow agents/skills/python-review.md#Validation route and agents/skills/agent-orchestration.md#Write-Capable Handoff Validation Trust Boundary for validation scope; review the parent packet route and do not add validation outside that route. When the canonical route selects SOLID evidence, require a path-covered OOP readability report, SOLID principle signal, Single responsibility, Open/closed, Liskov substitution, Interface segregation, Dependency inversion, and check_solid_evidence.py path-coverage evidence; otherwise do not add those checks. Return revise only for evidence required by the canonical route.',
    },
    'report_reviewer': {
        'name': 'report_reviewer',
        'description': 'Read-only reviewer for experiment reports and evidence traceability.',
        'nickname_candidates': ['report_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as report_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'reproducibility_reviewer': {
        'name': 'reproducibility_reviewer',
        'description': 'Read-only reviewer for provenance, seeds, commands, environments, and rerunability.',
        'nickname_candidates': ['reproducibility_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as reproducibility_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'requirements_organizer': {
        'name': 'requirements_organizer',
        'description': 'Requirements-organizing agent for turning user intent and local precedent into concrete scope, acceptance criteria, and reuse targets.',
        'nickname_candidates': ['requirements_organizer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as requirements_organizer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'reviewer': {
        'name': 'reviewer',
        'description': 'Read-only review agent for diffs, regressions, and documentation alignment.',
        'nickname_candidates': ['reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions. Review exact diffs findings-first against request clauses and owning evidence. For SOLID-sensitive Python changes require a path-covered OOP readability report, SOLID principle signal counts, and check_solid_evidence.py evidence; return revise when that evidence or changed-path coverage is incomplete.',
    },
    'scientific_computing_reviewer': {
        'name': 'scientific_computing_reviewer',
        'description': 'Read-only reviewer for incremental change, testing, automation, and prototype discipline in research code.',
        'nickname_candidates': ['scientific_computing_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as scientific_computing_reviewer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'ship_reviewer': {
        'name': 'ship_reviewer',
        'description': 'High-assurance read-only reviewer for final clause coverage and release readiness.',
        'nickname_candidates': ['ship_reviewer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'xhigh',
        'developer_instructions': 'You are acting as ship_reviewer for ship readiness under luna_ship. Constrain edits to one responsibility unit and one-pass materialization only when selected.',
    },
    'skill_evaluator': {
        'name': 'skill_evaluator',
        'description': 'Fresh read-only evaluator for explicit empirical skill scenarios.',
        'nickname_candidates': ['skill_evaluator'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.4-mini',
        'model_reasoning_effort': 'medium',
        'developer_instructions': 'You are acting as skill_evaluator with skill_evaluator policy. Evaluate policy conformance with explicit evidence and typed outputs.',
    },
    'spark_worker': {
        'name': 'spark_worker',
        'description': 'Low-latency implementation agent for bounded code, docs, tests, or mechanical cleanup slices derived from the Abstract Design Frame and design trace.',
        'nickname_candidates': ['spark_worker'],
        'sandbox_mode': 'workspace-write',
        'approval_policy': 'never',
        'model': 'gpt-5.3-codex-spark',
        'model_reasoning_effort': 'low',
        'developer_instructions': 'You are acting as spark_worker for implementation execution with spark_implementation. Materialize one fixed packet directly, keep checkpoints observational, and return the closed Spark result schema. Follow the sole validation scope owner at agents/skills/agent-orchestration.md#Write-Capable Handoff Validation Trust Boundary for parent-assigned commands, mechanism-required static checks, full-suite selection, and unexpected-action reporting. Execute only implement/commit/push within authority bounds; PR create/merge/close, admin override, base integration decision, and final integration/final editorial decision are parent-only. After push, return branch, head, and check evidence to the parent integrator and stop.',
    },
    'terra': {
        'name': 'terra',
        'description': 'Conditional read-only cross-cutting specialist for owner closure, context reconstruction, and adversarial contradiction validation.',
        'nickname_candidates': ['terra'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-terra',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as terra with terra_cross_cutting cross-cutting review capacity. Operate only as a conditional read-only cross-cutting specialist. Activate on multi-owner dependency closure, compaction/long-run/incomplete-handoff context reconstruction, or adversarial contradiction validation. Treat user-provided alternatives and alternatives already present in findings as admissible adversarial-comparison input. Return owner closure, context capsule, and accepted/rejected/escalated handback; send unresolved findings to Sol. Do not invent unrequested alternatives, adopt an architecture, coordinate, implement as a general worker, mutate repository state, create PRs, or make final integration decisions.',
    },
    'test_designer': {
        'name': 'test_designer',
        'description': 'Read-only agent for post-implementation static analysis when an explicit unresolved oracle, specification, regression, or failure-mode risk remains beyond existing validation.',
        'nickname_candidates': ['test_designer'],
        'sandbox_mode': 'read-only',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'high',
        'developer_instructions': 'You are acting as test_designer with luna_reasoning reasoning capacity. Prioritize rigorous decomposition and evidence-first conclusions.',
    },
    'worker': {
        'name': 'worker',
        'description': 'Implementation agent for bounded code, docs, or test changes.',
        'nickname_candidates': ['worker'],
        'sandbox_mode': 'workspace-write',
        'approval_policy': 'never',
        'model': 'gpt-5.6-luna',
        'model_reasoning_effort': 'xhigh',
        'developer_instructions': 'You are acting as worker with luna_implementation implementation rigor. Use precise mechanical changes and strict failure semantics; avoid unrelated scope expansion. Follow the sole validation scope owner at agents/skills/agent-orchestration.md#Write-Capable Handoff Validation Trust Boundary for parent-assigned commands, mechanism-required static checks, full-suite selection, and unexpected-action reporting. For this role, execute only implement/commit/push within authority bounds; PR create/merge/close, admin override, base integration decision, and final integration/final editorial decision are parent-only. After push, return branch, head, and check evidence to the parent integrator and stop.',
    },
}



def run_eval(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the role eval helper."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def copy_eval_root(root: Path) -> None:
    """Copy the runtime surfaces needed by the role evaluator."""
    shutil.copytree(PROJECT_ROOT / ".codex" / "agents", root / ".codex" / "agents")
    (root / ".codex").mkdir(exist_ok=True)
    shutil.copy2(PROJECT_ROOT / ".codex" / "config.toml", root / ".codex" / "config.toml")
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
        self.assertIn("skill_evaluator:gpt-5.4-mini:medium", result.stdout)
        self.assertIn("worker:gpt-5.6-luna:xhigh", result.stdout)
        self.assertIn("diff_triage_reviewer:gpt-5.6-luna:high", result.stdout)
        self.assertIn("experiment_runner:gpt-5.6-luna:high", result.stdout)
        self.assertIn("explorer:gpt-5.6-luna:high", result.stdout)
        matrix = next(
            line for line in result.stdout.splitlines() if line.startswith("ROLE_MODEL_MATRIX=")
        )
        self.assertEqual(
            [entry for entry in matrix.split("=", 1)[1].split(";") if "gpt-5.4-mini" in entry],
            ["skill_evaluator:gpt-5.4-mini:medium"],
        )
        self.assertIn("manager_reviewer:gpt-5.6-luna:high", result.stdout)
        self.assertIn("plan_reviewer:gpt-5.6-luna:high", result.stdout)
        self.assertIn("spark_worker:gpt-5.3-codex-spark:low", result.stdout)
        self.assertIn("ship_reviewer:gpt-5.6-luna:xhigh", result.stdout)

    def test_evaluator_policy_is_read_only_and_fresh(self) -> None:
        """The role evaluator rejects an unsafe empirical evaluator policy."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            evaluator = root / ".codex" / "agents" / "skill_evaluator.toml"
            text = evaluator.read_text(encoding="utf-8")
            evaluator.write_text(
                text.replace('sandbox_mode = "read-only"', 'sandbox_mode = "workspace-write"')
                .replace('approval_policy = "never"', 'approval_policy = "on-request"'),
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

    def test_materialization_uses_target_registry_without_current_checkout_fallback(self) -> None:
        """Copied-root availability controls candidate materialization."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            (root / ".codex" / "agents" / "worker.toml").unlink()
            config = load_team_config(root / "agents" / "agents_config.json")
            catalog = load_task_catalog(config, root=root)
            roles = select_roles(
                config,
                ["implementer"],
                full_team=False,
                catalog=catalog,
                workflow_family_id="owner_bounded_change",
            )
            initial_wave = recommended_initial_subagent_wave(
                roles,
                4,
                catalog,
                agent_root=root / ".codex" / "agents",
            )
            expansion_waves = recommended_dynamic_expansion_wave_slots(
                roles,
                4,
                initial_wave,
                catalog,
                agent_root=root / ".codex" / "agents",
            )

            materialized = [
                slot.agent_type for wave in expansion_waves for slot in wave
            ]
            self.assertIn("spark_worker", materialized)
            self.assertNotIn("worker", materialized)

    def test_dynamic_expansion_rejects_mismatched_initial_wave(self) -> None:
        """Dynamic expansion must validate the caller's initial agent types."""
        config = load_team_config()
        catalog = load_task_catalog(config)
        roles = select_roles(
            config,
            ["implementer"],
            full_team=False,
            catalog=catalog,
            workflow_family_id="owner_bounded_change",
        )

        with self.assertRaisesRegex(RuntimeError, "initial_wave does not match"):
            recommended_dynamic_expansion_wave_slots(
                roles,
                4,
                ("worker",),
                catalog,
                agent_root=PROJECT_ROOT / ".codex" / "agents",
            )

    def test_evaluator_grammar_is_packet_driven_and_parent_scored(self) -> None:
        """Evaluator execution is a closed view generated from canonical profile truth."""
        evaluator_path = PROJECT_ROOT / ".codex" / "agents" / "skill_evaluator.toml"
        evaluator_text = evaluator_path.read_text(encoding="utf-8")
        evaluator = tomllib.loads(evaluator_text)
        expected_fields = {
            "name",
            "description",
            "nickname_candidates",
            "sandbox_mode",
            "approval_policy",
            "model",
            "model_reasoning_effort",
            "developer_instructions",
        }

        self.assertEqual(set(evaluator), expected_fields)
        self.assertIn("generated role view: generated_role_view_v1", evaluator_text)
        for producer_prefix in (
            "agents/skills/",
            "agents/model_profiles.toml",
            "tools/agent_tools/",
            "../../agents/",
            "../../tools/",
        ):
            self.assertNotIn(producer_prefix, evaluator_text)
        self.assertEqual(evaluator["model"], "gpt-5.4-mini")
        self.assertEqual(evaluator["model_reasoning_effort"], "medium")
        self.assertIn("explicit evidence and typed outputs", evaluator["developer_instructions"])
        self.assertNotIn("R<integer>", evaluator_text)
        self.assertNotIn("score_percent=", evaluator_text)

    def test_pre_change_live_golden_is_invariant_for_all_35_roles(self) -> None:
        """The post-change live materializer remains byte-identical to the HEAD golden."""
        registry = load_model_profile_registry(PROJECT_ROOT)
        views = {
            view.role_id: view
            for view in generate_role_views(registry, PROJECT_ROOT, projection="live")
        }
        self.assertEqual(set(views), set(PRE_CHANGE_LIVE_GOLDEN))
        self.assertEqual(len(views), 35)
        fields = (
            "name",
            "description",
            "nickname_candidates",
            "sandbox_mode",
            "approval_policy",
            "model",
            "model_reasoning_effort",
        )
        for role_id, golden in PRE_CHANGE_LIVE_GOLDEN.items():
            view = views[role_id]
            actual = {
                "name": view.name,
                "description": view.description,
                "nickname_candidates": list(view.nickname_candidates),
                "sandbox_mode": view.sandbox_mode,
                "approval_policy": view.approval_policy,
                "model": view.model,
                "model_reasoning_effort": view.reasoning_effort,
                "developer_instructions": view.rendered_instructions,
            }
            self.assertEqual(
                {field: actual[field] for field in fields},
                {field: golden[field] for field in fields},
                role_id,
            )
            self.assertEqual(actual["developer_instructions"], golden["developer_instructions"], role_id)

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

    def test_runtime_metrics_are_aggregated(self) -> None:
        """Optional JSONL runtime metrics should be summarized by agent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "roles.jsonl"
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

            result = run_eval("--runtime-log", str(log_path))

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
            compact = Path(tmp_dir) / "roles.json"

            result = run_eval("--compact-out", str(compact))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CODEX_AGENT_ROLE_EVAL=pass", result.stdout)
            self.assertIn("CODEX_AGENT_ROLE_COMPACT_OUT=", result.stdout)
            self.assertNotIn("ROLE_MODEL_MATRIX=", result.stdout)
            payload = json.loads(compact.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["finding_count"], 0)
            self.assertIn("gpt-5.6-luna", payload["model_counts"])
            self.assertNotIn("gpt-5.5", payload["model_counts"])

    def test_accumulate_writes_role_eval_report(self) -> None:
        """Role evals should accumulate through the shared eval result contract."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            results_dir = Path(tmp_dir) / "role-results"

            result = run_eval("--accumulate", "--results-dir", str(results_dir), "--run-id", "test-run")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CODEX_AGENT_ROLE_EVAL_RUN_ID=codex-agent-role-eval-", result.stdout)
            self.assertIn("CODEX_AGENT_ROLE_EVAL_ACCUMULATED_REPORT=", result.stdout)
            reports = tuple(results_dir.glob("codex-agent-role-eval-*-pass.md"))
            self.assertEqual(len(reports), 1)
            text = reports[0].read_text(encoding="utf-8")
            self.assertIn("CODEX_AGENT_ROLE_EVAL_RUN_ID=codex-agent-role-eval-", text)
            self.assertIn("run_id: `test-run`", text)

    def test_runtime_metrics_report_invalid_numeric_values(self) -> None:
        """Malformed metric values should produce findings instead of tracebacks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "roles.jsonl"
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

            result = run_eval("--runtime-log", str(log_path))

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
                task_catalog.replace("family: owner_bounded_change", "family: scoped_change", 1),
                encoding="utf-8",
            )

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn("CODEX_AGENT_ROLE_FINDING=routing:T1:must-use-owner-bounded-change", result.stdout)

    def test_routing_reports_missing_stage_waves(self) -> None:
        """The role evaluator should reject catalogs without topology stages."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            catalog_path = root / "agents" / "task_catalog.yaml"
            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
            del catalog["role_topology_defaults"]["stage_waves"]
            catalog_path.write_text(yaml.safe_dump(catalog), encoding="utf-8")

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=routing:role_topology_defaults:missing-stage-waves",
                result.stdout,
            )

    def test_routing_reports_malformed_stage_waves_without_traceback(self) -> None:
        """Malformed stage_waves entries should become findings instead of tracebacks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            catalog_path = root / "agents" / "task_catalog.yaml"
            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
            catalog["role_topology_defaults"]["stage_waves"][0] = "not-a-mapping"
            catalog_path.write_text(yaml.safe_dump(catalog), encoding="utf-8")

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn("malformed-stage-wave", result.stdout)
            self.assertIn("materialization-failed", result.stdout)
            self.assertNotIn("Traceback", result.stderr)

    def test_routing_reports_duplicate_stage_role(self) -> None:
        """One permanent role should not appear in multiple catalog stages."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            catalog_path = root / "agents" / "task_catalog.yaml"
            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
            evaluation_stage = next(
                stage
                for stage in catalog["role_topology_defaults"]["stage_waves"]
                if stage["id"] == "skill_evaluation"
            )
            evaluation_stage["role_ids"].append("manager")
            catalog_path.write_text(yaml.safe_dump(catalog), encoding="utf-8")

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn("duplicate-stage-role", result.stdout)

    def test_routing_reports_reversed_producer_reviewer_order(self) -> None:
        """Reviewer stages must come after their producer stages."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            catalog_path = root / "agents" / "task_catalog.yaml"
            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
            stage_waves = catalog["role_topology_defaults"]["stage_waves"]
            intake_index = next(
                index for index, wave in enumerate(stage_waves) if wave["id"] == "intake"
            )
            review_index = next(
                index
                for index, wave in enumerate(stage_waves)
                if wave["id"] == "intake_review"
            )
            stage_waves[intake_index], stage_waves[review_index] = (
                stage_waves[review_index],
                stage_waves[intake_index],
            )
            catalog_path.write_text(yaml.safe_dump(catalog), encoding="utf-8")

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn("producer-reviewer-stage-order", result.stdout)

    def test_routing_reports_missing_stage_role(self) -> None:
        """Every permanent role should appear exactly once in stage_waves."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            catalog_path = root / "agents" / "task_catalog.yaml"
            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
            final_stage = catalog["role_topology_defaults"]["stage_waves"][-1]
            final_stage["role_ids"].remove("auditor")
            catalog_path.write_text(yaml.safe_dump(catalog), encoding="utf-8")

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn("CODEX_AGENT_ROLE_FINDING=routing:auditor:missing-stage-role", result.stdout)

    def test_routing_reports_missing_skill_evaluator_stage(self) -> None:
        """The evaluator must not be exempt from executable stage topology."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            catalog_path = root / "agents" / "task_catalog.yaml"
            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
            for stage in catalog["role_topology_defaults"]["stage_waves"]:
                if "skill_evaluator" in stage["role_ids"]:
                    stage["role_ids"].remove("skill_evaluator")
            catalog_path.write_text(yaml.safe_dump(catalog), encoding="utf-8")

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=routing:skill_evaluator:missing-stage-role",
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
                role for role in config["always_on_roles"] if role["id"] == "implementer"
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
                role for role in config["specialist_roles"] if role["id"] == "experimenter"
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

    def test_materialization_rejects_skill_evaluator_fallback_for_ordinary_role(self) -> None:
        """Unavailable ordinary candidates cannot fall through to the evaluator."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            config_path = root / "agents" / "agents_config.json"
            config_raw = json.loads(config_path.read_text(encoding="utf-8"))
            experimenter_raw = next(
                role
                for role in config_raw["specialist_roles"]
                if role["id"] == "experimenter"
            )
            experimenter_raw["codex_agents"].append("skill_evaluator")
            config_path.write_text(json.dumps(config_raw), encoding="utf-8")
            (root / ".codex" / "agents" / "experiment_runner.toml").unlink()
            (root / ".codex" / "agents" / "worker.toml").unlink()
            config = load_team_config(config_path)
            catalog = load_task_catalog(config, root=root)
            roles = select_roles(
                config,
                ["experimenter"],
                full_team=False,
                catalog=catalog,
                workflow_family_id="research_driven_change",
            )
            initial_wave = recommended_initial_subagent_wave(
                roles,
                4,
                catalog,
                agent_root=root / ".codex" / "agents",
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "experimenter codex_agents must not include skill_evaluator",
            ):
                recommended_dynamic_expansion_wave_slots(
                    roles,
                    4,
                    initial_wave,
                    catalog,
                    agent_root=root / ".codex" / "agents",
                )

    def test_spark_model_is_reserved_for_spark_worker(self) -> None:
        """Only spark_worker should use the Spark model."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            explorer = root / ".codex" / "agents" / "explorer.toml"
            explorer.write_text(
                explorer.read_text(encoding="utf-8").replace(
                    'model = "gpt-5.6-luna"',
                    'model = "gpt-5.3-codex-spark"',
                ),
                encoding="utf-8",
            )

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=model-settings:explorer:"
                "spark-model-reserved-for-spark-worker",
                result.stdout,
            )

    def test_review_roles_require_luna_high(self) -> None:
        """Ordinary reviewer roles cannot claim the T14 mini exception."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            copy_eval_root(root)
            python_reviewer = root / ".codex" / "agents" / "python_reviewer.toml"
            python_reviewer.write_text(
                python_reviewer.read_text(encoding="utf-8")
                .replace('model = "gpt-5.6-luna"', 'model = "gpt-5.4-mini"')
                .replace('model_reasoning_effort = "high"', 'model_reasoning_effort = "medium"'),
                encoding="utf-8",
            )

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=model-settings:python_reviewer:"
                "skill-validation-model-reserved-for-skill-evaluator-t14",
                result.stdout,
            )
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=model-settings:python_reviewer:expected-model-gpt-5.6-luna",
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
                    'model = "gpt-5.6-luna"',
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
