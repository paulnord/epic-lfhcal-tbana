#!/usr/bin/env python3
"""Plot full-chain LFHCal calibration convergence on normal-quantile run lanes.

Each dataset gets one horizontal lane centered on an integer.  For a dataset,
a monotonic map is learned from the final (refine5) scale_h distribution and
turns that distribution into normal quantiles.  The same map is then applied
to MIP and refine1..refine4 values, so the plot shows how every cell approaches
its run's final distribution without mixing the very different absolute MIP
scales of the data sets.

By default the reference distribution is the pooled legacy+adaptive refine5
values.  That gives both models exactly the same transformation and therefore
preserves any residual legacy/adaptive difference at the final stage.  Use
--reference each to normalize each model to its own final distribution when the
only question is the shape of convergence.

Input is one or more campaign roots containing reports/*-comparison.csv as
written by adaptive_fulltests.py / recover_adaptive_d1.py.

Example:
  python3 plot_adaptive_convergence.py \
    --root /path/to/first-campaign \
    --root /path/to/remaining-campaign \
    --root /path/to/d1-recovery \
    --out lfhcal-convergence

Outputs:
  lfhcal-convergence-legacy.png
  lfhcal-convergence-adaptive.png
  lfhcal-convergence-transformed.csv
  lfhcal-convergence-bands.csv

Add --pdf to also write PDF copies.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np


STAGES = ("mip", "refine1", "refine2", "refine3", "refine4", "refine5")
STAGE_LABELS = ("MIP", "R1", "R2", "R3", "R4", "R5")
MODELS = ("legacy", "adaptive")


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
            dataset = path.name[: -len("-comparison.csv")].lower()
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


class QuantileMap:
    def __init__(self, values, z_clip):
        values = np.asarray([x for x in values if math.isfinite(x)], dtype=float)
        if values.size < 8:
            raise ValueError(f"Need at least 8 final values; found {values.size}")
        values.sort()
        n = values.size
        probs = (np.arange(n, dtype=float) + 0.5) / n
        normal = NormalDist()
        z = np.array([normal.inv_cdf(float(p)) for p in probs], dtype=float)

        unique, first, counts = np.unique(values, return_index=True, return_counts=True)
        uz = np.empty_like(unique, dtype=float)
        for i, (start, count) in enumerate(zip(first, counts)):
            uz[i] = float(np.mean(z[start : start + count]))

        self.x = unique
        self.z = uz
        self.z_clip = float(z_clip)

    def __call__(self, value):
        # Interpolate inside the final distribution.  Outside it, extrapolate
        # using the end slope so an early-pass shift does not collapse onto a
        # single clipped edge merely because it lies just outside refine5.
        if value < self.x[0] and self.x.size > 1:
            dx = self.x[1] - self.x[0]
            slope = 0.0 if dx == 0 else (self.z[1] - self.z[0]) / dx
            z = self.z[0] + slope * (value - self.x[0])
        elif value > self.x[-1] and self.x.size > 1:
            dx = self.x[-1] - self.x[-2]
            slope = 0.0 if dx == 0 else (self.z[-1] - self.z[-2]) / dx
            z = self.z[-1] + slope * (value - self.x[-1])
        else:
            z = float(np.interp(value, self.x, self.z))
        return float(np.clip(z, -self.z_clip, self.z_clip))


def final_values(data, dataset, model):
    return [
        stages["refine5"]
        for stages in data[dataset][model].values()
        if "refine5" in stages
    ]


def build_maps(data, reference, z_clip):
    maps = {}
    for dataset in data:
        if reference == "each":
            for model in MODELS:
                maps[(dataset, model)] = QuantileMap(
                    final_values(data, dataset, model), z_clip
                )
            continue

        if reference == "pooled":
            values = final_values(data, dataset, "legacy") + final_values(
                data, dataset, "adaptive"
            )
        else:
            values = final_values(data, dataset, reference)
        mapping = QuantileMap(values, z_clip)
        for model in MODELS:
            maps[(dataset, model)] = mapping
    return maps


def transform(data, maps, lane_sigma, datasets):
    rows = []
    lane_for = {dataset: i + 1 for i, dataset in enumerate(datasets)}
    for dataset in datasets:
        lane = lane_for[dataset]
        for model in MODELS:
            mapping = maps[(dataset, model)]
            for cell, values in sorted(data[dataset][model].items()):
                for stage in STAGES:
                    if stage not in values:
                        continue
                    scale = values[stage]
                    z = mapping(scale)
                    rows.append(
                        dict(
                            dataset=dataset,
                            model=model,
                            cell_id=cell,
                            stage=stage,
                            scale_h=scale,
                            z=z,
                            lane=lane,
                            y=lane + lane_sigma * z,
                        )
                    )
    return rows, lane_for


def write_rows(path, rows):
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
                    r["z"]
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
                        median_z=float(np.median(arr)),
                        q16_z=float(np.quantile(arr, 0.16)),
                        q84_z=float(np.quantile(arr, 0.84)),
                    )
                )
    return out


def plot_model(rows, datasets, model, outstem, lane_sigma, alpha, linewidth, pdf, show):
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit(
            "matplotlib is required for plotting. The transformed CSV can still be "
            "made by installing matplotlib or running in the EIC environment."
        ) from exc

    stage_x = {stage: i for i, stage in enumerate(STAGES)}
    lane_for = {dataset: i + 1 for i, dataset in enumerate(datasets)}

    by_track = {}
    for row in rows:
        if row["model"] != model:
            continue
        by_track.setdefault((row["dataset"], row["cell_id"]), {})[row["stage"]] = row

    height = max(8.0, 0.58 * len(datasets) + 2.0)
    fig, ax = plt.subplots(figsize=(13.0, height))

    for dataset in datasets:
        lane = lane_for[dataset]
        ax.axhline(lane, linewidth=0.6, alpha=0.22)

    for (_, _), track in by_track.items():
        xs = []
        ys = []
        for stage in STAGES:
            row = track.get(stage)
            if row is None:
                xs.append(np.nan)
                ys.append(np.nan)
            else:
                xs.append(stage_x[stage])
                ys.append(row["y"])
        ax.plot(xs, ys, linewidth=linewidth, alpha=alpha)

    # Median and central 68% envelope for each dataset.  These are summaries of
    # the same transformed cell trajectories, not an additional normalization.
    for dataset in datasets:
        lane = lane_for[dataset]
        med = []
        lo = []
        hi = []
        xs = []
        for stage in STAGES:
            vals = [
                r["z"]
                for r in rows
                if r["dataset"] == dataset
                and r["model"] == model
                and r["stage"] == stage
            ]
            if not vals:
                continue
            arr = np.asarray(vals, dtype=float)
            xs.append(stage_x[stage])
            med.append(lane + lane_sigma * float(np.median(arr)))
            lo.append(lane + lane_sigma * float(np.quantile(arr, 0.16)))
            hi.append(lane + lane_sigma * float(np.quantile(arr, 0.84)))
        ax.fill_between(xs, lo, hi, alpha=0.12)
        ax.plot(xs, med, linewidth=1.7)

    ax.set_xticks(range(len(STAGES)), STAGE_LABELS)
    ax.set_yticks([lane_for[d] for d in datasets], [d.upper() for d in datasets])
    ax.set_xlabel("Calibration pass")
    ax.set_ylabel("Dataset lane; final distribution mapped to normal quantiles")
    ax.set_title(f"LFHCal calibration convergence: {model}")
    ax.set_xlim(-0.15, len(STAGES) - 0.85)
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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        action="append",
        type=Path,
        required=True,
        help="Campaign root containing reports/*-comparison.csv; repeat as needed",
    )
    ap.add_argument("--out", type=Path, default=Path("lfhcal-convergence"))
    ap.add_argument(
        "--reference",
        choices=("pooled", "legacy", "adaptive", "each"),
        default="pooled",
        help=(
            "Final distribution used for the quantile map. pooled (default) uses "
            "legacy+adaptive together and preserves final method differences; each "
            "normalizes each model separately."
        ),
    )
    ap.add_argument(
        "--lane-sigma",
        type=float,
        default=0.13,
        help="Vertical spacing corresponding to one normal sigma within a lane",
    )
    ap.add_argument(
        "--z-clip",
        type=float,
        default=3.5,
        help="Clip transformed tails at +/- this many sigma",
    )
    ap.add_argument("--alpha", type=float, default=0.045, help="Cell-line opacity")
    ap.add_argument("--linewidth", type=float, default=0.45)
    ap.add_argument("--pdf", action="store_true", help="Also save PDF figures")
    ap.add_argument("--show", action="store_true", help="Display figures interactively")
    args = ap.parse_args()

    if args.lane_sigma <= 0 or args.z_clip <= 0:
        ap.error("--lane-sigma and --z-clip must be positive")

    roots = [p.resolve() for p in args.root]
    data, sources = load_campaigns(roots)
    datasets = sorted(data, key=dataset_sort_key)
    maps = build_maps(data, args.reference, args.z_clip)
    rows, _ = transform(data, maps, args.lane_sigma, datasets)
    if not rows:
        raise SystemExit("No finite scale_h values found")

    transformed = Path(str(args.out) + "-transformed.csv")
    bands = Path(str(args.out) + "-bands.csv")
    write_rows(transformed, rows)
    write_rows(bands, band_rows(rows, datasets))
    print(transformed)
    print(bands)

    print("datasets:", " ".join(d.upper() for d in datasets))
    print("reference:", args.reference)
    for dataset in datasets:
        print(f"  {dataset.upper():>3}  {sources[dataset]}")

    for model in MODELS:
        plot_model(
            rows,
            datasets,
            model,
            args.out,
            args.lane_sigma,
            args.alpha,
            args.linewidth,
            args.pdf,
            args.show,
        )


if __name__ == "__main__":
    main()
