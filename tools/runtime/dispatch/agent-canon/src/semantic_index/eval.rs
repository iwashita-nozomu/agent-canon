// @dependency-start
// contract implementation
// responsibility Owns semantic-index fixture and generated-artifact evaluation semantics.
// upstream design ../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../tools/catalog.yaml command catalog and public command source
// downstream implementation ../../../../tools/repository/github/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use super::args::{
    default_excludes, BuildArgs, CompareProvidersArgs, EvalArgs, EvalOutputArgs, OutputFormat,
    SearchArgs, SimilarKind, DEFAULT_EMBEDDING_BATCH, DEFAULT_MAX_FILE_BYTES, DEFAULT_MIN_SCORE,
};
use super::embedding::{cosine_score, embed_one_for_provider};
use super::model::{sorted_difference, sorted_intersection, IndexedNode, ScoredNode};
use super::pipeline::build_index;
use super::query::{score_nodes, search_index};
use super::relations::{similar_pairs_from_nodes, SimilarPair};
use super::report::scored_node_json;
use super::storage::{
    load_nodes, open_cache_connection, resolve_provider_dim, validate_analysis_db,
};
use serde_json::{json, Value};
use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

pub(super) fn max_path_pair_score(
    nodes: &[IndexedNode],
    left_path: &str,
    right_path: &str,
) -> Option<f32> {
    let left_nodes: Vec<&IndexedNode> =
        nodes.iter().filter(|node| node.path == left_path).collect();
    let right_nodes: Vec<&IndexedNode> = nodes
        .iter()
        .filter(|node| node.path == right_path)
        .collect();
    if left_nodes.is_empty() || right_nodes.is_empty() {
        return None;
    }
    let mut best = 0.0_f32;
    for left in left_nodes {
        for right in &right_nodes {
            best = best.max(cosine_score(&left.vector, &right.vector));
        }
    }
    Some(best)
}

pub(super) fn compare_pair_sets(left: &[SimilarPair], right: &[SimilarPair]) -> Value {
    let left_keys: HashSet<String> = left.iter().map(pair_key).collect();
    let right_keys: HashSet<String> = right.iter().map(pair_key).collect();
    let shared: Vec<String> = sorted_intersection(&left_keys, &right_keys);
    let left_only: Vec<String> = sorted_difference(&left_keys, &right_keys)
        .into_iter()
        .take(10)
        .collect();
    let right_only: Vec<String> = sorted_difference(&right_keys, &left_keys)
        .into_iter()
        .take(10)
        .collect();
    let denominator = left_keys.len().max(right_keys.len()).max(1);
    json!({
        "left_count": left_keys.len(),
        "right_count": right_keys.len(),
        "shared_count": shared.len(),
        "overlap_ratio": shared.len() as f64 / denominator as f64,
        "shared": shared.into_iter().take(10).collect::<Vec<_>>(),
        "left_only": left_only,
        "right_only": right_only
    })
}

pub(super) fn compare_search_sets(query: &str, left: &[ScoredNode], right: &[ScoredNode]) -> Value {
    let left_keys: HashSet<String> = left.iter().map(|hit| node_key(&hit.node)).collect();
    let right_keys: HashSet<String> = right.iter().map(|hit| node_key(&hit.node)).collect();
    let shared: Vec<String> = sorted_intersection(&left_keys, &right_keys);
    let denominator = left_keys.len().max(right_keys.len()).max(1);
    json!({
        "query_chars": query.chars().count(),
        "left_count": left_keys.len(),
        "right_count": right_keys.len(),
        "shared_count": shared.len(),
        "overlap_ratio": shared.len() as f64 / denominator as f64,
        "left_top": left.iter().take(10).map(scored_node_json).collect::<Vec<_>>(),
        "right_top": right.iter().take(10).map(scored_node_json).collect::<Vec<_>>(),
        "left_only": sorted_difference(&left_keys, &right_keys).into_iter().take(10).collect::<Vec<_>>(),
        "right_only": sorted_difference(&right_keys, &left_keys).into_iter().take(10).collect::<Vec<_>>()
    })
}

pub(super) fn pair_key(pair: &SimilarPair) -> String {
    let left = node_key(&pair.left);
    let right = node_key(&pair.right);
    if left <= right {
        format!("{left}|{right}")
    } else {
        format!("{right}|{left}")
    }
}

