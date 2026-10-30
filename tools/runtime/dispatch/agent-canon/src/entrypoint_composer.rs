//! Deterministic composition of the portable and consumer-owned root guidance.

use sha2::{Digest, Sha256};
use std::fmt;
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

const MANAGED_MARKER: &[u8] = b"<!-- agent-canon:consumer-root-agents:v1 -->\n";
const BASE_START: &[u8] = b"<!-- agent-canon:consumer-root-base:start -->\n";
const BASE_END: &[u8] = b"<!-- agent-canon:consumer-root-base:end -->\n";
const SPECIFIC_START: &[u8] = b"<!-- agent-canon:consumer-root-specific:start -->\n";
const SPECIFIC_END: &[u8] = b"<!-- agent-canon:consumer-root-specific:end -->\n";
const SEPARATOR: &[u8] = b"\n";

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ComposeError {
    pub(crate) code: &'static str,
    pub(crate) detail: String,
}

impl ComposeError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for ComposeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "ENTRYPOINT_COMPOSE_ERROR={}:{}",
            self.code, self.detail
        )
    }
}

impl std::error::Error for ComposeError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Composition {
    pub(crate) source_commit: String,
    pub(crate) base: Vec<u8>,
    pub(crate) specific: Vec<u8>,
}

impl Composition {
    pub(crate) fn base_sha256(&self) -> String {
        digest_hex(&self.base)
    }

    pub(crate) fn specific_sha256(&self) -> String {
        digest_hex(&self.specific)
    }

    pub(crate) fn render(&self) -> Vec<u8> {
        let mut output = Vec::with_capacity(
            MANAGED_MARKER.len()
                + 240
                + self.base.len()
                + self.specific.len()
                + BASE_START.len()
                + BASE_END.len()
                + SPECIFIC_START.len()
                + SPECIFIC_END.len(),
        );
        output.extend_from_slice(MANAGED_MARKER);
        output.extend_from_slice(
            format!(
                "<!-- agent-canon:source-commit={} -->\n",
                self.source_commit
            )
            .as_bytes(),
        );
        output.extend_from_slice(
            format!("<!-- agent-canon:base-sha256={} -->\n", self.base_sha256()).as_bytes(),
        );
        output.extend_from_slice(
            format!("<!-- agent-canon:base-bytes={} -->\n", self.base.len()).as_bytes(),
        );
        output.extend_from_slice(
            format!(
                "<!-- agent-canon:specific-sha256={} -->\n",
                self.specific_sha256()
            )
            .as_bytes(),
        );
        output.extend_from_slice(
            format!(
                "<!-- agent-canon:specific-bytes={} -->\n",
                self.specific.len()
            )
            .as_bytes(),
        );
        output.extend_from_slice(BASE_START);
        output.extend_from_slice(&self.base);
        output.extend_from_slice(SEPARATOR);
        output.extend_from_slice(BASE_END);
        output.extend_from_slice(SPECIFIC_START);
        output.extend_from_slice(&self.specific);
        output.extend_from_slice(SEPARATOR);
        output.extend_from_slice(SPECIFIC_END);
        output
    }
}

fn digest_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn valid_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn read_regular(path: &Path, label: &str) -> Result<Vec<u8>, ComposeError> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            return Err(ComposeError::new(
                "missing",
                format!("{label}={}", path.display()),
            ))
        }
        Err(error) => {
            return Err(ComposeError::new(
                "read",
                format!("{label}={}:{}", path.display(), error),
            ))
        }
    };
    if metadata.file_type().is_symlink() {
        return Err(ComposeError::new(
            "symlink",
            format!("{label}={}", path.display()),
        ));
    }
    if !metadata.is_file() {
        return Err(ComposeError::new(
            "type",
            format!("{label}={}", path.display()),
        ));
    }
    fs::read(path)
        .map_err(|error| ComposeError::new("read", format!("{label}={}:{}", path.display(), error)))
}

fn source_commit(source_root: &Path) -> Result<String, ComposeError> {
    let metadata = fs::symlink_metadata(source_root)
        .map_err(|_| ComposeError::new("source-root", source_root.display().to_string()))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(ComposeError::new(
            "source-root",
            source_root.display().to_string(),
        ));
    }
    let result = Command::new("git")
        .arg("-C")
        .arg(source_root)
        .arg("rev-parse")
        .arg("HEAD")
        .output()
        .map_err(|error| ComposeError::new("source-commit-unavailable", error.to_string()))?;
    let commit = String::from_utf8_lossy(&result.stdout).trim().to_owned();
    if !result.status.success() || !valid_hex(&commit, 40) {
        let detail = String::from_utf8_lossy(&result.stderr).trim().to_owned();
        return Err(ComposeError::new(
            "source-commit-unavailable",
            if detail.is_empty() {
                source_root.display().to_string()
            } else {
                detail
            },
        ));
    }
    Ok(commit)
}

