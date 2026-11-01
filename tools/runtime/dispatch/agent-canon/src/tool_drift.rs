// @dependency-start
// contract implementation
// responsibility Detects drift between tool contracts, convention docs, and dependency manifests using native source and catalog owners.
// upstream design ../../../../../documents/design/source-owned-dependency-validation.md source-owned dependency authority
// upstream design ../../../../../documents/design/dependency-manifest-design.md dependency manifest and graph semantics
// upstream design ../../../../../agents/skills/agent-canon-update.md PR validation contract
// upstream design ../../../../../agents/canonical/CODEX_SUBAGENTS.md subagent wave routing contract
// upstream design ../../../../../agents/TASK_WORKFLOWS.md workflow routing contract
// upstream design ../../../../../agents/skills/agent-orchestration.md orchestration routing contract
// upstream design ../../../../../documents/conventions/REVIEW_PROCESS.md closeout validation policy
// upstream design ../../../../catalog.yaml structured tool catalog
// upstream design ../../../../../documents/tools/tool-docs.toml one-to-one tool documentation map
// upstream implementation catalog/tool_catalog.rs validates catalog structure and resolves source paths
// upstream implementation catalog/path_policy.rs owns retired tool path policy
// upstream implementation ../../../../validation/semantic/convention/check_convention_compliance.py verifies skill-routing markers
// upstream implementation graph_client.rs provides typed source-derived dependency facts
// downstream implementation ../../../../validation/ci/runners/run_all_checks.sh runs the native drift checker
// downstream implementation ../../../../../tests/agent_tools/test_tool_drift.py tests the CLI contract
// @dependency-end

use crate::graph_client::{GraphClient, GraphClientError, GraphDependencyFact};
use agent_canon::catalog::{path_policy, tool_catalog};
use regex::Regex;
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;
use yaml_rust2::{Yaml, YamlLoader};

const USAGE: &str =
    "usage: agent-canon tool-drift [--root ROOT] [--contract CONTRACT]... [--format text|json]";
const HELP: &str = "usage: agent-canon tool-drift [--root ROOT] [--contract CONTRACT]... [--format text|json]\n\nCheck tool/convention drift using dependency manifests as the trace map.\n\noptions:\n  -h, --help            show this help message and exit\n  --root ROOT           repository root\n  --contract CONTRACT   limit checks to one contract; may be repeated\n  --format FORMAT       text or json";

const fn direct_link(target: &'static str) -> LinkCheck {
    LinkCheck {
        target,
        direct_required: true,
        reverse_required: false,
    }
}

const fn reverse_link(target: &'static str) -> LinkCheck {
    LinkCheck {
        target,
        direct_required: true,
        reverse_required: true,
    }
}

#[derive(Clone, Copy)]
struct LinkCheck {
    target: &'static str,
    direct_required: bool,
    reverse_required: bool,
}

#[derive(Clone, Copy)]
struct TextCheck {
    path: &'static str,
    snippet: &'static str,
    detail: &'static str,
}

#[derive(Clone, Copy)]
struct CommandCheck {
    path: &'static str,
    pattern: &'static str,
    detail: &'static str,
    required_count: usize,
}

struct ToolContract {
    name: &'static str,
    tool: &'static str,
    links: &'static [LinkCheck],
    text_checks: &'static [TextCheck],
    command_checks: &'static [CommandCheck],
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct Finding {
    kind: String,
    contract: String,
    path: String,
    detail: String,
}

impl Finding {
    fn new(
        kind: impl Into<String>,
        contract: impl Into<String>,
        path: impl Into<String>,
        detail: impl Into<String>,
    ) -> Self {
        Self {
            kind: kind.into(),
            contract: contract.into(),
            path: path.into(),
            detail: detail.into(),
        }
    }

