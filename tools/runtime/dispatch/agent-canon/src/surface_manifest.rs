// @dependency-start
// contract implementation
// responsibility Parses standalone runtime surfaces and emits the native graph snapshot without Python execution.
// upstream design ../../../../../documents/runtime/SHARED_RUNTIME_SURFACES.md source classification and snapshot contract
// upstream design ../../../../../documents/runtime/shared-runtime-surfaces.toml machine-readable runtime inventory
// upstream implementation skill_projection_registry.rs resolves generated view owners without materializing views
// @dependency-end

use crate::skill_projection_registry::{
    generated_skill_projections, GeneratedProjection, ProjectionError,
};
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::fmt;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use toml_edit::{DocumentMut, Item, TableLike};

const DEFAULT_MANIFEST: &str = "documents/runtime/shared-runtime-surfaces.toml";
const DEFAULT_DOC: &str = "documents/runtime/SHARED_RUNTIME_SURFACES.md";
const SNAPSHOT_SCHEMA: &str = "agent-canon.surface-manifest.v2";
const DOC_MARKERS: &[&str] = &[
    "bootstrap runtime",
    "standalone",
    "agent-canon-log",
    "no parent-repository synchronization",
];
const HELP: &str = "Usage: agent-canon surface-manifest [--root PATH] [--prefix PREFIX] [--manifest PATH] <normalized-snapshot|check-doc|projection-forbidden-roots>\n\nRead-only standalone runtime surface classification.\n";

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct SurfaceEntry {
    path: String,
    mode: String,
    source: String,
    projection_producer: String,
    projection_kind: String,
    local_override_allowed: bool,
    optional: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SurfaceManifest {
    prefix: String,
    entries: Vec<SurfaceEntry>,
    generated_projections: Vec<GeneratedProjection>,
    projection_forbidden_roots: Vec<String>,
}

#[derive(Debug)]
pub(crate) enum SurfaceError {
    Invalid(String),
    Io(io::Error),
    Projection(ProjectionError),
}

impl fmt::Display for SurfaceError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Invalid(message) => formatter.write_str(message),
            Self::Io(error) => write!(formatter, "{error}"),
            Self::Projection(error) => write!(formatter, "{error}"),
        }
    }
}

fn string(table: &dyn TableLike, key: &str, default: Option<&str>) -> Result<String, SurfaceError> {
    match table.get(key) {
        Some(value) => value
            .as_str()
            .map(str::to_string)
            .ok_or_else(|| SurfaceError::Invalid(format!("{key} must be a string"))),
        None => default
            .map(str::to_string)
            .ok_or_else(|| SurfaceError::Invalid(format!("{key} is required"))),
    }
}

fn boolean(table: &dyn TableLike, key: &str) -> Result<bool, SurfaceError> {
    match table.get(key) {
        Some(value) => value
            .as_bool()
            .ok_or_else(|| SurfaceError::Invalid(format!("{key} must be a boolean"))),
        None => Ok(false),
    }
}

fn relative(value: String, field: &str) -> Result<String, SurfaceError> {
    if value.is_empty()
        || Path::new(&value).is_absolute()
        || value.contains('\\')
        || (value != "."
            && value
                .split('/')
                .any(|part| part.is_empty() || part == "." || part == ".."))
    {
        return Err(SurfaceError::Invalid(format!(
            "{field} must be a normalized repository-relative POSIX path"
        )));
    }
    Ok(value)
}

fn surface_tables(document: &DocumentMut) -> Result<Vec<&dyn TableLike>, SurfaceError> {
    let Some(item) = document.get("surface") else {
        return Ok(Vec::new());
    };
    if let Some(tables) = item.as_array_of_tables() {
        return Ok(tables.iter().map(|table| table as &dyn TableLike).collect());
    }
    let array = item
        .as_array()
        .ok_or_else(|| SurfaceError::Invalid("surface must be a list".to_string()))?;
    array
        .iter()
        .map(|value| {
            value
                .as_inline_table()
                .map(|table| table as &dyn TableLike)
                .ok_or_else(|| SurfaceError::Invalid("surface entries must be tables".to_string()))
        })
        .collect()
}

