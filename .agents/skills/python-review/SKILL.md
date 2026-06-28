---
name: python-review
description: Python 差分を pyright、pytest、ruff、型境界、API 挙動、OOP 可読性根拠で厳密に確認する。
---
<!--
@dependency-start
contract skill
responsibility Documents Python Review for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Python Review

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill python-review --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. `agents/skills/python-review.md` を読みます。
1. 変更された Python ファイルと関連テストを直してから検証します。
1. `pyright` を実行または確認します。
1. `pytest tests/` を実行または確認します。
1. `ruff check python tests --select D,E,F,I,UP --ignore E501` を実行または確認します。
1. Python 差分が定義順、公開入口の配置、内部補助関数の配置を変える場合は、
   `python3 tools/agent_tools/check_convention_compliance.py` を実行または確認し、
   定義順契約が review evidence に見えていることを確認します。
1. 変更された Python ファイルが、公開契約、公開入口、共有の内部補助関数、単一公開入口に従う内部補助関数の読者順序を保っていることを確認します。
1. Python 差分が class、dataclass、`Protocol`、継承、公開 API、型境界、依存方向を持つ場合は、`$oop-readability-check` / `python3 tools/oop/python/readability.py` を下流根拠として実行または確認し、SOLID 原則シグナル数を確認します。
   レポート内の Single responsibility、Open/closed、Liskov substitution、
   Interface segregation、Dependency inversion のシグナルを review evidence として使います。
1. 同じ変更パスに対して `python3 tools/agent_tools/check_solid_evidence.py --root . <changed-python-paths> --evidence <oop-readability-report>` を実行または確認し、レポートの `scanned_paths` が確認対象の SOLID 対象ファイルを覆っていることを確認します。
1. API 挙動、型境界、文書とテストの追随を確認します。
1. 要約より前に指摘を返します。
