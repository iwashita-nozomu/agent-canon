# 論文執筆 workflow

この文書は、投稿論文、thesis chapter、scholarly paper section のような paper-like 文書を書くときの正本です。
学術文章一般より paper structure の拘束を強くし、section ごとの役割、citation/evidence trace、figure/table/appendix の参照順を複数 reviewer で精査します。

この workflow は `agents/workflows/academic-writing-workflow.md` の paper-specific overlay です。
記号と論理だけでなく、citation と evidence の対応を独立 reviewer で閉じる点が違いです。

## Use When

- 学会・ジャーナル論文の draft を作る
- thesis chapter を paper 形式でまとめる
- abstract から conclusion まで paper の section role を明示して起草したい
- figure、table、appendix、citation の参照順が reader の理解を左右する

## Required Artifacts

- `paper intent brief`
- `claim contract`
- `section contract`
- `citation and evidence matrix`
- `notation ledger`
- `paragraph claim map`
- reverse outline

artifact は run bundle 内の note でも別紙でも構いませんが、reviewer が追える形にします。

## Standard Section Contract

最低限、次の役割を先に固定します。

- `abstract`
  - 問題、方法、主結果、含意を圧縮して言う
- `introduction`
  - gap、contribution、paper map を言う
- `related work`
  - 何が既知で、どこが未解決かを位置付ける
- `method`
  - setting、assumption、notation、procedure を言う
- `results`
  - observation と measured outcome を言う
- `discussion`
  - result の interpretation、scope、limitation を言う
- `limitations`
  - 何を主張していないかを明示する
- `conclusion`
  - contribution と next step を短く閉じる

必要のない section は無理に作りませんが、役割を混ぜません。

## Standard Flow

### 1. Paper Intent Brief を固定する

最初に次を短く書きます。

- target venue or paper type
- central claim
- non-goal
- expected reader
- paper が答える question

### 2. Section Contract を固定する

各 section について次を決めます。

- section purpose
- main subclaim
- prerequisite
- supporting citations / figures / tables / derivations
- section end で reader に残す message

### 3. Citation And Evidence Matrix を作る

paper では major claim と support の対応を表にします。

- claim sentence or paragraph
- supporting citation / figure / table / derivation / appendix
- support type
  - prior work
  - theorem / derivation
  - experiment result
  - implementation artifact
  - limitation evidence
- current support strength
  - direct
  - indirect
  - weak
  - missing

matrix がないまま本文を書き進めません。

### 4. Notation Ledger と Paragraph Claim Map を作る

これは `academic-writing` と同じです。
paper では figure / table reference order も paragraph claim map に含めます。

### 5. Draft を Reader Order で書く

- introduction より先に related work detail に沈みません
- method でしか定義していない quantity を abstract や introduction で乱用しません
- results では observation を述べ、discussion で interpretation を述べます
- limitation は conclusion の免責文ではなく、reader-facing な section として扱います

### 6. Mandatory Multi-Agent Review

paper writing では、次をすべて別 instance で通します。

- `document_flow_reviewer`
  - 上から読んだときの reader path、section order、前提順
- `citation_evidence_reviewer`
  - claim と citation / figure / table / derivation / appendix の traceability
- `notation_definition_reviewer`
  - notation、abbreviation、unit、index、assumption の定義順
- `logic_gap_reviewer`
  - inferential jump、hidden assumption、result と interpretation の境界
- 別 reviewer の docs completeness review
  - section 欠落、decision point 欠落、reader context 欠落

条件次第で追加します。

- `report_reviewer`
  - rebuttal、response letter、claim-heavy narrative
- critical review
  - 強い empirical claim や比較 claim
- docs consistency review
  - 複数文書や appendix / supplement と跨るとき

開始時は次で run bundle と review 宣言を機械生成できます。

```bash
python3 tools/agent_tools/doc_start.py \
  --task "paper writing task" \
  --kind paper \
  --owner "codex" \
  --workspace-root "$PWD"
```

### 7. Revision Order

1. section role の混線
1. citation / evidence mismatch
1. notation / definition order gap
1. logic gap と hidden assumption
1. completeness gap
1. sentence-level polish

## Closeout

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

## Relationship To Other Workflows

- 長文一般の構成技法は `agents/workflows/long-form-writing-workflow.md`
- 学術文章一般の原則は `agents/workflows/academic-writing-workflow.md`
- 文献探索が主 task なら `agents/workflows/research-workflow.md`
