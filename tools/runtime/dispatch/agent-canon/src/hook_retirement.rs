// @dependency-start
// contract implementation
// responsibility Owns the static hook-retirement tombstone manifest and canonical digest.
// upstream implementation ../../../../../tools/runtime/authority/hook_retirement.py owns the current data contract.
// downstream implementation ./hook_dispatcher.rs exposes manifest readback.
// @dependency-end
//! Static hook-retirement data used by hook contract readback.

use crate::python_json::{
    canonical_json_ascii_bytes_reject_nonfinite, JsonArray, JsonObject, JsonString, JsonValue,
};
use sha2::{Digest, Sha256};

pub const TOMBSTONE_SCHEMA: &str = "agent-canon.hook-retirement-tombstones.v2";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RetiredChildTombstone {
    pub filename: &'static str,
    pub owner: &'static str,
    pub command_or_skill: &'static str,
    pub profile_trigger: &'static str,
    pub decision_semantics: &'static str,
    pub artifact: &'static str,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct MovedSourceAbsence {
    pub filename: &'static str,
    pub moved_to: &'static str,
    pub import_contract: &'static str,
    pub reason: &'static str,
    pub artifact: &'static str,
}

const ARTIFACT: &str = "hook-retirement tombstone";

pub const RETIRED_CHILD_TOMBSTONES: &[RetiredChildTombstone] = &[
    row(
        "log_archive_mount_warning.py",
        "tools/runtime/archive/runtime_log_archive_git.py",
        "command-only:python3 tools/runtime/archive/runtime_log_archive_git.py ensure",
        "explicit archive checkpoint",
        "archive checkpoint is administrative",
    ),
    row(
        "reference_capture_guard.py",
        "tools/analysis/documents/reference_materializer.py",
        "command-only:python3 tools/analysis/documents/reference_materializer.py",
        "reference capture",
        "reference registration belongs to materialization",
    ),
    row(
        "direct_rg_context_guard.py",
        "$task-routing",
        "skill-only:$task-routing",
        "pre-edit investigation",
        "context construction owns investigation",
    ),
    row(
        "task_authority_schema_guard.py",
        "tools/runtime/authority/task_authority.py",
        "command-only:python3 tools/runtime/authority/task_authority.py",
        "implementation handoff",
        "authority is validated at the write route",
    ),
    row(
        "role_write_policy_guard.py",
        "tools/agent/orchestration/agent_team.py",
        "command-only:python3 tools/agent/orchestration/agent_team.py",
        "write-capable handoff",
        "write scope belongs to handoff and closeout",
    ),
    row(
        "oop_readability_guard.py",
        "$oop-readability-check",
        "skill-only:$oop-readability-check",
        "explicit OOP review",
        "review evidence is not hook blocking",
    ),
    row(
        "first_party_library_guard.py",
        "tools/runtime/authority/task_authority.py",
        "import-only:tools.runtime.authority.task_authority:first_party_library_authorized",
        "first-party surface",
        "public-surface authority is explicit",
    ),
    row(
        "helper_inventory_guard.py",
        "tools/analysis/code/helper_function_inventory.py",
        "command-only:python3 tools/analysis/code/helper_function_inventory.py",
        "helper inventory",
        "inventory findings are review evidence",
    ),
    row(
        "helper_first_guard.py",
        "tools/runtime/dispatch/agent-canon/src/responsibility_scope.rs",
        "command-only:tools/bin/agent-canon responsibility-scope",
        "owner boundary",
        "helper placement follows responsibility",
    ),
    row(
        "log_surface_inventory_guard.py",
        "tools/runtime/dispatch/agent-canon/src/log_surface_inventory.rs",
        "command-only:tools/bin/agent-canon log-surface-inventory",
        "explicit inventory request",
        "telemetry inventory is an on-demand projection",
    ),
    row(
        "notebook_quality_guard.py",
        "tools/runtime/dispatch/agent-canon/src/notebook_quality.rs",
        "command-only:tools/bin/agent-canon notebook-quality",
        "experiment notebook",
        "notebook quality is experiment evidence",
    ),
    row(
        "goal_completion_guard.py",
        "$adaptive-improvement-loop",
        "skill-only:$adaptive-improvement-loop",
        "iterative task",
        "completion follows selected run-bundle state",
    ),
    row(
        "codex_runtime_summary_logger.py",
        "tools/runtime/archive/export_codex_runtime_summary.py",
        "command-only:python3 tools/runtime/archive/export_codex_runtime_summary.py",
        "runtime summary",
        "summary is bounded derived evidence",
    ),
    row(
        "runtime_log_auto_sync.py",
        "tools/runtime/archive/runtime_log_archive_git.py",
        "command-only:python3 tools/runtime/archive/runtime_log_archive_git.py sync",
        "archive checkpoint",
        "archive sync is administrative",
    ),
    row(
        "execution_resource_plan_projection_guard.py",
        "tools/runtime/container/execution_resource_projection.py",
        "import-only:tools.runtime.container.execution_resource_projection:validate_projection_bytes",
        "PostToolUse projection",
        "projection validation belongs to pure owner",
    ),
    row(
        "skill_usage_logger.py",
        "tools/runtime/archive/behavior_event_assembly.py",
        "import-only:tools.runtime.archive.behavior_event_assembly:assemble_behavior_event",
        "behavior evidence",
        "canonical event assembly owns durable behavior",
    ),
    row(
        "prompt_secret_guard.py",
        "tools/runtime/authority/hook_safety.py",
        "import-only:tools.runtime.authority.hook_safety:secret_block_payload",
        "prompt safety",
        "pure safety owns secret blocking",
    ),
    row(
        "branch_worktree_guard.py",
        "tools/runtime/authority/hook_safety.py",
        "import-only:tools.runtime.authority.hook_safety:first_block",
        "Git safety",
        "pure safety owns protected Git classification",
    ),
    row(
        "cause_investigation_guard.py",
        "tools/runtime/dispatch/agent-canon/src/tool_rejection_preflight.rs",
        "command-only:tools/bin/agent-canon tool-rejection-preflight",
        "cause investigation",
        "cause evidence belongs to intake",
    ),
    row(
        "module_boundary_guard.py",
        "tools/analysis/code/import_responsibility.py",
        "command-only:python3 tools/analysis/code/import_responsibility.py",
        "dependency boundary",
        "import ownership belongs to checker",
    ),
    row(
        "library_implementation_guard.py",
        "tools/runtime/authority/task_authority.py",
        "import-only:tools.runtime.authority.task_authority:first_party_library_authorized",
        "dependency source",
        "dependency edits use source route",
    ),
    row(
        "style_checker_guard.py",
        "$md-style-check",
        "docs-only:tools/bin/agent-canon docs check",
        "changed Markdown",
        "style is targeted validation",
    ),
    row(
        "completion_review_guard.py",
        "tools/agent/orchestration/review_dispatch.py",
        "import-only:tools.agent.orchestration.review_dispatch:resolve_current_review_state",
        "review gate",
        "review approval belongs to closeout",
    ),
];

