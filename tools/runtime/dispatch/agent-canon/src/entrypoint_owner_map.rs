// @dependency-start
// contract implementation
// responsibility Verifies thin root entrypoint owner maps and actual required owner links.
// upstream design ../../../../../documents/design/entrypoint-owner-map.md structural grammar and owner-map contract
// upstream implementation ../../../../../tools/validation/semantic/convention/convention_compliance_contracts.toml operational marker ownership manifest
// upstream implementation python_cli_integer.rs provides the shared argparse negative-integer token rule
// downstream implementation docs.rs routes the docs check-entrypoints command
// downstream implementation main.rs registers this docs-family module
// downstream implementation ../../../../../tests/agent_tools/test_check_entrypoint_owner_map.py preserves entrypoint behavior oracles
// downstream implementation ../../../../../.github/workflows/entrypoint-owner-map.yml verifies the exact built source binary
// @dependency-end

use regex::Regex;
use serde::Serialize;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::sync::OnceLock;
use toml_edit::{DocumentMut, Item, TableLike};

const MARKER_MANIFEST_PATH: &str =
    "tools/validation/semantic/convention/convention_compliance_contracts.toml";

#[derive(Clone, Copy)]
struct EntrypointContract {
    path: &'static str,
    title: &'static str,
    headings: &'static [&'static str],
    owner_rows: &'static [&'static [&'static str]],
}

const CONTRACTS: &[EntrypointContract] = &[
    EntrypointContract {
        path: "AGENTS.md",
        title: "# AgentCanon Repository Instructions",
        headings: &["## Repository Role", "## Runtime Owner Map"],
        owner_rows: &[&[
            "unresolved source owner",
            "agents/canonical/SOURCE_ROUTING.md",
            "selected row only",
        ]],
    },
    EntrypointContract {
        path: "agents/canonical/SOURCE_ROUTING.md",
        title: "# AgentCanon Source Routing",
        headings: &[
            "## Repository Role",
            "## Reader Map",
            "## Always-On Boundary",
            "## Runtime Owner Map",
            "## Task Entry",
            "## Validation Routing",
        ],
        owner_rows: &[
            &[
                "root runtime entrypoint",
                "bootstrap.sh",
                "bash bootstrap.sh --help",
            ],
            &[
                "workflow family and role candidates",
                "agents/task_catalog.yaml",
                "check_agent_runtime_alignment.py",
            ],
            &[
                "public skill registry",
                "agents/skills/catalog.yaml",
                "check_agent_runtime_alignment.py",
            ],
            &[
                "AgentCanon source publication",
                "agents/skills/agent-canon-update.md",
                "repository-topic-clone and PR checks",
            ],
            &[
                "entrypoint responsibility grammar",
                "documents/design/entrypoint-owner-map.md",
                "agent-canon docs check-entrypoints",
            ],
        ],
    },
    EntrypointContract {
        path: "ROOT_AGENTS.md",
        title: "# AgentCanon Consumer Instructions",
        headings: &[
            "## Repository Role",
            "## Reader Map",
            "## Always-On Boundary",
            "## Runtime Owner Map",
            "## Task Entry",
            "## Validation Routing",
        ],
        owner_rows: &[
            &[
                "product implementation and behavior",
                "consumer source and design owners",
            ],
            &[
                "build, tests, and runtime environment",
                "consumer build and test owners",
            ],
            &[
                "repository structure and file placement",
                "consumer structure owner",
            ],
            &[
                "root instruction extension",
                "consumer-specific section in this file",
            ],
            &[
                "AgentCanon source maintenance",
                "selected AgentCanon development checkout",
            ],
        ],
    },
];

const ROOT_ENTRYPOINT_PATHS: &[&str] = &["AGENTS.md", "ROOT_AGENTS.md"];

struct Patterns {
    h1: Regex,
    h2: Regex,
    nested_heading: Regex,
    fence: Regex,
    ordered_procedure: Regex,
    direct_command: Regex,
    bullet_command: Regex,
    owner_link: Regex,
}

