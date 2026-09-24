// Exercise the actual exporter against a small synthetic ROOT file. The
// deliberately different entries and integrals catch accidental rebinning or
// interpreting sum of weights as the number of selected events.
#include "export_cell_examples.C"

#include <TDirectory.h>
#include <TFile.h>
#include <TH1D.h>
#include <TH2D.h>
#include <TH3D.h>
#include <TKey.h>
#include <TNamed.h>
#include <TROOT.h>

#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void require(bool ok, const std::string &message) {
  if (!ok) throw std::runtime_error(message);
}

std::string bytes(const std::filesystem::path &path) {
  std::ifstream in(path, std::ios::binary);
  require(in.good(), "cannot read " + path.string());
  return std::string(std::istreambuf_iterator<char>(in), {});
}

bool same_number(double a, double b) {
  return a == b || (std::isnan(a) && std::isnan(b));
}

// CSV quoting is part of the output contract; do not depend on sample_reason
// using any particular punctuation to join overlapping selections.
std::vector<std::string> csv_row(const std::string &line) {
  std::vector<std::string> fields;
  std::string field;
  bool quoted = false;
  for (std::size_t i = 0; i < line.size(); ++i) {
    const char c = line[i];
    if (c == '"') {
      if (quoted && i + 1 < line.size() && line[i + 1] == '"') {
        field += '"';
        ++i;
      } else {
        quoted = !quoted;
      }
    } else if (c == ',' && !quoted) {
      fields.push_back(field);
      field.clear();
    } else if (c != '\r') {
      field += c;
    }
  }
  require(!quoted, "unterminated quoted CSV field");
  fields.push_back(field);
  return fields;
}

using Row = std::map<std::string, std::string>;
std::map<int, Row> read_csv(const std::filesystem::path &path) {
  std::ifstream in(path);
  require(in.good(), "missing entries.csv");
  std::string line;
  require(static_cast<bool>(std::getline(in, line)), "empty entries.csv");
  const auto columns = csv_row(line);
  const std::vector<std::string> expected{
      "cell_id", "module", "layer", "row", "column", "bc",
      "has_histogram", "entries", "integral", "underflow", "overflow",
      "sample_reason"};
  require(columns == expected, "entries.csv header differs from contract");
  std::map<int, Row> rows;
  while (std::getline(in, line)) {
    if (line.empty()) continue;
    const auto fields = csv_row(line);
    require(fields.size() == columns.size(), "CSV field count mismatch");
    Row row;
    for (std::size_t i = 0; i < fields.size(); ++i) row[columns[i]] = fields[i];
    require(rows.emplace(std::stoi(row.at("cell_id")), row).second,
            "duplicate cell in entries.csv");
  }
  return rows;
}

void calibration_row(std::ostream &out, int id, int bc) {
  // Geometry: layer=2, row=1, column=3, module=4. Remaining columns are
  // ordinary finite calibration values; the eighteenth field is BC.
  out << id << " 2 1 3 4 0 1 0 1 70 1 5 1 10 1 10 1 " << bc << '\n';
}

void histogram(int id, double entries, bool nonfinite_bin = false) {
  const double edges[] = {-10, -2, 0, 3, 15, 30, 100};
  const std::string name = "hspectramipTriggADCCellID" + std::to_string(id);
  TH1D h(name.c_str(), "Unmodified fixture;HG ADC;Selected events", 6, edges);
  h.Sumw2();
  for (int bin = 0; bin <= h.GetNbinsX() + 1; ++bin) {
    h.SetBinContent(bin, entries == 0 ? 0 : entries / 20 + bin);
    h.SetBinError(bin, entries == 0 ? 0 : 0.25 + bin / 10.0);
  }
  h.GetXaxis()->SetBinLabel(2, "pedestal side");
  if (nonfinite_bin) {
    h.SetBinContent(4, std::numeric_limits<double>::quiet_NaN());
    h.SetBinError(5, std::numeric_limits<double>::quiet_NaN());
  }
  h.SetEntries(entries);
  require(h.Write() > 0, "could not write histogram fixture");
}

