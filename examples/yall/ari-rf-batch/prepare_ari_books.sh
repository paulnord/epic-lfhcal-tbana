#!/usr/bin/env bash
# Preparation only. Safe to invoke from tcsh: /bin/bash prepare_ari_books.sh DEST [layer|robust|global]
set -euo pipefail
umask 077
[[ $# -le 2 ]] || { echo 'Usage: /bin/bash prepare_ari_books.sh FRESH_ABSOLUTE_DEST [layer|robust|global]' >&2; exit 2; }
dest=${1:-/gpfs01/star/scratch/pnord/ari-books-20261111}; mode=${2:-layer}
[[ $mode == layer || $mode == robust || $mode == global ]] || { echo 'Scale must be layer, robust or global.' >&2; exit 2; }
[[ $dest == /* && $dest != *[!a-zA-Z0-9_./-]* && ! -e $dest ]] || { echo 'Use a fresh absolute destination, with no spaces or shell metacharacters.' >&2; exit 2; }
[[ -z ${ARI_RF_BATCH_WORKER:-} && -z ${_CONDOR_JOB_AD:-} ]] || { echo 'Preparation belongs on the normal host shell.' >&2; exit 2; }
for cmd in git python3 yall-run; do command -v "$cmd" >/dev/null || { echo "Missing command: $cmd" >&2; exit 2; }; done
version=$(yall-run --version)
python3 - "$version" <<'PYVERSION'
import re,sys
m=re.search(r'(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?',sys.argv[1])
if not m:raise SystemExit('Cannot parse yall-run version; require 0.12.0a7 or newer')
v=tuple(map(int,m.group(1,2,3)))+({'a':0,'b':1,'rc':2,None:3}[m[4]],int(m[5] or 0))
if v<(0,12,0,0,7):raise SystemExit('Require yall-run 0.12.0a7 or newer; no installation changed')
PYVERSION
eic=${EIC_SHELL:-/star/u/pnord/bin/eic-shell}
[[ -x $eic && $eic == /* && $eic != *[!a-zA-Z0-9_./-]* ]] || { echo 'Set EIC_SHELL to the existing executable EIC launcher.' >&2; exit 2; }
commit=008e973fec634aed9c33c6b23c252623c7d195ad
input_root=${ARI_INPUT_ROOT:-/gpfs01/star/scratch/pnord/ari-rebuild-eX4Mld}
run302=${ARI_RUN302_ROOT:-/gpfs01/star/scratch/pnord/ari-run302-annotations-bdLvhL/work}
# Bounded filesystem/CSV preflight only; do not read ROOT on the login host.
python3 - "$dest" "$input_root" "$run302" "$mode" "$commit" <<'PY'
import csv,hashlib,json,os,pathlib,sys
out,base,r302,mode,commit=sys.argv[1:]
rf=[298,300,304,306,310,329,333,335,337,339,341,343,345]
other=[347,349,351,353,355,357,359,361,363]
header=['run','cell','status','has_peak','has_fwhm','peak_bin','left_bin','right_bin','amplitude','peak_time_ns','left_ns','right_ns','fwhm_ns','source']
records=[]
for run in sorted(rf+other+[302]):
    p=pathlib.Path(r302) if run==302 else pathlib.Path(base)/('rf' if run in rf else 'other')
    root=p/f'products/waveform/calibratedHGCROC_wave_Run_{run}_Hists.root'
    csvpath=p/f'products/plots/waveform/Run{run}/WaveformGrid_Run{run}_Measurements.csv'
    row={'run':run,'profile_root':str(root),'measurements_csv':str(csvpath),'files':[]}
    for f in (root,csvpath):
        if not f.is_file() or not os.access(f,os.R_OK) or f.stat().st_size==0: raise SystemExit(f'Missing/empty/unreadable input: {f}')
        st=f.stat();row['files'].append({'path':str(f),'size':st.st_size,'mtime_ns':st.st_mtime_ns})
    with csvpath.open(newline='') as f:
        reader=csv.reader(f)
        if next(reader,None)!=header: raise SystemExit(f'Wrong annotation CSV header: {csvpath}')
        rows=list(reader)
        if len(rows)!=64 or any(len(r)!=14 or r[0]!=str(run) for r in rows): raise SystemExit(f'Wrong run/row count: {csvpath}')
    row['csv_sha256']=hashlib.sha256(csvpath.read_bytes()).hexdigest();records.append(row)
path=pathlib.Path(out);path.mkdir(parents=True,exist_ok=False)
with (path/'inputs.csv').open('w',newline='') as f:
    writer=csv.writer(f);writer.writerow(['run','profile_root','measurements_csv'])
    writer.writerows([r['run'],r['profile_root'],r['measurements_csv']] for r in records)
(path/'preparation.json').write_text(json.dumps({'commit':commit,'scale':mode,'inputs':records},indent=2)+'\n')
print(f'Preflight passed: {len(records)} exact ROOT/CSV pairs. No ROOT processing performed.')
PY
# A local repository can be used as a verified source; never alter that checkout.
source=${ARI_SOURCE_REPO:-https://github.com/paulnord/epic-lfhcal-tbana.git}
git clone --no-checkout --no-hardlinks "$source" "$dest/source"
git -C "$dest/source" cat-file -e "$commit^{commit}" 2>/dev/null || git -C "$dest/source" fetch origin "$commit"
git -C "$dest/source" checkout --detach "$commit"
[[ $(git -C "$dest/source" rev-parse HEAD) == "$commit" ]]
[[ -f "$dest/source/NewStructure/CombineWaveformBooks.cc" && -f "$dest/source/NewStructure/Tests/test_waveform_books.cc" ]]
# Decoder is intentionally not initialized: these plotting/test targets do not need it.
git -C "$dest/source" submodule status > "$dest/submodules.txt"
cat > "$dest/run_books.sh" <<'WORKER'
#!/usr/bin/env bash
set -euo pipefail
[[ ${ARI_RF_BATCH_WORKER:-} == 1 ]] || { echo 'Build/ROOT replay must run in the Condor/EIC worker.' >&2; exit 2; }
base=$1
verify_inputs() {
python3 - "$base" <<'PY'
import hashlib,json,pathlib,subprocess,sys
p=pathlib.Path(sys.argv[1]);m=json.loads((p/'preparation.json').read_text())
if subprocess.check_output(['git','-C',str(p/'source'),'rev-parse','HEAD'],text=True).strip()!=m['commit']:raise SystemExit('Source commit changed')
if subprocess.check_output(['git','-C',str(p/'source'),'status','--porcelain','--untracked-files=no'],text=True).strip():raise SystemExit('Tracked source changed')
for r in m['inputs']:
    for record in r['files']:
        st=pathlib.Path(record['path']).stat()
        if st.st_size!=record['size'] or st.st_mtime_ns!=record['mtime_ns']:raise SystemExit('Input changed: '+record['path'])
    if hashlib.sha256(pathlib.Path(r['measurements_csv']).read_bytes()).hexdigest()!=r['csv_sha256']:raise SystemExit('CSV content changed')
PY
}
verify_inputs
mode=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["scale"])' "$base/preparation.json")
mkdir -p "$base/build" "$base/products"
{ date -u; hostname; root-config --version; cmake --version; git -C "$base/source" rev-parse HEAD; } > "$base/environment.txt"
cmake -S "$base/source/NewStructure" -B "$base/build" -DBUILD_TESTING=ON -DLFHCAL_USE_ADAPTIVE_LANGAU=OFF
cmake --build "$base/build" --parallel 2 --target CombineWaveformBooks test_waveform_books test_waveform_annotations test_waveform_measurement test_fit_curve_legend
ctest --test-dir "$base/build" --output-on-failure -R '^(waveform_books|waveform_annotations|waveform_measurement|fit_curve_legend_lifetime)$'
"$base/build/CombineWaveformBooks" "$base/inputs.csv" "$base/source/configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv" "$base/products/AllScans" "$mode"
# Count pages when Poppler is available. The writer's fixed inventory always has26.
if command -v pdfinfo >/dev/null; then
    for p in "$base/products/AllScans_Unnormalized.pdf" "$base/products/AllScans_Normalized.pdf"; do
        [[ $(pdfinfo "$p" | awk '/^Pages:/{print $2}') == 26 ]] || { echo "Unexpected page count: $p" >&2; exit 1; }
    done
fi
verify_inputs
sha256sum "$base/products/AllScans_Unnormalized.pdf" "$base/products/AllScans_Normalized.pdf" > "$base/products/SHA256SUMS"
printf 'Display-only replay complete: two 26-page books, scale=%s\n' "$mode" > "$base/products/BOOKS_READY"
WORKER
chmod +x "$dest/run_books.sh"
cat > "$dest/Yallfile" <<YALL
campaign ari-combined-waveform-books
backend condor
%account-provenance off
%cpus 2
%memory 4GB
%disk 8GB
%time 2h
%getenv true
%wrapper $dest/source/examples/yall/ari-rf-batch/worker.sh $eic /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1

books:
    %retry 0
    @input runner $dest/run_books.sh
    @input manifest $dest/inputs.csv
    @input provenance $dest/preparation.json
    @output absolute $dest/products/AllScans_Unnormalized.pdf
    @output normalized $dest/products/AllScans_Normalized.pdf
    @output ready $dest/products/BOOKS_READY
    /bin/bash @input.runner $dest
YALL
cd "$dest"
yall-run --version | tee yall-version.txt
yall-run validate | tee validation.log
yall-run plan | tee plan.txt
printf '\nPrepared only. NO JOBS SUBMITTED.\nDestination: %s\nScale: %s\n' "$dest" "$mode"
cat > "$dest/submit_books.sh" <<'SUBMIT'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ ! -e campaign-path.txt ]] || { echo 'Campaign already created; inspect campaign-path.txt and status rather than resubmit.' >&2; exit 2; }
campaign=$(yall-run create --campaigns-dir "$PWD/campaigns")
[[ -n $campaign && -f "$campaign/campaign.json" ]] || { echo 'No verified campaign directory returned; nothing submitted.' >&2; exit 2; }
printf '%s\n' "$campaign" > campaign-path.txt
yall-run status "$campaign"
yall-run start "$campaign"
yall-run status "$campaign"
SUBMIT
chmod +x "$dest/submit_books.sh"
printf 'Review the plan above. To submit explicitly, run:\n/bin/bash %s/submit_books.sh\n' "$dest"
printf 'Primary outputs: %s/products/AllScans_Unnormalized.pdf\n%s/products/AllScans_Normalized.pdf\n' "$dest" "$dest"
printf 'After BOOKS_READY exists, include this entire new workspace in your archive: %s\n' "$dest"
