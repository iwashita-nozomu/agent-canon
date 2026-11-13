// @dependency-start
// contract implementation
// responsibility Reads and serializes the existing experiment registry for topic creation and context updates.
// upstream implementation ../experiment_registry.rs owns TOML parsing and registry values
// upstream implementation ../python_json.rs owns ASCII string encoding
// @dependency-end

use super::{parse_registry, RegistryValue};
use crate::python_json::{canonical_json_ascii_bytes, JsonString, JsonValue};
use std::fs;
use std::path::Path;

const DEFAULTS_ORDER: &[&str] = &[
    "managed_runner",
    "report_root",
    "integration_branch",
    "topic_template_dir",
    "required_eval_artifacts",
    "optional_eval_artifacts",
];
const TOPIC_ORDER: &[&str] = &[
    "name",
    "status",
    "topic_dir",
    "topic_readme",
    "canonical_entrypoint",
    "result_root",
    "report_root",
    "default_variant",
    "default_inner_command",
    "smoke_inner_command",
    "formal_inner_command",
    "required_eval_artifacts",
    "optional_eval_artifacts",
    "primary_note",
    "active_branch",
    "active_worktree",
    "scope_file",
    "branch_note",
];

pub(crate) fn load(path: &Path) -> Result<RegistryValue, String> {
    let text = fs::read_to_string(path).map_err(|error| error.to_string())?;
    parse_registry(&text)
}

pub(crate) fn json_value(value: &RegistryValue) -> Result<JsonValue, String> {
    use crate::python_json::{JsonArray, JsonNumber, JsonObject};
    Ok(match value {
        RegistryValue::String(value) => JsonValue::String(JsonString::from_text(value)),
        RegistryValue::Integer(value) => JsonValue::Number(JsonNumber::Integer(value.to_string())),
        RegistryValue::Float(value) => JsonValue::Number(JsonNumber::Float(*value)),
        RegistryValue::Boolean(value) => JsonValue::Bool(*value),
        RegistryValue::Array(values) => JsonValue::Array(JsonArray(
            values.iter().map(json_value).collect::<Result<_, _>>()?,
        )),
        RegistryValue::Table(values) => JsonValue::Object(JsonObject(
            values
                .iter()
                .map(|(key, value)| Ok((JsonString::from_text(key), json_value(value)?)))
                .collect::<Result<_, String>>()?,
        )),
        RegistryValue::Other(value) => {
            return Err(format!(
                "experiment registry contains an unsupported JSON value: {value}"
            ))
        }
    })
}

pub(crate) fn get<'a>(table: &'a RegistryValue, key: &str) -> Option<&'a RegistryValue> {
    let RegistryValue::Table(items) = table else {
        return None;
    };
    items
        .iter()
        .find(|(name, _)| name == key)
        .map(|(_, value)| value)
}

pub(crate) fn set(table: &mut RegistryValue, key: &str, value: RegistryValue) {
    let RegistryValue::Table(items) = table else {
        return;
    };
    if let Some((_, old)) = items.iter_mut().find(|(name, _)| name == key) {
        *old = value;
    } else {
        items.push((key.to_owned(), value));
    }
}

pub(crate) fn remove(table: &mut RegistryValue, key: &str) {
    if let RegistryValue::Table(items) = table {
        items.retain(|(name, _)| name != key);
    }
}

pub(crate) fn topics_mut(registry: &mut RegistryValue) -> Result<&mut Vec<RegistryValue>, String> {
    let RegistryValue::Table(items) = registry else {
        return Err("experiment registry TOML root must be a table".to_owned());
    };
    let Some((_, topics)) = items.iter_mut().find(|(name, _)| name == "topics") else {
        return Err("registry must contain [[topics]]".to_owned());
    };
    let RegistryValue::Array(topics) = topics else {
        return Err("experiment registry must contain [[topics]]".to_owned());
    };
    for (index, topic) in topics.iter().enumerate() {
        if !matches!(topic, RegistryValue::Table(_)) {
            return Err(format!("topics[{index}] must be a table"));
        }
    }
    Ok(topics)
}

pub(crate) fn find_topic_mut<'a>(
    registry: &'a mut RegistryValue,
    name: &str,
) -> Result<Option<&'a mut RegistryValue>, String> {
    if get(registry, "topics").is_none() {
        return Ok(None);
    }
    Ok(topics_mut(registry)?.iter_mut().find(
        |topic| matches!(get(topic, "name"), Some(RegistryValue::String(value)) if value == name),
    ))
}

