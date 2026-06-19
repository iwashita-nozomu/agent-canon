// @dependency-start
// contract implementation
// responsibility Builds deterministic change-impact scope plans from Python structural findings and dependency evidence.
// upstream design ../../../documents/design/python-structure-hash.md Python structural duplicate analysis policy
// upstream design ../../../agents/skills/dependency-analysis.md Change Impact Packet contract
// upstream implementation python_structure_hash_report.rs emits structured findings, priority_order, repair_slice, and clusters
// downstream implementation main.rs exposes python-structure-hash-scope-plan
// @dependency-end

use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

const DEFAULT_TOKEN_BUDGET: usize = 14_000;

#[derive(Debug, PartialEq, Eq)]
struct Args {
    input: PathBuf,
    dependency_report_dir: Option<PathBuf>,
    impact_json: Option<PathBuf>,
    output: Option<PathBuf>,
    requested_target: Option<String>,
    token_budget: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct DependencyEdge {
    direction: String,
    kind: String,
    source: String,
    target: String,
    raw_line: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct DependencyEvidence {
    report_dir: Option<PathBuf>,
    graph_path: Option<PathBuf>,
    edit_scope_path: Option<PathBuf>,
    edges: Vec<DependencyEdge>,
    edit_scope_paths: Vec<String>,
    missing_evidence: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ImpactBlock {
    block_id: String,
    problem_kind: String,
    cluster_key: String,
    action_hint: String,
    confidence: String,
    priority_score: usize,
    finding_hashes: Vec<String>,
    target_objects: Vec<String>,
    affected_files: Vec<String>,
    dependency_related_files: Vec<String>,
    source_groups: Vec<String>,
    dependency_depth: usize,
    blocked_by: Vec<String>,
    parallel_safe: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ScopeCandidate {
    candidate_id: String,
    granularity: String,
    block_ids: Vec<String>,
    objective_score: isize,
    wave_count: usize,
    expected_tool_reruns: usize,
    write_conflict_risk: usize,
    token_budget_cost: usize,
    validation_cost: usize,
    semantic_risk: usize,
    rejected_reason: Option<String>,
}

pub fn run(args: &[String]) -> i32 {
    match Args::parse(args).and_then(scope_plan) {
        Ok(()) => 0,
        Err(message) => {
            eprintln!("PY_STRUCTURE_HASH_SCOPE_PLAN=fail");
            eprintln!("PY_STRUCTURE_HASH_SCOPE_PLAN_FINDING={message}");
            2
        }
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut input = None;
        let mut dependency_report_dir = None;
        let mut impact_json = None;
        let mut output = None;
        let mut requested_target = None;
        let mut token_budget = DEFAULT_TOKEN_BUDGET;
        let mut index = 0;
        while index < args.len() {
            match args[index].as_str() {
                "--input" => {
                    input = Some(PathBuf::from(value_after(args, index, "--input")?));
                    index += 2;
                }
                "--dependency-report-dir" => {
                    dependency_report_dir = Some(PathBuf::from(value_after(
                        args,
                        index,
                        "--dependency-report-dir",
                    )?));
                    index += 2;
                }
                "--impact-json" => {
                    impact_json = Some(PathBuf::from(value_after(args, index, "--impact-json")?));
                    index += 2;
                }
                "--output" => {
                    output = Some(PathBuf::from(value_after(args, index, "--output")?));
                    index += 2;
                }
                "--requested-target" => {
                    requested_target =
                        Some(value_after(args, index, "--requested-target")?.to_string());
                    index += 2;
                }
                "--token-budget" => {
                    token_budget = value_after(args, index, "--token-budget")?
                        .parse::<usize>()
                        .map_err(|error| format!("invalid --token-budget: {error}"))?;
                    index += 2;
                }
                value if value.starts_with("--") => {
                    return Err(format!("unknown argument {value}"));
                }
                value => return Err(format!("unexpected positional argument {value}")),
            }
        }
        Ok(Self {
            input: input.ok_or_else(|| "--input is required".to_string())?,
            dependency_report_dir,
            impact_json,
            output,
            requested_target,
            token_budget,
        })
    }
}

fn value_after(args: &[String], index: usize, flag: &str) -> Result<String, String> {
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("{flag} requires a value"))
}

fn scope_plan(args: Args) -> Result<(), String> {
    let report = read_json(&args.input)?;
    let impact = match &args.impact_json {
        Some(path) => read_json(path)?,
        None => Value::Null,
    };
    let dependency = read_dependency_evidence(args.dependency_report_dir.as_deref())?;
    let blocks = build_impact_blocks(&report, &dependency);
    let candidates = scope_candidates(&blocks, args.token_budget);
    let selected = candidates
        .iter()
        .filter(|candidate| candidate.rejected_reason.is_none())
        .max_by(|left, right| {
            left.objective_score
                .cmp(&right.objective_score)
                .then_with(|| left.block_ids.len().cmp(&right.block_ids.len()))
                .then_with(|| left.candidate_id.cmp(&right.candidate_id))
        })
        .cloned();
    let selected_ids = selected
        .as_ref()
        .map(|candidate| candidate.block_ids.iter().cloned().collect::<BTreeSet<_>>())
        .unwrap_or_default();
    let selected_blocks = blocks
        .iter()
        .filter(|block| selected_ids.contains(&block.block_id))
        .cloned()
        .collect::<Vec<_>>();
    let surface_edges = selected_surface_edges(&dependency.edges, &selected_blocks);
    let repair_batches = repair_batches_json(&selected_blocks);
    let handoff_context = handoff_context_json(&selected_blocks, &args.input, &dependency);
    let status = if blocks.is_empty() {
        "empty"
    } else if dependency.missing_evidence.is_empty() {
        "pass"
    } else {
        "incomplete_evidence"
    };
    let payload = json!({
        "schema": "python_structure_hash_scope_plan.v1",
        "summary": {
            "status": status,
            "requested_target": args.requested_target,
            "source_report": args.input,
            "impact_json": args.impact_json,
            "finding_count": report["findings"].as_array().map(|items| items.len()).unwrap_or(0),
            "priority_count": report.pointer("/summary/priority_order").and_then(Value::as_array).map(|items| items.len()).unwrap_or(0),
            "impact_block_count": blocks.len(),
            "scope_candidate_count": candidates.len(),
            "repair_batch_count": repair_batches.as_array().map(|items| items.len()).unwrap_or(0),
            "selected_scope_id": selected.as_ref().map(|candidate| candidate.candidate_id.clone()),
            "dependency_evidence": dependency_evidence_json(&dependency),
            "missing_evidence": dependency.missing_evidence,
            "objective_policy": {
                "goal": "maximize priority coverage while minimizing waves, reruns, write conflicts, token cost, validation cost, and semantic risk",
                "algorithm_basis": [
                    "change impact analysis as graph reachability over affected code and manifest edges",
                    "precedence-constrained scheduling by dependency depth",
                    "coarse scope candidates as lightweight hypergraph-like blocks over files, groups, and finding clusters"
                ]
            },
            "impact_summary": impact_summary_json(&impact),
        },
        "impact_blocks": blocks.iter().map(impact_block_json).collect::<Vec<_>>(),
        "scope_candidates": candidates.iter().map(scope_candidate_json).collect::<Vec<_>>(),
        "selected_scope": selected.as_ref().map(scope_candidate_json).unwrap_or(Value::Null),
        "selected_surface_edges": surface_edges,
        "repair_batches": repair_batches,
        "subagent_handoff_context": handoff_context,
    });
    let rendered = serde_json::to_string_pretty(&payload)
        .map_err(|error| format!("failed to render JSON: {error}"))?
        + "\n";
    if let Some(output) = args.output {
        fs::write(&output, rendered)
            .map_err(|error| format!("failed to write {}: {error}", output.display()))?;
        println!("PY_STRUCTURE_HASH_SCOPE_PLAN_OUTPUT={}", output.display());
    } else {
        print!("{rendered}");
    }
    Ok(())
}

fn read_json(path: &PathBuf) -> Result<Value, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("failed to read {}: {error}", path.display()))?;
    serde_json::from_str(&text)
        .map_err(|error| format!("failed to parse {}: {error}", path.display()))
}

fn read_dependency_evidence(report_dir: Option<&Path>) -> Result<DependencyEvidence, String> {
    let mut evidence = DependencyEvidence {
        report_dir: report_dir.map(Path::to_path_buf),
        graph_path: None,
        edit_scope_path: None,
        edges: Vec::new(),
        edit_scope_paths: Vec::new(),
        missing_evidence: Vec::new(),
    };
    let Some(report_dir) = report_dir else {
        evidence
            .missing_evidence
            .push("dependency_report_dir_missing".to_string());
        return Ok(evidence);
    };
    let graph_path = report_dir.join("dependency_graph.tsv");
    if graph_path.exists() {
        evidence.graph_path = Some(graph_path.clone());
        evidence.edges = parse_dependency_graph(&graph_path)?;
    } else {
        evidence.missing_evidence.push(format!(
            "dependency_graph_tsv_missing:{}",
            graph_path.display()
        ));
    }
    let edit_scope_path = report_dir.join("dependency_edit_scope.txt");
    if edit_scope_path.exists() {
        evidence.edit_scope_path = Some(edit_scope_path.clone());
        evidence.edit_scope_paths = parse_dependency_edit_scope(&edit_scope_path)?;
    } else {
        evidence.missing_evidence.push(format!(
            "dependency_edit_scope_txt_missing:{}",
            edit_scope_path.display()
        ));
    }
    Ok(evidence)
}

fn parse_dependency_graph(path: &Path) -> Result<Vec<DependencyEdge>, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("failed to read {}: {error}", path.display()))?;
    let mut edges = Vec::new();
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let columns = trimmed.split('\t').collect::<Vec<_>>();
        if columns.len() < 4 || columns[0].eq_ignore_ascii_case("direction") {
            continue;
        }
        edges.push(DependencyEdge {
            direction: columns[0].to_string(),
            kind: columns[1].to_string(),
            source: columns[2].to_string(),
            target: columns[3].to_string(),
            raw_line: trimmed.to_string(),
        });
    }
    Ok(edges)
}

