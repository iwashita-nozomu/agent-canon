# subagent-bootstrap
<!--
@dependency-start
contract skill
responsibility Documents subagent-bootstrap for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../COMMUNICATION_PROTOCOL.md defines pre-edit tool rejection handoff fields
upstream design ../internal-routines/subagent-startup.md owns private subagent startup route labels
@dependency-end
-->


## Reader Map

- Purpose: create run bundles and bounded subagent handoffs without losing role,
  write-scope, validation, and review evidence.
- Section path: Purpose, Use When, and Core References introduce the route;
  Standard Command contains the bootstrap commands and handoff rules;
  Subagent Return Investigation covers missing or stalled subagent returns.
- Use when: a task needs specialist delegation, reviewer/implementer separation,
  explicit wave records, or write-capable handoff packets.
- Boundary: this skill owns launch mechanics and evidence; workflow family
  selection stays with `agent-orchestration` and role behavior stays with
  `.codex/agents/*.toml`.

## Purpose

specialist delegation が必要な task で、run bundle、役割分担、write-scope を崩さずに起動します。
この skill は launch mechanics の正本であり、workflow family の選定や prompt /
config policy の第二の正本にはしません。

## Use When

- run artifact を残したい
- specialist を使う
- reviewer / implementer の責務を分けたい
- 計画レビュー agent、詳細設計レビュー agent、文書通読レビュー agent を分けたい
- `/goal` 確定前に read-only subagent、または明示許可待ちの handoff plan で goal draft、repo survey、first-slice plan を固めたい
- prompt、routing、subagent-config drift の修正前に dedicated prompt-audit subagent を挟みたい
- repo-changing implementation / patch / doc-edit work で、parent が
  orchestrator / integrator に徹し、write-capable subagent handoff を既定 route
  にする必要がある

## Core References

- `agents/TASK_WORKFLOWS.md`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `agents/internal-routines/subagent-startup.md`
- `tools/agent_tools/bootstrap_agent_run.py`

## Standard Command

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "repo-changing task" \
  --task-id T1 \
  --owner "codex" \
  --workspace-root "$PWD"
```

研究・実験つき変更:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "research-backed change" \
  --task-id T4 \
  --owner "codex" \
  --workspace-root "$PWD"
```

環境変更:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "platform or environment change" \
  --task-id T8 \
  --owner "codex" \
  --workspace-root "$PWD"
```

学術文章:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "academic writing task" \
  --task-id T10 \
  --owner "codex" \
  --workspace-root "$PWD"
```

