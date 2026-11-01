//! Exact, caller-supplied capabilities for bounded source-file rewrites and removals.
// @dependency-start
// contract implementation
// responsibility Validates source mutation capabilities and writes or removes files only beneath their exact source-bound paths.
// upstream implementation runtime_boundary.rs owns external runtime artifacts and intentionally rejects source writes
// upstream design ../../../../../documents/tools/agent-canon.md defines the explicit source mutation capability contract
// downstream implementation docs.rs uses this capability for link rewrites, duplicate deletion, and organizer copies
// downstream test ../tests/source_mutation_native.rs validates exact scope and no-follow writes/removals
// @dependency-end

use cap_fs_ext::{DirExt, FollowSymlinks, MetadataExt, OpenOptionsFollowExt, SystemTimeSpec};
use serde_json::{Map, Value};
use std::collections::BTreeSet;
use std::ffi::{OsStr, OsString};
use std::fmt;
use std::fs;
use std::io::{self, Write};
use std::path::{Component, Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SourceMutationError {
    detail: String,
}

impl SourceMutationError {
    fn new(detail: impl Into<String>) -> Self {
        Self {
            detail: detail.into(),
        }
    }
}

impl fmt::Display for SourceMutationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.detail)
    }
}

impl std::error::Error for SourceMutationError {}

pub type Result<T> = std::result::Result<T, SourceMutationError>;

/// An opaque mutation grant bound to one canonical source root and allowed subtrees.
#[derive(Debug, Clone)]
pub struct SourceMutationCapability {
    source_root: PathBuf,
    allowed_paths: Vec<PathBuf>,
    _purpose: String,
    _authority: String,
}

