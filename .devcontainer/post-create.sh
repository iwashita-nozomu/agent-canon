#!/usr/bin/env bash
# @dependency-start
# responsibility Runs shared devcontainer post-create setup after workspace mount.
# upstream design ../documents/github-first-module-and-devcontainer-policy.md devcontainer boundary
# upstream design ../documents/rust-agent-tool-migration.md Rust toolchain and CLI install boundary
# upstream environment devcontainer.json postCreateCommand entrypoint
# upstream implementation ../tools/install_llama_cpp.sh builds llama.cpp local LLM tooling
# upstream implementation ../tools/ci/scan_secrets.sh runs dedicated secret scanners
# @dependency-end

set -euo pipefail

workspace="${1:-/workspace}"
node_version="${NODE_VERSION:-22.14.0}"
rust_toolchain="${RUST_TOOLCHAIN:-stable}"
tools_home="${AGENT_CANON_TOOLS_HOME:-${HOME}/.tools}"
llama_cpp_ref="${AGENT_CANON_LLAMA_CPP_REF:-master}"
local_llm_model="${AGENT_CANON_LOCAL_LLM_MODEL:-ggml-org/SmolLM3-3B-GGUF:Q4_K_M}"
gitleaks_version="${AGENT_CANON_GITLEAKS_VERSION:-8.30.1}"
trufflehog_version="${AGENT_CANON_TRUFFLEHOG_VERSION:-3.95.3}"
detect_secrets_version="${AGENT_CANON_DETECT_SECRETS_VERSION:-1.5.0}"

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

publish_agent_tools_profile() {
  local profile_script

  install -d -m 755 "${tools_home}/bin"
  profile_script="$(mktemp)"
  cat >"$profile_script" <<EOF
export AGENT_CANON_TOOLS_HOME="${tools_home}"
export AGENT_CANON_LOCAL_LLM_MODEL="${local_llm_model}"
export AGENT_CANON_LLAMA_CLI="${tools_home}/bin/llama-cli"
case ":\${PATH}:" in
  *:"${tools_home}/bin":*) ;;
  *) export PATH="${tools_home}/bin:\${PATH}" ;;
esac
EOF
  run_as_root install -m 644 "$profile_script" /etc/profile.d/agent-canon-tools.sh
  rm -f "$profile_script"
  export PATH="${tools_home}/bin:${PATH}"
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

linux_arch() {
  case "$(uname -m)" in
    x86_64 | amd64)
      printf '%s\n' "amd64"
      ;;
    aarch64 | arm64)
      printf '%s\n' "arm64"
      ;;
    *)
      echo "Unsupported secret scanner architecture: $(uname -m)" >&2
      return 1
      ;;
  esac
}

download_release_asset() {
  local repo="$1"
  local tag="$2"
  local asset="$3"
  local output="$4"
  curl -fsSL "https://github.com/${repo}/releases/download/${tag}/${asset}" -o "$output"
}

verify_release_checksum() {
  local repo="$1"
  local tag="$2"
  local asset="$3"
  local archive="$4"
  local checksum_file
  local checksum_asset
  local work_dir

  work_dir="$(dirname "$archive")"
  checksum_file="${work_dir}/checksums.txt"
  checksum_asset="${asset%%_linux_*}_checksums.txt"
  curl -fsSL "https://github.com/${repo}/releases/download/${tag}/${checksum_asset}" \
    -o "$checksum_file"
  if ! grep -F "  $(basename "$archive")" "$checksum_file" >/dev/null 2>&1; then
    echo "Checksum entry for $(basename "$archive") not found in ${repo} ${tag}" >&2
    return 1
  fi
  (cd "$work_dir" && grep -F "  $(basename "$archive")" checksums.txt | sha256sum -c -)
}

