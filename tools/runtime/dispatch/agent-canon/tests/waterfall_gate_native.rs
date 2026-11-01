// @dependency-start
// contract test
// responsibility Replays frozen historical Waterfall CLI outputs and report inputs through the native command.
// upstream implementation ../src/waterfall_gate.rs owns gate behavior
// upstream implementation ../src/active_design_packet.rs owns active packet normalization and mapping
// upstream implementation ../src/runtime_boundary.rs owns no-follow bundle reads
// upstream test ../../../../../tests/fixtures/waterfall_gate/python_golden.jsonl freezes old Python CLI records
// @dependency-end

use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs;
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

const PYTHON_GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/waterfall_gate/python_golden.jsonl");
const PYTHON_GOLDEN_SHA256: &str =
    "abb08d9859fa061f15b0bc889ee5990e84263fdbf08f5b9edeeab351a356e070";
const OLD_SOURCE_COMMIT: &str = "c3a202e66d7b7019d90a7715ce2b2c1152a8b117";
const OLD_SOURCE_TREE: &str = "47fc5e7e6ed780f7a342670d57f9c1593eb13501";

static NEXT_FIXTURE: AtomicU64 = AtomicU64::new(0);

struct Fixture(PathBuf);

impl Fixture {
    fn new(label: &str) -> Self {
        let temp_root = std::env::var_os("AGENT_CANON_RUNTIME_ROOT")
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir);
        let path = temp_root.join(format!(
            "agent-canon-waterfall-{label}-{}-{}",
            std::process::id(),
            NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).expect("create Waterfall fixture root");
        Self(fs::canonicalize(path).expect("resolve Waterfall fixture root"))
    }

    fn case_root(&self) -> &Path {
        &self.0
    }

    fn report_root(&self) -> PathBuf {
        self.0.join("reports")
    }

    fn report_dir(&self, case_id: &str) -> PathBuf {
        self.report_root().join(case_id)
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn json_string<'a>(value: &'a Value, field: &str) -> &'a str {
    value[field]
        .as_str()
        .unwrap_or_else(|| panic!("golden field {field} must be a string"))
}

fn safe_relative_path(value: &str) -> PathBuf {
    let path = Path::new(value);
    assert!(
        !path.is_absolute(),
        "golden report path must be relative: {value}"
    );
    for component in path.components() {
        assert!(
            matches!(component, Component::Normal(_)),
            "golden report path must not traverse directories: {value}"
        );
    }
    path.to_path_buf()
}

fn create_directories_nofollow(root: &Path, relative: &Path) {
    let mut current = root.to_path_buf();
    for component in relative.components() {
        let Component::Normal(name) = component else {
            panic!("only normal components are allowed in fixture paths")
        };
        current.push(name);
        match fs::symlink_metadata(&current) {
            Ok(metadata) => assert!(
                metadata.is_dir() && !metadata.file_type().is_symlink(),
                "fixture parent is not a real directory: {}",
                current.display()
            ),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                fs::create_dir(&current).expect("create fixture directory");
            }
            Err(error) => panic!("inspect fixture directory {}: {error}", current.display()),
        }
    }
}

fn expected_link_target_is_directory(manifest: &[Value], link_path: &str, target: &str) -> bool {
    let target_path = Path::new(target);
    if target_path.is_absolute() {
        return false;
    }
    let parent = Path::new(link_path)
        .parent()
        .unwrap_or_else(|| Path::new(""));
    let joined = parent.join(target_path);
    let mut normalized = PathBuf::new();
    for component in joined.components() {
        match component {
            Component::Normal(name) => normalized.push(name),
            Component::CurDir => {}
            Component::ParentDir => {
                if !normalized.pop() {
                    return false;
                }
            }
            Component::RootDir | Component::Prefix(_) => return false,
        }
    }
    let normalized = normalized.to_string_lossy().replace('\\', "/");
    manifest.iter().any(|entry| {
        entry["kind"].as_str() == Some("directory")
            && entry["path"].as_str() == Some(normalized.as_str())
    })
}

#[cfg(unix)]
fn create_symlink(target: &str, link: &Path, _is_directory: bool) -> std::io::Result<()> {
    std::os::unix::fs::symlink(target, link)
}

#[cfg(windows)]
fn create_symlink(target: &str, link: &Path, is_directory: bool) -> std::io::Result<()> {
    if is_directory {
        std::os::windows::fs::symlink_dir(target, link)
    } else {
        std::os::windows::fs::symlink_file(target, link)
    }
}