fn patterns() -> &'static Patterns {
    static PATTERNS: OnceLock<Patterns> = OnceLock::new();
    PATTERNS.get_or_init(|| Patterns {
        h1: Regex::new(r"^#\s+\S").expect("static H1 expression"),
        h2: Regex::new(r"^##\s+\S").expect("static H2 expression"),
        nested_heading: Regex::new(r"^#{3,}\s+\S").expect("static nested heading expression"),
        fence: Regex::new(r"^\s*(?:```|~~~)").expect("static fence expression"),
        ordered_procedure: Regex::new(r"^\s*\d+[.)]\s+\S")
            .expect("static ordered procedure expression"),
        direct_command: Regex::new(
            r"^\s*(?:python(?:3(?:\.\d+)?)?|bash|sh|git|make|cargo|npm|npx|docker|tools/[A-Za-z0-9_./-]+|PYTHONPATH=\S+|AGENT_CANON_[A-Z0-9_]+=\S+)(?:\s|$)",
        )
        .expect("static direct command expression"),
        bullet_command: Regex::new(
            r"^\s*[-*]\s+(?:`)?(?:python(?:3(?:\.\d+)?)?|bash|sh|git|make|cargo|npm|npx|docker|tools/[A-Za-z0-9_./-]+|PYTHONPATH=\S+|AGENT_CANON_[A-Z0-9_]+=\S+)(?:`|\s|$)",
        )
        .expect("static bullet command expression"),
        owner_link: Regex::new(r"\]\(([^\s)]+)\)")
            .expect("static inline owner link expression"),
    })
}

#[derive(Clone, Debug, Serialize)]
struct Finding {
    detail: String,
    line: Option<usize>,
    path: String,
    rule: String,
}

impl Finding {
    fn new(path: &str, rule: &str, detail: impl Into<String>, line: Option<usize>) -> Self {
        Self {
            detail: detail.into(),
            line,
            path: path.to_owned(),
            rule: rule.to_owned(),
        }
    }

    fn render(&self) -> String {
        let location = self
            .line
            .map(|line| format!("{}:{line}", self.path))
            .unwrap_or_else(|| self.path.clone());
        format!(
            "ENTRYPOINT_OWNER_MAP_FINDING={}:{}:{}",
            self.rule, location, self.detail
        )
    }
}

#[derive(Serialize)]
struct JsonReport<'a> {
    checked: Vec<&'static str>,
    findings: &'a [Finding],
    status: &'static str,
}

enum OutputFormat {
    Text,
    Json,
}

struct Options {
    root: PathBuf,
    format: OutputFormat,
}

enum ParseResult {
    Help,
    Options(Options),
}

/// Run `agent-canon docs check-entrypoints`.
pub fn run(args: &[String]) -> i32 {
    let options = match parse_args(args) {
        Ok(ParseResult::Help) => {
            print_help();
            return 0;
        }
        Ok(ParseResult::Options(options)) => options,
        Err(error) => {
            eprintln!("usage: agent-canon docs check-entrypoints [--root <repo-root>] [--format text|json]");
            eprintln!("agent-canon docs check-entrypoints: error: {error}");
            return 2;
        }
    };
    let root = resolve_root(&options.root);
    let findings = match run_checks(&root) {
        Ok(findings) => findings,
        Err(error) => {
            eprintln!("agent-canon docs check-entrypoints: {error}");
            return 1;
        }
    };
    match options.format {
        OutputFormat::Text => println!("{}", render_text(&findings)),
        OutputFormat::Json => println!("{}", render_json(&findings)),
    }
    if findings.is_empty() {
        0
    } else {
        1
    }
}

fn parse_args(args: &[String]) -> Result<ParseResult, String> {
    let mut options = Options {
        root: PathBuf::from("."),
        format: OutputFormat::Text,
    };
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        if matches!(token.as_str(), "-h" | "--help") {
            return Ok(ParseResult::Help);
        }
        if token == "--root" {
            options.root = PathBuf::from(required_value(args, index, token)?);
            index += 2;
            continue;
        }
        if let Some(value) = token.strip_prefix("--root=") {
            options.root = PathBuf::from(value);
        } else if token == "--format" {
            options.format = parse_format(required_value(args, index, token)?)?;
            index += 2;
            continue;
        } else if let Some(value) = token.strip_prefix("--format=") {
            options.format = parse_format(value)?;
        } else if token == "--" {
            if index + 1 < args.len() {
                return Err(format!(
                    "unrecognized arguments: {}",
                    args[index + 1..].join(" ")
                ));
            }
        } else if token.starts_with('-') {
            return Err(format!("unrecognized arguments: {token}"));
        } else {
            return Err(format!("unrecognized arguments: {token}"));
        }
        index += 1;
    }
    Ok(ParseResult::Options(options))
}

