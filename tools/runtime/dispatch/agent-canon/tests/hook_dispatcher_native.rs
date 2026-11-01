#![cfg(target_os = "linux")]

use agent_canon::hook_dispatcher::{run_with_input, HookCliResult};
use agent_canon::python_json::{canonical_json_ascii_bytes, parse_json, JsonArray, JsonValue};
use base64::engine::general_purpose::STANDARD;
use base64::Engine as _;
use sha2::{Digest, Sha256};
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
fn report_selection_preserves_precedence_and_pointer_containment() {
    for kind in [
        "explicit",
        "pointer",
        "local-pointer",
        "container-target",
        "missing",
        "parent-escape",
        "absolute-escape",
        "target-symlink",
        "report-root-symlink",
    ] {
        let temp = TempDir::new();
        git_repo(temp.path());
        let source = temp.path().join("source");
        let results = temp.path().join("results");
        let report_root = source.join("reports/agents");
        let target = report_root.join("selected-run");
        let outside = temp.path().join("outside");
        fs::create_dir_all(&target).expect("create existing run target");
        fs::create_dir_all(&results).expect("create event results directory");
        fs::create_dir_all(&outside).expect("create outside directory");
        let mut values = environment(&source, &results);
        values.insert(
            "AGENT_CANON_PARENT_ROOT".to_owned(),
            temp.path().display().to_string(),
        );
        values.insert(
            "AGENT_CANON_RUNTIME_ROOT".to_owned(),
            temp.path().display().to_string(),
        );
        let mut selected = None;
        match kind {
            "explicit" => {
                fs::write(report_root.join(".active_run"), "selected-run\n").unwrap();
                values.insert(
                    "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR".to_owned(),
                    outside.display().to_string(),
                );
                selected = Some(outside.clone());
            }
            "pointer" | "container-target" => {
                fs::write(report_root.join(".active_run"), "selected-run\n").unwrap();
                selected = Some(target.clone());
                if kind == "container-target" {
                    values.remove("AGENT_CANON_HOOK_SOURCE_ROOT");
                    values.insert(
                        "AGENT_CANON_TARGET_CONTAINER_ROOT".to_owned(),
                        source.display().to_string(),
                    );
                }
            }
            "local-pointer" => {
                fs::write(source.join(".active_run"), "reports/agents/selected-run\n").unwrap();
                selected = Some(target.clone());
            }
            "missing" => fs::write(report_root.join(".active_run"), "missing-run\n").unwrap(),
            "parent-escape" => fs::write(report_root.join(".active_run"), "../escape\n").unwrap(),
            "absolute-escape" => fs::write(
                report_root.join(".active_run"),
                outside.display().to_string(),
            )
            .unwrap(),
            "target-symlink" => {
                std::os::unix::fs::symlink(&outside, report_root.join("escape")).unwrap();
                fs::write(report_root.join(".active_run"), "escape\n").unwrap();
            }
            "report-root-symlink" => {
                fs::remove_dir(&target).unwrap();
                fs::remove_dir(&report_root).unwrap();
                std::os::unix::fs::symlink(&outside, &report_root).unwrap();
                fs::create_dir(outside.join("selected-run")).unwrap();
                fs::write(outside.join(".active_run"), "selected-run\n").unwrap();
            }
            _ => unreachable!(),
        }
        let result = run_with_input(
            &["UserPromptSubmit".to_owned()],
            br#"{"prompt":"use $task-routing"}"#,
            &values,
            &source,
        );
        assert_eq!(
            result.exit_code,
            0,
            "{kind}: {}",
            String::from_utf8_lossy(&result.stderr)
        );
        assert!(result.stdout.is_empty(), "{kind}: no prompt output");
        let events = event_values(&results);
        assert_eq!(events.len(), 1, "{kind}: one event");
        assert_eq!(
            text(field(&events[0], "root").unwrap()),
            source.display().to_string(),
            "{kind}: event uses selected repository root"
        );
        let expected = selected
            .as_ref()
            .map(|path| path.display().to_string())
            .unwrap_or_default();
        assert_eq!(
            text(field(&events[0], "workflow_monitor_report_dir").unwrap()),
            expected,
            "{kind}: report selection"
        );
        if let Some(selected) = selected {
            assert!(
                selected.join("workflow_monitoring.md").is_file(),
                "{kind}: selected report is written"
            );
        } else {
            assert!(
                !target.join("workflow_monitoring.md").exists(),
                "{kind}: target report absent"
            );
            assert!(
                !outside.join("workflow_monitoring.md").exists(),
                "{kind}: outside report absent"
            );
        }
    }
}

