<!--
@dependency-start
contract agent-runtime
responsibility Documents legacy eval manifest path compatibility for this repository.
upstream design ../../eval/README.md evidence directory ownership
upstream design ../../eval/definitions/README.md canonical eval manifest source
downstream implementation ../../eval/checkers/eval_manifest_paths.py resolves legacy manifest paths
downstream implementation ../../templates/documents/github/issue/eval-capture.yml captures eval issues.
downstream implementation ../../documents/operations/issue-label-taxonomy.md defines eval labels and routing.
@dependency-end
-->

# Legacy Eval Manifest Path

`agents/evals/` is a compatibility stub, and the canonical tracked eval manifest
source directory is now [../../eval/definitions/](../../eval/definitions/).
This directory must remain empty except for this stub because the source
contract moved to `eval/definitions/`, and the dependency header above
records the only active downstream resolver.

Do not add TOML manifests or result artifacts here. Tools accept old
`agents/evals/*.toml` manifest paths only to print a migration warning and
resolve them to `eval/definitions/*.toml`.

Legacy `agents/evals/results/` paths remain migration inputs for old accumulated
run artifacts. New accumulated run output belongs in the mounted runtime log
archive documented by `documents/runtime/runtime-log-archive.md`.