fn required_value<'a>(args: &'a [String], index: usize, option: &str) -> Result<&'a str, String> {
    args.get(index + 1)
        .filter(|value| {
            !value.starts_with('-') || *value == "-" || is_argparse_negative_option_value(value)
        })
        .map(String::as_str)
        .ok_or_else(|| format!("argument {option}: expected one argument"))
}

fn is_argparse_negative_option_value(value: &str) -> bool {
    static NEGATIVE_FLOAT: OnceLock<Regex> = OnceLock::new();
    crate::python_cli_integer::is_argparse_negative_number(value)
        || NEGATIVE_FLOAT
            .get_or_init(|| Regex::new(r"^-\d*\.\d+$").expect("static negative float regex"))
            .is_match(value)
}

fn parse_format(raw: &str) -> Result<OutputFormat, String> {
    match raw {
        "text" => Ok(OutputFormat::Text),
        "json" => Ok(OutputFormat::Json),
        _ => Err(format!(
            "argument --format: invalid choice: {} (choose from 'text', 'json')",
            python_string_repr(raw)
        )),
    }
}

fn print_help() {
    println!(
        "Verify that AGENTS.md entrypoints are thin canonical owner maps.\n\n\
         usage: agent-canon docs check-entrypoints [--root <repo-root>] [--format text|json]\n\n\
         options:\n\
           -h, --help          show this help message and exit\n\
           --root <path>       Repository root. Defaults to cwd.\n\
           --format text|json  Output format. Defaults to text."
    );
}

fn resolve_root(root: &Path) -> PathBuf {
    if let Ok(canonical) = fs::canonicalize(root) {
        return canonical;
    }
    let absolute = if root.is_absolute() {
        root.to_path_buf()
    } else {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(root)
    };
    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                if !normalized.pop() && !normalized.has_root() {
                    normalized.push(component.as_os_str());
                }
            }
            other => normalized.push(other.as_os_str()),
        }
    }
    normalized
}

fn run_checks(root: &Path) -> Result<Vec<Finding>, String> {
    let mut findings = Vec::new();
    for contract in CONTRACTS {
        findings.extend(check_entrypoint(root, contract)?);
    }
    findings.extend(check_marker_manifest(root));
    findings.sort_by(|left, right| {
        (
            left.path.as_str(),
            left.line.map_or(-1i128, |line| line as i128),
            left.rule.as_str(),
            left.detail.as_str(),
        )
            .cmp(&(
                right.path.as_str(),
                right.line.map_or(-1i128, |line| line as i128),
                right.rule.as_str(),
                right.detail.as_str(),
            ))
    });
    Ok(findings)
}