fn parse_dependency_edit_scope(path: &Path) -> Result<Vec<String>, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("failed to read {}: {error}", path.display()))?;
    let mut paths = BTreeSet::new();
    for line in text.lines() {
        if !line.contains("DEPENDENCY_EDIT_SCOPE_PATH") && !line.contains("DEPENDENCY_OPEN") {
            continue;
        }
        for token in line
            .replace(['=', ':'], " ")
            .split_whitespace()
            .map(|value| value.trim_matches(|c: char| c == '"' || c == '\'' || c == ','))
        {
            if looks_like_repo_path(token) {
                paths.insert(token.to_string());
                break;
            }
        }
    }
    Ok(paths.into_iter().collect())
}

fn looks_like_repo_path(value: &str) -> bool {
    (value.contains('/') || value.contains('.'))
        && !value.starts_with('-')
        && !value.contains('=')
        && value
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "/._+-".contains(c))
}

fn build_impact_blocks(report: &Value, dependency: &DependencyEvidence) -> Vec<ImpactBlock> {
    let mut blocks = Vec::new();
    if let Some(clusters) = report
        .pointer("/summary/mechanical_problem_clusters")
        .and_then(Value::as_array)
    {
        for cluster in clusters {
            let hashes = hashes_from_refs(cluster.get("findings"));
            let block = block_from_cluster(blocks.len() + 1, cluster, report, dependency, hashes);
            blocks.push(block);
        }
    }
    if blocks.is_empty() {
        if let Some(root) = report.pointer("/summary/repair_slice/root_finding") {
            let hashes = optional_string(root.get("hash"))
                .into_iter()
                .collect::<Vec<_>>();
            blocks.push(block_from_root_finding(1, root, report, dependency, hashes));
        }
    }
    if blocks.is_empty() {
        if let Some(priority) = report
            .pointer("/summary/priority_order")
            .and_then(Value::as_array)
        {
            for item in priority.iter().take(10) {
                let hashes = optional_string(item.get("hash"))
                    .into_iter()
                    .collect::<Vec<_>>();
                blocks.push(block_from_root_finding(
                    blocks.len() + 1,
                    item,
                    report,
                    dependency,
                    hashes,
                ));
            }
        }
    }
    blocks.sort_by(|left, right| {
        right
            .priority_score
            .cmp(&left.priority_score)
            .then_with(|| right.dependency_depth.cmp(&left.dependency_depth))
            .then_with(|| left.block_id.cmp(&right.block_id))
    });
    for (index, block) in blocks.iter_mut().enumerate() {
        block.block_id = format!("impact-block-{:04}", index + 1);
    }
    blocks
}

