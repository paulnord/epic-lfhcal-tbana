#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${LFHCAL_CONTAINER_IMAGE:-}" ]]; then
    echo "run-in-eic-container: LFHCAL_CONTAINER_IMAGE is not set" >&2
    exit 2
fi

if command -v apptainer >/dev/null 2>&1; then
    runtime=$(command -v apptainer)
elif command -v singularity >/dev/null 2>&1; then
    runtime=$(command -v singularity)
else
    echo "run-in-eic-container: neither apptainer nor singularity was found" >&2
    exit 127
fi

exec "$runtime" exec "$LFHCAL_CONTAINER_IMAGE" "$@"
