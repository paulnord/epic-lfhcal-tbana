// Real ROOT/libLFHCAL benchmark for PR #90. No replacement/stub plotting code.
// Usage: plot_copy_bench OUTPUT_DIR [CELLS=32] [ITERATIONS=5] [WARMUP=1]
// Build with the headers and libLFHCAL from ONE checkout; run each build in
// a separate process. The Python companion performs the before/after comparison.
// The only plotted cell is 0, but the whole dense map crosses the real wrapper
// and helper boundaries. This is a controlled copy benchmark, not a Run165 replay.

#include "MultiCanvas.h"
#include "TArrayD.h"
#include "TFile.h"
#include "TList.h"
#include "TROOT.h"
#include "TSystem.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>
#include <sys/resource.h>

namespace {
using Spectra = std::map<int, TileSpectra>;

// A streaming non-cryptographic integrity checksum, not a ROOT file checksum.
// Scalars have fixed little-endian encoding; doubles retain every IEEE bit.
// No pointer, file timestamp, directory ownership, or ROOT UUID is included.
class Digest {
  std::uint64_t state_ = UINT64_C(14695981039346656037);
 public:
  void byte(unsigned char b) {
    state_ = (state_ ^ b) * UINT64_C(1099511628211);
  }
  void integer(std::uint64_t value) {
    for (int i = 0; i < 8; ++i) { byte(value & 255); value >>= 8; }
  }
  void number(double value) {
    static_assert(sizeof(double) == 8 && std::numeric_limits<double>::is_iec559,
                  "This benchmark needs IEEE-754 64-bit doubles");
    std::uint64_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    integer(bits);
  }
  void string(const char* s) {
    const std::size_t n = std::strlen(s);
    integer(n);
    for (std::size_t i = 0; i < n; ++i) byte(static_cast<unsigned char>(s[i]));
  }
  std::string hex() const {
    std::ostringstream out;
    out << std::hex << std::setfill('0') << std::setw(16) << state_;
    return out.str();
  }
};

void arrayDigest(Digest& d, const TArrayD* a) {
  d.integer(a ? a->GetSize() : 0);
  if (a) for (int i = 0; i < a->GetSize(); ++i) d.number(a->At(i));
}

void axisDigest(Digest& d, const TAxis& a) {
  d.string(a.GetName()); d.string(a.GetTitle());
  d.integer(a.GetNbins()); d.number(a.GetXmin()); d.number(a.GetXmax());
  arrayDigest(d, a.GetXbins());
  d.integer(a.GetFirst()); d.integer(a.GetLast());
  d.integer(a.TestBit(TAxis::kAxisRange));
  d.integer(a.GetDecimals()); d.integer(a.GetCenterLabels()); d.integer(a.GetCenterTitle());
  d.integer(a.GetMoreLogLabels());
  d.integer(a.GetNdivisions()); d.integer(a.GetAxisColor());
  d.integer(a.GetLabelColor()); d.integer(a.GetLabelFont());
  d.number(a.GetLabelOffset()); d.number(a.GetLabelSize());
  d.number(a.GetTickLength()); d.number(a.GetTitleOffset());
  d.number(a.GetTitleSize()); d.integer(a.GetTitleColor()); d.integer(a.GetTitleFont());
  for (int bin = 1; bin <= a.GetNbins(); ++bin) d.string(a.GetBinLabel(bin));
}

void histogramDigest(Digest& d, TH1& h) {
  d.string(h.ClassName()); d.string(h.GetName()); d.string(h.GetTitle());
  d.integer(h.GetDimension()); d.integer(h.GetNcells());
  axisDigest(d, *h.GetXaxis()); axisDigest(d, *h.GetYaxis()); axisDigest(d, *h.GetZaxis());
  d.number(h.GetEntries()); d.number(h.GetNormFactor());
  d.number(h.GetMinimumStored()); d.number(h.GetMaximumStored());
  d.integer(h.GetBinErrorOption()); d.string(h.GetOption());
  d.integer(h.TestBit(TH1::kNoStats)); d.integer(h.TestBit(TH1::kNoTitle));
  d.integer(h.TestBit(TH1::kUserContour));
  d.integer(h.GetLineColor()); d.integer(h.GetLineStyle()); d.integer(h.GetLineWidth());
  d.integer(h.GetFillColor()); d.integer(h.GetFillStyle());
  d.integer(h.GetMarkerColor()); d.integer(h.GetMarkerStyle()); d.number(h.GetMarkerSize());
  d.number(h.GetBarOffset()); d.number(h.GetBarWidth());
  double stats[13] = {};
  h.GetStats(stats);
  for (double value : stats) d.number(value);
  // All normal bins plus every underflow/overflow corner, not just the zoomed
  // plotting range. The raw array also retains the profile sum(w*y) values.
  const auto* raw = dynamic_cast<const TArrayD*>(&h);
  if (!raw) throw std::runtime_error("Expected a double-backed ROOT histogram");
  arrayDigest(d, raw);
  arrayDigest(d, h.GetSumw2());
  for (int bin = 0; bin < h.GetNcells(); ++bin) {
    d.number(h.GetBinContent(bin)); d.number(h.GetBinError(bin));
  }
  auto* p = dynamic_cast<TProfile*>(&h);
  d.integer(p != nullptr);
  if (p) {
    d.string(p->GetErrorOption()); d.number(p->GetYmin()); d.number(p->GetYmax());
    arrayDigest(d, p->GetBinSumw2());
    for (int bin = 0; bin < p->GetNcells(); ++bin) d.number(p->GetBinEntries(bin));
  }
  // This fixture contains no fitted functions; catches unexpected additions
  // such as a stats or palette object to the caller's histogram.
  d.integer(h.GetListOfFunctions()->GetSize());
}

std::vector<TH1*> histograms(TileSpectra& s) {
  // All ten histograms/profiles initialized by the real Hgcroc ext=3 ctor.
  return {s.GetHG(), s.GetTOT(), s.GetTOA(), s.GetWave1D(), s.GetCorr(),
          s.GetCorrTOAADC(), s.GetCorrADCTOA(), s.GetCorrTOASample(),
          s.GetTOAADC(), s.GetADCTOA()};
}

std::string fixtureDigest(Spectra& spectra, const std::string& manifestPath,
                          TFile* saved = nullptr) {
  std::ofstream manifest(manifestPath);
  if (!manifest) throw std::runtime_error("Cannot write " + manifestPath);
  Digest all;
  all.string("plot-copy-fixture-v1-fnv1a64"); all.integer(spectra.size());
  for (auto& item : spectra) {
    all.integer(item.first);
    const auto objects = histograms(item.second);
    all.integer(objects.size());
    for (TH1* original : objects) {
      std::unique_ptr<TH1> restored;
      TH1* h = original;
      if (saved) {
        auto* obj = saved->Get(original->GetName());
        h = dynamic_cast<TH1*>(obj);
        if (!h) throw std::runtime_error(std::string("Missing saved histogram: ") + original->GetName());
        h->SetDirectory(nullptr);
        restored.reset(h); // Do not accumulate a second full map in memory.
      }
      Digest one;
      histogramDigest(one, *h); histogramDigest(all, *h);
      manifest << item.first << '\t' << h->ClassName() << '\t' << h->GetName()
               << '\t' << h->GetNcells() << '\t' << one.hex() << '\n';
    }
  }
  manifest << "TOTAL\t" << all.hex() << '\n';
  if (!manifest) throw std::runtime_error("Cannot finish " + manifestPath);
  return all.hex();
}

void saveHistograms(Spectra& spectra, const std::string& path) {
  TFile out(path.c_str(), "RECREATE");
  if (out.IsZombie()) throw std::runtime_error("Cannot create " + path);
  for (auto& item : spectra) {
    // Exercise the production save path for its five normal ext=3 outputs.
    // Verify those keys instead of replacing them, so a missing/incorrect
    // production save cannot be hidden by benchmark writes. Persist only the
    // five extra initialized correlations ourselves.
    item.second.WriteExt(false);
    const auto objects = histograms(item.second);
    for (std::size_t i = 0; i < objects.size(); ++i) {
      TH1* h = objects[i];
      if (i < 5) {
        if (!out.GetKey(h->GetName()))
          throw std::runtime_error(std::string("Production WriteExt omitted: ") + h->GetName());
        continue;
      }
      if (h->Write(h->GetName(), TObject::kOverwrite) <= 0)
        throw std::runtime_error(std::string("ROOT Write failed: ") + h->GetName());
    }
  }
  out.Close();
  if (out.TestBit(TFile::kWriteError)) throw std::runtime_error("ROOT write error: " + path);
}

std::string savedDigest(Spectra& spectra, const std::string& path,
                        const std::string& manifest) {
  TFile in(path.c_str(), "READ");
  if (in.IsZombie()) throw std::runtime_error("Cannot reopen " + path);
  return fixtureDigest(spectra, manifest, &in);
}

long long peakRssKiB() {
  struct rusage usage {};
  if (getrusage(RUSAGE_SELF, &usage)) throw std::runtime_error("getrusage failed");
#if defined(__APPLE__)
  return static_cast<long long>(usage.ru_maxrss) / 1024;
#else
  return static_cast<long long>(usage.ru_maxrss);
#endif
}

int parseCount(const char* arg, bool zeroAllowed = false) {
  std::size_t used = 0;
  long long value = std::stoll(arg, &used);
  if (used != std::strlen(arg) || value < (zeroAllowed ? 0 : 1) || value > 1000000)
    throw std::runtime_error("Counts must be positive integers (warmup may be zero)");
  return static_cast<int>(value);
}

void fillFixture(TileSpectra& s, int ordinal) {
  for (TH1* h : histograms(s)) {
    h->SetDirectory(nullptr);
    h->SetStats(false);
    if (auto* p = dynamic_cast<TProfile*>(h)) {
      p->Sumw2(); // Keep the per-bin squared weights for weighted profile errors.
      for (int bin = 0; bin < p->GetNcells(); ++bin) {
        const double x = p->GetXaxis()->GetBinCenter(bin);
        const double y = 80 + ((bin * 13 + ordinal * 7) % 420);
        p->Fill(x, y - 3, 1.0); p->Fill(x, y + 3, 2.0);
      }
    } else {
      // Every allocated bin is written, including flow bins and outside the
      // plotted window, so copy cost cannot be hidden by untouched zero pages.
      for (int bin = 0; bin < h->GetNcells(); ++bin)
        h->SetBinContent(bin, 1 + ((bin * 17ULL + ordinal * 7ULL) % 29));
      h->ResetStats();
    }
  }
  TH2D* wave = s.GetCorr();
  TProfile* profile = s.GetWave1D();
  if (wave->GetNbinsX() != 550 || wave->GetNbinsY() != 1034)
    throw std::runtime_error("Unexpected production waveform binning");
  profile->Reset();
  for (int bx = 0; bx <= wave->GetNbinsX() + 1; ++bx) {
    const int t = bx - 50;
    const int distance = std::abs(t - (100 + ordinal % 13));
    const int mean = 80 + std::max(0, 560 - 5 * distance);
    for (int by = 0; by <= wave->GetNbinsY() + 1; ++by) {
      const int adc = by - 10;
      const int ridge = std::max(0, 90 - 3 * std::abs(adc - mean));
      const int background = ((bx * 7 + by * 13 + ordinal) % 43 == 0) ? 1 : 0;
      wave->SetBinContent(bx, by, ridge + background);
    }
    const double x = profile->GetXaxis()->GetBinCenter(bx);
    profile->Fill(x, mean - 4, 1.0); profile->Fill(x, mean + 2, 2.0);
  }
  // Explicit sentinels ensure all-flow-bin preservation is exercised.
  wave->SetBinContent(0, 0, 17 + ordinal);
  wave->SetBinContent(551, 1035, 31 + ordinal);
  wave->ResetStats();
}
} // namespace

