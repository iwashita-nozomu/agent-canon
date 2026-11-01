// @dependency-start
// contract implementation
// responsibility Assembles one pure, deduplicatable behavior event from typed hook observations.
// upstream implementation ../../../../../tools/runtime/archive/behavior_event_assembly.py owns the current API contract.
// upstream implementation ./prompt_capture.rs owns bounded prompt evidence and redaction.
// upstream implementation ./prompt_classifier.rs owns prompt classification.
// upstream implementation ./tool_selection.rs owns tool observations.
// upstream implementation ./subagent_selection.rs owns subagent observations and coordination receipts.
// upstream implementation ./workflow_context.rs owns read-only workflow context values.
// upstream implementation ./python_json.rs owns Python-compatible canonical JSON bytes.
// downstream implementation ../tests/behavior_event_assembly_native.rs checks the frozen CPython 3.12.3 assembly oracle.
// downstream evidence ../../../../../tests/fixtures/behavior_event_assembly/python_golden.json freezes old assembly inputs and outputs.
// @dependency-end
//! Pure behavior-event eligibility and assembly from typed hook observations.

use crate::prompt_capture::{capture_prompt, PromptCapture, PromptCaptureError};
use crate::prompt_classifier::{
    feedback_targets, prompt_intake_signals, PromptClassifierInputs, PromptIntakeSignals,
};
use crate::python_json::{
    canonical_json_ascii_bytes_reject_nonfinite, JsonArray, JsonNumber, JsonObject, JsonString,
    JsonValue,
};
use crate::subagent_selection::SubagentSelection;
use crate::tool_selection::{select_tools, ToolSelection};
use crate::workflow_context::WorkflowContext;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

pub const SCHEMA: &str = "agent-canon.behavior-event.v1";
pub const RECORD_KIND: &str = "behavior_event";
pub const EVENT_KIND: &str = "behavior_snapshot";

const ACTIVE_EVENTS: [&str; 3] = ["UserPromptSubmit", "PreToolUse", "PostToolUse"];
const INELIGIBLE_STATUSES: [&str; 4] = [
    "malformed_payload",
    "blocked_secret",
    "blocked_destructive_git",
    "blocked_parent_mutation",
];
const PARITY_FIELDS: &[&str] = &[
    "hook_log_namespace",
    "root",
    "event_declared",
    "skills",
    "selected_skills",
    "skill_selection_kind",
    "skill_count",
    "selected_workflow",
    "selected_workflows",
    "workflow",
    "workflow_family",
    "workflow_selection_kind",
    "workflow_attribution_kind",
    "workflow_owner",
    "workflow_owner_workflows",
    "workflow_context_kind",
    "workflow_context_source",
    "workflow_context_workflows",
    "workflow_context_timestamp",
    "workflow_context_source_event",
    "selected_workflow_count",
    "candidate_skills",
    "candidate_skill_reasons",
    "candidate_skill_count",
    "candidate_workflows",
    "candidate_workflow_count",
    "candidate_tools",
    "candidate_tool_count",
    "prompt_capture_status",
    "prompt_excerpt_redacted",
    "prompt_fingerprint",
    "prompt_char_count",
    "prompt_excerpt_truncated",
    "tool_name",
    "tool_selection_kind",
    "tool_input_fingerprint",
    "tool_input_key_count",
    "tool_input_keys",
    "tool_command_verb",
    "selected_tools",
    "selected_tool_count",
    "subagent_invoked",
    "subagent_event_kind",
    "subagent_tool_name",
    "subagent_agent_type",
    "subagent_target",
    "subagent_targets",
    "subagent_target_count",
    "subagent_model",
    "subagent_reasoning_effort",
    "subagent_fork_context",
    "subagent_prompt_fingerprint",
    "subagent_prompt_char_count",
    "subagent_item_count",
    "prompt_feedback_detected",
    "feedback_labels",
    "feedback_targets",
    "feedback_action",
    "skill_source_fields",
    "observed_text_field_count",
    "observed_text_value_count",
    "payload_key_count",
    "payload_fingerprint",
    "tool_input_fingerprint",
    "workflow_monitor_event_count",
    "workflow_monitor_feedback_count",
    "workflow_monitor_subagent_event_count",
    "workflow_monitor_report_dir",
];

