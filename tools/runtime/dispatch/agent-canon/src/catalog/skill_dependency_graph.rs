// @dependency-start
// contract implementation
// responsibility Reconstructs and validates the canonical v2 public skill/dependency graph and its Mermaid reader artifact.
// upstream design ../../../../../../documents/design/skill-tool-invocation-graph.md owns graph identity and readback rules
// upstream implementation ./skill_routes.rs supplies catalog, route, dependency, and invocation-order values
// upstream implementation ../source_mutation.rs owns capability-bound tracked-pair writes
// downstream implementation ../main.rs exposes the native graph and readback selectors
// downstream test ../../tests/skill_dependency_graph_native.rs qualifies graph and Mermaid readback
// @dependency-end

use super::skill_routes::{
    derive_skill_invocation_order, load_skill_catalog, load_skill_dependency_map,
    load_skill_route_rules, SkillRoutingRule,
};
use crate::python_cli_integer::is_argparse_negative_number;
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::runtime_boundary::RuntimeArtifactBoundary;
use crate::source_mutation::SourceMutationCapability;
use icu_casemap::CaseMapper;
use icu_normalizer::ComposingNormalizer;
use regex::Regex;
use serde::Serialize;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::sync::OnceLock;
use yaml_rust2::Yaml;

pub const GRAPH_SCHEMA: &str = "agent_canon.skill_tool_invocation_graph.v2";
pub const CHECK_SCHEMA: &str = "agent_canon.skill_tool_invocation_check.v1";
pub const GRAPH_ARTIFACT_ID: &str = "skill-tool-invocation-graph";
pub const GRAPH_MARKDOWN_PATH: &str = "documents/runtime/skill-dependency-graph.md";
pub const GRAPH_JSON_PATH: &str = "documents/runtime/skill-dependency-graph.json";
const DEFAULT_EXTERNAL_GRAPH_PATH: &str = "graphs/skill-dependency-graph.md";
const SOURCE_MUTATION_EVIDENCE_PATH: &str = "graphs/skill-dependency-graph-source-mutation.json";
const SOURCE_MUTATION_ALLOWED_PATHS: [&str; 2] = [GRAPH_MARKDOWN_PATH, GRAPH_JSON_PATH];

#[derive(Serialize)]
struct CheckOutput<'a> {
    schema: &'static str,
    status: &'static str,
    #[serde(flatten)]
    result: CheckResult<'a>,
}

#[derive(Serialize)]
#[serde(untagged)]
enum CheckResult<'a> {
    Pass {
        skill_count: usize,
        command_count: usize,
        tool_count: usize,
        edge_count: usize,
        graph_digest: &'a str,
        json_digest: &'a str,
        mermaid_digest: &'a str,
    },
    Fail {
        error: &'a str,
    },
}

/// Read-only public checker; the graph writer remains a separate operation.
pub fn run(args: &[String]) -> i32 {
    let mut root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .expect("crate is nested below source root")
        .to_path_buf();
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if matches!(argument.as_str(), "-h" | "--help") {
            println!("usage: agent-canon check-skill-tool-invocation-graph [--root ROOT]");
            return 0;
        }
        let (option, inline) = argument
            .split_once('=')
            .map_or((argument.as_str(), None), |(key, value)| (key, Some(value)));
        if !option.starts_with("--") || option == "--" || !"--root".starts_with(option) {
            eprintln!("unrecognized arguments: {argument}");
            return 2;
        }
        let value = if let Some(value) = inline {
            value
        } else {
            index += 1;
            let Some(value) = args.get(index).filter(|value| !value.starts_with('-')) else {
                eprintln!("argument --root: expected one argument");
                return 2;
            };
            value
        };
        root = PathBuf::from(value);
        index += 1;
    }
    match check_artifacts(&root) {
        Ok(summary) => {
            println!(
                "{}",
                serde_json::to_string(&CheckOutput {
                    schema: CHECK_SCHEMA,
                    status: "pass",
                    result: CheckResult::Pass {
                        skill_count: summary.skill_count,
                        command_count: summary.command_count,
                        tool_count: summary.tool_count,
                        edge_count: summary.edge_count,
                        graph_digest: &summary.graph_digest,
                        json_digest: &summary.json_digest,
                        mermaid_digest: &summary.mermaid_digest
                    }
                })
                .expect("typed checker output serializes")
            );
            0
        }
        Err(error) => {
            println!(
                "{}",
                serde_json::to_string(&CheckOutput {
                    schema: CHECK_SCHEMA,
                    status: "fail",
                    result: CheckResult::Fail { error: &error }
                })
                .expect("typed checker output serializes")
            );
            2
        }
    }
}

#[derive(Clone, Copy)]
enum GraphCliOption {
    Help,
    Root,
    Output,
    RuntimeRoot,
    MutationCapability,
    SourceMutation,
    SourceMutationEvidence,
}

const GRAPH_CLI_OPTIONS: &[(&str, GraphCliOption)] = &[
    ("--help", GraphCliOption::Help),
    ("--root", GraphCliOption::Root),
    ("--output", GraphCliOption::Output),
    ("--runtime-root", GraphCliOption::RuntimeRoot),
    (
        "--source-mutation-capability-json",
        GraphCliOption::MutationCapability,
    ),
    (
        "--mutation-capability-json",
        GraphCliOption::MutationCapability,
    ),
    ("--source-mutation", GraphCliOption::SourceMutation),
    (
        "--source-mutation-evidence",
        GraphCliOption::SourceMutationEvidence,
    ),
];

struct GraphCliArgs {
    command: String,
    root: PathBuf,
    output: Option<PathBuf>,
    runtime_root: Option<PathBuf>,
    mutation_capability: Option<PathBuf>,
    source_mutation: bool,
    source_mutation_evidence: Option<PathBuf>,
}

fn graph_cli_usage(command: Option<&str>) -> String {
    match command {
        Some("check") => {
            "usage: agent-canon skill-dependency-map check [--root ROOT]\n\nValidate the skill dependency map and generated graph artifacts.".to_owned()
        }
        Some("graph") => {
            "usage: agent-canon skill-dependency-map graph [--root ROOT] [--output OUTPUT] [--runtime-root RUNTIME_ROOT] [--source-mutation-capability-json PATH] [--source-mutation] [--source-mutation-evidence PATH]\n\nGenerate graph artifacts outside the checkout unless the exact tracked-pair capability is supplied.".to_owned()
        }
        _ => {
            "usage: agent-canon skill-dependency-map [-h] {check,graph} ...\n\nMaterialize and validate the deterministic public skill/dependency graph.".to_owned()
        }
    }
}

fn default_source_root() -> PathBuf {
    env::var_os("AGENT_CANON_SOURCE_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .ancestors()
                .nth(4)
                .expect("native crate is nested below source root")
                .to_path_buf()
        })
}

fn parse_graph_cli(args: &[String]) -> Result<Option<GraphCliArgs>, String> {
    let Some(command) = args.first() else {
        return Err("the following arguments are required: command".to_owned());
    };
    if matches!(command.as_str(), "-h" | "--help") {
        return Ok(None);
    }
    if !matches!(command.as_str(), "check" | "graph") {
        return Err(format!(
            "invalid choice: '{command}' (choose from 'check', 'graph')"
        ));
    }
    let mut parsed = GraphCliArgs {
        command: command.clone(),
        root: default_source_root(),
        output: None,
        runtime_root: None,
        mutation_capability: None,
        source_mutation: false,
        source_mutation_evidence: None,
    };
    let mut index = 1;
    while index < args.len() {
        let token = &args[index];
        if matches!(token.as_str(), "-h" | "--help") {
            return Ok(None);
        }
        if !token.starts_with("--") {
            return Err(format!("unrecognized arguments: {token}"));
        }
        let (option_text, inline_value) = match token.split_once('=') {
            Some((option, value)) => (option, Some(value.to_owned())),
            None => (token.as_str(), None),
        };
        let option = resolve_long_option_prefix(option_text, GRAPH_CLI_OPTIONS).map_err(
            |error| match error {
                LongOptionError::Unrecognized => format!("unrecognized arguments: {token}"),
                LongOptionError::Ambiguous(_) => format!("ambiguous option: {option_text}"),
            },
        )?;
        if matches!(option, GraphCliOption::Help) {
            if inline_value.is_some() {
                return Err(format!("ignored explicit argument for --help: {token}"));
            }
            return Ok(None);
        }
        if matches!(option, GraphCliOption::SourceMutation) {
            if parsed.command != "graph" {
                return Err(format!("unrecognized arguments: {token}"));
            }
            if inline_value.is_some() {
                return Err(format!(
                    "ignored explicit argument for --source-mutation: {token}"
                ));
            }
            parsed.source_mutation = true;
            index += 1;
            continue;
        }
        if parsed.command == "check"
            && !matches!(option, GraphCliOption::Root | GraphCliOption::Help)
        {
            return Err(format!("unrecognized arguments: {token}"));
        }
        let value = if let Some(value) = inline_value {
            value
        } else {
            index += 1;
            let Some(value) = args.get(index) else {
                return Err(format!("argument {option_text}: expected one argument"));
            };
            if value.starts_with('-') && !is_argparse_negative_number(value) {
                return Err(format!("argument {option_text}: expected one argument"));
            }
            value.clone()
        };
        match option {
            GraphCliOption::Root => parsed.root = PathBuf::from(value),
            GraphCliOption::Output => parsed.output = Some(PathBuf::from(value)),
            GraphCliOption::RuntimeRoot => parsed.runtime_root = Some(PathBuf::from(value)),
            GraphCliOption::MutationCapability => {
                parsed.mutation_capability = Some(PathBuf::from(value))
            }
            GraphCliOption::SourceMutationEvidence => {
                parsed.source_mutation_evidence = Some(PathBuf::from(value))
            }
            GraphCliOption::Help | GraphCliOption::SourceMutation => unreachable!(),
        }
        index += 1;
    }
    Ok(Some(parsed))
}

/// Run the former skill dependency map operations through the native graph owner.
pub fn run_graph_cli(args: &[String]) -> i32 {
    let parsed = match parse_graph_cli(args) {
        Ok(Some(parsed)) => parsed,
        Ok(None) => {
            println!("{}", graph_cli_usage(args.first().map(String::as_str)));
            return 0;
        }
        Err(error) => {
            eprintln!(
                "{}\n{error}",
                graph_cli_usage(args.first().map(String::as_str))
            );
            return 2;
        }
    };
    let root = resolve_root(&parsed.root);
    if parsed.command == "check" {
        return run_graph_check(&root);
    }
    match write_graph_artifacts(&root, &parsed) {
        Ok((graph, markdown, json_path, evidence)) => {
            let evidence = evidence
                .map(|path| format!(" evidence={}", path.display()))
                .unwrap_or_default();
            println!(
                "SKILL_TOOL_INVOCATION_GRAPH=pass schema={} skills={} commands={} tools={} edges={} json={} mermaid={}{}",
                GRAPH_SCHEMA,
                graph.get("skill_count").and_then(Value::as_u64).unwrap_or(0),
                array_len(&graph, "commands").unwrap_or(0),
                array_len(&graph, "tools").unwrap_or(0),
                array_len(&graph, "edges").unwrap_or(0),
                json_path.display(),
                markdown.display(),
                evidence
            );
            0
        }
        Err(error) => {
            eprintln!("SKILL_TOOL_INVOCATION_GRAPH=fail reason={error}");
            2
        }
    }
}

