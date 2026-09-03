#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Compiles every source-mounted Rust tool into the external runtime cache.
# upstream design ../../../documents/design/agent-canon-bootstrap-tool-runtime.md source-mounted tool build
# downstream implementation ../../../bootstrap/container/dispatch/tool-wrapper.sh cached tool dispatch
# @dependency-end

set -euo pipefail

source_root=${AGENT_CANON_SOURCE_ROOT:-/opt/agent-canon/source}
cache_root=${AGENT_CANON_CACHE_ROOT:-/var/lib/agent-canon/cache}
compiled_bin_dir=${AGENT_CANON_COMPILED_BIN_DIR:-$cache_root/bin}
cargo_target_dir=${CARGO_TARGET_DIR:-${AGENT_CANON_CARGO_TARGET_DIR:-$cache_root/cargo-target}}
cargo_home=${CARGO_HOME:-$cache_root/cargo}
temporary=
cleanup() {
    [[ -z "$temporary" ]] || rm -f -- "$temporary"
}
trap cleanup EXIT

mkdir -p -- "$compiled_bin_dir" "$cargo_target_dir" "$cargo_home"

# The source tree is the only tool inventory. Cargo metadata supplies binary
# names, so this route has no list of tool directories or tool names to drift.
shopt -s globstar nullglob
manifests=("$source_root"/tools/**/Cargo.toml)
for manifest in "${manifests[@]}"; do
    metadata=$(cargo metadata --format-version 1 --no-deps --manifest-path "$manifest")
    target_directory=$(jq -er '.target_directory' <<<"$metadata")
    mapfile -t binaries < <(
        jq -er '.packages[] | .targets[] | select(.kind | index("bin")) | .name' <<<"$metadata"
    )
    ((${#binaries[@]})) || continue
    cargo build --manifest-path "$manifest" --locked --release
    for binary in "${binaries[@]}"; do
        artifact="$target_directory/release/$binary"
        temporary=$(mktemp "$compiled_bin_dir/.${binary}.XXXXXX")
        cp -- "$artifact" "$temporary"
        chmod 0555 -- "$temporary"
        mv -f -- "$temporary" "$compiled_bin_dir/$binary"
        temporary=
    done
done
