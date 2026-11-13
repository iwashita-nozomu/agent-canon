//! Native repository-topic checkout lifecycle.

// @dependency-start
// contract implementation
// responsibility Owns isolated topic checkout preparation, native origin/main integration, publication readback, and reconstructibility cleanup.
// upstream design ../../../../../documents/rule/repository-topic-clone.md owns lifecycle and Git-state preservation
// upstream implementation authority/mod.rs owns receipt-bound parent directory capabilities
// upstream implementation checkout_identity.rs owns read-only checkout identity
// upstream implementation update_lifecycle_contract.rs validates publication receipts
// downstream test ../../../../../tests/agent_tools/test_repository_topic_clone.py drives the native CLI and checks Git readback
// @dependency-end

use crate::authority::{
    AttestationRequest, AttestedParent, NonEmptyTrimmedString, Nonce128,
    ParentOwnedDirectoryTarget, ParentOwnedPathReceipt, ParentRootAttestor,
};
use crate::{path_expansion, path_resolution, update_lifecycle_contract};
use serde_json::Value;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::io;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Output, Stdio};

pub const CHECKOUT_MODE_LINKED: &str = "linked-worktree";
pub const CHECKOUT_MODE_INDEPENDENT: &str = "independent-clone";
const CANONICAL_MARKER: &str = "repository-topic-clone";
const LEGACY_MODULE_MARKER: &str = "agent-canon.topic";
const WORKSPACE_PROBE: &str = "workspace/.agent-canon-workspace-probe";

const USAGE: &str = "usage: agent-canon repository-topic-clone <prepare|merge-main|finalize-merge|verify-publication|cleanup> [options]";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CheckoutMode {
    LinkedWorktree,
    IndependentClone,
}

impl CheckoutMode {
    fn parse(value: &str) -> Result<Self, WorkspaceLifecycleError> {
        match value {
            CHECKOUT_MODE_LINKED => Ok(Self::LinkedWorktree),
            CHECKOUT_MODE_INDEPENDENT => Ok(Self::IndependentClone),
            _ => Err(WorkspaceLifecycleError::new(format!(
                "checkout_mode must be linked-worktree or independent-clone: {value:?}"
            ))),
        }
    }
}

#[derive(Clone, Debug)]
pub struct RepositoryTopicCloneRequest {
    pub url: String,
    pub repository: String,
    pub workspace_root: PathBuf,
    pub topic: String,
    pub branch: String,
    pub checkout_mode: CheckoutMode,
}

#[derive(Clone, Debug)]
pub struct PrepareReceipt {
    pub request: RepositoryTopicCloneRequest,
    pub clone: PathBuf,
    pub branch: String,
    pub candidate_sha: String,
    pub candidate_tree: String,
}

#[derive(Clone, Debug)]
pub struct MergeMainReceipt {
    pub request: RepositoryTopicCloneRequest,
    pub clone: PathBuf,
    pub candidate_sha: String,
    pub candidate_tree: String,
    pub merged_sha: String,
    pub merged_tree: String,
    pub origin_main_sha: String,
}

#[derive(Clone, Debug)]
pub struct CleanupProof {
    pub request: RepositoryTopicCloneRequest,
    pub clone: PathBuf,
    pub removed: bool,
    pub evidence: String,
}

/// A typed failure from repository-topic lifecycle operations.
#[derive(Debug)]
pub struct WorkspaceLifecycleError {
    detail: String,
}

impl WorkspaceLifecycleError {
    fn new(detail: impl Into<String>) -> Self {
        Self {
            detail: detail.into(),
        }
    }
}

impl std::fmt::Display for WorkspaceLifecycleError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.detail)
    }
}

impl std::error::Error for WorkspaceLifecycleError {}

/// Result returned by native workspace lifecycle APIs.
pub type LifecycleResult<T> = Result<T, WorkspaceLifecycleError>;

#[derive(Clone, Debug)]
struct CloneInspection {
    state: String,
    branch_source: Option<String>,
}

fn authority_error(error: impl std::fmt::Display) -> WorkspaceLifecycleError {
    WorkspaceLifecycleError::new(format!("parent-root-attestation:{error}"))
}

fn attest_parent(root: &Path, purpose: &str) -> LifecycleResult<AttestedParent> {
    let purpose = NonEmptyTrimmedString::new(purpose.to_owned()).map_err(authority_error)?;
    let nonce = Nonce128::generate().map_err(authority_error)?;
    ParentRootAttestor::new()
        .attest(&AttestationRequest {
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
            purpose,
            nonce,
        })
        .map_err(authority_error)
}

fn path_has_symlink_component(path: &Path) -> LifecycleResult<Option<PathBuf>> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|error| WorkspaceLifecycleError::new(format!("current directory: {error}")))?
            .join(path)
    };
    let mut current = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::RootDir | Component::CurDir => current.push(component.as_os_str()),
            Component::ParentDir => {
                current.pop();
            }
            Component::Normal(name) => current.push(name),
            Component::Prefix(prefix) => current.push(prefix.as_os_str()),
        }
        match fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.file_type().is_symlink() => return Ok(Some(current)),
            Ok(_) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(WorkspaceLifecycleError::new(format!(
                    "cannot inspect path component {}: {error}",
                    current.display()
                )))
            }
        }
    }
    Ok(None)
}

fn absolute_resolved(path: &Path) -> LifecycleResult<PathBuf> {
    let expanded = path_expansion::expand_user_path(path)
        .map_err(|error| WorkspaceLifecycleError::new(error.to_string()))?;
    let absolute = if expanded.is_absolute() {
        expanded
    } else {
        std::env::current_dir()
            .map_err(|error| WorkspaceLifecycleError::new(format!("current directory: {error}")))?
            .join(expanded)
    };
    if let Some(component) = path_has_symlink_component(&absolute)? {
        return Err(WorkspaceLifecycleError::new(format!(
            "workspace root contains symlinked path component: {}",
            component.display()
        )));
    }
    path_resolution::resolve_non_strict(&absolute).map_err(WorkspaceLifecycleError::new)
}

fn output_text(output: &Output) -> String {
    String::from_utf8_lossy(&output.stdout).into_owned()
}

fn git_error(cwd: &Path, args: &[OsString], output: &Output) -> WorkspaceLifecycleError {
    let command = args
        .iter()
        .map(|arg| arg.to_string_lossy())
        .collect::<Vec<_>>()
        .join(" ");
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
    WorkspaceLifecycleError::new(format!(
        "git -C {} {command}: {}",
        cwd.display(),
        if stderr.is_empty() {
            "command failed"
        } else {
            &stderr
        }
    ))
}

fn run_git_os(cwd: &Path, args: &[OsString]) -> LifecycleResult<Output> {
    let output = Command::new("git")
        .arg("-C")
        .arg(cwd)
        .args(args)
        .output()
        .map_err(|error| {
            WorkspaceLifecycleError::new(format!("git process unavailable: {error}"))
        })?;
    if !output.status.success() {
        return Err(git_error(cwd, args, &output));
    }
    Ok(output)
}

fn run_git(cwd: &Path, args: &[&str]) -> LifecycleResult<String> {
    let args = args
        .iter()
        .map(|argument| OsString::from(*argument))
        .collect::<Vec<_>>();
    Ok(output_text(&run_git_os(cwd, &args)?))
}

#[cfg(target_os = "linux")]
fn run_git_target(
    cwd: &Path,
    args: &[OsString],
    target: &ParentOwnedDirectoryTarget,
) -> LifecycleResult<String> {
    use std::os::unix::process::CommandExt;

    let descriptor = target.raw_fd();
    let mut command = Command::new("git");
    command.arg("-C").arg(cwd).args(args);
    unsafe {
        command.pre_exec(move || {
            use rustix::fd::BorrowedFd;
            use rustix::io::{fcntl_getfd, fcntl_setfd, FdFlags};
            let borrowed = BorrowedFd::borrow_raw(descriptor);
            let flags = fcntl_getfd(borrowed).map_err(io::Error::from)?;
            fcntl_setfd(borrowed, flags & !FdFlags::CLOEXEC).map_err(io::Error::from)
        });
    }
    let output = command.output().map_err(|error| {
        WorkspaceLifecycleError::new(format!("git process unavailable: {error}"))
    })?;
    if !output.status.success() {
        return Err(git_error(cwd, args, &output));
    }
    Ok(output_text(&output))
}

