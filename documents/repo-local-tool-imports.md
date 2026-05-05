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

## Preserved As Legacy Provenance

The following tools are retained under `tools/legacy/jax_solver_util/scripts/`
because they are project-specific, stale compared with current AgentCanon, or
need separate review before becoming defaults.

- `create_toml.sh`
- `docker_dependency_validator.py`
- `extract_deps_from_svg.sh`
- `guide.sh`
- `read_conventions.sh`
- `restructure_code_review_skill.py`
- `run_week1_tests.py`
- `setup_week1_env.py`
- `verify_week1.py`
- `view_conventions.sh`
- `security/*`
- repo-local copies of docs, audit, HLO, and Markdown tools

Legacy provenance files are not default CI entrypoints. A future PR may promote
one legacy tool only after it has repo-neutral paths, current dependency
headers, strict static checks, and tests or help-smoke evidence.

## Explicitly Not Overwritten

Current AgentCanon versions were kept for core runtime files such as
`tools/agent_tools/agent_team.py`, `bootstrap_agent_run.py`,
`tools/ci/run_all_checks.sh`, `tools/validation/triplet_validator.py`, and
Markdown tooling that already has newer AgentCanon behavior.
