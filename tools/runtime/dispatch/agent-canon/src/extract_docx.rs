// @dependency-start
// contract implementation
// responsibility Decomposes an authorized DOCX into a searchable, auditable reference bundle.
// upstream design ../../../../../documents/tools/extract_docx.md defines the bundle and CLI contract
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md defines native ownership and caller closure
// upstream implementation ../Cargo.toml selects ZIP offset detection, the native reader/codecs, XML, Unicode, and filesystem providers
// upstream implementation python_cli_integer.rs shares Python Unicode 15 digit classification
// downstream implementation ../tests/extract_docx_native.rs qualifies the XML parser and native DOCX projection
// downstream implementation ../../../../../tests/tools/test_extract_docx.py checks the public CLI and transaction behavior
// @dependency-end

use bzip2::read::BzDecoder;
use cap_fs_ext::{
    DirExt, FollowSymlinks, MetadataExt as CapabilityMetadataExt, OpenOptionsFollowExt,
};
use cap_std::fs::{Dir, DirBuilder, OpenOptions};
use expat::internal::parse::{Handler, HandlerSet, Parser, Status};
use icu_casemap::CaseMapper;
use icu_normalizer::ComposingNormalizer;
use lzma_rust2::LzmaReader;
use rawzip::{CompressionMethod, ZipArchive as RawZipArchive, ZipArchiveEntryWayfinder};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::env;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::path::{Component, Path, PathBuf};
#[cfg(not(unix))]
use std::time::SystemTime;

const SCHEMA_VERSION: u64 = 1;
const DOCUMENT_XML_MEMBER: &str = "word/document.xml";
const WORD_NAMESPACE: &str = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
const CHUNK_SIZE: usize = 1024 * 1024;
const LOCAL_HEADER_BUFFER_SIZE: usize = u16::MAX as usize * 2;
const UNSUPPORTED_ZIP_ENTRY_FLAGS: u16 = 0x0001 | 0x0020 | 0x0040;

#[derive(Clone, Debug, Eq, PartialEq)]
struct FileDigest {
    size_bytes: u64,
    sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct SourceStatIdentity {
    device: u64,
    inode: u64,
    size: u64,
    #[cfg(unix)]
    mtime_seconds: i64,
    #[cfg(unix)]
    mtime_nanoseconds: i64,
    #[cfg(unix)]
    ctime_seconds: i64,
    #[cfg(unix)]
    ctime_nanoseconds: i64,
    #[cfg(not(unix))]
    modified: SystemTime,
    #[cfg(not(unix))]
    created: Option<SystemTime>,
}

struct InputFile {
    parent: Dir,
    name: OsString,
    source_name: String,
    canonical_path: PathBuf,
}

struct ArchiveCoordinateReader<R> {
    inner: R,
    base_offset: u64,
    length: u64,
    position: u64,
}

impl<R: Read + Seek> ArchiveCoordinateReader<R> {
    fn new(mut inner: R, base_offset: u64) -> io::Result<Self> {
        let file_length = inner.seek(SeekFrom::End(0))?;
        let length = file_length.checked_sub(base_offset).ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "ZIP archive offset exceeds the input length",
            )
        })?;
        inner.seek(SeekFrom::Start(base_offset))?;
        Ok(Self {
            inner,
            base_offset,
            length,
            position: 0,
        })
    }

    fn physical_position(&self, logical_position: u64) -> io::Result<u64> {
        self.base_offset
            .checked_add(logical_position)
            .ok_or_else(|| {
                io::Error::new(io::ErrorKind::InvalidInput, "ZIP reader offset overflow")
            })
    }
}

impl<R: Read> Read for ArchiveCoordinateReader<R> {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        let remaining = self.length.saturating_sub(self.position);
        let requested = u64::try_from(buffer.len()).map_err(|_| {
            io::Error::new(
                io::ErrorKind::InvalidInput,
                "ZIP read buffer length overflow",
            )
        })?;
        let read_length = usize::try_from(remaining.min(requested))
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "ZIP read length overflow"))?;
        let read = self.inner.read(&mut buffer[..read_length])?;
        let read_count =
            u64::try_from(read).map_err(|_| io::Error::other("ZIP read byte count overflow"))?;
        self.position = self
            .position
            .checked_add(read_count)
            .ok_or_else(|| io::Error::other("ZIP reader position overflow"))?;
        Ok(read)
    }
}

impl<R: Read + Seek> Seek for ArchiveCoordinateReader<R> {
    fn seek(&mut self, position: SeekFrom) -> io::Result<u64> {
        let logical_position = match position {
            SeekFrom::Start(position) => i128::from(position),
            SeekFrom::Current(delta) => i128::from(self.position) + i128::from(delta),
            SeekFrom::End(delta) => i128::from(self.length) + i128::from(delta),
        };
        if !(0..=i128::from(u64::MAX)).contains(&logical_position) {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "ZIP seek is outside the representable range",
            ));
        }
        let logical_position = logical_position as u64;
        self.inner
            .seek(SeekFrom::Start(self.physical_position(logical_position)?))?;
        self.position = logical_position;
        Ok(logical_position)
    }
}

struct ArchiveMember {
    wayfinder: ZipArchiveEntryWayfinder,
    header_name: String,
    original_name: String,
    name: String,
    parts: Vec<String>,
    identity_parts: Vec<String>,
    is_directory: bool,
    size_bytes: u64,
    compression_method: CompressionMethod,
    central_flags: u16,
    local_header_offset: u64,
    next_header_offset: u64,
}

struct ArchiveIndex {
    base_offset: u64,
    members: Vec<ArchiveMember>,
}

struct RawMemberRecord {
    name: String,
    directory: bool,
    size_bytes: u64,
    sha256: Option<String>,
}

struct OutputReservation {
    parent: Dir,
    name: OsString,
    path: PathBuf,
    existed: bool,
    identity: Option<(u64, u64)>,
}

struct StagingDirectory {
    name: Option<String>,
    directory: Option<Dir>,
}

#[derive(Debug)]
enum XmlEvent {
    Start {
        name: Vec<u8>,
        attributes: Vec<(Vec<u8>, Vec<u8>)>,
    },
    End(Vec<u8>),
    Text(Vec<u8>),
}

#[derive(Default)]
struct XmlEventRecorder {
    events: Vec<XmlEvent>,
}

impl Handler for XmlEventRecorder {
    fn start_element(&mut self, name: &[u8], attributes: &[(&[u8], &[u8])], _: i32) {
        self.events.push(XmlEvent::Start {
            name: name.to_vec(),
            attributes: attributes
                .iter()
                .map(|(name, value)| (name.to_vec(), value.to_vec()))
                .collect(),
        });
    }

    fn end_element(&mut self, name: &[u8]) {
        self.events.push(XmlEvent::End(name.to_vec()));
    }

    fn character_data(&mut self, text: &[u8]) {
        if !text.is_empty() {
            self.events.push(XmlEvent::Text(text.to_vec()));
        }
    }
}

#[derive(Debug)]
struct XmlElement {
    name: String,
    attributes: Vec<(String, String)>,
    text: String,
    tail: String,
    children: Vec<usize>,
}

struct XmlDocument {
    elements: Vec<XmlElement>,
    root: usize,
}

pub fn extract_bundle(source: &Path, output_dir: &Path) -> Result<Value, String> {
    let input = resolve_input(source)?;
    let reservation = reserve_output_directory(output_dir)?;
    let mut staging = create_staging_directory(&reservation)?;

    let copied_source = {
        let staging_directory = staging
            .directory
            .as_ref()
            .expect("new staging directory has an open capability");
        copy_source_snapshot(&input, staging_directory)
    };
    let source_digest = match copied_source {
        Ok(digest) => digest,
        Err(error) => return Err(cleanup_staging(&reservation, &mut staging, error)),
    };
    finish_staged_bundle(&input, &reservation, &mut staging, &source_digest)
}

fn finish_staged_bundle(
    input: &InputFile,
    reservation: &OutputReservation,
    staging: &mut StagingDirectory,
    source_digest: &FileDigest,
) -> Result<Value, String> {
    let built_bundle = {
        let staging_directory = staging
            .directory
            .as_ref()
            .expect("staged source remains open until final validation");
        build_staged_bundle(input, staging_directory, source_digest)
    };
    let manifest = match built_bundle {
        Ok(manifest) => manifest,
        Err(error) => return Err(cleanup_staging(reservation, staging, error)),
    };
    match publish_staged_bundle(staging, reservation) {
        Ok(()) => Ok(manifest),
        Err(error) => Err(cleanup_staging(reservation, staging, error)),
    }
}

