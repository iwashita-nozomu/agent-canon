// @dependency-start
// contract implementation
// responsibility Renders native dependency-manifest TSV and committed-tree facts into deterministic reports and projections.
// upstream implementation dependency_manifest.rs owns complete source snapshots and manifest semantics
// upstream implementation template_bundle.rs owns the selected committed Git tree reader
// upstream implementation source_mutation.rs owns explicit path-bound report writes
// upstream design ../../../../../documents/design/dependency-manifest-design.md owns graph semantics
// downstream test ../../../../../tests/agent_tools/test_render_dependency_manifest_graph.py verifies CLI, identity, publication, and projections
// @dependency-end

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

pub const SELECTOR: &str = "render-dependency-manifest-graph";
const GRAPH_IR_SCHEMA: &str = "agent_canon.graph_ir.v2";
const BUNDLE_SCHEMA: &str = "agent_canon.dependency_graph_bundle.v1";
const PROJECTION_SCHEMA: &str = "agent_canon.dependency_graph_projection.v1";
const CHECKER_AUTHORITY: &str = "tools/analysis/dependencies/check_dependency_graph.sh";
const PRODUCER_PATH: &str = "tools/runtime/dispatch/agent-canon/src/dependency_manifest_graph.rs";
const CHECKER_GRAPH_TSV_LOCATOR: &str =
    "tools/analysis/dependencies/check_dependency_graph.sh#graph-tsv";
