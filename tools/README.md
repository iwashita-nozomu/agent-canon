# AgentCanon tools

<!--
@dependency-start
contract tool
responsibility Documents the standalone AgentCanon tool surface and execution-plane boundary.
upstream design ../documents/runtime/bootstrap-runtime.md shared bootstrap user contract
upstream design ../documents/runtime/runtime-log-archive.md external archive publication contract
upstream implementation agent_tools/bootstrap_runtime.py lifecycle implementation
upstream implementation agent_tools/tool_dispatch.py typed dispatch implementation
upstream implementation agent_tools/runtime_artifacts.py external artifact boundary
upstream design catalog.yaml public tool registry
@dependency-end
-->

`tools/` is owned by the standalone AgentCanon source repository. It contains
the Python tools, Rust/CLI wrappers, host adapters, checkers, and tool catalog
used by AgentCanon. A parent repository does not vendor this directory, copy it
into its own `tools/`, or create a symlink view. Parent automation and project
tests stay parent-owned.

## Execution planes

Use the top-level [`bootstrap.sh`](../bootstrap.sh) for the shared AgentCanon
runtime. It requires an authorized control root. The default runtime is the
bootstrap-owned ignored `.runtime/` under the install checkout:

```bash
./bootstrap.sh --control-parent-root <authorized-parent-root> <operation>
```

| Plane | Owner | Examples | Side-effect rule |
| --- | --- | --- | --- |
| `tool-container` | shared AgentCanon runtime | Rust CLI, Python tools, LSP | one non-root container; source read-only; external artifacts |
| `host-adapter` | bootstrap/host | Docker, Git/archive, Codex launch | typed allowlist; credentials stay host-side |
| `project-container` | parent project | product build, test runner, GPU | project-owned Docker/test contract |
| `source` | AgentCanon checkout | policy/docs/design edits | explicit mutation only; no runtime output |

For a project-owned GPU workload, keep GPU admission and the child command in
the single Docker adapter.  The caller supplies the image and command only;
the adapter selects its internal CDI or `--gpus all` injection route from the
daemon's observed capabilities:

```bash
run_gpu_container.sh --image <image> -- <argv...>
```

This is a project execution route, not a requirement of the AgentCanon tool
container.  The wrapper receives the admitted, full-UUID environment and does
not expose a public runtime-mode or GPU-selection argument.

The AgentCanon runtime uses one shared image and at most one resident container
per authorized control root. It does not create project/task-specific images,
containers, virtualenvs, Cargo toolchains, or volumes. Docker daemon rootful vs
rootless mode is irrelevant to the route; the container process is always
non-root. The container has no Docker socket, host HOME, global Codex state,
GitHub token, SSH agent, or general network.

## Public commands

Rust first-class commands retain their existing public shape:

```bash
agent-canon docs check ...
agent-canon semantic-index ...
agent-canon structured-analysis ...
```

Python tools are not made into flat global executables. A public catalog entry
is callable through the namespaced route only when its schema-v2 parity fixture
is verified:

```bash
./bootstrap.sh --control-parent-root <root> --runtime-root <runtime> \
  target add --root <project-root> --mode read-only
./bootstrap.sh --control-parent-root <root> --runtime-root <runtime> \
  tool run <verified-catalog-id> -- <args...>
```

Parity covers argv, cwd, stdin/stdout/stderr, exit and signal behavior, and
written paths. The dispatcher rejects unknown IDs, shell command strings, and
unverified entries. It does not infer that every internal Python file is a
public command.

Until parity is verified, keep the existing exact command and use the typed
legacy execution route:

```bash
./bootstrap.sh --control-parent-root <root> --runtime-root <runtime> \
  exec --root <registered-project> -- <existing-command> <args...>
```

A parity failure leaves the legacy route authoritative; no compatibility alias
silently changes the command's execution plane or side effects.

## Catalog and ownership

`tools/catalog.yaml` is the machine-readable catalog. It owns command identity,
audience, placement, current legacy route, and schema-v2 dispatch metadata.
`tools/fixtures/tool_dispatch/public-command-parity.json` records the observed
parity evidence. Use the existing catalog/checker owners rather than adding a
second README registry.

