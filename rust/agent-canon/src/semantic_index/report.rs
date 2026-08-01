// @dependency-start
// contract implementation
// responsibility Owns semantic-index text, JSON, JSONL schemas, serialization, and direct report writes.
// upstream design ../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../tools/catalog.yaml command catalog and public command source
// downstream implementation ../../../../tools/agent_tools/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use super::args::{
    ContextPackArgs, DiscourseRelationsArgs, NaturalRelationsArgs, OutputFormat,
    ResponsibilityTreeArgs, SearchArgs, SimilarArgs, SimilarKind, ThinDocsArgs,
};
use super::model::{responsibility_scope_bucket, ScoredNode};
use super::query::{
    ContextCell, DirectoryCoverage, DirectoryResponsibilityNode, ResponsibilityTreeReport,
    SearchResults,
};
use super::relations::{
    merge_candidate_bucket, merge_candidate_surface_kind, DiscourseRelation, NaturalRelation,
    SimilarPair, ThinDocCandidate, ThinDocMetrics,
};
use serde_json::{json, Value};
use std::fs;
use std::path::Path;

pub(super) fn print_search_results(args: &SearchArgs, search_results: &SearchResults) {
    if args.format == OutputFormat::Json {
        println!(
            "{}",
            json!({
                "semantic_index_search": "ok",
                "query": args.query,
                "stale_path_count": search_results.stale_path_count,
                "results": search_results.results.iter().map(scored_node_json).collect::<Vec<_>>()
            })
        );
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_search": "ok",
                "query_chars": args.query.chars().count(),
                "result_count": search_results.results.len(),
                "stale_path_count": search_results.stale_path_count
            })
        );
        for result in &search_results.results {
            println!("{}", scored_node_json(result));
        }
        return;
    }
    println!("SEMANTIC_INDEX_SEARCH=ok");
    println!(
        "SEMANTIC_INDEX_STALE_PATHS_SKIPPED={}",
        search_results.stale_path_count
    );
    for result in &search_results.results {
        println!(
            "rank={} score={:.4} path={} lines={}-{} kind={}",
            result.rank,
            result.score,
            result.node.path,
            result.node.line_start,
            result.node.line_end,
            result.node.kind
        );
    }
}

pub(super) fn print_context_pack_results(args: &ContextPackArgs, cells: &[ContextCell]) {
    if args.format == OutputFormat::Json {
        println!(
            "{}",
            json!({
                "semantic_index_context_pack": "ok",
                "query_chars": args.query.chars().count(),
                "provider": args.provider,
                "model": args.model,
                "max_cells": args.max_cells,
                "max_cell_chars": args.max_cell_chars,
                "max_total_chars": args.max_total_chars,
                "cell_count": cells.len(),
                "cells": cells.iter().map(context_cell_json).collect::<Vec<_>>()
            })
        );
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_context_pack": "ok",
                "query_chars": args.query.chars().count(),
                "provider": args.provider,
                "model": args.model,
                "cell_count": cells.len()
            })
        );
        for cell in cells {
            println!("{}", context_cell_json(cell));
        }
        return;
    }
    println!("SEMANTIC_INDEX_CONTEXT_PACK=ok");
    println!("SEMANTIC_INDEX_CONTEXT_PACK_CELLS={}", cells.len());
    for cell in cells {
        println!(
            "CELL rank={} score={:.4} responsibility={} path={} lines={}-{} kind={} chars={}",
            cell.rank,
            cell.score,
            cell.responsibility_bucket,
            cell.path,
            cell.line_start,
            cell.line_end,
            cell.node_kind,
            cell.excerpt.chars().count()
        );
        println!("EXCERPT_BEGIN");
        println!("{}", cell.excerpt);
        println!("EXCERPT_END");
    }
}

