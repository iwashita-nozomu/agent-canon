# Codex Implementation

<!--
@dependency-start
contract agent-runtime
responsibility Owns design admission, implementation scope, dependencies, and implementation execution.
upstream design ./CODEX_WORKFLOW.md conditional task-phase reader map
upstream design ../../documents/design/entrypoint-owner-map.md document responsibility split
@dependency-end
-->

Read the selected section for design or implementation work.
Return to [Codex Workflow](CODEX_WORKFLOW.md) for phase selection; do not
load inactive phases or restart completed intake merely by following a link.

## 契約完全実装

実装 behavior は request clauses、acceptance contract、
`Implementation Source Packet`、`Design-To-Implementation Trace`、
dependency-expanded scope、validation route、review gate から導きます。
見た目の広さ、owner-bounded route、MVP、thin slice は暫定的な routing、
wave、validation profile の signal に留めます。owner boundary や impact surface が
違うと分かった時点で route を更新します。

repo-changing run では `team_manifest.yaml` の
`run.contract_complete_implementation_policy` を handoff packet に含めます。
`bootstrap_agent_run.py` の
`IMPLEMENTATION_COMPLETENESS_POLICY=contract_complete` を起動時 evidence として
扱います。contract gap、責務境界、API shape、依存方向、runtime contract の不足は
`design_issue_blocker` として Gate 5-6 に戻します。

## Design Integrity Gate

実装前の設計判断は、近い file、現在の finding、会話印象ではなく
owning responsibility model から始めます。選択した typed route が full staging を
要求する場合は、`Abstract Design Frame`、`Implementation Source Packet`、
`Design Side-Effect Map`、`Design-To-Implementation Trace` をそろえます。親は edit
authorization を持たず、catalog の `workflow_activation_policy` と選択 family の
role/stage records に従って child handoff の packet と gate を選択・relay します。
Child or tool blockers remain typed blocked/retry/user-report evidence; the parent does not
perform a direct write as a fallback.
Gate 6 の detailed design review は、owner/design boundary、API shape、仕様解釈、
または別の unresolved claim が owning review gate では判定できない場合だけ選択します。
設計文書の存在だけでは別 review stage や artifact を生成しません。reviewer output は
hypothesis であり、decision-owning reviewer が current source snapshot、reachable
input/control path、contract、witness/static proof を確認して adjudicate します。

実装前の design gate は、run manifest の `run.active_design_packet` を唯一の
artifact ownership source とします。schema は `waterfall.design_packet.v1` で、
design artifact、technical design review、document-flow review の相対 path と
`document_flow_required` を必須にします。generator の precedence は、explicit
run `--active-design-packet` input、workflow-specific record、standard
`agents_config` artifact registry の順です。generator は選択 record を生成済み
run manifest に永続化し、以後その manifest が persisted authority になります。
gate は persisted manifest の `run.active_design_packet` を唯一の runtime input として
読み、manifest-declared path だけを active artifact route として消費します。
active packet の source reference には、同じ run bundle にある
`semantic_responsibility_contract.toml` を `artifact:` reference として含めます。
この instance は実装前に semantic delta、implementation action、obligation、一次検証
owner、supporting property/role、hard-edge closure を割り当てるために使います。
missing / unknown field / unknown schema / invalid field / outside-bundle path は typed blocker として
design owner に戻します。implementation handoff は、manifest-declared design artifact、
両 review の一致する `Design artifact path:`、review dispatcher の normalized decision、および required
な document-flow approval を要求します。

API shape、責務境界、path layout、命名、アルゴリズム、test oracle、依存方向、
runtime contract、config surface の判断が未確定なら、実装吸収ではなく
`design_issue_blocker=<issue>` と evidence を残して Gate 5-6 へ戻ります。local
fallback、wrapper、helper、branch、alternate route、test relaxation、docs
overwrite、implementation shortcut は Design Integrity Gate の外側です。

