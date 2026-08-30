// @dependency-start
// contract implementation
// responsibility Owns semantic-index pair, thin-document, natural-relation, and discourse analysis.
// upstream design ../../../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../../catalog.yaml command catalog and public command source
// downstream implementation ../../../../../repository/github/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use super::args::{
    DiscourseRelationsArgs, NaturalRelationsArgs, SimilarArgs, SimilarKind, ThinDocsArgs,
    DEFAULT_DISCOURSE_PROFILE,
};
use super::embedding::{
    all_signed_features, cosine_score, prefix_features, strip_dependency_manifest, text_tokens,
    DEFAULT_REMOTE_EMBEDDING_MAX_CHARS, DISCOURSE_TEXT_CHARS, NATURAL_RELATION_FEATURE_FANOUT,
};
use super::model::{count_lines, responsibility_scope_bucket, IndexedNode};
use super::source::context_excerpt;
use super::storage::{
    load_nodes, open_cache_connection, resolve_provider_dim, validate_analysis_db,
};
use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;

#[derive(Debug, Clone)]
pub(super) struct SimilarPair {
    pub(super) left: IndexedNode,
    pub(super) right: IndexedNode,
    pub(super) score: f32,
    pub(super) rank: usize,
}

#[derive(Debug, Clone)]
pub(super) struct ThinDocNeighbor {
    pub(super) node: IndexedNode,
    pub(super) score: f32,
}

#[derive(Debug, Clone)]
pub(super) struct ThinDocMetrics {
    pub(super) total_lines: usize,
    pub(super) meaningful_lines: usize,
    pub(super) link_lines: usize,
    pub(super) wrapper_phrase_hits: usize,
    pub(super) link_density: f32,
}

#[derive(Debug, Clone)]
pub(super) struct ThinDocCandidate {
    pub(super) node: IndexedNode,
    pub(super) thin_score: f32,
    pub(super) rank: usize,
    pub(super) action: String,
    pub(super) reasons: Vec<String>,
    pub(super) best_match: Option<ThinDocNeighbor>,
    pub(super) metrics: ThinDocMetrics,
}

#[derive(Debug, Clone)]
pub(super) struct NaturalRelation {
    pub(super) left: IndexedNode,
    pub(super) right: IndexedNode,
    pub(super) similarity_score: f32,
    pub(super) left_is_kind_of_right_score: f32,
    pub(super) right_is_kind_of_left_score: f32,
    pub(super) relation_kind: String,
    pub(super) rank: usize,
}

#[derive(Debug, Clone)]
pub(super) struct DiscourseRelation {
    pub(super) left: IndexedNode,
    pub(super) right: IndexedNode,
    pub(super) similarity_score: f32,
    pub(super) connective_profile: String,
    pub(super) relation_family: String,
    pub(super) relation_schema: String,
    pub(super) surface_phrase: String,
    pub(super) inverse_surface_phrase: Option<String>,
    pub(super) surface_order: String,
    pub(super) logical_direction: String,
    pub(super) naturalness_score: f32,
    pub(super) inverse_naturalness_score: Option<f32>,
    pub(super) direction_confidence: f32,
    pub(super) ambiguity: String,
    pub(super) gap_flags: Vec<String>,
    pub(super) rank: usize,
}

#[derive(Debug, Clone)]
pub(super) struct DiscourseRealization {
    relation_family: &'static str,
    relation_schema: &'static str,
    surface_phrase: &'static str,
    inverse_surface_phrase: Option<&'static str>,
    surface_order: &'static str,
    logical_direction: &'static str,
    profile_boost: f32,
}

pub(super) const MERGE_CANDIDATE_MIN_LINES: i64 = 4;

pub(super) fn is_merge_candidate_node(node: &IndexedNode) -> bool {
    if node.kind != "document" && node.kind != "section" {
        return false;
    }
    let line_count = node.line_end.saturating_sub(node.line_start) + 1;
    line_count >= MERGE_CANDIDATE_MIN_LINES
}

pub(super) fn merge_candidate_bucket(node: &IndexedNode) -> Option<String> {
    let path = node.path.replace('\\', "/");
    if is_alignment_or_log_surface(&path) {
        return None;
    }
    let surface = merge_candidate_surface_kind(&path)?;
    let responsibility = responsibility_scope_bucket(&path);
    let topic = match surface {
        "docs" => document_responsibility_bucket(&path).to_string(),
        _ => Path::new(&path)
            .extension()
            .and_then(|part| part.to_str())
            .unwrap_or("none")
            .to_ascii_lowercase(),
    };
    Some(format!("{surface}:{responsibility}:{topic}"))
}

pub(super) fn merge_candidate_surface_kind(path: &str) -> Option<&'static str> {
    let extension = Path::new(&path)
        .extension()
        .and_then(|part| part.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    match extension.as_str() {
        "md" | "markdown" | "txt" | "rst" => Some("docs"),
        "rs" | "py" | "sh" | "sql" => Some("code"),
        "toml" | "yaml" | "yml" | "json" | "jsonl" => Some("config"),
        _ => None,
    }
}

