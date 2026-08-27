# issue-finding-report

<!--
@dependency-start
contract skill
responsibility Documents issue-finding-report for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design agent-log-analysis.md structured runtime evidence analysis workflow
upstream design dependency-analysis.md cause-hypothesis, mechanism, impact, and validation evidence workflow
upstream design responsibility-cleanup.md complete owning responsibility-unit and boundary workflow
upstream design subagent-bootstrap.md multi-agent partition and handoff workflow
upstream design pr-processing.md repository-qualified Issue identity and publication boundary
upstream design ../../documents/runtime/private-feedback-knowledge.md private GitHub Issue packet route
upstream implementation ../../tools/agent_tools/generate_agent_runtime_dashboard.py emits structured log evidence
upstream implementation ../../tools/agent_tools/runtime_log_archive_git.py resolves accumulated log archive state
upstream implementation ../../tools/agent_tools/issue_sync.py resolves GitHub Issues and private packets
downstream design ../../.codex/personal/skills/issue-finding-report/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

- Purpose: turn accumulated evidence or a direct AgentCanon-owned defect into a
  durable issue, and re-cut an existing related Issue set when its current
  boundaries do not match the owning responsibilities.
- Section path: Purpose and Use When set the route; Cause Investigation and
  Issue Responsibility Unit define the epistemic and boundary contracts;
  Related Issue Set Intake, Reorganization, Clause Conservation, and Mutation
  Order define existing-Issue repair; later sections retain evidence,
  occurrence-location, candidate, output, and validation contracts.
- Use when: repeated agent behavior, routing misses, workflow evidence, a
  current consumer task, or an existing open/closed Issue set should become
  cause-investigated and responsibility-bounded repair work.
- Boundary: `agent-log-analysis` owns compact observation, `dependency-analysis`
  owns causal and mechanism evidence, `responsibility-cleanup` owns complete
  responsibility units, and `pr-processing` owns repository-qualified GitHub
  publication. This skill composes those facts into Issue boundaries and
  relation receipts; it does not replace their owner decisions.

## Purpose

Convert accumulated prompt, run-bundle, hook, skill, tool, workflow, and eval
evidence into durable AgentCanon operational issues. The same entrypoint also
repairs an existing Issue set when simple duplicate avoidance would leave one
decision distributed across conflicting owners, states, or completion criteria.

The shared finding normalization owner may initially group repeated signals by
`(owner, root_cause, fix)`. That tuple is a search and candidate-grouping key,
not proof that the recorded root cause is true and not a final Issue boundary.
Before publication, this skill investigates plausible causes and evaluates the
complete owning responsibility unit.

This skill is the issue-production follow-up to `agent-log-analysis`. It accepts
structured evidence and returns one of:

- a new durable Issue candidate,
- a merge into an already cohesive Issue,
- a responsibility reorganization of existing Issues, or
- an investigation/defer result when repository identity, mechanism, or
  clause destination is unavailable to the host publisher.

It also owns direct upstream escalation when a current repository task supports
that the failing invariant belongs to AgentCanon rather than the consumer
repository. This direct route does not require repeated evidence or a dashboard.

## Use When

- User asks to turn logs, prompt history, run bundles, or agent reports into
  skill issues.
- User asks to split, consolidate, re-parent, reopen, supersede, or otherwise
  re-cut Issues by responsibility rather than merely avoid duplicate titles.
- A structured dashboard exposes repeated skill, workflow, tool, hook, wave,
  eval, or token evidence that should survive the current run.
- Open and closed related Issues contain mixed decision, implementation,
  validation, evidence, or cross-repository policy responsibilities.
- Unique acceptance clauses are distributed across Issues and may be lost by a
  mechanical duplicate close.
- The task asks why behavior keeps recurring and wants issue-backed repair work.
- A current repository task supports that a failing contract, workflow, tool,
  hook, runtime surface, or policy is owned by AgentCanon rather than by the
  consumer repository.
- An explicit repository-wide sweep is requested. Otherwise use changed-surface,
  user-request, or owner-bounded scope.

Do not activate this skill only because two Issues share words. Similar wording
is evidence for retrieval, not evidence for common responsibility.

## Direct AgentCanon Defect Escalation

