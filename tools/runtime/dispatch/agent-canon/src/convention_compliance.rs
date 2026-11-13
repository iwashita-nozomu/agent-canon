// @dependency-start
// contract implementation
// responsibility Checks convention source, tool, workflow, marker, and forwarder wiring.
// upstream design ../../../../../documents/conventions/README.md owns the convention index
// upstream design ../../../../../agents/canonical/CODEX_COMPLETION.md owns selected validation evidence
// upstream design ../../../../../documents/codex/codex-configuration-reference.md owns hook severity
// upstream design ../../../../../documents/conventions/coding-conventions-house-style.md owns source definition order
// upstream design ../../../../../.codex/README.md summarizes hook behavior
// upstream design ../../../../catalog.yaml owns structured tool registration
// upstream implementation ../../../../validation/semantic/convention/convention_compliance_contracts.toml owns declarative checker inputs
// upstream implementation skill_frontmatter.rs validates skill frontmatter
// upstream implementation tool_drift.rs validates tool and convention trace contracts
// downstream implementation ../../../../validation/ci/runners/run_all_checks.sh runs the convention gate
// downstream test ../../../../../tests/agent_tools/test_check_convention_compliance.py checks independent source fixtures and missing contracts
// @dependency-end

use regex::Regex;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

const MANIFEST: &str =
    include_str!("../../../../validation/semantic/convention/convention_compliance_contracts.toml");
