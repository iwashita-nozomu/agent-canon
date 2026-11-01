// @dependency-start
// contract implementation
// responsibility Owns the hook-retirement tombstone manifest, digest, and fail-closed caller-audit CLI.
// upstream design ../../../../../documents/design/agentcanon-hook-simplification-wave3.md fixes the tombstone and caller-audit contract.
// upstream implementation path_resolution.rs resolves the selected source root without creating it
// upstream implementation python_cli_options.rs preserves argparse-compatible option prefixes
// upstream implementation python_json.rs parses hook configuration and serializes contract output
// upstream implementation python_text.rs preserves Python-compatible audit line splitting
// downstream implementation ./hook_dispatcher.rs exposes manifest readback.
// downstream implementation main.rs routes the native hook-retirement check command.
// downstream implementation ../../../../../tests/agent_tools/test_hook_retirement.py validates native readback and checking.
// @dependency-end
//! Hook-retirement manifest, read-only caller audit, and native check command.

use crate::python_json::{
    canonical_json_ascii_bytes, canonical_json_ascii_bytes_reject_nonfinite, parse_json,
    JsonArray, JsonNumber, JsonObject, JsonString, JsonValue,
};
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::python_text::python_splitlines;
use crate::path_resolution::resolve_non_strict;
use regex::Regex;
use sha2::{Digest, Sha256};
use std::collections::{BTreeSet, HashSet};
use std::env;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

pub const TOMBSTONE_SCHEMA: &str = "agent-canon.hook-retirement-tombstones.v2";
pub const CALLER_AUDIT_SCHEMA: &str = "agent-canon.hook-retirement-caller-audit.v1";
pub const SELECTOR: &str = "hook-retirement-check";

const CALLER_AUDIT_ROOTS: &[&str] = &[
    ".codex",
    ".agents",
    "agents",
    "documents",
    "evidence",
    "templates",
    "tools",
    "tests",
    "README.md",
    "AGENTS.md",
    "ROOT_AGENTS.md",
    "responsibility-scope.toml",
];
const EXECUTABLE_SCAN_PATHS: &[&str] = &[
    ".codex/hooks.json",
    ".codex/config.toml",
    ".codex/agents",
    "templates",
    "tools/catalog.yaml",
    "tools/validation/ci/checks/run_python_quality_checks.sh",
    "tools/validation/semantic/runtime/check_agent_runtime_alignment.py",
    "tools/validation/semantic/convention/check_convention_compliance.py",
    "tools/validation/semantic/convention/convention_compliance_contracts.toml",
    "eval/producers/generate_agent_runtime_dashboard.py",
    "tools/agent/skills/skill_lane_detector.py",
    "tools/runtime/artifacts/report_artifact_checks.py",
    "tools/runtime/lifecycle/workflow_monitor.py",
    "agents/skills/worktree-health.md",
    ".codex/personal/skills/worktree-health/SKILL.md",
    "documents/experiments/gpu-admission-r5-source-packet.md",
    "AGENTS.md",
    "ROOT_AGENTS.md",
    "README.md",
    "documents/runtime/runtime-log-archive.md",
    "tools/README.md",
    "tools/experiments/execution/execution_resource_plan.py",
    "tools/runtime/dispatch/agent-canon/src/notebook_quality.rs",
];
const METADATA_ALLOWLIST: &[&str] = &[
    "tools/runtime/dispatch/agent-canon/src/hook_retirement.rs",
    "documents/design/agentcanon-hook-simplification-wave3.md",
];
static COMMAND_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"^(?:import-only:tools\.[A-Za-z0-9_.]+:[A-Za-z0-9_]+|command-only:python3 tools/[A-Za-z0-9_./-]+\.py(?: [^\n]*)?|command-only:tools/bin/agent-canon (?:[a-z0-9][a-z0-9-]*|--[a-z][a-z0-9-]*)|skill-only:\$[A-Za-z0-9][A-Za-z0-9_-]*|docs-only:tools/bin/agent-canon docs check)$",
    )
    .expect("hook-retirement command grammar is valid")
});

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

fn string_value(value: &str) -> JsonValue {
    JsonValue::String(JsonString::from_text(value))
}

fn count_value(value: usize) -> JsonValue {
    JsonValue::Number(JsonNumber::Integer(value.to_string()))
}

fn value_array(values: Vec<JsonValue>) -> JsonValue {
    JsonValue::Array(JsonArray(values))
}

