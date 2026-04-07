# Canonical Skill Registry

## Curated Skills

- `repo-onboarding`
  - unfamiliar repo の入口確認
- `agent-orchestration`
  - workflow family 選択と handoff 整理
- `artifact-placement`
  - task 文書、run artifact、repo 正本の置き分け
- `from_another_agent`
  - 前回 run の carry-over と optional follow-up を吸う
- `subagent-bootstrap`
  - specialist 起動、report bundle、write-scope 整理
- `static-check`
  - 速い検査と基礎品質確認
- `static-validation`
  - lint / test / link / CI 確認
- `code-review`
  - correctness / 設計 / 保守性レビュー
- `python-review`
  - pyright / pytest / ruff を前提にした Python review
- `docs-completeness-review`
  - 文書の欠落や説明不足のレビュー
- `md-style-check`
  - Markdown の体裁とリンク確認
- `docs-consistency-review`
  - 文書間の矛盾と stale route の確認
- `change-review`
  - findings-first review
- `worktree-start`
  - worktree 開始時の scope、action log、kickoff を整える
- `worktree-health`
  - worktree の scope drift と cleanup risk を確認
- `experiment-workflow`
  - question, protocol, run, report の整理
- `experiment-lifecycle`
  - 単一 run と review / rerun 分岐
- `experiment-change-loop`
  - 実験結果で改造 loop を閉じるまで回す
- `literature-survey`
  - 先行研究、関連文献、反証候補の整理
- `research-workflow`
  - 外部調査、比較設計、run loop、decision state の整理
- `critical-review`
  - fairness, overclaim, missing evidence の確認
- `report-review`
  - experiment report の reader-facing review
- `research-perspective-review`
  - 研究系変更を複数視点で並列レビュー
- `comprehensive-review`
  - docs / tools / workflow の横断レビュー
- `project-health`
  - 継続運用、CI、drift の健全性確認
- `project-review`
  - repo-wide な棚卸しと全体レビュー
- `environment-maintenance`
  - Docker, CI, dependency, runtime 更新
- `codex-cli`
  - Codex 用の入口と skill path
- `codex-task-workflow`
  - Codex の context-independent task 実行フロー
- `claude-code-cli`
  - Claude Code 用の入口と subagent path
- `copilot-cli`
  - Copilot CLI / coding agent 用の入口と注意点

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
