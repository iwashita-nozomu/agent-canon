<!--
@dependency-start
contract data
responsibility Documents evidence/ for this repository.
upstream design ../README.md shared canon overview
upstream design ../responsibility-scope.toml evidence responsibility scope map
downstream design agent-evals/README.md eval manifest evidence contract
@dependency-end
-->

# Evidence

This directory stores source-controlled evidence contracts that are not runtime
entrypoints themselves, and it must stay separate from runtime entrypoints
because the source-controlled evidence contract is reviewable repository state
while generated run output is append-only runtime evidence.

- [agent-evals/README.md](agent-evals/README.md)
  - deterministic eval manifests for skills, workflows, routing, local LLM
    responsibility analysis, report quality, and run-bundle behavior checks.

Runtime result accumulation does not live here. Append-only run output belongs
in the mounted runtime log archive documented by
`documents/runtime-log-archive.md`; legacy `agents/evals/results/` paths are
only migration inputs.
