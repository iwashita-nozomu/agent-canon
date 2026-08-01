// @dependency-start
// contract implementation
// responsibility Owns explicit cross-owner semantic-index regression tests and fixture behavior oracles.
// upstream design ../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../tools/catalog.yaml command catalog and public command source
// downstream implementation ../../../../tools/agent_tools/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use super::args::{
    default_db_path, default_excludes, parse_args, BuildArgs, CompareProvidersArgs,
    ContextPackArgs, DiscourseRelationsArgs, EmbedProviderArgs, EvalArgs, EvalOutputArgs,
    NaturalRelationsArgs, OutputFormat, ParsedArgs, ProviderSpec, ResponsibilityTreeArgs,
    SearchArgs, SimilarArgs, SimilarKind, ThinDocsArgs, DEFAULT_EMBEDDING_BATCH,
    DEFAULT_MAX_FILE_BYTES, DEFAULT_MIN_KIND_OF_SCORE, DEFAULT_MODEL, DEFAULT_PROVIDER,
};
use super::cli::run;
use super::embedding::{
    bound_remote_embedding_text, dot, embed_text, parse_openai_embeddings_response,
};
use super::eval::{compare_providers, eval_output, run_eval};
use super::model::{
    merge_candidate_bucket, responsibility_scope_bucket, run_id, IndexedNode,
    MERGE_CANDIDATE_MIN_LINES,
};
use super::pipeline::{build_index, embed_existing_nodes};
use super::query::{context_pack, responsibility_tree, search_index};
use super::relations::{
    classify_natural_relation, directed_kind_of_score, discourse_relations, natural_relations,
    relation_terms, similar_pairs, thin_docs,
};
use super::report::{pair_json, responsibility_tree_report_json, write_pretty_report};
use super::source::segment_text;
use super::storage::{
    insert_embedding, load_nodes, open_cache_connection, persist_discourse_relations,
    persist_natural_relations, provider_dimensions, DiscourseRelationRow, NaturalRelationRow,
};
use serde_json::Value;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

#[test]
fn markdown_segmentation_emits_document_sections_and_blocks() {
    let nodes = segment_text("documents/example.md", "# One\nalpha beta\n\n## Two\ngamma");
    assert!(nodes.iter().any(|node| node.kind == "document"));
    assert_eq!(
        nodes.iter().filter(|node| node.kind == "section").count(),
        2
    );
    assert_eq!(nodes.iter().filter(|node| node.kind == "block").count(), 2);
}

#[test]
fn embedding_is_normalized_and_zero_safe() {
    let vector = embed_text("semantic index search", 32);
    let norm = vector.iter().map(|value| value * value).sum::<f32>().sqrt();
    assert!((norm - 1.0).abs() < 0.0001);
    let empty = embed_text("   ", 32);
    assert!(empty.iter().all(|value| *value == 0.0));
}

#[test]
fn embedding_ignores_dependency_manifest_comment() {
    let with_manifest = "<!--\n@dependency-start\nresponsibility noisy header\n@dependency-end\n-->\n\n# Topic\nunique semantic payload";
    let without_manifest = "# Topic\nunique semantic payload";
    assert!(
        dot(
            &embed_text(with_manifest, 32),
            &embed_text(without_manifest, 32)
        ) > 0.99
    );
}

#[test]
fn openai_embedding_response_parses_indexed_batch() {
    let response = r#"{
          "object": "list",
          "data": [
            {"object": "embedding", "embedding": [0.1, 0.2, 0.3], "index": 1},
            {"object": "embedding", "embedding": [0.4, 0.5, 0.6], "index": 0}
          ],
          "model": "fixture-embedding"
        }"#;
    let vectors = parse_openai_embeddings_response(response, 2).unwrap();
    assert_eq!(vectors[0], vec![0.4, 0.5, 0.6]);
    assert_eq!(vectors[1], vec![0.1, 0.2, 0.3]);
}

#[test]
fn openai_embedding_response_rejects_bad_shapes() {
    for response in [
        r#"{"object":"list"}"#,
        r#"{"data":[{"embedding":["bad"],"index":0}]}"#,
        r#"{"data":[{"embedding":[],"index":0}]}"#,
        "prefix noise {\"data\":[]}",
    ] {
        assert!(parse_openai_embeddings_response(response, 1).is_err());
    }
}

#[test]
fn remote_embedding_text_is_bounded_without_splitting_chars() {
    let bounded = bound_remote_embedding_text("abcdef", 3);
    assert_eq!(bounded, "abc");
    assert_eq!(bound_remote_embedding_text("abc", 3), "abc");
}

#[test]
fn provider_compare_reuses_existing_responsibility_buckets() {
    let root = unique_temp_dir("semantic-index-provider-compare");
    fs::create_dir_all(root.join("documents")).unwrap();
    let duplicate =
        "# Duplicate\nshared provider comparison phrase\nwith enough lines\nfor merge candidates";
    fs::write(root.join("documents").join("one.md"), duplicate).unwrap();
    fs::write(root.join("documents").join("two.md"), duplicate).unwrap();
    let db = root.join("index.sqlite");
    build_index(&BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    })
    .unwrap();
    let mut conn = open_cache_connection(&db).unwrap();
    let tx = conn.transaction().unwrap();
    let nodes = load_nodes(&tx, DEFAULT_PROVIDER, DEFAULT_MODEL, 64).unwrap();
    for node in &nodes {
        insert_embedding(
            &tx,
            node.node_id,
            "fixture-llm",
            "fixture",
            64,
            &node.vector,
        )
        .unwrap();
    }
    tx.commit().unwrap();

    let report = compare_providers(&CompareProvidersArgs {
        db,
        query: Some("provider comparison phrase".to_string()),
        left: ProviderSpec {
            provider: DEFAULT_PROVIDER.to_string(),
            model: DEFAULT_MODEL.to_string(),
            dim: 64,
            embedding_url: None,
        },
        right: ProviderSpec {
            provider: "fixture-llm".to_string(),
            model: "fixture".to_string(),
            dim: 64,
            embedding_url: None,
        },
        min_score: 0.5,
        top_k: 10,
        report: None,
        format: OutputFormat::Json,
    })
    .unwrap();
    assert_eq!(
        report
            .get("semantic_index_provider_compare")
            .and_then(Value::as_str),
        Some("ok")
    );
    assert_eq!(
        report["merge_candidates"]["overlap_ratio"].as_f64(),
        Some(1.0)
    );
    assert_eq!(report["search"]["query_chars"].as_u64(), Some(26));
    assert!(report["search"].get("query").is_none());
}

