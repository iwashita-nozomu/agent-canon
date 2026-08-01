// @dependency-start
// contract implementation
// responsibility Owns deterministic and remote semantic-index embedding and vector operations.
// upstream design ../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../tools/catalog.yaml command catalog and public command source
// downstream implementation ../../../../tools/agent_tools/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use super::args::{validate_dim, DEFAULT_DIM, OPENAI_COMPATIBLE_EMBEDDING_PROVIDER};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::cmp::Ordering;
use std::env;
use std::process::Command;

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
    let payload = json!({
        "model": model,
        "input": texts,
    })
    .to_string();
    let curl = env::var("AGENT_CANON_EMBEDDING_CURL").unwrap_or_else(|_| "curl".to_string());
    let output = Command::new(curl)
        .arg("-fsS")
        .arg("--retry")
        .arg("2")
        .arg("--retry-delay")
        .arg("1")
        .arg("-H")
        .arg("Content-Type: application/json")
        .arg("-d")
        .arg(payload)
        .arg(endpoint)
        .output()
        .map_err(|error| format!("embedding request failed to launch curl: {error}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "embedding request failed for {endpoint}: status={} stderr={}",
            output.status,
            stderr.trim()
        ));
    }
    let body = String::from_utf8(output.stdout)
        .map_err(|error| format!("embedding response was not utf-8: {error}"))?;
    parse_openai_embeddings_response(&body, texts.len())
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
