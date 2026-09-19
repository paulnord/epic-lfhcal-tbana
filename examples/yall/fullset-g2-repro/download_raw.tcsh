#!/bin/tcsh -f
# Download the raw files needed for the FullSet G2 reproduction.
#
# Usage:
#   tcsh download_raw.tcsh
#   tcsh download_raw.tcsh /some/other/destination
#
# If LFHCAL_DATA is set, it is used as the default destination. Otherwise use
# Paul's standard TB2026 raw-data directory at BNL.

set SRC = root://dtn-eic.jlab.org:1094//work/eic3/EPIC/TestBeam/LFHCAL/CERN/2026/2026_SPSH2/raw

if ($#argv >= 1) then
    set DEST = "$argv[1]"
else if ($?LFHCAL_DATA) then
    set DEST = "$LFHCAL_DATA"
else
    set DEST = /gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBdata
endif

mkdir -p "$DEST"
if ($status != 0) exit 1

foreach r (529 530 531 532 533 534 535 536 537)
    set OUT = "$DEST/Run${r}.h2g"
    set TMP = "$OUT.part"

    if (-s "$OUT") then
        echo "Run${r}.h2g already present"
        continue
    endif

    echo "Downloading Run${r}.h2g"
    /bin/rm -f "$TMP"
    xrdcp "$SRC/Run${r}.h2g" "$TMP"
    if ($status != 0) then
        echo "ERROR: download failed for Run${r}.h2g"
        /bin/rm -f "$TMP"
        exit 1
    endif

    /bin/mv "$TMP" "$OUT"
    if ($status != 0) exit 1
end

echo ""
echo "G2 raw files:"
foreach r (529 530 531 532 533 534 535 536 537)
    ls -lh "$DEST/Run${r}.h2g"
end
