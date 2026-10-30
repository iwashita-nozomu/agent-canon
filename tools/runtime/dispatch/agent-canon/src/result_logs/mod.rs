// @dependency-start
// contract implementation
// responsibility Preserves JSONL result conversion and HLO summary behavior in native Rust.
// upstream design ../../../../../../documents/experiments/result-log-retention-and-visualization.md owns summary and report policy
// downstream implementation ../../../../../../../tests/tools/test_result_log_tools.py exercises both public commands
// @dependency-end

use serde::de::{self, Visitor};
use serde::{Deserialize, Deserializer};
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

#[derive(Debug, Clone, Default, PartialEq, Eq, PartialOrd, Ord)]
struct JsonString(Vec<u32>);

impl JsonString {
    fn from_text(value: &str) -> Self {
        Self(value.chars().map(u32::from).collect())
    }

    fn from_wtf8(bytes: &[u8]) -> Result<Self, &'static str> {
        let mut codepoints = Vec::with_capacity(bytes.len());
        let mut index = 0;
        while index < bytes.len() {
            let first = bytes[index];
            let (codepoint, length) = match first {
                0x00..=0x7f => (u32::from(first), 1),
                0xc2..=0xdf if index + 1 < bytes.len() => {
                    let second = continuation(bytes[index + 1])?;
                    ((u32::from(first & 0x1f) << 6) | u32::from(second), 2)
                }
                0xe0..=0xef if index + 2 < bytes.len() => {
                    let second = continuation(bytes[index + 1])?;
                    let third = continuation(bytes[index + 2])?;
                    let codepoint = (u32::from(first & 0x0f) << 12)
                        | (u32::from(second) << 6)
                        | u32::from(third);
                    if codepoint < 0x800 {
                        return Err("overlong WTF-8 sequence");
                    }
                    (codepoint, 3)
                }
                0xf0..=0xf4 if index + 3 < bytes.len() => {
                    let second = continuation(bytes[index + 1])?;
                    let third = continuation(bytes[index + 2])?;
                    let fourth = continuation(bytes[index + 3])?;
                    let codepoint = (u32::from(first & 0x07) << 18)
                        | (u32::from(second) << 12)
                        | (u32::from(third) << 6)
                        | u32::from(fourth);
                    if !(0x1_0000..=0x10_ffff).contains(&codepoint) {
                        return Err("invalid four-byte WTF-8 sequence");
                    }
                    (codepoint, 4)
                }
                _ => return Err("invalid WTF-8 sequence"),
            };
            codepoints.push(codepoint);
            index += length;
        }
        Ok(Self(codepoints))
    }

    fn to_text(&self) -> Option<String> {
        self.0
            .iter()
            .copied()
            .map(char::from_u32)
            .collect::<Option<String>>()
    }

    fn contains_surrogate(&self) -> bool {
        self.0
            .iter()
            .any(|codepoint| (0xd800..=0xdfff).contains(codepoint))
    }

    fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    fn equals_text(&self, value: &str) -> bool {
        self.0.iter().copied().eq(value.chars().map(u32::from))
    }

    fn push_text(&mut self, value: &str) {
        self.0.extend(value.chars().map(u32::from));
    }
}

fn continuation(byte: u8) -> Result<u8, &'static str> {
    if byte & 0xc0 == 0x80 {
        Ok(byte & 0x3f)
    } else {
        Err("invalid WTF-8 continuation byte")
    }
}

impl<'de> Deserialize<'de> for JsonString {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct JsonStringVisitor;

        impl<'de> Visitor<'de> for JsonStringVisitor {
            type Value = JsonString;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("a JSON string")
            }

            fn visit_bytes<E>(self, value: &[u8]) -> Result<Self::Value, E>
            where
                E: de::Error,
            {
                JsonString::from_wtf8(value).map_err(E::custom)
            }

            fn visit_borrowed_bytes<E>(self, value: &'de [u8]) -> Result<Self::Value, E>
            where
                E: de::Error,
            {
                self.visit_bytes(value)
            }

            fn visit_byte_buf<E>(self, value: Vec<u8>) -> Result<Self::Value, E>
            where
                E: de::Error,
            {
                self.visit_bytes(&value)
            }
        }

