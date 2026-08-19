# issue-finding-report

<!--
@dependency-start
contract skill
responsibility Documents issue-finding-report for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design agent-log-analysis.md structured runtime evidence analysis workflow
upstream design subagent-bootstrap.md multi-agent partition and handoff workflow
upstream design ../../issues/README.md durable AgentCanon operational issue schema
upstream implementation ../../tools/agent_tools/generate_agent_runtime_dashboard.py emits structured log evidence
upstream implementation ../../tools/agent_tools/runtime_log_archive_git.py resolves accumulated log archive state
upstream implementation ../../tools/agent_tools/issue_sync.py validates local issue records and GitHub mirrors
downstream design ../../.agents/skills/issue-finding-report/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

- Purpose: turn accumulated runtime, prompt, hook, skill, tool, workflow, and
  eval evidence into durable AgentCanon operational issue candidates.
- Section path: Purpose and Use When set the route; Inputs and Abstract Cause
  Taxonomy define evidence and grouping; Multi-Agent Partition, Confirmed
  Occurrence Location Contract, Issue Candidate Contract, Output Packet, and
  Validation define production and checks.
- Use when: repeated agent behavior, routing misses, workflow evidence, or log
  dashboard signals should become issue-backed repair work.
- Boundary: compact analysis comes from `agent-log-analysis`; this skill writes
  issue candidates or finding packets without replacing PR processing or tool
  finding ownership.

## Purpose

Convert accumulated prompt, run-bundle, hook, skill, tool, workflow, and eval
evidence into durable AgentCanon operational issues. The shared finding
normalization/grouping owner groups repeated signals by owner, root cause, and
fix; one resulting group becomes one issue candidate with structured evidence.

This skill is the issue-production follow-up to `agent-log-analysis`. It
receives structured dashboard artifacts and produces issue records or a finding
packet while leaving runtime analysis, tool finding packets, and PR processing
with their owner skills.

## Use When

- User asks to turn logs, prompt history, run bundles, or agent reports into
  skill issues.
- A structured dashboard exposes repeated skill, workflow, tool, hook, wave, eval,
  or token evidence that should survive the current run.
- An explicit repo-wide sweep is requested. Otherwise use changed-surface,
  user-request, or owner-bounded scope.
- The task asks why agent behavior keeps recurring and wants issue-backed
  repair work.

## Inputs

Use structured artifacts as the normal input:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
python3 tools/agent_tools/generate_agent_runtime_dashboard.py \
  --root . \
  --compact-out reports/agent-runtime-dashboard/agent-log-analysis-compact.md \
  --api-out reports/agent-runtime-dashboard/agent-log-analysis-api.json
