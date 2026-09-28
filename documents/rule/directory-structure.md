<!--
@dependency-start
contract policy
responsibility Documents 文書の配置・分割・正本境界の規約。
upstream design ./README.md document rule canon index
upstream design ../design/README.md design canon reader route
upstream design ../structure/repo-structure-contract.toml machine validator companion
downstream implementation ../../tools/validation/semantic/structure/repo_structure_contract.py expected tree validation
downstream implementation ../../tools/validation/semantic/responsibility/responsibility_scope.py responsibility validation
downstream implementation ../../tools/analysis/code/import_responsibility.py import boundary validation
@dependency-end
-->

# ディレクトリ構成

この文書は、文書をどこに置くか、どの責務で分割するか、どこを正本にするかを決める抽象規約です。
個別の repository tree は machine validator と各 directory README が担います。

## 配置と分割の判断軸

文書の配置または split は、次の責任境界が一つの説明と検証に収まるかで決めます。

- owner: 誰が内容を決め、更新を承認するか。
- reader: 誰がどの判断のために読むか。
- source / evidence: 何が事実、設計、または検証の根拠か。
- update cadence: どの変化に追随して更新するか。
- validation responsibility: どの checker、review、または owner が整合性を確認するか。
- downstream consumer: どの実装、workflow、root view、reader route が参照するか。

これらの境界が異なる文書を一つの README や directory にまとめません。逆に、同じ owner、reader、source、validation、consumer が共有される文書は、重複した入口を増やさず一つの責務単位にまとめます。

文書の length、token 数、task phase、作業順を directory の境界にはしません。それらは読者の負荷や workflow の情報であり、正本の責務境界ではありません。

## 正本の境界

- `documents/rule/` は、命名・配置・構成判断を再利用できる抽象規約として持ちます。
- `documents/design/` は、個別の target state、実装境界、前提、影響範囲を固定する設計正本として持ちます。ここには配置規則そのものを複製しません。
- reports、logs、raw evidence、generated artifacts、issues は、それぞれの evidence または運用 owner に置き、design の代替にしません。
- machine validator が必要とする expected directory/path は `documents/structure/repo-structure-contract.toml` に置き、人間向けの理由や規約をそこへ重複記載しません。

## 参照と到達性

文書の追加・分割では、読者が既に使う責務別 README、workflow、Skill、または実装の
説明から、必要な場面と参照先が分かる通常の Markdown リンクを同じ変更で接続します。
参照先から親へ戻るリンクだけでは、親から新しい文書へ進めません。索引は発見する入口、
実際の consumer の参照は適用する入口として区別し、索引への掲載だけで実行・適用済みとは
扱いません。本文の複製、全資料の常時読了、無関係な入口への一括リンクは不要です。

孤立候補は、本文の責務と固有情報、実際の reader / consumer、既存の代替先を照合します。
自己参照、入口から到達しない相互参照群、台帳やテスト中の名前だけの言及は、本来の
consumer から利用される証拠ではありません。一方、import / include、既存 catalog を読む
loader、glob、自動 discovery、
生成処理による利用も確認し、ファイル名検索の0件だけを削除根拠にしません。コードや
設定を孤立して見せないためだけの文書リンクも追加しません。

必要な内容は担当する既存入口へ接続し、同じ責務の重複は既存正本へ統合します。役割も
固有情報もなく、現行 consumer を確認して不要と判断できるものは、当該 owner の範囲で
削除します。形式的なリンクを足して不要物を温存せず、未確認の外部利用や動的利用は
未確認として既存 Issue に残します。範囲外 consumer の全面移行を局所整理の終了条件に
しません。

移動・分割・削除では、変更対象への直接の参照元を新しい正本または残る入口へ更新し、
元の入口から必要な内容へたどれることと、変更したリンクの path / anchor が実在することを
確認します。関係のない推移的な全依存へ編集・検証範囲を広げません。既存の Markdown、
import、catalog などを使い、接続のためだけの独自 DSL、第二の registry、新しい常時
checker は作りません。参照経路があることは到達可能性の根拠であり、内容の正しさや
実際に読まれたことの証明ではありません。

## 更新と検証

責任境界、reader route、source/evidence、downstream consumer のいずれかが変わったときに、この規約と該当 directory README を見直します。
配置の整合性は `repo_structure_contract.py`、責任の重複は `responsibility_scope.py`、import 境界は `import_responsibility.py` で確認します。
