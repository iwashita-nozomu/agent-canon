<!--
@dependency-start
contract design
responsibility Documents the jax_util algorithm module contract checked by AgentCanon tools.
upstream design ../../algorithm-implementation-boundary.md algorithm boundary policy
upstream design ../../coding-conventions-python.md Python implementation policy
downstream implementation ../../../tools/agent_tools/check_algorithm_config_partition.py checks config ownership
downstream implementation ../../../rust/agent-canon/src/python_algorithm_contract.rs checks algorithm module AST contracts
downstream implementation ../../../tools/catalog.yaml records the checker documentation surface
@dependency-end
-->

# JAX Util Algorithm Module Contract

Algorithm modules that opt into `algorithm_module_protocol` expose a standard
public surface: `InitializeConfig`, `SolveConfig`, `Problem`, `State`, `Answer`,
`Info`, `Algorithm`, and `initialize`.

`InitializeConfig` owns setup-time inputs such as run logging, output paths, and
other initialization sinks. `SolveConfig` owns runtime numerical controls such
as tolerances, iteration limits, and stopping configuration. A parent algorithm
that wraps a child algorithm must surface the child ownership explicitly through
nested config, info, and algorithm fields instead of hiding those dependencies
behind ad hoc module state or alternate route defaults.

The Rust `python-algorithm-contract-check` tool is the stricter checker for this
contract. It analyzes Python AST JSON to verify the public surface, callable
`Algorithm`, nested ownership, and concrete `Info` schema.
