// @dependency-start
// contract implementation
// responsibility Validates semantic responsibility contract instance shape, identity, and references.
// upstream design ../../../../../documents/design/semantic-responsibility-contract.md canonical contract
// upstream design ../../../../../templates/documents/semantic-responsibility-contract.template.toml reusable instance shape
// downstream test ../../../../../tests/agent_tools/test_check_semantic_responsibility_contract.py focused validator tests
// downstream design ../../../../../documents/tools/check_semantic_responsibility_contract.md reader-facing tool documentation
// @dependency-end

use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::env;
use std::ffi::OsString;
use std::fmt;
use std::fs;
use std::path::{Component, Path, PathBuf};
use toml_edit::{DocumentMut, Item, TableLike, Value as TomlEditValue};

pub const SELECTOR: &str = "check-semantic-responsibility-contract";

const SCHEMA: &str = "agent-canon.semantic_responsibility_contract.v1";
const POLICY_PATH: &str = "documents/design/semantic-responsibility-contract.md";
const TEMPLATE_PATH: &str = "templates/documents/semantic-responsibility-contract.template.toml";
const USAGE: &str = "usage: agent-canon check-semantic-responsibility-contract [-h] [paths ...] [--root ROOT] [--template TEMPLATE] [--instance INSTANCE] [--artifact-root ARTIFACT_ROOT] [--format {text,json}]";
const HARD_EDGES: &[&str] = &[
    "invariant",
    "atomic_transition",
    "transaction",
    "lifecycle",
    "effect",
    "consistency",
    "substitutability",
];
const OWNER_KINDS: &[&str] = &[
    "compiler",
    "static_checker",
    "design_review",
    "existing_test",
    "test_extension",
    "new_test",
    "experiment",
    "formal_proof",
];
const ROOT_FIELDS: &[&str] = &[
    "schema",
    "instance_kind",
    "policy_ref",
    "active_design_packet_ref",
    "run_id",
    "task_id",
    "responsibility_id",
    "allocation_phase",
    "test_designer_activation",
    "hard_edge_kinds",
    "semantic_grouping",
    "structural_mandates",
    "semantic_delta",
];
const DELTA_FIELDS: &[&str] = &[
    "id",
    "summary",
    "implementation_action",
    "design_refs",
    "obligation",
];
const OBLIGATION_FIELDS: &[&str] = &[
    "id",
    "claim",
    "verification_owner_kind",
    "verification_owner",
    "primary_verification_ref",
    "contract_ref",
    "changed_mechanism_ref",
    "observable_assertion",
    "decidable_oracle",
    "removal_witness",
    "supporting_evidence",
];
const SUPPORTING_FIELDS: &[&str] = &["property", "role", "owner_kind", "reference"];
const VALID_ACTIONS: &[&str] = &["reuse", "extend", "replace", "introduce"];

#[derive(Debug)]
struct ContractError(String);

impl fmt::Display for ContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

#[derive(Debug)]
enum ContractValue {
    Table(BTreeMap<String, ContractValue>),
    Array(Vec<ContractValue>),
    String(String),
    Integer(i64),
    Float(f64),
    Boolean(bool),
    Other,
}

impl ContractValue {
    fn as_table(&self) -> Option<&BTreeMap<String, ContractValue>> {
        match self {
            Self::Table(table) => Some(table),
            _ => None,
        }
    }

    fn as_array(&self) -> Option<&[ContractValue]> {
        match self {
            Self::Array(values) => Some(values),
            _ => None,
        }
    }

    fn as_str(&self) -> Option<&str> {
        match self {
            Self::String(value) => Some(value),
            _ => None,
        }
    }

    fn is_truthy(&self) -> bool {
        match self {
            Self::Table(value) => !value.is_empty(),
            Self::Array(value) => !value.is_empty(),
            Self::String(value) => !value.is_empty(),
            Self::Integer(value) => *value != 0,
            Self::Float(value) => *value != 0.0,
            Self::Boolean(value) => *value,
            Self::Other => true,
        }
    }

    fn is_empty_string(&self) -> bool {
        matches!(self, Self::String(value) if value.is_empty())
    }
}

