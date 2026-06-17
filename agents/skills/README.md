# Shared Skill Canon

<!--
@dependency-start
responsibility Documents Shared Skill Canon for this repository.
upstream design ./catalog.yaml enumerates public skill families
downstream design ../canonical/CODEX_WORKFLOW.md consumes the shared skill canon during task routing
@dependency-end
-->

このディレクトリは、Codex skill 文書の人間向け正本です。
機械 discovery 用の `SKILL.md` は `.agents/skills/` を正本にします。

## Rules

- skill の目的、使う場面、関連正本は `agents/skills/` に書きます。
- `AGENTS.md` には長い skill 説明を複製しません。
- `.agents/skills/` は Codex の auto-discovery path です。
- 人間が skill を明示する場合は plain text ではなく `$skill-name` を使います。
- 例: `$research-workflow`、`$adaptive-improvement-loop`、`$paper-writing`
- 新しい public skill を追加するときは `catalog.yaml` と対応文書を同時に更新します。

## Public Skill Surface

CLI に出す公開 skill は、user が直接選ぶ価値が高いものだけに絞ります。
review の細粒度 checklist、CLI adapter、artifact placement、validation helper は public skill ではなく canonical docs と subagent routing に寄せます。
workflow selection は task 開始時に使い忘れると実害が出るため、`agent-orchestration` を routing entry skill として public surface の先頭に置きます。
subagent bootstrap は repo-changing task の stage 分離に必要なため public skill として出します。

