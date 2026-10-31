// @dependency-start
// contract test
// responsibility Validates the public read-only environment dependency resolver against standalone manifest and receipt inputs.
// upstream implementation ../src/environment_dependencies.rs owns full plan identity and verified executable resolution
// downstream test ../../../../container/tests/test_devcontainer_dependencies.py remains the complete installer and receipt semantics baseline
// @dependency-end

use agent_canon::artifacts::artifact_identity::canonical_json_ascii_bytes;
use agent_canon::environment_dependencies::resolve_verified_executable;
use serde_json::json;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct TempRoot(PathBuf);

impl TempRoot {
    fn new() -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock is after epoch")
            .as_nanos();
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-environment-api-{}-{sequence}-{nonce}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("temporary test root is created");
        Self(path)
    }

    fn write(&self, relative: &str, value: &str) -> PathBuf {
        let path = self.0.join(relative);
        fs::create_dir_all(path.parent().expect("fixture has parent"))
            .expect("fixture parent is created");
        fs::write(&path, value).expect("fixture is written");
        path
    }
}

impl Drop for TempRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

const RELEASE_MANIFEST: &str = r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "fixture-release"
package = "fixture-release"
method = "release-asset"
version = "1.2.3"
source = "https://example.invalid/fixture-release"
checksum = "0000000000000000000000000000000000000000000000000000000000000000"
asset = "fixture-release"
archive_format = "binary"
extract = "none"
destination = "/usr/local/bin/fixture-release"
deps = []
provides = ["fixture-release"]
failure_policy = "fail"

[records.verification]
kind = "absolute-executable"
path = "/usr/local/bin/fixture-release"
args = ["--version"]
output_contains = "1.2.3"
"#;

fn fingerprint(value: &serde_json::Value) -> String {
    Sha256::digest(canonical_json_ascii_bytes(value).expect("fixture identity encodes"))
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn release_record_payload() -> serde_json::Value {
    json!({
        "id": "fixture-release",
        "package": "fixture-release",
        "method": "release-asset",
        "version": "1.2.3",
        "source": "https://example.invalid/fixture-release",
        "verification": {
            "kind": "absolute-executable",
            "executable": null,
            "path": "/usr/local/bin/fixture-release",
            "args": ["--version"],
            "output_contains": "1.2.3",
            "executable_globs": []
        },
        "deps": [],
        "provides": ["fixture-release"],
        "failure_policy": "fail",
        "platform": null,
        "platforms": [],
        "key_fingerprint": null,
        "key_url": null,
        "repository_suite": null,
        "repository_components": [],
        "repository_packages_sha256": null,
        "repository_package_url": null,
        "repository_package_sha256": null,
        "repository_packages_sha256s": [],
        "repository_package_urls": [],
        "repository_package_sha256s": [],
        "checksum": "0000000000000000000000000000000000000000000000000000000000000000",
        "checksums": [],
        "asset": "fixture-release",
        "assets": [],
        "archive_format": "binary",
        "extract": "none",
        "destination": "/usr/local/bin/fixture-release",
        "executable_owner_packages": [],
        "repo": null,
        "commit": null,
        "source_identity": null,
        "source_tree_sha256": null,
        "cargo_lock_sha256": null,
        "locked": null,
        "browser": null,
        "browser_cache_path": null,
        "components": []
    })
}

fn valid_release_receipt() -> serde_json::Value {
    let record = release_record_payload();
    let record_fingerprint = fingerprint(&record);
    let plan = json!({
        "source_roles": ["canonical"],
        "records": [record],
        "order": ["fixture-release"],
        "dependency_providers": [["fixture-release", []]]
    });
    json!({
        "schema": "agent-canon.tool-dependency-receipt",
        "status": "pass",
        "record_id": "fixture-release",
        "manifest_version": "1.2.3",
        "record_fingerprint": record_fingerprint,
        "plan_fingerprint": fingerprint(&plan),
        "verification": {
            "kind": "absolute-executable",
            "executable": null,
            "path": "/usr/local/bin/fixture-release",
            "args": ["--version"],
            "output_contains": "1.2.3",
            "executable_globs": []
        },
        "repository_packages": null,
        "repository_package": null,
        "executable_bindings": {}
    })
}

#[test]
fn public_resolver_builds_the_complete_default_plan_before_receipt_lookup() {
    let repository = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../../")
        .canonicalize()
        .expect("repository root exists");
    let receipts = repository.join("target/absent-native-dependency-receipts");
    let error =
        resolve_verified_executable(&repository, &receipts, "scip-python", "scip-python", None)
            .expect_err("fixture intentionally has no receipt");
    assert!(error
        .to_string()
        .contains("executable receipt is unreadable"));
}

#[test]
fn public_resolver_rejects_a_command_not_owned_by_the_manifest_record() {
    let root = TempRoot::new();
    let manifest = root.write("dependencies.toml", RELEASE_MANIFEST);
    let receipt = root.write(
        "receipts/fixture-release.json",
        &serde_json::to_string(&valid_release_receipt()).expect("valid receipt serializes"),
    );
    let error = resolve_verified_executable(
        &root.0,
        receipt.parent().expect("receipt directory exists"),
        "fixture-release",
        "different-name",
        Some(&manifest),
    )
    .expect_err("release executable name is record-owned");
    assert!(error
        .to_string()
        .contains("requested executable does not match its declared absolute path"));
}

#[test]
fn public_resolver_rejects_stale_full_plan_fingerprints_before_running_a_probe() {
    let root = TempRoot::new();
    let manifest = root.write("dependencies.toml", RELEASE_MANIFEST);
    let receipt = json!({
        "schema": "agent-canon.tool-dependency-receipt",
        "status": "pass",
        "record_id": "fixture-release",
        "manifest_version": "1.2.3",
        "plan_fingerprint": "0".repeat(64),
        "record_fingerprint": "0".repeat(64),
        "verification": {
            "kind": "absolute-executable",
            "executable": null,
            "path": "/usr/local/bin/fixture-release",
            "args": ["--version"],
            "output_contains": "1.2.3",
            "executable_globs": []
        },
        "repository_packages": null,
        "repository_package": null,
        "executable_bindings": {}
    });
    let receipt_path = root.write(
        "receipts/fixture-release.json",
        &serde_json::to_string(&receipt).expect("receipt fixture serializes"),
    );
    let error = resolve_verified_executable(
        &root.0,
        receipt_path.parent().expect("receipt root exists"),
        "fixture-release",
        "fixture-release",
        Some(&manifest),
    )
    .expect_err("zero fingerprints are intentionally stale");
    assert!(error
        .to_string()
        .contains("executable receipt binding is stale"));
}

#[test]
fn public_resolver_keeps_unported_methods_explicitly_unsupported() {
    let root = TempRoot::new();
    let manifest = root.write(
        "dependencies.toml",
        r#"
schema = "agent-canon.tool-dependencies"
schema_version = 2

[[records]]
id = "fixture-pipx"
package = "fixture-pipx"
method = "pipx"
version = "1.2.3"
source = "https://pypi.org/simple"
deps = []
provides = ["fixture-pipx"]
failure_policy = "fail"

[records.verification]
kind = "pipx-package"
executable = "fixture-pipx"
args = ["--version"]
output_contains = "1.2.3"
"#,
    );
    let error = resolve_verified_executable(
        &root.0,
        &root.0.join("receipts"),
        "fixture-pipx",
        "fixture-pipx",
        Some(&manifest),
    )
    .expect_err("pipx live verification is outside this native slice");
    assert!(error
        .to_string()
        .contains("native read-only verification is not implemented for pipx"));
}
