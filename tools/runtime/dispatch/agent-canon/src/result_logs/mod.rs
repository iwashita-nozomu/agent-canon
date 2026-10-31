// @dependency-start
// contract implementation
// responsibility Preserves JSONL result conversion and HLO summary behavior in native Rust.
// upstream design ../../../../../../documents/experiments/result-log-retention-and-visualization.md owns summary and report policy
// downstream implementation ../../../../../../tests/tools/test_result_log_tools.py exercises both public commands
// @dependency-end

use agent_canon::python_json::{parse_json as parse_json_line, JsonObject, JsonString, JsonValue};
use rustpython_ast::bigint::BigInt;
use std::fmt;
use std::fs;
use std::io::{self, BufRead, BufReader};
use std::path::PathBuf;

const PREFERRED_KEYS: &[&str] = &[
    "case",
    "source_file",
    "test",
    "func",
    "event",
    "iter",
    "step",
    "num_iter",
];

#[derive(Default)]
struct Counter(Vec<(JsonString, usize)>);

impl Counter {
    fn add(&mut self, key: &JsonString, amount: usize) {
        if let Some(position) = self.0.iter().position(|(existing, _)| existing == key) {
            self.0[position].1 += amount;
        } else {
            self.0.push((key.clone(), amount));
        }
    }

    fn pairs(&self, limit: Option<&BigInt>) -> Vec<(JsonString, usize)> {
        if limit.is_some_and(|limit| limit <= &BigInt::from(0)) {
            return Vec::new();
        }
        let mut sorted = self.0.clone();
        // Stable sorting preserves Counter.most_common's first-seen tie order.
        sorted.sort_by_key(|entry| std::cmp::Reverse(entry.1));
        if let Some(limit) = limit {
            let entry_count = BigInt::from(sorted.len());
            if limit < &entry_count {
                let limit = limit
                    .to_string()
                    .parse::<usize>()
                    .expect("positive limit below entry count fits usize");
                sorted.truncate(limit);
            }
        }
        sorted
    }
}

