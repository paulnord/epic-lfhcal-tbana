#!/usr/bin/env python3
"""Plot LFHCal step-to-step calibration changes with a signed-log transform.

For each dataset/model/cell and each refinement transition, define

    delta_n = (scale_h(n) - scale_h(n-1)) / scale_h(n-1)

for the five transitions

    MIP->R1, R1->R2, R2->R3, R3->R4, R4->R5

and transform it numerically as

    q_n = sign(delta_n) * log10(1 + abs(delta_n) / r0)

where r0 defaults to 1e-4 (0.01%).  The sign is preserved and a shrinking
sequence toward zero is direct evidence that the iterative calibration changes
are becoming smaller.  Unlike the refine5-residual plot, no iteration is
defined to be the correct answer.

Input is one or more campaign roots containing reports/*-comparison.csv as
written by adaptive_fulltests.py / recover_adaptive_d1.py.

Outputs are separate legacy/adaptive PNGs, optional PDFs, a transformed CSV,
and a median/central-68%-band CSV.  Each dataset lane also gets a symmetric
ADC reference ruler at 0.01, 0.1, 1, and 10 ADC, converted with that
dataset/model's median R5 scale.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np

STAGES = ("mip", "refine1", "refine2", "refine3", "refine4", "refine5")
TRANSITIONS = (
    ("mip", "refine1", "MIP→R1"),
    ("refine1", "refine2", "R1→R2"),
    ("refine2", "refine3", "R2→R3"),
    ("refine3", "refine4", "R3→R4"),
    ("refine4", "refine5", "R4→R5"),
)
MODELS = ("legacy", "adaptive")
DEFAULT_DATASETS = None
DEFAULT_OUT = "lfhcal-step-convergence"
DEFAULT_LANE_SCALE = 0.12
DEFAULT_HEIGHT_PER_DATASET = 0.58
DEFAULT_ALPHA = 0.08
DEFAULT_LINEWIDTH = 0.50
ADC_REFERENCES = (0.01, 0.1, 1.0, 10.0)


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
                for before, after, label in TRANSITIONS:
                    x0 = values.get(before)
                    x1 = values.get(after)
                    if x0 is None or x1 is None or x0 == 0:
                        continue
                    delta = (x1 - x0) / x0
                    q = signed_log(delta, r0)
                    q_plot = float(np.clip(q, -transform_clip, transform_clip))
                    rows.append(
                        dict(
                            dataset=dataset,
                            model=model,
                            cell_id=cell,
                            transition=label,
                            before_stage=before,
                            after_stage=after,
                            before_scale_h=x0,
                            after_scale_h=x1,
                            fractional_step=delta,
                            signed_log_step=q,
                            signed_log_step_plot=q_plot,
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
            for _, _, label in TRANSITIONS:
                vals = [
                    r["signed_log_step_plot"]
                    for r in rows
                    if r["dataset"] == dataset
                    and r["model"] == model
                    and r["transition"] == label
                ]
                if not vals:
                    continue
                arr = np.asarray(vals, dtype=float)
                out.append(
                    dict(
                        dataset=dataset,
                        model=model,
                        transition=label,
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

    labels = [label for _, _, label in TRANSITIONS]
    transition_x = {label: i for i, label in enumerate(labels)}
    lane_for = {dataset: i + 1 for i, dataset in enumerate(datasets)}

    by_track = {}
    for row in rows:
        if row["model"] != model:
            continue
        by_track.setdefault((row["dataset"], row["cell_id"]), {})[
            row["transition"]
        ] = row

    height = max(8.0, height_per_dataset * len(datasets) + 2.0)
    fig, ax = plt.subplots(figsize=(13.0, height))

    for dataset in datasets:
        lane = lane_for[dataset]
        ax.axhline(lane, linewidth=0.7, alpha=0.28)

        # Physical scale reference around the zero-change lane.  Convert
        # 0.01, 0.1, 1, and 10 ADC to this signed-log coordinate using the
        # dataset/model's median R5 scale.  The ruler is symmetric: labels are
        # shown on one side, with matching unlabeled ticks on the other.
        final_scales = [
            r["after_scale_h"]
            for r in rows
            if r["dataset"] == dataset
            and r["model"] == model
            and r["transition"] == "R4→R5"
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

                xmark = -0.24
                cap_left, cap_right = -0.28, -0.20
                outer = max(dy for _, dy in adc_marks)
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

                # Mirror the same ADC ruler on the right side of the plot.
                last_x = len(labels) - 1
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
        for label in labels:
            row = track.get(label)
            if row is None:
                xs.append(np.nan)
                ys.append(np.nan)
            else:
                xs.append(transition_x[label])
                ys.append(row["y"])
        ax.plot(xs, ys, linewidth=linewidth, alpha=alpha)

    for dataset in datasets:
        lane = lane_for[dataset]
        xs, med, lo, hi = [], [], [], []
        for label in labels:
            vals = [
                r["signed_log_step_plot"]
                for r in rows
                if r["dataset"] == dataset
                and r["model"] == model
                and r["transition"] == label
            ]
            if not vals:
                continue
            arr = np.asarray(vals, dtype=float)
            xs.append(transition_x[label])
            med.append(lane + lane_scale * float(np.median(arr)))
            lo.append(lane + lane_scale * float(np.quantile(arr, 0.16)))
            hi.append(lane + lane_scale * float(np.quantile(arr, 0.84)))
        ax.fill_between(xs, lo, hi, alpha=band_alpha)
        ax.plot(xs, med, linewidth=median_width, color="black")

    ax.set_xticks(range(len(labels)), labels)
    ax.set_yticks([lane_for[d] for d in datasets], [d.upper() for d in datasets])
    ax.set_xlabel("Refinement step")
    ax.set_ylabel(
        "Calibration set; ΔH shown on signed-log scale"
    )
    ax.set_title(f"LFHCal calibration step size: {model}")
    ax.set_xlim(-0.48, (len(labels) - 1) + 0.48)
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
    default_alpha=DEFAULT_ALPHA,
    default_linewidth=DEFAULT_LINEWIDTH,
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
        help="Fractional step scale inside signed log; 1e-4 = 0.01%%",
    )
    ap.add_argument(
        "--transform-clip",
        type=float,
        default=4.0,
        help="Clip plotted signed-log step at +/- this value",
    )
    ap.add_argument(
        "--lane-scale",
        type=float,
        default=default_lane_scale,
        help="Vertical lane displacement per unit signed-log step",
    )
    ap.add_argument("--alpha", type=float, default=default_alpha)
    ap.add_argument("--linewidth", type=float, default=default_linewidth)
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
        raise SystemExit("No finite consecutive scale_h pairs found")

    transformed = Path(str(args.out) + "-transformed.csv")
    bands = Path(str(args.out) + "-bands.csv")
    write_rows(transformed, rows)
    write_rows(bands, band_rows(rows, datasets))
    print(transformed)
    print(bands)

    print("datasets:", " ".join(d.upper() for d in datasets))
    print("r0:", args.r0)
    print(
        "transform: sign(delta) * log10(1 + abs(delta)/r0), "
        "delta=(scale_h-after - scale_h-before)/scale_h-before"
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
