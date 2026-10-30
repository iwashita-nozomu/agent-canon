//! Source-bound native release verification and resumable GitHub draft publication.
// @dependency-start
// contract implementation
// responsibility Owns source-bound native release planning, artifact selection, archive validation, and resumable draft publication.
// upstream implementation template_bundle.rs packages and verifies source-bound native artifacts
// downstream implementation lib.rs exposes the native release owner
// downstream implementation main.rs preserves the native release CLI selector
// downstream implementation ../../../.github/workflows/agent-canon-native-release.yml invokes current-source release operations
// downstream test ../tests/native_release_native.rs verifies release integrity and recovery
// @dependency-end

use crate::template_bundle::{self, TemplateBundleError};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;

/// A release operation failed before its requested state transition completed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NativeReleaseError(pub(crate) String);

impl fmt::Display for NativeReleaseError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for NativeReleaseError {}

impl From<TemplateBundleError> for NativeReleaseError {
    fn from(error: TemplateBundleError) -> Self {
        Self(error.to_string())
    }
}

/// Result type for native release operations.
pub type ReleaseResult<T> = Result<T, NativeReleaseError>;

fn set(object: &mut Value, key: &str, value: Value) -> ReleaseResult<()> {
    object
        .as_object_mut()
        .ok_or_else(|| release_error("native release result is invalid"))?
        .insert(key.to_owned(), value);
    Ok(())
}

/// Result captured from one configured `gh` subprocess invocation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommandResult {
    /// Process exit status, or `-1` when the process could not be started.
    pub returncode: i32,
    /// Captured standard output.
    pub stdout: String,
    /// Captured standard error.
    pub stderr: String,
}

/// Source and artifact identity for one native release publication.
#[derive(Debug, Clone)]
pub struct PublishRequest {
    /// Canonical AgentCanon source checkout.
    pub source_root: PathBuf,
    /// Requested source revision.
    pub source_ref: String,
    /// Directory containing the exact verified archive set.
    pub artifacts: PathBuf,
    /// Complete expected target set.
    pub targets: Vec<String>,
    /// GitHub owner/repository slug.
    pub repo: String,
    /// Stable release tag.
    pub tag: String,
    /// Verify remote state without creating or changing a release.
    pub check_only: bool,
}

fn release_error(message: impl Into<String>) -> NativeReleaseError {
    NativeReleaseError(message.into())
}

fn gh_runner(args: &[String]) -> CommandResult {
    let Some(program) = args.first() else {
        return CommandResult {
            returncode: -1,
            stdout: String::new(),
            stderr: "empty gh command".to_owned(),
        };
    };
    match Command::new(program).args(&args[1..]).output() {
        Ok(output) => CommandResult {
            returncode: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        },
        Err(error) => CommandResult {
            returncode: -1,
            stdout: String::new(),
            stderr: error.to_string(),
        },
    }
}

fn git(root: &Path, args: &[String]) -> ReleaseResult<CommandResult> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .map_err(|error| release_error(error.to_string()))?;
    Ok(CommandResult {
        returncode: output.status.code().unwrap_or(-1),
        stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
    })
}

/// Require a commit on the first-parent history of `refs/remotes/origin/main`.
pub fn require_mainline_source(source_root: &Path, source_ref: &str) -> ReleaseResult<String> {
    let resolved = git(
        source_root,
        &[
            "rev-parse".to_owned(),
            "--verify".to_owned(),
            "--end-of-options".to_owned(),
            format!("{source_ref}^{{commit}}"),
        ],
    )?;
    let history = git(
        source_root,
        &[
            "rev-list".to_owned(),
            "--first-parent".to_owned(),
            "refs/remotes/origin/main".to_owned(),
        ],
    )?;
    let commit = resolved.stdout.trim();
    if resolved.returncode != 0
        || history.returncode != 0
        || !history.stdout.lines().any(|candidate| candidate == commit)
    {
        return Err(release_error(
            "stable releases require a commit on origin/main's first-parent history",
        ));
    }
    Ok(commit.to_owned())
}