int main(int argc, char** argv) {
  try {
    if (argc < 2 || argc > 5 || std::string(argv[1]) == "--help") {
      std::cout << "Usage: " << argv[0] << " OUTPUT_DIR [CELLS=32] [ITERATIONS=5] [WARMUP=1]\n";
      return argc == 2 ? 0 : 2;
    }
    const std::string out = argv[1];
    const int cells = argc > 2 ? parseCount(argv[2]) : 32;
    const int iterations = argc > 3 ? parseCount(argv[3]) : 5;
    const int warmup = argc > 4 ? parseCount(argv[4], true) : 1;
    gROOT->SetBatch(kTRUE);
    TH1::AddDirectory(kFALSE);
    TH1::SetDefaultSumw2(kFALSE);
    gStyle->SetOptStat(0); gStyle->SetOptFit(0); gStyle->SetPalette(kViridis);
    gStyle->SetNumberContours(64);
    gSystem->mkdir(out.c_str(), kTRUE);
    const std::string setupFile = out + "/fixture_mapping.txt";
    {
      std::ofstream mapping(setupFile);
      if (!mapping) throw std::runtime_error("Cannot write fixture mapping");
      // Actual Setup::Initialize format: ROunit ROchannel layer assembly
      // ROlayer row column module moduleX moduleY segmentSize (11 fields).
      for (int i = 0; i < cells; ++i) {
        const int layer = i % 64, column = (i / 64) % 4;
        const int row = (i / 256) % 2, module = i / 512;
        mapping << i / 72 << '\t' << i % 72 << '\t' << layer << "\tbench\t0\t"
                << row << '\t' << column << '\t' << module << "\t0\t0\t1\n";
      }
    }
    Setup* setup = Setup::GetInstance();
    if (!setup->Initialize(setupFile.c_str(), 0) || !setup->ContainedInSetup(0))
      throw std::runtime_error("Fixture Setup initialization failed");
    Calib calib;
    Spectra spectra;
    for (int i = 0; i < cells; ++i) {
      const int id = setup->GetCellID(i / 72, i % 72);
      if (id < 0) throw std::runtime_error("Fixture mapping lookup failed");
      TileCalib* c = calib.GetTileCalib(id);
      c->BadChannel = 3;
      auto inserted = spectra.emplace(std::piecewise_construct, std::forward_as_tuple(id),
        std::forward_as_tuple(TString("CopyBench"), 3, id, c, ReadOut::Type::Hgcroc, 1, 0));
      if (!inserted.second) throw std::runtime_error("Duplicate fixture cell");
      fillFixture(inserted.first->second, i);
    }
    MultiCanvas canvas(DetConf::Type::SingleTile, "CopyBench");
    canvas.SetCellVector({0});
    if (!canvas.Initialize(2)) throw std::runtime_error("Canvas initialization failed");
    RunInfo run;
    run.runNr = 0; run.species = "Electron"; run.pdg = 11; run.energy = 10;
    run.vop = 3; run.vbr = 0; run.year = 2026; run.month = 1;
    run.detector = "LFHCal"; run.readout = "HGCROC"; run.facility = "synthetic";
    run.beamline = "fixture"; run.samples = 20;

    const long long fixturePeak = peakRssKiB();
    const std::string before = fixtureDigest(spectra, out + "/before.digest.txt");
    auto plot = [&](const char* name) {
      const std::string prefix = out + "/" + name;
      canvas.PlotCorr2DLayer(spectra, 1, -25, 300, -10, 800,
                            prefix.c_str(), "png", run, &calib, 0, -1, 0, 0, true);
    };
    for (int i = 0; i < warmup; ++i) plot("warmup");
    const long long warmupPeak = peakRssKiB();
    const auto start = std::chrono::steady_clock::now();
    for (int i = 0; i < iterations; ++i) plot("plot");
    const auto end = std::chrono::steady_clock::now();
    const long long plotPeak = peakRssKiB();
    const double seconds = std::chrono::duration<double>(end - start).count();

    // Validation and final save/readback are outside timing and after sampling
    // peak RSS. ru_maxrss is a process-lifetime high-water mark, not a delta.
    const std::string after = fixtureDigest(spectra, out + "/after.digest.txt");
    saveHistograms(spectra, out + "/after.root");
    const std::string savedAfter = savedDigest(spectra, out + "/after.root", out + "/saved_after.digest.txt");
    const bool unchanged = before == after;
    const bool savedUnchanged = before == savedAfter && after == savedAfter;
    const std::string plotFile = "plot_CellID00000.png";
    std::ifstream png(out + "/" + plotFile, std::ios::binary);
    const unsigned char expected[] = {137, 80, 78, 71, 13, 10, 26, 10};
    unsigned char signature[8] = {};
    png.read(reinterpret_cast<char*>(signature), 8);
    const bool plotExists = png.gcount() == 8 && std::memcmp(signature, expected, 8) == 0;

    std::ofstream result(out + "/result.json");
    if (!result) throw std::runtime_error("Cannot write result.json");
    result << std::setprecision(17)
      << "{\n  \"schema\": 1,\n  \"root_version\": \"" << gROOT->GetVersion() << "\",\n"
      << "  \"synthetic_fixture\": true,\n  \"histograms_per_cell\": 10,\n"
      << "  \"selected_cells\": [0],\n  \"waveform_bins\": [550, 1034],\n"
      << "  \"timing_includes\": \"wrapper, helper, rendering and PNG output\",\n"
      << "  \"cells\": " << cells << ",\n  \"iterations\": " << iterations
      << ",\n  \"warmup\": " << warmup << ",\n  \"elapsed_seconds\": " << seconds
      << ",\n  \"peak_rss_kib\": " << plotPeak
      << ",\n  \"fixture_peak_rss_kib\": " << fixturePeak
      << ",\n  \"warmup_peak_rss_kib\": " << warmupPeak
      << ",\n  \"digest_algorithm\": \"fnv1a64-canonical-ieee754-v1\",\n"
      << "  \"before_digest\": \"" << before << "\",\n  \"after_digest\": \"" << after
      << "\",\n  \"saved_digest\": \"" << savedAfter << "\",\n"
      << "  \"caller_unchanged\": " << (unchanged ? "true" : "false")
      << ",\n  \"saved_unchanged\": " << (savedUnchanged ? "true" : "false")
      << ",\n  \"round_trip_unchanged\": " << (savedUnchanged ? "true" : "false")
      << ",\n  \"plot_exists\": " << (plotExists ? "true" : "false")
      << ",\n  \"plot_file\": \"" << plotFile << "\",\n  \"saved_file\": \"after.root\"\n}\n";
    result.close();
    if (!result) throw std::runtime_error("Cannot finish result.json");
    std::cout << "elapsed_seconds=" << seconds << " peak_rss_kib=" << plotPeak
              << " caller_unchanged=" << unchanged << " saved_unchanged=" << savedUnchanged << '\n';
    return unchanged && savedUnchanged && plotExists ? 0 : 3;
  } catch (const std::exception& e) {
    std::cerr << "plot_copy_bench: " << e.what() << '\n';
    return 2;
  }
}
