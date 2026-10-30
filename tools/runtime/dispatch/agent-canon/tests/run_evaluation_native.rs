// @dependency-start
// contract test
// responsibility Verifies native run-evaluation selection, scoring, shared checks, and external output.
// upstream implementation ../src/run_evaluation.rs implements the evaluation API and CLI
// upstream implementation ../src/report_artifact_checks.rs owns pure report checks
// upstream implementation ../src/eval_manifest_paths.rs owns canonical/legacy Eval source paths
// upstream design ../../../../../eval/definitions/agent_behavior_eval.toml defines behavior criteria
// downstream implementation ../../../../../tools/runtime/lifecycle/task_close.py consumes evaluator status
// @dependency-end

use agent_canon::eval_manifest_paths::{eval_manifest_path, resolve_eval_manifest};
use agent_canon::report_artifact_checks::{
    check_final_review_artifact, check_schedule_artifact, check_work_log_artifact,
};
use agent_canon::run_evaluation::{
    evaluate_run, load_behavior_manifest, CriterionResult, PLANNED_WORK_AND_CHRONOLOGY_SCORE,
};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_FIXTURE: AtomicU64 = AtomicU64::new(0);

struct Fixture(PathBuf);

impl Fixture {
    fn new(label: &str) -> Self {
        let id = NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-run-evaluation-{}-{label}-{id}",
            std::process::id()
        ));
        fs::create_dir_all(&path).unwrap();
        Self(path)
    }

    fn root(&self) -> &Path {
        &self.0
    }

    fn write(&self, name: &str, text: &str) {
        let path = self.0.join(name);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, text).unwrap();
    }

    fn remove(&self, name: &str) {
        let _ = fs::remove_file(self.0.join(name));
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

const READY_OUTPUTS: &[&str] = &[
    "user_request_contract.md",
    "schedule.md",
    "work_log.md",
    "workflow_monitoring.md",
    "change_review.md",
    "final_review.md",
    "verification.txt",
    "closeout_gate.md",
    "retrospective.md",
];

fn schedule() -> &'static str {
    "# Schedule\n\n## Stage Plan\n| Stage | Owner Agent | Review Agent | Inputs | Exit Criteria | Status |\n| ----- | ----------- | ------------ | ------ | ------------- | ------ |\n| requirements | manager | reviewer | request | fixed | complete |\n## Clause Coverage\n| Clause ID | Covered By Stage | Review Gate | Status |\n| --------- | ---------------- | ----------- | ------ |\n| C1 | requirements | review | complete |\n## Planned Work Units\n| Unit ID | Clause IDs | Owner | Completion Evidence | Next Gate | Status |\n| ------- | ---------- | ----- | ------------------- | --------- | ------ |\n| W1 | C1 | codex | tests | closeout | complete |\n"
}

fn work_log() -> &'static str {
    "# Work Log\n## Purpose\n- Record execution.\n## Entries\n- kickoff: request_clause_ids=C1 skills=$agent-orchestration stage=implementation\n- validation: repo_dependency_review=pass next=closeout\n"
}

fn write_manifest(fixture: &Fixture, required: &[&str], materialized: &[&str]) {
    let mut lines = vec![
        "run:".to_string(),
        "  id: fixture-run".to_string(),
        "  task: bounded native evaluation".to_string(),
        "roles:".to_string(),
        "  - id: evaluator".to_string(),
        "    required_outputs:".to_string(),
    ];
    lines.extend(required.iter().map(|name| format!("      - {name}")));
    lines.push("artifacts:".to_string());
    lines.push("  - team_manifest.yaml".to_string());
    lines.extend(materialized.iter().map(|name| format!("  - {name}")));
    fixture.write("team_manifest.yaml", &(lines.join("\n") + "\n"));
}

