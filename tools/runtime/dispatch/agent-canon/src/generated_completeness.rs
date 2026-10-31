// @dependency-start
// contract implementation
// responsibility Owns pure G2 generated-completeness receipts and their parent-bound runtime CLI.
// upstream implementation authority/mod.rs owns control-parent attestation
// upstream implementation artifacts/artifact_identity.rs owns canonical JSON bytes
// upstream implementation git_dependency_diff_summary.rs owns selected-root Git readback
// upstream implementation python_text.rs owns Python-compatible output trimming
// upstream implementation runtime_boundary.rs owns confined atomic writes and no-follow replay reads
// upstream implementation update_lifecycle_contract.rs owns G1/G2 validation, receipt mechanics, and immutable replay
// downstream implementation main.rs routes the materialize-agent-canon-pr-g2 command
// downstream implementation ../../../../validation/ci/checks/check_agent_canon_pr.sh invokes G2 after ordered checks
// downstream test ../tests/generated_completeness_native.rs freezes G2 bytes, errors, authority, and persistence
// downstream test ../../../../../tests/agent_tools/test_github_publish.py consumes frozen G1/G2 publication contexts
// downstream test ../../../../../tests/agent_tools/test_bootstrap_and_close.py consumes frozen G1/G2 closeout context
// @dependency-end

use crate::artifacts::artifact_identity::canonical_json_bytes;
use crate::authority::{AttestationRequest, NonEmptyTrimmedString, Nonce128, ParentRootAttestor};
use crate::git_dependency_diff_summary::git_stdout;
use crate::python_text::python_strip;
use crate::runtime_boundary::RuntimeArtifactBoundary;
use crate::update_lifecycle_contract::{
    materialize_gate_verdict, validate_gate_chain, validate_gate_verdict,
    validate_immutable_replay, GateVerdictInput, LifecycleContractError,
};
use serde_json::{json, Value as JsonValue};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};

pub const SELECTOR: &str = "materialize-agent-canon-pr-g2";
pub const GENERATED_COMPLETENESS_CHECK_IDS: [&str; 4] = [
    "standalone_static_gate_ci",
    "documentation_checks",
    "repository_quick_ci",
    "generated_artifact_guard",
];

// This existing .py#symbol string is hashed into G2 identity and remains the schema owner.
const G2_LOGICAL_OWNER_PATH: &str =
    "tools/validation/ci/checks/check_agent_canon_pr.py#materialize_generated_completeness_receipt";

fn generated_completeness_error(code: &str) -> LifecycleContractError {
    LifecycleContractError {
        code: code.to_string(),
        detail: String::new(),
    }
}

pub fn materialize_generated_completeness_receipt(
    g1_gate: &JsonValue,
    candidate_sha: &str,
    tree_sha: &str,
    check_results: &[JsonValue],
    source_root: &str,
) -> Result<JsonValue, LifecycleContractError> {
    let g1 = validate_gate_chain(std::slice::from_ref(g1_gate), Some(&["G1"]), true)?
        .into_iter()
        .next()
        .expect("the validated G1 gate is present");
    let binding = g1
        .get("binding")
        .and_then(JsonValue::as_object)
        .expect("validated G1 gate has an object binding");
    if binding.get("candidate_sha").and_then(JsonValue::as_str) != Some(candidate_sha)
        || binding.get("tree_sha").and_then(JsonValue::as_str) != Some(tree_sha)
    {
        return Err(generated_completeness_error(
            "generated_completeness:candidate_identity_mismatch",
        ));
    }

    let mut normalized = Vec::with_capacity(check_results.len());
    for result in check_results {
        let Some(fields) = result.as_object() else {
            return Err(generated_completeness_error(
                "generated_completeness:check_result_fields_invalid",
            ));
        };
        if fields.len() != 2 || !fields.contains_key("check_id") || !fields.contains_key("status") {
            return Err(generated_completeness_error(
                "generated_completeness:check_result_fields_invalid",
            ));
        }
        let (Some(check_id), Some(status)) = (
            fields.get("check_id").and_then(JsonValue::as_str),
            fields.get("status").and_then(JsonValue::as_str),
        ) else {
            return Err(generated_completeness_error(
                "generated_completeness:check_result_invalid",
            ));
        };
        normalized.push(json!({"check_id": check_id, "status": status}));
    }
    let check_order_matches = normalized
        .iter()
        .map(|result| {
            result["check_id"]
                .as_str()
                .expect("normalized check ID is a string")
        })
        .eq(GENERATED_COMPLETENESS_CHECK_IDS.iter().copied());
    if !check_order_matches {
        return Err(generated_completeness_error(
            "generated_completeness:check_order_invalid",
        ));
    }
    if normalized
        .iter()
        .any(|result| result["status"].as_str() != Some("pass"))
    {
        return Err(generated_completeness_error(
            "generated_completeness:check_not_passed",
        ));
    }

    let output = json!({
        "candidate_sha": candidate_sha,
        "tree_sha": tree_sha,
        "check_results": normalized,
    });
    let digest = Sha256::digest(canonical_json_bytes(&output)?)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let owner = format!(
        "{}/{}",
        source_root.trim_end_matches('/'),
        G2_LOGICAL_OWNER_PATH
    );
    let g1_binding = g1
        .get("binding")
        .cloned()
        .expect("validated G1 gate has a binding");
    let predecessor = g1_binding
        .get("evidence_ref")
        .and_then(JsonValue::as_str)
        .expect("validated G1 binding has an evidence reference")
        .to_string();
    materialize_gate_verdict(&GateVerdictInput {
        binding: g1_binding,
        gate_id: "G2".to_string(),
        ordered_input_evidence_refs: vec![predecessor],
        invariant: "generated_completeness".to_string(),
        output_digest: format!("sha256:{digest}"),
        owner,
        verdict: "pass".to_string(),
        retry_reason: None,
        next_checkpoint: None,
    })
}

