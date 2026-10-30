// @dependency-start
// contract implementation
// responsibility Reads selected canonical Skill bodies in bounded UTF-8 chunks and reports exact file EOF.
// upstream design ../../../../../agents/skills/agent-orchestration.md owner-first Skill read and implementation admission
// upstream design ../../../../../agents/canonical/CODEX_WORKFLOW.md bounded Skill read admission
// downstream implementation ../../../../../tests/agent_tools/test_skill_document_reader.py validates heading indexing, chunk boundaries, and admission state
// @dependency-end
//! Read selected Skill sections or canonical bodies through bounded UTF-8 chunks.

use serde::Serialize;
use serde_json::Value;
use std::error::Error;
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};

pub const DEFAULT_MAX_BYTES: i128 = 4_096;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SkillDocumentError {
    pub code: &'static str,
    pub detail: String,
}

impl SkillDocumentError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for SkillDocumentError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.detail.is_empty() {
            formatter.write_str(self.code)
        } else {
            write!(formatter, "{}:{}", self.code, self.detail)
        }
    }
}

impl Error for SkillDocumentError {}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Heading {
    pub heading: String,
    pub title: String,
    pub level: usize,
    pub line: usize,
    pub byte_start: usize,
    pub byte_end: usize,
    pub section_end: usize,
}

impl Heading {
    pub fn as_json(&self) -> Value {
        serde_json::to_value(self).expect("Heading is JSON serializable")
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct DocumentChunk {
    pub path: String,
    pub heading: Option<String>,
    pub line_start: Option<usize>,
    pub line_end: Option<usize>,
    pub byte_start: usize,
    pub byte_end: usize,
    pub next_offset: usize,
    pub section_eof: bool,
    pub file_eof: bool,
    pub text: String,
}

impl DocumentChunk {
    pub fn as_json(&self) -> Value {
        serde_json::to_value(self).expect("DocumentChunk is JSON serializable")
    }

    fn metadata(&self) -> DocumentChunkMetadata<'_> {
        DocumentChunkMetadata {
            path: &self.path,
            heading: self.heading.as_deref(),
            line_start: self.line_start,
            line_end: self.line_end,
            byte_start: self.byte_start,
            byte_end: self.byte_end,
            next_offset: self.next_offset,
            section_eof: self.section_eof,
            file_eof: self.file_eof,
        }
    }
}

#[derive(Serialize)]
struct DocumentChunkMetadata<'a> {
    path: &'a str,
    heading: Option<&'a str>,
    line_start: Option<usize>,
    line_end: Option<usize>,
    byte_start: usize,
    byte_end: usize,
    next_offset: usize,
    section_eof: bool,
    file_eof: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SkillReadAdmission {
    pub owner_sections: Vec<DocumentChunk>,
    pub implementation_read: String,
}

impl SkillReadAdmission {
    pub fn as_json(&self) -> Value {
        serde_json::to_value(AdmissionProjection {
            owner_sections: self
                .owner_sections
                .iter()
                .map(DocumentChunk::metadata)
                .collect(),
            implementation_read: &self.implementation_read,
        })
        .expect("SkillReadAdmission is JSON serializable")
    }
}

#[derive(Serialize)]
struct AdmissionProjection<'a> {
    owner_sections: Vec<DocumentChunkMetadata<'a>>,
    implementation_read: &'a str,
}

#[derive(Debug)]
struct Line {
    start: usize,
    end: usize,
    text: String,
}

pub struct SkillDocumentReader {
    path: PathBuf,
    data: Vec<u8>,
    lines: Vec<Line>,
    headings: Vec<Heading>,
}

impl SkillDocumentReader {
    pub fn new(path: impl AsRef<Path>) -> Result<Self, SkillDocumentError> {
        let path = path.as_ref().to_path_buf();
        let data = fs::read(&path)
            .map_err(|_| SkillDocumentError::new("read_failed", path_as_posix(&path)))?;
        let lines = line_table(&data)?;
        let headings = index_headings(&lines, data.len());
        Ok(Self {
            path,
            data,
            lines,
            headings,
        })
    }