fn metadata_value(line: &[u8], prefix: &[u8], label: &'static str) -> Result<String, ComposeError> {
    const SUFFIX: &[u8] = b" -->\n";
    if !line.starts_with(prefix) || !line.ends_with(SUFFIX) {
        return Err(ComposeError::new("partial", label));
    }
    let value = &line[prefix.len()..line.len() - SUFFIX.len()];
    if value.is_empty() || !value.is_ascii() {
        return Err(ComposeError::new("partial", label));
    }
    Ok(String::from_utf8(value.to_vec()).expect("ASCII was checked"))
}

fn parse_count(value: &str, label: &'static str) -> Result<usize, ComposeError> {
    if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(ComposeError::new("partial", label));
    }
    value
        .parse()
        .map_err(|_| ComposeError::new("partial", label))
}

pub(crate) fn parse_marked(data: &[u8]) -> Result<Composition, ComposeError> {
    if !data.starts_with(MANAGED_MARKER) {
        return Err(ComposeError::new(
            "collision",
            "output is not a managed consumer AGENTS.md",
        ));
    }
    let fields: [(&[u8], &'static str); 5] = [
        (b"<!-- agent-canon:source-commit=", "source-commit"),
        (b"<!-- agent-canon:base-sha256=", "base-sha256"),
        (b"<!-- agent-canon:base-bytes=", "base-bytes"),
        (b"<!-- agent-canon:specific-sha256=", "specific-sha256"),
        (b"<!-- agent-canon:specific-bytes=", "specific-bytes"),
    ];
    let mut cursor = MANAGED_MARKER.len();
    let mut values = Vec::with_capacity(fields.len());
    for (prefix, label) in fields {
        let relative_end = data[cursor..]
            .iter()
            .position(|byte| *byte == b'\n')
            .ok_or_else(|| ComposeError::new("partial", label))?;
        let end = cursor + relative_end + 1;
        values.push(metadata_value(&data[cursor..end], prefix, label)?);
        cursor = end;
    }
    let commit = &values[0];
    if !valid_hex(commit, 40) {
        return Err(ComposeError::new("partial", "source-commit"));
    }
    if !valid_hex(&values[1], 64) {
        return Err(ComposeError::new("partial", "base-sha256"));
    }
    if !valid_hex(&values[3], 64) {
        return Err(ComposeError::new("partial", "specific-sha256"));
    }
    let base_size = parse_count(&values[2], "base-bytes")?;
    let specific_size = parse_count(&values[4], "specific-bytes")?;
    if !data[cursor..].starts_with(BASE_START) {
        return Err(ComposeError::new("partial", "base-start"));
    }
    cursor += BASE_START.len();
    let base_end = cursor
        .checked_add(base_size)
        .filter(|end| *end <= data.len())
        .ok_or_else(|| ComposeError::new("partial", "base-bytes"))?;
    let base = data[cursor..base_end].to_vec();
    cursor = base_end;
    let boundary = [SEPARATOR, BASE_END].concat();
    if !data[cursor..].starts_with(&boundary) {
        return Err(ComposeError::new("partial", "base-end"));
    }
    cursor += boundary.len();
    if !data[cursor..].starts_with(SPECIFIC_START) {
        return Err(ComposeError::new("partial", "specific-start"));
    }
    cursor += SPECIFIC_START.len();
    let specific_end = cursor
        .checked_add(specific_size)
        .filter(|end| *end <= data.len())
        .ok_or_else(|| ComposeError::new("partial", "specific-bytes"))?;
    let specific = data[cursor..specific_end].to_vec();
    cursor = specific_end;
    let ending = [SEPARATOR, SPECIFIC_END].concat();
    if data[cursor..] != ending {
        return Err(ComposeError::new("partial", "specific-end"));
    }
    if digest_hex(&base) != values[1] {
        return Err(ComposeError::new("partial", "base-digest"));
    }
    if digest_hex(&specific) != values[3] {
        return Err(ComposeError::new("partial", "specific-digest"));
    }
    Ok(Composition {
        source_commit: commit.clone(),
        base,
        specific,
    })
}

static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

fn write_atomic(output: &Path, bytes: &[u8]) -> Result<(), ComposeError> {
    let parent = output.parent().unwrap_or_else(|| Path::new("."));
    let parent_metadata = fs::symlink_metadata(parent).map_err(|error| {
        ComposeError::new("output-parent", format!("{}:{error}", parent.display()))
    })?;
    if parent_metadata.file_type().is_symlink() || !parent_metadata.is_dir() {
        return Err(ComposeError::new(
            "output-parent",
            parent.display().to_string(),
        ));
    }
    let name = output
        .file_name()
        .ok_or_else(|| ComposeError::new("write", format!("output={}", output.display())))?;
    let (temporary, mut file) = loop {
        let suffix = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        let temporary_name = format!(
            ".{}.{}.{}.tmp",
            name.to_string_lossy(),
            std::process::id(),
            suffix
        );
        let temporary = parent.join(temporary_name);
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)
        {
            Ok(file) => break (temporary, file),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => {
                return Err(ComposeError::new(
                    "write",
                    format!("output={}:{}", output.display(), error),
                ))
            }
        }
    };
    let result = (|| {
        file.write_all(bytes)?;
        file.flush()?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            file.set_permissions(fs::Permissions::from_mode(0o644))?;
        }
        drop(file);
        fs::rename(&temporary, output)
    })();
    let cleanup = fs::remove_file(&temporary);
    match (result, cleanup) {
        (Err(error), _) => Err(ComposeError::new(
            "write",
            format!("output={}:{}", output.display(), error),
        )),
        (Ok(()), Err(error)) if error.kind() != io::ErrorKind::NotFound => Err(ComposeError::new(
            "write",
            format!("output={}:{}", output.display(), error),
        )),
        _ => Ok(()),
    }
}

