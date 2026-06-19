// @dependency-start
// contract implementation
// responsibility Structures text output from python-structure-hash without dropping raw finding data.
// upstream implementation python_structure_hash.rs emits PY_STRUCTURE_HASH_FINDING lines
// downstream implementation main.rs exposes this parser through the AgentCanon Rust CLI
// @dependency-end

use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};

use crate::python_module_groups::{group_for_path, load_default_contract, ModuleGroupContract};

const INTERNAL_STRUCT_INLINE_FIELD_LIMIT: usize = 6;

#[derive(Debug, PartialEq, Eq)]
struct Args {
    input: Option<PathBuf>,
    output: Option<PathBuf>,
    root: PathBuf,
}

#[derive(Debug, PartialEq, Eq)]
struct Finding {
    raw_line: String,
    kind: String,
    role: String,
    block_kind: String,
    parameter_count: usize,
    token_count: usize,
    hash: String,
    instance_count: usize,
    module_scope: String,
    import_scope: String,
    decorator_scope: String,
    base_scope: String,
    instances: Vec<Instance>,
    public_api: Option<bool>,
    caller_count: usize,
    call_site_count: usize,
    callers: Vec<CallerEvidence>,
    callee_count: usize,
    callees: Vec<CalleeEvidence>,
    similar_callers: Vec<SimilarCallerEvidence>,
}

#[derive(Debug, PartialEq, Eq)]
struct Instance {
    raw_instance: String,
    path: String,
    line_start: usize,
    line_end: usize,
    module: String,
    qualname: String,
    parent: String,
    imports_hash: String,
    decorators_hash: String,
    bases_hash: String,
    context_hash: String,
    import_facts: Vec<String>,
}

#[derive(Debug, PartialEq, Eq)]
struct CallerEvidence {
    raw_caller: String,
    path: String,
    line_start: usize,
    line_end: usize,
    module: String,
    qualname: String,
    call_lines: Vec<usize>,
}

#[derive(Debug, PartialEq, Eq)]
struct CalleeEvidence {
    raw_callee: String,
    path: String,
    line_start: usize,
    line_end: usize,
    module: String,
    qualname: String,
    call_lines: Vec<usize>,
}

#[derive(Debug, PartialEq, Eq)]
struct SimilarCallerEvidence {
    raw_caller: String,
    path: String,
    line_start: usize,
    line_end: usize,
    module: String,
    qualname: String,
    token_count: usize,
    structure_hash: String,
    parent_scope: String,
    score: usize,
    shared_call_count: usize,
    shared_profile: Vec<String>,
    reason_codes: Vec<String>,
}

pub fn run(args: &[String]) -> i32 {
    match Args::parse(args).and_then(structure_report) {
        Ok(()) => 0,
        Err(message) => {
            eprintln!("PY_STRUCTURE_HASH_REPORT=fail");
            eprintln!("PY_STRUCTURE_HASH_REPORT_FINDING={message}");
            2
        }
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut input = None;
        let mut output = None;
        let mut root = PathBuf::from(".");
        let mut index = 0;
        while index < args.len() {
            match args[index].as_str() {
                "--input" => {
                    input = Some(PathBuf::from(value_after(args, index, "--input")?));
                    index += 2;
                }
                "--output" => {
                    output = Some(PathBuf::from(value_after(args, index, "--output")?));
                    index += 2;
                }
                "--root" => {
                    root = PathBuf::from(value_after(args, index, "--root")?);
                    index += 2;
                }
                value if value.starts_with("--") => {
                    return Err(format!("unknown argument {value}"));
                }
                value => {
                    if input.is_some() {
                        return Err(format!("unexpected positional argument {value}"));
                    }
                    input = Some(PathBuf::from(value));
                    index += 1;
                }
            }
        }
        Ok(Self {
            input,
            output,
            root,
        })
    }
}

fn value_after(args: &[String], index: usize, flag: &str) -> Result<String, String> {
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("{flag} requires a value"))
}

fn structure_report(args: Args) -> Result<(), String> {
    let text = read_input(args.input.as_ref())?;
    let payload = structure_text(&text, &args.root)?;
    let rendered = serde_json::to_string_pretty(&payload)
        .map_err(|error| format!("failed to render JSON: {error}"))?
        + "\n";
    if let Some(output) = args.output {
        fs::write(&output, rendered)
            .map_err(|error| format!("failed to write {}: {error}", output.display()))?;
        println!("PY_STRUCTURE_HASH_REPORT_OUTPUT={}", output.display());
    } else {
        print!("{rendered}");
    }
    Ok(())
}

fn read_input(input: Option<&PathBuf>) -> Result<String, String> {
    if let Some(path) = input {
        return fs::read_to_string(path)
            .map_err(|error| format!("failed to read {}: {error}", path.display()));
    }
    let mut text = String::new();
    io::stdin()
        .read_to_string(&mut text)
        .map_err(|error| format!("failed to read stdin: {error}"))?;
    Ok(text)
}