fn block_from_cluster(
    index: usize,
    cluster: &Value,
    report: &Value,
    dependency: &DependencyEvidence,
    hashes: Vec<String>,
) -> ImpactBlock {
    let priority = priority_for_hashes(report, &hashes);
    let mut affected_files = strings_from_array(cluster.get("affected_files"));
    let mut target_objects = target_objects_for_hashes(report, &hashes);
    target_objects.extend(strings_from_cluster_refs(cluster.get("findings")));
    affected_files.extend(files_from_target_objects(&target_objects));
    affected_files = unique_sorted(affected_files);
    let source_groups = source_groups_for_hashes(report, &hashes);
    let dependency_depth =
        dependency_depth_for_hashes(report, &hashes, &affected_files, dependency);
    let blocked_by = unique_sorted(strings_from_array(cluster.get("blockers")));
    ImpactBlock {
        block_id: format!("impact-block-{index:04}"),
        problem_kind: string_or(cluster.get("problem_kind"), "mechanical_problem_cluster"),
        cluster_key: string_or(cluster.get("cluster_key"), "cluster"),
        action_hint: string_or(cluster.get("action_hint"), "plan_repair_batch"),
        confidence: string_or(cluster.get("confidence"), "medium"),
        priority_score: usize_or(cluster.get("priority_score"), priority),
        finding_hashes: unique_sorted(hashes),
        target_objects: unique_sorted(target_objects),
        dependency_related_files: dependency_related_files(&affected_files, dependency),
        affected_files,
        source_groups,
        dependency_depth,
        parallel_safe: blocked_by.is_empty(),
        blocked_by,
    }
}

fn block_from_root_finding(
    index: usize,
    item: &Value,
    report: &Value,
    dependency: &DependencyEvidence,
    hashes: Vec<String>,
) -> ImpactBlock {
    let target_objects = target_objects_for_hashes(report, &hashes);
    let affected_files = unique_sorted(
        strings_from_array(item.get("instance_files"))
            .into_iter()
            .chain(files_from_target_objects(&target_objects))
            .collect(),
    );
    let source_groups = unique_sorted(strings_from_array(item.get("source_groups")));
    let blocked_by = root_blockers(item);
    ImpactBlock {
        block_id: format!("impact-block-{index:04}"),
        problem_kind: string_or(item.get("kind"), "priority_item"),
        cluster_key: hashes
            .first()
            .cloned()
            .unwrap_or_else(|| "root".to_string()),
        action_hint: if blocked_by.is_empty() {
            "repair_priority_item".to_string()
        } else {
            "review_before_repair".to_string()
        },
        confidence: if blocked_by.is_empty() {
            "medium".to_string()
        } else {
            "low".to_string()
        },
        priority_score: usize_or(item.get("score"), 0),
        finding_hashes: unique_sorted(hashes),
        target_objects: unique_sorted(target_objects),
        dependency_related_files: dependency_related_files(&affected_files, dependency),
        affected_files: affected_files.clone(),
        source_groups,
        dependency_depth: dependency_depth_for_hashes(report, &[], &affected_files, dependency),
        parallel_safe: blocked_by.is_empty(),
        blocked_by,
    }
}

