// @dependency-start
// contract implementation
// responsibility Owns semantic-index SQLite schema, persistence, transactions, and atomic database publish.
// upstream design ../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../tools/catalog.yaml command catalog and public command source
// downstream implementation ../../../../tools/agent_tools/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use super::args::{
    DiscourseRelationsArgs, NaturalRelationsArgs, SimilarArgs, SimilarKind, ThinDocsArgs,
};
use super::model::{blob_to_vector, hex_hash, vector_to_blob, IndexedNode, TextNode};
use crate::runtime_boundary::{
    resolve_runtime_root, runtime_root_is_explicit, validate_external_target,
};
use rusqlite::{params, Connection};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

pub(super) struct SimilarPairRow {
    pub(super) left_node_id: i64,
    pub(super) right_node_id: i64,
    pub(super) score: f32,
    pub(super) rank: usize,
}

pub(super) struct ThinDocRow {
    pub(super) node_id: i64,
    pub(super) thin_score: f32,
    pub(super) rank: usize,
    pub(super) action: String,
    pub(super) reasons: Vec<String>,
    pub(super) total_lines: usize,
    pub(super) meaningful_lines: usize,
    pub(super) link_lines: usize,
    pub(super) wrapper_phrase_hits: usize,
    pub(super) link_density: f32,
    pub(super) target_node_id: Option<i64>,
    pub(super) target_score: Option<f32>,
}

pub(super) struct NaturalRelationRow {
    pub(super) left_node_id: i64,
    pub(super) right_node_id: i64,
    pub(super) similarity_score: f32,
    pub(super) left_is_kind_of_right_score: f32,
    pub(super) right_is_kind_of_left_score: f32,
    pub(super) relation_kind: String,
    pub(super) rank: usize,
}

pub(super) struct DiscourseRelationRow {
    pub(super) left_node_id: i64,
    pub(super) right_node_id: i64,
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

pub(super) fn temporary_db_identity() -> String {
    run_id()
}

pub(super) fn validate_analysis_db(root: &Path, db: &Path) -> Result<(), String> {
    let runtime_root = resolve_runtime_root(root)?;
    if cfg!(test) && !runtime_root_is_explicit() {
        return Ok(());
    }
    validate_external_target(root, &runtime_root, db, "semantic-index database").map(|_| ())
}

fn unix_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

fn run_id() -> String {
    unix_millis().to_string()
}

pub(super) fn persist_pairs(args: &SimilarArgs, pairs: &[SimilarPairRow]) -> Result<(), String> {
    validate_analysis_db(&args.root, &args.db)?;
    let write_db = prepare_existing_write_db(&args.db)?;
    let conn = open_cache_connection(&write_db)?;
    init_schema(&conn)?;
    let run_id = run_id();
    let kind = match args.kind {
        SimilarKind::Similar => "similar",
        SimilarKind::MergeCandidates => "merge-candidates",
    };
    conn.execute(
        "INSERT INTO analysis_runs(run_id, kind, created_at, params_json) VALUES (?1, ?2, ?3, ?4)",
        params![
            run_id,
            kind,
            unix_millis().to_string(),
            json!({
                "min_score": args.min_score,
                "top_k": args.top_k,
                "cross_file_only": args.cross_file_only,
                "provider": args.provider,
                "model": args.model,
                "dim": args.dim
            })
            .to_string()
        ],
    )
    .map_err(|error| error.to_string())?;
    for pair in pairs {
        conn.execute(
            "INSERT INTO similar_pairs(run_id, left_node_id, right_node_id, score, rank) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                run_id,
                pair.left_node_id,
                pair.right_node_id,
                pair.score,
                pair.rank as i64
            ],
        )
        .map_err(|error| error.to_string())?;
    }
    finish_write_db(&write_db, &args.db)?;
    Ok(())
}