#[test]
fn embed_provider_adds_vectors_without_rebuilding_nodes() {
    let root = unique_temp_dir("semantic-index-embed-provider");
    fs::create_dir_all(root.join("documents")).unwrap();
    fs::write(
        root.join("documents").join("one.md"),
        "# One\nprovider add vector text\nwith enough lines\nfor an indexed node",
    )
    .unwrap();
    let db = root.join("index.sqlite");
    build_index(&BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    })
    .unwrap();
    let stats = embed_existing_nodes(&EmbedProviderArgs {
        root: root.clone(),
        db: db.clone(),
        provider: "fixture-provider".to_string(),
        model: "fixture-model".to_string(),
        dim: 32,
        embedding_url: None,
        embedding_batch: 2,
    })
    .unwrap();
    assert_eq!(stats.nodes, stats.embeddings);
    let resumed_stats = embed_existing_nodes(&EmbedProviderArgs {
        root: root.clone(),
        db: db.clone(),
        provider: "fixture-provider".to_string(),
        model: "fixture-model".to_string(),
        dim: 32,
        embedding_url: None,
        embedding_batch: 2,
    })
    .unwrap();
    assert_eq!(resumed_stats.nodes, 0);
    assert_eq!(resumed_stats.embeddings, 0);
    let different_dim_stats = embed_existing_nodes(&EmbedProviderArgs {
        root: root.clone(),
        db: db.clone(),
        provider: "fixture-provider".to_string(),
        model: "fixture-model".to_string(),
        dim: 16,
        embedding_url: None,
        embedding_batch: 2,
    })
    .unwrap();
    assert_eq!(different_dim_stats.nodes, stats.nodes);
    assert_eq!(different_dim_stats.embeddings, stats.embeddings);
    let conn = open_cache_connection(&db).unwrap();
    assert_eq!(
        provider_dimensions(&conn, "fixture-provider", "fixture-model").unwrap(),
        vec![16, 32]
    );
    assert!(!load_nodes(&conn, "fixture-provider", "fixture-model", 32)
        .unwrap()
        .is_empty());
}

#[test]
fn candidate_commands_auto_resolve_provider_dimension() {
    let root = unique_temp_dir("semantic-index-auto-provider-dim");
    fs::create_dir_all(root.join("documents")).unwrap();
    fs::write(
        root.join("documents").join("one.md"),
        "# One\nshared auto provider phrase\nwith enough lines\nfor merge candidates",
    )
    .unwrap();
    fs::write(
        root.join("documents").join("two.md"),
        "# Two\nshared auto provider phrase\nwith enough lines\nfor merge candidates",
    )
    .unwrap();
    let db = root.join("index.sqlite");
    build_index(&BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    })
    .unwrap();
    let mut conn = open_cache_connection(&db).unwrap();
    let tx = conn.transaction().unwrap();
    let nodes = load_nodes(&tx, DEFAULT_PROVIDER, DEFAULT_MODEL, 64).unwrap();
    let mut vector = vec![0.0; 32];
    vector[0] = 1.0;
    for node in &nodes {
        insert_embedding(
            &tx,
            node.node_id,
            "fixture-provider",
            "fixture-model",
            32,
            &vector,
        )
        .unwrap();
    }
    tx.commit().unwrap();

    let pairs = similar_pairs(&SimilarArgs {
        root: root.clone(),
        db: db.clone(),
        provider: "fixture-provider".to_string(),
        model: "fixture-model".to_string(),
        dim: 0,
        min_score: 0.99,
        top_k: 10,
        format: OutputFormat::Jsonl,
        cross_file_only: true,
        kind: SimilarKind::MergeCandidates,
    })
    .unwrap();
    assert!(!pairs.is_empty());

    let candidates = thin_docs(&ThinDocsArgs {
        root,
        db,
        provider: "fixture-provider".to_string(),
        model: "fixture-model".to_string(),
        dim: 0,
        min_thin_score: 0.1,
        min_neighbor_score: 0.99,
        top_k: 10,
        format: OutputFormat::Jsonl,
    })
    .unwrap();
    assert!(!candidates.is_empty());
}

#[test]
fn directed_kind_of_score_classifies_equivalent_and_containment() {
    let specific =
        relation_terms("Python reviewer checks Python diffs with ruff pyright pytest evidence.");
    let general = relation_terms("Reviewer checks diffs and records evidence.");
    let left = directed_kind_of_score(&specific, &general, 0.80);
    let right = directed_kind_of_score(&general, &specific, 0.80);
    assert_eq!(
        classify_natural_relation(left, right, DEFAULT_MIN_KIND_OF_SCORE),
        "left_is_kind_of_right"
    );

    let equivalent_left = relation_terms("Agent update validates submodule pin workflow.");
    let equivalent_right = relation_terms("Submodule pin workflow validates agent update.");
    let left = directed_kind_of_score(&equivalent_left, &equivalent_right, 0.95);
    let right = directed_kind_of_score(&equivalent_right, &equivalent_left, 0.95);
    assert_eq!(
        classify_natural_relation(left, right, DEFAULT_MIN_KIND_OF_SCORE),
        "equivalent"
    );
}