#[derive(Debug, PartialEq, Eq)]
struct Args {
    paths: Vec<PathBuf>,
    root: PathBuf,
    templates: Vec<PathBuf>,
    instances: Vec<PathBuf>,
    artifact_root: Option<PathBuf>,
    format: OutputFormat,
}

#[derive(Debug, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

enum ParseResult {
    Help,
    Args(Args),
}

#[derive(Clone, Copy)]
struct ReferenceContext<'a> {
    root: &'a Path,
    instance_path: &'a Path,
    artifact_root: Option<&'a Path>,
}

#[derive(Serialize)]
struct ValidationResult {
    path: String,
    template: bool,
    identity: Vec<String>,
}

#[derive(Serialize)]
struct ValidationReport {
    status: &'static str,
    results: Vec<ValidationResult>,
    errors: Vec<String>,
}

pub fn run(args: &[String]) -> i32 {
    let parsed = match parse_args(args) {
        Ok(ParseResult::Help) => {
            println!("{USAGE}\n\nValidate semantic responsibility contract schema, identity, and references.");
            return 0;
        }
        Ok(ParseResult::Args(args)) => args,
        Err(message) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon {SELECTOR}: error: {message}");
            return 2;
        }
    };

    let root = match resolve_non_strict(&parsed.root) {
        Ok(root) => root,
        Err(error) => return path_resolution_failure(&parsed.root, &error),
    };
    let mut templates = parsed.templates;
    let mut instances = parsed.instances;
    for path in parsed.paths {
        if path.file_name().and_then(|name| name.to_str())
            == Path::new(TEMPLATE_PATH)
                .file_name()
                .and_then(|name| name.to_str())
        {
            templates.push(path);
        } else {
            instances.push(path);
        }
    }
    if templates.is_empty() {
        templates.push(root.join(TEMPLATE_PATH));
    }

    let documents: Vec<(PathBuf, bool)> = templates
        .into_iter()
        .map(|path| (path, true))
        .chain(instances.into_iter().map(|path| (path, false)))
        .collect();
    if documents.is_empty() {
        eprintln!("SEMANTIC_RESPONSIBILITY_CONTRACT=fail");
        eprintln!("no contract documents supplied");
        return 2;
    }

    let artifact_root = match parsed
        .artifact_root
        .as_deref()
        .map(resolve_non_strict)
        .transpose()
    {
        Ok(root) => root,
        Err(error) => {
            let path = parsed.artifact_root.as_deref().expect("failed root exists");
            return path_resolution_failure(path, &error);
        }
    };
    let mut results = Vec::new();
    let mut failures = Vec::new();
    for (raw_path, is_template) in documents {
        let selected_path = if raw_path.is_absolute() {
            raw_path
        } else {
            env::current_dir().unwrap_or_default().join(raw_path)
        };
        let path = match resolve_non_strict(&selected_path) {
            Ok(path) => path,
            Err(error) => {
                failures.push(format!(
                    "{}:path_resolution_failed:{error}",
                    selected_path.display()
                ));
                continue;
            }
        };
        let context = ReferenceContext {
            root: &root,
            instance_path: &path,
            artifact_root: artifact_root.as_deref(),
        };
        match validate_document(&path, context, is_template) {
            Ok(identity) => results.push(ValidationResult {
                path: path.to_string_lossy().into_owned(),
                template: is_template,
                identity,
            }),
            Err(error) => failures.push(error.to_string()),
        }
    }

    let report = ValidationReport {
        status: if failures.is_empty() { "pass" } else { "fail" },
        results,
        errors: failures,
    };
    match parsed.format {
        OutputFormat::Json => print_json(&report),
        OutputFormat::Text => print_text(&report),
    }
    if report.errors.is_empty() {
        0
    } else {
        1
    }
}

