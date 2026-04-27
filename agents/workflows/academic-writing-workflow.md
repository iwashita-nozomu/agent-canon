# 学術文章 workflow
<!--
@dependency-start
upstream design README.md workflow catalog
@dependency-end
-->


この文書は、論文、thesis chapter、scholarly note、method note、claim-heavy な technical memo のような学術文章を作るときの正本です。
一般の長文作成とは分けて扱い、論理、記号定義、根拠の接続を段階ごとに複数 reviewer で精査します。
投稿論文や thesis chapter では、さらに `agents/workflows/paper-writing-workflow.md` を paper-specific overlay として使います。

この workflow は、Purdue OWL、Cornell Knight Institute、MIT OpenCourseWare、PLOS Computational Biology の writing guide を repo 向けに再構成したものです。
ここでの `claim contract`、`notation ledger`、`paragraph claim map`、`logic-gap review` は local interpretation です。

## Use When

- 論文 draft、thesis chapter、technical note、method note を書く
- claim-heavy な survey、research proposal、appendix、response letter を書く
- 記号、略語、定義、仮定、証拠のつながりが reader の理解を左右する文書を書く
- section ごとの argument と paragraph ごとの inferential step を明示したい

## Core Principles

- reader と central contribution を先に固定する
- 文書全体の gap、claim、supporting evidence を先に固定する
- 記号、略語、用語、仮定は `use before definition` を許さない
- paragraph は単なる prose block ではなく、1 つの claim step として扱う
- 結果、解釈、限界、今後の課題を混ぜない
- wording の polish より前に、logic gap と notation gap を潰す
- author 1 人の自己点検だけで閉じず、独立 reviewer を段階ごとに通す

## Standard Flow

### 1. Claim Contract を固定する

書き始める前に、少なくとも次を短く固定します。

- central contribution / main claim を 1-2 文
- どの gap を埋める文書か
- 想定 reader
- 文書種別
  - empirical paper
  - method note
  - theory note
  - survey
  - proposal

repo ではこれを `claim contract` と呼びます。
この時点で、何を主張しないかも 1 行で書きます。

### 2. Evidence Map を作る

主張を section ごとに支える根拠を並べます。

- どの section がどの subclaim を担当するか
- その subclaim を支える citation、result、figure、derivation、artifact
- まだ不足している evidence
- reader が先に知るべき前提

この段階で、claim と support が 1 対 1 か、少なくとも辿れる形になっていない paragraph は書き始めません。

### 3. Notation Ledger と Definition Order を固定する

記号や用語がある文書では、本文前に ledger を作ります。

- symbol / term
- meaning
- domain / unit / type / index
- 初出 section
- 依存する前提や definition
- 似た記号や紛らわしい語との区別

対象:

- 数式中の記号
- 変数名
- 添字
- 略語
- technical term
- overloaded concept

本文より前に完璧な表を公開する必要はありませんが、author と reviewer が definition order を追える状態にはします。

### 4. Section Contract と Paragraph Claim Map を作る

`claim contract` と `evidence map` に基づいて、見出しと paragraph role を先に固定します。

section ごとに:

- focus
- purpose
- support
- 先に必要な prerequisite

paragraph ごとに:

- 冒頭で何の question / claim step を扱うか
- 途中で何を evidence として出すか
- 最後に何が結論として残るか

結果 section では、paragraph の終わりに reader が何を受け取るかが曖昧なまま進めません。

### 5. Draft を Reader Order で書く

draft では次を守ります。

- abstract / introduction / results / discussion の役割を混ぜない
- 結論や gap を reader が受け取る前に detail へ飛ばない
- 定義、記号、略語、仮定を使う前に出す
- 同じ concept には同じ語と同じ notation を使う
- 結果と解釈を混ぜず、どこから inference が入るかを明示する
- one paragraph = one main move を維持する

### 6. Reverse Outline と Dependency Check を取る

draft 後に、section と paragraph を 1 文で言い直します。

- この paragraph はどの claim step を担うか
- どの前 paragraph に依存するか
- この inference は evidence から飛びすぎていないか
- 後から出てくる definition や assumption がないか