pub(super) fn is_alignment_or_log_surface(path: &str) -> bool {
    path.starts_with("agents/evals/results/")
        || path.starts_with("reports/")
        || path.starts_with(".agent-canon/")
        || path.starts_with(".codex/personal/skills/")
        || path.starts_with("templates/agents/_partials/")
        || path.starts_with("codex-cli-guide/source/")
        || path.starts_with("codex-cli-guide/sections/")
}

pub(super) fn is_document_text_path(path: &str) -> bool {
    let extension = Path::new(path)
        .extension()
        .and_then(|part| part.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    matches!(extension.as_str(), "md" | "markdown" | "txt" | "rst")
}

pub(super) fn is_thin_doc_protected_surface(path: &str) -> bool {
    path == "README.md"
        || path == "AGENTS.md"
        || path == "ROOT_AGENTS.md"
        || path.ends_with("/README.md")
        || path.starts_with(".github/")
        || path.starts_with(".codex/")
}

pub(super) fn is_thin_doc_non_candidate_surface(path: &str) -> bool {
    path.starts_with("templates/agents/") || path.starts_with("tests/fixtures/")
}

pub(super) fn document_responsibility_bucket(path: &str) -> &'static str {
    if path == "README.md" || path.ends_with("/README.md") {
        return "readme";
    }
    if path.starts_with("agents/skills/") {
        return "skill";
    }
    if path.starts_with("agents/workflows/") {
        return "workflow";
    }
    if path.starts_with("documents/tools/") {
        return "tool-doc";
    }
    if path.starts_with("documents/") {
        return "document";
    }
    if path.starts_with("documents/notes/knowledge/") {
        return "knowledge-note";
    }
    if path.starts_with("documents/notes/") {
        return "note";
    }
    if path.starts_with("references/") {
        return "reference";
    }
    if path.starts_with("tests/fixtures/") {
        return "fixture";
    }
    if path.starts_with(".github/") {
        return "github";
    }
    "general"
}

pub(super) fn similar_pairs(args: &SimilarArgs) -> Result<Vec<SimilarPair>, String> {
    validate_analysis_db(&args.root, &args.db)?;
    let conn = open_cache_connection(&args.db)?;
    let dim = resolve_provider_dim(&conn, &args.provider, &args.model, args.dim)?;
    let nodes = load_nodes(&conn, &args.provider, &args.model, dim)?;
    Ok(similar_pairs_from_nodes(
        &nodes,
        args.kind,
        args.min_score,
        args.top_k,
        args.cross_file_only,
    ))
}

pub(super) fn similar_pairs_from_nodes(
    nodes: &[IndexedNode],
    kind: SimilarKind,
    min_score: f32,
    top_k: usize,
    cross_file_only: bool,
) -> Vec<SimilarPair> {
    let mut bucket_ids: HashMap<String, usize> = HashMap::new();
    let mut buckets: Vec<Option<usize>> = Vec::with_capacity(nodes.len());
    for node in nodes {
        let bucket = comparison_bucket(kind, node);
        let bucket_id = bucket.map(|value| {
            let next_id = bucket_ids.len();
            *bucket_ids.entry(value).or_insert(next_id)
        });
        buckets.push(bucket_id);
    }
    let mut pairs: Vec<SimilarPair> = Vec::new();
    let mut inverted: HashMap<(usize, usize, bool), Vec<usize>> = HashMap::new();
    let prune_limit = top_k.saturating_mul(16).max(1024);
    for right_index in 0..nodes.len() {
        let right = &nodes[right_index];
        let Some(bucket) = buckets[right_index] else {
            continue;
        };
        let mut candidates: HashSet<usize> = HashSet::new();
        for (index, sign) in prefix_features(&right.vector, min_score) {
            if let Some(indices) = inverted.get(&(bucket, index, sign)) {
                candidates.extend(indices.iter().copied());
            }
        }
        for left_index in candidates {
            let left = &nodes[left_index];
            if cross_file_only && left.file_id == right.file_id {
                continue;
            }
            let score = cosine_score(&left.vector, &right.vector);
            if score + f32::EPSILON >= min_score {
                pairs.push(SimilarPair {
                    left: left.clone(),
                    right: right.clone(),
                    score,
                    rank: 0,
                });
                if pairs.len() > prune_limit {
                    sort_pairs(&mut pairs);
                    pairs.truncate(top_k);
                }
            }
        }
        for (index, sign) in all_signed_features(&right.vector) {
            inverted
                .entry((bucket, index, sign))
                .or_default()
                .push(right_index);
        }
    }
    sort_pairs(&mut pairs);
    pairs.truncate(top_k);
    for (index, pair) in pairs.iter_mut().enumerate() {
        pair.rank = index + 1;
    }
    pairs
}