```

Required structured fields:

- `unknown_event_count`
- `status_by_hook_family`
- `failure_by_hook_family`
- `skip_by_hook_family`
- `namespace_debt_by_hook_family`
- `oop_applicability`

Use run-bundle artifacts, prompt excerpts, and dashboard drilldown sections as
bounded evidence. Raw JSONL or full transcripts are schema debugging,
corruption audit, or dashboard-named drilldown inputs.

## Abstract Cause Taxonomy

Assign each cluster to one primary cause and optional secondary causes:

| cause | evidence signal | likely route target |
| --- | --- | --- |
| `archive_hygiene` | dirty archive, foreign repo-key tree, unreadable result, malformed accumulation | `documents/runtime/runtime-log-archive.md`, `runtime_log_archive_git.py`, `result-artifact-writeout` |
| `workflow_attribution` | missing workflow labels, unknown events, namespace debt, status mapping gaps | hook logging owner, `agent-learning`, dashboard owner |
| `selection_gap` | skill, workflow, or tool candidate selected late, missed, or routed to the wrong surface | affected skill, `agents/skills/catalog.yaml`, `task-routing` |
| `wave_execution` | planned wave lacks actual row, blocked/skipped wave lacks cause, same-role instance drift | `subagent-bootstrap`, `CODEX_SUBAGENTS.md`, run-bundle templates |
| `eval_gap` | missing, stale, or failing eval family; proof/eval coverage gap | `agent-eval-accumulation`, eval producer/checker owner |
| `token_coverage` | token comparisons missing, moving average missing, prompt volume ungrounded | token logging owner, `agent-learning` |
| `reference_capture` | external URL observed without registered source material | reference capture owner, `references/` policy |
| `prompt_or_config_drift` | behavior follows prompt, config, or role-policy mismatch | affected prompt/config surface, `prompt_config_reviewer` |
| `structure_boundary` | evidence points to wrong repo/view/skill/tool boundary | `structure-refactor`, responsibility-scope owner |

Create one issue per abstract recurring cause cluster, with structured evidence
counts and route target.

## Grouping And Dispatch Boundary

Use `tools/agent_tools/issue_sync.py` as the shared normalization/grouping
owner for tool and issue findings. A group is keyed by `(owner, root_cause,
fix)` and remains one issue candidate; do not automatically partition a group
into multiple agents. Warnings add a closeout obligation only when they are
actionable or blocking.

## Multi-Agent Partition

Use a parent-created `Issue Finding Packet` before spawning. Each packet fixes:

```text
cause: <abstract-cause>
evidence_cells: <structured dashboard headings or API JSON paths>
instance_partition: <repo_key|hook_family|skill_name|workflow_name|tool_name|issue_id|path_scope>
candidate_issue_slug: <lowercase-ascii-slug>
affected_surfaces: <candidate edit or verification paths>
occurrence_locations: <confirmed location records from the contract below>
duplicate_search: <rg query>
expected_output: <issue_candidate|defer_with_reason|merge_with_existing>
```

`affected_surfaces` is planning scope. It may include files that need edits or
verification, but it is not evidence that the defect occurred there.
`occurrence_locations` names the observed sites and cannot be inferred from a
repository name, directory, or broad affected surface.

Recommended review partition:

- `prompt_config_reviewer`: `selection_gap`, `prompt_or_config_drift`
- `docs_workflow_steward`: skill/workflow wording and issue text quality
- `project_reviewer`: `archive_hygiene`, `wave_execution`, `structure_boundary`
- `artifact_reviewer`: raw/structured artifact sufficiency and evidence paths

When several independent clusters exist, parent-owned routing may dispatch
distinct groups. A single group is never split solely to increase fan-out.
Each optional instance receives only its packet, structured artifact paths,
allowed issue paths, candidate affected surfaces, validation route, and return
schema; the parent consumes the shared grouping result before writing files.

## Confirmed Occurrence Location Contract

Before an issue candidate is complete, record at least one confirmed occurrence
location tied to the source or artifact snapshot where the behavior was
observed. Use one record per distinct site:

```text
repository: <owner/name or local repository identity>
snapshot: <commit SHA or immutable artifact/run identity>
path: <repo-relative source path or artifact path>
locator_type: <symbol|config-key|heading|data-field|workflow-step|command-phase|absence-query>
locator: <function/class/type, table.key, heading/anchor, JSON/TOML field, job/step, or bounded query>
lines: <Lx-Ly|unavailable:reason>
observation: <behavior or conflicting contract observed at this locator>
evidence: <command and output/artifact reference that confirms the observation>
```

Apply these rules:

- A repository name, directory, subsystem, or `affected_surfaces` value alone is
  not a confirmed occurrence location.
- `path` and a stable `locator` are required. Add the line or range from the
  recorded snapshot when available; a line number without a stable locator is
  insufficient because lines move.
- For a cross-surface disconnect, list every endpoint needed to demonstrate the
  broken invariant, such as both producer and consumer, rather than naming only
  the subsystem that contains them.
- For an absence defect, do not invent a source location. Record the bounded
  search universe, immutable snapshot, exact query, and zero-match or missing
  field result with `locator_type: absence-query`.
- For generated or runtime evidence, name both the producer surface when known
  and the immutable artifact/run field where the bad state was observed.
- When no occurrence location can yet be confirmed, return
  `defer_with_reason`, keep the issue in investigation with the
  `need verification` label, and do not present a root cause or required fix as
  confirmed.

## Issue Candidate Contract

Before writing a new issue:

1. Search existing durable surfaces.

   ```bash
   git grep -n "<cause keywords>" -- issues memory documents/notes/failures documents agents
   ```

1. Expand candidate affected surfaces through dependency review.

   ```bash
   bash tools/agent_tools/run_repo_dependency_review.sh \
     --report-dir reports/agents/<run-id>/dependency-review/<slug> \
     --search-hits-file reports/agents/<run-id>/<slug>-search-hits.txt
   ```

1. Confirm the occurrence locations using the contract above. Keep the
   observation location separate from the proposed edit scope.
1. Write `issues/open/AC-YYYYMMDD-short-slug.md` after the duplicate search
   shows that the cause cluster needs a new durable record.
1. Populate the minimum issue form from `issues/README.md`: `problem`,
   `evidence`, and `done`, plus identity fields. Add a structured
   `occurrence_locations` block even when no extended planning fields are
   needed.
1. Use `github_issue: pending` or `github_issue: not-created` only for a mirror
   being prepared in the same branch or explicit follow-up. These markers are
   unresolved until `--apply` replaces them with one real GitHub Issue URL;
   `--github-check` must report them and `--require-github-link` must fail.

Issue body sections:

- `## Finding`: observed recurring behavior and structured evidence counts
- `## Occurrence Locations`: one structured record per confirmed observation
  site, including snapshot, path, stable locator, observation, and evidence
- `## Abstract Cause`: why the cluster belongs to the selected cause
- `## Required Fix`: skill, workflow, tool, or logging repair expected
- `## Evidence`: commands and artifacts tied to the occurrence records,
  dependency review, or existing issue links

Do not call an issue candidate complete when `## Occurrence Locations` is
missing, contains only broad affected surfaces, or lacks evidence tied to the
recorded snapshot.

## Output Packet

Write a run-local issue finding packet when the task asks for analysis, when
multiple candidates exist, or before spawning subagents:

```text
issue_finding_scope: <dashboard|run-bundle|archive|mixed>
structured_evidence: <paths>
candidate_count: <n>
new_issue_count: <n>
merged_existing_count: <n>
deferred_count: <n>
confirmed_occurrence_location_count: <n>
issue_paths: <paths>
subagent_partitions: <role_id:instance_id:agent_type:packet>
validation: <commands>
```

When every candidate merges into an existing issue or stays below durable issue
threshold, record the existing issue path or the evidence classification.

## Validation

Run the local issue schema and skill wiring checks after creating or updating
issues or this skill:

```bash
python3 tools/agent_tools/issue_sync.py --root .
python3 tools/agent_tools/check_skill_frontmatter.py --root .
python3 tools/agent_tools/skill_tool_commands.py check
python3 tools/agent_tools/check_dependency_headers.py --changed
bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing
bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header
```
