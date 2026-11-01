#![cfg(unix)]

// @dependency-start
// contract test
// responsibility Compares native duplicate-design CLI reports and deletion effects with frozen Python CLI outcomes.
// upstream implementation ../src/docs.rs owns the native duplicate-design command
// upstream implementation ../src/source_mutation.rs owns capability-bound deletion
// upstream evidence ../../../../../tests/fixtures/design_duplicates/python_golden.json freezes the old CLI oracle
// @dependency-end

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

const PYTHON_GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/design_duplicates/python_golden.json");
const PYTHON_GOLDEN_SHA256: &str =
    "9d39e8739fa7ff56c437873587131b40bf41fa1c993c3111488e224858e5e971";
const NATIVE_PROGRAM: &str = "agent-canon docs find-redundant-designs";
const PREFIX_USAGE: &str = "usage: agent-canon docs find-redundant-designs [-h] [--design-root DESIGN_ROOT] [--delete]\n                                 [--mutation-capability-json MUTATION_CAPABILITY_JSON]\n                                 [--runtime-root RUNTIME_ROOT]\n                                 [--output OUTPUT]";
const PREFIX_HELP: &str = "usage: agent-canon docs find-redundant-designs [-h] [--design-root DESIGN_ROOT] [--delete]\n                                 [--mutation-capability-json MUTATION_CAPABILITY_JSON]\n                                 [--runtime-root RUNTIME_ROOT]\n                                 [--output OUTPUT]\n\nDetect exact-duplicate design documents. The analyzer is read-only by default.\nReports are runtime artifacts and therefore require an explicit external\nruntime root (or its explicitly configured environment capability).\n``--delete`` is a separate source mutation operation and requires an exact\ntyped ``--mutation-capability-json``.\n\noptions:\n  -h, --help            show this help message and exit\n  --design-root DESIGN_ROOT\n                        Read-only design root (defaults to documents/design).\n  --delete              Delete redundant source files; requires an explicit\n                        mutation capability.\n  --mutation-capability-json MUTATION_CAPABILITY_JSON\n                        Exact typed source mutation capability JSON.\n  --runtime-root RUNTIME_ROOT\n                        External runtime root (or AGENT_CANON_RUNTIME_ROOT);\n                        never source-local.\n  --output OUTPUT       External report path; when omitted, a run-scoped file\n                        is created under the runtime root.\n";

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct TempRoot(PathBuf);

impl TempRoot {
    fn new() -> Self {
        let elapsed = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock is after the epoch")
            .as_nanos();
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-design-duplicates-{}-{elapsed:x}-{sequence:x}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("temporary test root is created");
        Self(path.canonicalize().expect("temporary root is canonical"))
    }

    fn source(&self) -> PathBuf {
        self.0.join("source")
    }

    fn runtime(&self) -> PathBuf {
        self.0.join("runtime")
    }
}

impl Drop for TempRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn native_duplicate_design_cli_matches_frozen_python_oracle() {
    let fixture_hash = format!("{:x}", Sha256::digest(PYTHON_GOLDEN.as_bytes()));
    assert_eq!(fixture_hash, PYTHON_GOLDEN_SHA256);
    let golden: Value = serde_json::from_str(PYTHON_GOLDEN).expect("frozen oracle parses");
    let cases = golden["cases"].as_array().expect("oracle has cases");
    assert_eq!(cases.len(), 13, "the original CLI oracle has 13 cases");

    for case in cases {
        run_oracle_case(case);
    }
}

