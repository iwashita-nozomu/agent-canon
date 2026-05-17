# Local LLM Responsibility Analysis

<!--
@dependency-start
responsibility Documents the local LLM single-file responsibility analysis boundary.
upstream design responsibility-scope-management.md responsibility scope policy
upstream design rust-agent-tool-migration.md compiled tool installation boundary
upstream design ../CONTAINER_OPERATIONS.md devcontainer and Dockerfile ownership boundary
downstream environment ../.devcontainer/post-create.sh installs llama.cpp under AGENT_CANON_TOOLS_HOME
downstream implementation ../tools/agent_tools/file_responsibility_llm.py runs single-file advisory analysis
downstream implementation ../tests/agent_tools/test_file_responsibility_llm.py tests prompt and scope limits
@dependency-end
-->

Local LLM responsibility analysis is advisory and single-file only.

The deterministic sources remain primary:

- dependency headers
- top-level `responsibility-scope.toml`
- `tools/catalog.yaml`
- issue `edit_scope`
- dependency review output

The local LLM may suggest whether one file's responsibility text, ownership
class, and protecting-tool relationship look inconsistent. It must not decide
repo-wide ownership, dependency closure, CI pass/fail, or PR readiness.

## Default Runtime

The shared devcontainer installs llama.cpp into:

```text
${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}/bin/llama-cli
${AGENT_CANON_TOOLS_HOME:-$HOME/.tools}/bin/llama-server
```

The initial model is:

```text
Qwen/Qwen3-0.6B-GGUF:Q8_0
```

This model is small enough for local responsibility review and is published by
Qwen as Apache-2.0 GGUF. llama.cpp is compiled in post-create and kept outside
the Dockerfile. The model itself is fetched lazily by llama.cpp cache behavior
on first use; it is not committed to the repository.

## Command

```bash
python3 tools/agent_tools/file_responsibility_llm.py path/to/file.py
```

Dry prompt inspection:

```bash
python3 tools/agent_tools/file_responsibility_llm.py \
  --print-prompt \
  path/to/file.py
```

The command rejects directories and multiple files. It emits
`FILE_RESP_LLM_SCOPE=single_file` so downstream logs can tell this is not a
repo-wide analyzer.

## Allowed Use

- Review one changed file's responsibility statement.
- Ask for possible owner-class mismatch in that file.
- Ask for missing protecting-tool or issue evidence hints for that file.
- Feed the suggestion into a human or deterministic checker follow-up.

## Prohibited Use

- Do not run this as a required CI gate.
- Do not use it to replace dependency review.
- Do not give it multiple files as one prompt.
- Do not let it create issue files or edit source directly.
- Do not treat model output as authoritative evidence.

If future work needs multi-file or repo-wide LLM analysis, create a separate
issue, manifest scope, eval, and tool contract first.
