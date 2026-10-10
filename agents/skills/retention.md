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

Use this Skill before mutating or archiving an existing collection of experiment results.
It plans retention; it does not own experiment execution, artifact writing, archive serialization, publication, or report generation.

## Procedure

各 source unit について、mutation または archive の前に順に決めます。

1. source identity/content evidence と semantic classification。
2. `retain|archive|external|delete-after-use|defer` の retention decision。
3. `compressed_archive|as_is|existing_external` の representation、destination、provenance。
4. source-preservation condition、verification、resume identity。

Semantic classification and physical representation are orthogonal. Do not infer that canonical data must be kept as-is or that noncanonical data must be compressed.

## Failure-closed rules

- `unknown` or `defer` never authorizes compression or deletion.
- Planning is read-only. Archive execution remains with the existing archive writer.
- A source unit may have only one selected final placement in a plan.
- Reuse an already verified identical archive/object when available instead of creating a duplicate.
- Deletion is admissible only after the selected destination has been read back and the explicit preservation condition is satisfied.

## Handoff

decision records と unresolved units を返します。実行は `experiment-lifecycle`、artifact identity/checksum は
`result-artifact-writeout`、annex/archive serialization は既存 writer に委譲します。