/// Select the latest unexpired successful workflow artifact for every target.
pub fn select_native_artifacts(
    artifacts: &[Value],
    targets: &[String],
) -> ReleaseResult<Vec<Value>> {
    let mut selected = BTreeMap::<String, (u64, Value)>::new();
    for artifact in artifacts {
        let expired = artifact
            .get("expired")
            .and_then(Value::as_bool)
            .ok_or_else(|| release_error("GitHub returned invalid artifact metadata"))?;
        if expired {
            continue;
        }
        let name = artifact
            .get("name")
            .and_then(Value::as_str)
            .ok_or_else(|| release_error("GitHub returned invalid artifact metadata"))?;
        let id = artifact
            .get("id")
            .ok_or_else(|| release_error("GitHub returned invalid artifact metadata"))?;
        for target in targets {
            let prefix = format!("agent-canon-native-{target}-attempt-");
            let Some(attempt_text) = name.strip_prefix(&prefix) else {
                continue;
            };
            if attempt_text.is_empty() || !attempt_text.bytes().all(|byte| byte.is_ascii_digit()) {
                continue;
            }
            let attempt = attempt_text
                .parse::<u64>()
                .map_err(|_| release_error("GitHub returned invalid artifact metadata"))?;
            if selected
                .get(target)
                .is_none_or(|(previous, _)| attempt > *previous)
            {
                selected.insert(
                    target.clone(),
                    (
                        attempt,
                        json!({
                            "target": target,
                            "attempt": attempt,
                            "artifact_id": id,
                        }),
                    ),
                );
            }
        }
    }
    let missing = targets
        .iter()
        .filter(|target| !selected.contains_key(*target))
        .cloned()
        .collect::<BTreeSet<_>>();
    if !missing.is_empty() {
        return Err(release_error(format!(
            "native CI artifacts are missing or expired: {:?}",
            missing.into_iter().collect::<Vec<_>>()
        )));
    }
    targets
        .iter()
        .map(|target| {
            selected
                .get(target)
                .map(|(_, row)| row.clone())
                .ok_or_else(|| release_error("native CI artifact selection is incomplete"))
        })
        .collect()
}

fn quote_component(value: &str) -> String {
    let mut encoded = String::new();
    for byte in value.bytes() {
        if byte.is_ascii_alphanumeric() || b"-_.~".contains(&byte) {
            encoded.push(byte as char);
        } else {
            encoded.push_str(&format!("%{byte:02X}"));
        }
    }
    encoded
}

fn api_json<F>(runner: &mut F, endpoint: &str, optional: bool) -> ReleaseResult<Option<Value>>
where
    F: FnMut(&[String]) -> CommandResult + ?Sized,
{
    let result = runner(&[
        "gh".to_owned(),
        "api".to_owned(),
        "--include".to_owned(),
        endpoint.to_owned(),
        "--header".to_owned(),
        "Cache-Control: no-cache".to_owned(),
    ]);
    let output = result.stdout.replace("\r\n", "\n");
    let (headers, body) = output
        .split_once("\n\n")
        .ok_or_else(|| release_error("gh did not return an HTTP response"))?;
    let code = headers
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|value| value.parse::<u16>().ok())
        .ok_or_else(|| release_error("gh did not return an HTTP response"))?;
    if optional && code == 404 {
        return Ok(None);
    }
    if result.returncode != 0 || code != 200 {
        return Err(release_error(format!(
            "GitHub read failed with HTTP {code}: {}",
            result.stderr.trim()
        )));
    }
    serde_json::from_str(body)
        .map(Some)
        .map_err(|_| release_error("GitHub returned invalid JSON"))
}

fn api<F>(runner: &mut F, endpoint: &str, optional: bool) -> ReleaseResult<Option<Value>>
where
    F: FnMut(&[String]) -> CommandResult + ?Sized,
{
    let value = api_json(runner, endpoint, optional)?;
    if value.as_ref().is_some_and(|value| !value.is_object()) {
        return Err(release_error("GitHub returned invalid release metadata"));
    }
    Ok(value)
}

fn release_for_tag<F>(runner: &mut F, repo: &str, tag: &str) -> ReleaseResult<Option<Value>>
where
    F: FnMut(&[String]) -> CommandResult + ?Sized,
{
    let release_endpoint = format!("repos/{repo}/releases/tags/{}", quote_component(tag));
    if let Some(release) = api(runner, &release_endpoint, true)? {
        return Ok(Some(release));
    }
    let mut page = 1usize;
    loop {
        let endpoint = format!("repos/{repo}/releases?per_page=100&page={page}");
        let releases = api_json(runner, &endpoint, false)?
            .ok_or_else(|| release_error("GitHub returned invalid draft metadata"))?;
        let rows = releases
            .as_array()
            .ok_or_else(|| release_error("GitHub returned invalid draft metadata"))?;
        for row in rows {
            if !row.is_object() {
                return Err(release_error("GitHub returned invalid draft metadata"));
            }
            if row.get("draft").and_then(Value::as_bool) == Some(true)
                && row.get("tag_name").and_then(Value::as_str) == Some(tag)
            {
                return Ok(Some(row.clone()));
            }
        }
        if rows.len() < 100 {
            return Ok(None);
        }
        page += 1;
    }
}