fn write_ready_run(fixture: &Fixture, required: &[&str]) {
    fixture.write(
        "user_request_contract.md",
        "- all_clauses_resolved: yes\n- forbidden_drift_detected: no\n- unresolved_clause_ids:\n",
    );
    fixture.write("schedule.md", schedule());
    fixture.write("work_log.md", work_log());
    fixture.write(
        "workflow_monitoring.md",
        "# Workflow Monitoring\n## Signals\n- skills=$agent-orchestration,$codex-task-workflow\n- stage owner=codex subagent=worker write_capable_child=yes\n- repo_dependency_review=pass\n- web_research_not_required: local test\n- review_status=approve\n- validation_status=pass\n- drift_risk=none\n## Behavior Events\n- generated_role_view_v1 profile-attribution topology_derived_v1 declared_team_peak_plus_nested_reservations_v1 requested_capacity_loader model-capacity thread-capacity\n- skill_invocation=$agent-orchestration status=observed\n- subagent_routing=worker stage=implementation write_capable_child=yes child_execution_receipts=pass status=observed\n- tool_call=run_repo_dependency_review.sh status=pass\n- tool_call=pyright code_checker=pass checker=pyright scope=repo-wide\n- tool_call=ruff code_checker=pass checker=ruff scope=repo-wide\n- tool_call=oop-readability-check code_checker=pass checker=oop-readability scope=changed-paths\n- validation_failure_not_observed reason=native-test\n- execution_path_comparison=pass route_efficiency=efficient selected_inefficient_route=no\n- static_analysis_feedback=applied\n- hook_tool_feedback=reviewed parent_protocol_update=applied subagent_protocol_update=applied protocol_feedback_reason=native-test\n- runtime_feedback=observed source=user action=prompt_repair evidence=native-test\n- review_decision=approve feedback_actions_resolved=yes\n- subagent_lifecycle=closed subagents_closed=yes\n- diff_check_not_required reason=native-test\n- token_efficiency_not_required reason=native-test\n## Tool Warnings\n- tool_warnings_status: none\n## Interventions\n- Kept work bounded.\n## Improvement Decisions\n- skill_improvement_decision: recorded\n- config_improvement_decision: not_applicable\n- workflow_improvement_decision: not_applicable\n- knowledge_learning_decision: not_applicable\n",
    );
    fixture.write(
        "runtime/child_execution_receipts.json",
        &child_receipt_json(),
    );
    fixture.write(
        "change_review.md",
        "# Change Review\n## Chunk Findings\nNo fix-now findings are open.\n",
    );
    fixture.write("final_review.md", "# Final Review\n## Decision\napprove\n");
    fixture.write("verification.txt", "status=pass\n");
    fixture.write(
        "closeout_gate.md",
        "- validation_complete: yes\n- dependency_headers_complete: yes\n- repo_wide_dependency_tools_complete: yes\n- repo_wide_static_analysis_complete: yes\n- canonical_tree_head_complete: yes\n- commit_created: yes\n- push_completed: yes\ncontract_observation=none contract_observation_schema=agent-canon.task-contract-observation.v1 task_contract_observation_eval_status=pass task_contract_observation_digest=fixture task_contract_observation_coverage=complete task_contract_resolution=terminal task_contract_observation_unresolved=none contract_archive_route=agent-canon-log:agent-reports\n",
    );
    fixture.write(
        "retrospective.md",
        "# Retrospective\n## What Worked\n- Stable\n## What Hurt\n- None\n## Follow-ups\n- None\n",
    );
    write_manifest(fixture, required, required);
}

fn child_receipt_json() -> String {
    let unsigned = serde_json::json!({
        "schema": "agent-canon.child-execution-receipts.v1",
        "spawn": {"agent_id": "worker-1", "role_id": "implementer", "scope_digest": "scope-1"},
        "mutations": [{"actor_id": "worker-1", "role_id": "implementer", "scope_digest": "scope-1", "status": "allowed"}],
        "close": {"agent_id": "worker-1", "status": "closed"},
    });
    let bytes = serde_json::to_vec(&unsigned).unwrap();
    let digest = sha256_hex(&bytes);
    let mut record = unsigned.as_object().unwrap().clone();
    record.insert("receipt_sha256".to_string(), serde_json::json!(digest));
    serde_json::to_string(&serde_json::Value::Object(record)).unwrap()
}

