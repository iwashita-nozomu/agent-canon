// @dependency-start
// contract test
// responsibility Compares native design similarity CLI outputs with frozen CPython oracles.
// upstream implementation ../src/docs.rs owns native design similarity CLI and external report admission
// upstream implementation ../src/python_sequence_matcher.rs owns CPython-compatible matching and ratio
// upstream evidence ../../../../../tests/fixtures/design_similarity/python_golden.json freezes the original CLI oracle
// upstream evidence ../../../../../tests/fixtures/design_similarity/float_python_golden.json freezes Unicode float parsing observations
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
    include_str!("../../../../../tests/fixtures/design_similarity/python_golden.json");
const PYTHON_GOLDEN_SHA256: &str =
    "497ce651f05cf0a33643425864f0b21ce5527be250f532b9cf5141e369a0d320";
const FLOAT_GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/design_similarity/float_python_golden.json");
const FLOAT_GOLDEN_SHA256: &str =
    "3db07c4b8801235e66d43d138892830a884018fe74932869277aca46ef8c37ee";

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
            "agent-canon-design-similarity-{}-{elapsed:x}-{sequence:x}",
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
fn native_similarity_cli_matches_frozen_python_oracle() {
    assert_eq!(
        format!("{:x}", Sha256::digest(PYTHON_GOLDEN.as_bytes())),
        PYTHON_GOLDEN_SHA256,
        "the original CPython fixture bytes are immutable"
    );
    let golden: Value = serde_json::from_str(PYTHON_GOLDEN).expect("frozen oracle parses");
    let cases = golden["cases"].as_array().expect("oracle has cases");
    assert_eq!(cases.len(), 13, "the original CLI oracle has 13 cases");
    for case in cases {
        run_oracle_case(case);
    }
}

#[test]
fn native_similarity_cli_matches_frozen_unicode_float_oracle() {
    assert_eq!(
        format!("{:x}", Sha256::digest(FLOAT_GOLDEN.as_bytes())),
        FLOAT_GOLDEN_SHA256,
        "the supplemental CPython fixture bytes are immutable"
    );
    let golden: Value = serde_json::from_str(FLOAT_GOLDEN).expect("float oracle parses");
    let cases = golden["cases"].as_array().expect("float oracle has cases");
    assert_eq!(cases.len(), 6, "the Unicode float oracle has six cases");
    for case in cases {
        run_oracle_case(case);
    }
}

#[test]
fn native_similarity_preserves_unlisted_bracket_punctuation() {
    // The captured CPython CLI oracle kept brackets in normalized text, yielding 0.8
    // similarity and no report pair at the 0.85 threshold.
    let temp = TempRoot::new();
    let source = temp.source();
    let runtime = temp.runtime();
    write(&source.join("documents/design/a.md"), "[todo]");
    write(&source.join("documents/design/b.md"), "todo");

    let output = run_native(
        &source,
        &runtime,
        &["--min", "0.85", "--output", "report.txt"],
    );
    assert_eq!(output.status.code(), Some(0));
    assert!(output.stderr.is_empty());
    assert_eq!(
        String::from_utf8_lossy(&output.stdout),
        format!(
            "Report written to {}\n",
            runtime.join("report.txt").display()
        )
    );
    assert_eq!(
        fs::read_to_string(runtime.join("report.txt")).expect("frozen-oracle report exists"),
        "No similar design files found with threshold >= 0.85\n"
    );
}

#[test]
fn native_similarity_path_order_matches_python_path_models() {
    // These expected orientations were produced by the captured PurePosixPath and
    // PureWindowsPath comparison models. They are not a Windows filesystem run.
    let temp = TempRoot::new();
    let source = temp.source();
    let runtime = temp.runtime();
    let design_root = source.join("documents/design");
    for name in ["B.md", "a.md", "c.md"] {
        write(&design_root.join(name), "identical content");
    }
    let before = snapshot(&source);

    let output = run_native(&source, &runtime, &["--min", "1", "--output", "report.txt"]);
    assert_eq!(output.status.code(), Some(0));
    assert!(output.stderr.is_empty());
    let pairs: [(&str, &str); 3] = if cfg!(windows) {
        [("B.md", "c.md"), ("a.md", "c.md"), ("a.md", "B.md")]
    } else {
        [("a.md", "c.md"), ("B.md", "c.md"), ("B.md", "a.md")]
    };
    let mut expected = "Similar design file pairs (threshold >= 1.0)\n".to_owned();
    for (first, second) in pairs {
        expected.push_str(&format!(
            "1.000  {}  {}\n",
            design_root.join(first).display(),
            design_root.join(second).display()
        ));
    }
    assert_eq!(
        fs::read_to_string(runtime.join("report.txt")).expect("ordered report exists"),
        expected
    );
    assert_eq!(snapshot(&source), before, "source tree stays unchanged");
}

#[test]
fn native_similarity_path_order_uses_python_lowercase_not_casefold() {
    // Python 3.12 pathlib.lower() keeps sharp-s distinct from "ss". This expected
    // vector comes from PureWindowsPath comparison, not a Windows filesystem run.
    let temp = TempRoot::new();
    let source = temp.source();
    let runtime = temp.runtime();
    let design_root = source.join("documents/design");
    for name in ["ß.md", "ss.md", "S.md"] {
        write(&design_root.join(name), "identical content");
    }
    let before = snapshot(&source);

    let output = run_native(&source, &runtime, &["--min", "1", "--output", "report.txt"]);
    assert_eq!(output.status.code(), Some(0));
    assert!(output.stderr.is_empty());
    let mut expected = "Similar design file pairs (threshold >= 1.0)\n".to_owned();
    for (first, second) in [("ss.md", "ß.md"), ("S.md", "ß.md"), ("S.md", "ss.md")] {
        expected.push_str(&format!(
            "1.000  {}  {}\n",
            design_root.join(first).display(),
            design_root.join(second).display()
        ));
    }
    assert_eq!(
        fs::read_to_string(runtime.join("report.txt")).expect("lowercase report exists"),
        expected
    );
    assert_eq!(snapshot(&source), before, "source tree stays unchanged");
}