#[cfg(not(target_os = "linux"))]
fn run_git_target(
    _: &Path,
    _: &[OsString],
    _: &ParentOwnedDirectoryTarget,
) -> LifecycleResult<String> {
    Err(WorkspaceLifecycleError::new(
        "parent-root-attestation:unsupported-platform:descriptor-bound Git targets require Linux",
    ))
}

fn git_succeeds(cwd: &Path, args: &[&str]) -> bool {
    let args = args
        .iter()
        .map(|argument| OsString::from(*argument))
        .collect::<Vec<_>>();
    Command::new("git")
        .arg("-C")
        .arg(cwd)
        .args(args)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok_and(|status| status.success())
}

fn git_path(cwd: &Path, name: &str) -> LifecycleResult<PathBuf> {
    let value = run_git(cwd, &["rev-parse", "--git-path", name])?;
    let path = PathBuf::from(value.trim());
    Ok(if path.is_absolute() {
        path
    } else {
        cwd.join(path)
    })
}

fn git_common_dir(cwd: &Path) -> LifecycleResult<PathBuf> {
    let value = run_git(cwd, &["rev-parse", "--git-common-dir"])?;
    let path = PathBuf::from(value.trim());
    let path = if path.is_absolute() {
        path
    } else {
        cwd.join(path)
    };
    path_resolution::resolve_non_strict(&path).map_err(WorkspaceLifecycleError::new)
}

fn is_linked_worktree(path: &Path, anchor: Option<&Path>) -> bool {
    let Ok(git_dir) = run_git(path, &["rev-parse", "--git-dir"]) else {
        return false;
    };
    let mut git_dir = PathBuf::from(git_dir.trim());
    if !git_dir.is_absolute() {
        git_dir = path.join(git_dir);
    }
    let Ok(git_dir) = path_resolution::resolve_non_strict(&git_dir) else {
        return false;
    };
    let Ok(common) = git_common_dir(path) else {
        return false;
    };
    if git_dir == common {
        return false;
    }
    anchor.is_none_or(|anchor| git_common_dir(anchor).is_ok_and(|value| value == common))
}

fn normalize_url(value: &str) -> String {
    let mut value = value.trim().trim_end_matches('/').to_owned();
    if value.ends_with(".git") {
        value.truncate(value.len() - 4);
    }
    value
}

pub(crate) fn topic_slug(value: &str) -> LifecycleResult<String> {
    let value = value.trim();
    if value.is_empty() {
        return Err(WorkspaceLifecycleError::new("topic must be non-empty"));
    }
    let mut result = String::new();
    let mut separator = false;
    for character in value.chars() {
        if character.is_ascii_alphanumeric() {
            result.push(character.to_ascii_lowercase());
            separator = false;
        } else if !separator {
            result.push('-');
            separator = true;
        }
    }
    let result = result.trim_matches('-').to_owned();
    if result.is_empty() {
        return Err(WorkspaceLifecycleError::new(format!(
            "topic has no usable slug: {value:?}"
        )));
    }
    Ok(result)
}

fn repository_name(value: &str) -> LifecycleResult<String> {
    if value.is_empty()
        || matches!(value, "." | "..")
        || value
            .chars()
            .any(|character| matches!(character, '/' | '\\' | '\r' | '\n' | '\0'))
        || Path::new(value).file_name().and_then(OsStr::to_str) != Some(value)
    {
        return Err(WorkspaceLifecycleError::new(format!(
            "repository must be one safe path component: {value:?}"
        )));
    }
    Ok(value.to_owned())
}

fn normalize_branch(value: &str, cwd: &Path) -> LifecycleResult<String> {
    if value != value.trim() || value.contains(['\r', '\n', '\0']) {
        return Err(WorkspaceLifecycleError::new(format!(
            "branch must be an exact named branch: {value:?}"
        )));
    }
    run_git(cwd, &["check-ref-format", "--branch", value]).map_err(|_| {
        WorkspaceLifecycleError::new(format!("branch is not a valid named branch: {value:?}"))
    })?;
    Ok(value.to_owned())
}

pub(crate) fn validate_workspace_root(
    path: &Path,
    require_ignore: bool,
) -> LifecycleResult<PathBuf> {
    let root = absolute_resolved(path)?;
    if !root.is_dir() {
        return Err(WorkspaceLifecycleError::new(format!(
            "workspace root must be a directory: {}",
            root.display()
        )));
    }
    let workspace = root.join("workspace");
    if let Some(component) = path_has_symlink_component(&workspace)? {
        return Err(WorkspaceLifecycleError::new(format!(
            "workspace directory contains symlinked path component: {}",
            component.display()
        )));
    }
    let git_root = run_git(&root, &["rev-parse", "--show-toplevel"]).map_err(|_| {
        WorkspaceLifecycleError::new(format!(
            "workspace root must be a Git repository root: {}",
            root.display()
        ))
    })?;
    let git_root = path_resolution::resolve_non_strict(Path::new(git_root.trim()))
        .map_err(WorkspaceLifecycleError::new)?;
    if git_root != root {
        return Err(WorkspaceLifecycleError::new(format!(
            "workspace root must equal the Git toplevel: {}",
            root.display()
        )));
    }
    if require_ignore {
        require_workspace_ignored(&root)?;
    }
    Ok(root)
}

