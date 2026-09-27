#!/usr/bin/env python3
"""Export one Weka-friendly row per (FullSet, cell) for TB2026 calibration studies.

The composite observation key is (dataset, cell_id).  Cell ID alone is not a
unique observation because the same physical channel was calibrated repeatedly
under different run settings.

Published calibration values come from calibrations/TB2026.  Run settings come
from the SPS-H2 data-taking database.  Optional replay sources add saved TF1 fit
parameters and replay calibration outputs.  Missing values are written as "?"
by default, which Weka's CSV loader treats as missing.
"""

import argparse
import csv
import math
from pathlib import Path
import re
from statistics import mean, median


CALIB_RE = re.compile(r"calib_SPS-H2_(FullSet([A-G])_([0-9]+))\.txt$")
CALIB_INFO_RE = re.compile(
    r"RunNr:\s*(\d+).*?"
    r"RunNrPed:\s*(\d+).*?"
    r"RunNrMip:\s*(\d+).*?"
    r"Vop:\s*([-+0-9.eE]+).*?"
    r"Vov:\s*([-+0-9.eE]+).*?"
    r"BC calib set:\s*(\d+)"
)
FIT_NAME_RE = re.compile(r"fmipmipTriggHGCellID(\d+)$")

DB_NUMERIC_FIELDS = {
    "Run Number": "run_number",
    "pdg": "pdg",
    "beam energy (GeV)": "beam_energy_gev",
    "bias Voltage": "bias_voltage",
    "V_br": "breakdown_voltage",
    "trigger delay": "trigger_delay",
    "machine gun number": "machine_gun_number",
    "Table Position x": "table_x",
    "Table Position (y)": "table_y",
    "dead time": "dead_time",
    "phase": "phase",
    "nrKCU": "nr_kcu",
    "nrAsic": "nr_asic",
    "Temp": "temperature_c",
    "RF": "rf",
    "CF": "cf",
    "CC": "cc",
    "CFComp": "cf_comp",
}


def number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return int(value) if value.is_integer() else value

    text = str(value).strip()
    if text in ("", "-"):
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def missing_sentinel(value, sentinel):
    if value is None:
        return None
    return None if value == sentinel else value