fn tag_commit<F>(runner: &mut F, repo: &str, tag: &str) -> ReleaseResult<Option<String>>
where
    F: FnMut(&[String]) -> CommandResult + ?Sized,
{
    let endpoint = format!("repos/{repo}/git/ref/tags/{}", quote_component(tag));
    let Some(mut reference) = api(runner, &endpoint, true)? else {
        return Ok(None);
    };
    let mut object = reference
        .as_object_mut()
        .and_then(|reference| reference.remove("object"))
        .ok_or_else(|| release_error("release tag metadata is invalid"))?;
    loop {
        match object.get("type").and_then(Value::as_str) {
            Some("tag") => {
                let sha = object
                    .get("sha")
                    .and_then(Value::as_str)
                    .ok_or_else(|| release_error("annotated tag metadata is invalid"))?;
                let annotated = api(runner, &format!("repos/{repo}/git/tags/{sha}"), false)?
                    .ok_or_else(|| release_error("annotated tag metadata is missing"))?;
                object = annotated
                    .as_object()
                    .and_then(|tag| tag.get("object"))
                    .cloned()
                    .ok_or_else(|| release_error("annotated tag metadata is invalid"))?;
            }
            Some("commit") => {
                return object
                    .get("sha")
                    .and_then(Value::as_str)
                    .map(|sha| Some(sha.to_owned()))
                    .ok_or_else(|| release_error("release tag metadata is invalid"));
            }
            _ => return Err(release_error("release tag does not resolve to a commit")),
        }
    }
}

fn release_bool(release: &Value, key: &str) -> ReleaseResult<bool> {
    release
        .get(key)
        .and_then(Value::as_bool)
        .ok_or_else(|| release_error("GitHub returned invalid release metadata"))
}

fn release_str<'a>(release: &'a Value, key: &str) -> ReleaseResult<&'a str> {
    release
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| release_error("GitHub returned invalid release metadata"))
}

fn missing_assets(
    release: &Value,
    expected: &BTreeMap<String, Value>,
) -> ReleaseResult<Vec<String>> {
    let assets = release
        .get("assets")
        .and_then(Value::as_array)
        .ok_or_else(|| release_error("GitHub returned invalid release metadata"))?;
    let mut by_name = BTreeMap::<String, Value>::new();
    for asset in assets {
        let name = asset
            .get("name")
            .and_then(Value::as_str)
            .ok_or_else(|| release_error("GitHub returned invalid release asset metadata"))?;
        by_name.insert(name.to_owned(), asset.clone());
    }
    let draft = release_bool(release, "draft")?;
    if draft && by_name.keys().any(|name| !expected.contains_key(name)) {
        return Err(release_error(
            "draft contains unrelated assets; preserved without publication",
        ));
    }
    for (name, actual) in &by_name {
        let Some(wanted) = expected.get(name) else {
            continue;
        };
        let actual_size = actual.get("size").and_then(Value::as_u64);
        let wanted_size = wanted.get("size").and_then(Value::as_u64);
        let actual_digest = actual.get("digest").and_then(Value::as_str);
        let wanted_digest = wanted
            .get("sha256")
            .and_then(Value::as_str)
            .map(|sha| format!("sha256:{sha}"));
        if actual.get("state").and_then(Value::as_str) != Some("uploaded")
            || actual_size != wanted_size
            || actual_digest != wanted_digest.as_deref()
        {
            return Err(release_error(format!(
                "existing release asset differs: {name}"
            )));
        }
    }
    Ok(expected
        .keys()
        .filter(|name| !by_name.contains_key(*name))
        .cloned()
        .collect())
}