/// The final dispatcher status and safe metadata; safe fields remain unconsumed here.
pub struct FinalHandlerResult {
    pub status: JsonString,
    pub output_kind: JsonString,
    pub safe_fields: JsonValue,
}

impl Default for FinalHandlerResult {
    fn default() -> Self {
        Self {
            status: JsonString::from_text("pass"),
            output_kind: JsonString::default(),
            safe_fields: empty_object(),
        }
    }
}

/// Typed inputs assembled by the caller from the original hook request and existing leaf APIs.
pub struct HookInvocationParts<'a> {
    pub hook_event_name: JsonString,
    pub hook_invocation_id: JsonString,
    pub hook_payload: Option<&'a JsonValue>,
    pub payload_status: JsonString,
    pub handler_result: FinalHandlerResult,
    pub classifier_rules: Option<&'a PromptClassifierInputs<'a>>,
    pub tool_selection: Option<&'a ToolSelection>,
    pub subagent_selection: Option<&'a SubagentSelection>,
    pub workflow_context: &'a WorkflowContext,
    pub payload_fingerprint: JsonString,
    pub timestamp: JsonString,
    pub root: PathBuf,
    pub hook_log_namespace: JsonString,
    pub report_dir: Option<PathBuf>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum BehaviorEventError {
    PromptCapture(PromptCaptureError),
    ToolSelection(String),
    CanonicalJson(String),
    UnsupportedHookEvent,
}

/// One pure assembled behavior event.
pub struct BehaviorEvent {
    data: JsonValue,
    event_id: JsonString,
}

impl BehaviorEvent {
    pub fn event_id(&self) -> &JsonString {
        &self.event_id
    }

    pub fn as_json_value(&self) -> &JsonValue {
        &self.data
    }

    pub fn canonical_bytes(&self) -> Result<Vec<u8>, BehaviorEventError> {
        canonical_json_ascii_bytes_reject_nonfinite(&self.data)
            .map_err(BehaviorEventError::CanonicalJson)
    }
}

struct SignalBundle {
    prompt: PromptCapture,
    classifier: PromptIntakeSignals,
    tool: ToolSelection,
    subagent: SubagentSelection,
}

/// Return whether the selected event has sufficient safe observation evidence.
pub fn eligible_hook_invocation(
    parts: &HookInvocationParts<'_>,
) -> Result<bool, BehaviorEventError> {
    if !is_active_event(&parts.hook_event_name) {
        return Ok(false);
    }
    if !parts.payload_status.equals_text("parsed")
        || INELIGIBLE_STATUSES
            .iter()
            .any(|status| parts.handler_result.status.equals_text(status))
    {
        return Ok(false);
    }
    let signals = signal_bundle(parts)?;
    Ok(signals.prompt.should_log()
        || signals.classifier.should_log()
        || signals.tool.should_log()
        || signals.subagent.should_log()
        || parts.workflow_context.has_workflow())
}