const BUNDLE_GRAPH_TSV_LOCATOR: &str = "dependency_graph.tsv";
const BUNDLE_ARTIFACTS: &[&str] = &[
    "dependency_graph.tsv",
    "dependency_graph.ir.json",
    "dependency_graph.md",
    "dependency_graph.dot",
    "dependency_graph.html",
];

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
struct Edge {
    direction: String,
    kind: String,
    source: String,
    target: String,
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
struct TreeEntry {
    mode: String,
    object_type: String,
    object_id: String,
    path: String,
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
struct ContainmentEdge {
    source: String,
    target: String,
    parent_path: String,
    child_path: String,
    child_kind: String,
}

#[derive(Clone, Debug)]
struct GraphInput {
    path: PathBuf,
    source_returncode: Option<i32>,
    origin_kind: String,
    origin_locator: String,
}

#[derive(Clone, Debug)]
struct GraphReport {
    nodes: Vec<String>,
    edges: Vec<Edge>,
    upstream_cycles: Vec<Vec<String>>,
    downstream_cycles: Vec<Vec<String>>,
    orphan_nodes: Vec<String>,
    broken_targets: Vec<String>,
    high_degree_nodes: Vec<(String, usize)>,
    tracked_tree_revision: String,
    tracked_tree_entries: Vec<TreeEntry>,
}

#[derive(Default)]
struct Options {
    root: Option<PathBuf>,
    graph_tsv: Option<PathBuf>,
    source_revision: String,
    scope: String,
    bundle_dir: Option<PathBuf>,
    ir_out: Option<PathBuf>,
    markdown_out: Option<PathBuf>,
    dot_out: Option<PathBuf>,
    html_out: Option<PathBuf>,
    title: String,
    format: String,
    fail_on_broken: bool,
}

struct TemporaryPath(PathBuf);

impl TemporaryPath {
    fn new() -> Result<Self, String> {
        let file = tempfile::NamedTempFile::new().map_err(|error| error.to_string())?;
        let (_handle, path) = file.keep().map_err(|error| error.error.to_string())?;
        Ok(Self(path))
    }
}

impl Drop for TemporaryPath {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}

fn usage() -> &'static str {
    "usage: agent-canon render-dependency-manifest-graph [--root ROOT] [--graph-tsv PATH] [--source-revision REF] [--scope full|changed] [--bundle-dir DIR | --ir-out PATH] [--markdown-out PATH] [--dot-out PATH] [--html-out PATH] [--title TITLE] [--format text|json] [--fail-on-broken]"
}

fn parse_options(args: &[String]) -> Result<Option<Options>, String> {
    let mut options = Options {
        source_revision: "HEAD".into(),
        scope: "full".into(),
        title: "Code Space Dependency Graph".into(),
        format: "text".into(),
        ..Options::default()
    };
    let names = [
        ("--root", 0),
        ("--graph-tsv", 1),
        ("--source-revision", 2),
        ("--scope", 3),
        ("--bundle-dir", 4),
        ("--ir-out", 5),
        ("--markdown-out", 6),
        ("--dot-out", 7),
        ("--html-out", 8),
        ("--title", 9),
        ("--format", 10),
        ("--fail-on-broken", 11),
    ];
    let mut index = 0;
    while index < args.len() {
        let raw = &args[index];
        if raw == "-h" || raw == "--help" {
            return Ok(None);
        }
        let (flag, inline) = raw
            .split_once('=')
            .map_or((raw.as_str(), None), |(flag, value)| (flag, Some(value)));
        let resolved = crate::python_cli_options::resolve_long_option_prefix(flag, &names)
            .map_err(|_| format!("unrecognized or ambiguous argument: {raw}"))?;
        if resolved == 11 {
            if inline.is_some() {
                return Err(format!("argument {flag}: ignored explicit argument"));
            }
            options.fail_on_broken = true;
            index += 1;
            continue;
        }
        let value = match inline {
            Some(value) => value.to_owned(),
            None => {
                index += 1;
                args.get(index)
                    .cloned()
                    .ok_or_else(|| format!("argument {flag}: expected one argument"))?
            }
        };
        match resolved {
            0 => options.root = Some(value.into()),
            1 => options.graph_tsv = Some(value.into()),
            2 => options.source_revision = value,
            3 if ["full", "changed"].contains(&value.as_str()) => options.scope = value,
            3 => return Err(format!("argument --scope: invalid choice: {value:?}")),
            4 => options.bundle_dir = Some(value.into()),
            5 => options.ir_out = Some(value.into()),
            6 => options.markdown_out = Some(value.into()),
            7 => options.dot_out = Some(value.into()),
            8 => options.html_out = Some(value.into()),
            9 => options.title = value,
            10 if ["text", "json"].contains(&value.as_str()) => options.format = value,
            10 => return Err(format!("argument --format: invalid choice: {value:?}")),
            _ => unreachable!(),
        }
        index += 1;
    }
    let selected = options.ir_out.is_some()
        || options.markdown_out.is_some()
        || options.dot_out.is_some()
        || options.html_out.is_some();
    if options.bundle_dir.is_some() && selected {
        return Err("--bundle-dir is mutually exclusive with named output options".into());
    }
    if options.bundle_dir.is_none() && !selected {
        return Err("projection mode requires at least one named output".into());
    }
    Ok(Some(options))
}

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn json_text(value: &Value) -> Result<String, String> {
    let parsed = crate::python_json::parse_json(&value.to_string())?;
    let mut bytes = crate::python_json::python_json_pretty_ascii_bytes(&parsed)?;
    bytes.push(b'\n');
    String::from_utf8(bytes).map_err(|error| error.to_string())
}

fn normalize_path(path: &Path) -> Result<PathBuf, String> {
    crate::path_resolution::resolve_non_strict(path).map_err(|error| error.to_string())
}

fn normalized_cli_token(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn load_edges(path: &Path) -> Result<Vec<Edge>, String> {
    let text = fs::read_to_string(path).map_err(|error| error.to_string())?;
    let lines = text.lines().collect::<Vec<_>>();
    let header = "direction\tkind\tsource\ttarget";
    let first_content = lines.iter().position(|line| !line.trim().is_empty());
    if !first_content.is_some_and(|index| lines[index] == header) {
        return Err("dependency graph TSV must start with the four-column header".into());
    }
    let first = first_content.expect("header checked");
    let mut edges = Vec::new();
    for (offset, line) in lines.iter().enumerate().skip(first + 1) {
        if line.trim().is_empty() {
            continue;
        }
        let fields = line.split('\t').collect::<Vec<_>>();
        if fields.len() != 4 {
            return Err(format!(
                "dependency graph TSV line {} has {} fields; expected 4",
                offset + 1,
                fields.len()
            ));
        }
        if *line == header {
            return Err(format!(
                "dependency graph TSV line {} repeats the header",
                offset + 1
            ));
        }
        edges.push(Edge {
            direction: fields[0].to_owned(),
            kind: fields[1].to_owned(),
            source: fields[2].to_owned(),
            target: fields[3].to_owned(),
        });
    }
    Ok(edges)
}

fn generate_graph_tsv(
    root: &Path,
    target: &Path,
    scope: &str,
) -> Result<GraphInput, (i32, String, String)> {
    let mut command = Command::new("bash");
    command
        .arg("tools/analysis/dependencies/check_dependency_graph.sh")
        .arg("--root")
        .arg(root)
        .arg("--graph-tsv")
        .arg(target)
        .arg("--cycle-report-only")
        .current_dir(root);
    if scope == "changed" {
        command.arg("--changed");
    }
    let output = command.output().map_err(|error| {
        (
            2,
            String::new(),
            format!("unable to run dependency graph checker: {error}\n"),
        )
    })?;
    if !output.status.success() {
        let code = output.status.code().unwrap_or(2);
        return Err((
            code,
            String::from_utf8_lossy(&output.stdout).into_owned(),
            String::from_utf8_lossy(&output.stderr).into_owned(),
        ));
    }
    Ok(GraphInput {
        path: target.to_path_buf(),
        source_returncode: Some(output.status.code().unwrap_or(0)),
        origin_kind: "generated".into(),
        origin_locator: CHECKER_GRAPH_TSV_LOCATOR.into(),
    })
}

fn repo_path_exists(root: &Path, path: &str) -> bool {
    if path.contains("://") || path.starts_with('#') {
        return true;
    }
    root.join(path).exists()
}

fn is_repo_path_token(path: &str) -> bool {
    !path.is_empty() && !path.contains("://") && !path.starts_with('#')
}

fn directory_id(path: &str) -> String {
    format!("dir:{path}")
}

fn path_group(path: &str) -> String {
    if path.contains("://") {
        return "external".into();
    }
    if path.starts_with('#') {
        return "anchor".into();
    }
    for prefix in ["vendor/agent-canon/", "vendor/model-artifact-canon/"] {
        if path.starts_with(prefix) {
            return prefix.trim_end_matches('/').to_owned();
        }
    }
    path.split('/')
        .next()
        .filter(|value| !value.is_empty())
        .unwrap_or("root")
        .to_owned()
}

fn compact_middle(value: &str, limit: usize) -> String {
    let chars = value.chars().collect::<Vec<_>>();
    if chars.len() <= limit {
        return value.to_owned();
    }
    if limit <= 5 {
        return chars.iter().take(limit).collect();
    }
    let head = 8usize.max((limit - 5) / 2);
    let tail = 8usize.max(limit.saturating_sub(head + 5));
    let first = chars.iter().take(head).collect::<String>();
    let last = chars
        .iter()
        .skip(chars.len().saturating_sub(tail))
        .collect::<String>();
    format!("{first}...{last}")
}

fn path_display(path: &str) -> Value {
    let group = path_group(path);
    if let Some((scheme, rest)) = path.split_once("://") {
        return json!({"label":compact_middle(&format!("{scheme}://{rest}"),28),"parent":"external","full":path});
    }
    if path.starts_with('#') {
        return json!({"label":compact_middle(path,28),"parent":"anchor","full":path});
    }
    let stripped = path.trim_end_matches('/');
    let parts = if stripped.is_empty() {
        vec![path]
    } else {
        stripped.split('/').collect()
    };
    let label = parts.last().copied().unwrap_or(path);
    let mut parent = if parts.len() > 1 {
        parts[..parts.len() - 1].join("/")
    } else {
        group.clone()
    };
    if parent.starts_with(&format!("{group}/")) {
        parent = format!("{group}/{}", parent[group.len() + 1..].to_owned());
    }
    json!({"label":compact_middle(label,32),"parent":compact_middle(if parent.is_empty(){&group}else{&parent},42),"full":path})
}

fn read_committed_tree(
    root: &Path,
    revision: &str,
) -> Result<(String, BTreeMap<String, TreeEntry>), String> {
    let value = crate::template_bundle::committed_tree_value(root, revision)
        .map_err(|error| format!("unable to read selected Git tree: {error}"))?;
    let commit = value
        .get("source_commit")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_owned();
    let mut entries = BTreeMap::new();
    for raw in value
        .get("entries")
        .and_then(Value::as_array)
        .ok_or("committed Git tree entries are missing")?
    {
        let item = raw
            .as_object()
            .ok_or("committed Git tree entry must be an object")?;
        let get = |key: &str| {
            item.get(key)
                .and_then(Value::as_str)
                .map(str::to_owned)
                .ok_or_else(|| format!("committed Git tree entry missing {key}"))
        };
        let entry = TreeEntry {
            mode: get("mode")?,
            object_type: get("object_type")?,
            object_id: get("object_id")?,
            path: get("path")?,
        };
        entries.insert(entry.path.clone(), entry);
    }
    Ok((commit, entries))
}

fn detect_cycles(edges: &[Edge]) -> Vec<Vec<String>> {
    fn canonical(cycle: &[String]) -> Vec<String> {
        let body = &cycle[..cycle.len() - 1];
        let rotations = (0..body.len()).map(|index| {
            let mut rotated = body[index..].to_vec();
            rotated.extend_from_slice(&body[..index]);
            rotated.push(rotated[0].clone());
            rotated
        });
        rotations.min().unwrap_or_default()
    }
    fn visit(
        node: &str,
        adjacency: &BTreeMap<String, BTreeSet<String>>,
        state: &mut BTreeSet<String>,
        done: &mut BTreeSet<String>,
        stack: &mut Vec<String>,
        cycles: &mut BTreeSet<Vec<String>>,
    ) {
        if done.contains(node) {
            return;
        }
        if let Some(index) = stack.iter().position(|item| item == node) {
            cycles.insert(canonical(
                &stack[index..]
                    .iter()
                    .cloned()
                    .chain(std::iter::once(node.to_owned()))
                    .collect::<Vec<_>>(),
            ));
            return;
        }
        if !state.insert(node.to_owned()) {
            return;
        }
        stack.push(node.to_owned());
        if let Some(next) = adjacency.get(node) {
            for child in next {
                visit(child, adjacency, state, done, stack, cycles);
            }
        }
        stack.pop();
        state.remove(node);
        done.insert(node.to_owned());
    }
    let mut adjacency = BTreeMap::<String, BTreeSet<String>>::new();
    for edge in edges {
        adjacency
            .entry(edge.source.clone())
            .or_default()
            .insert(edge.target.clone());
    }
    let mut cycles = BTreeSet::new();
    let mut state = BTreeSet::new();
    let mut done = BTreeSet::new();
    let mut stack = Vec::new();
    for node in adjacency.keys() {
        visit(
            node,
            &adjacency,
            &mut state,
            &mut done,
            &mut stack,
            &mut cycles,
        );
    }
    cycles.into_iter().collect()
}

fn build_report(root: &Path, edges: Vec<Edge>, revision: &str) -> Result<GraphReport, String> {
    let (tree_revision, tree) = read_committed_tree(root, revision)?;
    let tracked_tree_entries = tree.into_values().collect::<Vec<_>>();
    let nodes = edges
        .iter()
        .flat_map(|edge| [edge.source.clone(), edge.target.clone()])
        .collect::<BTreeSet<_>>();
    let mut degree = BTreeMap::<String, usize>::new();
    let mut incoming = BTreeMap::<String, usize>::new();
    let mut outgoing = BTreeMap::<String, usize>::new();
    for edge in &edges {
        *degree.entry(edge.source.clone()).or_default() += 1;
        *degree.entry(edge.target.clone()).or_default() += 1;
        *outgoing.entry(edge.source.clone()).or_default() += 1;
        *incoming.entry(edge.target.clone()).or_default() += 1;
    }
    let orphan_nodes = nodes
        .iter()
        .filter(|node| {
            incoming.get(*node).copied().unwrap_or(0) == 0
                && outgoing.get(*node).copied().unwrap_or(0) == 0
        })
        .cloned()
        .collect();
    let broken_targets = nodes
        .iter()
        .filter(|node| !repo_path_exists(root, node))
        .cloned()
        .collect();
    let mut high_degree_nodes = degree.into_iter().collect::<Vec<_>>();
    high_degree_nodes
        .sort_by(|left, right| right.1.cmp(&left.1).then_with(|| left.0.cmp(&right.0)));
    let upstream_cycles = detect_cycles(
        &edges
            .iter()
            .filter(|edge| edge.direction == "upstream")
            .cloned()
            .collect::<Vec<_>>(),
    );
    let downstream_cycles = detect_cycles(
        &edges
            .iter()
            .filter(|edge| edge.direction == "downstream")
            .cloned()
            .collect::<Vec<_>>(),
    );
    Ok(GraphReport {
        nodes: nodes.into_iter().collect(),
        edges,
        upstream_cycles,
        downstream_cycles,
        orphan_nodes,
        broken_targets,
        high_degree_nodes,
        tracked_tree_revision: tree_revision,
        tracked_tree_entries,
    })
}

fn containment_paths(report: &GraphReport) -> Vec<String> {
    report
        .tracked_tree_entries
        .iter()
        .map(|entry| entry.path.clone())
        .collect()
}
fn directory_containment(
    paths: &[String],
    child_kinds: &BTreeMap<String, String>,
) -> (Vec<String>, Vec<ContainmentEdge>) {
    let mut dirs = BTreeSet::new();
    let mut edges = BTreeSet::new();
    for path in paths {
        if !is_repo_path_token(path) {
            continue;
        }
        let parts = path
            .trim_matches('/')
            .split('/')
            .filter(|part| !part.is_empty() && *part != ".")
            .collect::<Vec<_>>();
        if parts.is_empty() {
            continue;
        }
        dirs.insert(".".to_owned());
        let mut parent = ".".to_owned();
        for index in 1..parts.len() {
            let child = parts[..index].join("/");
            dirs.insert(child.clone());
            edges.insert(ContainmentEdge {
                source: directory_id(&parent),
                target: directory_id(&child),
                parent_path: parent.clone(),
                child_path: child.clone(),
                child_kind: "directory".into(),
            });
            parent = child;
        }
        edges.insert(ContainmentEdge {
            source: directory_id(&parent),
            target: path.clone(),
            parent_path: parent,
            child_path: path.clone(),
            child_kind: child_kinds
                .get(path)
                .cloned()
                .unwrap_or_else(|| "repo_path".into()),
        });
    }
    let mut dirs = dirs.into_iter().collect::<Vec<_>>();
    dirs.sort_by_key(|value| (value != ".", value.clone()));
    (dirs, edges.into_iter().collect())
}

fn graph_fingerprint(edges: &[Edge], revision: &str) -> String {
    let mut lines = edges
        .iter()
        .map(|edge| {
            format!(
                "{}\t{}\t{}\t{}",
                edge.direction, edge.kind, edge.source, edge.target
            )
        })
        .collect::<Vec<_>>();
    lines.push(format!("git-tree-revision\t{revision}"));
    sha256(lines.join("\n").as_bytes())
}

fn graph_ir(report: &GraphReport, source_locator: &str) -> Value {
    let mut incoming = BTreeMap::<String, usize>::new();
    let mut outgoing = BTreeMap::<String, usize>::new();
    for edge in &report.edges {
        *outgoing.entry(edge.source.clone()).or_default() += 1;
        *incoming.entry(edge.target.clone()).or_default() += 1;
    }
    let paths = containment_paths(report);
    let child_kinds = report
        .tracked_tree_entries
        .iter()
        .map(|entry| {
            (
                entry.path.clone(),
                if entry.mode == "120000" {
                    "symlink".to_owned()
                } else if entry.mode == "160000" && entry.object_type == "commit" {
                    "gitlink".to_owned()
                } else {
                    "repo_path".to_owned()
                },
            )
        })
        .collect::<BTreeMap<_, _>>();
    let (dirs, contains) = directory_containment(&paths, &child_kinds);
    let mut contain_in = BTreeMap::<String, usize>::new();
    let mut contain_out = BTreeMap::<String, usize>::new();
    for edge in &contains {
        *contain_out.entry(edge.source.clone()).or_default() += 1;
        *contain_in.entry(edge.target.clone()).or_default() += 1;
    }
    let broken = report
        .broken_targets
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>();
    let tree = report
        .tracked_tree_entries
        .iter()
        .map(|entry| (entry.path.clone(), entry))
        .collect::<BTreeMap<_, _>>();
    let path_nodes = report
        .nodes
        .iter()
        .cloned()
        .chain(tree.keys().cloned())
        .collect::<BTreeSet<_>>();
    let mut nodes = Vec::new();
    for path in path_nodes {
        let display = path_display(&path);
        let group = path_group(&path);
        let inc = incoming.get(&path).copied().unwrap_or(0);
        let out = outgoing.get(&path).copied().unwrap_or(0);
        let payload = json!({"path":path,"group":group,"display":display,"exists":!broken.contains(&path),"metrics":{"incoming":inc,"outgoing":out,"degree":inc+out}});
        let mut record = json!({"id":path,"document_id":"dependency-manifest-graph","layer":"artifact","kind":"repo_path","label":display["label"],"text":path,"source_start":0,"source_end":0,"confidence":1.0,"group":group,"display":display,"source_locator":path,"incoming":inc,"outgoing":out,"degree":inc+out,"broken":broken.contains(&path),"payload_json":payload});
        if let Some(entry) = tree.get(&path) {
            record["document_id"] = json!(format!("git-tree:{}", report.tracked_tree_revision));
            record["payload_json"]["git_tree_entry"] = json!({"revision":report.tracked_tree_revision,"mode":entry.mode,"object_type":entry.object_type,"object_id":entry.object_id});
        }
        nodes.push(record);
    }
    for dir in &dirs {
        let display = if dir == "." {
            json!({"label":".","parent":"repository","full":dir})
        } else {
            path_display(dir)
        };
        let id = directory_id(dir);
        let group = if dir == "." {
            "root".to_owned()
        } else {
            path_group(dir)
        };
        let inc = contain_in.get(&id).copied().unwrap_or(0);
        let out = contain_out.get(&id).copied().unwrap_or(0);
        nodes.push(json!({"id":id,"document_id":format!("git-tree:{}",report.tracked_tree_revision),"layer":"artifact","kind":"directory","label":display["label"],"text":dir,"source_start":0,"source_end":0,"confidence":1.0,"group":group,"display":display,"source_locator":dir,"incoming":inc,"outgoing":out,"degree":inc+out,"broken":false,"payload_json":{"path":dir,"group":group,"display":display,"exists":true,"metrics":{"incoming":inc,"outgoing":out,"degree":inc+out}}}));
    }
    let mut edges=report.edges.iter().enumerate().map(|(index,edge)|json!({"id":format!("edge:{index:06}"),"document_id":"dependency-manifest-graph","layer":"artifact","kind":edge.kind,"relation":edge.direction,"from_node_id":edge.source,"to_node_id":edge.target,"order_kind":"none","label":if edge.direction=="upstream"{edge.kind.clone()}else{format!("{}:{}",edge.direction,edge.kind)},"source_locator":format!("dependency_graph.tsv:{}",index+2),"source_start":index+2,"source_end":index+2,"confidence":1.0,"payload_json":{"direction":edge.direction,"kind":edge.kind,"source":edge.source,"target":edge.target,"row":index}})).collect::<Vec<_>>();
    edges.extend(contains.iter().enumerate().map(|(index,edge)|json!({"id":format!("contains:{index:06}"),"document_id":format!("git-tree:{}",report.tracked_tree_revision),"layer":"artifact","kind":"contains","relation":"contains","from_node_id":edge.source,"to_node_id":edge.target,"order_kind":"none","label":"contains","source_locator":edge.parent_path,"source_start":0,"source_end":0,"confidence":1.0,"payload_json":{"source":edge.source,"target":edge.target,"parentPath":edge.parent_path,"childPath":edge.child_path,"childKind":edge.child_kind}})));
    let mut diagnostics = Vec::new();
    for (direction, cycles) in [
        ("upstream", &report.upstream_cycles),
        ("downstream", &report.downstream_cycles),
    ] {
        for (index, cycle) in cycles.iter().enumerate() {
            diagnostics.push(json!({"id":format!("topology:{direction}:cycle:{index:06}"),"severity":"info","kind":"directional_topology_cycle","message":format!("{direction} directional topology diagnostic: {}",cycle.join(" -> ")),"document_id":"dependency-manifest-graph","node_ids":cycle,"payload_json":{"direction":direction,"cycle":cycle,"checker_failure":false}}));
        }
    }
    for (index, target) in report.broken_targets.iter().enumerate() {
        diagnostics.push(json!({"id":format!("broken-target:{index:06}"),"severity":"warn","kind":"broken_target","message":format!("Broken dependency target: {target}"),"document_id":"dependency-manifest-graph","node_ids":[target],"payload_json":{"target":target,"checker_failure":false}}));
    }
    let total_edges = edges.len();
    let total_nodes = nodes.len();
    let dirs_count = dirs.len();
    let summary = json!({"nodes":report.nodes.len(),"edges":report.edges.len(),"directoryNodes":dirs_count,"containmentEdges":contains.len(),"totalNodes":total_nodes,"totalEdges":total_edges,"upstreamCycles":report.upstream_cycles.len(),"downstreamCycles":report.downstream_cycles.len(),"cycles":report.upstream_cycles.len()+report.downstream_cycles.len(),"brokenTargets":report.broken_targets.len(),"trackedPaths":report.tracked_tree_entries.len()});
    let high = report
        .high_degree_nodes
        .iter()
        .map(|(id, degree)| json!({"id":id,"degree":degree}))
        .collect::<Vec<_>>();
    json!({"schema":GRAPH_IR_SCHEMA,"version":2,"id":format!("dependency-manifest:{}",&graph_fingerprint(&report.edges,&report.tracked_tree_revision)[..16]),"producer":PRODUCER_PATH,"source":{"kind":"dependency_manifest_graph_tsv","path":source_locator,"authority":format!("{CHECKER_AUTHORITY} --graph-tsv"),"git_tree_revision":report.tracked_tree_revision},"documents":[{"id":"dependency-manifest-graph","kind":"dependency_manifest_graph_tsv","title":"Dependency Manifest Graph","source_locator":source_locator,"created_at":"unknown"},{"id":format!("git-tree:{}",report.tracked_tree_revision),"kind":"git_tree_inventory","title":"Tracked Git Tree","source_locator":format!("git-commit:{}",report.tracked_tree_revision),"created_at":"unknown"}],"metadata":[{"name":"created_at","value":"unknown"},{"name":"adapter","value":PRODUCER_PATH},{"name":"checker_authority","value":CHECKER_AUTHORITY},{"name":"checker_pass_fail_authority","value":"checker"},{"name":"git_tree_revision","value":report.tracked_tree_revision}],"summary":summary,"nodes":nodes,"edges":edges,"diagnostics":diagnostics,"directions":report.edges.iter().map(|edge|edge.direction.clone()).collect::<BTreeSet<_>>(),"kinds":report.edges.iter().map(|edge|edge.kind.clone()).collect::<BTreeSet<_>>(),"highDegree":high,"cycles":{"upstream":report.upstream_cycles,"downstream":report.downstream_cycles},"brokenTargets":report.broken_targets,"views":{"html_workbench":{"projection":"browser_graph_workbench","primary_visual":"code_territory_map","secondary_visual":"dense_group_static_graph"},"code_territory_map":{"projection":"group_voronoi","group_field":"group","edge_projection":"inter_group_dependency_edges"},"dense_group_static_graph":{"projection":"group_packed_nodes","node_label":"display.label","node_sub_label":"display.parent"}}})
}

fn graph_summary(report: &GraphReport) -> Value {
    json!({
        "node_count": report.nodes.len(),
        "edge_count": report.edges.len(),
        "upstream_cycle_count": report.upstream_cycles.len(),
        "downstream_cycle_count": report.downstream_cycles.len(),
        "orphan_node_count": report.orphan_nodes.len(),
        "broken_target_count": report.broken_targets.len(),
        "tracked_path_count": report.tracked_tree_entries.len(),
    })
}

fn source_envelope(root: &Path, input: &GraphInput, report: &GraphReport) -> Result<Value, String> {
    let bytes = fs::read(&input.path).map_err(|error| error.to_string())?;
    Ok(json!({
        "root": normalized_cli_token(root),
        "origin_kind": input.origin_kind,
        "origin_locator": input.origin_locator,
        "graph_tsv_sha256": sha256(&bytes),
        "git_tree_revision": report.tracked_tree_revision,
    }))
}

fn checker_envelope(input: &GraphInput) -> Value {
    let status = if input.origin_kind == "supplied" {
        "not_run"
    } else if input.source_returncode == Some(0) {
        "pass"
    } else {
        "fail"
    };
    json!({"authority":CHECKER_AUTHORITY,"status":status})
}

fn render_ir(ir: &Value) -> Result<String, String> {
    let parsed = crate::python_json::parse_json(&ir.to_string())?;
    let mut bytes = crate::python_json::python_json_pretty_ascii_bytes(&parsed)?;
    bytes.push(b'\n');
    String::from_utf8(bytes).map_err(|error| error.to_string())
}

fn render_markdown(report: &GraphReport) -> String {
    let paths = containment_paths(report);
    let child_kinds = report
        .tracked_tree_entries
        .iter()
        .map(|entry| {
            (
                entry.path.clone(),
                if entry.mode == "120000" {
                    "symlink".to_owned()
                } else if entry.mode == "160000" && entry.object_type == "commit" {
                    "gitlink".to_owned()
                } else {
                    "repo_path".to_owned()
                },
            )
        })
        .collect::<BTreeMap<_, _>>();
    let (directory_nodes, containment_edges) = directory_containment(&paths, &child_kinds);
    let all_path_nodes = report
        .nodes
        .iter()
        .cloned()
        .chain(paths.iter().cloned())
        .collect::<BTreeSet<_>>();
    let mut lines = vec![
        "# Dependency Manifest Graph Report".to_owned(),
        String::new(),
        format!("- nodes: {}", report.nodes.len()),
        format!("- edges: {}", report.edges.len()),
        format!("- tracked paths: {}", report.tracked_tree_entries.len()),
        format!("- source revision: {}", report.tracked_tree_revision),
        format!("- directory nodes: {}", directory_nodes.len()),
        format!("- containment edges: {}", containment_edges.len()),
        format!(
            "- total IR nodes: {}",
            all_path_nodes.len() + directory_nodes.len()
        ),
        format!(
            "- total IR edges: {}",
            report.edges.len() + containment_edges.len()
        ),
        format!("- upstream cycles: {}", report.upstream_cycles.len()),
        format!("- downstream cycles: {}", report.downstream_cycles.len()),
        format!("- broken targets: {}", report.broken_targets.len()),
        String::new(),
        "## High Degree Nodes".to_owned(),
        String::new(),
        "| Path | Degree |".to_owned(),
        "| --- | ---: |".to_owned(),
    ];
    for (path, degree) in &report.high_degree_nodes {
        lines.push(format!("| `{path}` | {degree} |"));
    }
    lines.extend([
        String::new(),
        "## Upstream Directional Topology Diagnostics".into(),
        String::new(),
    ]);
    extend_cycles(&mut lines, &report.upstream_cycles);
    lines.extend([
        String::new(),
        "## Downstream Directional Topology Diagnostics".into(),
        String::new(),
    ]);
    extend_cycles(&mut lines, &report.downstream_cycles);
    lines.extend([String::new(), "## Broken Targets".into(), String::new()]);
    if report.broken_targets.is_empty() {
        lines.push("- none".into());
    } else {
        lines.extend(
            report
                .broken_targets
                .iter()
                .map(|path| format!("- `{path}`")),
        );
    }
    let node_ids = report
        .nodes
        .iter()
        .enumerate()
        .map(|(index, node)| (node.clone(), format!("N{index}")))
        .collect::<BTreeMap<_, _>>();
    lines.extend([
        String::new(),
        "## Complete Dependency Projection".into(),
        String::new(),
        "```mermaid".into(),
        "flowchart TD".into(),
    ]);
    for node in &report.nodes {
        lines.push(format!("    {}[\"{}\"]", node_ids[node], html_escape(node)));
    }
    let mut sorted_edges = report.edges.iter().collect::<Vec<_>>();
    sorted_edges.sort_by(|left, right| {
        (&left.source, &left.target, &left.direction, &left.kind).cmp(&(
            &right.source,
            &right.target,
            &right.direction,
            &right.kind,
        ))
    });
    for edge in sorted_edges {
        let label =
            html_escape(&format!("{}:{}", edge.direction, edge.kind)).replace('|', "&#124;");
        lines.push(format!(
            "    {} -->|{}| {}",
            node_ids[&edge.source], label, node_ids[&edge.target]
        ));
    }
    lines.push("```".into());
    let directory_ids = directory_nodes
        .iter()
        .enumerate()
        .map(|(index, path)| (path.clone(), format!("D{index}")))
        .collect::<BTreeMap<_, _>>();
    let path_ids = report
        .tracked_tree_entries
        .iter()
        .enumerate()
        .map(|(index, entry)| (entry.path.clone(), format!("P{index}")))
        .collect::<BTreeMap<_, _>>();
    lines.extend([
        String::new(),
        "## Committed Git Tree Containment".into(),
        String::new(),
        format!("Source commit: `{}`. These `contains` relations are repository structure, not dependency edges.", report.tracked_tree_revision),
        String::new(),
        "```mermaid".into(),
        "flowchart TD".into(),
    ]);
    for path in &directory_nodes {
        lines.push(format!(
            "    {}[\"{}\"]",
            directory_ids[path],
            html_escape(path)
        ));
    }
    for entry in &report.tracked_tree_entries {
        let kind = child_kinds
            .get(&entry.path)
            .map(String::as_str)
            .unwrap_or("repo_path");
        lines.push(format!(
            "    {}[\"{} ({})\"]",
            path_ids[&entry.path],
            html_escape(&entry.path),
            html_escape(kind)
        ));
    }
    for edge in containment_edges {
        let target = if edge.child_kind == "directory" {
            directory_ids[&edge.child_path].clone()
        } else {
            path_ids[&edge.child_path].clone()
        };
        let label = html_escape(&format!("contains:{}", edge.child_kind)).replace('|', "&#124;");
        lines.push(format!(
            "    {} -->|{}| {}",
            directory_ids[&edge.parent_path], label, target
        ));
    }
    lines.push("```".into());
    lines.join("\n") + "\n"
}

fn extend_cycles(lines: &mut Vec<String>, cycles: &[Vec<String>]) {
    if cycles.is_empty() {
        lines.push("- none".into());
    } else {
        lines.extend(
            cycles
                .iter()
                .map(|cycle| format!("- {}", cycle.join(" -> "))),
        );
    }
}

fn dot_id(value: &str) -> String {
    let value = json!(value);
    let parsed = crate::python_json::parse_json(&value.to_string())
        .unwrap_or(crate::python_json::JsonValue::Null);
    crate::python_json::python_json_ascii_bytes(&parsed)
        .ok()
        .and_then(|bytes| String::from_utf8(bytes).ok())
        .unwrap_or_else(|| "\"\"".into())
}

fn render_dot(report: &GraphReport) -> String {
    let paths = containment_paths(report);
    let child_kinds = report
        .tracked_tree_entries
        .iter()
        .map(|entry| {
            (
                entry.path.clone(),
                if entry.mode == "120000" {
                    "symlink".into()
                } else if entry.mode == "160000" && entry.object_type == "commit" {
                    "gitlink".into()
                } else {
                    "repo_path".into()
                },
            )
        })
        .collect::<BTreeMap<String, String>>();
    let (directories, contains) = directory_containment(&paths, &child_kinds);
    let mut lines = vec![
        "digraph dependency_manifest {".into(),
        "  rankdir=LR;".into(),
    ];
    for node in report
        .nodes
        .iter()
        .chain(paths.iter())
        .collect::<BTreeSet<_>>()
    {
        lines.push(format!("  {};", dot_id(node)));
    }
    for directory in directories {
        lines.push(format!("  {};", dot_id(&directory_id(&directory))));
    }
    for edge in &report.edges {
        let label = if edge.direction == "upstream" {
            edge.kind.clone()
        } else {
            format!("{}:{}", edge.direction, edge.kind)
        };
        lines.push(format!(
            "  {} -> {} [label={}];",
            dot_id(&edge.source),
            dot_id(&edge.target),
            dot_id(&label)
        ));
    }
    for edge in contains {
        lines.push(format!(
            "  {} -> {} [label={}];",
            dot_id(&edge.source),
            dot_id(&edge.target),
            dot_id(&format!("contains:{}", edge.child_kind))
        ));
    }
    lines.push("}".into());
    lines.join("\n") + "\n"
}

fn html_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#x27;")
}

fn graph_payload(ir: &Value) -> Value {
    let nodes = ir["nodes"].as_array().cloned().unwrap_or_default();
    let edges = ir["edges"].as_array().cloned().unwrap_or_default();
    let dependency_nodes = nodes
        .iter()
        .filter(|node| node["kind"] == "repo_path")
        .map(|node| {
            json!({
                "id":node["id"],
                "group":node["group"],
                "label":node["display"]["label"],
                "parentLabel":node["display"]["parent"],
                "incoming":node["incoming"],
                "outgoing":node["outgoing"],
                "degree":node["degree"],
                "broken":node["broken"],
            })
        })
        .collect::<Vec<_>>();
    let directory_nodes = nodes
        .iter()
        .filter(|node| node["kind"] == "directory")
        .map(|node| {
            json!({
                "id":node["id"],
                "path":node["payload_json"]["path"],
                "group":node["group"],
                "label":node["display"]["label"],
                "parentLabel":node["display"]["parent"],
                "degree":node["degree"],
            })
        })
        .collect::<Vec<_>>();
    let dependency_edges = edges
        .iter()
        .filter(|edge| edge["relation"] != "contains")
        .map(|edge| edge["payload_json"].clone())
        .collect::<Vec<_>>();
    let containment_edges = edges
        .iter()
        .filter(|edge| edge["relation"] == "contains")
        .map(|edge| edge["payload_json"].clone())
        .collect::<Vec<_>>();
    json!({
        "summary":ir["summary"],
        "nodes":dependency_nodes,
        "edges":dependency_edges,
        "directoryTree":{"nodes":directory_nodes,"edges":containment_edges},
        "directions":ir["directions"],
        "kinds":ir["kinds"],
        "highDegree":ir["highDegree"],
        "cycles":ir["cycles"],
        "brokenTargets":ir["brokenTargets"],
        "views":ir["views"],
    })
}

fn script_json(value: &Value) -> String {
    serde_json::to_string(value)
        .unwrap_or_else(|_| "null".into())
        .replace('&', "\\u0026")
        .replace('<', "\\u003c")
        .replace('>', "\\u003e")
        .replace('\u{2028}', "\\u2028")
        .replace('\u{2029}', "\\u2029")
}

fn short_html_label(value: &str, limit: usize) -> String {
    let chars = value.chars().collect::<Vec<_>>();
    if chars.len() <= limit {
        value.to_owned()
    } else {
        format!(
            "{}...",
            chars
                .iter()
                .take(limit.saturating_sub(3))
                .collect::<String>()
        )
    }
}

fn static_group_node_columns(count: usize) -> usize {
    if count >= 72 {
        4
    } else if count >= 24 {
        3
    } else {
        2
    }
}

type StaticGraphPosition = (usize, usize);
type StaticGraphBounds = (usize, usize, usize, usize);
type StaticGraphLayout = (
    BTreeMap<String, StaticGraphPosition>,
    BTreeMap<String, StaticGraphBounds>,
    Vec<String>,
    usize,
    usize,
);

fn static_graph_layout(nodes: &[Value]) -> StaticGraphLayout {
    let mut grouped = BTreeMap::<String, Vec<Value>>::new();
    for node in nodes {
        grouped
            .entry(node["group"].as_str().unwrap_or_default().to_owned())
            .or_default()
            .push(node.clone());
    }
    for values in grouped.values_mut() {
        values.sort_by_key(|node| node["id"].as_str().unwrap_or_default().to_owned());
    }
    const NODE_W: usize = 180;
    const NODE_H: usize = 34;
    const COL_GAP: usize = 14;
    const ROW_GAP: usize = 10;
    const COLS: usize = 3;
    const GROUP_GAP_X: usize = 52;
    const GROUP_GAP_Y: usize = 48;
    const PAD_X: usize = 22;
    const PAD_TOP: usize = 52;
    const PAD_BOTTOM: usize = 18;
    let max_width = PAD_X * 2 + 4 * NODE_W + 3 * COL_GAP;
    let column_width = max_width + GROUP_GAP_X;
    let mut column_heights = [0usize; COLS];
    let mut positions = BTreeMap::new();
    let mut boxes = BTreeMap::new();
    let mut group_order = grouped.keys().cloned().collect::<Vec<_>>();
    group_order.sort_by_key(|group| (std::cmp::Reverse(grouped[group].len()), group.clone()));
    for group in group_order {
        let group_nodes = &grouped[&group];
        let columns = static_group_node_columns(group_nodes.len());
        let rows = group_nodes.len().div_ceil(columns);
        let width = PAD_X * 2 + columns * NODE_W + (columns - 1) * COL_GAP;
        let height = PAD_TOP + rows * NODE_H + rows.saturating_sub(1) * ROW_GAP + PAD_BOTTOM;
        let column = (0..COLS)
            .min_by_key(|index| column_heights[*index])
            .unwrap_or(0);
        let x = 36 + column * column_width;
        let y = 42 + column_heights[column];
        column_heights[column] += height + GROUP_GAP_Y;
        boxes.insert(group.clone(), (x, y, width, height));
        for (index, node) in group_nodes.iter().enumerate() {
            let col = index % columns;
            let row = index / columns;
            positions.insert(
                node["id"].as_str().unwrap_or_default().to_owned(),
                (
                    x + PAD_X + col * (NODE_W + COL_GAP),
                    y + PAD_TOP + row * (NODE_H + ROW_GAP),
                ),
            );
        }
    }
    let width = 72 + COLS * column_width - GROUP_GAP_X;
    let height = 620.max(column_heights.into_iter().max().unwrap_or(0) + 48);
    let mut render_order = grouped.keys().cloned().collect::<Vec<_>>();
    render_order.sort_by_key(|group| (std::cmp::Reverse(grouped[group].len()), group.clone()));
    (positions, boxes, render_order, width, height)
}

fn node_table_html(payload: &Value) -> String {
    let mut rows = vec![
        "<table id=\"node-table\">".to_owned(),
        "<thead><tr><th>Group</th><th>Name</th><th>Parent</th><th>Path</th><th>In</th><th>Out</th><th>Degree</th></tr></thead>".into(),
        "<tbody>".into(),
    ];
    let mut nodes = payload["nodes"].as_array().cloned().unwrap_or_default();
    nodes.sort_by_key(|node| {
        (
            node["group"].as_str().unwrap_or_default().to_owned(),
            node["id"].as_str().unwrap_or_default().to_owned(),
        )
    });
    for node in nodes {
        let id = node["id"].as_str().unwrap_or_default();
        rows.push(format!(
            "<tr data-agent-canon-source-id=\"{}\"><td>{}</td><td><code>{}</code></td><td><code>{}</code></td><td><code>{}</code></td><td>{}</td><td>{}</td><td>{}</td></tr>",
            html_escape(&format!("node:{id}")),
            html_escape(node["group"].as_str().unwrap_or_default()),
            html_escape(node["label"].as_str().unwrap_or_default()),
            html_escape(node["parentLabel"].as_str().unwrap_or_default()),
            html_escape(id),
            node["incoming"], node["outgoing"], node["degree"]
        ));
    }
    rows.extend(["</tbody>".into(), "</table>".into()]);
    rows.join("\n")
}

fn edge_table_html(report: &GraphReport) -> String {
    let mut rows = vec![
        "<table id=\"edge-table\">".to_owned(),
        "<thead><tr><th>Direction</th><th>Kind</th><th>Source</th><th>Target</th></tr></thead>"
            .into(),
        "<tbody>".into(),
    ];
    for (index, edge) in report.edges.iter().enumerate() {
        let source = format!(
            "edge:{index}:{}:{}:{}:{}",
            edge.direction, edge.kind, edge.source, edge.target
        );
        rows.push(format!(
            "<tr data-agent-canon-source-id=\"{}\"><td>{}</td><td>{}</td><td><code>{}</code></td><td><code>{}</code></td></tr>",
            html_escape(&source), html_escape(&edge.direction), html_escape(&edge.kind), html_escape(&edge.source), html_escape(&edge.target)
        ));
    }
    rows.extend(["</tbody>".into(), "</table>".into()]);
    rows.join("\n")
}

fn directory_tables_html(payload: &Value) -> String {
    let mut rows = vec![
        "<table id=\"directory-node-table\">".to_owned(),
        "<thead><tr><th>Directory</th><th>Path</th></tr></thead>".into(),
        "<tbody>".into(),
    ];
    let mut nodes = payload["directoryTree"]["nodes"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    nodes.sort_by_key(|node| node["path"].as_str().unwrap_or_default().to_owned());
    for node in nodes {
        rows.push(format!(
            "<tr data-agent-canon-source-id=\"{}\"><td>module</td><td><code>{}</code></td></tr>",
            html_escape(node["id"].as_str().unwrap_or_default()),
            html_escape(node["path"].as_str().unwrap_or_default())
        ));
    }
    rows.extend([
        "</tbody>".into(),
        "</table>".into(),
        "<table id=\"directory-edge-table\">".into(),
        "<thead><tr><th>Parent</th><th>Child</th><th>Child kind</th></tr></thead>".into(),
        "<tbody>".into(),
    ]);
    for (index, edge) in payload["directoryTree"]["edges"]
        .as_array()
        .cloned()
        .unwrap_or_default()
        .iter()
        .enumerate()
    {
        rows.push(format!("<tr data-agent-canon-source-id=\"contains:{index:06}\"><td><code>{}</code></td><td><code>{}</code></td><td>{}</td></tr>",html_escape(edge["parentPath"].as_str().unwrap_or_default()),html_escape(edge["childPath"].as_str().unwrap_or_default()),html_escape(edge["childKind"].as_str().unwrap_or_default())));
    }
    rows.extend(["</tbody>".into(), "</table>".into()]);
    rows.join("\n")
}

fn static_graph_svg(report: &GraphReport, payload: &Value) -> String {
    const NODE_W: usize = 180;
    const NODE_H: usize = 34;
    let nodes = payload["nodes"].as_array().cloned().unwrap_or_default();
    let (positions, boxes, group_order, width, height) = static_graph_layout(&nodes);
    let broken = report
        .broken_targets
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>();
    let mut out = vec![format!("<svg id=\"static-graph\" class=\"static-graph js-graph\" viewBox=\"0 0 {width} {height}\" data-base-width=\"{width}\" data-base-height=\"{height}\" role=\"img\" aria-label=\"Static dependency manifest graph\">"), "<defs><marker id=\"static-arrow\" viewBox=\"0 0 10 10\" refX=\"9\" refY=\"5\" markerWidth=\"5\" markerHeight=\"5\" orient=\"auto-start-reverse\"><path d=\"M 0 0 L 10 5 L 0 10 z\"></path></marker></defs>".into(), "<g id=\"static-graph-content\" class=\"static-graph-content\">".into(), "<g class=\"static-groups\">".into()];
    for group in &group_order {
        let (x, y, w, h) = boxes[group];
        let count = nodes
            .iter()
            .filter(|node| node["group"].as_str() == Some(group))
            .count();
        out.push(format!("<g class=\"static-group-block\" transform=\"translate({x} {y})\"><rect width=\"{w}\" height=\"{h}\"></rect><text class=\"static-group\" x=\"12\" y=\"24\">{}</text><text class=\"static-group-sub\" x=\"12\" y=\"40\">{count} nodes</text></g>",html_escape(group)));
    }
    out.extend(["</g>".into(), "<g class=\"static-edges\">".into()]);
    for (index, edge) in report.edges.iter().enumerate() {
        if let (Some(source), Some(target)) =
            (positions.get(&edge.source), positions.get(&edge.target))
        {
            let sx = source.0 + NODE_W;
            let sy = source.1 as f64 + NODE_H as f64 / 2.0;
            let ex = target.0 as f64;
            let ey = target.1 as f64 + NODE_H as f64 / 2.0;
            let curve = 54.0f64.max((ex - sx as f64).abs() / 2.0);
            let source_id = format!(
                "edge:{index}:{}:{}:{}:{}",
                edge.direction, edge.kind, edge.source, edge.target
            );
            out.push(format!("<path class=\"static-edge {}\" data-agent-canon-source-id=\"{}\" d=\"M {sx:.1} {sy:.1} C {:.1} {sy:.1}, {:.1} {ey:.1}, {ex:.1} {ey:.1}\"><title>{}/{:?}: {} -&gt; {}</title></path>",html_escape(&edge.kind),html_escape(&source_id),sx as f64+curve,ex-curve,html_escape(&edge.direction),edge.kind,html_escape(&edge.source),html_escape(&edge.target)));
        }
    }
    out.extend(["</g>".into(), "<g class=\"static-nodes\">".into()]);
    for node in &nodes {
        let id = node["id"].as_str().unwrap_or_default();
        let Some((x, y)) = positions.get(id) else {
            continue;
        };
        let class = if broken.contains(id) {
            "static-node broken"
        } else {
            "static-node"
        };
        let label = html_escape(node["label"].as_str().unwrap_or(id));
        let parent = short_html_label(node["parentLabel"].as_str().unwrap_or("root"), 30);
        let degree = node["degree"].as_u64().unwrap_or(0);
        let source_id = format!("node:{id}");
        out.push(format!("<g class=\"{class}\" data-agent-canon-source-id=\"{}\" transform=\"translate({x} {y})\"><rect width=\"{NODE_W}\" height=\"{NODE_H}\"></rect><text class=\"label\" x=\"10\" y=\"14\">{}</text><text class=\"sub\" x=\"10\" y=\"28\">{} / d {degree}</text><title>{}</title></g>",html_escape(&source_id),html_escape(&short_html_label(&label,29)),html_escape(&parent),html_escape(id)));
    }
    out.push("</g></g></svg>".into());
    out.join("\n")
}

type Point = (f64, f64);

fn halfplane_score(point: Point, seed: Point, other: Point) -> f64 {
    let (x, y) = point;
    let (sx, sy) = seed;
    let (ox, oy) = other;
    2.0 * x * (ox - sx) + 2.0 * y * (oy - sy) + sx * sx + sy * sy - ox * ox - oy * oy
}

fn clip_polygon_to_seed(polygon: &[Point], seed: Point, other: Point) -> Vec<Point> {
    if polygon.is_empty() {
        return Vec::new();
    }
    let mut output = Vec::new();
    let mut previous = polygon[polygon.len() - 1];
    let mut previous_score = halfplane_score(previous, seed, other);
    let mut previous_inside = previous_score <= 1e-9;
    for &current in polygon {
        let current_score = halfplane_score(current, seed, other);
        let current_inside = current_score <= 1e-9;
        if current_inside != previous_inside {
            let denominator = previous_score - current_score;
            let ratio = if denominator == 0.0 {
                0.0
            } else {
                previous_score / denominator
            };
            output.push((
                previous.0 + ratio * (current.0 - previous.0),
                previous.1 + ratio * (current.1 - previous.1),
            ));
        }
        if current_inside {
            output.push(current);
        }
        previous = current;
        previous_score = current_score;
        previous_inside = current_inside;
    }
    output
}

fn polygon_centroid(polygon: &[Point]) -> Point {
    if polygon.is_empty() {
        return (0.0, 0.0);
    }
    (
        polygon.iter().map(|point| point.0).sum::<f64>() / polygon.len() as f64,
        polygon.iter().map(|point| point.1).sum::<f64>() / polygon.len() as f64,
    )
}

fn polygon_path(polygon: &[Point]) -> String {
    let Some(first) = polygon.first() else {
        return String::new();
    };
    let mut parts = vec![format!("M {:.1} {:.1}", first.0, first.1)];
    parts.extend(
        polygon
            .iter()
            .skip(1)
            .map(|point| format!("L {:.1} {:.1}", point.0, point.1)),
    );
    parts.push("Z".into());
    parts.join(" ")
}

fn stable_jitter(text: &str, amplitude: f64) -> Point {
    let digest = Sha256::digest(text.as_bytes());
    let x = u32::from_be_bytes(digest[0..4].try_into().unwrap()) as f64 / 4_294_967_296.0;
    let y = u32::from_be_bytes(digest[4..8].try_into().unwrap()) as f64 / 4_294_967_296.0;
    ((x - 0.5) * amplitude, (y - 0.5) * amplitude)
}

fn territory_seed_points(
    groups: &[String],
    counts: &BTreeMap<String, usize>,
    width: f64,
    height: f64,
) -> BTreeMap<String, Point> {
    let columns = groups.len().clamp(1, 6);
    let rows = groups.len().div_ceil(columns);
    let mut spots = Vec::new();
    for row in 0..rows {
        for column in 0..columns {
            spots.push((
                54.0 + (column as f64 + 0.5) * (width - 108.0) / columns as f64,
                44.0 + (row as f64 + 0.5) * (height - 88.0) / rows as f64,
            ));
        }
    }
    let center = (width / 2.0, height / 2.0);
    spots.sort_by(|left, right| {
        let ld = (left.0 - center.0).abs() + (left.1 - center.1).abs();
        let rd = (right.0 - center.0).abs() + (right.1 - center.1).abs();
        ld.total_cmp(&rd)
            .then_with(|| left.1.total_cmp(&right.1))
            .then_with(|| left.0.total_cmp(&right.0))
    });
    let mut group_order = groups.to_vec();
    group_order.sort_by_key(|group| (std::cmp::Reverse(counts[group]), group.clone()));
    group_order
        .into_iter()
        .zip(spots)
        .map(|(group, spot)| {
            let jitter = stable_jitter(&group, 34.0);
            (
                group,
                (
                    24.0f64.max((width - 24.0).min(spot.0 + jitter.0)),
                    24.0f64.max((height - 24.0).min(spot.1 + jitter.1)),
                ),
            )
        })
        .collect()
}

fn territory_map_svg(report: &GraphReport, payload: &Value) -> String {
    let nodes = payload["nodes"].as_array().cloned().unwrap_or_default();
    let mut group_counts = BTreeMap::<String, usize>::new();
    let mut group_by_node = BTreeMap::new();
    for node in &nodes {
        let group = node["group"].as_str().unwrap_or("root").to_owned();
        *group_counts.entry(group.clone()).or_default() += 1;
        group_by_node.insert(node["id"].as_str().unwrap_or_default().to_owned(), group);
    }
    let mut groups = group_counts.keys().cloned().collect::<Vec<_>>();
    groups.sort();
    let mut group_edges = BTreeMap::<(String, String), usize>::new();
    let mut edge_kinds = BTreeMap::<(String, String), BTreeMap<String, (usize, usize)>>::new();
    for (index, edge) in report.edges.iter().enumerate() {
        let source = group_by_node
            .get(&edge.source)
            .cloned()
            .unwrap_or_else(|| path_group(&edge.source));
        let target = group_by_node
            .get(&edge.target)
            .cloned()
            .unwrap_or_else(|| path_group(&edge.target));
        *group_edges
            .entry((source.clone(), target.clone()))
            .or_default() += 1;
        let counts = edge_kinds.entry((source, target)).or_default();
        let entry = counts.entry(edge.kind.clone()).or_insert((0, index));
        entry.0 += 1;
    }
    let width = 1180.0;
    let height = 420.0;
    let seeds = territory_seed_points(&groups, &group_counts, width, height);
    let bounds = vec![
        (10.0, 10.0),
        (width - 10.0, 10.0),
        (width - 10.0, height - 10.0),
        (10.0, height - 10.0),
    ];
    let mut cells = BTreeMap::new();
    let mut label_points = BTreeMap::new();
    for group in &groups {
        let mut polygon = bounds.clone();
        for other in &groups {
            if other != group {
                polygon = clip_polygon_to_seed(&polygon, seeds[group], seeds[other]);
            }
        }
        label_points.insert(group.clone(), polygon_centroid(&polygon));
        cells.insert(group.clone(), polygon);
    }
    let colors = [
        "#d8ecf0", "#eadff1", "#e1ecd6", "#f1e4d1", "#dbe4f4", "#f3dedd", "#d8eee4", "#e7e1c7",
        "#dde8df", "#e2e0f2", "#f0e0c8", "#d7e6ee",
    ];
    let mut out=vec![format!("<svg class=\"territory-map\" viewBox=\"0 0 {:.0} {:.0}\" role=\"img\" aria-label=\"Voronoi-style code territory map\">",width,height),"<defs><marker id=\"territory-arrow\" viewBox=\"0 0 10 10\" refX=\"9\" refY=\"5\" markerWidth=\"5\" markerHeight=\"5\" orient=\"auto-start-reverse\"><path d=\"M 0 0 L 10 5 L 0 10 z\"></path></marker></defs>".into(),"<g class=\"territory-cells\">".into()];
    let mut render_groups = groups.clone();
    render_groups.sort_by_key(|group| (std::cmp::Reverse(group_counts[group]), group.clone()));
    for (index, group) in render_groups.iter().enumerate() {
        let title = html_escape(&format!("{group}: {} nodes", group_counts[group]));
        out.push(format!(
            "<path class=\"territory-cell\" fill=\"{}\" d=\"{}\"><title>{title}</title></path>",
            colors[index % colors.len()],
            polygon_path(&cells[group])
        ));
    }
    out.extend(["</g>".into(), "<g class=\"territory-edges\">".into()]);
    let max_edge_count = group_edges.values().copied().max().unwrap_or(1);
    for ((source, target), count) in &group_edges {
        if source == target {
            continue;
        }
        let (Some(source_point), Some(target_point)) =
            (label_points.get(source), label_points.get(target))
        else {
            continue;
        };
        let dominant = edge_kinds
            .get(&(source.clone(), target.clone()))
            .and_then(|kinds| {
                kinds.iter().max_by(|left, right| {
                    left.1
                         .0
                        .cmp(&right.1 .0)
                        .then_with(|| right.1 .1.cmp(&left.1 .1))
                })
            })
            .map(|entry| entry.0.as_str())
            .unwrap_or("dependency");
        let title = html_escape(&format!("{source} -> {target}: {count} edges"));
        let width_scale = 1.2 + 4.2 * (*count as f64 / max_edge_count as f64).sqrt();
        out.push(format!("<path class=\"territory-edge {}\" stroke-width=\"{width_scale:.2}\" d=\"M {:.1} {:.1} L {:.1} {:.1}\"><title>{title}</title></path>",html_escape(dominant),source_point.0,source_point.1,target_point.0,target_point.1));
    }
    out.extend(["</g>".into(), "<g class=\"territory-labels\">".into()]);
    for group in &render_groups {
        let (x, y) = label_points[group];
        let count = group_counts[group];
        let title = html_escape(&format!("{group}: {count} nodes"));
        let label = html_escape(&short_html_label(group, 24));
        out.push(format!("<text class=\"territory-label\" x=\"{x:.1}\" y=\"{y:.1}\"><title>{title}</title><tspan x=\"{x:.1}\" dy=\"-3\">{label}</tspan><tspan class=\"sub\" x=\"{x:.1}\" dy=\"14\">{count} nodes</tspan></text>"));
    }
    out.push("</g></svg>".into());
    out.join("\n")
}

fn render_html(report: &GraphReport, title: &str, source_locator: &str, ir: &Value) -> String {
    let payload = graph_payload(ir);
    let page_title = html_escape(title);
    let source = html_escape(source_locator);
    let data = script_json(ir);
    let territory = territory_map_svg(report, &payload);
    let static_graph = static_graph_svg(report, &payload);
    let node_table = node_table_html(&payload);
    let edge_table = edge_table_html(report);
    let directory_table = directory_tables_html(&payload);
    let summary = &payload["summary"];
    let path_node_count = payload["nodes"].as_array().map(Vec::len).unwrap_or(0);
    let zoom=[("fit",1.0,"Fit"),("2x",2.0,"2x"),("4x",4.0,"4x"),("8x",8.0,"8x")].iter().map(|(_,scale,label)|format!("<button type=\"button\" class=\"static-zoom-link\" data-static-zoom=\"{}\">{}</button>",scale,html_escape(label))).collect::<Vec<_>>().join("\n");
    format!("<!doctype html>\n<html lang=\"en\">\n<head>\n  <meta charset=\"utf-8\">\n  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n  <title>{page_title}</title>\n{}\n</head>\n<body>\n  <header><h1>{page_title}</h1><div class=\"metrics\"><div class=\"metric\"><span>path nodes</span><strong>{path_node_count}</strong></div><div class=\"metric\"><span>dependency edges</span><strong>{}</strong></div><div class=\"metric\"><span>tracked paths</span><strong>{}</strong></div><div class=\"metric\"><span>directories</span><strong>{}</strong></div><div class=\"metric\"><span>contains</span><strong>{}</strong></div><div class=\"metric\"><span>cycles</span><strong>{}</strong></div><div class=\"metric\"><span>broken targets</span><strong>{}</strong></div></div></header>\n  <section class=\"graph-workbench\" aria-label=\"Dependency graph workbench\"><h2>Dependency Map</h2><p class=\"muted\">The territory map groups dependency endpoints and committed tracked paths by repository area. The graph view keeps path nodes and dependency edges; committed directory containment is listed separately below.</p><div class=\"graph-stage-grid\"><section class=\"overview-pane\" aria-label=\"Code territory map\"><h3>Code Territory Map</h3><div class=\"territory-map-wrap\">{territory}</div></section><section class=\"fullgraph-pane\" aria-label=\"Full graph map\"><h3>Full Graph Map</h3><div class=\"static-toolbar\" aria-label=\"Static graph zoom controls\"><label for=\"static-zoom\">Zoom <input id=\"static-zoom\" type=\"range\" min=\"1\" max=\"8\" step=\"0.25\" value=\"1\"></label><output id=\"static-zoom-value\" for=\"static-zoom\">1.0x</output>{zoom}<button id=\"static-reset\" type=\"button\">Center</button></div><div class=\"static-graph-wrap\">{static_graph}</div></section></div><details class=\"edge-table\"><summary>Complete path node list ({path_node_count})</summary><div class=\"table-wrap\">{node_table}</div></details><details class=\"edge-table\"><summary>Complete dependency edge list ({})</summary><div class=\"table-wrap\">{edge_table}</div></details><details class=\"edge-table\"><summary>Directory containment ({} directories / {} edges)</summary><div class=\"table-wrap\">{directory_table}</div></details></section>\n  <main class=\"app-shell\"><aside class=\"controls\" aria-label=\"Graph controls\"><fieldset><legend>Search</legend><label for=\"query\">Path query</label><input id=\"query\" type=\"search\" autocomplete=\"off\"><label for=\"focus\">Focus path</label><input id=\"focus\" type=\"text\" list=\"focus-list\" autocomplete=\"off\"><datalist id=\"focus-list\"></datalist><label for=\"depth\">Depth</label><input id=\"depth\" type=\"number\" min=\"0\" max=\"8\" value=\"1\"></fieldset><fieldset><legend>Direction</legend><div id=\"direction-filters\"></div></fieldset><fieldset><legend>Kind</legend><div id=\"kind-filters\"></div></fieldset><p class=\"muted\">Source graph: <code>{source}</code></p></aside><section class=\"graph-pane\" aria-label=\"Graph viewer\"><div class=\"graph-toolbar\"><output id=\"result-count\" aria-live=\"polite\"></output><label for=\"zoom\">Zoom <input id=\"zoom\" type=\"range\" min=\"0.6\" max=\"1.6\" step=\"0.1\" value=\"1\"></label></div><div class=\"graph-canvas\"><svg id=\"graph\" role=\"img\" aria-label=\"Dependency manifest graph\"></svg></div></section><aside class=\"inspector\" aria-label=\"Node inspector\"><div id=\"inspector-content\"></div></aside></main><noscript>Static SVG maps and complete node, edge, and directory tables remain evidence without JavaScript.</noscript><script id=\"graph-data\" type=\"application/json\">{data}</script>\n{}\n</body>\n</html>\n",include_str!("dependency_manifest_graph_style.inc"),report.edges.len(),report.tracked_tree_entries.len(),summary["directoryNodes"],summary["containmentEdges"],report.upstream_cycles.len()+report.downstream_cycles.len(),report.broken_targets.len(),report.edges.len(),summary["directoryNodes"],summary["containmentEdges"],include_str!("dependency_manifest_graph_script.inc"))
}

fn render_outputs(
    report: &GraphReport,
    title: &str,
    source_locator: &str,
    ir: &Value,
) -> Result<BTreeMap<String, String>, String> {
    Ok(BTreeMap::from([
        ("dependency_graph.ir.json".into(), render_ir(ir)?),
        ("dependency_graph.md".into(), render_markdown(report)),
        ("dependency_graph.dot".into(), render_dot(report)),
        (
            "dependency_graph.html".into(),
            render_html(report, title, source_locator, ir),
        ),
    ]))
}

fn output_envelope(
    root: &Path,
    input: &GraphInput,
    report: &GraphReport,
    schema: &str,
    scope: &str,
    paths: &[(String, PathBuf)],
) -> Result<Value, String> {
    let source = source_envelope(root, input, report)?;
    let artifacts = paths
        .iter()
        .map(|(name, path)| {
            let bytes = fs::read(path).map_err(|error| error.to_string())?;
            let media = match path.extension().and_then(|value| value.to_str()).unwrap_or("") {
                "tsv" => "text/tab-separated-values; charset=utf-8",
                "json" => "application/json; charset=utf-8",
                "md" => "text/markdown; charset=utf-8",
                "dot" => "text/vnd.graphviz; charset=utf-8",
                "html" => "text/html; charset=utf-8",
                _ => "application/octet-stream",
            };
            let artifact_name = path.file_name().and_then(|value| value.to_str()).unwrap_or(name);
            Ok(json!({"path":artifact_name,"media_type":media,"bytes":bytes.len(),"sha256":sha256(&bytes)}))
        })
        .collect::<Result<Vec<_>, String>>()?;
    Ok(json!({
        "schema":schema,
        "status":if report.broken_targets.is_empty(){"pass"}else{"fail"},
        "scope":scope,
        "source":source,
        "checker":checker_envelope(input),
        "summary":graph_summary(report),
        "artifacts":artifacts,
    }))
}

fn explicit_output_capability(
    capability_root: &Path,
    allowed: &[PathBuf],
) -> Result<crate::source_mutation::SourceMutationCapability, String> {
    let allowed_paths = allowed
        .iter()
        .map(|path| {
            path.strip_prefix(capability_root)
                .map(|relative| relative.to_string_lossy().replace('\\', "/"))
                .map_err(|_| {
                    format!(
                        "selected output is outside repository root: {}",
                        path.display()
                    )
                })
        })
        .collect::<Result<Vec<_>, _>>()?;
    let packet = json!({
        "allowed_paths":allowed_paths,
        "purpose":"write explicitly selected dependency graph report outputs",
        "authority":"dependency manifest graph CLI output selection"
    });
    crate::source_mutation::SourceMutationCapability::from_json(
        capability_root,
        Some(&packet.to_string()),
    )
    .map_err(|error| error.to_string())
}

fn named_output_paths(options: &Options, _root: &Path) -> Result<Vec<(String, PathBuf)>, String> {
    let mut outputs = Vec::new();
    for (option, path) in [
        ("ir_out", &options.ir_out),
        ("markdown_out", &options.markdown_out),
        ("dot_out", &options.dot_out),
        ("html_out", &options.html_out),
    ] {
        if let Some(path) = path {
            outputs.push((option.to_owned(), normalize_path(path)?));
        }
    }
    Ok(outputs)
}

fn projection_artifact_name(option: &str) -> &'static str {
    match option {
        "ir_out" => "dependency_graph.ir.json",
        "markdown_out" => "dependency_graph.md",
        "dot_out" => "dependency_graph.dot",
        "html_out" => "dependency_graph.html",
        _ => unreachable!(),
    }
}

fn write_named_outputs(
    outputs: &[(String, PathBuf)],
    bodies: &BTreeMap<String, String>,
) -> Result<Vec<(String, PathBuf)>, String> {
    let mut written = Vec::new();
    for (option, path) in outputs {
        let body = bodies
            .get(projection_artifact_name(option))
            .ok_or_else(|| {
                format!(
                    "renderer did not produce {}",
                    projection_artifact_name(option)
                )
            })?;
        let parent = path
            .parent()
            .ok_or_else(|| format!("output path has no parent: {}", path.display()))?;
        fs::create_dir_all(parent).map_err(|error| format!("create output parent: {error}"))?;
        let capability = explicit_output_capability(parent, std::slice::from_ref(path))?;
        capability
            .atomic_write_text_with_parents(path, body, 0o600, true)
            .map_err(|error| error.to_string())?;
        written.push((option.clone(), path.clone()));
    }
    written.sort_by(|left, right| left.0.cmp(&right.0));
    Ok(written)
}

fn reject_duplicate_paths(outputs: &[(String, PathBuf)]) -> Result<(), String> {
    let mut seen = BTreeMap::<PathBuf, String>::new();
    for (option, path) in outputs {
        if let Some(previous) = seen.get(path) {
            return Err(format!(
                "conflicting projection output path: --{} and --{} resolve to {}",
                previous.replace('_', "-"),
                option.replace('_', "-"),
                path.display()
            ));
        }
        seen.insert(path.clone(), option.clone());
    }
    Ok(())
}

fn reject_output_input_collisions(
    graph_tsv: Option<&Path>,
    outputs: &[(String, PathBuf)],
    bundle_dir: Option<&Path>,
) -> Result<(), String> {
    let Some(input) = graph_tsv else {
        return Ok(());
    };
    for (option, path) in outputs {
        if path == input {
            return Err(format!(
                "conflicting output path: --{} and --graph-tsv resolve to {}",
                option.replace('_', "-"),
                input.display()
            ));
        }
    }
    if let Some(bundle) = bundle_dir {
        if bundle == input
            || BUNDLE_ARTIFACTS
                .iter()
                .any(|name| bundle.join(name) == input)
        {
            return Err(format!(
                "conflicting output path: --bundle-dir and --graph-tsv resolve to {}",
                input.display()
            ));
        }
    }
    Ok(())
}

fn write_bundle(
    root: &Path,
    bundle_dir: &Path,
    scope: &str,
    input: &GraphInput,
    report: &GraphReport,
    title: &str,
) -> Result<Value, String> {
    let target = normalize_path(bundle_dir)?;
    if fs::symlink_metadata(&target).is_ok() || target.exists() {
        return Err(format!(
            "bundle target already exists: {}",
            target.display()
        ));
    }
    let parent = target.parent().ok_or("bundle target has no parent")?;
    fs::create_dir_all(parent).map_err(|error| format!("create bundle parent: {error}"))?;
    let parent = fs::canonicalize(parent).map_err(|error| error.to_string())?;
    let target_name = target.file_name().ok_or("bundle target has no name")?;
    let staging = tempfile::Builder::new()
        .prefix(&format!(".{}.staging-", target_name.to_string_lossy()))
        .tempdir_in(&parent)
        .map_err(|error| format!("create bundle staging directory: {error}"))?;
    let stage_path = staging.path().to_path_buf();
    let capability = explicit_output_capability(&parent, &[target.clone(), stage_path.clone()])?;
    let source_bytes = fs::read(&input.path).map_err(|error| error.to_string())?;
    let staged_tsv = stage_path.join("dependency_graph.tsv");
    capability
        .atomic_write_bytes(&staged_tsv, &source_bytes, 0o644)
        .map_err(|error| error.to_string())?;
    let ir = graph_ir(report, BUNDLE_GRAPH_TSV_LOCATOR);
    let outputs = render_outputs(report, title, BUNDLE_GRAPH_TSV_LOCATOR, &ir)?;
    for name in [
        "dependency_graph.ir.json",
        "dependency_graph.md",
        "dependency_graph.dot",
        "dependency_graph.html",
    ] {
        capability
            .atomic_write_text(&stage_path.join(name), &outputs[name], 0o600)
            .map_err(|error| error.to_string())?;
    }
    let artifacts = BUNDLE_ARTIFACTS
        .iter()
        .map(|name| {
            let path = stage_path.join(name);
            let bytes = fs::read(&path).map_err(|error| error.to_string())?;
            let media = match Path::new(name)
                .extension()
                .and_then(|value| value.to_str())
                .unwrap_or("")
            {
                "tsv" => "text/tab-separated-values; charset=utf-8",
                "json" => "application/json; charset=utf-8",
                "md" => "text/markdown; charset=utf-8",
                "dot" => "text/vnd.graphviz; charset=utf-8",
                "html" => "text/html; charset=utf-8",
                _ => "application/octet-stream",
            };
            Ok(json!({"path":name,"media_type":media,"bytes":bytes.len(),"sha256":sha256(&bytes)}))
        })
        .collect::<Result<Vec<_>, String>>()?;
    let manifest = json!({
        "schema":BUNDLE_SCHEMA,
        "status":if report.broken_targets.is_empty(){"pass"}else{"fail"},
        "scope":scope,
        "source":source_envelope(root,input,report)?,
        "checker":checker_envelope(input),
        "summary":graph_summary(report),
        "artifacts":artifacts,
    });
    let manifest_text = json_text(&manifest)?;
    let manifest_path = stage_path.join("manifest.json");
    capability
        .atomic_write_text(&manifest_path, &manifest_text, 0o600)
        .map_err(|error| error.to_string())?;
    capability
        .publish_directory_noreplace(&stage_path, &target)
        .map_err(|error| format!("publish dependency graph bundle: {error}"))?;
    let _ = staging.keep();
    let committed_path = target.join("manifest.json");
    let committed_bytes = fs::read(&committed_path).map_err(|error| error.to_string())?;
    let committed: Value =
        serde_json::from_slice(&committed_bytes).map_err(|error| error.to_string())?;
    if committed != manifest {
        return Err("committed manifest differs from staged manifest".into());
    }
    let mut output = manifest;
    output["manifest_path"] = json!(normalized_cli_token(&committed_path));
    output["manifest_sha256"] = json!(sha256(&committed_bytes));
    Ok(output)
}

fn render_text(envelope: &Value) -> String {
    let mut lines = vec![
        format!("schema={}", envelope["schema"].as_str().unwrap_or_default()),
        format!("status={}", envelope["status"].as_str().unwrap_or_default()),
        format!("scope={}", envelope["scope"].as_str().unwrap_or_default()),
    ];
    for key in ["root", "origin_kind", "origin_locator", "graph_tsv_sha256"] {
        lines.push(format!(
            "source.{key}={}",
            envelope["source"][key].as_str().unwrap_or_default()
        ));
    }
    lines.push(format!(
        "checker.authority={}",
        envelope["checker"]["authority"]
            .as_str()
            .unwrap_or_default()
    ));
    lines.push(format!(
        "checker.status={}",
        envelope["checker"]["status"].as_str().unwrap_or_default()
    ));
    if let Some(summary) = envelope["summary"].as_object() {
        for (key, value) in summary {
            lines.push(format!("summary.{key}={}", scalar(value)));
        }
    }
    if let Some(value) = envelope.get("manifest_path").and_then(Value::as_str) {
        lines.push(format!("manifest.path={value}"));
    }
    if let Some(value) = envelope.get("manifest_sha256").and_then(Value::as_str) {
        lines.push(format!("manifest.hash={value}"));
    }
    if let Some(artifacts) = envelope["artifacts"].as_array() {
        for item in artifacts {
            if let (Some(path), Some(hash)) = (item["path"].as_str(), item["sha256"].as_str()) {
                lines.push(format!("artifact.{path}.sha256={hash}"));
            }
        }
    }
    lines.join("\n") + "\n"
}

fn scalar(value: &Value) -> String {
    value
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| value.to_string())
}