def read_run_db(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("Run Number,"):
            start = i
            break
    if start is None:
        raise ValueError(f"Run Number header not found in {path}")

    rows = {}
    reader = csv.DictReader(lines[start:])
    for raw in reader:
        clean = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
        run = number(clean.get("Run Number"))
        if run is None:
            continue
        clean["Run Number"] = int(run)
        rows[int(run)] = clean
    return rows


def db_features(row, prefix):
    out = {}
    if row is None:
        out[f"{prefix}_db_present"] = 0
        out[f"{prefix}_beam_species"] = None
        for dst in DB_NUMERIC_FIELDS.values():
            out[f"{prefix}_{dst}"] = None
        out[f"{prefix}_overvoltage"] = None
        return out

    out[f"{prefix}_db_present"] = 1
    out[f"{prefix}_beam_species"] = row.get("beam species") or None
    for src, dst in DB_NUMERIC_FIELDS.items():
        out[f"{prefix}_{dst}"] = number(row.get(src))

    bias = out[f"{prefix}_bias_voltage"]
    vbr = out[f"{prefix}_breakdown_voltage"]
    out[f"{prefix}_overvoltage"] = (
        float(bias) - float(vbr)
        if bias is not None and vbr is not None else None
    )
    return out


def read_calibration(path):
    meta = None
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "RunNr:" in line:
            match = CALIB_INFO_RE.search(line)
            if match:
                meta = {
                    "run_number": int(match.group(1)),
                    "pedestal_run_number": int(match.group(2)),
                    "mip_run_number": int(match.group(3)),
                    "header_vop": float(match.group(4)),
                    "header_vov": float(match.group(5)),
                    "bc_calib_set": int(match.group(6)),
                }
        f = line.split()
        if len(f) != 18 or not f[0].isdigit():
            continue
        cell = int(f[0])
        rows[cell] = {
            "cell_id": cell,
            "layer": int(f[1]),
            "row": int(f[2]),
            "column": int(f[3]),
            "module": int(f[4]),
            "pedestal_mean_h": missing_sentinel(float(f[5]), -1000.0),
            "pedestal_sigma_h": missing_sentinel(float(f[6]), -1000.0),
            "pedestal_mean_l": missing_sentinel(float(f[7]), -1000.0),
            "pedestal_sigma_l": missing_sentinel(float(f[8]), -1000.0),
            "mip_scale_h": missing_sentinel(float(f[9]), -1000.0),
            "mip_fwhm_h": missing_sentinel(float(f[10]), -1000.0),
            "mip_scale_l": missing_sentinel(float(f[11]), -1000.0),
            "mip_fwhm_l": missing_sentinel(float(f[12]), -1000.0),
            "lg_hg_slope": missing_sentinel(float(f[13]), -64.0),
            "lg_hg_intercept": missing_sentinel(float(f[14]), -1000.0),
            "hg_lg_slope": missing_sentinel(float(f[15]), -64.0),
            "hg_lg_intercept": missing_sentinel(float(f[16]), -1000.0),
            "bad_channel": None if int(f[17]) == -64 else int(f[17]),
        }
    if meta is None:
        raise ValueError(f"Calibration metadata header not found in {path}")
    if not rows:
        raise ValueError(f"No calibration rows found in {path}")
    return meta, rows


def load_histogram_stats(path, pedestal_sigmas):
    """Extract per-cell statistics from the triggered MIP spectra.

    GetEntries() is the same quantity called numMipTrig in Analyses.cc.
    The signal/noise regions mirror the monitoring calculation there:
    noise-like region [-1 sigma_ped, 3 sigma_ped], signal region above
    3 sigma_ped.
    """
    import ROOT

    ROOT.gROOT.SetBatch(True)
    root_file = ROOT.TFile.Open(str(path))
    if not root_file or root_file.IsZombie():
        raise ValueError(f"cannot open ROOT histogram file: {path}")
    directory = root_file.Get("IndividualCellsTrigg")
    if not directory:
        root_file.Close()
        raise ValueError(f"IndividualCellsTrigg directory is absent: {path}")

    result = {}
    for cell, ped_sigma in pedestal_sigmas.items():
        hist = directory.Get(f"hspectramipTriggADCCellID{cell}")
        if not hist:
            continue

        nbins = hist.GetNbinsX()
        integral = float(hist.Integral(1, nbins))
        entries = float(hist.GetEntries())
        effective = float(hist.GetEffectiveEntries())
        nonzero = 0
        max_bin_count = 0.0
        bins_ge_5 = 0
        bins_ge_10 = 0
        for b in range(1, nbins + 1):
            value = float(hist.GetBinContent(b))
            if value > 0:
                nonzero += 1
            if value >= 5:
                bins_ge_5 += 1
            if value >= 10:
                bins_ge_10 += 1
            if value > max_bin_count:
                max_bin_count = value

        noise_count = None
        signal_count = None
        snr = None
        signal_fraction = None
        if ped_sigma is not None and ped_sigma > 0:
            b_noise_lo = hist.FindBin(-1.0 * ped_sigma)
            b_noise_hi = hist.FindBin(3.0 * ped_sigma)
            b_signal_hi = hist.FindBin(1024.0)
            noise_count = float(hist.Integral(b_noise_lo, b_noise_hi))
            signal_count = float(hist.Integral(b_noise_hi, b_signal_hi))
            snr = signal_count / noise_count if noise_count > 0 else None
            denom = signal_count + noise_count
            signal_fraction = signal_count / denom if denom > 0 else None

        result[cell] = {
            "mip_trigger_entries": entries,
            "mip_trigger_integral": integral,
            "mip_trigger_effective_entries": effective,
            "mip_trigger_nonzero_bins": nonzero,
            "mip_trigger_bins_ge_5": bins_ge_5,
            "mip_trigger_bins_ge_10": bins_ge_10,
            "mip_trigger_peak_bin_count": max_bin_count,
            "mip_trigger_mean_adc": float(hist.GetMean()),
            "mip_trigger_rms_adc": float(hist.GetRMS()),
            "mip_trigger_noise_region_count": noise_count,
            "mip_trigger_signal_region_count": signal_count,
            "mip_trigger_snr": snr,
            "mip_trigger_signal_fraction": signal_fraction,
        }

    root_file.Close()
    return result


def load_fits(path):
    import ROOT

    ROOT.gROOT.SetBatch(True)
    root_file = ROOT.TFile.Open(str(path))
    if not root_file or root_file.IsZombie():
        raise ValueError(f"cannot open ROOT histogram file: {path}")
    directory = root_file.Get("IndividualCellsTrigg")
    if not directory:
        root_file.Close()
        raise ValueError(f"IndividualCellsTrigg directory is absent: {path}")

    result = {}
    for key in directory.GetListOfKeys():
        match = FIT_NAME_RE.fullmatch(key.GetName())
        if not match or key.GetClassName() != "TF1":
            continue
        cell = int(match.group(1))
        if cell in result:
            continue
        fit = directory.Get(key.GetName())
        if not fit or fit.GetNpar() < 4:
            continue
        ndf = int(fit.GetNDF())
        chi2 = float(fit.GetChisquare())
        vals = {
            "landau_width": float(fit.GetParameter(0)),
            "mpv": float(fit.GetParameter(1)),
            "area": float(fit.GetParameter(2)),
            "gaussian_sigma": float(fit.GetParameter(3)),
            "landau_width_err": float(fit.GetParError(0)),
            "mpv_err": float(fit.GetParError(1)),
            "area_err": float(fit.GetParError(2)),
            "gaussian_sigma_err": float(fit.GetParError(3)),
            "chi2": chi2,
            "ndf": ndf,
            "chi2_ndf": chi2 / ndf if ndf > 0 else None,
            "fit_xmin": float(fit.GetXmin()),
            "fit_xmax": float(fit.GetXmax()),
        }
        width = vals["landau_width"]
        sigma = vals["gaussian_sigma"]
        mpv = vals["mpv"]
        vals["sigma_over_landau"] = sigma / width if width != 0 else None
        vals["landau_over_mpv"] = width / mpv if mpv != 0 else None
        result[cell] = vals

    root_file.Close()
    return result


def replay_paths(root, code, set_name, adaptive=False):
    if adaptive:
        directory = root / f"adaptive-fullset-{code}-repro" / "refine5"
    else:
        directory = root / code / "refine5"
    stem = f"rawHGCROC_wPedwMuon_wBC_Imp5R_Muon_{set_name}"
    return (
        directory / f"{stem}_calib.txt",
        directory / f"{stem}_Hists.root",
    )


def parse_replay_root(spec):
    if "=" not in spec:
        raise argparse.ArgumentTypeError("replay root must be NAME=/path")
    name, path = spec.split("=", 1)
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name.strip())
    if not name:
        raise argparse.ArgumentTypeError("replay source NAME is empty")
    return name, Path(path).expanduser()