/// Assemble one active behavior event without writing it.
pub fn assemble_behavior_event(
    parts: &HookInvocationParts<'_>,
) -> Result<BehaviorEvent, BehaviorEventError> {
    if !is_active_event(&parts.hook_event_name) {
        return Err(BehaviorEventError::UnsupportedHookEvent);
    }

    let signals = signal_bundle(parts)?;
    let empty_payload = empty_object();
    let payload = effective_payload_with_empty(parts.hook_payload, &empty_payload);
    let payload_fingerprint = if parts.payload_fingerprint.is_empty() {
        let bytes = canonical_json_ascii_bytes_reject_nonfinite(payload)
            .map_err(BehaviorEventError::CanonicalJson)?;
        JsonString::from_text(&sha256_hex(&bytes))
    } else {
        parts.payload_fingerprint.clone()
    };
    let mut parity_fields = assemble_fields(parts, &signals, payload, payload_fingerprint.clone());
    let schema = JsonString::from_text(SCHEMA);
    let record_kind = JsonString::from_text(RECORD_KIND);
    let event_kind = JsonString::from_text(EVENT_KIND);
    let source = JsonString::from_text("behavior_event_assembly");

    let mut behavior_fields = vec![
        (key("schema"), JsonValue::String(schema.clone())),
        (key("record_kind"), JsonValue::String(record_kind.clone())),
        (
            key("hook_invocation_id"),
            JsonValue::String(parts.hook_invocation_id.clone()),
        ),
        (
            key("hook_event_name"),
            JsonValue::String(parts.hook_event_name.clone()),
        ),
        (key("event_kind"), JsonValue::String(event_kind.clone())),
        (key("source"), JsonValue::String(source.clone())),
        (
            key("status"),
            JsonValue::String(parts.handler_result.status.clone()),
        ),
    ];
    behavior_fields.extend(std::mem::take(&mut parity_fields.0));

    let preimage = JsonValue::Object(JsonObject(vec![
        (key("schema"), JsonValue::String(schema)),
        (key("record_kind"), JsonValue::String(record_kind)),
        (
            key("hook_invocation_id"),
            JsonValue::String(parts.hook_invocation_id.clone()),
        ),
        (
            key("hook_event_name"),
            JsonValue::String(parts.hook_event_name.clone()),
        ),
        (key("event_kind"), JsonValue::String(event_kind)),
        (
            key("payload_fingerprint"),
            JsonValue::String(payload_fingerprint),
        ),
        (
            key("behavior_fields"),
            JsonValue::Object(JsonObject(behavior_fields)),
        ),
    ]));
    let preimage_bytes = canonical_json_ascii_bytes_reject_nonfinite(&preimage)
        .map_err(BehaviorEventError::CanonicalJson)?;
    let event_id = JsonString::from_text(&sha256_hex(&preimage_bytes));
    let behavior_fields = take_behavior_fields(preimage)?;
    let JsonValue::Object(mut event) = behavior_fields else {
        return Err(BehaviorEventError::CanonicalJson(
            "behavior event fields are not an object".to_owned(),
        ));
    };
    event
        .0
        .push((key("timestamp"), JsonValue::String(parts.timestamp.clone())));
    event
        .0
        .push((key("event_id"), JsonValue::String(event_id.clone())));

    Ok(BehaviorEvent {
        data: JsonValue::Object(event),
        event_id,
    })
}

/// Return one pure behavior candidate, suppressing capture/assembly failures.
pub fn record_hook_invocation(parts: &HookInvocationParts<'_>) -> Option<BehaviorEvent> {
    match eligible_hook_invocation(parts) {
        Ok(true) => assemble_behavior_event(parts).ok(),
        Ok(false) | Err(_) => None,
    }
}

fn signal_bundle(parts: &HookInvocationParts<'_>) -> Result<SignalBundle, BehaviorEventError> {
    let empty_payload = empty_object();
    let payload = effective_payload_with_empty(parts.hook_payload, &empty_payload);
    let prompt = capture_prompt(payload).map_err(BehaviorEventError::PromptCapture)?;
    let classifier = match parts.classifier_rules {
        Some(rules) => prompt_intake_signals(rules),
        None => {
            let empty_prompt = JsonString::default();
            let empty_rules = empty_object();
            let rules = PromptClassifierInputs {
                prompt: &empty_prompt,
                repo_root: &parts.root,
                catalog: &empty_rules,
                routing_rules: &empty_rules,
                structural_lane_evidence: &[],
                validation_repair_evidence: &[],
            };
            prompt_intake_signals(&rules)
        }
    };
    let tool = match parts.tool_selection {
        Some(tool) => tool.clone(),
        None => {
            let empty_payload = empty_object();
            select_tools(&empty_payload)
                .map_err(|error| BehaviorEventError::ToolSelection(error.message))?
        }
    };
    let subagent = parts.subagent_selection.cloned().unwrap_or_default();
    Ok(SignalBundle {
        prompt,
        classifier,
        tool,
        subagent,
    })
}

