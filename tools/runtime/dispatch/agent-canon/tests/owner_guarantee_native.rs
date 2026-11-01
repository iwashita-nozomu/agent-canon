// @dependency-start
// contract test
// responsibility Verifies native owner-guarantee packet APIs and closeout projection against frozen CPython outputs.
// upstream implementation ../src/owner_guarantee.rs owns native packet and projection behavior.
// upstream implementation ../src/python_json.rs owns Python-compatible code-point strings and canonical ASCII bytes.
// upstream test ../../../../../tests/fixtures/owner_guarantee/python_golden.json freezes actual CPython 3.12.3 outputs and errors.
// @dependency-end

use agent_canon::owner_guarantee::{
    normalize_owner_guarantee_packet, normalize_owner_invalidation_packet,
    owner_receipt_closeout_state, owner_receipt_is_compatible, owner_receipt_is_invalidated,
    owner_receipt_key, OwnerGuaranteeError, OwnerReceiptCloseoutInput, OwnerReceiptCompatibility,
};
use agent_canon::python_json::{
    canonical_json_ascii_bytes, parse_json, JsonArray, JsonObject, JsonString, JsonValue,
};
use sha2::{Digest, Sha256};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/owner_guarantee/python_golden.json");
const GOLDEN_SHA256: &str = "8f1e3334c7e68805187c0772ce328dd8dc75eef08d7c0ee09c8b75f7403c912b";
const OWNER_SOURCE_SHA256: &str =
    "cf7613c0345756f7879df525ebb4bc079f72c99ae9e737ba0db81071ec0d41fe";

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn object_field<'a>(value: &'a JsonValue, field: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(object) = value else {
        return None;
    };
    object
        .0
        .iter()
        .rev()
        .find_map(|(key, value)| key.equals_text(field).then_some(value))
}

fn array(value: &JsonValue) -> Option<&[JsonValue]> {
    match value {
        JsonValue::Array(array) => Some(&array.0),
        _ => None,
    }
}

fn string(value: &JsonValue) -> Option<&JsonString> {
    match value {
        JsonValue::String(string) => Some(string),
        _ => None,
    }
}

fn object_string<'a>(value: &'a JsonValue, field: &str) -> Option<&'a JsonString> {
    object_field(value, field).and_then(string)
}

fn option_string<'a>(value: &'a JsonValue, field: &str) -> Option<&'a JsonString> {
    object_string(value, field)
}

fn optional_text_list(value: &JsonValue, field: &str) -> Vec<JsonString> {
    let Some(values) = object_field(value, field) else {
        return Vec::new();
    };
    array(values)
        .expect("frozen optional text list is an array")
        .iter()
        .map(|value| {
            string(value)
                .expect("frozen optional text list has strings")
                .clone()
        })
        .collect()
}

fn output_object(fields: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(JsonObject(
        fields
            .into_iter()
            .map(|(key, value)| (JsonString::from_text(key), value))
            .collect(),
    ))
}

