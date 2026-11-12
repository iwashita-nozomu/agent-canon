#![cfg(target_os = "linux")]

// @dependency-start
// contract test
// responsibility Replays frozen Hook CLI cases and declared migration locators through the native owner.
// upstream implementation ../src/hook_dispatcher.rs owns event execution and contract readback
// upstream reference ../../../../../tests/fixtures/hook_dispatcher/python_golden.json freezes the old CLI outputs
// @dependency-end

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
        if expected_name == "mutation_control" {
            assert!(field(actual, "mutation_control").is_none());
            continue;
        }
        let value = actual_fields
            .0
            .iter()
            .rev()
            .find(|(actual_key, _)| actual_key == expected_key)
            .map(|(_, value)| value)
            .unwrap_or_else(|| panic!("{name}: missing spool field {expected_name}"));
        if expected_name == "status" && text(expected_value) == "blocked_parent_mutation" {
            assert_eq!(text(value), "pass", "ordinary writes are admitted");
            continue;
        }
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
    let expected_stdout = case_bytes(case, "stdout_base64");
    if matches!(
        text(field(case, "name").unwrap()).as_str(),
        "contract" | "contract-stop"
    ) {
        // Keep the frozen current-event oracle; retired migration metadata was removed.
        let expected_text = String::from_utf8(expected_stdout)
            .unwrap()
            .replace("raw_git_merge_or_rebase=block; ", "")
            .replace("writer_target_packet_missing=block; ", "")
            .replace("writer_target_mismatch=block; ", "");
        let expected = parse_json(&expected_text).unwrap();
        let JsonValue::Object(mut fields) = expected else {
            panic!("contract oracle must be an object");
        };
        fields.0.retain(|(key, _)| {
            !matches!(
                key.to_text().unwrap().as_str(),
                "retired_child_tombstones" | "moved_source_absences" | "counts" | "source_digest"
            )
        });
        let expected_contract = canonical_json_ascii_bytes(&JsonValue::Object(fields)).unwrap();
        assert_eq!(
            canonical_json_ascii_bytes(
                &parse_json(&String::from_utf8(result.stdout.clone()).unwrap()).unwrap()
            )
            .unwrap(),
            expected_contract,
            "current-event contract for {name}"
        );
    } else if text(field(case, "name").expect("case name")) == "touch" {
        assert!(result.stdout.is_empty(), "ordinary writes are admitted");
    } else {
        assert_eq!(result.stdout, expected_stdout, "stdout bytes for {name}");
    }
    if text(field(case, "name").expect("case name")) == "surrogate-command" {
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

#[test]
fn report_and_spool_keep_private_arguments_out_and_fail_open() {
    for marker in [
        "private-command-value".to_owned(),
        format!("ghp_{}", "A".repeat(36)),
    ] {
        for failure in ["none", "append", "report", "parent"] {
            let temp = TempDir::new();
            git_repo(temp.path());
            let source = temp.path().join("source");
            let results = temp.path().join("results");
            let report = temp.path().join("report");
            for directory in [&source, &results, &report] {
                fs::create_dir(directory).unwrap();
            }
            let mut values = environment(&source, &results);
            for name in ["AGENT_CANON_PARENT_ROOT", "AGENT_CANON_RUNTIME_ROOT"] {
                values.insert(name.to_owned(), temp.path().display().to_string());
            }
            values.insert(
                "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR".to_owned(),
                report.display().to_string(),
            );
            let monitor = report.join("workflow_monitoring.md");
            if failure == "append" {
                fs::write(results.join(".event-spool"), "existing-file").unwrap();
            } else if failure == "report" {
                fs::create_dir(&monitor).unwrap();
            } else if failure == "parent" {
                values.insert("AGENT_CANON_PARENT_ROOT".to_owned(), String::new());
            }
            let payload = serde_json::json!({"tool_name":"Bash","tool_input":{"command":format!("/usr/bin/printf '%s' {marker}")},"tool_response":{"exit_code":0,"stdout":"private-stdout","stderr":"private-stderr"},"metadata":"private-metadata-value"});
            let result = run_with_input(
                &["PostToolUse".to_owned()],
                &serde_json::to_vec(&payload).unwrap(),
                &values,
                &source,
            );
            assert_eq!(result.exit_code, 0, "{failure}: hook remains successful");
            assert!(result.stdout.is_empty());
            assert!(result.stderr.is_empty());
            let events = event_values(&results);
            assert_eq!(
                events.len(),
                usize::from(!matches!(failure, "append" | "parent")),
                "{failure}: one append outcome"
            );
            if matches!(failure, "append" | "parent") {
                assert!(!monitor.exists(), "failed append does not write a report");
                if failure == "append" {
                    assert_eq!(
                        fs::read(results.join(".event-spool")).unwrap(),
                        b"existing-file"
                    );
                }
                continue;
            }
            let event = &events[0];
            assert_eq!(text(field(event, "status").unwrap()), "invalid_projection");
            assert_eq!(text(field(event, "tool_command_verb").unwrap()), "");
            assert!(field(event, "tool_response").is_none());
            let bytes = canonical_json_ascii_bytes(event).unwrap();
            let event_text = String::from_utf8(bytes).unwrap();
            if failure == "none" {
                assert!(
                    !monitor.exists(),
                    "hooks do not create retired progress reports"
                );
            } else {
                assert!(monitor.is_dir(), "existing report path is untouched");
            }
            for private in [
                marker.as_str(),
                "private-stdout",
                "private-stderr",
                "private-metadata-value",
            ] {
                assert!(
                    !event_text.contains(private),
                    "{failure}: private event value"
                );
            }
        }
    }
}

#[test]
fn missing_runtime_directory_does_not_change_safety_or_create_files() {
    let temp = TempDir::new();
    git_repo(temp.path());
    let source = temp.path().join("source");
    fs::create_dir(&source).unwrap();
    fs::create_dir(source.join("subdir")).unwrap();
    let declared_source_runtime = source.join(".runtime");
    let source_runtime_alias = source.join("subdir/../.runtime");
    assert_eq!(
        agent_canon::runtime_boundary::RuntimeSpoolBoundary::resolve_path(
            &source,
            &declared_source_runtime,
            Path::new("spool/hook-events")
        )
        .unwrap(),
        declared_source_runtime.join("spool/hook-events")
    );
    assert!(
        agent_canon::runtime_boundary::RuntimeSpoolBoundary::resolve_path(
            &source,
            &source_runtime_alias,
            Path::new("spool/hook-events")
        )
        .is_err()
    );
    assert!(!declared_source_runtime.exists());
    let missing_runtime = temp.path().join("uncreated-runtime");
    let mut values = environment(&source, &temp.path().join("unused-results"));
    values.remove("AGENT_CANON_HOOK_RESULTS_DIR");
    values.insert(
        "AGENT_CANON_RUNTIME_ROOT".to_owned(),
        missing_runtime.display().to_string(),
    );
    values.insert("AGENT_CANON_PARENT_ROOT".to_owned(), String::new());
    for (payload, blocked) in [
        (
            br#"{"tool_name":"Bash","tool_input":{"command":"git status"}}"#.as_slice(),
            false,
        ),
        (
            br#"{"tool_name":"Bash","tool_input":{"command":"git reset --hard"}}"#.as_slice(),
            true,
        ),
    ] {
        let result = run_with_input(&["PreToolUse".to_owned()], payload, &values, &source);
        assert_eq!(
            result.exit_code,
            0,
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        assert!(result.stderr.is_empty());
        if blocked {
            let output = parse_json(std::str::from_utf8(&result.stdout).unwrap()).unwrap();
            assert_eq!(text(field(&output, "decision").unwrap()), "block");
        } else {
            assert!(result.stdout.is_empty());
        }
        assert!(
            !missing_runtime.exists(),
            "path calculation creates no runtime directory"
        );
    }
}

#[test]
fn dispatcher_admits_edits_without_runtime_work_control_records() {
    for role in ["", "parent", "implementer"] {
        for stale_records in [false, true] {
            let temp = TempDir::new();
            git_repo(temp.path());
            let source = temp.path().join("source");
            let results = source.join("hook-results");
            fs::create_dir_all(&source).unwrap();
            if stale_records {
                for path in [
                    "run/runtime/agent_identity.json",
                    ".agent-canon/writer-target.json",
                    "hook-results/.event-spool/spawn.json",
                ] {
                    let path = source.join(path);
                    fs::create_dir_all(path.parent().unwrap()).unwrap();
                    fs::write(path, b"{}").unwrap();
                }
            }
            let mut values = environment(&source, &results);
            for name in ["AGENT_CANON_PARENT_ROOT", "AGENT_CANON_RUNTIME_ROOT"] {
                values.insert(name.to_owned(), temp.path().display().to_string());
            }
            values.insert(
                "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR".to_owned(),
                source.join("run").display().to_string(),
            );
            values.insert("AGENT_CANON_RUNTIME_ROLE_ID".to_owned(), role.to_owned());
            for payload in [
                br#"{"tool_name":"apply_patch","tool_input":{"patch":"*** Begin Patch\n*** Update File: src/owned.rs\n*** End Patch\n"}}"#.as_slice(),
                br#"{"tool_name":"Write","tool_input":{"file_path":"src/new.rs","content":"pub fn answer() -> u32 { 42 }"}}"#.as_slice(),
                br#"{"tool_name":"Bash","tool_input":{"command":"touch src/a.rs"}}"#.as_slice(),
            ] {
                let result = run_with_input(&["PreToolUse".to_owned()], payload, &values, &source);
                assert_eq!(result.exit_code, 0, "{role}: {}", String::from_utf8_lossy(&result.stderr));
                assert!(result.stdout.is_empty(), "{role}: {}", String::from_utf8_lossy(&result.stdout));
                assert!(result.stderr.is_empty());
            }
            let events = event_values(&results);
            let invocations: Vec<_> = events
                .iter()
                .filter(|event| field(event, "hook_event_name").is_some())
                .collect();
            assert_eq!(invocations.len(), 3);
            for event in invocations {
                assert_eq!(text(field(event, "status").unwrap()), "pass");
                assert!(field(event, "mutation_control").is_none());
            }
        }
    }
}