fn assemble_fields(
    parts: &HookInvocationParts<'_>,
    signals: &SignalBundle,
    payload: &JsonValue,
    payload_fingerprint: JsonString,
) -> JsonObject {
    let classifier = &signals.classifier;
    let context = parts.workflow_context;
    let selected_workflow = classifier.selected_workflows.first();
    let workflow_attribution_kind = if selected_workflow.is_some() {
        "owner"
    } else if context.has_workflow() {
        "context"
    } else {
        "missing"
    };
    let prompt_present = signals.prompt.status.equals_text("present");
    let mut fields = default_fields();

    set_field(
        &mut fields,
        "hook_log_namespace",
        JsonValue::String(parts.hook_log_namespace.clone()),
    );
    set_field(
        &mut fields,
        "root",
        JsonValue::String(path_text(&parts.root)),
    );
    set_field(&mut fields, "event_declared", JsonValue::Bool(true));
    set_field(&mut fields, "skills", string_array(&classifier.skills));
    set_field(
        &mut fields,
        "selected_skills",
        string_array(&classifier.skills),
    );
    set_field(
        &mut fields,
        "skill_selection_kind",
        text_value(if classifier.skills.is_empty() {
            ""
        } else {
            "declared_skill"
        }),
    );
    set_field(
        &mut fields,
        "skill_count",
        integer_value(classifier.skills.len()),
    );
    set_field(
        &mut fields,
        "selected_workflow",
        selected_workflow
            .cloned()
            .map(JsonValue::String)
            .unwrap_or_else(empty_string),
    );
    set_field(
        &mut fields,
        "selected_workflows",
        string_array(&classifier.selected_workflows),
    );
    set_field(
        &mut fields,
        "workflow",
        string_array(&classifier.selected_workflows),
    );
    set_field(
        &mut fields,
        "workflow_family",
        selected_workflow
            .cloned()
            .map(JsonValue::String)
            .unwrap_or_else(empty_string),
    );
    set_field(
        &mut fields,
        "workflow_selection_kind",
        text_value(if selected_workflow.is_some() {
            "declared_workflow"
        } else if context.has_workflow() {
            "context_workflow"
        } else {
            ""
        }),
    );
    set_field(
        &mut fields,
        "workflow_attribution_kind",
        text_value(workflow_attribution_kind),
    );
    set_field(
        &mut fields,
        "workflow_owner",
        selected_workflow
            .cloned()
            .map(JsonValue::String)
            .unwrap_or_else(empty_string),
    );
    set_field(
        &mut fields,
        "workflow_owner_workflows",
        string_array(&classifier.selected_workflows),
    );
    set_workflow_context_fields(&mut fields, workflow_attribution_kind, context);
    set_field(
        &mut fields,
        "selected_workflow_count",
        integer_value(classifier.selected_workflows.len()),
    );
    set_field(
        &mut fields,
        "candidate_skills",
        string_array(&classifier.candidate_skills),
    );
    set_field(
        &mut fields,
        "candidate_skill_reasons",
        string_array(&classifier.candidate_skill_reasons),
    );
    set_field(
        &mut fields,
        "candidate_skill_count",
        integer_value(classifier.candidate_skills.len()),
    );
    set_field(
        &mut fields,
        "candidate_workflows",
        string_array(&classifier.candidate_workflows),
    );
    set_field(
        &mut fields,
        "candidate_workflow_count",
        integer_value(classifier.candidate_workflows.len()),
    );
    set_field(
        &mut fields,
        "candidate_tools",
        string_array(&classifier.candidate_tools),
    );
    set_field(
        &mut fields,
        "candidate_tool_count",
        integer_value(classifier.candidate_tools.len()),
    );
    set_field(
        &mut fields,
        "prompt_capture_status",
        if prompt_present {
            JsonValue::String(signals.prompt.status.clone())
        } else {
            text_value("missing")
        },
    );
    set_field(
        &mut fields,
        "prompt_excerpt_redacted",
        if prompt_present {
            JsonValue::String(signals.prompt.excerpt_redacted.clone())
        } else {
            empty_string()
        },
    );
    set_field(
        &mut fields,
        "prompt_fingerprint",
        if prompt_present {
            text_value(&signals.prompt.fingerprint)
        } else {
            empty_string()
        },
    );
    set_field(
        &mut fields,
        "prompt_char_count",
        integer_value(if prompt_present {
            signals.prompt.char_count
        } else {
            0
        }),
    );
    set_field(
        &mut fields,
        "prompt_excerpt_truncated",
        JsonValue::Bool(prompt_present && signals.prompt.truncated),
    );
    set_field(
        &mut fields,
        "tool_name",
        JsonValue::String(signals.tool.tool_name.clone()),
    );
    set_field(
        &mut fields,
        "tool_selection_kind",
        text_value(&signals.tool.selection_kind),
    );
    set_field(
        &mut fields,
        "tool_input_fingerprint",
        text_value(&signals.tool.tool_input_fingerprint),
    );
    set_field(
        &mut fields,
        "tool_input_key_count",
        integer_value(signals.tool.tool_input_key_count),
    );
    set_field(
        &mut fields,
        "tool_input_keys",
        string_array(&signals.tool.tool_input_keys),
    );
    set_field(
        &mut fields,
        "tool_command_verb",
        text_value(&signals.tool.command_verb),
    );
    set_field(
        &mut fields,
        "selected_tools",
        string_array(&signals.tool.selected_tools),
    );
    set_field(
        &mut fields,
        "selected_tool_count",
        integer_value(signals.tool.selected_tools.len()),
    );
    set_field(
        &mut fields,
        "subagent_invoked",
        JsonValue::Bool(signals.subagent.invoked),
    );
    set_field(
        &mut fields,
        "subagent_event_kind",
        JsonValue::String(signals.subagent.action.clone()),
    );
    set_field(
        &mut fields,
        "subagent_tool_name",
        JsonValue::String(signals.subagent.tool_name.clone()),
    );
    set_field(
        &mut fields,
        "subagent_agent_type",
        JsonValue::String(signals.subagent.agent_type.clone()),
    );
    set_field(
        &mut fields,
        "subagent_target",
        JsonValue::String(signals.subagent.target.clone()),
    );
    set_field(
        &mut fields,
        "subagent_targets",
        string_array(&signals.subagent.targets),
    );
    set_field(
        &mut fields,
        "subagent_target_count",
        integer_value(
            signals.subagent.targets.len()
                + if signals.subagent.target.is_empty() {
                    0
                } else {
                    1
                },
        ),
    );
    set_field(
        &mut fields,
        "subagent_model",
        JsonValue::String(signals.subagent.model.clone()),
    );
    set_field(
        &mut fields,
        "subagent_reasoning_effort",
        JsonValue::String(signals.subagent.reasoning_effort.clone()),
    );
    set_field(
        &mut fields,
        "subagent_fork_context",
        JsonValue::Bool(signals.subagent.fork_context),
    );
    set_field(
        &mut fields,
        "subagent_prompt_fingerprint",
        text_value(&signals.subagent.prompt_fingerprint),
    );
    set_field(
        &mut fields,
        "subagent_prompt_char_count",
        integer_value(signals.subagent.prompt_char_count),
    );
    set_field(
        &mut fields,
        "subagent_item_count",
        integer_value(signals.subagent.item_count),
    );
    set_field(
        &mut fields,
        "prompt_feedback_detected",
        JsonValue::Bool(!classifier.feedback_labels.is_empty()),
    );
    set_field(
        &mut fields,
        "feedback_labels",
        string_array(&classifier.feedback_labels),
    );
    set_field(
        &mut fields,
        "feedback_targets",
        string_array(&feedback_targets(classifier)),
    );
    set_field(
        &mut fields,
        "feedback_action",
        JsonValue::String(classifier.feedback_action.clone()),
    );
    set_field(
        &mut fields,
        "payload_key_count",
        integer_value(object_key_count(payload)),
    );
    set_field(
        &mut fields,
        "payload_fingerprint",
        JsonValue::String(payload_fingerprint),
    );
    set_field(
        &mut fields,
        "workflow_monitor_report_dir",
        parts
            .report_dir
            .as_deref()
            .map(path_text)
            .map(JsonValue::String)
            .unwrap_or_else(empty_string),
    );

    fields
}

