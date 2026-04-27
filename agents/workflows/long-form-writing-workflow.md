# 長文作成 workflow
<!--
@dependency-start
upstream design README.md workflow catalog
@dependency-end
-->


この文書は、README、workflow 文書、移行文書、設計補助文書、reader-facing guide のような長めの文章を作るときの正本です。
単なる Markdown 編集ではなく、読者、構成、段落順、review を先に固定する workflow として扱います。

この workflow は外部の writing guide を、そのまま転載せず repo 向けに再構成したものです。
とくに `summary statement`、`roadmap`、`reverse outline`、`higher-order concerns`、`scannable content` は外部資料に基づく概念で、ここでの `section contract` と reviewer routing は repo 向けの推論です。

## Use When

- 新しい README、guide、workflow 文書を書く
- 既存文書を大きく組み替える
- 1 screen を超える長さの reader-facing 文書を書く
- 複数 section の argument や decision path を持つ文書を書く

学術論文、thesis chapter、scholarly note のような文書は `agents/workflows/academic-writing-workflow.md` を優先します。

## Core Principles

- 先に `何を言う文書か` を固定してから書く
- 見出し列を、あとで本文が従う roadmap として扱う
- section ごとに `focus`、`purpose`、`support` を先に固定する
- 長文では、scan できる構造と linear に読んだときの意味の両方を満たす
- line edit より先に、focus、purpose、order、gap を直す
- 長文作成では subagent review を必須にする
- readability や reader flow の accept / reject は tool check ではなく agent review で決める

## Standard Flow

### 1. Summary Statement を固定する

書き始める前に、少なくとも次を短く書きます。

- 文書全体の argument / main point を 1-2 文
- 文書の purpose を 2-4 文
- 想定 reader を 1 つ

repo ではこれを `summary statement` と呼びます。
長文で途中脱線するのを防ぐための固定点です。

### 2. Roadmap と Section Contract を作る

`summary statement` を基準に、見出し列を先に作ります。

- section の順番
- 各 section の `focus`
- 各 section の `purpose`
- 各 section が依拠する evidence、artifact、file path、supporting point

repo では、Purdue OWL の sentence / skeleton outline を、`section contract` に落として使います。
section contract が曖昧なまま本文を書き始めません。

### 3. Reader Order で draft する

draft では、最初の reader が上から読む順番を基準にします。

- 先に結論、判断軸、要点を置く
- 必要な前提を、使う前に出す
- 長い文書には table of contents か同等の navigation を置く
- 見出し、箇条書き、比較項目では parallel structure を使う
- 段落は短く保ち、dense block を避ける

### 4. Reverse Outline を取る

draft 後に、paragraph か section ごとに 1 文要約を作ります。

- この paragraph / section は何をしているか
- それは文書全体の `summary statement` にどう繋がるか
- 途中で遅れて出る前提、定義、判断軸がないか

reverse outline で、focus drift、logic gap、section order の乱れを見つけます。

### 5. Higher-Order Revision を先にやる

feedback を受けたら、wording 修正より先に次を見ます。

- argument / purpose がずれていないか
- section order が妥当か
- 欠けている前提、定義、手順、decision point がないか
- どの指摘を先に直すべきか

feedback は action list に落とし、higher-order concern から先に潰します。

### 6. Mandatory Subagent Review を通す

長文作成では、subagent review を省略しません。

開始時は、必要なら次で run bundle と宣言を機械生成します。

```bash
python3 tools/agent_tools/doc_start.py \
  --task "long-form document task" \
  --kind long-form \
  --owner "codex" \
  --workspace-root "$PWD"
```

最低限:

- `document_flow_reviewer`
  - 上から読んだときの意味の通り方、定義順、section order、reader path を見る
- 別 instance の `reviewer`
  - docs completeness review を使い、読者に必要な情報の欠落を探す

`make docs-check`、lint、link check は体裁や壊れた参照の検出には使えますが、読みやすさや reader flow の accept evidence にはしません。可読性は `document_flow_reviewer` と completeness reviewer の judgement を正本にします。

追加条件:

- 複数文書、entrypoint、canonical doc をまたぐなら docs consistency review を追加する
- repo-wide canon を触るなら `project_reviewer` を追加してよい
- 実験 report なら report review を併用し、report policy を優先する

`document_flow_reviewer` と completeness reviewer は兼務させません。

### 7. Validation と Closeout

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

validation command が通っても readability は自動では pass しません。closeout では agent review artifact に可読性 judgement が残っていることを確認します。

## Review Outcomes

- `rewrite_required`
  - summary statement、section order、前提順、欠落情報のいずれかが崩れている
- `consistency_fix_required`
  - 他文書との食い違いが残っている
- `approved`
  - top-down readability、information completeness、canon alignment が揃っている
  - tool check pass は補助条件であり、これだけでは `approved` にしない

## Repo Interpretation

- `summary statement` は task note、run artifact、または draft 冒頭メモでよい
- `section contract` は大げさな別紙でなくてよいが、見出しごとの `focus/purpose/support` は実際に固定する
- 長文作成 task では `long-form-writing` skill を明示的に読み、reviewer subagent を先に割り当てる
- 記号密度が高い、または claim-heavy な academic 文書では `academic-writing` へ切り替える
- 設計文書そのものは `implementation-waterfall-workflow.md` の gate に従い、ここでは writing 技法だけを補います

## External Basis

- [Reverse Outlining | John S. Knight Institute for Writing in the Disciplines](https://knight.as.cornell.edu/reverse-outlining)
  - `summary statement` を固定し、reverse outline で focus / logic gap を見る構成
- [Creating a Roadmap | Purdue OWL](https://owl.purdue.edu/owl/graduate_writing/documents/creating-a-roadmap.pdf)
  - roadmap、sentence outline、skeleton outline、section purpose を先に固定する構成
- [Writing with Feedback on a Manuscript | Purdue OWL](https://owl.purdue.edu/owl/general_writing/the_writing_process/feedback/editor-reviewer_feedback.html)
  - feedback を checklist 化して priority 順に処理する revision 運用
- [Higher Order Concerns | Purdue OWL](https://owl.purdue.edu/owl/subject_specific_writing/professional_technical_writing/prioritizing_your_concerns_for_effective_business_writing/index.html)
  - line edit より先に focus、purpose、organization を直す review 順序
- [Scannable content - Microsoft Style Guide](https://learn.microsoft.com/en-us/style-guide/scannable-content/)
  - 長文に navigation、parallel structure、short paragraph、lead-with-what-matters を入れる考え方
