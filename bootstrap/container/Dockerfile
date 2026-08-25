# @dependency-start
# contract environment
# responsibility Defines the one shared AgentCanon Python, Rust, and LSP tool image.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared tool runtime boundary
# upstream implementation ../../tools/agent_tools/dependency_plan.py typed image dependency installer
# downstream implementation ./entrypoint.sh resident runtime and health probe
# @dependency-end

# The Node provider is copied into the fixed Ubuntu image so npm LSP tools stay
# image-owned. Both base images are pinned to immutable multi-platform OCI
# indexes and selected for the target platform; no project checkout is used as
# an image build input other than the canonical Rust CLI source, public tool
# assets, and this standalone dependency manifest.
ARG TARGETPLATFORM
FROM --platform=$TARGETPLATFORM node:22.14.0-bullseye-slim@sha256:73a9dfbb6c761aebdf4666cce2627635a30d1d4c20f67ff642d01b8f09e709a3 AS node-provider

FROM --platform=$TARGETPLATFORM ubuntu:22.04@sha256:2edbbc5dc405e9612ba3584ce95480277e3eb374407b5505fe26f17df77c7dbc

ENV PYTHONDONTWRITEBYTECODE=1

LABEL org.opencontainers.image.title="AgentCanon shared tool runtime"

ARG TARGETOS
ARG TARGETARCH
ARG TARGETVARIANT

RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      gnupg \
      build-essential \
      ninja-build \
      python3 \
      python3-pip \
      python3-packaging \
      python3-pytest \
      python3-tomli \
      python3-yaml; \
    install -d -m 0755 /workspace /var/lib/agent-canon/runtime /usr/local/share/agent-canon; \
    chmod 1777 /tmp; \
    printf 'agent-canon-tool-container/v1\n' > /usr/local/share/agent-canon/.agent-canon-tool-container; \
    chmod 0444 /usr/local/share/agent-canon/.agent-canon-tool-container; \
    test "$(stat -c '%a:%u:%g' /usr/local/share/agent-canon/.agent-canon-tool-container)" = '444:0:0'

# Node and npm are image-owned capabilities. The provider remains digest
# pinned while the final image owns the stable executable locations.
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

# The host bootstrap supplies these paths in the repository-root build
# context. They are copied into a disposable installer workspace and removed
# in the same layer.  The manifest is explicit: no synthetic developer
# configuration path is needed by the standalone image installer.
COPY bootstrap/container/dependencies.toml /opt/agent-canon/bootstrap/container/dependencies.toml
COPY tools/agent_tools/devcontainer_dependencies.py /opt/agent-canon/tools/agent_tools/devcontainer_dependencies.py
COPY tools/agent_tools/dependency_plan.py /opt/agent-canon/tools/agent_tools/dependency_plan.py
COPY tools/agent_tools/parent_root_side_effects.py /opt/agent-canon/tools/agent_tools/parent_root_side_effects.py
COPY tools/agent_tools/runtime_artifacts.py /opt/agent-canon/tools/agent_tools/runtime_artifacts.py
COPY rust/agent-canon /opt/agent-canon/rust/agent-canon

ENV CARGO_HOME=/usr/local/share/agent-canon/toolchains/cargo \
    RUSTUP_HOME=/usr/local/share/agent-canon/toolchains/rustup \
    AGENT_CANON_CARGO_TARGET_DIR=/usr/local/share/agent-canon/toolchains/cargo-target \
    AGENT_CANON_IMAGE_DEPENDENCIES_ROOT=/usr/local/share/agent-canon/image-dependencies \
    PATH=/usr/local/share/agent-canon/toolchains/cargo/bin:/usr/local/bin:/usr/bin:/bin

