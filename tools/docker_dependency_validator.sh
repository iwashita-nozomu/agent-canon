#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Validates Docker dependency declarations in repository tooling.
# upstream design README.md shared automation index
# upstream design ../CONTAINER_OPERATIONS.md canonical Docker and devcontainer ownership boundary
# upstream design ../documents/rust-agent-tool-migration.md Rust toolchain and AgentCanon CLI migration boundary
# upstream environment ../documents/linux-wsl-host-requirements.md documents canonical host tool inventory
# @dependency-end

set -euo pipefail

issues=0
has_docker_surface=0
has_devcontainer_surface=0
if [ -f "vendor/agent-canon/CONTAINER_OPERATIONS.md" ]; then
  rulebook="vendor/agent-canon/CONTAINER_OPERATIONS.md"
else
  rulebook="CONTAINER_OPERATIONS.md"
fi

if [ -d docker ]; then
  has_docker_surface=1
fi
if [ -d .devcontainer ]; then
  has_devcontainer_surface=1
fi

printf 'Docker/development-container rulebook: %s\n' "$rulebook"

report_issue() {
  printf '   \342\235\214 %s\n' "$1"
  issues=$((issues + 1))
}

report_warning() {
  printf '   \342\232\240\357\270\217 %s\n' "$1"
  issues=$((issues + 1))
}

trim_line() {
  local line="$1"
  line="${line%%#*}"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  printf '%s' "$line"
}

check_requirements_format() {
  local req_file="docker/requirements.txt"
  local line_num=0
  local line=""
  local trimmed=""

  printf '1. Checking requirements.txt format...\n'
  if [ "$has_docker_surface" -eq 0 ]; then
    printf '   docker/ absent; skipping repo-local requirements format\n'
    return
  fi
  if [ ! -f "$req_file" ]; then
    report_issue "docker/requirements.txt not found"
    return
  fi

  while IFS= read -r line || [ -n "$line" ]; do
    line_num=$((line_num + 1))
    trimmed="$(trim_line "$line")"
    [ -n "$trimmed" ] || continue
    if [[ ! "$trimmed" =~ ^[A-Za-z0-9_.-]+(\[[A-Za-z0-9_,.-]+\])?([[:space:]]*(==|>=|<=|~=|!=|>|<).+)?$ ]]; then
      report_issue "Line ${line_num}: invalid requirement syntax: ${trimmed}"
    fi
  done < "$req_file"
}

check_dockerfile_coherence() {
  local dockerfile="docker/Dockerfile"

  printf '\n2. Checking Dockerfile coherence...\n'
  if [ "$has_docker_surface" -eq 0 ]; then
    printf '   docker/ absent; skipping repo-local Dockerfile coherence\n'
    return
  fi
  if [ ! -f "$dockerfile" ]; then
    report_issue "docker/Dockerfile not found"
    return
  fi

  if grep -Eiq 'pip[[:space:]]+install.*-r[[:space:]]+[^[:space:]]*requirements\.txt' "$dockerfile"; then
    report_issue "docker/Dockerfile must not install Python requirements; use devcontainer post-create setup"
  fi
  if grep -q 'COPY docker/requirements.txt' "$dockerfile"; then
    report_issue "docker/Dockerfile must not copy docker/requirements.txt into the image build"
  fi
  grep -Eq '(^|[[:space:]])rsync([[:space:]]|\\|$)' "$dockerfile" \
    || report_issue "docker/Dockerfile must install rsync so fresh-clone overlay works in the canonical container"
  grep -q 'openssh-client' "$dockerfile" \
    || report_issue "docker/Dockerfile must install openssh-client so GitHub SSH and agent forwarding work"
  grep -Eq '(^|[[:space:]])graphviz([[:space:]]|\\|$)' "$dockerfile" \
    || report_issue "docker/Dockerfile must install graphviz so result/dependency graphs can render"
  ! grep -q 'cli.github.com/packages' "$dockerfile" \
    || report_issue "docker/Dockerfile must not configure GitHub CLI; shared devcontainer post-create owns gh setup"
  ! grep -Eq '(^|[[:space:]])gh([[:space:]]|\\|$)' "$dockerfile" \
    || report_issue "docker/Dockerfile must not install gh; shared devcontainer post-create owns gh setup"
  ! grep -q 'gh --version' "$dockerfile" \
    || report_issue "docker/Dockerfile must not smoke-check gh; shared devcontainer post-create owns gh setup"
  ! grep -q '@openai/codex' "$dockerfile" \
    || report_issue "docker/Dockerfile must not install Codex CLI; shared devcontainer post-create owns Codex setup"
  ! grep -q 'codex --version' "$dockerfile" \
    || report_issue "docker/Dockerfile must not smoke-check Codex CLI; shared devcontainer post-create owns Codex setup"
  ! grep -Eq '(^|[^[:alnum:]_])rustup([^[:alnum:]_]|$)' "$dockerfile" \
    || report_issue "docker/Dockerfile must not install rustup; shared devcontainer post-create owns AgentCanon Rust setup"
  ! grep -Eq '(^|[^[:alnum:]_])cargo[[:space:]]+(build|install|test|clippy|fmt)([^[:alnum:]_]|$)' "$dockerfile" \
    || report_issue "docker/Dockerfile must not run cargo for AgentCanon tooling; shared devcontainer post-create owns Rust setup"
  ! grep -Eq '(^|[^[:alnum:]_])rustc[[:space:]]+--version([^[:alnum:]_]|$)' "$dockerfile" \
    || report_issue "docker/Dockerfile must not smoke-check rustc for AgentCanon tooling; shared devcontainer post-create owns Rust setup"
}

