// @dependency-start
// contract implementation
// responsibility Checks one selected AgentTeam waterfall gate over a persisted run bundle.
// upstream design ../../../../../agents/COMMUNICATION_PROTOCOL.md active design packet and handoff gates
// upstream implementation active_design_packet.rs owns native active-design packet types and normalization
// upstream implementation report_artifact_checks.rs owns shared report content and schedule checks
// upstream implementation runtime_boundary.rs owns no-follow report bundle reads
// downstream implementation main.rs exposes the native waterfall-gate-check command
// downstream design ../../../../../tools/catalog.yaml registers the read-only Rust route
// downstream test ../tests/waterfall_gate_native.rs replays historical Python CLI records
// @dependency-end

use crate::active_design_packet::{
    active_design_packet_mapping, normalize_active_design_packet_config,
    validate_active_design_packet_reference_projection, ActiveDesignPacketConfig,
    ACTIVE_DESIGN_PACKET_FIELDS,
};
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::report_artifact_checks::{
    check_schedule_artifact, check_work_log_artifact, has_approve_decision,
    is_placeholder_only_section, section_has_content, table_body_rows,
};
use crate::runtime_boundary::{RuntimeArtifactBoundary, RuntimeDirectory, RUNTIME_ROOT_ENV};
use regex::Regex;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::sync::OnceLock;
use yaml_rust2::{Yaml, YamlLoader};

const GATES: [&str; 7] = [
    "requirements",
    "plan",
    "design",
    "document_flow",
    "test",
    "implementation",
    "final",
];

const ACTIVE_DESIGN_FRAME_TERMS: [(&str, &[&str]); 6] = [
    (
        "responsibility_model",
        &["responsibility model", "responsibility_model"],
    ),
    (
        "concept_or_layer_model",
        &[
            "concept graph",
            "concept or layer model",
            "concept/layer model",
            "layer model",
            "concept/layer",
            "concept_or_layer_model",
        ],
    ),
    ("non_goals", &["non-goals", "non_goals", "non goals"]),
    (
        "future_extension_layers",
        &["future extension layers", "future_extension_layers"],
    ),
    ("evaluation_axes", &["evaluation axes", "evaluation_axes"]),
    (
        "canonical_surface_relationships",
        &[
            "canonical-surface relationships",
            "canonical surface relationships",
            "relationship to existing canonical surfaces",
            "canonical_surface_relationships",
        ],
    ),
];

const REQUIREMENTS: [ArtifactCheck<'static>; 2] = [
    ArtifactCheck {
        path: "user_request_contract.md",
        require_filled: true,
        require_approve: false,
        required_sections: &[
            "## Requirements Resolution Sweep",
            "## Resolved From Accumulated Context",
        ],
    },
    ArtifactCheck {
        path: "management_review.md",
        require_filled: true,
        require_approve: true,
        required_sections: &[
            "## Accumulated Context Resolution Review",
            "## Unknown Handling Review",
        ],
    },
];

const PLAN: [ArtifactCheck<'static>; 2] = [
    ArtifactCheck {
        path: "schedule.md",
        require_filled: true,
        require_approve: false,
        required_sections: &[
            "## Stage Plan",
            "## Clause Coverage",
            "## Planned Work Units",
        ],
    },
    ArtifactCheck {
        path: "schedule_review.md",
        require_filled: true,
        require_approve: true,
        required_sections: &[],
    },
];

const TEST_PLAN: [ArtifactCheck<'static>; 1] = [ArtifactCheck {
    path: "test_plan.md",
    require_filled: true,
    require_approve: false,
    required_sections: &[],
}];

const IMPLEMENTATION: [ArtifactCheck<'static>; 1] = [ArtifactCheck {
    path: "change_review.md",
    require_filled: true,
    require_approve: true,
    required_sections: &[
        "## Design-Base Implementation Review",
        "## Canonical Tree-Head Review",
    ],
}];

const FINAL: [ArtifactCheck<'static>; 2] = [
    ArtifactCheck {
        path: "final_review.md",
        require_filled: true,
        require_approve: true,
        required_sections: &[
            "## Design Trace Acceptance",
            "## Planned Work Completion Review",
            "## Spec-To-Product Coverage Review",
            "## Review Finding Incorporation Review",
            "## Post-Fix Full Review Rerun Review",
            "## Canonical Tree-Head Acceptance",
        ],
    },
    ArtifactCheck {
        path: "work_log.md",
        require_filled: true,
        require_approve: false,
        required_sections: &["## Entries"],
    },
];