    fn render(&self) -> String {
        format!(
            "TOOL_CONVENTION_DRIFT_FINDING={}:{}:{}:{}",
            self.kind, self.contract, self.path, self.detail
        )
    }
}

const CONTRACTS: &[ToolContract] = &[
    ToolContract {
        name: "github_pr_flow",
        tool: "tools/validation/ci/checks/check_github_workflows.py",
        links: &[
            direct_link("agents/skills/agent-canon-update.md"),
            direct_link(".github/AGENTS.md"),
            direct_link(".github/PULL_REQUEST_TEMPLATE.md"),
            direct_link("templates/documents/github/pull-request/agent_canon.md"),
            direct_link("README.md"),
        ],
        text_checks: &[],
        command_checks: &[],
    },
    ToolContract {
        name: "tool_catalog",
        tool: "tools/runtime/dispatch/agent-canon/src/catalog/tool_catalog.rs",
        links: &[
            reverse_link("tools/catalog.yaml"),
            direct_link("tools/README.md"),
            direct_link("documents/tools/README.md"),
            direct_link("documents/tools/tool-docs.toml"),
            direct_link("documents/tools/repo-local-tool-imports.md"),
            direct_link("tools/validation/ci/runners/run_all_checks.sh"),
            direct_link("tests/agent_tools/test_tool_catalog.py"),
        ],
        text_checks: &[
            TextCheck {
                path: "tools/README.md",
                snippet: "tools/catalog.yaml",
                detail: "missing-tool-catalog-pointer",
            },
            TextCheck {
                path: "documents/tools/README.md",
                snippet: "tools/catalog.yaml",
                detail: "missing-tool-catalog-pointer",
            },
            TextCheck {
                path: "documents/tools/README.md",
                snippet: "tool-docs.toml",
                detail: "missing-tool-docs-pointer",
            },
            TextCheck {
                path: "documents/tools/repo-local-tool-imports.md",
                snippet: "tools/catalog.yaml",
                detail: "missing-tool-catalog-pointer",
            },
        ],
        command_checks: &[],
    },
    ToolContract {
        name: "responsibility_scope",
        tool: "tools/validation/semantic/responsibility/responsibility_scope.py",
        links: &[
            direct_link("responsibility-scope.toml"),
            direct_link("templates/documents/responsibility-scope.template.toml"),
            direct_link("documents/design/responsibility-scope-management.md"),
            direct_link("tools/catalog.yaml"),
            direct_link("tools/README.md"),
            direct_link("documents/tools/README.md"),
            direct_link("tools/validation/ci/runners/run_all_checks.sh"),
            direct_link("tests/agent_tools/test_responsibility_scope.py"),
        ],
        text_checks: &[],
        command_checks: &[],
    },
    ToolContract {
        name: "tool_rejection_preflight",
        tool: "tools/runtime/dispatch/agent-canon/src/tool_rejection_preflight.rs",
        links: &[
            direct_link("agents/COMMUNICATION_PROTOCOL.md"),
            direct_link("agents/skills/codex-task-workflow.md"),
            direct_link("tools/runtime/dispatch/agent-canon/src/responsibility_scope.rs"),
            direct_link("tools/README.md"),
            direct_link("documents/tools/README.md"),
            direct_link("tests/agent_tools/test_tool_rejection_preflight.py"),
        ],
        text_checks: &[TextCheck {
            path: "agents/COMMUNICATION_PROTOCOL.md",
            snippet: "`responsibility_scope` gate records",
            detail: "missing-responsibility-scope-preflight-protocol",
        }],
        command_checks: &[],
    },
    ToolContract {
        name: "eval_accumulation",
        tool: "eval/checkers/eval_accumulation_check.py",
        links: &[
            direct_link("eval/definitions/README.md"),
            direct_link("documents/runtime/runtime-log-archive.md"),
            direct_link("documents/runtime/runtime-log-archive-migration.md"),
            direct_link("tools/README.md"),
            direct_link("documents/tools/README.md"),
            direct_link("tools/validation/ci/runners/run_all_checks.sh"),
            direct_link("tests/agent_tools/test_eval_accumulation_check.py"),
        ],
        text_checks: &[],
        command_checks: &[],
    },
    ToolContract {
        name: "run_accumulated_agent_evals",
        tool: "eval/producers/run_accumulated_agent_evals.py",
        links: &[
            direct_link("eval/definitions/README.md"),
            direct_link("documents/runtime/runtime-log-archive.md"),
            direct_link("tools/README.md"),
            direct_link("documents/tools/README.md"),
            direct_link("tools/catalog.yaml"),
            direct_link("tools/validation/ci/runners/run_all_checks.sh"),
            direct_link(".github/workflows/agent-canon-static-gates.yml"),
            direct_link("tests/agent_tools/test_run_accumulated_agent_evals.py"),
        ],
        text_checks: &[],
        command_checks: &[],
    },
    ToolContract {
        name: "generated_artifact_guard",
        tool: "tools/runtime/dispatch/agent-canon/src/report_artifact_checks.rs",
        links: &[
            direct_link("tools/runtime/artifacts/report_artifact_checks.py"),
            direct_link("documents/design/request-intent-and-update-relation.md"),
            direct_link("agents/canonical/ARTIFACT_PLACEMENT.md"),
            direct_link("templates/agents/closeout_gate.md"),
            direct_link("tools/runtime/dispatch/agent-canon/src/main.rs"),
            direct_link("tools/README.md"),
            direct_link("documents/tools/README.md"),
            direct_link("tools/catalog.yaml"),
            direct_link("tools/validation/ci/checks/check_agent_canon_pr.sh"),
            direct_link("tests/agent_tools/test_generated_artifact_guard.py"),
            direct_link("tests/agent_tools/test_tool_drift.py"),
            direct_link("tools/runtime/dispatch/agent-canon/tests/generated_artifact_guard_native.rs"),
        ],
        text_checks: &[],
        command_checks: &[CommandCheck {
            path: "tools/validation/ci/checks/check_agent_canon_pr.sh",
            pattern: r#"^run_agent_canon\s+generated-artifact-guard\s+--root\s+"\$\{WORKSPACE_ROOT\}"\s*$"#,
            detail: "missing-generated-artifact-pr-guard",
            required_count: 1,
        }],
    },
    ToolContract {
        name: "agent_canon_pr_check",
        tool: "tools/validation/ci/checks/check_agent_canon_pr.sh",
        links: &[
            direct_link("agents/skills/agent-canon-update.md"),
            direct_link(".github/PULL_REQUEST_TEMPLATE.md"),
            direct_link("tools/runtime/dispatch/agent-canon/src/report_artifact_checks.rs"),
            direct_link("tools/validation/semantic/runtime/check_agent_runtime_alignment.py"),
            direct_link("tools/validation/semantic/convention/check_convention_compliance.py"),
            direct_link("tools/validation/ci/checks/check_github_workflows.py"),
        ],
        text_checks: &[TextCheck {
            path: "tools/validation/ci/checks/check_agent_canon_pr.sh",
            snippet: "python3 \"${WORKSPACE_ROOT}/tools/validation/semantic/runtime/check_agent_runtime_alignment.py\"",
            detail: "missing-agent-runtime-alignment-check",
        }],
        command_checks: &[],
    },
    ToolContract {
        name: "convention_compliance",
        tool: "tools/validation/semantic/convention/check_convention_compliance.py",
        links: &[
            direct_link("documents/conventions/README.md"),
            direct_link("agents/canonical/CODEX_COMPLETION.md"),
            direct_link("documents/codex/codex-configuration-reference.md"),
            direct_link("documents/conventions/coding-conventions-house-style.md"),
            direct_link(".codex/README.md"),
            direct_link("tools/catalog.yaml"),
            direct_link("tools/validation/semantic/convention/convention_compliance_contracts.toml"),
            direct_link("tools/validation/semantic/skills/check_skill_frontmatter.py"),
            direct_link("tools/validation/ci/runners/run_all_checks.sh"),
            direct_link("tools/runtime/dispatch/agent-canon/src/tool_drift.rs"),
            direct_link("tests/agent_tools/test_check_convention_compliance.py"),
        ],
        text_checks: &[],
        command_checks: &[],
    },
    ToolContract {
        name: "repo_dependency_review",
        tool: "tools/analysis/dependencies/run_repo_dependency_review.sh",
        links: &[
            direct_link("documents/design/source-owned-dependency-validation.md"),
            direct_link("documents/design/dependency-manifest-design.md"),
            direct_link("agents/canonical/CODEX_WORKFLOW.md"),
            direct_link("templates/agents/closeout_gate.md"),
            direct_link("tools/analysis/dependencies/scan_dependency_headers.sh"),
            direct_link("tools/validation/semantic/dependencies/check_dependency_header_format.sh"),
            direct_link("tools/analysis/dependencies/check_dependency_graph.sh"),
            direct_link("tests/agent_tools/test_dependency_manifest_tools.py"),
        ],
        text_checks: &[],
        command_checks: &[],
    },
    ToolContract {
        name: "bootstrap_container_runtime",
        tool: "tools/runtime/container/bootstrap_runtime.py",
        links: &[
            direct_link("documents/design/agent-canon-bootstrap-tool-runtime.md"),
            direct_link("tools/runtime/source/agent_canon_source_root.py"),
            direct_link("bootstrap.sh"),
            direct_link("bootstrap/container/image/Dockerfile"),
            direct_link("tests/bootstrap/test_bootstrap_runtime.py"),
        ],
        text_checks: &[],
        command_checks: &[],
    },
];

#[derive(Debug)]
enum ToolDriftError {
    Graph(GraphClientError),
    Io(String),
}

static SHELL_COMMENT_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\s*#").expect("static shell comment regex"));
static SHELL_NOOP_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\s*:").expect("static shell no-op regex"));
static SHELL_ECHO_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\s*(echo|printf)\b").expect("static shell output regex"));
static SHELL_TRUE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\|\|\s*true\b").expect("static shell true guard regex"));
static SHELL_DISABLED_IF_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^\s*if\b.*\bfalse\b.*\bthen\b\s*$").expect("static disabled shell block regex")
});
static SHELL_FI_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\s*fi\b").expect("static shell block terminator regex"));
static SHELL_WHITESPACE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\s+").expect("static shell whitespace regex"));