pub fn extract_markdown(document_xml: &[u8], source_name: &str) -> Result<String, String> {
    let document = parse_document_xml(document_xml)?;
    let body = find_element(&document, "body")
        .ok_or_else(|| "word/document.xml has no document body".to_string())?;

    let mut lines = vec![
        "# DOCX extracted text".to_string(),
        String::new(),
        format!("Source: `{source_name}`"),
        String::new(),
        "This is a searchable extraction. The source DOCX and raw XML/media in this bundle remain authoritative for layout and editable equations.".to_string(),
        String::new(),
        "## Body".to_string(),
        String::new(),
    ];

    let body_children = document.elements[body].children.clone();
    for block in body_children {
        match local_name(&document.elements[block].name) {
            "p" => {
                if let Some(rendered) = paragraph_markdown(&document, block)? {
                    lines.push(rendered);
                    lines.push(String::new());
                }
            }
            "tbl" => {
                let rendered = table_markdown(&document, block);
                if !rendered.is_empty() {
                    lines.extend(rendered);
                    lines.push(String::new());
                }
            }
            _ => {}
        }
    }

    let markdown = lines.join("\n");
    let markdown = markdown.trim_end_matches('\n');
    Ok(format!("{markdown}\n"))
}

pub fn run(args: &[String]) -> i32 {
    let parsed = match parse_args(args) {
        Ok(Some(parsed)) => parsed,
        Ok(None) => {
            print_usage();
            return 0;
        }
        Err(error) => {
            eprintln!("extract_docx: {error}");
            eprintln!("usage: agent-canon extract-docx <input.docx> --output-dir <directory>");
            return 2;
        }
    };

    match extract_bundle(&parsed.input, &parsed.output_dir) {
        Ok(manifest) => {
            let source_name = manifest["source"]["name"]
                .as_str()
                .expect("the extractor writes a string source name");
            println!("extracted {source_name} -> {}", parsed.output_dir.display());
            0
        }
        Err(error) => {
            eprintln!("extract_docx: {error}");
            1
        }
    }
}

struct CliArgs {
    input: PathBuf,
    output_dir: PathBuf,
}

fn parse_args(args: &[String]) -> Result<Option<CliArgs>, String> {
    let mut input = None;
    let mut output_dir = None;
    let mut options_enabled = true;
    let mut index = 0;
    while index < args.len() {
        let argument = args[index].as_str();
        if options_enabled && argument == "--" {
            options_enabled = false;
            index += 1;
            continue;
        }
        if options_enabled && matches!(argument, "-h" | "--help") {
            return Ok(None);
        }
        if options_enabled && (argument == "--output-dir" || argument.starts_with("--output-dir="))
        {
            let value = if let Some((_, value)) = argument.split_once('=') {
                index += 1;
                value
            } else {
                let value = args
                    .get(index + 1)
                    .ok_or_else(|| "--output-dir requires a value".to_string())?;
                if value.starts_with('-') {
                    return Err("--output-dir requires a value".to_string());
                }
                index += 2;
                value
            };
            output_dir = Some(PathBuf::from(value));
            continue;
        }
        if options_enabled && argument.starts_with('-') {
            return Err(format!("unrecognized argument: {argument}"));
        }
        if input.is_some() {
            return Err(format!("unrecognized argument: {argument}"));
        }
        input = Some(PathBuf::from(argument));
        index += 1;
    }
    let input = input.ok_or_else(|| "the following arguments are required: input".to_string())?;
    let output_dir = output_dir
        .ok_or_else(|| "the following arguments are required: --output-dir".to_string())?;
    Ok(Some(CliArgs { input, output_dir }))
}

fn print_usage() {
    println!("Extract an authorized DOCX into a searchable reference bundle.\n\nUsage: agent-canon extract-docx <input.docx> --output-dir <directory>");
}

fn resolve_input(source: &Path) -> Result<InputFile, String> {
    let expanded = crate::path_expansion::expand_user_path(source)
        .map_err(|_| format!("input file does not exist: {}", source.display()))?;
    let canonical_path = fs::canonicalize(&expanded)
        .map_err(|_| format!("input file does not exist: {}", source.display()))?;
    if !canonical_path
        .extension()
        .and_then(OsStr::to_str)
        .is_some_and(|extension| extension.eq_ignore_ascii_case("docx"))
    {
        return Err(format!(
            "input must have a .docx extension: {}",
            canonical_path.display()
        ));
    }
    let name = canonical_path
        .file_name()
        .ok_or_else(|| format!("input is not a regular file: {}", canonical_path.display()))?
        .to_os_string();
    let source_name = name
        .to_str()
        .ok_or_else(|| {
            format!(
                "input file name is not valid UTF-8: {}",
                canonical_path.display()
            )
        })?
        .to_owned();
    let parent_path = canonical_path
        .parent()
        .ok_or_else(|| format!("input is not a regular file: {}", canonical_path.display()))?;
    let (parent, _) = open_parent_directory(parent_path, false)?;
    let metadata = parent
        .symlink_metadata(&name)
        .map_err(|_| format!("input is not a regular file: {}", canonical_path.display()))?;
    if metadata.is_symlink() || !metadata.is_file() {
        return Err(format!(
            "input is not a regular file: {}",
            canonical_path.display()
        ));
    }
    Ok(InputFile {
        parent,
        name,
        source_name,
        canonical_path,
    })
}

fn reserve_output_directory(output_dir: &Path) -> Result<OutputReservation, String> {
    let expanded = crate::path_expansion::expand_user_path(output_dir).map_err(|error| {
        format!(
            "cannot resolve output directory {}: {error}",
            output_dir.display()
        )
    })?;
    let absolute = absolute_lexical_path(&expanded)?;
    let name = absolute
        .file_name()
        .ok_or_else(|| "output directory must not be a filesystem root".to_string())?
        .to_os_string();
    let parent_path = absolute
        .parent()
        .ok_or_else(|| "output directory must not be a filesystem root".to_string())?;
    let (parent, canonical_parent) = open_parent_directory(parent_path, true)?;
    let path = canonical_parent.join(&name);

    match parent.symlink_metadata(&name) {
        Ok(metadata) if metadata.is_symlink() => Err(format!(
            "output directory must not be a symlink: {}",
            path.display()
        )),
        Ok(metadata) if !metadata.is_dir() => Err(format!(
            "output path is not a directory: {}",
            path.display()
        )),
        Ok(metadata) => {
            if !directory_is_empty(&parent, &name).map_err(|error| {
                format!(
                    "cannot inspect output directory {}: {error}",
                    path.display()
                )
            })? {
                return Err(format!("output directory is not empty: {}", path.display()));
            }
            Ok(OutputReservation {
                identity: Some(directory_identity(&parent, &name).map_err(|error| {
                    format!(
                        "cannot inspect output directory {}: {error}",
                        path.display()
                    )
                })?),
                parent,
                name,
                path,
                existed: true,
            })
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(OutputReservation {
            parent,
            name,
            path,
            existed: false,
            identity: None,
        }),
        Err(error) => Err(format!(
            "cannot inspect output path {}: {error}",
            path.display()
        )),
    }
}

fn verify_output_reservation(reservation: &OutputReservation) -> Result<(), String> {
    let metadata = match reservation.parent.symlink_metadata(&reservation.name) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            if reservation.existed {
                return Err(format!(
                    "output directory changed before publication: {}",
                    reservation.path.display()
                ));
            }
            return Ok(());
        }
        Err(error) => {
            return Err(format!(
                "cannot verify output directory {}: {error}",
                reservation.path.display()
            ));
        }
    };
    if !reservation.existed {
        return Err(format!(
            "output path appeared before publication: {}",
            reservation.path.display()
        ));
    }
    if metadata.is_symlink() || !metadata.is_dir() {
        return Err(format!(
            "output directory changed before publication: {}",
            reservation.path.display()
        ));
    }
    if Some(
        directory_identity(&reservation.parent, &reservation.name).map_err(|error| {
            format!(
                "output directory changed before publication: {}: {error}",
                reservation.path.display()
            )
        })?,
    ) != reservation.identity
        || !directory_is_empty(&reservation.parent, &reservation.name).map_err(|error| {
            format!(
                "cannot verify output directory {}: {error}",
                reservation.path.display()
            )
        })?
    {
        return Err(format!(
            "output directory changed before publication: {}",
            reservation.path.display()
        ));
    }
    Ok(())
}

fn verify_output_absent(reservation: &OutputReservation) -> Result<(), String> {
    match reservation.parent.symlink_metadata(&reservation.name) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Ok(_) => Err(format!(
            "output path appeared before publication: {}",
            reservation.path.display()
        )),
        Err(error) => Err(format!(
            "cannot verify output path {}: {error}",
            reservation.path.display()
        )),
    }
}

