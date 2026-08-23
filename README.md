# agent-canon

<!--
@dependency-start
contract reference
responsibility Documents the standalone AgentCanon source repository and its shared tool runtime entrypoint.
upstream design PHILOSOPHY.md design-time philosophy
upstream design AGENTS.md source-tree instruction entrypoint
upstream design documents/runtime/bootstrap-runtime.md bootstrap and tool-runtime user contract
downstream design CONTAINER_OPERATIONS.md container operation policy
@dependency-end
-->

この repository は AgentCanon の正本です。policy、workflow、skill、role、validation
contract、Python/Rust tool の source を所有します。project の domain code、project の
build/test、GitHub Issue/PR、GPU 実行は所有しません。AgentCanon は parent repository に
vendor するものではなく、必要な作業時に明示的な development clone を作成して扱います。

## First read path

人が読む入口は次の順です。

1. `README.md`
2. `PHILOSOPHY.md`
3. `documents/README.md`
4. `agents/README.md`
5. `agents/workflows/README.md`

Codex の source-tree instruction entrypoint は `AGENTS.md` です。skill、workflow、
subagent の canonical owner は `agents/`、設計と runtime contract の owner は
`documents/`、実行可能な tool と checker の owner は `tools/` と `rust/` です。

## Standalone runtime

通常の利用では、source checkout の中で依存を直接実行せず、top-level
[`bootstrap.sh`](bootstrap.sh) から共有 tool runtime を起動します。control root と
runtime root は必須です。

```bash
ROOT=<authorized-parent-root>
RUNTIME="$ROOT/workspace/agent-canon-runtime/<installation>"
BOOTSTRAP=./bootstrap.sh
COMMON=(--control-parent-root "$ROOT" --runtime-root "$RUNTIME")

"$BOOTSTRAP" "${COMMON[@]}" install
"$BOOTSTRAP" "${COMMON[@]}" update
"$BOOTSTRAP" "${COMMON[@]}" start
"$BOOTSTRAP" "${COMMON[@]}" target add --root <project-root> --mode read-only
"$BOOTSTRAP" "${COMMON[@]}" status
"$BOOTSTRAP" "${COMMON[@]}" codex prepare
"$BOOTSTRAP" "${COMMON[@]}" codex launch --project-root <project-root>
"$BOOTSTRAP" "${COMMON[@]}" tool run --root <project-root> <verified-catalog-id> -- <args...>
"$BOOTSTRAP" "${COMMON[@]}" eval collect --root <project-root> --run-id <run-id>
"$BOOTSTRAP" "${COMMON[@]}" eval sync --run-id <run-id>
"$BOOTSTRAP" "${COMMON[@]}" stop
"$BOOTSTRAP" "${COMMON[@]}" gc
"$BOOTSTRAP" "${COMMON[@]}" uninstall
```

The complete user journey, target modes, generation rollback, limits, failure
codes, cleanup, and archive handoff are in
[Standalone Bootstrap And Shared Tool Runtime](documents/runtime/bootstrap-runtime.md).

There is one shared image and at most one resident AgentCanon tool container per
authorized control root. The image contains Python, Rust, and language-server
tools only. The project owns its own Docker/test runner; AgentCanon never mounts
project test directories into the tool runtime and does not create a project-
specific image, container, virtualenv, Cargo toolchain, or volume.

Bootstrap treats the Docker CLI/daemon as an available host capability and
reports Docker's exit code and stderr when a command fails. Container process
identity, UID/GID mapping, and root/rootless policy belong to the host and
caller environment; AgentCanon does not create a user, pass `--user`, or
validate those settings. Host state, credentials, Git metadata, and global
Codex configuration are not mounted into the container.

## Source and artifact boundary

The AgentCanon source tree is read-only for analysis. A write-capable operation
must name an exact target root, allowed paths, purpose, and receipt. Runtime
logs, evals, dashboards, summaries, reports, temporary files, caches, Cargo
targets, and SQLite state are external runtime artifacts and must not appear as
implicit writes beneath the source checkout. This includes `__pycache__` and
tool-generated report directories.

