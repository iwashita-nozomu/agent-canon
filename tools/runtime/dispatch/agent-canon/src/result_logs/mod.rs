// @dependency-start
// contract implementation
// responsibility Preserves JSONL result conversion and HLO summary behavior in native Rust.
// upstream design ../../../../../../documents/experiments/result-log-retention-and-visualization.md owns summary and report policy
// downstream implementation ../../../../../../../tests/tools/test_result_log_tools.py exercises both public commands
// @dependency-end

use std::fmt;
use std::fs;
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

#[derive(Debug, Clone)]
enum JsonValue {
    Null,
    Bool(bool),
    Integer(String),
    Float(f64),
    String(String),
    Array(Vec<JsonValue>),
    Object(Vec<(String, JsonValue)>),
}

struct JsonParser<'a> {
    input: &'a str,
    bytes: &'a [u8],
    index: usize,
}

impl<'a> JsonParser<'a> {
    fn new(input: &'a str) -> Self {
        Self {
            input,
            bytes: input.as_bytes(),
            index: 0,
        }
    }

    fn parse(mut self) -> Result<JsonValue, String> {
        self.skip_whitespace();
        let value = self.parse_value()?;
        self.skip_whitespace();
        if self.index != self.bytes.len() {
            return Err(self.error("unexpected trailing characters"));
        }
        Ok(value)
    }

    fn parse_value(&mut self) -> Result<JsonValue, String> {
        match self.peek() {
            Some(b'{') => self.parse_object(),
            Some(b'[') => self.parse_array(),
            Some(b'"') => self.parse_string().map(JsonValue::String),
            Some(b't') => {
                self.consume_literal("true")?;
                Ok(JsonValue::Bool(true))
            }
            Some(b'f') => {
                self.consume_literal("false")?;
                Ok(JsonValue::Bool(false))
            }
            Some(b'n') => {
                self.consume_literal("null")?;
                Ok(JsonValue::Null)
            }
            Some(b'N') => {
                self.consume_literal("NaN")?;
                Ok(JsonValue::Float(f64::NAN))
            }
            Some(b'I') => {
                self.consume_literal("Infinity")?;
                Ok(JsonValue::Float(f64::INFINITY))
            }
            Some(b'-') if self.input[self.index..].starts_with("-Infinity") => {
                self.consume_literal("-Infinity")?;
                Ok(JsonValue::Float(f64::NEG_INFINITY))
            }
            Some(b'-' | b'0'..=b'9') => self.parse_number(),
            Some(_) => Err(self.error("expected a JSON value")),
            None => Err(self.error("unexpected end of input")),
        }
    }

    fn parse_object(&mut self) -> Result<JsonValue, String> {
        self.index += 1;
        self.skip_whitespace();
        let mut values: Vec<(String, JsonValue)> = Vec::new();
        if self.consume_if(b'}') {
            return Ok(JsonValue::Object(values));
        }
        loop {
            if self.peek() != Some(b'"') {
                return Err(self.error("object keys must be strings"));
            }
            let key = self.parse_string()?;
            self.skip_whitespace();
            if !self.consume_if(b':') {
                return Err(self.error("expected ':' after object key"));
            }
            self.skip_whitespace();
            let value = self.parse_value()?;
            if let Some(position) = values.iter().position(|(existing, _)| existing == &key) {
                values[position].1 = value;
            } else {
                values.push((key, value));
            }
            self.skip_whitespace();
            if self.consume_if(b'}') {
                return Ok(JsonValue::Object(values));
            }
            if !self.consume_if(b',') {
                return Err(self.error("expected ',' or '}' after object value"));
            }
            self.skip_whitespace();
        }
    }

    fn parse_array(&mut self) -> Result<JsonValue, String> {
        self.index += 1;
        self.skip_whitespace();
        let mut values = Vec::new();
        if self.consume_if(b']') {
            return Ok(JsonValue::Array(values));
        }
        loop {
            values.push(self.parse_value()?);
            self.skip_whitespace();
            if self.consume_if(b']') {
                return Ok(JsonValue::Array(values));
            }
            if !self.consume_if(b',') {
                return Err(self.error("expected ',' or ']' after array value"));
            }
            self.skip_whitespace();
        }
    }