void same_histogram(const TH1 &a, const TH1 &b, const std::string &context) {
  require(a.IsA() == b.IsA(), context + ": histogram type changed");
  require(std::string(a.GetTitle()) == b.GetTitle(), context + ": title changed");
  require(a.GetNcells() == b.GetNcells(), context + ": cell count changed");
  require(same_number(a.GetEntries(), b.GetEntries()), context + ": entries changed");
  for (int bin = 0; bin < a.GetNcells(); ++bin) {
    require(same_number(a.GetBinContent(bin), b.GetBinContent(bin)),
            context + ": bin content changed at " + std::to_string(bin));
    require(same_number(a.GetBinError(bin), b.GetBinError(bin)),
            context + ": bin error changed at " + std::to_string(bin));
  }
  const TAxis *axes_a[] = {a.GetXaxis(), a.GetYaxis(), a.GetZaxis()};
  const TAxis *axes_b[] = {b.GetXaxis(), b.GetYaxis(), b.GetZaxis()};
  for (int axis = 0; axis < a.GetDimension(); ++axis) {
    require(axes_a[axis]->GetNbins() == axes_b[axis]->GetNbins(),
            context + ": axis bin count changed");
    require(std::string(axes_a[axis]->GetTitle()) == axes_b[axis]->GetTitle(),
            context + ": axis title changed");
    for (int bin = 1; bin <= axes_a[axis]->GetNbins() + 1; ++bin) {
      require(axes_a[axis]->GetBinLowEdge(bin) == axes_b[axis]->GetBinLowEdge(bin),
              context + ": axis edge changed");
      require(std::string(axes_a[axis]->GetBinLabel(bin)) ==
                  axes_b[axis]->GetBinLabel(bin),
              context + ": axis label changed");
    }
  }
}
} // namespace

