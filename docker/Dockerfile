# @dependency-start
# contract environment
# responsibility Provides the standalone AgentCanon public Docker test image.
# upstream design ../CONTAINER_OPERATIONS.md standalone source test boundary
# upstream design ../documents/runtime/SHARED_RUNTIME_SURFACES.md source/view ownership boundary
# upstream design ../responsibility-scope.toml source responsibility scopes
# downstream implementation ../test/testrunner.sh public test runner
# downstream implementation ../test/testlist.toml typed test command contract
# downstream implementation ../tests/tools/test_container_config.py container contract regression tests
# @dependency-end

FROM rust:1.89-bookworm

ARG PROJECT_UID=1000
ARG PROJECT_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/agent-canon-parent/vendor/agent-canon/test:/usr/local/cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

RUN set -eux; \
    apt-get update; \
    apt-get install --yes --no-install-recommends \
      bash \
      ca-certificates \
      git \
      build-essential \
      jq \
      libssl-dev \
      pkg-config \
      python3 \
      python3-pip \
      tree; \
    rm -rf /var/lib/apt/lists/*; \
    case "${PROJECT_UID}" in \
      ''|*[!0-9]*) echo "PROJECT_UID must be a nonzero decimal" >&2; exit 1 ;; \
    esac; \
    case "${PROJECT_UID}" in \
      *[1-9]*) ;; \
      *) echo "PROJECT_UID must be a nonzero decimal" >&2; exit 1 ;; \
    esac; \
    case "${PROJECT_GID}" in \
      ''|*[!0-9]*) echo "PROJECT_GID must be a nonnegative decimal" >&2; exit 1 ;; \
    esac; \
    existing_group_record="$(getent group "${PROJECT_GID}" || true)"; \
    if [ -z "${existing_group_record}" ]; then \
      groupadd --gid "${PROJECT_GID}" project; \
    fi; \
    useradd --uid "${PROJECT_UID}" --gid "${PROJECT_GID}" --create-home --shell /bin/bash project; \
    python3 -m pip install --break-system-packages --no-cache-dir --disable-pip-version-check \
      pytest==9.1.1 \
      pyright==1.1.411 \
      ruff==0.16.3 \
      pydocstyle==6.3.0 \
      tomli==2.4.1 \
      PyYAML==6.0.3 \
      jax==0.9.2 \
      jaxlib==0.9.2 \
      equinox==0.13.6

WORKDIR /opt/agent-canon-parent/vendor/agent-canon
COPY . /opt/agent-canon-parent/vendor/agent-canon/

RUN source_root=/opt/agent-canon-parent/vendor/agent-canon \
    && parent_root=/opt/agent-canon-parent \
    && runtime_root=/opt/agent-canon-parent/.agent-canon/image-runtime \
    && chmod 0555 "${source_root}/test/testrunner.sh" \
    && test -f "${source_root}/test/testlist.toml" \
    && git -C "${source_root}" init \
    && current_head="$(git -C "${source_root}" rev-parse --verify HEAD^{commit})" \
    && git -C "${source_root}" update-ref refs/heads/main "${current_head}" \
    && git -C "${source_root}" symbolic-ref HEAD refs/heads/main \
    && git -C "${source_root}" for-each-ref --format='%(refname)' refs \
      | while IFS= read -r ref; do \
          if [ "${ref}" != "refs/heads/main" ]; then \
            git -C "${source_root}" update-ref -d "${ref}"; \
          fi; \
        done \
    && test "$(git -C "${source_root}" rev-parse --verify HEAD^{commit})" = "${current_head}" \
    && git -C "${source_root}" reset --mixed "${current_head}" \
    && git -C "${source_root}" config user.name "AgentCanon Test" \
    && git -C "${source_root}" config user.email "agent-canon-test@invalid" \
    && { git -C "${source_root}" remote remove origin 2>/dev/null || true; } \
    && git -C "${source_root}" remote add origin https://github.com/iwashita-nozomu/agent-canon.git \
    && git -C "${source_root}" add -A \
    && if ! git -C "${source_root}" diff --cached --quiet; then \
         GIT_AUTHOR_DATE=2026-08-14T00:00:00Z \
         GIT_COMMITTER_DATE=2026-08-14T00:00:00Z \
         git -C "${source_root}" commit -m "Initialize AgentCanon image test snapshot"; \
       fi \
    && printf '%s\n' '.agent-canon/' >> "${source_root}/.git/info/exclude" \
    && git -C "${parent_root}" init --initial-branch=main \
    && git -C "${parent_root}" config user.name "AgentCanon Parent Test" \
    && git -C "${parent_root}" config user.email "agent-canon-parent-test@invalid" \
    && git -C "${parent_root}" remote add origin https://github.com/iwashita-nozomu/project_template.git \
    && printf '%s\n' '.agent-canon/' > "${parent_root}/.gitignore" \
    && printf '%s\n' \
         '[submodule "vendor/agent-canon"]' \
         '  path = vendor/agent-canon' \
         '  url = https://github.com/iwashita-nozomu/agent-canon.git' \
         > "${parent_root}/.gitmodules" \
    && git -C "${parent_root}" add .gitignore .gitmodules vendor/agent-canon \
    && GIT_AUTHOR_DATE=2026-08-14T00:00:00Z \
       GIT_COMMITTER_DATE=2026-08-14T00:00:00Z \
       git -C "${parent_root}" commit -m "Initialize parent image test snapshot" \
    && AGENT_CANON_COMMIT_REQUEST_EVIDENCE=evidence:bbde708b7b3bb2a893da85652df55ea7337b1908c2e74cf3a9e0b2e054289593 \
       AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval \
       AGENT_CANON_DESTRUCTIVE_GIT_REASON=materialize-public-parent-runtime-views-in-image-fixture \
       HOME="${parent_root}/.agent-canon/home" \
       TMPDIR="${parent_root}/.agent-canon/tmp/sync" \
       TEMP="${parent_root}/.agent-canon/tmp/sync" \
       TMP="${parent_root}/.agent-canon/tmp/sync" \
       XDG_CACHE_HOME="${parent_root}/.agent-canon/cache" \
       PYTHONPYCACHEPREFIX="${parent_root}/.agent-canon/cache/pycache" \
       AGENT_CANON_TOOLS_HOME="${parent_root}/.agent-canon/tools" \
       CARGO_HOME="${parent_root}/.agent-canon/cache/cargo-home" \
       CARGO_TARGET_DIR="${parent_root}/.agent-canon/cache/cargo-target" \
       AGENT_CANON_CLI_TARGET_DIR="${parent_root}/.agent-canon/cache/cargo-target" \
       bash "${source_root}/tools/sync_agent_canon.sh" link-root \
    && test -L "${parent_root}/AGENTS.md" \
    && test ! -e "${parent_root}/.agents" \
    && test -L "${parent_root}/tools/agent-canon" \
    && test "$(git -C "${parent_root}" ls-tree HEAD vendor/agent-canon | awk '{print $1":"$2":"$3}')" \
         = "160000:commit:$(git -C "${source_root}" rev-parse HEAD)" \
    && test "$(git -C "${source_root}" symbolic-ref HEAD)" = "refs/heads/main" \
    && test "$(git -C "${source_root}" rev-parse HEAD)" \
         = "$(git -C "${source_root}" rev-parse refs/heads/main)" \
    && test "$(git -C "${source_root}" remote)" = "origin" \
    && test "$(git -C "${parent_root}" remote)" = "origin" \
    && test "$(git -C "${source_root}" remote get-url origin)" \
         = 'https://github.com/iwashita-nozomu/agent-canon.git' \
    && test "$(git -C "${parent_root}" remote get-url origin)" \
         = 'https://github.com/iwashita-nozomu/project_template.git' \
    && test "$(git -C "${parent_root}" config -f .gitmodules --get submodule.vendor/agent-canon.url)" \
         = 'https://github.com/iwashita-nozomu/agent-canon.git' \
    && test -z "$(git -C "${source_root}" for-each-ref --format='%(refname)' refs/remotes || true)" \
    && test -z "$(git -C "${parent_root}" for-each-ref --format='%(refname)' refs/remotes || true)" \
    && test -z "$(git -C "${source_root}" config --get-regexp '^credential\.' || true)" \
    && test -z "$(git -C "${parent_root}" config --get-regexp '^credential\.' || true)" \
    && clone_probe="$(mktemp -d --tmpdir="${parent_root}/.agent-canon" docker-git-clone.XXXXXX)" \
    && git clone --bare --no-local "${source_root}" "${clone_probe}/agent-canon.git" \
    && git --git-dir="${clone_probe}/agent-canon.git" fsck --full \
    && rm -rf "${clone_probe}" \
    && mkdir -p "${runtime_root}/tools/agent-canon" "${runtime_root}/cargo-target" \
    && CARGO_TARGET_DIR="${runtime_root}/cargo-target" \
      cargo install --locked --path "${source_root}/rust/agent-canon" \
      --root "${runtime_root}/tools/agent-canon" \
    && CARGO_TARGET_DIR="${runtime_root}/cargo-target" \
      cargo test --locked --offline --no-run \
      --manifest-path "${source_root}/rust/agent-canon/Cargo.toml" \
    && python3 -m py_compile \
      "${source_root}/tools/agent_tools/surface_manifest.py" \
      "${source_root}/tools/agent_tools/repo_structure_contract.py" \
      "${source_root}/tools/agent_tools/responsibility_scope.py" \
    && chown -R "${PROJECT_UID}:${PROJECT_GID}" \
      "${parent_root}"

WORKDIR /opt/agent-canon-parent/vendor/agent-canon
USER project
ENV HOME=/home/project \
    USER=project \
    AGENT_CANON_CONTAINER_USER=project

CMD ["testrunner.sh"]