#[derive(Clone, Copy)]
enum OutputFormat {
    Text,
    Json,
}

struct CliArgs {
    root: PathBuf,
    contracts: Vec<String>,
    format: OutputFormat,
    help: bool,
}

impl CliArgs {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut parsed = Self {
            root: PathBuf::from("."),
            contracts: Vec::new(),
            format: OutputFormat::Text,
            help: false,
        };
        let mut index = 0;
        while index < args.len() {
            let argument = &args[index];
            if matches!(argument.as_str(), "-h" | "--help") {
                parsed.help = true;
                return Ok(parsed);
            }
            let (name, inline) = argument
                .split_once('=')
                .map_or((argument.as_str(), None), |(name, value)| {
                    (name, Some(value))
                });
            let value = match inline {
                Some(value) if !value.is_empty() => Some(value.to_string()),
                Some(_) => return Err(format!("argument {name}: expected one argument")),
                None if matches!(name, "--root" | "--contract" | "--format") => {
                    let Some(value) = args.get(index + 1) else {
                        return Err(format!("argument {name}: expected one argument"));
                    };
                    if value.starts_with('-') {
                        return Err(format!("argument {name}: expected one argument"));
                    }
                    index += 1;
                    Some(value.clone())
                }
                None => None,
            };
            let Some(value) = value else {
                return Err(format!("unrecognized argument: {argument}"));
            };
            match name {
                "--root" => parsed.root = PathBuf::from(value),
                "--contract" => {
                    if !CONTRACTS.iter().any(|contract| contract.name == value) {
                        return Err(format!(
                            "invalid choice: '{value}' (choose from {})",
                            CONTRACTS
                                .iter()
                                .map(|contract| format!("'{}'", contract.name))
                                .collect::<Vec<_>>()
                                .join(", ")
                        ));
                    }
                    parsed.contracts.push(value);
                }
                "--format" => {
                    parsed.format = match value.as_str() {
                        "text" => OutputFormat::Text,
                        "json" => OutputFormat::Json,
                        _ => {
                            return Err(format!(
                                "invalid choice: '{value}' (choose from 'text', 'json')"
                            ))
                        }
                    }
                }
                _ => return Err(format!("unrecognized argument: {argument}")),
            }
            index += 1;
        }
        Ok(parsed)
    }
}

