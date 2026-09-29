<!--
@dependency-start
contract reference
responsibility Documents path-risk classifier usage.
upstream implementation ../../tools/validation/semantic/path/classify_path_risk.py classifies changed paths into runtime profiles.
upstream design ../runtime/runtime-profiles-and-check-matrix.md defines profile-based validation routing.
downstream implementation ../../tests/agent_tools/test_classify_path_risk.py tests representative profiles.
@dependency-end
-->

# classify_path_risk.py

Use this tool to turn a changed-path list into an active runtime profile and
targeted validation route.

```bash
git diff --name-only origin/main...HEAD > "${AGENT_CANON_RUNTIME_ROOT:?}/changed-paths.txt"
python3 tools/validation/semantic/path/classify_path_risk.py \
  --paths-file "${AGENT_CANON_RUNTIME_ROOT:?}/changed-paths.txt" \
  --format text
```

The classifier is a direct CLI/test-owned surface. It does not require a
separate manual workflow wrapper.

## Standalone CI ownership

[Static Gates](../../.github/workflows/agent-canon-static-gates.yml) runs on pull
requests and manual dispatch. This classifier alone selects execution units;
[the unit runner](../../tools/validation/ci/runners/run_standalone_static_gate_unit.sh)
owns their commands. A selector failure fails the final `static-gates` job.

| Changed surface | Unit |
| --- | --- |
| Markdown or documentation-check inputs | `docs` |
| Python, catalogs, or otherwise unclassified source | `contracts` |
| Rust crate | `rust` |
| Evaluation producer or definitions | `eval` |
| GitHub automation or container lifecycle | `workflow-container` |
| Selector/runner/workflow boundary, or manual dispatch | All units |

Mixed changes select the union, including unclassified files. Documentation
changes do not by themselves select Rust tests, evaluations, or container
regressions. The `docs` unit calls the existing source-built
`agent-canon docs check` on changed Markdown paths. Deleted documents or changes to the docs
checker/inventory select its normal repository-wide document check so incoming
links are not silently ignored. Other text formats are not claimed as Markdown
validation.

The PR diff is taken between the event's base commit and the checked-out merge
candidate. Bootstrap runs from a disposable local `main` pointing to that same
candidate, following the existing improvement-guide workflow's source route.
This prevents bootstrap's normal main synchronization from replacing the PR
code with remote main. The registered target stays read-only; the installation,
cache, and reports live outside it. The runner uses the mounted candidate tools
and the already provisioned toolchain rather than creating empty Cargo/Rustup
homes or reading obsolete image source paths.

Selected units run independently; one failure does not prevent later selected
units from producing evidence, and any failure fails the aggregate. Contract
regressions use pytest, which collects both unittest classes and pytest
functions. Merely importing a pytest module through unittest is not evidence
that its tests ran. Temporary installation and local source transport are
removed after the job. No publishing credential or repository write permission
is needed.

The shared image provisions `python3-pytest` for its system Python through the
[existing dependency manifest](../../bootstrap/container/image/dependencies.toml);
a pipx-isolated executable does not supply an importable system Python module.
The same manifest includes `rustfmt` and `clippy`, consumed by the existing
Rust unit; their commands must not depend on undeclared toolchain components.
