<!--
@dependency-start
contract design
responsibility Defines the structural grammar and ownership invariant for root agent instruction entrypoints.
upstream design ../conventions/software-engineering-principles.md single-owner, information-hiding, and contract-complete change policy
downstream design ../../AGENTS.md standalone source-tree entrypoint
downstream design ../../ROOT_AGENTS.md common consumer root base
downstream implementation ../../tools/agent_tools/entrypoint_composer.py consumer root composer
downstream implementation ../../tools/agent_tools/check_entrypoint_owner_map.py structural verifier
downstream implementation ../../tools/agent_tools/convention_compliance_contracts.toml canonical marker ownership projection
downstream implementation ../../tests/agent_tools/test_check_entrypoint_owner_map.py contract regression
downstream design ../../agents/skills/comprehensive-development.md implementation-basis consumer
@dependency-end
-->

# Root entrypoint owner-map contract

## Purpose

`AGENTS.md` と `ROOT_AGENTS.md` は常時ロードされ得るため、task-specific policy の
保存場所ではなく、repository identity と canonical owner を解決する入口に限定します。
詳細手順を Skill から入口へ複製すると、activation boundary、instruction budget、変更理由、
validation owner が混線します。本設計は「薄い」という形容を、見出し名や byte 数ではなく
検証可能な構造不変条件として定義します。

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

byte 数や行数は、この不変条件の代理にしません。短い文書でも command recipe を持てば違反で、
長さが増えても owner table の必要な edge だけなら直ちに違反ではないためです。

## Allowed information architecture

Standalone `AGENTS.md`:

- `Repository Role`
- `Reader Map`
- `Always-On Boundary`
- `Runtime Owner Map`
- `Task Entry`
- `Validation Routing`

Consumer common `ROOT_AGENTS.md`:

- `Repository Role`
- `Reader Map`
- `Always-On Boundary`
- `Runtime Owner Map`
- `Task Entry`
- `Validation Routing`

Consumer root `AGENTS.md` は、この `ROOT_AGENTS.md` の bytes を先頭の論理内容として
保持し、consumer-owned specific section を明示的に合成した regular tracked file です。
合成元の source commit と exact input-byte digest は deterministic comment marker にのみ
記録します。これらの節は identity、owner edge、activation boundary の要約だけを持ちます。
subagent sequence、Git environment variables、update command、design receipt、experiment setting、
validation menu、closeout token は、それぞれの owner surface に置きます。

## Responsibility migration

| Detailed responsibility | Canonical owner after migration |
| --- | --- |
| implementation completeness and evidence-backed mechanism selection | `documents/conventions/software-engineering-principles.md` and selected implementation / review Skill |
| cross-surface implementation-basis packet | `agents/skills/comprehensive-development.md` |
| design correspondence | `agents/internal-routines/design-implementation-correspondence.md` |
| structure intake | `agents/skills/structure-refactor.md` and structure contract |
| Git mutation safety | `agents/skills/worktree-health.md`, canonical workflow, hooks |
| AgentCanon update | `agents/skills/agent-canon-update.md` and update route |
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
- convention marker manifest が source `AGENTS.md` / `ROOT_AGENTS.md` を operational surface として
  再登録していないこと

checker は prose の意味を推測しません。意味上の重複は review owner が判断し、構造的に再流入可能な
surface は checker が拒否します。この分担により、自然言語 classifier を新しい policy owner に
せず、検証可能な文書 grammar だけを機械化します。

## Consumer root composition

`tools/agent_tools/entrypoint_composer.py` は、明示された base、consumer-specific source、
output の三つの path と source checkout から現在 commit を読み、通常 file を同一 directory
内で atomic に置き換えます。出力には managed marker、source commit、base/specific の exact
byte count と SHA-256、固定 separator、二つの exact source byte 列が入ります。新規 output は
作成でき、既存の unmarked output、directory、symlink、partial/corrupt marker は保存したまま
typed failure になります。valid な managed output だけが current exact sources で更新されます。

この composition は consumer の bootstrap/maintenance 操作です。AgentCanon runtime update、
source symlink、vendor/submodule projection、nested directory `AGENTS.md` の更新を行いません。
生成後の consumer は output だけで instruction を読め、AgentCanon checkout や runtime の存在を
前提にしません。`AGENT.md` という singular alias はこの contract に存在しません。

## Template boundary

`project_template` の tracked `AGENTS.md` は self-contained static consumer の project-owned file です。
本設計はそれを source resolver、updater、vendor、submodule、symlink projection へ戻しません。
consumer の具体的な追加文は consumer 側の `documents/agent-canon/consumer-root-instructions.md`
が所有し、AgentCanon の `ROOT_AGENTS.md` はその共通 base だけを所有します。static-seed allowlist は
role/config のままとし、生成された root `AGENTS.md` は consumer の tracked output として扱います。