#[test]
fn report_and_spool_keep_private_arguments_out_and_fail_open() {
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
        let result = run_with_input(&["PostToolUse".to_owned()], br#"{"tool_name":"Bash","tool_input":{"command":"/usr/bin/printf '%s' private-command-value"},"tool_response":{"exit_code":0,"stdout":"private-stdout","stderr":"private-stderr"},"metadata":"private-metadata-value"}"#, &values, &source);
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
        let report_text = if failure == "none" {
            fs::read_to_string(&monitor).expect("successful append writes report")
        } else {
            assert!(
                monitor.is_dir(),
                "failed report preserves existing directory"
            );
            String::new()
        };
        for private in [
            "private-command-value",
            "private-stdout",
            "private-stderr",
            "private-metadata-value",
        ] {
            assert!(
                !event_text.contains(private),
                "{failure}: private event value"
            );
            assert!(
                !report_text.contains(private),
                "{failure}: private report value"
            );
        }
        if failure == "none" {
            assert_eq!(report_text.matches("behavior_event_json=").count(), 1);
            let line = report_text
                .lines()
                .find_map(|line| line.trim().strip_prefix("behavior_event_json="))
                .expect("one behavior projection");
            let projected = parse_json(line).unwrap();
            let JsonValue::Object(fields) = &projected else {
                panic!("projected event is an object");
            };
            for (name, expected) in &fields.0 {
                let name = name.to_text().unwrap();
                assert_eq!(
                    canonical_json_ascii_bytes(
                        field(event, &name).expect("projection field belongs to spooled event")
                    )
                    .unwrap(),
                    canonical_json_ascii_bytes(expected).unwrap(),
                    "monitor and spool agree on {name}"
                );
            }
        }
    }
}

#[test]
fn dispatcher_preserves_parent_denial_and_authenticated_child_admission() {
    for role in ["parent", "implementer"] {
        let temp = TempDir::new();
        git_repo(temp.path());
        let source = temp.path().join("source");
        let results = source.join("hook-results");
        let report = source.join("run");
        fs::create_dir_all(report.join("runtime")).unwrap();
        fs::create_dir_all(results.join(".event-spool")).unwrap();
        let scope_digest = format!(
            "{:x}",
            Sha256::digest(br#"{"allowed_directories":[],"allowed_files":["src/owned.py"]}"#)
        );
        let mut receipt = serde_json::json!({
            "schema": "agent-canon.runtime-agent-identity.v1",
            "run_id": "hook-run", "agent_id": "child-hook", "role_id": role,
            "parent_agent_id": "parent-hook", "authority": "write_capable_child",
            "allowed_files": ["src/owned.py"], "allowed_directories": [],
            "scope_digest": scope_digest, "status": "active"
        });
        let receipt_hash = format!(
            "{:x}",
            Sha256::digest(serde_json::to_vec(&receipt).unwrap())
        );
        receipt["receipt_sha256"] = serde_json::Value::String(receipt_hash);
        fs::write(
            report.join("runtime/agent_identity.json"),
            serde_json::to_vec(&receipt).unwrap(),
        )
        .unwrap();
        let packet = serde_json::json!({
            "schema": "agent-canon.writer-target-packet.v1",
            "checkout_root": source, "branch": "test", "remote": "local/repo",
            "allowed_paths": ["src/"],
            "checkout_identity": {"cwd": source, "git_root": source, "branch": "test", "head": "a".repeat(40), "remote": "local/repo"}
        });
        fs::create_dir(source.join(".agent-canon")).unwrap();
        fs::write(
            source.join(".agent-canon/writer-target.json"),
            serde_json::to_vec(&packet).unwrap(),
        )
        .unwrap();
        let spawn = serde_json::json!({"subagent_event_kind":"spawn", "subagent_target":"child-hook", "subagent_agent_type":"worker", "mutation_scope_digest":scope_digest});
        fs::write(
            results.join(".event-spool/spawn.json"),
            serde_json::to_vec(&spawn).unwrap(),
        )
        .unwrap();
        let mut values = environment(&source, &results);
        for name in ["AGENT_CANON_PARENT_ROOT", "AGENT_CANON_RUNTIME_ROOT"] {
            values.insert(name.to_owned(), temp.path().display().to_string());
        }
        values.insert(
            "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR".to_owned(),
            report.display().to_string(),
        );
        values.insert(
            "AGENT_CANON_RUNTIME_AGENT_ID".to_owned(),
            "child-hook".to_owned(),
        );
        values.insert("AGENT_CANON_RUNTIME_ROLE_ID".to_owned(), role.to_owned());
        values.insert(
            "AGENT_CANON_RUNTIME_PARENT_AGENT_ID".to_owned(),
            "parent-hook".to_owned(),
        );
        let result = run_with_input(&["PreToolUse".to_owned()], br#"{"hookEventName":"PreToolUse","tool_name":"apply_patch","tool_input":{"patch":"*** Begin Patch\n*** Update File: src/owned.py\n*** End Patch\n"}}"#, &values, &source);
        assert_eq!(
            result.exit_code,
            0,
            "{role}: {}",
            String::from_utf8_lossy(&result.stderr)
        );
        if role == "parent" {
            let output = parse_json(std::str::from_utf8(&result.stdout).unwrap()).unwrap();
            assert_eq!(text(field(&output, "decision").unwrap()), "block");
            assert_eq!(
                text(field(&output, "mutation_authority").unwrap()),
                "parent_mutation_forbidden"
            );
        } else {
            assert!(result.stdout.is_empty(), "authenticated child is admitted");
            let events = event_values(&results);
            let event = events
                .iter()
                .find(|event| field(event, "hook_event_name").is_some())
                .unwrap();
            let control = field(event, "mutation_control").unwrap();
            assert_eq!(text(field(control, "status").unwrap()), "allowed");
            assert_eq!(text(field(control, "role_id").unwrap()), "implementer");
        }
    }
}