pub fn run(args: &[String]) -> i32 {
    let args = match CliArgs::parse(args) {
        Ok(args) => args,
        Err(error) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon tool-drift: error: {error}");
            return 2;
        }
    };
    if args.help {
        println!("{HELP}");
        return 0;
    }
    let root = args.root.canonicalize().unwrap_or(args.root);
    let selected = selected_contracts(&args.contracts);
    let findings = match run_checks(&root, &args.contracts) {
        Ok(findings) => findings,
        Err(ToolDriftError::Graph(error)) => vec![Finding::new(
            "graph-unavailable",
            "canonical_graph",
            ".",
            error.to_string(),
        )],
        Err(ToolDriftError::Io(error)) => {
            eprintln!("TOOL_CONVENTION_DRIFT=fail reason={error}");
            return 1;
        }
    };
    match args.format {
        OutputFormat::Json => println!("{}", render_json(&findings)),
        OutputFormat::Text => {
            for finding in &findings {
                println!("{}", finding.render());
            }
            println!("TOOL_CONVENTION_DRIFT_CONTRACTS={}", selected.len());
            println!("TOOL_CONVENTION_DRIFT_FINDINGS={}", findings.len());
            println!(
                "TOOL_CONVENTION_DRIFT={}",
                if findings.is_empty() { "pass" } else { "fail" }
            );
        }
    }
    if findings.is_empty() {
        0
    } else {
        1
    }
}