fn structure_text(text: &str, root: &Path) -> Result<Value, String> {
    let mut findings = Vec::new();
    let mut status = None;
    let mut group_count = None;
    let mut duplicate_group_count = None;
    let mut single_caller_finding_count = None;
    let mut single_callee_finding_count = None;
    let mut analyzed_file_count = None;
    let mut analyzed_files = Vec::new();
    let mut ignored_lines = Vec::new();
    let mut import_cache = BTreeMap::<String, Vec<String>>::new();
    for line in text.lines() {
        if line.trim().is_empty() {
            continue;
        }
        if let Some(value) = line.strip_prefix("PY_STRUCTURE_HASH_GROUPS=") {
            group_count = value.parse::<usize>().ok();
            continue;
        }
        if let Some(value) = line.strip_prefix("PY_STRUCTURE_HASH_DUPLICATE_GROUPS=") {
            duplicate_group_count = value.parse::<usize>().ok();
            continue;
        }
        if let Some(value) = line.strip_prefix("PY_STRUCTURE_HASH_SINGLE_CALLER_FINDINGS=") {
            single_caller_finding_count = value.parse::<usize>().ok();
            continue;
        }
        if let Some(value) = line.strip_prefix("PY_STRUCTURE_HASH_SINGLE_CALLEE_FINDINGS=") {
            single_callee_finding_count = value.parse::<usize>().ok();
            continue;
        }
        if let Some(value) = line.strip_prefix("PY_STRUCTURE_HASH_ANALYZED_FILES=") {
            analyzed_file_count = value.parse::<usize>().ok();
            continue;
        }
        if let Some(value) = line.strip_prefix("PY_STRUCTURE_HASH_ANALYZED_FILE=") {
            analyzed_files.push(value.to_string());
            continue;
        }
        if let Some(value) = line.strip_prefix("PY_STRUCTURE_HASH=") {
            status = Some(value.to_string());
            continue;
        }
        if line.starts_with("PY_STRUCTURE_HASH_FINDING=") {
            findings.push(parse_finding(line, root, &mut import_cache)?);
            continue;
        }
        ignored_lines.push(line.to_string());
    }

    let mut role_counts = BTreeMap::<String, usize>::new();
    let mut block_kind_counts = BTreeMap::<String, usize>::new();
    let mut module_scope_counts = BTreeMap::<String, usize>::new();
    for finding in &findings {
        *role_counts.entry(finding.role.clone()).or_default() += 1;
        *block_kind_counts
            .entry(finding.block_kind.clone())
            .or_default() += 1;
        *module_scope_counts
            .entry(finding.module_scope.clone())
            .or_default() += 1;
    }
    let repo_import_targets = repo_import_targets(&findings, root);
    let import_target_counts = import_target_counts(&findings, root);
    let module_group_contract = load_default_contract(root);
    let group_graph = module_group_graph(
        &findings,
        root,
        &analyzed_files,
        module_group_contract.as_ref(),
    );
    let priority_order = priority_order(
        &findings,
        root,
        &import_target_counts,
        &group_graph,
        module_group_contract.as_ref(),
    );
    let priority_by_hash = priority_order
        .iter()
        .map(|item| {
            (
                item.hash.clone(),
                (item.rank, item.score, item.reason_codes.clone()),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let mechanical_problem_clusters =
        mechanical_problem_clusters_json(&findings, &priority_order, &group_graph);

    Ok(json!({
        "summary": {
            "status": status,
            "reported_group_count": group_count,
            "reported_duplicate_group_count": duplicate_group_count,
            "reported_single_caller_finding_count": single_caller_finding_count,
            "reported_single_callee_finding_count": single_callee_finding_count,
            "parsed_group_count": findings.len(),
            "reported_analyzed_file_count": analyzed_file_count,
            "parsed_analyzed_file_count": analyzed_files.len(),
            "analyzed_files": analyzed_files,
            "ignored_line_count": ignored_lines.len(),
            "role_counts": role_counts,
            "block_kind_counts": block_kind_counts,
            "module_scope_counts": module_scope_counts,
            "repo_import_target_count": repo_import_targets.len(),
            "repo_import_targets": repo_import_targets,
            "module_group_graph": group_graph_json(&group_graph),
            "module_group_contract": {
                "path": crate::python_module_groups::DEFAULT_CONTRACT_PATH,
                "loaded": module_group_contract.is_some(),
            },
            "priority_rule": "deep_dependency_first: module-group incoming dependency count, file incoming dependency count, fewer module-group outgoing dependencies, single-caller ownership, non-public single-callee wrapper, production surface, implementation role, cross-module scope, impact tokens, stable hash; external libraries are advisory only",
            "priority_order": priority_order.iter().map(priority_json).collect::<Vec<_>>(),
            "repair_slice": repair_slice_json(&priority_order, &group_graph),
            "mechanical_problem_cluster_count": mechanical_problem_clusters.len(),
            "mechanical_problem_clusters": mechanical_problem_clusters,
        },
        "findings": findings.iter().map(|finding| finding_json(finding, root, &priority_by_hash, &import_target_counts)).collect::<Vec<_>>(),
        "ignored_lines": ignored_lines,
    }))
}

fn parse_finding(
    line: &str,
    root: &Path,
    import_cache: &mut BTreeMap<String, Vec<String>>,
) -> Result<Finding, String> {
    if let Some(body) =
        line.strip_prefix("PY_STRUCTURE_HASH_FINDING=single_caller_structural_helper:")
    {
        return parse_single_caller_finding(line, body, root, import_cache);
    }
    if let Some(body) =
        line.strip_prefix("PY_STRUCTURE_HASH_FINDING=single_callee_structural_wrapper:")
    {
        return parse_single_callee_finding(line, body, root, import_cache);
    }
    let body = line
        .strip_prefix("PY_STRUCTURE_HASH_FINDING=duplicate_structural_hash:")
        .ok_or_else(|| format!("unsupported finding line: {line}"))?;
    let (role, rest) = take_field(body, "role")?;
    let (block_kind, rest) = take_until_colon(rest)?;
    let (params, rest) = take_field(rest, "params")?;
    let (tokens, rest) = take_field(rest, "tokens")?;
    let (hash, rest) = take_field(rest, "hash")?;
    let (count, rest) = take_field(rest, "count")?;
    let (module_scope, rest) = take_field(rest, "module_scope")?;
    let (import_scope, rest) = take_field(rest, "import_scope")?;
    let (decorator_scope, rest) = take_field(rest, "decorator_scope")?;
    let (base_scope, instances_text) = take_field(rest, "base_scope")?;
    let instances = instances_text
        .split(',')
        .filter(|value| !value.is_empty())
        .map(|value| parse_instance(value, root, import_cache))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(Finding {
        raw_line: line.to_string(),
        kind: "duplicate_structural_hash".to_string(),
        role,
        block_kind,
        parameter_count: parse_usize(&params, "params")?,
        token_count: parse_usize(&tokens, "tokens")?,
        hash,
        instance_count: parse_usize(&count, "count")?,
        module_scope,
        import_scope,
        decorator_scope,
        base_scope,
        instances,
        public_api: None,
        caller_count: 0,
        call_site_count: 0,
        callers: Vec::new(),
        callee_count: 0,
        callees: Vec::new(),
        similar_callers: Vec::new(),
    })
}

fn parse_single_caller_finding(
    line: &str,
    body: &str,
    root: &Path,
    import_cache: &mut BTreeMap<String, Vec<String>>,
) -> Result<Finding, String> {
    let (role, rest) = take_field(body, "role")?;
    let (block_kind, rest) = take_until_colon(rest)?;
    let (params, rest) = take_field(rest, "params")?;
    let (tokens, rest) = take_field(rest, "tokens")?;
    let (hash, rest) = take_field(rest, "hash")?;
    let (count, rest) = take_field(rest, "count")?;
    let (caller_count, rest) = take_field(rest, "caller_count")?;
    let (call_site_count, rest) = take_field(rest, "call_site_count")?;
    let (caller, rest) = take_field(rest, "caller")?;
    let (similar_callers, rest) = if let Some(rest) = rest.strip_prefix("similar_callers=") {
        let (value, rest) = take_until_colon(rest)?;
        (parse_similar_callers(&value)?, rest)
    } else {
        (Vec::new(), rest)
    };
    let (module_scope, rest) = take_field(rest, "module_scope")?;
    let (import_scope, rest) = take_field(rest, "import_scope")?;
    let (decorator_scope, rest) = take_field(rest, "decorator_scope")?;
    let (base_scope, instances_text) = take_field(rest, "base_scope")?;
    let instances = instances_text
        .split(',')
        .filter(|value| !value.is_empty())
        .map(|value| parse_instance(value, root, import_cache))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(Finding {
        raw_line: line.to_string(),
        kind: "single_caller_structural_helper".to_string(),
        role,
        block_kind,
        parameter_count: parse_usize(&params, "params")?,
        token_count: parse_usize(&tokens, "tokens")?,
        hash,
        instance_count: parse_usize(&count, "count")?,
        module_scope,
        import_scope,
        decorator_scope,
        base_scope,
        instances,
        public_api: None,
        caller_count: parse_usize(&caller_count, "caller_count")?,
        call_site_count: parse_usize(&call_site_count, "call_site_count")?,
        callers: vec![parse_caller(&caller)?],
        callee_count: 0,
        callees: Vec::new(),
        similar_callers,
    })
}

fn parse_single_callee_finding(
    line: &str,
    body: &str,
    root: &Path,
    import_cache: &mut BTreeMap<String, Vec<String>>,
) -> Result<Finding, String> {
    let (role, rest) = take_field(body, "role")?;
    let (block_kind, rest) = take_until_colon(rest)?;
    let (params, rest) = take_field(rest, "params")?;
    let (tokens, rest) = take_field(rest, "tokens")?;
    let (hash, rest) = take_field(rest, "hash")?;
    let (count, rest) = take_field(rest, "count")?;
    let (callee_count, rest) = take_field(rest, "callee_count")?;
    let (call_site_count, rest) = take_field(rest, "call_site_count")?;
    let (public_api, rest) = take_field(rest, "public_api")?;
    let (callee, rest) = take_field(rest, "callee")?;
    let (module_scope, rest) = take_field(rest, "module_scope")?;
    let (import_scope, rest) = take_field(rest, "import_scope")?;
    let (decorator_scope, rest) = take_field(rest, "decorator_scope")?;
    let (base_scope, instances_text) = take_field(rest, "base_scope")?;
    let instances = instances_text
        .split(',')
        .filter(|value| !value.is_empty())
        .map(|value| parse_instance(value, root, import_cache))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(Finding {
        raw_line: line.to_string(),
        kind: "single_callee_structural_wrapper".to_string(),
        role,
        block_kind,
        parameter_count: parse_usize(&params, "params")?,
        token_count: parse_usize(&tokens, "tokens")?,
        hash,
        instance_count: parse_usize(&count, "count")?,
        module_scope,
        import_scope,
        decorator_scope,
        base_scope,
        instances,
        public_api: Some(parse_bool(&public_api, "public_api")?),
        caller_count: 0,
        call_site_count: parse_usize(&call_site_count, "call_site_count")?,
        callers: Vec::new(),
        callee_count: parse_usize(&callee_count, "callee_count")?,
        callees: vec![parse_callee(&callee)?],
        similar_callers: Vec::new(),
    })
}

fn take_field<'a>(text: &'a str, key: &str) -> Result<(String, &'a str), String> {
    let prefix = format!("{key}=");
    let rest = text
        .strip_prefix(&prefix)
        .ok_or_else(|| format!("expected {prefix} in {text}"))?;
    take_until_colon(rest)
}

fn take_until_colon(text: &str) -> Result<(String, &str), String> {
    let Some((value, rest)) = text.split_once(':') else {
        return Err(format!("expected ':' in {text}"));
    };
    Ok((value.to_string(), rest))
}

fn parse_instance(
    text: &str,
    root: &Path,
    import_cache: &mut BTreeMap<String, Vec<String>>,
) -> Result<Instance, String> {
    let (prefix, context_hash) = split_required(text, ":context=", "context")?;
    let (prefix, bases_hash) = split_required(prefix, ":bases=", "bases")?;
    let (prefix, decorators_hash) = split_required(prefix, ":decorators=", "decorators")?;
    let (prefix, imports_hash) = split_required(prefix, ":imports=", "imports")?;
    let mut parts = prefix.splitn(5, ':');
    let path = parts
        .next()
        .ok_or_else(|| format!("missing path in {text}"))?
        .to_string();
    let line_range = parts
        .next()
        .ok_or_else(|| format!("missing line range in {text}"))?;
    let module = parts
        .next()
        .ok_or_else(|| format!("missing module in {text}"))?
        .to_string();
    let qualname = parts
        .next()
        .ok_or_else(|| format!("missing qualname in {text}"))?
        .to_string();
    let parent = parts
        .next()
        .ok_or_else(|| format!("missing parent in {text}"))?
        .strip_prefix("parent=")
        .ok_or_else(|| format!("missing parent= in {text}"))?
        .to_string();
    let (line_start, line_end) = parse_line_range(line_range)?;
    let import_facts = import_cache
        .entry(path.clone())
        .or_insert_with(|| collect_import_facts(root, &path))
        .clone();
    Ok(Instance {
        raw_instance: text.to_string(),
        path,
        line_start,
        line_end,
        module,
        qualname,
        parent,
        imports_hash: imports_hash.to_string(),
        decorators_hash: decorators_hash.to_string(),
        bases_hash: bases_hash.to_string(),
        context_hash: context_hash.to_string(),
        import_facts,
    })
}

fn parse_caller(text: &str) -> Result<CallerEvidence, String> {
    let parts = text.split('@').collect::<Vec<_>>();
    if parts.len() != 5 {
        return Err(format!("invalid caller evidence {text}"));
    }
    let (line_start, line_end) = parse_line_range(parts[1])?;
    let call_lines = parts[4]
        .strip_prefix("sites=")
        .ok_or_else(|| format!("missing caller sites= in {text}"))?
        .split('|')
        .filter(|value| !value.is_empty())
        .map(|value| parse_usize(value, "call_line"))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(CallerEvidence {
        raw_caller: text.to_string(),
        path: parts[0].to_string(),
        line_start,
        line_end,
        module: parts[2].to_string(),
        qualname: parts[3].to_string(),
        call_lines,
    })
}

fn parse_callee(text: &str) -> Result<CalleeEvidence, String> {
    let parts = text.split('@').collect::<Vec<_>>();
    if parts.len() != 5 {
        return Err(format!("invalid callee evidence {text}"));
    }
    let (line_start, line_end) = parse_line_range(parts[1])?;
    let call_lines = parts[4]
        .strip_prefix("sites=")
        .ok_or_else(|| format!("missing callee sites= in {text}"))?
        .split('|')
        .filter(|value| !value.is_empty())
        .map(|value| parse_usize(value, "call_line"))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(CalleeEvidence {
        raw_callee: text.to_string(),
        path: parts[0].to_string(),
        line_start,
        line_end,
        module: parts[2].to_string(),
        qualname: parts[3].to_string(),
        call_lines,
    })
}

fn parse_similar_callers(text: &str) -> Result<Vec<SimilarCallerEvidence>, String> {
    if text == "none" || text.is_empty() {
        return Ok(Vec::new());
    }
    text.split(';').map(parse_similar_caller).collect()
}

fn parse_similar_caller(text: &str) -> Result<SimilarCallerEvidence, String> {
    let parts = text.split('@').collect::<Vec<_>>();
    if parts.len() == 7 {
        let (line_start, line_end) = parse_line_range(parts[1])?;
        let score = parts[4]
            .strip_prefix("score=")
            .ok_or_else(|| format!("missing score= in similar caller evidence {text}"))
            .and_then(|value| parse_usize(value, "similar_caller_score"))?;
        let shared_call_count = parts[5]
            .strip_prefix("shared=")
            .ok_or_else(|| format!("missing shared= in similar caller evidence {text}"))
            .and_then(|value| parse_usize(value, "similar_caller_shared"))?;
        let reason_codes = parts[6]
            .strip_prefix("reasons=")
            .ok_or_else(|| format!("missing reasons= in similar caller evidence {text}"))?
            .split('|')
            .filter(|value| !value.is_empty())
            .map(str::to_string)
            .collect::<Vec<_>>();
        return Ok(SimilarCallerEvidence {
            raw_caller: text.to_string(),
            path: parts[0].to_string(),
            line_start,
            line_end,
            module: parts[2].to_string(),
            qualname: parts[3].to_string(),
            token_count: 0,
            structure_hash: String::new(),
            parent_scope: String::new(),
            score,
            shared_call_count,
            shared_profile: Vec::new(),
            reason_codes,
        });
    }
    if parts.len() != 11 {
        return Err(format!("invalid similar caller evidence {text}"));
    }
    let (line_start, line_end) = parse_line_range(parts[1])?;
    let token_count = parts[4]
        .strip_prefix("tokens=")
        .ok_or_else(|| format!("missing tokens= in similar caller evidence {text}"))
        .and_then(|value| parse_usize(value, "similar_caller_tokens"))?;
    let structure_hash = parts[5]
        .strip_prefix("structure=")
        .ok_or_else(|| format!("missing structure= in similar caller evidence {text}"))?
        .to_string();
    let parent_scope = parts[6]
        .strip_prefix("parent=")
        .ok_or_else(|| format!("missing parent= in similar caller evidence {text}"))?
        .to_string();
    let score = parts[7]
        .strip_prefix("score=")
        .ok_or_else(|| format!("missing score= in similar caller evidence {text}"))
        .and_then(|value| parse_usize(value, "similar_caller_score"))?;
    let shared_call_count = parts[8]
        .strip_prefix("shared=")
        .ok_or_else(|| format!("missing shared= in similar caller evidence {text}"))
        .and_then(|value| parse_usize(value, "similar_caller_shared"))?;
    let shared_profile = parts[9]
        .strip_prefix("profile=")
        .ok_or_else(|| format!("missing profile= in similar caller evidence {text}"))?
        .split('|')
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .collect::<Vec<_>>();
    let reason_codes = parts[10]
        .strip_prefix("reasons=")
        .ok_or_else(|| format!("missing reasons= in similar caller evidence {text}"))?
        .split('|')
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .collect::<Vec<_>>();
    Ok(SimilarCallerEvidence {
        raw_caller: text.to_string(),
        path: parts[0].to_string(),
        line_start,
        line_end,
        module: parts[2].to_string(),
        qualname: parts[3].to_string(),
        token_count,
        structure_hash,
        parent_scope,
        score,
        shared_call_count,
        shared_profile,
        reason_codes,
    })
}

fn collect_import_facts(root: &Path, relative_path: &str) -> Vec<String> {
    let path = root.join(relative_path);
    let Ok(text) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let mut facts = Vec::new();
    let mut pending_from_module: Option<String> = None;
    for line in text.lines() {
        let trimmed = line.trim();
        if let Some(module) = pending_from_module.clone() {
            add_from_import_names(&mut facts, &module, trimmed);
            if trimmed.contains(')') {
                pending_from_module = None;
            }
            continue;
        }
        if trimmed.starts_with("import ") {
            let rest = trimmed
                .trim_start_matches("import ")
                .split('#')
                .next()
                .unwrap_or("");
            for item in rest.split(',') {
                let name = item.split_whitespace().next().unwrap_or("");
                if !name.is_empty() {
                    facts.push(format!("import:{name}"));
                }
            }
        } else if trimmed.starts_with("from ") {
            let rest = trimmed.trim_start_matches("from ");
            if let Some((module, names)) = rest.split_once(" import ") {
                let module = module.trim();
                if names.trim().starts_with('(') && !names.contains(')') {
                    pending_from_module = Some(module.to_string());
                } else {
                    add_from_import_names(&mut facts, module, names);
                }
            }
        }
    }
    facts.sort();
    facts.dedup();
    facts
}

fn add_from_import_names(facts: &mut Vec<String>, module: &str, names: &str) {
    let cleaned = names
        .split('#')
        .next()
        .unwrap_or("")
        .trim()
        .trim_start_matches('(')
        .trim_end_matches(')')
        .trim();
    for item in cleaned.split(',') {
        let name = item.split_whitespace().next().unwrap_or("");
        if !module.is_empty() && !name.is_empty() && name != "(" && name != ")" {
            facts.push(format!("from:{module}:{name}"));
        }
    }
}

fn split_required<'a>(
    text: &'a str,
    delimiter: &str,
    label: &str,
) -> Result<(&'a str, &'a str), String> {
    text.rsplit_once(delimiter)
        .ok_or_else(|| format!("missing {label} delimiter {delimiter} in {text}"))
}

fn parse_line_range(text: &str) -> Result<(usize, usize), String> {
    let (start, end) = text
        .split_once('-')
        .ok_or_else(|| format!("invalid line range {text}"))?;
    Ok((
        parse_usize(start, "line_start")?,
        parse_usize(end, "line_end")?,
    ))
}

fn parse_usize(value: &str, label: &str) -> Result<usize, String> {
    value
        .parse::<usize>()
        .map_err(|error| format!("invalid {label} value {value}: {error}"))
}

fn parse_bool(value: &str, label: &str) -> Result<bool, String> {
    match value {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => Err(format!(
            "invalid {label} value {value}: expected true or false"
        )),
    }
}

fn finding_json(
    finding: &Finding,
    root: &Path,
    priority_by_hash: &BTreeMap<String, (usize, usize, Vec<String>)>,
    import_target_counts: &BTreeMap<String, usize>,
) -> Value {
    let import_analysis = import_analysis_json(finding, root);
    let internal_struct_analysis = internal_struct_analysis_json(finding, root);
    let (priority_rank, priority_score, priority_reasons) = priority_by_hash
        .get(&finding.hash)
        .cloned()
        .unwrap_or((0, 0, Vec::new()));
    json!({
        "raw_line": finding.raw_line,
        "kind": finding.kind,
        "role": finding.role,
        "block_kind": finding.block_kind,
        "parameter_count": finding.parameter_count,
        "token_count": finding.token_count,
        "hash": finding.hash,
        "instance_count": finding.instance_count,
        "module_scope": finding.module_scope,
        "import_scope": finding.import_scope,
        "decorator_scope": finding.decorator_scope,
        "base_scope": finding.base_scope,
        "public_api": finding.public_api,
        "priority": {
            "rank": priority_rank,
            "score": priority_score,
            "reason_codes": priority_reasons,
        },
        "why": {
            "primary": finding.kind,
            "same_role": finding.role,
            "same_block_kind": finding.block_kind,
            "same_parameter_count": finding.parameter_count,
            "same_token_count": finding.token_count,
            "same_structure_hash": finding.hash,
            "group_instance_count": finding.instance_count,
            "scope": {
                "module": finding.module_scope,
                "imports": finding.import_scope,
                "decorators": finding.decorator_scope,
                "bases": finding.base_scope,
            },
            "import_analysis": import_analysis,
        },
        "instances": finding.instances.iter().map(instance_json).collect::<Vec<_>>(),
        "internal_struct_analysis": internal_struct_analysis.clone().unwrap_or(Value::Null),
        "caller_analysis": {
            "caller_count": finding.caller_count,
            "call_site_count": finding.call_site_count,
            "callers": finding.callers.iter().map(caller_json).collect::<Vec<_>>(),
            "similar_responsibility_callers": finding.similar_callers.iter().map(similar_caller_json).collect::<Vec<_>>(),
            "integration_candidates": integration_candidates_json(finding, &import_analysis, import_target_counts, internal_struct_analysis.as_ref()),
        },
        "callee_analysis": {
            "callee_count": finding.callee_count,
            "call_site_count": finding.call_site_count,
            "callees": finding.callees.iter().map(callee_json).collect::<Vec<_>>(),
            "integration_candidates": callee_integration_candidates_json(finding, &import_analysis, import_target_counts),
        },
    })
}

fn caller_json(caller: &CallerEvidence) -> Value {
    json!({
        "raw_caller": caller.raw_caller,
        "path": caller.path,
        "line_start": caller.line_start,
        "line_end": caller.line_end,
        "module": caller.module,
        "qualname": caller.qualname,
        "call_lines": caller.call_lines,
    })
}

fn callee_json(callee: &CalleeEvidence) -> Value {
    json!({
        "raw_callee": callee.raw_callee,
        "path": callee.path,
        "line_start": callee.line_start,
        "line_end": callee.line_end,
        "module": callee.module,
        "qualname": callee.qualname,
        "call_lines": callee.call_lines,
    })
}

fn similar_caller_json(caller: &SimilarCallerEvidence) -> Value {
    json!({
        "raw_caller": caller.raw_caller,
        "path": caller.path,
        "line_start": caller.line_start,
        "line_end": caller.line_end,
        "module": caller.module,
        "qualname": caller.qualname,
        "token_count": caller.token_count,
        "structure_hash": caller.structure_hash,
        "parent_scope": caller.parent_scope,
        "score": caller.score,
        "shared_call_count": caller.shared_call_count,
        "shared_profile": caller.shared_profile,
        "reason_codes": caller.reason_codes,
    })
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct CandidateFeature {
    code: &'static str,
    weight: usize,
    detail: String,
}

fn integration_candidates_json(
    finding: &Finding,
    import_analysis: &Value,
    import_target_counts: &BTreeMap<String, usize>,
    internal_struct_analysis: Option<&Value>,
) -> Vec<Value> {
    if finding.kind != "single_caller_structural_helper" {
        return Vec::new();
    }
    let Some(target) = finding.instances.first() else {
        return Vec::new();
    };
    let Some(caller) = finding.callers.first() else {
        return Vec::new();
    };
    let base_features = base_single_owner_features(
        finding,
        target,
        caller,
        import_analysis,
        import_target_counts,
        internal_struct_analysis,
    );
    let mut candidates = vec![candidate_json(
        single_owner_candidate_kind(&finding.block_kind, internal_struct_analysis),
        target,
        caller,
        None,
        &base_features,
    )];
    candidates.extend(finding.similar_callers.iter().map(|similar| {
        let mut features = base_features.clone();
        features.extend(similar_caller_features(similar));
        features.extend(similar_dependency_features(similar, import_target_counts));
        candidate_json(
            "consolidate_owner_with_similar_responsibility_caller",
            target,
            caller,
            Some(similar),
            &features,
        )
    }));
    candidates
}

fn callee_integration_candidates_json(
    finding: &Finding,
    import_analysis: &Value,
    import_target_counts: &BTreeMap<String, usize>,
) -> Vec<Value> {
    if finding.kind != "single_callee_structural_wrapper" {
        return Vec::new();
    }
    let Some(wrapper) = finding.instances.first() else {
        return Vec::new();
    };
    let Some(callee) = finding.callees.first() else {
        return Vec::new();
    };
    let mut features = vec![
        CandidateFeature {
            code: "non_public_wrapper",
            weight: 40,
            detail: format!("public_api={}", finding.public_api.unwrap_or(false)),
        },
        CandidateFeature {
            code: "single_resolved_callee",
            weight: 40,
            detail: format!("callee_count={}", finding.callee_count),
        },
        CandidateFeature {
            code: "usage_site_count",
            weight: finding.call_site_count.min(5) * 4,
            detail: format!("call_site_count={}", finding.call_site_count),
        },
        CandidateFeature {
            code: "wrapper_structure_size",
            weight: finding.token_count.min(50),
            detail: format!(
                "block_kind={},token_count={}",
                finding.block_kind, finding.token_count
            ),
        },
    ];
    features.extend(dependency_tree_features(
        import_analysis,
        wrapper,
        import_target_counts,
    ));
    vec![json!({
        "candidate_kind": "inline_or_merge_non_public_single_callee_wrapper",
        "candidate_schema_scope": "dependency_enriched",
        "wrapper": {
            "path": wrapper.path,
            "line_start": wrapper.line_start,
            "line_end": wrapper.line_end,
            "module": wrapper.module,
            "qualname": wrapper.qualname,
        },
        "callee": {
            "path": callee.path,
            "line_start": callee.line_start,
            "line_end": callee.line_end,
            "module": callee.module,
            "qualname": callee.qualname,
            "call_lines": callee.call_lines,
        },
        "features": features.iter().map(candidate_feature_json).collect::<Vec<_>>(),
        "reason_codes": features.iter().map(|feature| feature.code).collect::<Vec<_>>(),
    })]
}

fn base_single_owner_features(
    finding: &Finding,
    target: &Instance,
    caller: &CallerEvidence,
    import_analysis: &Value,
    import_target_counts: &BTreeMap<String, usize>,
    internal_struct_analysis: Option<&Value>,
) -> Vec<CandidateFeature> {
    let mut features = vec![
        CandidateFeature {
            code: "unique_owner",
            weight: 40,
            detail: format!("caller_count={}", finding.caller_count),
        },
        CandidateFeature {
            code: "module_local_ownership",
            weight: if target.module == caller.module {
                20
            } else {
                0
            },
            detail: format!(
                "target_module={},caller_module={}",
                target.module, caller.module
            ),
        },
        CandidateFeature {
            code: "usage_site_count",
            weight: finding.call_site_count.min(5) * 4,
            detail: format!("call_site_count={}", finding.call_site_count),
        },
        CandidateFeature {
            code: "target_structure_size",
            weight: finding.token_count.min(50),
            detail: format!(
                "block_kind={},token_count={}",
                finding.block_kind, finding.token_count
            ),
        },
    ];
    features.extend(dependency_tree_features(
        import_analysis,
        target,
        import_target_counts,
    ));
    features.extend(ast_shape_features(finding, target));
    features.extend(internal_struct_features(internal_struct_analysis));
    features
}

fn dependency_tree_features(
    import_analysis: &Value,
    target: &Instance,
    import_target_counts: &BTreeMap<String, usize>,
) -> Vec<CandidateFeature> {
    let file_incoming_count = import_target_counts
        .get(&target.path)
        .copied()
        .unwrap_or_default();
    let repo_dependency_count = import_analysis
        .get("repo_dependency_count")
        .and_then(Value::as_u64)
        .or_else(|| {
            import_analysis
                .get("repo_import_targets")
                .and_then(Value::as_array)
                .map(|items| items.len() as u64)
        })
        .unwrap_or_default() as usize;
    vec![
        CandidateFeature {
            code: "dependency_tree_file_incoming",
            weight: file_incoming_count.min(10) * 3,
            detail: format!("file_incoming_count={file_incoming_count}"),
        },
        CandidateFeature {
            code: "dependency_tree_repo_dependencies",
            weight: repo_dependency_count.min(10),
            detail: format!("repo_dependency_count={repo_dependency_count}"),
        },
    ]
}

fn ast_shape_features(finding: &Finding, target: &Instance) -> Vec<CandidateFeature> {
    let mut features = Vec::new();
    features.push(CandidateFeature {
        code: "ast_block_kind",
        weight: match finding.block_kind.as_str() {
            "Function" => 8,
            "Class" => 8,
            "Alias" => 4,
            _ => 1,
        },
        detail: finding.block_kind.clone(),
    });
    if target.parent == "<module>" {
        features.push(CandidateFeature {
            code: "ast_module_level_target",
            weight: 6,
            detail: target.parent.clone(),
        });
    } else {
        features.push(CandidateFeature {
            code: "ast_nested_target",
            weight: 3,
            detail: target.parent.clone(),
        });
    }
    if finding.block_kind == "Class" {
        features.push(CandidateFeature {
            code: "ast_structural_type_target",
            weight: 8,
            detail: format!("parameter_count={}", finding.parameter_count),
        });
    }
    features
}

fn internal_struct_features(internal_struct_analysis: Option<&Value>) -> Vec<CandidateFeature> {
    let Some(analysis) = internal_struct_analysis else {
        return Vec::new();
    };
    let Some(decision) = internal_struct_decision(Some(analysis)) else {
        return Vec::new();
    };
    let mut features = vec![CandidateFeature {
        code: "internal_struct_decision",
        weight: if decision == "inline_candidate" {
            20
        } else {
            0
        },
        detail: decision.to_string(),
    }];
    if let Some(reasons) = analysis.get("decision_reasons").and_then(Value::as_array) {
        features.extend(
            reasons
                .iter()
                .filter_map(Value::as_str)
                .map(|reason| CandidateFeature {
                    code: "internal_struct_reason",
                    weight: 0,
                    detail: reason.to_string(),
                }),
        );
    }
    features
}

#[derive(Debug, Default)]
struct ClassSourceFacts {
    decorator_names: Vec<String>,
    base_names: Vec<String>,
    field_names: Vec<String>,
    method_names: Vec<String>,
}

impl ClassSourceFacts {
    fn is_dataclass_like(&self) -> bool {
        self.decorator_names
            .iter()
            .any(|decorator| decorator.contains("dataclass"))
    }

    fn has_pytree_registration(&self) -> bool {
        self.decorator_names
            .iter()
            .any(|decorator| decorator.contains("register_pytree_node_class"))
    }

    fn has_tree_methods(&self) -> bool {
        self.method_names
            .iter()
            .any(|method| method == "tree_flatten" || method == "tree_unflatten")
    }

    fn has_protocol_or_generic_contract(&self) -> bool {
        self.base_names.iter().any(|base| {
            let leaf = base.rsplit('.').next().unwrap_or(base);
            leaf.starts_with("Protocol") || leaf == "Generic"
        })
    }

    fn custom_method_names(&self) -> Vec<String> {
        self.method_names
            .iter()
            .filter(|method| {
                method.as_str() != "__post_init__"
                    && method.as_str() != "tree_flatten"
                    && method.as_str() != "tree_unflatten"
            })
            .cloned()
            .collect()
    }
}

#[derive(Debug, Default)]
struct InternalStructUsageFacts {
    constructor_call_count: usize,
    attribute_read_count: usize,
    attribute_read_scope: String,
    single_callee_names: Vec<String>,
    unscoped_instance_usage_count: usize,
    loop_carry_usage: bool,
    public_payload_usage: bool,
    return_usage: bool,
}

fn internal_struct_analysis_json(finding: &Finding, root: &Path) -> Option<Value> {
    if finding.kind != "single_caller_structural_helper" || finding.block_kind != "Class" {
        return None;
    }
    let target = finding.instances.first()?;
    let leaf_name = target
        .qualname
        .rsplit('.')
        .next()
        .unwrap_or(&target.qualname);
    if !leaf_name.starts_with('_') {
        return None;
    }
    let source_facts = class_source_facts(root, target);
    let usage_facts = internal_struct_usage_facts(root, target, finding.callers.first());
    let custom_methods = source_facts.custom_method_names();
    let mut preserve_reasons = Vec::<String>::new();
    let mut review_reasons = Vec::<String>::new();
    let mut inline_reasons = Vec::<String>::new();

    if source_facts.has_pytree_registration() {
        preserve_reasons.push("jax_pytree_registration".to_string());
    }
    if source_facts.has_tree_methods() {
        preserve_reasons.push("tree_flatten_contract".to_string());
    }
    if source_facts.has_protocol_or_generic_contract() {
        preserve_reasons.push("protocol_or_generic_contract".to_string());
    }
    if usage_facts.loop_carry_usage {
        preserve_reasons.push("loop_or_scan_carry_usage".to_string());
    }
    if usage_facts.public_payload_usage {
        preserve_reasons.push("public_algorithm_payload_usage".to_string());
    }
    if usage_facts.constructor_call_count != 1 {
        review_reasons.push(format!(
            "constructor_call_count={}",
            usage_facts.constructor_call_count
        ));
    }
    if !custom_methods.is_empty() {
        review_reasons.push(format!("custom_methods={}", custom_methods.join("|")));
    }
    if usage_facts.return_usage {
        review_reasons.push("returned_internal_struct_instance".to_string());
    }
    if usage_facts.attribute_read_scope == "unresolved" {
        review_reasons.push("attribute_reads_not_closed_in_owner_or_single_callee".to_string());
    }
    if usage_facts.unscoped_instance_usage_count > 0 {
        review_reasons.push(format!(
            "unscoped_instance_usage_count={}",
            usage_facts.unscoped_instance_usage_count
        ));
    }
    if source_facts.field_names.len() > INTERNAL_STRUCT_INLINE_FIELD_LIMIT {
        preserve_reasons.push(format!(
            "field_count_exceeds_inline_limit={}>{}",
            source_facts.field_names.len(),
            INTERNAL_STRUCT_INLINE_FIELD_LIMIT
        ));
    }
    if source_facts.field_names.is_empty() && !source_facts.is_dataclass_like() {
        review_reasons.push("no_dataclass_field_surface_detected".to_string());
    }
    if preserve_reasons.is_empty() && review_reasons.is_empty() {
        inline_reasons.push("single_constructor_owner".to_string());
        inline_reasons.push("field_only_private_dataclass_surface".to_string());
        if usage_facts.attribute_read_count > 0 {
            inline_reasons.push(format!(
                "attribute_reads_scope={}",
                usage_facts.attribute_read_scope
            ));
        }
    }

    let (decision, decision_reasons) = if !preserve_reasons.is_empty() {
        ("preserve_candidate", preserve_reasons)
    } else if !review_reasons.is_empty() {
        ("review_required", review_reasons)
    } else {
        ("inline_candidate", inline_reasons)
    };

    Some(json!({
        "kind": "private_internal_struct",
        "decision": decision,
        "decision_reasons": decision_reasons,
        "source_facts": {
            "decorator_names": source_facts.decorator_names,
            "base_names": source_facts.base_names,
            "field_names": source_facts.field_names,
            "field_count": source_facts.field_names.len(),
            "method_names": source_facts.method_names,
            "custom_method_names": custom_methods,
            "is_dataclass_like": source_facts.is_dataclass_like(),
            "has_pytree_registration": source_facts.has_pytree_registration(),
            "has_tree_methods": source_facts.has_tree_methods(),
            "has_protocol_or_generic_contract": source_facts.has_protocol_or_generic_contract(),
        },
        "usage_facts": {
            "constructor_call_count": usage_facts.constructor_call_count,
            "attribute_read_count": usage_facts.attribute_read_count,
            "attribute_read_scope": usage_facts.attribute_read_scope,
            "single_callee_names": usage_facts.single_callee_names,
            "unscoped_instance_usage_count": usage_facts.unscoped_instance_usage_count,
            "loop_carry_usage": usage_facts.loop_carry_usage,
            "public_payload_usage": usage_facts.public_payload_usage,
            "return_usage": usage_facts.return_usage,
        },
        "policy": {
            "inline_field_limit": INTERNAL_STRUCT_INLINE_FIELD_LIMIT,
            "constructor_call_count_required": 1,
        }
    }))
}

fn class_source_facts(root: &Path, target: &Instance) -> ClassSourceFacts {
    let Ok(text) = fs::read_to_string(root.join(&target.path)) else {
        return ClassSourceFacts::default();
    };
    let lines = text.lines().collect::<Vec<_>>();
    if target.line_start == 0 || target.line_start > lines.len() {
        return ClassSourceFacts::default();
    }
    let class_line = lines[target.line_start - 1];
    let class_indent = leading_spaces(class_line);
    let mut decorators = Vec::new();
    let mut cursor = target.line_start.saturating_sub(1);
    while cursor > 0 {
        let trimmed = lines[cursor - 1].trim();
        if trimmed.starts_with('@') {
            decorators.push(trimmed.trim_start_matches('@').to_string());
            cursor -= 1;
            continue;
        }
        if trimmed.is_empty() {
            cursor -= 1;
            continue;
        }
        break;
    }
    decorators.reverse();

    let base_names = class_base_names(class_line);
    let mut field_names = Vec::new();
    let mut method_names = Vec::new();
    for line in lines
        .iter()
        .skip(target.line_start)
        .take(target.line_end.saturating_sub(target.line_start))
    {
        let indent = leading_spaces(line);
        if indent <= class_indent {
            continue;
        }
        let trimmed = line.trim();
        if trimmed.starts_with("def ") || trimmed.starts_with("async def ") {
            if let Some(name) = function_name_from_line(trimmed) {
                method_names.push(name);
            }
        } else if indent == class_indent + 4 {
            if let Some(name) = annotated_field_name(trimmed) {
                field_names.push(name);
            }
        }
    }
    field_names.sort();
    field_names.dedup();
    method_names.sort();
    method_names.dedup();

    ClassSourceFacts {
        decorator_names: decorators,
        base_names,
        field_names,
        method_names,
    }
}

fn internal_struct_usage_facts(
    root: &Path,
    target: &Instance,
    caller: Option<&CallerEvidence>,
) -> InternalStructUsageFacts {
    let Some(caller) = caller else {
        return InternalStructUsageFacts::default();
    };
    let Ok(text) = fs::read_to_string(root.join(&caller.path)) else {
        return InternalStructUsageFacts::default();
    };
    let lines = text.lines().collect::<Vec<_>>();
    let target_leaf = target
        .qualname
        .rsplit('.')
        .next()
        .unwrap_or(&target.qualname);
    let mut constructor_vars = BTreeSet::<String>::new();
    let mut facts = InternalStructUsageFacts::default();
    for line_number in &caller.call_lines {
        if let Some(line) = line_at(&lines, *line_number) {
            if line.contains(&format!("{target_leaf}(")) {
                facts.constructor_call_count += 1;
                if let Some(name) = assignment_target_name(line) {
                    constructor_vars.insert(name);
                }
                if starts_with_returned_value(line, target_leaf) {
                    facts.return_usage = true;
                }
            }
        }
    }
    let mut callee_refs = Vec::<CalleeInstanceUse>::new();
    for line in caller_lines(&lines, caller) {
        let trimmed = line.trim();
        let public_payload_use = public_payload_names()
            .iter()
            .any(|name| trimmed.contains(&format!("{name}(")))
            && (trimmed.contains(target_leaf)
                || constructor_vars.iter().any(|name| trimmed.contains(name)));
        let line_loop_carry_use = (trimmed.contains("while_loop(")
            || trimmed.contains("lax.scan(")
            || trimmed.contains("jax.lax.scan("))
            && (trimmed.contains(target_leaf)
                || constructor_vars.iter().any(|name| trimmed.contains(name)));
        if line_loop_carry_use {
            facts.loop_carry_usage = true;
        }
        if public_payload_use {
            facts.public_payload_usage = true;
        }
        if starts_with_returned_value(trimmed, target_leaf)
            || constructor_vars
                .iter()
                .any(|name| starts_with_returned_value(trimmed, name))
        {
            facts.return_usage = true;
        }
        for name in &constructor_vars {
            let direct_attr_reads = trimmed.matches(&format!("{name}.")).count();
            facts.attribute_read_count += direct_attr_reads;
            let direct_constructor_line = trimmed.contains(&format!("{target_leaf}("));
            for callee_ref in callee_instance_uses(trimmed, name) {
                callee_refs.push(callee_ref);
            }
            if trimmed.contains(name)
                && direct_attr_reads == 0
                && !direct_constructor_line
                && !public_payload_use
                && !line_loop_carry_use
                && !trimmed.starts_with("return ")
                && callee_instance_uses(trimmed, name).is_empty()
            {
                facts.unscoped_instance_usage_count += 1;
            }
        }
    }
    let mut callee_names = BTreeSet::<String>::new();
    let mut callee_attribute_reads = 0usize;
    for callee_ref in &callee_refs {
        callee_names.insert(callee_ref.function_name.clone());
        callee_attribute_reads +=
            function_attribute_read_count(&lines, &callee_ref.function_name, &callee_ref.argument);
    }
    facts.single_callee_names = callee_names.iter().cloned().collect();
    let owner_attribute_reads = facts.attribute_read_count;
    facts.attribute_read_count += callee_attribute_reads;
    facts.attribute_read_scope = if owner_attribute_reads > 0 && callee_attribute_reads == 0 {
        "caller".to_string()
    } else if owner_attribute_reads == 0 && callee_attribute_reads > 0 && callee_names.len() == 1 {
        "single_callee".to_string()
    } else if owner_attribute_reads == 0 && callee_attribute_reads == 0 && callee_names.is_empty() {
        "none".to_string()
    } else {
        "unresolved".to_string()
    };
    facts
}

fn internal_struct_decision(internal_struct_analysis: Option<&Value>) -> Option<&str> {
    internal_struct_analysis?
        .get("decision")
        .and_then(Value::as_str)
}

fn leading_spaces(line: &str) -> usize {
    line.chars().take_while(|value| *value == ' ').count()
}

fn class_base_names(class_line: &str) -> Vec<String> {
    let Some(after_open) = class_line.split_once('(').map(|(_, rest)| rest) else {
        return Vec::new();
    };
    let Some(before_close) = after_open.rsplit_once(')').map(|(left, _)| left) else {
        return Vec::new();
    };
    before_close
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .collect()
}

fn function_name_from_line(line: &str) -> Option<String> {
    let rest = line
        .strip_prefix("async def ")
        .or_else(|| line.strip_prefix("def "))?;
    rest.split_once('(')
        .map(|(name, _)| name.trim().to_string())
}

fn annotated_field_name(line: &str) -> Option<String> {
    if line.starts_with('#')
        || line.starts_with("def ")
        || line.starts_with("class ")
        || line.starts_with("if ")
        || line.starts_with("for ")
        || line.starts_with("return ")
    {
        return None;
    }
    let (candidate, _rest) = line.split_once(':')?;
    let candidate = candidate.trim();
    if candidate.is_empty()
        || candidate.contains(' ')
        || candidate.contains('.')
        || candidate.contains('[')
        || candidate.contains('(')
    {
        return None;
    }
    Some(candidate.to_string())
}

fn line_at<'a>(lines: &'a [&str], one_based_line: usize) -> Option<&'a str> {
    if one_based_line == 0 {
        return None;
    }
    lines.get(one_based_line - 1).copied()
}

