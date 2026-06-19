# refactor-loop
<!--
@dependency-start
contract skill
responsibility Documents refactor-loop for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable refactor structure contract
upstream design dependency-analysis.md unified change-impact and repair-planning packet
upstream design tool-finding-report.md tool-based finding packet and prompt feedback loop
upstream implementation ../../tools/agent_tools/check_design_doc_claims.py emits design evidence findings for refactor plans
@dependency-end
-->


## Purpose

大きめの refactor を、feature 追加ではなく挙動保存つきの再編として扱います。

## Use When

- file 分割、rename、module 境界整理
- 依存方向の整理
- implementation の差し替えを伴う構造再編
- branch 側で file 構成変更を含む整理

## Core References

- `agents/TASK_WORKFLOWS.md`
- `agents/workflows/implementation-waterfall-workflow.md`
- `agents/workflows/comprehensive-refactoring-workflow.md`
- `documents/REVIEW_PROCESS.md`
- `agents/workflows/main-integration-workflow.md`

## Required Contract

1. refactor-loop の対象 file は、最初に user が指した file だけで固定しません。
   まず依存解析で requested object / file から到達する依存 file、依存元 file、
   関連 test / docs / validation command を展開し、その dependency-expanded scope 全体を候補集合に
   します。実装対象は、その展開済み scope 内で関数、method、class 単位に
   絞り込んでから決めます。
1. target 選定、`Refactor Orchestration Plan:`、write-capable subagent handoff
   の前に、`dependency-analysis` で token-light な `Change Impact Packet:`
   manifest を作ります。この packet は code dependency、header dependency、
   search surface、structural finding、tests / docs / config / log / Info
   surface、unknown dynamic edge をまとめた修正計画の入力ですが、full graph を
   LLM prose 化する場所ではありません。raw artifact は path と count で参照し、
   current repair batch に必要な excerpt だけを載せます。raw finding、raw
   `rg` hit、単一 file 名だけから実装計画を作ってはいけません。
1. refactor pass では `Behavior Contract:` を先に固定します。
1. file moves、module boundary、repair slice、path mapping、responsibility map が非自明な場合は `structure-planning` で構造 contract を先に固定します。
1. `Allowed Structural Delta:` と `Forbidden Semantic Delta:` を分けて書きます。
1. API 形状を変える refactor では `Expected API:` を先に固定します。
   ここには public names、call shape、config field、削除する互換 surface、
   subagent が従うべき利用例を含めます。subagent handoff にはこの
   `Expected API:` を必ず渡します。
1. user-facing return までの内部 step では、途中状態を毎回動作可能に保つための
   分割や per-step operation check を要求しません。期待 API と対象 call site を
   一貫して更新し、最後の return gate で intended API 全体を検証します。
1. 実装前に `Targets To Change:` として、変更する関数、method、class を
   `path:start-end:qualname` で列挙します。file や module だけを target にして
   実装へ入ってはいけません。
1. 新機能追加は同じ pass に混ぜません。必要なら先に分離します。
1. delete、rename、move、module split は `Files To Remove Or Move:` として先に列挙します。
1. old path と new path の対応を `Path Mapping:` として残します。
1. 大規模 repo では `Current Responsibility Map:` と `Target Responsibility Map:` を先に作り、OOP 的に責務、状態、契約、adapter を最小境界へ分けます。
1. full tool finding、mechanical priority order、baseline packet、任意の impact、repair packet は `tool-finding-report` を使って固定し、その後 `dependency-analysis` の `Change Impact Packet` に統合します。
   design document が refactor rationale を持つ場合は、`check_design_doc_claims.py` の finding も同じ packet に入れ、implementation-backed claim、parent-doc alignment、assumption ledger の evidence gap を repair slice の入力にします。