#[test]
fn natural_relations_persist_directed_kind_of_analysis() {
    let root = unique_temp_dir("semantic-index-natural-relations");
    fs::create_dir_all(root.join("docs")).unwrap();
    fs::write(
        root.join("docs").join("python_review.md"),
        "# Python Review\nPython reviewer checks Python diffs with ruff pyright pytest evidence.",
    )
    .unwrap();
    fs::write(
        root.join("docs").join("review.md"),
        "# Review\nReviewer checks diffs and records evidence.",
    )
    .unwrap();
    fs::write(
        root.join("docs").join("security.md"),
        "# Security\nSecret scanner credential exposure audit.",
    )
    .unwrap();
    let db = root.join("index.sqlite");
    build_index(&BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from("docs")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    })
    .unwrap();
    let args = NaturalRelationsArgs {
        root: root.clone(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        min_similarity: 0.05,
        min_kind_of_score: DEFAULT_MIN_KIND_OF_SCORE,
        top_k: 20,
        format: OutputFormat::Jsonl,
        cross_file_only: true,
    };
    let relations = natural_relations(&args).unwrap();
    let review_relation = relations
        .iter()
        .find(|relation| {
            relation.left.path == "docs/python_review.md"
                && relation.right.path == "docs/review.md"
                && relation.relation_kind == "left_is_kind_of_right"
        })
        .expect("expected Python review to be a kind of review");
    assert!(
        review_relation.left_is_kind_of_right_score > review_relation.right_is_kind_of_left_score
    );

    let rows = relations
        .iter()
        .map(|relation| NaturalRelationRow {
            left_node_id: relation.left.node_id,
            right_node_id: relation.right.node_id,
            similarity_score: relation.similarity_score,
            left_is_kind_of_right_score: relation.left_is_kind_of_right_score,
            right_is_kind_of_left_score: relation.right_is_kind_of_left_score,
            relation_kind: relation.relation_kind.clone(),
            rank: relation.rank,
        })
        .collect::<Vec<_>>();
    persist_natural_relations(&args, &rows).unwrap();
    let conn = open_cache_connection(&db).unwrap();
    let count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM natural_language_relations WHERE relation_kind = 'left_is_kind_of_right'",
                [],
                |row| row.get(0),
            )
            .unwrap();
    assert!(count >= 1);
}

#[test]
fn discourse_relations_pair_therefore_and_because_variants() {
    let root = unique_temp_dir("semantic-index-discourse-relations");
    fs::create_dir_all(root.join("docs")).unwrap();
    fs::write(
            root.join("docs").join("flow.md"),
            "# Flow\nThe runtime log branch may not be mounted before an AgentCanon update.\n\nTherefore the update tool should warn and continue without blocking validation.\n\nThe warning belongs in workflow guidance.\n\nBecause the same missing mount can appear before the log archive checkout exists.",
        )
        .unwrap();
    let db = root.join("index.sqlite");
    build_index(&BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from("docs")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    })
    .unwrap();
    let args = DiscourseRelationsArgs {
        root: root.clone(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        profile: "experiment-report".to_string(),
        min_naturalness: 0.20,
        window: 2,
        top_k: 20,
        format: OutputFormat::Jsonl,
    };
    let relations = discourse_relations(&args).unwrap();
    let therefore = relations
        .iter()
        .find(|relation| {
            relation.surface_phrase == "therefore"
                && relation.relation_schema == "reason_to_result"
                && relation.logical_direction == "left_to_right"
        })
        .expect("expected therefore to map reason-to-result left-to-right");
    assert_eq!(therefore.inverse_surface_phrase.as_deref(), Some("because"));

    let because = relations
        .iter()
        .find(|relation| {
            relation.surface_phrase == "because"
                && relation.relation_schema == "reason_to_result"
                && relation.logical_direction == "right_to_left"
        })
        .expect("expected because to map the same schema with reverse logical direction");
    assert_eq!(because.inverse_surface_phrase.as_deref(), Some("therefore"));

    let rows = relations
        .iter()
        .map(|relation| DiscourseRelationRow {
            left_node_id: relation.left.node_id,
            right_node_id: relation.right.node_id,
            similarity_score: relation.similarity_score,
            connective_profile: relation.connective_profile.clone(),
            relation_family: relation.relation_family.clone(),
            relation_schema: relation.relation_schema.clone(),
            surface_phrase: relation.surface_phrase.clone(),
            inverse_surface_phrase: relation.inverse_surface_phrase.clone(),
            surface_order: relation.surface_order.clone(),
            logical_direction: relation.logical_direction.clone(),
            naturalness_score: relation.naturalness_score,
            inverse_naturalness_score: relation.inverse_naturalness_score,
            direction_confidence: relation.direction_confidence,
            ambiguity: relation.ambiguity.clone(),
            gap_flags: relation.gap_flags.clone(),
            rank: relation.rank,
        })
        .collect::<Vec<_>>();
    persist_discourse_relations(&args, &rows).unwrap();
    let conn = open_cache_connection(&db).unwrap();
    let count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM discourse_relations WHERE relation_schema = 'reason_to_result'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert!(count >= 2);
}

#[test]
fn sqlite_build_and_search_roundtrip() {
    let root = unique_temp_dir("semantic-index-search");
    fs::create_dir_all(root.join("docs")).unwrap();
    fs::write(
        root.join("docs").join("update.md"),
        "# AgentCanon update\nsubmodule pin latest workflow",
    )
    .unwrap();
    fs::write(
        root.join("docs").join("security.md"),
        "# Security audit\nsecret scanner hardening",
    )
    .unwrap();
    let db = root.join(".agent-canon/semantic-index/index.sqlite");
    let build_args = BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from("docs")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    };
    let stats = build_index(&build_args).unwrap();
    assert_eq!(stats.files, 2);
    assert!(stats.nodes >= 4);
    let search_args = SearchArgs {
        root,
        db,
        query: "latest submodule update workflow".to_string(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        top_k: 3,
        format: OutputFormat::Json,
    };
    let hits = search_index(&search_args).unwrap();
    assert!(hits
        .results
        .iter()
        .any(|hit| hit.node.path == "docs/update.md"));
    assert_eq!(hits.stale_path_count, 0);
}

