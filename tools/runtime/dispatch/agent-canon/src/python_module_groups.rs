// @dependency-start
// contract implementation
// responsibility Validates parent-repo Python module group contracts and maps Python files to design groups.
// upstream design ../../../documents/design/python-structure-hash.md Python module-group contract policy
// downstream implementation main.rs exposes python-module-groups-check
// downstream implementation python_structure_hash_report.rs uses contract-backed group names
// @dependency-end

use serde_json::json;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

pub const DEFAULT_CONTRACT_PATH: &str = "documents/design/python-module-groups.toml";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModuleGroupContract {
    pub groups: Vec<ModuleGroup>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModuleGroup {
    pub id: String,
    pub label: String,
    pub submodules: Vec<String>,
}

#[derive(Debug, PartialEq, Eq)]
struct Args {
    root: PathBuf,
    contract: PathBuf,
    format: OutputFormat,
}

#[derive(Debug, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

pub fn run_check(args: &[String]) -> i32 {
    match Args::parse(args).and_then(|args| check_contract(&args)) {
        Ok(report) => {
            render_report(&report);
            if report.findings.is_empty() {
                0
            } else {
                1
            }
        }
        Err(message) => {
            eprintln!("PY_MODULE_GROUPS_CHECK=fail");
            eprintln!("PY_MODULE_GROUPS_CHECK_FINDING={message}");
            2
        }
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut root = PathBuf::from(".");
        let mut contract = PathBuf::from(DEFAULT_CONTRACT_PATH);
        let mut format = OutputFormat::Text;
        let mut index = 0;
        while index < args.len() {
            match args[index].as_str() {
                "--root" => {
                    root = PathBuf::from(value_after(args, index, "--root")?);
                    index += 2;
                }
                "--contract" => {
                    contract = PathBuf::from(value_after(args, index, "--contract")?);
                    index += 2;
                }
                "--format" => {
                    format = match value_after(args, index, "--format")?.as_str() {
                        "text" => OutputFormat::Text,
                        "json" => OutputFormat::Json,
                        value => return Err(format!("--format must be text or json, got {value}")),
                    };
                    index += 2;
                }
                value if value.starts_with("--") => {
                    return Err(format!("unknown argument {value}"));
                }
                value => {
                    return Err(format!("unexpected positional argument {value}"));
                }
            }
        }
        Ok(Self {
            root,
            contract,
            format,
        })
    }
}

fn value_after(args: &[String], index: usize, flag: &str) -> Result<String, String> {
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("{flag} requires a value"))
}

#[derive(Debug, PartialEq, Eq)]
struct CheckReport {
    contract_path: String,
    discovered_submodules: Vec<String>,
    declared_submodules: Vec<String>,
    findings: Vec<String>,
    format: OutputFormat,
}

fn check_contract(args: &Args) -> Result<CheckReport, String> {
    let root = resolve_like_cwd(&args.root);
    let contract_path = if args.contract.is_absolute() {
        args.contract.clone()
    } else {
        root.join(&args.contract)
    };
    if !contract_path.is_file() {
        return Ok(CheckReport {
            contract_path: relative_path(&root, &contract_path),
            discovered_submodules: discover_python_submodules(&root),
            declared_submodules: Vec::new(),
            findings: vec![format!(
                "missing-contract:{}",
                relative_path(&root, &contract_path)
            )],
            format: args.format.clone(),
        });
    }
    let contract = load_contract(&contract_path)?;
    let discovered = discover_python_submodules(&root);
    let declared = contract_submodules(&contract);
    let mut findings = Vec::new();
    let discovered_set = discovered.iter().cloned().collect::<BTreeSet<_>>();
    let declared_set = declared.iter().cloned().collect::<BTreeSet<_>>();
    for submodule in discovered_set.difference(&declared_set) {
        findings.push(format!("missing-submodule:{submodule}"));
    }
    for submodule in declared_set.difference(&discovered_set) {
        findings.push(format!("unknown-submodule:{submodule}"));
    }
    findings.extend(duplicate_submodules(&contract));
    Ok(CheckReport {
        contract_path: relative_path(&root, &contract_path),
        discovered_submodules: discovered,
        declared_submodules: declared,
        findings,
        format: args.format.clone(),
    })
}