fn directory_is_empty(parent: &Dir, name: &OsStr) -> io::Result<bool> {
    let directory = parent.open_dir_nofollow(name)?;
    let mut entries = directory.entries()?;
    Ok(entries.next().transpose()?.is_none())
}

fn directory_identity(parent: &Dir, name: &OsStr) -> io::Result<(u64, u64)> {
    let directory = parent.open_dir_nofollow(name)?;
    let metadata = directory.dir_metadata()?;
    Ok(metadata_identity(&metadata))
}

fn metadata_identity(metadata: &cap_std::fs::Metadata) -> (u64, u64) {
    (
        CapabilityMetadataExt::dev(metadata),
        CapabilityMetadataExt::ino(metadata),
    )
}

fn absolute_lexical_path(path: &Path) -> Result<PathBuf, String> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .map_err(|error| format!("cannot resolve current directory: {error}"))?
            .join(path)
    };
    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::Prefix(prefix) => normalized.push(prefix.as_os_str()),
            Component::RootDir => normalized.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => {
                if normalized.file_name().is_some() {
                    normalized.pop();
                }
            }
            Component::Normal(name) => normalized.push(name),
        }
    }
    if !normalized.is_absolute() {
        return Err(format!("cannot resolve absolute path: {}", path.display()));
    }
    Ok(normalized)
}

fn path_root_and_relative(path: &Path) -> Result<(PathBuf, PathBuf), String> {
    let mut root = PathBuf::new();
    let mut relative = PathBuf::new();
    let mut saw_root = false;
    for component in path.components() {
        match component {
            Component::Prefix(prefix) => root.push(prefix.as_os_str()),
            Component::RootDir => {
                root.push(component.as_os_str());
                saw_root = true;
            }
            Component::CurDir => {}
            Component::Normal(name) => relative.push(name),
            Component::ParentDir => {
                return Err(format!("path is not normalized: {}", path.display()));
            }
        }
    }
    if !saw_root {
        return Err(format!("path is not absolute: {}", path.display()));
    }
    Ok((root, relative))
}

fn open_parent_directory(path: &Path, create_missing: bool) -> Result<(Dir, PathBuf), String> {
    let (root_path, relative) = path_root_and_relative(path)?;
    let root =
        Dir::open_ambient_dir(&root_path, cap_std::ambient_authority()).map_err(|error| {
            format!(
                "cannot open filesystem root {}: {error}",
                root_path.display()
            )
        })?;
    if create_missing {
        let create_path = if relative.as_os_str().is_empty() {
            Path::new(".")
        } else {
            relative.as_path()
        };
        root.create_dir_all(create_path)
            .map_err(|error| format!("cannot create output parent {}: {error}", path.display()))?;
    }
    let canonical_relative = if relative.as_os_str().is_empty() {
        PathBuf::from(".")
    } else {
        root.canonicalize(&relative)
            .map_err(|error| format!("cannot resolve directory {}: {error}", path.display()))?
    };
    let directory = open_directory_chain_nofollow(&root, &canonical_relative)
        .map_err(|error| format!("cannot open directory {}: {error}", path.display()))?;
    let canonical_path = if canonical_relative == Path::new(".") {
        root_path
    } else {
        root_path.join(canonical_relative)
    };
    Ok((directory, canonical_path))
}

fn open_directory_chain_nofollow(root: &Dir, relative: &Path) -> io::Result<Dir> {
    let mut directory = root.open_dir(".")?;
    for component in relative.components() {
        match component {
            Component::CurDir => {}
            Component::Normal(name) => directory = directory.open_dir_nofollow(name)?,
            _ => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "directory path must be relative and normalized",
                ));
            }
        }
    }
    Ok(directory)
}

fn source_stat_identity(metadata: &cap_std::fs::Metadata) -> Result<SourceStatIdentity, String> {
    #[cfg(unix)]
    use cap_std::fs::MetadataExt as CapMetadataExt;
    #[cfg(not(unix))]
    let modified = metadata
        .modified()
        .map_err(|error| format!("cannot read source modification time: {error}"))?
        .into_std();
    #[cfg(not(unix))]
    let created = metadata.created().ok().map(|time| time.into_std());
    Ok(SourceStatIdentity {
        device: CapabilityMetadataExt::dev(metadata),
        inode: CapabilityMetadataExt::ino(metadata),
        size: metadata.len(),
        #[cfg(unix)]
        mtime_seconds: CapMetadataExt::mtime(metadata),
        #[cfg(unix)]
        mtime_nanoseconds: CapMetadataExt::mtime_nsec(metadata),
        #[cfg(unix)]
        ctime_seconds: CapMetadataExt::ctime(metadata),
        #[cfg(unix)]
        ctime_nanoseconds: CapMetadataExt::ctime_nsec(metadata),
        #[cfg(not(unix))]
        modified,
        #[cfg(not(unix))]
        created,
    })
}