fn normalize_source_mutation_path(path: &str) -> Result<String, String> {
    if path.is_empty() || path.starts_with('/') || Path::new(path).is_absolute() {
        return Err(format!("source_mutation_capability_invalid:path:{path}"));
    }
    let mut parts = Vec::new();
    for part in path.split('/') {
        match part {
            "" | "." => {}
            ".." => return Err(format!("source_mutation_capability_invalid:path:{path}")),
            part => parts.push(part),
        }
    }
    if parts.is_empty() {
        return Err(format!("source_mutation_capability_invalid:path:{path}"));
    }
    Ok(parts.join("/"))
}

fn read_source_mutation_capability(
    root: &Path,
    path: Option<&Path>,
) -> Result<Option<SourceMutationCapability>, String> {
    let Some(path) = path else {
        return Ok(None);
    };
    let raw = fs::read_to_string(path).map_err(|error| {
        format!(
            "source_mutation_capability_invalid:{}:{error}",
            path.display()
        )
    })?;
    let capability = SourceMutationCapability::from_json(root, Some(&raw))
        .map_err(|error| format!("source_mutation_capability_invalid:{error}"))?;
    let payload: Value = serde_json::from_str(&raw).map_err(|error| {
        format!(
            "source_mutation_capability_invalid:{}:{error}",
            path.display()
        )
    })?;
    let object = payload
        .as_object()
        .ok_or_else(|| "source_mutation_capability_invalid:fields".to_owned())?;
    let mut normalized = BTreeSet::new();
    let allowed = object
        .get("allowed_paths")
        .and_then(Value::as_array)
        .filter(|paths| !paths.is_empty())
        .ok_or_else(|| "source_mutation_capability_invalid:allowed_paths".to_owned())?;
    for item in allowed {
        let item = item
            .as_str()
            .ok_or_else(|| "source_mutation_capability_invalid:allowed_paths".to_owned())?;
        normalized.insert(normalize_source_mutation_path(item)?);
    }
    let expected = SOURCE_MUTATION_ALLOWED_PATHS
        .iter()
        .map(|path| (*path).to_owned())
        .collect::<BTreeSet<_>>();
    if normalized != expected {
        return Err(format!(
            "source_mutation_capability_target_mismatch:{}",
            SOURCE_MUTATION_ALLOWED_PATHS.join(",")
        ));
    }
    Ok(Some(capability))
}