pub(super) fn node_key(node: &IndexedNode) -> String {
    format!(
        "{}:{}:{}-{}",
        node.path, node.kind, node.line_start, node.line_end
    )
}

pub(super) fn reciprocal_rank(hits: &[ScoredNode], expected_paths: &[String]) -> f64 {
    for hit in hits.iter().take(10) {
        if expected_paths.contains(&hit.node.path) {
            return 1.0 / hit.rank.max(1) as f64;
        }
    }
    0.0
}

fn string_field(value: &Value, key: &str) -> Result<String, String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(|value| value.to_string())
        .ok_or_else(|| format!("expected string field {key}"))
}

fn string_array_field(value: &Value, key: &str) -> Result<Vec<String>, String> {
    let Some(values) = value.get(key).and_then(Value::as_array) else {
        return Err(format!("expected array field {key}"));
    };
    values
        .iter()
        .map(|item| {
            item.as_str()
                .map(|value| value.to_string())
                .ok_or_else(|| format!("{key} must contain only strings"))
        })
        .collect()
}

pub(super) fn run_eval(args: &EvalArgs) -> Result<Value, String> {
    let input_root = args.fixture.join("input");
    let expected_path = args.fixture.join("expected.json");
    let expected_text = fs::read_to_string(&expected_path)
        .map_err(|error| format!("failed to read {}: {error}", expected_path.display()))?;
    let expected: Value = serde_json::from_str(&expected_text)
        .map_err(|error| format!("failed to parse {}: {error}", expected_path.display()))?;
    let build_args = BuildArgs {
        root: input_root.clone(),
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db: args.db.clone(),
        provider: args.provider.clone(),
        model: args.model.clone(),
        dim: args.dim,
        embedding_url: args.embedding_url.clone(),
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    };
    let started = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let stats = build_index(&build_args)?;
    let build_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        .saturating_sub(started);
    let queries = eval_queries(args, &expected)?;
    let pairs = eval_pairs(args, &expected, false)?;
    let must_not = eval_pairs(args, &expected, true)?;
    let passed = queries["failed"].as_u64().unwrap_or(0) == 0
        && pairs["failed"].as_u64().unwrap_or(0) == 0
        && must_not["failed"].as_u64().unwrap_or(0) == 0;
    Ok(json!({
        "semantic_index_eval": if passed { "pass" } else { "fail" },
        "fixture": args.fixture.display().to_string(),
        "db": args.db.display().to_string(),
        "build": {
            "indexed_files": stats.files,
            "indexed_nodes": stats.nodes,
            "missing_embeddings": stats.nodes.saturating_sub(stats.embeddings),
            "build_ms": build_ms
        },
        "search": queries,
        "similarity": pairs,
        "must_not_pairs": must_not
    }))
}

pub(super) fn eval_queries(args: &EvalArgs, expected: &Value) -> Result<Value, String> {
    let Some(queries) = expected.get("queries").and_then(Value::as_array) else {
        return Ok(json!({"cases": 0, "failed": 0, "results": []}));
    };
    let mut results = Vec::new();
    let mut failed = 0;
    let mut recall_sum = 0.0;
    let mut mrr_sum = 0.0;
    for case in queries {
        let id = string_field(case, "id")?;
        let text = string_field(case, "text")?;
        let expected_paths = string_array_field(case, "expected_paths")?;
        let min_recall = case
            .get("min_recall_at_5")
            .and_then(Value::as_f64)
            .unwrap_or(1.0);
        let search_args = SearchArgs {
            root: args.fixture.join("input"),
            db: args.db.clone(),
            query: text,
            provider: args.provider.clone(),
            model: args.model.clone(),
            dim: args.dim,
            embedding_url: args.embedding_url.clone(),
            top_k: args.top_k.max(5),
            format: OutputFormat::Json,
        };
        let hits = search_index(&search_args)?;
        let top5: Vec<&ScoredNode> = hits.results.iter().take(5).collect();
        let found = expected_paths
            .iter()
            .filter(|expected_path| top5.iter().any(|hit| hit.node.path == **expected_path))
            .count();
        let recall = if expected_paths.is_empty() {
            1.0
        } else {
            found as f64 / expected_paths.len() as f64
        };
        let reciprocal_rank = reciprocal_rank(&hits.results, &expected_paths);
        let pass = recall + f64::EPSILON >= min_recall;
        if !pass {
            failed += 1;
        }
        recall_sum += recall;
        mrr_sum += reciprocal_rank;
        results.push(json!({
            "id": id,
            "recall_at_5": recall,
            "mrr": reciprocal_rank,
            "pass": pass,
            "top_paths": hits.results.iter().take(5).map(|hit| hit.node.path.clone()).collect::<Vec<_>>()
        }));
    }
    let cases = queries.len() as f64;
    Ok(json!({
        "cases": queries.len(),
        "failed": failed,
        "mean_recall_at_5": if cases == 0.0 { 0.0 } else { recall_sum / cases },
        "mrr": if cases == 0.0 { 0.0 } else { mrr_sum / cases },
        "results": results
    }))
}