pub(super) fn print_responsibility_tree_results(
    args: &ResponsibilityTreeArgs,
    report: &ResponsibilityTreeReport,
    value: &Value,
) {
    if args.format == OutputFormat::Json {
        println!("{value}");
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_responsibility_tree": "ok",
                "provider": report.provider,
                "model": report.model,
                "dim": report.dim,
                "node_kind": report.node_kind,
                "directory_count_total": report.directory_count_total,
                "directory_count_returned": report.directories.len(),
                "coverage_status": report.coverage.status,
                "missing_directories": report.coverage.missing_directories.len(),
                "stale_directories": report.coverage.stale_directories.len()
            })
        );
        for directory in &report.directories {
            println!("{}", directory_node_json(directory, report.include_vector));
        }
        return;
    }
    println!("SEMANTIC_INDEX_RESPONSIBILITY_TREE=ok");
    println!(
        "SEMANTIC_INDEX_RESPONSIBILITY_TREE_DB={}",
        report.db.display()
    );
    println!(
        "SEMANTIC_INDEX_RESPONSIBILITY_TREE_DIRECTORIES={}",
        report.directory_count_total
    );
    println!(
        "SEMANTIC_INDEX_RESPONSIBILITY_TREE_RETURNED={}",
        report.directories.len()
    );
    println!(
        "SEMANTIC_INDEX_RESPONSIBILITY_TREE_COVERAGE={}",
        report.coverage.status
    );
    println!(
        "SEMANTIC_INDEX_RESPONSIBILITY_TREE_MISSING_DIRS={}",
        report.coverage.missing_directories.len()
    );
    println!(
        "SEMANTIC_INDEX_RESPONSIBILITY_TREE_STALE_DIRS={}",
        report.coverage.stale_directories.len()
    );
    if let Some(path) = &args.report {
        println!(
            "SEMANTIC_INDEX_RESPONSIBILITY_TREE_REPORT={}",
            path.display()
        );
    }
    for directory in &report.directories {
        let parent_similarity = directory
            .parent_similarity
            .map(|value| format!("{value:.4}"))
            .unwrap_or_else(|| "none".to_string());
        println!(
            "DIR path={} parent={} depth={} files={} nodes={} responsibility={} share={:.3} parent_similarity={} vector_hash={}",
            directory.path,
            directory.parent.as_deref().unwrap_or("none"),
            directory.depth,
            directory.file_count,
            directory.node_count,
            directory.dominant_responsibility,
            directory.dominant_share,
            parent_similarity,
            directory.vector_hash
        );
    }
}

pub(super) fn print_similar_results(args: &SimilarArgs, pairs: &[SimilarPair]) {
    let status = match args.kind {
        SimilarKind::Similar => "SEMANTIC_INDEX_SIMILAR=ok",
        SimilarKind::MergeCandidates => "SEMANTIC_INDEX_MERGE_CANDIDATES=ok",
    };
    if args.format == OutputFormat::Json {
        println!(
            "{}",
            json!({
                "semantic_index_pairs": "ok",
                "kind": match args.kind {
                    SimilarKind::Similar => "similar",
                    SimilarKind::MergeCandidates => "merge-candidates",
                },
                "results": pairs.iter().map(pair_json).collect::<Vec<_>>()
            })
        );
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_pairs": "ok",
                "kind": match args.kind {
                    SimilarKind::Similar => "similar",
                    SimilarKind::MergeCandidates => "merge-candidates",
                },
                "result_count": pairs.len()
            })
        );
        for pair in pairs {
            println!("{}", pair_json(pair));
        }
        return;
    }
    println!("{status}");
    for pair in pairs {
        let left_responsibility = responsibility_scope_bucket(&pair.left.path);
        let right_responsibility = responsibility_scope_bucket(&pair.right.path);
        let candidate_bucket = merge_candidate_bucket(&pair.left)
            .filter(|bucket| {
                merge_candidate_bucket(&pair.right)
                    .as_ref()
                    .is_some_and(|right_bucket| right_bucket == bucket)
            })
            .unwrap_or_else(|| "similar:any".to_string());
        println!(
            "rank={} score={:.4} responsibility={} same_responsibility={} candidate_bucket={} left={}:{}-{} right={}:{}-{}",
            pair.rank,
            pair.score,
            left_responsibility,
            left_responsibility == right_responsibility,
            candidate_bucket,
            pair.left.path,
            pair.left.line_start,
            pair.left.line_end,
            pair.right.path,
            pair.right.line_start,
            pair.right.line_end
        );
    }
}

