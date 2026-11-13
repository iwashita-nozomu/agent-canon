// @dependency-start
// contract implementation
// responsibility Exposes existing runtime path, archive, gate, and read-only mount APIs to shell callers.
// upstream implementation runtime_boundary.rs owns runtime filesystem capabilities
// upstream implementation eval_archive_paths.rs owns eval archive layout
// upstream implementation update_lifecycle_contract.rs owns G1 validation
// downstream test ../tests/runtime_paths_native.rs verifies shell-facing operations and unsafe path rejection
// @dependency-end

use crate::runtime_boundary::RuntimeArtifactBoundary;
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;

fn required<'a>(values: &'a BTreeMap<String, String>, key: &str) -> Result<&'a str, String> {
    values
        .get(key)
        .map(String::as_str)
        .ok_or_else(|| format!("--{key} is required"))
}
fn run_inner(args: &[String]) -> Result<i32, String> {
    if args
        .iter()
        .any(|value| matches!(value.as_str(), "--help" | "-h"))
    {
        println!("usage: agent-canon runtime-paths <root|path|ensure-dir|check-control|check-read-only|gate-g1|temp-dir|remove-tree|copy-read-only|capture-subprocess|detect-secrets-report|write-file|receipt-identity> [options]");
        return Ok(0);
    }
    let action = args.first().ok_or("runtime-paths action is required")?;
    if ![
        "root",
        "path",
        "ensure-dir",
        "check-control",
        "check-read-only",
        "gate-g1",
        "temp-dir",
        "remove-tree",
        "copy-read-only",
        "capture-subprocess",
        "detect-secrets-report",
        "write-file",
        "receipt-identity",
    ]
    .contains(&action.as_str())
    {
        return Err(format!("unknown runtime-paths action: {action}"));
    }
    let mut values = BTreeMap::new();
    let mut index = 1;
    let mut command = &[][..];
    while index < args.len() {
        let key = &args[index];
        if key == "--" {
            command = &args[index + 1..];
            break;
        }
        if !key.starts_with("--") {
            return Err(format!("unexpected argument: {key}"));
        }
        index += 1;
        let value = args
            .get(index)
            .ok_or_else(|| format!("{key}: expected one argument"))?;
        if values
            .insert(key.trim_start_matches("--").into(), value.clone())
            .is_some()
        {
            return Err(format!("duplicate option: {key}"));
        }
        index += 1;
    }
    match action.as_str() {
        "check-control" => {
            let source = Path::new(required(&values, "source-root")?)
                .canonicalize()
                .map_err(|error| error.to_string())?;
            let control = crate::path_resolution::resolve_non_strict(Path::new(required(
                &values,
                "control-parent-root",
            )?))?;
            if source == control {
                return Err("control parent root must differ from source root".into());
            }
            Ok(0)
        }
        "check-read-only" => {
            let root = Path::new(required(&values, "source-root")?)
                .canonicalize()
                .map_err(|error| error.to_string())?;
            let output=Command::new("findmnt").args(["--kernel","--first-only","--direction","backward","--list","--target"]).arg(root).args(["--json","--output","TARGET,VFS-OPTIONS"]).output().map_err(|error|format!("AGENT_CANON_STATIC_GATE=fail reason=target_mount_query_failed error={error}"))?;
            if !output.status.success() {
                return Err("AGENT_CANON_STATIC_GATE=fail reason=target_mount_query_failed".into());
            }
            let payload: Value = serde_json::from_slice(&output.stdout).map_err(|error| {
                format!(
                    "AGENT_CANON_STATIC_GATE=fail reason=target_mount_query_failed error={error}"
                )
            })?;
            let rows = payload
                .get("filesystems")
                .and_then(Value::as_array)
                .filter(|rows| rows.len() == 1)
                .ok_or("AGENT_CANON_STATIC_GATE=fail reason=target_mount_missing")?;
            let mount = rows[0]
                .get("target")
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
                .ok_or("AGENT_CANON_STATIC_GATE=fail reason=target_mount_columns_missing")?;
            let flags = rows[0]
                .get("vfs-options")
                .and_then(Value::as_str)
                .ok_or("AGENT_CANON_STATIC_GATE=fail reason=target_mount_columns_missing")?;
            if !flags.split(',').any(|flag| flag == "ro")
                || flags.split(',').any(|flag| flag == "rw")
            {
                return Err(format!(
                    "AGENT_CANON_STATIC_GATE=fail reason=target_mount_not_read_only mount={mount}"
                ));
            }
            println!("AGENT_CANON_STATIC_GATE_TARGET_MOUNT=read-only mount={mount}");
            Ok(0)
        }
        "gate-g1" => {
            let payload: Value = serde_json::from_slice(
                &std::fs::read(required(&values, "input")?).map_err(|error| error.to_string())?,
            )
            .map_err(|error| error.to_string())?;
            let gates = payload
                .get("gate_verdicts")
                .and_then(Value::as_array)
                .ok_or("agent_canon_pr_gate_bundle:gate_verdicts_missing")?;
            crate::update_lifecycle_contract::validate_gate_chain(gates, Some(&["G1"]), true)
                .map_err(|error| error.to_string())?;
            println!("AGENT_CANON_G1_RECEIPT=consumed\nAGENT_CANON_PR_GATE_ORDER=G1");
            Ok(0)
        }
        "receipt-identity" => {
            let path = required(&values, "input")?;
            let payload: Value = serde_json::from_slice(&std::fs::read(path).map_err(|error| {
                format!("AgentCanon source identity receipt is unavailable: {path}: {error}")
            })?)
            .map_err(|error| {
                format!("AgentCanon source identity receipt is unavailable: {path}: {error}")
            })?;
            let expected = required(&values, "expected-identity")?;
            if payload.get("source_identity").and_then(Value::as_str) != Some(expected) {
                return Err(format!(
                    "AgentCanon receipt source identity mismatch: {}!={expected}",
                    payload.get("source_identity").unwrap_or(&Value::Null)
                ));
            }
            Ok(0)
        }
        "detect-secrets-report" => {
            let payload: Value = serde_json::from_slice(
                &std::fs::read(required(&values, "input")?).map_err(|error| error.to_string())?,
            )
            .map_err(|error| error.to_string())?;
            let empty = serde_json::Map::new();
            let results = match payload.get("results") {
                None => &empty,
                Some(value) => value
                    .as_object()
                    .ok_or("detect-secrets results must be an object")?,
            };
            let mut count = 0;
            for items in results.values() {
                count += items
                    .as_array()
                    .ok_or("detect-secrets findings must be arrays")?
                    .len();
            }
            println!("SECRET_SCAN_DETECT_SECRETS_FINDINGS={count}");
            if count > 0 {
                for (path, items) in results {
                    println!(
                        "SECRET_SCAN_DETECT_SECRETS_PATH={path} findings={}",
                        items.as_array().expect("validated array").len()
                    );
                }
            }
            Ok(i32::from(count > 0))
        }
        _ => {
            let source = Path::new(required(&values, "source-root")?);
            let runtime = values.get("runtime-root").map(PathBuf::from);
            let read_root = RuntimeArtifactBoundary::resolve_read_path(
                source,
                runtime.as_deref(),
                Path::new(".root-probe"),
            )?
            .parent()
            .ok_or("runtime root has no parent")?
            .to_path_buf();
            if let Some(target) = values.get("target-root") {
                let target = Path::new(target)
                    .canonicalize()
                    .map_err(|error| error.to_string())?;
                if target.starts_with(&read_root) || read_root.starts_with(&target) {
                    return Err("runtime root must be outside target repository".into());
                }
                if let Some(control) = values.get("control-parent-root") {
                    let control = Path::new(control)
                        .canonicalize()
                        .map_err(|error| error.to_string())?;
                    if !target.starts_with(control) {
                        return Err("target repository is outside control root".into());
                    }
                }
            }
            if values.get("create").is_some_and(|value| value == "false") {
                let path = if action == "root" {
                    read_root
                } else if action == "path" {
                    RuntimeArtifactBoundary::resolve_read_path(
                        source,
                        runtime.as_deref(),
                        Path::new(required(&values, "candidate")?),
                    )?
                } else {
                    return Err("--create false supports root and path".into());
                };
                println!("{}", path.display());
                return Ok(0);
            }
            let boundary = RuntimeArtifactBoundary::for_source(source, runtime.as_deref(), true)?;
            let result = match action.as_str() {
                "root" => boundary.root().to_path_buf(),
                "path" => boundary.resolve(Path::new(required(&values, "candidate")?))?,
                "ensure-dir" => boundary.ensure_directory(Path::new(required(&values, "candidate")?))?,
                "temp-dir" => boundary.temporary_directory(
                    Path::new(required(&values, "candidate")?),
                    required(&values, "prefix")?,
                )?,
                "remove-tree" => {
                    boundary.remove_directory_tree(Path::new(required(&values, "candidate")?))?;
                    return Ok(0);
                }
                "copy-read-only" => boundary.copy_source_file(
                    Path::new(required(&values, "source")?),
                    Path::new(required(&values, "candidate")?),
                )?,
                "write-file" => {
                    let bytes = boundary
                        .read_bytes(Path::new(required(&values, "input")?))?
                        .ok_or("runtime input file is missing")?;
                    boundary.atomic_write_bytes(
                        Path::new(required(&values, "candidate")?),
                        &bytes,
                        0o600,
                    )?
                }
                "capture-subprocess" => {
                    let target = boundary.resolve(Path::new(required(&values, "candidate")?))?;
                    let executable = command
                        .first()
                        .ok_or("capture-subprocess requires a command after --")?;
                    let output = Command::new(executable)
                        .args(&command[1..])
                        .output()
                        .map_err(|error| error.to_string())?;
                    use std::io::Write;
                    std::io::stderr()
                        .write_all(&output.stderr)
                        .map_err(|error| error.to_string())?;
                    boundary.atomic_write_bytes(&target, &output.stdout, 0o600)?;
                    return Ok(output.status.code().unwrap_or(1));
                }
                _ => return Err(format!("unknown runtime-paths action: {action}")),
            };
            println!("{}", result.display());
            Ok(0)
        }
    }
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
