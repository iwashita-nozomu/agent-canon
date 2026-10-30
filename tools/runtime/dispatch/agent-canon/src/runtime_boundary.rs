//! Common filesystem boundary checks for analysis runtime artifacts.
//!
//! Analysis reads the selected source tree, but all databases, snapshots,
//! temporary files, and reports belong to an explicitly external runtime
//! root.  Keeping this policy in one module prevents individual tools from
//! accidentally recreating the old `.agent-canon` source-tree cache.

use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};

pub const RUNTIME_ROOT_ENV: &str = "AGENT_CANON_RUNTIME_ROOT";

// Win32 FILE_FLAG_BACKUP_SEMANTICS, required when opening a directory handle.
#[cfg(windows)]
const WINDOWS_FILE_FLAG_BACKUP_SEMANTICS: u32 = 0x0200_0000;

fn current_home_directory() -> Result<PathBuf, String> {
    #[cfg(windows)]
    let home = env::var_os("USERPROFILE").or_else(|| {
        let mut drive = env::var_os("HOMEDRIVE").unwrap_or_default();
        drive.push(env::var_os("HOMEPATH")?);
        Some(drive)
    });
    #[cfg(not(windows))]
    let home = env::var_os("HOME");
    home.map(PathBuf::from)
        .filter(|home| home.is_absolute())
        .ok_or_else(|| "home directory unavailable for explicit ~ path".to_string())
}

/// Expand only the current-user `~` form; named-user lookup is deliberately unsupported.
fn expand_user_path(path: &Path) -> Result<PathBuf, String> {
    let Some(value) = path.to_str() else {
        return Ok(path.to_path_buf());
    };
    let suffix = if value == "~" {
        Some("")
    } else if let Some(suffix) = value.strip_prefix("~/") {
        Some(suffix)
    } else if cfg!(windows) {
        value.strip_prefix("~\\")
    } else {
        None
    };
    if suffix.is_none() && value.starts_with('~') {
        return Err("named-user home expansion is unsupported".to_string());
    }
    match suffix {
        Some(suffix) => Ok(current_home_directory()?.join(suffix.trim_start_matches(['/', '\\']))),
        None => Ok(path.to_path_buf()),
    }
}

pub fn runtime_root_is_explicit() -> bool {
    env::var_os(RUNTIME_ROOT_ENV).is_some_and(|value| !value.is_empty())
}

#[doc(hidden)]
pub fn test_runtime_root_path(source_root: &Path) -> Result<PathBuf, String> {
    let source_root = expand_user_path(source_root)?;
    let source = fs::canonicalize(&source_root).map_err(|error| {
        format!(
            "canonicalize source root {}: {error}",
            source_root.display()
        )
    })?;
    test_runtime_root_for_source(&source)
}

fn test_runtime_root_for_source(source: &Path) -> Result<PathBuf, String> {
    let digest = Sha256::digest(source.to_string_lossy().as_bytes());
    let key = digest[..8]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let temporary = fs::canonicalize(env::temp_dir())
        .map_err(|error| format!("canonicalize test temporary root: {error}"))?;
    Ok(temporary.join(format!("agent-canon-test-runtime-{key}")))
}

fn absolute(path: &Path) -> Result<PathBuf, String> {
    let path = expand_user_path(path)?;
    if path.is_absolute() {
        Ok(path)
    } else {
        env::current_dir()
            .map(|cwd| cwd.join(&path))
            .map_err(|error| format!("resolve {}: {error}", path.display()))
    }
}

fn canonical_existing_parent(path: &Path) -> Result<PathBuf, String> {
    let mut cursor = path.to_path_buf();
    while !cursor.exists() {
        cursor = cursor
            .parent()
            .ok_or_else(|| format!("no existing parent for {}", path.display()))?
            .to_path_buf();
    }
    fs::canonicalize(&cursor).map_err(|error| format!("canonicalize {}: {error}", cursor.display()))
}

fn canonicalize_with_missing_suffix(path: &Path) -> Result<PathBuf, String> {
    let mut cursor = path.to_path_buf();
    let mut missing = Vec::new();
    loop {
        match fs::canonicalize(&cursor) {
            Ok(mut canonical) => {
                for component in missing.iter().rev() {
                    canonical.push(component);
                }
                return Ok(canonical);
            }
            Err(error)
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::NotFound | std::io::ErrorKind::NotADirectory
                ) =>
            {
                let name = cursor
                    .file_name()
                    .ok_or_else(|| format!("cannot resolve runtime path {}", path.display()))?;
                missing.push(name.to_os_string());
                cursor = cursor
                    .parent()
                    .ok_or_else(|| format!("cannot resolve runtime path {}", path.display()))?
                    .to_path_buf();
            }
            Err(error) => {
                return Err(format!(
                    "cannot resolve runtime path {}: {error}",
                    path.display()
                ))
            }
        }
    }
}

/// Resolve the process/task runtime root and prove that it is not the source.
///
/// Production callers must provide `AGENT_CANON_RUNTIME_ROOT`.  Unit tests
/// use a deterministic temporary root so that existing pure Rust fixtures can
/// continue to exercise the public command semantics without writing source.
pub fn resolve_runtime_root(source_root: &Path) -> Result<PathBuf, String> {
    #[cfg(test)]
    {
        // Unit tests use their deterministic fixture root, not the resident
        // container's inherited runtime root. Explicit test roots use the
        // resolve_runtime_root_at(..., Some(...)) API below.
        resolve_runtime_root_at(source_root, None)
    }
    #[cfg(not(test))]
    {
        let requested = env::var_os(RUNTIME_ROOT_ENV)
            .filter(|value| !value.is_empty())
            .map(PathBuf::from);
        resolve_runtime_root_at(source_root, requested.as_deref())
    }
}

