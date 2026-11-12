use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use rustpython_ast::bigint::BigInt;
use serde::ser::{SerializeStruct, Serializer};
use serde::Serialize;

use crate::python_cli_integer;
use crate::python_json::{
    parse_json, python_json_ascii_bytes, JsonArray, JsonNumber, JsonObject, JsonString, JsonValue,
};
use crate::python_text::{python_splitlines, python_strip};
use crate::runtime_boundary::RuntimeArtifactBoundary;

#[derive(Clone, Debug)]
pub(super) struct RuntimeSummary {
    pub(super) calls: BigInt,
    pub(super) tokens: BigInt,
    pub(super) latency_ms: BigInt,
    pub(super) retries: BigInt,
    pub(super) parent_interventions: BigInt,
    pub(super) format_violations: BigInt,
    pub(super) output_used: BigInt,
}

impl RuntimeSummary {
    fn zero() -> Self {
        Self {
            calls: BigInt::from(0_u8),
            tokens: BigInt::from(0_u8),
            latency_ms: BigInt::from(0_u8),
            retries: BigInt::from(0_u8),
            parent_interventions: BigInt::from(0_u8),
            format_violations: BigInt::from(0_u8),
            output_used: BigInt::from(0_u8),
        }
    }
}

impl Serialize for RuntimeSummary {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let mut state = serializer.serialize_struct("RuntimeSummary", 7)?;
        let calls = serde_number(&self.calls).map_err(serde::ser::Error::custom)?;
        let tokens = serde_number(&self.tokens).map_err(serde::ser::Error::custom)?;
        let latency_ms = serde_number(&self.latency_ms).map_err(serde::ser::Error::custom)?;
        let retries = serde_number(&self.retries).map_err(serde::ser::Error::custom)?;
        let parent_interventions =
            serde_number(&self.parent_interventions).map_err(serde::ser::Error::custom)?;
        let format_violations =
            serde_number(&self.format_violations).map_err(serde::ser::Error::custom)?;
        let output_used = serde_number(&self.output_used).map_err(serde::ser::Error::custom)?;
        state.serialize_field("calls", &calls)?;
        state.serialize_field("tokens", &tokens)?;
        state.serialize_field("latency_ms", &latency_ms)?;
        state.serialize_field("retries", &retries)?;
        state.serialize_field("parent_interventions", &parent_interventions)?;
        state.serialize_field("format_violations", &format_violations)?;
        state.serialize_field("output_used", &output_used)?;
        state.end()
    }
}

fn serde_number(value: &BigInt) -> Result<serde_json::Number, String> {
    value
        .to_string()
        .parse::<serde_json::Number>()
        .map_err(|error| format!("runtime metric integer serialization failed: {error}"))
}

/// Aggregate explicit and archived role runtime logs using the producer's path order.
///
/// Explicit paths remain in caller order. Sorted default-directory paths are appended without
/// deduplication, so the same file selected both ways contributes twice, matching the Python
/// producer.
type AggregatedMetrics = (
    String,
    BTreeMap<String, RuntimeSummary>,
    Vec<super::Finding>,
);

