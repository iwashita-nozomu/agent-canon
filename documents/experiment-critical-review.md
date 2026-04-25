# 実験の批判的レビュー手順
<!--
@dependency-start
@dependency-end
-->


この文書は、実験コード、結果レポート、図表、結論の妥当性を批判的にレビューするための正本です。
個別の実験 topic に依存しない review 観点をまとめ、`experiment_reviewer`、`report_reviewer`、`change_reviewer` が共通に参照できる形にします。

実験全体の標準手順は [experiment-workflow.md](../agents/workflows/experiment-workflow.md) を参照してください。
レポート本文の構成は [experiment-report-style.md](experiment-report-style.md) を参照してください。
問い、比較対象、逐次改造の流れは [research-workflow.md](../agents/workflows/research-workflow.md) を参照してください。

## 1. 目的

批判的レビューの目的は、単に「run が終わった」ことを確認することではありません。
次を独立に確認することが目的です。

- 実験コードが、書かれている数式や方法を本当に実装しているか
- レポートが結果の列挙で終わらず、問いに対する判断文書になっているか
- 外部文献、baseline、既知の方法とどう接続するかが明示されているか
- 結論に必要なデータ、図表、比較条件が欠けていないか
- 図の表示方法が誤解を招かないか
- 計算式、変数、仮定、数値リスクが読者に見える形で書かれているか

## 2. 役割分担

批判的レビューでは、code review と experiment review を分けます。

- `change_reviewer`
  - code diff を見る。
  - 特に、実装が設計どおりか、危険な shortcut が入っていないか、数値的に危うい変更がないかを見る。
- `experiment_reviewer`
  - protocol、結果、図表、解釈、結論をまとめて見る。
  - 特に、比較公平性、evidence の十分性、overclaim、図表の妥当性を見る。
- `report_reviewer`
  - user-facing report を独立に見る。
  - 特に、概要、主要数値の見せ方、figure / table の読みやすさ、結論と根拠の対応、rewrite / 追加検証 / rerun の判定を見る。

数学的妥当性は code だけでは完結しないため、

- code と equation の対応
- parameter / initial condition / boundary condition の記述
- figure と結論の対応

は `change_reviewer` と `experiment_reviewer` の両方で見ます。

## 3. 学術的な根拠

この review 手順は、次の文献やガイドラインを基に整理しています。

- Minocher et al., *Implementing code review in the scientific workflow*:
  - review の四つの優先事項を
    - code is as reported
    - code runs
    - code is reliable
    - code reproduces stated results
    として整理しています。
- Tiwari et al., *Reproducibility in systems biology modelling*:
  - 数式、parameter、initial condition、units の欠落や誤記が再現失敗の主要因になることを示しています。
- Bartz-Beielstein et al., *Benchmarking in Optimization: Best Practice and Open Issues*:
  - 明確な goal、well-specified problems、適切な指標、thoughtful analysis、comprehensible presentations、reproducibility を benchmark review の主要要素として整理しています。
- Rougier et al., *Ten Simple Rules for Better Figures*:
  - caption、軸、scale、default 設定、図の媒体適合性が、図の読みを大きく左右することを示しています。
- Nature, *Guidance on reproducibility for papers using computational tools*:
  - custom code の validation、code availability、documentation、tests、benchmark との比較を明示することを求めています。
- NeurIPS Paper Checklist Guidelines:
  - proofs / derivations、実験設定、error bars、統計的有意性、limitation を review の一部として明示しています。

さらに、生成 AI を review 補助に使うときは、review の自動化そのものを結論にしません。
AI に要約や論点抽出を補助させても、math validity、figure validity、citation integrity、overclaim の最終判断は人間が保持します。
この点は、review 支援や multi-agent scientific workflow を扱う文献でも一貫して重要です。

この repo の review は、これらの観点を

- 実験コード review
- report review
- 図表 review
- claim review

へ落とし込んだものです。

## 4. レビューの主質問

批判的レビューでは、少なくとも次の 6 問を順に確認します。

### 4.1 実験コードが数学的に妥当か

最低限次を確認します。