fn value_object(fields: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(JsonObject(
        fields
            .into_iter()
            .map(|(name, value)| (key(name), value))
            .collect(),
    ))
}

fn path_sort_key(path: &Path) -> Vec<String> {
    path.components()
        .map(|component| {
            let value = component.as_os_str().to_string_lossy().into_owned();
            #[cfg(windows)]
            {
                value.to_lowercase()
            }
            #[cfg(not(windows))]
            {
                value
            }
        })
        .collect()
}

fn path_as_posix(path: &Path) -> String {
    let value = path.to_string_lossy();
    #[cfg(windows)]
    {
        value.replace('\\', "/")
    }
    #[cfg(not(windows))]
    {
        value.into_owned()
    }
}

fn relative(root: &Path, path: &Path) -> String {
    path_as_posix(path.strip_prefix(root).unwrap_or(path))
}

fn files(root: &Path, relative_path: &str) -> Vec<PathBuf> {
    let selected = root.join(relative_path);
    if selected.is_file() {
        return vec![selected];
    }
    if !selected.is_dir() {
        return Vec::new();
    }

    let mut pending = vec![selected];
    let mut files = Vec::new();
    while let Some(directory) = pending.pop() {
        let Ok(entries) = fs::read_dir(directory) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if entry.file_type().is_ok_and(|kind| kind.is_dir()) {
                pending.push(path.clone());
            }
            if path.is_file() {
                files.push(path);
            }
        }
    }
    files.sort_by_key(|path| path_sort_key(path));
    files
}

#[derive(Clone, Debug)]
struct CallerMatch {
    path: String,
    line: usize,
    retirement_kind: String,
    token: String,
}

impl CallerMatch {
    fn to_json_value(&self) -> JsonValue {
        value_object(vec![
            ("path", string_value(&self.path)),
            ("line", count_value(self.line)),
            ("retirement_kind", string_value(&self.retirement_kind)),
            ("token", string_value(&self.token)),
        ])
    }
}

fn matches_in_files(
    root: &Path,
    files: &[PathBuf],
    tokens: &[String],
    retirement_kind: &str,
) -> Vec<CallerMatch> {
    let mut matches = Vec::new();
    for path in files {
        let Ok(contents) = fs::read_to_string(path) else {
            continue;
        };
        for (line_index, line) in python_splitlines(&contents).into_iter().enumerate() {
            for token in tokens {
                if line.contains(token.as_str()) {
                    matches.push(CallerMatch {
                        path: relative(root, path),
                        line: line_index + 1,
                        retirement_kind: retirement_kind.to_owned(),
                        token: token.clone(),
                    });
                }
            }
        }
    }
    matches
}

fn all_audit_files(root: &Path) -> Vec<PathBuf> {
    let mut seen = HashSet::new();
    let mut paths = Vec::new();
    for relative_path in CALLER_AUDIT_ROOTS {
        for path in files(root, relative_path) {
            if seen.insert(path.clone()) {
                paths.push(path);
            }
        }
    }
    paths.sort_by_key(|path| path_sort_key(path));
    paths
}

fn active_events(root: &Path) -> Vec<JsonString> {
    let path = root.join(".codex/hooks.json");
    let Ok(contents) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let Ok(JsonValue::Object(hooks)) = parse_json(&contents) else {
        return Vec::new();
    };
    let Some(JsonValue::Object(groups)) = object_value(&hooks, "hooks") else {
        return Vec::new();
    };
    let mut events: Vec<JsonString> = Vec::new();
    for (name, _) in &groups.0 {
        // Python's JSON decoder keeps the first insertion position for duplicate keys.
        if !events.iter().any(|event| event == name) {
            events.push(name.clone());
        }
    }
    events
}

fn object_value<'a>(object: &'a JsonObject, field: &str) -> Option<&'a JsonValue> {
    object
        .0
        .iter()
        .rev()
        .find(|(name, _)| name.equals_text(field))
        .map(|(_, value)| value)
}

