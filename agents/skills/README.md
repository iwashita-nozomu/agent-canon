# Shared Skill Canon

<!--
@dependency-start
contract skill
responsibility Documents Shared Skill Canon for this repository.
upstream design ./catalog.yaml enumerates public skill families
downstream design ../canonical/CODEX_WORKFLOW.md consumes the shared skill canon during task routing
downstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py validates public and official skill boundaries
@dependency-end
-->

このディレクトリは、public Codex skill 文書の人間向け正本です。
機械 discovery 用の `SKILL.md` は `.agents/skills/` を正本にします。

## Reader Map

- Purpose: index the public skill canon and explain the split between
  human-facing skill docs and runtime discovery shims.
- Section path: Rules and Skill Visibility Naming define naming and ownership;
  Public Skill Surface defines the catalog owner; Internal Review And Runtime
  Routines, Official System Skill Delegation, Codex Defaults, and Updating
  Skills define boundaries and maintenance.
- Use when: adding, routing, reviewing, or explaining public AgentCanon skills.
- Boundary: long skill behavior belongs in each `agents/skills/<skill>.md` and
  runtime discovery belongs in `.agents/skills/<skill>/SKILL.md`.

## Rules

- skill の目的、使う場面、関連正本は `agents/skills/` に書きます。
- `AGENTS.md` には長い skill 説明を複製しません。
- `.agents/skills/` は Codex の auto-discovery path です。
- 人間が skill を明示する場合は plain text ではなく `$skill-name` を使います。
- 例: `$research-workflow`、`$adaptive-improvement-loop`、`$paper-writing`
- 新しい public skill を追加するときは `catalog.yaml` と対応文書を同時に更新します。
- Workflow-routed internal routine は `agents/internal-routines/` に置きます。

## Skill Visibility Naming

ユーザー向け skill 名は `research-workflow` のような plain hyphen-case を使います。
catalog に登録し、この directory に文書化し、`.agents/skills/<skill>/SKILL.md`
から公開し、`.codex/config.toml` で有効化します。

runtime-internal skill shim は `_runtime-helper` のように先頭 underscore を使います。
owner surface は public catalog、public table、`.codex/config.toml` ではなく、呼び出し元の
workflow、role、public skill です。Codex runtime shim が必要な場合はこの lane を使い、
workflow-only material は `agents/internal-routines/` に置きます。

## Public Skill Surface

CLI に出す公開 skill は、user が直接選ぶ価値が高いものだけに絞ります。
review の細粒度 checklist、CLI adapter、artifact placement、validation helper は public skill ではなく canonical docs と subagent routing に寄せます。
workflow selection は task 開始時に使い忘れると実害が出るため、`agent-orchestration` を routing entry skill として public surface の先頭に置きます。
subagent bootstrap は repo-changing task の stage 分離に必要なため public skill として出します。

公開 skill の id、purpose、canonical doc、discovery shim、related skills、
prompt routing trigger は `agents/skills/catalog.yaml` が唯一の列挙正本です。
この README には catalog の行を複製しません。

