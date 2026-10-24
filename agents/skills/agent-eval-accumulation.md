# agent-eval-accumulation

<!--
@dependency-start
contract skill
responsibility Documents accumulated AgentCanon eval evidence repair and validation.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../eval/definitions/README.md accumulated eval family contract
upstream design ../../documents/runtime/runtime-log-archive.md external log archive boundary
upstream implementation ../../eval/producers/run_accumulated_agent_evals.py runs registered eval producers
upstream implementation ../../eval/checkers/eval_accumulation_check.py validates accumulated eval families
downstream implementation ../../.codex/personal/skills/agent-eval-accumulation/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Purpose / Use When

Use when eval collection or repair is selected to establish fresh accumulated
evidence. Read-only observation of missing, old, or failing data stays with
[agent-log-analysis](agent-log-analysis.md). Registered producers own reports;
this Skill does not create or edit eval results by hand.

Related main changes select the registered producers automatically through
[main Eval collection and delivery](../../documents/runtime/runtime-log-archive.md#main-change-eval-collection).
Use the flow below for a selected manual collection or repair.

## Required Flow

1. Fix the target, producer-source revision, requested freshness, and a unique
   run ID. Reuse the installed bootstrap and authorized control root from
   [agent-canon-bootstrap](agent-canon-bootstrap.md#command-shape). Keep this
   run's command output and receipts under the explicit external runtime root.
2. Run the registered `eval-accumulation-check` through `tool run` for the target
   and retain its bounded summary. Its pass establishes archive structure and
   family coverage; freshness requires the selected collection's revision and
   timestamp. Classify transport metadata separately from actual hook events.
3. Collect through the existing bootstrap entrypoint:

```bash
"$BOOTSTRAP" "${COMMON[@]}" eval collect --root "$TARGET" --run-id "$RUN_ID"
```

4. Inspect the returned collection and producer summaries: selected source and
   target revisions, family status, output locations, and before/after source
   identity. Source unchanged and producer success need their actual evidence.
   Read only relevant failure details; keep the original stdout/stderr and
   failure receipts until their owning retention/publication route permits cleanup.
5. Publish the successful collection through the existing host archive owner:

```bash
"$BOOTSTRAP" "${COMMON[@]}" eval sync --run-id "$RUN_ID"
```

6. Verify the publisher's remote ref/tree/blob readback and the archived
   collection identity. Recheck accumulation with the same owner, then run the
   selected source-artifact guard. Report `published`, `pending`, or
   `not-required` from evidence. A local collection or commit is not publication.
   A completed repair requires `EVAL_ACCUMULATION=pass` and zero blocking
   findings; unresolved work remains explicit.

`BOOTSTRAP`, `COMMON`, and `TARGET` use the observed install/control/target
bindings; `RUN_ID` is unique to this selected run. Use returned spool paths.
Do not write reports into the source checkout or invent another producer,
queue, publisher, or archive layout.

## Failures and completion

Keep a failing producer/checker result as a failure. Record the failing contract,
observation, cause, preserved intent, and evidence in the existing task record.
Distinguish producer bugs, oracle/spec mismatches, fixture/environment/stale
artifacts, unrelated failures, and an unresolved governing-contract conflict.
Repair the supported cause through its owner and rerun the affected operation.
Preserve unresolved failures and pending spool for continuation.

Do not omit registered families, weaken an oracle or validation scope, replace
producer output with handwritten reports, or delete unpublished evidence to
obtain a pass. Final evidence includes the selected source revision, actual
producer/checker outcomes, source unchanged result, and archive publication
state. Raw/summary placement uses [result-artifact-writeout](result-artifact-writeout.md);
a requested narrative report uses [report-writing](report-writing.md).
