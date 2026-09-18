<!--
@dependency-start
contract design
responsibility Defines the structural grammar and ownership invariant for root agent instruction entrypoints.
upstream design ../conventions/software-engineering-principles.md single-owner, information-hiding, and contract-complete change policy
downstream design ../../AGENTS.md minimal source-tree entrypoint
downstream design ../../agents/canonical/SOURCE_ROUTING.md optional source owner map
downstream design ../../ROOT_AGENTS.md common root base read by consumer and source-specific AGENTS
downstream design ../../.github/AGENTS.md minimal GitHub subtree overlay
downstream implementation ../../tools/agent/templates/entrypoint_composer.py consumer root composer
downstream implementation ../../tools/validation/semantic/entrypoint/check_entrypoint_owner_map.py structural verifier
downstream implementation ../../tools/validation/semantic/convention/convention_compliance_contracts.toml canonical marker ownership projection
downstream implementation ../../tests/agent_tools/test_check_entrypoint_owner_map.py contract regression
downstream design ../../agents/skills/comprehensive-development.md implementation-basis consumer
downstream design ../../agents/canonical/ROOT_DELIVERY.md responsibility-specific detail owner
downstream design ../../agents/canonical/ROOT_EXECUTION.md responsibility-specific detail owner
downstream design ../../agents/canonical/ROOT_IMPLEMENTATION.md responsibility-specific detail owner
downstream design ../../agents/canonical/CODEX_BOOTSTRAP.md responsibility-specific detail owner
downstream design ../../agents/canonical/CODEX_COMPLETION.md responsibility-specific detail owner
downstream design ../../agents/canonical/CODEX_IMPLEMENTATION.md responsibility-specific detail owner
downstream design ../../agents/canonical/CODEX_INTAKE.md responsibility-specific detail owner
downstream design ../../agents/canonical/CODEX_ROUTING.md responsibility-specific detail owner
@dependency-end
-->

# Root entrypoint owner-map contract

## Purpose

[AGENTS.md](../../AGENTS.md) と [ROOT_AGENTS.md](../../ROOT_AGENTS.md) は常時ロードされ得るため、task-specific policy の
保存場所ではなく、repository identity と canonical owner を解決する入口に限定します。
詳細手順を Skill から入口へ複製すると、activation boundary、instruction budget、変更理由、
validation owner が混線します。本設計は常時読取と条件付き読取の境界を定義します。構造検査を通ることだけを理由に、
入口へ詳細や長い owner 一覧を残しません。

## Model

入口文書の集合を `E`、文書 `e` の level-2 heading 列を `H(e)`、許可された heading 列を
`A(e)` とします。task procedure を表す構文集合を `P(e)`、責務集合を `R`、責務 `r` の
canonical owner を `owner(r)` とします。

成立条件は次です。

- `H(e) = A(e)`: 許可された reader / owner sections だけが、定義順で存在する。
- `P(e) = ∅`: fenced command、番号付き手順、command recipe、nested procedure heading を
  入口に持たない。
- material な各 `r` について、入口は `owner(r)` への一つの route を持ち、同じ policy を
  本文で再定義しない。
- convention marker contract の集合を `C` とすると、`∀c ∈ C, paths(c) ∩ E = ∅`。
  入口は operational marker の canonical surface にならない。
- standalone source、explicit live integration、static-seed consumer の identity を混同しない。

構造不変条件と読取量は別に確認します。短くても command recipe を持つ入口は不適切であり、
構造を満たしていても毎回不要な詳細を読ませる入口は短縮対象です。必須入口は最小の共通制約と
条件付きの参照だけにし、詳しい owner 表は自動 discovery されない optional 文書へ置きます。

## Allowed information architecture

Standalone [AGENTS.md](../../AGENTS.md) と optional
[SOURCE_ROUTING.md](../../agents/canonical/SOURCE_ROUTING.md) は同じ小さな見出し構造を使います。
常時入口の owner 表は optional map への1行だけ、詳細な owner 行は後者が所有します。