pub(super) fn thin_docs(args: &ThinDocsArgs) -> Result<Vec<ThinDocCandidate>, String> {
    validate_analysis_db(&args.root, &args.db)?;
    let conn = open_cache_connection(&args.db)?;
    let dim = resolve_provider_dim(&conn, &args.provider, &args.model, args.dim)?;
    let nodes = load_nodes(&conn, &args.provider, &args.model, dim)?;
    let document_nodes: Vec<IndexedNode> = nodes
        .into_iter()
        .filter(|node| node.kind == "document")
        .filter(|node| is_document_text_path(&node.path))
        .filter(|node| !is_alignment_or_log_surface(&node.path))
        .filter(|node| !is_thin_doc_non_candidate_surface(&node.path))
        .collect();
    let mut candidates = Vec::new();
    for node in &document_nodes {
        let metrics = thin_doc_metrics(&args.root, &node.path);
        if !has_thin_doc_shape(&metrics) {
            continue;
        }
        let best_match = best_thin_doc_neighbor(node, &document_nodes, args.min_neighbor_score);
        let best_score = best_match
            .as_ref()
            .map(|neighbor| neighbor.score)
            .unwrap_or(0.0);
        let protected = is_thin_doc_protected_surface(&node.path);
        let mut reasons = thin_doc_reasons(&metrics, best_score, args.min_neighbor_score);
        if protected {
            reasons.push("protected_entrypoint".to_string());
        }
        let thin_score = thin_doc_score(&metrics, best_score, args.min_neighbor_score);
        if thin_score + f32::EPSILON < args.min_thin_score {
            continue;
        }
        candidates.push(ThinDocCandidate {
            node: node.clone(),
            thin_score,
            rank: 0,
            action: thin_doc_action(&metrics, best_score, args.min_neighbor_score, protected),
            reasons,
            best_match,
            metrics,
        });
    }
    sort_thin_docs(&mut candidates);
    candidates.truncate(args.top_k);
    for (index, candidate) in candidates.iter_mut().enumerate() {
        candidate.rank = index + 1;
    }
    Ok(candidates)
}

pub(super) fn natural_relations(
    args: &NaturalRelationsArgs,
) -> Result<Vec<NaturalRelation>, String> {
    validate_analysis_db(&args.root, &args.db)?;
    let conn = open_cache_connection(&args.db)?;
    let dim = resolve_provider_dim(&conn, &args.provider, &args.model, args.dim)?;
    let nodes: Vec<IndexedNode> = load_nodes(&conn, &args.provider, &args.model, dim)?
        .into_iter()
        .filter(is_natural_relation_node)
        .collect();
    let pairs = natural_relation_candidate_pairs_from_nodes(&nodes, args);
    let mut term_cache: HashMap<i64, Vec<String>> = HashMap::new();
    let mut relations = Vec::new();
    for pair in pairs {
        let left_terms = relation_terms_for_node(args, &pair.left, &mut term_cache)?;
        let right_terms = relation_terms_for_node(args, &pair.right, &mut term_cache)?;
        let left_is_kind_of_right = directed_kind_of_score(&left_terms, &right_terms, pair.score);
        let right_is_kind_of_left = directed_kind_of_score(&right_terms, &left_terms, pair.score);
        let relation_kind = classify_natural_relation(
            left_is_kind_of_right,
            right_is_kind_of_left,
            args.min_kind_of_score,
        )
        .to_string();
        relations.push(NaturalRelation {
            left: pair.left,
            right: pair.right,
            similarity_score: pair.score,
            left_is_kind_of_right_score: left_is_kind_of_right,
            right_is_kind_of_left_score: right_is_kind_of_left,
            relation_kind,
            rank: 0,
        });
    }
    sort_natural_relations(&mut relations);
    relations.truncate(args.top_k);
    for (index, relation) in relations.iter_mut().enumerate() {
        relation.rank = index + 1;
    }
    Ok(relations)
}

pub(super) fn natural_relation_candidate_pairs_from_nodes(
    nodes: &[IndexedNode],
    args: &NaturalRelationsArgs,
) -> Vec<SimilarPair> {
    let mut pairs: Vec<SimilarPair> = Vec::new();
    let mut inverted: HashMap<(usize, bool), Vec<usize>> = HashMap::new();
    let prune_limit = args.top_k.saturating_mul(64).max(1024);
    for right_index in 0..nodes.len() {
        let right = &nodes[right_index];
        let mut candidates: HashSet<usize> = HashSet::new();
        for (index, sign) in prefix_features(&right.vector, args.min_similarity) {
            if let Some(indices) = inverted.get(&(index, sign)) {
                candidates.extend(
                    indices
                        .iter()
                        .rev()
                        .take(NATURAL_RELATION_FEATURE_FANOUT)
                        .copied(),
                );
            }
        }
        for left_index in candidates {
            let left = &nodes[left_index];
            if args.cross_file_only && left.file_id == right.file_id {
                continue;
            }
            let score = cosine_score(&left.vector, &right.vector);
            if score + f32::EPSILON >= args.min_similarity {
                pairs.push(SimilarPair {
                    left: left.clone(),
                    right: right.clone(),
                    score,
                    rank: 0,
                });
                if pairs.len() > prune_limit {
                    sort_pairs(&mut pairs);
                    pairs.truncate(args.top_k.saturating_mul(16).max(args.top_k));
                }
            }
        }
        for (index, sign) in all_signed_features(&right.vector) {
            inverted.entry((index, sign)).or_default().push(right_index);
        }
    }
    sort_pairs(&mut pairs);
    pairs.truncate(args.top_k.saturating_mul(16).max(args.top_k));
    for (index, pair) in pairs.iter_mut().enumerate() {
        pair.rank = index + 1;
    }
    pairs
}

