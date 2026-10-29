//! Common filesystem boundary checks for analysis runtime artifacts.
//!
//! Analysis reads the selected source tree, but all databases, snapshots,
//! temporary files, and reports belong to an explicitly external runtime
//! root.  Keeping this policy in one module prevents individual tools from
//! accidentally recreating the old `.agent-canon` source-tree cache.

use sha2::{Digest, Sha256};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

pub(crate) const RUNTIME_ROOT_ENV: &str = "AGENT_CANON_RUNTIME_ROOT";

pub(crate) fn runtime_root_is_explicit() -> bool {
    env::var_os(RUNTIME_ROOT_ENV).is_some_and(|value| !value.is_empty())
}

#[cfg(test)]
pub(crate) fn test_runtime_root_path(source_root: &Path) -> Result<PathBuf, String> {
    let source = fs::canonicalize(source_root).map_err(|error| {
        format!(
            "canonicalize source root {}: {error}",
            source_root.display()
        )
    })?;
    test_runtime_root_for_source(&source)
}

#[cfg(test)]
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
    if path.is_absolute() {
        Ok(path.to_path_buf())
    } else {
        env::current_dir()
            .map(|cwd| cwd.join(path))
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

/// Resolve the process/task runtime root and prove that it is not the source.
///
/// Production callers must provide `AGENT_CANON_RUNTIME_ROOT`.  Unit tests
/// use a deterministic temporary root so that existing pure Rust fixtures can
/// continue to exercise the public command semantics without writing source.
pub(crate) fn resolve_runtime_root(source_root: &Path) -> Result<PathBuf, String> {
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

pub(crate) fn resolve_runtime_root_at(
    source_root: &Path,
    requested: Option<&Path>,
) -> Result<PathBuf, String> {
    let source = fs::canonicalize(source_root).map_err(|error| {
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
pub(crate) fn validate_external_target(
    source_root: &Path,
    runtime_root: &Path,
    target: &Path,
    label: &str,
) -> Result<PathBuf, String> {
    let source = fs::canonicalize(source_root).map_err(|error| {
        format!(
            "canonicalize source root {}: {error}",
            source_root.display()
        )
    })?;
    let runtime = fs::canonicalize(runtime_root).map_err(|error| {
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

pub(crate) fn stable_source_key(source_root: &Path) -> String {
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
            return Err(std::io::Error::new(std::io::ErrorKind::InvalidInput, "absolute runtime directory required"));
        }
        if create {
            fs::create_dir_all(path)?;
        }
        let path = fs::canonicalize(path)?;
        let directory = cap_std::fs::Dir::open_ambient_dir(&path, cap_std::ambient_authority())?;
        Ok(Self { directory })
    }

    pub(crate) fn child(&self, relative: &Path, create: bool) -> std::io::Result<Self> {
        use cap_fs_ext::DirExt;
        use std::path::Component;
        let mut directory = self.directory.try_clone()?;
        for component in relative.components() {
            let Component::Normal(name) = component else {
                return Err(std::io::Error::new(std::io::ErrorKind::InvalidInput, "invalid runtime-relative directory"));
            };
            match directory.open_dir_nofollow(name) {
                Ok(child) => directory = child,
                Err(error) if create && error.kind() == std::io::ErrorKind::NotFound => {
                    match directory.create_dir(name) {
                        Ok(()) => {},
                        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {},
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

    fn parent(&self, relative: &Path, create: bool) -> std::io::Result<(Self, std::ffi::OsString)> {
        use std::path::Component;
        if relative.as_os_str().is_empty() || relative.components().any(|part| !matches!(part, Component::Normal(_))) {
            return Err(std::io::Error::new(std::io::ErrorKind::InvalidInput, "invalid runtime-relative file"));
        }
        let name = relative.file_name().ok_or_else(|| std::io::Error::new(std::io::ErrorKind::InvalidInput, "runtime file name required"))?;
        let parent = self.child(relative.parent().unwrap_or(Path::new("")), create)?;
        Ok((parent, name.to_os_string()))
    }

    pub(crate) fn read(&self, relative: &Path) -> std::io::Result<Option<Vec<u8>>> {
        use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
        use std::io::Read;
        let (parent, name) = match self.parent(relative, false) {
            Ok(value) => value,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error),
        };
        let mut options = cap_std::fs::OpenOptions::new();
        options.read(true).follow(FollowSymlinks::No);
        match parent.directory.symlink_metadata(&name) {
            Ok(metadata) if metadata.is_file() => {},
            Ok(_) => return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "runtime target is not a regular file")),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error),
        }
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
        if !file.metadata()?.is_file() {
            return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "runtime target is not a regular file"));
        }
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes)?;
        Ok(Some(bytes))
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
        options.write(true).create_new(true).follow(FollowSymlinks::No);
        #[cfg(unix)]
        {
            use cap_std::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let (temporary, mut file) = loop {
            let temporary = format!(".private-feedback-{}-{}.tmp", std::process::id(), NEXT_TEMP.fetch_add(1, Ordering::Relaxed));
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
            parent.directory.rename(&temporary, &parent.directory, &name)
        })();
        let cleanup = parent.directory.remove_file(&temporary);
        match (result, cleanup) {
            (Err(error), _) => Err(error),
            (Ok(()), Err(error)) if error.kind() != std::io::ErrorKind::NotFound => Err(error),
            _ => Ok(()),
        }
    }

    pub(crate) fn append(&self, relative: &Path, bytes: &[u8]) -> std::io::Result<()> {
        use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
        use std::io::Write;
        let (parent, name) = self.parent(relative, true)?;
        let mut options = cap_std::fs::OpenOptions::new();
        options.read(true).append(true).create(true).follow(FollowSymlinks::No);
        #[cfg(unix)]
        {
            use cap_std::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = parent.directory.open_with(&name, &options)?;
        if !file.metadata()?.is_file() {
            return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "runtime target is not a regular file"));
        }
        file.write_all(bytes)?;
        file.sync_all()
    }

    pub(crate) fn lock(&self, relative: &Path) -> std::io::Result<RuntimeFileLock> {
        use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
        use std::io::Write;
        let (parent, name) = self.parent(relative, true)?;
        let mut options = cap_std::fs::OpenOptions::new();
        options.read(true).write(true).create(true).follow(FollowSymlinks::No);
        #[cfg(unix)]
        {
            use cap_std::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = parent.directory.open_with(&name, &options)?.into_std();
        if !file.metadata()?.is_file() {
            return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "runtime lock is not a regular file"));
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

fn identical_private_bytes(existing: &[u8], requested: &[u8]) -> std::io::Result<()> {
    if existing == requested { Ok(()) } else {
        Err(std::io::Error::new(std::io::ErrorKind::AlreadyExists, "existing private record differs"))
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

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