fn create_staging_directory(reservation: &OutputReservation) -> Result<StagingDirectory, String> {
    for _ in 0..8 {
        let mut random = [0_u8; 16];
        getrandom::getrandom(&mut random)
            .map_err(|error| format!("cannot create private staging name: {error}"))?;
        let stage_name = format!(
            ".{}.extract-{}",
            reservation.name.to_string_lossy(),
            encode_hex(&random)
        );
        let mut builder = DirBuilder::new();
        #[cfg(unix)]
        {
            use cap_std::fs::DirBuilderExt;
            builder.mode(0o700);
        }
        match reservation.parent.create_dir_with(&stage_name, &builder) {
            Ok(()) => {
                let directory = match reservation.parent.open_dir_nofollow(&stage_name) {
                    Ok(directory) => directory,
                    Err(error) => {
                        let cleanup = reservation.parent.remove_dir(&stage_name);
                        return Err(match cleanup {
                            Ok(()) => format!(
                                "cannot open private staging directory {stage_name:?}: {error}"
                            ),
                            Err(cleanup_error) => format!(
                                "cannot open private staging directory {stage_name:?}: {error}; cannot remove it: {cleanup_error}"
                            ),
                        });
                    }
                };
                return Ok(StagingDirectory {
                    name: Some(stage_name),
                    directory: Some(directory),
                });
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => {
                return Err(format!(
                    "cannot create private staging directory beside {}: {error}",
                    reservation.path.display()
                ));
            }
        }
    }
    Err(format!(
        "cannot reserve a private staging directory beside {}",
        reservation.path.display()
    ))
}

fn cleanup_staging(
    reservation: &OutputReservation,
    staging: &mut StagingDirectory,
    original_error: String,
) -> String {
    drop(staging.directory.take());
    let Some(name) = staging.name.take() else {
        return original_error;
    };
    match reservation.parent.remove_dir_all(&name) {
        Ok(()) => original_error,
        Err(error) if error.kind() == io::ErrorKind::NotFound => original_error,
        Err(error) => {
            format!("{original_error}; cannot remove staging directory {name:?}: {error}")
        }
    }
}

fn build_staged_bundle(
    input: &InputFile,
    staging: &Dir,
    source_digest: &FileDigest,
) -> Result<Value, String> {
    let source_dir = staging
        .open_dir_nofollow("source")
        .map_err(|error| format!("cannot open source snapshot directory: {error}"))?;
    verify_file_digest(
        &source_dir,
        OsStr::new(&input.source_name),
        source_digest,
        "source copy",
    )?;
    let archive = inspect_archive(staging, &input.source_name, &input.canonical_path)?;
    let raw_records = copy_archive_members(
        staging,
        &input.source_name,
        archive.base_offset,
        &archive.members,
        &input.canonical_path,
    )?;
    let raw_root = staging
        .open_dir_nofollow("raw")
        .map_err(|error| format!("cannot open raw ZIP member root: {error}"))?;
    let document_xml = read_file(&raw_root, Path::new(DOCUMENT_XML_MEMBER))
        .map_err(|error| format!("cannot read {DOCUMENT_XML_MEMBER}: {error}"))?;
    let markdown = extract_markdown(&document_xml, &input.source_name)?;
    let mut extracted = create_new_file(staging, OsStr::new("extracted.md"))
        .map_err(|error| format!("cannot write extracted.md: {error}"))?;
    extracted
        .write_all(markdown.as_bytes())
        .map_err(|error| format!("cannot write extracted.md: {error}"))?;
    drop(extracted);

    let manifest = json!({
        "schema_version": SCHEMA_VERSION,
        "source": {
            "name": input.source_name,
            "size_bytes": source_digest.size_bytes,
            "sha256": source_digest.sha256,
        },
        "outputs": {
            "source_copy": format!("source/{}", input.source_name),
            "extracted_markdown": "extracted.md",
            "raw_members": "raw/",
            "document_xml": format!("raw/{DOCUMENT_XML_MEMBER}"),
        },
        "zip_members": raw_records.iter().map(RawMemberRecord::as_value).collect::<Vec<_>>(),
    });
    verify_bundle_hashes(
        staging,
        input,
        source_digest,
        &archive.members,
        &raw_records,
    )?;
    write_manifest(staging, &manifest)?;
    Ok(manifest)
}

impl RawMemberRecord {
    fn as_value(&self) -> Value {
        if self.directory {
            json!({"name":self.name, "directory":true, "size_bytes":0})
        } else {
            json!({
                "name":self.name,
                "directory":false,
                "size_bytes":self.size_bytes,
                "sha256":self.sha256,
            })
        }
    }
}

fn copy_source_snapshot(input: &InputFile, staging: &Dir) -> Result<FileDigest, String> {
    let path_before = input
        .parent
        .symlink_metadata(&input.name)
        .map_err(|error| {
            format!(
                "input file does not exist: {}: {error}",
                input.canonical_path.display()
            )
        })?;
    if path_before.is_symlink() || !path_before.is_file() {
        return Err(format!(
            "input is not a regular file: {}",
            input.canonical_path.display()
        ));
    }
    let mut options = OpenOptions::new();
    options.read(true).follow(FollowSymlinks::No);
    let mut source = input
        .parent
        .open_with(&input.name, &options)
        .map_err(|error| {
            format!(
                "cannot open input file {}: {error}",
                input.canonical_path.display()
            )
        })?;
    let before = source.metadata().map_err(|error| {
        format!(
            "cannot inspect input file {}: {error}",
            input.canonical_path.display()
        )
    })?;
    if !before.is_file() {
        return Err(format!(
            "input is not a regular file: {}",
            input.canonical_path.display()
        ));
    }
    let mut confirmation_options = OpenOptions::new();
    confirmation_options.read(true).follow(FollowSymlinks::No);
    let confirmation = input
        .parent
        .open_with(&input.name, &confirmation_options)
        .map_err(|error| {
            format!(
                "input changed while snapshotting: {}: {error}",
                input.canonical_path.display()
            )
        })?;
    let confirmed = confirmation.metadata().map_err(|error| {
        format!(
            "input changed while snapshotting: {}: {error}",
            input.canonical_path.display()
        )
    })?;
    if !confirmed.is_file() || source_stat_identity(&before)? != source_stat_identity(&confirmed)? {
        return Err(format!(
            "input changed while snapshotting: {}",
            input.canonical_path.display()
        ));
    }
    drop(confirmation);

    staging
        .create_dir("source")
        .map_err(|error| format!("cannot create source snapshot directory: {error}"))?;
    let source_dir = staging
        .open_dir_nofollow("source")
        .map_err(|error| format!("cannot open source snapshot directory: {error}"))?;
    let mut target = create_new_file(&source_dir, OsStr::new(&input.source_name))
        .map_err(|error| format!("cannot create source snapshot: {error}"))?;
    let expected = copy_and_digest(&mut source, &mut target).map_err(|error| {
        format!(
            "cannot copy input file {}: {error}",
            input.canonical_path.display()
        )
    })?;
    drop(target);

    let after = source.metadata().map_err(|error| {
        format!(
            "cannot inspect input file {}: {error}",
            input.canonical_path.display()
        )
    })?;
    let path_after = input
        .parent
        .symlink_metadata(&input.name)
        .map_err(|error| {
            format!(
                "input path changed while snapshotting: {}: {error}",
                input.canonical_path.display()
            )
        })?;
    if path_after.is_symlink() || !path_after.is_file() {
        return Err(format!(
            "input changed while snapshotting: {}",
            input.canonical_path.display()
        ));
    }
    let mut after_options = OpenOptions::new();
    after_options.read(true).follow(FollowSymlinks::No);
    let after_path_file = input
        .parent
        .open_with(&input.name, &after_options)
        .map_err(|error| {
            format!(
                "input changed while snapshotting: {}: {error}",
                input.canonical_path.display()
            )
        })?;
    let after_path_metadata = after_path_file.metadata().map_err(|error| {
        format!(
            "input changed while snapshotting: {}: {error}",
            input.canonical_path.display()
        )
    })?;
    if !after_path_metadata.is_file()
        || source_stat_identity(&before)? != source_stat_identity(&after)?
        || source_stat_identity(&after_path_metadata)? != source_stat_identity(&after)?
        || expected.size_bytes != after.len()
    {
        return Err(format!(
            "input changed while snapshotting: {}",
            input.canonical_path.display()
        ));
    }
    Ok(expected)
}

fn inspect_archive(
    staging: &Dir,
    source_name: &str,
    source_path: &Path,
) -> Result<ArchiveIndex, String> {
    let source_dir = staging
        .open_dir_nofollow("source")
        .map_err(|error| format!("cannot open copied source directory: {error}"))?;
    let source = open_read_file(&source_dir, OsStr::new(source_name)).map_err(|error| {
        format!(
            "cannot read copied source {}: {error}",
            source_path.display()
        )
    })?;
    let (base_offset, source) = zip_archive_coordinate_view(source, source_path)?;
    let mut buffer = vec![0; rawzip::RECOMMENDED_BUFFER_SIZE];
    let archive = RawZipArchive::from_seekable(source, &mut buffer)
        .map_err(|_| format!("not a readable DOCX ZIP archive: {}", source_path.display()))?;

    let directory_offset = archive.directory_offset();
    let mut entries = archive.entries(&mut buffer);
    let mut members = Vec::new();
    let mut identities: HashMap<Vec<String>, (String, bool)> = HashMap::new();
    let mut prefix_spellings: HashMap<Vec<String>, Vec<String>> = HashMap::new();
    while let Some(entry) = entries
        .next_entry()
        .map_err(|_| format!("not a readable DOCX ZIP archive: {}", source_path.display()))?
    {
        let header_name =
            decode_zip_name_untruncated(entry.file_path().as_ref(), entry.flags().is_utf8())?;
        let original_name = truncate_zip_name(&header_name);
        let (name, parts, identity_parts) = normalized_member_identity(&original_name)?;
        if let Some((other, _)) = identities.get(&identity_parts) {
            return Err(format!(
                "duplicate ZIP member identity: {other:?} and {original_name:?} -> {name:?}"
            ));
        }
        for depth in 1..=identity_parts.len() {
            let identity_prefix = identity_parts[..depth].to_vec();
            let spelling = parts[..depth].to_vec();
            if let Some(previous) = prefix_spellings.get(&identity_prefix) {
                if previous != &spelling {
                    return Err(format!(
                        "duplicate ZIP path-prefix identity: {:?} and {:?}",
                        previous.join("/"),
                        spelling.join("/")
                    ));
                }
            } else {
                prefix_spellings.insert(identity_prefix, spelling);
            }
        }
        let mode = (entry.external_attributes() >> 16) & 0o170000;
        if mode == 0o120000 {
            return Err(format!(
                "symlink ZIP member is not allowed: {original_name:?}"
            ));
        }
        let is_directory = original_name.ends_with('/');
        let wayfinder = entry.wayfinder();
        identities.insert(
            identity_parts.clone(),
            (original_name.clone(), is_directory),
        );
        members.push(ArchiveMember {
            wayfinder,
            header_name,
            original_name,
            name,
            parts,
            identity_parts,
            is_directory,
            size_bytes: entry.uncompressed_size_hint(),
            compression_method: entry.compression_method(),
            central_flags: entry.flags().bits(),
            local_header_offset: entry.local_header_offset(),
            next_header_offset: directory_offset,
        });
    }
    drop(entries);

    let mut physical_order = (0..members.len()).collect::<Vec<_>>();
    physical_order.sort_by(|left, right| {
        members[*right]
            .local_header_offset
            .cmp(&members[*left].local_header_offset)
    });
    let mut next_header_offset = directory_offset;
    for index in physical_order {
        members[index].next_header_offset = next_header_offset;
        next_header_offset = members[index].local_header_offset;
    }

    for member in &members {
        for depth in 1..member.identity_parts.len() {
            if let Some((parent, parent_is_directory)) =
                identities.get(&member.identity_parts[..depth])
            {
                if !*parent_is_directory {
                    return Err(format!(
                        "ZIP member path topology conflict: {parent:?} is a file parent of {:?}",
                        member.original_name
                    ));
                }
            }
        }
    }

    let document_identity = Path::new(DOCUMENT_XML_MEMBER)
        .components()
        .filter_map(|component| match component {
            Component::Normal(part) => part.to_str().map(portable_part_identity),
            _ => None,
        })
        .collect::<Vec<_>>();
    let document_member = members
        .iter()
        .find(|member| {
            member.identity_parts == document_identity && member.name == DOCUMENT_XML_MEMBER
        })
        .ok_or_else(|| format!("DOCX is missing {DOCUMENT_XML_MEMBER}"))?;
    if document_member.is_directory {
        return Err(format!("DOCX member is not a file: {DOCUMENT_XML_MEMBER}"));
    }
    Ok(ArchiveIndex {
        base_offset,
        members,
    })
}

fn decode_zip_name(raw_name: &[u8], utf8_name: bool) -> Result<String, String> {
    decode_zip_name_untruncated(raw_name, utf8_name).map(|name| truncate_zip_name(&name))
}

fn decode_zip_name_untruncated(raw_name: &[u8], utf8_name: bool) -> Result<String, String> {
    if utf8_name {
        return std::str::from_utf8(raw_name)
            .map(str::to_owned)
            .map_err(|error| format!("ZIP member name is not valid UTF-8: {error}"));
    }
    Ok(raw_name.iter().copied().map(cp437_char).collect())
}

fn truncate_zip_name(name: &str) -> String {
    name.split_once('\0')
        .map_or(name, |(prefix, _)| prefix)
        .to_owned()
}

fn cp437_char(byte: u8) -> char {
    const HIGH: &[u32] = &[
        0x00c7, 0x00fc, 0x00e9, 0x00e2, 0x00e4, 0x00e0, 0x00e5, 0x00e7, 0x00ea, 0x00eb, 0x00e8,
        0x00ef, 0x00ee, 0x00ec, 0x00c4, 0x00c5, 0x00c9, 0x00e6, 0x00c6, 0x00f4, 0x00f6, 0x00f2,
        0x00fb, 0x00f9, 0x00ff, 0x00d6, 0x00dc, 0x00a2, 0x00a3, 0x00a5, 0x20a7, 0x0192, 0x00e1,
        0x00ed, 0x00f3, 0x00fa, 0x00f1, 0x00d1, 0x00aa, 0x00ba, 0x00bf, 0x2310, 0x00ac, 0x00bd,
        0x00bc, 0x00a1, 0x00ab, 0x00bb, 0x2591, 0x2592, 0x2593, 0x2502, 0x2524, 0x2561, 0x2562,
        0x2556, 0x2555, 0x2563, 0x2551, 0x2557, 0x255d, 0x255c, 0x255b, 0x2510, 0x2514, 0x2534,
        0x252c, 0x251c, 0x2500, 0x253c, 0x255e, 0x255f, 0x255a, 0x2554, 0x2569, 0x2566, 0x2560,
        0x2550, 0x256c, 0x2567, 0x2568, 0x2564, 0x2565, 0x2559, 0x2558, 0x2552, 0x2553, 0x256b,
        0x256a, 0x2518, 0x250c, 0x2588, 0x2584, 0x258c, 0x2590, 0x2580, 0x03b1, 0x00df, 0x0393,
        0x03c0, 0x03a3, 0x03c3, 0x00b5, 0x03c4, 0x03a6, 0x0398, 0x03a9, 0x03b4, 0x221e, 0x03c6,
        0x03b5, 0x2229, 0x2261, 0x00b1, 0x2265, 0x2264, 0x2320, 0x2321, 0x00f7, 0x2248, 0x00b0,
        0x2219, 0x00b7, 0x221a, 0x207f, 0x00b2, 0x25a0, 0x00a0,
    ];
    if byte < 0x80 {
        char::from(byte)
    } else {
        char::from_u32(HIGH[usize::from(byte - 0x80)]).expect("the CP437 table contains scalars")
    }
}

fn normalized_member_identity(name: &str) -> Result<(String, Vec<String>, Vec<String>), String> {
    if name.is_empty() || name.contains('\0') {
        return Err(format!("unsafe ZIP member path: {name:?}"));
    }
    let slash_name = name.replace('\\', "/");
    if slash_name.starts_with('/') || has_windows_drive(&slash_name) {
        return Err(format!("unsafe ZIP member path: {name:?}"));
    }
    let mut parts = Vec::new();
    for part in slash_name.split('/') {
        match part {
            "" | "." => {}
            ".." => return Err(format!("unsafe ZIP member path: {name:?}")),
            _ => parts.push(part.to_owned()),
        }
    }
    if parts.is_empty() {
        return Err(format!("unsafe ZIP member path: {name:?}"));
    }
    let normalized = parts.join("/");
    let identity = parts
        .iter()
        .map(|part| portable_part_identity(part))
        .collect();
    Ok((normalized, parts, identity))
}

fn has_windows_drive(path: &str) -> bool {
    let bytes = path.as_bytes();
    bytes.len() >= 2 && bytes[0].is_ascii_alphabetic() && bytes[1] == b':'
}

fn portable_part_identity(part: &str) -> String {
    let normalized = ComposingNormalizer::new_nfc().normalize(part).into_owned();
    CaseMapper::new().fold_string(&normalized).into_owned()
}

fn copy_archive_members(
    staging: &Dir,
    source_name: &str,
    base_offset: u64,
    members: &[ArchiveMember],
    source_path: &Path,
) -> Result<Vec<RawMemberRecord>, String> {
    staging
        .create_dir("raw")
        .map_err(|error| format!("cannot create raw ZIP member root: {error}"))?;
    let raw_root = staging
        .open_dir_nofollow("raw")
        .map_err(|error| format!("cannot open raw ZIP member root: {error}"))?;
    let source_dir = staging
        .open_dir_nofollow("source")
        .map_err(|error| format!("cannot open copied source directory: {error}"))?;
    let source = open_read_file(&source_dir, OsStr::new(source_name)).map_err(|error| {
        format!(
            "cannot read copied source {}: {error}",
            source_path.display()
        )
    })?;
    let source = ArchiveCoordinateReader::new(source, base_offset)
        .map_err(|_| format!("not a readable DOCX ZIP archive: {}", source_path.display()))?;
    let mut buffer = vec![0; rawzip::RECOMMENDED_BUFFER_SIZE];
    let archive = RawZipArchive::from_seekable(source, &mut buffer)
        .map_err(|_| format!("not a readable DOCX ZIP archive: {}", source_path.display()))?;

    let mut records = Vec::with_capacity(members.len());
    let mut local_header_buffer = vec![0; LOCAL_HEADER_BUFFER_SIZE];
    for member in members {
        if member.is_directory {
            create_directory_chain(&raw_root, &member.parts).map_err(|error| {
                format!("ZIP directory path conflict: {:?}: {error}", member.name)
            })?;
            records.push(RawMemberRecord {
                name: member.name.clone(),
                directory: true,
                size_bytes: 0,
                sha256: None,
            });
            continue;
        }
        let entry = archive
            .get_entry(member.wayfinder)
            .map_err(|_| format!("cannot read ZIP member: {:?}", member.original_name))?;
        let local_header = entry
            .local_header(&mut local_header_buffer)
            .map_err(|_| format!("cannot read ZIP member: {:?}", member.original_name))?;
        let local_name = decode_zip_name_untruncated(
            local_header.file_path().as_ref(),
            local_header.flags().is_utf8(),
        )
        .map_err(|_| format!("cannot read ZIP member: {:?}", member.original_name))?;
        if local_name != member.header_name {
            return Err(format!(
                "cannot read ZIP member: {:?}",
                member.original_name
            ));
        }
        drop(local_header);
        let (compressed_start, compressed_end) = entry.compressed_data_range();
        if compressed_start < member.local_header_offset
            || compressed_end < compressed_start
            || compressed_end > member.next_header_offset
        {
            return Err(format!(
                "cannot read ZIP member: {:?}",
                member.original_name
            ));
        }
        if member.central_flags & UNSUPPORTED_ZIP_ENTRY_FLAGS != 0 {
            return Err(format!(
                "cannot read ZIP member: {:?}",
                member.original_name
            ));
        }

        let leaf = member
            .parts
            .last()
            .expect("validated member paths are non-empty");
        let parent = create_directory_chain(&raw_root, &member.parts[..member.parts.len() - 1])
            .map_err(|error| {
                format!(
                    "cannot create ZIP member parent for {:?}: {error}",
                    member.name
                )
            })?;
        let mut target = create_new_file(&parent, OsStr::new(leaf))
            .map_err(|error| format!("cannot create ZIP member {:?}: {error}", member.name))?;
        let decoder =
            zip_member_decoder(member.compression_method, entry.reader(), member.size_bytes)
                .map_err(|_| format!("cannot read ZIP member: {:?}", member.original_name))?;
        let mut verified = entry.verifying_reader(decoder);
        let digest = copy_and_digest(&mut verified, &mut target)
            .map_err(|_| format!("cannot read ZIP member: {:?}", member.original_name))?;
        drop(target);
        if digest.size_bytes != member.size_bytes {
            return Err(format!(
                "ZIP member size mismatch: {:?}: expected {}, observed {}",
                member.original_name, member.size_bytes, digest.size_bytes
            ));
        }
        records.push(RawMemberRecord {
            name: member.name.clone(),
            directory: false,
            size_bytes: digest.size_bytes,
            sha256: Some(digest.sha256),
        });
    }
    Ok(records)
}

fn zip_member_decoder<'a, R: Read + 'a>(
    method: CompressionMethod,
    mut compressed: R,
    uncompressed_size: u64,
) -> Result<Box<dyn Read + 'a>, String> {
    match method {
        CompressionMethod::STORE => Ok(Box::new(compressed)),
        CompressionMethod::DEFLATE => Ok(Box::new(flate2::read::DeflateDecoder::new(compressed))),
        CompressionMethod::BZIP2 => Ok(Box::new(BzDecoder::new(compressed))),
        CompressionMethod::LZMA => {
            // ZIP method 14 prefixes the raw LZMA stream with version and property-size fields.
            let mut header = [0_u8; 4];
            compressed
                .read_exact(&mut header)
                .map_err(|error| format!("cannot read ZIP LZMA header: {error}"))?;
            let properties_size = u16::from_le_bytes([header[2], header[3]]);
            if properties_size != 5 {
                return Err(format!(
                    "unexpected ZIP LZMA properties size: {properties_size}"
                ));
            }
            let mut properties = [0_u8; 5];
            compressed
                .read_exact(&mut properties)
                .map_err(|error| format!("cannot read ZIP LZMA properties: {error}"))?;
            let dictionary_size =
                u32::from_le_bytes([properties[1], properties[2], properties[3], properties[4]]);
            let decoder = LzmaReader::new_with_props(
                compressed,
                uncompressed_size,
                properties[0],
                dictionary_size,
                None,
            )
            .map_err(|error| format!("cannot initialize ZIP LZMA decoder: {error}"))?;
            Ok(Box::new(decoder))
        }
        _ => Err(format!("unsupported ZIP compression method: {method}")),
    }
}

