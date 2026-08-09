<!--
@dependency-start
contract design
responsibility Documents the compact request, update-overlay, positive-rule, and cleanup correspondence flow.
upstream design README.md design index and reader route.
upstream design ../rule/README.md document naming, placement, and ownership rules.
upstream design ../../documents/codex/prompt-skill-evaluation-checklist.md evaluator scenarios and validation route.
downstream design ../../agents/skills/agent-orchestration.md consumes request clauses, write gate, and routing contract.
downstream design ../../agents/skills/codex-task-workflow.md consumes task packet, workflow, and validation contract.
downstream design ../../agents/COMMUNICATION_PROTOCOL.md consumes active context, handoff, write-scope, and transport contract.
downstream design ../../agents/canonical/CODEX_SUBAGENTS.md consumes reuse, parallel handoff, and lifecycle clauses.
downstream design ../../agents/skills/worktree-health.md consumes worktree and scratch cleanup clauses.
downstream design ../../agents/skills/dependency-module-change.md consumes dependency-clone cleanup clause.
downstream design ../../agents/internal-routines/design-implementation-correspondence.md owns correspondence and related-document closure.
downstream implementation ../../tools/agent_tools/bootstrap_agent_run.py materializes task packets.
downstream implementation ../../tools/agent_tools/task_close.py materializes closeout receipts.
downstream implementation ../../tools/agent_tools/dependency_module_change.py executes dependency-clone cleanup.
downstream implementation ../../tools/agent_tools/runtime_log_archive_git.py archives and checks retained run-bundle reports.
downstream implementation ../../tools/agent_tools/generated_artifact_guard.py reads generated-artifact cleanup status.
downstream implementation ../../tools/agent_tools/report_artifact_checks.py classifies report placement and transient state.
downstream implementation ../../tools/agent_tools/agent_team.py materializes lifecycle cleanup and terminal ToolCall receipts.
downstream design ../../ROOT_AGENTS.md canonical root reader projection.
downstream design ../../AGENTS.md AgentCanon root-view projection.
@dependency-end
-->

# Request Intent と進行中 Update の compact design

## Reader Map / Owner Boundaries

この note は既存 owner の操作、状態、完了 evidence を一つの flow と trace に接続します。 `agents/skills/agent-orchestration.md`
入力と packet の表現は既存 owner の route に保持します。 <!-- evidence: `agents/skills/agent-orchestration.md` -->

| responsibility | canonical owner | この note の境界 |
| --- | --- | --- |
| request clause、authority、owner、write set、route | `agents/skills/agent-orchestration.md` | semantic decision を所有し、task packet へ渡す |
| intake、task packet、workflow、validation | `agents/skills/codex-task-workflow.md`、`tools/agent_tools/bootstrap_agent_run.py` | request clauses と active work state を保持する |
| active context、handoff、transport | `agents/COMMUNICATION_PROTOCOL.md` | packet/capsule と write scope を運ぶ |
| agent reuse、必要な並列 handoff、descendant close | `agents/canonical/CODEX_SUBAGENTS.md` | 同じ context の再利用と独立 scope の handoff を所有する |
| dependency/topic clone cleanup | `agents/skills/dependency-module-change.md`、`tools/agent_tools/dependency_module_change.py` | reconstructibility-gated cleanup を実行し `CLEANUP` receipt を返す |
| run bundle temporary state / retention | `tools/agent_tools/runtime_log_archive_git.py`、`documents/runtime/runtime-log-archive.md` | archive、sync、check-clean の retention receipt を返す |
| task/run lifecycle cleanup | `agents/canonical/CODEX_SUBAGENTS.md`、`tools/agent_tools/task_close.py`、`tools/agent_tools/agent_team.py` | CleanupProof、G6、terminal close_agent receipt を検証・materializeする |
| generated report / local graph-cache readback | `tools/agent_tools/generated_artifact_guard.py`、`tools/agent_tools/report_artifact_checks.py`、`tools/agent_tools/graph_client.py` | 既存 guard/producer の状態を読み、owner-bounded cleanup write set の根拠を返す |
| worktree health / merge-readback | `agents/skills/worktree-health.md` | health、scope、linked worktree、clean status の readback だけを返す |
| design read、clause fingerprint、implementation correspondence | `agents/internal-routines/design-implementation-correspondence.md` | design-to-implementation trace を所有する |
| root reader projection | `ROOT_AGENTS.md`（正本）、`AGENTS.md`（root view） | 同じ positive contract とこの note の route を投影する |