## Edit Execution Surface

Repo file edits use the responsibility-preserving execution surface:

1. 手編集で責務を追える編集は patch-based edit を使います。
1. 機械生成・一括変換・format は repo 内の script / formatter / generator を使います。
この選択は編集手段の選択です。対象範囲の正本は `requested_scope` に残します。
作業 log / run bundle には、`requested_scope`、選んだ `work_scope`、外した surface
の理由を必要な粒度で残します。user update では、既定から外れる編集手段を使う場合、
tool availability が作業判断に影響する場合、または user が編集手段を質問した場合に説明します。

## Library And Reuse Sweep

新しい code path、module、helper、test、script を足す前に、導入済みライブラリと既存の再利用候補を探索します。
dependency surface は task に応じて次を見ます。

- `docker/requirements.txt`
- `pyproject.toml`
- lockfile
- build file
- package manager file
- 必要なら `pipdeptree` / `deptry`

既存実装の探索対象は task に応じて次です。

- `python/`
- `tests/`
- `src/`
- `include/`
- `lib/`
- `scripts/`

既存実装がある場合は、その module を拡張または再利用します。
新規追加は、既存ライブラリや既存実装で足りない理由を既存の reuse survey に残してから選びます。
reuse survey は prose/status だけでなく、known な asset と test context を持つ advisory
handoff context です。worker は選択済み asset と tests から読み始めます。

## File Dependency Manifest

新規作成・編集する canonical design / workflow / tool / policy / template text file では、ファイル冒頭に `@dependency-start` / `@dependency-end` marker を持つ dependency manifest block を置きます。Routine notes、generated reports、closed issue records、archive / compatibility records は scanner の classification に従います。
設計正本は [documents/design/dependency-manifest-design.md](../../documents/design/dependency-manifest-design.md) です。
旧 `Dependency Files:` block は新規・変更 file では使いません。

- manifest の内部 DSL は `<direction> <kind> <relative-path> <reason...>` です
- `direction` は `upstream` または `downstream` です
- `kind` は `design`、`implementation`、`environment` です
- path は manifest を持つ file から見た相対 path です
- 依存として書くのは、その file を理解・実行・検証するために読むべき repo 内の正本 file です。dependency list は実際の責務関係に基づけます
- upstream は「編集前に読む file」、downstream は「編集後に影響確認する file」として分けます
- 依存が無い direction は行を置きません。`none` placeholder は置きません
- Markdown は title 直後、Python / shell / TOML / YAML など comment 可能な file は shebang / encoding marker 直後、C-like file は先頭 comment block に置きます
- line comment しかない format では `# @dependency-start` のように line comment wrapping を使います
- commentless format や generated / binary / vendored external file は scan tool の分類に従い、必要なら同じ変更の design / manifest / README に理由を残します

編集 workflow:

1. 変更対象 file の manifest を先に読み、upstream edge の target を編集前 context として読む
1. manifest が無い checkable file を編集する場合は、同じ差分で `@dependency-start` block を追加する
1. downstream edge を持つ file を編集した場合は、差分後に downstream target を確認する
1. 新しい dependency edge を足す場合は、同じ変更で reverse edge も足すか、migration 中で足せない理由を review artifact に記録する
1. subagent handoff には `dependency_manifest_plan` と dependency header graph の再帰展開結果を含め、編集対象ごとの upstream / downstream edge、`dependency_edit_scope.txt` / `dependency_graph.tsv`、読む順序を handoff packet に載せる

closeout 前に、少なくとも次を実行します。

```bash
python3 tools/validation/semantic/dependencies/check_dependency_headers.py --changed
bash tools/analysis/dependencies/scan_dependency_headers.sh --changed --fail-missing
bash tools/validation/semantic/dependencies/check_dependency_header_format.sh --changed --require-header
```

dependency edge を追加・変更した場合は次も実行します。

```bash
bash tools/analysis/dependencies/check_dependency_graph.sh --print-edges
```