pub(super) fn persist_thin_docs(
    args: &ThinDocsArgs,
    candidates: &[ThinDocRow],
) -> Result<(), String> {
    validate_analysis_db(&args.root, &args.db)?;
    let write_db = prepare_existing_write_db(&args.db)?;
    let conn = open_cache_connection(&write_db)?;
    init_schema(&conn)?;
    let run_id = run_id();
    conn.execute(
        "INSERT INTO analysis_runs(run_id, kind, created_at, params_json) VALUES (?1, ?2, ?3, ?4)",
        params![
            run_id,
            "thin-docs",
            unix_millis().to_string(),
            json!({
                "min_thin_score": args.min_thin_score,
                "min_neighbor_score": args.min_neighbor_score,
                "top_k": args.top_k,
                "provider": args.provider,
                "model": args.model,
                "dim": args.dim
            })
            .to_string()
        ],
    )
    .map_err(|error| error.to_string())?;
    for candidate in candidates {
        conn.execute(
            r#"
            INSERT INTO thin_docs(
                run_id, node_id, thin_score, rank, action, reasons_json,
                metrics_json, target_node_id, target_score
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)
            "#,
            params![
                run_id,
                candidate.node_id,
                candidate.thin_score,
                candidate.rank as i64,
                candidate.action,
                json!(candidate.reasons).to_string(),
                json!({
                    "total_lines": candidate.total_lines,
                    "meaningful_lines": candidate.meaningful_lines,
                    "link_lines": candidate.link_lines,
                    "wrapper_phrase_hits": candidate.wrapper_phrase_hits,
                    "link_density": candidate.link_density
                })
                .to_string(),
                candidate.target_node_id,
                candidate.target_score,
            ],
        )
        .map_err(|error| error.to_string())?;
    }
    finish_write_db(&write_db, &args.db)?;
    Ok(())
}

pub(super) fn persist_natural_relations(
    args: &NaturalRelationsArgs,
    relations: &[NaturalRelationRow],
) -> Result<(), String> {
    validate_analysis_db(&args.root, &args.db)?;
    let write_db = prepare_existing_write_db(&args.db)?;
    let conn = open_cache_connection(&write_db)?;
    init_schema(&conn)?;
    let run_id = run_id();
    conn.execute(
        "INSERT INTO analysis_runs(run_id, kind, created_at, params_json) VALUES (?1, ?2, ?3, ?4)",
        params![
            run_id,
            "natural-relations",
            unix_millis().to_string(),
            json!({
                "min_similarity": args.min_similarity,
                "min_kind_of_score": args.min_kind_of_score,
                "top_k": args.top_k,
                "cross_file_only": args.cross_file_only,
                "provider": args.provider,
                "model": args.model,
                "dim": args.dim
            })
            .to_string()
        ],
    )
    .map_err(|error| error.to_string())?;
    for relation in relations {
        conn.execute(
            r#"
            INSERT INTO natural_language_relations(
                run_id, left_node_id, right_node_id, similarity_score,
                left_is_kind_of_right_score, right_is_kind_of_left_score,
                relation_kind, rank
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)
            "#,
            params![
                run_id,
                relation.left_node_id,
                relation.right_node_id,
                relation.similarity_score,
                relation.left_is_kind_of_right_score,
                relation.right_is_kind_of_left_score,
                relation.relation_kind,
                relation.rank as i64,
            ],
        )
        .map_err(|error| error.to_string())?;
    }
    finish_write_db(&write_db, &args.db)?;
    Ok(())
}

pub(super) fn persist_discourse_relations(
    args: &DiscourseRelationsArgs,
    relations: &[DiscourseRelationRow],
) -> Result<(), String> {
    validate_analysis_db(&args.root, &args.db)?;
    let write_db = prepare_existing_write_db(&args.db)?;
    let conn = open_cache_connection(&write_db)?;
    init_schema(&conn)?;
    let run_id = run_id();
    conn.execute(
        "INSERT INTO analysis_runs(run_id, kind, created_at, params_json) VALUES (?1, ?2, ?3, ?4)",
        params![
            run_id,
            "discourse-relations",
            unix_millis().to_string(),
            json!({
                "profile": args.profile,
                "min_naturalness": args.min_naturalness,
                "window": args.window,
                "top_k": args.top_k,
                "provider": args.provider,
                "model": args.model,
                "dim": args.dim
            })
            .to_string()
        ],
    )
    .map_err(|error| error.to_string())?;
    for relation in relations {
        conn.execute(
            r#"
            INSERT INTO discourse_relations(
                run_id, left_node_id, right_node_id, similarity_score,
                connective_profile, relation_family, relation_schema,
                surface_phrase, inverse_surface_phrase, surface_order,
                logical_direction, naturalness_score, inverse_naturalness_score,
                direction_confidence, ambiguity, gap_flags_json, rank
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17)
            "#,
            params![
                run_id,
                relation.left_node_id,
                relation.right_node_id,
                relation.similarity_score,
                relation.connective_profile,
                relation.relation_family,
                relation.relation_schema,
                relation.surface_phrase,
                relation.inverse_surface_phrase,
                relation.surface_order,
                relation.logical_direction,
                relation.naturalness_score,
                relation.inverse_naturalness_score,
                relation.direction_confidence,
                relation.ambiguity,
                json!(relation.gap_flags).to_string(),
                relation.rank as i64,
            ],
        )
        .map_err(|error| error.to_string())?;
    }
    finish_write_db(&write_db, &args.db)?;
    Ok(())
}

