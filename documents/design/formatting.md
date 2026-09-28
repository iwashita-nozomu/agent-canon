# Formatter settings

<!--
@dependency-start
contract reference
responsibility Owns AgentCanon's native formatter settings and their direct use.
upstream design ../../ROOT_AGENTS.md editing and validation boundary
downstream design ../../AGENTS.md source-specific reader map
downstream implementation ../../.editorconfig editor whitespace defaults
downstream implementation ../../ruff.toml Python formatting policy
downstream implementation ../../.clang-format C and C++ formatting policy
downstream implementation ../../rustfmt.toml Rust formatting policy
downstream implementation ../../.vscode/settings.json editor formatting adapter
@dependency-end
-->

## Ownership and purpose

AgentCanon keeps formatter settings as tracked, tool-native configuration at
its root. This page owns their location and direct use; the mandatory execution
boundary is [Validation Routing](../../ROOT_AGENTS.md#validation-routing).
Keep that boundary in the common root rather than copying a second formatter
checklist into every Skill.

| Surface | Configuration owner | Formatting operation |
| --- | --- | --- |
| Editor whitespace | [`.editorconfig`](../../.editorconfig) | EditorConfig-aware editor; not a substitute for a language formatter |
| Python | [`ruff.toml`](../../ruff.toml) | `ruff format <edited Python paths...>` |
| C, C++, CUDA | [`.clang-format`](../../.clang-format) | `clang-format -i --style=file <edited paths...>` |
| Rust | [`rustfmt.toml`](../../rustfmt.toml) | Owning crate's existing formatting command, or `rustfmt` on edited files using its declared edition |
| Markdown | [Existing docs tool](../tools/agent-canon.md) | `tools/bin/agent-canon docs format <edited Markdown paths...>` |
| VS Code integration | [Settings](../../.vscode/settings.json), [recommendations](../../.vscode/extensions.json) | Format on save for Python, C/C++/CUDA and Rust using the selected native formatter |

Run commands from the repository's existing working context and name the edited
files. Rust's language edition comes from the owning Cargo manifest and existing
command, not a new runtime selector or a value copied into the shared style.
A crate-wide command is appropriate only within the repository's accepted scope;
do not expand a bounded edit to a whole-workspace reformat.

Markdown stays with its existing formatter. This change does not introduce an
unused markdownlint or Prettier configuration, change the Markdown mechanism,
or make Ruff's Python formatting a replacement for Markdown formatting. Other
file types retain their existing owner-selected formatter and settings.

## Engineering rationale

The requirement is to keep the edited, validated, and submitted content aligned.
Native configuration gives the editor and CLI the same formatting inputs without
an AgentCanon-specific schema, dispatcher, wrapper, or configuration sync service.
Ruff and rustfmt retain their ordinary style choices; clang-format uses its LLVM
baseline. Only basic whitespace and style choices are written down, not a dump of
every tool default or an exact toolchain version.

EditorConfig covers whitespace rather than parsing source syntax. Its Markdown
exception preserves meaningful hard breaks. Format on save reduces omission for
editor changes, but CLI edits, generated files and conflict resolutions may not
produce an editor save event. It therefore supplements, never replaces, actual
formatter execution on the final edited content. A clean check result alone
also does not establish that the write operation was performed.

Put the actual command, target files, result and any execution limitation in the
existing Issue/PR validation record as required by the shared boundary. No new
receipt format, pre-commit framework, environment probe, or broad CI gate is
needed. The existing Ruff lint overlays remain independent; this configuration
does not add lint rules or suppress findings.

## Consumer adoption boundary

These files are AgentCanon's maintained baseline, not permission to overwrite a
consumer repository's formatting policy. When adoption is explicitly requested,
use the applicable native settings in that consumer's own tracked configuration
and preserve deliberate project overrides. Ordinary consumer work uses its
already selected settings. No live AgentCanon dependency, symlink, automatic
copy/sync, personal-dotfile requirement, or unrelated consumer migration is added.

## Native references

- [Ruff formatter configuration](https://docs.astral.sh/ruff/formatter/)
- [Clang-format style configuration](https://clang.llvm.org/docs/ClangFormatStyleOptions.html)
- [Rustfmt configuration](https://github.com/rust-lang/rustfmt#configuring-rustfmt)
- [EditorConfig properties](https://editorconfig.org/#supported-properties)
- [Ruff editor setup](https://docs.astral.sh/ruff/editors/setup/)
