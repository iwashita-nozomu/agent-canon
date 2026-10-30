#[path = "../src/code_template_rendering.rs"]
mod code_template_rendering;
#[path = "../src/entrypoint_composer.rs"]
mod entrypoint_composer;
#[path = "../src/runtime_boundary.rs"]
mod runtime_boundary;
#[path = "../src/template_bundle.rs"]
mod template_bundle;

use flate2::read::GzDecoder;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use tar::Archive as TarArchive;
use zip::{System as ZipSystem, ZipArchive};

static NEXT_FIXTURE: AtomicU64 = AtomicU64::new(0);

struct TemporaryDirectory(PathBuf);

impl TemporaryDirectory {
    fn new(label: &str) -> Self {
        let id = NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-template-native-{}-{label}-{id}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("create temporary test directory");
        Self(path)
    }

    fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for TemporaryDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn write(root: &Path, relative: &str, content: &[u8]) {
    let path = root.join(relative);
    fs::create_dir_all(path.parent().expect("fixture file has a parent"))
        .expect("create fixture parents");
    fs::write(path, content).expect("write fixture file");
}

fn git(root: &Path, args: &[&str]) -> String {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .expect("run git fixture command");
    assert!(
        output.status.success(),
        "git {:?} failed: {}",
        args,
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8(output.stdout).expect("git fixture output is UTF-8")
}

fn source_fixture(parent: &Path) -> PathBuf {
    let source = parent.join("source");
    fs::create_dir_all(&source).expect("create source fixture");
    write(
        &source,
        "documents/contracts/template-bundle-manifest.toml",
        br#"version = 1

[profiles.agent-artifacts]
roots = ["templates/agents"]

[profiles.codex-user]
roots = ["ROOT_AGENTS.md", ".codex/hooks.json", ".codex/personal/skills", "agents/skills", "bootstrap.sh", "bootstrap/host/lifecycle/entrypoint.sh", "tools/runtime/container/bootstrap_runtime.py", ".codex/hooks/hook_dispatcher.py", "LICENSE", "references"]

[profiles.native-cli]
roots = ["LICENSE"]

[profiles.native-cli.layout]
"LICENSE" = "LICENSE"

[profiles.experiment-scaffold]
roots = ["templates/experiments"]
"#,
    );
    write(&source, "ROOT_AGENTS.md", b"# Common guidance\n");
    write(&source, "LICENSE", b"Fixture license\n");
    write(
        &source,
        "Cargo.toml",
        b"[package]\nname = \"agent-canon\"\nversion = \"0.1.0\"\n",
    );
    write(
        &source,
        "tools/runtime/dispatch/agent-canon/Cargo.toml",
        b"[package]\nname = \"agent-canon\"\nversion = \"0.1.0\"\n",
    );
    write(&source, "templates/agents/example.txt", b"Agent template\n");
    write(
        &source,
        "templates/experiments/example/README.md",
        b"# Instance\n",
    );
    write(&source, "bootstrap.sh", b"#!/bin/sh\nexit 0\n");
    write(
        &source,
        "bootstrap/host/lifecycle/entrypoint.sh",
        b"#!/bin/sh\nexit 0\n",
    );
    write(
        &source,
        "tools/runtime/container/bootstrap_runtime.py",
        b"# runtime\n",
    );
    write(
        &source,
        ".codex/hooks/hook_dispatcher.py",
        b"# dispatcher\n",
    );
    write(
        &source,
        ".codex/hooks.json",
        br#"{"hooks":{"UserPromptSubmit":[{"hooks":[{"type":"command","command":"old"}]}],"PreToolUse":[{"hooks":[{"type":"command","command":"old"}]}],"PostToolUse":[{"hooks":[{"type":"command","command":"old"}]}]}}"#,
    );
    write(
        &source,
        ".codex/personal/skills/agent-canon-bootstrap/SKILL.md",
        b"---\nname: agent-canon-bootstrap\ndescription: Bootstrap.\n---\n",
    );
    write(
        &source,
        "agents/skills/agent-canon-bootstrap.md",
        b"# Bootstrap\n<!--\n@dependency-start\ncontract skill\n@dependency-end\n-->\n[Guide](../../references/guide.md#read)\n",
    );
    write(&source, "references/guide.md", b"# Guide\n");

    let initialized = Command::new("git")
        .args(["init", "--quiet"])
        .arg(&source)
        .status()
        .expect("initialize git fixture");
    assert!(initialized.success(), "initialize git fixture");
    git(&source, &["config", "user.name", "Template fixture"]);
    git(
        &source,
        &["config", "user.email", "template@example.invalid"],
    );
    git(&source, &["add", "--all"]);
    git(&source, &["commit", "-qm", "template fixture"]);
    source
}

fn source_commit(root: &Path) -> String {
    git(root, &["rev-parse", "HEAD"]).trim().to_owned()
}

fn sha256(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[test]
fn code_template_reader_uses_explicit_root_and_rejects_escape() {
    let temporary = TemporaryDirectory::new("code");
    let source = source_fixture(temporary.path());
    write(&source, "templates/code/python/example.py", b"value = 3\n");
    assert_eq!(
        code_template_rendering::render_code_template(&source, "python/example.py")
            .expect("read code template"),
        "value = 3\n"
    );
    let error = code_template_rendering::render_code_template(&source, "../../Cargo.toml")
        .expect_err("reject an owner-root escape");
    assert!(error.to_string().contains("escapes owner"));
    let error = code_template_rendering::render_code_template(&source, "missing.py")
        .expect_err("report a missing template");
    assert!(error.to_string().contains("not found"));
    assert_eq!(
        fs::read(source.join("Cargo.toml")).unwrap(),
        b"[package]\nname = \"agent-canon\"\nversion = \"0.1.0\"\n"
    );
    #[cfg(unix)]
    {
        let outside = temporary.path().join("outside.py");
        fs::write(&outside, b"outside\n").unwrap();
        std::os::unix::fs::symlink(&outside, source.join("templates/code/escape.py")).unwrap();
        let error = code_template_rendering::render_code_template(&source, "escape.py")
            .expect_err("reject an escaping template symlink");
        assert!(error.to_string().contains("escapes owner"));
    }
}

#[test]
fn composer_preserves_arbitrary_source_bytes_and_exact_marker_order() {
    let temporary = TemporaryDirectory::new("compose");
    let source = source_fixture(temporary.path());
    let base = temporary.path().join("ROOT_AGENTS.md");
    let specific = temporary.path().join("consumer.md");
    let output = temporary.path().join("AGENTS.md");
    let base_bytes = b"# Portable\r\n".to_vec();
    let specific_bytes = b"consumer-owned\xff\n".to_vec();
    fs::write(&base, &base_bytes).unwrap();
    fs::write(&specific, &specific_bytes).unwrap();

    let (status, composition) = entrypoint_composer::compose(&base, &specific, &output, &source)
        .expect("compose consumer root instructions");
    assert_eq!(status, "created");
    assert_eq!(composition.source_commit, source_commit(&source));
    assert_eq!(composition.base, base_bytes);
    assert_eq!(composition.specific, specific_bytes);
    let rendered = fs::read(&output).unwrap();
    let marker = b"<!-- agent-canon:consumer-root-agents:v1 -->\n";
    let base_start = b"<!-- agent-canon:consumer-root-base:start -->\n";
    let base_end = b"\n<!-- agent-canon:consumer-root-base:end -->\n";
    let specific_start = b"<!-- agent-canon:consumer-root-specific:start -->\n";
    let specific_end = b"\n<!-- agent-canon:consumer-root-specific:end -->\n";
    let start = |needle: &[u8]| {
        rendered
            .windows(needle.len())
            .position(|part| part == needle)
            .unwrap()
    };
    assert!(start(marker) < start(base_start));
    assert!(start(base_start) < start(base_end));
    assert!(start(base_end) < start(specific_start));
    assert!(start(specific_start) < start(specific_end));
    let expected = format!(
        "{}<!-- agent-canon:source-commit={} -->\n<!-- agent-canon:base-sha256={} -->\n<!-- agent-canon:base-bytes={} -->\n<!-- agent-canon:specific-sha256={} -->\n<!-- agent-canon:specific-bytes={} -->\n",
        String::from_utf8_lossy(marker),
        source_commit(&source),
        sha256(&base_bytes),
        base_bytes.len(),
        sha256(&specific_bytes),
        specific_bytes.len(),
    );
    assert!(rendered.starts_with(expected.as_bytes()));
    let parsed = entrypoint_composer::parse_marked(&rendered).unwrap();
    assert_eq!(parsed.base, base_bytes);
    assert_eq!(parsed.specific, specific_bytes);

    fs::write(&output, b"consumer data\n").unwrap();
    let failure = entrypoint_composer::compose(&base, &specific, &output, &source)
        .expect_err("preserve an unmarked consumer file");
    assert_eq!(failure.code, "collision");
    assert_eq!(fs::read(&output).unwrap(), b"consumer data\n");
    fs::write(&output, b"<!-- agent-canon:consumer-root-agents:v1 -->\n").unwrap();
    let failure = entrypoint_composer::compose(&base, &specific, &output, &source)
        .expect_err("reject a partial managed output");
    assert_eq!(failure.code, "partial");
    #[cfg(unix)]
    {
        fs::remove_file(&output).unwrap();
        let linked_base = temporary.path().join("base-link.md");
        std::os::unix::fs::symlink(&base, &linked_base).unwrap();
        let failure = entrypoint_composer::compose(&linked_base, &specific, &output, &source)
            .expect_err("reject a symlink input");
        assert_eq!(failure.code, "symlink");
    }
}

#[test]
fn profile_and_codex_exports_are_commit_bound_source_free_and_verifiable() {
    let temporary = TemporaryDirectory::new("export");
    let source = source_fixture(temporary.path());
    let runtime = temporary.path().join("runtime");
    fs::create_dir_all(&runtime).unwrap();
    let ordinary = runtime.join("agent-artifacts");
    let identity = template_bundle::bundle_identity(&source, "HEAD", "agent-artifacts")
        .expect("compute source-bound profile identity");
    let exported =
        template_bundle::export_bundle_at(&source, "HEAD", "agent-artifacts", &ordinary, &runtime)
            .expect("export profile to external runtime");
    assert_eq!(exported["source_commit"], source_commit(&source));
    assert_eq!(exported["bundle_digest"], identity["bundle_digest"]);
    assert_eq!(
        fs::read(ordinary.join("templates/agents/example.txt")).unwrap(),
        b"Agent template\n"
    );
    let provenance: serde_json::Value = serde_json::from_slice(
        &fs::read(ordinary.join("template-bundle-provenance.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(provenance["manifest_digest"], identity["manifest_digest"]);

    let first = runtime.join("codex-user");
    let second = runtime.join("codex-user-repeat");
    let one = template_bundle::export_bundle_at(&source, "HEAD", "codex-user", &first, &runtime)
        .expect("export Codex user projection");
    let two = template_bundle::export_bundle_at(&source, "HEAD", "codex-user", &second, &runtime)
        .expect("repeat Codex user projection");
    assert_eq!(one["bundle_digest"], two["bundle_digest"]);
    assert!(!first.join(".git").exists());
    let skill = fs::read_to_string(first.join("skills/agent-canon-bootstrap/SKILL.md")).unwrap();
    assert!(!skill.contains("@dependency-start"));
    assert!(skill.contains("[Guide](../../references/guide.md#read)"));
    let hook: serde_json::Value =
        serde_json::from_slice(&fs::read(first.join("hooks/hooks.json")).unwrap()).unwrap();
    for event in ["UserPromptSubmit", "PreToolUse", "PostToolUse"] {
        assert!(hook["hooks"][event][0]["hooks"][0]["command"]
            .as_str()
            .unwrap()
            .contains(&format!("codex hook {event}")));
    }
    let verified = template_bundle::verify_codex_user_bundle(&first).unwrap();
    assert_eq!(verified["bundle_digest"], one["bundle_digest"]);
    fs::write(first.join("hooks/hooks.json"), b"{}\n").unwrap();
    assert!(template_bundle::verify_codex_user_bundle(&first)
        .unwrap_err()
        .to_string()
        .contains("digest differs"));
}

#[test]
fn native_version_counts_first_parent_updates_until_the_next_baseline() {
    let temporary = TemporaryDirectory::new("version");
    let source = source_fixture(temporary.path());
    assert_eq!(
        template_bundle::native_release_version(&source, "HEAD").unwrap(),
        "0.1.0"
    );
    write(
        &source,
        "CHANGELOG.md",
        b"A source update without a version bump.\n",
    );
    git(&source, &["add", "CHANGELOG.md"]);
    git(&source, &["commit", "-qm", "source update"]);
    assert_eq!(
        template_bundle::native_release_version(&source, "HEAD").unwrap(),
        "0.1.1"
    );
    write(
        &source,
        "tools/runtime/dispatch/agent-canon/Cargo.toml",
        b"[package]\nname = \"agent-canon\"\nversion = \"0.2.0\"\n",
    );
    git(
        &source,
        &["add", "tools/runtime/dispatch/agent-canon/Cargo.toml"],
    );
    git(&source, &["commit", "-qm", "release baseline"]);
    assert_eq!(
        template_bundle::native_release_version(&source, "HEAD").unwrap(),
        "0.2.0"
    );
}

#[test]
fn native_package_roundtrips_with_reproducible_metadata_and_source_receipts() {
    let temporary = TemporaryDirectory::new("native");
    let source = source_fixture(temporary.path());
    let runtime = temporary.path().join("runtime");
    fs::create_dir_all(&runtime).unwrap();
    let binary = temporary.path().join("agent-canon");
    fs::write(&binary, b"fixture native executable\n").unwrap();
    let first_root = runtime.join("first");
    let second_root = runtime.join("second");
    let tree_before = git(&source, &["rev-parse", "HEAD^{tree}"]);
    let worktree_before = git(&source, &["status", "--porcelain"]);
    let first = template_bundle::package_native_cli_at(
        &source,
        "HEAD",
        &binary,
        "x86_64-unknown-linux-gnu",
        &first_root,
        "rustc 1.89.0",
        &runtime,
    )
    .expect("package native executable");
    template_bundle::package_native_cli_at(
        &source,
        "HEAD",
        &binary,
        "x86_64-unknown-linux-gnu",
        &second_root,
        "rustc 1.89.0",
        &runtime,
    )
    .expect("repeat package native executable");
    assert_eq!(git(&source, &["rev-parse", "HEAD^{tree}"]), tree_before);
    assert_eq!(git(&source, &["status", "--porcelain"]), worktree_before);
    assert_eq!(first["version"], "0.1.0");
    let tar_name = "agent-canon-0.1.0-x86_64-unknown-linux-gnu.tar.gz";
    let zip_name = "agent-canon-0.1.0-x86_64-unknown-linux-gnu.zip";
    let first_tar = fs::read(first_root.join(tar_name)).unwrap();
    assert_eq!(first_tar, fs::read(second_root.join(tar_name)).unwrap());
    assert_eq!(
        fs::read(first_root.join(zip_name)).unwrap(),
        fs::read(second_root.join(zip_name)).unwrap()
    );
    let tar_sha = sha256(&first_tar);
    assert_eq!(
        fs::read_to_string(first_root.join(format!("{tar_name}.sha256"))).unwrap(),
        format!("{tar_sha}  {tar_name}\n")
    );
    assert_eq!(
        template_bundle::verify_native_packages(
            &source,
            "HEAD",
            &first_root,
            &["x86_64-unknown-linux-gnu".to_owned()],
        )
        .unwrap()["source_commit"],
        source_commit(&source)
    );

    let gzip = GzDecoder::new(first_tar.as_slice());
    let mut tar = TarArchive::new(gzip);
    let mut tar_entries = tar.entries().unwrap();
    let mut tar_names = Vec::new();
    let mut tar_payload = BTreeMap::new();
    while let Some(entry) = tar_entries.next() {
        let mut entry = entry.unwrap();
        let name = entry.path().unwrap().to_string_lossy().into_owned();
        assert_eq!(entry.header().uid().unwrap(), 0);
        assert_eq!(entry.header().gid().unwrap(), 0);
        assert_eq!(entry.header().mtime().unwrap(), 0);
        assert_eq!(entry.header().username().unwrap().unwrap_or(""), "");
        assert_eq!(entry.header().groupname().unwrap().unwrap_or(""), "");
        if name.ends_with("/bin/agent-canon") {
            assert_eq!(entry.header().mode().unwrap(), 0o755);
        } else {
            assert_eq!(entry.header().mode().unwrap(), 0o644);
        }
        let mut content = Vec::new();
        entry.read_to_end(&mut content).unwrap();
        tar_names.push(name.clone());
        tar_payload.insert(name, content);
    }
    assert!(tar_names.windows(2).all(|pair| pair[0] < pair[1]));
    assert_eq!(&first_tar[4..8], &[0, 0, 0, 0]);
    assert_eq!(first_tar[3] & 0x08, 0);

    let zip_file = fs::File::open(first_root.join(zip_name)).unwrap();
    let mut zip = ZipArchive::new(zip_file).unwrap();
    let mut zip_names = Vec::new();
    let mut zip_payload = BTreeMap::new();
    for index in 0..zip.len() {
        let mut member = zip.by_index(index).unwrap();
        assert_eq!(member.system(), ZipSystem::Unix);
        assert_eq!(member.last_modified(), Some(zip::DateTime::default()));
        assert_eq!((member.external_attributes() >> 16) & 0o170000, 0o100000);
        let mut content = Vec::new();
        member.read_to_end(&mut content).unwrap();
        let name = member.name().expect("valid ZIP member name").into_owned();
        if name.ends_with("/bin/agent-canon") {
            assert_eq!((member.external_attributes() >> 16) & 0o777, 0o755);
            assert_eq!(content, b"fixture native executable\n");
        }
        zip_names.push(name.clone());
        zip_payload.insert(name, content);
    }
    assert!(zip_names.windows(2).all(|pair| pair[0] < pair[1]));
    assert_eq!(tar_payload, zip_payload);
    assert!(source.join("templates/agents/example.txt").is_file());
    assert!(!source.join("runtime").exists());

    let windows_root = runtime.join("windows");
    template_bundle::package_native_cli_at(
        &source,
        "HEAD",
        &binary,
        "x86_64-pc-windows-msvc",
        &windows_root,
        "rustc 1.89.0",
        &runtime,
    )
    .expect("package Windows native executable");
    let windows_name = "agent-canon-0.1.0-x86_64-pc-windows-msvc.zip";
    let windows_zip =
        ZipArchive::new(fs::File::open(windows_root.join(windows_name)).unwrap()).unwrap();
    assert!(windows_zip.file_names().any(|name| {
        name.unwrap() == "agent-canon-0.1.0-x86_64-pc-windows-msvc/bin/agent-canon.exe"
    }));
    template_bundle::verify_native_packages(
        &source,
        "HEAD",
        &windows_root,
        &["x86_64-pc-windows-msvc".to_owned()],
    )
    .expect("verify Windows package naming and payload");
}
