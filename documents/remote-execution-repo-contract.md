<!--
@dependency-start
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# Remote Execution Repo Contract

この文書は、server や orchestration layer から SSH 経由で remote execution を受けられる repo の最小契約です。
target host のセットアップ自体は利用者責務にしつつ、repo 側で揃えるべき項目だけを固定します。

## 必須

- `docker/Dockerfile`
- `docker/packs/*.toml`
- repo root から動く実行入口
- `commit SHA` 固定実行で壊れないこと
- log / artifact の出力先が決まっていること

## 推奨

- CPU 前提の default runtime pack を 1 つ持つ
- GPU を要する場合だけ追加 pack を持つ
- `python3 tools/ci/run_container_pack.py --pack ... --print-only` で preview できる
- `README.md` か `docker/README.md` に runtime の役割が書かれている

## branch と commit の扱い

- 実行依頼の入力では branch を受けてもよい
- orchestration 側で branch を `commit SHA` に解決し、その SHA を execution record に残します
- target 側では branch 名ではなく resolved commit を checkout します

## Docker 契約

- remote execution は repo 定義の Docker pack をそのまま使います
- server 固有の ad-hoc command 断片に依存しません
- 必要な env や mount は pack か repo 内 script に寄せます

## artifact 契約

- 実行結果の log と artifact の置き場を決めます
- repo 内に残すものと orchestration 側で集約するものを分けます
- partial run を正式結果として扱うかどうかは repo 文書で明示します

## template

登録 template の正本は次です。

- `documents/templates/remote_execution_repo.template.toml`
- `documents/templates/remote_execution_target.template.toml`