fn source_file_evidence(root: &Path) -> Result<Value, String> {
    let mut files = Vec::new();
    for relative in SOURCE_MUTATION_ALLOWED_PATHS {
        let path = root.join(relative);
        let entry = match fs::metadata(&path) {
            Ok(metadata) => {
                let bytes = fs::read(&path).map_err(|error| {
                    format!("source_mutation_evidence_unreadable:{relative}:{error}")
                })?;
                #[cfg(unix)]
                let mode = {
                    use std::os::unix::fs::PermissionsExt;
                    metadata.permissions().mode() & 0o777
                };
                #[cfg(windows)]
                let mode = if metadata.permissions().readonly() {
                    0o444_u32
                } else {
                    0o666_u32
                };
                #[cfg(not(any(unix, windows)))]
                let mode = 0_u32;
                json!({
                    "path": relative,
                    "exists": true,
                    "sha256": sha256_hex(&bytes),
                    "mode": mode,
                })
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => json!({
                "path": relative,
                "exists": false,
                "sha256": Value::Null,
                "mode": Value::Null,
            }),
            Err(error) => {
                return Err(format!(
                    "source_mutation_evidence_unreadable:{relative}:{error}"
                ))
            }
        };
        files.push(entry);
    }
    let mut evidence = json!({ "files": files });
    let digest = digest_value(&evidence)?;
    evidence
        .as_object_mut()
        .ok_or_else(|| "source_mutation_evidence_invalid".to_owned())?
        .insert("digest".to_owned(), Value::String(digest));
    Ok(evidence)
}

fn graph_output_path(root: &Path, output: &Path) -> Result<PathBuf, String> {
    let expanded = crate::path_expansion::expand_user_path(output)
        .map_err(|error| format!("output_path_invalid:{error}"))?;
    let candidate = if expanded.is_absolute() {
        expanded
    } else {
        root.join(expanded)
    };
    let mut normalized = PathBuf::new();
    for component in candidate.components() {
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
        return Err(format!("output_path_invalid:{}", normalized.display()));
    }
    Ok(normalized)
}

fn graph_runtime_boundary(
    root: &Path,
    runtime_root: Option<&Path>,
    required_code: &str,
    invalid_code: &str,
) -> Result<RuntimeArtifactBoundary, String> {
    RuntimeArtifactBoundary::for_source(root, runtime_root, true).map_err(|error| {
        if error.contains("explicit runtime root required") {
            format!("{required_code}:pass --runtime-root or set AGENT_CANON_RUNTIME_ROOT")
        } else {
            format!("{invalid_code}:{error}")
        }
    })
}

fn write_graph_artifacts(
    root: &Path,
    options: &GraphCliArgs,
) -> Result<(Value, PathBuf, PathBuf, Option<PathBuf>), String> {
    let root = resolve_root(root);
    let graph = build_graph(&root)?;
    let capability =
        read_source_mutation_capability(&root, options.mutation_capability.as_deref())?;
    let (markdown_path, json_path, source_pair) = match options.output.as_deref() {
        None => {
            let boundary = graph_runtime_boundary(
                &root,
                options.runtime_root.as_deref(),
                "runtime_root_required",
                "runtime_root_invalid",
            )?;
            let markdown = boundary
                .resolve(Path::new(DEFAULT_EXTERNAL_GRAPH_PATH))
                .map_err(|error| format!("runtime_output_invalid:{error}"))?;
            let json = markdown.with_extension("json");
            (markdown, json, false)
        }
        Some(output) => {
            let markdown = graph_output_path(&root, output)?;
            let json = markdown.with_extension("json");
            let source_markdown = root.join(GRAPH_MARKDOWN_PATH);
            let source_json = root.join(GRAPH_JSON_PATH);
            let source_pair = markdown == source_markdown && json == source_json;
            if markdown.starts_with(&root) && !source_pair {
                return Err(
                    "source_output_not_allowed:only documents/runtime/skill-dependency-graph.{md,json} may be selected with an explicit mutation capability".to_owned(),
                );
            }
            (markdown, json, source_pair)
        }
    };

    if options.source_mutation && capability.is_none() {
        return Err("source_mutation_capability_required".to_owned());
    }
    if options.source_mutation_evidence.is_some() && !source_pair {
        return Err(
            "source_mutation_evidence_unexpected:tracked graph pair is required".to_owned(),
        );
    }
    if capability.is_some() && !source_pair {
        return Err(
            "source_mutation_capability_unexpected:tracked graph pair is required".to_owned(),
        );
    }

    let mermaid = render_graph_mermaid(&graph)?;
    let json_text = canonical_json(&graph)?;
    let mut evidence_path = None;
    if source_pair {
        let capability = capability
            .as_ref()
            .ok_or_else(|| "source_mutation_capability_required".to_owned())?;
        let boundary = graph_runtime_boundary(
            &root,
            options.runtime_root.as_deref(),
            "runtime_root_required_for_source_mutation",
            "runtime_root_invalid",
        )?;
        let before = source_file_evidence(&root)?;
        capability
            .atomic_write_text(&markdown_path, &mermaid, 0o644)
            .map_err(|error| format!("output_write_failed:{}:{error}", markdown_path.display()))?;
        capability
            .atomic_write_text(&json_path, &json_text, 0o644)
            .map_err(|error| format!("output_write_failed:{}:{error}", json_path.display()))?;
        let after = source_file_evidence(&root)?;
        let before_files = before
            .get("files")
            .and_then(Value::as_array)
            .ok_or_else(|| "source_mutation_evidence_invalid".to_owned())?;
        let after_files = after
            .get("files")
            .and_then(Value::as_array)
            .ok_or_else(|| "source_mutation_evidence_invalid".to_owned())?;
        let changed_paths = SOURCE_MUTATION_ALLOWED_PATHS
            .iter()
            .enumerate()
            .filter_map(|(index, path)| {
                (before_files.get(index) != after_files.get(index)).then_some(*path)
            })
            .collect::<Vec<_>>();
        let capability_value: Value = serde_json::from_str(
            &fs::read_to_string(
                options
                    .mutation_capability
                    .as_ref()
                    .expect("source capability exists"),
            )
            .map_err(|error| format!("source_mutation_capability_invalid:{error}"))?,
        )
        .map_err(|error| format!("source_mutation_capability_invalid:{error}"))?;
        let capability_object = capability_value
            .as_object()
            .ok_or_else(|| "source_mutation_capability_invalid:fields".to_owned())?;
        let evidence = json!({
            "schema": "agent_canon.skill_graph_source_mutation.v1",
            "status": "pass",
            "root": root.display().to_string(),
            "allowed_paths": SOURCE_MUTATION_ALLOWED_PATHS,
            "purpose": capability_object.get("purpose").and_then(Value::as_str).unwrap_or_default(),
            "authority": capability_object.get("authority").and_then(Value::as_str).unwrap_or_default(),
            "before": before,
            "after": after,
            "changed_paths": changed_paths,
            "source_tree_unchanged_outside_allowed_paths": true,
        });
        let output = options
            .source_mutation_evidence
            .as_deref()
            .unwrap_or(Path::new(SOURCE_MUTATION_EVIDENCE_PATH));
        let evidence_target = boundary
            .resolve(output)
            .map_err(|error| format!("source_mutation_evidence_write_failed:{error}"))?;
        boundary
            .atomic_write_json(
                evidence_target.strip_prefix(boundary.root()).map_err(|_| {
                    format!("source_mutation_evidence_write_failed:{evidence_target:?}")
                })?,
                &evidence,
                0o600,
            )
            .map_err(|error| format!("source_mutation_evidence_write_failed:{error}"))?;
        evidence_path = Some(output.to_path_buf());
    } else {
        let boundary = match options.runtime_root.as_deref() {
            Some(runtime_root) => graph_runtime_boundary(
                &root,
                Some(runtime_root),
                "runtime_root_required",
                "runtime_output_invalid",
            )?,
            None => {
                let parent = markdown_path
                    .parent()
                    .ok_or_else(|| "output_path_invalid:no_parent".to_owned())?;
                graph_runtime_boundary(
                    &root,
                    Some(parent),
                    "runtime_root_required",
                    "runtime_output_invalid",
                )?
            }
        };
        boundary
            .atomic_write_text(&markdown_path, &mermaid, 0o644)
            .map_err(|error| format!("output_write_failed:{}:{error}", markdown_path.display()))?;
        boundary
            .atomic_write_text(&json_path, &json_text, 0o644)
            .map_err(|error| format!("output_write_failed:{}:{error}", json_path.display()))?;
    }
    Ok((graph, markdown_path, json_path, evidence_path))
}

fn run_graph_check(root: &Path) -> i32 {
    let rules = match load_skill_dependency_map(root, None) {
        Ok(rules) => rules,
        Err(error) => {
            eprintln!("SKILL_TOOL_INVOCATION_GRAPH=fail reason={error}");
            return 2;
        }
    };
    match check_artifacts(root) {
        Ok(graph) => {
            println!(
                "SKILL_DEPENDENCY_MAP=pass source={} skills={}",
                super::skill_routes::SKILL_DEPENDENCY_MAP_PATH,
                rules.len()
            );
            println!(
                "SKILL_TOOL_INVOCATION_GRAPH=pass schema={} skills={} edges={} parallel_edges={} json={} mermaid={}",
                GRAPH_SCHEMA,
                graph.skill_count,
                graph.edge_count,
                graph.parallel_edge_count,
                GRAPH_JSON_PATH,
                GRAPH_MARKDOWN_PATH
            );
            0
        }
        Err(error) => {
            eprintln!("SKILL_TOOL_INVOCATION_GRAPH=fail reason={error}");
            2
        }
    }
}

const GRAPH_HEADER: &str =
    "<!-- Generated from the public skill/dependency graph; do not edit by hand. -->";
const GRAPH_DEPENDENCY_HEADER: &str = "<!--\n@dependency-start\ncontract reference\nresponsibility Publishes the generated public skill/dependency graph as a Mermaid reader surface.\nupstream design ../../documents/design/skill-tool-invocation-graph.md owns graph identity, serialization, and readback\nupstream implementation ../../tools/runtime/dispatch/agent-canon/src/catalog/skill_dependency_graph.rs materializes skill and dependency records and renders the Mermaid projection\nupstream implementation ../../tools/runtime/dispatch/agent-canon/src/source_mutation.rs owns capability-bound tracked-pair writes\ndownstream implementation ../../tools/runtime/dispatch/agent-canon/src/catalog/skill_dependency_graph.rs validates source/artifact equality and actual Mermaid syntax readback\ndownstream implementation ../../tests/agent_tools/test_skill_dependency_map.py covers identity, determinism, and stale-artifact failures\n@dependency-end\n-->";
const DESIGN_LOCATOR: &str = "documents/design/skill-tool-invocation-graph.md";
const IMPLEMENTATION_TRACE_PATHS: &[&str] = &[
    "agents/skills/catalog.yaml",
    "documents/design/skill-tool-invocation-graph.md",
    "documents/runtime/skill-dependency-graph.json",
    "documents/runtime/skill-dependency-graph.md",
    "tests/agent_tools/test_route.py",
    "tests/agent_tools/test_skill_dependency_map.py",
    "tools/runtime/dispatch/agent-canon/src/catalog/skill_dependency_graph.rs",
    "tools/runtime/dispatch/agent-canon/src/catalog/skill_routes.rs",
    "tools/agent/orchestration/route.py",
    "tools/runtime/dispatch/agent-canon/src/source_mutation.rs",
    "tools/agent/skills/skill_route_catalog.py",
];
const DESIGN_CLAUSE_IDS: &[&str] = &[
    "SG-001", "SG-002", "SG-003", "SG-004", "SG-005", "SG-006", "SG-007", "SG-008", "SG-009",
    "SG-010", "SG-011", "SG-012", "SG-013", "SG-014", "SG-015",
];
const DIC_CLAUSE_IDS: &[&str] = &[
    "DIC-001", "DIC-002", "DIC-003", "DIC-004", "DIC-005", "DIC-006", "DIC-007", "DIC-008",
    "DIC-009",
];
const SOURCE_KINDS: &[&str] = &[
    "identity", "edge", "field", "phase", "branch", "module", "evidence", "time",
];
const IDENTITY_KINDS: &[&str] = &[
    "skill",
    "phase",
    "command",
    "tool",
    "capability",
    "edge",
    "source",
    "manifest",
    "readback",
];
const EDGE_TYPES: &[&str] = &[
    "prerequisite",
    "successor",
    "order",
    "routing",
    "parallel",
    "invocation",
    "tool-resolution",
];
const IDENTIFIER_FIELDS: &[&str] = &[
    "adapter_id",
    "alias",
    "alias_of",
    "argument_schema_id",
    "capability_id",
    "edge_id",
    "id",
    "kind",
    "owner_id",
    "phase_id",
    "schema",
    "skill_id",
    "source_id",
    "target_id",
    "tool_id",
];

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SkillDependencyGraphCheck {
    pub skill_count: usize,
    pub command_count: usize,
    pub tool_count: usize,
    pub edge_count: usize,
    pub parallel_edge_count: usize,
    pub graph_digest: String,
    pub json_digest: String,
    pub mermaid_digest: String,
}

#[derive(Default)]
struct IdentityStore {
    records: Vec<Value>,
    by_key: BTreeMap<(String, String), Value>,
    by_digest: BTreeMap<String, Vec<u8>>,
    by_payload: BTreeMap<Vec<u8>, (String, String)>,
}

impl IdentityStore {
    fn add(&mut self, kind: &str, identity_id: &str, payload: &Value) -> Result<Value, String> {
        if !IDENTITY_KINDS.contains(&kind) {
            return Err(format!("invalid_identity_kind:{kind}"));
        }
        let canonical_kind = normalize_identifier(kind);
        let canonical_id = normalize_identifier(identity_id);
        let normalized = canonicalize(payload, None)?;
        let preimage = identity_preimage(&canonical_id, &canonical_kind, &normalized)?;
        let digest = sha256_hex(&preimage);
        let key = (canonical_kind.clone(), canonical_id.clone());
        if let Some(existing) = self.by_key.get(&key) {
            if string_field(existing, "digest")? != digest.as_str()
                || get(existing, "canonical_payload") != Some(&normalized)
            {
                return Err(format!("identity_collision:{kind}:{identity_id}"));
            }
            return reference(existing);
        }
        if self
            .by_digest
            .get(&digest)
            .is_some_and(|old_preimage| old_preimage != &preimage)
        {
            return Err(format!("digest_collision:{digest}"));
        }
        let payload_key = canonical_bytes(&normalized)?;
        if let Some((old_kind, old_id)) = self.by_payload.get(&payload_key) {
            return Err(format!(
                "identity_collision:payload_duplicate:{old_kind}:{old_id}:{canonical_kind}:{canonical_id}"
            ));
        }
        let record = json!({
            "id": canonical_id,
            "digest": digest,
            "kind": canonical_kind,
            "canonical_payload": normalized,
        });
        self.records.push(record.clone());
        self.by_key.insert(key.clone(), record);
        self.by_digest.insert(digest.clone(), preimage);
        self.by_payload
            .insert(payload_key, (canonical_kind, canonical_id));
        Ok(json!({"id": key.1, "digest": digest}))
    }

    fn require(&self, reference: &Value) -> Result<Value, String> {
        let identity_id = reference
            .get("id")
            .and_then(Value::as_str)
            .ok_or_else(|| "digest_mismatch:malformed_ref".to_owned())?;
        let digest = reference
            .get("digest")
            .and_then(Value::as_str)
            .ok_or_else(|| "digest_mismatch:malformed_ref".to_owned())?;
        let canonical_id = normalize_identifier(identity_id);
        let matches = self
            .records
            .iter()
            .filter(|record| {
                record.get("id").and_then(Value::as_str) == Some(canonical_id.as_str())
            })
            .collect::<Vec<_>>();
        if matches.len() != 1 {
            return Err(format!("digest_mismatch:missing_ref:{identity_id}"));
        }
        let record = matches[0];
        if record.get("digest").and_then(Value::as_str) != Some(digest) {
            return Err(format!("digest_mismatch:ref:{identity_id}"));
        }
        let kind = string_field(record, "kind")?;
        let payload = get(record, "canonical_payload")
            .ok_or_else(|| format!("digest_mismatch:record:{identity_id}"))?;
        if identity_digest(&canonical_id, kind, payload)? != digest {
            return Err(format!("digest_mismatch:record:{identity_id}"));
        }
        Ok(record.clone())
    }
}

/// Rebuild the v2 graph, then compare both tracked artifacts and actual Mermaid syntax.
pub fn check_artifacts(root: &Path) -> Result<SkillDependencyGraphCheck, String> {
    let root = resolve_root(root);
    let graph = build_graph(&root)?;
    let markdown_path = root.join(GRAPH_MARKDOWN_PATH);
    let json_path = root.join(GRAPH_JSON_PATH);
    let mut findings = Vec::new();
    if !markdown_path.is_file() {
        findings.push(format!("{GRAPH_MARKDOWN_PATH}:missing"));
    }
    if !json_path.is_file() {
        findings.push(format!("{GRAPH_JSON_PATH}:missing"));
    }
    if !findings.is_empty() {
        return Err(format!(
            "skill_tool_invocation_graph_stale_artifact:{}",
            findings.join(";")
        ));
    }
    let actual_markdown = read_text(&markdown_path)?;
    let actual_json_text = read_text(&json_path)?;
    let json_readback = serde_json::from_str::<Value>(&actual_json_text)
        .map_err(|error| error.to_string())
        .and_then(|machine| validate_loaded_graph(&machine));
    match json_readback {
        Ok(()) => {
            if let Err(error) = readback_mermaid(&graph, &actual_markdown) {
                findings.push(format!("readback:{error}"));
            }
        }
        Err(error) => findings.push(format!("readback:{error}")),
    }
    let expected_markdown = render_graph_mermaid(&graph)?;
    let expected_json = canonical_json(&graph)?;
    if actual_markdown != expected_markdown {
        findings.push(format!("{GRAPH_MARKDOWN_PATH}:edited-or-stale"));
    }
    if actual_json_text != expected_json {
        findings.push(format!("{GRAPH_JSON_PATH}:edited-or-stale"));
    }
    if !findings.is_empty() {
        return Err(format!(
            "skill_tool_invocation_graph_stale_artifact:{}",
            findings.join(";")
        ));
    }
    Ok(SkillDependencyGraphCheck {
        skill_count: array_len(&graph, "skills")?,
        command_count: array_len(&graph, "commands")?,
        tool_count: array_len(&graph, "tools")?,
        edge_count: array_len(&graph, "edges")?,
        parallel_edge_count: graph
            .get("edges")
            .and_then(Value::as_array)
            .ok_or("skill graph edges must be an array")?
            .iter()
            .filter(|edge| edge.get("display_label").and_then(Value::as_str) == Some("parallel"))
            .count(),
        graph_digest: string_field(&graph, "graph_digest")?.to_owned(),
        json_digest: string_field(&graph, "json_digest")?.to_owned(),
        mermaid_digest: string_field(&graph, "mermaid_digest")?.to_owned(),
    })
}

/// Build the source-bound v2 graph used by the checker and Mermaid reader.
pub fn build_graph(root: &Path) -> Result<Value, String> {
    let root = resolve_root(root);
    let design_correspondence = validate_design_correspondence(&root)?;
    let catalog = load_skill_catalog(&root)?;
    let skill_ids = skill_ids_from_catalog(&catalog)?;
    if skill_ids.is_empty() {
        return Err("skill_tool_invocation_graph_skill_count:0".to_owned());
    }
    let rules = load_skill_dependency_map(&root, Some(&skill_ids))?;
    let route_rules = load_skill_route_rules(&root)?;
    let route_by_skill = route_rules
        .iter()
        .map(|rule| (rule.skill.clone(), rule))
        .collect::<BTreeMap<_, _>>();
    let rule_by_skill = skill_ids
        .iter()
        .map(|skill| {
            rules
                .get(skill)
                .map(|rule| (skill.clone(), rule))
                .ok_or_else(|| "skill_tool_invocation_graph_skill_identity_mismatch".to_owned())
        })
        .collect::<Result<BTreeMap<_, _>, _>>()?;
    if skill_ids
        .iter()
        .any(|skill| !route_by_skill.contains_key(skill))
        || route_by_skill.len() != skill_ids.len()
        || rule_by_skill.len() != skill_ids.len()
    {
        return Err("skill_tool_invocation_graph_skill_identity_mismatch".to_owned());
    }
    let invocation_order = derive_skill_invocation_order(&skill_ids, &route_rules)?;
    let invocation_ordinals = invocation_order
        .iter()
        .enumerate()
        .map(|(index, skill)| (skill.clone(), index))
        .collect::<BTreeMap<_, _>>();
    let mut identities = IdentityStore::default();
    let mut source_inventory = Vec::new();
    let mut skill_refs = BTreeMap::new();
    let mut capability_refs = Vec::new();

    for (skill_ordinal, skill) in skill_ids.iter().enumerate() {
        let rule = rule_by_skill[skill];
        let route = route_by_skill[skill];
        let capability_ids = route
            .capabilities
            .iter()
            .map(|capability| format!("capability:{skill}:{}", capability.capability_id))
            .collect::<Vec<_>>();
        let skill_ref = identities.add(
            "skill",
            &format!("skill:{skill}"),
            &json!({
                "id": skill,
                "catalog_locator": format!("agents/skills/catalog.yaml#skill:{skill}"),
                "canonical_doc": format!("agents/skills/{skill}.md"),
                "shim": format!(".codex/personal/skills/{skill}/SKILL.md"),
                "command_ids": [],
                "capability_ids": capability_ids,
                "phase_ids": [],
            }),
        )?;
        skill_refs.insert(skill.clone(), skill_ref.clone());
        source_record(
            &mut identities,
            &mut source_inventory,
            "identity",
            &format!("agents/skills/catalog.yaml#skill:{skill}"),
            skill_ordinal,
            Some(&skill_ref),
            json!({"responsibility_group": rule.responsibility_group}),
        )?;
        source_record(
            &mut identities,
            &mut source_inventory,
            "time",
            &format!("agents/skills/skill-dependencies.yaml#invocation:{skill}"),
            invocation_ordinals[skill],
            Some(&skill_ref),
            json!({"invocation_ordinal": invocation_ordinals[skill]}),
        )?;
        for capability in &route.capabilities {
            let capability_id = format!("capability:{skill}:{}", capability.capability_id);
            let capability_ref = identities.add(
                "capability",
                &capability_id,
                &json!({
                    "id": capability.capability_id,
                    "owner_id": skill,
                    "type": capability.activation,
                    "phase_id": format!("phase:{skill}:conditional"),
                }),
            )?;
            source_record(
                &mut identities,
                &mut source_inventory,
                "branch",
                &format!(
                    "agents/skills/catalog.yaml#capability:{}",
                    capability.capability_id
                ),
                capability_refs.len(),
                Some(&capability_ref),
                json!({"owner": capability.owner, "phase": capability.phase}),
            )?;
            capability_refs.push((capability_id, capability_ref));
        }
    }

    let source_snapshot = source_snapshot(&root, &route_rules)?;
    for (key, locator) in [
        ("catalog_sha256", "agents/skills/catalog.yaml"),
        (
            "dependencies_sha256",
            "agents/skills/skill-dependencies.yaml",
        ),
        ("reader_index_sha256", "agents/canonical/skills.md"),
        ("route_packet_sha256", "agents/skills/catalog.yaml#routing"),
    ] {
        let evidence_ordinal = source_inventory.len();
        source_record(
            &mut identities,
            &mut source_inventory,
            "evidence",
            locator,
            evidence_ordinal,
            None,
            json!({"source_name": key, "sha256": source_snapshot[key]}),
        )?;
    }

    let mut edges = Vec::new();
    let mut edge_order = 0usize;
    for skill in &skill_ids {
        let rule = rule_by_skill[skill];
        for prerequisite in &rule.required_prerequisites {
            add_edge(
                (&mut identities, &mut edges, &mut source_inventory),
                "prerequisite",
                &skill_refs[prerequisite],
                &skill_refs[skill],
                edge_order,
                json!({}),
            )?;
            edge_order += 1;
        }
        for successor in &rule.successors {
            add_edge(
                (&mut identities, &mut edges, &mut source_inventory),
                "successor",
                &skill_refs[skill],
                &skill_refs[successor],
                edge_order,
                json!({}),
            )?;
            edge_order += 1;
        }
        for constraint in &rule.order_constraints {
            add_edge(
                (&mut identities, &mut edges, &mut source_inventory),
                "order",
                &skill_refs[&constraint.before],
                &skill_refs[&constraint.after],
                edge_order,
                json!({"reason": constraint.reason}),
            )?;
            edge_order += 1;
        }
        for candidate in &rule.routing_candidates {
            add_edge(
                (&mut identities, &mut edges, &mut source_inventory),
                "routing",
                &skill_refs[skill],
                &skill_refs[candidate],
                edge_order,
                json!({}),
            )?;
            edge_order += 1;
        }
        for other in &rule.parallel_independent {
            if skill < other {
                add_edge(
                    (&mut identities, &mut edges, &mut source_inventory),
                    "parallel",
                    &skill_refs[skill],
                    &skill_refs[other],
                    edge_order,
                    json!({}),
                )?;
                edge_order += 1;
            }
        }
    }
    if !skill_ids.iter().any(|skill| skill == "dependency-design") {
        return Err("skill_tool_invocation_graph_dependency-design_omission".to_owned());
    }
    if edges.iter().any(|edge| {
        edge.get("display_label")
            .and_then(Value::as_str)
            .is_none_or(|kind| !EDGE_TYPES.contains(&kind))
    }) {
        return Err("skill_tool_invocation_graph_unknown_edge_type".to_owned());
    }

    let skills = skill_ids
        .iter()
        .map(|skill| {
            projection_entry(
                &skill_refs[skill],
                skill,
                Some(invocation_ordinals[skill]),
                Some("skill"),
            )
        })
        .collect::<Vec<_>>();
    let capabilities = capability_refs
        .iter()
        .map(|(label, reference)| projection_entry(reference, label, None, None))
        .collect::<Vec<_>>();
    let invocation = invocation_order
        .iter()
        .map(|skill| json!({"ref": skill_refs[skill], "order": invocation_ordinals[skill]}))
        .collect::<Vec<_>>();
    let responsibility_groups = rule_by_skill
        .iter()
        .map(|(skill, rule)| (skill.clone(), json!(rule.responsibility_group)))
        .collect::<Map<_, _>>();
    let graph_source_counts = source_counts(&source_inventory);
    let mut graph = json!({
        "schema": GRAPH_SCHEMA,
        "version": 2,
        "artifact_id": GRAPH_ARTIFACT_ID,
        "skill_count": skill_ids.len(),
        "skills": skills,
        "phases": [],
        "commands": [],
        "tools": [],
        "capabilities": capabilities,
        "edges": edges,
        "invocation_order": invocation,
        "source_snapshot": source_snapshot,
        "source_inventory": source_inventory,
        "source_counts": graph_source_counts,
        "design_correspondence": design_correspondence,
        "responsibility_groups": responsibility_groups,
        "projection_digests": {},
    });
    let projection_digests = projection_digests(&graph)?;
    graph["projection_digests"] = projection_digests;
    let identity_refs = identities
        .records
        .iter()
        .map(reference)
        .collect::<Result<Vec<_>, _>>()?;
    let edge_refs = graph["edges"]
        .as_array()
        .ok_or_else(|| "graph_edges_not_array".to_owned())?
        .iter()
        .map(|edge| {
            get(edge, "edge_ref")
                .cloned()
                .ok_or_else(|| "edge_ref_missing".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    let source_digest = digest_value(&graph["source_snapshot"])?;
    let manifest_payload = json!({
        "id": "manifest:skill-tool-invocation-graph",
        "source_digest": source_digest,
        "identity_refs": identity_refs,
        "edge_refs": edge_refs,
        "counts": {
            "skills": skills_len(&graph)?,
            "phases": array_len(&graph, "phases")?,
            "commands": array_len(&graph, "commands")?,
            "tools": array_len(&graph, "tools")?,
            "edges": array_len(&graph, "edges")?,
        },
    });
    let manifest_ref = identities.add(
        "manifest",
        "manifest:skill-tool-invocation-graph",
        &manifest_payload,
    )?;
    let readback_payload = json!({
        "id": "readback:skill-tool-invocation-graph",
        "source_digest": source_digest,
        "projection_digests": graph["projection_digests"],
        "manifest_ref": manifest_ref,
        "counts": graph["source_counts"],
    });
    let readback_ref = identities.add(
        "readback",
        "readback:skill-tool-invocation-graph",
        &readback_payload,
    )?;
    graph["identity_records"] = Value::Array(identities.records.clone());
    graph["manifest"] = json!({
        "ref": manifest_ref,
        "source_digest": source_digest,
        "identity_refs": identity_refs,
        "edge_refs": edge_refs,
        "counts": manifest_payload["counts"],
    });
    graph["manifest_digest"] = manifest_ref["digest"].clone();
    graph["source_digests"] = json!({
        "catalog_sha256": source_snapshot["catalog_sha256"],
        "dependencies_sha256": source_snapshot["dependencies_sha256"],
        "reader_index_sha256": source_snapshot["reader_index_sha256"],
        "route_packet_sha256": source_snapshot["route_packet_sha256"],
    });
    graph["readback_ref"] = readback_ref.clone();
    graph["graph_digest"] = Value::String(digest_value(&without_fields(
        &graph,
        &["graph_digest", "json_digest", "mermaid_digest", "readback"],
    )?)?);
    let mermaid = render_graph_mermaid(&graph)?;
    graph["mermaid_digest"] = json!(sha256_hex(mermaid.as_bytes()));
    graph["readback"] = json!({
        "ref": readback_ref,
        "source_digest": source_digest,
        "graph_digest": graph["graph_digest"],
        "mermaid_digest": graph["mermaid_digest"],
        "json_digest": "",
        "projection_digests": graph["projection_digests"],
        "counts": graph["source_counts"],
    });
    graph["json_digest"] = Value::String(digest_value(&without_fields(
        &graph,
        &["json_digest", "readback", "mermaid_digest"],
    )?)?);
    graph["readback"]["json_digest"] = graph["json_digest"].clone();
    validate_projection_refs(&graph, &identities)?;
    Ok(graph)
}

fn yaml_field<'a>(value: &'a Yaml, key: &str) -> Option<&'a Yaml> {
    value
        .as_hash()?
        .iter()
        .find_map(|(candidate, value)| (candidate.as_str() == Some(key)).then_some(value))
}

fn skill_ids_from_catalog(catalog: &Yaml) -> Result<Vec<String>, String> {
    let families = yaml_field(catalog, "skill_families")
        .and_then(Yaml::as_vec)
        .ok_or_else(|| "skill_families must be a list".to_owned())?;
    let mut ids = Vec::with_capacity(families.len());
    for (index, family) in families.iter().enumerate() {
        let field = format!("skill_families[{index}]");
        let id = yaml_field(family, "id")
            .and_then(Yaml::as_str)
            .ok_or_else(|| format!("{field}.id is required"))?;
        ids.push(id.to_owned());
    }
    Ok(ids)
}

fn validate_design_correspondence(root: &Path) -> Result<Value, String> {
    let design_path = root.join(DESIGN_LOCATOR);
    if !design_path.is_file() {
        return Err("design_correspondence_missing:design_locator".to_owned());
    }
    let design_text = fs::read_to_string(&design_path).map_err(|error| error.to_string())?;
    let required_tokens = DESIGN_CLAUSE_IDS
        .iter()
        .chain(DIC_CLAUSE_IDS.iter())
        .chain(IMPLEMENTATION_TRACE_PATHS.iter());
    let missing = required_tokens
        .filter(|token| !design_text.contains(**token))
        .copied()
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        return Err(format!(
            "design_correspondence_missing:{}",
            missing.join(",")
        ));
    }
    Ok(json!({
        "design_locator": DESIGN_LOCATOR,
        "design_sha256": file_digest(root, DESIGN_LOCATOR)?,
        "clause_ids": DESIGN_CLAUSE_IDS,
        "dic_clause_ids": DIC_CLAUSE_IDS,
        "implementation_target_paths": IMPLEMENTATION_TRACE_PATHS,
    }))
}

fn source_snapshot(root: &Path, rules: &[SkillRoutingRule]) -> Result<Value, String> {
    let route_packet = rules.iter().map(route_snapshot_entry).collect::<Vec<_>>();
    let catalog_sha256 = file_digest(root, "agents/skills/catalog.yaml")?;
    let dependencies_sha256 = file_digest(root, "agents/skills/skill-dependencies.yaml")?;
    let reader_index_sha256 = file_digest(root, "agents/canonical/skills.md")?;
    let route_packet_sha256 = digest_value(&Value::Array(route_packet))?;
    Ok(json!({
        "catalog_sha256": catalog_sha256,
        "dependencies_sha256": dependencies_sha256,
        "reader_index_sha256": reader_index_sha256,
        "route_packet_sha256": route_packet_sha256,
        "source_locators": {
            "catalog_sha256": "agents/skills/catalog.yaml",
            "dependencies_sha256": "agents/skills/skill-dependencies.yaml",
            "reader_index_sha256": "agents/canonical/skills.md",
            "route_packet_sha256": "agents/skills/catalog.yaml#routing",
        },
    }))
}

fn route_snapshot_entry(rule: &SkillRoutingRule) -> Value {
    let capabilities = rule
        .capabilities
        .iter()
        .map(|capability| {
            json!({
                "id": capability.capability_id,
                "owner": capability.owner,
                "phase": capability.phase,
                "activation": capability.activation,
                "exclusive": capability.exclusive,
            })
        })
        .collect::<Vec<_>>();
    json!({
        "skill": rule.skill,
        "stage_policy": rule.stage_policy,
        "responsibility_group": rule.responsibility_group,
        "related_skills": rule.related_skills,
        "capabilities": capabilities,
        "required_prerequisites": rule.required_prerequisites,
        "successors": rule.successors,
    })
}

fn file_digest(root: &Path, relative: &str) -> Result<String, String> {
    let path = root.join(relative);
    if !path.is_file() {
        return Err(format!(
            "skill_tool_invocation_graph_missing_source:{relative}"
        ));
    }
    let bytes = fs::read(&path).map_err(|error| error.to_string())?;
    Ok(sha256_hex(&bytes))
}

fn read_text(path: &Path) -> Result<String, String> {
    fs::read_to_string(path)
        .map(|text| text.replace("\r\n", "\n").replace('\r', "\n"))
        .map_err(|error| error.to_string())
}

fn source_record(
    identities: &mut IdentityStore,
    inventory: &mut Vec<Value>,
    source_kind: &str,
    locator: &str,
    ordinal: usize,
    subject: Option<&Value>,
    extra: Value,
) -> Result<Value, String> {
    if !SOURCE_KINDS.contains(&source_kind) {
        return Err(format!("invalid_source_kind:{source_kind}"));
    }
    let mut payload = json!({
        "source_kind": source_kind,
        "source_locator": locator,
        "ordinal": ordinal,
        "subject_ref": subject.cloned().unwrap_or(Value::Null),
    });
    if let (Some(target), Some(extra)) = (payload.as_object_mut(), extra.as_object()) {
        for (key, value) in extra {
            target.insert(key.clone(), value.clone());
        }
    }
    let source_id = format!(
        "source:{source_kind}:{ordinal:05}:{}",
        &digest_value(&payload)?[..16]
    );
    let source_ref = identities.add("source", &source_id, &payload)?;
    inventory.push(json!({
        "ref": source_ref,
        "kind": source_kind,
        "source_locator": locator,
        "ordinal": ordinal,
    }));
    Ok(source_ref)
}

fn add_edge(
    output: (&mut IdentityStore, &mut Vec<Value>, &mut Vec<Value>),
    edge_type: &str,
    source: &Value,
    target: &Value,
    order: usize,
    attributes: Value,
) -> Result<(), String> {
    let (identities, edges, inventory) = output;
    if !EDGE_TYPES.contains(&edge_type) {
        return Err(format!("unknown_edge_type:{edge_type}"));
    }
    let edge_id = format!("edge:{:05}", edges.len());
    let payload = json!({
        "id": edge_id,
        "kind": edge_type,
        "source_id": string_field(source, "id")?,
        "target_id": string_field(target, "id")?,
        "order": order,
        "attributes": attributes,
    });
    let edge_ref = identities.add("edge", &edge_id, &payload)?;
    edges.push(json!({
        "edge_ref": edge_ref,
        "source_ref": source,
        "target_ref": target,
        "display_label": edge_type,
    }));
    source_record(
        identities,
        inventory,
        "edge",
        &format!("graph:edge:{:05}", edges.len() - 1),
        edges.len() - 1,
        Some(&edge_ref),
        json!({
            "edge_type": edge_type,
            "source_ref": source,
            "target_ref": target,
            "order": order,
        }),
    )?;
    Ok(())
}

fn projection_entry(
    reference: &Value,
    label: &str,
    order: Option<usize>,
    kind: Option<&str>,
) -> Value {
    let mut result = json!({"ref": reference, "display_label": label});
    if let Some(order) = order {
        result["order"] = json!(order);
    }
    if let Some(kind) = kind {
        result["kind"] = json!(kind);
    }
    result
}

fn source_counts(inventory: &[Value]) -> Value {
    let mut counts = SOURCE_KINDS
        .iter()
        .map(|kind| ((*kind).to_owned(), json!(0)))
        .collect::<Map<_, _>>();
    for item in inventory {
        if let Some(kind) = item.get("kind").and_then(Value::as_str) {
            if let Some(count) = counts.get_mut(kind) {
                *count = json!(count.as_u64().unwrap_or_default() + 1);
            }
        }
    }
    Value::Object(counts)
}

fn projection_digests(graph: &Value) -> Result<Value, String> {
    let mut nodes = Map::new();
    for field in ["skills", "phases", "commands", "tools", "capabilities"] {
        nodes.insert(
            field.to_owned(),
            get(graph, field)
                .cloned()
                .ok_or_else(|| format!("graph_projection_missing:{field}"))?,
        );
    }
    Ok(json!({
        "nodes": digest_value(&Value::Object(nodes))?,
        "edges": digest_value(get(graph, "edges").ok_or_else(|| "graph_edges_missing".to_owned())?)?,
        "invocation_order": digest_value(get(graph, "invocation_order").ok_or_else(|| "graph_invocation_order_missing".to_owned())?)?,
    }))
}

fn validate_projection_refs(graph: &Value, identities: &IdentityStore) -> Result<(), String> {
    for field in ["skills", "phases", "commands", "tools", "capabilities"] {
        for item in array(graph, field)? {
            let reference =
                get(item, "ref").ok_or_else(|| format!("projection_ref_missing:{field}"))?;
            identities.require(reference)?;
            if item.get("canonical_payload").is_some()
                || item.get("logical_argv").is_some()
                || item.get("execution_argv").is_some()
            {
                return Err(format!("payload_leak:{field}"));
            }
        }
    }
    for edge in array(graph, "edges")? {
        for field in ["edge_ref", "source_ref", "target_ref"] {
            let reference =
                get(edge, field).ok_or_else(|| format!("projection_ref_missing:edges.{field}"))?;
            identities.require(reference)?;
        }
    }
    Ok(())
}

fn canonicalize(value: &Value, field: Option<&str>) -> Result<Value, String> {
    match value {
        Value::String(text) => {
            if field.is_some_and(|field| IDENTIFIER_FIELDS.contains(&field)) {
                Ok(Value::String(normalize_identifier(text)))
            } else {
                Ok(Value::String(normalize_nfc(text)))
            }
        }
        Value::Array(items) => items
            .iter()
            .map(|item| canonicalize(item, field))
            .collect::<Result<Vec<_>, _>>()
            .map(Value::Array),
        Value::Object(object) => {
            let mut normalized = Map::new();
            for (key, item) in object {
                let normalized_key = normalize_nfc(key);
                normalized.insert(
                    normalized_key.clone(),
                    canonicalize(item, Some(&normalized_key))?,
                );
            }
            Ok(Value::Object(normalized))
        }
        _ => Ok(value.clone()),
    }
}

fn canonical_bytes(value: &Value) -> Result<Vec<u8>, String> {
    serde_json::to_vec(&canonicalize(value, None)?).map_err(|error| error.to_string())
}

fn canonical_json(value: &Value) -> Result<String, String> {
    String::from_utf8(canonical_bytes(value)?).map_err(|error| error.to_string())
}

fn digest_value(value: &Value) -> Result<String, String> {
    Ok(sha256_hex(&canonical_bytes(value)?))
}

fn identity_preimage(identity_id: &str, kind: &str, payload: &Value) -> Result<Vec<u8>, String> {
    let canonical_payload = canonical_bytes(payload)?;
    let canonical_id = normalize_identifier(identity_id);
    let canonical_kind = normalize_identifier(kind);
    let mut preimage = Vec::with_capacity(
        b"agent-canon".len()
            + GRAPH_SCHEMA.len()
            + identity_id.len()
            + kind.len()
            + canonical_payload.len()
            + 4,
    );
    let parts: [&[u8]; 5] = [
        b"agent-canon",
        b"skill-tool-invocation-graph.v2",
        canonical_id.as_bytes(),
        canonical_kind.as_bytes(),
        canonical_payload.as_slice(),
    ];
    for part in parts {
        if !preimage.is_empty() {
            preimage.push(0);
        }
        preimage.extend_from_slice(part);
    }
    Ok(preimage)
}

fn identity_digest(identity_id: &str, kind: &str, payload: &Value) -> Result<String, String> {
    Ok(sha256_hex(&identity_preimage(identity_id, kind, payload)?))
}

fn normalize_identifier(value: &str) -> String {
    let normalized = ComposingNormalizer::new_nfkc().normalize(value);
    CaseMapper::new().fold_string(&normalized)
}

fn normalize_nfc(value: &str) -> String {
    ComposingNormalizer::new_nfc().normalize(value)
}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    let mut text = String::with_capacity(digest.len() * 2);
    for byte in digest {
        use std::fmt::Write as _;
        let _ = write!(text, "{byte:02x}");
    }
    text
}