fn parse_args(args: &[String]) -> Result<ParseResult, String> {
    let mut paths = Vec::new();
    let mut root = PathBuf::from(".");
    let mut templates = Vec::new();
    let mut instances = Vec::new();
    let mut artifact_root = None;
    let mut format = OutputFormat::Text;
    let mut options = true;
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if options && argument == "--" {
            options = false;
            index += 1;
            continue;
        }
        if options && matches!(argument.as_str(), "-h" | "--help") {
            return Ok(ParseResult::Help);
        }

        let (option, inline_value) = if options {
            option_and_value(argument)
        } else {
            (None, None)
        };
        if let Some(option) = option {
            let value = if let Some(value) = inline_value {
                value.to_owned()
            } else {
                index += 1;
                let Some(value) = args.get(index) else {
                    return Err(format!("argument {option}: expected one argument"));
                };
                if starts_option(value) {
                    return Err(format!("argument {option}: expected one argument"));
                }
                value.clone()
            };
            match option {
                "--root" => root = PathBuf::from(value),
                "--template" => templates.push(PathBuf::from(value)),
                "--instance" => instances.push(PathBuf::from(value)),
                "--artifact-root" => artifact_root = Some(PathBuf::from(value)),
                "--format" => {
                    format = match value.as_str() {
                        "text" => OutputFormat::Text,
                        "json" => OutputFormat::Json,
                        _ => {
                            return Err(format!(
                                "argument --format: invalid choice: '{value}' (choose from 'text', 'json')"
                            ));
                        }
                    };
                }
                _ => unreachable!("option parser only returns known options"),
            }
        } else if options && starts_option(argument) {
            return Err(format!("unrecognized arguments: {argument}"));
        } else {
            paths.push(PathBuf::from(argument));
        }
        index += 1;
    }
    Ok(ParseResult::Args(Args {
        paths,
        root,
        templates,
        instances,
        artifact_root,
        format,
    }))
}

fn option_and_value(argument: &str) -> (Option<&'static str>, Option<&str>) {
    const OPTIONS: &[&str] = &[
        "--root",
        "--template",
        "--instance",
        "--artifact-root",
        "--format",
    ];
    let (name, value) = argument
        .split_once('=')
        .map_or((argument, None), |(name, value)| (name, Some(value)));
    let mut matches = OPTIONS.iter().filter(|option| option.starts_with(name));
    let first = matches.next().copied();
    let second = matches.next();
    match (first, second) {
        (Some(option), None) => (Some(option), value),
        _ => (None, None),
    }
}

fn starts_option(value: &str) -> bool {
    value.starts_with('-') && value != "-" && !negative_number(value)
}

fn negative_number(value: &str) -> bool {
    let digits = value.strip_prefix('-').unwrap_or_default();
    !digits.is_empty()
        && digits
            .chars()
            .all(|character| character.is_ascii_digit() || character == '.')
        && digits.chars().any(|character| character.is_ascii_digit())
}

fn print_json(report: &ValidationReport) {
    println!(
        "{}",
        serde_json::to_string_pretty(report).expect("semantic contract report serializes to JSON")
    );
}

fn print_text(report: &ValidationReport) {
    for result in &report.results {
        println!("SEMANTIC_RESPONSIBILITY_CONTRACT_FILE={}", result.path);
    }
    if report.errors.is_empty() {
        println!("SEMANTIC_RESPONSIBILITY_CONTRACT=pass");
    } else {
        eprintln!("SEMANTIC_RESPONSIBILITY_CONTRACT=fail");
        for error in &report.errors {
            eprintln!("SEMANTIC_RESPONSIBILITY_CONTRACT_ERROR={error}");
        }
    }
}

fn path_resolution_failure(path: &Path, error: &str) -> i32 {
    eprintln!("SEMANTIC_RESPONSIBILITY_CONTRACT=fail");
    eprintln!(
        "SEMANTIC_RESPONSIBILITY_CONTRACT_ERROR={}:path_resolution_failed:{error}",
        path.display()
    );
    1
}

fn parse_document(path: &Path) -> Result<ContractValue, ContractError> {
    let text = fs::read_to_string(path)
        .map_err(|error| ContractError(format!("{}:toml_invalid:{error}", path.display())))?;
    let document = text
        .parse::<DocumentMut>()
        .map_err(|error| ContractError(format!("{}:toml_invalid:{error}", path.display())))?;
    Ok(contract_table(document.as_table()))
}