ここで `logic gap`、`late definition`、`result/interpretation blur` を探します。

### 7. Mandatory Multi-Agent Review を通す

学術文章では、次を必須とします。

- `document_flow_reviewer`
  - 上から読んだときの reader path、section order、前提順を確認する
- `notation_definition_reviewer`
  - 記号、略語、technical term、仮定、domain / unit / index の definition-before-use と一貫性を確認する
- `logic_gap_reviewer`
  - 主張の飛躍、暗黙の仮定、根拠不足、result から interpretation へのジャンプを確認する
- 別 reviewer による docs completeness review
  - 読者に必要な背景、条件、入力、出力、限界、decision point の不足を探す

追加条件:

- 投稿論文や thesis chapter では `citation_evidence_reviewer`
- 複数文書を跨ぐなら docs consistency review
- empirical claim が強いなら critical review
- report / response / rebuttal として出すなら report review

`document_flow_reviewer`、`citation_evidence_reviewer`、`notation_definition_reviewer`、`logic_gap_reviewer`、completeness reviewer は兼務させません。

開始時は次で run bundle と review 宣言を機械生成できます。

```bash
python3 tools/agent_tools/doc_start.py \
  --task "academic writing task" \
  --kind academic \
  --owner "codex" \
  --workspace-root "$PWD"
```

### 8. Revision Order を守る

review 後は次の順で直します。

1. claim / gap / contribution のずれ
1. section order と paragraph order
1. logic gap と unstated assumption
1. notation / definition / abbreviation gap
1. completeness gap
1. wording、style、sentence-level polish

line edit を先に始めません。

### 9. Validation と Closeout

最低限:

```bash
make docs-check
```

必要なら:

```bash
make agent-checks
python3 tools/docs/check_markdown_lint.py documents notes
python3 tools/docs/audit_and_fix_links.py --check documents notes
```

## Mandatory Review Outcomes

- `rewrite_required`
  - claim contract、logic chain、definition order のどれかが崩れている
- `notation_fix_required`
  - 記号、略語、technical term、unit、index に未定義や不整合がある
- `logic_fix_required`
  - 支持されていない inference や飛躍がある
- `approved`
  - top-down readability、notation discipline、logic continuity、information completeness が揃っている

## Repo Interpretation

- draft author は `long_form_writer` でよいが、学術文章では `academic-writing` skill を明示して進める
- 投稿論文や thesis chapter では `paper-writing` skill を優先する
- `notation ledger` と `paragraph claim map` は別紙でも run artifact でもよい
- 設計文書が学術文章に近い密度になったら、この workflow を overlay として使ってよい
- 長文一般の構成技法は `agents/workflows/long-form-writing-workflow.md` を併用する

## External Basis

- [Ten simple rules for structuring papers | PLOS Computational Biology](https://doi.org/10.1371/journal.pcbi.1005619)
  - central contribution、context-content-conclusion、logical flow、feedback from multiple people の根拠
- [Creating a Roadmap | Purdue OWL](https://owl.purdue.edu/owl/graduate_writing/documents/creating-a-roadmap.pdf)
  - roadmap と section purpose を先に固定する根拠
- [Flow in Scholarly Writing | Purdue OWL](https://owl.purdue.edu/owl/graduate_writing/documents/Flow-Handout.pdf)
  - paragraph-level flow、support、transition、text-level alignment の根拠
- [Writing with Feedback on a Manuscript | Purdue OWL](https://owl.purdue.edu/owl/general_writing/the_writing_process/feedback/editor-reviewer_feedback.html)
  - feedback を checklist 化して revision する根拠
- [Reverse Outlining | John S. Knight Institute for Writing in the Disciplines](https://knight.as.cornell.edu/reverse-outlining)
  - reverse outline で focus と gap を検査する根拠
- [Writing Tips | MIT OpenCourseWare](https://ocw.mit.edu/courses/8-06-quantum-physics-iii-spring-2016/e498e7c0d2db9e3846df12bfdac3e10e_MIT8_06S16_TermPaper.pdf)
  - scientific writing では ambiguity を避け、導入した quantity を明確に定義する根拠