#[derive(Deserialize)]
struct Configuration {
    checker: Checker,
    contracts: Vec<Contract>,
}
#[derive(Deserialize)]
struct Checker {
    convention_sources: Vec<String>,
    workflow_consumers: Vec<String>,
    stale_owner_phrases: Vec<String>,
    forwarder_markers: Vec<String>,
    forwarder_policy_markers: Vec<String>,
    gates: Vec<Gate>,
}
#[derive(Deserialize)]
struct Gate {
    id: String,
    path: String,
    owners: Vec<String>,
}
#[derive(Deserialize)]
struct Contract {
    id: String,
    surfaces: Vec<Surface>,
}
#[derive(Deserialize)]
struct Surface {
    path: String,
    markers: Vec<String>,
}
#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd, Serialize)]
struct Finding {
    check: String,
    path: String,
    detail: String,
}
fn finding(findings: &mut Vec<Finding>, check: &str, path: &str, detail: impl Into<String>) {
    findings.push(Finding {
        check: check.into(),
        path: path.into(),
        detail: detail.into(),
    });
}
fn readable(root: &Path, path: &str) -> Option<PathBuf> {
    [root.join(path), root.join("vendor/agent-canon").join(path)]
        .into_iter()
        .find(|path| path.is_file())
}
fn read(root: &Path, path: &str) -> Result<Option<String>, String> {
    readable(root, path)
        .map(|path| {
            fs::read_to_string(&path).map_err(|error| format!("{}: {error}", path.display()))
        })
        .transpose()
}
fn required(root: &Path, paths: &[String], check: &str, findings: &mut Vec<Finding>) {
    for path in paths {
        if readable(root, path).is_none() {
            finding(findings, check, path, "missing-required-file");
        }
    }
}
fn tool_checks(root: &Path, config: &Checker, findings: &mut Vec<Finding>) -> Result<(), String> {
    for gate in &config.gates {
        if readable(root, &gate.path).is_none() {
            finding(
                findings,
                "tool_gate",
                &gate.path,
                format!("{}:missing-tool", gate.id),
            );
            continue;
        }
        for owner in &gate.owners {
            let Some(text) = read(root, owner)? else {
                finding(
                    findings,
                    "tool_gate",
                    owner,
                    format!("{}:missing-owner-surface", gate.id),
                );
                continue;
            };
            if owner == "tools/catalog.yaml" {
                let pattern = Regex::new(&format!(
                    r#"(?m)^\s*path:\s*['\"]?{}['\"]?\s*(?:#.*)?$"#,
                    regex::escape(&gate.path)
                ))
                .map_err(|error| error.to_string())?;
                if !pattern.is_match(&text) {
                    finding(
                        findings,
                        "tool_gate",
                        owner,
                        format!("{}:missing-catalog-owner", gate.id),
                    );
                }
            }
        }
    }
    Ok(())
}
fn workflow_checks(
    root: &Path,
    config: &Checker,
    findings: &mut Vec<Finding>,
) -> Result<(), String> {
    required(root, &config.workflow_consumers, "workflow_hook", findings);
    let positive=Regex::new(r#"(?m)^\s*run_agent_canon\s+check-convention-compliance\s+--root\s+"\$\{WORKSPACE_ROOT\}"\s+--format\s+json$"#).map_err(|error|error.to_string())?;
    let forbidden=Regex::new(r"(?is)(?:do\s+not|don't|never|skip|omit)\s+(?:\S+\s+){0,6}?check-convention-compliance|check-convention-compliance(?:\S+\s+){0,6}?(?:optional|not\s+required)").map_err(|error|error.to_string())?;
    for path in &config.workflow_consumers {
        let Some(text) = read(root, path)? else {
            continue;
        };
        if !text.contains("check-convention-compliance") {
            finding(
                findings,
                "workflow_hook",
                path,
                "missing-convention-compliance-gate",
            );
            continue;
        }
        if !positive.is_match(&text) {
            finding(
                findings,
                "workflow_hook",
                path,
                "missing-positive-convention-compliance-command",
            );
        }
        if forbidden.is_match(&text) {
            finding(
                findings,
                "workflow_hook",
                path,
                "forbidden-convention-compliance-suppression",
            );
        }
    }
    Ok(())
}
fn contract_checks(
    root: &Path,
    config: &Configuration,
    findings: &mut Vec<Finding>,
) -> Result<(), String> {
    for contract in &config.contracts {
        for surface in &contract.surfaces {
            if surface.path.starts_with(".codex/personal/skills/")
                && surface.path.ends_with("/SKILL.md")
            {
                return Err(format!(
                    "generated skill shims cannot own convention marker contracts: {}",
                    surface.path
                ));
            }
            let Some(text) = read(root, &surface.path)? else {
                finding(
                    findings,
                    &contract.id,
                    &surface.path,
                    "missing-required-file",
                );
                continue;
            };
            for marker in &surface.markers {
                if !text.contains(marker) {
                    finding(
                        findings,
                        &contract.id,
                        &surface.path,
                        format!("missing-marker:{marker}"),
                    );
                }
            }
            if contract.id == "validation_failure_response" {
                for phrase in &config.checker.stale_owner_phrases {
                    if text.contains(phrase) {
                        finding(
                            findings,
                            &contract.id,
                            &surface.path,
                            format!("stale-taxonomy-owner:{phrase}"),
                        );
                    }
                }
            }
        }
    }
    Ok(())
}
fn convention_assertions(
    root: &Path,
    config: &Checker,
    findings: &mut Vec<Finding>,
) -> Result<(), String> {
    let normative=Regex::new(r"(?im)^\s*[-*]\s+.*(?:禁止|必須|しなければなりません|してはいけません|must|must not|required|forbidden)").map_err(|error|error.to_string())?;
    let verification=Regex::new(r"(?:tools/|check_|pyright|pytest|ruff|make ci|make agent-checks|CONVENTION_COMPLIANCE|EVAL_STATUS|AGENT_EVALUATION_STATUS)").map_err(|error|error.to_string())?;
    for path in &config.convention_sources {
        if let Some(text) = read(root, path)? {
            if normative.is_match(&text) && !verification.is_match(&text) {
                finding(
                    findings,
                    "convention_assertions",
                    path,
                    "normative-lines-without-verification-route",
                );
            }
        }
    }
    Ok(())
}
fn forwarders(root: &Path, config: &Checker, findings: &mut Vec<Finding>) -> Result<(), String> {
    let mut pending = vec![root.join("tools")];
    let mut files = vec![];
    while let Some(path) = pending.pop() {
        let metadata = match fs::symlink_metadata(&path) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Err(error) => return Err(error.to_string()),
        };
        if metadata.is_dir() {
            for entry in fs::read_dir(path).map_err(|error| error.to_string())? {
                pending.push(entry.map_err(|error| error.to_string())?.path());
            }
        } else if path.is_file()
            && path
                .extension()
                .is_some_and(|extension| extension == "py" || extension == "sh")
        {
            files.push(path);
        }
    }
    files.sort();
    for path in files {
        let bytes = fs::read(&path).map_err(|error| error.to_string())?;
        let text = String::from_utf8_lossy(&bytes);
        if !text.contains("LEGACY_FORWARDER_WARNING_REQUIRED") {
            continue;
        }
        let relative = path
            .strip_prefix(root)
            .map_err(|error| error.to_string())?
            .iter()
            .map(|part| part.to_string_lossy())
            .collect::<Vec<_>>()
            .join("/");
        for marker in &config.forwarder_markers {
            if !text.contains(marker) {
                finding(
                    findings,
                    "legacy_forwarder_warning",
                    &relative,
                    format!("missing-marker:{marker}"),
                );
            }
        }
    }
    let mut policy = String::new();
    for path in [
        "documents/codex/codex-configuration-reference.md",
        ".codex/README.md",
    ] {
        if let Some(text) = read(root, path)? {
            policy.push_str(&text);
            policy.push('\n');
        }
    }
    if !policy.is_empty() {
        for marker in &config.forwarder_policy_markers {
            if !policy.contains(marker) {
                finding(
                    findings,
                    "legacy_forwarder_warning",
                    "AGENTS.md",
                    format!("missing-policy-marker:{marker}"),
                );
            }
        }
    }
    Ok(())
}
fn run_inner(args: &[String]) -> Result<i32, String> {
    let mut root = PathBuf::from(".");
    let mut format = "text";
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if matches!(argument.as_str(), "--help" | "-h") {
            println!(
                "usage: agent-canon check-convention-compliance [--root ROOT] [--format text|json]"
            );
            return Ok(0);
        }
        let (option, inline) = argument
            .split_once('=')
            .map_or((argument.as_str(), None), |(key, value)| (key, Some(value)));
        let key = if option.starts_with("--") && "--root".starts_with(option) {
            "root"
        } else if option.starts_with("--") && "--format".starts_with(option) {
            "format"
        } else {
            return Err(format!("unrecognized argument: {argument}"));
        };
        let value = if let Some(value) = inline {
            value
        } else {
            index += 1;
            args.get(index)
                .ok_or_else(|| format!("{option}: expected one argument"))?
        };
        if key == "root" {
            root = PathBuf::from(value);
        } else {
            format = value;
        }
        index += 1;
    }
    if !matches!(format, "text" | "json") {
        return Err("--format must be text or json".into());
    }
    let root = crate::path_resolution::resolve_non_strict(&root)?;
    let config: Configuration =
        toml_edit::de::from_str(MANIFEST).map_err(|error| error.to_string())?;
    let mut findings = vec![];
    required(
        &root,
        &config.checker.convention_sources,
        "convention_sources",
        &mut findings,
    );
    tool_checks(&root, &config.checker, &mut findings)?;
    workflow_checks(&root, &config.checker, &mut findings)?;
    contract_checks(&root, &config, &mut findings)?;
    convention_assertions(&root, &config.checker, &mut findings)?;
    forwarders(&root, &config.checker, &mut findings)?;
    findings.sort();
    let status = if findings.is_empty() { "pass" } else { "fail" };
    if format == "json" {
        println!("{}",serde_json::to_string_pretty(&serde_json::json!({"status":status,"findings":findings,"convention_sources":config.checker.convention_sources.len(),"tool_gates":config.checker.gates.len(),"workflow_prompts":config.checker.workflow_consumers.iter().filter(|path|readable(&root,path).is_some()).count()})).map_err(|error|error.to_string())?);
    } else {
        for value in &findings {
            println!(
                "CONVENTION_COMPLIANCE_FINDING={}:{}:{}",
                value.check, value.path, value.detail
            );
        }
        println!("CONVENTION_COMPLIANCE_SOURCES={}\nCONVENTION_COMPLIANCE_TOOL_GATES={}\nCONVENTION_COMPLIANCE_WORKFLOWS={}\nCONVENTION_COMPLIANCE_FINDINGS={}\nCONVENTION_COMPLIANCE={status}",config.checker.convention_sources.len(),config.checker.gates.len(),config.checker.workflow_consumers.len(),findings.len());
    }
    Ok(i32::from(!findings.is_empty()))
}
pub fn run(args: &[String]) -> i32 {
    match run_inner(args) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("{error}");
            2
        }
    }
}