pub(super) fn print_thin_docs_results(args: &ThinDocsArgs, candidates: &[ThinDocCandidate]) {
    if args.format == OutputFormat::Json {
        println!(
            "{}",
            json!({
                "semantic_index_thin_docs": "ok",
                "results": candidates.iter().map(thin_doc_json).collect::<Vec<_>>()
            })
        );
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_thin_docs": "ok",
                "result_count": candidates.len()
            })
        );
        for candidate in candidates {
            println!("{}", thin_doc_json(candidate));
        }
        return;
    }
    println!("SEMANTIC_INDEX_THIN_DOCS=ok");
    for candidate in candidates {
        let target = candidate
            .best_match
            .as_ref()
            .map(|neighbor| {
                format!(
                    "{}:{}-{}:{:.4}",
                    neighbor.node.path,
                    neighbor.node.line_start,
                    neighbor.node.line_end,
                    neighbor.score
                )
            })
            .unwrap_or_else(|| "none".to_string());
        println!(
            "rank={} thin_score={:.4} action={} path={} lines={}-{} target={} reasons={}",
            candidate.rank,
            candidate.thin_score,
            candidate.action,
            candidate.node.path,
            candidate.node.line_start,
            candidate.node.line_end,
            target,
            candidate.reasons.join(",")
        );
    }
}

pub(super) fn print_natural_relation_results(
    args: &NaturalRelationsArgs,
    relations: &[NaturalRelation],
) {
    if args.format == OutputFormat::Json {
        println!(
            "{}",
            json!({
                "semantic_index_natural_relations": "ok",
                "min_similarity": args.min_similarity,
                "min_kind_of_score": args.min_kind_of_score,
                "results": relations.iter().map(natural_relation_json).collect::<Vec<_>>()
            })
        );
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_natural_relations": "ok",
                "min_similarity": args.min_similarity,
                "min_kind_of_score": args.min_kind_of_score,
                "result_count": relations.len()
            })
        );
        for relation in relations {
            println!("{}", natural_relation_json(relation));
        }
        return;
    }
    println!("SEMANTIC_INDEX_NATURAL_RELATIONS=ok");
    for relation in relations {
        println!(
            "rank={} relation={} similarity={:.4} left_kind_of_right={:.4} right_kind_of_left={:.4} left={}:{}-{} right={}:{}-{}",
            relation.rank,
            relation.relation_kind,
            relation.similarity_score,
            relation.left_is_kind_of_right_score,
            relation.right_is_kind_of_left_score,
            relation.left.path,
            relation.left.line_start,
            relation.left.line_end,
            relation.right.path,
            relation.right.line_start,
            relation.right.line_end
        );
    }
}

pub(super) fn print_discourse_relation_results(
    args: &DiscourseRelationsArgs,
    relations: &[DiscourseRelation],
) {
    if args.format == OutputFormat::Json {
        println!(
            "{}",
            json!({
                "semantic_index_discourse_relations": "ok",
                "profile": args.profile,
                "min_naturalness": args.min_naturalness,
                "window": args.window,
                "results": relations.iter().map(discourse_relation_json).collect::<Vec<_>>()
            })
        );
        return;
    }
    if args.format == OutputFormat::Jsonl {
        println!(
            "{}",
            json!({
                "semantic_index_discourse_relations": "ok",
                "profile": args.profile,
                "min_naturalness": args.min_naturalness,
                "window": args.window,
                "result_count": relations.len()
            })
        );
        for relation in relations {
            println!("{}", discourse_relation_json(relation));
        }
        return;
    }
    println!("SEMANTIC_INDEX_DISCOURSE_RELATIONS=ok");
    println!("SEMANTIC_INDEX_DISCOURSE_PROFILE={}", args.profile);
    for relation in relations {
        println!(
            "rank={} family={} schema={} phrase={} inverse={} naturalness={:.4} direction={} confidence={:.4} ambiguity={} left={}:{}-{} right={}:{}-{} flags={}",
            relation.rank,
            relation.relation_family,
            relation.relation_schema,
            relation.surface_phrase,
            relation
                .inverse_surface_phrase
                .as_deref()
                .unwrap_or("none"),
            relation.naturalness_score,
            relation.logical_direction,
            relation.direction_confidence,
            relation.ambiguity,
            relation.left.path,
            relation.left.line_start,
            relation.left.line_end,
            relation.right.path,
            relation.right.line_start,
            relation.right.line_end,
            relation.gap_flags.join(",")
        );
    }
}

