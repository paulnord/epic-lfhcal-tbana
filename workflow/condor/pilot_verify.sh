#!/usr/bin/env bash
set -euo pipefail

REPO="/star/u/pnord/eic-2026/epic-lfhcal-tbana"
BUILD="/star/u/pnord/eic-2026/build-epic-lfhcal-tbana-main-20260825-142900"
HISTS="/gpfs01/star/pwg/pnord/eic/2026TBdata/prod_296_306/calibratedHGCROC_wave_Run_306_Hists.root"
PROV="$REPO/tools/provenance/lfhcal_provenance.py"

export LD_LIBRARY_PATH="${BUILD}:${LD_LIBRARY_PATH:-}"
export ROOT_INCLUDE_PATH="${REPO}/NewStructure:${ROOT_INCLUDE_PATH:-}"
export ROOT_MAX_THREADS=1

echo "Host: $(hostname)"
echo "ROOT: $(root-config --version)"
echo "Python: $(python3 --version)"
echo "Input: $HISTS"

test -x "$BUILD/DataPrep"
test -x "$BUILD/HGCROCStudy"
test -r "$PROV"
test -r "$HISTS"

python3 "$PROV" verify "$HISTS"
python3 "$PROV" show "$HISTS"

echo "Condor container pilot passed"
ls -lh "$HISTS"
