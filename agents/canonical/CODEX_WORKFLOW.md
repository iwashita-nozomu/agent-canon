<!--
@dependency-start
contract agent-runtime
responsibility Routes Codex tasks to phase-owned procedures without loading inactive phases.
upstream design ../../ROOT_AGENTS.md common consumer root instruction base
upstream design ./CODEX_SUBAGENTS.md subagent routing contract
upstream design ../skills/agent-canon-update.md standalone source update owner
upstream design ../skills/pr-processing.md source PR publication owner
upstream design ../../documents/runtime/private-feedback-knowledge.md private GitHub Issue packet route
upstream implementation ../../tools/agent/skills/skill_document_reader.py bounded Skill read and EOF admission
downstream design ../skills/tokens.md token and resource-aware routing
downstream design ../../templates/agents/closeout_gate.md closeout gate contract
upstream design ../../documents/design/dependency-manifest-design.md dependency manifest design
upstream design ../../documents/design/semantic-responsibility-contract.md semantic delta and verification-owner contract
upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md runtime profile and risk-based validation routing
upstream design ../../documents/operations/BRANCH_SCOPE.md commit correctness and push contract
upstream design ../skills/tool-finding-report.md tool finding packet and prompt feedback workflow
downstream implementation ../../tools/runtime/lifecycle/task_close.py enforces closeout keys
downstream design ./CODEX_INTAKE.md selected phase procedure owner
downstream design ./CODEX_ROUTING.md selected phase procedure owner
downstream design ./CODEX_BOOTSTRAP.md selected phase procedure owner
downstream design ./CODEX_IMPLEMENTATION.md selected phase procedure owner
downstream design ./CODEX_COMPLETION.md selected phase procedure owner
@dependency-end
-->

# Codex Workflow

この文書は、Codex でこの repo を扱うときの標準フローです。
各局面の正本を下表から直接読み、適用されない局面は読み込みません。

## Reader Map

This entrypoint owns phase selection; the linked documents own the procedures.
Read the named section when its condition applies, not every linked file at startup.
Reuse still-applicable intake and decisions. A link is a read route, not an import,
new activation condition, or instruction to restart the workflow.