fn require_workspace_ignored(root: &Path) -> LifecycleResult<()> {
    let ignore = root.join(".gitignore");
    let metadata = fs::symlink_metadata(&ignore).map_err(|_| {
        WorkspaceLifecycleError::new(format!(
            "workspace root requires a regular .gitignore: {}",
            ignore.display()
        ))
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(WorkspaceLifecycleError::new(format!(
            "workspace root requires a regular .gitignore: {}",
            ignore.display()
        )));
    }
    run_git(root, &["ls-files", "--error-unmatch", "--", ".gitignore"]).map_err(|_| {
        WorkspaceLifecycleError::new(format!(
            "workspace root requires a tracked .gitignore: {}",
            ignore.display()
        ))
    })?;
    let output = run_git(
        root,
        &["check-ignore", "-v", "--no-index", "--", WORKSPACE_PROBE],
    )
    .map_err(|_| {
        WorkspaceLifecycleError::new(format!(
            "workspace root .gitignore must ignore {WORKSPACE_PROBE}"
        ))
    })?;
    let lines = output.lines().collect::<Vec<_>>();
    if lines.len() != 1 {
        return Err(WorkspaceLifecycleError::new(format!(
            "workspace root .gitignore probe is ambiguous: {WORKSPACE_PROBE}"
        )));
    }
    let (metadata, ignored_path) = lines[0].split_once('\t').ok_or_else(|| {
        WorkspaceLifecycleError::new(format!(
            "workspace root .gitignore probe is malformed: {}",
            lines[0]
        ))
    })?;
    let fields = metadata.rsplitn(3, ':').collect::<Vec<_>>();
    if fields.len() != 3 || ignored_path.trim() != WORKSPACE_PROBE {
        return Err(WorkspaceLifecycleError::new(format!(
            "workspace root .gitignore probe is malformed: {}",
            lines[0]
        )));
    }
    let source = PathBuf::from(fields[2]);
    let source = if source.is_absolute() {
        source
    } else {
        root.join(source)
    };
    let source =
        path_resolution::resolve_non_strict(&source).map_err(WorkspaceLifecycleError::new)?;
    if source != ignore {
        return Err(WorkspaceLifecycleError::new(format!(
            "workspace root .gitignore must own the ignore for {WORKSPACE_PROBE}"
        )));
    }
    Ok(())
}

fn attested_path(
    attested: &AttestedParent,
    candidate: &Path,
    purpose: &str,
) -> LifecycleResult<ParentOwnedPathReceipt> {
    let purpose = NonEmptyTrimmedString::new(purpose.to_owned()).map_err(authority_error)?;
    attested
        .resolve_parent_owned_path(candidate, purpose)
        .map_err(authority_error)
}

fn topic_root(root: &Path, topic: &str) -> LifecycleResult<PathBuf> {
    Ok(root.join("workspace").join(topic_slug(topic)?))
}

fn computed_clone_path(
    request: &RepositoryTopicCloneRequest,
    create_topic: bool,
    attested: &AttestedParent,
) -> LifecycleResult<PathBuf> {
    let repository = repository_name(&request.repository)?;
    let topic = topic_root(&request.workspace_root, &request.topic)?;
    if let Some(component) = path_has_symlink_component(&topic)? {
        return Err(WorkspaceLifecycleError::new(format!(
            "topic workspace contains symlinked path component: {}",
            component.display()
        )));
    }
    if create_topic {
        let purpose =
            NonEmptyTrimmedString::new("repository-topic-workspace").map_err(authority_error)?;
        attested
            .ensure_parent_owned_directory(&topic, purpose)
            .map_err(authority_error)?;
    } else if !topic.is_dir() || path_has_symlink_component(&topic)?.is_some() {
        return Err(WorkspaceLifecycleError::new(format!(
            "topic workspace is absent or unsafe: {}",
            topic.display()
        )));
    }
    let candidate = topic.join(repository);
    if let Some(component) = path_has_symlink_component(&candidate)? {
        return Err(WorkspaceLifecycleError::new(format!(
            "topic clone path contains symlinked path component: {}",
            component.display()
        )));
    }
    let receipt = attested_path(attested, &candidate, "repository-topic-clone")?;
    Ok(receipt.physical_path().to_path_buf())
}

pub(crate) fn projected_clone_path(
    workspace_root: &Path,
    topic: &str,
    repository: &str,
) -> LifecycleResult<PathBuf> {
    let root = validate_workspace_root(workspace_root, false)?;
    let repository = repository_name(repository)?;
    let topic = topic_root(&root, topic)?;
    if let Some(component) = path_has_symlink_component(&topic)? {
        return Err(WorkspaceLifecycleError::new(format!(
            "topic workspace contains symlinked path component: {}",
            component.display()
        )));
    }
    let candidate = topic.join(repository);
    if let Some(component) = path_has_symlink_component(&candidate)? {
        return Err(WorkspaceLifecycleError::new(format!(
            "topic clone path contains symlinked path component: {}",
            component.display()
        )));
    }
    let attested = attest_parent(&root, "repository-topic-clone")?;
    let receipt = attested_path(&attested, &candidate, "repository-topic-clone")?;
    Ok(receipt.physical_path().to_path_buf())
}

fn local_branch_exists(path: &Path, branch: &str) -> bool {
    let reference = format!("refs/heads/{branch}");
    git_succeeds(path, &["show-ref", "--verify", "--quiet", &reference])
}

fn remote_branch_exists(remote: &str, branch: &str) -> LifecycleResult<bool> {
    let args = [
        OsString::from("ls-remote"),
        OsString::from("--exit-code"),
        OsString::from("--heads"),
        OsString::from(remote),
        OsString::from(format!("refs/heads/{branch}")),
    ];
    let output = Command::new("git").args(&args).output().map_err(|error| {
        WorkspaceLifecycleError::new(format!("git process unavailable: {error}"))
    })?;
    if output.status.success() {
        return Ok(true);
    }
    if output.status.code() == Some(2) {
        return Ok(false);
    }
    Err(git_error(Path::new("."), &args, &output))
}

fn upstream(path: &Path, branch: &str) -> Option<String> {
    let reference = format!("{branch}@{{upstream}}");
    let output = Command::new("git")
        .arg("-C")
        .arg(path)
        .args(["rev-parse", "--abbrev-ref", &reference])
        .output()
        .ok()?;
    output
        .status
        .success()
        .then(|| output_text(&output).trim().to_owned())
}

fn ensure_independent_branch(path: &Path, remote: &str, branch: &str) -> LifecycleResult<String> {
    if local_branch_exists(path, branch) {
        run_git(path, &["checkout", branch])?;
        if let Some(upstream) = upstream(path, branch) {
            if upstream != format!("origin/{branch}") {
                return Err(WorkspaceLifecycleError::new(format!(
                    "prepare collision: branch-upstream-mismatch ({upstream})"
                )));
            }
            return Ok(format!("origin/{branch}"));
        }
        return Ok(format!(
            "local:{}",
            run_git(path, &["rev-parse", branch])?.trim()
        ));
    }
    if remote_branch_exists(remote, branch)? {
        run_git(path, &["fetch", "origin", branch])?;
        run_git(
            path,
            &[
                "checkout",
                "--track",
                "-b",
                branch,
                &format!("origin/{branch}"),
            ],
        )?;
        return Ok(format!("origin/{branch}"));
    }
    run_git(path, &["fetch", "origin", "main"])?;
    let base = run_git(path, &["rev-parse", "origin/main"])?;
    let base = base.trim();
    run_git(path, &["checkout", "-b", branch, base])?;
    Ok(format!("origin/main@{base}"))
}

fn ensure_linked_worktree(
    request: &RepositoryTopicCloneRequest,
    clone: &Path,
    attested: &AttestedParent,
) -> LifecycleResult<String> {
    if normalize_url(&run_git(
        &request.workspace_root,
        &["remote", "get-url", "origin"],
    )?) != normalize_url(&request.url)
    {
        return Err(WorkspaceLifecycleError::new(
            "prepare collision: anchor-origin-mismatch",
        ));
    }
    let (add_kind, branch_source, base_sha) =
        if local_branch_exists(&request.workspace_root, &request.branch) {
            let sha = run_git(&request.workspace_root, &["rev-parse", &request.branch])?;
            ("local", format!("local:{}", sha.trim()), None)
        } else if remote_branch_exists(&request.url, &request.branch)? {
            run_git(
                &request.workspace_root,
                &["fetch", "origin", &request.branch],
            )?;
            ("remote", format!("origin/{}", request.branch), None)
        } else {
            run_git(&request.workspace_root, &["fetch", "origin", "main"])?;
            let base = run_git(&request.workspace_root, &["rev-parse", "origin/main"])?;
            let base = base.trim().to_owned();
            ("main", format!("origin/main@{base}"), Some(base))
        };
    let initial = attested_path(attested, clone, "repository-topic-clone-worktree-create")?;
    if initial.target_exists() {
        return Err(WorkspaceLifecycleError::new(
            "prepare collision: linked worktree target already exists",
        ));
    }
    let mut args = vec![OsString::from("worktree"), OsString::from("add")];
    match add_kind {
        "local" => {}
        "remote" => {
            args.extend([
                OsString::from("--track"),
                OsString::from("-b"),
                OsString::from(&request.branch),
            ]);
        }
        _ => args.extend([OsString::from("-b"), OsString::from(&request.branch)]),
    }
    args.push(clone.as_os_str().to_os_string());
    match add_kind {
        "local" => args.push(OsString::from(&request.branch)),
        "remote" => args.push(OsString::from(format!("origin/{}", request.branch))),
        _ => args.push(OsString::from(base_sha.expect("main source has base"))),
    }
    run_git_os(&request.workspace_root, &args)?;
    let receipt = attested_path(attested, clone, "repository-topic-clone-worktree-create")?;
    if receipt.physical_path() != clone || !receipt.target_is_directory() {
        return Err(WorkspaceLifecycleError::new(
            "parent-root-attestation:root_race_detected:linked worktree target identity changed",
        ));
    }
    if !is_linked_worktree(clone, Some(&request.workspace_root)) {
        return Err(WorkspaceLifecycleError::new(
            "prepare collision: checkout-mode-mismatch",
        ));
    }
    #[cfg(target_os = "linux")]
    {
        use std::os::unix::fs::PermissionsExt;
        let anchor_mode = fs::metadata(&request.workspace_root)
            .map_err(|error| {
                WorkspaceLifecycleError::new(format!("cannot inspect workspace mode: {error}"))
            })?
            .permissions();
        attested
            .set_parent_owned_directory_mode(&receipt, anchor_mode.mode() & 0o7777)
            .map_err(authority_error)?;
    }
    run_git(clone, &["config", "extensions.worktreeConfig", "true"])?;
    Ok(branch_source)
}

fn config_marker(path: &Path, mode: &CheckoutMode, prefix: &str, field: &str) -> Option<String> {
    let config_scope = if *mode == CheckoutMode::LinkedWorktree {
        "--worktree"
    } else {
        "--local"
    };
    let key = format!("{prefix}.{field}");
    let args = ["config", config_scope, "--get", key.as_str()];
    Command::new("git")
        .arg("-C")
        .arg(path)
        .args(args)
        .output()
        .ok()
        .filter(|output| output.status.success())
        .map(|output| output_text(&output).trim().to_owned())
        .filter(|value| !value.is_empty())
}

fn marker_namespace_present(path: &Path, mode: &CheckoutMode, prefix: &str) -> bool {
    let config_scope = if *mode == CheckoutMode::LinkedWorktree {
        "--worktree"
    } else {
        "--local"
    };
    let pattern = format!("^{prefix}\\.");
    let args = [
        "config",
        config_scope,
        "--name-only",
        "--get-regexp",
        pattern.as_str(),
    ];
    Command::new("git")
        .arg("-C")
        .arg(path)
        .args(args)
        .output()
        .is_ok_and(|output| output.status.success() && !output.stdout.is_empty())
}

fn set_marker(path: &Path, mode: &CheckoutMode, field: &str, value: &str) -> LifecycleResult<()> {
    let config_scope = if *mode == CheckoutMode::LinkedWorktree {
        "--worktree"
    } else {
        "--local"
    };
    let key = format!("{CANONICAL_MARKER}.{field}");
    run_git(path, &["config", config_scope, &key, value])?;
    Ok(())
}

fn inspect_clone(
    path: &Path,
    request: &RepositoryTopicCloneRequest,
    require_clean: bool,
) -> CloneInspection {
    if !path.exists() {
        return CloneInspection {
            state: "absent".to_owned(),
            branch_source: None,
        };
    }
    if path.is_symlink() {
        return CloneInspection {
            state: "not-git".to_owned(),
            branch_source: None,
        };
    }
    if !path.is_dir() {
        return CloneInspection {
            state: "not-git".to_owned(),
            branch_source: None,
        };
    }
    let identity = match crate::checkout_identity::resolve(path) {
        Ok(value) if value.git_root != "unknown" => value,
        _ => {
            return CloneInspection {
                state: "not-git".to_owned(),
                branch_source: None,
            }
        }
    };
    let observed_root = Some(PathBuf::from(identity.git_root.clone()));
    let computed_root = path_resolution::resolve_non_strict(path).ok();
    if observed_root.is_none() || observed_root != computed_root {
        return CloneInspection {
            state: "repository-mismatch".to_owned(),
            branch_source: None,
        };
    }
    if git_path(path, "MERGE_HEAD").is_ok_and(|value| value.exists())
        || git_path(path, "MERGE_MSG").is_ok_and(|value| value.exists())
    {
        return CloneInspection {
            state: "merge-in-progress".to_owned(),
            branch_source: None,
        };
    }
    let linked = is_linked_worktree(path, Some(&request.workspace_root));
    if request.checkout_mode == CheckoutMode::LinkedWorktree && !linked {
        return CloneInspection {
            state: "checkout-mode-mismatch".to_owned(),
            branch_source: None,
        };
    }
    if request.checkout_mode == CheckoutMode::IndependentClone && is_linked_worktree(path, None) {
        return CloneInspection {
            state: "checkout-mode-mismatch".to_owned(),
            branch_source: None,
        };
    }
    if require_clean {
        match run_git(
            path,
            &[
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignore-submodules=none",
            ],
        ) {
            Ok(status) if status.trim().is_empty() => {}
            Ok(_) => {
                return CloneInspection {
                    state: "dirty-worktree-index-or-untracked".to_owned(),
                    branch_source: None,
                };
            }
            Err(_) => {
                return CloneInspection {
                    state: "git-status-unavailable".to_owned(),
                    branch_source: None,
                };
            }
        }
    }
    let remote = match run_git(path, &["config", "--get", "remote.origin.url"]) {
        Ok(value) => normalize_url(value.trim()),
        Err(_) => {
            return CloneInspection {
                state: "missing-remote".to_owned(),
                branch_source: None,
            }
        }
    };
    let requested_url = normalize_url(&request.url);
    if remote != requested_url {
        return CloneInspection {
            state: "url-mismatch".to_owned(),
            branch_source: None,
        };
    }
    let canonical_fields = ["repository", "topic", "branch", "url"];
    let mut canonical = std::collections::BTreeMap::new();
    for field in canonical_fields {
        canonical.insert(
            field,
            config_marker(path, &request.checkout_mode, CANONICAL_MARKER, field),
        );
    }
    let canonical_present = canonical.values().any(Option::is_some)
        || marker_namespace_present(path, &request.checkout_mode, CANONICAL_MARKER);
    let mut marker_branch = request.branch.clone();
    if canonical_present {
        if canonical.values().any(Option::is_none) {
            return CloneInspection {
                state: "marker-incomplete".to_owned(),
                branch_source: None,
            };
        }
        let url = canonical
            .get("url")
            .and_then(Option::as_deref)
            .unwrap_or_default();
        if normalize_url(url) != requested_url {
            return CloneInspection {
                state: "url-mismatch".to_owned(),
                branch_source: None,
            };
        }
        if canonical.get("repository").and_then(Option::as_deref)
            != Some(request.repository.as_str())
        {
            return CloneInspection {
                state: "repository-mismatch".to_owned(),
                branch_source: None,
            };
        }
        if canonical.get("topic").and_then(Option::as_deref)
            != topic_slug(&request.topic).ok().as_deref()
        {
            return CloneInspection {
                state: "topic-mismatch".to_owned(),
                branch_source: None,
            };
        }
        marker_branch = canonical
            .get("branch")
            .and_then(Option::as_ref)
            .cloned()
            .unwrap_or_default();
    } else {
        let fields = ["topic", "role", "module", "url", "branch", "placement"];
        let mut legacy = std::collections::BTreeMap::new();
        for field in fields {
            legacy.insert(
                field,
                config_marker(path, &request.checkout_mode, LEGACY_MODULE_MARKER, field),
            );
        }
        let legacy_present = legacy.values().any(Option::is_some)
            || marker_namespace_present(path, &request.checkout_mode, LEGACY_MODULE_MARKER);
        if legacy_present {
            if request.checkout_mode == CheckoutMode::LinkedWorktree {
                return CloneInspection {
                    state: "repository-mismatch".to_owned(),
                    branch_source: None,
                };
            }
            if legacy.values().any(Option::is_none) {
                return CloneInspection {
                    state: "legacy-marker-incomplete".to_owned(),
                    branch_source: None,
                };
            }
            let module = legacy
                .get("module")
                .and_then(Option::as_deref)
                .unwrap_or_default();
            let module_name = Path::new(module)
                .file_name()
                .and_then(OsStr::to_str)
                .unwrap_or_default();
            let exact = legacy.get("topic").and_then(Option::as_deref)
                == topic_slug(&request.topic).ok().as_deref()
                && legacy.get("role").and_then(Option::as_deref) == Some("module")
                && module_name == request.repository
                && legacy
                    .get("url")
                    .and_then(Option::as_deref)
                    .is_some_and(|value| normalize_url(value) == requested_url)
                && legacy
                    .get("branch")
                    .and_then(Option::as_deref)
                    .is_some_and(|value| value == request.branch)
                && legacy.get("placement").and_then(Option::as_deref)
                    == Some("workspace-continuation");
            if !exact {
                return CloneInspection {
                    state: "legacy-marker-mismatch".to_owned(),
                    branch_source: None,
                };
            }
            marker_branch = legacy
                .get("branch")
                .and_then(Option::as_ref)
                .cloned()
                .unwrap_or_default();
        }
    }
    let actual_branch = identity.branch;
    if actual_branch == "detached" {
        return CloneInspection {
            state: "detached".to_owned(),
            branch_source: None,
        };
    }
    if marker_branch != actual_branch {
        return CloneInspection {
            state: "actual-branch-mismatch".to_owned(),
            branch_source: None,
        };
    }
    if actual_branch != request.branch {
        return CloneInspection {
            state: "branch-mismatch".to_owned(),
            branch_source: None,
        };
    }
    let branch_source = config_marker(
        path,
        &request.checkout_mode,
        CANONICAL_MARKER,
        "branch-source",
    );
    CloneInspection {
        state: "ready".to_owned(),
        branch_source,
    }
}

fn set_checkout_markers(
    path: &Path,
    request: &RepositoryTopicCloneRequest,
    branch_source: &str,
) -> LifecycleResult<()> {
    if request.checkout_mode == CheckoutMode::LinkedWorktree {
        run_git(path, &["config", "extensions.worktreeConfig", "true"])?;
    }
    let values = [
        ("repository", request.repository.clone()),
        ("topic", topic_slug(&request.topic)?),
        ("branch", request.branch.clone()),
        ("url", normalize_url(&request.url)),
        ("branch-source", branch_source.to_owned()),
    ];
    for (field, value) in values {
        set_marker(path, &request.checkout_mode, field, &value)?;
    }
    Ok(())
}

pub fn prepare(request: &RepositoryTopicCloneRequest) -> LifecycleResult<PrepareReceipt> {
    let root = validate_workspace_root(&request.workspace_root, true)?;
    let repository = repository_name(&request.repository)?;
    let branch = normalize_branch(&request.branch, &root)?;
    let mut request = request.clone();
    request.workspace_root = root;
    request.repository = repository;
    request.branch = branch;
    if request.url.trim().is_empty() {
        return Err(WorkspaceLifecycleError::new("url must be non-empty"));
    }
    if request.checkout_mode == CheckoutMode::LinkedWorktree
        && normalize_url(&run_git(
            &request.workspace_root,
            &["remote", "get-url", "origin"],
        )?) != normalize_url(&request.url)
    {
        return Err(WorkspaceLifecycleError::new(
            "prepare collision: anchor-origin-mismatch",
        ));
    }
    let attested = attest_parent(&request.workspace_root, "repository-topic-clone")?;
    let clone = computed_clone_path(&request, true, &attested)?;
    let initial = inspect_clone(&clone, &request, true);
    let branch_source = match initial.state.as_str() {
        "absent" => {
            if request.checkout_mode == CheckoutMode::LinkedWorktree {
                ensure_linked_worktree(&request, &clone, &attested)?
            } else {
                let purpose = NonEmptyTrimmedString::new("repository-topic-clone-create")
                    .map_err(authority_error)?;
                let target = attested
                    .reserve_parent_owned_directory_target(&clone, purpose)
                    .map_err(authority_error)?;
                let args = [
                    OsString::from("clone"),
                    OsString::from(&request.url),
                    target.child_process_path().into_os_string(),
                ];
                let result = run_git_target(&request.workspace_root, &args, &target);
                if let Err(error) = result {
                    let cleanup = attested.abort_parent_owned_directory_target(&target);
                    if let Err(cleanup) = cleanup {
                        return Err(WorkspaceLifecycleError::new(format!(
                            "clone-create-failed:{error}; target-cleanup-failed:{cleanup}"
                        )));
                    }
                    return Err(error);
                }
                attested
                    .verify_parent_owned_directory_target(&target)
                    .map_err(authority_error)?;
                ensure_independent_branch(&clone, &request.url, &request.branch)?
            }
        }
        "ready" => {
            if request.checkout_mode == CheckoutMode::LinkedWorktree {
                initial
                    .branch_source
                    .unwrap_or_else(|| "existing".to_owned())
            } else {
                ensure_independent_branch(&clone, &request.url, &request.branch)?
            }
        }
        "actual-branch-mismatch" | "branch-mismatch"
            if request.checkout_mode == CheckoutMode::IndependentClone =>
        {
            ensure_independent_branch(&clone, &request.url, &request.branch)?
        }
        "dirty-worktree-index-or-untracked"
        | "merge-in-progress"
        | "detached"
        | "not-git"
        | "missing-remote"
        | "url-mismatch"
        | "repository-mismatch"
        | "topic-mismatch"
        | "checkout-mode-mismatch"
        | "actual-branch-mismatch"
        | "branch-mismatch" => {
            return Err(WorkspaceLifecycleError::new(format!(
                "prepare collision: {}",
                initial.state
            )))
        }
        state => {
            return Err(WorkspaceLifecycleError::new(format!(
                "prepare rejected: {state}"
            )))
        }
    };
    let branch = run_git(&clone, &["symbolic-ref", "--quiet", "--short", "HEAD"])?
        .trim()
        .to_owned();
    if branch != request.branch {
        return Err(WorkspaceLifecycleError::new(format!(
            "prepared clone branch differs from request: {branch}"
        )));
    }
    set_checkout_markers(&clone, &request, &branch_source)?;
    let final_state = inspect_clone(&clone, &request, true);
    if final_state.state != "ready" {
        return Err(WorkspaceLifecycleError::new(format!(
            "prepared clone not ready: {}",
            final_state.state
        )));
    }
    let identity =
        crate::checkout_identity::resolve(&clone).map_err(WorkspaceLifecycleError::new)?;
    let candidate_sha = identity.head;
    let candidate_tree = run_git(&clone, &["rev-parse", &format!("{candidate_sha}^{{tree}}")])?
        .trim()
        .to_owned();
    Ok(PrepareReceipt {
        request,
        clone,
        branch,
        candidate_sha,
        candidate_tree,
    })
}

pub fn merge_main(request: &RepositoryTopicCloneRequest) -> LifecycleResult<MergeMainReceipt> {
    let root = validate_workspace_root(&request.workspace_root, false)?;
    let mut request = request.clone();
    request.workspace_root = root;
    request.repository = repository_name(&request.repository)?;
    request.branch = normalize_branch(&request.branch, &request.workspace_root)?;
    let attested = attest_parent(&request.workspace_root, "repository-topic-clone")?;
    let clone = computed_clone_path(&request, false, &attested)?;
    if clone.exists() {
        let state = inspect_clone(&clone, &request, true);
        if state.state == "dirty-worktree-index-or-untracked" {
            return Err(WorkspaceLifecycleError::new(
                "merge-main hold: dirty-worktree-index-or-untracked",
            ));
        }
    }
    let prepared = prepare(&request)?;
    let request = prepared.request;
    let clone = prepared.clone;
    run_git(&clone, &["fetch", "origin", "main"])?;
    let candidate_sha = run_git(&clone, &["rev-parse", "HEAD"])?.trim().to_owned();
    let candidate_tree = run_git(&clone, &["rev-parse", &format!("{candidate_sha}^{{tree}}")])?
        .trim()
        .to_owned();
    let origin_main_sha = run_git(&clone, &["rev-parse", "origin/main"])?
        .trim()
        .to_owned();
    let merge = run_git(&clone, &["merge", "--no-edit", "origin/main"]);
    if let Err(error) = merge {
        if git_path(&clone, "MERGE_HEAD").is_ok_and(|path| path.exists()) {
            return Err(WorkspaceLifecycleError::new(
                "merge-conflict: native origin/main merge remains in progress; resolve the actual Git index conflicts before finalizing",
            ));
        }
        return Err(error);
    }
    let merged_sha = run_git(&clone, &["rev-parse", "HEAD"])?.trim().to_owned();
    let merged_tree = run_git(&clone, &["rev-parse", &format!("{merged_sha}^{{tree}}")])?
        .trim()
        .to_owned();
    run_git(
        &clone,
        &["merge-base", "--is-ancestor", &candidate_sha, &merged_sha],
    )?;
    run_git(
        &clone,
        &["merge-base", "--is-ancestor", &origin_main_sha, &merged_sha],
    )?;
    Ok(MergeMainReceipt {
        request,
        clone,
        candidate_sha,
        candidate_tree,
        merged_sha,
        merged_tree,
        origin_main_sha,
    })
}

pub fn finalize_merge_main(
    request: &RepositoryTopicCloneRequest,
) -> LifecycleResult<MergeMainReceipt> {
    let root = validate_workspace_root(&request.workspace_root, false)?;
    let mut request = request.clone();
    request.workspace_root = root;
    request.repository = repository_name(&request.repository)?;
    request.branch = normalize_branch(&request.branch, &request.workspace_root)?;
    let attested = attest_parent(&request.workspace_root, "repository-topic-clone")?;
    let clone = computed_clone_path(&request, false, &attested)?;
    if !clone.is_dir() || !clone.join(".git").exists() {
        return Err(WorkspaceLifecycleError::new(
            "merge-finalize hold: clone is unavailable",
        ));
    }
    if request.checkout_mode == CheckoutMode::LinkedWorktree
        && !is_linked_worktree(&clone, Some(&request.workspace_root))
    {
        return Err(WorkspaceLifecycleError::new(
            "merge-finalize hold: checkout mode mismatch",
        ));
    }
    if request.checkout_mode == CheckoutMode::IndependentClone && is_linked_worktree(&clone, None) {
        return Err(WorkspaceLifecycleError::new(
            "merge-finalize hold: checkout mode mismatch",
        ));
    }
    if normalize_url(&run_git(&clone, &["config", "--get", "remote.origin.url"])?)
        != normalize_url(&request.url)
    {
        return Err(WorkspaceLifecycleError::new(
            "merge-finalize hold: remote identity mismatch",
        ));
    }
    let branch = run_git(&clone, &["symbolic-ref", "--quiet", "--short", "HEAD"])?
        .trim()
        .to_owned();
    if branch != request.branch {
        return Err(WorkspaceLifecycleError::new(format!(
            "merge-finalize hold: branch mismatch ({branch})"
        )));
    }
    let merge_head_result = Command::new("git")
        .arg("-C")
        .arg(&clone)
        .args(["rev-parse", "MERGE_HEAD"])
        .output()
        .map_err(|error| {
            WorkspaceLifecycleError::new(format!("git process unavailable: {error}"))
        })?;
    let merge_head_text = output_text(&merge_head_result);
    let merge_heads = merge_head_text
        .lines()
        .filter(|line| !line.is_empty())
        .collect::<Vec<_>>();
    if !merge_head_result.status.success() || merge_heads.len() != 1 {
        return Err(WorkspaceLifecycleError::new(
            "merge-finalize hold: expected one native MERGE_HEAD",
        ));
    }
    let origin_main_sha = merge_heads[0].to_owned();
    let candidate_sha = run_git(&clone, &["rev-parse", "HEAD"])?.trim().to_owned();
    let candidate_tree = run_git(&clone, &["rev-parse", &format!("{candidate_sha}^{{tree}}")])?
        .trim()
        .to_owned();
    let resolved_index_tree = run_git(&clone, &["write-tree"])?.trim().to_owned();
    run_git(&clone, &["commit", "--no-edit"])?;
    let merged_sha = run_git(&clone, &["rev-parse", "HEAD"])?.trim().to_owned();
    let merged_tree = run_git(&clone, &["rev-parse", &format!("{merged_sha}^{{tree}}")])?
        .trim()
        .to_owned();
    let parents = run_git(&clone, &["show", "-s", "--format=%P", &merged_sha])?
        .split_whitespace()
        .map(str::to_owned)
        .collect::<Vec<_>>();
    if parents != [candidate_sha.clone(), origin_main_sha.clone()] {
        return Err(WorkspaceLifecycleError::new(
            "merge-finalize hold: native merge parent readback mismatch",
        ));
    }
    if merged_tree != resolved_index_tree {
        return Err(WorkspaceLifecycleError::new(
            "merge-finalize hold: native merge tree readback mismatch",
        ));
    }
    Ok(MergeMainReceipt {
        request,
        clone,
        candidate_sha,
        candidate_tree,
        merged_sha,
        merged_tree,
        origin_main_sha,
    })
}

fn read_json(path: &Path, label: &str) -> LifecycleResult<Value> {
    let bytes = fs::read(path)
        .map_err(|error| WorkspaceLifecycleError::new(format!("{label} malformed: {error}")))?;
    serde_json::from_slice(&bytes)
        .map_err(|error| WorkspaceLifecycleError::new(format!("{label} malformed: {error}")))
}

fn json_string<'a>(value: &'a Value, key: &str) -> Option<&'a str> {
    value.get(key).and_then(Value::as_str)
}

