#!/usr/bin/env bash
set -euo pipefail
repo=$1
build=$2
ready=$3
# Shared storage is required; never compile on a login host.
[[ ${ARI_RF_BATCH_WORKER:-} == 1 ]] || { echo 'Build must execute in a Condor worker' >&2; exit 2; }
[[ -f "$repo/NewStructure/h2g_decode/CMakeLists.txt" ]] || { echo 'Initialize pinned h2g_decode submodule before submission' >&2; exit 2; }
mkdir -p "$build"
{
  date -u
  hostname
  git -C "$repo" rev-parse HEAD
  git -C "$repo" submodule status
  root-config --version
  cmake --version
} > "$build/environment.txt"
cmake -S "$repo/NewStructure" -B "$build" -DBUILD_TESTING=ON -DLFHCAL_USE_ADAPTIVE_LANGAU=OFF
cmake --build "$build" --parallel 2 --target Convert DataPrep HGCROCStudy CompareWaveform test_waveform_measurement test_fit_curve_legend
ctest --test-dir "$build" --output-on-failure -R '^(waveform_measurement|fit_curve_legend_lifetime)$'
printf 'build, waveform and fit-legend lifetime tests passed\n' > "$ready"
