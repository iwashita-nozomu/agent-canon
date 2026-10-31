// @dependency-start
// contract test
// responsibility Preserves Git diff parsing, source-language selection, external summary artifacts, and CLI schema.
// upstream implementation ../src/git_dependency_diff_summary.rs owns diff and report behavior
// upstream implementation ../src/scip_index.rs owns optional native SCIP impact
// upstream implementation ../src/runtime_boundary.rs owns external report paths
// @dependency-end

use agent_canon::git_dependency_diff_summary::{
    changed_file_list, parse_name_status, parse_name_status_z, parse_numstat, parse_numstat_z,
    scip_target_paths, ChangedPath,
};
#[cfg(unix)]
use agent_canon::git_dependency_diff_summary::{collect_changed_paths, DiffSpec};
use serde_json::Value;
use std::ffi::{OsStr, OsString};
use std::fs;
#[cfg(unix)]
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(0);

struct Fixture(PathBuf);

impl Fixture {
    fn new() -> Self {
        let sequence = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!(
            "agent-canon-git-summary-native-{}-{sequence}",
            std::process::id()
        ));
        fs::create_dir_all(&root).expect("create Git summary fixture root");
        let root = fs::canonicalize(root).expect("resolve Git summary fixture root");
        fs::create_dir_all(root.join("source")).expect("create source fixture root");
        fs::create_dir_all(root.join("runtime")).expect("create runtime fixture root");
        Self(root)
    }

    fn source(&self) -> PathBuf {
        self.0.join("source")
    }

    fn runtime(&self) -> PathBuf {
        self.0.join("runtime")
    }

    fn report(&self) -> PathBuf {
        self.runtime().join("report")
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn git(root: &Path, args: &[&str]) -> Output {
    Command::new("git")
        .args(args)
        .current_dir(root)
        .output()
        .expect("Git fixture command runs")
}

fn init_repository(root: &Path) {
    assert!(git(root, &["init", "-q"]).status.success());
    assert!(git(root, &["config", "user.email", "test@example.com"])
        .status
        .success());
    assert!(git(root, &["config", "user.name", "Test User"])
        .status
        .success());
}

fn commit_paths(root: &Path, message: &str, paths: &[&str]) {
    let mut add = vec!["add", "--"];
    add.extend(paths.iter().copied());
    assert!(git(root, &add).status.success());
    assert!(git(root, &["commit", "-m", message]).status.success());
}

#[cfg(unix)]
fn add_native_path(root: &Path, path: &OsStr) {
    let output = Command::new("git")
        .args(["add", "--"])
        .arg(path)
        .current_dir(root)
        .output()
        .expect("Git can add a native path");
    assert!(output.status.success(), "Git adds the native path");
}

fn summary_cli(fixture: &Fixture, extra: &[&str]) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_agent-canon"));
    command.args([
        "git-dependency-diff-summary",
        "--root",
        fixture.source().to_str().expect("fixture root is UTF-8"),
        "--report-dir",
        fixture.report().to_str().expect("report path is UTF-8"),
        "--runtime-root",
        fixture.runtime().to_str().expect("runtime path is UTF-8"),
    ]);
    command.args(extra);
    command
        .output()
        .expect("current native agent-canon executable runs")
}

fn summary_json(output: &Output) -> Value {
    serde_json::from_slice(&output.stdout).expect("native summary output is JSON")
}

fn changed(status: &str, path: &str, old_path: Option<&str>) -> ChangedPath {
    ChangedPath {
        status: status.to_string(),
        path: OsString::from(path),
        old_path: old_path.map(OsString::from),
        additions: None,
        deletions: None,
        binary: false,
        exists_in_worktree: true,
    }
}

#[test]
fn parse_name_status_keeps_rename_source() {
    let rows = parse_name_status("M\talpha.py\nR100\told.py\tnew.py\n");

    assert_eq!(rows[0].status, "M");
    assert_eq!(rows[0].path, OsString::from("alpha.py"));
    assert_eq!(rows[1].status, "R100");
    assert_eq!(rows[1].old_path.as_deref(), Some(OsStr::new("old.py")));
    assert_eq!(rows[1].path, OsString::from("new.py"));
}

#[test]
fn parse_name_status_z_preserves_tab_in_path() {
    let rows = parse_name_status_z(b"M\0tab\tname.py\0");

    assert_eq!(rows[0].status, "M");
    assert_eq!(rows[0].path, OsString::from("tab\tname.py"));
}

