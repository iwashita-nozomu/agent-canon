# `extract_docx.py`

`tools/docs/extract_docx.py` decomposes an authorized local `.docx` file into a
reference bundle without requiring LibreOffice, Pandoc, or `python-docx`.
It uses the standard-library ZIP and XML readers.

```bash
python3 tools/docs/extract_docx.py \
  references/発表原稿_岩下_ver2.docx \
  --output-dir references/ieice-2026g-b-9-04-peak-cut-control
```

The output directory must be new or empty. It contains:

- `source/<name>.docx`: the verified private snapshot used for extraction;
- `extracted.md`: searchable paragraph, table, and Office Math text;
- `raw/`: every validated ZIP member, including XML and media;
- `manifest.json`: source hash, member hashes, sizes, and output paths.

The extractor normalizes slash and dot aliases once, assigns each member a
Unicode-normalized case-folded portable identity, and rejects absolute,
traversal, duplicate-identity, file-parent-conflict, and advertised symlink
members before extraction. Missing or non-file `word/document.xml` is also
rejected.

The caller-visible output is a staged transaction. The tool copies the source
once through a stable file descriptor, rejects observable source mutation,
extracts only from that private copy, and reads back every retained source/member
hash plus the manifest. It publishes the completed staging directory only after
all checks pass. An absent destination remains absent on failure; an admitted
pre-existing empty destination remains empty. A non-empty path or final-component
symlink is never used as an output directory.

The source DOCX remains authoritative for layout, figures, and editable equation
structure; `extracted.md` is a search and review projection. The tool is
intentionally limited to local input supplied by the caller. It does not fetch
or bypass access controls for conference PDFs.