fn opposite_direction(direction: &str) -> &'static str {
    if direction == "upstream" {
        "downstream"
    } else {
        "upstream"
    }
}

fn compatible_reverse_kind(direct: &GraphDependencyFact, reverse: &GraphDependencyFact) -> bool {
    if direct.kind == reverse.kind {
        return true;
    }
    (direct.direction == "upstream"
        && direct.kind == "design"
        && reverse.direction == "downstream"
        && reverse.kind == "implementation")
        || (direct.direction == "downstream"
            && direct.kind == "implementation"
            && reverse.direction == "upstream"
            && reverse.kind == "design")
}

fn logical_graph_path(path: &str) -> String {
    let normalized = path.replace('\\', "/");
    let normalized = normalized.strip_prefix("./").unwrap_or(&normalized);
    if let Some(path) = normalized.strip_prefix("vendor/agent-canon/") {
        return path.to_string();
    }
    if let Some(path) = normalized.strip_prefix("tools/agent-canon/") {
        return format!("tools/{path}");
    }
    normalized.to_string()
}

fn matching_direct_edges<'a>(
    edges: &'a [GraphDependencyFact],
    tool: &str,
    target: &str,
) -> Vec<&'a GraphDependencyFact> {
    edges
        .iter()
        .filter(|edge| {
            logical_graph_path(&edge.source) == tool && logical_graph_path(&edge.target) == target
        })
        .collect()
}

fn matching_reverse_edges<'a>(
    edges: &'a [GraphDependencyFact],
    tool: &str,
    target: &str,
) -> Vec<&'a GraphDependencyFact> {
    edges
        .iter()
        .filter(|edge| {
            logical_graph_path(&edge.source) == target && logical_graph_path(&edge.target) == tool
        })
        .collect()
}