fn create_directory_chain(root: &Dir, parts: &[String]) -> io::Result<Dir> {
    let mut directory = root.open_dir(".")?;
    for part in parts {
        match directory.create_dir(part) {
            Ok(()) => {}
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(error),
        }
        directory = directory.open_dir_nofollow(part)?;
    }
    Ok(directory)
}

fn open_existing_directory_chain(root: &Dir, parts: &[String]) -> io::Result<Dir> {
    let mut directory = root.open_dir(".")?;
    for part in parts {
        directory = directory.open_dir_nofollow(part)?;
    }
    Ok(directory)
}

fn create_new_file(parent: &Dir, name: &OsStr) -> io::Result<cap_std::fs::File> {
    let mut options = OpenOptions::new();
    options
        .write(true)
        .create_new(true)
        .follow(FollowSymlinks::No);
    parent.open_with(name, &options)
}

fn open_read_file(parent: &Dir, name: &OsStr) -> io::Result<cap_std::fs::File> {
    let mut options = OpenOptions::new();
    options.read(true).follow(FollowSymlinks::No);
    parent.open_with(name, &options)
}

// zip 9 detects prepended data; rawzip must read with the ZIP start at logical offset zero.
fn zip_archive_coordinate_view(
    source: cap_std::fs::File,
    source_path: &Path,
) -> Result<(u64, ArchiveCoordinateReader<cap_std::fs::File>), String> {
    let archive = zip::ZipArchive::new(source)
        .map_err(|_| format!("not a readable DOCX ZIP archive: {}", source_path.display()))?;
    let base_offset = archive.offset();
    let source = archive.into_inner();
    let source = ArchiveCoordinateReader::new(source, base_offset)
        .map_err(|_| format!("not a readable DOCX ZIP archive: {}", source_path.display()))?;
    Ok((base_offset, source))
}

