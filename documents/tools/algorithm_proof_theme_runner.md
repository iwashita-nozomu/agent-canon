<!--
@dependency-start
responsibility Documents algorithm_proof_theme_runner.py operator usage.
upstream implementation ../../tools/agent_tools/algorithm_proof_theme_runner.py runs configured proof-theme regeneration.
upstream design ../../documents/design/algorithm-ir-to-lean.md defines the Algorithm IR to Lean orchestration role.
upstream design ../../agents/skills/algorithm-proof-exploration.md defines proof-theme artifact flow.
@dependency-end
-->

# algorithm_proof_theme_runner.py

`algorithm_proof_theme_runner.py` regenerates a configured algorithm-proof
theme from a JSON manifest. It is an orchestration helper: it calls the
existing Algorithm Expansion IR, lemma graph, Algorithm IR to Lean, KKT equation
section, proof-path analysis, and Lake build entrypoints instead of duplicating
their logic.

Run it from an AgentCanon or template repository root:

```bash
python3 tools/agent_tools/algorithm_proof_theme_runner.py \
  --config lean/<topic>/algorithm_theme.json \
  --dry-run
```

Remove `--dry-run` only after the configured roots, output paths, and Lake
package are owned by the proof theme. Use `--root-name <name>` to regenerate one
configured root, and use the `--skip-*` flags when a review requires a bounded
stage such as graph regeneration without rebuilding Lean.

The config owns generated artifact paths relative to its directory. Root entries
must provide `name`, `python_symbol`, and `target_theorem`; optional `profiles`
select lemma graph target profiles. `equation_sections` and
`proof_path_analyses` entries point the runner at existing tool outputs and
proof-status files. Missing or unsupported algorithm-specific shapes should be
handled in the theme's own entrypoint, not by extending this generic runner with
topic-local branches.
