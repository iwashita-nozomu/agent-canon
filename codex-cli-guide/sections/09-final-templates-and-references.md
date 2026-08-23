<!--
@dependency-start
contract reference
responsibility Houses the split guide section: 最終追加テンプレート集と参考文献.
upstream design ../source/codex_cli_guide_config_deepdive.full.md preserved generated guide body.
@dependency-end
-->

# 最終追加テンプレート集と参考文献

- source file: `codex_cli_guide_config_deepdive.md`
- source lines: 11748-12386
- section sha256: `e6b5487c3f3e0263fca9f54727a19a7959b9369e6153e68acd3677ddd78d9510`

<!-- split-content-start -->

# 第IX部 最終追加テンプレート集


## 設定を運用へ落とし込むテンプレート

この部では、設定ファイルそのものに加えて、PR、月次棚卸し、障害時rollback、CI実行に使う短いテンプレートを追加する。


### 最終追加レシピ 254: repo監査用profile

**目的**  設定断片を運用テンプレートとして追加する。


```
[profiles.audit]
sandbox_mode = "read-only"
approval_policy = "on-request"
web_search = "disabled"
model_reasoning_effort = "high"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 255: 依存更新レビューprofile

**目的**  設定断片を運用テンプレートとして追加する。


```
[profiles.dependency_review]
sandbox_mode = "read-only"
web_search = "cached"
model_reasoning_effort = "high"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 256: docs更新worker

**目的**  設定断片を運用テンプレートとして追加する。


```
name = "docs-update-worker"
description = "Update docs after verified code changes."
developer_instructions = "Only edit docs and examples. Include verification notes."
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 257: release manager agent

**目的**  設定断片を運用テンプレートとして追加する。


```
name = "release-manager"
description = "Prepare release notes and checklist from diffs."
developer_instructions = "Do not publish. Draft notes, risk list, and verification checklist."
sandbox_mode = "read-only"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 258: MCP read only owner lookup

**目的**  設定断片を運用テンプレートとして追加する。


```
[mcp_servers.owner_lookup]
url = "https://mcp.example.internal/owners/mcp"
bearer_token_env_var = "OWNER_LOOKUP_TOKEN"
enabled_tools = ["lookup_owner", "list_team_services"]
tool_timeout_sec = 30
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 259: MCP contract docs

**目的**  設定断片を運用テンプレートとして追加する。


```
[mcp_servers.contract_docs]
url = "https://mcp.example.internal/contracts/mcp"
bearer_token_env_var = "CONTRACT_DOCS_TOKEN"
enabled_tools = ["search_contracts", "get_contract"]
startup_timeout_sec = 10
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 260: MCP disable write tools

**目的**  設定断片を運用テンプレートとして追加する。