impl SourceMutationCapability {
    /// Parse the existing exact three-field mutation-capability JSON shape.
    pub fn from_json(source_root: &Path, raw: Option<&str>) -> Result<Self> {
        let raw = raw.filter(|value| !value.is_empty()).ok_or_else(|| {
            SourceMutationError::new(
                "explicit mutation capability required; pass --mutation-capability-json",
            )
        })?;
        let value: Value = serde_json::from_str(raw)
            .map_err(|_| SourceMutationError::new("mutation capability is not valid JSON"))?;
        let object = value
            .as_object()
            .ok_or_else(|| SourceMutationError::new("mutation capability must be a JSON object"))?;
        reject_unknown_fields(object)?;
        let source_root = fs::canonicalize(source_root).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot resolve mutation source root {}: {error}",
                source_root.display()
            ))
        })?;
        let allowed_paths = parse_allowed_paths(object, &source_root)?;
        let purpose = required_label(object, "purpose")?;
        let authority = required_label(object, "authority")?;
        Ok(Self {
            source_root,
            allowed_paths,
            _purpose: purpose,
            _authority: authority,
        })
    }

    /// Resolve and recheck one target against this exact capability.
    pub fn assert_allowed(&self, path: &Path) -> Result<PathBuf> {
        let candidate = if path.is_absolute() {
            path.to_path_buf()
        } else {
            self.source_root.join(path)
        };
        if !candidate.starts_with(&self.source_root) {
            return Err(SourceMutationError::new(format!(
                "mutation target is outside source: {}",
                path.display()
            )));
        }
        reject_symlink_components(&self.source_root, &candidate)?;
        let resolved = resolve_with_missing(&candidate)?;
        let relative = resolved.strip_prefix(&self.source_root).map_err(|_| {
            SourceMutationError::new(format!(
                "mutation target is outside source: {}",
                path.display()
            ))
        })?;
        if !relative_path_is_allowed(relative, &self.allowed_paths) {
            return Err(SourceMutationError::new(format!(
                "mutation target is outside allowed_paths: {}",
                relative_path_as_posix(relative)
            )));
        }
        Ok(resolved)
    }

    /// Revalidate and write one UTF-8 source file without following a path symlink.
    pub fn write_text(&self, path: &Path, text: &str) -> Result<()> {
        let resolved = self.assert_allowed(path)?;
        let relative = resolved.strip_prefix(&self.source_root).map_err(|_| {
            SourceMutationError::new(format!(
                "mutation target is outside source: {}",
                path.display()
            ))
        })?;
        let components = relative.components().collect::<Vec<_>>();
        let Some(Component::Normal(name)) = components.last() else {
            return Err(SourceMutationError::new(format!(
                "mutation target must name a source file: {}",
                path.display()
            )));
        };
        let mut directory = open_root_nofollow(&self.source_root).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot open mutation source root {}: {error}",
                self.source_root.display()
            ))
        })?;
        for component in &components[..components.len() - 1] {
            let Component::Normal(component) = component else {
                return Err(SourceMutationError::new(format!(
                    "unsafe mutation target: {}",
                    path.display()
                )));
            };
            directory = directory.open_dir_nofollow(component).map_err(|error| {
                SourceMutationError::new(format!(
                    "cannot open mutation parent for {}: {error}",
                    path.display()
                ))
            })?;
        }
        let mut options = cap_std::fs::OpenOptions::new();
        options.write(true).truncate(true);
        options.follow(FollowSymlinks::No);
        let mut file = directory.open_with(name, &options).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot open mutation target {}: {error}",
                path.display()
            ))
        })?;
        file.write_all(text.as_bytes()).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot write mutation target {}: {error}",
                path.display()
            ))
        })
    }

    /// Copy one approved regular file or source symlink with copy2-style
    /// content, permission, timestamp, and available extended-attribute data.
    pub fn copy_file_with_metadata(&self, source: &Path, target: &Path) -> Result<()> {
        let resolved_target = self.assert_allowed(target)?;
        let target_relative = resolved_target
            .strip_prefix(&self.source_root)
            .map_err(|_| {
                SourceMutationError::new(format!(
                    "mutation target is outside source: {}",
                    target.display()
                ))
            })?;
        // Keep the full no-delete-share chain alive while Windows creates an
        // absolute symlink path below the canonical capability root.
        #[cfg(windows)]
        let (target_directories, target_name, target_link_path) =
            open_file_parent_chain_nofollow(&self.source_root, target_relative, true).map_err(
                |error| {
                    SourceMutationError::new(format!(
                        "cannot create mutation parent for {}: {error}",
                        target.display()
                    ))
                },
            )?;
        #[cfg(windows)]
        let target_directory = target_directories
            .last()
            .expect("target parent chain includes the volume root");
        #[cfg(not(windows))]
        let (target_directory, target_name) =
            open_file_parent_nofollow(&self.source_root, target_relative, true).map_err(
                |error| {
                    SourceMutationError::new(format!(
                        "cannot create mutation parent for {}: {error}",
                        target.display()
                    ))
                },
            )?;

        let source_candidate = if source.is_absolute() {
            source.to_path_buf()
        } else {
            self.source_root.join(source)
        };
        let source_relative = source_candidate
            .strip_prefix(&self.source_root)
            .map_err(|_| {
                SourceMutationError::new(format!(
                    "copy source is outside source root: {}",
                    source.display()
                ))
            })?;
        let (source_directory, source_name) =
            open_file_parent_nofollow(&self.source_root, source_relative, false).map_err(
                |error| {
                    SourceMutationError::new(format!(
                        "cannot open copy source parent for {}: {error}",
                        source.display()
                    ))
                },
            )?;
        let source_entry = source_directory
            .symlink_metadata(&source_name)
            .map_err(|error| {
                SourceMutationError::new(format!(
                    "cannot inspect copy source {}: {error}",
                    source.display()
                ))
            })?;
        if source_entry.is_symlink() {
            #[cfg(windows)]
            return copy_source_symlink(
                &source_directory,
                &source_name,
                target_directory,
                &target_name,
                source,
                target,
                &target_link_path,
            );
            #[cfg(not(windows))]
            return copy_source_symlink(
                &source_directory,
                &source_name,
                &target_directory,
                &target_name,
                source,
                target,
            );
        }
        if !source_entry.is_file() {
            return Err(SourceMutationError::new(format!(
                "copy source is not a regular file: {}",
                source.display()
            )));
        }

        let mut source_options = cap_std::fs::OpenOptions::new();
        source_options.read(true);
        source_options.follow(FollowSymlinks::No);
        let mut source_file = source_directory
            .open_with(&source_name, &source_options)
            .map_err(|error| {
                SourceMutationError::new(format!(
                    "cannot open copy source {}: {error}",
                    source.display()
                ))
            })?;
        let source_metadata = source_file.metadata().map_err(|error| {
            SourceMutationError::new(format!(
                "cannot inspect copy source {}: {error}",
                source.display()
            ))
        })?;
        if !source_metadata.is_file() {
            return Err(SourceMutationError::new(format!(
                "copy source is not a regular file: {}",
                source.display()
            )));
        }

        let existing_target = match target_directory.symlink_metadata(&target_name) {
            Ok(metadata) if metadata.is_symlink() => {
                return Err(SourceMutationError::new(format!(
                    "mutation target contains symlink component: {}",
                    target.display()
                )))
            }
            Ok(metadata) if metadata.is_file() => true,
            Ok(_) => {
                return Err(SourceMutationError::new(format!(
                    "copy target is not a regular file: {}",
                    target.display()
                )))
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => false,
            Err(error) => {
                return Err(SourceMutationError::new(format!(
                    "cannot inspect copy target {}: {error}",
                    target.display()
                )))
            }
        };
        let mut target_options = cap_std::fs::OpenOptions::new();
        target_options.write(true);
        target_options.follow(FollowSymlinks::No);
        if !existing_target {
            target_options.create(true);
        }
        let mut target_file = target_directory
            .open_with(&target_name, &target_options)
            .map_err(|error| {
                SourceMutationError::new(format!(
                    "cannot open copy target {}: {error}",
                    target.display()
                ))
            })?;
        let target_metadata = target_file.metadata().map_err(|error| {
            SourceMutationError::new(format!(
                "cannot inspect copy target {}: {error}",
                target.display()
            ))
        })?;
        if same_file(&source_metadata, &target_metadata) {
            return Err(SourceMutationError::new(format!(
                "copy source and target are the same file: {} and {}",
                source.display(),
                target.display()
            )));
        }
        target_file.set_len(0).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot truncate copy target {}: {error}",
                target.display()
            ))
        })?;
        io::copy(&mut source_file, &mut target_file).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot copy source {} to {}: {error}",
                source.display(),
                target.display()
            ))
        })?;

        // copy2 reads source stat after copying bytes, then applies times,
        // extended attributes, and mode in that order.
        let source_metadata = source_file.metadata().map_err(|error| {
            SourceMutationError::new(format!(
                "cannot inspect copy source {}: {error}",
                source.display()
            ))
        })?;
        let source_atime = source_metadata.accessed().map_err(|error| {
            SourceMutationError::new(format!(
                "cannot read source access time {}: {error}",
                source.display()
            ))
        })?;
        let source_mtime = source_metadata.modified().map_err(|error| {
            SourceMutationError::new(format!(
                "cannot read source modification time {}: {error}",
                source.display()
            ))
        })?;
        set_open_file_times(&target_file, source_atime, source_mtime).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot copy file times to {}: {error}",
                target.display()
            ))
        })?;
        copy_regular_file_xattrs(&source_file, &target_file).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot copy extended attributes to {}: {error}",
                target.display()
            ))
        })?;
        target_file
            .set_permissions(source_metadata.permissions())
            .map_err(|error| {
                SourceMutationError::new(format!(
                    "cannot copy file mode to {}: {error}",
                    target.display()
                ))
            })?;
        copy_regular_file_flags(&source_file, &target_file).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot copy file flags to {}: {error}",
                target.display()
            ))
        })
    }

    /// Revalidate and remove one approved file through its no-follow parent directory.
    pub fn remove_file(&self, path: &Path) -> Result<()> {
        let resolved = self.assert_allowed(path)?;
        let relative = resolved.strip_prefix(&self.source_root).map_err(|_| {
            SourceMutationError::new(format!(
                "mutation target is outside source: {}",
                path.display()
            ))
        })?;
        let components = relative.components().collect::<Vec<_>>();
        let Some(Component::Normal(name)) = components.last() else {
            return Err(SourceMutationError::new(format!(
                "mutation target must name a source file: {}",
                path.display()
            )));
        };
        let mut directory = open_root_nofollow(&self.source_root).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot open mutation source root {}: {error}",
                self.source_root.display()
            ))
        })?;
        for component in &components[..components.len() - 1] {
            let Component::Normal(component) = component else {
                return Err(SourceMutationError::new(format!(
                    "unsafe mutation target: {}",
                    path.display()
                )));
            };
            directory = directory.open_dir_nofollow(component).map_err(|error| {
                SourceMutationError::new(format!(
                    "cannot open mutation parent for {}: {error}",
                    path.display()
                ))
            })?;
        }
        // unlinkat-style removal does not follow a final symlink. The parent
        // handle was opened descriptor-relatively without following links.
        directory.remove_file(Path::new(name)).map_err(|error| {
            SourceMutationError::new(format!(
                "cannot remove mutation target {}: {error}",
                path.display()
            ))
        })
    }
}