#[test]
fn native_duplicate_cli_matches_observed_argparse_prefixes() {
    // These cases preserve the old CLI observations with only the native command
    // label and temporary source/runtime roots substituted.
    let help_temp = TempRoot::new();
    let help_source = help_temp.source();
    let (help_a, help_b) = write_duplicate_pair(&help_source);
    let help = run_native_args(&help_source, &["--he".to_string()]);
    assert_eq!(help.status.code(), Some(0));
    assert_eq!(String::from_utf8_lossy(&help.stdout), PREFIX_HELP);
    assert!(help.stderr.is_empty());
    assert!(help_a.exists() && help_b.exists());
    assert!(!help_temp.runtime().exists());

    let data_temp = TempRoot::new();
    let data_source = data_temp.source();
    let data_runtime = data_temp.runtime();
    let (data_a, data_b) = write_duplicate_pair(&data_source);
    let data_design = data_source.join("documents/design");
    let data_output = data_runtime.join("report.txt");
    let data = run_native_args(
        &data_source,
        &[
            "--des".to_string(),
            data_design.display().to_string(),
            "--runtime-r".to_string(),
            data_runtime.display().to_string(),
            "--out".to_string(),
            "report.txt".to_string(),
        ],
    );
    assert_eq!(data.status.code(), Some(0));
    assert!(data.stderr.is_empty());
    assert_eq!(
        String::from_utf8_lossy(&data.stdout),
        format!("Report written to {}\n", data_output.display())
    );
    assert_eq!(
        fs::read_to_string(&data_output).expect("prefix report is written"),
        duplicate_pair_report(&data_design, false)
    );
    assert!(data_a.exists() && data_b.exists());

    let delete_temp = TempRoot::new();
    let delete_source = delete_temp.source();
    let delete_runtime = delete_temp.runtime();
    let (delete_a, delete_b) = write_duplicate_pair(&delete_source);
    let delete_design = delete_source.join("documents/design");
    let delete_output = delete_runtime.join("report.txt");
    let delete = run_native_args(
        &delete_source,
        &[
            "--des".to_string(),
            delete_design.display().to_string(),
            "--del".to_string(),
            "--mutation-c".to_string(),
            r#"{"allowed_paths": ["documents/design/b.md"], "purpose": "oracle", "authority": "issue-1630"}"#.to_string(),
            "--runtime-r".to_string(),
            delete_runtime.display().to_string(),
            "--out".to_string(),
            "report.txt".to_string(),
        ],
    );
    assert_eq!(delete.status.code(), Some(0));
    assert!(delete.stderr.is_empty());
    assert_eq!(
        String::from_utf8_lossy(&delete.stdout),
        format!("Report written to {}\n", delete_output.display())
    );
    assert_eq!(
        fs::read_to_string(&delete_output).expect("delete-prefix report is written"),
        duplicate_pair_report(&delete_design, true)
    );
    assert!(delete_a.exists());
    assert!(!delete_b.exists());

    for (arguments, detail) in [
        (
            vec!["--d".to_string()],
            "ambiguous option: --d could match --design-root, --delete",
        ),
        (
            vec!["--he=value".to_string()],
            "argument -h/--help: ignored explicit argument 'value'",
        ),
    ] {
        let temp = TempRoot::new();
        let source = temp.source();
        let (a, b) = write_duplicate_pair(&source);
        let result = run_native_args(&source, &arguments);
        assert_eq!(result.status.code(), Some(2));
        assert!(result.stdout.is_empty());
        assert_eq!(
            String::from_utf8_lossy(&result.stderr),
            format!("{PREFIX_USAGE}\n{NATIVE_PROGRAM}: error: {detail}\n")
        );
        assert!(a.exists() && b.exists());
        assert!(!temp.runtime().exists());
    }
}

fn write_duplicate_pair(source: &Path) -> (PathBuf, PathBuf) {
    let design_root = source.join("documents/design");
    fs::create_dir_all(&design_root).expect("design root is created");
    let a = design_root.join("a.md");
    let b = design_root.join("b.md");
    fs::write(&a, "same").expect("first design is written");
    fs::write(&b, "same").expect("second design is written");
    (a, b)
}

fn duplicate_pair_report(design_root: &Path, delete: bool) -> String {
    let a = design_root.join("a.md");
    let b = design_root.join("b.md");
    let mut report = format!(
        "DUP_GROUP:\n  {}\n  {}\n  KEEP: {}\n  DELETE: {}\n\n",
        a.display(),
        b.display(),
        a.display(),
        b.display()
    );
    if delete {
        report.push_str(&format!("\nDELETED:\n{}\n", b.display()));
    }
    report
}

