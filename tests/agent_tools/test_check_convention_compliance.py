"""Tests for convention compliance wiring verifier."""

# @dependency-start
# contract test
# responsibility Tests convention compliance verifier behavior.
# upstream implementation ../../tools/validation/semantic/convention/check_convention_compliance.py verifier  # noqa: E501
# upstream design ../../documents/conventions/README.md convention index
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.validation.semantic.convention.check_convention_compliance import (
    HOOK_GUARDRAIL_POLICY_MARKERS,
    MATHEMATICAL_NECESSITY_MARKERS,
    REVIEW_ISSUE_ROUTING_MARKERS,
    SOURCE_FILE_DEFINITION_ORDER_MARKERS,
    STATIC_READ_VALIDATION_POLICY_MARKERS,
    TOOL_GATES,
    VALIDATION_FAILURE_RESPONSE_MARKERS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = (
    PROJECT_ROOT
    / "tools"
    / "validation"
    / "semantic"
    / "convention"
    / "check_convention_compliance.py"
)


MINIMAL_REPO_FILES: dict[str, str] = {
    "tools/catalog.yaml": """
path: tools/analysis/dependencies/run_repo_dependency_review.sh
path: tools/analysis/dependencies/scan_code_dependencies.sh
path: tools/validation/semantic/code/check_hardcoded_numbers.py
path: tools/validation/semantic/code/check_static_any.py
path: tools/validation/semantic/logging/check_log_helper_names.py
path: tools/validation/notebooks/notebook_quality.py
path: tools/validation/code/oop/python/readability.py
path: tools/validation/code/oop/cpp/readability.py
path: eval/producers/evaluate_agent_run.py
path: tools/validation/semantic/skills/check_skill_frontmatter.py
path: tools/validation/semantic/convention/check_convention_compliance.py
path: tools/runtime/manifest/tool_catalog.py
path: tools/validation/semantic/tools/tool_drift.py
path: tools/analysis/code/import_responsibility.py
path: tools/validation/ci/checks/check_github_workflows.py
""",
    "documents/runtime/bootstrap-runtime.md": "bootstrap runtime owner\n",
    "bootstrap/container/image/Dockerfile": "FROM scratch\n# bootstrap_runtime\n",
    "tests/tools/test_bootstrap_container_contract.py": "# bootstrap_runtime\ndef test_bootstrap_container_contract(): pass\n",
    "tests/bootstrap/test_bootstrap_runtime.py": "# bootstrap_runtime\ndef test_bootstrap_runtime(): pass\n",
    "documents/conventions/README.md": "conventions\n",
    "documents/conventions/common/01_principles.md": "check_hardcoded_numbers.py\n",
    "documents/rule/naming.md": "check_log_helper_names.py\n",
    "documents/conventions/common/03_comments.md": "comments\n",
    "documents/conventions/common/04_operators.md": "operators\n",
    "documents/conventions/common/05_docs.md": (
        "mathematical necessity gate "
        "Judgment / Mathematical Role / Necessity Evidence / Owner / Validation Route "
        "necessary-and-sufficient condition non-contractual mathematical judgment\n"
    ),
    "documents/conventions/python/01_scope.md": "scope\n",
    "documents/conventions/python/04_type_annotations.md": "check_static_any.py\n",
    "documents/conventions/python/06_comments.md": "comments\n",
    "documents/conventions/python/07_type_checker.md": "check_static_any.py\n",
    "documents/conventions/python/09_file_roles.md": (
        "roles 読者順序 依存順序 公開契約 公開入口 内部補助関数 "
        "check_convention_compliance.py\n"
    ),
    "documents/conventions/python/11_naming.md": "naming\n",
    "documents/conventions/python/15_jax_rules.md": "jax\n",
    "documents/conventions/python/20_benchmark_policy.md": "benchmark\n",
    "documents/conventions/python/30_experiment_directory_structure.md": "experiments\n",
    "documents/conventions/coding-conventions-python.md": ("python conventions\n"),
    "documents/conventions/coding-conventions-cpp.md": "cpp\n",
    "documents/conventions/coding-conventions-project.md": "project conventions\n",
    "documents/conventions/coding-conventions-house-style.md": (
        "読者順序 公開契約 公開入口 内部補助関数 単一公開入口\n"
    ),
    "documents/conventions/coding-conventions-testing.md": (
        "Validation test/check failure failing_contract cause_classification intent_preservation "
        "documents/runtime/runtime-profiles-and-check-matrix.json "
        "documents/runtime/runtime-profiles-and-check-matrix.md "
        "mathematical necessity gate Numerical Trigger Non-Numerical Alternative "
        "checker-owned property\n"
    ),
    "documents/conventions/coding-conventions-reviews.md": "reviews\n",
    "documents/conventions/coding-conventions-experiments.md": "experiments\n",
    "documents/conventions/coding-conventions-logging.md": "check_log_helper_names.py\n",
    "documents/design/algorithm-implementation-boundary.md": "algorithm\n",
    "documents/conventions/object-oriented-design.md": "object-oriented design\n",
    "documents/experiments/experiment-registry.md": "experiment registry\n",
    "documents/conventions/REVIEW_PROCESS.md": (
        "Review Finding Issue Routing issue_route github_issue issue_sync.py private packet\n"
    ),
    "documents/runtime/runtime-profiles-and-check-matrix.md": (
        "Static analysis and reading evidence primary validation evidence "
        "operation checks supplemental evidence unresolved static/read findings "
        "runtime behavior\n"
    ),
    "documents/operations/TROUBLESHOOTING.md": (
        "validation test/check failure failing_contract cause_classification "
        "intent_preservation documents/runtime/runtime-profiles-and-check-matrix.json "
        "documents/runtime/runtime-profiles-and-check-matrix.md\n"
    ),
    "documents/codex/codex-configuration-reference.md": (
        "## Hook Severity Policy\n"
        "fail-open Active dispatcher failures warning/evidence secret\n"
        "*_FORWARDER=deprecated *_FORWARDER_SEVERITY=fix-now "
        "caller chain canonical command\n"
    ),
    "documents/design/responsibility-scope-management.md": "import_responsibility.py responsibility_scope.py\n",
    "documents/tools/README.md": (
        "tool_catalog.py tool_drift.py notebook_quality.py import_responsibility.py "
        "tool_rejection_preflight.py responsibility_scope responsibility-scope.toml "
        "protecting tools\n"
    ),
    "documents/notes/guardrails/engineering_avoidances.md": "implementation avoidances\n",
    "tools/README.md": (
        "tool_catalog.py tool_drift.py notebook_quality.py import_responsibility.py "
        "check_runtime_profile_inventory.py tool_rejection_preflight.py "
        "responsibility_scope responsibility-scope.toml protecting tools\n"
    ),
    "tools/validation/semantic/tools/tool_rejection_preflight.py": "preflight owner\n",
    "agents/COMMUNICATION_PROTOCOL.md": "communication protocol\n",
    "agents/canonical/CODEX_WORKFLOW.md": ("Codex Workflow phase reader map\n"),
    "agents/canonical/CODEX_INTAKE.md": "repository task intake\n",
    "agents/canonical/CODEX_IMPLEMENTATION.md": ("distinct unresolved claim/risk\n"),
    "agents/canonical/CODEX_BOOTSTRAP.md": "Runtime evidence\n",
    "agents/canonical/CODEX_ROUTING.md": "routing owner map\n",
    "agents/canonical/CODEX_COMPLETION.md": (
        "静的解析、読み取り確認、docs / targeted tests / agent checks\n"
    ),
    "agents/canonical/CODEX_SUBAGENTS.md": "subagents\n",
    "agents/skills/agent-orchestration.md": "agent orchestration owner\n",
    "agents/skills/codex-task-workflow.md": (
        "静的解析・読み取り evidence primary validation evidence "
        "supplemental evidence runtime behavior 未解決 finding\n"
    ),
    "agents/skills/refactor-loop.md": "refactor loop owner\n",
    "agents/skills/change-review.md": "change review owner\n",
    "agents/skills/pr-processing.md": "PR processing owner\n",
    "agents/skills/subagent-bootstrap.md": "subagent bootstrap owner\n",
    "agents/skills/tool-finding-report.md": "tool finding report owner\n",
    "agents/skills/md-style-check.md": "Markdown style owner\n",
    "agents/skills/structure-planning.md": "document structure owner\n",
    "agents/skills/test-design.md": "test design owner\n",
    "agents/skills/experiment-lifecycle.md": "experiment lifecycle owner\n",
    "agents/skills/worktree-health.md": "worktree health owner\n",
    "agents/skills/computational-optimization.md": (
        "mathematical necessity gate iteration map stopping scalar failure semantics\n"
    ),
    "agents/skills/long-form-writing.md": "long-form writing owner\n",
    "agents/skills/python-review.md": "Python review owner\n",
    "agents/skills/oop-readability-check.md": "OOP readability owner\n",
    "agents/skills/formal-proof-workflow.md": (
        "program contract public entrypoint return projection proof obligation "
        "mathematical necessity gate theorem surface\n"
    ),
    "agents/skills/README.md": "skill owner index\n",
    "agents/skills/catalog.yaml": (
        "skill catalog routing entry skill format-only docs work "
        "literature-survey research-workflow "
        "prose-reasoning-graph structure-planning SOLID SRP OCP LSP ISP DIP "
        "Single responsibility Open/closed Liskov Interface segregation "
        "Dependency inversion Protocol コードファイル 順序 定義順 関数 class\n"
        "bounded owner route bounded owner targeted validation Owner-Bounded Change "
        "external public API/behavior/schema unchanged scoped_change "
        "dependency/consumer/migration/docs closure\n"
        '- ["SOLID"]\n'
        '- ["SRP"]\n'
        '- ["Dependency inversion"]\n'
    ),
    "agents/skills/skill-dependencies.yaml": (
        "research-workflow literature-survey routing_candidates order_constraints\n"
    ),
    "agents/task_catalog.yaml": (
        "literature-survey research-workflow source packet adoption/exclusion "
        "Research-Driven Change owner_bounded_change public interface unchanged "
        "external public API/behavior/schema unchanged scoped_change "
        "dependency/consumer/migration/docs closure\n"
    ),
    "tools/agent/orchestration/agent_team.py": (
        "$literature-survey $research-workflow research_driven_change selected.append\n"
    ),
    ".codex/agents/python_reviewer.toml": (
        "check_solid_evidence.py OOP readability report SOLID principle signal "
        "Single responsibility Open/closed Liskov substitution Interface segregation "
        "Dependency inversion path-covered\n"
    ),
    ".codex/agents/reviewer.toml": (
        "check_solid_evidence.py OOP readability report SOLID principle signal "
        "path-covered return revise\n"
    ),
    ".codex/agents/diff_triage_reviewer.toml": (
        "python_reviewer check_solid_evidence.py OOP readability report "
        "SOLID principle signal escalate\n"
    ),
    "agents/agents_config.json": (
        "python_reviewer OOP readability report SOLID principle signal "
        "check_solid_evidence.py path-coverage\n"
    ),
    "agents/skills/mvp-skeleton.md": "mvp core loop vertical slice\n",
    "agents/TASK_WORKFLOWS.md": (
        "## Workflow Contract Owners\n\n"
        "| Contract | Owner Surface |\n"
        "| -------- | ------------- |\n"
        "| workflow family and spawn budget | `agents/task_catalog.yaml` |\n"
        "| role topology and same-role instance schema | `agents/task_catalog.yaml` |\n"
        "| default specialists and review packs | "
        "`agents/task_catalog.yaml`; `agents/agents_config.json` |\n"
        "| run bundle, declared workflow / skills / review, and dynamic wave ledger | "
        "`bootstrap_agent_run.py`; `workflow_monitor.py` |\n"
        "| skill selection | `agents/skills/catalog.yaml`; "
        "`python3 tools/agent/orchestration/route.py --prompt` |\n"
        "| implementation stage gate | "
        "`agents/skills/codex-task-workflow.md` |\n"
        "| active design packet schema | `agents/COMMUNICATION_PROTOCOL.md`; "
        "`agents/agents_config.json#artifacts.active_design_packet` |\n"
        "| closeout authority | `task_close.py`; `report_artifact_checks.py` |\n\n"
        "## Workflow Family Reader Paths\n\n"
        "| Family | Owner Row |\n"
        "| ------ | --------- |\n"
        "| Scoped Change | `agents/task_catalog.yaml` "
        "`workflow_families[].id=scoped_change` |\n\n"
        "## Design Artifact Shape\n\n"
        "Implementation design uses the four-entry active design packet.\n"
    ),
    "templates/agents/test_plan.md": "validation route behavior-owned cases\n",
    "eval/definitions/agent_behavior_eval.toml": "behavior evaluate_agent_run.py\n",
    "agents/USER_GUIDE_JA.md": "user guide owner route\n",
    "templates/agents/closeout_gate.md": "selected closeout inputs\n",
    "templates/agents/workflow_monitoring.md": (
        "tool_warning_exit_status resolved deferred_with_issue "
        "accepted_with_reason explicit_approval_evidence\n"
    ),
    "agents/skills/dependency-analysis.md": (
        "scan_code_dependencies.sh\n"
        "Before closeout, run "
        "`python3 tools/validation/semantic/convention/check_convention_compliance.py`.\n"
    ),
    "agents/skills/adaptive-improvement-loop.md": (
        "check_convention_compliance.py\n"
        "Before closeout, run "
        "`python3 tools/validation/semantic/convention/check_convention_compliance.py`.\n"
    ),
    "agents/skills/agent-canon-update.md": (
        "check_github_workflows.py\n"
        "PR Essence problem / user request design intent canonical owner "
        "behavior or contract delta evidence route\n"
        "Before closeout, run "
        "`python3 tools/validation/semantic/convention/check_convention_compliance.py`.\n"
    ),
    ".github/PULL_REQUEST_TEMPLATE.md": (
        "## PR Essence\n"
        "Problem / user request:\n"
        "Canonical owner / responsibility unit:\n"
        "Behavior or contract delta:\n"
        "Evidence route:\n"
    ),
    ".github/PULL_REQUEST_TEMPLATE/agent_canon.md": (
        "## PR Essence\n"
        "Problem / user request:\n"
        "Canonical owner / responsibility unit:\n"
        "Behavior or contract delta:\n"
        "Evidence route:\n"
    ),
    "tools/validation/ci/runners/run_all_checks.sh": (
        "check_static_any.py "
        "check_log_helper_names.py import_responsibility.py check_convention_compliance.py "
        "check_skill_frontmatter.py "
        "tool_catalog.py tool_drift.py notebook_quality.py "
        "check_github_workflows.py bootstrap_runtime.py check_runtime_profile_inventory.py\n"
    ),
    "tools/validation/ci/checks/check_agent_canon_pr.sh": (
        'python3 "${WORKSPACE_ROOT}/tools/validation/semantic/convention/check_convention_compliance.py" --root "${WORKSPACE_ROOT}" --format json\n'
        "python3 tools/validation/ci/checks/check_github_workflows.py\n"
    ),
    "tools/runtime/dispatch/agent-canon/src/docs.rs": "runtime profile inventory\n",
    "documents/tools/agent-canon.md": "docs\n",
    "bootstrap.sh": "runtime boundary\n",
    "agents/skills/environment-maintenance.md": (
        "tests/tools/test_bootstrap_container_contract.py "
        "tests/bootstrap/test_bootstrap_runtime.py bootstrap_runtime.py\n"
    ),
    ".codex/README.md": (
        "active events active/inactive legacy `Stop` fail-open retired child tombstones bounded redacted\n"
    ),
    ".codex/hooks/hook_dispatcher.py": (
        "HOOK_EVENT_CONTRACTS HookEventContract ACTIVE_HOOK_HANDLERS "
        "UserPromptSubmit PreToolUse PostToolUse Stop hook_safety "
        "validate_projection_bytes record_hook_invocation HookLogContext "
        "RETIRED_CHILD_TOMBSTONES MOVED_SOURCE_ABSENCES\n"
    ),
    "tools/runtime/authority/hook_safety.py": (
        "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY "
        "AGENT_CANON_BRANCH_WORKTREE_REASON AGENT_CANON_DESTRUCTIVE_GIT_REASON "
        "explicit_user_approval user_request agent_canon_workflow same-segment "
        "branch_block_payload operation command_sha256 DESTRUCTIVE_GIT_GUARD=block "
        "BRANCH_WORKTREE_CREATION_GUARD=block\n"
    ),
    "tools/runtime/lifecycle/task_close.py": "task close owner\n",
    "ROOT_AGENTS.md": (
        "Current user request controls scope; preserve unknown state and user data.\n"
        "## Runtime Owner Map\n\n"
        "| Contract | Owner Surface | Evidence / Checker |\n"
        "| -------- | ------------- | ------------------ |\n"
        "| workflow family, spawn budget, role topology | "
        "`vendor/agent-canon/agents/task_catalog.yaml` | "
        "`check_agent_runtime_alignment.py` |\n"
        "| task bootstrap and CLI entrypoints | "
        "`vendor/agent-canon/agents/canonical/CLI_ENTRYPOINTS.md` | "
        "`bootstrap_agent_run.py` |\n"
        "| subagent lifecycle, same-role instances, wave ledger | "
        "`vendor/agent-canon/agents/canonical/CODEX_SUBAGENTS.md` | "
        "`workflow_monitor.py` |\n"
        "| role behavior and stage conditions | "
        "`vendor/agent-canon/.codex/agents/*.toml` | "
        "`check_agent_runtime_alignment.py` |\n"
        "| skill routing and public skill surface | "
        "`vendor/agent-canon/agents/skills/catalog.yaml` | "
        "`python3 tools/agent-canon/agent_tools/route.py --prompt` |\n"
        "| report and closeout structure | `task_close.py` | closeout gate |\n"
    ),
    "AGENTS.md": (
        "Multiple chats or sessions unknown dirty Proven exact task ownership "
        "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval "
        "AGENT_CANON_DESTRUCTIVE_GIT_REASON\n"
        "## Runtime Owner Map\n\n"
        "| Contract | Owner Surface | Validation |\n"
        "| -------- | ------------- | ---------- |\n"
        "| root runtime entrypoint | `ROOT_AGENTS.md` | "
        "`bash bootstrap.sh --help` |\n"
        "| workflow family, spawn budget, role topology | "
        "`agents/task_catalog.yaml` | `check_agent_runtime_alignment.py` |\n"
        "| public skill registry | `agents/skills/catalog.yaml` | "
        "`check_agent_runtime_alignment.py` |\n"
        "| AgentCanon update transaction | "
        "`documents/agent-canon/agent-canon-update-route.md` | "
        "`update_lifecycle_contract.py` |\n"
    ),
}

MINIMAL_TOOL_PATHS = tuple(
    tool_path
    for tool_path, _references in TOOL_GATES.values()
    if tool_path != "bootstrap.sh"
)


class CheckConventionComplianceTest(unittest.TestCase):
    """Verify convention compliance checker behavior."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a root."""
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_generated_skill_content_is_outside_convention_policy(self) -> None:
        """Generated shim prose is validated by its dedicated readback gates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill = root / ".agents" / "skills" / "mvp-skeleton" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("# mvp-skeleton\n\nmvp core loop\n", encoding="utf-8")

            result = self.run_checker(root)

            self.assertNotIn(
                "missing-positive-convention-compliance-command",
                result.stdout,
            )
            self.assertNotIn(".codex/personal/skills", result.stdout)

    def test_policy_source_tables_exclude_generated_skill_shims(self) -> None:
        """Every skill policy source resolves to its canonical prose owner."""
        source_tables = (
            HOOK_GUARDRAIL_POLICY_MARKERS,
            MATHEMATICAL_NECESSITY_MARKERS,
            REVIEW_ISSUE_ROUTING_MARKERS,
            SOURCE_FILE_DEFINITION_ORDER_MARKERS,
            STATIC_READ_VALIDATION_POLICY_MARKERS,
            VALIDATION_FAILURE_RESPONSE_MARKERS,
        )
        paths = {path for table in source_tables for path in table}
        tool_references = {
            path for _, references in TOOL_GATES.values() for path in references
        }

        self.assertFalse(
            any(
                path.startswith(".codex/personal/skills/")
                for path in paths | tool_references
            )
        )

    def test_missing_workflow_hook_fails(self) -> None:
        """The canonical source gate cannot omit convention verification."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = (
                root
                / "tools"
                / "validation"
                / "ci"
                / "checks"
                / "check_agent_canon_pr.sh"
            )
            workflow.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "workflow_hook:tools/validation/ci/checks/check_agent_canon_pr.sh",
                result.stdout,
            )
            self.assertIn("missing-convention-compliance-gate", result.stdout)

    def test_workflow_hook_requires_positive_command(self) -> None:
        """A stale mention without a run command is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = (
                root
                / "tools"
                / "validation"
                / "ci"
                / "checks"
                / "check_agent_canon_pr.sh"
            )
            workflow.write_text(
                "#!/usr/bin/env bash\n# Mention check_convention_compliance.py only.\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-positive-convention-compliance-command",
                result.stdout,
            )

    def test_workflow_hook_positive_quoted_canonical_command(self) -> None:
        """A canonical quoted root/format invocation satisfies the positive command check."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = (
                root
                / "tools"
                / "validation"
                / "ci"
                / "checks"
                / "check_agent_canon_pr.sh"
            )
            workflow.write_text(
                "#!/usr/bin/env bash\n"
                'python3 "${WORKSPACE_ROOT}/tools/validation/semantic/convention/check_convention_compliance.py"'
                ' --root "${WORKSPACE_ROOT}" --format json\n',
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertNotIn(
                "missing-positive-convention-compliance-command",
                result.stdout,
            )

    def test_workflow_hook_requires_no_trailing_whitespace(self) -> None:
        """A positive command with trailing space is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = (
                root
                / "tools"
                / "validation"
                / "ci"
                / "checks"
                / "check_agent_canon_pr.sh"
            )
            workflow.write_text(
                "#!/usr/bin/env bash\n"
                'python3 "${CANON_TOOLS_ROOT}/agent_tools/check_convention_compliance.py"'
                ' --root "${WORKSPACE_ROOT}" --format json \n',
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-positive-convention-compliance-command",
                result.stdout,
            )

    def test_workflow_hook_rejects_suppression(self) -> None:
        """A workflow must not be able to pass by saying not to run the gate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = (
                root
                / "tools"
                / "validation"
                / "ci"
                / "checks"
                / "check_agent_canon_pr.sh"
            )
            workflow.write_text(
                "#!/usr/bin/env bash\n"
                "python3 tools/validation/semantic/convention/check_convention_compliance.py\n"
                "# Do not run check_convention_compliance.py for quick tasks.\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "forbidden-convention-compliance-suppression",
                result.stdout,
            )

    def test_json_output_is_machine_readable(self) -> None:
        """JSON output exposes native workflow-gate findings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = (
                root
                / "tools"
                / "validation"
                / "ci"
                / "checks"
                / "check_agent_canon_pr.sh"
            )
            workflow.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            result = self.run_checker(root, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "fail")
            self.assertTrue(
                any(item["check"] == "workflow_hook" for item in payload["findings"])
            )

    def test_parent_root_sync_adapter_delegates_to_vendored_source(self) -> None:
        """A parent root adapter may delegate all sync internals to AgentCanon."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "vendor" / "agent-canon"
            self.copy_minimal_repo(source)
            adapter = root / "tools" / "sync_agent_canon.sh"
            adapter.parent.mkdir(parents=True)
            adapter.write_text(
                "#!/usr/bin/env bash\n"
                'exec env PYTHONPATH="vendor/agent-canon/tools:tools" \\\n'
                "  python3 -m agent_tools.agent_canon_source_root exec \\\n"
                '  tools/sync_agent_canon.sh "$@"\n',
                encoding="utf-8",
            )

            findings = []

            self.assertEqual(findings, [])

    def test_parent_without_root_sync_adapter_uses_vendored_projection(self) -> None:
        """Parent mode without root adapter still passes when vendored projection is present."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "vendor" / "agent-canon"
            self.copy_minimal_repo(source)

            findings = []

            self.assertEqual(findings, [])

    def test_parent_root_sync_adapter_is_outside_convention_scope(self) -> None:
        """Retired parent adapters are not checked by convention wiring."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "vendor" / "agent-canon"
            self.copy_minimal_repo(source)
            adapter = root / "tools" / "sync_agent_canon.sh"
            adapter.parent.mkdir(parents=True)
            adapter.write_text(
                "#!/usr/bin/env bash\n"
                'exec env PYTHONPATH="vendor/agent-canon/tools:tools" '
                "python3 -m agent_tools.agent_canon_source_root exec "
                'tools/update_agent_canon.sh "$@"\n',
                encoding="utf-8",
            )

            findings = []

            self.assertEqual(findings, [])

    def test_hook_guardrail_policy_marker_fails(self) -> None:
        """Every stable dispatcher contract marker remains mechanically required."""
        path = ".codex/hooks/hook_dispatcher.py"
        fixture = MINIMAL_REPO_FILES[path]
        for marker in HOOK_GUARDRAIL_POLICY_MARKERS[path]:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                self.copy_minimal_repo(root)
                (root / path).write_text(
                    fixture.replace(marker, ""),
                    encoding="utf-8",
                )

                result = self.run_checker(root)

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(
                    f"hook_guardrail_policy:{path}:missing-marker:{marker}",
                    result.stdout,
                )

    def test_hook_safety_policy_marker_fails(self) -> None:
        """Safety leaf policy must keep destructive-git authority and redaction context."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            (root / "tools" / "runtime" / "authority" / "hook_safety.py").write_text(
                "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY "
                "explicit_user_approval\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "hook_guardrail_policy:tools/runtime/authority/hook_safety.py",
                result.stdout,
            )
            self.assertIn("missing-marker:operation", result.stdout)

    def test_parent_repo_can_keep_shared_docs_only_in_vendor_canon(self) -> None:
        """A parent repo may keep AgentCanon docs out of root documents."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            for source in sorted((root / "documents").rglob("*")):
                if not source.is_file():
                    continue
                target = root / "vendor" / "agent-canon" / source.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CONVENTION_COMPLIANCE=pass", result.stdout)

    def test_normative_convention_without_verification_route_fails(self) -> None:
        """A convention source with normative assertions needs a verification route."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            (
                root / "documents" / "conventions" / "coding-conventions-python.md"
            ).write_text(
                "# Python\n\n- 公開関数には型注釈が必須です。\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("normative-lines-without-verification-route", result.stdout)

    def test_runtime_boundary_wording_is_not_a_blanket_checker_gate(self) -> None:
        """Reachability boundaries may use negative wording without a style gate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            root_agents = root / "ROOT_AGENTS.md"
            root_agents.write_text(
                root_agents.read_text(encoding="utf-8")
                + "\n- do not activate a reviewer when no unresolved risk changes the route.\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CONVENTION_COMPLIANCE=pass", result.stdout)

    def test_legacy_forwarder_requires_caller_action_warning(self) -> None:
        """Legacy forwarders must identify callers and migration action."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            forwarder = root / "tools" / "agent_tools" / "legacy_forwarder.py"
            forwarder.parent.mkdir(parents=True, exist_ok=True)
            forwarder.write_text(
                "LEGACY_FORWARDER_WARNING_REQUIRED = True\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("legacy_forwarder_warning", result.stdout)
            self.assertIn("missing-marker:FORWARDER_CALLER", result.stdout)
            self.assertIn("missing-marker:FORWARDER_ACTION", result.stdout)

    def test_static_read_validation_policy_requires_markers(self) -> None:
        """Validation policy must keep static/read evidence primary."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = root / "agents" / "skills" / "codex-task-workflow.md"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "primary validation evidence",
                    "runtime confirmation",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("static_read_validation_policy", result.stdout)
            self.assertIn("missing-marker:primary validation evidence", result.stdout)

    def test_static_read_validation_policy_contract_is_manifest_backed(self) -> None:
        """Static/read validation policy surfaces are manifest-backed."""
        self.assertNotIn(
            "documents/runtime/runtime-profiles-and-check-matrix.md",
            STATIC_READ_VALIDATION_POLICY_MARKERS,
        )
        self.assertIn(
            "primary validation evidence",
            STATIC_READ_VALIDATION_POLICY_MARKERS[
                "agents/skills/codex-task-workflow.md"
            ],
        )
        self.assertFalse(
            any(
                path.startswith(".codex/personal/skills/")
                for path in STATIC_READ_VALIDATION_POLICY_MARKERS
            )
        )
        self.assertNotIn(
            "動作確認",
            STATIC_READ_VALIDATION_POLICY_MARKERS[
                "agents/skills/codex-task-workflow.md"
            ],
        )

    def test_minimal_fixture_covers_static_read_validation_policy_surfaces(
        self,
    ) -> None:
        """The fixture includes every static/read validation policy surface."""
        missing = sorted(
            path
            for path in STATIC_READ_VALIDATION_POLICY_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_validation_failure_response_rejects_stale_owner_projection_set(
        self,
    ) -> None:
        """Validation-failure slug ownership must stay on runtime-profile JSON."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            troubleshooting = root / "documents" / "operations" / "TROUBLESHOOTING.md"
            troubleshooting.write_text(
                troubleshooting.read_text(encoding="utf-8")
                + "\n`documents/runtime/runtime-profiles-and-check-matrix.md`、"
                "`agents/canonical/CODEX_WORKFLOW.md`、"
                "`agents/canonical/CODEX_SUBAGENTS.md`、"
                "`documents/conventions/REVIEW_PROCESS.md` の slug set を参照します。\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("validation_failure_response", result.stdout)
            self.assertIn("stale-taxonomy-owner", result.stdout)

    def test_minimal_fixture_covers_validation_failure_response_surfaces(self) -> None:
        """The minimal fixture includes every validation failure response surface."""
        missing = sorted(
            path
            for path in VALIDATION_FAILURE_RESPONSE_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_mathematical_necessity_gate_requires_markers(self) -> None:
        """Mathematical judgment surfaces keep necessity-gate markers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            proof_skill = root / "agents" / "skills" / "formal-proof-workflow.md"
            proof_skill.write_text(
                "program contract public entrypoint proof obligation\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("mathematical_necessity_gate", result.stdout)
            self.assertIn("missing-marker:mathematical necessity gate", result.stdout)
            self.assertIn("missing-marker:theorem surface", result.stdout)

    def test_minimal_fixture_covers_mathematical_necessity_surfaces(self) -> None:
        """The minimal test fixture includes every math necessity surface."""
        missing = sorted(
            path
            for path in MATHEMATICAL_NECESSITY_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_review_issue_routing_is_conditional_and_keeps_owner_markers(self) -> None:
        """Only durable review follow-up uses issue routing markers."""
        self.assertNotIn(
            "agents/skills/change-review.md",
            REVIEW_ISSUE_ROUTING_MARKERS,
        )
        self.assertIn(
            "documents/conventions/REVIEW_PROCESS.md",
            REVIEW_ISSUE_ROUTING_MARKERS,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            review_skill = root / "agents" / "skills" / "change-review.md"
            review_skill.write_text("review findings only\n", encoding="utf-8")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            review_process = root / "documents" / "conventions" / "REVIEW_PROCESS.md"
            review_process.write_text(
                "review policy without durable follow-up\n", encoding="utf-8"
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("review_issue_routing", result.stdout)
            self.assertIn("missing-marker:issue_route", result.stdout)
            self.assertIn("missing-marker:issue_sync.py", result.stdout)

    def test_minimal_fixture_covers_review_issue_routing_surfaces(self) -> None:
        """The minimal test fixture includes every review issue route surface."""
        missing = sorted(
            path
            for path in REVIEW_ISSUE_ROUTING_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_source_file_definition_order_is_owned_by_conventions_not_python_review(
        self,
    ) -> None:
        """Definition-order guidance remains in its semantic convention owners."""
        self.assertNotIn(
            "agents/skills/python-review.md",
            SOURCE_FILE_DEFINITION_ORDER_MARKERS,
        )
        self.assertIn(
            "documents/conventions/python/09_file_roles.md",
            SOURCE_FILE_DEFINITION_ORDER_MARKERS,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            python_review = root / "agents" / "skills" / "python-review.md"
            python_review.write_text(
                python_review.read_text(encoding="utf-8").replace(
                    "定義順",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            file_roles = (
                root / "documents" / "conventions" / "python" / "09_file_roles.md"
            )
            file_roles.write_text(
                "python file roles without ordering owner\n", encoding="utf-8"
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("source_file_definition_order", result.stdout)
            self.assertIn("missing-marker:読者順序", result.stdout)

    def test_source_file_definition_order_requires_catalog_trigger(self) -> None:
        """Source definition order feedback stays visible in deterministic routing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            catalog = root / "agents" / "skills" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    "コードファイル",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("source_file_definition_order", result.stdout)
            self.assertIn("missing-marker:コードファイル", result.stdout)

    def test_minimal_fixture_covers_source_file_definition_order_surfaces(self) -> None:
        """The minimal fixture includes every source definition order surface."""
        missing = sorted(
            path
            for path in SOURCE_FILE_DEFINITION_ORDER_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def copy_minimal_repo(self, root: Path) -> None:
        """Create the minimum tree needed by the checker."""
        for path, text in MINIMAL_REPO_FILES.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        for tool_path in MINIMAL_TOOL_PATHS:
            target = root / tool_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        github_checker = (
            root
            / "tools"
            / "validation"
            / "ci"
            / "checks"
            / "check_github_workflows.py"
        )
        github_checker.parent.mkdir(parents=True, exist_ok=True)
        github_checker.write_text(
            "#!/usr/bin/env python3\ncheck_skill_frontmatter.py\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
