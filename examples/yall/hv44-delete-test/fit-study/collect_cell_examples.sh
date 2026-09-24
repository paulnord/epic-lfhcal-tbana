#!/usr/bin/env bash
# Collect existing BNL ROOT histograms; no calibration/event processing.
set -euo pipefail
if [[ $# != 5 ]]; then
  printf 'Usage: bash %s EIC_WRAPPER EIC_SHELL HISTOGRAM_ROOT CALIBRATION_TEXT OUTPUT_PARENT\n' "$0" >&2
  exit 2
fi
sample_wrapper=$1
sample_eic_shell=$2
sample_input=$3
sample_calib=$4
sample_parent=$5
sample_script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
sample_macro="$sample_script_dir/export_cell_examples.C"
[[ -x "$sample_wrapper" && -x "$sample_eic_shell" && -f "$sample_input" && -f "$sample_calib" && -f "$sample_macro" && -d "$sample_parent" ]]
command -v sha256sum >/dev/null
sample_out=$(mktemp -d "$sample_parent/cell-examples-XXXXXX")
trap 'printf "Export failed; partial outputs preserved in %s\n" "$sample_out" >&2' ERR
printf 'Results: %s\n' "$sample_out"
sha256sum "$sample_input" "$sample_calib" "$sample_macro" "${BASH_SOURCE[0]}" > "$sample_out/input-and-code.sha256"
date -u '+Started: %Y-%m-%dT%H:%M:%SZ' > "$sample_out/run.txt"
sample_start=$SECONDS
sample_command=("$sample_wrapper" "$sample_eic_shell" /usr/bin/env
  "CELL_SAMPLE_INPUT=$sample_input" "CELL_SAMPLE_CALIB=$sample_calib"
  "CELL_SAMPLE_OUT=$sample_out/export" root -l -b -q "$sample_macro")
printf '%q ' "${sample_command[@]}" >> "$sample_out/run.txt"
printf '\n' >> "$sample_out/run.txt"
if "${sample_command[@]}" > "$sample_out/export.log" 2>&1; then
  sample_status=0
else
  sample_status=$?
fi
printf 'Exit status: %s\nElapsed seconds: %s\n' "$sample_status" "$((SECONDS-sample_start))" >> "$sample_out/run.txt"
date -u '+Finished: %Y-%m-%dT%H:%M:%SZ' >> "$sample_out/run.txt"
if [[ $sample_status != 0 ]]; then
  cat "$sample_out/export.log" >&2
  printf 'Export failed; partial outputs preserved in %s\n' "$sample_out" >&2
  exit "$sample_status"
fi
sha256sum --check "$sample_out/input-and-code.sha256" > "$sample_out/input-check.log"
cat "$sample_out/export/summary.txt"
[[ ! -e "$sample_out.tgz" && ! -e "$sample_out.tgz.sha256" ]]
tar -czf "$sample_out.tgz" -C "$sample_out" .
(
  cd -- "$(dirname -- "$sample_out")"
  sha256sum "${sample_out##*/}.tgz"
) > "$sample_out.tgz.sha256"
printf '\nTransfer these two files back to the Mac:\n%s\n%s\n' "$sample_out.tgz" "$sample_out.tgz.sha256"