def fit_source_features(label, calib_rows, fits, source_available, cell, published_ped_sigma):
    out = {
        f"{label}_source_available": 1 if source_available else 0,
        f"{label}_fit_saved": None if not source_available else (1 if cell in fits else 0),
    }

    replay = calib_rows.get(cell) if calib_rows else None
    out[f"{label}_calib_mip_scale_h"] = replay.get("mip_scale_h") if replay else None
    out[f"{label}_calib_mip_fwhm_h"] = replay.get("mip_fwhm_h") if replay else None

    fit = fits.get(cell) if fits else None
    fit_fields = (
        "landau_width", "mpv", "area", "gaussian_sigma",
        "landau_width_err", "mpv_err", "area_err", "gaussian_sigma_err",
        "chi2", "ndf", "chi2_ndf", "fit_xmin", "fit_xmax",
        "sigma_over_landau", "landau_over_mpv",
    )
    for field in fit_fields:
        out[f"{label}_{field}"] = fit.get(field) if fit else None

    sigma = fit.get("gaussian_sigma") if fit else None
    out[f"{label}_sigma_over_pedestal"] = (
        sigma / published_ped_sigma
        if sigma is not None and published_ped_sigma is not None and published_ped_sigma > 0
        else None
    )
    return out


def finite_values(values):
    return [
        float(v) for v in values
        if v is not None and isinstance(v, (int, float)) and math.isfinite(float(v))
    ]


