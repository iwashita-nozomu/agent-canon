<!--
@dependency-start
contract design
responsibility Documents the Rust-native algorithm config partition checker.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/check_algorithm_config_partition.rs implements the checker
upstream implementation ../../tools/catalog.yaml registers the native command and CI route
downstream implementation ../../tests/agent_tools/test_check_algorithm_config_partition.py preserves the old behavior oracles through the native CLI
downstream design ./tool-docs.toml registers this tool documentation
@dependency-end
-->

# Algorithm Config Partition

The native `agent-canon check-algorithm-config-partition` command checks that
initialization-only config fields remain in `InitializeConfig`, runtime-only
fields remain in `SolveConfig`, and runtime defaults are visible through config
surfaces.

## Usage

```bash
tools/bin/agent-canon check-algorithm-config-partition [paths...] [options]
```

Without paths, the checker scans Python files below `--root`, which defaults to
the current directory. A supplied file is analyzed directly; a supplied
directory is searched recursively. Directory discovery skips hidden and
excluded paths. The default exclusions are `.git`, `.ruff_cache`,
`__pycache__`, `build`, `reports`, `vendor`, and
`python/jax_util.egg-info`.

Options:

- `--root <path>` sets the repository root.
- `--exclude <pattern>` adds a path, prefix, path-part, or glob exclusion.
  Repeat this option to add patterns.
- `--format text|json` selects the report format. The default is `text`.
- `--fail-on-finding` returns status 1 when partition findings exist.
- `--fail-on-default` returns status 1 when hidden runtime-default errors exist.

## Findings and output

The partition check recognizes config classes derived from
`jax_util.base.algorithm_module_protocol.InitializeConfig` and `SolveConfig`,
including imported aliases and inherited classes. It reports initialization-only
field names or config types in SolveConfig, and runtime field names or config
types in InitializeConfig.

Default findings include callable parameter defaults, mapping `get` and
`setdefault` defaults, `getattr` defaults, empty config constructors,
`or` fallback values, and assigned config-field defaults. Runtime defaults
are errors; config-owned defaults are warnings. Syntax errors become partition
findings with their root-relative path and one-based line.

JSON output contains `summary`, `fields`, `findings`, and
`default_findings`. Text
output prints machine-readable finding markers followed by field, finding,
default, error, and status counts. Findings do not change the default exit
status. `--fail-on-finding` and `--fail-on-default` independently select the
conditions that return status 1; invalid arguments return status 2.
