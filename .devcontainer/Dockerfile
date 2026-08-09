# @dependency-start
# contract environment
# responsibility Provides the standalone AgentCanon source devcontainer image.
# upstream design ../documents/design/devcontainer/parent-devcontainer-policy.md canonical project identity
# downstream implementation generate-runtime-compose.sh passes PROJECT_UID/PROJECT_GID
# @dependency-end

FROM ubuntu:22.04@sha256:0e0a0fc6d18feda9db1590da249ac93e8d5abfea8f4c3c0c849ce512b5ef8982

ARG PROJECT_UID=1000
ARG PROJECT_GID=1000

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

ENV HOME=/home/project \
    USER=project \
    AGENT_CANON_CONTAINER_USER=project
WORKDIR /workspace
USER project
CMD ["bash", "-lc", "sleep infinity"]
