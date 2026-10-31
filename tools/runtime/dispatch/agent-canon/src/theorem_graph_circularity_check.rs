// @dependency-start
// contract tool
// responsibility Checks proposition-graph circularity, leaf origins, and forbidden reachability for theorem routes.
// upstream design ../../../../../agents/skills/formal-proof-workflow.md requires graph-based circularity checks.
// upstream design ../../../../../agents/skills/algorithm-proof-exploration.md separates projection evidence from convergence evidence.
// downstream test ../../../../../tests/agent_tools/test_theorem_graph_circularity_check.py preserves independent graph oracles.
// @dependency-end

//! Theorem graph circularity, terminal-leaf, and forbidden-reachability checks.

use serde::Serialize;
use serde_json::{Map, Value};
use std::collections::{HashMap, HashSet, VecDeque};
use std::fs;
use std::path::{Path, PathBuf};

pub const SELECTOR: &str = "theorem-graph-circularity-check";

#[derive(Clone, Debug, Serialize)]
pub struct CircularityFinding {
    pub check_id: String,
    pub start: String,
    pub reached: String,
    pub reached_kind: String,
    pub path: Vec<String>,
    pub edge_kinds: Vec<String>,
    pub severity: String,
    pub explanation: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct LeafOriginFinding {
    pub check_id: String,
    pub leaf: String,
    pub leaf_kind: String,
    pub leaf_status: String,
    pub leaf_origin: String,
    pub path: Vec<String>,
    pub severity: String,
    pub explanation: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct ReachabilityFinding {
    pub check_id: String,
    pub start: String,
    pub reached: String,
    pub reached_kind: String,
    pub reached_status: String,
    pub reached_origin: String,
    pub path: Vec<String>,
    pub edge_kinds: Vec<String>,
    pub severity: String,
    pub explanation: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct TheoremGraphReport {
    pub status: String,
    pub check_count: usize,
    pub passed_checks: Vec<String>,
    pub findings: Vec<CircularityFinding>,
    pub directed_cycles: Vec<Vec<String>>,
    pub leaf_origin_check_count: usize,
    pub leaf_origin_passed_checks: Vec<String>,
    pub leaf_origin_findings: Vec<LeafOriginFinding>,
    pub forbidden_reachability_check_count: usize,
    pub forbidden_reachability_passed_checks: Vec<String>,
    pub forbidden_reachability_findings: Vec<ReachabilityFinding>,
}

#[derive(Clone, Debug)]
struct Edge {
    source: String,
    target: String,
    kind: String,
    status: String,
}

#[derive(Clone, Debug, Default)]
struct GraphIndex {
    nodes: HashMap<String, Map<String, Value>>,
    node_order: Vec<String>,
    outgoing: HashMap<String, Vec<Edge>>,
}

type PathFinding = (String, Vec<String>, Vec<String>);

pub fn check_theorem_graph(graph: &Value) -> Result<TheoremGraphReport, String> {
    let object = graph
        .as_object()
        .ok_or_else(|| "graph must be a JSON object".to_string())?;
    let (findings, passed_checks, cycles) = check_circularity(object);
    let (leaf_findings, leaf_passed_checks) = check_leaf_origins(object);
    let (reachability_findings, reachability_passed_checks) = check_forbidden_reachability(object);
    let reachability_check_ids: HashSet<_> = reachability_findings
        .iter()
        .map(|finding| finding.check_id.as_str())
        .collect();
    let has_findings =
        !findings.is_empty() || !leaf_findings.is_empty() || !reachability_findings.is_empty();
    Ok(TheoremGraphReport {
        status: if has_findings { "found" } else { "pass" }.into(),
        check_count: findings.len() + passed_checks.len(),
        passed_checks,
        findings,
        directed_cycles: cycles,
        leaf_origin_check_count: leaf_findings.len() + leaf_passed_checks.len(),
        leaf_origin_passed_checks: leaf_passed_checks,
        leaf_origin_findings: leaf_findings,
        forbidden_reachability_check_count: reachability_check_ids.len()
            + reachability_passed_checks.len(),
        forbidden_reachability_passed_checks: reachability_passed_checks,
        forbidden_reachability_findings: reachability_findings,
    })
}

fn rows(value: Option<&Value>) -> Vec<&Map<String, Value>> {
    value
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_object)
        .collect()
}

fn string_set(value: Option<&Value>) -> HashSet<String> {
    value
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .map(python_string)
        .collect()
}

fn python_string(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::Number(number) => number.to_string(),
        Value::Array(items) => format!(
            "[{}]",
            items.iter().map(python_repr).collect::<Vec<_>>().join(", ")
        ),
        Value::Object(items) => format!(
            "{{{}}}",
            items
                .iter()
                .map(|(key, value)| format!("'{}': {}", key, python_repr(value)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

fn python_repr(value: &Value) -> String {
    match value {
        Value::String(text) => format!("'{}'", text.replace('\\', "\\\\").replace('\'', "\\'")),
        _ => python_string(value),
    }
}

fn field(object: &Map<String, Value>, name: &str, default: &str) -> String {
    object
        .get(name)
        .map(python_string)
        .unwrap_or_else(|| default.into())
}

fn graph_indexes(graph: &Map<String, Value>) -> GraphIndex {
    let mut index = GraphIndex::default();
    for node in rows(graph.get("nodes")) {
        let Some(id) = node.get("id") else { continue };
        let id = python_string(id);
        index.node_order.push(id.clone());
        index.nodes.insert(id, node.clone());
    }
    for edge in rows(graph.get("edges")) {
        let (Some(source), Some(target)) = (edge.get("source"), edge.get("target")) else {
            continue;
        };
        let record = Edge {
            source: python_string(source),
            target: python_string(target),
            kind: field(edge, "kind", ""),
            status: field(edge, "status", ""),
        };
        if is_active_proof_edge(&record) {
            index
                .outgoing
                .entry(record.source.clone())
                .or_default()
                .push(record);
        }
    }
    index
}

fn is_active_proof_edge(edge: &Edge) -> bool {
    !edge.kind.starts_with("diagnostic_")
        && !["not_required", "diagnostic", "projection_only", "rejected"]
            .iter()
            .any(|term| edge.status.contains(*term))
}

fn node_string(nodes: &HashMap<String, Map<String, Value>>, node_id: &str, key: &str) -> String {
    nodes
        .get(node_id)
        .map(|node| field(node, key, ""))
        .unwrap_or_default()
}

fn reachable_path(
    start: &str,
    index: &GraphIndex,
    allowed_edge_kinds: &HashSet<String>,
    forbidden_node_kinds: &HashSet<String>,
) -> Option<PathFinding> {
    let mut queue = VecDeque::from([(
        start.to_string(),
        vec![start.to_string()],
        Vec::<String>::new(),
    )]);
    let mut seen = HashSet::from([start.to_string()]);
    while let Some((node_id, path, edge_kinds)) = queue.pop_front() {
        if node_id != start
            && forbidden_node_kinds.contains(&node_string(&index.nodes, &node_id, "kind"))
        {
            return Some((node_id, path, edge_kinds));
        }
        if let Some(edges) = index.outgoing.get(&node_id) {
            for edge in edges {
                if !allowed_edge_kinds.contains(&edge.kind) || !seen.insert(edge.target.clone()) {
                    continue;
                }
                let mut next_path = path.clone();
                next_path.push(edge.target.clone());
                let mut next_kinds = edge_kinds.clone();
                next_kinds.push(edge.kind.clone());
                queue.push_back((edge.target.clone(), next_path, next_kinds));
            }
        }
    }
    None
}

fn detect_directed_cycles(index: &GraphIndex) -> Vec<Vec<String>> {
    fn canonical(cycle: &[String]) -> Vec<String> {
        let body = &cycle[..cycle.len() - 1];
        let mut best: Option<Vec<String>> = None;
        for offset in 0..body.len() {
            let mut rotation = body[offset..].to_vec();
            rotation.extend_from_slice(&body[..offset]);
            let is_smallest = match best.as_ref() {
                Some(current) => rotation.as_slice() < current.as_slice(),
                None => true,
            };
            if is_smallest {
                best = Some(rotation);
            }
        }
        let mut result = best.unwrap_or_default();
        if let Some(first) = result.first().cloned() {
            result.push(first);
        }
        result
    }

    fn edge_kinds(index: &GraphIndex, cycle: &[String]) -> Vec<String> {
        cycle
            .windows(2)
            .map(|pair| {
                index
                    .outgoing
                    .get(&pair[0])
                    .and_then(|edges| edges.iter().find(|edge| edge.target == pair[1]))
                    .map(|edge| edge.kind.clone())
                    .unwrap_or_default()
            })
            .collect()
    }

    fn visit(
        node: &str,
        index: &GraphIndex,
        visiting: &mut Vec<String>,
        visited: &mut HashSet<String>,
        cycles: &mut HashSet<Vec<String>>,
    ) {
        if let Some(position) = visiting.iter().position(|item| item == node) {
            let mut cycle = visiting[position..].to_vec();
            cycle.push(node.to_string());
            let normalized = canonical(&cycle);
            let kinds = edge_kinds(index, &normalized);
            if !kinds.is_empty() && kinds.iter().all(|kind| kind == "equivalent_to") {
                return;
            }
            cycles.insert(normalized);
            return;
        }
        if visited.contains(node) {
            return;
        }
        visiting.push(node.to_string());
        if let Some(edges) = index.outgoing.get(node) {
            for edge in edges {
                visit(&edge.target, index, visiting, visited, cycles);
            }
        }
        visiting.pop();
        visited.insert(node.to_string());
    }

    let mut cycles = HashSet::new();
    let mut visiting = vec![];
    let mut visited = HashSet::new();
    for node in &index.node_order {
        visit(node, index, &mut visiting, &mut visited, &mut cycles);
    }
    let mut cycles: Vec<_> = cycles.into_iter().collect();
    cycles.sort();
    cycles
}

fn node_passes_leaf_origin_check(
    node: Option<&Map<String, Value>>,
    allowed_node_kinds: &HashSet<String>,
    allowed_origins: &HashSet<String>,
    allowed_origin_terms: &HashSet<String>,
    allowed_statuses: &HashSet<String>,
    allowed_status_prefixes: &HashSet<String>,
    forbidden_status_terms: &HashSet<String>,
) -> bool {
    let kind = node.map(|node| field(node, "kind", "")).unwrap_or_default();
    let status = node
        .map(|node| field(node, "status", ""))
        .unwrap_or_default();
    let origin = node
        .map(|node| field(node, "origin", ""))
        .unwrap_or_default();
    if forbidden_status_terms
        .iter()
        .any(|term| !term.is_empty() && status.contains(term.as_str()))
    {
        return false;
    }
    allowed_node_kinds.contains(&kind)
        || allowed_origins.contains(&origin)
        || allowed_origin_terms
            .iter()
            .any(|term| !term.is_empty() && origin.contains(term.as_str()))
        || allowed_statuses.contains(&status)
        || allowed_status_prefixes
            .iter()
            .any(|prefix| !prefix.is_empty() && status.starts_with(prefix.as_str()))
}

fn leaf_paths(
    start: &str,
    index: &GraphIndex,
    allowed_edge_kinds: &HashSet<String>,
) -> Vec<(String, Vec<String>)> {
    let mut leaves = vec![];
    let mut queue = VecDeque::from([(start.to_string(), vec![start.to_string()])]);
    let mut seen_edges = HashSet::new();
    while let Some((node_id, path)) = queue.pop_front() {
        let next_edges: Vec<_> = index
            .outgoing
            .get(&node_id)
            .into_iter()
            .flatten()
            .filter(|edge| allowed_edge_kinds.contains(&edge.kind))
            .collect();
        if next_edges.is_empty() {
            leaves.push((node_id, path));
            continue;
        }
        for edge in next_edges {
            let key = (node_id.clone(), edge.kind.clone(), edge.target.clone());
            if !seen_edges.insert(key) {
                continue;
            }
            let mut next_path = path.clone();
            next_path.push(edge.target.clone());
            if path.contains(&edge.target) {
                leaves.push((edge.target.clone(), next_path));
                continue;
            }
            queue.push_back((edge.target.clone(), next_path));
        }
    }
    leaves
}

struct ForbiddenReachabilityPolicy<'a> {
    allowed_edge_kinds: &'a HashSet<String>,
    forbidden_node_kinds: &'a HashSet<String>,
    forbidden_status_terms: &'a HashSet<String>,
    allowed_node_kinds: &'a HashSet<String>,
    allowed_statuses: &'a HashSet<String>,
    allowed_status_prefixes: &'a HashSet<String>,
}

fn node_is_forbidden_reachable(
    node: Option<&Map<String, Value>>,
    policy: &ForbiddenReachabilityPolicy<'_>,
) -> bool {
    let kind = node.map(|node| field(node, "kind", "")).unwrap_or_default();
    let status = node
        .map(|node| field(node, "status", ""))
        .unwrap_or_default();
    if policy.allowed_node_kinds.contains(&kind)
        || policy.allowed_statuses.contains(&status)
        || policy
            .allowed_status_prefixes
            .iter()
            .any(|prefix| !prefix.is_empty() && status.starts_with(prefix.as_str()))
    {
        return false;
    }
    policy.forbidden_node_kinds.contains(&kind)
        || policy
            .forbidden_status_terms
            .iter()
            .any(|term| !term.is_empty() && status.contains(term.as_str()))
}

fn forbidden_reachable_nodes(
    start: &str,
    index: &GraphIndex,
    policy: &ForbiddenReachabilityPolicy<'_>,
) -> Vec<PathFinding> {
    let mut findings = vec![];
    let mut queue = VecDeque::from([(
        start.to_string(),
        vec![start.to_string()],
        Vec::<String>::new(),
    )]);
    let mut seen_edges = HashSet::new();
    while let Some((node_id, path, edge_kinds)) = queue.pop_front() {
        if node_id != start && node_is_forbidden_reachable(index.nodes.get(&node_id), policy) {
            findings.push((node_id.clone(), path.clone(), edge_kinds.clone()));
        }
        if let Some(edges) = index.outgoing.get(&node_id) {
            for edge in edges {
                if !policy.allowed_edge_kinds.contains(&edge.kind)
                    || !seen_edges.insert((node_id.clone(), edge.kind.clone(), edge.target.clone()))
                    || path.contains(&edge.target)
                {
                    continue;
                }
                let mut next_path = path.clone();
                next_path.push(edge.target.clone());
                let mut next_kinds = edge_kinds.clone();
                next_kinds.push(edge.kind.clone());
                queue.push_back((edge.target.clone(), next_path, next_kinds));
            }
        }
    }
    findings
}

fn check_circularity(
    graph: &Map<String, Value>,
) -> (Vec<CircularityFinding>, Vec<String>, Vec<Vec<String>>) {
    let index = graph_indexes(graph);
    let mut findings = vec![];
    let mut passed = vec![];
    for check in rows(graph.get("circularity_checks")) {
        let check_id = field(check, "id", "unnamed_check");
        let start = field(check, "start", "");
        if start.is_empty() {
            continue;
        }
        let allowed_edges = string_set(check.get("via_edge_kinds"));
        let forbidden_kinds = string_set(check.get("forbidden_reachable_kinds"));
        if allowed_edges.is_empty() || forbidden_kinds.is_empty() {
            continue;
        }
        let Some((reached, path, edge_kinds)) =
            reachable_path(&start, &index, &allowed_edges, &forbidden_kinds)
        else {
            passed.push(check_id);
            continue;
        };
        findings.push(CircularityFinding {
            check_id,
            start,
            reached_kind: node_string(&index.nodes, &reached, "kind"),
            reached,
            path,
            edge_kinds,
            severity: field(check, "severity", "circularity_check"),
            explanation: field(check, "explanation", ""),
        });
    }
    (findings, passed, detect_directed_cycles(&index))
}

fn check_leaf_origins(graph: &Map<String, Value>) -> (Vec<LeafOriginFinding>, Vec<String>) {
    let index = graph_indexes(graph);
    let mut findings = vec![];
    let mut passed = vec![];
    for check in rows(graph.get("leaf_origin_checks")) {
        let check_id = field(check, "id", "unnamed_leaf_origin_check");
        let start = field(check, "start", "");
        if start.is_empty() {
            continue;
        }
        let allowed_edges = string_set(check.get("via_edge_kinds"));
        if allowed_edges.is_empty() {
            continue;
        }
        let allowed_kinds = string_set(check.get("allowed_node_kinds"));
        let allowed_origins = string_set(check.get("allowed_origins"));
        let allowed_origin_terms = string_set(check.get("allowed_origin_terms"));
        let allowed_statuses = string_set(check.get("allowed_statuses"));
        let allowed_prefixes = string_set(check.get("allowed_status_prefixes"));
        let forbidden_terms = string_set(check.get("forbidden_status_terms"));
        let mut check_findings = vec![];
        for (leaf, path) in leaf_paths(&start, &index, &allowed_edges) {
            let node = index.nodes.get(&leaf);
            if node_passes_leaf_origin_check(
                node,
                &allowed_kinds,
                &allowed_origins,
                &allowed_origin_terms,
                &allowed_statuses,
                &allowed_prefixes,
                &forbidden_terms,
            ) {
                continue;
            }
            check_findings.push(LeafOriginFinding {
                check_id: check_id.clone(),
                leaf_kind: node.map(|node| field(node, "kind", "")).unwrap_or_default(),
                leaf_status: node
                    .map(|node| field(node, "status", ""))
                    .unwrap_or_default(),
                leaf_origin: node
                    .map(|node| field(node, "origin", ""))
                    .unwrap_or_default(),
                leaf,
                path,
                severity: field(check, "severity", "leaf_origin_check"),
                explanation: field(check, "explanation", ""),
            });
        }
        if check_findings.is_empty() {
            passed.push(check_id);
        } else {
            findings.extend(check_findings);
        }
    }
    (findings, passed)
}

fn check_forbidden_reachability(
    graph: &Map<String, Value>,
) -> (Vec<ReachabilityFinding>, Vec<String>) {
    let index = graph_indexes(graph);
    let mut findings = vec![];
    let mut passed = vec![];
    for check in rows(graph.get("forbidden_reachability_checks")) {
        let check_id = field(check, "id", "unnamed_forbidden_reachability_check");
        let start = field(check, "start", "");
        if start.is_empty() {
            continue;
        }
        let allowed_edges = string_set(check.get("via_edge_kinds"));
        if allowed_edges.is_empty() {
            continue;
        }
        let forbidden_node_kinds = string_set(check.get("forbidden_node_kinds"));
        let forbidden_status_terms = string_set(check.get("forbidden_status_terms"));
        let allowed_node_kinds = string_set(check.get("allowed_node_kinds"));
        let allowed_statuses = string_set(check.get("allowed_statuses"));
        let allowed_status_prefixes = string_set(check.get("allowed_status_prefixes"));
        let policy = ForbiddenReachabilityPolicy {
            allowed_edge_kinds: &allowed_edges,
            forbidden_node_kinds: &forbidden_node_kinds,
            forbidden_status_terms: &forbidden_status_terms,
            allowed_node_kinds: &allowed_node_kinds,
            allowed_statuses: &allowed_statuses,
            allowed_status_prefixes: &allowed_status_prefixes,
        };
        let check_findings: Vec<_> = forbidden_reachable_nodes(&start, &index, &policy)
            .into_iter()
            .map(|(reached, path, edge_kinds)| {
                let node = index.nodes.get(&reached);
                ReachabilityFinding {
                    check_id: check_id.clone(),
                    start: start.clone(),
                    reached_kind: node.map(|node| field(node, "kind", "")).unwrap_or_default(),
                    reached_status: node
                        .map(|node| field(node, "status", ""))
                        .unwrap_or_default(),
                    reached_origin: node
                        .map(|node| field(node, "origin", ""))
                        .unwrap_or_default(),
                    reached,
                    path,
                    edge_kinds,
                    severity: field(check, "severity", "forbidden_reachability"),
                    explanation: field(check, "explanation", ""),
                }
            })
            .collect();
        if check_findings.is_empty() {
            passed.push(check_id);
        } else {
            findings.extend(check_findings);
        }
    }
    (findings, passed)
}

pub fn render_text(report: &TheoremGraphReport) -> String {
    let status = if report.status == "found" {
        "found"
    } else {
        "pass"
    };
    let reach_ids: HashSet<_> = report
        .forbidden_reachability_findings
        .iter()
        .map(|f| f.check_id.as_str())
        .collect();
    let reach_count = reach_ids.len() + report.forbidden_reachability_passed_checks.len();
    let mut lines = vec![
        format!("THEOREM_GRAPH_CIRCULARITY={status}"),
        format!("THEOREM_GRAPH_CIRCULARITY_CHECKS={}", report.check_count),
        format!(
            "THEOREM_GRAPH_CIRCULARITY_FINDINGS={}",
            report.findings.len()
        ),
        format!(
            "THEOREM_GRAPH_CIRCULARITY_PASSED={}",
            report.passed_checks.len()
        ),
        format!(
            "THEOREM_GRAPH_DIRECTED_CYCLES={}",
            report.directed_cycles.len()
        ),
        format!(
            "THEOREM_GRAPH_LEAF_ORIGIN_CHECKS={}",
            report.leaf_origin_check_count
        ),
        format!(
            "THEOREM_GRAPH_LEAF_ORIGIN_FINDINGS={}",
            report.leaf_origin_findings.len()
        ),
        format!(
            "THEOREM_GRAPH_LEAF_ORIGIN_PASSED={}",
            report.leaf_origin_passed_checks.len()
        ),
        format!("THEOREM_GRAPH_FORBIDDEN_REACHABILITY_CHECKS={reach_count}"),
        format!(
            "THEOREM_GRAPH_FORBIDDEN_REACHABILITY_FINDINGS={}",
            report.forbidden_reachability_findings.len()
        ),
        format!(
            "THEOREM_GRAPH_FORBIDDEN_REACHABILITY_PASSED={}",
            report.forbidden_reachability_passed_checks.len()
        ),
    ];
    for finding in &report.findings {
        lines.push(format!(
            "THEOREM_GRAPH_CIRCULARITY_FINDING={}:start={}:reached={}:path={}",
            finding.check_id,
            finding.start,
            finding.reached,
            finding.path.join("->")
        ));
    }
    for check in &report.passed_checks {
        lines.push(format!("THEOREM_GRAPH_CIRCULARITY_PASS={check}"));
    }
    for finding in &report.leaf_origin_findings {
        lines.push(format!(
            "THEOREM_GRAPH_LEAF_ORIGIN_FINDING={}:leaf={}:status={}:origin={}:path={}",
            finding.check_id,
            finding.leaf,
            finding.leaf_status,
            finding.leaf_origin,
            finding.path.join("->")
        ));
    }
    for check in &report.leaf_origin_passed_checks {
        lines.push(format!("THEOREM_GRAPH_LEAF_ORIGIN_PASS={check}"));
    }
    for finding in &report.forbidden_reachability_findings {
        lines.push(format!("THEOREM_GRAPH_FORBIDDEN_REACHABILITY_FINDING={}:reached={}:status={}:origin={}:path={}", finding.check_id, finding.reached, finding.reached_status, finding.reached_origin, finding.path.join("->")));
    }
    for check in &report.forbidden_reachability_passed_checks {
        lines.push(format!("THEOREM_GRAPH_FORBIDDEN_REACHABILITY_PASS={check}"));
    }
    lines.join("\n") + "\n"
}

fn dependency_path_from_output(output: Option<&Path>) -> String {
    let source =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src/theorem_graph_circularity_check.rs");
    let Some(output) = output else {
        return source.to_string_lossy().into_owned();
    };
    let parent = output.parent().unwrap_or_else(|| Path::new("."));
    let parent = if parent.is_absolute() {
        parent.to_path_buf()
    } else {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(parent)
    };
    pathdiff::diff_paths(&source, parent)
        .unwrap_or(source)
        .to_string_lossy()
        .into_owned()
}

pub fn render_markdown(report: &TheoremGraphReport, dependency_path: &str) -> String {
    let reach_ids: HashSet<_> = report
        .forbidden_reachability_findings
        .iter()
        .map(|f| f.check_id.as_str())
        .collect();
    let reach_count = reach_ids.len() + report.forbidden_reachability_passed_checks.len();
    let mut lines = vec![
        "<!--".into(),
        "@dependency-start".into(),
        "responsibility Records theorem-graph circularity, leaf-origin, and forbidden-reachability checks.".into(),
        format!("upstream implementation {dependency_path} generates this report from a theorem graph JSON."),
        "downstream design check_finite_stop_goal.py consumes circularity and reachability counts.".into(),
        "@dependency-end".into(),
        "-->".into(),
        "".into(),
        "# Theorem Graph Circularity Check".into(),
        "".into(),
        format!("- checks: `{}`", report.check_count),
        format!("- findings: `{}`", report.findings.len()),
        format!("- passed: `{}`", report.passed_checks.len()),
        format!("- directed cycles: `{}`", report.directed_cycles.len()),
        format!("- leaf-origin checks: `{}`", report.leaf_origin_check_count),
        format!("- leaf-origin findings: `{}`", report.leaf_origin_findings.len()),
        format!("- forbidden-reachability checks: `{reach_count}`"),
        format!("- forbidden-reachability findings: `{}`", report.forbidden_reachability_findings.len()),
        "".into(),
        "| Check | Severity | Start | Reached | Path | Edge Kinds | Explanation |".into(),
        "| --- | --- | --- | --- | --- | --- | --- |".into(),
    ];
    for finding in &report.findings {
        lines.push(format!(
            "| `{}` | `{}` | `{}` | `{}` (`{}`) | `{}` | `{}` | {} |",
            finding.check_id,
            finding.severity,
            finding.start,
            finding.reached,
            finding.reached_kind,
            finding.path.join(" -> "),
            finding.edge_kinds.join(" -> "),
            if finding.explanation.is_empty() {
                "None"
            } else {
                &finding.explanation
            }
        ));
    }
    if !report.passed_checks.is_empty() {
        lines.extend(["".into(), "## Passed Checks".into(), "".into()]);
        lines.extend(report.passed_checks.iter().map(|id| format!("- `{id}`")));
    }
    if !report.directed_cycles.is_empty() {
        lines.extend(["".into(), "## Directed Cycles".into(), "".into()]);
        lines.extend(
            report
                .directed_cycles
                .iter()
                .map(|cycle| format!("- `{}`", cycle.join(" -> "))),
        );
    }
    if !report.leaf_origin_findings.is_empty() {
        lines.extend([
            "".into(),
            "## Leaf-Origin Findings".into(),
            "".into(),
            "| Check | Severity | Leaf | Kind | Status | Origin | Path | Explanation |".into(),
            "| --- | --- | --- | --- | --- | --- | --- | --- |".into(),
        ]);
        for finding in &report.leaf_origin_findings {
            lines.push(format!(
                "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | {} |",
                finding.check_id,
                finding.severity,
                finding.leaf,
                finding.leaf_kind,
                finding.leaf_status,
                finding.leaf_origin,
                finding.path.join(" -> "),
                if finding.explanation.is_empty() {
                    "None"
                } else {
                    &finding.explanation
                }
            ));
        }
    }
    if !report.leaf_origin_passed_checks.is_empty() {
        lines.extend(["".into(), "## Leaf-Origin Passed Checks".into(), "".into()]);
        lines.extend(
            report
                .leaf_origin_passed_checks
                .iter()
                .map(|id| format!("- `{id}`")),
        );
    }
    if !report.forbidden_reachability_findings.is_empty() {
        lines.extend(["".into(), "## Forbidden Reachability Findings".into(), "".into(), "| Check | Severity | Reached | Kind | Status | Origin | Path | Edge Kinds | Explanation |".into(), "| --- | --- | --- | --- | --- | --- | --- | --- | --- |".into()]);
        for finding in &report.forbidden_reachability_findings {
            lines.push(format!(
                "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | {} |",
                finding.check_id,
                finding.severity,
                finding.reached,
                finding.reached_kind,
                finding.reached_status,
                finding.reached_origin,
                finding.path.join(" -> "),
                finding.edge_kinds.join(" -> "),
                if finding.explanation.is_empty() {
                    "None"
                } else {
                    &finding.explanation
                }
            ));
        }
    }
    if !report.forbidden_reachability_passed_checks.is_empty() {
        lines.extend([
            "".into(),
            "## Forbidden Reachability Passed Checks".into(),
            "".into(),
        ]);
        lines.extend(
            report
                .forbidden_reachability_passed_checks
                .iter()
                .map(|id| format!("- `{id}`")),
        );
    }
    lines.join("\n") + "\n"
}

#[derive(Default)]
struct CliArgs {
    graph: Option<PathBuf>,
    out: Option<PathBuf>,
    format: String,
    fail_on_finding: bool,
}

fn parse_args(args: &[String]) -> Result<Option<CliArgs>, String> {
    let mut parsed = CliArgs {
        format: "text".into(),
        ..CliArgs::default()
    };
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--help" | "-h" => {
                println!("Usage: agent-canon {SELECTOR} --graph PATH [--out PATH] [--format text|json|markdown] [--fail-on-finding]");
                return Ok(None);
            }
            "--fail-on-finding" => parsed.fail_on_finding = true,
            "--graph" | "--out" | "--format" => {
                let option = args[index].as_str();
                index += 1;
                let value = args
                    .get(index)
                    .ok_or_else(|| format!("{option} requires a value"))?;
                match option {
                    "--graph" => parsed.graph = Some(PathBuf::from(value)),
                    "--out" => parsed.out = Some(PathBuf::from(value)),
                    _ => parsed.format = value.clone(),
                }
            }
            option => return Err(format!("unknown option: {option}")),
        }
        index += 1;
    }
    if parsed.graph.is_none() {
        return Err("--graph is required".into());
    }
    if !["text", "json", "markdown"].contains(&parsed.format.as_str()) {
        return Err("--format must be text, json, or markdown".into());
    }
    Ok(Some(parsed))
}

pub fn run(args: &[String]) -> i32 {
    match run_inner(args) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: {error}");
            2
        }
    }
}

fn run_inner(args: &[String]) -> Result<i32, String> {
    let Some(args) = parse_args(args)? else {
        return Ok(0);
    };
    let graph_path = args.graph.expect("required arg checked");
    let bytes =
        fs::read(&graph_path).map_err(|error| format!("{}: {error}", graph_path.display()))?;
    let graph: Value = serde_json::from_slice(&bytes)
        .map_err(|error| format!("{}: {error}", graph_path.display()))?;
    let report = check_theorem_graph(&graph)?;
    let rendered = match args.format.as_str() {
        "json" => {
            let json = serde_json::to_value(&report).map_err(|error| error.to_string())?;
            serde_json::to_string_pretty(&json).map_err(|error| error.to_string())? + "\n"
        }
        "markdown" => render_markdown(&report, &dependency_path_from_output(args.out.as_deref())),
        _ => render_text(&report),
    };
    if let Some(out) = args.out {
        fs::write(&out, rendered).map_err(|error| format!("{}: {error}", out.display()))?;
    } else {
        print!("{rendered}");
    }
    Ok(if args.fail_on_finding && report.status == "found" {
        1
    } else {
        0
    })
}