fn render_report(report: &CheckReport) {
    match report.format {
        OutputFormat::Json => {
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "status": if report.findings.is_empty() { "pass" } else { "fail" },
                    "contract_path": report.contract_path,
                    "discovered_submodules": report.discovered_submodules,
                    "declared_submodules": report.declared_submodules,
                    "findings": report.findings,
                }))
                .expect("json payload serializes")
            );
        }
        OutputFormat::Text => {
            for finding in &report.findings {
                println!("PY_MODULE_GROUPS_CHECK_FINDING={finding}");
            }
            println!(
                "PY_MODULE_GROUPS_CHECK_DISCOVERED={}",
                report.discovered_submodules.len()
            );
            println!(
                "PY_MODULE_GROUPS_CHECK_DECLARED={}",
                report.declared_submodules.len()
            );
            println!(
                "PY_MODULE_GROUPS_CHECK={}",
                if report.findings.is_empty() {
                    "pass"
                } else {
                    "fail"
                }
            );
        }
    }
}

pub fn load_default_contract(root: &Path) -> Option<ModuleGroupContract> {
    load_contract(&root.join(DEFAULT_CONTRACT_PATH)).ok()
}

pub fn load_contract(path: &Path) -> Result<ModuleGroupContract, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("failed to read {}: {error}", path.display()))?;
    parse_contract(&text)
}

pub fn group_for_path(path: &str, contract: Option<&ModuleGroupContract>) -> String {
    if let Some(contract) = contract {
        let normalized = normalize_path(path);
        let mut best: Option<(&ModuleGroup, usize)> = None;
        for group in &contract.groups {
            for submodule in &group.submodules {
                let prefix = format!("{}/", submodule.trim_end_matches('/'));
                if normalized == *submodule || normalized.starts_with(&prefix) {
                    let len = submodule.len();
                    if best.map(|(_, best_len)| len > best_len).unwrap_or(true) {
                        best = Some((group, len));
                    }
                }
            }
        }
        if let Some((group, _)) = best {
            return group.id.clone();
        }
        return "__unassigned__".to_string();
    }
    "__missing_contract__".to_string()
}

fn parse_contract(text: &str) -> Result<ModuleGroupContract, String> {
    let mut groups = Vec::new();
    let mut current: Option<ModuleGroup> = None;
    for raw_line in text.lines() {
        let line = raw_line.split('#').next().unwrap_or("").trim();
        if line.is_empty() {
            continue;
        }
        if line == "[[module_group]]" {
            if let Some(group) = current.take() {
                groups.push(group);
            }
            current = Some(ModuleGroup {
                id: String::new(),
                label: String::new(),
                submodules: Vec::new(),
            });
            continue;
        }
        let Some(group) = current.as_mut() else {
            continue;
        };
        if let Some(value) = line.strip_prefix("id =") {
            group.id = parse_string(value)?;
        } else if let Some(value) = line.strip_prefix("label =") {
            group.label = parse_string(value)?;
        } else if let Some(value) = line.strip_prefix("submodules =") {
            group.submodules = parse_string_array(value)?;
        }
    }
    if let Some(group) = current.take() {
        groups.push(group);
    }
    for group in &groups {
        if group.id.is_empty() {
            return Err("module_group id must not be empty".to_string());
        }
        if group.submodules.is_empty() {
            return Err(format!("module_group {} has no submodules", group.id));
        }
    }
    Ok(ModuleGroupContract { groups })
}

fn parse_string(value: &str) -> Result<String, String> {
    let value = value.trim();
    if value.starts_with('"') && value.ends_with('"') && value.len() >= 2 {
        return Ok(value[1..value.len() - 1].to_string());
    }
    Err(format!("expected quoted string, got {value}"))
}

fn parse_string_array(value: &str) -> Result<Vec<String>, String> {
    let value = value.trim();
    if !value.starts_with('[') || !value.ends_with(']') {
        return Err(format!("expected one-line string array, got {value}"));
    }
    let inner = &value[1..value.len() - 1];
    let mut values = Vec::new();
    for item in inner.split(',') {
        let item = item.trim();
        if item.is_empty() {
            continue;
        }
        values.push(normalize_path(&parse_string(item)?));
    }
    Ok(values)
}

