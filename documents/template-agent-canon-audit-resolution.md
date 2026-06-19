<!--
@dependency-start
contract reference
responsibility Records resolution policy for the 2026-05-16 Template / AgentCanon 500 item audit.
upstream design ./runtime-profiles-and-check-matrix.md runtime profile and validation routing policy
upstream design ./SHARED_RUNTIME_SURFACES.md shared runtime surface ownership policy
upstream design ./agent-canon-parent-repo-latest-checklist.md parent repo latest-state checklist
downstream design ../README.md AgentCanon repository overview
downstream design ../agents/canonical/CODEX_WORKFLOW.md Codex execution workflow
downstream design ./agent-canon-parent-repo-latest-checklist.md parent repository update checklist
@dependency-end
-->

# Template / AgentCanon Audit Resolution

This ledger resolves `template_agent_canon_audit_500_issues.md` by common cause.
The audit is treated as a triage input, not as a command to remove every surface.
Resolution means one of:

- `profiled`: the surface remains available but is no longer described as always
  active.
- `risk_based`: the gate remains available but is selected by changed path and
  risk class.
- `compatibility_only`: legacy wording remains only in compatibility docs or
  tool output.
- `canon_source`: edits must be made in `vendor/agent-canon/` or standalone
  AgentCanon, not in root views.
- `higher_priority_override`: the audit recommendation conflicts with current
  repository runtime requirements and is intentionally not applied.

## Coverage

| Audit IDs | Resolution |
| --- | --- |
| I-001-I-010 | `profiled`: agent, Codex, MCP, memory, and shared tool views are installed capability, not project runtime requirements. |
| I-011-I-020 | `profiled`: C++, experiments, reports, references, Docker, editor, server, and notebook surfaces are optional profiles. |
| I-021-I-030 | `risk_based`: validation entrypoints are selected by changed path; `make ci` remains full confidence, not mandatory for every small edit. |
| I-031-I-040 | `profiled`: observability, profiling, GitHub CLI, root repair, and copy sync belong to environment, GitHub, or maintenance profiles. |
| I-041-I-050 | `profiled`: README and Quick Start use minimal required reads plus conditional references. |
| I-051-I-060 | `compatibility_only`: subtree, snapshot, pull, and push routes are legacy compatibility routes, not normal submodule-first work. |
| I-061-I-080 | `risk_based`: AgentCanon update and PR evidence are required for shared-canon or pin changes, not unrelated project work. |
| I-081-I-100 | `compatibility_only`: start-repository and update docs are GitHub/submodule-first; subtree details are appendix or migration-only. |
| I-101-I-110 | `retired`: repo MCP inventory was removed from current runtime policy; local AgentCanon CLI tools own repo checks. |
| I-111-I-140 | `profiled`: Codex goals and token modes are Codex overlays; reusable profiles belong to user config, not project runtime requirements. |
| I-141-I-150 | `profiled`: monitoring tokens, connectors, and MCP no-edit details are emitted only when the related profile is active. |
| I-151-I-170 | `profiled`: public skills are routing shortcuts; task family and path/risk decide activation. |
| I-171-I-200 | `risk_based`: subagents and reviewer separation are mandatory for high-risk/comprehensive work and optional for trivial parent-direct edits. |
| I-201-I-230 | `risk_based`: closeout artifacts, review agents, and full-repo validation scale with risk class and changed surface. |
| I-231-I-250 | `risk_based`: eval, learning, run bundle, and artifact gates are required for prompt/workflow/large tasks, not every small edit. |
| I-251-I-270 | `risk_based`: dependency manifests and graph scans apply to canonical docs, design/workflow/tool docs, and changed dependency surfaces. |
| I-271-I-300 | `risk_based`: convention gates and mechanical checks are subchecks selected by source, gate, workflow, prompt, and changed path. |
| I-301-I-330 | `profiled`: optional tools move to maintenance, experiment, docs, or skill/vendor profiles; catalog can mark optional or maintainer-only tools. |
| I-331-I-350 | `compatibility_only`: retired tool names and docs helpers are removed from primary guidance or kept only in historical ledgers. |
| I-351-I-390 | `profiled`: Docker, Python environment, C++, and experiment checks are profile-specific. |
| I-391-I-420 | `profiled`: Makefile, GitHub automation, and PR authority surfaces are selected by repo capability and task scope. |
| I-421-I-450 | `profiled`: multi-runtime mirrors, GitHub checks, remote assumptions, and PR automation are runtime or GitHub profiles. |
| I-451-I-500 | `profiled`: historical ledgers, memory/notes, search expansion, generated results, and strict canonical-doc rules are scoped to maintenance, learning, refactor, or audit tasks. |

## Non-Negotiable Exceptions

- Local AgentCanon CLI checks stay mandatory when selected by the current
  runtime profile.
- AgentCanon-owned shared surfaces remain source-controlled under
  `vendor/agent-canon/` or standalone AgentCanon.
- Hook, eval, skill, and tool logs that are intentionally append-only evidence
  are not discarded merely because they are generated.
- Compatibility docs may mention subtree or snapshot routes only as migration
  appendices.
