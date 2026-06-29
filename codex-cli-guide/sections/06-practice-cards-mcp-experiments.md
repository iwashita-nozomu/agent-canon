<!--
@dependency-start
contract reference
responsibility Houses the split guide section: 実務カード集: MCPと実験機能パターン.
upstream design ../source/codex_cli_guide_config_deepdive.full.md preserved generated guide body.
@dependency-end
-->

# 実務カード集: MCPと実験機能パターン

- source file: `codex_cli_guide_config_deepdive.md`
- source lines: 4527-5633
- section sha256: `aac0698dd013797fc78718d0af953659319a1ff38a05a867f75c3c0e2e19a9e5`

<!-- split-content-start -->

# 第VIII部 実務カード集: すぐ使うMCPと実験機能パターン


## 実務カード集の使い方

この部は、設計会議やpull request reviewでそのまま参照できる短いカード集である。各カードは、入口、判断、結果の三段階で構成している。MCPを追加する時、実験的機能を有効化する時、subagentを増やす時、HooksやRulesを調整する時に、該当カードをチェックリストとして使う。


## MCP追加カード


この節のカードは、短時間のreviewで見るためのものである。左から入口、判断、結果の順に読む。必要ならAGENTS.mdやdocs/codexへ転記してチーム標準にする。


#### 図解: MCP追加カード 01

`purpose` → `owner` → `risk`

_MCP追加カードの確認カード01。_


#### 図解: MCP追加カード 02

`transport` → `auth` → `tools`

_MCP追加カードの確認カード02。_


#### 図解: MCP追加カード 03

`stdio` → `cwd` → `args`

_MCP追加カードの確認カード03。_


#### 図解: MCP追加カード 04

`http` → `url` → `token`

_MCP追加カードの確認カード04。_


#### 図解: MCP追加カード 05

`oauth` → `scope` → `callback`

_MCP追加カードの確認カード05。_


#### 図解: MCP追加カード 06

`allowlist` → `tools` → `review`

_MCP追加カードの確認カード06。_


#### 図解: MCP追加カード 07

`required` → `startup` → `alternate route`

_MCP追加カードの確認カード07。_


#### 図解: MCP追加カード 08

`timeout` → `measure` → `tune`

_MCP追加カードの確認カード08。_


#### 図解: MCP追加カード 09

`secret` → `env` → `rotate`

_MCP追加カードの確認カード09。_


#### 図解: MCP追加カード 10

`docs` → `AGENTS` → `FAQ`

_MCP追加カードの確認カード10。_


#### 図解: MCP追加カード 11

`test` → `start` → `call`

_MCP追加カードの確認カード11。_


#### 図解: MCP追加カード 12

`disable` → `enabled false` → `verify`

_MCP追加カードの確認カード12。_


#### 図解: MCP追加カード 13

`upgrade` → `version` → `diff`

_MCP追加カードの確認カード13。_


#### 図解: MCP追加カード 14

`incident` → `block` → `alternate route`

_MCP追加カードの確認カード14。_


#### 図解: MCP追加カード 15

`audit` → `log` → `owner`

_MCP追加カードの確認カード15。_


#### 図解: MCP追加カード 16

`read server` → `safe` → `summary`

_MCP追加カードの確認カード16。_


#### 図解: MCP追加カード 17

`write server` → `approval` → `guard`

_MCP追加カードの確認カード17。_


#### 図解: MCP追加カード 18

`browser server` → `repro` → `evidence`

_MCP追加カードの確認カード18。_


#### 図解: MCP追加カード 19

`docs server` → `search` → `fetch`

_MCP追加カードの確認カード19。_


#### 図解: MCP追加カード 20

`logs server` → `rank` → `cause`

_MCP追加カードの確認カード20。_


#### 図解: MCP追加カード 21

`issue server` → `link` → `history`

_MCP追加カードの確認カード21。_


#### 図解: MCP追加カード 22

`db server` → `limit` → `mask`

_MCP追加カードの確認カード22。_


#### 図解: MCP追加カード 23

`obs server` → `trace` → `metric`

_MCP追加カードの確認カード23。_


#### 図解: MCP追加カード 24

`file server` → `range` → `guard`

_MCP追加カードの確認カード24。_


#### 図解: MCP追加カード 25

`team server` → `requirements` → `pin`

_MCP追加カードの確認カード25。_


## 実験機能カード


この節のカードは、短時間のreviewで見るためのものである。左から入口、判断、結果の順に読む。必要ならAGENTS.mdやdocs/codexへ転記してチーム標準にする。