    pub fn find_heading(&self, requested: &str) -> Result<&Heading, SkillDocumentError> {
        let value = requested.trim();
        let exact: Vec<&Heading> = self
            .headings
            .iter()
            .filter(|item| item.heading == value)
            .collect();
        if exact.len() == 1 {
            return Ok(exact[0]);
        }
        if exact.len() > 1 {
            return Err(SkillDocumentError::new("heading_ambiguous", value));
        }
        let title_matches: Vec<&Heading> = self
            .headings
            .iter()
            .filter(|item| item.title == value)
            .collect();
        if title_matches.len() == 1 {
            return Ok(title_matches[0]);
        }
        if title_matches.len() > 1 {
            return Err(SkillDocumentError::new("heading_ambiguous", value));
        }
        Err(SkillDocumentError::new("heading_not_found", value))
    }

    pub fn index(&self) -> &[Heading] {
        &self.headings
    }

    pub fn chunk(
        &self,
        heading: Option<&str>,
        offset: i128,
        max_bytes: i128,
    ) -> Result<DocumentChunk, SkillDocumentError> {
        if max_bytes <= 0 {
            return Err(SkillDocumentError::new(
                "invalid_max_bytes",
                max_bytes.to_string(),
            ));
        }
        let selected = heading.map(|value| self.find_heading(value)).transpose()?;
        let section_start = selected.map_or(0, |item| item.byte_start);
        let section_end = selected.map_or(self.data.len(), |item| item.section_end);
        let effective_offset = if offset == 0 {
            section_start as i128
        } else {
            offset
        };
        if effective_offset < section_start as i128 || effective_offset > section_end as i128 {
            return Err(SkillDocumentError::new(
                "offset_out_of_section",
                effective_offset.to_string(),
            ));
        }
        if effective_offset == section_end as i128 {
            return Err(SkillDocumentError::new(
                "offset_at_eof",
                effective_offset.to_string(),
            ));
        }

        let start = effective_offset as usize;
        let max_bytes_value = max_bytes;
        let max_bytes = usize::try_from(max_bytes_value).unwrap_or(usize::MAX);
        let mut end = start + max_bytes.min(section_end - start);
        let text = loop {
            if end <= start {
                break None;
            }
            match std::str::from_utf8(&self.data[start..end]) {
                Ok(text) => break Some(text.to_owned()),
                Err(_) => end -= 1,
            }
        }
        .ok_or_else(|| {
            SkillDocumentError::new("max_bytes_splits_utf8", max_bytes_value.to_string())
        })?;

        let line_starts: Vec<usize> = self.lines.iter().map(|line| line.start).collect();
        let line_start = if line_starts.is_empty() {
            None
        } else {
            Some(line_starts.partition_point(|line_start| *line_start <= start))
        };
        let line_end = if line_starts.is_empty() {
            None
        } else {
            Some(line_starts.partition_point(|line_start| *line_start < end))
        };

        Ok(DocumentChunk {
            path: path_as_posix(&self.path),
            heading: selected.map(|item| item.heading.clone()),
            line_start,
            line_end,
            byte_start: start,
            byte_end: end,
            next_offset: end,
            section_eof: end >= section_end,
            file_eof: end >= self.data.len(),
            text,
        })
    }

    pub fn read_section(
        &self,
        heading: &str,
        max_bytes: i128,
    ) -> Result<Vec<DocumentChunk>, SkillDocumentError> {
        let selected = self.find_heading(heading)?;
        let section_start = selected.byte_start;
        let section_end = selected.section_end;
        let selected_heading = selected.heading.clone();
        let mut chunks = Vec::new();
        let mut offset = section_start as i128;
        while offset < section_end as i128 {
            let current = self.chunk(Some(&selected_heading), offset, max_bytes)?;
            if current.next_offset <= offset as usize {
                return Err(SkillDocumentError::new(
                    "read_incomplete",
                    path_as_posix(&self.path),
                ));
            }
            offset = current.next_offset as i128;
            chunks.push(current);
        }
        Ok(chunks)
    }

