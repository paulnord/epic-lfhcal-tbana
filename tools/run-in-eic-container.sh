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

# Mirror the standard host paths discovered by the generated EIC shell.  A
# caller can replace this detection with a comma-separated explicit list.
bind_path=${LFHCAL_CONTAINER_BINDPATH:-}
if [[ -z "$bind_path" ]]; then
    for candidate in /media /cvmfs /gpfs /gpfs01 /gpfs02 /direct; do
        if [[ -e "$candidate" ]]; then
            if [[ -n "$bind_path" ]]; then
                bind_path+=,
            fi
            bind_path+=$candidate
        fi
    done
fi

if [[ -n "$bind_path" ]]; then
    if [[ "$(basename "$runtime")" == apptainer ]]; then
        export APPTAINER_BINDPATH="${APPTAINER_BINDPATH:+${APPTAINER_BINDPATH},}${bind_path}"
    else
        export SINGULARITY_BINDPATH="${SINGULARITY_BINDPATH:+${SINGULARITY_BINDPATH},}${bind_path}"
    fi
fi

exec "$runtime" exec "$LFHCAL_CONTAINER_IMAGE" "$@"