#### 図解: 実験機能カード 01

`maturity` → `docs` → `version`

_実験機能カードの確認カード01。_


#### 図解: 実験機能カード 02

`flag` → `enable` → `record`

_実験機能カードの確認カード02。_


#### 図解: 実験機能カード 03

`profile` → `lab` → `default`

_実験機能カードの確認カード03。_


#### 図解: 実験機能カード 04

`rollback` → `disable` → `confirm`

_実験機能カードの確認カード04。_


#### 図解: 実験機能カード 05

`goal` → `success` → `stop`

_実験機能カードの確認カード05。_


#### 図解: 実験機能カード 06

`background` → `start` → `stop`

_実験機能カードの確認カード06。_


#### 図解: 実験機能カード 07

`fast mode` → `small diff` → `review`

_実験機能カードの確認カード07。_


#### 図解: 実験機能カード 08

`multi agent` → `threads` → `depth`

_実験機能カードの確認カード08。_


#### 図解: 実験機能カード 09

`hooks` → `feature` → `matcher`

_実験機能カードの確認カード09。_


#### 図解: 実験機能カード 10

`rules` → `prefix` → `policy`

_実験機能カードの確認カード10。_


#### 図解: 実験機能カード 11

`search live` → `source` → `risk`

_実験機能カードの確認カード11。_


#### 図解: 実験機能カード 12

`image` → `purpose` → `rights`

_実験機能カードの確認カード12。_


#### 図解: 実験機能カード 13

`apps` → `scope` → `audit`

_実験機能カードの確認カード13。_


#### 図解: 実験機能カード 14

`mcp server` → `caller` → `boundary`

_実験機能カードの確認カード14。_


#### 図解: 実験機能カード 15

`cloud` → `env` → `secret`

_実験機能カードの確認カード15。_


#### 図解: 実験機能カード 16

`canary` → `sandbox repo` → `observe`

_実験機能カードの確認カード16。_


#### 図解: 実験機能カード 17

`promote` → `docs` → `owner`

_実験機能カードの確認カード17。_


#### 図解: 実験機能カード 18

`freeze` → `requirements` → `pin`

_実験機能カードの確認カード18。_


#### 図解: 実験機能カード 19

`conflict` → `isolate` → `bisect`

_実験機能カードの確認カード19。_


#### 図解: 実験機能カード 20

`deprecate` → `remove` → `notify`

_実験機能カードの確認カード20。_


#### 図解: 実験機能カード 21

`train` → `example` → `FAQ`

_実験機能カードの確認カード21。_


#### 図解: 実験機能カード 22

`measure` → `time` → `rework`

_実験機能カードの確認カード22。_


#### 図解: 実験機能カード 23

`safety` → `sandbox` → `approval`

_実験機能カードの確認カード23。_


#### 図解: 実験機能カード 24

`review` → `diff` → `test`

_実験機能カードの確認カード24。_


#### 図解: 実験機能カード 25

`standard` → `AGENTS` → `team`

_実験機能カードの確認カード25。_


## サブエージェントカード


この節のカードは、短時間のreviewで見るためのものである。左から入口、判断、結果の順に読む。必要ならAGENTS.mdやdocs/codexへ転記してチーム標準にする。


#### 図解: サブエージェントカード 01

`role` → `bounded` → `output`

_サブエージェントカードの確認カード01。_


#### 図解: サブエージェントカード 02

`explorer` → `map` → `return`

_サブエージェントカードの確認カード02。_


#### 図解: サブエージェントカード 03

`reviewer` → `risk` → `rank`

_サブエージェントカードの確認カード03。_


#### 図解: サブエージェントカード 04

`fixer` → `patch` → `test`

_サブエージェントカードの確認カード04。_


#### 図解: サブエージェントカード 05

`docs agent` → `source` → `cite`

_サブエージェントカードの確認カード05。_


#### 図解: サブエージェントカード 06

`browser agent` → `repro` → `console`

_サブエージェントカードの確認カード06。_


#### 図解: サブエージェントカード 07

`logs agent` → `artifact` → `cause`

_サブエージェントカードの確認カード07。_


#### 図解: サブエージェントカード 08

`issue agent` → `ticket` → `context`

_サブエージェントカードの確認カード08。_


#### 図解: サブエージェントカード 09

`data agent` → `csv` → `summary`

_サブエージェントカードの確認カード09。_


#### 図解: サブエージェントカード 10

`migration agent` → `one row` → `result`

