// @dependency-start
// contract implementation
// responsibility Inventories owned implementations and orders Rust migration families.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md all-own-tools migration contract
// upstream design ../../../../catalog.yaml public command identities and external providers
// upstream implementation migration_audit.rs shared source foundation checks
// downstream implementation ../../../../bin/agent-canon exposes the read-only planning command
// @dependency-end

use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use toml_edit::DocumentMut;
use yaml_rust2::YamlLoader;

const DEFAULT_LIMIT: usize = 12;
const SCAN_ROOTS: &[&str] = &["tools", "eval", ".codex/hooks", "tests", "templates"];
const SKIP_DIRS: &[&str] = &[
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "target",
    "build",
    "dist",
];

#[derive(Debug, PartialEq, Eq)]
struct Args {
    root: PathBuf,
    limit: usize,
    json: bool,
}

#[derive(Debug, Serialize)]
struct Family {
    id: &'static str,
    order: usize,
    prerequisites: &'static [&'static str],
}

// These are responsibility prerequisites from the design, not an inferred
// complete import graph. They deliberately keep shared authority before writers.
const FAMILIES: &[Family] = &[
    Family {
        id: "independent-inventory",
        order: 0,
        prerequisites: &[],
    },
    Family {
        id: "catalog-foundation",
        order: 10,
        prerequisites: &[],
    },
    Family {
        id: "authority-foundation",
        order: 20,
        prerequisites: &[],
    },
    Family {
        id: "source-analysis",
        order: 30,
        prerequisites: &["catalog-foundation"],
    },
    Family {
        id: "ast-analysis",
        order: 30,
        prerequisites: &["authority-foundation"],
    },
    Family {
        id: "runtime-execution",
        order: 40,
        prerequisites: &["catalog-foundation", "authority-foundation"],
    },
    Family {
        id: "archive-lifecycle",
        order: 50,
        prerequisites: &["authority-foundation", "runtime-execution"],
    },
    Family {
        id: "agent-workflow",
        order: 60,
        prerequisites: &[
            "catalog-foundation",
            "authority-foundation",
            "archive-lifecycle",
        ],
    },
    Family {
        id: "repository-operations",
        order: 60,
        prerequisites: &["authority-foundation", "archive-lifecycle"],
    },
    Family {
        id: "experiment-proof",
        order: 60,
        prerequisites: &["authority-foundation", "runtime-execution"],
    },
    Family {
        id: "validation-eval-hooks",
        order: 70,
        prerequisites: &[
            "agent-workflow",
            "source-analysis",
            "ast-analysis",
            "archive-lifecycle",
        ],
    },
];

#[derive(Debug, Serialize)]
struct InventoryRecord {
    path: String,
    classification: &'static str,
    responsibility: String,
    catalog_ids: Vec<String>,
    family: Option<&'static str>,
    python_delegation: Option<&'static str>,
}

#[derive(Debug, Serialize)]
struct ExternalRuntime {
    owner: String,
    source: String,
    contract: String,
}

#[derive(Debug, Serialize)]
struct Candidate {
    path: String,
    family: &'static str,
    order: usize,
    class: &'static str,
    remaining_prerequisites: Vec<&'static str>,
    contract_work: Option<&'static str>,
}

#[derive(Debug, Serialize)]
struct Plan {
    schema: &'static str,
    foundation_findings: Vec<String>,
    inventory: Vec<InventoryRecord>,
    counts: BTreeMap<&'static str, usize>,
    owned_python_by_scope: BTreeMap<&'static str, usize>,
    external_runtimes: Vec<ExternalRuntime>,
    families: &'static [Family],
    candidates: Vec<Candidate>,
    candidate_total: usize,
    catalogued_implementations: usize,
    uncatalogued_implementations: usize,
    findings: Vec<String>,
}