| Need | Owner command |
| --- | --- |
| catalog shape and docs wiring | `python3 tools/agent_tools/tool_catalog.py` |
| tool/workflow drift | `python3 tools/agent_tools/tool_drift.py` |
| responsibility scope | `python3 tools/agent_tools/responsibility_scope.py --root .` |
| runtime artifact boundary | `python3 tools/agent_tools/generated_artifact_guard.py` |
| archive state | `python3 tools/agent_tools/runtime_log_archive_git.py status` |
| eval archive structure | `python3 tools/agent_tools/eval_accumulation_check.py` |
| path-risk/profile selection | `python3 tools/agent_tools/classify_path_risk.py` |
| Markdown/links/Mermaid | `tools/bin/agent-canon docs check` |
| semantic repository search | `tools/bin/agent-canon semantic-index ...` |

## Artifact and archive route

Tool output, cache, Cargo target, SQLite, reports, hook events, dashboards,
evals, and temporary files go to task-specific directories below the external
runtime root. Do not rely on source-local `reports/`, `.agent-canon/`,
`target/`, `$HOME/.cache`, or `$HOME/.local` defaults.

Existing eval producers remain the producer owner. `eval collect` creates a
versioned collection in the runtime spool; `eval sync` uses the typed host Git
adapter and `runtime_log_archive_git.py` to publish to the separate
[`agent-canon-log`](https://github.com/iwashita-nozomu/agent-canon-log)
repository. Archive branch/retention belong to that repository. Publication is
successful only after remote ref/tree/blob readback; failure retains spool and
receipt for retry. See [Runtime Log Archive](../documents/runtime/runtime-log-archive.md).

The prompt-eval audit remains a first-class validation signal. A healthy audit
reports `EVAL_AUDIT_STATUS=pass`, `EVAL_GROWTH_CANDIDATES=0`, and confirms
`duplicate explicit targets` remain zero. Maintainers may run a producer with `--accumulate`; the
receipt exposes `EVAL_RUN_ID` and `EVAL_ACCUMULATED_REPORT`, and skill reports
use `<eval_run_id>-<status>-<skill-slug>.md`. These files live in the external
archive checkout, never in the source tree.

`generate_agent_improvement_guide.py` reads the mounted runtime hook archive
and repository-qualified GitHub Issue URLs from run-local private packets as read-only evidence. Its generated guide is another
external runtime artifact and is not permission to change source, Issue, or
archive state.

## Host adapters and credentials

Bootstrap host operations are typed and allowlisted: Docker image/container
lifecycle, target Git identity, archive clone/fetch/commit/push/readback, and
the explicitly scoped embedding request. Issue/PR publication is owned by the
GitHub workflow and is not an arbitrary bootstrap shell operation. Unknown
options, shell fragments, arbitrary remotes, and arbitrary URLs are rejected.

Credential mode may be `none`, `ssh-agent`, `git-credential-helper`, or a
named provider secret. Receipts keep mode, provider/remote digest, byte counts,
and exit status only; they never contain secret values, paths, headers, or raw
payloads. Network stays on the host adapter; the resident tool container is
`network=none`.

## Update route

For a shared change, read
[AgentCanon Update Skill](../agents/skills/agent-canon-update.md), edit the
AgentCanon source or a qualified ignored development clone, run focused tests,
open the AgentCanon PR, and read back merged `main`. Parent repositories are
updated only after the merge. Do not restore a vendor/submodule or root
projection route.

Issue ownership is explicit: [#841](https://github.com/iwashita-nozomu/agent-canon/issues/841)
owns local bootstrap, shared runtime, side-effect isolation, skills, eval, and
archive lifecycle. [#821](https://github.com/iwashita-nozomu/agent-canon/issues/821)
owns prebuilt artifact build/distribution.

## Validation

For tool/runtime documentation or code changes:

```bash
git diff --check
python3 -m pytest -q tests/agent_tools/test_runtime_artifacts.py \
  tests/agent_tools/test_tool_dispatch.py
```

For bootstrap/container changes, add:

```bash
python3 -m pytest -q tests/bootstrap \
  tests/tools/test_bootstrap_container_contract.py
```

Select broader checks from
[Runtime Profiles And Check Matrix](../documents/runtime/runtime-profiles-and-check-matrix.md).
Each failure report must identify whether the failing code is AgentCanon tool
runtime, host adapter/archive, or project execution code.