fn copy_source_symlink(
    source_directory: &cap_std::fs::Dir,
    source_name: &OsStr,
    target_directory: &cap_std::fs::Dir,
    target_name: &OsStr,
    source: &Path,
    target: &Path,
    #[cfg(windows)] target_link_path: &Path,
) -> Result<()> {
    let link_text = source_directory
        .read_link_contents(source_name)
        .map_err(|error| {
            SourceMutationError::new(format!(
                "cannot read source symlink {}: {error}",
                source.display()
            ))
        })?;
    let source_metadata = source_directory
        .symlink_metadata(source_name)
        .map_err(|error| {
            SourceMutationError::new(format!(
                "cannot inspect source symlink {}: {error}",
                source.display()
            ))
        })?;
    #[cfg(windows)]
    let create_link = std::os::windows::fs::symlink_file(&link_text, target_link_path);
    #[cfg(not(windows))]
    let create_link = target_directory.symlink_contents(&link_text, target_name);
    create_link.map_err(|error| {
        SourceMutationError::new(format!(
            "cannot copy source symlink {} to {}: {error}",
            source.display(),
            target.display()
        ))
    })?;

    let source_atime = source_metadata.accessed().map_err(|error| {
        SourceMutationError::new(format!(
            "cannot read source symlink access time {}: {error}",
            source.display()
        ))
    })?;
    let source_mtime = source_metadata.modified().map_err(|error| {
        SourceMutationError::new(format!(
            "cannot read source symlink modification time {}: {error}",
            source.display()
        ))
    })?;
    target_directory
        .set_symlink_times(
            target_name,
            Some(SystemTimeSpec::from(source_atime)),
            Some(SystemTimeSpec::from(source_mtime)),
        )
        .map_err(|error| {
            SourceMutationError::new(format!(
                "cannot copy symlink times to {}: {error}",
                target.display()
            ))
        })?;
    copy_symlink_xattrs(source_directory, source_name, target_directory, target_name).map_err(
        |error| {
            SourceMutationError::new(format!(
                "cannot copy symlink extended attributes to {}: {error}",
                target.display()
            ))
        },
    )?;
    match target_directory.set_symlink_permissions(target_name, source_metadata.permissions()) {
        Ok(()) => {}
        Err(error) if error.kind() == io::ErrorKind::Unsupported => {}
        Err(error) => {
            return Err(SourceMutationError::new(format!(
                "cannot copy symlink mode to {}: {error}",
                target.display()
            )))
        }
    }
    copy_symlink_flags(
        source_directory,
        source_name,
        target_directory,
        target_name,
        target,
    )
    .map_err(|error| {
        SourceMutationError::new(format!(
            "cannot copy symlink flags to {}: {error}",
            target.display()
        ))
    })
}

fn set_open_file_times(
    target: &cap_std::fs::File,
    atime: cap_std::time::SystemTime,
    mtime: cap_std::time::SystemTime,
) -> io::Result<()> {
    let target = target.try_clone()?.into_std();
    let times = std::fs::FileTimes::new()
        .set_accessed(atime.into_std())
        .set_modified(mtime.into_std());
    target.set_times(times)
}

