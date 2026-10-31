// @dependency-start
// contract test
// responsibility Preserves native G2 materialization and production persistence against frozen Python receipts.
// upstream implementation ../src/generated_completeness.rs owns G2 validation, materialization, and CLI persistence
// upstream implementation ../src/runtime_boundary.rs owns no-follow G2 replay reads
// upstream test ../../../../../tests/fixtures/generated_completeness/python_golden.json stores the old pure G2 oracle
// upstream test ../../../../../tests/fixtures/generated_completeness/github_g1_g2.json stores complete publication consumer gates
// upstream test ../../../../../tests/fixtures/generated_completeness/closeout_g1_g2.json stores complete closeout consumer gates
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_bytes;
use agent_canon::generated_completeness::materialize_generated_completeness_receipt;
use serde_json::Value as JsonValue;
use sha2::{Digest, Sha256};

const PYTHON_G2_ORACLE: &str =
    include_str!("../../../../../tests/fixtures/generated_completeness/python_golden.json");
const G2_LOGICAL_OWNER_SUFFIX: &str =
    "/tools/validation/ci/checks/check_agent_canon_pr.py#materialize_generated_completeness_receipt";

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn recorded_source_root(oracle: &JsonValue) -> String {
    let canonical = oracle["cases"][0]["canonical_utf8"]
        .as_str()
        .expect("valid G2 oracle has canonical JSON bytes");
    let receipt: JsonValue =
        serde_json::from_str(canonical).expect("valid G2 oracle receipt parses");
    let owner = receipt["owner"]
        .as_str()
        .expect("valid G2 oracle receipt records its owner");
    owner
        .strip_suffix(G2_LOGICAL_OWNER_SUFFIX)
        .expect("G2 owner preserves the existing Python schema suffix")
        .to_string()
}

#[test]
fn g2_materializer_matches_all_frozen_python_cases() {
    let oracle: JsonValue =
        serde_json::from_str(PYTHON_G2_ORACLE).expect("frozen G2 oracle is JSON");
    let cases = oracle["cases"]
        .as_array()
        .expect("frozen G2 oracle has cases");
    assert_eq!(cases.len(), 12, "all frozen G2 oracle cases remain covered");
    let source_root = recorded_source_root(&oracle);

    for case in cases {
        let input = &case["input"];
        let results = input["check_results"]
            .as_array()
            .expect("case check results are a list");
        let result = materialize_generated_completeness_receipt(
            &input["g1_gate"],
            input["candidate_sha"]
                .as_str()
                .expect("case candidate SHA is text"),
            input["tree_sha"].as_str().expect("case tree SHA is text"),
            results,
            &source_root,
        );
        if case["error"].is_null() {
            let receipt = result.unwrap_or_else(|error| {
                panic!("case {} unexpectedly failed: {error}", case["name"])
            });
            let bytes = canonical_json_bytes(&receipt).expect("canonical G2 receipt bytes");
            assert_eq!(
                bytes,
                case["canonical_utf8"]
                    .as_str()
                    .expect("valid case has canonical bytes")
                    .as_bytes(),
                "case {} canonical G2 bytes",
                case["name"]
            );
            assert_eq!(
                sha256_hex(&bytes),
                case["sha256"]
                    .as_str()
                    .expect("valid case has output digest"),
                "case {} G2 SHA-256",
                case["name"]
            );
        } else {
            let error = result.expect_err("invalid G2 oracle case is rejected");
            let expected = case["error"]
                .get("message")
                .and_then(JsonValue::as_str)
                .or_else(|| case["error"].get("code").and_then(JsonValue::as_str))
                .expect("invalid G2 case records its error");
            assert_eq!(error.to_string(), expected, "case {} error", case["name"]);
        }
    }
}

#[cfg(target_os = "linux")]
mod runtime_boundary_tests {
    use super::*;
    use agent_canon::runtime_boundary::RuntimeArtifactBoundary;
    use agent_canon::update_lifecycle_contract::{materialize_gate_verdict, GateVerdictInput};
    use std::fs;
    use std::path::{Path, PathBuf};
    use std::process::{Command, Output};
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT_DIRECTORY: AtomicU64 = AtomicU64::new(0);

