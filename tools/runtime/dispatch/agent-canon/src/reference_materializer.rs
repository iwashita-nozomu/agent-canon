// @dependency-start
// contract implementation
// responsibility Materializes consulted HTML and PDF references with retained external parser APIs.
// upstream design ../../../../../references/README.md external reference capture contract
// upstream implementation ../../../python-provider/src/main.rs safe parser and PDF runtime connection
// downstream test ../../../../../tests/agent_tools/test_reference_materializer.py public CLI oracles
// @dependency-end

use crate::authority::{AttestationRequest, NonEmptyTrimmedString, Nonce128, ParentRootAttestor};
use crate::python_text::{python_splitlines, python_strip};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

fn normalize(value: &str) -> String {
    let mut result = Vec::new();
    let mut previous_blank = false;
    for line in python_splitlines(value) {
        let line = line
            .split(|character: char| {
                character.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&character)
            })
            .filter(|part| !part.is_empty())
            .collect::<Vec<_>>()
            .join(" ");
        if !line.is_empty() || !previous_blank {
            result.push(line.clone());
        }
        previous_blank = line.is_empty();
    }
    python_strip(&result.join("\n")).to_owned()
}

fn provider(kind: &str, bytes: &[u8]) -> Result<Value, String> {
    let executable = std::env::var_os("AGENT_CANON_PYTHON_PROVIDER")
        .unwrap_or_else(|| "agent-canon-python-provider".into());
    let mut child = Command::new(executable)
        .arg(kind)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| error.to_string())?;
    child
        .stdin
        .take()
        .ok_or("provider stdin unavailable")?
        .write_all(bytes)
        .map_err(|error| error.to_string())?;
    let output = child
        .wait_with_output()
        .map_err(|error| error.to_string())?;
    serde_json::from_slice(&output.stdout).map_err(|error| format!("provider response: {error}"))
}

fn pdftotext(input: &Path) -> Result<Option<String>, String> {
    let mut child = match Command::new("pdftotext")
        .arg("-layout")
        .arg(input)
        .arg("-")
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(child) => child,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.to_string()),
    };
    let mut stream = child.stdout.take().ok_or("pdftotext stdout unavailable")?;
    let reader = std::thread::spawn(move || {
        let mut bytes = Vec::new();
        stream.read_to_end(&mut bytes).map(|_| bytes)
    });
    let started = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if started.elapsed() < Duration::from_secs(30) => {
                std::thread::sleep(Duration::from_millis(10))
            }
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                break None;
            }
        }
    };
    let bytes = reader
        .join()
        .map_err(|_| "pdftotext reader failed")?
        .map_err(|error| error.to_string())?;
    Ok(Some(if status.is_some_and(|status| status.success()) {
        normalize(&String::from_utf8_lossy(&bytes))
    } else {
        String::new()
    }))
}

fn relative(from: &Path, to: &Path) -> String {
    let from = from.components().collect::<Vec<_>>();
    let to = to.components().collect::<Vec<_>>();
    let shared = from.iter().zip(&to).take_while(|(a, b)| a == b).count();
    let mut result = PathBuf::new();
    for _ in shared..from.len() {
        result.push("..");
    }
    for part in &to[shared..] {
        result.push(part.as_os_str());
    }
    result.to_string_lossy().replace('\\', "/")
}

