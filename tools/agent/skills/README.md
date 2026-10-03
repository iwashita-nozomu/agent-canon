<!--
@dependency-start
contract tool
responsibility Defines the target area for skill-owned AgentCanon helper tools.
upstream design ../../catalog.yaml structured tool audience and placement catalog
upstream design ../README.md internal tool placement policy
upstream design ../../../agents/skills/agent-orchestration.md point-of-use Skill reading policy
downstream implementation ../../runtime/manifest/tool_catalog.py validates skill-helper placement
downstream implementation ./skill_document_reader.py bounded direct-section reader
@dependency-end
-->

# Skill Helpers

Use this directory for helpers whose primary caller is a skill packet rather
than a repository user. A helper may be listed in `tools/catalog.yaml` with
`audience: skill` and `placement: skill_helper` before its file is physically
moved here.

## Skill document reader

`bootstrap.sh ... tool run --root <registered-project> skill-document-reader -- ...`
is the runtime entrypoint. Branch selection follows
[Owner-First Read Trace](../../../agents/skills/agent-orchestration.md#owner-first-read-trace).

Use `index --path <skill>` to list headings without branch bodies, then
`chunk --path <skill> --heading <selected-heading>` for common constraints or a
currently needed branch. Continue that heading from `next_offset` until
`section_eof=true`. A section ends before the next heading, including a child;
children and nested branches must be selected separately when needed.
`file_eof=false` is normal and does not require opening the remaining branches.
A `chunk` without `--heading` is an explicit raw file slice, not the default
Skill-reading route.

The optional `admit --owner '<skill>#<common-heading>' --owner '<skill>#<active-heading>'`
reports metadata for only the supplied sections. Repeat `--owner` for a needed
canonical section, not every link or descendant. An empty selection is locked;
a nonempty selection with each section EOF is ready. Neither output format
repeats section text. This checks source readability, not that the model actually
read the text or chose sufficient sections; obtain content through `chunk`.

Migration: `--compact`, `compact_path`, `compact_file_eof`, and the full-file
`read_file()` helper were removed. Python callers pass only `owner_sections` to
`admit_implementation_read`; `implementation_read_state` accepts only the
selected section EOF flags. Replace full-file admission with explicit current
common/branch sections rather than a compatibility fallback that eagerly reads
the old compact body.
