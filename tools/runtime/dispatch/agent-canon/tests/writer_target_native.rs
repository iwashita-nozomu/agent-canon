// @dependency-start
// contract test
// responsibility Compares native writer-target values and read-only packet admission with the frozen CPython oracle.
// upstream implementation ../src/writer_target.rs owns typed target and packet validation
// upstream implementation ../src/path_resolution.rs owns non-strict path resolution
// upstream implementation ../src/path_expansion.rs owns user-home expansion
// upstream evidence ../../../../../tests/fixtures/writer_target/python_golden.json freezes actual old API outcomes
// @dependency-end

use agent_canon::python_json::{
    canonical_json_ascii_bytes, parse_json, JsonArray, JsonNumber, JsonObject, JsonString,
    JsonValue,
};
use agent_canon::writer_target::{
    parse_writer_target, read_writer_target_packet, validate_writer_target_identity,
    WriterTargetError,
};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

const PYTHON_GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/writer_target/python_golden.json");
const PYTHON_GOLDEN_SHA256: &str =
    "36d5f28d07234354ae549da3ded6e0a2284ffdbefb8c322532da754c6e5a80a5";

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct TempRoot(PathBuf);

impl TempRoot {
    fn new() -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock is after epoch")
            .as_nanos();
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-writer-target-{sequence}-{nonce}-{}",
            std::process::id()
        ));
        fs::create_dir_all(path.join("real")).expect("real fixture root is created");
        create_directory_link(&path.join("real"), &path.join("alias"))
            .expect("alias points at the real fixture root");
        Self(path.canonicalize().expect("fixture root is canonical"))
    }
}

impl Drop for TempRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn writer_target_values_match_frozen_python_oracle() {
    assert_frozen_golden();
    let root = TempRoot::new();
    let corpus = parse_json(PYTHON_GOLDEN).expect("frozen corpus parses with shared JSON owner");
    let value_cases = array_field(&corpus, "value_cases");
    assert_eq!(value_cases.len(), 47, "the old value corpus has 47 cases");

    for case in value_cases {
        let name = string_field(case, "name")
            .to_text()
            .expect("case name is text");
        let operation = string_field(case, "operation")
            .to_text()
            .expect("case operation is text");
        let mut input = replace_root(
            object_field(case, "input").expect("value case has input"),
            &root.0,
        );
        if cfg!(windows) && name == "allowed_paths/6" {
            replace_absolute_allowed_path(&mut input);
        }
        let result = match operation.as_str() {
            "parse" => parse_writer_target(&input),
            "identity" => {
                let parsed = parse_writer_target(&input);
                parsed.and_then(|target| {
                    let identity = replace_root(
                        object_field(case, "identity").expect("identity case has identity"),
                        &root.0,
                    );
                    validate_writer_target_identity(&target, &identity)
                })
            }
            _ => panic!("{name}: unknown frozen operation {operation}"),
        };
        assert_value_case(case, result, &root.0, &name);
    }
}

#[test]
fn writer_target_packet_reads_match_frozen_python_oracle() {
    assert_frozen_golden();
    let root = TempRoot::new();
    let corpus = parse_json(PYTHON_GOLDEN).expect("frozen corpus parses with shared JSON owner");
    let packet_cases = array_field(&corpus, "packet_cases");
    assert_eq!(
        packet_cases.len(),
        10,
        "the old packet corpus has ten cases"
    );

    for case in packet_cases {
        let name = string_field(case, "name")
            .to_text()
            .expect("case name is text");
        let checkout_root = replace_root(
            &JsonValue::String(string_field(case, "checkout_root").clone()),
            &root.0,
        );
        let checkout_root = string_value(&checkout_root)
            .to_text()
            .expect("checkout root is Unicode text");
        let checkout_root = PathBuf::from(checkout_root);
        materialize_packet_case(case, &checkout_root, &root.0);

        match read_writer_target_packet(&checkout_root) {
            Ok((target, identity)) => {
                assert!(
                    bool_field(case, "accepted"),
                    "{name}: old API rejected the packet"
                );
                let expected_target = replace_root(
                    object_field(case, "output").expect("accepted packet has target output"),
                    &root.0,
                );
                assert_json_equal(
                    &target.as_dict().expect("normalized target projects"),
                    &expected_target,
                    &name,
                    "packet target",
                );
                let expected_identity = replace_root(
                    object_field(case, "identity").expect("accepted packet has identity"),
                    &root.0,
                );
                assert_json_equal(&identity, &expected_identity, &name, "checkout identity");
            }
            Err(error) => {
                assert!(
                    !bool_field(case, "accepted"),
                    "{name}: unexpected rejection"
                );
                assert_eq!(
                    error.code(),
                    string_field(case, "error")
                        .to_text()
                        .expect("error code is text"),
                    "{name}: stable packet rejection"
                );
            }
        }
    }
}

