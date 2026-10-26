#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "Usage: bash $0 ORIGINAL_CAMPAIGN NEW_OUTPUT_DIRECTORY" >&2
  exit 2
fi
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export CAMPAIGN="$1" OUT="$2"
command -v root-config >/dev/null
python3 -c 'import ROOT'
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
