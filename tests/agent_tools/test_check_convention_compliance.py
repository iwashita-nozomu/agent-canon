"""Tests for convention compliance wiring verifier."""

# @dependency-start
# contract test
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
    BRANCH_WORKTREE_CREATION_GUARD_MARKERS,
    DESIGN_INTEGRITY_GATE_MARKERS,
    DOCUMENT_CLAIM_GROUNDING_MARKERS,
    DOCUMENT_SPLIT_DECISION_MARKERS,
    DOCUMENT_STRUCTURE_ROUTING_MARKERS,
    EXPERIMENT_EXECUTION_SURFACE_GUARD_MARKERS,
    FALLBACK_EXIT_POLICY_MARKERS,
    IMPLEMENTATION_GUARDRAIL_MARKERS,
    LITERATURE_BACKED_SKILL_CALL_ORDER_MARKERS,
    MATHEMATICAL_NECESSITY_MARKERS,
    OWNER_BOUNDED_TOOL_ROUTE_MARKERS,
    OWNER_MAP_ENTRYPOINT_MARKERS,
    POSITIVE_RUNTIME_WORDING_SURFACES,
    PR_ESSENCE_DOCUMENTATION_MARKERS,
    REFACTOR_SEQUENCE_MARKERS,
    RESPONSIBILITY_PREFLIGHT_GATE_MARKERS,
    REVIEW_ISSUE_ROUTING_MARKERS,
    SOLID_CODING_CONTRACT_MARKERS,
    SOURCE_FILE_DEFINITION_ORDER_MARKERS,
    STATIC_READ_VALIDATION_POLICY_MARKERS,
    TEST_CONTRACT_ROUTING_MARKERS,
    VALIDATION_FAILURE_RESPONSE_MARKERS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "check_convention_compliance.py"


def skill_fixture(skill: str, body: str) -> str:
    """Return a minimal runtime skill fixture with its tool command packet."""
    return (
        f"# {skill}\n\n"
        "## Tool Commands\n\n"
        "```bash\n"
        "python3 tools/agent_tools/skill_tool_commands.py show "
        f"--skill {skill} --format text\n"
        "```\n\n"
        f"{body}"
    )


