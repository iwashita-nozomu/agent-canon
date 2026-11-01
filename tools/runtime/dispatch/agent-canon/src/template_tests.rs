// @dependency-start
// contract test
// responsibility Verifies native template rendering, composition, source-bound profile export, native packaging and external artifact boundaries.
// upstream implementation code_template_rendering.rs explicit-root code renderer
// upstream implementation entrypoint_composer.rs consumer root composer
// upstream implementation template_bundle.rs profile and archive owner
// downstream implementation lib.rs library-owned Template test module
// @dependency-end

use crate::{code_template_rendering, entrypoint_composer, template_bundle};

use flate2::read::GzDecoder;
use serde_json::Value;
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

[profiles.document-artifacts]
roots = ["templates/documents"]

[profiles.codex-user]
roots = ["ROOT_AGENTS.md", ".codex/hooks.json", ".codex/personal/skills", "agents/skills", "bootstrap.sh", "bootstrap/host/lifecycle/entrypoint.sh", "tools/runtime/container/bootstrap_runtime.py", "LICENSE", "tools/agent/templates", "documents/runtime/runtime-profiles-and-check-matrix.json"]

[profiles.native-cli]
roots = ["LICENSE"]

[profiles.native-cli.layout]
"LICENSE" = "LICENSE"

[profiles.experiment-scaffold]
roots = ["templates/experiments"]
"#,
    );
    write(&source, "ROOT_AGENTS.md", b"# Common guidance\n");
    write(
        &source,
        "AGENTS.md",
        b"# Source-only AgentCanon instructions\n",
    );
    write(
        &source,
        "documents/runtime/runtime-profiles-and-check-matrix.json",
        b"{\"schema\":\"fixture\"}\n",
    );
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
        "templates/documents/example.md",
        b"Document template\n",
    );
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
        ".codex/personal/skills/demo/SKILL.md",
        b"---\nname: demo\ndescription: Demonstrate a source-free workflow.\n---\n",
    );
    write(
        &source,
        "agents/skills/agent-canon-bootstrap.md",
        b"# Bootstrap\n",
    );
    write(
        &source,
        "agents/skills/demo.md",
        b"# Demo\n<!--\n@dependency-start\ncontract skill\nresponsibility Source maintenance metadata.\n@dependency-end\n-->\n[guide](../../references/guide.md#read)\n[peer](peer.md)\n![icon](../../assets/icon.svg)\n[external](https://example.com/guide)\n[section](#demo)\n`[literal](not-a-resource.md)`\n```markdown\n[example](not-a-resource-either.md)\n```\n[named][nested]\n[nested]: ../../references/nested.md#nested\n",
    );
    write(
        &source,
        "agents/skills/peer.md",
        b"# Peer\n[shared](../../references/guide.md)\n",
    );
    write(
        &source,
        "references/guide.md",
        b"# Guide\n[child](nested.md)\n[template](../templates/experiments/example)\n",
    );
    write(&source, "references/nested.md", b"# Nested\n");
    write(
        &source,
        "references/unrelated.md",
        b"# Unreferenced document\n",
    );
    write(
        &source,
        "templates/experiments/example/README.md",
        b"# Instance\n[future](../../consumer-doc.md)\n",
    );
    write(
        &source,
        "templates/experiments/example/input.json",
        b"{\"value\":1}\n",
    );
    write(
        &source,
        "assets/icon.svg",
        b"<svg xmlns=\"http://www.w3.org/2000/svg\"/>\n",
    );
    write(
        &source,
        "tests/unrelated.py",
        b"# Not a profile resource.\n",
    );
    write(&source, "tools/agent/templates/__init__.py", b"");
    write(
        &source,
        "tools/agent/templates/entrypoint_composer.py",
        b"Composition = None\n",
    );

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
    git(&source, &["update-index", "--chmod=+x", "bootstrap.sh"]);
    git(
        &source,
        &[
            "update-index",
            "--chmod=+x",
            "bootstrap/host/lifecycle/entrypoint.sh",
        ],
    );
    git(&source, &["commit", "-qm", "template fixture"]);
    source
}

fn source_commit(root: &Path) -> String {
    git(root, &["rev-parse", "HEAD"]).trim().to_owned()
}