pub fn verify_publication(
    request: &RepositoryTopicCloneRequest,
    candidate_cas: &Path,
    pr_lifecycle: &Path,
    publication_readback: Option<&Path>,
) -> LifecycleResult<Value> {
    let cas = read_json(candidate_cas, "candidate CAS receipt")?;
    let lifecycle = read_json(pr_lifecycle, "PR lifecycle receipt")?;
    let checked_lifecycle = update_lifecycle_contract::validate_candidate_cas_pr_transition(
        &cas, &lifecycle,
    )
    .map_err(|error| {
        WorkspaceLifecycleError::new(format!("publication lifecycle evidence invalid: {error}"))
    })?;
    let checked_readback = publication_readback
        .map(|path| {
            let readback = read_json(path, "publication readback receipt")?;
            update_lifecycle_contract::validate_publication_readback_transition(
                &cas, &lifecycle, &readback,
            )
            .map_err(|error| {
                WorkspaceLifecycleError::new(format!(
                    "publication lifecycle evidence invalid: {error}"
                ))
            })
        })
        .transpose()?;
    let state = json_string(&checked_lifecycle, "state");
    if !matches!(
        state,
        Some("draft" | "ready" | "changes_requested" | "external_review" | "merged")
    ) {
        return Err(WorkspaceLifecycleError::new(format!(
            "publication lifecycle state does not prove a PR head: {state:?}"
        )));
    }
    if state == Some("merged") && checked_readback.is_none() {
        return Err(WorkspaceLifecycleError::new(
            "publication lifecycle merged state requires publication readback",
        ));
    }
    if state != Some("merged") && checked_readback.is_some() {
        return Err(WorkspaceLifecycleError::new(
            "publication readback requires merged lifecycle state",
        ));
    }
    let expected_ref = format!("refs/heads/{}", request.branch);
    let remote = checked_lifecycle
        .get("remote_identity")
        .unwrap_or(&Value::Null);
    let base = checked_lifecycle
        .get("base_identity")
        .unwrap_or(&Value::Null);
    let head = checked_lifecycle
        .get("head_identity")
        .unwrap_or(&Value::Null);
    if json_string(remote, "remote_name") != Some("origin")
        || json_string(remote, "repo_name") != Some(request.repository.as_str())
        || json_string(remote, "ref") != Some(expected_ref.as_str())
        || json_string(head, "repo_name") != Some(request.repository.as_str())
        || json_string(head, "ref") != Some(expected_ref.as_str())
        || json_string(base, "ref") != Some("refs/heads/main")
    {
        return Err(WorkspaceLifecycleError::new(
            "publication lifecycle repository/branch identity mismatch",
        ));
    }
    Ok(serde_json::json!({
        "candidate_cas": cas,
        "pr_lifecycle": checked_lifecycle,
        "publication_readback": checked_readback,
    }))
}