pub const MOVED_SOURCE_ABSENCES: &[MovedSourceAbsence] = &[MovedSourceAbsence {
    filename: "hook_safety.py",
    moved_to: "tools/runtime/authority/hook_safety.py",
    import_contract: "import-only:tools.runtime.authority.hook_safety:secret_kind",
    reason: "pure safety implementation moves out of the hook directory; old path is absent",
    artifact: "moved-source absence proof",
}];

const fn row(
    filename: &'static str,
    owner: &'static str,
    command_or_skill: &'static str,
    profile_trigger: &'static str,
    decision_semantics: &'static str,
) -> RetiredChildTombstone {
    RetiredChildTombstone {
        filename,
        owner,
        command_or_skill,
        profile_trigger,
        decision_semantics,
        artifact: ARTIFACT,
    }
}

impl RetiredChildTombstone {
    pub fn to_json_value(self) -> JsonValue {
        object(vec![
            ("filename", self.filename),
            ("owner", self.owner),
            ("command_or_skill", self.command_or_skill),
            ("profile_trigger", self.profile_trigger),
            ("decision_semantics", self.decision_semantics),
            ("artifact", self.artifact),
        ])
    }
}

impl MovedSourceAbsence {
    pub fn to_json_value(self) -> JsonValue {
        object(vec![
            ("filename", self.filename),
            ("moved_to", self.moved_to),
            ("import_contract", self.import_contract),
            ("reason", self.reason),
            ("artifact", self.artifact),
        ])
    }
}

pub fn source_digest() -> String {
    let mut children = RETIRED_CHILD_TOMBSTONES.iter().collect::<Vec<_>>();
    children.sort_by(|left, right| {
        (
            left.filename,
            left.owner,
            left.command_or_skill,
            left.profile_trigger,
            left.decision_semantics,
            left.artifact,
        )
            .cmp(&(
                right.filename,
                right.owner,
                right.command_or_skill,
                right.profile_trigger,
                right.decision_semantics,
                right.artifact,
            ))
    });
    let mut moved = MOVED_SOURCE_ABSENCES.iter().collect::<Vec<_>>();
    moved.sort_by(|left, right| {
        (
            left.filename,
            left.moved_to,
            left.import_contract,
            left.reason,
            left.artifact,
        )
            .cmp(&(
                right.filename,
                right.moved_to,
                right.import_contract,
                right.reason,
                right.artifact,
            ))
    });
    let projection = JsonValue::Object(JsonObject(vec![
        (
            key("schema"),
            JsonValue::String(JsonString::from_text(TOMBSTONE_SCHEMA)),
        ),
        (
            key("retired_child_tombstones"),
            JsonValue::Array(JsonArray(
                children.iter().map(|row| row.to_json_value()).collect(),
            )),
        ),
        (
            key("moved_source_absences"),
            JsonValue::Array(JsonArray(
                moved.iter().map(|row| row.to_json_value()).collect(),
            )),
        ),
    ]));
    let bytes = canonical_json_ascii_bytes_reject_nonfinite(&projection)
        .expect("static hook-retirement manifest is valid JSON");
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn object(fields: Vec<(&str, &str)>) -> JsonValue {
    JsonValue::Object(JsonObject(
        fields
            .into_iter()
            .map(|(name, value)| (key(name), JsonValue::String(JsonString::from_text(value))))
            .collect(),
    ))
}

fn key(value: &str) -> JsonString {
    JsonString::from_text(value)
}