| Family | Purpose | Canonical Doc | Discovery Shim |
| ------ | ------- | ------------- | -------------- |
| `agent-orchestration` | task 開始時の mandatory routing。workflow family、skill、review、runtime entrypoint を先に選ぶ | `agents/skills/agent-orchestration.md` | `.agents/skills/agent-orchestration/SKILL.md` |
| `repo-onboarding` | unfamiliar repo の最短入口確認 | `agents/skills/repo-onboarding.md` | `.agents/skills/repo-onboarding/SKILL.md` |
| `task-routing` | 長い tool / skill 候補名を短い route area と command に解決する | `agents/skills/task-routing.md` | `.agents/skills/task-routing/SKILL.md` |
| `start-repository` | template clone から新 repo を開始し bare remote と agent-canon seed を整える | `agents/skills/start-repository.md` | `.agents/skills/start-repository/SKILL.md` |
| `codex-task-workflow` | Codex の context-independent task 実行 | `agents/skills/codex-task-workflow.md` | `.agents/skills/codex-task-workflow/SKILL.md` |
| `subagent-bootstrap` | specialist run bundle と stage subagent の明示 | `agents/skills/subagent-bootstrap.md` | `.agents/skills/subagent-bootstrap/SKILL.md` |
| `change-review` | findings-first の差分 review | `agents/skills/change-review.md` | `.agents/skills/change-review/SKILL.md` |
| `python-review` | pyright / pytest / ruff を前提にした Python review | `agents/skills/python-review.md` | `.agents/skills/python-review/SKILL.md` |
| `cpp-review` | build / header / ownership を前提にした C / C++ review | `agents/skills/cpp-review.md` | `.agents/skills/cpp-review/SKILL.md` |
| `oop-readability-check` | OOP readability tool を走らせ、必要なら機械結果と分離して agent 分析も出す | `agents/skills/oop-readability-check.md` | `.agents/skills/oop-readability-check/SKILL.md` |
| `result-artifact-writeout` | tool / hook / eval / experiment result を raw artifact、summary、manifest として上書きせず書き出す | `agents/skills/result-artifact-writeout.md` | `.agents/skills/result-artifact-writeout/SKILL.md` |
| `tool-finding-report` | tool / checker / hook / static analysis で finding を探し、raw / structured full artifact、mechanical priority order、repair packet を作る | `agents/skills/tool-finding-report.md` | `.agents/skills/tool-finding-report/SKILL.md` |
| `agent-log-analysis` | skill / tool / workflow / hook / eval の蓄積ログを compact summary に変換してから分析する | `agents/skills/agent-log-analysis.md` | `.agents/skills/agent-log-analysis/SKILL.md` |
| `agent-eval-accumulation` | missing / stale な AgentCanon eval family を registered producer と checker で append-only evidence に戻す | `agents/skills/agent-eval-accumulation.md` | `.agents/skills/agent-eval-accumulation/SKILL.md` |
| `agent-canon-update` | AgentCanon source、parent submodule pin、root runtime view、parent update TODO を正規 route で更新する | `agents/skills/agent-canon-update.md` | `.agents/skills/agent-canon-update/SKILL.md` |
| `pr-processing` | PR / Issue queue を inventory、authority、conflict、validation、merge、Issue triage、closeout evidence の順に処理する | `agents/skills/pr-processing.md` | `.agents/skills/pr-processing/SKILL.md` |
| `agent-update-branch` | memory / eval / AgentCanon pin などの agent-runtime 更新を update branch に分離する | `agents/skills/agent-update-branch.md` | `.agents/skills/agent-update-branch/SKILL.md` |
| `report-writing` | evidence から reader-facing report / presentation narrative / PPT storyboard を構成し、source packet、visual asset plan、limitations、actionability、quality checklist を固定する | `agents/skills/report-writing.md` | `.agents/skills/report-writing/SKILL.md` |
| `prose-reasoning-graph` | 既存 prose を SQLite-backed graph に変換し、構造診断、自然言語説明、rewrite packet、既存 skill handoff を出す | `agents/skills/prose-reasoning-graph.md` | `.agents/skills/prose-reasoning-graph/SKILL.md` |
| `structure-planning` | report / experiment / Eval / presentation / document / refactor の構造 contract、primary artifact、source map、invalid interpretation を先に固定する | `agents/skills/structure-planning.md` | `.agents/skills/structure-planning/SKILL.md` |
| `html-output` | HTML が明示された出力だけを browser-readable artifact にし、layout、ImageGen、既存 server reuse / external URL 公開を固定する | `agents/skills/html-output.md` | `.agents/skills/html-output/SKILL.md` |
| `html-experiment-report` | experiment / Eval artifact を HTML report にし、primary figure、実験計画、責務境界、表示 artifact を固定する | `agents/skills/html-experiment-report.md` | `.agents/skills/html-experiment-report/SKILL.md` |
| `test-design` | brittle test 診断、behavior contract、oracle、property/metamorphic 候補、nasty/regression case を固定 | `agents/skills/test-design.md` | `.agents/skills/test-design/SKILL.md` |
| `refactor-loop` | 大規模 refactor を挙動保存つき構造変更として扱う | `agents/skills/refactor-loop.md` | `.agents/skills/refactor-loop/SKILL.md` |
| `structure-refactor` | directory README と dependency manifest を再帰展開し、責務に基づいて directory 構造、path mapping、scope map を refactor する | `agents/skills/structure-refactor.md` | `.agents/skills/structure-refactor/SKILL.md` |
| `user-guided-debugging` | ユーザー明示時に、1 件ずつ問題点を提示してから修正し、検証後に次の課題を提示する | `agents/skills/user-guided-debugging.md` | `.agents/skills/user-guided-debugging/SKILL.md` |
| `long-form-writing` | README、workflow、guide、migration、specification など一般説明 prose の DSL-to-prose adapter | `agents/skills/long-form-writing.md` | `.agents/skills/long-form-writing/SKILL.md` |
| `academic-writing` | 論文、thesis chapter、scholarly note の作成フロー | `agents/skills/academic-writing.md` | `.agents/skills/academic-writing/SKILL.md` |
| `paper-writing` | 投稿論文、thesis chapter、paper section の作成フロー | `agents/skills/paper-writing.md` | `.agents/skills/paper-writing/SKILL.md` |
| `md-style-check` | format-only な Markdown の体裁とリンク確認。substantive な文書変更は `prose-reasoning-graph` と `structure-planning` も併用 | `agents/skills/md-style-check.md` | `.agents/skills/md-style-check/SKILL.md` |
| `document-canon-cleanup` | 非正本の文書候補を棚卸しし、generated evidence / closed issue / duplicate heading を正本へ振り分ける | `agents/skills/document-canon-cleanup.md` | `.agents/skills/document-canon-cleanup/SKILL.md` |
| `dependency-analysis` | 依存 manifest / 実コード依存を確認し、変更影響範囲と repair-planning packet を作る | `agents/skills/dependency-analysis.md` | `.agents/skills/dependency-analysis/SKILL.md` |
| `worktree-start` | stale worktree / `WORKTREE_SCOPE.md` / action log を legacy cleanup evidence として診断し、new worktree kickoff には使わない | `agents/skills/worktree-start.md` | `.agents/skills/worktree-start/SKILL.md` |
| `worktree-health` | worktree の scope drift と cleanup risk を確認 | `agents/skills/worktree-health.md` | `.agents/skills/worktree-health/SKILL.md` |
| `experiment-lifecycle` | 単一 run と review / rerun 分岐 | `agents/skills/experiment-lifecycle.md` | `.agents/skills/experiment-lifecycle/SKILL.md` |
| `computational-optimization` | 数値最適化、solver、preconditioner、収束、derivative、KKT、tolerance、benchmark の数学契約と検証契約を固定する | `agents/skills/computational-optimization.md` | `.agents/skills/computational-optimization/SKILL.md` |
| `adaptive-improvement-loop` | 実験、調査、チューニングを backlog-driven に回す outer loop | `agents/skills/adaptive-improvement-loop.md` | `.agents/skills/adaptive-improvement-loop/SKILL.md` |
| `literature-survey` | 先行研究、関連文献、反証候補の整理 | `agents/skills/literature-survey.md` | `.agents/skills/literature-survey/SKILL.md` |
| `formal-proof-workflow` | 自然言語 claim を形式証明 obligation、既存 proof 検索、proof assistant scaffold、checker evidence へ接続する | `agents/skills/formal-proof-workflow.md` | `.agents/skills/formal-proof-workflow/SKILL.md` |
| `algorithm-proof-exploration` | 証明義務を入力に、IR / lemma graph / algorithmic blocker frontier でアルゴリズム選択と必要な algorithm change を探索し、formal-proof へ渡す | `agents/skills/algorithm-proof-exploration.md` | `.agents/skills/algorithm-proof-exploration/SKILL.md` |
| `research-workflow` | 外部調査、比較設計、run loop、decision state の整理 | `agents/skills/research-workflow.md` | `.agents/skills/research-workflow/SKILL.md` |
| `comprehensive-development` | code / docs / tools / runtime をまたぐ包括的開発フロー | `agents/skills/comprehensive-development.md` | `.agents/skills/comprehensive-development/SKILL.md` |
| `environment-maintenance` | Docker / CI / dependency / runtime 更新 | `agents/skills/environment-maintenance.md` | `.agents/skills/environment-maintenance/SKILL.md` |
| `user-preference-sync` | user preference note を stable な AGENTS guidance へ昇格 | `agents/skills/user-preference-sync.md` | `.agents/skills/user-preference-sync/SKILL.md` |
| `agent-learning` | agent の作業哲学、対話学習、task retrospective を蓄積 | `agents/skills/agent-learning.md` | `.agents/skills/agent-learning/SKILL.md` |

