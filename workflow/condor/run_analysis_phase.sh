#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 4 ]; then
    echo "Usage: $0 PHASE PEDESTAL_RUN MUON_RUN CPUS" >&2
    exit 2
fi

PHASE="$1"
PEDRUN="$2"
RUN="$3"
CPUS="$4"

REPO="/star/u/pnord/eic-2026/epic-lfhcal-tbana"
BUILD="/star/u/pnord/eic-2026/build-epic-lfhcal-tbana-main-20260825-142900"
DATA="/gpfs01/star/pwg/pnord/eic/2026TBdata"
OUT="$DATA/prod_${PEDRUN}_${RUN}"

PROV="$REPO/tools/provenance/lfhcal_provenance.py"
RUNDB="$REPO/configs/TB2026/DataTakingDB_TBSPSH2_202605_HGCROC.csv"
BAD="$REPO/configs/TB2026/badChannel_HGCROC_SPSTB2026_OnlyCenter2x4.txt"
TOA="$REPO/configs/TB2026/ToAOffsets_TBSPS2026_ParamScan_1.csv"
CELLS="$REPO/configs/TB2026/activeCellsHGCROCParameterScan.txt"

DATAPREP="$BUILD/DataPrep"
HGCROCSTUDY="$BUILD/HGCROCStudy"
CONVERT="$BUILD/Convert"

RAW_PED="$DATA/rawHGCROC_${PEDRUN}_offlinefix_batch.root"
RAW_MUON="$DATA/rawHGCROC_${RUN}_offlinefix_batch.root"
PED_FILE="$OUT/rawHGCROC_wPed_${PEDRUN}.root"
CORRECTED="$OUT/rawHGCROC_wPed_wBC_${RUN}.root"
MIP_INITIAL="$OUT/rawHGCROC_wPedwMuon_wBC_${RUN}.root"
SELECTED="$OUT/rawHGCROC_mipTrigg_wPedwMuon_wBC_${RUN}.root"
REFINE1="$OUT/rawHGCROC_wPedwMuon_wBC_ImpR_${RUN}.root"
REFINE2="$OUT/rawHGCROC_wPedwMuon_wBC_Imp2R_${RUN}.root"
REFINE3="$OUT/rawHGCROC_wPedwMuon_wBC_Imp3R_${RUN}.root"
CALIBRATED="$OUT/calibratedHGCROC_Run_${RUN}.root"
WAVE_BASE="$OUT/calibratedHGCROC_wave_Run_${RUN}.root"
WAVE_HISTS="$OUT/calibratedHGCROC_wave_Run_${RUN}_Hists.root"

export LD_LIBRARY_PATH="${BUILD}:${LD_LIBRARY_PATH:-}"
export ROOT_INCLUDE_PATH="${REPO}/NewStructure:${ROOT_INCLUDE_PATH:-}"
export ROOT_MAX_THREADS="$CPUS"
export OMP_NUM_THREADS="$CPUS"

require_file() {
    if [ ! -s "$1" ]; then
        echo "MISSING OR EMPTY: $1" >&2
        exit 2
    fi
}

validate_run_pair() {
    python3 - "$RUNDB" "$PEDRUN" "$RUN" <<'PY'
import csv
import sys

run_db, requested_pedestal, requested_muon = sys.argv[1:]
requested_pedestal = int(requested_pedestal)
requested_muon = int(requested_muon)
pedestal = None

with open(run_db, newline="", encoding="utf-8") as handle:
    for row in csv.reader(handle):
        if not row or not row[0].strip().isdigit() or len(row) < 19:
            continue
        run = int(row[0])
        kind = row[1].strip().lower()
        settings = tuple(field.strip() for field in row[15:19])
        if "pedestal" in kind:
            pedestal = (run, settings)
            continue
        if run != requested_muon:
            continue
        if "muon" not in kind:
            raise SystemExit(f"Run {run} is not a muon run")
        if pedestal is None:
            raise SystemExit(f"No preceding pedestal found for muon run {run}")
        pedestal_run, pedestal_settings = pedestal
        if pedestal_run != requested_pedestal:
            raise SystemExit(
                f"Muon run {run} uses preceding pedestal {pedestal_run}, "
                f"not requested pedestal {requested_pedestal}"
            )
        if settings != pedestal_settings:
            raise SystemExit(
                f"Run {run} settings {settings} do not match pedestal "
                f"{pedestal_run} settings {pedestal_settings}"
            )
        print(
            f"Matched pair: pedestal {pedestal_run} -> muon {run}; "
            f"RF={settings[0]} CF={settings[1]} "
            f"CC={settings[2]} CFComp={settings[3]}"
        )
        break
    else:
        raise SystemExit(f"Muon run {requested_muon} not found in {run_db}")
PY
}