pub(super) fn discourse_relations(
    args: &DiscourseRelationsArgs,
) -> Result<Vec<DiscourseRelation>, String> {
    validate_analysis_db(&args.root, &args.db)?;
    let conn = open_cache_connection(&args.db)?;
    let dim = resolve_provider_dim(&conn, &args.provider, &args.model, args.dim)?;
    let mut nodes: Vec<IndexedNode> = load_nodes(&conn, &args.provider, &args.model, dim)?
        .into_iter()
        .filter(is_discourse_relation_node)
        .collect();
    nodes.sort_by(|left, right| {
        left.path
            .cmp(&right.path)
            .then_with(|| left.line_start.cmp(&right.line_start))
            .then_with(|| left.line_end.cmp(&right.line_end))
    });
    let pairs = discourse_candidate_pairs_from_nodes(&nodes, args.window);
    let mut text_cache: HashMap<i64, String> = HashMap::new();
    let mut relations = Vec::new();
    for pair in pairs {
        let left_text = discourse_text_for_node(args, &pair.left, &mut text_cache)?;
        let right_text = discourse_text_for_node(args, &pair.right, &mut text_cache)?;
        if let Some(mut relation) =
            score_discourse_pair(args, pair, left_text.as_str(), right_text.as_str())
        {
            if relation.naturalness_score + f32::EPSILON >= args.min_naturalness {
                relation.rank = 0;
                relations.push(relation);
            }
        }
    }
    sort_discourse_relations(&mut relations);
    relations.truncate(args.top_k);
    for (index, relation) in relations.iter_mut().enumerate() {
        relation.rank = index + 1;
    }
    Ok(relations)
}

pub(super) fn discourse_candidate_pairs_from_nodes(
    nodes: &[IndexedNode],
    window: usize,
) -> Vec<SimilarPair> {
    let mut grouped: HashMap<&str, Vec<&IndexedNode>> = HashMap::new();
    for node in nodes {
        grouped.entry(&node.path).or_default().push(node);
    }
    let mut pairs = Vec::new();
    for file_nodes in grouped.values_mut() {
        file_nodes.sort_by(|left, right| {
            left.line_start
                .cmp(&right.line_start)
                .then_with(|| left.line_end.cmp(&right.line_end))
        });
        for left_index in 0..file_nodes.len() {
            let max_right = (left_index + window + 1).min(file_nodes.len());
            for right in file_nodes.iter().take(max_right).skip(left_index + 1) {
                let left = file_nodes[left_index];
                let score = cosine_score(&left.vector, &right.vector);
                pairs.push(SimilarPair {
                    left: left.clone(),
                    right: (*right).clone(),
                    score,
                    rank: 0,
                });
            }
        }
    }
    pairs
}

pub(super) fn is_discourse_relation_node(node: &IndexedNode) -> bool {
    if is_alignment_or_log_surface(&node.path) {
        return false;
    }
    if !is_document_text_path(&node.path) {
        return false;
    }
    node.kind == "block"
}

pub(super) fn discourse_text_for_node(
    args: &DiscourseRelationsArgs,
    node: &IndexedNode,
    cache: &mut HashMap<i64, String>,
) -> Result<String, String> {
    if let Some(text) = cache.get(&node.node_id) {
        return Ok(text.clone());
    }
    let text = context_excerpt(&args.root, node, DISCOURSE_TEXT_CHARS)?;
    cache.insert(node.node_id, text.clone());
    Ok(text)
}

