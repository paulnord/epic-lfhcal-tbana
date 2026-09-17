#!/usr/bin/env bash

# Source this helper from an examples/yall/<example>/env.sh wrapper.
# It activates the installed yall/LFHCal environment and prepares the shared
# raw-data and work directories used by the Yallfile.

_example=${1:-}
if [[ -z "$_example" ]]; then
    echo "example-env.sh: missing example name" >&2
    return 1 2>/dev/null || exit 1
fi

# In a bootstrap workspace the installation root is the checkout's parent.
# Prefer that workspace over an LFHCAL_HOME left by another installation.
# A separately located checkout can still use an explicit LFHCAL_HOME.
_lfhcal_workspace=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P) || {
    unset _example
    return 1 2>/dev/null || exit 1
}
if [[ -f "$_lfhcal_workspace/activate.sh" ]]; then
    export LFHCAL_HOME="$_lfhcal_workspace"
fi

if [[ -z "${LFHCAL_HOME:-}" || ! -f "$LFHCAL_HOME/activate.sh" ]]; then
    echo "LFHCal environment not installed at $_lfhcal_workspace." >&2
    echo "Run the bootstrap from your workspace, or set LFHCAL_HOME to an existing installation." >&2
    unset _example _lfhcal_workspace
    return 1 2>/dev/null || exit 1
fi

source "$LFHCAL_HOME/activate.sh" || {
    unset _example _lfhcal_workspace
    return 1 2>/dev/null || exit 1
}

export LFHCAL_EXAMPLE="$_example"
export LFHCAL_EXAMPLE_WORK="$LFHCAL_WORK/$_example"

mkdir -p "$LFHCAL_DATA" "$LFHCAL_EXAMPLE_WORK" "$LFHCAL_WORK/campaigns" || {
    unset _example _lfhcal_workspace
    return 1 2>/dev/null || exit 1
}

printf 'LFHCAL_HOME=%s\n' "$LFHCAL_HOME"
printf 'LFHCAL_DATA=%s\n' "$LFHCAL_DATA"
printf 'LFHCAL_WORK=%s\n' "$LFHCAL_WORK"
printf 'EIC_SHELL=%s\n' "$EIC_SHELL"
printf 'Example work=%s\n' "$LFHCAL_EXAMPLE_WORK"

unset _example _lfhcal_workspace