fn assert_frozen_golden() {
    assert_eq!(
        format!("{:x}", Sha256::digest(PYTHON_GOLDEN.as_bytes())),
        PYTHON_GOLDEN_SHA256,
        "the actual CPython corpus bytes are immutable"
    );
}

fn assert_value_case(
    case: &JsonValue,
    result: Result<agent_canon::writer_target::WriterTarget, WriterTargetError>,
    root: &Path,
    name: &str,
) {
    if bool_field(case, "accepted") {
        let target = result.unwrap_or_else(|error| panic!("{name}: rejected: {error}"));
        let expected_target = replace_root(
            object_field(case, "output").expect("accepted value has projected target"),
            root,
        );
        assert_json_equal(
            &target.as_dict().expect("normalized target projects"),
            &expected_target,
            name,
            "target projection",
        );
        let expected_environment = replace_root(
            object_field(case, "environment").expect("accepted value has environment"),
            root,
        );
        assert_json_equal(
            &environment_json(
                target
                    .environment()
                    .expect("target environment projection is valid"),
            ),
            &expected_environment,
            name,
            "environment projection",
        );
    } else {
        let error = result.expect_err("old API rejects this value");
        let expected_error = if cfg!(windows) && name == "allowed_paths/6" {
            format!(
                "writer_target:allowed_path_not_relative:{}",
                windows_absolute_allowed_path().to_string_lossy()
            )
        } else {
            string_field(case, "error")
                .to_text()
                .expect("error code is text")
        };
        assert_eq!(
            error.code(),
            expected_error,
            "{name}: stable writer-target rejection"
        );
    }
}

fn materialize_packet_case(case: &JsonValue, checkout_root: &Path, fixture_root: &Path) {
    let recipe = object_field(case, "recipe").expect("packet case has setup recipe");
    let kind = string_field(recipe, "kind")
        .to_text()
        .expect("packet recipe kind is text");
    if kind == "missing" {
        return;
    }
    if kind == "symlink-parent" {
        fs::create_dir_all(checkout_root).expect("packet checkout is created");
        create_directory_link(
            &fixture_root.join("real"),
            &checkout_root.join(".agent-canon"),
        )
        .expect("packet parent symlink is created");
        return;
    }

    let packet_path = checkout_root
        .join(".agent-canon")
        .join("writer-target.json");
    fs::create_dir_all(packet_path.parent().expect("packet file has parent"))
        .expect("packet directory is created");
    match kind.as_str() {
        "symlink-file" => {
            let outside = fixture_root.join("real").join("writer-target-outside.json");
            fs::write(&outside, b"external packet data\n").expect("outside packet is seeded");
            create_file_link(&outside, &packet_path).expect("packet file symlink is created");
        }
        "directory-file" => {
            fs::create_dir(&packet_path).expect("packet file directory is created");
        }
        "bad-json" => {
            fs::write(&packet_path, b"{not-json").expect("malformed packet is written");
        }
        _ => {
            let packet = replace_root(
                object_field(recipe, "packet").expect("packet recipe contains packet"),
                fixture_root,
            );
            let bytes = canonical_json_ascii_bytes(&packet)
                .expect("packet fixture serializes with shared JSON owner");
            fs::write(&packet_path, bytes).expect("packet fixture is written");
        }
    }
}

fn create_directory_link(target: &Path, link: &Path) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(target, link)
    }
    #[cfg(windows)]
    {
        std::os::windows::fs::symlink_dir(target, link)
    }
}

fn create_file_link(target: &Path, link: &Path) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(target, link)
    }
    #[cfg(windows)]
    {
        std::os::windows::fs::symlink_file(target, link)
    }
}

