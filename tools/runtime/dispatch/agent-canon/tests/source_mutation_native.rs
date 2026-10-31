// @dependency-start
// contract test
// responsibility Verifies source-root binding, exact allowed subtrees, and no-follow source writes/removals.
// upstream implementation ../src/source_mutation.rs owns the explicit source-mutation capability
// downstream implementation ../src/docs.rs uses the capability for native link rewrites
// @dependency-end

use agent_canon::source_mutation::SourceMutationCapability;
use std::fs;
#[cfg(unix)]
use std::io;
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

#[cfg(unix)]
fn invalid_byte_path_is_unsupported(error: &io::Error) -> bool {
    #[cfg(target_os = "macos")]
    {
        // macOS reports EILSEQ (92) when its filesystem rejects raw path bytes.
        error.raw_os_error() == Some(92)
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = error;
        false
    }
}

#[test]
fn source_capability_binds_root_and_exact_allowed_subtree() {
    let root = TempRoot::new();
    let guide = root.write("docs/guide.md", "before\n");
    let exact_capability = capability(&root.0, &["docs/guide.md"]);
    assert_eq!(
        exact_capability
            .assert_allowed(&guide)
            .expect("allowed file resolves"),
        guide.canonicalize().expect("file is canonical")
    );
    assert!(exact_capability
        .assert_allowed(&root.0.join("README.md"))
        .is_err());
    let subtree_capability = capability(&root.0, &["docs"]);
    assert!(subtree_capability.assert_allowed(&guide).is_ok());

    let other = TempRoot::new();
    let outside = other.write("docs/guide.md", "outside\n");
    assert!(exact_capability.assert_allowed(&outside).is_err());
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

#[cfg(unix)]
#[test]
fn posix_replacement_character_grant_does_not_alias_invalid_utf8_component() {
    use std::os::unix::ffi::OsStringExt;

    let root = TempRoot::new();
    let valid = root.write("docs/�/guide.md", "valid subtree\n");
    let invalid = root
        .0
        .join("docs")
        .join(std::ffi::OsString::from_vec(vec![0xff]))
        .join("guide.md");
    let invalid_parent = invalid.parent().expect("invalid-byte fixture has parent");
    if let Err(error) = fs::create_dir_all(invalid_parent) {
        if invalid_byte_path_is_unsupported(&error) {
            eprintln!("filesystem-bound invalid-byte write oracle unavailable: EILSEQ");
            return;
        }
        panic!("invalid-byte fixture directory is created: {error}");
    }
    if let Err(error) = fs::write(&invalid, "invalid-byte subtree remains\n") {
        if invalid_byte_path_is_unsupported(&error) {
            eprintln!("filesystem-bound invalid-byte write oracle unavailable: EILSEQ");
            return;
        }
        panic!("invalid-byte fixture is written: {error}");
    }
    let capability = capability(&root.0, &["docs/�"]);

    assert!(capability.assert_allowed(&valid).is_ok());
    assert!(capability.assert_allowed(&invalid).is_err());
    assert!(capability
        .write_text(&invalid, "must remain denied\n")
        .is_err());
    assert_eq!(
        fs::read_to_string(&invalid).unwrap(),
        "invalid-byte subtree remains\n"
    );
}

#[cfg(unix)]
#[test]
fn posix_control_character_component_is_an_exact_valid_grant() {
    let root = TempRoot::new();
    let allowed = root.write("docs/a\u{1}b/guide.md", "before\n");
    let different = root.write("docs/ab/guide.md", "different path\n");
    let capability = capability(&root.0, &["docs/a\u{1}b"]);

    assert!(capability.assert_allowed(&allowed).is_ok());
    assert!(capability.assert_allowed(&different).is_err());
    capability
        .write_text(&allowed, "after\n")
        .expect("valid control-character path is within its exact grant");
    assert!(capability
        .write_text(&different, "must remain denied\n")
        .is_err());
    assert_eq!(fs::read_to_string(&allowed).unwrap(), "after\n");
    assert_eq!(fs::read_to_string(&different).unwrap(), "different path\n");
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
fn source_capability_removes_only_the_approved_file() {
    let root = TempRoot::new();
    let approved = root.write("docs/approved.md", "remove me\n");
    let untouched = root.write("docs/untouched.md", "untouched\n");
    let capability = capability(&root.0, &["docs/approved.md"]);

    capability
        .remove_file(&approved)
        .expect("approved source file is removed");

    assert!(!approved.exists());
    assert!(capability.remove_file(&untouched).is_err());
    assert_eq!(fs::read_to_string(&untouched).unwrap(), "untouched\n");
}

#[test]
fn source_capability_copies_regular_file_content_mode_and_times() {
    let root = TempRoot::new();
    let source = root.write("documents/design/a.md", "copy source\n");
    let target = root.0.join("documents/design/foo/a.md");
    let source_atime = std::time::UNIX_EPOCH + std::time::Duration::from_secs(1_700_000_100);
    let source_mtime = std::time::UNIX_EPOCH + std::time::Duration::new(1_700_000_123, 456_789_012);
    let source_file = fs::OpenOptions::new()
        .write(true)
        .open(&source)
        .expect("source is opened for metadata setup");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&source, fs::Permissions::from_mode(0o640))
            .expect("source mode is seeded");
    }
    source_file
        .set_times(
            fs::FileTimes::new()
                .set_accessed(source_atime)
                .set_modified(source_mtime),
        )
        .expect("source times are seeded");
    let capability = capability(&root.0, &["documents/design/foo/a.md"]);

    capability
        .copy_file_with_metadata(&source, &target)
        .expect("source file copies under the exact grant");

    let source_metadata = fs::metadata(&source).expect("source metadata remains available");
    let target_metadata = fs::metadata(&target).expect("target metadata is available");
    assert_eq!(
        source_metadata.modified().unwrap(),
        target_metadata.modified().unwrap()
    );
    assert_eq!(
        source_metadata.accessed().unwrap(),
        target_metadata.accessed().unwrap()
    );
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            source_metadata.permissions().mode() & 0o7777,
            target_metadata.permissions().mode() & 0o7777
        );
    }
    assert_eq!(
        fs::read(&target).expect("copied bytes are readable"),
        b"copy source\n"
    );
    assert_eq!(
        fs::read(&source).expect("source bytes remain readable"),
        b"copy source\n"
    );
}