pub(crate) fn compose(
    base_path: &Path,
    specific_path: &Path,
    output_path: &Path,
    source_root: &Path,
) -> Result<(String, Composition), ComposeError> {
    let base = read_regular(base_path, "base")?;
    let specific = read_regular(specific_path, "specific")?;
    let composition = Composition {
        source_commit: source_commit(source_root)?,
        base,
        specific,
    };
    match fs::symlink_metadata(output_path) {
        Ok(metadata) if metadata.file_type().is_symlink() => {
            return Err(ComposeError::new(
                "symlink",
                format!("output={}", output_path.display()),
            ));
        }
        Ok(metadata) if !metadata.is_file() => {
            return Err(ComposeError::new(
                "type",
                format!("output={}", output_path.display()),
            ));
        }
        Ok(_) => {
            parse_marked(&fs::read(output_path).map_err(|error| {
                ComposeError::new(
                    "read",
                    format!("output={}:{}", output_path.display(), error),
                )
            })?)?;
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => {
            return Err(ComposeError::new(
                "read",
                format!("output={}:{}", output_path.display(), error),
            ));
        }
    }
    let status = if output_path.exists() {
        "updated"
    } else {
        "created"
    };
    write_atomic(output_path, &composition.render())?;
    Ok((status.to_owned(), composition))
}

/// Native implementation for the existing `compose-consumer-entrypoint` route.
pub(crate) fn run(args: &[String]) -> i32 {
    let mut base = None;
    let mut specific = None;
    let mut output = None;
    let mut source_root = PathBuf::from(".");
    let mut index = 0;
    while index < args.len() {
        let key = args[index].as_str();
        if matches!(key, "-h" | "--help") {
            println!("Compose a source-free consumer AGENTS.md from explicit inputs.\n\nUsage: agent-canon compose-consumer-entrypoint --base <path> --specific <path> --output <path> [--source-root <path>]");
            return 0;
        }
        let Some(value) = args.get(index + 1) else {
            eprintln!("ENTRYPOINT_COMPOSE_ERROR=arguments:missing value for {key}");
            return 2;
        };
        match key {
            "--base" => base = Some(PathBuf::from(value)),
            "--specific" => specific = Some(PathBuf::from(value)),
            "--output" => output = Some(PathBuf::from(value)),
            "--source-root" => source_root = PathBuf::from(value),
            _ => {
                eprintln!("ENTRYPOINT_COMPOSE_ERROR=arguments:unknown option {key}");
                return 2;
            }
        }
        index += 2;
    }
    let (Some(base), Some(specific), Some(output)) = (base, specific, output) else {
        eprintln!(
            "ENTRYPOINT_COMPOSE_ERROR=arguments:--base, --specific and --output are required"
        );
        return 2;
    };
    match compose(&base, &specific, &output, &source_root) {
        Ok((status, composition)) => {
            println!("ENTRYPOINT_COMPOSE_STATUS={status}");
            println!("ENTRYPOINT_COMPOSE_OUTPUT={}", output.display());
            println!(
                "ENTRYPOINT_COMPOSE_SOURCE_COMMIT={}",
                composition.source_commit
            );
            println!(
                "ENTRYPOINT_COMPOSE_BASE_SHA256={}",
                composition.base_sha256()
            );
            println!(
                "ENTRYPOINT_COMPOSE_SPECIFIC_SHA256={}",
                composition.specific_sha256()
            );
            0
        }
        Err(error) => {
            eprintln!("{error}");
            2
        }
    }
}
