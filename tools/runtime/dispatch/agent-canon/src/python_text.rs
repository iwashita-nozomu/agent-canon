// @dependency-start
// contract implementation
// responsibility Shares Python-compatible Unicode string stripping across native callers.
// downstream implementation agent_search.rs preserves Python input validation
// downstream implementation notebook_quality.rs preserves Python notebook text semantics
// @dependency-end

pub(crate) fn python_strip(value: &str) -> &str {
    value.trim_matches(is_python_whitespace)
}

pub(crate) fn is_python_whitespace(character: char) -> bool {
    character.is_whitespace()
        || matches!(character, '\u{001c}' | '\u{001d}' | '\u{001e}' | '\u{001f}')
}
