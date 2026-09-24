#!/usr/bin/env python3
"""Read-only inventory of existing HV-scan histograms; no refits or new cuts."""
from __future__ import annotations

import argparse
from array import array
import csv
import ctypes
import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys


THRESHOLDS = (200, 500, 1000, 2000, 5000)
NOTE = ("Counts are selected per-cell TH1 entries, including underflow/overflow, "
        "not distinct run events. Distribution population: present BC>=2 cells, "
        "including zeros. Missing histograms are not zeros. Thresholds are "
        "descriptive only; no cuts, refills, rebinning, error replacement, "
        "fit-range derivation, TF1 evaluation or refits are performed.")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(json_safe(value), stream, indent=2, allow_nan=False)
        stream.write("\n")


def read_calibration(path):
    text = Path(path).read_text(encoding="utf-8")
    metadata = {}
    for label in ("RunNr", "RunNrPed", "RunNrMip", "Vop", "Vov", "BC calib set"):
        match = re.search(r"(?<!\w)" + re.escape(label) + r":\s*([^\s]+)", text)
        if match:
            metadata[label] = match.group(1)
    cells = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        fields = line.split()
        if not fields or not re.fullmatch(r"[+-]?\d+", fields[0]):
            continue
        if len(fields) != 18:
            raise ValueError(f"{path}:{lineno}: expected 18 calibration fields")
        try:
            values = [float(field) for field in fields]
        except ValueError as error:
            raise ValueError(f"{path}:{lineno}: nonnumeric calibration field") from error
        for index in (0, 1, 2, 3, 4, 17):
            if not math.isfinite(values[index]) or values[index] != int(values[index]):
                raise ValueError(f"{path}:{lineno}: invalid integer field {index}")
        cid, layer, row, column, module = map(int, values[:5])
        if cid in cells:
            raise ValueError(f"{path}:{lineno}: duplicate cell {cid}")
        cells[cid] = dict(cell_id=cid, module=module, layer=layer, row=row,
                          column=column, bc=int(values[17]), ped_sigma=values[6],
                          calib_scale_h=values[9], calib_width_h=values[10])
    if not cells:
        raise ValueError(f"{path}: no calibration cells")
    return cells, metadata


def source_paths(work, run):
    prefix = f"rawHGCROC_wPedwMuon_wBC_Imp2R_{run}"
    return (work / "refine2" / (prefix + "_Hists.root"),
            work / "refine2" / (prefix + "_calib.txt"),
            work / "refine1" / f"rawHGCROC_wPedwMuon_wBC_ImpR_{run}_calib.txt")


def key_inventory(directory, prefix=""):
    records = []
    for key in directory.GetListOfKeys():
        name = prefix + key.GetName()
        record = dict(path=name, cycle=key.GetCycle(), class_name=key.GetClassName())
        records.append(record)
        if key.GetClassName().startswith("TDirectory"):
            child = directory.GetDirectory(key.GetName())
            if child:
                records.extend(key_inventory(child, name + "/"))
    return records


def stored_function(obj):
    if not obj:
        return None
    if not obj.InheritsFrom("TF1"):
        raise ValueError("stored MIP function key is not a TF1")
    parameters = []
    for index in range(obj.GetNpar()):
        low, high = ctypes.c_double(), ctypes.c_double()
        obj.GetParLimits(index, low, high)
        parameters.append(dict(name=obj.GetParName(index), value=obj.GetParameter(index),
                               error=obj.GetParError(index), low=low.value, high=high.value))
    return dict(class_name=obj.ClassName(), name=obj.GetName(), xmin=obj.GetXmin(),
                xmax=obj.GetXmax(), parameters=parameters,
                note="Stored metadata only; TF1 not evaluated. No minimizer status inferred.")


