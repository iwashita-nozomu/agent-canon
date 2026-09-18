# AgentCanon Tool Guide

<!--
@dependency-start
contract reference
responsibility Routes readers to standalone AgentCanon tools without recreating Host or parent-repository execution paths.
upstream design ../runtime/bootstrap-runtime.md shared tool runtime and Host adapter boundary
upstream implementation ../../bootstrap.sh sole Host lifecycle entrypoint
upstream implementation ../../tools/catalog.yaml machine-readable tool inventory
downstream design ../../agents/canonical/CLI_ENTRYPOINTS.md typed command examples
@dependency-end
-->

## Execution boundary

AgentCanon tools run in the shared non-root tool container created by
`bootstrap.sh`. The AgentCanon source and selected project targets are mounted
read-only unless an exact mutation capability is registered. Python/Rust
caches, logs, reports, receipts, Cargo targets, and temporary files remain in
the explicit external runtime root.

Project builds, tests, GPU execution, and application dependencies remain in
the project-owned execution environment. The tool container does not execute
project commands.

## Public command routes

- `bootstrap.sh ... tool run --root <target> <catalog-id> -- <args...>` runs a
  parity-verified catalog entry.
- `bootstrap.sh ... exec --root <target> -- <argv...>` retains argv-only
  compatibility for AgentCanon tools that are still classified as
  `legacy-route`.
- `bootstrap.sh ... eval collect` and `eval sync` own evaluation collection and
  publication to `agent-canon-log`.
- `bootstrap.sh ... codex prepare|launch` owns the isolated runtime-local Codex
  home.

There is no `tools/agent-canon` alias, vendor checkout, source projection,
global Python executable, or Host Cargo fallback.

## Tool families

| Family | Canonical owner |
| --- | --- |
| typed dispatch and route selection | `tools/runtime/dispatch/tool_dispatch.py`, `tools/catalog.yaml` |
| source/dependency analysis | `search.py`, `source_dependency_graph.py`, `lsp_code_analysis.py` |
| runtime artifact boundary | `runtime_artifacts.py`, `bootstrap_runtime.py` |
| eval and archive | `run_accumulated_agent_evals.py`, `runtime_log_archive_git.py` |
| docs and structure | Rust `agent-canon docs`, `repo_structure_contract.py`, `check_design_doc_claims.py` |
| Skill loading | `bootstrap.sh ... tool run --root <registered-project> skill-document-reader -- ...` via the persistent AgentCanon tool container (bounded UTF-8 chunks and EOF admission) |
| review and closeout | `review_dispatch.py`, `task_close.py`, canonical workflow |

Each tool that writes requires an external runtime/output root or an explicit
target mutation capability. Read-only tools must not create a source-local
fallback when that capability is absent.

## Guides by task

Use the matching guide below when its owning task applies. This is a reader
index, not a list of tools to run or a second public-tool registry.
[tool-docs.toml](tool-docs.toml) owns tool-to-document mappings and surface
classification; [the tool catalog](../../tools/catalog.yaml) and the existing
execution owner determine the available command route. A link here does not
promote an internal tool, require a check, or revalidate a historical record.

| Reader task | Guides |
| --- | --- |
| Select a task route or inspect the CLI | [Task routing](route.md), [AgentCanon CLI and docs formatting](agent-canon.md) |
| Search and inspect source | [Search coordination](search-coordination.md), [LSP analysis](lsp_code_analysis.md), [Semantic index](semantic_index.md), [Provider comparison reports](semantic_provider_html_report.md) |
| Plan dependency or repository changes | [Dependency diff summary](git_dependency_diff_summary.md), [Dependency module changes](dependency_module_change.md), [Repository topic checkouts](repository_topic_clone.md), [Conflict preservation](conflict_preservation.md) |
| Inspect repository structure and design evidence | [Repository structure](repo_structure_contract.md), [Path-risk classification](classify_path_risk.md), [Design claims](check_design_doc_claims.md), [Semantic responsibility contracts](check_semantic_responsibility_contract.md) |
| Review object contracts and test design | [Python readability](oop/python/readability.md), [Python rule inventory](oop/python/rule_inventory.md), [C++ readability](oop/cpp/readability.md), [C++ rule inventory](oop/cpp/rule_inventory.md), [Test design](test_design.md) |
| Extract, analyze, or visualize documents | [DOCX extraction](extract_docx.md), [Prose reasoning graph](prose_reasoning_graph.md), [Dependency graph rendering](render_dependency_manifest_graph.md), [Visualization contract](visualization_contract.md) |
| Plan and check formal proofs | [Formal proof](formal_proof.md), [Lean capabilities](lean_capability_matrix.md), [Lean proof environment](lean_proof_env.md), [Recursive proof search](lean_recursive_proof_search.md), [Tool proof coverage](tool_proof_coverage.md) |
| Trace source and intermediate representations into proofs | [C++ source IR](cpp_source_canonical_ir.md), [C++ templates to Lean](cpp_template_to_lean.md), [JIT canonical IR](jit_canonical_ir.md), [StableHLO value closure](stablehlo_value_closure.md), [Operational IR to Lean](operational_ir_to_lean.md), [JIT IR to Lean](jit_ir_to_lean.md), [Proof trace alignment](check_proof_trace_alignment.md) |
| Publish changes and share artifacts | [GitHub publication](github_publish.md), [Wiki publication](wiki_publish.md), [HTML artifact access](html_artifact_access.md) |
| Compose or export consumer instructions | [Entrypoint composition](entrypoint_composer.md), [Static seed export](export_static_seed.md) |
| Maintain tool dependencies and imports | [Dependency and license inventory](dependency-tools-and-licenses.md), [Repository-local imports](repo-local-tool-imports.md) |

Keep guide additions, moves, and removals connected through the existing
[reference maintenance rule](../rule/directory-structure.md#参照と到達性).

## Skill reader output

`skill-document-reader` の本文取得は `chunk`、見出し一覧は `index` を使います。
必要な状態確認に選択する `admit` は、JSON/textとも参照節の位置・EOFとready/lockedだけを返し、
`owner_sections[].text` を再出力しません。本文が必要なcallerは `chunk` の `next_offset` を辿って取得します。
状態の位置情報は各節の最終chunkのもので、未読部分を含む全文ではありません。
`admit` はファイル側の読取状態であり、モデルが内容を読んだ証拠でも、新たな必須の読了gateでもありません。
本文・権限・失敗の意味を状態確認や短い要約で代用せず、既存の読取・実行境界を維持します。

## Validation

Validate the selected owner rather than every tool family:

```bash
python3 tools/runtime/manifest/tool_catalog.py
python3 tools/validation/semantic/convention/check_convention_compliance.py
python3 tools/agent/skills/skill_tool_commands.py check
python3 tools/validation/documentation/checks/check_bootstrap_docs.py --root .
```

Container behavior is validated with `bootstrap.sh install -> start -> target
add -> tool/eval -> stop -> uninstall` and exact resource absence readback.
Do not use `docker system prune`.