fn contract_table(table: &dyn TableLike) -> ContractValue {
    ContractValue::Table(
        table
            .iter()
            .map(|(name, item)| (name.to_owned(), contract_item(item)))
            .collect(),
    )
}

fn contract_item(item: &Item) -> ContractValue {
    if let Some(tables) = item.as_array_of_tables() {
        return ContractValue::Array(
            tables
                .iter()
                .map(|table| contract_table(table as &dyn TableLike))
                .collect(),
        );
    }
    if let Some(table) = item.as_table_like() {
        return contract_table(table);
    }
    if let Some(array) = item.as_array() {
        return ContractValue::Array(array.iter().map(contract_toml_value).collect());
    }
    if let Some(value) = item.as_value() {
        return contract_toml_value(value);
    }
    ContractValue::Other
}

fn contract_toml_value(value: &TomlEditValue) -> ContractValue {
    if let Some(table) = value.as_inline_table() {
        return contract_table(table as &dyn TableLike);
    }
    if let Some(array) = value.as_array() {
        return ContractValue::Array(array.iter().map(contract_toml_value).collect());
    }
    if let Some(value) = value.as_str() {
        return ContractValue::String(value.to_owned());
    }
    if let Some(value) = value.as_integer() {
        return ContractValue::Integer(value);
    }
    if let Some(value) = value.as_float() {
        return ContractValue::Float(value);
    }
    if let Some(value) = value.as_bool() {
        return ContractValue::Boolean(value);
    }
    ContractValue::Other
}

fn validate_document(
    path: &Path,
    context: ReferenceContext<'_>,
    template: bool,
) -> Result<Vec<String>, ContractError> {
    let data = parse_document(path)?;
    let Some(data) = data.as_table() else {
        return Err(ContractError(format!(
            "{}:root_must_be_table",
            path.display()
        )));
    };
    check_unknown(data, ROOT_FIELDS, "root")?;
    if string(data.get("schema")) != Some(SCHEMA) {
        return Err(ContractError("root.schema:invalid".to_owned()));
    }
    let expected_kind = if template { "template" } else { "task" };
    if string(data.get("instance_kind")) != Some(expected_kind) {
        return Err(ContractError(format!(
            "root.instance_kind:expected_{expected_kind}"
        )));
    }
    let policy_ref = data.get("policy_ref");
    if template {
        if string(policy_ref) != Some(POLICY_PATH) {
            return Err(ContractError(
                "root.policy_ref:invalid_template_policy".to_owned(),
            ));
        }
    } else {
        let policy_ref = check_reference(policy_ref, "root.policy_ref", true, context)?;
        if !policy_ref
            .split('#')
            .next()
            .unwrap_or_default()
            .ends_with(POLICY_PATH)
        {
            return Err(ContractError(
                "root.policy_ref:not_semantic_responsibility_policy".to_owned(),
            ));
        }
    }

    if string(data.get("allocation_phase")) != Some("pre_implementation") {
        return Err(ContractError("root.allocation_phase:invalid".to_owned()));
    }
    if string(data.get("test_designer_activation"))
        != Some("post_implementation_unresolved_test_owned_runtime_risk")
    {
        return Err(ContractError(
            "root.test_designer_activation:invalid".to_owned(),
        ));
    }

    let edges = require_list(data.get("hard_edge_kinds"), "root.hard_edge_kinds")?;
    if edges.len() != HARD_EDGES.len()
        || edges
            .iter()
            .zip(HARD_EDGES)
            .any(|(actual, expected)| actual.as_str() != Some(expected))
    {
        return Err(ContractError("root.hard_edge_kinds:invalid".to_owned()));
    }
    let mandates = require_list(data.get("structural_mandates"), "root.structural_mandates")?;
    if !mandates.is_empty() {
        return Err(ContractError(
            "root.structural_mandates:must_be_empty".to_owned(),
        ));
    }

    if template {
        for name in [
            "active_design_packet_ref",
            "run_id",
            "task_id",
            "responsibility_id",
            "semantic_grouping",
        ] {
            if !data.get(name).is_some_and(ContractValue::is_empty_string) {
                return Err(ContractError(format!("root.{name}:template_must_be_empty")));
            }
        }
    } else {
        for name in [
            "run_id",
            "task_id",
            "responsibility_id",
            "semantic_grouping",
        ] {
            require_text(data.get(name), &format!("root.{name}"), false)?;
        }
        check_reference(
            data.get("active_design_packet_ref"),
            "root.active_design_packet_ref",
            true,
            context,
        )?;
    }

    let deltas = require_list(data.get("semantic_delta"), "root.semantic_delta")?;
    if template && deltas.len() != 1 {
        return Err(ContractError(
            "root.semantic_delta:template_shape_requires_placeholder".to_owned(),
        ));
    }
    if !template && deltas.is_empty() {
        return Err(ContractError("root.semantic_delta:empty".to_owned()));
    }
    let mut delta_ids = BTreeSet::new();
    for (index, delta) in deltas.iter().enumerate() {
        let field = format!("root.semantic_delta[{index}]");
        if let Some(identifier) = check_delta(delta, &field, context, template)? {
            if !delta_ids.insert(identifier) {
                return Err(ContractError(format!("{field}.id:duplicate")));
            }
        }
    }
    Ok(vec![
        format!("schema={SCHEMA}"),
        format!("instance_kind={expected_kind}"),
        format!("path={}", path.display()),
    ])
}