fn require_clean_checkout(path: &Path) -> LifecycleResult<()> {
    let status = run_git(
        path,
        &[
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=none",
        ],
    )?;
    if !status.trim().is_empty() {
        return Err(WorkspaceLifecycleError::new(
            "cleanup hold: dirty-worktree-index-or-untracked",
        ));
    }
    Ok(())
}

fn remove_linked_worktree(
    request: &RepositoryTopicCloneRequest,
    clone: &Path,
    attested: &AttestedParent,
) -> LifecycleResult<()> {
    let receipt = attested_path(attested, clone, "repository-topic-clone-worktree-cleanup")?;
    if receipt.physical_path() != clone || !clone.is_dir() {
        return Err(WorkspaceLifecycleError::new(
            "cleanup hold: clone path identity changed",
        ));
    }
    if !receipt.target_is_directory() {
        return Err(WorkspaceLifecycleError::new(
            "cleanup hold: clone identity receipt is missing",
        ));
    }
    run_git_os(
        &request.workspace_root,
        &[
            OsString::from("worktree"),
            OsString::from("remove"),
            OsString::from("--force"),
            clone.as_os_str().to_os_string(),
        ],
    )?;
    match fs::symlink_metadata(clone) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        _ => {
            return Err(WorkspaceLifecycleError::new(
                "cleanup hold: linked worktree remains",
            ))
        }
    }
    let worktrees = run_git(
        &request.workspace_root,
        &["worktree", "list", "--porcelain", "-z"],
    )?;
    for entry in worktrees.split('\0') {
        if let Some(path) = entry.strip_prefix("worktree ") {
            let listed = path_resolution::resolve_non_strict(Path::new(path))
                .map_err(WorkspaceLifecycleError::new)?;
            if listed == clone {
                return Err(WorkspaceLifecycleError::new(
                    "cleanup hold: linked worktree remains registered",
                ));
            }
        }
    }
    Ok(())
}