`check_dependency_graph.sh` は upstream graph と downstream graph を別々に扱い、自己参照、reverse edge、kind mismatch、cycle を検証します。
移行期間中に repo 全体の既存 graph failure が残る場合でも、新規・変更 file は現行形式と reverse-edge を満たして closeout します。

## 5. Implementation

- 実装は `$codex-task-workflow` と選択された task-family Skill の owner route に従って進める
- SEP-09 を適用し、implementation は開始前に固定した complete target state から導く。waves は定義済み work の順序だけを決め、target state を後から完成させる段階実装にはしない。禁止事項と scope exception の詳細は SEP-09 を参照し、この workflow は policy を複製しない
- selected gate の次段移行では `waterfall_gate_check.py` を通し、`WATERFALL_GATE_READY=yes`
  でない場合は指示された owner stage へ戻る
- 実装前に `design_brief.md` の `Abstract Design Frame`、`Installed Libraries And Existing Implementation Survey`、`Implementation Source Packet`、`Design Side-Effect Map`、`Design-To-Implementation Trace` を読み、抽象責務と概念 model から実装 slice と downstream side effect が導かれていることを確認してから、そこにある artifact、repo docs、dependency surface、code path を読了する。test plan は、active workflow または touched surface が post-implementation test design を選択し、その activation により `test_plan.md` が生成されたか必須になった場合のみ読了する
- 実装前に既存 handoff の `reuse_survey` を読み、known な selected asset とその
  tests を worker の開始 context にする。split / extraction では splitter の
  current+git-history 調査結果と、同一 asset を触る slices の consolidation を
  全 child に同じまま渡す。
- selected design review がある場合だけ、実装前に `design_review.md` を読み、
  `Design Artifact Under Review` が現在の `design_brief.md` を指し normalized decision が
  承認であることを確認する。設計を修正した後は selected Gate 6 で現行設計を
  adjudicate し直す
- selected design review がある run では、write-capable handoff route の前に
  `pre_handoff_gate_status` へ review dispatcher の normalized decision と
  `waterfall-gate-check --gate design` pass evidence を記録する。candidate artifact
  は記録や handoff を自動的に要求しない
