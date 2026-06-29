<!--
@dependency-start
contract reference
responsibility Houses the split guide section: MCPと実験機能の運用パターン図解.
upstream design ../source/codex_cli_guide_config_deepdive.full.md preserved generated guide body.
@dependency-end
-->

# MCPと実験機能の運用パターン図解

- source file: `codex_cli_guide_config_deepdive.md`
- source lines: 3986-4526
- section sha256: `1232210f62464e8bb053dfedd83baf24c4b3290fdfbb4d0f637cd7ae361ebb6c`

<!-- split-content-start -->

# 第VII部 図解カタログ: MCPと実験機能の運用パターン


## 図解で見る運用パターン

この部は、前章までの説明を現場で参照しやすいように、短い図解として再整理したものである。MCP、feature flag、subagent、hooks、rules、approval、sandboxは個別機能ではなく、一つの運用設計として組み合わせる。


#### 図解: 調査専用profile

`read only` → `docs MCP` → `要約`

_調査専用profileの基本パターン。_


#### 図解: PRレビューprofile

`diff` → `subagents` → `統合`

_PRレビューprofileの基本パターン。_


#### 図解: UI debug profile

`browser MCP` → `logs` → `修正`

_UI debug profileの基本パターン。_


#### 図解: CI調査profile

`artifact` → `log` → `原因`

_CI調査profileの基本パターン。_


#### 図解: 社内docs profile

`search` → `fetch` → `根拠`

_社内docs profileの基本パターン。_


#### 図解: issue調査profile

`issue` → `PR` → `履歴`

_issue調査profileの基本パターン。_


#### 図解: DB参照profile

`read only` → `limit` → `mask`

_DB参照profileの基本パターン。_


#### 図解: observability profile

`trace` → `metric` → `log`

_observability profileの基本パターン。_


#### 図解: release profile

`notes` → `check` → `draft`

_release profileの基本パターン。_


#### 図解: security profile

`secret scan` → `policy` → `review`

_security profileの基本パターン。_


#### 図解: MCP inventory

`server` → `tools` → `owner`

_MCP inventoryの基本パターン。_


#### 図解: MCP review

`purpose` → `auth` → `scope`

_MCP reviewの基本パターン。_


#### 図解: MCP test

`start` → `call` → `result`

_MCP testの基本パターン。_


#### 図解: MCP disable

`enabled false` → `reload` → `verify`

_MCP disableの基本パターン。_


#### 図解: MCP remove

`delete config` → `docs` → `notify`

_MCP removeの基本パターン。_


#### 図解: MCP upgrade

`version` → `diff` → `test`

_MCP upgradeの基本パターン。_


#### 図解: MCP incident

`detect` → `disable` → `alternate route`

_MCP incidentの基本パターン。_


#### 図解: MCP onboarding

`env` → `login` → `smoke`

_MCP onboardingの基本パターン。_


#### 図解: MCP audit

`call` → `approval` → `diff`

_MCP auditの基本パターン。_


#### 図解: MCP cleanup

`unused` → `disabled` → `archive`

_MCP cleanupの基本パターン。_


#### 図解: feature canary

`lab` → `sandbox repo` → `observe`

_feature canaryの基本パターン。_


#### 図解: feature promote

`docs` → `owner` → `default`

_feature promoteの基本パターン。_


#### 図解: feature rollback

`disable` → `profile` → `notify`

_feature rollbackの基本パターン。_


#### 図解: feature conflict

`flag A` → `flag B` → `isolate`

_feature conflictの基本パターン。_


#### 図解: feature drift

`binary` → `schema` → `docs`

_feature driftの基本パターン。_


#### 図解: feature policy

`requirements` → `pin` → `audit`

_feature policyの基本パターン。_


#### 図解: feature training

`example` → `FAQ` → `rules`

_feature trainingの基本パターン。_


#### 図解: feature metrics

`time` → `errors` → `rework`

_feature metricsの基本パターン。_


#### 図解: feature risk

`scope` → `privilege` → `duration`

_feature riskの基本パターン。_


#### 図解: feature sunset

`deprecated` → `remove` → `update`

_feature sunsetの基本パターン。_


#### 図解: hook safety

`input` → `decision` → `block`

_hook safetyの基本パターン。_


#### 図解: hook audit

`payload` → `log` → `review`

_hook auditの基本パターン。_


#### 図解: hook secret

`scan` → `mask` → `stop`

_hook secretの基本パターン。_


#### 図解: hook query

`length` → `scope` → `limit`

_hook queryの基本パターン。_


#### 図解: hook write

`tool name` → `approval` → `deny`

_hook writeの基本パターン。_


