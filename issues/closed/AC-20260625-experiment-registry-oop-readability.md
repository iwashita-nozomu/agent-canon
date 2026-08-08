<!--
@dependency-start
contract issue
responsibility Tracks OOP readability refactor work for the experiment registry checker.
upstream implementation ../../tools/ci/check_experiment_registry.py validates experiment registry contracts.
upstream implementation ../../tools/oop/python/readability.py reports OOP readability findings.
upstream design ../../documents/conventions/object-oriented-design.md defines OOP readability policy.
@dependency-end
-->

# Experiment Registry Checker OOP Readability

date: 2026-06-25
issue_id: AC-20260625-experiment-registry-oop-readability
status: resolved
severity: follow-up
owner: AgentCanon
source: OOP readability validation during managed experiment reproducibility log work
evidence: `python3 tools/oop/python/readability.py --root . --format text tools/ci/check_experiment_registry.py tests/tools/test_run_managed_experiment.py`
affected_surfaces: tools/ci/check_experiment_registry.py, tests/tools/test_run_managed_experiment.py
edit_scope: tools/ci/check_experiment_registry.py validation helper extraction and topic orchestration split
required_action: Split registry value extraction, finding construction, and topic-level validation orchestration while preserving registry behavior.
close_condition: OOP readability reports no new findings against HEAD and no named issue findings; focused registry tests pass; and the checker exits 0 for a valid registry root.
resolved_by: current AgentCanon GitHub issue-resolution branch; OOP readability and focused registry validation
resolved_at: 2026-08-08

## Finding

`python3 tools/oop/python/readability.py --root . tools/ci/check_experiment_registry.py tests/tools/test_run_managed_experiment.py`
reported existing findings in `tools/ci/check_experiment_registry.py`.

Current findings:

- `repo_root_from_script`: mixed return/effect boundary
- `require_string`: mixed return/effect boundary
- `require_registered_command`: mixed return/effect boundary
- `maybe_string_list`: mixed return/effect boundary
- `validate_topic`: cognitive complexity

## Required Repair

Refactor `check_experiment_registry.py` by separating value extraction, finding
construction, and topic-level orchestration. Keep the registry contract behavior
and current test coverage intact.

## Validation

```bash
python3 -m pytest tests/tools/test_run_managed_experiment.py -q
python3 tools/oop/python/readability.py --root . --format text --baseline-ref HEAD tools/ci/check_experiment_registry.py tests/tools/test_run_managed_experiment.py
python3 tools/ci/check_experiment_registry.py --repo-root <valid-registry-root>
python3 -m py_compile tools/ci/check_experiment_registry.py
python3 tools/agent_tools/check_solid_evidence.py --root . --evidence <OOP-JSON-report> tools/ci/check_experiment_registry.py tests/tools/test_run_managed_experiment.py
```

Observed focused validation: 30 tests passed; baseline OOP readability reported
zero findings; the parent template registry checker exited 0; pycompile passed;
SOLID evidence passed; and the dependency-header format and diff checks passed.
