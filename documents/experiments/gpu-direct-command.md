# Provider-independent GPU direct command admission

<!--
@dependency-start
contract design
responsibility Defines the provider-independent GPU admission state machine, direct-command adapter, exact environment, lifecycle evidence, and direct-versus-managed selection boundary.
upstream design ./gpu-admission-r5-source-packet.md canonical GPU discovery, occupancy, reservation, and plan ownership
upstream design ./gpu-admission-r5-nvidia-visibility.md strict NVIDIA topology and full UUID evidence boundary
downstream implementation ../../tools/experiments/execution_resource_plan.py canonical NVIDIA evidence, BUSY/UNKNOWN/FREE classification, UUID lock, and admission receipt owners
downstream implementation ../../tools/experiments/gpu_command_admission.py direct admission composition, immutable plan, exact environment, execution lifecycle, and release owner
downstream implementation ../../tools/experiments/run_gpu_command.py shell-free direct-command CLI adapter
downstream implementation ../../tools/experiments/run_managed_experiment.py optional managed provider adapter
downstream contract ../../tests/tools/test_run_gpu_command.py fake NVIDIA, race, environment, lifecycle, and provider-independence acceptance tests
downstream design ../../agents/skills/gpu-execution.md route selection and operator workflow
@dependency-end
-->

## Purpose

GPU admission is a resource-safety mechanism, not an ExperimentRunner feature. The canonical
NVIDIA evidence, occupancy closure, and UUID lock owners remain in
`execution_resource_plan.py`. A provider-independent adapter composes those owners and can run
an arbitrary argv without a managed provider, registry, topic, cases, source snapshot, artifact
schema, or completion-coverage handshake.

The managed route remains available when those experiment lifecycle contracts are required. It
is not a prerequisite for direct pytest, benchmark, diagnosis, or one-off GPU commands.

## Route selection

Use the direct route by default when the requested unit is an argv and success is defined by its
exit status plus stdout/stderr:

```text
python3 tools/experiments/run_gpu_command.py \
  --gpu-count 1 \
  --min-free-memory <bytes> \
  -- <argv...>
```

Use `run_managed_experiment.py` only when the request needs managed topic/registry identity,
case expansion, source snapshotting, provider-owned artifact schemas, lifecycle result schemas,
or completion coverage. Provider discovery and provider contract validation are therefore
conditional on managed mode only.

## Admission state machine

For candidate set $C$, requested cardinality $k$, and minimum free memory $m$, direct
execution follows this one-way state machine:

```text
strict nvidia-smi -L
  -> full physical/MIG executable leaves
  -> fresh structured observation S0
  -> BUSY/UNKNOWN/FREE closure
  -> memory-qualified candidate set E
  -> full-UUID flock transaction
  -> distinct post-lock observation S_lock
  -> race and memory validation
  -> immutable command/resource plan
  -> exact child environment
  -> shell=False child launch
  -> transitive descendant quiescence
  -> lock release
```

Let $L(T)$ be the executable leaves of strict topology $T$. Admission requires

$$

C \subseteq L(T_0) \cap L(T_{lock})

$$

and defines

$$

E = \{u \in C \mid state_0(u)=FREE \land free_0(u) \ge m\}.

$$

The reservation must produce a set $R \subseteq E$ with $|R|=k$, one unique full UUID lock
identity and reservation identity per selected unit. Immediately before launch, every
$u \in R$ must still satisfy

$$

state_{lock}(u)=FREE \land free_{lock}(u) \ge m.

$$

Any BUSY, UNKNOWN, missing, topology-changed, visibility-changed, memory-insufficient, lock-busy,
or stale observation is a typed preflight failure. UNKNOWN is never treated as FREE.

## Identity and topology rules

- Only complete opaque `GPU-...` and `MIG-...` identities observed in strict NVIDIA topology are
  accepted. Integer indices and UUID prefixes are not identities.
- A physical GPU with observed MIG children is not an executable leaf. Its MIG children are the
  executable leaves. A physical GPU without MIG children is an executable leaf.