#[cfg(target_os = "linux")]
fn copy_symlink_xattrs(
    source_directory: &cap_std::fs::Dir,
    source_name: &OsStr,
    target_directory: &cap_std::fs::Dir,
    target_name: &OsStr,
) -> io::Result<()> {
    use rustix::fs::{
        lgetxattr, lgetxattr_query, llistxattr, llistxattr_query, lsetxattr, XattrFlags,
    };
    use std::os::unix::ffi::OsStrExt;

    // Rustix's l* calls do not accept a directory fd. `/proc/self/fd/N`
    // anchors the parent directory, and the validated basename remains the
    // terminal no-follow component. Both Dir handles stay borrowed until all
    // operations finish; if procfs is unavailable, propagate that error.
    let source_path = anchored_symlink_xattr_path(source_directory, source_name)?;
    let target_path = anchored_symlink_xattr_path(target_directory, target_name)?;
    let names = match llistxattr_query(&source_path) {
        Ok(length) => {
            let mut buffer = vec![0; length];
            let written = match llistxattr(&source_path, &mut buffer) {
                Ok(written) => written,
                Err(error) if ignored_xattr_list_error(error) => return Ok(()),
                Err(error) => return Err(error.into()),
            };
            buffer.truncate(written);
            buffer
        }
        Err(error) if ignored_xattr_list_error(error) => return Ok(()),
        Err(error) => return Err(error.into()),
    };

    for name in names
        .split(|byte| *byte == 0)
        .filter(|name| !name.is_empty())
    {
        let name = OsStr::from_bytes(name);
        let value = match lgetxattr_query(&source_path, name) {
            Ok(length) => {
                let mut buffer = vec![0; length];
                match lgetxattr(&source_path, name, &mut buffer) {
                    Ok(written) => {
                        buffer.truncate(written);
                        buffer
                    }
                    Err(error) if ignored_xattr_attribute_error(error) => continue,
                    Err(error) => return Err(error.into()),
                }
            }
            Err(error) if ignored_xattr_attribute_error(error) => continue,
            Err(error) => return Err(error.into()),
        };
        match lsetxattr(&target_path, name, &value, XattrFlags::empty()) {
            Ok(()) => {}
            Err(error) if ignored_xattr_attribute_error(error) => {}
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}

#[cfg(target_os = "linux")]
fn anchored_symlink_xattr_path(directory: &cap_std::fs::Dir, name: &OsStr) -> io::Result<PathBuf> {
    use std::os::fd::AsRawFd;

    let mut components = Path::new(name).components();
    match components.next() {
        Some(Component::Normal(component)) if component == name && components.next().is_none() => {}
        _ => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "symlink xattr name must be one directory entry",
            ))
        }
    }
    let mut path = PathBuf::from(format!("/proc/self/fd/{}", directory.as_raw_fd()));
    path.push(name);
    Ok(path)
}

#[cfg(target_os = "macos")]
fn copy_symlink_xattrs(
    source_directory: &cap_std::fs::Dir,
    source_name: &OsStr,
    target_directory: &cap_std::fs::Dir,
    target_name: &OsStr,
) -> io::Result<()> {
    use rustix::fs::{openat, Mode, OFlags};

    let link_flags = OFlags::SYMLINK | OFlags::RDONLY | OFlags::CLOEXEC;
    let source = openat(source_directory, source_name, link_flags, Mode::empty())
        .map_err(io::Error::from)?;
    let target = openat(target_directory, target_name, link_flags, Mode::empty())
        .map_err(io::Error::from)?;
    copy_descriptor_xattrs(&source, &target)
}

#[cfg(windows)]
fn copy_symlink_xattrs(
    _source_directory: &cap_std::fs::Dir,
    _source_name: &OsStr,
    _target_directory: &cap_std::fs::Dir,
    _target_name: &OsStr,
) -> io::Result<()> {
    // Windows does not expose Python os xattrs; the old route uses CopyFile2.
    Ok(())
}

#[cfg(all(unix, not(any(target_os = "linux", target_os = "macos"))))]
fn copy_symlink_xattrs(
    _source_directory: &cap_std::fs::Dir,
    _source_name: &OsStr,
    _target_directory: &cap_std::fs::Dir,
    _target_name: &OsStr,
) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "safe descriptor-relative symlink xattr copy is unavailable on this target",
    ))
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
fn copy_regular_file_xattrs(
    source: &cap_std::fs::File,
    target: &cap_std::fs::File,
) -> io::Result<()> {
    copy_descriptor_xattrs(source, target)
}

#[cfg(windows)]
fn copy_regular_file_xattrs(
    _source: &cap_std::fs::File,
    _target: &cap_std::fs::File,
) -> io::Result<()> {
    // Windows does not expose Python os xattrs; the old route uses CopyFile2.
    Ok(())
}

#[cfg(all(unix, not(any(target_os = "linux", target_os = "macos"))))]
fn copy_regular_file_xattrs(
    _source: &cap_std::fs::File,
    _target: &cap_std::fs::File,
) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "safe descriptor-relative xattr copy is unavailable on this target",
    ))
}

#[cfg(target_os = "macos")]
fn copy_symlink_flags(
    source_directory: &cap_std::fs::Dir,
    source_name: &OsStr,
    target_directory: &cap_std::fs::Dir,
    target_name: &OsStr,
    _target: &Path,
) -> io::Result<()> {
    use cap_std::io_lifetimes::AsFd;
    use rustix::fs::{openat, statat, AtFlags, Mode, OFlags};

    let source_stat = statat(source_directory, source_name, AtFlags::SYMLINK_NOFOLLOW)?;
    // O_SYMLINK opens the symlink itself; parent handle and final-link identity
    // stay anchored across the borrowed fchflags call.
    let target_link = openat(
        target_directory,
        target_name,
        OFlags::SYMLINK | OFlags::RDONLY | OFlags::CLOEXEC,
        Mode::empty(),
    )?;
    match fchflags_borrowed_fd(target_link.as_fd(), source_stat.st_flags as u64) {
        Ok(()) => Ok(()),
        Err(error) if is_unsupported_file_flags(&error) => Ok(()),
        Err(error) => Err(error),
    }
}

