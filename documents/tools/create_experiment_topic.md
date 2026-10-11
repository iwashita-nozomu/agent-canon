# create-experiment-topic

`create-experiment-topic` copies one canonical experiment package into a registered
parent and adds its entry to `experiments/registry.toml` in the same operation.
The tool runs in the AgentCanon tool container, reads the selected package from
the source checkout, and writes only through the active explicit target.

Register the parent with the existing `explicit-target-write` capability and its
exact allowed paths before invoking the tool:

```bash
bootstrap.sh --control-parent-root <control-root> tool run --root <parent-root> \
  create-experiment-topic -- <topic> --template-profile cpp \
  --cmake-profile <root-aggregate|consumer-local>
```

Omit the profile flags to create the existing Python scaffold.

The direct source-checkout invocation for the existing Python scaffold is:

```text
python3 tools/experiments/lifecycle/create_experiment_topic.py <topic>
```

For C++ topics, use `--template-profile cpp` and set `--cmake-profile` to the
consumer's existing `consumer-local` or `root-aggregate` choice.

`consumer-local` materializes a topic-local `CMakeLists.txt`. `root-aggregate`
materializes a `cmake-registration.cmake` request for the project-owned root
manifest. The caller supplies this selection; the tool does not infer a profile
from repository paths. Both C++ profile variants contain a native target, a thin
Python launcher, a raw-output renderer, and `report/` and `result/` roots. The fixed one-case C++
package does not contain `cases.py`.

Add `--multi-case` only when this topic has actual case inputs. That selection
materializes the existing `CaseSpec` input shape and updates the registry command
to enumerate the non-empty `cases` list in JSON-compatible YAML. The launcher
passes each case identity and config path to the same C++ executable; it adds no Python
calculation worker or sample case.

Before invoking the tool, register the parent root with the existing
`explicit-target-write` capability and limit its allowed paths to the selected
topic directory and `experiments/registry.toml`. The tool resolves its target root
from the runtime-provided `AGENT_CANON_OUTPUT_ROOT`; a caller may pass
`--repo-root` for a direct source-checkout invocation.

Existing topic paths and registry identities fail before publication by default.
The existing `--force` option remains an explicit authorization to replace an
unregistered topic directory; it does not bypass a duplicate registry identity.
`--dry-run` prints the selected file inventory and identifies an existing topic
that `--force` would replace. C++ starter topics reject a non-`draft` initial status.
For either package, topic files and the serialized registry are staged before
publication, and a publication failure restores the prior topic and leaves the
registry unchanged.

The source-free `experiment-scaffold` template export contains both package
templates. A generated parent topic has no dependency on the AgentCanon checkout,
runtime, or network. The C++ starter target exits with an error until its native
experiment is implemented; its registry status stays `draft`.