pub(super) fn score_discourse_pair(
    args: &DiscourseRelationsArgs,
    pair: SimilarPair,
    left_text: &str,
    right_text: &str,
) -> Option<DiscourseRelation> {
    let similarity_score = pair.score.max(0.0);
    let term_overlap = discourse_term_overlap(left_text, right_text);
    let mut best: Option<(DiscourseRealization, f32, f32, String, Vec<String>)> = None;
    for realization in discourse_realizations(&args.profile) {
        let surface_score = connective_surface_score(right_text, realization.surface_phrase);
        if surface_score <= 0.0 {
            continue;
        }
        let naturalness = (0.36 * similarity_score
            + 0.34 * surface_score
            + 0.18 * term_overlap
            + 0.12 * realization.profile_boost)
            .clamp(0.0, 1.0);
        let direction_confidence =
            discourse_direction_confidence(&realization, surface_score, term_overlap);
        let ambiguity = discourse_ambiguity(&realization, surface_score, right_text);
        let gap_flags = discourse_gap_flags(naturalness, direction_confidence, &ambiguity, true);
        if best
            .as_ref()
            .is_none_or(|(_, best_score, _, _, _)| naturalness > *best_score)
        {
            best = Some((
                realization,
                naturalness,
                direction_confidence,
                ambiguity,
                gap_flags,
            ));
        }
    }
    let (realization, naturalness_score, direction_confidence, ambiguity, gap_flags) = best
        .unwrap_or_else(|| {
            let naturalness =
                (0.62 * similarity_score + 0.26 * term_overlap + 0.12).clamp(0.0, 1.0);
            (
                implicit_discourse_realization(&args.profile),
                naturalness,
                0.55,
                "medium".to_string(),
                discourse_gap_flags(naturalness, 0.55, "medium", false),
            )
        });
    let inverse_naturalness_score = realization.inverse_surface_phrase.map(|_| {
        (naturalness_score
            * if realization.surface_phrase == "because" {
                1.02
            } else {
                0.96
            })
        .min(1.0)
    });
    Some(DiscourseRelation {
        left: pair.left,
        right: pair.right,
        similarity_score,
        connective_profile: args.profile.clone(),
        relation_family: realization.relation_family.to_string(),
        relation_schema: realization.relation_schema.to_string(),
        surface_phrase: realization.surface_phrase.to_string(),
        inverse_surface_phrase: realization.inverse_surface_phrase.map(str::to_string),
        surface_order: realization.surface_order.to_string(),
        logical_direction: realization.logical_direction.to_string(),
        naturalness_score,
        inverse_naturalness_score,
        direction_confidence,
        ambiguity,
        gap_flags,
        rank: 0,
    })
}

pub(super) fn discourse_realizations(profile: &str) -> Vec<DiscourseRealization> {
    let mut realizations = vec![
        DiscourseRealization {
            relation_family: "causal",
            relation_schema: "reason_to_result",
            surface_phrase: "therefore",
            inverse_surface_phrase: Some("because"),
            surface_order: "reason_then_result",
            logical_direction: "left_to_right",
            profile_boost: 0.72,
        },
        DiscourseRealization {
            relation_family: "causal",
            relation_schema: "reason_to_result",
            surface_phrase: "as a result",
            inverse_surface_phrase: Some("because"),
            surface_order: "reason_then_result",
            logical_direction: "left_to_right",
            profile_boost: 0.70,
        },
        DiscourseRealization {
            relation_family: "causal",
            relation_schema: "reason_to_result",
            surface_phrase: "because",
            inverse_surface_phrase: Some("therefore"),
            surface_order: "result_then_reason",
            logical_direction: "right_to_left",
            profile_boost: 0.72,
        },
        DiscourseRealization {
            relation_family: "contrast",
            relation_schema: "contrast_peer",
            surface_phrase: "however",
            inverse_surface_phrase: Some("however"),
            surface_order: "peer_then_peer",
            logical_direction: "symmetric",
            profile_boost: 0.64,
        },
        DiscourseRealization {
            relation_family: "elaboration",
            relation_schema: "claim_to_example",
            surface_phrase: "for example",
            inverse_surface_phrase: Some("for instance"),
            surface_order: "claim_then_example",
            logical_direction: "left_to_right",
            profile_boost: 0.66,
        },
        DiscourseRealization {
            relation_family: "evidence",
            relation_schema: "evidence_to_claim",
            surface_phrase: "this shows",
            inverse_surface_phrase: Some("because"),
            surface_order: "evidence_then_claim",
            logical_direction: "left_to_right",
            profile_boost: 0.68,
        },
        DiscourseRealization {
            relation_family: "condition",
            relation_schema: "condition_to_outcome",
            surface_phrase: "if",
            inverse_surface_phrase: Some("only if"),
            surface_order: "condition_then_outcome",
            logical_direction: "left_to_right",
            profile_boost: 0.60,
        },
    ];
    match profile {
        "experiment-report" => {
            for realization in &mut realizations {
                if matches!(realization.relation_family, "causal" | "evidence") {
                    realization.profile_boost = (realization.profile_boost + 0.16).min(1.0);
                }
            }
        }
        "methods-protocol" => {
            for realization in &mut realizations {
                if matches!(realization.relation_family, "condition" | "causal") {
                    realization.profile_boost = (realization.profile_boost + 0.14).min(1.0);
                }
            }
        }
        "academic-argument" => {
            for realization in &mut realizations {
                if matches!(
                    realization.relation_family,
                    "causal" | "contrast" | "evidence" | "elaboration"
                ) {
                    realization.profile_boost = (realization.profile_boost + 0.10).min(1.0);
                }
            }
        }
        "refactor-design" => {
            for realization in &mut realizations {
                if matches!(realization.relation_family, "causal" | "condition") {
                    realization.profile_boost = (realization.profile_boost + 0.12).min(1.0);
                }
            }
        }
        _ => {}
    }
    realizations
}

