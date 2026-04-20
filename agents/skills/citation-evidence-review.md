# citation-evidence-review

## Purpose

論文、thesis chapter、claim-heavy な academic text で、各主張が citation、figure、table、derivation、result に本当に結び付いているかを独立に見る skill です。

## Use When

- 論文本文で citation と主張の対応が reader の信頼性を左右する
- source を挙げているが、本文の言い方が source の強さを超えている可能性がある
- figure/table/appendix/result 参照が claim の支えとして十分かを点検したい
- literature survey より、既に集めた citation が本文の主張を正しく支えているかを見たい

## Core References

- `agents/workflows/paper-writing-workflow.md`
- `agents/workflows/academic-writing-workflow.md`
- `documents/REVIEW_PROCESS.md`
- `agents/templates/citation_evidence_review.md`

## Checklist

- major claim ごとに citation / figure / table / derivation / appendix / result の支え先を辿る
- cited source が本文の wording を本当に支持しているかを見る
- `shows`, `proves`, `suggests`, `is consistent with` の強さが source と合っているかを見る
- no-citation claim と under-cited synthesis を拾う
- source mismatch と support mismatch を notation/style issue と混ぜない

## Boundary

- 用語導入順と section order は `document_flow_reviewer` を使います
- 記号、略語、technical term、unit、index は `notation-definition-review` を使います
- hidden assumption と inferential jump は `logic-gap-review` を使います
