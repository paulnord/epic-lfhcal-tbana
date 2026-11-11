#!/usr/bin/env bash
# Call with /bin/bash from a normal host shell (including tcsh).
# This process may exit on error without closing its caller's interactive shell.
set -euo pipefail
[[ $# == 1 ]] || { echo 'Usage: /bin/bash launch_waveform_annotations.sh FRESH_BASE' >&2; exit 2; }
base=$1
repo=$(cd -L "$(dirname "$0")/../../.." && pwd -L)
[[ -d "$base" && ! -e "$base/work" ]] || { echo 'Base must exist and work must be fresh.' >&2; exit 2; }
[[ -z ${ARI_RF_BATCH_WORKER:-} && -z ${_CONDOR_JOB_AD:-} ]] || { echo 'Submit from the normal host shell, not a worker.' >&2; exit 2; }
for command in python3 git yall-run condor_submit condor_submit_dag; do
    command -v "$command" >/dev/null || { echo "Missing host command: $command" >&2; exit 2; }
done
yall-run --version | tee "$base/yall-version.txt"
python3 - "$base/yall-version.txt" <<'PY'
import re, sys
s = open(sys.argv[1]).read()
m = re.search(r'(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?', s)
if not m:
    raise SystemExit('Cannot read yall-run version; require 0.12.0a7 or later.')
v = tuple(map(int, m.group(1,2,3))) + ({'a':0,'b':1,'rc':2,None:3}[m[4]], int(m[5] or 0))
if v < (0,12,0,0,7):
    raise SystemExit('Require host yall-run 0.12.0a7 or later; no installation was changed.')
PY
# The fallback is the documented BNL launcher, and must actually exist.
eic=${EIC_SHELL:-/star/u/pnord/bin/eic-shell}
[[ -f "$eic" && -x "$eic" ]] || { echo "EIC launcher is not executable: $eic. Set EIC_SHELL to the existing launcher." >&2; exit 2; }
echo "EIC launcher: $eic"
git -C "$repo" rev-parse HEAD | tee "$base/source-commit.txt"
git -C "$repo" submodule status | tee "$base/submodules.txt"
[[ -f "$repo/NewStructure/h2g_decode/CMakeLists.txt" ]] || { echo 'Pinned decoder is missing; initialize submodules in this fresh checkout.' >&2; exit 2; }
[[ -z $(git -C "$repo" status --porcelain --untracked-files=no) ]] || { echo 'Source has tracked changes; use an immutable checkout.' >&2; exit 2; }
root=${ARI_ANNOTATION_SEARCH_ROOT:-/gpfs01/star/scratch/pnord}
# Metadata discovery only. Explicit campaign paths may be supplied by running
# prepare_waveform_annotations.py directly when discovery reports ambiguity.
python3 "$repo/examples/yall/ari-rf-batch/prepare_waveform_annotations.py" \
    --destination "$base/work" --search-root "$root" --eic-shell "$eic" --interactive | tee "$base/preparation.log"
cd "$base/work"
yall-run validate | tee "$base/validation.log"
yall-run plan | tee "$base/plan.txt"
printf '\nExpected: one build + 23 waveform tasks, no conversion or calibration.\n'
printf 'All new products: %s/work/products\n' "$base"
printf 'Review the input list and plan above. Type SUBMIT 23 to submit, or Enter to keep preparation only: '
IFS= read -r answer </dev/tty
[[ "$answer" == 'SUBMIT 23' ]] || { echo 'Prepared only. No jobs submitted.'; exit 0; }
campaign=$(yall-run create --campaigns-dir "$base/campaigns")
[[ -n "$campaign" && -f "$campaign/campaign.json" ]] || { echo 'Creation did not return a verified campaign directory; not submitting.' >&2; exit 2; }
printf '%s\n' "$campaign" | tee "$base/campaign-path.txt"
yall-run status "$campaign"
yall-run start "$campaign"
yall-run status "$campaign"
printf '\nCampaign: %s\nProducts: %s/work/products/plots/waveform/Run<RUN>/\n' "$campaign" "$base"
echo 'No automatic retries. Inspect worker logs, paired PDFs and CSVs; preserve old inputs and partial outputs.'