#[derive(Debug, Clone, Copy)]
struct ArtifactCheck<'a> {
    path: &'a str,
    require_filled: bool,
    require_approve: bool,
    required_sections: &'a [&'static str],
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct GateBlocker {
    code: String,
    owner_gate: String,
}

impl GateBlocker {
    fn design(code: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            owner_gate: "design".to_owned(),
        }
    }

    fn owned_by(code: impl Into<String>, gate: &str) -> Self {
        Self {
            code: code.into(),
            owner_gate: gate.to_owned(),
        }
    }
}

#[derive(Debug)]
struct Arguments {
    run_id: Option<String>,
    report_dir: Option<String>,
    report_root: Option<String>,
    gate: String,
}

enum ParseResult {
    Help,
    Parsed(Arguments),
}

#[derive(Clone, Copy)]
enum ArgumentName {
    RunId,
    ReportDir,
    ReportRoot,
    Gate,
    Help,
}

const ARGUMENTS: [(&str, ArgumentName); 5] = [
    ("--run-id", ArgumentName::RunId),
    ("--report-dir", ArgumentName::ReportDir),
    ("--gate", ArgumentName::Gate),
    ("--report-root", ArgumentName::ReportRoot),
    ("--help", ArgumentName::Help),
];

struct BundleReader {
    root: PathBuf,
    directory: Option<RuntimeDirectory>,
}

impl BundleReader {
    fn open(root: PathBuf) -> Result<Self, String> {
        match RuntimeDirectory::open_nofollow(&root, false) {
            Ok(directory) => Ok(Self {
                root,
                directory: Some(directory),
            }),
            Err(error)
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::NotFound | std::io::ErrorKind::NotADirectory
                ) =>
            {
                Ok(Self {
                    root,
                    directory: None,
                })
            }
            Err(error) => Err(format!(
                "report directory is unavailable: {}: {error}",
                root.display()
            )),
        }
    }

    fn read_stable(&self, relative: &Path) -> Result<Option<Vec<u8>>, String> {
        let Some(directory) = &self.directory else {
            return Ok(None);
        };
        directory
            .read_stable(relative)
            .map(|value| value.map(|(bytes, _snapshot)| bytes))
            .map_err(|error| format!("{}: {error}", self.root.join(relative).display()))
    }
}

struct ActiveDesignPacket {
    config: ActiveDesignPacketConfig,
    design_relative_path: String,
    design_bytes: Vec<u8>,
    design_review_bytes: Vec<u8>,
    document_flow_review_bytes: Vec<u8>,
}

fn usage() -> &'static str {
    "usage: agent-canon waterfall-gate-check (--run-id RUN_ID | --report-dir REPORT_DIR) --gate {requirements,plan,design,document_flow,test,implementation,final} [--report-root REPORT_ROOT]"
}

fn parse_args(args: &[String]) -> Result<ParseResult, String> {
    let mut run_id = None;
    let mut report_dir = None;
    let mut report_root = None;
    let mut gate = None;
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if matches!(argument.as_str(), "-h" | "--help") {
            return Ok(ParseResult::Help);
        }
        let (option, inline_value) = argument
            .split_once('=')
            .map_or((argument.as_str(), None), |(option, value)| {
                (option, Some(value.to_owned()))
            });
        if !option.starts_with("--") {
            return Err(format!("unrecognized argument: {argument}"));
        }
        let name = resolve_long_option_prefix(option, &ARGUMENTS).map_err(|error| match error {
            LongOptionError::Unrecognized => format!("unrecognized argument: {argument}"),
            LongOptionError::Ambiguous(matches) => format!(
                "ambiguous option: {option} could match {}",
                matches.join(", ")
            ),
        })?;
        if matches!(name, ArgumentName::Help) {
            return match inline_value {
                Some(value) => Err(format!(
                    "argument -h/--help: ignored explicit argument '{value}'"
                )),
                None => Ok(ParseResult::Help),
            };
        }
        let value = if let Some(value) = inline_value {
            value
        } else {
            index += 1;
            args.get(index)
                .filter(|value| !value.starts_with("--"))
                .cloned()
                .ok_or_else(|| format!("{option} requires one value"))?
        };
        match name {
            ArgumentName::RunId => run_id = Some(value),
            ArgumentName::ReportDir => report_dir = Some(value),
            ArgumentName::ReportRoot => report_root = Some(value),
            ArgumentName::Gate => gate = Some(value),
            ArgumentName::Help => unreachable!("help option handled before value parsing"),
        }
        index += 1;
    }
    let gate = gate.ok_or_else(|| "the following arguments are required: --gate".to_owned())?;
    if !GATES.contains(&gate.as_str()) {
        return Err(format!(
            "invalid choice: {gate:?} (choose from {})",
            GATES.join(", ")
        ));
    }
    Ok(ParseResult::Parsed(Arguments {
        run_id,
        report_dir,
        report_root,
        gate,
    }))
}