const USAGE: &str = "usage: agent-canon materialize-agent-canon-pr-g2 --g1-bundle G1_BUNDLE --source-root SOURCE_ROOT --control-parent-root CONTROL_PARENT_ROOT --runtime-root RUNTIME_ROOT [--output OUTPUT]";
const HELP: &str = "Materialize the G2 receipt after the ordered AgentCanon PR checks pass.";
const LONG_OPTIONS: &[&str] = &[
    "--g1-bundle",
    "--output",
    "--source-root",
    "--control-parent-root",
    "--runtime-root",
    "--help",
];

#[derive(Default)]
struct CliOptions {
    g1_bundle: Option<PathBuf>,
    output: Option<PathBuf>,
    source_root: Option<PathBuf>,
    control_parent_root: Option<PathBuf>,
    runtime_root: Option<PathBuf>,
}

struct CliError {
    exit_code: i32,
    message: String,
    show_usage: bool,
}

impl CliError {
    fn usage(message: impl Into<String>) -> Self {
        Self {
            exit_code: 2,
            message: message.into(),
            show_usage: true,
        }
    }

    fn failure(message: impl Into<String>) -> Self {
        Self {
            exit_code: 1,
            message: message.into(),
            show_usage: false,
        }
    }
}

fn matching_long_option(option: &str) -> Option<&'static str> {
    if option.len() <= 2 {
        return None;
    }
    let mut matches = LONG_OPTIONS
        .iter()
        .copied()
        .filter(|candidate| candidate.starts_with(option));
    let matched = matches.next()?;
    matches.next().is_none().then_some(matched)
}

fn option_value(
    args: &[String],
    index: usize,
    option: &str,
    inline_value: Option<&str>,
) -> Result<(String, usize), String> {
    if let Some(value) = inline_value {
        return Ok((value.to_string(), 1));
    }
    let Some(value) = args.get(index + 1) else {
        return Err(format!("argument {option}: expected one argument"));
    };
    if value.starts_with('-') && value != "-" {
        return Err(format!("argument {option}: expected one argument"));
    }
    Ok((value.clone(), 2))
}

fn parse_cli(args: &[String]) -> Result<Option<CliOptions>, String> {
    let mut options = CliOptions::default();
    let mut index = 0;
    while index < args.len() {
        let argument = args[index].as_str();
        if argument == "-h" {
            return Ok(None);
        }
        let (option, inline_value) = argument
            .split_once('=')
            .map_or((argument, None), |(option, value)| (option, Some(value)));
        let Some(canonical) = matching_long_option(option) else {
            return Err(format!("unrecognized arguments: {argument}"));
        };
        if canonical == "--help" {
            return if inline_value.is_none() {
                Ok(None)
            } else {
                Err("argument --help: ignored explicit argument".to_string())
            };
        }
        let (value, consumed) = option_value(args, index, canonical, inline_value)?;
        let path = PathBuf::from(if value.is_empty() {
            "."
        } else {
            value.as_str()
        });
        match canonical {
            "--g1-bundle" => options.g1_bundle = Some(path),
            "--output" => options.output = Some(path),
            "--source-root" => options.source_root = Some(path),
            "--control-parent-root" => options.control_parent_root = Some(path),
            "--runtime-root" => options.runtime_root = Some(path),
            _ => unreachable!("only registered options are returned"),
        }
        index += consumed;
    }
    let missing = [
        ("--g1-bundle", options.g1_bundle.is_none()),
        ("--source-root", options.source_root.is_none()),
        (
            "--control-parent-root",
            options.control_parent_root.is_none(),
        ),
        ("--runtime-root", options.runtime_root.is_none()),
    ]
    .into_iter()
    .filter_map(|(option, absent)| absent.then_some(option))
    .collect::<Vec<_>>();
    if !missing.is_empty() {
        return Err(format!(
            "the following arguments are required: {}",
            missing.join(", ")
        ));
    }
    Ok(Some(options))
}

