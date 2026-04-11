# Method Memory

`memory/methods/` は、role 固有ではなく方法ベースの memory を置く層です。
複数の subagent が同じ file を読み、同じ execution method を共有します。

## Files

- [requirements.md](/mnt/l/workspace/project_template/memory/methods/requirements.md)
- [planning.md](/mnt/l/workspace/project_template/memory/methods/planning.md)
- [design.md](/mnt/l/workspace/project_template/memory/methods/design.md)
- [implementation.md](/mnt/l/workspace/project_template/memory/methods/implementation.md)
- [testing.md](/mnt/l/workspace/project_template/memory/methods/testing.md)
- [review.md](/mnt/l/workspace/project_template/memory/methods/review.md)
- [verification.md](/mnt/l/workspace/project_template/memory/methods/verification.md)
- [research.md](/mnt/l/workspace/project_template/memory/methods/research.md)
- [operations.md](/mnt/l/workspace/project_template/memory/methods/operations.md)

## Rule

- role は `memory/subagent_loadouts.yaml` で指定された method file だけを読む
- role local な気付きはまず candidate に入り、method への昇格は closeout か periodic sweep で行う
