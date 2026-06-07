# Canonical Skill Registry
<!--
@dependency-start
responsibility Documents Canonical Skill Registry for this repository.
upstream design README.md canonical workflow index
@dependency-end
-->


## Public Skills

- `agent-orchestration`
  - task 開始時の mandatory routing。workflow family、skill、review、runtime entrypoint の選択
- `repo-onboarding`
  - unfamiliar repo の入口確認
- `task-routing`
  - 長い tool / skill 候補名を短い route area と command に解決する
- `start-repository`
  - template clone から新 repository を開始する
- `codex-task-workflow`
  - Codex の context-independent task 実行フロー
- `subagent-bootstrap`
  - specialist run bundle と stage subagent の明示
- `change-review`
  - findings-first review
- `python-review`
  - pyright / pytest / ruff を前提にした Python review
- `cpp-review`
  - build / header / ownership を前提にした C / C++ review
- `oop-readability-check`
  - OOP readability tool の機械実行、表形式 report、分離された agent 分析
- `result-artifact-writeout`
  - tool / hook / eval / experiment result を raw artifact、summary、manifest として上書きせず書き出す
- `tool-finding-report`
  - tool / checker / hook / static analysis で finding を探し、raw / structured full artifact、mechanical priority order、repair packet を作る。impact artifact は比較が明示されたときだけ作る
- `agent-log-analysis`
  - skill / tool / workflow / hook / eval の蓄積ログを compact summary に変換してから分析する
- `agent-canon-update`
  - AgentCanon source、parent submodule pin、root runtime view、parent update TODO を正規 route で更新する
- `pr-processing`
  - PR / Issue queue の inventory、authority、conflict 解消、merge 順、validation、Issue triage、closeout evidence を固定する
- `agent-update-branch`
  - memory / eval / AgentCanon pin などの agent-runtime 更新を update branch に分離する
- `report-writing`
  - evidence から reader-facing report を構成し、source packet、limitations、actionability、quality checklist を固定する
- `test-design`
  - static 解析で nasty case と regression case を先に固定する
- `long-form-writing`
  - README、workflow、guide、migration、specification など一般説明 prose の DSL-to-prose adapter。長さではなく file responsibility で選ぶ
- `academic-writing`
  - 論文、thesis chapter、scholarly note の作成フロー
- `paper-writing`
  - 投稿論文、thesis chapter、paper section の作成フロー
- `md-style-check`
  - Markdown の体裁とリンク確認
- `mvp-skeleton`
  - MVP、prototype、v0、first working version、thin slice の初手を 1 core loop と明示 deferral に抑える
- `worktree-start`
  - stale worktree、古い `WORKTREE_SCOPE.md`、legacy action log を cleanup evidence として診断する。new worktree kickoff には使わない
- `worktree-health`
  - worktree の scope drift と cleanup risk を確認
- `experiment-lifecycle`
  - 単一 run と review / rerun 分岐
- `computational-optimization`
  - 数値最適化、solver、preconditioner、収束、derivative、KKT、tolerance、benchmark の数学契約と検証契約
- `adaptive-improvement-loop`
  - 実験、調査、チューニング、比較改善の outer loop
- `literature-survey`
  - 先行研究、関連文献、反証候補の整理
- `formal-proof-workflow`
  - 自然言語 claim から形式証明 obligation、既存 proof 検索、proof assistant scaffold、checker evidence を作る
- `research-workflow`
  - 外部調査、比較設計、run loop、decision state の整理
- `comprehensive-development`
  - code / docs / tools / runtime をまたぐ包括的開発フロー
- `structure-refactor`
  - directory README と dependency manifest を再帰展開し、責務に基づく directory 構造 refactor を進める
- `environment-maintenance`
  - Docker、CI、dependency、runtime 更新

## Internal Review And Runtime Routines

- docs completeness review
- docs consistency review
- citation review
- notation review
- logic-gap review
- critical review
- report review
- research perspective review pack
- artifact placement
- CLI adapter docs
- static validation commands

これらは workflow や subagent routing が要求する internal routine として扱い、public skill surface には出しません。
`agent-orchestration` は task 開始時の使い忘れが実害になるため public skill surface の先頭に出します。
`subagent-bootstrap` も repo-changing task の stage 分離に必要なため public skill surface に出します。

## Discovery Paths

- Codex:
  - `.agents/skills/<skill>/SKILL.md`

## Human Canon

- skill purpose and routing:
  - `agents/skills/README.md`
- machine-readable skill catalog:
  - `agents/skills/catalog.yaml`