    pub fn read_document(&self, max_bytes: i128) -> Result<String, SkillDocumentError> {
        let mut chunks = Vec::new();
        let mut offset = 0i128;
        loop {
            let chunk = self.chunk(None, offset, max_bytes)?;
            if chunk.byte_start as i128 != offset || chunk.next_offset as i128 <= offset {
                return Err(SkillDocumentError::new(
                    "read_incomplete",
                    path_as_posix(&self.path),
                ));
            }
            let file_eof = chunk.file_eof;
            let byte_end = chunk.byte_end;
            offset = chunk.next_offset as i128;
            chunks.push(chunk.text);
            if file_eof {
                if byte_end != self.data.len() {
                    return Err(SkillDocumentError::new(
                        "read_incomplete",
                        path_as_posix(&self.path),
                    ));
                }
                let mut document = String::new();
                for text in chunks {
                    document.push_str(&text);
                }
                return Ok(document);
            }
        }
    }
}

pub fn admit_implementation_read(
    owner_sections: &[(PathBuf, String)],
    max_bytes: i128,
) -> Result<SkillReadAdmission, SkillDocumentError> {
    let mut owner_chunks = Vec::with_capacity(owner_sections.len());
    for (owner_path, owner_heading) in owner_sections {
        let reader = SkillDocumentReader::new(owner_path)?;
        let chunks = reader.read_section(owner_heading, max_bytes)?;
        let last = chunks
            .last()
            .cloned()
            .ok_or_else(|| SkillDocumentError::new("read_incomplete", path_as_posix(owner_path)))?;
        owner_chunks.push(last);
    }
    let implementation_read = implementation_read_state(
        &owner_chunks
            .iter()
            .map(|chunk| chunk.section_eof)
            .collect::<Vec<_>>(),
    )
    .to_owned();
    Ok(SkillReadAdmission {
        owner_sections: owner_chunks,
        implementation_read,
    })
}

pub fn implementation_read_state(owner_section_eofs: &[bool]) -> &'static str {
    if !owner_section_eofs.is_empty() && owner_section_eofs.iter().all(|eof| *eof) {
        "ready"
    } else {
        "locked"
    }
}

fn path_as_posix(path: &Path) -> String {
    if path.as_os_str().is_empty() {
        return ".".to_owned();
    }
    let absolute = path.is_absolute();
    let components = path
        .components()
        .filter_map(|component| match component {
            std::path::Component::CurDir | std::path::Component::RootDir => None,
            _ => Some(component.as_os_str().to_string_lossy().into_owned()),
        })
        .collect::<Vec<_>>();
    if absolute {
        format!("/{}", components.join("/"))
    } else if components.is_empty() {
        ".".to_owned()
    } else {
        components.join("/")
    }
}

fn line_table(data: &[u8]) -> Result<Vec<Line>, SkillDocumentError> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut index = 0;
    while index < data.len() {
        let end = match data[index] {
            b'\n' => Some(index + 1),
            b'\r' if data.get(index + 1) == Some(&b'\n') => Some(index + 2),
            b'\r' => Some(index + 1),
            _ => None,
        };
        if let Some(end) = end {
            lines.push(line_from_bytes(data, start, end)?);
            start = end;
            index = end;
        } else {
            index += 1;
        }
    }
    if start < data.len() {
        lines.push(line_from_bytes(data, start, data.len())?);
    }
    Ok(lines)
}

fn line_from_bytes(data: &[u8], start: usize, end: usize) -> Result<Line, SkillDocumentError> {
    let text = std::str::from_utf8(&data[start..end])
        .map_err(|_| SkillDocumentError::new("invalid_utf8", format!("byte={start}")))?;
    Ok(Line {
        start,
        end,
        text: text.to_owned(),
    })
}

fn index_headings(lines: &[Line], file_end: usize) -> Vec<Heading> {
    let mut headings = Vec::new();
    let mut fence: Option<char> = None;
    for (index, line) in lines.iter().enumerate() {
        let stripped = line.text.trim();
        if stripped.starts_with("```") || stripped.starts_with("~~~") {
            let marker = stripped.chars().next().expect("fence marker is nonempty");
            if fence.is_none() {
                fence = Some(marker);
            } else if fence == Some(marker) {
                fence = None;
            }
            continue;
        }
        if fence.is_some() {
            continue;
        }
        if let Some((heading, title, level)) = heading_from_line(&line.text) {
            headings.push(Heading {
                heading,
                title,
                level,
                line: index + 1,
                byte_start: line.start,
                byte_end: line.end,
                section_end: file_end,
            });
        }
    }
    for index in 0..headings.len().saturating_sub(1) {
        headings[index].section_end = headings[index + 1].byte_start;
    }
    headings
}