/// Build the caller-audit payload using the existing typed tombstone rows.
pub fn contract_payload(root: &Path) -> JsonValue {
    let children = RETIRED_CHILD_TOMBSTONES
        .iter()
        .map(|row| row.to_json_value())
        .collect::<Vec<_>>();
    let moved = MOVED_SOURCE_ABSENCES
        .iter()
        .map(|row| row.to_json_value())
        .collect::<Vec<_>>();
    let child_basenames = RETIRED_CHILD_TOMBSTONES
        .iter()
        .map(|row| row.filename.to_owned())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let moved_source_old_paths = MOVED_SOURCE_ABSENCES
        .iter()
        .map(|row| format!(".codex/hooks/{}", row.filename))
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();

    let audit_files = all_audit_files(root);
    let mut matches = matches_in_files(
        root,
        &audit_files,
        &child_basenames,
        "retired_child_basename",
    );
    matches.extend(matches_in_files(
        root,
        &audit_files,
        &moved_source_old_paths,
        "moved_source_old_path",
    ));

    let executable_files = EXECUTABLE_SCAN_PATHS
        .iter()
        .flat_map(|relative_path| files(root, relative_path))
        .collect::<Vec<_>>();
    let mut executable_references = Vec::new();
    for (tokens, retirement_kind) in [
        (child_basenames.as_slice(), "retired_child_basename"),
        (moved_source_old_paths.as_slice(), "moved_source_old_path"),
    ] {
        executable_references.extend(
            matches_in_files(root, &executable_files, tokens, retirement_kind)
                .into_iter()
                .filter(|entry| !METADATA_ALLOWLIST.contains(&entry.path.as_str())),
        );
    }
    executable_references.sort_by(|left, right| {
        (&left.path, left.line, &left.token).cmp(&(&right.path, right.line, &right.token))
    });

    // Keep the historical field and behavior: it lists retired paths that are present.
    let mut missing_files = RETIRED_CHILD_TOMBSTONES
        .iter()
        .filter(|row| root.join(".codex/hooks").join(row.filename).exists())
        .map(|row| format!(".codex/hooks/{}", row.filename))
        .collect::<Vec<_>>();
    missing_files.extend(
        MOVED_SOURCE_ABSENCES
            .iter()
            .map(|row| format!(".codex/hooks/{}", row.filename))
            .filter(|path| root.join(path).exists()),
    );

    let artifacts = vec![
        value_object(vec![
            ("name", string_value("skill_usage.jsonl")),
            ("mode", string_value("historical_read_only")),
            ("producer", string_value("none")),
            (
                "parser",
                string_value("tools/runtime/archive/historical_skill_usage_reader.py"),
            ),
            (
                "consumers",
                value_array(
                    [
                        "tools/runtime/archive/historical_skill_usage_reader.py",
                        "eval/producers/generate_agent_improvement_guide.py",
                        "eval/producers/generate_agent_runtime_dashboard.py",
                    ]
                    .into_iter()
                    .map(string_value)
                    .collect(),
                ),
            ),
        ]),
        value_object(vec![
            ("name", string_value("behavior_events.jsonl")),
            ("mode", string_value("active_canonical")),
            (
                "producer",
                string_value("tools/runtime/archive/behavior_event_assembly.py"),
            ),
            (
                "parser",
                string_value("tools/runtime/archive/behavior_event_assembly.py"),
            ),
            (
                "consumers",
                value_array(vec![string_value(
                    "eval/producers/generate_agent_runtime_dashboard.py",
                )]),
            ),
        ]),
        value_object(vec![
            ("name", string_value("workflow_monitoring.md")),
            ("mode", string_value("projection")),
            (
                "producer",
                string_value("tools/runtime/lifecycle/workflow_monitor.py"),
            ),
            (
                "parser",
                string_value("tools/runtime/lifecycle/workflow_monitor.py"),
            ),
            (
                "consumers",
                value_array(vec![
                    string_value("eval/producers/generate_agent_runtime_dashboard.py"),
                    string_value("tools/runtime/dispatch/agent-canon/src/task_close.rs"),
                ]),
            ),
        ]),
    ];
    let malformed_matches = matches
        .iter()
        .filter(|entry| entry.token.is_empty())
        .map(CallerMatch::to_json_value)
        .collect::<Vec<_>>();
    let caller_audit = value_object(vec![
        ("schema", string_value(CALLER_AUDIT_SCHEMA)),
        (
            "retired_child_basenames",
            value_array(child_basenames.iter().map(|value| string_value(value)).collect()),
        ),
        (
            "moved_source_old_paths",
            value_array(
                moved_source_old_paths
                    .iter()
                    .map(|value| string_value(value))
                    .collect(),
            ),
        ),
        (
            "matches",
            value_array(matches.iter().map(CallerMatch::to_json_value).collect()),
        ),
        ("malformed_matches", value_array(malformed_matches)),
        ("artifacts", value_array(artifacts)),
    ]);

    value_object(vec![
        ("schema", string_value(TOMBSTONE_SCHEMA)),
        ("retired_child_tombstones", value_array(children)),
        ("moved_source_absences", value_array(moved)),
        (
            "counts",
            value_object(vec![
                (
                    "retired_child_tombstones",
                    count_value(RETIRED_CHILD_TOMBSTONES.len()),
                ),
                (
                    "moved_source_absences",
                    count_value(MOVED_SOURCE_ABSENCES.len()),
                ),
                (
                    "retired_filenames",
                    count_value(child_basenames.len() + moved_source_old_paths.len()),
                ),
            ]),
        ),
        (
            "active_events",
            value_array(active_events(root).into_iter().map(JsonValue::String).collect()),
        ),
        (
            "inactive_events",
            value_array(vec![string_value("Stop")]),
        ),
        ("source_digest", string_value(&source_digest())),
        (
            "missing_files",
            value_array(missing_files.drain(..).map(|value| string_value(&value)).collect()),
        ),
        (
            "executable_references",
            value_array(
                executable_references
                    .iter()
                    .map(CallerMatch::to_json_value)
                    .collect(),
            ),
        ),
        ("caller_audit", caller_audit),
    ])
}

