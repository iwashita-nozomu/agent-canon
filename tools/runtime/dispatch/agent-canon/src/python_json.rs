// @dependency-start
// contract implementation
// responsibility Provides Python-compatible JSON values, parsing, number formatting, and compact ASCII canonicalization.
// downstream implementation execution_resource_projection.rs reuses strict parsing for exact projections.
// downstream implementation update_lifecycle_contract.rs reuses Python integer/bool equality after canonical float rejection.
// downstream implementation result_logs/mod.rs retains result-log output formatting over the shared values.
// downstream test ../tests/python_json_native.rs validates frozen CPython 3.12.3 byte and digest oracles.
// downstream test ../tests/update_lifecycle_queue_native.rs exercises immutable replay equality semantics.
// @dependency-end

use serde::de::{self, Visitor};
use serde::{Deserialize, Deserializer};
use std::fmt;
#[derive(Debug, Clone, Default, PartialEq, Eq, PartialOrd, Ord)]
pub struct JsonString(pub Vec<u32>);

impl JsonString {
    pub fn from_text(value: &str) -> Self {
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

    pub fn to_text(&self) -> Option<String> {
        self.0
            .iter()
            .copied()
            .map(char::from_u32)
            .collect::<Option<String>>()
    }

    pub fn contains_surrogate(&self) -> bool {
        self.0
            .iter()
            .any(|codepoint| (0xd800..=0xdfff).contains(codepoint))
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn equals_text(&self, value: &str) -> bool {
        self.0.iter().copied().eq(value.chars().map(u32::from))
    }

    pub fn push_text(&mut self, value: &str) {
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

pub enum JsonValue {
    Null,
    Bool(bool),
    Number(JsonNumber),
    String(JsonString),
    Array(JsonArray),
    Object(JsonObject),
}

pub struct JsonArray(pub Vec<JsonValue>);

pub enum JsonNumber {
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

    pub fn python_string(&self) -> String {
        match self {
            Self::Integer(value) => value.clone(),
            Self::Float(value) => python_float(*value),
        }
    }

    pub fn json_string(&self) -> String {
        match self {
            Self::Integer(value) => value.clone(),
            Self::Float(value) => json_float(*value),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum JsonParseError {
    Syntax {
        message: String,
        index: usize,
        byte_index: usize,
        parser_column: bool,
    },
    DuplicateKey(JsonString),
    NonFiniteConstant(String),
}

impl JsonParseError {
    pub fn message(&self) -> JsonString {
        match self {
            Self::Syntax { message, index, .. } => JsonString::from_text(&format!(
                "Expecting value: line 1 column {} (char {index})",
                *index + 1
            )),
            Self::DuplicateKey(key) => {
                let mut message = JsonString::from_text("duplicate JSON key: ");
                message.0.extend_from_slice(&key.0);
                message
            }
            Self::NonFiniteConstant(message) => JsonString::from_text(message),
        }
    }

    fn display_text(&self) -> String {
        match self {
            Self::Syntax {
                message,
                byte_index,
                parser_column,
                ..
            } => {
                if *parser_column {
                    format!("{message} at column {}", *byte_index + 1)
                } else {
                    message.clone()
                }
            }
            Self::DuplicateKey(key) => {
                let mut message = String::from("duplicate JSON key: ");
                for codepoint in &key.0 {
                    if let Some(character) = char::from_u32(*codepoint) {
                        message.push(character);
                    } else {
                        message.push_str(&format!("\\u{codepoint:04x}"));
                    }
                }
                message
            }
            Self::NonFiniteConstant(message) => message.clone(),
        }
    }
}

impl From<String> for JsonParseError {
    fn from(value: String) -> Self {
        Self::Syntax {
            message: value,
            index: 0,
            byte_index: 0,
            parser_column: false,
        }
    }
}

pub fn parse_json(input: &str) -> Result<JsonValue, String> {
    JsonParser::new(input, false)
        .parse()
        .map_err(|error| error.display_text())
}

/// Parse JSON while rejecting duplicate object keys and Python's non-finite constants.
/// Existing callers retain `parse_json`'s last-key-wins and constant behavior.
pub fn parse_json_reject_duplicates(input: &str) -> Result<JsonValue, JsonParseError> {
    JsonParser::new(input, true).parse()
}

// Python accepts 9,994 arrays nested inside the record object (9,995 containers total).
pub const MAX_JSON_NESTING: usize = 9995;

enum JsonFrame {
    Array {
        values: JsonArray,
        state: ArrayState,
    },
    Object {
        values: JsonObject,
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
    reject_duplicates: bool,
}

impl<'a> JsonParser<'a> {
    fn new(input: &'a str, reject_duplicates: bool) -> Self {
        Self {
            input,
            bytes: input.as_bytes(),
            index: 0,
            reject_duplicates,
        }
    }

    fn parse(mut self) -> Result<JsonValue, JsonParseError> {
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
                            values.0.push(value);
                            *state = ArrayState::CommaOrEnd;
                        }
                        JsonFrame::Object { values, key, state } => {
                            if !matches!(state, ObjectState::Value) {
                                return Err(self.error("unexpected object value"));
                            }
                            let key = key.take().ok_or_else(|| self.error("missing object key"))?;
                            if let Some(position) =
                                values.0.iter().position(|(existing, _)| existing == &key)
                            {
                                if self.reject_duplicates {
                                    return Err(JsonParseError::DuplicateKey(key));
                                }
                                values.0[position].1 = value;
                            } else {
                                values.0.push((key, value));
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
    ) -> Result<Option<JsonValue>, JsonParseError> {
        self.skip_whitespace();
        match self.peek() {
            Some(b'{') => {
                self.check_depth(frames.len())?;
                self.index += 1;
                frames.push(JsonFrame::Object {
                    values: JsonObject(Vec::new()),
                    key: None,
                    state: ObjectState::KeyOrEnd,
                });
                Ok(None)
            }
            Some(b'[') => {
                self.check_depth(frames.len())?;
                self.index += 1;
                frames.push(JsonFrame::Array {
                    values: JsonArray(Vec::new()),
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
                if self.reject_duplicates {
                    return Err(JsonParseError::NonFiniteConstant(
                        "non-finite JSON constant: NaN".to_owned(),
                    ));
                }
                Ok(Some(JsonValue::Number(JsonNumber::Float(f64::NAN))))
            }
            Some(b'I') => {
                self.consume_literal("Infinity")?;
                if self.reject_duplicates {
                    return Err(JsonParseError::NonFiniteConstant(
                        "non-finite JSON constant: Infinity".to_owned(),
                    ));
                }
                Ok(Some(JsonValue::Number(JsonNumber::Float(f64::INFINITY))))
            }
            Some(b'-') if self.input[self.index..].starts_with("-Infinity") => {
                self.consume_literal("-Infinity")?;
                if self.reject_duplicates {
                    return Err(JsonParseError::NonFiniteConstant(
                        "non-finite JSON constant: -Infinity".to_owned(),
                    ));
                }
                Ok(Some(JsonValue::Number(JsonNumber::Float(
                    f64::NEG_INFINITY,
                ))))
            }
            Some(b'-' | b'0'..=b'9') => self.parse_number().map(Some),
            Some(_) => Err(self.error("expected a JSON value")),
            None => Err(self.error("unexpected end of input")),
        }
    }

    fn parse_string(&mut self) -> Result<JsonString, JsonParseError> {
        let start = self.index;
        self.index += 1;
        while self.index < self.bytes.len() {
            match self.bytes[self.index] {
                b'"' => {
                    self.index += 1;
                    // This scan only finds the token boundary; serde_json decodes the escapes.
                    return serde_json::from_str::<JsonString>(&self.input[start..self.index])
                        .map_err(|error| error.to_string().into());
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

    fn parse_number(&mut self) -> Result<JsonValue, JsonParseError> {
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

    fn consume_literal(&mut self, literal: &str) -> Result<(), JsonParseError> {
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

    fn check_depth(&self, depth: usize) -> Result<(), JsonParseError> {
        if depth >= MAX_JSON_NESTING {
            Err(self.error("maximum JSON nesting depth exceeded"))
        } else {
            Ok(())
        }
    }

    fn error(&self, message: &str) -> JsonParseError {
        JsonParseError::Syntax {
            message: message.to_owned(),
            index: self.input[..self.index].chars().count(),
            byte_index: self.index,
            parser_column: true,
        }
    }
}

fn pop_frame(frames: &mut Vec<JsonFrame>) -> Result<JsonValue, JsonParseError> {
    match frames.pop() {
        Some(JsonFrame::Array { values, .. }) => Ok(JsonValue::Array(values)),
        Some(JsonFrame::Object {
            values, key: None, ..
        }) => Ok(JsonValue::Object(values)),
        Some(JsonFrame::Object { .. }) => {
            Err("object closed with an incomplete key".to_owned().into())
        }
        None => Err("container stack is empty".to_owned().into()),
    }
}

pub struct JsonObject(pub Vec<(JsonString, JsonValue)>);

impl Drop for JsonArray {
    fn drop(&mut self) {
        discard_json_values(std::mem::take(&mut self.0));
    }
}

impl Drop for JsonObject {
    fn drop(&mut self) {
        discard_json_values(
            std::mem::take(&mut self.0)
                .into_iter()
                .map(|(_, value)| value),
        );
    }
}

fn discard_json_values(values: impl IntoIterator<Item = JsonValue>) {
    // Empty child containers before their normal field drops to keep destruction iterative.
    let mut pending: Vec<JsonValue> = values.into_iter().collect();
    while let Some(mut value) = pending.pop() {
        match &mut value {
            JsonValue::Array(array) => pending.extend(std::mem::take(&mut array.0)),
            JsonValue::Object(object) => {
                pending.extend(
                    std::mem::take(&mut object.0)
                        .into_iter()
                        .map(|(_, value)| value),
                );
            }
            JsonValue::Null | JsonValue::Bool(_) | JsonValue::Number(_) | JsonValue::String(_) => {}
        }
    }
}

pub fn python_float(value: f64) -> String {
    rustpython_ast::Constant::Float(value).to_string()
}

pub fn json_float(value: f64) -> String {
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

fn is_json_integer(value: &str) -> bool {
    let digits = value.strip_prefix('-').unwrap_or(value);
    if digits == "0" {
        return !value.starts_with('-');
    }
    let bytes = digits.as_bytes();
    !bytes.is_empty()
        && (b'1'..=b'9').contains(&bytes[0])
        && bytes[1..].iter().all(u8::is_ascii_digit)
}

/// Serialize with Python's `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)` bytes.
pub fn canonical_json_ascii_bytes(value: &JsonValue) -> Result<Vec<u8>, String> {
    canonical_json_ascii_bytes_with_nonfinite(value, false)
}

/// Serialize with the same canonical form, rejecting non-finite floats as `allow_nan=False` does.
pub fn canonical_json_ascii_bytes_reject_nonfinite(value: &JsonValue) -> Result<Vec<u8>, String> {
    canonical_json_ascii_bytes_with_nonfinite(value, true)
}

fn canonical_json_ascii_bytes_with_nonfinite(
    value: &JsonValue,
    reject_nonfinite: bool,
) -> Result<Vec<u8>, String> {
    enum Action<'a> {
        Value(&'a JsonValue),
        String(&'a JsonString),
        Text(&'static [u8]),
    }

    let mut bytes = Vec::new();
    let mut actions = vec![Action::Value(value)];
    while let Some(action) = actions.pop() {
        match action {
            Action::Text(text) => bytes.extend_from_slice(text),
            Action::String(value) => write_ascii_json_string(value, &mut bytes)?,
            Action::Value(value) => match value {
                JsonValue::Null => bytes.extend_from_slice(b"null"),
                JsonValue::Bool(value) => {
                    bytes.extend_from_slice(if *value { b"true" } else { b"false" })
                }
                JsonValue::Number(JsonNumber::Integer(value)) => {
                    if value == "-0" {
                        bytes.push(b'0');
                    } else if !is_json_integer(value) {
                        return Err("invalid integer in Python JSON value".to_owned());
                    } else {
                        bytes.extend_from_slice(value.as_bytes());
                    }
                }
                JsonValue::Number(JsonNumber::Float(value)) => {
                    if reject_nonfinite && !value.is_finite() {
                        let value_text = if value.is_nan() {
                            "nan"
                        } else if value.is_sign_negative() {
                            "-inf"
                        } else {
                            "inf"
                        };
                        return Err(format!(
                            "Out of range float values are not JSON compliant: {value_text}"
                        ));
                    }
                    bytes.extend_from_slice(json_float(*value).as_bytes());
                }
                JsonValue::String(value) => actions.push(Action::String(value)),
                JsonValue::Array(values) => {
                    bytes.push(b'[');
                    actions.push(Action::Text(b"]"));
                    for index in (0..values.0.len()).rev() {
                        actions.push(Action::Value(&values.0[index]));
                        if index > 0 {
                            actions.push(Action::Text(b","));
                        }
                    }
                }
                JsonValue::Object(values) => {
                    let mut entries: Vec<_> = values.0.iter().collect();
                    entries.sort_by(|left, right| left.0.cmp(&right.0));
                    let mut unique_entries = Vec::with_capacity(entries.len());
                    let mut index = 0;
                    while index < entries.len() {
                        let mut end = index + 1;
                        while end < entries.len() && entries[end].0 == entries[index].0 {
                            end += 1;
                        }
                        unique_entries.push(entries[end - 1]);
                        index = end;
                    }
                    bytes.push(b'{');
                    actions.push(Action::Text(b"}"));
                    for index in (0..unique_entries.len()).rev() {
                        let (key, value) = unique_entries[index];
                        actions.push(Action::Value(value));
                        actions.push(Action::Text(b":"));
                        actions.push(Action::String(key));
                        if index > 0 {
                            actions.push(Action::Text(b","));
                        }
                    }
                }
            },
        }
    }
    Ok(bytes)
}

fn write_ascii_json_string(value: &JsonString, output: &mut Vec<u8>) -> Result<(), String> {
    output.push(b'"');
    for &codepoint in &value.0 {
        match codepoint {
            0x08 => output.extend_from_slice(b"\\b"),
            0x09 => output.extend_from_slice(b"\\t"),
            0x0a => output.extend_from_slice(b"\\n"),
            0x0c => output.extend_from_slice(b"\\f"),
            0x0d => output.extend_from_slice(b"\\r"),
            0x00..=0x1f => write_u16_escape(codepoint as u16, output),
            0x22 => output.extend_from_slice(b"\\\""),
            0x5c => output.extend_from_slice(b"\\\\"),
            0x20..=0x7e => output.push(codepoint as u8),
            0x7f..=0xffff => write_u16_escape(codepoint as u16, output),
            0x1_0000..=0x10_ffff => {
                let scalar = codepoint - 0x1_0000;
                let high = 0xd800 + (scalar >> 10);
                let low = 0xdc00 + (scalar & 0x3ff);
                write_u16_escape(high as u16, output);
                write_u16_escape(low as u16, output);
            }
            _ => {
                return Err(format!(
                    "JSON string contains invalid code point U+{codepoint:X}"
                ))
            }
        }
    }
    output.push(b'"');
    Ok(())
}

fn write_u16_escape(codepoint: u16, output: &mut Vec<u8>) {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    output.extend_from_slice(b"\\u");
    output.push(HEX[((codepoint >> 12) & 0xf) as usize]);
    output.push(HEX[((codepoint >> 8) & 0xf) as usize]);
    output.push(HEX[((codepoint >> 4) & 0xf) as usize]);
    output.push(HEX[(codepoint & 0xf) as usize]);
}

fn integer_number_text(value: &serde_json::Number) -> Option<String> {
    if value.is_f64() {
        return None;
    }
    let text = value.to_string();
    Some(if text == "-0" { "0".to_owned() } else { text })
}

/// Compare canonicalized serde JSON values using Python's integer/bool equality.
/// Callers must canonical-clone first, which rejects floats through the artifact owner.
pub(crate) fn python_json_equal_after_float_rejection(
    left: &serde_json::Value,
    right: &serde_json::Value,
) -> bool {
    let mut pending = vec![(left, right)];
    while let Some((left, right)) = pending.pop() {
        match (left, right) {
            (serde_json::Value::Null, serde_json::Value::Null) => {}
            (serde_json::Value::Bool(left), serde_json::Value::Bool(right)) => {
                if left != right {
                    return false;
                }
            }
            (serde_json::Value::Bool(left), serde_json::Value::Number(right)) => {
                let expected = if *left { "1" } else { "0" };
                if integer_number_text(right).as_deref() != Some(expected) {
                    return false;
                }
            }
            (serde_json::Value::Number(left), serde_json::Value::Bool(right)) => {
                let expected = if *right { "1" } else { "0" };
                if integer_number_text(left).as_deref() != Some(expected) {
                    return false;
                }
            }
            (serde_json::Value::Number(left), serde_json::Value::Number(right)) => {
                match (integer_number_text(left), integer_number_text(right)) {
                    (Some(left), Some(right)) if left == right => {}
                    _ => return false,
                }
            }
            (serde_json::Value::String(left), serde_json::Value::String(right)) => {
                if left != right {
                    return false;
                }
            }
            (serde_json::Value::Array(left), serde_json::Value::Array(right)) => {
                if left.len() != right.len() {
                    return false;
                }
                pending.extend(left.iter().zip(right));
            }
            (serde_json::Value::Object(left), serde_json::Value::Object(right)) => {
                if left.len() != right.len() {
                    return false;
                }
                for (key, left_value) in left {
                    let Some(right_value) = right.get(key) else {
                        return false;
                    };
                    pending.push((left_value, right_value));
                }
            }
            _ => return false,
        }
    }
    true
}
