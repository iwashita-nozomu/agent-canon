// @dependency-start
// contract test
// responsibility Verifies the managed experiment CLI, immutable snapshot publication, provider protocol, and terminal artifacts.
// upstream implementation ../src/managed_experiment.rs owns the composition and external admitted-runner handshake
// upstream implementation ../src/execution_source_freeze.rs owns the sole source_snapshot.json writer
// upstream implementation ../src/execution_resource_plan.rs owns source and GPU admission evidence
// @dependency-end

use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use tempfile::TempDir;

struct Fixture {
    _temporary: TempDir,
    root: PathBuf,
    provider: PathBuf,
}

fn build_fixture() -> Fixture {
    let temporary = tempfile::tempdir().expect("temporary managed fixture");
    let root = fs::canonicalize(temporary.path()).expect("fixture root resolves");
    fs::create_dir_all(root.join("experiments/demo_topic/result")).expect("result directory");
    fs::create_dir_all(root.join("experiments/demo_topic/report")).expect("report directory");
    fs::write(
        root.join("experiments/registry.toml"),
        "schema_version = 1\n\n[defaults]\nrequired_eval_artifacts = [\"summary/summary.json\", \"summary/cases.jsonl\"]\n\n[[topics]]\nname = \"demo_topic\"\nstatus = \"active\"\ntopic_dir = \"experiments/demo_topic\"\ncanonical_entrypoint = \"experiments/demo_topic/run.py\"\nresult_root = \"experiments/demo_topic/result\"\nreport_root = \"experiments/demo_topic/report\"\ndefault_variant = \"formal\"\ndefault_inner_command = \"python3 experiments/demo_topic/run.py --config {config_path}\"\nformal_inner_command = \"python3 experiments/demo_topic/run.py --config {config_path}\"\n",
    )
    .expect("registry fixture writes");
    fs::write(root.join("experiments/demo_topic/config.yaml"), "seed: 7\n")
        .expect("source config fixture writes");
    fs::write(
        root.join("experiments/demo_topic/run.py"),
        "def main():\n    return 0\n",
    )
    .expect("topic entrypoint fixture writes");
    let git = |args: &[&str]| {
        let output = Command::new("git")
            .args(args)
            .current_dir(&root)
            .output()
            .expect("git command starts");
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
    };
    git(&["init", "--quiet"]);
    git(&["config", "user.name", "Managed Test"]);
    git(&["config", "user.email", "managed@example.invalid"]);
    git(&["add", "experiments"]);
    git(&["commit", "--quiet", "-m", "fixture"]);

    let provider = root.join("fake-experiment-runner-admitted");
    fs::write(
        &provider,
        r##"#!/usr/bin/env python3
import json, os, sys
args = sys.argv
request = json.load(open(args[args.index('--request') + 1], encoding='utf-8'))
result_path = args[args.index('--result') + 1]
assert os.getcwd() == request['metadata']['agentcanon_working_directory']
assert os.environ['EXPERIMENT_RUN_DIR'] == request['metadata']['agentcanon_output_directory']
open(os.path.join(request['metadata']['agentcanon_output_directory'], 'fixture-provider-called'), 'a').write('called\n')
pid = os.getpid()
mode = os.environ.get('MANAGED_FIXTURE_MODE', 'valid')
lifecycle = {
    'run_id': request['run_id'], 'terminal_event_id': 'terminal-1',
    'observed_at_ns': 1, 'terminal_status': 'finished',
    'total_case_count_at_start': 1, 'completion_count_before': 0,
    'completion_count_after': 1, 'scheduler_completed': True,
    'admitted_case_count': 1, 'terminal_notification_count': 1,
    'child_process_ids': [pid], 'process_group_ids': [pid],
    'direct_children_quiescent': True, 'descendant_quiescence': 'proved',
    'cleanup_failures': [], 'terminal_coverage_complete': True,
    'requested_case_coverage_complete': True, 'quiescence_complete': True,
    'completion_coverage_complete': True,
}
result = {
    'schema': 'agentcanon-managed-run-result/v1',
    'identity': request['identity'], 'run_id': request['run_id'],
    'request_fingerprint': '0' * 64 if mode == 'bad-fingerprint' else request['fingerprint'],
    'status': 'ok', 'worker_pid': pid, 'worker_pids': [pid],
    'lifecycle': lifecycle, 'descendant_quiescence': 'proved',
    'quiescence': {'direct_children_quiescent': True,
        'descendant_quiescence': 'proved', 'complete': True, 'cleanup_failures': []},
    'exit': {'code': 0, 'error': None}, 'exit_code': 0, 'error': None,
    'completions': [{'case': {}, 'result': {'status': 'ok'}}],
}
if mode == 'bad-schema': result['schema'] = 'agentcanon-managed-run-result/v2'
if mode == 'bad-run-id': result['run_id'] = 'other-run'
if mode == 'bad-identity': result['identity']['run_name'] = 'other-run'
if mode == 'unproven-completion': lifecycle['completion_coverage_complete'] = False
json.dump(result, open(result_path, 'w', encoding='utf-8'))
"##,
    )
    .expect("provider protocol double writes");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&provider, fs::Permissions::from_mode(0o755))
            .expect("provider protocol double is executable");
    }
    Fixture {
        _temporary: temporary,
        root,
        provider,
    }
}