Let `owner(f)` be the canonical owner of the failing invariant `f`. Activate
this route only after bounded evidence supports `owner(f) = AgentCanon`. A
nearby vendored path, generated copy, or consumer observation alone does not
establish ownership.

Before changing the consumer repository, freeze this packet:

```text
consumer_task: <owner/repository#number, qualified PR, or task reference>
agentcanon_snapshot: <vendored pin, source commit, or immutable runtime identity>
failure_condition: <minimal precondition plus command/action that reproduces the failure>
expected_behavior: <owner contract or invariant>
actual_behavior: <observed result>
occurrence_locations: <confirmed AgentCanon and cross-surface endpoint records>
cause_hypotheses: <supported alternatives and confidence>
related_issue_set: <open/closed repository-qualified Issue identities>
consumer_scope_disposition: <blocked|deferred|independent-work-remains>
upstream_issue: <owner/repository#number for the existing or newly created durable AgentCanon Issue>
```

Apply these rules:

1. Consume `pr-processing`'s repository-qualified Issue identity. Keep consumer
   and upstream repositories explicit in every packet, progress update,
   publication comment, relation, and closeout readback.
1. Identify the minimal failure condition and exact AgentCanon snapshot or pin
   before proposing a fix.
1. Use the Confirmed Occurrence Location Contract. For a cross-repository
   disconnect, record the consumer observation endpoint and every AgentCanon
   endpoint needed to demonstrate the broken invariant. Keep proposed edit
   paths separate from observed locations.
1. Search existing AgentCanon durable and GitHub Issues, including closed
   Issues, by owner, decision, mechanism, cause hypothesis, fix, linked PR, and
   occurrence location. Do not search by title keywords alone.
1. Preserve the current consumer task's requested scope and completion criteria.
   Record the AgentCanon Issue only as a dependency, blocker, or policy sibling.
   Continue only consumer work that is independent of the defect.
1. Do not resolve or close the AgentCanon finding with a consumer-local copy,
   symlink, monkeypatch, source override, fallback, bypass, validation
   weakening, exception config, or other change whose purpose is to mask the
   upstream defect.
1. If AgentCanon ownership, cause, or a confirmed occurrence location remains
   unresolved, keep the finding as an investigation with `need verification`.
   Do not present a root cause or required fix as confirmed.

The upstream repair is a separate AgentCanon responsibility. Do not add it to
the consumer Issue's done conditions or expand the active consumer write scope
to implement it.

## Inputs

Use structured artifacts as the normal evidence input:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
./bootstrap.sh --control-parent-root <control-parent-root> \
  --runtime-root <runtime-root> \
  tool run --root <registered-source-root> generate-agent-runtime-dashboard -- \
  --root . \
  --compact-out reports/agent-runtime-dashboard/agent-log-analysis-compact.md \
  --api-out reports/agent-runtime-dashboard/agent-log-analysis-api.json
