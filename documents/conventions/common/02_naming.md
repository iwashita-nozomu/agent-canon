<!--
@dependency-start
upstream design ../../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# 命名

この章は、実装全体で共有する命名方針をまとめます。

## 要約

- 役割が直感的に伝わる名前を使います。
- 省略は最小限にします。
- 運用に効く命名規則は、対応する正本文書へ残します。

## 規約

- 役割が直感的に伝わる名前にします。
- 省略は最小限にし、意味が曖昧になる略称は避けます。
- directory、branch、run_name、report 名のように検索性や運用手順へ効く名前は、script や口頭運用の中だけに閉じません。
- repo 全体へ効く naming rule は `documents/` 配下の正本へ残し、topic 固有の naming rule は対応する `README.md` に残します。
- experiment では少なくとも、topic 名、report 名、`result/<run_name>/` の構成、run_name 形式を文書に明記します。