install_tar_binary() {
  local repo="$1"
  local tag="$2"
  local asset="$3"
  local binary="$4"
  local archive
  local work_dir

  work_dir="$(mktemp -d)"
  archive="${work_dir}/${asset}"
  download_release_asset "$repo" "$tag" "$asset" "$archive"
  verify_release_checksum "$repo" "$tag" "$asset" "$archive"
  tar -xzf "$archive" -C "$work_dir" "$binary"
  install -d -m 755 "${tools_home}/bin"
  install -m 755 "${work_dir}/${binary}" "${tools_home}/bin/${binary}"
  run_as_root ln -sf "${tools_home}/bin/${binary}" "/usr/local/bin/${binary}"
  rm -rf "$work_dir"
}

install_detect_secrets() {
  local detector

  if command -v detect-secrets >/dev/null 2>&1; then
    return
  fi
  apt_install python3-pip
  PIP_BREAK_SYSTEM_PACKAGES=1 python3 -m pip install --user --upgrade "detect-secrets==${detect_secrets_version}"
  detector="${HOME}/.local/bin/detect-secrets"
  if [ ! -x "$detector" ]; then
    echo "detect-secrets install completed but ${detector} is missing" >&2
    return 1
  fi
  install -d -m 755 "${tools_home}/bin"
  ln -sf "$detector" "${tools_home}/bin/detect-secrets"
  run_as_root ln -sf "${tools_home}/bin/detect-secrets" /usr/local/bin/detect-secrets
}

install_secret_scanners() {
  local arch
  local gitleaks_arch

  apt_install ca-certificates curl tar
  arch="$(linux_arch)"
  if [ "$arch" = "amd64" ]; then
    gitleaks_arch="x64"
  else
    gitleaks_arch="$arch"
  fi

  if ! command -v gitleaks >/dev/null 2>&1; then
    install_tar_binary \
      "gitleaks/gitleaks" \
      "v${gitleaks_version}" \
      "gitleaks_${gitleaks_version}_linux_${gitleaks_arch}.tar.gz" \
      "gitleaks"
  fi
  if ! command -v trufflehog >/dev/null 2>&1; then
    install_tar_binary \
      "trufflesecurity/trufflehog" \
      "v${trufflehog_version}" \
      "trufflehog_${trufflehog_version}_linux_${arch}.tar.gz" \
      "trufflehog"
  fi
  install_detect_secrets

  gitleaks version
  trufflehog --version
  detect-secrets --version
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

  install -d -m 755 "${tools_home}/agent-canon/bin" "${tools_home}/bin"
  install -m 755 "$binary" "${tools_home}/agent-canon/bin/agent-canon"
  ln -sf "${tools_home}/agent-canon/bin/agent-canon" "${tools_home}/bin/agent-canon"
  run_as_root ln -sf "${tools_home}/bin/agent-canon" /usr/local/bin/agent-canon
  /usr/local/bin/agent-canon --version
}

install_llama_cpp() {
  local canon_root
  local installer

  apt_install ca-certificates curl git cmake build-essential pkg-config libcurl4-openssl-dev
  canon_root="$(agent_canon_source_root)"
  installer="${canon_root}/tools/install_llama_cpp.sh"
  if [ -z "$canon_root" ] || [ ! -f "$installer" ]; then
    echo "AgentCanon llama.cpp installer absent; skipping local LLM tool install"
    return
  fi
  AGENT_CANON_TOOLS_HOME="$tools_home" \
    AGENT_CANON_LLAMA_CPP_REF="$llama_cpp_ref" \
    bash "$installer" --allow-fetch
}

publish_agent_tools_profile
if [ -f "${workspace%/}/docker/register_safe_directories.sh" ]; then
  bash "${workspace%/}/docker/register_safe_directories.sh" "$workspace"
else
  git config --global --add safe.directory "$workspace" || true
  if [ -d "${workspace%/}/.git" ]; then
    git config --global --add safe.directory "${workspace%/}/.git" || true
  fi
fi
if [ -f "${workspace%/}/docker/install_python_dependencies.sh" ]; then
  bash "${workspace%/}/docker/install_python_dependencies.sh" "$workspace"
else
  echo "repo-local Python dependency installer absent; skipping docker/install_python_dependencies.sh"
fi
install_github_cli
install_codex_cli
install_secret_scanners
install_agent_canon_cli
install_llama_cpp
gh --version
codex --version