fn check_link(
    contract: &ToolContract,
    link: &LinkCheck,
    all_edges: &[GraphDependencyFact],
) -> Vec<Finding> {
    let direct = matching_direct_edges(all_edges, contract.tool, link.target);
    let reverse = matching_reverse_edges(all_edges, contract.tool, link.target);
    if direct.is_empty() && reverse.is_empty() {
        return vec![Finding::new(
            "missing-manifest-link",
            contract.name,
            contract.tool,
            link.target,
        )];
    }
    let mut findings = Vec::new();
    if link.direct_required && direct.is_empty() {
        findings.push(Finding::new(
            "missing-direct-manifest-link",
            contract.name,
            contract.tool,
            link.target,
        ));
    }
    if link.reverse_required && reverse.is_empty() {
        findings.push(Finding::new(
            "missing-reverse-manifest-link",
            contract.name,
            contract.tool,
            link.target,
        ));
    }
    for direct_edge in &direct {
        for reverse_edge in &reverse {
            if reverse_edge.direction != opposite_direction(&direct_edge.direction) {
                continue;
            }
            if !compatible_reverse_kind(direct_edge, reverse_edge) {
                findings.push(Finding::new(
                    "kind-mismatch",
                    contract.name,
                    contract.tool,
                    format!(
                        "{}:{} {} != {} {}",
                        link.target,
                        direct_edge.direction,
                        direct_edge.kind,
                        reverse_edge.direction,
                        reverse_edge.kind
                    ),
                ));
            }
        }
    }
    findings
}

fn resolve_repo_path(root: &Path, relative_path: &str) -> PathBuf {
    let root_path = root.join(relative_path);
    if root_path.exists() {
        return root_path;
    }
    if let Some(projected) = relative_path.strip_prefix("tools/") {
        let projected_path = root.join("tools/agent-canon").join(projected);
        if projected_path.exists() {
            return projected_path;
        }
    }
    tool_catalog::resolve_repo_path(root, relative_path, None)
}

fn check_text(
    root: &Path,
    contract: &ToolContract,
    text_check: &TextCheck,
) -> Result<Vec<Finding>, ToolDriftError> {
    let path = resolve_repo_path(root, text_check.path);
    if !path.is_file() {
        return Ok(vec![Finding::new(
            "missing-file",
            contract.name,
            text_check.path,
            text_check.detail,
        )]);
    }
    let text = fs::read_to_string(&path)
        .map_err(|error| ToolDriftError::Io(format!("{}: {error}", path.display())))?;
    let projected = projected_runtime_snippet(root, text_check.snippet);
    if text.contains(text_check.snippet) || text.contains(&projected) {
        return Ok(Vec::new());
    }
    Ok(vec![Finding::new(
        "missing-required-text",
        contract.name,
        text_check.path,
        text_check.detail,
    )])
}

fn collect_shell_executable_commands(path: &Path) -> Result<Vec<String>, ToolDriftError> {
    let text = fs::read_to_string(path)
        .map_err(|error| ToolDriftError::Io(format!("{}: {error}", path.display())))?;
    let mut continuation_lines = Vec::new();
    let mut current = String::new();
    for raw_line in text.lines() {
        if let Some(line) = raw_line.strip_suffix('\\') {
            if !current.is_empty() {
                current.push(' ');
            }
            current.push_str(line);
            continue;
        }
        let mut full_line = String::new();
        if !current.is_empty() {
            full_line.push_str(&current);
            full_line.push(' ');
        }
        full_line.push_str(raw_line);
        current.clear();
        continuation_lines.push(full_line);
    }
    if !current.is_empty() {
        continuation_lines.push(current);
    }

    let mut commands = Vec::new();
    let mut disabled_depth = 0usize;
    for raw_line in continuation_lines {
        let line = raw_line.trim();
        if line.is_empty()
            || SHELL_COMMENT_RE.is_match(line)
            || SHELL_NOOP_RE.is_match(line)
            || SHELL_ECHO_RE.is_match(line)
            || SHELL_TRUE_RE.is_match(line)
        {
            continue;
        }
        if SHELL_DISABLED_IF_RE.is_match(line) {
            disabled_depth += 1;
            continue;
        }
        if SHELL_FI_RE.is_match(line) {
            disabled_depth = disabled_depth.saturating_sub(1);
            continue;
        }
        if disabled_depth > 0 {
            continue;
        }
        let line = line
            .split_once(" #")
            .map_or(line, |(before_comment, _)| before_comment)
            .trim_end();
        if line.is_empty() {
            continue;
        }
        commands.push(SHELL_WHITESPACE_RE.replace_all(line, " ").into_owned());
    }
    Ok(commands)
}

