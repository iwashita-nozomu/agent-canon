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
    test "${PROJECT_UID}" -gt 0; \
    test "${PROJECT_GID}" -gt 0; \
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
    groupadd --gid "${PROJECT_GID}" project; \
    useradd --uid "${PROJECT_UID}" --gid project --create-home --shell /bin/bash project; \
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

COPY .devcontainer/dependencies.toml /opt/agent-canon/.devcontainer/dependencies.toml
COPY tools/agent_tools/devcontainer_dependencies.py /opt/agent-canon/tools/agent_tools/devcontainer_dependencies.py
RUN python3 /opt/agent-canon/tools/agent_tools/devcontainer_dependencies.py \
      image-install --workspace /opt/agent-canon --vendor-root /opt/agent-canon --format text \
    && rm -rf /opt/agent-canon

RUN install -d -o project -g project -m 0755 \
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