fn entry(table: &dyn TableLike) -> Result<SurfaceEntry, SurfaceError> {
    let path = relative(string(table, "path", None)?, "surface path")?;
    let mode = string(table, "mode", None)?;
    if !matches!(mode.as_str(), "runtime" | "tool" | "eval") {
        return Err(SurfaceError::Invalid(format!(
            "{path}: unsupported runtime surface mode {mode}"
        )));
    }
    let producer = string(table, "projection_producer", None)?;
    if !matches!(
        producer.as_str(),
        "agent-canon" | "agent-canon-bootstrap" | "agent-canon-log"
    ) {
        return Err(SurfaceError::Invalid(format!(
            "{path}: unsupported runtime surface producer {producer}"
        )));
    }
    let kind = string(table, "projection_kind", None)?;
    if !matches!(
        kind.as_str(),
        "runtime_surface" | "tool_surface" | "eval_surface"
    ) {
        return Err(SurfaceError::Invalid(format!(
            "{path}: unsupported runtime surface kind {kind}"
        )));
    }
    let source = string(table, "source", Some(""))?;
    let source = if source.is_empty() {
        path.clone()
    } else {
        relative(source, &format!("{path}: source"))?
    };
    Ok(SurfaceEntry {
        path,
        mode,
        source,
        projection_producer: producer,
        projection_kind: kind,
        local_override_allowed: boolean(table, "local_override_allowed")?,
        optional: boolean(table, "optional")?,
    })
}

fn forbidden_roots(document: &DocumentMut) -> Result<Vec<String>, SurfaceError> {
    let Some(value) = document.get("projection_forbidden_roots") else {
        return Ok(Vec::new());
    };
    let values = value.as_array().ok_or_else(|| {
        SurfaceError::Invalid("projection_forbidden_roots must be a list".to_string())
    })?;
    values
        .iter()
        .map(|value| {
            let value = value
                .as_str()
                .filter(|value| !value.is_empty())
                .ok_or_else(|| {
                    SurfaceError::Invalid(
                        "projection_forbidden_roots entries must be non-empty strings".to_string(),
                    )
                })?;
            relative(value.to_string(), "projection_forbidden_roots entry")
        })
        .collect()
}

pub(crate) fn selected_manifest_path(root: &Path, prefix: &str, raw_manifest: &Path) -> PathBuf {
    let prefixed = root.join(prefix).join(raw_manifest);
    if prefixed.is_file() {
        prefixed
    } else {
        root.join(raw_manifest)
    }
}

pub(crate) fn load_manifest(
    root: &Path,
    prefix: &str,
    raw_manifest: &Path,
) -> Result<SurfaceManifest, SurfaceError> {
    let path = selected_manifest_path(root, prefix, raw_manifest);
    let text = fs::read_to_string(path).map_err(SurfaceError::Io)?;
    let document = text
        .parse::<DocumentMut>()
        .map_err(|error| SurfaceError::Invalid(error.to_string()))?;
    if document.get("version").and_then(Item::as_integer) != Some(1) {
        return Err(SurfaceError::Invalid("version = 1 is required".to_string()));
    }
    let entries: Vec<SurfaceEntry> = surface_tables(&document)?
        .into_iter()
        .map(entry)
        .collect::<Result<_, _>>()?;
    let mut paths = BTreeSet::new();
    if entries.iter().any(|entry| !paths.insert(&entry.path)) {
        return Err(SurfaceError::Invalid("duplicate surface paths".to_string()));
    }
    let generated_projections =
        generated_skill_projections(root).map_err(SurfaceError::Projection)?;
    let projection_forbidden_roots = forbidden_roots(&document)?;
    let table = document.as_table() as &dyn TableLike;
    let prefix = string(table, "prefix", Some(prefix))?;
    let integration_mode = string(table, "integration_mode", None)?;
    if integration_mode != "agent-canon-runtime" {
        return Err(SurfaceError::Invalid(format!(
            "invalid integration_mode: {integration_mode}"
        )));
    }
    boolean(table, "default_consumer")?;
    let selection = string(table, "selection", None)?;
    if selection != "explicit-opt-in" {
        return Err(SurfaceError::Invalid(format!(
            "invalid selection: {selection}"
        )));
    }
    Ok(SurfaceManifest {
        prefix,
        entries,
        generated_projections,
        projection_forbidden_roots,
    })
}