pub fn cleanup(
    request: &RepositoryTopicCloneRequest,
    candidate_cas: Option<&Path>,
    pr_lifecycle: Option<&Path>,
    publication_readback: Option<&Path>,
    apply: bool,
) -> LifecycleResult<CleanupProof> {
    let has_evidence =
        candidate_cas.is_some() || pr_lifecycle.is_some() || publication_readback.is_some();
    if has_evidence && (candidate_cas.is_none() || pr_lifecycle.is_none()) {
        return Err(WorkspaceLifecycleError::new(
            "cleanup hold: candidate CAS and PR lifecycle evidence must be provided together",
        ));
    }
    let root = validate_workspace_root(&request.workspace_root, false)?;
    let mut request = request.clone();
    request.workspace_root = root;
    request.repository = repository_name(&request.repository)?;
    request.branch = normalize_branch(&request.branch, &request.workspace_root)?;
    let attested = attest_parent(&request.workspace_root, "repository-topic-clone-cleanup")?;
    let clone = computed_clone_path(&request, false, &attested)?;
    let inspection = inspect_clone(&clone, &request, true);
    if inspection.state != "ready" {
        return Err(WorkspaceLifecycleError::new(format!(
            "cleanup hold: {}",
            inspection.state
        )));
    }
    require_clean_checkout(&clone)?;
    let candidate_sha = run_git(&clone, &["rev-parse", "HEAD"])?.trim().to_owned();
    let candidate_tree = run_git(&clone, &["rev-parse", &format!("{candidate_sha}^{{tree}}")])?
        .trim()
        .to_owned();
    let evidence = if let (Some(cas), Some(lifecycle)) = (candidate_cas, pr_lifecycle) {
        let evidence = verify_publication(&request, cas, lifecycle, publication_readback)?;
        let head = evidence
            .get("pr_lifecycle")
            .and_then(|value| value.get("head_identity"))
            .ok_or_else(|| WorkspaceLifecycleError::new("publication head identity missing"))?;
        if json_string(head, "commit_sha") != Some(candidate_sha.as_str())
            || json_string(head, "tree_sha") != Some(candidate_tree.as_str())
        {
            return Err(WorkspaceLifecycleError::new(
                "cleanup hold: local candidate identity mismatch",
            ));
        }
        Some(evidence)
    } else {
        None
    };
    let evidence_kind = if publication_readback.is_none() {
        if request.checkout_mode == CheckoutMode::LinkedWorktree {
            "linked-superproject-head".to_owned()
        } else {
            run_git(&clone, &["fetch", "origin", &request.branch]).map_err(|_| {
                WorkspaceLifecycleError::new(format!(
                    "cleanup hold: remote branch unavailable ({})",
                    request.branch
                ))
            })?;
            let remote_head = run_git(
                &clone,
                &[
                    "rev-parse",
                    &format!("refs/remotes/origin/{}", request.branch),
                ],
            )?
            .trim()
            .to_owned();
            let remote_tree = run_git(&clone, &["rev-parse", &format!("{remote_head}^{{tree}}")])?
                .trim()
                .to_owned();
            if remote_head != candidate_sha || remote_tree != candidate_tree {
                return Err(WorkspaceLifecycleError::new(
                    "cleanup hold: remote branch head mismatch",
                ));
            }
            if has_evidence {
                "publication-head".to_owned()
            } else {
                "remote-head".to_owned()
            }
        }
    } else {
        run_git(&clone, &["fetch", "origin", "main"])?;
        let origin_main = run_git(&clone, &["rev-parse", "origin/main"])?
            .trim()
            .to_owned();
        let readback = evidence
            .as_ref()
            .and_then(|value| value.get("publication_readback"))
            .and_then(Value::as_object)
            .ok_or_else(|| {
                WorkspaceLifecycleError::new(
                    "cleanup hold: integrated publication evidence is missing",
                )
            })?;
        let pr = readback
            .get("pr_identity")
            .and_then(Value::as_object)
            .ok_or_else(|| {
                WorkspaceLifecycleError::new("cleanup hold: publication PR identity is missing")
            })?;
        let merge_sha = pr
            .get("merge_commit_sha")
            .and_then(Value::as_str)
            .map(str::to_owned)
            .ok_or_else(|| {
                WorkspaceLifecycleError::new("cleanup hold: merge commit identity is missing")
            })?;
        let merge_tree = pr
            .get("merge_tree_sha")
            .and_then(Value::as_str)
            .map(str::to_owned)
            .ok_or_else(|| {
                WorkspaceLifecycleError::new("cleanup hold: merge tree identity is missing")
            })?;
        let observed_tree = run_git(&clone, &["rev-parse", &format!("{merge_sha}^{{tree}}")])?
            .trim()
            .to_owned();
        if observed_tree != merge_tree {
            return Err(WorkspaceLifecycleError::new(
                "cleanup hold: merged tree mismatch",
            ));
        }
        run_git(
            &clone,
            &["merge-base", "--is-ancestor", &merge_sha, &origin_main],
        )?;
        let post_merge_base = pr
            .get("post_merge_base_ref_sha")
            .and_then(Value::as_str)
            .map(str::to_owned)
            .ok_or_else(|| {
                WorkspaceLifecycleError::new("cleanup hold: post-merge base identity is missing")
            })?;
        run_git(
            &clone,
            &[
                "merge-base",
                "--is-ancestor",
                &post_merge_base,
                &origin_main,
            ],
        )?;
        "integrated-publication".to_owned()
    };
    if !apply {
        return Ok(CleanupProof {
            request,
            clone,
            removed: false,
            evidence: evidence_kind,
        });
    }
    if request.checkout_mode == CheckoutMode::LinkedWorktree {
        remove_linked_worktree(&request, &clone, &attested)?;
    } else {
        let receipt = attested_path(&attested, &clone, "repository-topic-clone-cleanup")?;
        if receipt.physical_path() != clone {
            return Err(WorkspaceLifecycleError::new(
                "cleanup hold: clone path identity changed",
            ));
        }
        attested
            .remove_parent_owned_tree(&receipt)
            .map_err(authority_error)?;
    }
    let topic = clone
        .parent()
        .ok_or_else(|| WorkspaceLifecycleError::new("cleanup hold: topic root is missing"))?;
    if topic.exists() {
        let receipt = attested_path(&attested, topic, "repository-topic-workspace-cleanup")?;
        let _ = attested
            .remove_empty_parent_owned_directory(&receipt)
            .map_err(authority_error)?;
    }
    Ok(CleanupProof {
        request,
        clone,
        removed: true,
        evidence: evidence_kind,
    })
}

