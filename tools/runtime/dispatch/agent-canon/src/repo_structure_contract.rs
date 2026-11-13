// @dependency-start
// contract implementation
// responsibility Compares tree JSON path kinds with existing repository structure profiles.
// upstream design ../../../../../documents/structure/repo-structure-contract.toml owns profiles and ignore rules
// upstream implementation ./path_resolution.rs owns Python-compatible glob matching
// downstream test ../../../../../tests/agent_tools/test_repo_structure_contract.py preserves public CLI oracles
// @dependency-end

use crate::path_resolution::{python_fnmatch_case, resolve_non_strict};
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use serde::Serialize;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use toml_edit::{DocumentMut, Item, TableLike};

const DEFAULT_CONTRACT: &str = "documents/structure/repo-structure-contract.toml";
const USAGE: &str = "usage: agent-canon repo-structure-contract [--root ROOT] [--contract PATH] [--profile PROFILE] [--tree-json PATH] [--format text|json]";

#[derive(Default)]
struct IgnoreRules {
    names: Vec<String>,
    globs: Vec<String>,
}
struct ExpectedPath {
    path: String,
    kind: String,
}
struct Profile {
    id: String,
    detect_all: Vec<String>,
    required: Vec<ExpectedPath>,
    optional: Vec<ExpectedPath>,
}
#[derive(Serialize, PartialEq, Eq, PartialOrd, Ord)]
struct Finding {
    severity: &'static str,
    category: &'static str,
    path: String,
    detail: String,
}
#[derive(Serialize)]
struct Report {
    status: &'static str,
    profile: String,
    tree_source: String,
    checked_paths: usize,
    findings: Vec<Finding>,
}

