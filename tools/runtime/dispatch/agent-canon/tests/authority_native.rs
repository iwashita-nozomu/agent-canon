#![cfg(target_os = "linux")]

use agent_canon::authority::{
    AttestationRequest, AuthorityError, ChildHandoffRequest, NonEmptyTrimmedString,
    Nonce128, ParentRootAttestor, ParentRootReject, Sha256Digest, SecretToken,
};
use base64::engine::general_purpose::URL_SAFE;
use base64::Engine;
use hmac::{Hmac, Mac};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;
use std::os::unix::fs::{MetadataExt, PermissionsExt};

static NEXT_TEMP: AtomicUsize = AtomicUsize::new(0);
type HmacSha256 = Hmac<Sha256>;

struct TempDir(PathBuf);

impl TempDir {
    fn new() -> Self {
        let suffix = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-authority-native-{}-{suffix}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("create isolated test directory");
        Self(fs::canonicalize(path).expect("canonicalize isolated test directory"))
    }

    fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

struct TopicFixture {
    root: PathBuf,
    source: PathBuf,
    clone: PathBuf,
    marker: PathBuf,
    gitmodules: PathBuf,
    owner: PathBuf,
    module_digest: Sha256Digest,
}

fn nonempty(value: impl Into<String>) -> NonEmptyTrimmedString {
    NonEmptyTrimmedString::new(value).expect("fixture purpose is valid")
}

fn attestation_request(root: &Path, purpose: &str) -> AttestationRequest {
    AttestationRequest {
        cwd: root.to_path_buf(),
        explicit_root: Some(root.to_path_buf()),
        source_root: None,
        clone_root: None,
        topic_marker: None,
        gitmodules: None,
        owner_evidence: None,
        expected_remote: None,
        expected_module_digest: None,
        child_handoff_token: None,
        purpose: nonempty(purpose),
        nonce: Nonce128::generate().expect("OS CSPRNG supplies a request nonce"),
    }
}

fn git(path: &Path, args: &[&str]) -> Output {
    Command::new("git")
        .arg("-C")
        .arg(path)
        .args(args)
        .output()
        .expect("run host Git oracle")
}

fn git_ok(path: &Path, args: &[&str]) -> Output {
    let output = git(path, args);
    assert!(
        output.status.success(),
        "git {args:?} failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    output
}

fn git_stdout(path: &Path, args: &[&str]) -> String {
    String::from_utf8(git_ok(path, args).stdout)
        .expect("Git identity output is UTF-8")
        .trim()
        .to_owned()
}

fn git_repo(path: &Path, remote: &str) {
    fs::create_dir_all(path).expect("create Git fixture path");
    let output = Command::new("git")
        .args(["init", "-q", "-b", "main"])
        .arg(path)
        .output()
        .expect("initialize fixture repository");
    assert!(output.status.success(), "git init: {}", String::from_utf8_lossy(&output.stderr));
    git_ok(path, &["remote", "add", "origin", remote]);
    let output = Command::new("git")
        .arg("-C")
        .arg(path)
        .args([
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "fixture",
        ])
        .output()
        .expect("create fixture commit");
    assert!(output.status.success(), "git commit: {}", String::from_utf8_lossy(&output.stderr));
}

fn sha256_hex(value: &[u8]) -> String {
    Sha256::digest(value)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn decode_hex(value: &str) -> Vec<u8> {
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let digit = |byte: u8| match byte {
                b'0'..=b'9' => Some(byte - b'0'),
                b'a'..=b'f' => Some(byte - b'a' + 10),
                b'A'..=b'F' => Some(byte - b'A' + 10),
                _ => None,
            };
            (digit(pair[0]).expect("hex digit") << 4) | digit(pair[1]).expect("hex digit")
        })
        .collect()
}

fn python_canonical_json_oracle(value: &Value) -> Vec<u8> {
    const PYTHON: &str = "import json,sys; value=json.load(sys.stdin); sys.stdout.buffer.write(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8'))";
    let input = serde_json::to_vec(value).expect("serialize Python JSON input");
    let mut process = Command::new("python3")
        .args(["-c", PYTHON])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("start Python JSON byte oracle");
    process
        .stdin
        .take()
        .expect("Python oracle stdin")
        .write_all(&input)
        .expect("write Python JSON oracle input");
    let output = process
        .wait_with_output()
        .expect("wait for Python JSON byte oracle");
    assert!(
        output.status.success(),
        "Python JSON oracle failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    output.stdout
}

fn verify_handoff_independently(token: &str, root: &Path) -> Value {
    let envelope_bytes = URL_SAFE.decode(token).expect("decode URL-safe handoff");
    let envelope: Value = serde_json::from_slice(&envelope_bytes).expect("parse handoff envelope");
    assert_eq!(envelope_bytes, python_canonical_json_oracle(&envelope));
    let payload = envelope["payload"].as_object().expect("payload object");
    let payload_keys = payload.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected_payload_keys = [
        "token_version",
        "audience",
        "parent_root",
        "source_root",
        "clone_root",
        "issued_at",
        "expires_at",
        "nonce",
        "payload_sha256",
        "storage",
        "mode",
        "validation",
        "transport",
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();
    assert_eq!(
        payload_keys,
        expected_payload_keys
    );
    let signature = envelope["signature"].as_str().expect("signature string");
    let mut body = payload.clone();
    let claimed_digest = body
        .remove("payload_sha256")
        .and_then(|value| value.as_str().map(str::to_owned))
        .expect("payload digest");
    assert_eq!(
        claimed_digest,
        sha256_hex(&python_canonical_json_oracle(&Value::Object(body)))
    );

    let secret_path = root.join(".agent-canon/handoff/secret");
    let secret_metadata = fs::metadata(&secret_path).expect("stat persisted handoff secret");
    assert_eq!(secret_metadata.permissions().mode() & 0o077, 0);
    let secret = fs::read(secret_path).expect("read persisted fixture secret");
    assert!(secret.len() >= 32);
    let boot_id = fs::read_to_string("/proc/sys/kernel/random/boot_id")
        .expect("read Linux boot identity");
    let mut derive = HmacSha256::new_from_slice(&secret).expect("initialize session-key oracle");
    derive.update(boot_id.trim().as_bytes());
    let session_key = derive.finalize().into_bytes();
    let mut verify = HmacSha256::new_from_slice(&session_key).expect("initialize HMAC oracle");
    verify.update(&python_canonical_json_oracle(&Value::Object(payload.clone())));
    verify
        .verify_slice(&decode_hex(signature))
        .expect("standard HMAC-SHA256 verifies the issued token");

    let state_path = root.join(".agent-canon/handoff/nonces.json");
    let state: BTreeMap<String, f64> =
        serde_json::from_slice(&fs::read(state_path).expect("read pending nonce receipt"))
            .expect("parse pending nonce state");
    let nonce = payload["nonce"].as_str().expect("nonce string");
    assert!(state.contains_key(nonce), "issued nonce is durable before consumption");
    assert_eq!(nonce.len(), 32, "handoff nonce has 128 bits");
    envelope
}

fn pending_handoff_nonces(root: &Path) -> BTreeMap<String, f64> {
    let state_path = root.join(".agent-canon/handoff/nonces.json");
    serde_json::from_slice(&fs::read(state_path).expect("read nonce receipt"))
        .expect("parse nonce receipt")
}

fn python_owner_verify(token: &str, root: &Path, purpose: &str) -> Output {
    const SCRIPT: &str = "import os,sys; from pathlib import Path; from tools.repository.workspace.parent_root_side_effects import ParentRootAttestationRequest,ParentRootSideEffectBoundary; root=Path(sys.argv[1]); request=ParentRootAttestationRequest(cwd=root,explicit_root=root,purpose=sys.argv[2]); ParentRootSideEffectBoundary().verify_child_environment(request,os.environ)";
    Command::new("python3")
        .args(["-c", SCRIPT])
        .arg(root)
        .arg(purpose)
        .env(
            "PYTHONPATH",
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .ancestors()
                .nth(4)
                .expect("repository source root")
                .as_os_str(),
        )
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("AGENT_CANON_CHILD_HANDOFF", token)
        .env_remove("AGENT_CANON_ACTIVE_REPOSITORY_ROOT")
        .output()
        .expect("run Python owner token verifier")
}

fn python_owner_issue(root: &Path, purpose: &str) -> String {
    const SCRIPT: &str = "import sys; from pathlib import Path; from tools.repository.workspace.parent_root_side_effects import ParentRootSideEffectBoundary; print(ParentRootSideEffectBoundary().issue_child_handoff(Path(sys.argv[1]),audience=sys.argv[2]))";
    let output = Command::new("python3")
        .args(["-c", SCRIPT])
        .arg(root)
        .arg(purpose)
        .env(
            "PYTHONPATH",
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .ancestors()
                .nth(4)
                .expect("repository source root")
                .as_os_str(),
        )
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env_remove("AGENT_CANON_ACTIVE_REPOSITORY_ROOT")
        .output()
        .expect("run Python owner handoff issuer");
    assert!(
        output.status.success(),
        "Python handoff issuer failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8(output.stdout)
        .expect("Python handoff token is UTF-8")
        .trim()
        .to_owned()
}

fn json_string(value: &str) -> String {
    serde_json::to_string(value).expect("encode fixture string")
}

fn fixture_canonical_owner_body(
    module_path: &str,
    observed_commit: &str,
    observed_tree: &str,
    parent_repo_id: &str,
    physical_parent: &str,
    remote_url: &str,
) -> Vec<u8> {
    // This is a fixed-key-order test oracle, independent of the production
    // canonical serializer. The fixture values are UTF-8 paths and URLs.
    format!(
        "{{\"module_path\":{},\"observed_commit\":{},\"observed_tree\":{},\"parent_repo_id\":{},\"physical_parent\":{},\"remote_url\":{},\"schema\":{}}}",
        json_string(module_path),
        json_string(observed_commit),
        json_string(observed_tree),
        json_string(parent_repo_id),
        json_string(physical_parent),
        json_string(remote_url),
        json_string("agent-canon.owner-evidence.v1"),
    )
    .into_bytes()
}

fn topic_fixture(temp: &TempDir) -> TopicFixture {
    let root = temp.path().to_path_buf();
    let source = root.join("vendor/agent-canon");
    let clone = root.join("workspace/topic/agent-canon");
    let parent_remote = "https://example.invalid/parent.git";
    let source_remote = "https://example.invalid/source.git";
    let clone_remote = "https://example.invalid/clone.git";
    git_repo(&root, parent_remote);
    git_repo(&source, source_remote);
    git_repo(&clone, clone_remote);

    let gitmodules = root.join(".gitmodules");
    fs::write(
        &gitmodules,
        "[submodule \"vendor/agent-canon\"]\n\tpath = vendor/agent-canon\n\turl = https://example.invalid/source.git\n",
    )
    .expect("write .gitmodules fixture");
    let module_raw = fs::read(&gitmodules).expect("read module bytes independently");
    let source_commit = git_stdout(&source, &["rev-parse", "HEAD"]);
    let source_tree = git_stdout(&source, &["rev-parse", "HEAD^{tree}"]);
    let parent_repo_id = sha256_hex(
        format!("{}\0{}", root.display(), parent_remote.trim_end_matches('/')).as_bytes(),
    );
    let gitlink = format!("160000,{source_commit},vendor/agent-canon");
    git_ok(
        &root,
        &["update-index", "--add", "--cacheinfo", gitlink.as_str()],
    );
    let output = Command::new("git")
        .arg("-C")
        .arg(&root)
        .args([
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "gitlink",
        ])
        .output()
        .expect("commit actual gitlink fixture");
    assert!(output.status.success(), "gitlink commit: {}", String::from_utf8_lossy(&output.stderr));

    let module_path = "vendor/agent-canon";
    let owner_body = fixture_canonical_owner_body(
        module_path,
        &source_commit,
        &source_tree,
        &parent_repo_id,
        &root.display().to_string(),
        parent_remote,
    );
    let evidence_sha = sha256_hex(&owner_body);
    let mut owner_value = Map::new();
    owner_value.insert("schema".into(), json!("agent-canon.owner-evidence.v1"));
    owner_value.insert("parent_repo_id".into(), json!(parent_repo_id.clone()));
    owner_value.insert("physical_parent".into(), json!(root.display().to_string()));
    owner_value.insert("module_path".into(), json!(module_path));
    owner_value.insert("remote_url".into(), json!(parent_remote));
    owner_value.insert("observed_commit".into(), json!(source_commit.clone()));
    owner_value.insert("observed_tree".into(), json!(source_tree.clone()));
    owner_value.insert("evidence_sha256".into(), json!(evidence_sha));
    let owner = root.join("owner.json");
    fs::write(
        &owner,
        serde_json::to_vec(&Value::Object(owner_value)).expect("serialize owner evidence"),
    )
    .expect("write owner evidence");
    let owner_sha = sha256_hex(&fs::read(&owner).expect("read owner evidence raw bytes"));

    let mut marker_value = BTreeMap::new();
    marker_value.insert("schema", json!("agent-canon.repository-topic.v2"));
    marker_value.insert("parent_repo_id", json!(parent_repo_id));
    marker_value.insert("topic_slug", json!("topic"));
    marker_value.insert("repo_name", json!("agent-canon"));
    marker_value.insert("clone_path", json!(clone.display().to_string()));
    marker_value.insert("remote_url", json!(clone_remote));
    marker_value.insert("branch", json!("main"));
    marker_value.insert("owner_evidence_sha256", json!(owner_sha));
    marker_value.insert("source_commit", json!(source_commit));
    marker_value.insert("source_tree", json!(source_tree));
    marker_value.insert("created_at", json!("2026-08-10T00:00:00Z"));
    marker_value.insert("nonce", json!("fixture-nonce"));
    let marker = root.join("marker.json");
    fs::write(
        &marker,
        serde_json::to_vec(&marker_value).expect("serialize topic marker"),
    )
    .expect("write topic marker");

    TopicFixture {
        root,
        source,
        clone,
        marker,
        gitmodules,
        owner,
        module_digest: Sha256Digest::from_bytes(Sha256::digest(&module_raw).into()),
    }
}

impl TopicFixture {
    fn request(&self, purpose: &str) -> AttestationRequest {
        let mut request = attestation_request(&self.root, purpose);
        request.source_root = Some(self.source.clone());
        request.clone_root = Some(self.clone.clone());
        request.topic_marker = Some(self.marker.clone());
        request.gitmodules = Some(self.gitmodules.clone());
        request.owner_evidence = Some(self.owner.clone());
        request.expected_module_digest = Some(self.module_digest);
        request
    }
}

fn assert_reject<T: std::fmt::Debug>(result: Result<T, AuthorityError>, expected: ParentRootReject) {
    let error = result.expect_err("authority request must reject");
    assert_eq!(error.reject, expected, "typed authority rejection");
    assert!(error.to_string().starts_with(&format!("{}: ", expected.as_str())));
}

#[test]
fn test_attestation_binds_parent_source_and_clone_identities() {
    let temp = TempDir::new();
    let fixture = topic_fixture(&temp);
    let attested = ParentRootAttestor::new()
        .attest(&fixture.request("topic-test"))
        .expect("valid topic clone relation attests");
    assert_eq!(attested.root_kind().as_str(), "topic");
    assert_eq!(attested.parent_root().path(), fixture.root.as_path());
    assert_eq!(
        attested.source_root().expect("bound source").path(),
        fixture.source.as_path()
    );
    assert_eq!(
        attested.clone_root().expect("bound clone").path(),
        fixture.clone.as_path()
    );
    let observed = fs::metadata(attested.parent_root().path()).expect("stat parent root");
    assert_eq!(attested.parent_identity().device(), observed.dev());
    assert_eq!(attested.parent_identity().inode(), observed.ino());
    attested
        .verify_live_identity()
        .expect("live parent and Git common identities remain bound");

    let mut marker = fs::read(&fixture.marker)
        .ok()
        .and_then(|raw| serde_json::from_slice::<Value>(&raw).ok())
        .expect("read topic marker independently");
    marker["branch"] = json!("tampered");
    fs::write(&fixture.marker, serde_json::to_vec(&marker).expect("serialize marker"))
        .expect("tamper marker branch");
    assert_reject(
        ParentRootAttestor::new().attest(&fixture.request("topic-test")),
        ParentRootReject::MarkerInvalid,
    );

    marker["branch"] = json!("main");
    fs::write(&fixture.marker, serde_json::to_vec(&marker).expect("serialize restored marker"))
        .expect("restore marker branch");
    fs::write(
        &fixture.gitmodules,
        "[submodule \"vendor/agent-canon\"]\n\tpath = vendor/agent-canon\n\turl = https://example.invalid/tampered.git\n",
    )
    .expect("tamper .gitmodules URL");
    assert_reject(
        ParentRootAttestor::new().attest(&fixture.request("topic-test")),
        ParentRootReject::ModuleInvalid,
    );
}

#[test]
fn test_missing_and_spoofed_roots_are_typed() {
    let temp = TempDir::new();
    git_repo(temp.path(), "https://example.invalid/parent.git");
    let missing = temp.path().join("missing");
    let request = attestation_request(&missing, "root-test");
    assert_reject(
        ParentRootAttestor::new().attest(&request),
        ParentRootReject::RootMissing,
    );

    let outside = TempDir::new();
    let mut request = attestation_request(outside.path(), "root-test");
    request.explicit_root = Some(temp.path().to_path_buf());
    assert_reject(
        ParentRootAttestor::new().attest(&request),
        ParentRootReject::RootSpoofed,
    );
}

#[test]
fn test_arbitrary_directory_and_remote_spoof_are_rejected() {
    let temp = TempDir::new();
    let request = attestation_request(temp.path(), "root-test");
    assert_reject(
        ParentRootAttestor::new().attest(&request),
        ParentRootReject::RootMismatch,
    );

    git_repo(temp.path(), "https://example.invalid/actual.git");
    let mut request = attestation_request(temp.path(), "root-test");
    request.expected_remote = Some("https://example.invalid/expected.git".into());
    assert_reject(
        ParentRootAttestor::new().attest(&request),
        ParentRootReject::MarkerInvalid,
    );
    let mut request = attestation_request(temp.path(), "resolved-root-test");
    request.explicit_root = None;
    let resolved = ParentRootAttestor::new()
        .attest(&request)
        .expect("Git resolver selects the actual parent root");
    assert_eq!(resolved.precedence().as_str(), "resolver");
    assert_eq!(resolved.root_kind().as_str(), "standalone");
}

#[test]
fn test_missing_module_digest_and_exact_bound_schema_are_rejected() {
    let temp = TempDir::new();
    git_repo(temp.path(), "https://example.invalid/parent.git");
    let module = temp.path().join(".gitmodules");
    fs::write(&module, "[submodule \"vendor/agent-canon\"]\n")
        .expect("write module fixture");
    let digest = Sha256Digest::from_bytes(
        Sha256::digest(fs::read(&module).expect("read module bytes")).into(),
    );

    let mut request = attestation_request(temp.path(), "root-test");
    request.gitmodules = Some(module.clone());
    request.expected_module_digest = Some(Sha256Digest::from_bytes([0; 32]));
    assert_reject(
        ParentRootAttestor::new().attest(&request),
        ParentRootReject::ModuleInvalid,
    );

    let mut request = attestation_request(temp.path(), "root-test");
    request.expected_module_digest = Some(digest);
    assert_reject(
        ParentRootAttestor::new().attest(&request),
        ParentRootReject::ModuleInvalid,
    );

    let marker = temp.path().join("marker.json");
    fs::write(
        &marker,
        br#"{"schema":"agent-canon.repository-topic.v2","schema":"duplicate"}"#,
    )
    .expect("write duplicate-key marker");
    let mut request = attestation_request(temp.path(), "root-test");
    request.topic_marker = Some(marker);
    assert_reject(
        ParentRootAttestor::new().attest(&request),
        ParentRootReject::MarkerInvalid,
    );
}

#[test]
fn test_regular_nested_git_is_not_a_submodule_gitlink() {
    let temp = TempDir::new();
    git_repo(temp.path(), "https://example.invalid/parent.git");
    let nested = temp.path().join("vendor/nested");
    git_repo(&nested, "https://example.invalid/nested.git");
    let module = temp.path().join(".gitmodules");
    fs::write(
        &module,
        "[submodule \"vendor/nested\"]\n\tpath = vendor/nested\n\turl = https://example.invalid/nested.git\n",
    )
    .expect("write nested module manifest");
    let mut request = attestation_request(temp.path(), "module-check");
    request.source_root = Some(nested);
    request.gitmodules = Some(module);
    assert_reject(
        ParentRootAttestor::new().attest(&request),
        ParentRootReject::ModuleInvalid,
    );
}

#[test]
fn test_handoff_forgery_and_cross_instance_replay_are_rejected() {
    let temp = TempDir::new();
    git_repo(temp.path(), "https://example.invalid/parent.git");
    let attestor = ParentRootAttestor::new();
    let handoff = attestor
        .issue_child_handoff(&ChildHandoffRequest::new(
            temp.path(),
            nonempty("handoff-test-é"),
        ))
        .expect("issue signed handoff");
    assert!(!format!("{:?}", handoff.token()).contains(handoff.token().expose_for_transport()));
    let envelope = verify_handoff_independently(
        handoff.token().expose_for_transport(),
        temp.path(),
    );
    assert_eq!(envelope["payload"]["audience"], "handoff-test-é");
    let python_verification = python_owner_verify(
        handoff.token().expose_for_transport(),
        temp.path(),
        "handoff-test-é",
    );
    assert!(
        python_verification.status.success(),
        "Python owner rejected Rust-issued token: {}",
        String::from_utf8_lossy(&python_verification.stderr)
    );
    let mut request = attestation_request(temp.path(), "handoff-test-é");
    request.child_handoff_token = Some(handoff.token().clone());
    assert!(attestor.attest(&request).expect("consume valid handoff").handoff().is_some());
    assert!(pending_handoff_nonces(temp.path()).is_empty());
    assert_reject(
        ParentRootAttestor::new().attest(&request),
        ParentRootReject::HandoffInvalid,
    );

    let python_temp = TempDir::new();
    git_repo(python_temp.path(), "https://example.invalid/python-issued.git");
    let python_token = python_owner_issue(python_temp.path(), "python-issued-test");
    let mut python_request = attestation_request(python_temp.path(), "python-issued-test");
    python_request.child_handoff_token = Some(SecretToken::from_untrusted(python_token));
    ParentRootAttestor::new()
        .attest(&python_request)
        .expect("Rust owner verifies Python-issued token and consumes shared receipt");

    let mut forged = handoff.token().expose_for_transport().to_owned();
    let index = forged.len().saturating_sub(3);
    let replacement = if forged.as_bytes().get(index) == Some(&b'A') { 'B' } else { 'A' };
    forged.replace_range(index..index + 1, &replacement.to_string());
    request.child_handoff_token = Some(SecretToken::from_untrusted(forged));
    assert_reject(
        ParentRootAttestor::new().attest(&request),
        ParentRootReject::HandoffInvalid,
    );
}

#[test]
fn test_handoff_nonce_receipt_survives_a_new_process() {
    const CHILD_ROOT: &str = "AGENT_CANON_NATIVE_AUTHORITY_TEST_ROOT";
    const CHILD_TOKEN: &str = "AGENT_CANON_NATIVE_AUTHORITY_TEST_TOKEN";
    if let (Ok(root), Ok(token)) = (std::env::var(CHILD_ROOT), std::env::var(CHILD_TOKEN)) {
        let root = PathBuf::from(root);
        let mut request = attestation_request(&root, "process-handoff-test");
        request.child_handoff_token = Some(SecretToken::from_untrusted(token));
        std::process::exit(if ParentRootAttestor::new().attest(&request).is_ok() {
            0
        } else {
            17
        });
    }

    let temp = TempDir::new();
    git_repo(temp.path(), "https://example.invalid/parent.git");
    let token = ParentRootAttestor::new()
        .issue_child_handoff(&ChildHandoffRequest::new(
            temp.path(),
            nonempty("process-handoff-test"),
        ))
        .expect("issue process handoff")
        .token()
        .expose_for_transport()
        .to_owned();
    let executable = std::env::current_exe().expect("current test process path");
    let run_child = || {
        Command::new(&executable)
            .args([
                "--exact",
                "test_handoff_nonce_receipt_survives_a_new_process",
                "--nocapture",
            ])
            .env(CHILD_ROOT, temp.path())
            .env(CHILD_TOKEN, token.as_str())
            .env_remove("AGENT_CANON_ACTIVE_REPOSITORY_ROOT")
            .output()
            .expect("start fresh native test process")
    };
    let first = run_child();
    assert!(first.status.success(), "first process did not consume handoff: {}", String::from_utf8_lossy(&first.stderr));
    let replay = run_child();
    assert!(!replay.status.success(), "fresh process accepted replayed nonce");
}

#[test]
fn test_handoff_source_and_clone_bindings_are_symmetric() {
    let temp = TempDir::new();
    git_repo(temp.path(), "https://example.invalid/parent.git");
    let source = temp.path().join("source");
    git_repo(&source, "https://example.invalid/source.git");
    let attestor = ParentRootAttestor::new();

    let mut with_source = ChildHandoffRequest::new(temp.path(), nonempty("binding-test"));
    with_source.source_root = Some(source.clone());
    let token_with_source = attestor
        .issue_child_handoff(&with_source)
        .expect("issue source-bound handoff");
    let mut request = attestation_request(temp.path(), "binding-test");
    request.child_handoff_token = Some(token_with_source.token().clone());
    assert_reject(attestor.attest(&request), ParentRootReject::HandoffInvalid);

    let token_without_source = attestor
        .issue_child_handoff(&ChildHandoffRequest::new(
            temp.path(),
            nonempty("binding-test"),
        ))
        .expect("issue source-free handoff");
    let mut request = attestation_request(temp.path(), "binding-test");
    request.source_root = Some(source);
    request.child_handoff_token = Some(token_without_source.token().clone());
    assert_reject(attestor.attest(&request), ParentRootReject::HandoffInvalid);

    let topic_temp = TempDir::new();
    let topic = topic_fixture(&topic_temp);
    let mut with_clone =
        ChildHandoffRequest::new(topic.root.clone(), nonempty("clone-binding-test"));
    with_clone.clone_root = Some(topic.clone.clone());
    let token_with_clone = attestor
        .issue_child_handoff(&with_clone)
        .expect("issue clone-bound handoff");
    let mut request = attestation_request(&topic.root, "clone-binding-test");
    request.child_handoff_token = Some(token_with_clone.token().clone());
    assert_reject(attestor.attest(&request), ParentRootReject::HandoffInvalid);

    let token_without_clone = attestor
        .issue_child_handoff(&ChildHandoffRequest::new(
            topic.root.clone(),
            nonempty("clone-binding-test"),
        ))
        .expect("issue clone-free handoff");
    let mut request = topic.request("clone-binding-test");
    request.child_handoff_token = Some(token_without_clone.token().clone());
    assert_reject(attestor.attest(&request), ParentRootReject::HandoffInvalid);
}

#[test]
fn test_handoff_is_single_use_and_rejects_mutation_or_expiry() {
    let temp = TempDir::new();
    git_repo(temp.path(), "https://example.invalid/parent.git");
    let attestor = ParentRootAttestor::new();
    let mut issuance = ChildHandoffRequest::new(temp.path(), nonempty("single-use-test"));
    issuance.ttl = Duration::from_secs(30);
    let token = attestor
        .issue_child_handoff(&issuance)
        .expect("issue short-lived handoff");
    let mut request = attestation_request(temp.path(), "single-use-test");
    request.child_handoff_token = Some(token.token().clone());
    assert!(attestor.attest(&request).expect("consume handoff").handoff().is_some());
    assert_reject(attestor.attest(&request), ParentRootReject::HandoffInvalid);

    let mut expiring = ChildHandoffRequest::new(temp.path(), nonempty("expiry-test"));
    expiring.ttl = Duration::from_secs(1);
    let expired = attestor
        .issue_child_handoff(&expiring)
        .expect("issue expiring handoff");
    std::thread::sleep(Duration::from_millis(1_050));
    let mut request = attestation_request(temp.path(), "expiry-test");
    request.child_handoff_token = Some(expired.token().clone());
    assert_reject(
        ParentRootAttestor::new().attest(&request),
        ParentRootReject::HandoffInvalid,
    );
}

#[test]
fn test_child_reattest_requires_handoff_even_when_root_env_is_present() {
    let temp = TempDir::new();
    git_repo(temp.path(), "https://example.invalid/parent.git");
    let attestor = ParentRootAttestor::new();
    let request = attestation_request(temp.path(), "reattest-test");
    let initial = attestor.attest(&request).expect("parent root initially attests");
    assert_eq!(initial.parent_root().path(), temp.path());

    let token = attestor
        .issue_child_handoff(&ChildHandoffRequest::new(
            temp.path(),
            nonempty("reattest-test"),
        ))
        .expect("issue child handoff")
        .token()
        .clone();
    let mut child_request = request.clone();
    child_request.child_handoff_token = Some(token);
    assert_eq!(
        attestor
            .reattest_child(&child_request)
            .expect("child reattests with its bearer token")
            .parent_root()
            .path(),
        temp.path()
    );
    assert_reject(
        attestor.reattest_child(&request),
        ParentRootReject::HandoffInvalid,
    );
}

#[test]
fn test_verify_child_rejects_forged_purpose_without_handoff() {
    let temp = TempDir::new();
    git_repo(temp.path(), "https://example.invalid/parent.git");
    let request = attestation_request(temp.path(), "forged-child");
    assert_reject(
        ParentRootAttestor::new().reattest_child(&request),
        ParentRootReject::HandoffInvalid,
    );
}
