#!/usr/bin/env bash
# @dependency-start
# responsibility Runs shared devcontainer post-create setup after workspace mount.
# upstream design ../documents/github-first-module-and-devcontainer-policy.md devcontainer boundary
# upstream environment devcontainer.json postCreateCommand entrypoint
# @dependency-end

set -euo pipefail

workspace="${1:-/workspace}"
node_version="${NODE_VERSION:-22.14.0}"

run_as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
    return
  fi
  if command -v sudo >/dev/null 2>&1; then
    sudo "$@"
    return
  fi
  echo "post-create requires root or sudo for package installation: $*" >&2
  exit 1
}

apt_install() {
  run_as_root apt-get update
  run_as_root apt-get install -y --no-install-recommends "$@"
}

install_node_for_codex() {
  local archive
  if command -v npm >/dev/null 2>&1; then
    return
  fi
  apt_install ca-certificates curl xz-utils
  archive="$(mktemp)"
  curl -fsSL "https://nodejs.org/dist/v${node_version}/node-v${node_version}-linux-x64.tar.xz" \
    -o "$archive"
  run_as_root tar -xJ --strip-components=1 -C /usr/local -f "$archive"
  rm -f "$archive"
}

install_github_cli() {
  local keyring
  if command -v gh >/dev/null 2>&1; then
    return
  fi
  apt_install ca-certificates curl
  keyring="$(mktemp)"
  run_as_root install -d -m 755 /etc/apt/keyrings
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    -o "$keyring"
  run_as_root install -m 644 "$keyring" /etc/apt/keyrings/githubcli-archive-keyring.gpg
  rm -f "$keyring"
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\n' "$(dpkg --print-architecture)" \
    | run_as_root tee /etc/apt/sources.list.d/github-cli.list >/dev/null
  apt_install gh
}

install_codex_cli() {
  if command -v codex >/dev/null 2>&1; then
    return
  fi
  install_node_for_codex
  run_as_root env "PATH=${PATH}" npm install -g @openai/codex
  run_as_root env "PATH=${PATH}" npm cache clean --force
}

if [ -f "${workspace%/}/docker/register_safe_directories.sh" ]; then
  bash "${workspace%/}/docker/register_safe_directories.sh" "$workspace"
else
  git config --global --add safe.directory "$workspace" || true
fi
if [ -f "${workspace%/}/docker/install_python_dependencies.sh" ]; then
  bash "${workspace%/}/docker/install_python_dependencies.sh" "$workspace"
else
  echo "repo-local Python dependency installer absent; skipping docker/install_python_dependencies.sh"
fi
install_github_cli
install_codex_cli
gh --version
codex --version
