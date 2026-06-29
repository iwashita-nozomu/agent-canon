---
name: dependency-analysis
description: Use when checking, validating, or diagnosing repository dependency manifests, expanding code/header/search dependencies into a change-impact packet, or preparing repair-planning and subagent handoff context before editing, review, or closeout.
---

<!--
@dependency-start
contract skill
responsibility Documents Dependency Analysis for this repository.
upstream design ../../../documents/dependency-manifest-design.md defines manifest format and graph semantics
upstream design ../../../agents/canonical/CODEX_WORKFLOW.md defines workflow gate usage
upstream design ../../../agents/skills/dependency-analysis.md documents the human-facing skill
upstream design ../../../agents/workflows/hypothesis-validation-workflow.md separates code and header dependency evidence
upstream implementation ../../../tools/agent_tools/scan_code_dependencies.sh extracts file-level code dependency evidence
upstream implementation ../../../tools/agent_tools/helper_function_inventory.py extracts Python function-level call graph context
upstream implementation ../../../tools/agent_tools/check_design_doc_claims.py validates design-document evidence claims
@dependency-end
-->

# Dependency Analysis

## Reader Map

- Purpose: expose dependency-analysis routing to Codex for manifests, graphs,
  code dependency evidence, and repair-planning handoffs.
- Section path: Tool Commands gives the command packet; the numbered rules
  choose an evidence-complete mode and list changed-file, graph, search,
  design-claim, and Change Impact Packet operations.
- Use when: a task must validate dependency headers, expand fix scope, compare
  code/header dependency evidence, or prepare a subagent handoff.
- Boundary: this shim defines runtime sequencing; the canonical explanation
  lives in `agents/skills/dependency-analysis.md`.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-analysis --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `documents/dependency-manifest-design.md`.
1. If the task selects or justifies a fix surface, read `agents/workflows/hypothesis-validation-workflow.md`.
1. For code-improvement work, do not implement until the artifact records `Observation`, `Hypothesis`, `Expected Mechanism`, `Candidate Comparison`, `Disconfirming Evidence`, `Support Evidence`, and `fix_surface_validated=yes`.
1. After the change, record `Post-Change Evidence` and `Hypothesis Decision: supported|rejected|inconclusive`. If the decision is `rejected` or `inconclusive`, return to hypothesis selection instead of expanding the implementation pass.
1. Choose the mode that answers the task without hiding dependency evidence:
   - code dependency surface: run `scan_code_dependencies.sh`
   - changed-file closeout gate: use `--changed`
   - explicit file review: pass file paths explicitly
   - repo migration inventory: run full scan without `--changed`
   - dependency edge change: include graph validation
   - repo-wide search triage: run responsibility-based search first, then use bounded `git grep -l` only as comparison evidence or within selected source surfaces before search-to-edit-scope expansion
   - design-document evidence: run `check_design_doc_claims.py` on changed or newly authored design docs
   - repair planning or subagent handoff: build a structured `Change Impact
     Packet` manifest before selecting implementation targets
1. For code dependency evidence, run:

```bash
bash tools/agent_tools/scan_code_dependencies.sh --changed
```

1. For Python code changes, add function-level dependency evidence:

```bash
python3 tools/agent_tools/helper_function_inventory.py --changed --all-functions --format json
```

   Treat `HELPER_INVENTORY_FILES=0` as scope evidence when the changed Python
   file count is zero. For changed Python files, carry direct caller / callee
   context into the `Change Impact Packet`.

1. Keep code dependency evidence separate from header dependency evidence. Do not merge import/include/source edges with manifest upstream/downstream graph edges.
1. For changed human-authored text files, run:

```bash
python3 tools/agent_tools/check_dependency_headers.py --changed
bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing
bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header
```

1. When dependency edges were added or changed, run:

```bash
bash tools/agent_tools/check_dependency_graph.sh --changed --print-edges
```

1. When repo-wide search may determine a fix surface, run responsibility-based search before text search. Use the result to choose source dirs, candidate paths, and terms; then write bounded `git grep -l` hits and expand them through dependency headers before editing:

```bash
printf '%s\n' "search purpose or user request" > reports/search_query.txt
agent-canon semantic-index context-pack \
  --query-file reports/search_query.txt \
  --max-cells 12 \
  --format text \
  > reports/search_responsibility_context.txt
git grep -l "search phrase" -- <responsibility-scoped dirs> > reports/search_hits.txt
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --search-hits-file reports/search_hits.txt
```

1. Use `dependency_graph.tsv` and `dependency_edit_scope.txt` to list files that need edits or review. Do not close an issue or PR with only raw search hits when dependency-expanded edit scope is available.
1. When a design document introduces implementation-backed claims, DSL or problem-standard-form terms, normalization rules, or parent-document differences, run:

```bash
python3 tools/agent_tools/check_design_doc_claims.py \
  --root . \
  --recursive-depth 3 \
  <design-doc>
```

   Treat `DESIGN_DOC_CLAIMS=fail` as a design evidence gap. Route structural
   claim gaps to `$structure-refactor` after dependency-expanded scope is
   available.

1. When a task changes one requested object/file/finding, or when a parent will
   hand work to a write-capable subagent, produce a structured
   `Change Impact Packet` manifest instead of passing raw hits, raw findings,
   or pasted dependency dumps. Tool outputs stay on disk as JSON/TSV/Markdown
   artifacts; the packet stores paths, counts, object ids, selected excerpts,
   and structured summaries needed for planning. Keep code dependency evidence and header
   dependency evidence as separate sections, then unify them only in the
   planning packet. The packet must include:
   - `requested_target`: `path:start-end:qualname`, file, or finding id
   - `code_dependency_surface`: imports/includes/source edges and function or
     public-entrypoint direct callees/callers that are visible to static
     analysis
   - `header_dependency_surface`: upstream/downstream design, test,
     environment, and workflow edges
   - `search_surface`: `git grep -l` hits and `dependency_edit_scope.txt` paths when
     text search seeded the work
   - `structural_surface`: tool finding packet, priority order, and repair
     slice paths when a checker seeded the work
   - `public_api_exports`: re-export, public import, and generated entrypoint
     surfaces affected by the target
   - `tests_docs_config_log_info_edges`: tests, docs, config, log, and Info
     surfaces that must be edited or reviewed with the code
   - `unknown_dynamic_edges`: JAX/equinox/runtime dispatch or reflection edges
     not proven by static analysis
   - `impact_blocks`: tool-generated blocks grouped by connected dependency
     component, dependency depth, responsibility group, and validation surface;
     each block records `block_id`, root targets, downstream targets,
     evidence artifact paths, `blocked_by`, `parallel_safe`, allowed files,
     validation, and non-goals
   - `scope_candidates`: tool-generated candidate granularities for the same
     impact surface, such as object-level, module-level, responsibility-group
     level, or representative-consumer-plus-root level
   - `selected_scope`: the chosen granularity with objective scores for wave
     count, expected tool reruns, write-conflict risk, token budget, validation
     cost, and semantic risk
   - `repair_batches`: sequential root batches and parallel-safe downstream
     batches derived from `impact_blocks`
   - `subagent_handoff_context`: object-by-object current problem, intended
     change, forbidden semantic delta, validation signal, and output format
1. Do not ask an LLM to re-summarize the full dependency graph by default.
   Read full artifacts only for the current repair batch or when a reviewer
   needs to inspect a disputed edge.
1. Do not ask an LLM to manually partition impact scope by default. Block
   construction is a tool responsibility. The LLM may accept, split, merge, or
   mark a block `review_required`, but it must record the reason and preserve
   the original tool-generated block id.
1. Do not treat node size as fixed. Scope granularity is an optimization
   problem. Prefer the largest block that preserves a clear behavior contract,
   avoids write conflicts, fits the token budget, and can be validated with one
   coherent test/tool surface; shrink the block only when semantic risk,
   ownership, or validation isolation requires it.
1. For Python structural finding packets, generate the mechanical planning
   packet with:

```bash
agent-canon python-structure-hash-scope-plan \
  --input <python-structure-hash-report.json> \
  --dependency-report-dir <dependency-review-dir> \
  --output <change-impact-packet.json>
```

   The output `python_structure_hash_scope_plan.v1` is the default
   `Change Impact Packet` input for refactor planning. Do not ask an LLM to
   hand-partition `impact_blocks`, `scope_candidates`, `selected_scope`, or
   `repair_batches` when this tool can read the structured report and
   dependency artifacts.

1. When reverse-edge migration is the task, add strict bidirectional validation:

```bash
bash tools/agent_tools/check_dependency_graph.sh --changed --print-edges --check-bidirectional
```

1. For full-repo migration inventory, run report-only scan first:

```bash
bash tools/agent_tools/scan_dependency_headers.sh
```

1. For full graph baseline, run:

```bash
bash tools/agent_tools/check_dependency_graph.sh --print-edges
```

1. Treat changed-file header / scan / format failures as fix-now blockers.
1. Treat default graph failures as fix-now blockers because they indicate isolated manifests, self references, or cycles.
1. Do not make Dockerfile or environment files universal anchors. Use the nearest true canon anchor (`AGENTS.md`, `README.md`, directory README, workflow/design doc, tool index, skill guide) unless the file actually depends on Docker, CI, requirements, or runtime configuration.
1. During reverse-edge migration, `--check-bidirectional` failures may be a baseline, but do not call them pass. Record the baseline and confirm the current diff introduced no new old-format header, self reference, missing reverse edge, kind mismatch, or cycle.
1. Put command outputs and any baseline decision in `verification.txt` and `closeout_gate.md`.