pub fn run(args: &[String]) -> i32 {
    let parsed = match Args::parse(args) {
        Ok(parsed) => parsed,
        Err(message) => {
            eprintln!("RUST_MIGRATION_PLAN=fail");
            eprintln!("RUST_MIGRATION_PLAN_FINDING=invalid-arguments:{message}");
            return 2;
        }
    };
    match build_plan(&parsed.root, parsed.limit) {
        Ok(plan) => render(&plan, &parsed),
        Err(message) => {
            eprintln!("RUST_MIGRATION_PLAN=fail");
            eprintln!("RUST_MIGRATION_PLAN_FINDING={message}");
            1
        }
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut result = Self {
            root: PathBuf::from("."),
            limit: DEFAULT_LIMIT,
            json: false,
        };
        let mut index = 0;
        while index < args.len() {
            let name = args[index].as_str();
            if !matches!(name, "--root" | "--limit" | "--format") {
                return Err(format!("unknown argument {name}"));
            }
            let value = args
                .get(index + 1)
                .ok_or_else(|| format!("{name} requires a value"))?;
            match name {
                "--root" => result.root = PathBuf::from(value),
                "--limit" => {
                    result.limit = value
                        .parse()
                        .map_err(|_| "--limit must be a positive integer".to_string())?;
                    if result.limit == 0 {
                        return Err("--limit must be greater than zero".to_string());
                    }
                }
                "--format" => match value.as_str() {
                    "text" => result.json = false,
                    "json" => result.json = true,
                    _ => return Err("--format must be text or json".to_string()),
                },
                _ => unreachable!(),
            }
            index += 2;
        }
        Ok(result)
    }
}

fn collect_sources(root: &Path, relative: &Path, paths: &mut Vec<String>) -> Result<(), String> {
    let path = root.join(relative);
    let metadata = fs::symlink_metadata(&path)
        .map_err(|error| format!("inventory-read:{}:{error}", relative.display()))?;
    if metadata.is_dir() && !metadata.is_symlink() {
        for entry in fs::read_dir(&path)
            .map_err(|error| format!("inventory-read:{}:{error}", relative.display()))?
        {
            let entry =
                entry.map_err(|error| format!("inventory-read:{}:{error}", relative.display()))?;
            if SKIP_DIRS.iter().any(|name| entry.file_name() == *name) {
                continue;
            }
            collect_sources(root, &relative.join(entry.file_name()), paths)?;
        }
    } else if metadata.is_symlink()
        || matches!(
            relative.extension().and_then(|value| value.to_str()),
            Some("py" | "rs")
        )
    {
        let text = relative.to_string_lossy();
        paths.push(if cfg!(windows) {
            text.replace('\\', "/")
        } else {
            text.into_owned()
        });
    }
    Ok(())
}

fn responsibility(text: &str) -> String {
    text.lines()
        .find_map(|line| {
            line.trim()
                .trim_start_matches('#')
                .trim_start_matches('/')
                .trim()
                .strip_prefix("responsibility ")
                .map(str::to_string)
        })
        .unwrap_or_default()
}

fn package_marker(text: &str) -> bool {
    let mut rest = text;
    let mut docstring_seen = false;
    loop {
        rest = rest.trim_start();
        if rest.is_empty() {
            return true;
        }
        if rest.starts_with('#') {
            rest = rest.split_once('\n').map_or("", |(_, tail)| tail);
            continue;
        }
        if !docstring_seen && (rest.starts_with("\"\"\"") || rest.starts_with("'''")) {
            let delimiter = &rest[..3];
            if let Some(end) = rest[3..].find(delimiter) {
                rest = &rest[3 + end + 3..];
                docstring_seen = true;
                continue;
            }
        }
        return false;
    }
}

fn classification(path: &str, text: &str, symlink: bool) -> &'static str {
    if symlink {
        return "source-view";
    }
    let parts: Vec<&str> = path.split('/').collect();
    if parts
        .iter()
        .any(|part| matches!(*part, "vendor" | "third_party" | "third-party"))
    {
        return "third-party-source";
    }
    if parts
        .iter()
        .any(|part| matches!(*part, "templates" | "fixtures" | "fixture"))
    {
        return "template-or-fixture";
    }
    if parts.contains(&"tests") || path.ends_with("/tests.rs") {
        return "test";
    }
    if path.ends_with(".rs") {
        return "native-source-unverified";
    }
    if path.ends_with("/__init__.py") && package_marker(text) {
        return "package-marker";
    }
    if path.starts_with("tools/") || path.starts_with("eval/") || path.starts_with(".codex/hooks/")
    {
        return "owned-python-implementation";
    }
    "unclassified-source"
}

