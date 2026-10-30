//! Classify post-run numerical performance observations before a JIT handoff.
//!
//! The input is a closed observation record. The task supplies its trajectory
//! tolerance and mathematical oracle; this module never invents a success
//! threshold or treats timing-only evidence as JIT authorization.
// @dependency-start
// contract tool
// responsibility Classifies post-run numerical performance evidence into math, systems, unresolved, or non-numeric ownership.
// upstream design ../../../../../agents/skills/computational-optimization.md owns convergence-first numerical performance diagnosis
// upstream design ../../../../../agents/skills/cpp-review.md owns the non-numerical native performance boundary
// downstream implementation ../../../../../tests/agent_tools/test_numeric_performance.py tests observation classification
// downstream implementation main.rs registers the numeric-performance CLI command
// @dependency-end

use rustpython_ast::bigint::BigInt;
use serde::Serialize;
use serde_json::{json, Map, Number, Value};
use std::error::Error;
use std::fmt;
use std::fs;
use std::io::{self, Read};

pub const INPUT_SCHEMA: &str = "agent-canon.numeric-performance-observation.v1";
pub const OUTPUT_SCHEMA: &str = "agent-canon.numeric-performance-classification.v1";

const TOP_LEVEL_FIELDS: &[&str] = &[
    "schema",
    "scope",
    "trajectory_tolerance",
    "math_oracle",
    "before",
    "after",
];
const OBSERVATION_FIELDS: &[&str] = &[
    "total_seconds",
    "compile_jit_seconds",
    "iterations",
    "per_iteration_seconds",
    "eval_seconds",
    "linear_solve_seconds",
    "communication_seconds",
    "transfer_seconds",
    "synchronization_seconds",
    "other_seconds",
    "residual_trajectory",
    "objective_trajectory",
    "kkt_trajectory",
    "step_acceptance",
    "step_sizes",
    "termination",
    "conditioning",
    "inner_solver",
    "inner_solver_work",
    "finite_nonfinite_events",
    "work_counters",
    "mathematical_problem",
    "initial_state",
    "stopping_policy",
    "dtype",
    "workload",
    "run_mode",
    "compile_cache_state",
    "backend",
    "device",
    "compiler",
];
const CONTEXT_FIELDS: &[&str] = &[
    "backend",
    "compile_cache_state",
    "compiler",
    "device",
    "dtype",
    "initial_state",
    "mathematical_problem",
    "run_mode",
    "stopping_policy",
    "workload",
];
const WORK_COUNTER_FIELDS: &[&str] = &[
    "evaluation_count",
    "gradient_evaluations",
    "inner_solver_acceptance",
    "inner_solver_iterations",
    "linear_solve_count",
    "linear_solve_iterations",
    "matvec_count",
    "objective_evaluations",
];
const REQUIRED_NUMERICAL_FIELDS: &[&str] = &[
    "compile_jit_seconds",
    "iterations",
    "per_iteration_seconds",
    "eval_seconds",
    "linear_solve_seconds",
    "communication_seconds",
    "transfer_seconds",
    "synchronization_seconds",
    "other_seconds",
    "residual_trajectory",
    "objective_trajectory",
    "kkt_trajectory",
    "step_acceptance",
    "step_sizes",
    "termination",
    "conditioning",
    "inner_solver",
    "inner_solver_work",
    "finite_nonfinite_events",
    "work_counters",
];
const REQUIRED_CONTEXT_FIELDS: &[&str] = &[
    "backend",
    "compile_cache_state",
    "compiler",
    "device",
    "dtype",
    "initial_state",
    "mathematical_problem",
    "run_mode",
    "stopping_policy",
    "workload",
];
const TIMING_FIELDS: &[&str] = &[
    "compile_jit_seconds",
    "per_iteration_seconds",
    "eval_seconds",
    "linear_solve_seconds",
    "communication_seconds",
    "transfer_seconds",
    "synchronization_seconds",
    "other_seconds",
    "total_seconds",
];
const DECOMPOSED_COST_FIELDS: &[&str] = &[
    "compile_jit_seconds",
    "per_iteration_seconds",
    "eval_seconds",
    "linear_solve_seconds",
    "communication_seconds",
    "transfer_seconds",
    "synchronization_seconds",
    "other_seconds",
];
const SEMANTIC_FIELDS: &[&str] = &[
    "conditioning",
    "finite_nonfinite_events",
    "inner_solver",
    "inner_solver_work",
    "iterations",
    "kkt_trajectory",
    "objective_trajectory",
    "residual_trajectory",
    "step_acceptance",
    "step_sizes",
    "termination",
    "work_counters",
];
const TRAJECTORY_FIELDS: &[&str] = &[
    "kkt_trajectory",
    "objective_trajectory",
    "residual_trajectory",
];
const FORBIDDEN_NON_MATH_WRITES: &[&str] = &[
    "architecture",
    "framework",
    "JIT",
    "compiler",
    "backend",
    "runtime",
    "container",
    "routing",
    "environment",
];
const DESCRIPTION: &str = "Classify post-run numerical performance observations before a JIT handoff.\n\nThe input is a closed observation record. Its task supplies trajectory_tolerance and math_oracle. This command never invents a numerical success threshold or treats timing-only evidence as a JIT authorization.";
const USAGE: &str = "usage: numeric-performance [-h] [--input INPUT] [--format {json}]";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ObservationError(String);