fn caller_lines<'a>(lines: &'a [&str], caller: &CallerEvidence) -> impl Iterator<Item = &'a str> {
    let start = caller.line_start.saturating_sub(1);
    let end = caller.line_end.min(lines.len());
    lines[start..end].iter().copied()
}

fn assignment_target_name(line: &str) -> Option<String> {
    let (left, _right) = line.split_once('=')?;
    let name = left
        .split(|value: char| !(value.is_ascii_alphanumeric() || value == '_'))
        .rfind(|value| !value.is_empty())?;
    Some(name.to_string())
}

fn starts_with_returned_value(line: &str, value_name: &str) -> bool {
    let trimmed = line.trim();
    trimmed == format!("return {value_name}")
        || trimmed.starts_with(&format!("return {value_name},"))
        || trimmed.starts_with(&format!("return {value_name})"))
        || trimmed.starts_with(&format!("return {value_name}("))
}

#[derive(Debug, Clone)]
struct CalleeInstanceUse {
    function_name: String,
    argument: String,
}

fn callee_instance_uses(line: &str, variable_name: &str) -> Vec<CalleeInstanceUse> {
    let mut uses = Vec::new();
    let mut cursor = 0usize;
    while let Some(offset) = line[cursor..].find('(') {
        let open = cursor + offset;
        let function_name = line[..open]
            .split(|value: char| !(value.is_ascii_alphanumeric() || value == '_' || value == '.'))
            .rfind(|value| !value.is_empty())
            .unwrap_or("")
            .rsplit('.')
            .next()
            .unwrap_or("")
            .to_string();
        let Some(close) = line[open + 1..].find(')').map(|value| open + 1 + value) else {
            break;
        };
        let args = &line[open + 1..close];
        if !function_name.is_empty()
            && !public_payload_names().contains(&function_name.as_str())
            && !["fori_loop", "scan", "while_loop", "where"].contains(&function_name.as_str())
            && args
                .split(',')
                .map(str::trim)
                .any(|argument| argument == variable_name)
        {
            uses.push(CalleeInstanceUse {
                function_name,
                argument: variable_name.to_string(),
            });
        }
        cursor = close + 1;
    }
    uses
}