1. implementation subagent を起動する前に、親 agent が dependency graph から
   `Refactor Orchestration Plan:` を作ります。依存の根本に近い sequential root
   slice と、root 修正後に並列化できる independent downstream slice を分け、
   各 target object に owner wave、`blocked_by`、allowed files、validation
   signal、single-agent / parallel-safe の判定を付けます。
   `structure-refactor` が構造 surface 分類、root/scope contract、path mapping、
   runtime boundary を所有し、この skill が repair batch sizing、`blocked_by`、
   sequential / parallel wave choice、write-capable subagent orchestration を所有します。
1. repair scope の粒度は、file / function / class に固定しません。
   `Change Impact Packet` の `scope_candidates` から、wave 数、tool rerun 数、
   write conflict risk、token budget、validation cost、semantic risk を見て
   `selected_scope` を選びます。behavior contract が保てて、1 つの coherent な
   validation surface で確認できるなら、大きい block を選んで構いません。
1. implementation の既定単位は finding 1 件ではなく、dependency-expanded repair
   batch です。同じ責務 group、同じ dependency wave、同じ validation surface に
   属し、機械的に安全に直せる target object は 1 つの handoff にまとめます。
   finding 1 件だけの handoff は、root/shared contract、semantic risk、または
   関連 target を `review_required` / deferred と記録した場合に限ります。
1. implementation slice 後は、latest `git diff` と full finding packet を突き合わせた
   `Diff Linked Findings:` を作ります。変更 file、diff hunk 行範囲、
   finding の `path` / `line` / structural `instances` / `representatives` /
   dependency signal を使い、変更行に直接乗る finding、同じ変更 object に属する
   related structural finding、変更外 finding を分けます。
1. 外部 repo や bare snapshot の OOP survey では、元 repo を編集せず、commit SHA、解析 path、`--exclude vendor --exclude reports` などの除外条件、Markdown / JSON report を run bundle に残します。
1. implementation 前に `test_designer` で regression case と nasty case を固定します。
1. 既存 test が薄い場合は baseline capture を追加してから rework します。
1. closeout 前に `python3 tools/ci/check_merge_structure.py ...` の要否を確認します。

## Canonicalization-First Refactors

Stopping、logging、runtime tolerance、preconditioner など、複数 algorithm
から参照される policy / base abstraction を一本化する refactor では、依存先を
先に個別修正しません。最初の slice は正本 surface の確定に使います。

1. `Canonical Surface:` として、責務を持つ module、public object、Info / State
   / SolveConfig ownership、既存 primitive helper の扱いを固定します。
1. `Expected API:` として、正本化後に caller が使う import path、config field、
   initialize-time policy、削除する legacy alias / helper を明示します。この
   expected API は write-capable subagent と reviewer の context に含めます。
1. `Targets To Change:` には canonical surface を構成する関数、method、class を
   `path:start-end:qualname` で列挙します。利用側の全置換を同じ最初の slice に
   混ぜません。
1. `Forbidden Semantic Delta:` には、停止条件、tolerance 解決、ログ項目、数値
   residual の定義を変えないことを明記します。意味を変える必要がある場合は
   refactor pass ではなく design / algorithm pass に分離します。
1. canonical surface を直したら、dependency scan、call-site scan、algorithm
   contract check、OOP/readability scan を再実行し、利用側の `repair_slice`
   を作ります。
1. 利用側は、最も依存の深い algorithm から順に、primitive helper 直接呼び出しを
   canonical object 呼び出しへ置き換えます。専用 wrapper を caller ごとに増やす
   ことを既定解にしてはいけません。
1. 1 つの利用側 slice を直すたびに全走査を再実行し、残り finding が正本
   abstraction へ収束しているか確認します。

## Dependency-Guided Repair Slice Loop

構造重複、OOP readable finding、module boundary finding など、依存関係で
修正順を決める refactor では、単発の上位一覧を一括修正しません。次の
repair-slice loop で 1 slice ずつ進めます。

1. `tool-finding-report` で解析 tool の raw result、structured artifact、
   `priority_order`、`repair_slice` を生成します。
   Python structural duplicate では次を既定入口にします。
   `python-structure-hash` -> `python-structure-hash-report`
