---
name: dependency-design
description: Define and validate the typed declarative devcontainer dependency design packet before changing mounted developer or agent tools, manifests, bootstrap, or dependency installation order.
---
<!--
@dependency-start
contract skill
responsibility Exposes the canonical dependency-design workflow to Codex runtime discovery.
upstream design ../../../agents/skills/dependency-design.md canonical dependency design packet
upstream design ../../../agents/skills/catalog.yaml public skill registry and precedence
downstream implementation ../../../tools/agent_tools/devcontainer_dependencies.py typed dependency engine
@dependency-end
-->

# Dependency Design

1. Read the canonical skill document at
   `agents/skills/dependency-design.md`.
1. Produce its design packet, scoped to mounted developer/agent tools and the
   parent follow-up contract.
1. Hand the passing packet to `environment-maintenance`.

## Tool Commands

<!-- skill-tool-commands:start -->
この skill の workflow を適用する前に、次の command packet を使用してください。

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-design --format text
```

論理コマンドは、実行前に AgentCanon source root を基準として解決します。各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、fallback-only skill を含む script entry の script path は絶対 path にします。

packet が出力した必須 command と、task に該当する conditional command を実行してください。
<!-- skill-tool-commands:end -->