#[test]
fn native_similarity_default_report_is_run_scoped_in_external_runtime() {
    let temp = TempRoot::new();
    let source = temp.source();
    let runtime = temp.runtime();
    write(&source.join("documents/design/a.md"), "shared design");
    write(&source.join("documents/design/b.md"), "shared design");

    let output = run_native(&source, &runtime, &["--min", "1"]);
    assert_eq!(output.status.code(), Some(0));
    assert!(output.stderr.is_empty());
    let report_path = stdout_report_path(&output);
    assert!(report_path.starts_with(runtime.join("tasks/similar-designs")));
    assert_eq!(
        report_path.file_name().and_then(|name| name.to_str()),
        Some("similar_designs_report.txt")
    );
    assert!(report_path.is_file());
    assert!(!source.join("reports").exists());
}

fn run_oracle_case(case: &Value) {
    let name = case["name"].as_str().expect("case has a name");
    let temp = TempRoot::new();
    let source = temp.source();
    let runtime = temp.runtime();
    let design_root = source.join("documents/design");
    fs::create_dir_all(&design_root).expect("fixture design root is created");

    for (relative, contents) in case["files"].as_object().expect("case files are an object") {
        write(
            &design_root.join(relative),
            contents.as_str().expect("fixture contents are text"),
        );
    }
    let before = snapshot(&source);
    let threshold = case["threshold_argument"]
        .as_str()
        .expect("case has a threshold argument");
    let output = run_native(
        &source,
        &runtime,
        &["--min", threshold, "--output", "report.txt"],
    );

    assert_eq!(
        output.status.code(),
        Some(case["exit"].as_i64().expect("case has exit status") as i32),
        "{name}: exit status\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(
        String::from_utf8_lossy(&output.stdout),
        map_context(
            case,
            case["stdout"].as_str().expect("stdout is text"),
            &source,
            &runtime
        ),
        "{name}: stdout"
    );
    assert_eq!(
        String::from_utf8_lossy(&output.stderr),
        case["stderr"].as_str().expect("stderr is text"),
        "{name}: stderr"
    );
    match case["report"].as_str() {
        Some(expected) => {
            let report = fs::read_to_string(runtime.join("report.txt"))
                .unwrap_or_else(|error| panic!("{name}: report is absent: {error}"));
            assert_eq!(
                report,
                map_context(case, expected, &source, &runtime),
                "{name}: report"
            );
        }
        None => {
            assert!(
                !runtime.exists(),
                "{name}: invalid input fails before creating the runtime root"
            );
            assert!(
                !runtime.join("report.txt").exists(),
                "{name}: invalid input does not write a report"
            );
        }
    }
    assert_eq!(
        snapshot(&source),
        before,
        "{name}: source tree stays unchanged"
    );
    assert!(
        !source.join("reports").exists(),
        "{name}: no source-local report"
    );
}

fn run_native(source: &Path, runtime: &Path, extra: &[&str]) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_agent-canon"));
    command
        .arg("docs")
        .arg("find-similar-designs")
        .arg("--design-root")
        .arg("documents/design")
        .args(extra)
        .arg("--runtime-root")
        .arg(runtime)
        .current_dir(source)
        .env_remove("AGENT_CANON_RUNTIME_ROOT");
    command.output().expect("native CLI starts")
}

fn map_context(case: &Value, expected: &str, source: &Path, runtime: &Path) -> String {
    let old_source = case["source"].as_str().expect("case source is text");
    let mut mapped = expected.to_owned();
    for relative in case["files"]
        .as_object()
        .expect("case files are an object")
        .keys()
    {
        let old_path = format!("{old_source}/documents/design/{relative}");
        let new_path = source.join("documents/design").join(relative);
        mapped = mapped.replace(&old_path, &new_path.display().to_string());
    }
    if let Some(old_runtime) = case["runtime"].as_str() {
        let old_report = format!("{old_runtime}/report.txt");
        let new_report = runtime.join("report.txt");
        mapped = mapped.replace(&old_report, &new_report.display().to_string());
    }
    mapped
}

fn stdout_report_path(output: &Output) -> PathBuf {
    let stdout = String::from_utf8_lossy(&output.stdout);
    let path = stdout
        .strip_prefix("Report written to ")
        .expect("successful CLI names its report")
        .trim();
    PathBuf::from(path)
}

fn write(path: &Path, text: &str) {
    fs::create_dir_all(path.parent().expect("fixture file has a parent"))
        .expect("fixture parent is created");
    fs::write(path, text).expect("fixture file is written");
}

fn snapshot(root: &Path) -> BTreeMap<PathBuf, Vec<u8>> {
    let mut files = BTreeMap::new();
    collect_snapshot(root, root, &mut files);
    files
}

fn collect_snapshot(root: &Path, current: &Path, files: &mut BTreeMap<PathBuf, Vec<u8>>) {
    for entry in fs::read_dir(current).expect("source directory is readable") {
        let entry = entry.expect("source entry is readable");
        let path = entry.path();
        if entry
            .file_type()
            .expect("source file type is readable")
            .is_dir()
        {
            collect_snapshot(root, &path, files);
        } else if path.is_file() {
            files.insert(
                path.strip_prefix(root)
                    .expect("file is inside source")
                    .to_path_buf(),
                fs::read(path).expect("source file bytes are readable"),
            );
        }
    }
}