fn check_delta(
    raw: &ContractValue,
    field: &str,
    context: ReferenceContext<'_>,
    template: bool,
) -> Result<Option<String>, ContractError> {
    let Some(table) = raw.as_table() else {
        return Err(ContractError(format!("{field}:required_table")));
    };
    check_unknown(table, DELTA_FIELDS, field)?;
    if template {
        for name in ["id", "summary", "implementation_action"] {
            if !empty_or_missing(table.get(name)) {
                return Err(ContractError(format!(
                    "{field}.{name}:template_must_be_empty"
                )));
            }
        }
        if !matches!(table.get("design_refs"), Some(ContractValue::Array(values)) if values.is_empty())
        {
            return Err(ContractError(format!(
                "{field}.design_refs:template_must_be_empty"
            )));
        }
        let obligations = require_list(table.get("obligation"), &format!("{field}.obligation"))?;
        if obligations.len() != 1 {
            return Err(ContractError(format!(
                "{field}.obligation:template_shape_requires_placeholder"
            )));
        }
        check_obligation(
            &obligations[0],
            &format!("{field}.obligation[0]"),
            context,
            true,
        )?;
        return Ok(None);
    }

    let identifier = check_identifier(table.get("id"), &format!("{field}.id"), false)?;
    require_text(table.get("summary"), &format!("{field}.summary"), false)?;
    let action = require_text(
        table.get("implementation_action"),
        &format!("{field}.implementation_action"),
        false,
    )?;
    if !VALID_ACTIONS.contains(&action) {
        return Err(ContractError(format!(
            "{field}.implementation_action:unknown_action"
        )));
    }
    let refs = require_list(table.get("design_refs"), &format!("{field}.design_refs"))?;
    if refs.is_empty() {
        return Err(ContractError(format!("{field}.design_refs:empty")));
    }
    for (index, reference) in refs.iter().enumerate() {
        check_reference(
            Some(reference),
            &format!("{field}.design_refs[{index}]"),
            true,
            context,
        )?;
    }
    let obligations = require_list(table.get("obligation"), &format!("{field}.obligation"))?;
    if obligations.is_empty() {
        return Err(ContractError(format!("{field}.obligation:empty")));
    }
    let mut obligation_ids = BTreeSet::new();
    for (index, obligation) in obligations.iter().enumerate() {
        let obligation_field = format!("{field}.obligation[{index}]");
        let obligation_id = check_obligation(obligation, &obligation_field, context, false)?
            .expect("populated obligations have an identifier");
        if !obligation_ids.insert(obligation_id) {
            return Err(ContractError(format!("{obligation_field}.id:duplicate")));
        }
    }
    Ok(Some(identifier.to_owned()))
}