pub fn resolve_runtime_root_at(
    source_root: &Path,
    requested: Option<&Path>,
) -> Result<PathBuf, String> {
    let source_root = expand_user_path(source_root)?;
    let source = fs::canonicalize(&source_root).map_err(|error| {
        format!(
            "canonicalize source root {}: {error}",
            source_root.display()
        )
    })?;
    // The explicit match keeps the test-only fallback lazy without creating a
    // non-test closure that Clippy correctly identifies as unnecessary.
    #[allow(clippy::manual_map)]
    let raw = match requested {
        Some(requested) => Some(requested.to_path_buf()),
        None => {
            #[cfg(test)]
            {
                Some(test_runtime_root_for_source(&source)?)
            }
            #[cfg(not(test))]
            {
                None
            }
        }
    }
    .ok_or_else(|| {
        format!(
            "{RUNTIME_ROOT_ENV} is required; analysis artifacts must use an external runtime root"
        )
    })?;
    let raw = absolute(&raw)?;
    let mut cursor = PathBuf::new();
    for component in raw.components() {
        cursor.push(component.as_os_str());
        if cursor.exists() {
            let metadata = fs::symlink_metadata(&cursor)
                .map_err(|error| format!("inspect runtime path {}: {error}", cursor.display()))?;
            if metadata.file_type().is_symlink() {
                return Err(format!(
                    "runtime root contains symlink component {}; choose an explicit physical path",
                    cursor.display()
                ));
            }
        }
    }
    let existing_parent = canonical_existing_parent(&raw)?;
    if existing_parent == source || existing_parent.starts_with(&source) {
        return Err(format!(
            "runtime root {} is inside source root {}; choose an external root",
            raw.display(),
            source.display()
        ));
    }
    fs::create_dir_all(&raw)
        .map_err(|error| format!("create runtime root {}: {error}", raw.display()))?;
    let runtime = fs::canonicalize(&raw)
        .map_err(|error| format!("canonicalize runtime root {}: {error}", raw.display()))?;
    if runtime == source || runtime.starts_with(&source) {
        return Err(format!(
            "runtime root {} is inside source root {}; choose an external root",
            runtime.display(),
            source.display()
        ));
    }
    Ok(runtime)
}

/// Validate a write target: it must be absolute, external to the source, and
/// contained by the runtime root after resolving all existing symlinks.
pub fn validate_external_target(
    source_root: &Path,
    runtime_root: &Path,
    target: &Path,
    label: &str,
) -> Result<PathBuf, String> {
    let source_root = expand_user_path(source_root)?;
    let runtime_root = expand_user_path(runtime_root)?;
    let source = fs::canonicalize(&source_root).map_err(|error| {
        format!(
            "canonicalize source root {}: {error}",
            source_root.display()
        )
    })?;
    let runtime = fs::canonicalize(&runtime_root).map_err(|error| {
        format!(
            "canonicalize runtime root {}: {error}",
            runtime_root.display()
        )
    })?;
    let target = absolute(target)?;
    let parent = target
        .parent()
        .ok_or_else(|| format!("{label} has no parent: {}", target.display()))?;
    let canonical_parent = canonical_existing_parent(parent)?;
    if canonical_parent == source || canonical_parent.starts_with(&source) {
        return Err(format!(
            "{label} {} is inside source root {}",
            target.display(),
            source.display()
        ));
    }
    if canonical_parent != runtime && !canonical_parent.starts_with(&runtime) {
        return Err(format!(
            "{label} {} escapes runtime root {}",
            target.display(),
            runtime.display()
        ));
    }
    if target.exists() {
        let canonical_target = fs::canonicalize(&target)
            .map_err(|error| format!("canonicalize {label} {}: {error}", target.display()))?;
        if canonical_target == source || canonical_target.starts_with(&source) {
            return Err(format!(
                "{label} {} resolves inside source root {}",
                target.display(),
                source.display()
            ));
        }
        if canonical_target != runtime && !canonical_target.starts_with(&runtime) {
            return Err(format!(
                "{label} {} resolves outside runtime root {}",
                target.display(),
                runtime.display()
            ));
        }
    }
    Ok(target)
}

