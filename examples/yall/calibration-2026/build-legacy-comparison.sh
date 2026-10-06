#!/usr/bin/env bash
# One-time setup/build, outside the Yallfile and outside the running source tree.
set -euo pipefail
if [[ $# != 3 ]]; then
    echo "Usage: $0 ACTIVE_SOURCE SEPARATE_LEGACY_SOURCE EIC_SHELL" >&2
    exit 2
fi
source_dir=$(realpath "$1")
legacy_dir=$(realpath -m "$2")
eic_shell=$3
support=$(cd "$(dirname "$0")" && pwd)
case "$legacy_dir/" in
    "$source_dir/"*) echo "Legacy source must be outside the active source tree." >&2; exit 2;;
esac
[[ -x "$eic_shell" ]]
[[ -f "$source_dir/NewStructure/h2g_decode/CMakeLists.txt" ]]
[[ -d "$source_dir/configs/TB2026" ]]

if [[ -e "$legacy_dir" ]]; then
    # Retry only our already-patched copy; never copy over an existing checkout.
    [[ -f "$legacy_dir/legacy-source.sha256" ]] || {
        echo "Destination already exists without a completed source snapshot: $legacy_dir" >&2
        exit 2
    }
    (cd "$legacy_dir" && sha256sum --status -c legacy-source.sha256)
    if [[ -f "$legacy_dir/NewStructure/build/legacy-build.sha256" ]]; then
        sha256sum --status -c "$legacy_dir/NewStructure/build/legacy-build.sha256"
        echo "Legacy comparison build already ready: $legacy_dir/NewStructure/build"
        exit 0
    fi
else
    mkdir -p "$legacy_dir"
    rsync -a --exclude='build/' --exclude='.git' \
        "$source_dir/NewStructure" "$source_dir/configs" "$legacy_dir/"
    # Apply only the dispatch change to the exact sources used by Adaptive.
    git -C "$legacy_dir" apply --check "$support/legacy-dispatch.patch"
    git -C "$legacy_dir" apply "$support/legacy-dispatch.patch"
    if grep -Eq 'LFHCAL_RANGE_V1|mip_range_v1::choose' "$legacy_dir/NewStructure/TileSpectra.cc"; then
        echo "Unexpected valley patch in source; comparison requires the original boundary." >&2
        exit 2
    fi
    git -C "$source_dir" rev-parse HEAD > "$legacy_dir/reference-commit.txt"
    git -C "$source_dir" diff -- NewStructure > "$legacy_dir/reference-working-changes.patch"
    cp "$support/legacy-dispatch.patch" "$legacy_dir/legacy-dispatch.patch"
    (cd "$legacy_dir" && sha256sum NewStructure/TileSpectra.cc > legacy-source.sha256)
fi

# EIC shell supplies ROOT/compiler versions, just as for the current campaigns.
bash "$support/run-in-eic-shell.sh" "$eic_shell" /bin/bash -c \
    'set -euo pipefail; cmake -S "$1/NewStructure" -B "$1/NewStructure/build"; cmake --build "$1/NewStructure/build" --target DataPrep -j 4; sha256sum "$1/NewStructure/TileSpectra.cc" "$1/NewStructure/build/DataPrep" "$1/NewStructure/build/libLFHCAL.so" > "$1/NewStructure/build/legacy-build.sha256"' \
    legacy-build "$legacy_dir"
# The marker is created only by a successful build inside the EIC shell.
sha256sum --status -c "$legacy_dir/NewStructure/build/legacy-build.sha256"
echo "Legacy comparison build ready: $legacy_dir/NewStructure/build"