_サブエージェントカードの確認カード10。_


#### 図解: サブエージェントカード 11

`parent` → `spawn` → `merge`

_サブエージェントカードの確認カード11。_


#### 図解: サブエージェントカード 12

`threads` → `budget` → `limit`

_サブエージェントカードの確認カード12。_


#### 図解: サブエージェントカード 13

`depth` → `one` → `stop`

_サブエージェントカードの確認カード13。_


#### 図解: サブエージェントカード 14

`timeout` → `job` → `abort`

_サブエージェントカードの確認カード14。_


#### 図解: サブエージェントカード 15

`handoff` → `format` → `evidence`

_サブエージェントカードの確認カード15。_


#### 図解: サブエージェントカード 16

`failure` → `alternate route` → `human`

_サブエージェントカードの確認カード16。_


#### 図解: サブエージェントカード 17

`cost` → `parallel` → `cap`

_サブエージェントカードの確認カード17。_


#### 図解: サブエージェントカード 18

`privacy` → `mask` → `avoid`

_サブエージェントカードの確認カード18。_


#### 図解: サブエージェントカード 19

`mcp inherit` → `limit` → `override`

_サブエージェントカードの確認カード19。_


#### 図解: サブエージェントカード 20

`profile` → `readonly` → `write`

_サブエージェントカードの確認カード20。_


#### 図解: サブエージェントカード 21

`model` → `effort` → `task`

_サブエージェントカードの確認カード21。_


#### 図解: サブエージェントカード 22

`skill` → `path` → `scope`

_サブエージェントカードの確認カード22。_


#### 図解: サブエージェントカード 23

`prompt` → `clear` → `bounded`

_サブエージェントカードの確認カード23。_


#### 図解: サブエージェントカード 24

`result` → `json` → `short`

_サブエージェントカードの確認カード24。_


#### 図解: サブエージェントカード 25

`cleanup` → `close` → `summarize`

_サブエージェントカードの確認カード25。_


## HooksとRulesカード


この節のカードは、短時間のreviewで見るためのものである。左から入口、判断、結果の順に読む。必要ならAGENTS.mdやdocs/codexへ転記してチーム標準にする。


#### 図解: HooksとRulesカード 01

`PreToolUse` → `inspect` → `block`

_HooksとRulesカードの確認カード01。_


#### 図解: HooksとRulesカード 02

`PostToolUse` → `review` → `log`

_HooksとRulesカードの確認カード02。_


#### 図解: HooksとRulesカード 03

`UserPrompt` → `detect` → `warn`

_HooksとRulesカードの確認カード03。_


#### 図解: HooksとRulesカード 04

`Stop` → `validate` → `continue`

_HooksとRulesカードの確認カード04。_


#### 図解: HooksとRulesカード 05

`matcher` → `specific` → `small`

_HooksとRulesカードの確認カード05。_


#### 図解: HooksとRulesカード 06

`payload` → `schema` → `parse`

_HooksとRulesカードの確認カード06。_


#### 図解: HooksとRulesカード 07

`secret scan` → `mask` → `deny`

_HooksとRulesカードの確認カード07。_


#### 図解: HooksとRulesカード 08

`write guard` → `tool` → `approval`

_HooksとRulesカードの確認カード08。_


#### 図解: HooksとRulesカード 09

`query guard` → `length` → `limit`

_HooksとRulesカードの確認カード09。_


#### 図解: HooksとRulesカード 10

`command guard` → `prefix` → `policy`

_HooksとRulesカードの確認カード10。_


#### 図解: HooksとRulesカード 11

`allow` → `safe` → `fast`

_HooksとRulesカードの確認カード11。_


#### 図解: HooksとRulesカード 12

`prompt` → `risky` → `human`

_HooksとRulesカードの確認カード12。_


#### 図解: HooksとRulesカード 13

`forbid` → `danger` → `stop`

_HooksとRulesカードの確認カード13。_


#### 図解: HooksとRulesカード 14

`unit test` → `match` → `not match`

_HooksとRulesカードの確認カード14。_


#### 図解: HooksとRulesカード 15

`CI mode` → `no prompt` → `safe`

_HooksとRulesカードの確認カード15。_


#### 図解: HooksとRulesカード 16

`hook logs` → `file` → `rotate`

_HooksとRulesカードの確認カード16。_


#### 図解: HooksとRulesカード 17

`hook owner` → `team` → `docs`

_HooksとRulesカードの確認カード17。_


#### 図解: HooksとRulesカード 18