pub fn stable_source_key(source_root: &Path) -> String {
    let digest = Sha256::digest(source_root.to_string_lossy().as_bytes());
    digest[..12]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// An explicitly selected runtime directory, used by the private feedback producer.
/// Child operations stay relative to this handle; this is not parent/Git authority.
pub(crate) struct RuntimeDirectory {
    directory: cap_std::fs::Dir,
}

impl RuntimeDirectory {
    pub(crate) fn open(path: &Path, create: bool) -> std::io::Result<Self> {
        if !path.is_absolute() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "absolute runtime directory required",
            ));
        }
        if create {
            fs::create_dir_all(path)?;
        }
        let path = fs::canonicalize(path)?;
        let directory = cap_std::fs::Dir::open_ambient_dir(&path, cap_std::ambient_authority())?;
        Ok(Self { directory })
    }

    /// Open an absolute directory by walking every component without following symlinks.
    pub(crate) fn open_nofollow(path: &Path, create: bool) -> std::io::Result<Self> {
        use cap_fs_ext::DirExt;
        if !path.is_absolute() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "absolute runtime directory required",
            ));
        }
        let mut components = path.components();
        #[cfg(windows)]
        let mut directory = {
            let prefix = match components.next() {
                Some(Component::Prefix(prefix)) => prefix,
                _ => {
                    return Err(std::io::Error::new(
                        std::io::ErrorKind::InvalidInput,
                        "absolute runtime directory requires a volume prefix",
                    ))
                }
            };
            if !matches!(components.next(), Some(Component::RootDir)) {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidInput,
                    "absolute runtime directory requires a volume root",
                ));
            }
            let mut volume_root = PathBuf::from(prefix.as_os_str());
            volume_root.push(std::path::MAIN_SEPARATOR.to_string());
            cap_std::fs::Dir::open_ambient_dir(&volume_root, cap_std::ambient_authority())?
        };
        #[cfg(not(windows))]
        let mut directory = {
            if !matches!(components.next(), Some(Component::RootDir)) {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidInput,
                    "absolute runtime directory requires a root component",
                ));
            }
            cap_std::fs::Dir::open_ambient_dir(Path::new("/"), cap_std::ambient_authority())?
        };
        for component in components {
            match component {
                Component::Normal(name) => match directory.open_dir_nofollow(name) {
                    Ok(child) => directory = child,
                    Err(error) if create && error.kind() == std::io::ErrorKind::NotFound => {
                        match directory.create_dir(name) {
                            Ok(()) => {}
                            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                            Err(error) => return Err(error),
                        }
                        directory = directory.open_dir_nofollow(name)?;
                    }
                    Err(error) => return Err(error),
                },
                Component::CurDir | Component::ParentDir | Component::Prefix(_) => {
                    return Err(std::io::Error::new(
                        std::io::ErrorKind::InvalidInput,
                        "runtime directory path is not canonical",
                    ));
                }
                Component::RootDir => {
                    return Err(std::io::Error::new(
                        std::io::ErrorKind::InvalidInput,
                        "runtime directory path contains an unexpected root component",
                    ));
                }
            }
        }
        Ok(Self { directory })
    }

    pub(crate) fn child(&self, relative: &Path, create: bool) -> std::io::Result<Self> {
        use cap_fs_ext::DirExt;
        use std::path::Component;
        let mut directory = self.directory.try_clone()?;
        for component in relative.components() {
            let Component::Normal(name) = component else {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidInput,
                    "invalid runtime-relative directory",
                ));
            };
            match directory.open_dir_nofollow(name) {
                Ok(child) => directory = child,
                Err(error) if create && error.kind() == std::io::ErrorKind::NotFound => {
                    match directory.create_dir(name) {
                        Ok(()) => {}
                        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                        Err(error) => return Err(error),
                    }
                    directory = directory.open_dir_nofollow(name)?;
                    private_directory_mode(&directory)?;
                }
                Err(error) => return Err(error),
            }
        }
        Ok(Self { directory })
    }

    pub(crate) fn make_private(&self) -> std::io::Result<()> {
        private_directory_mode(&self.directory)
    }

    fn sync_directory(&self) -> std::io::Result<()> {
        use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};

        // Dir handles are opened for capability-relative traversal and may be O_PATH.
        // Reopen `.` relative to that handle to obtain an fsync-capable descriptor.
        let mut options = cap_std::fs::OpenOptions::new();
        #[cfg(windows)]
        {
            use cap_std::fs::OpenOptionsExt;
            options
                .read(true)
                .write(true)
                .custom_flags(WINDOWS_FILE_FLAG_BACKUP_SEMANTICS);
        }
        #[cfg(not(windows))]
        options.read(true);
        options.follow(FollowSymlinks::No);
        let directory = self.directory.open_with(Path::new("."), &options)?;
        if !directory.metadata()?.is_dir() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "runtime directory handle is not a directory",
            ));
        }
        directory.sync_all()
    }

    fn parent(&self, relative: &Path, create: bool) -> std::io::Result<(Self, std::ffi::OsString)> {
        use std::path::Component;
        if relative.as_os_str().is_empty()
            || relative
                .components()
                .any(|part| !matches!(part, Component::Normal(_)))
        {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "invalid runtime-relative file",
            ));
        }
        let name = relative.file_name().ok_or_else(|| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "runtime file name required",
            )
        })?;
        let parent = self.child(relative.parent().unwrap_or(Path::new("")), create)?;
        Ok((parent, name.to_os_string()))
    }

    pub(crate) fn read(&self, relative: &Path) -> std::io::Result<Option<Vec<u8>>> {
        self.read_stable(relative)
            .map(|result| result.map(|(bytes, _)| bytes))
    }

    pub(crate) fn read_stable(
        &self,
        relative: &Path,
    ) -> std::io::Result<Option<(Vec<u8>, RuntimeFileSnapshot)>> {
        use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
        let (parent, name) = match self.parent(relative, false) {
            Ok(value) => value,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error),
        };
        let mut options = cap_std::fs::OpenOptions::new();
        options.read(true).follow(FollowSymlinks::No);
        let before = match parent.directory.symlink_metadata(&name) {
            Ok(metadata) if metadata.is_file() => metadata,
            Ok(_) => {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    "runtime target is not a regular file",
                ))
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error),
        };
        #[cfg(unix)]
        {
            use cap_fs_ext::OpenOptionsSyncExt;
            options.nonblock(true);
        }
        let mut file = match parent.directory.open_with(&name, &options) {
            Ok(file) => file,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error),
        };
        let opened = file.metadata()?;
        if !opened.is_file() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "runtime target is not a regular file",
            ));
        }
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes)?;
        let after = file.metadata()?;
        let before_snapshot = RuntimeFileSnapshot::from_metadata(&before);
        let opened_snapshot = RuntimeFileSnapshot::from_metadata(&opened);
        let after_snapshot = RuntimeFileSnapshot::from_metadata(&after);
        if before_snapshot != opened_snapshot || opened_snapshot != after_snapshot {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "runtime file changed during read",
            ));
        }
        if bytes.len() as u64 != after.len() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "runtime file size changed during read",
            ));
        }
        Ok(Some((bytes, after_snapshot)))
    }

    pub(crate) fn read_candidate(&self, relative: &Path) -> std::io::Result<Option<Vec<u8>>> {
        let (parent, name) = match self.parent(relative, false) {
            Ok(value) => value,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error),
        };
        match parent.directory.symlink_metadata(&name) {
            Ok(metadata) if metadata.is_file() => parent.read(Path::new(&name)),
            Ok(_) => Ok(None),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
            Err(error) => Err(error),
        }
    }

    /// The caller holds the stable spool lock through read, write and publication.
    pub(crate) fn write_once(&self, relative: &Path, bytes: &[u8]) -> std::io::Result<()> {
        use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
        use std::io::Write;
        use std::sync::atomic::{AtomicU64, Ordering};
        static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);
        let (parent, name) = self.parent(relative, true)?;
        parent.make_private()?;
        if let Some(existing) = parent.read(Path::new(&name))? {
            return identical_private_bytes(&existing, bytes);
        }
        let mut options = cap_std::fs::OpenOptions::new();
        options
            .write(true)
            .create_new(true)
            .follow(FollowSymlinks::No);
        #[cfg(unix)]
        {
            use cap_std::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let (temporary, mut file) = loop {
            let temporary = format!(
                ".private-feedback-{}-{}.tmp",
                std::process::id(),
                NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
            );
            match parent.directory.open_with(&temporary, &options) {
                Ok(file) => break (temporary, file),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(error),
            }
        };
        let result = (|| {
            file.write_all(bytes)?;
            file.sync_all()?;
            drop(file);
            // Preserve a pre-existing/conflicting record even if another producer
            // did not participate in the spool protocol. The protocol lock, not
            // this preflight, serializes cooperating publication and host cleanup.
            if let Some(existing) = parent.read(Path::new(&name))? {
                return identical_private_bytes(&existing, bytes);
            }
            parent
                .directory
                .rename(&temporary, &parent.directory, &name)
        })();
        let cleanup = parent.directory.remove_file(&temporary);
        match (result, cleanup) {
            (Err(error), _) => Err(error),
            (Ok(()), Err(error)) if error.kind() != std::io::ErrorKind::NotFound => Err(error),
            _ => Ok(()),
        }
    }

    /// Atomically replace one handle-relative regular file and sync the file and parent.
    pub(crate) fn atomic_write_bytes(
        &self,
        relative: &Path,
        bytes: &[u8],
        mode: u32,
    ) -> std::io::Result<()> {
        #[cfg(not(unix))]
        let _ = mode;
        use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
        use std::sync::atomic::{AtomicU64, Ordering};
        static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);
        let (parent, name) = self
            .parent(relative, true)
            .map_err(|error| atomic_write_stage("parent_directory_open", error))?;
        parent
            .make_private()
            .map_err(|error| atomic_write_stage("parent_directory_permissions", error))?;
        match parent.directory.symlink_metadata(&name) {
            Ok(metadata) if metadata.is_file() => {}
            Ok(_) => {
                return Err(atomic_write_stage(
                    "target_type_check",
                    std::io::Error::new(
                        std::io::ErrorKind::InvalidData,
                        "runtime target is not a regular file",
                    ),
                ))
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(atomic_write_stage("target_inspect", error)),
        }
        let mut options = cap_std::fs::OpenOptions::new();
        options
            .write(true)
            .create_new(true)
            .follow(FollowSymlinks::No);
        #[cfg(unix)]
        {
            use cap_std::fs::OpenOptionsExt;
            options.mode(mode);
        }
        let (temporary, mut file) = loop {
            let temporary = format!(
                ".runtime-artifact-{}-{}.tmp",
                std::process::id(),
                NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
            );
            match parent.directory.open_with(&temporary, &options) {
                Ok(file) => break (temporary, file),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(atomic_write_stage("temporary_file_open", error)),
            }
        };
        let result = (|| {
            #[cfg(unix)]
            {
                use cap_std::fs::PermissionsExt;
                file.set_permissions(cap_std::fs::Permissions::from_mode(mode))
                    .map_err(|error| atomic_write_stage("temporary_file_permissions", error))?;
            }
            file.write_all(bytes)
                .map_err(|error| atomic_write_stage("temporary_file_write", error))?;
            file.sync_all()
                .map_err(|error| atomic_write_stage("temporary_file_sync", error))?;
            drop(file);
            parent
                .directory
                .rename(&temporary, &parent.directory, &name)
                .map_err(|error| atomic_write_stage("target_rename", error))?;
            parent
                .sync_directory()
                .map_err(|error| atomic_write_stage("parent_directory_sync", error))
        })();
        let cleanup = parent.directory.remove_file(&temporary);
        match (result, cleanup) {
            (Err(error), _) => Err(error),
            (Ok(()), Err(error)) if error.kind() != std::io::ErrorKind::NotFound => {
                Err(atomic_write_stage("temporary_file_cleanup", error))
            }
            _ => Ok(()),
        }
    }

    pub(crate) fn append(&self, relative: &Path, bytes: &[u8]) -> std::io::Result<()> {
        use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
        use std::io::Write;
        let (parent, name) = self.parent(relative, true)?;
        let mut options = cap_std::fs::OpenOptions::new();
        options
            .read(true)
            .append(true)
            .create(true)
            .follow(FollowSymlinks::No);
        #[cfg(unix)]
        {
            use cap_std::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = parent.directory.open_with(&name, &options)?;
        if !file.metadata()?.is_file() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "runtime target is not a regular file",
            ));
        }
        file.write_all(bytes)?;
        file.sync_all()
    }

    pub(crate) fn lock(&self, relative: &Path) -> std::io::Result<RuntimeFileLock> {
        use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
        use std::io::Write;
        let (parent, name) = self.parent(relative, true)?;
        let mut options = cap_std::fs::OpenOptions::new();
        options
            .read(true)
            .write(true)
            .create(true)
            .follow(FollowSymlinks::No);
        #[cfg(unix)]
        {
            use cap_std::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = parent.directory.open_with(&name, &options)?.into_std();
        if !file.metadata()?.is_file() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "runtime lock is not a regular file",
            ));
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            file.set_permissions(fs::Permissions::from_mode(0o600))?;
        }
        if file.metadata()?.len() == 0 {
            file.write_all(&[0])?;
        }
        file.lock()?;
        Ok(RuntimeFileLock { file })
    }

    pub(crate) fn files(&self, relative: &Path) -> std::io::Result<Vec<PathBuf>> {
        let start = match self.child(relative, false) {
            Ok(value) => value,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
            Err(error) => return Err(error),
        };
        let mut stack = vec![(start, relative.to_path_buf())];
        let mut files = Vec::new();
        while let Some((directory, prefix)) = stack.pop() {
            for entry in directory.directory.entries()? {
                let entry = entry?;
                let name = entry.file_name();
                let kind = entry.file_type()?;
                let path = prefix.join(&name);
                if kind.is_dir() {
                    stack.push((directory.child(Path::new(&name), false)?, path));
                } else if kind.is_file() {
                    files.push(path);
                }
            }
        }
        files.sort();
        Ok(files)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct RuntimeFileSnapshot {
    pub(crate) device: u64,
    pub(crate) inode: u64,
    pub(crate) mode: u32,
    pub(crate) size: u64,
    pub(crate) mtime_ns: i128,
}

#[derive(Debug)]
struct RuntimeAtomicWriteStageError {
    stage: &'static str,
    source: std::io::Error,
}

impl std::fmt::Display for RuntimeAtomicWriteStageError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            formatter,
            "atomic write stage {}: {}",
            self.stage, self.source
        )
    }
}

