<!--
@dependency-start
contract reference
responsibility Documents the repository structure contract checker.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/repo_structure_contract.rs compares repo trees with the structure contract
upstream design ../structure/repo-structure-contract.toml defines expected repository structure profiles
downstream implementation ../../tools/catalog.yaml catalogs this checker
@dependency-end
-->

# Repo Structure Contract

`tools/runtime/dispatch/agent-canon/src/repo_structure_contract.rs` compares an observed repository
tree with `documents/structure/repo-structure-contract.toml`.

Use it when a template or derived repository needs to prove that its top-level
layout still matches an AgentCanon-supported profile.

Typical direct check, which runs `tree -a -J` internally:

```bash
agent-canon repo-structure-contract --root .
```

To compare a saved `tree` command result:

```bash
tree -a -J \
  -I '.git|.agent-canon|reports|target|__pycache__|.pytest_cache|.ruff_cache|.venv|node_modules' \
  . > /tmp/repo-tree.json
agent-canon repo-structure-contract --root . --tree-json /tmp/repo-tree.json
```

The contract, not the checker source, owns required paths, optional paths,
ignored generated directories, profile detection, and unexpected top-level
path severity.
