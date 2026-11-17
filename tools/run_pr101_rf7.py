#!/usr/bin/env python3
"""Download PR101 and prepare/submit an isolated RF7 QA test through BNL Condor.

Host use (tcsh is fine): python3 run_pr101_rf7.py --submit
No ROOT/build/analysis runs on the submission host. Existing RF7 data is read only.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

PIN = 'dedad9bb937ba4a97b6122da76f80129161d58fa'
DECODER_PIN = '2a7f7d4e8b760ff9f9406e36d31e99c5b6fffa2c'
REPOSITORY = 'https://github.com/paulnord/epic-lfhcal-tbana.git'
PARENT = Path('/gpfs01/star/pwg/pnord/eic/2026TBdata/analyzed')
RF7 = PARENT / 'ari-rf7-cs939lgs'
INPUT = RF7 / 'work/products/calibrated/calibratedHGCROC_Run_331.root'
RUNS = RF7 / 'source/configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv'
EIC = Path('/star/u/pnord/bin/eic-shell')

RUNNER = r'''#!/usr/bin/env bash
set -euo pipefail
work=$1
input=$2
runs=$3
n=$4
[[ -n ${_CONDOR_JOB_AD:-} || ${PR101_CONDOR_WORKER:-} == 1 ]] || { echo 'Condor worker required' >&2; exit 2; }
tmp=$(/usr/bin/mktemp -d /tmp/pr101-rf7.XXXXXXXXXX)
trap 'rm -rf -- "$tmp"' EXIT
export TMPDIR="$tmp" TMP="$tmp" TEMP="$tmp"
export ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1
cd "$work"
root-config --version
[[ -s source/NewStructure/h2g_decode/CMakeLists.txt && -s source/NewStructure/h2g_decode/src/hgc_decoder.h ]] || { echo 'Pinned decoder missing on worker; stopping before build' >&2; exit 2; }
cmake -S source/NewStructure -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target DataAna --parallel 2
export LD_LIBRARY_PATH="$work/build${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export ROOT_INCLUDE_PATH="$work/source/NewStructure${ROOT_INCLUDE_PATH:+:$ROOT_INCLUDE_PATH}"
export QA_INPUT="$input" QA_RUNS="$runs"
# The shared dictionary loads before this macro. Match the actual run-list reader.
root -l -b -q -e 'if(gSystem->Load("./build/libLFHCAL.so")<0) gSystem->Exit(10);' preflight.C
stat -Lc '%s %Y' "$input" > input.before.stat
sha256sum source/NewStructure/DataAna.cc "$runs" > provenance.sha256
for case_name in fallback precedence; do
  mkdir "$case_name"
  args=(-Q -a -n "$n" -i "$input" -r "$runs" -O "$work/$case_name/hist.root" -P "$work/$case_name/plots")
  if [[ "$case_name" == precedence ]]; then args+=(-o "$work/precedence/tree.root"); fi
  printf '%q ' "$work/build/DataAna" "${args[@]}" > "$case_name/command.txt"
  printf '\n' >> "$case_name/command.txt"
  "$work/build/DataAna" "${args[@]}" > "$case_name/run.log" 2>&1
  calib="$work/$case_name/hist_calib.txt"
  if [[ "$case_name" == precedence ]]; then
    calib="$work/precedence/tree_calib.txt"
    [[ ! -e "$work/precedence/hist_calib.txt" ]]
  fi
  grep -q '#Calib info:' "$calib"
  export QA_CHECK_FILE="$work/$case_name/hist.root"
  root -l -b -q -e 'TFile f(gSystem->Getenv("QA_CHECK_FILE"),"READ"); gSystem->Exit(f.IsZombie() || f.TestBit(TFile::kRecovered) || f.GetNkeys()==0);'
done
stat -Lc '%s %Y' "$input" > input.after.stat
cmp input.before.stat input.after.stat
printf 'PASS: RF7 full QA, -O fallback and -o precedence, %s events per invocation. Not physics validation.\n' "$n" > SUCCESS.txt
cat SUCCESS.txt
'''
PREFLIGHT = r'''#include "Event.h"
#include "CommonHelperFunctions.h"
#include "TFile.h"
#include "TTree.h"
void preflight() {
  TFile f(gSystem->Getenv("QA_INPUT"), "READ");
  if (f.IsZombie()) gSystem->Exit(2);
  auto s=dynamic_cast<TTree*>(f.Get("Setup"));
  auto d=dynamic_cast<TTree*>(f.Get("Data"));
  auto c=dynamic_cast<TTree*>(f.Get("Calib"));
  if (!s || !d || !c || s->GetEntries()<1 || d->GetEntries()<1 || c->GetEntries()<1 || !s->GetBranch("setup") || !d->GetBranch("event") || !c->GetBranch("calib")) gSystem->Exit(3);
  Event* event=nullptr;
  if (d->SetBranchAddress("event", &event)<0 || d->GetEntry(0)<=0 || !event) gSystem->Exit(4);
  auto runs=readRunInfosFromFile(gSystem->Getenv("QA_RUNS"),0,0);
  std::cout << "First event run: " << event->GetRunNumber() << std::endl;
  if (event->GetRunNumber()!=331 || runs.find(331)==runs.end()) gSystem->Exit(5);
  gSystem->Exit(0);
}
'''

def run(args, **kwargs):
    print('+ ' + shlex.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str,args)), check=True, **kwargs)

def safe_path(path):
    if not path.is_absolute() or re.search(r'[^A-Za-z0-9_/.-]', str(path)) or '.root' in str(path.parent):
        raise ValueError('Use an absolute path with no spaces/shell characters or .root in parent directories: '+str(path))

def submit_text(work):
    return f'''universe = vanilla
executable = /usr/bin/env
arguments = python3 {work}/run_pr101_rf7.py --worker {work}
initialdir = {work}
getenv = True
should_transfer_files = NO
request_cpus = 2
request_memory = 8GB
request_disk = 8GB
+MaxRuntime = 7200
output = {work}/job.out
error = {work}/job.err
log = {work}/job.events
queue 1
'''

def prepare(args):
    for p in (args.parent,args.input,args.runs,args.eic_shell): safe_path(p)
    if not args.parent.is_dir() or not os.access(args.parent,os.W_OK):
        raise ValueError('Output parent is not writable: '+str(args.parent))
    for p in (args.input,args.runs):
        if not p.is_file() or not os.access(p,os.R_OK) or p.stat().st_size==0:
            raise ValueError('Missing/unreadable/empty input: '+str(p))
    if not args.eic_shell.is_file() or not os.access(args.eic_shell,os.X_OK):
        raise ValueError('Missing executable EIC launcher: '+str(args.eic_shell))
    for tool in ('git','condor_submit'):
        if not shutil.which(tool): raise ValueError('Missing host tool: '+tool)
    if args.events<1: raise ValueError('--events must be positive')
    work=Path(tempfile.mkdtemp(prefix='pr101-rf7-',dir=str(args.parent)))
    print('Workspace: '+str(work),flush=True)
    run(['git','clone','--no-checkout',REPOSITORY,work/'source'])
    # The pinned commit belongs to the public fork, so its branch clone obtains it.
    run(['git','-C',work/'source','checkout','--detach',PIN])
    actual=run(['git','-C',work/'source','rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
    if actual!=PIN: raise ValueError('Unexpected source revision')
    # DataAna links Analysis, whose HGCROC_Convert.cc requires decoder headers.
    # Match the original RF7 setup even though this test does not decode raw data.
    run(['git','-C',work/'source','submodule','update','--init','--recursive'])
    decoder=work/'source/NewStructure/h2g_decode'
    decoder_sha=run(['git','-C',decoder,'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
    if decoder_sha!=DECODER_PIN: raise ValueError('Unexpected decoder revision; no job submitted')
    for required in ('CMakeLists.txt','src/hgc_decoder.h'):
        if not (decoder/required).is_file(): raise ValueError('Missing decoder file: '+str(decoder/required))
    shutil.copyfile(Path(__file__),work/'run_pr101_rf7.py')
    (work/'worker.sh').write_text(RUNNER)
    (work/'preflight.C').write_text(PREFLIGHT)
    (work/'parameters.json').write_text(json.dumps({'pin':PIN,'decoder_pin':DECODER_PIN,'input':str(args.input),'runs':str(args.runs),'eic_shell':str(args.eic_shell),'events':args.events},indent=2)+'\n')
    sub=work/'test.sub';sub.write_text(submit_text(work))
    run(['condor_submit','-dry-run',work/'submit.ad',sub])
    if args.submit:
        # One attempt only. An uncertain submission is NOT automatically retried.
        run(['condor_submit',sub])
        print('Submitted, not completed. Look for SUCCESS.txt in '+str(work))
    else:
        print('Prepared only. Submit from tcsh: condor_submit '+str(sub))
    print('Logs: '+str(work/'job.out')+' and '+str(work/'job.err'))
    print('Monitor: condor_q pnord; results remain in '+str(work))
    return work

def worker(work):
    if not os.environ.get('_CONDOR_JOB_AD'): raise ValueError('Worker execution requires Condor; do not run on login node')
    params=json.loads((work/'parameters.json').read_text())
    if (work/'SUCCESS.txt').exists() or (work/'fallback').exists() or (work/'precedence').exists():
        raise ValueError('Prior output exists; refusing worker retry/overwrite')
    args=['/usr/bin/env','PR101_CONDOR_WORKER=1','/bin/bash',str(work/'worker.sh'),str(work),params['input'],params['runs'],str(params['events'])]
    # Same stdin transport as the RF7 campaign. eic-shell uses read without -r.
    line=shlex.join(args).replace('\\','\\\\')+'\n'
    run([params['eic_shell']],input=line,text=True)
    if not (work/'SUCCESS.txt').is_file(): raise ValueError('Container returned without SUCCESS.txt; inspect job.out/job.err and case logs')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--submit',action='store_true')
    p.add_argument('--events',type=int,default=1000)
    p.add_argument('--parent',type=Path,default=PARENT)
    p.add_argument('--input',type=Path,default=INPUT)
    p.add_argument('--runs',type=Path,default=RUNS)
    p.add_argument('--eic-shell',type=Path,default=EIC)
    p.add_argument('--worker',type=Path,help=argparse.SUPPRESS)
    args=p.parse_args()
    try:
        if args.worker: worker(args.worker)
        else: prepare(args)
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        print('STOPPED: '+str(exc)+'\nWorkspace/logs retained. Do not blindly repeat a submission.',file=sys.stderr)
        return 1
    return 0
if __name__=='__main__': sys.exit(main())