### Related Document Closure reference

`DIC-010` と `agents/internal-routines/design-implementation-correspondence.md#Related-Document-Closure`
がこの note の Related Document Closure 参照です。traversal、source-packet closure、worker
read-before-handoff、changed-path reverse readback の意味は DIC が所有します。 <!-- evidence: `agents/internal-routines/design-implementation-correspondence.md` -->

## Compact Flow / Positive Completion Contract

各規約は、実行する操作、到達する状態、完了を示す証拠を肯定形で記述します。制約は
対応する操作の precondition、適用境界、または正規 alternative route として配置します。 <!-- evidence: `ROOT_AGENTS.md` -->

### 質問と明示 write clause

1. `agent-orchestration` がユーザー入力から既存 task packet の request clauses と <!-- evidence: `agents/skills/agent-orchestration.md` -->
   evidence route を形成します。入力は既存 owner の request relation として保持し、質問に必要な read scope と <!-- evidence: `agents/skills/codex-task-workflow.md` -->
   write に必要な明示 clause をそれぞれの既存 packet field へ接続します。 `agents/skills/agent-orchestration.md`
2. 質問の precondition は read scope と根拠の route です。操作は根拠を読み、必要な結論を `agents/COMMUNICATION_PROTOCOL.md`
   返し、既存 write scope と active context を保持したまま回答状態を完了します。 <!-- evidence: `agents/COMMUNICATION_PROTOCOL.md` -->
3. 明示 write clause の precondition は対象、operation、owner、write set、acceptance <!-- evidence: `agents/skills/agent-orchestration.md` -->
   evidence です。操作はその clause だけを該当 owner の write route と handoff packet に <!-- evidence: `agents/skills/codex-task-workflow.md` -->
   handoff packet に `agents/COMMUNICATION_PROTOCOL.md` 接続します。回答の要求は read route で完了し、複合入力では write clause の
   部分だけが write authority を持ちます。 <!-- evidence: `agents/skills/agent-orchestration.md` -->
4. 追加または変更された request clause は、作用を materialize する前に同じ existing
   explicit-write-clause gate を通ります。gate の完了後、作用は goal、artifact、order、handoff `agents/skills/agent-orchestration.md`
   の sparse delta へ投影され、authority は既存 gate の owner、write set、acceptance evidence `agents/skills/agent-orchestration.md`
   に保持されます。 <!-- evidence: `agents/skills/agent-orchestration.md` -->

### 進行中 update の overlay

1. `COMMUNICATION_PROTOCOL` の active context、final objective、artifact identity、 <!-- evidence: `agents/COMMUNICATION_PROTOCOL.md` -->
   dependency order、agent context を base として既存 task packet に追加入力を重ねます。 `agents/COMMUNICATION_PROTOCOL.md`
2. overlay の操作は、変化した goal、artifact、order、handoff の差分だけを sparse delta <!-- evidence: `agents/COMMUNICATION_PROTOCOL.md` -->
   として既存 packet に更新します。既存 context と artifact は既存 refs を使い、必要な field を保持します。 <!-- evidence: `agents/COMMUNICATION_PROTOCOL.md` -->
   chat summary の再生成を完了条件にせず、既存 packet の readback を完了 evidence にします。 `agents/COMMUNICATION_PROTOCOL.md`
3. owner、write set、dependency order が互換な差分は既存 agent context へ handoff します。 `agents/canonical/CODEX_SUBAGENTS.md`
   disjoint write scope と依存順の evidence が揃う差分だけを独立 owner へ並列 handoff `agents/canonical/CODEX_SUBAGENTS.md`
   します。追加入力は既存 packet と active context の関係として保持し、既存 owner の表現を使います。 <!-- evidence: `agents/canonical/CODEX_SUBAGENTS.md` -->
4. gate を通った update の作用は goal、artifact、order、handoff の各 sparse delta として
   既存 packet へ投影されます。独立 scope の authority は既存 owner/write-set route から `agents/COMMUNICATION_PROTOCOL.md`
   読み、追加 field として materialize しません。 `agents/COMMUNICATION_PROTOCOL.md`