fn run(fixture: &Fixture, name: &str, mode: &str) -> Output {
    run_paths(&fixture.root, &fixture.provider, name, mode)
}

fn run_paths(root: &Path, provider: &Path, name: &str, mode: &str) -> Output {
    Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "run-managed-experiment",
            "--repo-root",
            root.to_str().unwrap(),
            "--topic",
            "demo_topic",
            "--variant",
            "formal",
            "--run-name",
            name,
            "--",
            "python3",
            "experiments/demo_topic/run.py",
            "--config",
            "{config_path}",
        ])
        .env("AGENT_CANON_EXPERIMENT_RUNNER_ADMITTED", provider)
        .env("MANAGED_FIXTURE_MODE", mode)
        .output()
        .expect("native managed command starts")
}

fn result_dir(fixture: &Fixture, run_name: &str) -> PathBuf {
    fixture
        .root
        .join("experiments/demo_topic/result")
        .join(run_name)
}

#[test]
fn managed_cli_freezes_source_once_and_publishes_provider_receipts() {
    let fixture = build_fixture();
    let output = run(&fixture, "managed-success", "valid");
    assert_eq!(
        output.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let result = result_dir(&fixture, "managed-success");
    assert!(result.join("source_snapshot.json").is_file());
    assert!(result
        .join("source_snapshot/experiments/demo_topic/run.py")
        .is_file());
    assert!(result.join("raw").is_dir());
    assert!(result.join("config_source.yaml").is_file());
    assert!(result.join("runtime/managed-run-request.json").is_file());
    assert!(result.join("runtime/managed-run-result.json").is_file());
    assert!(result.join("runtime/managed-run-lifecycle.json").is_file());
    assert!(result.join("runtime/managed-run-receipt.json").is_file());
    assert!(result.join("runtime/completion_coverage.json").is_file());
    assert!(result
        .join("runtime/post_tool_use_projection.json")
        .is_file());
    assert!(fixture
        .root
        .join("experiments/demo_topic/report/managed-success.md")
        .is_file());
    assert_eq!(
        fs::read_to_string(result.join("fixture-provider-called")).unwrap(),
        "called\n"
    );
    let request: Value =
        serde_json::from_slice(&fs::read(result.join("runtime/managed-run-request.json")).unwrap())
            .unwrap();
    assert_eq!(request["schema"], "agentcanon-managed-run/v1");
    assert_eq!(
        request["cases"][0]["entrypoint_relative_path"],
        "experiments/demo_topic/run.py"
    );
    let environment: Value =
        serde_json::from_slice(&fs::read(result.join("environment.json")).unwrap()).unwrap();
    assert_eq!(
        environment["values"]["EXPERIMENT_RUN_DIR"],
        result.to_string_lossy().as_ref()
    );
    assert_eq!(
        environment["values"]["EXPERIMENT_RAW_DIR"],
        result.join("raw").to_string_lossy().as_ref()
    );
    let manifest: Value =
        serde_json::from_slice(&fs::read(result.join("run_manifest.json")).unwrap()).unwrap();
    assert_eq!(
        manifest["raw_artifacts"]["path"],
        "experiments/demo_topic/result/managed-success/raw"
    );
    let receipt: Value =
        serde_json::from_slice(&fs::read(result.join("runtime/managed-run-receipt.json")).unwrap())
            .unwrap();
    assert_eq!(receipt["identity"]["run_name"], "managed-success");
    assert_eq!(receipt["request_fingerprint"], request["fingerprint"]);
    assert!(!String::from_utf8_lossy(&output.stderr).contains("runtime_receipt_publish_failed"));
}

#[test]
fn provider_fingerprint_mismatch_fails_closed_after_recording_terminal_coverage() {
    let fixture = build_fixture();
    let output = run(&fixture, "managed-mismatch", "bad-fingerprint");
    assert_eq!(output.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&output.stderr)
        .contains("admitted_runner_result_fingerprint_mismatch"));
    let result = result_dir(&fixture, "managed-mismatch");
    assert!(result.join("source_snapshot.json").is_file());
    let coverage: Value =
        serde_json::from_slice(&fs::read(result.join("runtime/completion_coverage.json")).unwrap())
            .unwrap();
    assert_eq!(coverage["terminal_complete"], true);
    assert_eq!(
        coverage["failure_kind"],
        "admitted_runner_result_fingerprint_mismatch"
    );
    assert!(result
        .join("runtime/post_tool_use_projection.json")
        .is_file());
}