fn function_attribute_read_count(lines: &[&str], function_name: &str, argument: &str) -> usize {
    let Some((line_index, def_line)) = lines.iter().enumerate().find(|(_index, line)| {
        let trimmed = line.trim_start();
        trimmed.starts_with(&format!("def {function_name}("))
            || trimmed.starts_with(&format!("async def {function_name}("))
    }) else {
        return 0;
    };
    let Some(parameter_name) = callee_parameter_name(def_line, argument) else {
        return 0;
    };
    let def_indent = leading_spaces(def_line);
    lines
        .iter()
        .skip(line_index + 1)
        .take_while(|line| line.trim().is_empty() || leading_spaces(line) > def_indent)
        .map(|line| line.matches(&format!("{parameter_name}.")).count())
        .sum()
}

fn callee_parameter_name(def_line: &str, argument: &str) -> Option<String> {
    let (_prefix, after_open) = def_line.split_once('(')?;
    let (params, _suffix) = after_open.split_once(')')?;
    let data_params = params
        .split(',')
        .map(|param| param.trim().split([':', '=']).next().unwrap_or("").trim())
        .filter(|param| !param.is_empty() && *param != "self" && *param != "cls")
        .map(str::to_string)
        .collect::<Vec<_>>();
    if data_params.iter().any(|param| param == argument) {
        return Some(argument.to_string());
    }
    if data_params.len() == 1 {
        return data_params.into_iter().next();
    }
    None
}

fn public_payload_names() -> &'static [&'static str] {
    &[
        "Algorithm",
        "Answer",
        "Info",
        "Problem",
        "SolveConfig",
        "State",
    ]
}

fn similar_caller_features(similar: &SimilarCallerEvidence) -> Vec<CandidateFeature> {
    let mut features = vec![
        CandidateFeature {
            code: "similar_responsibility_caller",
            weight: 30,
            detail: format!("similar={}", similar.qualname),
        },
        CandidateFeature {
            code: "shared_call_profile_count",
            weight: similar.shared_call_count * 8,
            detail: format!("shared_call_count={}", similar.shared_call_count),
        },
    ];
    features.extend(similar.reason_codes.iter().map(|reason| CandidateFeature {
        code: "similarity_reason",
        weight: similarity_reason_weight(reason),
        detail: reason.clone(),
    }));
    features
}

fn similar_dependency_features(
    similar: &SimilarCallerEvidence,
    import_target_counts: &BTreeMap<String, usize>,
) -> Vec<CandidateFeature> {
    let file_incoming_count = import_target_counts
        .get(&similar.path)
        .copied()
        .unwrap_or_default();
    vec![CandidateFeature {
        code: "similar_caller_dependency_tree_file_incoming",
        weight: file_incoming_count.min(10) * 2,
        detail: format!(
            "similar_caller={},file_incoming_count={file_incoming_count}",
            similar.qualname
        ),
    }]
}

fn similarity_reason_weight(reason: &str) -> usize {
    match reason {
        "same_caller_structure" => 20,
        "same_parent_scope" => 12,
        "shared_call_profile" => 10,
        "similar_token_band" => 4,
        _ => 1,
    }
}

fn candidate_json(
    candidate_kind: &str,
    target: &Instance,
    caller: &CallerEvidence,
    similar: Option<&SimilarCallerEvidence>,
    features: &[CandidateFeature],
) -> Value {
    let mut payload = json!({
        "candidate_kind": candidate_kind,
        "candidate_schema_scope": "dependency_enriched",
        "target": instance_json(target),
        "destination_caller": caller_json(caller),
        "score": features.iter().map(|feature| feature.weight).sum::<usize>(),
        "features": features.iter().map(candidate_feature_json).collect::<Vec<_>>(),
        "reason_codes": features.iter().map(|feature| feature.code).collect::<Vec<_>>(),
    });
    if let Some(similar) = similar {
        payload["similar_caller"] = similar_caller_json(similar);
    }
    payload
}

fn single_owner_candidate_kind(
    block_kind: &str,
    internal_struct_analysis: Option<&Value>,
) -> &'static str {
    if block_kind == "Class" {
        match internal_struct_decision(internal_struct_analysis) {
            Some("inline_candidate") => return "inline_single_owner_internal_struct",
            Some("preserve_candidate") => return "preserve_internal_struct_contract",
            Some("review_required") => return "review_internal_struct",
            _ => {}
        }
    }
    match block_kind {
        "Class" => "move_or_nest_single_owner_type",
        "Alias" => "inline_single_owner_alias",
        _ => "inline_target_into_owner",
    }
}