5. update の完了 evidence は、変更された request clause と4つの delta の packet readback、
   および再利用または必要並列の owner handoff evidence です。 `agents/COMMUNICATION_PROTOCOL.md`

### Integration と cleanup

completed integration の merge/readback と tree/remote evidence が揃った直後に、既存 owner
executors を dispatch し、final closeout は各 receipt を統合します。 `agents/internal-routines/design-implementation-correspondence.md`

| operation | existing executor | receipt |
| --- | --- | --- |
| dependency/topic clone cleanup | `python3 tools/agent_tools/dependency_module_change.py cleanup --apply` with the existing same-command authority and reconstructibility readback | `CLEANUP module=... action=removed` または owner の hold/readback evidence |
| run bundle temporary state / retention | `python3 tools/agent_tools/runtime_log_archive_git.py archive-agent-report` → `sync` → `check-clean` | `RUNTIME_LOG_ARCHIVE_AGENT_REPORT=pass`、`RUNTIME_LOG_ARCHIVE_SYNC=pass`、`RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=pass` |
| generated report roots | artifact owner operation followed by `python3 tools/agent_tools/generated_artifact_guard.py --root .` | `GENERATED_ARTIFACT_GUARD=pass` と `report_artifact_checks.py` placement readback |
| generated local graph/cache | current graph producer `agent-canon graph build`; general delete executor は current tools に存在しない | artifact-owner cleanup operation を今回の design write set として選定し、owner receipt を追加する |
| completed agent and descendants | `task_close.py` / `agent_team.py` lifecycle materializer under `agents/canonical/CODEX_SUBAGENTS.md` | `CleanupProof` → `G6` → terminal `close_agent` ToolCall、descendants-closed、reservations-released receipt |

merge/readback → dependency cleanup receipt → scratch cleanup または typed retention receipt →
`CODEX_SUBAGENTS` `CleanupProof` → `G6` → terminal `close_agent` ToolCall の順で実行し、
receipt は既存 closeout packet へ read-back します。 `agents/internal-routines/design-implementation-correspondence.md`
`worktree-health` はこの sequence の health/readback evidence を返し、executor を所有しません。

## Failure / Readback Semantics

- 根拠が揃う質問は回答操作へ進み、根拠が不足する質問は既存 task packet の evidence <!-- evidence: `agents/skills/codex-task-workflow.md` -->
  route と next action を更新します。 `agents/skills/codex-task-workflow.md`
- owner、write set、acceptance の join が揃う write clause は owner handoff へ進み、 `agents/skills/agent-orchestration.md`
  design sufficiency が不足する場合は `agent-orchestration` の design route へ戻ります。
- update の dependency order または active context が変化する場合は、protocol の <!-- evidence: `agents/COMMUNICATION_PROTOCOL.md` -->
  safe checkpoint で既存 packet を再読し、差分 handoff または必要並列を選択します。
- merge/readback evidence が揃う場合は dependency cleanup receipt、scratch cleanup または
  typed retention receipt、CleanupProof、G6、terminal close_agent receipt が順に closeout
  packet へ入ります。 `tools/agent_tools/task_close.py`

## Validation / Performance Observation

design read/fingerprint、task packet readback、既存 runtime alignment、既存 docs/dependency `agents/internal-routines/design-implementation-correspondence.md`
checks がこの flow の validation evidence です。 <!-- evidence: `agents/internal-routines/design-implementation-correspondence.md` -->

性能は `documents/codex/prompt-skill-evaluation-checklist.md` の validation route を使い、fresh `gpt-5.4-mini` skill evaluator の次の3 scenariosで <!-- evidence: `documents/codex/prompt-skill-evaluation-checklist.md` -->
観測します。

| scenario | expected observation |
| --- | --- |
| 質問 | 根拠を読んだ回答が返り、repository state が読み取り状態で完了する `agents/COMMUNICATION_PROTOCOL.md` |
| 複合追加入力 | 既存 context を再利用し、disjoint な必要 scope だけが並列 handoff になる `agents/canonical/CODEX_SUBAGENTS.md` |
| merge/readback | completed integration の readback 後に既存 cleanup route が実行される `agents/skills/worktree-health.md` |

## Evidence And Assumption Ledger