fn dependency_related_files(
    affected_files: &[String],
    dependency: &DependencyEvidence,
) -> Vec<String> {
    let affected = affected_files.iter().cloned().collect::<BTreeSet<_>>();
    let mut related = BTreeSet::new();
    for edge in &dependency.edges {
        if affected.contains(&edge.source) {
            related.insert(edge.target.clone());
        }
        if affected.contains(&edge.target) {
            related.insert(edge.source.clone());
        }
    }
    for path in affected {
        related.remove(&path);
    }
    related.into_iter().collect()
}

fn root_blockers(item: &Value) -> Vec<String> {
    let mut blockers = Vec::new();
    if string_or(item.get("role"), "implementation") != "implementation" {
        blockers.push(format!(
            "non_implementation_role:{}",
            string_or(item.get("role"), "unknown")
        ));
    }
    if string_or(item.get("block_kind"), "") == "Alias" {
        blockers.push("alias_requires_design_review".to_string());
    }
    unique_sorted(blockers)
}

fn priority_for_hashes(report: &Value, hashes: &[String]) -> usize {
    priority_items(report)
        .into_iter()
        .filter(|item| {
            optional_string(item.get("hash"))
                .map(|hash| hashes.contains(&hash))
                .unwrap_or(false)
        })
        .map(|item| usize_or(item.get("score"), 0))
        .sum()
}

fn dependency_depth_for_hashes(
    report: &Value,
    hashes: &[String],
    affected_files: &[String],
    dependency: &DependencyEvidence,
) -> usize {
    let priority_depth = priority_items(report)
        .into_iter()
        .filter(|item| {
            optional_string(item.get("hash"))
                .map(|hash| hashes.is_empty() || hashes.contains(&hash))
                .unwrap_or(false)
        })
        .map(|item| {
            usize_or(item.get("group_imported_by_count"), 0)
                + usize_or(item.get("imported_by_count"), 0)
        })
        .max()
        .unwrap_or(0);
    let dependency_edge_depth = dependency
        .edges
        .iter()
        .filter(|edge| {
            affected_files.contains(&edge.source) || affected_files.contains(&edge.target)
        })
        .count();
    priority_depth + dependency_edge_depth
}

fn source_groups_for_hashes(report: &Value, hashes: &[String]) -> Vec<String> {
    unique_sorted(
        priority_items(report)
            .into_iter()
            .filter(|item| {
                optional_string(item.get("hash"))
                    .map(|hash| hashes.contains(&hash))
                    .unwrap_or(false)
            })
            .flat_map(|item| strings_from_array(item.get("source_groups")))
            .collect(),
    )
}

fn priority_items(report: &Value) -> Vec<&Value> {
    report
        .pointer("/summary/priority_order")
        .and_then(Value::as_array)
        .map(|items| items.iter().collect())
        .unwrap_or_default()
}

fn hashes_from_refs(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| optional_string(item.get("hash")))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default()
}

fn target_objects_for_hashes(report: &Value, hashes: &[String]) -> Vec<String> {
    let mut targets = Vec::new();
    let Some(findings) = report.get("findings").and_then(Value::as_array) else {
        return targets;
    };
    for finding in findings {
        let Some(hash) =
            optional_string(finding.pointer("/why/hash").or_else(|| finding.get("hash")))
        else {
            continue;
        };
        if !hashes.contains(&hash) {
            continue;
        }
        if let Some(instances) = finding.get("instances").and_then(Value::as_array) {
            for instance in instances {
                let path = string_or(instance.get("path"), "");
                if path.is_empty() {
                    continue;
                }
                let line_start = usize_or(instance.get("line_start"), 0);
                let line_end = usize_or(instance.get("line_end"), line_start);
                let qualname = string_or(instance.get("qualname"), "<unknown>");
                targets.push(format!("{path}:{line_start}-{line_end}:{qualname}"));
            }
        }
    }
    targets
}

fn strings_from_cluster_refs(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .flat_map(|item| strings_from_array(item.get("representative_instances")))
                .collect()
        })
        .unwrap_or_default()
}

fn files_from_target_objects(targets: &[String]) -> Vec<String> {
    targets
        .iter()
        .filter_map(|target| target.split(':').next().map(str::to_string))
        .collect()
}

