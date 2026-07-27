---
name: result-visualize
description: Use when designing reusable result visualizations that bind each figure to its exact calculation, coverage, and chart geometry in one contract.
---
<!--
@dependency-start
contract skill
responsibility Documents result visualization design for this repository.
upstream design ../../../agents/skills/result-visualize.md defines reusable figure contracts and required calculation patterns
upstream design ../../../documents/runtime/SHARED_RUNTIME_SURFACES.md documents runtime boundary policy
upstream design ../../../documents/experiments/experiment-report-style.md defines reader-facing evidence expectations
upstream design ../../../agents/skills/structure-planning.md defines first-figure planning for non-trivial results
upstream design ../../../agents/skills/report-writing.md receives interpretation prose from figure inventories
upstream design ../../../agents/skills/html-experiment-report.md reuses figure-first contracts for browser reports
upstream design ../../../agents/skills/result-artifact-writeout.md owns artifact placement and manifest discipline
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py prints skill command packets
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py validates public skill catalog consistency
@dependency-end
-->

# result-visualize

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill result-visualize --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->

1. Read `agents/skills/result-visualize.md`.
1. Keep the process domain-independent by parameterizing every result index,
   measure, and comparison key from the source artifact.
1. Make the execution-status view the first figure contract and include it
   exactly once; do not repeat status summaries before later sections.
1. For each figure, define question, source fields, population coverage rule, index levels, grouping keys, denominator, and weighting in one block.
1. Keep coverage complete over expected keys by default; missingness must be represented through explicit status entries or eligible observations, not silent dropping.
1. For every figure block, colocate:
   - exact metric formula/transformation,
   - chart geometry (`x`, `y`, `facet`, scale type),
   - missingness handling,
   - interpretation scope.
1. Write formulas with Markdown math delimiters. Resolve every `or`, `optional`,
   and alternative geometry before finalizing the inventory; split alternatives
   into separate figure contracts when both outputs are required.
1. Distinguish estimator forms before summarization: if averages and transforms are nested, declare whether the target is $E[g(X)]$ or $g(E[X])$.
1. Use reusable calculation patterns from the canonical doc and choose geometry by question; additional geometries are allowed when their contract is explicit and includes coverage assumptions.
1. Track missingness explicitly with `observed`, `missing`, `failed`, and `not_applicable` populations. Never impute silently.
1. If source data is pre-imputed, document provenance with the exact source and operation.
1. Keep interpretation and prose to `report-writing` and raw artifact persistence to `result-artifact-writeout`.