#[test]
fn provider_protocol_rejections_remain_typed_and_recorded() {
    let fixture = build_fixture();
    for (mode, expected) in [
        ("bad-schema", "admitted_runner_result_schema_mismatch"),
        ("bad-run-id", "admitted_runner_result_corrupt"),
        ("bad-identity", "admitted_runner_result_identity_mismatch"),
        (
            "unproven-completion",
            "admitted_runner_descendant_quiescence_unproven",
        ),
    ] {
        let name = format!("protocol-{mode}");
        let output = run(&fixture, &name, mode);
        assert_eq!(output.status.code(), Some(2), "mode={mode}");
        assert!(
            String::from_utf8_lossy(&output.stderr).contains(expected),
            "mode={mode}: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        let result = result_dir(&fixture, &name);
        assert!(result.join("runtime/completion_coverage.json").is_file());
        assert!(result
            .join("runtime/post_tool_use_projection.json")
            .is_file());
    }
}

#[test]
fn missing_variant_is_rejected_before_result_or_report_mutation() {
    let fixture = build_fixture();
    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "run-managed-experiment",
            "--repo-root",
            fixture.root.to_str().unwrap(),
            "--topic",
            "demo_topic",
            "--run-name",
            "missing-variant",
            "--",
            "python3",
            "experiments/demo_topic/run.py",
        ])
        .output()
        .expect("native managed command starts");
    assert_eq!(output.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&output.stderr).contains("--variant"));
    assert!(!result_dir(&fixture, "missing-variant").exists());
    assert!(!fixture
        .root
        .join("experiments/demo_topic/report/missing-variant.md")
        .exists());
}

#[test]
fn existing_report_blocks_before_result_reservation() {
    let fixture = build_fixture();
    let report = fixture
        .root
        .join("experiments/demo_topic/report/report-conflict.md");
    fs::write(&report, "existing report\n").expect("existing report fixture writes");
    let output = run(&fixture, "report-conflict", "valid");
    assert_eq!(output.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&output.stderr).contains("report already exists for identity"));
    assert_eq!(fs::read_to_string(report).unwrap(), "existing report\n");
    assert!(!result_dir(&fixture, "report-conflict").exists());
}

#[cfg(unix)]
#[test]
fn symlinked_result_root_is_rejected_without_writing_outside() {
    use std::os::unix::fs::symlink;
    let fixture = build_fixture();
    let result_root = fixture.root.join("experiments/demo_topic/result");
    let real_root = fixture.root.join("experiments/demo_topic/result-real");
    let outside_name = format!(
        "{}-outside",
        fixture.root.file_name().unwrap().to_string_lossy()
    );
    let outside = fixture.root.with_file_name(outside_name);
    fs::create_dir(&outside).expect("outside sentinel directory creates");
    fs::rename(&result_root, &real_root).expect("real result root renames");
    symlink(&outside, &result_root).expect("escaping result symlink creates");
    let output = run(&fixture, "symlink-result", "valid");
    assert_eq!(output.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&output.stderr).contains("run path must not escape by symlink"));
    assert_eq!(fs::read_dir(outside).unwrap().count(), 0);
}

#[test]
fn concurrent_same_identity_requests_have_one_winner_and_no_loser_residue() {
    let fixture = build_fixture();
    let root = fixture.root.clone();
    let provider = fixture.provider.clone();
    let outputs = std::thread::scope(|scope| {
        let first_root = root.clone();
        let first_provider = provider.clone();
        let first =
            scope.spawn(move || run_paths(&first_root, &first_provider, "race-run", "valid"));
        let second = scope.spawn(move || run_paths(&root, &provider, "race-run", "valid"));
        [first.join().unwrap(), second.join().unwrap()]
    });
    let mut codes = outputs
        .iter()
        .map(|output| output.status.code().unwrap_or(-1))
        .collect::<Vec<_>>();
    codes.sort_unstable();
    assert_eq!(codes, [0, 2]);
    let result = result_dir(&fixture, "race-run");
    assert!(result.join("run_manifest.json").is_file());
    assert!(!result.join(".agentcanon-reservation.json").exists());
    assert_eq!(
        fs::read_to_string(result.join("fixture-provider-called")).unwrap(),
        "called\n"
    );
    assert!(fixture
        .root
        .join("experiments/demo_topic/report/race-run.md")
        .is_file());
}