        // serde_json decodes lone surrogates as WTF-8 on its byte path.
        deserializer.deserialize_bytes(JsonStringVisitor)
    }
}

#[derive(Debug, Clone)]
enum JsonValue {
    Null,
    Bool(bool),
    Number(JsonNumber),
    String(JsonString),
    Array(Vec<JsonValue>),
    Object(JsonObject),
}

#[derive(Debug, Clone)]
enum JsonNumber {
    Integer(String),
    Float(f64),
}

impl JsonNumber {
    fn from_raw(raw: &str) -> Self {
        if raw
            .chars()
            .any(|character| matches!(character, '.' | 'e' | 'E'))
        {
            let value = raw.parse().unwrap_or_else(|_| {
                if raw.starts_with('-') {
                    f64::NEG_INFINITY
                } else {
                    f64::INFINITY
                }
            });
            Self::Float(value)
        } else if raw == "-0" {
            Self::Integer("0".to_owned())
        } else {
            Self::Integer(raw.to_owned())
        }
    }

    fn python_string(&self) -> String {
        match self {
            Self::Integer(value) => value.clone(),
            Self::Float(value) => python_float(*value),
        }
    }

    fn json_string(&self) -> String {
        match self {
            Self::Integer(value) => value.clone(),
            Self::Float(value) => json_float(*value),
        }
    }
}

fn parse_json_line(input: &str) -> Result<JsonValue, String> {
    JsonParser::new(input).parse()
}

const MAX_JSON_NESTING: usize = 1000;

enum JsonFrame {
    Array {
        values: Vec<JsonValue>,
        state: ArrayState,
    },
    Object {
        values: Vec<(JsonString, JsonValue)>,
        key: Option<JsonString>,
        state: ObjectState,
    },
}

#[derive(Clone, Copy)]
enum ArrayState {
    ValueOrEnd,
    Value,
    CommaOrEnd,
}

#[derive(Clone, Copy)]
enum ObjectState {
    KeyOrEnd,
    Key,
    Colon,
    Value,
    CommaOrEnd,
}

#[derive(Clone, Copy)]
enum FrameState {
    ArrayValueOrEnd,
    ArrayValue,
    ArrayCommaOrEnd,
    ObjectKeyOrEnd,
    ObjectKey,
    ObjectColon,
    ObjectValue,
    ObjectCommaOrEnd,
}