    fn parse_string(&mut self) -> Result<String, String> {
        let start = self.index;
        self.index += 1;
        while self.index < self.bytes.len() {
            match self.bytes[self.index] {
                b'"' => {
                    self.index += 1;
                    return serde_json::from_str(&self.input[start..self.index])
                        .map_err(|error| format!("invalid JSON string: {error}"));
                }
                b'\\' => self.index = (self.index + 2).min(self.bytes.len()),
                byte if byte < 0x20 => {
                    return Err(self.error("unescaped control character in string"))
                }
                _ => self.index += 1,
            }
        }
        Err(self.error("unterminated string"))
    }

    fn parse_number(&mut self) -> Result<JsonValue, String> {
        let start = self.index;
        self.consume_if(b'-');
        match self.peek() {
            Some(b'0') => {
                self.index += 1;
                if matches!(self.peek(), Some(b'0'..=b'9')) {
                    return Err(self.error("leading zeros are not permitted in numbers"));
                }
            }
            Some(b'1'..=b'9') => {
                self.index += 1;
                while matches!(self.peek(), Some(b'0'..=b'9')) {
                    self.index += 1;
                }
            }
            _ => return Err(self.error("expected a digit in number")),
        }
        let mut is_float = false;
        if self.consume_if(b'.') {
            is_float = true;
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(self.error("expected a digit after decimal point"));
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.index += 1;
            }
        }
        if matches!(self.peek(), Some(b'e' | b'E')) {
            is_float = true;
            self.index += 1;
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.index += 1;
            }
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(self.error("expected a digit in exponent"));
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.index += 1;
            }
        }
        let raw = &self.input[start..self.index];
        if is_float {
            raw.parse::<f64>()
                .map(JsonValue::Float)
                .map_err(|error| format!("invalid JSON number '{raw}': {error}"))
        } else if raw == "-0" {
            Ok(JsonValue::Integer("0".to_owned()))
        } else {
            Ok(JsonValue::Integer(raw.to_owned()))
        }
    }

    fn consume_literal(&mut self, literal: &str) -> Result<(), String> {
        if self.input[self.index..].starts_with(literal) {
            self.index += literal.len();
            Ok(())
        } else {
            Err(self.error("invalid literal"))
        }
    }

    fn skip_whitespace(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\t' | b'\r' | b'\n')) {
            self.index += 1;
        }
    }

    fn consume_if(&mut self, expected: u8) -> bool {
        if self.peek() == Some(expected) {
            self.index += 1;
            true
        } else {
            false
        }
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.index).copied()
    }

    fn error(&self, message: &str) -> String {
        format!("{message} at column {}", self.index + 1)
    }
}

#[derive(Default)]
struct Counter(Vec<(String, usize)>);

impl Counter {
    fn add(&mut self, key: &str, amount: usize) {
        if let Some(position) = self
            .0
            .iter()
            .position(|(existing, _)| existing.as_str() == key)
        {
            self.0[position].1 += amount;
        } else {
            self.0.push((key.to_owned(), amount));
        }
    }