fn source_root_from_context() -> Result<PathBuf, String> {
    if let Some(value) = env::var_os("AGENT_CANON_SOURCE_ROOT").filter(|value| !value.is_empty()) {
        return Ok(PathBuf::from(value));
    }
    env::current_dir().map_err(|error| format!("cannot resolve current source context: {error}"))
}

fn runtime_root_from_context() -> Option<PathBuf> {
    env::var_os(RUNTIME_ROOT_ENV)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
}

fn reject_symlink_components(path: &Path) -> Result<(), String> {
    let mut component = Some(path);
    while let Some(current) = component {
        match fs::symlink_metadata(current) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(format!(
                    "runtime artifact contains a symlink component: {}",
                    current.display()
                ));
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(format!(
                    "cannot inspect runtime artifact path {}: {error}",
                    current.display()
                ));
            }
        }
        component = current.parent();
    }
    Ok(())
}

fn validate_active_report_root(report_root: &Path) -> Result<(), String> {
    let source_root = source_root_from_context()?;
    if let Some(runtime_root) = runtime_root_from_context() {
        let boundary =
            RuntimeArtifactBoundary::for_source(&source_root, Some(&runtime_root), false)?;
        boundary.resolve(report_root)?;
        return Ok(());
    }
    let source_root = fs::canonicalize(&source_root).unwrap_or(source_root);
    if report_root.starts_with(&source_root) {
        return Err(format!(
            "runtime artifact must not resolve into AgentCanon source: {}",
            report_root.display()
        ));
    }
    Ok(())
}

fn report_root_for_run_id(
    report_root: Option<&str>,
    source_root: &Path,
) -> Result<PathBuf, String> {
    if let Some(runtime_root) = runtime_root_from_context() {
        let boundary =
            RuntimeArtifactBoundary::for_source(source_root, Some(&runtime_root), false)?;
        let declared = report_root.unwrap_or("reports/agents");
        return boundary.resolve(Path::new(declared));
    }
    let Some(declared) = report_root else {
        return Err(format!(
            "explicit external runtime root required; pass an absolute --report-root or set {RUNTIME_ROOT_ENV}"
        ));
    };
    let declared = Path::new(declared);
    if !declared.is_absolute() {
        return Err(format!(
            "explicit external runtime root required; pass an absolute --report-root or set {RUNTIME_ROOT_ENV}"
        ));
    }
    reject_symlink_components(declared)?;
    let root = resolve_non_strict(declared)?;
    let source = fs::canonicalize(source_root).unwrap_or_else(|_| source_root.to_path_buf());
    if root.starts_with(&source) {
        return Err(format!(
            "absolute --report-root must be outside the AgentCanon source tree: {}",
            root.display()
        ));
    }
    Ok(root)
}

fn resolve_non_strict(path: &Path) -> Result<PathBuf, String> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .map_err(|error| format!("cannot resolve relative report path: {error}"))?
            .join(path)
    };
    let mut missing = Vec::new();
    let mut cursor = absolute.as_path();
    loop {
        match fs::canonicalize(cursor) {
            Ok(mut resolved) => {
                for component in missing.iter().rev() {
                    resolved.push(component);
                }
                return Ok(resolved);
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                let Some(name) = cursor.file_name() else {
                    return Err(format!(
                        "cannot resolve report path {}: {error}",
                        absolute.display()
                    ));
                };
                missing.push(name.to_os_string());
                cursor = cursor.parent().ok_or_else(|| {
                    format!("cannot resolve report path {}: {error}", absolute.display())
                })?;
            }
            Err(error) => {
                return Err(format!(
                    "cannot resolve report path {}: {error}",
                    absolute.display()
                ))
            }
        }
    }
}