fn set_workflow_context_fields(
    fields: &mut JsonObject,
    attribution_kind: &str,
    context: &WorkflowContext,
) {
    if attribution_kind == "owner" {
        for (name, value) in [
            ("workflow_context_kind", ""),
            ("workflow_context_source", ""),
            ("workflow_context_timestamp", ""),
            ("workflow_context_source_event", ""),
        ] {
            set_field(fields, name, text_value(value));
        }
        set_field(
            fields,
            "workflow_context_workflows",
            JsonValue::Array(JsonArray(Vec::new())),
        );
        return;
    }
    let has_context = context.has_workflow();
    set_field(
        fields,
        "workflow_context_kind",
        text_value(if has_context { "context_workflow" } else { "" }),
    );
    set_field(
        fields,
        "workflow_context_source",
        text_value(if has_context { "recent_log" } else { "" }),
    );
    set_field(
        fields,
        "workflow_context_workflows",
        string_array(&context.workflows),
    );
    set_field(
        fields,
        "workflow_context_timestamp",
        JsonValue::String(context.timestamp.clone()),
    );
    set_field(
        fields,
        "workflow_context_source_event",
        JsonValue::String(context.source_event.clone()),
    );
}

fn default_fields() -> JsonObject {
    let mut fields = JsonObject(Vec::with_capacity(PARITY_FIELDS.len()));
    for name in PARITY_FIELDS {
        let value = if name.ends_with('s')
            || [
                "selected_tools",
                "skills",
                "workflow",
                "tool_input_keys",
                "feedback_labels",
                "feedback_targets",
            ]
            .contains(name)
        {
            JsonValue::Array(JsonArray(Vec::new()))
        } else if name.ends_with("count") {
            integer_value(0)
        } else if name.ends_with("invoked")
            || name.ends_with("context")
            || name.ends_with("truncated")
            || name.starts_with("prompt_feedback")
            || *name == "event_declared"
        {
            JsonValue::Bool(false)
        } else {
            empty_string()
        };
        set_field(&mut fields, name, value);
    }
    fields
}

