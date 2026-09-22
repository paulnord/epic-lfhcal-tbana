# Environment for the calibration-only adaptive FullSet replays.
source ../../../tools/example-env.tcsh adaptive-fullsets
if ($status != 0) exit 1

# Persistent converted inputs gathered under the TB2026 layout.
setenv LFHCAL_CONVERTED "/gpfs/mnt/gpfs01/star/pwg/pnord/eic/TB2026/converted"
setenv LFHCAL_MERGED "/gpfs/mnt/gpfs01/star/pwg/pnord/eic/TB2026/merged"
mkdir -p "$LFHCAL_WORK/adaptive-fullsets/campaigns"

echo "Converted inputs=$LFHCAL_CONVERTED"
echo "Merged inputs=$LFHCAL_MERGED"