#[test]
fn context_pack_returns_bounded_evidence_cells() {
    let root = unique_temp_dir("semantic-index-context-pack");
    fs::create_dir_all(root.join("docs")).unwrap();
    fs::write(
            root.join("docs").join("routing.md"),
            "# Routing\nskill workflow tool responsibility candidate context phrase\nsecond line for bounded excerpt\nthird line stays local",
        )
        .unwrap();
    fs::write(
        root.join("docs").join("other.md"),
        "# Other\nunrelated content",
    )
    .unwrap();
    let db = root.join("index.sqlite");
    build_index(&BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from("docs")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    })
    .unwrap();

    let cells = context_pack(&ContextPackArgs {
        root,
        db,
        query: "skill workflow responsibility".to_string(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        max_cells: 2,
        max_cell_chars: 40,
        max_total_chars: 80,
        format: OutputFormat::Jsonl,
    })
    .unwrap();

    assert!(!cells.is_empty());
    assert!(cells.len() <= 2);
    assert!(cells.iter().all(|cell| cell.excerpt.chars().count() <= 40));
    assert!(cells.iter().any(|cell| cell.path.ends_with("routing.md")));
}

#[test]
fn responsibility_tree_reports_vectors_and_coverage() {
    let root = unique_temp_dir("semantic-index-responsibility-tree");
    fs::create_dir_all(root.join("documents")).unwrap();
    fs::create_dir_all(root.join("tools")).unwrap();
    fs::write(
        root.join("documents").join("policy.md"),
        "# Policy\nsemantic index directory coverage responsibility tree",
    )
    .unwrap();
    fs::write(
        root.join("tools").join("scan.py"),
        "print('semantic index directory coverage tool')\n",
    )
    .unwrap();
    let db = root.join("index.sqlite");
    build_index(&BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    })
    .unwrap();
    let args = ResponsibilityTreeArgs {
        root: root.clone(),
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db,
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        node_kind: "document".to_string(),
        max_depth: None,
        top_k: None,
        include_vector: true,
        check_directory_coverage: true,
        report: None,
        format: OutputFormat::Json,
    };
    let report = responsibility_tree(&args).unwrap();
    assert_eq!(report.coverage.status, "pass");
    assert!(report
        .directories
        .iter()
        .any(|directory| directory.path == "documents" && directory.vector.len() == 64));
    assert!(report
        .directories
        .iter()
        .any(|directory| directory.path == "tools" && directory.vector.len() == 64));
    let json = responsibility_tree_report_json(&report);
    assert_eq!(
        json["coverage"]["missing_directory_count"].as_u64(),
        Some(0)
    );
    assert!(json["directories"]
        .as_array()
        .unwrap()
        .iter()
        .any(|directory| directory.get("vector").is_some()));
    let output = root.join("responsibility_tree.json");
    write_pretty_report(&output, &json).unwrap();
    let parsed: Value = serde_json::from_str(&fs::read_to_string(output).unwrap()).unwrap();
    assert_eq!(
        parsed
            .get("semantic_index_responsibility_tree")
            .and_then(Value::as_str),
        Some("ok")
    );
}

#[test]
fn responsibility_tree_detects_missing_directory_coverage() {
    let root = unique_temp_dir("semantic-index-responsibility-tree-missing");
    fs::create_dir_all(root.join("documents")).unwrap();
    fs::create_dir_all(root.join("tools")).unwrap();
    fs::write(
        root.join("documents").join("policy.md"),
        "# Policy\nsemantic index coverage baseline",
    )
    .unwrap();
    let db = root.join("index.sqlite");
    build_index(&BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from("documents")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    })
    .unwrap();
    fs::write(
        root.join("tools").join("new_tool.py"),
        "print('not yet indexed')\n",
    )
    .unwrap();
    let report = responsibility_tree(&ResponsibilityTreeArgs {
        root,
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db,
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
        node_kind: "document".to_string(),
        max_depth: None,
        top_k: None,
        include_vector: false,
        check_directory_coverage: true,
        report: None,
        format: OutputFormat::Json,
    })
    .unwrap();
    assert_eq!(report.coverage.status, "fail");
    assert!(report
        .coverage
        .missing_directories
        .contains(&"tools".to_string()));
}

#[test]
fn parse_search_requires_query() {
    let args = vec![
        "search".to_string(),
        "--format".to_string(),
        "json".to_string(),
    ];
    let error = parse_args(&args).unwrap_err();
    assert!(error.contains("--query, --query-file, or --query-stdin is required"));
}

#[test]
fn mismatched_search_dimension_returns_no_hits() {
    let root = unique_temp_dir("semantic-index-dim");
    fs::create_dir_all(root.join("docs")).unwrap();
    fs::write(
        root.join("docs").join("alpha.md"),
        "# Alpha\nsemantic vector",
    )
    .unwrap();
    let db = root.join("index.sqlite");
    let build_args = BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from("docs")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 32,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    };
    build_index(&build_args).unwrap();
    let search_args = SearchArgs {
        root,
        db,
        query: "semantic vector".to_string(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        top_k: 5,
        format: OutputFormat::Json,
    };
    assert!(search_index(&search_args).unwrap().results.is_empty());
}