impl JsonFrame {
    fn state(&self) -> FrameState {
        match self {
            Self::Array { state, .. } => match state {
                ArrayState::ValueOrEnd => FrameState::ArrayValueOrEnd,
                ArrayState::Value => FrameState::ArrayValue,
                ArrayState::CommaOrEnd => FrameState::ArrayCommaOrEnd,
            },
            Self::Object { state, .. } => match state {
                ObjectState::KeyOrEnd => FrameState::ObjectKeyOrEnd,
                ObjectState::Key => FrameState::ObjectKey,
                ObjectState::Colon => FrameState::ObjectColon,
                ObjectState::Value => FrameState::ObjectValue,
                ObjectState::CommaOrEnd => FrameState::ObjectCommaOrEnd,
            },
        }
    }
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
        let mut frames = Vec::new();
        let mut completed = None;
        let root = loop {
            if let Some(value) = completed.take() {
                if let Some(frame) = frames.last_mut() {
                    match frame {
                        JsonFrame::Array { values, state } => {
                            if !matches!(state, ArrayState::ValueOrEnd | ArrayState::Value) {
                                return Err(self.error("unexpected array value"));
                            }
                            values.push(value);
                            *state = ArrayState::CommaOrEnd;
                        }
                        JsonFrame::Object { values, key, state } => {
                            if !matches!(state, ObjectState::Value) {
                                return Err(self.error("unexpected object value"));
                            }
                            let key = key.take().ok_or_else(|| self.error("missing object key"))?;
                            if let Some(position) =
                                values.iter().position(|(existing, _)| existing == &key)
                            {
                                values[position].1 = value;
                            } else {
                                values.push((key, value));
                            }
                            *state = ObjectState::CommaOrEnd;
                        }
                    }
                } else {
                    break value;
                }
                continue;
            }

            let Some(state) = frames.last().map(JsonFrame::state) else {
                completed = self.parse_value_start(&mut frames)?;
                continue;
            };
            match state {
                FrameState::ArrayValueOrEnd => {
                    self.skip_whitespace();
                    if self.consume_if(b']') {
                        completed = Some(pop_frame(&mut frames)?);
                    } else {
                        completed = self.parse_value_start(&mut frames)?;
                    }
                }
                FrameState::ArrayValue => {
                    self.skip_whitespace();
                    completed = self.parse_value_start(&mut frames)?;
                }
                FrameState::ArrayCommaOrEnd => {
                    self.skip_whitespace();
                    if self.consume_if(b']') {
                        completed = Some(pop_frame(&mut frames)?);
                    } else if self.consume_if(b',') {
                        if let Some(JsonFrame::Array { state, .. }) = frames.last_mut() {
                            *state = ArrayState::Value;
                        }
                    } else {
                        return Err(self.error("expected ',' or ']' after array value"));
                    }
                }
                FrameState::ObjectKeyOrEnd => {
                    self.skip_whitespace();
                    if self.consume_if(b'}') {
                        completed = Some(pop_frame(&mut frames)?);
                    } else {
                        let key = self.parse_string()?;
                        if let Some(JsonFrame::Object {
                            key: slot, state, ..
                        }) = frames.last_mut()
                        {
                            *slot = Some(key);
                            *state = ObjectState::Colon;
                        }
                    }
                }
                FrameState::ObjectKey => {
                    self.skip_whitespace();
                    let key = self.parse_string()?;
                    if let Some(JsonFrame::Object {
                        key: slot, state, ..
                    }) = frames.last_mut()
                    {
                        *slot = Some(key);
                        *state = ObjectState::Colon;
                    }
                }
                FrameState::ObjectColon => {
                    self.skip_whitespace();
                    if !self.consume_if(b':') {
                        return Err(self.error("expected ':' after object key"));
                    }
                    if let Some(JsonFrame::Object { state, .. }) = frames.last_mut() {
                        *state = ObjectState::Value;
                    }
                }
                FrameState::ObjectValue => {
                    self.skip_whitespace();
                    completed = self.parse_value_start(&mut frames)?;
                }
                FrameState::ObjectCommaOrEnd => {
                    self.skip_whitespace();
                    if self.consume_if(b'}') {
                        completed = Some(pop_frame(&mut frames)?);
                    } else if self.consume_if(b',') {
                        if let Some(JsonFrame::Object { state, .. }) = frames.last_mut() {
                            *state = ObjectState::Key;
                        }
                    } else {
                        return Err(self.error("expected ',' or '}' after object value"));
                    }
                }
            }
        };
        self.skip_whitespace();
        if self.index != self.bytes.len() {
            return Err(self.error("unexpected trailing characters"));
        }
        Ok(root)
    }

    fn parse_value_start(
        &mut self,
        frames: &mut Vec<JsonFrame>,
    ) -> Result<Option<JsonValue>, String> {
        self.skip_whitespace();
        match self.peek() {
            Some(b'{') => {
                self.check_depth(frames.len())?;
                self.index += 1;
                frames.push(JsonFrame::Object {
                    values: Vec::new(),
                    key: None,
                    state: ObjectState::KeyOrEnd,
                });
                Ok(None)
            }
            Some(b'[') => {
                self.check_depth(frames.len())?;
                self.index += 1;
                frames.push(JsonFrame::Array {
                    values: Vec::new(),
                    state: ArrayState::ValueOrEnd,
                });
                Ok(None)
            }
            Some(b'"') => self.parse_string().map(JsonValue::String).map(Some),
            Some(b't') => {
                self.consume_literal("true")?;
                Ok(Some(JsonValue::Bool(true)))
            }
            Some(b'f') => {
                self.consume_literal("false")?;
                Ok(Some(JsonValue::Bool(false)))
            }
            Some(b'n') => {
                self.consume_literal("null")?;
                Ok(Some(JsonValue::Null))
            }
            Some(b'N') => {
                self.consume_literal("NaN")?;
                Ok(Some(JsonValue::Number(JsonNumber::Float(f64::NAN))))
            }
            Some(b'I') => {
                self.consume_literal("Infinity")?;
                Ok(Some(JsonValue::Number(JsonNumber::Float(f64::INFINITY))))
            }
            Some(b'-') if self.input[self.index..].starts_with("-Infinity") => {
                self.consume_literal("-Infinity")?;
                Ok(Some(JsonValue::Number(JsonNumber::Float(
                    f64::NEG_INFINITY,
                ))))
            }
            Some(b'-' | b'0'..=b'9') => self.parse_number().map(Some),
            Some(_) => Err(self.error("expected a JSON value")),
            None => Err(self.error("unexpected end of input")),
        }
    }

    fn parse_string(&mut self) -> Result<JsonString, String> {
        let start = self.index;
        self.index += 1;
        while self.index < self.bytes.len() {
            match self.bytes[self.index] {
                b'"' => {
                    self.index += 1;
                    // This scan only finds the token boundary; serde_json decodes the escapes.
                    return serde_json::from_str::<JsonString>(&self.input[start..self.index])
                        .map_err(|error| error.to_string());
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
        if !is_float && raw == "-0" {
            Ok(JsonValue::Number(JsonNumber::Integer("0".to_owned())))
        } else {
            Ok(JsonValue::Number(JsonNumber::from_raw(raw)))
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

    fn check_depth(&self, depth: usize) -> Result<(), String> {
        if depth >= MAX_JSON_NESTING {
            Err(self.error("maximum JSON nesting depth exceeded"))
        } else {
            Ok(())
        }
    }

    fn error(&self, message: &str) -> String {
        format!("{message} at column {}", self.index + 1)
    }
}

fn pop_frame(frames: &mut Vec<JsonFrame>) -> Result<JsonValue, String> {
    match frames.pop() {
        Some(JsonFrame::Array { values, .. }) => Ok(JsonValue::Array(values)),
        Some(JsonFrame::Object {
            values, key: None, ..
        }) => Ok(JsonValue::Object(JsonObject(values))),
        Some(JsonFrame::Object { .. }) => Err("object closed with an incomplete key".to_owned()),
        None => Err("container stack is empty".to_owned()),
    }
}

#[derive(Debug, Clone)]
struct JsonObject(Vec<(JsonString, JsonValue)>);

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

    fn pairs(&self, limit: Option<i64>) -> Vec<(JsonString, usize)> {
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
        let value = match parse_json_line(stripped) {
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

    let top_ops = ops_total.pairs(Some(parsed.top));
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
    match value {
        JsonValue::Null => JsonString::from_text("None"),
        JsonValue::Bool(value) => JsonString::from_text(if *value { "True" } else { "False" }),
        JsonValue::Number(value) => JsonString::from_text(&value.python_string()),
        JsonValue::String(value) => python_string_repr(value),
        JsonValue::Array(values) => {
            let mut rendered = JsonString::from_text("[");
            for (index, value) in values.iter().enumerate() {
                if index > 0 {
                    rendered.push_text(", ");
                }
                rendered.0.extend(python_repr(value).0);
            }
            rendered.push_text("]");
            rendered
        }
        JsonValue::Object(values) => {
            let mut rendered = JsonString::from_text("{");
            for (index, (key, value)) in values.0.iter().enumerate() {
                if index > 0 {
                    rendered.push_text(", ");
                }
                rendered.0.extend(python_string_repr(key).0);
                rendered.push_text(": ");
                rendered.0.extend(python_repr(value).0);
            }
            rendered.push_text("}");
            rendered
        }
    }
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
        output.extend(std::iter::repeat_n('0', (-decimal_point) as usize));
        output.push_str(&digits);
    } else if decimal_point as usize >= digits.len() {
        output.push_str(&digits);
        output.extend(std::iter::repeat_n(
            '0',
            decimal_point as usize - digits.len(),
        ));
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
    Ok(match value {
        JsonValue::Null => "null".to_owned(),
        JsonValue::Bool(value) => value.to_string(),
        JsonValue::Number(value) => value.json_string(),
        JsonValue::String(value) => json_string(value)?,
        JsonValue::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(json_value)
                .collect::<Result<Vec<_>, _>>()?
                .join(", ")
        ),
        JsonValue::Object(values) => {
            let mut rendered = Vec::with_capacity(values.0.len());
            for (key, value) in &values.0 {
                rendered.push(format!("{}: {}", json_string(key)?, json_value(value)?));
            }
            format!("{{{}}}", rendered.join(", "))
        }
    })
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
