#!/usr/bin/env python3
import argparse
import csv
import math
from pathlib import Path
import numpy as np

PARAMS = ["mpv", "landau_width", "gauss_sigma"]


def load_raw(path):
    return np.genfromtxt(path, delimiter="\t", names=True)


def retained(raw, burn, path):
    if len(raw) <= burn:
        raise RuntimeError(f"{path}: only {len(raw)} rows, burn={burn}")
    return raw[burn:]


def split_rhat(chains, name):
    halves = []
    for c in chains:
        x = np.asarray(c[name], dtype=float)
        n = len(x) // 2
        halves.extend([x[:n], x[-n:]])
    n = min(map(len, halves))
    a = np.asarray([x[:n] for x in halves])
    means = a.mean(axis=1)
    variances = a.var(axis=1, ddof=1)
    W = variances.mean()
    B = n * means.var(ddof=1)
    varhat = ((n - 1) / n) * W + B / n
    return math.sqrt(varhat / W)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chains", nargs="+", type=Path)
    ap.add_argument("--burn", type=int, default=3000)
    ap.add_argument("--output", type=Path, default=Path("refine1-posterior.tsv"))
    ap.add_argument("--summary", type=Path, default=Path("refine1-summary.txt"))
    a = ap.parse_args()

    raw = [load_raw(p) for p in a.chains]
    chains = [retained(r, a.burn, p) for r, p in zip(raw, a.chains)]

    a.output.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for ci, c in enumerate(chains):
        for j in range(len(c)):
            rows.append((ci, int(c["iteration"][j]), *(float(c[p][j]) for p in PARAMS),
                         float(c["area_mle"][j]), float(c["nll"][j])))

    with a.output.open("w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["chain", "iteration", *PARAMS, "area_mle", "nll"])
        w.writerows(rows)

    lines = [
        f"chains={len(chains)}",
        f"iterations_per_chain={len(raw[0])}",
        f"burn_in={a.burn}",
        f"retained_total={sum(len(c) for c in chains)}",
    ]

    for p in PARAMS:
        allx = np.concatenate([np.asarray(c[p], dtype=float) for c in chains])
        q16, q50, q84 = np.quantile(allx, [0.16, 0.50, 0.84])
        lines.append(
            f"{p}: mean={allx.mean():.6g} sd={allx.std(ddof=1):.6g} "
            f"median={q50:.6g} 68%=[{q16:.6g},{q84:.6g}] "
            f"split_rhat={split_rhat(chains,p):.5f}"
        )

    # Escape diagnostic is computed from the unburned chain.
    for ci, r in enumerate(raw):
        gs = np.asarray(r["gauss_sigma"], dtype=float)
        for threshold in (1.0, 5.0, 10.0, 15.0):
            idx = np.nonzero(gs > threshold)[0]
            first = int(r["iteration"][idx[0]]) if len(idx) else None
            lines.append(f"chain_{ci}_first_sigma_gt_{threshold:g}={first}")

        nll = np.asarray(r["nll"], dtype=float)
        best = int(np.argmin(nll))
        lines.append(
            f"chain_{ci}_best: iteration={int(r['iteration'][best])} "
            f"mpv={float(r['mpv'][best]):.6g} "
            f"landau_width={float(r['landau_width'][best]):.6g} "
            f"gauss_sigma={float(r['gauss_sigma'][best]):.6g} "
            f"nll={float(r['nll'][best]):.6g}"
        )

    text = "\n".join(lines) + "\n"
    a.summary.write_text(text)
    print(text, end="")
    print(f"wrote {a.output}")
    print(f"wrote {a.summary}")


if __name__ == "__main__":
    main()
