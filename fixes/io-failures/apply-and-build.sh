#!/usr/bin/env bash
# One-time source patch and rebuild. No runtime wrapper or fitter changes.
set -euo pipefail
if [[ $# != 2 ]]; then
    echo "Usage: $0 ACTIVE_SOURCE EIC_SHELL" >&2
    exit 2
fi
source_dir=$(realpath "$1")
eic_shell=$(realpath "$2")
support=$(cd "$(dirname "$0")" && pwd)
[[ -x "$eic_shell" ]]
[[ -f "$source_dir/NewStructure/build/CMakeCache.txt" ]] || {
    echo "No configured build at $source_dir/NewStructure/build" >&2
    exit 2
}
selected_patch=
already_applied=false
for name in minimal existing_check; do
    patch_file="$support/$name.patch"
    if git -C "$source_dir" apply --reverse --check "$patch_file" 2>/dev/null; then
        already_applied=true
        break
    fi
    if git -C "$source_dir" apply --check "$patch_file" 2>/dev/null; then
        selected_patch=$patch_file
        break
    fi
done
if [[ "$already_applied" == true ]]; then
    echo "Checked I/O source changes already present."
elif [[ -n "$selected_patch" ]]; then
    git -C "$source_dir" apply "$selected_patch"
else
    echo "Source differs from both supported versions; no changes applied." >&2
    git -C "$source_dir" apply --check "$support/minimal.patch"
    exit 2
fi
marker="$source_dir/NewStructure/build/checked-io.sha256"
rm -f "$marker"
bash "$support/run-in-eic-shell.sh" "$eic_shell" /bin/bash -c \
    'set -euo pipefail; source_dir=$1; build="$source_dir/NewStructure/build"; cmake --build "$build" --target Convert DataPrep -j 4; sha256sum "$source_dir/NewStructure/CheckedIO.h" "$source_dir/NewStructure/DataPrep.cc" "$source_dir/NewStructure/Convert.cc" "$source_dir/NewStructure/Calib.cc" "$source_dir/NewStructure/Analyses.cc" "$build/DataPrep" "$build/Convert" "$build/libLFHCAL.so" > "$build/checked-io.sha256.tmp"; mv "$build/checked-io.sha256.tmp" "$build/checked-io.sha256"' \
    checked-io-build "$source_dir"
# Also detects an EIC shell that masks a failed inner command's exit status.
sha256sum --status -c "$marker"
echo "Checked I/O build ready: $source_dir/NewStructure/build"
