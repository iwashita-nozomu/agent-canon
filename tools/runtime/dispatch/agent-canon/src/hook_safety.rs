// @dependency-start
// contract implementation
// responsibility Owns pure native secret matching, protected Git intent classification, and redacted safety payloads.
// upstream implementation ../../../../../tools/runtime/authority/hook_safety.py owns the currently active Python leaf contract.
// downstream implementation ../tests/hook_safety_native.rs checks frozen old-API inputs and outputs.
// downstream test ../../../../../tests/fixtures/hook_safety/python_golden.json freezes the accepted CPython 3.12.3 oracle.
// @dependency-end
//! Pure hook safety leaves used by the future native hook consumer.

use crate::python_text::{is_python_whitespace, python_strip};
use regex::Regex;
use serde::Serialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, VecDeque};
use std::path::Path;
use std::sync::LazyLock;

/// Tool names whose command fields are interpreted as shell commands.
pub const SHELL_TOOL_NAMES: [&str; 2] = ["Bash", "bash"];

const COMMAND_SEPARATORS: [&str; 5] = ["&&", "||", ";", "|", "&"];
const GROUPING_TOKENS: [&str; 4] = ["(", ")", "{", "}"];
const SHELL_COMMENT_BOUNDARY_CHARS: &str = ";&|()<>";
const SHELL_WRAPPERS: [&str; 3] = ["bash", "sh", "zsh"];
const BRANCH_AUTHORITY_ENV: &str = "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY";
const BRANCH_REASON_ENV: &str = "AGENT_CANON_BRANCH_WORKTREE_REASON";
const DESTRUCTIVE_AUTHORITY_ENV: &str = "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY";
const DESTRUCTIVE_REASON_ENV: &str = "AGENT_CANON_DESTRUCTIVE_GIT_REASON";
const DESTRUCTIVE_AUTHORITY: &str = "explicit_user_approval";
const ALLOWED_BRANCH_AUTHORITIES: [&str; 2] = ["user_request", "agent_canon_workflow"];
const READ_ONLY_BRANCH_OPTIONS: [&str; 19] = [
    "--all",
    "--color",
    "--contains",
    "--format",
    "--ignore-case",
    "--list",
    "--merged",
    "--no-color",
    "--no-contains",
    "--no-merged",
    "--points-at",
    "--remotes",
    "--show-current",
    "--sort",
    "--verbose",
    "-a",
    "-r",
    "-v",
    "-vv",
];
const READ_ONLY_BRANCH_VALUE_OPTIONS: [&str; 8] = [
    "--color",
    "--contains",
    "--format",
    "--merged",
    "--no-contains",
    "--no-merged",
    "--points-at",
    "--sort",
];
const BENIGN_BRANCH_OPTIONS: [&str; 3] = ["--edit-description", "--unset-upstream", "-u"];
const BENIGN_BRANCH_VALUE_OPTIONS: [&str; 2] = ["--set-upstream-to", "-u"];
const BRANCH_NORMAL_CREATE_SHORTS: [char; 1] = ['c'];
const BRANCH_FORCE_SHORTS: [char; 2] = ['C', 'f'];
const BRANCH_DESTRUCTIVE_SHORTS: [char; 4] = ['D', 'M', 'd', 'm'];
const BRANCH_CREATION_MODIFIERS: [&str; 3] = ["--create-reflog", "--no-track", "--track"];
const PROTECTED_GIT_SUBCOMMANDS: [&str; 8] = [
    "restore", "reset", "clean", "checkout", "switch", "stash", "branch", "worktree",
];
const OPAQUE_GIT_OPTIONS_WITH_VALUES: [&str; 7] = [
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
    "--config-env",
];
const PUNCTUATION_CHARS: &str = ";&|(){}!";
const PYTHON_15_WORD_CHAR: &str = r"[\p{Age:15.0}&&[\pL\pN_]]";
const PYTHON_15_NONWORD_CHAR: &str = r"[^[\p{Age:15.0}&&[\pL\pN_]]]";
const PYTHON_15_START_BOUNDARY: &str = r"(?:\A|[^[\p{Age:15.0}&&[\pL\pN_]]])";
const PYTHON_15_END_BOUNDARY: &str = r"(?:\z|[^[\p{Age:15.0}&&[\pL\pN_]]])";

static SECRET_PATTERNS: LazyLock<[(Regex, &'static str); 4]> = LazyLock::new(|| {
    [
        (
            Regex::new(r"-----BEGIN (RSA |DSA |EC |OPENSSH |)PRIVATE KEY-----")
                .expect("static private-key pattern is valid"),
            "private key block",
        ),
        (
            Regex::new(&format!(
                r"{PYTHON_15_START_BOUNDARY}AKIA[0-9A-Z]{{16}}{PYTHON_15_END_BOUNDARY}"
            ))
            .expect("static AWS key pattern is valid"),
            "AWS access key id",
        ),
        (
            Regex::new(&format!(
                r"{PYTHON_15_START_BOUNDARY}gh[pousr]_[A-Za-z0-9_]{{30,}}{PYTHON_15_END_BOUNDARY}"
            ))
            .expect("static GitHub token pattern is valid"),
            "GitHub token",
        ),
        (
            Regex::new(&format!(
                r"{PYTHON_15_START_BOUNDARY}sk-(?:[A-Za-z0-9_-]{{31,}}[A-Za-z0-9_](?:\z|{PYTHON_15_NONWORD_CHAR})|[A-Za-z0-9_-]{{31,}}-{PYTHON_15_WORD_CHAR})"
            ))
            .expect("static API key pattern is valid"),
            "OpenAI-style API key",
        ),
    ]
});