確認入口:
- public skill の一覧と shim/doc/config の整合: `python3 tools/agent_tools/check_agent_runtime_alignment.py`
- prompt からの skill 選択: `python3 tools/agent_tools/route.py --prompt "<user request>" --format json`
- skill ごとの command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill <skill> --format text`

## Internal Review And Runtime Routines

- docs completeness、docs consistency、notation、logic gap、citation/evidence、critical/report、research perspective review は public skill ではなく、workflow が自動で要求する review pass として扱います。
- artifact placement、CLI adapter、static validation は `agents/internal-routines/`、`agents/canonical/`、`documents/REVIEW_PROCESS.md` の責務に寄せます。
- `.agents/skills/<skill>/SKILL.md` shim がない routine は `agents/internal-routines/` に置きます。AgentCanon public skill へ昇格するときだけ `agents/skills/` 文書、catalog entry、shim、AgentCanon-owned `.codex/config.toml` の `[[skills.config]]` を同じ変更で追加します。parent-owned skill は `.codex/project-config.toml` で有効化します。
- agent orchestration は public skill として先頭に出し、task 開始時に runtime が拾えるようにします。
- subagent bootstrap は public skill として出し、repo-changing task の stage separation で使います。
- carry-over の吸い上げは `notes/` と worktree log を正本にし、独立 public skill にはしません。
- Internal / compatibility review docs の一覧と route は [internal-routines/README.md](../internal-routines/README.md) に集約します。

## Official System Skill Delegation

OpenAI system skills stay host-provided. AgentCanon records routing triggers,
local evidence, and repo-specific contracts, while the official skill body stays
in the Codex host runtime.

| Official System Skill | AgentCanon Route |
| --- | --- |
| `$openai-docs` | Current OpenAI / Codex product docs, model guidance, API reference, and Codex manual source route. |
| `$skill-creator` | Skill creation, skill refactor, and skill instruction quality work after AgentCanon fixes the local owner surface. |
| `$skill-installer` | External skill installation and curated skill listing. |
| `$imagegen` | Bitmap visual asset generation for HTML, reports, dashboards, or visual mockups. |
| `$plugin-creator` | Codex plugin scaffold, manifest defaults, marketplace entries, and plugin reinstall flow. |

## Codex Defaults

- AgentCanon public skill discovery is wired through official Codex `[[skills.config]]` entries in AgentCanon-owned `.codex/config.toml`; every `.agents/skills/<skill>/SKILL.md` shim must be enabled there.
- Parent repositories may add repo-specific skills in
  `.codex/project-skills/<skill>/SKILL.md` and wire them with additional
  `[[skills.config]]` entries in parent-owned `.codex/project-config.toml`.
  Do not put parent-specific skills under
  AgentCanon-owned `.agents/skills/`; that directory remains catalog-backed
  shared canon.
- AgentCanon-owned public skills appear in `catalog.yaml`; official system skills stay in the host-provided lane above.
- Codex では `AGENTS.md` と `agents/canonical/CODEX_WORKFLOW.md` を先に読み、repo task の skill 選択は `$agent-orchestration` から始めます。
- task ごとの skill 選択は `python3 tools/agent_tools/route.py --prompt "<user request>" --format json` の `ACTIVE_SKILLS` / `DEFERRED_SKILLS` を第一候補にし、このディレクトリと `catalog.yaml` は skill の責務確認に使います。
- user が skill を明示したい場合は `$skill-name` の形を既定にし、曖昧な prose より優先します。
- template clone から新 repo を始めるときは `start-repository` を使います。
- 長い tool / skill 候補名を短い command に落とすときは `task-routing` を使います。
- specialist を使う場合の Codex-specific routing は `agents/canonical/CODEX_SUBAGENTS.md` を見ます。
- repo-changing task では `$agent-orchestration` から始めます。owner boundary、差し替え可能な単位、validation route、public impact boundary が evidence で閉じている修正では `$owner-bounded-routing` を使い、execution stage で `$codex-task-workflow`、handoff / wave が ready になった stage で `$subagent-bootstrap` を追加します。
- 文献調査が主タスクなら `literature-survey` を先に見ます。
- 自然言語の数学的 claim を形式証明へ落とすときは `formal-proof-workflow` を使い、既存 proof / 文献探索は `literature-survey` へ接続します。
- 実装前にアルゴリズムを設計する場合は `lean-algorithm-design` を使い、Lean 上の数学モデルと target theorem を先に検証してから production API へ渡します。
- 既存実装または実装候補の収束性、停止性、certificate soundness、finite-precision floor、solver-chain handoff に対してアルゴリズム選択や変更候補を探索するときは `algorithm-proof-exploration` を使い、最終 theorem / counterexample / unprovable-under-assumptions claim は `formal-proof-workflow` へ接続します。
- README、workflow、guide、migration、specification など、file responsibility が一般説明 prose の文書では `long-form-writing` を DSL-to-prose adapter として見ます。長さだけでは選びません。
- 論文、thesis chapter、scholarly note のような学術文章では `academic-writing` を先に見ます。
- paper section まで含む論文 draft では `paper-writing` を先に見ます。
- 研究系の task では `research-workflow` を outer loop に使います。
- tuning、探索、比較改善を backlog 付きで継続反復する task では `adaptive-improvement-loop` を outer loop にします。
- 実験 topic の review、`run.py` 直実行、GPU/JAX 環境所有、artifact schema、notebook readiness を確認するときは `experiment-review` を使います。
- observable behavior、regression risk、または test contract を変える code 変更では `test-design` を使い、実装前に nasty case と regression case を先に固定します。contract-only wrapper は static contract validation と canonical command evidence を使います。
- owner boundary、差し替え可能な単位、validation route、public impact boundary が evidence で閉じている修正、typo / link / format-only、Routine docs、Focused code では `owner-bounded-routing` を使い、existing tool を読了 gate なしに先に実行し、owner boundary、existing-tool route、targeted validation を evidence に残します。file 数だけでは route を固定しません。
- 文書整理で正本、generated evidence、closed issue record、重複見出しを分けるときは `document-canon-cleanup` を使います。
- dependency manifest、reverse edge、cycle、full-repo manifest inventory、または修正対象の change-impact / repair-planning packet を作るときは `dependency-analysis` を使います。
- 大規模 refactor では `refactor-loop` を追加し、semantic delta を別管理にします。target 選定と subagent handoff の前に `dependency-analysis` の change-impact packet を正本入力にします。
- directory 構造、directory README、root view、path mapping、responsibility-scope map を責務ベースで変えるときは `structure-refactor` を追加し、recursive directory responsibility graph を先に作ります。
- ユーザーが 1 件ずつ共同デバッグする進め方を明示した場合は `user-guided-debugging` を使い、修正前の問題提示と修正後の次課題提示を固定します。
- C / C++ 差分では `cpp-review` を既定候補にします。
- OOP readability tool の実行、表出力、結果解釈はいずれも `oop-readability-check` を使い、出力内で `Mechanical Result` と `Agent Analysis` を分けます。
- tool、hook、eval、skill、experiment の結果を書き出すときは `result-artifact-writeout` を使い、raw result、summary、manifest、unique artifact path、overwrite policy を分けます。
- tool、checker、hook、static analysis、構造解析で問題を探して report / repair packet を作るときは `tool-finding-report` を使い、raw artifact、structured full artifact、mechanical priority order、任意の impact、prompt feedback decision を分けます。finding の取捨選択は上位 workflow が行います。
- skill / tool / workflow / hook / eval の蓄積ログを分析するときは `agent-log-analysis` を使い、raw JSONL の広域検索より先に structured summary を生成して読みます。
- structured summary、prompt excerpt、run bundle、hook / routing / eval evidence から durable skill issue 候補を作るときは `issue-finding-report` を使い、抽象原因、重複検索、dependency-expanded edit scope、multi-agent partition を先に固定します。
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
- HTML で experiment / Eval 結果を表示するときは `html-experiment-report` を使い、primary figure、既存資産調査、責務境界、report-specific renderer、ignored artifact 出力を固定します。
- stale worktree、古い `WORKTREE_SCOPE.md`、legacy action log を調査するときだけ `worktree-start` を使います。新規作業の kickoff や worktree 再開には使わず、scope drift や cleanup 判断は `worktree-health` を使います。
- optimizer、solver、preconditioner、gradient、Jacobian、Hessian、KKT、収束、tolerance、数値 benchmark を扱うときは `computational-optimization` を使い、数学契約と検証契約を実装や実験の前に固定します。
- GPU / CUDA / JAX / XLA / IREE backend 実行、`CUDA_VISIBLE_DEVICES`、`nvidia-smi`、JAX preallocation 無効化、GPU validation blocker を扱うときは `gpu-execution` を使い、Python 実行は ExperimentRunner に委譲します。
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