int main() {
  std::filesystem::path fixture;
  try {
    std::string pattern =
        (std::filesystem::current_path() / "export-cell-examples-test-XXXXXX").string();
    std::vector<char> writable(pattern.begin(), pattern.end());
    writable.push_back('\0');
    const char *created = mkdtemp(writable.data());
    require(created != nullptr, "mkdtemp failed");
    fixture = created;
    const auto input = fixture / "input.root";
    const auto calibration = fixture / "input-calibration.txt";
    const auto output = fixture / "exported";
    {
      std::ofstream out(calibration);
      require(out.good(), "cannot create calibration fixture");
      out << "# cell layer row column module calibration fields BC\n";
      for (int id = 101; id <= 111; ++id) calibration_row(out, id, id == 107 ? 2 : 3);
      calibration_row(out, 903, 3);
      calibration_row(out, 9000, 1); // Masked despite many entries.
      calibration_row(out, 9001, 3); // Good in calibration, missing histogram.
    }
    {
      TFile root(input.c_str(), "CREATE");
      require(!root.IsZombie(), "cannot create ROOT fixture");
      auto *individual = root.mkdir("IndividualCellsTrigg");
      require(individual != nullptr, "cannot create fixture directory");
      individual->cd();
      for (int id = 101; id <= 111; ++id)
        histogram(id, std::min(id - 101, 9) * 10, id == 111);
      histogram(903, 127);
      histogram(9000, 10000);
      root.cd();
      TH1D triggers("hmipTriggers", "Selected entries;cell;entries", 3, 0, 3);
      triggers.Fill(0.5, 7);
      triggers.Write();
      TH2D xy("hMipTriggXY", "XY;x;y", 2, 0, 2, 3, -1, 2);
      xy.Fill(0.5, 0.5, 4);
      xy.Write();
      TH3D xyz("hMipTriggXYZ", "XYZ;x;y;z", 2, 0, 2, 3, -1, 2, 2, 0, 2);
      xyz.Fill(0.5, 0.5, 1.5, 8);
      xyz.Write();
      root.Close();
    }
    const auto input_before = bytes(input);
    const auto calibration_before = bytes(calibration);
    cell_examples::run(input.string(), calibration.string(), output.string());
    require(bytes(input) == input_before, "export changed source ROOT file");
    require(bytes(calibration) == calibration_before, "export changed source calibration");
    require(bytes(output / "calibration.txt") == calibration_before,
            "copied calibration is not byte-for-byte identical");
    const auto summary = bytes(output / "summary.txt");
    require(summary.find("comparison_population=12\n") != std::string::npos,
            "summary comparison population excludes empty or includes masked/missing cells");
    require(summary.find("median_entries=55\n") != std::string::npos,
            "summary median must average the middle two counts for an even population");
    require(summary.find("missing_unmasked_histograms=1\n") != std::string::npos,
            "summary omits missing unmasked histogram count");

    const auto rows = read_csv(output / "entries.csv");
    require(rows.size() == 14, "CSV must include masked and missing calibration rows");
    const std::set<int> selected{102, 107, 111, 903};
    std::set<int> selected_csv;
    for (const auto &[id, row] : rows) {
      require(row.at("module") == "4" && row.at("layer") == "2" &&
                  row.at("row") == "1" && row.at("column") == "3",
              "calibration geometry columns were misinterpreted");
      require(std::stoi(row.at("has_histogram")) == (id == 9001 ? 0 : 1),
              "incorrect histogram-presence flag");
      if (!row.at("sample_reason").empty()) selected_csv.insert(id);
    }
    require(selected_csv == selected,
            "wrong representatives: include zero, exclude missing/masked, break ties by id");
    require(rows.at(107).at("bc") == "2", "BC2 was not preserved");
    require(std::stod(rows.at(101).at("entries")) == 0,
            "present empty histogram must have entries=0");
    require(std::stod(rows.at(9000).at("entries")) == 10000,
            "masked histogram must still have its observed count");
    for (const std::string column : {"entries", "integral", "underflow", "overflow"})
      require(std::isnan(std::stod(rows.at(9001).at(column))),
              "missing histogram must have NaN " + column + ", not zero");

    {
      TFile source(input.c_str(), "READ");
      TFile exported((output / "examples.root").c_str(), "READ");
      require(!source.IsZombie() && !exported.IsZombie(), "cannot read source or exported ROOT");
      std::set<int> selected_root;
      TIter next(exported.GetListOfKeys());
      while (auto *key = static_cast<TKey *>(next())) {
        const std::string name = key->GetName();
        if (name.rfind("cell", 0) == 0) selected_root.insert(std::stoi(name.substr(4)));
      }
      require(selected_root == selected, "ROOT examples do not match requested representatives");
      for (int id : selected) {
        const auto original_name =
            "IndividualCellsTrigg/hspectramipTriggADCCellID" + std::to_string(id);
        auto *original = dynamic_cast<TH1 *>(source.Get(original_name.c_str()));
        auto *copy = dynamic_cast<TH1 *>(exported.Get(("cell" + std::to_string(id)).c_str()));
        require(original && copy, "selected histogram missing in source or export");
        same_histogram(*original, *copy, "cell" + std::to_string(id));
        const auto &row = rows.at(id);
        require(same_number(std::stod(row.at("entries")), original->GetEntries()),
                "CSV entries changed");
        require(same_number(std::stod(row.at("integral")), original->Integral()),
                "CSV integral changed");
        require(same_number(std::stod(row.at("underflow")), original->GetBinContent(0)),
                "CSV underflow changed");
        require(same_number(std::stod(row.at("overflow")),
                            original->GetBinContent(original->GetNbinsX() + 1)),
                "CSV overflow changed");
      }
      for (const std::string name : {"hmipTriggers", "hMipTriggXY", "hMipTriggXYZ"}) {
        auto *original = dynamic_cast<TH1 *>(source.Get(name.c_str()));
        auto *copy = dynamic_cast<TH1 *>(exported.Get(name.c_str()));
        require(original && copy, "missing optional occupancy map " + name);
        same_histogram(*original, *copy, name);
      }
      require(dynamic_cast<TNamed *>(exported.Get("source_context")) != nullptr,
              "missing ROOT source context");
    }

    const auto csv_before = bytes(output / "entries.csv");
    const auto root_before = bytes(output / "examples.root");
    bool refused_existing = false;
    try {
      cell_examples::run(input.string(), calibration.string(), output.string());
    } catch (const std::runtime_error &) {
      refused_existing = true;
    }
    require(refused_existing, "exporter overwrote an existing output directory");
    require(bytes(output / "entries.csv") == csv_before &&
                bytes(output / "examples.root") == root_before,
            "existing-output refusal modified exported data");
    require(bytes(input) == input_before && bytes(calibration) == calibration_before,
            "source input changed after second export");

    // ROOT can retain the current directory/file in its global list after
    // reading the exported file.  Close that state before removing the
    // fixture; otherwise NFS may rename the open file to a .nfs* placeholder
    // and report EBUSY even though the test assertions all passed.
    gROOT->cd();
    gROOT->GetListOfFiles()->Delete();
    std::filesystem::remove_all(fixture);
    std::cout << "PASS: representative selection, missing counts, lossless histograms/maps, "
                 "source preservation, and existing-output refusal.\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "test_export_cell_examples: " << e.what() << '\n';
    if (!fixture.empty()) std::cerr << "Fixture retained at " << fixture << '\n';
    return 1;
  }
}