fn replace_root(value: &JsonValue, root: &Path) -> JsonValue {
    match value {
        JsonValue::Null => JsonValue::Null,
        JsonValue::Bool(value) => JsonValue::Bool(*value),
        JsonValue::Number(JsonNumber::Integer(value)) => {
            JsonValue::Number(JsonNumber::Integer(value.clone()))
        }
        JsonValue::Number(JsonNumber::Float(value)) => JsonValue::Number(JsonNumber::Float(*value)),
        JsonValue::String(value) => {
            let Some(text) = value.to_text() else {
                return JsonValue::String(value.clone());
            };
            JsonValue::String(JsonString::from_text(&replace_root_text(&text, root)))
        }
        JsonValue::Array(JsonArray(values)) => JsonValue::Array(JsonArray(
            values
                .iter()
                .map(|value| replace_root(value, root))
                .collect(),
        )),
        JsonValue::Object(JsonObject(entries)) => JsonValue::Object(JsonObject(
            entries
                .iter()
                .map(|(key, value)| (key.clone(), replace_root(value, root)))
                .collect(),
        )),
    }
}

fn replace_root_text(value: &str, root: &Path) -> String {
    let Some(suffix) = value.strip_prefix("$ROOT") else {
        return value.to_owned();
    };
    let mut relative = suffix;
    while relative.starts_with('/') || relative.starts_with('\\') {
        relative = &relative[1..];
    }
    let mut path = root.to_path_buf();
    for component in relative.split('/') {
        if !component.is_empty() {
            path.push(component);
        }
    }
    path.to_string_lossy().into_owned()
}

fn windows_absolute_allowed_path() -> PathBuf {
    std::env::temp_dir().join("agent-canon-writer-target-absolute-allowed-path")
}

fn replace_absolute_allowed_path(input: &mut JsonValue) {
    let JsonValue::Object(object) = input else {
        panic!("absolute-path fixture input is an object");
    };
    let allowed_paths = object
        .0
        .iter_mut()
        .find(|(key, _)| key.equals_text("allowed_paths"))
        .map(|(_, value)| value)
        .expect("absolute-path fixture has allowed_paths");
    let JsonValue::Array(array) = allowed_paths else {
        panic!("absolute-path fixture has an allowed_paths array");
    };
    let paths = &mut array.0;
    assert_eq!(paths.len(), 1);
    // The frozen POSIX `/absolute` premise is not a Windows absolute path.
    // Give this one case a native absolute path and keep its path-bearing error.
    paths[0] = JsonValue::String(JsonString::from_text(
        &windows_absolute_allowed_path().to_string_lossy(),
    ));
}

fn environment_json(environment: std::collections::BTreeMap<String, JsonString>) -> JsonValue {
    JsonValue::Object(JsonObject(
        environment
            .into_iter()
            .map(|(key, value)| (JsonString::from_text(&key), JsonValue::String(value)))
            .collect(),
    ))
}

fn assert_json_equal(actual: &JsonValue, expected: &JsonValue, name: &str, field: &str) {
    assert_eq!(
        canonical_json_ascii_bytes(actual).expect("actual JSON projection serializes"),
        canonical_json_ascii_bytes(expected).expect("expected JSON projection serializes"),
        "{name}: {field}"
    );
}

fn object_field<'a>(value: &'a JsonValue, key: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(JsonObject(entries)) = value else {
        return None;
    };
    entries
        .iter()
        .rev()
        .find(|(candidate, _)| candidate.equals_text(key))
        .map(|(_, value)| value)
}

fn string_field<'a>(value: &'a JsonValue, key: &str) -> &'a JsonString {
    match object_field(value, key) {
        Some(JsonValue::String(value)) => value,
        _ => panic!("frozen {key} field is text"),
    }
}

fn string_value(value: &JsonValue) -> &JsonString {
    match value {
        JsonValue::String(value) => value,
        _ => panic!("frozen value is text"),
    }
}

fn array_field<'a>(value: &'a JsonValue, key: &str) -> &'a [JsonValue] {
    match object_field(value, key) {
        Some(JsonValue::Array(JsonArray(values))) => values,
        _ => panic!("frozen {key} field is an array"),
    }
}

fn bool_field(value: &JsonValue, key: &str) -> bool {
    match object_field(value, key) {
        Some(JsonValue::Bool(value)) => *value,
        _ => panic!("frozen {key} field is boolean"),
    }
}
