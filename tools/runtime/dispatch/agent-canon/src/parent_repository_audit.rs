//! Canonical audit-unit selection and tracked evidence. Reads source and Git only.

use crate::agent_canon_source_root::resolve_source_roots;
use crate::path_expansion::expand_user_path;
use crate::path_resolution::resolve_non_strict;
use regex::Regex;
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const UNIT_ROOT: &str = "documents/parent-repository-audit/audit-unit";
const SCHEMA: &str = "agent_canon.parent_repository_audit.v1";
const SECTIONS: &[&str] = &[
    "Owner Responsibility",
    "Invariant",
    "Evidence Sources",
    "Repair Route",
    "Validation",
    "Close Condition",
    "Related Change Surfaces",
    "Legacy Migration IDs",
];

#[derive(Debug)]
struct Failure {
    code: &'static str,
    detail: String,
    blocked: bool,
}
impl Failure {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
            blocked: false,
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct AuditUnit {
    pub unit_id: String,
    pub path: String,
    pub surfaces: Vec<String>,
    pub legacy_ids: Vec<String>,
}

fn section(text: &str, heading: &str) -> String {
    let marker = format!("## {heading}");
    let mut lines = text.lines().skip_while(|line| *line != marker);
    lines.next();
    lines
        .take_while(|line| !line.starts_with("## "))
        .collect::<Vec<_>>()
        .join("\n")
        .trim()
        .to_owned()
}

fn safe_child(path: &Path, root: &Path) -> Result<PathBuf, Failure> {
    let resolved = resolve_non_strict(path)
        .map_err(|detail| Failure::new("parent_repository_audit_path_escape", detail))?;
    if !resolved.starts_with(root) {
        return Err(Failure::new(
            "parent_repository_audit_path_escape",
            format!("path={} root={}", path.display(), root.display()),
        ));
    }
    Ok(resolved)
}

fn unique_matches(pattern: &Regex, text: &str) -> Vec<String> {
    let mut result = Vec::new();
    for found in pattern.captures_iter(text) {
        let value = found
            .get(1)
            .unwrap_or_else(|| found.get(0).expect("regex match"))
            .as_str()
            .to_owned();
        if !result.contains(&value) {
            result.push(value);
        }
    }
    result
}

pub fn load_units(source_root: &Path) -> Result<Vec<AuditUnit>, String> {
    load_units_checked(source_root).map_err(|error| format!("{}:{}", error.code, error.detail))
}

fn load_units_checked(source_root: &Path) -> Result<Vec<AuditUnit>, Failure> {
    let root = safe_child(&source_root.join(UNIT_ROOT), source_root)?;
    let invalid = |detail| Failure::new("parent_repository_audit_unit_invalid", detail);
    if !root.is_dir() {
        return Err(invalid(format!(
            "unit directory missing: {}",
            root.display()
        )));
    }
    let entries = fs::read_dir(&root).map_err(|error| invalid(error.to_string()))?;
    let mut paths = entries
        .map(|entry| entry.map(|item| item.path()))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| invalid(error.to_string()))?;
    paths.retain(|path| path.extension().is_some_and(|extension| extension == "md"));
    paths.sort();
    if paths.is_empty() {
        return Err(invalid(format!("no audit units: {}", root.display())));
    }
    let surface_re = Regex::new(r"\bsurface:([a-z0-9_.-]+)\b").expect("constant surface regex");
    let legacy_re =
        Regex::new(r"\bPRA-M[0-9]{2}\b|\bPRA-[CX][0-9]{3}\b").expect("constant migration regex");
    let mut units = Vec::new();
    let mut legacy_owners = BTreeMap::new();
    for path in paths {
        let path = safe_child(&path, source_root)?;
        let text = fs::read_to_string(&path).map_err(|error| invalid(error.to_string()))?;
        let missing: Vec<_> = SECTIONS
            .iter()
            .filter(|heading| section(&text, heading).is_empty())
            .copied()
            .collect();
        if !missing.is_empty() {
            return Err(invalid(format!(
                "unit={} missing_sections={}",
                path.display(),
                missing.join(",")
            )));
        }
        let surfaces = unique_matches(&surface_re, &section(&text, "Related Change Surfaces"));
        if surfaces.is_empty() {
            return Err(invalid(format!(
                "missing change surface: {}",
                path.display()
            )));
        }
        let legacy_ids = unique_matches(&legacy_re, &section(&text, "Legacy Migration IDs"));
        let relative = path
            .strip_prefix(source_root)
            .expect("checked source containment")
            .to_string_lossy()
            .replace('\\', "/");
        for legacy_id in &legacy_ids {
            if let Some(previous) = legacy_owners.insert(legacy_id.clone(), relative.clone()) {
                return Err(invalid(format!(
                    "duplicate legacy migration ID={legacy_id}: {previous}, {relative}"
                )));
            }
        }
        units.push(AuditUnit {
            unit_id: path
                .file_stem()
                .unwrap_or_default()
                .to_string_lossy()
                .into(),
            path: relative,
            surfaces,
            legacy_ids,
        });
    }
    Ok(units)
}

