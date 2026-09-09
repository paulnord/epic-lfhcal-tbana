#!/usr/bin/env python3
"""
MCMC for Run 308, cell 1473, refine1 using the exact production histogram
and production fit window. The Landau-Gaussian model is supplied by
production_langau.py in this directory.

Half the chains should be started at the ROOT QRLMNE0 broad solution and half
at the QRLN0 collapsed-sigma solution.
"""
import argparse
import csv
import math
from pathlib import Path

import numpy as np
import ROOT
import production_langau

BROAD = np.array([61.9291, 4.8844, 20.9411], dtype=float)      # MP, LW, GS
COLLAPSED = np.array([67.6173, 8.4137, 0.0511], dtype=float)


def walk(d, prefix=""):
    for k in d.GetListOfKeys():
        o = k.ReadObj()
        p = f"{prefix}/{k.GetName()}"
        if o.InheritsFrom("TDirectory"):
            yield from walk(o, p)
        else:
            yield p, o


def load_hist(path, cell, lo, hi):
    f = ROOT.TFile.Open(str(path), "READ")
    if not f or f.IsZombie():
        raise RuntimeError(f"cannot open {path}")
    wanted = f"hspectramipTriggADCCellID{cell}"
    found = []
    for p, o in walk(f):
        if o.InheritsFrom("TH1") and o.GetName() == wanted:
            found.append((p, o))
    if not found:
        f.Close()
        raise RuntimeError(f"{wanted} not found in {path}")
    p, o = found[0]
    h = o.Clone("mcmc_source")
    h.SetDirectory(0)
    f.Close()

    xs, ns = [], []
    for i in range(1, h.GetNbinsX() + 1):
        x = float(h.GetBinCenter(i))
        if lo <= x <= hi:
            xs.append(x)
            ns.append(float(h.GetBinContent(i)))
    return p, h, np.asarray(xs), np.asarray(ns)


def shape_values(xs, mpv, lw, gs):
    return np.asarray(
        [production_langau.expected_value(float(x), float(lw), float(mpv), 1.0, float(gs))
         for x in xs],
        dtype=float,
    )


def profiled_nll(xs, ns, theta):
    mpv, lw, gs = map(float, theta)
    shape = shape_values(xs, mpv, lw, gs)
    if np.any(~np.isfinite(shape)) or np.any(shape <= 0):
        return math.inf, math.nan
    denom = float(shape.sum())
    if denom <= 0:
        return math.inf, math.nan
    area = float(ns.sum() / denom)
    mu = area * shape
    if np.any(mu <= 0) or np.any(~np.isfinite(mu)):
        return math.inf, area
    nz = ns > 0
    dev = float(mu[~nz].sum())
    dev += float(np.sum(mu[nz] + ns[nz] * np.log(ns[nz] / mu[nz]) - ns[nz]))
    return dev, area


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hist", required=True, type=Path)
    ap.add_argument("--cell", type=int, default=1473)
    ap.add_argument("--range-low", type=float, default=54.87849070342843)
    ap.add_argument("--range-high", type=float, default=365.85660468952284)
    ap.add_argument("--pedestal-sigma", type=float, default=2.4319)
    ap.add_argument("--avmip", type=float, default=91.46415117238071)
    ap.add_argument("--mpv-high-factor", type=float, default=2.2)
    ap.add_argument("--init", choices=["broad", "collapsed"], required=True)
    ap.add_argument("--chain", type=int, required=True)
    ap.add_argument("--iterations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--output", required=True, type=Path)
    a = ap.parse_args()

    ROOT.gROOT.SetBatch(True)
    production_langau.declare_cpp()

    hpath, h, xs, ns = load_hist(a.hist, a.cell, a.range_low, a.range_high)

    bounds = np.array([
        [0.5 * a.avmip, a.mpv_high_factor * a.avmip],
        [0.1, 100.0],
        [0.01 * a.pedestal_sigma, 30.0 * a.pedestal_sigma],
    ], dtype=float)

    theta = BROAD.copy() if a.init == "broad" else COLLAPSED.copy()
    if np.any(theta < bounds[:, 0]) or np.any(theta > bounds[:, 1]):
        raise RuntimeError(f"initial point {theta} outside bounds {bounds}")

    seed = a.seed if a.seed is not None else 1473000 + a.chain
    rng = np.random.default_rng(seed)

    nll, area = profiled_nll(xs, ns, theta)
    if not math.isfinite(nll):
        raise RuntimeError("initial point has non-finite likelihood")

    # Symmetric two-scale random-walk proposal. The occasional large move
    # gives a chain initialized in the sigma~0 ROOT basin a fair chance to
    # cross any shallow barrier without changing the stationary distribution.
    small = np.array([0.35, 0.25, 0.55])
    large = np.array([2.5, 1.8, 5.0])
    p_large = 0.05

    a.output.parent.mkdir(parents=True, exist_ok=True)
    accepted_total = 0
    accepted_large = 0
    proposed_large = 0

    with a.output.open("w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["iteration", "mpv", "landau_width", "gauss_sigma",
                    "area_mle", "nll", "accepted", "proposal"])
        for it in range(a.iterations):
            use_large = bool(rng.random() < p_large)
            scales = large if use_large else small
            if use_large:
                proposed_large += 1

            proposal = theta + rng.normal(0.0, scales)
            accepted = False
            new_nll, new_area = math.inf, math.nan

            if np.all(proposal >= bounds[:, 0]) and np.all(proposal <= bounds[:, 1]):
                new_nll, new_area = profiled_nll(xs, ns, proposal)
                if math.isfinite(new_nll):
                    log_alpha = nll - new_nll
                    if log_alpha >= 0.0 or math.log(rng.random()) < log_alpha:
                        theta = proposal
                        nll = new_nll
                        area = new_area
                        accepted = True
                        accepted_total += 1
                        if use_large:
                            accepted_large += 1

            w.writerow([it, *theta, area, nll, int(accepted),
                        "large" if use_large else "small"])

    broad_nll, broad_area = profiled_nll(xs, ns, BROAD)
    collapsed_nll, collapsed_area = profiled_nll(xs, ns, COLLAPSED)

    print(f"histogram: {hpath}")
    print(f"range: [{a.range_low:.6f}, {a.range_high:.6f}]  bins={len(xs)} count={ns.sum():.0f}")
    print(f"init={a.init} chain={a.chain} seed={seed}")
    print(f"broad:     nll={broad_nll:.6f} area_mle={broad_area:.6f}")
    print(f"collapsed: nll={collapsed_nll:.6f} area_mle={collapsed_area:.6f}")
    print(f"delta_nll(collapsed-broad)={collapsed_nll-broad_nll:.6f}")
    print(f"acceptance={accepted_total/a.iterations:.4f}")
    if proposed_large:
        print(f"large_proposal_acceptance={accepted_large/proposed_large:.4f}")
    print(f"final: MP={theta[0]:.6f} LW={theta[1]:.6f} GS={theta[2]:.6f} nll={nll:.6f}")
    print(a.output)


if __name__ == "__main__":
    main()