#[test]
fn search_skips_cached_nodes_for_deleted_paths() {
    let root = unique_temp_dir("semantic-index-stale-paths");
    fs::create_dir_all(root.join("docs")).unwrap();
    let stale_path = root.join("docs").join("stale.md");
    fs::write(
        &stale_path,
        "# Stale\nsemantic vector deleted path phrase\nwith enough lines\nfor an indexed node",
    )
    .unwrap();
    let db = root.join("index.sqlite");
    build_index(&BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from("docs")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    })
    .unwrap();
    fs::remove_file(stale_path).unwrap();

    let hits = search_index(&SearchArgs {
        root,
        db,
        query: "deleted path phrase".to_string(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        top_k: 5,
        format: OutputFormat::Json,
    })
    .unwrap();

    assert!(hits.results.is_empty());
    assert!(hits.stale_path_count > 0);
}

#[test]
fn merge_candidates_exclude_same_file_pairs_by_default() {
    let root = unique_temp_dir("semantic-index-cross-file");
    fs::create_dir_all(root.join("docs")).unwrap();
    fs::write(
        root.join("docs").join("one.md"),
        "# One\nshared semantic topic\nwith enough lines\nfor merge candidates",
    )
    .unwrap();
    fs::write(
        root.join("docs").join("two.md"),
        "# Two\nshared semantic topic\nwith enough lines\nfor merge candidates",
    )
    .unwrap();
    let db = root.join("index.sqlite");
    let build_args = BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from("docs")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    };
    build_index(&build_args).unwrap();
    let args = SimilarArgs {
        root,
        db,
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        min_score: 0.5,
        top_k: 20,
        format: OutputFormat::Json,
        cross_file_only: true,
        kind: SimilarKind::MergeCandidates,
    };
    let pairs = similar_pairs(&args).unwrap();
    assert!(!pairs.is_empty());
    assert!(pairs
        .iter()
        .all(|pair| pair.left.file_id != pair.right.file_id));
}

#[test]
fn merge_candidates_stay_within_responsibility_bucket_on_full_repo_input() {
    let root = unique_temp_dir("semantic-index-merge-buckets");
    fs::create_dir_all(root.join("docs")).unwrap();
    fs::create_dir_all(root.join("src")).unwrap();
    let duplicate =
        "# Duplicate\nshared responsibility vector phrase\n\nshared responsibility vector phrase";
    fs::write(root.join("docs").join("one.md"), duplicate).unwrap();
    fs::write(root.join("docs").join("two.md"), duplicate).unwrap();
    fs::write(root.join("src").join("one.py"), duplicate).unwrap();
    let db = root.join("index.sqlite");
    let build_args = BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    };
    build_index(&build_args).unwrap();
    let args = SimilarArgs {
        root,
        db,
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        min_score: 0.95,
        top_k: 50,
        format: OutputFormat::Json,
        cross_file_only: true,
        kind: SimilarKind::MergeCandidates,
    };
    let pairs = similar_pairs(&args).unwrap();
    let doc_pair = pairs
        .iter()
        .find(|pair| pair.left.path.ends_with(".md") && pair.right.path.ends_with(".md"))
        .expect("docs pair should stay eligible inside one responsibility bucket");
    let doc_json = pair_json(doc_pair);
    assert_eq!(
        doc_json.get("same_responsibility").and_then(Value::as_bool),
        Some(true)
    );
    assert_eq!(
        doc_json
            .get("candidate_bucket")
            .and_then(Value::as_str)
            .unwrap_or(""),
        "docs:general:general"
    );
    assert!(pairs.iter().all(|pair| {
        let left_is_doc = pair.left.path.ends_with(".md");
        let right_is_doc = pair.right.path.ends_with(".md");
        let left_is_code = pair.left.path.ends_with(".py");
        let right_is_code = pair.right.path.ends_with(".py");
        !(left_is_doc && right_is_code || left_is_code && right_is_doc)
    }));
}

#[test]
fn responsibility_scope_bucket_tracks_manifest_surfaces() {
    assert_eq!(
        responsibility_scope_bucket("agents/workflows/run.md"),
        "runtime-entrypoints"
    );
    assert_eq!(
        responsibility_scope_bucket("agents/evals/results/run.json"),
        "eval-and-hook-evidence"
    );
    assert_eq!(
        responsibility_scope_bucket("evidence/agent-evals/skill_workflow_prompt_eval.toml"),
        "eval-and-hook-evidence"
    );
    assert_eq!(
        responsibility_scope_bucket("documents/tools/search-coordination.md"),
        "shared-policy-documents"
    );
    assert_eq!(
        responsibility_scope_bucket("rust/agent-canon/src/semantic_index.rs"),
        "shared-tooling"
    );
    assert_eq!(
        responsibility_scope_bucket("tests/agent_tools/test_semantic.py"),
        "test-surfaces"
    );
    assert_eq!(
        merge_candidate_bucket(&IndexedNode {
            node_id: 1,
            file_id: 1,
            path: "documents/tools/semantic-index.md".to_string(),
            kind: "document".to_string(),
            line_start: 1,
            line_end: 10,
            vector: Vec::new(),
        })
        .as_deref(),
        Some("docs:shared-policy-documents:tool-doc")
    );
}

#[test]
fn similar_pairs_can_cross_responsibility_bucket_for_alignment_search() {
    let root = unique_temp_dir("semantic-index-similar-cross-bucket");
    fs::create_dir_all(root.join("docs")).unwrap();
    fs::create_dir_all(root.join("src")).unwrap();
    let duplicate = "# Alignment\nsame exact phrase for code and docs";
    fs::write(root.join("docs").join("alignment.md"), duplicate).unwrap();
    fs::write(root.join("src").join("alignment.py"), duplicate).unwrap();
    let db = root.join("index.sqlite");
    let build_args = BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    };
    build_index(&build_args).unwrap();
    let args = SimilarArgs {
        root,
        db,
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        min_score: 0.99,
        top_k: 20,
        format: OutputFormat::Json,
        cross_file_only: true,
        kind: SimilarKind::Similar,
    };
    let pairs = similar_pairs(&args).unwrap();
    assert!(pairs.iter().any(|pair| {
        let left_is_doc = pair.left.path.ends_with(".md");
        let right_is_doc = pair.right.path.ends_with(".md");
        let left_is_code = pair.left.path.ends_with(".py");
        let right_is_code = pair.right.path.ends_with(".py");
        left_is_doc && right_is_code || left_is_code && right_is_doc
    }));
}

