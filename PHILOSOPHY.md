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
downstream design memory/AGENT_PHILOSOPHY.md append-first observation log before promotion.
@dependency-end
-->

この文書は、AgentCanon の top-level philosophy です。
ユーザー、repo owner、maintainer、agent が同じ設計思想を共有するために置きます。

## 原則

- まず責務を明確にする。
- 設計は、最初に実装対象 file や最小 patch へ閉じない。
- 先に抽象責務、概念モデル、非対象、拡張余地、評価軸を固定し、その後で実装 slice に落とす。
- code、directory、document、tool、skill、workflow、DB、report の責務を同じように扱う。
- 責務が曖昧な surface を作らない。
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
- memory は安定前の観測置き場にし、安定した思想は正本へ昇格する。

## 境界

- 個別 tool の使い方は `tools/` と tool document に置く。
- skill の実行契約は `agents/skills/` と `.agents/skills/` に置く。
- workflow の手順は `agents/workflows/` に置く。
- validation matrix と policy は `documents/` に置く。
- 対話から得た未昇格の学習は `memory/` に置く。