/// One visible Git invocation and its same-segment assignments.
#[derive(Clone, Debug)]
struct GitCommand {
    tokens: Vec<String>,
    assignments: BTreeMap<String, String>,
}

/// One protected Git intent and the authority it requires.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct GitIntent {
    pub kind: String,
    pub subcommand: String,
    pub evidence: String,
    pub requires_creation: bool,
    pub requires_destructive: bool,
}

impl GitIntent {
    fn new(
        kind: &str,
        subcommand: &str,
        evidence: &str,
        requires_creation: bool,
        requires_destructive: bool,
    ) -> Self {
        Self {
            kind: kind.to_owned(),
            subcommand: subcommand.to_owned(),
            evidence: evidence.to_owned(),
            requires_creation,
            requires_destructive,
        }
    }
}

enum FirstBlockWorkItem {
    Command(String),
    Direct(String),
    Segments(std::vec::IntoIter<Vec<String>>),
    EvalWords(VecDeque<String>),
}

/// Return the first high-confidence secret class in prompt text.
pub fn secret_kind(prompt: &str) -> Option<&'static str> {
    SECRET_PATTERNS
        .iter()
        .find_map(|(pattern, kind)| pattern.is_match(prompt).then_some(*kind))
}

/// Return a block payload without retaining the matched prompt.
pub fn secret_block_payload(secret: &str) -> Value {
    json!({
        "decision": "block",
        "reason": format!(
            "Prompt appears to include a {secret}. Remove the secret or replace it with a redacted placeholder."
        ),
        "next_action": "remove_secret_or_use_redacted_placeholder_then_retry",
        "remediation": [
            "Remove the secret material from the prompt.",
            format!(
                "Replace examples with redacted placeholders such as {}[REDACTED_TOKEN]{}.",
                char::from(96_u8),
                char::from(96_u8)
            ),
            "Rotate the secret if it was pasted into the session by mistake.",
        ],
    })
}

