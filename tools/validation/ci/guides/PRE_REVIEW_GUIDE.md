# pre_review.sh Guide
<!--
@dependency-start
contract tool
responsibility Documents the verifier pre-review entrypoint for this repository.
upstream design ../../../README.md shared automation index
upstream implementation ../runners/pre_review.sh verifier entrypoint
upstream implementation ../checks/run_python_quality_checks.sh shared Python quality gate
downstream implementation ../../semantic/code/pydocstyle_review.py explicit AgentCanon Docstring review
@dependency-end
-->

## Reader Map

- Purpose: explain the `tools/validation/ci/runners/pre_review.sh` verifier entrypoint.
- Use When: maintaining GitHub agent-coordination verifier jobs or running the
  same Python quality gate with optional role write-scope evidence.
- Section path: Entry Contract shows the owner boundary; Commands gives local
  usage; Report Evidence explains `AGENT_REPORT_DIR` and role write-scope
  output.
- Boundary: Python quality check behavior is owned by
  `tools/validation/ci/checks/run_python_quality_checks.sh`; this guide does not duplicate its
  command list.

## Entry Contract

`tools/validation/ci/runners/pre_review.sh` is a thin verifier wrapper. It calls
`tools/validation/ci/checks/run_python_quality_checks.sh` and, when requested by the workflow,
records `verification.txt` plus role write-scope evidence.

It is not a separate PR-quality policy surface. Update
`tools/validation/ci/checks/run_python_quality_checks.sh` when the shared Python gate changes.
Update this guide only when verifier report or role-scope behavior changes.

## Commands

Run the verifier gate:

```bash
bash tools/validation/ci/runners/pre_review.sh
```

Run the same gate with ruff skipped:

```bash
bash tools/validation/ci/runners/pre_review.sh --quick
```

Run the shared Python gate directly when report/write-scope evidence is not
needed:

```bash
bash tools/validation/ci/checks/run_python_quality_checks.sh
```

The PR quick chain intentionally runs pytest and pyright while skipping Ruff;
the explicit full Python quality command adds Ruff. Neither shared path invokes
pydocstyle.

For `check_agent_canon_pr.sh`, standalone and derived AgentCanon gates run
shared AgentCanon surfaces only. A derived parent emits
`AGENT_CANON_PR_PROJECT_QUALITY=delegated` with owner `parent_ci`; its workflow
must expose that owner marker and canonical `make ci` command, regardless of
job name. Project tests, type checks, and lint remain in that selected parent
CI route. Standalone AgentCanon keeps its existing `static-gates` shared owner
and adds no repository-wide project-quality job. The shared gate does not
invoke `run_all_checks.sh`.

Explicit Docstring review for selected Python targets:

    tools/bin/agent-canon pydocstyle-review --target <repo-relative.py>

This command resolves the canonical AgentCanon source root and applies its D213
configuration. Parent-specific Docstring review remains a separate parent-owner
command and does not substitute its authority. Missing pydocstyle or reported
diagnostics fail this explicit review only; the shared PR correctness gate is
unaffected.

## Report Evidence

`agent-coordination.yml` sets these variables for verifier jobs:

```bash
export AGENT_REPORT_DIR="<run-bundle-report-dir>"
export AGENT_ROLE="verifier"
export AGENT_ENFORCE_WRITE_SCOPE="1"
bash tools/validation/ci/runners/pre_review.sh
```

When `AGENT_REPORT_DIR` is set, `pre_review.sh` writes
`verification.txt` with start/end timestamps, the workspace root,
`python_quality=pass|fail`, and `write_scope=pass|fail` when role enforcement
is active.

## Validation

After editing this wrapper or the shared Python gate, run:

```bash
bash -n tools/validation/ci/runners/pre_review.sh
bash -n tools/validation/ci/checks/run_python_quality_checks.sh
python3 -m pytest tests/tools/test_run_all_checks_script.py -q
```