`hook failure` → `message` → `exit`

_HooksとRulesカードの確認カード18。_


#### 図解: HooksとRulesカード 19

`rule review` → `diff` → `example`

_HooksとRulesカードの確認カード19。_


#### 図解: HooksとRulesカード 20

`rule update` → `test` → `merge`

_HooksとRulesカードの確認カード20。_


#### 図解: HooksとRulesカード 21

`sandbox pair` → `rule` → `approval`

_HooksとRulesカードの確認カード21。_


#### 図解: HooksとRulesカード 22

`MCP pair` → `hook` → `allowlist`

_HooksとRulesカードの確認カード22。_


#### 図解: HooksとRulesカード 23

`network pair` → `live` → `warn`

_HooksとRulesカードの確認カード23。_


#### 図解: HooksとRulesカード 24

`debug pair` → `verbose` → `log`

_HooksとRulesカードの確認カード24。_


#### 図解: HooksとRulesカード 25

`rollback pair` → `disable` → `remove`

_HooksとRulesカードの確認カード25。_


## トラブルシュートカード


この節のカードは、短時間のreviewで見るためのものである。左から入口、判断、結果の順に読む。必要ならAGENTS.mdやdocs/codexへ転記してチーム標準にする。


#### 図解: トラブルシュートカード 01

`not loaded` → `trust` → `root`

_トラブルシュートカードの確認カード01。_


#### 図解: トラブルシュートカード 02

`bad config` → `debug` → `layer`

_トラブルシュートカードの確認カード02。_


#### 図解: トラブルシュートカード 03

`server fail` → `cwd` → `command`

_トラブルシュートカードの確認カード03。_


#### 図解: トラブルシュートカード 04

`auth fail` → `env` → `scope`

_トラブルシュートカードの確認カード04。_


#### 図解: トラブルシュートカード 05

`tool missing` → `allowlist` → `schema`

_トラブルシュートカードの確認カード05。_


#### 図解: トラブルシュートカード 06

`slow start` → `timeout` → `profile`

_トラブルシュートカードの確認カード06。_


#### 図解: トラブルシュートカード 07

`slow tool` → `limit` → `server`

_トラブルシュートカードの確認カード07。_


#### 図解: トラブルシュートカード 08

`huge output` → `snippet` → `summary`

_トラブルシュートカードの確認カード08。_


#### 図解: トラブルシュートカード 09

`bad answer` → `source` → `prompt`

_トラブルシュートカードの確認カード09。_


#### 図解: トラブルシュートカード 10

`wrong file` → `root` → `AGENTS`

_トラブルシュートカードの確認カード10。_


#### 図解: トラブルシュートカード 11

`hook silent` → `feature` → `matcher`

_トラブルシュートカードの確認カード11。_


#### 図解: トラブルシュートカード 12

`rule silent` → `prefix` → `test`

_トラブルシュートカードの確認カード12。_


#### 図解: トラブルシュートカード 13

`agent edits` → `sandbox` → `readonly`

_トラブルシュートカードの確認カード13。_


#### 図解: トラブルシュートカード 14

`agent loops` → `stop` → `goal`

_トラブルシュートカードの確認カード14。_


#### 図解: トラブルシュートカード 15

`cost spike` → `threads` → `limit`

_トラブルシュートカードの確認カード15。_


#### 図解: トラブルシュートカード 16

`context bloat` → `subagent` → `summary`

_トラブルシュートカードの確認カード16。_


#### 図解: トラブルシュートカード 17

`network fail` → `mode` → `proxy`

_トラブルシュートカードの確認カード17。_


#### 図解: トラブルシュートカード 18

`oauth fail` → `callback` → `resource`

_トラブルシュートカードの確認カード18。_


#### 図解: トラブルシュートカード 19

`token leak` → `rotate` → `mask`

_トラブルシュートカードの確認カード19。_


#### 図解: トラブルシュートカード 20

`server down` → `disable` → `alternate route`

_トラブルシュートカードの確認カード20。_


#### 図解: トラブルシュートカード 21

`version drift` → `changelog` → `binary`

_トラブルシュートカードの確認カード21。_


#### 図解: トラブルシュートカード 22

`schema drift` → `docs` → `test`

_トラブルシュートカードの確認カード22。_


#### 図解: トラブルシュートカード 23

`team confusion` → `FAQ` → `owner`

_トラブルシュートカードの確認カード23。_


#### 図解: トラブルシュートカード 24

`unsafe diff` → `review` → `revert`