pub fn run(args: &[String]) -> i32 {
    let options = match parse_options(args) {
        Ok(Some(options)) => options,
        Ok(None) => {
            println!("{}", usage());
            return 0;
        }
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let output_format = options.format.clone();
    match run_inner(options) {
        Ok((envelope, exit_code)) => {
            if output_format == "json" {
                match json_text(&envelope) {
                    Ok(text) => print!("{text}"),
                    Err(error) => {
                        eprintln!("{error}");
                        return 2;
                    }
                }
            } else {
                print!("{}", render_text(&envelope));
            }
            exit_code
        }
        Err((code, stdout, stderr)) => {
            eprint!("{stdout}{stderr}");
            code
        }
    }
}

fn run_inner(options: Options) -> Result<(Value, i32), (i32, String, String)> {
    let root = normalize_path(options.root.as_deref().unwrap_or(Path::new(".")))
        .map_err(|error| (2, String::new(), format!("{error}\n")))?;
    let outputs = named_output_paths(&options, &root)
        .map_err(|error| (2, String::new(), format!("{error}\n")))?;
    reject_duplicate_paths(&outputs).map_err(|error| (2, String::new(), format!("{error}\n")))?;
    let graph_tsv = options
        .graph_tsv
        .as_deref()
        .map(normalize_path)
        .transpose()
        .map_err(|error| (2, String::new(), format!("{error}\n")))?;
    let bundle_dir = options
        .bundle_dir
        .as_deref()
        .map(normalize_path)
        .transpose()
        .map_err(|error| (2, String::new(), format!("{error}\n")))?;
    if let Err(error) =
        reject_output_input_collisions(graph_tsv.as_deref(), &outputs, bundle_dir.as_deref())
    {
        return Err((2, String::new(), format!("{error}\n")));
    }
    if let Some(target) = bundle_dir.as_deref() {
        if fs::symlink_metadata(target).is_ok() || target.exists() {
            return Err((
                2,
                String::new(),
                format!("bundle target already exists: {}\n", target.display()),
            ));
        }
    }
    let mut generated_temp = None;
    let mut supplied_temp = None;
    let input = if let Some(path) = graph_tsv.as_deref() {
        let temp = TemporaryPath::new().map_err(|error| {
            (
                2,
                String::new(),
                format!("create input snapshot: {error}\n"),
            )
        })?;
        let target = temp.0.clone();
        fs::copy(path, &target).map_err(|error| {
            (
                2,
                String::new(),
                format!("snapshot supplied TSV: {error}\n"),
            )
        })?;
        supplied_temp = Some(temp);
        GraphInput {
            path: target,
            source_returncode: None,
            origin_kind: "supplied".into(),
            origin_locator: normalized_cli_token(path),
        }
    } else {
        let temporary = TemporaryPath::new().map_err(|error| {
            (
                2,
                String::new(),
                format!("create temporary graph TSV: {error}\n"),
            )
        })?;
        let target = temporary.0.clone();
        generated_temp = Some(temporary);
        generate_graph_tsv(&root, &target, &options.scope)?
    };
    let edges =
        load_edges(&input.path).map_err(|error| (2, String::new(), format!("{error}\n")))?;
    let report = build_report(&root, edges, &options.source_revision)
        .map_err(|error| (2, String::new(), format!("{error}\n")))?;
    let result = if let Some(bundle) = bundle_dir.as_deref() {
        write_bundle(
            &root,
            bundle,
            &options.scope,
            &input,
            &report,
            &options.title,
        )
        .map_err(|error| (2, String::new(), format!("{error}\n")))?
    } else {
        let ir = graph_ir(&report, &input.origin_locator);
        let bodies = render_outputs(&report, &options.title, &input.origin_locator, &ir)
            .map_err(|error| (2, String::new(), format!("{error}\n")))?;
        let written = write_named_outputs(&outputs, &bodies)
            .map_err(|error| (2, String::new(), format!("{error}\n")))?;
        output_envelope(
            &root,
            &input,
            &report,
            PROJECTION_SCHEMA,
            &options.scope,
            &written,
        )
        .map_err(|error| (2, String::new(), format!("{error}\n")))?
    };
    let exit = if options.fail_on_broken && !report.broken_targets.is_empty() {
        1
    } else {
        0
    };
    drop(generated_temp);
    drop(supplied_temp);
    Ok((result, exit))
}