- 詳細設計前に `bootstrap_agent_run.py` の `DESIGN_DOCUMENT_PACKET` を読み、その path 群を `design_brief.md` の `Upstream Requirement Packet` に転記する
- 詳細設計では `design_brief.md` の `Canonical Tree-Head Plan` に、この task の後に tracked tree に残してよい設計文書 path と実装 path を固定し、parallel design doc、implementation copy、snapshot、backup path を残さないことを明記する
- worker の実装入力は、各 implementation slice の前に明示された design artifact path、design section、request clause ID です。test plan item は、active workflow または touched surface が post-implementation test design を選択し、その activation により `test_plan.md` が生成されたか必須になった場合のみ実装入力に含めます
- worker は docs、workflow、prompt/config、validation output、dependency manifest、user-facing surface へ波及する変更を `Design Side-Effect Map` の item として扱い、implementation summary に owner stage と review gate を残す
- `Abstract Design Frame`、`Installed Libraries And Existing Implementation Survey`、`Implementation Source Packet`、選択された場合の承認済み `design_review.md`、design gate check、および design と現行 repo docs / code / dependency surface の整合が揃った時点で実装へ進む。design review が未選択なら semantic decision sufficiency と owner validation evidence を使い、欠けた場合だけ Gate 5-6 へ戻る
- 実装中に design issue が見つかった場合は、`design_issue_blocker=<issue>`、evidence、候補 option を artifact または structured handoff に残し、Gate 5-6 へ戻す。API shape、責務境界、path layout、命名、アルゴリズム、証明対象、test oracle、依存方向、runtime contract、config surface の欠落や矛盾は設計側で解決します。run bundle が無い bounded task は、catalog の typed route が要求する場合だけ write-capable child packet を作って継続します
- `design_issue_blocker` は local fallback、wrapper、helper、分岐、別経路、test 緩和、docs 上書きではなく、Gate 5-6 の設計更新で閉じる。承認済み design と局所 precedent から一意に導ける typo、format、import、狭い機械的追従だけが同じ implementation pass で修正できる
- legacy-route drift と duplicate implementation は implementation GuardRail finding として扱い、旧 route、旧 wrapper、旧 helper、config mirror は caller migration で canonical owner へ統合する
- implementation は current tree head の canonical path だけを更新対象にし、`*_old`、`*_copy`、dated clone、parallel module、duplicate directory のような別 truth surface を作らない
- `bootstrap_agent_run.py` の `IMPLEMENTATION_CODEX_AGENTS=worker,spark_worker` を確認し、catalog の typed route が要求する implementation work だけを write-capable handoff で進める。`worker` が既定で、`spark_worker` は Abstract Design Frame、design trace、naming、test-plan artifact / evidence（active workflow または touched surface が post-implementation test design を選択し、その activation により `test_plan.md` が生成されたか必須になった場合のみ）、dependency-expanded handoff scope に加え、`--select-agent-type implementer=spark_worker:<evidence>` が stdout / manifest に記録された場合だけ使います。選択済み candidate が blocked の場合は typed blocker を記録し、親は実行しません。
- 新規または rename する file、function、class、theorem、artifact、CLI flag、
  config key は、implementation handoff 前に naming plan で固定する。naming plan は
  対象概念、責務語彙、既存 naming family、採用名、avoid-name list を含み、
  [documents/rule/naming.md](../../documents/rule/naming.md) と言語別規約を参照します。
  名前が未確定な場合は Gate 5-6 へ戻り、worker handoff 前に naming plan を確定します
- 明示 spawn 許可がある場合、実装前の repo inventory と tool drift survey は Luna/high の通常 role TOML へ、static validation failure triage と diff-local language review も該当 decision がある場合だけ `gpt-5.6-luna/high` review role TOML へ渡します。`gpt-5.4-mini/medium` は明示 T14 `skill_evaluation` の fresh read-only artifact-only `skill_evaluator` に限り、permanent team role にはありません。`worker` は `gpt-5.6-luna/xhigh` の既定 implementer で、typed parent-packet selection がある機械的 slice だけ `spark_worker` へ渡します。`.codex/config.toml` の `gpt-5.6-sol/high` parent は統合判断と次 gate 判定に集中します
- `spark_worker` を選択できる実装は、Abstract Design Frame から導かれた差し替え可能な単位で、public interface 変更なし、依存追加なし、仕様解釈なし、既存 test / docs の局所更新で閉じる slice だけにする。design trace と dependency-expanded handoff scope は必要 evidence であり、実際の選択には `--select-agent-type implementer=spark_worker:<evidence>` が必要です。
- 実装 subagent を起動するときは `IMPLEMENTATION_DOCUMENT_PACKET` の path 群を明示入力し、chat 要約ではなく packet path を読ませる
- すべての stage subagent を起動するときは `team_manifest.yaml` の `run.subagent_prompt_packet` と該当 role の `prompt_contract` を local/tool context 参照として扱い、prompt には選択済み `Fresh Subagent Context Capsule` fields を入れる
- `spark_worker` は design trace と dependency-expanded handoff scope が揃い、typed parent-packet selection が記録された bounded implementation slice にだけ使い、設計判断、scope 判断、review 判断は frontier owner / reviewer に残す
- chunk、slice、checkpoint、subpass の後は remaining planned work units と next gate を確認してから続行する
- repo-changing task では selected durable coordination/resumption route がある場合だけ current checkout の run bundle `work_log.md` を継続更新し、それ以外は structured handoff/tool-result evidence を使う
- 新規作業は current checkout で kickoff します。`WORKTREE_SCOPE.md` と `worktree_scope_lint.py` は legacy cleanup / drift diagnosis 専用です
- stale な `WORKTREE_SCOPE.md`、別 branch、別 path の action log を見つけた場合は、current checkout の `work_log.md` に観測事実と扱いを残す
- selected review の instance reuse / separation と implementation 着手条件は、semantic owner route と `.codex/agents/*.toml` の runtime projection に従う。同一責務・同一 context の review は再利用し、distinct unresolved claim/risk の場合だけ分ける
- 包括的開発では `project_reviewer` を intake と closeout に追加し、repo-wide な integration risk を確認する
- 文書主体の成果物では `document_flow_reviewer` を通し、上から順に読んだときの意味の通り方を確認する
- README、workflow、guide、migration、specification など file responsibility が一般説明 prose の文書で reader-facing 構成を変える場合は `long-form-writing` を DSL-to-prose adapter として読み、docs-impact がある distinct unresolved reader-path claim を owning gate が判定できない場合だけ `docs-completeness-review` を追加する
- 論文、thesis chapter、scholarly note のような学術文章では `academic-writing` を読み、notation / logic reviewer は distinct unresolved claim が owning gate の範囲を超える場合だけ選択する
- 投稿論文や thesis chapter の draft では `paper-writing` を読み、citation evidence reviewer は distinct unresolved citation claim が残る場合だけ追加する
- contract-only wrapper や checker-owned validation だけの変更では、static contract validation と canonical command evidence を validation route に置く。
  Approved typed contract evidence remains the completion criterion.