fn read_file(root: &Dir, relative: &Path) -> io::Result<Vec<u8>> {
    let parts = relative
        .components()
        .map(|component| match component {
            Component::Normal(part) => part.to_str().map(str::to_owned).ok_or_else(|| {
                io::Error::new(io::ErrorKind::InvalidInput, "non-UTF-8 member path")
            }),
            _ => Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "invalid member path",
            )),
        })
        .collect::<io::Result<Vec<_>>>()?;
    let leaf = parts
        .last()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "empty member path"))?;
    let parent = open_existing_directory_chain(root, &parts[..parts.len() - 1])?;
    let mut file = open_read_file(&parent, OsStr::new(leaf))?;
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes)?;
    Ok(bytes)
}

fn copy_and_digest(reader: &mut impl Read, writer: &mut impl Write) -> io::Result<FileDigest> {
    let mut hasher = Sha256::new();
    let mut size_bytes = 0_u64;
    let mut buffer = vec![0_u8; CHUNK_SIZE];
    loop {
        let read = reader.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        writer.write_all(&buffer[..read])?;
        hasher.update(&buffer[..read]);
        size_bytes += read as u64;
    }
    Ok(FileDigest {
        size_bytes,
        sha256: encode_hex(&hasher.finalize()),
    })
}

fn digest_reader(reader: &mut impl Read) -> io::Result<FileDigest> {
    let mut sink = io::sink();
    copy_and_digest(reader, &mut sink)
}

fn verify_file_digest(
    parent: &Dir,
    name: &OsStr,
    expected: &FileDigest,
    label: &str,
) -> Result<(), String> {
    let mut file = open_read_file(parent, name)
        .map_err(|error| format!("{label} readback failed: {error}"))?;
    let observed =
        digest_reader(&mut file).map_err(|error| format!("{label} readback failed: {error}"))?;
    if &observed != expected {
        return Err(format!(
            "{label} readback mismatch: expected {}, observed {}",
            digest_debug(expected),
            digest_debug(&observed)
        ));
    }
    Ok(())
}

fn digest_debug(digest: &FileDigest) -> String {
    format!(
        "FileDigest(size_bytes={}, sha256='{}')",
        digest.size_bytes, digest.sha256
    )
}

fn verify_bundle_hashes(
    staging: &Dir,
    input: &InputFile,
    source_digest: &FileDigest,
    members: &[ArchiveMember],
    records: &[RawMemberRecord],
) -> Result<(), String> {
    let source_dir = staging
        .open_dir_nofollow("source")
        .map_err(|error| format!("source copy readback failed: {error}"))?;
    verify_file_digest(
        &source_dir,
        OsStr::new(&input.source_name),
        source_digest,
        "source copy",
    )?;
    let raw_root = staging
        .open_dir_nofollow("raw")
        .map_err(|error| format!("raw ZIP member readback failed: {error}"))?;
    for (member, record) in members.iter().zip(records) {
        if member.name != record.name {
            return Err("invalid internal ZIP member record".to_string());
        }
        if record.directory {
            let directory =
                open_existing_directory_chain(&raw_root, &member.parts).map_err(|error| {
                    format!(
                        "ZIP directory readback mismatch: {:?}: {error}",
                        member.name
                    )
                })?;
            if !directory
                .dir_metadata()
                .map_err(|error| error.to_string())?
                .is_dir()
            {
                return Err(format!(
                    "ZIP directory readback mismatch: {:?}",
                    member.name
                ));
            }
            continue;
        }
        let leaf = member
            .parts
            .last()
            .expect("validated member paths are non-empty");
        let parent =
            open_existing_directory_chain(&raw_root, &member.parts[..member.parts.len() - 1])
                .map_err(|error| {
                    format!("ZIP member readback failed: {:?}: {error}", member.name)
                })?;
        let expected = FileDigest {
            size_bytes: record.size_bytes,
            sha256: record
                .sha256
                .clone()
                .ok_or_else(|| "invalid internal ZIP member record".to_string())?,
        };
        verify_file_digest(
            &parent,
            OsStr::new(leaf),
            &expected,
            &format!("ZIP member {:?}", member.name),
        )?;
    }
    Ok(())
}

