// @dependency-start
// contract implementation
// responsibility Measures the compressed size of selected Git snapshot contents.
// upstream design ../../../../../documents/tools/code_complexity.md input and measurement contract
// upstream implementation git_dependency_diff_summary.rs shared Git output adapters
// @dependency-end

use agent_canon::git_dependency_diff_summary::git_stdout;
use flate2::{write::GzEncoder, Compression};
use serde::Serialize;
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

const HELP: &str = "Usage: agent-canon code-complexity [--root ROOT] [--base REV] \
[--target REV] [-- PATH ...]\n\n\
Measure the gzip description length of committed file contents. The target defaults to HEAD.\n\
Supply --base to compare two snapshots with the same repository-relative paths.\n\
Output is JSON. A successful measurement has exit status 0 regardless of the delta.";

struct Options<'a> {
    root: PathBuf,
    base: Option<&'a str>,
    target: &'a str,
    paths: &'a [String],
}

impl<'a> Options<'a> {
    fn parse(args: &'a [String]) -> Result<Self, String> {
        let mut options = Self {
            root: PathBuf::from("."),
            base: None,
            target: "HEAD",
            paths: &[],
        };
        let mut remaining = args.iter();
        while let Some(argument) = remaining.next() {
            let value = || format!("{argument} requires a value");
            match argument.as_str() {
                "--" => {
                    options.paths = remaining.as_slice();
                    break;
                }
                "--root" => options.root = PathBuf::from(remaining.next().ok_or_else(value)?),
                "--base" => options.base = Some(remaining.next().ok_or_else(value)?),
                "--target" => options.target = remaining.next().ok_or_else(value)?,
                _ => return Err(format!("unexpected argument {argument:?}")),
            }
        }
        Ok(options)
    }
}

#[derive(Serialize)]
struct Snapshot {
    commit: String,
    files: u64,
    source_bytes: u64,
    gzip_bytes: u64,
}

#[derive(Serialize)]
struct Delta {
    files: i128,
    source_bytes: i128,
    gzip_bytes: i128,
}

#[derive(Serialize)]
struct Report<'a> {
    schema: &'static str,
    method: &'static str,
    paths: &'a [String],
    target: Snapshot,
    base: Option<Snapshot>,
    delta: Option<Delta>,
}

#[derive(Default)]
struct ByteCount(u64);

impl Write for ByteCount {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.0 += bytes.len() as u64;
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn measure(root: &Path, revision: &str, paths: &[String]) -> Result<Snapshot, String> {
    let commit = git_stdout(
        root,
        &[
            "--no-replace-objects".into(),
            "rev-parse".into(),
            "--verify".into(),
            "--end-of-options".into(),
            format!("{revision}^{{commit}}"),
        ],
    )?
    .trim()
    .to_owned();
    let mut args = vec![
        "--no-replace-objects".into(),
        "--literal-pathspecs".into(),
        "ls-tree".into(),
        "-rz".into(),
        "--full-tree".into(),
        "--format=%(objectmode) %(objectname)".into(),
        commit.clone(),
        "--".into(),
    ];
    args.extend_from_slice(paths);
    let entries = git_stdout(root, &args)?;
    let blobs = entries.split_terminator('\0').filter_map(|entry| {
        let (mode, object) = entry.split_once(' ')?;
        matches!(mode, "100644" | "100755").then_some(object)
    });

    let mut child = Command::new("git")
        .args(["--no-replace-objects", "cat-file", "--batch"])
        .current_dir(root)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .map_err(|error| format!("unable to start git cat-file: {error}"))?;
    let stdin = child.stdin.take().expect("piped child stdin");
    let stdout = child.stdout.take().expect("piped child stdout");
    let result = compress_blobs(stdin, BufReader::new(stdout), blobs);
    if result.is_err() {
        let _ = child.kill();
    }
    let status = child.wait();
    let (files, source_bytes, gzip_bytes) = result.map_err(|error| error.to_string())?;
    if !status.map_err(|error| error.to_string())?.success() {
        return Err("git cat-file failed".into());
    }
    Ok(Snapshot {
        commit,
        files,
        source_bytes,
        gzip_bytes,
    })
}

fn compress_blobs<'a>(
    mut requests: impl Write,
    mut responses: impl BufRead,
    blobs: impl Iterator<Item = &'a str>,
) -> io::Result<(u64, u64, u64)> {
    let mut encoder = GzEncoder::new(ByteCount::default(), Compression::new(6));
    let mut header = String::new();
    let mut files = 0;
    let mut source_bytes = 0;
    for object in blobs {
        writeln!(requests, "{object}")?;
        header.clear();
        responses.read_line(&mut header)?;
        // The batch response is "<object> blob <size>\n", followed by <size> bytes and a newline.
        let size = header
            .split_ascii_whitespace()
            .nth(2)
            .and_then(|size| size.parse::<u64>().ok())
            .ok_or_else(|| {
                io::Error::other(format!("cannot read Git blob {object}: {header:?}"))
            })?;
        encoder.write_all(&size.to_le_bytes())?;
        let copied = io::copy(&mut responses.by_ref().take(size), &mut encoder)?;
        let mut delimiter = [0];
        responses.read_exact(&mut delimiter)?;
        if copied != size || delimiter != [b'\n'] {
            return Err(io::Error::other(format!("invalid Git blob frame {object}")));
        }
        source_bytes += size;
        files += 1;
    }
    Ok((files, source_bytes, encoder.finish()?.0))
}

fn report(options: Options<'_>) -> Result<Report<'_>, String> {
    let target = measure(&options.root, options.target, options.paths)?;
    let base = options
        .base
        .map(|revision| measure(&options.root, revision, options.paths))
        .transpose()?;
    let delta = base.as_ref().map(|base| Delta {
        files: i128::from(target.files) - i128::from(base.files),
        source_bytes: i128::from(target.source_bytes) - i128::from(base.source_bytes),
        gzip_bytes: i128::from(target.gzip_bytes) - i128::from(base.gzip_bytes),
    });
    Ok(Report {
        schema: "agent_canon.code_complexity.v1",
        method: "gzip-level-6-git-blob-length-prefix-v1",
        paths: options.paths,
        target,
        base,
        delta,
    })
}

pub fn run(args: &[String]) -> i32 {
    if matches!(args, [arg] if matches!(arg.as_str(), "--help" | "-h")) {
        println!("{HELP}");
        return 0;
    }
    let result = Options::parse(args).and_then(report).and_then(|report| {
        let mut stdout = io::stdout().lock();
        serde_json::to_writer_pretty(&mut stdout, &report).map_err(|error| error.to_string())?;
        writeln!(stdout).map_err(|error| error.to_string())
    });
    if let Err(error) = result {
        eprintln!("code-complexity: {error}");
        return 2;
    }
    0
}