fn run_oracle_case(case: &Value) {
    let name = case["name"].as_str().expect("case has a name");
    let temp = TempRoot::new();
    let source = temp.source();
    let runtime = temp.runtime();
    let design_root = source.join("documents/design");
    fs::create_dir_all(&design_root).expect("design root is created");

    for (relative, contents) in case["files"].as_object().expect("case files are an object") {
        let path = design_root.join(relative);
        fs::create_dir_all(path.parent().expect("fixture file has a parent"))
            .expect("fixture parent is created");
        fs::write(path, contents.as_str().expect("fixture contents are text"))
            .expect("fixture file is written");
    }
    assert_eq!(
        source_hashes(&source),
        oracle_hashes(&case["before"]),
        "{name}: setup"
    );

    let first = run_cli(case, &source, &runtime);
    assert_eq!(
        first.status.code(),
        Some(case["exit"].as_i64().expect("case has exit status") as i32),
        "{name}: exit status\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&first.stdout),
        String::from_utf8_lossy(&first.stderr)
    );
    assert_eq!(
        String::from_utf8_lossy(&first.stderr),
        mapped_context(
            case,
            case["stderr"].as_str().expect("case stderr is text"),
            &source,
            &runtime
        ),
        "{name}: stderr"
    );
    if !case["default_output"].as_bool().unwrap_or(false) {
        assert_eq!(
            String::from_utf8_lossy(&first.stdout),
            mapped_context(
                case,
                case["stdout"].as_str().expect("case stdout is text"),
                &source,
                &runtime
            ),
            "{name}: stdout"
        );
    } else {
        assert_default_report_path(&first, &runtime, name);
    }

    let mut report_paths = Vec::new();
    if first.status.success() {
        report_paths.push(stdout_report_path(&first));
    }
    if !case["second_invocation"].is_null() {
        let second = run_cli(case, &source, &runtime);
        let expected = &case["second_invocation"];
        assert_eq!(
            second.status.code(),
            Some(expected["exit"].as_i64().expect("second exit status") as i32),
            "{name}: second invocation status"
        );
        assert_eq!(
            String::from_utf8_lossy(&second.stderr),
            mapped_context(
                case,
                expected["stderr"].as_str().expect("second stderr is text"),
                &source,
                &runtime,
            ),
            "{name}: second invocation stderr"
        );
        assert_default_report_path(&second, &runtime, name);
        report_paths.push(stdout_report_path(&second));
    }
    if report_paths.len() == 2 {
        assert_ne!(
            report_paths[0], report_paths[1],
            "{name}: output paths are unique"
        );
    }

    assert_eq!(
        report_contents(&runtime),
        expected_report_contents(case, &source, &runtime),
        "{name}: report files"
    );
    assert_eq!(
        source_hashes(&source),
        oracle_hashes(&case["after"]),
        "{name}: source effects"
    );
}

fn run_cli(case: &Value, source: &Path, runtime: &Path) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_agent-canon"));
    command
        .args(["docs", "find-redundant-designs"])
        .current_dir(source)
        .env_remove("AGENT_CANON_RUNTIME_ROOT");

    for argument in case["extra"]
        .as_array()
        .expect("case arguments are an array")
    {
        let argument = argument.as_str().expect("case argument is text");
        if argument != "--default-output" && argument != "--source-output" {
            command.arg(argument);
        }
    }
    if let Some(capability) = case["capability"].as_object() {
        command
            .arg("--mutation-capability-json")
            .arg(serde_json::to_string(capability).expect("capability serializes"));
    }
    if case["has_runtime"].as_bool().unwrap_or(false) {
        command.arg("--runtime-root").arg(runtime);
    }
    if !case["default_output"].as_bool().unwrap_or(false) {
        let old_source = case["source_root"].as_str().expect("case source root");
        let old_runtime = case["runtime_root"].as_str().expect("case runtime root");
        let old_output = case["output"].as_str().expect("case output path");
        let output = old_output
            .replace(old_source, &source.display().to_string())
            .replace(old_runtime, &runtime.display().to_string());
        command.arg("--output").arg(output);
    }
    command.output().expect("native duplicate CLI runs")
}

