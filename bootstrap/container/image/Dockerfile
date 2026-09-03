# @dependency-start
# contract environment
# responsibility Defines the stable shared AgentCanon Python, Rust, and LSP environment image.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared tool runtime boundary
# upstream implementation ../../tools/runtime/container/compile_tools.sh source-mounted Rust compilation
# downstream implementation ../lifecycle/entrypoint.sh resident liveness and dispatch
# @dependency-end

FROM ubuntu:24.04@sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517

ARG TARGETOS
ARG TARGETARCH
ENV PYTHONDONTWRITEBYTECODE=1 \
    CARGO_HOME=/var/lib/agent-canon/cache/cargo \
    RUSTUP_HOME=/usr/local/share/agent-canon/toolchains/rustup \
    CARGO_TARGET_DIR=/var/lib/agent-canon/cache/cargo-target \
    AGENT_CANON_CARGO_TARGET_DIR=/var/lib/agent-canon/cache/cargo-target \
    AGENT_CANON_SOURCE_ROOT=/opt/agent-canon/source \
    AGENT_CANON_CACHE_ROOT=/var/lib/agent-canon/cache \
    AGENT_CANON_COMPILED_BIN_DIR=/var/lib/agent-canon/cache/bin \
    PIPX_HOME=/usr/local/share/agent-canon/pipx \
    PIPX_BIN_DIR=/usr/local/bin \
    PIPX_MAN_DIR=/usr/local/share/man \
    AGENT_CANON_IMAGE_DEPENDENCIES_ROOT=/usr/local/share/agent-canon/image-dependencies \
    PATH=/var/lib/agent-canon/cache/bin:/usr/local/share/agent-canon/toolchains/cargo/bin:/usr/local/bin:/usr/bin:/bin

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

# Install bootstrap packages and manifest-owned environment dependencies in one image layer.
RUN --mount=type=bind,source=bootstrap/container/image/dependencies.toml,target=/src/bootstrap/container/image/dependencies.toml,readonly \
    --mount=type=bind,source=tools/runtime/container/devcontainer_dependencies.py,target=/src/tools/runtime/container/devcontainer_dependencies.py,readonly \
    --mount=type=bind,source=tools/analysis/dependencies/dependency_plan.py,target=/src/tools/analysis/dependencies/dependency_plan.py,readonly \
    --mount=type=bind,source=tools/repository/workspace/parent_root_side_effects.py,target=/src/tools/repository/workspace/parent_root_side_effects.py,readonly \
    --mount=type=bind,source=tools/runtime/artifacts/runtime_artifacts.py,target=/src/tools/runtime/artifacts/runtime_artifacts.py,readonly \
    set -eux; \
    export CARGO_HOME=/usr/local/share/agent-canon/toolchains/cargo; \
    export PATH="$CARGO_HOME/bin:$PATH"; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates git nodejs=18.19.1+dfsg-6ubuntu5 npm=9.2.0~ds1-2 \
      python3.12 python3-packaging python3-yaml build-essential curl; \
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
    rm -rf /var/lib/agent-canon/cache/cargo-target "$CARGO_HOME/registry" "$CARGO_HOME/git" /root/.npm /root/.cache /tmp/* /usr/local/bin/rustup-init; \
    DEBIAN_FRONTEND=noninteractive apt-get purge -y --auto-remove npm pipx; \
    rm -rf /var/lib/apt/lists/*

# Only the fixed container adapter is copied into the image.  The current
# AgentCanon source, controller, skills, and dispatch catalog are mounted by
# the host at runtime, so source-only updates reuse this environment image.
RUN --mount=type=bind,source=bootstrap/container/lifecycle/entrypoint.sh,target=/src/entrypoint.sh,readonly \
    --mount=type=bind,source=bootstrap/container/dispatch/tool-wrapper.sh,target=/src/tool-wrapper.sh,readonly \
    set -eux; \
    install -m 0555 /src/entrypoint.sh /usr/local/bin/agent-canon-container-entrypoint; \
    install -m 0555 /src/tool-wrapper.sh /usr/local/bin/agent-canon-tool

ENV AGENT_CANON_CONTROL_PARENT_ROOT=/var/lib/agent-canon \
    AGENT_CANON_RUNTIME_ROOT=/var/lib/agent-canon/runtime \
    AGENT_CANON_IMAGE_ROOT=/usr/local/share/agent-canon \
    AGENT_CANON_RUNTIME_TOOLS_ROOT=/opt/agent-canon/source \
    AGENT_CANON_MOUNT_REGISTRY=/var/lib/agent-canon/mount-registry.toml \
    AGENT_CANON_IMAGE_MARKER_DIGEST=sha256:fa0a3ed734c6aa712c8446f5ea945470396df6427df761d75b78ed6ea146bcf9 \
    AGENT_CANON_RUNTIME_MARKER_DIGEST=sha256:86eded2c0e3aa36f3fe24e59a54f4eb18b0a152161d889617560a7553947ca13

WORKDIR /workspace
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["/usr/local/bin/agent-canon-container-entrypoint", "health"]
ENTRYPOINT ["/usr/local/bin/agent-canon-container-entrypoint"]
CMD ["resident"]
