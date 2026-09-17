#!/usr/bin/env bash
# Source this from bash inside eic-shell, from any directory.
# It mirrors the BNL storage defaults used by the host tcsh setup and makes the
# yall-run installation for the EIC Python visible on PATH.

_lfhcal_workspace=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd -P) || return 1

export LFHCAL_HOME="$_lfhcal_workspace"
export LFHCAL_REPO="$LFHCAL_HOME/epic-lfhcal-tbana"
export YALL_RUN_REPO="$LFHCAL_HOME/yall-run"
export EIC_SHELL="$LFHCAL_HOME/eic-shell"

# If env.tcsh was sourced before entering eic-shell, these values are normally
# inherited. Otherwise use the same BNL defaults directly.
export LFHCAL_DATA="${LFHCAL_DATA:-/gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBdata}"
export LFHCAL_WORK="${LFHCAL_WORK:-/gpfs01/star/scratch/$(id -un)/lfhcal}"
export LFHCAL_EXAMPLE="lfhcal-simple"
export LFHCAL_EXAMPLE_WORK="$LFHCAL_WORK/$LFHCAL_EXAMPLE"

_yall_user_bin="$(python3 -m site --user-base)/bin"
export PATH="$_yall_user_bin:$PATH"

mkdir -p "$LFHCAL_WORK/campaigns" "$LFHCAL_EXAMPLE_WORK" || {
    echo "Cannot create LFHCal work directories under $LFHCAL_WORK" >&2
    unset _lfhcal_workspace _yall_user_bin
    return 1
}

if [[ ! -r "$LFHCAL_DATA" ]]; then
    echo "WARNING: shared raw data are not readable: $LFHCAL_DATA" >&2
fi

if ! command -v yall-run >/dev/null 2>&1; then
    echo "yall-run is not on PATH inside eic-shell." >&2
    echo "Rerun the BNL bootstrap so yall-run is installed for the EIC Python." >&2
    unset _lfhcal_workspace _yall_user_bin
    return 1
fi

printf 'LFHCAL_DATA=%s\n' "$LFHCAL_DATA"
printf 'LFHCAL_WORK=%s\n' "$LFHCAL_WORK"
printf 'Example work=%s\n' "$LFHCAL_EXAMPLE_WORK"
printf 'yall-run=%s\n' "$(command -v yall-run)"

unset _lfhcal_workspace _yall_user_bin