fn as_object(value: Option<&JsonValue>) -> Option<&JsonObject> {
    match value {
        Some(JsonValue::Object(object)) => Some(object),
        _ => None,
    }
}

fn as_array(value: Option<&JsonValue>) -> Option<&JsonArray> {
    match value {
        Some(JsonValue::Array(array)) => Some(array),
        _ => None,
    }
}

fn as_text(value: Option<&JsonValue>) -> Option<String> {
    match value {
        Some(JsonValue::String(text)) => text.to_text(),
        _ => None,
    }
}

fn string_array_matches(value: Option<&JsonValue>, expected: &[&str]) -> bool {
    let Some(JsonValue::Array(values)) = value else {
        return false;
    };
    values.0.len() == expected.len()
        && values
            .0
            .iter()
            .zip(expected)
            .all(|(actual, expected)| matches!(actual, JsonValue::String(text) if text.equals_text(expected)))
}

fn integer_matches(value: Option<&JsonValue>, expected: usize) -> bool {
    matches!(value, Some(JsonValue::Number(JsonNumber::Integer(actual))) if actual == &expected.to_string())
}

fn regex_fullmatch(regex: &Regex, value: &str) -> bool {
    regex
        .find(value)
        .is_some_and(|matched| matched.start() == 0 && matched.end() == value.len())
}

fn check_payload(payload: &JsonValue) -> Vec<&'static str> {
    let mut errors = Vec::new();
    let root = match payload {
        JsonValue::Object(root) => root,
        _ => return vec!["retired_child_tombstones", "moved_source_absences", "retired_filenames"],
    };
    let children = as_array(object_value(root, "retired_child_tombstones"));
    let moved = as_array(object_value(root, "moved_source_absences"));
    if children.map_or(0, |rows| rows.0.len()) != RETIRED_CHILD_TOMBSTONES.len() {
        errors.push("retired_child_tombstones");
    }
    if moved.map_or(0, |rows| rows.0.len()) != MOVED_SOURCE_ABSENCES.len() {
        errors.push("moved_source_absences");
    }
    let retired_filename_count = as_object(object_value(root, "counts"))
        .and_then(|counts| object_value(counts, "retired_filenames"));
    if !integer_matches(retired_filename_count, RETIRED_CHILD_TOMBSTONES.len() + MOVED_SOURCE_ABSENCES.len()) {
        errors.push("retired_filenames");
    }
    if as_array(object_value(root, "missing_files")).is_some_and(|files| !files.0.is_empty()) {
        errors.push("missing_files");
    }
    if as_array(object_value(root, "executable_references"))
        .is_some_and(|references| !references.0.is_empty())
    {
        errors.push("executable_references");
    }
    let invalid_command = children.is_some_and(|rows| {
        rows.0.iter().any(|row| {
            let Some(command) = as_text(as_object(Some(row)).and_then(|row| {
                object_value(row, "command_or_skill")
            })) else {
                return true;
            };
            !regex_fullmatch(&COMMAND_RE, &command)
                || [".codex/hooks/", "compat", "wrapper", "shim", "fallback"]
                    .iter()
                    .any(|bad| command.contains(bad))
        })
    });
    if invalid_command {
        errors.push("command_or_skill_grammar");
    }
    if !string_array_matches(
        object_value(root, "active_events"),
        &["UserPromptSubmit", "PreToolUse", "PostToolUse"],
    ) {
        errors.push("active_events");
    }
    if !string_array_matches(object_value(root, "inactive_events"), &["Stop"]) {
        errors.push("inactive_events");
    }
    errors
}

