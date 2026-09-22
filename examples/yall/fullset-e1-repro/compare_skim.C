// Read-only comparison of old and corrected DataPrep -X outputs.
// Load this checkout's libLFHCAL before loading this macro, for example:
// root -l -b -q -e 'gSystem->AddDynamicPath("/repo/NewStructure/build"); gSystem->Load("libLFHCAL")' \
//   'compare_skim.C("old.root","new.root","/fresh/report/skim")'
// Writes PREFIX.json and PREFIX.csv. ROOT exits nonzero if event selection,
// existing tile order or payload changed, or any old tile was lost. Added
// tiles are expected. This checks the skim, not the downstream calibrations.
#include "../../../NewStructure/Event.h"
#include <TFile.h>
#include <TSystem.h>
#include <TTree.h>

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace skim_comparison {
void require(bool condition, const std::string& message) {
  if (!condition) throw std::runtime_error(message);
}
bool equal(double a, double b) {
  return a == b || (std::isnan(a) && std::isnan(b));
}
std::string quoted(const std::string& value) {
  std::string result = "\"";
  for (unsigned char c : value) {
    if (c == '\\' || c == '"') result += '\\';
    if (c == '\n') result += "\\n";
    else if (c == '\r') result += "\\r";
    else if (c == '\t') result += "\\t";
    else if (c < 32) throw std::runtime_error("unsupported control character in path");
    else result += c;
  }
  return result + '"';
}
bool same_event(Event& a, Event& b) {
  return a.GetRunNumber() == b.GetRunNumber() &&
      a.GetEventID() == b.GetEventID() && a.GetROtype() == b.GetROtype() &&
      a.GetBeamID() == b.GetBeamID() && a.GetBeamName() == b.GetBeamName() &&
      *a.GetBeginRunTime() == *b.GetBeginRunTime() &&
      equal(a.GetBeamEnergy(), b.GetBeamEnergy()) &&
      equal(a.GetTimeStamp(), b.GetTimeStamp()) &&
      equal(a.GetVov(), b.GetVov()) && equal(a.GetVop(), b.GetVop()) &&
      equal(a.GetBeamPosX(), b.GetBeamPosX()) &&
      equal(a.GetBeamPosY(), b.GetBeamPosY());
}
bool same_tile(Hgcroc& a, Hgcroc& b) {
  return a.GetCellID() == b.GetCellID() &&
      a.GetROClassName() == b.GetROClassName() &&
      a.GetNsample() == b.GetNsample() &&
      a.GetADCWaveform() == b.GetADCWaveform() &&
      a.GetTOAWaveform() == b.GetTOAWaveform() &&
      a.GetTOTWaveform() == b.GetTOTWaveform() &&
      equal(a.GetCorrectedTOA(), b.GetCorrectedTOA()) &&
      equal(a.GetCorrectedTOT(), b.GetCorrectedTOT()) &&
      a.GetPedestal() == b.GetPedestal() &&
      equal(a.GetIntegratedADC(), b.GetIntegratedADC()) &&
      equal(a.GetIntegratedTOT(), b.GetIntegratedTOT()) &&
      equal(a.GetIntegratedValue(), b.GetIntegratedValue()) &&
      equal(a.GetE(), b.GetE()) && equal(a.GetTOA(), b.GetTOA()) &&
      equal(a.GetLocalTriggerPrimitive(), b.GetLocalTriggerPrimitive()) &&
      a.GetLocalTriggerBit() == b.GetLocalTriggerBit();
}
struct Counts {
  Long64_t old_tiles = 0, new_tiles = 0, added = 0, missing = 0, changed = 0;
};
struct Reader {
  TFile file;
  TTree* data = nullptr;
  Event event{};
  Event* pointer = &event;
  explicit Reader(const char* path) : file(path, "READ") {
    require(!file.IsZombie(), std::string("cannot open ") + path);
    file.GetObject("Data", data);
    require(data != nullptr, std::string("missing Data tree: ") + path);
    require(data->SetBranchAddress("event", &pointer) >= 0,
            std::string("cannot read event branch: ") + path);
  }
  void read(Long64_t entry) {
    event.ClearTiles();
    require(data->GetEntry(entry) > 0, "cannot read entry " + std::to_string(entry));
  }
  ~Reader() {
    if (data) data->ResetBranchAddresses();
    event.ClearTiles();
  }
};

int run(const char* old_path, const char* new_path, const char* prefix) {
  const std::string json_path = std::string(prefix) + ".json";
  const std::string csv_path = std::string(prefix) + ".csv";
  require(gSystem->AccessPathName(json_path.c_str()) &&
              gSystem->AccessPathName(csv_path.c_str()),
          "refusing to overwrite an existing report; choose a fresh prefix");
  Reader old_file(old_path), new_file(new_path);
  const Long64_t old_entries = old_file.data->GetEntries();
  const Long64_t new_entries = new_file.data->GetEntries();
  std::map<int, Counts> counts;
  Long64_t identity_changes = 0, metadata_changes = 0, order_changes = 0;
  Long64_t changed_events = 0, added_total = 0, missing_total = 0, payload_changes = 0;
  Long64_t old_total = 0, new_total = 0;
  std::vector<std::string> examples;
  const auto example = [&](Long64_t entry, const std::string& message) {
    if (examples.size() < 20)
      examples.push_back("entry " + std::to_string(entry) + ": " + message);
  };
  for (Long64_t entry = 0; entry < std::max(old_entries, new_entries); ++entry) {
    const bool have_old = entry < old_entries, have_new = entry < new_entries;
    if (have_old) old_file.read(entry);
    if (have_new) new_file.read(entry);
    Event& old_event = old_file.event;
    Event& new_event = new_file.event;
    std::map<int, std::pair<Hgcroc*, int>> old_tiles, new_tiles;
    for (int side = 0; side < 2; ++side) {
      if (!(side == 0 ? have_old : have_new)) continue;
      Event& event = side == 0 ? old_event : new_event;
      auto& tiles = side == 0 ? old_tiles : new_tiles;
      for (int position = 0; position < event.GetNTiles(); ++position) {
        auto* tile = dynamic_cast<Hgcroc*>(event.GetTile(position));
        require(tile != nullptr, "non-Hgcroc tile at entry " + std::to_string(entry));
        const int id = tile->GetCellID();
        require(tiles.emplace(id, std::make_pair(tile, position)).second,
                "duplicate cell ID at entry " + std::to_string(entry));
        if (side == 0) { ++counts[id].old_tiles; ++old_total; }
        else { ++counts[id].new_tiles; ++new_total; }
      }
    }
    if (!have_old || !have_new) continue;
    if (old_event.GetRunNumber() != new_event.GetRunNumber() ||
        old_event.GetEventID() != new_event.GetEventID()) {
      ++identity_changes;
      example(entry, "run/event identity differs; tile comparison skipped");
      continue;
    }
    if (!same_event(old_event, new_event)) {
      ++metadata_changes;
      example(entry, "event metadata differs");
    }
    bool added_in_event = false, reordered = false;
    int previous_new_position = -1;
    // Preserve the original tile sequence; map key order is not tile order.
    for (int position = 0; position < old_event.GetNTiles(); ++position) {
      auto* old_tile = static_cast<Hgcroc*>(old_event.GetTile(position));
      const int id = old_tile->GetCellID();
      const auto found = new_tiles.find(id);
      if (found == new_tiles.end()) {
        ++counts[id].missing; ++missing_total;
        example(entry, "old cell " + std::to_string(id) + " missing");
        continue;
      }
      if (found->second.second <= previous_new_position) reordered = true;
      previous_new_position = found->second.second;
      if (!same_tile(*old_tile, *found->second.first)) {
        ++counts[id].changed; ++payload_changes;
        example(entry, "cell " + std::to_string(id) + " payload differs");
      }
    }
    if (reordered) { ++order_changes; example(entry, "retained tile order differs"); }
    for (const auto& item : new_tiles) {
      if (old_tiles.count(item.first)) continue;
      ++counts[item.first].added; ++added_total; added_in_event = true;
    }
    if (added_in_event) ++changed_events;
    if (entry % 50000 == 0) std::cout << "Compared " << entry << " / " << old_entries << '\n';
  }
  const bool passed = old_entries == new_entries && identity_changes == 0 &&
      metadata_changes == 0 && order_changes == 0 && missing_total == 0 && payload_changes == 0;
  std::ofstream csv(csv_path);
  require(bool(csv), "cannot write " + csv_path);
  csv << "cell_id,old_tiles,new_tiles,added_tiles,missing_old_tiles,changed_old_payloads\n";
  for (const auto& item : counts) {
    const Counts& c = item.second;
    csv << item.first << ',' << c.old_tiles << ',' << c.new_tiles << ',' << c.added
        << ',' << c.missing << ',' << c.changed << '\n';
  }
  csv.close();
  require(bool(csv), "write failed: " + csv_path);
  std::ofstream json(json_path);
  require(bool(json), "cannot write " + json_path);
  json << "{\n  \"passed\": " << (passed ? "true" : "false")
       << ",\n  \"old_file\": " << quoted(old_path)
       << ",\n  \"new_file\": " << quoted(new_path)
       << ",\n  \"old_events\": " << old_entries << ",\n  \"new_events\": " << new_entries
       << ",\n  \"old_tiles\": " << old_total << ",\n  \"new_tiles\": " << new_total
       << ",\n  \"event_identity_mismatches\": " << identity_changes
       << ",\n  \"event_metadata_mismatches\": " << metadata_changes
       << ",\n  \"retained_tile_order_mismatches\": " << order_changes
       << ",\n  \"events_with_added_tiles\": " << changed_events
       << ",\n  \"added_tiles\": " << added_total
       << ",\n  \"missing_old_tiles\": " << missing_total
       << ",\n  \"changed_old_payloads\": " << payload_changes
       << ",\n  \"notes\": \"Tile differences use matching run/event IDs at the same entry. "
          "Mismatched entries are excluded from added/missing/payload counts. "
          "Floating values compare exactly, with two NaNs treated as unchanged. "
          "This does not verify added tiles against the pre-skim input.\""
       << ",\n  \"first_mismatches\": [";
  for (std::size_t i = 0; i < examples.size(); ++i) {
    if (i) json << ", ";
    json << quoted(examples[i]);
  }
  json << "]\n}\n";
  json.close();
  require(bool(json), "write failed: " + json_path);
  std::cout << (passed ? "PASS" : "FAIL") << ": events " << old_entries << " -> "
            << new_entries << ", tiles " << old_total << " -> " << new_total
            << ", added " << added_total << ", lost " << missing_total
            << ", changed payloads " << payload_changes << '\n'
            << "Reports: " << json_path << " and " << csv_path << '\n';
  return passed ? 0 : 1;
}
}  // namespace skim_comparison

void compare_skim(const char* old_path, const char* new_path, const char* prefix) {
  int status = 2;
  try { status = skim_comparison::run(old_path, new_path, prefix); }
  catch (const std::exception& error) {
    std::cerr << "Skim comparison: " << error.what() << '\n';
  }
  gSystem->Exit(status);
}