fn check_obligation(
    raw: &ContractValue,
    field: &str,
    context: ReferenceContext<'_>,
    template: bool,
) -> Result<Option<String>, ContractError> {
    let Some(table) = raw.as_table() else {
        return Err(ContractError(format!("{field}:required_table")));
    };
    check_unknown(table, OBLIGATION_FIELDS, field)?;
    if template && !table.get("id").is_some_and(ContractValue::is_truthy) {
        for name in OBLIGATION_FIELDS {
            if *name == "supporting_evidence" {
                if !matches!(table.get(*name), Some(ContractValue::Array(values)) if values.is_empty())
                {
                    return Err(ContractError(format!(
                        "{field}.{name}:template_must_be_empty"
                    )));
                }
            } else if !empty_or_missing(table.get(*name)) {
                return Err(ContractError(format!(
                    "{field}.{name}:template_must_be_empty"
                )));
            }
        }
        return Ok(None);
    }

    let identifier = check_identifier(table.get("id"), &format!("{field}.id"), false)?;
    let claim = require_text(table.get("claim"), &format!("{field}.claim"), false)?;
    let owner_kind = require_text(
        table.get("verification_owner_kind"),
        &format!("{field}.verification_owner_kind"),
        false,
    )?;
    if !OWNER_KINDS.contains(&owner_kind) {
        return Err(ContractError(format!(
            "{field}.verification_owner_kind:unknown_owner_kind"
        )));
    }
    let owner = require_text(
        table.get("verification_owner"),
        &format!("{field}.verification_owner"),
        false,
    )?;
    check_reference(
        table.get("primary_verification_ref"),
        &format!("{field}.primary_verification_ref"),
        true,
        context,
    )?;
    for name in ["contract_ref", "changed_mechanism_ref", "removal_witness"] {
        check_reference(
            table.get(name),
            &format!("{field}.{name}"),
            owner_kind == "existing_test",
            context,
        )?;
    }
    for name in ["observable_assertion", "decidable_oracle"] {
        require_text(
            table.get(name),
            &format!("{field}.{name}"),
            owner_kind != "existing_test",
        )?;
    }
    if owner_kind == "existing_test" {
        for name in [
            "contract_ref",
            "changed_mechanism_ref",
            "removal_witness",
            "observable_assertion",
            "decidable_oracle",
        ] {
            require_text(table.get(name), &format!("{field}.{name}"), false)?;
        }
    }
    check_supporting_evidence(
        table.get("supporting_evidence"),
        &format!("{field}.supporting_evidence"),
        context,
        claim,
        owner,
    )?;
    Ok(Some(identifier.to_owned()))
}

fn check_supporting_evidence(
    value: Option<&ContractValue>,
    field: &str,
    context: ReferenceContext<'_>,
    primary_property: &str,
    primary_role: &str,
) -> Result<(), ContractError> {
    let entries = require_list(value, field)?;
    let mut seen = BTreeSet::new();
    for (index, raw) in entries.iter().enumerate() {
        let entry_field = format!("{field}[{index}]");
        let Some(table) = raw.as_table() else {
            return Err(ContractError(format!("{entry_field}:required_table")));
        };
        check_unknown(table, SUPPORTING_FIELDS, &entry_field)?;
        let property = require_text(
            table.get("property"),
            &format!("{entry_field}.property"),
            false,
        )?;
        let role = require_text(table.get("role"), &format!("{entry_field}.role"), false)?;
        let owner_kind = require_text(
            table.get("owner_kind"),
            &format!("{entry_field}.owner_kind"),
            false,
        )?;
        if !OWNER_KINDS.contains(&owner_kind) {
            return Err(ContractError(format!(
                "{entry_field}.owner_kind:unknown_owner_kind"
            )));
        }
        if property == primary_property && role == primary_role {
            return Err(ContractError(format!(
                "{entry_field}:duplicates_primary_property_role"
            )));
        }
        if !seen.insert((property.to_owned(), role.to_owned())) {
            return Err(ContractError(format!(
                "{entry_field}:duplicate_property_role"
            )));
        }
        check_reference(
            table.get("reference"),
            &format!("{entry_field}.reference"),
            true,
            context,
        )?;
    }
    Ok(())
}

