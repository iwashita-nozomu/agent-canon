// @dependency-start
// contract test
// responsibility Preserves generated artifact classification and CLI output against the frozen old Python oracle.
// upstream implementation ../src/report_artifact_checks.rs owns native generated artifact scanning and rendering
// upstream design ../../../../../documents/design/request-intent-and-update-relation.md generated artifact guard contract
// upstream test ../../../../../tests/fixtures/generated_artifact_guard/python_golden.json stores old CLI output and fixture declarations
// @dependency-end

use serde_json::Value;
use std::ffi::OsString;
use std::fs;
use std::os::unix::ffi::OsStringExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

const PYTHON_ORACLE: &str =
    include_str!("../../../../../tests/fixtures/generated_artifact_guard/python_golden.json");

static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(0);

struct Fixture(PathBuf);

impl Fixture {
    fn new(name: &str) -> Self {
        let sequence = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!(
            "agent-canon-generated-artifact-guard-{name}-{}-{sequence}",
            std::process::id()
        ));
        fs::create_dir_all(&root).expect("create generated artifact fixture root");
        Self(fs::canonicalize(root).expect("resolve generated artifact fixture root"))
    }

    fn root(&self) -> &Path {
        &self.0
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn decode_hex(value: &str) -> Vec<u8> {
    let digits = value.as_bytes().chunks_exact(2);
    assert!(
        digits.remainder().is_empty(),
        "hex fixture has paired digits"
    );
    digits
        .map(|digits| {
            let digit = |byte: u8| match byte {
                b'0'..=b'9' => byte - b'0',
                b'a'..=b'f' => byte - b'a' + 10,
                b'A'..=b'F' => byte - b'A' + 10,
                _ => panic!("fixture contains a non-hex digit"),
            };
            digit(digits[0]) * 16 + digit(digits[1])
        })
        .collect()
}

fn path_from_bytes(path: &[u8]) -> PathBuf {
    PathBuf::from(OsString::from_vec(path.to_vec()))
}

fn git(root: &Path, args: &[&str]) -> Output {
    Command::new("git")
        .args(args)
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env("GIT_CONFIG_GLOBAL", "/dev/null")
        .current_dir(root)
        .output()
        .expect("Git fixture command runs")
}

fn initialize_repository(root: &Path) {
    assert!(git(root, &["init", "-q"]).status.success());
}

fn write_ignore_patterns(root: &Path, patterns: &[Value]) {
    if patterns.is_empty() {
        return;
    }
    let mut contents = Vec::new();
    for pattern in patterns {
        contents.extend(decode_hex(
            pattern.as_str().expect("ignore pattern is encoded as hex"),
        ));
    }
    fs::write(root.join(".gitignore"), contents).expect("write Git ignore fixture");
}

fn prepare_fixture(case: &Value, root: &Path) {
    if case["name"] != "plain-non-git-root" {
        initialize_repository(root);
    }
    write_ignore_patterns(
        root,
        case["ignore_patterns_hex"]
            .as_array()
            .expect("ignore patterns are a list"),
    );
    for fixture_file in case["fixture_files"]
        .as_array()
        .expect("fixture files are a list")
    {
        let path_bytes = decode_hex(
            fixture_file["path_bytes_hex"]
                .as_str()
                .expect("path is encoded as hex"),
        );
        let path = root.join(path_from_bytes(&path_bytes));
        fs::create_dir_all(path.parent().expect("fixture file has a parent"))
            .expect("create generated artifact parent");
        fs::write(&path, b"generated artifact fixture\n")
            .expect("write generated artifact fixture");
        if fixture_file["declared_state"] == "tracked" {
            let output = Command::new("git")
                .args(["add", "-f", "--"])
                .arg(path_from_bytes(&path_bytes))
                .env("GIT_CONFIG_NOSYSTEM", "1")
                .env("GIT_CONFIG_GLOBAL", "/dev/null")
                .current_dir(root)
                .output()
                .expect("Git can stage the tracked fixture");
            assert!(
                output.status.success(),
                "Git stages the tracked fixture: exit {:?}",
                output.status.code()
            );
        }
    }
}

fn run_native_guard(root: &Path, name: &str) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_agent-canon"));
    command.arg("generated-artifact-guard");
    match name {
        "default-cwd-root" => {}
        "help" => {
            command.arg("--help");
        }
        "invalid-argument" => {
            command.arg("--not-a-real-option");
        }
        _ => {
            command.arg("--root").arg(root);
        }
    }
    command
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env("GIT_CONFIG_GLOBAL", "/dev/null")
        .current_dir(root)
        .output()
        .expect("native generated artifact guard runs")
}

