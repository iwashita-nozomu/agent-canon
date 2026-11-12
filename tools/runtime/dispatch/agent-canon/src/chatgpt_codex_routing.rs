//! Request-modality decisions from explicit facts.
// @dependency-start
// contract implementation
// responsibility Routes conversation closure and workspace execution without observing or mutating a workspace.
// upstream design ../../../../../agents/internal-routines/chatgpt-codex-routing.md owns the finite decision relation
// upstream implementation python_json.rs preserves Python JSON and ASCII output
// upstream implementation python_text.rs preserves Python whitespace
// downstream test ../tests/chatgpt_codex_routing_native.rs retains the original decision oracles
// @dependency-end

use crate::python_cli_options::resolve_long_option_prefix;
use crate::python_json::{
    parse_json, python_json_ascii_bytes, python_json_pretty_ascii_bytes, JsonArray, JsonObject,
    JsonString, JsonValue,
};
use crate::python_text::is_python_whitespace;
use std::fs;
use std::io::{self, Read, Write};

pub const EXECUTION_REASON_FIELDS: &[&str] = &[
    "explicit_codex_execution",
    "workspace_or_repository_mutation",
    "repository_local_or_uncommitted_state_required",
    "command_test_build_benchmark_runtime_observation_required",
    "iterative_inspect_edit_validate_loop_required",
    "durable_repository_delivery_required",
];
const INPUT_FIELDS: &[&str] = &[
    "requested_deliverable",
    "facts",
    "chatgpt_scope",
    "codex_scope",
    "validation_oracle",
];

#[derive(Debug, PartialEq, Eq)]
pub struct RoutingInputError {
    pub code: &'static str,
    pub field: JsonString,
}

fn error(code: &'static str, field: &str) -> RoutingInputError {
    RoutingInputError {
        code,
        field: JsonString::from_text(field),
    }
}

fn field<'a>(object: &'a JsonObject, key: &str) -> Option<&'a JsonValue> {
    object
        .0
        .iter()
        .rev()
        .find(|(name, _)| name.equals_text(key))
        .map(|(_, value)| value)
}

fn string(value: &str) -> JsonValue {
    JsonValue::String(JsonString::from_text(value))
}

fn object(fields: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(JsonObject(
        fields
            .into_iter()
            .map(|(k, v)| (JsonString::from_text(k), v))
            .collect(),
    ))
}

fn text(value: Option<&JsonValue>, name: &str) -> Result<JsonString, RoutingInputError> {
    let Some(JsonValue::String(value)) = value else {
        return Err(error("invalid_text", name));
    };
    let whitespace = |point: &u32| char::from_u32(*point).is_some_and(is_python_whitespace);
    let start = value
        .0
        .iter()
        .position(|point| !whitespace(point))
        .unwrap_or(value.0.len());
    let end = value
        .0
        .iter()
        .rposition(|point| !whitespace(point))
        .map_or(start, |i| i + 1);
    if start == end {
        return Err(error("invalid_text", name));
    }
    Ok(JsonString(value.0[start..end].to_vec()))
}

fn reject_unknown(
    object: &JsonObject,
    allowed: &[&str],
    prefix: &str,
) -> Result<(), RoutingInputError> {
    if let Some(key) = object
        .0
        .iter()
        .map(|(key, _)| key)
        .filter(|key| !allowed.iter().any(|name| key.equals_text(name)))
        .min()
    {
        let mut field = JsonString::from_text(prefix);
        field.0.extend_from_slice(&key.0);
        return Err(RoutingInputError {
            code: "unknown_field",
            field,
        });
    }
    Ok(())
}

