# @dependency-start
# contract environment
# responsibility Defines the one shared AgentCanon Python, Rust, and LSP tool image.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared tool runtime boundary
# upstream implementation ../../tools/analysis/dependencies/dependency_plan.py typed image dependency installer
# downstream implementation ./entrypoint.sh resident runtime and health probe
# @dependency-end

ARG TARGETPLATFORM
FROM node:22.14.0-bullseye-slim@sha256:73a9dfbb6c761aebdf4666cce2627635a30d1d4c20f67ff642d01b8f09e709a3 AS node-provider

# Runtime base owns the retained Ubuntu closure and the one exact clangd
# installation.  Both builder and final runtime inherit this clean state.
FROM ubuntu:22.04@sha256:2edbbc5dc405e9612ba3584ce95480277e3eb374407b5505fe26f17df77c7dbc AS runtime-base
ARG TARGETOS
ARG TARGETARCH
ARG TARGETVARIANT
ENV PYTHONDONTWRITEBYTECODE=1

LABEL org.opencontainers.image.title="AgentCanon shared tool runtime" \
      io.agent-canon.runtime="shared-v1" \
      io.agent-canon.container.max-instances="1" \
      io.agent-canon.run.read-only-rootfs="true" \
      io.agent-canon.run.network="none" \
      io.agent-canon.run.cap-drop="ALL" \
      io.agent-canon.run.no-new-privileges="true" \
      io.agent-canon.run.cpus="2" \
      io.agent-canon.run.memory="4g" \
      io.agent-canon.run.pids-limit="512" \
      io.agent-canon.run.tmpfs="/tmp"

RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates \
      git \
      jq=1.6-2.1ubuntu3.2 \
      tree=2.0.2-1 \
      python3 \
      python3-packaging \
      python3-tomli \
      python3-yaml; \
    install -d -m 0755 /workspace /var/lib/agent-canon/runtime /usr/local/share/agent-canon; \
    chmod 1777 /tmp; \
    printf 'agent-canon-tool-container/v1\n' > /usr/local/share/agent-canon/.agent-canon-tool-container; \
    chmod 0444 /usr/local/share/agent-canon/.agent-canon-tool-container; \
    test "$(stat -c '%a:%u:%g' /usr/local/share/agent-canon/.agent-canon-tool-container)" = '444:0:0'; \
    rm -rf /var/lib/apt/lists/*

# clangd is verified and cleaned in this single base layer.  curl, gnupg, the
# repository key/source, and apt indexes do not survive into either descendant.
RUN set -eux; \
    case "$TARGETOS/$TARGETARCH" in \
      linux/amd64) llvm_arch=amd64; clangd_sha=05ba173847cca9a3362155b9b7b59b3a7968195cde17dfa5e26bd777d9558660 ;; \
      linux/arm64) llvm_arch=arm64; clangd_sha=c98c785017ed4c0d1e45ee42d78fabe4eda569c28e67d5811da49cec8d528599 ;; \
      *) echo "unsupported_target_arch=$TARGETOS/$TARGETARCH" >&2; exit 2 ;; \
    esac; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl gnupg; \
    temporary="$(mktemp -d)"; \
    curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --output "$temporary/llvm-snapshot.gpg.key" https://apt.llvm.org/llvm-snapshot.gpg.key; \
    test "$(gpg --show-keys --with-colons "$temporary/llvm-snapshot.gpg.key" | awk -F: '$1 == "fpr" {print toupper($10); exit}')" = '6084F3CF814B57C1CF12EFD515CF4D18AF4F7421'; \
    gpg --dearmor --output "$temporary/llvm.gpg" "$temporary/llvm-snapshot.gpg.key"; \
    install -D -m 0644 "$temporary/llvm.gpg" /etc/apt/keyrings/clangd-language-server.gpg; \
    printf 'deb [arch=%s signed-by=/etc/apt/keyrings/clangd-language-server.gpg] https://apt.llvm.org/jammy/ llvm-toolchain-jammy-18 main\n' "$llvm_arch" > /etc/apt/sources.list.d/clangd-language-server.list; \
    apt-get update; \
    curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --output "$temporary/clangd-18.deb" "https://apt.llvm.org/jammy/pool/main/l/llvm-toolchain-18/clangd-18_18.1.8~++20240731024944+3b5b5c1ec4a3-1~exp1~20240731145000.144_${llvm_arch}.deb"; \
    echo "$clangd_sha  $temporary/clangd-18.deb" | sha256sum --check --strict; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$temporary/clangd-18.deb"; \
    clangd-18 --version | grep -F 'clangd version 18.1.8' >/dev/null; \
    rm -rf /etc/apt/keyrings/clangd-language-server.gpg /etc/apt/sources.list.d/clangd-language-server.list /var/lib/apt/lists/* "$temporary"; \
    DEBIAN_FRONTEND=noninteractive apt-get purge -y --auto-remove curl gnupg; \
    rm -rf /var/lib/apt/lists/*; \
    test ! -e /etc/apt/keyrings/clangd-language-server.gpg; \
    test ! -e /etc/apt/sources.list.d/clangd-language-server.list; \
    test ! -e /usr/bin/curl; \
    test ! -e /usr/bin/gpg

FROM runtime-base AS builder
ARG TARGETOS
ARG TARGETARCH
ARG TARGETVARIANT

# Disposable builder adds only build/package-manager capabilities to the clean
# runtime base.  System pip is unnecessary: pipx bootstraps each isolated app.

RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      curl \
      gnupg \
      build-essential \
      ninja-build \
      pipx

# Node/npm/corepack are builder-only package-management capabilities.
COPY --from=node-provider /usr/local/bin/node /usr/local/bin/node
COPY --from=node-provider /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=node-provider /usr/local/bin/npm /usr/local/bin/npm
COPY --from=node-provider /usr/local/bin/npx /usr/local/bin/npx
COPY --from=node-provider /usr/local/bin/corepack /usr/local/bin/corepack
RUN ln -sfn ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sfn ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -sfn ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack

RUN set -eux; \
    case "$TARGETOS/$TARGETARCH" in \
      linux/amd64) rustup_target=x86_64-unknown-linux-gnu; rustup_sha=20a06e644b0d9bd2fbdbfd52d42540bdde820ea7df86e92e533c073da0cdd43c ;; \
      linux/arm64) rustup_target=aarch64-unknown-linux-gnu; rustup_sha=e3853c5a252fca15252d07cb23a1bdd9377a8c6f3efa01531109281ae47f841c ;; \
      *) echo "unsupported_target_arch=$TARGETOS/$TARGETARCH" >&2; exit 2 ;; \
    esac; \
    curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
      --output /usr/local/bin/rustup-init \
      "https://static.rust-lang.org/rustup/archive/1.28.2/${rustup_target}/rustup-init"; \
    echo "$rustup_sha  /usr/local/bin/rustup-init" | sha256sum --check --strict; \
    chmod 0555 /usr/local/bin/rustup-init; \
    /usr/local/bin/rustup-init --version | grep -F '1.28.2' >/dev/null

COPY bootstrap/container/image/dependencies.toml /opt/agent-canon/bootstrap/container/image/dependencies.toml
COPY tools/runtime/container/devcontainer_dependencies.py /opt/agent-canon/tools/runtime/container/devcontainer_dependencies.py
COPY tools/analysis/dependencies/dependency_plan.py /opt/agent-canon/tools/analysis/dependencies/dependency_plan.py
COPY tools/repository/workspace/parent_root_side_effects.py /opt/agent-canon/tools/repository/workspace/parent_root_side_effects.py
COPY tools/runtime/artifacts/runtime_artifacts.py /opt/agent-canon/tools/runtime/artifacts/runtime_artifacts.py
COPY tools/runtime/dispatch/agent-canon /opt/agent-canon/tools/runtime/dispatch/agent-canon

ENV CARGO_HOME=/usr/local/share/agent-canon/toolchains/cargo \
    RUSTUP_HOME=/usr/local/share/agent-canon/toolchains/rustup \
    AGENT_CANON_CARGO_TARGET_DIR=/usr/local/share/agent-canon/toolchains/cargo-target \
    PIPX_HOME=/usr/local/share/agent-canon/pipx \
    PIPX_BIN_DIR=/usr/local/bin \
    PIPX_MAN_DIR=/usr/local/share/man \
    AGENT_CANON_IMAGE_DEPENDENCIES_ROOT=/usr/local/share/agent-canon/image-dependencies \
    PATH=/usr/local/share/agent-canon/toolchains/cargo/bin:/usr/local/bin:/usr/bin:/bin

RUN python3 /opt/agent-canon/tools/analysis/dependencies/dependency_plan.py \
      image-install --workspace /opt/agent-canon \
      --manifest /opt/agent-canon/bootstrap/container/image/dependencies.toml \
      --final-binary-dir /usr/local/bin --format text \
    && test -x /usr/local/bin/agent-canon \
    && test -d /usr/local/share/agent-canon/toolchains/cargo \
    && test -d /usr/local/share/agent-canon/toolchains/rustup \
    && test -f /usr/local/share/agent-canon/image-dependencies/plan.json \
    && test -f /usr/local/share/agent-canon/image-dependencies/receipts/agent-canon-cli.json \
    && install -d -m 0555 /usr/local/share/agent-canon/runtime \
    && install -m 0444 /opt/agent-canon/bootstrap/container/image/dependencies.toml /usr/local/share/agent-canon/runtime/dependencies.toml \
    && printf 'agent-canon-runtime/v1\n' > /usr/local/share/agent-canon/runtime/.agent-canon-runtime \
    && chmod 0444 /usr/local/share/agent-canon/runtime/.agent-canon-runtime \
    && test "$(stat -c '%a:%u:%g' /usr/local/share/agent-canon/runtime/.agent-canon-runtime)" = '444:0:0' \
    && rm -rf "$AGENT_CANON_CARGO_TARGET_DIR" "$CARGO_HOME/registry" "$CARGO_HOME/git" "$RUSTUP_HOME/downloads" "$RUSTUP_HOME/tmp" /root/.npm /usr/local/bin/rustup-init \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /opt/agent-canon \
    && test ! -e /opt/agent-canon \
    && test ! -e "$AGENT_CANON_CARGO_TARGET_DIR" \
    && test ! -e "$CARGO_HOME/registry" \
    && test ! -e "$CARGO_HOME/git"

# Final runtime inherits the already-clean retained system closure.
FROM runtime-base AS runtime
ARG TARGETOS
ARG TARGETARCH
ARG TARGETVARIANT

# Copy only node, the two declared JavaScript LSP trees, and package-relative
# launchers.  npm, npx, and corepack are intentionally not copied.
COPY --from=builder /usr/local/bin/node /usr/local/bin/node
COPY --from=builder /usr/local/lib/node_modules/pyright /usr/local/lib/node_modules/pyright
COPY --from=builder /usr/local/lib/node_modules/bash-language-server /usr/local/lib/node_modules/bash-language-server
RUN ln -sfn ../lib/node_modules/pyright/index.js /usr/local/bin/pyright \
    && ln -sfn ../lib/node_modules/pyright/langserver.index.js /usr/local/bin/pyright-langserver \
    && ln -sfn ../lib/node_modules/bash-language-server/out/cli.js /usr/local/bin/bash-language-server

# Copy pipx environments and only their public launchers.  The pipx package
# and executable themselves remain builder-only.
COPY --from=builder /usr/local/share/agent-canon/pipx/venvs/check-jsonschema /usr/local/share/agent-canon/pipx/venvs/check-jsonschema
COPY --from=builder /usr/local/share/agent-canon/pipx/venvs/yamllint /usr/local/share/agent-canon/pipx/venvs/yamllint
COPY --from=builder /usr/local/bin/check-jsonschema /usr/local/bin/check-jsonschema
COPY --from=builder /usr/local/bin/yamllint /usr/local/bin/yamllint

# Keep complete declared Rust components, but no Cargo target/registry/git
# caches.  The builder cleaned these before copying.
COPY --from=builder /usr/local/share/agent-canon/toolchains/cargo/bin /usr/local/share/agent-canon/toolchains/cargo/bin
COPY --from=builder /usr/local/share/agent-canon/toolchains/rustup /usr/local/share/agent-canon/toolchains/rustup
COPY --from=builder /usr/local/bin/agent-canon /usr/local/bin/agent-canon
COPY --from=builder /usr/local/share/agent-canon/image-dependencies /usr/local/share/agent-canon/image-dependencies
COPY --from=builder /usr/local/share/agent-canon/runtime/dependencies.toml /usr/local/share/agent-canon/runtime/dependencies.toml
COPY --from=builder /usr/local/share/agent-canon/runtime/.agent-canon-runtime /usr/local/share/agent-canon/runtime/.agent-canon-runtime

ENV CARGO_HOME=/usr/local/share/agent-canon/toolchains/cargo \
    RUSTUP_HOME=/usr/local/share/agent-canon/toolchains/rustup \
    AGENT_CANON_IMAGE_DEPENDENCIES_ROOT=/usr/local/share/agent-canon/image-dependencies \
    PATH=/usr/local/share/agent-canon/toolchains/cargo/bin:/usr/local/bin:/usr/bin:/bin

COPY tools /usr/local/share/agent-canon/runtime/tools
COPY agents /usr/local/share/agent-canon/runtime/agents
COPY documents /usr/local/share/agent-canon/runtime/documents
COPY schemas /usr/local/share/agent-canon/runtime/schemas
COPY bootstrap/host/manifest.toml /usr/local/share/agent-canon/runtime/bootstrap/host/manifest.toml
RUN install -d -m 0755 /usr/local/share/agent-canon/runtime/.codex/personal \
    && command -v yamllint \
    && command -v check-jsonschema \
    && test -f /usr/local/share/agent-canon/runtime/schemas/agent-canon/skill-catalog.schema.json \
    && test -f /usr/local/share/agent-canon/runtime/schemas/agent-canon/skill-dependencies.schema.json \
    && test -f /usr/local/share/agent-canon/runtime/schemas/agent-canon/tool-catalog.schema.json \
    && AGENT_CANON_IMAGE_BUILD=1 python3 /usr/local/share/agent-canon/runtime/tools/agent/skills/skill_shim_materializer.py materialize --root /usr/local/share/agent-canon/runtime --all --image-build --format text
COPY .codex/agents /usr/local/share/agent-canon/runtime/.codex/agents
COPY .codex/config.toml /usr/local/share/agent-canon/runtime/.codex/config.toml
COPY eval/definitions /usr/local/share/agent-canon/runtime/eval/definitions
COPY eval/producers /usr/local/share/agent-canon/runtime/eval/producers
COPY eval/checkers /usr/local/share/agent-canon/runtime/eval/checkers
COPY eval/fixtures /usr/local/share/agent-canon/runtime/eval/fixtures
COPY references /usr/local/share/agent-canon/runtime/references
COPY templates /usr/local/share/agent-canon/runtime/templates
COPY AGENTS.md ROOT_AGENTS.md /usr/local/share/agent-canon/runtime/

# Final capability, receipt, import, and absence checks.
RUN set -eux; \
    test -x /usr/local/bin/agent-canon; \
    test -x /usr/local/bin/node; node --version >/dev/null; \
    pyright --version | grep -F '1.1.411' >/dev/null; \
    test -x /usr/local/bin/pyright-langserver; langserver="$(readlink -f /usr/local/bin/pyright-langserver)"; test -f "$langserver"; node --check "$langserver"; \
    bash-language-server --version | grep -F '5.6.0' >/dev/null; \
    check-jsonschema --version | grep -F '0.31.0' >/dev/null; yamllint --version | grep -F '1.35.1' >/dev/null; \
    command -v jq; command -v tree; command -v clangd-18; \
    command -v cargo; command -v rustc; command -v rustfmt; command -v clippy-driver; command -v rust-analyzer; \
    python3 -c 'import packaging, tomli, yaml'; \
    test -f /usr/local/share/agent-canon/image-dependencies/plan.json; \
    test -f /usr/local/share/agent-canon/image-dependencies/receipts/agent-canon-cli.json; \
    test -f /usr/local/share/agent-canon/image-dependencies/receipts/clangd-language-server.json; \
    test -f /usr/local/share/agent-canon/image-dependencies/receipts/rust-toolchain.json; \
    test ! -e /usr/local/share/agent-canon/toolchains/cargo-target; \
    test ! -e /usr/local/share/agent-canon/toolchains/cargo/registry; \
    test ! -e /usr/local/share/agent-canon/toolchains/cargo/git; \
    test ! -e /usr/local/bin/rustup-init; \
    ! command -v pipx; test ! -e /usr/bin/pipx; test ! -d /usr/lib/python3/dist-packages/pipx; \
    ! command -v pytest; ! command -v pip; ! command -v pip3; ! command -v ninja; ! command -v curl; ! command -v gpg; \
    ! command -v npm; ! command -v npx; ! command -v corepack; ! command -v clang-format; \
    test -f /usr/local/share/agent-canon/runtime/tools/catalog.yaml \
    && test -f /usr/local/share/agent-canon/runtime/tools/runtime/dispatch/tool_dispatch.py \
    && test -f /usr/local/share/agent-canon/runtime/tools/bin/agent-canon \
    && test -f /usr/local/share/agent-canon/runtime/tools/fixtures/tool_dispatch/public-command-parity.json \
    && test -f /usr/local/share/agent-canon/runtime/agents/skills/catalog.yaml \
    && test -f /usr/local/share/agent-canon/runtime/.codex/config.toml \
    && test -f /usr/local/share/agent-canon/runtime/.codex/agents/worker.toml \
    && test -f /usr/local/share/agent-canon/runtime/.codex/personal/skills/agent-orchestration/SKILL.md \
    && test -f /usr/local/share/agent-canon/runtime/eval/definitions/skill_workflow_prompt_eval.toml \
    && test -f /usr/local/share/agent-canon/runtime/eval/producers/generate_agent_runtime_dashboard.py \
    && test -f /usr/local/share/agent-canon/runtime/eval/checkers/eval_accumulation_check.py \
    && test -f /usr/local/share/agent-canon/runtime/eval/fixtures/skill-runtime-shim/measurements/fixture-measurement.json \
    && test -f /usr/local/share/agent-canon/runtime/ROOT_AGENTS.md \
    && test -f /usr/local/share/agent-canon/runtime/documents/runtime/runtime-profiles-and-check-matrix.json

COPY bootstrap/container/lifecycle/entrypoint.sh /usr/local/bin/agent-canon-container-entrypoint
COPY bootstrap/container/dispatch/tool-wrapper.sh /usr/local/bin/agent-canon-tool
RUN chmod 0555 /usr/local/bin/agent-canon-container-entrypoint /usr/local/bin/agent-canon-tool

ENV AGENT_CANON_CONTROL_PARENT_ROOT=/var/lib/agent-canon \
    AGENT_CANON_RUNTIME_ROOT=/var/lib/agent-canon/runtime \
    AGENT_CANON_IMAGE_ROOT=/usr/local/share/agent-canon \
    AGENT_CANON_IMAGE_DEPENDENCIES_ROOT=/usr/local/share/agent-canon/image-dependencies \
    AGENT_CANON_RUNTIME_TOOLS_ROOT=/usr/local/share/agent-canon/runtime \
    AGENT_CANON_MOUNT_REGISTRY=/var/lib/agent-canon/mount-registry.toml \
    AGENT_CANON_IMAGE_MARKER_DIGEST=sha256:fa0a3ed734c6aa712c8446f5ea945470396df6427df761d75b78ed6ea146bcf9 \
    AGENT_CANON_RUNTIME_MARKER_DIGEST=sha256:86eded2c0e3aa36f3fe24e59a54f4eb18b0a152161d889617560a7553947ca13
WORKDIR /workspace
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["/usr/local/bin/agent-canon-container-entrypoint", "health"]
ENTRYPOINT ["/usr/local/bin/agent-canon-container-entrypoint"]
CMD ["resident"]
