// @dependency-start
// contract implementation
// responsibility Loads read-only workflow attribution context with fail-open empty-state semantics.
// upstream implementation ../../../../../tools/agent/orchestration/workflow_context.py owns the current load API contract.
// downstream implementation ../tests/workflow_context_native.rs checks the frozen CPython 3.12.3 load corpus.
// downstream evidence ../../../../../tests/fixtures/workflow_context/python_golden.json freezes old load inputs and outputs.
// @dependency-end
//! Read-only workflow context loading for native consumers.

use crate::python_json::{parse_json, JsonArray, JsonObject, JsonString, JsonValue};
use std::fs;
use std::path::Path;

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct WorkflowContext {
    pub workflows: Vec<JsonString>,
    pub timestamp: JsonString,
    pub source_event: JsonString,
}

impl WorkflowContext {
    pub fn has_workflow(&self) -> bool {
        !self.workflows.is_empty()
    }
}

/// Read one paired context file. Missing, unreadable, or malformed input is empty state.
pub fn load_workflow_context(path: &Path) -> WorkflowContext {
    let Ok(raw) = fs::read(path) else {
        return WorkflowContext::default();
    };
    let Ok(text) = String::from_utf8(raw) else {
        return WorkflowContext::default();
    };
    let Ok(value) = parse_json(&text) else {
        return WorkflowContext::default();
    };
    let JsonValue::Object(object) = value else {
        return WorkflowContext::default();
    };

    let Some(JsonValue::Array(JsonArray(workflows))) = object_field(&object, "workflows") else {
        return WorkflowContext::default();
    };
    let Some(workflows) = workflows
        .iter()
        .map(|value| match value {
            JsonValue::String(value) => Some(value.clone()),
            _ => None,
        })
        .collect::<Option<Vec<_>>>()
    else {
        return WorkflowContext::default();
    };
    let Some(timestamp) = optional_string(&object, "timestamp") else {
        return WorkflowContext::default();
    };
    let Some(source_event) = optional_string(&object, "source_event") else {
        return WorkflowContext::default();
    };

    WorkflowContext {
        workflows,
        timestamp,
        source_event,
    }
}

fn object_field<'a>(object: &'a JsonObject, key: &str) -> Option<&'a JsonValue> {
    object
        .0
        .iter()
        .rev()
        .find_map(|(candidate, value)| candidate.equals_text(key).then_some(value))
}

fn optional_string(object: &JsonObject, key: &str) -> Option<JsonString> {
    match object_field(object, key) {
        None => Some(JsonString::default()),
        Some(JsonValue::String(value)) => Some(value.clone()),
        Some(_) => None,
    }
}