impl std::error::Error for RuntimeAtomicWriteStageError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        Some(&self.source)
    }
}

fn atomic_write_stage(stage: &'static str, source: std::io::Error) -> std::io::Error {
    // Keep the original category and source while making the failing filesystem stage visible.
    let kind = source.kind();
    std::io::Error::new(kind, RuntimeAtomicWriteStageError { stage, source })
}

impl RuntimeFileSnapshot {
    fn from_metadata(metadata: &cap_std::fs::Metadata) -> Self {
        #[cfg(unix)]
        use cap_std::fs::{MetadataExt, PermissionsExt};
        #[cfg(unix)]
        let (device, inode, mode, mtime_ns) = (
            metadata.dev(),
            metadata.ino(),
            metadata.permissions().mode() & 0o7777,
            i128::from(metadata.mtime()) * 1_000_000_000 + i128::from(metadata.mtime_nsec()),
        );
        #[cfg(not(unix))]
        let (device, inode, mode, mtime_ns) = (0, 0, 0, 0);
        Self {
            device,
            inode,
            mode,
            size: metadata.len(),
            mtime_ns,
        }
    }
}

fn identical_private_bytes(existing: &[u8], requested: &[u8]) -> std::io::Result<()> {
    if existing == requested {
        Ok(())
    } else {
        Err(std::io::Error::new(
            std::io::ErrorKind::AlreadyExists,
            "existing private record differs",
        ))
    }
}