fn family_for(path: &str) -> &'static str {
    if path.ends_with("/file_surface_inventory.py") {
        return "independent-inventory";
    }
    if path == "tools/runtime/manifest/manifest_rendering.py" {
        return "agent-workflow";
    }
    if path.starts_with("tools/runtime/manifest/")
        || path.ends_with("/skill_projection_registry.py")
        || path.ends_with("/skill_route_catalog.py")
        || path.ends_with("/tool_path_policy.py")
        || path.ends_with("/dependency_manifest.rs")
    {
        return "catalog-foundation";
    }
    if path.starts_with("tools/runtime/artifacts/")
        || path.starts_with("tools/runtime/authority/")
        || path.starts_with("tools/runtime/source/")
        || path.starts_with("tools/support/")
        || path == "tools/runtime/values.py"
        || path.ends_with("/workspace_scope.py")
        || path.ends_with("/parent_root_side_effects.py")
    {
        return "authority-foundation";
    }
    if path.ends_with("/helper_function_inventory.py")
        || path.ends_with("/log_surface_inventory.py")
        || path.starts_with("tools/validation/code/oop/")
        || path.ends_with("/python_structure_hash.rs")
        || path.ends_with("/python_algorithm_contract.rs")
    {
        return "ast-analysis";
    }
    if path.starts_with("tools/analysis/proof/")
        || path.starts_with("tools/analysis/hlo/")
        || path.starts_with("tools/analysis/numerical/")
        || path.starts_with("tools/experiments/")
        || path.ends_with("/check_jax_export_stack.py")
    {
        return "experiment-proof";
    }
    if path.starts_with("tools/analysis/") {
        return "source-analysis";
    }
    if path.starts_with("tools/runtime/container/")
        || path.ends_with("/tool_dispatch.py")
        || path.starts_with("tools/validation/ci/runners/")
    {
        return "runtime-execution";
    }
    if path.starts_with("tools/runtime/archive/")
        || path.starts_with("tools/runtime/lifecycle/")
        || path.starts_with("tools/audit/")
        || path.ends_with("/private_feedback.rs")
    {
        return "archive-lifecycle";
    }
    if path.starts_with("tools/agent/") {
        return "agent-workflow";
    }
    if path.starts_with("tools/repository/") {
        return "repository-operations";
    }
    "validation-eval-hooks"
}

fn python_delegation(path: &str, text: &str) -> Option<&'static str> {
    let (suffix, marker, detail) = if path.ends_with("/private_feedback.rs") {
        (
            ".rs",
            "tools/runtime/archive/private_feedback.py",
            "private-feedback Python implementation adapter",
        )
    } else if path.ends_with("/dependency_manifest.rs") {
        (
            ".rs",
            "tools/runtime/manifest/surface_manifest.py",
            "owned surface-manifest Python snapshot producer",
        )
    } else if path.ends_with("/python_structure_hash.rs")
        || path.ends_with("/python_algorithm_contract.rs")
    {
        (
            ".rs",
            "Command::new(\"python3\")",
            "embedded Python AST implementation",
        )
    } else {
        return None;
    };
    (path.ends_with(suffix) && text.contains(marker)).then_some(detail)
}

fn contract_work(path: &str, family: &str) -> Option<&'static str> {
    if path.ends_with("/jit_canonical_ir.py") || path.ends_with("/check_jax_export_stack.py") {
        Some("preserve dynamic CPython/JAX API through a reviewed native provider connection")
    } else if family == "ast-analysis" {
        Some(
            "select native parser and preserve Python AST/output semantics without embedded Python",
        )
    } else if path.ends_with("/parent_root_side_effects.py")
        || path.ends_with("/runtime_artifacts.py")
    {
        Some("preserve descriptor-relative writes, identities, locks and root capabilities with safe APIs")
    } else {
        None
    }
}

type CatalogPaths = BTreeMap<String, BTreeSet<String>>;