def write_csv(path, rows, fieldnames, missing_token):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: (missing_token if row.get(key) is None else row.get(key))
                for key in fieldnames
            })


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--adaptive-root", type=Path,
        help="Root containing adaptive-fullset-<code>-repro/refine5 directories.",
    )
    ap.add_argument(
        "--replay-root", action="append", default=[], type=parse_replay_root,
        metavar="NAME=PATH",
        help="Add a replay source laid out as PATH/<code>/refine5. Repeat as needed.",
    )
    ap.add_argument(
        "--missing-token", default="?",
        help='CSV token for missing values (default: "?", Weka-friendly).',
    )
    args = ap.parse_args()

    repo = args.repo.resolve()
    calib_dir = repo / "calibrations" / "TB2026"
    run_db_path = repo / "configs" / "TB2026" / "DataTakingDB_TBSPSH2_202605_HGCROC.csv"
    run_db = read_run_db(run_db_path)

    datasets = []
    for path in sorted(calib_dir.glob("calib_SPS-H2_FullSet*.txt")):
        match = CALIB_RE.fullmatch(path.name)
        if not match:
            continue
        set_name = match.group(1)
        family = match.group(2)
        set_index = int(match.group(3))
        code = f"{family.lower()}{set_index}"
        meta, cells = read_calibration(path)
        datasets.append({
            "path": path,
            "set_name": set_name,
            "family": family,
            "set_index": set_index,
            "code": code,
            "meta": meta,
            "cells": cells,
        })

    if not datasets:
        raise SystemExit(f"No FullSet calibration files found under {calib_dir}")

    fit_sources = []
    if args.adaptive_root:
        fit_sources.append(("adaptive", args.adaptive_root.resolve(), True))
    for label, root in args.replay_root:
        fit_sources.append((label, root.resolve(), False))

    rows = []
    replay_cache = {}

    for dataset in datasets:
        set_name = dataset["set_name"]
        code = dataset["code"]
        family = dataset["family"]
        meta = dataset["meta"]

        mip_db = run_db.get(meta["mip_run_number"])
        ped_db = run_db.get(meta["pedestal_run_number"])

        source_data = {}
        canonical_hist_path = None
        for label, root, adaptive in fit_sources:
            calib_path, hist_path = replay_paths(root, code, set_name, adaptive=adaptive)
            source_available = hist_path.is_file()
            replay_calib = {}
            fits = {}
            if calib_path.is_file():
                _, replay_calib = read_calibration(calib_path)
            if source_available:
                fits = load_fits(hist_path)
                if canonical_hist_path is None or label == "adaptive":
                    canonical_hist_path = hist_path
            source_data[label] = (replay_calib, fits, source_available)
            replay_cache[(set_name, label)] = {
                "calib_path": str(calib_path),
                "hist_path": str(hist_path),
                "available": source_available,
                "fit_count": len(fits),
            }

        pedestal_sigmas = {
            cell: calib["pedestal_sigma_h"]
            for cell, calib in dataset["cells"].items()
        }
        histogram_stats = (
            load_histogram_stats(canonical_hist_path, pedestal_sigmas)
            if canonical_hist_path is not None else {}
        )

        for cell, calib in sorted(dataset["cells"].items()):
            row = {
                "observation_id": f"{set_name}:cell{cell:04d}",
                "cell_key": f"cell{cell:04d}",
                "dataset": set_name,
                "family": family,
                "set_index": dataset["set_index"],
                "cell_id": cell,
                "layer": calib["layer"],
                "row": calib["row"],
                "column": calib["column"],
                "module": calib["module"],
                "calib_run_number": meta["run_number"],
                "pedestal_run_number": meta["pedestal_run_number"],
                "mip_run_number": meta["mip_run_number"],
                "calib_header_vop": meta["header_vop"],
                "calib_header_vov": meta["header_vov"],
                "bc_calib_set": meta["bc_calib_set"],
                "published_pedestal_mean_h": calib["pedestal_mean_h"],
                "published_pedestal_sigma_h": calib["pedestal_sigma_h"],
                "published_pedestal_mean_l": calib["pedestal_mean_l"],
                "published_pedestal_sigma_l": calib["pedestal_sigma_l"],
                "published_mip_scale_h": calib["mip_scale_h"],
                "published_mip_fwhm_h": calib["mip_fwhm_h"],
                "published_mip_scale_l": calib["mip_scale_l"],
                "published_mip_fwhm_l": calib["mip_fwhm_l"],
                "published_lg_hg_slope": calib["lg_hg_slope"],
                "published_lg_hg_intercept": calib["lg_hg_intercept"],
                "published_hg_lg_slope": calib["hg_lg_slope"],
                "published_hg_lg_intercept": calib["hg_lg_intercept"],
                "published_bad_channel": calib["bad_channel"],
                "published_mip_valid": 1 if calib["mip_scale_h"] is not None else 0,
            }
            row.update(db_features(mip_db, "mip"))
            row.update(db_features(ped_db, "ped"))

            db_vov = row.get("mip_overvoltage")
            row["calib_vov_minus_db_overvoltage"] = (
                meta["header_vov"] - db_vov if db_vov is not None else None
            )

            available_saved = []
            for label, _, _ in fit_sources:
                replay_calib, fits, available = source_data[label]
                row.update(fit_source_features(
                    label, replay_calib, fits, available, cell,
                    calib["pedestal_sigma_h"],
                ))
                if available:
                    available_saved.append(1 if cell in fits else 0)

            row["fit_sources_available"] = len(available_saved)
            row["fit_sources_saved"] = sum(available_saved)
            row["fit_failed_any_source"] = (
                None if not available_saved else (1 if any(v == 0 for v in available_saved) else 0)
            )
            rows.append(row)

    # Same-family peer comparisons for the published calibration.  These are
    # deliberately within-family, because B/C/D/E/F/G used different settings.
    by_family_cell = {}
    for row in rows:
        by_family_cell.setdefault((row["family"], row["cell_id"]), []).append(row)

    for row in rows:
        peers = [
            peer for peer in by_family_cell[(row["family"], row["cell_id"])]
            if peer["dataset"] != row["dataset"]
        ]
        row["family_peer_count"] = len(peers)
        for value_name, stem in (
            ("published_mip_scale_h", "published_scale"),
            ("published_mip_fwhm_h", "published_fwhm"),
        ):
            values = finite_values(peer.get(value_name) for peer in peers)
            peer_mean = mean(values) if values else None
            row[f"{stem}_family_peer_mean"] = peer_mean
            row[f"{stem}_family_peer_delta"] = (
                row[value_name] - peer_mean
                if row[value_name] is not None and peer_mean is not None else None
            )
            row[f"{stem}_family_peer_frac_delta"] = (
                (row[value_name] - peer_mean) / peer_mean
                if row[value_name] is not None and peer_mean not in (None, 0) else None
            )

    # Per-cell failure history, repeated onto each observation so Weka can use
    # it as a color/class attribute without a join.  It should normally be
    # excluded from an unsupervised PCA if it is being used as an outcome label.
    by_cell = {}
    for row in rows:
        by_cell.setdefault(row["cell_id"], []).append(row)

    source_labels = [label for label, _, _ in fit_sources]
    summary_rows = []
    for cell, cell_rows in sorted(by_cell.items()):
        first = cell_rows[0]
        summary = {
            "cell_key": first["cell_key"],
            "cell_id": cell,
            "layer": first["layer"],
            "row": first["row"],
            "column": first["column"],
            "module": first["module"],
            "n_datasets": len(cell_rows),
            "published_mip_missing_count": sum(
                1 for r in cell_rows if not r["published_mip_valid"]
            ),
        }
        total_failures = 0
        for label in source_labels:
            available = [r for r in cell_rows if r[f"{label}_source_available"] == 1]
            failures = [r for r in available if r[f"{label}_fit_saved"] == 0]
            saved = [r for r in available if r[f"{label}_fit_saved"] == 1]
            summary[f"{label}_datasets_available"] = len(available)
            summary[f"{label}_fit_saved_count"] = len(saved)
            summary[f"{label}_fit_failure_count"] = len(failures)
            chi = finite_values(r.get(f"{label}_chi2_ndf") for r in saved)
            summary[f"{label}_chi2_ndf_median"] = median(chi) if chi else None
            summary[f"{label}_chi2_ndf_max"] = max(chi) if chi else None
            total_failures += len(failures)
        summary["fit_failure_count_all_sources"] = total_failures
        summary["cell_ever_fit_failed"] = 1 if total_failures else 0
        summary_rows.append(summary)

        for row in cell_rows:
            row["cell_ever_fit_failed"] = summary["cell_ever_fit_failed"]
            row["cell_fit_failure_count_all_sources"] = total_failures
            row["cell_published_mip_missing_count"] = summary["published_mip_missing_count"]

    fieldnames = list(rows[0].keys())
    write_csv(args.out, rows, fieldnames, args.missing_token)

    summary_path = args.out.with_name(args.out.stem + "-cell-summary.csv")
    summary_fields = list(summary_rows[0].keys())
    write_csv(summary_path, summary_rows, summary_fields, args.missing_token)

    print(f"Published FullSets: {len(datasets)}")
    print(f"Cells per FullSet: {len(datasets[0]['cells'])}")
    print(f"Observation rows: {len(rows)}")
    print(f"Fit sources: {', '.join(source_labels) if source_labels else '(none)'}")
    print(f"Weka table: {args.out}")
    print(f"Cell summary: {summary_path}")
    print()
    print("Primary key: observation_id = dataset + cell_id")
    print("For PCA, normally exclude observation_id, cell_key, dataset, family,")
    print("cell_id, and outcome/flag columns; retain the numerical detector settings")
    print("and calibration/fit features you want to study.")

    for dataset in datasets:
        valid = sum(
            1 for c in dataset["cells"].values()
            if c["mip_scale_h"] is not None
        )
        print(f"{dataset['set_name']:12s}: {valid:3d}/{len(dataset['cells'])} published MIP calibrations")

    if fit_sources:
        print()
        print("Replay availability:")
        for dataset in datasets:
            bits = []
            for label in source_labels:
                info = replay_cache[(dataset["set_name"], label)]
                if info["available"]:
                    bits.append(f"{label}={info['fit_count']}")
                else:
                    bits.append(f"{label}=NA")
            print(f"{dataset['set_name']:12s}: " + "  ".join(bits))


if __name__ == "__main__":
    main()
