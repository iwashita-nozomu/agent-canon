<!--
@dependency-start
contract issue
responsibility Tracks the single ChatGPT conversation-closure versus Codex workspace-execution routing owner.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
downstream design ../../agents/internal-routines/chatgpt-codex-routing.md canonical fact model and handoff policy
downstream design ../../AGENTS.md standalone entrypoint consumer
downstream design ../../ROOT_AGENTS.md live-integration entrypoint consumer
downstream implementation ../../.agents/skills/_chatgpt-codex-routing/SKILL.md private runtime discovery adapter
downstream implementation ../../tools/agent_tools/chatgpt_codex_routing.py deterministic decision owner
downstream implementation ../../tests/agent_tools/test_chatgpt_codex_routing.py finite relation and monotonicity validation
@dependency-end
-->

# [Routing skill] ChatGPT会話完結とCodex実行の判定を単一の境界にする

issue_id: AC-20260819-chatgpt-codex-routing
status: resolved
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/779
source: user
severity: S2
problem: ChatGPT で完結する request と Codex workspace execution を必要とする request の判定が repository-only orchestration に埋め込まれ、独立した単調 predicate、有限 reason code、typed handoff を持たない。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/778
done: requested deliverable の workspace execution dependency だけから ChatGPT / Codex を決め、Codex route のみを agent-orchestration へ渡す private skill、pure tool、finite regression matrix が存在する。
affected_surfaces: AGENTS.md, ROOT_AGENTS.md, agents/internal-routines/README.md, agents/internal-routines/chatgpt-codex-routing.md, .agents/skills/_chatgpt-codex-routing/SKILL.md, tools/agent_tools/chatgpt_codex_routing.py, tests/agent_tools/test_chatgpt_codex_routing.py
edit_scope: owner-bounded
required_action: request modality を internal routine に分離し、root entrypoint、private shim、deterministic decision function、table-driven and exhaustive monotonicity tests を同じ変更で接続する。
close_condition: focused relation tests、entrypoint owner-map、dependency headers、Markdown、runtime alignment、Issue mirror、PR checks が pass し、Issue から branch、commit、PR、validation、remaining verification を追跡できる。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/778

## Baseline

- AgentCanon source: `main@bafcd812a214df0885d6475482d2ce1146542bb6`
- project template: `main@45d99b4d0fe8510c55db7cd13af37d46f86506f9`
- work branch: `agent/chatgpt-codex-routing-778`

`project_template` は self-contained static consumer であり、`.codex/` snapshot の更新は
explicit template-maintainer import に限定されます。今回の正本変更を template-local
policy として複製せず、live dependency や runtime updater も追加しません。

## Confirmed occurrence locations

### Embedded modality decision

```text
repository: iwashita-nozomu/agent-canon
snapshot: bafcd812a214df0885d6475482d2ce1146542bb6
path: agents/skills/agent-orchestration.md
locator: Decision Order item 1
observation: repo-changing execution と routing-only/advisory を分けるが、ChatGPT/Codex entry gate、finite reason code、mixed-request projection を独立 owner として持たない。
```

### Codex execution transport already has an owner

```text
repository: iwashita-nozomu/agent-canon
snapshot: bafcd812a214df0885d6475482d2ce1146542bb6
path: agents/skills/codex-task-workflow.md
locator: Purpose, Boundary, Stages
observation: repository task の implementation、validation、closeout を所有し、通常の相談・説明 turn は対象外である。入口 modality をこの workflow に重複させるべきではない。
```

### Public skill surface is post-admission Codex discovery

```text
repository: iwashita-nozomu/agent-canon
snapshot: bafcd812a214df0885d6475482d2ce1146542bb6
paths: agents/skills/README.md, agents/skills/catalog.yaml
observation: public skill は Codex auto-discovery surface で、runtime-only skill は underscore lane と internal routine に置く。Codex admission gate を public catalog に登録すると呼出順が循環する。
```

### Template is not a second policy owner

```text
repository: iwashita-nozomu/project_template
snapshot: 45d99b4d0fe8510c55db7cd13af37d46f86506f9
paths: AGENTS.md, agent-canon-static-seed.json
observation: template は source-free static seed を追跡し、runtime AgentCanon synchronization を行わない。
```

## Root cause

`request modality` と `Codex-side repository orchestration` が同じ skill の decision order
に畳み込まれていました。そのため ChatGPT entrypoint から再利用できる owner がなく、
作業量、難易度、file 数等の非本質的 heuristic が判定へ混入し得ます。

必要なのは task classifier ではなく、requested deliverable の correctness が workspace
execution に依存するかを表す finite boolean relation です。

