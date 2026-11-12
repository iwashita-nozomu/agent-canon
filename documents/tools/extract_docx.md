# `agent-canon extract-docx`

The native `extract-docx` command decomposes an authorized local `.docx` file
into a reference bundle without requiring LibreOffice, Pandoc, or
`python-docx`.

```bash
tools/bin/agent-canon extract-docx \
  references/発表原稿_岩下_ver2.docx \
  --output-dir references/ieice-2026g-b-9-04-peak-cut-control
```

The output directory must be new or empty. It contains:

- `source/<name>.docx`: the verified private snapshot used for extraction;
- `extracted.md`: searchable paragraph, table, and Office Math text;
- `raw/`: every validated ZIP member, including XML and media;
- `manifest.json`: source hash, member hashes, sizes, and output paths.

The extractor reads ZIP names from their raw bytes and flags: bit 11 selects
UTF-8, otherwise CP437 is used, followed by the same NUL truncation as
`zipfile.ZipInfo`. It normalizes slash and dot aliases once, assigns each
member a Unicode 15 NFC and case-folded portable identity, and rejects
absolute, traversal, duplicate-identity, file-parent-conflict, and advertised
symlink members before extraction. Stored, Deflate, BZIP2, and LZMA members are
supported. Missing or non-file `word/document.xml` is also rejected.

The main Word XML is parsed by the pinned, safe Expat 2.9 port. Its behavior is
qualified against the frozen 20-case ElementTree corpus for XML acceptance,
namespaces, default attributes, internal entities, and depth cases; this is not
a claim of equivalence for every XML input. Internal entities and default
attributes are retained; external entity references are refused without
reading external resources. Paragraphs, tables, simple breaks, field
instructions, and Office Math text keep their existing Markdown projection.
Raw XML remains in the bundle as the authoritative source.

The command reads the caller-selected source through a file capability and
writes through a capability opened for the canonical output parent. It copies
the source once through a stable file descriptor, rejects observable source
mutation, extracts only from that private copy, and reads back every retained
source/member hash plus the manifest. It publishes the completed private
staging directory only after all checks pass. An absent destination remains
absent on failure; an admitted pre-existing empty destination remains empty. A
non-empty path or final-component symlink is never used as an output directory.

The source DOCX remains authoritative for layout, figures, and editable equation
structure; `extracted.md` is a search and review projection. The tool is
intentionally limited to local input supplied by the caller. It does not fetch
or bypass access controls for conference PDFs.