    struct Fixture {
        root: PathBuf,
        source: PathBuf,
        control: PathBuf,
        runtime: PathBuf,
        global_git_config: PathBuf,
        g1_bundle: PathBuf,
    }

    impl Fixture {
        fn new() -> Self {
            let sequence = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
            let root = std::env::temp_dir().join(format!(
                "agent-canon-generated-completeness-{}-{sequence}",
                std::process::id()
            ));
            fs::create_dir_all(&root).expect("create G2 runtime fixture root");
            let root = fs::canonicalize(root).expect("resolve G2 runtime fixture root");
            let control = root.join("control");
            let source = control.join("source");
            let runtime = root.join("runtime");
            fs::create_dir_all(&control).expect("create G2 control root");
            fs::create_dir_all(&source).expect("create G2 source root");
            fs::create_dir_all(&runtime).expect("create G2 runtime root");
            let global_git_config = root.join("empty-global-gitconfig");
            fs::write(&global_git_config, b"").expect("write empty Git config");
            let g1_bundle = runtime.join("g1.bundle.json");
            Self {
                root,
                source,
                control,
                runtime,
                global_git_config,
                g1_bundle,
            }
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.root);
        }
    }

    fn git(fixture: &Fixture, root: &Path, args: &[&str]) -> Output {
        Command::new("git")
            .args(args)
            .env("GIT_CONFIG_NOSYSTEM", "1")
            .env("GIT_CONFIG_GLOBAL", &fixture.global_git_config)
            .current_dir(root)
            .output()
            .expect("Git fixture command runs")
    }

    fn initialize_repository(fixture: &Fixture, root: &Path) {
        let output = git(fixture, root, &["init", "-q", "-b", "main"]);
        assert!(
            output.status.success(),
            "Git initializes the temporary repository"
        );
    }

    fn source_identity(fixture: &Fixture) -> (String, String) {
        let commit = git(fixture, &fixture.source, &["rev-parse", "HEAD"]);
        let tree = git(fixture, &fixture.source, &["rev-parse", "HEAD^{tree}"]);
        assert!(commit.status.success(), "Git reads the source commit");
        assert!(tree.status.success(), "Git reads the source tree");
        (
            String::from_utf8(commit.stdout)
                .expect("Git commit is UTF-8")
                .trim()
                .to_string(),
            String::from_utf8(tree.stdout)
                .expect("Git tree is UTF-8")
                .trim()
                .to_string(),
        )
    }

    fn write_g1_bundle(fixture: &Fixture) {
        let oracle: JsonValue =
            serde_json::from_str(PYTHON_G2_ORACLE).expect("frozen G2 oracle is JSON");
        let g1_input = &oracle["cases"][0]["input"]["g1_gate"];
        let (candidate_sha, tree_sha) = source_identity(fixture);
        let mut binding = g1_input["binding"].clone();
        binding["candidate_sha"] = JsonValue::String(candidate_sha);
        binding["tree_sha"] = JsonValue::String(tree_sha);
        let ordered_input_evidence_refs = g1_input["ordered_input_evidence_refs"]
            .as_array()
            .expect("G1 fixture has ordered input refs")
            .iter()
            .map(|reference| {
                reference
                    .as_str()
                    .expect("G1 input ref is text")
                    .to_string()
            })
            .collect::<Vec<_>>();
        let owner = fixture
            .source
            .join("tools/repository/github/publication_integrator.py")
            .to_str()
            .expect("fixture source path is UTF-8")
            .to_string()
            + "#resolve_publication_eligibility";
        let g1 = materialize_gate_verdict(&GateVerdictInput {
            binding,
            gate_id: "G1".to_string(),
            ordered_input_evidence_refs,
            invariant: "source_correctness".to_string(),
            output_digest: g1_input["output_digest"]
                .as_str()
                .expect("G1 output digest is text")
                .to_string(),
            owner,
            verdict: "pass".to_string(),
            retry_reason: None,
            next_checkpoint: None,
        })
        .expect("valid G1 fixture materializes");
        let bundle = json!({"gate_verdicts": [g1]});
        fs::write(
            &fixture.g1_bundle,
            serde_json::to_vec(&bundle).expect("serialize G1 bundle"),
        )
        .expect("write G1 bundle fixture");
    }

    fn cli(fixture: &Fixture, control_root: &Path, output: Option<&Path>) -> Output {
        let mut command = Command::new(env!("CARGO_BIN_EXE_agent-canon"));
        command
            .args([SELECTOR, "--g1-bundle"])
            .arg(&fixture.g1_bundle)
            .args(["--source-root"])
            .arg(&fixture.source)
            .args(["--control-parent-root"])
            .arg(control_root)
            .args(["--runtime-root"])
            .arg(&fixture.runtime)
            .env("AGENT_CANON_PARENT_ROOT", control_root)
            .env("AGENT_CANON_ACTIVE_REPOSITORY_ROOT", control_root)
            .env("GIT_CONFIG_NOSYSTEM", "1")
            .env("GIT_CONFIG_GLOBAL", &fixture.global_git_config)
            .current_dir(&fixture.source);
        if let Some(output) = output {
            command.arg("--output").arg(output);
        }
        command.output().expect("native G2 CLI runs")
    }

    fn pretty_bytes(value: &JsonValue) -> Vec<u8> {
        let mut bytes = serde_json::to_vec_pretty(value).expect("serialize runtime gate record");
        bytes.push(b'\n');
        bytes
    }

    #[test]
    fn g2_cli_attests_control_and_confines_runtime_replay() {
        let fixture = Fixture::new();
        initialize_repository(&fixture, &fixture.control);
        initialize_repository(&fixture, &fixture.source);
        fs::create_dir_all(
            fixture
                .source
                .join("tools/validation/ci/checks")
                .parent()
                .expect("source owner directory has a parent"),
        )
        .expect("create logical G2 owner parent");
        fs::write(
            fixture
                .source
                .join("tools/validation/ci/checks/check_agent_canon_pr.py"),
            b"# logical schema owner fixture\n",
        )
        .expect("write logical G2 owner fixture");
        fs::create_dir_all(fixture.source.join("tools/repository/github"))
            .expect("create G1 owner parent");
        fs::write(
            fixture
                .source
                .join("tools/repository/github/publication_integrator.py"),
            b"# G1 schema owner fixture\n",
        )
        .expect("write G1 owner fixture");
        fs::write(fixture.source.join("README.md"), b"G2 test source\n")
            .expect("write source fixture");
        assert!(git(&fixture, &fixture.source, &["add", "--all"])
            .status
            .success());
        let commit = git(
            &fixture,
            &fixture.source,
            &[
                "-c",
                "user.name=G2 Fixture",
                "-c",
                "user.email=g2-fixture@example.invalid",
                "commit",
                "-q",
                "-m",
                "source fixture",
            ],
        );
        assert!(commit.status.success(), "Git commits the source fixture");
        write_g1_bundle(&fixture);

        let transaction = "1111111111111111111111111111111111111111111111111111111111111111";
        let output_path = fixture
            .runtime
            .join("tasks/update-lifecycle/evidence")
            .join(transaction)
            .join("g2.generated-completeness.json");
        let same_root = cli(&fixture, &fixture.source, None);
        assert_eq!(same_root.status.code(), Some(2));
        assert!(!same_root
            .stdout
            .windows(b"AGENT_CANON_G2_RECEIPT".len())
            .any(|window| window == b"AGENT_CANON_G2_RECEIPT"));
        assert!(!output_path.exists());

        let first = cli(&fixture, &fixture.control, None);
        assert_eq!(
            first.status.code(),
            Some(0),
            "{}",
            String::from_utf8_lossy(&first.stderr)
        );
        let first_stdout = String::from_utf8(first.stdout.clone()).expect("G2 markers are UTF-8");
        assert!(first_stdout.contains("AGENT_CANON_G2_RECEIPT=materialized\n"));
        assert!(first_stdout.contains(&format!(
            "AGENT_CANON_G2_OUTPUT={}\n",
            output_path.display()
        )));
        let runtime =
            RuntimeArtifactBoundary::for_source(&fixture.source, Some(&fixture.runtime), false)
                .expect("open selected runtime boundary");
        let first_bytes = runtime
            .read_bytes(&output_path)
            .expect("read persisted G2 through the boundary")
            .expect("G2 receipt exists");
        assert!(first_bytes.ends_with(b"\n"));
        let first_record: JsonValue =
            serde_json::from_slice(&first_bytes).expect("persisted G2 is JSON");
        let evidence_ref = first_record["binding"]["evidence_ref"]
            .as_str()
            .expect("persisted G2 has an evidence ref");
        assert!(first_stdout.contains(&format!("AGENT_CANON_G2_EVIDENCE_REF={evidence_ref}\n")));
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                fs::metadata(&output_path)
                    .expect("read G2 output metadata")
                    .permissions()
                    .mode()
                    & 0o777,
                0o600
            );
        }

        let explicit_output = fixture.runtime.join("selected/g2.json");
        let selected = cli(&fixture, &fixture.control, Some(&explicit_output));
        assert_eq!(
            selected.status.code(),
            Some(0),
            "{}",
            String::from_utf8_lossy(&selected.stderr)
        );
        let selected_stdout = String::from_utf8(selected.stdout).expect("G2 markers are UTF-8");
        assert!(selected_stdout.contains(&format!(
            "AGENT_CANON_G2_OUTPUT={}\n",
            explicit_output.display()
        )));
        assert!(runtime
            .read_bytes(&explicit_output)
            .expect("read explicitly selected G2 through the boundary")
            .is_some());

        let replay = cli(&fixture, &fixture.control, None);
        assert_eq!(replay.status.code(), Some(0));
        assert_eq!(
            runtime
                .read_bytes(&output_path)
                .expect("read G2 replay")
                .expect("G2 replay remains present"),
            first_bytes
        );

        let mut timing_replay = first_record.clone();
        let timing = timing_replay["binding"]["timing"]
            .as_object_mut()
            .expect("G2 binding has timing metadata");
        for field in ["started_at", "finished_at", "last_attempt_at"] {
            timing.insert(
                field.to_string(),
                JsonValue::String("2026-08-01T00:00:00Z".to_string()),
            );
        }
        runtime
            .atomic_write_bytes(&output_path, &pretty_bytes(&timing_replay), 0o600)
            .expect("write timing-only replay fixture");
        let timing_replay_output = cli(&fixture, &fixture.control, None);
        assert_eq!(
            timing_replay_output.status.code(),
            Some(0),
            "{}",
            String::from_utf8_lossy(&timing_replay_output.stderr)
        );
        let preserved_timing: JsonValue = serde_json::from_slice(
            &runtime
                .read_bytes(&output_path)
                .expect("read timing replay")
                .expect("timing replay remains present"),
        )
        .expect("timing replay JSON parses");
        assert_eq!(
            preserved_timing["binding"]["timing"]["started_at"],
            "2026-08-01T00:00:00Z"
        );

        let mut immutable_change = preserved_timing;
        immutable_change["output_digest"] = JsonValue::String(format!("sha256:{}", "f".repeat(64)));
        runtime
            .atomic_write_bytes(&output_path, &pretty_bytes(&immutable_change), 0o600)
            .expect("write immutable-change refusal fixture");
        let refusal = cli(&fixture, &fixture.control, None);
        assert_ne!(refusal.status.code(), Some(0));
        assert!(!refusal
            .stdout
            .windows(b"AGENT_CANON_G2_RECEIPT".len())
            .any(|window| window == b"AGENT_CANON_G2_RECEIPT"));
        let outside_output = fixture.root.join("outside-runtime.json");
        let outside = cli(&fixture, &fixture.control, Some(&outside_output));
        assert_eq!(outside.status.code(), Some(1));
        assert!(!outside_output.exists());
    }
}