fn check_entrypoint(root: &Path, contract: &EntrypointContract) -> Result<Vec<Finding>, String> {
    let target = root.join(contract.path);
    if !target.is_file() {
        return Ok(vec![Finding::new(contract.path, "file", "missing", None)]);
    }
    let text = fs::read_to_string(&target)
        .map_err(|error| format!("cannot read {}: {error}", contract.path))?;
    let lines = split_python_lines(&text);
    let mut findings = Vec::new();
    if contract.path == "AGENTS.md" && lines.first().copied() != Some("@ROOT_AGENTS.md") {
        findings.push(Finding::new(
            contract.path,
            "common-base",
            "expected-leading=@ROOT_AGENTS.md",
            Some(1),
        ));
    }

    let h1 = lines
        .iter()
        .enumerate()
        .filter(|(_, line)| patterns().h1.is_match(line))
        .map(|(index, line)| (index + 1, python_strip(line)))
        .collect::<Vec<_>>();
    if h1.len() != 1 {
        findings.push(Finding::new(
            contract.path,
            "title",
            format!("h1-count={}", h1.len()),
            None,
        ));
    } else if h1[0].1 != contract.title {
        findings.push(Finding::new(
            contract.path,
            "title",
            format!("expected={}", python_string_repr(contract.title)),
            Some(h1[0].0),
        ));
    }

    let actual_headings = lines
        .iter()
        .map(|line| python_strip(line))
        .filter(|line| patterns().h2.is_match(line))
        .collect::<Vec<_>>();
    if actual_headings.as_slice() != contract.headings {
        findings.push(Finding::new(
            contract.path,
            "heading-sequence",
            format!(
                "expected={};actual={}",
                python_tuple_repr(contract.headings.iter().copied()),
                python_tuple_repr(actual_headings.iter().copied())
            ),
            None,
        ));
    }

    for (index, line) in lines.iter().enumerate() {
        let line_number = index + 1;
        if patterns().nested_heading.is_match(line) {
            findings.push(Finding::new(
                contract.path,
                "nested-heading",
                python_strip(line).to_owned(),
                Some(line_number),
            ));
        }
        if patterns().fence.is_match(line) {
            findings.push(Finding::new(
                contract.path,
                "fenced-recipe",
                python_strip(line).to_owned(),
                Some(line_number),
            ));
        }
        if patterns().ordered_procedure.is_match(line) {
            findings.push(Finding::new(
                contract.path,
                "ordered-procedure",
                python_strip(line).to_owned(),
                Some(line_number),
            ));
        }
        if patterns().direct_command.is_match(line) || patterns().bullet_command.is_match(line) {
            findings.push(Finding::new(
                contract.path,
                "command-recipe",
                python_strip(line).to_owned(),
                Some(line_number),
            ));
        }
    }

    match section_lines(&lines, "## Runtime Owner Map") {
        None => findings.push(Finding::new(
            contract.path,
            "owner-map",
            "missing-section",
            None,
        )),
        Some(owner_section) => {
            let rows = table_rows(&owner_section);
            for markers in contract.owner_rows.iter().copied() {
                let matching = rows
                    .iter()
                    .filter(|row| {
                        markers
                            .iter()
                            .all(|marker| (*row).as_str().contains(*marker))
                    })
                    .collect::<Vec<_>>();
                if matching.is_empty() {
                    findings.push(Finding::new(
                        contract.path,
                        "owner-map",
                        format!("missing-row={}", markers[0]),
                        None,
                    ));
                } else {
                    findings.extend(check_owner_links(root, contract, &matching, markers));
                }
            }
        }
    }
    Ok(findings)
}

fn section_lines<'a>(lines: &[&'a str], heading: &str) -> Option<Vec<&'a str>> {
    let start = lines
        .iter()
        .position(|line| python_strip(line) == heading)?;
    Some(
        lines[start + 1..]
            .iter()
            .copied()
            .take_while(|line| !patterns().h2.is_match(python_strip(line)))
            .collect(),
    )
}

fn table_rows(lines: &[&str]) -> Vec<String> {
    lines
        .iter()
        .filter_map(|line| {
            let stripped = python_strip(line);
            if !stripped.starts_with('|') || !stripped.ends_with('|') {
                return None;
            }
            let cells = stripped
                .trim_matches('|')
                .split('|')
                .map(str::trim)
                .collect::<Vec<_>>();
            let separator = !cells.is_empty()
                && cells.iter().all(|cell| {
                    !cell.is_empty() && cell.chars().all(|ch| matches!(ch, '-' | ':' | ' '))
                });
            (!separator).then(|| stripped.to_owned())
        })
        .collect()
}

fn check_owner_links(
    root: &Path,
    contract: &EntrypointContract,
    rows: &[&String],
    markers: &[&str],
) -> Vec<Finding> {
    let destinations = rows
        .iter()
        .flat_map(|row| {
            patterns()
                .owner_link
                .captures_iter(row.as_str())
                .filter_map(|capture| capture.get(1).map(|href| href.as_str()))
        })
        .map(|href| href.split('#').next().unwrap_or_default())
        .map(|href| normalize_posix_destination(contract.path, href))
        .collect::<std::collections::BTreeSet<_>>();
    let mut findings = Vec::new();
    for target in markers.iter().filter(|target| target.ends_with(".md")) {
        if !destinations.contains(*target) {
            findings.push(Finding::new(
                contract.path,
                "owner-link",
                format!("missing-destination={target}"),
                None,
            ));
        }
        if !root.join(*target).is_file() {
            findings.push(Finding::new(
                contract.path,
                "owner-target",
                format!("missing-file={target}"),
                None,
            ));
        }
    }
    findings
}

