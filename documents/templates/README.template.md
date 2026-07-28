<!--
@dependency-start
contract template
responsibility Provides the canonical structure for a repository or directory README.
upstream design ../README.md document index and reader routing.
upstream design ../rule/README.md repository document filename and language rules.
downstream implementation <repository-path> owns the described entrypoint.
@dependency-end
-->

# <Repository or directory name>

この template は、読者が正しい入口から目的の source、実装、検証へ到達するための
README 正本雛形です。

## 責務

- この階層の目的、責任 owner、entrypoint、構造、再現手順を短く案内する。
- canonical source と generated projection、run-local artifact、履歴・参考資料を区別する。
- 読者が README の記述だけで、現在の状態を確認し、同じ結果を再構築できるようにする。

## 読者 map

- **初見の利用者**: 目的と最初に読む入口を知る。
- **実装者**: 変更対象、owner、依存する設計・契約を知る。
- **reviewer / maintainer**: 正本、projection、validation、更新責任を確認する。
- **再現担当者**: clean state、command、入力、出力、期待結果を再現する。

## 含む内容

目的、構造、owner、entrypoint、再現手順、canonical/non-canonical の区別、更新規則、
validation と既知の制約を含めます。README は設計契約や巨大な履歴、raw log、生成結果の
複製を正本にしません。

## Purpose

- purpose:
- intended reader outcome:
- governing contract / design:
- supported use cases:
- non-goals:

## Structure

```text
<root>/
├── <canonical-source>
├── <entrypoint>
├── <implementation>
└── <generated-or-local-artifact>
```

| path | responsibility | owner | source of truth | generated / local |
| --- | --- | --- | --- | --- |
| `<path>` | `<what it owns>` | `<owner>` | yes / no | generated / local / none |

## Owner and entrypoint

- canonical owner:
- responsibility boundary:
- human entrypoint:
- machine entrypoint:
- governing design / contract:
- downstream consumers:
- update owner and cadence:

## Reproduce

### Preconditions

- repository root and branch:
- required dependency / submodule state:
- runtime profile and resource assumptions:
- input fixture or configuration:

### Commands

```bash
# Replace each placeholder with a reviewed value.
<prepare-command>
<run-command>
<validation-command>
```

## Expected readback

- expected output / artifact:
- provenance fields to compare:
- pass condition:
- typed failure or accepted failure-result condition:
- cleanup or retention rule:

## Canonical and non-canonical surfaces

- canonical source:
- generated projection and producer:
- root view / copy / symlink rule:
- run-local report or raw log:
- historical issue / closed report:
- reference-only material:

Generated files are recreated by their named producer. Do not hand-edit a projection or
promote a report, log, or example into a second source of truth.

## Update and validation

1. Update the canonical owner and its governing design/contract.
2. Regenerate or project downstream views using the named producer.
3. Read back the generated output and confirm ownership/path invariants.
4. Run the targeted format, parse, and surface checks.

- update command:
- validation command:
- acceptance evidence:
- rollback / stale projection handling:

## Known limitations

- limitation:
- unsupported environment:
- deferred follow-up and owner:
