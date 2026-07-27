<!--
@dependency-start
contract issue
responsibility Tracks OOP readability refactor work for the experiment registry checker.
upstream implementation ../../tools/ci/check_experiment_registry.py validates experiment registry contracts.
upstream implementation ../../tools/oop/python/readability.py reports OOP readability findings.
upstream design ../../documents/object-oriented-design.md defines OOP readability policy.
@dependency-end
-->

# Experiment Registry Checker OOP Readability

date: 2026-06-25
issue_id: AC-20260625-experiment-registry-oop-readability
status: open
severity: follow-up
owner: AgentCanon
source: OOP readability validation during managed experiment reproducibility log work
evidence: `python3 tools/oop/python/readability.py --root . --min-score 95 tools/experiments/run_managed_experiment.py tools/ci/check_experiment_registry.py tests/tools/test_run_managed_experiment.py`
affected_surfaces: tools/ci/check_experiment_registry.py, tests/tools/test_run_managed_experiment.py
edit_scope: tools/ci/check_experiment_registry.py validation helper extraction and topic orchestration split
required_action: Split registry value extraction, finding construction, and topic-level validation orchestration while preserving registry behavior.
close_condition: OOP readability no longer reports `require_string`, `require_registered_command`, `maybe_string_list`, or `validate_topic` findings for `tools/ci/check_experiment_registry.py`, and experiment registry tests pass.

## Finding

`python3 tools/oop/python/readability.py --root . --min-score 95 tools/experiments/run_managed_experiment.py tools/ci/check_experiment_registry.py tests/tools/test_run_managed_experiment.py`
still reports existing findings in `tools/ci/check_experiment_registry.py`.

Current findings:

- `require_string`: mixed return/effect boundary
- `require_registered_command`: mixed return/effect boundary
- `maybe_string_list`: mixed return/effect boundary
- `validate_topic`: cognitive complexity
- `validate_topic`: function length

## Required Repair

Refactor `check_experiment_registry.py` by separating value extraction, finding
construction, and topic-level orchestration. Keep the registry contract behavior
and current test coverage intact.

## Validation

```bash
python3 -m pytest tests/tools/test_run_managed_experiment.py -q
python3 tools/oop/python/readability.py --root . --min-score 95 tools/ci/check_experiment_registry.py tests/tools/test_run_managed_experiment.py
python3 tools/ci/check_experiment_registry.py --repo-root .
```
