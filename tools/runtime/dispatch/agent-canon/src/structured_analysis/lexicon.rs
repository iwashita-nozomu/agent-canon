//! Shared prose words and domain hints. ICU owns word boundaries and dictionary data.

use icu_casemap::CaseMapper;
use icu_normalizer::ComposingNormalizer;
use icu_segmenter::WordSegmenter;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::io::{self, Read};

const STOPWORDS: &[&str] = &[
    "the", "and", "for", "that", "this", "with", "from", "into", "are", "is", "can", "not", "but",
    "you", "our", "their", "have", "has", "must", "should", "する", "です", "ます", "こと", "これ",
    "それ", "ため",
];
const SOFTWARE_CUES: &[&str] = &[
    "code",
    "software",
    "engineering",
    "implementation",
    "developer",
    "repository",
    "dependency",
    "command",
    "python",
    "rust",
    "cli",
    "ソフトウェア",
    "プログラミング",
    "リポジトリ",
    "依存関係",
    "コマンド",
    "開発者",
    "実装",
];
const ACADEMIC_CUES: &[&str] = &["academic", "paper", "research", "論文", "学術", "研究"];
const TOP_TERM_LIMIT: usize = 12;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    texts: Vec<String>,
    #[serde(default)]
    prompt: String,
}

#[derive(Serialize)]
struct Analysis {
    schema: &'static str,
    segmentation: &'static str,
    terms: Vec<Vec<String>>,
    top_terms: Vec<String>,
    corpus_hints: Vec<Value>,
}

struct Lexicon {
    segmenter: WordSegmenter,
    case_mapper: CaseMapper,
    normalizer: ComposingNormalizer,
}

impl Lexicon {
    fn new() -> Self {
        Self {
            segmenter: WordSegmenter::new_dictionary(),
            case_mapper: CaseMapper::new(),
            normalizer: ComposingNormalizer::new_nfc(),
        }
    }

    fn normalize(&self, text: &str) -> String {
        self.case_mapper
            .fold_string(&self.normalizer.normalize(text))
    }

    fn terms(&self, text: &str) -> Vec<String> {
        let normalized = self.normalize(text);
        let mut start = 0;
        let mut terms = Vec::new();
        for end in self.segmenter.segment_str(&normalized) {
            let word = &normalized[start..end];
            let minimum = if word.is_ascii() { 3 } else { 2 };
            // ICU4X 1.3 can report no word type for a terminal dictionary segment.
            // Character properties retain such Han words while excluding symbols.
            if word.chars().any(char::is_alphabetic)
                && word.chars().count() >= minimum
                && !STOPWORDS.contains(&word)
            {
                terms.push(word.to_owned());
            }
            start = end;
        }
        terms
    }

    fn analyze(&self, request: &Request) -> Analysis {
        let terms: Vec<_> = request.texts.iter().map(|text| self.terms(text)).collect();
        let mut counts: BTreeMap<&str, (usize, usize)> = BTreeMap::new();
        for (position, term) in terms.iter().flatten().enumerate() {
            let entry = counts.entry(term.as_str()).or_insert((0, position));
            entry.0 += 1;
        }
        let mut ranked: Vec<_> = counts.into_iter().collect();
        ranked.sort_by_key(|(_, (count, first))| (std::cmp::Reverse(*count), *first));
        let top_terms = ranked
            .into_iter()
            .take(TOP_TERM_LIMIT)
            .map(|(term, _)| term.to_owned())
            .collect();
        let mut texts: Vec<_> = request.texts.iter().map(String::as_str).collect();
        texts.push(&request.prompt);
        let combined = self.normalize(&texts.join("\n"));
        let mut corpus_hints = Vec::new();
        for (id, label, cues) in [
            (
                "software_engineering",
                "Software engineering prose and implementation artifacts",
                SOFTWARE_CUES,
            ),
            (
                "academic_writing",
                "Academic writing and research communication",
                ACADEMIC_CUES,
            ),
        ] {
            let signals: Vec<_> = cues
                .iter()
                .filter(|cue| cue_present(&combined, cue))
                .collect();
            if !signals.is_empty() {
                corpus_hints.push(json!({
                    "corpus_id": id,
                    "label": label,
                    "score": 1,
                    "selected": true,
                    "basis": {"source": "lexical_keyword_matching", "signals": signals}
                }));
            }
        }
        Analysis {
            schema: "agent-canon.prose-lexicon.v1",
            segmentation: "icu4x-1.3.2-word-dictionary-nfc-casefold",
            terms,
            top_terms,
            corpus_hints,
        }
    }
}

