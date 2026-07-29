---
name: cpp-review
description: Use when C or C++ code changes need strict review for build evidence, header boundaries, ownership, and native-code behavior.
---
<!--
@dependency-start
contract skill
responsibility Documents C++ Review for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# C++ Review

## Tool Commands

<!-- skill-tool-commands:start -->
この skill の workflow を適用する前に、次の command packet を使用してください。

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill cpp-review --format text
```

論理コマンドは、実行前に AgentCanon source root を基準として解決します。各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、fallback-only skill を含む script entry の script path は絶対 path にします。

packet が出力した必須 command と、task に該当する conditional command を実行してください。
<!-- skill-tool-commands:end -->


1. Read `agents/skills/cpp-review.md`.
1. Fix the changed native files, headers, and related tests before validating.
1. Run or inspect the project-native configure, build, and test commands.
1. If the repo uses CMake, run or inspect `cmake -S . -B build`, `cmake --build build`, and `ctest --test-dir build`.
1. Check ABI boundaries, header drift, ownership, error paths, and docs/test follow-through.
1. Report findings before summaries.