fn repository_root() -> PathBuf {
    fs::canonicalize(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../../"))
        .expect("resolve AgentCanon source root")
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
    let source_agents = fs::read(source.join("AGENTS.md")).unwrap();
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
    assert!(!output.parent().unwrap().join("AGENT.md").exists());
    assert_eq!(fs::read(source.join("AGENTS.md")).unwrap(), source_agents);
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

    fs::write(&base, b"# Portable\nnew common input\n").unwrap();
    fs::write(&specific, b"consumer-owned\nnew consumer input\n").unwrap();
    let (status, refreshed) = entrypoint_composer::compose(&base, &specific, &output, &source)
        .expect("refresh a valid managed output from current sources");
    assert_eq!(status, "updated");
    let parsed = entrypoint_composer::parse_marked(&fs::read(&output).unwrap()).unwrap();
    assert_eq!(parsed.base, refreshed.base);
    assert_eq!(parsed.specific, refreshed.specific);

    let portable_source = source.clone();
    let portable_base = portable_source.join("ROOT_AGENTS.md");
    let portable_bytes = fs::read(repository_root().join("ROOT_AGENTS.md")).unwrap();
    fs::write(&portable_base, &portable_bytes).unwrap();
    git(&portable_source, &["add", "ROOT_AGENTS.md"]);
    git(&portable_source, &["commit", "-qm", "actual portable base"]);
    let standalone_specific = temporary.path().join("portable-specific.md");
    let standalone_output = temporary.path().join("standalone-AGENTS.md");
    fs::write(&standalone_specific, b"## Standalone consumer\n").unwrap();
    entrypoint_composer::compose(
        &portable_base,
        &standalone_specific,
        &standalone_output,
        &portable_source,
    )
    .expect("compose the actual portable base");
    fs::remove_file(&standalone_specific).unwrap();
    let parsed = entrypoint_composer::parse_marked(&fs::read(&standalone_output).unwrap()).unwrap();
    assert_eq!(parsed.base, portable_bytes);
    assert_eq!(parsed.specific, b"## Standalone consumer\n");
    let portable_text = String::from_utf8(parsed.base).unwrap();
    let comments = regex::Regex::new(r"(?s)<!--.*?-->").unwrap();
    let links = regex::Regex::new(r"\[[^\]]+\]\(([^)]+)\)").unwrap();
    let body = comments.replace_all(&portable_text, "");
    let destinations = links
        .captures_iter(&body)
        .map(|capture| capture[1].to_owned())
        .collect::<Vec<_>>();
    assert!(!destinations.is_empty());
    assert!(destinations.iter().all(|target| {
        target.starts_with('#') || target.split('#').next() == Some("AGENTS.md")
    }));

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
        fs::remove_file(&linked_base).unwrap();
        std::os::unix::fs::symlink(&specific, &linked_base).unwrap();
        let failure = entrypoint_composer::compose(&base, &linked_base, &output, &source)
            .expect_err("reject a symlink consumer input");
        assert_eq!(failure.code, "symlink");
        fs::remove_file(&linked_base).unwrap();
        let linked_output = temporary.path().join("output-link.md");
        std::os::unix::fs::symlink(&output, &linked_output).unwrap();
        let failure = entrypoint_composer::compose(&base, &specific, &linked_output, &source)
            .expect_err("reject a symlink output");
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
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            fs::metadata(first.join("bootstrap.sh"))
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o755
        );
    }
    let skill = fs::read_to_string(first.join("skills/demo/SKILL.md")).unwrap();
    assert!(!skill.contains("@dependency-start"));
    assert!(skill.contains("[guide](../../references/guide.md#read)"));
    assert!(skill.contains("[peer](../../agents/skills/peer.md)"));
    assert!(skill.contains("![icon](../../assets/icon.svg)"));
    assert!(skill.contains("[external](https://example.com/guide)"));
    assert!(skill.contains("[section](#demo)"));
    assert!(skill.contains("`[literal](not-a-resource.md)`"));
    assert!(skill.contains("[example](not-a-resource-either.md)"));
    assert!(skill.contains("[nested]: ../../references/nested.md#nested"));
    assert!(first.join("agents/skills/demo.md").is_file());
    for relative in [
        "references/guide.md",
        "references/nested.md",
        "assets/icon.svg",
        "templates/experiments/example/README.md",
        "templates/experiments/example/input.json",
    ] {
        assert!(first.join(relative).is_file(), "missing {relative}");
    }
    let manifest: Value =
        serde_json::from_slice(&fs::read(first.join("codex-user-bundle.json")).unwrap()).unwrap();
    let paths = manifest["files"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| row["path"].as_str().unwrap())
        .collect::<Vec<_>>();
    assert_eq!(
        paths
            .iter()
            .filter(|path| **path == "references/guide.md")
            .count(),
        1
    );
    assert!(!paths.contains(&"references/unrelated.md"));
    assert!(!paths.contains(&"tests/unrelated.py"));
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
fn profile_identity_binds_profile_and_manifest_inputs() {
    let temporary = TemporaryDirectory::new("identity");
    let source = source_fixture(temporary.path());
    let agents = template_bundle::bundle_identity(&source, "HEAD", "agent-artifacts").unwrap();
    let documents =
        template_bundle::bundle_identity(&source, "HEAD", "document-artifacts").unwrap();
    assert_eq!(agents["source_commit"], documents["source_commit"]);
    assert_eq!(agents["manifest_digest"], documents["manifest_digest"]);
    assert_ne!(agents["bundle_digest"], documents["bundle_digest"]);
}