```
[mcp_servers.tracker]
url = "https://mcp.example.internal/tracker/mcp"
bearer_token_env_var = "TRACKER_TOKEN"
enabled_tools = ["search_tickets", "get_ticket"]
disabled_tools = ["update_ticket", "delete_ticket", "assign_ticket"]
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 261: hookでlockfile変更を検知

**目的**  設定断片を運用テンプレートとして追加する。


```
[hooks]
[[hooks.PostToolUse]]
matcher = "^Bash$"
[[hooks.PostToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/check_lockfile_changes.py"
timeout = 10
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 262: hookで生成物を警告

**目的**  設定断片を運用テンプレートとして追加する。


```
[hooks]
[[hooks.PostToolUse]]
matcher = "^Bash$"
[[hooks.PostToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/warn_generated_diff.py"
timeout = 10
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 263: hookでbranch保護

**目的**  設定断片を運用テンプレートとして追加する。


```
[hooks]
[[hooks.SessionStart]]
matcher = ".*"
[[hooks.SessionStart.hooks]]
type = "command"
command = "python3 .codex/hooks/check_not_main_branch.py"
timeout = 10
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 264: rulesでpublish禁止

**目的**  設定断片を運用テンプレートとして追加する。


```
prefix_rule(pattern=["npm", "publish"], decision="forbidden", reason="Publishing packages from Codex is not allowed.")
prefix_rule(pattern=["pnpm", "publish"], decision="forbidden", reason="Publishing packages from Codex is not allowed.")
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 265: rulesでcloud操作確認

**目的**  設定断片を運用テンプレートとして追加する。


```
prefix_rule(pattern=["aws"], decision="prompt", reason="Cloud provider commands require human review.")
prefix_rule(pattern=["gcloud"], decision="prompt", reason="Cloud provider commands require human review.")
prefix_rule(pattern=["az"], decision="prompt", reason="Cloud provider commands require human review.")
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 266: rulesでmigration確認

**目的**  設定断片を運用テンプレートとして追加する。


```
prefix_rule(pattern=["rails", "db:migrate"], decision="prompt", reason="Database migration requires review.")
prefix_rule(pattern=["prisma", "migrate", "deploy"], decision="prompt", reason="Database migration requires review.")
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 267: requirementsでCI host制御

**目的**  設定断片を運用テンプレートとして追加する。


```
[[remote_sandbox_config]]
hostname_patterns = ["ci-runner-*" ]
allowed_sandbox_modes = ["read-only", "workspace-write"]
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 268: requirementsでprod host制御

**目的**  設定断片を運用テンプレートとして追加する。


```
[[remote_sandbox_config]]
hostname_patterns = ["prod-*", "bastion-*" ]
allowed_sandbox_modes = ["read-only"]
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 269: requirementsでMCP docs固定

**目的**  設定断片を運用テンプレートとして追加する。


```
[mcp_servers.docs.identity]
url = "https://mcp.example.internal/docs/mcp"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 270: requirementsでMCP tracker固定

**目的**  設定断片を運用テンプレートとして追加する。


```
[mcp_servers.tracker.identity]
url = "https://mcp.example.internal/tracker/mcp"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 271: project READMEテンプレ

**目的**  設定断片を運用テンプレートとして追加する。


```
# .codex/README.md
This directory contains Codex project configuration.
- config.toml: trusted project settings.
- agents: role-specific agents.
- hooks: local policy scripts.
- rules: command policy.
- mcp: repo-local MCP servers.
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 272: AGENTSの最小安全項目

**目的**  設定断片を運用テンプレートとして追加する。


```
# AGENTS.md
## Safety
- Do not read secrets.
- Do not commit unless asked.
- Do not push.
- Show test results and git diff summary.
- Ask before installing dependencies.
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 273: AGENTSの検証項目

**目的**  設定断片を運用テンプレートとして追加する。


```
# AGENTS.md
## Verification
- Run the smallest relevant test first.
- If tests are skipped, explain why.
- Include command output summary in final response.
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 274: CI review command

**目的**  設定断片を運用テンプレートとして追加する。


```
codex exec --profile ci_review "Review this diff for correctness, security, and missing tests. Output JSON."
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 275: CI patch command

**目的**  設定断片を運用テンプレートとして追加する。


```
codex exec --profile ci_patch "Fix the failing tests with minimal changes. Do not use network."
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 276: MCP health workflow

**目的**  設定断片を運用テンプレートとして追加する。


```
codex mcp list
codex mcp get docs
codex mcp get tracker
# In TUI: /mcp
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 277: feature review workflow

**目的**  設定断片を運用テンプレートとして追加する。


```
codex features list
codex --profile lab features enable goals
codex --profile lab features disable apps
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 278: debug config workflow

**目的**  設定断片を運用テンプレートとして追加する。


```
# In TUI
/debug-config
/status
/mcp
/experimental
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 279: schema付き設定開始

**目的**  設定断片を運用テンプレートとして追加する。


```
#:schema https://developers.openai.com/codex/config-schema.json
model = "gpt-5.5"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 280: 設定変更PRテンプレ

**目的**  設定断片を運用テンプレートとして追加する。


```
# Codex config PR
Purpose:
Permission impact:
MCP impact:
Hooks and rules:
Validation:
Rollback:
Owner:
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 281: 月次棚卸しテンプレ

**目的**  設定断片を運用テンプレートとして追加する。


```
# Monthly Codex config review
- codex version:
- deprecated keys:
- MCP servers still needed:
- hooks still passing:
- rules false positives:
- requirements exceptions:
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 282: 障害時disableテンプレ

**目的**  設定断片を運用テンプレートとして追加する。


```
# Emergency rollback
# 1. Disable project MCP
# enabled = false
# 2. Disable hooks
# [features]
# hooks = false
# 3. Revert .codex config PR
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 283: 最終確認テンプレ

**目的**  設定断片を運用テンプレートとして追加する。


```
codex --version
codex features list
codex mcp list
codex execpolicy check "git push"
# TUI: /debug-config
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


## 参考文献・一次情報


- OpenAI Developers, Codex CLI: <https://developers.openai.com/codex/cli>
- OpenAI Developers, Command line options: <https://developers.openai.com/codex/cli/reference>
- OpenAI Developers, Codex CLI features: <https://developers.openai.com/codex/cli/features>
- OpenAI Developers, Slash commands in Codex CLI: <https://developers.openai.com/codex/cli/slash-commands>
- OpenAI Developers, Config basics: <https://developers.openai.com/codex/config-basic>
- OpenAI Developers, Advanced Configuration: <https://developers.openai.com/codex/config-advanced>
- OpenAI Developers, Configuration Reference: <https://developers.openai.com/codex/config-reference>
- OpenAI Developers, Config JSON schema: <https://developers.openai.com/codex/config-schema.json>
- OpenAI Developers, Agent approvals & security: <https://developers.openai.com/codex/agent-approvals-security>
- OpenAI Developers, Hooks: <https://developers.openai.com/codex/hooks>
- OpenAI Developers, AGENTS.md guide: <https://developers.openai.com/codex/guides/agents-md>
- OpenAI Developers, Model Context Protocol: <https://developers.openai.com/codex/mcp>
- OpenAI GitHub, openai/codex README: <https://github.com/openai/codex/blob/main/README.md>

- OpenAI Developers, Subagents: <https://developers.openai.com/codex/subagents>
- OpenAI Developers, Subagent concepts: <https://developers.openai.com/codex/concepts/subagents>
- OpenAI Developers, Customization: <https://developers.openai.com/codex/concepts/customization>
- OpenAI Developers, Sample Configuration: <https://developers.openai.com/codex/config-sample>
- OpenAI Developers, Rules: <https://developers.openai.com/codex/rules>
- OpenAI Developers, Agent Skills: <https://developers.openai.com/codex/skills>
- OpenAI Developers, Managed configuration: <https://developers.openai.com/codex/enterprise/managed-configuration>
- OpenAI Developers, Local environments: <https://developers.openai.com/codex/app/local-environments>
- OpenAI Developers, Feature Maturity: <https://developers.openai.com/codex/feature-maturity>
- OpenAI Developers, Codex changelog: <https://developers.openai.com/codex/changelog?type=codex-cli>
- OpenAI Developers, Follow a goal: <https://developers.openai.com/codex/use-cases/follow-goals>
- OpenAI Developers, Best practices: <https://developers.openai.com/codex/learn/best-practices>
- OpenAI Developers, Use Codex with the Agents SDK: <https://developers.openai.com/codex/guides/agents-sdk>
- OpenAI Developers, Codex MCP server command: <https://developers.openai.com/codex/cli/reference#codex-mcp-server>