def summarize(rows):
    eligible = [r for r in rows if r["bc"] >= 2]
    present = [r for r in eligible if r["has_histogram"]]
    counts = sorted(r["entries"] for r in present)
    return dict(calibration_cells=len(rows), present_histograms=sum(r["has_histogram"] for r in rows),
                missing_histograms=sum(not r["has_histogram"] for r in rows),
                unmasked_calibration_cells=len(eligible),
                missing_unmasked_histograms=sum(not r["has_histogram"] for r in eligible),
                comparison_population=len(counts), zero_entry_unmasked=sum(x == 0 for x in counts),
                minimum=min(counts) if counts else None,
                median=statistics.median(counts) if counts else None,
                maximum=max(counts) if counts else None,
                mean=statistics.mean(counts) if counts else None,
                selected_cell_entries_sum=sum(counts),
                counts_at_least={str(cut): sum(x >= cut for x in counts) for cut in THRESHOLDS},
                stored_function_count=sum(r["has_stored_function"] for r in rows),
                stored_function_unmasked_count=sum(r["has_stored_function"] for r in eligible),
                nonfinite_content_cells=sum(r["nonfinite_contents"] > 0 for r in rows if r["has_histogram"]),
                nonfinite_error_cells=sum(r["nonfinite_errors"] > 0 for r in rows if r["has_histogram"]))


def inspect_run(ROOT, run, hist_path, calib_path, preceding_path):
    cells, metadata = read_calibration(calib_path)
    preceding = None
    if preceding_path.is_file():
        previous_cells, previous_metadata = read_calibration(preceding_path)
        preceding = dict(path=str(preceding_path), metadata=previous_metadata,
                         calibration_cells=len(previous_cells))
    root_file = ROOT.TFile.Open(str(hist_path), "READ")
    if not root_file or root_file.IsZombie():
        raise ValueError(f"cannot read ROOT file {hist_path}")
    rows, functions = [], {}
    try:
        if not root_file.GetDirectory("IndividualCellsTrigg"):
            raise ValueError(f"{hist_path}: missing IndividualCellsTrigg directory")
        keys = key_inventory(root_file)
        for cid, cell in sorted(cells.items()):
            hist_key = f"IndividualCellsTrigg/hspectramipTriggADCCellID{cid}"
            function_key = f"IndividualCellsTrigg/fmipmipTriggHGCellID{cid}"
            hist = root_file.Get(hist_key)
            row = dict(run=run, **cell, histogram_key=hist_key, has_histogram=bool(hist),
                       histogram_class="", nbins=math.nan, entries=math.nan, integral=math.nan,
                       underflow=math.nan, overflow=math.nan, nonfinite_contents=math.nan,
                       nonfinite_errors=math.nan, stored_function_key=function_key,
                       has_stored_function=False)
            if hist:
                if not hist.InheritsFrom("TH1") or hist.GetDimension() != 1:
                    raise ValueError(f"{hist_path}:{hist_key}: expected 1D histogram")
                entries = hist.GetEntries()
                if not math.isfinite(entries) or entries < 0:
                    raise ValueError(f"{hist_path}:{hist_key}: invalid entry count")
                row.update(histogram_class=hist.ClassName(), nbins=hist.GetNbinsX(), entries=entries,
                           integral=hist.Integral(1, hist.GetNbinsX()),
                           underflow=hist.GetBinContent(0), overflow=hist.GetBinContent(hist.GetNbinsX()+1),
                           nonfinite_contents=sum(not math.isfinite(hist.GetBinContent(i)) for i in range(hist.GetNcells())),
                           nonfinite_errors=sum(not math.isfinite(hist.GetBinError(i)) for i in range(hist.GetNcells())))
            function = stored_function(root_file.Get(function_key))
            if function is not None:
                row["has_stored_function"] = True
                functions[str(cid)] = function
            rows.append(row)
    finally:
        root_file.Close()
    return rows, dict(run=run, histogram_path=str(hist_path), calibration_path=str(calib_path),
                      calibration_metadata=metadata, preceding_calibration=preceding,
                      summary=summarize(rows), root_keys=keys, stored_functions=functions)


def write_csv(path, records, fields=None):
    with Path(path).open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def compare_runs(rows, runs):
    by_run = {run: {r["cell_id"]: r for r in rows if r["run"] == run} for run in runs}
    result = []
    for cid in sorted({r["cell_id"] for r in rows}):
        record = {"cell_id": cid}
        locations = set()
        for run in runs:
            cell = by_run[run].get(cid)
            record.update({f"run{run}_has_calibration": bool(cell),
                           f"run{run}_has_histogram": cell["has_histogram"] if cell else False,
                           f"run{run}_bc": cell["bc"] if cell else math.nan,
                           f"run{run}_entries": cell["entries"] if cell else math.nan})
            if cell:
                locations.add(tuple(cell[k] for k in ("module", "layer", "row", "column")))
        record["geometry_consistent"] = len(locations) <= 1
        result.append(record)
    return result


