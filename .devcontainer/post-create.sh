#!/usr/bin/env bash
# @dependency-start
# responsibility Runs shared devcontainer post-create setup after workspace mount.
# upstream design ../documents/github-first-module-and-devcontainer-policy.md devcontainer boundary
# upstream design ../documents/rust-agent-tool-migration.md Rust toolchain and CLI install boundary
# upstream environment devcontainer.json postCreateCommand entrypoint
# @dependency-end

set -euo pipefail

workspace="${1:-/workspace}"
node_version="${NODE_VERSION:-22.14.0}"
rust_toolchain="${RUST_TOOLCHAIN:-stable}"

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

agent_canon_source_root() {
  if [ -f "${workspace%/}/vendor/agent-canon/rust/agent-canon/Cargo.toml" ]; then
    printf '%s\n' "${workspace%/}/vendor/agent-canon"
    return
  fi
  if [ -f "${workspace%/}/rust/agent-canon/Cargo.toml" ]; then
    printf '%s\n' "${workspace%/}"
    return
  fi
  printf '%s\n' ""
}

install_rust_toolchain() {
  local profile_script
  local tool

  export CARGO_HOME="${CARGO_HOME:-${HOME}/.cargo}"
  export RUSTUP_HOME="${RUSTUP_HOME:-${HOME}/.rustup}"
  export PATH="${CARGO_HOME}/bin:${PATH}"

  if ! command -v rustup >/dev/null 2>&1; then
    apt_install ca-certificates curl build-essential pkg-config
    curl -fsSL https://sh.rustup.rs \
      | sh -s -- -y --profile minimal --default-toolchain "${rust_toolchain}" --no-modify-path
  fi

  rustup toolchain install "${rust_toolchain}" --profile minimal
  rustup default "${rust_toolchain}"
  rustup component add rustfmt clippy rust-analyzer --toolchain "${rust_toolchain}"

  profile_script="$(mktemp)"
  cat >"$profile_script" <<EOF
export CARGO_HOME="${CARGO_HOME}"
export RUSTUP_HOME="${RUSTUP_HOME}"
case ":\${PATH}:" in
  *:"${CARGO_HOME}/bin":*) ;;
  *) export PATH="${CARGO_HOME}/bin:\${PATH}" ;;
esac
EOF
  run_as_root install -m 644 "$profile_script" /etc/profile.d/agent-canon-rust.sh
  rm -f "$profile_script"

  for tool in cargo rustc rustup rustfmt rust-analyzer cargo-clippy clippy-driver; do
    if [ -x "${CARGO_HOME}/bin/${tool}" ]; then
      run_as_root ln -sf "${CARGO_HOME}/bin/${tool}" "/usr/local/bin/${tool}"
    fi
  done

  cargo --version
  rustc --version
}

install_agent_canon_cli() {
  local canon_root
  local manifest
  local binary

  canon_root="$(agent_canon_source_root)"
  if [ -z "$canon_root" ]; then
    echo "AgentCanon Rust CLI source absent; skipping rust/agent-canon build"
    return
  fi

  install_rust_toolchain
  manifest="${canon_root}/rust/agent-canon/Cargo.toml"
  cargo build --release --manifest-path "$manifest"
  binary="${canon_root}/rust/agent-canon/target/release/agent-canon"

  run_as_root install -d -m 755 /opt/agent-canon/bin
  run_as_root install -m 755 "$binary" /opt/agent-canon/bin/agent-canon
  run_as_root ln -sf /opt/agent-canon/bin/agent-canon /usr/local/bin/agent-canon
  /usr/local/bin/agent-canon --version
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
install_agent_canon_cli
gh --version
codex --version
