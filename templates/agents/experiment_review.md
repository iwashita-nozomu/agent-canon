# Experiment Review（実験レビュー）
<!--
@dependency-start
contract template
responsibility Documents Experiment Review for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


{{>reader_map}}
{{>review_contract}}

{{>findings_required_change_table}}

## Review Focus（確認点）

- 比較の公平性
- metric の妥当性
- 定量要約の品質
- report structure の品質
- abstract が数値付きで主要 finding を述べるか
- Results と Discussion が適切に分離されるか
- figure/table が周辺 prose なしで解釈できるか
- axis、unit、linear/log scale が明記されるか
- conclusion が根拠となる figure/table を引用するか
- 順序付き difficulty axis の sweep が正当な理由なく途切れていないか
- 同じ case set を比較したか
- aggregation により failure を隠していないか
- 過大主張リスク
- restart または rerun の判断
- 次の変更の正当化

## Critical Questions（重要な問い）

- conclusion が平均値だけに依存していないか。
- headline metric の横に success rate と failure kind があるか。
- baseline comparison が同じ case と condition で行われたか。
- abstract が main result と scope を実際に述べるか。
- Results が explanation より先に observation を報告するか。
- Discussion に Results に置くべき新しい evidence が混入していないか。
- 主要 figure ごとに axis name、unit、linear/log scale が明示されるか。
- 各 major conclusion が supporting figure/table を指すか。
- dimension/level sweep が連続しているか、例外があれば正当化されているか。
- interpretation が観測 data に支えられるか、それとも speculative か。
- 次の code change または claim の前に不足している evidence は何か。