RUN python3 /opt/agent-canon/tools/agent_tools/dependency_plan.py \
      image-install --workspace /opt/agent-canon \
      --manifest /opt/agent-canon/bootstrap/container/dependencies.toml \
      --final-binary-dir /usr/local/bin --format text \
    && test -x /usr/local/bin/agent-canon \
    && test -d /usr/local/share/agent-canon/toolchains/cargo \
    && test -d /usr/local/share/agent-canon/toolchains/rustup \
    && test -f /usr/local/share/agent-canon/image-dependencies/plan.json \
    && install -d -m 0555 /usr/local/share/agent-canon/runtime \
    && install -m 0444 /opt/agent-canon/bootstrap/container/dependencies.toml \
      /usr/local/share/agent-canon/runtime/dependencies.toml \
    && printf 'agent-canon-runtime/v1\n' > /usr/local/share/agent-canon/runtime/.agent-canon-runtime \
    && chmod 0444 /usr/local/share/agent-canon/runtime/.agent-canon-runtime \
    && test "$(stat -c '%a:%u:%g' /usr/local/share/agent-canon/runtime/.agent-canon-runtime)" = '444:0:0' \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /opt/agent-canon \
    && test ! -e /opt/agent-canon

# Public tool assets are layered after the expensive dependency/Rust build so
# catalog and Python-tool updates do not rebuild the shared toolchain.
COPY tools /usr/local/share/agent-canon/runtime/tools
COPY agents /usr/local/share/agent-canon/runtime/agents
COPY documents /usr/local/share/agent-canon/runtime/documents
COPY .codex/personal/skills /usr/local/share/agent-canon/runtime/.codex/personal/skills
COPY .codex/agents /usr/local/share/agent-canon/runtime/.codex/agents
COPY .codex/config.toml /usr/local/share/agent-canon/runtime/.codex/config.toml
COPY evidence/agent-evals /usr/local/share/agent-canon/runtime/evidence/agent-evals
COPY references /usr/local/share/agent-canon/runtime/references
COPY templates /usr/local/share/agent-canon/runtime/templates
COPY AGENTS.md ROOT_AGENTS.md /usr/local/share/agent-canon/runtime/
RUN test -f /usr/local/share/agent-canon/runtime/tools/catalog.yaml \
    && test -f /usr/local/share/agent-canon/runtime/tools/agent_tools/tool_dispatch.py \
    && test -f /usr/local/share/agent-canon/runtime/tools/bin/agent-canon \
    && test -f /usr/local/share/agent-canon/runtime/tools/fixtures/tool_dispatch/public-command-parity.json \
    && test -f /usr/local/share/agent-canon/runtime/agents/skills/catalog.yaml \
    && test -f /usr/local/share/agent-canon/runtime/.codex/config.toml \
    && test -f /usr/local/share/agent-canon/runtime/.codex/agents/worker.toml \
    && test -f /usr/local/share/agent-canon/runtime/.codex/personal/skills/agent-orchestration/SKILL.md \
    && test -f /usr/local/share/agent-canon/runtime/evidence/agent-evals/skill_workflow_prompt_eval.toml \
    && test -f /usr/local/share/agent-canon/runtime/ROOT_AGENTS.md \
    && test -f /usr/local/share/agent-canon/runtime/documents/runtime/runtime-profiles-and-check-matrix.json \
    && chown -R root:root /usr/local/share/agent-canon/runtime/tools /usr/local/share/agent-canon/runtime/agents /usr/local/share/agent-canon/runtime/documents

COPY bootstrap/container/entrypoint.sh /usr/local/bin/agent-canon-container-entrypoint
COPY bootstrap/container/agent-canon-tool-wrapper.sh /usr/local/bin/agent-canon-tool
RUN chmod 0555 /usr/local/bin/agent-canon-container-entrypoint /usr/local/bin/agent-canon-tool \
    && chown -R root:root /usr/local/bin/agent-canon-container-entrypoint \
    && chown -R root:root /usr/local/bin/agent-canon-tool \
    && chown -R root:root /usr/local/share/agent-canon /var/lib/agent-canon /workspace

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