fn private_directory_mode(directory: &cap_std::fs::Dir) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        use cap_std::fs::PermissionsExt;
        directory.set_permissions(".", cap_std::fs::Permissions::from_mode(0o700))?;
    }
    #[cfg(not(unix))]
    let _ = directory;
    Ok(())
}

pub(crate) struct RuntimeFileLock {
    file: fs::File,
}

impl RuntimeFileLock {
    pub(crate) fn finish(self) -> std::io::Result<()> {
        self.file.unlock()
    }
}

const SOURCE_RUNTIME_DIRECTORY: &str = ".runtime";
const SOURCE_RUNTIME_ALLOWED_TOP_LEVELS: [&str; 2] = ["locks", "spool"];

/// A validated explicit runtime artifact root. This type never grants parent-root authority.
pub struct RuntimeArtifactBoundary {
    source_root: PathBuf,
    root: PathBuf,
    directory: RuntimeDirectory,
    spool_only: bool,
    source_runtime_spool: bool,
}

/// The restricted bootstrap spool/control capability, distinct from general artifacts.
pub struct RuntimeSpoolBoundary(RuntimeArtifactBoundary);

impl std::ops::Deref for RuntimeSpoolBoundary {
    type Target = RuntimeArtifactBoundary;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl RuntimeArtifactBoundary {
    pub fn for_source(
        source_root: &Path,
        requested: Option<&Path>,
        create: bool,
    ) -> Result<Self, String> {
        let source_root = expand_user_path(source_root)?;
        let source = fs::canonicalize(&source_root).map_err(|error| {
            format!(
                "source root is unavailable: {}: {error}",
                source_root.display()
            )
        })?;
        let requested = requested
            .map(Path::to_path_buf)
            .or_else(|| {
                env::var_os(RUNTIME_ROOT_ENV)
                    .filter(|value| !value.is_empty())
                    .and_then(|value| value.into_string().ok())
                    .map(|value| value.trim().to_string())
                    .filter(|value| !value.is_empty())
                    .map(PathBuf::from)
            })
            .ok_or_else(|| {
                format!(
                    "explicit runtime root required; pass --runtime-root or set {RUNTIME_ROOT_ENV}"
                )
            })?;
        let root = resolve_explicit_root(&source, &requested, create)?;
        let directory = RuntimeDirectory::open_nofollow(&root, false)
            .map_err(|error| format!("runtime root is unavailable: {}: {error}", root.display()))?;
        Ok(Self {
            source_root: source,
            root,
            directory,
            spool_only: false,
            source_runtime_spool: false,
        })
    }

    fn for_spool(
        source_root: &Path,
        requested: Option<&Path>,
        create: bool,
    ) -> Result<Self, String> {
        let source_root = expand_user_path(source_root)?;
        let source = fs::canonicalize(&source_root).map_err(|error| {
            format!(
                "source root is unavailable: {}: {error}",
                source_root.display()
            )
        })?;
        let requested = requested
            .map(Path::to_path_buf)
            .or_else(|| {
                env::var_os(RUNTIME_ROOT_ENV)
                    .filter(|value| !value.is_empty())
                    .and_then(|value| value.into_string().ok())
                    .map(|value| value.trim().to_string())
                    .filter(|value| !value.is_empty())
                    .map(PathBuf::from)
            })
            .ok_or_else(|| {
                format!(
                    "explicit runtime root required; pass --runtime-root or set {RUNTIME_ROOT_ENV}"
                )
            })?;
        let requested = expand_user_path(&requested)?;
        if !requested.is_absolute() {
            return Err(format!(
                "runtime root must be absolute: {}",
                requested.display()
            ));
        }
        let source_runtime = source.join(SOURCE_RUNTIME_DIRECTORY);
        let source_runtime_spool = requested == source_runtime;
        let root = if source_runtime_spool {
            reject_symlink_components(&requested, Path::new("/"))?;
            if create {
                RuntimeDirectory::open_nofollow(&requested, true).map_err(|error| {
                    format!(
                        "runtime root is unavailable: {}: {error}",
                        requested.display()
                    )
                })?;
            } else if !requested.is_dir() {
                return Err(format!(
                    "runtime root is unavailable: {}",
                    requested.display()
                ));
            }
            requested
        } else {
            resolve_explicit_root(&source, &requested, create)?
        };
        let directory = RuntimeDirectory::open_nofollow(&root, false)
            .map_err(|error| format!("runtime root is unavailable: {}: {error}", root.display()))?;
        Ok(Self {
            source_root: source,
            root,
            directory,
            spool_only: true,
            source_runtime_spool,
        })
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    pub fn resolve(&self, path: &Path) -> Result<PathBuf, String> {
        let canonical_absolute = if path.is_absolute() {
            reject_symlink_components(path, Path::new("/"))?;
            Some(canonicalize_with_missing_suffix(path)?)
        } else {
            None
        };
        let relative = if let Some(canonical_absolute) = &canonical_absolute {
            canonical_absolute
                .strip_prefix(&self.root)
                .map_err(|_| format!("path escapes runtime root: {}", path.display()))?
        } else {
            path
        };
        let mut parts = Vec::new();
        for component in relative.components() {
            match component {
                Component::Normal(part) => parts.push(part.to_os_string()),
                _ => return Err(format!("unsafe runtime-relative path: {}", path.display())),
            }
        }
        if parts.is_empty() {
            return Err("runtime root itself is not an artifact".to_string());
        }
        if self.spool_only {
            let first = parts[0].to_string_lossy();
            if !SOURCE_RUNTIME_ALLOWED_TOP_LEVELS
                .iter()
                .any(|allowed| first == *allowed)
            {
                return Err(format!(
                    "runtime spool path is outside bootstrap spool/control paths: {}",
                    path.display()
                ));
            }
        }
        let mut relative = PathBuf::new();
        for part in &parts {
            relative.push(part);
        }
        let joined = self.root.join(&relative);
        reject_symlink_components(&joined, &self.root)?;
        match self.directory.parent(&relative, false) {
            Ok((parent, name)) => match parent.directory.symlink_metadata(&name) {
                Ok(metadata) if metadata.is_symlink() => {
                    return Err(format!("runtime target is a symlink: {}", joined.display()))
                }
                Ok(_) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => {
                    return Err(format!(
                        "cannot inspect runtime path {}: {error}",
                        joined.display()
                    ))
                }
            },
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(format!(
                    "cannot inspect runtime path {}: {error}",
                    joined.display()
                ))
            }
        }
        if self.source_runtime_spool && !joined.starts_with(&self.source_root) {
            return Err(format!(
                "source runtime path escaped source root: {}",
                joined.display()
            ));
        }
        Ok(joined)
    }

    pub fn ensure_directory(&self, path: &Path) -> Result<PathBuf, String> {
        let target = if path == Path::new(".") {
            self.root.clone()
        } else {
            self.resolve(path)?
        };
        let relative = target
            .strip_prefix(&self.root)
            .map_err(|_| format!("path escapes runtime root: {}", target.display()))?;
        self.directory.child(relative, true).map_err(|error| {
            format!(
                "cannot create runtime directory {}: {error}",
                target.display()
            )
        })?;
        Ok(target)
    }

    pub fn atomic_write_bytes(
        &self,
        path: &Path,
        bytes: &[u8],
        mode: u32,
    ) -> Result<PathBuf, String> {
        let target = self.resolve(path)?;
        let relative = target
            .strip_prefix(&self.root)
            .map_err(|_| format!("path escapes runtime root: {}", target.display()))?;
        self.directory
            .atomic_write_bytes(relative, bytes, mode)
            .map_err(|error| {
                format!("atomic runtime write failed: {}: {error}", target.display())
            })?;
        Ok(target)
    }

    pub fn atomic_write_text(&self, path: &Path, text: &str, mode: u32) -> Result<PathBuf, String> {
        self.atomic_write_bytes(path, text.as_bytes(), mode)
    }

    pub fn atomic_write_json(
        &self,
        path: &Path,
        value: &serde_json::Value,
        mode: u32,
    ) -> Result<PathBuf, String> {
        let mut bytes = serde_json::to_vec_pretty(value)
            .map_err(|error| format!("runtime JSON serialization failed: {error}"))?;
        bytes.push(b'\n');
        self.atomic_write_bytes(path, &bytes, mode)
    }

    pub fn append_bytes(&self, path: &Path, bytes: &[u8], mode: u32) -> Result<PathBuf, String> {
        let target = self.resolve(path)?;
        let relative = target
            .strip_prefix(&self.root)
            .map_err(|_| format!("path escapes runtime root: {}", target.display()))?;
        let name = relative
            .file_name()
            .ok_or_else(|| format!("runtime target has no filename: {}", target.display()))?;
        let lock_name = format!(".{}.lock", name.to_string_lossy());
        let lock_path = relative.parent().unwrap_or(Path::new("")).join(lock_name);
        let _lock = self.directory.lock(&lock_path).map_err(|error| {
            format!("external append lock failed: {}: {error}", target.display())
        })?;
        let mut merged = self
            .directory
            .read(relative)
            .map_err(|error| format!("cannot read runtime artifact {}: {error}", target.display()))?
            .unwrap_or_default();
        merged.extend_from_slice(bytes);
        self.directory
            .atomic_write_bytes(relative, &merged, mode)
            .map_err(|error| format!("external append failed: {}: {error}", target.display()))?;
        Ok(target)
    }

    pub fn digest(&self, path: &Path) -> Result<String, String> {
        let target = self.resolve(path)?;
        let relative = target
            .strip_prefix(&self.root)
            .map_err(|_| format!("path escapes runtime root: {}", target.display()))?;
        let bytes = self
            .directory
            .read(relative)
            .map_err(|error| format!("cannot read runtime artifact {}: {error}", target.display()))?
            .ok_or_else(|| format!("cannot read runtime artifact: {}", target.display()))?;
        Ok(Sha256::digest(bytes)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect())
    }
}

impl RuntimeSpoolBoundary {
    pub fn for_source(
        source_root: &Path,
        requested: Option<&Path>,
        create: bool,
    ) -> Result<Self, String> {
        RuntimeArtifactBoundary::for_spool(source_root, requested, create).map(Self)
    }