fn strings(item: Option<&Item>) -> Vec<String> {
    item.and_then(Item::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(|value| value.as_str().map(str::to_owned))
                .collect()
        })
        .unwrap_or_default()
}
fn normalize(path: &str) -> String {
    let normalized = path.replace('\\', "/").trim_matches('/').to_owned();
    if normalized == "." {
        String::new()
    } else {
        normalized
    }
}
fn expected(item: Option<&Item>) -> Vec<ExpectedPath> {
    tables(item)
        .into_iter()
        .filter_map(|table| {
            let path = table.get("path")?.as_str()?;
            (!path.is_empty()).then(|| ExpectedPath {
                path: normalize(path),
                kind: table
                    .get("kind")
                    .and_then(Item::as_str)
                    .unwrap_or("any")
                    .into(),
            })
        })
        .collect()
}
fn tables(item: Option<&Item>) -> Vec<&dyn TableLike> {
    match item {
        Some(Item::ArrayOfTables(values)) => {
            values.iter().map(|value| value as &dyn TableLike).collect()
        }
        Some(Item::Value(toml_edit::Value::Array(values))) => values
            .iter()
            .filter_map(|value| value.as_inline_table().map(|value| value as &dyn TableLike))
            .collect(),
        _ => Vec::new(),
    }
}
fn load_contract(path: &Path) -> Result<(IgnoreRules, Vec<Profile>), String> {
    let document = fs::read_to_string(path)
        .map_err(|error| error.to_string())?
        .parse::<DocumentMut>()
        .map_err(|error| error.to_string())?;
    if document.get("catalog_kind").and_then(Item::as_str)
        != Some("agent_canon_repo_structure_contract")
    {
        return Err(format!(
            "invalid structure contract kind: {}",
            path.display()
        ));
    }
    let defaults = document.get("defaults").and_then(Item::as_table_like);
    let rules = IgnoreRules {
        names: strings(defaults.and_then(|table| table.get("ignore_names"))),
        globs: strings(defaults.and_then(|table| table.get("ignore_globs"))),
    };
    let profiles_item = document.get("profile");
    if !matches!(
        profiles_item,
        Some(Item::ArrayOfTables(_)) | Some(Item::Value(toml_edit::Value::Array(_)))
    ) {
        return Err(format!(
            "missing profile list in structure contract: {}",
            path.display()
        ));
    }
    let profiles: Vec<_> = tables(profiles_item)
        .into_iter()
        .filter_map(|table| {
            let id = table.get("id")?.as_str()?;
            (!id.is_empty()).then(|| Profile {
                id: id.into(),
                detect_all: strings(table.get("detect_all")),
                required: expected(table.get("required")),
                optional: expected(table.get("optional")),
            })
        })
        .collect();
    if profiles.is_empty() {
        return Err(format!(
            "no valid profiles in structure contract: {}",
            path.display()
        ));
    }
    Ok((rules, profiles))
}
fn ignored(path: &str, rules: &IgnoreRules) -> bool {
    let path = normalize(path);
    if path.is_empty() {
        return false;
    }
    let parts: Vec<_> = path.split('/').collect();
    parts
        .iter()
        .any(|part| rules.names.iter().any(|name| name == part))
        || rules.globs.iter().any(|pattern| {
            platform_fnmatch(&path, pattern)
                || platform_fnmatch(parts.last().copied().unwrap_or(""), pattern)
        })
}
fn platform_fnmatch(value: &str, pattern: &str) -> bool {
    #[cfg(windows)]
    {
        let lower = |value: &str| {
            icu_casemap::CaseMapper::new().lowercase_to_string(value, &Default::default())
        };
        python_fnmatch_case(
            &lower(&value.replace('/', "\\")),
            &lower(&pattern.replace('/', "\\")),
        )
    }
    #[cfg(not(windows))]
    {
        python_fnmatch_case(value, pattern)
    }
}
fn record(node: &Value, parent: &str, rules: &IgnoreRules, records: &mut BTreeMap<String, String>) {
    let Some(name) = node.get("name").and_then(Value::as_str) else {
        return;
    };
    let path = normalize(&if parent.is_empty() {
        name.to_owned()
    } else {
        format!("{parent}/{name}")
    });
    if ignored(&path, rules) {
        return;
    }
    let kind = match node.get("type").and_then(Value::as_str).unwrap_or("other") {
        "directory" => "dir",
        "file" => "file",
        "link" => "link",
        value => value,
    };
    records.insert(path.clone(), kind.into());
    if let Some(children) = node.get("contents").and_then(Value::as_array) {
        for child in children {
            record(child, &path, rules, records);
        }
    }
}
fn records(raw: &Value, rules: &IgnoreRules) -> BTreeMap<String, String> {
    let roots = raw
        .as_array()
        .map_or_else(|| vec![raw], |roots| roots.iter().collect());
    let mut records = BTreeMap::new();
    for root in roots {
        if !root.is_object() {
            continue;
        }
        if let Some(children) = root.get("contents").and_then(Value::as_array) {
            for child in children {
                record(child, "", rules, &mut records);
            }
        } else {
            record(root, "", rules, &mut records);
        }
    }
    records
}
fn check(
    root: &Path,
    contract: &Path,
    requested: &str,
    tree_json: Option<&Path>,
) -> Result<Report, String> {
    let (rules, profiles) = load_contract(contract)?;
    let (bytes, tree_source) = if let Some(path) = tree_json {
        (
            fs::read(path).map_err(|error| error.to_string())?,
            format!("tree-json:{}", path.display()),
        )
    } else {
        let mut names: BTreeSet<_> = rules.names.iter().cloned().collect();
        for pattern in &rules.globs {
            let tail = pattern
                .trim_end_matches('/')
                .rsplit('/')
                .next()
                .unwrap_or("");
            if !tail.is_empty() && tail != "**" {
                names.insert(tail.into());
            }
        }
        let mut command = Command::new("tree");
        command.args(["-a", "-J", "--noreport"]);
        if !names.is_empty() {
            command
                .arg("-I")
                .arg(names.into_iter().collect::<Vec<_>>().join("|"));
        }
        let result = command
            .arg(root)
            .output()
            .map_err(|error| error.to_string())?;
        if !result.status.success() {
            return Err(format!(
                "tree command failed: {}",
                String::from_utf8_lossy(&result.stderr).trim()
            ));
        }
        (result.stdout, format!("tree-command:{}", root.display()))
    };
    let raw: Value = serde_json::from_slice(&bytes).map_err(|error| error.to_string())?;
    let observed = records(&raw, &rules);
    let profile = profiles
        .iter()
        .find(|profile| {
            if requested == "auto" {
                profile
                    .detect_all
                    .iter()
                    .all(|path| observed.contains_key(path))
            } else {
                profile.id == requested
            }
        })
        .ok_or_else(|| {
            if requested == "auto" {
                "could not auto-detect repo structure profile".into()
            } else {
                format!("unknown repo structure profile: {requested}")
            }
        })?;
    let mut findings = Vec::new();
    for (entries, required) in [(&profile.required, true), (&profile.optional, false)] {
        for expected in entries {
            let actual = observed.get(&expected.path);
            let detail = match actual {
                None if required => Some(format!("missing-{}", expected.kind)),
                Some(actual) if expected.kind != "any" && &expected.kind != actual => {
                    Some(format!(
                        "{}kind-mismatch:{actual}!={}",
                        if required { "" } else { "optional-" },
                        expected.kind
                    ))
                }
                _ => None,
            };
            if let Some(detail) = detail {
                findings.push(Finding {
                    severity: if required { "error" } else { "warn" },
                    category: if required {
                        "required_path"
                    } else {
                        "optional_path"
                    },
                    path: expected.path.clone(),
                    detail,
                });
            }
        }
    }
    findings.sort();
    Ok(Report {
        status: if findings.iter().any(|finding| finding.severity == "error") {
            "fail"
        } else {
            "pass"
        },
        profile: profile.id.clone(),
        tree_source,
        checked_paths: observed.len(),
        findings,
    })
}