pub(super) fn print_eval_summary(report: &Value) {
    println!(
        "SEMANTIC_INDEX_EVAL={}",
        report
            .get("semantic_index_eval")
            .and_then(Value::as_str)
            .unwrap_or("unknown")
    );
    if let Some(build) = report.get("build") {
        println!(
            "SEMANTIC_INDEX_EVAL_FILES={}",
            build
                .get("indexed_files")
                .and_then(Value::as_u64)
                .unwrap_or(0)
        );
        println!(
            "SEMANTIC_INDEX_EVAL_NODES={}",
            build
                .get("indexed_nodes")
                .and_then(Value::as_u64)
                .unwrap_or(0)
        );
    }
    for key in ["search", "similarity", "must_not_pairs"] {
        if let Some(section) = report.get(key) {
            println!(
                "SEMANTIC_INDEX_EVAL_{}_FAILED={}",
                key.to_ascii_uppercase(),
                section.get("failed").and_then(Value::as_u64).unwrap_or(0)
            );
        }
    }
}

pub(super) fn print_output_eval_summary(report: &Value) {
    println!(
        "SEMANTIC_INDEX_OUTPUT_EVAL={}",
        report
            .get("semantic_index_output_eval")
            .and_then(Value::as_str)
            .unwrap_or("unknown")
    );
    println!(
        "SEMANTIC_INDEX_OUTPUT_EVAL_ERRORS={}",
        report
            .get("error_count")
            .and_then(Value::as_u64)
            .unwrap_or(0)
    );
    println!(
        "SEMANTIC_INDEX_OUTPUT_EVAL_ARTIFACTS={}",
        report
            .get("artifacts")
            .and_then(Value::as_array)
            .map(Vec::len)
            .unwrap_or(0)
    );
}

pub(super) fn print_provider_compare_summary(report: &Value) {
    println!(
        "SEMANTIC_INDEX_PROVIDER_COMPARE={}",
        report
            .get("semantic_index_provider_compare")
            .and_then(Value::as_str)
            .unwrap_or("unknown")
    );
    if let Some(left) = report.get("left") {
        println!(
            "SEMANTIC_INDEX_PROVIDER_COMPARE_LEFT={}:{}:{}",
            left.get("provider").and_then(Value::as_str).unwrap_or(""),
            left.get("model").and_then(Value::as_str).unwrap_or(""),
            left.get("dim").and_then(Value::as_u64).unwrap_or(0)
        );
    }
    if let Some(right) = report.get("right") {
        println!(
            "SEMANTIC_INDEX_PROVIDER_COMPARE_RIGHT={}:{}:{}",
            right.get("provider").and_then(Value::as_str).unwrap_or(""),
            right.get("model").and_then(Value::as_str).unwrap_or(""),
            right.get("dim").and_then(Value::as_u64).unwrap_or(0)
        );
    }
    if let Some(merge) = report.get("merge_candidates") {
        println!(
            "SEMANTIC_INDEX_PROVIDER_COMPARE_MERGE_OVERLAP={:.4}",
            merge
                .get("overlap_ratio")
                .and_then(Value::as_f64)
                .unwrap_or(0.0)
        );
    }
    if let Some(search) = report.get("search").filter(|value| !value.is_null()) {
        println!(
            "SEMANTIC_INDEX_PROVIDER_COMPARE_SEARCH_OVERLAP={:.4}",
            search
                .get("overlap_ratio")
                .and_then(Value::as_f64)
                .unwrap_or(0.0)
        );
    }
}

