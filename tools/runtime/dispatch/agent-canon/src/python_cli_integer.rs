// @dependency-start
// contract implementation
// responsibility Parses Python-compatible signed decimal CLI integers and classifies Unicode 15.0 decimal/digit characters.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md native CLI compatibility
// downstream implementation skill_document_reader.rs parses bounded reader options
// downstream implementation notebook_quality.rs parses Python-compatible notebook thresholds
// downstream implementation result_logs/mod.rs parses summary top limits
// downstream implementation extract_docx.rs preserves Python heading digit selection and conversion behavior
// downstream reference ../../../../../tests/fixtures/python_cli_integer/python_oracle.json freezes Python 3.12 Unicode 15.0 nondecimal digits
// @dependency-end

use regex::Regex;
use rustpython_ast::bigint::BigInt;
use std::sync::OnceLock;

const PYTHON_DECIMAL_DIGIT_PATTERN: &str = r"^[\p{Nd}&&\p{Age:15.0}]$";

// Numeric_Type=Digit ranges from Unicode 15.0 DerivedNumericType.txt. Python's
// str.isdigit() accepts these, while int(character) accepts decimal digits only.
const PYTHON_NONDECIMAL_DIGIT_RANGES: &[(u32, u32)] = &[
    (0x00b2, 0x00b3),
    (0x00b9, 0x00b9),
    (0x1369, 0x1371),
    (0x19da, 0x19da),
    (0x2070, 0x2070),
    (0x2074, 0x2079),
    (0x2080, 0x2089),
    (0x2460, 0x2468),
    (0x2474, 0x247c),
    (0x2488, 0x2490),
    (0x24ea, 0x24ea),
    (0x24f5, 0x24fd),
    (0x24ff, 0x24ff),
    (0x2776, 0x277e),
    (0x2780, 0x2788),
    (0x278a, 0x2792),
    (0x10a40, 0x10a43),
    (0x10e60, 0x10e68),
    (0x11052, 0x1105a),
    (0x1f100, 0x1f10a),
];

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

pub fn decimal_digit_value(character: char) -> Option<u8> {
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

pub fn is_python_digit(character: char) -> bool {
    decimal_digit_value(character).is_some()
        || PYTHON_NONDECIMAL_DIGIT_RANGES
            .iter()
            .any(|(start, end)| (*start..=*end).contains(&(character as u32)))
}

pub fn parse(value: &str) -> Option<BigInt> {
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
                || digits
                    .peek()
                    .copied()
                    .and_then(decimal_digit_value)
                    .is_none()
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

pub fn is_argparse_negative_number(value: &str) -> bool {
    value
        .strip_prefix('-')
        .is_some_and(|digits| !digits.is_empty() && digits.chars().all(is_python_decimal_digit))
}

#[cfg(test)]
mod tests {
    use super::{decimal_digit_value, is_python_digit};
    use serde_json::Value;

    const PYTHON_ORACLE: &str =
        include_str!("../../../../../tests/fixtures/python_cli_integer/python_oracle.json");

    #[test]
    fn nondecimal_python_digits_match_the_frozen_python_unicode_oracle() {
        let oracle: Value = serde_json::from_str(PYTHON_ORACLE).unwrap();
        assert_eq!(oracle["python_version"].as_str(), Some("3.12.3"));
        assert_eq!(oracle["unicode_version"].as_str(), Some("15.0.0"));
        let ranges = oracle["extra_digit_ranges"].as_array().unwrap();
        let mut count = 0_u64;
        for range in ranges {
            let start = range[0].as_u64().unwrap() as u32;
            let end = range[1].as_u64().unwrap() as u32;
            for codepoint in start..=end {
                let character = char::from_u32(codepoint).unwrap();
                assert!(is_python_digit(character), "U+{codepoint:04X}");
                assert_eq!(decimal_digit_value(character), None, "U+{codepoint:04X}");
                count += 1;
            }
        }
        assert_eq!(count, oracle["extra_digit_count"].as_u64().unwrap());
        assert!(!is_python_digit('¼'));
        assert_eq!(decimal_digit_value('٢'), Some(2));
        assert_eq!(decimal_digit_value('２'), Some(2));
    }
}