fn reference(record: &Value) -> Result<Value, String> {
    Ok(json!({
        "id": string_field(record, "id")?,
        "digest": string_field(record, "digest")?,
    }))
}

fn get<'a>(value: &'a Value, key: &str) -> Option<&'a Value> {
    value.as_object()?.get(key)
}

fn string_field<'a>(value: &'a Value, key: &str) -> Result<&'a str, String> {
    get(value, key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("graph_string_missing:{key}"))
}

fn array<'a>(value: &'a Value, key: &str) -> Result<&'a [Value], String> {
    get(value, key)
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .ok_or_else(|| format!("graph_array_missing:{key}"))
}

fn array_len(value: &Value, key: &str) -> Result<usize, String> {
    Ok(array(value, key)?.len())
}

fn skills_len(value: &Value) -> Result<usize, String> {
    array_len(value, "skills")
}

fn without_fields(value: &Value, excluded: &[&str]) -> Result<Value, String> {
    let object = value
        .as_object()
        .ok_or_else(|| "graph_object_expected".to_owned())?;
    let mut projected = object.clone();
    for field in excluded {
        projected.remove(*field);
    }
    Ok(Value::Object(projected))
}

fn resolve_root(root: &Path) -> PathBuf {
    root.canonicalize().unwrap_or_else(|_| {
        if root.is_absolute() {
            root.to_path_buf()
        } else {
            std::env::current_dir()
                .map(|cwd| cwd.join(root))
                .unwrap_or_else(|_| root.to_path_buf())
        }
    })
}

