#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Seeds writable Cargo archives and index from the shared image.
# upstream design ../../../documents/design/agent-canon-bootstrap-tool-runtime.md offline Rust dependency support
# downstream implementation ../../../bootstrap/container/lifecycle/entrypoint.sh activation route
# downstream test ../../../tests/tools/test_seed_cargo_cache.py verifies the seeded registry-index merge
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

    local cache_root=${AGENT_CANON_CACHE_ROOT:-/var/lib/agent-canon/cache}
    local cargo_home=${CARGO_HOME:-$cache_root/cargo}
    local seed_registry=/usr/local/share/agent-canon/toolchains/cargo/registry

    mkdir -p -- "$cargo_home/registry/cache"
    cp -R --update=none -- "$seed_registry/cache/." "$cargo_home/registry/cache/"
    _refresh_seeded_registry_index "$seed_registry/index" "$cargo_home/registry/index"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
