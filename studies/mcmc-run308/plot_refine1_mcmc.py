#!/usr/bin/env python3
import argparse
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import ROOT
import production_langau

BROAD = np.array([61.9291, 4.8844, 20.9411], dtype=float)
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
    wanted = f"hspectramipTriggADCCellID{cell}"
    for p, o in walk(f):
        if o.InheritsFrom("TH1") and o.GetName() == wanted:
            h = o.Clone("plot_source")
            h.SetDirectory(0)
            f.Close()
            xs, ns = [], []
            for i in range(1, h.GetNbinsX() + 1):
                x = float(h.GetBinCenter(i))
                if lo <= x <= hi:
                    xs.append(x)
                    ns.append(float(h.GetBinContent(i)))
            return np.asarray(xs), np.asarray(ns)
    f.Close()
    raise RuntimeError(f"{wanted} not found")


def curve(xs, ns, point):
    mpv, lw, gs = point
    shape = np.asarray([
        production_langau.expected_value(float(x), float(lw), float(mpv), 1.0, float(gs))
        for x in xs
    ])
    area = float(ns.sum() / shape.sum())
    return area * shape


def scatter_plot(post, xname, yname, xlabel, ylabel, path):
    fig, ax = plt.subplots()
    thin = max(1, len(post) // 20000)
    ax.scatter(post[xname][::thin], post[yname][::thin], s=3, alpha=0.15,
               label="MCMC posterior")
    ix = {"mpv": 0, "landau_width": 1, "gauss_sigma": 2}
    ax.scatter([BROAD[ix[xname]]], [BROAD[ix[yname]]], marker="*", s=140,
               label="ROOT QRLMNE0 broad")
    ax.scatter([COLLAPSED[ix[xname]]], [COLLAPSED[ix[yname]]], marker="x", s=90,
               label="ROOT QRLN0 collapsed")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--posterior", required=True, type=Path)
    ap.add_argument("--chains", nargs="+", required=True, type=Path)
    ap.add_argument("--hist", required=True, type=Path)
    ap.add_argument("--cell", type=int, default=1473)
    ap.add_argument("--range-low", type=float, default=54.87849070342843)
    ap.add_argument("--range-high", type=float, default=365.85660468952284)
    ap.add_argument("--outdir", type=Path, default=Path("refine1-plots"))
    a = ap.parse_args()

    ROOT.gROOT.SetBatch(True)
    production_langau.declare_cpp()
    a.outdir.mkdir(parents=True, exist_ok=True)

    post = np.genfromtxt(a.posterior, delimiter="\t", names=True)

    scatter_plot(post, "landau_width", "gauss_sigma", "Landau width", "Gaussian sigma",
                 a.outdir / "landau_width-vs-sigma.png")
    scatter_plot(post, "mpv", "gauss_sigma", "MP parameter", "Gaussian sigma",
                 a.outdir / "mpv-vs-sigma.png")
    scatter_plot(post, "mpv", "landau_width", "MP parameter", "Landau width",
                 a.outdir / "mpv-vs-landau_width.png")

    fig, ax = plt.subplots()
    for p in a.chains:
        c = np.genfromtxt(p, delimiter="\t", names=True)
        ax.plot(c["iteration"], c["gauss_sigma"], lw=0.8, label=p.stem)
    ax.axhline(BROAD[2], ls="--", label="ROOT broad sigma")
    ax.axhline(COLLAPSED[2], ls=":", label="ROOT collapsed sigma")
    ax.set_xlabel("MCMC iteration")
    ax.set_ylabel("Gaussian sigma")
    ax.legend(fontsize="small")
    fig.tight_layout()
    fig.savefig(a.outdir / "sigma-traces.png", dpi=180)
    plt.close(fig)

    xs, ns = load_hist(a.hist, a.cell, a.range_low, a.range_high)
    med = np.array([
        np.median(post["mpv"]),
        np.median(post["landau_width"]),
        np.median(post["gauss_sigma"]),
    ])
    fig, ax = plt.subplots()
    ax.errorbar(xs, ns, yerr=np.sqrt(np.maximum(ns, 1.0)), fmt=".", ms=3,
                label="refine1 data")
    ax.plot(xs, curve(xs, ns, BROAD), label="ROOT QRLMNE0 broad")
    ax.plot(xs, curve(xs, ns, COLLAPSED), label="ROOT QRLN0 collapsed")
    ax.plot(xs, curve(xs, ns, med), label="MCMC posterior median")
    ax.set_xlabel("ADC")
    ax.set_ylabel("Counts / bin")
    ax.set_xlim(a.range_low, a.range_high)
    ax.legend()
    fig.tight_layout()
    fig.savefig(a.outdir / "data-and-solutions.png", dpi=180)
    plt.close(fig)

    print(a.outdir)


if __name__ == "__main__":
    main()