#[cfg(any(
    target_os = "freebsd",
    target_os = "netbsd",
    target_os = "openbsd",
    target_os = "dragonfly"
))]
fn copy_symlink_flags(
    source_directory: &cap_std::fs::Dir,
    source_name: &OsStr,
    _target_directory: &cap_std::fs::Dir,
    _target_name: &OsStr,
    source: &Path,
) -> io::Result<()> {
    use rustix::fs::{statat, AtFlags};

    // The locked safe APIs can read BSD symlink flags but provide no anchored
    // no-follow setter. Do not claim parity for a nonzero source flag.
    let metadata = statat(source_directory, source_name, AtFlags::SYMLINK_NOFOLLOW)
        .map_err(io::Error::from)?;
    if metadata.st_flags != 0 {
        return Err(io::Error::new(
            io::ErrorKind::Unsupported,
            format!(
                "source symlink flags cannot be copied safely: {}",
                source.display()
            ),
        ));
    }
    Ok(())
}

#[cfg(any(target_os = "linux", windows))]
fn copy_symlink_flags(
    _source_directory: &cap_std::fs::Dir,
    _source_name: &OsStr,
    _target_directory: &cap_std::fs::Dir,
    _target_name: &OsStr,
    _source: &Path,
) -> io::Result<()> {
    Ok(())
}

#[cfg(any(
    target_os = "macos",
    target_os = "freebsd",
    target_os = "netbsd",
    target_os = "openbsd",
    target_os = "dragonfly"
))]
fn copy_regular_file_flags(
    source: &cap_std::fs::File,
    target: &cap_std::fs::File,
) -> io::Result<()> {
    let source_stat = rustix::fs::fstat(source).map_err(io::Error::from)?;
    let flags = source_stat.st_flags as u64;
    let result = set_file_flags(target, flags);
    match result {
        Ok(()) => Ok(()),
        Err(error) if is_unsupported_file_flags(&error) => Ok(()),
        Err(error) => Err(error),
    }
}

#[cfg(any(target_os = "macos", target_os = "openbsd"))]
type NativeFileFlags = nix::libc::c_uint;

#[cfg(any(target_os = "freebsd", target_os = "netbsd", target_os = "dragonfly"))]
type NativeFileFlags = nix::libc::c_ulong;

#[cfg(any(
    target_os = "macos",
    target_os = "freebsd",
    target_os = "netbsd",
    target_os = "openbsd",
    target_os = "dragonfly"
))]
fn set_file_flags(target: &cap_std::fs::File, flags: u64) -> io::Result<()> {
    use cap_std::io_lifetimes::{AsFd, BorrowedFd};

    let borrowed_fd: BorrowedFd<'_> = target.as_fd();
    fchflags_borrowed_fd(borrowed_fd, flags)
}

#[cfg(any(
    target_os = "macos",
    target_os = "freebsd",
    target_os = "netbsd",
    target_os = "openbsd",
    target_os = "dragonfly"
))]
fn fchflags_borrowed_fd(
    borrowed_fd: cap_std::io_lifetimes::BorrowedFd<'_>,
    flags: u64,
) -> io::Result<()> {
    use std::os::fd::AsRawFd;

    let flags = NativeFileFlags::try_from(flags)
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "file flags do not fit target"))?;
    let raw_fd = borrowed_fd.as_raw_fd();
    // SAFETY: fchflags has only this borrowed descriptor number and integer
    // flags. The caller keeps the owner alive for the call; this wrapper does
    // not own, close, retain, or store the descriptor and passes no pointers.
    let result = unsafe { nix::libc::fchflags(raw_fd, flags) };
    if result == -1 {
        // Capture errno immediately after the sentinel return.
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}

#[cfg(any(
    target_os = "macos",
    target_os = "freebsd",
    target_os = "netbsd",
    target_os = "openbsd",
    target_os = "dragonfly"
))]
fn is_unsupported_file_flags(error: &io::Error) -> bool {
    let Some(error) = error.raw_os_error() else {
        return false;
    };
    error == nix::libc::EOPNOTSUPP || error == nix::libc::ENOTSUP
}