fn sha256_hex(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn source_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../../")
}

fn evaluate(fixture: &Fixture) -> agent_canon::run_evaluation::EvaluationReport {
    let source = source_root();
    let manifest = source.join(eval_manifest_path("agent_behavior_eval.toml"));
    let criteria = load_behavior_manifest(&manifest).unwrap();
    evaluate_run(fixture.root(), &criteria, &source, 85).unwrap()
}

fn criterion<'a>(
    report: &'a agent_canon::run_evaluation::EvaluationReport,
    name: &str,
) -> &'a CriterionResult {
    report
        .criteria
        .iter()
        .find(|item| item.name == name)
        .unwrap()
}

#[test]
fn selected_valid_schedule_and_work_log_keep_fixed_criteria_maxima() {
    let fixture = Fixture::new("selected-valid");
    write_ready_run(&fixture, READY_OUTPUTS);
    let report = evaluate(&fixture);
    assert_eq!(criterion(&report, "planned_work_and_chronology").score, 10);
    assert_eq!(
        criterion(&report, "planned_work_and_chronology").max_score,
        PLANNED_WORK_AND_CHRONOLOGY_SCORE
    );
    assert_eq!(criterion(&report, "artifact_completeness").score, 8);
    assert_eq!(criterion(&report, "artifact_completeness").max_score, 8);
}

#[test]
fn selected_missing_schedule_fails_both_fixed_score_claims() {
    let fixture = Fixture::new("selected-missing-schedule");
    write_ready_run(&fixture, READY_OUTPUTS);
    fixture.remove("schedule.md");
    let report = evaluate(&fixture);
    assert_eq!(criterion(&report, "planned_work_and_chronology").score, 0);
    assert_eq!(
        criterion(&report, "planned_work_and_chronology").max_score,
        10
    );
    assert_eq!(criterion(&report, "artifact_completeness").score, 0);
    assert_eq!(criterion(&report, "artifact_completeness").max_score, 8);
    assert!(report
        .blockers
        .iter()
        .any(|item| item.contains("schedule.md")));
}

#[test]
fn required_schedule_missing_from_expected_materialization_is_missing() {
    let fixture = Fixture::new("missing-materialization");
    write_ready_run(&fixture, READY_OUTPUTS);
    let materialized = READY_OUTPUTS
        .iter()
        .copied()
        .filter(|name| *name != "schedule.md")
        .collect::<Vec<_>>();
    write_manifest(&fixture, READY_OUTPUTS, &materialized);
    assert!(fixture.root().join("schedule.md").is_file());
    let report = evaluate(&fixture);
    assert_eq!(criterion(&report, "planned_work_and_chronology").score, 0);
    assert_eq!(criterion(&report, "artifact_completeness").score, 0);
}

#[test]
fn unselected_schedule_absence_or_malformed_contents_are_ignored() {
    let selected_without_schedule = READY_OUTPUTS
        .iter()
        .copied()
        .filter(|name| *name != "schedule.md")
        .collect::<Vec<_>>();
    for (case, malformed) in [("absent", false), ("malformed", true)] {
        let fixture = Fixture::new(case);
        write_ready_run(&fixture, &selected_without_schedule);
        fixture.remove("schedule.md");
        if malformed {
            fixture.write("schedule.md", "not a schedule; missing every section");
        }
        let report = evaluate(&fixture);
        assert_eq!(criterion(&report, "planned_work_and_chronology").score, 10);
        assert_eq!(criterion(&report, "artifact_completeness").score, 8);
    }
}

#[test]
fn empty_planning_selection_is_neutral_only_for_that_criterion() {
    let selected = READY_OUTPUTS
        .iter()
        .copied()
        .filter(|name| *name != "schedule.md" && *name != "work_log.md")
        .collect::<Vec<_>>();
    let fixture = Fixture::new("empty-selection");
    write_ready_run(&fixture, &selected);
    fixture.remove("schedule.md");
    fixture.remove("work_log.md");
    let report = evaluate(&fixture);
    assert_eq!(criterion(&report, "planned_work_and_chronology").score, 10);
    assert_eq!(criterion(&report, "artifact_completeness").score, 8);
    assert!(report
        .criteria
        .iter()
        .any(|item| item.name == "request_traceability"));
    assert!(report
        .criteria
        .iter()
        .any(|item| item.name == "workflow_monitoring"));
}