## Canonical decision model

```text
E = explicit_codex_execution
M = workspace_or_repository_mutation
R = repository_local_or_uncommitted_state_required
X = command_test_build_benchmark_runtime_observation_required
V = iterative_inspect_edit_validate_loop_required
D = durable_repository_delivery_required

codex_required := E ∨ M ∨ R ∨ X ∨ V ∨ D
route := codex if codex_required else chatgpt
```

この predicate は execution-fact set の包含順序に対して単調です。true fact を追加しても
`codex -> chatgpt` へ戻りません。complexity、推定時間、task length、file count、agent
count は入力にしません。

`explicit_chat_only ∧ codex_required` は user constraint を優先して `route=chatgpt`、
`handoff=none` とし、必要だった execution scope と validation oracle を blocked dependency
として残します。mutation や verified execution claim は行いません。

## Ownership decision

新しい owner:

- canonical routine: `agents/internal-routines/chatgpt-codex-routing.md`
- private runtime skill: `.agents/skills/_chatgpt-codex-routing/SKILL.md`
- pure decision function / CLI: `tools/agent_tools/chatgpt_codex_routing.py`
- finite and exhaustive regression: `tests/agent_tools/test_chatgpt_codex_routing.py`
- root consumers: `AGENTS.md`, `ROOT_AGENTS.md`

既存 owner に残す責務:

- `agent-orchestration`: Codex admission 後の workflow、skill、owner、review、subagent、entrypoint selection
- `codex-task-workflow`: repository execution、implementation、validation、closeout
- `task-routing`: Codex 内の skill/tool owner selection
- `project_template`: static snapshot provenance。判定 algebra の第二コピーを持たない

public skill catalog、public dependency DAG、第二 workflow family、natural-language keyword
classifier は追加しません。

## Canonical output packet

```text
route: chatgpt | codex
reason_codes: finite ordered set
requested_deliverable: one sentence
chatgpt_scope: advisory/read-only framing scope
codex_scope: workspace execution scope or none
validation_oracle: required execution evidence or none
handoff: none | agent-orchestration
blocked_dependency: none | explicit description
```

## Validation evidence

Focused local validation against the new pure owner:

```text
python3 -m unittest -v tests/agent_tools/test_chatgpt_codex_routing.py
Ran 8 tests in 0.005s
OK
```

Covered invariants:

- conversation-only explanation, summary, translation, supplied-material reasoning, and read-only web/connector research close in ChatGPT
- every execution fact independently routes to Codex
- mixed facts preserve canonical reason order
- explicit chat-only conflict returns advisory-only without handoff
- Codex packet requires concrete execution scope and validation oracle
- unknown classifier state and non-boolean facts fail closed
- exhaustive 64-state subset/superset relation proves route monotonicity
- mapping output remains exact and JSON-compatible

Repository-wide validation and GitHub Actions readback are pending branch publication.

## Acceptance criteria

- [x] ChatGPT / Codex 判定の canonical owner が一つだけ存在する。
- [x] 判定が `E ∨ M ∨ R ∨ X ∨ V ∨ D` の単調 predicate として説明・実装される。
- [x] complexity、file count、推定時間、task length を route 条件にしない。
- [x] explanation、summary、translation、supplied-material reasoning、read-only web/connector research が ChatGPT route になる。
- [x] repository edit、local/uncommitted state inspection、command/test/build/benchmark、iterative debug、branch/commit/PR delivery が Codex route になる。
- [x] mixed request は Codex route になり、ChatGPT framing と Codex execution scope が分離される。
- [x] explicit chat-only と execution-dependent deliverable の conflict は mutation せず typed blocked dependency を返す。
- [x] root entrypoint は Codex route のみを `agent-orchestration` へ渡し、判定 algebra を重複しない。
- [x] `codex-task-workflow` と `task-routing` の既存責務を変更しない。
- [x] table-driven tests が ChatGPT、Codex、mixed、chat-only conflict、input failure、monotonicity を閉じる。
- [ ] entrypoint owner-map、dependency headers、Markdown、runtime alignment、Issue mirror が pass する。
- [x] project_template は static consumer のままで、template-local routing policy を追加しない。
- [ ] Issue から commit、PR、remote validation、remaining verification を追跡できる。

## Non-goals

- ChatGPT または Codex の能力、品質、速度、費用の score 化
- task complexity や推定工数での route selection
- Codex 内 workflow / skill / subagent routing の再実装
- web / connector の read-only 利用の一律 Codex 化
- template への live AgentCanon dependency、runtime updater、第二 policy owner
- natural-language keyword classifier を correctness owner にすること