#[cfg(not(any(
    target_os = "macos",
    target_os = "freebsd",
    target_os = "netbsd",
    target_os = "openbsd",
    target_os = "dragonfly"
)))]
fn copy_regular_file_flags(
    _source: &cap_std::fs::File,
    _target: &cap_std::fs::File,
) -> io::Result<()> {
    Ok(())
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
fn copy_descriptor_xattrs<Source, Target>(source: &Source, target: &Target) -> io::Result<()>
where
    Source: rustix::fd::AsFd,
    Target: rustix::fd::AsFd,
{
    use rustix::fs::{
        fgetxattr, fgetxattr_query, flistxattr, flistxattr_query, fsetxattr, XattrFlags,
    };
    use std::os::unix::ffi::OsStrExt;

    let names = match flistxattr_query(source) {
        Ok(length) => {
            let mut buffer = vec![0; length];
            let written = match flistxattr(source, &mut buffer) {
                Ok(written) => written,
                Err(error) if ignored_xattr_list_error(error) => return Ok(()),
                Err(error) => return Err(error.into()),
            };
            buffer.truncate(written);
            buffer
        }
        Err(error) if ignored_xattr_list_error(error) => return Ok(()),
        Err(error) => return Err(error.into()),
    };

    for name in names
        .split(|byte| *byte == 0)
        .filter(|name| !name.is_empty())
    {
        let name = OsStr::from_bytes(name);
        let value = match fgetxattr_query(source, name) {
            Ok(length) => {
                let mut buffer = vec![0; length];
                match fgetxattr(source, name, &mut buffer) {
                    Ok(written) => {
                        buffer.truncate(written);
                        buffer
                    }
                    Err(error) if ignored_xattr_attribute_error(error) => continue,
                    Err(error) => return Err(error.into()),
                }
            }
            Err(error) if ignored_xattr_attribute_error(error) => continue,
            Err(error) => return Err(error.into()),
        };
        match fsetxattr(target, name, &value, XattrFlags::empty()) {
            Ok(()) => {}
            Err(error) if ignored_xattr_attribute_error(error) => continue,
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
fn ignored_xattr_list_error(error: rustix::io::Errno) -> bool {
    use rustix::io::Errno;

    // shutil._copyxattr treats these three listxattr errors as an absent
    // listing. Permission errors are only ignored for individual attributes.
    error == Errno::NOTSUP || error == Errno::NODATA || error == Errno::INVAL
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
fn ignored_xattr_attribute_error(error: rustix::io::Errno) -> bool {
    use rustix::io::Errno;

    ignored_xattr_list_error(error) || error == Errno::PERM || error == Errno::ACCESS
}

fn open_file_parent_nofollow(
    root: &Path,
    relative: &Path,
    create_missing: bool,
) -> io::Result<(cap_std::fs::Dir, OsString)> {
    let mut components = relative.components().collect::<Vec<_>>();
    let Some(Component::Normal(name)) = components.pop() else {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "source mutation target must name a file",
        ));
    };
    let parent = components
        .into_iter()
        .map(|component| match component {
            Component::Normal(name) => Ok(name.to_os_string()),
            _ => Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "unsafe source mutation parent path",
            )),
        })
        .collect::<io::Result<Vec<_>>>()?;
    let mut directory = open_root_nofollow(root)?;
    for part in parent {
        match directory.open_dir_nofollow(&part) {
            Ok(child) => directory = child,
            Err(error) if create_missing && error.kind() == io::ErrorKind::NotFound => {
                match directory.create_dir(&part) {
                    Ok(()) => {}
                    Err(create_error) if create_error.kind() == io::ErrorKind::AlreadyExists => {}
                    Err(create_error) => return Err(create_error),
                }
                directory = directory.open_dir_nofollow(&part)?;
            }
            Err(error) => return Err(error),
        }
    }
    Ok((directory, name.to_os_string()))
}

#[cfg(windows)]
fn open_file_parent_chain_nofollow(
    root: &Path,
    relative: &Path,
    create_missing: bool,
) -> io::Result<(Vec<cap_std::fs::Dir>, OsString, PathBuf)> {
    let mut components = relative.components().collect::<Vec<_>>();
    let Some(Component::Normal(name)) = components.pop() else {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "source mutation target must name a file",
        ));
    };
    let mut target_path = root.to_path_buf();
    for component in relative.components() {
        let Component::Normal(name) = component else {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "unsafe source mutation target path",
            ));
        };
        target_path.push(name);
    }

    let parent = components
        .into_iter()
        .map(|component| match component {
            Component::Normal(name) => Ok(name.to_os_string()),
            _ => Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "unsafe source mutation parent path",
            )),
        })
        .collect::<io::Result<Vec<_>>>()?;
    let mut directories = open_root_nofollow_chain(root)?;
    for part in parent {
        let next = match directories
            .last()
            .expect("root chain contains the volume root")
            .open_dir_nofollow(&part)
        {
            Ok(child) => child,
            Err(error) if create_missing && error.kind() == io::ErrorKind::NotFound => {
                let parent = directories
                    .last()
                    .expect("root chain contains the volume root");
                match parent.create_dir(&part) {
                    Ok(()) => {}
                    Err(create_error) if create_error.kind() == io::ErrorKind::AlreadyExists => {}
                    Err(create_error) => return Err(create_error),
                }
                parent.open_dir_nofollow(&part)?
            }
            Err(error) => return Err(error),
        };
        directories.push(next);
    }
    Ok((directories, name.to_os_string(), target_path))
}

fn same_file(left: &cap_std::fs::Metadata, right: &cap_std::fs::Metadata) -> bool {
    left.dev() == right.dev() && left.ino() == right.ino()
}

fn relative_path_as_posix(path: &Path) -> String {
    let components = path
        .components()
        .map(|component| component.as_os_str().to_string_lossy().into_owned())
        .collect::<Vec<_>>();
    if components.is_empty() {
        ".".to_string()
    } else {
        components.join("/")
    }
}

fn relative_path_is_allowed(relative: &Path, allowed_paths: &[PathBuf]) -> bool {
    allowed_paths.iter().any(|allowed| {
        allowed.as_os_str().is_empty() || relative == allowed || relative.starts_with(allowed)
    })
}