#[derive(Default)]
struct ParsedOptions {
    values: std::collections::BTreeMap<String, String>,
    flags: std::collections::BTreeSet<String>,
}

fn parse_options(
    args: &[String],
    allowed_values: &[&str],
    allowed_flags: &[&str],
) -> LifecycleResult<ParsedOptions> {
    let mut parsed = ParsedOptions::default();
    let mut index = 0;
    while index < args.len() {
        let argument = args[index].as_str();
        if argument == "--help" || argument == "-h" {
            parsed.flags.insert("--help".to_owned());
            index += 1;
            continue;
        }
        let (option, inline_value) = argument
            .split_once('=')
            .map_or((argument, None), |(name, value)| (name, Some(value)));
        if !option.starts_with("--") {
            return Err(WorkspaceLifecycleError::new(format!(
                "unrecognized argument: {argument}"
            )));
        }
        let all = allowed_values
            .iter()
            .map(|value| (*value, true))
            .chain(allowed_flags.iter().map(|flag| (*flag, false)))
            .collect::<Vec<_>>();
        let resolved = crate::python_cli_options::resolve_long_option_prefix(
            option,
            &all.iter()
                .map(|(name, _)| (*name, *name))
                .collect::<Vec<_>>(),
        )
        .map_err(|error| match error {
            crate::python_cli_options::LongOptionError::Unrecognized => {
                WorkspaceLifecycleError::new(format!("unrecognized argument: {option}"))
            }
            crate::python_cli_options::LongOptionError::Ambiguous(matches) => {
                WorkspaceLifecycleError::new(format!(
                    "ambiguous option: {option} could match {}",
                    matches.join(", ")
                ))
            }
        })?;
        let takes_value = all
            .iter()
            .find(|(name, _)| *name == resolved)
            .is_some_and(|(_, value)| *value);
        if takes_value {
            let value = if let Some(value) = inline_value {
                value.to_owned()
            } else {
                index += 1;
                args.get(index)
                    .filter(|value| !value.starts_with('-'))
                    .cloned()
                    .ok_or_else(|| {
                        WorkspaceLifecycleError::new(format!(
                            "argument {resolved}: expected one argument"
                        ))
                    })?
            };
            parsed.values.insert(resolved.to_owned(), value);
        } else {
            if inline_value.is_some() {
                return Err(WorkspaceLifecycleError::new(format!(
                    "argument {resolved}: does not take a value"
                )));
            }
            parsed.flags.insert(resolved.to_owned());
        }
        index += 1;
    }
    Ok(parsed)
}