fn runtime_output_path(
    runtime: &RuntimeArtifactBoundary,
    path: &Path,
) -> Result<PathBuf, CliError> {
    runtime.resolve(path).map_err(|error| {
        let message = if error.contains("path escapes runtime root") {
            "agent_canon_pr_gate:output must remain under runtime root".to_string()
        } else {
            error
        };
        CliError::failure(message)
    })
}

fn persist_g2_receipt(
    runtime: &RuntimeArtifactBoundary,
    output_path: &Path,
    display_path: &Path,
    receipt: &JsonValue,
) -> Result<JsonValue, CliError> {
    let target = runtime_output_path(runtime, output_path)?;
    if let Some(bytes) = runtime.read_bytes(&target).map_err(CliError::failure)? {
        let existing: JsonValue = serde_json::from_slice(&bytes)
            .map_err(|error| CliError::failure(format!("G2 replay JSON is invalid: {error}")))?;
        let existing = validate_gate_verdict(&existing)
            .map_err(|error| CliError::failure(error.to_string()))?;
        validate_immutable_replay(&existing, receipt, &display_path.display().to_string())
            .map_err(|error| CliError::failure(error.to_string()))?;
        return Ok(existing);
    }

    let mut bytes = serde_json::to_vec_pretty(receipt)
        .map_err(|error| CliError::failure(format!("G2 receipt serialization failed: {error}")))?;
    bytes.push(b'\n');
    runtime
        .atomic_write_bytes(&target, &bytes, 0o600)
        .map_err(CliError::failure)?;
    Ok(receipt.clone())
}

fn make_g2_receipt(
    g1_gate: &JsonValue,
    candidate_sha: &str,
    tree_sha: &str,
    source_root: &str,
) -> Result<JsonValue, CliError> {
    let check_results = GENERATED_COMPLETENESS_CHECK_IDS
        .iter()
        .map(|check_id| json!({"check_id": check_id, "status": "pass"}))
        .collect::<Vec<_>>();
    materialize_generated_completeness_receipt(
        g1_gate,
        candidate_sha,
        tree_sha,
        &check_results,
        source_root,
    )
    .map_err(|error| CliError::failure(error.to_string()))
}