pub fn run(args: &[String]) -> i32 {
    let options = [
        "--help",
        "--root",
        "--contract",
        "--profile",
        "--tree-json",
        "--format",
    ];
    let choices: Vec<_> = options.iter().map(|&name| (name, name)).collect();
    let mut values = BTreeMap::from([
        ("--root", ".".to_owned()),
        ("--contract", DEFAULT_CONTRACT.into()),
        ("--profile", "auto".into()),
        ("--format", "text".into()),
    ]);
    let mut index = 0;
    while index < args.len() {
        if args[index] == "-h" {
            println!("{USAGE}");
            return 0;
        }
        let (raw, inline) = args[index]
            .split_once('=')
            .map_or((args[index].as_str(), None), |(name, value)| {
                (name, Some(value))
            });
        let option = match resolve_long_option_prefix(raw, &choices) {
            Ok(option) => option,
            Err(error) => {
                let detail = match error {
                    LongOptionError::Unrecognized => {
                        format!("unrecognized arguments: {}", args[index])
                    }
                    LongOptionError::Ambiguous(names) => {
                        format!("ambiguous option: {raw} could match {}", names.join(", "))
                    }
                };
                eprintln!("{USAGE}\n{detail}");
                return 2;
            }
        };
        if option == "--help" {
            println!("{USAGE}");
            return 0;
        }
        let value = if let Some(value) = inline {
            value
        } else {
            index += 1;
            let Some(value) = args.get(index) else {
                eprintln!("{USAGE}\nargument {raw}: expected one argument");
                return 2;
            };
            value
        };
        values.insert(option, value.into());
        index += 1;
    }
    if !["text", "json"].contains(&values["--format"].as_str()) {
        eprintln!("{USAGE}\ninvalid format");
        return 2;
    }
    let result = (|| {
        let root = resolve_non_strict(Path::new(&values["--root"]))?;
        let resolve = |value: &str| {
            let path = PathBuf::from(value);
            if path.is_absolute() {
                path
            } else {
                root.join(path)
            }
        };
        check(
            &root,
            &resolve(&values["--contract"]),
            &values["--profile"],
            values
                .get("--tree-json")
                .map(|value| resolve(value))
                .as_deref(),
        )
    })();
    let report = match result {
        Ok(report) => report,
        Err(error) => {
            eprintln!("REPO_STRUCTURE_ERROR={error}");
            return 2;
        }
    };
    if values["--format"] == "json" {
        println!(
            "{}",
            serde_json::to_string_pretty(&report).expect("serializable report")
        );
    } else {
        for finding in &report.findings {
            println!(
                "REPO_STRUCTURE_FINDING={}:{}:{}:{}",
                finding.severity, finding.category, finding.path, finding.detail
            );
        }
        println!("REPO_STRUCTURE_PROFILE={}\nREPO_STRUCTURE_TREE_SOURCE={}\nREPO_STRUCTURE_CHECKED_PATHS={}\nREPO_STRUCTURE_ERRORS={}\nREPO_STRUCTURE_WARNINGS={}\nREPO_STRUCTURE={}", report.profile, report.tree_source, report.checked_paths, report.findings.iter().filter(|finding| finding.severity == "error").count(), report.findings.iter().filter(|finding| finding.severity == "warn").count(), report.status);
    }
    i32::from(report.status == "fail")
}