fn reject_unknown_fields(object: &Map<String, Value>) -> Result<()> {
    const FIELDS: [&str; 3] = ["allowed_paths", "purpose", "authority"];
    let unknown = object
        .keys()
        .filter(|key| !FIELDS.contains(&key.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    if unknown.is_empty() {
        Ok(())
    } else {
        Err(SourceMutationError::new(
            "mutation capability fields must be allowed_paths, purpose, authority",
        ))
    }
}

fn parse_allowed_paths(object: &Map<String, Value>, source_root: &Path) -> Result<Vec<PathBuf>> {
    let allowed = object
        .get("allowed_paths")
        .and_then(Value::as_array)
        .filter(|items| !items.is_empty())
        .ok_or_else(|| SourceMutationError::new("mutation capability allowed_paths is required"))?;
    let mut normalized = BTreeSet::new();
    for item in allowed {
        let item = item
            .as_str()
            .filter(|value| !value.trim().is_empty())
            .ok_or_else(|| SourceMutationError::new("mutation capability path must be text"))?;
        if item.starts_with('/')
            || Path::new(item).is_absolute()
            || Path::new(item)
                .components()
                .any(|component| matches!(component, Component::Prefix(_) | Component::RootDir))
            || cfg!(windows) && item.contains('\\')
        {
            return Err(SourceMutationError::new(format!(
                "unsafe mutation capability path: {item}"
            )));
        }
        let mut parts = Vec::new();
        for part in item.split('/') {
            match part {
                "" | "." => {}
                ".." => {
                    return Err(SourceMutationError::new(format!(
                        "unsafe mutation capability path: {item}"
                    )))
                }
                part => parts.push(part),
            }
        }
        let relative = PathBuf::from(parts.join("/"));
        let lexical = source_root.join(&relative);
        if !candidate_resolves_under(source_root, &lexical)? {
            return Err(SourceMutationError::new(format!(
                "mutation capability escapes source: {item}"
            )));
        }
        normalized.insert(relative);
    }
    Ok(normalized.into_iter().collect())
}

fn required_label(object: &Map<String, Value>, field: &str) -> Result<String> {
    object
        .get(field)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .map(str::to_string)
        .ok_or_else(|| SourceMutationError::new(format!("mutation capability {field} is required")))
}

fn candidate_resolves_under(root: &Path, path: &Path) -> Result<bool> {
    let resolved = resolve_with_missing(path)?;
    Ok(resolved == root || resolved.starts_with(root))
}

fn reject_symlink_components(root: &Path, path: &Path) -> Result<()> {
    let relative = path.strip_prefix(root).map_err(|_| {
        SourceMutationError::new(format!(
            "mutation target is outside source: {}",
            path.display()
        ))
    })?;
    let mut cursor = root.to_path_buf();
    for component in relative.components() {
        let Component::Normal(part) = component else {
            return Err(SourceMutationError::new(format!(
                "unsafe mutation target: {}",
                path.display()
            )));
        };
        cursor.push(part);
        match fs::symlink_metadata(&cursor) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(SourceMutationError::new(format!(
                    "mutation target contains symlink component: {}",
                    cursor.display()
                )))
            }
            Ok(_) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(SourceMutationError::new(format!(
                    "cannot inspect mutation target {}: {error}",
                    cursor.display()
                )))
            }
        }
    }
    Ok(())
}

fn resolve_with_missing(path: &Path) -> Result<PathBuf> {
    let mut cursor = path.to_path_buf();
    let mut missing = Vec::new();
    loop {
        match fs::canonicalize(&cursor) {
            Ok(mut resolved) => {
                for component in missing.iter().rev() {
                    resolved.push(component);
                }
                return Ok(resolved);
            }
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
                ) =>
            {
                let name = cursor.file_name().ok_or_else(|| {
                    SourceMutationError::new(format!(
                        "cannot resolve mutation path: {}",
                        path.display()
                    ))
                })?;
                missing.push(name.to_os_string());
                cursor = cursor
                    .parent()
                    .ok_or_else(|| {
                        SourceMutationError::new(format!(
                            "cannot resolve mutation path: {}",
                            path.display()
                        ))
                    })?
                    .to_path_buf();
            }
            Err(error) => {
                return Err(SourceMutationError::new(format!(
                    "cannot resolve mutation path {}: {error}",
                    path.display()
                )))
            }
        }
    }
}

#[cfg(windows)]
fn open_root_nofollow(root: &Path) -> io::Result<cap_std::fs::Dir> {
    open_root_nofollow_chain(root)?
        .pop()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "empty source root chain"))
}

#[cfg(windows)]
fn open_root_nofollow_chain(root: &Path) -> io::Result<Vec<cap_std::fs::Dir>> {
    let mut components = root.components();
    let prefix = match components.next() {
        Some(Component::Prefix(prefix)) => prefix,
        _ => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "absolute source root requires a volume prefix",
            ))
        }
    };
    if !matches!(components.next(), Some(Component::RootDir)) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "absolute source root requires a volume root",
        ));
    }
    let mut volume_root = PathBuf::from(prefix.as_os_str());
    volume_root.push(std::path::MAIN_SEPARATOR.to_string());
    let mut directories = vec![cap_std::fs::Dir::open_ambient_dir(
        &volume_root,
        cap_std::ambient_authority(),
    )?];
    for component in components {
        match component {
            Component::Normal(name) => {
                let child = directories
                    .last()
                    .expect("root chain contains the volume root")
                    .open_dir_nofollow(name)?;
                directories.push(child);
            }
            Component::RootDir => {}
            Component::CurDir | Component::ParentDir | Component::Prefix(_) => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "source root path is not canonical",
                ))
            }
        }
    }
    Ok(directories)
}

