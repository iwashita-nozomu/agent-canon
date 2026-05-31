<!--
@dependency-start
responsibility Documents fix_markdown_math tool usage.
upstream implementation ../../tools/docs/fix_markdown_math.py rewrites markdown math delimiters.
upstream implementation ../../tools/docs/check_markdown_math.py defines markdown math policy.
downstream implementation ../../tests/tools/test_fix_markdown_math.py validates fixer behavior.
@dependency-end
-->

# fix_markdown_math.py

`fix_markdown_math.py` rewrites Markdown math notation to the repository
standard:

- inline math uses the single-dollar form
- display math uses the double-dollar form

The fixer is conservative. It rewrites the common drift that
`check_markdown_math.py` reports:

- backslash-parenthesis inline delimiters to the single-dollar form
- backslash-bracket display delimiters to the double-dollar form
- standalone single-dollar display lines to the double-dollar form
- single-dollar block delimiters to double-dollar block delimiters

It skips fenced code blocks.

```bash
python3 tools/docs/fix_markdown_math.py documents/design/感度解析.md
python3 tools/docs/fix_markdown_math.py documents
python3 tools/docs/fix_markdown_math.py "documents/**/*.md"
```

Use it as a repair helper after `python3 tools/docs/check_markdown_math.py`
finds notation drift. It is not a general Markdown formatter and should not be
used as a substitute for broader docs cleanup.
