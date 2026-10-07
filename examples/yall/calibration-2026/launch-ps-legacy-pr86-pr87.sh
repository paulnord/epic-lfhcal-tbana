#!/usr/bin/env bash
# Submit the existing full-chain PS Yallfiles, with one verified shared build.
set -euo pipefail
: "${CALWORK:?Set CALWORK to a new Legacy results directory}"
: "${LFHCAL_SOURCE:?Set LFHCAL_SOURCE to the separate Legacy source checkout}"
: "${LFHCAL_RAW:?Set LFHCAL_RAW to the directory containing ps-2026/raw}"
: "${EIC_SHELL:?Set EIC_SHELL}"
support=$(cd "$(dirname "$0")" && pwd)
source_dir=$(realpath "$support/../../..")
[[ $(realpath "$LFHCAL_SOURCE") == "$source_dir" ]]
CALWORK=$(realpath -m "$CALWORK")
export CALWORK
build="$source_dir/NewStructure/build"
(cd "$source_dir" && sha256sum --status -c "$build/legacy-pr86-pr87-source.sha256")
sha256sum --status -c "$build/legacy-pr86-pr87-build.sha256"
[[ -d "$LFHCAL_RAW/ps-2026/raw" ]]
[[ -x "$EIC_SHELL" ]]
if [[ $# == 0 ]]; then
    set -- ps-a1 ps-a2 ps-b1 ps-b2 ps-c1 ps-c2 ps-d1 ps-d2 ps-e1 ps-e2 \
        ps-f1 ps-f2 ps-g1 ps-g2 ps-h1 ps-i1 ps-i2
fi
for psset in "$@"; do
    case "$psset" in
        ps-a[12]|ps-b[12]|ps-c[12]|ps-d[12]|ps-e[12]|ps-f[12]|ps-g[12]|ps-h1|ps-i[12]) ;;
        *) echo "Unknown PS set: $psset" >&2; exit 2;;
    esac
    if [[ -d "$CALWORK/$psset" && ! -f "$CALWORK/launch-state/$psset.campaign" ]]; then
        # A failed create may leave empty directories; existing data need review.
        if [[ -n $(find "$CALWORK/$psset" -type f -name '*.root' -print -quit) ]]; then
            echo "Existing results at $CALWORK/$psset; use a new CALWORK." >&2
            exit 2
        fi
    fi
done
mkdir -p "$CALWORK/campaigns" "$CALWORK/plans" "$CALWORK/launch-state"
for psset in "$@"; do
    (cd "$source_dir/examples/yall/$psset" && yall-run validate && \
        yall-run plan > "$CALWORK/plans/$psset.txt")
done
for psset in "$@"; do
    ledger="$CALWORK/launch-state/$psset.campaign"
    started="$CALWORK/launch-state/$psset.started"
    if [[ -f "$ledger" ]]; then
        cam=$(cat "$ledger")
        if [[ -f "$started" ]]; then
            echo "$psset already submitted: $cam"
            continue
        fi
    else
        if ! cam=$(yall-run create "$source_dir/examples/yall/$psset/Yallfile" \
                   --campaigns-dir "$CALWORK/campaigns"); then
            echo "Creation failed for $psset; stopping." >&2; exit 1
        fi
        [[ "$cam" != *$'\n'* && -d "$cam" ]] || {
            echo "Unexpected campaign path: $cam" >&2; exit 1;
        }
        printf '%s\n' "$cam" > "$ledger"
        printf '%s %s\n' "$psset" "$cam" >> "$CALWORK/ps-campaigns.txt"
    fi
    if ! yall-run start "$cam"; then
        echo "Submission failed. Inspect with: yall-run status \"$cam\" -v" >&2
        exit 1
    fi
    touch "$started"
done
echo "Campaign list: $CALWORK/ps-campaigns.txt"
