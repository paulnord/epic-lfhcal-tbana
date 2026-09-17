#!/usr/bin/env bash
set -euo pipefail

# BNL setup, launched from the normal tcsh login/submit session.
# Bash executes this installer and the EIC wrapper; it is not a second
# interactive environment. Condor stays on the host. The wrapper-free local
# LFHCal example is run from inside eic-shell, so yall-run is installed for
# both the host Python and the Python in eic-shell.
# Software is installed in the current folder (or --prefix PATH).

install_root=$PWD
while (($#)); do
    case "$1" in
        --prefix)
            if [[ $# -lt 2 || -z "$2" ]]; then
                echo "--prefix requires an installation directory." >&2
                exit 2
            fi
            install_root=$2
            shift 2
            ;;
        -h|--help)
            echo "Usage: bash bootstrap-yall-integration.sh [--prefix PATH]"
            echo "Default destination: the current working directory."
            exit 0
            ;;
        *)
            echo "Unknown argument: $1 (use --help)." >&2
            exit 2
            ;;
    esac
done

YALL_REPO_URL=${YALL_REPO_URL:-"https://github.com/paulnord/yall-run.git"}
LFHCAL_REPO_URL=${LFHCAL_REPO_URL:-"https://github.com/paulnord/epic-lfhcal-tbana.git"}
YALL_BRANCH=${YALL_BRANCH:-main}
LFHCAL_BRANCH=${LFHCAL_BRANCH:-yall-integration}
LFHCAL_BUILD_JOBS=${LFHCAL_BUILD_JOBS:-2}

say() { printf '\n==> %s\n' "$*"; }
need() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Required command not found: $1. Use the normal BNL submit shell." >&2
        exit 1
    }
}
update_checkout() {
    local url=$1 branch=$2 dir=$3
    if [[ -d "$dir/.git" ]]; then
        say "Updating $(basename "$dir") ($branch)"
        git -C "$dir" fetch origin
        git -C "$dir" switch "$branch"
        git -C "$dir" pull --ff-only
    else
        say "Cloning $(basename "$dir") ($branch)"
        git clone --branch "$branch" "$url" "$dir"
    fi
}

need git
need curl
need python3
need tcsh
need condor_submit
need condor_submit_dag

mkdir -p -- "$install_root"
LFHCAL_HOME=$(cd -- "$install_root" && pwd -P)
YALL_DIR="$LFHCAL_HOME/yall-run"
LFHCAL_DIR="$LFHCAL_HOME/epic-lfhcal-tbana"
EIC_SHELL="$LFHCAL_HOME/eic-shell"
YALL_USER_BIN="$(python3 -m site --user-base)/bin"

# Keep one user-editable storage file. Never overwrite existing settings.
# Raw input is shared; only the user's work tree is created by activation.
if [[ ! -f "$LFHCAL_HOME/site-env.tcsh" ]]; then
    cat > "$LFHCAL_HOME/site-env.tcsh" <<'EOF'
# BNL storage defaults. Change these paths here when needed.
if (! $?LFHCAL_DATA) setenv LFHCAL_DATA "/gpfs/mnt/gpfs01/star/pwg/pnord/eic/2026TBdata"
if (! $?LFHCAL_WORK) setenv LFHCAL_WORK "/gpfs01/star/scratch/`id -un`/lfhcal"
EOF
fi

cat > "$LFHCAL_HOME/activate.tcsh" <<EOF
# Source from the normal BNL tcsh session. This does not enter eic-shell.
unset LFHCAL_HOME LFHCAL_REPO YALL_RUN_REPO EIC_SHELL
setenv LFHCAL_HOME "${LFHCAL_HOME}"
setenv LFHCAL_REPO "${LFHCAL_DIR}"
setenv YALL_RUN_REPO "${YALL_DIR}"
setenv EIC_SHELL "${EIC_SHELL}"
setenv PATH "${YALL_USER_BIN}:\$PATH"
rehash
source "${LFHCAL_HOME}/site-env.tcsh"
if (\$status == 0) then
    # Read access only: never create or write into the shared raw-data tree.
    if (! -d "\$LFHCAL_DATA" || ! -r "\$LFHCAL_DATA" || ! -x "\$LFHCAL_DATA") then
        echo "WARNING: shared raw data are not readable: \$LFHCAL_DATA"
        echo "Check access with Paul, or set LFHCAL_DATA to readable raw data before analysis."
    endif
    # -p also creates /gpfs01/star/scratch/<username> when it is missing.
    mkdir -p "\$LFHCAL_WORK/campaigns"
    if (\$status != 0) then
        echo "Cannot create work directories: \$LFHCAL_WORK"
        echo "Check scratch permissions or edit ${LFHCAL_HOME}/site-env.tcsh."
        /bin/false
    else if (! -w "\$LFHCAL_WORK" || ! -w "\$LFHCAL_WORK/campaigns") then
        echo "Work directories are not writable: \$LFHCAL_WORK"
        /bin/false
    else
        echo "Raw input: \$LFHCAL_DATA"
        echo "Work root: \$LFHCAL_WORK"
        /bin/true
    endif