pub(super) fn eval_pairs(
    args: &EvalArgs,
    expected: &Value,
    must_not: bool,
) -> Result<Value, String> {
    let key = if must_not {
        "must_not_pairs"
    } else {
        "similar_pairs"
    };
    let Some(cases) = expected.get(key).and_then(Value::as_array) else {
        return Ok(json!({"cases": 0, "failed": 0, "results": []}));
    };
    let conn = open_cache_connection(&args.db)?;
    let nodes = load_nodes(&conn, &args.provider, &args.model, args.dim)?;
    let mut results = Vec::new();
    let mut failed = 0;
    for case in cases {
        let id = string_field(case, "id")?;
        let left_path = string_field(case, "left")?;
        let right_path = string_field(case, "right")?;
        let score = max_path_pair_score(&nodes, &left_path, &right_path);
        let pass = if must_not {
            let max_score = case
                .get("max_score")
                .and_then(Value::as_f64)
                .unwrap_or(DEFAULT_MIN_SCORE as f64);
            score.is_some_and(|value| value <= max_score as f32)
        } else {
            let min_score = case
                .get("min_score")
                .and_then(Value::as_f64)
                .unwrap_or(DEFAULT_MIN_SCORE as f64);
            score.is_some_and(|value| value + f32::EPSILON >= min_score as f32)
        };
        if !pass {
            failed += 1;
        }
        results.push(json!({
            "id": id,
            "left": left_path,
            "right": right_path,
            "score": score.unwrap_or(0.0),
            "missing_path": score.is_none(),
            "pass": pass
        }));
    }
    Ok(json!({
        "cases": cases.len(),
        "failed": failed,
        "results": results
    }))
}

pub(super) fn compare_providers(args: &CompareProvidersArgs) -> Result<Value, String> {
    validate_analysis_db(&args.root, &args.db)?;
    let conn = open_cache_connection(&args.db)?;
    let left_dim =
        resolve_provider_dim(&conn, &args.left.provider, &args.left.model, args.left.dim)?;
    let right_dim = resolve_provider_dim(
        &conn,
        &args.right.provider,
        &args.right.model,
        args.right.dim,
    )?;
    let left_nodes = load_nodes(&conn, &args.left.provider, &args.left.model, left_dim)?;
    let right_nodes = load_nodes(&conn, &args.right.provider, &args.right.model, right_dim)?;
    let left_pairs = similar_pairs_from_nodes(
        &left_nodes,
        SimilarKind::MergeCandidates,
        args.min_score,
        args.top_k,
        true,
    );
    let right_pairs = similar_pairs_from_nodes(
        &right_nodes,
        SimilarKind::MergeCandidates,
        args.min_score,
        args.top_k,
        true,
    );
    let merge_delta = compare_pair_sets(&left_pairs, &right_pairs);
    let search_delta = if let Some(query) = &args.query {
        let left_query = embed_one_for_provider(
            &args.left.provider,
            &args.left.model,
            left_dim,
            args.left.embedding_url.as_deref(),
            query,
        )?;
        let right_query = embed_one_for_provider(
            &args.right.provider,
            &args.right.model,
            right_dim,
            args.right.embedding_url.as_deref(),
            query,
        )?;
        let left_hits = score_nodes(&left_nodes, &left_query, args.top_k);
        let right_hits = score_nodes(&right_nodes, &right_query, args.top_k);
        Some(compare_search_sets(query, &left_hits, &right_hits))
    } else {
        None
    };
    Ok(json!({
        "semantic_index_provider_compare": "ok",
        "db": args.db,
        "top_k": args.top_k,
        "min_score": args.min_score,
        "left": {
            "provider": args.left.provider,
            "model": args.left.model,
            "dim": left_dim,
            "nodes": left_nodes.len(),
            "merge_candidates": left_pairs.len()
        },
        "right": {
            "provider": args.right.provider,
            "model": args.right.model,
            "dim": right_dim,
            "nodes": right_nodes.len(),
            "merge_candidates": right_pairs.len()
        },
        "merge_candidates": merge_delta,
        "search": search_delta
    }))
}