pub(super) fn scored_node_json(result: &ScoredNode) -> Value {
    json!({
        "rank": result.rank,
        "score": result.score,
        "path": result.node.path,
        "node_kind": result.node.kind,
        "line_start": result.node.line_start,
        "line_end": result.node.line_end
    })
}

pub(super) fn responsibility_tree_report_json(report: &ResponsibilityTreeReport) -> Value {
    json!({
        "semantic_index_responsibility_tree": "ok",
        "root": report.root.display().to_string(),
        "db": report.db.display().to_string(),
        "provider": report.provider,
        "model": report.model,
        "dim": report.dim,
        "node_kind": report.node_kind,
        "directory_count_total": report.directory_count_total,
        "directory_count_returned": report.directories.len(),
        "include_vector": report.include_vector,
        "coverage": coverage_json(&report.coverage),
        "directories": report
            .directories
            .iter()
            .map(|directory| directory_node_json(directory, report.include_vector))
            .collect::<Vec<_>>()
    })
}

pub(super) fn coverage_json(coverage: &DirectoryCoverage) -> Value {
    json!({
        "status": coverage.status,
        "expected_directory_count": coverage.expected_directories.len(),
        "db_directory_count": coverage.db_directories.len(),
        "missing_directory_count": coverage.missing_directories.len(),
        "stale_directory_count": coverage.stale_directories.len(),
        "repo_tree_directories": coverage.expected_directories,
        "db_tree_directories": coverage.db_directories,
        "missing_directories": coverage.missing_directories,
        "stale_directories": coverage.stale_directories
    })
}

pub(super) fn directory_node_json(
    directory: &DirectoryResponsibilityNode,
    include_vector: bool,
) -> Value {
    let mut value = json!({
        "path": directory.path,
        "parent": directory.parent,
        "depth": directory.depth,
        "file_count": directory.file_count,
        "node_count": directory.node_count,
        "vector_dim": directory.vector.len(),
        "vector_hash": directory.vector_hash,
        "dominant_responsibility": directory.dominant_responsibility,
        "dominant_share": directory.dominant_share,
        "responsibility_counts": counts_json(&directory.responsibility_counts),
        "node_kind_counts": counts_json(&directory.node_kind_counts),
        "parent_similarity": directory.parent_similarity
    });
    if include_vector {
        value["vector"] = json!(directory.vector);
    }
    value
}

pub(super) fn counts_json(counts: &[(String, usize)]) -> Value {
    let mut object = serde_json::Map::new();
    for (key, value) in counts {
        object.insert(key.clone(), json!(value));
    }
    Value::Object(object)
}

pub(super) fn context_cell_json(cell: &ContextCell) -> Value {
    json!({
        "rank": cell.rank,
        "score": cell.score,
        "path": cell.path,
        "node_kind": cell.node_kind,
        "line_start": cell.line_start,
        "line_end": cell.line_end,
        "responsibility_bucket": cell.responsibility_bucket,
        "excerpt_chars": cell.excerpt.chars().count(),
        "excerpt": cell.excerpt
    })
}

pub(super) fn pair_json(pair: &SimilarPair) -> Value {
    let left_responsibility = responsibility_scope_bucket(&pair.left.path);
    let right_responsibility = responsibility_scope_bucket(&pair.right.path);
    let left_candidate_bucket = merge_candidate_bucket(&pair.left);
    let right_candidate_bucket = merge_candidate_bucket(&pair.right);
    let candidate_bucket = if left_candidate_bucket == right_candidate_bucket {
        left_candidate_bucket
    } else {
        None
    };
    json!({
        "rank": pair.rank,
        "score": pair.score,
        "same_responsibility": left_responsibility == right_responsibility,
        "candidate_bucket": candidate_bucket,
        "left": {
            "path": pair.left.path,
            "responsibility_bucket": left_responsibility,
            "node_kind": pair.left.kind,
            "line_start": pair.left.line_start,
            "line_end": pair.left.line_end
        },
        "right": {
            "path": pair.right.path,
            "responsibility_bucket": right_responsibility,
            "node_kind": pair.right.kind,
            "line_start": pair.right.line_start,
            "line_end": pair.right.line_end
        }
    })
}

