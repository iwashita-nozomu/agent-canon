// @dependency-start
// contract implementation
// responsibility Owns deterministic and remote semantic-index embedding and vector operations.
// upstream design ../../../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../../catalog.yaml command catalog and public command source
// downstream implementation ../../../../../repository/github/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use super::args::{validate_dim, DEFAULT_DIM, OPENAI_COMPATIBLE_EMBEDDING_PROVIDER};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::cmp::Ordering;
use std::env;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use crate::runtime_boundary::{resolve_runtime_root, stable_source_key, validate_external_target};

pub(super) const DEFAULT_REMOTE_EMBEDDING_MAX_CHARS: usize = 3000;

pub(super) const VECTOR_EPSILON: f32 = 1.0e-6;

pub(super) const NATURAL_RELATION_FEATURE_FANOUT: usize = 64;

pub(super) const DISCOURSE_TEXT_CHARS: usize = 1600;

pub(super) fn embed_text(text: &str, dim: usize) -> Vec<f32> {
    let text = strip_dependency_manifest(text);
    let mut vector = vec![0.0_f32; dim];
    for token in text_tokens(&text) {
        add_feature(&mut vector, &format!("tok:{token}"), 1.0);
    }
    for gram in char_grams(&text, 3) {
        add_feature(&mut vector, &format!("chr:{gram}"), 0.35);
    }
    normalize_vector(&mut vector);
    vector
}

pub(super) fn embed_one_for_provider(
    provider: &str,
    model: &str,
    dim: usize,
    embedding_url: Option<&str>,
    text: &str,
) -> Result<Vec<f32>, String> {
    let vectors =
        embed_texts_for_provider(provider, model, dim, embedding_url, &[text.to_string()], 1)?;
    vectors
        .into_iter()
        .next()
        .ok_or_else(|| "embedding provider returned no vector".to_string())
}

pub(super) fn embed_texts_for_provider(
    provider: &str,
    model: &str,
    dim: usize,
    embedding_url: Option<&str>,
    texts: &[String],
    batch_size: usize,
) -> Result<Vec<Vec<f32>>, String> {
    if !is_remote_embedding_provider(provider) {
        validate_dim(dim)?;
        return Ok(texts.iter().map(|text| embed_text(text, dim)).collect());
    }
    let endpoint = embedding_endpoint(embedding_url);
    if endpoint.is_empty() {
        return Err(
            "OpenAI-compatible embedding provider requires an explicit endpoint; local server defaults are disabled"
                .to_string(),
        );
    }
    let expected_dim = remote_expected_dim(dim);
    let batch_size = batch_size.max(1);
    let max_chars = remote_embedding_max_chars();
    let mut output = Vec::with_capacity(texts.len());
    for chunk in texts.chunks(batch_size) {
        let bounded_chunk: Vec<String> = chunk
            .iter()
            .map(|text| bound_remote_embedding_text(text, max_chars))
            .collect();
        let mut vectors = request_openai_compatible_embeddings(&endpoint, model, &bounded_chunk)?;
        for vector in &mut vectors {
            if let Some(expected) = expected_dim {
                if vector.len() != expected {
                    return Err(format!(
                        "embedding dimension mismatch: expected {expected}, got {}",
                        vector.len()
                    ));
                }
            }
            normalize_vector(vector);
        }
        output.extend(vectors);
    }
    Ok(output)
}

pub(super) fn is_remote_embedding_provider(provider: &str) -> bool {
    matches!(
        provider,
        OPENAI_COMPATIBLE_EMBEDDING_PROVIDER | "openai-compatible"
    )
}

pub(super) fn remote_expected_dim(dim: usize) -> Option<usize> {
    if dim == 0 || dim == DEFAULT_DIM {
        None
    } else {
        Some(dim)
    }
}

pub(super) fn embedding_endpoint(explicit: Option<&str>) -> String {
    explicit
        .map(str::to_string)
        .or_else(|| env::var("AGENT_CANON_SEMANTIC_INDEX_EMBEDDING_URL").ok())
        .unwrap_or_default()
}

