<!--
@dependency-start
contract issue
responsibility Tracks deterministic GitHub Issue status lifecycle reconciliation and private runtime skill integration.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
downstream design ../../agents/internal-routines/github-status-lifecycle.md canonical lifecycle, evidence, failure, and readback owner
downstream design ../../agents/skills/pr-processing.md public GitHub publication caller
downstream design ../../documents/operations/issue-label-taxonomy.toml machine-readable label owner
downstream implementation ../../.agents/skills/_github-status-lifecycle/SKILL.md private runtime discovery shim
downstream implementation ../../tools/agent_tools/github_status_lifecycle.py transport and reconciler
@dependency-end
-->

# [GitHub運用] Issue status lifecycle skill を追加する

issue_id: AC-20260815-github-status-lifecycle-skill
status: in_progress
source: user
severity: S2
problem: repository-changing task の GitHub Issue status label 遷移、証拠コメント、競合・部分失敗時の扱いが単一 owner を持たず、相反 label や追跡不能な handoff を生じ得る。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/719
done: private runtime skill と injectable GitHub adapter が status を desired-state へ収束させ、Issue から branch、commit、PR、validation、remaining verification を追跡できる。
affected_surfaces: agents/internal-routines/github-status-lifecycle.md, .agents/skills/_github-status-lifecycle/SKILL.md, agents/skills/pr-processing.md, documents/operations/issue-label-taxonomy.toml, tools/agent_tools/github_status_lifecycle.py, tests/agent_tools/test_github_status_lifecycle.py
edit_scope: owner-bounded
required_action: status lifecycle の正本、TOML taxonomy、private runtime shim、transport/reconciler、FakeRunner tests を追加し、pr-processing の publication boundary から責務を重複せず委譲する。
close_condition: implementation PR が merge され、focused tests、semantic responsibility、dependency headers、Markdown、runtime alignment、issue mirror、git diff check が pass している。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/719

## Current snapshot

- Baseline: `main@cdde13b18e4d0c667d9e04b95a77ddd3e1152266`
- Active branch: `fix/719-status-lifecycle-followup-20260815`
- Root cause: prior merge supplied policy text only; no testable GitHub adapter, evidence create/readback, or per-label drift protocol existed.
- Canonical label owner: `documents/operations/issue-label-taxonomy.toml` (`in progress`, `ready for review`, `need verification`; declared legacy aliases only).
- Implementation owner: `tools/agent_tools/github_status_lifecycle.py`, reusing `github_publish.Runner` without extending `issue_sync`.

## Ownership decision

The public skill surface is unchanged. GitHub status mutation remains inside the
`pr-processing` publication boundary:

- canonical semantic owner: `agents/internal-routines/github-status-lifecycle.md`
- machine-readable taxonomy: `documents/operations/issue-label-taxonomy.toml`
- transport/reconciler: `tools/agent_tools/github_status_lifecycle.py`
- runtime shim: `.agents/skills/_github-status-lifecycle/SKILL.md`
- public caller: `agents/skills/pr-processing.md`
- durable mirror: this issue file

`pr-processing` owns target resolution, fresh initial reads, write authority,
transport invocation, and publication readback. The routine owns classification,
evidence identity, transition ordering, observable race stops, and the exact
success predicate. The adapter has no lifecycle state machine and does not use
full-label replacement.

## State model

The TOML mapping supplies names; the routine never hard-codes repository labels.

| Lifecycle state | Required canonical labels | Forbidden managed labels | Admission |
| --- | --- | --- | --- |
| `active` | `in progress` | `ready for review`, `need verification` | work started and handoff/validation is incomplete or failed |
| `review-ready` | `ready for review` | `in progress`, `need verification` | handoff ready and selected validation complete |
| `review-ready-unverified` | `ready for review`, `need verification` | `in progress` | handoff ready plus complete external-unavailability gap |

`need verification` is never used alone. An implementation failure, failing
validation, unknown result, or unconfirmed defect remains `active`/blocked.

## Reconciliation and concurrency contract

The adapter reads the complete Issue, paginated comments, and paginated label
catalog through separate `gh` token arrays. It normalizes nested `--slurp`
pages, deduplicates/sorts comment IDs, and encodes DELETE label paths with
`quote(label, safe="")`. It never parses Markdown for taxonomy and never calls
`issue_sync`.

Evidence is bound to canonical payload, exact PR identity, taxonomy digest, and
preflight source snapshot digest. A stable operation identity excludes the mutable
source snapshot, so a retry after label mutation reuses one historical payload
instead of creating a duplicate. A same marker or operation identity with another
payload is `evidence_conflict`; multiple matching comments are
`evidence_duplicate`; a lost POST is reread once and becomes
`evidence_readback_unavailable` if zero/ambiguous. Historical comments are never
automatically edited or deleted, and no CAS guarantee is claimed.

For labels, `M = canonical ∪ declared aliases`, `O = observed ∩ M`,
`remove = O - D`, and `add = D - O`. Evidence publication is followed by a
complete-label equality check. Every single-label add/remove is preceded and
followed by a complete-label readback. Observable drift stops with exact state;
partial mutation reports the completed prefix and does not rollback. The final
predicate requires desired canonical labels, absent declared aliases, preserved
unrelated labels, and exactly one evidence payload.

Every typed failure includes `code_owner` and `responsibility_scope`; transport
(`github-api-transport`) and lifecycle (`status-label-lifecycle`) failures stay
separate.

## Implementation and validation evidence

- `GhStatusAdapter` uses the exact `github_publish.Runner`, `CommandResult`, and
  `subprocess_runner` boundary.
- `tests/agent_tools/test_github_status_lifecycle.py` uses only FakeRunner and
  covers taxonomy/catalog, pagination, URL encoding, evidence races, drift/ABA
  limitation, partial failure, final predicate, and owner/scope output.
- No public catalog entry, label creation path, Project field workflow, Issue
  close, PR approval/merge, or second lifecycle state machine is added.

Validation route:

```bash
python3 -m pytest -q tests/agent_tools/test_github_status_lifecycle.py
python3 tools/agent_tools/check_semantic_responsibility_contract.py --root . --instance <run-local>/semantic_responsibility_contract.toml
python3 tools/agent_tools/check_dependency_headers.py --changed
python3 tools/agent_tools/check_agent_runtime_alignment.py
tools/bin/agent-canon docs check agents/internal-routines/github-status-lifecycle.md agents/skills/pr-processing.md .agents/skills/_github-status-lifecycle/SKILL.md documents/operations/issue-label-taxonomy.md documents/operations/issue-label-taxonomy.toml issues/open/AC-20260815-github-status-lifecycle-skill.md
python3 tools/agent_tools/issue_sync.py --root . --repo iwashita-nozomu/agent-canon --github-check
git diff --check
```

## Non-goals

- GitHub Projects custom fields
- label creation, rename, or color changes
- Issue close, PR approval, or merge automation
- repository-specific names hard-coded outside the repository TOML owner
- duplicated PR queue, authority, publication, or lifecycle policy
