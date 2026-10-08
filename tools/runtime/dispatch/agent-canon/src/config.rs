// @dependency-start
// contract implementation
// responsibility Applies the canonical context defaults to a personal Codex TOML document.
// upstream implementation ../../../../../.codex/config.toml owns the context default values
// downstream implementation ../../../../../bootstrap/host/lifecycle/entrypoint.sh owns the stdin, temporary-file, and replacement transaction
// @dependency-end

use std::fs;
use std::io::{self, Read, Write};
use std::path::Path;

use toml_edit::{value as toml_value, DocumentMut, Item};

const CONTEXT_WINDOW_KEY: &str = "model_context_window";
const AUTO_COMPACT_KEY: &str = "model_auto_compact_token_limit";

fn root_integer(document: &DocumentMut, key: &str) -> Option<i64> {
    document.get(key).and_then(Item::as_integer)
}

fn set_root_integer(document: &mut DocumentMut, key: &str, number: i64) {
    if let Some(item) = document.get_mut(key) {
        let decor = item.as_value().map(|current| current.decor().clone());
        *item = toml_value(number).into();
        if let (Some(decor), Some(updated)) = (decor, item.as_value_mut()) {
            *updated.decor_mut() = decor;
        }
    } else {
        document.insert(key, toml_value(number));
    }
}

fn apply_context_defaults(personal: &str, canonical: &str) -> Result<String, &'static str> {
    let defaults = canonical
        .parse::<DocumentMut>()
        .map_err(|_| "canonical Codex config is invalid")?;
    let context_window = root_integer(&defaults, CONTEXT_WINDOW_KEY)
        .ok_or("canonical Codex context defaults are missing or invalid")?;
    let auto_compact = root_integer(&defaults, AUTO_COMPACT_KEY)
        .ok_or("canonical Codex context defaults are missing or invalid")?;
    let mut personal = personal
        .parse::<DocumentMut>()
        .map_err(|_| "personal Codex config is invalid")?;
    set_root_integer(&mut personal, CONTEXT_WINDOW_KEY, context_window);
    set_root_integer(&mut personal, AUTO_COMPACT_KEY, auto_compact);
    Ok(personal.to_string())
}

pub fn run(args: &[String]) -> i32 {
    let Some(source_config) = parse_args(args) else {
        eprintln!("usage: agent-canon codex-config --source-config <path>");
        return 2;
    };
    let canonical = match fs::read_to_string(source_config) {
        Ok(content) => content,
        Err(_) => {
            eprintln!("codex-config: canonical config could not be read");
            return 2;
        }
    };
    let mut personal = String::new();
    if io::stdin().read_to_string(&mut personal).is_err() {
        eprintln!("codex-config: personal config could not be read");
        return 2;
    }
    let updated = match apply_context_defaults(&personal, &canonical) {
        Ok(updated) => updated,
        Err(error) => {
            eprintln!("codex-config: {error}");
            return 2;
        }
    };
    if io::stdout().write_all(updated.as_bytes()).is_err() {
        eprintln!("codex-config: updated config could not be written");
        return 2;
    }
    0
}

fn parse_args(args: &[String]) -> Option<&Path> {
    match args {
        [flag, path] if flag == "--source-config" => Some(Path::new(path)),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const CANONICAL: &str =
        "model_context_window = 1050000\nmodel_auto_compact_token_limit = 900000\n";

    #[test]
    fn updates_only_root_context_values_and_preserves_multiline_provider_data() {
        let personal = r#"
"model_context_window" = 1000000 # user value
model_auto_compact_token_limit = 700000
provider_notes = """
[this.is.not.a.table]
model_context_window = 17
"""

[profiles."other"]
model_auto_compact_token_limit = 123
provider = "private-provider"
"#;
        let updated = apply_context_defaults(personal, CANONICAL).expect("valid TOML");
        let original = personal.parse::<DocumentMut>().expect("valid TOML");
        let result = updated.parse::<DocumentMut>().expect("valid TOML output");

        assert_eq!(root_integer(&result, CONTEXT_WINDOW_KEY), Some(1_050_000));
        assert_eq!(root_integer(&result, AUTO_COMPACT_KEY), Some(900_000));
        assert_eq!(
            result["provider_notes"].as_str(),
            original["provider_notes"].as_str()
        );
        assert_eq!(
            result["profiles"]["other"][AUTO_COMPACT_KEY].as_integer(),
            Some(123)
        );
        assert_eq!(
            result["profiles"]["other"]["provider"].as_str(),
            Some("private-provider")
        );
    }

    #[test]
    fn applying_context_defaults_is_idempotent() {
        let personal = "approval_policy = 'on-request'\n";
        let once = apply_context_defaults(personal, CANONICAL).expect("valid TOML");
        let twice = apply_context_defaults(&once, CANONICAL).expect("valid TOML");
        assert_eq!(once, twice);
    }

    #[test]
    fn replaces_wrong_typed_root_settings_and_keeps_their_comments() {
        let personal = "model_context_window = 'old' # context comment\nmodel_auto_compact_token_limit = false # compact comment\n";
        let updated = apply_context_defaults(personal, CANONICAL).expect("valid TOML");
        let result = updated.parse::<DocumentMut>().expect("valid TOML output");

        assert_eq!(root_integer(&result, CONTEXT_WINDOW_KEY), Some(1_050_000));
        assert_eq!(root_integer(&result, AUTO_COMPACT_KEY), Some(900_000));
        assert!(updated.contains("# context comment"));
        assert!(updated.contains("# compact comment"));
    }

    #[test]
    fn malformed_inputs_fail_without_returning_config_contents() {
        let personal = "private = 'do not echo'\n[broken\n";
        let error = apply_context_defaults(personal, CANONICAL).unwrap_err();
        assert_eq!(error, "personal Codex config is invalid");
        assert!(!error.contains("do not echo"));

        let missing_default =
            apply_context_defaults(personal, "model_context_window = 1\n").unwrap_err();
        assert_eq!(
            missing_default,
            "canonical Codex context defaults are missing or invalid"
        );
    }
}