fn set_field(fields: &mut JsonObject, name: &str, value: JsonValue) {
    if let Some((_, current)) = fields
        .0
        .iter_mut()
        .find(|(candidate, _)| candidate.equals_text(name))
    {
        *current = value;
    } else {
        fields.0.push((key(name), value));
    }
}

fn effective_payload_with_empty<'a>(
    payload: Option<&'a JsonValue>,
    empty: &'a JsonValue,
) -> &'a JsonValue {
    match payload {
        Some(value) if matches!(value, JsonValue::Object(_)) => value,
        _ => empty,
    }
}

fn object_key_count(payload: &JsonValue) -> usize {
    let JsonValue::Object(object) = payload else {
        return 0;
    };
    object
        .0
        .iter()
        .map(|(key, _)| key.clone())
        .collect::<BTreeSet<_>>()
        .len()
}

fn take_behavior_fields(preimage: JsonValue) -> Result<JsonValue, BehaviorEventError> {
    let JsonValue::Object(mut object) = preimage else {
        return Err(BehaviorEventError::CanonicalJson(
            "event ID preimage is not an object".to_owned(),
        ));
    };
    std::mem::take(&mut object.0)
        .into_iter()
        .find_map(|(name, value)| name.equals_text("behavior_fields").then_some(value))
        .ok_or_else(|| {
            BehaviorEventError::CanonicalJson("event ID preimage has no behavior fields".to_owned())
        })
}

fn key(value: &str) -> JsonString {
    JsonString::from_text(value)
}

fn text_value(value: &str) -> JsonValue {
    JsonValue::String(JsonString::from_text(value))
}

fn empty_string() -> JsonValue {
    JsonValue::String(JsonString::default())
}

fn empty_object() -> JsonValue {
    JsonValue::Object(JsonObject(Vec::new()))
}

fn integer_value(value: usize) -> JsonValue {
    JsonValue::Number(JsonNumber::Integer(value.to_string()))
}

fn string_array(values: &[JsonString]) -> JsonValue {
    JsonValue::Array(JsonArray(
        values.iter().cloned().map(JsonValue::String).collect(),
    ))
}

fn path_text(path: &Path) -> JsonString {
    JsonString::from_text(&path.to_string_lossy())
}

fn is_active_event(event: &JsonString) -> bool {
    ACTIVE_EVENTS.iter().any(|active| event.equals_text(active))
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
