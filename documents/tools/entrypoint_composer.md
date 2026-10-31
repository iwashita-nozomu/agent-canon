<!--
@dependency-start
contract reference
responsibility Documents the explicit source-to-consumer root instruction composition route.
upstream design ../design/entrypoint-owner-map.md consumer root composition contract
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/entrypoint_composer.rs deterministic composer
downstream design ../../ROOT_AGENTS.md common consumer base
@dependency-end
-->

# Consumer root instruction composer

The native `compose-consumer-entrypoint` command creates a consumer-owned
regular [AGENTS.md](../../AGENTS.md) from three explicit inputs: AgentCanon
[ROOT_AGENTS.md](../../ROOT_AGENTS.md), consumer-specific text, and the output
path. The source checkout is used only to record its current
commit in the managed comment marker. The output contains the exact input
bytes, fixed separators, and their SHA-256 digests, so a consumer can read it
without an AgentCanon checkout or runtime.

An absent output is created atomically. An existing unmarked file, symlink,
directory, or partial managed file fails without changing it. A valid managed
file may be refreshed from the current exact inputs. Nested [AGENTS.md](../../AGENTS.md) files
are outside this operation, and `AGENT.md` is not a supported alias.

The command is a maintainer workflow helper. Invoke the native CLI with explicit
`--base`, `--specific`, `--output`, and (when the working directory is not the
source checkout) `--source-root` values. The composer reads the named files and
Git commit through fixed argv; it does not load consumer source modules or add a
Python adapter. Do not add a vendor, submodule, symlink, updater, or runtime
projection to the consumer.