fn replace_bytes(input: &[u8], needle: &[u8], replacement: &[u8]) -> Vec<u8> {
    assert!(!needle.is_empty());
    let mut output = Vec::new();
    let mut remaining = input;
    while let Some(index) = remaining
        .windows(needle.len())
        .position(|window| window == needle)
    {
        output.extend_from_slice(&remaining[..index]);
        output.extend_from_slice(replacement);
        remaining = &remaining[index + needle.len()..];
    }
    output.extend_from_slice(remaining);
    output
}

#[test]
fn native_cli_matches_all_frozen_python_oracle_cases() {
    let oracle: Value = serde_json::from_str(PYTHON_ORACLE).expect("frozen Python oracle is JSON");
    assert_eq!(
        oracle["schema"],
        "agent-canon.generated-artifact-guard-python-oracle.v1"
    );
    let cases = oracle["cases"]
        .as_array()
        .expect("frozen Python oracle has cases");
    assert_eq!(cases.len(), 12, "all frozen old CLI cases remain covered");

    for case in cases {
        let name = case["name"].as_str().expect("case has a name");
        let fixture = Fixture::new(name);
        prepare_fixture(case, fixture.root());
        let output = run_native_guard(fixture.root(), name);

        let expected_exit = i32::try_from(
            case["exit_code"]
                .as_i64()
                .expect("frozen exit code is an integer"),
        )
        .expect("frozen exit code fits i32");
        let mut expected_stdout = decode_hex(
            case["stdout_hex"]
                .as_str()
                .expect("stdout oracle is encoded as hex"),
        );
        let mut expected_stderr = decode_hex(
            case["stderr_hex"]
                .as_str()
                .expect("stderr oracle is encoded as hex"),
        );
        if matches!(name, "help" | "invalid-argument") {
            expected_stdout = replace_bytes(
                &expected_stdout,
                b"generated_artifact_guard.py",
                b"agent-canon generated-artifact-guard",
            );
            expected_stderr = replace_bytes(
                &expected_stderr,
                b"generated_artifact_guard.py",
                b"agent-canon generated-artifact-guard",
            );
        }

        assert_eq!(
            output.status.code(),
            Some(expected_exit),
            "case {name} exit"
        );
        assert_eq!(output.stdout, expected_stdout, "case {name} stdout");
        assert_eq!(output.stderr, expected_stderr, "case {name} stderr");
    }
}

#[test]
fn invalid_git_path_sorting_matches_python_surrogateescape_order() {
    let fixture = Fixture::new("surrogateescape-sort");
    initialize_repository(fixture.root());

    let invalid_path = b"reports/dependency-review/run/same-\xff.tsv";
    let astral_path = "reports/dependency-review/run/same-𐀀.tsv".as_bytes();
    for path_bytes in [invalid_path.as_slice(), astral_path] {
        let path = fixture.root().join(path_from_bytes(path_bytes));
        fs::create_dir_all(path.parent().expect("fixture file has a parent"))
            .expect("create generated artifact parent");
        fs::write(path, b"generated artifact fixture\n").expect("write generated artifact fixture");
    }

    let output = run_native_guard(fixture.root(), "surrogateescape-sort");
    let mut expected = b"GENERATED_ARTIFACT_GUARD=fail\nGENERATED_ARTIFACT_BLOCKERS=generated_report_artifact_untracked_left_in_tree:reports/dependency-review/run/same-\xff.tsv|generated_report_artifact_untracked_left_in_tree:reports/dependency-review/run/same-"
        .to_vec();
    expected.extend_from_slice("𐀀".as_bytes());
    expected.extend_from_slice(
        b".tsv\nGENERATED_ARTIFACT_NEXT=delete_regeneratable_report_outputs_or_write_durable_evidence_to_documents_agents_notes_with_dependency_manifest\n",
    );
    assert_eq!(output.status.code(), Some(1));
    assert_eq!(output.stdout, expected);
    assert!(output.stderr.is_empty());
}
