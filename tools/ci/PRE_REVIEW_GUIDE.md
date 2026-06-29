# pre_review.sh Guide
<!--
@dependency-start
contract tool
responsibility Documents the verifier pre-review entrypoint for this repository.
upstream design ../README.md shared automation index
upstream implementation ./pre_review.sh verifier entrypoint
upstream implementation ./run_python_quality_checks.sh shared Python quality gate
@dependency-end
-->

## Reader Map

- Purpose: explain the `tools/ci/pre_review.sh` verifier entrypoint.
- Use When: maintaining GitHub agent-coordination verifier jobs or running the
  same Python quality gate with optional role write-scope evidence.
- Section path: Entry Contract shows the owner boundary; Commands gives local
  usage; Report Evidence explains `AGENT_REPORT_DIR` and role write-scope
  output.
- Boundary: Python quality check behavior is owned by
  `tools/ci/run_python_quality_checks.sh`; this guide does not duplicate its
  command list.

## Entry Contract

`tools/ci/pre_review.sh` is a thin verifier wrapper. It calls
`tools/ci/run_python_quality_checks.sh` and, when requested by the workflow,
records `verification.txt` plus role write-scope evidence.

It is not a separate PR-quality policy surface. Update
`tools/ci/run_python_quality_checks.sh` when the shared Python gate changes.
Update this guide only when verifier report or role-scope behavior changes.

## Commands

Run the verifier gate:

```bash
bash tools/ci/pre_review.sh
```

Run the same gate with ruff skipped:

```bash
bash tools/ci/pre_review.sh --quick
```

Run the shared Python gate directly when report/write-scope evidence is not
needed:

```bash
bash tools/ci/run_python_quality_checks.sh
```

## Report Evidence

`agent-coordination.yml` sets these variables for verifier jobs:

```bash
export AGENT_REPORT_DIR="<run-bundle-report-dir>"
export AGENT_ROLE="verifier"
export AGENT_ENFORCE_WRITE_SCOPE="1"
bash tools/ci/pre_review.sh
```

When `AGENT_REPORT_DIR` is set, `pre_review.sh` writes
`verification.txt` with start/end timestamps, the workspace root,
`python_quality=pass|fail`, and `write_scope=pass|fail` when role enforcement
is active.

## Validation

After editing this wrapper or the shared Python gate, run:

```bash
bash -n tools/ci/pre_review.sh
bash -n tools/ci/run_python_quality_checks.sh
python3 -m pytest vendor/agent-canon/tests/tools/test_run_all_checks_script.py -q
```
