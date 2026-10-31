//! Board-level route summaries for formal-proof theorem graphs.
// @dependency-start
// contract implementation
// responsibility Builds board-level route summaries for formal-proof theorem graphs.
// upstream design ../../../../../agents/skills/formal-proof-workflow.md problem-level board passes
// upstream design ../../../../../agents/skills/algorithm-proof-exploration.md route-row batch selection
// upstream implementation ../../../../analysis/proof/theorem_graph_circularity_check.py theorem-edge reachability policy
// downstream implementation lib.rs exposes the theorem-board API
// downstream implementation main.rs dispatches the native theorem-board command
// downstream test ../tests/theorem_graph_board_native.rs preserves theorem-board input/output contracts
// @dependency-end

use serde::Serialize;
use serde_json::{Map, Value};
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::fs;
use std::io::{self, Write};

const ROUTE_EXAMPLE_LIMIT: usize = 5;
const ROUTE_NODE_DISPLAY_LIMIT: usize = 20;

const TERMINAL_STATUS_TERMS: &[&str] = &[
    "verified",
    "checked",
    "refuted",
    "unprovable_under_assumptions",
    "boundary",
    "profile_only",
    "projection_only",
];

const OPEN_STATUS_TERMS: &[&str] = &[
    "open",
    "frontier",
    "unverified",
    "unconnected",
    "next_witness",
];

const INACTIVE_EDGE_TERMS: &[&str] = &[
    "not_required",
    "diagnostic",
    "projection_only",
    "rejected",
    "obsolete",
    "profile_only",
];

const ROUTE_LABELS: &[(&str, &[&str])] = &[
    (
        "sufficient",
        &[
            "sufficient",
            "direct_stop_bridge",
            "value_numeric_stop_route",
            "finite_stop",
        ],
    ),
    ("reverse", &["reverse", "necessity", "equivalence"]),
    ("circularity", &["circularity", "projection"]),
    (
        "implementation_extractor",
        &[
            "implementation",
            "extractor",
            "stablehlo",
            "generated_source",
            "trace",
            "lookup",
        ],
    ),
    ("backend", &["backend", "fp32", "llvm", "decode"]),
    (
        "problem_config_expressivity",
        &[
            "problem",
            "config",
            "member",
            "expressivity",
            "first_order",
            "generated_tolerance",
            "budget",
        ],
    ),
    (
        "algorithm_change",
        &["algorithm", "recurrence", "line_search", "initializer"],
    ),
];

/// One route row in a theorem graph board.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct RouteSummary {
    /// Route label selected from the route-bearing node text.
    pub route: String,
    /// `actionable_open`, `needs_classification`, or `closed`.
    pub verdict: String,
    /// Reachable theorem nodes assigned to the route.
    pub total: usize,
    /// Nodes classified as terminal.
    pub terminal: usize,
    /// Nodes classified as open.
    pub open: usize,
    /// Nodes whose status could not be classified.
    pub unknown: usize,
    /// First displayed open node identifiers in sorted order.
    pub open_nodes: Vec<String>,
    /// First displayed unknown node identifiers in sorted order.
    pub unknown_nodes: Vec<String>,
    /// First displayed node identifiers in sorted order.
    pub examples: Vec<String>,
}

/// Board-level summary for a theorem graph.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct BoardSummary {
    /// Input graph identifier, or JSON null when the input has no identifier.
    pub graph_id: Value,
    /// Input root converted with Python-compatible JSON value display.
    pub root: String,
    /// Count of reachable identifiers, including active edge targets absent from `nodes`.
    pub reachable_nodes: usize,
    /// Route summaries sorted by route label.
    pub routes: Vec<RouteSummary>,
    /// Number of routes with at least one open node.
    pub open_route_count: usize,
    /// Number of routes with at least one unclassified node.
    pub unknown_route_count: usize,
}

#[derive(Default)]
struct RouteAccumulator {
    total: usize,
    terminal: usize,
    open: usize,
    unknown: usize,
    open_nodes: Vec<String>,
    unknown_nodes: Vec<String>,
    examples: Vec<String>,
}

