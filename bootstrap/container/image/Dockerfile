# @dependency-start
# contract environment
# responsibility Defines the single pulled AgentCanon Python, Rust, and LSP runtime image.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared tool runtime boundary
# upstream implementation ../../tools/analysis/dependencies/dependency_plan.py typed dependency installer
# downstream implementation ../lifecycle/entrypoint.sh resident liveness and dispatch
# @dependency-end

FROM ubuntu:24.04@sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517

ARG TARGETOS
ARG TARGETARCH
ARG TARGETVARIANT
ENV PYTHONDONTWRITEBYTECODE=1 \
    CARGO_HOME=/usr/local/share/agent-canon/toolchains/cargo \
    RUSTUP_HOME=/usr/local/share/agent-canon/toolchains/rustup \
    AGENT_CANON_CARGO_TARGET_DIR=/usr/local/share/agent-canon/toolchains/cargo-target \
    PIPX_HOME=/usr/local/share/agent-canon/pipx \
    PIPX_BIN_DIR=/usr/local/bin \
    PIPX_MAN_DIR=/usr/local/share/man \
    AGENT_CANON_IMAGE_DEPENDENCIES_ROOT=/usr/local/share/agent-canon/image-dependencies \
    PATH=/usr/local/share/agent-canon/toolchains/cargo/bin:/usr/local/bin:/usr/bin:/bin

LABEL org.opencontainers.image.title="AgentCanon shared tool runtime" \
      org.opencontainers.image.version="24.04" \
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

