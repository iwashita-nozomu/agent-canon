// @dependency-start
// contract test
// responsibility Compares native PreToolUse mutation decisions and block payloads with independently captured CPython outputs.
// upstream implementation ../src/mutation_authority.rs owns mutation classification and authority decisions
// upstream implementation ../src/writer_target.rs owns the static writer-target packet boundary
// upstream implementation ../src/python_json.rs owns the shared JSON representation and canonical receipt bytes
// upstream evidence ../../../../../tests/fixtures/mutation_authority/python_golden.json freezes 31 old basic API cases
// upstream evidence ../../../../../tests/fixtures/mutation_authority/git_python_golden.json freezes 16 old real-Git cases
// upstream evidence ../../../../../tests/fixtures/mutation_authority/parser/python_golden.json freezes 15 old parser boundary cases
// @dependency-end

use agent_canon::mutation_authority::{
    evaluate_mutation_authority, mutation_block_payload, MutationAuthorityContext,
};
use agent_canon::python_json::{canonical_json_ascii_bytes, parse_json};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

const BASIC_GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/mutation_authority/python_golden.json");
const GIT_GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/mutation_authority/git_python_golden.json");
const PARSER_GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/mutation_authority/parser/python_golden.json");
const BASIC_SHA256: &str = "7861606800e965d30c385eda6d295de6df68f3bec0debee98ee3d8a206c447c7";
const GIT_SHA256: &str = "f6c2833a38629e37978605fc33b1e2dcd70502185a5c177d325f5ee3f107f8c6";
const PARSER_SHA256: &str = "8c9310487272ebb884d9f2899cc0e42c1dadea21ad44019d829d3f2e9d73173c";

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
            "agent-canon-mutation-authority-{}-{sequence}-{nonce}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("temporary checkout is created");
        Self(
            path.canonicalize()
                .expect("temporary checkout is canonical"),
        )
    }
}

impl Drop for TempRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn mutation_authority_matches_frozen_basic_cpython_cases() {
    assert_eq!(sha256(BASIC_GOLDEN.as_bytes()), BASIC_SHA256);
    let corpus: Value = serde_json::from_str(BASIC_GOLDEN).expect("basic corpus parses");
    let cases = corpus["cases"]
        .as_array()
        .expect("basic cases are an array");
    assert_eq!(cases.len(), 31);
    for case in cases {
        verify_case(case, false);
    }
}

#[test]
fn mutation_authority_matches_frozen_real_git_cpython_cases() {
    assert_eq!(sha256(GIT_GOLDEN.as_bytes()), GIT_SHA256);
    let corpus: Value = serde_json::from_str(GIT_GOLDEN).expect("Git corpus parses");
    let cases = corpus["cases"].as_array().expect("Git cases are an array");
    assert_eq!(cases.len(), 16);
    for case in cases {
        verify_case(case, true);
    }
}

#[test]
fn mutation_authority_matches_frozen_parser_boundary_cases() {
    assert_eq!(sha256(PARSER_GOLDEN.as_bytes()), PARSER_SHA256);
    let corpus: Value = serde_json::from_str(PARSER_GOLDEN).expect("parser corpus parses");
    let cases = corpus["cases"]
        .as_array()
        .expect("parser cases are an array");
    assert_eq!(cases.len(), 15);
    for case in cases {
        verify_case(case, false);
    }
}

fn verify_case(case: &Value, has_git_recipe: bool) {
    let name = case["name"].as_str().expect("case name is text");
    let root = TempRoot::new();
    if has_git_recipe {
        materialize_git_recipe(&root.0, case);
        apply_git_actions(&root.0, case);
    }
    materialize_json_files(&root.0, &case["json_files"]);

    let payload = replace_fixture_roots(case.get("payload").unwrap_or(&Value::Null), &root.0);
    let payload_text = serde_json::to_string(&payload).expect("payload serializes");
    let payload = parse_json(&payload_text).expect("payload parses with the product JSON owner");

    let environment = case["environment"]
        .as_object()
        .expect("case environment is a mapping")
        .iter()
        .map(|(key, value)| {
            let value = value.as_str().expect("environment values are strings");
            (key.clone(), replace_text(value, &root.0))
        })
        .collect::<BTreeMap<_, _>>();
    let report_dir = optional_fixture_path(case.get("report_dir"), &root.0, true);
    let hook_spool_root = optional_fixture_path(case.get("hook_spool_root"), &root.0, true);
    let decision = evaluate_mutation_authority(
        &payload,
        &MutationAuthorityContext {
            report_dir: report_dir.as_deref(),
            active_root: &root.0,
            environment: &environment,
            hook_spool_root: hook_spool_root.as_deref(),
        },
    );
    let actual_decision = normalize_product_roots(decision.as_dict(), &root.0);
    let mut expected_decision = case.get("decision").expect("case freezes decision").clone();
    if cfg!(windows) {
        let reference = expected_decision["evidence_ref"]
            .as_str()
            .unwrap_or_default();
        if reference.starts_with("$ROOT/") || reference.starts_with("$ROOT_PARENT/") {
            expected_decision["evidence_ref"] = Value::String(reference.replace('/', "\\"));
        }
    }
    assert_eq!(
        actual_decision, expected_decision,
        "{name}: complete decision projection"
    );

    if !case["block_payload"].is_null() {
        let actual = normalize_product_roots(mutation_block_payload(&decision), &root.0);
        assert_eq!(
            actual, case["block_payload"],
            "{name}: sanitized block payload"
        );
    }
}

