<!--
@dependency-start
contract policy
responsibility Documents 命名 for this repository.
upstream design ../../SHARED_RUNTIME_SURFACES.md shared documents ownership policy
@dependency-end
-->

# 命名

この章は、実装全体で共有する命名方針をまとめます。

## 要約

- 役割が直感的に伝わる名前を使います。
- 省略は最小限にします。
- 新しい名前は、責務、入力、変換、出力、既存 naming family から決めます。
- 運用に効く命名規則は、対応する正本文書へ残します。

## 規約

- 役割が直感的に伝わる名前にします。
- 省略は最小限にし、意味が曖昧になる略称は避けます。
- ファイル名、関数名、theorem 名、artifact 名は、近くの作業都合ではなく
  所有する概念と責務から決めます。`helper`、`misc`、`new`、`tmp`、
  `bridge`、`wrapper`、`thing`、`stuff` のように責務を説明しない語だけで
  名前を作りません。
- 関数や tool の名前は、できるだけ「入力 domain / 対象 object」、
  「行う変換または判定」、「戻り値または副作用」が読める形にします。
  例: `extract_jit_root_return_projection` は許容できますが、
  `handle_projection` や `do_bridge` は不可です。
- 新規または rename する名前は、既存 naming family と並べて違和感がないかを
  先に確認します。既存 family が悪い場合は、互換 alias を増やさず同じ差分で
  family 全体を rename します。
- proof / generated artifact の名前は、証明手順ではなく対象 theorem profile、
  public root、projection を表します。探索途中の都合を名前に焼き込んだ
  `attempt2`、`bridge_tmp`、`configured_main_extra` のような名前を残しません。
- directory、branch、run_name、report 名のように検索性や運用手順へ効く名前は、script や口頭運用の中だけに閉じません。
- repo 全体へ効く naming rule は `documents/` 配下の正本へ残し、topic 固有の naming rule は対応する `README.md` に残します。
- Python helper / local function は、`helper_function_inventory.py` が推定する role に対応する action token を名前へ含めます。`--only-name-gaps` は role/action token alignment の review 対象を抽出します。
- experiment では少なくとも、topic 名、report 名、`result/<run_name>/` の構成、run_name 形式を文書に明記します。
- Python のログ用 helper 関数は `documents/coding-conventions-logging.md` に従い、必ず `_log` から始めます。
- ログ helper 命名は `python3 tools/agent_tools/check_log_helper_names.py --changed --exclude vendor --exclude reports` で検証します。

## Naming Plan

新しい identifier を導入する design、handoff、または implementation slice は、
短い naming plan を持ちます。

- 対象概念: 何を表す名前か。
- 責務語彙: domain 上のどの言葉に合わせるか。
- 既存 family: 近い既存 file / function / theorem / artifact 名。
- 採用名: 作る名前または rename 後の名前。
- 禁止名: 似ているが曖昧、過剰、互換維持目的、または proof-only な名前。

naming plan が未確定なら、subagent や worker に命名裁量を渡さず、設計へ戻します。