#[test]
fn codex_export_uses_the_native_composer_independent_of_source_modules() {
    let temporary = TemporaryDirectory::new("own-composer");
    let source = source_fixture(temporary.path());
    assert_eq!(
        fs::read(source.join("tools/agent/templates/entrypoint_composer.py")).unwrap(),
        b"Composition = None\n"
    );
    let runtime = temporary.path().join("runtime");
    fs::create_dir_all(&runtime).unwrap();
    let output = runtime.join("codex-user");
    template_bundle::export_bundle_at(&source, "HEAD", "codex-user", &output, &runtime)
        .expect("export without importing source composer");
    assert!(output.join("guidance/AGENTS.md").is_file());
    let composition =
        entrypoint_composer::parse_marked(&fs::read(output.join("guidance/AGENTS.md")).unwrap())
            .unwrap();
    assert_eq!(composition.base, b"# Common guidance\n");
    assert!(composition.specific.is_empty());
}

#[test]
fn codex_resources_follow_the_requested_commit_snapshot() {
    let temporary = TemporaryDirectory::new("requested-commit");
    let source = source_fixture(temporary.path());
    let runtime = temporary.path().join("runtime");
    fs::create_dir_all(&runtime).unwrap();
    let first = runtime.join("first");
    let unchanged = runtime.join("unchanged");
    let changed = runtime.join("changed");
    let identity =
        template_bundle::export_bundle_at(&source, "HEAD", "codex-user", &first, &runtime).unwrap();
    write(
        &source,
        "references/nested.md",
        b"# Nested\nUncommitted change.\n",
    );
    let still_first =
        template_bundle::export_bundle_at(&source, "HEAD", "codex-user", &unchanged, &runtime)
            .unwrap();
    assert_eq!(still_first["bundle_digest"], identity["bundle_digest"]);
    git(&source, &["add", "references/nested.md"]);
    git(&source, &["commit", "-qm", "resource change"]);
    let second =
        template_bundle::export_bundle_at(&source, "HEAD", "codex-user", &changed, &runtime)
            .unwrap();
    assert_ne!(second["bundle_digest"], identity["bundle_digest"]);
    assert_eq!(
        fs::read(changed.join("references/nested.md")).unwrap(),
        b"# Nested\nUncommitted change.\n"
    );
    assert_eq!(
        fs::read(first.join("references/nested.md")).unwrap(),
        b"# Nested\n"
    );
}

#[test]
fn codex_export_rejects_unresolvable_local_resources() {
    for target in ["../../missing.md", "../../../escape.md"] {
        let temporary = TemporaryDirectory::new("missing-resource");
        let source = source_fixture(temporary.path());
        write(
            &source,
            "agents/skills/demo.md",
            format!("# Demo\n[resource]({target})\n").as_bytes(),
        );
        git(&source, &["add", "agents/skills/demo.md"]);
        git(&source, &["commit", "-qm", "unresolvable resource"]);
        let runtime = temporary.path().join("runtime");
        fs::create_dir_all(&runtime).unwrap();
        let error = template_bundle::export_bundle_at(
            &source,
            "HEAD",
            "codex-user",
            &runtime.join("bundle"),
            &runtime,
        )
        .unwrap_err();
        assert!(error.to_string().contains("Markdown resource"));
    }
}