fn resolve_report_dir(arguments: &Arguments) -> Result<PathBuf, String> {
    let run_id = arguments
        .run_id
        .as_deref()
        .filter(|value| !value.is_empty());
    let report_dir = arguments
        .report_dir
        .as_deref()
        .filter(|value| !value.is_empty());
    if run_id.is_some() == report_dir.is_some() {
        return Err("Provide exactly one of --run-id or --report-dir.".to_owned());
    }
    if let Some(report_dir) = report_dir {
        return resolve_non_strict(Path::new(report_dir));
    }
    let source_root = source_root_from_context()?;
    let report_root = report_root_for_run_id(arguments.report_root.as_deref(), &source_root)?;
    resolve_non_strict(&report_root.join(run_id.expect("exactly one path selector")))
}

fn yaml_mapping_has_string_keys(value: &Yaml) -> bool {
    value
        .as_hash()
        .is_some_and(|mapping| mapping.keys().all(|key| key.as_str().is_some()))
}

fn yaml_field<'a>(value: &'a Yaml, key: &str) -> Option<&'a Yaml> {
    value.as_hash()?.get(&Yaml::String(key.to_owned()))
}

fn design_blocker(code: impl Into<String>) -> GateBlocker {
    GateBlocker::design(code)
}

fn normalize_packet_error(message: &str) -> String {
    for (needle, replacement) in [
        (":field_unknown:", "active_design_packet_field_unknown:"),
        (":field_missing:", "active_design_packet_field_missing:"),
        (":schema_unknown:", "active_design_packet_schema_unknown:"),
        (":field_invalid:", "active_design_packet_field_invalid:"),
    ] {
        if let Some((_, suffix)) = message.rsplit_once(needle) {
            return format!("team_manifest.yaml:{replacement}{suffix}");
        }
    }
    let last = message.rsplit('.').next().unwrap_or(message);
    let field = last.split(':').next().unwrap_or(last);
    format!("team_manifest.yaml:active_design_packet_field_invalid:{field}")
}

fn packet_relative_path(value: &str) -> Result<(PathBuf, String), &'static str> {
    if value.is_empty() {
        return Err("not_relative");
    }
    let path = Path::new(value);
    if path.is_absolute() {
        return Err("not_relative");
    }
    let mut relative = PathBuf::new();
    let mut display_parts = Vec::new();
    for component in path.components() {
        match component {
            Component::Normal(part) => {
                relative.push(part);
                display_parts.push(part.to_string_lossy().into_owned());
            }
            Component::CurDir => {}
            Component::ParentDir => return Err("outside_bundle"),
            Component::RootDir | Component::Prefix(_) => return Err("not_relative"),
        }
    }
    if display_parts.is_empty() {
        return Err("not_relative");
    }
    Ok((relative, display_parts.join("/")))
}

fn packet_artifact(
    reader: &BundleReader,
    field: &str,
    declared_path: &str,
) -> Result<(Vec<u8>, String), GateBlocker> {
    let (relative, normalized) = packet_relative_path(declared_path).map_err(|reason| {
        let kind = if reason == "outside_bundle" {
            "active_design_packet_path_outside_bundle"
        } else {
            "active_design_packet_field_invalid"
        };
        design_blocker(format!("team_manifest.yaml:{kind}:{field}"))
    })?;
    match reader.read_stable(&relative) {
        Ok(Some(bytes)) => Ok((bytes, normalized)),
        Ok(None) | Err(_) => Err(design_blocker(format!(
            "team_manifest.yaml:active_design_packet_field_invalid:{field}"
        ))),
    }
}

