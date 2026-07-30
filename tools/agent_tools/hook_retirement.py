#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns the typed, immutable AgentCanon hook-retirement tombstone manifest.
# upstream design ../../documents/design/agentcanon-hook-simplification-wave3.md fixes the 23-child/1-moved-source ledger.
# downstream implementation ./check_hook_retirement.py validates absence and caller closure.
# downstream implementation ../../.codex/hooks/hook_dispatcher.py exposes manifest readback.
# downstream implementation ../../tests/agent_tools/test_hook_retirement.py validates digest and typed counts.
# @dependency-end
"""Single source of truth for retired hook metadata."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

TOMBSTONE_SCHEMA = "agent-canon.hook-retirement-tombstones.v2"
CALLER_AUDIT_SCHEMA = "agent-canon.hook-retirement-caller-audit.v1"
CALLER_AUDIT_ROOTS = (
    ".codex", ".agents", "agents", "documents", "evidence", "templates", "tools", "tests",
    "README.md", "AGENTS.md", "ROOT_AGENTS.md", "responsibility-scope.toml",
)


@dataclass(frozen=True)
class RetiredChildTombstone:
    filename: str
    owner: str
    command_or_skill: str
    profile_trigger: str
    decision_semantics: str
    artifact: str


@dataclass(frozen=True)
class MovedSourceAbsence:
    filename: str
    moved_to: str
    import_contract: str
    reason: str
    artifact: str


def _row(filename: str, owner: str, command: str, trigger: str, semantics: str) -> RetiredChildTombstone:
    return RetiredChildTombstone(filename, owner, command, trigger, semantics, "hook-retirement tombstone")


RETIRED_CHILD_TOMBSTONES: tuple[RetiredChildTombstone, ...] = (
    _row("log_archive_mount_warning.py", "tools/agent_tools/runtime_log_archive_git.py", "command-only:python3 tools/agent_tools/runtime_log_archive_git.py ensure", "explicit archive checkpoint", "archive checkpoint is administrative"),
    _row("reference_capture_guard.py", "tools/agent_tools/reference_materializer.py", "command-only:python3 tools/agent_tools/reference_materializer.py", "reference capture", "reference registration belongs to materialization"),
    _row("direct_rg_context_guard.py", "$task-routing", "skill-only:$task-routing", "pre-edit investigation", "context construction owns investigation"),
    _row("task_authority_schema_guard.py", "tools/agent_tools/task_authority.py", "command-only:python3 tools/agent_tools/task_authority.py", "implementation handoff", "authority is validated at the write route"),
    _row("role_write_policy_guard.py", "tools/agent_tools/agent_team.py", "command-only:python3 tools/agent_tools/agent_team.py", "write-capable handoff", "write scope belongs to handoff and closeout"),
    _row("oop_readability_guard.py", "$oop-readability-check", "skill-only:$oop-readability-check", "explicit OOP review", "review evidence is not hook blocking"),
    _row("first_party_library_guard.py", "tools/agent_tools/task_authority.py", "import-only:tools.agent_tools.task_authority:first_party_library_authorized", "first-party surface", "public-surface authority is explicit"),
    _row("helper_inventory_guard.py", "tools/agent_tools/helper_function_inventory.py", "command-only:python3 tools/agent_tools/helper_function_inventory.py", "helper inventory", "inventory findings are review evidence"),
    _row("helper_first_guard.py", "tools/agent_tools/responsibility_scope.py", "command-only:python3 tools/agent_tools/responsibility_scope.py --root .", "owner boundary", "helper placement follows responsibility"),
    _row("log_surface_inventory_guard.py", "tools/agent_tools/log_surface_inventory.py", "command-only:python3 tools/agent_tools/log_surface_inventory.py --root . --check", "log surface change", "telemetry fields belong to inventory owner"),
    _row("notebook_quality_guard.py", "tools/validation/notebook_quality.py", "command-only:python3 tools/validation/notebook_quality.py", "experiment notebook", "notebook quality is experiment evidence"),
    _row("goal_completion_guard.py", "$codex-goals-workflow", "skill-only:$codex-goals-workflow", "goal-driven task", "goal continuation is workflow state"),
    _row("codex_runtime_summary_logger.py", "tools/agent_tools/export_codex_runtime_summary.py", "command-only:python3 tools/agent_tools/export_codex_runtime_summary.py", "runtime summary", "summary is bounded derived evidence"),
    _row("runtime_log_auto_sync.py", "tools/agent_tools/runtime_log_archive_git.py", "command-only:python3 tools/agent_tools/runtime_log_archive_git.py sync", "archive checkpoint", "archive sync is administrative"),
    _row("execution_resource_plan_projection_guard.py", "tools/agent_tools/execution_resource_projection.py", "import-only:tools.agent_tools.execution_resource_projection:validate_projection_bytes", "PostToolUse projection", "projection validation belongs to pure owner"),
    _row("skill_usage_logger.py", "tools/agent_tools/behavior_event_assembly.py", "import-only:tools.agent_tools.behavior_event_assembly:assemble_behavior_event", "behavior evidence", "canonical event assembly owns durable behavior"),
    _row("prompt_secret_guard.py", "tools/agent_tools/hook_safety.py", "import-only:tools.agent_tools.hook_safety:secret_block_payload", "prompt safety", "pure safety owns secret blocking"),
    _row("branch_worktree_guard.py", "tools/agent_tools/hook_safety.py", "import-only:tools.agent_tools.hook_safety:first_block", "Git safety", "pure safety owns protected Git classification"),
    _row("cause_investigation_guard.py", "tools/agent_tools/tool_rejection_preflight.py", "command-only:python3 tools/agent_tools/tool_rejection_preflight.py --gate cause_investigation", "cause investigation", "cause evidence belongs to intake"),
    _row("module_boundary_guard.py", "tools/agent_tools/import_responsibility.py", "command-only:python3 tools/agent_tools/import_responsibility.py", "dependency boundary", "import ownership belongs to checker"),
    _row("library_implementation_guard.py", "tools/agent_tools/task_authority.py", "import-only:tools.agent_tools.task_authority:first_party_library_authorized", "dependency source", "dependency edits use source route"),
    _row("style_checker_guard.py", "$md-style-check", "docs-only:tools/bin/agent-canon docs check", "changed Markdown", "style is targeted validation"),
    _row("completion_review_guard.py", "tools/agent_tools/review_dispatch.py", "import-only:tools.agent_tools.review_dispatch:resolve_current_review_state", "review gate", "review approval belongs to closeout"),
)

MOVED_SOURCE_ABSENCES: tuple[MovedSourceAbsence, ...] = (
    MovedSourceAbsence(
        "hook_safety.py",
        "tools/agent_tools/hook_safety.py",
        "import-only:tools.agent_tools.hook_safety:secret_kind",
        "pure safety implementation moves out of the hook directory; old path is absent",
        "moved-source absence proof",
    ),
)


def retired_filenames() -> tuple[str, ...]:
    return tuple(row.filename for row in RETIRED_CHILD_TOMBSTONES) + tuple(row.filename for row in MOVED_SOURCE_ABSENCES)


def digest_projection() -> dict[str, object]:
    return {
        "schema": TOMBSTONE_SCHEMA,
        "retired_child_tombstones": [asdict(row) for row in sorted(RETIRED_CHILD_TOMBSTONES, key=lambda row: (row.filename, row.owner, row.command_or_skill, row.profile_trigger, row.decision_semantics, row.artifact))],
        "moved_source_absences": [asdict(row) for row in sorted(MOVED_SOURCE_ABSENCES, key=lambda row: (row.filename, row.moved_to, row.import_contract, row.reason, row.artifact))],
    }


def source_digest() -> str:
    raw = json.dumps(digest_projection(), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
