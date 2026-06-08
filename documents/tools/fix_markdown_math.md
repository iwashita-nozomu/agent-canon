<!--
@dependency-start
responsibility Documents legacy fix_markdown_math forwarder usage.
upstream implementation ../../rust/agent-canon/src/docs.rs rewrites markdown math delimiters and runs adjacent checks.
upstream implementation ../../tools/docs/fix_markdown_math.py forwards legacy CLI calls.
downstream implementation ../../tests/tools/test_fix_markdown_math.py validates fixer behavior.
@dependency-end
-->

# fix_markdown_math.py

`fix_markdown_math.py` is a legacy CLI forwarder. The canonical command is:

```bash
tools/bin/agent-canon docs fix-math <paths...>
```

The Rust command rewrites Markdown math notation to the repository standard:

- inline math uses the single-dollar form
- display math uses the double-dollar form

The fixer is conservative. It rewrites the common drift that `agent-canon docs
check` reports:

- backslash-parenthesis inline delimiters to the single-dollar form
- backslash-bracket display delimiters to the double-dollar form
- standalone single-dollar display lines to the double-dollar form
- single-dollar block delimiters to double-dollar block delimiters

It skips fenced code blocks.

```bash
tools/bin/agent-canon docs fix-math documents/design/感度解析.md
tools/bin/agent-canon docs fix-math documents
```

The command runs the adjacent docs check after writing repairs. The old Python
entrypoint prints a forwarder warning and then executes this Rust command.