def plots(ROOT, out, rows, records):
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)
    ROOT.gStyle.SetPaintTextFormat(".0f")
    artifacts = []
    # Keep Python proxies alive until each canvas has been saved.
    for record in records:
        run = record["run"]
        cells = [r for r in rows if r["run"] == run]
        unmasked = [r for r in cells if r["bc"] >= 2 and r["has_histogram"]]
        counts = sorted(r["entries"] for r in unmasked)
        positive = [x for x in counts if x > 0]
        max_count = max(counts, default=0)
        canvas = ROOT.TCanvas(f"counts_{run}", "", 1200, 700)
        canvas.SetLeftMargin(.11)
        canvas.SetBottomMargin(.13)
        upper = max(10., max_count * 1.15)
        edges = array("d", [10 ** (i * math.log10(upper) / 35) for i in range(36)])
        hist = ROOT.TH1D(f"distribution_{run}",
                         f"Run {run}: selected entries per cell (not run events);Selected per-cell entries;Cells per logarithmic interval",
                         35, edges)
        hist.SetDirectory(0)
        for count in positive:
            hist.Fill(count)
        canvas.SetLogx()
        hist.SetMinimum(0)
        hist.SetMaximum(max(1., hist.GetMaximum()) * 1.25)
        hist.SetLineColor(ROOT.kBlue + 1)
        hist.SetLineWidth(2)
        hist.Draw("HIST")
        label = ROOT.TLatex()
        label.SetNDC(True)
        label.SetTextSize(.029)
        label.DrawLatex(.14, .84, f"Present BC#geq2: {len(counts)} cells; zero entries: {len(counts)-len(positive)} (listed separately)")
        label.DrawLatex(.14, .79, f"Missing BC#geq2: {record['summary']['missing_unmasked_histograms']}; no count cut applied")
        name = f"run{run}-count-distribution.png"
        canvas.SaveAs(str(out/name))
        artifacts.append(name)
        canvas.Close()

        towers = sorted({(r["module"], r["row"], r["column"]) for r in cells})
        layers = sorted({r["layer"] for r in cells})
        tx, ly = {t: i+1 for i, t in enumerate(towers)}, {l: i+1 for i, l in enumerate(layers)}
        canvas = ROOT.TCanvas(f"occupancy_{run}", "", max(1200, len(towers)*29), 760)
        canvas.SetLeftMargin(.065)
        canvas.SetRightMargin(.14)
        canvas.SetBottomMargin(.24)
        canvas.SetTopMargin(.18)
        canvas.SetLogz()
        occupancy = ROOT.TH2D(f"occupancy_map_{run}",
                              f"Run {run}: selected per-cell entries;;Detector layer",
                              len(towers), .5, len(towers)+.5, len(layers), .5, len(layers)+.5)
        occupancy.SetDirectory(0)
        occupancy.SetMinimum(.5)
        occupancy.SetMaximum(max(1, max_count)*1.05)
        for t, index in tx.items():
            occupancy.GetXaxis().SetBinLabel(index, f"M{t[0]} r{t[1]} c{t[2]}")
        for layer, index in ly.items():
            occupancy.GetYaxis().SetBinLabel(index, str(layer))
        occupancy.GetXaxis().LabelsOption("v")
        occupancy.GetXaxis().SetLabelSize(.025)
        marks = []
        for cell in cells:
            x, y = tx[(cell["module"], cell["row"], cell["column"])], ly[cell["layer"]]
            if cell["bc"] < 2:
                marker = ROOT.TMarker(x, y, 5)
                marker.SetMarkerColor(ROOT.kGray+2)
            elif not cell["has_histogram"]:
                marker = ROOT.TMarker(x, y, 29)
                marker.SetMarkerColor(ROOT.kRed+1)
            elif cell["entries"] == 0:
                marker = ROOT.TMarker(x, y, 24)
                marker.SetMarkerColor(ROOT.kBlack)
            else:
                occupancy.SetBinContent(x, y, cell["entries"])
                continue
            marker.SetMarkerSize(.95)
            marks.append(marker)
        occupancy.Draw("COLZ")
        for marker in marks:
            marker.Draw()
        label = ROOT.TLatex()
        label.SetNDC(True)
        label.SetTextSize(.026)
        label.DrawLatex(.07, .915, "BC#geq2 occupancy; grey #times = BC<2; red star = missing; open circle = zero")
        label.DrawLatex(.07, .87, "Selected cell counts, not distinct run events; logarithmic colour scale")
        label.DrawLatex(.36, .09, "Module / row / column")
        name = f"run{run}-occupancy.png"
        canvas.SaveAs(str(out/name))
        artifacts.append(name)
        canvas.Close()
    return artifacts