#[derive(Default)]
struct Args {
    command: String,
    root: PathBuf,
    scopes: Vec<String>,
    surfaces: Vec<String>,
    statuses: Vec<String>,
    json: bool,
}
fn parse(args: &[String]) -> Result<Args, String> {
    let Some(command) = args.first() else {
        return Err("a list or check subcommand is required".into());
    };
    if command != "list" && command != "check" {
        return Err(format!("unknown subcommand: {command}"));
    }
    let mut parsed = Args {
        command: command.clone(),
        ..Args::default()
    };
    let mut index = 1;
    while index < args.len() {
        let (key, inline) = args[index]
            .split_once('=')
            .map_or((args[index].as_str(), None), |(key, value)| {
                (key, Some(value))
            });
        let value = if let Some(value) = inline {
            value
        } else {
            index += 1;
            args.get(index)
                .map(String::as_str)
                .ok_or_else(|| format!("{key} requires a value"))?
        };
        match key {
            "--root" => parsed.root = value.into(),
            "--scope" => parsed.scopes.push(value.into()),
            "--surface" => {
                let value = value.strip_prefix("surface:").unwrap_or(value);
                if !value.is_empty() && !parsed.surfaces.iter().any(|item| item == value) {
                    parsed.surfaces.push(value.into());
                }
            }
            "--unit-status"
                if ["pass", "closed", "failed", "deferred", "blocked"].contains(&value) =>
            {
                parsed.statuses.push(value.into())
            }
            "--format" if value == "json" || value == "text" => parsed.json = value == "json",
            _ => return Err(format!("invalid argument: {key}={value}")),
        }
        index += 1;
    }
    if parsed.root.as_os_str().is_empty() {
        return Err("--root is required".into());
    }
    Ok(parsed)
}

fn evaluate(args: &Args) -> Result<Value, Failure> {
    let environment = std::env::vars().collect();
    let cwd = std::env::current_dir().map_err(|error| {
        Failure::new(
            "parent_repository_audit_parent_git_missing",
            error.to_string(),
        )
    })?;
    let resolution = resolve_source_roots(&cwd, &environment).map_err(|error| Failure {
        code: error.code,
        detail: error.detail,
        blocked: true,
    })?;
    let units = load_units_checked(&resolution.source_root)?;
    let expanded = expand_user_path(&args.root)
        .map_err(|error| Failure::new("parent_repository_audit_path_escape", error.to_string()))?;
    let parent = resolve_non_strict(&expanded)
        .map_err(|detail| Failure::new("parent_repository_audit_path_escape", detail))?;
    let output = Command::new("git")
        .arg("-C")
        .arg(&parent)
        .args(["ls-files", "-z"])
        .output()
        .map_err(|error| {
            Failure::new(
                "parent_repository_audit_parent_git_missing",
                error.to_string(),
            )
        })?;
    if !output.status.success() {
        return Err(Failure::new(
            "parent_repository_audit_parent_git_missing",
            String::from_utf8_lossy(&output.stderr).trim(),
        ));
    }
    let raw = String::from_utf8(output.stdout).map_err(|_| {
        Failure::new(
            "parent_repository_audit_parent_git_invalid",
            format!("non-UTF8 tracked path output: {}", parent.display()),
        )
    })?;
    let tracked: BTreeSet<_> = raw
        .split('\0')
        .filter(|item| !item.is_empty())
        .map(str::to_owned)
        .collect();
    let mut selected = BTreeSet::new();
    if args.scopes.is_empty() {
        selected.clone_from(&tracked);
    }
    for scope in &args.scopes {
        let candidate = Path::new(scope);
        let absolute = if candidate.is_absolute() {
            candidate.to_owned()
        } else {
            parent.join(candidate)
        };
        let safe = safe_child(&absolute, &parent)?;
        if safe == parent {
            selected.extend(tracked.iter().cloned());
        } else {
            let relative = safe
                .strip_prefix(&parent)
                .expect("checked parent containment")
                .to_string_lossy()
                .replace('\\', "/");
            if safe.is_dir() {
                let prefix = format!("{relative}/");
                selected.extend(
                    tracked
                        .iter()
                        .filter(|path| path.starts_with(&prefix))
                        .cloned(),
                );
            } else if tracked.contains(&relative) {
                selected.insert(relative);
            } else {
                return Err(Failure::new(
                    "parent_repository_audit_scope_missing",
                    format!("scope={scope} parent={}", parent.display()),
                ));
            }
        }
    }
    let unknown: Vec<_> = args
        .surfaces
        .iter()
        .filter(|surface| !units.iter().any(|unit| unit.surfaces.contains(surface)))
        .cloned()
        .collect();
    if !unknown.is_empty() {
        return Err(Failure::new(
            "parent_repository_audit_surface_unknown",
            format!("surfaces={}", unknown.join(",")),
        ));
    }
    let units: Vec<_> = units
        .into_iter()
        .filter(|unit| {
            args.surfaces.is_empty()
                || unit
                    .surfaces
                    .iter()
                    .any(|surface| args.surfaces.contains(surface))
        })
        .collect();
    let statuses: &[String] = if args.command == "check" {
        &args.statuses
    } else {
        &[]
    };
    let failed = statuses
        .iter()
        .any(|status| status == "failed" || status == "deferred");
    let blocked = !failed && statuses.iter().any(|status| status == "blocked");
    let status = if failed {
        "failed"
    } else if blocked {
        "blocked"
    } else {
        "pass"
    };
    let mut value = json!({"schema": SCHEMA, "status":status, "source_root":resolution.source_root, "parent_root":parent, "tracked_path_count":selected.len(), "unit_paths":units.iter().map(|unit| &unit.path).collect::<Vec<_>>(), "unit_records":units, "scope_paths":selected, "unit_statuses":statuses});
    if !args.surfaces.is_empty() {
        value["selected_surfaces"] = json!(args.surfaces);
    }
    if failed {
        value["failure_code"] = json!("parent_repository_audit_unit_status_failed");
    }
    Ok(value)
}