fn candidate_feature_json(feature: &CandidateFeature) -> Value {
    json!({
        "code": feature.code,
        "weight": feature.weight,
        "detail": feature.detail,
    })
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct PriorityItem {
    rank: usize,
    score: usize,
    kind: String,
    hash: String,
    role: String,
    block_kind: String,
    instance_count: usize,
    parameter_count: usize,
    token_count: usize,
    module_scope: String,
    import_scope: String,
    imported_by_count: usize,
    group_imported_by_count: usize,
    repo_dependency_count: usize,
    group_dependency_count: usize,
    production_instance_count: usize,
    source_groups: Vec<String>,
    representative_instances: Vec<String>,
    instance_files: Vec<String>,
    reason_codes: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ModuleGroupGraph {
    file_counts: BTreeMap<String, usize>,
    incoming_counts: BTreeMap<String, usize>,
    outgoing_counts: BTreeMap<String, usize>,
    edge_counts: BTreeMap<(String, String), usize>,
}

fn priority_order(
    findings: &[Finding],
    root: &Path,
    import_target_counts: &BTreeMap<String, usize>,
    group_graph: &ModuleGroupGraph,
    contract: Option<&ModuleGroupContract>,
) -> Vec<PriorityItem> {
    let mut items = findings
        .iter()
        .map(|finding| priority_item(finding, root, import_target_counts, group_graph, contract))
        .collect::<Vec<_>>();
    items.sort_by(|left, right| {
        right
            .score
            .cmp(&left.score)
            .then_with(|| left.hash.cmp(&right.hash))
    });
    for (index, item) in items.iter_mut().enumerate() {
        item.rank = index + 1;
    }
    items
}

fn priority_item(
    finding: &Finding,
    root: &Path,
    import_target_counts: &BTreeMap<String, usize>,
    group_graph: &ModuleGroupGraph,
    contract: Option<&ModuleGroupContract>,
) -> PriorityItem {
    let production_instance_count = finding
        .instances
        .iter()
        .filter(|instance| production_path(&instance.path))
        .count();
    let imported_by_count = finding
        .instances
        .iter()
        .map(|instance| {
            import_target_counts
                .get(&instance.path)
                .copied()
                .unwrap_or(0)
        })
        .sum::<usize>();
    let source_groups = finding_source_groups(finding, contract);
    let group_imported_by_count = source_groups
        .iter()
        .map(|group| group_graph.incoming_counts.get(group).copied().unwrap_or(0))
        .sum::<usize>();
    let group_dependency_count = source_groups
        .iter()
        .map(|group| group_graph.outgoing_counts.get(group).copied().unwrap_or(0))
        .sum::<usize>();
    let repo_target_count = import_analysis_targets(finding, root).len();
    let impact = finding.instance_count.saturating_mul(finding.token_count);
    let mut reason_codes = Vec::new();
    let single_caller_weight = if finding.kind == "single_caller_structural_helper" {
        reason_codes.push("single_caller_structural_helper".to_string());
        750_000
    } else {
        0
    };
    let single_callee_weight = if finding.kind == "single_callee_structural_wrapper" {
        reason_codes.push("single_callee_structural_wrapper".to_string());
        700_000
    } else {
        0
    };
    let group_deep_dependency_weight = group_imported_by_count * 10_000_000;
    if group_imported_by_count > 0 {
        reason_codes.push("deep_module_group_dependency".to_string());
    }
    let file_deep_dependency_weight = imported_by_count * 1_000_000;
    if imported_by_count > 0 {
        reason_codes.push("deep_file_dependency".to_string());
    }
    let fewer_group_dependencies_weight =
        1_000_000usize.saturating_sub(group_dependency_count * 100_000);
    if group_dependency_count == 0 {
        reason_codes.push("leaf_module_group_dependency".to_string());
    }
    let role_weight = match finding.role.as_str() {
        "implementation" => {
            reason_codes.push("implementation_role".to_string());
            10_000
        }
        "protocol" => 1_000,
        "alias" => 100,
        _ => 0,
    };
    let production_weight = production_instance_count * 50_000;
    if production_instance_count > 0 {
        reason_codes.push("production_surface".to_string());
    }
    let module_scope_weight = if finding.module_scope == "CrossModule" {
        reason_codes.push("cross_module_duplicate".to_string());
        5_000
    } else {
        0
    };
    let block_kind_weight = match finding.block_kind.as_str() {
        "Class" => {
            reason_codes.push("class_structure".to_string());
            3_000
        }
        "Function" => 2_000,
        "Alias" => 500,
        _ => 0,
    };
    let import_scope_weight = if finding.import_scope == "MixedImports" {
        reason_codes.push("mixed_import_context".to_string());
        1_000
    } else {
        0
    };
    if repo_target_count > 0 {
        reason_codes.push("has_repo_import_targets".to_string());
    }
    let score = group_deep_dependency_weight
        + file_deep_dependency_weight
        + fewer_group_dependencies_weight
        + single_caller_weight
        + single_callee_weight
        + production_weight
        + role_weight
        + module_scope_weight
        + block_kind_weight
        + import_scope_weight
        + impact;
    PriorityItem {
        rank: 0,
        score,
        kind: finding.kind.clone(),
        hash: finding.hash.clone(),
        role: finding.role.clone(),
        block_kind: finding.block_kind.clone(),
        instance_count: finding.instance_count,
        parameter_count: finding.parameter_count,
        token_count: finding.token_count,
        module_scope: finding.module_scope.clone(),
        import_scope: finding.import_scope.clone(),
        imported_by_count,
        group_imported_by_count,
        repo_dependency_count: repo_target_count,
        group_dependency_count,
        production_instance_count,
        source_groups,
        representative_instances: finding
            .instances
            .iter()
            .take(5)
            .map(|instance| {
                format!(
                    "{}:{}-{}:{}",
                    instance.path, instance.line_start, instance.line_end, instance.qualname
                )
            })
            .collect(),
        instance_files: finding
            .instances
            .iter()
            .map(|instance| instance.path.clone())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect(),
        reason_codes,
    }
}

fn priority_json(item: &PriorityItem) -> Value {
    json!({
        "rank": item.rank,
        "score": item.score,
        "kind": item.kind,
        "hash": item.hash,
        "role": item.role,
        "block_kind": item.block_kind,
        "instance_count": item.instance_count,
        "parameter_count": item.parameter_count,
        "token_count": item.token_count,
        "module_scope": item.module_scope,
        "import_scope": item.import_scope,
        "imported_by_count": item.imported_by_count,
        "group_imported_by_count": item.group_imported_by_count,
        "repo_dependency_count": item.repo_dependency_count,
        "group_dependency_count": item.group_dependency_count,
        "production_instance_count": item.production_instance_count,
        "source_groups": item.source_groups,
        "representative_instances": item.representative_instances,
        "instance_files": item.instance_files,
        "reason_codes": item.reason_codes,
    })
}

fn repair_slice_json(priority_order: &[PriorityItem], graph: &ModuleGroupGraph) -> Value {
    let skipped = priority_order
        .iter()
        .filter_map(|item| {
            let blockers = repair_blockers(item);
            if blockers.is_empty() {
                None
            } else {
                Some(json!({
                    "rank": item.rank,
                    "hash": item.hash,
                    "blockers": blockers,
                    "source_groups": item.source_groups,
                    "representative_instances": item.representative_instances,
                }))
            }
        })
        .take(20)
        .collect::<Vec<_>>();
    let Some(root) = priority_order
        .iter()
        .find(|item| repair_blockers(item).is_empty() && item.source_groups.len() == 1)
        .or_else(|| {
            priority_order
                .iter()
                .find(|item| repair_blockers(item).is_empty())
        })
        .or_else(|| priority_order.first())
    else {
        return json!(null);
    };
    let preferred_home_group = preferred_home_group(root, graph);
    let downstream_groups = downstream_groups(&preferred_home_group, graph);
    let mut repair_groups = BTreeSet::new();
    repair_groups.insert(preferred_home_group.clone());
    repair_groups.extend(downstream_groups.iter().cloned());
    let related_findings = priority_order
        .iter()
        .skip(1)
        .filter(|item| {
            item.source_groups
                .iter()
                .any(|group| repair_groups.contains(group))
        })
        .take(25)
        .map(|item| {
            json!({
                "rank": item.rank,
                "hash": item.hash,
                "score": item.score,
                "source_groups": item.source_groups,
                "representative_instances": item.representative_instances,
            })
        })
        .collect::<Vec<_>>();
    let affected_files = priority_order
        .iter()
        .filter(|item| {
            item.source_groups
                .iter()
                .any(|group| repair_groups.contains(group))
        })
        .flat_map(|item| item.instance_files.iter().cloned())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    json!({
        "actionability": if repair_blockers(root).is_empty() { "actionable" } else { "review_required" },
        "skipped_review_required": skipped,
        "root_finding": priority_json(root),
        "preferred_home_group": preferred_home_group,
        "affected_downstream_groups": downstream_groups,
        "affected_files": affected_files,
        "related_findings": related_findings,
        "algorithm": [
            "select priority_order[0]",
            "choose the source group with highest incoming dependency count and lowest outgoing dependency count as preferred_home_group",
            "expand downstream groups through module_group_graph edges pointing into preferred_home_group",
            "include related findings whose source_groups intersect preferred_home_group or downstream groups",
            "after fixing this slice, rerun full python-structure-hash and python-structure-hash-report"
        ],
        "after_fix_commands": [
            "cargo run --quiet --manifest-path vendor/agent-canon/rust/agent-canon/Cargo.toml -- python-structure-hash --root . --min-tokens 8 --format text > /tmp/python_structure_hash_findings.txt",
            "cargo run --quiet --manifest-path vendor/agent-canon/rust/agent-canon/Cargo.toml -- python-structure-hash-report --root . --input /tmp/python_structure_hash_findings.txt --output /tmp/python_structure_hash_findings.json"
        ],
    })
}

fn mechanical_problem_clusters_json(
    findings: &[Finding],
    priority_order: &[PriorityItem],
    graph: &ModuleGroupGraph,
) -> Vec<Value> {
    let priority_by_hash = priority_order
        .iter()
        .map(|item| (item.hash.clone(), item))
        .collect::<BTreeMap<_, _>>();
    let mut clusters = Vec::<Value>::new();
    clusters.extend(same_callee_problem_clusters(findings, &priority_by_hash));
    clusters.extend(same_owner_problem_clusters(findings, &priority_by_hash));
    clusters.extend(file_hotspot_problem_clusters(findings, &priority_by_hash));
    clusters.extend(module_group_problem_clusters(priority_order, graph));
    clusters.extend(duplicate_shape_problem_clusters(
        findings,
        &priority_by_hash,
    ));
    clusters.extend(review_blocker_problem_clusters(priority_order));
    clusters.sort_by(|left, right| {
        right["priority_score"]
            .as_u64()
            .cmp(&left["priority_score"].as_u64())
            .then_with(|| {
                left["problem_kind"]
                    .as_str()
                    .cmp(&right["problem_kind"].as_str())
            })
            .then_with(|| {
                left["cluster_key"]
                    .as_str()
                    .cmp(&right["cluster_key"].as_str())
            })
    });
    clusters
}

fn same_callee_problem_clusters<'a>(
    findings: &'a [Finding],
    priority_by_hash: &BTreeMap<String, &'a PriorityItem>,
) -> Vec<Value> {
    let mut by_callee = BTreeMap::<String, Vec<&Finding>>::new();
    for finding in findings
        .iter()
        .filter(|finding| finding.kind == "single_callee_structural_wrapper")
    {
        let Some(callee) = finding.callees.first() else {
            continue;
        };
        by_callee
            .entry(callee_key(callee))
            .or_default()
            .push(finding);
    }
    by_callee
        .into_iter()
        .filter(|(_, grouped)| grouped.len() >= 2)
        .map(|(cluster_key, grouped)| {
            let callee = grouped
                .first()
                .and_then(|finding| finding.callees.first())
                .expect("callee group has callee");
            let blockers = same_callee_batch_blockers(&grouped);
            json!({
                "problem_kind": "same_callee_wrapper_batch",
                "cluster_key": cluster_key,
                "action_hint": if blockers.is_empty() { "merge_or_inline_wrapper_batch" } else { "batch_review_required" },
                "confidence": if blockers.is_empty() { "high" } else { "medium" },
                "priority_score": grouped_priority_score(&grouped, priority_by_hash),
                "finding_count": grouped.len(),
                "affected_files": affected_files_for_findings(&grouped),
                "shared_target": {
                    "path": callee.path,
                    "line_start": callee.line_start,
                    "line_end": callee.line_end,
                    "module": callee.module,
                    "qualname": callee.qualname,
                },
                "blockers": blockers,
                "findings": finding_refs(&grouped, priority_by_hash),
            })
        })
        .collect()
}

fn same_owner_problem_clusters<'a>(
    findings: &'a [Finding],
    priority_by_hash: &BTreeMap<String, &'a PriorityItem>,
) -> Vec<Value> {
    let mut by_owner = BTreeMap::<String, Vec<&Finding>>::new();
    for finding in findings
        .iter()
        .filter(|finding| finding.kind == "single_caller_structural_helper")
    {
        let Some(caller) = finding.callers.first() else {
            continue;
        };
        by_owner
            .entry(caller_key(caller))
            .or_default()
            .push(finding);
    }
    by_owner
        .into_iter()
        .filter(|(_, grouped)| grouped.len() >= 2)
        .map(|(cluster_key, grouped)| {
            let caller = grouped
                .first()
                .and_then(|finding| finding.callers.first())
                .expect("owner group has caller");
            let blockers = same_owner_batch_blockers(&grouped);
            json!({
                "problem_kind": "same_owner_single_caller_batch",
                "cluster_key": cluster_key,
                "action_hint": if blockers.is_empty() { "inline_or_nest_owned_helpers_together" } else { "batch_review_required" },
                "confidence": if blockers.is_empty() { "high" } else { "medium" },
                "priority_score": grouped_priority_score(&grouped, priority_by_hash),
                "finding_count": grouped.len(),
                "affected_files": affected_files_for_findings(&grouped),
                "shared_owner": caller_json(caller),
                "blockers": blockers,
                "findings": finding_refs(&grouped, priority_by_hash),
            })
        })
        .collect()
}

fn file_hotspot_problem_clusters<'a>(
    findings: &'a [Finding],
    priority_by_hash: &BTreeMap<String, &'a PriorityItem>,
) -> Vec<Value> {
    let mut by_file = BTreeMap::<String, Vec<&Finding>>::new();
    for finding in findings {
        for path in finding
            .instances
            .iter()
            .map(|instance| instance.path.clone())
            .collect::<BTreeSet<_>>()
        {
            by_file.entry(path).or_default().push(finding);
        }
    }
    by_file
        .into_iter()
        .filter(|(path, grouped)| production_path(path) && grouped.len() >= 5)
        .map(|(cluster_key, grouped)| {
            let kind_counts = finding_kind_counts(&grouped);
            json!({
                "problem_kind": "same_file_refactor_hotspot",
                "cluster_key": cluster_key,
                "action_hint": "plan_file_level_repair_batch",
                "confidence": "medium",
                "priority_score": grouped_priority_score(&grouped, priority_by_hash),
                "finding_count": grouped.len(),
                "affected_files": affected_files_for_findings(&grouped),
                "kind_counts": kind_counts,
                "blockers": file_hotspot_blockers(&grouped),
                "findings": finding_refs_limited(&grouped, priority_by_hash, 20),
            })
        })
        .collect()
}

fn module_group_problem_clusters(
    priority_order: &[PriorityItem],
    graph: &ModuleGroupGraph,
) -> Vec<Value> {
    let mut by_group = BTreeMap::<String, Vec<&PriorityItem>>::new();
    for item in priority_order {
        for group in &item.source_groups {
            by_group.entry(group.clone()).or_default().push(item);
        }
    }
    by_group
        .into_iter()
        .filter(|(_, grouped)| grouped.len() >= 10)
        .map(|(cluster_key, grouped)| {
            let blockers = if cluster_key == "__unassigned__" {
                vec!["module_group_contract_missing_or_unassigned".to_string()]
            } else {
                Vec::new()
            };
            json!({
                "problem_kind": "module_group_refactor_hotspot",
                "cluster_key": cluster_key.clone(),
                "action_hint": if blockers.is_empty() { "plan_module_group_repair_wave" } else { "fix_module_group_contract_before_repair_wave" },
                "confidence": if blockers.is_empty() { "medium" } else { "low" },
                "priority_score": grouped.iter().take(20).map(|item| item.score).sum::<usize>(),
                "finding_count": grouped.len(),
                "incoming_dependency_count": graph.incoming_counts.get(&cluster_key).copied().unwrap_or(0),
                "outgoing_dependency_count": graph.outgoing_counts.get(&cluster_key).copied().unwrap_or(0),
                "affected_files": grouped.iter().flat_map(|item| item.instance_files.iter().cloned()).collect::<BTreeSet<_>>().into_iter().collect::<Vec<_>>(),
                "kind_counts": priority_kind_counts(&grouped),
                "blockers": blockers,
                "findings": priority_refs_limited(&grouped, 20),
            })
        })
        .collect()
}

