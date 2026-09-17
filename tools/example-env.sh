#!/usr/bin/env bash

# Source this helper from an examples/yall/<example>/env.sh wrapper.
# It activates the installed yall/LFHCal environment and prepares the shared
# raw-data and work directories used by the Yallfile.

_example=${1:-}
if [[ -z "$_example" ]]; then
    echo "example-env.sh: missing example name" >&2
    return 1 2>/dev/null || exit 1
fi

export LFHCAL_HOME=${LFHCAL_HOME:-"$HOME/eic-2026"}

if [[ ! -f "$LFHCAL_HOME/activate.sh" ]]; then
    echo "LFHCal environment not installed at $LFHCAL_HOME." >&2
    echo "Run tools/bootstrap-yall-integration.sh first." >&2
    return 1 2>/dev/null || exit 1
fi

source "$LFHCAL_HOME/activate.sh"

export LFHCAL_EXAMPLE="$_example"
export LFHCAL_EXAMPLE_WORK="$LFHCAL_WORK/$_example"

mkdir -p "$LFHCAL_DATA" "$LFHCAL_EXAMPLE_WORK" "$LFHCAL_WORK/campaigns"

printf 'LFHCAL_DATA=%s\n' "$LFHCAL_DATA"
printf 'LFHCAL_WORK=%s\n' "$LFHCAL_WORK"
printf 'EIC_SHELL=%s\n' "$EIC_SHELL"
printf 'Example work=%s\n' "$LFHCAL_EXAMPLE_WORK"

unset _example