| scope | evidence / owner |
| --- | --- |
| current owner flow | `agents/skills/agent-orchestration.md`; `agents/skills/codex-task-workflow.md`; `agents/COMMUNICATION_PROTOCOL.md` |
| current lifecycle route | `agents/canonical/CODEX_SUBAGENTS.md`; `agents/skills/worktree-health.md`; `tools/agent_tools/task_close.py` |
| correspondence and closure | `agents/internal-routines/design-implementation-correspondence.md`; `documents/design/README.md` |
| planned evaluator observation | `documents/codex/prompt-skill-evaluation-checklist.md` |

## Design-To-Implementation Trace

| clause | current/planned owner and files | completion evidence / reverse rule |
| --- | --- | --- |
| `QWA-01` | `agents/skills/agent-orchestration.md`; `agents/skills/codex-task-workflow.md`; `agents/COMMUNICATION_PROTOCOL.md`; `ROOT_AGENTS.md`; `AGENTS.md` | read evidence、回答、unchanged write scope の packet readback。質問回答経路の変更はこの clause と既存 owner packet を先に読む |
| `QWA-02` | `agents/skills/agent-orchestration.md`; `tools/agent_tools/bootstrap_agent_run.py`; `agents/COMMUNICATION_PROTOCOL.md` | explicit write clause gate を通った request clause だけが owner/write set/acceptance handoff に接続される |
| `UPD-01` | `agents/skills/agent-orchestration.md`; `agents/skills/codex-task-workflow.md`; `agents/COMMUNICATION_PROTOCOL.md` | gate-approved effect が goal/artifact/order/handoff の各 sparse delta として既存 packet に更新される |
| `UPD-02` | `agents/COMMUNICATION_PROTOCOL.md`; `agents/canonical/CODEX_SUBAGENTS.md` | compatible context は reuse、disjoint scope は必要並列 handoff。追加入力の routing 変更はこの clause と active packet を先に読む |
| `LIFE-01` | `agents/skills/dependency-module-change.md`; `tools/agent_tools/dependency_module_change.py` | merge/readback 直後に dependency cleanup が dispatch され、`CLEANUP` receipt が read-back される |
| `LIFE-02` | `tools/agent_tools/runtime_log_archive_git.py`; `documents/runtime/runtime-log-archive.md`; `tools/agent_tools/generated_artifact_guard.py`; `tools/agent_tools/report_artifact_checks.py` | run bundle は archive/sync/check-clean、generated roots は owner operation/guard readback の existing route へ接続される |
| `LIFE-03` | `agents/canonical/CODEX_SUBAGENTS.md`; `tools/agent_tools/task_close.py`; `tools/agent_tools/agent_team.py` | dependency receipt → scratch/retention receipt → CleanupProof → G6 → terminal close_agent ToolCall の実 sequence が read-back される |
| `LIFE-04` | `tools/agent_tools/graph_client.py`; `documents/design/dependency-manifest-design.md`; `tools/agent_tools/generated_artifact_guard.py` | general graph/cache delete executor の欠落を artifact-owner cleanup write set として明示し、guard/producer を cleanup executor として扱わない |
| `STYLE-01` | `ROOT_AGENTS.md`; `AGENTS.md`; `agents/internal-routines/design-implementation-correspondence.md` | operation、state、completion evidence の肯定形と、対応 precondition/alternative route が design fingerprint と root projection に現れる |
| `DOC-01` | `agents/internal-routines/design-implementation-correspondence.md` `DIC-010` | Related Document Closure の traversal、packet closure、worker先読み、changed-path reverse readback は DIC の clause/ref だけで接続される |

### Reverse correspondence rule

request intake、質問回答、write handoff、update overlay、context reuse/parallel handoff、 <!-- evidence: `agents/internal-routines/design-implementation-correspondence.md` -->
merge/readback、cleanup、または規約文面を変更する実装は、上表の clause、該当 owner file、
既存 packet/readback evidence を実装前に結合します。clause、owner、evidence のいずれかが
不足する場合は DIC の design read/review route を完了してから handoff を再開します。 `agents/internal-routines/design-implementation-correspondence.md`

## Planned Design Review Evidence

この note の review は、DIC trace、`documents/codex/prompt-skill-evaluation-checklist.md` の
3 evaluator scenarios、docs/dependency/runtime alignment の
readbackで完了します。
