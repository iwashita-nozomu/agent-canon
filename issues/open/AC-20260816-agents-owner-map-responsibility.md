<!--
@dependency-start
contract issue
responsibility Tracks the migration of root Agent instruction procedures to canonical Skills and owner surfaces.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
downstream design ../../documents/design/entrypoint-owner-map.md structural target contract
downstream design ../../AGENTS.md standalone source-tree entrypoint
downstream design ../../ROOT_AGENTS.md explicit live-integration entrypoint
downstream design ../../agents/skills/comprehensive-development.md implementation-basis owner consumer
downstream implementation ../../tools/agent_tools/check_entrypoint_owner_map.py structural verifier
downstream implementation ../../tests/agent_tools/test_check_entrypoint_owner_map.py focused regression
@dependency-end
-->

# [Agent runtime] Root entrypointをowner mapへ縮退し実装根拠をSkillへ移す

issue_id: AC-20260816-agents-owner-map-responsibility
status: in_progress
source: user
severity: S2
problem: `AGENTS.md` / `ROOT_AGENTS.md` がreader mapを宣言しながらSkill、Git、update、validation、closeoutの詳細手順を再所有し、別名見出しで手順を再導入できる。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/738
done: root entrypointをidentity・reader map・owner mapへ限定し、contract-complete implementationと数理・engineering basisをSkillへ移し、構造checkerで再流入を拒否する。
affected_surfaces: AGENTS.md, ROOT_AGENTS.md, documents/design/entrypoint-owner-map.md, agents/skills/comprehensive-development.md, tools/agent_tools/check_entrypoint_owner_map.py, tests/agent_tools/test_check_entrypoint_owner_map.py, .github/workflows/entrypoint-owner-map.yml
edit_scope: owner-bounded
required_action: 詳細手順をcanonical ownerへ委譲し、entrypoint grammar、implementation basis、focused regression、remote validationを同一changeで閉じる。
close_condition: PRがmergeされ、entrypoint checker、focused tests、runtime alignment、convention、workflow validationがpassし、Issueにbranch・PR・validation evidenceが残る。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/738

## Current snapshot

- Baseline: `main@fd947707d2c987776f80886ea490213fb024476a`.
- Active branch: `refactor/738-agents-owner-map`.
- `AGENTS.md`: 13,217 bytes at baseline.
- `ROOT_AGENTS.md`: 30,099 bytes at baseline.
- `project_template/AGENTS.md`: 851-byte self-contained static consumer entrypoint; it remains outside this write set.
- Existing engineering principle owner: `documents/conventions/software-engineering-principles.md`.
- Existing implementation consumer: `agents/skills/comprehensive-development.md`.

## Root cause

The prior delegation check rejected a fixed list of historical heading names. It did not define the allowed information architecture of a root entrypoint, so the same procedures could return under renamed sections. At the same time, implementation sufficiency was projected into always-loaded root prose instead of being consumed by the selected implementation and review Skills.

## Target ownership

| Responsibility | Canonical owner |
| --- | --- |
| root identity and first reader route | `AGENTS.md` / `ROOT_AGENTS.md` |
| entrypoint grammar and live/static boundary | `documents/design/entrypoint-owner-map.md` |
| general engineering precedence | `documents/conventions/software-engineering-principles.md` |
| cross-surface implementation-basis packet | `agents/skills/comprehensive-development.md` |
| structure, Git, update, subagent, validation, closeout detail | existing task-specific Skills and canonical workflow owners |
| structural regression | `check_entrypoint_owner_map.py` and focused tests |

## Engineering basis

The checker verifies a grammar rather than an arbitrary byte limit. For each entrypoint `e`, the level-2 heading sequence must equal the declared allowed sequence, procedural syntax must be absent, and required responsibility rows must resolve to canonical owners. This closes renamed-section drift without creating a natural-language policy classifier.

Implementation selection uses the smallest contract-complete owning unit, not the smallest diff. Material algorithm, numerical, architecture, performance, resource, concurrency, or reliability decisions require a basis appropriate to the claim and a validation oracle. Missing basis remains an explicit blocker rather than a temporary success path.

## Validation plan

- `python3 tools/agent_tools/check_entrypoint_owner_map.py --root . --format json`
- `python3 -m unittest tests.agent_tools.test_check_entrypoint_owner_map -v`
- `python3 tools/agent_tools/check_agent_runtime_alignment.py`
- `python3 tools/agent_tools/check_convention_compliance.py --root . --format json`
- `python3 tools/ci/check_github_workflows.py`
- `python3 tools/agent_tools/check_dependency_headers.py --root .`
- `python3 tools/agent_tools/issue_sync.py --root . --repo iwashita-nozomu/agent-canon --github-check`

## Acceptance criteria

- root entrypoints contain only identity, reader map, always-on boundary, owner map, task entry routing, and validation routing.
- Skill or workflow procedures are not copied into root entrypoints.
- cross-surface implementation packets distinguish contract-complete scope from responsibility-incomplete minimum implementations.
- material mechanism decisions carry mathematical, domain, or engineering basis, alternatives, and a validation oracle.
- renamed operational headings, nested procedure headings, fenced commands, numbered procedures, command bullets, and missing owner rows fail focused regression.
- default static `project_template` remains source-free and self-contained.
- GitHub Issue #738 retains status, branch, PR, validation, and remaining verification evidence.