#[cfg(unix)]
#[test]
fn source_capability_copies_source_symlink_text_and_timestamps() {
    use std::os::unix::fs::symlink;

    let root = TempRoot::new();
    let target_payload = root.write("documents/payload.md", "link target\n");
    let source_link = root.0.join("documents/design/a.md");
    fs::create_dir_all(source_link.parent().unwrap()).expect("source parent exists");
    symlink(&target_payload, &source_link).expect("source symlink is created");
    let source_link_times =
        std::time::SystemTime::UNIX_EPOCH + std::time::Duration::new(1_700_000_123, 456_789_012);
    let source_parent = cap_std::fs::Dir::open_ambient_dir(
        source_link.parent().unwrap(),
        cap_std::ambient_authority(),
    )
    .expect("source parent is opened for fixture metadata");
    use cap_fs_ext::DirExt;
    source_parent
        .set_symlink_times(
            "a.md",
            Some(cap_fs_ext::SystemTimeSpec::from(
                cap_std::time::SystemTime::from_std(source_link_times),
            )),
            Some(cap_fs_ext::SystemTimeSpec::from(
                cap_std::time::SystemTime::from_std(source_link_times),
            )),
        )
        .expect("source symlink times are seeded");
    let target = root.0.join("documents/design/foo/a.md");
    let capability = capability(&root.0, &["documents/design/foo/a.md"]);

    capability
        .copy_file_with_metadata(&source_link, &target)
        .expect("source symlink is copied as a link");

    assert_eq!(
        fs::read_link(&target).expect("target remains a link"),
        target_payload
    );
    assert!(fs::symlink_metadata(&target)
        .expect("target link metadata exists")
        .file_type()
        .is_symlink());
    let source_mtime = fs::symlink_metadata(&source_link)
        .expect("source link metadata exists")
        .modified()
        .unwrap();
    let target_mtime = fs::symlink_metadata(&target)
        .expect("target link metadata exists")
        .modified()
        .unwrap();
    assert_eq!(source_mtime, target_mtime);
    assert_eq!(fs::read_to_string(&target).unwrap(), "link target\n");
    assert_eq!(
        fs::read_to_string(&target_payload).unwrap(),
        "link target\n"
    );
}

#[cfg(target_os = "linux")]
#[test]
fn source_capability_copies_symlink_xattrs_when_the_filesystem_allows_them() {
    use rustix::fs::{lgetxattr, lgetxattr_query, lsetxattr, XattrFlags};
    use rustix::io::Errno;
    use std::os::unix::fs::symlink;

    let root = TempRoot::new();
    root.write("documents/payload.md", "symlink target\n");
    let source_link = root.0.join("documents/design/a.md");
    fs::create_dir_all(source_link.parent().unwrap()).expect("source parent exists");
    symlink("../payload.md", &source_link).expect("source symlink is created");
    let xattr_name = "user.agentcanon.organizer.link";
    let xattr_value = b"copied-link-value";
    match lsetxattr(&source_link, xattr_name, xattr_value, XattrFlags::empty()) {
        Ok(()) => {}
        Err(error)
            if error == Errno::PERM
                || error == Errno::ACCESS
                || error == Errno::NOTSUP
                || error == Errno::OPNOTSUPP =>
        {
            eprintln!("filesystem does not permit symlink xattr setup: {error}");
            return;
        }
        Err(error) => panic!("source symlink xattr setup failed: {error}"),
    }
    let target_link = root.0.join("documents/design/foo/a.md");
    let capability = capability(&root.0, &["documents/design/foo/a.md"]);

    capability
        .copy_file_with_metadata(&source_link, &target_link)
        .expect("source symlink and its metadata are copied");

    let length = lgetxattr_query(&target_link, xattr_name).expect("copied link xattr exists");
    let mut actual = vec![0; length];
    let written =
        lgetxattr(&target_link, xattr_name, &mut actual).expect("copied link xattr is readable");
    actual.truncate(written);
    assert_eq!(actual, xattr_value);
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
fn source_capability_rechecks_symlink_components_before_write_or_remove() {
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
    assert!(capability.remove_file(&guide).is_err());
    assert!(fs::symlink_metadata(&guide)
        .expect("replacement symlink remains")
        .file_type()
        .is_symlink());
    assert_eq!(fs::read_to_string(&outside).unwrap(), "outside remains\n");
}
