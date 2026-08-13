# CLI Entrypoints
<!--
@dependency-start
contract agent-runtime
responsibility Documents CLI Entrypoints for this repository.
upstream design README.md canonical workflow index
@dependency-end
-->


この文書は、agent ごとの入口差分をまとめた正本です。
共有ルールは `agents/` に寄せ、各 CLI では薄い入口だけを使います。

## この文書の読み方

この文書は、CLI ごとの最初の入口と run bootstrap の使い分けを扱います。
まず `共通ルール` で全 CLI に共通する起動前提を確認し、Codex で作業する場合は
`Codex` を読みます。新しい run bundle を作る場合は `Run Bootstrap` の
標準 command を使います。共有 workflow、skill、subagent routing の詳細は
この文書に重複させず、参照先の `agents/` owner surface で保守します。

## 共通ルール

- 目的の repository または submodule checkout を project root として扱える
  directory から起動する。template / derived parent root と
  `vendor/agent-canon/` source checkout は instruction chain が異なる。
- Codex は起動時に Codex home の global guidance を読み、その後 project root
  から current working directory まで `AGENTS.override.md`、`AGENTS.md`、
  configured fallback names の順に各 directory から最大 1 file を読み込む。
  人が確認するときは、その chain の repo 側 entrypoint を `AGENTS.md` から辿る。
- reusable workflow は `agents/` と skill directory で保守する
- task 固有の run artifact は `reports/agents/<run-id>/` に寄せる

## Codex

入口:
- Codex instruction chain: Codex home guidance, then project-root-to-CWD
  `AGENTS.override.md` / `AGENTS.md` / configured fallback files
- Repository entrypoint: root `AGENTS.md` for the active project root
- Skill discovery metadata: `.agents/skills/`

使いどころ:
- local repository 上の実装、review、文書整備
- `AGENTS.md` を起点に canonical docs を読む運用

補足:
- skill discovery は metadata が先で、選択後に
  `.agents/skills/<skill>/SKILL.md` を読む
- task 実行の標準順序は `agents/canonical/CODEX_WORKFLOW.md`
- subagent routing は `agents/canonical/CODEX_SUBAGENTS.md`
- repo-wide の正本変更は `agents/` を先に更新する
- 最初の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言する
- planning を含む parent session では、parent session 側の plan-mode command を使う。official Codex CLI では `/plan`
- runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を直接見る
- `bootstrap_agent_run.py` の出力では
  `REPO_TOOL_ROUTING_SEQUENCE`、`REPO_TOOL_ROUTING_NEXT_COMMAND`、
  `REPO_DYNAMIC_SKILL_ROUTING_CANDIDATES` を確認する

## Run Bootstrap

標準 bundle を作るときは次を使います。

```bash
python3 tools/agent-canon/agent_tools/bootstrap_agent_run.py \
  --task "short task summary" \
  --task-id T1 \
  --owner "human-or-agent" \
  --workspace-root "$PWD"
```

nonstandard design packet を run-local input として固定する場合は、
`bootstrap_agent_run.py` の flag
`--active-design-packet JSON` を使います。JSON は schema、3 つの相対 artifact
path、`document_flow_required` からなる closed record です。unknown field を reject
し、全 field がそろった場合だけ run を作成します。生成後の authority は `team_manifest.yaml` の
`run.active_design_packet` です。

```bash
python3 tools/agent-canon/agent_tools/bootstrap_agent_run.py \
  --task "design packet run" \
  --task-id T12 \
  --owner codex \
  --workspace-root "$PWD" \
  --active-design-packet '{"schema":"waterfall.design_packet.v1","design_artifact":"custom_design_brief.md","design_review_artifact":"custom_design_review.md","document_flow_review_artifact":"custom_document_flow_review.md","document_flow_required":true}'
```

task catalog の default specialist と default review pack は候補です。owner-critical
decision または distinct unresolved claim/risk が選択したものだけ materialize し、
その他は `--enable` または明示された route で有効化します。
`--task` の文面は `route.py --prompt` にも使われ、prompt-derived skill は
`SUGGESTED_SKILLS` と `team_manifest.yaml` の `run.repo_tool_routing_policy`
へ反映されます。

```bash
python3 tools/agent-canon/agent_tools/bootstrap_agent_run.py \
  --task "research-backed change" \
  --task-id T4 \
  --owner "codex" \
  --workspace-root "$PWD"
```

環境変更では `--task-id T8`、学術文章では `--task-id T10` を起点にします。

包括的開発では次を起点にします。T12 の
`scheduler`、`schedule_reviewer`、`project_reviewer`、`docs_workflow_steward`、
`prompt_config_reviewer` は候補であり、owner-critical decision または distinct
unresolved claim/risk が選択した role だけを materialize します。

```bash
python3 tools/agent-canon/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```