```

Dashboard generation is a shared tool-container invocation. Its relative
report paths resolve under the external runtime root, not the source checkout.

Required dashboard fields when that producer is used:

- `unknown_event_count`
- `status_by_hook_family`
- `failure_by_hook_family`
- `skip_by_hook_family`
- `namespace_debt_by_hook_family`
- `oop_applicability`

Use run-bundle artifacts, prompt excerpts, source snapshots, linked PRs/commits,
and dashboard drilldown sections as bounded evidence. Raw JSONL or full
transcripts are schema-debugging, corruption-audit, or explicitly named
drilldown inputs rather than the default review surface.

## Abstract Cause Taxonomy

Assign each observation cluster one primary cause category and optional
secondary categories. A category narrows investigation; it is not a causal
assertion.

| cause category | evidence signal | likely route target |
| --- | --- | --- |
| `archive_hygiene` | dirty archive, foreign repo-key tree, unreadable result, malformed accumulation | `documents/runtime/runtime-log-archive.md`, `runtime_log_archive_git.py`, `result-artifact-writeout` |
| `workflow_attribution` | missing workflow labels, unknown events, namespace debt, status mapping gaps | hook logging owner, `agent-learning`, dashboard owner |
| `selection_gap` | skill, workflow, or tool candidate selected late, missed, or routed to the wrong surface | affected skill, `agents/skills/catalog.yaml`, `task-routing` |
| `wave_execution` | planned wave lacks actual row, blocked/skipped wave lacks cause, same-role instance drift | `subagent-bootstrap`, `CODEX_SUBAGENTS.md`, run-bundle templates |
| `eval_gap` | missing, stale, or failing eval family; proof/eval coverage gap | `agent-eval-accumulation`, eval producer/checker owner |
| `token_coverage` | token comparisons missing, moving average missing, prompt volume ungrounded | token logging owner, `agent-learning` |
| `reference_capture` | external URL observed without registered source material | reference capture owner, `references/` policy |
| `prompt_or_config_drift` | behavior is consistent with a prompt, config, or role-policy mismatch | affected prompt/config surface, `prompt_config_reviewer` |
| `structure_boundary` | evidence points to the wrong repository, view, skill, tool, or owner boundary | `structure-refactor`, `responsibility-cleanup` |

## Cause Investigation Contract

An Issue must not stop at naming the visible symptom. Before choosing the Issue
owner, required fix, validation route, or responsibility relation, consume a
bounded Cause Investigation Receipt from `dependency-analysis` or produce the
same fields directly for a mechanically straightforward case.

```text
observed_facts: <snapshot-bound facts without causal wording>
cause_hypotheses:
  - statement: <plausible mechanism>
    supporting_evidence: <source/artifact locators>
    disconfirming_evidence: <facts that weaken the hypothesis>
    unresolved_alternatives: <alternatives that could change owner/fix/validation>
    confidence: <low|medium|high>
