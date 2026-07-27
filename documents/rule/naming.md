<!--
@dependency-start
contract policy
responsibility Documents 文書および識別子の命名規約。
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ./README.md document rule canon index
downstream implementation ../../tools/agent_tools/check_convention_compliance.py convention validation
downstream implementation ../../tools/agent_tools/check_log_helper_names.py log helper naming validation
@dependency-end
-->

# 命名

この文書は、文書、実装、artifact、運用識別子に共通する命名の正本です。
言語や tool に固有の細則は、それぞれの owner 文書へ委ねます。

## 基本方針

- 名前から owner の責務と対象が読み取れるようにします。
- 省略や抽象語は、既存の naming family と意味が衝突しない場合に限ります。
- 近くのファイル名や一時的な作業段階ではなく、概念、責務、入力、変換、出力を根拠にします。
- 共通規約はこの文書に置き、言語や topic に固有の規約は対応する owner 文書へ置きます。

## 文書 filename

- 文書 filename は英語にします。owner 指定のない prose 文書では、英語 lower-kebab-case を既定にします。
- `README.md`、`AGENTS.md`、external schema、tool、manifest など owner が固定する名前は例外です。
- 命名の可読性を、過度な語彙リストや path の列挙で代替しません。既存の naming family、owner の用語、読者が行う検索を根拠にします。
- 本文は日本語にします。ただし path、identifier、ToolCall、external fixed name は原表記を保ちます。
- 互換 alias や一時的な suffix を追加して不確かな名前を温存せず、既存 family と一緒に rename する必要がある場合は design で境界を固定します。

## 識別子と生成物

- 関数、tool、theorem、artifact、branch、run、report の名前は、対象概念と責務が検索できる粒度にします。
- proof や generated artifact は探索手順ではなく、対象 theorem profile、public root、projection などの安定した対象を表します。
- Python helper / local function は、`helper_function_inventory.py` が推定する role と整合する action token を含めます。
- Python のログ用 helper 関数は `documents/conventions/coding-conventions-logging.md` に従い、`_log` から始めます。

## 命名計画

新しい名前や rename を design、handoff、implementation で扱うときは、短い naming plan を先に固定します。

- 対象概念: 何を表す名前か。
- 責務語彙: owner が使う domain 上の語。
- 既存 family: 近い file、function、theorem、artifact の名前。
- 採用名: 作成または rename 後の名前。
- 避ける名前: 責務を隠す、過剰な互換維持を招く、または探索手順に依存する候補。

名前が未確定なら、worker に新しい語彙を発明させず、design へ戻します。

## 検証

ログ helper の命名は、次の checker で検証します。

```bash
python3 tools/agent_tools/check_log_helper_names.py --changed --exclude vendor --exclude reports
```
