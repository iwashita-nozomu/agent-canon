# academic-writing
<!--
@dependency-start
contract skill
responsibility Documents academic-writing for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable document structure contract
upstream design prose-reasoning-graph.md prose graph diagnostics and rewrite handoff overlay
upstream design ../../CONTAINER_OPERATIONS.md TeX devcontainer tooling boundary
downstream implementation ../../.agents/skills/academic-writing/SKILL.md Codex skill shim
@dependency-end
-->


## Reader Map

- Purpose: routes scholarly prose through notation, logic, and reader-flow
  review before drafting or revising.
- Use When: drafting or revising papers, thesis chapters, scholarly notes, or
  academic documents outside a more specific paper-submission route.
- Section path: Purpose, Use When, and Core References set scope; Mandatory
  Checklist, Default Sequence, and Standard Command are the operational rules;
  TeX Output Boundary and Boundary limit the surface.
- Boundary: submission-paper ownership goes through `paper-writing` when that
  more specific route applies.

## Purpose

file / document responsibility が academic prose、scholarly note、thesis chapter、
method note、symbol-dense claim-heavy explanation の文書を、共通 graph/DSL 構造から
学術 prose へ射影する adapter skill です。claim、notation、logic を分離 review します。
選択基準は長さではなく、文書責務と review gate です。

## Use When

- 学術論文や chapter を新規作成する
- claim-heavy な survey、method note、appendix を書く
- 記号、略語、technical term、仮定、根拠の接続が reader の理解を左右する
- 一般の guide より、論理の欠落や定義順の破綻が問題になる
- file responsibility の判定結果が、一般説明 prose や report ではなく academic prose adapter を要求している

## Core References

- `agents/workflows/academic-writing-workflow.md`
- `agents/workflows/paper-writing-workflow.md`
- `agents/workflows/long-form-writing-workflow.md`
- `documents/REVIEW_PROCESS.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `agents/skills/literature-survey.md`
- `CONTAINER_OPERATIONS.md`

## Mandatory Checklist

- `claim contract` で central contribution、gap、reader、non-goal を先に固定する
- section order、figure/table placement、claim/evidence layout が非自明な場合は `structure-planning` で構造 contract を先に固定する
- claim flow、transition pair、logic-gap triage が非自明な場合は、`structure-planning` で `agent-canon semantic-index discourse-relations --profile academic-argument` を使う
- 非自明な academic prose の新規作成・改稿では、reader-facing prose の前に `prose-reasoning-graph` の handoff を作るか受け取る
- prose graph diagnostics は unsupported claim、weak bridge、experiment completeness、split / merge / reorder operations を logic-gap review と paragraph claim map の入力にする
- prose graph handoff に `selected_ordering.ordered_anchors` がある場合は、全文 sentence anchor の topological order を DSL-to-prose input sequence として使う
- graph responsibility は肯定形の academic prose contract に射影する。claim、definition、warrant、evidence relation、limitation、reviewer handoff を直接書く。否定形の boundary は Boundary / Limitation / Non-Goal slot に集約し、`ad hoc` label は責務名、evidence gap、verification route、prompt-defect classification のいずれかへ置き換える
- reader-facing prose に入る前に DSL / projection 段階で `fix-now` finding を閉じる。claim contract、evidence map、paragraph claim map、graph-backed rewrite packet、または graph-backed unit を直し、graph diagnostics を再実行してから draft する
- DSL / projection から prose に射影した後、同じ graph check を再実行する。閉じた DSL/projection には無かった finding が射影後に出た場合は `dsl_to_prose_prompt_defect` として academic prose-generation prompt を直す
- `evidence map` で claim と support を section 単位で結ぶ
- `notation ledger` を作り、symbol / term / abbreviation / unit / index を管理する
- `paragraph claim map` を作り、各 paragraph の inferential role を固定する
- Codex では、可能なら parent session 側の plan-mode command を使う。official Codex CLI では `/plan`
- runtime が `/agent` を提供する場合は inventory を確認し、使えない場合は `.codex/agents/*.toml` を見る
- run bundle を先に作り、`notation_definition_reviewer` と `logic_gap_reviewer` を explicit に有効化する
- paper-like draft では `citation_evidence_reviewer` も explicit に有効化する
- draft 後に reverse outline を取る
- `document_flow_reviewer` を必ず通す
- 別 reviewer で notation review を必ず通す
- 別 reviewer で logic-gap review を必ず通す
- 別 reviewer で docs completeness review を必ず通す
- empirical claim や report なら critical review、必要なら report review を追加する
- 投稿論文や thesis chapter では `paper-writing` を優先 overlay とする
- PDF-ready な学術文章、数式密度の高い draft、または図版を作るときは TeX output plan を作り、devcontainer の `latexmk` / pdfLaTeX / XeLaTeX / `dvisvgm` / `pdfcrop` toolchain を使う
- TeX を使う既定配線はこの skill に限る。一般 README、workflow、guide、migration doc、通常 report は TeX へ自動遷移しない

## Default Sequence

1. `claim contract` を短く書く
1. 必要なら `structure-planning` で first section / figure / table、source-to-structure map、section order、invalid interpretation を固定する
1. paragraph order や discourse connective が論点なら discourse-relations JSONL を構造 evidence として添付する
1. `evidence map` と `notation ledger` を作る
1. `section contract` と `paragraph claim map` を作る
1. 非自明な academic prose なら prose graph handoff を作るか受け取り、DSL / projection finding closure loop を回してから reader-facing prose に入る
1. PDF-ready draft、数式、図版が必要なら TeX output plan を固定する
1. run bundle を作る
1. reader order で draft する
1. TeX output plan が active なら `.tex` source を作り、document は `latexmk -pdf`、図版は `latexmk -pdf` と `dvisvgm` / `pdfcrop` で検証する
1. reverse outline を取る
1. `document_flow_reviewer` を通す
1. `notation_definition_reviewer` に notation review を通す
1. `logic_gap_reviewer` に logic-gap review を通す
1. 別 reviewer に docs completeness review を通す
1. higher-order revision を終えてから line edit に入る
1. `tools/bin/agent-canon docs check` で閉じる

## Standard Command

```bash
python3 tools/agent_tools/doc_start.py \
  --task "academic writing task" \
  --kind academic \
  --owner "codex" \
  --workspace-root "$PWD"
```

## TeX Output Boundary

- TeX は `$academic-writing` の既定出力 route です。PDF-ready な学術文章、数式密度の高い manuscript、TikZ / standalone 図版、または reviewer に渡す図表を作るときに使います。
- TeX toolchain は devcontainer の `.devcontainer/post-create.sh` が用意します。必要な command は `latexmk`、`pdflatex`、`xelatex`、`dvisvgm`、`pdfcrop` です。
- 生成物は原則 run bundle や ignored output directory に置き、tracked tree には canonical `.tex` source と、ユーザーが要求した final artifact だけを残します。
- TeX を一般の `$long-form-writing`、workflow guide、migration doc、ordinary report の既定 route にしません。それらはユーザーが明示した場合だけ TeX を使います。

## Boundary

- 一般の README、workflow、migration 文書なら `long-form-writing` を使います
- 文献調査自体が主タスクなら `literature-survey` を先に使います
- experiment report の evidence traceability は report review を優先します