fn projection_nodes(graph: &Value) -> Result<Vec<(String, Value, usize)>, String> {
    let mut result = Vec::new();
    for (kind, field) in [
        ("skill", "skills"),
        ("phase", "phases"),
        ("command", "commands"),
        ("tool", "tools"),
        ("capability", "capabilities"),
    ] {
        for (index, item) in array(graph, field)?.iter().enumerate() {
            result.push((kind.to_owned(), item.clone(), index));
        }
    }
    Ok(result)
}

fn safe_mermaid_id(value: &str) -> String {
    let mut result = String::from("n_");
    for character in value.chars() {
        result.push(if character.is_alphanumeric() {
            character
        } else {
            '_'
        });
    }
    result
}

fn mermaid_label(value: &str) -> String {
    value
        .replace('"', "'")
        .replace('\n', " ")
        .replace('[', "(")
        .replace(']', ")")
}

fn rendered_node_label(item: &Value) -> Result<String, String> {
    let reference = get(item, "ref").ok_or_else(|| "projection_ref_missing".to_owned())?;
    let display = mermaid_label(string_field(item, "display_label")?);
    let digest = string_field(reference, "digest")?;
    if let Some(order) = get(item, "order") {
        Ok(format!(
            "{display} (order={}; ref={digest})",
            order
                .as_u64()
                .ok_or_else(|| "projection_order_invalid".to_owned())?
        ))
    } else {
        Ok(format!("{display} (ref={digest})"))
    }
}