pub(super) fn remote_embedding_max_chars() -> usize {
    env::var("AGENT_CANON_SEMANTIC_INDEX_EMBEDDING_MAX_CHARS")
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(DEFAULT_REMOTE_EMBEDDING_MAX_CHARS)
}

pub(super) fn bound_remote_embedding_text(text: &str, max_chars: usize) -> String {
    if text.chars().count() <= max_chars {
        return text.to_string();
    }
    text.chars().take(max_chars).collect()
}

pub(super) fn request_openai_compatible_embeddings(
    endpoint: &str,
    model: &str,
    texts: &[String],
) -> Result<Vec<Vec<f32>>, String> {
    request_host_embeddings(endpoint, model, texts)
}

const EMBEDDING_IPC_SCHEMA: &str = "agent_canon.embedding.https.request.v1";

fn unix_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

fn json_digest(value: &Value) -> Result<String, String> {
    let bytes = serde_json::to_vec(value).map_err(|error| error.to_string())?;
    let mut digest = Sha256::new();
    digest.update(bytes);
    Ok(format!("{:x}", digest.finalize()))
}

fn embedding_endpoint_allowed(endpoint: &str) -> bool {
    if endpoint.contains(['\0', '\n', '\r', '\\']) {
        return false;
    }
    endpoint.starts_with("https://")
        || endpoint.starts_with("http://localhost/")
        || endpoint.starts_with("http://127.0.0.1/")
        || endpoint.starts_with("http://[::1]/")
}

fn host_uid() -> String {
    env::var("AGENT_CANON_HOST_UID")
        .or_else(|_| env::var("UID"))
        .unwrap_or_else(|_| "unknown".to_string())
}

fn embedding_ipc_dir() -> Result<PathBuf, String> {
    let source = env::current_dir().map_err(|error| error.to_string())?;
    let runtime = resolve_runtime_root(&source)?;
    let dir = runtime
        .join("ipc")
        .join("embedding.https.request")
        .join(stable_source_key(&source));
    validate_external_target(&source, &runtime, &dir, "embedding IPC directory")?;
    fs::create_dir_all(&dir).map_err(|error| format!("create embedding IPC directory: {error}"))?;
    Ok(dir)
}

fn canonical_envelope_bytes(value: &Value, digest_field: &str) -> Result<Vec<u8>, String> {
    let mut copy = value.clone();
    copy.as_object_mut()
        .ok_or_else(|| "embedding IPC envelope must be an object".to_string())?
        .remove(digest_field);
    serde_json::to_vec(&copy).map_err(|error| error.to_string())
}

fn parse_host_embedding_response(
    bytes: &[u8],
    uid: &str,
    nonce: &str,
    request_digest: &str,
    expected_count: usize,
    deadline: u128,
) -> Result<Vec<Vec<f32>>, String> {
    let response: Value = serde_json::from_slice(bytes)
        .map_err(|error| format!("embedding host response is not JSON: {error}"))?;
    let object = response
        .as_object()
        .ok_or_else(|| "embedding host response is not an object".to_string())?;
    if object.get("schema").and_then(Value::as_str) != Some(EMBEDDING_IPC_SCHEMA)
        || object.get("operation").and_then(Value::as_str) != Some("embedding.https.request")
        || object.get("mode").and_then(Value::as_str) != Some("response")
        || object.get("uid").and_then(Value::as_str) != Some(uid)
        || object.get("nonce").and_then(Value::as_str) != Some(nonce)
        || object.get("request_digest").and_then(Value::as_str) != Some(request_digest)
    {
        return Err("embedding host response envelope identity mismatch".to_string());
    }
    let response_digest = object
        .get("response_digest")
        .and_then(Value::as_str)
        .ok_or_else(|| "embedding host response digest is missing".to_string())?;
    let expected_digest = {
        let canonical = canonical_envelope_bytes(&response, "response_digest")?;
        let mut digest = Sha256::new();
        digest.update(canonical);
        format!("{:x}", digest.finalize())
    };
    if response_digest != expected_digest {
        return Err("embedding host response digest mismatch".to_string());
    }
    let response_deadline = object
        .get("deadline_ms")
        .and_then(Value::as_u64)
        .ok_or_else(|| "embedding host response deadline is missing".to_string())?
        as u128;
    if response_deadline != deadline || unix_millis() > deadline {
        return Err("embedding host response is stale or deadline-mismatched".to_string());
    }
    if object.get("status").and_then(Value::as_str) != Some("ok") {
        return Err(object
            .get("error")
            .and_then(Value::as_str)
            .unwrap_or("embedding host request failed")
            .to_string());
    }
    let body = object
        .get("body")
        .ok_or_else(|| "embedding host response body is missing".to_string())?;
    let body_bytes = serde_json::to_vec(body).map_err(|error| error.to_string())?;
    let body_text = String::from_utf8(body_bytes)
        .map_err(|error| format!("embedding host response body is not UTF-8: {error}"))?;
    parse_openai_embeddings_response(&body_text, expected_count)
}