fn catalog(root: &Path, external: &mut Vec<ExternalRuntime>) -> Result<CatalogPaths, String> {
    let text = fs::read_to_string(root.join("tools/catalog.yaml"))
        .map_err(|error| format!("catalog-read:{error}"))?;
    let documents =
        YamlLoader::load_from_str(&text).map_err(|error| format!("catalog-parse:{error}"))?;
    let document = documents.first().ok_or("catalog-empty")?;
    let entries = document["entries"]
        .as_vec()
        .ok_or("catalog-entries-missing")?;
    let mut result = CatalogPaths::new();
    for entry in entries {
        let id = entry["id"].as_str().ok_or("catalog-id-invalid")?;
        let path = entry["path"].as_str().ok_or("catalog-path-invalid")?;
        result
            .entry(path.to_string())
            .or_default()
            .insert(id.to_string());
        if entry["dispatch"]["runtime"].as_str() == Some("native") {
            external.push(ExternalRuntime {
                owner: id.to_string(),
                source: "tools/catalog.yaml".to_string(),
                contract: "external executable; the catalog dispatcher remains AgentCanon-owned"
                    .to_string(),
            });
        }
    }
    if let Some(commands) = document["runtime_schema"]["rust_public_commands"].as_vec() {
        for command in commands {
            let id = command["id"].as_str().ok_or("catalog-rust-id-invalid")?;
            let path = command["path"]
                .as_str()
                .ok_or("catalog-rust-path-invalid")?;
            result
                .entry(path.to_string())
                .or_default()
                .insert(id.to_string());
        }
    }
    Ok(result)
}

fn external_providers(root: &Path, external: &mut Vec<ExternalRuntime>) -> Result<(), String> {
    let text = fs::read_to_string(root.join("agent-canon-environment.toml"))
        .map_err(|error| format!("environment-read:{error}"))?;
    let document = text
        .parse::<DocumentMut>()
        .map_err(|error| format!("environment-parse:{error}"))?;
    if let Some(providers) = document
        .get("external_provider")
        .and_then(|item| item.as_table_like())
    {
        for (name, provider) in providers.iter() {
            external.push(ExternalRuntime {
                owner: name.to_string(),
                source: "agent-canon-environment.toml".to_string(),
                contract: provider
                    .get("invocation")
                    .and_then(|item| item.as_str())
                    .unwrap_or("declared external provider")
                    .to_string(),
            });
        }
    }
    for path in [
        "tools/analysis/proof/jit_canonical_ir.py",
        "tools/validation/ci/checks/check_jax_export_stack.py",
    ] {
        if root.join(path).is_file() {
            external.push(ExternalRuntime {
                owner: path.to_string(), source: path.to_string(),
                contract: "dynamic CPython/JAX runtime; AgentCanon implementation remains in migration scope".to_string(),
            });
        }
    }
    Ok(())
}

