<!--
@dependency-start
contract reference
responsibility Provides a ready-to-use pull request description for adding the split Codex CLI guide.
upstream design source/codex_cli_guide_config_deepdive.full.md preserved generated guide body with runtime hook flag normalization.
@dependency-end
-->

# Add split OpenAI Codex CLI guide

## Summary

- Adds `codex-cli-guide/` at the repository root.
- Preserves the complete single-file Markdown source under `codex-cli-guide/source/` with current hook flag spelling.
- Splits the guide into chapter-sized files under `codex-cli-guide/sections/`.
- Adds `codex-cli-guide/MANIFEST.md` with source ranges and hashes.
- Adds `codex-cli-guide/tools/validate_split.py` to verify that the split sections reconstruct the full source without omissions.

## Validation

```bash
python3 codex-cli-guide/tools/validate_split.py
```

Expected result:

```text
split validation passed
```

## Notes

The generated dependency manifests at the beginning of Markdown files are repository metadata. The validation script compares only the content after `<!-- split-content-start -->`.