selected_cause_hypothesis: <best-supported current explanation|inconclusive>
cause_status: <hypothesis|directly-demonstrated|inconclusive>
expected_mechanism: <behavior expected if the selected hypothesis is correct>
action_derivation: <why the proposed investigation or fix follows>
```

Investigation depth is bounded by decision relevance. Inspect callers and
entrypoints, owning state/guards, downstream consumers and cleanup, sibling
implementations, tests/docs/config, and temporal evidence only when an
alternative in those surfaces could change owner, fix, validation, or Issue
boundary. Stop after those alternatives are disconfirmed or explicitly bounded;
do not perform an arbitrary full-repository scan.

Use epistemically qualified language:

- State observations as `observed at <snapshot/locator>`.
- State inferences as `is consistent with`, `suggests`, `may`, or `the current
  evidence favors`.
- Use `caused by` or `root cause` as a confirmed statement only when a direct,
  snapshot-bound mechanism demonstration excludes material alternatives. Even
  then, record the demonstration and its scope.
- Treat the `root_cause` value required by an existing schema as the selected
  cause hypothesis for grouping unless `cause_status: directly-demonstrated`.
- When alternatives remain that could change owner, fix, validation, or
  completion criteria, publish an investigation Issue and add
  `need verification`; do not prescribe a definitive required fix.

## Issue Responsibility Unit

Evaluate clauses, not titles. For each target or acceptance clause `c`, define:

```text
R(c) = (
  owner,
  decision,
  mechanism,
  change_surface,
  validation_authority,
  lifecycle,
  completion_condition
)
```

Two clauses remain in the same Issue only when all of the following hold:

1. One canonical owner can decide and close both clauses.
1. They belong to one mechanism closure or one governing decision.
1. They share a validation authority, or their validations are inseparable for
   correctness rather than merely convenient to run together.
1. Their completion conditions are jointly satisfiable without requiring an
   unrelated owner to finish independent work.

A small diff is not an Issue boundary. Select the smallest complete owning
responsibility unit that closes the supported mechanism. Conversely, do not
keep independent responsibilities together merely because they arose from the
same finding, path, PR, or conversation.

## Related Issue Set Intake

Before creating or modifying an Issue, collect the repository-qualified set of
related open and closed Issues plus linked PRs/commits. For each Issue record:

```text
issue: <owner/repository#number>
snapshot: <updated_at/body/comment readback identity>
state_and_reason: <open|closed plus close reason>
owner_responsibility: <canonical owner or unresolved>
kind: <decision|implementation|validation-tooling|workflow-policy|evidence|investigation>
responsibility_clauses: <clause ids and R(c) fields>
observed_facts: <snapshot-bound facts>
cause_hypotheses: <status, evidence, alternatives, confidence>
linked_changes: <repository-qualified PRs/commits>
unique_clauses: <obligations not represented elsewhere>
relations: <existing parent/child/sibling/supersedes/evidence links>
```

Closed state is lifecycle metadata, not implementation evidence. Compare the
Issue's clauses with linked changes and validation readback. A closed but
unimplemented governing decision is a reopen candidate, not automatically a
completed or duplicate Issue.

## Responsibility Reorganization

Use the intake set to construct one compact Issue relation graph. Choose
relations by responsibility, not chronology or title similarity:

- `canonical decision parent`: owns one governing decision and its own close
  condition.
- `implementation child`: owns one implementation mechanism under that
  decision.
- `validation/tooling child`: owns an independent validation oracle, router, or
  tool mechanism.
- `cross-repository policy sibling`: owns policy in another repository or
  authority domain; link it bidirectionally without copying implementation
  details.
- `evidence for`: preserves a finding or failure receipt without assigning
  implementation authority.
- `duplicate/superseded`: has no unique surviving responsibility after clause
  transfer and relation readback.

Apply this algorithm:

1. Freeze Issue, PR, commit, and source snapshots before planning mutations.
1. Partition every clause into Issue Responsibility Units.
1. Investigate causes sufficiently to distinguish owners and mechanisms; keep
   unresolved alternatives explicit.
1. Select at most one canonical parent for each governing decision. Prefer the
   Issue that owns the decision contract, not the oldest, largest, open, or most
   recently edited Issue.
1. Split an Issue when it contains independent owners, mechanism closures,
   validation authorities, or completion conditions.
1. Merge or re-parent clauses only when the receiving Issue is cohesive under
   the Issue Responsibility Unit contract.
1. Classify cross-repository authority as a sibling unless an actual
   decision-to-implementation dependency justifies a parent/child edge.
1. Preserve every unique clause using the Clause Conservation Contract.
1. Write repository-qualified backlinks and transfer receipts on every affected
   Issue before changing lifecycle state.
1. Read back the resulting bodies, relations, labels, and states. Close or
   reopen only after the graph and clause ledger are complete.

A relation does not automatically become a done-condition dependency. Add a
`requires` edge only when the related Issue's output is a logical precondition
for this Issue's own completion. Parent, child, and sibling Issues otherwise
retain independent, owner-scoped completion criteria. Do not create one giant
tracking Issue whose closure requires all related work.

## Clause Conservation Contract

Let `C_before` be the set of unique obligations in the intake Issue set. After
reorganization, every clause must appear in exactly one of these disjoint sets:

```text
C_before = C_assigned + C_deferred + C_rejected_with_reason
```

- `C_assigned`: one canonical destination Issue owns the clause.
- `C_deferred`: a named follow-up or investigation owns the unresolved clause.
- `C_rejected_with_reason`: evidence shows the clause is invalid, obsolete, or
  outside the owning responsibility; record the reason and authority.

For every moved clause, write:

```text
clause_id: <stable local id>
from_issue: <owner/repository#number>
to_issue: <owner/repository#number|defer target|rejected>
responsibility_unit: <R(c) summary>
reason: <why the destination owns it>
evidence: <snapshot-bound support>
relation: <parent|child|sibling|supersedes|evidence-for>
readback: <destination locator confirming preservation>
```

Reorganization is incomplete when a unique clause has no destination, one
clause has multiple authorities, or a destination cannot be read back. Do not
close the source Issue in those states.

## GitHub Mutation Order And Lifecycle

Build a mutation plan before writes and route GitHub publication through
`pr-processing`:

1. Add `in progress` to the active implementation Issue when code or canonical
   policy changes begin.
1. Update canonical destinations with transferred clauses and source backlinks.
1. Update source Issues with destination links and transfer receipts.
1. Add parent/child/sibling/evidence/supersedes relations in both directions.
1. Read back every affected Issue using repository-qualified identity.
1. Only then close duplicate/superseded Issues, reopen closed-but-incomplete
   parents when authorized, or change completion labels.
1. When the implementation is handoff-ready, remove `in progress` and add
   `ready for review`. Add `need verification` when the owner, mechanism,
   relation, or validation remains unresolved. Missing optional occurrence
   detail is carried as a follow-up clause, not used as a qualification gate.

Do not mutate an Issue in a repository for which the current actor lacks
explicit authority. Produce the same plan and receipt as a handoff instead.
AgentCanon owns relation and workflow-policy receipts; it does not copy or make
repository-specific implementation decisions for the parent repository.

## Related Skill Handoffs

Use one owner per fact class:

| skill | produces for this skill | this skill returns |
| --- | --- | --- |
| `agent-log-analysis` | compact observations, counts, artifact locators | selected durable finding or defer disposition |
| `dependency-analysis` | callers, mechanism/state, consumers, alternatives, impact, validation evidence | Issue owner/boundary questions and selected hypothesis status |
| `responsibility-cleanup` | complete owning responsibility unit and owner boundary | clauses requiring cleanup dispatch or boundary readback |
| `subagent-bootstrap` | bounded reviewer partitions and handback identities | Issue Finding Packets with non-overlapping evidence scopes |
| `pr-processing` | repository-qualified Issue/PR identity and mutation/publication boundary | mutation plan, backlinks, transfer receipts, and closeout readback |
| `task-routing` | discovery and ordered related-skill route | final selected route and any unresolved handoff |

Do not duplicate these skills' algorithms inside an Issue body. Record their
outputs, locators, and decisions as evidence.

## Grouping And Dispatch Boundary

Use `tools/agent_tools/issue_sync.py` as the host-side GitHub adapter for tool
and Issue findings. Its `(owner, root_cause, fix)` key produces
an initial candidate group. Before publication, apply Cause Investigation and
Issue Responsibility Unit contracts:

- keep one group when it is one owner/mechanism/validation/completion unit;
- split it when those responsibilities are independent;
- reorganize related existing Issues instead of creating another Issue when the
  target responsibility already exists but is incorrectly bounded; and
- never split solely to increase agent fan-out.

Warnings add a closeout obligation only when actionable or blocking.

Runtime dashboard evidence enters this route only through an explicit
`issue_worker_candidate` or `issue_worker_candidates` field. Counts, status
rows, and selection misses are observations and never synthesize candidates.
`read_issue_worker_handoffs()` emits a typed, read-only handoff using the
`checkout_identity.remote` value from the #938 readback. The same repository
may proceed to the logical IssueWorker route, which is executed by the host
`publisher`; another repository receives a qualified no-mutation handoff.
Missing owner or mechanism evidence remains in that publisher investigation
and may become `need verification`; it is not silently discarded.
`IssueWorker.plan_publication()` reads the related open/closed set and returns
`create`, `update`, `reopen`, `reorganize`, or `noop`. The publisher performs
the required GitHub mutation through the existing adapter and reads back the
URL, number, body, and state. The dashboard, resident runtime, and parent
Python remain read-only and do not receive GitHub credentials. Orchestration
materializes a publisher ToolCall with the checkout identity and typed handoff;
publication failure writes only the existing metadata-only pending packet
(repository, reason, private locator, and digest) and retries through this
same IssueWorker route.

After a successful GitHub readback, the publisher records and reads back one
body-free metadata receipt in the private archive's
`feedback/issue-packets/published/<owner>/<repository>/<number>.json` path
before consuming a pending packet. The receipt carries only repository,
number, URL, state, action, responsibility/occurrence locators, source finding
kind, and timestamp. Receipt/archive failure retains the pending packet and
must not be reported as successful publication; non-qualified and foreign
handoffs do not create receipts. The publisher ToolCall invokes the resident
AgentCanon `issue_sync.py --stage-publication-receipt` subcommand after a
receipt-route preflight, and the host shell archive sync owns the subsequent
Git commit/push; the dashboard only reads the published namespace. If the
external runtime/spool route is unavailable, defer before invoking GitHub.

The publisher filters every related Issue against both the candidate repository
and the current checkout identity before editing. Foreign Issues are retained
as handoff relations only. `noop` requires the same responsibility tuple and a
candidate fix/mechanism clause in the structured required-fix section; an old
or missing clause is an update/reorganization case. Clause transfer removes
only the matching lines inside the owning Markdown section and preserves the
same text in Evidence or other sections. Pending retries must receive a fresh
#938 checkout identity; the packet's repository is checked against it but is
never treated as authentication authority.

## Multi-Agent Partition

Use a parent-created `Issue Finding Packet` before spawning. Each packet fixes:

```text
cause_category: <abstract-cause>
evidence_cells: <structured dashboard headings, source locators, or API JSON paths>
instance_partition: <repo_key|hook_family|skill_name|workflow_name|tool_name|issue_id|path_scope>
candidate_issue_slug: <lowercase-ascii-slug>
affected_surfaces: <candidate edit or verification paths>
occurrence_locations: <observed records when available>
related_issue_set: <repository-qualified open/closed identities>
cause_hypothesis_scope: <alternatives this reviewer may evaluate>
duplicate_search: <bounded query and snapshot>
expected_output: <new_candidate|merge_existing|reorganize_existing|defer_with_reason>
```

`affected_surfaces` is planning scope. It may include files that need edits or
verification, but it is not evidence that the defect occurred there.
`occurrence_locations` names observed sites when available and cannot be
inferred from a repository name, directory, or broad affected surface. The
IssueWorker route does not require a separate `*_confirmed` flag: the explicit
candidate record and the checkout identity readback are the authorities.

Recommended review partition:

- `prompt_config_reviewer`: `selection_gap`, `prompt_or_config_drift`
- `docs_workflow_steward`: skill/workflow wording, Issue clauses, and relation
  quality
- `project_reviewer`: `archive_hygiene`, `wave_execution`,
  `structure_boundary`, and responsibility units
- `artifact_reviewer`: raw/structured artifact sufficiency and evidence paths

When several independent clusters exist, parent-owned routing may dispatch
distinct groups. A single responsibility unit is never split solely to increase
fan-out. Each optional instance receives only its packet, structured artifact
paths, allowed Issue paths, candidate affected surfaces, validation route, and
return schema. The parent consumes the grouping and responsibility result before
writing files or mutating Issues.

## Confirmed Occurrence Location Contract

When available, record each observed occurrence location tied to the source or
artifact snapshot where the behavior was observed. Use one record per distinct
site:

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
- When no occurrence location is available, retain the explicit candidate and
  let the IssueWorker publisher carry the missing-location follow-up. Do not
  synthesize a location from a repository name, directory, or broad surface.

## Issue Candidate Contract

Before writing a new Issue:

1. Search existing durable and GitHub surfaces, including open and closed
   Issues, repository-qualified cross-repository links, and linked PRs/commits.

   ```bash
   git grep -n "<owner, decision, mechanism, cause, or occurrence keywords>" \
     -- documents/notes/knowledge documents agents
   ```

1. Build the Related Issue Set Intake. If the responsibility exists but current
   boundaries conflict, use Responsibility Reorganization instead of creating a
   new parallel Issue.
1. Expand candidate affected surfaces and investigate cause through dependency
   review.

   ```bash
   bash tools/agent_tools/run_repo_dependency_review.sh \
     --report-dir reports/agents/<run-id>/dependency-review/<slug> \
     --search-hits-file reports/agents/<run-id>/<slug>-search-hits.txt
   ```

1. Record occurrence locations when the candidate carries observed sites. Keep
   observed sites separate from proposed edit scope; an absent optional
   occurrence locator does not disqualify an explicit IssueWorker candidate.
1. Resolve or create one repository-qualified GitHub Issue through the host
   adapter when online.
1. When offline, write only metadata under the private
   `agent-canon-log/feedback/issue-packets/pending/` path. The packet stores a
   private body locator and digest; it never stores the body or a pending
   marker in AgentCanon source.
1. Online publication reads back the GitHub URL, repository, number, title,
   body, and state, then records and reads back the body-free private
   publication receipt before removing the pending packet.

Issue body sections:

- `## Finding`: observed behavior and structured evidence counts, without
  causal overstatement
