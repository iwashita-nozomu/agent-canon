// @dependency-start
// contract test
// responsibility Verifies public Lean proof environment planning, result schema, and error boundaries.
// upstream implementation ../src/lean_proof_env.rs owns the native command API
// @dependency-end

use agent_canon::lean_proof_env::{
    build_result, render_text, LeanProofEnvArgs, OutputFormat, DEFAULT_PACKAGE_NAME,
};
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct TempRoot(PathBuf);

impl TempRoot {
    fn new() -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock after epoch")
            .as_nanos();
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!(
            "agent-canon-lean-proof-env-api-{}-{sequence}-{nonce}",
            std::process::id()
        ));
        fs::create_dir_all(&root).expect("temporary API root is created");
        Self(root)
    }
}

impl Drop for TempRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn public_api_returns_an_unexecuted_plan_without_creating_the_selected_directory() {
    let root = TempRoot::new();
    let env_dir = root.0.join("absent");
    let result = build_result(&LeanProofEnvArgs {
        action: "all-smoke".to_owned(),
        env_dir: env_dir.clone(),
        lean_toolchain: Some("leanprover/lean4:v4.30.0".to_owned()),
        package_name: DEFAULT_PACKAGE_NAME.to_owned(),
        lean_file: None,
        execute: false,
        format: OutputFormat::Json,
    })
    .expect("a dry run with an exact toolchain produces a plan");

    assert_eq!(result.status, "dry_run");
    assert!(!result.executed);
    assert!(!env_dir.exists());
    assert!(result.created_or_updated_files.is_empty());
    assert!(result.command_results.is_empty());
    assert_eq!(result.lean_toolchain, None);
    assert_eq!(
        result.commands[0],
        "lake +leanprover/lean4:v4.30.0 init agent_canon_lean_proof_env math"
    );
    assert_eq!(result.commands.len(), 7);

    let serialized = serde_json::to_value(&result).expect("public result serializes");
    let object = serialized.as_object().expect("result is a mapping");
    assert!(object.contains_key("created_or_updated_files"));
    assert!(object.contains_key("command_results"));
    assert_eq!(object["action"], "all-smoke");
    assert_eq!(object["executed"], false);

    let rendered = render_text(&result);
    assert!(rendered.contains("LEAN_PROOF_ENV_STATUS=dry_run"));
    assert!(rendered.contains("LEAN_PROOF_ENV_EXECUTED=no"));
    assert!(rendered.contains(&result.commands[0]));
}

#[test]
fn check_file_requires_a_selected_source_before_creating_any_directory() {
    let root = TempRoot::new();
    let env_dir = root.0.join("absent");
    let error = build_result(&LeanProofEnvArgs {
        action: "check-file".to_owned(),
        env_dir: env_dir.clone(),
        lean_toolchain: Some("leanprover/lean4:v4.30.0".to_owned()),
        package_name: DEFAULT_PACKAGE_NAME.to_owned(),
        lean_file: None,
        execute: true,
        format: OutputFormat::Json,
    })
    .expect_err("check-file requires an input path");

    assert_eq!(error, "--lean-file is required for check-file");
    assert!(!env_dir.exists());
}