#[cfg(not(windows))]
fn open_root_nofollow(root: &Path) -> io::Result<cap_std::fs::Dir> {
    let mut components = root.components();
    if !matches!(components.next(), Some(Component::RootDir)) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "absolute source root requires a root component",
        ));
    }
    let mut directory =
        cap_std::fs::Dir::open_ambient_dir(Path::new("/"), cap_std::ambient_authority())?;
    for component in components {
        match component {
            Component::Normal(name) => directory = directory.open_dir_nofollow(name)?,
            Component::RootDir => {}
            Component::CurDir | Component::ParentDir | Component::Prefix(_) => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "source root path is not canonical",
                ))
            }
        }
    }
    Ok(directory)
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;

    #[test]
    fn allowed_path_comparison_keeps_invalid_utf8_component_identity() {
        use std::os::unix::ffi::OsStringExt;

        let allowed = PathBuf::from("docs").join("�");
        let valid_target = allowed.join("guide.md");
        let invalid_target = PathBuf::from("docs")
            .join(std::ffi::OsString::from_vec(vec![0xff]))
            .join("guide.md");

        assert!(relative_path_is_allowed(
            &valid_target,
            std::slice::from_ref(&allowed)
        ));
        assert!(!relative_path_is_allowed(
            &invalid_target,
            std::slice::from_ref(&allowed)
        ));
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn copy_file_with_metadata_preserves_nonzero_regular_and_symlink_flags() {
        use cap_std::io_lifetimes::AsFd;
        use rustix::fs::{fstat, openat, statat, AtFlags, Mode, OFlags};
        use std::os::unix::fs::symlink;
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
                    "agent-canon-macos-copy-flags-{}-{sequence}-{nonce}",
                    std::process::id()
                ));
                fs::create_dir_all(path.join("docs")).expect("copy flag root is created");
                Self(path.canonicalize().expect("copy flag root is canonical"))
            }
        }

        impl Drop for TempRoot {
            fn drop(&mut self) {
                let _ = fs::remove_dir_all(&self.0);
            }
        }

        let root = TempRoot::new();
        let docs_path = root.0.join("docs");
        fs::write(docs_path.join("regular-source.md"), "regular source\n")
            .expect("regular source is written");
        fs::write(docs_path.join("payload.md"), "symlink payload\n")
            .expect("symlink payload is written");
        symlink("payload.md", docs_path.join("symlink-source.md"))
            .expect("source symlink is created");

        let source_root =
            cap_std::fs::Dir::open_ambient_dir(&docs_path, cap_std::ambient_authority())
                .expect("source directory is opened");
        let mut read_options = cap_std::fs::OpenOptions::new();
        read_options.read(true);
        let regular_source = source_root
            .open_with("regular-source.md", &read_options)
            .expect("regular source is opened");
        let flags = nix::libc::UF_NODUMP as u64;
        set_file_flags(&regular_source, flags).expect("regular source flag is set");
        assert_eq!(
            fstat(&regular_source).unwrap().st_flags as u64 & flags,
            flags,
            "fixture starts with the requested nonzero regular-file flag"
        );

        let source_link = openat(
            &source_root,
            "symlink-source.md",
            OFlags::SYMLINK | OFlags::RDONLY | OFlags::CLOEXEC,
            Mode::empty(),
        )
        .expect("source symlink opens without following its target");
        fchflags_borrowed_fd(source_link.as_fd(), flags)
            .expect("source symlink flag is set through its link descriptor");
        assert_eq!(
            statat(&source_root, "symlink-source.md", AtFlags::SYMLINK_NOFOLLOW)
                .unwrap()
                .st_flags as u64
                & flags,
            flags,
            "fixture starts with the requested nonzero symlink flag"
        );

        let capability_json = serde_json::json!({
            "allowed_paths": ["docs/regular-copy.md", "docs/symlink-copy.md"],
            "purpose": "copy-flag-test",
            "authority": "issue-1630"
        });
        let capability = SourceMutationCapability::from_json(
            &root.0,
            Some(&serde_json::to_string(&capability_json).unwrap()),
        )
        .expect("exact copy capability is created");
        let regular_target = docs_path.join("regular-copy.md");
        let symlink_target = docs_path.join("symlink-copy.md");

        capability
            .copy_file_with_metadata(&docs_path.join("regular-source.md"), &regular_target)
            .expect("regular file copy succeeds");
        capability
            .copy_file_with_metadata(&docs_path.join("symlink-source.md"), &symlink_target)
            .expect("symlink copy succeeds");

        let regular_target_file = source_root
            .open_with("regular-copy.md", &read_options)
            .expect("regular target is opened");
        assert_eq!(
            fstat(&regular_target_file).unwrap().st_flags as u64 & flags,
            flags,
            "copy2-style regular copy preserves nonzero file flags"
        );
        assert_eq!(
            statat(&source_root, "symlink-copy.md", AtFlags::SYMLINK_NOFOLLOW)
                .unwrap()
                .st_flags as u64
                & flags,
            flags,
            "copy2-style symlink copy preserves nonzero link flags"
        );
    }
}

#[cfg(all(test, windows))]
mod windows_tests {
    use super::*;
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
                "agent-canon-source-chain-{}-{sequence}-{nonce}",
                std::process::id()
            ));
            fs::create_dir_all(path.join("docs/parent"))
                .expect("target ancestor fixture is created");
            Self(path.canonicalize().expect("target root is canonical"))
        }
    }

    impl Drop for TempRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn target_parent_chain_blocks_ancestor_rename_until_released() {
        let root = TempRoot::new();
        let relative = Path::new("docs/parent/link.md");
        let (directories, name, target_path) =
            open_file_parent_chain_nofollow(&root.0, relative, false)
                .expect("target directory chain opens");
        assert_eq!(name, OsStr::new("link.md"));
        assert_eq!(
            target_path,
            root.0.join("docs").join("parent").join("link.md")
        );
        let renamed = root.0.join("docs-renamed");

        assert!(
            fs::rename(root.0.join("docs"), &renamed).is_err(),
            "held non-delete-share directory handles block ancestor rename"
        );

        drop(directories);
        fs::rename(root.0.join("docs"), renamed)
            .expect("ancestor can be renamed after the chain is released");
    }
}
