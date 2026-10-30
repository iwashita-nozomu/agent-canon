# Notebook Quality

`tools/bin/agent-canon notebook-quality` checks that notebooks work as readable
demos. It looks for narrative Markdown, runnable code, visualization code,
small code cells, and code that has been kept separate from fine-grained tests.

## Usage

```bash
tools/bin/agent-canon notebook-quality [paths...] [options]
```

With explicit paths, the checker examines those notebook files and directories.
Without paths, it checks changed notebooks relative to `HEAD`, including staged
and untracked notebooks. Use `--all` to check notebooks below `jupyter/` and
`notebooks/`, or `--changed` to select changed notebooks explicitly.

Options:

- `--root <path>` sets the repository root. The default is the current directory.
- `--max-code-cell-lines <count>` sets the code cell line limit. The default is
  80.
- `--min-markdown-chars <count>` sets the total Markdown character minimum. The
  default is 120 Unicode code points after trimming surrounding whitespace.
- `--format text|json` selects the report format. The default is `text`.

If paths are supplied, they take precedence over `--changed` and `--all`. If
both selection flags are supplied without paths, `--changed` takes precedence.

## Findings and output

The checker reports invalid notebook JSON or structure, a missing or misplaced
title cell, missing Markdown or code, thin narrative, missing visualization,
consecutive code cells, oversized code cells, and forbidden test patterns.
Stored error outputs are warnings and do not fail an otherwise valid notebook.

Text output includes file, finding, warning, and per-notebook metric markers.
JSON output has `status`, `findings`, `warnings`, and `metrics` fields. Findings
and warnings include the notebook path, one-based cell and source line numbers,
check name, and detail. A finding returns exit status 1; a report without
findings returns 0; invalid arguments return 2.
