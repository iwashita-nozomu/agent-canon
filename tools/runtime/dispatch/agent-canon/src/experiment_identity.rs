// @dependency-start
// contract implementation
// responsibility Validates the safe experiment topic and variant segment grammar needed by registry consumers.
// upstream design ../../../../../documents/experiments/experiment-registry.md defines topic and variant identities
// upstream implementation python_text.rs provides Python-compatible whitespace classification
// upstream implementation icu_normalizer::ComposingNormalizer provides NFKC comparison
// downstream implementation experiment_registry.rs validates registry topic and default-variant segments
// @dependency-end

use crate::python_json::{JsonString, JsonValue};
use crate::python_text::is_python_whitespace;
use icu_normalizer::ComposingNormalizer;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

pub const IDENTITY_SCHEMA: &str = "agentcanon.experiment-run-identity/v2";

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct ExperimentIdentity {
    pub topic: String,
    pub variant: String,
    pub run_name: String,
}

impl ExperimentIdentity {
    pub fn new(topic: &str, variant: &str, run_name: &str) -> Result<Self, String> {
        for (value, field) in [
            (topic, "topic"),
            (variant, "variant"),
            (run_name, "run_name"),
        ] {
            validate_segment(value, field)?;
        }
        Ok(Self {
            topic: topic.into(),
            variant: variant.into(),
            run_name: run_name.into(),
        })
    }

    pub fn from_value(value: &Value) -> Result<Self, String> {
        let object = value
            .as_object()
            .ok_or("identity payload must be an object")?;
        if ["topic", "variant", "run_name"]
            .iter()
            .any(|key| object.contains_key(*key))
        {
            return Err("identity fields must not be duplicated at top level".into());
        }
        let identity = object
            .get("identity")
            .and_then(Value::as_object)
            .ok_or("identity payload must contain an identity object")?;
        if identity.len() != 4
            || ["schema", "topic", "variant", "run_name"]
                .iter()
                .any(|key| !identity.contains_key(*key))
        {
            return Err("identity object has missing or extra fields".into());
        }
        if identity["schema"] != IDENTITY_SCHEMA {
            return Err("identity schema must be agentcanon.experiment-run-identity/v2".into());
        }
        let segment = |key: &str| {
            identity[key]
                .as_str()
                .ok_or_else(|| format!("{key} must be a non-empty string"))
        };
        Self::new(segment("topic")?, segment("variant")?, segment("run_name")?)
    }

    pub fn to_value(&self) -> Value {
        json!({"identity":{"schema":IDENTITY_SCHEMA,"topic":self.topic,"variant":self.variant,"run_name":self.run_name}})
    }
    pub fn result_relative_path(&self) -> PathBuf {
        Path::new("experiments")
            .join(&self.topic)
            .join("result")
            .join(&self.run_name)
    }
    pub fn raw_relative_path(&self) -> PathBuf {
        self.result_relative_path().join("raw")
    }
    pub fn report_relative_path(&self) -> PathBuf {
        Path::new("experiments")
            .join(&self.topic)
            .join("report")
            .join(format!("{}.md", self.run_name))
    }

    pub fn from_raw_relative_path(path: &Path, variant: &str) -> Result<Self, String> {
        let parts = path
            .components()
            .map(|part| match part {
                std::path::Component::Normal(value) => value.to_str(),
                _ => None,
            })
            .collect::<Option<Vec<_>>>()
            .ok_or("raw path must be repository-relative and contained")?;
        if parts.len() != 5
            || parts[0] != "experiments"
            || parts[2] != "result"
            || parts[4] != "raw"
        {
            return Err("raw path must be experiments/<topic>/result/<run_name>/raw".into());
        }
        Self::new(parts[1], variant, parts[3])
    }
}

pub fn json_field<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(object) = value else {
        return None;
    };
    let key = JsonString::from_text(key);
    object
        .0
        .iter()
        .find(|(name, _)| name == &key)
        .map(|(_, value)| value)
}

pub fn json_text(value: &JsonValue) -> Option<String> {
    if let JsonValue::String(value) = value {
        value.to_text()
    } else {
        None
    }
}

pub fn identity_from_json(value: &JsonValue) -> Result<ExperimentIdentity, String> {
    if !matches!(value, JsonValue::Object(_)) {
        return Err("identity payload must be an object".into());
    }
    if ["topic", "variant", "run_name"]
        .iter()
        .any(|field| json_field(value, field).is_some())
    {
        return Err("identity fields must not be duplicated at top level".into());
    }
    let identity =
        json_field(value, "identity").ok_or("identity payload must contain an identity object")?;
    let inner = crate::python_json::to_serde_json_value(identity)?;
    ExperimentIdentity::from_value(&json!({"identity":inner}))
}

/// Validate the shared safe segment grammar without normalizing input into acceptance.
pub fn validate_segment(value: &str, field: &str) -> Result<(), String> {
    if value.is_empty() {
        return Err(format!("{field} must be a non-empty string"));
    }
    if matches!(value, "." | "..") {
        return Err(format!("{field} must not be . or .."));
    }
    if value
        .chars()
        .any(|character| matches!(character, '/' | '\\' | '\0'))
    {
        return Err(format!("{field} must not contain a path separator or NUL"));
    }
    if value.chars().any(is_python_whitespace) {
        return Err(format!("{field} must not contain whitespace"));
    }
    let normalized = ComposingNormalizer::new_nfkc().normalize(value);
    if normalized != value {
        return Err(format!("{field} must not change under normalization"));
    }
    let mut characters = value.chars();
    let valid_first = characters
        .next()
        .is_some_and(|character| character.is_ascii_alphanumeric());
    if !valid_first
        || !characters.all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '.' | '_' | '-')
        })
    {
        return Err(format!("{field} must match [A-Za-z0-9][A-Za-z0-9._-]*"));
    }
    Ok(())
}