#[test]
fn merge_candidates_skip_alignment_mirrors_and_eval_logs() {
    let root = unique_temp_dir("semantic-index-skip-alignment");
    fs::create_dir_all(root.join("documents")).unwrap();
    fs::create_dir_all(root.join(".agents/skills/example")).unwrap();
    fs::create_dir_all(root.join("agents/evals/results/example")).unwrap();
    fs::create_dir_all(root.join("templates/agents/_partials")).unwrap();
    fs::create_dir_all(root.join("codex-cli-guide/source")).unwrap();
    fs::create_dir_all(root.join("codex-cli-guide/sections")).unwrap();
    let mergeable_duplicate =
        "# Same\nshared duplicate section text\nwith enough lines\nfor a merge candidate";
    fs::write(root.join("documents").join("one.md"), mergeable_duplicate).unwrap();
    fs::write(root.join("documents").join("two.md"), mergeable_duplicate).unwrap();
    fs::write(
        root.join(".agents/skills/example").join("SKILL.md"),
        mergeable_duplicate,
    )
    .unwrap();
    fs::write(
        root.join("agents/evals/results/example").join("one.md"),
        mergeable_duplicate,
    )
    .unwrap();
    fs::write(
        root.join("agents/evals/results/example").join("two.md"),
        mergeable_duplicate,
    )
    .unwrap();
    fs::write(
        root.join("templates/agents/_partials").join("table.md"),
        mergeable_duplicate,
    )
    .unwrap();
    fs::write(
        root.join("codex-cli-guide/source").join("guide.full.md"),
        mergeable_duplicate,
    )
    .unwrap();
    fs::write(
        root.join("codex-cli-guide/sections").join("guide.md"),
        mergeable_duplicate,
    )
    .unwrap();
    let db = root.join("index.sqlite");
    let build_args = BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    };
    build_index(&build_args).unwrap();
    let args = SimilarArgs {
        root,
        db,
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        min_score: 0.95,
        top_k: 50,
        format: OutputFormat::Json,
        cross_file_only: true,
        kind: SimilarKind::MergeCandidates,
    };
    let pairs = similar_pairs(&args).unwrap();
    assert!(pairs
        .iter()
        .any(|pair| pair.left.path.starts_with("documents/")
            && pair.right.path.starts_with("documents/")));
    assert!(pairs.iter().all(|pair| {
        let paths = [&pair.left.path, &pair.right.path];
        !paths.iter().any(|path| {
            path.starts_with(".agents/")
                || path.starts_with("agents/evals/results/")
                || path.starts_with("templates/agents/_partials/")
                || path.starts_with("codex-cli-guide/source/")
                || path.starts_with("codex-cli-guide/sections/")
        })
    }));
}

#[test]
fn merge_candidates_skip_tiny_heading_only_sections() {
    let root = unique_temp_dir("semantic-index-skip-tiny");
    fs::create_dir_all(root.join("documents")).unwrap();
    fs::write(
        root.join("documents").join("one.md"),
        "# One\n\n## Standard Flow\n\nlong duplicate body\nwith enough lines\nfor scoring",
    )
    .unwrap();
    fs::write(
        root.join("documents").join("two.md"),
        "# Two\n\n## Standard Flow\n\nlong duplicate body\nwith enough lines\nfor scoring",
    )
    .unwrap();
    let db = root.join("index.sqlite");
    let build_args = BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    };
    build_index(&build_args).unwrap();
    let args = SimilarArgs {
        root,
        db,
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        min_score: 0.95,
        top_k: 50,
        format: OutputFormat::Json,
        cross_file_only: true,
        kind: SimilarKind::MergeCandidates,
    };
    let pairs = similar_pairs(&args).unwrap();
    assert!(pairs.iter().all(|pair| {
        let left_lines = pair.left.line_end.saturating_sub(pair.left.line_start) + 1;
        let right_lines = pair.right.line_end.saturating_sub(pair.right.line_start) + 1;
        left_lines >= MERGE_CANDIDATE_MIN_LINES && right_lines >= MERGE_CANDIDATE_MIN_LINES
    }));
}

#[test]
fn thin_docs_reports_short_wrapper_from_vector_db() {
    let root = unique_temp_dir("semantic-index-thin-docs");
    fs::create_dir_all(root.join("documents")).unwrap();
    fs::write(
            root.join("documents").join("canonical.md"),
            "# Canonical\nsemantic index cache search routing document wrapper analysis\nsemantic index cache search routing document wrapper analysis\nsemantic index cache search routing document wrapper analysis",
        )
        .unwrap();
    fs::write(
            root.join("documents").join("wrapper.md"),
            "# Wrapper\nsemantic index cache search routing document wrapper analysis\nSee [canonical](canonical.md).\nThis compatibility entrypoint redirects to canonical semantic index cache search routing document.",
        )
        .unwrap();
    fs::write(
            root.join("documents").join("substantial.md"),
            "# Substantial\nalpha beta gamma delta epsilon\nzeta eta theta iota kappa\nlambda mu nu xi omicron\npi rho sigma tau upsilon\nphi chi psi omega",
        )
        .unwrap();
    let db = root.join("index.sqlite");
    build_index(&BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    })
    .unwrap();
    let candidates = thin_docs(&ThinDocsArgs {
        root,
        db,
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        min_thin_score: 0.60,
        min_neighbor_score: 0.75,
        top_k: 10,
        format: OutputFormat::Json,
    })
    .unwrap();
    let wrapper = candidates
        .iter()
        .find(|candidate| candidate.node.path == "documents/wrapper.md")
        .expect("wrapper should be reported as a thin doc");
    assert_eq!(wrapper.action, "inline_into_target");
    assert!(wrapper
        .reasons
        .contains(&"low_meaningful_content".to_string()));
    assert!(wrapper
        .reasons
        .contains(&"high_single_target_similarity".to_string()));
    assert_eq!(
        wrapper
            .best_match
            .as_ref()
            .map(|neighbor| neighbor.node.path.as_str()),
        Some("documents/canonical.md")
    );
    assert!(!candidates
        .iter()
        .any(|candidate| candidate.node.path == "documents/substantial.md"));
}

