# dependency-analysis

<!--
@dependency-start
contract skill
responsibility Documents dependency-analysis for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../canonical/CODEX_WORKFLOW.md defines workflow gate usage
upstream design ./catalog.yaml registers this public skill
upstream design ../../documents/tools/lsp_code_analysis.md owns LSP relation evidence and capability limits
upstream implementation ../../tools/analysis/dependencies/scip_index.py owns native SCIP index and bounded query operations
@dependency-end
-->

## Reader Map

- Purpose: locate causal code and use dependency evidence to decide the owner,
  edit, and validation.
- Use When: a repair's cause is unresolved, or a dependency question can change
  the requested decision. Start with [Method](#method).
- Boundary: dependency headers, code-symbol relations, and text-search matches
  answer different questions; keep their evidence distinct.

## Purpose

Choose the smallest useful evidence for a cause or dependency question. Start
from the requested target and its contract, then investigate further only where
the result could change the selected owner, edit, or validation.

## Use When

- A requested diagnosis or repair has no established causal code or mechanism.
- A dependency manifest or edge is changed or disputed.
- A possible code reference or dependency may affect the requested scope.
- An explicit cross-module/API change needs an execution order or affected
  consumer identified.

## Method

For a repair with no established cause, use steps 1-4 before choosing a fix:
the causal mechanism determines the edit, not the first plausible patch. Reuse
current cause evidence. New implementation and explicitly agreed replacement
follow the current contract without requiring diagnosis of superseded code.

1. Read the target, current diff, and governing contract. Use the requested
   path, source location, or finding as the starting point.
2. Identify the question that remains open. A filename, search hit, stack frame,
   or error-reporting site alone does not establish ownership or cause.
3. Select only evidence that can resolve it. Keep manifest edges, code-symbol
   relations, and text-search candidates separate: a header edge is not a call
   graph, a symbol reference does not prove runtime reachability, and a text
   match does not establish that a file owns the behavior.
4. For a failure, compare expected and actual inputs, state, and outputs.
   Trace the relevant path from source and available observations to the
   expression, branch, call, state update, or missing operation that produces
   the difference, rather than stopping where the error becomes visible.
   Record the revision, path, symbol or block, and the supported chain from
   input/state through that operation to the observed effect in the existing
   task record. If competing explanations could change the repair, select the
   smallest source check or authorized observation that distinguishes them;
   keep unsupported alternatives uncertain. A sufficient static derivation
   needs no extra run. Preserve current execution authority and explicit holds.
5. If the task includes a repair, change the supported cause at its owner first.
   For code changes, then follow affected definitions, references, and callers
   through the existing [LSP route](../../documents/tools/lsp_code_analysis.md)
   and fix concrete related problems within scope. Compare the resulting diff
   with changed and retained guarantees, and use the selected validation route.
   Do not turn an unresolved cause into a symptom-level fix or require inspecting
   all related code before the located repair.

Inspect additional or historical assets only when a concrete question about
reuse, continuity, or a suspected missing predecessor could change the repair.
Do not make a packet, repository-wide scan, index, or history search a default
entry condition.

## Conditional evidence routes

- For dependency-header format, graph semantics, or owner-tool questions, use
  [dependency-manifest-design](../../documents/design/dependency-manifest-design.md)
  and its existing check commands.
- When repository-wide symbol/reference evidence could change scope, use the
  project's supported native relation source. AgentCanon's bounded SCIP query
  is available when a suitable index exists:

  ```bash
  python3 tools/analysis/dependencies/scip_index.py query \
    --root . \
    --runtime-root <external-runtime-root> \
    --index <runtime-relative-path>/index.scip \
    --path <source-path>
  ```

  Index creation and language support follow the existing
  [SCIP owner](../../documents/tools/scip_index.md). An unavailable or partial
  relation source leaves that relation unverified; it does not prove absence.
- When source search is the starting point, treat matches as candidates. Expand
  to a responsible edit scope only when source ownership or the governing
  contract requires it.

## Conditional cross-module resolution

For an explicit cross-module/API change, inspect only the involved roots and
edges. Distinguish source/API/build dependencies from repository pin edges;
record order and affected consumers in the caller's existing plan when they
determine implementation or validation order. Keep using the established
cross-module handoff when this route needs it.

## Interpretation

Use only what the selected evidence establishes. Failed or unsupported relation
queries, missing fields, and incomplete indexes remain verification gaps rather
than evidence of no dependency. Keep code relations separate from manifest
edges even when both inform one scope decision. Preserve the observed input,
source location, causal reasoning, and remaining uncertainty in the existing
task record when they affect the action. If LSP relation evidence is selected,
follow its capability limits in
[lsp_code_analysis.md](../../documents/tools/lsp_code_analysis.md).

## Conditional review

If findings-first review is selected after the owner is known, use
[change-review](change-review.md). For dependency evidence needed by an existing
cross-surface plan, use its current handoff; do not require a new packet schema
or fixed field list.
