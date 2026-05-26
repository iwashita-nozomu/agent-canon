# agent-log-analysis
<!--
@dependency-start
responsibility Documents agent-log-analysis for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/runtime-log-archive.md accumulated eval and hook result storage
upstream design ../../documents/search-coordination.md coordinated search policy
upstream implementation ../../tools/agent_tools/generate_agent_runtime_dashboard.py generates compact runtime summaries
downstream implementation ../../.agents/skills/agent-log-analysis/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Purpose

skill、tool、workflow、hook、eval の蓄積ログを、raw JSONL の広域検索ではなく
token-light な compact summary に変換してから分析するための skill です。

## Use When

- user が skill / tool / workflow / hook のログ分析、弱い skill、routing miss、selection gap、蓄積分析を求めている
- `.agent-canon/archive/<env-key>/**`、`reports/**`、`*.jsonl` の生ログを読みそうな調査で、先に要約が必要
- dashboard や improvement guide の signal をもとに、どの skill / tool / workflow を直すか判断する
- token 消費を抑えながら AgentCanon runtime evidence を見る

## Required Flow

1. Raw log を `rg -n` で直接広域検索しません。
1. 先に compact summary を生成します。

```bash
python3 tools/agent_tools/generate_agent_runtime_dashboard.py \
  --root . \
  --out reports/agent-runtime-dashboard/agent-runtime-dashboard.md \
  --compact-out reports/agent-runtime-dashboard/agent-runtime-compact.md
```

1. 原則として `agent-runtime-compact.md` だけを読み、machine summary、priority problems、next actions、selection misses、evidence drilldown、prompt/token trend の移動平均を分析します。
1. compact summary で足りない観点がある場合は、raw JSONL を開く前に dashboard tool を拡張するか、より具体的な generated summary を出す option を追加します。
1. Raw JSONL は tool 実装、schema debugging、破損 audit の例外入力としてだけ読みます。読む場合は理由を明示し、`tail`、小さい parser、または path 限定 `rg -n` を使い、全ログ横断の一致行 dump を避けます。
1. user-facing report では、観測値、解釈、修正先、未確認仮説を分けます。

## Boundaries

- 実際の prompt / workflow / tool 修正は、分析結果に応じて `$agent-learning`、`$md-style-check`、`$codex-task-workflow`、または対象 skill を追加して行います。
- Durable report を残す必要がある場合は `$result-artifact-writeout` を使います。
- Full dashboard は human review 用です。agent の通常分析入力は compact summary、generated drilldown、rolling trend summary を既定にします。