def analyze(work, runs, out, ROOT):
    work, out = Path(work).expanduser().resolve(), Path(out).expanduser().absolute()
    if len(set(runs)) != len(runs) or not runs or any(run < 0 for run in runs):
        raise ValueError("runs must be a nonempty list of distinct nonnegative integers")
    if out.exists() or out.is_symlink():
        raise ValueError(f"output already exists: {out}")
    paths = {run: source_paths(work, run) for run in runs}
    inputs = []
    for run, (hist, calib, preceding) in paths.items():
        for path in (hist, calib):
            if not path.is_file():
                raise ValueError(f"missing input for run {run}: {path}")
            inputs.append(path)
        if preceding.is_file():
            inputs.append(preceding)
    hashes = {str(path): digest(path) for path in inputs}
    # Only this new directory is writable; all ROOT inputs are opened READ.
    out.mkdir(parents=True, exist_ok=False)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    rows, records = [], []
    ROOT.gROOT.SetBatch(True)
    for run in runs:
        run_rows, record = inspect_run(ROOT, run, *paths[run])
        rows.extend(run_rows)
        records.append(record)
    write_csv(out/"cells.csv", rows)
    comparisons = compare_runs(rows, runs)
    write_csv(out/"cell-counts-across-runs.csv", comparisons)
    artifacts = plots(ROOT, out, rows, records)
    current = {str(path): digest(path) for path in inputs}
    if current != hashes:
        write_json(out/"input-mutation.json", dict(before=hashes, after=current))
        raise RuntimeError(f"input changed during analysis; partial outputs preserved at {out}")
    report = dict(schema=1, note=NOTE, started_utc=started,
                  finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  ROOT_version=ROOT.gROOT.GetVersion(), work=str(work), input_sha256=hashes,
                  inputs_unchanged=True, script_sha256=digest(__file__), runs=records,
                  geometry_inconsistent_cells=[r["cell_id"] for r in comparisons if not r["geometry_consistent"]],
                  plots=artifacts)
    write_json(out/"summary.json", report)
    with (out/"README.md").open("x", encoding="utf-8") as stream:
        stream.write("# Existing HV histogram inventory\n\n" + NOTE + "\n\n")
        stream.write("Inputs were hashed before and after this analysis and were unchanged. "
                     "Stored function presence/parameters do not supply minimizer status or establish calibration validity.\n\n")
        stream.write("| Run | Vop | Present BC≥2 | Missing BC≥2 | Min | Median | Max |\n|---:|---:|---:|---:|---:|---:|---:|\n")
        for record in records:
            s = record["summary"]
            stream.write(f"| {record['run']} | {record['calibration_metadata'].get('Vop', 'unknown')} | {s['comparison_population']} | {s['missing_unmasked_histograms']} | {s['minimum']} | {s['median']} | {s['maximum']} |\n")
        stream.write("\nAll calibration cells are listed in `cells.csv`; missing numbers are `nan`. "
                     "`cell-counts-across-runs.csv` matches cells by ID and flags changed geometry. "
                     "`summary.json` includes file hashes, stored TF1 metadata and descriptive threshold counts.\n\n")
        for name in artifacts:
            stream.write(f"- [{name}]({name})\n")
    print(json.dumps(json_safe({"out": str(out), "inputs_unchanged": True,
                               "runs": [{"run": r["run"], **r["summary"]} for r in records]}), indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--runs", type=int, nargs="+", default=list(range(194, 203)))
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    args = parser.parse_args()
    # Import only after parsing so --help also works without PyROOT.
    import ROOT
    analyze(args.work, args.runs, args.out, ROOT)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"analyze_hv_histograms: {error}", file=sys.stderr)
        raise SystemExit(1)
