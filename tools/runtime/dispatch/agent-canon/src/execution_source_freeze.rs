// @dependency-start
// contract implementation
// responsibility Captures source membership and immutable snapshot bytes through retained no-follow filesystem handles.
// upstream implementation execution_resource_plan.rs owns source-freeze request and evidence records
// upstream implementation source_mutation.rs owns no-follow relative parent traversal
// upstream implementation runtime_boundary.rs owns anonymous create-once publication
// downstream implementation managed_experiment.rs retains the freeze until managed execution releases it
// @dependency-end

#[cfg(target_os = "linux")]
mod linux {
    use crate::execution_resource_plan::{
        canonical_fingerprint, AbsolutePosixPath, Failure, GpuRunRequest, SourceFileRecord,
        SourceFreezeReceipt, SourceSnapshotManifest, SourceSnapshotRecord,
    };
    use crate::runtime_boundary::RuntimeDirectory;
    use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
    use cap_std::fs::MetadataExt as CapMetadataExt;
    use serde_json::json;
    use sha2::{Digest, Sha256};
    use std::collections::BTreeSet;
    use std::os::fd::AsRawFd;
    use std::os::unix::fs::{FileExt, MetadataExt};
    use std::path::{Path, PathBuf};
    use std::process::Command;
    type Result<T> = std::result::Result<T, Failure>;
    pub fn source_path_set(root: &Path, topic: &str, command: &[String]) -> Result<Vec<String>> {
        if topic.is_empty() || topic.contains(['/', '\\']) {
            return Err(Failure::new(
                "gpu_source_path_topic_invalid",
                "source path selection requires one simple topic name",
            ));
        }
        if !root.join("experiments/registry.toml").is_file() {
            return Err(Failure::new(
                "gpu_source_path_registry_missing",
                "canonical experiments/registry.toml source edge is missing",
            ));
        }
        let pattern = format!("experiments/{topic}/**");
        let listed = crate::git_read::output(
            root,
            &[
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                &pattern,
            ],
            std::time::Duration::from_secs(10),
        )
        .map_err(|error| Failure::new("gpu_source_path_membership_failed", error))?
        .ok_or_else(|| {
            Failure::new(
                "gpu_source_path_membership_failed",
                "git source membership command failed",
            )
        })?;
        let mut paths = vec!["experiments/registry.toml".to_owned()];
        for path in listed.split('\0').filter(|path| !path.is_empty()) {
            if Path::new(path).components().any(|part| {
                ["result", ".venv", "__pycache__", ".cache", "runtime"]
                    .iter()
                    .any(|name| part.as_os_str() == *name)
            }) {
                continue;
            }
            if std::fs::symlink_metadata(root.join(path))
                .is_ok_and(|metadata| metadata.is_symlink())
            {
                return Err(Failure::new(
                    "gpu_source_path_symlink",
                    "source membership cannot include a symlink",
                ));
            }
            paths.push(path.into());
        }
        for token in command.iter().filter(|token| !token.starts_with('-')) {
            let path = Path::new(token);
            let relative = if path.is_absolute() {
                let Ok(relative) = path.strip_prefix(root) else {
                    continue;
                };
                relative
            } else {
                path
            };
            if relative
                .components()
                .any(|part| !matches!(part, std::path::Component::Normal(_)))
            {
                continue;
            }
            if ![
                Some("py"),
                Some("pyi"),
                Some("toml"),
                Some("yaml"),
                Some("yml"),
                Some("json"),
            ]
            .contains(&relative.extension().and_then(|value| value.to_str()))
            {
                continue;
            }
            if root.join(relative).is_file() {
                paths.push(relative.to_string_lossy().into_owned());
            }
        }
        let mut seen = BTreeSet::new();
        paths.retain(|path| seen.insert(path.clone()));
        Ok(paths)
    }
    pub struct SourceFreezeOwner {
        result: AbsolutePosixPath,
        source_path: Option<AbsolutePosixPath>,
        root: Option<cap_std::fs::Dir>,
        root_identity: Option<(u64, u64)>,
        files: Vec<std::fs::File>,
        closed: bool,
        frozen: bool,
    }
    impl SourceFreezeOwner {
        pub fn new(result: AbsolutePosixPath) -> Self {
            Self {
                result,
                source_path: None,
                root: None,
                root_identity: None,
                files: Vec::new(),
                closed: false,
                frozen: false,
            }
        }
        pub fn freeze(&mut self, request: &GpuRunRequest) -> Result<SourceFreezeReceipt> {
            if self.closed {
                return Err(Failure::new(
                    "gpu_source_freeze_closed",
                    "a closed source-freeze owner cannot be reused",
                ));
            }
            if self.frozen {
                return Err(Failure::new(
                    "gpu_source_freeze_repeated",
                    "a source-freeze owner accepts exactly one freeze operation",
                ));
            }
            let result = self.freeze_once(request);
            if let Err(mut error) = result {
                if let Err(cleanup) = self.close_owned() {
                    error
                        .details
                        .insert("cleanup_failure".into(), json!(cleanup.message));
                }
                return Err(error);
            }
            result
        }
        fn freeze_once(&mut self, request: &GpuRunRequest) -> Result<SourceFreezeReceipt> {
            if !["MANAGED_CONTAINER", "HOST_DIRECT"].contains(&request.runtime_route.as_str()) {
                return Err(Failure::new(
                    "gpu_source_freeze_route_invalid",
                    "source freeze runtime route is unsupported",
                ));
            }
            let mut membership = BTreeSet::new();
            for path in &request.source_paths {
                if path.is_empty()
                    || path.starts_with('/')
                    || path.contains('\0')
                    || path.split('/').any(|part| ["", ".", ".."].contains(&part))
                {
                    return Err(Failure::new(
                        "gpu_source_freeze_path_invalid",
                        "source paths must be relative, normalized POSIX paths",
                    ));
                }
                if !membership.insert(path.clone()) {
                    return Err(Failure::new(
                        "gpu_source_freeze_path_duplicate",
                        "source paths must be unique",
                    ));
                }
            }
            self.source_path = Some(AbsolutePosixPath::parse(
                &request.source_root.path().to_string_lossy(),
            )?);
            let root = crate::source_mutation::open_root_nofollow(request.source_root.path())
                .map_err(|error| {
                    Failure::new("gpu_source_freeze_root_invalid", error.to_string())
                })?;
            let metadata = root.dir_metadata().map_err(|error| {
                Failure::new("gpu_source_freeze_root_invalid", error.to_string())
            })?;
            let (device, inode) = (metadata.dev(), metadata.ino());
            self.root_identity = Some((device, inode));
            self.root = Some(root);
            let root = self.root.as_ref().expect("retained source handle");
            let git_root = PathBuf::from(format!(
                "/proc/{}/fd/{}",
                std::process::id(),
                root.as_raw_fd()
            ));
            let git = |args: &[&str]| -> Result<String> {
                let output = Command::new("git")
                    .arg("-C")
                    .arg(&git_root)
                    .args(args)
                    .output()
                    .map_err(|error| {
                        Failure::new("gpu_source_freeze_git_identity_failed", error.to_string())
                    })?;
                if !output.status.success() {
                    return Err(Failure::new(
                        "gpu_source_freeze_git_identity_failed",
                        String::from_utf8_lossy(&output.stderr).trim().to_owned(),
                    ));
                }
                String::from_utf8(output.stdout)
                    .map(|text| text.trim().to_owned())
                    .map_err(|error| {
                        Failure::new("gpu_source_freeze_git_identity_failed", error.to_string())
                    })
            };
            let source_commit = git(&["rev-parse", "HEAD"])?;
            let source_tree = git(&["rev-parse", "HEAD^{tree}"])?;
            if source_commit.len() != 40 || source_tree.len() != 40 {
                return Err(Failure::new(
                    "gpu_source_freeze_git_identity_invalid",
                    "Git source identity must contain exact commit and tree hashes",
                ));
            }
            let result_root = crate::source_mutation::open_root_nofollow(self.result.path())
                .map_err(|error| {
                    Failure::new("gpu_source_snapshot_open_failed", error.to_string())
                })?;
            let (snapshot_root, _) = crate::source_mutation::file_parent_from_root(
                &result_root,
                Path::new("source_snapshot/.membership"),
                Some(0o770),
            )
            .map_err(|error| Failure::new("gpu_source_snapshot_open_failed", error.to_string()))?;
            let mut records = Vec::new();
            let mut files = Vec::new();
            for path in &membership {
                let (parent, name) =
                    crate::source_mutation::file_parent_from_root(root, Path::new(path), None)
                        .map_err(|error| {
                            Failure::new("gpu_source_freeze_path_invalid", error.to_string())
                        })?;
                let mut options = cap_std::fs::OpenOptions::new();
                options.read(true).follow(FollowSymlinks::No);
                let source = parent
                    .open_with(&name, &options)
                    .map_err(|error| {
                        Failure::new("gpu_source_freeze_open_failed", error.to_string())
                    })?
                    .into_std();
                let before = source.metadata().map_err(|error| {
                    Failure::new("gpu_source_freeze_open_failed", error.to_string())
                })?;
                if !before.is_file() {
                    return Err(Failure::new(
                        "gpu_source_freeze_non_regular",
                        "source freeze accepts regular files only",
                    ));
                }
                let bytes = read_all_at(&source)?;
                let after = source
                    .metadata()
                    .map_err(|error| Failure::new("gpu_source_freeze_raced", error.to_string()))?;
                if changed(&before, &after, bytes.len()) {
                    return Err(Failure::new(
                        "gpu_source_freeze_raced",
                        "source identity changed during fd-bound read",
                    ));
                }
                let hash = format!("{:x}", Sha256::digest(&bytes));
                let source_kind = match git(&["ls-files", "--error-unmatch", "--", path]) {
                    Ok(value) if !value.is_empty() => {
                        if git(&[
                            "status",
                            "--porcelain=v1",
                            "--untracked-files=all",
                            "--",
                            path,
                        ])?
                        .is_empty()
                        {
                            "tracked"
                        } else {
                            "dirty"
                        }
                    }
                    _ => {
                        if git(&["ls-files", "--others", "--exclude-standard", "--", path])?
                            .is_empty()
                        {
                            return Err(Failure::new(
                                "gpu_source_freeze_unlisted_path",
                                "source path is neither tracked nor non-ignored untracked content",
                            ));
                        }
                        "untracked"
                    }
                };
                let snapshot_relative = format!("source_snapshot/{path}");
                crate::source_mutation::file_parent_from_root(
                    &result_root,
                    Path::new(&snapshot_relative),
                    Some(0o770),
                )
                .map_err(|error| {
                    Failure::new("gpu_source_snapshot_open_failed", error.to_string())
                })?;
                let result = RuntimeDirectory::open_nofollow(self.result.path(), false).map_err(
                    |error| Failure::new("gpu_source_snapshot_open_failed", error.to_string()),
                )?;
                let snapshot = result
                    .publish_anonymous_once(Path::new(&snapshot_relative), &bytes, 0o660)
                    .map_err(snapshot_failure)?;
                let snapshot_metadata = snapshot.metadata().map_err(|error| {
                    Failure::new("gpu_source_snapshot_invalid", error.to_string())
                })?;
                let copied = read_all_at(&snapshot)?;
                let copied_hash = format!("{:x}", Sha256::digest(&copied));
                if copied != bytes {
                    return Err(Failure::new(
                        "gpu_source_snapshot_mismatch",
                        "snapshot bytes do not match retained source fd",
                    ));
                }
                records.push(SourceSnapshotRecord {
                    relative_path: path.clone(),
                    source_dev: before.dev(),
                    source_ino: before.ino(),
                    source_byte_count: bytes.len() as u64,
                    source_sha256: hash.clone(),
                    snapshot_relative_path: snapshot_relative,
                    snapshot_dev: snapshot_metadata.dev(),
                    snapshot_ino: snapshot_metadata.ino(),
                    snapshot_byte_count: copied.len() as u64,
                    snapshot_sha256: copied_hash,
                });
                files.push(SourceFileRecord {
                    relative_path: path.clone(),
                    source_kind: source_kind.into(),
                    st_dev: before.dev(),
                    st_ino: before.ino(),
                    st_mode: before.mode(),
                    st_size: before.len(),
                    st_mtime_ns: i128::from(before.mtime()) * 1_000_000_000
                        + i128::from(before.mtime_nsec()),
                    st_ctime_ns: i128::from(before.ctime()) * 1_000_000_000
                        + i128::from(before.ctime_nsec()),
                    sha256: hash,
                    byte_count: bytes.len() as u64,
                });
                self.files.push(source);
            }
            let payload = json!({"schema_version":"source-snapshot/v2","source_root_dev":device,"source_root_ino":inode,"source_commit":source_commit,"source_tree":source_tree,"records":records});
            let manifest_fingerprint = canonical_fingerprint(&payload)?;
            let manifest = SourceSnapshotManifest {
                schema_version: "source-snapshot/v2".into(),
                source_root_dev: device,
                source_root_ino: inode,
                source_commit: source_commit.clone(),
                source_tree: source_tree.clone(),
                records,
                manifest_fingerprint: manifest_fingerprint.clone(),
            };
            let payload = serde_json::to_value(&manifest)
                .map_err(|error| Failure::new("gpu_source_snapshot_invalid", error.to_string()))?;
            let value = crate::python_json::parse_json(&payload.to_string())
                .map_err(|error| Failure::new("gpu_source_snapshot_invalid", error))?;
            let mut bytes = crate::python_json::canonical_json_ascii_bytes(&value)
                .map_err(|error| Failure::new("gpu_source_snapshot_invalid", error))?;
            bytes.push(b'\n');
            let result =
                RuntimeDirectory::open_nofollow(self.result.path(), false).map_err(|error| {
                    Failure::new("gpu_source_snapshot_open_failed", error.to_string())
                })?;
            result
                .publish_anonymous_once(Path::new("source_snapshot.json"), &bytes, 0o660)
                .map_err(snapshot_failure)?;
            let sync = snapshot_root
                .open_with(".", cap_std::fs::OpenOptions::new().read(true))
                .map_err(|error| {
                    Failure::new("gpu_source_snapshot_open_failed", error.to_string())
                })?;
            sync.sync_all().map_err(|error| {
                Failure::new("gpu_source_snapshot_open_failed", error.to_string())
            })?;
            let mut receipt = SourceFreezeReceipt {
                schema_version: "source-freeze/v2".into(),
                runtime_route: request.runtime_route.clone(),
                source_root_path: request.source_root.clone(),
                source_root_dev: device,
                source_root_ino: inode,
                source_commit,
                source_tree,
                files,
                source_paths: membership.into_iter().collect(),
                snapshot_root_relative_path: "source_snapshot".into(),
                snapshot_relative_path: "source_snapshot.json".into(),
                snapshot_manifest_fingerprint: manifest_fingerprint,
                receipt_fingerprint: String::new(),
            };
            let mut payload = serde_json::to_value(&receipt)
                .map_err(|error| Failure::new("gpu_source_snapshot_invalid", error.to_string()))?;
            payload
                .as_object_mut()
                .expect("receipt object")
                .remove("receipt_fingerprint");
            receipt.receipt_fingerprint = canonical_fingerprint(&payload)?;
            self.frozen = true;
            Ok(receipt)
        }
        pub fn revalidate(&self) -> Result<()> {
            if self.closed {
                return Err(Failure::new(
                    "gpu_source_freeze_closed",
                    "a closed source-freeze owner cannot be revalidated",
                ));
            }
            let path = self.source_path.as_ref().ok_or_else(|| {
                Failure::new(
                    "gpu_source_freeze_not_started",
                    "source root is not retained for revalidation",
                )
            })?;
            let root = crate::source_mutation::open_root_nofollow(path.path())
                .map_err(|error| Failure::new("gpu_source_freeze_raced", error.to_string()))?;
            let metadata = root
                .dir_metadata()
                .map_err(|error| Failure::new("gpu_source_freeze_raced", error.to_string()))?;
            if self.root_identity != Some((metadata.dev(), metadata.ino())) {
                return Err(Failure::new(
                    "gpu_source_freeze_raced",
                    "source-root identity changed before release",
                ));
            }
            Ok(())
        }
        pub fn close(&mut self) -> Result<()> {
            if self.closed {
                return Err(Failure::new(
                    "gpu_descriptor_double_close",
                    "source-freeze descriptors were closed more than once",
                ));
            }
            let identity = self.revalidate();
            let closed = self.close_owned();
            identity.and(closed)
        }
        fn close_owned(&mut self) -> Result<()> {
            let mut failure = None;
            for file in self.files.drain(..).rev() {
                if let Err(error) = nix::unistd::close(file) {
                    failure.get_or_insert_with(|| {
                        Failure::new("gpu_descriptor_close_ambiguous", error.to_string())
                    });
                }
            }
            if let Some(root) = self.root.take() {
                if let Err(error) = nix::unistd::close(root.into_std_file()) {
                    failure.get_or_insert_with(|| {
                        Failure::new("gpu_descriptor_close_ambiguous", error.to_string())
                    });
                }
            }
            self.closed = true;
            match failure {
                Some(error) => Err(error),
                None => Ok(()),
            }
        }
    }
    fn snapshot_failure(error: std::io::Error) -> Failure {
        let code = if [Some(nix::libc::EINVAL), Some(nix::libc::EOPNOTSUPP)]
            .contains(&error.raw_os_error())
        {
            "gpu_source_snapshot_unsupported"
        } else {
            "gpu_source_snapshot_open_failed"
        };
        Failure::new(code, error.to_string())
    }
    fn read_all_at(file: &std::fs::File) -> Result<Vec<u8>> {
        let metadata = file
            .metadata()
            .map_err(|error| Failure::new("gpu_source_freeze_open_failed", error.to_string()))?;
        let size = usize::try_from(metadata.len())
            .map_err(|error| Failure::new("gpu_source_freeze_open_failed", error.to_string()))?;
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(size)
            .map_err(|error| Failure::new("gpu_source_freeze_open_failed", error.to_string()))?;
        bytes.resize(size, 0);
        let mut offset = 0;
        while offset < size {
            let count = file
                .read_at(&mut bytes[offset..], offset as u64)
                .map_err(|error| {
                    Failure::new("gpu_source_freeze_open_failed", error.to_string())
                })?;
            if count == 0 {
                return Err(Failure::new(
                    "gpu_source_freeze_raced",
                    "source ended before observed byte count",
                ));
            }
            offset += count;
        }
        Ok(bytes)
    }
    fn changed(before: &std::fs::Metadata, after: &std::fs::Metadata, count: usize) -> bool {
        before.dev() != after.dev()
            || before.ino() != after.ino()
            || before.mode() != after.mode()
            || before.len() != after.len()
            || after.len() != count as u64
            || before.mtime() != after.mtime()
            || before.mtime_nsec() != after.mtime_nsec()
            || before.ctime() != after.ctime()
            || before.ctime_nsec() != after.ctime_nsec()
    }
}
#[cfg(target_os = "linux")]
pub use linux::{source_path_set, SourceFreezeOwner};
