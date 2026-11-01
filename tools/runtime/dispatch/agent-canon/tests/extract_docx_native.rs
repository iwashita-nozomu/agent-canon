// @dependency-start
// contract test
// responsibility Qualifies the XML provider against the existing DOCX extractor's parsed inputs.
// upstream implementation ../Cargo.toml selects the safe XML provider candidate
// upstream evidence ../../../../../tests/fixtures/docx_xml/python_golden.json freezes old ElementTree events and product Markdown
// @dependency-end

use base64::engine::general_purpose::STANDARD;
use base64::Engine as _;
use expat_rs::{Event, Parser};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

const GOLDEN: &str = include_str!("../../../../../tests/fixtures/docx_xml/python_golden.json");

fn expanded_name(name: &str, namespace: Option<&str>) -> String {
    match namespace {
        Some(namespace) => format!("{{{namespace}}}{}", expat_rs::local_name(name)),
        None => name.to_owned(),
    }
}

fn provider_events(bytes: &[u8]) -> Result<Vec<Value>, String> {
    let decoded = expat_rs::decode(bytes).map_err(|error| error.to_string())?;
    let mut parser = Parser::new(&decoded).with_namespaces();
    let mut events: Vec<Value> = Vec::new();
    let mut names = Vec::new();
    while let Some(event) = parser.next_event().map_err(|error| error.to_string())? {
        match event {
            Event::StartElement {
                name,
                namespace,
                attributes,
            } => {
                let qualified = name.to_string();
                let expanded = expanded_name(&name, namespace.as_deref());
                let attributes = attributes
                    .into_iter()
                    .map(|attribute| {
                        (
                            expanded_name(&attribute.name, attribute.namespace.as_deref()),
                            Value::String(attribute.value.into_owned()),
                        )
                    })
                    .collect::<Map<_, _>>();
                names.push((qualified, expanded.clone()));
                events.push(json!({"kind":"start", "name":expanded, "attributes":attributes}));
            }
            Event::EndElement(name) => {
                let (qualified, expanded) = names.pop().ok_or("unmatched end event")?;
                if name != qualified {
                    return Err("end event differs from its start event".to_owned());
                }
                events.push(json!({"kind":"end", "name":expanded}));
            }
            Event::Text(text) | Event::CData(text) if !names.is_empty() && !text.is_empty() => {
                if let Some(Value::Object(previous)) = events.last_mut() {
                    if previous.get("kind").and_then(Value::as_str) == Some("text") {
                        if let Some(Value::String(value)) = previous.get_mut("text") {
                            value.push_str(&text);
                            continue;
                        }
                    }
                }
                events.push(json!({"kind":"text", "text":text.as_ref()}));
            }
            _ => {}
        }
    }
    Ok(events)
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
