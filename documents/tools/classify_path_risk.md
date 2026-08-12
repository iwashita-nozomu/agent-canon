<!--
@dependency-start
contract reference
responsibility Documents path-risk classifier usage.
upstream implementation ../../tools/agent_tools/classify_path_risk.py classifies changed paths into runtime profiles.
upstream design ../runtime/runtime-profiles-and-check-matrix.md defines profile-based validation routing.
downstream implementation ../../tests/agent_tools/test_classify_path_risk.py tests representative profiles.
@dependency-end
-->

# classify_path_risk.py

Use this tool to turn a changed-path list into an active runtime profile and
targeted validation route.

```bash
git diff --name-only origin/main...HEAD > reports/changed-paths.txt
python3 tools/agent_tools/classify_path_risk.py \
  --paths-file reports/changed-paths.txt \
  --format text
```

The classifier is a direct CLI/test-owned surface. It does not require a
separate manual workflow wrapper.