fn materialize_json_files(root: &Path, files: &Value) {
    let files = files.as_object().expect("fixture JSON files are a mapping");
    for (relative, contents) in files {
        let path = root.join(relative);
        fs::create_dir_all(path.parent().expect("JSON fixture has a parent"))
            .expect("JSON fixture parent is created");
        let contents = replace_fixture_roots(contents, root);
        let bytes = serde_json::to_vec(&contents).expect("JSON fixture serializes");
        fs::write(path, bytes).expect("fixture JSON file is written");
    }
}

fn materialize_git_recipe(root: &Path, case: &Value) {
    let recipe = case["git_recipe"]
        .as_str()
        .expect("Git case has a setup recipe");
    assert!(recipe.starts_with("helpers.init_writer_git_repo:"));
    run_git_setup(root, &["init", "--quiet", "--initial-branch=fix/942"]);
    run_git_setup(root, &["config", "user.name", "Test"]);
    run_git_setup(root, &["config", "user.email", "test@example.invalid"]);
    fs::create_dir_all(root.join("src")).expect("source directory is created");
    fs::write(root.join("src/owned.py"), b"base\n").expect("owned source is written");
    fs::write(root.join("README.md"), b"base readme\n").expect("readme is written");
    run_git_setup(root, &["add", "README.md", "src/owned.py"]);
    run_git_setup(
        root,
        &[
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "base",
        ],
    );
}

fn apply_git_actions(root: &Path, case: &Value) {
    let actions = case["actions"]
        .as_array()
        .expect("Git actions are an array");
    for action in actions {
        let action = action.as_array().expect("Git action is a sequence");
        let kind = action
            .first()
            .and_then(Value::as_str)
            .expect("action kind is text");
        match kind {
            "write" => {
                let relative = action[1].as_str().expect("write path is text");
                let contents = action[2].as_str().expect("write contents are text");
                let path = root.join(relative);
                fs::create_dir_all(path.parent().expect("write action has a parent"))
                    .expect("write action parent is created");
                fs::write(path, contents.as_bytes()).expect("write action is applied");
            }
            "git" => {
                let args = action[1..]
                    .iter()
                    .map(|argument| argument.as_str().expect("Git argument is text"))
                    .collect::<Vec<_>>();
                run_git_setup(root, &args);
            }
            _ => panic!("unknown Git fixture action {kind}"),
        }
    }
}

fn run_git_setup(root: &Path, args: &[&str]) {
    let output = Command::new("git")
        .args(args)
        .current_dir(root)
        .output()
        .expect("Git setup command starts");
    assert!(
        output.status.success(),
        "Git setup command {args:?} failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}

fn optional_fixture_path(
    value: Option<&Value>,
    root: &Path,
    default_root: bool,
) -> Option<PathBuf> {
    match value {
        None if default_root => Some(root.to_path_buf()),
        None | Some(Value::Null) => None,
        Some(Value::String(value)) => Some(PathBuf::from(replace_text(value, root))),
        Some(_) => panic!("fixture path is a string or null"),
    }
}

fn replace_fixture_roots(value: &Value, root: &Path) -> Value {
    match value {
        Value::String(value) => Value::String(replace_text(value, root)),
        Value::Array(values) => Value::Array(
            values
                .iter()
                .map(|value| replace_fixture_roots(value, root))
                .collect(),
        ),
        Value::Object(values) => Value::Object(
            values
                .iter()
                .map(|(key, value)| (key.clone(), replace_fixture_roots(value, root)))
                .collect::<Map<_, _>>(),
        ),
        value => value.clone(),
    }
}

fn replace_text(value: &str, root: &Path) -> String {
    let parent = root.parent().unwrap_or(root).to_string_lossy().into_owned();
    let root = root.to_string_lossy().into_owned();
    value
        .replace("$ROOT_PARENT", &parent)
        .replace("$ROOT", &root)
}

fn normalize_product_roots(value: agent_canon::python_json::JsonValue, root: &Path) -> Value {
    let bytes =
        canonical_json_ascii_bytes(&value).expect("product projection has canonical JSON bytes");
    let mut value: Value = serde_json::from_slice(&bytes).expect("product projection is JSON");
    normalize_value_roots(&mut value, root);
    value
}

fn normalize_value_roots(value: &mut Value, root: &Path) {
    match value {
        Value::String(text) => {
            let normalized = normalize_path_prefix(text, root, "$ROOT").unwrap_or_else(|| {
                normalize_path_prefix(text, root.parent().unwrap_or(root), "$ROOT_PARENT")
                    .unwrap_or_else(|| text.clone())
            });
            *text = normalized;
        }
        Value::Array(values) => values
            .iter_mut()
            .for_each(|value| normalize_value_roots(value, root)),
        Value::Object(values) => values
            .values_mut()
            .for_each(|value| normalize_value_roots(value, root)),
        _ => {}
    }
}

fn normalize_path_prefix(value: &str, path: &Path, token: &str) -> Option<String> {
    let prefix = path.to_string_lossy();
    if value == prefix.as_ref() {
        return Some(token.to_owned());
    }
    let suffix = value.strip_prefix(prefix.as_ref())?;
    if !suffix.starts_with('/') && !suffix.starts_with('\\') {
        return None;
    }
    Some(format!("{token}{suffix}"))
}

fn sha256(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