ensure_raw_provenance() {
    local file="$1"
    local run="$2"
    local role="$3"
    local role_args=()
    local show_output=""

    if show_output=$(python3 "$PROV" show "$file" 2>/dev/null) && \
            grep -q 'raw_conversion' <<<"$show_output"; then
        echo "Raw provenance already present: $file"
        python3 "$PROV" verify "$file"
        return
    fi

    if [ "$role" = "pedestal" ]; then
        role_args=(--pedestal-run "$run")
    else
        role_args=(--muon-run "$run")
    fi

    python3 "$PROV" stamp-existing "$file" \
        --stage raw_conversion \
        --run "$run" \
        "${role_args[@]}" \
        --program "$CONVERT" \
        --git-commit 054ab73caf362a5181ca1d0189a276605465da40 \
        --decoder-commit 559036a1553e2e79a4a024b44cc532b82f460021 \
        --container-image /cvmfs/singularity.opensciencegrid.org/eicweb/eic_xl:nightly \
        --attribute campaign="CERN SPS H2 May 2026" \
        --attribute production="matched-pedestal parameter-scan analysis" \
        --note "Retrospective provenance for previously completed raw conversion"
}

COMMON_PROV=(
    --run "$RUN"
    --pedestal-run "$PEDRUN"
    --muon-run "$RUN"
    --config "run_database=$RUNDB"
    --attribute "campaign=CERN SPS H2 May 2026"
    --attribute "scan_set=ParamScan Set1"
    --attribute "pedestal_pairing=matched_register_settings"
)

run_pedestal() {
    require_file "$RAW_PED"
    require_file "$RUNDB"
    require_file "$DATAPREP"
    mkdir -p "$OUT/PlotsPedestal/Run${PEDRUN}"

    ensure_raw_provenance "$RAW_PED" "$PEDRUN" pedestal

    python3 "$PROV" run \
        --stage pedestal \
        --run "$PEDRUN" \
        --pedestal-run "$PEDRUN" \
        --input "raw=$RAW_PED" \
        --output "pedestal=$PED_FILE" \
        --config "run_database=$RUNDB" \
        --attribute "campaign=CERN SPS H2 May 2026" \
        --attribute "scan_set=ParamScan Set1" \
        --attribute "pedestal_pairing=matched_register_settings" \
        -- \
        "$DATAPREP" \
            -a -d 1 -p \
            -i "$RAW_PED" \
            -f \
            -o "$PED_FILE" \
            -O "$OUT/PlotsPedestal/Run${PEDRUN}" \
            -r "$RUNDB" \
            -F pdf

    python3 "$PROV" verify "$PED_FILE"
}

run_calibration() {
    require_file "$RAW_MUON"
    require_file "$PED_FILE"
    require_file "$RUNDB"
    require_file "$BAD"
    require_file "$TOA"
    require_file "$DATAPREP"

    mkdir -p \
        "$OUT/HGCROC_PlotsCalibTransferWToA/Run_${RUN}" \
        "$OUT/HGCROC_PlotsCalibMuon/Run_${RUN}" \
        "$OUT/HGCROC_PlotsSaveNewMuon/Run_${RUN}" \
        "$OUT/HGCROC_PlotsCalibMuonImproved_Red/Run_${RUN}" \
        "$OUT/HGCROC_PlotsCalibMuonImproved2nd_Red/Run_${RUN}" \
        "$OUT/HGCROC_PlotsCalibMuonImproved3rd_Red/Run_${RUN}"

    python3 "$PROV" verify "$PED_FILE"
    ensure_raw_provenance "$RAW_MUON" "$RUN" muon

    python3 "$PROV" run \
        --stage pedestal_bc_toa \
        "${COMMON_PROV[@]}" \
        --input "pedestal=$PED_FILE" \
        --input "raw_muon=$RAW_MUON" \
        --output "corrected=$CORRECTED" \
        --config "bad_channel_map=$BAD" \
        --config "toa_offsets=$TOA" \
        -- \
        "$DATAPREP" \
            -d 2 -e -f \
            -P "$PED_FILE" \
            -i "$RAW_MUON" \
            -o "$CORRECTED" \
            -O "$OUT/HGCROC_PlotsCalibTransferWToA/Run_${RUN}" \
            -r "$RUNDB" \
            -B "$BAD" \
            -G "$TOA"

    python3 "$PROV" run \
        --stage mip_calibration_initial \
        "${COMMON_PROV[@]}" \
        --input "corrected=$CORRECTED" \
        --output "mip_calibrated=$MIP_INITIAL" \
        -- \
        "$DATAPREP" \
            -a -f -d 1 -e -s \
            -i "$CORRECTED" \
            -o "$MIP_INITIAL" \
            -O "$OUT/HGCROC_PlotsCalibMuon/Run_${RUN}" \
            -r "$RUNDB"

    python3 "$PROV" run \
        --stage save_new_muon \
        "${COMMON_PROV[@]}" \
        --input "mip_calibrated=$MIP_INITIAL" \
        --output "selected_muons=$SELECTED" \
        -- \
        "$DATAPREP" \
            -f -d 1 -X \
            -i "$MIP_INITIAL" \
            -o "$SELECTED" \
            -O "$OUT/HGCROC_PlotsSaveNewMuon/Run_${RUN}" \
            -r "$RUNDB"

    python3 "$PROV" run \
        --stage mip_refinement_1 \
        "${COMMON_PROV[@]}" \
        --input "selected_muons=$SELECTED" \
        --output "refined_calibration=$REFINE1" \
        --attribute "historical_workflow_step=imp1st_red" \
        -- \
        "$DATAPREP" \
            -a -f -d 1 -S \
            -i "$SELECTED" \
            -o "$REFINE1" \
            -O "$OUT/HGCROC_PlotsCalibMuonImproved_Red/Run_${RUN}" \
            -r "$RUNDB"

    python3 "$PROV" run \
        --stage mip_refinement_2 \
        "${COMMON_PROV[@]}" \
        --input "previous_calibration=$REFINE1" \
        --output "refined_calibration=$REFINE2" \
        --attribute "historical_workflow_step=imp2nd_red" \
        -- \
        "$DATAPREP" \
            -a -f -d 1 -S \
            -i "$REFINE1" \
            -o "$REFINE2" \
            -O "$OUT/HGCROC_PlotsCalibMuonImproved2nd_Red/Run_${RUN}" \
            -r "$RUNDB"

    python3 "$PROV" run \
        --stage mip_refinement_3 \
        "${COMMON_PROV[@]}" \
        --input "previous_calibration=$REFINE2" \
        --output "refined_calibration=$REFINE3" \
        --attribute "historical_workflow_step=imp3rd_red" \
        -- \
        "$DATAPREP" \
            -a -f -d 1 -S \
            -i "$REFINE2" \
            -o "$REFINE3" \
            -O "$OUT/HGCROC_PlotsCalibMuonImproved3rd_Red/Run_${RUN}" \
            -r "$RUNDB"

    python3 "$PROV" verify "$REFINE3"
}