fn rendered_edge_label(edge: &Value, payload: &Value) -> Result<String, String> {
    let edge_ref = get(edge, "edge_ref").ok_or_else(|| "edge_ref_missing".to_owned())?;
    Ok(format!(
        "{} (order={}; ref={})",
        string_field(edge, "display_label")?,
        get(payload, "order")
            .and_then(Value::as_u64)
            .ok_or_else(|| "edge_order_invalid".to_owned())?,
        string_field(edge_ref, "digest")?
    ))
}

/// Render the exact generated Mermaid reader artifact for a canonical graph.
pub fn render_graph_mermaid(graph: &Value) -> Result<String, String> {
    let mut lines = vec![
        GRAPH_DEPENDENCY_HEADER.to_owned(),
        GRAPH_HEADER.to_owned(),
        "# Public Skill Dependency Graph".to_owned(),
        String::new(),
        format!(
            "<!-- graph_digest={} -->",
            string_field(graph, "graph_digest")?
        ),
        "```mermaid".to_owned(),
        "graph LR".to_owned(),
    ];
    let skills = array(graph, "skills")?;
    let groups_by_skill = get(graph, "responsibility_groups")
        .and_then(Value::as_object)
        .ok_or_else(|| "responsibility_groups_invalid".to_owned())?;
    let mut groups = BTreeMap::<String, Vec<Value>>::new();
    for item in skills {
        let reference = get(item, "ref").ok_or_else(|| "projection_ref_missing".to_owned())?;
        let identity_id = string_field(reference, "id")?;
        let skill = identity_id
            .strip_prefix("skill:")
            .ok_or_else(|| format!("skill_identity_invalid:{identity_id}"))?;
        let group = groups_by_skill
            .get(skill)
            .and_then(Value::as_str)
            .ok_or_else(|| format!("responsibility_group_missing:{skill}"))?;
        groups
            .entry(group.to_owned())
            .or_default()
            .push(item.clone());
    }
    for (group, members) in &groups {
        lines.push(format!(
            "  subgraph responsibility_{}[\"Responsibility: {}\"]",
            safe_mermaid_id(group),
            mermaid_label(group)
        ));
        for item in members {
            let reference = get(item, "ref").ok_or_else(|| "projection_ref_missing".to_owned())?;
            let identity_id = string_field(reference, "id")?;
            let digest = string_field(reference, "digest")?;
            let order = get(item, "order")
                .and_then(Value::as_u64)
                .ok_or_else(|| "skill_projection_order_invalid".to_owned())?;
            lines.push(format!(
                "    %% node kind=skill id={identity_id} digest={digest} order={order}"
            ));
            lines.push(format!(
                "    {}[\"{}\"]",
                safe_mermaid_id(identity_id),
                rendered_node_label(item)?
            ));
        }
        lines.push("  end".to_owned());
    }
    let identities = array(graph, "identity_records")?
        .iter()
        .map(|record| Ok((string_field(record, "id")?.to_owned(), record.clone())))
        .collect::<Result<BTreeMap<_, _>, String>>()?;
    for (kind, field, title) in [
        ("tool", "tools", "ToolID catalog"),
        ("capability", "capabilities", "Typed capabilities"),
    ] {
        let entries = array(graph, field)?;
        if entries.is_empty() {
            continue;
        }
        lines.push(format!("  subgraph {kind}_catalog[\"{title}\"]"));
        for item in entries {
            let reference = get(item, "ref").ok_or_else(|| "projection_ref_missing".to_owned())?;
            let identity_id = string_field(reference, "id")?;
            let digest = string_field(reference, "digest")?;
            let order = get(item, "order")
                .and_then(Value::as_u64)
                .unwrap_or_default();
            lines.push(format!(
                "    %% node kind={kind} id={identity_id} digest={digest} order={order}"
            ));
            lines.push(format!(
                "    {}[[\"{}\"]]",
                safe_mermaid_id(identity_id),
                rendered_node_label(item)?
            ));
        }
        lines.push("  end".to_owned());
    }
    for source in array(graph, "source_inventory")? {
        let reference = get(source, "ref").ok_or_else(|| "source_ref_missing".to_owned())?;
        let locator = string_field(source, "source_locator")?.replace(' ', "%20");
        lines.push(format!(
            "  %% source kind={} id={} digest={} locator={} ordinal={}",
            string_field(source, "kind")?,
            string_field(reference, "id")?,
            string_field(reference, "digest")?,
            locator,
            get(source, "ordinal")
                .and_then(Value::as_u64)
                .ok_or_else(|| "source_ordinal_invalid".to_owned())?
        ));
    }
    for edge in array(graph, "edges")? {
        let edge_ref = get(edge, "edge_ref").ok_or_else(|| "edge_ref_missing".to_owned())?;
        let source_ref = get(edge, "source_ref").ok_or_else(|| "source_ref_missing".to_owned())?;
        let target_ref = get(edge, "target_ref").ok_or_else(|| "target_ref_missing".to_owned())?;
        let edge_id = string_field(edge_ref, "id")?;
        let edge_record = identities
            .get(edge_id)
            .ok_or_else(|| format!("missing_edge_identity:{edge_id}"))?;
        let payload = get(edge_record, "canonical_payload")
            .ok_or_else(|| format!("missing_edge_payload:{edge_id}"))?;
        let edge_type = string_field(edge, "display_label")?;
        let source_id = string_field(source_ref, "id")?;
        let target_id = string_field(target_ref, "id")?;
        let arrow = if matches!(edge_type, "routing" | "parallel") {
            "-.->"
        } else {
            "-->"
        };
        lines.push(format!(
            "  %% edge id={edge_id} digest={} type={edge_type} source={source_id} source_digest={} target={target_id} target_digest={} order={}",
            string_field(edge_ref, "digest")?,
            string_field(source_ref, "digest")?,
            string_field(target_ref, "digest")?,
            get(payload, "order")
                .and_then(Value::as_u64)
                .ok_or_else(|| format!("edge_order_invalid:{edge_id}"))?
        ));
        lines.push(format!(
            "  {} {arrow}|\"{}\"| {}",
            safe_mermaid_id(source_id),
            rendered_edge_label(edge, payload)?,
            safe_mermaid_id(target_id)
        ));
    }
    lines.extend([
        "  %% Edge legend: solid = prerequisite, successor, order, invocation, tool-resolution; dashed = routing, parallel.".to_owned(),
        "```".to_owned(),
        String::new(),
        "## Edge legend".to_owned(),
        String::new(),
        "- `prerequisite`, `successor`, `order`, `invocation`, and `tool-resolution`: solid directed edges.".to_owned(),
        "- `routing` and `parallel`: dashed directed edges.".to_owned(),
        String::new(),
        format!("Graph digest: `{}`.", string_field(graph, "graph_digest")?),
        String::new(),
    ]);
    Ok(lines.join("\n"))
}

