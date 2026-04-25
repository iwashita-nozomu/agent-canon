# Canonical Skill Registry
<!--
@dependency-start
@dependency-end
-->


## Public Skills

- `agent-orchestration`
  - task 開始時の mandatory routing。workflow family、skill、review、runtime entrypoint の選択
- `repo-onboarding`
  - unfamiliar repo の入口確認
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
- `test-design`
  - static 解析で nasty case と regression case を先に固定する
- `long-form-writing`
  - README、workflow、guide などの長文作成フロー
- `academic-writing`
  - 論文、thesis chapter、scholarly note の作成フロー
- `paper-writing`
  - 投稿論文、thesis chapter、paper section の作成フロー
- `md-style-check`
  - Markdown の体裁とリンク確認
- `worktree-start`
  - worktree 開始時の scope、action log、kickoff を整える
- `worktree-health`
  - worktree の scope drift と cleanup risk を確認
- `experiment-lifecycle`
  - 単一 run と review / rerun 分岐
- `adaptive-improvement-loop`
  - 実験、調査、チューニング、比較改善の outer loop
- `literature-survey`
  - 先行研究、関連文献、反証候補の整理
- `research-workflow`
  - 外部調査、比較設計、run loop、decision state の整理
- `comprehensive-development`
  - code / docs / tools / runtime をまたぐ包括的開発フロー
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

- Codex / Copilot:
  - `.agents/skills/<skill>/SKILL.md`
- Claude:
  - `.claude/skills/<skill>/SKILL.md` (generated mirror from `.agents/skills/`)

## Human Canon

- skill purpose and routing:
  - `agents/skills/README.md`
- machine-readable skill catalog:
  - `agents/skills/catalog.yaml`