pub(super) fn analyze_texts(texts: &[String], prompt: &str) -> Value {
    let request = Request {
        texts: texts.to_vec(),
        prompt: prompt.to_owned(),
    };
    serde_json::to_value(Lexicon::new().analyze(&request))
        .expect("prose lexicon response serializes")
}

fn cue_present(text: &str, cue: &str) -> bool {
    if !cue.is_ascii() {
        return text.contains(cue);
    }
    let is_identifier =
        |character: char| character.is_ascii_alphanumeric() || "_-".contains(character);
    text.match_indices(cue).any(|(start, matched)| {
        !text[..start].chars().next_back().is_some_and(is_identifier)
            && !text[start + matched.len()..]
                .chars()
                .next()
                .is_some_and(is_identifier)
    })
}

pub(super) fn run(args: &[String]) -> i32 {
    if !args.is_empty() {
        eprintln!("usage: agent-canon structured-analysis lexicon < request.json");
        return 2;
    }
    let result = (|| -> Result<Analysis, String> {
        let mut input = String::new();
        io::stdin()
            .read_to_string(&mut input)
            .map_err(|error| error.to_string())?;
        let request: Request = serde_json::from_str(&input).map_err(|error| error.to_string())?;
        Ok(Lexicon::new().analyze(&request))
    })();
    match result {
        Ok(analysis) => {
            println!(
                "{}",
                serde_json::to_string(&analysis).expect("serializable prose words")
            );
            0
        }
        Err(error) => {
            eprintln!("PROSE_LEXICON_ERROR={error}");
            2
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn japanese_uses_dictionary_boundaries_and_ignores_punctuation() {
        let lexicon = Lexicon::new();
        assert_eq!(
            lexicon.terms("こんにちは世界。——— 。。。 😀😀😀"),
            ["こんにちは", "世界"]
        );
        assert!(lexicon.terms("——— 。。。 😀😀😀 1234").is_empty());
    }

    #[test]
    fn words_are_normalized_without_ascii_truncation() {
        let lexicon = Lexicon::new();
        assert_eq!(
            lexicon.terms("Résumé RE\u{301}SUME\u{301} STRASSE Straße"),
            ["résumé", "résumé", "strasse", "strasse"]
        );
        assert_eq!(
            lexicon.terms("the and source_graph Rust"),
            ["source_graph", "rust"]
        );
    }

    #[test]
    fn frequency_ties_follow_first_source_appearance() {
        let result = Lexicon::new().analyze(&Request {
            texts: vec!["zebra apple 世界 世界 apple".into()],
            prompt: String::new(),
        });
        assert_eq!(result.top_terms, ["apple", "世界", "zebra"]);
    }

    #[test]
    fn japanese_domain_cues_and_prompt_share_the_existing_hint_contract() {
        let result = Lexicon::new().analyze(&Request {
            texts: vec!["ソフトウェアの依存関係を調べ、設計文書を作成する。".into()],
            prompt: "研究論文".into(),
        });
        assert_eq!(result.corpus_hints[0]["corpus_id"], "software_engineering");
        assert_eq!(result.corpus_hints[1]["corpus_id"], "academic_writing");
        assert!(!result.top_terms.iter().any(|term| term.contains('。')));
        assert!(!result.top_terms.iter().any(|term| term == "研究"));
    }

    #[test]
    fn ascii_cues_do_not_match_inside_identifiers() {
        assert!(!cue_present("trust cliff rusty_python", "rust"));
        assert!(!cue_present("trust cliff rusty_python", "cli"));
        assert!(cue_present("rustの実装", "rust"));
    }

    #[test]
    fn malformed_input_is_rejected_at_the_request_boundary() {
        assert!(serde_json::from_str::<Request>(r#"{"texts":[3]}"#).is_err());
        assert!(serde_json::from_str::<Request>(r#"{"texts":[],"unknown":true}"#).is_err());
    }
}