fn readback_mermaid(graph: &Value, text: &str) -> Result<Value, String> {
    let (header, nodes, edges, sources) = parse_mermaid_metadata(text)?;
    let (actual_nodes, actual_edges) = parse_mermaid_syntax(text)?;
    if header != string_field(graph, "graph_digest")? {
        return Err("mermaid_readback_digest_mismatch".to_owned());
    }
    let mut expected_actual_nodes = BTreeMap::<String, (String, Option<u64>, String)>::new();
    for (_kind, item, _index) in projection_nodes(graph)? {
        let reference = get(&item, "ref").ok_or_else(|| "projection_ref_missing".to_owned())?;
        expected_actual_nodes.insert(
            safe_mermaid_id(string_field(reference, "id")?),
            (
                mermaid_label(string_field(&item, "display_label")?),
                get(&item, "order").and_then(Value::as_u64),
                string_field(reference, "digest")?.to_owned(),
            ),
        );
    }
    let mut observed_actual_nodes = BTreeMap::new();
    for (node_id, label) in &actual_nodes {
        observed_actual_nodes.insert(node_id.clone(), parse_actual_node_label(label)?);
    }
    if observed_actual_nodes != expected_actual_nodes {
        return Err("mermaid_readback_actual_node_order_or_digest_mismatch".to_owned());
    }

    let identity_by_id = array(graph, "identity_records")?
        .iter()
        .map(|record| Ok((string_field(record, "id")?.to_owned(), record)))
        .collect::<Result<BTreeMap<_, _>, String>>()?;
    let mut expected_actual_edges = BTreeSet::new();
    for edge in array(graph, "edges")? {
        let edge_ref = get(edge, "edge_ref").ok_or_else(|| "edge_ref_missing".to_owned())?;
        let source_ref = get(edge, "source_ref").ok_or_else(|| "source_ref_missing".to_owned())?;
        let target_ref = get(edge, "target_ref").ok_or_else(|| "target_ref_missing".to_owned())?;
        let edge_id = string_field(edge_ref, "id")?;
        let edge_record = identity_by_id
            .get(edge_id)
            .ok_or_else(|| format!("digest_mismatch:missing_ref:{edge_id}"))?;
        let payload = get(edge_record, "canonical_payload")
            .ok_or_else(|| format!("edge_payload_missing:{edge_id}"))?;
        let edge_type = string_field(edge, "display_label")?;
        expected_actual_edges.insert((
            safe_mermaid_id(string_field(source_ref, "id")?),
            if matches!(edge_type, "routing" | "parallel") {
                "-.->".to_owned()
            } else {
                "-->".to_owned()
            },
            safe_mermaid_id(string_field(target_ref, "id")?),
            edge_type.to_owned(),
            string_field(edge_ref, "digest")?.to_owned(),
            get(payload, "order")
                .and_then(Value::as_u64)
                .ok_or_else(|| format!("edge_order_invalid:{edge_id}"))?,
        ));
    }
    let mut observed_actual_edges = BTreeSet::new();
    for edge in &actual_edges {
        let (edge_type, order, digest) = parse_actual_edge_label(&edge.label)?;
        observed_actual_edges.insert((
            edge.source.clone(),
            edge.arrow.clone(),
            edge.target.clone(),
            edge_type,
            digest,
            order,
        ));
    }
    if observed_actual_edges != expected_actual_edges
        || actual_edges.len() != expected_actual_edges.len()
    {
        return Err("mermaid_readback_actual_edge_order_or_digest_mismatch".to_owned());
    }

    let mut expected_nodes = BTreeSet::new();
    for (kind, item, _index) in projection_nodes(graph)? {
        let reference = get(&item, "ref").ok_or_else(|| "projection_ref_missing".to_owned())?;
        expected_nodes.insert((
            kind,
            string_field(reference, "id")?.to_owned(),
            string_field(reference, "digest")?.to_owned(),
        ));
    }
    let observed_nodes = nodes
        .iter()
        .map(|item| {
            (
                item.get("kind").cloned().unwrap_or_default(),
                item.get("id").cloned().unwrap_or_default(),
                item.get("digest").cloned().unwrap_or_default(),
            )
        })
        .collect::<BTreeSet<_>>();
    if observed_nodes != expected_nodes {
        return Err("mermaid_readback_node_ref_mismatch".to_owned());
    }

    let mut expected_edges = BTreeSet::new();
    for edge in array(graph, "edges")? {
        let edge_ref = get(edge, "edge_ref").ok_or_else(|| "edge_ref_missing".to_owned())?;
        let source_ref = get(edge, "source_ref").ok_or_else(|| "source_ref_missing".to_owned())?;
        let target_ref = get(edge, "target_ref").ok_or_else(|| "target_ref_missing".to_owned())?;
        let edge_id = string_field(edge_ref, "id")?;
        let edge_record = identity_by_id
            .get(edge_id)
            .ok_or_else(|| format!("digest_mismatch:missing_ref:{edge_id}"))?;
        let payload = get(edge_record, "canonical_payload")
            .ok_or_else(|| format!("edge_payload_missing:{edge_id}"))?;
        expected_edges.insert((
            edge_id.to_owned(),
            string_field(edge_ref, "digest")?.to_owned(),
            string_field(edge, "display_label")?.to_owned(),
            string_field(source_ref, "id")?.to_owned(),
            string_field(source_ref, "digest")?.to_owned(),
            string_field(target_ref, "id")?.to_owned(),
            string_field(target_ref, "digest")?.to_owned(),
            get(payload, "order")
                .and_then(Value::as_u64)
                .ok_or_else(|| format!("edge_order_invalid:{edge_id}"))?
                .to_string(),
        ));
    }
    let observed_edges = edges
        .iter()
        .map(|item| {
            (
                item.get("id").cloned().unwrap_or_default(),
                item.get("digest").cloned().unwrap_or_default(),
                item.get("type").cloned().unwrap_or_default(),
                item.get("source").cloned().unwrap_or_default(),
                item.get("source_digest").cloned().unwrap_or_default(),
                item.get("target").cloned().unwrap_or_default(),
                item.get("target_digest").cloned().unwrap_or_default(),
                item.get("order").cloned().unwrap_or_default(),
            )
        })
        .collect::<Vec<_>>();
    if observed_edges.iter().cloned().collect::<BTreeSet<_>>() != expected_edges
        || observed_edges.len() != expected_edges.len()
    {
        return Err("mermaid_readback_edge_order_or_digest_mismatch".to_owned());
    }

    let mut expected_sources = BTreeSet::new();
    for source in array(graph, "source_inventory")? {
        let reference = get(source, "ref").ok_or_else(|| "source_ref_missing".to_owned())?;
        expected_sources.insert((
            string_field(source, "kind")?.to_owned(),
            string_field(reference, "id")?.to_owned(),
            string_field(reference, "digest")?.to_owned(),
            string_field(source, "source_locator")?.to_owned(),
            get(source, "ordinal")
                .and_then(Value::as_u64)
                .ok_or_else(|| "source_ordinal_invalid".to_owned())?
                .to_string(),
        ));
    }
    let observed_sources = sources
        .iter()
        .map(|item| {
            (
                item.get("kind").cloned().unwrap_or_default(),
                item.get("id").cloned().unwrap_or_default(),
                item.get("digest").cloned().unwrap_or_default(),
                item.get("locator").cloned().unwrap_or_default(),
                item.get("ordinal").cloned().unwrap_or_default(),
            )
        })
        .collect::<BTreeSet<_>>();
    if observed_sources != expected_sources {
        return Err("mermaid_readback_source_inventory_mismatch".to_owned());
    }
    Ok(json!({
        "status": "pass",
        "node_count": nodes.len(),
        "edge_count": edges.len(),
        "source_counts": get(graph, "source_counts").cloned().unwrap_or(Value::Null),
    }))
}

type MermaidMetadata = (
    String,
    Vec<BTreeMap<String, String>>,
    Vec<BTreeMap<String, String>>,
    Vec<BTreeMap<String, String>>,
);

fn parse_mermaid_metadata(text: &str) -> Result<MermaidMetadata, String> {
    let headers = text
        .lines()
        .filter(|line| mermaid_header_regex().is_match(line))
        .collect::<Vec<_>>();
    if headers.len() != 1 || !text.contains("```mermaid") || text.matches("```mermaid").count() != 1
    {
        return Err("mermaid_readback_block_or_header".to_owned());
    }
    let captures = mermaid_header_regex()
        .captures(headers[0])
        .ok_or_else(|| "mermaid_readback_block_or_header".to_owned())?;
    let graph_digest = captures
        .get(1)
        .ok_or_else(|| "mermaid_readback_block_or_header".to_owned())?
        .as_str()
        .to_owned();
    let mut nodes = Vec::new();
    let mut edges = Vec::new();
    let mut sources = Vec::new();
    for line in text.lines() {
        let stripped = line.trim();
        if let Some(payload) = stripped.strip_prefix("%% node ") {
            nodes.push(parse_mermaid_kv(payload));
        } else if let Some(payload) = stripped.strip_prefix("%% edge ") {
            edges.push(parse_mermaid_kv(payload));
        } else if let Some(payload) = stripped.strip_prefix("%% source ") {
            sources.push(parse_mermaid_kv(payload));
        }
    }
    Ok((graph_digest, nodes, edges, sources))
}

#[derive(Clone, Debug)]
struct ActualMermaidEdge {
    source: String,
    arrow: String,
    label: String,
    target: String,
}

fn parse_mermaid_syntax(
    text: &str,
) -> Result<(BTreeMap<String, String>, Vec<ActualMermaidEdge>), String> {
    let lines = text.lines().collect::<Vec<_>>();
    let start = lines
        .iter()
        .position(|line| *line == "```mermaid")
        .map(|index| index + 1)
        .ok_or_else(|| "mermaid_readback_block_or_header".to_owned())?;
    let end = lines[start..]
        .iter()
        .position(|line| *line == "```")
        .map(|offset| start + offset)
        .ok_or_else(|| "mermaid_readback_block_or_header".to_owned())?;
    let mut actual_nodes = BTreeMap::new();
    let mut actual_edges = Vec::new();
    for line in &lines[start..end] {
        if line.trim_start().starts_with("%%") {
            continue;
        }
        if let Some(captures) = mermaid_node_regex().captures(line) {
            let node_id = captures
                .get(1)
                .ok_or_else(|| "mermaid_node_parse".to_owned())?
                .as_str()
                .to_owned();
            let label = (2..=4)
                .find_map(|index| {
                    captures
                        .get(index)
                        .map(|capture| capture.as_str().to_owned())
                })
                .ok_or_else(|| "mermaid_node_parse".to_owned())?;
            if actual_nodes.insert(node_id.clone(), label).is_some() {
                return Err(format!("mermaid_readback_duplicate_node:{node_id}"));
            }
        } else if let Some(captures) = mermaid_edge_regex().captures(line) {
            actual_edges.push(ActualMermaidEdge {
                source: captures.get(1).unwrap().as_str().to_owned(),
                arrow: captures.get(2).unwrap().as_str().to_owned(),
                label: captures.get(3).unwrap().as_str().to_owned(),
                target: captures.get(4).unwrap().as_str().to_owned(),
            });
        }
    }
    Ok((actual_nodes, actual_edges))
}

fn parse_actual_node_label(label: &str) -> Result<(String, Option<u64>, String), String> {
    if let Some(captures) = mermaid_ordered_label_regex().captures(label) {
        let order = captures
            .get(2)
            .and_then(|capture| capture.as_str().parse::<u64>().ok())
            .ok_or_else(|| "mermaid_readback_node_label_missing_ref".to_owned())?;
        return Ok((
            captures.get(1).unwrap().as_str().to_owned(),
            Some(order),
            captures.get(3).unwrap().as_str().to_owned(),
        ));
    }
    if let Some(captures) = mermaid_ref_label_regex().captures(label) {
        return Ok((
            captures.get(1).unwrap().as_str().to_owned(),
            None,
            captures.get(2).unwrap().as_str().to_owned(),
        ));
    }
    Err("mermaid_readback_node_label_missing_ref".to_owned())
}

fn parse_actual_edge_label(label: &str) -> Result<(String, u64, String), String> {
    let captures = mermaid_edge_label_regex()
        .captures(label)
        .ok_or_else(|| "mermaid_readback_edge_label_missing_ref".to_owned())?;
    let order = captures
        .get(2)
        .and_then(|capture| capture.as_str().parse::<u64>().ok())
        .ok_or_else(|| "mermaid_readback_edge_label_missing_ref".to_owned())?;
    Ok((
        captures.get(1).unwrap().as_str().to_owned(),
        order,
        captures.get(3).unwrap().as_str().to_owned(),
    ))
}

fn validate_loaded_graph(machine: &Value) -> Result<(), String> {
    if get(machine, "schema").and_then(Value::as_str) != Some(GRAPH_SCHEMA)
        || get(machine, "version").and_then(Value::as_u64) != Some(2)
    {
        return Err("skill_tool_invocation_graph_schema_mismatch".to_owned());
    }
    let skills = array(machine, "skills")?;
    if skills.is_empty() {
        return Err("skill_tool_invocation_graph_skill_count:0".to_owned());
    }
    if get(machine, "skill_count").and_then(Value::as_u64) != Some(skills.len() as u64) {
        return Err("skill_tool_invocation_graph_skill_count_parity".to_owned());
    }
    let mut skill_ids = BTreeSet::new();
    for skill in skills {
        if let Some(reference) = get(skill, "ref") {
            if let Some(identity_id) = get(reference, "id").and_then(Value::as_str) {
                skill_ids.insert(identity_id.to_owned());
            }
        }
    }
    if !skill_ids.contains("skill:dependency-design") {
        return Err("dependency-design:omission".to_owned());
    }
    let expected_digest = digest_value(&without_fields(
        machine,
        &["json_digest", "readback", "mermaid_digest"],
    )?)?;
    if get(machine, "json_digest").and_then(Value::as_str) != Some(expected_digest.as_str()) {
        return Err("json_digest:mismatch".to_owned());
    }
    Ok(())
}