1. `tool-finding-report` の結果はそのまま実装者へ配らず、`dependency-analysis`
   に渡して token-light な `Change Impact Packet` manifest を作ります。ここで code dependency、
   header dependency、search scope、structural finding、tests / docs / config /
   log / Info surface、unknown dynamic edge を統合し、tool-generated
   `impact_blocks`、`repair_batches`、`subagent_handoff_context` を固定します。
   Python structural finding では既定で
   `agent-canon python-structure-hash-scope-plan --input <report.json> --dependency-report-dir <dependency-review-dir> --output <change-impact-packet.json>`
   を使い、親 agent が手作業で block 化しません。
1. `repair_slice.root_finding` は今回の修正 batch の根を示します。実装単位は
   root finding 1 件に固定せず、同じ home/downstream group と dependency wave
   にあり、同じ責務で同時に消せる related finding / target object を batch に
   含めます。
1. `repair_slice.preferred_home_group` を共通化候補にします。ただし、
   その group の設計責務に合わない helper / base / protocol / alias を追加
   してはいけません。
1. `repair_slice.affected_downstream_groups` と `affected_files` を call-site /
   downstream 修正候補として読みます。
1. `repair_slice.related_findings` に同じ home/downstream group の finding が
   あれば、同じ責務で同時に消せるものは原則同じ pass に含めます。含めない場合は
   `review_required`、semantic risk、validation 分離、または blocked dependency
   として理由を orchestration plan に残します。
1. root finding が薄い marker class、例外型、Protocol、型 alias、config
   marker など複数責務をまたいでいる場合は、共通化せず
   `review_required` として次の actionable slice に進みます。
1. 修正は依存 graph の根本側へ寄せます。呼び出し側ごとの専用 helper 増設を
   既定解にしてはいけません。
1. 根本 group の既存責務で足りる場合は既存実装を拡張します。責務拡張が必要な
   場合は親 repo の設計文書を先に更新します。責務が合わない場合は、直近の
   共通 ancestor group か現状維持を選び、理由を report に残します。
1. 1 slice を修正したら必ず全走査を再実行します。差分 finding だけで次の
   slice を判断してはいけません。
1. 再走査前後の判断材料として、latest `git diff` を full finding packet に
   join した `diff_linked_findings` artifact を作ります。最低限、次を分けます。
   - `direct_changed_findings`: diff hunk の変更行に finding location が重なるもの
   - `related_structural_findings`: 変更した関数、method、class、またはその
     structural `instances` / `representatives` / dependency group に属するもの
   - `unchanged_scope_findings`: full report には残るが今回 slice の変更範囲外のもの
   この artifact は reviewer handoff と次 slice 選択の入力にします。
1. 再走査後の `priority_order` と `repair_slice` を新しい正本として、次の
   slice を選びます。

この loop では、機械的な順序決定と人間/agent の設計判断を分離します。
tool は候補と影響面を出し、実装者は責務境界に反する共通化を拒否します。

## Finding Packet And Prompt Feedback

refactor-loop は tool 実行と finding report の詳細手順を自分で複製しません。
実装前と各 slice 後に `tool-finding-report` を使い、full finding packet、
mechanical priority order、baseline、必要に応じた impact、prompt feedback
decision を作ります。

1. write-capable subagent への handoff には、`dependency-analysis` が作った
   `Change Impact Packet` path、`tool-finding-report` が作った finding packet
   path、current `repair_slice`、repair batch に含める全 target object、
   `Forbidden Semantic Delta`、新規 finding を増やさない制約を含めます。
1. write-capable subagent への handoff は token-bounded にします。必ず exact
   target objects、allowed files、object-by-object repair intent、
   forbidden semantic delta、test commands、final response format を指定します。
   repair intent では、各 target object ごとに current problem、intended
   structural change、behavior が変わらない理由、non-goals、validation signal を
   親 agent が言語化します。final response は changed paths、validation
   commands、unresolved blockers に絞らせます。broad prose、unrelated edit、
   file-level target だけの実装、target-object trace のない差分は
   `handoff_prompt_gap` として扱い、次の writer 起動前に handoff / skill を
   修正します。
