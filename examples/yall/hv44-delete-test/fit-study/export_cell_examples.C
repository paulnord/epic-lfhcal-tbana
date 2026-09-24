// ROOT-only, read-only extraction of per-cell statistics and representative TH1s.
// env CELL_SAMPLE_INPUT=Hists.root CELL_SAMPLE_CALIB=calib.txt \
//     CELL_SAMPLE_OUT=/new/directory root -l -b -q export_cell_examples.C
#include "TDirectory.h"
#include "TFile.h"
#include "TH1.h"
#include "TNamed.h"
#include "TROOT.h"
#include "TSystem.h"
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <vector>

namespace cell_examples {
void require(bool ok, const std::string &message) {
  if (!ok) throw std::runtime_error(message);
}
struct Cell {
  int id, layer, row, column, module, bc;
  TH1 *hist = nullptr; // owned by the input file, which remains open
  std::string reason;
};
std::string env(const char *name) {
  const char *value = std::getenv(name);
  require(value && *value, std::string("set ")+name);
  return value;
}
void write_text(const std::string &path, const std::string &text) {
  std::ofstream output(path);
  require(bool(output), "cannot create "+path);
  output << text;
  output.close();
  require(bool(output), "failed writing "+path);
}
void mark(Cell &cell, const std::string &why) {
  if (!cell.reason.empty()) cell.reason += ';';
  cell.reason += why;
}
void run(const std::string &input_path, const std::string &calib_path,
         const std::string &outdir) {
  std::ifstream calib(calib_path);
  require(bool(calib), "cannot read "+calib_path);
  const std::string calibration((std::istreambuf_iterator<char>(calib)), {});
  std::istringstream lines(calibration);
  std::map<int, Cell> cells;
  std::string line;
  int lineno = 0;
  while (std::getline(lines, line)) {
    ++lineno;
    std::istringstream row(line);
    int id;
    if (!(row >> id)) continue; // comments and run-header lines
    std::vector<double> fields;
    double value;
    while (row >> value) fields.push_back(value);
    require(fields.size() == 17 && row.eof(), "invalid calibration row "+std::to_string(lineno));
    for (int index : {0,1,2,3,16})
      require(std::isfinite(fields[index]) && fields[index] == std::floor(fields[index]) &&
              fields[index] >= -64 && fields[index] <= 1000000,
              "invalid calibration integer at row "+std::to_string(lineno));
    Cell cell{id, int(fields[0]), int(fields[1]), int(fields[2]), int(fields[3]), int(fields[16])};
    require(cells.emplace(id, cell).second, "duplicate calibration cell "+std::to_string(id));
  }
  require(!cells.empty(), "no calibration rows");
  TFile input(input_path.c_str(), "READ");
  require(!input.IsZombie(), "cannot read ROOT input "+input_path);
  require(input.GetDirectory("IndividualCellsTrigg") != nullptr,
          "input must be the original Hists file with IndividualCellsTrigg, not a single-cell result");
  std::vector<Cell *> ranked;
  int present = 0, missing = 0, missing_unmasked = 0;
  for (auto &item : cells) {
    Cell &cell = item.second;
    const std::string key = "IndividualCellsTrigg/hspectramipTriggADCCellID"+std::to_string(cell.id);
    TObject *object = input.Get(key.c_str());
    if (object) {
      cell.hist = dynamic_cast<TH1 *>(object);
      require(cell.hist && cell.hist->GetDimension() == 1, "expected 1D ADC histogram at "+key);
      require(std::isfinite(cell.hist->GetEntries()) && cell.hist->GetEntries() >= 0,
              "invalid entry count at "+key);
      ++present;
      if (cell.bc >= 2) ranked.push_back(&cell);
    } else {
      ++missing;
      if (cell.bc >= 2) ++missing_unmasked;
    }
  }
  require(!ranked.empty(), "no present unmasked (BC>=2) histograms");
  std::sort(ranked.begin(), ranked.end(), [](const Cell *a, const Cell *b) {
    if (a->hist->GetEntries() != b->hist->GetEntries())
      return a->hist->GetEntries() < b->hist->GetEntries();
    return a->id < b->id;
  });
  auto at = [&](double p) -> Cell & {
    return *ranked.at(static_cast<size_t>(std::lround(p*(ranked.size()-1))));
  };
  for (const auto &choice : std::vector<std::pair<double,std::string>>{
      {0.1,"p10"},{0.5,"p50"},{0.9,"p90"},{1.,"maximum"}})
    mark(at(choice.first), choice.second);
  const auto ref = cells.find(903);
  if (ref != cells.end() && ref->second.hist) mark(ref->second, "reference903");

  // mkdir is exclusive: an existing directory, file, or symlink is refused.
  // Inputs have only been opened READ. Preserve any partial output on failure.
  const int mkdir_status = ::mkdir(outdir.c_str(), 0700);
  require(mkdir_status == 0,
          "cannot create NEW output directory "+outdir+": "+std::strerror(errno));
  std::unique_ptr<TFile> output(TFile::Open((outdir+"/examples.root").c_str(), "NEW"));
  require(output && !output->IsZombie(), "cannot create examples.root");
  std::ostringstream context;
  context << "input=" << input_path << "\ncalibration=" << calib_path
          << "\nROOT=" << gROOT->GetVersion() << "\ncompiler=" << __VERSION__
          << "\nhost=" << gSystem->HostName()
          << "\nselection=present BC>=2, including zero entries; sorted by entries then cell ID"
          << "\nrank_index=round(p*(N-1)); p10,p50,p90,maximum plus cell903 if present"
          << "\ncounts=TH1 GetEntries, including underflow/overflow; not whole-run events"
          << "\nNo refilling, rebinning, refitting, or error replacement.\n";
  output->cd();
  TNamed provenance("source_context", context.str().c_str());
  require(provenance.Write() > 0, "cannot save source context");
  for (const char *key : {"hmipTriggers", "hMipTriggXY", "hMipTriggXYZ"}) {
    if (TObject *object = input.Get(key)) {
      output->cd();
      require(object->Write(key) > 0, std::string("cannot copy ")+key);
    }
  }
  std::ostringstream csv, summary;
  csv << std::setprecision(17)
      << "cell_id,module,layer,row,column,bc,has_histogram,entries,integral,underflow,overflow,sample_reason\n";
  summary << std::setprecision(17) << context.str()
          << "calibration_cells=" << cells.size() << "\npresent_histograms=" << present
          << "\nmissing_histograms=" << missing << "\nmissing_unmasked_histograms=" << missing_unmasked
          << "\ncomparison_population=" << ranked.size() << '\n';
  for (double p : {0., .1, .5, .9, 1.})
    summary << "order_statistic_p=" << p << " entries=" << at(p).hist->GetEntries()
            << " cell_id=" << at(p).id << '\n';
  const size_t n = ranked.size();
  summary << "median_entries=" << (ranked[(n-1)/2]->hist->GetEntries()/2. + ranked[n/2]->hist->GetEntries()/2.) << '\n';
  for (const auto &item : cells) {
    const Cell &c = item.second;
    csv << c.id << ',' << c.module << ',' << c.layer << ',' << c.row << ',' << c.column
        << ',' << c.bc << ',' << int(c.hist != nullptr) << ',';
    if (c.hist) csv << c.hist->GetEntries() << ',' << c.hist->Integral() << ','
                   << c.hist->GetBinContent(0) << ',' << c.hist->GetBinContent(c.hist->GetNbinsX()+1);
    else csv << "nan,nan,nan,nan";
    csv << ',' << c.reason << '\n';
    if (!c.reason.empty()) {
      output->cd();
      require(c.hist->Write(("cell"+std::to_string(c.id)).c_str()) > 0, "cannot copy histogram");
      summary << "sample cell_id=" << c.id << " bc=" << c.bc << " entries=" << c.hist->GetEntries()
              << " reason=" << c.reason << '\n';
    }
  }
  output->Close();
  write_text(outdir+"/entries.csv", csv.str());
  write_text(outdir+"/summary.txt", summary.str());
  write_text(outdir+"/calibration.txt", calibration);
  std::cout << summary.str() << "Outputs: " << outdir << '\n';
}
} // namespace cell_examples

void export_cell_examples() {
  try {
    cell_examples::run(cell_examples::env("CELL_SAMPLE_INPUT"),
                       cell_examples::env("CELL_SAMPLE_CALIB"),
                       cell_examples::env("CELL_SAMPLE_OUT"));
  } catch (const std::exception &error) {
    std::cerr << "export_cell_examples: " << error.what() << '\n';
    gSystem->Exit(2);
  }
}