fn required(options: &ParsedOptions, name: &str) -> LifecycleResult<String> {
    options.values.get(name).cloned().ok_or_else(|| {
        WorkspaceLifecycleError::new(format!("the following arguments are required: {name}"))
    })
}

fn request_from_options(options: &ParsedOptions) -> LifecycleResult<RepositoryTopicCloneRequest> {
    let root = PathBuf::from(required(options, "--workspace-root")?);
    let mode = CheckoutMode::parse(&required(options, "--checkout-mode")?)?;
    Ok(RepositoryTopicCloneRequest {
        url: required(options, "--url")?,
        repository: required(options, "--repo-name")?,
        workspace_root: root,
        topic: required(options, "--topic")?,
        branch: required(options, "--branch")?,
        checkout_mode: mode,
    })
}

fn lifecycle_options(command: &str) -> (&'static [&'static str], &'static [&'static str]) {
    const COMMON: &[&str] = &[
        "--url",
        "--repo-name",
        "--workspace-root",
        "--topic",
        "--branch",
        "--checkout-mode",
    ];
    const CLEANUP_VALUES: &[&str] = &[
        "--url",
        "--repo-name",
        "--workspace-root",
        "--topic",
        "--branch",
        "--checkout-mode",
        "--candidate-cas",
        "--pr-lifecycle",
        "--publication-readback",
    ];
    const VERIFY_VALUES: &[&str] = &[
        "--url",
        "--repo-name",
        "--workspace-root",
        "--topic",
        "--branch",
        "--checkout-mode",
        "--candidate-cas",
        "--pr-lifecycle",
        "--publication-readback",
    ];
    const APPLY: &[&str] = &["--apply"];
    const NONE: &[&str] = &[];
    match command {
        "prepare" | "merge-main" | "finalize-merge" => (COMMON, NONE),
        "cleanup" => (CLEANUP_VALUES, APPLY),
        "verify-publication" => (VERIFY_VALUES, NONE),
        _ => (NONE, NONE),
    }
}

fn print_prepare(receipt: &PrepareReceipt) {
    println!("REQUEST_STATE=ready");
    println!("REQUEST_REPO={}", receipt.request.repository);
    println!(
        "REQUEST_TOPIC={}",
        topic_slug(&receipt.request.topic).unwrap_or_default()
    );
    println!("REQUEST_BRANCH={}", receipt.branch);
    println!("REQUEST_CLONE={}", receipt.clone.display());
    println!("REQUEST_CANDIDATE_SHA={}", receipt.candidate_sha);
    println!("REQUEST_CANDIDATE_TREE={}", receipt.candidate_tree);
    if run_git(
        &receipt.clone,
        &[
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=none",
        ],
    )
    .is_ok_and(|status| !status.trim().is_empty())
    {
        println!("REQUEST_CHECKOUT_STATUS=dirty-preserved");
    }
}

fn print_merge(receipt: &MergeMainReceipt, finalized: bool) {
    println!(
        "MERGE_STATUS={}",
        if finalized { "finalized" } else { "done" }
    );
    println!("MERGE_CLONE={}", receipt.clone.display());
    println!("MERGE_CANDIDATE_SHA={}", receipt.candidate_sha);
    println!("MERGE_CANDIDATE_TREE={}", receipt.candidate_tree);
    println!("MERGE_INTEGRATED_SHA={}", receipt.merged_sha);
    println!("MERGE_INTEGRATED_TREE={}", receipt.merged_tree);
    println!("MERGE_ORIGIN_MAIN_SHA={}", receipt.origin_main_sha);
}

fn print_help() {
    println!("{USAGE}");
    println!("  prepare --url URL --repo-name NAME --workspace-root ROOT --topic TOPIC --branch BRANCH --checkout-mode linked-worktree|independent-clone");
    println!("  merge-main --url URL --repo-name NAME --workspace-root ROOT --topic TOPIC --branch BRANCH --checkout-mode linked-worktree|independent-clone");
    println!("  finalize-merge --url URL --repo-name NAME --workspace-root ROOT --topic TOPIC --branch BRANCH --checkout-mode linked-worktree|independent-clone");
    println!("  verify-publication <common identity> --candidate-cas PATH --pr-lifecycle PATH [--publication-readback PATH]");
    println!("  cleanup <common identity> [--candidate-cas PATH --pr-lifecycle PATH [--publication-readback PATH]] [--apply]");
}

pub fn run(args: &[String]) -> i32 {
    if args.is_empty() || args[0] == "--help" || args[0] == "-h" {
        print_help();
        return 0;
    }
    let command = args[0].as_str();
    let (value_options, flag_options) = lifecycle_options(command);
    if value_options.is_empty() {
        eprintln!("REPOSITORY_TOPIC_CLONE_ERROR=invalid command: {command}");
        return 2;
    }
    let options = match parse_options(&args[1..], value_options, flag_options) {
        Ok(options) => options,
        Err(error) => {
            eprintln!("{USAGE}");
            eprintln!("error: {error}");
            return 2;
        }
    };
    if options.flags.contains("--help") {
        print_help();
        return 0;
    }
    let request = match request_from_options(&options) {
        Ok(request) => request,
        Err(error) => {
            eprintln!("{USAGE}");
            eprintln!("error: {error}");
            return 2;
        }
    };
    let result = (|| -> LifecycleResult<()> {
        match command {
            "prepare" => print_prepare(&prepare(&request)?),
            "merge-main" => print_merge(&merge_main(&request)?, false),
            "finalize-merge" => print_merge(&finalize_merge_main(&request)?, true),
            "verify-publication" => {
                let evidence = verify_publication(
                    &request,
                    Path::new(&required(&options, "--candidate-cas")?),
                    Path::new(&required(&options, "--pr-lifecycle")?),
                    options.values.get("--publication-readback").map(Path::new),
                )?;
                println!("PUBLICATION=pass");
                println!(
                    "PUBLICATION_STATE={}",
                    evidence["pr_lifecycle"]["state"].as_str().unwrap_or("")
                );
            }
            "cleanup" => {
                let proof = cleanup(
                    &request,
                    options.values.get("--candidate-cas").map(Path::new),
                    options.values.get("--pr-lifecycle").map(Path::new),
                    options.values.get("--publication-readback").map(Path::new),
                    options.flags.contains("--apply"),
                )?;
                let action = if proof.removed {
                    "removed"
                } else {
                    "would-remove"
                };
                println!("CLEANUP={}:{}", proof.clone.display(), action);
            }
            _ => unreachable!("command was validated above"),
        }
        Ok(())
    })();
    match result {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("REPOSITORY_TOPIC_CLONE_ERROR={error}");
            1
        }
    }
}
