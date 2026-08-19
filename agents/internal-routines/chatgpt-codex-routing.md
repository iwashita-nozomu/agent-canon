# ChatGPT / Codex Request Routing

<!--
@dependency-start
contract agent-runtime
responsibility Owns the ChatGPT conversation-closure versus Codex workspace-execution decision and typed handoff packet.
upstream design ../skills/README.md public and private skill visibility boundary
upstream design ../../documents/design/request-intent-and-update-relation.md explicit read, write, and request-update semantics
downstream design ../../AGENTS.md standalone repository entrypoint consumer
downstream design ../../ROOT_AGENTS.md live-integration entrypoint consumer
downstream design ../skills/agent-orchestration.md Codex-side workflow and owner routing consumer
downstream implementation ../../.agents/skills/_chatgpt-codex-routing/SKILL.md private runtime discovery adapter
downstream implementation ../../tools/agent_tools/chatgpt_codex_routing.py deterministic decision owner
downstream implementation ../../tests/agent_tools/test_chatgpt_codex_routing.py finite-relation and monotonicity validation
@dependency-end
-->

## Purpose

ユーザー要求を、ChatGPT の会話内で完結させるか、Codex で repository / workspace
を観測・変更・検証しながら進めるかに分けます。この routine は入口の modality
だけを所有し、Codex 内の workflow、skill、owner、review、subagent、validation
selection は `agent-orchestration` に渡します。

判定根拠は task の難しさ、長さ、推定時間、file 数、agent 数ではありません。
requested deliverable の正しさが workspace execution に依存するかだけを使います。

## Visibility And Invocation

これは public Codex workflow ではなく、root entrypoint から呼ばれる internal routine
です。runtime activation が必要な場合だけ
`.agents/skills/_chatgpt-codex-routing/SKILL.md` を使います。先頭 underscore は private
surface を表し、public skill catalog と public dependency DAG は増やしません。

request modality は Codex public skill selection より前に決まるため、この gate を
`catalog.yaml` に登録して Codex 内 routing の後ろへ置いてはいけません。

## Explicit Fact Model

request の requested deliverable から、次の boolean facts を解釈します。

| Symbol | Canonical fact | True when |
| --- | --- | --- |
| `E` | `explicit_codex_execution` | user が Codex / coding workspace での実行を明示した |
| `M` | `workspace_or_repository_mutation` | file、configuration、issue、branch、commit、PR、または workspace state の変更が deliverable に含まれる |
| `R` | `repository_local_or_uncommitted_state_required` | correctness が local checkout、dirty state、untracked file、worktree、または未 push state の観測に依存する |
| `X` | `command_test_build_benchmark_runtime_observation_required` | command、test、build、benchmark、runtime、reproduction の観測が claim の oracle である |
| `V` | `iterative_inspect_edit_validate_loop_required` | inspect、edit、validate の feedback loop 自体が deliverable に必要である |
| `D` | `durable_repository_delivery_required` | repository file、commit、branch、Issue comment、または PR として追跡可能な成果物が必要である |

`explicit_chat_only` は実行必要条件ではなく、workspace execution を禁止する user
constraint です。

LLM は自然言語をこの有限 fact set に解釈します。keyword score、complexity score、
estimated effort、file count を fact に追加しません。曖昧な自然言語 classifier を
correctness owner にせず、抽出後の decision は pure function に渡します。

## Monotone Decision Relation

Codex 必要条件は disjunction 一つです。

```text
codex_required := E ∨ M ∨ R ∨ X ∨ V ∨ D
```

通常の route は次です。

```text
route := codex   if codex_required
route := chatgpt otherwise
```

この relation は包含順序に対して単調です。execution fact を追加しても
`codex -> chatgpt` へ戻りません。このため、別々の score threshold、task-size
heuristic、例外優先順位を持つ必要がありません。

`explicit_chat_only ∧ codex_required` のときは user constraint を優先して mutation を
行わず、route は `chatgpt`、handoff は `none` とします。ただし execution dependency
を隠さず、`explicit_chat_only_conflict`、必要だった Codex reason、blocked scope、
validation oracle を packet に残します。これは verified execution result ではなく
advisory-only result です。