`codex prepare` installs verified skills, agents, hooks, and configuration as
manifest-managed links under the selected runtime root's isolated `codex-home`.
It never modifies global `CODEX_HOME`; `codex launch` sets `CODEX_HOME` only in
the child process. Conflicting pre-existing paths fail closed, and uninstall
removes only links owned by this installation.

## Evaluation and archive

`eval collect` writes a versioned collection and receipt to the external runtime
spool. `eval sync` publishes through the typed host Git adapter to the separate
[`iwashita-nozomu/agent-canon-log`](https://github.com/iwashita-nozomu/agent-canon-log)
repository. The log repository owns branch and retention policy; AgentCanon owns
the local spool and publication receipt. Archive or network failure preserves
the spool for retry and never dirties this source tree. Publication is complete
only after remote ref/tree/blob readback. See
[Runtime Log Archive](documents/runtime/runtime-log-archive.md).

## Compatibility and tool routing

Existing Rust first-class commands retain their public shape, including:

```bash
agent-canon docs check ...
agent-canon semantic-index ...
agent-canon structured-analysis ...
```

Python tools are not exposed as a new collection of flat global executables.
Only catalog entries with schema-v2 parity evidence can use the bootstrap-owned route:

```bash
agent-canon tool run <catalog-id> -- <args...>  # AGENT_CANON_TARGET_ROOT is explicit
```

Parity covers argv, cwd, stdin/stdout/stderr, exit and signal behavior, and
written paths. Unverified internal tools are not exposed through the public
bootstrap command family. The dispatcher rejects shell command strings and does
not infer public status for every internal Python file. See [tools/README.md](tools/README.md)
and [the tool catalog](tools/catalog.yaml).

## Repository layout

| Directory | Responsibility |
| --- | --- |
| `agents/` | Skills, workflows, roles, communication, and task contracts |
| `documents/` | Design, runtime, tool, and responsibility contracts |
| `tools/` | Host adapters, checkers, Python tools, and CLI wrappers |
| `rust/` | Compiled AgentCanon tools |
| `tests/` | AgentCanon mechanism tests |
| `bootstrap/` | Shared image and lifecycle manifest used by `bootstrap.sh` |

The runtime root is intentionally separate:

```text
<authorized-parent-root>/workspace/agent-canon-runtime/<installation>/
  current-generation  rollback-generation  lifecycle.lock  mounts.toml
  codex-home/  tasks/  spool/  archive/  container-runtime/
  cache/       # bounded external cache, never source-local
```

For an AgentCanon edit from Template or another parent repository, use that
parent's ignored `workspace/agent-canondevelop/<qualified-task>/agent-canon`
clone. Do not add a submodule, vendor checkout, source symlink, or `notes/` /
`tests/` projection to the parent. The parent owns project tests and the user
workflow; AgentCanon owns only the shared runtime source.

## Operations and validation

Read [Container Operations](CONTAINER_OPERATIONS.md) before changing the image,
container limits, or host adapter. Read
[Runtime Profiles And Check Matrix](documents/runtime/runtime-profiles-and-check-matrix.md)
to select checks by changed responsibility. Read
[AgentCanon Update](agents/skills/agent-canon-update.md) for source branch,
review, publication, and main readback.

Issue ownership is explicit: [#841](https://github.com/iwashita-nozomu/agent-canon/issues/841)
owns local bootstrap, shared runtime, source side-effect, and eval lifecycle;
[#821](https://github.com/iwashita-nozomu/agent-canon/issues/821) owns prebuilt
artifact build/distribution only. Do not use #821 as the lifecycle issue.

The minimum focused checks for documentation changes are:

```bash
python3 tools/docs/check_bootstrap_docs.py --root .
bash tools/agent_tools/check_dependency_header_format.sh --root . --changed
git diff --check
```

Use the canonical AgentCanon checks selected by the runtime profile for code,
container, bootstrap, or archive changes.

## License

AgentCanon is licensed under Apache License 2.0. See [LICENSE](LICENSE) and
[the licensing policy](documents/agent-canon/agent-canon-licensing-policy.md).
`install` and `update` own only the exact `<control-parent-root>/.agents` link to
the tracked source adapters. No home link is inferred; selecting `$HOME` as the
explicit control root makes `$HOME/.agents` the owned path. Global `.codex`
remains outside AgentCanon ownership.
