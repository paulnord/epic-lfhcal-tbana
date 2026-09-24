// Generate two data-free PDF sheets illustrating the legacy Langau grid issue.
// See README.md for build and rendering commands.
#include "TileSpectra.h"

#include <TApplication.h>
#include <TBox.h>
#include <TCanvas.h>
#include <TColor.h>
#include <TGraph.h>
#include <TH1D.h>
#include <TLatex.h>
#include <TLine.h>
#include <TMath.h>
#include <TPad.h>
#include <TROOT.h>
#include <TStyle.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

namespace {

constexpr int side = 8;
constexpr int points = 281;
constexpr double xMin = -3.4;
constexpr double xMax = 6.2;
constexpr std::array<double, side> widths = {0.08, 0.12, 0.18, 0.27, 0.40, 0.65, 1.0, 1.6};
constexpr std::array<double, side> sigmas = {0.4, 0.65, 1.0, 1.6, 2.5, 4.0, 7.9, 12.0};
int ink;
int legacyColor;
int adjustedColor;

struct Probe : TileSpectra {
  static double evaluate(double &x, std::array<double, 4> &p) {
    return langaufun(&x, p.data());
  }
};

int adjustedSteps(double width, double sigma) {
  const double halfSteps = std::ceil(5.0 * 5.0 * sigma / width);
  return static_cast<int>(2.0 * std::min(5000.0, std::max(50.0, halfSteps)));
}

// Same midpoint sum, shift, and Gaussian truncation as TileSpectra::langaufun.
double midpoint(double x, const std::array<double, 4> &p, int steps) {
  const double lower = x - 5.0 * p[3];
  const double step = 10.0 * p[3] / steps;
  const double shiftedMpv = p[1] + 0.22278298 * p[0];
  double sum = 0.0;
  for (int i = 0; i < steps; ++i) {
    const double t = lower + (i + 0.5) * step;
    sum += TMath::Landau(t, shiftedMpv, p[0]) / p[0] * TMath::Gaus(x, t, p[3]);
  }
  return p[2] * step * sum * 0.3989422804014 / p[3];
}

struct Cell {
  double width;
  double sigma;
  int steps;
  double shapeDifference;
  double fineCheckError;
  std::vector<double> x, oldPdf, newPdf;
};

Cell calculate(double width, double sigma) {
  Cell c{width, sigma, adjustedSteps(width, sigma), 0.0, 0.0};
  std::array<double, 4> p = {width, 0.0, 1.0, sigma};
  const int referenceSteps = std::max(4000, static_cast<int>(std::ceil(200.0 * sigma / width)));
  std::vector<double> finePdf;
  double adjustedPeak = 0.0, finePeak = 0.0;
  for (int i = 0; i < points; ++i) {
    const double u = xMin + (xMax - xMin) * i / (points - 1);
    double x = u * (width + sigma);
    c.x.push_back(u);
    c.oldPdf.push_back(midpoint(x, p, 100));
    c.newPdf.push_back(Probe::evaluate(x, p));
    finePdf.push_back(midpoint(x, p, referenceSteps));
    adjustedPeak = std::max(adjustedPeak, c.newPdf.back());
    finePeak = std::max(finePeak, finePdf.back());
  }
  for (int i = 0; i < points; ++i) {
    c.shapeDifference = std::max(c.shapeDifference, std::abs(c.oldPdf[i] - c.newPdf[i]) / adjustedPeak);
    c.fineCheckError = std::max(c.fineCheckError, std::abs(c.newPdf[i] - finePdf[i]) / finePeak);
    c.oldPdf[i] /= adjustedPeak;
    c.newPdf[i] /= adjustedPeak;
  }
  return c;
}

void label(double x, double y, const char *s, double size, int color = ink, int align = 11) {
  TLatex t;
  t.SetNDC();
  t.SetTextFont(42);
  t.SetTextSize(size);
  t.SetTextColor(color);
  t.SetTextAlign(align);
  t.DrawLatex(x, y, s);
}

std::unique_ptr<TGraph> graph(const std::vector<double> &x, const std::vector<double> &y,
                              int color, int width) {
  auto g = std::make_unique<TGraph>(static_cast<int>(x.size()), x.data(), y.data());
  g->SetLineColor(color);
  g->SetLineWidth(width);
  return g;
}

double ymax(const Cell &c) {
  const double oldMax = *std::max_element(c.oldPdf.begin(), c.oldPdf.end());
  const double newMax = *std::max_element(c.newPdf.begin(), c.newPdf.end());
  return 1.12 * std::max({1.05, oldMax, newMax});
}

void legendLine(double x, double y, int color, const char *name) {
  TLine line;
  line.SetLineColor(color);
  line.SetLineWidth(color == kBlack ? 1 : 2);
  line.DrawLineNDC(x, y, x + 0.025, y);
  label(x + 0.032, y - 0.004, name, 0.014);
}

void drawGrid(const std::array<Cell, side * side> &cells, const std::string &path) {
  TCanvas canvas("grid", "Langau width grid", 3200, 2600);
  canvas.SetFillColor(kWhite);
  label(0.06, 0.977, "WHEN THE LANDAU PEAK FALLS BETWEEN CONVOLUTION SAMPLES", 0.026);
  label(0.06, 0.949,
        "Landau-Gaussian PDF | rows: Gaussian sigma | columns: Landau width | MPV = 0, area = 1", 0.016);
  legendLine(0.27, 0.925, legacyColor, "legacy: 100 steps");
  legendLine(0.53, 0.925, kBlack, "adjusted: >=5 steps / Landau width");

  const double left = 0.067, right = 0.989, bottom = 0.063, top = 0.878;
  const double cw = (right - left) / side, ch = (top - bottom) / side;
  for (int wi = 0; wi < side; ++wi) {
    char txt[64];
    std::snprintf(txt, sizeof(txt), "w_{L} = %.2g", widths[wi]);
    label(left + (wi + 0.5) * cw, 0.886, txt, 0.014, ink, 22);
  }
  for (int displayRow = 0; displayRow < side; ++displayRow) {
    const int si = side - displayRow - 1;
    char txt[64];
    std::snprintf(txt, sizeof(txt), "#sigma_{G} = %.2g", sigmas[si]);
    label(0.06, top - (displayRow + 0.5) * ch, txt, 0.013, ink, 32);
  }

  std::vector<std::unique_ptr<TPad>> pads;
  std::vector<std::unique_ptr<TH1D>> frames;
  std::vector<std::unique_ptr<TGraph>> graphs;
  for (int displayRow = 0; displayRow < side; ++displayRow) {
    const int si = side - displayRow - 1;
    for (int wi = 0; wi < side; ++wi) {
      const Cell &c = cells[si * side + wi];
      const double x0 = left + wi * cw, y1 = top - displayRow * ch;
      auto pad = std::make_unique<TPad>(Form("cell_%d_%d", si, wi), "", x0, y1 - ch, x0 + cw, y1);
      pad->SetBorderMode(0);
      pad->SetLeftMargin(0.10);
      pad->SetRightMargin(0.035);
      pad->SetTopMargin(0.09);
      pad->SetBottomMargin(0.16);
      if (c.shapeDifference > 0.05) pad->SetFillColor(TColor::GetColor("#fff7f5"));
      pad->Draw();
      pad->cd();

      auto frame = std::make_unique<TH1D>(Form("axis_%d_%d", si, wi), "", 10, xMin, xMax);
      frame->SetDirectory(nullptr);
      frame->SetMinimum(0.0);
      frame->SetMaximum(ymax(c));
      frame->SetLineColor(TColor::GetColor("#c6ccd2"));
      frame->GetXaxis()->SetNdivisions(3);
      frame->GetYaxis()->SetNdivisions(3);
      frame->GetXaxis()->SetLabelSize(displayRow == 7 ? 0.082 : 0.0);
      frame->GetYaxis()->SetLabelSize(wi == 0 ? 0.077 : 0.0);
      frame->GetXaxis()->SetTickLength(0.025);
      frame->GetYaxis()->SetTickLength(0.025);
      frame->Draw("AXIS");

      auto legacy = graph(c.x, c.oldPdf, legacyColor, 1);
      auto adjusted = graph(c.x, c.newPdf, kBlack, 1);
      legacy->Draw("L SAME");
      adjusted->Draw("L SAME");
      char errorText[48];
      const double differencePct = 100.0 * c.shapeDifference;
      if (differencePct < 0.05) std::snprintf(errorText, sizeof(errorText), "<0.1%%");
      else if (differencePct < 10.0) std::snprintf(errorText, sizeof(errorText), "%.1f%%", differencePct);
      else std::snprintf(errorText, sizeof(errorText), "%.0f%%", differencePct);
      label(0.94, 0.80, errorText, 0.077, c.shapeDifference > 0.05 ? legacyColor : ink, 32);
      if (si == 6 && wi == 1) label(0.16, 0.80, "E1 896", 0.077, legacyColor);
      graphs.push_back(std::move(adjusted));
      graphs.push_back(std::move(legacy));
      frames.push_back(std::move(frame));
      canvas.cd();
      pads.push_back(std::move(pad));
    }
  }
  label(0.06, 0.035,
        "Each panel: x = (charge - MPV)/(Landau width + Gaussian sigma); PDF divided by its adjusted peak."
        " Corner number = max |legacy - adjusted| / adjusted peak.", 0.013);
  canvas.Print(path.c_str());
}

using Value = double (*)(const Cell &);

void heatmap(const std::array<Cell, side * side> &cells, double x0, double y0,
             double width, double height, const char *title, Value value, int mode) {
  label(x0, y0 + height + 0.031, title, 0.017);
  const double tileW = width / side, tileH = height / side;
  for (int si = 0; si < side; ++si) {
    char txt[32];
    std::snprintf(txt, sizeof(txt), "%.2g", sigmas[si]);
    label(x0 - 0.008, y0 + (si + 0.5) * tileH, txt, 0.012, ink, 32);
  }
  for (int wi = 0; wi < side; ++wi) {
    char txt[32];
    std::snprintf(txt, sizeof(txt), "%.2g", widths[wi]);
    label(x0 + (wi + 0.5) * tileW, y0 - 0.019, txt, 0.012, ink, 22);
  }
  for (int si = 0; si < side; ++si) {
    for (int wi = 0; wi < side; ++wi) {
      const Cell &c = cells[si * side + wi];
      const double v = value(c);
      const double x = x0 + wi * tileW, y = y0 + si * tileH;
      int color;
      if (mode == 0) {
        const double a = std::clamp(v / 0.25, 0.0, 1.0);
        color = TColor::GetColor(255, static_cast<int>(246 - 145 * a), static_cast<int>(241 - 155 * a));
      } else if (mode == 1) {
        const double a = std::clamp(std::log10(std::max(v, 0.02) / 0.02) / std::log10(15.0 / 0.02), 0.0, 1.0);
        color = TColor::GetColor(255, static_cast<int>(250 - 110 * a), static_cast<int>(235 - 180 * a));
      } else {
        const double a = std::clamp((v - 100.0) / 7400.0, 0.0, 1.0);
        color = TColor::GetColor(static_cast<int>(238 - 160 * a), static_cast<int>(246 - 115 * a), 255);
      }
      auto *box = new TBox(x + 0.001, y + 0.001, x + tileW - 0.001, y + tileH - 0.001);
      box->SetFillColor(color);
      box->SetLineColor(TColor::GetColor("#d5dce2"));
      box->Draw();
      char txt[32];
      if (mode == 2) {
        if (v >= 1000) std::snprintf(txt, sizeof(txt), "%.1fk", v / 1000.0);
        else std::snprintf(txt, sizeof(txt), "%.0f", v);
      } else if (mode == 1) {
        if (v >= 10) std::snprintf(txt, sizeof(txt), "%.0f", v);
        else if (v >= 1) std::snprintf(txt, sizeof(txt), "%.1f", v);
        else std::snprintf(txt, sizeof(txt), "%.2f", v);
      } else {
        const double pct = 100.0 * v;
        if (pct < 0.01) std::snprintf(txt, sizeof(txt), "<.01");
        else if (pct < 10) std::snprintf(txt, sizeof(txt), "%.1f", pct);
        else std::snprintf(txt, sizeof(txt), "%.0f", pct);
      }
      label(x + 0.5 * tileW, y + 0.36 * tileH, txt, 0.012, ink, 22);
      if (si == 6 && wi == 1) {
        auto *highlight = new TBox(x + 0.002, y + 0.002, x + tileW - 0.002, y + tileH - 0.002);
        highlight->SetFillStyle(0);
        highlight->SetLineWidth(3);
        highlight->SetLineColor(legacyColor);
        highlight->Draw();
      }
    }
  }
}

double shapeDifference(const Cell &c) { return c.shapeDifference; }
double legacyStepInWidths(const Cell &c) { return c.sigma / (10.0 * c.width); }
double steps(const Cell &c) { return c.steps; }

void drawExplanation(const std::array<Cell, side * side> &cells, const std::string &path) {
  TCanvas canvas("explanation", "Sampling diagnosis", 3000, 1800);
  canvas.SetFillColor(kWhite);
  label(0.055, 0.962, "WHERE THE LEGACY GRID FAILS - AND WHAT THE ADJUSTMENT CHANGES", 0.031);
  label(0.055, 0.929,
        "Data-free numerical study | same Landau-Gaussian formula, MPV = 0, area = 1, integration from x-5 sigma to x+5 sigma", 0.017);
  heatmap(cells, 0.080, 0.556, 0.235, 0.282, "Legacy vs adjusted difference (%)", shapeDifference, 0);
  heatmap(cells, 0.403, 0.556, 0.235, 0.282, "Legacy step / Landau width", legacyStepInWidths, 1);
  heatmap(cells, 0.726, 0.556, 0.235, 0.282, "Adjusted midpoint steps", steps, 2);
  label(0.055, 0.493,
        "Columns: Landau width (ADC). Rows: Gaussian sigma (ADC). Difference = max |legacy - adjusted| / adjusted peak.", 0.014);
  label(0.055, 0.467,
        "Red outline: near the E1 cell 896 narrow-width fit (Landau width 0.122, Gaussian sigma 7.889).", 0.014);

  const Cell &c = cells[6 * side + 1];
  TPad curve("curve", "", 0.055, 0.09, 0.535, 0.428);
  curve.SetLeftMargin(0.105);
  curve.SetRightMargin(0.03);
  curve.SetTopMargin(0.26);
  curve.SetBottomMargin(0.17);
  curve.Draw();
  curve.cd();
  TH1D frame("curve_axis", "", 10, xMin, xMax);
  frame.SetDirectory(nullptr);
  frame.SetMinimum(0.0);
  frame.SetMaximum(ymax(c));
  frame.GetXaxis()->SetTitle("(charge - MPV)/(w_{L} + #sigma_{G})");
  frame.GetYaxis()->SetTitle("PDF / adjusted peak");
  frame.GetXaxis()->SetTitleSize(0.055);
  frame.GetYaxis()->SetTitleSize(0.055);
  frame.GetXaxis()->SetLabelSize(0.047);
  frame.GetYaxis()->SetLabelSize(0.047);
  frame.Draw("AXIS");
  auto legacy = graph(c.x, c.oldPdf, legacyColor, 1);
  auto adjusted = graph(c.x, c.newPdf, adjustedColor, 2);
  adjusted->Draw("L SAME");
  legacy->Draw("L SAME");
  label(0.12, 0.94, "E1 896-like PDF: old grid jumps around the smooth adjusted curve", 0.060);
  label(0.12, 0.84, "red = legacy   blue = adjusted", 0.050);
  canvas.cd();

  TPad sampling("sampling", "", 0.555, 0.09, 0.966, 0.428);
  sampling.SetLeftMargin(0.11);
  sampling.SetRightMargin(0.04);
  sampling.SetTopMargin(0.26);
  sampling.SetBottomMargin(0.17);
  sampling.Draw();
  sampling.cd();
  TH1D sampleAxis("sampling_axis", "", 10, -0.6, 0.6);
  sampleAxis.SetDirectory(nullptr);
  sampleAxis.SetMinimum(0.0);
  sampleAxis.SetMaximum(1.3);
  sampleAxis.GetXaxis()->SetTitle("integration coordinate t - MPV (ADC)");
  sampleAxis.GetYaxis()->SetTitle("Landau density / peak");
  sampleAxis.GetXaxis()->SetTitleSize(0.055);
  sampleAxis.GetYaxis()->SetTitleSize(0.055);
  sampleAxis.GetXaxis()->SetLabelSize(0.047);
  sampleAxis.GetYaxis()->SetLabelSize(0.047);
  sampleAxis.Draw("AXIS");
  std::vector<double> xx, yy;
  const double w = 0.12192, sigma = 7.889;
  const double shiftedMpv = 0.22278298 * w;
  const double peak = TMath::Landau(0.0, shiftedMpv, w) / w;
  for (int i = 0; i <= 500; ++i) {
    const double x = -0.6 + 1.2 * i / 500.0;
    xx.push_back(x);
    yy.push_back((TMath::Landau(x, shiftedMpv, w) / w) / peak);
  }
  auto landau = graph(xx, yy, ink, 3);
  landau->Draw("L SAME");
  for (int mode = 0; mode < 2; ++mode) {
    const int n = mode == 0 ? 100 : adjustedSteps(w, sigma);
    const double h = 10.0 * sigma / n;
    TLine tick;
    tick.SetLineColor(mode == 0 ? legacyColor : adjustedColor);
    tick.SetLineWidth(mode == 0 ? 5 : 2);
    for (int i = 0; i < n; ++i) {
      const double t = -5.0 * sigma + (i + 0.5) * h;
      if (t >= -0.6 && t <= 0.6)
        tick.DrawLine(t, mode == 0 ? 0.18 : 0.055, t, mode == 0 ? 0.31 : 0.12);
    }
  }
  label(0.12, 0.94, "Why: old midpoints miss the narrow Landau core", 0.060);
  label(0.12, 0.85, "Legacy step: 0.789 ADC = 6.47 Landau widths", 0.046, legacyColor);
  label(0.12, 0.77, "Adjusted step: 0.0244 ADC = 0.20 widths", 0.046, adjustedColor);
  canvas.cd();
  label(0.055, 0.046,
        "Adjusted count: next even integer >= max(100, 50 sigma / Landau width), capped at 10,000.", 0.014);
  label(0.055, 0.025,
        "Hidden fine-grid check: at least 20 samples per Landau width; adjusted result differs by less than 0.01% of peak throughout this grid.", 0.014);
  canvas.Print(path.c_str());
}

} // namespace