#[test]
fn thin_docs_marks_readme_wrappers_as_protected_entrypoints() {
    let root = unique_temp_dir("semantic-index-thin-protected");
    fs::create_dir_all(root.join("docs")).unwrap();
    fs::write(
        root.join("README.md"),
        "# Project\nsemantic index cache search routing\nSee [docs](docs/README.md).",
    )
    .unwrap();
    fs::write(
        root.join("docs").join("README.md"),
        "# Docs\nsemantic index cache search routing\nSee [root](../README.md).",
    )
    .unwrap();
    let db = root.join("index.sqlite");
    build_index(&BuildArgs {
        root: root.clone(),
        includes: vec![PathBuf::from(".")],
        excludes: default_excludes(),
        db: db.clone(),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    })
    .unwrap();
    let candidates = thin_docs(&ThinDocsArgs {
        root,
        db,
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        min_thin_score: 0.60,
        min_neighbor_score: 0.75,
        top_k: 10,
        format: OutputFormat::Json,
    })
    .unwrap();
    let readme = candidates
        .iter()
        .find(|candidate| candidate.node.path == "README.md")
        .expect("protected README wrapper should still be visible");
    assert_eq!(readme.action, "keep_entrypoint");
    assert!(readme.reasons.contains(&"protected_entrypoint".to_string()));
}

#[test]
fn parse_similar_rejects_non_positive_min_score() {
    let args = vec![
        "merge-candidates".to_string(),
        "--min-score".to_string(),
        "0".to_string(),
    ];
    let error = parse_args(&args).unwrap_err();
    assert!(error.contains("--min-score must be greater than zero"));
}

#[test]
fn parse_search_accepts_query_file_and_jsonl_for_long_text() {
    let root = unique_temp_dir("semantic-index-query-file");
    let query_path = root.join("query.txt");
    fs::write(
        &query_path,
        "This is a long natural-language task description for semantic search.",
    )
    .unwrap();
    let args = vec![
        "search".to_string(),
        "--query-file".to_string(),
        query_path.display().to_string(),
        "--format".to_string(),
        "jsonl".to_string(),
    ];
    let ParsedArgs::Search(parsed) = parse_args(&args).unwrap() else {
        panic!("expected search args");
    };
    assert!(parsed.query.contains("natural-language task"));
    assert_eq!(parsed.format, OutputFormat::Jsonl);
}

#[test]
fn default_db_path_lives_under_home_cache_and_outside_repo() {
    let root = unique_temp_dir("semantic-index-default-db");
    let db = default_db_path(&root);
    assert!(db.is_absolute());
    assert!(!db.starts_with(&root));
    assert!(db.ends_with("index.sqlite"));
    if let Ok(home) = env::var("HOME") {
        if !home.trim().is_empty() {
            assert!(db.starts_with(Path::new(&home)));
        }
    }
}

#[test]
fn eval_fixture_reports_pass() {
    let fixture = unique_temp_dir("semantic-index-eval");
    let input = fixture.join("input").join("docs");
    fs::create_dir_all(&input).unwrap();
    fs::write(
        input.join("agent_update.md"),
        "# Agent update\nAgentCanon latest submodule pin workflow",
    )
    .unwrap();
    fs::write(
        input.join("agent_sync.md"),
        "# Agent sync\nAgentCanon latest submodule pin process",
    )
    .unwrap();
    fs::write(
        input.join("security.md"),
        "# Security\nsecret scanner credential audit",
    )
    .unwrap();
    fs::write(
        fixture.join("expected.json"),
        r#"{
              "queries": [
                {
                  "id": "agent_update",
                  "text": "AgentCanon latest submodule workflow",
                  "expected_paths": ["docs/agent_update.md"],
                  "min_recall_at_5": 1.0
                }
              ],
              "similar_pairs": [
                {
                  "id": "update_sync",
                  "left": "docs/agent_update.md",
                  "right": "docs/agent_sync.md",
                  "min_score": 0.40
                }
              ],
              "must_not_pairs": [
                {
                  "id": "update_security",
                  "left": "docs/agent_update.md",
                  "right": "docs/security.md",
                  "max_score": 0.95
                }
              ]
            }"#,
    )
    .unwrap();
    let args = EvalArgs {
        fixture: fixture.clone(),
        db: fixture.join("eval.sqlite"),
        report: None,
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        top_k: 5,
        format: OutputFormat::Json,
    };
    let report = run_eval(&args).unwrap();
    assert_eq!(
        report
            .get("semantic_index_eval")
            .and_then(Value::as_str)
            .unwrap(),
        "pass"
    );
}

#[test]
fn eval_run_returns_nonzero_when_quality_fails() {
    let fixture = unique_temp_dir("semantic-index-failing-eval");
    let input = fixture.join("input").join("docs");
    fs::create_dir_all(&input).unwrap();
    fs::write(input.join("only.md"), "# Only\nunrelated text").unwrap();
    fs::write(
        fixture.join("expected.json"),
        r#"{
              "queries": [
                {
                  "id": "missing",
                  "text": "not present",
                  "expected_paths": ["docs/missing.md"],
                  "min_recall_at_5": 1.0
                }
              ]
            }"#,
    )
    .unwrap();
    let args = vec![
        "eval".to_string(),
        "--fixture".to_string(),
        fixture.display().to_string(),
        "--db".to_string(),
        fixture.join("eval.sqlite").display().to_string(),
        "--format".to_string(),
        "json".to_string(),
    ];
    assert_eq!(run(&args), 1);
}