pub(super) fn implicit_discourse_realization(profile: &str) -> DiscourseRealization {
    let profile_boost = match profile {
        "experiment-report" => 0.62,
        "methods-protocol" => 0.58,
        "academic-argument" => 0.60,
        "refactor-design" => 0.56,
        _ => 0.50,
    };
    DiscourseRealization {
        relation_family: "continuation",
        relation_schema: "implicit_neighbor",
        surface_phrase: "implicit",
        inverse_surface_phrase: None,
        surface_order: "left_then_right",
        logical_direction: "left_to_right",
        profile_boost,
    }
}

pub(super) fn connective_surface_score(text: &str, phrase: &str) -> f32 {
    let normalized = normalize_connective_surface(text);
    let phrase = phrase.to_ascii_lowercase();
    if normalized.starts_with(&phrase)
        && normalized
            .chars()
            .nth(phrase.chars().count())
            .is_none_or(|ch| ch.is_whitespace() || matches!(ch, ',' | ':' | ';' | '.'))
    {
        return 1.0;
    }
    let bounded = normalized.chars().take(220).collect::<String>();
    if bounded.contains(&format!(" {phrase} ")) {
        0.72
    } else {
        0.0
    }
}

pub(super) fn normalize_connective_surface(text: &str) -> String {
    let lowered = text.trim_start().to_ascii_lowercase();
    let trimmed = lowered
        .trim_start_matches('#')
        .trim_start_matches('-')
        .trim_start_matches('*')
        .trim_start_matches(|ch: char| ch.is_ascii_digit() || ch == '.' || ch == ')')
        .trim_start();
    trimmed
        .chars()
        .map(|ch| if ch.is_ascii_alphanumeric() { ch } else { ' ' })
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

pub(super) fn discourse_term_overlap(left_text: &str, right_text: &str) -> f32 {
    let left_terms: HashSet<String> = relation_terms(left_text).into_iter().collect();
    let right_terms: HashSet<String> = relation_terms(right_text).into_iter().collect();
    if left_terms.is_empty() || right_terms.is_empty() {
        return 0.0;
    }
    let intersection = left_terms.intersection(&right_terms).count();
    let union = left_terms.union(&right_terms).count();
    if union == 0 {
        0.0
    } else {
        intersection as f32 / union as f32
    }
}

pub(super) fn discourse_direction_confidence(
    realization: &DiscourseRealization,
    surface_score: f32,
    term_overlap: f32,
) -> f32 {
    if realization.logical_direction == "symmetric" {
        return 0.50;
    }
    (0.68 + 0.22 * surface_score + 0.10 * term_overlap).clamp(0.0, 1.0)
}

pub(super) fn discourse_ambiguity(
    realization: &DiscourseRealization,
    surface_score: f32,
    right_text: &str,
) -> String {
    if realization.logical_direction == "symmetric" {
        return "medium".to_string();
    }
    if realization.surface_phrase == "if" || realization.surface_phrase == "because" {
        return "medium".to_string();
    }
    let normalized = normalize_connective_surface(right_text);
    let signal_count = discourse_realizations(DEFAULT_DISCOURSE_PROFILE)
        .iter()
        .filter(|candidate| connective_surface_score(&normalized, candidate.surface_phrase) > 0.0)
        .count();
    if signal_count > 1 {
        "high".to_string()
    } else if surface_score >= 0.99 {
        "low".to_string()
    } else {
        "medium".to_string()
    }
}

pub(super) fn discourse_gap_flags(
    naturalness: f32,
    direction_confidence: f32,
    ambiguity: &str,
    explicit_connective: bool,
) -> Vec<String> {
    let mut flags = Vec::new();
    if !explicit_connective {
        flags.push("implicit_relation".to_string());
    }
    if naturalness < 0.50 {
        flags.push("weak_transition_evidence".to_string());
    }
    if direction_confidence < 0.60 {
        flags.push("low_direction_confidence".to_string());
    }
    if ambiguity == "high" {
        flags.push("ambiguous_connective".to_string());
    }
    flags
}

pub(super) fn comparison_bucket(kind: SimilarKind, node: &IndexedNode) -> Option<String> {
    match kind {
        SimilarKind::Similar => Some("similar:any".to_string()),
        SimilarKind::MergeCandidates => {
            if !is_merge_candidate_node(node) {
                return None;
            }
            merge_candidate_bucket(node)
                .map(|bucket| format!("merge:{bucket}:node-kind:{}", node.kind))
        }
    }
}

pub(super) fn best_thin_doc_neighbor(
    node: &IndexedNode,
    document_nodes: &[IndexedNode],
    min_neighbor_score: f32,
) -> Option<ThinDocNeighbor> {
    let bucket = document_responsibility_bucket(&node.path);
    let mut best: Option<ThinDocNeighbor> = None;
    for candidate in document_nodes {
        if candidate.file_id == node.file_id {
            continue;
        }
        if document_responsibility_bucket(&candidate.path) != bucket {
            continue;
        }
        let score = cosine_score(&node.vector, &candidate.vector);
        if score + f32::EPSILON < min_neighbor_score {
            continue;
        }
        let replace = best
            .as_ref()
            .map(|current| score > current.score)
            .unwrap_or(true);
        if replace {
            best = Some(ThinDocNeighbor {
                node: candidate.clone(),
                score,
            });
        }
    }
    best
}

pub(super) fn thin_doc_metrics(root: &Path, path: &str) -> ThinDocMetrics {
    let full_path = root.join(path);
    let text = fs::read_to_string(full_path).unwrap_or_default();
    let stripped = strip_dependency_manifest(&text);
    let mut meaningful_lines = 0;
    let mut link_lines = 0;
    let mut in_fence = false;
    for line in stripped.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("```") {
            in_fence = !in_fence;
            continue;
        }
        if trimmed.is_empty() || trimmed.starts_with('#') || is_markdown_table_rule(trimmed) {
            continue;
        }
        meaningful_lines += 1;
        if !in_fence && line_has_reference(trimmed) {
            link_lines += 1;
        }
    }
    let wrapper_phrase_hits = wrapper_phrase_hits(&stripped);
    let link_density = if meaningful_lines == 0 {
        0.0
    } else {
        link_lines as f32 / meaningful_lines as f32
    };
    ThinDocMetrics {
        total_lines: count_lines(&text),
        meaningful_lines,
        link_lines,
        wrapper_phrase_hits,
        link_density,
    }
}