fn duplicate_shape_problem_clusters<'a>(
    findings: &'a [Finding],
    priority_by_hash: &BTreeMap<String, &'a PriorityItem>,
) -> Vec<Value> {
    findings
        .iter()
        .filter(|finding| {
            finding.kind == "duplicate_structural_hash"
                && finding.instance_count >= 5
                && finding
                    .instances
                    .iter()
                    .filter(|instance| production_path(&instance.path))
                    .count()
                    >= 2
        })
        .map(|finding| {
            let grouped = vec![finding];
            let blockers = duplicate_shape_blockers(finding);
            json!({
                "problem_kind": "large_duplicate_shape_batch",
                "cluster_key": finding.hash,
                "action_hint": if blockers.is_empty() { "extract_or_contract_review_batch" } else { "design_review_before_unification" },
                "confidence": if blockers.is_empty() { "medium" } else { "low" },
                "priority_score": priority_by_hash.get(&finding.hash).map(|item| item.score).unwrap_or_default(),
                "finding_count": 1,
                "instance_count": finding.instance_count,
                "affected_files": affected_files_for_findings(&grouped),
                "blockers": blockers,
                "findings": finding_refs(&grouped, priority_by_hash),
            })
        })
        .collect()
}

fn review_blocker_problem_clusters(priority_order: &[PriorityItem]) -> Vec<Value> {
    let mut by_blocker = BTreeMap::<String, Vec<&PriorityItem>>::new();
    for item in priority_order {
        for blocker in repair_blockers(item) {
            by_blocker.entry(blocker).or_default().push(item);
        }
    }
    by_blocker
        .into_iter()
        .filter(|(_, grouped)| grouped.len() >= 3)
        .map(|(cluster_key, grouped)| {
            json!({
                "problem_kind": "review_blocker_cluster",
                "cluster_key": cluster_key.clone(),
                "action_hint": "resolve_policy_or_design_boundary_before_bulk_repair",
                "confidence": "high",
                "priority_score": grouped.iter().take(20).map(|item| item.score).sum::<usize>(),
                "finding_count": grouped.len(),
                "affected_files": grouped.iter().flat_map(|item| item.instance_files.iter().cloned()).collect::<BTreeSet<_>>().into_iter().collect::<Vec<_>>(),
                "blockers": [cluster_key],
                "findings": priority_refs_limited(&grouped, 20),
            })
        })
        .collect()
}

fn callee_key(callee: &CalleeEvidence) -> String {
    format!(
        "{}:{}-{}:{}",
        callee.path, callee.line_start, callee.line_end, callee.qualname
    )
}

fn caller_key(caller: &CallerEvidence) -> String {
    format!(
        "{}:{}-{}:{}",
        caller.path, caller.line_start, caller.line_end, caller.qualname
    )
}

fn same_callee_batch_blockers(findings: &[&Finding]) -> Vec<String> {
    let mut blockers = BTreeSet::new();
    for finding in findings {
        for instance in &finding.instances {
            if instance.qualname.contains(".__") {
                blockers.insert("dunder_or_operator_contract".to_string());
            }
            if !production_path(&instance.path) {
                blockers.insert("contains_non_production_wrapper".to_string());
            }
        }
        if finding.public_api.unwrap_or(false) {
            blockers.insert("public_api_wrapper".to_string());
        }
    }
    blockers.into_iter().collect()
}

fn same_owner_batch_blockers(findings: &[&Finding]) -> Vec<String> {
    let mut blockers = BTreeSet::new();
    for finding in findings {
        if finding.role != "implementation" {
            blockers.insert(format!("non_implementation_role:{}", finding.role));
        }
        if finding.block_kind == "Alias" {
            blockers.insert("alias_requires_design_review".to_string());
        }
        for instance in &finding.instances {
            if !production_path(&instance.path) {
                blockers.insert("contains_non_production_target".to_string());
            }
        }
    }
    blockers.into_iter().collect()
}

fn file_hotspot_blockers(findings: &[&Finding]) -> Vec<String> {
    let mut blockers = BTreeSet::new();
    if findings
        .iter()
        .any(|finding| finding.role == "protocol" || finding.role == "alias")
    {
        blockers.insert("contains_protocol_or_alias_findings".to_string());
    }
    if findings.iter().any(|finding| finding.block_kind == "Class") {
        blockers.insert("contains_class_contract_findings".to_string());
    }
    blockers.into_iter().collect()
}

fn duplicate_shape_blockers(finding: &Finding) -> Vec<String> {
    let mut blockers = BTreeSet::new();
    if finding.role != "implementation" {
        blockers.insert(format!("non_implementation_role:{}", finding.role));
    }
    if finding.module_scope == "CrossModule" {
        blockers.insert("cross_module_contract_review".to_string());
    }
    if finding.block_kind == "Class" && finding.token_count <= 100 {
        blockers.insert("thin_class_contract_review".to_string());
    }
    blockers.into_iter().collect()
}

fn grouped_priority_score(
    findings: &[&Finding],
    priority_by_hash: &BTreeMap<String, &PriorityItem>,
) -> usize {
    findings
        .iter()
        .filter_map(|finding| priority_by_hash.get(&finding.hash).map(|item| item.score))
        .take(20)
        .sum()
}