pub(crate) fn normalized_snapshot(manifest: &SurfaceManifest) -> Value {
    json!({
        "schema": SNAPSHOT_SCHEMA,
        "prefix": &manifest.prefix,
        "entries": &manifest.entries,
        "generated_projections": &manifest.generated_projections,
    })
}

fn check_doc(
    root: &Path,
    prefix: &str,
    manifest: &SurfaceManifest,
) -> Result<Vec<String>, SurfaceError> {
    let prefixed = root.join(prefix).join(DEFAULT_DOC);
    let path = if prefixed.is_file() {
        prefixed
    } else {
        root.join(DEFAULT_DOC)
    };
    let text = if path.is_file() {
        fs::read_to_string(path).map_err(SurfaceError::Io)?
    } else {
        String::new()
    };
    let mut findings: Vec<String> = DOC_MARKERS
        .iter()
        .filter(|marker| !text.contains(**marker))
        .map(|marker| format!("SURFACE_MANIFEST_FINDING={marker}:missing-doc-marker"))
        .collect();
    if manifest.entries.is_empty() {
        findings.push("SURFACE_MANIFEST_FINDING=runtime-inventory:empty-manifest".to_string());
    }
    Ok(findings)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Command {
    Snapshot,
    CheckDoc,
    ForbiddenRoots,
}

#[derive(Debug, PartialEq, Eq)]
struct Args {
    root: PathBuf,
    prefix: String,
    manifest: PathBuf,
    command: Command,
}

fn parse_command(value: &str) -> Result<Command, String> {
    match value {
        "normalized-snapshot" => Ok(Command::Snapshot),
        "check-doc" => Ok(Command::CheckDoc),
        "projection-forbidden-roots" => Ok(Command::ForbiddenRoots),
        _ => Err(format!("invalid choice: {value}")),
    }
}

fn negative_number(value: &str) -> bool {
    let Some(tail) = value.strip_prefix('-') else {
        return false;
    };
    let mut digits = 0;
    let mut dots = 0;
    for character in tail.chars() {
        if character.is_ascii_digit() {
            digits += 1;
        } else if character == '.' {
            dots += 1;
        } else {
            return false;
        }
    }
    digits > 0 && dots <= 1
}

fn parse_args(args: &[String]) -> Result<Option<Args>, String> {
    let mut root = PathBuf::from(".");
    let mut prefix = ".".to_string();
    let mut manifest = PathBuf::from(DEFAULT_MANIFEST);
    let mut command = None;
    let mut options = true;
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        if options && token == "--" {
            options = false;
            index += 1;
            continue;
        }
        if options && token == "-h" {
            return Ok(None);
        }
        if options && token.starts_with("--") {
            let (flag, inline) = token
                .split_once('=')
                .map_or((token.as_str(), None), |(name, value)| (name, Some(value)));
            let matching: Vec<&str> = ["--root", "--prefix", "--manifest", "--help"]
                .into_iter()
                .filter(|option| option.starts_with(flag))
                .collect();
            let option = match matching.as_slice() {
                [option] => *option,
                [] => return Err(format!("unrecognized arguments: {token}")),
                _ => return Err(format!("ambiguous option: {flag}")),
            };
            if option == "--help" {
                if inline.is_some() {
                    return Err("--help does not take a value".to_string());
                }
                return Ok(None);
            }
            let value = if let Some(value) = inline {
                value
            } else {
                index += 1;
                let value = args
                    .get(index)
                    .ok_or_else(|| format!("{option} requires a value"))?;
                if value.starts_with('-') && value != "-" && !negative_number(value) {
                    return Err(format!("{option} requires a value"));
                }
                value
            };
            match option {
                "--root" => root = PathBuf::from(value),
                "--prefix" => prefix = value.to_string(),
                "--manifest" => manifest = PathBuf::from(value),
                _ => unreachable!(),
            }
        } else if options && token.starts_with('-') && token != "-" {
            return Err(format!("unrecognized arguments: {token}"));
        } else if command.is_none() {
            command = Some(parse_command(token)?);
        } else {
            return Err(format!("unrecognized arguments: {token}"));
        }
        index += 1;
    }
    Ok(Some(Args {
        root,
        prefix,
        manifest,
        command: command.ok_or("command is required")?,
    }))
}