_トラブルシュートカードの確認カード24。_


#### 図解: トラブルシュートカード 25

`final check` → `pdf` → `render`

_トラブルシュートカードの確認カード25。_


## チーム運用カード


この節のカードは、短時間のreviewで見るためのものである。左から入口、判断、結果の順に読む。必要ならAGENTS.mdやdocs/codexへ転記してチーム標準にする。


#### 図解: チーム運用カード 01

`onboarding` → `install` → `login`

_チーム運用カードの確認カード01。_


#### 図解: チーム運用カード 02

`smoke test` → `codex` → `debug`

_チーム運用カードの確認カード02。_


#### 図解: チーム運用カード 03

`standard config` → `root` → `profile`

_チーム運用カードの確認カード03。_


#### 図解: チーム運用カード 04

`AGENTS` → `rules` → `style`

_チーム運用カードの確認カード04。_


#### 図解: チーム運用カード 05

`MCP inventory` → `server` → `owner`

_チーム運用カードの確認カード05。_


#### 図解: チーム運用カード 06

`feature policy` → `lab` → `promote`

_チーム運用カードの確認カード06。_


#### 図解: チーム運用カード 07

`review policy` → `PR` → `check`

_チーム運用カードの確認カード07。_


#### 図解: チーム運用カード 08

`secret policy` → `env` → `vault`

_チーム運用カードの確認カード08。_


#### 図解: チーム運用カード 09

`docs policy` → `update` → `link`

_チーム運用カードの確認カード09。_


#### 図解: チーム運用カード 10

`incident policy` → `disable` → `notify`

_チーム運用カードの確認カード10。_


#### 図解: チーム運用カード 11

`monthly review` → `version` → `schema`

_チーム運用カードの確認カード11。_


#### 図解: チーム運用カード 12

`training` → `examples` → `demo`

_チーム運用カードの確認カード12。_


#### 図解: チーム運用カード 13

`templates` → `copy` → `adapt`

_チーム運用カードの確認カード13。_


#### 図解: チーム運用カード 14

`enterprise` → `requirements` → `pin`

_チーム運用カードの確認カード14。_


#### 図解: チーム運用カード 15

`local env` → `repro` → `secret`

_チーム運用カードの確認カード15。_


#### 図解: チーム運用カード 16

`CI` → `readonly` → `json`

_チーム運用カードの確認カード16。_


#### 図解: チーム運用カード 17

`release` → `notes` → `verify`

_チーム運用カードの確認カード17。_


#### 図解: チーム運用カード 18

`security` → `audit` → `hook`

_チーム運用カードの確認カード18。_


#### 図解: チーム運用カード 19

`privacy` → `mask` → `minimize`

_チーム運用カードの確認カード19。_


#### 図解: チーム運用カード 20

`access` → `scope` → `expire`

_チーム運用カードの確認カード20。_


#### 図解: チーム運用カード 21

`archive` → `remove` → `cleanup`

_チーム運用カードの確認カード21。_


#### 図解: チーム運用カード 22

`metrics` → `usage` → `errors`

_チーム運用カードの確認カード22。_


#### 図解: チーム運用カード 23

`owner` → `rotation` → `handoff`

_チーム運用カードの確認カード23。_


#### 図解: チーム運用カード 24

`roadmap` → `feature` → `risk`

_チーム運用カードの確認カード24。_


#### 図解: チーム運用カード 25

`governance` → `standard` → `exception`

_チーム運用カードの確認カード25。_


## 実務カード集のまとめ

カード化すると、Codex CLIの運用は属人的な勘ではなく、繰り返し使える判断手順になる。特に、MCP追加、実験機能導入、subagent増設、HooksとRulesの変更は、設定diffだけでなく、目的、owner、失敗時挙動、rollback、文書更新までを一つの変更として扱うと安定する。


## 今回の徹底増補で追加した一次情報メモ

この徹底増補では、OpenAI DevelopersのCodex CLI、CLI features、Slash commands、Configuration Reference、MCP、Subagents、Hooks、Rules、Feature Maturity、Managed configuration、Best practices、Follow a goal、Codex changelog、Agents SDK関連ページを参照した。特に、MCPについてはSTDIO、Streamable HTTP、Bearer token、OAuth、tool allowlist、timeout、required、環境変数転送、OAuth callbackの観点で再整理した。実験的機能については、feature flag、`/experimental`、`/goal`、multi agent、background terminal、fast mode、Codex MCP server、Apps connectorを、導入手順とrollback手順の観点で説明した。


---
