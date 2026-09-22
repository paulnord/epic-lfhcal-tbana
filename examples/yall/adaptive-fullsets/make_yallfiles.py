#!/usr/bin/env python3
"""Generate calibration-only Yallfiles from the checked-in FullSet recipes."""
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent
CODES = ("b1", "b2", "c1", "c2", "c3", "d1", "d2", "e1", "e2", "e3", "g1", "g2")


def source_config(code):
    text = (EXAMPLES / f"fullset-{code}-repro/Yallfile").read_text()
    get = lambda pattern: re.search(pattern, text, re.MULTILINE).group(1)
    set_name = get(r"^@set SET (\S+)$")
    toa = get(r"^@set TOA (\S+)$")
    bad = get(r"^@set BAD_CHANNELS (\S+)$")
    rundb = get(r"^@set RUNDB (\S+)$")
    pedestal = get(r"^\s+pedestal\s+(\S+)$")
    return set_name, toa, bad, rundb, pedestal


def workflow(code):
    set_name, toa, bad, rundb, pedestal = source_config(code)
    work = f"adaptive-fullset-{code}-repro"
    prefix = f"{set_name.replace('_', '-').lower()}"
    out = f"""campaign lfhcal-tb2026-adaptive-fullset-{code}
backend condor

# Calibration-only replay using persistent converted and merged ROOT files.
# Adaptive fitting is in the DataPrep executable built from this branch.
# No raw conversion or muon merge task is submitted here.
#
# The -M selector is intentional: it is Fredi's intended MIP-only calibration
# path. It is kept separate from the -X whole-event skim experiments.

@env LFHCAL_WORK
@env LFHCAL_CONVERTED
@env LFHCAL_MERGED
@env EIC_SHELL

@set BUILD ../../../NewStructure/build
@set WORK {work}
@set SET {set_name}
@set BAD_CHANNELS {bad}
@set TOA {toa}
@set RUNDB {rundb}
@set PED {pedestal}

%cpus 1
%memory 4GB
%disk 8GB
%time 2h
%getenv true
%wrapper ../../../tools/run-in-eic-shell.sh {{EIC_SHELL}} /usr/bin/env ROOT_MAX_THREADS=1 OMP_NUM_THREADS=1

# Create the output tree on the submit host before DAGMan is launched.
%preflight /bin/mkdir -p {{LFHCAL_WORK}}/{{WORK}}/pedestal {{LFHCAL_WORK}}/{{WORK}}/transfer {{LFHCAL_WORK}}/{{WORK}}/mip {{LFHCAL_WORK}}/{{WORK}}/selected {{LFHCAL_WORK}}/{{WORK}}/refine1 {{LFHCAL_WORK}}/{{WORK}}/refine2 {{LFHCAL_WORK}}/{{WORK}}/refine3 {{LFHCAL_WORK}}/{{WORK}}/refine4 {{LFHCAL_WORK}}/{{WORK}}/refine5 {{LFHCAL_WORK}}/{{WORK}}/final {{LFHCAL_WORK}}/{{WORK}}/plots/pedestal {{LFHCAL_WORK}}/{{WORK}}/plots/transfer {{LFHCAL_WORK}}/{{WORK}}/plots/mip {{LFHCAL_WORK}}/{{WORK}}/plots/refine1 {{LFHCAL_WORK}}/{{WORK}}/plots/refine2 {{LFHCAL_WORK}}/{{WORK}}/plots/refine3 {{LFHCAL_WORK}}/{{WORK}}/plots/refine4 {{LFHCAL_WORK}}/{{WORK}}/plots/refine5

pedestal-{code}:
    @input raw {{LFHCAL_CONVERTED}}/rawHGCROC_{{PED}}.root
    @input rundb {{RUNDB}}
    @output root {{LFHCAL_WORK}}/{{WORK}}/pedestal/rawHGCROC_wPed.root
    @output calib {{LFHCAL_WORK}}/{{WORK}}/pedestal/rawHGCROC_wPed_calib.txt
    @output hists {{LFHCAL_WORK}}/{{WORK}}/pedestal/rawHGCROC_wPed_Hists.root
    @output plots {{LFHCAL_WORK}}/{{WORK}}/plots/pedestal/Run{{PED}}
    {{BUILD}}/DataPrep -a -d 1 -p -i @input.raw -f \\
        -o @output.root -O @output.plots -r @input.rundb -F pdf

transfer-{code}: pedestal-{code}
    @input pedestal {{LFHCAL_WORK}}/{{WORK}}/pedestal/rawHGCROC_wPed.root
    @input raw {{LFHCAL_MERGED}}/rawHGCROC_Muon_{{SET}}.root
    @input bad {{BAD_CHANNELS}}
    @input toa {{TOA}}
    @input rundb {{RUNDB}}
    @output root {{LFHCAL_WORK}}/{{WORK}}/transfer/rawHGCROC_wPed_wBC_Muon_{{SET}}.root
    @output plots {{LFHCAL_WORK}}/{{WORK}}/plots/transfer/Muon_{{SET}}
    {{BUILD}}/DataPrep -d 1 -e -f -P @input.pedestal \\
        -i @input.raw -o @output.root -O @output.plots \\
        -r @input.rundb -B @input.bad -G @input.toa

mip-{code}: transfer-{code}
    @input root {{LFHCAL_WORK}}/{{WORK}}/transfer/rawHGCROC_wPed_wBC_Muon_{{SET}}.root
    @input rundb {{RUNDB}}
    @output root {{LFHCAL_WORK}}/{{WORK}}/mip/rawHGCROC_wPedwMuon_wBC_Muon_{{SET}}.root
    @output calib {{LFHCAL_WORK}}/{{WORK}}/mip/rawHGCROC_wPedwMuon_wBC_Muon_{{SET}}_calib.txt
    @output hists {{LFHCAL_WORK}}/{{WORK}}/mip/rawHGCROC_wPedwMuon_wBC_Muon_{{SET}}_Hists.root
    @output plots {{LFHCAL_WORK}}/{{WORK}}/plots/mip/Muon_{{SET}}
    {{BUILD}}/DataPrep -a -f -d 1 -e -s -i @input.root \\
        -o @output.root -O @output.plots -r @input.rundb

select-{code}: mip-{code}
    @input root {{LFHCAL_WORK}}/{{WORK}}/mip/rawHGCROC_wPedwMuon_wBC_Muon_{{SET}}.root
    @output root {{LFHCAL_WORK}}/{{WORK}}/selected/rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_{{SET}}.root
    {{BUILD}}/DataPrep -f -d 1 -M -i @input.root -o @output.root

refine1-{code}: select-{code}
    @input root {{LFHCAL_WORK}}/{{WORK}}/selected/rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_{{SET}}.root
    @input rundb {{RUNDB}}
    @output root {{LFHCAL_WORK}}/{{WORK}}/refine1/rawHGCROC_wPedwMuon_wBC_ImpR_Muon_{{SET}}.root
    @output calib {{LFHCAL_WORK}}/{{WORK}}/refine1/rawHGCROC_wPedwMuon_wBC_ImpR_Muon_{{SET}}_calib.txt
    @output plots {{LFHCAL_WORK}}/{{WORK}}/plots/refine1/Muon_{{SET}}
    {{BUILD}}/DataPrep -x -a -f -d 1 -S -i @input.root \\
        -o @output.root -O @output.plots -r @input.rundb

refine2-{code}: refine1-{code}
    @input root {{LFHCAL_WORK}}/{{WORK}}/selected/rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_{{SET}}.root
    @input prev {{LFHCAL_WORK}}/{{WORK}}/refine1/rawHGCROC_wPedwMuon_wBC_ImpR_Muon_{{SET}}_calib.txt
    @input rundb {{RUNDB}}
    @output root {{LFHCAL_WORK}}/{{WORK}}/refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_Muon_{{SET}}.root
    @output calib {{LFHCAL_WORK}}/{{WORK}}/refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_Muon_{{SET}}_calib.txt
    @output plots {{LFHCAL_WORK}}/{{WORK}}/plots/refine2/Muon_{{SET}}
    {{BUILD}}/DataPrep -x -a -f -d 1 -S -i @input.root -k @input.prev \\
        -o @output.root -O @output.plots -r @input.rundb

refine3-{code}: refine2-{code}
    @input root {{LFHCAL_WORK}}/{{WORK}}/selected/rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_{{SET}}.root
    @input prev {{LFHCAL_WORK}}/{{WORK}}/refine2/rawHGCROC_wPedwMuon_wBC_Imp2R_Muon_{{SET}}_calib.txt
    @input rundb {{RUNDB}}
    @output root {{LFHCAL_WORK}}/{{WORK}}/refine3/rawHGCROC_wPedwMuon_wBC_Imp3R_Muon_{{SET}}.root
    @output calib {{LFHCAL_WORK}}/{{WORK}}/refine3/rawHGCROC_wPedwMuon_wBC_Imp3R_Muon_{{SET}}_calib.txt
    @output plots {{LFHCAL_WORK}}/{{WORK}}/plots/refine3/Muon_{{SET}}
    {{BUILD}}/DataPrep -x -a -f -d 1 -S -i @input.root -k @input.prev \\
        -o @output.root -O @output.plots -r @input.rundb

refine4-{code}: refine3-{code}
    @input root {{LFHCAL_WORK}}/{{WORK}}/selected/rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_{{SET}}.root
    @input prev {{LFHCAL_WORK}}/{{WORK}}/refine3/rawHGCROC_wPedwMuon_wBC_Imp3R_Muon_{{SET}}_calib.txt
    @input rundb {{RUNDB}}
    @output root {{LFHCAL_WORK}}/{{WORK}}/refine4/rawHGCROC_wPedwMuon_wBC_Imp4R_Muon_{{SET}}.root
    @output calib {{LFHCAL_WORK}}/{{WORK}}/refine4/rawHGCROC_wPedwMuon_wBC_Imp4R_Muon_{{SET}}_calib.txt
    @output plots {{LFHCAL_WORK}}/{{WORK}}/plots/refine4/Muon_{{SET}}
    {{BUILD}}/DataPrep -x -a -f -d 1 -S -i @input.root -k @input.prev \\
        -o @output.root -O @output.plots -r @input.rundb

refine5-{code}: refine4-{code}
    @input root {{LFHCAL_WORK}}/{{WORK}}/selected/rawHGCROC_mipTrigg_wPedwMuon_wBC_Muon_{{SET}}.root
    @input prev {{LFHCAL_WORK}}/{{WORK}}/refine4/rawHGCROC_wPedwMuon_wBC_Imp4R_Muon_{{SET}}_calib.txt
    @input rundb {{RUNDB}}
    @output root {{LFHCAL_WORK}}/{{WORK}}/refine5/rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{{SET}}.root
    @output calib {{LFHCAL_WORK}}/{{WORK}}/refine5/rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{{SET}}_calib.txt
    @output plots {{LFHCAL_WORK}}/{{WORK}}/plots/refine5/Muon_{{SET}}
    {{BUILD}}/DataPrep -x -a -f -d 1 -S -i @input.root -k @input.prev \\
        -o @output.root -O @output.plots -r @input.rundb

final-{code}: refine5-{code}
    @input root {{LFHCAL_WORK}}/{{WORK}}/refine5/rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{{SET}}.root
    @input calib {{LFHCAL_WORK}}/{{WORK}}/refine5/rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{{SET}}_calib.txt
    @output root {{LFHCAL_WORK}}/{{WORK}}/final/calib_Final_Muon_{{SET}}.root
    @output calib {{LFHCAL_WORK}}/{{WORK}}/final/calib_Final_Muon_{{SET}}_calib.txt
    ! /bin/mkdir -p {{LFHCAL_WORK}}/{{WORK}}/final && \\
        /bin/cp @input.root @output.root && /bin/cp @input.calib @output.calib
"""
    (HERE / f"Yallfile.{code}").write_text(out)


if __name__ == "__main__":
    for code in CODES:
        workflow(code)
    print("generated", ", ".join(f"Yallfile.{c}" for c in CODES))