pub(super) fn init_schema(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        r#"
        PRAGMA busy_timeout = 5000;
        PRAGMA user_version = 1;
        CREATE TABLE IF NOT EXISTS files(
            file_id INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            content_hash TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            indexed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS nodes(
            node_id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            node_kind TEXT NOT NULL,
            parent_node_id INTEGER,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            text_hash TEXT NOT NULL,
            FOREIGN KEY(file_id) REFERENCES files(file_id)
        );
        CREATE TABLE IF NOT EXISTS embeddings(
            node_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            dtype TEXT NOT NULL,
            vector BLOB NOT NULL,
            PRIMARY KEY(node_id, provider, model, dim),
            FOREIGN KEY(node_id) REFERENCES nodes(node_id)
        );
        CREATE TABLE IF NOT EXISTS analysis_runs(
            run_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL,
            params_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS similar_pairs(
            run_id TEXT NOT NULL,
            left_node_id INTEGER NOT NULL,
            right_node_id INTEGER NOT NULL,
            score REAL NOT NULL,
            rank INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS thin_docs(
            run_id TEXT NOT NULL,
            node_id INTEGER NOT NULL,
            thin_score REAL NOT NULL,
            rank INTEGER NOT NULL,
            action TEXT NOT NULL,
            reasons_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            target_node_id INTEGER,
            target_score REAL
        );
        CREATE TABLE IF NOT EXISTS natural_language_relations(
            run_id TEXT NOT NULL,
            left_node_id INTEGER NOT NULL,
            right_node_id INTEGER NOT NULL,
            similarity_score REAL NOT NULL,
            left_is_kind_of_right_score REAL NOT NULL,
            right_is_kind_of_left_score REAL NOT NULL,
            relation_kind TEXT NOT NULL,
            rank INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS discourse_relations(
            run_id TEXT NOT NULL,
            left_node_id INTEGER NOT NULL,
            right_node_id INTEGER NOT NULL,
            similarity_score REAL NOT NULL,
            connective_profile TEXT NOT NULL,
            relation_family TEXT NOT NULL,
            relation_schema TEXT NOT NULL,
            surface_phrase TEXT NOT NULL,
            inverse_surface_phrase TEXT,
            surface_order TEXT NOT NULL,
            logical_direction TEXT NOT NULL,
            naturalness_score REAL NOT NULL,
            inverse_naturalness_score REAL,
            direction_confidence REAL NOT NULL,
            ambiguity TEXT NOT NULL,
            gap_flags_json TEXT NOT NULL,
            rank INTEGER NOT NULL
        );
        "#,
    )
    .map_err(|error| error.to_string())
}

pub(super) fn open_cache_connection(path: &Path) -> Result<Connection, String> {
    Connection::open(path).map_err(|error| error.to_string())
}

pub(super) fn clear_index(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        r#"
        DELETE FROM thin_docs;
        DELETE FROM discourse_relations;
        DELETE FROM natural_language_relations;
        DELETE FROM similar_pairs;
        DELETE FROM analysis_runs;
        DELETE FROM embeddings;
        DELETE FROM nodes;
        DELETE FROM files;
        "#,
    )
    .map_err(|error| error.to_string())
}

pub(super) fn insert_file(
    conn: &Connection,
    path: &str,
    text: &str,
    size_bytes: u64,
) -> Result<i64, String> {
    conn.execute(
        "INSERT INTO files(path, content_hash, size_bytes, indexed_at) VALUES (?1, ?2, ?3, ?4)",
        params![
            path,
            hex_hash(text),
            size_bytes as i64,
            unix_millis().to_string()
        ],
    )
    .map_err(|error| error.to_string())?;
    Ok(conn.last_insert_rowid())
}

pub(super) fn insert_node(
    conn: &Connection,
    file_id: i64,
    parent_id: Option<i64>,
    node: &TextNode,
) -> Result<i64, String> {
    conn.execute(
        "INSERT INTO nodes(file_id, node_kind, parent_node_id, line_start, line_end, text_hash) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![
            file_id,
            node.kind,
            parent_id,
            node.line_start as i64,
            node.line_end as i64,
            hex_hash(&node.text)
        ],
    )
    .map_err(|error| error.to_string())?;
    Ok(conn.last_insert_rowid())
}

pub(super) fn insert_embedding(
    conn: &Connection,
    node_id: i64,
    provider: &str,
    model: &str,
    dim: usize,
    vector: &[f32],
) -> Result<(), String> {
    conn.execute(
        "INSERT OR REPLACE INTO embeddings(node_id, provider, model, dim, dtype, vector) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
        params![node_id, provider, model, dim as i64, "f32le", vector_to_blob(vector)],
    )
    .map_err(|error| error.to_string())?;
    Ok(())
}

pub(super) fn load_nodes(
    conn: &Connection,
    provider: &str,
    model: &str,
    dim: usize,
) -> Result<Vec<IndexedNode>, String> {
    let mut statement = conn
        .prepare(
            r#"
            SELECT n.node_id, n.file_id, f.path, n.node_kind, n.line_start, n.line_end, e.vector
            FROM nodes n
            JOIN files f ON f.file_id = n.file_id
            JOIN embeddings e ON e.node_id = n.node_id
            WHERE e.provider = ?1 AND e.model = ?2 AND e.dim = ?3
            "#,
        )
        .map_err(|error| error.to_string())?;
    let rows = statement
        .query_map(params![provider, model, dim as i64], |row| {
            let blob: Vec<u8> = row.get(6)?;
            Ok(IndexedNode {
                node_id: row.get(0)?,
                file_id: row.get(1)?,
                path: row.get(2)?,
                kind: row.get(3)?,
                line_start: row.get(4)?,
                line_end: row.get(5)?,
                vector: blob_to_vector(&blob),
            })
        })
        .map_err(|error| error.to_string())?;
    let mut nodes = Vec::new();
    for row in rows {
        let node = row.map_err(|error| error.to_string())?;
        if node.vector.len() == dim {
            nodes.push(node);
        }
    }
    Ok(nodes)
}

pub(super) fn load_file_paths(conn: &Connection) -> Result<Vec<String>, String> {
    let mut statement = conn
        .prepare("SELECT path FROM files ORDER BY path")
        .map_err(|error| error.to_string())?;
    let rows = statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(|error| error.to_string())?;
    let mut paths = Vec::new();
    for row in rows {
        paths.push(row.map_err(|error| error.to_string())?);
    }
    Ok(paths)
}

pub(super) fn provider_dimensions(
    conn: &Connection,
    provider: &str,
    model: &str,
) -> Result<Vec<usize>, String> {
    let mut statement = conn
        .prepare(
            r#"
            SELECT DISTINCT dim
            FROM embeddings
            WHERE provider = ?1 AND model = ?2
            ORDER BY dim
            "#,
        )
        .map_err(|error| error.to_string())?;
    let rows = statement
        .query_map(params![provider, model], |row| {
            let dim: i64 = row.get(0)?;
            Ok(dim as usize)
        })
        .map_err(|error| error.to_string())?;
    let mut dims = Vec::new();
    for row in rows {
        dims.push(row.map_err(|error| error.to_string())?);
    }
    Ok(dims)
}

pub(super) fn resolve_provider_dim(
    conn: &Connection,
    provider: &str,
    model: &str,
    requested_dim: usize,
) -> Result<usize, String> {
    if requested_dim > 0 {
        return Ok(requested_dim);
    }
    let dims = provider_dimensions(conn, provider, model)?;
    match dims.as_slice() {
        [dim] => Ok(*dim),
        [] => Err(format!(
            "no embeddings found for provider={provider} model={model}"
        )),
        _ => Err(format!(
            "multiple embedding dimensions found for provider={provider} model={model}; pass --dim"
        )),
    }
}

pub(super) fn load_missing_node_texts(
    conn: &Connection,
    root: &Path,
    provider: &str,
    model: &str,
    dim: usize,
) -> Result<Vec<(i64, String)>, String> {
    let root_for_files = fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    let mut statement = conn
        .prepare(
            r#"
            SELECT n.node_id, f.path, n.line_start, n.line_end
            FROM nodes n
            JOIN files f ON f.file_id = n.file_id
            WHERE NOT EXISTS (
                SELECT 1
                FROM embeddings e
                WHERE e.node_id = n.node_id
                  AND e.provider = ?1
                  AND e.model = ?2
                  AND (?3 = 0 OR e.dim = ?3)
            )
            ORDER BY n.node_id
            "#,
        )
        .map_err(|error| error.to_string())?;
    let rows = statement
        .query_map(params![provider, model, dim as i64], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, i64>(3)?,
            ))
        })
        .map_err(|error| error.to_string())?;
    let mut output = Vec::new();
    for row in rows {
        let (node_id, relative, line_start, line_end) = row.map_err(|error| error.to_string())?;
        let path = root_for_files.join(&relative);
        let text = fs::read_to_string(&path)
            .map_err(|error| format!("failed to read indexed file {}: {error}", path.display()))?;
        output.push((node_id, line_range_text(&text, line_start, line_end)));
    }
    Ok(output)
}