fn check_command(
    root: &Path,
    contract: &ToolContract,
    command_check: &CommandCheck,
) -> Result<Vec<Finding>, ToolDriftError> {
    let path = resolve_repo_path(root, command_check.path);
    if !path.is_file() {
        return Ok(vec![Finding::new(
            "missing-file",
            contract.name,
            command_check.path,
            command_check.detail,
        )]);
    }
    let commands = collect_shell_executable_commands(&path)?;
    let pattern = Regex::new(command_check.pattern)
        .map_err(|error| ToolDriftError::Io(format!("invalid command regex: {error}")))?;
    let hits = commands
        .iter()
        .filter(|command| pattern.is_match(command))
        .count();
    if hits == 0 {
        return Ok(vec![Finding::new(
            "missing-required-command",
            contract.name,
            command_check.path,
            command_check.detail,
        )]);
    }
    if hits != command_check.required_count {
        return Ok(vec![Finding::new(
            "duplicate-required-command",
            contract.name,
            command_check.path,
            format!(
                "{}:actual={hits}:expected={}",
                command_check.detail, command_check.required_count
            ),
        )]);
    }
    Ok(Vec::new())
}

fn projected_runtime_snippet(root: &Path, snippet: &str) -> String {
    if !root.join("tools/agent-canon").exists() || root.join("tools/agent").exists() {
        return snippet.to_string();
    }
    snippet
        .replace("tools/agent/", "tools/agent-canon/agent/")
        .replace("tools/validation/", "tools/agent-canon/validation/")
}

