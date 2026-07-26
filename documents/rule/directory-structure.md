<!--
@dependency-start
contract policy
responsibility Documents 文書の配置・分割・正本境界の規約。
upstream design ./README.md document rule canon index
upstream design ../design/README.md design canon reader route
upstream design ../repo-structure-contract.toml machine validator companion
downstream implementation ../../tools/agent_tools/repo_structure_contract.py expected tree validation
downstream implementation ../../tools/agent_tools/responsibility_scope.py responsibility validation
downstream implementation ../../tools/agent_tools/import_responsibility.py import boundary validation
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
- machine validator が必要とする expected directory/path は `documents/repo-structure-contract.toml` に置き、人間向けの理由や規約をそこへ重複記載しません。

## 更新と検証

責任境界、reader route、source/evidence、downstream consumer のいずれかが変わったときに、この規約と該当 directory README を見直します。
配置の整合性は `repo_structure_contract.py`、責任の重複は `responsibility_scope.py`、import 境界は `import_responsibility.py` で確認します。
