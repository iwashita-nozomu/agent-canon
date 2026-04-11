# Agent Learning Workflow

この文書は、agent の作業哲学と対話から得た学習を、会話文脈ではなく shared canon の階層化された `memory/` と tool へ固定する手順です。

## Purpose

- user preference と agent philosophy を混同しない
- role ごとの方法 memory と repo-wide memory を混同しない
- raw chat ではなく、短い observation と evidence に圧縮して残す
- 毎 task の closeout で、学習すべき項目があるか確認する
- stable になった項目だけを `AGENTS.md`、workflow、review rule へ昇格する
- 自己学習と対話記録の追記を template local artifact ではなく shared canon workflow の責務として扱う

## Literature Basis

- reflective equilibrium は、個別判断と一般原則を相互調整する考え方です。この repo では、個別 task の観測と agent の作業原則を `AGENT_PHILOSOPHY.md` で照合し、矛盾が増えたら workflow 正本を見直します。
- reflective practice は、専門家が作業中と作業後の reflection で暗黙知を言語化する考え方です。この repo では、task 中の気づきと closeout retrospective を `log_agent_learning.py` で短く残します。
- situated knowledges は、知識を特定の立場と実践に結び付いたものとして扱います。この repo では、observation に source、scope、confidence を付け、どこまで一般化できるかを明示します。
- Value Sensitive Design は、価値を設計過程全体で扱う方法論です。この repo では、user preference、agent philosophy、repo rule、review gate を分けて、価値の出所を追跡可能にします。
- extended mind は、外部 notebook や言語的 scaffold が認知の一部になり得ると見る立場です。この repo では、notes を agent の外部記憶として扱い、入口文書で毎回読む対象にします。
- human-feedback preference learning は、対話や評価から preference を更新する実装上の比喩を与えます。ただし、この repo では raw feedback を自動学習せず、agent が evidence 付き observation として明示的に記録します。

## Canonical Notes

- `memory/global/USER_PREFERENCES.md`
  - user の coding philosophy、review expectation、document preference
- `memory/global/AGENT_PHILOSOPHY.md`
  - agent の作業哲学、判断原則、対話から得た再発防止、task retrospective
- `memory/methods/*.md`
  - method-based memory。role 固有ではなく requirements、planning、design、implementation、review などの方法を置く
- `memory/candidates/*.md`
  - 未昇格 observation。reviewer 系はここまでで止める
- `memory/subagent_loadouts.yaml`
  - role ごとの固定 read surface と write route
- `notes/guardrails/engineering_avoidances.md`
  - 既に失敗ログから確定した禁止事項

`memory/` は shared canon 側の正本です。template root では runtime view を使いますが、closeout では canon update として扱います。

## Memory Layers

1. `reports/agents/<run-id>/`
   - run-local
1. `memory/candidates/`
   - 未昇格 candidate
1. `memory/methods/`
   - 方法ベース memory
1. `memory/global/`
   - repo-wide durable memory
1. workflow / `AGENTS.md`
   - stable rule

## Logging Rule

durable な観測を得たら次を使います。

```bash
python3 tools/agent_tools/log_agent_learning.py \
  --role manager \
  --kind interaction-observation \
  --statement "ユーザーは agent の人格形成を raw chat ではなく repo 内の更新可能な作業哲学として扱いたい" \
  --source chat \
  --evidence "2026-04-10 request about agent knowledge/philosophy updates" \
  --scope repo-wide \
  --confidence tentative
```

user preference そのものは既存の次を使います。

```bash
python3 tools/agent_tools/log_user_preference.py \
  --preference "agent の作業哲学を task / dialogue ごとに更新したい" \
  --kind provisional \
  --source chat
```

## Kind Definitions

- `interaction-observation`
  - user との対話から得た agent 側の振る舞い改善
- `work-principle`
  - 今後の task execution に使う作業原則
- `failure-avoidance`
  - 同じ失敗を防ぐための観測。確定したら `notes/guardrails/engineering_avoidances.md` へ昇格する
- `task-retrospective`
  - closeout 時の作業後 reflection
- `promotion-candidate`
  - `AGENTS.md`、workflow、review rule へ上げる候補
- `open-question`
  - まだ判断原則へ上げない未確定点

## Closeout Gate

closeout 前に次を確認します。

1. user preference は `USER_PREFERENCES.md` に入れるべきか
1. agent の作業哲学や対話上の再発防止は `memory/candidates/`、`memory/methods/`、`memory/global/AGENT_PHILOSOPHY.md` のどこへ入れるべきか
1. 確定した禁止事項は `engineering_avoidances.md` に昇格すべきか
1. stable な項目は `AGENTS.md`、`CODEX_WORKFLOW.md`、review TOML に昇格すべきか
1. `memory/` への追記が shared canon 側の更新として commit / push まで反映されたか

## Promotion Rule

- 1 回限りの task-local 指示は昇格しません。
- reviewer role は `memory/candidates/` までしか直書きしません。
- 反復して観測された、または user が明示的に durable とした項目だけを promotion candidate にします。
- `AGENTS.md` へ昇格するときは短い rule にし、source、rationale、例は note 側に残します。
- agent personality は自由作文にしません。repo の作業品質を改善する observable rule として残します。
