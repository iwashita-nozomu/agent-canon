// @dependency-start
// contract test
// responsibility Qualifies the XML provider and Markdown projection against the frozen DOCX XML corpus.
// upstream implementation ../Cargo.toml selects the safe XML provider candidate
// upstream evidence ../../../../../tests/fixtures/docx_xml/python_golden.json freezes old ElementTree events and product Markdown
// @dependency-end

use agent_canon::extract_docx::extract_markdown;
use base64::engine::general_purpose::STANDARD;
use base64::Engine as _;
use expat::internal::parse::{Handler, HandlerSet, Parser, Status};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

const GOLDEN: &str = include_str!("../../../../../tests/fixtures/docx_xml/python_golden.json");

fn expanded_name(name: &[u8]) -> String {
    let name = std::str::from_utf8(name).expect("the parser emits UTF-8 names");
    match name.split_once('\u{1f}') {
        Some((namespace, local)) => format!("{{{namespace}}}{local}"),
        None => name.to_owned(),
    }
}

#[derive(Default)]
struct ElementEvents {
    values: Vec<Value>,
    depth: usize,
}

impl Handler for ElementEvents {
    fn start_element(&mut self, name: &[u8], attributes: &[(&[u8], &[u8])], _: i32) {
        let attributes = attributes
            .iter()
            .map(|(name, value)| {
                (
                    expanded_name(name),
                    Value::String(std::str::from_utf8(value).expect("UTF-8 value").to_owned()),
                )
            })
            .collect::<Map<_, _>>();
        self.depth += 1;
        self.values
            .push(json!({"kind":"start", "name":expanded_name(name), "attributes":attributes}));
    }

    fn end_element(&mut self, name: &[u8]) {
        self.depth -= 1;
        self.values
            .push(json!({"kind":"end", "name":expanded_name(name)}));
    }

    fn character_data(&mut self, text: &[u8]) {
        if self.depth == 0 || text.is_empty() {
            return;
        }
        let text = std::str::from_utf8(text).expect("UTF-8 character data");
        if let Some(Value::Object(previous)) = self.values.last_mut() {
            if previous.get("kind").and_then(Value::as_str) == Some("text") {
                if let Some(Value::String(value)) = previous.get_mut("text") {
                    value.push_str(text);
                    return;
                }
            }
        }
        self.values.push(json!({"kind":"text", "text":text}));
    }
}

fn provider_events(bytes: &[u8]) -> Result<Vec<Value>, String> {
    let mut salt = [0; 16];
    getrandom::getrandom(&mut salt).map_err(|error| error.to_string())?;
    let mut parser = Parser::new(None, Some(b'\x1f'), salt);
    parser.set_handlers(HandlerSet {
        start_element: true,
        end_element: true,
        character_data: true,
        // ElementTree rejects external references through its handler. The
        // provider's default handler refuses them without loading any resource.
        external_entity_ref: true,
        ..HandlerSet::default()
    });
    let mut events = ElementEvents::default();
    match parser.parse(&mut events, bytes, true) {
        Status::Ok => Ok(events.values),
        _ => Err(format!("{:?}", parser.error_code())),
    }
}

fn heading_document(style: &str) -> String {
    format!(
        r#"<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr><w:r><w:t>Section</w:t></w:r></w:p></w:body></w:document>"#
    )
}

#[test]
fn xml_provider_preserves_old_docx_input_acceptance_and_element_values() {
    assert_eq!(
        format!("{:x}", Sha256::digest(GOLDEN.as_bytes())),
        "0d6127b88c59d6cea5e6811e926518d4f724558e589212797116687c70fb2e3a"
    );
    let corpus: Value = serde_json::from_str(GOLDEN).unwrap();
    let cases = corpus["cases"].as_array().unwrap();
    assert_eq!(cases.len(), 20);
    let mut mismatches = Vec::new();
    for case in cases {
        let name = case["name"].as_str().unwrap();
        let input = STANDARD
            .decode(case["input_base64"].as_str().unwrap())
            .unwrap();
        let result = provider_events(&input);
        let expected_acceptance = case["xml_accepted"].as_bool().unwrap();
        match result {
            Ok(events) if expected_acceptance => {
                if Value::Array(events) != case["events"] {
                    mismatches.push(format!("{name}: element values differ"));
                }
                if let Some(expected_markdown) = case["markdown"].as_str() {
                    match extract_markdown(&input, "reference.docx") {
                        Ok(markdown) if markdown == expected_markdown => {}
                        Ok(_) => mismatches.push(format!("{name}: product Markdown differs")),
                        Err(error) => {
                            mismatches.push(format!("{name}: product projection failed: {error}"))
                        }
                    }
                } else if name == "valid-no-body" {
                    match extract_markdown(&input, "reference.docx") {
                        Err(error) if error.contains("has no document body") => {}
                        _ => mismatches.push(format!("{name}: missing-body product error differs")),
                    }
                }
            }
            Ok(_) => mismatches.push(format!("{name}: accepted an old rejected input")),
            Err(error) if expected_acceptance => {
                mismatches.push(format!("{name}: rejected an old accepted input: {error}"))
            }
            Err(_) => {}
        }
    }
    assert!(mismatches.is_empty(), "{}", mismatches.join("\n"));
}

#[test]
fn product_heading_suffix_matches_python_unicode_digit_then_int_behavior() {
    for suffix in ["٢", "２"] {
        let xml = heading_document(&format!("Heading{suffix}"));
        let markdown = extract_markdown(xml.as_bytes(), "reference.docx").unwrap();
        assert!(
            markdown.contains("## Section"),
            "suffix={suffix:?}: {markdown}"
        );
    }

    let superscript = heading_document("Heading²");
    assert_eq!(
        extract_markdown(superscript.as_bytes(), "reference.docx").unwrap_err(),
        "invalid literal for int() with base 10: '²'"
    );

    let fraction = heading_document("Heading½");
    let markdown = extract_markdown(fraction.as_bytes(), "reference.docx").unwrap();
    assert!(markdown.contains("# Section"), "{markdown}");

    let multiple_properties = format!(
        r#"<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:rPr/></w:pPr><w:pPr><w:pStyle w:val="Heading２"/></w:pPr><w:r><w:t>Section</w:t></w:r></w:p></w:body></w:document>"#
    );
    let markdown = extract_markdown(multiple_properties.as_bytes(), "reference.docx").unwrap();
    assert!(markdown.contains("## Section"), "{markdown}");
}

#[test]
fn product_projection_walks_and_drops_deep_xml_iteratively() {
    let depth = 10_000;
    let mut xml = String::from(
        "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">",
    );
    for _ in 0..depth {
        xml.push_str("<x>");
    }
    xml.push_str("<w:body><w:p>");
    for _ in 0..depth {
        xml.push_str("<x>");
    }
    xml.push_str("<w:t>Deep</w:t>");
    for _ in 0..depth {
        xml.push_str("</x>");
    }
    xml.push_str("</w:p></w:body>");
    for _ in 0..depth {
        xml.push_str("</x>");
    }
    xml.push_str("</w:document>");

    let markdown = extract_markdown(xml.as_bytes(), "reference.docx").unwrap();
    assert!(markdown.contains("\nDeep\n"), "{markdown}");
}
