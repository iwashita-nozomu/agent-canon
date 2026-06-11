# agent-log-analysis
<!--
@dependency-start
responsibility Documents agent-log-analysis for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/runtime-log-archive.md accumulated eval and hook result storage
upstream design ../../documents/search-coordination.md coordinated search policy
upstream design ../../documents/runtime-log-archive.md defines the external log archive mount and branch policy
upstream implementation ../../tools/agent_tools/runtime_log_archive_git.py resolves the mounted log archive
downstream implementation ../../.agents/skills/agent-log-analysis/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Purpose

skill、tool、workflow、hook、eval の蓄積ログを、AgentCanon source tree
ではなく外部 log archive repository 側の API / compact summary に変換してから
分析するための skill です。

## Use When

- user が skill / tool / workflow / hook のログ分析、弱い skill、routing miss、selection gap、蓄積分析を求めている
- `.agent-canon/log-archive/**`、`reports/**`、`*.jsonl` の生ログを読みそうな調査で、先に要約が必要
- dashboard や improvement guide の signal をもとに、どの skill / tool / workflow を直すか判断する
- token 消費を抑えながら AgentCanon runtime evidence を見る

## Required Flow

1. Raw log を `rg -n` で直接広域検索しません。
1. AgentCanon 側では archive の mount / branch 状態だけを確認します。

```bash
python3 tools/agent_tools/runtime_log_archive_git.py ensure
python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
python3 tools/agent_tools/runtime_log_archive_git.py sync
python3 tools/agent_tools/runtime_log_archive_git.py check-clean --porcelain
```

1. `check-clean` が `RUNTIME_LOG_ARCHIVE_CLEAN=yes` を返すまで、分析や closeout を完了扱いにしません。`RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=yes` の場合は、別 repo_key の log が現在 branch に混入しているので、該当 repo_key の sync / migration を先に解消します。
1. `status --porcelain` または `check-clean --porcelain` の `RUNTIME_LOG_ARCHIVE_ROOT` を `<archive-root>` として、log archive repo 側の API / compact profile を呼びます。

```bash
python3 <archive-root>/tools/runtime_log_dashboard.py \
  --root <archive-root> \
  --profile log-analysis \
  --output reports/agent-runtime-dashboard/agent-log-analysis-compact.md \
  --api-output reports/agent-runtime-dashboard/agent-log-analysis-api.json
```

1. 原則として `agent-log-analysis-api.json` または `agent-log-analysis-compact.md` だけを読みます。log archive repo が集計、移動平均、原稿構造に合わせた evidence cell を所有します。
1. `<archive-root>/tools/runtime_log_dashboard.py` が無い場合は `log_archive_api_missing` として止めます。AgentCanon 側で raw JSONL 広域検索に戻ってはいけません。
1. compact summary で足りない観点がある場合は、raw JSONL を開く前に log archive repo の API / report profile を拡張します。
1. Raw JSONL は tool 実装、schema debugging、破損 audit の例外入力としてだけ読みます。読む場合は理由を明示し、`tail`、小さい parser、または path 限定 `rg -n` を使い、全ログ横断の一致行 dump を避けます。
1. user-facing report では、観測値、解釈、修正先、未確認仮説を分けます。

## Boundaries

- 実際の prompt / workflow / tool 修正は、分析結果に応じて `$agent-learning`、`$md-style-check`、`$codex-task-workflow`、または対象 skill を追加して行います。
- Durable report を残す必要がある場合は `$result-artifact-writeout` を使います。
- Full dashboard は human review 用です。agent の通常分析入力は log archive API JSON、compact summary、generated evidence cell を既定にします。
