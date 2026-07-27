<!--
@dependency-start
contract reference
responsibility Documents の索引と正本境界。
upstream design ./rule/README.md filename、配置、分割規約。
upstream design ./design/README.md target state と実装境界。
upstream design ./runtime/SHARED_RUNTIME_SURFACES.md shared runtime surface policy。
upstream design ./runtime/shared-runtime-surfaces.toml machine-readable ownership manifest。
downstream design ./parent-repository/README.md parent repository structure and projection boundary。
downstream implementation ../tools/agent_tools/document_inventory.py document inventory。
@dependency-end
-->

# documents/

`documents/README.md` は、この directory の唯一の直下ファイルであり、文書の入口です。
個別文書は責務 directory に置き、直下へ戻しません。各 directory の README が、その
配下の役割、構造、読者入口を所有します。

## 読み方

- 配置・分割・命名の判断は [文書規約](./rule/README.md) から始めます。
- target state と実装境界は [設計](./design/README.md) を読みます。
- root view、Symlink、checked copy は [Runtime Surface](./runtime/SHARED_RUNTIME_SURFACES.md)
  と [親レポ構造](./parent-repository/README.md) を読みます。
- 機械可読の構造契約は [structure](./structure/) にあります。
- workflow、skill、subagent の正本は `agents/` であり、この directory に複製しません。

## Directory Map

| Directory | 役割 |
| --- | --- |
| `agent-canon/` | AgentCanon source、branch、remote、submodule、親レポ投影 |
| `codex/` | Codex 設定、エージェント運用、skill、prompt 評価 |
| `contracts/` | 親レポの bootstrap、host、remote、devcontainer、license 契約 |
| `conventions/` | 言語、レビュー、logging、OOP、docstring の共通規約 |
| `design/` | 数理・API・依存・build・tooling の設計境界 |
| `experiments/` | 実験、GPU admission、ExperimentRunner、結果保持 |
| `operations/` | branch、checklist、troubleshooting、legacy cleanup |
| `parent-repository/` | AgentCanon をvendorする親レポのroot構造 |
| `prose-reasoning-graph/` | 文書推論グラフのDSLと分析 |
| `rule/` | 文書配置、命名、依存変更の抽象規約 |
| `runtime/` | runtime surface、profile、log archive の契約 |
| `structure/` | repository structure の機械可読契約 |
| `structured-analysis/` | 構造化文書・依存・DB分析 |
| `templates/` | 契約や設定の生成テンプレート |
| `tools/` | 文書・依存・証明・可視化toolの読者向け説明 |

各 directory の詳細は、その directory の README を読みます。root index は内容を
再掲せず、正本と読者経路だけを示します。

## 所有権

- AgentCanon の共有文書は、この source tree の責任 directory が正本です。
- template / derived repo の active contract は、親レポの `documents/` が所有します。
- reports、logs、raw evidence、experiment result は `reports/` または `experiments/`
  に保存し、文書正本の代替にしません。
- 文書を移動するときは、dependency header、参照元、checker、root view を同じ変更で
  更新します。直下に互換Symlinkやchecked copyを残しません。

## 代表的な経路

- AgentCanon の更新: [agent-canon](./agent-canon/)
- Codex の runtime 設定: [codex](./codex/)
- 親レポの導入・環境: [contracts](./contracts/)
- 共有runtimeの所有境界: [runtime](./runtime/)
- 構造の機械検証: [structure](./structure/)
- 文書の分割判断: [rule](./rule/)

構造確認は `tree` と `repo_structure_contract.py` を使います。直下ファイルが
`README.md` 以外に増えた場合は、責務を分類して適切な directory owner document を
更新します。