- Candidate topology is compared with both the initial and post-lock structured observations.
  A MIG enable/disable or join change aborts before child launch.
- Existing caller visibility can restrict candidates but cannot be widened. Conflicting CUDA and
  NVIDIA visibility sets abort.
- The canonical shared runtime and UUID lock namespace remain
  `/var/lib/agent-canon/runtime` and its canonical lock root.

## Immutable plan and exact environment

The command/resource plan is written and fsynced before selected child visibility is
materialized. It binds argv, cwd, candidate inventory fingerprint and MIG joins, initial and
post-lock observation events, BUSY/UNKNOWN/FREE states, selected memory, every reservation ID,
every lock device/inode identity, and the admission fingerprint.

The child environment is derived only from that frozen plan. For selected ordered UUID list
`U`, both variables are exactly `U`:

```text
CUDA_VISIBLE_DEVICES=<full UUID list>
NVIDIA_VISIBLE_DEVICES=<same full UUID list>
JAX_PLATFORMS=cuda
XLA_PYTHON_CLIENT_PREALLOCATE=false
XLA_PYTHON_CLIENT_ALLOCATOR=platform
XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR=false
```

`JAX_PLATFORMS=cuda` makes a missing JAX GPU backend fail instead of silently accepting a CPU
backend. The adapter never converts UUIDs to integer indices. Sensitive inherited environment
values are cryptographically bound in fingerprints without being written in plaintext.

## Child lifecycle and lock retention

The direct adapter invokes an argv array with `shell=False` and `start_new_session=True`. On
Linux it becomes a child subreaper before launch, tracks descendants by PID plus process start
identity, ancestry, process group, session, and post-launch adoption, and excludes children that
already belonged to the runner before launch.

No signal or kill is sent. After `Popen` succeeds, diagnostic, procfs, fsync, or restoration
errors are retained while observation continues. The UUID lock is released only after the root
process has terminated and every AgentCanon-started descendant is proven quiescent. A close
operation is attempted once; ambiguous or incomplete release is a typed failure and is not
retried as a second descriptor-close attempt.

## Exit and evidence contract

A successfully launched child retains its raw return code. The CLI maps a signal return to the
conventional `128 + signal` process exit domain and otherwise returns the child exit code.
Internal admission/adapter failures return `125`.

The output directory is append-once and contains:

| File | Contract |
| --- | --- |
| `gpu_command_plan.json` | Immutable pre-launch command/resource plan |
| `gpu_command_environment.json` | Exact selected visibility and JAX policy, without secret values |
| `stdout.log` | Exact child stdout bytes |
| `stderr.log` | Exact child stderr bytes |
| `gpu_command_result.json` | Exit, timestamps, hashes, lifecycle, visibility, descendant, and release evidence |
| `gpu_command_failure.json` | Typed failure, launch/quiescence state, and release state |

Direct-mode evidence explicitly records `managed_provider_required=false`.

## Validation

Provider-independent fake tests:

```text
python3 -m pytest tests/tools/test_run_gpu_command.py -q
```

A real GPU JAX smoke must import JAX only inside the admitted child:

```text
python3 tools/experiments/run_gpu_command.py \
  --gpu-count 1 \
  --min-free-memory 2147483648 \
  -- python3 -c \
  'import jax; assert jax.default_backend() == "gpu"; print(jax.devices())'
```

A GPU-heavy test or benchmark uses the same adapter, for example:

```text
python3 tools/experiments/run_gpu_command.py \
  --gpu-count 1 \
  --min-free-memory 8589934592 \
  -- python3 -m pytest tests/gpu/test_heavy_backend.py -q
```

Acceptance requires both fake NVIDIA coverage and real-device evidence for claims that depend on
CUDA/JAX runtime behavior. Static tests, CPU-only tests, and a machine without `nvidia-smi` do not
constitute real GPU verification; closeout must record `gpu_validation_blocker=<reason>` for the
unverified claims.