fn discover_python_submodules(root: &Path) -> Vec<String> {
    let python_root = root.join("python");
    let mut submodules = BTreeSet::new();
    collect_python_submodules(&python_root, &python_root, &mut submodules);
    submodules.into_iter().collect()
}

fn collect_python_submodules(root: &Path, path: &Path, submodules: &mut BTreeSet<String>) {
    let Ok(entries) = fs::read_dir(path) else {
        return;
    };
    if excluded_python_path(root, path) {
        return;
    }
    if path.join("__init__.py").is_file() {
        submodules.insert(relative_path(root.parent().unwrap_or(root), path));
    }
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_python_submodules(root, &path, submodules);
        }
    }
}

fn excluded_python_path(root: &Path, path: &Path) -> bool {
    let relative = path.strip_prefix(root).unwrap_or(path);
    let text = relative.to_string_lossy().replace('\\', "/");
    text == "tests"
        || text.starts_with("tests/")
        || text == "typings"
        || text.starts_with("typings/")
        || text.ends_with(".egg-info")
        || text.split('/').any(|part| part == "__pycache__")
}

fn contract_submodules(contract: &ModuleGroupContract) -> Vec<String> {
    contract
        .groups
        .iter()
        .flat_map(|group| group.submodules.iter().cloned())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn duplicate_submodules(contract: &ModuleGroupContract) -> Vec<String> {
    let mut owner = BTreeMap::<String, String>::new();
    let mut findings = Vec::new();
    for group in &contract.groups {
        for submodule in &group.submodules {
            if let Some(previous) = owner.insert(submodule.clone(), group.id.clone()) {
                findings.push(format!(
                    "duplicate-submodule:{submodule}:groups={previous},{}",
                    group.id
                ));
            }
        }
    }
    findings
}

fn normalize_path(path: &str) -> String {
    path.trim().trim_matches('/').replace('\\', "/")
}

fn resolve_like_cwd(path: &Path) -> PathBuf {
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(path)
    }
}

fn relative_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

impl Clone for OutputFormat {
    fn clone(&self) -> Self {
        match self {
            OutputFormat::Text => OutputFormat::Text,
            OutputFormat::Json => OutputFormat::Json,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_module_group_contract() {
        let contract = parse_contract(
            r#"
[[module_group]]
id = "base"
label = "Base"
submodules = ["python/pkg/base", "python/pkg/protocols"]
"#,
        )
        .expect("contract parses");
        assert_eq!(contract.groups[0].id, "base");
        assert_eq!(contract.groups[0].submodules.len(), 2);
    }

    #[test]
    fn maps_path_to_longest_matching_group() {
        let contract = parse_contract(
            r#"
[[module_group]]
id = "pkg"
label = "Package"
submodules = ["python/pkg"]

[[module_group]]
id = "pkg_base"
label = "Base"
submodules = ["python/pkg/base"]
"#,
        )
        .expect("contract parses");
        assert_eq!(
            group_for_path("python/pkg/base/operators.py", Some(&contract)),
            "pkg_base"
        );
        assert_eq!(
            group_for_path("python/tests/base/test_operators.py", Some(&contract)),
            "__unassigned__"
        );
    }

    #[test]
    fn discovers_python_submodules_without_tests() {
        let root = std::env::temp_dir().join(format!(
            "agent-canon-python-module-groups-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("python/pkg/base")).expect("base dir");
        fs::create_dir_all(root.join("python/tests/base")).expect("test dir");
        fs::write(root.join("python/pkg/__init__.py"), "").expect("pkg init");
        fs::write(root.join("python/pkg/base/__init__.py"), "").expect("base init");
        fs::write(root.join("python/tests/base/__init__.py"), "").expect("test init");
        assert_eq!(
            discover_python_submodules(&root),
            vec!["python/pkg", "python/pkg/base"]
        );
        fs::remove_dir_all(root).expect("cleanup temp tree");
    }
}