fn affected_files_for_findings(findings: &[&Finding]) -> Vec<String> {
    findings
        .iter()
        .flat_map(|finding| {
            finding
                .instances
                .iter()
                .map(|instance| instance.path.clone())
        })
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn finding_kind_counts(findings: &[&Finding]) -> BTreeMap<String, usize> {
    let mut counts = BTreeMap::new();
    for finding in findings {
        *counts.entry(finding.kind.clone()).or_default() += 1;
    }
    counts
}

fn priority_kind_counts(items: &[&PriorityItem]) -> BTreeMap<String, usize> {
    let mut counts = BTreeMap::new();
    for item in items {
        *counts.entry(item.kind.clone()).or_default() += 1;
    }
    counts
}

fn finding_refs(
    findings: &[&Finding],
    priority_by_hash: &BTreeMap<String, &PriorityItem>,
) -> Vec<Value> {
    finding_refs_limited(findings, priority_by_hash, usize::MAX)
}

fn finding_refs_limited(
    findings: &[&Finding],
    priority_by_hash: &BTreeMap<String, &PriorityItem>,
    limit: usize,
) -> Vec<Value> {
    findings
        .iter()
        .take(limit)
        .map(|finding| {
            let priority = priority_by_hash.get(&finding.hash);
            json!({
                "kind": finding.kind,
                "hash": finding.hash,
                "rank": priority.map(|item| item.rank),
                "score": priority.map(|item| item.score),
                "representative_instances": finding.instances.iter().take(5).map(|instance| {
                    format!("{}:{}-{}:{}", instance.path, instance.line_start, instance.line_end, instance.qualname)
                }).collect::<Vec<_>>(),
            })
        })
        .collect()
}

fn priority_refs_limited(items: &[&PriorityItem], limit: usize) -> Vec<Value> {
    items
        .iter()
        .take(limit)
        .map(|item| {
            json!({
                "kind": item.kind,
                "hash": item.hash,
                "rank": item.rank,
                "score": item.score,
                "source_groups": item.source_groups,
                "representative_instances": item.representative_instances,
            })
        })
        .collect()
}

fn repair_blockers(item: &PriorityItem) -> Vec<String> {
    let mut blockers = Vec::new();
    if item.role != "implementation" {
        blockers.push(format!("non_implementation_role:{}", item.role));
    }
    if item.block_kind == "Alias" {
        blockers.push("alias_requires_design_review".to_string());
    }
    if item.block_kind == "Function"
        && item.parameter_count == 0
        && item.module_scope == "SameModule"
        && same_owner_methods(item)
    {
        blockers.push("same_owner_parameterless_method_variants".to_string());
    }
    if item.block_kind == "Function"
        && item.module_scope == "SameModule"
        && same_owner_methods(item)
        && cond_body_pair_methods(item)
    {
        blockers.push("same_owner_cond_body_pair_variants".to_string());
    }
    if item.block_kind == "Function"
        && item.parameter_count <= 1
        && item.module_scope == "SameModule"
        && item.instance_files.len() == 1
        && item.representative_instances.len() == 2
        && all_method_instances(item)
        && !same_owner_methods(item)
    {
        blockers.push("cross_owner_small_method_variants".to_string());
    }
    if item.block_kind == "Class" && item.token_count <= 20 && item.source_groups.len() > 1 {
        blockers.push("thin_marker_class_crosses_design_groups".to_string());
    }
    if item.block_kind == "Class" && item.token_count <= 100 && item.source_groups.len() > 1 {
        blockers.push("thin_data_carrier_class_crosses_design_groups".to_string());
    }
    if item
        .source_groups
        .iter()
        .any(|group| group == "__unassigned__")
        && item.source_groups.len() == 1
    {
        blockers.push("unassigned_only_scope".to_string());
    }
    if item.kind == "single_caller_structural_helper"
        || item.kind == "single_callee_structural_wrapper"
    {
        if item.production_instance_count == 0 {
            blockers.push("non_production_single_owner_or_callee".to_string());
        }
    } else if item.production_instance_count < 2 {
        blockers.push("insufficient_production_instances".to_string());
    }
    blockers
}

fn same_owner_methods(item: &PriorityItem) -> bool {
    let mut owners = BTreeSet::new();
    for instance in &item.representative_instances {
        let Some(qualname) = instance.rsplit_once(':').map(|(_, qualname)| qualname) else {
            return false;
        };
        let Some((owner, _method)) = qualname.rsplit_once('.') else {
            return false;
        };
        owners.insert(owner.to_string());
    }
    owners.len() == 1 && item.representative_instances.len() >= 2
}

fn all_method_instances(item: &PriorityItem) -> bool {
    item.representative_instances.iter().all(|instance| {
        let Some(qualname) = instance.rsplit_once(':').map(|(_, qualname)| qualname) else {
            return false;
        };
        qualname.contains('.')
    })
}

fn cond_body_pair_methods(item: &PriorityItem) -> bool {
    let method_names = item
        .representative_instances
        .iter()
        .filter_map(|instance| {
            let qualname = instance.rsplit_once(':').map(|(_, qualname)| qualname)?;
            let (_, method) = qualname.rsplit_once('.')?;
            Some(method.to_string())
        })
        .collect::<BTreeSet<_>>();
    method_names.len() == 2
        && method_names.contains("cond_fun")
        && method_names.contains("body_fun")
}

fn preferred_home_group(item: &PriorityItem, graph: &ModuleGroupGraph) -> String {
    item.source_groups
        .iter()
        .max_by(|left, right| {
            let left_in = graph.incoming_counts.get(*left).copied().unwrap_or(0);
            let right_in = graph.incoming_counts.get(*right).copied().unwrap_or(0);
            let left_out = graph.outgoing_counts.get(*left).copied().unwrap_or(0);
            let right_out = graph.outgoing_counts.get(*right).copied().unwrap_or(0);
            left_in
                .cmp(&right_in)
                .then_with(|| right_out.cmp(&left_out))
                .then_with(|| right.cmp(left))
        })
        .cloned()
        .unwrap_or_else(|| "__unassigned__".to_string())
}

fn downstream_groups(home_group: &str, graph: &ModuleGroupGraph) -> Vec<String> {
    graph
        .edge_counts
        .iter()
        .filter_map(|((source, target), _)| {
            if target == home_group {
                Some(source.clone())
            } else {
                None
            }
        })
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn module_group_graph(
    findings: &[Finding],
    root: &Path,
    analyzed_files: &[String],
    contract: Option<&ModuleGroupContract>,
) -> ModuleGroupGraph {
    let mut group_files = BTreeMap::<String, BTreeSet<String>>::new();
    let mut edge_counts = BTreeMap::<(String, String), usize>::new();
    for path in analyzed_files {
        group_files
            .entry(file_group(path, contract))
            .or_default()
            .insert(path.clone());
    }
    for finding in findings {
        for instance in &finding.instances {
            let source_group = file_group(&instance.path, contract);
            group_files
                .entry(source_group.clone())
                .or_default()
                .insert(instance.path.clone());
            for target in repo_import_targets_for_instance(root, instance) {
                let target_group = file_group(&target, contract);
                group_files
                    .entry(target_group.clone())
                    .or_default()
                    .insert(target);
                if source_group != target_group {
                    *edge_counts
                        .entry((source_group.clone(), target_group))
                        .or_default() += 1;
                }
            }
        }
    }
    let mut incoming_counts = BTreeMap::<String, usize>::new();
    let mut outgoing_counts = BTreeMap::<String, usize>::new();
    for ((source, target), count) in &edge_counts {
        *outgoing_counts.entry(source.clone()).or_default() += count;
        *incoming_counts.entry(target.clone()).or_default() += count;
    }
    let file_counts = group_files
        .into_iter()
        .map(|(group, files)| (group, files.len()))
        .collect();
    ModuleGroupGraph {
        file_counts,
        incoming_counts,
        outgoing_counts,
        edge_counts,
    }
}

fn group_graph_json(graph: &ModuleGroupGraph) -> Value {
    let mut nodes = graph
        .file_counts
        .iter()
        .map(|(group, file_count)| {
            json!({
                "group": group,
                "file_count": file_count,
                "incoming_dependency_count": graph.incoming_counts.get(group).copied().unwrap_or(0),
                "outgoing_dependency_count": graph.outgoing_counts.get(group).copied().unwrap_or(0),
            })
        })
        .collect::<Vec<_>>();
    nodes.sort_by(|left, right| {
        right["incoming_dependency_count"]
            .as_u64()
            .cmp(&left["incoming_dependency_count"].as_u64())
            .then_with(|| left["group"].as_str().cmp(&right["group"].as_str()))
    });
    let edges = graph
        .edge_counts
        .iter()
        .map(|((source, target), count)| {
            json!({
                "source_group": source,
                "target_group": target,
                "count": count,
            })
        })
        .collect::<Vec<_>>();
    json!({
        "nodes": nodes,
        "edges": edges,
    })
}

fn finding_source_groups(finding: &Finding, contract: Option<&ModuleGroupContract>) -> Vec<String> {
    let groups = finding
        .instances
        .iter()
        .map(|instance| file_group(&instance.path, contract))
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let assigned = groups
        .iter()
        .filter(|group| !matches!(group.as_str(), "__unassigned__" | "__missing_contract__"))
        .cloned()
        .collect::<Vec<_>>();
    if assigned.is_empty() {
        groups
    } else {
        assigned
    }
}

fn file_group(path: &str, contract: Option<&ModuleGroupContract>) -> String {
    group_for_path(path, contract)
}

fn import_target_counts(findings: &[Finding], root: &Path) -> BTreeMap<String, usize> {
    let mut counts = BTreeMap::new();
    for finding in findings {
        for instance in &finding.instances {
            for target in repo_import_targets_for_instance(root, instance) {
                *counts.entry(target).or_default() += 1;
            }
        }
    }
    counts
}

fn import_analysis_targets(finding: &Finding, root: &Path) -> Vec<String> {
    let mut targets = BTreeSet::new();
    for instance in &finding.instances {
        targets.extend(repo_import_targets_for_instance(root, instance));
    }
    targets.into_iter().collect()
}

fn production_path(path: &str) -> bool {
    (path.starts_with("python/") || path.starts_with("src/"))
        && !path.contains("/tests/")
        && !path.starts_with("tests/")
}

fn import_analysis_json(finding: &Finding, root: &Path) -> Value {
    let mut union = BTreeSet::<String>::new();
    let mut common: Option<BTreeSet<String>> = None;
    let mut repo_targets = BTreeSet::new();
    let mut by_instance = Vec::new();
    for instance in &finding.instances {
        let facts = instance
            .import_facts
            .iter()
            .cloned()
            .collect::<BTreeSet<_>>();
        union.extend(facts.iter().cloned());
        let instance_repo_targets = repo_import_targets_for_instance(root, instance);
        repo_targets.extend(instance_repo_targets.iter().cloned());
        common = Some(match common {
            Some(current) => current.intersection(&facts).cloned().collect(),
            None => facts,
        });
        by_instance.push(json!({
            "path": instance.path,
            "qualname": instance.qualname,
            "imports_hash": instance.imports_hash,
            "import_facts": instance.import_facts,
            "external_libraries": external_libraries(&instance.import_facts),
            "repo_import_targets": instance_repo_targets,
        }));
    }
    let common = common.unwrap_or_default();
    let varying = union.difference(&common).cloned().collect::<Vec<_>>();
    json!({
        "common_import_facts": common.into_iter().collect::<Vec<_>>(),
        "varying_import_facts": varying,
        "all_external_libraries": external_libraries(&union.into_iter().collect::<Vec<_>>()),
        "repo_dependency_count": repo_targets.len(),
        "repo_import_targets": repo_targets.into_iter().collect::<Vec<_>>(),
        "by_instance": by_instance,
    })
}

fn repo_import_targets(findings: &[Finding], root: &Path) -> Vec<String> {
    let mut targets = BTreeSet::new();
    for finding in findings {
        for instance in &finding.instances {
            targets.extend(repo_import_targets_for_instance(root, instance));
        }
    }
    targets.into_iter().collect()
}

fn repo_import_targets_for_instance(root: &Path, instance: &Instance) -> Vec<String> {
    let mut targets = BTreeSet::new();
    for fact in &instance.import_facts {
        for module in imported_modules(&instance.module, fact) {
            for target in module_file_candidates(root, &module) {
                targets.insert(target);
            }
        }
    }
    targets.into_iter().collect()
}

fn imported_modules(current_module: &str, fact: &str) -> Vec<String> {
    if let Some(module) = fact.strip_prefix("import:") {
        return vec![module.to_string()];
    }
    let Some(rest) = fact.strip_prefix("from:") else {
        return Vec::new();
    };
    let Some((module, name)) = rest.split_once(':') else {
        return Vec::new();
    };
    let Some(resolved) = resolve_import_module(current_module, module) else {
        return Vec::new();
    };
    let mut modules = vec![resolved.clone()];
    if !name.is_empty() && name != "*" {
        modules.push(format!("{resolved}.{name}"));
    }
    modules
}

fn resolve_import_module(current_module: &str, module: &str) -> Option<String> {
    if !module.starts_with('.') {
        return Some(module.to_string());
    }
    let dots = module.chars().take_while(|value| *value == '.').count();
    let suffix = module.trim_start_matches('.');
    let mut package = current_module
        .split('.')
        .map(str::to_string)
        .collect::<Vec<_>>();
    package.pop();
    let drop_count = dots.saturating_sub(1);
    if drop_count > package.len() {
        return None;
    }
    let keep = package.len() - drop_count;
    package.truncate(keep);
    if !suffix.is_empty() {
        package.extend(suffix.split('.').map(str::to_string));
    }
    if package.is_empty() {
        None
    } else {
        Some(package.join("."))
    }
}

fn module_file_candidates(root: &Path, module: &str) -> Vec<String> {
    let relative = module.replace('.', "/");
    let mut candidates = Vec::new();
    for source_root in ["", "python", "src"] {
        let base = if source_root.is_empty() {
            root.to_path_buf()
        } else {
            root.join(source_root)
        };
        candidates.push(base.join(format!("{relative}.py")));
        candidates.push(base.join(&relative).join("__init__.py"));
    }
    candidates
        .into_iter()
        .filter(|path| exact_file_exists(path))
        .map(|path| relative_path(root, &path))
        .collect()
}

fn exact_file_exists(path: &Path) -> bool {
    if !path.is_file() {
        return false;
    }
    let Some(parent) = path.parent() else {
        return false;
    };
    let Some(file_name) = path.file_name() else {
        return false;
    };
    let Ok(entries) = fs::read_dir(parent) else {
        return false;
    };
    entries
        .flatten()
        .any(|entry| entry.file_name() == file_name)
}

fn relative_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn external_libraries(import_facts: &[String]) -> Vec<String> {
    let mut libraries = BTreeSet::new();
    for fact in import_facts {
        let Some(imported) = fact
            .strip_prefix("import:")
            .or_else(|| fact.strip_prefix("from:"))
        else {
            continue;
        };
        let module = imported.split(':').next().unwrap_or("");
        if module.is_empty() || module.starts_with('.') {
            continue;
        }
        let root = module.split('.').next().unwrap_or(module);
        if !is_likely_stdlib(root) {
            libraries.insert(root.to_string());
        }
    }
    libraries.into_iter().collect()
}

fn is_likely_stdlib(root: &str) -> bool {
    matches!(
        root,
        "__future__"
            | "abc"
            | "argparse"
            | "ast"
            | "collections"
            | "contextlib"
            | "dataclasses"
            | "functools"
            | "hashlib"
            | "io"
            | "json"
            | "math"
            | "os"
            | "pathlib"
            | "re"
            | "subprocess"
            | "sys"
            | "tempfile"
            | "textwrap"
            | "typing"
    )
}

fn instance_json(instance: &Instance) -> Value {
    json!({
        "raw_instance": instance.raw_instance,
        "path": instance.path,
        "line_start": instance.line_start,
        "line_end": instance.line_end,
        "module": instance.module,
        "qualname": instance.qualname,
        "parent": instance.parent,
        "imports_hash": instance.imports_hash,
        "decorators_hash": instance.decorators_hash,
        "bases_hash": instance.bases_hash,
        "context_hash": instance.context_hash,
        "import_facts": instance.import_facts,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_finding_without_losing_raw_text() {
        let line = "PY_STRUCTURE_HASH_FINDING=duplicate_structural_hash:role=implementation:Function:params=1:tokens=24:hash=abc:count=1:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/a.py:10-12:pkg.a:Cls.fn:parent=Class:Cls:imports=i:decorators=d:bases=b:context=c";
        let mut cache = BTreeMap::new();
        let finding = parse_finding(line, Path::new("."), &mut cache).expect("finding parses");
        assert_eq!(finding.raw_line, line);
        assert_eq!(finding.role, "implementation");
        assert_eq!(finding.instances[0].parent, "Class:Cls");
        assert_eq!(
            finding.instances[0].raw_instance,
            "pkg/a.py:10-12:pkg.a:Cls.fn:parent=Class:Cls:imports=i:decorators=d:bases=b:context=c"
        );
    }

    #[test]
    fn structures_summary_lines() {
        let text = "PY_STRUCTURE_HASH_FINDING=duplicate_structural_hash:role=alias:Alias:params=0:tokens=13:hash=h:count=1:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/a.py:1-1:pkg.a:Name:parent=<module>:imports=i:decorators=d:bases=b:context=c\nPY_STRUCTURE_HASH_ANALYZED_FILES=1\nPY_STRUCTURE_HASH_ANALYZED_FILE=pkg/a.py\nPY_STRUCTURE_HASH_DUPLICATE_GROUPS=1\nPY_STRUCTURE_HASH_SINGLE_CALLER_FINDINGS=0\nPY_STRUCTURE_HASH_GROUPS=1\nPY_STRUCTURE_HASH=fail\n";
        let payload = structure_text(text, Path::new(".")).expect("report structures");
        assert_eq!(payload["summary"]["reported_duplicate_group_count"], 1);
        assert_eq!(
            payload["summary"]["reported_single_caller_finding_count"],
            0
        );
        assert_eq!(payload["summary"]["parsed_group_count"], 1);
        assert_eq!(payload["summary"]["parsed_analyzed_file_count"], 1);
        assert_eq!(payload["findings"][0]["instances"][0]["qualname"], "Name");
    }

    #[test]
    fn parses_single_caller_finding_with_call_site_evidence() {
        let text = "PY_STRUCTURE_HASH_FINDING=single_caller_structural_helper:role=implementation:Function:params=1:tokens=24:hash=h:count=1:caller_count=1:call_site_count=2:caller=pkg/a.py@10-14@pkg.a@public_api@sites=11|12:similar_callers=pkg/a.py@20-24@pkg.a@other_api@tokens=18@structure=peerhash@parent=<module>@score=6@shared=2@profile=load_config|validate_inputs@reasons=shared_call_profile:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/a.py:1-3:pkg.a:_helper:parent=<module>:imports=i:decorators=d:bases=b:context=c\nPY_STRUCTURE_HASH_GROUPS=1\nPY_STRUCTURE_HASH=fail\n";
        let payload = structure_text(text, Path::new(".")).expect("report structures");
        assert_eq!(
            payload["findings"][0]["kind"],
            "single_caller_structural_helper"
        );
        assert_eq!(
            payload["findings"][0]["why"]["primary"],
            "single_caller_structural_helper"
        );
        assert_eq!(payload["findings"][0]["caller_analysis"]["caller_count"], 1);
        assert_eq!(
            payload["findings"][0]["caller_analysis"]["callers"][0]["call_lines"][1],
            12
        );
        assert_eq!(
            payload["findings"][0]["caller_analysis"]["similar_responsibility_callers"][0]
                ["qualname"],
            "other_api"
        );
        assert_eq!(
            payload["findings"][0]["caller_analysis"]["similar_responsibility_callers"][0]
                ["shared_call_count"],
            2
        );
        assert_eq!(
            payload["findings"][0]["caller_analysis"]["similar_responsibility_callers"][0]
                ["token_count"],
            18
        );
        assert_eq!(
            payload["findings"][0]["caller_analysis"]["similar_responsibility_callers"][0]
                ["shared_profile"][1],
            "validate_inputs"
        );
        assert_eq!(
            payload["findings"][0]["caller_analysis"]["integration_candidates"][0]
                ["candidate_kind"],
            "inline_target_into_owner"
        );
        assert_eq!(
            payload["findings"][0]["caller_analysis"]["integration_candidates"][0]
                ["candidate_schema_scope"],
            "dependency_enriched"
        );
        assert_eq!(
            payload["findings"][0]["caller_analysis"]["integration_candidates"][1]
                ["candidate_kind"],
            "consolidate_owner_with_similar_responsibility_caller"
        );
        assert_eq!(
            payload["findings"][0]["caller_analysis"]["integration_candidates"][1]["features"][0]
                ["code"],
            "unique_owner"
        );
    }

    #[test]
    fn parses_single_callee_wrapper_with_callee_evidence() {
        let text = "PY_STRUCTURE_HASH_FINDING=single_callee_structural_wrapper:role=implementation:Function:params=1:tokens=24:hash=h:count=1:callee_count=1:call_site_count=2:public_api=false:callee=pkg/a.py@1-3@pkg.a@_target@sites=11|12:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/a.py:10-14:pkg.a:_wrapper:parent=<module>:imports=i:decorators=d:bases=b:context=c\nPY_STRUCTURE_HASH_SINGLE_CALLEE_FINDINGS=1\nPY_STRUCTURE_HASH_GROUPS=1\nPY_STRUCTURE_HASH=fail\n";
        let payload = structure_text(text, Path::new(".")).expect("report structures");
        assert_eq!(
            payload["summary"]["reported_single_callee_finding_count"],
            1
        );
        assert_eq!(
            payload["findings"][0]["kind"],
            "single_callee_structural_wrapper"
        );
        assert_eq!(payload["findings"][0]["public_api"], false);
        assert_eq!(
            payload["findings"][0]["callee_analysis"]["callees"][0]["qualname"],
            "_target"
        );
        assert_eq!(
            payload["findings"][0]["callee_analysis"]["callees"][0]["call_lines"][1],
            12
        );
        assert_eq!(
            payload["findings"][0]["callee_analysis"]["integration_candidates"][0]
                ["candidate_kind"],
            "inline_or_merge_non_public_single_callee_wrapper"
        );
    }

    #[test]
    fn structures_mechanical_problem_cluster_for_shared_callee_wrappers() {
        let text = "PY_STRUCTURE_HASH_FINDING=single_callee_structural_wrapper:role=implementation:Function:params=1:tokens=24:hash=h1:count=1:callee_count=1:call_site_count=1:public_api=false:callee=pkg/a.py@1-3@pkg.a@_target@sites=11:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/a.py:10-14:pkg.a:_wrapper_one:parent=<module>:imports=i:decorators=d:bases=b:context=c\nPY_STRUCTURE_HASH_FINDING=single_callee_structural_wrapper:role=implementation:Function:params=1:tokens=20:hash=h2:count=1:callee_count=1:call_site_count=1:public_api=false:callee=pkg/a.py@1-3@pkg.a@_target@sites=21:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/a.py:20-24:pkg.a:_wrapper_two:parent=<module>:imports=i:decorators=d:bases=b:context=c\nPY_STRUCTURE_HASH_SINGLE_CALLEE_FINDINGS=2\nPY_STRUCTURE_HASH_GROUPS=2\nPY_STRUCTURE_HASH=fail\n";
        let payload = structure_text(text, Path::new(".")).expect("report structures");
        let clusters = payload["summary"]["mechanical_problem_clusters"]
            .as_array()
            .expect("mechanical problem clusters");
        let shared_callee = clusters
            .iter()
            .find(|cluster| cluster["problem_kind"] == "same_callee_wrapper_batch")
            .expect("shared callee cluster");
        assert_eq!(shared_callee["finding_count"], 2);
        assert_eq!(shared_callee["shared_target"]["qualname"], "_target");
        assert_eq!(
            shared_callee["findings"][0]["representative_instances"][0],
            "pkg/a.py:10-14:_wrapper_one"
        );
    }

    #[test]
    fn parses_legacy_single_caller_without_similar_callers() {
        let text = "PY_STRUCTURE_HASH_FINDING=single_caller_structural_helper:role=implementation:Class:params=0:tokens=30:hash=h:count=1:caller_count=1:call_site_count=1:caller=pkg/a.py@10-14@pkg.a@build_api@sites=11:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/a.py:1-8:pkg.a:_Carry:parent=<module>:imports=i:decorators=d:bases=b:context=c\nPY_STRUCTURE_HASH_GROUPS=1\nPY_STRUCTURE_HASH=fail\n";
        let payload = structure_text(text, Path::new(".")).expect("legacy report structures");
        assert_eq!(
            payload["findings"][0]["caller_analysis"]["similar_responsibility_callers"]
                .as_array()
                .expect("similar caller list")
                .len(),
            0
        );
        assert!(
            payload["findings"][0]["caller_analysis"]["integration_candidates"][0]["features"]
                .as_array()
                .expect("features")
                .iter()
                .any(|feature| feature["code"] == "ast_structural_type_target")
        );
    }

    #[test]
    fn class_single_owner_struct_gets_inline_candidate_when_usage_is_local() {
        let root = temp_report_root("inline-struct");
        let path = root.join("pkg/a.py");
        fs::create_dir_all(path.parent().expect("parent")).expect("create package dir");
        fs::write(
            &path,
            r#"from dataclasses import dataclass

@dataclass(frozen=True)
class _Bundle:
    left: int
    right: int

def build_api():
    bundle = _Bundle(1, 2)
    return bundle.left + bundle.right
"#,
        )
        .expect("write source");
        let text = "PY_STRUCTURE_HASH_FINDING=single_caller_structural_helper:role=implementation:Class:params=0:tokens=30:hash=h:count=1:caller_count=1:call_site_count=1:caller=pkg/a.py@8-10@pkg.a@build_api@sites=9:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/a.py:4-6:pkg.a:_Bundle:parent=<module>:imports=i:decorators=d:bases=b:context=c\nPY_STRUCTURE_HASH_GROUPS=1\nPY_STRUCTURE_HASH=fail\n";
        let payload = structure_text(text, &root).expect("report structures");
        assert_eq!(
            payload["findings"][0]["internal_struct_analysis"]["decision"],
            "inline_candidate"
        );
        assert_eq!(
            payload["findings"][0]["caller_analysis"]["integration_candidates"][0]
                ["candidate_kind"],
            "inline_single_owner_internal_struct"
        );
        fs::remove_dir_all(root).expect("remove temp root");
    }

    #[test]
    fn class_single_owner_struct_preserves_pytree_contracts() {
        let root = temp_report_root("preserve-struct");
        let path = root.join("pkg/a.py");
        fs::create_dir_all(path.parent().expect("parent")).expect("create package dir");
        fs::write(
            &path,
            r#"from dataclasses import dataclass
import jax

@jax.tree_util.register_pytree_node_class
@dataclass(frozen=True)
class _Carry:
    value: int

    def tree_flatten(self):
        return (self.value,), None

    @classmethod
    def tree_unflatten(cls, aux_data, children):
        return cls(children[0])

def build_api():
    carry = _Carry(1)
    return carry
"#,
        )
        .expect("write source");
        let text = "PY_STRUCTURE_HASH_FINDING=single_caller_structural_helper:role=implementation:Class:params=0:tokens=80:hash=h:count=1:caller_count=1:call_site_count=1:caller=pkg/a.py@16-18@pkg.a@build_api@sites=17:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/a.py:6-14:pkg.a:_Carry:parent=<module>:imports=i:decorators=d:bases=b:context=c\nPY_STRUCTURE_HASH_GROUPS=1\nPY_STRUCTURE_HASH=fail\n";
        let payload = structure_text(text, &root).expect("report structures");
        assert_eq!(
            payload["findings"][0]["internal_struct_analysis"]["decision"],
            "preserve_candidate"
        );
        assert_eq!(
            payload["findings"][0]["caller_analysis"]["integration_candidates"][0]
                ["candidate_kind"],
            "preserve_internal_struct_contract"
        );
        fs::remove_dir_all(root).expect("remove temp root");
    }

    #[test]
    fn class_single_owner_struct_allows_single_callee_attribute_scope() {
        let root = temp_report_root("inline-struct-single-callee");
        let path = root.join("pkg/a.py");
        fs::create_dir_all(path.parent().expect("parent")).expect("create package dir");
        fs::write(
            &path,
            r#"from dataclasses import dataclass

@dataclass(frozen=True)
class _Bundle:
    left: int
    right: int

def consume(bundle):
    return bundle.left + bundle.right

def build_api():
    bundle = _Bundle(1, 2)
    return consume(bundle)
"#,
        )
        .expect("write source");
        let text = "PY_STRUCTURE_HASH_FINDING=single_caller_structural_helper:role=implementation:Class:params=0:tokens=30:hash=h:count=1:caller_count=1:call_site_count=1:caller=pkg/a.py@11-13@pkg.a@build_api@sites=12:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/a.py:4-6:pkg.a:_Bundle:parent=<module>:imports=i:decorators=d:bases=b:context=c\nPY_STRUCTURE_HASH_GROUPS=1\nPY_STRUCTURE_HASH=fail\n";
        let payload = structure_text(text, &root).expect("report structures");
        assert_eq!(
            payload["findings"][0]["internal_struct_analysis"]["decision"],
            "inline_candidate"
        );
        assert_eq!(
            payload["findings"][0]["internal_struct_analysis"]["usage_facts"]
                ["attribute_read_scope"],
            "single_callee"
        );
        fs::remove_dir_all(root).expect("remove temp root");
    }

    #[test]
    fn class_single_owner_struct_review_blocks_returned_private_instance() {
        let root = temp_report_root("review-returned-struct");
        let path = root.join("pkg/a.py");
        fs::create_dir_all(path.parent().expect("parent")).expect("create package dir");
        fs::write(
            &path,
            r#"from dataclasses import dataclass

@dataclass(frozen=True)
class _Bundle:
    left: int

def build_api():
    bundle = _Bundle(1)
    return bundle
"#,
        )
        .expect("write source");
        let text = "PY_STRUCTURE_HASH_FINDING=single_caller_structural_helper:role=implementation:Class:params=0:tokens=30:hash=h:count=1:caller_count=1:call_site_count=1:caller=pkg/a.py@7-9@pkg.a@build_api@sites=8:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/a.py:4-5:pkg.a:_Bundle:parent=<module>:imports=i:decorators=d:bases=b:context=c\nPY_STRUCTURE_HASH_GROUPS=1\nPY_STRUCTURE_HASH=fail\n";
        let payload = structure_text(text, &root).expect("report structures");
        assert_eq!(
            payload["findings"][0]["internal_struct_analysis"]["decision"],
            "review_required"
        );
        assert!(
            payload["findings"][0]["internal_struct_analysis"]["decision_reasons"]
                .as_array()
                .expect("decision reasons")
                .iter()
                .any(|reason| reason == "returned_internal_struct_instance")
        );
        fs::remove_dir_all(root).expect("remove temp root");
    }

    #[test]
    fn class_single_owner_struct_preserves_protocol_contracts() {
        let root = temp_report_root("preserve-protocol-struct");
        let path = root.join("pkg/a.py");
        fs::create_dir_all(path.parent().expect("parent")).expect("create package dir");
        fs::write(
            &path,
            r#"from typing import Protocol

class _SupportsValue(Protocol):
    value: int

def build_api():
    return None
"#,
        )
        .expect("write source");
        let text = "PY_STRUCTURE_HASH_FINDING=single_caller_structural_helper:role=protocol:Class:params=0:tokens=30:hash=h:count=1:caller_count=1:call_site_count=0:caller=pkg/a.py@6-7@pkg.a@build_api@sites=:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/a.py:3-4:pkg.a:_SupportsValue:parent=<module>:imports=i:decorators=d:bases=Protocol:context=c\nPY_STRUCTURE_HASH_GROUPS=1\nPY_STRUCTURE_HASH=fail\n";
        let payload = structure_text(text, &root).expect("report structures");
        assert_eq!(
            payload["findings"][0]["internal_struct_analysis"]["decision"],
            "preserve_candidate"
        );
        assert!(
            payload["findings"][0]["internal_struct_analysis"]["decision_reasons"]
                .as_array()
                .expect("decision reasons")
                .iter()
                .any(|reason| reason == "protocol_or_generic_contract")
        );
        fs::remove_dir_all(root).expect("remove temp root");
    }

    #[test]
    fn same_owner_parameterless_methods_are_review_blocked() {
        let item = PriorityItem {
            rank: 1,
            score: 1,
            kind: "duplicate_structural_hash".to_string(),
            hash: "h".to_string(),
            role: "implementation".to_string(),
            block_kind: "Function".to_string(),
            instance_count: 2,
            parameter_count: 0,
            token_count: 40,
            module_scope: "SameModule".to_string(),
            import_scope: "SameImports".to_string(),
            imported_by_count: 1,
            group_imported_by_count: 1,
            repo_dependency_count: 0,
            group_dependency_count: 0,
            production_instance_count: 2,
            source_groups: vec!["jax_util_solvers".to_string()],
            representative_instances: vec![
                "python/jax_util/solvers/_preconditioners.py:44-46:InitializeConfig.identity"
                    .to_string(),
                "python/jax_util/solvers/_preconditioners.py:49-51:InitializeConfig.external"
                    .to_string(),
            ],
            instance_files: vec!["python/jax_util/solvers/_preconditioners.py".to_string()],
            reason_codes: Vec::new(),
        };
        assert_eq!(
            repair_blockers(&item),
            vec!["same_owner_parameterless_method_variants"]
        );
    }

    fn temp_report_root(label: &str) -> PathBuf {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system time")
            .as_nanos();
        std::env::temp_dir().join(format!(
            "agent-canon-python-structure-report-{label}-{}-{unique}",
            std::process::id()
        ))
    }

    #[test]
    fn cross_owner_small_methods_are_review_blocked() {
        let item = PriorityItem {
            rank: 1,
            score: 1,
            kind: "duplicate_structural_hash".to_string(),
            hash: "h".to_string(),
            role: "implementation".to_string(),
            block_kind: "Function".to_string(),
            instance_count: 2,
            parameter_count: 1,
            token_count: 47,
            module_scope: "SameModule".to_string(),
            import_scope: "SameImports".to_string(),
            imported_by_count: 1,
            group_imported_by_count: 1,
            repo_dependency_count: 0,
            group_dependency_count: 0,
            production_instance_count: 2,
            source_groups: vec!["jax_util_solvers".to_string()],
            representative_instances: vec![
                "python/jax_util/solvers/_preconditioners.py:100-102:SolveConfig.dense_eigh"
                    .to_string(),
                "python/jax_util/solvers/_preconditioners.py:164-166:State.external".to_string(),
            ],
            instance_files: vec!["python/jax_util/solvers/_preconditioners.py".to_string()],
            reason_codes: Vec::new(),
        };
        assert_eq!(
            repair_blockers(&item),
            vec!["cross_owner_small_method_variants"]
        );
    }

    #[test]
    fn same_owner_cond_body_pair_is_review_blocked() {
        let item = PriorityItem {
            rank: 1,
            score: 1,
            kind: "duplicate_structural_hash".to_string(),
            hash: "h".to_string(),
            role: "implementation".to_string(),
            block_kind: "Function".to_string(),
            instance_count: 2,
            parameter_count: 1,
            token_count: 31,
            module_scope: "SameModule".to_string(),
            import_scope: "SameImports".to_string(),
            imported_by_count: 1,
            group_imported_by_count: 1,
            repo_dependency_count: 0,
            group_dependency_count: 0,
            production_instance_count: 2,
            source_groups: vec!["jax_util_solvers".to_string()],
            representative_instances: vec![
                "python/jax_util/solvers/lobpcg.py:461-462:_block_preconditioned_rayleigh_ritz.cond_fun"
                    .to_string(),
                "python/jax_util/solvers/lobpcg.py:464-465:_block_preconditioned_rayleigh_ritz.body_fun"
                    .to_string(),
            ],
            instance_files: vec!["python/jax_util/solvers/lobpcg.py".to_string()],
            reason_codes: Vec::new(),
        };
        assert_eq!(
            repair_blockers(&item),
            vec!["same_owner_cond_body_pair_variants"]
        );
    }

    #[test]
    fn resolves_relative_import_modules() {
        assert_eq!(
            imported_modules("python.jax_util.optimizers.pdipm", "from:..base:Scalar"),
            vec![
                "python.jax_util.base".to_string(),
                "python.jax_util.base.Scalar".to_string()
            ]
        );
        assert_eq!(
            imported_modules("python.jax_util.optimizers.pdipm", "import:jax"),
            vec!["jax".to_string()]
        );
    }

    #[test]
    fn repo_import_targets_are_part_of_analysis() {
        let root = std::env::temp_dir().join(format!(
            "agent-canon-python-structure-hash-report-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&root);
        let pkg = root.join("pkg");
        fs::create_dir_all(&pkg).expect("pkg dir");
        fs::write(pkg.join("a.py"), "from .b import B\n").expect("a.py");
        fs::write(pkg.join("b.py"), "class B:\n    pass\n").expect("b.py");
        let line = "PY_STRUCTURE_HASH_FINDING=duplicate_structural_hash:role=implementation:Function:params=1:tokens=24:hash=abc:count=1:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/a.py:10-12:pkg.a:fn:parent=<module>:imports=i:decorators=d:bases=b:context=c";
        let payload = structure_text(line, &root).expect("report structures");
        assert_eq!(payload["summary"]["repo_import_target_count"], 1);
        assert_eq!(
            payload["findings"][0]["why"]["import_analysis"]["repo_import_targets"][0],
            "pkg/b.py"
        );
        fs::remove_dir_all(root).expect("cleanup temp tree");
    }

    #[test]
    fn module_group_graph_aggregates_file_dependencies() {
        let root = std::env::temp_dir().join(format!(
            "agent-canon-python-structure-hash-report-graph-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("pkg/core")).expect("core dir");
        fs::create_dir_all(root.join("pkg/app")).expect("app dir");
        fs::create_dir_all(root.join("documents/design")).expect("design dir");
        fs::write(
            root.join("documents/design/python-module-groups.toml"),
            r#"
[[module_group]]
id = "pkg/core"
label = "Core"
submodules = ["pkg/core"]

[[module_group]]
id = "pkg/app"
label = "App"
submodules = ["pkg/app"]
"#,
        )
        .expect("module group contract");
        fs::write(root.join("pkg/core/base.py"), "class Base:\n    pass\n").expect("base.py");
        fs::write(
            root.join("pkg/app/use.py"),
            "from ..core.base import Base\nclass Use:\n    pass\n",
        )
        .expect("use.py");
        let line = "PY_STRUCTURE_HASH_FINDING=duplicate_structural_hash:role=implementation:Class:params=0:tokens=24:hash=abc:count=1:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:pkg/app/use.py:2-3:pkg.app.use:Use:parent=<module>:imports=i:decorators=d:bases=b:context=c";
        let payload = structure_text(line, &root).expect("report structures");
        let graph = &payload["summary"]["module_group_graph"];
        assert_eq!(graph["edges"][0]["source_group"], "pkg/app");
        assert_eq!(graph["edges"][0]["target_group"], "pkg/core");
        assert_eq!(
            payload["summary"]["priority_order"][0]["group_imported_by_count"],
            0
        );
        fs::remove_dir_all(root).expect("cleanup temp tree");
    }
}