check_post_create_python_install() {
  local post_create=".devcontainer/post-create.sh"
  local generate_compose=".devcontainer/generate-runtime-compose.sh"
  local installer="docker/install_python_dependencies.sh"
  local devcontainer=".devcontainer/devcontainer.json"
  local post_attach=".devcontainer/post-attach.sh"

  printf '\n3. Checking post-create Python dependency setup...\n'
  if [ "$has_devcontainer_surface" -eq 0 ]; then
    printf '   .devcontainer/ absent; skipping shared devcontainer checks\n'
    return
  elif [ "$has_docker_surface" -eq 0 ]; then
    printf '   docker/ absent; checking shared devcontainer source only\n'
  fi
  if [ ! -f "$post_create" ]; then
    report_issue ".devcontainer/post-create.sh not found"
  else
    grep -q 'run_as_root' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must route privileged setup through run_as_root"
    grep -q 'docker/register_safe_directories.sh' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must register safe directories"
    grep -q 'docker/install_python_dependencies.sh' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must run the Python dependency installer"
    grep -q 'git config --global --add safe.directory "$workspace"' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must provide standalone safe.directory route"
    grep -q 'repo-local Python dependency installer absent' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must skip missing repo-local Python installer"
    grep -q 'cli.github.com/packages' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must configure the GitHub CLI apt repository"
    grep -q 'apt_install gh' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must install gh"
    grep -q 'npm install -g @openai/codex' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must install the Codex CLI"
    grep -q 'gh --version' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must smoke-check gh"
    grep -q 'codex --version' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must smoke-check Codex CLI"
    grep -q 'rustup toolchain install' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must install the Rust toolchain"
    grep -q 'rustfmt' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must install rustfmt"
    grep -q 'clippy' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must install clippy"
    grep -q 'rust-analyzer' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must install rust-analyzer"
    grep -q 'cargo build --release' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must build the AgentCanon Rust CLI"
    grep -q 'AGENT_CANON_TOOLS_HOME' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must define AGENT_CANON_TOOLS_HOME"
    grep -q '${tools_home}/agent-canon/bin/agent-canon' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must install the AgentCanon Rust CLI under AGENT_CANON_TOOLS_HOME"
    grep -q '/usr/local/bin/agent-canon' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must expose the AgentCanon Rust CLI on PATH"
    grep -q 'install_llama_cpp' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must install llama.cpp for local single-file responsibility review"
    grep -q 'tools/install_llama_cpp.sh' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must call the shared llama.cpp installer"
    grep -q 'ggml-org/SmolLM3-3B-GGUF:Q4_K_M' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must set the default 3B-class local LLM model selector"
    grep -q '${tools_home}/bin/llama-cli' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must expose llama-cli under AGENT_CANON_TOOLS_HOME"
    if [ ! -f tools/install_llama_cpp.sh ]; then
      report_issue "tools/install_llama_cpp.sh not found"
    else
      grep -q 'ggml-org/llama.cpp' tools/install_llama_cpp.sh \
        || report_issue "tools/install_llama_cpp.sh must fetch llama.cpp from its canonical repository"
      grep -q 'cmake --build' tools/install_llama_cpp.sh \
        || report_issue "tools/install_llama_cpp.sh must build llama.cpp"
    fi
    grep -q '/etc/profile.d/agent-canon-rust.sh' "$post_create" \
      || report_issue ".devcontainer/post-create.sh must publish Rust PATH for non-interactive devcontainer exec"
  fi

  if [ "$has_docker_surface" -eq 0 ]; then
    if [ ! -f "$devcontainer" ]; then
      report_issue ".devcontainer/devcontainer.json not found"
    else
      grep -q '"postCreateCommand": "bash .devcontainer/post-create.sh /workspace"' "$devcontainer" \
        || report_issue "devcontainer postCreateCommand must call .devcontainer/post-create.sh"
      grep -q '"postAttachCommand": "bash .devcontainer/post-attach.sh"' "$devcontainer" \
        || report_issue "devcontainer postAttachCommand must call .devcontainer/post-attach.sh"
    fi
    if [ ! -f "$generate_compose" ]; then
      report_issue ".devcontainer/generate-runtime-compose.sh not found"
    else
      grep -q 'agent-canon-source-only' "$generate_compose" \
        || report_issue ".devcontainer/generate-runtime-compose.sh must support standalone AgentCanon source-only mode"
      grep -q 'mcr.microsoft.com/devcontainers/base:ubuntu-22.04' "$generate_compose" \
        || report_issue ".devcontainer/generate-runtime-compose.sh must provide a standalone base image"
      grep -q 'AGENT_CANON_SECRET_DIR' "$generate_compose" \
        || report_issue ".devcontainer/generate-runtime-compose.sh must support optional host secret directory mounts"
      grep -q 'AGENT_CANON_SECRET_MOUNT' "$generate_compose" \
        || report_issue ".devcontainer/generate-runtime-compose.sh must expose the optional secret mount target"
    fi
    if [ ! -f "$post_attach" ]; then
      report_issue ".devcontainer/post-attach.sh not found"
    fi
    return
  fi

  if [ ! -f "$installer" ]; then
    report_issue "docker/install_python_dependencies.sh not found"
  else
    grep -q 'docker/requirements.txt' "$installer" \
      || report_issue "docker/install_python_dependencies.sh must read docker/requirements.txt"
    grep -Eiq 'python3[[:space:]]+-m[[:space:]]+pip[[:space:]]+install[[:space:]]+--no-cache-dir[[:space:]]+-r' "$installer" \
      || report_issue "docker/install_python_dependencies.sh must install docker/requirements.txt with pip -r"
    grep -q 'sha256sum' "$installer" \
      || report_issue "docker/install_python_dependencies.sh must be idempotent with a requirements hash"
    grep -q 'python3 -m pip check' "$installer" \
      || report_issue "docker/install_python_dependencies.sh must run pip check"
  fi

  if [ ! -f "$devcontainer" ]; then
    report_issue ".devcontainer/devcontainer.json not found"
  else
    grep -q '"postCreateCommand": "bash .devcontainer/post-create.sh /workspace"' "$devcontainer" \
      || report_issue "devcontainer postCreateCommand must call .devcontainer/post-create.sh"
  fi
}