fn validate_release(
    release: &Value,
    expected: &BTreeMap<String, Value>,
    tag: &str,
    commit: &str,
) -> ReleaseResult<Vec<String>> {
    if release_str(release, "tag_name")? != tag || release_bool(release, "prerelease")? {
        return Err(release_error(
            "existing release does not match the stable release request",
        ));
    }
    if release_bool(release, "draft")? && release_str(release, "target_commitish")? != commit {
        return Err(release_error(
            "draft is not bound to the requested source commit",
        ));
    }
    missing_assets(release, expected)
}

fn expected_assets(identity: &Value) -> ReleaseResult<BTreeMap<String, Value>> {
    let files = identity
        .get("files")
        .and_then(Value::as_array)
        .ok_or_else(|| release_error("native release identity has no asset records"))?;
    let mut expected = BTreeMap::new();
    for file in files {
        let name = file
            .get("path")
            .and_then(Value::as_str)
            .ok_or_else(|| release_error("native release asset record is invalid"))?;
        if expected.insert(name.to_owned(), file.clone()).is_some() {
            return Err(release_error("native release asset record is duplicated"));
        }
    }
    Ok(expected)
}

/// Verify and resume one draft release through the supplied configured `gh` runner.
pub fn publish_native_release<F>(request: &PublishRequest, runner: &mut F) -> ReleaseResult<Value>
where
    F: FnMut(&[String]) -> CommandResult + ?Sized,
{
    let identity = template_bundle::verify_native_packages(
        &request.source_root,
        &request.source_ref,
        &request.artifacts,
        &request.targets,
    )
    .map_err(NativeReleaseError::from)?;
    let version = identity
        .get("version")
        .and_then(Value::as_str)
        .ok_or_else(|| release_error("native release identity has no version"))?;
    if request.tag != format!("v{version}") {
        return Err(release_error(
            "release tag must match the source release version",
        ));
    }
    let commit = identity
        .get("source_commit")
        .and_then(Value::as_str)
        .ok_or_else(|| release_error("native release identity has no source commit"))?;
    require_mainline_source(&request.source_root, commit)?;
    let expected = expected_assets(&identity)?;
    let mut recovered = Vec::new();
    let tagged = tag_commit(runner, &request.repo, &request.tag)?;
    if tagged.as_deref().is_some_and(|tagged| tagged != commit) {
        return Err(release_error(
            "release tag points to a different source commit",
        ));
    }
    let mut release = release_for_tag(runner, &request.repo, &request.tag)?;
    let mut missing = if let Some(existing) = release.as_ref() {
        let missing = validate_release(existing, &expected, &request.tag, commit)?;
        if !release_bool(existing, "draft")? {
            if tagged.as_deref() != Some(commit) || !missing.is_empty() {
                return Err(release_error(
                    "published release is incomplete or has a different source",
                ));
            }
            let url = release_str(existing, "html_url")?.to_owned();
            let mut result = identity;
            set(
                &mut result,
                "status",
                Value::String("already-published".to_owned()),
            )?;
            set(&mut result, "url", Value::String(url))?;
            return Ok(result);
        }
        missing
    } else {
        expected.keys().cloned().collect()
    };
    if request.check_only {
        let mut result = identity;
        set(&mut result, "status", Value::String("checked".to_owned()))?;
        set(&mut result, "missing_assets", json!(missing))?;
        return Ok(result);
    }
    if release.is_none() {
        let notes = format!(
            "Native CLI {version}: archives and SHA256 sidecars for {}. Extract the matching archive and add bin/ to PATH. Source and command dependencies: https://github.com/{}/blob/{}/README.md#native-cli-distribution",
            request.targets.join(", "),
            request.repo,
            commit
        );
        let created = runner(&[
            "gh".to_owned(),
            "api".to_owned(),
            "--method".to_owned(),
            "POST".to_owned(),
            format!("repos/{}/releases", request.repo),
            "-f".to_owned(),
            format!("tag_name={}", request.tag),
            "-f".to_owned(),
            format!("target_commitish={commit}"),
            "-F".to_owned(),
            "draft=true".to_owned(),
            "-f".to_owned(),
            format!("name=AgentCanon {}", request.tag),
            "-f".to_owned(),
            format!("body={notes}"),
        ]);
        if created.returncode == 0 {
            let response: Value = serde_json::from_str(&created.stdout)
                .map_err(|_| release_error("draft creation returned invalid metadata"))?;
            if !response.is_object() {
                return Err(release_error("draft creation returned invalid metadata"));
            }
            release = Some(response);
        } else {
            release = release_for_tag(runner, &request.repo, &request.tag)?;
        }
        let Some(created_release) = release.as_ref() else {
            return Err(release_error(format!(
                "draft creation did not complete: {}",
                created.stderr.trim()
            )));
        };
        if !release_bool(created_release, "draft")?
            || release_str(created_release, "target_commitish")? != commit
        {
            return Err(release_error(
                "new draft does not match the requested source",
            ));
        }
        missing = validate_release(created_release, &expected, &request.tag, commit)?;
        if created.returncode != 0 {
            recovered.push(json!({
                "operation": "create",
                "error": created.stderr.trim(),
            }));
        }
    }
    let release = release
        .as_ref()
        .ok_or_else(|| release_error("draft release metadata is missing"))?;
    let release_id = release
        .get("id")
        .and_then(Value::as_u64)
        .ok_or_else(|| release_error("GitHub returned invalid release metadata"))?;
    let release_endpoint = format!("repos/{}/releases/{release_id}", request.repo);
    if !missing.is_empty() {
        let mut upload_error = String::new();
        for name in &missing {
            let upload_url = format!(
                "https://uploads.github.com/repos/{}/releases/{release_id}/assets?name={}",
                request.repo,
                quote_component(name)
            );
            let uploaded = runner(&[
                "gh".to_owned(),
                "api".to_owned(),
                "--method".to_owned(),
                "POST".to_owned(),
                upload_url,
                "--header".to_owned(),
                "Content-Type: application/octet-stream".to_owned(),
                "--input".to_owned(),
                request.artifacts.join(name).to_string_lossy().into_owned(),
            ]);
            if uploaded.returncode != 0 {
                upload_error = uploaded.stderr.trim().to_owned();
                break;
            }
        }
        let Some(after_upload) = api(runner, &release_endpoint, false)? else {
            return Err(release_error("draft disappeared after upload"));
        };
        let remaining = validate_release(&after_upload, &expected, &request.tag, commit)?;
        if !remaining.is_empty() {
            return Err(release_error(format!(
                "upload incomplete; rerun the failed publication job to resume {:?}: {upload_error}",
                remaining
            )));
        }
        if !upload_error.is_empty() {
            recovered.push(json!({
                "operation": "upload",
                "error": upload_error,
            }));
        }
    }
    if tag_commit(runner, &request.repo, &request.tag)?
        .as_deref()
        .is_some_and(|tagged| tagged != commit)
    {
        return Err(release_error("release tag changed before publication"));
    }
    let release = api(runner, &release_endpoint, false)?
        .ok_or_else(|| release_error("draft release metadata is missing"))?;
    let mut publish_error = String::new();
    if release_bool(&release, "draft")? {
        let published = runner(&[
            "gh".to_owned(),
            "api".to_owned(),
            "--method".to_owned(),
            "PATCH".to_owned(),
            release_endpoint.clone(),
            "-F".to_owned(),
            "draft=false".to_owned(),
            "-f".to_owned(),
            "make_latest=legacy".to_owned(),
        ]);
        publish_error = published.stderr.trim().to_owned();
        if published.returncode != 0 {
            recovered.push(json!({
                "operation": "publish",
                "error": publish_error,
            }));
        }
    }
    let release = api(runner, &release_endpoint, false)?
        .ok_or_else(|| release_error("release publication did not complete"))?;
    if release_bool(&release, "draft")? {
        return Err(release_error(format!(
            "release publication did not complete: {publish_error}"
        )));
    }
    if tag_commit(runner, &request.repo, &request.tag)?.as_deref() != Some(commit)
        || !validate_release(&release, &expected, &request.tag, commit)?.is_empty()
    {
        return Err(release_error("published release readback differs"));
    }
    let url = release_str(&release, "html_url")?.to_owned();
    let mut result = identity;
    set(&mut result, "status", Value::String("published".to_owned()))?;
    set(&mut result, "url", Value::String(url))?;
    set(&mut result, "recovered_operations", Value::Array(recovered))?;
    Ok(result)
}