| When | Procedure owner | Start with |
| --- | --- | --- |
| Task intake; relevant checkout/context changed | [Codex Intake](CODEX_INTAKE.md) | [1. Intake](CODEX_INTAKE.md#1-intake), then the relevant intake section |
| Select task family, skills, validation profile, or placement | [Codex Routing](CODEX_ROUTING.md) | [Task Classification](CODEX_ROUTING.md#task-classification) |
| Selected route requires run state, goal handling, or token adaptation | [Codex Bootstrap](CODEX_BOOTSTRAP.md) | [4. Run Bootstrap](CODEX_BOOTSTRAP.md#4-run-bootstrap) or the named goal/token section |
| Design or implementation | [Codex Implementation](CODEX_IMPLEMENTATION.md) | [Design Integrity Gate](CODEX_IMPLEMENTATION.md#design-integrity-gate), [5. Implementation](CODEX_IMPLEMENTATION.md#5-implementation) |
| Validation, completion evidence, or closeout | [Codex Completion](CODEX_COMPLETION.md) | [6. Validation](CODEX_COMPLETION.md#6-validation), [Completion Readiness](CODEX_COMPLETION.md#completion-readiness) |

## Start Here

1. [AGENTS.md](../../AGENTS.md) を読む
1. [agents/skills/README.md](../skills/README.md) と `$agent-orchestration` skill を読み、routing mode と skill set を先に決める
1. [agents/TASK_WORKFLOWS.md](../TASK_WORKFLOWS.md) で task family を決める
1. implementation owner または対象差分の validation route が未解決の場合だけ、canonical router / semantic-index / dependency review のうち、その判断に必要な既存の出力を使う。解決済みの owner と実行経路は再利用し、runtime profile の未指定を環境調査や再構築の開始理由にしない
1. 作業対象の checkout と Git identity を確認する。AgentCanon source 自体の変更が要求範囲にある場合だけ、その repository-topic checkout を選ぶ。parent または同一 repository の branch は `linked-worktree`、dependency repository は `independent-clone` とし、どちらも `<anchor>/workspace/<topic>/<repo>` に置く。current checkout の dirty / unpushed / divergent state は evidence として保持する。編集候補を選ぶ前に [`Checkout Identity Readback`](../COMMUNICATION_PROTOCOL.md#checkout-identity-readback) を一度取得し、owner/path/validation に関係する依存 edge ごとに実依存 checkout の HEAD と参照 pin（存在する場合）を確認します。依存なしは未調査の既定値にせず、依存/consumer trace で edge が無い根拠を確認して記録します。cwd、branch、または依存 checkout/pin が変わった場合だけ identity と依存 HEAD を再読し、状態が変わらない通常 command では繰り返しません
1. 選択された workflow/profile が必要とする Base Runtime Packet だけを読む。inactive profile の packet は `not_applicable` として記録する
1. Cross-Cutting Packet は選択 route、review gate、または structured tool finding が必要にした slice を読む
1. 実装を伴う task では `$codex-task-workflow` と、選択された task-family Skill を読む
1. subagent を使う task では [agents/canonical/CODEX_SUBAGENTS.md](CODEX_SUBAGENTS.md) を読む
1. [agents/canonical/ARTIFACT_PLACEMENT.md](ARTIFACT_PLACEMENT.md) で文書の置き場を決める
1. 必要なら `.codex/personal/skills/` から該当 skill を読む

Base Runtime Packet:

- [README.md](../../README.md)
- [agents/workflows/README.md](../workflows/README.md)
- [agents/README.md](../README.md)
- [agents/TASK_WORKFLOWS.md](../TASK_WORKFLOWS.md)
- [agents/canonical/CODEX_WORKFLOW.md](CODEX_WORKFLOW.md)

Cross-Cutting Packet:

- [documents/conventions/REVIEW_PROCESS.md](../../documents/conventions/REVIEW_PROCESS.md)
- [documents/codex/AGENTS_COORDINATION.md](../../documents/codex/AGENTS_COORDINATION.md)
- [documents/conventions/coding-conventions-python.md](../../documents/conventions/coding-conventions-python.md)
- [documents/operations/notes-lifecycle.md](../../documents/operations/notes-lifecycle.md)
- [agents/skills/agent-learning.md](../skills/agent-learning.md)
- [documents/runtime/runtime-profiles-and-check-matrix.md](../../documents/runtime/runtime-profiles-and-check-matrix.md)
- [documents/rule/dependency-module-changes.md](../../documents/rule/dependency-module-changes.md)
- [documents/notes/guardrails/README.md](../../documents/notes/guardrails/README.md)
- [documents/notes/guardrails/engineering_avoidances.md](../../documents/notes/guardrails/engineering_avoidances.md)
- `docker/README.md`

## Execution Flow

1. Use [intake](CODEX_INTAKE.md#1-intake) to establish the requested scope and owner.
1. Resolve [workflow selection](CODEX_ROUTING.md#2-workflow-selection) and
   [placement](CODEX_ROUTING.md#3-placement), reusing decisions already established.
1. Use [run bootstrap](CODEX_BOOTSTRAP.md#4-run-bootstrap) only for its selected route.
1. Follow [implementation](CODEX_IMPLEMENTATION.md#5-implementation) at the owning unit.
1. Complete [validation](CODEX_COMPLETION.md#6-validation) and
   [closeout](CODEX_COMPLETION.md#7-closeout) with the applicable evidence.

The detailed documents preserve existing activation, authority, validation,
and failure semantics. Their presence does not activate a profile, agent,
review, run bundle, environment change, or unrelated completion criterion.
