// @dependency-start
// contract implementation
// responsibility Projects existing provider comparison JSON through Quarto and offline Lychee.
// upstream design ../../../../../../documents/tools/semantic_provider_html_report.md owns report inputs and provider boundaries
// upstream implementation ../runtime_boundary.rs owns external output and no-follow publication
// downstream test ../../../../../../tests/agent_tools/test_semantic_provider_html_report.py verifies provider argv and failure stages
// @dependency-end

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn string(value: &Value) -> String {
    value
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| value.to_string())
}
fn get(value: &Value, key: &str) -> String {
    value.get(key).map(string).unwrap_or_default()
}
fn integer(value: &Value) -> i64 {
    value
        .as_i64()
        .or_else(|| value.as_f64().map(|value| value as i64))
        .or_else(|| value.as_bool().map(i64::from))
        .unwrap_or(0)
}
fn number(value: &Value) -> f64 {
    value
        .as_f64()
        .or_else(|| value.as_bool().map(|value| f64::from(u8::from(value))))
        .unwrap_or(0.)
}
fn percent(value: &Value) -> String {
    format!("{:.1}%", number(value) * 100.)
}
fn items(value: &Value) -> Vec<String> {
    value
        .as_array()
        .map(|values| {
            values
                .iter()
                .map(|value| {
                    if value.is_object() {
                        format!(
                            "rank {} score {} {}:{}:{}-{}",
                            get(value, "rank"),
                            get(value, "score"),
                            get(value, "path"),
                            get(value, "node_kind"),
                            get(value, "line_start"),
                            get(value, "line_end")
                        )
                    } else {
                        string(value)
                    }
                })
                .collect()
        })
        .unwrap_or_default()
}
fn code(value: &str) -> String {
    let value = value.replace(['\r', '\n'], " ");
    let run = value
        .split(|value| value != '`')
        .map(str::len)
        .max()
        .unwrap_or(0)
        + 1;
    let delimiter = "`".repeat(run);
    let padding = if value.starts_with(' ') || value.ends_with(' ') {
        " "
    } else {
        ""
    };
    format!("{delimiter}{padding}{value}{padding}{delimiter}")
}
fn html(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#x27;")
}
fn label(report: &Value, side: &str) -> String {
    let raw = &report[side];
    format!(
        "{} / {} / dim {}",
        if get(raw, "provider").is_empty() {
            "unknown-provider".into()
        } else {
            get(raw, "provider")
        },
        if get(raw, "model").is_empty() {
            "unknown-model".into()
        } else {
            get(raw, "model")
        },
        integer(&raw["dim"])
    )
}
fn search_recorded(report: &Value) -> bool {
    report["search"]
        .as_object()
        .is_some_and(|value| !value.is_empty())
}
fn figure(report: &Value) -> String {
    let merge = &report["merge_candidates"];
    let search = if search_recorded(report) {
        format!(
            "search overlap {}",
            percent(&report["search"]["overlap_ratio"])
        )
    } else {
        "search not recorded".into()
    };
    include_str!("assets/provider_delta.svg")
        .replace(
            "{escape_text(provider_label(left))}",
            &html(&label(report, "left")),
        )
        .replace(
            "{escape_text(provider_label(right))}",
            &html(&label(report, "right")),
        )
        .replace(
            "{len(merge.left_only)}",
            &items(&merge["left_only"]).len().to_string(),
        )
        .replace(
            "{len(merge.right_only)}",
            &items(&merge["right_only"]).len().to_string(),
        )
        .replace(
            "{escape_text(percent(merge.overlap_ratio))}",
            &percent(&merge["overlap_ratio"]),
        )
        .replace("{escape_text(search_text)}", &html(&search))
}
fn list(title: &str, values: Vec<String>) -> String {
    format!(
        "### {title}\n{}",
        if values.is_empty() {
            "- none in the reported top set".into()
        } else {
            values
                .iter()
                .map(|value| format!("- {}", code(value)))
                .collect::<Vec<_>>()
                .join("\n")
        }
    )
}
fn delta(title: &str, raw: &Value) -> String {
    format!("## {title}\n\nCounts compare top candidate keys from both providers. Overlap is shared_count divided by max(left_count, right_count).\n\n| Left count | Right count | Shared count | Overlap |\n| ---: | ---: | ---: | ---: |\n| {} | {} | {} | {} |\n\n{}\n\n{}\n\n{}",integer(&raw["left_count"]),integer(&raw["right_count"]),integer(&raw["shared_count"]),percent(&raw["overlap_ratio"]),list("Shared",items(&raw["shared"])),list("Left only",items(&raw["left_only"])),list("Right only",items(&raw["right_only"])))
}
fn markdown(report: &Value, source: &Path) -> String {
    let merge = &report["merge_candidates"];
    let mut metrics: Vec<(String, String)> = vec![
        ("merge overlap".into(), percent(&merge["overlap_ratio"])),
        (
            "merge shared".into(),
            integer(&merge["shared_count"]).to_string(),
        ),
        (
            "merge left-only".into(),
            items(&merge["left_only"]).len().to_string(),
        ),
        (
            "merge right-only".into(),
            items(&merge["right_only"]).len().to_string(),
        ),
    ];
    if search_recorded(report) {
        let search = &report["search"];
        metrics.extend([
            ("search overlap".into(), percent(&search["overlap_ratio"])),
            (
                "search shared".into(),
                integer(&search["shared_count"]).to_string(),
            ),
            (
                "search left-only".into(),
                items(&search["left_only"]).len().to_string(),
            ),
            (
                "search right-only".into(),
                items(&search["right_only"]).len().to_string(),
            ),
        ]);
    }
    let mut result=format!("Source: {}\n\n## Provider Delta To Shared Candidate Logic\n\n![Provider delta to shared candidate logic](provider-delta.svg)\n\nLLM latent vectors may change retrieval and ranking deltas. This figure keeps the decision boundary in the existing responsibility-scoped candidate logic.\n\n## Comparison Metrics\n\n| Metric | Value |\n| --- | --- |\n",code(&source.to_string_lossy()));
    for (label, value) in metrics {
        result.push_str(&format!("| {label} | {} |\n", code(&value)));
    }
    result.push_str("\n## Reader Guide\n\nInspect the primary figure first. Ratios are diagnostic overlap values: higher means the two providers returned more of the same top keys, lower means the provider changed retrieval or ranking. A lower overlap does not grant merge, deletion, labeling, or ownership authority.\n\n`candidate_logic_authority=shared_responsibility_bucket`\n\n## Provider Provenance\n\n");
    for (side, title) in [("left", "Left"), ("right", "Right")] {
        let raw = &report[side];
        result.push_str(&format!("### {title} provider\n\n- Provider: {}\n- Model: {}\n- Dimension: {}\n- Nodes: {}\n- Merge candidates: {}\n\n",code(&get(raw,"provider")),code(&get(raw,"model")),integer(&raw["dim"]),integer(&raw["nodes"]),integer(&raw["merge_candidates"])));
    }
    result.push_str(&delta("Merge Candidates", merge));
    if search_recorded(report) {
        result.push_str(&format!(
            "\n\n{}\n\n## Search Top Hits\n\n{}\n\n{}",
            delta("Search", &report["search"]),
            list("Left top hits", items(&report["search"]["left_top"])),
            list("Right top hits", items(&report["search"]["right_top"]))
        ));
    } else {
        result.push_str(
            "\n\n## Search Top Hits\n\nSearch comparison was not recorded in the input JSON.",
        );
    }
    result.push_str(&format!("\n\n## Limitations\n\nThis report renders the supplied compare-providers JSON only. It does not rerun indexing, validate candidate quality, or change semantic-index thresholds. Query text is not embedded in this report; query length was {} characters when the input recorded it.\n",integer(&report["search"]["query_chars"])));
    result
}
fn program(name: &str) -> Option<PathBuf> {
    std::env::var_os("PATH")
        .and_then(|path| {
            std::env::split_paths(&path)
                .map(|directory| directory.join(name))
                .find(|candidate| candidate.is_file())
        })
        .and_then(|path| path.canonicalize().ok())
}
fn invoke(path: &Path, args: &[String], cwd: Option<&Path>) -> std::io::Result<Output> {
    let mut command = Command::new(path);
    command.args(args);
    if let Some(cwd) = cwd {
        command.current_dir(cwd);
    }
    command.output()
}
struct Failure {
    status: &'static str,
    error: String,
    code: i32,
    fields: Value,
}
fn failure(status: &'static str, error: impl Into<String>) -> Failure {
    Failure {
        status,
        error: error.into(),
        code: 1,
        fields: json!({}),
    }
}
fn with(mut error: Failure, fields: Value) -> Failure {
    error.fields = fields;
    error
}
type Result<T> = std::result::Result<T, Failure>;
fn render(source: &Path, output: &Path, title: &str, embed: bool) -> Result<Value> {
    if !output
        .extension()
        .is_some_and(|extension| extension.eq_ignore_ascii_case("html"))
    {
        return Err(failure(
            "invalid_source",
            "--output must name an .html artifact",
        ));
    }
    let bytes = fs::read(source).map_err(|error| {
        failure(
            if error.kind() == std::io::ErrorKind::NotFound {
                "missing_asset"
            } else {
                "invalid_source"
            },
            format!("compare-providers JSON is unreadable: {error}"),
        )
    })?;
    let report: Value = serde_json::from_slice(&bytes).map_err(|error| {
        failure(
            "invalid_source",
            format!("compare-providers JSON is invalid: {error}"),
        )
    })?;
    if !report.is_object() {
        return Err(failure(
            "invalid_source",
            "compare-providers JSON must contain an object",
        ));
    }
    let svg = figure(&report);
    let frontmatter=format!("---\ntitle: {}\nformat:\n  html:\n    embed-resources: {embed}\nexecute:\n  enabled: false\n---\n\n",json!(title));
    let project = "project:\n  type: default\n";
    let source_hash = sha(&bytes);
    let config_hash = sha(format!("{project}{frontmatter}").as_bytes());
    let asset_hash = sha(svg.as_bytes());
    let provenance = json!({"source":source,"source_sha256":source_hash,"config_sha256":config_hash,"asset_sha256":asset_hash});
    let quarto = program("quarto").ok_or_else(|| {
        with(
            failure(
                "renderer_unavailable",
                "Quarto CLI is not available on PATH",
            ),
            provenance.clone(),
        )
    })?;
    let version = invoke(&quarto, &["--version".into()], None)
        .map_err(|error| failure("renderer_unavailable", error.to_string()))?;
    let pandoc = invoke(&quarto, &["pandoc".into(), "--version".into()], None)
        .map_err(|error| failure("renderer_unavailable", error.to_string()))?;
    if !version.status.success() || !pandoc.status.success() {
        let mut error = with(
            failure(
                "renderer_unavailable",
                "Quarto or its embedded Pandoc version command failed",
            ),
            provenance,
        );
        error.code = if !version.status.success() {
            version.status.code().unwrap_or(1)
        } else {
            pandoc.status.code().unwrap_or(1)
        };
        return Err(error);
    }
    let repository = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../..");
    let config = repository.join("tools/validation/documentation/config/lychee.toml");
    let lychee = program("lychee")
        .filter(|_| config.is_file())
        .ok_or_else(|| {
            with(
                failure(
                    "validation_failed",
                    "the configured offline Lychee link validator is unavailable",
                ),
                provenance.clone(),
            )
        })?;
    let temporary = tempfile::Builder::new()
        .prefix("semantic-provider-html-report-")
        .tempdir()
        .map_err(|error| failure("invalid_source", error.to_string()))?;
    let workspace = temporary.path();
    let input = workspace.join("source");
    fs::create_dir(&input).map_err(|error| failure("invalid_source", error.to_string()))?;
    let rendered = input.join("rendered");
    let document = input.join("semantic-provider-report.qmd");
    let inspection = workspace.join("quarto-inspect.json");
    for (path, bytes) in [
        (input.join("_quarto.yml"), project.as_bytes().to_vec()),
        (
            document.clone(),
            format!("{frontmatter}{}", markdown(&report, source)).into_bytes(),
        ),
        (input.join("provider-delta.svg"), svg.into_bytes()),
    ] {
        fs::write(path, bytes).map_err(|error| failure("invalid_source", error.to_string()))?;
    }
    let inspect_argv = vec![
        quarto.to_string_lossy().into_owned(),
        "inspect".into(),
        document.to_string_lossy().into(),
        inspection.to_string_lossy().into(),
    ];
    let inspected = invoke(&quarto, &inspect_argv[1..], Some(&input))
        .map_err(|error| failure("renderer_unavailable", error.to_string()))?;
    if !inspected.status.success() {
        let mut error = with(
            failure(
                "invalid_source",
                "Quarto inspect rejected the generated source or configuration",
            ),
            provenance,
        );
        error.code = inspected.status.code().unwrap_or(1);
        return Err(error);
    }
    let inspected: Value = serde_json::from_slice(
        &fs::read(&inspection).map_err(|error| failure("invalid_source", error.to_string()))?,
    )
    .map_err(|error| failure("invalid_source", error.to_string()))?;
    let resources = inspected["resources"].as_array().ok_or_else(|| {
        failure(
            "invalid_source",
            "Quarto inspect did not return its resource list",
        )
    })?;
    for resource in resources {
        let resource = resource.as_str().ok_or_else(|| {
            failure(
                "invalid_source",
                "Quarto inspect returned an unsupported resource entry",
            )
        })?;
        if resource.starts_with("//")
            || resource.starts_with("http:")
            || resource.starts_with("https:")
        {
            return Err(failure(
                "validation_failed",
                "generated report resources must be local to keep rendering offline",
            ));
        }
        let path = Path::new(resource);
        if !(if path.is_absolute() {
            path.into()
        } else {
            input.join(path)
        })
        .is_file()
        {
            return Err(failure(
                "missing_asset",
                "Quarto source has a missing local report asset",
            ));
        }
    }
    let name = output
        .file_name()
        .unwrap_or_default()
        .to_string_lossy()
        .into_owned();
    let render_argv = vec![
        quarto.to_string_lossy().into_owned(),
        "render".into(),
        document.to_string_lossy().into(),
        "--to".into(),
        "html".into(),
        "--output".into(),
        name.clone(),
        "--output-dir".into(),
        "rendered".into(),
        "--no-execute".into(),
    ];
    let result = invoke(&quarto, &render_argv[1..], Some(&input))
        .map_err(|error| failure("renderer_unavailable", error.to_string()))?;
    if !result.status.success() {
        let mut error = with(
            failure("render_failed", "Quarto render returned a failure status"),
            provenance,
        );
        error.code = result.status.code().unwrap_or(1);
        return Err(error);
    }
    let html = rendered.join(&name);
    if !html.is_file() {
        return Err(failure(
            "render_failed",
            "Quarto returned success without producing the requested HTML file",
        ));
    }
    let link_argv = vec![
        lychee.to_string_lossy().into_owned(),
        "--config".into(),
        config.to_string_lossy().into(),
        "--no-progress".into(),
        html.to_string_lossy().into(),
    ];
    let checked = invoke(&lychee, &link_argv[1..], Some(&rendered))
        .map_err(|error| failure("validation_failed", error.to_string()))?;
    if !checked.status.success() {
        let mut error = failure(
            "validation_failed",
            "Lychee rejected a local link or asset in the rendered HTML",
        );
        error.code = checked.status.code().unwrap_or(1);
        return Err(error);
    }
    let output_root = agent_canon::source_mutation::ensure_file_parent_nofollow(output)
        .map_err(|error| failure("validation_failed", error.to_string()))?;
    let mut output_files = Vec::new();
    let mut stack = vec![rendered.clone()];
    while let Some(directory) = stack.pop() {
        for entry in fs::read_dir(directory)
            .map_err(|error| failure("validation_failed", error.to_string()))?
        {
            let entry = entry.map_err(|error| failure("validation_failed", error.to_string()))?;
            if entry
                .file_type()
                .map_err(|error| failure("validation_failed", error.to_string()))?
                .is_dir()
            {
                stack.push(entry.path());
            } else {
                output_files.push(entry.path());
            }
        }
    }
    let allowed: Vec<_> = output_files
        .iter()
        .map(|path| {
            path.strip_prefix(&rendered)
                .unwrap()
                .to_string_lossy()
                .replace('\\', "/")
        })
        .collect();
    let boundary=agent_canon::source_mutation::SourceMutationCapability::from_json(&output_root,Some(&json!({"allowed_paths":allowed,"purpose":"semantic provider report output","authority":"explicit output argument"}).to_string())).map_err(|error|failure("validation_failed",error.to_string()))?;
    let mut assets = Vec::new();
    for path in output_files.into_iter().filter(|path| path != &html) {
        let relative = path.strip_prefix(&rendered).unwrap();
        let destination = output_root.join(relative);
        boundary
            .copy_file_from_root_with_metadata(&rendered, &path, &destination)
            .map_err(|error| failure("validation_failed", error.to_string()))?;
        let hash = sha(&fs::read(&destination)
            .map_err(|error| failure("validation_failed", error.to_string()))?);
        if hash
            != sha(&fs::read(&path)
                .map_err(|error| failure("validation_failed", error.to_string()))?)
        {
            return Err(failure(
                "validation_failed",
                "rendered asset readback differs after writing",
            ));
        }
        assets.push(json!({"path":destination,"sha256":hash}));
    }
    boundary
        .copy_file_from_root_with_metadata(&rendered, &html, &output_root.join(&name))
        .map_err(|error| failure("validation_failed", error.to_string()))?;
    let output_hash =
        sha(&fs::read(output).map_err(|error| failure("validation_failed", error.to_string()))?);
    assets.sort_by_key(|value| get(value, "path"));
    Ok(
        json!({"status":"rendered","source":source,"source_sha256":source_hash,"config_sha256":config_hash,"configuration":{"title":title,"project":{"type":"default"},"format":"html","embed-resources":embed,"execute":{"enabled":false}},"asset_sha256":asset_hash,"quarto_version":String::from_utf8_lossy(&version.stdout).trim(),"pandoc_version":String::from_utf8_lossy(&pandoc.stdout).trim(),"inspect_argv":inspect_argv,"argv":render_argv,"exit_code":0,"output":output,"output_sha256":output_hash,"assets":assets,"resources":resources,"link_check_argv":link_argv,"validation":{"quarto_inspect":"pass","local_resources":"pass","lychee":"pass"}}),
    )
}
pub fn run(args: &[String]) -> i32 {
    const USAGE:&str="usage: agent-canon semantic-provider-html-report --compare-json PATH --output PATH [--title TEXT] [--embed-resources]";
    let mut source = None;
    let mut output = None;
    let mut title = "Semantic Provider Comparison";
    let mut embed = false;
    let mut index = 0;
    while index < args.len() {
        let name = args[index].as_str();
        if ["--help", "-h"].contains(&name) {
            println!("{USAGE}");
            return 0;
        }
        if name == "--embed-resources" {
            embed = true;
            index += 1;
            continue;
        }
        if index + 1 == args.len() {
            eprintln!("{USAGE}");
            return 2;
        }
        match name {
            "--compare-json" => source = Some(Path::new(&args[index + 1])),
            "--output" => output = Some(Path::new(&args[index + 1])),
            "--title" => title = &args[index + 1],
            _ => {
                eprintln!("{USAGE}");
                return 2;
            }
        }
        index += 2;
    }
    let (Some(source), Some(output)) = (source, output) else {
        eprintln!("{USAGE}");
        return 2;
    };
    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let source = if source.is_absolute() {
        source.into()
    } else {
        cwd.join(source)
    };
    let output = if output.is_absolute() {
        output.into()
    } else {
        cwd.join(output)
    };
    match render(&source, &output, title, embed) {
        Ok(value) => {
            println!(
                "SEMANTIC_PROVIDER_HTML_REPORT={}\nSEMANTIC_PROVIDER_HTML_REPORT_RESULT={value}",
                output.display()
            );
            0
        }
        Err(error) => {
            let mut value = error.fields;
            let object = value.as_object_mut().unwrap();
            object.insert("status".into(), json!(error.status));
            object.insert("error".into(), json!(error.error));
            object.insert("exit_code".into(), json!(error.code));
            println!("SEMANTIC_PROVIDER_HTML_REPORT_RESULT={value}");
            error.code.max(1)
        }
    }
}
