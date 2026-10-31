// @dependency-start
// contract implementation
// responsibility Provides Python difflib SequenceMatcher matching blocks and ratio for Unicode-scalar strings without custom junk.
// upstream implementation Python stdlib difflib.SequenceMatcher defines compatibility behavior.
// downstream test ../tests/python_sequence_matcher_native.rs freezes CPython matching blocks and binary64 ratios.
// @dependency-end

use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MatchBlock {
    pub a: usize,
    pub b: usize,
    pub size: usize,
}

/// Python SequenceMatcher over Unicode scalar sequences with its default popular-item filtering.
pub struct SequenceMatcher {
    a: Vec<char>,
    b: Vec<char>,
    b_to_indices: HashMap<char, Vec<usize>>,
}

impl SequenceMatcher {
    /// Create a matcher with Python's default `autojunk=True` behavior.
    pub fn new(a: &str, b: &str) -> Self {
        Self::with_autojunk(a, b, true)
    }

    /// Create a matcher with an explicit `autojunk` setting and no custom junk predicate.
    pub fn with_autojunk(a: &str, b: &str, autojunk: bool) -> Self {
        let a = a.chars().collect::<Vec<_>>();
        let b = b.chars().collect::<Vec<_>>();
        let mut b_to_indices: HashMap<char, Vec<usize>> = HashMap::new();
        for (index, character) in b.iter().copied().enumerate() {
            b_to_indices.entry(character).or_default().push(index);
        }
        if autojunk && b.len() >= 200 {
            let popular_threshold = b.len() / 100 + 1;
            let popular = b_to_indices
                .iter()
                .filter_map(|(character, indices)| {
                    (indices.len() > popular_threshold).then_some(*character)
                })
                .collect::<Vec<_>>();
            for character in popular {
                b_to_indices.remove(&character);
            }
        }
        Self { a, b, b_to_indices }
    }

    /// Return the sorted, coalesced matching blocks and Python's final zero-size sentinel.
    pub fn get_matching_blocks(&self) -> Vec<MatchBlock> {
        let mut pending = vec![(0, self.a.len(), 0, self.b.len())];
        let mut matches = Vec::new();
        while let Some((a_low, a_high, b_low, b_high)) = pending.pop() {
            let block = find_longest_match(
                &self.a,
                &self.b,
                &self.b_to_indices,
                a_low,
                a_high,
                b_low,
                b_high,
            );
            if block.size == 0 {
                continue;
            }
            matches.push(block);
            if a_low < block.a && b_low < block.b {
                pending.push((a_low, block.a, b_low, block.b));
            }
            if block.a + block.size < a_high && block.b + block.size < b_high {
                pending.push((block.a + block.size, a_high, block.b + block.size, b_high));
            }
        }
        matches.sort_by_key(|block| (block.a, block.b, block.size));

        let mut coalesced = Vec::with_capacity(matches.len() + 1);
        let mut previous: Option<MatchBlock> = None;
        for block in matches {
            match previous.take() {
                Some(mut prior)
                    if prior.a + prior.size == block.a && prior.b + prior.size == block.b =>
                {
                    prior.size += block.size;
                    previous = Some(prior);
                }
                Some(prior) => {
                    coalesced.push(prior);
                    previous = Some(block);
                }
                None => previous = Some(block),
            }
        }
        if let Some(prior) = previous {
            coalesced.push(prior);
        }
        coalesced.push(MatchBlock {
            a: self.a.len(),
            b: self.b.len(),
            size: 0,
        });
        coalesced
    }

    /// Return Python's `2.0 * matches / (len(a) + len(b))` binary64 ratio.
    pub fn ratio(&self) -> f64 {
        let matches = self
            .matching_blocks()
            .iter()
            .map(|block| block.size)
            .sum::<usize>();
        let total = self.a.len() + self.b.len();
        if total == 0 {
            1.0
        } else {
            2.0 * matches as f64 / total as f64
        }
    }
}

fn find_longest_match(
    a: &[char],
    b: &[char],
    b_to_indices: &HashMap<char, Vec<usize>>,
    a_low: usize,
    a_high: usize,
    b_low: usize,
    b_high: usize,
) -> MatchBlock {
    let mut best = MatchBlock {
        a: a_low,
        b: b_low,
        size: 0,
    };
    let mut previous_row = HashMap::<usize, usize>::new();
    for (a_index, character) in a.iter().enumerate().take(a_high).skip(a_low) {
        let mut current_row = HashMap::new();
        if let Some(indices) = b_to_indices.get(character) {
            for &b_index in indices {
                if b_index < b_low {
                    continue;
                }
                if b_index >= b_high {
                    break;
                }
                let previous_size = b_index
                    .checked_sub(1)
                    .and_then(|previous| previous_row.get(&previous).copied())
                    .unwrap_or(0);
                let size = previous_size + 1;
                current_row.insert(b_index, size);
                if size > best.size {
                    best = MatchBlock {
                        a: a_index + 1 - size,
                        b: b_index + 1 - size,
                        size,
                    };
                }
            }
        }
        previous_row = current_row;
    }

    while best.a > a_low && best.b > b_low && a[best.a - 1] == b[best.b - 1] {
        best.a -= 1;
        best.b -= 1;
        best.size += 1;
    }
    while best.a + best.size < a_high
        && best.b + best.size < b_high
        && a[best.a + best.size] == b[best.b + best.size]
    {
        best.size += 1;
    }
    best
}
