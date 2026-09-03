#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -lt 1 ]]; then
    echo "Usage: $0 COMMAND [ARGUMENTS ...]" >&2
    exit 2
fi

IMAGE="${EIC_CONTAINER_IMAGE:-/cvmfs/singularity.opensciencegrid.org/eicweb/eic_xl:nightly}"

[[ -e "$IMAGE" ]] || {
    echo "Container image or alias does not exist: $IMAGE" >&2
    exit 2
}

exec /usr/bin/singularity exec -e \
    -B /direct \
    -B /star \
    -B /afs \
    -B /gpfs \
    -B /gpfs01 \
    -B /sdcc/lustre02 \
    "$IMAGE" \
    /usr/bin/env \
        ROOT_MAX_THREADS="${ROOT_MAX_THREADS:-1}" \
        OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}" \
        "$@"