fn parse_options(
    args: &[String],
    allowed: &[&str],
    repeatable: &[&str],
    flags: &[&str],
) -> ReleaseResult<BTreeMap<String, Vec<String>>> {
    let mut options = BTreeMap::<String, Vec<String>>::new();
    let mut index = 0;
    while index < args.len() {
        let name = args[index].as_str();
        if flags.contains(&name) {
            if !allowed.contains(&name) || options.contains_key(name) {
                return Err(release_error(format!(
                    "invalid or duplicate option: {name}"
                )));
            }
            options.insert(name.to_owned(), vec!["true".to_owned()]);
            index += 1;
            continue;
        }
        if !allowed.contains(&name) {
            return Err(release_error(format!("unknown option: {name}")));
        }
        let value = args
            .get(index + 1)
            .ok_or_else(|| release_error(format!("missing value for {name}")))?;
        let values = options.entry(name.to_owned()).or_default();
        if !values.is_empty() && !repeatable.contains(&name) {
            return Err(release_error(format!("duplicate option: {name}")));
        }
        values.push(value.clone());
        index += 2;
    }
    Ok(options)
}

fn required<'a>(options: &'a BTreeMap<String, Vec<String>>, name: &str) -> ReleaseResult<&'a str> {
    options
        .get(name)
        .and_then(|values| values.first())
        .map(String::as_str)
        .ok_or_else(|| release_error(format!("missing required option {name}")))
}

