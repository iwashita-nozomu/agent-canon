// @dependency-start
// contract implementation
// responsibility Validates the safe experiment topic and variant segment grammar needed by registry consumers.
// upstream design ../../../../../documents/experiments/experiment-registry.md defines topic and variant identities
// upstream implementation python_text.rs provides Python-compatible whitespace classification
// upstream implementation icu_normalizer::ComposingNormalizer provides NFKC comparison
// downstream implementation experiment_registry.rs validates registry topic and default-variant segments
// @dependency-end

use crate::python_text::is_python_whitespace;
use icu_normalizer::ComposingNormalizer;

/// Validate the shared safe segment grammar without normalizing input into acceptance.
pub fn validate_segment(value: &str, field: &str) -> Result<(), String> {
    if value.is_empty() {
        return Err(format!("{field} must be a non-empty string"));
    }
    if matches!(value, "." | "..") {
        return Err(format!("{field} must not be . or .."));
    }
    if value
        .chars()
        .any(|character| matches!(character, '/' | '\\' | '\0'))
    {
        return Err(format!("{field} must not contain a path separator or NUL"));
    }
    if value.chars().any(is_python_whitespace) {
        return Err(format!("{field} must not contain whitespace"));
    }
    let normalized = ComposingNormalizer::new_nfkc().normalize(value);
    if normalized.as_ref() != value {
        return Err(format!("{field} must not change under normalization"));
    }
    let mut characters = value.chars();
    let valid_first = characters.next().is_some_and(|character| character.is_ascii_alphanumeric());
    if !valid_first
        || !characters.all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '.' | '_' | '-')
        })
    {
        return Err(format!(
            "{field} must match [A-Za-z0-9][A-Za-z0-9._-]*"
        ));
    }
    Ok(())
}
