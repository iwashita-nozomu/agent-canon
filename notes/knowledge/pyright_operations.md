# Pyright Operations
<!--
@dependency-start
responsibility Documents Pyright Operations for this repository.
upstream design README.md notes lifecycle index
@dependency-end
-->


## Config

- `pyright` の正本設定は `pyproject.toml` の `[tool.pyright]` に置く。
- repo root の `pyrightconfig.json` は editor / tool 互換のための shim とし、`extends = "./pyproject.toml"` だけを持たせる。
- baseline の対象は `python/` と `tests/` 全体とする。
- VSCode / Pylance で third-party import が missing になるときは、まず workspace の selected interpreter を疑う。repo では `.vscode/settings.json` の `python.defaultInterpreterPath` を `/usr/bin/python3` に合わせる。

## Baseline Run

- repo root で `pyright` を実行する。
- baseline が落ちる状態を常態化させない。
- import path の確認が必要なときも、まず repo root から実行する。

## Targeted Run

- test を触ったときは `pyright tests/<subdir-or-file>` を追加で回す。
- 大きな変更では、baseline と touched path の両方を残す。

## Recording

- 既知の `pyright` エラーを一時的に残すなら、理由と scope を `reviews/` か `task.md` に書く。
- `ignore` を入れたときは、なぜ必要かをコード直前コメントで説明する。
- config を広げる前に、今の baseline が clean かを確認する。

## Common Failures

- `pyproject.toml` と `pyrightconfig.json` に別々の設定を書いてしまい、どちらが効いているか分からなくなる。
- repo root 以外で実行して import 解決がぶれる。
- `exclude` で作業中モジュールを外してしまい、editor 上で loose file 扱いになって import 解決が不安定になる。
- CLI の `pyright` は通るのに Pylance だけ `reportMissingImports` を出す。これは config より interpreter 不一致のことが多い。
