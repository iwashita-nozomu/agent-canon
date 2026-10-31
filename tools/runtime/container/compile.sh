#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Compiles every source-mounted Rust tool into the external runtime cache.
# upstream design ../../../documents/design/agent-canon-bootstrap-tool-runtime.md source-mounted tool build
# downstream implementation ../../../bootstrap/container/dispatch/tool-wrapper.sh cached tool dispatch
# downstream test ../../../tests/tools/test_compile_cache.py verifies the seeded registry-index merge
# @dependency-end

_refresh_seeded_registry_index() (
    set -euo pipefail
    local seed_index="${1:?seed registry index is required}"
    local destination_index="${2:?persistent registry index is required}"
    [[ -d "$seed_index" ]] || exit 0
    mkdir -p -- "$destination_index"

    local find_fd find_pid seed_file relative destination_file destination_directory
    local temporary_file=""
    trap '[[ -z "$temporary_file" ]] || rm -f -- "$temporary_file" || true' EXIT
    trap 'exit 1' HUP INT TERM

    exec {find_fd}< <(find "$seed_index" -type f -print0)
    find_pid=$!
    while IFS= read -r -d '' seed_file <&"$find_fd"; do
        relative=${seed_file#"$seed_index"/}
        destination_file="$destination_index/$relative"
        destination_directory=${destination_file%/*}
        mkdir -p -- "$destination_directory"
        temporary_file="$(mktemp "${destination_file}.tmp.XXXXXX")"
        if ! cp --preserve=mode -- "$seed_file" "$temporary_file"; then
            exit 1
        fi
        if ! mv -f -- "$temporary_file" "$destination_file"; then
            exit 1
        fi
        temporary_file=""
    done
    exec {find_fd}<&-
    wait "$find_pid"
)

main() {
    set -euo pipefail

    local source_root=${AGENT_CANON_SOURCE_ROOT:-/opt/agent-canon/source}
    local cache_root=${AGENT_CANON_CACHE_ROOT:-/var/lib/agent-canon/cache}
    local cargo_target_dir=${CARGO_TARGET_DIR:-${AGENT_CANON_CARGO_TARGET_DIR:-$cache_root/cargo-target}}
    local cargo_home=${CARGO_HOME:-$cache_root/cargo}
    local seed_cargo_home=/usr/local/share/agent-canon/toolchains/cargo

    mkdir -p -- "$cache_root" "$cargo_target_dir" "$cargo_home"
    if [[ -d "$seed_cargo_home" ]]; then
        cp -R --update=none -- "$seed_cargo_home/." "$cargo_home/"
        _refresh_seeded_registry_index \
            "$seed_cargo_home/registry/index" \
            "$cargo_home/registry/index"
    fi

    shopt -s globstar nullglob
    local -a manifests=("$source_root"/tools/**/Cargo.toml)
    local manifest
    for manifest in "${manifests[@]}"; do
        cargo install \
            --path "${manifest%/Cargo.toml}" \
            --root "$cache_root" \
            --target-dir "$cargo_target_dir" \
            --locked \
            --force \
            --offline
    done
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
