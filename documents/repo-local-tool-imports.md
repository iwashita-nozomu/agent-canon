<!--
@dependency-start
responsibility Records imported repo-local tools and their canonical disposition.
upstream design tools/README.md defines shared tool families
upstream design result-log-retention-and-visualization.md defines result tooling policy
downstream design tools/README.md lists canonical and legacy tool locations
@dependency-end
-->

# Repo-Local Tool Imports

This document records repo-local tools found during the 2026-05-05 consolidation
pass and how they were handled. Future passes should turn this into a PR
instead of direct updates.

## Source Repositories Checked

- `/mnt/l/workspace/agent-canon`
- `/mnt/l/workspace/experiment_runner`
- `/mnt/l/workspace/jax_solver_util`
- `/mnt/l/workspace/project_template`
- `/mnt/l/workspace/test2`

The main tool growth was in `/mnt/l/workspace/jax_solver_util/scripts/`.

## Promoted To Canonical Tool Families

| Source | Canonical Path | Disposition |
| ------ | -------------- | ----------- |
| `scripts/audit/audit_log_schema.py` | `tools/audit/audit_log_schema.py` | Promoted as portable audit schema support. |
| `scripts/audit/audit_logger.py` | `tools/audit/audit_logger.py` | Promoted as portable audit JSONL writer. |
| `scripts/jsonl_to_md.sh` | `tools/data/jsonl_to_md.py` | Reimplemented as Python CLI for testability. |
| `scripts/hlo/summarize_hlo_jsonl.py` | `tools/hlo/summarize_hlo_jsonl.py` | Promoted as HLO JSONL summary helper. |
| `scripts/tools/create_design_template.py` | `tools/docs/create_design_template.py` | Promoted as design-doc helper. |
| `scripts/tools/find_redundant_designs.py` | `tools/docs/find_redundant_designs.py` | Promoted as document consolidation helper. |
| `scripts/tools/find_similar_designs.py` | `tools/docs/find_similar_designs.py` | Promoted as design similarity helper. |
| `scripts/tools/organize_designs.py` | `tools/docs/organize_designs.py` | Promoted as conservative design organization helper. |
| `scripts/tools/tfidf_similar_docs.py` | `tools/docs/tfidf_similar_docs.py` | Promoted as dependency-free similarity helper. |
| `scripts/read_conventions.sh` and `scripts/view_conventions.sh` | `tools/agent_tools/oop_rule_inventory.py` | Reimplemented as repo-neutral OOP rule inventory instead of project-root convention viewers. |
| `scripts/restructure_code_review_skill.py` | `tools/legacy/jax_solver_util/oop_check_support/restructure_code_review_skill.py` | Reclassified as OOP / review-rule provenance; not promoted because it rewrites one historical skill layout. |
| `vendor/agent-canon/tools/agent_tools/check_algorithm_module_nested_contract.py` | `tools/agent_tools/check_algorithm_module_nested_contract.py` | Promoted from jax_solver_util submodule diff as a repo-neutral algorithm module ownership checker. |
| `vendor/agent-canon/tools/experiments/update_latest_result.py` | `tools/experiments/update_latest_result.py` | Promoted from jax_solver_util submodule diff as a latest-result pointer helper. |
| `vendor/agent-canon/tools/agent_tools/analyze_oop_readability.py` local diff | `tools/agent_tools/analyze_oop_readability.py` | Promoted algorithm-protocol contract-class exemption so intentional value contracts are not reported as thin classes. |
| `vendor/agent-canon/tools/agent_tools/analyze_oop_readability.py` follow-up local diff | `tools/agent_tools/analyze_oop_readability.py` | Promoted public-boundary filtering and algorithm config factory exemptions. |
| `vendor/agent-canon/tools/agent_tools/check_algorithm_module_nested_contract.py` follow-up local diff | `tools/agent_tools/check_algorithm_module_nested_contract.py` | Promoted explicit summary return type so the checker avoids `Any`. |
| `vendor/agent-canon/tools/experiments/update_latest_result.py` follow-up local diff | `tools/experiments/update_latest_result.py` | Promoted deterministic nanosecond timestamp tie-break for latest-result selection. |
| `vendor/agent-canon/tools/__init__.py` and `tools/experiments/__init__.py` | `tools/__init__.py`, `tools/experiments/__init__.py` | Promoted package markers used by shared tool tests. |

## Preserved As Legacy Provenance

The following tools are retained under `tools/legacy/jax_solver_util/scripts/`
because they are project-specific, stale compared with current AgentCanon, or
need separate review before becoming defaults.

- `create_toml.sh`
- `docker_dependency_validator.py`
- `extract_deps_from_svg.sh`
- `guide.sh`
- `run_week1_tests.py`
- `setup_week1_env.py`
- `verify_week1.py`
- `security/*`
- repo-local copies of docs, audit, HLO, and Markdown tools

OOP / convention-check legacy support now lives under
`tools/legacy/jax_solver_util/oop_check_support/` and is represented by the
canonical `tools/agent_tools/oop_rule_inventory.py` inventory tool.

Legacy provenance files are not default CI entrypoints. A future PR may promote
one legacy tool only after it has repo-neutral paths, current dependency
headers, strict static checks, and tests or help-smoke evidence.

## Explicitly Not Overwritten

Current AgentCanon versions were kept for core runtime files such as
`tools/agent_tools/agent_team.py`, `bootstrap_agent_run.py`,
`tools/ci/run_all_checks.sh`, `tools/validation/triplet_validator.py`, and
Markdown tooling that already has newer AgentCanon behavior.

## Additional Local Preference Captured

jax_solver_util had a local AgentCanon memory note requiring OOP readability,
public surface, and nested-contract checks in implementation/experiment paths.
The shared canon now keeps the nested-contract checker and runs it from
`tools/ci/run_all_checks.sh` when a repo has a `python/` tree.

The jax_solver_util local diff that excluded `python/jax_util`,
`python/tests`, and several tool families from `check_static_any.py` was not
promoted because it is repo-specific and weakens the shared explicit-`Any`
policy.