MINIMAL_REPO_FILES: dict[str, str] = {
    "documents/conventions/README.md": "conventions\n",
    "documents/conventions/common/01_principles.md": "check_hardcoded_numbers.py\n",
    "documents/conventions/common/02_naming.md": "check_log_helper_names.py\n",
    "documents/conventions/common/03_comments.md": "comments\n",
    "documents/conventions/common/04_operators.md": "operators\n",
    "documents/conventions/common/05_docs.md": (
        "docs claim grounding program contract public entrypoint "
        "return projection proof obligation provisional wording "
        "check_convention_compliance.py mathematical necessity gate "
        "Judgment / Mathematical Role / Necessity Evidence / Owner / Validation Route "
        "necessary-and-sufficient condition non-contractual mathematical judgment "
        "Document Split Decision document_split_decision document_unit split_when "
        "merge_when invalid_split_boundaries task_close.py\n"
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
    "documents/coding-conventions-python.md": (
        "python import_responsibility.py\n"
        "SOLID 設計契約 Single responsibility Open/closed Liskov substitution "
        "Interface segregation Dependency inversion "
        "tools/oop/python/readability.py tools/oop/shared/readability_core.py "
        "tools/agent_tools/check_solid_evidence.py SOLID principle signal scanned_paths "
        "SOLID_PRINCIPLES_BY_KIND readability.py\n"
    ),
    "documents/coding-conventions-cpp.md": "cpp\n",
    "documents/coding-conventions-project.md": (
        "project container_config.py claim grounding program contract proof obligation "
        "run-local planning evidence\n"
    ),
    "documents/coding-conventions-house-style.md": (
        "house compatibility-preservation drift duplicate implementation "
        "canonical owner caller migration contract-complete implementation "
        "acceptance contract design_issue_blocker implementation shortcut "
        "two-stage refactor forced migration usage-surface repair "
        "return-gate validation 読者順序 公開契約 公開入口 内部補助関数 "
        "単一公開入口 "
        "check_convention_compliance.py\n"
    ),
    "documents/coding-conventions-testing.md": (
        "testing contract-only wrapper static contract validation "
        "static-analysis-duplicate-test canonical command Validation repair scope "
        "mathematical necessity gate Numerical Trigger Non-Numerical Alternative "
        "checker-owned property SOLID / OOP boundary assertion "
        "$oop-readability-check tools/oop/python/readability.py "
        "tools/oop/cpp/readability.py import_responsibility.py\n"
    ),
    "documents/coding-conventions-reviews.md": "reviews\n",
    "documents/coding-conventions-experiments.md": "experiments\n",
    "documents/coding-conventions-logging.md": "check_log_helper_names.py\n",
    "documents/algorithm-implementation-boundary.md": "algorithm\n",
    "documents/object-oriented-design.md": (
        "readability.py SOLID との対応 Single responsibility Open/closed "
        "Liskov substitution Interface segregation Dependency inversion "
        "tools/oop/shared/readability_core.py SOLID_PRINCIPLES_BY_KIND "
        "import_responsibility.py\n"
    ),
    "documents/experiment-registry.md": (
        "experiment_execution_surface_guard tool_rejection_preflight.py "
        "check_experiment_registry.py tests/tools/test_run_managed_experiment.py\n"
    ),
    "documents/REVIEW_PROCESS.md": (
        "review structure-planning prose-reasoning-graph md-style-check "
        "structure_contract=skipped Review Finding Issue Routing issue_route "
        "issues/open/ issue_sync.py github_mirror\n"
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
    "documents/runtime-profiles-and-check-matrix.md": (
        "Static analysis and reading evidence primary validation evidence "
        "operation checks supplemental evidence unresolved static/read findings\n"
    ),
    "documents/codex-configuration-reference.md": (
        "## Hook Severity Policy\n"
        "fail-open CRITICAL_BLOCKING_CHILD_HOOKS warning/evidence\n"
        "*_FORWARDER=deprecated *_FORWARDER_SEVERITY=fix-now "
        "caller chain canonical command\n"
    ),
    "documents/responsibility-scope-management.md": "import_responsibility.py responsibility_scope.py\n",
    "documents/tools/README.md": (
        "tool_catalog.py tool_drift.py notebook_quality.py import_responsibility.py "
        "tool_rejection_preflight.py responsibility_scope responsibility-scope.toml "
        "protecting tools\n"
    ),
    "notes/guardrails/engineering_avoidances.md": (
        "compatibility-preservation drift duplicate implementation canonical owner "
        "contract-complete implementation acceptance contract design_issue_blocker "
        "implementation shortcut\n"
    ),
    "tools/README.md": (
        "tool_catalog.py tool_drift.py notebook_quality.py import_responsibility.py "
        "check_runtime_profile_inventory.py tool_rejection_preflight.py "
        "responsibility_scope responsibility-scope.toml protecting tools\n"
    ),
    "tools/agent_tools/tool_rejection_preflight.py": (
        "RESPONSIBILITY_SCOPE_COMMAND responsibility_scope_gate scope_covers "
        "protecting_tools gate=\"responsibility_scope\" "
        "EXPERIMENT_EXECUTION_SURFACE_PATHS experiment_execution_surface_guard "
        "experiment_execution_surface_path check_experiment_registry.py "
        "test_run_managed_experiment.py\n"
    ),
    "agents/COMMUNICATION_PROTOCOL.md": (
        "responsibility_scope responsibility-scope.toml owner class protecting tools "
        "planned path\n"
    ),
    "agents/canonical/CODEX_WORKFLOW.md": (
        "Completion Readiness\n"
        "Design Integrity Gate owning responsibility model "
        "Abstract Design Frame Design-To-Implementation Trace "
        "design_issue_blocker implementation shortcut\n"
        "user-facing completion\n"
        "repo_wide_static_analysis_complete\n"
        "repo_wide_dependency_tools_complete\n"
        "run_repo_dependency_review.sh\n"
        "bounded route existing tool targeted validation follow-up context\n"
        "contract-only wrapper static contract validation canonical command evidence "
        "validation tool\n"
        "静的解析・読み取り 主証跡 reading evidence 動作確認 broad execution\n"
        "compatibility-preservation drift duplicate implementation canonical owner "
        "caller migration contract-complete implementation acceptance contract "
        "design_issue_blocker implementation shortcut\n"
        "Branch Reuse Default branch_worktree_guard.py user が別 branch を明示 "
        "AgentCanon branch / PR workflow "
        "branch_creation_reason=<reason> worktree_creation_reason=<reason> "
        "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=user_request "
        "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=agent_canon_workflow "
        "AGENT_CANON_BRANCH_WORKTREE_REASON=<reason>\n"
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
    "agents/workflows/pr-queue-cleanup-workflow.md": (
        "PR Essence problem / user request design intent canonical owner "
        "behavior or contract delta evidence route\n"
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
    ),
    ".agents/skills/agent-orchestration/SKILL.md": skill_fixture(
        "agent-orchestration",
        "$agent-orchestration $codex-task-workflow $subagent-bootstrap "
        "$owner-bounded-routing $literature-survey $research-workflow "
        "task-shape skill check_convention_compliance.py vertical dynamic wave "
        "write-capable handoff $prose-reasoning-graph $structure-planning "
        "$md-style-check format-only structure_contract=skipped "
        "existing-tool route targeted-validation evidence Owner-Bounded Change "
        "static/read evidence unresolved signal operation checks smoke runs "
        "Expensive command "
        "Design Integrity Gate responsibility model Abstract Design Frame "
        "design_issue_blocker implementation shortcut "
        "before `$research-workflow` source packet adoption/exclusion "
        "parent-direct SKILL.md "
        "fallback_exit_status canonical_rerun_pass durable_blocker_or_issue "
        "explicit_approval_evidence router_unavailable_blocker\n"
    ),
    ".agents/skills/codex-task-workflow/SKILL.md": skill_fixture(
        "codex-task-workflow",
        "codex task workflow prose-reasoning-graph $structure-planning "
        "$literature-survey $research-workflow before design "
        "$md-style-check format-only structure_contract=skipped "
        "existing-tool route targeted-validation evidence Owner-Bounded Change "
        "static/read evidence primary validation evidence supplemental evidence "
        "operation checks unresolved static findings "
        "Design Integrity Gate responsibility model Abstract Design Frame "
        "design_issue_blocker implementation latitude "
        "parent-direct $owner-bounded-routing SKILL.md "
        "Implementation Source Packet adoption/exclusion "
        "tool_rejection_preflight.py "
        "contract-complete implementation acceptance contract design_issue_blocker "
        "implementation shortcut "
        "fallback_exit_status canonical_rerun_pass durable_blocker_or_issue "
        "explicit_approval_evidence router_unavailable_blocker "
        "$oop-readability-check SOLID principle signal OOP dimension "
        "finding kind tools/oop/shared/readability_core.py check_solid_evidence.py "
        "scanned_paths classes Protocol responsibility_scope owner scope "
        "protecting tools implementation directory\n"
    ),
    ".agents/skills/refactor-loop/SKILL.md": skill_fixture(
        "refactor-loop",
        "two-stage refactor forced migration usage-surface repair "
        "return-gate validation\n",
    ),
    ".agents/skills/change-review/SKILL.md": skill_fixture(
        "change-review",
        "issue_route issues/README.md issue_sync.py new_local_issue github_mirror "
        "python-review $oop-readability-check tools/agent_tools/check_solid_evidence.py "
        "SOLID principle signal OOP readability report classes Protocol\n",
    ),
    ".agents/skills/subagent-bootstrap/SKILL.md": skill_fixture(
        "subagent-bootstrap",
        "fallback_exit_status canonical_rerun_pass durable_blocker_or_issue "
        "explicit_approval_evidence router_unavailable_blocker\n"
    ),
    ".agents/skills/tool-finding-report/SKILL.md": skill_fixture(
        "tool-finding-report",
        "tool_warning_exit_status resolved deferred_with_issue "
        "accepted_with_reason explicit_approval_evidence\n"
    ),
    ".agents/skills/md-style-check/SKILL.md": skill_fixture(
        "md-style-check",
        "$prose-reasoning-graph $structure-planning $owner-bounded-routing format-only "
        "structure_contract=skipped existing-tool route "
        "targeted-validation evidence\n"
    ),
    ".agents/skills/structure-planning/SKILL.md": skill_fixture(
        "structure-planning",
        "document_unit document_split_decision invalid split boundaries\n",
    ),
    ".agents/skills/owner-bounded-routing/SKILL.md": skill_fixture(
        "owner-bounded-routing",
        "existing tool owner boundary targeted validation Owner-Bounded Change "
        "targeted validation tool_rejection_preflight.py "
        "structure_contract=skipped responsibility_scope owner scope protecting tools "
        "implementation directory SKILL.md\n"
    ),
    ".agents/skills/test-design/SKILL.md": skill_fixture(
        "test-design",
        "contract-only wrapper static contract validation canonical command evidence "
        "observable behavior validation repair scope mathematical necessity gate "
        "Numerical Trigger Non-Numerical Alternative checker-owned property "
        "failing contract observation level failure cause approved intent escalate "
        "oracle weakening\n"
    ),
    ".agents/skills/experiment-lifecycle/SKILL.md": skill_fixture(
        "experiment-lifecycle",
        "experiment_execution_surface_guard tool_rejection_preflight.py "
        "$test-design check_experiment_registry.py "
        "tests/tools/test_run_managed_experiment.py\n",
    ),
    ".agents/skills/worktree-health/SKILL.md": skill_fixture(
        "worktree-health",
        "agents/canonical/CODEX_WORKFLOW.md Branch Reuse Default "
        "branch_worktree_guard.py "
        "branch_creation_reason=<reason> "
        "worktree_creation_reason=<reason> git worktree list --porcelain "
        "git branch --show-current\n",
    ),
    ".agents/skills/computational-optimization/SKILL.md": skill_fixture(
        "computational-optimization",
        "mathematical necessity gate iteration map stopping scalar failure semantics\n",
    ),
    ".agents/skills/mvp-skeleton/SKILL.md": skill_fixture(
        "mvp-skeleton",
        "mvp core loop vertical slice\n",
    ),
    ".agents/skills/pr-processing/SKILL.md": skill_fixture(
        "pr-processing",
        "PR Essence problem / user request design intent canonical owner "
        "behavior or contract delta evidence route\n",
    ),
    ".agents/skills/python-review/SKILL.md": skill_fixture(
        "python-review",
        "SOLID 原則シグナル $oop-readability-check "
        "tools/oop/python/readability.py tools/agent_tools/check_solid_evidence.py "
        "Single responsibility Open/closed "
        "Liskov substitution Interface segregation Dependency inversion "
        "scanned_paths 定義順 読者順序 "
        "公開入口 内部補助関数 check_convention_compliance.py\n",
    ),
    ".agents/skills/oop-readability-check/SKILL.md": skill_fixture(
        "oop-readability-check",
        "SOLID SOLID route owner Single responsibility Open/closed Liskov substitution "
        "Interface segregation Dependency inversion tools/oop/shared/readability_core.py "
        "mechanical projections readability.py\n",
    ),
    "agents/skills/agent-orchestration.md": (
        "$agent-orchestration $codex-task-workflow $subagent-bootstrap "
        "literature-survey research-workflow 先に source packet adoption/exclusion "
        "静的解析・読み取り evidence 未解決 signal 動作確認 smoke run "
        "重いコマンド "
        "Design Integrity Gate responsibility model Abstract Design Frame "
        "design_issue_blocker implementation shortcut "
        "$owner-bounded-routing "
        "task-shape skill check_convention_compliance.py vertical dynamic wave "
        "write-capable handoff prose-reasoning-graph structure-planning "
        "md-style-check format-only structure_contract=skipped "
        "existing-tool route targeted validation Owner-Bounded Change "
        "parent-direct SKILL.md "
        "fallback_exit_status canonical_rerun_pass durable_blocker_or_issue "
        "explicit_approval_evidence router_unavailable_blocker\n"
    ),
    "agents/skills/codex-task-workflow.md": (
        "codex task workflow prose-reasoning-graph structure-planning "
        "literature-survey research-workflow 設計 Implementation Source Packet "
        "adoption/exclusion "
        "静的解析・読み取り evidence primary validation evidence "
        "supplemental evidence 動作確認 未解決 finding "
        "Design Integrity Gate 責務 model Abstract Design Frame "
        "design_issue_blocker implementation shortcut "
        "md-style-check format-only structure_contract=skipped "
        "existing-tool route targeted validation Owner-Bounded Change "
        "parent-direct $owner-bounded-routing SKILL.md "
        "tool_rejection_preflight.py "
        "contract-complete implementation acceptance contract design_issue_blocker "
        "implementation shortcut "
        "fallback_exit_status canonical_rerun_pass durable_blocker_or_issue "
        "explicit_approval_evidence router_unavailable_blocker "
        "$oop-readability-check SOLID principle signal OOP dimension finding kind "
        "tools/oop/shared/readability_core.py check_solid_evidence.py scanned_paths "
        "class Protocol responsibility_scope owner scope protecting tools "
        "実装ディレクトリ\n"
    ),
    "agents/skills/refactor-loop.md": (
        "two-stage refactor forced migration usage-surface repair "
        "return-gate validation\n"
    ),
    "agents/skills/change-review.md": (
        "issue_route issues/open/ issue_sync.py new_local_issue github_mirror "
        "python-review $oop-readability-check tools/agent_tools/check_solid_evidence.py "
        "SOLID principle signal OOP readability report class Protocol\n"
    ),
    "agents/skills/pr-processing.md": (
        "PR Essence problem / user request design intent canonical owner "
        "behavior or contract delta evidence route\n"
    ),
    "agents/skills/subagent-bootstrap.md": (
        "fallback_exit_status canonical_rerun_pass durable_blocker_or_issue "
        "explicit_approval_evidence router_unavailable_blocker\n"
    ),
    "agents/skills/tool-finding-report.md": (
        "tool_warning_exit_status resolved deferred_with_issue "
        "accepted_with_reason explicit_approval_evidence\n"
    ),
    "agents/skills/md-style-check.md": (
        "prose-reasoning-graph structure-planning $owner-bounded-routing format-only "
        "structure_contract=skipped existing-tool route targeted validation\n"
    ),
    "agents/skills/structure-planning.md": (
        "document_unit document_split_decision split_when merge_when "
        "invalid_split_boundaries\n"
    ),
    "agents/skills/owner-bounded-routing.md": (
        "existing tool owner boundary targeted validation Owner-Bounded Change "
        "targeted validation tool_rejection_preflight.py "
        "structure_contract=skipped responsibility_scope owner scope protecting tools "
        "実装ディレクトリ SKILL.md\n"
    ),
    "agents/skills/test-design.md": (
        "contract-only wrapper static contract validation canonical command evidence "
        "observable behavior validation repair scope mathematical necessity gate "
        "Numerical Trigger Non-Numerical Alternative checker-owned property "
        "failing contract observation level cause classification approved intent "
        "escalation oracle weakening\n"
    ),
    "agents/skills/experiment-lifecycle.md": (
        "experiment_execution_surface_guard tool_rejection_preflight.py "
        "test-design check_experiment_registry.py "
        "tests/tools/test_run_managed_experiment.py\n"
    ),
    "agents/skills/worktree-health.md": (
        "agents/canonical/CODEX_WORKFLOW.md Branch Reuse Default "
        "branch_worktree_guard.py "
        "branch_creation_reason=<reason> "
        "worktree_creation_reason=<reason> git worktree list --porcelain "
        "git branch --show-current\n"
    ),
    "agents/skills/computational-optimization.md": (
        "mathematical necessity gate iteration map stopping scalar failure semantics\n"
    ),
    "agents/skills/long-form-writing.md": (
        "数学的 claim program contract proof obligation $formal-proof-workflow "
        "provisional wording existing-tool route targeted validation "
        "typo format-only SKILL.md document_split_decision owner reader path "
        "source map validation route chunking convenience\n"
    ),
    "agents/skills/python-review.md": (
        "SOLID 原則シグナル OOP 可読性レポート "
        "tools/oop/python/readability.py tools/agent_tools/check_solid_evidence.py "
        "Single responsibility Open/closed "
        "Liskov substitution Interface segregation Dependency inversion "
        "readability.py scanned_paths 定義順 読者順序 "
        "公開入口 内部補助関数 check_convention_compliance.py\n"
    ),
    "agents/skills/oop-readability-check.md": (
        "SOLID Single responsibility Open/closed Liskov substitution "
        "Interface segregation Dependency inversion "
        "tools/oop/shared/readability_core.py SOLID route owner mechanical projections "
        "readability.py\n"
    ),
    "agents/workflows/implementation-waterfall-workflow.md": (
        "Design Integrity Gate owning responsibility model Abstract Design Frame "
        "design_issue_blocker implementation shortcut\n"
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
    ),
    ".agents/skills/long-form-writing/SKILL.md": skill_fixture(
        "long-form-writing",
        "mathematical claim program contract proof obligation $formal-proof-workflow "
        "provisional wording existing-tool route targeted-validation evidence "
        "typo/link/format-only SKILL.md document_split_decision owner reader path "
        "source map validation route chunking convenience\n"
    ),
    "agents/skills/formal-proof-workflow.md": (
        "program contract public entrypoint return projection proof obligation "
        "mathematical necessity gate theorem surface\n"
    ),
    ".agents/skills/formal-proof-workflow/SKILL.md": skill_fixture(
        "formal-proof-workflow",
        "program contract public entrypoint return projection validation command "
        "mathematical necessity gate theorem surface proof obligation\n"
    ),
    "agents/skills/README.md": (
        "owner-bounded-routing existing tool targeted validation .codex/config.toml "
        "prose-reasoning-graph structure-planning md-style-check "
        "structure_contract=skipped\n"
    ),
    "agents/skills/catalog.yaml": (
        "skill catalog routing entry skill format-only docs work "
        "literature-survey research-workflow related_skills "
        "prose-reasoning-graph structure-planning SOLID SRP OCP LSP ISP DIP "
        "Single responsibility Open/closed Liskov Interface segregation "
        "Dependency inversion Protocol コードファイル 順序 定義順 関数 class\n"
        "owner-bounded-routing owner-bounded targeted validation Owner-Bounded Change\n"
        "- [\"SOLID\"]\n"
        "- [\"SRP\"]\n"
        "- [\"Dependency inversion\"]\n"
    ),
    "agents/task_catalog.yaml": (
        "literature-survey research-workflow source packet adoption/exclusion "
        "Research-Driven Change\n"
    ),
    "tools/agent_tools/agent_team.py": (
        "$literature-survey $research-workflow research_driven_change selected.append\n"
    ),
    ".codex/config.toml": "../.agents/skills/owner-bounded-routing/SKILL.md\n",
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
        "`task_start.py`; `bootstrap_agent_run.py`; `workflow_monitor.py` |\n"
        "| skill selection | `agents/skills/catalog.yaml`; "
        "`python3 tools/agent_tools/route.py --prompt` |\n"
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
        "Document Structure Evidence structure_contract=skipped "
        "existing tool targeted validation 読了 gate なし\n"
    ),
    "agents/templates/closeout_gate.md": (
        "evaluate_agent_run.py run_repo_dependency_review.sh\n"
        "Document Structure Evidence document_structure_status structure_planning "
        "prose_graph md_style_check format_only_reason document_split_decision "
        "keep:<reason> split:<new-owner-boundary> "
        "not_applicable:format-only:<reason>\n"
    ),
    "agents/templates/workflow_monitoring.md": (
        "tool_warning_exit_status resolved deferred_with_issue "
        "accepted_with_reason explicit_approval_evidence\n"
    ),
    "agents/workflows/hypothesis-validation-workflow.md": (
        "scan_code_dependencies.sh\n"
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
    ),
    "agents/workflows/comprehensive-refactoring-workflow.md": (
        "readability.py check_convention_compliance.py\n"
        "compatibility-preservation drift duplicate implementation canonical owner "
        "Removal and Caller Migration Plan two-stage refactor forced migration "
        "usage-surface repair return-gate validation\n"
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
        "PR Essence problem / user request design intent canonical owner "
        "behavior or contract delta evidence route\n"
        "Before closeout, run "
        "`python3 tools/agent_tools/check_convention_compliance.py`.\n"
        + "".join(f"{marker}\n" for marker in AGENT_CANON_PUSH_REMOTE_MARKERS)
    ),
    ".github/PULL_REQUEST_TEMPLATE.md": (
        "## PR Essence\n"
        "Problem / user request\n"
        "Design intent\n"
        "Canonical owner\n"
        "Behavior or contract delta\n"
        "Evidence route\n"
    ),
    ".github/PULL_REQUEST_TEMPLATE/agent_canon.md": (
        "## PR Essence\n"
        "Problem / user request\n"
        "Design intent\n"
        "Canonical owner\n"
        "Behavior or contract delta\n"
        "Evidence route\n"
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
        "downgraded_block_payload failure_warning_payload direct_rg_context_guard.py "
        "branch_worktree_guard.py PreToolUse\n"
    ),
    ".codex/hooks/branch_worktree_guard.py": (
        "BRANCH_WORKTREE_CREATION_GUARD=block "
        "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY user_request agent_canon_workflow "
        "AGENT_CANON_BRANCH_WORKTREE_REASON "
        "git worktree add git switch -c/-C git checkout -b/-B/--orphan "
        "git branch <name>/-c/-C/-f/--force\n"
    ),
    ".codex/hooks/direct_rg_context_guard.py": (
        "DIRECT_RG_CONTEXT_RISK=warn rg -l --max-count .agent-canon/log-archive "
        "reports *.jsonl\n"
    ),
    "tools/agent_tools/task_close.py": (
        "changed_markdown_paths Document Structure Evidence "
        "document_structure_evidence DOCUMENT_STRUCTURE_REQUIRED "
        "document_split_decision DOCUMENT_SPLIT_DECISION_EVIDENCE "
        "document_split_decision_ready\n"
    ),
    "ROOT_AGENTS.md": (
        "Design Integrity Gate responsibility model Abstract Design Frame "
        "Design-To-Implementation Trace design_issue_blocker "
        "implementation shortcut\n"
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
        "`python3 tools/agent_tools/route.py --prompt` |\n"
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

    def test_runtime_skill_requires_tool_command_packet(self) -> None:
        """Runtime skills expose the command packet entrypoint."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill = root / ".agents" / "skills" / "mvp-skeleton" / "SKILL.md"
            skill.write_text("# mvp-skeleton\n\nmvp core loop\n", encoding="utf-8")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("skill_tool_commands", result.stdout)
            self.assertIn("missing-tool-commands-section", result.stdout)

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

    def test_fallback_exit_policy_rejects_parent_direct_alternate_route(self) -> None:
        """Fallback route wording must point at explicit exit evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill = root / ".agents" / "skills" / "codex-task-workflow" / "SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8")
                + "\nrecord blocker before falling back to a parent-direct alternate route\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("skill_fallback_exit_policy", result.stdout)
            self.assertIn("forbidden-fallback-completion-wording", result.stdout)

    def test_fallback_exit_policy_requires_exit_markers(self) -> None:
        """Fallback route surfaces keep canonical exit status markers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill = root / "agents" / "skills" / "agent-orchestration.md"
            skill.write_text(
                skill.read_text(encoding="utf-8").replace(
                    " explicit_approval_evidence",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("skill_fallback_exit_policy", result.stdout)
            self.assertIn("missing-marker:explicit_approval_evidence", result.stdout)

    def test_warning_acceptance_requires_explicit_approval_evidence(self) -> None:
        """Accepted warning closeout requires approval evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill = root / ".agents" / "skills" / "tool-finding-report" / "SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8").replace(
                    " explicit_approval_evidence",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("skill_fallback_exit_policy", result.stdout)
            self.assertIn(
                "accepted-without-explicit-approval-evidence",
                result.stdout,
            )

    def test_minimal_fixture_covers_fallback_exit_policy_surfaces(self) -> None:
        """The minimal test fixture includes every fallback exit policy surface."""
        missing = sorted(
            path
            for path in FALLBACK_EXIT_POLICY_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

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

    def test_document_split_decision_requires_policy_markers(self) -> None:
        """Document split decisions must stay wired into source policy."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            policy_doc = root / "documents" / "conventions" / "common" / "05_docs.md"
            policy_doc.write_text(
                policy_doc.read_text(encoding="utf-8").replace(
                    "document_split_decision",
                    "document split decision missing",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("document_split_decision", result.stdout)
            self.assertIn("missing-marker:document_split_decision", result.stdout)

    def test_minimal_fixture_covers_document_split_decision_surfaces(self) -> None:
        """The fixture includes every document split decision surface."""
        missing = sorted(
            path
            for path in DOCUMENT_SPLIT_DECISION_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_owner_bounded_tool_route_requires_tool_route_markers(self) -> None:
        """Small edit routes must keep owner-bounded tool route markers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill_doc = root / "agents" / "skills" / "agent-orchestration.md"
            skill_doc.write_text(
                skill_doc.read_text(encoding="utf-8").replace(
                    " existing-tool route",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("owner_bounded_tool_route", result.stdout)
            self.assertIn("missing-marker:existing-tool route", result.stdout)

    def test_minimal_fixture_covers_owner_bounded_tool_route_surfaces(self) -> None:
        """The fixture includes every owner-bounded tool route surface."""
        missing = sorted(
            path
            for path in OWNER_BOUNDED_TOOL_ROUTE_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_owner_bounded_routing_requires_catalog_trigger_marker(self) -> None:
        """Owner-bounded route stays discoverable from the skill catalog."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            catalog = root / "agents" / "skills" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace("owner-bounded", ""),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("owner_bounded_tool_route", result.stdout)
            self.assertIn("missing-marker:owner-bounded", result.stdout)

    def test_owner_bounded_tool_route_contract_is_manifest_backed(self) -> None:
        """Owner-bounded marker surfaces are loaded from the manifest contract."""
        self.assertIn(
            ".agents/skills/owner-bounded-routing/SKILL.md",
            OWNER_BOUNDED_TOOL_ROUTE_MARKERS,
        )
        self.assertIn(
            "agents/skills/owner-bounded-routing.md",
            OWNER_BOUNDED_TOOL_ROUTE_MARKERS,
        )

    def test_design_integrity_gate_requires_markers(self) -> None:
        """Design guidance must keep implementation tied to responsibility model."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = root / "agents" / "canonical" / "CODEX_WORKFLOW.md"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "owning responsibility model",
                    "nearby file route",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("design_integrity_gate", result.stdout)
            self.assertIn(
                "missing-marker:owning responsibility model",
                result.stdout,
            )

    def test_design_integrity_gate_contract_is_manifest_backed(self) -> None:
        """Design-integrity surfaces are loaded from the marker manifest."""
        self.assertIn("ROOT_AGENTS.md", DESIGN_INTEGRITY_GATE_MARKERS)
        self.assertIn(
            "agents/workflows/implementation-waterfall-workflow.md",
            DESIGN_INTEGRITY_GATE_MARKERS,
        )

    def test_minimal_fixture_covers_design_integrity_gate_surfaces(self) -> None:
        """The fixture includes every design-integrity gate surface."""
        missing = sorted(
            path
            for path in DESIGN_INTEGRITY_GATE_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_literature_backed_skill_call_order_contract_is_manifest_backed(self) -> None:
        """Literature-backed skill-call order surfaces are manifest-backed."""
        self.assertIn(
            ".agents/skills/agent-orchestration/SKILL.md",
            LITERATURE_BACKED_SKILL_CALL_ORDER_MARKERS,
        )
        self.assertIn(
            "tools/agent_tools/agent_team.py",
            LITERATURE_BACKED_SKILL_CALL_ORDER_MARKERS,
        )

    def test_minimal_fixture_covers_literature_backed_skill_call_order_surfaces(self) -> None:
        """The fixture includes every literature-backed skill-call order surface."""
        missing = sorted(
            path
            for path in LITERATURE_BACKED_SKILL_CALL_ORDER_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_static_read_validation_policy_requires_markers(self) -> None:
        """Validation policy must keep static/read evidence primary."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            workflow = root / "agents" / "skills" / "codex-task-workflow.md"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "静的解析・読み取り evidence",
                    "runtime confirmation",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("static_read_validation_policy", result.stdout)
            self.assertIn("missing-marker:静的解析・読み取り evidence", result.stdout)

    def test_static_read_validation_policy_contract_is_manifest_backed(self) -> None:
        """Static/read validation policy surfaces are manifest-backed."""
        self.assertIn(
            "documents/runtime-profiles-and-check-matrix.md",
            STATIC_READ_VALIDATION_POLICY_MARKERS,
        )
        self.assertIn(
            ".agents/skills/codex-task-workflow/SKILL.md",
            STATIC_READ_VALIDATION_POLICY_MARKERS,
        )

    def test_minimal_fixture_covers_static_read_validation_policy_surfaces(self) -> None:
        """The fixture includes every static/read validation policy surface."""
        missing = sorted(
            path
            for path in STATIC_READ_VALIDATION_POLICY_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_responsibility_preflight_gate_requires_markers(self) -> None:
        """Pre-edit routing must keep responsibility-scope markers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            protocol = root / "agents" / "COMMUNICATION_PROTOCOL.md"
            protocol.write_text(
                protocol.read_text(encoding="utf-8").replace(
                    "responsibility_scope",
                    "scope route",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("responsibility_preflight_gate", result.stdout)
            self.assertIn("missing-marker:responsibility_scope", result.stdout)

    def test_minimal_fixture_covers_responsibility_preflight_gate_surfaces(self) -> None:
        """The minimal test fixture includes every responsibility preflight surface."""
        missing = sorted(
            path
            for path in RESPONSIBILITY_PREFLIGHT_GATE_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_experiment_execution_surface_guard_requires_markers(self) -> None:
        """Experiment execution surfaces keep lifecycle preflight markers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill = root / ".agents" / "skills" / "experiment-lifecycle" / "SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8").replace(
                    "experiment_execution_surface_guard",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("experiment_execution_surface_guard", result.stdout)
            self.assertIn(
                "missing-marker:experiment_execution_surface_guard",
                result.stdout,
            )

    def test_minimal_fixture_covers_experiment_execution_guard_surfaces(self) -> None:
        """The minimal test fixture includes every experiment execution surface."""
        missing = sorted(
            path
            for path in EXPERIMENT_EXECUTION_SURFACE_GUARD_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_branch_worktree_creation_guard_requires_markers(self) -> None:
        """Branch/worktree creation stays connected to the critical guard."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            dispatcher = root / ".codex" / "hooks" / "hook_dispatcher.py"
            dispatcher.write_text(
                dispatcher.read_text(encoding="utf-8").replace(
                    "branch_worktree_guard.py",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("branch_worktree_creation_guard", result.stdout)
            self.assertIn("missing-marker:branch_worktree_guard.py", result.stdout)

    def test_minimal_fixture_covers_branch_worktree_guard_surfaces(self) -> None:
        """The minimal test fixture includes every branch/worktree guard surface."""
        missing = sorted(
            path
            for path in BRANCH_WORKTREE_CREATION_GUARD_MARKERS
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

    def test_validation_failure_response_requires_runtime_skill_markers(self) -> None:
        """Runtime test-design keeps validation failure response markers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill = root / ".agents" / "skills" / "test-design" / "SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8").replace("failure cause", ""),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("validation_failure_response", result.stdout)
            self.assertIn("missing-marker:failure cause", result.stdout)

    def test_validation_failure_response_requires_human_doc_markers(self) -> None:
        """Human test-design keeps same-intent repair or escalation markers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill_doc = root / "agents" / "skills" / "test-design.md"
            skill_doc.write_text(
                skill_doc.read_text(encoding="utf-8").replace("approved intent", ""),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("validation_failure_response", result.stdout)
            self.assertIn("missing-marker:approved intent", result.stdout)

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

    def test_implementation_guardrails_require_markers(self) -> None:
        """Implementation policy keeps compatibility and duplicate guards visible."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            house_style = root / "documents" / "coding-conventions-house-style.md"
            house_style.write_text(
                "house canonical owner check_convention_compliance.py\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("implementation_guardrails", result.stdout)
            self.assertIn(
                "missing-marker:compatibility-preservation drift",
                result.stdout,
            )
            self.assertIn("missing-marker:duplicate implementation", result.stdout)
            self.assertIn("missing-marker:caller migration", result.stdout)
            self.assertIn(
                "missing-marker:contract-complete implementation",
                result.stdout,
            )
            self.assertIn("missing-marker:acceptance contract", result.stdout)
            self.assertIn("missing-marker:design_issue_blocker", result.stdout)
            self.assertIn("missing-marker:implementation shortcut", result.stdout)

    def test_minimal_fixture_covers_implementation_guardrail_surfaces(self) -> None:
        """The minimal test fixture includes every implementation guardrail surface."""
        missing = sorted(
            path
            for path in IMPLEMENTATION_GUARDRAIL_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_refactor_sequence_requires_two_stage_markers(self) -> None:
        """Refactor workflow keeps the forced-migration usage-repair sequence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            refactor_skill = root / "agents" / "skills" / "refactor-loop.md"
            refactor_skill.write_text("refactor workflow only\n", encoding="utf-8")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("refactor_sequence", result.stdout)
            self.assertIn("missing-marker:two-stage refactor", result.stdout)
            self.assertIn("missing-marker:forced migration", result.stdout)
            self.assertIn("missing-marker:usage-surface repair", result.stdout)
            self.assertIn("missing-marker:return-gate validation", result.stdout)

    def test_minimal_fixture_covers_refactor_sequence_surfaces(self) -> None:
        """The minimal test fixture includes every refactor sequence surface."""
        missing = sorted(
            path for path in REFACTOR_SEQUENCE_MARKERS if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_review_issue_routing_requires_markers(self) -> None:
        """Review findings keep durable issue routing markers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            review_skill = root / "agents" / "skills" / "change-review.md"
            review_skill.write_text("review findings only\n", encoding="utf-8")

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

    def test_pr_essence_documentation_requires_body_contract_markers(self) -> None:
        """PR body routes keep essence markers in their owner surfaces."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            template = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
            template.write_text(
                template.read_text(encoding="utf-8").replace(
                    "Behavior or contract delta\n",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("pr_essence_documentation", result.stdout)
            self.assertIn(
                "missing-marker:Behavior or contract delta",
                result.stdout,
            )

    def test_minimal_fixture_covers_pr_essence_documentation_surfaces(self) -> None:
        """The minimal test fixture includes every PR essence documentation surface."""
        missing = sorted(
            path
            for path in PR_ESSENCE_DOCUMENTATION_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_solid_coding_contract_requires_oop_checker_route_markers(self) -> None:
        """SOLID coding guidance stays wired to OOP readability evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            python_policy = root / "documents" / "coding-conventions-python.md"
            python_policy.write_text(
                python_policy.read_text(encoding="utf-8").replace(
                    "SOLID_PRINCIPLES_BY_KIND",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("solid_coding_contract", result.stdout)
            self.assertIn("missing-marker:SOLID_PRINCIPLES_BY_KIND", result.stdout)

    def test_solid_runtime_skill_requires_route_owner_marker(self) -> None:
        """Runtime OOP skill keeps the SOLID route owner visible."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            skill = root / ".agents" / "skills" / "oop-readability-check" / "SKILL.md"
            skill.write_text(
                skill.read_text(encoding="utf-8").replace(
                    "SOLID route owner",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("solid_coding_contract", result.stdout)
            self.assertIn("missing-marker:SOLID route owner", result.stdout)

    def test_solid_catalog_requires_trigger_marker(self) -> None:
        """Skill catalog keeps the direct SOLID trigger marker."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            catalog = root / "agents" / "skills" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    '- ["SOLID"]\n',
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("solid_coding_contract", result.stdout)
            self.assertIn('missing-marker:- ["SOLID"]', result.stdout)

    def test_solid_contract_requires_default_reviewer_evidence_gate(self) -> None:
        """Default reviewers keep SOLID evidence verification wired."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.copy_minimal_repo(root)
            reviewer = root / ".codex" / "agents" / "reviewer.toml"
            reviewer.write_text(
                reviewer.read_text(encoding="utf-8").replace(
                    "check_solid_evidence.py",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("solid_coding_contract", result.stdout)
            self.assertIn("missing-marker:check_solid_evidence.py", result.stdout)

    def test_minimal_fixture_covers_solid_coding_contract_surfaces(self) -> None:
        """The minimal test fixture includes every SOLID coding contract surface."""
        missing = sorted(
            path
            for path in SOLID_CODING_CONTRACT_MARKERS
            if path not in MINIMAL_REPO_FILES
        )

        self.assertEqual(missing, [])

    def test_source_file_definition_order_requires_review_markers(self) -> None:
        """Source definition order guidance stays wired to Python review evidence."""
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

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("source_file_definition_order", result.stdout)
            self.assertIn("missing-marker:定義順", result.stdout)

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
                    "python3 tools/agent_tools/route.py --prompt",
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
