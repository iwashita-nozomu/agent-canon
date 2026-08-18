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

- `source/<name>.docx`: a copy of the original source;
- `extracted.md`: searchable paragraph, table, and Office Math text;
- `raw/`: every validated ZIP member, including XML and media;
- `manifest.json`: source hash, member hashes, sizes, and output paths.

The extractor rejects absolute or traversal ZIP paths, duplicate normalized
members, advertised symlinks, missing `word/document.xml`, and non-empty output
directories. The source DOCX remains authoritative for layout, figures, and
editable equation structure; `extracted.md` is a search and review projection.

The tool is intentionally limited to local input supplied by the caller. It
does not fetch or bypass access controls for conference PDFs.