fn execute(values: &BTreeMap<String, String>, force: bool, fetch: bool) -> Result<Value, String> {
    let get = |key: &str| values.get(key).map(String::as_str).unwrap_or("");
    let root = std::fs::canonicalize(if get("--root").is_empty() {
        Path::new(".")
    } else {
        Path::new(get("--root"))
    })
    .map_err(|error| error.to_string())?;
    let url = get("--url");
    let input = if get("--input").is_empty() {
        None
    } else {
        Some(PathBuf::from(get("--input")))
    };
    let bytes = if let Some(input) = &input {
        std::fs::read(input).map_err(|error| error.to_string())?
    } else if fetch {
        let output = Command::new("curl")
            .args([
                "--fail",
                "--location",
                "--silent",
                "--show-error",
                "--max-time",
                "30",
                "--user-agent",
                "agent-canon-reference-materializer/1",
                "--url",
                url,
            ])
            .output()
            .map_err(|error| error.to_string())?;
        if !output.status.success() {
            return Err(String::from_utf8_lossy(&output.stderr).into_owned());
        }
        output.stdout
    } else {
        return Err("--input is required unless --fetch is set".into());
    };
    let source_kind = match get("--source-kind") {
        "" | "auto" => {
            if input
                .as_deref()
                .unwrap_or_else(|| Path::new(url.split(['?', '#']).next().unwrap_or(url)))
                .extension()
                .is_some_and(|suffix| suffix.to_string_lossy().eq_ignore_ascii_case("pdf"))
            {
                "pdf"
            } else {
                "html"
            }
        }
        "html" => "html",
        "pdf" => "pdf",
        _ => return Err("invalid --source-kind".into()),
    };
    let (title, text, method) = if source_kind == "html" {
        let result = provider("html-extract", &bytes)?;
        if result["status"] != "pass" {
            return Err(result["error"]
                .as_str()
                .unwrap_or("HTML extraction failed")
                .into());
        }
        (
            if get("--title").is_empty() {
                normalize(result["title"].as_str().unwrap_or(""))
            } else {
                normalize(get("--title"))
            },
            normalize(result["text"].as_str().unwrap_or("")),
            "stdlib-html-parser",
        )
    } else {
        let result = provider("pdf-extract", &bytes).ok();
        let text = result
            .as_ref()
            .filter(|value| value["status"] == "pass")
            .and_then(|value| value["text"].as_str())
            .map(normalize)
            .unwrap_or_default();
        if !text.is_empty() {
            (normalize(get("--title")), text, "pypdf")
        } else {
            let temporary;
            let input = if let Some(input) = &input {
                input.as_path()
            } else {
                temporary = tempfile::NamedTempFile::new().map_err(|error| error.to_string())?;
                temporary
                    .as_file()
                    .write_all(&bytes)
                    .map_err(|error| error.to_string())?;
                temporary.path()
            };
            let extracted = pdftotext(input)?;
            let available = extracted.is_some()
                || result
                    .as_ref()
                    .is_some_and(|value| value["available"] != false);
            let text = extracted.unwrap_or_default();
            if text.is_empty() {
                return Err(if available {
                    "pdf-text-extraction-failed: repair pypdf or pdftotext extraction"
                } else {
                    "pdf-text-extractor-required: install pypdf or pdftotext"
                }
                .into());
            }
            (normalize(get("--title")), text, "pdftotext")
        }
    };
    if title.is_empty() {
        return Err("reference title is required: pass --title or provide an HTML <title>".into());
    }
    let slug = regex::Regex::new("[^A-Za-z0-9]+")
        .unwrap()
        .replace_all(&title, "-")
        .trim_matches('-')
        .to_ascii_lowercase()
        .chars()
        .take(90)
        .collect::<String>()
        .trim_matches('-')
        .to_owned();
    let slug = if slug.is_empty() {
        "external-reference"
    } else {
        &slug
    };
    let output_dir = if get("--output-dir").is_empty() {
        PathBuf::from("references/external")
    } else {
        PathBuf::from(get("--output-dir"))
    };
    let url_digest = format!("{:x}", Sha256::digest(url.as_bytes()));
    let path = root
        .join(output_dir)
        .join(format!("{slug}-{}.md", &url_digest[..12]));
    let digest = format!("{:x}", Sha256::digest(&bytes));
    let status = if text.is_empty() { "warn" } else { "pass" };
    let extraction = if text.is_empty() {
        "metadata-only"
    } else {
        "text-extracted"
    };
    if !path.exists() || force {
        let parent = std::env::var_os("AGENT_CANON_PARENT_ROOT")
            .filter(|value| !value.is_empty())
            .ok_or("reference-materializer: explicit parent root is required")?;
        let parent = PathBuf::from(parent);
        let attested = ParentRootAttestor::new()
            .attest(&AttestationRequest {
                cwd: parent.clone(),
                explicit_root: Some(parent),
                source_root: None,
                clone_root: None,
                topic_marker: None,
                gitmodules: None,
                owner_evidence: None,
                expected_remote: None,
                expected_module_digest: None,
                child_handoff_token: None,
                purpose: NonEmptyTrimmedString::new("reference-materializer")
                    .map_err(|error| error.to_string())?,
                nonce: Nonce128::generate().map_err(|error| error.to_string())?,
            })
            .map_err(|error| error.to_string())?;
        let directory = path.parent().ok_or("output parent unavailable")?;
        let readme = relative(directory, &root.join("references/README.md"));
        let tool = relative(
            directory,
            &root.join("tools/runtime/dispatch/agent-canon/src/reference_materializer.rs"),
        );
        let mut snippet = text.chars().take(200_000).collect::<String>();
        if text.chars().count() > 200_000 {
            snippet.push_str("\n\n[Extraction truncated by reference-materializer.]");
        }
        let timestamp = OffsetDateTime::now_utc()
            .format(&Rfc3339)
            .map_err(|error| error.to_string())?;
        let snippet = if snippet.is_empty() {
            "_No text extracted. Keep this metadata record if the source was still consulted._"
        } else {
            &snippet
        };
        let rendered = format!("# {title}\n\n<!--\n@dependency-start\nresponsibility Stores extracted reference material for {url}.\nupstream design {readme} reference capture policy\nupstream implementation {tool} created this Markdown reference\n@dependency-end\n-->\n\n## Metadata\n\n- source_url: {url}\n- source_kind: {source_kind}\n- retrieved_at_utc: {timestamp}\n- content_sha256: {digest}\n- extraction_status: {extraction}\n- extraction_method: {method}\n\n## Extracted Text\n\n{snippet}\n");
        attested
            .write_parent_owned_file(
                &path,
                rendered.as_bytes(),
                NonEmptyTrimmedString::new("reference-materializer")
                    .map_err(|error| error.to_string())?,
            )
            .map_err(|error| error.to_string())?;
    }
    Ok(
        json!({"status":status,"path":relative(&root,&path),"url":url,"source_kind":source_kind,"extraction_method":method,"extraction_status":extraction,"content_sha256":digest}),
    )
}