pub(super) fn eval_output(args: &EvalOutputArgs) -> Result<Value, String> {
    let mut artifacts = Vec::new();
    let mut findings = Vec::new();
    if let Some(path) = &args.merge_candidates {
        artifacts.push(eval_merge_candidates_output(path, &mut findings)?);
    }
    if let Some(path) = &args.thin_docs {
        artifacts.push(eval_thin_docs_output(path, &mut findings)?);
    }
    if let Some(path) = &args.search {
        artifacts.push(eval_search_output(path, &mut findings)?);
    }
    let error_count = findings
        .iter()
        .filter(|finding| {
            finding
                .get("severity")
                .and_then(Value::as_str)
                .is_some_and(|severity| severity == "error")
        })
        .count();
    Ok(json!({
        "semantic_index_output_eval": if error_count == 0 { "pass" } else { "fail" },
        "artifacts": artifacts,
        "findings": findings,
        "error_count": error_count
    }))
}

pub(super) fn eval_merge_candidates_output(
    path: &Path,
    findings: &mut Vec<Value>,
) -> Result<Value, String> {
    let (summary, results) = read_jsonl_artifact(path)?;
    let artifact = path.display().to_string();
    expect_summary_field(findings, &artifact, &summary, "semantic_index_pairs", "ok");
    expect_summary_field(findings, &artifact, &summary, "kind", "merge-candidates");
    check_result_count(findings, &artifact, &summary, results.len());
    for (index, result) in results.iter().enumerate() {
        let context = format!("result[{index}]");
        check_rank_score(findings, &artifact, &context, result, "score");
        if !result
            .get("same_responsibility")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "merge candidate is not same_responsibility=true",
            );
        }
        let candidate_bucket = result
            .get("candidate_bucket")
            .and_then(Value::as_str)
            .unwrap_or("");
        if candidate_bucket.is_empty() || candidate_bucket == "similar:any" {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "merge candidate is missing a concrete candidate_bucket",
            );
        }
        let Some(left) = result.get("left") else {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "missing left object",
            );
            continue;
        };
        let Some(right) = result.get("right") else {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "missing right object",
            );
            continue;
        };
        let left_responsibility = json_str(left, "responsibility_bucket");
        let right_responsibility = json_str(right, "responsibility_bucket");
        if left_responsibility.is_empty()
            || right_responsibility.is_empty()
            || left_responsibility != right_responsibility
        {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "left/right responsibility_bucket must be present and equal",
            );
        }
        if left_responsibility == "eval-and-hook-evidence" {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "eval-and-hook-evidence must not be emitted as merge evidence",
            );
        }
        if json_str(left, "node_kind") != json_str(right, "node_kind") {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "merge candidate node_kind differs across sides",
            );
        }
        if json_str(left, "path").is_empty() || json_str(right, "path").is_empty() {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "merge candidate left/right path must be present",
            );
        }
    }
    Ok(json!({
        "artifact": artifact,
        "kind": "merge-candidates",
        "results": results.len()
    }))
}

pub(super) fn eval_thin_docs_output(
    path: &Path,
    findings: &mut Vec<Value>,
) -> Result<Value, String> {
    let (summary, results) = read_jsonl_artifact(path)?;
    let artifact = path.display().to_string();
    expect_summary_field(
        findings,
        &artifact,
        &summary,
        "semantic_index_thin_docs",
        "ok",
    );
    check_result_count(findings, &artifact, &summary, results.len());
    for (index, result) in results.iter().enumerate() {
        let context = format!("result[{index}]");
        check_rank_score(findings, &artifact, &context, result, "thin_score");
        let action = json_str(result, "action");
        if !matches!(
            action.as_str(),
            "keep_entrypoint"
                | "inline_into_target"
                | "replace_with_catalog_row"
                | "merge_with_peer"
                | "manual_review"
        ) {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "thin-doc action is missing or unknown",
            );
        }
        if json_str(result, "path").is_empty() {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "thin-doc path must be present",
            );
        }
        let protected = result
            .get("reasons")
            .and_then(Value::as_array)
            .is_some_and(|reasons| {
                reasons
                    .iter()
                    .any(|reason| reason.as_str() == Some("protected_entrypoint"))
            });
        if protected && action != "keep_entrypoint" {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "protected_entrypoint must use keep_entrypoint action",
            );
        }
    }
    Ok(json!({
        "artifact": artifact,
        "kind": "thin-docs",
        "results": results.len()
    }))
}