- validation tool の autofix は changed contract、changed lines、または task plan が名指しした checker-owned property に結び付く finding に適用し、広い validation で出た既存 style debt は residual evidence と repair route に分ける
- 研究・実験系の変更では active experiment profile の risk に応じて `report_reviewer` と research perspective reviewers を選ぶ
- JAX export / native runtime の task では、対象 implementation slice で `generic callable path`、`specialized coeff path`、`export-based generic path` のどれを触るか宣言する。generic path は `jax.export` artifact producer と consumer/runtime smoke を完了条件に含める
- cross-process export worker には serializable manifest と reconstruction recipe を渡す
- `LoadedProgram` のような runtime materialization は runtime vertex / lifetime scope として扱う
- まず導入済みライブラリ、既存 code path、既存 helper、既存 style を調べ、再利用と拡張を優先する
- 新規 helper や新規 module を足すときは、既存実装で足りる範囲と、導入済みライブラリの設定変更や薄い wrapper で足りる範囲を design packet に結び付ける
- worker は approved design または明白な局所 precedent に由来する variable、function、class、file、CLI flag、config key、public API identifier を使う
- implementation slice は contract-complete implementation として閉じる。request clause、acceptance contract、Implementation Source Packet、validation route を結び、implementation shortcut を見つけたら `design_issue_blocker` と evidence で design review へ戻す
- checkpoint review は diff だけでなく Abstract Design Frame、approved design packet、Design Side-Effect Map、source packet citation の一致を確認する
- role ごとの model / reasoning 設定は `.codex/agents/*.toml` に従う
- implementation の既定 candidate は `gpt-5.6-luna/xhigh` の `worker` とし、review / quality-check は active decision ごとに一つの `gpt-5.6-luna/high` role を選びます。Abstract Design Frame と design trace から導かれた機械的 slice は explicit parent-packet selection がある場合だけ `spark_worker` を使い、execution-only experiment / log work は Luna/high の `experiment_runner` に渡します。mini/medium は明示 T14 `skill_evaluation` の `skill_evaluator` だけです。
- parent-managed write-scope rule は `worker.toml`、`spark_worker.toml`、planning / reviewer TOML、`team_manifest.yaml` を正本にする
- 正本は `agents/` と `documents/` から先に直す
- runtime entrypoint は薄く保つ
- skill は repo 正本を置き換えず、導線だけを担う
