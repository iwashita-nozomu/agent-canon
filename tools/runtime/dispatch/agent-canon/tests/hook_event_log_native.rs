#![cfg(target_os = "linux")]

use agent_canon::authority::{
    AttestationRequest, AttestedParent, NonEmptyTrimmedString, Nonce128, ParentRootAttestor,
};
use agent_canon::hook_event_log::{
    canonical_hook_event_bytes, compact_timestamp, safe_slug, utc_now, HookAppendResult,
    HookLogContext, HOOK_EVENT_SPOOL_DIR_ENV, HOOK_RESULTS_DIR_ENV, HOOK_RUN_NAMESPACE_ENV,
    HOOK_SOURCE_ROOT_ENV,
};
use agent_canon::log_repository_identity::{
    normalize_remote, repo_log_key, stable_source_id_from_runtime_env, stable_source_repository_id,
    SOURCE_REMOTE_ENV, STABLE_ID_ENV,
};
use agent_canon::python_json::{parse_json, JsonString, JsonValue};
use agent_canon::runtime_boundary::RUNTIME_ROOT_ENV;
use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Barrier};
use std::thread;

static NEXT_TEMP: AtomicUsize = AtomicUsize::new(0);

struct TempDir(PathBuf);

impl TempDir {
    fn new() -> Self {
        let suffix = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-hook-event-native-{}-{suffix}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("create isolated hook fixture");
        Self(fs::canonicalize(path).expect("canonicalize hook fixture"))
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

fn run_git(root: &Path, args: &[&str]) -> Output {
    Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .expect("run test fixture Git command")
}

fn git_ok(root: &Path, args: &[&str]) {
    let output = run_git(root, args);
    assert!(
        output.status.success(),
        "git {args:?}: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}

fn git_repo(root: &Path, remote: &str) {
    fs::create_dir_all(root).expect("create Git fixture root");
    let output = Command::new("git")
        .args(["init", "-q", "-b", "main"])
        .arg(root)
        .output()
        .expect("initialize Git fixture");
    assert!(
        output.status.success(),
        "git init: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    git_ok(root, &["remote", "add", "origin", remote]);
    git_ok(
        root,
        &[
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "fixture",
        ],
    );
}

fn nonempty(value: impl Into<String>) -> NonEmptyTrimmedString {
    NonEmptyTrimmedString::new(value).expect("fixture purpose is non-empty")
}

fn attested_parent(root: &Path) -> AttestedParent {
    let request = AttestationRequest {
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
        purpose: nonempty("hook-event-spool"),
        nonce: Nonce128::generate().expect("OS CSPRNG supplies a request nonce"),
    };
    ParentRootAttestor::new()
        .attest(&request)
        .expect("fixture parent root attests")
}

fn field<'a>(value: &'a JsonValue, name: &str) -> Option<&'a JsonValue> {
    let JsonValue::Object(object) = value else {
        return None;
    };
    object
        .0
        .iter()
        .rev()
        .find(|(key, _)| key.equals_text(name))
        .map(|(_, value)| value)
}

fn text(value: &JsonValue) -> String {
    let JsonValue::String(value) = value else {
        panic!("expected string value")
    };
    value.to_text().expect("golden string is Unicode")
}

fn bool_value(value: &JsonValue) -> bool {
    match value {
        JsonValue::Bool(value) => *value,
        _ => panic!("expected boolean value"),
    }
}

fn hook_entry_with_thread(run_id: &str, status: &str) -> JsonValue {
    let mut entry = hook_entry(run_id, status);
    let JsonValue::Object(object) = &mut entry else {
        unreachable!()
    };
    object.0.push((
        JsonString::from_text("codex_thread_id"),
        JsonValue::String(JsonString::from_text("caller-thread")),
    ));
    entry
}

fn hook_entry(run_id: &str, status: &str) -> JsonValue {
    parse_json(&format!(
        r#"{{"hook_run_id":"{run_id}","timestamp":"2026-07-18T00:00:00Z","payload_fingerprint":"fingerprint-{run_id}","status":"{status}"}}"#
    ))
    .expect("construct hook event input")
}

fn environment(values: &[(&str, &str)]) -> BTreeMap<String, String> {
    values
        .iter()
        .map(|(name, value)| ((*name).to_owned(), (*value).to_owned()))
        .collect()
}

fn event_result(
    context: &HookLogContext,
    parent: &AttestedParent,
    run_id: &str,
) -> HookAppendResult {
    context.append(hook_entry(run_id, "pass"), Some(parent))
}

#[test]
fn test_hook_event_bytes_match_python_golden_corpus() {
    let golden = parse_json(include_str!(
        "../../../../../tests/fixtures/hook_event_log/python_golden.json"
    ))
    .expect("parse frozen Python hook event corpus");
    let cases = match field(&golden, "cases").expect("golden cases") {
        JsonValue::Array(cases) => &cases.0,
        _ => panic!("golden cases are an array"),
    };
    assert_eq!(cases.len(), 28);
    for case in cases {
        let name = text(field(case, "name").expect("case name"));
        let accepted = bool_value(field(case, "accepted").expect("accepted value"));
        let input = field(case, "input").expect("case input");
        let result = canonical_hook_event_bytes(input);
        if accepted {
            let expected = STANDARD
                .decode(text(field(case, "output_base64").expect("golden bytes")).as_bytes())
                .expect("decode frozen Python bytes");
            assert_eq!(result.expect(&name), expected, "{name}");
        } else {
            assert_eq!(
                result.expect_err(&name),
                text(field(case, "observed_error").expect("Python error code")),
                "{name}"
            );
        }
    }

    let slugs = match field(&golden, "slugs").expect("slug cases") {
        JsonValue::Array(values) => &values.0,
        _ => panic!("slug cases are an array"),
    };
    for case in slugs {
        assert_eq!(
            safe_slug(&text(field(case, "input").expect("slug input"))),
            text(field(case, "output").expect("slug output"))
        );
    }

    let timestamps = match field(&golden, "timestamps").expect("timestamp cases") {
        JsonValue::Array(values) => &values.0,
        _ => panic!("timestamp cases are an array"),
    };
    for case in timestamps {
        assert_eq!(
            compact_timestamp(&text(field(case, "input").expect("timestamp input"))),
            text(field(case, "output").expect("timestamp output"))
        );
    }

    let timestamp = utc_now();
    assert!(timestamp.ends_with('Z'));
    assert!(timestamp.len() == 20 || timestamp.len() == 27);
    let context = HookLogContext {
        active_root: PathBuf::new(),
        hook_name: "PostToolUse".to_owned(),
        override_path: String::new(),
        environment: BTreeMap::new(),
    };
    let run_id = context
        .run_id("2026-01-01T00:00:00Z", "fingerprint")
        .expect("create unique event identity");
    let suffix = run_id
        .strip_prefix("hook-20260101T000000Z-")
        .expect("run id contains compact timestamp");
    let (digest, nonce) = suffix.split_once('-').expect("run id has digest and nonce");
    assert_eq!(digest.len(), 10);
    assert_eq!(nonce.len(), 10);
    assert!(digest
        .bytes()
        .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()));
    assert!(nonce
        .bytes()
        .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()));
}

#[test]
fn test_log_repository_identity_matches_python_golden_corpus() {
    let golden = parse_json(include_str!(
        "../../../../../tests/fixtures/log_repository_identity/python_golden.json"
    ))
    .expect("parse frozen Python log identity corpus");
    let cases = match field(&golden, "cases").expect("identity cases") {
        JsonValue::Array(cases) => &cases.0,
        _ => panic!("identity cases are an array"),
    };
    assert_eq!(cases.len(), 14);
    for case in cases {
        let remote = text(field(case, "input").expect("remote input"));
        let result = normalize_remote(&remote);
        if bool_value(field(case, "accepted").expect("accepted value")) {
            let normalized = result.expect("valid remote");
            assert_eq!(
                normalized,
                text(field(case, "normalized").expect("normalized remote"))
            );
            assert_eq!(
                stable_source_repository_id(&remote).unwrap(),
                text(field(case, "stable_id").expect("stable source id"))
            );
        } else {
            let error = result.expect_err("invalid remote");
            let expected_error = text(field(case, "error").expect("error code"));
            assert_eq!(error.code(), Some(expected_error.as_str()));
        }
    }

    let root = TempDir::new();
    git_repo(root.path(), "https://github.com/Owner/Repo.git");
    let empty_environment = BTreeMap::new();
    assert_eq!(
        repo_log_key(root.path(), &empty_environment).unwrap(),
        "github.com-owner-repo-620c3a937ce854b7477cb210"
    );
    assert_eq!(
        stable_source_id_from_runtime_env(None, &empty_environment).unwrap(),
        "unidentified-source"
    );
    let remote_environment =
        environment(&[(SOURCE_REMOTE_ENV, "https://github.com/Owner/Repo.git")]);
    assert_eq!(
        stable_source_id_from_runtime_env(None, &remote_environment).unwrap(),
        "github.com-owner-repo-620c3a937ce854b7477cb210"
    );
    let matching_override = environment(&[
        (SOURCE_REMOTE_ENV, "https://github.com/Owner/Repo.git"),
        (
            STABLE_ID_ENV,
            "github.com-owner-repo-620c3a937ce854b7477cb210",
        ),
    ]);
    assert_eq!(
        stable_source_id_from_runtime_env(None, &matching_override).unwrap(),
        "github.com-owner-repo-620c3a937ce854b7477cb210"
    );
    let mismatch = environment(&[
        (SOURCE_REMOTE_ENV, "https://github.com/Owner/Repo.git"),
        (STABLE_ID_ENV, "wrong-id"),
    ]);
    assert_eq!(
        stable_source_id_from_runtime_env(None, &mismatch)
            .unwrap_err()
            .code(),
        Some("source_repository_id_mismatch")
    );
}

#[test]
fn test_hook_context_paths_preserve_override_and_runtime_namespace_precedence() {
    let source = TempDir::new();
    git_repo(source.path(), "https://github.com/Owner/Repo.git");
    let runtime = TempDir::new();
    let runtime_environment = environment(&[
        (RUNTIME_ROOT_ENV, runtime.path().to_str().unwrap()),
        (SOURCE_REMOTE_ENV, "https://github.com/Owner/Repo.git"),
        (HOOK_RUN_NAMESPACE_ENV, "  A B_C.D-E  "),
        ("DEVCONTAINER_PROJECT_NAME", "ignored-project"),
        ("COMPOSE_PROJECT_NAME", "ignored-compose"),
    ]);
    let default_context = HookLogContext {
        active_root: source.path().to_path_buf(),
        hook_name: "PostToolUse".to_owned(),
        override_path: String::new(),
        environment: runtime_environment.clone(),
    };
    let repository_key = "github.com-owner-repo-620c3a937ce854b7477cb210";
    let expected_root = runtime
        .path()
        .join("spool/hook-events")
        .join(repository_key);
    assert_eq!(default_context.spool_root().unwrap(), expected_root);
    assert_eq!(default_context.runtime_namespace(), "a-b_c.d-e");
    assert_eq!(
        default_context.event_path("event-a").unwrap(),
        expected_root.join("a-b_c.d-e/posttooluse/event-a.json")
    );

    let source_override = TempDir::new();
    git_repo(
        source_override.path(),
        "https://example.invalid/override.git",
    );
    let source_context = HookLogContext {
        environment: environment(&[(
            HOOK_SOURCE_ROOT_ENV,
            source_override.path().to_str().unwrap(),
        )]),
        ..default_context.clone()
    };
    assert_eq!(
        source_context.source_root().unwrap(),
        source_override.path()
    );

    let devcontainer_context = HookLogContext {
        environment: environment(&[
            ("DEVCONTAINER_PROJECT_NAME", "devcontainer-name"),
            ("COMPOSE_PROJECT_NAME", "compose-name"),
        ]),
        ..default_context.clone()
    };
    assert_eq!(
        devcontainer_context.runtime_namespace(),
        "devcontainer-name"
    );
    let compose_context = HookLogContext {
        environment: environment(&[("COMPOSE_PROJECT_NAME", "compose-name")]),
        ..default_context.clone()
    };
    assert_eq!(compose_context.runtime_namespace(), "compose-name");
    assert_eq!(
        HookLogContext {
            environment: BTreeMap::new(),
            ..default_context.clone()
        }
        .runtime_namespace(),
        "unknown-runtime"
    );

    let spool_override = runtime.path().join("spool/selected-events");
    let mut override_environment = runtime_environment.clone();
    override_environment.insert(
        HOOK_EVENT_SPOOL_DIR_ENV.to_owned(),
        spool_override.display().to_string(),
    );
    let override_context = HookLogContext {
        environment: override_environment,
        ..default_context.clone()
    };
    assert_eq!(
        override_context.spool_root().unwrap(),
        spool_override.join(repository_key)
    );

    let results_dir = source.path().join("legacy-results");
    let legacy_context = HookLogContext {
        active_root: source.path().to_path_buf(),
        hook_name: "PostToolUse".to_owned(),
        override_path: String::new(),
        environment: environment(&[(HOOK_RESULTS_DIR_ENV, results_dir.to_str().unwrap())]),
    };
    assert!(legacy_context.explicit_log_sink());
    assert_eq!(
        legacy_context.spool_root().unwrap(),
        results_dir.join(".event-spool")
    );

    let explicit_path = source.path().join("legacy-hook.jsonl");
    let direct_context = HookLogContext {
        active_root: source.path().to_path_buf(),
        hook_name: "PostToolUse".to_owned(),
        override_path: explicit_path.display().to_string(),
        environment: BTreeMap::new(),
    };
    assert!(direct_context.explicit_log_sink());
    assert_eq!(
        direct_context.spool_root().unwrap(),
        PathBuf::from(format!("{}.events", explicit_path.display()))
    );
    assert_eq!(direct_context.runtime_namespace(), "direct-log-override");
    assert_eq!(
        direct_context.event_path("run-a").unwrap(),
        PathBuf::from(format!(
            "{}.events/direct-log-override/posttooluse/run-a.json",
            explicit_path.display()
        ))
    );
}

#[test]
fn test_hook_append_writes_independent_ascii_bytes_and_classifies_no_replace_results() {
    let root = TempDir::new();
    git_repo(root.path(), "https://example.invalid/hook-parent.git");
    let parent = Arc::new(attested_parent(root.path()));
    let override_path = root.path().join("legacy-hook.jsonl");
    let context = Arc::new(HookLogContext {
        active_root: root.path().to_path_buf(),
        hook_name: "Post Tool Use".to_owned(),
        override_path: override_path.display().to_string(),
        environment: environment(&[
            (SOURCE_REMOTE_ENV, "https://github.com/Owner/Repo.git"),
            (HOOK_RUN_NAMESPACE_ENV, "Test Runtime"),
            ("CODEX_THREAD_ID", "trace-from-thread"),
            ("CODEX_SESSION_ID", "trace-from-session"),
        ]),
    });

    let event = hook_entry_with_thread("event-a", "pass");
    let expected = b"{\"codex_thread_id\":\"caller-thread\",\"codex_trace_key\":\"trace-from-thread\",\"hook_log_namespace\":\"test-runtime\",\"hook_run_id\":\"event-a\",\"payload_fingerprint\":\"fingerprint-event-a\",\"source_repo_key\":\"github.com-owner-repo-620c3a937ce854b7477cb210\",\"status\":\"pass\",\"timestamp\":\"2026-07-18T00:00:00Z\"}\n";
    let first = context.append(event, Some(&parent));
    assert_eq!(
        (first.status.as_str(), first.error_code.as_str()),
        ("spooled", "")
    );
    assert_eq!(
        first.spool_path,
        root.path()
            .join("legacy-hook.jsonl.events/test-runtime/post-tool-use/event-a.json")
    );
    assert_eq!(fs::read(&first.spool_path).unwrap(), expected);
    assert_eq!(first.event_sha256, sha256_hex(expected));

    let duplicate = context.append(hook_entry_with_thread("event-a", "pass"), Some(&parent));
    assert_eq!(
        (duplicate.status.as_str(), duplicate.error_code.as_str()),
        ("duplicate", "")
    );
    let conflict = context.append(hook_entry_with_thread("event-a", "warn"), Some(&parent));
    assert_eq!(
        (conflict.status.as_str(), conflict.error_code.as_str()),
        ("failed", "spool_conflict")
    );
    assert_eq!(fs::read(&first.spool_path).unwrap(), expected);

    let unattested = context.append(hook_entry("event-unattested", "pass"), None);
    assert_eq!(
        (unattested.status.as_str(), unattested.error_code.as_str()),
        ("failed", "parent_unattested")
    );
    assert!(!unattested.spool_path.exists());

    let barrier = Arc::new(Barrier::new(3));
    let handles = ["event-b", "event-c"]
        .into_iter()
        .map(|run_id| {
            let context = Arc::clone(&context);
            let parent = Arc::clone(&parent);
            let barrier = Arc::clone(&barrier);
            thread::spawn(move || {
                barrier.wait();
                event_result(&context, &parent, run_id)
            })
        })
        .collect::<Vec<_>>();
    barrier.wait();
    let distinct = handles
        .into_iter()
        .map(|handle| handle.join().expect("join distinct hook event"))
        .collect::<Vec<_>>();
    assert!(distinct.iter().all(|result| result.status == "spooled"));
    assert_ne!(distinct[0].spool_path, distinct[1].spool_path);
    for result in distinct {
        let bytes = fs::read(&result.spool_path).unwrap();
        assert!(bytes.ends_with(b"\n"));
        assert_eq!(result.event_sha256, sha256_hex(&bytes));
    }

    let barrier = Arc::new(Barrier::new(3));
    let handles = (0..2)
        .map(|_| {
            let context = Arc::clone(&context);
            let parent = Arc::clone(&parent);
            let barrier = Arc::clone(&barrier);
            thread::spawn(move || {
                barrier.wait();
                event_result(&context, &parent, "event-contended")
            })
        })
        .collect::<Vec<_>>();
    barrier.wait();
    let contended = handles
        .into_iter()
        .map(|handle| handle.join().expect("join contended hook event"))
        .collect::<Vec<_>>();
    let mut statuses = contended
        .iter()
        .map(|result| result.status.as_str())
        .collect::<Vec<_>>();
    statuses.sort_unstable();
    assert_eq!(statuses, ["duplicate", "spooled"]);
    assert_eq!(contended[0].spool_path, contended[1].spool_path);
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