pub fn run_summary(args: &[String]) -> i32 {
    let parsed = match SummaryArgs::parse(args) {
        Ok(Some(parsed)) => parsed,
        Ok(None) => {
            print_summary_help();
            return 0;
        }
        Err(message) => {
            eprintln!("agent-canon summarize-hlo-jsonl: {message}");
            eprintln!(
                "usage: agent-canon summarize-hlo-jsonl [--top TOP] [--only-case ONLY_CASE] jsonl"
            );
            return 2;
        }
    };

    let input = match fs::File::open(&parsed.path) {
        Ok(input) => input,
        Err(error) => {
            eprintln!(
                "agent-canon summarize-hlo-jsonl: read {}: {error}",
                parsed.path.display()
            );
            return 1;
        }
    };

    let mut total_records = 0usize;
    let mut total_selected = 0usize;
    let mut tags = Counter::default();
    let mut dialects = Counter::default();
    let mut ops_total = Counter::default();
    let mut hlo_lines_total = 0usize;
    let mut hlo_chars_total = 0usize;

    let mut line_reader = UniversalLineReader::new(BufReader::new(input));
    let mut line_number = 0;
    loop {
        let bytes = match line_reader.next_line() {
            Ok(Some(bytes)) => bytes,
            Ok(None) => break,
            Err(error) => {
                eprintln!(
                    "agent-canon summarize-hlo-jsonl: read {}: {error}",
                    parsed.path.display()
                );
                return 1;
            }
        };
        line_number += 1;
        let line = match String::from_utf8(bytes) {
            Ok(line) => line,
            Err(error) => {
                eprintln!(
                    "agent-canon summarize-hlo-jsonl: decode {} at line {}: {error}",
                    parsed.path.display(),
                    line_number
                );
                return 1;
            }
        };
        let stripped = python_trim(&line);
        if stripped.is_empty() {
            continue;
        }
        let value = match parse_json_line(stripped) {
            Ok(value) => value,
            Err(error) => {
                eprintln!(
                    "agent-canon summarize-hlo-jsonl: invalid JSON in {} at line {}: {error}",
                    parsed.path.display(),
                    line_number
                );
                return 1;
            }
        };
        let JsonValue::Object(record) = value else {
            continue;
        };
        total_records += 1;

        if !parsed.only_case.is_empty()
            && !record_key(&record, "case").equals_text(&parsed.only_case)
        {
            continue;
        }
        total_selected += 1;

        let tag = record_key(&record, "tag");
        if !tag.is_empty() {
            tags.add(&tag, 1);
        }
        let dialect = record_key(&record, "dialect");
        if !dialect.is_empty() {
            dialects.add(&dialect, 1);
        }
        if let Some(JsonValue::String(hlo)) = object_get(&record, "hlo") {
            let lines = python_splitlines(&hlo.0);
            for line_range in &lines {
                let line = &hlo.0[line_range.clone()];
                let trimmed_range = python_trim_codepoints(line);
                let trimmed = &line[trimmed_range];
                if trimmed.is_empty() || trimmed.starts_with(&[u32::from(b'/'), u32::from(b'/')]) {
                    continue;
                }
                let Some(equals) = trimmed
                    .iter()
                    .position(|codepoint| *codepoint == u32::from(b'='))
                else {
                    continue;
                };
                let rhs = &trimmed[equals + 1..];
                let rhs = &rhs[python_trim_codepoints(rhs)];
                let op_end = rhs
                    .iter()
                    .position(|codepoint| *codepoint == u32::from(b'('))
                    .unwrap_or(rhs.len());
                let op = &rhs[..op_end];
                let op = &op[python_trim_codepoints(op)];
                if !op.is_empty() {
                    ops_total.add(&JsonString(op.to_vec()), 1);
                }
            }
            hlo_lines_total += lines
                .into_iter()
                .filter(|range| !python_trim_codepoints(&hlo.0[range.clone()]).is_empty())
                .count();
            hlo_chars_total += hlo.0.len();
        }
    }

    let top_ops = ops_total.pairs(Some(&parsed.top));
    let summary_parts = (
        json_string(&JsonString::from_text(&parsed.path_text)),
        json_string(&JsonString::from_text(&parsed.only_case)),
        counter_json(&tags.pairs(None)),
        counter_json(&dialects.pairs(None)),
        counter_json(&top_ops),
    );
    let (jsonl, only_case, tags, dialects, top_ops) = match summary_parts {
        (Ok(jsonl), Ok(only_case), Ok(tags), Ok(dialects), Ok(top_ops)) => {
            (jsonl, only_case, tags, dialects, top_ops)
        }
        _ => {
            eprintln!("agent-canon summarize-hlo-jsonl: output contains a lone surrogate");
            return 1;
        }
    };
    let summary = format!(
        "{{\"jsonl\": {}, \"total_records\": {}, \"total_selected\": {}, \"filter\": {{\"only_case\": {}}}, \"tags\": {}, \"dialects\": {}, \"hlo_text\": {{\"total_lines\": {}, \"total_chars\": {}}}, \"top_ops\": {}}}",
        jsonl,
        total_records,
        total_selected,
        only_case,
        tags,
        dialects,
        hlo_lines_total,
        hlo_chars_total,
        top_ops,
    );
    println!("{summary}");
    0
}

pub fn run_jsonl_to_md(args: &[String]) -> i32 {
    let parsed = match MarkdownArgs::parse(args) {
        Ok(Some(parsed)) => parsed,
        Ok(None) => {
            print_markdown_help();
            return 0;
        }
        Err(message) => {
            eprintln!("agent-canon jsonl-to-md: {message}");
            eprintln!("usage: agent-canon jsonl-to-md input output");
            return 2;
        }
    };

    if !parsed.input.is_file() {
        println!("Input not found: {}", parsed.input_text);
        return 2;
    }
    let input = match fs::read_to_string(&parsed.input) {
        Ok(input) => input,
        Err(error) => {
            eprintln!(
                "agent-canon jsonl-to-md: read {}: {error}",
                parsed.input.display()
            );
            return 1;
        }
    };

    let mut records = Vec::new();
    for line in universal_lines(&input) {
        let stripped = python_trim(line);
        if stripped.is_empty() {
            continue;
        }
        if let Ok(JsonValue::Object(record)) = parse_json_line(stripped) {
            records.push(record);
        }
    }

    let report = match render_markdown(&parsed.input_text, &records) {
        Ok(report) => report,
        Err(error) => {
            eprintln!("agent-canon jsonl-to-md: {error}");
            return 1;
        }
    };
    if let Some(parent) = parsed
        .output
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        if let Err(error) = fs::create_dir_all(parent) {
            eprintln!(
                "agent-canon jsonl-to-md: create {}: {error}",
                parent.display()
            );
            return 1;
        }
    }
    if let Err(error) = fs::write(&parsed.output, report.as_bytes()) {
        eprintln!(
            "agent-canon jsonl-to-md: write {}: {error}",
            parsed.output.display()
        );
        return 1;
    }
    println!("written: {}", parsed.output_text);
    0
}

