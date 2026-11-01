// @dependency-start
// contract implementation
// responsibility Shares Python-compatible Unicode string and line handling across native callers.
// downstream implementation agent_search.rs preserves Python input validation
// downstream implementation notebook_quality.rs preserves Python notebook text semantics
// downstream implementation classify_path_risk.rs preserves Python changed-path file parsing
// downstream implementation token_footprints.rs preserves Python JSONL line splitting
// downstream implementation historical_skill_usage.rs preserves byte-oriented history splitting
// @dependency-end

pub fn python_strip(value: &str) -> &str {
    value.trim_matches(is_python_whitespace)
}

pub fn is_python_whitespace(character: char) -> bool {
    character.is_whitespace()
        || matches!(character, '\u{001c}' | '\u{001d}' | '\u{001e}' | '\u{001f}')
}

pub fn python_splitlines(value: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut characters = value.char_indices().peekable();
    while let Some((index, character)) = characters.next() {
        if !is_python_line_break(character) {
            continue;
        }
        lines.push(&value[start..index]);
        let mut end = index + character.len_utf8();
        if character == '\r' && characters.peek().is_some_and(|(_, next)| *next == '\n') {
            end += 1;
            characters.next();
        }
        start = end;
    }
    if start < value.len() {
        lines.push(&value[start..]);
    }
    lines
}

/// Split bytes on Python's ASCII byte-line boundaries (`\r`, `\n`, and `\r\n`).
pub(crate) fn python_bytes_splitlines(value: &[u8]) -> Vec<&[u8]> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut index = 0;
    while index < value.len() {
        let byte = value[index];
        if byte == b'\r' || byte == b'\n' {
            lines.push(&value[start..index]);
            if byte == b'\r' && value.get(index + 1) == Some(&b'\n') {
                index += 1;
            }
            start = index + 1;
        }
        index += 1;
    }
    if start < value.len() {
        lines.push(&value[start..]);
    }
    lines
}

fn is_python_line_break(character: char) -> bool {
    matches!(
        character,
        '\n' | '\r'
            | '\u{000b}'
            | '\u{000c}'
            | '\u{001c}'
            | '\u{001d}'
            | '\u{001e}'
            | '\u{0085}'
            | '\u{2028}'
            | '\u{2029}'
    )
}