    fn pairs(&self, limit: Option<i64>) -> Vec<(String, usize)> {
        if limit.is_some_and(|limit| limit <= 0) {
            return Vec::new();
        }
        let mut sorted = self.0.clone();
        // Stable sorting preserves Counter.most_common's first-seen tie order.
        sorted.sort_by(|left, right| right.1.cmp(&left.1));
        if let Some(limit) = limit {
            sorted.truncate(limit as usize);
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

    let input = match fs::read_to_string(&parsed.path) {
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

    for (line_number, line) in universal_lines(&input).into_iter().enumerate() {
        let stripped = python_trim(line);
        if stripped.is_empty() {
            continue;
        }
        let value = match JsonParser::new(stripped).parse() {
            Ok(value) => value,
            Err(error) => {
                eprintln!(
                    "agent-canon summarize-hlo-jsonl: invalid JSON in {} at line {}: {error}",
                    parsed.path.display(),
                    line_number + 1
                );
                return 1;
            }
        };
        let JsonValue::Object(record) = value else {
            continue;
        };
        total_records += 1;

        if !parsed.only_case.is_empty() && record_key(&record, "case") != parsed.only_case {
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
            for line in python_splitlines(hlo) {
                let trimmed = python_trim(line);
                if trimmed.is_empty() || trimmed.starts_with("//") {
                    continue;
                }
                let Some((_, rhs)) = trimmed.split_once('=') else {
                    continue;
                };
                let rhs = python_trim(rhs);
                let op = python_trim(rhs.split_once('(').map_or(rhs, |(op, _)| op));
                if !op.is_empty() {
                    ops_total.add(op, 1);
                }
            }
            hlo_lines_total += python_splitlines(hlo)
                .into_iter()
                .filter(|line| !python_trim(line).is_empty())
                .count();
            hlo_chars_total += hlo.chars().count();
        }
    }

    let top_ops = ops_total.pairs(Some(parsed.top));
    let summary = format!(
        "{{\"jsonl\": {}, \"total_records\": {}, \"total_selected\": {}, \"filter\": {{\"only_case\": {}}}, \"tags\": {}, \"dialects\": {}, \"hlo_text\": {{\"total_lines\": {}, \"total_chars\": {}}}, \"top_ops\": {}}}",
        json_string(&parsed.path_text),
        total_records,
        json_string(&parsed.only_case),
        counter_json(&tags.pairs(None)),
        counter_json(&dialects.pairs(None)),
        hlo_lines_total,
        hlo_chars_total,
        counter_json(&top_ops),
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
        if let Ok(JsonValue::Object(record)) = JsonParser::new(stripped).parse() {
            records.push(record);
        }
    }

    let report = render_markdown(&parsed.input_text, &records);
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
    top: i64,
    only_case: String,
}

impl SummaryArgs {
    fn parse(args: &[String]) -> Result<Option<Self>, String> {
        let mut path: Option<String> = None;
        let mut top = 30i64;
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
                top = value
                    .parse::<i64>()
                    .map_err(|_| format!("argument --top: invalid int value: '{value}'"))?;
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

fn object_get<'a>(record: &'a [(String, JsonValue)], key: &str) -> Option<&'a JsonValue> {
    record
        .iter()
        .find_map(|(candidate, value)| (candidate.as_str() == key).then_some(value))
}

fn record_key(record: &[(String, JsonValue)], key: &str) -> String {
    match object_get(record, key) {
        None | Some(JsonValue::Null) => String::new(),
        Some(value) => python_string(value),
    }
}

fn python_string(value: &JsonValue) -> String {
    match value {
        JsonValue::Null => "None".to_owned(),
        JsonValue::Bool(value) => if *value { "True" } else { "False" }.to_owned(),
        JsonValue::Integer(value) => value.clone(),
        JsonValue::Float(value) => python_float(*value),
        JsonValue::String(value) => value.clone(),
        JsonValue::Array(_) | JsonValue::Object(_) => python_repr(value),
    }
}

fn python_repr(value: &JsonValue) -> String {
    match value {
        JsonValue::Null => "None".to_owned(),
        JsonValue::Bool(value) => if *value { "True" } else { "False" }.to_owned(),
        JsonValue::Integer(value) => value.clone(),
        JsonValue::Float(value) => python_float(*value),
        JsonValue::String(value) => python_string_repr(value),
        JsonValue::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(python_repr)
                .collect::<Vec<_>>()
                .join(", ")
        ),
        JsonValue::Object(values) => format!(
            "{{{}}}",
            values
                .iter()
                .map(|(key, value)| format!("{}: {}", python_string_repr(key), python_repr(value)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

fn python_string_repr(value: &str) -> String {
    let quote = if value.contains('\'') && !value.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut rendered = String::with_capacity(value.len() + 2);
    rendered.push(quote);
    for character in value.chars() {
        match character {
            '\\' => rendered.push_str("\\\\"),
            '\n' => rendered.push_str("\\n"),
            '\r' => rendered.push_str("\\r"),
            '\t' => rendered.push_str("\\t"),
            value if value == quote => {
                rendered.push('\\');
                rendered.push(value);
            }
            value if value.is_control() => {
                use fmt::Write as _;
                let _ = write!(rendered, "\\x{:02x}", value as u32);
            }
            value => rendered.push(value),
        }
    }
    rendered.push(quote);
    rendered
}

fn python_float(value: f64) -> String {
    if value.is_nan() {
        return "nan".to_owned();
    }
    if value == f64::INFINITY {
        return "inf".to_owned();
    }
    if value == f64::NEG_INFINITY {
        return "-inf".to_owned();
    }
    if value == 0.0 {
        return if value.is_sign_negative() {
            "-0.0"
        } else {
            "0.0"
        }
        .to_owned();
    }

    let scientific = format!("{value:e}");
    let Some((mantissa, exponent_text)) = scientific.split_once('e') else {
        return scientific;
    };
    let exponent = exponent_text.parse::<i32>().unwrap_or(0);
    if !(-4..16).contains(&exponent) {
        let mut output = mantissa.to_owned();
        if !output.contains('.') {
            output.push_str(".0");
        }
        output.push('e');
        output.push(if exponent >= 0 { '+' } else { '-' });
        let magnitude = exponent.unsigned_abs();
        if magnitude < 10 {
            output.push('0');
        }
        output.push_str(&magnitude.to_string());
        return output;
    }

    let negative = mantissa.starts_with('-');
    let digits = mantissa.trim_start_matches('-').replace('.', "");
    let decimal_point = exponent + 1;
    let mut output = String::new();
    if negative {
        output.push('-');
    }
    if decimal_point <= 0 {
        output.push_str("0.");
        output.extend(std::iter::repeat('0').take((-decimal_point) as usize));
        output.push_str(&digits);
    } else if decimal_point as usize >= digits.len() {
        output.push_str(&digits);
        output.extend(std::iter::repeat('0').take(decimal_point as usize - digits.len()));
        output.push_str(".0");
    } else {
        let split = decimal_point as usize;
        output.push_str(&digits[..split]);
        output.push('.');
        output.push_str(&digits[split..]);
    }
    output
}

fn json_float(value: f64) -> String {
    if value.is_nan() {
        "NaN".to_owned()
    } else if value == f64::INFINITY {
        "Infinity".to_owned()
    } else if value == f64::NEG_INFINITY {
        "-Infinity".to_owned()
    } else {
        python_float(value)
    }
}

fn json_string(value: &str) -> String {
    serde_json::to_string(value).expect("serializing a string cannot fail")
}

fn json_value(value: &JsonValue) -> String {
    match value {
        JsonValue::Null => "null".to_owned(),
        JsonValue::Bool(value) => value.to_string(),
        JsonValue::Integer(value) => value.clone(),
        JsonValue::Float(value) => json_float(*value),
        JsonValue::String(value) => json_string(value),
        JsonValue::Array(values) => format!(
            "[{}]",
            values.iter().map(json_value).collect::<Vec<_>>().join(", ")
        ),
        JsonValue::Object(values) => format!(
            "{{{}}}",
            values
                .iter()
                .map(|(key, value)| format!("{}: {}", json_string(key), json_value(value)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

fn counter_json(counter: &[(String, usize)]) -> String {
    format!(
        "[{}]",
        counter
            .iter()
            .map(|(key, count)| format!("[{}, {}]", json_string(key), count))
            .collect::<Vec<_>>()
            .join(", ")
    )
}

fn format_value(value: &JsonValue) -> String {
    let rendered = match value {
        JsonValue::Array(_) | JsonValue::Object(_) => json_value(value),
        _ => python_string(value),
    };
    rendered.replace('|', "\\|").replace('\n', "<br>")
}

fn render_markdown(input_path: &str, records: &[Vec<(String, JsonValue)>]) -> String {
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
            .unwrap_or_else(|| format!("record-{}", index + 1));
        lines.extend([
            format!("## {title}"),
            String::new(),
            "| key | value |".to_owned(),
            "| --- | --- |".to_owned(),
        ]);
        for key in PREFERRED_KEYS {
            if let Some(value) = object_get(record, key) {
                lines.push(format!("| {key} | {} |", format_value(value)));
            }
        }
        let mut remaining: Vec<_> = record
            .iter()
            .filter(|(key, _)| !PREFERRED_KEYS.contains(&key.as_str()))
            .collect();
        remaining.sort_by(|left, right| left.0.cmp(&right.0));
        for (key, value) in remaining {
            lines.push(format!("| {key} | {} |", format_value(value)));
        }
        lines.push(String::new());
    }
    lines.join("\n")
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

fn python_splitlines(text: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut chars = text.char_indices().peekable();
    while let Some((index, character)) = chars.next() {
        if !is_python_line_separator(character) {
            continue;
        }
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
    if start < text.len() {
        lines.push(&text[start..]);
    }
    lines
}

fn is_python_line_separator(character: char) -> bool {
    matches!(
        character,
        '\n' | '\r' | '\u{000b}' | '\u{000c}' | '\u{001c}'
            ..='\u{001e}' | '\u{0085}' | '\u{2028}' | '\u{2029}'
    )
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
