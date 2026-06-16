# AgentCanon Repository Instructions
<!--
@dependency-start
responsibility Documents AgentCanon Repository Instructions for this repository.
downstream design README.md shared canon overview must reflect runtime contract
@dependency-end
-->


この tree は standalone AgentCanon repo の source of truth です。
template / derived repo では `vendor/agent-canon/` submodule pin として参照されます。
ここを単体で見ているときは、shared canon の整合を優先し、特定の派生 repo に閉じた Docker、implementation、experiment 前提を持ち込みません。

## Read First

- `README.md`
- `documents/README.md`
- `agents/README.md`
- `agents/workflows/README.md`
- `agents/canonical/README.md`
- `agents/canonical/CODEX_WORKFLOW.md`
- `documents/AGENTS_COORDINATION.md`
- `documents/SKILL_IMPLEMENTATION_GUIDE.md`
- `documents/worktree-lifecycle.md`
- `.codex/README.md`

## Scope

- root AGENTS runtime wrapper
- Codex runtime entrypoints
- shared Codex config defaults
- shared agent workflow
- shared skill canon
- Codex subagent inventory
- agent review / coordination documents
- shared runtime surface ownership document
- submodule update and legacy migration operation canon
- skill and worktree operation canon
- carry-over note template
- worktree note templates
- agent-specific CI workflow
- agent-specific regression tests
- agent support scripts

## Non-Goals

- `docker/`
- shared canon の外にある repo-local `python/`
- `experiments/`
- repo-local README / bootstrap / server contract

## Working Rule

- AgentCanon tree changes は shared canon として成立するかを先に確認する
- first-reader 向けの入口は `README.md` -> `documents/README.md` -> `agents/README.md` -> `agents/workflows/README.md` の順にたどれるよう保つ
- 広い概念、長い user request、文書統合、薄い文書洗い出しでは、広域 `rg` の前に `agent-canon semantic-index search --query-file <file> --top-k <N> --format text|jsonl` または `agent-canon semantic-index thin-docs --top-k <N> --format text` を試す
- 規定の実行 target は GPU です。数値計算、solver、optimizer、JAX / XLA / IREE lowering、convergence、residual、benchmark、experiment などの計算テストを CPU で実行することを禁止する。GPU が使えない場合は CPU fallback で代替せず、`gpu_validation_blocker=<reason>` と evidence を残す。CPU 使用は、format、lint、type check、docs check、dependency/header check など計算 kernel を実行しない静的・文書・tooling validation だけに限定する
- 設計では、実装対象 file、既存 helper、または直近 finding だけに scope を閉じない。先に抽象責務、概念モデル、非対象、将来 layer、評価軸、既存正本との関係を固定し、そこから実装 slice と validation を導く
- skill、tool、workflow、HTML report、実験 script を追加または変更するときは、先に既存資産の調査、次に責務境界の解析、その後に実装へ入る。この順序と再利用しなかった候補は run bundle または work log に残す
- ad hoc / 場当たりの修正実装は禁止する。局所的に失敗を隠す patch、未設計の alternate route / wrapper / helper、責務にない分岐、test / warning だけを黙らせる変更を入れて完了扱いにしない。修正は user request、責務、依存 graph、既存正本、検証 gate に結び付け、必要なら design / skill / workflow / tool の正本を先に直す
- 規定逸脱を見つけた場合、agent は逸脱したまま作業を継続しない。active な system / developer / user instruction、AGENTS / ROOT_AGENTS、workflow、skill、design packet、approved plan、allowed paths、validation gate、review gate と現在の行動が矛盾したら、都合よく解釈し直さず、skip、代替 route、局所 patch、後追い説明で吸収せず、`policy_deviation_blocker=<short description>` と evidence を残して、該当する上位 gate または user 判断へ戻す
- 規定逸脱の修正は、逸脱を生んだ workflow、skill、tool、handoff、role TOML、AGENTS / ROOT_AGENTS、または設計正本の責務として扱う。実装差分だけで辻褄を合わせることを禁止する
- backend、runtime target、compiler route、device、dtype を、証明・検証・実験・実装を通すために agent が勝手に固定することを禁止する。IREE、XLA、CUDA、CPU、GPU、VMFB、StableHLO、LLVM、FP32 などへの固定は、user request、approved design、runtime profile、または public API / config が明示した場合だけ扱う。それ以外では backend を top-level input、runtime profile、backend witness、または coverage evidence として保持し、特定 backend へ寄せた theorem、test、fallback、コード分岐で主張を成立させてはいけない
- backend 依存の証明・数値誤差・性能・lowering claim に必要な evidence が不足する場合は、backend を固定して回避せず、`backend_evidence_blocker=<missing evidence>` と対象 profile を記録する。backend 固有の調査や trace は active profile の evidence であり、アルゴリズムや theorem の正本を backend 固有へ縮退させる理由ではない
- 実装、調査、証明、レビューの途中で設計上の問題を見つけた場合、agent は勝手に実装で吸収しない。API shape、責務境界、path layout、命名、アルゴリズム、証明対象、test oracle、依存方向、runtime contract、config surface の不整合や欠落を見つけたら、local fallback、wrapper、helper、分岐、互換 route、test 緩和、説明だけの上書きで処理せず、`design_issue_blocker=<short description>` と evidence を残して詳細設計 / design review gate へ戻す。run bundle が無い parent-direct task では、編集を止めて user に設計判断を返す
- 設計問題ではなく、承認済み design、局所 precedent、既存責務境界から一意に導ける typo、format、import、狭い機械的追従だけが実装内修正を許される。判断が必要なら設計問題として扱う
- prompt、routing、subagent-config の shared canon を直す task では、親が policy prose を直接広く書き換える前に `prompt_config_reviewer` で prompt/config audit を切り、重複 surface と最小差分を先に確定する
- AGENTS / ROOT_AGENTS に禁止事項を増やす前に、warning hook、checker、closeout artifact gate、role TOML、または workflow eval に逃がせるかを決める。hook は原則 fail-open の context / evidence 収集面とし、prompt secret など高確信の公開事故以外を runtime blocker にしない
- legacy forwarder / migration wrapper が `*_FORWARDER=deprecated`、`*_FORWARDER_SEVERITY=fix-now`、または caller chain 付きの移行警告を出した場合は、元の作業を続ける前に呼び出し元を特定し、canonical command へ移行する。subagent handoff や workflow prompt には、警告の caller chain、移行先 command、「移行してから元 task へ戻る」指示を含める
- root entrypoint wrapper の変更は、この tree ではなく template / 派生 repo 側の wrapper task として扱う