1. implementation subagent が返した差分は、full finding packet と `git diff`
   hunk を突き合わせて `diff_linked_findings` にします。レビューには latest diff
   だけでなく、direct / related / unchanged finding の分類を渡します。
1. finding packet が `handoff_prompt_gap` または `shared_skill_or_workflow_gap`
   を示した場合は、次の write-capable subagent を起動する前に handoff prompt、
   skill、workflow、または task catalog prompt を修正します。
1. prompt feedback は `workflow_monitor.py --runtime-feedback ... action=prompt_repair`
   で run bundle に残します。
1. write-capable subagent を起動する前に、active run bundle が
   `AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR` または
   `reports/agents/.active_run` で hook から解決できる状態にします。
   subagent の spawn / wait / close は hook が `subagent_lifecycle_event=*`
   として `workflow_monitoring.md` に転記します。
1. write-capable subagent の結果を受けたら、parent は必ず
   `workflow_monitor.py --behavior-event` で
   `subagent_output_revision=none|parent_revised|review_revised`、
   `subagent_target` または `subagent_agent_type`、`repair_batch_id`、
   `revision_reason`、`tool_rerun_required=yes|no` を記録します。これを
   revision latency と handoff quality の正本にし、chat 上の記憶だけで
   revise 回数を数えません。
1. mechanically safe な finding を 1 件だけ渡す handoff は既定ではなく smell
   として扱います。単一 target wave が必要な場合は root contract、semantic
   risk、write-scope conflict、validation isolation のいずれかを理由として
   `Refactor Orchestration Plan` に残します。理由が無い場合は
   `handoff_prompt_gap` として関連 target を batch 化してから次 writer を起動します。

## Refactor Orchestration Plan

親 agent は tool の finding をそのまま subagent に配るのではなく、依存 DAG から
実装順と並列化可否を決める統括 plan を先に作ります。

1. `Change Impact Packet` の `impact_blocks` と `repair_batches` を起点に、
   対象 object、依存先、依存元、test / docs / config / log / Info surface、
   unknown dynamic edge を object 単位で並べます。block 化は tool の出力を
   正本にし、親 agent が手作業で依存範囲を切り直す場合は split / merge 理由と
   元の `block_id` を残します。
1. `scope_candidates` を比較し、node 粒度を選びます。最適化目的は最小 wave 数と
   最小 tool rerun 数だけではなく、writer 衝突、review 可能性、token 消費、
   validation surface の一貫性、semantic risk を含みます。選ばなかった候補は
   rejected reason を残します。
1. dependency depth、call direction、shared policy / base abstraction の有無から
   `sequential_root_slices` と `parallel_candidate_slices` に分けます。
1. 各 wave では、同じ責務 group と validation surface に属する mechanically safe
   target object を repair batch としてまとめます。親 agent は「小さく安全」だけを
   理由に finding 1 件へ分割せず、分割する場合は関連 target ごとに deferred /
   review_required 理由を書きます。
1. 依存の根本、共通 helper、shared policy、base abstraction、public contract に
   触る slice は先に少数の write-capable agent で直します。衝突リスクは scope を
   finding 1 件に縮める理由ではなく、task order で解く対象です。衝突する target は
   同一 wave に置かず、dependency order に従って先行 / 後続 wave に分け、先行 wave
   の validation と tool rerun 後に後続 writer へ渡します。
1. root slice の validation、tool rerun、`diff_linked_findings` が通ったあとだけ、
   write scope が交差しない downstream slice を wave に分けて並列化します。
