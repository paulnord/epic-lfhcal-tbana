#!/usr/bin/env bash
set -euo pipefail

IMAGE="/cvmfs/singularity.opensciencegrid.org/.images/sha256:9b/c2b320c0ae6e723615f63bc569cbfb347799ca5190fba4ec7750b0114548f7"

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 PAYLOAD [ARGUMENTS ...]" >&2
    exit 2
fi

PAYLOAD="$1"
shift

if [ ! -r "$PAYLOAD" ]; then
    echo "Payload is not readable: $PAYLOAD" >&2
    exit 2
fi

exec /usr/bin/singularity exec -e \
    -B /direct \
    -B /star \
    -B /afs \
    -B /gpfs \
    -B /gpfs01 \
    -B /sdcc/lustre02 \
    "$IMAGE" \
    /bin/bash "$PAYLOAD" "$@"