fn load_active_design_packet(
    reader: &BundleReader,
) -> Result<ActiveDesignPacket, Vec<GateBlocker>> {
    let manifest = match reader.read_stable(Path::new("team_manifest.yaml")) {
        Ok(Some(bytes)) => bytes,
        Ok(None) => return Err(vec![design_blocker("team_manifest.yaml:missing")]),
        Err(_) => {
            return Err(vec![design_blocker(
                "team_manifest.yaml:active_design_packet_field_invalid:manifest",
            )])
        }
    };
    let text = std::str::from_utf8(&manifest).map_err(|_| {
        vec![design_blocker(
            "team_manifest.yaml:active_design_packet_field_invalid:manifest",
        )]
    })?;
    let documents = YamlLoader::load_from_str(text).map_err(|_| {
        vec![design_blocker(
            "team_manifest.yaml:active_design_packet_field_invalid:manifest",
        )]
    })?;
    if documents.is_empty() {
        return Err(vec![design_blocker(
            "team_manifest.yaml:active_design_packet_missing",
        )]);
    }
    if documents.len() > 1 {
        return Err(vec![design_blocker(
            "team_manifest.yaml:active_design_packet_field_invalid:manifest",
        )]);
    }
    let root = &documents[0];
    if !yaml_mapping_has_string_keys(root) {
        return Err(vec![design_blocker(
            "team_manifest.yaml:active_design_packet_missing",
        )]);
    }
    let Some(run) = yaml_field(root, "run") else {
        return Err(vec![design_blocker(
            "team_manifest.yaml:active_design_packet_missing",
        )]);
    };
    if !yaml_mapping_has_string_keys(run) {
        return Err(vec![design_blocker(
            "team_manifest.yaml:active_design_packet_missing",
        )]);
    }
    let Some(packet) = yaml_field(run, "active_design_packet") else {
        return Err(vec![design_blocker(
            "team_manifest.yaml:active_design_packet_missing",
        )]);
    };
    if !yaml_mapping_has_string_keys(packet) {
        return Err(vec![design_blocker(
            "team_manifest.yaml:active_design_packet_missing",
        )]);
    }
    let packet_map = packet.as_hash().expect("string-key mapping was checked");
    let known_fields = ACTIVE_DESIGN_PACKET_FIELDS
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    let mut unknown_fields = packet_map
        .keys()
        .filter_map(Yaml::as_str)
        .filter(|field| !known_fields.contains(field))
        .collect::<Vec<_>>();
    unknown_fields.sort_unstable();
    if !unknown_fields.is_empty() {
        return Err(vec![design_blocker(format!(
            "team_manifest.yaml:active_design_packet_field_unknown:{}",
            unknown_fields.join(",")
        ))]);
    }
    let missing_fields = ACTIVE_DESIGN_PACKET_FIELDS
        .iter()
        .filter(|field| yaml_field(packet, field).is_none())
        .map(|field| {
            design_blocker(format!(
                "team_manifest.yaml:active_design_packet_field_missing:{field}"
            ))
        })
        .collect::<Vec<_>>();
    if !missing_fields.is_empty() {
        return Err(missing_fields);
    }
    let config = normalize_active_design_packet_config(packet, "active_design_packet")
        .map_err(|error| vec![design_blocker(normalize_packet_error(error.message()))])?;
    let mapping = active_design_packet_mapping(&config);
    let projection = yaml_field(run, "active_design_packet_reference_projection");
    if !projection
        .is_some_and(|value| validate_active_design_packet_reference_projection(&mapping, value))
    {
        return Err(vec![design_blocker(
            "team_manifest.yaml:active_design_packet_field_invalid:active_design_packet_reference_projection",
        )]);
    }
    if validate_active_report_root(&reader.root).is_err() {
        return Err(vec![design_blocker(
            "team_manifest.yaml:active_design_packet_field_invalid:manifest",
        )]);
    }
    let mut resolved = BTreeMap::new();
    let mut path_blockers = Vec::new();
    for (field, declared_path) in [
        ("design_artifact", config.design_artifact.as_str()),
        (
            "design_review_artifact",
            config.design_review_artifact.as_str(),
        ),
        (
            "document_flow_review_artifact",
            config.document_flow_review_artifact.as_str(),
        ),
    ] {
        match packet_artifact(reader, field, declared_path) {
            Ok(value) => {
                resolved.insert(field, value);
            }
            Err(blocker) => path_blockers.push(blocker),
        }
    }
    if !path_blockers.is_empty() {
        return Err(path_blockers);
    }
    let (design_bytes, design_relative_path) = resolved
        .remove("design_artifact")
        .expect("design artifact was resolved");
    let (design_review_bytes, _) = resolved
        .remove("design_review_artifact")
        .expect("design review artifact was resolved");
    let (document_flow_review_bytes, _) = resolved
        .remove("document_flow_review_artifact")
        .expect("document flow review artifact was resolved");
    Ok(ActiveDesignPacket {
        config,
        design_relative_path,
        design_bytes,
        design_review_bytes,
        document_flow_review_bytes,
    })
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn review_target_sha256_regex() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(r"(?i)\breview_target_sha256\s*=\s*`?([0-9a-f]{64})`?")
            .expect("fixed review target digest regex")
    })
}