fn materialize_report(report_dir: &Path, manifest: &[Value]) {
    fs::create_dir_all(report_dir).expect("create report fixture directory");
    for entry in manifest
        .iter()
        .filter(|entry| entry["kind"].as_str() == Some("directory"))
    {
        let relative = safe_relative_path(json_string(entry, "path"));
        if let Some(parent) = relative.parent() {
            create_directories_nofollow(report_dir, parent);
        }
        create_directories_nofollow(report_dir, &relative);
    }
    for entry in manifest
        .iter()
        .filter(|entry| entry["kind"].as_str() == Some("file"))
    {
        let relative = safe_relative_path(json_string(entry, "path"));
        let target = report_dir.join(&relative);
        if let Some(parent) = relative.parent() {
            create_directories_nofollow(report_dir, parent);
        }
        let bytes = STANDARD
            .decode(json_string(entry, "content_base64"))
            .expect("frozen report file content is base64");
        assert_eq!(
            bytes.len() as u64,
            entry["size_bytes"].as_u64().expect("file size is numeric")
        );
        assert_eq!(
            sha256_hex(&bytes),
            json_string(entry, "sha256"),
            "frozen input digest differs for {}",
            relative.display()
        );
        fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&target)
            .expect("create regular report fixture file")
            .write_all(&bytes)
            .expect("write report fixture bytes");
    }
    for entry in manifest
        .iter()
        .filter(|entry| entry["kind"].as_str() == Some("symlink"))
    {
        let relative = safe_relative_path(json_string(entry, "path"));
        let target = report_dir.join(&relative);
        if let Some(parent) = relative.parent() {
            create_directories_nofollow(report_dir, parent);
        }
        let link_target = json_string(entry, "target");
        let is_directory =
            expected_link_target_is_directory(manifest, json_string(entry, "path"), link_target);
        create_symlink(link_target, &target, is_directory).unwrap_or_else(|error| {
            panic!("create recorded symlink {}: {error}", target.display())
        });
    }
    assert_eq!(
        manifest.len(),
        manifest
            .iter()
            .filter(|entry| matches!(
                entry["kind"].as_str(),
                Some("directory" | "file" | "symlink")
            ))
            .count(),
        "frozen report manifest includes only supported entry kinds"
    );
}

fn snapshot_report(root: &Path) -> Vec<Value> {
    fn walk(root: &Path, current: &Path, entries: &mut Vec<Value>) {
        let mut children = fs::read_dir(current)
            .unwrap_or_else(|error| panic!("read report directory {}: {error}", current.display()))
            .map(|entry| entry.expect("read report entry").path())
            .collect::<Vec<_>>();
        children.sort();
        for path in children {
            let relative = path
                .strip_prefix(root)
                .expect("report entry stays below fixture root")
                .to_string_lossy()
                .replace('\\', "/");
            let metadata = fs::symlink_metadata(&path)
                .unwrap_or_else(|error| panic!("inspect report entry {}: {error}", path.display()));
            if metadata.file_type().is_symlink() {
                let target = fs::read_link(&path)
                    .unwrap_or_else(|error| panic!("read symlink {}: {error}", path.display()));
                entries.push(serde_json::json!({
                    "path": relative,
                    "kind": "symlink",
                    "target": target.to_string_lossy(),
                }));
            } else if metadata.is_dir() {
                entries.push(serde_json::json!({"path": relative, "kind": "directory"}));
                walk(root, &path, entries);
            } else if metadata.is_file() {
                let bytes = fs::read(&path).unwrap_or_else(|error| {
                    panic!("read fixture file {}: {error}", path.display())
                });
                entries.push(serde_json::json!({
                    "path": relative,
                    "kind": "file",
                    "size_bytes": bytes.len(),
                    "sha256": sha256_hex(&bytes),
                    "content_base64": STANDARD.encode(bytes),
                }));
            } else {
                panic!("unsupported report fixture type: {}", path.display());
            }
        }
    }
    let mut entries = Vec::new();
    walk(root, root, &mut entries);
    entries.sort_by(|left, right| left["path"].as_str().cmp(&right["path"].as_str()));
    entries
}

fn fixture_target(token: &str, fixture: &Fixture, report_dir: &Path, source_root: &Path) -> String {
    match token {
        "<CASE_ROOT>" => fixture.case_root().display().to_string(),
        "<REPORT_ROOT>" => fixture.report_root().display().to_string(),
        "<REPORT_DIR>" => report_dir.display().to_string(),
        "<SOURCE_ROOT>" => source_root.display().to_string(),
        other => panic!("unknown fixture path token: {other}"),
    }
}