pub(super) fn aggregate(
    root: &Path,
    explicit_logs: &[String],
    runtime_root: Option<&Path>,
) -> Result<AggregatedMetrics, String> {
    if runtime_root.is_none() && explicit_logs.is_empty() {
        return Ok(("missing".to_owned(), BTreeMap::new(), Vec::new()));
    }
    let boundary = RuntimeArtifactBoundary::for_source(root, runtime_root, false)?;
    let paths = runtime_log_paths(&boundary, explicit_logs)?;
    if paths.is_empty() {
        return Ok(("missing".to_owned(), BTreeMap::new(), Vec::new()));
    }

    let mut summaries = BTreeMap::<String, RuntimeSummary>::new();
    let mut findings = Vec::new();
    for path in paths {
        let bytes = boundary
            .read_bytes(&path)
            .map_err(|error| format!("runtime log {}: {error}", path.display()))?
            .ok_or_else(|| format!("runtime log disappeared: {}", path.display()))?;
        let text = String::from_utf8(bytes)
            .map_err(|error| format!("runtime log is not UTF-8 {}: {error}", path.display()))?;
        for (line_index, line) in python_splitlines(&text).into_iter().enumerate() {
            if python_strip(line).is_empty() {
                continue;
            }
            let entry = match parse_json(line) {
                Ok(JsonValue::Object(object)) => object,
                Ok(_) => {
                    findings.push(super::Finding::new(
                        "runtime-log",
                        format!("{}:{}", path.display(), line_index + 1),
                        "entry-not-object",
                    ));
                    continue;
                }
                Err(_) => {
                    findings.push(super::Finding::new(
                        "runtime-log",
                        format!("{}:{}", path.display(), line_index + 1),
                        "invalid-json",
                    ));
                    continue;
                }
            };
            let agent_id = ["agent", "codex_agent", "role"]
                .iter()
                .filter_map(|key| object_value(&entry, key))
                .find(|value| python_truthy(value))
                .map(python_string)
                .unwrap_or_default();
            if agent_id.is_empty() {
                findings.push(super::Finding::new(
                    "runtime-log",
                    format!("{}:{}", path.display(), line_index + 1),
                    "missing-agent",
                ));
                continue;
            }

            let summary = summaries
                .entry(agent_id.clone())
                .or_insert_with(RuntimeSummary::zero);
            summary.calls += BigInt::from(1_u8);
            for (metric_name, keys) in [
                ("tokens", &(["tokens", "total_tokens"])[..]),
                ("latency_ms", &(["latency_ms", ""])[..1]),
                ("retries", &(["retry_count", "retries"])[..]),
            ] {
                let (value, finding) = int_metric(&entry, keys)?;
                match metric_name {
                    "tokens" => summary.tokens += value,
                    "latency_ms" => summary.latency_ms += value,
                    "retries" => summary.retries += value,
                    _ => unreachable!("metrics are declared above"),
                }
                if let Some(field) = finding {
                    findings.push(super::Finding::new(
                        "runtime-log",
                        format!("{}:{}:{}:{field}", path.display(), line_index + 1, agent_id),
                        "invalid-int-metric",
                    ));
                }
            }
            summary.parent_interventions += bool_integer(
                object_value(&entry, "parent_intervention").is_some_and(python_truthy),
            );
            summary.format_violations +=
                bool_integer(object_value(&entry, "format_violation").is_some_and(python_truthy));
            summary.output_used +=
                bool_integer(object_value(&entry, "output_used").is_some_and(python_truthy));
        }
    }
    Ok(("observed".to_owned(), summaries, findings))
}

fn bool_integer(value: bool) -> BigInt {
    BigInt::from(u8::from(value))
}

fn runtime_log_paths(
    boundary: &RuntimeArtifactBoundary,
    explicit_logs: &[String],
) -> Result<Vec<PathBuf>, String> {
    let mut paths = Vec::new();
    for raw in explicit_logs {
        let path = boundary.resolve(Path::new(raw))?;
        if path.is_file() {
            paths.push(path);
        }
    }
    let default_dir = boundary.resolve(Path::new("metrics/subagent-role-runtime"))?;
    if default_dir.is_dir() {
        let mut default_paths = Vec::new();
        if let Ok(entries) = fs::read_dir(&default_dir) {
            for entry in entries.filter_map(Result::ok) {
                let path = entry.path();
                if path.extension().and_then(|extension| extension.to_str()) != Some("jsonl") {
                    continue;
                }
                let path = boundary.resolve(&path)?;
                if path.is_file() {
                    default_paths.push(path);
                }
            }
        }
        default_paths.sort();
        paths.extend(default_paths);
    }
    Ok(paths)
}

fn object_value<'a>(object: &'a JsonObject, key: &str) -> Option<&'a JsonValue> {
    object
        .0
        .iter()
        .rev()
        .find(|(candidate, _)| candidate.equals_text(key))
        .map(|(_, value)| value)
}

fn python_truthy(value: &JsonValue) -> bool {
    match value {
        JsonValue::Null => false,
        JsonValue::Bool(value) => *value,
        JsonValue::Number(JsonNumber::Integer(value)) => {
            python_cli_integer::parse(value).is_some_and(|value| value != BigInt::from(0_u8))
        }
        JsonValue::Number(JsonNumber::Float(value)) => *value != 0.0,
        JsonValue::String(value) => !value.is_empty(),
        JsonValue::Array(JsonArray(values)) => !values.is_empty(),
        JsonValue::Object(JsonObject(values)) => !values.is_empty(),
    }
}