- `## Occurrence Locations`: snapshot, path, stable locator, observation, and
  evidence for each site
- `## Cause Hypotheses`: alternatives, support, disconfirming evidence,
  confidence, and selected status
- `## Responsibility Boundary`: owner, decision/mechanism, change surface,
  validation authority, lifecycle, and completion condition
- `## Relations And Clause Transfers`: repository-qualified Issue graph and
  clause ledger when existing Issues are involved
- `## Required Investigation Or Fix`: action derived from current evidence;
  label tentative fixes as tentative
- `## Evidence`: commands, artifacts, dependency review, and linked changes
- `## Done`: only this Issue's owner-scoped completion criteria
- `## Non-goals`: adjacent work explicitly excluded from completion

Do not call an Issue complete when the owner/mechanism remains unresolved,
when clauses lack a canonical destination, or when completion requires
unrelated Issue responsibilities. Missing optional occurrence detail is a
follow-up clause, not a second qualification gate.

## Distributed Clause Routing

An Issue is a routing envelope, not an authority or a guarantee registry. Split
`problem`, `required_action`, `done`, and `close_condition` by the mechanism
owner before implementation or closeout. Each projected clause carries its
owner, bounded clause reference, original authority/witness, and (when
available) the owner's local receipt. A clause is `grounded` only when its
authority is a user request, pre-existing public contract, reproduced failure,
or external decision and its owner can point to the relevant mechanism and
observation. A problem without an observed artifact/path is `unproven`; an
action or completion condition without that root is `advisory`.

