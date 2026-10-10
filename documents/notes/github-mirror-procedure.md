# Git Mirror Procedure
<!--
@dependency-start
contract reference
responsibility Documents Git Mirror Procedure for this repository.
upstream design README.md notes lifecycle index
@dependency-end
-->


この note は、`origin` 以外の mirror remote を使う host 固有運用を記録するためのテンプレです。
SSH key、remote URL、hook path は環境依存なので、repo の正本ではなく `documents/notes/` に置きます。

## 共通手順

bare repo / `post-receive` の共通モデル、push と remote freshness の確認、認証の切り分けは
[Git Mirroring](knowledge/git_mirroring.md) を参照してください。この note には、次の host 固有値と
環境別の確認コマンドだけを記録します。

## 記録する項目

- bare repo path
- mirror remote 名と URL
- hook file の場所
- 前提 credential
- 手動同期コマンド
- 失敗時の確認コマンド

## Related

- `tools/repository/publish/push_origin.sh`