fn execute(options: CliOptions) -> Result<(JsonValue, PathBuf), CliError> {
    let source_argument = options.source_root.expect("required source root parsed");
    let source_root = fs::canonicalize(&source_argument).map_err(|error| {
        CliError::usage(format!("source root is unavailable: {}", error.kind()))
    })?;
    let source_root_string = source_root
        .to_str()
        .ok_or_else(|| CliError::usage("source root is not valid Unicode"))?;
    let control_argument = options
        .control_parent_root
        .expect("required control root parsed");
    let control_root = fs::canonicalize(&control_argument).map_err(|error| {
        CliError::usage(format!(
            "control parent root is unavailable: {}",
            error.kind()
        ))
    })?;
    if control_root == source_root {
        return Err(CliError::usage(
            "control parent root must differ from source",
        ));
    }
    let purpose = NonEmptyTrimmedString::new("agent-canon-g2")
        .expect("G2 authority purpose is a fixed valid identifier");
    let nonce = Nonce128::generate()
        .map_err(|_| CliError::usage("external boundary rejected: AuthorityError"))?;
    let request = AttestationRequest {
        cwd: control_root.clone(),
        explicit_root: Some(control_root.clone()),
        source_root: Some(source_root.clone()),
        clone_root: None,
        topic_marker: None,
        gitmodules: None,
        owner_evidence: None,
        expected_remote: None,
        expected_module_digest: None,
        child_handoff_token: None,
        purpose,
        nonce,
    };
    ParentRootAttestor::new()
        .attest(&request)
        .map_err(|_| CliError::usage("external boundary rejected: AuthorityError"))?;

    let runtime_argument = options.runtime_root.expect("required runtime root parsed");
    let runtime = RuntimeArtifactBoundary::for_source(&source_root, Some(&runtime_argument), true)
        .map_err(|_| CliError::usage("external boundary rejected: RuntimeError"))?;

    let supplied_output = options.output;
    let preliminary_output = match supplied_output.as_ref() {
        Some(path) if path.is_absolute() => path.clone(),
        Some(path) => std::env::current_dir()
            .map_err(|error| CliError::failure(error.to_string()))?
            .join(path),
        None => runtime.root().join("tasks/g2.generated-completeness.json"),
    };
    runtime_output_path(&runtime, &preliminary_output)?;

    let g1_bundle_path = options.g1_bundle.expect("required G1 bundle parsed");
    let bundle_bytes = fs::read(&g1_bundle_path)
        .map_err(|error| CliError::failure(format!("unable to read G1 bundle: {error}")))?;
    let payload: JsonValue = serde_json::from_slice(&bundle_bytes)
        .map_err(|error| CliError::failure(format!("G1 bundle JSON is invalid: {error}")))?;
    let Some(gate_values) = payload.get("gate_verdicts").and_then(JsonValue::as_array) else {
        return Err(CliError::failure(
            "agent_canon_pr_gate_bundle:gate_verdicts_missing",
        ));
    };
    if gate_values.iter().any(|gate| !gate.is_object()) {
        return Err(CliError::failure(
            "agent_canon_pr_gate_bundle:gate_verdict_invalid",
        ));
    }
    let gates = validate_gate_chain(gate_values, Some(&["G1"]), true)
        .map_err(|error| CliError::failure(error.to_string()))?;
    let g1_gate = gates
        .into_iter()
        .next()
        .expect("validated G1 bundle contains exactly one gate");
    let g1_binding = g1_gate
        .get("binding")
        .and_then(JsonValue::as_object)
        .expect("validated G1 gate has an object binding");
    let transaction_id = g1_binding
        .get("transaction_id")
        .and_then(JsonValue::as_str)
        .expect("validated G1 binding has a transaction id");

    let (output_path, display_path) = match supplied_output {
        Some(path) => (preliminary_output, path),
        None => {
            let transaction = transaction_id.strip_prefix("tx:").unwrap_or(transaction_id);
            let path = runtime
                .root()
                .join("tasks/update-lifecycle/evidence")
                .join(transaction)
                .join("g2.generated-completeness.json");
            (path.clone(), path)
        }
    };
    let output_path = runtime_output_path(&runtime, &output_path)?;

    let git_head = git_stdout(&source_root, &["rev-parse".to_string(), "HEAD".to_string()])
        .map_err(CliError::failure)?;
    let git_tree = git_stdout(
        &source_root,
        &["rev-parse".to_string(), "HEAD^{tree}".to_string()],
    )
    .map_err(CliError::failure)?;
    let receipt = make_g2_receipt(
        &g1_gate,
        python_strip(&git_head),
        python_strip(&git_tree),
        source_root_string,
    )?;
    let persisted = persist_g2_receipt(&runtime, &output_path, &display_path, &receipt)?;
    Ok((persisted, display_path))
}

fn print_help() {
    println!(
        "{USAGE}\n\n{HELP}\n\noptions:\n  -h, --help                   show this help message and exit\n  --g1-bundle G1_BUNDLE        validated G1 gate bundle\n  --output OUTPUT              optional runtime-owned output path\n  --source-root SOURCE_ROOT    selected source repository\n  --control-parent-root ROOT   distinct attested control repository\n  --runtime-root RUNTIME_ROOT  external runtime root"
    );
}

fn print_usage_error(message: &str) {
    eprintln!("{USAGE}");
    eprintln!("agent-canon {SELECTOR}: error: {message}");
}

pub fn run(args: &[String]) -> i32 {
    let options = match parse_cli(args) {
        Ok(Some(options)) => options,
        Ok(None) => {
            print_help();
            return 0;
        }
        Err(message) => {
            print_usage_error(&message);
            return 2;
        }
    };
    let (persisted, output) = match execute(options) {
        Ok(result) => result,
        Err(error) => {
            if error.show_usage {
                print_usage_error(&error.message);
            } else {
                eprintln!("agent-canon {SELECTOR}: {}", error.message);
            }
            return error.exit_code;
        }
    };
    let evidence_ref = persisted
        .get("binding")
        .and_then(JsonValue::as_object)
        .and_then(|binding| binding.get("evidence_ref"))
        .and_then(JsonValue::as_str)
        .expect("validated G2 receipt has an evidence reference");
    println!("AGENT_CANON_G2_RECEIPT=materialized");
    println!("AGENT_CANON_G2_OUTPUT={}", output.display());
    println!("AGENT_CANON_G2_EVIDENCE_REF={evidence_ref}");
    0
}