pub(super) fn eval_search_output(path: &Path, findings: &mut Vec<Value>) -> Result<Value, String> {
    let (summary, results) = read_jsonl_artifact(path)?;
    let artifact = path.display().to_string();
    expect_summary_field(findings, &artifact, &summary, "semantic_index_search", "ok");
    check_result_count(findings, &artifact, &summary, results.len());
    if summary.get("query").is_some() {
        push_output_finding(
            findings,
            &artifact,
            "error",
            "summary",
            "search JSONL summary must not echo full query text",
        );
    }
    if summary.get("query_chars").and_then(Value::as_u64).is_none() {
        push_output_finding(
            findings,
            &artifact,
            "error",
            "summary",
            "search JSONL summary must include query_chars",
        );
    }
    for (index, result) in results.iter().enumerate() {
        let context = format!("result[{index}]");
        check_rank_score(findings, &artifact, &context, result, "score");
        if json_str(result, "path").is_empty() {
            push_output_finding(
                findings,
                &artifact,
                "error",
                &context,
                "search result path must be present",
            );
        }
    }
    Ok(json!({
        "artifact": artifact,
        "kind": "search",
        "results": results.len()
    }))
}

pub(super) fn read_jsonl_artifact(path: &Path) -> Result<(Value, Vec<Value>), String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("failed to read {}: {error}", path.display()))?;
    let mut values = Vec::new();
    for (index, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let value = serde_json::from_str::<Value>(line).map_err(|error| {
            format!(
                "failed to parse {} line {} as JSON: {error}",
                path.display(),
                index + 1
            )
        })?;
        values.push(value);
    }
    if values.is_empty() {
        return Err(format!("{} is empty", path.display()));
    }
    let summary = values.remove(0);
    Ok((summary, values))
}

pub(super) fn expect_summary_field(
    findings: &mut Vec<Value>,
    artifact: &str,
    summary: &Value,
    field: &str,
    expected: &str,
) {
    if summary.get(field).and_then(Value::as_str) != Some(expected) {
        push_output_finding(
            findings,
            artifact,
            "error",
            "summary",
            &format!("summary field {field} must equal {expected}"),
        );
    }
}

pub(super) fn check_result_count(
    findings: &mut Vec<Value>,
    artifact: &str,
    summary: &Value,
    actual_count: usize,
) {
    if summary.get("result_count").and_then(Value::as_u64) != Some(actual_count as u64) {
        push_output_finding(
            findings,
            artifact,
            "error",
            "summary",
            "summary result_count must match JSONL result rows",
        );
    }
}

pub(super) fn check_rank_score(
    findings: &mut Vec<Value>,
    artifact: &str,
    context: &str,
    result: &Value,
    score_field: &str,
) {
    if result.get("rank").and_then(Value::as_u64).unwrap_or(0) == 0 {
        push_output_finding(
            findings,
            artifact,
            "error",
            context,
            "rank must be positive",
        );
    }
    let Some(score) = result.get(score_field).and_then(Value::as_f64) else {
        push_output_finding(
            findings,
            artifact,
            "error",
            context,
            &format!("{score_field} must be present"),
        );
        return;
    };
    if !(0.0..=1.000_001).contains(&score) {
        push_output_finding(
            findings,
            artifact,
            "error",
            context,
            &format!("{score_field} must be in [0, 1]"),
        );
    }
}

pub(super) fn json_str(value: &Value, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string()
}

pub(super) fn push_output_finding(
    findings: &mut Vec<Value>,
    artifact: &str,
    severity: &str,
    context: &str,
    message: &str,
) {
    findings.push(json!({
        "artifact": artifact,
        "severity": severity,
        "context": context,
        "message": message
    }));
}