fn append_github_outputs(outputs: &[(&str, String)]) -> ReleaseResult<()> {
    if outputs
        .iter()
        .any(|(_, value)| value.contains('\n') || value.contains('\r'))
    {
        return Err(release_error("GitHub output value contains a newline"));
    }
    let path = std::env::var_os("GITHUB_OUTPUT")
        .ok_or_else(|| release_error("GITHUB_OUTPUT is required for this operation"))?;
    let mut file = OpenOptions::new()
        .append(true)
        .open(PathBuf::from(path))
        .map_err(|error| release_error(format!("open GITHUB_OUTPUT: {error}")))?;
    for (key, value) in outputs {
        writeln!(file, "{key}={value}")
            .map_err(|error| release_error(format!("write GITHUB_OUTPUT: {error}")))?;
    }
    Ok(())
}

fn prepare_plan(options: &BTreeMap<String, Vec<String>>) -> ReleaseResult<Value> {
    let source_root = Path::new(required(options, "--source-root")?);
    let source_ref = required(options, "--source-ref")?;
    let event = required(options, "--event")?;
    let reference = required(options, "--ref")?;
    let ref_name = required(options, "--ref-name")?;
    let matrix: Value = serde_json::from_str(required(options, "--matrix-json")?)
        .map_err(|_| release_error("native release matrix is invalid JSON"))?;
    let rows = matrix
        .get("include")
        .and_then(Value::as_array)
        .ok_or_else(|| release_error("native release matrix has no include rows"))?;
    for row in rows {
        if row.get("target").and_then(Value::as_str).is_none() {
            return Err(release_error("native release matrix target is invalid"));
        }
    }
    let version = template_bundle::native_release_version(source_root, source_ref)
        .map_err(|error| release_error(error.to_string()))?;
    let tagged = reference.starts_with("refs/tags/v");
    let main_push = event == "push" && reference == "refs/heads/main";
    let publish_request = options
        .get("--publish-request")
        .and_then(|values| values.first())
        .is_some_and(|value| value == "true");
    let publish = main_push || (event == "push" && tagged) || publish_request;
    let mut tag = if main_push {
        format!("v{version}")
    } else if tagged {
        options
            .get("--release-tag")
            .and_then(|values| values.first())
            .filter(|value| !value.is_empty())
            .cloned()
            .unwrap_or_else(|| ref_name.to_owned())
    } else {
        options
            .get("--release-tag")
            .and_then(|values| values.first())
            .cloned()
            .unwrap_or_default()
    };
    if !publish {
        tag.clear();
    }
    if publish {
        require_mainline_source(source_root, source_ref)?;
        if tag != format!("v{version}") {
            return Err(release_error(format!(
                "release tag must match source release version v{version}"
            )));
        }
    }
    let targets = rows
        .iter()
        .map(|row| {
            row.get("target")
                .and_then(Value::as_str)
                .unwrap_or_default()
        })
        .collect::<Vec<_>>();
    let matrix_json = serde_json::to_string(&matrix)
        .map_err(|_| release_error("native release matrix could not be serialized"))?;
    let targets_json = serde_json::to_string(&targets)
        .map_err(|_| release_error("native release targets could not be serialized"))?;
    append_github_outputs(&[
        ("matrix", matrix_json),
        ("targets", targets_json),
        ("version", version.clone()),
        ("tag", tag.clone()),
        ("publish", publish.to_string()),
    ])?;
    Ok(json!({
        "matrix": matrix,
        "targets": targets,
        "version": version,
        "tag": tag,
        "publish": publish,
    }))
}