fn design_artifact_path_regex() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(r"(?im)^\s*-\s*Design artifact path:\s*`?([^`\r\n]+?)`?\s*$")
            .expect("fixed design artifact path regex")
    })
}

fn review_target_sha256(text: &str) -> Option<String> {
    review_target_sha256_regex()
        .captures_iter(text)
        .last()
        .and_then(|captures| captures.get(1))
        .map(|value| value.as_str().to_ascii_lowercase())
}

fn review_design_artifact_path(text: &str) -> Option<String> {
    design_artifact_path_regex()
        .captures_iter(text)
        .last()
        .and_then(|captures| captures.get(1))
        .map(|value| {
            value
                .as_str()
                .trim()
                .trim_matches(|character| character == '\'' || character == '"')
                .to_owned()
        })
}

fn decision_is_approve(text: &str) -> bool {
    has_approve_decision(text)
}

fn review_identity_blockers(
    path: &str,
    text: &str,
    expected_design_path: &str,
    expected_sha256: &str,
) -> Vec<GateBlocker> {
    let relative_path = Path::new(path)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or(path);
    let mut blockers = Vec::new();
    match review_design_artifact_path(text) {
        None => blockers.push(design_blocker(format!(
            "{relative_path}:design_artifact_path_missing"
        ))),
        Some(path) if path != expected_design_path => blockers.push(design_blocker(format!(
            "{relative_path}:design_artifact_path_mismatch"
        ))),
        Some(_) => {}
    }
    match review_target_sha256(text) {
        None => blockers.push(design_blocker(format!(
            "{relative_path}:review_target_sha256_missing"
        ))),
        Some(digest) if digest != expected_sha256 => blockers.push(design_blocker(format!(
            "{relative_path}:review_target_sha256_mismatch"
        ))),
        Some(_) => {}
    }
    if !decision_is_approve(text) {
        blockers.push(design_blocker(format!(
            "{relative_path}:decision_not_approve"
        )));
    }
    blockers
}

fn decode_text(bytes: &[u8], path: &str) -> Result<String, String> {
    std::str::from_utf8(bytes)
        .map(str::to_owned)
        .map_err(|error| format!("{path}: invalid UTF-8: {error}"))
}

fn check_active_document_flow_review(packet: &ActiveDesignPacket) -> Vec<GateBlocker> {
    if !packet.config.document_flow_required {
        return Vec::new();
    }
    let review_path = packet.config.document_flow_review_artifact.as_str();
    let design_text = match decode_text(&packet.design_bytes, &packet.config.design_artifact) {
        Ok(text) => text,
        Err(_) => return vec![design_blocker("design_brief.md:read_failed")],
    };
    let review_text = match decode_text(&packet.document_flow_review_bytes, review_path) {
        Ok(text) => text,
        Err(_) => {
            return vec![design_blocker(format!(
                "{}:read_failed",
                Path::new(review_path)
                    .file_name()
                    .and_then(|name| name.to_str())
                    .unwrap_or(review_path)
            ))]
        }
    };
    review_identity_blockers(
        review_path,
        &review_text,
        &packet.config.design_artifact,
        &sha256_hex(design_text.as_bytes()),
    )
}

fn section_body(text: &str, heading: &str) -> String {
    let mut in_section = false;
    let mut body = Vec::new();
    for line in text.lines() {
        let stripped = crate::python_text::python_strip(line);
        if stripped.starts_with("## ") {
            if in_section {
                break;
            }
            in_section = stripped == heading;
            continue;
        }
        if in_section {
            body.push(line);
        }
    }
    body.join("\n")
}

