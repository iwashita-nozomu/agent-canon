<!--
@dependency-start
contract agent-runtime
responsibility Documents legacy eval manifest path compatibility for this repository.
upstream design ../../evidence/README.md evidence directory ownership
upstream design ../../evidence/agent-evals/README.md canonical eval manifest source
downstream implementation ../../tools/agent_tools/eval_manifest_paths.py resolves legacy manifest paths
@dependency-end
-->

# Legacy Eval Manifest Path

`agents/evals/` is a compatibility stub, and the canonical tracked eval manifest
source directory is now [../../evidence/agent-evals/](../../evidence/agent-evals/).
This directory must remain empty except for this stub because the source
contract moved to `evidence/agent-evals/`, and the dependency header above
records the only active downstream resolver.

Do not add TOML manifests or result artifacts here. Tools accept old
`agents/evals/*.toml` manifest paths only to print a migration warning and
resolve them to `evidence/agent-evals/*.toml`.

Legacy `agents/evals/results/` paths remain migration inputs for old accumulated
run artifacts. New accumulated run output belongs in the mounted runtime log
archive documented by `documents/runtime-log-archive.md`.
