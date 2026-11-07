// @dependency-start
// contract implementation
// responsibility Parses Python-compatible signed decimal CLI integers, classifies Unicode 15.0 digits, and exactly divides integers to binary64.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md native CLI compatibility
// upstream environment ../Cargo.toml pins exact rational and numeric trait dependencies
// upstream reference ../../../../../tests/fixtures/python_integer_division/python_golden.json freezes CPython 3.12.3 integer division results
// downstream implementation token_footprints.rs uses Python-compatible integer division for token ratios
// downstream implementation skill_document_reader.rs parses bounded reader options
// downstream implementation notebook_quality.rs parses Python-compatible notebook thresholds
// downstream implementation result_logs/mod.rs parses summary top limits
// downstream implementation extract_docx.rs preserves Python heading digit selection and conversion behavior
// downstream reference ../../../../../tests/fixtures/python_cli_integer/python_oracle.json freezes Python 3.12 Unicode 15.0 nondecimal digits
// @dependency-end

use num_rational::Ratio;
use num_traits::ToPrimitive;
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

/// Divide arbitrary-precision integers with correctly rounded binary64 semantics.
pub fn true_divide(numerator: &BigInt, denominator: &BigInt) -> Result<f64, String> {
    if denominator == &BigInt::from(0_u8) {
        return Err("division by zero".to_owned());
    }
    let value = Ratio::new(numerator.clone(), denominator.clone())
        .to_f64()
        .ok_or_else(|| "integer division result too large for a float".to_owned())?;
    if value.is_finite() {
        Ok(value)
    } else {
        Err("integer division result too large for a float".to_owned())
    }
}

#[cfg(test)]
mod true_divide_tests {
    use super::true_divide;
    use rustpython_ast::bigint::BigInt;
    use serde_json::Value;
    use sha2::{Digest, Sha256};

    const PYTHON_ORACLE: &str =
        include_str!("../../../../../tests/fixtures/python_integer_division/python_golden.json");
    const PYTHON_ORACLE_SHA256: &str =
        "71559659ff717ba81880ee65b1870bca7aa526f2b6c959125a268d90479e4b4b";

    #[test]
    fn integer_division_matches_frozen_cpython_binary64_bits_and_overflow() {
        assert_eq!(
            format!("{:x}", Sha256::digest(PYTHON_ORACLE.as_bytes())),
            PYTHON_ORACLE_SHA256
        );
        let oracle: Value = serde_json::from_str(PYTHON_ORACLE).expect("CPython oracle parses");
        assert_eq!(oracle["python_version"].as_str(), Some("3.12.3"));
        assert_eq!(
            oracle["operation"].as_str(),
            Some("CPython int true division for positive denominator")
        );
        let cases = oracle["cases"]
            .as_array()
            .expect("oracle cases are an array");
        assert_eq!(cases.len(), 19);

        for case in cases {
            let name = case["name"].as_str().expect("case name is text");
            let numerator = case["numerator"]
                .as_str()
                .expect("numerator is decimal text")
                .parse::<BigInt>()
                .expect("numerator parses as an arbitrary-precision integer");
            let denominator = case["denominator"]
                .as_str()
                .expect("denominator is decimal text")
                .parse::<BigInt>()
                .expect("denominator parses as an arbitrary-precision integer");
            let actual = true_divide(&numerator, &denominator);
            match (case["bits"].as_str(), case["error"].as_str()) {
                (Some(expected_bits), None) => {
                    let expected = u64::from_str_radix(expected_bits, 16)
                        .expect("oracle bit pattern is hexadecimal");
                    let actual = actual.unwrap_or_else(|error| panic!("{name}: {error}"));
                    assert_eq!(actual.to_bits(), expected, "{name}");
                }
                (None, Some("OverflowError")) => {
                    assert_eq!(
                        actual.unwrap_err(),
                        case["detail"].as_str().expect("overflow detail is text"),
                        "{name}"
                    );
                }
                _ => panic!("{name}: oracle case must contain bits or an error"),
            }
        }
    }
}

#[cfg(test)]
mod digit_tests {
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
