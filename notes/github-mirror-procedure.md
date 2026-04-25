# Git Mirror Procedure
<!--
@dependency-start
@dependency-end
-->


この note は、`origin` 以外の mirror remote を使う host 固有運用を記録するためのテンプレです。
SSH key、remote URL、hook path は環境依存なので、repo の正本ではなく `notes/` に置きます。

## 使う場面

- bare repo の `post-receive` hook で GitHub / GitLab mirror を動かす
- `origin` へ push したあと、自動で別 remote へ同期したい
- mirror failure の切り分け手順を残したい

## 記録する項目

- bare repo path
- mirror remote 名と URL
- hook file の場所
- 前提 credential
- 手動同期コマンド
- 失敗時の確認コマンド

## 推奨フロー

1. ローカルで commit する
1. `origin` へ push する
1. bare repo hook が mirror remote へ同期する
1. mirror 側 branch hash を確認する

```bash
git push origin main
git fetch <mirror-remote> --all
git rev-parse origin/main
git rev-parse <mirror-remote>/main
```

## hook 例

hook 自体は host 管理下に置きます。たとえば bare repo の `hooks/post-receive` に、次のような mirror push を置けます。

```bash
#!/bin/sh
set -eu
git push --mirror <mirror-remote>
```

実際の remote 名、credential、logging は host ごとに決めてください。

## Troubleshooting

- mirror 側に反映されない
  - bare repo の hook path と実行権限を確認する
- `Permission denied (publickey)` が出る
  - mirror remote 用 SSH key と deploy key を確認する
- push 後の hash が揃わない
  - `origin/<branch>` と `<mirror-remote>/<branch>` の hash を比較する

## Related

- `notes/knowledge/git_mirroring.md`
- `tools/push_origin.sh`
