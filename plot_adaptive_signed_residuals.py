#!/usr/bin/env python3
"""Plot LFHCal calibration convergence as a signed-log residual from refine5.

For each dataset/model/cell, define the fractional residual at calibration pass n

    r_n = (scale_h(n) - scale_h(refine5)) / scale_h(refine5)

and transform it numerically as

    q_n = sign(r_n) * log10(1 + abs(r_n) / r0)

where r0 defaults to 1e-4 (0.01%).  The sign is preserved, refine5 is exactly
zero, and equal fractional deviations above/below the final value have equal
magnitude.  Each dataset is then placed on its own integer-centered lane.

Input is one or more campaign roots containing reports/*-comparison.csv as
written by adaptive_fulltests.py / recover_adaptive_d1.py.

Outputs are separate legacy/adaptive PNGs, optional PDFs, a transformed CSV,
and a median/central-68%-band CSV.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np

STAGES = ("mip", "refine1", "refine2", "refine3", "refine4", "refine5")
STAGE_LABELS = ("MIP", "R1", "R2", "R3", "R4", "R5")
MODELS = ("legacy", "adaptive")
ADC_REFERENCES = (0.01, 0.1, 1.0, 10.0)
DEFAULT_DATASETS = None
DEFAULT_OUT = "lfhcal-signed-residual"
DEFAULT_LANE_SCALE = 0.12
DEFAULT_HEIGHT_PER_DATASET = 0.58


def parse_float(value):
    if value in (None, "", "?"):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def dataset_sort_key(code):
    head = "".join(c for c in code if not c.isdigit())
    tail = "".join(c for c in code if c.isdigit())
    return (head, int(tail) if tail else -1, code)


def load_campaigns(roots):
    data = {}
    sources = {}
    for root in roots:
        report_dir = root / "reports"
        if not report_dir.is_dir():
            raise ValueError(f"No reports directory: {report_dir}")
        files = sorted(report_dir.glob("*-comparison.csv"))
        if not files:
            raise ValueError(f"No *-comparison.csv files in {report_dir}")
        for path in files:
            dataset = path.name[:-len("-comparison.csv")].lower()
            if dataset in data:
                raise ValueError(
                    f"Dataset {dataset} appears in both {sources[dataset]} and {path}"
                )
            by_model = {m: {} for m in MODELS}
            with path.open(newline="") as stream:
                reader = csv.DictReader(stream)
                required = {"stage", "cell_id", "legacy_scale_h", "adaptive_scale_h"}
                missing = required.difference(reader.fieldnames or ())
                if missing:
                    raise ValueError(f"{path}: missing columns {sorted(missing)}")
                for row in reader:
                    stage = row["stage"]
                    if stage not in STAGES:
                        continue
                    cell = int(row["cell_id"])
                    for model in MODELS:
                        value = parse_float(row[f"{model}_scale_h"])
                        if value is not None:
                            by_model[model].setdefault(cell, {})[stage] = value
            data[dataset] = by_model
            sources[dataset] = path
    if not data:
        raise ValueError("No comparison data loaded")
    return data, sources


def signed_log_residual(scale, final_scale, r0):
    if final_scale == 0:
        return None, None
    residual = (scale - final_scale) / final_scale
    if residual == 0:
        return 0.0, 0.0
    transformed = math.copysign(math.log10(1.0 + abs(residual) / r0), residual)
    return residual, transformed




def signed_log(value, r0):
    if value == 0:
        return 0.0
    return math.copysign(math.log10(1.0 + abs(value) / r0), value)

def transform(data, datasets, r0, transform_clip, lane_scale):
    rows = []
    lane_for = {dataset: i + 1 for i, dataset in enumerate(datasets)}
    for dataset in datasets:
        lane = lane_for[dataset]
        for model in MODELS:
            for cell, values in sorted(data[dataset][model].items()):
                final_scale = values.get("refine5")
                if final_scale is None or final_scale == 0:
                    continue
                for stage in STAGES:
                    scale = values.get(stage)
                    if scale is None:
                        continue
                    residual, q = signed_log_residual(scale, final_scale, r0)
                    if q is None:
                        continue
                    q_plot = float(np.clip(q, -transform_clip, transform_clip))
                    rows.append(
                        dict(
                            dataset=dataset,
                            model=model,
                            cell_id=cell,
                            stage=stage,
                            scale_h=scale,
                            final_scale_h=final_scale,
                            fractional_residual=residual,
                            signed_log_residual=q,
                            signed_log_residual_plot=q_plot,
                            lane=lane,
                            y=lane + lane_scale * q_plot,
                        )
                    )
    return rows, lane_for


def write_rows(path, rows):
    if not rows:
        raise ValueError(f"Refusing to write empty report: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def band_rows(rows, datasets):
    out = []
    for dataset in datasets:
        for model in MODELS:
            for stage in STAGES:
                vals = [
                    r["signed_log_residual_plot"]
                    for r in rows
                    if r["dataset"] == dataset
                    and r["model"] == model
                    and r["stage"] == stage
                ]
                if not vals:
                    continue
                arr = np.asarray(vals, dtype=float)
                out.append(
                    dict(
                        dataset=dataset,
                        model=model,
                        stage=stage,
                        n=len(arr),
                        median=float(np.median(arr)),
                        q16=float(np.quantile(arr, 0.16)),
                        q84=float(np.quantile(arr, 0.84)),
                    )
                )
    return out


def plot_model(
    rows,
    datasets,
    model,
    outstem,
    lane_scale,
    alpha,
    linewidth,
    band_alpha,
    median_width,
    height_per_dataset,
    r0,
    transform_clip,
    pdf,
    show,
):
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit("matplotlib is required for plotting") from exc

    stage_x = {stage: i for i, stage in enumerate(STAGES)}
    lane_for = {dataset: i + 1 for i, dataset in enumerate(datasets)}

    by_track = {}
    for row in rows:
        if row["model"] != model:
            continue
        by_track.setdefault((row["dataset"], row["cell_id"]), {})[row["stage"]] = row

    height = max(8.0, height_per_dataset * len(datasets) + 2.0)
    fig, ax = plt.subplots(figsize=(13.0, height))

    for dataset in datasets:
        lane = lane_for[dataset]
        ax.axhline(lane, linewidth=0.7, alpha=0.28)

        final_scales = [
            r["final_scale_h"]
            for r in rows
            if r["dataset"] == dataset and r["model"] == model
        ]
        if final_scales:
            ref_scale = float(np.median(np.asarray(final_scales, dtype=float)))
            if ref_scale > 0:
                adc_marks = []
                for adc in ADC_REFERENCES:
                    q_adc = min(
                        transform_clip,
                        abs(signed_log(adc / ref_scale, r0)),
                    )
                    adc_marks.append((adc, lane_scale * q_adc))

                outer = max(dy for _, dy in adc_marks)

                # Left ruler.
                xmark = -0.24
                cap_left, cap_right = -0.28, -0.20
                ax.vlines(
                    xmark,
                    lane - outer,
                    lane + outer,
                    color="black",
                    linewidth=0.7,
                    alpha=0.65,
                )
                for adc, dy in adc_marks:
                    ax.hlines(
                        [lane - dy, lane + dy],
                        cap_left,
                        cap_right,
                        color="black",
                        linewidth=0.7,
                        alpha=0.65,
                    )
                    ax.text(
                        -0.30,
                        lane - dy,
                        f"{adc:g}",
                        ha="right",
                        va="center",
                        fontsize=6,
                    )
                ax.text(
                    -0.30,
                    lane,
                    "ADC",
                    ha="right",
                    va="center",
                    fontsize=6,
                    fontweight="bold",
                )

                # Matching ruler on the right.
                last_x = len(STAGES) - 1
                xmark_r = last_x + 0.24
                cap_left_r, cap_right_r = last_x + 0.20, last_x + 0.28
                ax.vlines(
                    xmark_r,
                    lane - outer,
                    lane + outer,
                    color="black",
                    linewidth=0.7,
                    alpha=0.65,
                )
                for adc, dy in adc_marks:
                    ax.hlines(
                        [lane - dy, lane + dy],
                        cap_left_r,
                        cap_right_r,
                        color="black",
                        linewidth=0.7,
                        alpha=0.65,
                    )
                    ax.text(
                        last_x + 0.30,
                        lane - dy,
                        f"{adc:g}",
                        ha="left",
                        va="center",
                        fontsize=6,
                    )
                ax.text(
                    last_x + 0.30,
                    lane,
                    "ADC",
                    ha="left",
                    va="center",
                    fontsize=6,
                    fontweight="bold",
                )

    for track in by_track.values():
        xs, ys = [], []
        for stage in STAGES:
            row = track.get(stage)
            if row is None:
                xs.append(np.nan)
                ys.append(np.nan)
            else:
                xs.append(stage_x[stage])
                ys.append(row["y"])
        ax.plot(xs, ys, linewidth=linewidth, alpha=alpha)

    for dataset in datasets:
        lane = lane_for[dataset]
        xs, med, lo, hi = [], [], [], []
        for stage in STAGES:
            vals = [
                r["signed_log_residual_plot"]
                for r in rows
                if r["dataset"] == dataset
                and r["model"] == model
                and r["stage"] == stage
            ]
            if not vals:
                continue
            arr = np.asarray(vals, dtype=float)
            xs.append(stage_x[stage])
            med.append(lane + lane_scale * float(np.median(arr)))
            lo.append(lane + lane_scale * float(np.quantile(arr, 0.16)))
            hi.append(lane + lane_scale * float(np.quantile(arr, 0.84)))
        ax.fill_between(xs, lo, hi, alpha=band_alpha)
        ax.plot(xs, med, linewidth=median_width, color="black")

    ax.set_xticks(range(len(STAGES)), STAGE_LABELS)
    ax.set_yticks([lane_for[d] for d in datasets], [d.upper() for d in datasets])
    ax.set_xlabel("Calibration pass")
    ax.set_ylabel("Calibration set; ΔH from own R5 shown on signed-log scale")
    ax.set_title(f"LFHCal calibration convergence: {model}")
    ax.set_xlim(-0.48, (len(STAGES) - 1) + 0.48)
    ax.set_ylim(0.45, len(datasets) + 0.55)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.18)
    fig.tight_layout()

    png = Path(str(outstem) + f"-{model}.png")
    fig.savefig(png, dpi=200)
    print(png)
    if pdf:
        pdf_path = Path(str(outstem) + f"-{model}.pdf")
        fig.savefig(pdf_path)
        print(pdf_path)
    if show:
        plt.show()
    plt.close(fig)


def main(
    default_datasets=DEFAULT_DATASETS,
    default_out=DEFAULT_OUT,
    default_lane_scale=DEFAULT_LANE_SCALE,
    default_height_per_dataset=DEFAULT_HEIGHT_PER_DATASET,
):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        action="append",
        type=Path,
        required=True,
        help="Campaign root containing reports/*-comparison.csv; repeat as needed",
    )
    ap.add_argument("--out", type=Path, default=Path(default_out))
    ap.add_argument(
        "--datasets",
        nargs="+",
        default=default_datasets,
        help="Optional dataset subset/order, e.g. b1 b2 e1 e2 e3",
    )
    ap.add_argument(
        "--r0",
        type=float,
        default=1e-4,
        help="Fractional residual scale inside signed log; 1e-4 = 0.01%%",
    )
    ap.add_argument(
        "--transform-clip",
        type=float,
        default=4.0,
        help="Clip plotted signed-log residual at +/- this value",
    )
    ap.add_argument(
        "--lane-scale",
        type=float,
        default=default_lane_scale,
        help="Vertical lane displacement per unit signed-log residual",
    )
    ap.add_argument("--alpha", type=float, default=0.10, help="Cell-line opacity")
    ap.add_argument("--linewidth", type=float, default=0.55)
    ap.add_argument("--band-alpha", type=float, default=0.08)
    ap.add_argument("--median-width", type=float, default=1.5)
    ap.add_argument(
        "--height-per-dataset",
        type=float,
        default=default_height_per_dataset,
    )
    ap.add_argument("--pdf", action="store_true", help="Also save PDF figures")
    ap.add_argument("--show", action="store_true", help="Display figures interactively")
    args = ap.parse_args()

    if args.r0 <= 0 or args.transform_clip <= 0 or args.lane_scale <= 0:
        ap.error("--r0, --transform-clip, and --lane-scale must be positive")

    roots = [p.resolve() for p in args.root]
    data, sources = load_campaigns(roots)

    if args.datasets:
        requested = [d.lower() for d in args.datasets]
        missing = [d for d in requested if d not in data]
        if missing:
            raise SystemExit("Missing requested datasets: " + " ".join(missing))
        datasets = requested
    else:
        datasets = sorted(data, key=dataset_sort_key)

    rows, _ = transform(
        data,
        datasets,
        args.r0,
        args.transform_clip,
        args.lane_scale,
    )
    if not rows:
        raise SystemExit("No cells with finite refine5 scale_h values found")

    transformed = Path(str(args.out) + "-transformed.csv")
    bands = Path(str(args.out) + "-bands.csv")
    write_rows(transformed, rows)
    write_rows(bands, band_rows(rows, datasets))
    print(transformed)
    print(bands)

    print("datasets:", " ".join(d.upper() for d in datasets))
    print("r0:", args.r0)
    print(
        "transform: sign(r) * log10(1 + abs(r)/r0), "
        "r=(scale_h-stage - scale_h-R5)/scale_h-R5"
    )
    for dataset in datasets:
        print(f"  {dataset.upper():>3}  {sources[dataset]}")

    for model in MODELS:
        plot_model(
            rows,
            datasets,
            model,
            args.out,
            args.lane_scale,
            args.alpha,
            args.linewidth,
            args.band_alpha,
            args.median_width,
            args.height_per_dataset,
            args.r0,
            args.transform_clip,
            args.pdf,
            args.show,
        )


if __name__ == "__main__":
    main()
