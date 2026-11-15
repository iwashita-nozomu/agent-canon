# dependency-module-change

<!--
@dependency-start
contract workflow
responsibility Uses Git dependency declarations and standard checkout operations for dependency changes.
upstream design ../../documents/rule/dependency-module-changes.md dependency and pin owner
upstream design ../../documents/rule/repository-topic-clone.md standard Git checkout procedure
downstream implementation ./catalog.yaml public skill discovery
@dependency-end
-->

## 手順

1. 既存のmanifest・lock・`.gitmodules` と、consumerが実際に読むcheckoutを確認します。
   `.gitmodules` は `git config -f .gitmodules --get-regexp '^submodule\..*\.(path|url)$'`
   で読みます。submoduleの初期化と相対URLの解決は `git submodule update --init -- <path>`
   に任せ、必要なsource URLはそのcheckoutの `git remote get-url origin` で確認します。
2. [標準Gitのcheckout手順](../../documents/rule/repository-topic-clone.md) で依存の作業branchを
   作成・再利用し、最新mainを実マージします。既存の差分とpin用detached checkoutを保持します。
3. 依存側の変更を検証してPRへ公開します。consumerがexact pinを使う場合は、採用する
   commitをそのmanifest・lock・gitlinkへ反映し、実際の入力を照合してconsumerを検証します。
4. Issue/PRへ依存PR、採用commit、変更pathと検証結果を残し、利用を終えた作業cloneを片付けます。

pinとconsumer検証の責務は
[依存モジュール変更規約](../../documents/rule/dependency-module-changes.md) に従います。
GitがcheckoutとURLを扱うため、専用のURL parser・形式marker・cleanup proofを省けます。