fn check_reference<'a>(
    value: Option<&'a ContractValue>,
    field: &str,
    required: bool,
    context: ReferenceContext<'_>,
) -> Result<&'a str, ContractError> {
    let text = require_text(value, field, !required)?;
    if text.is_empty() {
        return Ok(text);
    }
    let Some((prefix, target)) = text.split_once(':') else {
        return Err(ContractError(format!("{field}:invalid_reference")));
    };
    let Some((target_path, anchor)) = target.split_once('#') else {
        if !matches!(prefix, "repo" | "artifact")
            || target.is_empty()
            || target.chars().any(char::is_whitespace)
        {
            return Err(ContractError(format!("{field}:invalid_reference")));
        }
        return check_reference_path(text, field, prefix, target, context);
    };
    if !matches!(prefix, "repo" | "artifact")
        || target_path.is_empty()
        || target_path.chars().any(char::is_whitespace)
        || anchor.is_empty()
        || anchor.chars().any(char::is_whitespace)
    {
        return Err(ContractError(format!("{field}:invalid_reference")));
    }
    check_reference_path(text, field, prefix, target_path, context)
}

fn check_reference_path<'a>(
    text: &'a str,
    field: &str,
    prefix: &str,
    target_path: &str,
    context: ReferenceContext<'_>,
) -> Result<&'a str, ContractError> {
    let relative = Path::new(target_path);
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| matches!(component, Component::ParentDir))
        || target_path.is_empty()
    {
        return Err(ContractError(format!("{field}:unsafe_reference")));
    }
    let base = if prefix == "repo" {
        context.root
    } else {
        context.artifact_root.unwrap_or_else(|| {
            context
                .instance_path
                .parent()
                .unwrap_or_else(|| Path::new("."))
        })
    };
    let unresolved = base.join(relative);
    if is_symlink(&unresolved) {
        return Err(ContractError(format!("{field}:symlink_reference")));
    }
    let candidate = resolve_non_strict(&unresolved)
        .map_err(|error| ContractError(format!("{field}:reference_resolution_failed:{error}")))?;
    let resolved_base = resolve_non_strict(base)
        .map_err(|error| ContractError(format!("{field}:reference_resolution_failed:{error}")))?;
    if !candidate.starts_with(&resolved_base) {
        return Err(ContractError(format!("{field}:outside_reference_root")));
    }
    if !candidate.is_file() || is_symlink(&candidate) {
        return Err(ContractError(format!(
            "{field}:missing_reference:{target_path}"
        )));
    }
    Ok(text)
}

fn is_symlink(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok_and(|metadata| metadata.file_type().is_symlink())
}

fn require_text<'a>(
    value: Option<&'a ContractValue>,
    field: &str,
    empty: bool,
) -> Result<&'a str, ContractError> {
    let Some(value) = value.and_then(ContractValue::as_str) else {
        return Err(ContractError(format!("{field}:required_text")));
    };
    if !empty && value.trim().is_empty() {
        return Err(ContractError(format!("{field}:required_text")));
    }
    Ok(value)
}

fn require_list<'a>(
    value: Option<&'a ContractValue>,
    field: &str,
) -> Result<&'a [ContractValue], ContractError> {
    value
        .and_then(ContractValue::as_array)
        .ok_or_else(|| ContractError(format!("{field}:required_list")))
}

fn check_unknown(
    mapping: &BTreeMap<String, ContractValue>,
    allowed: &[&str],
    field: &str,
) -> Result<(), ContractError> {
    let unknown: Vec<_> = mapping
        .keys()
        .filter(|key| !allowed.contains(&key.as_str()))
        .cloned()
        .collect();
    if unknown.is_empty() {
        return Ok(());
    }
    Err(ContractError(format!(
        "{field}:unknown_fields:{}",
        unknown.join(",")
    )))
}

fn check_identifier<'a>(
    value: Option<&'a ContractValue>,
    field: &str,
    empty: bool,
) -> Result<&'a str, ContractError> {
    let text = require_text(value, field, empty)?;
    if !text.is_empty() && !valid_identifier(text) {
        return Err(ContractError(format!("{field}:invalid_identifier")));
    }
    Ok(text)
}

