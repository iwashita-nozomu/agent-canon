<!--
@dependency-start
contract reference
responsibility Documents the repository structure contract checker.
upstream implementation ../../tools/agent_tools/repo_structure_contract.py compares repo trees with the structure contract
upstream design ../repo-structure-contract.toml defines expected repository structure profiles
upstream design ../SHARED_RUNTIME_SURFACES.md shared root surface policy
downstream implementation ../../tools/catalog.yaml catalogs this checker
@dependency-end
-->

# Repo Structure Contract

`tools/agent_tools/repo_structure_contract.py` compares an observed repository
tree with `documents/repo-structure-contract.toml`.

Use it when a template or derived repository needs to prove that its top-level
layout still matches an AgentCanon-supported profile.

Typical direct check, which runs `tree -a -J` internally:

```bash
python3 tools/agent_tools/repo_structure_contract.py --root .
```

To compare a saved `tree` command result:

```bash
tree -a -J \
  -I '.git|.agent-canon|reports|target|__pycache__|.pytest_cache|.ruff_cache|.venv|node_modules' \
  . > /tmp/repo-tree.json
python3 tools/agent_tools/repo_structure_contract.py --root . --tree-json /tmp/repo-tree.json
```

The contract, not the checker source, owns required paths, optional paths,
ignored generated directories, profile detection, and unexpected top-level
path severity.
