# GPT-5.6 benchmark report policy status
<!--
@dependency-start
contract reference
responsibility Separates dated GPT-5.6 benchmark observations from current AgentCanon orchestration and write-safety policy.
upstream reference gpt-5.6-benchmark-report-ja.md dated benchmark synthesis being scoped
upstream design ../documents/design/responsibility-rationale.md canonical current multi-agent and write-control rationale
@dependency-end
-->

## Status

`gpt-5.6-benchmark-report-ja.md` is retained as dated benchmark/evidence synthesis. It is **not** the canonical owner of current AgentCanon execution topology, agent count, or write protocol. Current policy is owned by `documents/design/responsibility-rationale.md`; a later benchmark may update evidence without silently changing that policy.

This separation resolves two places where the historical report over-generalized benchmark observations into defaults that the same report did not experimentally establish at task/system level.

## Multi-agent interpretation

The historical `3..N scouts + 1..2 verifiers + arbiter` topology is an example of a high-coverage decomposition, not a default. AgentCanon starts with one owner and expands only when independent search surfaces, competing hypotheses, verification value, failure cost, or parallel gain justify another agent. Repeating the same context across agents is not evidence diversity. Stopping depends on marginal information gain, latency/budget, and write contention rather than a fixed agent count.

The benchmark report's own Use/Avoid and proposed A/B evaluation sections therefore remain evidence/limitations, while the fixed topology language must not be consumed as current policy until comparative task-level evidence establishes a benefit for the relevant workload class.

## Write-control interpretation

The historical statement that every production write should use dry-run, plan validation, two-phase commit, and single-writer control is not a universal AgentCanon requirement. Those controls protect particular failure modes and are selected from operation semantics:

- local/reversible writes may execute directly with normal precondition/readback appropriate to the owner;
- bounded remote/reconcilable writes require fresh identity/authority/preconditions and API readback, but not a fictional prepare/commit phase when the API has none;
- irreversible, destructive, high-impact, or shared-mutable writes require stronger approval, conflict prevention, or single-writer controls when those controls actually mitigate the reachable failure.

Automation benchmark evidence supports caution around unattended high-impact writes. It does not establish two-phase commit as a meaningful protocol for every filesystem edit or remote API mutation.

## Consumer rule

No runtime skill, workflow, gate, or reviewer may treat a fixed agent topology or a universal two-phase write protocol from the historical report as normative merely by citation. Consumers must route through the canonical responsibility rationale and explain the concrete activation evidence for any stronger topology or write control they select.

## Revalidation

A future policy change may promote a stronger default only with workload-relevant comparative evidence and an explicit update to the canonical design owner. Updating the benchmark report alone is insufficient.
