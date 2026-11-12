// @dependency-start
// contract implementation
// responsibility Preserves the Skill frontmatter compatibility command as a native readback adapter.
// upstream implementation catalog/skill_materialization.rs renders and checks v3 Skill projections
// upstream implementation catalog/skill_routes.rs owns catalog schema validation
// downstream implementation main.rs registers the native command selector
// downstream test ../tests/skill_frontmatter_native.rs checks materialization readback
// @dependency-end

use crate::catalog::skill_materialization;
use crate::catalog::skill_routes::validate_catalog_schemas;
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use serde::Serialize;
use serde_json::json;
use std::fs;
use std::path::{Path, PathBuf};

const SELECTOR: &str = "check-skill-frontmatter";
const USAGE: &str =
    "usage: agent-canon check-skill-frontmatter [-h] [--root ROOT] [--format {text,json}]";

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct Finding {
    check: String,
    path: String,
    detail: String,
}

impl Finding {
    fn render(&self) -> String {
        format!(
            "SKILL_FRONTMATTER_FINDING={}:{}:{}",
            self.check, self.path, self.detail
        )
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Format {
    Text,
    Json,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct Options {
    root: PathBuf,
    format: Format,
}

#[derive(Clone, Debug, PartialEq, Eq)]
enum ParseResult {
    Help,
    Options(Options),
}

/// Run the compatibility checker over the full generated Skill projection set.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_args(args) {
        Ok(ParseResult::Help) => {
            println!("{USAGE}\n\nCheck generated Skill frontmatter and materialization readback.\n\nOptions:\n  -h, --help           Print help\n  --root ROOT          Repository root (default: .)\n  --format {{text,json}}  Output format");
            return 0;
        }
        Ok(ParseResult::Options(options)) => options,
        Err(error) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };

    let root = resolve_root(&options.root);
    let checked = skill_paths_count(&root);
    let catalog = root.join("agents/skills/catalog.yaml");
    let dependencies = root.join("agents/skills/skill-dependencies.yaml");
    let findings = if !catalog.is_file() || !dependencies.is_file() {
        Vec::new()
    } else {
        match validate_catalog_schemas(&root)
            .map_err(|error| error.to_string())
            .and_then(|_| {
                skill_materialization::check(&root)
                    .map_err(|error| error.to_string())
                    .map(|check| {
                        check
                            .content_delta_paths
                            .into_iter()
                            .map(|path| Finding {
                                check: "projection".to_owned(),
                                path,
                                detail: "fixed-point-drift".to_owned(),
                            })
                            .collect()
                    })
            }) {
            Ok(findings) => findings,
            Err(detail) => vec![Finding {
                check: "projection".to_owned(),
                path: ".codex/personal/skills".to_owned(),
                detail,
            }],
        }
    };

    match options.format {
        Format::Text => print_text(&findings, checked),
        Format::Json => print_json(&findings, checked),
    }
    if findings.is_empty() {
        0
    } else {
        1
    }
}

fn parse_args(args: &[String]) -> Result<ParseResult, String> {
    let mut root = PathBuf::from(".");
    let mut output_format = Format::Text;
    let mut index = 0;
    while index < args.len() {
        let argument = args[index].as_str();
        if argument == "-h" {
            return Ok(ParseResult::Help);
        }
        let (option, inline_value) = argument
            .split_once('=')
            .map_or((argument, None), |(option, value)| (option, Some(value)));
        let selected = resolve_long_option_prefix(
            option,
            &[
                ("--help", "help"),
                ("--root", "root"),
                ("--format", "format"),
            ],
        )
        .map_err(|error| match error {
            LongOptionError::Unrecognized => format!("unrecognized arguments: {argument}"),
            LongOptionError::Ambiguous(options) => format!(
                "ambiguous option: {option} could match {}",
                options.join(", ")
            ),
        })?;
        if selected == "help" {
            if inline_value.is_some() {
                return Err("argument --help: ignored explicit argument".to_owned());
            }
            return Ok(ParseResult::Help);
        }
        let value = if let Some(value) = inline_value {
            value.to_owned()
        } else {
            index += 1;
            args.get(index)
                .cloned()
                .ok_or_else(|| format!("argument {option}: expected one argument"))?
        };
        match selected {
            "root" => root = PathBuf::from(value),
            "format" => {
                output_format = match value.as_str() {
                    "text" => Format::Text,
                    "json" => Format::Json,
                    _ => {
                        return Err(format!(
                            "argument --format: invalid choice: {value:?} (choose from 'text', 'json')"
                        ));
                    }
                };
            }
            _ => unreachable!("registered option names are exhaustive"),
        }
        index += 1;
    }
    Ok(ParseResult::Options(Options {
        root,
        format: output_format,
    }))
}

fn resolve_root(root: &Path) -> PathBuf {
    if let Ok(path) = root.canonicalize() {
        return path;
    }
    if root.is_absolute() {
        root.to_path_buf()
    } else {
        std::env::current_dir()
            .map(|cwd| cwd.join(root))
            .unwrap_or_else(|_| root.to_path_buf())
    }
}

fn skill_paths_count(root: &Path) -> usize {
    let skill_root = root.join(".codex/personal/skills");
    let Ok(entries) = fs::read_dir(skill_root) else {
        return 0;
    };
    entries
        .filter_map(Result::ok)
        .filter(|entry| entry.path().join("SKILL.md").is_file())
        .count()
}

fn print_text(findings: &[Finding], checked: usize) {
    print!("{}", render_text(findings, checked));
}

fn render_text(findings: &[Finding], checked: usize) -> String {
    let mut lines = findings.iter().map(Finding::render).collect::<Vec<_>>();
    lines.push(format!("SKILL_FRONTMATTER_CHECKED={checked}"));
    lines.push(format!(
        "SKILL_FRONTMATTER={}",
        if findings.is_empty() { "pass" } else { "fail" }
    ));
    format!("{}\n", lines.join("\n"))
}

fn render_json(findings: &[Finding], checked: usize) -> String {
    let payload = json!({
        "status": if findings.is_empty() { "pass" } else { "fail" },
        "checked": checked,
        "findings": findings,
    });
    let rendered = serde_json::to_string_pretty(&payload).unwrap_or_else(|_| "{}".to_owned());
    ensure_ascii(&rendered)
}

fn print_json(findings: &[Finding], checked: usize) {
    println!("{}", render_json(findings, checked));
}

fn ensure_ascii(value: &str) -> String {
    let mut escaped = String::with_capacity(value.len());
    for character in value.chars() {
        let codepoint = u32::from(character);
        if codepoint <= 0x7f {
            escaped.push(character);
        } else if codepoint <= 0xffff {
            use std::fmt::Write as _;
            let _ = write!(escaped, "\\u{codepoint:04x}");
        } else {
            let adjusted = codepoint - 0x1_0000;
            let high = 0xd800 + (adjusted >> 10);
            let low = 0xdc00 + (adjusted & 0x3ff);
            use std::fmt::Write as _;
            let _ = write!(escaped, "\\u{high:04x}\\u{low:04x}");
        }
    }
    escaped
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parser_keeps_argparse_long_option_prefixes_and_last_value() {
        let parsed = parse_args(&[
            "--ro".to_owned(),
            "first".to_owned(),
            "--root=second".to_owned(),
            "--for".to_owned(),
            "json".to_owned(),
        ])
        .unwrap();
        assert_eq!(
            parsed,
            ParseResult::Options(Options {
                root: PathBuf::from("second"),
                format: Format::Json,
            })
        );
    }

    #[test]
    fn parser_rejects_ambiguous_and_invalid_options() {
        assert!(parse_args(&["--".to_owned()]).is_err());
        assert!(parse_args(&["--format".to_owned(), "yaml".to_owned()]).is_err());
    }

    #[test]
    fn json_output_uses_python_ascii_escaping() {
        assert_eq!(ensure_ascii("\"é😀\""), "\"\\u00e9\\ud83d\\ude00\"");
    }

    #[test]
    fn text_output_preserves_marker_order_and_final_newline() {
        let findings = [Finding {
            check: "projection".to_owned(),
            path: ".codex/personal/skills/example/SKILL.md".to_owned(),
            detail: "fixed-point-drift".to_owned(),
        }];
        assert_eq!(
            render_text(&findings, 2),
            "SKILL_FRONTMATTER_FINDING=projection:.codex/personal/skills/example/SKILL.md:fixed-point-drift\nSKILL_FRONTMATTER_CHECKED=2\nSKILL_FRONTMATTER=fail\n"
        );
    }

    #[test]
    fn json_output_preserves_sorted_python_report_shape() {
        let findings = [Finding {
            check: "projection".to_owned(),
            path: ".codex/personal/skills/example/SKILL.md".to_owned(),
            detail: "fixed-point-drift".to_owned(),
        }];
        assert_eq!(
            render_json(&findings, 1),
            "{\n  \"checked\": 1,\n  \"findings\": [\n    {\n      \"check\": \"projection\",\n      \"detail\": \"fixed-point-drift\",\n      \"path\": \".codex/personal/skills/example/SKILL.md\"\n    }\n  ],\n  \"status\": \"fail\"\n}"
        );
    }

    #[test]
    fn checked_count_matches_the_one_level_runtime_skill_glob() {
        let temp = tempfile::tempdir().expect("create root");
        let skill = temp.path().join(".codex/personal/skills/visible/SKILL.md");
        std::fs::create_dir_all(skill.parent().unwrap()).expect("create skill directory");
        std::fs::write(&skill, "projection").expect("write skill file");
        std::fs::create_dir_all(temp.path().join(".codex/personal/skills/nested/inner"))
            .expect("create nested directory");
        std::fs::write(
            temp.path()
                .join(".codex/personal/skills/nested/inner/SKILL.md"),
            "not matched",
        )
        .expect("write nested file");
        assert_eq!(skill_paths_count(temp.path()), 1);
    }
}