#[test]
fn codex_export_rejects_resources_at_each_generated_path() {
    for relative in [
        "skills/demo/SKILL.md",
        "guidance/AGENTS.md",
        "hooks/hooks.json",
        "plugin.json",
        ".agents/plugins/marketplace.json",
        "codex-user-bundle.json",
    ] {
        let temporary = TemporaryDirectory::new("generated-collision");
        let source = source_fixture(temporary.path());
        write(
            &source,
            "agents/skills/demo.md",
            format!("# Demo\n[resource](../../{relative})\n").as_bytes(),
        );
        write(&source, relative, b"Source resource.\n");
        git(&source, &["add", "--all"]);
        git(&source, &["commit", "-qm", "generated path collision"]);
        let runtime = temporary.path().join("runtime");
        fs::create_dir_all(&runtime).unwrap();
        let error = template_bundle::export_bundle_at(
            &source,
            "HEAD",
            "codex-user",
            &runtime.join("bundle"),
            &runtime,
        )
        .unwrap_err();
        assert!(
            error.to_string().contains("collides with source"),
            "{relative}: {error}"
        );
    }
}

#[test]
fn bundle_destinations_reject_nonportable_paths_without_output() {
    let temporary = TemporaryDirectory::new("portable-path");
    for relative in [
        "folder\\file.md",
        "C:note.md",
        "../note.md",
        "/note.md",
        "CON.txt",
    ] {
        let error = template_bundle::bundle_destination(temporary.path(), relative)
            .expect_err("reject a nonportable bundle destination");
        assert!(error.to_string().contains("bundle file"));
        assert_eq!(fs::read_dir(temporary.path()).unwrap().count(), 0);
    }
}

#[test]
fn exports_accept_prepared_empty_roots_and_preserve_occupied_or_symlinked_roots() {
    let temporary = TemporaryDirectory::new("output-boundary");
    let source = source_fixture(temporary.path());
    let runtime = temporary.path().join("runtime");
    fs::create_dir_all(&runtime).unwrap();
    let prepared = runtime.join("prepared");
    fs::create_dir(&prepared).unwrap();
    let expected_prepared = fs::canonicalize(&prepared).unwrap();
    let result =
        template_bundle::export_bundle_at(&source, "HEAD", "agent-artifacts", &prepared, &runtime)
            .expect("accept a dispatcher-prepared empty directory");
    assert_eq!(
        result["output"],
        expected_prepared.to_string_lossy().as_ref()
    );
    assert!(prepared.join("template-bundle-provenance.json").is_file());

    let occupied = runtime.join("occupied");
    fs::create_dir(&occupied).unwrap();
    fs::write(occupied.join("user.txt"), b"keep").unwrap();
    let target = runtime.join("target");
    fs::create_dir(&target).unwrap();
    #[cfg(unix)]
    {
        let link = runtime.join("link");
        std::os::unix::fs::symlink(&target, &link).unwrap();
        for output in [&occupied, &link] {
            let error = template_bundle::export_bundle_at(
                &source,
                "HEAD",
                "agent-artifacts",
                output,
                &runtime,
            )
            .unwrap_err();
            assert!(error.to_string().contains("fresh"));
        }
        assert!(fs::read_dir(&target).unwrap().next().is_none());
    }
    assert_eq!(fs::read(occupied.join("user.txt")).unwrap(), b"keep");
    let inside_source = source.join("workspace/template-output");
    let error = template_bundle::export_bundle_at(
        &source,
        "HEAD",
        "agent-artifacts",
        &inside_source,
        &runtime,
    )
    .unwrap_err();
    assert!(error.to_string().contains("outside"));
    assert!(!inside_source.exists());
}

#[test]
fn output_file_creation_preserves_a_concurrent_existing_file() {
    let temporary = TemporaryDirectory::new("write-once");
    let target = temporary.path().join("bundle/file.txt");
    fs::create_dir_all(target.parent().unwrap()).unwrap();
    fs::write(&target, b"concurrent user data").unwrap();
    let error = template_bundle::write_output_file(&target, b"native output", 0o644).unwrap_err();
    assert!(error.to_string().contains("write output file"));
    assert_eq!(fs::read(target).unwrap(), b"concurrent user data");
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
    let tar_entries = tar.entries().unwrap();
    let mut tar_names = Vec::new();
    let mut tar_payload = BTreeMap::new();
    for entry in tar_entries {
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