fn python_string(value: &JsonValue) -> String {
    match value {
        JsonValue::Null => "None".to_owned(),
        JsonValue::Bool(value) => if *value { "True" } else { "False" }.to_owned(),
        JsonValue::Number(JsonNumber::Integer(value)) => value.clone(),
        JsonValue::Number(JsonNumber::Float(value)) => crate::python_json::python_float(*value),
        JsonValue::String(value) => json_string_text(value),
        JsonValue::Array(_) | JsonValue::Object(_) => python_json_ascii_bytes(value)
            .ok()
            .and_then(|bytes| String::from_utf8(bytes).ok())
            .unwrap_or_default(),
    }
}

fn json_string_text(value: &JsonString) -> String {
    if let Some(text) = value.to_text() {
        return text;
    }
    let mut text = String::new();
    for codepoint in &value.0 {
        if let Some(character) = char::from_u32(*codepoint) {
            text.push(character);
        } else {
            use std::fmt::Write as _;
            let _ = write!(text, "\\u{codepoint:04x}");
        }
    }
    text
}

fn int_metric(entry: &JsonObject, keys: &[&str]) -> Result<(BigInt, Option<String>), String> {
    for key in keys {
        let Some(value) = object_value(entry, key) else {
            continue;
        };
        if matches!(value, JsonValue::Null) {
            continue;
        }
        return metric_value(value, key);
    }
    Ok((BigInt::from(0_u8), None))
}

fn metric_value(value: &JsonValue, key: &str) -> Result<(BigInt, Option<String>), String> {
    match value {
        JsonValue::Bool(value) => Ok((bool_integer(*value), None)),
        JsonValue::Number(JsonNumber::Integer(value)) => Ok((
            python_cli_integer::parse(value)
                .ok_or_else(|| format!("invalid JSON integer runtime metric {key}"))?,
            None,
        )),
        JsonValue::Number(JsonNumber::Float(value)) => {
            let integer = finite_float_to_integer(*value)?;
            let finding = (value.fract() != 0.0).then(|| key.to_owned());
            Ok((integer, finding))
        }
        JsonValue::String(value) => {
            let stripped = python_strip(&json_string_text(value)).to_owned();
            if let Some(integer) = python_cli_integer::parse(&stripped) {
                return Ok((integer, None));
            }
            match parse_python_float(&stripped) {
                Ok(number) if number.is_nan() => Ok((BigInt::from(0_u8), Some(key.to_owned()))),
                Ok(number) if number.is_infinite() => Err(format!(
                    "cannot convert float infinity to integer in runtime metric {key}"
                )),
                Ok(number) => Ok((finite_float_to_integer(number)?, Some(key.to_owned()))),
                Err(()) => Ok((BigInt::from(0_u8), Some(key.to_owned()))),
            }
        }
        JsonValue::Null | JsonValue::Array(_) | JsonValue::Object(_) => {
            Ok((BigInt::from(0_u8), Some(key.to_owned())))
        }
    }
}

fn parse_python_float(value: &str) -> Result<f64, ()> {
    let normalized = normalize_python_float_digits(value)?;
    normalized.parse::<f64>().map_err(|_| ())
}

fn normalize_python_float_digits(value: &str) -> Result<String, ()> {
    let characters = value.chars().collect::<Vec<_>>();
    let mut normalized = String::with_capacity(value.len());
    for (index, character) in characters.iter().copied().enumerate() {
        if character == '_' {
            let prior_digit = index
                .checked_sub(1)
                .and_then(|prior| python_cli_integer::decimal_digit_value(characters[prior]))
                .is_some();
            let next_digit = characters
                .get(index + 1)
                .and_then(|next| python_cli_integer::decimal_digit_value(*next))
                .is_some();
            if !prior_digit || !next_digit {
                return Err(());
            }
            continue;
        }
        if let Some(digit) = python_cli_integer::decimal_digit_value(character) {
            normalized.push(char::from(b'0' + digit));
        } else {
            normalized.push(character);
        }
    }
    Ok(normalized)
}

fn finite_float_to_integer(value: f64) -> Result<BigInt, String> {
    if !value.is_finite() {
        return Err(if value.is_nan() {
            "cannot convert float NaN to integer".to_owned()
        } else {
            "cannot convert float infinity to integer".to_owned()
        });
    }
    let decimal = format!("{:.0}", value.trunc());
    python_cli_integer::parse(&decimal)
        .ok_or_else(|| "cannot convert finite runtime float to integer".to_owned())
}
