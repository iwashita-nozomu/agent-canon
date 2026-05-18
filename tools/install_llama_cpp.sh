#!/usr/bin/env bash
# @dependency-start
# responsibility Builds and exposes llama.cpp for AgentCanon local LLM tools.
# upstream design ../CONTAINER_OPERATIONS.md compiled tool cache and devcontainer boundary.
# upstream design ../documents/local-llm-responsibility-analysis.md local LLM single-file policy.
# downstream environment ../.devcontainer/post-create.sh installs llama.cpp after workspace mount.
# downstream implementation ./rebuild_agent_tools.sh rebuilds llama.cpp after AgentCanon updates.
# downstream implementation ../tests/tools/test_install_llama_cpp.py validates installer behavior.
# @dependency-end

set -euo pipefail

TOOLS_HOME="${AGENT_CANON_TOOLS_HOME:-${HOME}/.tools}"
LLAMA_CPP_REF="${AGENT_CANON_LLAMA_CPP_REF:-master}"
FORCE_REBUILD="${AGENT_CANON_REBUILD_LLAMA_CPP:-0}"
ALLOW_FETCH=0
SKIP_MISSING_SOURCE=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --allow-fetch)
      ALLOW_FETCH=1
      shift
      ;;
    --skip-missing-source)
      SKIP_MISSING_SOURCE=1
      shift
      ;;
    --force)
      FORCE_REBUILD=1
      shift
      ;;
    *)
      echo "AGENT_CANON_LLAMA_CPP=fail"
      echo "AGENT_CANON_LLAMA_CPP_ERROR=unknown_argument:$1"
      exit 2
      ;;
  esac
done

missing_build_tool() {
  local tool
  for tool in git cmake; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "AGENT_CANON_LLAMA_CPP=skipped_missing_dependency"
      echo "AGENT_CANON_LLAMA_CPP_MISSING=$tool"
      return 0
    fi
  done
  return 1
}

llama_sources_newer_than_binary() {
  local source_dir="$1"
  local binary="$2"
  if [ ! -x "$binary" ]; then
    return 0
  fi
  find "$source_dir" \
    \( -name '*.c' -o -name '*.cc' -o -name '*.cpp' -o -name '*.h' -o -name '*.hpp' -o -name 'CMakeLists.txt' \) \
    -newer "$binary" -print -quit
}

main() {
  local source_dir
  local build_dir
  local install_dir
  local source_newer
  local jobs

  echo "AGENT_CANON_LLAMA_CPP_TOOLS_HOME=$TOOLS_HOME"
  echo "AGENT_CANON_LLAMA_CPP_REF=$LLAMA_CPP_REF"
  if missing_build_tool; then
    return 0
  fi

  source_dir="${TOOLS_HOME}/src/llama.cpp"
  build_dir="${TOOLS_HOME}/build/llama.cpp"
  install_dir="${TOOLS_HOME}/bin"
  install -d -m 755 "${TOOLS_HOME}/src" "${TOOLS_HOME}/build" "$install_dir"

  if [ ! -d "${source_dir}/.git" ]; then
    if [ "$ALLOW_FETCH" != "1" ] || [ "$SKIP_MISSING_SOURCE" = "1" ]; then
      echo "AGENT_CANON_LLAMA_CPP=skipped_missing_source"
      echo "AGENT_CANON_LLAMA_CPP_NEXT=run_devcontainer_post_create_or_set_AGENT_CANON_LLAMA_CPP_ALLOW_FETCH"
      return 0
    fi
    git clone --depth 1 --branch "$LLAMA_CPP_REF" https://github.com/ggml-org/llama.cpp.git "$source_dir"
  elif [ "$ALLOW_FETCH" = "1" ]; then
    git -C "$source_dir" fetch --depth 1 origin "$LLAMA_CPP_REF"
    git -C "$source_dir" checkout --detach FETCH_HEAD
  fi

  source_newer="$(llama_sources_newer_than_binary "$source_dir" "${install_dir}/llama-cli")"
  if [ "$FORCE_REBUILD" != "1" ] && [ -x "${install_dir}/llama-cli" ] && [ -x "${install_dir}/llama-server" ] && [ -z "$source_newer" ]; then
    "${install_dir}/llama-cli" --help >/dev/null
    echo "AGENT_CANON_LLAMA_CPP=already_current"
    return 0
  fi

  cmake -S "$source_dir" -B "$build_dir" -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=ON
  jobs="$(nproc 2>/dev/null || printf '%s\n' 2)"
  cmake --build "$build_dir" --config Release -j "$jobs" --target llama-cli llama-server
  ln -sf "${build_dir}/bin/llama-cli" "${install_dir}/llama-cli"
  ln -sf "${build_dir}/bin/llama-server" "${install_dir}/llama-server"
  "${install_dir}/llama-cli" --help >/dev/null
  echo "AGENT_CANON_LLAMA_CPP=rebuilt"
}

main "$@"