#[test]
fn parse_numstat_handles_binary_rows() {
    let stats = parse_numstat("3\t4\talpha.py\n-\t-\timage.bin\n1\t0\told.py => new.py\n")
        .expect("valid Git text numstat parses");

    assert_eq!(
        stats.get(&OsString::from("alpha.py")).copied(),
        Some((Some(3), Some(4), false))
    );
    assert_eq!(
        stats.get(&OsString::from("image.bin")).copied(),
        Some((None, None, true))
    );
    assert_eq!(
        stats.get(&OsString::from("new.py")).copied(),
        Some((Some(1), Some(0), false))
    );
}

#[test]
fn parse_numstat_z_keys_renames_by_current_path() {
    let stats = parse_numstat_z(b"1\t0\t\0old.py\0new.py\0")
        .expect("valid NUL-delimited rename numstat parses");

    assert_eq!(
        stats.get(&OsString::from("new.py")).copied(),
        Some((Some(1), Some(0), false))
    );
    assert!(!stats.contains_key(&OsString::from("old.py")));
}

#[test]
fn parse_numstat_z_preserves_tab_in_path() {
    let stats = parse_numstat_z(b"2\t1\ttab\tname.py\0")
        .expect("valid NUL-delimited tab path numstat parses");

    assert_eq!(
        stats.get(&OsString::from("tab\tname.py")).copied(),
        Some((Some(2), Some(1), false))
    );
}

#[test]
fn changed_file_list_includes_rename_source() {
    let rows = [changed("R100", "new.py", Some("old.py"))];

    assert_eq!(
        changed_file_list(&rows),
        vec![OsString::from("new.py"), OsString::from("old.py")]
    );
}

#[test]
fn scip_targets_include_recognized_old_and_new_source_suffixes() {
    let rows = [
        changed("M", "main.rs", None),
        changed("D", "old.py", None),
        changed("M", "typing.pyi", None),
        changed("M", "native.cxx", None),
        changed("M", "include/native.hxx", None),
        changed("R100", "current.rs", Some("previous.rs")),
    ];

    assert_eq!(
        scip_target_paths(&rows),
        vec![
            OsString::from("current.rs"),
            OsString::from("include/native.hxx"),
            OsString::from("main.rs"),
            OsString::from("native.cxx"),
            OsString::from("old.py"),
            OsString::from("previous.rs"),
            OsString::from("typing.pyi"),
        ]
    );
}

#[test]
fn cli_summarizes_worktree_diff_as_json() {
    let fixture = Fixture::new();
    init_repository(&fixture.source());
    fs::write(fixture.source().join("alpha.py"), "value = 1\n").unwrap();
    commit_paths(&fixture.source(), "initial", &["alpha.py"]);
    fs::write(fixture.source().join("alpha.py"), "value = 2\n").unwrap();
    fs::write(fixture.source().join("beta.py"), "import alpha\n").unwrap();

    let output = summary_cli(&fixture, &["--skip-dependency-review", "--format", "json"]);

    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let payload = summary_json(&output);
    assert_eq!(
        payload["schema"],
        "agent_canon.git_dependency_diff_summary.v2"
    );
    assert_eq!(
        payload["changed_files"]
            .as_array()
            .unwrap()
            .iter()
            .map(|row| row["path"].as_str().unwrap())
            .collect::<std::collections::BTreeSet<_>>(),
        ["alpha.py", "beta.py"].into_iter().collect()
    );
    let impact_path = PathBuf::from(payload["artifacts"]["scip_impact"].as_str().unwrap());
    let impact: Value = serde_json::from_slice(&fs::read(impact_path).unwrap()).unwrap();
    assert_eq!(impact["status"], "not-selected");
    assert!(payload["artifacts"].get("code_dependencies").is_none());
    assert!(fixture.report().join("summary.md").is_file());
}

#[test]
fn cli_preserves_rename_stats_and_seed_paths() {
    let fixture = Fixture::new();
    init_repository(&fixture.source());
    fs::write(fixture.source().join("old.py"), "value = 1\n").unwrap();
    commit_paths(&fixture.source(), "initial", &["old.py"]);
    assert!(git(&fixture.source(), &["mv", "old.py", "new.py"])
        .status
        .success());
    fs::write(fixture.source().join("new.py"), "value = 1\nextra = 2\n").unwrap();

    let output = summary_cli(
        &fixture,
        &[
            "--skip-scip-impact",
            "--skip-dependency-review",
            "--format",
            "json",
        ],
    );

    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let payload = summary_json(&output);
    let row = &payload["changed_files"][0];
    assert!(row["status"].as_str().unwrap().starts_with('R'));
    assert_eq!(row["old_path"], "old.py");
    assert_eq!(row["path"], "new.py");
    assert_eq!(row["additions"], 1);
    assert_eq!(row["deletions"], 0);
    let changed_paths = fs::read_to_string(fixture.report().join("changed_files.txt")).unwrap();
    assert_eq!(
        changed_paths.lines().collect::<Vec<_>>(),
        ["new.py", "old.py"]
    );
}