pub fn run(args: &[String]) -> i32 {
    const OPTIONS: &[(&str, &str)] = &[
        ("--root", "--root"),
        ("--url", "--url"),
        ("--input", "--input"),
        ("--title", "--title"),
        ("--source-kind", "--source-kind"),
        ("--output-dir", "--output-dir"),
        ("--format", "--format"),
        ("--force", "--force"),
        ("--fetch", "--fetch"),
        ("--help", "--help"),
    ];
    let mut values = BTreeMap::new();
    let mut force = false;
    let mut fetch = false;
    let mut index = 0;
    while index < args.len() {
        if args[index] == "--" && index + 1 == args.len() {
            break;
        }
        let (spelling, inline) = args[index]
            .split_once('=')
            .map_or((args[index].as_str(), None), |(key, value)| {
                (key, Some(value))
            });
        let key = if spelling == "-h" {
            "--help"
        } else {
            match crate::python_cli_options::resolve_long_option_prefix(spelling, OPTIONS) {
                Ok(key) => key,
                Err(_) => {
                    eprintln!("unrecognized or ambiguous argument: {spelling}");
                    return 2;
                }
            }
        };
        if ["--force", "--fetch", "--help"].contains(&key) && inline.is_some() {
            eprintln!("{key} does not take a value");
            return 2;
        }
        match key {
            "-h" | "--help" => {
                println!("usage: agent-canon reference-materializer --url URL [--root ROOT] [--input PATH|--fetch] [--title TITLE] [--source-kind auto|pdf|html] [--output-dir PATH] [--force] [--format text|json]");
                return 0;
            }
            "--force" => force = true,
            "--fetch" => fetch = true,
            "--root" | "--url" | "--input" | "--title" | "--source-kind" | "--output-dir"
            | "--format"
                if inline.is_some() || index + 1 < args.len() =>
            {
                let value = match inline {
                    Some(value) => value.to_owned(),
                    None => {
                        index += 1;
                        args[index].clone()
                    }
                };
                values.insert(key.to_owned(), value);
            }
            _ => {
                eprintln!("unrecognized or missing argument: {key}");
                return 2;
            }
        }
        index += 1;
    }
    if !values.contains_key("--url") {
        eprintln!("--url is required");
        return 2;
    }
    if values
        .get("--source-kind")
        .is_some_and(|kind| !["auto", "pdf", "html"].contains(&kind.as_str()))
    {
        eprintln!("invalid --source-kind");
        return 2;
    }
    if values
        .get("--format")
        .is_some_and(|format| !["text", "json"].contains(&format.as_str()))
    {
        eprintln!("invalid --format");
        return 2;
    }
    match execute(&values, force, fetch) {
        Ok(result)
            if values
                .get("--format")
                .is_some_and(|format| format == "json") =>
        {
            let value = crate::python_json::parse_json(&result.to_string())
                .expect("serialized JSON result");
            let bytes = crate::python_json::python_json_pretty_ascii_bytes(&value)
                .expect("string-valued result");
            println!("{}", String::from_utf8(bytes).expect("ASCII JSON"));
            0
        }
        Ok(result) => {
            for (field, name) in [
                ("path", "PATH"),
                ("url", "URL"),
                ("source_kind", "SOURCE_KIND"),
                ("extraction_method", "EXTRACTION_METHOD"),
                ("extraction_status", "EXTRACTION_STATUS"),
                ("content_sha256", "CONTENT_SHA256"),
            ] {
                println!(
                    "REFERENCE_MATERIALIZE_{name}={}",
                    result[field].as_str().unwrap()
                );
            }
            println!(
                "REFERENCE_MATERIALIZE={}",
                result["status"].as_str().unwrap()
            );
            0
        }
        Err(error) => {
            eprintln!("REFERENCE_MATERIALIZE_ERROR={error}");
            println!("REFERENCE_MATERIALIZE=fail");
            1
        }
    }
}