#### 図解: rules safe

`allow` → `prompt` → `forbid`

_rules safeの基本パターン。_


#### 図解: rules review

`prefix` → `effect` → `owner`

_rules reviewの基本パターン。_


#### 図解: approval flow

`request` → `human` → `decision`

_approval flowの基本パターン。_


#### 図解: sandbox flow

`read` → `write` → `network`

_sandbox flowの基本パターン。_


#### 図解: network flow

`cached` → `live` → `risk`

_network flowの基本パターン。_


#### 図解: subagent docs

`query` → `source` → `summary`

_subagent docsの基本パターン。_


#### 図解: subagent browser

`repro` → `console` → `evidence`

_subagent browserの基本パターン。_


#### 図解: subagent logs

`search` → `rank` → `cause`

_subagent logsの基本パターン。_


#### 図解: subagent reviewer

`risk` → `test` → `fix`

_subagent reviewerの基本パターン。_


#### 図解: subagent implementer

`patch` → `test` → `diff`

_subagent implementerの基本パターン。_


#### 図解: subagent coordinator

`spawn` → `collect` → `decide`

_subagent coordinatorの基本パターン。_


#### 図解: subagent limit

`threads` → `depth` → `timeout`

_subagent limitの基本パターン。_


#### 図解: subagent output

`format` → `evidence` → `todo`

_subagent outputの基本パターン。_


#### 図解: subagent failure

`timeout` → `alternate route` → `merge`

_subagent failureの基本パターン。_


#### 図解: subagent cost

`parallel` → `budget` → `stop`

_subagent costの基本パターン。_


#### 図解: goal tests

`watch` → `pass` → `stop`

_goal testsの基本パターン。_


#### 図解: goal migration

`plan` → `step` → `verify`

_goal migrationの基本パターン。_


#### 図解: goal cleanup

`find` → `fix` → `review`

_goal cleanupの基本パターン。_


#### 図解: goal docs

`draft` → `check` → `publish`

_goal docsの基本パターン。_


#### 図解: goal release

`prepare` → `verify` → `finish`

_goal releaseの基本パターン。_


#### 図解: background dev

`start` → `observe` → `stop`

_background devの基本パターン。_


#### 図解: background logs

`tail` → `filter` → `summarize`

_background logsの基本パターン。_


#### 図解: background tests

`watch` → `fail` → `rerun`

_background testsの基本パターン。_


#### 図解: background server

`port` → `health` → `stop`

_background serverの基本パターン。_


#### 図解: background cleanup

`list` → `kill` → `confirm`

_background cleanupの基本パターン。_


#### 図解: enterprise MCP

`allowlist` → `requirements` → `audit`

_enterprise MCPの基本パターン。_


#### 図解: enterprise feature

`pin` → `policy` → `rollout`

_enterprise featureの基本パターン。_


#### 図解: enterprise secret

`vault` → `env` → `rotation`

_enterprise secretの基本パターン。_


#### 図解: enterprise docs

`standard` → `examples` → `review`

_enterprise docsの基本パターン。_


#### 図解: enterprise incident

`disable` → `notify` → `postmortem`

_enterprise incidentの基本パターン。_


#### 図解: team onboarding

`install` → `login` → `smoke`

_team onboardingの基本パターン。_


#### 図解: team standards

`AGENTS` → `rules` → `hooks`

_team standardsの基本パターン。_


#### 図解: team review

`config` → `MCP` → `features`

_team reviewの基本パターン。_


#### 図解: team update

`changelog` → `test` → `merge`

_team updateの基本パターン。_


#### 図解: team archive

`remove` → `docs` → `cleanup`

_team archiveの基本パターン。_


#### 図解: final pattern A

`small` → `safe` → `documented`

_final pattern Aの基本パターン。_


#### 図解: final pattern B

`scoped` → `audited` → `reversible`

_final pattern Bの基本パターン。_


#### 図解: final pattern C

`subagent` → `MCP` → `summary`

_final pattern Cの基本パターン。_


#### 図解: final pattern D

`feature` → `profile` → `rollback`

_final pattern Dの基本パターン。_


#### 図解: final pattern E

`owner` → `version` → `runbook`

_final pattern Eの基本パターン。_


## 第VII部のまとめ

図解カタログの要点は単純である。MCPは外部能力を増やすため、tool allowlist、secret管理、timeout、Hooks、subagent分離が必要である。実験的機能は挙動変更の可能性があるため、profile隔離、feature flag、changelog確認、rollbackが必要である。どちらも、AGENTS.mdとteam docsに運用ルールを書き、ownerを置き、定期的に更新確認することで、便利さと安全性を両立できる。


---

