# Path Resolution
<!--
@dependency-start
responsibility Documents Path Resolution for this repository.
upstream design README.md notes lifecycle index
@dependency-end
-->


## Markdown の画像パス

- Markdown の画像は、できるだけその file から見た相対パスで書きます。
- `/workspace/...` のような絶対パスは Markdown preview で崩れることがあります。
- 長く残したい図は `notes/assets/` にコピーします。
- worktree の中にある画像へ直接リンクし続けません。

## Markdown のリンク

- `main` に残す note では、できるだけ `main` 側の file へリンクします。
- results worktree の file へリンクするときは、それが一時物か恒久物かを意識します。
- 本文の核心をリンク先に逃がしすぎません。

## Python 実行パス

- 基本の import root は `/workspace/python` です。
- script を直接実行して import が壊れるなら、`sys.path` を足すより runner 側で `PYTHONPATH` を明示する方が分かりやすいです。
- 子プロセスを起こす実験では、child に渡る `PYTHONPATH` を明示します。

## 実験結果の保存先

- 実験中の raw data は隔離場所に置きます。
- `main` に持ち帰るのは、再集計に必要な final JSON と note です。
- 画像を `main` に埋め込むなら `notes/assets/` に置きます。

## よくある失敗

- 絶対パス画像を Markdown に埋め込んで preview で出ない。
- worktree の path を `main` の恒久リンクだと思い込む。
- child process 側で `PYTHONPATH` が抜けて import が壊れる。
