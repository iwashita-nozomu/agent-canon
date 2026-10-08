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

For a direct runtime observation, distinguish an AgentCanon-owned invariant
failure from a consumer, host, credential, or unknown-owner failure. Preserve
the observed action, current snapshot, expected/actual behavior, and uncertain
hypotheses promptly; missing optional occurrence detail is not a reason to lose
the observation. Include the immutable checkout/runtime snapshot when available;
do not require a private receipt or second occurrence before recording. Investigate
only as far as needed to change the owner,
mechanism, validation, or Issue boundary. Use callers, state, effects, cleanup,
and sibling evidence to narrow the cause, and keep an unproven hypothesis out of
the required fix.

When updating or reorganizing existing Issues, inspect the related Issues and
linked PRs/commits that affect the requested clauses. Group by owner, mechanism,
validation authority, and independently satisfiable completion. Split or
re-parent when those responsibilities differ, preserving each unique clause;
similar titles or shared paths are retrieval signals, not merge proof.

Publish only the selected Issue operation through the existing
repository-qualified IssueWorker/host adapter, then read back its identity,
content, and state. Use configured GitHub/transport credentials; return
authentication failures to that owner. Offline work uses only the existing
private pending-metadata route and never writes Issue bodies into AgentCanon
source. Leave unresolved cause or cross-repository ownership investigative or
deferred, and do not close an Issue without completion evidence.

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