fn remap_captured_stdout(
    record: &Value,
    fixture: &Fixture,
    report_dir: &Path,
    source_root: &Path,
) -> String {
    let mut expected = json_string(&record["observed"], "stdout").to_owned();
    let mappings = record["path_context_mapping"]["mappings"]
        .as_array()
        .expect("frozen path mappings are an array");
    for mapping in mappings {
        expected = expected.replace(
            json_string(mapping, "source_prefix"),
            &fixture_target(
                json_string(mapping, "fixture_token"),
                fixture,
                report_dir,
                source_root,
            ),
        );
    }
    expected
}

#[test]
fn waterfall_python_cli_corpus_bytes_remain_frozen() {
    assert_eq!(sha256_hex(PYTHON_GOLDEN.as_bytes()), PYTHON_GOLDEN_SHA256);
}

#[test]
fn waterfall_python_cli_corpus_replays_through_native_gate() {
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../../")
        .canonicalize()
        .expect("resolve AgentCanon source root");
    let records = PYTHON_GOLDEN
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).expect("each frozen line is JSON"))
        .collect::<Vec<_>>();
    let source = records
        .iter()
        .find(|record| record["record_type"] == "waterfall_old_source_snapshot")
        .expect("frozen source record exists");
    assert_eq!(json_string(source, "git_commit"), OLD_SOURCE_COMMIT);
    assert_eq!(json_string(source, "git_tree"), OLD_SOURCE_TREE);
    let summary = records
        .iter()
        .find(|record| record["record_type"] == "waterfall_old_oracle_summary")
        .expect("frozen summary record exists");
    assert_eq!(summary["passed"], true);
    assert_eq!(summary["case_count"].as_u64(), Some(13));
    let cases = records
        .iter()
        .filter(|record| record["record_type"] == "waterfall_gate_cli_case")
        .collect::<Vec<_>>();
    assert_eq!(cases.len(), 13);

    for record in cases {
        assert_eq!(record["passed"], true, "historical case is accepted");
        assert_eq!(
            record["checks"]["report_tree_unchanged"], true,
            "historical CLI preserved the input tree"
        );
        assert_eq!(
            record["input_manifest"], record["post_action_manifest"],
            "frozen historical before/after report manifests match"
        );
        let case_id = json_string(record, "case_id");
        let fixture = Fixture::new(case_id);
        let report_dir = fixture.report_dir(case_id);
        materialize_report(
            &report_dir,
            record["input_manifest"]
                .as_array()
                .expect("frozen input manifest is a list"),
        );
        let before = snapshot_report(&report_dir);
        assert_eq!(
            before, record["input_manifest"],
            "materialized bytes match corpus"
        );

        let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
            .arg("waterfall-gate-check")
            .arg("--report-dir")
            .arg(&report_dir)
            .arg("--gate")
            .arg(json_string(record, "gate"))
            .current_dir(&repo_root)
            .env("AGENT_CANON_SOURCE_ROOT", &repo_root)
            .output()
            .expect("run native Waterfall CLI");
        let expected_status = record["expected"]["returncode"]
            .as_i64()
            .expect("frozen expected status is numeric");
        assert_eq!(
            output.status.code(),
            Some(expected_status as i32),
            "case {case_id}"
        );
        let actual_stdout = String::from_utf8(output.stdout).expect("native stdout is UTF-8");
        let actual_stderr = String::from_utf8(output.stderr).expect("native stderr is UTF-8");
        assert_eq!(
            actual_stdout,
            remap_captured_stdout(record, &fixture, &report_dir, &repo_root),
            "case {case_id} stdout differs from historical CLI"
        );
        assert_eq!(
            actual_stderr,
            json_string(&record["observed"], "stderr"),
            "case {case_id} stderr differs from historical CLI"
        );
        for expected_token in record["expected"]["stdout_contains"]
            .as_array()
            .expect("frozen output tokens are a list")
        {
            let expected_token = expected_token.as_str().expect("output token is text");
            assert!(
                actual_stdout.contains(expected_token),
                "case {case_id}: {expected_token}"
            );
        }
        let after = snapshot_report(&report_dir);
        assert_eq!(
            after, before,
            "native gate mutated report input for {case_id}"
        );
    }
}