impl ObservationError {
    fn new(message: impl Into<String>) -> Self {
        Self(message.into())
    }
}

impl fmt::Display for ObservationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl Error for ObservationError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Scope {
    NumericSolver,
    NonNumeric,
}

#[derive(Debug)]
struct NormalizedPacket {
    scope: Scope,
    trajectory_tolerance: Option<f64>,
    math_oracle: Option<String>,
    before: Map<String, Value>,
    after: Map<String, Value>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SeparateHandoff {
    pub route: String,
    pub status: String,
    pub reason: String,
}

/// Typed result of classifying a normalized post-run observation packet.
#[derive(Debug, Clone, Serialize)]
pub struct Classification {
    pub schema: String,
    pub category: String,
    pub reason_code: String,
    pub owner_route: String,
    pub next_action: String,
    pub forbidden_writes: Vec<String>,
    pub separate_handoff: SeparateHandoff,
    pub evidence: Value,
}

/// Validate and classify one closed post-run observation packet.
///
/// The returned type is stable for native consumers; its fields serialize to
/// the same JSON schema emitted by the command-line entrypoint.
pub fn classify(raw: &Value) -> Result<Classification, ObservationError> {
    let packet = normalize_observation(raw)?;
    let cost = json!({
        "before": cost_decomposition(&packet.before),
        "after": cost_decomposition(&packet.after),
    });
    let mut evidence = Map::new();
    evidence.insert(
        "math_oracle".to_string(),
        packet
            .math_oracle
            .as_ref()
            .map(|oracle| Value::String(oracle.clone()))
            .unwrap_or(Value::Null),
    );
    evidence.insert(
        "trajectory_tolerance".to_string(),
        packet
            .trajectory_tolerance
            .map(number_value)
            .unwrap_or(Value::Null),
    );
    evidence.insert("cost_decomposition".to_string(), cost);

    if packet.scope == Scope::NonNumeric {
        return Ok(result(
            "non_numeric",
            "non_numeric_scope",
            "cpp-review",
            "use the existing native performance review order",
            &[],
            SeparateHandoff {
                route: "computational-optimization".to_string(),
                status: "not_applicable".to_string(),
                reason:
                    "the observation does not describe a numerical solver or iterative algorithm"
                        .to_string(),
            },
            evidence,
        ));
    }

    let missing_before = missing_comparison_fields(&packet.before);
    let missing_after = missing_comparison_fields(&packet.after);
    evidence.insert(
        "missing_fields".to_string(),
        json!({"before": missing_before, "after": missing_after}),
    );
    if !missing_before.is_empty() || !missing_after.is_empty() {
        return Ok(result(
            "evidence_missing",
            "missing_post_run_evidence",
            "computational-optimization",
            "collect the missing trajectory and cost-decomposition metrics before proposing a JIT or architecture edit",
            FORBIDDEN_NON_MATH_WRITES,
            SeparateHandoff {
                route: "jit-backend-performance".to_string(),
                status: "forbidden".to_string(),
                reason: "post-run numerical evidence is incomplete".to_string(),
            },
            evidence,
        ));
    }

    let context_mismatches = REQUIRED_CONTEXT_FIELDS
        .iter()
        .filter(|field| {
            !python_equal(
                packet.before.get(**field).expect("required context field"),
                packet.after.get(**field).expect("required context field"),
            )
        })
        .map(|field| (*field).to_string())
        .collect::<Vec<_>>();
    evidence.insert("context_mismatches".to_string(), json!(context_mismatches));
    if !context_mismatches.is_empty() {
        return Ok(result(
            "evidence_missing",
            "comparison_context_mismatch",
            "computational-optimization",
            "rerun or align the same mathematical problem, initial state, stopping policy, dtype, workload, run mode, cache, backend, device, and compiler before attributing a cost to JIT",
            FORBIDDEN_NON_MATH_WRITES,
            SeparateHandoff {
                route: "jit-backend-performance".to_string(),
                status: "forbidden".to_string(),
                reason: "before/after comparison context is not identical".to_string(),
            },
            evidence,
        ));
    }

    let tolerance = packet
        .trajectory_tolerance
        .expect("numeric solver scope has a tolerance");
    let changed_fields = SEMANTIC_FIELDS
        .iter()
        .filter(|field| {
            let before = packet
                .before
                .get(**field)
                .expect("required numerical field");
            let after = packet.after.get(**field).expect("required numerical field");
            if TRAJECTORY_FIELDS.contains(field) {
                !equivalent(before, after, tolerance)
            } else {
                !python_equal(before, after)
            }
        })
        .map(|field| (*field).to_string())
        .collect::<Vec<_>>();
    evidence.insert(
        "changed_numerical_fields".to_string(),
        json!(changed_fields),
    );
    if !changed_fields.is_empty() {
        return Ok(result(
            "convergence_changed",
            "convergence_or_work_changed",
            "computational-optimization",
            "repair the mathematical or algorithmic mechanism from the first changed iteration; keep JIT and architecture unchanged",
            FORBIDDEN_NON_MATH_WRITES,
            SeparateHandoff {
                route: "jit-backend-performance".to_string(),
                status: "deferred".to_string(),
                reason: "numerical trajectory or iteration behavior changed".to_string(),
            },
            evidence,
        ));
    }

    let positive_cost_regressions = DECOMPOSED_COST_FIELDS
        .iter()
        .filter(|field| {
            numeric_value(packet.after.get(**field).expect("required timing field"))
                > numeric_value(packet.before.get(**field).expect("required timing field"))
        })
        .map(|field| (*field).to_string())
        .collect::<Vec<_>>();
    evidence.insert(
        "positive_cost_regressions".to_string(),
        json!(positive_cost_regressions),
    );
    if positive_cost_regressions.is_empty() {
        let total_increased = numeric_value(
            packet
                .after
                .get("total_seconds")
                .expect("common timing field"),
        ) > numeric_value(
            packet
                .before
                .get("total_seconds")
                .expect("common timing field"),
        );
        return Ok(result(
            "evidence_missing",
            if total_increased {
                "unattributed_total"
            } else {
                "no_positive_decomposed_regression"
            },
            "computational-optimization",
            if total_increased {
                "collect decomposed component timings: total_seconds is only a summary and cannot attribute a JIT or systems regression"
            } else {
                "take no action: the numerical work is equivalent but no positive decomposed performance regression was measured"
            },
            FORBIDDEN_NON_MATH_WRITES,
            SeparateHandoff {
                route: "jit-backend-performance".to_string(),
                status: "forbidden".to_string(),
                reason: "identical or non-regressed timing does not justify a systems edit"
                    .to_string(),
            },
            evidence,
        ));
    }

    Ok(result(
        "systems_cost_isolated",
        "isolated_decomposed_cost_regression",
        "jit-backend-performance",
        "handoff the isolated compile/JIT or per-iteration systems cost with the numerical record attached; do not edit math sources",
        &["mathematical algorithm", "tolerance / stopping semantics"],
        SeparateHandoff {
            route: "computational-optimization".to_string(),
            status: "read_only".to_string(),
            reason: "numerical trajectory, iterations, termination, conditioning, and inner-solver work are equivalent under the task tolerance".to_string(),
        },
        evidence,
    ))
}

fn result(
    category: &str,
    reason_code: &str,
    owner_route: &str,
    next_action: &str,
    forbidden_writes: &[&str],
    separate_handoff: SeparateHandoff,
    evidence: Map<String, Value>,
) -> Classification {
    Classification {
        schema: OUTPUT_SCHEMA.to_string(),
        category: category.to_string(),
        reason_code: reason_code.to_string(),
        owner_route: owner_route.to_string(),
        next_action: next_action.to_string(),
        forbidden_writes: forbidden_writes
            .iter()
            .map(|write| (*write).to_string())
            .collect(),
        separate_handoff,
        evidence: Value::Object(evidence),
    }
}

fn normalize_observation(raw: &Value) -> Result<NormalizedPacket, ObservationError> {
    let input = as_mapping(raw, "input")?;
    let unknown = unknown_fields(input, TOP_LEVEL_FIELDS);
    let missing = missing_fields(input, TOP_LEVEL_FIELDS);
    if !unknown.is_empty() {
        return Err(ObservationError::new(format!(
            "input:unknown_fields:{}",
            unknown.join(",")
        )));
    }
    if !missing.is_empty() {
        return Err(ObservationError::new(format!(
            "input:missing_fields:{}",
            missing.join(",")
        )));
    }
    if input.get("schema") != Some(&Value::String(INPUT_SCHEMA.to_string())) {
        return Err(ObservationError::new("input.schema:mismatch"));
    }
    let scope = match input.get("scope").and_then(Value::as_str) {
        Some("numeric_solver") => Scope::NumericSolver,
        Some("non_numeric") => Scope::NonNumeric,
        _ => return Err(ObservationError::new("input.scope:unknown")),
    };
    let (trajectory_tolerance, math_oracle) = if scope == Scope::NumericSolver {
        let tolerance = number(
            input.get("trajectory_tolerance").expect("required field"),
            "input.trajectory_tolerance",
        )?;
        let oracle = input
            .get("math_oracle")
            .and_then(Value::as_str)
            .filter(|oracle| !oracle.trim().is_empty())
            .ok_or_else(|| ObservationError::new("input.math_oracle:nonempty_string_required"))?;
        (Some(tolerance), Some(oracle.to_string()))
    } else {
        if input.get("trajectory_tolerance") != Some(&Value::Null)
            || input.get("math_oracle") != Some(&Value::Null)
        {
            return Err(ObservationError::new(
                "input.non_numeric:math_fields_must_be_null",
            ));
        }
        (None, None)
    };
    let before = normalize_observation_map(input.get("before").expect("required field"), "before")?;
    let after = normalize_observation_map(input.get("after").expect("required field"), "after")?;
    Ok(NormalizedPacket {
        scope,
        trajectory_tolerance,
        math_oracle,
        before,
        after,
    })
}

fn normalize_observation_map(
    raw: &Value,
    field: &str,
) -> Result<Map<String, Value>, ObservationError> {
    let observation = as_mapping(raw, field)?;
    let unknown = unknown_fields(observation, OBSERVATION_FIELDS);
    if !unknown.is_empty() {
        return Err(ObservationError::new(format!(
            "{field}:unknown_fields:{}",
            unknown.join(",")
        )));
    }
    let missing = missing_fields(observation, &["total_seconds"]);
    if !missing.is_empty() {
        return Err(ObservationError::new(format!(
            "{field}:missing_fields:{}",
            missing.join(",")
        )));
    }
    let total_seconds = number(
        observation.get("total_seconds").expect("required field"),
        &format!("{field}.total_seconds"),
    )?;
    let mut normalized = Map::new();
    normalized.insert("total_seconds".to_string(), number_value(total_seconds));
    for (name, item) in observation {
        if name == "total_seconds" {
            continue;
        }
        let item_field = format!("{field}.{name}");
        let value = if name.ends_with("_seconds") {
            number(item, &item_field).map(number_value)?
        } else if name == "iterations" {
            nonnegative_integer(item, &item_field)?
        } else if matches!(
            name.as_str(),
            "residual_trajectory" | "objective_trajectory" | "kkt_trajectory" | "step_sizes"
        ) {
            number_list(item, &item_field)?
        } else if name == "step_acceptance" {
            bool_list(item, &item_field)?
        } else if name == "finite_nonfinite_events" {
            string_list(item, &item_field)?
        } else if name == "termination" {
            nonempty_string(item, &item_field)?
        } else if name == "conditioning" || name == "inner_solver_work" {
            number(item, &item_field).map(number_value)?
        } else if name == "inner_solver" {
            normalize_inner_solver(item, &item_field)?
        } else if name == "work_counters" {
            normalize_work_counters(item, &item_field)?
        } else if CONTEXT_FIELDS.contains(&name.as_str()) {
            let value = context_value(item, &item_field)?;
            if name == "run_mode" && !matches!(value.as_str(), Some("cold") | Some("warm")) {
                return Err(ObservationError::new(format!(
                    "{item_field}:cold_or_warm_required"
                )));
            }
            value
        } else {
            return Err(ObservationError::new(format!("{item_field}:unsupported")));
        };
        normalized.insert(name.clone(), value);
    }
    Ok(normalized)
}

fn normalize_inner_solver(raw: &Value, field: &str) -> Result<Value, ObservationError> {
    let value = as_mapping(raw, field)?;
    const EXPECTED: &[&str] = &["name", "iterations", "work"];
    let unknown = unknown_fields(value, EXPECTED);
    let missing = missing_fields(value, EXPECTED);
    if !unknown.is_empty() {
        return Err(ObservationError::new(format!(
            "{field}:unknown_fields:{}",
            unknown.join(",")
        )));
    }
    if !missing.is_empty() {
        return Err(ObservationError::new(format!(
            "{field}:missing_fields:{}",
            missing.join(",")
        )));
    }
    let name = nonempty_string(
        value.get("name").expect("required field"),
        &format!("{field}.name"),
    )?;
    let iterations = nonnegative_integer(
        value.get("iterations").expect("required field"),
        &format!("{field}.iterations"),
    )?;
    let work = number(
        value.get("work").expect("required field"),
        &format!("{field}.work"),
    )?;
    let mut normalized = Map::new();
    normalized.insert("name".to_string(), name);
    normalized.insert("iterations".to_string(), iterations);
    normalized.insert("work".to_string(), number_value(work));
    Ok(Value::Object(normalized))
}

fn normalize_work_counters(raw: &Value, field: &str) -> Result<Value, ObservationError> {
    let value = as_mapping(raw, field)?;
    let unknown = unknown_fields(value, WORK_COUNTER_FIELDS);
    let missing = missing_fields(value, WORK_COUNTER_FIELDS);
    if !unknown.is_empty() {
        return Err(ObservationError::new(format!(
            "{field}:unknown_fields:{}",
            unknown.join(",")
        )));
    }
    if !missing.is_empty() {
        return Err(ObservationError::new(format!(
            "{field}:missing_fields:{}",
            missing.join(",")
        )));
    }
    let mut normalized = Map::new();
    for name in WORK_COUNTER_FIELDS {
        let item = value.get(*name).expect("required work counter");
        let item_field = format!("{field}.{name}");
        let normalized_item = if *name == "inner_solver_acceptance" {
            bool_list(item, &item_field)?
        } else {
            nonnegative_integer(item, &item_field)?
        };
        normalized.insert((*name).to_string(), normalized_item);
    }
    Ok(Value::Object(normalized))
}

fn as_mapping<'a>(
    value: &'a Value,
    field: &str,
) -> Result<&'a Map<String, Value>, ObservationError> {
    value
        .as_object()
        .ok_or_else(|| ObservationError::new(format!("{field}:mapping_required")))
}