fn scalar(value: &RegistryValue) -> Result<String, String> {
    match value {
        RegistryValue::String(text) => {
            let bytes =
                canonical_json_ascii_bytes(&JsonValue::String(JsonString::from_text(text)))?;
            String::from_utf8(bytes).map_err(|error| error.to_string())
        }
        RegistryValue::Boolean(value) => Ok(value.to_string()),
        RegistryValue::Integer(value) => Ok(value.to_string()),
        _ => Err("unsupported TOML scalar value".to_owned()),
    }
}

fn value_text(value: &RegistryValue) -> Result<String, String> {
    if let RegistryValue::Array(items) = value {
        return Ok(format!(
            "[{}]",
            items
                .iter()
                .map(scalar)
                .collect::<Result<Vec<_>, _>>()?
                .join(", ")
        ));
    }
    scalar(value)
}

fn append_table(
    output: &mut String,
    table: &RegistryValue,
    preferred: &[&str],
) -> Result<(), String> {
    let RegistryValue::Table(items) = table else {
        return Err("defaults must be a table".to_owned());
    };
    let mut remaining = items
        .iter()
        .filter(|(key, _)| !preferred.contains(&key.as_str()))
        .collect::<Vec<_>>();
    remaining.sort_by(|left, right| left.0.cmp(&right.0));
    let ordered = preferred
        .iter()
        .filter_map(|key| items.iter().find(|(name, _)| name == key))
        .chain(remaining);
    for (key, value) in ordered {
        output.push_str(&format!("{key} = {}\n", value_text(value)?));
    }
    Ok(())
}

pub(crate) fn render(registry: &RegistryValue) -> Result<String, String> {
    let version = match get(registry, "schema_version") {
        None => "1".to_owned(),
        Some(RegistryValue::Integer(value)) => value.to_string(),
        Some(RegistryValue::Boolean(value)) => if *value { "True" } else { "False" }.to_owned(),
        _ => return Err("schema_version must be an integer".to_owned()),
    };
    let empty_defaults = RegistryValue::Table(Vec::new());
    let defaults = get(registry, "defaults").unwrap_or(&empty_defaults);
    let mut output = format!("schema_version = {version}\n\n[defaults]\n");
    append_table(&mut output, defaults, DEFAULTS_ORDER)?;
    if let Some(topics) = get(registry, "topics") {
        let RegistryValue::Array(topics) = topics else {
            return Err("experiment registry must contain [[topics]]".to_owned());
        };
        for (index, topic) in topics.iter().enumerate() {
            if !matches!(topic, RegistryValue::Table(_)) {
                return Err(format!("topics[{index}] must be a table"));
            }
            output.push_str("\n[[topics]]\n");
            append_table(&mut output, topic, TOPIC_ORDER)?;
        }
    }
    Ok(output)
}

pub(crate) fn write(path: &Path, registry: &RegistryValue) -> Result<(), String> {
    fs::write(path, render(registry)?).map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_output_preserves_old_field_order_and_ascii_encoding() {
        let input = r#"
schema_version = 1
ignored_root = "omitted by the existing writer"
[defaults]
z = true
report_root = "reports"
managed_runner = "runner"
a = [1, false, "あ"]
[[topics]]
z = "last"
primary_note = "note"
name = "demo"
topic_provenance = "provenance.toml"
status = "draft"
a = 4
"#;
        let registry = parse_registry(input).unwrap();
        let expected = "schema_version = 1\n\n[defaults]\nmanaged_runner = \"runner\"\nreport_root = \"reports\"\na = [1, false, \"\\u3042\"]\nz = true\n\n[[topics]]\nname = \"demo\"\nstatus = \"draft\"\nprimary_note = \"note\"\na = 4\ntopic_provenance = \"provenance.toml\"\nz = \"last\"\n";
        assert_eq!(render(&registry).unwrap(), expected);
    }

    #[test]
    fn unsupported_values_leave_the_existing_registry_untouched() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("registry.toml");
        let original = b"preserve this existing file\n";
        fs::write(&path, original).unwrap();
        let registry = parse_registry("[defaults]\nunsupported = 1.5\n").unwrap();
        assert!(write(&path, &registry).is_err());
        assert_eq!(fs::read(&path).unwrap(), original);
    }

    #[test]
    fn boolean_schema_version_retains_the_existing_writer_behavior() {
        let registry = parse_registry("schema_version = true\n").unwrap();
        assert_eq!(
            render(&registry).unwrap(),
            "schema_version = True\n\n[defaults]\n"
        );
    }
}
