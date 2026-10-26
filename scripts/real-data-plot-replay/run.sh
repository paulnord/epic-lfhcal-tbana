#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "Usage: bash $0 ORIGINAL_CAMPAIGN NEW_OUTPUT_DIRECTORY" >&2
  exit 2
fi
prerequisite_failure() {
  printf 'ERROR: %s\n' "$1" >&2
  printf '%s\n' 'Activate your usual ROOT environment, including matching Python3/PyROOT, in this terminal; then rerun with bash.' >&2
  printf '%s\n' 'The launcher has not changed your environment or created an output directory.' >&2
  exit 1
}
if ! command -v root-config >/dev/null 2>&1; then
  prerequisite_failure 'root-config is not on PATH; ROOT is not active in this shell.'
fi
if ! command -v python3 >/dev/null 2>&1; then
  prerequisite_failure 'python3 is not on PATH.'
fi
if ! python3 - <<'PREREQUISITES'
import subprocess, sys
try:
    import ROOT
except Exception as exc:
    sys.exit('ERROR: python3 cannot import PyROOT: '+str(exc))
try:
    configured=subprocess.check_output(['root-config','--version'],text=True,stderr=subprocess.STDOUT).strip()
except (OSError,subprocess.CalledProcessError) as exc:
    sys.exit('ERROR: root-config --version failed: '+str(exc))
loaded=ROOT.gROOT.GetVersion().replace('/','.')
if loaded!=configured:
    sys.exit('ERROR: PyROOT version '+loaded+' differs from root-config '+configured+'.')
print('ROOT/PyROOT prerequisites OK: '+configured,flush=True)
PREREQUISITES
then
  prerequisite_failure 'ROOT/PyROOT prerequisite check failed (details above).'
fi
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export CAMPAIGN="$1" OUT="$2"
python3 - "$HERE" <<'PY'
import os, shutil, sys
from pathlib import Path
source=Path(sys.argv[1]); campaign=Path(os.environ['CAMPAIGN']).resolve(); out=Path(os.environ['OUT']).resolve()
if out==campaign or campaign in out.parents:
    raise SystemExit('Output must be outside the original campaign')
out.mkdir()  # Deliberately refuse existing directories; never overwrite a run.
for name in ('replay.cc','run.py'): shutil.copyfile(source/name,out/name)
PY
python3 "$OUT/run.py"