fn request_host_embeddings(
    endpoint: &str,
    model: &str,
    texts: &[String],
) -> Result<Vec<Vec<f32>>, String> {
    if !embedding_endpoint_allowed(endpoint) {
        return Err(
            "embedding endpoint must be HTTPS (or loopback HTTP); redirects and arbitrary URLs are rejected"
                .to_string(),
        );
    }
    let payload = json!({
        "model": model,
        "input": texts,
    });
    let uid = host_uid();
    let deadline = unix_millis()
        + env::var("AGENT_CANON_EMBEDDING_DEADLINE_MS")
            .ok()
            .and_then(|value| value.parse::<u128>().ok())
            .filter(|value| *value > 0)
            .unwrap_or(30_000);
    let nonce = format!(
        "{:x}",
        Sha256::digest(format!("{}:{}:{}", uid, std::process::id(), unix_millis()).as_bytes())
    );
    let request_without_digest = json!({
        "schema": EMBEDDING_IPC_SCHEMA,
        "operation": "embedding.https.request",
        "mode": "request",
        "uid": uid,
        "nonce": nonce,
        "deadline_ms": deadline,
        "redirect_policy": "deny",
        "endpoint": endpoint,
        "body": payload,
    });
    let request_digest = json_digest(&request_without_digest)?;
    let mut request = request_without_digest;
    request.as_object_mut().expect("request object").insert(
        "request_digest".to_string(),
        Value::String(request_digest.clone()),
    );
    let ipc_dir = embedding_ipc_dir()?;
    let request_path = ipc_dir.join(format!("{nonce}.request.json"));
    let response_path = ipc_dir.join(format!("{nonce}.response.json"));
    let request_bytes = serde_json::to_vec(&request).map_err(|error| error.to_string())?;
    let mut request_file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&request_path)
        .map_err(|error| format!("create embedding IPC request: {error}"))?;
    request_file
        .write_all(&request_bytes)
        .map_err(|error| format!("write embedding IPC request: {error}"))?;
    request_file
        .sync_all()
        .map_err(|error| format!("sync embedding IPC request: {error}"))?;
    while !response_path.is_file() && unix_millis() <= deadline {
        thread::sleep(Duration::from_millis(20));
    }
    if !response_path.is_file() {
        let _ = fs::remove_file(&request_path);
        return Err("embedding host adapter timed out waiting for a typed response".to_string());
    }
    let response_bytes = fs::read(&response_path)
        .map_err(|error| format!("read embedding host response: {error}"))?;
    let result = parse_host_embedding_response(
        &response_bytes,
        &uid,
        &nonce,
        &request_digest,
        texts.len(),
        deadline,
    );
    let _ = fs::remove_file(&request_path);
    let _ = fs::remove_file(&response_path);
    result
}

