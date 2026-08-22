// @dependency-start
// contract implementation
// responsibility Owns semantic-index build and provider-embedding orchestration.
// upstream design ../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../tools/catalog.yaml command catalog and public command source
// downstream implementation ../../../../tools/agent_tools/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use super::args::{BuildArgs, EmbedProviderArgs};
use super::embedding::{embed_text, embed_texts_for_provider, is_remote_embedding_provider};
use super::model::{count_lines, relative_path};
use super::source::{discover_files, path_metadata_size, segment_text};
use super::storage::{
    clear_index, ensure_parent_dir, finish_write_db, init_schema, insert_embedding, insert_file,
    insert_node, load_missing_node_texts, open_cache_connection, prepare_write_db,
};
use crate::runtime_boundary::{
    resolve_runtime_root, runtime_root_is_explicit, validate_external_target,
};
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone)]
pub(super) struct BuildStats {
    pub(super) files: usize,
    pub(super) nodes: usize,
    pub(super) embeddings: usize,
    pub(super) db: PathBuf,
}

#[derive(Debug, Clone)]
pub(super) struct EmbedStats {
    pub(super) nodes: usize,
    pub(super) embeddings: usize,
    pub(super) db: PathBuf,
}

pub(super) fn build_index(args: &BuildArgs) -> Result<BuildStats, String> {
    let runtime_root = resolve_runtime_root(&args.root)?;
    if runtime_root_is_explicit() || !cfg!(test) {
        validate_external_target(
            &args.root,
            &runtime_root,
            &args.db,
            "semantic-index database",
        )?;
    }
    ensure_parent_dir(&args.db)?;
    let write_db = prepare_write_db(&args.db)?;
    let mut conn = open_cache_connection(&write_db)?;
    init_schema(&conn)?;
    clear_index(&conn)?;
    let files = discover_files(
        &args.root,
        &args.includes,
        &args.excludes,
        args.max_file_bytes,
    )?;
    let root_for_relative = fs::canonicalize(&args.root).unwrap_or_else(|_| args.root.clone());
    let tx = conn.transaction().map_err(|error| error.to_string())?;
    let mut file_count = 0;
    let mut node_count = 0;
    let mut embedding_count = 0;
    let mut remote_embedding_inputs: Vec<(i64, String)> = Vec::new();
    for path in files {
        let text = fs::read_to_string(&path).map_err(|error| {
            format!("failed to read indexable file {}: {error}", path.display())
        })?;
        let relative = relative_path(&root_for_relative, &path);
        let line_count = count_lines(&text);
        let file_id = insert_file(&tx, &relative, &text, path_metadata_size(&path)?)?;
        file_count += 1;
        let nodes = segment_text(&relative, &text);
        let mut inserted_ids: Vec<i64> = Vec::new();
        for node in nodes {
            let parent_id = node
                .parent_index
                .and_then(|parent| inserted_ids.get(parent).copied());
            let node_id = insert_node(&tx, file_id, parent_id, &node)?;
            if is_remote_embedding_provider(&args.provider) {
                remote_embedding_inputs.push((node_id, node.text.clone()));
            } else {
                let vector = embed_text(&node.text, args.dim);
                insert_embedding(&tx, node_id, &args.provider, &args.model, args.dim, &vector)?;
                embedding_count += 1;
            }
            inserted_ids.push(node_id);
            node_count += 1;
        }
        if line_count == 0 {
            continue;
        }
    }
    if is_remote_embedding_provider(&args.provider) {
        let texts: Vec<String> = remote_embedding_inputs
            .iter()
            .map(|(_, text)| text.clone())
            .collect();
        let vectors = embed_texts_for_provider(
            &args.provider,
            &args.model,
            args.dim,
            args.embedding_url.as_deref(),
            &texts,
            args.embedding_batch,
        )?;
        if vectors.len() != remote_embedding_inputs.len() {
            return Err(format!(
                "embedding provider returned {} vectors for {} nodes",
                vectors.len(),
                remote_embedding_inputs.len()
            ));
        }
        for ((node_id, _), vector) in remote_embedding_inputs.iter().zip(vectors.iter()) {
            insert_embedding(
                &tx,
                *node_id,
                &args.provider,
                &args.model,
                vector.len(),
                vector,
            )?;
            embedding_count += 1;
        }
    }
    tx.commit().map_err(|error| error.to_string())?;
    finish_write_db(&write_db, &args.db)?;
    Ok(BuildStats {
        files: file_count,
        nodes: node_count,
        embeddings: embedding_count,
        db: args.db.clone(),
    })
}

pub(super) fn embed_existing_nodes(args: &EmbedProviderArgs) -> Result<EmbedStats, String> {
    let runtime_root = resolve_runtime_root(&args.root)?;
    if runtime_root_is_explicit() || !cfg!(test) {
        validate_external_target(
            &args.root,
            &runtime_root,
            &args.db,
            "semantic-index database",
        )?;
    }
    let mut conn = open_cache_connection(&args.db)?;
    let node_texts =
        load_missing_node_texts(&conn, &args.root, &args.provider, &args.model, args.dim)?;
    if node_texts.is_empty() {
        return Ok(EmbedStats {
            nodes: 0,
            embeddings: 0,
            db: args.db.clone(),
        });
    }
    let mut embedding_count = 0;
    for chunk in node_texts.chunks(args.embedding_batch.max(1)) {
        let texts: Vec<String> = chunk.iter().map(|(_, text)| text.clone()).collect();
        let vectors = embed_texts_for_provider(
            &args.provider,
            &args.model,
            args.dim,
            args.embedding_url.as_deref(),
            &texts,
            args.embedding_batch,
        )?;
        let tx = conn.transaction().map_err(|error| error.to_string())?;
        for ((node_id, _), vector) in chunk.iter().zip(vectors.iter()) {
            insert_embedding(
                &tx,
                *node_id,
                &args.provider,
                &args.model,
                vector.len(),
                vector,
            )?;
            embedding_count += 1;
        }
        tx.commit().map_err(|error| error.to_string())?;
    }
    Ok(EmbedStats {
        nodes: node_texts.len(),
        embeddings: embedding_count,
        db: args.db.clone(),
    })
}