fn python_string(value: &Value) -> String {
    match value {
        Value::Null => "None".to_owned(),
        Value::Bool(true) => "True".to_owned(),
        Value::Bool(false) => "False".to_owned(),
        Value::String(value) => value.clone(),
        Value::Number(value) => value.to_string(),
        Value::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(python_repr)
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Object(values) => format!(
            "{{{}}}",
            values
                .iter()
                .map(|(key, value)| format!("{}: {}", python_repr_string(key), python_repr(value)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

fn python_repr(value: &Value) -> String {
    match value {
        Value::String(value) => python_repr_string(value),
        _ => python_string(value),
    }
}

fn python_repr_string(value: &str) -> String {
    let quote = if value.contains('\'') && !value.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut output = String::with_capacity(value.len() + 2);
    output.push(quote);
    for character in value.chars() {
        match character {
            '\\' => output.push_str("\\\\"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            character if character == quote => {
                output.push('\\');
                output.push(character);
            }
            character if character.is_control() => {
                let code = character as u32;
                if code <= 0xff {
                    output.push_str(&format!("\\x{code:02x}"));
                } else if code <= 0xffff {
                    output.push_str(&format!("\\u{code:04x}"));
                } else {
                    output.push_str(&format!("\\U{code:08x}"));
                }
            }
            character => output.push(character),
        }
    }
    output.push(quote);
    output
}

fn node_text(node: &Map<String, Value>) -> String {
    ["id", "kind", "status", "origin", "theorem", "definition"]
        .iter()
        .map(|key| node.get(*key).map(python_string).unwrap_or_default())
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

fn classify_route(node: &Map<String, Value>) -> String {
    let text = node_text(node);
    let mut best: Option<(&'static str, usize)> = None;
    for &(route, terms) in ROUTE_LABELS {
        let score = terms.iter().filter(|term| text.contains(**term)).count();
        if best.is_none_or(|(best_route, best_score)| (score, route) > (best_score, best_route)) {
            best = Some((route, score));
        }
    }
    match best {
        Some((route, score)) if score > 0 => route.to_owned(),
        _ => "other".to_owned(),
    }
}

fn node_status(node: &Map<String, Value>) -> &'static str {
    let kind = node
        .get("kind")
        .map(python_string)
        .unwrap_or_default()
        .to_lowercase();
    let status = node
        .get("status")
        .map(python_string)
        .unwrap_or_default()
        .to_lowercase();
    let text = format!("{kind} {status}");
    if TERMINAL_STATUS_TERMS.iter().any(|term| text.contains(term)) {
        return "terminal";
    }
    if OPEN_STATUS_TERMS.iter().any(|term| text.contains(term)) {
        if text.contains("profile_only") || text.contains("not_required") {
            return "terminal";
        }
        return "open";
    }
    if ["code_fact", "formal_library", "verified_code_fact"].contains(&kind.as_str()) {
        return "terminal";
    }
    if [
        "condition",
        "certificate",
        "class",
        "conclusion",
        "lemma",
        "fact",
        "boundary",
    ]
    .iter()
    .any(|term| kind.contains(term))
    {
        return "terminal";
    }
    "unknown"
}

fn active_edges(graph: &Map<String, Value>) -> BTreeMap<String, Vec<String>> {
    let mut outgoing = BTreeMap::<String, Vec<String>>::new();
    let Some(edges) = graph.get("edges").and_then(Value::as_array) else {
        return outgoing;
    };
    for edge in edges.iter().filter_map(Value::as_object) {
        let Some(source) = edge.get("source").filter(|value| !value.is_null()) else {
            continue;
        };
        let Some(target) = edge.get("target").filter(|value| !value.is_null()) else {
            continue;
        };
        let kind = edge.get("kind").map(python_string).unwrap_or_default();
        let status = edge.get("status").map(python_string).unwrap_or_default();
        if kind.starts_with("diagnostic_")
            || INACTIVE_EDGE_TERMS
                .iter()
                .any(|term| kind.contains(term) || status.contains(term))
        {
            continue;
        }
        outgoing
            .entry(python_string(source))
            .or_default()
            .push(python_string(target));
    }
    outgoing
}

fn reachable(start: &str, outgoing: &BTreeMap<String, Vec<String>>) -> BTreeSet<String> {
    let mut seen = BTreeSet::new();
    let mut queue = VecDeque::from([start.to_owned()]);
    while let Some(current) = queue.pop_front() {
        if !seen.insert(current.clone()) {
            continue;
        }
        if let Some(targets) = outgoing.get(&current) {
            queue.extend(targets.iter().cloned());
        }
    }
    seen
}

/// Build the whole-theorem route board from one theorem graph JSON object.
pub fn board(graph: &Value) -> Result<BoardSummary, String> {
    let graph = graph
        .as_object()
        .ok_or_else(|| "graph must be a JSON object".to_owned())?;
    let nodes = graph
        .get("nodes")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_object)
        .filter_map(|node| node.get("id").map(|node_id| (python_string(node_id), node)))
        .collect::<BTreeMap<_, _>>();
    let outgoing = active_edges(graph);
    let root = graph.get("root").map(python_string).unwrap_or_default();
    let reachable_ids = if nodes.contains_key(&root) {
        reachable(&root, &outgoing)
    } else {
        nodes.keys().cloned().collect()
    };
    let reachable_ids = if reachable_ids.is_empty() {
        nodes.keys().cloned().collect()
    } else {
        reachable_ids
    };

    let mut route_rows = BTreeMap::<String, RouteAccumulator>::new();
    for node_id in &reachable_ids {
        let Some(node) = nodes.get(node_id) else {
            continue;
        };
        let route = classify_route(node);
        let row = route_rows.entry(route).or_default();
        row.total += 1;
        match node_status(node) {
            "terminal" => row.terminal += 1,
            "open" => {
                row.open += 1;
                if row.open_nodes.len() < ROUTE_NODE_DISPLAY_LIMIT {
                    row.open_nodes.push(node_id.clone());
                }
            }
            _ => {
                row.unknown += 1;
                if row.unknown_nodes.len() < ROUTE_NODE_DISPLAY_LIMIT {
                    row.unknown_nodes.push(node_id.clone());
                }
            }
        }
        if row.examples.len() < ROUTE_EXAMPLE_LIMIT {
            row.examples.push(node_id.clone());
        }
    }

    let routes = route_rows
        .into_iter()
        .map(|(route, row)| {
            let verdict = if row.open > 0 {
                "actionable_open"
            } else if row.unknown > 0 {
                "needs_classification"
            } else {
                "closed"
            };
            RouteSummary {
                route,
                verdict: verdict.to_owned(),
                total: row.total,
                terminal: row.terminal,
                open: row.open,
                unknown: row.unknown,
                open_nodes: row.open_nodes,
                unknown_nodes: row.unknown_nodes,
                examples: row.examples,
            }
        })
        .collect::<Vec<_>>();

    Ok(BoardSummary {
        graph_id: graph.get("graph_id").cloned().unwrap_or(Value::Null),
        root,
        reachable_nodes: reachable_ids.len(),
        open_route_count: routes
            .iter()
            .filter(|row| row.verdict == "actionable_open")
            .count(),
        unknown_route_count: routes
            .iter()
            .filter(|row| row.verdict == "needs_classification")
            .count(),
        routes,
    })
}

/// Render the board summary as Markdown.
pub fn render_markdown(summary: &BoardSummary) -> String {
    let mut lines = vec![
        "<!--".to_owned(),
        "@dependency-start".to_owned(),
        "responsibility Records theorem-graph route-board summary for a configured proof graph."
            .to_owned(),
        "upstream implementation theorem_graph_board.rs generates this report from a theorem graph JSON."
            .to_owned(),
        "downstream proof goal-level checkers consume route open and unknown counts.".to_owned(),
        "@dependency-end".to_owned(),
        "-->".to_owned(),
        String::new(),
        "# Theorem Graph Board".to_owned(),
        String::new(),
        format!("- graph_id: `{}`", python_string(&summary.graph_id)),
        format!("- root: `{}`", summary.root),
        format!("- reachable_nodes: `{}`", summary.reachable_nodes),
        format!("- open_route_count: `{}`", summary.open_route_count),
        format!("- unknown_route_count: `{}`", summary.unknown_route_count),
        String::new(),
        "| Route | Verdict | Total | Terminal | Open | Unknown | Open Nodes | Unknown Nodes |"
            .to_owned(),
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |".to_owned(),
    ];
    for row in &summary.routes {
        let open_nodes = display_nodes(&row.open_nodes);
        let unknown_nodes = display_nodes(&row.unknown_nodes);
        lines.push(format!(
            "| {} | `{}` | {} | {} | {} | {} | {} | {} |",
            row.route,
            row.verdict,
            row.total,
            row.terminal,
            row.open,
            row.unknown,
            open_nodes,
            unknown_nodes
        ));
    }
    lines.join("\n") + "\n"
}

fn display_nodes(nodes: &[String]) -> String {
    if nodes.is_empty() {
        "None".to_owned()
    } else {
        nodes
            .iter()
            .map(|item| format!("`{item}`"))
            .collect::<Vec<_>>()
            .join(", ")
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Options {
    graph: String,
    output: Option<String>,
    format: OutputFormat,
    fail_on_open: bool,
    fail_on_unknown: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OutputFormat {
    Json,
    Markdown,
}

fn option_value(
    args: &[String],
    index: &mut usize,
    name: &str,
    inline: Option<&str>,
) -> Result<String, String> {
    if let Some(value) = inline {
        return Ok(value.to_owned());
    }
    *index += 1;
    args.get(*index)
        .filter(|value| !value.starts_with('-'))
        .cloned()
        .ok_or_else(|| format!("argument {name}: expected one argument"))
}

fn parse_options(args: &[String]) -> Result<Option<Options>, String> {
    let mut graph = None;
    let mut output = None;
    let mut format = OutputFormat::Markdown;
    let mut fail_on_open = false;
    let mut fail_on_unknown = false;
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if argument == "-h" || argument == "--help" {
            return Ok(None);
        }
        let (name, inline) = argument
            .split_once('=')
            .map_or((argument.as_str(), None), |(name, value)| {
                (name, Some(value))
            });
        match name {
            "--graph" => graph = Some(option_value(args, &mut index, name, inline)?),
            "--out" => output = Some(option_value(args, &mut index, name, inline)?),
            "--format" => {
                format = match option_value(args, &mut index, name, inline)?.as_str() {
                    "json" => OutputFormat::Json,
                    "markdown" => OutputFormat::Markdown,
                    _ => {
                        return Err(
                            "argument --format: invalid choice (choose from json, markdown)"
                                .to_owned(),
                        )
                    }
                }
            }
            "--fail-on-open" if inline.is_none() => fail_on_open = true,
            "--fail-on-unknown" if inline.is_none() => fail_on_unknown = true,
            _ => return Err(format!("unrecognized arguments: {argument}")),
        }
        index += 1;
    }
    let Some(graph) = graph else {
        return Err("the following arguments are required: --graph".to_owned());
    };
    Ok(Some(Options {
        graph,
        output,
        format,
        fail_on_open,
        fail_on_unknown,
    }))
}

fn usage() -> &'static str {
    "Usage: agent-canon theorem-graph-board --graph <path> [--out <path>] [--format json|markdown] [--fail-on-open] [--fail-on-unknown]"
}

/// Run the native theorem-board command.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_options(args) {
        Ok(Some(options)) => options,
        Ok(None) => {
            println!("{}", usage());
            return 0;
        }
        Err(error) => {
            eprintln!("{}\n{}", error, usage());
            return 2;
        }
    };
    let graph_bytes = match fs::read(&options.graph) {
        Ok(bytes) => bytes,
        Err(error) => {
            eprintln!("read graph {}: {error}", options.graph);
            return 1;
        }
    };
    let graph: Value = match serde_json::from_slice(&graph_bytes) {
        Ok(graph) => graph,
        Err(error) => {
            eprintln!("invalid theorem graph JSON: {error}");
            return 1;
        }
    };
    let summary = match board(&graph) {
        Ok(summary) => summary,
        Err(error) => {
            eprintln!("{error}");
            return 1;
        }
    };
    let output = match options.format {
        OutputFormat::Json => match serde_json::to_string_pretty(&summary) {
            Ok(json) => format!("{json}\n"),
            Err(error) => {
                eprintln!("serialize theorem graph board: {error}");
                return 1;
            }
        },
        OutputFormat::Markdown => render_markdown(&summary),
    };
    if let Some(path) = options.output {
        if let Err(error) = fs::write(&path, output.as_bytes()) {
            eprintln!("write board {path}: {error}");
            return 1;
        }
    } else if let Err(error) = io::stdout().write_all(output.as_bytes()) {
        eprintln!("write board output: {error}");
        return 1;
    }
    if (options.fail_on_open && summary.open_route_count > 0)
        || (options.fail_on_unknown && summary.unknown_route_count > 0)
    {
        return 1;
    }
    0
}