fn select_artifacts_from_github<F>(
    runner: &mut F,
    options: &BTreeMap<String, Vec<String>>,
) -> ReleaseResult<Value>
where
    F: FnMut(&[String]) -> CommandResult + ?Sized,
{
    let repo = required(options, "--repo")?;
    let run_id = required(options, "--run-id")?;
    let targets: Vec<String> = serde_json::from_str(required(options, "--targets-json")?)
        .map_err(|_| release_error("native release targets are invalid JSON"))?;
    let endpoint = format!("repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100");
    let result = runner(&[
        "gh".to_owned(),
        "api".to_owned(),
        "--paginate".to_owned(),
        "--slurp".to_owned(),
        endpoint,
    ]);
    if result.returncode != 0 {
        return Err(release_error(format!(
            "GitHub artifact read failed: {}",
            result.stderr.trim()
        )));
    }
    let pages: Value = serde_json::from_str(&result.stdout)
        .map_err(|_| release_error("GitHub returned invalid artifact metadata"))?;
    let pages = pages
        .as_array()
        .ok_or_else(|| release_error("GitHub returned invalid artifact metadata"))?;
    let mut artifacts = Vec::new();
    for page in pages {
        let rows = page
            .get("artifacts")
            .and_then(Value::as_array)
            .ok_or_else(|| release_error("GitHub returned invalid artifact metadata"))?;
        artifacts.extend(rows.iter().cloned());
    }
    let selected = select_native_artifacts(&artifacts, &targets)?;
    let ids = selected
        .iter()
        .map(|row| match row.get("artifact_id") {
            Some(Value::Number(id)) => Ok(id.to_string()),
            Some(Value::String(id)) => Ok(id.clone()),
            _ => Err(release_error("native CI artifact selection is incomplete")),
        })
        .collect::<ReleaseResult<Vec<_>>>()?
        .join(",");
    append_github_outputs(&[("ids", ids)])?;
    Ok(json!({"selected": selected}))
}

fn directory_files(root: &Path) -> ReleaseResult<BTreeMap<String, PathBuf>> {
    let mut files = BTreeMap::new();
    for entry in fs::read_dir(root).map_err(|error| {
        release_error(format!(
            "read package directory {}: {error}",
            root.display()
        ))
    })? {
        let entry =
            entry.map_err(|error| release_error(format!("read package directory: {error}")))?;
        let kind = entry
            .file_type()
            .map_err(|error| release_error(format!("inspect package file: {error}")))?;
        if !kind.is_file() {
            return Err(release_error(
                "independent rebuild package file set differs",
            ));
        }
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| release_error("independent rebuild package file set differs"))?;
        files.insert(name, entry.path());
    }
    Ok(files)
}

