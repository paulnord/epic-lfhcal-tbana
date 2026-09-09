#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "usage: $0 /path/to/rawHGCROC_wPedwMuon_wBC_ImpR_308_Hists.root [output-dir]" >&2
    exit 2
fi

HIST=$1
OUT=${2:-refine1-mcmc/cell-1473/full}
mkdir -p "$OUT"

pids=()
for i in 0 1 2 3; do
    python3 run_refine1_chain.py \
        --hist "$HIST" \
        --cell 1473 \
        --init broad \
        --chain "$i" \
        --iterations 20000 \
        --output "$OUT/chain-0${i}.tsv" &
    pids+=("$!")
done

for i in 4 5 6 7; do
    python3 run_refine1_chain.py \
        --hist "$HIST" \
        --cell 1473 \
        --init collapsed \
        --chain "$i" \
        --iterations 20000 \
        --output "$OUT/chain-0${i}.tsv" &
    pids+=("$!")
done

for pid in "${pids[@]}"; do
    wait "$pid"
done

chains=(
    "$OUT/chain-00.tsv"
    "$OUT/chain-01.tsv"
    "$OUT/chain-02.tsv"
    "$OUT/chain-03.tsv"
    "$OUT/chain-04.tsv"
    "$OUT/chain-05.tsv"
    "$OUT/chain-06.tsv"
    "$OUT/chain-07.tsv"
)

python3 combine_refine1_mcmc.py \
    "${chains[@]}" \
    --burn 3000 \
    --output "$OUT/posterior.tsv" \
    --summary "$OUT/summary.txt"

python3 plot_refine1_mcmc.py \
    --posterior "$OUT/posterior.tsv" \
    --chains "${chains[@]}" \
    --hist "$HIST" \
    --cell 1473 \
    --outdir "$OUT/plots"

cat "$OUT/summary.txt"
echo "plots: $OUT/plots"
