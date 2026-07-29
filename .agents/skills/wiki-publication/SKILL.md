---
name: wiki-publication
description: Use this when publishing AgentCanon wiki pages to a dedicated wiki sidecar with default-branch-only, source-bound publication checks.
---
<!--
@dependency-start
contract skill
responsibility Documents runtime skill wiring for wiki publication.
upstream design ../../../agents/skills/wiki-publication.md canonical skill contract and workflow.
upstream implementation ../../../tools/agent_tools/wiki_publish.py wiki publication gate tool.
@dependency-end
-->

# Wiki Publication Skill

## Reader Map

- Canonical owner: `agents/skills/wiki-publication.md`.
- Runtime contract: `tools/agent_tools/wiki_publish.py`.

## Tool Commands

<!-- skill-tool-commands:start -->
この skill の workflow を適用する前に、次の command packet を使用してください。

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill wiki-publication --format text
```

論理コマンドは、実行前に AgentCanon source root を基準として解決します。各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、fallback-only skill を含む script entry の script path は絶対 path にします。

packet が出力した必須 command と、task に該当する conditional command を実行してください。
<!-- skill-tool-commands:end -->

1. Read `agents/skills/wiki-publication.md`.
2. Run the wiki publication command with explicit `--writer` and `--reviewer` roles,
   explicit source commit, source and wiki roots, and summary output.
3. If you need to publish, pass `--expected-page-set-digest` from an independent
   review summary.
4. Treat missing wiki page state as typed `REMOTE_UNINITIALIZED` and refuse mutation
   before explicit initialization.
5. Always publish to `<repo>.wiki.git` sidecar and never to in-tree `wiki` content.
6. Preserve only narrow, tool-defined validation gates in this route.

## Example

```bash
python3 tools/agent_tools/wiki_publish.py \
  --wiki-root /path/to/agent-canon.wiki \
  --source-root /path/to/agent-canon \
  --source-commit <40-char-commit> \
  --repo iwashita-nozomu/agent-canon \
  --writer alice \
  --reviewer bob \
  --summary-out reports/agents/wiki-publication.json
```