fn invoke(case: &JsonValue) -> Result<JsonValue, OwnerGuaranteeError> {
    let operation = object_string(case, "operation")
        .and_then(JsonString::to_text)
        .expect("frozen API operation is text");
    let args = array(object_field(case, "args").expect("frozen args exist"))
        .expect("frozen args are an array");
    let kwargs = object_field(case, "kwargs").expect("frozen kwargs exist");
    match operation.as_str() {
        "normalize_owner_guarantee_packet" => {
            normalize_owner_guarantee_packet(&args[0], option_string(kwargs, "field_prefix"))
        }
        "owner_receipt_key" => {
            let key = owner_receipt_key(&args[0])?;
            Ok(JsonValue::Array(JsonArray(
                key.into_iter().map(JsonValue::String).collect(),
            )))
        }
        "owner_receipt_is_compatible" => Ok(JsonValue::Bool(owner_receipt_is_compatible(
            &args[0],
            &OwnerReceiptCompatibility {
                candidate_digest: option_string(kwargs, "candidate_digest"),
                property_ref: option_string(kwargs, "property_ref"),
                owner_ref: option_string(kwargs, "owner_ref"),
                execution_plane: option_string(kwargs, "execution_plane"),
                tool_input_locator: option_string(kwargs, "tool_input_locator"),
                mechanism_ref: option_string(kwargs, "mechanism_ref"),
            },
        )?)),
        "normalize_owner_invalidation_packet" => {
            normalize_owner_invalidation_packet(&args[0], option_string(kwargs, "field_prefix"))
        }
        "owner_receipt_is_invalidated" => Ok(JsonValue::Bool(owner_receipt_is_invalidated(
            &args[0], &args[1],
        )?)),
        "owner_receipt_closeout_state" => {
            let receipts = array(&args[0]).expect("frozen owner receipts are an array");
            let required_owner_refs = optional_text_list(kwargs, "required_owner_refs");
            let dependency_edges = optional_text_list(kwargs, "dependency_edges");
            let decision = owner_receipt_closeout_state(&OwnerReceiptCloseoutInput {
                owner_receipts: receipts,
                candidate_digest: option_string(kwargs, "candidate_digest"),
                required_owner_refs: &required_owner_refs,
                dependency_edges: &dependency_edges,
            })?;
            Ok(output_object(vec![
                ("ready", JsonValue::Bool(decision.ready)),
                (
                    "reasons",
                    JsonValue::Array(JsonArray(
                        decision
                            .reasons
                            .into_iter()
                            .map(JsonValue::String)
                            .collect(),
                    )),
                ),
            ]))
        }
        other => panic!("unmapped frozen owner-guarantee API {other}"),
    }
}

#[test]
fn owner_guarantee_apis_match_frozen_cpython_results_errors_bytes_and_hashes() {
    assert_eq!(sha256_hex(GOLDEN.as_bytes()), GOLDEN_SHA256);
    let golden = parse_json(GOLDEN).expect("frozen CPython owner-guarantee golden parses");
    assert_eq!(
        object_string(&golden, "source_sha256")
            .and_then(JsonString::to_text)
            .as_deref(),
        Some(OWNER_SOURCE_SHA256)
    );
    let cases = array(object_field(&golden, "cases").expect("frozen cases exist"))
        .expect("frozen cases are an array");
    assert_eq!(cases.len(), 67);

    for case in cases {
        let name = object_string(case, "name")
            .and_then(JsonString::to_text)
            .expect("frozen case name is text");
        let outcome = object_field(case, "outcome").expect("frozen outcome exists");
        let status = object_string(outcome, "status").expect("frozen outcome status is text");
        match invoke(case) {
            Ok(actual) => {
                assert!(status.equals_text("ok"), "{name} unexpectedly succeeded");
                let bytes = canonical_json_ascii_bytes(&actual)
                    .expect("frozen owner result has canonical Python ASCII bytes");
                let expected_bytes = canonical_json_ascii_bytes(
                    object_field(outcome, "result").expect("accepted outcome has a result"),
                )
                .expect("frozen expected result has canonical Python ASCII bytes");
                assert_eq!(bytes, expected_bytes, "full result for {name}");
                assert_eq!(
                    sha256_hex(&bytes),
                    object_string(outcome, "canonical_ascii_sha256")
                        .and_then(JsonString::to_text)
                        .expect("accepted case freezes its SHA-256"),
                    "canonical digest for {name}"
                );
                assert_eq!(
                    bytes_to_hex(&bytes),
                    object_string(outcome, "canonical_ascii_hex")
                        .and_then(JsonString::to_text)
                        .expect("accepted case freezes canonical bytes"),
                    "canonical bytes for {name}"
                );
            }
            Err(actual) => {
                assert!(status.equals_text("error"), "{name} unexpectedly failed");
                assert_eq!(
                    object_string(outcome, "class")
                        .and_then(JsonString::to_text)
                        .as_deref(),
                    Some("RuntimeError"),
                    "exception class for {name}"
                );
                assert_eq!(
                    &actual.message,
                    object_string(outcome, "message").expect("frozen error message is text"),
                    "error message for {name}"
                );
            }
        }
    }
}

fn bytes_to_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}