fn heading_from_line(line: &str) -> Option<(String, String, usize)> {
    let line = line.trim_end_matches(|character| matches!(character, '\r' | '\n'));
    let leading_spaces = line.bytes().take_while(|byte| *byte == b' ').count();
    if leading_spaces > 3 {
        return None;
    }
    let tail = &line[leading_spaces..];
    let level = tail.bytes().take_while(|byte| *byte == b'#').count();
    if !(1..=6).contains(&level) {
        return None;
    }
    let rest = &tail[level..];
    let title_part = if rest.is_empty() {
        ""
    } else if rest.starts_with(' ') || rest.starts_with('\t') {
        rest.trim_start_matches(|character| matches!(character, ' ' | '\t'))
    } else {
        return None;
    };
    let mut title = title_part.trim().to_owned();
    let without_trailing_whitespace =
        title.trim_end_matches(|character| matches!(character, ' ' | '\t'));
    let trailing_hashes = without_trailing_whitespace
        .bytes()
        .rev()
        .take_while(|byte| *byte == b'#')
        .count();
    if trailing_hashes > 0 {
        let marker_start = without_trailing_whitespace.len() - trailing_hashes;
        let prefix = &without_trailing_whitespace[..marker_start];
        let separating_whitespace = prefix
            .bytes()
            .rev()
            .take_while(|byte| matches!(byte, b' ' | b'\t'))
            .count();
        if separating_whitespace > 0 {
            title = prefix[..prefix.len() - separating_whitespace]
                .trim_end()
                .to_owned();
        }
    }
    let heading = if title.is_empty() {
        "#".repeat(level)
    } else {
        format!("{} {title}", "#".repeat(level))
    };
    Some((heading, title, level))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OutputFormat {
    Json,
    Text,
}

#[derive(Debug)]
struct CliArgs {
    command: String,
    path: Option<PathBuf>,
    heading: Option<String>,
    offset: i128,
    max_bytes: i128,
    owners: Vec<String>,
    format: OutputFormat,
}

enum CliResult {
    Index(Vec<Heading>),
    Chunk(DocumentChunk),
    Admission(SkillReadAdmission),
}

pub fn run(args: &[String]) -> i32 {
    let parsed = match parse_args(args) {
        Ok(Some(parsed)) => parsed,
        Ok(None) => {
            println!("{}", help_text());
            return 0;
        }
        Err(message) => return argument_error(&message),
    };
    let result = match execute(&parsed) {
        Ok(result) => result,
        Err(error) => {
            eprintln!(
                "SKILL_DOCUMENT_READER_ERROR={}:{}",
                error.code, error.detail
            );
            return 2;
        }
    };
    match render(&result, parsed.format) {
        Ok(output) => {
            println!("{output}");
            0
        }
        Err(error) => {
            eprintln!("SKILL_DOCUMENT_READER_ERROR=serialization_failed:{error}");
            2
        }
    }
}

fn execute(args: &CliArgs) -> Result<CliResult, SkillDocumentError> {
    match args.command.as_str() {
        "index" => {
            let path = args
                .path
                .as_ref()
                .ok_or_else(|| SkillDocumentError::new("path_required", ""))?;
            Ok(CliResult::Index(
                SkillDocumentReader::new(path)?.index().to_vec(),
            ))
        }
        "chunk" => {
            let path = args
                .path
                .as_ref()
                .ok_or_else(|| SkillDocumentError::new("path_required", ""))?;
            let reader = SkillDocumentReader::new(path)?;
            Ok(CliResult::Chunk(reader.chunk(
                args.heading.as_deref(),
                args.offset,
                args.max_bytes,
            )?))
        }
        "admit" => {
            let owner_sections = args
                .owners
                .iter()
                .map(|value| parse_owner_spec(value))
                .collect::<Result<Vec<_>, _>>()?;
            Ok(CliResult::Admission(admit_implementation_read(
                &owner_sections,
                args.max_bytes,
            )?))
        }
        _ => unreachable!("command choices are validated by parse_args"),
    }
}

fn parse_owner_spec(value: &str) -> Result<(PathBuf, String), SkillDocumentError> {
    let (path, heading) = value
        .split_once('#')
        .ok_or_else(|| SkillDocumentError::new("invalid_owner_section", value))?;
    if path.is_empty() || heading.trim().is_empty() {
        return Err(SkillDocumentError::new("invalid_owner_section", value));
    }
    Ok((PathBuf::from(path), heading.trim().to_owned()))
}

fn render(result: &CliResult, output_format: OutputFormat) -> Result<String, serde_json::Error> {
    match (result, output_format) {
        (CliResult::Index(headings), OutputFormat::Json) => serde_json::to_string(headings),
        (CliResult::Index(headings), OutputFormat::Text) => serde_json::to_string_pretty(headings),
        (CliResult::Chunk(chunk), OutputFormat::Json) => serde_json::to_string(chunk),
        (CliResult::Chunk(chunk), OutputFormat::Text) => Ok(render_chunk_text(chunk)?),
        (CliResult::Admission(admission), OutputFormat::Json) => {
            serde_json::to_string(&AdmissionProjection {
                owner_sections: admission
                    .owner_sections
                    .iter()
                    .map(DocumentChunk::metadata)
                    .collect(),
                implementation_read: &admission.implementation_read,
            })
        }
        (CliResult::Admission(admission), OutputFormat::Text) => {
            let owner_sections = admission
                .owner_sections
                .iter()
                .map(|chunk| serde_json::to_string(&chunk.metadata()))
                .collect::<Result<Vec<_>, _>>()?
                .join(", ");
            Ok(format!(
                "owner_sections=[{owner_sections}]\nimplementation_read={}",
                serde_json::to_string(&admission.implementation_read)?
            ))
        }
    }
}

fn render_chunk_text(chunk: &DocumentChunk) -> Result<String, serde_json::Error> {
    Ok(format!(
        "path={}\nheading={}\nline_start={}\nline_end={}\nbyte_start={}\nbyte_end={}\nnext_offset={}\nsection_eof={}\nfile_eof={}\ntext={}",
        serde_json::to_string(&chunk.path)?,
        serde_json::to_string(&chunk.heading)?,
        serde_json::to_string(&chunk.line_start)?,
        serde_json::to_string(&chunk.line_end)?,
        chunk.byte_start,
        chunk.byte_end,
        chunk.next_offset,
        chunk.section_eof,
        chunk.file_eof,
        serde_json::to_string(&chunk.text)?
    ))
}

fn parse_args(args: &[String]) -> Result<Option<CliArgs>, String> {
    let mut command = None;
    let mut path = None;
    let mut heading = None;
    let mut offset = 0i128;
    let mut max_bytes = DEFAULT_MAX_BYTES;
    let mut owners = Vec::new();
    let mut output_format = OutputFormat::Json;
    let mut unknown: Vec<String> = Vec::new();
    let mut index = 0;
    let mut positional_only = false;
    while index < args.len() {
        let argument = &args[index];
        if !positional_only && (argument == "-h" || argument == "--help") {
            return Ok(None);
        }
        if !positional_only && argument == "--" {
            positional_only = true;
            index += 1;
            continue;
        }
        if !positional_only && argument.starts_with('-') {
            let (name, inline_value) = argument
                .split_once('=')
                .map_or((argument.as_str(), None), |(name, value)| {
                    (name, Some(value))
                });
            if matches!(
                name,
                "--path" | "--heading" | "--offset" | "--max-bytes" | "--owner" | "--format"
            ) {
                let value = match inline_value {
                    Some(value) => value.to_owned(),
                    None => {
                        let next = args
                            .get(index + 1)
                            .ok_or_else(|| format!("argument {name}: expected one argument"))?;
                        if next.starts_with('-')
                            && !((name == "--offset" || name == "--max-bytes")
                                && next.parse::<i128>().is_ok())
                        {
                            return Err(format!("argument {name}: expected one argument"));
                        }
                        index += 1;
                        next.to_owned()
                    }
                };
                match name {
                    "--path" => path = Some(PathBuf::from(value)),
                    "--heading" => heading = Some(value),
                    "--offset" => {
                        offset = value.parse().map_err(|_| {
                            format!("argument --offset: invalid int value: '{value}'")
                        })?;
                    }
                    "--max-bytes" => {
                        max_bytes = value.parse().map_err(|_| {
                            format!("argument --max-bytes: invalid int value: '{value}'")
                        })?;
                    }
                    "--owner" => owners.push(value),
                    "--format" => {
                        output_format = match value.as_str() {
                            "json" => OutputFormat::Json,
                            "text" => OutputFormat::Text,
                            _ => {
                                return Err(format!(
                                    "argument --format: invalid choice: '{value}' (choose from 'json', 'text')"
                                ));
                            }
                        };
                    }
                    _ => unreachable!(),
                }
            } else {
                unknown.push(argument.to_owned());
            }
        } else if command.is_none() {
            command = Some(argument.clone());
        } else {
            unknown.push(argument.to_owned());
        }
        index += 1;
    }
    let command =
        command.ok_or_else(|| "the following arguments are required: command".to_owned())?;
    if !matches!(command.as_str(), "index" | "chunk" | "admit") {
        return Err(format!(
            "argument command: invalid choice: '{command}' (choose from 'index', 'chunk', 'admit')"
        ));
    }
    if !unknown.is_empty() {
        return Err(format!("unrecognized arguments: {}", unknown.join(" ")));
    }
    Ok(Some(CliArgs {
        command,
        path,
        heading,
        offset,
        max_bytes,
        owners,
        format: output_format,
    }))
}

fn argument_error(message: &str) -> i32 {
    eprintln!("usage: agent-canon skill-document-reader [-h] {{index,chunk,admit}} [options]");
    eprintln!("agent-canon skill-document-reader: error: {message}");
    2
}

fn help_text() -> &'static str {
    "usage: agent-canon skill-document-reader [-h] {index,chunk,admit} [options]\n\nRead selected Skill sections or canonical bodies through bounded UTF-8 chunks.\n\npositional arguments:\n  {index,chunk,admit}\n    index               list headings\n    chunk               return one bounded chunk\n    admit               report current owner-section EOF metadata\n\noptions:\n  -h, --help            show this help message and exit\n  --path PATH           Markdown document path\n  --heading HEADING     exact heading or unique heading title\n  --offset OFFSET       zero-based file byte offset\n  --max-bytes MAX_BYTES\n  --owner PATH#HEADING  current common or active branch section\n  --format {json,text}\n"
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static NEXT_DIRECTORY: AtomicUsize = AtomicUsize::new(0);

    struct TestDirectory(PathBuf);

    impl TestDirectory {
        fn new() -> Self {
            loop {
                let path = std::env::temp_dir().join(format!(
                    "agent-canon-skill-reader-{}-{}",
                    std::process::id(),
                    NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed)
                ));
                match fs::create_dir(&path) {
                    Ok(()) => return Self(path),
                    Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                    Err(error) => panic!("create fixture directory: {error}"),
                }
            }
        }

        fn write(&self, name: &str, contents: impl AsRef<[u8]>) -> PathBuf {
            let path = self.0.join(name);
            fs::write(&path, contents).expect("write fixture");
            path
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn index_ignores_fenced_headings_and_computes_section_end() {
        let directory = TestDirectory::new();
        let path = directory.write(
            "skill.md",
            "# Intro\n```text\n## hidden\n```\n## Details\nbody\n### Nested\nchild\n## End\nend\n",
        );
        let reader = SkillDocumentReader::new(path).unwrap();

        assert_eq!(
            reader
                .index()
                .iter()
                .map(|heading| heading.heading.as_str())
                .collect::<Vec<_>>(),
            vec!["# Intro", "## Details", "### Nested", "## End"]
        );
        assert_eq!(reader.index()[1].section_end, reader.index()[2].byte_start);
        assert_eq!(reader.index()[2].section_end, reader.index()[3].byte_start);
    }

    #[test]
    fn section_chunks_are_bounded_and_continue_to_section_eof() {
        let directory = TestDirectory::new();
        let path = directory.write("skill.md", "## Details\n0123456789\nabcdefghij\n## End\n");
        let reader = SkillDocumentReader::new(path).unwrap();

        let chunks = reader.read_section("## Details", 9).unwrap();

        assert!(chunks.len() > 2);
        assert!(!chunks[0].section_eof);
        assert!(chunks.last().unwrap().section_eof);
        assert!(!chunks.last().unwrap().file_eof);
        assert_eq!(
            chunks
                .iter()
                .map(|chunk| chunk.text.as_str())
                .collect::<Vec<_>>()
                .join(""),
            "## Details\n0123456789\nabcdefghij\n"
        );
        assert_eq!(
            chunks[..chunks.len() - 1]
                .iter()
                .map(|chunk| chunk.next_offset)
                .collect::<Vec<_>>(),
            chunks[1..]
                .iter()
                .map(|chunk| chunk.byte_start)
                .collect::<Vec<_>>()
        );
    }

    #[test]
    fn read_document_delivers_all_content_through_file_eof() {
        let expected = "# Skill\nintro あいうえお\n## Branch\nselected body\n";
        let directory = TestDirectory::new();
        let path = directory.write("skill.md", expected);
        let reader = SkillDocumentReader::new(&path).unwrap();

        let actual = reader.read_document(7).unwrap();

        assert_eq!(actual, expected);
        assert_eq!(actual.as_bytes(), fs::read(path).unwrap().as_slice());
    }

    #[test]
    fn utf8_boundary_never_splits_multibyte_character() {
        let directory = TestDirectory::new();
        let path = directory.write("skill.md", "## 詳細\nあいうえお\n");
        let reader = SkillDocumentReader::new(path).unwrap();
        let heading = reader.find_heading("詳細").unwrap();
        let max_bytes = (heading.byte_end - heading.byte_start + 2) as i128;

        let chunk = reader.chunk(Some(&heading.heading), 0, max_bytes).unwrap();

        assert!(chunk.byte_end - chunk.byte_start <= max_bytes as usize);
        assert_eq!(
            chunk.text.as_bytes(),
            &reader.data[chunk.byte_start..chunk.byte_end]
        );
        assert_eq!(
            std::str::from_utf8(&reader.data[chunk.byte_start..chunk.byte_end]).unwrap(),
            chunk.text
        );
    }

    #[test]
    fn file_eof_is_distinct_from_section_eof() {
        let directory = TestDirectory::new();
        let path = directory.write("skill.md", "## First\none\n## Last\n最後\n");
        let reader = SkillDocumentReader::new(path).unwrap();

        let first = reader.read_section("First", 100).unwrap().pop().unwrap();
        let last = reader.read_section("Last", 100).unwrap().pop().unwrap();

        assert!(first.section_eof);
        assert!(!first.file_eof);
        assert!(last.section_eof);
        assert!(last.file_eof);
    }

    #[test]
    fn missing_heading_is_typed_failure() {
        let directory = TestDirectory::new();
        let path = directory.write("skill.md", "# Skill\n");
        let reader = SkillDocumentReader::new(path).unwrap();

        let error = reader
            .read_section("Missing", DEFAULT_MAX_BYTES)
            .unwrap_err();

        assert_eq!(error.code, "heading_not_found");
        assert_eq!(error.detail, "Missing");
    }

    #[test]
    fn admission_requires_only_current_section_eofs() {
        let directory = TestDirectory::new();
        let skill = directory.write("skill.md", "## Common\nconstraints\n## Later\n");
        let owner = directory.write("owner.md", "## Operation\nbody\n### Recovery\nunread\n");
        let sections = vec![
            (skill, "Common".to_owned()),
            (owner, "Operation".to_owned()),
        ];

        let result = admit_implementation_read(&sections, 8).unwrap();

        assert_eq!(result.implementation_read, "ready");
        assert_eq!(result.owner_sections.len(), 2);
        for section in result.owner_sections {
            assert!(section.section_eof);
            assert!(!section.file_eof);
        }
    }

    #[test]
    fn truncated_read_stays_locked() {
        assert_eq!(implementation_read_state(&[]), "locked");
        assert_eq!(implementation_read_state(&[false]), "locked");
        assert_eq!(implementation_read_state(&[true, false]), "locked");
        assert_eq!(implementation_read_state(&[true, true]), "ready");
        assert_eq!(
            admit_implementation_read(&[], DEFAULT_MAX_BYTES)
                .unwrap()
                .implementation_read,
            "locked"
        );
    }

    #[test]
    fn admission_projection_keeps_metadata_without_repeating_text() {
        let directory = TestDirectory::new();
        let mut text = String::new();
        for heading in ["First", "Second", "Last"] {
            text.push_str(&format!("## {heading}\n"));
            text.push_str("本文を再送しない\n".repeat(400).as_str());
        }
        let owner = directory.write("owner.md", text);
        let sections = ["First", "Second", "Last"]
            .into_iter()
            .map(|heading| (owner.clone(), heading.to_owned()))
            .collect::<Vec<_>>();
        let result = admit_implementation_read(&sections, DEFAULT_MAX_BYTES).unwrap();

        let expected = result
            .owner_sections
            .iter()
            .map(|chunk| {
                let mut entry = chunk.as_json();
                let text = entry
                    .as_object_mut()
                    .unwrap()
                    .remove("text")
                    .expect("chunk serialization includes text");
                assert!(text.as_str().map_or(false, |text| !text.is_empty()));
                entry
            })
            .collect::<Vec<_>>();
        let projection = result.as_json();

        assert_eq!(projection["owner_sections"], expected);
        assert_eq!(projection["implementation_read"], "ready");
        assert_eq!(
            projection
                .as_object()
                .unwrap()
                .keys()
                .cloned()
                .collect::<Vec<_>>(),
            vec!["implementation_read", "owner_sections"]
        );
        assert_eq!(
            expected
                .iter()
                .map(|entry| entry["file_eof"].as_bool().unwrap())
                .collect::<Vec<_>>(),
            vec![false, false, true]
        );
    }

    #[test]
    fn parent_and_nested_branches_are_read_only_when_selected() {
        let directory = TestDirectory::new();
        let parts = [
            (
                "Operation",
                "## Operation\nCommon constraints; choose A or B.\n",
            ),
            ("A", "### A\nACTIVE_A\n"),
            ("Retry A", "#### Retry A\nRECOVERY_A\n"),
            ("B", "### B\nINACTIVE_B\n"),
            ("Closeout", "## Closeout\nLATER_STAGE\n"),
        ];
        let contents = parts
            .iter()
            .map(|(_, text)| *text)
            .collect::<Vec<_>>()
            .join("");
        let path = directory.write("skill.md", contents);
        let reader = SkillDocumentReader::new(path).unwrap();

        for (heading, expected) in parts {
            let chunks = reader.read_section(heading, 100_000).unwrap();
            assert_eq!(
                chunks
                    .iter()
                    .map(|chunk| chunk.text.as_str())
                    .collect::<Vec<_>>()
                    .join(""),
                expected
            );
            assert!(chunks.last().unwrap().section_eof);
            assert_eq!(chunks.last().unwrap().file_eof, heading == "Closeout");
        }
    }

    #[test]
    fn continuation_cannot_cross_into_an_unselected_child() {
        let directory = TestDirectory::new();
        let path = directory.write("skill.md", "## Common\nrules\n### Child\nbody\n");
        let reader = SkillDocumentReader::new(path).unwrap();
        let parent = reader.read_section("Common", 7).unwrap().pop().unwrap();

        assert_eq!(
            parent.next_offset,
            reader.find_heading("Child").unwrap().byte_start
        );
        let at_eof = reader
            .chunk(
                Some("Common"),
                parent.next_offset as i128,
                DEFAULT_MAX_BYTES,
            )
            .unwrap_err();
        assert_eq!(at_eof.code, "offset_at_eof");
        let after_eof = reader
            .chunk(
                Some("Common"),
                parent.next_offset as i128 + 1,
                DEFAULT_MAX_BYTES,
            )
            .unwrap_err();
        assert_eq!(after_eof.code, "offset_out_of_section");
    }

    #[test]
    fn missing_deferred_owner_is_not_opened() {
        let directory = TestDirectory::new();
        let missing = directory.0.join("deferred.md");
        let path = directory.write(
            "skill.md",
            "## Common\nrules\n### Failure\n[repair](deferred.md#Repair)\n",
        );
        let sections = vec![(path, "Common".to_owned())];

        let result = admit_implementation_read(&sections, DEFAULT_MAX_BYTES).unwrap();

        assert_eq!(result.implementation_read, "ready");
        assert!(!missing.exists());
        let error =
            admit_implementation_read(&[(missing.clone(), "Repair".to_owned())], DEFAULT_MAX_BYTES)
                .unwrap_err();
        assert_eq!(error.code, "read_failed");
        assert_eq!(error.detail, path_as_posix(&missing));
    }
}