fn scope_candidates(blocks: &[ImpactBlock], token_budget: usize) -> Vec<ScopeCandidate> {
    let mut candidates = Vec::new();
    if blocks.is_empty() {
        return candidates;
    }
    candidates.push(candidate_for_blocks(
        "scope-candidate-0001",
        "top_impact_block",
        &[blocks[0].clone()],
        token_budget,
    ));
    candidates.push(candidate_for_blocks(
        "scope-candidate-0002",
        "all_actionable_impact_blocks",
        &blocks
            .iter()
            .filter(|block| block.blocked_by.is_empty())
            .cloned()
            .collect::<Vec<_>>(),
        token_budget,
    ));
    if let Some(group) = dominant_group(blocks) {
        let grouped = blocks
            .iter()
            .filter(|block| block.source_groups.contains(&group))
            .cloned()
            .collect::<Vec<_>>();
        candidates.push(candidate_for_blocks(
            "scope-candidate-0003",
            "module_group_batch",
            &grouped,
            token_budget,
        ));
    }
    if let Some(file) = dominant_file(blocks) {
        let grouped = blocks
            .iter()
            .filter(|block| block.affected_files.contains(&file))
            .cloned()
            .collect::<Vec<_>>();
        candidates.push(candidate_for_blocks(
            "scope-candidate-0004",
            "file_hotspot_batch",
            &grouped,
            token_budget,
        ));
    }
    candidates.push(candidate_for_blocks(
        "scope-candidate-0005",
        "all_visible_blocks",
        blocks,
        token_budget,
    ));
    deduplicate_candidates(candidates)
}

fn candidate_for_blocks(
    candidate_id: &str,
    granularity: &str,
    blocks: &[ImpactBlock],
    token_budget: usize,
) -> ScopeCandidate {
    let block_ids = blocks.iter().map(|block| block.block_id.clone()).collect();
    let priority_coverage = blocks
        .iter()
        .map(|block| block.priority_score.min(2_000_000) / 1000)
        .sum::<usize>();
    let wave_count = greedy_wave_count(blocks);
    let expected_tool_reruns = wave_count.saturating_add(1);
    let write_conflict_risk = write_conflict_risk(blocks);
    let token_budget_cost = token_budget_cost(blocks);
    let validation_cost = unique_files(blocks).len().max(1);
    let semantic_risk = blocks
        .iter()
        .map(|block| block.blocked_by.len() + usize::from(block.confidence == "low"))
        .sum::<usize>();
    let over_budget_penalty = token_budget_cost.saturating_sub(token_budget) / 10;
    let objective_score = priority_coverage as isize
        - (wave_count as isize * 500)
        - (expected_tool_reruns as isize * 250)
        - (write_conflict_risk as isize * 900)
        - (token_budget_cost as isize / 4)
        - (validation_cost as isize * 40)
        - (semantic_risk as isize * 1200)
        - (over_budget_penalty as isize * 10);
    let rejected_reason = if blocks.is_empty() {
        Some("no_blocks".to_string())
    } else if semantic_risk > 0 && granularity != "top_impact_block" {
        Some("contains_review_blocked_targets".to_string())
    } else if token_budget_cost > token_budget {
        Some("token_budget_exceeded".to_string())
    } else {
        None
    };
    ScopeCandidate {
        candidate_id: candidate_id.to_string(),
        granularity: granularity.to_string(),
        block_ids,
        objective_score,
        wave_count,
        expected_tool_reruns,
        write_conflict_risk,
        token_budget_cost,
        validation_cost,
        semantic_risk,
        rejected_reason,
    }
}

fn deduplicate_candidates(candidates: Vec<ScopeCandidate>) -> Vec<ScopeCandidate> {
    let mut seen = BTreeSet::new();
    let mut kept = Vec::new();
    for candidate in candidates {
        let key = candidate.block_ids.join("|");
        if seen.insert(key) {
            kept.push(candidate);
        }
    }
    kept
}

fn dominant_group(blocks: &[ImpactBlock]) -> Option<String> {
    let mut scores = BTreeMap::<String, usize>::new();
    for block in blocks {
        for group in &block.source_groups {
            *scores.entry(group.clone()).or_default() += block.priority_score.max(1);
        }
    }
    scores
        .into_iter()
        .max_by(|left, right| left.1.cmp(&right.1).then_with(|| right.0.cmp(&left.0)))
        .map(|(group, _)| group)
}

fn dominant_file(blocks: &[ImpactBlock]) -> Option<String> {
    let mut scores = BTreeMap::<String, usize>::new();
    for block in blocks {
        for file in &block.affected_files {
            *scores.entry(file.clone()).or_default() += block.priority_score.max(1);
        }
    }
    scores
        .into_iter()
        .max_by(|left, right| left.1.cmp(&right.1).then_with(|| right.0.cmp(&left.0)))
        .map(|(file, _)| file)
}

fn greedy_wave_count(blocks: &[ImpactBlock]) -> usize {
    if blocks.is_empty() {
        return 0;
    }
    let mut waves: Vec<BTreeSet<String>> = Vec::new();
    for block in blocks {
        let files = block
            .affected_files
            .iter()
            .cloned()
            .collect::<BTreeSet<_>>();
        let mut placed = false;
        for wave in &mut waves {
            if wave.is_disjoint(&files) {
                wave.extend(files.clone());
                placed = true;
                break;
            }
        }
        if !placed {
            waves.push(files);
        }
    }
    waves.len()
}