pub(super) fn is_markdown_table_rule(line: &str) -> bool {
    line.chars()
        .all(|ch| ch == '|' || ch == '-' || ch == ':' || ch.is_whitespace())
        && line.contains('-')
}

pub(super) fn line_has_reference(line: &str) -> bool {
    line.contains("](")
        || line.contains(".md")
        || line.contains(".rst")
        || line.contains(".txt")
        || line.contains("`agents/")
        || line.contains("`documents/")
        || line.contains("`tools/")
}

pub(super) fn wrapper_phrase_hits(text: &str) -> usize {
    let lower = text.to_ascii_lowercase();
    [
        "see ",
        "entrypoint",
        "compatibility",
        "mirror",
        "source of truth",
        "thin",
        "wrapper",
        "redirect",
        "instead",
    ]
    .iter()
    .filter(|phrase| lower.contains(**phrase))
    .count()
}

pub(super) fn thin_doc_score(
    metrics: &ThinDocMetrics,
    best_score: f32,
    min_neighbor_score: f32,
) -> f32 {
    let content = thin_content_score(metrics.meaningful_lines);
    let neighbor = if best_score + f32::EPSILON >= min_neighbor_score {
        best_score
    } else {
        0.0
    };
    let link = metrics.link_density.min(1.0);
    let wrapper = (metrics.wrapper_phrase_hits as f32 / 2.0).min(1.0);
    (0.40 * content + 0.35 * neighbor + 0.15 * link + 0.10 * wrapper).clamp(0.0, 1.0)
}

pub(super) fn has_thin_doc_shape(metrics: &ThinDocMetrics) -> bool {
    thin_content_score(metrics.meaningful_lines) > 0.0 || metrics.link_density >= 0.40
}

pub(super) fn thin_content_score(meaningful_lines: usize) -> f32 {
    match meaningful_lines {
        0..=4 => 1.0,
        5..=8 => 0.85,
        9..=16 => 0.65,
        17..=24 => 0.35,
        _ => 0.0,
    }
}

pub(super) fn thin_doc_reasons(
    metrics: &ThinDocMetrics,
    best_score: f32,
    min_neighbor_score: f32,
) -> Vec<String> {
    let mut reasons = Vec::new();
    if metrics.meaningful_lines <= 8 {
        reasons.push("low_meaningful_content".to_string());
    }
    if best_score + f32::EPSILON >= min_neighbor_score {
        reasons.push("high_single_target_similarity".to_string());
    }
    if metrics.link_density >= 0.40 {
        reasons.push("high_reference_density".to_string());
    }
    if metrics.wrapper_phrase_hits > 0 {
        reasons.push("wrapper_phrase".to_string());
    }
    reasons
}

pub(super) fn thin_doc_action(
    metrics: &ThinDocMetrics,
    best_score: f32,
    min_neighbor_score: f32,
    protected: bool,
) -> String {
    if protected {
        return "keep_entrypoint".to_string();
    }
    if best_score + f32::EPSILON >= min_neighbor_score && metrics.meaningful_lines <= 16 {
        return "inline_into_target".to_string();
    }
    if metrics.link_density >= 0.50 && metrics.meaningful_lines <= 12 {
        return "replace_with_catalog_row".to_string();
    }
    if best_score + f32::EPSILON >= min_neighbor_score {
        return "merge_with_peer".to_string();
    }
    "manual_review".to_string()
}

pub(super) fn is_natural_relation_node(node: &IndexedNode) -> bool {
    if is_alignment_or_log_surface(&node.path) {
        return false;
    }
    if is_document_text_path(&node.path) {
        return matches!(node.kind.as_str(), "document" | "section");
    }
    matches!(node.kind.as_str(), "document" | "block")
}