fn term_has_content(body: &str, accepted_terms: &[&str]) -> bool {
    const PLACEHOLDERS: [&str; 6] = ["", "-", "todo", "tbd", "none", "n/a"];
    let lines = body.lines().collect::<Vec<_>>();
    for (index, line) in lines.iter().enumerate() {
        let stripped = crate::python_text::python_strip(line);
        let normalized = stripped.trim_start_matches(['-', '*', ' ']).to_lowercase();
        let heading_normalized = normalized.trim_start_matches('#').trim().to_owned();
        if accepted_terms
            .iter()
            .any(|term| heading_normalized == *term)
        {
            for following in &lines[index + 1..] {
                let following_stripped = crate::python_text::python_strip(following);
                if following_stripped.is_empty() {
                    continue;
                }
                if following_stripped.starts_with('#') {
                    break;
                }
                if !PLACEHOLDERS.contains(&following_stripped.to_lowercase().as_str()) {
                    return true;
                }
            }
            continue;
        }
        let Some(matched_term) = accepted_terms
            .iter()
            .find(|term| normalized.starts_with(**term))
        else {
            continue;
        };
        let remainder = normalized[matched_term.len()..].trim();
        let Some(value) = remainder
            .strip_prefix(':')
            .or_else(|| remainder.strip_prefix('-'))
        else {
            continue;
        };
        if !PLACEHOLDERS.contains(&value.trim()) {
            return true;
        }
    }
    false
}

fn check_abstract_design_frame(text: &str, artifact_name: &str) -> Vec<GateBlocker> {
    let body = section_body(text, "## Abstract Design Frame");
    ACTIVE_DESIGN_FRAME_TERMS
        .iter()
        .filter(|(_term_id, accepted_terms)| !term_has_content(&body, accepted_terms))
        .map(|(term_id, _)| {
            design_blocker(format!(
                "{artifact_name}:abstract_design_frame_missing:{term_id}"
            ))
        })
        .collect()
}

fn check_user_request_contract(text: &str) -> Vec<String> {
    let mut blockers = Vec::new();
    if table_body_rows(text, "## Must-Do Clauses").is_empty() {
        blockers.push("user_request_contract.md:must_do_clauses_empty".to_owned());
    }
    if table_body_rows(text, "## Completion Evidence Clauses").is_empty() {
        blockers.push("user_request_contract.md:completion_evidence_empty".to_owned());
    }
    for heading in [
        "## Must-Do Clauses",
        "## Must-Not-Do Clauses",
        "## Completion Evidence Clauses",
    ] {
        for row in table_body_rows(text, heading) {
            if row.contains("unknown_or_open_question") {
                let slug = heading
                    .trim_start_matches("## ")
                    .to_lowercase()
                    .replace(['-', ' '], "_");
                blockers.push(format!(
                    "user_request_contract.md:active_unknown_clause:{slug}"
                ));
            }
        }
    }
    blockers
}

fn check_artifact_text(check: ArtifactCheck<'_>, text: &str) -> Vec<String> {
    let mut blockers = Vec::new();
    if check.require_filled && is_placeholder_only_section(text) {
        blockers.push(format!("{}:template_or_placeholder_remaining", check.path));
    }
    for section in check.required_sections {
        if !section_has_content(text, section) {
            let slug = section
                .strip_prefix("## ")
                .unwrap_or(section)
                .to_lowercase()
                .replace(' ', "_");
            blockers.push(format!("{}:section_empty_or_missing:{slug}", check.path));
        }
    }
    match check.path {
        "user_request_contract.md" => blockers.extend(check_user_request_contract(text)),
        "design_brief.md" => blockers.extend(
            check_abstract_design_frame(text, "design_brief.md")
                .into_iter()
                .map(|blocker| blocker.code),
        ),
        "schedule.md" => blockers.extend(check_schedule_artifact(text)),
        "work_log.md" => blockers.extend(check_work_log_artifact(text)),
        _ => {}
    }
    if check.require_approve && !decision_is_approve(text) {
        blockers.push(format!("{}:decision_not_approve", check.path));
    }
    blockers
}

fn check_artifact(reader: &BundleReader, check: ArtifactCheck<'_>) -> Result<Vec<String>, String> {
    let Some(bytes) = reader.read_stable(Path::new(check.path))? else {
        return Ok(vec![format!("{}:missing", check.path)]);
    };
    let text = decode_text(&bytes, check.path)?;
    Ok(check_artifact_text(check, &text))
}

