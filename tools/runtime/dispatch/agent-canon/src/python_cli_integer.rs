// @dependency-start
// contract implementation
// responsibility Parses Python-compatible signed decimal CLI integers using Unicode 15.0 decimal digits.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md native CLI compatibility
// downstream implementation skill_document_reader.rs parses bounded reader options
// @dependency-end

use regex::Regex;
use rustpython_ast::bigint::BigInt;
use std::sync::OnceLock;

const PYTHON_DECIMAL_DIGIT_PATTERN: &str = r"^[\p{Nd}&&\p{Age:15.0}]$";

fn decimal_digit_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(PYTHON_DECIMAL_DIGIT_PATTERN)
            .expect("the Python Unicode decimal digit pattern is valid")
    })
}

fn is_python_decimal_digit(character: char) -> bool {
    let mut encoded = [0; 4];
    decimal_digit_pattern().is_match(character.encode_utf8(&mut encoded))
}

fn decimal_digit_value(character: char) -> Option<u8> {
    if !is_python_decimal_digit(character) {
        return None;
    }
    let codepoint = character as u32;
    let mut zero = codepoint;
    while let Some(previous_codepoint) = zero.checked_sub(1) {
        let Some(previous) = char::from_u32(previous_codepoint) else {
            break;
        };
        if !is_python_decimal_digit(previous) {
            break;
        }
        zero = previous_codepoint;
    }
    u8::try_from(codepoint.checked_sub(zero)? % 10).ok()
}

pub(crate) fn parse(value: &str) -> Option<BigInt> {
    let value = value.trim();
    let (sign, digits) = if let Some(digits) = value.strip_prefix('+') {
        ("+", digits)
    } else if let Some(digits) = value.strip_prefix('-') {
        ("-", digits)
    } else {
        ("", value)
    };
    if digits.is_empty() {
        return None;
    }

    let mut normalized = String::with_capacity(value.len());
    normalized.push_str(sign);
    let mut previous_was_digit = false;
    let mut digits = digits.chars().peekable();
    while let Some(character) = digits.next() {
        if character == '_' {
            if !previous_was_digit
                || !digits
                    .peek()
                    .copied()
                    .and_then(decimal_digit_value)
                    .is_some()
            {
                return None;
            }
            previous_was_digit = false;
            continue;
        }
        let digit = decimal_digit_value(character)?;
        normalized.push(char::from(b'0' + digit));
        previous_was_digit = true;
    }
    if !previous_was_digit {
        return None;
    }
    normalized.parse().ok()
}

pub(crate) fn is_argparse_negative_number(value: &str) -> bool {
    value
        .strip_prefix('-')
        .is_some_and(|digits| !digits.is_empty() && digits.chars().all(is_python_decimal_digit))
}
