# @dependency-start
# contract environment
# responsibility Provides the standalone AgentCanon source devcontainer image.
# upstream design ../documents/design/devcontainer/parent-devcontainer-policy.md canonical project identity
# downstream implementation generate-runtime-compose.sh passes PROJECT_UID/PROJECT_GID
# @dependency-end

FROM --platform=linux/amd64 node:22.14.0-bullseye-slim@sha256:73a9dfbb6c761aebdf4666cce2627635a30d1d4c20f67ff642d01b8f09e709a3 AS node-provider

FROM --platform=linux/amd64 ubuntu:22.04@sha256:0e0a0fc6d18feda9db1590da249ac93e8d5abfea8f4c3c0c849ce512b5ef8982

ARG PROJECT_UID=1000
ARG PROJECT_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1

RUN set -eux; \
    case "${PROJECT_UID}" in \
      ''|0|0*|*[!0-9]*) echo "PROJECT_UID must be a nonzero decimal" >&2; exit 1 ;; \
    esac; \
    case "${PROJECT_GID}" in \
      ''|*[!0-9]*) echo "PROJECT_GID must be a nonnegative decimal" >&2; exit 1 ;; \
    esac; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates \
      git \
      sudo \
      python3 \
      python3-pip \
      pipx \
      python3-packaging \
      python3-tomli \
      curl \
      gnupg \
      build-essential \
      ninja-build; \
    rm -rf /var/lib/apt/lists/*; \
    if getent passwd project >/dev/null; then \
      echo "project user-name collision" >&2; exit 1; \
    fi; \
    if getent passwd "${PROJECT_UID}" >/dev/null; then \
      echo "PROJECT_UID is already owned by another user" >&2; exit 1; \
    fi; \
    existing_group_record="$(getent group "${PROJECT_GID}" || true)"; \
    if [ -n "${existing_group_record}" ]; then \
      :; \
    else \
      if getent group project >/dev/null; then \
        echo "project group-name collision at another GID" >&2; exit 1; \
      fi; \
      groupadd --gid "${PROJECT_GID}" project; \
    fi; \
    useradd --uid "${PROJECT_UID}" --gid "${PROJECT_GID}" --create-home --shell /bin/bash project; \
    printf '%s\n' 'project ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/project; \
    chmod 0440 /etc/sudoers.d/project

# Node is an image-owned capability. Keep the official provider pinned by
# digest while copying its runtime and package manager payload into the Ubuntu
# image that owns the remaining fixed capabilities.
COPY --from=node-provider /usr/local/bin/node /usr/local/bin/node
COPY --from=node-provider /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=node-provider /usr/local/bin/npm /usr/local/bin/npm
COPY --from=node-provider /usr/local/bin/npx /usr/local/bin/npx
COPY --from=node-provider /usr/local/bin/corepack /usr/local/bin/corepack
RUN ln -sfn ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sfn ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -sfn ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack

RUN set -eux; \
    curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
      --output /usr/local/bin/rustup-init \
      https://static.rust-lang.org/rustup/archive/1.28.2/x86_64-unknown-linux-gnu/rustup-init; \
    echo '20a06e644b0d9bd2fbdbfd52d42540bdde820ea7df86e92e533c073da0cdd43c  /usr/local/bin/rustup-init' | sha256sum --check --strict; \
    chmod 0555 /usr/local/bin/rustup-init; \
    /usr/local/bin/rustup-init --version | grep -F '1.28.2' >/dev/null

COPY .devcontainer/dependencies.toml /opt/agent-canon/.devcontainer/dependencies.toml
COPY tools/agent_tools/devcontainer_dependencies.py /opt/agent-canon/tools/agent_tools/devcontainer_dependencies.py
COPY tools/agent_tools/parent_root_side_effects.py /opt/agent-canon/tools/agent_tools/parent_root_side_effects.py
COPY rust/agent-canon /opt/agent-canon-source/rust/agent-canon
ENV CARGO_HOME=/usr/local/share/agent-canon/toolchains/cargo \
    RUSTUP_HOME=/usr/local/share/agent-canon/toolchains/rustup \
    AGENT_CANON_CARGO_TARGET_DIR=/usr/local/share/agent-canon/toolchains/cargo-target \
    PATH=/usr/local/share/agent-canon/toolchains/cargo/bin:$PATH
RUN python3 /opt/agent-canon/tools/agent_tools/devcontainer_dependencies.py \
      image-install --workspace /opt/agent-canon --vendor-root /opt/agent-canon \
      --final-binary-dir /usr/local/bin --format text \
    && test -x /usr/local/bin/agent-canon \
    && test -d /usr/local/share/agent-canon/toolchains/cargo \
    && test -d /usr/local/share/agent-canon/toolchains/rustup \
    && rm -rf /opt/agent-canon /opt/agent-canon-source \
    && test ! -e /opt/agent-canon \
    && test ! -e /opt/agent-canon-source

RUN install -d -o project -g "${PROJECT_GID}" -m 0755 \
      /home/project/.tools/bin \
      /var/lib/agent-canon/runtime \
      /var/lib/agent-canon/runtime/runs \
      /var/lib/agent-canon/runtime/logs \
    && printf '%s\n' \
      'export AGENT_CANON_TOOLS_HOME="/home/project/.tools"' \
      'export AGENT_CANON_RUNTIME_ROOT="/var/lib/agent-canon/runtime"' \
      'export AGENT_CANON_IMAGE_DEPENDENCIES_ROOT="/usr/local/share/agent-canon/image-dependencies"' \
      'case ":$PATH:" in *:"/home/project/.tools/bin":*) ;; *) export PATH="/home/project/.tools/bin:$PATH" ;; esac' \
      > /etc/profile.d/agent-canon-tools.sh \
    && chmod 0644 /etc/profile.d/agent-canon-tools.sh \
    && chown root:root /etc/profile.d/agent-canon-tools.sh

ENV HOME=/home/project \
    USER=project \
    AGENT_CANON_CONTAINER_USER=project
WORKDIR /workspace
USER project
CMD ["bash", "-lc", "sleep infinity"]