## Internal Review And Runtime Routines

- docs completeness、docs consistency、notation、logic gap、citation/evidence、critical/report、research perspective review は public skill ではなく、workflow が自動で要求する review pass として扱います。
- artifact placement、CLI adapter、static validation は `agents/canonical/` と `documents/REVIEW_PROCESS.md` の責務に寄せます。
- `.agents/skills/<skill>/SKILL.md` shim がない `agents/skills/*.md` は internal、compatibility、または workflow-owned reference doc です。人間は `agents/skills/` から発見できますが、Codex の public skill discovery には出さず、public skill へ昇格するときだけ shim と `.codex/config.toml` の `[[skills.config]]` を追加します。
- agent orchestration は public skill として先頭に出し、task 開始時に runtime が必ず拾えるようにします。
- subagent bootstrap は public skill として出し、repo-changing task の stage separation で使います。
- carry-over の吸い上げは `notes/` と worktree log を正本にし、独立 public skill にはしません。

Internal / compatibility review docs that remain routable by workflow, but are not public Codex skills:

| Doc | Status | Public Route |
| --- | ------ | ------------ |
| `project-review` | internal repo-wide review routine | `$comprehensive-development` / `project_reviewer` |
| `report-review` | internal report-quality review routine | `$report-writing` / `report_reviewer` |
| `critical-review` | internal experiment/report critique routine | `$research-workflow` / `critical_guardian` |
| `static-check` | internal checker-result interpretation routine | `$tool-finding-report` |
| `docs-completeness-review` | internal docs review routine | `$document-canon-cleanup` |
| `docs-consistency-review` | internal docs review routine | `$document-canon-cleanup` |
| `code-review` | compatibility review doc | `$change-review` |