fn command_output(
    root: &Path,
    args: &Args,
    manifest: &SurfaceManifest,
) -> Result<(String, i32), SurfaceError> {
    match args.command {
        Command::Snapshot => serde_json::to_string(&normalized_snapshot(manifest))
            .map(|text| (format!("{text}\n"), 0))
            .map_err(|error| SurfaceError::Invalid(error.to_string())),
        Command::ForbiddenRoots => Ok((
            format!("{}\n", manifest.projection_forbidden_roots.join("\n")),
            0,
        )),
        Command::CheckDoc => {
            let findings = check_doc(root, &args.prefix, manifest)?;
            if findings.is_empty() {
                Ok((String::new(), 0))
            } else {
                Ok((format!("{}\n", findings.join("\n")), 1))
            }
        }
    }
}

pub(crate) fn run(args: &[String]) -> i32 {
    let args = match parse_args(args) {
        Ok(Some(args)) => args,
        Ok(None) => {
            print!("{HELP}");
            return 0;
        }
        Err(error) => {
            eprintln!("{HELP}surface-manifest: {error}");
            return 2;
        }
    };
    let result = fs::canonicalize(&args.root)
        .map_err(SurfaceError::Io)
        .and_then(|root| {
            let manifest = load_manifest(&root, &args.prefix, &args.manifest)?;
            command_output(&root, &args, &manifest)
        });
    match result {
        Ok((text, code)) => match io::stdout().write_all(text.as_bytes()) {
            Ok(()) => code,
            Err(error) => {
                eprintln!("SURFACE_MANIFEST_ERROR={error}");
                1
            }
        },
        Err(error) => {
            eprintln!("SURFACE_MANIFEST_ERROR={error}");
            1
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};

    static SEQUENCE: AtomicU64 = AtomicU64::new(0);
    const HEADER: &str =
        "version = 1\nintegration_mode = 'agent-canon-runtime'\nselection = 'explicit-opt-in'\n";
    const ENTRY: &str = "[[surface]]\npath = 'tools'\nmode = 'tool'\nprojection_producer = 'agent-canon'\nprojection_kind = 'tool_surface'\n";

    struct Fixture(PathBuf);

    impl Fixture {
        fn new() -> Self {
            let nanos = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let count = SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let root = std::env::temp_dir().join(format!(
                "agent-canon-surfaces-{}-{nanos}-{count}",
                std::process::id()
            ));
            fs::create_dir_all(&root).unwrap();
            Self(root)
        }

        fn write(&self, relative: &str, text: &str) {
            let path = self.0.join(relative);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, text).unwrap();
        }

        fn load(&self) -> Result<SurfaceManifest, SurfaceError> {
            load_manifest(&self.0, ".", Path::new(DEFAULT_MANIFEST))
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn snapshot_preserves_exact_schema_defaults_unicode_and_entry_order() {
        let fixture = Fixture::new();
        fixture.write(DEFAULT_MANIFEST, &format!("{HEADER}prefix = '.'\n{ENTRY}\n[[surface]]\npath = '資料'\nmode = 'runtime'\nprojection_producer = 'agent-canon-bootstrap'\nprojection_kind = 'runtime_surface'\noptional = true\n"));
        let snapshot = normalized_snapshot(&fixture.load().unwrap());
        assert_eq!(
            snapshot,
            json!({
                "schema": "agent-canon.surface-manifest.v2", "prefix": ".",
                "entries": [
                    {"path": "tools", "mode": "tool", "source": "tools", "projection_producer": "agent-canon", "projection_kind": "tool_surface", "local_override_allowed": false, "optional": false},
                    {"path": "資料", "mode": "runtime", "source": "資料", "projection_producer": "agent-canon-bootstrap", "projection_kind": "runtime_surface", "local_override_allowed": false, "optional": true}
                ],
                "generated_projections": []
            })
        );
        assert!(serde_json::to_string(&snapshot).unwrap().contains("資料"));
    }

    #[test]
    fn prefixed_manifest_wins_and_root_manifest_is_the_fallback() {
        let fixture = Fixture::new();
        fixture.write(
            DEFAULT_MANIFEST,
            &format!("{HEADER}prefix = 'fallback'\n{ENTRY}"),
        );
        let prefixed = format!("selected/{DEFAULT_MANIFEST}");
        fixture.write(&prefixed, &format!("{HEADER}prefix = 'selected'\n{ENTRY}"));
        assert_eq!(
            load_manifest(&fixture.0, "selected", Path::new(DEFAULT_MANIFEST))
                .unwrap()
                .prefix,
            "selected"
        );
        fs::remove_file(fixture.0.join(prefixed)).unwrap();
        assert_eq!(
            load_manifest(&fixture.0, "selected", Path::new(DEFAULT_MANIFEST))
                .unwrap()
                .prefix,
            "fallback"
        );
    }

    #[test]
    fn inline_surface_tables_are_valid_and_invalid_field_types_are_rejected() {
        let fixture = Fixture::new();
        fixture.write(DEFAULT_MANIFEST, &format!("{HEADER}surface = [{{path='tools', mode='tool', projection_producer='agent-canon', projection_kind='tool_surface'}}]\n"));
        assert_eq!(fixture.load().unwrap().entries.len(), 1);
        for (text, expected) in [
            (format!("{HEADER}{ENTRY}{ENTRY}"), "duplicate surface paths"),
            (
                format!(
                    "{HEADER}{}",
                    ENTRY.replace("path = 'tools'", "path = '../tools'")
                ),
                "normalized repository-relative POSIX path",
            ),
            (
                format!(
                    "{HEADER}{}",
                    ENTRY.replace(
                        "projection_producer = 'agent-canon'",
                        "projection_producer = 'legacy'"
                    )
                ),
                "unsupported runtime surface producer",
            ),
            (
                format!("{HEADER}{ENTRY}optional = 'yes'\n"),
                "optional must be a boolean",
            ),
            (
                format!("{}{}", HEADER.replace("explicit-opt-in", "default"), ENTRY),
                "invalid selection",
            ),
        ] {
            fixture.write(DEFAULT_MANIFEST, &text);
            assert!(
                fixture.load().unwrap_err().to_string().contains(expected),
                "{expected}"
            );
        }
    }

    #[test]
    fn document_findings_and_forbidden_roots_keep_existing_outputs() {
        let fixture = Fixture::new();
        fixture.write(
            DEFAULT_MANIFEST,
            &format!("{HEADER}projection_forbidden_roots = ['rust']\n"),
        );
        let manifest = fixture.load().unwrap();
        let args = Args {
            root: fixture.0.clone(),
            prefix: ".".into(),
            manifest: DEFAULT_MANIFEST.into(),
            command: Command::CheckDoc,
        };
        let (output, code) = command_output(&fixture.0, &args, &manifest).unwrap();
        assert_eq!(code, 1);
        assert_eq!(output.lines().count(), 5);
        assert!(output.ends_with("SURFACE_MANIFEST_FINDING=runtime-inventory:empty-manifest\n"));
        let roots_args = Args {
            command: Command::ForbiddenRoots,
            ..args
        };
        assert_eq!(
            command_output(&fixture.0, &roots_args, &manifest).unwrap(),
            ("rust\n".to_string(), 0)
        );
        fixture.write(DEFAULT_MANIFEST, &format!("{HEADER}{ENTRY}"));
        fixture.write(DEFAULT_DOC, &DOC_MARKERS.join("\n"));
        assert!(check_doc(&fixture.0, ".", &fixture.load().unwrap())
            .unwrap()
            .is_empty());
    }

    #[test]
    fn cli_accepts_equals_options_and_rejects_removed_sync_commands() {
        let raw: Vec<String> = [
            "normalized-snapshot",
            "--root=selected",
            "--prefix",
            "nested",
            "--manifest=custom.toml",
        ]
        .into_iter()
        .map(str::to_string)
        .collect();
        assert_eq!(
            parse_args(&raw).unwrap().unwrap(),
            Args {
                root: "selected".into(),
                prefix: "nested".into(),
                manifest: "custom.toml".into(),
                command: Command::Snapshot
            }
        );
        assert!(parse_args(&["link-specs".into()])
            .unwrap_err()
            .contains("invalid choice"));
        assert!(parse_args(&["--root".into(), "--help".into()]).is_err());
        assert!(parse_args(&["--help".into()]).unwrap().is_none());
        assert!(parse_args(&[]).is_err());
    }
}