pub fn run(args: &[String]) -> i32 {
    if args.iter().any(|arg| arg == "--help" || arg == "-h") {
        println!("usage: agent-canon parent-repository-audit <list|check> --root ROOT [--scope PATH] [--surface SURFACE] [--unit-status STATUS] [--format text|json]");
        return 0;
    }
    let parsed = match parse(args) {
        Ok(args) => args,
        Err(error) => {
            eprintln!("parent-repository-audit: {error}");
            return 2;
        }
    };
    let value = match evaluate(&parsed) {
        Ok(value) => value,
        Err(error) => {
            json!({"schema":SCHEMA,"status":if error.blocked {"blocked"} else {"failed"},"failure_code":error.code,"failure_detail":error.detail,"unit_statuses":[]})
        }
    };
    if parsed.json {
        println!(
            "{}",
            serde_json::to_string_pretty(&value).expect("audit JSON serializes")
        );
    } else {
        println!(
            "PARENT_REPOSITORY_AUDIT_SCHEMA={SCHEMA}\nPARENT_REPOSITORY_AUDIT_STATUS={}",
            value["status"].as_str().unwrap_or("failed")
        );
        for key in [
            "failure_code",
            "source_root",
            "parent_root",
            "tracked_path_count",
        ] {
            if let Some(item) = value.get(key) {
                println!(
                    "PARENT_REPOSITORY_AUDIT_{}={}",
                    key.to_ascii_uppercase(),
                    item.as_str()
                        .map(str::to_owned)
                        .unwrap_or_else(|| item.to_string())
                );
            }
        }
        for (key, field) in [("selected_surfaces", "SURFACE"), ("unit_paths", "UNIT")] {
            for item in value[key].as_array().into_iter().flatten() {
                println!(
                    "PARENT_REPOSITORY_AUDIT_{field}={}",
                    item.as_str().unwrap_or("")
                );
            }
        }
        if let Some(items) = value["unit_statuses"]
            .as_array()
            .filter(|items| !items.is_empty())
        {
            println!(
                "PARENT_REPOSITORY_AUDIT_UNIT_STATUSES={}",
                items
                    .iter()
                    .filter_map(Value::as_str)
                    .collect::<Vec<_>>()
                    .join(",")
            );
        }
    }
    if value["status"] == "pass" {
        0
    } else if value["status"] == "blocked" && value.get("failure_detail").is_some() {
        2
    } else {
        1
    }
}
