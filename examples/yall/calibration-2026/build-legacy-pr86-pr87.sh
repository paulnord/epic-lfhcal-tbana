#!/usr/bin/env bash
# Build once; the Yallfiles remain ordinary analysis tasks.
set -euo pipefail
if [[ $# != 1 ]]; then
    echo "Usage: $0 EIC_SHELL" >&2
    exit 2
fi
support=$(cd "$(dirname "$0")" && pwd)
source_dir=$(realpath "$support/../../..")
eic_shell=$(realpath "$1")
build="$source_dir/NewStructure/build"
[[ -x "$eic_shell" ]]

# These are the inspected source blobs: both PR fixes, direct Legacy HG,
# original range selection. A different checkout must be reviewed explicitly.
while read -r expected path; do
    actual=$(git -C "$source_dir" hash-object "$source_dir/$path")
    if [[ "$actual" != "$expected" ]]; then
        echo "Unexpected source: $path; refusing an unverified build." >&2
        exit 2
    fi
done < "$support/legacy-pr86-pr87-source-blobs.txt"
git -C "$source_dir" diff --quiet HEAD -- NewStructure configs
decoder="$source_dir/NewStructure/h2g_decode"
[[ -f "$decoder/CMakeLists.txt" ]] || {
    echo "Initialize the h2g_decode submodule before building." >&2; exit 2;
}
[[ $(git -C "$decoder" rev-parse HEAD) == 2a7f7d4e8b760ff9f9406e36d31e99c5b6fffa2c ]]
git -C "$decoder" diff --quiet HEAD
mkdir -p "$build"
marker="$build/legacy-pr86-pr87-build.sha256"
if [[ -f "$marker" ]]; then
    (cd "$source_dir" && sha256sum --status -c "$build/legacy-pr86-pr87-source.sha256")
    sha256sum --status -c "$marker"
    echo "Legacy + PR86 + PR87 build already ready: $build"
    exit 0
fi

# Include the decoder and run configuration, but exclude generated build files.
(cd "$source_dir" && find NewStructure configs \
    -type d -name build -prune -o -name .git -prune -o -type f -print0 | \
    sort -z | xargs -0 sha256sum > "$build/legacy-pr86-pr87-source.sha256")
git -C "$source_dir" rev-parse HEAD > "$build/legacy-pr86-pr87-commit.txt"
printf '%s\n' 'Legacy fitter; original boundary' \
    'PR86 memory/array fixes; PR87 checked I/O and failure status' \
    > "$build/legacy-pr86-pr87-method.txt"

bash "$support/run-in-eic-shell.sh" "$eic_shell" /bin/bash -c '
    set -euo pipefail
    source_dir=$1
    build="$source_dir/NewStructure/build"
    root-config --version > "$build/legacy-pr86-pr87-root-version.txt"
    cmake -S "$source_dir/NewStructure" -B "$build"
    cmake --build "$build" --target Convert DataPrep -j 4
    cd "$build"
    export LD_LIBRARY_PATH="$build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    ./Convert -h > legacy-pr86-pr87-Convert-help.txt
    ./DataPrep -h > legacy-pr86-pr87-DataPrep-help.txt
    cd "$source_dir"
    sha256sum --status -c "$build/legacy-pr86-pr87-source.sha256"
    sha256sum "$build/Convert" "$build/DataPrep" "$build/libLFHCAL.so" \
        "$build/legacy-pr86-pr87-source.sha256" \
        > "$build/legacy-pr86-pr87-build.sha256.tmp"
    mv "$build/legacy-pr86-pr87-build.sha256.tmp" "$build/legacy-pr86-pr87-build.sha256"
' legacy-build "$source_dir"
# eic-shell can mask an inner failure. Only a successful inner build creates this.
sha256sum --status -c "$marker"
echo "Legacy + PR86 + PR87 build ready: $build"