#[derive(Clone, Copy)]
enum CliOption {
    Help,
    Root,
    Check,
    Contract,
}

const CLI_OPTIONS: &[(&str, CliOption)] = &[
    ("--help", CliOption::Help),
    ("--root", CliOption::Root),
    ("--check", CliOption::Check),
    ("--contract", CliOption::Contract),
];

struct CliArgs {
    root: PathBuf,
    check: bool,
}

const USAGE: &str =
    "usage: agent-canon hook-retirement-check [-h] [--root ROOT] [--check] [--contract]\n";
const HELP: &str = "usage: agent-canon hook-retirement-check [-h] [--root ROOT] [--check] [--contract]

Read the typed hook-retirement manifest and audit callers in the selected source root.

options:
  -h, --help     show this help message and exit
  --root ROOT
  --check
  --contract
";

fn parse_arguments(args: &[String]) -> Result<Option<CliArgs>, String> {
    let mut root = env::current_dir().map_err(|error| format!("current directory: {error}"))?;
    let mut check = false;
    let mut unrecognized = Vec::new();
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        if token == "--" {
            unrecognized.extend(args[index + 1..].iter().cloned());
            break;
        }
        if token == "-h" || token == "--help" {
            return Ok(None);
        }
        if !token.starts_with("--") {
            unrecognized.push(token.clone());
            index += 1;
            continue;
        }
        let (option_text, inline_value) = match token.split_once('=') {
            Some((option, value)) => (option, Some(value)),
            None => (token.as_str(), None),
        };
        let option = match resolve_long_option_prefix(option_text, CLI_OPTIONS) {
            Ok(option) => option,
            Err(LongOptionError::Unrecognized) => {
                unrecognized.push(token.clone());
                index += 1;
                continue;
            }
            Err(LongOptionError::Ambiguous(_)) => {
                return Err(format!("ambiguous option: {option_text}"));
            }
        };
        if matches!(option, CliOption::Help) {
            if inline_value.is_some() {
                return Err(format!("ignored explicit argument for --help: {token}"));
            }
            return Ok(None);
        }
        match option {
            CliOption::Root => {
                let value = if let Some(value) = inline_value {
                    value.to_owned()
                } else {
                    index += 1;
                    let Some(value) = args.get(index) else {
                        return Err(format!("argument {option_text}: expected one argument"));
                    };
                    if value.starts_with('-')
                        && !crate::python_cli_integer::is_argparse_negative_number(value)
                    {
                        return Err(format!("argument {option_text}: expected one argument"));
                    }
                    value.clone()
                };
                root = PathBuf::from(value);
            }
            CliOption::Check | CliOption::Contract => {
                if inline_value.is_some() {
                    return Err(format!("ignored explicit argument for {option_text}"));
                }
                match option {
                    CliOption::Check => check = true,
                    CliOption::Contract => {}
                    _ => unreachable!("handled boolean option"),
                }
            }
            CliOption::Help => unreachable!("help is handled before option parsing"),
        }
        index += 1;
    }
    if !unrecognized.is_empty() {
        return Err(format!("unrecognized arguments: {}", unrecognized.join(" ")));
    }
    Ok(Some(CliArgs { root, check }))
}

/// Run the native hook-retirement caller-audit command.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_arguments(args) {
        Ok(Some(options)) => options,
        Ok(None) => {
            print!("{HELP}");
            return 0;
        }
        Err(error) => {
            eprintln!("{USAGE}agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let root = match resolve_non_strict(&options.root) {
        Ok(root) => root,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: {error}");
            return 1;
        }
    };
    let payload = contract_payload(&root);
    let bytes = match canonical_json_ascii_bytes(&payload) {
        Ok(bytes) => bytes,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: serialize contract: {error}");
            return 1;
        }
    };
    let mut stdout = std::io::stdout().lock();
    if stdout.write_all(&bytes).and_then(|()| stdout.write_all(b"\n")).is_err() {
        return 1;
    }
    if options.check {
        let errors = check_payload(&payload);
        if !errors.is_empty() {
            eprintln!("hook retirement check failed: {}", errors.join(","));
            return 1;
        }
    }
    0
}
