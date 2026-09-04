# PHILOSOPHY
<!--
@dependency-start
contract reference
responsibility Defines the top-level AgentCanon philosophy for users, maintainers, and agents.
upstream design README.md AgentCanon source tree overview and first-read path.
downstream design AGENTS.md repository runtime instruction entrypoint.
downstream design ROOT_AGENTS.md root agent instruction source.
downstream design agents/README.md workflow, skill, and runtime hub.
downstream design documents/README.md documentation ownership and policy index.
downstream design documents/conventions/software-engineering-principles.md language- and paradigm-neutral engineering principles and decision precedence.
downstream design documents/runtime/private-feedback-knowledge.md private knowledge and feedback contract.
@dependency-end
-->

この文書は、AgentCanon の top-level philosophy です。
ユーザー、repo owner、maintainer、agent が同じ設計思想を共有するために置きます。
設計・実装・refactor・review で原則が競合する場合の詳細な判断順序は
`documents/conventions/software-engineering-principles.md` が所有し、この文書では複製しません。

## 原則

- まず責務を明確にする。
- 明示された contract、correctness、safety、semantic invariant を、差分サイズ、短さ、style より先に守る。
- 設計は、最初に実装対象 file や最小 patch へ閉じない。
- 先に抽象責務、概念モデル、非対象、拡張余地、評価軸を固定し、その後で実装 slice に落とす。
- code、directory、document、tool、skill、workflow、DB、report の責務を同じように扱う。
- 責務が曖昧な surface を作らない。
- 同じ policy、invariant、state、identity、lifecycle を複数の正本へ置かない。
- directory は単なる置き場ではなく、配下の code / document / artifact を束ねる責務を持つ。
- document は説明の有無ではなく、担うべき責務を満たしているかで評価する。
- 最も推論能力の低い agent でも同じ出力を得られる skill を設計する。
- agent の賢さに依存せず、入力、出力、判断範囲、終了条件を surface 側で固定する。
- 決定論的な規定動作は agent task ではなく tool task にする。
- agent は判断、統合、例外処理を担い、再現可能な定型処理は tool が担う。
- 人間の意図を上位に置く。
- 会話ではなく正本に判断を残す。
- 文章、コード、tool、DB、report の対応を見失わない。
- 構造化してから agent に渡す。
- 診断は作業に接続する。
- runtime agent には単純な contract を渡す。
- tool design 文書は実行時 agent ではなく maintainer / reviewer / 設計 agent が読む。
- 新しい surface は convenience ではなく責務 gap から作る。
- KISS、YAGNI、DRY、SOLID は一律 checklist にせず、到達する contract と failure evidence がある場合だけ専門 owner から選ぶ。
- private `agent-canon-log` は同じ問題に再遭遇したときに検索して使う knowledge / feedback の置き場にし、安定した契約は正本へ昇格する。

## 境界

- 一般的なソフトウェア工学原則と競合時の優先順位は `documents/conventions/software-engineering-principles.md` に置く。
- OOP、class、state、inheritance、`Protocol`、SOLID の専門判断は `documents/conventions/object-oriented-design.md` に置く。
- 個別 tool の使い方は `tools/` と tool document に置く。
- skill の実行契約は `agents/skills/` と `.codex/personal/skills/` に置く。
- task の手順は `agents/skills/` に置き、`agents/workflows/` には reader index と bibliography だけを置く。
- validation matrix と policy は `documents/` に置く。
- 対話から得た raw observation は runtime logs/evidence/Issue/failures の owner に置き、
  独立した再発防止知識や修正 feedback は private `agent-canon-log` に置く。source treeへ本文を複製しない。