    pub fn boundary(&self) -> &RuntimeArtifactBoundary {
        &self.0
    }
}

fn resolve_explicit_root(source: &Path, requested: &Path, create: bool) -> Result<PathBuf, String> {
    let requested = expand_user_path(requested)?;
    if !requested.is_absolute() {
        return Err(format!(
            "runtime root must be absolute: {}",
            requested.display()
        ));
    }
    reject_symlink_components(&requested, Path::new("/"))?;
    let normalized = normalize_absolute_path(&requested);
    let existing_parent = canonical_existing_parent(&requested).map_err(|error| {
        format!(
            "runtime root is unavailable: {}: {error}",
            requested.display()
        )
    })?;
    if existing_parent == source || existing_parent.starts_with(source) {
        return Err(format!(
            "runtime root must not be inside source root: source={} runtime={}",
            source.display(),
            requested.display()
        ));
    }
    if create {
        RuntimeDirectory::open_nofollow(&normalized, true).map_err(|error| {
            format!(
                "runtime root is unavailable: {}: {error}",
                requested.display()
            )
        })?;
    } else if !normalized.is_dir() {
        return Err(format!(
            "runtime root is unavailable: {}",
            requested.display()
        ));
    }
    let root = fs::canonicalize(&normalized).map_err(|error| {
        format!(
            "runtime root is unavailable: {}: {error}",
            requested.display()
        )
    })?;
    if root == source || root.starts_with(source) {
        return Err(format!(
            "runtime root must not be inside source root: source={} runtime={}",
            source.display(),
            root.display()
        ));
    }
    Ok(root)
}

fn inspect_runtime_path_component(path: &Path) -> Result<(), String> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_symlink() => Err(format!(
            "runtime root contains symlink component {}",
            path.display()
        )),
        Ok(_) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(format!(
            "cannot inspect runtime path {}: {error}",
            path.display()
        )),
    }
}