Issue authorship, labels, PR references, open/closed state, approval text,
copied agent claims, and repeated comments do not upgrade a clause. During
pre-close revalidation, retain grounded clauses and downgrade unsupported
`done`/`close_condition` text; do not discard a mixed Issue or create a new
blocker. `issue_sync.py` exposes this projection through
`project_issue_clauses()` and only projects it; the mechanism owner supplies the
receipt and decides correspondence.

## Output Packet

Write a run-local `Issue Finding And Reorganization Packet` when the task asks
for analysis, multiple candidates exist, existing Issue boundaries may change,
or before spawning subagents:

```text
issue_finding_scope: <dashboard|run-bundle|archive|source|mixed>
source_snapshots: <repository/artifact identities>
structured_evidence: <paths and locators>
related_issue_count: <n open/closed>
candidate_count: <n>
new_issue_count: <n>
merged_existing_count: <n>
reorganized_existing_count: <n>
deferred_count: <n>
confirmed_occurrence_location_count: <n>
cause_status: <hypothesis|directly-demonstrated|inconclusive>
responsibility_units: <owner/decision/mechanism/validation/completion summaries>
issue_graph: <parent/child/sibling/evidence/supersedes edges>
clause_transfer_ledger: <assigned/deferred/rejected rows>
issue_paths_or_urls: <repository-qualified GitHub URLs/numbers>
subagent_partitions: <role_id:instance_id:agent_type:packet>
validation: <commands and readback>
```