fn check_active_design_packet(packet: &ActiveDesignPacket) -> Result<Vec<GateBlocker>, String> {
    let design_path = packet.config.design_artifact.as_str();
    let design_text = decode_text(&packet.design_bytes, design_path)?;
    let review_path = packet.config.design_review_artifact.as_str();
    let review_text = decode_text(&packet.design_review_bytes, review_path)?;
    let check = ArtifactCheck {
        path: &packet.design_relative_path,
        require_filled: true,
        require_approve: false,
        required_sections: &[
            "## Abstract Design Frame",
            "## Implementation Source Packet",
            "## Design-To-Implementation Trace",
        ],
    };
    let mut blockers = check_artifact_text(check, &design_text)
        .into_iter()
        .map(GateBlocker::design)
        .collect::<Vec<_>>();
    if blockers.is_empty() {
        blockers.extend(check_abstract_design_frame(
            &design_text,
            &packet.design_relative_path,
        ));
    }
    blockers.extend(review_identity_blockers(
        review_path,
        &review_text,
        &packet.config.design_artifact,
        &sha256_hex(&packet.design_bytes),
    ));
    blockers.extend(check_active_document_flow_review(packet));
    Ok(blockers)
}

fn gate_checks(gate: &str) -> &'static [ArtifactCheck<'static>] {
    match gate {
        "requirements" => &REQUIREMENTS,
        "plan" => &PLAN,
        "test" => &TEST_PLAN,
        "implementation" => &IMPLEMENTATION,
        "final" => &FINAL,
        _ => &[],
    }
}

fn next_action_for_gate(gate: &str, blockers: &[GateBlocker]) -> String {
    let owner_gate = blockers
        .iter()
        .find(|blocker| blocker.owner_gate != gate)
        .map(|blocker| blocker.owner_gate.as_str())
        .unwrap_or(gate);
    format!("return_to_{owner_gate}_owner_until_gate_approves")
}

fn evaluate(reader: &BundleReader, gate: &str) -> Result<Vec<GateBlocker>, String> {
    let mut blockers = Vec::new();
    if matches!(gate, "design" | "document_flow" | "implementation") {
        match load_active_design_packet(reader) {
            Ok(packet) => {
                if gate == "document_flow" {
                    blockers.extend(check_active_document_flow_review(&packet));
                } else {
                    blockers.extend(check_active_design_packet(&packet)?);
                }
            }
            Err(packet_blockers) => blockers.extend(packet_blockers),
        }
        if gate == "implementation" {
            for check in &IMPLEMENTATION {
                blockers.extend(
                    check_artifact(reader, *check)?
                        .into_iter()
                        .map(|code| GateBlocker::owned_by(code, "implementation")),
                );
            }
        }
    } else {
        for check in gate_checks(gate) {
            blockers.extend(
                check_artifact(reader, *check)?
                    .into_iter()
                    .map(|code| GateBlocker::owned_by(code, gate)),
            );
        }
    }
    Ok(blockers)
}

pub fn run(args: &[String]) -> i32 {
    let arguments = match parse_args(args) {
        Ok(ParseResult::Help) => {
            println!(
                "{}\n\nFail unless the requested intermediate waterfall gate is ready.",
                usage()
            );
            return 0;
        }
        Ok(ParseResult::Parsed(arguments)) => arguments,
        Err(error) => {
            eprintln!("{}\nerror: {error}", usage());
            return 2;
        }
    };
    let report_dir = match resolve_report_dir(&arguments) {
        Ok(path) => path,
        Err(error) if error == "Provide exactly one of --run-id or --report-dir." => {
            eprintln!("{error}");
            return 1;
        }
        Err(error) => {
            eprintln!("{error}");
            return 1;
        }
    };
    let reader = match BundleReader::open(report_dir.clone()) {
        Ok(reader) => reader,
        Err(error) => {
            eprintln!("{error}");
            return 1;
        }
    };
    let blockers = match evaluate(&reader, &arguments.gate) {
        Ok(blockers) => blockers,
        Err(error) => {
            eprintln!("waterfall gate check failed: {error}");
            return 1;
        }
    };
    let ready = blockers.is_empty();
    println!("REPORT_DIR={}", reader.root.display());
    println!("WATERFALL_GATE={}", arguments.gate);
    println!("WATERFALL_GATE_READY={}", if ready { "yes" } else { "no" });
    if !ready {
        println!(
            "WATERFALL_GATE_BLOCKERS={}",
            blockers
                .iter()
                .map(|blocker| blocker.code.as_str())
                .collect::<Vec<_>>()
                .join(",")
        );
        println!(
            "NEXT_ACTION={}",
            next_action_for_gate(&arguments.gate, &blockers)
        );
        return 1;
    }
    println!("NEXT_ACTION=proceed_to_next_waterfall_gate");
    0
}
