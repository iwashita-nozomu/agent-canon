// @dependency-start
// contract test
// responsibility Verifies native release integrity, mainline tags, GitHub draft recovery, artifact selection, and rebuild checks without network publication.
// upstream implementation ../src/native_release.rs release state owner
// upstream implementation ../src/template_bundle.rs package creation and verification APIs
// downstream implementation ../../../../../.github/workflows/agent-canon-native-release.yml release workflow caller
// @dependency-end

use agent_canon::native_release::{
    publish_native_release, require_mainline_source, select_native_artifacts, CommandResult,
    NativeReleaseError, PublishRequest,
};
use flate2::read::GzDecoder;
use flate2::write::GzEncoder;
use flate2::{Compression, GzBuilder};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};
use tar::{Archive as TarArchive, Builder as TarBuilder, EntryType, Header as TarHeader};
use zip::write::SimpleFileOptions;
use zip::{CompressionMethod, DateTime, System as ZipSystem, ZipArchive, ZipWriter};

const NATIVE: &str = env!("CARGO_BIN_EXE_agent-canon");
const TARGET: &str = "x86_64-unknown-linux-gnu";

static NEXT_FIXTURE: AtomicU64 = AtomicU64::new(0);

struct TemporaryDirectory(PathBuf);

impl TemporaryDirectory {
    fn new(label: &str) -> Self {
        let id = NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-native-release-{}-{label}-{id}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("create release test directory");
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

fn write(root: &Path, relative: &str, bytes: &[u8]) {
    let path = root.join(relative);
    fs::create_dir_all(path.parent().expect("fixture file has a parent"))
        .expect("create fixture parents");
    fs::write(path, bytes).expect("write fixture file");
}

fn git(root: &Path, args: &[&str]) -> String {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .expect("run fixture git command");
    assert!(
        output.status.success(),
        "git {:?} failed: {}",
        args,
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8(output.stdout)
        .expect("fixture git output is UTF-8")
        .trim()
        .to_owned()
}

fn source_fixture(root: &Path) -> PathBuf {
    let source = root.join("source");
    fs::create_dir_all(&source).expect("create release source fixture");
    write(
        &source,
        "documents/contracts/template-bundle-manifest.toml",
        b"version = 1\n\n[profiles.native-cli]\nroots = [\"LICENSE\"]\n\n[profiles.native-cli.layout]\n\"LICENSE\" = \"LICENSE\"\n",
    );
    write(
        &source,
        "tools/runtime/dispatch/agent-canon/Cargo.toml",
        b"[package]\nname = \"agent-canon\"\nversion = \"0.1.0\"\n",
    );
    write(&source, "LICENSE", b"Fixture license\n");
    let initialized = Command::new("git")
        .args(["init", "--quiet"])
        .arg(&source)
        .status()
        .expect("initialize Git release fixture");
    assert!(initialized.success(), "initialize Git release fixture");
    git(&source, &["config", "user.name", "Release fixture"]);
    git(
        &source,
        &["config", "user.email", "release@example.invalid"],
    );
    git(&source, &["add", "--all"]);
    git(&source, &["commit", "-qm", "release fixture"]);
    git(&source, &["update-ref", "refs/remotes/origin/main", "HEAD"]);
    source
}

struct NativeReleaseFixture {
    _temporary: TemporaryDirectory,
    source: PathBuf,
    runtime: PathBuf,
    packages: PathBuf,
    identity: Value,
}

fn fixture(label: &str) -> NativeReleaseFixture {
    let temporary = TemporaryDirectory::new(label);
    let source = source_fixture(temporary.path());
    let runtime = temporary.path().join("runtime");
    fs::create_dir_all(&runtime).expect("create runtime fixture");
    let binary = temporary.path().join("agent-canon-fixture");
    fs::write(&binary, b"fixture native binary\n").expect("write native fixture");
    let packages = runtime.join("packages");
    let output = Command::new(NATIVE)
        .args([
            "template-bundle",
            "native-package",
            "--source-root",
            source.to_str().expect("source path UTF-8"),
            "--source-ref",
            "HEAD",
            "--binary",
            binary.to_str().expect("binary path UTF-8"),
            "--target",
            TARGET,
            "--output",
            packages.to_str().expect("package path UTF-8"),
            "--toolchain",
            "rustc fixture",
        ])
        .env("AGENT_CANON_RUNTIME_ROOT", &runtime)
        .output()
        .expect("run current native package command");
    assert_cli_success(&output, "package fixture artifacts");
    let identity = serde_json::from_slice(&output.stdout).expect("package identity JSON");
    NativeReleaseFixture {
        _temporary: temporary,
        source,
        runtime,
        packages,
        identity,
    }
}

fn assert_cli_success(output: &Output, action: &str) {
    assert!(
        output.status.success(),
        "{action}: stdout={} stderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}

fn verify(fixture: &NativeReleaseFixture, targets: &[&str]) -> Output {
    let mut args = vec![
        "template-bundle".to_owned(),
        "native-verify".to_owned(),
        "--source-root".to_owned(),
        fixture.source.to_string_lossy().into_owned(),
        "--source-ref".to_owned(),
        "HEAD".to_owned(),
        "--root".to_owned(),
        fixture.packages.to_string_lossy().into_owned(),
    ];
    for target in targets {
        args.push("--target".to_owned());
        args.push((*target).to_owned());
    }
    Command::new(NATIVE)
        .args(args)
        .output()
        .expect("verify packages")
}

fn request(fixture: &NativeReleaseFixture, tag: &str, check_only: bool) -> PublishRequest {
    PublishRequest {
        source_root: fixture.source.clone(),
        source_ref: "HEAD".to_owned(),
        artifacts: fixture.packages.clone(),
        targets: vec![TARGET.to_owned()],
        repo: "owner/repo".to_owned(),
        tag: tag.to_owned(),
        check_only,
    }
}

fn sha256(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn archive_payload(path: &Path, prefix: &str) -> BTreeMap<String, Vec<u8>> {
    let mut payload = BTreeMap::new();
    if path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or_default()
        .ends_with(".tar.gz")
    {
        let file = File::open(path).expect("open tar fixture");
        let mut archive = TarArchive::new(GzDecoder::new(file));
        for entry in archive.entries().expect("read tar entries") {
            let mut entry = entry.expect("read tar member");
            assert!(entry.header().entry_type().is_file());
            let name = entry
                .path()
                .expect("read tar path")
                .to_str()
                .expect("tar path UTF-8")
                .to_owned();
            let relative = name
                .strip_prefix(&format!("{prefix}/"))
                .expect("tar root name");
            let mut bytes = Vec::new();
            entry.read_to_end(&mut bytes).expect("read tar payload");
            assert!(payload.insert(relative.to_owned(), bytes).is_none());
        }
    } else {
        let file = File::open(path).expect("open ZIP fixture");
        let mut archive = ZipArchive::new(file).expect("read ZIP archive");
        for index in 0..archive.len() {
            let mut entry = archive.by_index(index).expect("read ZIP member");
            assert_eq!((entry.external_attributes() >> 16) & 0o170000, 0o100000);
            let name = entry.name().expect("read ZIP member name").into_owned();
            let relative = name
                .strip_prefix(&format!("{prefix}/"))
                .expect("ZIP root name");
            let mut bytes = Vec::new();
            entry.read_to_end(&mut bytes).expect("read ZIP payload");
            assert!(payload.insert(relative.to_owned(), bytes).is_none());
        }
    }
    payload
}

fn rebalanced_payload(payload: &mut BTreeMap<String, Vec<u8>>) {
    const PROVENANCE: &str = "share/agent-canon/provenance.json";
    const SUMS: &str = "share/agent-canon/SHA256SUMS";
    let mut provenance: Value =
        serde_json::from_slice(payload.get(PROVENANCE).unwrap()).expect("read provenance fixture");
    let files = payload
        .iter()
        .filter(|(name, _)| name.as_str() != PROVENANCE && name.as_str() != SUMS)
        .map(|(name, bytes)| json!({"path": name, "sha256": sha256(bytes)}))
        .collect::<Vec<_>>();
    provenance["files"] = Value::Array(files);
    payload.insert(
        PROVENANCE.to_owned(),
        serde_json::to_vec_pretty(&provenance)
            .map(|mut bytes| {
                bytes.push(b'\n');
                bytes
            })
            .unwrap(),
    );
    let sums = payload
        .iter()
        .filter(|(name, _)| name.as_str() != SUMS)
        .map(|(name, bytes)| format!("{}  {name}\n", sha256(bytes)))
        .collect::<String>();
    payload.insert(SUMS.to_owned(), sums.into_bytes());
}

fn tar_bytes(prefix: &str, payload: &BTreeMap<String, Vec<u8>>) -> Vec<u8> {
    let encoder = GzBuilder::new()
        .mtime(0)
        .write(Vec::new(), Compression::best());
    let mut archive = TarBuilder::new(encoder);
    for (path, bytes) in payload {
        let mut header = TarHeader::new_ustar();
        header.set_entry_type(EntryType::Regular);
        header.set_size(bytes.len() as u64);
        header.set_mode(if path.starts_with("bin/") {
            0o755
        } else {
            0o644
        });
        header.set_uid(0);
        header.set_gid(0);
        header.set_mtime(0);
        header.set_username("").unwrap();
        header.set_groupname("").unwrap();
        archive
            .append_data(&mut header, format!("{prefix}/{path}"), bytes.as_slice())
            .unwrap();
    }
    archive.into_inner().unwrap().finish().unwrap()
}

fn zip_bytes(prefix: &str, payload: &BTreeMap<String, Vec<u8>>) -> Vec<u8> {
    let mut archive = ZipWriter::new(std::io::Cursor::new(Vec::new()));
    for (path, bytes) in payload {
        let mode = if path.starts_with("bin/") {
            0o755
        } else {
            0o644
        };
        let options = SimpleFileOptions::default()
            .compression_method(CompressionMethod::Deflated)
            .compression_level(Some(9))
            .last_modified_time(DateTime::default())
            .system(ZipSystem::Unix)
            .external_attributes((0o100000 | mode) << 16);
        archive
            .start_file(format!("{prefix}/{path}"), options)
            .unwrap();
        archive.write_all(bytes).unwrap();
    }
    archive.finish().unwrap().into_inner()
}

fn rewrite_archives(
    fixture: &NativeReleaseFixture,
    suffixes: &[&str],
    mut mutate: impl FnMut(&str, &mut BTreeMap<String, Vec<u8>>),
) {
    let prefix = format!("agent-canon-0.1.0-{TARGET}");
    for suffix in suffixes {
        let filename = format!("{prefix}.{suffix}");
        let path = fixture.packages.join(&filename);
        let mut payload = archive_payload(&path, &prefix);
        mutate(suffix, &mut payload);
        rebalanced_payload(&mut payload);
        let bytes = if *suffix == "tar.gz" {
            tar_bytes(&prefix, &payload)
        } else {
            zip_bytes(&prefix, &payload)
        };
        fs::write(&path, &bytes).expect("rewrite test archive");
        fs::write(
            path.with_file_name(format!("{filename}.sha256")),
            format!("{}  {filename}\n", sha256(&bytes)),
        )
        .expect("rewrite test archive sidecar");
    }
}

fn cli_native_version(source: &Path, reference: &str) -> String {
    let output = Command::new(NATIVE)
        .args([
            "template-bundle",
            "native-version",
            "--source-root",
            source.to_str().expect("source path UTF-8"),
            "--source-ref",
            reference,
        ])
        .output()
        .expect("run native version command");
    assert_cli_success(&output, "resolve native version");
    serde_json::from_slice::<Value>(&output.stdout)
        .expect("native version JSON")
        .get("version")
        .and_then(Value::as_str)
        .expect("native version field")
        .to_owned()
}

#[test]
fn prepare_cli_uses_the_checked_out_source_and_writes_workflow_outputs() {
    let temporary = TemporaryDirectory::new("prepare-cli");
    let source = source_fixture(temporary.path());
    let github_output = temporary.path().join("github-output");
    fs::write(&github_output, b"").unwrap();
    let matrix = json!({
        "include": [{
            "target": TARGET,
            "runs_on": "ubuntu-24.04",
            "executable": "agent-canon",
            "rustflags": ""
        }]
    });
    let output = Command::new(NATIVE)
        .args([
            "native-release",
            "prepare",
            "--source-root",
            source.to_str().unwrap(),
            "--source-ref",
            "HEAD",
            "--event",
            "push",
            "--ref",
            "refs/heads/main",
            "--ref-name",
            "main",
            "--publish-request",
            "false",
            "--release-tag",
            "",
            "--matrix-json",
            &serde_json::to_string(&matrix).unwrap(),
        ])
        .env("GITHUB_OUTPUT", &github_output)
        .output()
        .expect("run native release preparation");
    assert_cli_success(&output, "prepare native release");
    let result: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(result["version"], "0.1.0");
    assert_eq!(result["tag"], "v0.1.0");
    assert!(result["publish"].as_bool().unwrap());
    let outputs = fs::read_to_string(github_output).unwrap();
    assert!(outputs.contains("version=0.1.0\n"));
    assert!(outputs.contains("tag=v0.1.0\n"));
    assert!(outputs.contains("publish=true\n"));
    assert!(outputs.contains(&format!("targets=[\"{TARGET}\"]\n")));
}

#[test]
fn reproducibility_cli_compares_binary_and_complete_package_file_set() {
    let fixture = fixture("reproducible-cli");
    let original_binary = fixture.runtime.join("original-agent-canon");
    let rebuilt_binary = fixture.runtime.join("rebuilt-agent-canon");
    fs::write(&original_binary, b"executable bytes\n").unwrap();
    fs::write(&rebuilt_binary, b"executable bytes\n").unwrap();
    let rebuilt_packages = fixture.runtime.join("rebuilt-packages");
    fs::create_dir_all(&rebuilt_packages).unwrap();
    for entry in fs::read_dir(&fixture.packages).unwrap() {
        let entry = entry.unwrap();
        fs::copy(entry.path(), rebuilt_packages.join(entry.file_name())).unwrap();
    }
    let compare = || {
        Command::new(NATIVE)
            .args([
                "native-release",
                "compare-reproducible",
                "--binary",
                original_binary.to_str().unwrap(),
                "--rebuilt-binary",
                rebuilt_binary.to_str().unwrap(),
                "--packages",
                fixture.packages.to_str().unwrap(),
                "--rebuilt-packages",
                rebuilt_packages.to_str().unwrap(),
            ])
            .output()
            .unwrap()
    };
    let output = compare();
    assert_cli_success(&output, "compare reproducible package");
    assert!(String::from_utf8_lossy(&output.stdout).contains("reproduced"));
    fs::write(&rebuilt_binary, b"different executable bytes\n").unwrap();
    let output = compare();
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("independent rebuild differs"));
}

#[derive(Default)]
struct FakeGitHub {
    commands: Vec<Vec<String>>,
    release: Option<Value>,
    tagged: Option<String>,
    fail_upload: bool,
    hide_draft_lists: bool,
    change_draft_source_after_upload: bool,
    change_tag_after_upload: bool,
}

impl FakeGitHub {
    fn result(returncode: i32, stdout: String, stderr: &str) -> CommandResult {
        CommandResult {
            returncode,
            stdout,
            stderr: stderr.to_owned(),
        }
    }

    fn http(value: Option<Value>) -> (i32, String) {
        let code = if value.is_some() { 200 } else { 404 };
        let body = value
            .map(|value| serde_json::to_string(&value).unwrap())
            .unwrap_or_else(|| "null".to_owned());
        (
            if code == 200 { 0 } else { 1 },
            format!("HTTP/2.0 {code} OK\ncontent-type: application/json\n\n{body}"),
        )
    }

    fn run(&mut self, args: &[String]) -> CommandResult {
        self.commands.push(args.to_vec());
        if args.first().map(String::as_str) != Some("gh")
            || args.get(1).map(String::as_str) != Some("api")
        {
            return Self::result(2, String::new(), "unexpected fake command");
        }
        match args.get(2).map(String::as_str) {
            Some("--include") => {
                let endpoint = args.get(3).map(String::as_str).unwrap_or_default();
                let value = if endpoint.contains("/git/ref/tags/") {
                    self.tagged
                        .as_ref()
                        .map(|sha| json!({"object": {"type": "commit", "sha": sha}}))
                } else if endpoint.contains("/git/tags/") {
                    None
                } else if endpoint.contains("/releases?") {
                    if self.hide_draft_lists {
                        Some(json!([]))
                    } else {
                        Some(Value::Array(self.release.iter().cloned().collect()))
                    }
                } else if endpoint.contains("/releases/tags/") {
                    self.release
                        .as_ref()
                        .filter(|release| release["draft"].as_bool() == Some(false))
                        .cloned()
                } else if endpoint.contains("/releases/") {
                    self.release.clone()
                } else {
                    None
                };
                let (code, stdout) = Self::http(value);
                Self::result(code, stdout, "not found")
            }
            Some("--method") => match args.get(3).map(String::as_str) {
                Some("POST")
                    if args
                        .get(4)
                        .is_some_and(|url| url.starts_with("https://uploads.github.com/")) =>
                {
                    let Some(path) = args
                        .iter()
                        .position(|argument| argument == "--input")
                        .and_then(|index| args.get(index + 1))
                    else {
                        return Self::result(2, String::new(), "upload path is missing");
                    };
                    let path = Path::new(path);
                    let bytes = match fs::read(path) {
                        Ok(bytes) => bytes,
                        Err(error) => {
                            return Self::result(2, String::new(), &error.to_string());
                        }
                    };
                    let Some(release) = self.release.as_mut() else {
                        return Self::result(2, String::new(), "release missing");
                    };
                    let asset = json!({
                        "name": path.file_name().unwrap().to_string_lossy(),
                        "state": "uploaded",
                        "size": bytes.len(),
                        "digest": format!("sha256:{}", sha256(&bytes)),
                    });
                    release["assets"]
                        .as_array_mut()
                        .unwrap()
                        .push(asset.clone());
                    if self.change_draft_source_after_upload {
                        release["target_commitish"] = Value::String("0".repeat(40));
                    }
                    if self.change_tag_after_upload {
                        self.tagged = Some("0".repeat(40));
                    }
                    if self.fail_upload {
                        Self::result(1, String::new(), "interrupted after one upload")
                    } else {
                        Self::result(0, serde_json::to_string(&asset).unwrap(), "")
                    }
                }
                Some("POST") => {
                    let mut fields = BTreeMap::new();
                    let mut index = 5;
                    while index + 1 < args.len() {
                        if matches!(args[index].as_str(), "-f" | "-F") {
                            if let Some((key, value)) = args[index + 1].split_once('=') {
                                fields.insert(key.to_owned(), value.to_owned());
                            }
                            index += 2;
                        } else {
                            index += 1;
                        }
                    }
                    self.release = Some(json!({
                        "id": 1,
                        "tag_name": fields.get("tag_name").cloned().unwrap_or_default(),
                        "draft": true,
                        "prerelease": false,
                        "target_commitish": fields.get("target_commitish").cloned().unwrap_or_default(),
                        "assets": [],
                        "html_url": "https://github.com/owner/repo/releases/tag/untagged-test",
                    }));
                    Self::result(
                        0,
                        serde_json::to_string(self.release.as_ref().unwrap()).unwrap(),
                        "",
                    )
                }
                Some("PATCH") => {
                    let Some(release) = self.release.as_mut() else {
                        return Self::result(2, String::new(), "release missing");
                    };
                    release["draft"] = Value::Bool(false);
                    if self.tagged.is_none() {
                        self.tagged = release["target_commitish"].as_str().map(str::to_owned);
                    }
                    Self::result(0, serde_json::to_string(release).unwrap(), "")
                }
                _ => Self::result(2, String::new(), "unexpected API method"),
            },
            _ => Self::result(2, String::new(), "unexpected gh API command"),
        }
    }

    fn write_count(&self) -> usize {
        self.commands
            .iter()
            .filter(|args| {
                args.get(2).map(String::as_str) == Some("--method")
                    && matches!(args.get(3).map(String::as_str), Some("POST" | "PATCH"))
            })
            .count()
    }

    fn publication_count(&self) -> usize {
        self.commands
            .iter()
            .filter(|args| {
                args.get(2).map(String::as_str) == Some("--method")
                    && args.get(3).map(String::as_str) == Some("PATCH")
            })
            .count()
    }
}

fn publish(
    fixture: &NativeReleaseFixture,
    github: &mut FakeGitHub,
    check_only: bool,
) -> Result<Value, NativeReleaseError> {
    let request = request(fixture, "v0.1.0", check_only);
    let mut runner = |args: &[String]| github.run(args);
    publish_native_release(&request, &mut runner)
}

#[test]
fn native_archives_bind_all_files_to_the_requested_source() {
    let fixture = fixture("verify");
    let output = verify(&fixture, &[TARGET]);
    assert_cli_success(&output, "verify native package");
    let verified: Value = serde_json::from_slice(&output.stdout).expect("verification JSON");
    assert_eq!(verified["source_commit"], fixture.identity["source_commit"]);
    assert_eq!(verified["version"], "0.1.0");
    assert_eq!(verified["files"].as_array().unwrap().len(), 4);
    assert_eq!(verified["targets"], json!([TARGET]));
}

#[test]
fn archive_checksum_drift_is_rejected() {
    let fixture = fixture("checksum");
    let path = fixture
        .packages
        .join(format!("agent-canon-0.1.0-{TARGET}.tar.gz"));
    let mut bytes = fs::read(&path).unwrap();
    bytes.extend_from_slice(b"changed");
    fs::write(path, bytes).unwrap();
    let output = verify(&fixture, &[TARGET]);
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("archive checksum differs"));
}

#[test]
fn self_consistent_wrong_source_identity_is_rejected() {
    let fixture = fixture("wrong-source");
    rewrite_archives(&fixture, &["tar.gz", "zip"], |_, payload| {
        let mut provenance: Value =
            serde_json::from_slice(payload.get("share/agent-canon/provenance.json").unwrap())
                .unwrap();
        provenance["source_commit"] = Value::String("0".repeat(40));
        let mut bytes = serde_json::to_vec_pretty(&provenance).unwrap();
        bytes.push(b'\n');
        payload.insert("share/agent-canon/provenance.json".to_owned(), bytes);
    });
    let output = verify(&fixture, &[TARGET]);
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("source identity differs"));
}

#[test]
fn self_consistent_different_archive_payloads_are_rejected() {
    let fixture = fixture("different-formats");
    rewrite_archives(&fixture, &["zip"], |_, payload| {
        payload.insert("bin/agent-canon".to_owned(), b"another binary".to_vec());
    });
    let output = verify(&fixture, &[TARGET]);
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("formats contain different payloads"));
}

#[test]
fn native_archive_file_set_rejects_missing_targets_and_extra_artifacts() {
    let fixture = fixture("file-set");
    let missing = verify(&fixture, &[TARGET, "aarch64-unknown-linux-gnu"]);
    assert!(!missing.status.success());
    assert!(String::from_utf8_lossy(&missing.stderr).contains("file set differs"));
    fs::write(fixture.packages.join("unexpected.txt"), b"extra").unwrap();
    let extra = verify(&fixture, &[TARGET]);
    assert!(!extra.status.success());
    assert!(String::from_utf8_lossy(&extra.stderr).contains("file set differs"));
}

#[test]
fn release_verification_failure_precedes_remote_writes() {
    let fixture = fixture("release-before-write");
    rewrite_archives(&fixture, &["tar.gz", "zip"], |_, payload| {
        let mut provenance: Value =
            serde_json::from_slice(payload.get("share/agent-canon/provenance.json").unwrap())
                .unwrap();
        provenance["source_commit"] = Value::String("0".repeat(40));
        payload.insert(
            "share/agent-canon/provenance.json".to_owned(),
            serde_json::to_vec_pretty(&provenance).unwrap(),
        );
        payload
            .get_mut("share/agent-canon/provenance.json")
            .unwrap()
            .push(b'\n');
    });
    let mut github = FakeGitHub::default();
    let error = publish(&fixture, &mut github, false).unwrap_err();
    assert!(error.to_string().contains("source identity differs"));
    assert!(github.commands.is_empty());
}

#[test]
fn draft_is_published_only_after_every_asset_is_verified() {
    let fixture = fixture("publish");
    let mut github = FakeGitHub::default();
    let result = publish(&fixture, &mut github, false).unwrap();
    assert_eq!(result["status"], "published");
    let release = github.release.as_ref().unwrap();
    assert_eq!(release["draft"].as_bool(), Some(false));
    assert_eq!(release["assets"].as_array().unwrap().len(), 4);
    assert_eq!(github.publication_count(), 1);
    let last_write = github
        .commands
        .iter()
        .rev()
        .find(|args| args.get(2).map(String::as_str) == Some("--method"))
        .unwrap();
    assert_eq!(last_write[3], "PATCH");
    assert!(last_write.contains(&"make_latest=legacy".to_owned()));
}

#[test]
fn creation_response_resumes_while_tag_and_release_listing_reads_lag() {
    let fixture = fixture("create-lag");
    let mut github = FakeGitHub::default();
    github.hide_draft_lists = true;
    assert_eq!(
        publish(&fixture, &mut github, false).unwrap()["status"],
        "published"
    );
    let creates = github
        .commands
        .iter()
        .filter(|args| {
            args.get(2).map(String::as_str) == Some("--method")
                && args.get(3).map(String::as_str) == Some("POST")
                && !args
                    .get(4)
                    .is_some_and(|url| url.starts_with("https://uploads.github.com/"))
        })
        .count();
    assert_eq!(creates, 1);
}

#[test]
fn interrupted_upload_resumes_only_missing_assets() {
    let fixture = fixture("resume-upload");
    let mut github = FakeGitHub::default();
    github.fail_upload = true;
    let error = publish(&fixture, &mut github, false).unwrap_err();
    assert!(error.to_string().contains("upload incomplete"));
    let release = github.release.as_ref().unwrap();
    assert_eq!(release["draft"].as_bool(), Some(true));
    let uploaded_name = release["assets"][0]["name"].as_str().unwrap().to_owned();
    assert_eq!(github.publication_count(), 0);
    let uploads_before = github
        .commands
        .iter()
        .filter(|args| {
            args.get(2).map(String::as_str) == Some("--method")
                && args.get(3).map(String::as_str) == Some("POST")
                && args
                    .get(4)
                    .is_some_and(|url| url.starts_with("https://uploads.github.com/"))
        })
        .count();
    github.fail_upload = false;
    assert_eq!(
        publish(&fixture, &mut github, false).unwrap()["status"],
        "published"
    );
    let uploads = github
        .commands
        .iter()
        .filter(|args| {
            args.get(2).map(String::as_str) == Some("--method")
                && args.get(3).map(String::as_str) == Some("POST")
                && args
                    .get(4)
                    .is_some_and(|url| url.starts_with("https://uploads.github.com/"))
        })
        .skip(uploads_before)
        .collect::<Vec<_>>();
    assert_eq!(uploads.len(), 3);
    assert!(!uploads.iter().any(|args| {
        args.get(args.iter().position(|arg| arg == "--input").unwrap() + 1)
            .and_then(|path| Path::new(path).file_name())
            .is_some_and(|name| name == uploaded_name)
    }));
    assert!(!github
        .commands
        .iter()
        .any(|args| args.contains(&"--clobber".to_owned())));
}

#[test]
fn published_release_reexecution_does_not_mutate_it() {
    let fixture = fixture("idempotent");
    let mut github = FakeGitHub::default();
    publish(&fixture, &mut github, false).unwrap();
    let writes = github.write_count();
    assert_eq!(
        publish(&fixture, &mut github, false).unwrap()["status"],
        "already-published"
    );
    assert_eq!(github.write_count(), writes);
}

#[test]
fn conflicting_existing_asset_is_preserved() {
    let fixture = fixture("asset-conflict");
    let mut github = FakeGitHub::default();
    publish(&fixture, &mut github, false).unwrap();
    github.release.as_mut().unwrap()["assets"][0]["digest"] =
        Value::String(format!("sha256:{}", "0".repeat(64)));
    let writes = github.write_count();
    let error = publish(&fixture, &mut github, false).unwrap_err();
    assert!(error.to_string().contains("existing release asset differs"));
    assert_eq!(github.write_count(), writes);
}

#[test]
fn wrong_tag_commit_never_creates_a_release() {
    let fixture = fixture("wrong-tag");
    let mut github = FakeGitHub::default();
    github.tagged = Some("0".repeat(40));
    let error = publish(&fixture, &mut github, false).unwrap_err();
    assert!(error.to_string().contains("different source commit"));
    assert_eq!(github.write_count(), 0);
}

#[test]
fn missing_mainline_fails_before_any_remote_request() {
    let fixture = fixture("missing-mainline");
    git(
        &fixture.source,
        &["update-ref", "-d", "refs/remotes/origin/main"],
    );
    let mut github = FakeGitHub::default();
    let error = publish(&fixture, &mut github, false).unwrap_err();
    assert!(error.to_string().contains("first-parent history"));
    assert!(github.commands.is_empty());
}

#[test]
fn check_only_reads_state_without_creating_a_draft() {
    let fixture = fixture("check-only");
    let mut github = FakeGitHub::default();
    let checked = publish(&fixture, &mut github, true).unwrap();
    assert_eq!(checked["status"], "checked");
    assert_eq!(checked["missing_assets"].as_array().unwrap().len(), 4);
    assert_eq!(github.write_count(), 0);
    assert!(github.release.is_none());
}

#[test]
fn changed_draft_source_is_rejected_before_publication() {
    let fixture = fixture("changed-draft");
    let mut github = FakeGitHub::default();
    github.change_draft_source_after_upload = true;
    let error = publish(&fixture, &mut github, false).unwrap_err();
    assert!(error
        .to_string()
        .contains("not bound to the requested source"));
    assert_eq!(github.publication_count(), 0);
}

#[test]
fn unrelated_draft_assets_are_preserved_without_publication() {
    let fixture = fixture("unrelated-draft");
    let mut github = FakeGitHub::default();
    github.release = Some(json!({
        "id": 1,
        "tag_name": "v0.1.0",
        "draft": true,
        "prerelease": false,
        "target_commitish": fixture.identity["source_commit"],
        "assets": [{"name": "unrelated.txt"}],
        "html_url": "https://github.com/owner/repo/releases/tag/v0.1.0",
    }));
    let error = publish(&fixture, &mut github, false).unwrap_err();
    assert!(error.to_string().contains("unrelated assets"));
    assert_eq!(github.write_count(), 0);
}

#[test]
fn changed_tag_is_rejected_before_publication() {
    let fixture = fixture("changed-tag");
    let mut github = FakeGitHub::default();
    github.change_tag_after_upload = true;
    let error = publish(&fixture, &mut github, false).unwrap_err();
    assert!(error.to_string().contains("release tag changed"));
    assert_eq!(github.publication_count(), 0);
}

fn commit_file(root: &Path, name: &str, bytes: &[u8]) -> String {
    write(root, name, bytes);
    git(root, &["add", name]);
    git(root, &["commit", "-qm", name]);
    git(root, &["rev-parse", "HEAD"])
}

#[test]
fn every_first_parent_main_update_receives_a_stable_distinct_patch() {
    let temporary = TemporaryDirectory::new("version-patches");
    let source = source_fixture(temporary.path());
    git(&source, &["tag", "v0.1.0"]);
    let first = commit_file(&source, "README.md", b"small documentation fix\n");
    assert_eq!(cli_native_version(&source, &first), "0.1.1");
    let second = commit_file(&source, "ci-note.txt", b"CI-only fix\n");
    assert_eq!(cli_native_version(&source, &second), "0.1.2");
    git(&source, &["tag", "v0.1.1", &first]);
    assert_eq!(cli_native_version(&source, &second), "0.1.2");
    assert_eq!(cli_native_version(&source, &first), "0.1.1");
    assert_eq!(git(&source, &["status", "--porcelain"]), "");
}

#[test]
fn a_new_cargo_baseline_works_before_its_first_release_tag() {
    let temporary = TemporaryDirectory::new("version-baseline");
    let source = source_fixture(temporary.path());
    git(&source, &["tag", "v0.1.0"]);
    let manifest = "tools/runtime/dispatch/agent-canon/Cargo.toml";
    let first = commit_file(
        &source,
        manifest,
        b"[package]\nname = \"agent-canon\"\nversion = \"0.2.0\"\n",
    );
    assert_eq!(cli_native_version(&source, &first), "0.2.0");
    let second = commit_file(&source, "README.md", b"next small change\n");
    assert_eq!(cli_native_version(&source, &second), "0.2.1");
    git(&source, &["tag", "v0.2.0", &first]);
    assert_eq!(cli_native_version(&source, &second), "0.2.1");
}

#[test]
fn an_unmerged_topic_cannot_consume_a_main_release_version() {
    let temporary = TemporaryDirectory::new("unmerged-topic");
    let source = source_fixture(temporary.path());
    git(&source, &["tag", "v0.1.0"]);
    git(&source, &["switch", "-c", "unmerged"]);
    let branch = commit_file(&source, "README.md", b"unmerged small change\n");
    assert_eq!(cli_native_version(&source, &branch), "0.1.1");
    assert!(require_mainline_source(&source, &branch)
        .unwrap_err()
        .to_string()
        .contains("first-parent history"));
}

#[test]
fn topic_commits_count_as_one_main_merge() {
    let temporary = TemporaryDirectory::new("topic-merge");
    let source = source_fixture(temporary.path());
    let main = git(&source, &["branch", "--show-current"]);
    git(&source, &["tag", "v0.1.0"]);
    git(&source, &["switch", "-c", "topic"]);
    commit_file(&source, "first.txt", b"one\n");
    commit_file(&source, "second.txt", b"two\n");
    git(&source, &["switch", &main]);
    git(
        &source,
        &["merge", "--no-ff", "-m", "merge small fix", "topic"],
    );
    assert_eq!(cli_native_version(&source, "HEAD"), "0.1.1");
}

#[test]
fn latest_retained_artifact_attempt_is_selected_per_target() {
    let artifacts = vec![
        json!({"name": "agent-canon-native-alpha-attempt-1", "id": 1, "expired": false}),
        json!({"name": "agent-canon-native-alpha-attempt-10", "id": 10, "expired": false}),
        json!({"name": "agent-canon-native-beta-attempt-1", "id": 20, "expired": false}),
        json!({"name": "agent-canon-native-beta-attempt-2", "id": 21, "expired": true}),
        json!({"name": "native-cli-checks-alpha-attempt-11", "id": 30, "expired": false}),
    ];
    let targets = vec!["alpha".to_owned(), "beta".to_owned()];
    let selected = select_native_artifacts(&artifacts, &targets).unwrap();
    assert_eq!(
        selected
            .iter()
            .map(|row| row["artifact_id"].as_u64().unwrap())
            .collect::<Vec<_>>(),
        vec![10, 20]
    );
    assert_eq!(
        selected
            .iter()
            .map(|row| row["attempt"].as_u64().unwrap())
            .collect::<Vec<_>>(),
        vec![10, 1]
    );
}

#[test]
fn missing_or_expired_artifact_targets_fail() {
    let error = select_native_artifacts(&[], &["alpha".to_owned()]).unwrap_err();
    assert!(error.to_string().contains("missing or expired"));
}