pub(super) fn parse_openai_embeddings_response(
    body: &str,
    expected_count: usize,
) -> Result<Vec<Vec<f32>>, String> {
    let value: Value = serde_json::from_str(body.trim())
        .map_err(|error| format!("embedding response is not JSON: {error}"))?;
    let data = value
        .get("data")
        .and_then(Value::as_array)
        .ok_or_else(|| "embedding response missing data array".to_string())?;
    if data.len() != expected_count {
        return Err(format!(
            "embedding response count mismatch: expected {expected_count}, got {}",
            data.len()
        ));
    }
    let mut vectors: Vec<Option<Vec<f32>>> = vec![None; expected_count];
    for (position, item) in data.iter().enumerate() {
        let index = item
            .get("index")
            .and_then(Value::as_u64)
            .map(|value| value as usize)
            .unwrap_or(position);
        if index >= expected_count {
            return Err(format!("embedding response index {index} out of range"));
        }
        let array = item
            .get("embedding")
            .and_then(Value::as_array)
            .ok_or_else(|| format!("embedding response data[{index}] missing embedding array"))?;
        if array.is_empty() {
            return Err(format!(
                "embedding response data[{index}] has empty embedding"
            ));
        }
        let mut vector = Vec::with_capacity(array.len());
        for value in array {
            let number = value.as_f64().ok_or_else(|| {
                format!("embedding response data[{index}] contains a non-numeric value")
            })?;
            if !number.is_finite() {
                return Err(format!(
                    "embedding response data[{index}] contains a non-finite value"
                ));
            }
            vector.push(number as f32);
        }
        vectors[index] = Some(vector);
    }
    vectors
        .into_iter()
        .enumerate()
        .map(|(index, vector)| {
            vector.ok_or_else(|| format!("embedding response missing vector for index {index}"))
        })
        .collect()
}

#[cfg(test)]
// Protocol fixtures remain adjacent to the response parser they exercise.
#[allow(clippy::items_after_test_module)]
mod tests {
    use super::*;

    fn response(uid: &str, nonce: &str, request_digest: &str, deadline: u128) -> Value {
        let mut value = json!({
            "schema": EMBEDDING_IPC_SCHEMA,
            "operation": "embedding.https.request",
            "mode": "response",
            "uid": uid,
            "nonce": nonce,
            "deadline_ms": deadline,
            "request_digest": request_digest,
            "status": "ok",
            "body": {"data": [{"index": 0, "embedding": [1.0, 0.0]}]},
        });
        let digest = {
            let canonical = canonical_envelope_bytes(&value, "response_digest").unwrap();
            let mut hasher = Sha256::new();
            hasher.update(canonical);
            format!("{:x}", hasher.finalize())
        };
        value
            .as_object_mut()
            .unwrap()
            .insert("response_digest".to_string(), Value::String(digest));
        value
    }

    #[test]
    fn host_response_rejects_replay_and_identity_mismatch() {
        let deadline = unix_millis() + 10_000;
        let valid = response("uid-1", "nonce-1", "request-1", deadline);
        let bytes = serde_json::to_vec(&valid).unwrap();
        assert!(parse_host_embedding_response(
            &bytes,
            "uid-1",
            "nonce-1",
            "request-1",
            1,
            deadline
        )
        .is_ok());
        assert!(parse_host_embedding_response(
            &bytes,
            "uid-1",
            "replayed",
            "request-1",
            1,
            deadline
        )
        .is_err());
        assert!(parse_host_embedding_response(
            &bytes,
            "uid-1",
            "nonce-1",
            "other-request",
            1,
            deadline
        )
        .is_err());
    }

    #[test]
    fn host_response_rejects_stale_and_digest_mismatch() {
        let expired = 1_u128;
        let stale = response("uid-1", "nonce-1", "request-1", expired);
        let stale_bytes = serde_json::to_vec(&stale).unwrap();
        assert!(parse_host_embedding_response(
            &stale_bytes,
            "uid-1",
            "nonce-1",
            "request-1",
            1,
            expired
        )
        .is_err());

        let deadline = unix_millis() + 10_000;
        let mut mismatched = response("uid-1", "nonce-1", "request-1", deadline);
        mismatched
            .as_object_mut()
            .unwrap()
            .insert("response_digest".to_string(), Value::String("0".repeat(64)));
        let mismatched_bytes = serde_json::to_vec(&mismatched).unwrap();
        assert!(parse_host_embedding_response(
            &mismatched_bytes,
            "uid-1",
            "nonce-1",
            "request-1",
            1,
            deadline
        )
        .is_err());
    }
}