run_apply() {
    require_file "$SELECTED"
    require_file "$REFINE3"
    require_file "$BAD"
    require_file "$TOA"
    require_file "$DATAPREP"
    mkdir -p "$OUT/HGCROC_PlotsFullCalib/Run_${RUN}"

    python3 "$PROV" verify "$SELECTED"
    python3 "$PROV" verify "$REFINE3"

    python3 "$PROV" run \
        --stage apply_final_calibration \
        "${COMMON_PROV[@]}" \
        --input "selected_muons=$SELECTED" \
        --input "final_calibration=$REFINE3" \
        --output "calibrated_events=$CALIBRATED" \
        --config "bad_channel_map=$BAD" \
        --config "toa_offsets=$TOA" \
        --attribute "historical_workflow_step=fullMuon" \
        -- \
        "$DATAPREP" \
            -e -f -d 1 -a \
            -C "$REFINE3" \
            -i "$SELECTED" \
            -o "$CALIBRATED" \
            -O "$OUT/HGCROC_PlotsFullCalib/Run_${RUN}" \
            -r "$RUNDB" \
            -B "$BAD" \
            -G "$TOA"

    python3 "$PROV" verify "$CALIBRATED"
}

run_waveform() {
    require_file "$CALIBRATED"
    require_file "$CELLS"
    require_file "$HGCROCSTUDY"
    mkdir -p "$OUT/HGCROC_PlotsWave/Run_${RUN}"

    python3 "$PROV" verify "$CALIBRATED"

    python3 "$PROV" run \
        --stage waveform_analysis \
        "${COMMON_PROV[@]}" \
        --input "calibrated_events=$CALIBRATED" \
        --output "waveform_histograms=$WAVE_HISTS" \
        --config "active_cells=$CELLS" \
        --attribute "historical_workflow_step=HGCInv wave" \
        -- \
        "$HGCROCSTUDY" \
            -d 1 -E 1 -f -w \
            -i "$CALIBRATED" \
            -o "$WAVE_BASE" \
            -O "$OUT/HGCROC_PlotsWave/Run_${RUN}" \
            -r "$RUNDB" \
            -l "$CELLS"

    python3 "$PROV" verify "$WAVE_HISTS"
    python3 "$PROV" show "$WAVE_HISTS"

    local profile_count
    profile_count=$(
        rootls -1 "$WAVE_HISTS":IndividualCells \
            | grep -c '^waveform1DfullCellID' || true
    )
    echo "waveform1DfullCellID profiles: $profile_count"
    if [ "$profile_count" -ne 64 ]; then
        echo "ERROR: expected 64 waveform profiles" >&2
        exit 1
    fi
}

echo "Phase: $PHASE"
echo "Pedestal run: $PEDRUN"
echo "Muon run: $RUN"
echo "Host: $(hostname)"
echo "Output: $OUT"
echo "ROOT_MAX_THREADS: $ROOT_MAX_THREADS"

validate_run_pair

case "$PHASE" in
    pedestal)    run_pedestal ;;
    calibration) run_calibration ;;
    apply)       run_apply ;;
    waveform)    run_waveform ;;
    *)
        echo "Unknown phase: $PHASE" >&2
        exit 2
        ;;
esac

echo "Completed phase $PHASE for pedestal $PEDRUN and muon $RUN"
