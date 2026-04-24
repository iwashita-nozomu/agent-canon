Dependency Files:

- vendor/agent-canon/AGENTS.md
- vendor/agent-canon/agents/canonical/CODEX_WORKFLOW.md
- vendor/agent-canon/documents/REVIEW_PROCESS.md
- vendor/agent-canon/tools/agent_tools/check_dependency_headers.py
- vendor/agent-canon/tests/agent_tools/test_check_dependency_headers.py

# Dependency Headers

Dependency headers make each text artifact state the source files it depends on before the reader or reviewer enters the body. They are not ownership labels. They are a compact trace from a file to the design, workflow, code, test, or tool surface that must be checked before editing it.

## Required Shape

Every human-authored checkable text file should declare a `Dependency Files:` block near the top. Use repository-relative paths.

Comment-capable code and config files use comments:

```python
# Dependency Files:
# - vendor/agent-canon/documents/dependency-headers.md
# - vendor/agent-canon/tools/agent_tools/check_dependency_headers.py
```

Markdown and other prose files use a plain block:

```markdown
Dependency Files:

- vendor/agent-canon/documents/dependency-headers.md
- vendor/agent-canon/documents/REVIEW_PROCESS.md
```

When a file has real front matter, keep the front matter first and place the dependency block immediately after it. Do not move dependency headers ahead of skill metadata or agent metadata.

## What To List

List the files that make the current file meaningful or safe to edit:

- Runtime code lists its design document, protocol or API files, and direct tests.
- Tests list the implementation under test, testing conventions, and the design document that defines expected behavior.
- Workflow and agent files list the canonical workflow, role inventory, templates, and scripts they call.
- Generated-artifact indexes list the generator or provenance docs, not the generated output internals.
- Docs list the implementation, sibling design docs, references, or lifecycle rules they summarize.

Avoid headers that only say `AGENTS.md` unless the file is truly only a thin runtime entrypoint.

## Exceptions

Do not add dependency headers to formats that cannot carry comments, such as JSON. Record their dependency policy in the nearest human-authored README or design document instead.

Do not add dependency headers directly to generated outputs, external HTML captures, static-analysis output captures, build artifacts, or binary data. Add or update the adjacent README or provenance document instead.

## Symlinked Root Views

Some repository-root paths are symlinks or synced copies of files whose source of truth is under `vendor/agent-canon/`. Edit the vendor source, not the root view. If a workflow or reader packet names a root path, keep that root path available as a view into the vendor source rather than introducing a second policy document.

The dependency-header inventory may report root symlinks as `symlink_surface`; that is informational. After changing a shared source or root view, run `bash tools/sync_agent_canon.sh link-root` when copy surfaces need repair, and run `bash tools/sync_agent_canon.sh check` to confirm the root views still match the shared canon.

## Validation

`tools/agent_tools/check_dependency_headers.py` enforces header presence for supported text formats. It intentionally checks comment-capable suffixless files such as `Makefile` and `Dockerfile`, and intentionally skips commentless formats such as JSON.

Presence is a gate, not a quality proof. Reviewers still need to reject generic or misleading headers during change review.
