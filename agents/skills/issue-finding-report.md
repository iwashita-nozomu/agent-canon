# issue-finding-report

<!--
@dependency-start
contract skill
responsibility Turns AgentCanon-owned defect evidence into investigative Issues and preserves clauses during Issue reorganization.
upstream design ../canonical/skills.md public Skill registry
upstream design ./agent-log-analysis.md structured runtime evidence
upstream design ./dependency-analysis.md cause and mechanism investigation
upstream design ./responsibility-cleanup.md responsibility and boundary units
upstream design ./pr-processing.md repository-qualified Issue identity and publication
upstream design ../../documents/runtime/private-feedback-knowledge.md private pending-Issue route
upstream implementation ../../tools/runtime/archive/runtime_log_archive_git.py runtime archive state
upstream implementation ../../tools/repository/github/issue_sync.py Issue clause projection
downstream design ../../.codex/personal/skills/issue-finding-report/SKILL.md runtime discovery adapter
@dependency-end
-->

## Purpose

Record a current AgentCanon-owned defect or accumulated structured evidence as an
investigative Issue, update a cohesive existing Issue, or reorganize related
responsibilities. An observation is not a confirmed cause or completed fix.

Use [agent-log-analysis](agent-log-analysis.md) for accumulated runtime evidence,
[dependency-analysis](dependency-analysis.md) when cause or mechanism is open,
and [responsibility-cleanup](responsibility-cleanup.md) for boundary
reorganization.

## Record a finding

Distinguish an AgentCanon invariant failure from consumer, host, credential, or
unknown-owner behavior. Preserve the observed action, source/runtime snapshot
when available, expected and actual behavior, and uncertain hypotheses. Do not
require recurrence or a private receipt before preserving a useful observation.

Investigate only enough to change the owner, mechanism, validation, or Issue
boundary. Keep unproven causes out of required fixes. For unknown or foreign
ownership, return a qualified no-mutation handoff.

Before creating an Issue, check whether an existing Issue already owns the same
decision; update or reorganize that Issue when its responsibility matches.

## Reorganize Issues

Read related Issues and linked PRs or commits that affect the requested clauses.
Split or re-parent when ownership, mechanism, validation authority, or
independently satisfiable completion differs; preserve each unique clause before
changing lifecycle state. Similar titles or shared paths alone do not establish
a duplicate.

## Publish and close

Use [pr-processing](pr-processing.md) for the authorized Issue operation,
repository-qualified identity, and remote readback. When GitHub is unavailable,
use only the existing
[private pending-metadata route](../../documents/runtime/private-feedback-knowledge.md);
never store Issue bodies in AgentCanon source. Do not close an Issue without
completion evidence.

The direct AgentCanon defect route targets iwashita-nozomu/agent-canon only when
current source and effect evidence support that ownership. Otherwise preserve
the investigation or hand it to the qualified owner.

## Return

Return the Issue URL or pending locator, owner and cause status, changed
relation or clause destination, readback, and remaining uncertainty.