- code が methods / equation / README に書かれた手法と一致しているか
- 目的関数、更新式、積分式、離散化、停止条件が code と文書で食い違っていないか
- parameter、initial condition、boundary condition、dtype、units が欠けていないか
- baseline や analytical reference があるなら、その比較経路が code 上で実在するか
- 「run する」だけでなく、中間量が意味的に正しいか

`Blocker:`
数式と code が一致しない、parameter が欠落して再現不能、unit や sign が曖昧、という状態です。

### 4.2 結果の報告に終始していないか

最低限次を確認します。

- `Results` が観測事実、`Discussion` がその意味、という分離が守られているか
- 「速かった」「精度が良かった」だけでなく、問いに対して何が言えて何がまだ言えないかが書かれているか
- failure case、negative result、limitation が落ちていないか
- report が単なる log やスクリーンショット集になっていないか

`Blocker:`
結果の数字はあるが、比較対象、問い、結論、限界がつながっていない状態です。

### 4.3 外部文献との接続が明記されているか

最低限次を確認します。

- 問題設定や手法選択が literature とどうつながるか書かれているか
- baseline や prior work が選ばれた理由が書かれているか
- 文献から確定的に言えることと、自前の観測や仮説が区別されているか
- 文献に依拠した数式、評価指標、既知の failure mode に source があるか

`Blocker:`
自前の設計判断が既知の方法との差分なしに書かれており、比較の意味が不明な状態です。

### 4.4 結論に必要なデータが明記されているか

最低限次を確認します。

- 結論を支える case 数、success / failure 数、failure kind があるか
- 比較対象ごとに同じ case set を使っているか
- 主要 metric の代表値だけでなく、ばらつきや error bar の意味が説明されているか
- 結論に必要な table / figure / final JSON への導線があるか
- partial run や subset run を正式 evidence に混ぜていないか

`Blocker:`
結論が figure だけで語られ、数表、case 数、失敗率、条件帯が明示されていない状態です。

### 4.5 示している図が表示方法として正しいか

最低限次を確認します。

- 軸名、単位、scale が明示されているか
- linear / log の選択理由があるか
- color map、bar plot、3D plot、dual axis などが読みを歪めていないか
- caption が図の読み方、条件、主要 trend を説明しているか
- error bars を使うなら、その意味、計算方法、仮定が本文か caption にあるか
- 図が journal article 用か monitor 用かを区別し、媒体に合う表示になっているか

`Blocker:`
軸、unit、scale、legend がなく、図だけでは何を見ればよいか分からない状態です。

### 4.6 計算式が明示されているか

最低限次を確認します。

- `Equation:` または擬似数式があるか
- 記号の意味、index、range、constraint が定義されているか
- 数値安定性や approximation の仮定が書かれているか
- 理論 claim に derivation や proof sketch が必要な場合、その所在があるか

`Blocker:`
主要な更新式や評価式が本文にも補足にも見当たらず、読者が code を読まないと method を再構成できない状態です。

## 5. 実験コードレビューの詳細チェック

実験コード review では、少なくとも次を順に確認します。

### 5.1 As Reported

- README、note、methods section に書かれたことと code が一致しているか
- case range、timeout、allocator 方針、platform 切替が、報告どおり引数化されているか
- ad hoc な条件分岐が script 本体に埋め込まれていないか

### 5.2 Runs

- `--help` を含め CLI が壊れていないか
- import path、dependency、version 情報が分かるか
- fresh run を 1 invocation で回す前提が守られているか

### 5.3 Reliable

- 中間量を確認する path があるか
- analytical check、reference implementation、unit test、small smoke があるか
- index、shape、dtype、unit の取り違えが入りやすい箇所に手当てがあるか

### 5.4 Reproducible

- commit、branch、command、output path が記録されるか
- final JSON と JSONL の関係が分かるか
- partial を resume の正本にしない運用が守られているか

## 6. レポートレビューの詳細チェック

レポート review では、少なくとも次を順に確認します。

この section は `report_reviewer` が必ず読みます。

### 6.1 Question-Claim Alignment

- 問いに答える構造になっているか
- 結論が protocol の範囲を越えていないか
- 改善主張が対象帯域を越えて一般化されていないか