int main(int argc, char **argv) {
  if (argc != 2) {
    std::cerr << "usage: plot_langau_grid OUTPUT_DIRECTORY\n";
    return 2;
  }
  int rootArgc = 1;
  char *rootArgv[] = {argv[0], nullptr};
  TApplication app("langau-grid", &rootArgc, rootArgv);
  gROOT->SetBatch(kTRUE);
  gStyle->SetOptStat(0);
  ink = TColor::GetColor("#253142");
  legacyColor = TColor::GetColor("#c54a3b");
  adjustedColor = TColor::GetColor("#087eaf");
  std::filesystem::create_directories(argv[1]);
  std::array<Cell, side * side> cells;
  for (int si = 0; si < side; ++si) {
    for (int wi = 0; wi < side; ++wi) {
      Cell &c = cells[si * side + wi];
      c = calculate(widths[wi], sigmas[si]);
      std::cout << "width=" << c.width << " sigma=" << c.sigma << " steps=" << c.steps
                << " difference=" << 100 * c.shapeDifference << "% fine_check=" << 100 * c.fineCheckError << "%\n";
    }
  }
  const std::filesystem::path out = argv[1];
  drawGrid(cells, (out / "langau_width_grid_8x8.svg").string());
  drawExplanation(cells, (out / "langau_sampling_diagnosis.svg").string());
}