- `Repository Role`
- `Reader Map`
- `Always-On Boundary`
- `Runtime Owner Map`
- `Task Entry`
- `Validation Routing`

Common [ROOT_AGENTS.md](../../ROOT_AGENTS.md) (shared entry base for consumer and source-specific roots):

- `Repository Role`
- `Reader Map`
- `Always-On Boundary`
- `Runtime Owner Map`
- `Task Entry`
- `Validation Routing`

Consumer root [AGENTS.md](../../AGENTS.md) は、この [ROOT_AGENTS.md](../../ROOT_AGENTS.md) の bytes を先頭の論理内容として
保持し、consumer-owned specific section を明示的に合成した regular tracked file です。
合成元の source commit と exact input-byte digest は deterministic comment marker にのみ
記録します。Source-specific AgentCanon [AGENTS.md](../../AGENTS.md) は先頭の literal `@ROOT_AGENTS.md`
でこの共通 base を明示参照し、未解決の owner だけ optional Source Routing へ案内します。
既知の owner へ直接進むときは map 自体を読みません。
これは consumer composition とは別の explicit read であり、自動展開、runtime import、
wrapper、source copy を意味しません。ROOT の consumer map / owner route は consumer root
にだけ適用し、source-specific AGENTS は source owner map への条件付き route を保持します。
これらの節は identity、owner edge、activation boundary の要約だけを持ちます。
subagent sequence、Git environment variables、update command、design receipt、experiment setting、
validation menu、closeout token は、それぞれの owner surface に置きます。

## Responsibility migration

| Detailed responsibility | Canonical owner after migration |
| --- | --- |
| implementation completeness and evidence-backed mechanism selection | [documents/conventions/software-engineering-principles.md](../conventions/software-engineering-principles.md) and selected implementation / review Skill |
| cross-surface implementation-basis packet | [agents/skills/comprehensive-development.md](../../agents/skills/comprehensive-development.md) |
| design correspondence | [agents/internal-routines/design-implementation-correspondence.md](../../agents/internal-routines/design-implementation-correspondence.md) |
| structure intake | [agents/skills/structure-refactor.md](../../agents/skills/structure-refactor.md) and structure contract |
| Git mutation safety | [agents/skills/worktree-health.md](../../agents/skills/worktree-health.md), canonical workflow, hooks |
| AgentCanon update | [agents/skills/agent-canon-update.md](../../agents/skills/agent-canon-update.md) and update route |
| orchestration / subagent lifecycle | orchestration and subagent canonical owners |
| validation / closeout | runtime profile, canonical workflow, closeout tools |

入口は上記 owner の存在と route を示しますが、owner の acceptance rule や操作順序を複製しません。

## Verification contract

`check_entrypoint_owner_map.py` は次を fail-closed で確認します。

- H1 が一つであること
- level-2 heading が許可列と一致すること
- level-3 以下の heading がないこと
- fenced block と番号付き procedure がないこと
- bullet / direct command recipe がないこと
- root の最小 route と optional SOURCE_ROUTING の required owner 行が、それぞれの所有先にあること
- optional map 自体が存在すること（検査時の読取であり、Codex の起動時読取ではない）
- convention marker manifest が source [AGENTS.md](../../AGENTS.md) / [ROOT_AGENTS.md](../../ROOT_AGENTS.md) を operational surface として
  再登録していないこと

checker は prose の意味を推測しません。意味上の重複は review owner が判断し、構造的に再流入可能な
surface は checker が拒否します。この分担により、自然言語 classifier を新しい policy owner に
せず、検証可能な文書 grammar だけを機械化します。

## Consumer root composition

