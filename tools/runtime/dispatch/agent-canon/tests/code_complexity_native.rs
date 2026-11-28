// @dependency-start
// contract test
// responsibility Checks the public compression measurement against known Git file records.
// upstream implementation ../src/code_complexity.rs code snapshot measurement
// @dependency-end

use flate2::{read::GzEncoder, Compression};
use serde_json::Value;
use std::fs;
use std::io::Read;
use std::path::Path;
use std::process::{Command, Output};

fn git(root: &Path, args: &[&str]) {
    let output = Command::new("git")
        .args([
            "-c",
            "user.name=Compression test",
            "-c",
            "user.email=compression@example.com",
            "-c",
            "core.autocrlf=false",
            "-c",
            "commit.gpgsign=false",
        ])
        .args(args)
        .current_dir(root)
        .output()
        .unwrap();
    assert!(output.status.success(), "{output:?}");
}

fn tool(root: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args(["code-complexity", "--root"])
        .arg(root)
        .args(args)
        .output()
        .unwrap()
}

fn reference_size(files: &[(&[u8], bool, &[u8])]) -> usize {
    let mut stream = Vec::new();
    for (path, executable, bytes) in files {
        stream.extend_from_slice(&(path.len() as u64).to_le_bytes());
        stream.extend_from_slice(path);
        stream.push(u8::from(*executable));
        stream.extend_from_slice(&(bytes.len() as u64).to_le_bytes());
        stream.extend_from_slice(bytes);
    }
    let mut compressed = Vec::new();
    GzEncoder::new(stream.as_slice(), Compression::new(6))
        .read_to_end(&mut compressed)
        .unwrap();
    compressed.len()
}

#[test]
fn compares_the_same_scope_using_paths_modes_and_committed_bytes() {
    let repo = tempfile::tempdir().unwrap();
    let root = repo.path();
    git(root, &["init", "-q"]);
    fs::create_dir(root.join("src")).unwrap();
    let original = b"fn square(x: u32) -> u32 { x * x }\n";
    let repeated = original.repeat(4096);
    fs::write(root.join("src/a.rs"), original).unwrap();
    fs::write(root.join("src/z.rs"), &repeated).unwrap();
    fs::write(root.join(".gitattributes"), "src/z.rs export-ignore\n").unwrap();
    fs::write(root.join("ignored.bin"), [0xff, 0x00]).unwrap();
    git(root, &["add", "src", ".gitattributes", "ignored.bin"]);
    git(root, &["commit", "-qm", "base"]);

    git(root, &["rm", "src/z.rs"]);
    git(root, &["mv", "src/a.rs", "src/file with spaces.rs"]);
    git(
        root,
        &["update-index", "--chmod=+x", "src/file with spaces.rs"],
    );
    git(root, &["commit", "-qm", "target"]);
    fs::write(root.join("src/file with spaces.rs"), b"worktree edit").unwrap();
    fs::write(root.join("src/untracked.rs"), b"untracked").unwrap();

    let output = tool(&root.join("src"), &["--base", "HEAD^", "--", "src"]);
    assert!(output.status.success(), "{output:?}");
    let report: Value = serde_json::from_slice(&output.stdout).unwrap();
    let base_gzip = reference_size(&[
        (b"src/a.rs", false, original),
        (b"src/z.rs", false, &repeated),
    ]);
    let target_gzip = reference_size(&[(b"src/file with spaces.rs", true, original)]);
    assert_eq!(report["schema"], "agent_canon.code_complexity.v2");
    assert_eq!(report["base"]["files"], 2);
    assert_eq!(report["target"]["files"], 1);
    assert_eq!(
        report["base"]["source_bytes"],
        original.len() + repeated.len()
    );
    assert_eq!(report["target"]["source_bytes"], original.len());
    assert_eq!(report["base"]["gzip_bytes"], base_gzip);
    assert_eq!(report["target"]["gzip_bytes"], target_gzip);
    assert_eq!(report["delta"]["files"], -1);
    assert_eq!(report["delta"]["source_bytes"], -(repeated.len() as i64));
    assert_eq!(
        report["delta"]["gzip_bytes"],
        target_gzip as i64 - base_gzip as i64
    );

    let added_or_removed_path = tool(root, &["--base", "HEAD^", "--", "src/z.rs"]);
    assert!(
        added_or_removed_path.status.success(),
        "{added_or_removed_path:?}"
    );
    let report: Value = serde_json::from_slice(&added_or_removed_path.stdout).unwrap();
    assert_eq!(report["target"]["files"], 0);
    assert_eq!(report["target"]["gzip_bytes"], reference_size(&[]));

    let bad_revision = tool(root, &["--target", "missing-revision"]);
    assert_eq!(bad_revision.status.code(), Some(2));
    assert!(bad_revision.stdout.is_empty());
}

#[cfg(unix)]
#[test]
fn preserves_path_bytes_outside_utf8() {
    use std::ffi::OsStr;
    use std::os::unix::ffi::OsStrExt;

    let repo = tempfile::tempdir().unwrap();
    let root = repo.path();
    let path = b"src/\xff.rs";
    let bytes = b"fn main() {}\n";
    git(root, &["init", "-q"]);
    fs::create_dir(root.join("src")).unwrap();
    fs::write(root.join(OsStr::from_bytes(path)), bytes).unwrap();
    git(root, &["add", "src"]);
    git(root, &["commit", "-qm", "raw path"]);

    let output = tool(root, &["--", "src"]);
    assert!(output.status.success(), "{output:?}");
    let report: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(
        report["target"]["gzip_bytes"],
        reference_size(&[(path, false, bytes)])
    );
}