## Codex Defaults

- Project-local skill discovery is wired through official Codex `[[skills.config]]` entries in `.codex/config.toml`; every `.agents/skills/<skill>/SKILL.md` shim must be enabled there.
- OpenAI system skills stay host-provided rather than vendored. Use `$openai-docs` when changing Codex/OpenAI API config or docs; do not vendor duplicate OpenAI docs alternate route references in AgentCanon. Use `$skill-creator` when creating or refactoring skill instructions, `$skill-installer` for external skill installation, `$imagegen` for bitmap visual assets in HTML/report workflows, and `$plugin-creator` for plugin scaffolding.
- Codex では `AGENTS.md` と `agents/canonical/CODEX_WORKFLOW.md` を先に読み、repo task の skill 選択は `$agent-orchestration` から始めます。
- task ごとの skill 選択は `agent-canon local-llm route-skill --prompt "<user request>" --format json` の `ACTIVE_SKILLS` / `DEFERRED_SKILLS` を第一候補にし、このディレクトリと `catalog.yaml` は skill の責務確認に使います。
- user が skill を明示したい場合は `$skill-name` の形を既定にし、曖昧な prose より優先します。
- template clone から新 repo を始めるときは `start-repository` を使います。
- 長い tool / skill 候補名を短い command に落とすときは `task-routing` を使います。
- specialist を使う場合の Codex-specific routing は `agents/canonical/CODEX_SUBAGENTS.md` を見ます。
- repo-changing task では `$agent-orchestration` から始め、execution stage で `$codex-task-workflow`、handoff / wave が ready になった stage で `$subagent-bootstrap` を追加します。
- 文献調査が主タスクなら `literature-survey` を先に見ます。
- 自然言語の数学的 claim を形式証明へ落とすときは `formal-proof-workflow` を使い、既存 proof / 文献探索は `literature-survey` へ接続します。
- アルゴリズムの収束性、停止性、certificate soundness、finite-precision floor、solver-chain handoff に対してアルゴリズム選択や変更候補を探索するときは `algorithm-proof-exploration` を使い、最終 theorem / counterexample / unprovable-under-assumptions claim は `formal-proof-workflow` へ接続します。
- README、workflow、guide、migration、specification など、file responsibility が一般説明 prose の文書では `long-form-writing` を DSL-to-prose adapter として見ます。長さだけでは選びません。
- 論文、thesis chapter、scholarly note のような学術文章では `academic-writing` を先に見ます。
- paper section まで含む論文 draft では `paper-writing` を先に見ます。
- 研究系の task では `research-workflow` を outer loop に使います。
- tuning、探索、比較改善を backlog 付きで継続反復する task では `adaptive-improvement-loop` を outer loop にします。
- observable behavior、regression risk、または test contract を変える code 変更では `test-design` を使い、実装前に nasty case と regression case を先に固定します。contract-only wrapper は static contract validation と canonical command evidence を使います。
- 文書整理で正本、generated evidence、closed issue record、重複見出しを分けるときは `document-canon-cleanup` を使います。
- dependency manifest、reverse edge、cycle、full-repo manifest inventory、または修正対象の change-impact / repair-planning packet を作るときは `dependency-analysis` を使います。
- 大規模 refactor では `refactor-loop` を追加し、semantic delta を別管理にします。target 選定と subagent handoff の前に `dependency-analysis` の change-impact packet を正本入力にします。
- directory 構造、directory README、root view、path mapping、responsibility-scope map を責務ベースで変えるときは `structure-refactor` を追加し、recursive directory responsibility graph を先に作ります。
- ユーザーが 1 件ずつ共同デバッグする進め方を明示した場合は `user-guided-debugging` を使い、修正前の問題提示と修正後の次課題提示を固定します。
- C / C++ 差分では `cpp-review` を既定候補にします。
- OOP readability tool の実行、表出力、結果解釈はいずれも `oop-readability-check` を使い、出力内で `Mechanical Result` と `Agent Analysis` を分けます。
- tool、hook、eval、skill、experiment の結果を書き出すときは `result-artifact-writeout` を使い、raw result、summary、manifest、unique artifact path、overwrite policy を分けます。
- tool、checker、hook、static analysis、構造解析で問題を探して report / repair packet を作るときは `tool-finding-report` を使い、raw artifact、structured full artifact、mechanical priority order、任意の impact、prompt feedback decision を分けます。finding の取捨選択は上位 workflow が行います。
- skill / tool / workflow / hook / eval の蓄積ログを分析するときは `agent-log-analysis` を使い、raw JSONL の広域検索より先に compact summary を生成して読みます。
- accumulated eval family が missing / stale / fail のときは `agent-eval-accumulation` を使い、registered producer、compact checker、log archive sync の順に戻します。eval report を手で生成しません。
- PR を処理、merge、conflict 解消、ready 化、Issue triage、queue cleanup するときは `pr-processing` を使い、mutation authority、merge order、validation evidence、Issue action table を先に固定します。
- AgentCanon source、`vendor/agent-canon` pin、root runtime view、parent update TODO を更新するときは `agent-canon-update` を使い、source PR と parent pin 更新を分けます。
- agent-runtime 更新 branch や AgentCanon pin 更新の分離が必要なときは `agent-update-branch` を使います。
- reader-facing な report、status report、eval summary、audit summary、decision brief、presentation narrative、PPT storyboard を書くときは `report-writing` を使い、source packet、visual asset plan、Report Quality Checklist を固定します。
- 既存文章を graph 化し、段落接続、claim/evidence、experiment plan、split/merge/bridge/reorder operation、既存 skill handoff を出すときは `prose-reasoning-graph` を使います。
- report、experiment plan / report、Eval output、decision brief、presentation / PPT deck、HTML view、document、paper、refactor の構造が非自明な場合は、本文、renderer、run、編集の前に `structure-planning` を使い、primary artifact、source map、metric / delta contract、invalid interpretation を固定します。
- substantive な文書変更では `prose-reasoning-graph` と `structure-planning` を先に通し、typo / link / format-only では `md-style-check` と `structure_contract=skipped` の理由を evidence に残します。
- docs、reports、plans、workflow guides で process、dependency、ownership、routing、state、review gate、handoff が非自明な場合は、`structure-planning` の `visual_plan` で Mermaid 図を既定の primary visual 候補にします。
- report の既定出力は Markdown です。user が HTML、browser view、dashboard、web page、external browser publication を明示した場合だけ `html-output` を使い、layout、ImageGen、server reuse / start command、local / external URL を固定します。
- HTML で experiment / Eval 結果を表示するときは `html-experiment-report` を使い、primary figure、既存資産調査、責務境界、最小 renderer、ignored artifact 出力を固定します。
- stale worktree、古い `WORKTREE_SCOPE.md`、legacy action log を調査するときだけ `worktree-start` を使います。新規作業の kickoff や worktree 再開には使わず、scope drift や cleanup 判断は `worktree-health` を使います。
- optimizer、solver、preconditioner、gradient、Jacobian、Hessian、KKT、収束、tolerance、数値 benchmark を扱うときは `computational-optimization` を使い、数学契約と検証契約を実装や実験の前に固定します。
- JIT-canonical IR、生成済み Lean 実装定義、theorem graph overlay から、反復法と証明状態を Mermaid block chart にしたいときは `algorithm-flowchart` を使います。図は proof navigation であり、証明済み判定は formal proof checker に戻します。
- repo-wide な実装・文書・tooling・runtime の統合変更では、上の `comprehensive-development` route を使います。
- repo-wide な tool 導入や Docker / CI 更新案では `environment-maintenance` と `agents/templates/environment_change_proposal.md` を使います。
- `memory/USER_PREFERENCES.md` の整理や `AGENTS.md` への昇格では `user-preference-sync` を使います。
- `memory/AGENT_PHILOSOPHY.md` の更新や agent-side learning の整理では `agent-learning` を使います。

## Updating Skills

1. `agents/skills/<family>.md` を更新する
1. `agents/skills/catalog.yaml` を更新する
1. `.agents/skills/<family>/SKILL.md` を更新する
1. 必要なら `agents/canonical/CODEX_WORKFLOW.md` と `agents/canonical/CODEX_SUBAGENTS.md` の routing を更新する