fn reject_symlink_components(path: &Path, stop: &Path) -> Result<(), String> {
    #[cfg(windows)]
    if stop == Path::new("/") {
        let mut components = path.components();
        let prefix = match components.next() {
            Some(Component::Prefix(prefix)) => prefix,
            _ => return Err(format!("path is outside boundary: {}", path.display())),
        };
        if !matches!(components.next(), Some(Component::RootDir)) {
            return Err(format!("path is outside boundary: {}", path.display()));
        }
        let mut current = PathBuf::from(prefix.as_os_str());
        current.push(std::path::MAIN_SEPARATOR.to_string());
        let volume_root = current.clone();
        for component in components {
            match component {
                Component::Normal(name) => {
                    current.push(name);
                    inspect_runtime_path_component(&current)?;
                }
                Component::ParentDir => {
                    if current != volume_root {
                        current.pop();
                    }
                }
                Component::CurDir => {}
                Component::RootDir | Component::Prefix(_) => {
                    return Err(format!("path is outside boundary: {}", path.display()))
                }
            }
        }
        return Ok(());
    }

    let relative = path
        .strip_prefix(stop)
        .map_err(|_| format!("path is outside boundary: {}", path.display()))?;
    let mut current = stop.to_path_buf();
    for component in relative.components() {
        match component {
            Component::Normal(name) => {
                current.push(name);
                inspect_runtime_path_component(&current)?;
            }
            Component::ParentDir => {
                current.pop();
            }
            Component::RootDir | Component::CurDir | Component::Prefix(_) => {}
        }
    }
    Ok(())
}

#[cfg(windows)]
fn normalize_absolute_path(path: &Path) -> PathBuf {
    let mut components = path.components();
    let Some(Component::Prefix(prefix)) = components.next() else {
        return path.to_path_buf();
    };
    if !matches!(components.next(), Some(Component::RootDir)) {
        return path.to_path_buf();
    }
    let mut normalized = PathBuf::from(prefix.as_os_str());
    normalized.push(std::path::MAIN_SEPARATOR.to_string());
    for component in components {
        match component {
            Component::Normal(name) => normalized.push(name),
            Component::CurDir => {}
            Component::ParentDir => {
                if normalized.components().count() > 2 {
                    normalized.pop();
                }
            }
            Component::RootDir | Component::Prefix(_) => return path.to_path_buf(),
        }
    }
    normalized
}

#[cfg(not(windows))]
fn normalize_absolute_path(path: &Path) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::Prefix(prefix) => normalized.push(prefix.as_os_str()),
            Component::RootDir => normalized.push(std::path::MAIN_SEPARATOR.to_string()),
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            Component::Normal(name) => normalized.push(name),
        }
    }
    normalized
}

const SAFE_CHILD_ENV_NAMES: [&str; 9] = [
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONUNBUFFERED",
    "SYSTEMROOT",
    "PATHEXT",
];
const RUNTIME_PATH_ENV_NAMES: [&str; 9] = [
    "TMPDIR",
    "TEMP",
    "TMP",
    "XDG_CACHE_HOME",
    "PYTHONPYCACHEPREFIX",
    "AGENT_CANON_TOOLS_HOME",
    "CARGO_HOME",
    "CARGO_TARGET_DIR",
    "AGENT_CANON_CLI_TARGET_DIR",
];