#[test]
fn missing_or_invalid_selection_metadata_is_unknown_and_blocks() {
    let fixture = Fixture::new("missing-selection");
    write_ready_run(&fixture, READY_OUTPUTS);
    fixture.remove("team_manifest.yaml");
    let report = evaluate(&fixture);
    assert!(matches!(
        report
            .criteria
            .iter()
            .find(|item| item.name == "artifact_completeness")
            .unwrap()
            .status
            .as_str(),
        "revise"
    ));
    assert_eq!(criterion(&report, "artifact_completeness").score, 0);
    assert_eq!(criterion(&report, "planned_work_and_chronology").score, 0);
    assert!(report
        .blockers
        .iter()
        .any(|item| item.contains("team_manifest.yaml")));

    let malformed = Fixture::new("invalid-selection");
    write_ready_run(&malformed, READY_OUTPUTS);
    malformed.write(
        "team_manifest.yaml",
        "run:\n  id: invalid\nroles:\n  - id: evaluator\nartifacts:\n  - schedule.md\n",
    );
    let report = evaluate(&malformed);
    assert_eq!(criterion(&report, "planned_work_and_chronology").score, 0);
    assert!(report
        .blockers
        .iter()
        .any(|item| item.contains("required_outputs")));
}

#[test]
fn shared_schedule_work_log_and_final_review_checks_keep_their_oracles() {
    assert!(check_schedule_artifact(schedule()).is_empty());
    let empty_units = schedule().replace("| W1 | C1 | codex | tests | closeout | complete |\n", "");
    assert!(check_schedule_artifact(&empty_units)
        .iter()
        .any(|item| item == "schedule.md:planned_work_units_empty"));
    assert!(check_work_log_artifact(work_log()).is_empty());
    assert!(
        check_work_log_artifact("## Entries\nmeaningful prose but no bullet row\n")
            .contains(&"work_log.md:entries_empty".to_string())
    );
    assert!(check_final_review_artifact("## Decision\napprove\n").is_empty());
    assert!(check_final_review_artifact("## Decision\nnot approved\n")
        .contains(&"final_review.md:decision_not_approve".to_string()));
}

#[test]
fn canonical_manifest_path_and_legacy_alias_resolution_are_preserved() {
    let root = Path::new("/repo");
    assert_eq!(
        resolve_eval_manifest(root, "eval/definitions/agent_behavior_eval.toml"),
        root.join("eval/definitions/agent_behavior_eval.toml")
    );
    assert_eq!(
        resolve_eval_manifest(root, "agents/evals/agent_behavior_eval.toml"),
        root.join("eval/definitions/agent_behavior_eval.toml")
    );
}

#[test]
fn native_cli_writes_only_through_explicit_external_runtime_boundary() {
    let fixture = Fixture::new("cli-output");
    write_ready_run(&fixture, READY_OUTPUTS);
    let runtime = fixture.root().join("external-runtime");
    fs::create_dir_all(&runtime).unwrap();
    let source = source_root();
    let behavior = source.join(eval_manifest_path("agent_behavior_eval.toml"));
    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args([
            "run-evaluation",
            "--report-dir",
            fixture.root().to_str().unwrap(),
            "--workspace-root",
            source.to_str().unwrap(),
            "--behavior-manifest",
            behavior.to_str().unwrap(),
            "--runtime-root",
            runtime.to_str().unwrap(),
            "--write",
        ])
        .output()
        .unwrap();
    assert_eq!(
        output.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("AGENT_EVALUATION_STATUS=pass"));
    assert!(runtime.join("agent_evaluation.md").is_file());
    assert!(!fixture.root().join("agent_evaluation.md").exists());
}
