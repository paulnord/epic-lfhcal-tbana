#!/usr/bin/env bash
# Run numerical and production-path checks against an already-built library.
set -euo pipefail
if [[ $# != 2 || ( $2 != legacy && $2 != adaptive ) ]]; then
  echo "Usage: $0 /path/to/build {legacy|adaptive}" >&2
  exit 2
fi
build=$(cd "$1" && pwd)
mode=$2
here=$(cd "$(dirname "$0")" && pwd)
if [[ ! -f "$build/libLFHCAL.so" && ! -f "$build/libLFHCAL.dylib" ]]; then
  echo "No built libLFHCAL in $build" >&2
  exit 2
fi
work=$(mktemp -d "${TMPDIR:-/tmp}/lfhcal-langau.XXXXXX")
trap 'rm -rf "$work"' EXIT
# Intentional flag splitting follows root-config's compiler/linker interface.
"${CXX:-c++}" -std=c++17 -O3 ${CXXFLAGS:-} "$here/test_adaptive_langau.cc" -o "$work/numerics"
"$work/numerics"
root -l -b -q "$here/test_adaptive_langau_root.C()"
for source in test_production benchmark_langau; do
  "${CXX:-c++}" -O3 ${CXXFLAGS:-} $(root-config --cflags) "$here/$source.cc" \
    -L"$build" -Wl,-rpath,"$build" -lLFHCAL $(root-config --libs) ${LDFLAGS:-} \
    -o "$work/$source"
done
"$work/test_production" "$mode"
"$work/benchmark_langau"