pub(super) fn line_range_text(text: &str, line_start: i64, line_end: i64) -> String {
    text.lines()
        .enumerate()
        .filter_map(|(index, line)| {
            let line_number = index as i64 + 1;
            if line_number >= line_start && line_number <= line_end {
                Some(line)
            } else {
                None
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
}

pub(super) fn prepare_write_db(target: &Path) -> Result<PathBuf, String> {
    if is_local_temp_path(target) {
        let _ = fs::remove_file(target);
        return Ok(target.to_path_buf());
    }
    Ok(temp_db_path(target))
}

pub(super) fn prepare_existing_write_db(target: &Path) -> Result<PathBuf, String> {
    if is_local_temp_path(target) {
        return Ok(target.to_path_buf());
    }
    let temp = temp_db_path(target);
    let _ = fs::remove_file(&temp);
    fs::copy(target, &temp).map_err(|error| {
        format!(
            "failed to copy cache db {} to temp {}: {error}",
            target.display(),
            temp.display()
        )
    })?;
    Ok(temp)
}

pub(super) fn finish_write_db(write_db: &Path, target: &Path) -> Result<(), String> {
    if write_db == target {
        return Ok(());
    }
    ensure_parent_dir(target)?;
    let publish_path = sibling_publish_path(target);
    let _ = fs::remove_file(&publish_path);
    fs::copy(write_db, &publish_path).map_err(|error| {
        format!(
            "failed to copy temp cache db {} to publish path {}: {error}",
            write_db.display(),
            publish_path.display()
        )
    })?;
    fs::rename(&publish_path, target).map_err(|error| {
        let _ = fs::remove_file(&publish_path);
        format!(
            "failed to publish temp cache db {} to {}: {error}",
            publish_path.display(),
            target.display()
        )
    })?;
    let _ = fs::remove_file(write_db);
    Ok(())
}

fn sibling_publish_path(target: &Path) -> PathBuf {
    let file_name = target
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("index.sqlite");
    target.with_file_name(format!(".{file_name}.tmp-{}", run_id()))
}

fn temp_db_path(target: &Path) -> PathBuf {
    let digest = Sha256::digest(target.to_string_lossy().as_bytes());
    let suffix: String = digest[..8]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    env::temp_dir().join(format!(
        "agent-canon-semantic-index-{suffix}-{}.sqlite",
        run_id()
    ))
}

fn is_local_temp_path(path: &Path) -> bool {
    path.is_absolute() && path.starts_with(env::temp_dir())
}

pub(super) fn ensure_parent_dir(path: &Path) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| {
            format!(
                "failed to create parent directory {}: {error}",
                parent.display()
            )
        })?;
    }
    Ok(())
}