`tools/agent/templates/entrypoint_composer.py` は、明示された base、consumer-specific source、
output の三つの path と source checkout から現在 commit を読み、通常 file を同一 directory
内で atomic に置き換えます。出力には managed marker、source commit、base/specific の exact
byte count と SHA-256、固定 separator、二つの exact source byte 列が入ります。新規 output は
作成でき、既存の unmarked output、directory、symlink、partial/corrupt marker は保存したまま
typed failure になります。valid な managed output だけが current exact sources で更新されます。

この composition は consumer の bootstrap/maintenance 操作です。AgentCanon runtime update、
source symlink、vendor/submodule projection、nested directory [AGENTS.md](../../AGENTS.md) の更新を行いません。
生成後の consumer は output だけで instruction を読め、AgentCanon checkout や runtime の存在を
前提にしません。`AGENT.md` という singular alias はこの contract に存在しません。

## Template boundary

`project_template` の tracked [AGENTS.md](../../AGENTS.md) は self-contained static consumer の project-owned file です。
本設計はそれを source resolver、updater、vendor、submodule、symlink projection へ戻しません。
consumer の具体的な追加文は consumer 側の `documents/agent-canon/consumer-root-instructions.md`
が所有し、AgentCanon の [ROOT_AGENTS.md](../../ROOT_AGENTS.md) はその共通 base だけを所有します。static-seed allowlist は
role/config のままとし、生成された root [AGENTS.md](../../AGENTS.md) は consumer の tracked output として扱います。

## Responsibility-based document split

ROOT の詳細判断を入口へ積み重ねると、実装・環境・Git・報告という異なる変更理由が
常時読取の一単位に結合する。Codex Workflow も intake から closeout までの全文が
同じ path のため、必要な局面だけを読む責務と機械的な section locator が混線していた。
分割は既存の規則・適用条件・例外を保持し、次の責務を直接選べるようにする。

| Surface | Responsibility | Activation |
| --- | --- | --- |
| `AGENTS.md` | minimal source entry and conditional lookup | source root entry |
| `ROOT_AGENTS.md` | portable common constraints and consumer owner map | root entry |
| [SOURCE_ROUTING.md](../../agents/canonical/SOURCE_ROUTING.md) | expanded source owner and validation map | unresolved source owner only |
| [ROOT_IMPLEMENTATION.md](../../agents/canonical/ROOT_IMPLEMENTATION.md) | implementation, necessity, reachability, numerical decisions | relevant source-side implementation decision |
| [ROOT_EXECUTION.md](../../agents/canonical/ROOT_EXECUTION.md) | configured execution, checkout, cleanup, team boundaries | relevant source-side execution operation |
| [ROOT_DELIVERY.md](../../agents/canonical/ROOT_DELIVERY.md) | Issue evidence, continuation, reporting, commit/push, formatting | relevant source-side evidence or delivery operation |
| [CODEX_WORKFLOW.md](../../agents/canonical/CODEX_WORKFLOW.md) | direct phase reader map and startup routing | Codex admission |
| [CODEX_INTAKE.md](../../agents/canonical/CODEX_INTAKE.md) | intake and checkout/context continuity | intake or relevant state change |
| [CODEX_ROUTING.md](../../agents/canonical/CODEX_ROUTING.md) | family, skills, profile, placement | unresolved route selection |
| [CODEX_BOOTSTRAP.md](../../agents/canonical/CODEX_BOOTSTRAP.md) | run bootstrap, goals, adaptive materialization | selected run/goal/token route |
| [CODEX_IMPLEMENTATION.md](../../agents/canonical/CODEX_IMPLEMENTATION.md) | design admission and implementation | design or implementation |
| [CODEX_COMPLETION.md](../../agents/canonical/CODEX_COMPLETION.md) | validation, coverage, terminal-owner delegation | validation or closeout |

ROOT は consumer で必要な禁止・義務・適用条件を自分の本文に保持する。source の詳細は
source-specific AGENTS から到達する optional Source Routing の該当行で選ぶ。consumer に source 文書の
存在を要求しない。portable base と source 向け詳細という配布上の差を、全詳細の二重コピーや
新たな全件読取条件に変えない。規則の意味を変える変更では両適用面への影響を確認する。