## ChatGPT Route

次の要求は、それだけでは Codex 条件になりません。

- 説明、相談、比較、brainstorming、設計論点の整理
- user が提示した text / code / data の要約、翻訳、書き換え、推論
- web search、connected source、GitHub connector 等による read-only 調査
- repository-local command や mutation を必要としない計算、文章、表、図の作成

read-only 調査でも、結論の正しさが local/uncommitted state、command reproduction、
または selected repository validation に依存するなら `R` または `X` を true にします。
remote source を読むこと自体は Codex 条件ではありません。

ChatGPT route は会話内で結果を返し、`agent-orchestration`、repository bootstrap、branch、
mutation、test command を開始しません。

## Codex Route

次の requested deliverable は対応する execution fact を持ちます。

- source、docs、configuration、workflow、test の変更: `M`
- local checkout、dirty worktree、uncommitted artifact の診断: `R`
- test、build、lint、benchmark、runtime、reproduction の実行結果: `X`
- inspect / edit / re-run を収束まで繰り返す debugging: `V`
- Issue、branch、commit、PR まで追跡可能にする delivery: `D`
- user が Codex での実行を明示: `E`

Codex route は `handoff=agent-orchestration` とし、`codex_scope` と
`validation_oracle` が `none` でないことを要求します。入口 gate はどの workflow や
skill を使うかを決めません。

## Mixed Requests

一つの request に説明と実装が含まれる場合、requested deliverable の一部でも
`codex_required` なら overall route は `codex` です。packet は次を分離します。

- `chatgpt_scope`: intent framing、前提整理、read-only reasoning
- `codex_scope`: workspace で実行する mutation / observation / delivery
- `validation_oracle`: Codex execution が立証すべき property

説明部分だけを返して implementation 要求を消したり、実装部分だけを始めて requested
rationale を落としたりしません。

## Canonical Output Packet

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

Execution reason order is fixed as follows so equivalent facts produce one packet.

1. `explicit_codex_execution`
2. `workspace_or_repository_mutation`
3. `repository_local_or_uncommitted_state_required`
4. `command_test_build_benchmark_runtime_observation_required`
5. `iterative_inspect_edit_validate_loop_required`
6. `durable_repository_delivery_required`

Conversation closure uses `conversation_closure` or `explicit_chat_only`.
Chat-only conflict prepends `explicit_chat_only_conflict` to the true execution reasons.

## Operation

1. requested deliverable を一文で固定します。
2. `E, M, R, X, V, D` と `explicit_chat_only` を boolean として抽出します。
3. Codex fact が一つでも true の場合、具体的な `codex_scope` と
   `validation_oracle` を固定します。
4. `python3 tools/agent_tools/chatgpt_codex_routing.py --input <packet.json>` で
   deterministic packet を生成します。
5. `route=chatgpt` は会話内で閉じます。`route=codex` だけを
   `agent-orchestration` へ渡します。

同じ request に対して route を再判定するのは、requested deliverable または execution
facts が変わった場合だけです。Codex 内の owner/skill/review decision をこの routine へ
逆流させません。

## Validation

Focused invariant set:

- ChatGPT-only examples close without handoff.
- Each execution fact independently routes to Codex.
- Mixed facts preserve canonical reason order.
- Explicit chat-only conflict performs no handoff and retains the blocked dependency.
- Codex packets reject missing execution scope or validation oracle.
- Unknown fields and non-boolean facts fail closed.
- Every superset of a Codex-routed execution fact set remains Codex-routed.

Canonical command:

```bash
python3 -m unittest -v tests/agent_tools/test_chatgpt_codex_routing.py
```

## Non-Goals

- ChatGPT と Codex の能力、品質、速度、費用の ranking
- task complexity、推定工数、file 数による score routing
- natural-language keyword classifier の追加
- Codex workflow / public skill / subagent routing の第二実装
- web / connector read-only access の一律 Codex 化
- project template への live AgentCanon dependency または policy copy