fn write_conflict_risk(blocks: &[ImpactBlock]) -> usize {
    let mut counts = BTreeMap::<String, usize>::new();
    for block in blocks {
        for file in &block.affected_files {
            *counts.entry(file.clone()).or_default() += 1;
        }
    }
    counts.values().map(|count| count.saturating_sub(1)).sum()
}

fn token_budget_cost(blocks: &[ImpactBlock]) -> usize {
    blocks
        .iter()
        .map(|block| {
            350 + block.target_objects.len() * 40
                + block.affected_files.len() * 25
                + block.finding_hashes.len() * 20
        })
        .sum()
}

fn unique_files(blocks: &[ImpactBlock]) -> Vec<String> {
    blocks
        .iter()
        .flat_map(|block| {
            block
                .affected_files
                .iter()
                .chain(block.dependency_related_files.iter())
                .cloned()
        })
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn selected_surface_edges(edges: &[DependencyEdge], blocks: &[ImpactBlock]) -> Vec<Value> {
    let selected_files = unique_files(blocks).into_iter().collect::<BTreeSet<_>>();
    edges
        .iter()
        .filter(|edge| {
            selected_files.contains(&edge.source) || selected_files.contains(&edge.target)
        })
        .map(|edge| {
            json!({
                "direction": edge.direction,
                "kind": edge.kind,
                "source": edge.source,
                "target": edge.target,
                "raw_line": edge.raw_line,
            })
        })
        .collect()
}

fn repair_batches_json(blocks: &[ImpactBlock]) -> Value {
    let mut sorted = blocks.to_vec();
    sorted.sort_by(|left, right| {
        right
            .dependency_depth
            .cmp(&left.dependency_depth)
            .then_with(|| right.priority_score.cmp(&left.priority_score))
            .then_with(|| left.block_id.cmp(&right.block_id))
    });
    let mut wave_files = Vec::<BTreeSet<String>>::new();
    let mut batches = Vec::new();
    for block in sorted {
        if !block.blocked_by.is_empty() {
            batches.push(json!({
                "batch_id": format!("batch-review-{}", block.block_id),
                "wave": 0,
                "batch_kind": "review_required",
                "block_ids": [block.block_id],
                "target_objects": block.target_objects,
                "allowed_files": allowed_files_for_block(&block),
                "blocked_by": block.blocked_by,
                "parallel_safe": false,
                "validation": validation_for_block(&block),
            }));
            continue;
        }
        let files = block
            .affected_files
            .iter()
            .cloned()
            .collect::<BTreeSet<_>>();
        let mut wave = None;
        for (index, used_files) in wave_files.iter_mut().enumerate() {
            if used_files.is_disjoint(&files) {
                used_files.extend(files.clone());
                wave = Some(index + 1);
                break;
            }
        }
        let wave = match wave {
            Some(value) => value,
            None => {
                wave_files.push(files);
                wave_files.len()
            }
        };
        batches.push(json!({
            "batch_id": format!("batch-wave-{wave:02}-{}", block.block_id),
            "wave": wave,
            "batch_kind": if wave == 1 { "sequential_root_or_disjoint_root" } else { "parallel_downstream_after_rerun" },
            "block_ids": [block.block_id],
            "target_objects": block.target_objects,
            "allowed_files": allowed_files_for_block(&block),
            "blocked_by": block.blocked_by,
            "parallel_safe": block.parallel_safe,
            "validation": validation_for_block(&block),
        }));
    }
    Value::Array(batches)
}

fn allowed_files_for_block(block: &ImpactBlock) -> Vec<String> {
    unique_sorted(
        block
            .affected_files
            .iter()
            .chain(block.dependency_related_files.iter())
            .cloned()
            .collect(),
    )
}

fn validation_for_block(block: &ImpactBlock) -> Vec<String> {
    let mut commands = vec![
        "rerun python-structure-hash for the selected Python scope".to_string(),
        "rerun python-structure-hash-report and python-structure-hash-scope-plan".to_string(),
        "run dependency review for changed files".to_string(),
    ];
    if block
        .affected_files
        .iter()
        .any(|path| path.starts_with("python/") || path.ends_with(".py"))
    {
        commands.push("run targeted Python tests for affected modules".to_string());
    }
    commands
}

fn handoff_context_json(
    blocks: &[ImpactBlock],
    source_report: &Path,
    dependency: &DependencyEvidence,
) -> Value {
    Value::Array(
        blocks
            .iter()
            .map(|block| {
                json!({
                    "block_id": block.block_id,
                    "target_objects": block.target_objects,
                    "current_problem": format!("{} from structural finding cluster {}", block.problem_kind, block.cluster_key),
                    "intended_change": block.action_hint,
                    "forbidden_semantic_delta": [
                        "do not change public behavior while removing structural redundancy",
                        "do not add caller-specific replacement helpers unless the plan marks the target review_required",
                        "do not edit outside allowed_files without updating the Change Impact Packet"
                    ],
                    "validation_signal": validation_for_block(block),
                    "final_response_format": "changed paths, validation commands, unresolved blockers",
                    "evidence_artifacts": {
                        "source_report": source_report,
                        "dependency_graph": dependency.graph_path,
                        "dependency_edit_scope": dependency.edit_scope_path,
                    },
                })
            })
            .collect(),
    )
}

fn dependency_evidence_json(dependency: &DependencyEvidence) -> Value {
    json!({
        "report_dir": dependency.report_dir,
        "dependency_graph_path": dependency.graph_path,
        "dependency_edit_scope_path": dependency.edit_scope_path,
        "edge_count": dependency.edges.len(),
        "edit_scope_path_count": dependency.edit_scope_paths.len(),
        "edit_scope_paths": dependency.edit_scope_paths,
    })
}

fn impact_summary_json(impact: &Value) -> Value {
    if impact.is_null() {
        return Value::Null;
    }
    json!({
        "before_groups": impact.pointer("/summary/before_groups"),
        "after_groups": impact.pointer("/summary/after_groups"),
        "delta_groups": impact.pointer("/summary/delta_groups"),
        "removed_hash_count": impact.pointer("/summary/removed_hash_count"),
        "added_hash_count": impact.pointer("/summary/added_hash_count"),
        "rank_change_count": impact.pointer("/summary/rank_change_count"),
    })
}

fn impact_block_json(block: &ImpactBlock) -> Value {
    json!({
        "block_id": block.block_id,
        "problem_kind": block.problem_kind,
        "cluster_key": block.cluster_key,
        "action_hint": block.action_hint,
        "confidence": block.confidence,
        "priority_score": block.priority_score,
        "finding_hashes": block.finding_hashes,
        "root_targets": block.target_objects,
        "downstream_targets": block.dependency_related_files,
        "affected_files": block.affected_files,
        "dependency_related_files": block.dependency_related_files,
        "source_groups": block.source_groups,
        "dependency_depth": block.dependency_depth,
        "blocked_by": block.blocked_by,
        "parallel_safe": block.parallel_safe,
        "allowed_files": allowed_files_for_block(block),
        "validation": validation_for_block(block),
        "non_goals": [
            "semantic feature changes",
            "new compatibility aliases",
            "manual graph summarization without updating this packet"
        ],
    })
}

fn scope_candidate_json(candidate: &ScopeCandidate) -> Value {
    json!({
        "candidate_id": candidate.candidate_id,
        "granularity": candidate.granularity,
        "block_ids": candidate.block_ids,
        "objective_score": candidate.objective_score,
        "wave_count": candidate.wave_count,
        "expected_tool_reruns": candidate.expected_tool_reruns,
        "write_conflict_risk": candidate.write_conflict_risk,
        "token_budget_cost": candidate.token_budget_cost,
        "validation_cost": candidate.validation_cost,
        "semantic_risk": candidate.semantic_risk,
        "rejected_reason": candidate.rejected_reason,
    })
}

fn optional_string(value: Option<&Value>) -> Option<String> {
    value.and_then(|value| value.as_str().map(str::to_string))
}

fn string_or(value: Option<&Value>, default: &str) -> String {
    optional_string(value).unwrap_or_else(|| default.to_string())
}

fn usize_or(value: Option<&Value>, default: usize) -> usize {
    value
        .and_then(Value::as_u64)
        .map(|value| value as usize)
        .unwrap_or(default)
}

fn strings_from_array(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default()
}

fn unique_sorted(values: Vec<String>) -> Vec<String> {
    values
        .into_iter()
        .filter(|value| !value.is_empty())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture_report() -> Value {
        json!({
            "summary": {
                "priority_order": [
                    {
                        "rank": 1,
                        "score": 2_000_000,
                        "kind": "single_caller_structural_helper",
                        "hash": "h1",
                        "role": "implementation",
                        "block_kind": "Function",
                        "source_groups": ["core"],
                        "instance_files": ["python/pkg/core.py"],
                        "group_imported_by_count": 3,
                        "imported_by_count": 2
                    },
                    {
                        "rank": 2,
                        "score": 1_000_000,
                        "kind": "single_callee_structural_wrapper",
                        "hash": "h2",
                        "role": "implementation",
                        "block_kind": "Function",
                        "source_groups": ["solver"],
                        "instance_files": ["python/pkg/solver.py"],
                        "group_imported_by_count": 1,
                        "imported_by_count": 0
                    }
                ],
                "mechanical_problem_clusters": [
                    {
                        "problem_kind": "same_owner_single_caller_batch",
                        "cluster_key": "python/pkg/core.py:10-20:owner",
                        "action_hint": "inline_or_nest_owned_helpers_together",
                        "confidence": "high",
                        "priority_score": 2_000_000,
                        "affected_files": ["python/pkg/core.py"],
                        "blockers": [],
                        "findings": [
                            {
                                "kind": "single_caller_structural_helper",
                                "hash": "h1",
                                "rank": 1,
                                "score": 2_000_000,
                                "representative_instances": ["python/pkg/core.py:30-35:_helper"]
                            }
                        ]
                    },
                    {
                        "problem_kind": "same_file_refactor_hotspot",
                        "cluster_key": "python/pkg/solver.py",
                        "action_hint": "plan_file_level_repair_batch",
                        "confidence": "medium",
                        "priority_score": 1_000_000,
                        "affected_files": ["python/pkg/solver.py"],
                        "blockers": [],
                        "findings": [
                            {
                                "kind": "single_callee_structural_wrapper",
                                "hash": "h2",
                                "rank": 2,
                                "score": 1_000_000,
                                "representative_instances": ["python/pkg/solver.py:40-44:_wrapper"]
                            }
                        ]
                    }
                ]
            },
            "findings": [
                {
                    "why": {"hash": "h1"},
                    "instances": [
                        {
                            "path": "python/pkg/core.py",
                            "line_start": 30,
                            "line_end": 35,
                            "qualname": "_helper"
                        }
                    ]
                },
                {
                    "why": {"hash": "h2"},
                    "instances": [
                        {
                            "path": "python/pkg/solver.py",
                            "line_start": 40,
                            "line_end": 44,
                            "qualname": "_wrapper"
                        }
                    ]
                }
            ]
        })
    }

    #[test]
    fn builds_blocks_from_mechanical_clusters() {
        let dependency = DependencyEvidence {
            report_dir: None,
            graph_path: None,
            edit_scope_path: None,
            edges: vec![DependencyEdge {
                direction: "downstream".to_string(),
                kind: "implementation".to_string(),
                source: "python/pkg/app.py".to_string(),
                target: "python/pkg/core.py".to_string(),
                raw_line: "downstream\timplementation\tpython/pkg/app.py\tpython/pkg/core.py"
                    .to_string(),
            }],
            edit_scope_paths: Vec::new(),
            missing_evidence: Vec::new(),
        };
        let blocks = build_impact_blocks(&fixture_report(), &dependency);
        assert_eq!(blocks.len(), 2);
        assert_eq!(blocks[0].block_id, "impact-block-0001");
        assert_eq!(blocks[0].finding_hashes, vec!["h1"]);
        assert_eq!(blocks[0].dependency_depth, 6);
        assert!(blocks[0]
            .target_objects
            .contains(&"python/pkg/core.py:30-35:_helper".to_string()));
    }

    #[test]
    fn keeps_edit_scope_paths_out_of_block_allowed_files() {
        let dependency = DependencyEvidence {
            report_dir: None,
            graph_path: None,
            edit_scope_path: Some(PathBuf::from("dependency_edit_scope.txt")),
            edges: vec![DependencyEdge {
                direction: "downstream".to_string(),
                kind: "implementation".to_string(),
                source: "python/pkg/app.py".to_string(),
                target: "python/pkg/core.py".to_string(),
                raw_line: "downstream\timplementation\tpython/pkg/app.py\tpython/pkg/core.py"
                    .to_string(),
            }],
            edit_scope_paths: vec!["python/pkg/unrelated.py".to_string()],
            missing_evidence: Vec::new(),
        };

        let blocks = build_impact_blocks(&fixture_report(), &dependency);
        let allowed = allowed_files_for_block(&blocks[0]);
        let dependency_evidence = dependency_evidence_json(&dependency);

        assert_eq!(
            blocks[0].dependency_related_files,
            vec!["python/pkg/app.py".to_string()]
        );
        assert!(allowed.contains(&"python/pkg/core.py".to_string()));
        assert!(allowed.contains(&"python/pkg/app.py".to_string()));
        assert!(!allowed.contains(&"python/pkg/unrelated.py".to_string()));
        assert_eq!(
            dependency_evidence
                .pointer("/edit_scope_paths/0")
                .and_then(Value::as_str),
            Some("python/pkg/unrelated.py")
        );
    }

    #[test]
    fn selects_larger_disjoint_actionable_candidate() {
        let dependency = DependencyEvidence {
            report_dir: None,
            graph_path: None,
            edit_scope_path: None,
            edges: Vec::new(),
            edit_scope_paths: Vec::new(),
            missing_evidence: Vec::new(),
        };
        let blocks = build_impact_blocks(&fixture_report(), &dependency);
        let candidates = scope_candidates(&blocks, DEFAULT_TOKEN_BUDGET);
        let selected = candidates
            .iter()
            .filter(|candidate| candidate.rejected_reason.is_none())
            .max_by_key(|candidate| candidate.objective_score)
            .expect("selected candidate");
        assert_eq!(selected.granularity, "all_actionable_impact_blocks");
        assert_eq!(selected.wave_count, 1);
    }

    #[test]
    fn parses_dependency_edit_scope_paths() {
        let root =
            std::env::temp_dir().join(format!("agent-canon-scope-plan-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).expect("temp dir");
        let scope = root.join("dependency_edit_scope.txt");
        fs::write(
            &scope,
            "DEPENDENCY_EDIT_SCOPE_PATH=python/pkg/core.py\nDEPENDENCY_OPEN documents/design.md\n",
        )
        .expect("scope file");
        let paths = parse_dependency_edit_scope(&scope).expect("parse scope");
        assert_eq!(
            paths,
            vec![
                "documents/design.md".to_string(),
                "python/pkg/core.py".to_string()
            ]
        );
        fs::remove_dir_all(root).expect("cleanup");
    }
}
