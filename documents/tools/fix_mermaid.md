<!--
@dependency-start
responsibility Documents legacy fix_mermaid forwarder usage and contract.
upstream implementation ../../rust/agent-canon/src/docs.rs rewrites Mermaid fenced blocks and runs adjacent checks.
upstream implementation ../../tools/docs/fix_mermaid.py forwards legacy CLI calls.
downstream implementation ../../tests/tools/test_fix_mermaid.py validates formatter behavior.
@dependency-end
-->

# fix_mermaid.py

`fix_mermaid.py` is a legacy CLI forwarder. The canonical command is:

```bash
tools/bin/agent-canon docs fix-mermaid <paths...>
```

The Rust command rewrites Mermaid fenced code blocks inside Markdown files. It
normalizes typoed Mermaid fence languages such as `mermeid` to `mermaid`, then
renames Mermaid-reserved node ids when they are used as flowchart node ids.

## Tool Design

The formatter scans Markdown line by line and only rewrites fenced code blocks
whose info string is `mermaid` or the known typo `mermeid`. Inside each block it
keeps Mermaid directives such as `flowchart LR` intact, then rewrites reserved
node ids in node-id positions. Labels remain unchanged, so a label such as
`SQLite graph DB` can keep the word `graph` while the node id becomes
`graph_node`.

```mermaid
flowchart LR
  markdown[Markdown file] --> fence_scan[scan fenced blocks]
  fence_scan --> mermaid_fix[fix Mermaid block]
  mermaid_fix --> markdown_format[finish Markdown formatting]
```

`tools/bin/agent-canon docs format` invokes this formatter before
trailing-space and blank-line normalization, so the standard Markdown formatter
also fixes Mermaid blocks.

## Usage

```bash
tools/bin/agent-canon docs fix-mermaid documents/tools/prose_reasoning_graph.md
tools/bin/agent-canon docs format documents/tools/prose_reasoning_graph.md
```

The command rewrites files in place, prints compact change summaries, and runs
the adjacent docs check after writing repairs. The old Python entrypoint prints a
forwarder warning and then executes this Rust command.
