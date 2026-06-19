"""Tests for convention compliance wiring verifier."""

# @dependency-start
# responsibility Tests convention compliance verifier behavior.
# upstream implementation ../../tools/agent_tools/check_convention_compliance.py verifier  # noqa: E501
# upstream design ../../documents/conventions/README.md convention index
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.agent_tools.check_convention_compliance import (
    AGENT_CANON_PUSH_REMOTE_MARKERS,
    DOCUMENT_CLAIM_GROUNDING_MARKERS,
    DOCUMENT_STRUCTURE_ROUTING_MARKERS,
    OWNER_MAP_ENTRYPOINT_MARKERS,
    POSITIVE_RUNTIME_WORDING_SURFACES,
    TEST_CONTRACT_ROUTING_MARKERS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "check_convention_compliance.py"

MINIMAL_REPO_FILES: dict[str, str] = {
    "documents/conventions/README.md": "conventions\n",
    "documents/conventions/common/01_principles.md": "check_hardcoded_numbers.py\n",
    "documents/conventions/common/02_naming.md": "check_log_helper_names.py\n",
    "documents/conventions/common/03_comments.md": "comments\n",
    "documents/conventions/common/04_operators.md": "operators\n",
    "documents/conventions/common/05_docs.md": (
        "docs claim grounding program contract public entrypoint "
        "return projection proof obligation provisional wording "
        "check_convention_compliance.py\n"
    ),
    "documents/conventions/python/01_scope.md": "scope\n",
    "documents/conventions/python/04_type_annotations.md": "check_static_any.py\n",
    "documents/conventions/python/06_comments.md": "comments\n",
    "documents/conventions/python/07_type_checker.md": "check_static_any.py\n",
    "documents/conventions/python/09_file_roles.md": "roles\n",
    "documents/conventions/python/11_naming.md": "naming\n",
    "documents/conventions/python/15_jax_rules.md": "jax\n",
    "documents/conventions/python/20_benchmark_policy.md": "benchmark\n",
    "documents/conventions/python/30_experiment_directory_structure.md": "experiments\n",
    "documents/coding-conventions-python.md": "python import_responsibility.py\n",
    "documents/coding-conventions-cpp.md": "cpp\n",
    "documents/coding-conventions-project.md": (
        "project container_config.py claim grounding program contract proof obligation "
        "run-local planning evidence\n"
    ),
    "documents/coding-conventions-house-style.md": "house\n",
    "documents/coding-conventions-testing.md": (
        "testing contract-only wrapper static contract validation "
        "static-analysis-duplicate-test canonical command Validation repair scope\n"
    ),
    "documents/coding-conventions-reviews.md": "reviews\n",
    "documents/coding-conventions-experiments.md": "experiments\n",
    "documents/coding-conventions-logging.md": "check_log_helper_names.py\n",
    "documents/algorithm-implementation-boundary.md": "algorithm\n",
    "documents/object-oriented-design.md": "readability.py\n",
    "documents/REVIEW_PROCESS.md": (
        "review structure-planning prose-reasoning-graph md-style-check "
        "structure_contract=skipped\n"
    ),
    "documents/SHARED_RUNTIME_SURFACES.md": (
        "surface_manifest.py documents/shared-runtime-surfaces.toml owner class\n"
        ".codex/hooks.json .codex/hooks .devcontainer/ .vscode/ documents/README.md "
        "documents/template-bootstrap.md "
        "documents/github-first-module-and-devcontainer-policy.md "
        "memory/USER_PREFERENCES.md "
        "tests/agent_tools/ Root `tools/` is a symlink view "
        "vendor/agent-canon/tools/ "
        "Project-local automation must stay in project-owned paths\n"
    ),
    "documents/shared-runtime-surfaces.toml": (
        'mode = "standalone_only"\n'
        'owner = "agent-canon-standalone"\n'
        'path = "goal.md"\n'
        '"documents/README.md"\n'
        '"documents/template-bootstrap.md"\n'
        '".devcontainer"\n'
        '".vscode"\n'
        '"documents/github-first-module-and-devcontainer-policy.md"\n'
        '".codex/hooks.json"\n'
        '"tests/agent_tools/test_check_convention_compliance.py"\n'
    ),
    "documents/agent-canon-parent-repo-latest-checklist.md": "checklist\n",
    "documents/codex-configuration-reference.md": (
        "## Hook Severity Policy\n"
        "fail-open CRITICAL_BLOCKING_CHILD_HOOKS warning/evidence\n"
        "*_FORWARDER=deprecated *_FORWARDER_SEVERITY=fix-now "
        "caller chain canonical command\n"
    ),
    "documents/responsibility-scope-management.md": "import_responsibility.py responsibility_scope.py\n",
    "documents/tools/README.md": "tool_catalog.py tool_drift.py notebook_quality.py import_responsibility.py\n",
    "tools/README.md": (
        "tool_catalog.py tool_drift.py notebook_quality.py import_responsibility.py "
        "check_runtime_profile_inventory.py\n"
    ),
    "agents/canonical/CODEX_WORKFLOW.md": (
        "Completion Readiness\n"
        "user-facing completion\n"
        "repo_wide_static_analysis_complete\n"
        "repo_wide_dependency_tools_complete\n"
        "run_repo_dependency_review.sh\n"
        "contract-only wrapper static contract validation canonical command evidence "
        "validation tool\n"
    ),
    "agents/canonical/CODEX_SUBAGENTS.md": "subagents\n",
    "agents/workflows/example-workflow.md": (
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
    ),
    "agents/workflows/long-form-writing-workflow.md": (
        "$structure-planning $prose-reasoning-graph $md-style-check "
        "structure_contract=skipped\n"
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
    ),
    ".agents/skills/agent-orchestration/SKILL.md": (
        "$agent-orchestration $codex-task-workflow $subagent-bootstrap "
        "task-shape skill check_convention_compliance.py vertical dynamic wave "
        "write-capable handoff $prose-reasoning-graph $structure-planning "
        "$md-style-check format-only structure_contract=skipped\n"
    ),
    ".agents/skills/codex-task-workflow/SKILL.md": (
        "codex task workflow prose-reasoning-graph $structure-planning "
        "$md-style-check format-only structure_contract=skipped\n"
    ),
    ".agents/skills/md-style-check/SKILL.md": (
        "$prose-reasoning-graph $structure-planning format-only "
        "structure_contract=skipped\n"
    ),
    ".agents/skills/test-design/SKILL.md": (
        "contract-only wrapper static contract validation canonical command evidence "
        "observable behavior validation repair scope\n"
    ),
    ".agents/skills/mvp-skeleton/SKILL.md": "mvp core loop vertical slice\n",
    "agents/skills/agent-orchestration.md": (
        "$agent-orchestration $codex-task-workflow $subagent-bootstrap "
        "task-shape skill check_convention_compliance.py vertical dynamic wave "
        "write-capable handoff prose-reasoning-graph structure-planning "
        "md-style-check format-only structure_contract=skipped\n"
    ),
    "agents/skills/codex-task-workflow.md": (
        "codex task workflow prose-reasoning-graph structure-planning "
        "md-style-check format-only structure_contract=skipped\n"
    ),
    "agents/skills/md-style-check.md": (
        "prose-reasoning-graph structure-planning format-only "
        "structure_contract=skipped\n"
    ),
    "agents/skills/test-design.md": (
        "contract-only wrapper static contract validation canonical command evidence "
        "observable behavior validation repair scope\n"
    ),
    "agents/skills/long-form-writing.md": (
        "数学的 claim program contract proof obligation $formal-proof-workflow "
        "provisional wording\n"
    ),
    ".agents/skills/long-form-writing/SKILL.md": (
        "mathematical claim program contract proof obligation $formal-proof-workflow "
        "provisional wording\n"
    ),
    "agents/skills/formal-proof-workflow.md": (
        "program contract public entrypoint return projection proof obligation\n"
    ),
    ".agents/skills/formal-proof-workflow/SKILL.md": (
        "program contract public entrypoint return projection validation command\n"
    ),
    "agents/skills/README.md": (
        "prose-reasoning-graph structure-planning md-style-check "
        "structure_contract=skipped\n"
    ),
    "agents/skills/catalog.yaml": (
        "skill catalog routing entry skill format-only docs work "
        "prose-reasoning-graph structure-planning\n"
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
        "`task_start.py`; `bootstrap_agent_run.py`; `workflow_monitor.py` |\n"
        "| skill selection | `agents/skills/catalog.yaml`; "
        "`agent-canon local-llm route-skill` |\n"
        "| implementation stage gate | "
        "`agents/workflows/implementation-waterfall-workflow.md` |\n"
        "| implementation packet schema | `agents/COMMUNICATION_PROTOCOL.md` |\n"
        "| closeout authority | `task_close.py`; `report_artifact_checks.py` |\n\n"
        "## Workflow Family Reader Paths\n\n"
        "| Family | Owner Row |\n"
        "| ------ | --------- |\n"
        "| Scoped Change | `agents/task_catalog.yaml` "
        "`workflow_families[].id=scoped_change` |\n\n"
        "Implementation Flow Graph\n"
    ),
    "agents/templates/test_plan.md": "validation route behavior-owned cases\n",
    "evidence/agent-evals/skill_workflow_prompt_eval.toml": (
        "check_convention_compliance.py CONVENTION-WORKFLOW CONVENTION-SKILL "
        "write-capable handoff\n"
        "evaluate_skill_workflow_prompts.py\n"
    ),
    "evidence/agent-evals/agent_behavior_eval.toml": "behavior evaluate_agent_run.py\n",
    "agents/USER_GUIDE_JA.md": (
        "structure-planning prose-reasoning-graph md-style-check "
        "Document Structure Evidence structure_contract=skipped\n"
    ),
    "agents/templates/closeout_gate.md": (
        "evaluate_agent_run.py run_repo_dependency_review.sh\n"
        "Document Structure Evidence document_structure_status structure_planning "
        "prose_graph md_style_check format_only_reason\n"
    ),
    "agents/workflows/hypothesis-validation-workflow.md": (
        "scan_code_dependencies.sh\n"
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
    ),
    "agents/workflows/comprehensive-refactoring-workflow.md": (
        "readability.py check_convention_compliance.py\n"
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
    ),
    "agents/workflows/adaptive-improvement-workflow.md": (
        "evaluate_skill_workflow_prompts.py check_convention_compliance.py\n"
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
    ),
    "agents/workflows/agent-canon-pr-workflow.md": (
        "check_github_workflows.py\n"
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
        + "".join(f"{marker}\n" for marker in AGENT_CANON_PUSH_REMOTE_MARKERS)
    ),
    "tools/ci/run_all_checks.sh": (
        "check_hardcoded_numbers.py check_static_any.py "
        "check_log_helper_names.py import_responsibility.py check_convention_compliance.py "
        "check_skill_frontmatter.py "
        "tool_catalog.py tool_drift.py notebook_quality.py "
        "check_github_workflows.py container_config.py check_runtime_profile_inventory.py\n"
    ),
    "rust/agent-canon/src/docs.rs": "runtime profile inventory\n",
    "documents/tools/agent-canon.md": "docs\n",
    "tools/sync_agent_canon.sh": "surface_manifest.py build_regular_specs regular_path\n",
    "agents/skills/environment-maintenance.md": "container_config.py\n",
    ".codex/README.md": (
        "dispatcher は fail-open AGENT_CANON_HOOK_STRICT_BLOCKS "
        "systemMessage hookSpecificOutput.additionalContext\n"
    ),
    ".codex/hooks/hook_dispatcher.py": (
        "CRITICAL_BLOCKING_CHILD_HOOKS STRICT_BLOCKS_ENV STRICT_FAILURES_ENV "
        "downgraded_block_payload failure_warning_payload direct_rg_context_guard.py\n"
    ),
    ".codex/hooks/direct_rg_context_guard.py": (
        "DIRECT_RG_CONTEXT_RISK=warn rg -l --max-count .agent-canon/log-archive "
        "reports *.jsonl\n"
    ),
    "tools/agent_tools/task_close.py": (
        "changed_markdown_paths Document Structure Evidence "
        "document_structure_evidence DOCUMENT_STRUCTURE_REQUIRED\n"
    ),
    "ROOT_AGENTS.md": (
        "## Runtime Owner Map\n\n"
        "| Contract | Owner Surface | Evidence / Checker |\n"
        "| -------- | ------------- | ------------------ |\n"
        "| workflow family, spawn budget, role topology | "
        "`vendor/agent-canon/agents/task_catalog.yaml` | "
        "`check_agent_runtime_alignment.py` |\n"
        "| task bootstrap and CLI entrypoints | "
        "`vendor/agent-canon/agents/canonical/CLI_ENTRYPOINTS.md` | "
        "`task_start.py`; `bootstrap_agent_run.py` |\n"
        "| subagent lifecycle, same-role instances, wave ledger | "
        "`vendor/agent-canon/agents/canonical/CODEX_SUBAGENTS.md` | "
        "`workflow_monitor.py` |\n"
        "| role behavior and stage conditions | "
        "`vendor/agent-canon/.codex/agents/*.toml` | "
        "`check_agent_runtime_alignment.py` |\n"
        "| skill routing and public skill surface | "
        "`vendor/agent-canon/agents/skills/catalog.yaml` | "
        "`agent-canon local-llm route-skill` |\n"
        "| report and closeout structure | `task_close.py` | closeout gate |\n"
    ),
    "AGENTS.md": (
        "## Runtime Owner Map\n\n"
        "| Contract | Owner Surface | Validation |\n"
        "| -------- | ------------- | ---------- |\n"
        "| root runtime entrypoint | `ROOT_AGENTS.md` | "
        "`bash tools/sync_agent_canon.sh check` |\n"
        "| workflow family, spawn budget, role topology | "
        "`agents/task_catalog.yaml` | `check_agent_runtime_alignment.py` |\n"
        "| public skill registry | `agents/skills/catalog.yaml` | "
        "`check_agent_runtime_alignment.py` |\n"
        "| shared-canon update | `tools/update_agent_canon.sh` | "
        "AgentCanon PR gate |\n"
    ),
}

MINIMAL_AGENT_TOOLS = (
    "run_repo_dependency_review.sh",
    "scan_code_dependencies.sh",
    "check_hardcoded_numbers.py",
    "check_static_any.py",
    "check_log_helper_names.py",
    "import_responsibility.py",
    "evaluate_skill_workflow_prompts.py",
    "evaluate_agent_run.py",
    "check_convention_compliance.py",
    "check_skill_frontmatter.py",
    "tool_catalog.py",
    "tool_drift.py",
    "surface_manifest.py",
    "check_runtime_profile_inventory.py",
)

MINIMAL_PYTHON_TOOLS = (
    "tools/oop/python/readability.py",
    "tools/oop/cpp/readability.py",
    "tools/validation/notebook_quality.py",
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

    def test_current_repository_passes(self) -> None:
        """The canonical repository satisfies the convention wiring gate."""
        result = self.run_checker(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CONVENTION_COMPLIANCE=pass", result.stdout)
        self.assertIn("CONVENTION_COMPLIANCE_FINDINGS=0", result.stdout)

    def test_missing_workflow_hook_fails(self) -> None:
        """A workflow prompt without the verifier marker is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = root / "agents" / "workflows" / "example-workflow.md"
            workflow.write_text("# Example\nNo verifier here.\n", encoding="utf-8")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "workflow_hook:agents/workflows/example-workflow.md",
                result.stdout,
            )
            self.assertIn("missing-convention-compliance-gate", result.stdout)

    def test_workflow_hook_requires_positive_command(self) -> None:
        """A stale mention without a run command is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = root / "agents" / "workflows" / "example-workflow.md"
            workflow.write_text(
                "# Example\nMention check_convention_compliance.py in prose only.\n",
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
            workflow = root / "agents" / "workflows" / "example-workflow.md"
            workflow.write_text(
                "# Example\n"
                "Before closeout, run "
                "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
                "Do not run check_convention_compliance.py for quick tasks.\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "forbidden-convention-compliance-suppression",
                result.stdout,
            )

    def test_json_output_is_machine_readable(self) -> None:
        """JSON output exposes status and finding records."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            manifest = root / "evidence" / "agent-evals" / "skill_workflow_prompt_eval.toml"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                "version = 1\n",
                encoding="utf-8",
            )

            result = self.run_checker(root, "--format", "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "fail")
            self.assertTrue(payload["findings"])

    def test_agentcanon_pr_workflow_requires_remote_verification_guard(self) -> None:
        """The AgentCanon PR workflow must keep every remote verification marker."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            for marker in AGENT_CANON_PUSH_REMOTE_MARKERS:
                with self.subTest(marker=marker):
                    workflow = root / "agents" / "workflows" / "agent-canon-pr-workflow.md"
                    workflow.write_text(
                        MINIMAL_REPO_FILES["agents/workflows/agent-canon-pr-workflow.md"].replace(
                            f"{marker}\n",
                            "",
                        ),
                        encoding="utf-8",
                    )

                    result = self.run_checker(root)

                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("agentcanon_push_remote_guard", result.stdout)
                    self.assertIn(f"missing-marker:{marker}", result.stdout)

    def test_missing_surface_manifest_marker_fails(self) -> None:
        """Shared surface docs must stay manifest-backed and complete."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            (root / "documents" / "SHARED_RUNTIME_SURFACES.md").write_text(
                "surface_manifest.py documents/shared-runtime-surfaces.toml\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("surface_manifest:documents/SHARED_RUNTIME_SURFACES.md", result.stdout)
            self.assertIn("missing-marker:.codex/hooks.json", result.stdout)

    def test_hook_guardrail_policy_marker_fails(self) -> None:
        """Hook severity policy must stay wired to docs and dispatcher behavior."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            (root / ".codex" / "hooks" / "hook_dispatcher.py").write_text(
                "CRITICAL_BLOCKING_CHILD_HOOKS STRICT_BLOCKS_ENV\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("hook_guardrail_policy:.codex/hooks/hook_dispatcher.py", result.stdout)
            self.assertIn("missing-marker:STRICT_FAILURES_ENV", result.stdout)

    def test_direct_rg_context_guard_policy_marker_fails(self) -> None:
        """Direct rg guard policy must stay mechanically checkable."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            (root / ".codex" / "hooks" / "direct_rg_context_guard.py").write_text(
                "DIRECT_RG_CONTEXT_RISK=warn rg -l\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("hook_guardrail_policy:.codex/hooks/direct_rg_context_guard.py", result.stdout)
            self.assertIn("missing-marker:--max-count", result.stdout)

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
            (root / "documents" / "coding-conventions-python.md").write_text(
                "# Python\n\n- 公開関数には型注釈が必須です。\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("normative-lines-without-verification-route", result.stdout)

    def test_runtime_wording_rejects_legacy_completion_blocker(self) -> None:
        """Runtime docs keep completion wording in readiness form."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = root / "agents" / "canonical" / "CODEX_WORKFLOW.md"
            workflow.write_text(
                workflow.read_text(encoding="utf-8")
                + "\n- completion report を出さない\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("positive_runtime_wording", result.stdout)
            self.assertIn("legacy-negative-runtime-wording", result.stdout)

    def test_runtime_wording_rejects_sequence_design_labels(self) -> None:
        """Runtime docs keep MVP and design routing free of sequence labels."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            cases = {
                ".agents/skills/mvp-skeleton/SKILL.md": (
                    "# MVP\nStop after the first runnable path.\n"
                ),
                "ROOT_AGENTS.md": "- first-wave target\n",
                "agents/TASK_WORKFLOWS.md": "- 最初の作業 update\n",
                "agents/skills/mvp-skeleton.md": (
                    "# MVP\nThis is a first-pass MVP scope.\n"
                ),
            }
            for rel_path, content in cases.items():
                with self.subTest(rel_path=rel_path):
                    self.copy_minimal_repo(root)
                    (root / rel_path).write_text(content, encoding="utf-8")

                    result = self.run_checker(root)

                    self.assertEqual(
                        result.returncode,
                        1,
                        result.stdout + result.stderr,
                    )
                    self.assertIn("positive_runtime_wording", result.stdout)
                    self.assertIn("legacy-sequence-design-wording", result.stdout)

    def test_minimal_fixture_covers_positive_runtime_wording_surfaces(self) -> None:
        """The minimal test fixture includes every positive wording surface."""
        missing = sorted(
            path
            for path in POSITIVE_RUNTIME_WORDING_SURFACES
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_legacy_forwarder_requires_caller_action_warning(self) -> None:
        """Legacy forwarders must identify callers and migration action."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            forwarder = root / "tools" / "agent_tools" / "legacy_forwarder.py"
            forwarder.write_text(
                "LEGACY_FORWARDER_WARNING_REQUIRED = True\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("legacy_forwarder_warning", result.stdout)
            self.assertIn("missing-marker:FORWARDER_CALLER", result.stdout)
            self.assertIn("missing-marker:FORWARDER_ACTION", result.stdout)

    def test_skill_routing_requires_codex_task_workflow_marker(self) -> None:
        """Skill routing prompts must keep execution-stage skill markers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill = root / ".agents" / "skills" / "agent-orchestration" / "SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8").replace(
                    " $codex-task-workflow",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("skill_routing", result.stdout)
            self.assertIn("missing-marker:$codex-task-workflow", result.stdout)

    def test_skill_routing_requires_subagent_bootstrap_marker(self) -> None:
        """Skill routing prompts must keep handoff-stage skill markers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill = root / ".agents" / "skills" / "agent-orchestration" / "SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8").replace(
                    " $subagent-bootstrap",
                    "",
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("skill_routing", result.stdout)
            self.assertIn("missing-marker:$subagent-bootstrap", result.stdout)

    def test_document_structure_routing_requires_structure_planning(self) -> None:
        """Document edit routing must keep structure analysis markers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = root / ".agents" / "skills" / "codex-task-workflow" / "SKILL.md"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "$structure-planning",
                    "structure-route-missing",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("document_structure_routing", result.stdout)
            self.assertIn("missing-marker:$structure-planning", result.stdout)

    def test_document_structure_routing_requires_format_skip_evidence(self) -> None:
        """Format-only Markdown routes must keep the skip evidence marker."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill_doc = root / "agents" / "skills" / "md-style-check.md"
            skill_doc.write_text(
                skill_doc.read_text(encoding="utf-8").replace(
                    "structure_contract=skipped",
                    "structure-contract-record",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("document_structure_routing", result.stdout)
            self.assertIn("missing-marker:structure_contract=skipped", result.stdout)

    def test_minimal_fixture_covers_document_structure_routing_surfaces(self) -> None:
        """The minimal test fixture includes every docs structure routing surface."""
        missing = sorted(
            path
            for path in DOCUMENT_STRUCTURE_ROUTING_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_document_claim_grounding_requires_markers(self) -> None:
        """Canonical docs must keep prose-claim grounding markers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            docs_policy = (
                root / "documents" / "conventions" / "common" / "05_docs.md"
            )
            docs_policy.write_text("docs check_convention_compliance.py\n", encoding="utf-8")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("document_claim_grounding", result.stdout)
            self.assertIn("missing-marker:claim grounding", result.stdout)
            self.assertIn("missing-marker:program contract", result.stdout)
            self.assertIn("missing-marker:proof obligation", result.stdout)

    def test_document_claim_grounding_rejects_provisional_canon(self) -> None:
        """Provisional wording in canonical docs needs an evidence route."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill_doc = root / "agents" / "skills" / "long-form-writing.md"
            skill_doc.write_text(
                skill_doc.read_text(encoding="utf-8")
                + "\n- まずは近い文書へ claim を入れる。\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("document_claim_grounding", result.stdout)
            self.assertIn("provisional-wording-without-grounding", result.stdout)

    def test_minimal_fixture_covers_document_claim_grounding_surfaces(self) -> None:
        """The minimal test fixture includes every claim grounding surface."""
        missing = sorted(
            path
            for path in DOCUMENT_CLAIM_GROUNDING_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_test_contract_routing_requires_contract_only_wrapper_markers(self) -> None:
        """Testing policy must route contract-only wrappers to static validation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            testing_policy = root / "documents" / "coding-conventions-testing.md"
            testing_policy.write_text("testing canonical command\n", encoding="utf-8")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("test_contract_routing", result.stdout)
            self.assertIn("missing-marker:contract-only wrapper", result.stdout)
            self.assertIn("missing-marker:static contract validation", result.stdout)

    def test_minimal_fixture_covers_test_contract_routing_surfaces(self) -> None:
        """The minimal test fixture includes every test contract routing surface."""
        missing = sorted(
            path
            for path in TEST_CONTRACT_ROUTING_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_owner_map_entrypoint_requires_root_owner_rows(self) -> None:
        """Root runtime entrypoints keep structure-backed owner anchors."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            root_agents = root / "ROOT_AGENTS.md"
            root_agents.write_text(
                root_agents.read_text(encoding="utf-8").replace(
                    "vendor/agent-canon/agents/task_catalog.yaml",
                    "vendor/agent-canon/agents/task_catalog-missing.yaml",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("owner_map_entrypoints", result.stdout)
            self.assertIn(
                "missing-owner-row:workflow family, spawn budget, role topology",
                result.stdout,
            )

    def test_owner_map_entrypoint_requires_agent_owner_rows(self) -> None:
        """Standalone AgentCanon entrypoint keeps public skill owner row."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            agents = root / "AGENTS.md"
            agents.write_text(
                agents.read_text(encoding="utf-8").replace(
                    "| public skill registry | `agents/skills/catalog.yaml` | "
                    "`check_agent_runtime_alignment.py` |\n",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("owner_map_entrypoints", result.stdout)
            self.assertIn("missing-owner-row:public skill registry", result.stdout)

    def test_owner_map_entrypoint_accepts_template_agents_root_view(self) -> None:
        """Template AGENTS.md views use ROOT_AGENTS owner-map rows."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            agents = root / "AGENTS.md"
            agents.unlink()
            agents.symlink_to("ROOT_AGENTS.md")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_owner_map_entrypoint_reports_root_view_row_once(self) -> None:
        """Template AGENTS.md root views do not duplicate owner-map findings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            root_agents = root / "ROOT_AGENTS.md"
            root_agents.write_text(
                root_agents.read_text(encoding="utf-8").replace(
                    "vendor/agent-canon/agents/task_catalog.yaml",
                    "vendor/agent-canon/agents/task_catalog-missing.yaml",
                ),
                encoding="utf-8",
            )
            agents = root / "AGENTS.md"
            agents.unlink()
            agents.symlink_to("ROOT_AGENTS.md")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            finding = (
                "missing-owner-row:workflow family, spawn budget, role topology"
            )
            self.assertEqual(result.stdout.count(finding), 1, result.stdout)
            self.assertIn(
                "owner_map_entrypoints:ROOT_AGENTS.md:" + finding,
                result.stdout,
            )

    def test_entrypoint_delegation_rejects_old_operational_sections(self) -> None:
        """Root runtime entrypoints delegate detailed procedures to owner surfaces."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            root_agents = root / "ROOT_AGENTS.md"
            root_agents.write_text(
                root_agents.read_text(encoding="utf-8")
                + "\n## Subagent Usage\n\n- duplicate operational procedure\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("entrypoint_delegation", result.stdout)
            self.assertIn("delegated-section:## Subagent Usage", result.stdout)

    def test_owner_map_entrypoint_requires_workflow_task_catalog_row(self) -> None:
        """Workflow owner row is required even when later reader rows repeat it."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflows = root / "agents" / "TASK_WORKFLOWS.md"
            workflows.write_text(
                workflows.read_text(encoding="utf-8").replace(
                    "| workflow family and spawn budget | "
                    "`agents/task_catalog.yaml` |\n",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("owner_map_entrypoints", result.stdout)
            self.assertIn(
                "missing-owner-row:workflow family and spawn budget",
                result.stdout,
            )

    def test_owner_map_entrypoint_requires_workflow_owner_rows(self) -> None:
        """Workflow reader map keeps the concrete implementation owners."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflows = root / "agents" / "TASK_WORKFLOWS.md"
            workflows.write_text(
                workflows.read_text(encoding="utf-8").replace(
                    "agent-canon local-llm route-skill",
                    "skill router owner omitted",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("owner_map_entrypoints", result.stdout)
            self.assertIn(
                "missing-owner-row:skill selection",
                result.stdout,
            )

    def test_minimal_fixture_covers_owner_map_entrypoint_surfaces(self) -> None:
        """The minimal test fixture includes every owner-map entrypoint."""
        missing = sorted(
            path
            for path in OWNER_MAP_ENTRYPOINT_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def copy_minimal_repo(self, root: Path) -> None:
        """Create the minimum tree needed by the checker."""
        for path, text in MINIMAL_REPO_FILES.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        for tool in MINIMAL_AGENT_TOOLS:
            target = root / "tools" / "agent_tools" / tool
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        for tool_path in MINIMAL_PYTHON_TOOLS:
            target = root / tool_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        github_checker = root / "tools" / "ci" / "check_github_workflows.py"
        github_checker.parent.mkdir(parents=True, exist_ok=True)
        github_checker.write_text(
            "#!/usr/bin/env python3\ncheck_skill_frontmatter.py\n",
            encoding="utf-8",
        )
        container_checker = root / "tools" / "ci" / "container_config.py"
        container_checker.write_text("#!/usr/bin/env python3\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