### 6.2 Evidence Sufficiency

- 各主張に figure または table が結び付いているか
- failure case を都合よく除外していないか
- representative case、worst case、failure case の少なくとも 1 つが本文で扱われているか

### 6.3 Literature Connection

- prior work、baseline、外部 reference との位置づけが明示されているか
- `Source:` と `Idea:` と `Interpretation:` が混ざっていないか

### 6.4 Figure Validity

- 図の読み方が明示されているか
- 重要な数字が figure だけに閉じず、table や本文でも拾えるか
- default 表示のままで誤認を招いていないか

### 6.5 Formula Visibility

- 核となる計算式が本文か補足にあるか
- 変数定義、仮定、boundary condition が省略されていないか

### 6.6 Review Outcome

- `report_rewrite_required`
  - evidence は足りているが、説明順、数値の見せ方、図表導線、結論の書き方が弱い
- `extra_validation_required`
  - 同じコードと比較方針のまま、追加 table、追加 figure、追加 narrow run が必要
- `rerun_required`
  - case set 不一致、条件変更、partial run 混入、protocol 汚染がある
- `approved`
  - reader-facing report として閉じてよい

## 7. レビュー結果の書き方

review の出力は、次の順を基本にします。

1. Findings
   - severity 順に並べる。
   - file / section / figure / table を明記する。
2. Open Questions
   - 読んでも確定できない点だけを残す。
3. Missing Evidence
   - 追加 run、追加 table、追加 citation、追加 equation が必要な点を書く。
4. Next Check
   - 次の 1 回の修正や再実行で何を確かめるべきかを書く。

review コメントの粒度は次を目安にします。

- `Blocker`
  - 結論の妥当性が崩れる。
- `High`
  - 比較公平性、再現性、図の読み、math validity を大きく損ねる。
- `Medium`
  - 解釈の厳密さや可読性を損ねる。
- `Low`
  - 表現改善、導線改善、補強 citation の不足。

## 8. 最低限のレビュー用テンプレート

次をそのまま埋めてもよいです。

    ## Critical Review

    ### Mathematical Validity
    - <fill here>

    ### Literature Connection
    - <fill here>

    ### Evidence Sufficiency
    - <fill here>

    ### Figure Validity
    - <fill here>

    ### Equation Visibility
    - <fill here>

    ### Overclaim Risk
    - <fill here>

    ### Missing Evidence
    - <fill here>

    ### Alternative Explanation
    - <fill here>

    ### Next Check
    - <fill here>

## 9. 参考文献

ローカルの入口は次です。

- [references/README.md](../references/README.md)
- [workflow-references.md](../agents/workflows/workflow-references.md)

### 批判的レビュー・再現性

- [Minocher et al. (2023), Implementing Code Review in the Scientific Workflow](https://doi.org/10.12688/f1000research.27137.2)
- Tiwari et al. (2021), Reproducibility in Systems Biology Modelling
- [Bartz-Beielstein et al. (2020), Benchmarking in Optimization: Best Practice and Open Issues](https://doi.org/10.48550/arXiv.2007.03488)
- [Rougier et al. (2014), Ten Simple Rules for Better Figures](https://doi.org/10.1371/journal.pcbi.1003833)
- [Nature, Guidance on Reproducibility for Papers Using Computational Tools](https://www.nature.com/articles/d41586-022-00563-z)
- [NeurIPS Paper Checklist Guidelines](https://nips.cc/public/guides/PaperChecklist)
- [Sandve et al. (2013), Ten Simple Rules for Reproducible Computational Research](https://doi.org/10.1371/journal.pcbi.1003285)
- [Wilson et al. (2017), Good Enough Practices in Scientific Computing](https://doi.org/10.1371/journal.pcbi.1005510)

### 生成AIによるレビュー・workflow 支援

- Rethinking the AI Scientist: Interactive Multi-Agent Workflows for Scientific Discovery
- Towards Scientific Discovery with Generative AI: Progress, Opportunities and Challenges
- Wu et al. (2025), Automated Literature Research and Review-Generation Method Based on Large Language Models
- OpenReviewer: A Specialized Large Language Model for Generating Critical Scientific Paper Reviews