fn normalize_posix_destination(source_path: &str, href: &str) -> String {
    let input = if href.starts_with('/') {
        href.to_owned()
    } else {
        let parent = source_path
            .rsplit_once('/')
            .map_or("", |(parent, _)| parent);
        if parent.is_empty() {
            href.to_owned()
        } else {
            format!("{parent}/{href}")
        }
    };
    let absolute = input.starts_with('/');
    let mut components = Vec::<&str>::new();
    for component in input.split('/') {
        match component {
            "" | "." => {}
            ".." => {
                if components.last().is_some_and(|part| *part != "..") {
                    components.pop();
                } else if !absolute {
                    components.push("..");
                }
            }
            other => components.push(other),
        }
    }
    let body = components.join("/");
    if absolute {
        format!("/{body}")
    } else if body.is_empty() {
        ".".to_owned()
    } else {
        body
    }
}

fn check_marker_manifest(root: &Path) -> Vec<Finding> {
    let target = root.join(MARKER_MANIFEST_PATH);
    if !target.is_file() {
        return vec![Finding::new(
            MARKER_MANIFEST_PATH,
            "marker-manifest",
            "missing",
            None,
        )];
    }
    let text = match fs::read_to_string(&target) {
        Ok(text) => text,
        Err(error) => {
            return vec![Finding::new(
                MARKER_MANIFEST_PATH,
                "marker-manifest",
                format!("parse-error={}", io_error_name(&error)),
                None,
            )];
        }
    };
    let document = match text.parse::<DocumentMut>() {
        Ok(document) => document,
        Err(_) => {
            return vec![Finding::new(
                MARKER_MANIFEST_PATH,
                "marker-manifest",
                "parse-error=TOMLDecodeError",
                None,
            )];
        }
    };
    let Some(contracts_item) = document.get("contracts") else {
        return vec![Finding::new(
            MARKER_MANIFEST_PATH,
            "marker-manifest",
            "contracts-not-list",
            None,
        )];
    };
    let Some(contracts) = table_list(contracts_item) else {
        return vec![Finding::new(
            MARKER_MANIFEST_PATH,
            "marker-manifest",
            "contracts-not-list",
            None,
        )];
    };
    let mut findings = Vec::new();
    for contract in contracts {
        let Some(contract) = contract else {
            findings.push(Finding::new(
                MARKER_MANIFEST_PATH,
                "marker-manifest",
                "contract-not-table",
                None,
            ));
            continue;
        };
        let contract_id = toml_python_string(contract.get("id"));
        let Some(surfaces_item) = contract.get("surfaces") else {
            continue;
        };
        let Some(surfaces) = table_list(surfaces_item) else {
            findings.push(Finding::new(
                MARKER_MANIFEST_PATH,
                "marker-manifest",
                format!("contract={contract_id};surfaces-not-list"),
                None,
            ));
            continue;
        };
        for surface in surfaces {
            let Some(surface) = surface else {
                findings.push(Finding::new(
                    MARKER_MANIFEST_PATH,
                    "marker-manifest",
                    format!("contract={contract_id};surface-not-table"),
                    None,
                ));
                continue;
            };
            if surface
                .get("path")
                .and_then(Item::as_str)
                .is_some_and(|path| ROOT_ENTRYPOINT_PATHS.contains(&path))
            {
                let surface_path = surface
                    .get("path")
                    .and_then(Item::as_str)
                    .unwrap_or_default();
                findings.push(Finding::new(
                    MARKER_MANIFEST_PATH,
                    "delegated-marker-surface",
                    format!("contract={contract_id};path={surface_path}"),
                    None,
                ));
            }
        }
    }
    findings
}

fn table_list(item: &Item) -> Option<Vec<Option<&dyn TableLike>>> {
    if let Some(tables) = item.as_array_of_tables() {
        return Some(
            tables
                .iter()
                .map(|table| Some(table as &dyn TableLike))
                .collect(),
        );
    }
    let array = item.as_array()?;
    Some(
        array
            .iter()
            .map(|value| value.as_inline_table().map(|table| table as &dyn TableLike))
            .collect(),
    )
}

