// @dependency-start
// contract test
// responsibility Verifies native run-path comparison, machine status, report rendering, exit codes, and Unicode boundaries against the frozen CPython CLI oracle.
// upstream implementation ../src/compare_agent_run_paths.rs owns run-path token parsing and report semantics.
// upstream implementation ../src/path_resolution.rs owns non-strict physical path resolution.
// upstream test ../../../../../tests/fixtures/compare_agent_run_paths/python_golden.json freezes the independent oracle.
// @dependency-end

use agent_canon::compare_agent_run_paths::{
    compare_agent_run_paths, render_machine_status, render_report,
};
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/compare_agent_run_paths/python_golden.json");
const OLD_REPORT_SOURCE: &str = "../../eval/checkers/compare_agent_run_paths.py";
const NATIVE_REPORT_SOURCE: &str =
    "../../tools/runtime/dispatch/agent-canon/src/compare_agent_run_paths.rs";
static NEXT_TEMP_DIRECTORY: AtomicU64 = AtomicU64::new(0);

struct TempDirectory(PathBuf);

impl TempDirectory {
    fn new(label: &str) -> Self {
        let sequence = NEXT_TEMP_DIRECTORY.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-run-path-comparison-{}-{sequence}-{label}",
            std::process::id()
        ));
        fs::create_dir(&path).expect("unique run-path test directory is created");
        Self(path)
    }
}

impl Drop for TempDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn field<'a>(value: &'a Value, key: &str) -> &'a Value {
    value.get(key).expect("frozen run-path field is present")
}

fn text(value: &Value) -> &str {
    value.as_str().expect("frozen run-path value is text")
}

fn write_run(root: &Path, name: &str, content: Option<&str>) -> PathBuf {
    let run = root.join(name);
    fs::create_dir_all(&run).expect("run bundle directory is created");
    if let Some(content) = content {
        fs::write(run.join("workflow_monitoring.md"), content)
            .expect("workflow monitoring input is written");
    }
    run
}

fn report_oracle(case: &Value, baseline: &Path, candidate: &Path) -> String {
    let mut report = text(field(case, "report")).to_owned();
    let old_baseline = text(field(case, "baseline_path"));
    let old_candidate = text(field(case, "candidate_path"));
    let baseline = baseline.display().to_string();
    let candidate = candidate.display().to_string();
    assert_eq!(
        report.matches(old_baseline).count(),
        1,
        "baseline path mapping"
    );
    assert_eq!(
        report.matches(old_candidate).count(),
        1,
        "candidate path mapping"
    );
    assert_eq!(
        report.matches(OLD_REPORT_SOURCE).count(),
        1,
        "native source header mapping"
    );
    report = report.replace(old_baseline, &baseline);
    report = report.replace(old_candidate, &candidate);
    report.replace(OLD_REPORT_SOURCE, NATIVE_REPORT_SOURCE)
}

#[test]
fn run_path_comparison_matches_all_frozen_cpython_cli_cases() {
    let golden: Value =
        serde_json::from_str(GOLDEN).expect("frozen CPython run-path CLI oracle parses");
    let cases = field(&golden, "cases")
        .as_array()
        .expect("frozen run-path cases are an array");
    assert_eq!(cases.len(), 10);

    let mut passed = 0;
    let mut failed = 0;
    for case in cases {
        let name = text(field(case, "name"));
        let temporary = TempDirectory::new(name);
        let baseline = write_run(
            &temporary.0,
            "baseline",
            field(case, "baseline_text").as_str(),
        );
        let candidate = write_run(
            &temporary.0,
            "candidate",
            field(case, "candidate_text").as_str(),
        );
        let expected_baseline =
            fs::canonicalize(&baseline).expect("test-created baseline directory resolves");
        let expected_candidate =
            fs::canonicalize(&candidate).expect("test-created candidate directory resolves");
        let comparison = compare_agent_run_paths(&baseline, &candidate)
            .expect("frozen UTF-8 inputs yield a comparison");
        assert_eq!(
            comparison.baseline.path.as_path(),
            expected_baseline.as_path(),
            "baseline input path for {name}"
        );
        assert_eq!(
            comparison.candidate.path.as_path(),
            expected_candidate.as_path(),
            "candidate input path for {name}"
        );
        let expected_exit = field(case, "exit")
            .as_i64()
            .expect("frozen CLI exit code is an integer") as i32;
        if expected_exit == 0 {
            passed += 1;
        } else {
            failed += 1;
        }
        assert_eq!(
            comparison.exit_code(),
            expected_exit,
            "exit code for {name}"
        );
        assert_eq!(
            render_machine_status(&comparison),
            text(field(case, "stdout")),
            "stdout for {name}"
        );
        assert_eq!(text(field(case, "stderr")), "", "stderr for {name}");
        assert_eq!(
            render_report(&comparison),
            report_oracle(case, &expected_baseline, &expected_candidate),
            "report for {name}"
        );
    }
    assert_eq!(passed, 5);
    assert_eq!(failed, 5);
}
