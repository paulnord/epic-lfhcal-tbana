from pathlib import Path
import re
lf=Path(__file__).resolve().parent
for which in ('scan-set-1','scan-set-2'):
    p=lf/f'examples/yall/{which}/Yallfile'
    s=p.read_text()
    m=re.search(r'    @each ped run: (?:\\\n)(.*?)(?=    @input)',s,re.S)
    assert m
    values=m.group(1).replace('\\','').split()
    pairs=list(zip(values[::2], values[1::2]))
    table='# Scientific configuration: pedestal / muon run pairs, declared once.\n@table pairs ped run:\n'+''.join(f'    {ped} {run}\n' for ped,run in pairs)+'\n'
    s=s.replace('prepare:\n',table+'prepare:\n',1)
    a=s.index('# Convert pedestal and muon runs as separate task families')
    b=s.index('pedestal-{ped}-{run}:',a)
    block=s[s.index('convert-muon-{run}: prepare',a):b]
    block=re.sub(r'    @each run.*?(?=    @input)', '    @each run in pairs.ped pairs.run\n', block, count=1, flags=re.S)
    block=block.replace('convert-muon-{run}:','convert-{run}:',1)
    s=s[:a]+'# Convert every unique run once; dependencies below remain per run/pair.\n'+block+s[b:]
    s=s.replace('pedestal-{ped}-{run}: convert-ped-{ped}', 'pedestal-{ped}: convert-{ped}')
    s=re.sub(r'    @each ped run:.*?(?=    @input)','    @each ped in pairs.ped\n',s,count=1,flags=re.S)
    s=s.replace('transfer-{ped}-{run}: pedestal-{ped}-{run} convert-muon-{run}\n', 'transfer-{ped}-{run}: pedestal-{ped} convert-{run}\n    @each ped run in pairs\n')
    p.write_text(s)
p=lf/'examples/yall/lfhcal-simple/Yallfile'
s=p.read_text()
s=s.replace('prepare:\n', '# Scientific configuration: pedestal / MIP run pairs, declared once.\n@table pairs ped mip:\n    296 298\n    299 300\n    303 304\n\nprepare:\n',1)
s=s.replace('# Pattern 1: run the same command for a list of runs.', '# Pattern 1: one conversion per unique run from either column.')
s=s.replace('    @each run 296 298 299 300 303 304', '    @each run in pairs.ped pairs.mip')
a=s.index('# Keep the introductory dependency simple:')
b=s.index('    @input raw {WORK}/converted/rawHGCROC_{ped}.root',a)
s=s[:a]+'''# Pattern 2: fit each unique pedestal, then apply it to its paired MIP runs.
pedestal-{ped}: convert-{ped}
    @each ped in pairs.ped
'''+s[b:]
s=s.replace('calibration-{ped}-{mip}: pedestal-{ped}-{mip}\n', 'calibration-{ped}-{mip}: pedestal-{ped} convert-{mip}\n    @each ped mip in pairs\n')
s=s.replace('# Pattern 3: run another analysis for a separate list of runs.', '# Pattern 3: summarize each MIP run without repeating its list.')
s=s.replace('summary-{run}: converted\n    @each run 298 300 304', 'summary-{run}: convert-{run}\n    @each run in pairs.mip')
p.write_text(s)
p=lf/'examples/yall/lfhcal-simple/README.md'
s=p.read_text()
s=s.replace('1. Convert a list of raw runs.\n2. Create calibrations from a list of pedestal/MIP pairs.\n3. Create summaries from another list of runs.', '1. Convert every unique run from a top-level pedestal/MIP table.\n2. Fit each pedestal once and calibrate the correlated pairs.\n3. Create summaries from the MIP column, without repeating the run list.')
s=s.replace('The example deliberately uses a simple `converted` barrier. It waits for all raw conversions before starting the calibration and summary tasks. The production scan-set examples use finer-grained dependencies for more parallelism.', 'The `pairs` table is the single source of run numbers. `@each run in pairs.ped pairs.mip` creates one conversion per unique run, even when a pedestal is shared. Pedestal fitting waits only for its own conversion; each calibration waits for its pedestal fit and MIP conversion. Summaries wait only for their own conversion. There is no all-conversions barrier. The default example has 16 tasks.\n\nUse a yall-run checkout with combined named-source support from PR #26 (`feat/each-source-union` until merged); PR #25 alone supports only one source after `in`. See the parent README for runner setup. Existing frozen campaigns are unaffected.')
p.write_text(s)
p=lf/'examples/yall/README.md'
s=p.read_text()
a=s.index('The Condor examples require **yall-run with `%time` support**')
b=s.index('\n\n## Where to start',a)
s=s[:a]+'''`lfhcal-simple`, `scan-set-1`, and `scan-set-2` require **combined named-source
`@each` support** from [yall-run PR #26](https://github.com/paulnord/yall-run/pull/26).
Use its `feat/each-source-union` branch until merged, then current `main`.
PR #25 provides named lists/tables but does not by itself accept two sources
after `in`. Do not rely on the 0.9.0 version string: update the runner before
validating or creating these workflows. The Condor workflows additionally use
the already-merged payload-wrapper and `%time` features.

```tcsh
cd ~/eic-2026/yall-run
git fetch origin
git switch feat/each-source-union
git pull --ff-only
```

Each of these examples declares its calibration pairs once in `@table pairs`.
A single conversion family visits the ordered union of both columns and
converts each run once. Pedestal fits use unique pedestal values; transfers
wait for their specific pedestal fit and muon conversion. Shared pedestals
are supported without duplicate output owners. Output names remain run-based,
so using multiple pedestal choices for the *same muon run* still requires
separate work areas or explicitly pair-specific output paths.

These refactors rename tasks and remove the introductory `converted` barrier.
Use a **new campaign and fresh work area**, not an amendment to an old campaign.
Existing workers, manifests, products and queued jobs are not modified. No C++
recompilation is required by this Yallfile-only change.''' + s[b:]
s=s.replace('It converts a list of raw runs, creates calibrations from a list of pedestal/MIP pairs, and creates summaries from another list of runs.', 'It converts unique runs from a pedestal/MIP table, fits each pedestal once, and creates calibrations and summaries from the same table.')
s=s.replace('Each production Yallfile contains its own explicit pedestal/MIP pairs.', 'Each production Yallfile contains one top-level table of pedestal/MIP pairs.')
p.write_text(s)