# BuildKit read-only exact inputs keep unrelated docs/skill changes out of the
# dependency/Rust layer.  Runtime and build packages share one apt transaction;
# all build-only package managers and caches are purged before this layer ends.
RUN --mount=type=bind,source=bootstrap/container/image/dependencies.toml,target=/src/bootstrap/container/image/dependencies.toml,readonly \
    --mount=type=bind,source=tools/runtime/container/devcontainer_dependencies.py,target=/src/tools/runtime/container/devcontainer_dependencies.py,readonly \
    --mount=type=bind,source=tools/analysis/dependencies/dependency_plan.py,target=/src/tools/analysis/dependencies/dependency_plan.py,readonly \
    --mount=type=bind,source=tools/repository/workspace/parent_root_side_effects.py,target=/src/tools/repository/workspace/parent_root_side_effects.py,readonly \
    --mount=type=bind,source=tools/runtime/artifacts/runtime_artifacts.py,target=/src/tools/runtime/artifacts/runtime_artifacts.py,readonly \
    --mount=type=bind,source=tools/runtime/dispatch/agent-canon,target=/src/tools/runtime/dispatch/agent-canon,readonly \
    set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates git jq=1.7.1-3ubuntu0.24.04.2 tree=2.1.1-2ubuntu3.24.04.2 \
      nodejs=18.19.1+dfsg-6ubuntu5 npm=9.2.0~ds1-2 clangd-18=1:18.1.3-1ubuntu1 \
      python3.12 python3-packaging python3-yaml pipx=1.4.3-1 build-essential curl; \
    case "$TARGETOS/$TARGETARCH" in \
      linux/amd64) rustup_target=x86_64-unknown-linux-gnu; rustup_sha=20a06e644b0d9bd2fbdbfd52d42540bdde820ea7df86e92e533c073da0cdd43c ;; \
      linux/arm64) rustup_target=aarch64-unknown-linux-gnu; rustup_sha=e3853c5a252fca15252d07cb23a1bdd9377a8c6f3efa01531109281ae47f841c ;; \
      *) echo "unsupported_target_arch=$TARGETOS/$TARGETARCH" >&2; exit 2 ;; \
    esac; \
    curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --output /usr/local/bin/rustup-init "https://static.rust-lang.org/rustup/archive/1.28.2/${rustup_target}/rustup-init"; \
    echo "$rustup_sha  /usr/local/bin/rustup-init" | sha256sum --check --strict; \
    chmod 0555 /usr/local/bin/rustup-init; \
    python3 /src/tools/analysis/dependencies/dependency_plan.py \
      image-install --workspace /src \
      --manifest /src/bootstrap/container/image/dependencies.toml \
      --final-binary-dir /usr/local/bin --format text; \
    install -d -m 0755 /usr/local/share/agent-canon/runtime; \
    install -m 0444 /src/bootstrap/container/image/dependencies.toml /usr/local/share/agent-canon/runtime/dependencies.toml; \
    printf 'agent-canon-tool-container/v1\n' > /usr/local/share/agent-canon/.agent-canon-tool-container; \
    chmod 0444 /usr/local/share/agent-canon/.agent-canon-tool-container; \
    printf 'agent-canon-runtime/v1\n' > /usr/local/share/agent-canon/runtime/.agent-canon-runtime; \
    chmod 0444 /usr/local/share/agent-canon/runtime/.agent-canon-runtime; \
    rm -rf /usr/local/share/agent-canon/toolchains/cargo-target /usr/local/share/agent-canon/toolchains/cargo/registry /usr/local/share/agent-canon/toolchains/cargo/git /root/.npm /root/.cache /tmp/* /usr/local/bin/rustup-init; \
    DEBIAN_FRONTEND=noninteractive apt-get purge -y --auto-remove npm pipx build-essential curl; \
    rm -rf /var/lib/apt/lists/*

# The asset projection is the only whole-source mount.  It runs after the
# dependency layer so skill/docs edits reuse the expensive package/Rust layer.
RUN --mount=type=bind,source=.,target=/src,readonly \
    set -eux; \
    cp -a /src/tools /usr/local/share/agent-canon/runtime/; \
    cp -a /src/agents /usr/local/share/agent-canon/runtime/; \
    cp -a /src/documents /usr/local/share/agent-canon/runtime/; \
    cp -a /src/schemas /usr/local/share/agent-canon/runtime/; \
    install -d -m 0755 /usr/local/share/agent-canon/runtime/bootstrap; \
    cp -a /src/bootstrap/host/manifest.toml /usr/local/share/agent-canon/runtime/bootstrap/host-manifest.toml; \
    cp -a /src/.codex /usr/local/share/agent-canon/runtime/; \
    cp -a /src/eval /usr/local/share/agent-canon/runtime/; \
    cp -a /src/references /usr/local/share/agent-canon/runtime/; \
    cp -a /src/templates /usr/local/share/agent-canon/runtime/; \
    cp -a /src/AGENTS.md /src/ROOT_AGENTS.md /usr/local/share/agent-canon/runtime/; \
    AGENT_CANON_IMAGE_BUILD=1 python3 /usr/local/share/agent-canon/runtime/tools/agent/skills/skill_shim_materializer.py materialize --root /usr/local/share/agent-canon/runtime --all --image-build --format text; \
    cp -a /src/bootstrap/container/lifecycle/entrypoint.sh /usr/local/bin/agent-canon-container-entrypoint; \
    cp -a /src/bootstrap/container/dispatch/tool-wrapper.sh /usr/local/bin/agent-canon-tool; \
    chmod 0555 /usr/local/bin/agent-canon-container-entrypoint /usr/local/bin/agent-canon-tool

ENV AGENT_CANON_CONTROL_PARENT_ROOT=/var/lib/agent-canon \
    AGENT_CANON_RUNTIME_ROOT=/var/lib/agent-canon/runtime \
    AGENT_CANON_IMAGE_ROOT=/usr/local/share/agent-canon \
    AGENT_CANON_RUNTIME_TOOLS_ROOT=/usr/local/share/agent-canon/runtime \
    AGENT_CANON_MOUNT_REGISTRY=/var/lib/agent-canon/mount-registry.toml \
    AGENT_CANON_IMAGE_MARKER_DIGEST=sha256:fa0a3ed734c6aa712c8446f5ea945470396df6427df761d75b78ed6ea146bcf9 \
    AGENT_CANON_RUNTIME_MARKER_DIGEST=sha256:86eded2c0e3aa36f3fe24e59a54f4eb18b0a152161d889617560a7553947ca13

WORKDIR /workspace
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["/usr/local/bin/agent-canon-container-entrypoint", "health"]
ENTRYPOINT ["/usr/local/bin/agent-canon-container-entrypoint"]
CMD ["resident"]