fn build_plan(root: &Path, limit: usize) -> Result<Plan, String> {
    if !root.is_dir() {
        return Err(format!("source-root-missing:{}", root.display()));
    }
    let mut external_runtimes = Vec::new();
    let catalog = catalog(root, &mut external_runtimes)?;
    external_providers(root, &mut external_runtimes)?;
    let mut paths = Vec::new();
    let mut findings = Vec::new();
    for relative in SCAN_ROOTS {
        if root.join(relative).exists() {
            collect_sources(root, Path::new(relative), &mut paths)?;
        } else {
            findings.push(format!("inventory-root-missing:{relative}"));
        }
    }
    paths.sort();
    paths.dedup();
    let mut inventory = Vec::new();
    let mut counts = BTreeMap::new();
    let mut owned_python_by_scope = BTreeMap::new();
    let mut remaining_families = BTreeSet::new();
    let mut catalogued_implementations = 0;
    let mut uncatalogued_implementations = 0;
    for path in paths {
        let source = root.join(&path);
        let symlink = source.is_symlink();
        let text = if symlink {
            String::new()
        } else {
            fs::read_to_string(&source).map_err(|error| format!("inventory-read:{path}:{error}"))?
        };
        let class = classification(&path, &text, symlink);
        let delegation = (class == "native-source-unverified")
            .then(|| python_delegation(&path, &text))
            .flatten();
        let owned = class == "owned-python-implementation";
        let family = (owned || delegation.is_some()).then(|| family_for(&path));
        if let Some(family) = family {
            remaining_families.insert(family);
        }
        let catalog_ids: Vec<String> = catalog
            .get(&path)
            .map(|ids| ids.iter().cloned().collect())
            .unwrap_or_default();
        if owned {
            let scope = if path.starts_with("tools/") {
                "tools"
            } else if path.starts_with("eval/") {
                "eval"
            } else {
                ".codex/hooks"
            };
            *owned_python_by_scope.entry(scope).or_insert(0) += 1;
            if catalog_ids.is_empty() {
                uncatalogued_implementations += 1;
            } else {
                catalogued_implementations += 1;
            }
        }
        *counts.entry(class).or_insert(0) += 1;
        inventory.push(InventoryRecord {
            responsibility: responsibility(&text),
            path,
            classification: class,
            catalog_ids,
            family,
            python_delegation: delegation,
        });
    }
    for path in catalog.keys() {
        if !root.join(path).is_file() {
            findings.push(format!("catalog-source-missing:{path}"));
        }
    }
    let mut candidates = Vec::new();
    for item in &inventory {
        let Some(family_id) = item.family else {
            continue;
        };
        let family = FAMILIES
            .iter()
            .find(|family| family.id == family_id)
            .expect("registered family");
        let remaining_prerequisites: Vec<&str> = family
            .prerequisites
            .iter()
            .copied()
            .filter(|id| remaining_families.contains(id))
            .collect();
        let contract_work = contract_work(&item.path, family_id);
        let class = if !remaining_prerequisites.is_empty() {
            "dependency-first"
        } else if contract_work.is_some() {
            "contract-first"
        } else {
            "port-now"
        };
        candidates.push(Candidate {
            path: item.path.clone(),
            family: family_id,
            order: family.order,
            class,
            remaining_prerequisites,
            contract_work,
        });
    }
    candidates.sort_by(|a, b| a.order.cmp(&b.order).then_with(|| a.path.cmp(&b.path)));
    let candidate_total = candidates.len();
    candidates.truncate(limit);
    Ok(Plan {
        schema: "agent-canon.rust-migration-plan.v2",
        foundation_findings: crate::migration_audit::foundation_findings(root),
        inventory,
        counts,
        owned_python_by_scope,
        external_runtimes,
        families: FAMILIES,
        candidates,
        candidate_total,
        catalogued_implementations,
        uncatalogued_implementations,
        findings,
    })
}

