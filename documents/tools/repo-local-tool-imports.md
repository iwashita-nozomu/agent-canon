<!--
@dependency-start
contract reference
responsibility Records imported repo-local tools and their canonical disposition.
upstream design ../../tools/README.md defines shared tool families
upstream design ../experiments/result-log-retention-and-visualization.md defines result tooling policy
downstream design ../../tools/README.md lists canonical tool locations
downstream implementation ../../tools/runtime/manifest/tool_catalog.py validates retired legacy catalog status
@dependency-end
-->

# Repo-Local Tool Imports

This document records repo-local tools found during the 2026-05-05 consolidation
pass and how they were handled. Future passes should turn this into a PR
instead of direct updates.

## Reader Map

- Owns the historical ledger for repo-local tool imports and their canonical
  disposition.
- Main path: Source Repositories Checked, Ledger Versus Catalog, Promoted To
  Canonical Tool Families, Retired Legacy Imports, Explicitly Not Overwritten,
  and Additional Local Preference Captured.
- Read this when auditing how local scripts were promoted, retired, or left in
  source repositories.
- Boundary: the live machine-readable tool registry is `tools/catalog.yaml`;
  this file is historical disposition evidence.

## Source Repositories Checked

- `/mnt/l/workspace/agent-canon`
- `/mnt/l/workspace/experiment_runner`
- `/mnt/l/workspace/jax_solver_util`
- `/mnt/l/workspace/project_template`
- `/mnt/l/workspace/test2`

The main tool growth was in `/mnt/l/workspace/jax_solver_util/scripts/`.

## Ledger Versus Catalog

This document is the historical import-disposition ledger. The live
machine-readable AgentCanon tool registry is `tools/catalog.yaml`, validated by
`tool_catalog.py` and cross-checked by `tool_drift.py`.
When a tool is promoted, left in the source repository, deleted, or converted
into a compatibility wrapper, update both this ledger and the corresponding
catalog entry. The catalog entry must also classify the imported tool with
`audience` and `placement` so a promoted user entrypoint is not mixed with a
skill-only helper, workflow gate, support library, or compatibility wrapper.
AgentCanon no longer keeps `tools/legacy/` provenance paths; update-route
legacy subtree wording is unrelated to tool import disposition.

## Promoted To Canonical Tool Families

| Source | Canonical Path | Disposition |
| ------ | -------------- | ----------- |
| `scripts/audit/audit_log_schema.py` | `tools/audit/logging/audit_log_schema.py` | Promoted as portable audit schema support. |
| `scripts/audit/audit_logger.py` | `tools/audit/logging/audit_logger.py` | Promoted as portable audit JSONL writer. |
| `scripts/jsonl_to_md.sh` | `tools/analysis/documents/formatting/jsonl_to_md.py` | Reimplemented as Python CLI for testability. |
| `scripts/hlo/summarize_hlo_jsonl.py` | `tools/analysis/hlo/summarization/summarize_hlo_jsonl.py` | Promoted as HLO JSONL summary helper. |
| `scripts/tools/create_design_template.py` | `tools/validation/documentation/authoring/create_design_template.py` | Promoted as design-doc helper. |
| `scripts/tools/find_redundant_designs.py` | `tools/analysis/documents/analysis/find_redundant_designs.py` | Promoted as an external-runtime document consolidation helper; deletion requires an explicit mutation capability. |
| `scripts/tools/find_similar_designs.py` | `tools/analysis/documents/analysis/find_similar_designs.py` | Promoted as an external-runtime design similarity helper. |
| `scripts/tools/organize_designs.py` | `tools/validation/documentation/authoring/organize_designs.py` | Promoted as a read-only organization planner; source apply requires an explicit mutation capability. |
| `scripts/tools/tfidf_similar_docs.py` | `tools/analysis/documents/analysis/tfidf_similar_docs.py` | Promoted as dependency-free similarity helper. |
| `scripts/read_conventions.sh` and `scripts/view_conventions.sh` | `tools/validation/code/oop/python/rule_inventory.py`, `tools/validation/code/oop/cpp/rule_inventory.py` | Reimplemented as repo-neutral, language-specific OOP rule inventories instead of project-root convention viewers. |
| `scripts/restructure_code_review_skill.py` | Source repository only | Not promoted because it rewrites one historical skill layout. AgentCanon legacy tool storage is retired. |
| `vendor/agent-canon/tools/experiments/artifacts/update_latest_result.py` | `tools/experiments/artifacts/update_latest_result.py` | Promoted from jax_solver_util submodule diff as a latest-result pointer helper. |
| OOP readability local diff | `tools/validation/code/oop/shared/readability_core.py` with `tools/validation/code/oop/python/readability.py` and `tools/validation/code/oop/cpp/readability.py` entrypoints | Promoted algorithm-protocol contract-class exemption so intentional value contracts are not reported as thin classes. |
| OOP readability follow-up local diff | `tools/validation/code/oop/shared/readability_core.py` with `tools/validation/code/oop/python/readability.py` and `tools/validation/code/oop/cpp/readability.py` entrypoints | Promoted public-boundary filtering and algorithm config factory exemptions. |
| `vendor/agent-canon/tools/experiments/artifacts/update_latest_result.py` follow-up local diff | `tools/experiments/artifacts/update_latest_result.py` | Promoted deterministic nanosecond timestamp tie-break for latest-result selection. |
| `vendor/agent-canon/tools/__init__.py` and `tools/experiments/__init__.py` | `tools/__init__.py`, `tools/experiments/__init__.py` | Promoted package markers used by shared tool tests. |

## Retired Legacy Imports

The following tools were historically discovered under
`/mnt/l/workspace/jax_solver_util/scripts/` but are no longer retained inside
AgentCanon. They are project-specific, stale compared with current AgentCanon,
or need separate review before promotion. Keep them in the source repository or
promote them through a focused PR; do not restore `tools/legacy/`.

- `create_toml.sh`
- `docker_dependency_validator.py`
- `extract_deps_from_svg.sh`
- `guide.sh`
- `run_week1_tests.py`
- `setup_week1_env.py`
- `verify_week1.py`
- `security/*`
- repo-local copies of docs, audit, HLO, and Markdown tools

OOP / convention-check support is now represented by the canonical
`tools/oop/python/*` and `tools/oop/cpp/*` entrypoints. A future PR may promote
one retired tool only after it has repo-neutral paths, current dependency
headers, strict static checks, catalog coverage, same-named tool docs when
needed, and tests or help-smoke evidence.

## Explicitly Not Overwritten

Current AgentCanon versions were kept for core runtime files such as
`tools/agent/orchestration/agent_team.py`, `bootstrap_agent_run.py`,
`tools/validation/ci/runners/run_all_checks.sh`, `tools/validation/documentation/checks/triplet_validator.py`, and
Markdown tooling that already has newer AgentCanon behavior.

## Additional Local Preference Captured

jax_solver_util had a local AgentCanon memory note requiring OOP readability
and algorithm-contract checks in implementation/experiment paths. The shared
canon now keeps the single Rust algorithm-contract checker and runs it from
`tools/validation/ci/runners/run_all_checks.sh` when a repo has a `python/` tree.

The jax_solver_util local diff that excluded `python/jax_util`,
`python/tests`, and several tool families from `check_static_any.py` was not
promoted because it is repo-specific and weakens the shared explicit-`Any`
policy.