fn toml_python_string(value: Option<&Item>) -> String {
    let Some(value) = value else {
        return "<missing>".to_owned();
    };
    if let Some(value) = value.as_str() {
        value.to_owned()
    } else if let Some(value) = value.as_bool() {
        if value { "True" } else { "False" }.to_owned()
    } else if let Some(value) = value.as_integer() {
        value.to_string()
    } else if let Some(value) = value.as_float() {
        let mut rendered = value.to_string();
        if value.is_finite()
            && !rendered.contains('.')
            && !rendered.contains('e')
            && !rendered.contains('E')
        {
            rendered.push_str(".0");
        }
        rendered
    } else {
        value.to_string()
    }
}

fn io_error_name(error: &std::io::Error) -> &'static str {
    match error.kind() {
        std::io::ErrorKind::NotFound => "FileNotFoundError",
        std::io::ErrorKind::PermissionDenied => "PermissionError",
        std::io::ErrorKind::IsADirectory => "IsADirectoryError",
        _ => "OSError",
    }
}

fn python_string_repr(value: &str) -> String {
    let quote = if value.contains('\'') && !value.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut rendered = String::from(quote);
    for character in value.chars() {
        match character {
            '\\' => rendered.push_str("\\\\"),
            character if character == quote => {
                rendered.push('\\');
                rendered.push(character);
            }
            '\t' => rendered.push_str("\\t"),
            '\n' => rendered.push_str("\\n"),
            '\r' => rendered.push_str("\\r"),
            character if character.is_control() => {
                let codepoint = character as u32;
                if codepoint <= 0xff {
                    rendered.push_str(&format!("\\x{codepoint:02x}"));
                } else if codepoint <= 0xffff {
                    rendered.push_str(&format!("\\u{codepoint:04x}"));
                } else {
                    rendered.push_str(&format!("\\U{codepoint:08x}"));
                }
            }
            character => rendered.push(character),
        }
    }
    rendered.push(quote);
    rendered
}

fn python_strip(value: &str) -> &str {
    value.trim_matches(|character: char| {
        character.is_whitespace()
            || matches!(character, '\u{001c}' | '\u{001d}' | '\u{001e}' | '\u{001f}')
    })
}

fn python_tuple_repr<'a>(values: impl IntoIterator<Item = &'a str>) -> String {
    let values = values.into_iter().collect::<Vec<_>>();
    let mut rendered = values
        .iter()
        .map(|value| python_string_repr(value))
        .collect::<Vec<_>>()
        .join(", ");
    if values.len() == 1 {
        rendered.push(',');
    }
    format!("({rendered})")
}

fn split_python_lines(value: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut line_start = 0;
    let mut characters = value.char_indices().peekable();
    while let Some((index, character)) = characters.next() {
        if !is_python_line_break(character) {
            continue;
        }
        lines.push(&value[line_start..index]);
        line_start = index + character.len_utf8();
        if character == '\r' && characters.peek().is_some_and(|(_, next)| *next == '\n') {
            let (newline_index, newline) = characters.next().expect("peeked newline exists");
            line_start = newline_index + newline.len_utf8();
        }
    }
    if line_start < value.len() {
        lines.push(&value[line_start..]);
    }
    lines
}

fn is_python_line_break(character: char) -> bool {
    matches!(
        character,
        '\n' | '\r'
            | '\u{000b}'
            | '\u{000c}'
            | '\u{001c}'
            | '\u{001d}'
            | '\u{001e}'
            | '\u{0085}'
            | '\u{2028}'
            | '\u{2029}'
    )
}

fn render_text(findings: &[Finding]) -> String {
    let mut lines = findings.iter().map(Finding::render).collect::<Vec<_>>();
    lines.push(format!("ENTRYPOINT_OWNER_MAP_FINDINGS={}", findings.len()));
    lines.push(format!(
        "ENTRYPOINT_OWNER_MAP={}",
        if findings.is_empty() { "pass" } else { "fail" }
    ));
    lines.join("\n")
}

fn render_json(findings: &[Finding]) -> String {
    let report = JsonReport {
        checked: CONTRACTS.iter().map(|contract| contract.path).collect(),
        findings,
        status: if findings.is_empty() { "pass" } else { "fail" },
    };
    serde_json::to_string_pretty(&report).expect("entrypoint owner-map report is JSON serializable")
}