fn unknown_fields(value: &Map<String, Value>, expected: &[&str]) -> Vec<String> {
    let mut fields = value
        .keys()
        .filter(|name| !expected.contains(&name.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    fields.sort();
    fields
}

fn missing_fields(value: &Map<String, Value>, expected: &[&str]) -> Vec<String> {
    let mut fields = expected
        .iter()
        .filter(|field| !value.contains_key(**field))
        .map(|field| (*field).to_string())
        .collect::<Vec<_>>();
    fields.sort();
    fields
}

fn nonempty_string(value: &Value, field: &str) -> Result<Value, ObservationError> {
    match value.as_str() {
        Some(value) if !value.trim().is_empty() => Ok(Value::String(value.to_string())),
        _ => Err(ObservationError::new(format!(
            "{field}:nonempty_string_required"
        ))),
    }
}

fn number(value: &Value, field: &str) -> Result<f64, ObservationError> {
    let Some(number) = value.as_number() else {
        return Err(ObservationError::new(format!("{field}:number_required")));
    };
    let Some(number) = number.as_f64() else {
        return Err(ObservationError::new(format!(
            "{field}:finite_nonnegative_required"
        )));
    };
    if !number.is_finite() || number < 0.0 {
        return Err(ObservationError::new(format!(
            "{field}:finite_nonnegative_required"
        )));
    }
    Ok(number)
}

fn scalar(value: &Value, field: &str) -> Result<Value, ObservationError> {
    let Some(number) = value.as_number() else {
        return Err(ObservationError::new(format!("{field}:number_required")));
    };
    let Some(number) = number.as_f64() else {
        return Err(ObservationError::new(format!(
            "{field}:finite_number_required"
        )));
    };
    if !number.is_finite() {
        return Err(ObservationError::new(format!(
            "{field}:finite_number_required"
        )));
    }
    Ok(number_value(number))
}

fn number_list(value: &Value, field: &str) -> Result<Value, ObservationError> {
    let Some(items) = value.as_array() else {
        return Err(ObservationError::new(format!("{field}:list_required")));
    };
    items
        .iter()
        .enumerate()
        .map(|(index, item)| scalar(item, &format!("{field}[{index}]")))
        .collect::<Result<Vec<_>, _>>()
        .map(Value::Array)
}

fn bool_list(value: &Value, field: &str) -> Result<Value, ObservationError> {
    let Some(items) = value.as_array() else {
        return Err(ObservationError::new(format!(
            "{field}:boolean_list_required"
        )));
    };
    if items.iter().any(|item| !item.is_boolean()) {
        return Err(ObservationError::new(format!(
            "{field}:boolean_list_required"
        )));
    }
    Ok(value.clone())
}

fn string_list(value: &Value, field: &str) -> Result<Value, ObservationError> {
    let Some(items) = value.as_array() else {
        return Err(ObservationError::new(format!("{field}:list_required")));
    };
    for (index, item) in items.iter().enumerate() {
        if !matches!(item.as_str(), Some(value) if !value.trim().is_empty()) {
            return Err(ObservationError::new(format!(
                "{field}[{index}]:nonempty_string_required"
            )));
        }
    }
    Ok(value.clone())
}

fn nonnegative_integer(value: &Value, field: &str) -> Result<Value, ObservationError> {
    let Some(number) = value.as_number() else {
        return Err(ObservationError::new(format!(
            "{field}:nonnegative_integer_required"
        )));
    };
    if nonnegative_integer_number(number) {
        Ok(value.clone())
    } else {
        Err(ObservationError::new(format!(
            "{field}:nonnegative_integer_required"
        )))
    }
}

fn context_value(value: &Value, field: &str) -> Result<Value, ObservationError> {
    match value {
        Value::String(value) if !value.trim().is_empty() => Ok(Value::String(value.clone())),
        Value::Bool(_) => Ok(value.clone()),
        Value::Number(number) => {
            if number.as_f64().is_some_and(f64::is_finite) {
                Ok(value.clone())
            } else {
                Err(ObservationError::new(format!(
                    "{field}:finite_number_required"
                )))
            }
        }
        Value::Array(items) => items
            .iter()
            .enumerate()
            .map(|(index, item)| context_value(item, &format!("{field}[{index}]")))
            .collect::<Result<Vec<_>, _>>()
            .map(Value::Array),
        Value::Object(items) => {
            let mut normalized = Map::new();
            for (key, item) in items {
                if key.trim().is_empty() {
                    return Err(ObservationError::new(format!(
                        "{field}:string_keys_required"
                    )));
                }
                normalized.insert(key.clone(), context_value(item, &format!("{field}.{key}"))?);
            }
            Ok(Value::Object(normalized))
        }
        _ => Err(ObservationError::new(format!(
            "{field}:json_identity_required"
        ))),
    }
}

fn missing_comparison_fields(observation: &Map<String, Value>) -> Vec<String> {
    let mut fields = REQUIRED_NUMERICAL_FIELDS
        .iter()
        .chain(REQUIRED_CONTEXT_FIELDS.iter())
        .filter(|field| !observation.contains_key(**field))
        .map(|field| (*field).to_string())
        .collect::<Vec<_>>();
    fields.sort();
    fields.dedup();
    fields
}

fn cost_decomposition(observation: &Map<String, Value>) -> Value {
    let mut result = Map::new();
    result.insert(
        "iterations".to_string(),
        observation
            .get("iterations")
            .cloned()
            .unwrap_or(Value::Null),
    );
    for field in TIMING_FIELDS {
        result.insert(
            (*field).to_string(),
            observation.get(*field).cloned().unwrap_or(Value::Null),
        );
    }
    Value::Object(result)
}

fn numeric_value(value: &Value) -> f64 {
    value
        .as_number()
        .and_then(Number::as_f64)
        .expect("validated numeric field")
}

fn number_value(value: f64) -> Value {
    Value::Number(Number::from_f64(value).expect("validated finite number"))
}

fn equivalent(left: &Value, right: &Value, tolerance: f64) -> bool {
    if let (Some(left), Some(right)) = (
        numeric_for_equivalence(left),
        numeric_for_equivalence(right),
    ) {
        return is_close(left, right, tolerance);
    }
    match (left, right) {
        (Value::Array(left), Value::Array(right)) => {
            left.len() == right.len()
                && left
                    .iter()
                    .zip(right)
                    .all(|(left, right)| equivalent(left, right, tolerance))
        }
        (Value::Object(left), Value::Object(right)) => {
            left.len() == right.len()
                && left.iter().all(|(key, value)| {
                    right
                        .get(key)
                        .is_some_and(|other| equivalent(value, other, tolerance))
                })
        }
        _ => python_equal(left, right),
    }
}

fn numeric_for_equivalence(value: &Value) -> Option<f64> {
    match value {
        Value::Number(number) => number.as_f64(),
        Value::Bool(value) => Some(if *value { 1.0 } else { 0.0 }),
        _ => None,
    }
}

fn is_close(left: f64, right: f64, tolerance: f64) -> bool {
    left == right
        || (left - right).abs() <= (tolerance * left.abs().max(right.abs())).max(tolerance)
}

fn python_equal(left: &Value, right: &Value) -> bool {
    match (left, right) {
        (Value::Null, Value::Null) => true,
        (Value::Bool(left), Value::Bool(right)) => left == right,
        (Value::Bool(boolean), Value::Number(number))
        | (Value::Number(number), Value::Bool(boolean)) => number_equals_bool(number, *boolean),
        (Value::Number(left), Value::Number(right)) => numbers_equal(left, right),
        (Value::String(left), Value::String(right)) => left == right,
        (Value::Array(left), Value::Array(right)) => {
            left.len() == right.len()
                && left
                    .iter()
                    .zip(right)
                    .all(|(left, right)| python_equal(left, right))
        }
        (Value::Object(left), Value::Object(right)) => {
            left.len() == right.len()
                && left.iter().all(|(key, value)| {
                    right
                        .get(key)
                        .is_some_and(|other| python_equal(value, other))
                })
        }
        _ => false,
    }
}

// `serde_json`'s arbitrary-precision Number retains large integer tokens.
// Keep context identity in BigInt form instead of rounding it through f64.
fn integer_value(number: &Number) -> Option<BigInt> {
    let representation = number.as_str();
    if representation.contains('.') || representation.contains('e') || representation.contains('E')
    {
        return None;
    }
    representation.parse().ok()
}

// Convert an integral IEEE-754 value to its exact integer value while retaining
// Python's int/float equality behavior across the full finite f64 range.
fn float_integer_value(value: f64) -> Option<BigInt> {
    if !value.is_finite() || value.fract() != 0.0 {
        return None;
    }
    let bits = value.to_bits();
    let negative = bits >> 63 != 0;
    let exponent_bits = ((bits >> 52) & 0x7ff) as i32;
    let fraction = bits & ((1_u64 << 52) - 1);
    let (significand, shift) = if exponent_bits == 0 {
        (fraction, -1074)
    } else {
        ((1_u64 << 52) | fraction, exponent_bits - 1023 - 52)
    };
    if significand == 0 {
        return Some(BigInt::from(0_u8));
    }
    let mut integer = BigInt::from(significand);
    if shift < 0 {
        let right_shift = (-shift) as u32;
        if right_shift >= u64::BITS || significand & ((1_u64 << right_shift) - 1) != 0 {
            return None;
        }
        integer = BigInt::from(significand >> right_shift);
    } else if shift > 0 {
        integer = integer << shift as usize;
    }
    Some(if negative { -integer } else { integer })
}

fn numbers_equal(left: &Number, right: &Number) -> bool {
    match (integer_value(left), integer_value(right)) {
        (Some(left), Some(right)) => left == right,
        (Some(integer), None) => right
            .as_f64()
            .and_then(float_integer_value)
            .is_some_and(|float_integer| integer == float_integer),
        (None, Some(integer)) => left
            .as_f64()
            .and_then(float_integer_value)
            .is_some_and(|float_integer| integer == float_integer),
        (None, None) => left.as_f64() == right.as_f64(),
    }
}

fn number_equals_bool(number: &Number, boolean: bool) -> bool {
    match integer_value(number) {
        Some(integer) => integer == BigInt::from(u8::from(boolean)),
        None => number
            .as_f64()
            .is_some_and(|value| value == if boolean { 1.0 } else { 0.0 }),
    }
}

fn nonnegative_integer_number(number: &Number) -> bool {
    matches!(integer_value(number), Some(integer) if integer >= BigInt::from(0_u8))
}

/// Run the `numeric-performance` command with command arguments (excluding the
/// executable and subcommand), returning its process exit code.
pub fn run(args: &[String]) -> i32 {
    let input_path = match parse_args(args) {
        Ok(ParseOutcome::Help) => {
            print_help();
            return 0;
        }
        Ok(ParseOutcome::Arguments(arguments)) => arguments.input,
        Err(error) => {
            print_argument_error(&error);
            return 2;
        }
    };
    let result = match read_input(input_path.as_deref()) {
        Ok(input) => match classify(&input) {
            Ok(classification) => serde_json::to_value(classification)
                .expect("classification is representable as JSON"),
            Err(error) => error_value(error.to_string()),
        },
        Err(error) => error_value(error),
    };
    println!(
        "{}",
        serde_json::to_string(&result).expect("JSON result serializes")
    );
    if result.get("status") == Some(&Value::String("error".to_string())) {
        2
    } else {
        0
    }
}

#[derive(Debug)]
struct CliArguments {
    input: Option<String>,
}

enum ParseOutcome {
    Help,
    Arguments(CliArguments),
}

fn parse_args(args: &[String]) -> Result<ParseOutcome, String> {
    let mut input = None;
    let mut format = "json";
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if matches!(argument.as_str(), "-h" | "--help") {
            return Ok(ParseOutcome::Help);
        }
        if argument == "--input" {
            index += 1;
            let Some(value) = args.get(index) else {
                return Err("argument --input: expected one argument".to_string());
            };
            if value.starts_with('-') && value != "-" {
                return Err("argument --input: expected one argument".to_string());
            }
            input = Some(value.clone());
        } else if let Some(value) = argument.strip_prefix("--input=") {
            input = Some(value.to_string());
        } else if argument == "--format" {
            index += 1;
            let Some(value) = args.get(index) else {
                return Err("argument --format: expected one argument".to_string());
            };
            if value.starts_with('-') {
                return Err("argument --format: expected one argument".to_string());
            }
            if value != "json" {
                return Err(format!(
                    "argument --format: invalid choice: '{value}' (choose from 'json')"
                ));
            }
            format = "json";
        } else if let Some(value) = argument.strip_prefix("--format=") {
            if value != "json" {
                return Err(format!(
                    "argument --format: invalid choice: '{value}' (choose from 'json')"
                ));
            }
            format = "json";
        } else {
            return Err(format!("unrecognized arguments: {argument}"));
        }
        index += 1;
    }
    let _selected_format = format;
    Ok(ParseOutcome::Arguments(CliArguments { input }))
}

fn print_help() {
    println!("{USAGE}\n\n{DESCRIPTION}\n\noptions:\n  -h, --help       show this help message and exit\n  --input INPUT    post-run observation JSON path; use - or omit for stdin\n  --format {{json}}  output format");
}

fn print_argument_error(error: &str) {
    eprintln!("{USAGE}\nnumeric-performance: error: {error}");
}

fn read_input(path: Option<&str>) -> Result<Value, String> {
    let mut text = String::new();
    match path {
        None | Some("-") => {
            io::stdin()
                .lock()
                .read_to_string(&mut text)
                .map_err(|error| error.to_string())?;
        }
        Some(path) => {
            text = fs::read_to_string(path).map_err(|error| error.to_string())?;
        }
    }
    serde_json::from_str(&text).map_err(|error| error.to_string())
}

fn error_value(error: String) -> Value {
    json!({
        "schema": OUTPUT_SCHEMA,
        "status": "error",
        "reason_code": "invalid_input",
        "error": error,
    })
}