#[test]
fn cli_preserves_tab_path_stats() {
    let fixture = Fixture::new();
    init_repository(&fixture.source());
    let path = fixture.source().join("tab\tname.py");
    fs::write(&path, "value = 1\n").unwrap();
    commit_paths(&fixture.source(), "initial", &["tab\tname.py"]);
    fs::write(&path, "value = 1\nextra = 2\n").unwrap();

    let output = summary_cli(
        &fixture,
        &[
            "--skip-scip-impact",
            "--skip-dependency-review",
            "--format",
            "json",
        ],
    );

    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let payload = summary_json(&output);
    let row = &payload["changed_files"][0];
    assert_eq!(row["path"], "tab\tname.py");
    assert_eq!(row["additions"], 1);
    assert_eq!(row["deletions"], 0);
}

#[cfg(unix)]
#[test]
fn nul_parsers_preserve_invalid_utf8_rename_identity_and_numstat_key() {
    let old_path = OsString::from_vec(b"old-\xff.py".to_vec());
    let current_path = OsString::from_vec(b"new-\xfe.py".to_vec());
    let mut names = b"R100\0".to_vec();
    names.extend_from_slice(old_path.as_bytes());
    names.push(0);
    names.extend_from_slice(current_path.as_bytes());
    names.push(0);

    let rows = parse_name_status_z(&names);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].status, "R100");
    assert_eq!(
        rows[0].old_path.as_deref().unwrap().as_bytes(),
        old_path.as_bytes()
    );
    assert_eq!(rows[0].path.as_bytes(), current_path.as_bytes());

    let mut numstat = b"3\t1\t\0".to_vec();
    numstat.extend_from_slice(old_path.as_bytes());
    numstat.push(0);
    numstat.extend_from_slice(current_path.as_bytes());
    numstat.push(0);
    let stats = parse_numstat_z(&numstat).expect("NUL numstat retains raw rename paths");

    assert_eq!(
        stats.get(&current_path).copied(),
        Some((Some(3), Some(1), false))
    );
    assert!(!stats.contains_key(&old_path));
}

#[cfg(unix)]
#[test]
fn cli_fails_at_changed_file_utf8_boundary_before_report_or_provider_writes() {
    let fixture = Fixture::new();
    let source = fixture.source();
    init_repository(&source);
    let raw_path = OsString::from_vec(b"tracked-\xff.py".to_vec());
    if let Err(error) = fs::write(source.join(&raw_path), "before\n") {
        #[cfg(target_os = "macos")]
        if error.raw_os_error() == Some(92) {
            println!(
                "filesystem-bound CLI oracle unavailable: macOS rejected the raw filename with EILSEQ (errno 92)"
            );
            return;
        }
        panic!("create raw-byte Git fixture path: {error}");
    }
    add_native_path(&source, &raw_path);
    assert!(git(&source, &["commit", "-m", "initial"]).status.success());
    fs::write(source.join(&raw_path), "after\n").unwrap();

    let rows = collect_changed_paths(
        &source,
        &DiffSpec {
            base: "HEAD".to_string(),
            head: String::new(),
            paths: Vec::new(),
        },
    )
    .expect("Git paths retain native bytes through diff and numstat matching");
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].path.as_bytes(), raw_path.as_bytes());
    assert!(rows[0].exists_in_worktree);
    assert_eq!((rows[0].additions, rows[0].deletions), (Some(1), Some(1)));
    assert_eq!(changed_file_list(&rows), vec![raw_path.clone()]);
    assert_eq!(scip_target_paths(&rows), vec![raw_path]);

    let output = summary_cli(&fixture, &["--format", "json"]);

    assert_eq!(output.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("GIT_DEPENDENCY_DIFF_SUMMARY=fail"));
    assert!(stderr.contains("GIT_DEPENDENCY_DIFF_SUMMARY_ERROR="));
    assert!(output.stdout.is_empty());
    assert!(fixture.report().is_dir());
    assert!(!fixture.report().join("changed_files.txt").exists());
    assert!(!fixture.report().join("git_stat.txt").exists());
    assert!(!fixture.report().join("scip_impact.json").exists());
    assert!(!fixture.report().join("dependency-review").exists());
    assert!(!fixture.report().join("summary.json").exists());
    assert!(!fixture.report().join("summary.md").exists());
}