1. 各 slice には少なくとも次を記録します。
   - `slice_id`
   - `target_objects`: `path:start-end:qualname`
   - `owner_agent`
   - `blocked_by`
   - `allowed_files`
   - `current_problem`
   - `intended_structural_change`
   - `forbidden_semantic_delta`
   - `validation_signal`
   - `parallel_safe`: yes/no と理由
1. parent はこの plan から subagent prompt を生成します。subagent は機械的に出た
   finding だけで判断せず、親が指定した修正方針、non-goals、validation に従います。
1. wave ごとに全走査を再実行し、次 wave の plan を更新します。最初に作った
   parallel plan を、root 修正後の finding 変化を見ずに最後まで使い回しては
   いけません。

## Subagent Routing

refactor が trivial な単発編集を超える場合、parent agent は実装と review を
兼務しません。run bundle または作業 update に、どの subagent がどの stage を
担当するかを固定します。

1. Parent agent
   - `Behavior Contract`、`Allowed Structural Delta`、
     `Forbidden Semantic Delta`、scan artifact、repair slice、validation
     sequence を固定します。
   - 非自明な構造変更では `structure-planning` の source-to-structure map、
     ordered structure、invalid interpretations を refactor contract に取り込みます。
   - dependency-expanded scope から `Refactor Orchestration Plan` を作り、
     sequential root slices と parallel-safe downstream slices を分けます。
   - 低レベル依存や shared abstraction の修正は少数 agent で先に通し、独立な
     downstream slice だけを validation 後に wave 並列化します。
   - write-capable agent と read-only reviewer の入力 artifact を分けます。
   - 実装後に reviewer finding を統合する責任を持ちますが、review 判定を
     自分だけで完了扱いにしません。
1. `test_designer`
   - code-changing refactor では implementation 前に起動します。
   - regression case、nasty case、behavior-preservation assertions を設計し、
     実装 agent へ渡します。
1. Write-capable implementation agent
   - 既定は `worker` または小さい slice では `spark_worker` です。
   - write-capable agent は既定 1 体ですが、parent が dependency order、
     wave plan、disjoint write scope、integration order、review gate を明示した
     場合は、複数 writer を同一 wave で並列化できます。衝突する target は禁止
     でも scope 縮小理由でもなく順序制約として扱い、先行 / 後続 wave に分けます。
     current checkout 内の wave plan で安全に分離できない場合は、separate worktree へ逃がさず後続 wave へ直列化します。
   - repair batch / slice、affected files、forbidden semantic delta、既存 dirty
     state の扱い、validation command を明示して渡します。
   - 親 agent は「どこをどう直すか」を file 単位ではなく object 単位で渡します。
     少なくとも `path:start-end:qualname`、問題の根拠、想定 diff 形状、触らない
     semantic、期待する test / checker signal を含めます。
   - 実装 agent は review を完了扱いにしてはいけません。
1. Read-only review agent
   - 実装 agent とは別 instance にします。
   - Python 差分は `python_reviewer`、C/C++ 差分は `cpp_reviewer`、Rust/tool
     差分や mixed diff は `reviewer` または task-specific reviewer を使います。
   - reviewer には latest diff、scan before/after、impact diff、test evidence、
     behavior contract、`diff_linked_findings` を渡します。
   - reviewer は approve / revise / escalate を artifact または parent への
     final message に明示します。
1. Design/document review
   - module boundary、public API、workflow/skill 文書を変えた場合は
     `detailed_design_reviewer`、`document_flow_reviewer`、または
     `docs_workflow_steward` を追加します。
   - 単なる実装差分 review の代替にしません。

## Review Emphasis

- `design_reviewer`
  - semantic delta が混入していないか
- `document_flow_reviewer`
  - path mapping と migration 説明が上から読んで追えるか
- `project_reviewer`
  - cross-module drift、stale path、残骸がないか
- language reviewer
  - Python なら `python-review`
  - C / C++ なら `cpp-review`
- `docs_workflow_steward`
  - design 見直し、OOP boundary、解析 score gate が workflow と docs に残っているか
