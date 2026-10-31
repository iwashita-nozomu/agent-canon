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
use std::io;
#[cfg(unix)]
use std::os::unix::ffi::OsStringExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

const PYTHON_ORACLE: &str =
    include_str!("../../../../../tests/fixtures/generated_artifact_guard/python_golden.json");

static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(0);

const PORTABLE_ORACLE_CASES: &[&str] = &[
    "tracked-generated-report",
    "untracked-generated-report",
    "ignored-generated-report",
    "mixed-tracked-untracked-ignored",
    "allowed-current-run-bundle",
    "plain-non-git-root",
    "default-cwd-root",
    "help",
    "invalid-argument",
];
const POSIX_SPECIAL_FILENAME_CASES: &[&str] = &[
    "literal-posix-backslash",
    "newline-filename",
    "raw-byte-filename",
];

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
    let (digits, remainder) = value.as_bytes().as_chunks::<2>();
    assert!(remainder.is_empty(), "hex fixture has paired digits");
    digits
        .iter()
        .map(|[high, low]| {
            let digit = |byte: u8| match byte {
                b'0'..=b'9' => byte - b'0',
                b'a'..=b'f' => byte - b'a' + 10,
                b'A'..=b'F' => byte - b'A' + 10,
                _ => panic!("fixture contains a non-hex digit"),
            };
            digit(*high) * 16 + digit(*low)
        })
        .collect()
}

#[cfg(unix)]
fn path_from_bytes(path: &[u8]) -> PathBuf {
    PathBuf::from(OsString::from_vec(path.to_vec()))
}

#[cfg(not(unix))]
fn path_from_bytes(path: &[u8]) -> PathBuf {
    PathBuf::from(std::str::from_utf8(path).expect("portable fixture path is UTF-8"))
}

fn empty_global_git_config(root: &Path) -> PathBuf {
    let path = root.join(".agent-canon-test-empty-global-gitconfig");
    fs::write(&path, b"").expect("write empty global Git config");
    path
}

fn fixture_command(root: &Path, program: &str) -> Command {
    let global_config = empty_global_git_config(root);
    let mut command = Command::new(program);
    command
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env("GIT_CONFIG_GLOBAL", global_config)
        .current_dir(root);
    command
}

#[cfg(unix)]
fn unavailable_by_platform(_case_name: &str) -> Option<&'static str> {
    None
}

#[cfg(not(unix))]
fn unavailable_by_platform(case_name: &str) -> Option<&'static str> {
    match case_name {
        "raw-byte-filename" => Some("non-Unix OsString cannot preserve a POSIX raw-byte filename"),
        #[cfg(windows)]
        "literal-posix-backslash" => {
            Some("Windows treats backslash as a path separator, not a filename byte")
        }
        _ => None,
    }
}

fn known_filesystem_unavailable(case_name: &str, error: &io::Error) -> Option<&'static str> {
    #[cfg(target_os = "macos")]
    if case_name == "raw-byte-filename" && error.raw_os_error() == Some(92) {
        return Some("filesystem rejected raw filename bytes with EILSEQ (92)");
    }
    #[cfg(windows)]
    if case_name == "newline-filename" && error.raw_os_error() == Some(123) {
        return Some("Windows rejected the newline filename with ERROR_INVALID_NAME (123)");
    }
    let _ = case_name;
    let _ = error;
    None
}

fn git(root: &Path, args: &[&str]) -> Output {
    fixture_command(root, "git")
        .args(args)
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

fn prepare_fixture(case: &Value, root: &Path) -> Result<(), io::Error> {
    if case["name"] != "plain-non-git-root" {
        initialize_repository(root);
    }
    if let Some(patterns) = case.get("ignore_patterns_hex") {
        write_ignore_patterns(
            root,
            patterns
                .as_array()
                .expect("ignore patterns are a list when present"),
        );
    }
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
        fs::write(&path, b"generated artifact fixture\n")?;
        if fixture_file["declared_state"] == "tracked" {
            let output = fixture_command(root, "git")
                .args(["add", "-f", "--"])
                .arg(path_from_bytes(&path_bytes))
                .output()
                .expect("Git can stage the tracked fixture");
            assert!(
                output.status.success(),
                "Git stages the tracked fixture: exit {:?}",
                output.status.code()
            );
        }
    }
    Ok(())
}

fn native_guard_command(root: &Path) -> Command {
    let mut command = fixture_command(root, env!("CARGO_BIN_EXE_agent-canon"));
    command.arg("generated-artifact-guard");
    command
}