実装 candidate は `worker,spark_worker` の順で、`worker` が既定です。
bounded slice で `spark_worker` を選ぶ場合だけ、parent packet から
`--select-agent-type implementer=spark_worker:<evidence>` を追加します。選択は
`SUBAGENT_AGENT_TYPE_SELECTIONS` と `team_manifest.yaml` に記録されます。
選択済み candidate が blocked の場合は local/tool context に
`selected_agent_type`、`write_capable_handoff_blocker`、`evidence`、
`parent_packet_ref`、`status=blocked` を記録し、candidate を変える場合は
parent packet と wave の改訂を必須にします。

post-implementation change review は selected owning gate が必要な場合に
`diff_triage_reviewer` を候補にします。
`python_reviewer` / `cpp_reviewer` は changed-path evidence、parent packet evidence、
または明示 review-pack activation がある場合だけ materialize します。

包括的開発では、parent が writer ごとの path / directory を `team_manifest.yaml` の write policy で管理します。write scope が重なる場合は current checkout 内の後続 wave に serialize し、別 `git worktree` へ分けません。

GitHub Actions から回すときは `.github/workflows/agent-coordination.yml` を使います。

## Runtime Evidence and Knowledge Graph

The generic source-bound context certificate is created first from native
Codex rollout evidence and the active run bundle:

```bash
python3 tools/agent-canon/agent_tools/runtime_log_archive_git.py append-context-discovery \
  --run-id <run-id> --agent-context-id <agent-context-id> --turn-id <turn-id>
```

The producer accepts only those three selectors. It reads the finite native
`session_meta` / `event_msg` rollout source, publishes exactly one immutable
`context_discovery.<certificate-id>.json` certificate, and prints its path,
certificate ID, task-completion record hash, and `CONTEXT_DISCOVERY_APPEND=pass`.
Missing, duplicate, malformed, or mismatched native evidence fails closed.
The runtime-event materializer then consumes exactly one certificate:

```bash
python3 tools/agent-canon/agent_tools/runtime_log_archive_git.py materialize-runtime-event \
  --result-family <requirements|design|review|validation|lifecycle> \
  --run-id <run-id> --gate-id <gate-id> --base-ref <base-ref>
```

The command writes one immutable prepared
`runtime_event.<unit-id>.json` artifact, appends post-target evidence to the
repo-local outcome spool, and publishes a separate hash-linked
`runtime_event.<unit-id>.outcome.<attempt-id>.<sequence>.json` receipt. The
artifact contains `publication_intent.prepared_state=prepared` and never
contains a future-valued outcome. Success requires a durability-confirmed
latest `committed` receipt; missing, uncertain, malformed, colliding, or
unconfirmed records fail closed.

Success prints the artifact path/unit/source-record hash, materialization and
attempt IDs, latest receipt path/hash, `RUNTIME_EVENT_OUTCOME=committed`, and
`RUNTIME_EVENT_MATERIALIZE=pass` only after the attempt lock is released. A
typed transaction failure prints only
`RUNTIME_EVENT_ERROR_CODE=<code>` and
`RUNTIME_EVENT_MATERIALIZE=fail`, writes no stderr, and exits `1`. Retrying the
same command confirms or appends records for the deterministic attempt; it
does not replace prior artifact, observation, or receipt bytes.

PostToolUse uses a separate O(1) local spool and never invokes this CLI. Check
the hot path without building repository/archive context, then publish one
explicit checkpoint when requested:

```bash
python3 tools/agent-canon/agent_tools/runtime_log_archive_git.py check-hook-hot-path
python3 tools/agent-canon/agent_tools/runtime_log_archive_git.py sync
```

`sync` owns one nonblocking lock and one archive ensure. It snapshots, ingests,
deduplicates, projects, publishes, reads back, and only then removes certified
spool files. `archive_transaction_busy`, `partial_retained`, `failed`, and
`uncertain` states leave source events for a later checkpoint.

The Rust graph uses one build transaction. When an active runtime event exists,
that transaction also captures one prepared-artifact/committed-receipt pair;
the pair is optional for source-only graph availability:

```bash
tools/agent-canon/bin/agent-canon graph build --root <repo-root> --format json
tools/agent-canon/bin/agent-canon graph status --root <repo-root> --format json
tools/agent-canon/bin/agent-canon graph query --root <repo-root> --relation dependency --all --format json
tools/agent-canon/bin/agent-canon graph context --root <repo-root> --path <repo-relative-path> --format json
```

`status`, `query`, and `context` are read-only consumers. They reuse the
persisted v2 snapshot and return stale/unavailable state when present runtime
artifact, receipt, live source identity, worktree manifest identity, or profile
changes. A source snapshot with unresolved, ambiguous, or uncovered diagnostics
is `incomplete` and cannot authorize query or context evidence; only an empty
completeness set is `fresh`. If no active runtime pointer existed at build time,
they consume the complete source-only snapshot as fresh. Each command performs
one bounded freshness probe and does not regenerate runtime evidence.