When every candidate merges into an existing cohesive Issue, reorganizes an
existing set, or stays below the durable threshold, record the destination
Issue and evidence classification rather than creating another registry entry.

## Failure Semantics

- If a canonical parent cannot be selected uniquely, do not auto-close,
  auto-reopen, or force unrelated responsibilities together.
- If cause alternatives could change owner, fix, validation, or boundary, keep
  the Issue investigative and add `need verification`.
- Do not close cross-repository authority as a duplicate solely because the
  finding is shared.
- Do not close a source Issue before clause destinations, backlinks, and
  readback exist.
- Closed state is not evidence that implementation or validation occurred.
- If a unique clause has no GitHub destination, reorganization remains incomplete.
- Do not create a second Issue database or a giant tracking Issue. GitHub Issues
  remain the authority; a private packet is only a run-local transport receipt.

## Validation

Run focused GitHub adapter and skill wiring checks after changing this route:

```bash
python3 tools/agent_tools/issue_sync.py --issue-url https://github.com/iwashita-nozomu/agent-canon/issues/<number>
python3 tools/agent_tools/check_skill_frontmatter.py --root .
python3 tools/agent_tools/skill_tool_commands.py check
python3 tools/agent_tools/skill_shim_materializer.py check --root .
python3 tools/agent_tools/check_dependency_headers.py --changed
bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing
bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header
```
