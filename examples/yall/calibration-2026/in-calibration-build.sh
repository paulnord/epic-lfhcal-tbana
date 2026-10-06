#!/usr/bin/env bash
set -euo pipefail
# Locate this campaign's ROOT dictionaries and library when running hadd/DataPrep.
build=$1
shift
mkdir -p "$build"
cd "$build"
export LD_LIBRARY_PATH="$build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1
exec "$@"
