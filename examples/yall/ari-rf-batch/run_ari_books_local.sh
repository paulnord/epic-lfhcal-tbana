#!/usr/bin/env bash
# From tcsh: /bin/bash run_ari_books_local.sh FRESH_ABSOLUTE_DEST [isolated|layer|robust|global]
set -euo pipefail
umask 077
verify() {
python3 - "$1" <<'PY'
import hashlib,json,pathlib,subprocess,sys
p=pathlib.Path(sys.argv[1]);m=json.loads((p/'preparation.json').read_text())
def digest(f):
    h=hashlib.sha256()
    with open(f,'rb') as s:
        for b in iter(lambda:s.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
if subprocess.check_output(['git','-C',str(p/'source'),'rev-parse','HEAD'],text=True).strip()!=m['commit']:raise SystemExit('Source commit changed')
if subprocess.check_output(['git','-C',str(p/'source'),'status','--porcelain','--untracked-files=no'],text=True).strip():raise SystemExit('Tracked source changed')
for r in m['files']:
    f=pathlib.Path(r['path']);st=f.stat()
    if st.st_size!=r['size'] or st.st_mtime_ns!=r['mtime_ns'] or digest(f)!=r['sha256']:raise SystemExit('Input changed: '+str(f))
if digest(p/'inputs.csv')!=m['manifest_sha256']:raise SystemExit('Manifest changed')
PY
}
if [[ ${1:-} == --payload ]]; then
    [[ $# == 2 && ${ARI_BOOKS_LOCAL_PAYLOAD:-} == 1 ]] || exit 2
    base=$2
    verify "$base"
    export ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1 CMAKE_BUILD_PARALLEL_LEVEL=1
    mkdir "$base/build" "$base/products"
    { date -u; hostname; root-config --version; cmake --version; git -C "$base/source" rev-parse HEAD; } > "$base/environment.txt"
    cmake -S "$base/source/NewStructure" -B "$base/build" -DBUILD_TESTING=OFF -DLFHCAL_USE_ADAPTIVE_LANGAU=OFF
    cmake --build "$base/build" --parallel 1 --target CombineWaveformBooks
    mode=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["scale"])' "$base/preparation.json")
    "$base/build/CombineWaveformBooks" "$base/inputs.csv" "$base/source/configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv" "$base/products/AllScans" "$mode"
    for pdf in "$base/products/AllScans_Unnormalized.pdf" "$base/products/AllScans_Normalized.pdf"; do
        [[ -s $pdf ]] || { echo "Missing output: $pdf" >&2; exit 1; }
        if command -v pdfinfo >/dev/null; then
            [[ $(pdfinfo "$pdf" | awk '/^Pages:/{print $2}') == 26 ]] || { echo "Unexpected page count: $pdf" >&2; exit 1; }
        fi
    done
    verify "$base"
    sha256sum "$base/products/AllScans_Unnormalized.pdf" "$base/products/AllScans_Normalized.pdf" > "$base/products/SHA256SUMS"
    printf 'Display-only local replay complete; scale=%s; source=%s\n' "$mode" "$(git -C "$base/source" rev-parse HEAD)" > "$base/products/BOOKS_READY"
    exit 0
fi
[[ $# -ge 1 && $# -le 2 ]] || { echo 'Usage: /bin/bash run_ari_books_local.sh FRESH_ABSOLUTE_DEST [isolated|layer|robust|global]' >&2; exit 2; }
dest=$1;mode=${2:-isolated}
[[ $mode == isolated || $mode == layer || $mode == robust || $mode == global ]] || exit 2
[[ $dest == /* && $dest != *[!a-zA-Z0-9_./-]* && ! -e $dest && ! -L $dest ]] || { echo 'Use a fresh absolute destination without spaces or shell metacharacters.' >&2; exit 2; }
[[ -z ${ARI_RF_BATCH_WORKER:-} && -z ${_CONDOR_JOB_AD:-} ]] || { echo 'This helper runs directly on the normal host, not in a batch worker.' >&2; exit 2; }
for cmd in git python3; do command -v "$cmd" >/dev/null; done
eic=${EIC_SHELL:-/star/u/pnord/bin/eic-shell}
[[ -x $eic && $eic == /* ]] || { echo 'Existing executable EIC_SHELL required.' >&2; exit 2; }
commit=${ARI_SOURCE_COMMIT:-}
[[ $commit =~ ^[0-9a-f]{40}$ ]] || { echo 'Set ARI_SOURCE_COMMIT to the full lowercase 40-hex reviewed commit.' >&2; exit 2; }
input_root=${ARI_INPUT_ROOT:-/gpfs01/star/scratch/pnord/ari-rebuild-eX4Mld}
run302=${ARI_RUN302_ROOT:-/gpfs01/star/scratch/pnord/ari-run302-annotations-bdLvhL/work}
python3 - "$dest" "$input_root" "$run302" "$mode" "$commit" <<'PY'
import csv,hashlib,json,os,pathlib,sys
out,base,r302,mode,commit=sys.argv[1:]
rf=[298,300,304,306,310,329,333,335,337,339,341,343,345]
other=[347,349,351,353,355,357,359,361,363]
header=['run','cell','status','has_peak','has_fwhm','peak_bin','left_bin','right_bin','amplitude','peak_time_ns','left_ns','right_ns','fwhm_ns','source']
def digest(f):
    h=hashlib.sha256()
    with open(f,'rb') as s:
        for b in iter(lambda:s.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
records=[];files=[]
for run in sorted(rf+other+[302]):
    p=pathlib.Path(r302) if run==302 else pathlib.Path(base)/('rf' if run in rf else 'other')
    root=p/f'products/waveform/calibratedHGCROC_wave_Run_{run}_Hists.root'
    csvpath=p/f'products/plots/waveform/Run{run}/WaveformGrid_Run{run}_Measurements.csv'
    for f in (root,csvpath):
        if not f.is_file() or not os.access(f,os.R_OK) or f.stat().st_size==0:raise SystemExit(f'Missing/empty/unreadable input: {f}')
        st=f.stat();sha=digest(f)
        if f.stat().st_mtime_ns!=st.st_mtime_ns or f.stat().st_size!=st.st_size:raise SystemExit(f'Input changed during hashing: {f}')
        files.append(dict(path=str(f.resolve()),size=st.st_size,mtime_ns=st.st_mtime_ns,sha256=sha))
    with csvpath.open(newline='') as f:
        reader=csv.reader(f)
        if next(reader,None)!=header:raise SystemExit(f'Wrong annotation CSV header: {csvpath}')
        rows=list(reader)
        if len(rows)!=64 or any(len(r)!=14 or r[0]!=str(run) for r in rows):raise SystemExit(f'Wrong run/row count: {csvpath}')
    records.append([run,str(root.resolve()),str(csvpath.resolve())])
p=pathlib.Path(out);p.mkdir(parents=True,exist_ok=False)
with (p/'inputs.csv').open('w',newline='') as f:
    writer=csv.writer(f);writer.writerow(['run','profile_root','measurements_csv']);writer.writerows(records)
(p/'preparation.json').write_text(json.dumps(dict(commit=commit,scale=mode,files=files,manifest_sha256=digest(p/'inputs.csv')),indent=2)+'\n')
print('Verified 23 saved ROOT/CSV pairs, including run 302. No event processing.')
PY
source=${ARI_SOURCE_REPO:-https://github.com/paulnord/epic-lfhcal-tbana.git}
git clone --no-checkout --no-hardlinks "$source" "$dest/source"
git -C "$dest/source" cat-file -e "$commit^{commit}" 2>/dev/null || git -C "$dest/source" fetch origin "$commit"
git -C "$dest/source" checkout --detach "$commit"
[[ -f $dest/source/NewStructure/CombineWaveformBooks.cc ]]
if [[ $mode == isolated ]]; then grep -q 'WaveformScale::IsolatedLayer' "$dest/source/NewStructure/CombineWaveformBooks.cc"; fi
verify "$dest"
cp -- "${BASH_SOURCE[0]}" "$dest/run_local_payload.sh"
unset -f which 2>/dev/null || true
# Match worker.sh's stdin command transport, including read's backslash layer.
quote_word() {
    local value=$1
    value=${value//\\/\\\\}
    local apostrophe="'\"'\"'"
    value=${value//\'/$apostrophe}
    printf "'%s'" "$value"
}
entry='set -euo pipefail; tmp=$(/usr/bin/mktemp -d /tmp/ari-books-local.XXXXXXXXXX); trap '\''rc=$?; /bin/rm -rf -- "$tmp" || true; exit "$rc"'\'' EXIT; export TMPDIR="$tmp" TMP="$tmp" TEMP="$tmp"; "$@"'
{
    for arg in /usr/bin/env ARI_BOOKS_LOCAL_PAYLOAD=1 /bin/bash -c "$entry" ari-books-local /bin/bash "$dest/run_local_payload.sh" --payload "$dest"; do quote_word "$arg"; printf ' '; done
    printf '\n'
} | "$eic" 2>&1 | tee "$dest/local-run.log"
# Some eic-shell versions may mask inner failures: require the verified marker.
[[ -s $dest/products/BOOKS_READY ]] || { echo "Local replay failed or incomplete. Inspect $dest/local-run.log; do not reuse this destination." >&2; exit 1; }
verify "$dest"
(cd "$dest/products"; sha256sum -c SHA256SUMS)
printf 'Local books ready: %s/products\n' "$dest"
