# dependency-analysis

<!--
@dependency-start
responsibility Documents dependency-analysis for this repository.
upstream design ../../documents/dependency-manifest-design.md defines dependency manifest format and tools
upstream design ../canonical/CODEX_WORKFLOW.md defines workflow gate usage
upstream design ./catalog.yaml registers this public skill
@dependency-end
-->

## Purpose

依存 manifest の header / scan / format / graph tool を、changed-file gate、個別 file review、full-repo migration inventory の目的に分けて起動します。

## Use When

- 依存 header / manifest / graph を確認したい
- `@dependency-start` / `@dependency-end` block を追加・修正した
- dependency edge、reverse edge、kind、cycle の問題を診断したい
- closeout 前に dependency manifest evidence を揃えたい

## Required Commands

Changed-file gate:

```bash
python3 tools/agent_tools/check_dependency_headers.py --changed
bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing
bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header
```

Graph check when edges changed:

```bash
bash tools/agent_tools/check_dependency_graph.sh --changed --print-edges
```

Strict reverse-edge check when that is the migration target:

```bash
bash tools/agent_tools/check_dependency_graph.sh --changed --print-edges --check-bidirectional
```

Full migration inventory:

```bash
bash tools/agent_tools/scan_dependency_headers.sh
bash tools/agent_tools/check_dependency_graph.sh --print-edges
```

## Interpretation

- changed-file header / scan / format failure は fix-now blocker です。
- default graph failure は孤立 manifest、自己参照、または cycle を示すため fix-now blocker です。
- Dockerfile や environment file を universal anchor にしません。実際に Docker、CI、requirements、runtime configuration に依存する file だけ `environment` edge を使い、それ以外は `AGENTS.md`、`README.md`、directory README、workflow/design doc、tool index、skill guide などの nearest true canon anchor に接続します。
- `--check-bidirectional` の full-repo failure は、reverse-edge 移行期間中は baseline として扱えます。ただし pass とは呼びません。
- baseline 扱いにする場合も、今回差分で old-format header、自己参照、reverse edge 欠落、kind mismatch、cycle を増やしていないことを review artifact に残します。

## Core References

- `documents/dependency-manifest-design.md`
- `agents/canonical/CODEX_WORKFLOW.md`
- `agents/templates/closeout_gate.md`