struct SummaryArgs {
    path: PathBuf,
    path_text: String,
    top: BigInt,
    only_case: String,
}

impl SummaryArgs {
    fn parse(args: &[String]) -> Result<Option<Self>, String> {
        let mut path: Option<String> = None;
        let mut top = BigInt::from(30);
        let mut only_case = "hlo".to_owned();
        let mut index = 0;
        let mut positional_only = false;
        while index < args.len() {
            let raw = &args[index];
            if !positional_only && matches!(raw.as_str(), "-h" | "--help") {
                return Ok(None);
            }
            if !positional_only && raw == "--" {
                positional_only = true;
                index += 1;
                continue;
            }
            if !positional_only && (raw == "--top" || raw.starts_with("--top=")) {
                let value: &str = if raw == "--top" {
                    index += 1;
                    args.get(index)
                        .map(String::as_str)
                        .ok_or_else(|| "argument --top: expected one argument".to_owned())?
                } else {
                    raw.split_once('=').expect("starts with --top=").1
                };
                top = crate::python_cli_integer::parse(value)
                    .ok_or_else(|| format!("argument --top: invalid int value: '{value}'"))?;
                index += 1;
                continue;
            }
            if !positional_only && (raw == "--only-case" || raw.starts_with("--only-case=")) {
                let value: &str = if raw == "--only-case" {
                    index += 1;
                    args.get(index)
                        .map(String::as_str)
                        .ok_or_else(|| "argument --only-case: expected one argument".to_owned())?
                } else {
                    raw.split_once('=').expect("starts with --only-case=").1
                };
                only_case = value.to_owned();
                index += 1;
                continue;
            }
            if !positional_only && raw.starts_with('-') {
                return Err(format!("unrecognized argument: {raw}"));
            }
            if path.replace(raw.clone()).is_some() {
                return Err(format!(
                    "unrecognized arguments: {}",
                    args[index..].join(" ")
                ));
            }
            index += 1;
        }
        let path_text =
            path.ok_or_else(|| "the following arguments are required: jsonl".to_owned())?;
        let path = PathBuf::from(&path_text);
        Ok(Some(Self {
            path,
            path_text: python_path_text(&path_text),
            top,
            only_case,
        }))
    }
}

struct MarkdownArgs {
    input: PathBuf,
    input_text: String,
    output: PathBuf,
    output_text: String,
}

impl MarkdownArgs {
    fn parse(args: &[String]) -> Result<Option<Self>, String> {
        let mut positional = Vec::new();
        let mut positional_only = false;
        for raw in args {
            if !positional_only && matches!(raw.as_str(), "-h" | "--help") {
                return Ok(None);
            }
            if !positional_only && raw == "--" {
                positional_only = true;
                continue;
            }
            if !positional_only && raw.starts_with('-') {
                return Err(format!("unrecognized argument: {raw}"));
            }
            positional.push(raw.clone());
        }
        if positional.len() < 2 {
            return Err(if positional.is_empty() {
                "the following arguments are required: input, output".to_owned()
            } else {
                "the following arguments are required: output".to_owned()
            });
        }
        if positional.len() > 2 {
            return Err(format!(
                "unrecognized arguments: {}",
                positional[2..].join(" ")
            ));
        }
        let input_text = python_path_text(&positional[0]);
        let output_text = python_path_text(&positional[1]);
        Ok(Some(Self {
            input: PathBuf::from(&positional[0]),
            input_text,
            output: PathBuf::from(&positional[1]),
            output_text,
        }))
    }
}

fn object_get<'a>(record: &'a JsonObject, key: &str) -> Option<&'a JsonValue> {
    record
        .0
        .iter()
        .find_map(|(candidate, value)| candidate.equals_text(key).then_some(value))
}

fn record_key(record: &JsonObject, key: &str) -> JsonString {
    match object_get(record, key) {
        None | Some(JsonValue::Null) => JsonString::default(),
        Some(value) => python_string(value),
    }
}

fn python_string(value: &JsonValue) -> JsonString {
    match value {
        JsonValue::Null => JsonString::from_text("None"),
        JsonValue::Bool(value) => JsonString::from_text(if *value { "True" } else { "False" }),
        JsonValue::Number(value) => JsonString::from_text(&value.python_string()),
        JsonValue::String(value) => value.clone(),
        JsonValue::Array(_) | JsonValue::Object(_) => python_repr(value),
    }
}

fn python_repr(value: &JsonValue) -> JsonString {
    enum Action<'a> {
        Value(&'a JsonValue),
        String(&'a JsonString),
        Text(&'static str),
    }

    let mut output = JsonString::default();
    let mut actions = vec![Action::Value(value)];
    while let Some(action) = actions.pop() {
        match action {
            Action::Text(text) => output.push_text(text),
            Action::String(value) => output.0.extend(python_string_repr(value).0),
            Action::Value(value) => match value {
                JsonValue::Null => output.push_text("None"),
                JsonValue::Bool(value) => output.push_text(if *value { "True" } else { "False" }),
                JsonValue::Number(value) => output.push_text(&value.python_string()),
                JsonValue::String(value) => output.0.extend(python_string_repr(value).0),
                JsonValue::Array(values) => {
                    output.push_text("[");
                    actions.push(Action::Text("]"));
                    for index in (0..values.0.len()).rev() {
                        actions.push(Action::Value(&values.0[index]));
                        if index > 0 {
                            actions.push(Action::Text(", "));
                        }
                    }
                }
                JsonValue::Object(values) => {
                    output.push_text("{");
                    actions.push(Action::Text("}"));
                    for index in (0..values.0.len()).rev() {
                        let (key, value) = &values.0[index];
                        actions.push(Action::Value(value));
                        actions.push(Action::Text(": "));
                        actions.push(Action::String(key));
                        if index > 0 {
                            actions.push(Action::Text(", "));
                        }
                    }
                }
            },
        }
    }
    output
}

fn python_string_repr(value: &JsonString) -> JsonString {
    let Some(text) = value.to_text() else {
        return python_string_repr_with_surrogates(value);
    };
    JsonString::from_text(&rustpython_ast::Constant::Str(text).to_string())
}

fn python_string_repr_with_surrogates(value: &JsonString) -> JsonString {
    let scalar_projection: String = value
        .0
        .iter()
        .filter_map(|codepoint| char::from_u32(*codepoint))
        .collect();
    let probe = rustpython_ast::Constant::Str(scalar_projection).to_string();
    let quote = probe
        .chars()
        .next()
        .expect("RustPython string repr has quotes");
    let mut rendered = String::with_capacity(probe.len() + value.0.len() * 6);
    rendered.push(quote);

    let mut segment = String::new();
    for &codepoint in &value.0 {
        if let Some(character) = char::from_u32(codepoint) {
            segment.push(character);
        } else {
            rendered.push_str(&rustpython_string_repr_segment(&segment, quote));
            segment.clear();
            use fmt::Write as _;
            let _ = write!(rendered, "\\u{codepoint:04x}");
        }
    }
    rendered.push_str(&rustpython_string_repr_segment(&segment, quote));
    rendered.push(quote);
    JsonString::from_text(&rendered)
}

fn rustpython_string_repr_segment(segment: &str, quote: char) -> String {
    if segment.is_empty() {
        return String::new();
    }
    let helper_quote = if quote == '\'' { '"' } else { '\'' };
    let mut with_helper_quote = segment.to_owned();
    with_helper_quote.push(helper_quote);
    let repr = rustpython_ast::Constant::Str(with_helper_quote).to_string();
    let body = repr
        .strip_prefix(quote)
        .and_then(|repr| repr.strip_suffix(quote))
        .expect("RustPython repr quote matches the whole string quote");
    body.strip_suffix(helper_quote)
        .expect("the helper quote remains a trailing literal character")
        .to_owned()
}

fn json_string(value: &JsonString) -> Result<String, String> {
    if value.contains_surrogate() {
        return Err("JSON output contains a lone surrogate".to_owned());
    }
    let value = value
        .to_text()
        .expect("non-surrogate code points form Rust text");
    serde_json::to_string(&value).map_err(|error| error.to_string())
}

fn json_value(value: &JsonValue) -> Result<String, String> {
    enum Action<'a> {
        Value(&'a JsonValue),
        String(&'a JsonString),
        Text(&'static str),
    }

    let mut output = String::new();
    let mut actions = vec![Action::Value(value)];
    while let Some(action) = actions.pop() {
        match action {
            Action::Text(text) => output.push_str(text),
            Action::String(value) => output.push_str(&json_string(value)?),
            Action::Value(value) => match value {
                JsonValue::Null => output.push_str("null"),
                JsonValue::Bool(value) => output.push_str(if *value { "true" } else { "false" }),
                JsonValue::Number(value) => output.push_str(&value.json_string()),
                JsonValue::String(value) => output.push_str(&json_string(value)?),
                JsonValue::Array(values) => {
                    output.push('[');
                    actions.push(Action::Text("]"));
                    for index in (0..values.0.len()).rev() {
                        actions.push(Action::Value(&values.0[index]));
                        if index > 0 {
                            actions.push(Action::Text(", "));
                        }
                    }
                }
                JsonValue::Object(values) => {
                    output.push('{');
                    actions.push(Action::Text("}"));
                    for index in (0..values.0.len()).rev() {
                        let (key, value) = &values.0[index];
                        actions.push(Action::Value(value));
                        actions.push(Action::Text(": "));
                        actions.push(Action::String(key));
                        if index > 0 {
                            actions.push(Action::Text(", "));
                        }
                    }
                }
            },
        }
    }
    Ok(output)
}

fn counter_json(counter: &[(JsonString, usize)]) -> Result<String, String> {
    let mut rendered = Vec::with_capacity(counter.len());
    for (key, count) in counter {
        rendered.push(format!("[{}, {}]", json_string(key)?, count));
    }
    Ok(format!("[{}]", rendered.join(", ")))
}

fn format_value(value: &JsonValue) -> Result<String, String> {
    let rendered = match value {
        JsonValue::Array(_) | JsonValue::Object(_) => json_value(value)?,
        _ => python_string(value)
            .to_text()
            .ok_or_else(|| "Markdown output contains a lone surrogate".to_owned())?,
    };
    Ok(rendered.replace('|', "\\|").replace('\n', "<br>"))
}

fn render_markdown(input_path: &str, records: &[JsonObject]) -> Result<String, String> {
    let mut lines = vec![
        "# JSONL Report".to_owned(),
        String::new(),
        format!("- input: `{input_path}`"),
        format!("- records: {}", records.len()),
        String::new(),
    ];
    for (index, record) in records.iter().enumerate() {
        let title = object_get(record, "case")
            .map(python_string)
            .unwrap_or_else(|| JsonString::from_text(&format!("record-{}", index + 1)))
            .to_text()
            .ok_or_else(|| "Markdown output contains a lone surrogate".to_owned())?;
        lines.extend([
            format!("## {title}"),
            String::new(),
            "| key | value |".to_owned(),
            "| --- | --- |".to_owned(),
        ]);
        for key in PREFERRED_KEYS {
            if let Some(value) = object_get(record, key) {
                lines.push(format!("| {key} | {} |", format_value(value)?));
            }
        }
        let mut remaining: Vec<_> = record
            .0
            .iter()
            .filter(|(key, _)| {
                !PREFERRED_KEYS
                    .iter()
                    .any(|preferred| key.equals_text(preferred))
            })
            .collect();
        remaining.sort_by(|left, right| left.0.cmp(&right.0));
        for (key, value) in remaining {
            let key = key
                .to_text()
                .ok_or_else(|| "Markdown output contains a lone surrogate in a key".to_owned())?;
            lines.push(format!("| {key} | {} |", format_value(value)?));
        }
        lines.push(String::new());
    }
    Ok(lines.join("\n"))
}

fn universal_lines(text: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut chars = text.char_indices().peekable();
    while let Some((index, character)) = chars.next() {
        if character == '\n' || character == '\r' {
            lines.push(&text[start..index]);
            if character == '\r' {
                if let Some((next_index, '\n')) = chars.peek().copied() {
                    chars.next();
                    start = next_index + '\n'.len_utf8();
                    continue;
                }
            }
            start = index + character.len_utf8();
        }
    }
    if start < text.len() {
        lines.push(&text[start..]);
    }
    lines
}

struct UniversalLineReader<R> {
    reader: R,
}

impl<R: BufRead> UniversalLineReader<R> {
    fn new(reader: R) -> Self {
        Self { reader }
    }

    fn next_line(&mut self) -> io::Result<Option<Vec<u8>>> {
        let mut line = Vec::new();
        loop {
            let (consumed, delimiter, swallow_lf) = {
                let buffer = self.reader.fill_buf()?;
                if buffer.is_empty() {
                    return if line.is_empty() {
                        Ok(None)
                    } else {
                        Ok(Some(line))
                    };
                }
                if let Some(index) = buffer
                    .iter()
                    .position(|byte| *byte == b'\r' || *byte == b'\n')
                {
                    line.extend_from_slice(&buffer[..index]);
                    let delimiter = buffer[index];
                    let mut consumed = index + 1;
                    let swallow_lf = if delimiter == b'\r' {
                        if buffer.get(consumed) == Some(&b'\n') {
                            consumed += 1;
                            false
                        } else {
                            consumed == buffer.len()
                        }
                    } else {
                        false
                    };
                    (consumed, Some(delimiter), swallow_lf)
                } else {
                    let consumed = buffer.len();
                    line.extend_from_slice(buffer);
                    (consumed, None, false)
                }
            };
            self.reader.consume(consumed);
            let Some(delimiter) = delimiter else {
                continue;
            };
            if delimiter == b'\r' && swallow_lf && self.reader.fill_buf()?.first() == Some(&b'\n') {
                self.reader.consume(1);
            }
            return Ok(Some(line));
        }
    }
}

fn python_splitlines(text: &[u32]) -> Vec<std::ops::Range<usize>> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut index = 0;
    while index < text.len() {
        let codepoint = text[index];
        if is_python_line_separator(codepoint) {
            lines.push(start..index);
            if codepoint == u32::from(b'\r') && text.get(index + 1) == Some(&u32::from(b'\n')) {
                index += 1;
            }
            start = index + 1;
        }
        index += 1;
    }
    if start < text.len() {
        lines.push(start..text.len());
    }
    lines
}

fn is_python_line_separator(codepoint: u32) -> bool {
    matches!(
        codepoint,
        0x000a | 0x000d | 0x000b | 0x000c | 0x001c..=0x001e | 0x0085 | 0x2028 | 0x2029
    )
}

fn python_trim_codepoints(value: &[u32]) -> std::ops::Range<usize> {
    let is_space = |codepoint: &u32| {
        char::from_u32(*codepoint).is_some_and(char::is_whitespace)
            || matches!(*codepoint, 0x001c..=0x001f)
    };
    let start = value.iter().position(|codepoint| !is_space(codepoint));
    let end = value.iter().rposition(|codepoint| !is_space(codepoint));
    match (start, end) {
        (Some(start), Some(end)) => start..end + 1,
        _ => 0..0,
    }
}

fn is_python_whitespace(character: char) -> bool {
    character.is_whitespace() || matches!(character, '\u{001c}'..='\u{001f}')
}

fn python_trim(value: &str) -> &str {
    value.trim_matches(is_python_whitespace)
}

fn python_path_text(raw: &str) -> String {
    let absolute = raw.starts_with('/');
    let components: Vec<_> = raw
        .split('/')
        .filter(|component| !component.is_empty() && *component != ".")
        .collect();
    if components.is_empty() {
        return if absolute {
            "/".to_owned()
        } else {
            ".".to_owned()
        };
    }
    let joined = components.join("/");
    if absolute {
        format!("/{joined}")
    } else {
        joined
    }
}

fn print_summary_help() {
    println!("usage: agent-canon summarize-hlo-jsonl [--top TOP] [--only-case ONLY_CASE] jsonl");
    println!();
    println!("Summarize HLO JSONL.");
    println!();
    println!("positional arguments:");
    println!("  jsonl                 Path to JSONL produced by an HLO dumping workflow.");
    println!();
    println!("options:");
    println!("  -h, --help            show this help message and exit");
    println!("  --top TOP             Show top-k ops. (default: 30)");
    println!("  --only-case ONLY_CASE Filter by record['case'] (default: hlo). Use empty string to disable.");
}

fn print_markdown_help() {
    println!("usage: agent-canon jsonl-to-md input output");
    println!();
    println!("Convert JSONL records into a compact Markdown report.");
    println!();
    println!("positional arguments:");
    println!("  input       Input JSONL file.");
    println!("  output      Output Markdown file.");
    println!();
    println!("options:");
    println!("  -h, --help  show this help message and exit");
}
