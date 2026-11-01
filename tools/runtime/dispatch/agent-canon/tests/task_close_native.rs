// @dependency-start
// contract test
// responsibility Replays frozen TaskClose API and CLI outcomes through the native owner.
// upstream implementation ../src/task_close.rs owns read-only terminal predicates and CLI output
// upstream implementation ../src/runtime_boundary.rs owns external runtime artifact reads
// upstream test ../../../../../tests/fixtures/task_close/python_golden.json freezes old TaskClose results
// @dependency-end

use agent_canon::agent_tool_calls::{
    materialize_close_agent_tool_call, CloseAgentLifecycleEvidence, CloseAgentLifecycleOwnerInput,
};
use agent_canon::runtime_boundary::RuntimeArtifactBoundary;
use agent_canon::task_close::{
    child_closeout_evidence, document_structure_evidence_ready, update_lifecycle_closeout_consumer,
};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};

const PYTHON_GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/task_close/python_golden.json");
#[cfg(target_os = "linux")]
const OLD_SOURCE_COMMIT: &str = "706c3b43f658b5341db7c3856208a870103f9568";

static NEXT_FIXTURE: AtomicU64 = AtomicU64::new(0);

struct Fixture(PathBuf);

impl Fixture {
    fn new(label: &str) -> Self {
        let path = std::env::temp_dir().join(format!(
            "agent-canon-task-close-{label}-{}-{}",
            std::process::id(),
            NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir_all(&path).expect("create TaskClose fixture root");
        Self(fs::canonicalize(path).expect("resolve TaskClose fixture root"))
    }

    fn source(&self) -> PathBuf {
        self.0.join("source")
    }

    fn runtime(&self) -> PathBuf {
        self.0.join("runtime")
    }

    fn report_dir(&self, run_id: &str) -> PathBuf {
        self.runtime().join("reports/agents").join(run_id)
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn golden() -> Value {
    serde_json::from_str(PYTHON_GOLDEN).expect("frozen Python TaskClose corpus is JSON")
}

#[test]
fn task_close_python_corpus_bytes_remain_frozen() {
    let digest = Sha256::digest(PYTHON_GOLDEN.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    assert_eq!(
        digest,
        "34a39f38017e8936a238ff88fe4b49d94009f9aba5f1a407b739f0f1f13883f3"
    );
}

fn write_bytes(path: &Path, bytes: &[u8]) {
    fs::create_dir_all(path.parent().expect("fixture file has a parent"))
        .expect("create fixture file parent");
    fs::write(path, bytes).expect("write TaskClose fixture file");
}

fn write_text(path: &Path, text: &str) {
    write_bytes(path, text.as_bytes());
}

#[cfg(target_os = "linux")]
fn git(root: &Path, args: &[&str]) -> Output {
    Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .expect("run temporary TaskClose Git premise")
}

#[cfg(target_os = "linux")]
fn create_main706_workspace(destination: &Path) -> PathBuf {
    let repository = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .expect("Cargo manifest lives below the AgentCanon root");
    let clone = Command::new("git")
        .args(["clone", "--quiet", "--shared", "--no-checkout"])
        .arg(repository)
        .arg(destination)
        .output()
        .expect("create isolated Git context from local source history");
    assert!(clone.status.success(), "local repository clone succeeds");
    let reset = git(destination, &["reset", "--hard", OLD_SOURCE_COMMIT]);
    assert!(
        reset.status.success(),
        "temporary Git context selects main706"
    );
    let remote = git(
        destination,
        &[
            "remote",
            "set-url",
            "origin",
            "https://github.com/iwashita-nozomu/agent-canon.git",
        ],
    );
    assert!(
        remote.status.success(),
        "temporary repository records the AgentCanon remote"
    );
    destination.to_path_buf()
}

fn rewrite_g6_source_context(artifact: &mut Value, source_root: &str) {
    let gates = artifact["gate_verdicts"]
        .as_array()
        .expect("closeout artifact has gate verdicts");
    // The valid case needs the host-local source identity in G6; the missing-G6
    // negative fixture remains byte-semantic input to its earlier cardinality guard.
    if gates.len() != 6 {
        return;
    }
    let source_gates = gates[..5].to_vec();
    let handback = artifact["durable_handback"].clone();
    let cleanup = artifact["cleanup_proof"].clone();
    let descendants = artifact["descendants"]
        .as_array()
        .expect("closeout artifact has descendants")
        .clone();
    let reservations = artifact["reservations"]
        .as_array()
        .expect("closeout artifact has reservations")
        .clone();
    let token = &artifact["close_agent_tool_call"];
    let run_id = token["args"]["run_id"]
        .as_str()
        .expect("terminal token carries its run id");
    let agent_id = handback["agent_id"]
        .as_str()
        .expect("durable handback carries its agent id");
    let materialized = materialize_close_agent_tool_call(CloseAgentLifecycleOwnerInput {
        source_root,
        run_id,
        agent_id,
        evidence: CloseAgentLifecycleEvidence {
            gate_verdicts: &source_gates,
            cleanup_proof: &cleanup,
            durable_handback: &handback,
            descendant_close_receipts: &descendants,
            reservation_release_receipts: &reservations,
        },
    })
    .expect("existing G6 owner rebinds only its source-root context");
    let gates = artifact["gate_verdicts"]
        .as_array_mut()
        .expect("closeout artifact has gate verdicts");
    gates[5] = materialized["g6_gate"].clone();
    artifact["close_agent_tool_call"] = materialized["close_agent_tool_call"].clone();
    artifact["descendants_closed_evidence_ref"] =
        materialized["descendants_closed_evidence_ref"].clone();
    artifact["reservations_released_evidence_ref"] =
        materialized["reservations_released_evidence_ref"].clone();
}

fn write_cli_case(fixture: &Fixture, source_root: &Path, case: &Value) -> PathBuf {
    let run_id = case["run_id"].as_str().expect("CLI case has run id");
    let report_root = fixture.runtime().join("reports/agents");
    let report_dir = report_root.join(run_id);
    let files = case["report_files"]
        .as_object()
        .expect("CLI case records report file inputs");
    for (relative, recorded) in files {
        let relative = Path::new(relative.as_str());
        let text = recorded.get("utf8_text").and_then(Value::as_str);
        let bytes = if let Some(text) = text {
            text.as_bytes().to_vec()
        } else {
            let encoded = recorded["bytes_hex"]
                .as_str()
                .expect("binary report artifact has hex bytes");
            let mut bytes = Vec::with_capacity(encoded.len() / 2);
            for index in (0..encoded.len()).step_by(2) {
                bytes.push(u8::from_str_radix(&encoded[index..index + 2], 16).unwrap());
            }
            bytes
        };
        let target = fixture.runtime().join(relative);
        if relative.ends_with("update_lifecycle_closeout.json") {
            let mut artifact: Value =
                serde_json::from_slice(&bytes).expect("old lifecycle closeout fixture is JSON");
            rewrite_g6_source_context(
                &mut artifact,
                source_root
                    .to_str()
                    .expect("temporary source path is UTF-8"),
            );
            write_bytes(
                &target,
                &serde_json::to_vec(&artifact).expect("mapped lifecycle artifact serializes"),
            );
        } else {
            write_bytes(&target, &bytes);
        }
    }
    report_dir
}

#[test]
fn task_close_g6_consumer_matches_all_six_frozen_python_cases() {
    let corpus = golden();
    let source_root = corpus["source"]["source_root"]
        .as_str()
        .expect("old source context is recorded");
    let fixture = Fixture::new("api");
    fs::create_dir_all(fixture.source()).expect("create source root for runtime boundary");
    fs::create_dir_all(fixture.runtime()).expect("create external runtime root");
    let boundary =
        RuntimeArtifactBoundary::for_source(&fixture.source(), Some(&fixture.runtime()), false)
            .expect("open read-only TaskClose runtime boundary");
    let cases = corpus["task_close_g6_consumer_api_cases"]
        .as_array()
        .expect("corpus records TaskClose G6 consumer cases");
    assert_eq!(
        cases.len(),
        6,
        "all six TaskClose consumer cases remain present"
    );
    for (index, case) in cases.iter().enumerate() {
        let report_dir = fixture.runtime().join(format!("api-case-{index}"));
        fs::create_dir_all(&report_dir).expect("create case-local report directory");
        let artifact = serde_json::to_vec(&case["input"])
            .expect("frozen API input serializes for read-only consumption");
        write_bytes(
            &report_dir.join("update_lifecycle_closeout.json"),
            &artifact,
        );
        let decision = update_lifecycle_closeout_consumer(&boundary, &report_dir, source_root);
        assert_eq!(
            decision.to_json_value(),
            case["result"],
            "TaskClose consumer case {}",
            case["test_name"].as_str().unwrap_or("unknown")
        );
    }
}

#[test]
fn document_structure_graph_evidence_is_checked_only_when_supplied() {
    let mut evidence = BTreeMap::from([
        (
            "document_structure_paths".to_owned(),
            "README.md".to_owned(),
        ),
        (
            "document_structure_status".to_owned(),
            "complete".to_owned(),
        ),
        ("structure_activation".to_owned(), "not_required".to_owned()),
        (
            "document_split_decision".to_owned(),
            "keep:existing-topology:README.md".to_owned(),
        ),
        ("structure_planning".to_owned(), "not_required".to_owned()),
        (
            "structure_contract".to_owned(),
            "not_required:existing-topology:README.md".to_owned(),
        ),
        ("structure_owner".to_owned(), "README.md owner".to_owned()),
        (
            "structure_source".to_owned(),
            "README.md canonical source".to_owned(),
        ),
        (
            "structure_reader".to_owned(),
            "repository entry reader".to_owned(),
        ),
        (
            "structure_layout".to_owned(),
            "existing README layout".to_owned(),
        ),
        (
            "structure_validation_topology".to_owned(),
            "targeted Markdown check".to_owned(),
        ),
    ]);
    let changed = vec!["README.md".to_owned()];
    assert!(document_structure_evidence_ready(&changed, &evidence).2);
    evidence.insert("prose_graph_activation".to_owned(), "selected".to_owned());
    evidence.insert("prose_graph".to_owned(), "pending".to_owned());
    assert!(!document_structure_evidence_ready(&changed, &evidence).2);
    evidence.insert("prose_graph".to_owned(), "complete".to_owned());
    assert!(document_structure_evidence_ready(&changed, &evidence).2);
}

#[test]
fn task_close_rejects_a_forged_child_receipt() {
    let corpus = golden();
    let fixture = Fixture::new("child-receipt");
    fs::create_dir_all(fixture.source()).expect("create runtime boundary source root");
    fs::create_dir_all(fixture.runtime()).expect("create external runtime root");
    let boundary =
        RuntimeArtifactBoundary::for_source(&fixture.source(), Some(&fixture.runtime()), false)
            .expect("open read-only TaskClose runtime boundary");
    let ready_case = &corpus["task_close_cli_cases"][0];
    write_cli_case(&fixture, &fixture.source(), ready_case);
    let report_dir = fixture.report_dir(ready_case["run_id"].as_str().expect("run id is text"));
    let verifier_path = report_dir.join("runtime/verifier_receipt.json");
    let verifier = fs::read_to_string(&verifier_path)
        .expect("ready fixture has verifier receipt")
        .replace("verifier-1", "forged");
    write_text(&verifier_path, &verifier);
    let closeout = BTreeMap::from([
        ("verifier_role_id".to_owned(), "verifier".to_owned()),
        (
            "verifier_runtime_agent_id".to_owned(),
            "verifier-1".to_owned(),
        ),
        (
            "verifier_receipt_ref".to_owned(),
            "runtime/verifier_receipt.json".to_owned(),
        ),
        (
            "parent_mutation_status".to_owned(),
            "no_parent_mutation".to_owned(),
        ),
        (
            "parent_mutation_evidence_ref".to_owned(),
            "runtime/parent_mutation_evidence.json".to_owned(),
        ),
    ]);
    let (ready, blockers) = child_closeout_evidence(&boundary, &report_dir, &closeout);
    assert!(!ready);
    assert!(blockers.contains(&"runtime_verifier_receipt_invalid".to_owned()));
}

#[test]
#[cfg(target_os = "linux")]
fn task_close_cli_replays_frozen_stdout_results_and_all_status_fields() {
    let corpus = golden();
    let fixture = Fixture::new("cli");
    let source_root = create_main706_workspace(&fixture.0.join("source"));
    let workspace = create_main706_workspace(&fixture.0.join("workspace"));
    let runtime = fixture.runtime();
    fs::create_dir_all(&runtime).expect("create external runtime root");
    let cases = corpus["task_close_cli_cases"]
        .as_array()
        .expect("corpus records TaskClose CLI cases");
    assert_eq!(
        cases.len(),
        5,
        "both ready and three blocker routes stay covered"
    );
    for case in cases {
        let report_dir = write_cli_case(&fixture, &source_root, case);
        let run_id = case["run_id"].as_str().expect("CLI case has run id");
        let mut command = Command::new(env!("CARGO_BIN_EXE_agent-canon"));
        command
            .arg("task-close")
            .current_dir(&workspace)
            .env("AGENT_CANON_PARENT_ROOT", &workspace)
            .env("AGENT_CANON_SOURCE_ROOT", &source_root)
            .env("AGENT_CANON_RUNTIME_ROOT", &runtime)
            .env_remove("AGENT_CANON_ACTIVE_REPOSITORY_ROOT");
        if case["mode"] == "run-id" {
            command
                .args(["--run-id", run_id, "--report-root"])
                .arg(runtime.join("reports/agents"))
                .arg("--runtime-root")
                .arg(&runtime);
        } else {
            command
                .arg("--report-dir")
                .arg(&report_dir)
                .arg("--runtime-root")
                .arg(&runtime);
        }
        let output = command.output().expect("run actual native TaskClose CLI");
        assert_eq!(
            output.status.code(),
            case["returncode"].as_i64().map(|code| code as i32),
            "CLI case {} exit status",
            case["name"].as_str().unwrap_or("unknown")
        );
        let actual_stdout = String::from_utf8(output.stdout).expect("TaskClose stdout is UTF-8");
        let old_stdout = case["stdout"].as_str().expect("old CLI stdout is text");
        let expected_report_line = old_stdout
            .lines()
            .next()
            .expect("report path is first output line");
        let mapped_report_line = format!("REPORT_DIR={}", report_dir.display());
        let expected_stdout = old_stdout.replacen(expected_report_line, &mapped_report_line, 1);
        assert_eq!(
            actual_stdout,
            expected_stdout,
            "CLI case {} preserves every printed predicate and value",
            case["name"].as_str().unwrap_or("unknown")
        );
        assert_eq!(
            String::from_utf8(output.stderr).expect("TaskClose stderr is UTF-8"),
            case["stderr"].as_str().expect("old CLI stderr is text"),
            "CLI case {} stderr",
            case["name"].as_str().unwrap_or("unknown")
        );
    }
}

#[cfg(not(target_os = "linux"))]
#[test]
fn task_close_cli_preserves_the_existing_unsupported_parent_authority_result() {
    let fixture = Fixture::new("unsupported-authority");
    fs::create_dir_all(fixture.source()).expect("create source root");
    fs::create_dir_all(fixture.runtime()).expect("create external runtime root");
    fs::create_dir_all(fixture.0.join("workspace")).expect("create workspace root");
    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args(["task-close", "--report-dir", "missing-report"])
        .current_dir(fixture.0.join("workspace"))
        .env("AGENT_CANON_PARENT_ROOT", fixture.0.join("workspace"))
        .env("AGENT_CANON_SOURCE_ROOT", fixture.source())
        .env("AGENT_CANON_RUNTIME_ROOT", fixture.runtime())
        .output()
        .expect("run native TaskClose command");
    assert_eq!(output.status.code(), Some(1));
    let stderr = String::from_utf8(output.stderr).expect("native error is UTF-8");
    assert!(stderr.contains("unsupported_platform"), "{stderr}");
}
