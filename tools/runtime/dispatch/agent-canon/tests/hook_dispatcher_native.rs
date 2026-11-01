#![cfg(target_os = "linux")]

use agent_canon::hook_dispatcher::{run_with_input, HookCliResult};
use agent_canon::python_json::{canonical_json_ascii_bytes, parse_json, JsonArray, JsonValue};
use base64::engine::general_purpose::STANDARD;
use base64::Engine as _;
use std::collections::BTreeMap;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT_TEMP: AtomicUsize = AtomicUsize::new(0);

struct TempDir(PathBuf);

impl TempDir {
    fn new() -> Self {
        let suffix = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-hook-dispatcher-native-{}-{suffix}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("create isolated hook fixture");
        Self(fs::canonicalize(path).expect("canonicalize hook fixture"))
    }

    fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn run_git(root: &Path, args: &[&str]) -> Output {
    Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .expect("run test fixture Git command")
}

fn git_ok(root: &Path, args: &[&str]) {
    let output = run_git(root, args);
    assert!(
        output.status.success(),
        "git {args:?}: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}

fn git_repo(root: &Path) {
    let output = Command::new("git")
        .args(["init", "-q", "-b", "main"])
        .arg(root)
        .output()
        .expect("initialize test fixture Git repository");
    assert!(
        output.status.success(),
        "git init: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    git_ok(
        root,
        &[
            "remote",
            "add",
            "origin",
            "https://example.invalid/hook-parent.git",
        ],
    );
    git_ok(
        root,
        &[
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "fixture",
        ],
    );
}

fn field<'a>(value: &'a JsonValue, name: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(object) = value else {
        return None;
    };
    object
        .0
        .iter()
        .rev()
        .find(|(key, _)| key.equals_text(name))
        .map(|(_, value)| value)
}

fn text(value: &JsonValue) -> String {
    let JsonValue::String(value) = value else {
        panic!("expected a JSON string")
    };
    value.to_text().expect("fixture string is valid Unicode")
}

fn usize_value(value: &JsonValue) -> usize {
    let JsonValue::Number(number) = value else {
        panic!("expected an integer")
    };
    match number {
        agent_canon::python_json::JsonNumber::Integer(value) => {
            value.parse().expect("fixture integer fits usize")
        }
        _ => panic!("expected an integer"),
    }
}

fn array(value: &JsonValue) -> &JsonArray {
    let JsonValue::Array(values) = value else {
        panic!("expected a JSON array")
    };
    values
}

fn case_arguments(case: &JsonValue) -> Vec<String> {
    match field(case, "args") {
        Some(JsonValue::Array(values)) => values.0.iter().map(text).collect(),
        Some(JsonValue::Null) | None => field(case, "event")
            .map(text)
            .filter(|event| !event.is_empty())
            .into_iter()
            .collect(),
        _ => panic!("fixture args is an array or null"),
    }
}

fn case_bytes(case: &JsonValue, name: &str) -> Vec<u8> {
    STANDARD
        .decode(text(field(case, name).expect("fixture Base64 field")).as_bytes())
        .expect("fixture Base64 is valid")
}

fn environment(root: &Path, results_dir: &Path) -> BTreeMap<String, String> {
    let root = root.to_str().expect("temporary path is UTF-8");
    let mut values = BTreeMap::new();
    values.insert("AGENT_CANON_HOOK_SOURCE_ROOT".to_owned(), root.to_owned());
    values.insert("AGENT_CANON_PARENT_ROOT".to_owned(), root.to_owned());
    values.insert(
        "AGENT_CANON_HOOK_RESULTS_DIR".to_owned(),
        results_dir.to_string_lossy().into_owned(),
    );
    values.insert(
        "AGENT_CANON_HOOK_RUN_NAMESPACE".to_owned(),
        "fixture".to_owned(),
    );
    values.insert(
        "AGENT_CANON_SOURCE_REPOSITORY_REMOTE".to_owned(),
        "https://example.invalid/hook-parent.git".to_owned(),
    );
    values.insert(
        "AGENT_CANON_RUNTIME_ROOT".to_owned(),
        Path::new(root)
            .join("runtime")
            .to_string_lossy()
            .into_owned(),
    );
    values
}

fn event_files(root: &Path, output: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(root) else {
        return;
    };
    for entry in entries {
        let entry = entry.expect("read hook spool directory entry");
        let path = entry.path();
        if path.is_dir() {
            event_files(&path, output);
        } else if path
            .extension()
            .is_some_and(|extension| extension == "json")
        {
            output.push(path);
        }
    }
}

fn event_values(results_dir: &Path) -> Vec<JsonValue> {
    let spool_root = results_dir.join(".event-spool");
    let mut paths = Vec::new();
    event_files(&spool_root, &mut paths);
    paths.sort();
    paths
        .iter()
        .map(|path| {
            let content = fs::read_to_string(path).expect("read native Hook event");
            parse_json(&content).expect("native Hook event is valid JSON")
        })
        .collect()
}

fn assert_spool_fields(actual: &JsonValue, expected: &JsonValue, name: &str) {
    let JsonValue::Object(expected_fields) = expected else {
        panic!("{name}: expected spool fields are an object")
    };
    let JsonValue::Object(actual_fields) = actual else {
        panic!("{name}: native spool entry is an object")
    };
    for (expected_key, expected_value) in &expected_fields.0 {
        let expected_name = expected_key.to_text().expect("field name is Unicode");
        let value = actual_fields
            .0
            .iter()
            .rev()
            .find(|(actual_key, _)| actual_key == expected_key)
            .map(|(_, value)| value)
            .unwrap_or_else(|| panic!("{name}: missing spool field {expected_name}"));
        assert_eq!(
            canonical_json_ascii_bytes(value).expect("serialize actual field"),
            canonical_json_ascii_bytes(expected_value).expect("serialize old oracle field"),
            "spool field {expected_name} for {name}"
        );
    }
}

fn assert_case_result(result: HookCliResult, case: &JsonValue, name: &str) {
    assert_eq!(
        result.exit_code,
        usize_value(field(case, "exit").expect("expected exit")) as i32,
        "exit status for {name}"
    );
    assert_eq!(
        result.stdout,
        case_bytes(case, "stdout_base64"),
        "stdout bytes for {name}"
    );
    if name == "surrogate-command" {
        assert!(
            !result.stderr.is_empty(),
            "unencodable command is refused with a native diagnostic"
        );
        assert!(
            !String::from_utf8_lossy(&result.stderr).contains("Traceback"),
            "native diagnostic does not recreate a CPython traceback"
        );
    } else {
        assert_eq!(
            result.stderr,
            text(field(case, "stderr_observed").expect("old stderr bytes")).into_bytes(),
            "stderr for {name}"
        );
    }
}

#[test]
fn native_hook_cli_matches_frozen_cpython_cases() {
    let golden = parse_json(include_str!(
        "../../../../../tests/fixtures/hook_dispatcher/python_golden.json"
    ))
    .expect("parse frozen Python Hook CLI corpus");
    assert_eq!(
        text(field(&golden, "python").expect("captured Python version")),
        "3.12.3"
    );
    assert_eq!(
        text(field(&golden, "source_hash").expect("captured Python source hash")),
        "5551d2946264cb0179655ba908832ac33f2016169015c0fca3c02d7cdd6b5995"
    );
    let cases = array(field(&golden, "cases").expect("captured CLI cases"));
    assert_eq!(cases.0.len(), 33);

    let temp = TempDir::new();
    git_repo(temp.path());
    for case in &cases.0 {
        let name = text(field(case, "name").expect("case name"));
        let input = case_bytes(case, "input_base64");
        let arguments = case_arguments(case);
        let results_dir = temp.path().join("results").join(&name);
        fs::create_dir_all(&results_dir).expect("create isolated hook result directory");
        let values = environment(temp.path(), &results_dir);

        let result = run_with_input(&arguments, &input, &values, temp.path());
        assert_case_result(result, case, &name);

        let events = event_values(&results_dir);
        assert_eq!(
            events.len(),
            usize_value(field(case, "spool_event_count").expect("old spool count")),
            "spool event count for {name}"
        );
        let expected_fields = array(field(case, "spool_fields").expect("old selected fields"));
        assert_eq!(
            events.len(),
            expected_fields.0.len(),
            "spool field cases for {name}"
        );
        for (actual, expected) in events.iter().zip(&expected_fields.0) {
            assert_spool_fields(actual, expected, &name);
        }

        let cli_results_dir = temp.path().join("cli-results").join(&name);
        fs::create_dir_all(&cli_results_dir).expect("create isolated CLI result directory");
        let cli_environment = environment(temp.path(), &cli_results_dir);
        let mut command = Command::new(env!("CARGO_BIN_EXE_agent-canon"));
        command
            .arg("codex-hook")
            .args(&arguments)
            .current_dir(temp.path())
            .env_clear()
            .envs(&cli_environment)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if let Some(path) = std::env::var_os("PATH") {
            command.env("PATH", path);
        }
        let mut child = command.spawn().expect("start native hook CLI");
        child
            .stdin
            .take()
            .expect("native hook CLI stdin")
            .write_all(&input)
            .expect("supply captured hook input");
        let output = child
            .wait_with_output()
            .expect("read native hook CLI output");
        assert_case_result(
            HookCliResult {
                exit_code: output.status.code().expect("native hook CLI exit code"),
                stdout: output.stdout,
                stderr: output.stderr,
            },
            case,
            &format!("CLI {name}"),
        );
        let cli_events = event_values(&cli_results_dir);
        assert_eq!(
            cli_events.len(),
            expected_fields.0.len(),
            "CLI spool event count for {name}"
        );
        for (actual, expected) in cli_events.iter().zip(&expected_fields.0) {
            assert_spool_fields(actual, expected, &format!("CLI {name}"));
        }
    }
}