fn run_native_guard(root: &Path, name: &str) -> Output {
    let mut command = native_guard_command(root);
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

    let mut executed = Vec::new();
    let mut unavailable = Vec::new();
    for case in cases {
        let name = case["name"].as_str().expect("case has a name");
        if let Some(reason) = unavailable_by_platform(name) {
            unavailable.push((name.to_string(), reason.to_string()));
            continue;
        }

        let fixture = Fixture::new(name);
        if let Err(error) = prepare_fixture(case, fixture.root()) {
            if let Some(reason) = known_filesystem_unavailable(name, &error) {
                unavailable.push((name.to_string(), reason.to_string()));
                continue;
            }
            panic!("fixture setup failed for {name}: {error}");
        }
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
        executed.push(name);
    }

    assert!(
        PORTABLE_ORACLE_CASES
            .iter()
            .all(|expected| executed.contains(expected)),
        "portable cases must execute; executed={executed:?}, unavailable={unavailable:?}"
    );
    assert!(
        executed.len() >= PORTABLE_ORACLE_CASES.len(),
        "at least nine portable oracle cases must execute"
    );
    assert_eq!(
        executed.len() + unavailable.len(),
        cases.len(),
        "every frozen case is executed or has an explicit platform/filesystem reason: {unavailable:?}"
    );
    assert!(unavailable
        .iter()
        .all(|(name, _)| { POSIX_SPECIAL_FILENAME_CASES.contains(&name.as_str()) }));
    for (name, reason) in unavailable {
        eprintln!("generated artifact oracle case unavailable: {name}: {reason}");
    }
}

#[cfg(unix)]
#[test]
fn invalid_git_path_sorting_matches_python_surrogateescape_order() {
    let fixture = Fixture::new("surrogateescape-sort");
    initialize_repository(fixture.root());

    let invalid_path = b"reports/dependency-review/run/same-\xff.tsv";
    let astral_path = "reports/dependency-review/run/same-𐀀.tsv".as_bytes();
    let invalid_file = fixture.root().join(path_from_bytes(invalid_path));
    fs::create_dir_all(invalid_file.parent().expect("fixture file has a parent"))
        .expect("create generated artifact parent");
    if let Err(error) = fs::write(&invalid_file, b"generated artifact fixture\n") {
        if let Some(reason) = known_filesystem_unavailable("raw-byte-filename", &error) {
            eprintln!("surrogateescape sort case unavailable: {reason}");
            return;
        }
        panic!("raw-byte sort fixture setup failed: {error}");
    }
    let astral_file = fixture.root().join(path_from_bytes(astral_path));
    fs::write(astral_file, b"generated artifact fixture\n").expect("write astral-Unicode fixture");

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

#[test]
fn native_cli_accepts_unambiguous_argparse_long_option_prefixes() {
    let fixture = Fixture::new("argparse-option-prefixes");
    initialize_repository(fixture.root());

    let canonical_root = run_native_guard(fixture.root(), "explicit-root");
    let mut short_root_command = native_guard_command(fixture.root());
    let short_root_output = short_root_command
        .arg("--r")
        .arg(fixture.root())
        .output()
        .expect("native guard accepts the shortest root prefix");
    assert_eq!(
        short_root_output.status.code(),
        canonical_root.status.code()
    );
    assert_eq!(short_root_output.stdout, canonical_root.stdout);
    assert_eq!(short_root_output.stderr, canonical_root.stderr);

    let mut inline_root = OsString::from("--roo=");
    inline_root.push(fixture.root().as_os_str());
    let mut inline_command = native_guard_command(fixture.root());
    let inline_root_output = inline_command
        .arg(inline_root)
        .output()
        .expect("native guard accepts an abbreviated root option with an inline value");
    assert_eq!(
        inline_root_output.status.code(),
        canonical_root.status.code()
    );
    assert_eq!(inline_root_output.stdout, canonical_root.stdout);
    assert_eq!(inline_root_output.stderr, canonical_root.stderr);

    let full_help = run_native_guard(fixture.root(), "help");
    let mut abbreviated_help = native_guard_command(fixture.root());
    let abbreviated_help = abbreviated_help
        .arg("--he")
        .output()
        .expect("native guard accepts an unambiguous help prefix");
    assert_eq!(abbreviated_help.status.code(), full_help.status.code());
    assert_eq!(abbreviated_help.stdout, full_help.stdout);
    assert_eq!(abbreviated_help.stderr, full_help.stderr);
}