composer は exact base/specific bytes を扱う既存実装のままにする。include DSL、再帰的
loader、追加公開 API、配布ファイル追加は不要であり、output だけで consumer が読める
性質を維持する。既存 owner を単にリンクへ置換して consumer の規則を欠落させる案、
全分割先を無条件展開して入口の読取量を変えない案は採用しない。

`tools/agent/orchestration/packets.py` の designer / implementer は、従来の
`4. Run Bootstrap` と `5. Implementation` をそれぞれの正本で読み切る。同じ意味の
section heading を維持し、locator の path だけを分離する。`agents/agents_config.json`、
manifest の source reference、publication/review evidence も移動した規則の直接 owner を指す。
既存 convention/runtime checker と prompt eval は marker/regex を削らず、本文の新しい
所有先へ付け替える。入口に marker を複製して通過させない。

検証は entrypoint grammar、source-free composition、section locator、既存 marker/eval、
移動本文・リンクの対応を対象とする。行数/bytes は文書量の観測であり、実 agent の token、
速度、品質の実測値ではない。新たな checker、承認、全 profile 実行、他 Issue の完了は
この分割の条件にしない。

## Codex automatic loading and on-demand reading

一次資料（2026-09-18確認）は [AGENTS.md discovery](https://developers.openai.com/codex/guides/agents-md/)
と [Skills progressive disclosure](https://developers.openai.com/codex/skills/) です。Codex は起動時に
適用される global/project AGENTS（override、設定された fallback を含む）を指示へ取り込みます。
Skill は discovery 時の名前・説明等と、選択時の本文を区別します。`.github/AGENTS.md` も
その subtree に適用されると自動読取対象になるため、仕様説明・全体索引を除き、局所制約と
既存の GitHub template / PR owner への条件付き参照だけにします。ROOT_AGENTS という名前や
`@` 記法を native include とみなしてはいけません。この repo では明示読取と consumer への
本文合成によって ROOT が実効的な共通読取量へ加算されます。

最小化する対象は常時本文だけでなく、そこから無条件に読むよう指示された資料の集合です。
HTML comment の dependency metadata も渡される文字量に含まれ、別ファイルへの分割後に
「全資料を読む」と命じれば読取量は減りません。下位 AGENTS、fallback 名への変更、同じ
説明を Skill description へ詰める方法も on-demand 化ではありません。

入口を `A`、task に必要でまだ context にない detail section 集合を `S(task)` とすると、
読取量は `bytes(A) + sum(bytes(s) for s in S(task))` に局所化します。これは選択単位の
設計上の量であり、実 token 数、速度、遵守率の測定ではありません。未知の owner の場合だけ
短い入口 → optional map の該当行 → owner の該当節へ進み、既知の owner は map を迂回します。
Skill の選択済み本文/EOF 規則は維持し、未選択 Skill と無関係な canonical 文書は読みません。

旧 CODEX_WORKFLOW の Start Here と二つの packet 一覧は、条件付き Reader Map と
[Optional Context](../../agents/canonical/CODEX_INTAKE.md#optional-context) の条件表へ置き換えます。
移動先の全文読取を要求するだけの変更にはしません。設定済みの owner、admission、作業経路を
再判定せず、inactive 項目の棚卸しや not_applicable 帳票も既存 active contract が求める場合だけです。

ROOT の共通制約は portable な要約、source 詳細は既存 ROOT_IMPLEMENTATION / EXECUTION /
DELIVERY に保持します。composer とその公開 API は変更せず、生成物へ source-only path の
読取依存を追加しません。新しい loader、include DSL、読取 budget 設定、常設の文字数 gate は不要です。
検証範囲はこの入口と直接 owner、リンク/anchor、既存 grammar、source-free composition に限定し、
他 PR の統合や全 consumer への配布、全エージェントの実測を終了条件に含めません。