pub(super) fn relation_terms_for_node(
    args: &NaturalRelationsArgs,
    node: &IndexedNode,
    cache: &mut HashMap<i64, Vec<String>>,
) -> Result<Vec<String>, String> {
    if let Some(terms) = cache.get(&node.node_id) {
        return Ok(terms.clone());
    }
    let text = context_excerpt(&args.root, node, DEFAULT_REMOTE_EMBEDDING_MAX_CHARS)?;
    let terms = relation_terms(&format!("{}\n{}", node.path, text));
    cache.insert(node.node_id, terms.clone());
    Ok(terms)
}

pub(super) fn relation_terms(text: &str) -> Vec<String> {
    let mut seen = HashSet::new();
    let mut terms = Vec::new();
    for token in text_tokens(&strip_dependency_manifest(text)) {
        if token.len() < 3 || is_relation_stop_word(&token) {
            continue;
        }
        if seen.insert(token.clone()) {
            terms.push(token);
        }
    }
    terms
}

pub(super) fn is_relation_stop_word(token: &str) -> bool {
    matches!(
        token,
        "the"
            | "and"
            | "for"
            | "with"
            | "that"
            | "this"
            | "from"
            | "into"
            | "onto"
            | "when"
            | "then"
            | "than"
            | "must"
            | "should"
            | "will"
            | "can"
            | "are"
            | "was"
            | "were"
            | "has"
            | "have"
            | "had"
            | "not"
            | "but"
            | "one"
            | "two"
            | "via"
            | "out"
            | "all"
            | "any"
            | "none"
            | "true"
            | "false"
    )
}

pub(super) fn directed_kind_of_score(
    specific_terms: &[String],
    general_terms: &[String],
    similarity_score: f32,
) -> f32 {
    if specific_terms.is_empty() || general_terms.is_empty() {
        return 0.0;
    }
    let specific: HashSet<&str> = specific_terms.iter().map(String::as_str).collect();
    let matched_general_terms = general_terms
        .iter()
        .filter(|term| specific.contains(term.as_str()))
        .count();
    let coverage = matched_general_terms as f32 / general_terms.len() as f32;
    let length_balance = (specific_terms.len() as f32 / general_terms.len() as f32).min(1.0);
    (0.85 * coverage * length_balance + 0.15 * similarity_score).clamp(0.0, 1.0)
}

pub(super) fn classify_natural_relation(
    left_is_kind_of_right_score: f32,
    right_is_kind_of_left_score: f32,
    min_kind_of_score: f32,
) -> &'static str {
    let left_high = left_is_kind_of_right_score + f32::EPSILON >= min_kind_of_score;
    let right_high = right_is_kind_of_left_score + f32::EPSILON >= min_kind_of_score;
    match (left_high, right_high) {
        (true, true) => "equivalent",
        (true, false) => "left_is_kind_of_right",
        (false, true) => "right_is_kind_of_left",
        (false, false) => "unrelated",
    }
}

pub(super) fn sort_pairs(pairs: &mut [SimilarPair]) {
    pairs.sort_by(|left, right| {
        right
            .score
            .partial_cmp(&left.score)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.left.path.cmp(&right.left.path))
            .then_with(|| left.right.path.cmp(&right.right.path))
    });
}

pub(super) fn sort_thin_docs(candidates: &mut [ThinDocCandidate]) {
    candidates.sort_by(|left, right| {
        right
            .thin_score
            .partial_cmp(&left.thin_score)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.node.path.cmp(&right.node.path))
    });
}

pub(super) fn sort_natural_relations(relations: &mut [NaturalRelation]) {
    relations.sort_by(|left, right| {
        right
            .left_is_kind_of_right_score
            .max(right.right_is_kind_of_left_score)
            .partial_cmp(
                &left
                    .left_is_kind_of_right_score
                    .max(left.right_is_kind_of_left_score),
            )
            .unwrap_or(Ordering::Equal)
            .then_with(|| {
                right
                    .similarity_score
                    .partial_cmp(&left.similarity_score)
                    .unwrap_or(Ordering::Equal)
            })
            .then_with(|| left.left.path.cmp(&right.left.path))
            .then_with(|| left.right.path.cmp(&right.right.path))
    });
}

pub(super) fn sort_discourse_relations(relations: &mut [DiscourseRelation]) {
    relations.sort_by(|left, right| {
        right
            .naturalness_score
            .partial_cmp(&left.naturalness_score)
            .unwrap_or(Ordering::Equal)
            .then_with(|| {
                right
                    .direction_confidence
                    .partial_cmp(&left.direction_confidence)
                    .unwrap_or(Ordering::Equal)
            })
            .then_with(|| left.left.path.cmp(&right.left.path))
            .then_with(|| left.left.line_start.cmp(&right.left.line_start))
            .then_with(|| left.right.line_start.cmp(&right.right.line_start))
    });
}