fn valid_identifier(text: &str) -> bool {
    let mut characters = text.bytes();
    characters
        .next()
        .is_some_and(|character| character.is_ascii_alphanumeric())
        && characters
            .all(|character| character.is_ascii_alphanumeric() || matches!(character, b'_' | b'-'))
}

fn string(value: Option<&ContractValue>) -> Option<&str> {
    value.and_then(ContractValue::as_str)
}

fn empty_or_missing(value: Option<&ContractValue>) -> bool {
    value.is_none_or(ContractValue::is_empty_string)
}

#[derive(Clone)]
enum ResolutionComponent {
    RootDir(OsString),
    CurDir,
    ParentDir,
    Normal(OsString),
    #[cfg(windows)]
    Prefix(OsString),
}

struct ResolutionFrame {
    components: Vec<ResolutionComponent>,
    next: usize,
    resolving_symlink: Option<PathBuf>,
}

impl ResolutionFrame {
    fn new(path: &Path, resolving_symlink: Option<PathBuf>) -> Self {
        let components = path
            .components()
            .map(|component| match component {
                root @ Component::RootDir => {
                    ResolutionComponent::RootDir(root.as_os_str().to_os_string())
                }
                Component::CurDir => ResolutionComponent::CurDir,
                Component::ParentDir => ResolutionComponent::ParentDir,
                Component::Normal(name) => ResolutionComponent::Normal(name.to_os_string()),
                #[cfg(windows)]
                Component::Prefix(prefix) => {
                    ResolutionComponent::Prefix(prefix.as_os_str().to_os_string())
                }
            })
            .collect();
        Self {
            components,
            next: 0,
            resolving_symlink,
        }
    }
}

fn resolve_non_strict(path: &Path) -> Result<PathBuf, String> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .map_err(|error| format!("current directory: {error}"))?
            .join(path)
    };
    let mut resolved = PathBuf::new();
    let mut frames = vec![ResolutionFrame::new(&absolute, None)];
    let mut active_symlinks = HashSet::new();

    while !frames.is_empty() {
        let frame_finished = frames
            .last()
            .is_some_and(|frame| frame.next == frame.components.len());
        if frame_finished {
            let frame = frames.pop().expect("finished frame exists");
            if let Some(symlink) = frame.resolving_symlink {
                active_symlinks.remove(&symlink);
            }
            continue;
        }
        let component = {
            let frame = frames.last_mut().expect("active frame exists");
            let component = frame.components[frame.next].clone();
            frame.next += 1;
            component
        };
        match component {
            ResolutionComponent::RootDir(root) => resolved.push(root),
            ResolutionComponent::CurDir => {}
            ResolutionComponent::ParentDir => {
                if !resolved.pop() && !resolved.has_root() {
                    resolved.push("..");
                }
            }
            ResolutionComponent::Normal(name) => {
                let candidate = resolved.join(&name);
                match fs::symlink_metadata(&candidate) {
                    Ok(metadata) if metadata.file_type().is_symlink() => {
                        if !active_symlinks.insert(candidate.clone()) {
                            return Err(format!("symbolic link loop at {}", candidate.display()));
                        }
                        let target = fs::read_link(&candidate).map_err(|error| {
                            format!("read symbolic link {}: {error}", candidate.display())
                        })?;
                        let target = if target.is_absolute() {
                            target
                        } else {
                            resolved.join(target)
                        };
                        frames.push(ResolutionFrame::new(&target, Some(candidate)));
                    }
                    Ok(_) => {
                        resolved = fs::canonicalize(&candidate).map_err(|error| {
                            format!("canonicalize {}: {error}", candidate.display())
                        })?;
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                        resolved.push(name);
                    }
                    Err(error) => {
                        return Err(format!("inspect {}: {error}", candidate.display()));
                    }
                }
            }
            #[cfg(windows)]
            ResolutionComponent::Prefix(prefix) => resolved.push(prefix),
        }
    }
    Ok(resolved)
}