pub(super) fn thin_doc_json(candidate: &ThinDocCandidate) -> Value {
    json!({
        "rank": candidate.rank,
        "thin_score": candidate.thin_score,
        "action": candidate.action,
        "reasons": candidate.reasons,
        "path": candidate.node.path,
        "node_kind": candidate.node.kind,
        "line_start": candidate.node.line_start,
        "line_end": candidate.node.line_end,
        "best_match": candidate.best_match.as_ref().map(|neighbor| {
            json!({
                "path": neighbor.node.path,
                "score": neighbor.score,
                "node_kind": neighbor.node.kind,
                "line_start": neighbor.node.line_start,
                "line_end": neighbor.node.line_end
            })
        }),
        "metrics": thin_doc_metrics_json(&candidate.metrics)
    })
}

pub(super) fn natural_relation_json(relation: &NaturalRelation) -> Value {
    json!({
        "rank": relation.rank,
        "relation_kind": relation.relation_kind,
        "similarity_score": relation.similarity_score,
        "left_is_kind_of_right_score": relation.left_is_kind_of_right_score,
        "right_is_kind_of_left_score": relation.right_is_kind_of_left_score,
        "left": {
            "path": relation.left.path,
            "responsibility_bucket": responsibility_scope_bucket(&relation.left.path),
            "surface_kind": merge_candidate_surface_kind(&relation.left.path),
            "node_kind": relation.left.kind,
            "line_start": relation.left.line_start,
            "line_end": relation.left.line_end
        },
        "right": {
            "path": relation.right.path,
            "responsibility_bucket": responsibility_scope_bucket(&relation.right.path),
            "surface_kind": merge_candidate_surface_kind(&relation.right.path),
            "node_kind": relation.right.kind,
            "line_start": relation.right.line_start,
            "line_end": relation.right.line_end
        }
    })
}

pub(super) fn discourse_relation_json(relation: &DiscourseRelation) -> Value {
    json!({
        "rank": relation.rank,
        "connective_profile": relation.connective_profile,
        "relation_family": relation.relation_family,
        "relation_schema": relation.relation_schema,
        "surface_phrase": relation.surface_phrase,
        "inverse_surface_phrase": relation.inverse_surface_phrase,
        "surface_order": relation.surface_order,
        "logical_direction": relation.logical_direction,
        "similarity_score": relation.similarity_score,
        "naturalness_score": relation.naturalness_score,
        "inverse_naturalness_score": relation.inverse_naturalness_score,
        "direction_confidence": relation.direction_confidence,
        "ambiguity": relation.ambiguity,
        "gap_flags": relation.gap_flags,
        "left": {
            "path": relation.left.path,
            "responsibility_bucket": responsibility_scope_bucket(&relation.left.path),
            "node_kind": relation.left.kind,
            "line_start": relation.left.line_start,
            "line_end": relation.left.line_end
        },
        "right": {
            "path": relation.right.path,
            "responsibility_bucket": responsibility_scope_bucket(&relation.right.path),
            "node_kind": relation.right.kind,
            "line_start": relation.right.line_start,
            "line_end": relation.right.line_end
        }
    })
}

pub(super) fn thin_doc_metrics_json(metrics: &ThinDocMetrics) -> Value {
    json!({
        "total_lines": metrics.total_lines,
        "meaningful_lines": metrics.meaningful_lines,
        "link_lines": metrics.link_lines,
        "wrapper_phrase_hits": metrics.wrapper_phrase_hits,
        "link_density": metrics.link_density
    })
}

pub(super) fn write_report(path: &Path, report: &Value) -> Result<(), String> {
    ensure_parent_dir(path)?;
    fs::write(path, format!("{}\n", report)).map_err(|error| error.to_string())
}

pub(super) fn write_pretty_report(path: &Path, report: &Value) -> Result<(), String> {
    ensure_parent_dir(path)?;
    let text = serde_json::to_string_pretty(report).map_err(|error| error.to_string())?;
    fs::write(path, format!("{text}\n")).map_err(|error| error.to_string())
}

pub(super) fn ensure_parent_dir(path: &Path) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    Ok(())
}