endif
EOF

say "Preparing BNL scratch directories"
# Execute the same setup users will source, including any local overrides.
# A child tcsh does not change the caller's interactive shell.
tcsh -f "$LFHCAL_HOME/activate.tcsh"

say "Installation root: $LFHCAL_HOME"
if [[ ! -x "$EIC_SHELL" ]]; then
    say "Installing eic-shell"
    (
        cd "$LFHCAL_HOME"
        curl --fail --silent --show-error --location https://get.epic-eic.org | bash
    )
    if [[ ! -x "$EIC_SHELL" && -x "$LFHCAL_HOME/eic-env/eic-shell" ]]; then
        ln -s "$LFHCAL_HOME/eic-env/eic-shell" "$EIC_SHELL"
    fi
fi
if [[ ! -x "$EIC_SHELL" ]]; then
    echo "eic-shell was not found at $EIC_SHELL after installation." >&2
    exit 1
fi

update_checkout "$YALL_REPO_URL" "$YALL_BRANCH" "$YALL_DIR"
update_checkout "$LFHCAL_REPO_URL" "$LFHCAL_BRANCH" "$LFHCAL_DIR"
git -C "$LFHCAL_DIR" submodule update --init --recursive

say "Installing yall-run for this user with the host Python"
python3 -m pip install --user -e "$YALL_DIR"

say "Installing yall-run for local tests inside eic-shell"
"$LFHCAL_DIR/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
    python3 -m pip install --user -e "$YALL_DIR"

say "Configuring LFHCal inside eic-shell"
"$LFHCAL_DIR/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
    cmake -S "$LFHCAL_DIR/NewStructure" -B "$LFHCAL_DIR/NewStructure/build"
say "Building LFHCal"
"$LFHCAL_DIR/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
    cmake --build "$LFHCAL_DIR/NewStructure/build" -j"$LFHCAL_BUILD_JOBS"

say "Smoke tests (no batch jobs submitted)"
"$LFHCAL_DIR/tools/run-in-eic-shell.sh" "$EIC_SHELL" root-config --version
"$YALL_USER_BIN/yall-run" --help >/dev/null
# Exercise the same bash environment setup used by lfhcal-simple inside eic-shell.
"$LFHCAL_DIR/tools/run-in-eic-shell.sh" "$EIC_SHELL" \
    /bin/bash -lc "cd '$LFHCAL_DIR/examples/yall/lfhcal-simple' && source ./env-eic.sh >/dev/null && yall-run --help >/dev/null"
test -x "$LFHCAL_DIR/NewStructure/build/Convert"
test -x "$LFHCAL_DIR/NewStructure/build/DataPrep"
if [[ -f "$LFHCAL_DIR/examples/yall/check_shared_conversions.py" ]]; then
    python3 "$LFHCAL_DIR/examples/yall/check_shared_conversions.py" -v
fi

say "Ready"
printf 'Install root: %s\n' "$LFHCAL_HOME"
printf 'Host command: %s/yall-run\n' "$YALL_USER_BIN"
printf '\nIn your normal tcsh session:\n  source "%s/activate.tcsh"\n' "$LFHCAL_HOME"
printf 'For lfhcal-simple, enter eic-shell and source env-eic.sh before running yall-run.\n'
printf 'Return to the host for the Condor smoke test and scan-set-1.\n'
printf 'Instructions: %s/examples/yall/SETUP.md\n' "$LFHCAL_DIR"
