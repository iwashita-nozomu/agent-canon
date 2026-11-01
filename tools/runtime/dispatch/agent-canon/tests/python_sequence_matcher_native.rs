// @dependency-start
// contract test
// responsibility Verifies matching-block boundaries and binary64 ratios against frozen CPython difflib.SequenceMatcher results.
// upstream implementation ../src/python_sequence_matcher.rs owns Unicode-scalar matching semantics.
// upstream test ../../../../../tests/fixtures/python_sequence_matcher/python_golden.json freezes the independent oracle.
// @dependency-end

use agent_canon::python_sequence_matcher::{MatchBlock, SequenceMatcher};
use serde_json::Value;

const GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/python_sequence_matcher/python_golden.json");

fn field<'a>(value: &'a Value, key: &str) -> &'a Value {
    value
        .get(key)
        .expect("frozen SequenceMatcher field is present")
}

fn text(value: &Value) -> &str {
    value
        .as_str()
        .expect("frozen SequenceMatcher value is text")
}

fn usize_value(value: &Value) -> usize {
    usize::try_from(
        value
            .as_u64()
            .expect("frozen matching-block index is a nonnegative integer"),
    )
    .expect("frozen matching-block index fits the host")
}

#[test]
fn sequence_matcher_blocks_and_binary64_ratios_match_all_frozen_cpython_cases() {
    let golden: Value =
        serde_json::from_str(GOLDEN).expect("frozen CPython SequenceMatcher oracle parses");
    let cases = field(&golden, "cases")
        .as_array()
        .expect("frozen SequenceMatcher cases are an array");
    assert_eq!(cases.len(), 32);

    for case in cases {
        let name = text(field(case, "name"));
        let a = text(field(case, "a"));
        let b = text(field(case, "b"));
        let autojunk = field(case, "autojunk")
            .as_bool()
            .expect("frozen autojunk setting is boolean");
        let matcher = if autojunk {
            SequenceMatcher::new(a, b)
        } else {
            SequenceMatcher::with_autojunk(a, b, false)
        };
        let expected_blocks = field(case, "matching_blocks")
            .as_array()
            .expect("frozen matching blocks are an array")
            .iter()
            .map(|block| {
                let values = block
                    .as_array()
                    .expect("frozen matching block is a three-item array");
                assert_eq!(values.len(), 3, "block shape for {name}");
                MatchBlock {
                    a: usize_value(&values[0]),
                    b: usize_value(&values[1]),
                    size: usize_value(&values[2]),
                }
            })
            .collect::<Vec<_>>();
        assert_eq!(
            matcher.get_matching_blocks(),
            expected_blocks,
            "blocks for {name}"
        );

        let expected_ratio_bits = u64::from_str_radix(text(field(case, "ratio_bits_hex")), 16)
            .expect("frozen ratio bits are hexadecimal");
        assert_eq!(
            matcher.ratio().to_bits(),
            expected_ratio_bits,
            "binary64 ratio for {name}"
        );
    }
}
