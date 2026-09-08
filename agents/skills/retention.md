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

## Decision model

For every selected source unit, record these independent decisions before mutation:

1. source identity and content evidence;
2. semantic classification and confidence;
3. retention decision: `retain|archive|external|delete-after-use|defer`;
4. physical representation: `compressed_archive|as_is|existing_external`;
5. source-preservation condition;
6. destination and provenance reference;
7. verification and resume identity.

Semantic classification and physical representation are orthogonal. Do not infer that canonical data must be kept as-is or that noncanonical data must be compressed.

## Failure-closed rules

- `unknown` or `defer` never authorizes compression or deletion.
- Planning is read-only. Archive execution remains with the existing archive writer.
- A source unit may have only one selected final placement in a plan.
- Reuse an already verified identical archive/object when available instead of creating a duplicate.
- Deletion is admissible only after the selected destination has been read back and the explicit preservation condition is satisfied.

## Handoff

Return the decision records plus unresolved units. The existing experiment lifecycle remains the run-state owner, result-artifact-writeout remains the concrete artifact identity/checksum owner, and the annex/archive writer remains the deterministic serialization owner.
