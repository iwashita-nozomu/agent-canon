# 依存モジュールの変更

<!--
@dependency-start
contract policy
responsibility Owns dependency source changes and consumer pin adoption through standard Git.
upstream design ./repository-topic-clone.md standard Git checkout operations
upstream design ../operations/BRANCH_SCOPE.md task scope and Git state preservation
downstream design ../../agents/skills/dependency-module-change.md dependency procedure
downstream design ../agent-canon/agent-canon-update-route.md standalone AgentCanon update route
@dependency-end
-->

## 依存と実際の入力

既存のmanifest・lock・`.gitmodules` と、build/importが実際に読むcheckoutを確認します。
依存の開発用cloneとconsumerの入力は、それぞれの実path・HEADで区別します。
GitはsubmoduleのURL解決・初期化・gitlinkを扱い、作業checkoutは
[標準Gitの手順](repository-topic-clone.md) で作成・再利用します。

```bash
git config -f .gitmodules --get-regexp '^submodule\..*\.(path|url)$'
git submodule status
git ls-files --stage -- <module-path>
```

submoduleを初期化する場合は `git submodule update --init -- <module-path>` を使います。
relative URLの解決はGitに任せ、必要ならsubmodule内の `git remote get-url origin` で
解決後のsourceを確認します。Gitが作るpin用detached checkoutは、その用途で保持します。

## 依存PRとconsumerへの採用

1. 依存repositoryのIssueと変更範囲を決め、Issue番号入りbranchで最新mainを実マージします。
   依存側の変更・必要な削除を終えてから、その責務に必要な検証を行います。
2. commit/pushして依存PRを公開し、repository・PR・実commitを読み戻します。
3. consumerがexact pinを使う場合は、採用するcommitを既存manifest・lock・gitlinkへ反映します。
   buildが読むcheckoutもその入力と照合してconsumerを検証します。通常の依存解決を使う
   consumerは、その既存方式を使い、実際に採用された入力を確認します。
4. consumerのIssue/PRへ依存PR、採用commit、変更path、実入力と検証結果を記録します。
   入力を更新した場合は、その変更が影響するconsumer検証を行います。

依存単体の開発検証と、consumerが採用したpinによる検証は、それぞれの入力で報告します。
merge前のPR headを採用するかはconsumerの既存受入条件で判断します。

## 片付けとAgentCanonの責務

利用を終えた作業cloneは、必要な変更・結果の保存先を確認して標準Gitの手順で片付けます。
AgentCanonのsource更新はstandalone repositoryで扱い、source-free consumerは自身の
既存の配布・更新経路を使います。この依存手順は、実際に依存宣言を持つconsumerに適用します。
