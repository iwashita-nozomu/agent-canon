// @dependency-start
// contract test
// responsibility Verifies source-root binding, exact allowed subtrees, and no-follow source writes.
// upstream implementation ../src/source_mutation.rs owns the explicit source-mutation capability
// downstream implementation ../src/docs.rs uses the capability for native link rewrites
// @dependency-end

use agent_canon::source_mutation::SourceMutationCapability;
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
            "agent-canon-source-mutation-{}-{sequence}-{nonce}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("temporary source root is created");
        Self(path.canonicalize().expect("temporary root is canonical"))
    }

    fn write(&self, relative: &str, text: &str) -> PathBuf {
        let path = self.0.join(relative);
        fs::create_dir_all(path.parent().expect("fixture has parent"))
            .expect("fixture parent is created");
        fs::write(&path, text).expect("fixture is written");
        path
    }
}

impl Drop for TempRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn capability(root: &Path, allowed_paths: &[&str]) -> SourceMutationCapability {
    let json = serde_json::json!({
        "allowed_paths": allowed_paths,
        "purpose": "link-repair",
        "authority": "issue-1630"
    });
    SourceMutationCapability::from_json(
        root,
        Some(&serde_json::to_string(&json).expect("capability serializes")),
    )
    .expect("exact capability parses")
}

#[test]
fn source_capability_binds_root_and_exact_allowed_subtree() {
    let root = TempRoot::new();
    let guide = root.write("docs/guide.md", "before\n");
    let capability = capability(&root.0, &["docs/guide.md"]);
    assert_eq!(
        capability
            .assert_allowed(&guide)
            .expect("allowed file resolves"),
        guide.canonicalize().expect("file is canonical")
    );
    assert!(capability
        .assert_allowed(&root.0.join("README.md"))
        .is_err());
    let subtree_capability = capability(&root.0, &["docs"]);
    assert!(subtree_capability.assert_allowed(&guide).is_ok());

    let other = TempRoot::new();
    let outside = other.write("docs/guide.md", "outside\n");
    assert!(capability.assert_allowed(&outside).is_err());
}

#[cfg(unix)]
#[test]
fn posix_backslash_filename_does_not_alias_a_slash_allowed_subtree() {
    let root = TempRoot::new();
    let slash_path = root.write("docs/x/guide.md", "slash path\n");
    let backslash_component = root.write("docs\\x/guide.md", "backslash path\n");
    let capability = capability(&root.0, &["docs/x"]);

    assert!(capability.assert_allowed(&slash_path).is_ok());
    assert!(capability.assert_allowed(&backslash_component).is_err());
    assert!(capability
        .write_text(&backslash_component, "must remain\n")
        .is_err());
    assert_eq!(
        fs::read_to_string(&backslash_component).unwrap(),
        "backslash path\n"
    );
}

#[test]
fn source_capability_writes_only_the_approved_file() {
    let root = TempRoot::new();
    let guide = root.write("docs/guide.md", "before\n");
    let untouched = root.write("docs/untouched.md", "untouched\n");
    let capability = capability(&root.0, &["docs/guide.md"]);

    capability
        .write_text(&guide, "after\n")
        .expect("approved source file is rewritten");

    assert_eq!(fs::read_to_string(&guide).unwrap(), "after\n");
    assert_eq!(fs::read_to_string(&untouched).unwrap(), "untouched\n");
}

#[test]
fn source_capability_rejects_malformed_fields_and_escaping_paths() {
    let root = TempRoot::new();
    for json in [
        r#"{"allowed_paths":["docs/guide.md"],"authority":"issue-1630"}"#,
        r#"{"allowed_paths":["docs/guide.md"],"purpose":"link-repair","authority":"issue-1630","extra":true}"#,
        r#"{"allowed_paths":[],"purpose":"link-repair","authority":"issue-1630"}"#,
        r#"{"allowed_paths":["../outside.md"],"purpose":"link-repair","authority":"issue-1630"}"#,
    ] {
        assert!(
            SourceMutationCapability::from_json(&root.0, Some(json)).is_err(),
            "invalid capability accepted: {json}"
        );
    }
}

#[cfg(unix)]
#[test]
fn source_capability_rechecks_symlink_components_before_write() {
    use std::os::unix::fs::symlink;

    let root = TempRoot::new();
    let guide = root.write("docs/guide.md", "before\n");
    let outside = root.write("outside.md", "outside remains\n");
    let capability = capability(&root.0, &["docs/guide.md"]);

    fs::remove_file(&guide).expect("regular target is removed");
    symlink(&outside, &guide).expect("replacement symlink is created");
    assert!(capability
        .write_text(&guide, "must not follow link\n")
        .is_err());
    assert_eq!(fs::read_to_string(&outside).unwrap(), "outside remains\n");
}