fn render(plan: &Plan, args: &Args) -> i32 {
    let status = if plan.findings.is_empty() {
        "pass"
    } else {
        "fail"
    };
    if args.json {
        match serde_json::to_string_pretty(plan) {
            Ok(text) => println!("{text}"),
            Err(error) => {
                eprintln!("RUST_MIGRATION_PLAN_FINDING=serialize:{error}");
                return 1;
            }
        }
    } else {
        println!("RUST_MIGRATION_PLAN={status}");
        println!("RUST_MIGRATION_SOURCE_ROOT={}", args.root.display());
        println!(
            "RUST_MIGRATION_FOUNDATION={}",
            if plan.foundation_findings.is_empty() {
                "present"
            } else {
                "missing"
            }
        );
        for finding in &plan.foundation_findings {
            println!("RUST_MIGRATION_FOUNDATION_FINDING={finding}");
        }
        for (class, count) in &plan.counts {
            println!("RUST_MIGRATION_INVENTORY_COUNT=class={class} count={count}");
        }
        for (scope, count) in &plan.owned_python_by_scope {
            println!("RUST_MIGRATION_OWNED_PYTHON_COUNT=scope={scope} count={count}");
        }
        println!("RUST_MIGRATION_CATALOG_COVERAGE=catalogued_owned_python={} uncatalogued_owned_python={}", plan.catalogued_implementations, plan.uncatalogued_implementations);
        println!(
            "RUST_MIGRATION_COMPLETION=unverified native_source_presence_is_not_port_evidence"
        );
        for record in &plan.inventory {
            if let Some(reason) = record.python_delegation {
                println!(
                    "RUST_MIGRATION_PYTHON_DELEGATION=path={} reason={reason}",
                    record.path
                );
            }
        }
        for runtime in &plan.external_runtimes {
            println!(
                "RUST_MIGRATION_EXTERNAL_RUNTIME=owner={} source={} contract={}",
                runtime.owner, runtime.source, runtime.contract
            );
        }
        println!("RUST_MIGRATION_CANDIDATE_TOTAL={}", plan.candidate_total);
        println!("RUST_MIGRATION_CANDIDATE_COUNT={}", plan.candidates.len());
        for (index, candidate) in plan.candidates.iter().enumerate() {
            println!("RUST_MIGRATION_CANDIDATE=rank={} class={} order={} family={} path={} prerequisites={} contract={}",
                index + 1, candidate.class, candidate.order, candidate.family, candidate.path,
                candidate.remaining_prerequisites.join(","), candidate.contract_work.unwrap_or("preserve owning CLI/API and side-effect contract"));
        }
        for finding in &plan.findings {
            println!("RUST_MIGRATION_PLAN_FINDING={finding}");
        }
    }
    i32::from(!plan.findings.is_empty())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn parses_plan_options_and_rejects_zero_limit() {
        assert_eq!(Args::parse(&[]).unwrap().limit, DEFAULT_LIMIT);
        assert!(Args::parse(&["--limit".into(), "0".into()]).is_err());
        assert!(
            Args::parse(&["--format".into(), "json".into()])
                .unwrap()
                .json
        );
    }

    #[test]
    fn classifies_responsibilities_without_exempting_executable_initializers() {
        assert_eq!(
            classification(
                "tools/pkg/__init__.py",
                "# package\n\"\"\"Marker.\"\"\"\n",
                false
            ),
            "package-marker"
        );
        assert_eq!(
            classification("tools/pkg/__init__.py", "from .owner import run\n", false),
            "owned-python-implementation"
        );
        assert_eq!(
            classification("tools/pkg/fixtures/example.py", "", false),
            "template-or-fixture"
        );
        assert_eq!(
            classification("templates/experiments/run.py", "", false),
            "template-or-fixture"
        );
        assert_eq!(
            classification("tools/vendor/external.py", "", false),
            "third-party-source"
        );
        assert_eq!(classification("tests/test_owner.py", "", false), "test");
        assert_eq!(
            classification("eval/checkers/smoke_test_example.py", "", false),
            "owned-python-implementation"
        );
        assert_eq!(
            classification(".codex/hooks/hook_dispatcher.py", "", false),
            "owned-python-implementation"
        );
        assert_eq!(classification("tools/view.py", "", true), "source-view");
    }

    #[test]
    fn inventories_uncatalogued_hooks_and_orders_foundations_before_writers() {
        let root = fixture();
        for path in [
            "tools/runtime/authority/task_authority.py",
            "tools/runtime/lifecycle/task_close.py",
            "eval/producers/evaluate_agent_run.py",
            ".codex/hooks/hook_dispatcher.py",
            ".codex/hooks/hook_event_log.py",
        ] {
            write(
                &root,
                path,
                "# responsibility Owns fixture behavior.\nVALUE = 1\n",
            );
        }
        write(&root, "tools/pkg/__init__.py", "\"\"\"Package.\"\"\"\n");
        write(&root, "tests/test_fixture.py", "pass\n");
        write(&root, "templates/run.py", "pass\n");
        let plan = build_plan(&root, 20).unwrap();
        assert_eq!(plan.counts["owned-python-implementation"], 5);
        assert_eq!(plan.counts["package-marker"], 1);
        assert_eq!(plan.owned_python_by_scope[".codex/hooks"], 2);
        assert_eq!(plan.uncatalogued_implementations, 5);
        assert_eq!(plan.candidates[0].family, "authority-foundation");
        let close = plan
            .candidates
            .iter()
            .find(|item| item.path.ends_with("task_close.py"))
            .unwrap();
        assert_eq!(close.class, "dependency-first");
        assert!(close
            .remaining_prerequisites
            .contains(&"authority-foundation"));
        assert!(plan
            .candidates
            .iter()
            .any(|item| item.path.ends_with("evaluate_agent_run.py")));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn catalog_presence_does_not_complete_python_or_native_delegations() {
        let root = fixture();
        write(
            &root,
            "tools/catalog.yaml",
            "entries:\n  - id: authority\n    path: tools/runtime/authority/task_authority.py\n",
        );
        write(
            &root,
            "tools/runtime/authority/task_authority.py",
            "VALUE = 1\n",
        );
        write(
            &root,
            "tools/runtime/dispatch/agent-canon/src/private_feedback.rs",
            "const ADAPTER: &str = \"tools/runtime/archive/private_feedback.py\";\n",
        );
        let plan = build_plan(&root, 20).unwrap();
        assert_eq!(plan.catalogued_implementations, 1);
        assert_eq!(plan.candidate_total, 2);
        assert!(plan
            .inventory
            .iter()
            .any(|item| item.python_delegation.is_some()));
        let limited = build_plan(&root, 1).unwrap();
        assert_eq!(limited.candidates.len(), 1);
        assert_eq!(limited.candidate_total, 2);
        assert_eq!(limited.inventory.len(), plan.inventory.len());
        // A behavior-test reference is not an owned Python implementation call.
        assert!(python_delegation(
            "tools/runtime/dispatch/agent-canon/src/private_feedback.rs",
            "// downstream implementation tests/agent_tools/test_private_feedback.py",
        )
        .is_none());
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn inventories_literal_backslash_names_without_changing_source_identity() {
        let root = fixture();
        let relative = r"tools/analysis/code/literal\name.py";
        write(
            &root,
            relative,
            "# responsibility Preserves literal filename identity.\nVALUE = 1\n",
        );

        let plan = build_plan(&root, 12).expect("literal backslash source must remain readable");
        let record = plan
            .inventory
            .iter()
            .find(|item| item.path == relative)
            .expect("inventory must preserve the Unix basename");
        assert_eq!(
            record.responsibility,
            "Preserves literal filename identity."
        );
        assert_eq!(plan.counts["owned-python-implementation"], 1);
        assert_eq!(plan.candidates[0].path, relative);
        assert!(!root.join("tools/analysis/code/literal/name.py").exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn standalone_foundation_keeps_file_inventory_as_a_python_port_candidate() {
        let root = fixture();
        let path = "tools/analysis/code/file_surface_inventory.py";
        write(&root, path, "VALUE = 1\n");
        write(
            &root,
            "tools/catalog.yaml",
            "entries:\n  - id: file-surface-inventory\n    path: tools/analysis/code/file_surface_inventory.py\n",
        );

        let plan = build_plan(&root, 12).unwrap();
        assert_eq!(plan.catalogued_implementations, 1);
        assert_eq!(plan.counts["owned-python-implementation"], 1);
        assert_eq!(plan.candidates[0].path, path);
        assert_eq!(plan.candidates[0].family, "independent-inventory");
        assert_eq!(plan.candidates[0].class, "port-now");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn manifest_rendering_waits_for_workflow_prerequisites() {
        let root = fixture();
        let path = "tools/runtime/manifest/manifest_rendering.py";
        write(&root, path, "VALUE = 1\n");
        write(
            &root,
            "tools/runtime/lifecycle/task_close.py",
            "VALUE = 1\n",
        );

        let plan = build_plan(&root, 12).unwrap();
        let rendering = plan
            .candidates
            .iter()
            .find(|item| item.path == path)
            .unwrap();
        assert_eq!(rendering.family, "agent-workflow");
        assert_eq!(rendering.class, "dependency-first");
        assert!(rendering
            .remaining_prerequisites
            .contains(&"archive-lifecycle"));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn explicit_external_producer_execution_is_not_an_owned_python_delegation() {
        let path = "tools/runtime/dispatch/agent-canon/src/dependency_manifest.rs";
        assert!(
            python_delegation(path, "Command::new(\"python3\").arg(external_producer)").is_none()
        );
        assert!(python_delegation(
            path,
            "root.join(\"tools/runtime/manifest/surface_manifest.py\")"
        )
        .is_some());
    }

    #[test]
    fn missing_source_and_invalid_catalog_are_not_empty_success() {
        let root = fixture();
        write(&root, "tools/catalog.yaml", "entries: invalid\n");
        assert!(build_plan(&root, 12).is_err());
        fs::remove_dir_all(&root).unwrap();
        assert!(build_plan(&root, 12).is_err());
    }

    fn fixture() -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "agent-canon-rust-plan-{}-{suffix}",
            std::process::id()
        ));
        for directory in SCAN_ROOTS {
            fs::create_dir_all(root.join(directory)).unwrap();
        }
        write(&root, "tools/catalog.yaml", "entries: []\n");
        write(&root, "agent-canon-environment.toml", "version = 1\n");
        root
    }

    fn write(root: &Path, relative: &str, text: &str) {
        let path = root.join(relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, text).unwrap();
    }
}
