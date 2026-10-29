#!/usr/bin/env bash
set -euo pipefail
# Check on the execute host BEFORE container environment filtering.
[[ -n ${_CONDOR_JOB_AD:-} ]] || { echo 'RF payloads must execute in an HTCondor worker, not on the login host' >&2; exit 2; }
eic_shell=$1
shift
here=$(cd -- "$(dirname -- "$0")" && pwd)
exec "$here/../../../tools/run-in-eic-shell.sh" "$eic_shell" /usr/bin/env ARI_RF_BATCH_WORKER=1 "$@"