#[test]
fn eval_missing_must_not_path_fails() {
    let fixture = unique_temp_dir("semantic-index-missing-path");
    let input = fixture.join("input").join("docs");
    fs::create_dir_all(&input).unwrap();
    fs::write(input.join("one.md"), "# One\nsemantic content").unwrap();
    fs::write(
        fixture.join("expected.json"),
        r#"{
              "must_not_pairs": [
                {
                  "id": "missing_path",
                  "left": "docs/one.md",
                  "right": "docs/missing.md",
                  "max_score": 0.9
                }
              ]
            }"#,
    )
    .unwrap();
    let args = EvalArgs {
        fixture: fixture.clone(),
        db: fixture.join("eval.sqlite"),
        report: None,
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        top_k: 5,
        format: OutputFormat::Json,
    };
    let report = run_eval(&args).unwrap();
    assert_eq!(
        report
            .get("semantic_index_eval")
            .and_then(Value::as_str)
            .unwrap(),
        "fail"
    );
    assert!(report["must_not_pairs"]["results"][0]["missing_path"]
        .as_bool()
        .unwrap());
}

#[test]
fn eval_output_accepts_valid_review_artifacts() {
    let root = unique_temp_dir("semantic-index-output-eval-pass");
    let merge_path = root.join("merge.jsonl");
    let thin_path = root.join("thin.jsonl");
    let search_path = root.join("search.jsonl");
    fs::write(
            &merge_path,
            r#"{"semantic_index_pairs":"ok","kind":"merge-candidates","result_count":1}
{"rank":1,"score":0.95,"same_responsibility":true,"candidate_bucket":"docs:shared-policy-documents:document","left":{"path":"documents/a.md","responsibility_bucket":"shared-policy-documents","node_kind":"document","line_start":1,"line_end":4},"right":{"path":"documents/b.md","responsibility_bucket":"shared-policy-documents","node_kind":"document","line_start":1,"line_end":4}}
"#,
        )
        .unwrap();
    fs::write(
            &thin_path,
            r#"{"semantic_index_thin_docs":"ok","result_count":1}
{"rank":1,"thin_score":0.72,"action":"keep_entrypoint","reasons":["protected_entrypoint"],"path":"README.md","node_kind":"document","line_start":1,"line_end":3}
"#,
        )
        .unwrap();
    fs::write(
            &search_path,
            r#"{"semantic_index_search":"ok","query_chars":42,"result_count":1}
{"rank":1,"score":0.61,"path":"documents/tools/semantic_index.md","node_kind":"block","line_start":10,"line_end":12}
"#,
        )
        .unwrap();
    let report = eval_output(&EvalOutputArgs {
        merge_candidates: Some(merge_path),
        thin_docs: Some(thin_path),
        search: Some(search_path),
        report: None,
        format: OutputFormat::Json,
    })
    .unwrap();
    assert_eq!(
        report
            .get("semantic_index_output_eval")
            .and_then(Value::as_str),
        Some("pass")
    );
    assert_eq!(report.get("error_count").and_then(Value::as_u64), Some(0));
}

#[test]
fn eval_output_rejects_cross_responsibility_and_query_echo() {
    let root = unique_temp_dir("semantic-index-output-eval-fail");
    let merge_path = root.join("merge.jsonl");
    let search_path = root.join("search.jsonl");
    fs::write(
            &merge_path,
            r#"{"semantic_index_pairs":"ok","kind":"merge-candidates","result_count":1}
{"rank":1,"score":0.95,"same_responsibility":false,"candidate_bucket":"similar:any","left":{"path":"documents/a.md","responsibility_bucket":"shared-policy-documents","node_kind":"document","line_start":1,"line_end":4},"right":{"path":"agents/a.md","responsibility_bucket":"runtime-entrypoints","node_kind":"document","line_start":1,"line_end":4}}
"#,
        )
        .unwrap();
    fs::write(
            &search_path,
            r#"{"semantic_index_search":"ok","query":"long user request should not echo","result_count":0}
"#,
        )
        .unwrap();
    let report = eval_output(&EvalOutputArgs {
        merge_candidates: Some(merge_path),
        thin_docs: None,
        search: Some(search_path),
        report: None,
        format: OutputFormat::Json,
    })
    .unwrap();
    assert_eq!(
        report
            .get("semantic_index_output_eval")
            .and_then(Value::as_str),
        Some("fail")
    );
    assert!(
        report
            .get("error_count")
            .and_then(Value::as_u64)
            .unwrap_or(0)
            >= 3
    );
}

#[test]
fn absolute_include_outside_root_is_rejected() {
    let root = unique_temp_dir("semantic-index-root");
    let outside = unique_temp_dir("semantic-index-outside");
    fs::write(outside.join("outside.md"), "# Outside\nexternal").unwrap();
    let args = BuildArgs {
        root: root.clone(),
        includes: vec![outside],
        excludes: default_excludes(),
        db: root.join("index.sqlite"),
        provider: DEFAULT_PROVIDER.to_string(),
        model: DEFAULT_MODEL.to_string(),
        dim: 64,
        embedding_url: None,
        embedding_batch: DEFAULT_EMBEDDING_BATCH,
        max_file_bytes: DEFAULT_MAX_FILE_BYTES,
    };
    let error = build_index(&args).unwrap_err();
    assert!(error.contains("outside --root"));
}

fn unique_temp_dir(prefix: &str) -> PathBuf {
    let path = env::temp_dir().join(format!("{prefix}-{}-{}", std::process::id(), run_id()));
    fs::create_dir_all(&path).unwrap();
    path
}
