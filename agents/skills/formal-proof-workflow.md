# formal-proof-workflow
<!--
@dependency-start
responsibility Documents the natural-language to formal-proof workflow.
upstream design ../canonical/skills.md skill canon registry.
upstream design literature-survey.md source search and bibliography workflow.
upstream design research-workflow.md external research and implementation loop.
upstream implementation ../../tools/agent_tools/formal_proof.py builds proof scaffolds.
upstream design ../../references/agent-canon-technology-bibliography.md records proof-assistant references.
downstream implementation ../../.agents/skills/formal-proof-workflow/SKILL.md exposes the skill to Codex/Copilot runtimes.
downstream implementation ../../.claude/skills/formal-proof-workflow/SKILL.md mirrors the skill for Claude-compatible runtimes.
@dependency-end
-->

## Purpose

自然言語の数学的主張、証明スケッチ、設計上の lemma、または
Python AST から抽出した証明候補を、形式証明へ進めるための workflow です。
この skill は、claim を assumptions / definitions / theorem target /
proof obligations / existing proof search / checker command に分解します。
LLM 生成文、自然言語証明、未実行の theorem stub を証明済みとは扱いません。

## Use When

- 文書や設計にある数学的 claim を Lean、Isabelle/HOL、Coq/Rocq、SMT などへ形式化したい
- 既存 formal library に theorem や lemma があるかを先に探したい
- proof assistant を使う前に proof obligation、前提、定義不足を棚卸ししたい
- 論文、scholarly note、optimization / numerical method design の理論 claim を検査可能な形に落としたい
- Python 実装の特定 symbol から side-effect-free な AST 抽出で proof scaffold を作りたい

## Core References

- `agents/skills/literature-survey.md`
- `agents/skills/research-workflow.md`
- `agents/skills/academic-writing.md`
- `agents/skills/paper-writing.md`
- `documents/tools/formal_proof.md`
- `references/agent-canon-technology-bibliography.md`

## Mandatory Checklist

- 形式化前に、claim、assumptions、definitions、target theorem、proof sketch を分けます。
- 実装由来の claim は `formal_proof.py --python-symbol path.py::qualname` で
  AST から抽出できます。この route は対象 module を import / execute しません。
- `python3 tools/agent_tools/formal_proof.py` で scaffold と query packet を作ります。
- 既存 proof search を先に行い、検索 query、採用候補、除外理由を残します。
- web search は `$literature-survey` の source policy に従い、primary source、公式 docs、formal library docs、peer-reviewed paper、preprint、blog を区別します。
- Lean/mathlib では mathlib docs、LeanSearch / Loogle / Moogle 系、Zulip archive、`exact?` / `apply?` のような in-editor tactic search を候補にします。
- Isabelle/HOL では AFP、loaded theory、Sledgehammer result、reconstruction proof を分けます。
- Coq/Rocq では library search、CoqHammer、SMTCoq、Tactician などの適用範囲と限界を記録します。
- SMT route は first-order / arithmetic / bit-vector / array など solver-friendly な obligation に限り、証明対象全体の代替にしません。
- theorem stub に `<FORMAL_TARGET>`、`sorry`、`Admitted`、placeholder が残る限り `proof_status=unverified` とします。
- 証明済み claim として採用するには、target proof assistant / solver の実行 log、tool version、import context、source file path を残します。
- checker が走らない環境では `proof_status=not_run` とし、検証 command と未確認理由を残します。

## Canonical Flow

1. Claim intake:
   - natural-language claim を一文の target に縮約する
   - Python 実装由来の claim は AST source (`--python-symbol path.py::qualname`) から provenance、signature、branch、return-expression obligation を抽出する
   - assumptions、definitions、notation、domain、expected theorem name を分ける
1. Scaffold:
   - `formal_proof.py` で plan、stub、existing proof queries、literature queries を生成する
   - output は run bundle、report、または project-local proof artifact directory に置く
1. Existing proof search:
   - local repo、`references/`、`notes/`、`documents/` を先に確認する
   - formal library docs と theorem search tools を確認する
   - web search / paper search は `$literature-survey` として source packet に残す
1. Formalization:
   - target proof assistant を選ぶ
   - `<FORMAL_TARGET>` を正式な proposition に置き換える
   - informal proof sketch を assistant-checkable lemmas に分ける
1. Automation:
   - Lean/mathlib tactic search、Isabelle Sledgehammer、CoqHammer、SMT solver などを bounded subgoal に使う
   - automation result は再構成・最小化・checker log まで確認する
1. Verification:
   - generated command か project-specific command を実行する
   - log が pass した file / theorem だけを verified にする
   - placeholder、axiom、admit、sorry、unchecked assumption は gap として残す
1. Handoff:
   - 学術文章へ戻す場合は `$academic-writing` / `$paper-writing`
   - 文献・既存 proof の source trail は `$literature-survey`
   - reader-facing report は `$report-writing`

## Required Outputs

```text
proof_claim=<path-or-inline-summary>
proof_plan_json=<path>
proof_plan_md=<path>
proof_existing_queries=<path>
proof_literature_queries=<path>
proof_stub=<path>
proof_library_trace_module=<path>
proof_checker_command=<command>
proof_checker_log=<path|not_run>
proof_status=<unverified|not_run|verified|blocked>
proof_source_packet=<path>
proof_source_kind=<natural_language|python_ast>
```

## Target Selection

- Default to Lean 4 for ordinary mathematical formalization when no project
  policy or existing artifact selects another prover.
- Use Isabelle/HOL when the claim depends on Isabelle libraries, AFP material,
  or Sledgehammer reconstruction is a good fit.
- Use Coq/Rocq when the project already owns Coq artifacts, dependent program
  proofs, extraction, or Coq-specific libraries.
- Use SMT only for subgoals that fit solver theories or as a certificate
  route, not as a replacement for higher-order or library-heavy mathematics.

## Proof Status Boundary

`verified` is allowed only when a checker command succeeds on the exact formal
artifact and the artifact has no placeholders or unchecked proof escape hatches.
Everything else is planning, search evidence, or an unverified proof sketch.