fn write_manifest(staging: &Dir, manifest: &Value) -> Result<(), String> {
    let mut contents = serde_json::to_vec_pretty(manifest)
        .map_err(|error| format!("cannot serialize manifest: {error}"))?;
    contents.push(b'\n');
    let mut file = create_new_file(staging, OsStr::new("manifest.json"))
        .map_err(|error| format!("cannot write manifest: {error}"))?;
    file.write_all(&contents)
        .map_err(|error| format!("cannot write manifest: {error}"))?;
    drop(file);

    let observed = read_file(staging, Path::new("manifest.json"))
        .map_err(|_| "manifest readback failed".to_string())?;
    let observed: Value =
        serde_json::from_slice(&observed).map_err(|_| "manifest readback failed".to_string())?;
    if &observed != manifest {
        return Err("manifest readback mismatch".to_string());
    }
    Ok(())
}

fn publish_staged_bundle(
    staging: &mut StagingDirectory,
    reservation: &OutputReservation,
) -> Result<(), String> {
    verify_output_reservation(reservation)?;
    let stage_name = staging
        .name
        .as_ref()
        .expect("staging is unpublished before transaction commit");
    let stage_directory = staging
        .directory
        .as_ref()
        .expect("staging is open before transaction commit");
    let stage_metadata = stage_directory
        .dir_metadata()
        .map_err(|error| format!("cannot inspect staging directory: {error}"))?;
    let stage_identity = metadata_identity(&stage_metadata);
    let stage_path_metadata = reservation
        .parent
        .symlink_metadata(stage_name)
        .map_err(|error| format!("cannot inspect staging directory: {error}"))?;
    if stage_path_metadata.is_symlink()
        || !stage_path_metadata.is_dir()
        || directory_identity(&reservation.parent, OsStr::new(stage_name))
            .map_err(|error| format!("cannot verify staging directory: {error}"))?
            != stage_identity
    {
        return Err("private staging path changed before publication".to_string());
    }
    drop(staging.directory.take());

    if reservation.existed {
        let reserved_identity = reservation.identity.ok_or_else(|| {
            "invalid internal output reservation for existing directory".to_string()
        })?;
        let backup_name = format!("{stage_name}.previous-empty-output");
        reservation
            .parent
            .rename(&reservation.name, &reservation.parent, &backup_name)
            .map_err(|error| format!("cannot preserve existing empty output directory: {error}"))?;
        let backup_metadata = match reservation.parent.symlink_metadata(&backup_name) {
            Ok(metadata) => metadata,
            Err(error) => {
                let rollback =
                    reservation
                        .parent
                        .rename(&backup_name, &reservation.parent, &reservation.name);
                return Err(match rollback {
                    Ok(()) => format!("cannot verify preserved empty output directory: {error}"),
                    Err(rollback_error) => format!(
                        "cannot verify preserved empty output directory: {error}; rollback failed: {rollback_error}; preserved at {backup_name:?}"
                    ),
                });
            }
        };
        let backup_identity = if backup_metadata.is_symlink() || !backup_metadata.is_dir() {
            None
        } else {
            Some(
                directory_identity(&reservation.parent, OsStr::new(&backup_name)).map_err(
                    |error| format!("cannot verify preserved output directory: {error}"),
                )?,
            )
        };
        if backup_identity != Some(reserved_identity)
            || !directory_is_empty(&reservation.parent, OsStr::new(&backup_name))
                .map_err(|error| format!("cannot verify preserved output directory: {error}"))?
        {
            let rollback =
                reservation
                    .parent
                    .rename(&backup_name, &reservation.parent, &reservation.name);
            return Err(match rollback {
                Ok(()) => format!("output directory changed before publication: {}", reservation.path.display()),
                Err(error) => format!(
                    "output directory changed before publication: {}; rollback failed: {error}; preserved at {backup_name:?}",
                    reservation.path.display()
                ),
            });
        }
        if let Err(error) = verify_output_absent(reservation) {
            let rollback =
                reservation
                    .parent
                    .rename(&backup_name, &reservation.parent, &reservation.name);
            return Err(match rollback {
                Ok(()) => error,
                Err(rollback_error) => format!(
                    "{error}; rollback failed: {rollback_error}; preserved at {backup_name:?}"
                ),
            });
        }
        if let Err(error) =
            reservation
                .parent
                .rename(stage_name, &reservation.parent, &reservation.name)
        {
            let rollback =
                reservation
                    .parent
                    .rename(&backup_name, &reservation.parent, &reservation.name);
            return Err(match rollback {
                Ok(()) => format!("cannot publish verified output directory: {error}"),
                Err(rollback_error) => format!(
                    "cannot publish verified output directory: {error}; rollback failed: {rollback_error}; preserved at {backup_name:?}"
                ),
            });
        }
        staging.name = None;
        verify_published_identity(reservation, stage_identity)?;
        reservation
            .parent
            .remove_dir(&backup_name)
            .map_err(|error| format!("cannot remove preserved empty output directory: {error}"))?;
    } else {
        verify_output_absent(reservation)?;
        reservation
            .parent
            .rename(stage_name, &reservation.parent, &reservation.name)
            .map_err(|error| format!("cannot publish verified output directory: {error}"))?;
        staging.name = None;
        verify_published_identity(reservation, stage_identity)?;
    }
    Ok(())
}

fn verify_published_identity(
    reservation: &OutputReservation,
    expected: (u64, u64),
) -> Result<(), String> {
    let published = reservation
        .parent
        .symlink_metadata(&reservation.name)
        .map_err(|error| format!("published output readback failed: {error}"))?;
    if published.is_symlink() || !published.is_dir() {
        return Err(format!(
            "published output readback mismatch: {}",
            reservation.path.display()
        ));
    }
    let identity = directory_identity(&reservation.parent, &reservation.name)
        .map_err(|error| format!("published output readback failed: {error}"))?;
    if identity != expected {
        return Err(format!(
            "published output readback mismatch: {}",
            reservation.path.display()
        ));
    }
    Ok(())
}

fn parse_document_xml(bytes: &[u8]) -> Result<XmlDocument, String> {
    let mut salt = [0_u8; 16];
    getrandom::getrandom(&mut salt)
        .map_err(|error| format!("cannot initialize XML parser: {error}"))?;
    let mut parser = Parser::new(None, Some(b'\x1f'), salt);
    parser.set_handlers(HandlerSet {
        start_element: true,
        end_element: true,
        character_data: true,
        // The Expat port's default handler refuses external references without I/O.
        external_entity_ref: true,
        ..HandlerSet::default()
    });
    let mut recorder = XmlEventRecorder::default();
    match parser.parse(&mut recorder, bytes, true) {
        Status::Ok => {}
        _ => return Err("word/document.xml is not valid XML".to_string()),
    }
    build_xml_tree(recorder.events).map_err(|_| "word/document.xml is not valid XML".to_string())
}

fn build_xml_tree(events: Vec<XmlEvent>) -> Result<XmlDocument, String> {
    let mut elements = Vec::new();
    let mut stack: Vec<usize> = Vec::new();
    let mut root = None;
    for event in events {
        match event {
            XmlEvent::Start { name, attributes } => {
                let index = elements.len();
                elements.push(XmlElement {
                    name: expanded_name(&name)?,
                    attributes: attributes
                        .iter()
                        .map(|(name, value)| Ok((expanded_name(name)?, utf8(value)?)))
                        .collect::<Result<Vec<_>, String>>()?,
                    text: String::new(),
                    tail: String::new(),
                    children: Vec::new(),
                });
                if let Some(parent) = stack.last().copied() {
                    elements[parent].children.push(index);
                } else if root.replace(index).is_some() {
                    return Err("multiple XML document roots".to_string());
                }
                stack.push(index);
            }
            XmlEvent::End(name) => {
                let name = expanded_name(&name)?;
                let index = stack
                    .pop()
                    .ok_or_else(|| "unexpected XML end element".to_string())?;
                if elements[index].name != name {
                    return Err("mismatched XML end element".to_string());
                }
            }
            XmlEvent::Text(bytes) => {
                if let Some(element) = stack.last().copied() {
                    let text = utf8(&bytes)?;
                    if let Some(child) = elements[element].children.last().copied() {
                        elements[child].tail.push_str(&text);
                    } else {
                        elements[element].text.push_str(&text);
                    }
                }
            }
        }
    }
    if !stack.is_empty() {
        return Err("unclosed XML element".to_string());
    }
    let root = root.ok_or_else(|| "XML document has no root element".to_string())?;
    Ok(XmlDocument { elements, root })
}

fn expanded_name(name: &[u8]) -> Result<String, String> {
    let name = utf8(name)?;
    match name.split_once('\u{1f}') {
        Some((namespace, local)) => Ok(format!("{{{namespace}}}{local}")),
        None => Ok(name),
    }
}

fn utf8(bytes: &[u8]) -> Result<String, String> {
    std::str::from_utf8(bytes)
        .map(str::to_owned)
        .map_err(|error| format!("XML provider emitted invalid UTF-8: {error}"))
}

