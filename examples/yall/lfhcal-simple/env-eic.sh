#!/usr/bin/env bash
# Source this from bash inside eic-shell, from any directory.
# It mirrors the BNL storage defaults used by the host tcsh setup and exposes
# the checked-out yall-run source directly to the EIC Python. No container-side
# pip install is required.

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

_yall_src="$YALL_RUN_REPO/src"
if [[ ! -r "$_yall_src/yall_run/cli.py" ]]; then
    echo "yall-run checkout is not readable inside eic-shell: $YALL_RUN_REPO" >&2
    unset _lfhcal_workspace _yall_src
    return 1
fi
export PYTHONPATH="$_yall_src${PYTHONPATH:+:$PYTHONPATH}"

# The EIC Python disables the user site and treats /opt/local as an isolated
# prefix, so `pip install --user` is not usable here. Run directly from the
# checkout instead. This also means a git pull immediately updates local-mode
# Yall without a second install step.
yall-run() {
    python3 -m yall_run.cli "$@"
}

mkdir -p "$LFHCAL_WORK/campaigns" "$LFHCAL_EXAMPLE_WORK" || {
    echo "Cannot create LFHCal work directories under $LFHCAL_WORK" >&2
    unset _lfhcal_workspace _yall_src
    return 1
}

if [[ ! -r "$LFHCAL_DATA" ]]; then
    echo "WARNING: shared raw data are not readable: $LFHCAL_DATA" >&2
fi

if ! yall-run --version >/dev/null 2>&1; then
    echo "yall-run checkout is not runnable with the EIC Python." >&2
    echo "Check $YALL_RUN_REPO and the eic-shell Python environment." >&2
    unset _lfhcal_workspace _yall_src
    return 1
fi

printf 'LFHCAL_DATA=%s\n' "$LFHCAL_DATA"
printf 'LFHCAL_WORK=%s\n' "$LFHCAL_WORK"
printf 'Example work=%s\n' "$LFHCAL_EXAMPLE_WORK"
printf 'yall-run=%s\n' "$(yall-run --version)"

unset _lfhcal_workspace _yall_src
