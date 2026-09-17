<!--
@dependency-start
contract design
responsibility Defines the structural grammar and ownership invariant for root agent instruction entrypoints.
upstream design ../conventions/software-engineering-principles.md single-owner, information-hiding, and contract-complete change policy
downstream design ../../AGENTS.md standalone source-tree entrypoint
downstream design ../../ROOT_AGENTS.md common root base read by consumer and source-specific AGENTS
downstream implementation ../../tools/agent/templates/entrypoint_composer.py consumer root composer
downstream implementation ../../tools/validation/semantic/entrypoint/check_entrypoint_owner_map.py structural verifier
downstream implementation ../../tools/validation/semantic/convention/convention_compliance_contracts.toml canonical marker ownership projection
downstream implementation ../../tests/agent_tools/test_check_entrypoint_owner_map.py contract regression
downstream design ../../agents/skills/comprehensive-development.md implementation-basis consumer
@dependency-end
-->

# Root entrypoint owner-map contract

## Purpose

[AGENTS.md](../../AGENTS.md) と [ROOT_AGENTS.md](../../ROOT_AGENTS.md) は常時ロードされ得ますが、
同じ配布責務ではありません。前者は AgentCanon source checkout の identity と canonical owner
への案内、後者は source-free consumer にも配る共通制約と最小限の owner 案内を所有します。
共通制約を保持することと、task-specific な詳細手順を所有することを区別します。
詳細手順を Skill から入口へ複製すると、activation boundary、instruction budget、変更理由、
validation owner が混線します。本設計は文書の短さではなく、適用範囲と読取経路を定義します。

## Model

入口文書の集合を `E`、文書 `e` の level-2 heading 列を `H(e)`、許可された heading 列を
`A(e)` とします。task procedure を表す構文集合を `P(e)`、責務集合を `R`、責務 `r` の
canonical owner を `owner(r)` とします。

成立条件は次です。

- `H(e) = A(e)`: 許可された reader / owner sections だけが、定義順で存在する。
- `P(e) = ∅`: fenced command、番号付き手順、command recipe、nested procedure heading を
  入口に持たない。
- task-specific な各 `r` について、入口は `owner(r)` への一つの route を持ち、同じ policy を
  本文で再定義しない。
- 共通制約は ROOT に保持し、source は明示読取、consumer は本文合成で同じ base を使う。
  source-specific AGENTS は共通制約を再定義せず、適用先の owner を解決する。
- convention marker contract の集合を `C` とすると、`∀c ∈ C, paths(c) ∩ E = ∅`。
  入口は operational marker の canonical surface にならない。
- standalone source、explicit live integration、static-seed consumer の identity を混同しない。

byte 数や行数は、この不変条件の代理にしません。短い文書でも command recipe を持てば違反で、
長さが増えても owner table の必要な edge だけなら直ちに違反ではないためです。

## Allowed information architecture

Standalone [AGENTS.md](../../AGENTS.md):

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
でこの共通 base を明示参照し、その後に source-specific Reader Map を保持します。
これは consumer composition とは別の explicit read であり、自動展開、runtime import、
wrapper、source copy を意味しません。ROOT の consumer map / owner route は consumer root
にだけ適用し、source-specific AGENTS が source owner と validation route を保持します。
source 入口の節は identity、owner edge、activation boundary の案内に限定します。
ROOT はそれに加え、単独配布に必要な共通制約を保持します。これは詳細手順の移管先ではありません。
subagent sequence、Git environment variables、update command、design receipt、experiment setting、
validation menu、closeout token は、それぞれの owner surface に置きます。

## Ownership and distribution boundary

| 文書 / 配布物 | 所有する内容 | 置かない内容 |
| --- | --- | --- |
| AgentCanon 自身の `AGENTS.md` | source identity、共通 base の読取方法、AgentCanon 固有の owner/path・runtime・検証への案内 | 共通制約の再定義、consumer 固有設定、詳細手順 |
| `ROOT_AGENTS.md` | repository 共通の行動制約、consumer が単独で読める owner 案内 | source 専用の入口説明、source checkout を必要とする実行手順 |
| consumer-specific source | その製品の owner、build/test、配置、追加指示 | AgentCanon source 入口や内部 workflow のコピー |
| consumer の生成 `AGENTS.md` | ROOT と consumer-specific source の合成結果 | AgentCanon 自身の `AGENTS.md` の合成、参照先を配らない include |

source の読取経路は `AGENTS.md -> ROOT_AGENTS.md -> AGENTS.md の source owner map`、
consumer の配布単位は `ROOT_AGENTS.md の本文 + consumer-owned specific source` です。
同じ `AGENTS.md` という名前でも、前者は source 入口、後者は consumer 所有の出力です。
共通規則を source の Skill へのリンクだけに置き換えると、AgentCanon checkout のない
consumer では必要な規則が読めません。composer は二つの入力本文を合成するだけで、
参照の再帰展開や source AGENTS の自動取込を行いません。

新しい記述は適用先と変更理由で配置します。共通の制約は ROOT、AgentCanon 固有の
owner/path は source AGENTS、製品固有の指示は consumer-specific source、具体的な手順や
acceptance rule は既存の Skill / workflow / internal routine に置きます。入口の owner 変更は
共通制約の無効化ではありません。文書分割だけを理由に全参照先の読了を必須にしません。

この境界に従い、source identity と `@ROOT_AGENTS.md` の解釈は source AGENTS に集約し、
directory-local instructions、owner を迂回しない規則、限定作業の activation boundary、
他 owner の検証例を一律チェックリストにしない規則は ROOT に集約します。
実装の単純さ・問題領域保持・設計根拠・環境選択抑止・数値結果保持・format/report の共通制約は
配布先でも必要なため保持します。AgentCanon defect の報告と source maintenance の案内も
consumer からの handoff に必要であり、source 専用と誤判定して削除しません。
新しい loader、分割 manifest、同期機構、checker は追加しません。

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
- required owner-map row が同一 row 内に存在すること
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