/// Return the only command identity allowed in a safety payload.
pub fn command_sha256(command: &str) -> String {
    let digest = Sha256::digest(command.as_bytes());
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

/// Return the shell tool name when the value is a string.
pub fn payload_tool_name(payload: &Value) -> &str {
    payload
        .get("tool_name")
        .and_then(Value::as_str)
        .unwrap_or("")
}

/// Return the first nested or top-level command string in payload precedence order.
pub fn payload_tool_command(payload: &Value) -> &str {
    if let Some(tool_input) = payload.get("tool_input").and_then(Value::as_object) {
        for key in ["command", "cmd"] {
            if let Some(value) = tool_input.get(key).and_then(Value::as_str) {
                return value;
            }
        }
    }
    for key in ["command", "cmd"] {
        if let Some(value) = payload.get(key).and_then(Value::as_str) {
            return value;
        }
    }
    ""
}

/// Return the prompt when the value is a string.
pub fn payload_prompt(payload: &Value) -> &str {
    payload.get("prompt").and_then(Value::as_str).unwrap_or("")
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ShlexState {
    Whitespace,
    Word,
    SingleQuoted,
    DoubleQuoted,
    EscapedWord,
    EscapedDoubleQuoted,
    Punctuation,
}

fn is_shlex_whitespace(character: char) -> bool {
    matches!(character, ' ' | '\t' | '\r' | '\n')
}

fn is_punctuation(character: char) -> bool {
    PUNCTUATION_CHARS.contains(character)
}

fn push_token(tokens: &mut Vec<String>, token: &mut String, started: &mut bool) {
    if *started {
        tokens.push(std::mem::take(token));
        *started = false;
    }
}

/// Return POSIX shlex tokens with the old punctuation set; malformed input yields no tokens.
fn shell_tokens(command: &str) -> Vec<String> {
    let stripped = python_strip(command);
    if stripped.is_empty() {
        return Vec::new();
    }

    let characters: Vec<char> = stripped.chars().collect();
    let mut tokens = Vec::new();
    let mut token = String::new();
    let mut started = false;
    let mut state = ShlexState::Whitespace;
    let mut index = 0;

    while index < characters.len() {
        let character = characters[index];
        match state {
            ShlexState::Whitespace => {
                if is_shlex_whitespace(character) {
                    index += 1;
                } else if character == '#' {
                    while index < characters.len() && characters[index] != '\n' {
                        index += 1;
                    }
                } else if character == '\'' {
                    started = true;
                    state = ShlexState::SingleQuoted;
                    index += 1;
                } else if character == '"' {
                    started = true;
                    state = ShlexState::DoubleQuoted;
                    index += 1;
                } else if character == '\\' {
                    started = true;
                    state = ShlexState::EscapedWord;
                    index += 1;
                } else if is_punctuation(character) {
                    token.push(character);
                    started = true;
                    state = ShlexState::Punctuation;
                    index += 1;
                } else {
                    token.push(character);
                    started = true;
                    state = ShlexState::Word;
                    index += 1;
                }
            }
            ShlexState::Word => {
                if is_shlex_whitespace(character) {
                    push_token(&mut tokens, &mut token, &mut started);
                    state = ShlexState::Whitespace;
                    index += 1;
                } else if character == '#' {
                    push_token(&mut tokens, &mut token, &mut started);
                    state = ShlexState::Whitespace;
                } else if character == '\\' {
                    state = ShlexState::EscapedWord;
                    index += 1;
                } else if character == '\'' {
                    state = ShlexState::SingleQuoted;
                    index += 1;
                } else if character == '"' {
                    state = ShlexState::DoubleQuoted;
                    index += 1;
                } else if is_punctuation(character) {
                    push_token(&mut tokens, &mut token, &mut started);
                    state = ShlexState::Whitespace;
                } else {
                    token.push(character);
                    index += 1;
                }
            }
            ShlexState::SingleQuoted => {
                if character == '\'' {
                    state = ShlexState::Word;
                } else {
                    token.push(character);
                }
                index += 1;
            }
            ShlexState::DoubleQuoted => {
                if character == '"' {
                    state = ShlexState::Word;
                    index += 1;
                } else if character == '\\' {
                    state = ShlexState::EscapedDoubleQuoted;
                    index += 1;
                } else {
                    token.push(character);
                    index += 1;
                }
            }
            ShlexState::EscapedWord => {
                if character != '\n' {
                    token.push(character);
                }
                state = ShlexState::Word;
                index += 1;
            }
            ShlexState::EscapedDoubleQuoted => {
                if character == '"' || character == '\\' {
                    token.push(character);
                } else {
                    token.push('\\');
                    token.push(character);
                }
                state = ShlexState::DoubleQuoted;
                index += 1;
            }
            ShlexState::Punctuation => {
                if is_punctuation(character) {
                    token.push(character);
                    index += 1;
                } else {
                    push_token(&mut tokens, &mut token, &mut started);
                    state = ShlexState::Whitespace;
                }
            }
        }
    }

    if matches!(
        state,
        ShlexState::SingleQuoted
            | ShlexState::DoubleQuoted
            | ShlexState::EscapedWord
            | ShlexState::EscapedDoubleQuoted
    ) {
        return Vec::new();
    }
    push_token(&mut tokens, &mut token, &mut started);
    tokens
}

fn is_backslash_escapable_in_double_quote(character: char) -> bool {
    matches!(character, '$' | '\u{0060}' | '"' | '\\' | '\n')
}

fn is_shell_comment_boundary(character: char) -> bool {
    is_python_whitespace(character) || SHELL_COMMENT_BOUNDARY_CHARS.contains(character)
}

/// Return complete and uncertain executable backtick bodies without shell I/O.
fn backtick_command_substitutions(command: &str) -> (Vec<String>, Vec<String>) {
    let characters: Vec<char> = command.chars().collect();
    let mut complete = Vec::new();
    let mut active: Option<Vec<char>> = None;
    let mut single_quoted = false;
    let mut double_quoted = false;
    let mut in_comment = false;
    let mut comment_boundary = true;
    let mut active_single_quoted = false;
    let mut active_double_quoted = false;
    let mut active_in_comment = false;
    let mut active_comment_boundary = true;
    let mut index = 0;

    while index < characters.len() {
        let character = characters[index];
        if let Some(mut body) = active.take() {
            if active_in_comment {
                body.push(character);
                if character == '\n' {
                    active_in_comment = false;
                    active_comment_boundary = true;
                }
                active = Some(body);
                index += 1;
                continue;
            }
            if character == '\\' && !active_single_quoted && index + 1 < characters.len() {
                let escaped = characters[index + 1];
                if !active_double_quoted || is_backslash_escapable_in_double_quote(escaped) {
                    body.push(character);
                    body.push(escaped);
                    if escaped != '\n' {
                        active_comment_boundary = false;
                    }
                    active = Some(body);
                    index += 2;
                    continue;
                }
                body.push(character);
                active_comment_boundary = false;
                active = Some(body);
                index += 1;
                continue;
            }
            if character == '\u{0060}' {
                complete.push(body.iter().collect());
                comment_boundary = false;
                index += 1;
                continue;
            }
            body.push(character);
            if character == '\'' && !active_double_quoted {
                active_single_quoted = !active_single_quoted;
                active_comment_boundary = false;
            } else if character == '"' && !active_single_quoted {
                active_double_quoted = !active_double_quoted;
                active_comment_boundary = false;
            } else if character == '#'
                && !active_single_quoted
                && !active_double_quoted
                && active_comment_boundary
            {
                active_in_comment = true;
            } else {
                active_comment_boundary = !active_single_quoted
                    && !active_double_quoted
                    && is_shell_comment_boundary(character);
            }
            active = Some(body);
            index += 1;
            continue;
        }

        if in_comment {
            if character == '\n' {
                in_comment = false;
                comment_boundary = true;
            }
            index += 1;
            continue;
        }
        if character == '\\' && !single_quoted && index + 1 < characters.len() {
            let escaped = characters[index + 1];
            if !double_quoted || is_backslash_escapable_in_double_quote(escaped) {
                if escaped != '\n' || double_quoted {
                    comment_boundary = false;
                }
                index += 2;
                continue;
            }
            comment_boundary = false;
            index += 1;
            continue;
        }
        if character == '\'' && !double_quoted {
            single_quoted = !single_quoted;
            comment_boundary = false;
        } else if character == '"' && !single_quoted {
            double_quoted = !double_quoted;
            comment_boundary = false;
        } else if character == '#' && !single_quoted && !double_quoted && comment_boundary {
            in_comment = true;
        } else if character == '\u{0060}' && !single_quoted {
            active = Some(Vec::new());
            active_single_quoted = false;
            active_double_quoted = false;
            active_in_comment = false;
            active_comment_boundary = true;
            comment_boundary = false;
        } else {
            comment_boundary =
                !single_quoted && !double_quoted && is_shell_comment_boundary(character);
        }
        index += 1;
    }

    let uncertain = active
        .map(|body| vec![body.iter().collect()])
        .unwrap_or_default();
    (complete, uncertain)
}

fn command_basename(token: &str) -> &str {
    Path::new(token)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("")
}

fn assignment(token: &str) -> Option<(String, String)> {
    let (name, value) = token.split_once('=')?;
    if name.is_empty() || token.starts_with('-') {
        return None;
    }
    let mut characters = name.chars();
    let first = characters.next()?;
    if !first.is_alphabetic() && first != '_' {
        return None;
    }
    if !characters.all(|character| character.is_alphanumeric() || character == '_') {
        return None;
    }
    Some((name.to_owned(), value.to_owned()))
}

fn is_command_separator(token: &str) -> bool {
    COMMAND_SEPARATORS.contains(&token) || token.chars().all(|character| ";&|".contains(character))
}

fn command_segments(tokens: Vec<String>) -> Vec<Vec<String>> {
    let mut segments = Vec::new();
    let mut current = Vec::new();
    for token in tokens {
        if is_command_separator(&token) {
            if !current.is_empty() {
                segments.push(std::mem::take(&mut current));
            }
        } else {
            current.push(token);
        }
    }
    if !current.is_empty() {
        segments.push(current);
    }
    segments
}

fn eval_join_preserves_shell_tokens(tokens: &[String]) -> bool {
    if tokens.is_empty()
        || tokens.iter().any(|token| {
            token.is_empty()
                || token.chars().any(|character| {
                    is_shlex_whitespace(character)
                        || matches!(character, '\'' | '"' | '\\' | '#' | '\u{0060}')
                        || is_punctuation(character)
                })
                || token.chars().next().is_some_and(is_python_whitespace)
        })
    {
        return false;
    }
    !tokens
        .last()
        .and_then(|token| token.chars().last())
        .is_some_and(is_python_whitespace)
}

fn is_leading_grouping(token: &str) -> bool {
    GROUPING_TOKENS.contains(&token) || token.chars().all(|character| "(){}!".contains(character))
}

fn is_trailing_grouping(token: &str) -> bool {
    GROUPING_TOKENS.contains(&token) || token.chars().all(|character| "(){}".contains(character))
}

fn strip_grouping(tokens: &[String]) -> Vec<String> {
    let mut start = 0;
    while start < tokens.len() && is_leading_grouping(&tokens[start]) {
        start += 1;
    }
    let mut end = tokens.len();
    while end > start && is_trailing_grouping(&tokens[end - 1]) {
        end -= 1;
    }
    tokens[start..end].to_vec()
}

fn consume_time_prefix(tokens: &[String], mut index: usize) -> usize {
    if index >= tokens.len() || command_basename(&tokens[index]) != "time" {
        return index;
    }
    index += 1;
    while index < tokens.len() {
        let token = &tokens[index];
        if token == "--" {
            return index + 1;
        }
        if ["-f", "--format", "-o", "--output"].contains(&token.as_str()) {
            index += 2;
            continue;
        }
        if token.starts_with('-') {
            index += 1;
            continue;
        }
        break;
    }
    index
}

fn consume_command_prefix(tokens: &[String], mut index: usize) -> usize {
    if index >= tokens.len() || command_basename(&tokens[index]) != "command" {
        return index;
    }
    index += 1;
    while index < tokens.len() {
        let token = &tokens[index];
        if token == "--" {
            return index + 1;
        }
        if ["-p", "-v", "-V"].contains(&token.as_str()) {
            index += 1;
            continue;
        }
        break;
    }
    index
}

fn consume_env_prefix(
    tokens: &[String],
    mut index: usize,
    values: &mut BTreeMap<String, String>,
) -> usize {
    if index >= tokens.len() || command_basename(&tokens[index]) != "env" {
        return index;
    }
    index += 1;
    while index < tokens.len() {
        let token = &tokens[index];
        if token == "--" {
            return index + 1;
        }
        if ["-u", "--unset"].contains(&token.as_str()) {
            if index + 1 < tokens.len() {
                values.remove(&tokens[index + 1]);
            }
            index += 2;
            continue;
        }
        if let Some(name) = token.strip_prefix("--unset=") {
            values.remove(name);
            index += 1;
            continue;
        }
        if ["-i", "--ignore-environment", "-0", "--null"].contains(&token.as_str()) {
            index += 1;
            continue;
        }
        if let Some((name, value)) = assignment(token) {
            values.insert(name, value);
            index += 1;
            continue;
        }
        if token.starts_with('-') {
            index += 1;
            continue;
        }
        break;
    }
    index
}

fn git_subcommand_index(tokens: &[String], git_index: usize) -> usize {
    let mut index = git_index + 1;
    while index < tokens.len() {
        let token = &tokens[index];
        if [
            "-C",
            "-c",
            "--git-dir",
            "--work-tree",
            "--namespace",
            "--config-env",
        ]
        .contains(&token.as_str())
        {
            index += 2;
            continue;
        }
        if [
            "-p",
            "-P",
            "--paginate",
            "--no-pager",
            "--bare",
            "--no-replace-objects",
            "--literal-pathspecs",
            "--glob-pathspecs",
            "--noglob-pathspecs",
            "--icase-pathspecs",
            "--exec-path",
        ]
        .contains(&token.as_str())
        {
            index += 1;
            continue;
        }
        if (token.starts_with("-C") || token.starts_with("-c")) && token.len() > 2 {
            index += 1;
            continue;
        }
        if [
            "--git-dir=",
            "--work-tree=",
            "--namespace=",
            "--exec-path=",
            "--config-env=",
        ]
        .iter()
        .any(|prefix| token.starts_with(prefix))
        {
            index += 1;
            continue;
        }
        break;
    }
    index
}

fn normalized_git_command(segment: &[String]) -> Option<GitCommand> {
    let tokens = strip_grouping(segment);
    let mut values = BTreeMap::new();
    let mut index = 0;
    while index < tokens.len() {
        if let Some((name, value)) = assignment(&tokens[index]) {
            values.insert(name, value);
            index += 1;
        } else {
            break;
        }
    }
    index = consume_time_prefix(&tokens, index);
    index = consume_command_prefix(&tokens, index);
    index = consume_env_prefix(&tokens, index, &mut values);
    while index < tokens.len() {
        if let Some((name, value)) = assignment(&tokens[index]) {
            values.insert(name, value);
            index += 1;
        } else {
            break;
        }
    }
    index = consume_command_prefix(&tokens, index);
    if index >= tokens.len() || command_basename(&tokens[index]) != "git" {
        return None;
    }
    let subcommand_index = git_subcommand_index(&tokens, index);
    let command_tokens = tokens.get(subcommand_index..).unwrap_or_default().to_vec();
    Some(GitCommand {
        tokens: command_tokens,
        assignments: values,
    })
}

fn wrapper_script(segment: &[String]) -> String {
    let tokens = strip_grouping(segment);
    let mut index = consume_time_prefix(&tokens, 0);
    index = consume_command_prefix(&tokens, index);
    if index < tokens.len() && command_basename(&tokens[index]) == "eval" {
        return tokens[index + 1..].join(" ");
    }
    if index >= tokens.len() || !SHELL_WRAPPERS.contains(&command_basename(&tokens[index])) {
        return String::new();
    }
    for option_index in index + 1..tokens.len() {
        let token = &tokens[option_index];
        if token == "--" {
            return String::new();
        }
        if token == "-c"
            || (token.starts_with('-') && !token.starts_with("--") && token[1..].contains('c'))
        {
            return tokens.get(option_index + 1).cloned().unwrap_or_default();
        }
    }
    String::new()
}

fn short_option_letters(arguments: &[String]) -> Vec<char> {
    let mut letters = Vec::new();
    for argument in arguments {
        if argument == "--" {
            break;
        }
        if argument.starts_with('-') && !argument.starts_with("--") {
            letters.extend(argument[1..].chars());
        }
    }
    letters
}

fn has_long_option(arguments: &[String], options: &[&str]) -> bool {
    arguments.iter().any(|argument| {
        options.iter().any(|option| {
            argument == option
                || argument
                    .strip_prefix(option)
                    .is_some_and(|suffix| suffix.starts_with('='))
        })
    })
}

fn branch_is_read_only(arguments: &[String]) -> bool {
    if arguments.is_empty() || (arguments.len() == 1 && arguments[0] == "--show-current") {
        return true;
    }
    let mut index = 0;
    let mut saw_list = false;
    let mut saw_benign_metadata = false;
    while index < arguments.len() {
        let argument = &arguments[index];
        if argument == "--" {
            return false;
        }
        if argument == "--list" {
            saw_list = true;
            index += 1;
            continue;
        }
        if READ_ONLY_BRANCH_VALUE_OPTIONS.contains(&argument.as_str()) {
            index += 2;
            continue;
        }
        if READ_ONLY_BRANCH_VALUE_OPTIONS.iter().any(|option| {
            argument
                .strip_prefix(option)
                .is_some_and(|suffix| suffix.starts_with('='))
        }) {
            index += 1;
            continue;
        }
        if argument.starts_with("-u") && !argument.starts_with("--") && argument != "-u" {
            saw_benign_metadata = true;
            index += 1;
            continue;
        }
        if BENIGN_BRANCH_VALUE_OPTIONS.contains(&argument.as_str()) {
            if index + 1 >= arguments.len() || arguments[index + 1].starts_with('-') {
                return false;
            }
            saw_benign_metadata = true;
            index += 2;
            continue;
        }
        if argument
            .strip_prefix("--set-upstream-to")
            .is_some_and(|suffix| suffix.starts_with('='))
        {
            saw_benign_metadata = true;
            index += 1;
            continue;
        }
        if BENIGN_BRANCH_OPTIONS.contains(&argument.as_str()) {
            saw_benign_metadata = true;
            index += 1;
            continue;
        }
        if READ_ONLY_BRANCH_OPTIONS.contains(&argument.as_str()) {
            index += 1;
            continue;
        }
        if (saw_list || saw_benign_metadata) && !argument.starts_with('-') {
            index += 1;
            continue;
        }
        return false;
    }
    true
}

fn branch_intent(arguments: &[String]) -> Option<GitIntent> {
    if branch_is_read_only(arguments) {
        return None;
    }
    let letters = short_option_letters(arguments);
    if letters
        .iter()
        .any(|letter| BRANCH_FORCE_SHORTS.contains(letter))
        || has_long_option(arguments, &["--force", "--copy-force"])
    {
        return Some(GitIntent::new(
            "destructive_branch_creation",
            "branch",
            "force-create/ref-overwrite",
            true,
            true,
        ));
    }
    if letters
        .iter()
        .any(|letter| BRANCH_DESTRUCTIVE_SHORTS.contains(letter))
        || has_long_option(arguments, &["--delete", "--move"])
    {
        return Some(GitIntent::new(
            "destructive_git",
            "branch",
            "delete/rename",
            false,
            true,
        ));
    }
    if letters
        .iter()
        .any(|letter| BRANCH_NORMAL_CREATE_SHORTS.contains(letter))
        || has_long_option(arguments, &["--copy"])
    {
        return Some(GitIntent::new(
            "branch_creation",
            "branch",
            "create/copy",
            true,
            false,
        ));
    }
    if has_long_option(arguments, &BRANCH_CREATION_MODIFIERS)
        && arguments.iter().any(|argument| !argument.starts_with('-'))
    {
        return Some(GitIntent::new(
            "branch_creation",
            "branch",
            "create with tracking/reflog",
            true,
            false,
        ));
    }
    if arguments
        .first()
        .is_some_and(|argument| !argument.starts_with('-'))
    {
        return Some(GitIntent::new(
            "branch_creation",
            "branch",
            "branch name",
            true,
            false,
        ));
    }
    Some(GitIntent::new(
        "destructive_git",
        "branch",
        "metadata mutation",
        false,
        true,
    ))
}

fn worktree_intent(arguments: &[String]) -> Option<GitIntent> {
    let mut index = 0;
    while index < arguments.len() && ["-v", "--verbose"].contains(&arguments[index].as_str()) {
        index += 1;
    }
    if index >= arguments.len() {
        return Some(GitIntent::new(
            "destructive_git",
            "worktree",
            "worktree mutation",
            false,
            true,
        ));
    }
    let subcommand = &arguments[index];
    let rest = &arguments[index + 1..];
    if subcommand == "list" {
        return None;
    }
    if subcommand == "lock" {
        let mut index = 0;
        let mut saw_path = false;
        while index < rest.len() {
            let argument = &rest[index];
            if argument == "--reason" {
                if index + 1 >= rest.len() || rest[index + 1].starts_with('-') {
                    return Some(GitIntent::new(
                        "destructive_git",
                        "worktree",
                        "worktree lock mutation",
                        false,
                        true,
                    ));
                }
                index += 2;
                continue;
            }
            if argument.starts_with("--reason=") {
                index += 1;
                continue;
            }
            if argument == "--" {
                if !saw_path && rest.len() - index - 1 == 1 {
                    return None;
                }
                return Some(GitIntent::new(
                    "destructive_git",
                    "worktree",
                    "worktree lock mutation",
                    false,
                    true,
                ));
            }
            if argument.starts_with('-') || saw_path {
                return Some(GitIntent::new(
                    "destructive_git",
                    "worktree",
                    "worktree lock mutation",
                    false,
                    true,
                ));
            }
            saw_path = true;
            index += 1;
        }
        if saw_path {
            return None;
        }
    }
    if subcommand == "unlock"
        && !rest.is_empty()
        && rest.iter().all(|argument| !argument.starts_with('-'))
    {
        return None;
    }
    if subcommand == "add" {
        let force_overwrite = short_option_letters(rest)
            .iter()
            .any(|letter| ['B', 'f'].contains(letter))
            || has_long_option(rest, &["--force"]);
        return Some(if force_overwrite {
            GitIntent::new(
                "destructive_worktree_creation",
                "worktree",
                "worktree force-add",
                true,
                true,
            )
        } else {
            GitIntent::new("worktree_creation", "worktree", "worktree add", true, false)
        });
    }
    Some(GitIntent::new(
        "destructive_git",
        "worktree",
        &format!("worktree {subcommand}"),
        false,
        true,
    ))
}

fn git_intent(command: &GitCommand) -> Option<GitIntent> {
    let subcommand = command.tokens.first().map(String::as_str)?;
    let arguments = &command.tokens[1..];
    match subcommand {
        "restore" => Some(GitIntent::new(
            "destructive_git",
            subcommand,
            "git restore",
            false,
            true,
        )),
        "reset" => Some(GitIntent::new(
            "destructive_git",
            subcommand,
            "git reset",
            false,
            true,
        )),
        "clean" => {
            let letters = short_option_letters(arguments);
            let dry_run = letters.contains(&'n') || has_long_option(arguments, &["--dry-run"]);
            let forced = letters.contains(&'f') || has_long_option(arguments, &["--force"]);
            if forced && !dry_run {
                Some(GitIntent::new(
                    "destructive_git",
                    "clean",
                    "git clean force",
                    false,
                    true,
                ))
            } else {
                None
            }
        }
        "checkout" | "switch" => {
            let letters = short_option_letters(arguments);
            if has_long_option(arguments, &["--help"]) || letters.contains(&'h') {
                return None;
            }
            let force_create = (subcommand == "switch" && letters.contains(&'C'))
                || (subcommand == "checkout" && letters.contains(&'B'))
                || has_long_option(arguments, &["--force-create"]);
            let normal_create = (subcommand == "switch" && letters.contains(&'c'))
                || (subcommand == "checkout" && letters.contains(&'b'))
                || has_long_option(arguments, &["--create", "--orphan"]);
            if force_create {
                Some(GitIntent::new(
                    "destructive_branch_creation",
                    subcommand,
                    "force-create/ref-overwrite",
                    true,
                    true,
                ))
            } else if normal_create {
                Some(GitIntent::new(
                    "branch_creation",
                    subcommand,
                    "create/orphan",
                    true,
                    false,
                ))
            } else {
                Some(GitIntent::new(
                    "destructive_git",
                    subcommand,
                    "current-checkout mutation",
                    false,
                    true,
                ))
            }
        }
        "stash" => {
            if arguments
                .first()
                .is_some_and(|argument| ["list", "show"].contains(&argument.as_str()))
            {
                None
            } else {
                Some(GitIntent::new(
                    "destructive_git",
                    "stash",
                    "stash mutation",
                    false,
                    true,
                ))
            }
        }
        "branch" => branch_intent(arguments),
        "worktree" => worktree_intent(arguments),
        _ => None,
    }
}

fn creation_authorized(command: &GitCommand) -> bool {
    let values = &command.assignments;
    values
        .get(BRANCH_AUTHORITY_ENV)
        .is_some_and(|value| ALLOWED_BRANCH_AUTHORITIES.contains(&python_strip(value)))
        && values
            .get(BRANCH_REASON_ENV)
            .is_some_and(|value| !python_strip(value).is_empty())
}

fn destructive_authorized(command: &GitCommand) -> bool {
    let values = &command.assignments;
    values
        .get(DESTRUCTIVE_AUTHORITY_ENV)
        .is_some_and(|value| python_strip(value) == DESTRUCTIVE_AUTHORITY)
        && values
            .get(DESTRUCTIVE_REASON_ENV)
            .is_some_and(|value| !python_strip(value).is_empty())
}

fn intent_authorized(command: &GitCommand, intent: &GitIntent) -> bool {
    (!intent.requires_creation || creation_authorized(command))
        && (!intent.requires_destructive || destructive_authorized(command))
}

fn opaque_protected_intent(command: &str) -> Option<GitIntent> {
    let tokens = shell_tokens(command);
    for (git_index, token) in tokens.iter().enumerate() {
        if command_basename(token) != "git" {
            continue;
        }
        let mut index = git_index + 1;
        while index < tokens.len() {
            let option = &tokens[index];
            if OPAQUE_GIT_OPTIONS_WITH_VALUES.contains(&option.as_str()) {
                index += 2;
                continue;
            }
            if option.starts_with('-') {
                index += 1;
                continue;
            }
            if PROTECTED_GIT_SUBCOMMANDS.contains(&option.as_str()) {
                return Some(GitIntent::new(
                    "destructive_git",
                    "opaque",
                    "opaque protected Git mutation",
                    false,
                    true,
                ));
            }
            break;
        }
    }
    None
}

/// Return the first unauthorized raw Git intent.
pub fn first_block(command: &str) -> Option<GitIntent> {
    let mut work = vec![FirstBlockWorkItem::Command(command.to_owned())];
    while let Some(item) = work.pop() {
        match item {
            FirstBlockWorkItem::Command(command) => {
                let (mut complete, uncertain) = backtick_command_substitutions(&command);
                complete.extend(uncertain);
                work.push(FirstBlockWorkItem::Direct(command));
                for substitution in complete.into_iter().rev() {
                    work.push(FirstBlockWorkItem::Command(substitution));
                }
            }
            FirstBlockWorkItem::Direct(command) => {
                let tokens = shell_tokens(&command);
                if tokens.is_empty() {
                    if let Some(intent) = opaque_protected_intent(&command) {
                        return Some(intent);
                    }
                    continue;
                }
                let segments = command_segments(tokens).into_iter();
                work.push(FirstBlockWorkItem::Segments(segments));
            }
            FirstBlockWorkItem::Segments(mut segments) => {
                let Some(segment) = segments.next() else {
                    continue;
                };
                if !segments.as_slice().is_empty() {
                    work.push(FirstBlockWorkItem::Segments(segments));
                }
                if segment
                    .first()
                    .is_some_and(|token| command_basename(token) == "eval")
                    && eval_join_preserves_shell_tokens(&segment[1..])
                {
                    let words = segment.into_iter().skip(1).collect::<VecDeque<_>>();
                    if !words.is_empty() {
                        work.push(FirstBlockWorkItem::EvalWords(words));
                    }
                    continue;
                }
                let script = wrapper_script(&segment);
                if !script.is_empty() {
                    drop(segment);
                    work.push(FirstBlockWorkItem::Command(script));
                    continue;
                }
                if let Some(git_command) = normalized_git_command(&segment) {
                    if let Some(intent) = git_intent(&git_command) {
                        if !intent_authorized(&git_command, &intent) {
                            return Some(intent);
                        }
                    } else if git_command
                        .tokens
                        .first()
                        .is_some_and(|token| token.starts_with('-'))
                    {
                        if let Some(intent) = opaque_protected_intent(&segment.join(" ")) {
                            return Some(intent);
                        }
                    }
                    continue;
                }
                if let Some(intent) = opaque_protected_intent(&segment.join(" ")) {
                    return Some(intent);
                }
            }
            FirstBlockWorkItem::EvalWords(mut words) => {
                while words
                    .front()
                    .is_some_and(|token| command_basename(token) == "eval")
                {
                    words.pop_front();
                }
                if !words.is_empty() {
                    let tokens = words.into_iter().collect();
                    let segments = command_segments(tokens).into_iter();
                    work.push(FirstBlockWorkItem::Segments(segments));
                }
            }
        }
    }
    None
}

/// Return a redacted block payload; command text never crosses the leaf boundary.
pub fn branch_block_payload(command: &str, intent: &GitIntent) -> Value {
    let mut markers = Vec::new();
    if intent.requires_destructive {
        markers.push("DESTRUCTIVE_GIT_GUARD=block");
    }
    if intent.requires_creation {
        markers.push("BRANCH_WORKTREE_CREATION_GUARD=block");
    }
    let mut requirements = Vec::new();
    if intent.requires_creation {
        requirements.push(format!(
            "same-segment {}=user_request|agent_canon_workflow and nonempty {}",
            BRANCH_AUTHORITY_ENV, BRANCH_REASON_ENV
        ));
    }
    if intent.requires_destructive {
        requirements.push(format!(
            "same-segment {}=explicit_user_approval and nonempty {}",
            DESTRUCTIVE_AUTHORITY_ENV, DESTRUCTIVE_REASON_ENV
        ));
    }
    let next_action = if intent.requires_creation && intent.requires_destructive {
        "request_explicit_user_approval_then_rerun_same_command_with_inline_git_authority_and_reason"
    } else if intent.requires_creation {
        "request_branch_or_worktree_creation_authority_then_rerun_same_command_with_inline_git_authority_and_reason"
    } else {
        "inspect_status_preserve_other_task_changes_or_record_explicit_user_approval"
    };
    json!({
        "decision": "block",
        "reason": format!(
            "{}: protected shared-checkout Git intent lacks required authority. operation={}:{}; requires={}",
            markers.join("; "),
            intent.kind,
            intent.subcommand,
            requirements.join("; "),
        ),
        "next_action": next_action,
        "remediation": [
            "Inspect status and preserve changes owned by the user or another concurrent chat.",
            "Continue only on proven task-owned exact paths; that evidence bounds an approval request and never bypasses explicit destructive approval.",
            "If the user explicitly approves the protected action, place every required authority and reason assignment in the same shell segment immediately before Git.",
        ],
        "operation": format!("{}:{}", intent.kind, intent.subcommand),
        "command_sha256": command_sha256(command),
    })
}