/// Copy only non-secret process settings and attach path identities, not write attestations.
pub fn root_capability_environment(
    source_root: &Path,
    runtime_root: &Path,
    base_env: Option<&BTreeMap<String, String>>,
    target_root: Option<&Path>,
) -> Result<BTreeMap<String, String>, String> {
    let source_root = expand_user_path(source_root)?;
    let target_root = expand_user_path(target_root.unwrap_or(&source_root))?;
    let runtime_root = expand_user_path(runtime_root)?;
    let parent = fs::canonicalize(&source_root).map_err(|error| {
        format!(
            "root capability is unavailable: {}: {error}",
            source_root.display()
        )
    })?;
    let target = fs::canonicalize(&target_root).map_err(|error| {
        format!(
            "root capability is unavailable: {}: {error}",
            target_root.display()
        )
    })?;
    let runtime = fs::canonicalize(&runtime_root).map_err(|error| {
        format!(
            "root capability is unavailable: {}: {error}",
            runtime_root.display()
        )
    })?;
    let supplied = base_env.cloned().unwrap_or_else(|| {
        env::vars_os()
            .filter_map(|(name, value)| Some((name.into_string().ok()?, value.into_string().ok()?)))
            .collect::<BTreeMap<String, String>>()
    });
    let mut child = supplied
        .into_iter()
        .filter(|(name, _)| {
            SAFE_CHILD_ENV_NAMES.contains(&name.as_str())
                || RUNTIME_PATH_ENV_NAMES.contains(&name.as_str())
                || name.starts_with("LC_")
        })
        .collect::<BTreeMap<_, _>>();
    let identity = |path: &Path| -> Result<(String, String), String> {
        let directory = RuntimeDirectory::open_nofollow(path, false).map_err(|error| {
            format!(
                "root capability is unavailable: {}: {error}",
                path.display()
            )
        })?;
        let metadata = directory.directory.dir_metadata().map_err(|error| {
            format!(
                "root capability is unavailable: {}: {error}",
                path.display()
            )
        })?;
        #[cfg(any(unix, windows))]
        {
            use cap_fs_ext::MetadataExt;
            Ok((metadata.dev().to_string(), metadata.ino().to_string()))
        }
        #[cfg(not(any(unix, windows)))]
        {
            let _ = metadata;
            Err("root device/inode identity is unavailable on this platform".to_string())
        }
    };
    let (parent_dev, parent_ino) = identity(&parent)?;
    let (target_dev, target_ino) = identity(&target)?;
    let (runtime_dev, runtime_ino) = identity(&runtime)?;
    child.insert(RUNTIME_ROOT_ENV.to_string(), runtime.display().to_string());
    child.insert(
        "AGENT_CANON_PARENT_ROOT".to_string(),
        parent.display().to_string(),
    );
    child.insert(
        "AGENT_CANON_TARGET_ROOT".to_string(),
        target.display().to_string(),
    );
    child.insert(
        "AGENT_CANON_PARENT_ROOT_DEV".to_string(),
        parent_dev.clone(),
    );
    child.insert(
        "AGENT_CANON_PARENT_ROOT_INO".to_string(),
        parent_ino.clone(),
    );
    child.insert(
        "AGENT_CANON_TARGET_ROOT_DEV".to_string(),
        target_dev.clone(),
    );
    child.insert(
        "AGENT_CANON_TARGET_ROOT_INO".to_string(),
        target_ino.clone(),
    );
    child.insert(
        "AGENT_CANON_PARENT_ROOT_CAPABILITY".to_string(),
        serde_json::to_string(&serde_json::json!({
            "kind": "parent-root",
            "root": parent.display().to_string(),
            "dev": parent_dev,
            "ino": parent_ino,
        }))
        .map_err(|error| format!("root capability serialization failed: {error}"))?,
    );
    child.insert(
        "AGENT_CANON_TARGET_ROOT_CAPABILITY".to_string(),
        serde_json::to_string(&serde_json::json!({
            "kind": "target-root",
            "root": target.display().to_string(),
            "dev": target_dev,
            "ino": target_ino,
        }))
        .map_err(|error| format!("root capability serialization failed: {error}"))?,
    );
    child.insert("AGENT_CANON_RUNTIME_ROOT_DEV".to_string(), runtime_dev);
    child.insert("AGENT_CANON_RUNTIME_ROOT_INO".to_string(), runtime_ino);
    Ok(child)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn expands_only_explicit_current_home_paths() {
        let home = current_home_directory().expect("current home directory");
        assert_eq!(
            expand_user_path(Path::new("~/runtime-fixture")).unwrap(),
            home.join("runtime-fixture")
        );
        assert_eq!(
            expand_user_path(Path::new("~named-user/runtime-fixture")).unwrap_err(),
            "named-user home expansion is unsupported"
        );
    }

    #[test]
    fn rejects_source_and_symlink_escape() {
        let root = env::temp_dir().join("agent-canon-runtime-boundary-source");
        let runtime = env::temp_dir().join("agent-canon-runtime-boundary-runtime");
        let outside = env::temp_dir().join("agent-canon-runtime-boundary-outside");
        let _ = fs::remove_dir_all(&root);
        let _ = fs::remove_dir_all(&runtime);
        let _ = fs::remove_dir_all(&outside);
        fs::create_dir_all(&root).unwrap();
        fs::create_dir_all(&runtime).unwrap();
        fs::create_dir_all(&outside).unwrap();
        assert!(validate_external_target(&root, &runtime, &root.join("cache"), "db").is_err());
        #[cfg(unix)]
        {
            std::os::unix::fs::symlink(&outside, runtime.join("escape")).unwrap();
            assert!(
                validate_external_target(&root, &runtime, &runtime.join("escape/db"), "db")
                    .is_err()
            );
        }
        let _ = fs::remove_dir_all(&root);
        let _ = fs::remove_dir_all(&runtime);
        let _ = fs::remove_dir_all(&outside);
    }
}