pub(super) fn strip_dependency_manifest(text: &str) -> String {
    let trimmed = text.trim_start();
    if !trimmed.starts_with("<!--") || !trimmed.contains("@dependency-start") {
        return text.to_string();
    }
    let Some(end) = trimmed.find("-->") else {
        return text.to_string();
    };
    trimmed[end + 3..].to_string()
}

pub(super) fn text_tokens(text: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut current = String::new();
    for ch in text.chars().flat_map(char::to_lowercase) {
        if ch.is_alphanumeric() || ch == '_' || ch == '-' {
            current.push(ch);
        } else if !current.is_empty() {
            tokens.push(std::mem::take(&mut current));
        }
    }
    if !current.is_empty() {
        tokens.push(current);
    }
    tokens
}

pub(super) fn char_grams(text: &str, width: usize) -> Vec<String> {
    let compact: Vec<char> = text
        .chars()
        .flat_map(char::to_lowercase)
        .filter(|ch| !ch.is_whitespace() && !ch.is_control())
        .collect();
    if compact.len() < width {
        return Vec::new();
    }
    compact
        .windows(width)
        .map(|window| window.iter().collect())
        .collect()
}

pub(super) fn add_feature(vector: &mut [f32], feature: &str, weight: f32) {
    if vector.is_empty() {
        return;
    }
    let digest = Sha256::digest(feature.as_bytes());
    let mut bytes = [0_u8; 8];
    bytes.copy_from_slice(&digest[..8]);
    let hash = u64::from_le_bytes(bytes);
    let index = (hash as usize) % vector.len();
    let sign = if digest[8] % 2 == 0 { 1.0 } else { -1.0 };
    vector[index] += sign * weight;
}

pub(super) fn normalize_vector(vector: &mut [f32]) {
    let norm = vector.iter().map(|value| value * value).sum::<f32>().sqrt();
    if norm == 0.0 {
        return;
    }
    for value in vector.iter_mut() {
        *value /= norm;
    }
}

pub(super) fn dot(left: &[f32], right: &[f32]) -> f32 {
    left.iter()
        .zip(right.iter())
        .map(|(left_value, right_value)| left_value * right_value)
        .sum()
}

pub(super) fn cosine_score(left: &[f32], right: &[f32]) -> f32 {
    dot(left, right).clamp(-1.0, 1.0)
}

pub(super) fn prefix_features(vector: &[f32], min_score: f32) -> Vec<(usize, bool)> {
    let mut features = signed_features_by_magnitude(vector);
    let mut suffix_squared = features
        .iter()
        .map(|(_, _, value)| value * value)
        .sum::<f32>();
    let mut prefix = Vec::new();
    for (index, sign, value) in features.drain(..) {
        if suffix_squared.sqrt() + VECTOR_EPSILON < min_score {
            break;
        }
        prefix.push((index, sign));
        suffix_squared = (suffix_squared - value * value).max(0.0);
    }
    prefix
}

pub(super) fn all_signed_features(vector: &[f32]) -> Vec<(usize, bool)> {
    vector
        .iter()
        .enumerate()
        .filter_map(|(index, value)| {
            if value.abs() <= VECTOR_EPSILON {
                None
            } else {
                Some((index, *value > 0.0))
            }
        })
        .collect()
}

pub(super) fn signed_features_by_magnitude(vector: &[f32]) -> Vec<(usize, bool, f32)> {
    let mut features: Vec<(usize, bool, f32)> = vector
        .iter()
        .enumerate()
        .filter_map(|(index, value)| {
            let magnitude = value.abs();
            if magnitude <= VECTOR_EPSILON {
                None
            } else {
                Some((index, *value > 0.0, magnitude))
            }
        })
        .collect();
    features.sort_by(|left, right| {
        right
            .2
            .partial_cmp(&left.2)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.0.cmp(&right.0))
    });
    features
}
