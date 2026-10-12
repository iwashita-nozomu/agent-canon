# Experiment Result Retention Planning
<!--
@dependency-start
contract skill
responsibility Owns read-only retention planning for existing experiment results and delegates run state, artifact identity, and archive serialization.
upstream design ../canonical/skills.md public skill registry and visibility contract
upstream design ../../documents/experiments/result-log-retention-and-visualization.md shared result retention policy
upstream implementation ./catalog.yaml public skill identity and routing metadata
downstream design ./experiment-lifecycle.md experiment run-state and publication owner
downstream design ./result-artifact-writeout.md concrete artifact identity and checksum owner
downstream implementation ../../tools/experiments/artifacts/save_experiment_result_annex.py deterministic archive serialization owner
@dependency-end
-->

Use this Skill to plan retention read-only. Execution, artifact, and report
details stay with their owners.

## Procedure

For each source unit, identify its role and future-use, reproducibility, or
interpretation value. Recommend keeping, archiving, external storage, deletion
after use, or deferral under the caller's policy. Choose a representation or
destination only when it affects preservation; role and representation are
separate decisions.

## Topic code and result closeout

For AgentCanon topic-code retirement only, follow the
[branch scope](../../documents/operations/BRANCH_SCOPE.md#experiment-topic-branch-scope)
and [archive/summary policy](../../documents/experiments/result-log-retention-and-visualization.md#experiment-archive-and-summary-retention).
These require retrievable evidence before retirement, preserve shared
infrastructure and completed summaries on `main`, and define when an Issue
lists missing summary paths.

## Failure-closed rules

- Unknown value, destination, or preservation condition means defer, not delete.
- Give each source unit one disposition; split only when its parts need different treatment.
- Reuse a verified retained copy when it meets the preservation need.
- Delete only after required copies are retrievable and the preservation condition holds.
- Archive execution remains with the existing archive owner.

## Handoff

Return recommendations and unresolved decisions in the requested form. Use
[experiment-lifecycle](experiment-lifecycle.md) or
[result-artifact-writeout](result-artifact-writeout.md) only when relevant;
archive serialization stays with its owner.