fn compare_file(first: &Path, second: &Path, name: &str) -> ReleaseResult<String> {
    let left = fs::read(first).map_err(|error| release_error(format!("read {name}: {error}")))?;
    let right = fs::read(second).map_err(|error| release_error(format!("read {name}: {error}")))?;
    if left != right {
        return Err(release_error(format!(
            "independent rebuild differs: {name}"
        )));
    }
    Ok(Sha256::digest(&left)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

fn compare_reproducible(options: &BTreeMap<String, Vec<String>>) -> ReleaseResult<Value> {
    let first_binary = Path::new(required(options, "--binary")?);
    let second_binary = Path::new(required(options, "--rebuilt-binary")?);
    let first_packages = Path::new(required(options, "--packages")?);
    let second_packages = Path::new(required(options, "--rebuilt-packages")?);
    let first_files = directory_files(first_packages)?;
    let second_files = directory_files(second_packages)?;
    if first_files.keys().collect::<Vec<_>>() != second_files.keys().collect::<Vec<_>>() {
        return Err(release_error("rebuilt package file set differs"));
    }
    let binary_name = first_binary
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| release_error("native executable path is invalid"))?;
    let mut records = vec![json!({
        "path": binary_name,
        "sha256": compare_file(first_binary, second_binary, binary_name)?,
    })];
    for (name, first) in &first_files {
        let second = second_files
            .get(name)
            .ok_or_else(|| release_error("rebuilt package file set differs"))?;
        records.push(json!({
            "path": name,
            "sha256": compare_file(first, second, name)?,
        }));
    }
    Ok(json!({"status": "reproduced", "files": records}))
}

fn print_json(value: &Value) -> ReleaseResult<()> {
    let output = serde_json::to_string(value)
        .map_err(|_| release_error("native release result could not be serialized"))?;
    println!("{output}");
    Ok(())
}

/// Native CLI for release planning, artifact selection, reproducibility and publication.
pub fn run(args: &[String]) -> i32 {
    let result = (|| -> ReleaseResult<(Value, bool)> {
        let operation = args
            .first()
            .ok_or_else(|| release_error("native-release operation is required"))?;
        let rest = &args[1..];
        let (allowed, repeatable, flags): (&[&str], &[&str], &[&str]) = match operation.as_str() {
            "prepare" => (
                &[
                    "--source-root",
                    "--source-ref",
                    "--event",
                    "--ref",
                    "--ref-name",
                    "--publish-request",
                    "--release-tag",
                    "--matrix-json",
                ],
                &[],
                &[],
            ),
            "select-artifacts" => (&["--repo", "--run-id", "--targets-json"], &[], &[]),
            "publish" => (
                &[
                    "--source-root",
                    "--source-ref",
                    "--artifacts",
                    "--target",
                    "--targets-json",
                    "--repo",
                    "--tag",
                    "--check-only",
                ],
                &["--target"],
                &["--check-only"],
            ),
            "compare-reproducible" => (
                &[
                    "--binary",
                    "--rebuilt-binary",
                    "--packages",
                    "--rebuilt-packages",
                ],
                &[],
                &[],
            ),
            "-h" | "--help" | "help" => {
                println!("Usage: agent-canon native-release <prepare|select-artifacts|publish|compare-reproducible> [options]");
                return Ok((Value::Null, false));
            }
            _ => return Err(release_error("native-release operation is invalid")),
        };
        let options = parse_options(rest, allowed, repeatable, flags)?;
        let value = match operation.as_str() {
            "prepare" => prepare_plan(&options)?,
            "select-artifacts" => {
                let mut runner = gh_runner;
                select_artifacts_from_github(&mut runner, &options)?
            }
            "publish" => {
                let targets = match (options.get("--target"), options.get("--targets-json")) {
                    (Some(_), Some(_)) => {
                        return Err(release_error("choose --target or --targets-json, not both"));
                    }
                    (Some(targets), None) => targets.clone(),
                    (None, Some(json)) => serde_json::from_str::<Vec<String>>(
                        json.first().map(String::as_str).unwrap_or_default(),
                    )
                    .map_err(|_| release_error("native release targets are invalid JSON"))?,
                    (None, None) => {
                        return Err(release_error(
                            "native release requires --target or --targets-json",
                        ));
                    }
                };
                let request = PublishRequest {
                    source_root: PathBuf::from(required(&options, "--source-root")?),
                    source_ref: required(&options, "--source-ref")?.to_owned(),
                    artifacts: PathBuf::from(required(&options, "--artifacts")?),
                    targets,
                    repo: required(&options, "--repo")?.to_owned(),
                    tag: required(&options, "--tag")?.to_owned(),
                    check_only: options.contains_key("--check-only"),
                };
                let mut runner = gh_runner;
                publish_native_release(&request, &mut runner)?
            }
            "compare-reproducible" => compare_reproducible(&options)?,
            _ => Value::Null,
        };
        Ok((value, operation == "compare-reproducible"))
    })();
    match result {
        Ok((value, true)) => {
            if let Some(files) = value.get("files").and_then(Value::as_array) {
                for file in files {
                    println!(
                        "reproduced {}  {}",
                        file.get("sha256")
                            .and_then(Value::as_str)
                            .unwrap_or_default(),
                        file.get("path").and_then(Value::as_str).unwrap_or_default()
                    );
                }
            }
            0
        }
        Ok((value, false)) if value.is_null() => 0,
        Ok((value, false)) => match print_json(&value) {
            Ok(()) => 0,
            Err(error) => {
                print_error(&error.to_string());
                2
            }
        },
        Err(error) => {
            print_error(&error.to_string());
            2
        }
    }
}

fn print_error(message: &str) {
    eprintln!("{}", json!({"status": "failed", "error": message}));
}