fn run_native_args(source: &Path, args: &[String]) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_agent-canon"));
    command
        .args(["docs", "find-redundant-designs"])
        .args(args)
        .current_dir(source)
        .env_remove("AGENT_CANON_RUNTIME_ROOT");
    command.output().expect("native duplicate CLI runs")
}

fn mapped_context(case: &Value, text: &str, source: &Path, runtime: &Path) -> String {
    let old_source = case["source_root"].as_str().expect("case source root");
    let old_runtime = case["runtime_root"].as_str().expect("case runtime root");
    text.replace(old_source, &source.display().to_string())
        .replace(old_runtime, &runtime.display().to_string())
        .replace(
            "find_redundant_designs.py",
            "agent-canon docs find-redundant-designs",
        )
}

fn assert_default_report_path(output: &Output, runtime: &Path, name: &str) {
    let path = stdout_report_path(output);
    assert_eq!(
        String::from_utf8_lossy(&output.stdout),
        format!("Report written to {}\n", path.display()),
        "{name}: report path output"
    );
    assert!(
        path.starts_with(runtime.join("tasks/redundant-designs")),
        "{name}: {path:?}"
    );
    assert_eq!(
        path.file_name().and_then(|value| value.to_str()),
        Some("redundant_designs.txt"),
        "{name}: report filename"
    );
    assert!(
        path.parent()
            .and_then(|parent| parent.file_name())
            .and_then(|value| value.to_str())
            .is_some_and(|run_name| run_name.starts_with("run-")),
        "{name}: run-scoped directory"
    );
}

fn stdout_report_path(output: &Output) -> PathBuf {
    let stdout = String::from_utf8_lossy(&output.stdout);
    let path = stdout
        .strip_prefix("Report written to ")
        .expect("successful command prints report path")
        .strip_suffix('\n')
        .expect("report path is newline terminated");
    PathBuf::from(path)
}

fn expected_report_contents(case: &Value, source: &Path, runtime: &Path) -> Vec<String> {
    let reports = case["reports"]
        .as_object()
        .expect("case reports are an object");
    let mut expected = reports
        .values()
        .map(|contents| {
            mapped_context(
                case,
                contents.as_str().expect("report contents are text"),
                source,
                runtime,
            )
        })
        .collect::<Vec<_>>();
    expected.sort();
    expected
}

fn report_contents(root: &Path) -> Vec<String> {
    let mut files = Vec::new();
    if root.is_dir() {
        collect_files(root, &mut files);
    }
    let mut contents = files
        .into_iter()
        .filter(|path| path.extension().is_some_and(|extension| extension == "txt"))
        .map(|path| fs::read_to_string(path).expect("runtime report is UTF-8"))
        .collect::<Vec<_>>();
    contents.sort();
    contents
}

fn collect_files(directory: &Path, files: &mut Vec<PathBuf>) {
    for entry in fs::read_dir(directory).expect("runtime directory is readable") {
        let path = entry.expect("runtime entry is readable").path();
        if path.is_dir() {
            collect_files(&path, files);
        } else if path.is_file() {
            files.push(path);
        }
    }
}

fn source_hashes(root: &Path) -> BTreeMap<String, String> {
    let mut files = Vec::new();
    let design_root = root.join("documents/design");
    collect_files(&design_root, &mut files);
    files
        .into_iter()
        .map(|path| {
            let relative = path
                .strip_prefix(root)
                .expect("fixture file is below source root");
            let key = relative
                .to_string_lossy()
                .replace(std::path::MAIN_SEPARATOR, "/");
            let hash = format!(
                "{:x}",
                Sha256::digest(fs::read(path).expect("source reads"))
            );
            (key, hash)
        })
        .collect()
}

fn oracle_hashes(value: &Value) -> BTreeMap<String, String> {
    value
        .as_object()
        .expect("oracle source hashes are an object")
        .iter()
        .map(|(path, hash)| {
            (
                path.clone(),
                hash.as_str().expect("oracle hash is text").to_string(),
            )
        })
        .collect()
}
