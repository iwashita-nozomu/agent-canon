<!--
@dependency-start
contract issue
responsibility Tracks the migration of root Agent instruction procedures to canonical Skills and owner surfaces.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
downstream design ../../documents/design/entrypoint-owner-map.md structural target contract
downstream design ../../AGENTS.md standalone source-tree entrypoint
downstream design ../../ROOT_AGENTS.md explicit live-integration entrypoint
downstream design ../../agents/skills/comprehensive-development.md implementation-basis owner consumer
downstream implementation ../../tools/agent_tools/convention_compliance_contracts.toml canonical marker ownership projection
downstream implementation ../../tools/agent_tools/check_entrypoint_owner_map.py structural verifier
downstream implementation ../../tests/agent_tools/test_check_entrypoint_owner_map.py focused regression
@dependency-end
-->

# [Agent runtime] Root entrypointをowner mapへ縮退し実装根拠をSkillへ移す

issue_id: AC-20260816-agents-owner-map-responsibility
status: resolved
source: user
severity: S2
problem: `AGENTS.md` / `ROOT_AGENTS.md` がreader mapを宣言しながらSkill、Git、update、validation、closeoutの詳細手順を再所有し、別名見出しで手順を再導入できる。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/738
done: root entrypointをidentity・reader map・owner mapへ限定し、contract-complete implementationと数理・engineering basisをSkillへ移し、構造checkerで再流入を拒否する。
affected_surfaces: AGENTS.md, ROOT_AGENTS.md, documents/design/entrypoint-owner-map.md, agents/skills/comprehensive-development.md, tools/agent_tools/convention_compliance_contracts.toml, tools/agent_tools/check_entrypoint_owner_map.py, tests/agent_tools/test_check_entrypoint_owner_map.py, .github/workflows/entrypoint-owner-map.yml
edit_scope: owner-bounded
required_action: 詳細手順をcanonical ownerへ委譲し、entrypoint grammar、implementation basis、focused regression、remote validationを同一changeで閉じる。
close_condition: PRがmergeされ、entrypoint checker、focused tests、runtime alignment、convention、workflow validationがpassし、Issueにbranch・PR・validation evidenceが残る。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/738
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/739

## Resolution snapshot

- Initial baseline: `main@fd947707d2c987776f80886ea490213fb024476a`.
- Implementation branch: `refactor/738-agents-owner-map`.
- Pre-merge current main: `01b4aebcf050ce599385b9bd5dccfa9848f6d9db`; its one-commit drift changed only Issue form, label taxonomy documentation, and standalone template files outside PR #739's write set.
- Synchronized implementation head: `8aa6de4dea513b68a5e0f99a8563c4915f1c1c67`.
- Final implementation merge: PR #739 / `69152df78272398dad3729c7e789ae426c7e8f34`.
- Closeout baseline: `main@69152df78272398dad3729c7e789ae426c7e8f34`.
- Closeout branch: `docs/738-close-durable-record`.
- `project_template/AGENTS.md` remains a self-contained static consumer entrypoint outside the implementation write set.
- General engineering precedence remains owned by `documents/conventions/software-engineering-principles.md`; cross-surface implementation basis remains owned by `agents/skills/comprehensive-development.md`.

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
| operational marker ownership | `convention_compliance_contracts.toml` with no root entrypoint surfaces |
| structural regression | `check_entrypoint_owner_map.py` and focused tests |

## Engineering basis

The checker verifies a grammar rather than an arbitrary byte limit. For each entrypoint `e`, the level-2 heading sequence must equal the declared allowed sequence, procedural syntax must be absent, and required responsibility rows must resolve to canonical owners. Convention marker surfaces must also remain disjoint from the root entrypoint set. This closes renamed-section and marker-contract drift without creating a natural-language policy classifier.

Implementation selection uses the smallest contract-complete owning unit, not the smallest diff. Material algorithm, numerical, architecture, performance, resource, concurrency, or reliability decisions require a basis appropriate to the claim and a validation oracle. Missing basis remains an explicit blocker rather than a temporary success path.

## Validation evidence

- `python3 tools/agent_tools/check_entrypoint_owner_map.py --root . --format json` — pass.
- `python3 -m unittest tests.agent_tools.test_check_entrypoint_owner_map -v` — 8/8 pass.
- marker manifest parse and root-surface disjoint readback — pass.
- AgentCanon Static Gates run #2193 on synchronized head — success; `contracts-static` and `workflow-container-static` succeeded, while `rust-static` and `eval-static` were skipped by the changed-path classifier.
- Entrypoint Owner Map run #3 — success.
- Issue Mirror run #2960 — success.
- Agent Runtime Dashboard run #3026 — success.
- Final pre-merge review readback: zero review submissions, zero review threads, and zero PR conversation comments.
- Main-relative final implementation diff remained the original nine files at `+897/-657` after current-main synchronization.
- Remaining verification: none.

## Acceptance criteria

- root entrypoints contain only identity, reader map, always-on boundary, owner map, task entry routing, and validation routing.
- Skill or workflow procedures are not copied into root entrypoints.
- cross-surface implementation packets distinguish contract-complete scope from responsibility-incomplete minimum implementations.
- material mechanism decisions carry mathematical, domain, or engineering basis, alternatives, and a validation oracle.
- renamed operational headings, nested procedure headings, fenced commands, numbered procedures, command bullets, missing owner rows, and root operational marker surfaces fail focused regression.
- default static `project_template` remains source-free and self-contained.
- GitHub Issue #738 retains branch, PR, validation, current-main reconciliation, and remaining-verification evidence.

## Closeout evidence

- PR #739 was merged only after the current-main drift was incorporated into the issue branch and all protected checks reran successfully on exact head `8aa6de4dea513b68a5e0f99a8563c4915f1c1c67`.
- Merge commit `69152df78272398dad3729c7e789ae426c7e8f34` retains the thin owner-map boundary, the contract-complete implementation-basis contract, and the static default `project_template` boundary.
- The GitHub Issue received final merge, review, validation, and label-reconciliation evidence before this durable record was closed.
- This closeout changes only the durable issue location and resolution metadata; it does not alter runtime behavior, entrypoint grammar, implementation policy, checker logic, workflows, or taxonomy.