pub fn packet_from_value(input: &JsonValue) -> Result<JsonValue, RoutingInputError> {
    let JsonValue::Object(input) = input else {
        return Err(error("invalid_mapping", "input"));
    };
    reject_unknown(input, INPUT_FIELDS, "")?;
    let empty = JsonValue::Object(JsonObject(Vec::new()));
    let JsonValue::Object(facts) = field(input, "facts").unwrap_or(&empty) else {
        return Err(error("invalid_mapping", "facts"));
    };
    let mut allowed = EXECUTION_REASON_FIELDS.to_vec();
    allowed.push("explicit_chat_only");
    reject_unknown(facts, &allowed, "facts.")?;
    let mut reasons = Vec::new();
    let mut chat_only = false;
    for name in allowed {
        let value = match field(facts, name) {
            None => false,
            Some(JsonValue::Bool(value)) => *value,
            _ => return Err(error("invalid_boolean", &format!("facts.{name}"))),
        };
        if name == "explicit_chat_only" {
            chat_only = value;
        } else if value {
            reasons.push(string(name));
        }
    }
    let deliverable = text(
        field(input, "requested_deliverable"),
        "requested_deliverable",
    )?;
    let conversation_scope = text(field(input, "chatgpt_scope"), "chatgpt_scope")?;
    let none = string("none");
    let (route, codex_scope, oracle, handoff, blocked) = if reasons.is_empty() {
        reasons.push(string(if chat_only {
            "explicit_chat_only"
        } else {
            "conversation_closure"
        }));
        ("chatgpt", string("none"), string("none"), "none", "none")
    } else {
        let scope = text(
            Some(field(input, "codex_scope").unwrap_or(&none)),
            "codex_scope",
        )?;
        let oracle = text(
            Some(field(input, "validation_oracle").unwrap_or(&none)),
            "validation_oracle",
        )?;
        if scope.equals_text("none") {
            return Err(error("missing_execution_scope", "codex_scope"));
        }
        if oracle.equals_text("none") {
            return Err(error("missing_validation_oracle", "validation_oracle"));
        }
        if chat_only {
            reasons.insert(0, string("explicit_chat_only_conflict"));
            ("chatgpt", JsonValue::String(scope), JsonValue::String(oracle), "none",
             "workspace execution is required by the requested deliverable but explicitly prohibited")
        } else {
            (
                "codex",
                JsonValue::String(scope),
                JsonValue::String(oracle),
                "agent-orchestration",
                "none",
            )
        }
    };
    Ok(object(vec![
        ("route", string(route)),
        ("reason_codes", JsonValue::Array(JsonArray(reasons))),
        ("requested_deliverable", JsonValue::String(deliverable)),
        ("chatgpt_scope", JsonValue::String(conversation_scope)),
        ("codex_scope", codex_scope),
        ("validation_oracle", oracle),
        ("handoff", string(handoff)),
        ("blocked_dependency", string(blocked)),
    ]))
}

fn failure(error: RoutingInputError) -> i32 {
    let payload = object(vec![
        ("status", string("fail")),
        ("code", string(error.code)),
        ("field", JsonValue::String(error.field)),
    ]);
    match python_json_ascii_bytes(&payload) {
        Ok(bytes) => eprintln!("{}", String::from_utf8(bytes).expect("ASCII JSON")),
        Err(message) => eprintln!("{message}"),
    }
    2
}

pub fn run_cli(args: &[String]) -> i32 {
    const USAGE: &str = "usage: agent-canon chatgpt-codex-route [-h] --input INPUT";
    let options = [("--help", false), ("--input", true)];
    let mut input = None;
    let mut position = 0;
    while position < args.len() {
        let arg = &args[position];
        if arg == "-h" {
            println!("{USAGE}\n\nDeterministic ChatGPT/Codex request-modality routing.");
            return 0;
        }
        let (name, inline) = arg
            .split_once('=')
            .map_or((arg.as_str(), None), |(a, b)| (a, Some(b)));
        match resolve_long_option_prefix(name, &options) {
            Ok(false) if inline.is_none() => {
                println!("{USAGE}\n\nDeterministic ChatGPT/Codex request-modality routing.");
                return 0;
            }
            Ok(true) => {
                if let Some(value) = inline {
                    input = Some(value.to_owned());
                } else {
                    position += 1;
                    if position >= args.len()
                        || (args[position].starts_with('-') && args[position] != "-")
                    {
                        eprintln!("{USAGE}\nagent-canon chatgpt-codex-route: error: argument --input: expected one argument");
                        return 2;
                    }
                    input = Some(args[position].clone());
                }
            }
            _ => {
                eprintln!("{USAGE}\nagent-canon chatgpt-codex-route: error: unrecognized arguments: {arg}");
                return 2;
            }
        }
        position += 1;
    }
    let Some(input) = input else {
        eprintln!("{USAGE}\nagent-canon chatgpt-codex-route: error: the following arguments are required: --input");
        return 2;
    };
    let source = if input == "-" {
        let mut source = String::new();
        io::stdin().read_to_string(&mut source).map(|_| source)
    } else {
        fs::read_to_string(&input)
    };
    let source = match source {
        Ok(source) => source,
        Err(error) if error.kind() == io::ErrorKind::InvalidData => {
            eprintln!("cannot decode routing input {input}: {error}");
            return 1;
        }
        Err(_) => return failure(error("invalid_json", &input)),
    };
    let value = match parse_json(&source) {
        Ok(value) => value,
        Err(_) => return failure(error("invalid_json", &input)),
    };
    let mut packet = match packet_from_value(&value) {
        Ok(JsonValue::Object(packet)) => packet,
        Ok(_) => unreachable!(),
        Err(error) => return failure(error),
    };
    packet
        .0
        .push((JsonString::from_text("status"), string("pass")));
    match python_json_pretty_ascii_bytes(&JsonValue::Object(packet)) {
        Ok(mut bytes) => {
            bytes.push(b'\n');
            match io::stdout().lock().write_all(&bytes) {
                Ok(()) => 0,
                Err(error) => {
                    eprintln!("cannot write routing packet: {error}");
                    1
                }
            }
        }
        Err(error) => {
            eprintln!("{error}");
            1
        }
    }
}
