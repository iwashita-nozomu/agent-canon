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
upstream implementation ../../eval/producers/generate_agent_runtime_dashboard.py emits structured log evidence
upstream implementation ../../tools/runtime/archive/runtime_log_archive_git.py resolves accumulated log archive state
upstream implementation ../../tools/repository/github/issue_sync.py resolves GitHub Issues and private packets
downstream design ../../.codex/personal/skills/issue-finding-report/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

Read the section for the current action. `agent-log-analysis` owns compact
runtime observation, `dependency-analysis` owns causal/mechanism evidence,
`responsibility-cleanup` owns complete responsibility units, and `pr-processing`
owns GitHub publication. This skill connects those results to Issue boundaries.

## Purpose

Turn a current AgentCanon-owned defect or accumulated structured evidence into
an investigative Issue, an update to a cohesive existing Issue, or a responsibility
reorganization. A first runtime record preserves observation; it does not claim a
confirmed cause or completion.

## Procedure

1. Classify the input as a direct runtime defect, an evidence-backed new Issue,
   or an existing Issue-set repair. For a runtime defect, first distinguish an
   AgentCanon-owned invariant failure from a consumer, host, credential, or
   ownership-unknown failure.
2. Record a direct runtime candidate immediately with the observed error/action,
   immutable checkout/runtime snapshot, expected/actual behavior, and explicitly
   uncertain hypotheses. Missing optional occurrence detail does not block the
   record. Do not require a private receipt or second occurrence before recording.
3. Investigate the current cause only as far as it can change owner, mechanism,
   validation, or Issue boundary. Read callers/entrypoints, state/guards, effects,
   cleanup, and relevant sibling evidence; stop when alternatives are excluded or
   remain explicitly unresolved. Use the existing dependency-analysis evidence and
   avoid turning a hypothesis into a required fix.
4. Collect related open/closed Issues and linked PRs/commits when enriching or
   reorganizing. Group clauses by one owner, mechanism closure, validation
   authority, and independently satisfiable completion; split mixed Issues,
   re-parent governing decisions, and preserve every unique clause. Similar titles
   or a shared path are retrieval signals, not merge proof.
5. Publish through the existing repository-qualified IssueWorker/host adapter:
   create, comment, edit, reopen, or reorganize as selected, then read back the
   URL/number/title/body/state. Use configured GitHub/transport credentials;
   authentication failures return to that owner. Offline work keeps only the
   existing private pending metadata route and does not write Issue bodies into
   AgentCanon source.
6. Validate the final Issue relation and clause destinations through the existing
   readback owner. Leave unresolved cause or cross-repository ownership investigative
   or deferred; do not close an Issue because text, labels, or a prior closed state
   says it is complete.

## Direct AgentCanon Defect Escalation

Use this route only when current source/effect evidence supports AgentCanon as the
owner. The host publisher targets `iwashita-nozomu/agent-canon`; a foreign or
unknown owner is a qualified no-mutation handoff. Preserve pending metadata when
GitHub or the configured transport is unavailable.

## Existing Issue Reorganization

Use the current Issue set as the source for clauses and relations. Prefer one
canonical decision owner, implementation/validation children only when their
mechanisms are independent, and cross-repository siblings for separate authority.
Transfer unique obligations before changing lifecycle state, then read back bodies,
relations, labels, and states. Existing `issue_sync.py#project_issue_clauses()`
projects clause state; this skill does not create a second ledger or packet schema.

## Output and Validation

Return the selected Issue URL/number or pending locator, owner/mechanism status,
changed relation or clause destination, actual readback, and remaining uncertainty.
Use the existing resident receipt and skill/frontmatter/dependency checks only when
this route changes or the selected owner requires them. A local observation does not
create an extra gate or a second Issue database.