fn find_element(document: &XmlDocument, target: &str) -> Option<usize> {
    let mut pending = vec![document.root];
    while let Some(index) = pending.pop() {
        let element = &document.elements[index];
        if local_name(&element.name) == target {
            return Some(index);
        }
        pending.extend(element.children.iter().rev().copied());
    }
    None
}

fn local_name(name: &str) -> &str {
    name.rsplit_once('}').map_or(name, |(_, local)| local)
}

fn text_from_element(document: &XmlDocument, root: usize) -> String {
    let mut pending = vec![root];
    let mut text = String::new();
    while let Some(index) = pending.pop() {
        let element = &document.elements[index];
        match local_name(&element.name) {
            "t" | "instrText" => text.push_str(&element.text),
            "tab" => text.push('\t'),
            "br" | "cr" => text.push('\n'),
            _ => {}
        }
        pending.extend(element.children.iter().rev().copied());
    }
    crate::python_text::python_strip(&text).to_owned()
}

fn paragraph_style(document: &XmlDocument, paragraph: usize) -> String {
    let value_attribute = format!("{{{WORD_NAMESPACE}}}val");
    for properties in &document.elements[paragraph].children {
        if local_name(&document.elements[*properties].name) != "pPr" {
            continue;
        }
        for style in &document.elements[*properties].children {
            let style = &document.elements[*style];
            if local_name(&style.name) != "pStyle" {
                continue;
            }
            return style
                .attributes
                .iter()
                .find(|(name, _)| name == &value_attribute)
                .map(|(_, value)| value.clone())
                .unwrap_or_default();
        }
    }
    String::new()
}

fn paragraph_markdown(document: &XmlDocument, paragraph: usize) -> Result<Option<String>, String> {
    let text = text_from_element(document, paragraph);
    if text.is_empty() {
        return Ok(None);
    }
    let style = paragraph_style(document, paragraph).to_lowercase();
    if style.contains("heading") || style.contains("見出し") {
        let mut level = 1_usize;
        for character in style.chars().rev() {
            if crate::python_cli_integer::is_python_digit(character) {
                let digit =
                    crate::python_cli_integer::decimal_digit_value(character).ok_or_else(|| {
                        format!("invalid literal for int() with base 10: '{character}'")
                    })? as usize;
                level = digit.clamp(1, 6);
                break;
            }
        }
        return Ok(Some(format!("{} {text}", "#".repeat(level))));
    }
    Ok(Some(text))
}

fn table_markdown(document: &XmlDocument, table: usize) -> Vec<String> {
    let rows = collect_rows(document, table);
    let mut rendered_rows = Vec::new();
    for row in rows {
        let cells = document.elements[row]
            .children
            .iter()
            .filter(|cell| local_name(&document.elements[**cell].name) == "tc")
            .map(|cell| {
                text_from_element(document, *cell)
                    .replace('|', "\\|")
                    .replace('\n', "<br>")
            })
            .collect::<Vec<_>>();
        if !cells.is_empty() {
            rendered_rows.push(cells);
        }
    }
    if rendered_rows.is_empty() {
        return Vec::new();
    }
    let width = rendered_rows.iter().map(Vec::len).max().unwrap_or(0);
    for row in &mut rendered_rows {
        row.resize(width, String::new());
    }
    let mut lines = vec![format!("| {} |", rendered_rows[0].join(" | "))];
    lines.push(format!("| {} |", vec!["---"; width].join(" | ")));
    lines.extend(
        rendered_rows
            .iter()
            .skip(1)
            .map(|row| format!("| {} |", row.join(" | "))),
    );
    lines
}

fn collect_rows(document: &XmlDocument, root: usize) -> Vec<usize> {
    let mut rows = Vec::new();
    let mut pending = vec![root];
    while let Some(index) = pending.pop() {
        let element = &document.elements[index];
        if local_name(&element.name) == "tr" {
            rows.push(index);
        }
        pending.extend(element.children.iter().rev().copied());
    }
    rows
}

fn encode_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut encoded = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        encoded.push(HEX[usize::from(byte >> 4)] as char);
        encoded.push(HEX[usize::from(byte & 0x0f)] as char);
    }
    encoded
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use zip::write::SimpleFileOptions;
    use zip::ZipWriter;

    struct TestDirectory(PathBuf);

    impl TestDirectory {
        fn new() -> Self {
            let mut random = [0_u8; 12];
            getrandom::getrandom(&mut random).expect("test temporary directory entropy");
            let path =
                env::temp_dir().join(format!("agent-canon-docx-test-{}", encode_hex(&random)));
            fs::create_dir(&path).expect("create test temporary directory");
            Self(path)
        }

        fn capability(&self) -> Dir {
            Dir::open_ambient_dir(&self.0, cap_std::ambient_authority())
                .expect("open test temporary directory capability")
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn write_test_docx(path: &Path) {
        let mut archive = ZipWriter::new(fs::File::create(path).expect("create input DOCX"));
        let options =
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Stored);
        archive
            .start_file("[Content_Types].xml", options)
            .expect("write content types member");
        archive.write_all(b"<Types/>").expect("write content types");
        archive
            .start_file(DOCUMENT_XML_MEMBER, options)
            .expect("write document member");
        archive
            .write_all(
                format!("<w:document xmlns:w=\"{WORD_NAMESPACE}\"><w:body/></w:document>")
                    .as_bytes(),
            )
            .expect("write Word document");
        archive.finish().expect("finish input DOCX ZIP");
    }

    #[test]
    fn zip_names_follow_flags_and_python_nul_truncation() {
        assert_eq!(
            decode_zip_name(b"caf\xc3\xa9.bin", false).unwrap(),
            "caf├⌐.bin"
        );
        assert_eq!(
            decode_zip_name(b"caf\xc3\xa9.bin", true).unwrap(),
            "café.bin"
        );
        assert_eq!(
            decode_zip_name(b"assets/\x82.bin", false).unwrap(),
            "assets/é.bin"
        );
        assert_eq!(
            decode_zip_name(b"assets/name\0ignored", false).unwrap(),
            "assets/name"
        );
    }

    #[test]
    fn portable_zip_identity_uses_nfc_before_full_casefold() {
        assert_eq!(
            portable_part_identity("Cafe\u{301}"),
            portable_part_identity("CAFÉ")
        );
        assert_eq!(portable_part_identity("Straße"), "strasse");
    }

    #[test]
    fn source_copy_readback_failure_aborts_transaction_and_cleans_staging() {
        let root = TestDirectory::new();
        let source_path = root.0.join("input.docx");
        write_test_docx(&source_path);
        let input = resolve_input(&source_path).unwrap();
        let source_bytes = fs::read(&source_path).unwrap();
        let expected = FileDigest {
            size_bytes: source_bytes.len() as u64,
            sha256: encode_hex(&Sha256::digest(&source_bytes)),
        };

        for (output_name, existed) in [("absent", false), ("empty", true)] {
            let output = root.0.join(output_name);
            if existed {
                fs::create_dir(&output).unwrap();
            }
            let reservation = reserve_output_directory(&output).unwrap();
            let mut staging = create_staging_directory(&reservation).unwrap();
            {
                let staging_root = staging.directory.as_ref().unwrap();
                staging_root.create_dir("source").unwrap();
                staging_root
                    .open_dir_nofollow("source")
                    .unwrap()
                    .write(&input.source_name, b"changed bytes")
                    .unwrap();
            }

            let error =
                finish_staged_bundle(&input, &reservation, &mut staging, &expected).unwrap_err();
            assert!(error.contains("source copy readback mismatch"));
            if existed {
                assert!(output.is_dir());
                assert_eq!(fs::read_dir(&output).unwrap().count(), 0);
            } else {
                assert!(!output.exists());
            }
            let prefix = format!(".{output_name}.extract-");
            assert!(!fs::read_dir(&root.0)
                .unwrap()
                .filter_map(Result::ok)
                .any(|entry| entry.file_name().to_string_lossy().starts_with(&prefix)));
        }
    }

    #[test]
    fn output_reservation_detects_real_path_changes() {
        let root = TestDirectory::new();
        let output = root.0.join("bundle");
        let absent = reserve_output_directory(&output).unwrap();
        fs::create_dir(&output).unwrap();
        assert!(verify_output_reservation(&absent)
            .unwrap_err()
            .contains("output path appeared before publication"));

        fs::remove_dir(&output).unwrap();
        fs::create_dir(&output).unwrap();
        let empty = reserve_output_directory(&output).unwrap();
        fs::write(output.join("keep.txt"), b"keep").unwrap();
        assert!(verify_output_reservation(&empty)
            .unwrap_err()
            .contains("output directory changed before publication"));
    }
}