check_docker_build_context_isolation() {
  local dockerignore=".dockerignore"

  printf '\n4. Checking Docker build context isolation...\n'
  if [ "$has_docker_surface" -eq 0 ]; then
    printf '   docker/ absent; skipping repo-local build context isolation\n'
    return
  fi
  if [ ! -f "$dockerignore" ]; then
    report_issue ".dockerignore not found"
    return
  fi

  grep -Fxq 'vendor/agent-canon' "$dockerignore" \
    || report_issue ".dockerignore must exclude vendor/agent-canon from template Docker build context"
  grep -Fxq '.git' "$dockerignore" \
    || report_issue ".dockerignore must exclude .git from template Docker build context"
  grep -Fxq '.state' "$dockerignore" \
    || report_issue ".dockerignore must exclude .state so local model caches stay out of Docker build context"
  grep -Fxq '*.gguf' "$dockerignore" \
    || report_issue ".dockerignore must exclude GGUF model artifacts from Docker build context"
}

check_result_visualization_requirements() {
  local req_file="docker/requirements.txt"
  local requirement=""
  local missing=0

  printf '\n5. Checking result-log and visualization requirements...\n'
  if [ "$has_docker_surface" -eq 0 ]; then
    printf '   docker/ absent; skipping repo-local result-log requirements\n'
    return
  fi
  if [ ! -f "$req_file" ]; then
    report_issue "docker/requirements.txt not found"
    return
  fi

  for requirement in jupyterlab notebook ipykernel pydeps snakeviz pyyaml; do
    if ! grep -Eiq "^${requirement}(\\[[^]]+\\])?([<>=~![:space:]]|$)" "$req_file"; then
      report_issue "docker/requirements.txt must include ${requirement}"
      missing=1
    fi
  done

  [ "$missing" -eq 0 ] && printf '   result-log / visualization requirements present\n'
}