fn yaml_mapping_value<'a>(mapping: &'a [(&str, &'a Yaml)], key: &str) -> Option<&'a Yaml> {
    mapping
        .iter()
        .find_map(|(candidate, value)| (*candidate == key).then_some(*value))
}

fn check_catalog_entries(root: &Path) -> Result<Vec<Finding>, ToolDriftError> {
    let catalog_path = resolve_repo_path(root, tool_catalog::CATALOG_PATH);
    if !catalog_path.is_file() {
        return Ok(vec![Finding::new(
            "missing-file",
            "tool_catalog",
            tool_catalog::CATALOG_PATH,
            "catalog",
        )]);
    }
    let catalog_text = fs::read_to_string(&catalog_path)
        .map_err(|error| ToolDriftError::Io(format!("{}: {error}", catalog_path.display())))?;
    let documents = YamlLoader::load_from_str(&catalog_text)
        .map_err(|error| ToolDriftError::Io(format!("{}: {error}", catalog_path.display())))?;
    if documents.len() > 1 {
        return Err(ToolDriftError::Io(format!(
            "{}: expected a single YAML document",
            catalog_path.display()
        )));
    }
    let Some(document) = documents.first() else {
        return Ok(vec![Finding::new(
            "invalid-catalog",
            "tool_catalog",
            tool_catalog::CATALOG_PATH,
            "not-mapping",
        )]);
    };
    let Some(catalog) = tool_catalog::as_mapping(document) else {
        return Ok(vec![Finding::new(
            "invalid-catalog",
            "tool_catalog",
            tool_catalog::CATALOG_PATH,
            "not-mapping",
        )]);
    };
    let Some(entries) = yaml_mapping_value(&catalog, "entries").and_then(tool_catalog::as_sequence)
    else {
        return Ok(vec![Finding::new(
            "invalid-catalog",
            "tool_catalog",
            tool_catalog::CATALOG_PATH,
            "entries-not-list",
        )]);
    };
    let mut findings = Vec::new();
    let mut catalog_retired_paths = BTreeSet::new();
    for (index, raw_entry) in entries.iter().enumerate() {
        let Some(entry) = tool_catalog::as_mapping(raw_entry) else {
            findings.push(Finding::new(
                "invalid-catalog-entry",
                "tool_catalog",
                tool_catalog::CATALOG_PATH,
                format!("entry-{}-not-mapping", index + 1),
            ));
            continue;
        };
        let Some(entry_path) = yaml_mapping_value(&entry, "path").and_then(Yaml::as_str) else {
            findings.push(Finding::new(
                "invalid-catalog-entry",
                "tool_catalog",
                tool_catalog::CATALOG_PATH,
                format!("entry-{}-missing-path", index + 1),
            ));
            continue;
        };
        let status = yaml_mapping_value(&entry, "status").and_then(Yaml::as_str);
        if !resolve_repo_path(root, entry_path).exists() {
            findings.push(Finding::new(
                "stale-catalog-entry",
                "tool_catalog",
                entry_path,
                "missing-path",
            ));
        }
        if path_policy::is_retired_legacy_tool_path(entry_path)
            || status == Some("legacy_provenance")
        {
            let normalized = entry_path.replace('\\', "/");
            catalog_retired_paths.insert(
                normalized
                    .strip_prefix("./")
                    .unwrap_or(&normalized)
                    .to_string(),
            );
            findings.push(Finding::new(
                "retired-legacy-tool",
                "tool_catalog",
                entry_path,
                "legacy-tools-are-retired",
            ));
        }
    }
    for retired_path in path_policy::iter_retired_legacy_tool_paths(root) {
        if catalog_retired_paths.contains(&retired_path) {
            continue;
        }
        findings.push(Finding::new(
            "retired-legacy-tool",
            "tool_catalog",
            &retired_path,
            path_policy::retired_legacy_tool_detail(&retired_path),
        ));
    }
    Ok(findings)
}

fn selected_contracts(names: &[String]) -> Vec<&'static ToolContract> {
    if names.is_empty() {
        return CONTRACTS.iter().collect();
    }
    CONTRACTS
        .iter()
        .filter(|contract| names.iter().any(|name| name.as_str() == contract.name))
        .collect()
}

fn run_checks(root: &Path, names: &[String]) -> Result<Vec<Finding>, ToolDriftError> {
    let contracts = selected_contracts(names);
    let graph = GraphClient::new(root).map_err(ToolDriftError::Graph)?;
    let response = graph
        .query(None, "dependency", "both", 0, true)
        .map_err(ToolDriftError::Graph)?;
    if response.status != "fresh" || response.exit_code != 0 {
        let reason = response
            .payload
            .get("reason")
            .map(|reason| match reason {
                Value::Null => "None".to_string(),
                Value::String(reason) => reason.clone(),
                value => value.to_string(),
            })
            .unwrap_or_else(|| "None".to_string());
        return Err(ToolDriftError::Graph(GraphClientError {
            message: format!(
                "canonical graph dependency query is unavailable: status={} reason={reason}",
                response.status
            ),
        }));
    }
    let all_edges = response.dependency_facts().map_err(ToolDriftError::Graph)?;
    let mut findings = Vec::new();
    for contract in contracts {
        if !resolve_repo_path(root, contract.tool).is_file() {
            findings.push(Finding::new(
                "missing-tool",
                contract.name,
                contract.tool,
                "missing-file",
            ));
            continue;
        }
        for link in contract.links {
            if !resolve_repo_path(root, link.target).is_file() {
                findings.push(Finding::new(
                    "missing-file",
                    contract.name,
                    link.target,
                    "link-target",
                ));
                continue;
            }
            findings.extend(check_link(contract, link, &all_edges));
        }
        for text_check in contract.text_checks {
            findings.extend(check_text(root, contract, text_check)?);
        }
        for command_check in contract.command_checks {
            findings.extend(check_command(root, contract, command_check)?);
        }
        if contract.name == "tool_catalog" {
            findings.extend(check_catalog_entries(root)?);
        }
    }
    findings.sort_by(|left, right| {
        (&left.kind, &left.contract, &left.path, &left.detail).cmp(&(
            &right.kind,
            &right.contract,
            &right.path,
            &right.detail,
        ))
    });
    Ok(findings)
}

fn render_json(findings: &[Finding]) -> String {
    let status = if findings.is_empty() { "pass" } else { "fail" };
    serde_json::to_string_pretty(&json!({
        "status": status,
        "findings": findings,
        "contracts": CONTRACTS.len()
    }))
    .unwrap_or_else(|_| "{}".to_string())
}