fn parse_mermaid_kv(value: &str) -> BTreeMap<String, String> {
    mermaid_kv_regex()
        .captures_iter(value)
        .filter_map(|captures| {
            Some((
                captures.get(1)?.as_str().to_owned(),
                captures.get(2)?.as_str().to_owned(),
            ))
        })
        .collect()
}

fn mermaid_header_regex() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| Regex::new(r"^<!-- graph_digest=([0-9a-f]{64}) -->$").unwrap())
}

fn mermaid_kv_regex() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| Regex::new(r"([a-z_]+)=([^ ]+)").unwrap())
}

fn mermaid_node_regex() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(r#"^\s+(n_[A-Za-z0-9_]+)(?:\[\["(.*)"\]\]|\["(.*)"\]|\{"(.*)"\})$"#).unwrap()
    })
}

fn mermaid_edge_regex() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| {
        Regex::new(r#"^\s+(n_[A-Za-z0-9_]+)\s+(-\.->|-->)\|"(.*)"\|\s+(n_[A-Za-z0-9_]+)$"#).unwrap()
    })
}

fn mermaid_ref_label_regex() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| Regex::new(r"^(.*) \(ref=([0-9a-f]{64})\)$").unwrap())
}

fn mermaid_ordered_label_regex() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| Regex::new(r"^(.*) \(order=([0-9]+); ref=([0-9a-f]{64})\)$").unwrap())
}

fn mermaid_edge_label_regex() -> &'static Regex {
    static REGEX: OnceLock<Regex> = OnceLock::new();
    REGEX.get_or_init(|| Regex::new(r"^(.*) \(order=([0-9]+); ref=([0-9a-f]{64})\)$").unwrap())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn repository_root() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(4)
            .expect("crate is nested under the repository root")
            .to_path_buf()
    }

    fn copy_source_inputs(source: &Path, destination: &Path) {
        for relative in [
            "agents/skills/catalog.yaml",
            "agents/skills/skill-dependencies.yaml",
            "agents/canonical/skills.md",
            DESIGN_LOCATOR,
            GRAPH_MARKDOWN_PATH,
            GRAPH_JSON_PATH,
        ] {
            let from = source.join(relative);
            let to = destination.join(relative);
            fs::create_dir_all(to.parent().expect("input has a parent"))
                .expect("create copied input parent");
            fs::copy(from, to).expect("copy graph input");
        }
    }

    #[test]
    fn canonical_bytes_sort_maps_and_normalize_unicode_identifier_aliases() {
        let first = json!({
            "z": {"b": 2, "a": 1},
            "id": "Ｆｏｏ",
            "alias": "ＦＯＯ",
        });
        let second = json!({
            "alias": "foo",
            "id": "foo",
            "z": {"a": 1, "b": 2},
        });
        assert_eq!(
            canonical_bytes(&first).unwrap(),
            canonical_bytes(&second).unwrap()
        );
        assert_eq!(normalize_identifier("Ｆｏｏ"), "foo");
    }

    #[test]
    fn identity_store_reuses_equal_records_and_rejects_payload_collisions() {
        let mut store = IdentityStore::default();
        let first = store
            .add("skill", "skill:sample", &json!({"id": "sample"}))
            .unwrap();
        assert_eq!(
            first,
            store
                .add("skill", "skill:sample", &json!({"id": "sample"}))
                .unwrap()
        );
        assert!(store
            .add("skill", "skill:sample", &json!({"id": "different"}))
            .unwrap_err()
            .contains("identity_collision:skill:skill:sample"));
        assert!(store
            .add("phase", "phase:sample", &json!({"id": "sample"}))
            .unwrap_err()
            .contains("payload_duplicate:skill:skill:sample:phase:phase:sample"));
        assert!(store
            .require(&json!({"id": first["id"], "digest": "0".repeat(64)}))
            .unwrap_err()
            .contains("digest_mismatch:ref:"));
    }

    #[test]
    fn reader_index_is_a_hashed_input_without_a_link_substring_gate() {
        let source = repository_root();
        let before = build_graph(&source).expect("build source graph");
        let temp = tempfile::tempdir().expect("create temporary graph root");
        copy_source_inputs(&source, temp.path());
        let reader = temp.path().join("agents/canonical/skills.md");
        let original = fs::read_to_string(&reader).expect("read copied reader index");
        let edited = original
            .replace("../skills/README.md", "")
            .replace("../skills/catalog.yaml", "")
            .replace("../internal-routines/README.md", "");
        fs::write(&reader, edited).expect("remove reader-index links");
        let after = build_graph(temp.path()).expect("reader index remains a source hash");
        assert_ne!(
            before["source_snapshot"]["reader_index_sha256"],
            after["source_snapshot"]["reader_index_sha256"]
        );
        assert_ne!(before["graph_digest"], after["graph_digest"]);
    }

    #[test]
    fn loaded_graph_requires_dependency_design_even_if_counts_are_recomputed() {
        let mut graph = build_graph(&repository_root()).expect("build source graph");
        let skills = array(&graph, "skills")
            .unwrap()
            .iter()
            .filter(|item| {
                get(item, "ref")
                    .and_then(|reference| reference.get("id"))
                    .and_then(Value::as_str)
                    != Some("skill:dependency-design")
            })
            .cloned()
            .collect::<Vec<_>>();
        let skill_count = skills.len();
        graph["skills"] = Value::Array(skills);
        graph["skill_count"] = json!(skill_count);
        let json_digest = digest_value(
            &without_fields(&graph, &["json_digest", "readback", "mermaid_digest"]).unwrap(),
        )
        .unwrap();
        graph["json_digest"] = json!(json_digest);
        assert_eq!(
            validate_loaded_graph(&graph).unwrap_err(),
            "dependency-design:omission"
        );
    }

    #[test]
    fn graph_writer_requires_an_external_runtime_and_preserves_source_inputs() {
        let source = repository_root();
        let temp = tempfile::tempdir().expect("create isolated graph root");
        copy_source_inputs(&source, temp.path());
        let before_markdown =
            fs::read(temp.path().join(GRAPH_MARKDOWN_PATH)).expect("read source graph markdown");
        let before_json =
            fs::read(temp.path().join(GRAPH_JSON_PATH)).expect("read source graph json");
        let runtime = tempfile::tempdir().expect("create external graph runtime");
        let options = GraphCliArgs {
            command: "graph".to_owned(),
            root: temp.path().to_path_buf(),
            output: None,
            runtime_root: Some(runtime.path().to_path_buf()),
            mutation_capability: None,
            source_mutation: false,
            source_mutation_evidence: None,
        };

        let (graph, markdown, json_path, evidence) =
            write_graph_artifacts(temp.path(), &options).expect("write external graph pair");
        assert!(markdown.starts_with(runtime.path()));
        assert!(json_path.starts_with(runtime.path()));
        assert!(markdown.is_file());
        assert!(json_path.is_file());
        assert!(evidence.is_none());
        assert_eq!(
            fs::read(&markdown).expect("read generated graph markdown"),
            render_graph_mermaid(&graph)
                .expect("render graph markdown")
                .as_bytes()
        );
        assert_eq!(
            fs::read(&json_path).expect("read generated graph JSON"),
            canonical_json(&graph)
                .expect("serialize graph JSON")
                .as_bytes()
        );
        assert_eq!(
            fs::read(temp.path().join(GRAPH_MARKDOWN_PATH)).unwrap(),
            before_markdown
        );
        assert_eq!(
            fs::read(temp.path().join(GRAPH_JSON_PATH)).unwrap(),
            before_json
        );
    }

    #[test]
    fn graph_writer_requires_the_exact_capability_for_the_tracked_pair() {
        let source = repository_root();
        let temp = tempfile::tempdir().expect("create isolated graph root");
        copy_source_inputs(&source, temp.path());
        fs::write(temp.path().join(GRAPH_MARKDOWN_PATH), "stale markdown\n")
            .expect("seed a stale graph reader file");
        fs::write(temp.path().join(GRAPH_JSON_PATH), "stale json\n")
            .expect("seed a stale graph machine file");
        let runtime = tempfile::tempdir().expect("create external graph runtime");
        let capability = temp.path().join("capability.json");
        fs::write(
            &capability,
            serde_json::to_vec(&json!({
                "allowed_paths": [GRAPH_MARKDOWN_PATH, GRAPH_JSON_PATH],
                "purpose": "refresh canonical graph reader pair",
                "authority": "graph-writer-oracle",
            }))
            .unwrap(),
        )
        .expect("write exact source mutation capability");
        let options = GraphCliArgs {
            command: "graph".to_owned(),
            root: temp.path().to_path_buf(),
            output: Some(PathBuf::from(GRAPH_MARKDOWN_PATH)),
            runtime_root: Some(runtime.path().to_path_buf()),
            mutation_capability: Some(capability),
            source_mutation: true,
            source_mutation_evidence: None,
        };

        let (graph, markdown, json_path, evidence) =
            write_graph_artifacts(temp.path(), &options).expect("write tracked graph pair");
        assert_eq!(markdown, temp.path().join(GRAPH_MARKDOWN_PATH));
        assert_eq!(json_path, temp.path().join(GRAPH_JSON_PATH));
        assert_eq!(
            fs::read(&markdown).expect("read updated graph markdown"),
            render_graph_mermaid(&graph)
                .expect("render graph markdown")
                .as_bytes()
        );
        assert_eq!(
            fs::read(&json_path).expect("read updated graph JSON"),
            canonical_json(&graph)
                .expect("serialize graph JSON")
                .as_bytes()
        );
        let evidence_path = runtime.path().join(SOURCE_MUTATION_EVIDENCE_PATH);
        assert_eq!(
            evidence.as_deref(),
            Some(Path::new(SOURCE_MUTATION_EVIDENCE_PATH))
        );
        let payload: Value = serde_json::from_slice(
            &fs::read(evidence_path).expect("read source mutation evidence"),
        )
        .expect("parse source mutation evidence");
        assert_eq!(
            payload["schema"],
            "agent_canon.skill_graph_source_mutation.v1"
        );
        assert_eq!(payload["allowed_paths"][0], GRAPH_MARKDOWN_PATH);
        assert_eq!(payload["allowed_paths"][1], GRAPH_JSON_PATH);
        assert_eq!(payload["changed_paths"].as_array().unwrap().len(), 2);
        assert_eq!(payload["source_tree_unchanged_outside_allowed_paths"], true);
    }

    #[test]
    fn graph_writer_rejects_a_capability_broader_than_the_tracked_pair() {
        let source = repository_root();
        let temp = tempfile::tempdir().expect("create isolated graph root");
        copy_source_inputs(&source, temp.path());
        let runtime = tempfile::tempdir().expect("create external graph runtime");
        let capability = temp.path().join("capability.json");
        fs::write(
            &capability,
            serde_json::to_vec(&json!({
                "allowed_paths": ["README.md"],
                "purpose": "wrong target",
                "authority": "graph-writer-oracle",
            }))
            .unwrap(),
        )
        .expect("write unrelated source mutation capability");
        let options = GraphCliArgs {
            command: "graph".to_owned(),
            root: temp.path().to_path_buf(),
            output: Some(PathBuf::from(GRAPH_MARKDOWN_PATH)),
            runtime_root: Some(runtime.path().to_path_buf()),
            mutation_capability: Some(capability),
            source_mutation: true,
            source_mutation_evidence: None,
        };

        let error = write_graph_artifacts(temp.path(), &options)
            .expect_err("reject an unrelated mutation capability");
        assert!(error.contains("source_mutation_capability_target_mismatch"));
    }
}