包括的開発:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```

repo-changing task では、`--task-id` を使って task catalog の default specialist と default review pack をそのまま有効化します。
handoff / capsule fields の正本は `agents/COMMUNICATION_PROTOCOL.md` です。この skill は launch timing、role selection、wave ledger、authorization、closeout mechanics を所有し、capsule field list を第二の正本にしません。
subagent-only startup / internal skill routes are owned by `agents/internal-routines/subagent-startup.md`. Bootstrap cites that routine and carries `run.subagent_prompt_packet.subagent_startup_route` into handoff routing when present; it does not add `_...` labels to public skill routing or duplicate the capsule schema.
prompt / routing / subagent-config drift を直す task では、shared policy prose を
直接広く書き換える前に `prompt_config_reviewer` を prompt/config audit wave として起動し、
対象 surface は route seed として扱い、責務検索、再利用確認、stale surface scan、dependency expansion を通して handoff scope へ落とします。
goal-driven repo-changing task では、`/goal` がまだ exact でなくても provisional run bundle を作り、`requirements_organizer`、`explorer`、必要なら `execution_planner` と `plan_reviewer` の read-only handoff plan を先に作ります。active runtime が明示許可を持つ場合だけ、その wave を起動します。
goal-driven task では、write-capable implementation subagent は `goal.md` が parseable で、Codex goal view が mirrored / queued され、Plan-mode evidence mapping が揃うまで起動しません。
通常の repo-changing task で coding / implementation / patch / doc-edit work が scope に入る場合は、この goal-driven `goal.md` block を適用しません。run bundle と pre-handoff investigation packet が dependency-expanded handoff scope、validation plan、tool-rejection preflight evidence を作ったら、read-only wave の追加より先に `spark_worker` / `worker` を起動または schedule します。read-only wave は setup evidence であり、implementation handoff の代替ではありません。
active runtime が explicit user request なしの `spawn_agent` を禁止する場合、read-only pre-goal wave も即座には起動せず、handoff packet、owner、expected output、`PRE_GOAL_SUBAGENT_AUTHORIZATION=required` を run bundle に残して許可待ちにします。
command output の `IMPLEMENTATION_CODEX_AGENTS` を確認し、`spark_worker,worker` なら Abstract Design Frame と approved design packet で完全に切れる低リスク implementation slice は `spark_worker` を先に使います。
subagent の model / reasoning は該当 `.codex/agents/*.toml` を先に読みます。
read-only exploration に切る前に、その質問を所有する checker、router、semantic index、dashboard があるか確認し、ある場合は tool を先に呼びます。subagent は structured tool artifact が曖昧な場合の解釈や、tool-covered ではない judgement の独立 review に使い、同じ文書を読み直して決定論的 check を反復しません。
repo inventory、tool drift survey、機械 report 要約は、implementation の critical path を塞がない独立検証としてだけ mini helper role に切ります。static validation triage、diff-local Python / C++ review、bounded review、report traceability、checklist-style review gate は frontier review role TOML に切ります。user が coding / implementation / patch / doc-edit work を求めている場合、既定の説明は write-capable handoff first にします。surface route seed、responsibility search、reuse survey、stale-surface scan、dependency expansion、validation plan、tool-rejection preflight から handoff packet が揃い次第、write-capable `spark_worker` / `worker` handoff を schedule し、parent は handoff packet、統合順序、review gate、最終責任を持ちます。parent-direct は explicit approval、spawn authorization blocker、または tool-gate blocker を run bundle に記録した exception route です。
実装 slice は Abstract Design Frame から導かれた差し替え可能な責務単位で、public interface 変更なし、依存追加なし、仕様解釈なし、局所 validation で閉じる場合だけ `spark_worker` first にします。
`spark_worker` が runtime capacity または compatibility で起動できない場合は、同じ packet を `worker` に渡して実装 route を継続します。mini helper role または review role の起動失敗は、同じ role packet と該当 `.codex/agents/*.toml` の `model` / `model_reasoning_effort` で原因を切り分けます。
command output の `WORKFLOW_SUBAGENT_PROMPT_PACKET` を確認し、すべての subagent handoff prompt は `agents/COMMUNICATION_PROTOCOL.md` の `Context Visibility Contract` と `Fresh Subagent Context Capsule` を満たすように、`team_manifest.yaml` の `run.subagent_prompt_packet` と該当 role の `prompt_contract` から selected fields だけを入れます。full packet、raw stdout、raw logs、broad chat summary は prompt に貼りません。
command output の `STANDARD_AGENT_WAVE_SEQUENCE=plan,review,edit` を確認し、
各 wave の handoff では `team_manifest.yaml` の
`run.standard_wave_sequence` に沿って plan artifact、review gate decision、
edit handoff evidence を順に記録します。
command output の `DEFAULT_QUALITY_CHECKS=enabled`、
`DEFAULT_QUALITY_CHECK_ROLES`、`DEFAULT_QUALITY_CHECK_AGENT_TYPES` を確認し、
review と edit の handoff では `team_manifest.yaml` の
`run.default_quality_check_policy` を含めます。
handoff prompt には repo root や `/workspace` 全体ではなく、dependency-expanded `allowed_paths`、該当 canon 節、`do_not_read` surface、expected output schema を含め、context artifact は `agents/COMMUNICATION_PROTOCOL.md` が定義する capsule で参照します。implementation handoff では implementation-surface router の `PRIMARY_PATHS` を `allowed_paths` の seed、`FORBIDDEN_PATHS` を `do_not_read` の seed にし、router が unavailable なら deterministic fallback output を provisional source-packet seed として渡すか `router_unavailable_blocker` を記録します。fallback routing は `fallback_exit_status` として `canonical_rerun_pass`、`durable_blocker_or_issue`、`explicit_approval_evidence` のいずれかに接続します。`allowed_paths` は手書き対象だけで閉じず、編集候補、検索 hit、checker finding、changed path を seed に dependency header graph で再帰展開した `dependency_edit_scope.txt` / `dependency_graph.tsv` を優先します。full tree search、raw accumulated logs、unrelated module scan が必要になった場合は、parent へ escalation して input packet を拡張してから進めます。
theorem-driven、algorithm、implementation handoff では、protocol-owned `Target Binding Packet` を Fresh Subagent Context Capsule に必ず入れます。packet が不完全な場合は subagent を起動せず、parent が capsule または source packet を補完します。subagent から返った unchecked theorem sketch、型が合っていない式、public root への到達が示されていない local counterexample、または code suggestion は、親が同じ public root に対する checker / validation route を通すまで採用しません。
write-capable subagent へ渡す前に `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` を走らせるか明示引用し、`TOOL_REJECTION_PREDICTED_GATE`、`rejection_preflight_command`、gate-specific repair plan を handoff に含めます。Hook / Tool / SKILL / workflow / protocol surface では、予測 gate が `agentcanon_new_tool_source_route`、`codex_hook_runtime_alignment`、`tool_catalog`、`agent_protocol_convention`、`log_surface_inventory_guard` を出す場合があるため、対応 command を実装前の必須 evidence として渡します。既存 AgentCanon tool source はこの新規 source route gate では止めません。
設計解釈、衝突解決、広い architecture 判断、scope 判断を含む implementation は `worker` に戻します。
write-capable coding / docs-edit subagent を authorization または tool gate で起動できない場合は、`WRITE_SUBAGENT_AUTHORIZATION=required` または gate-specific blocker を run bundle に残し、その slice について read-only 分析を増やし続けません。parent-direct へ切り替える場合は、blocked subagent route、exception rationale、owner boundary、targeted validation を同じ run bundle に残します。
独立 workstream が複数ある場合は、workstream ごとに stage owner を置き、`run.delegated_spawn_policy` の下で vertical dynamic wave を起こします。同じ parent wave へ全 role を flat に詰め込むのは避け、入力 packet、write scope、validation route、review gate が交差しない sibling wave だけを同時に走らせます。
log-analysis 由来の wave は `agent-log-analysis` の `Finding Route Packet` を
input にします。`finding_class` が `wave_execution`、`skill_selection`、
`workflow_attribution`、`eval_gap`、`archive_hygiene`、`prompt_or_config_drift`、
または `structure_boundary` のときは、その route target を stage owner とし、
parent は launch mechanics、budget、fresh lifecycle、wave ledger の整合だけを持ちます。
同じ role を複数起動する場合は、`instance_partition` を
`repo_key`、`hook_family`、`skill_name`、`workflow_name`、`issue_id`、
または path scope で分けます。instance id は
`<role_type>:<repo_key>:<finding_class>:<partition>:<seq>` を推奨形にします。
parent または delegated stage owner が実際に spawn / skip / replacement を行ったら、`python3 tools/agent_tools/workflow_monitor.py --subagent-wave ...` で `schedule.md` と `workflow_monitoring.md` を同じ `wave_id` で更新します。delegated child wave は `remaining_spawn_budget` を必ず含めます。
Wave は「最初に決めた agent 数を一度だけ走らせる」運用ではありません。
parent は各 wave の出力を frontier queue に戻し、次に必要な bounded handoff を
作り、fresh subagent を追加または scope 変更時に差し替え、同じ checker /
validation を再実行します。次 frontier が repository / code / tool action で進む
限り、`unverified_with_next_witness` や `connection_unconnected` を user-facing
停止点にしてはいけません。
validation failure を次 writer に返す場合は、handoff に `failing_contract`、
`observation_level`、`cause_classification`、`intent_preservation`、`evidence`
を含め、pass 目的の単純化、revert、intended behavior / test 削除、
oracle weakening、validation downscope を禁止事項として明示します。
調査、環境変更、学術文章、包括的開発の強い review coverage は task catalog 側の default として管理します。
behavior-changing、regression-prone、または high-risk code change では
`test_designer` を実装前に立て、nasty case を `test_plan.md` に残します。
contract-only wrapper では checker-owned validation と static contract evidence を handoff に入れます。
包括的開発では bundle に加えて `project_reviewer`、`docs_workflow_steward`、`python_reviewer`、必要に応じて `cpp_reviewer` を固定で立てます。
Codex で planning を含む parent session では、plan-mode command を先に使います。official Codex CLI では `/plan` です。
runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を見ます。
計画レビュー agent、詳細設計レビュー agent、文書通読レビュー agent は、同じ instance を使い回しません。
学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` も別 instance を使います。
包括的開発では、parent が `team_manifest.yaml` の write policy で writer ごとの path / directory を管理します。scope が重なる場合は current checkout 内の後続 wave に serialize し、別 `git worktree` へ分けません。
新規 user request では前 task の subagent に `send_input` せず、run bundle ごとに fresh subagent を起こします。
active task の途中追加指示は別扱いです。parent は追加指示を `same_active_task_delta`、`scope_or_contract_change`、`new_task` に分類し、`python3 tools/agent_tools/workflow_monitor.py --mid-task-user-input ...` で run bundle、Agent Wave Ledger、workflow monitoring に checkpoint と updated packet path を残してから配送します。same-task delta だけ run-local active subagent へ再配送でき、scope、allowed paths、owner、review gate が変わるなら既存 agent へ継ぎ足さず fresh follow-up wave を起こします。
subagent handoff prompt には `team_manifest.yaml` の `run.subagent_lifecycle_policy` を含め、`fresh_subagents_required: true` と `reuse_for_new_task: forbidden` を明示します。
subagent context は chat 要約を蓄積するのではなく、run bundle 内の capsule artifact を更新して渡します。途中追加指示で scope が変わる場合は `workflow_monitor.py --mid-task-user-input` の updated packet path を capsule に入れ、古い handoff prompt へ追記し続けません。

## Subagent Return Investigation

`wait_agent` の timeout、empty status、または wave decision point での final
response 未着は `subagent_no_return_investigation` として扱います。parent は
close、replacement、escalation の前に、agent id、wave id、wait command と timeout、
last known status、last workflow-monitor event、runtime / tool error、log / dashboard
pointer、cause hypothesis を `workflow_monitoring.md` と closeout evidence に残します。

調査後の action は `continue_wait`、`status_probe_same_task`、
`close_and_replace_fresh_wave`、`escalate_runtime_issue` のいずれかにします。
`status_probe_same_task` は同じ active task の bounded status 確認だけに使い、
scope、allowed paths、owner、review gate が変わる場合は fresh follow-up wave へ
切り替えます。

closeout 前に run-local subagent を閉じ、`closeout_gate.md` の `subagents_closed=yes` と `Subagent Lifecycle Evidence` に close evidence を残します。