check_python_dependency_manifest_contract() {
  local validator="tools/requirement_sync_validator.py"
  local output_file=""

  printf '\n6. Checking pyproject/docker dependency contract...\n'
  if [ "$has_docker_surface" -eq 0 ]; then
    printf '   docker/ absent; skipping repo-local dependency manifest contract\n'
    return
  fi
  if [ ! -f "pyproject.toml" ]; then
    report_issue "pyproject.toml not found"
    return
  fi
  if [ ! -f "$validator" ]; then
    report_issue "requirement sync validator missing: $validator"
    return
  fi

  output_file="$(mktemp)"
  if python3 "$validator" >"$output_file" 2>&1; then
    grep -E '^(PYPROJECT_|DOCKER_REQUIREMENTS_)' "$output_file" || true
  else
    cat "$output_file"
    report_issue "pyproject/docker dependency contract failed"
  fi
  rm -f "$output_file"
}

is_container_runtime() {
  [ -f "/.dockerenv" ] || [ -f "/run/.containerenv" ] || [ -n "${container:-}" ] || [ -n "${DEVCONTAINER_RUNTIME_MODE:-}" ]
}

check_repo_local_venv_policy() {
  local gitignore=".gitignore"
  local path=""
  local match_file=""
  local roots=()
  local root=""
  local pattern='python3?[[:space:]]+-m[[:space:]]+venv|virtualenv|conda[[:space:]]+create|uv[[:space:]]+venv|pipenv|poetry[[:space:]]+env'
  local canonical_tool="tools/ci/python_env_policy.py"

  printf '\n7. Checking repo-local virtual-environment policy...\n'

  for path in venv env .conda conda-env .venv-*; do
    if [ -e "$path" ]; then
      report_issue "non-canonical virtual-environment directory exists: $path"
    fi
  done

  if is_container_runtime; then
    :
  elif [ -e ".venv" ]; then
    report_issue "host runtime must not keep repo-local .venv; use the canonical container runtime instead"
  fi

  if [ -f "$gitignore" ]; then
    grep -Eq '(^|/)\.venv/|^\.venv/' "$gitignore" \
      || report_issue ".venv/ is not explicitly excluded in .gitignore"
    grep -Eq '(^|/)venv/|^venv/' "$gitignore" \
      || report_issue "venv/ is not explicitly excluded in .gitignore"
  else
    report_issue ".gitignore not found"
  fi

  if [ ! -f "$canonical_tool" ]; then
    report_issue "canonical env-policy tool missing: $canonical_tool"
  fi

  if [ -f docker/Dockerfile ] && ! grep -q 'python3.11-venv' docker/Dockerfile; then
    report_issue "docker/Dockerfile must install python3.11-venv so the canonical container can create .venv"
  fi

  for root in scripts tools Makefile .github; do
    [ -e "$root" ] && roots+=("$root")
  done
  [ "${#roots[@]}" -gt 0 ] || return

  while IFS= read -r match_file; do
    case "$match_file" in
      */__pycache__/*|*.pyc|*/docker_dependency_validator.sh|*/python_env_policy.py)
        continue
        ;;
    esac
    report_issue "non-canonical virtual-environment creation command found in ${match_file}"
  done < <(
    grep -RIlE "$pattern" "${roots[@]}" 2>/dev/null \
      | sort -u
  )
}

check_pythonpath_documentation() {
  local documented=0
  local docker_documented=0
  local file=""

  printf '\n8. Checking PYTHONPATH and Docker documentation...\n'
  if [ "$has_docker_surface" -eq 0 ]; then
    printf '   docker/ absent; skipping repo-local Docker documentation checks\n'
    return
  fi
  for file in README.md QUICK_START.md documents/coding-conventions-project.md; do
    [ -f "$file" ] || continue
    if grep -q 'PYTHONPATH' "$file" && grep -q '=/workspace/python' "$file"; then
      documented=1
    fi
    if grep -Eiq 'docker (run|build)' "$file"; then
      docker_documented=1
    fi
  done

  [ "$documented" -eq 1 ] \
    || report_warning "PYTHONPATH=/workspace/python not documented in README/QUICK_START"
  [ "$docker_documented" -eq 1 ] \
    || report_warning "Docker execution instructions not found in README/QUICK_START"
}

printf 'Checking Docker environment consistency without Python-dependent tooling...\n\n'
check_requirements_format
check_dockerfile_coherence
check_post_create_python_install
check_docker_build_context_isolation
check_result_visualization_requirements
check_python_dependency_manifest_contract
check_repo_local_venv_policy
check_pythonpath_documentation

printf '\nSummary: %s issues found\n' "$issues"
[ "$issues" -eq 0 ]
