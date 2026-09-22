// Audit DataPrep -M against the original pre-skim tree, without modifying either.
// Reuse the exact exposed event/tile payload comparison used by the -X audit.
// Reuse the read-only ROOT reader and exact event/payload comparisons.
// This macro audits the original input, not an earlier -X skim.
#include "compare_skim.C"

namespace muon_skim_comparison {
using skim_comparison::Reader;
using skim_comparison::quoted;
using skim_comparison::require;
using skim_comparison::same_event;
using skim_comparison::same_tile;

struct Counts {
  Long64_t input = 0, expected = 0, selected = 0;
  Long64_t missing = 0, unexpected = 0, changed = 0;
};

int run(const char* input_path, const char* selected_path, const char* prefix) {
  const std::string json_path = std::string(prefix) + ".json";
  const std::string csv_path = std::string(prefix) + ".csv";
  require(gSystem->AccessPathName(json_path.c_str()) &&
              gSystem->AccessPathName(csv_path.c_str()),
          "refusing to overwrite an existing report; choose a fresh prefix");
  Reader input(input_path), selected(selected_path);
  const Long64_t input_events = input.data->GetEntries();
  const Long64_t selected_events = selected.data->GetEntries();
  Long64_t input_tiles = 0, expected_tiles = 0, selected_tiles = 0;
  Long64_t input_empty = 0, expected_empty = 0, selected_empty = 0;
  Long64_t identity = 0, metadata = 0, order = 0;
  Long64_t missing = 0, unexpected = 0, changed = 0;
  std::map<int, Counts> counts;
  std::vector<std::string> examples;
  const auto example = [&](Long64_t entry, const std::string& message) {
    if (examples.size() < 20)
      examples.push_back("entry " + std::to_string(entry) + ": " + message);
  };
  for (Long64_t entry = 0; entry < std::max(input_events, selected_events); ++entry) {
    const bool have_input = entry < input_events;
    const bool have_selected = entry < selected_events;
    std::vector<Hgcroc*> expected;
    std::map<int, Hgcroc*> input_by_cell;
    std::map<int, std::pair<Hgcroc*, int>> selected_by_cell;
    if (have_input) {
      input.read(entry);
      input_empty += input.event.GetNTiles() == 0;
      for (int i = 0; i < input.event.GetNTiles(); ++i) {
        auto* tile = dynamic_cast<Hgcroc*>(input.event.GetTile(i));
        require(tile != nullptr, "non-Hgcroc input tile at entry " + std::to_string(entry));
        const int id = tile->GetCellID();
        require(input_by_cell.emplace(id, tile).second, "duplicate input cell ID");
        ++counts[id].input;
        ++input_tiles;
        if (tile->GetLocalTriggerBit() == (char)1) {
          expected.push_back(tile);
          ++counts[id].expected;
          ++expected_tiles;
        }
      }
      expected_empty += expected.empty();
    }
    if (have_selected) {
      selected.read(entry);
      selected_empty += selected.event.GetNTiles() == 0;
      for (int i = 0; i < selected.event.GetNTiles(); ++i) {
        auto* tile = dynamic_cast<Hgcroc*>(selected.event.GetTile(i));
        require(tile != nullptr, "non-Hgcroc selected tile at entry " + std::to_string(entry));
        const int id = tile->GetCellID();
        require(selected_by_cell.emplace(id, std::make_pair(tile, i)).second,
                "duplicate selected cell ID");
        ++counts[id].selected;
        ++selected_tiles;
      }
    }
    if (!have_input || !have_selected) continue;
    if (input.event.GetRunNumber() != selected.event.GetRunNumber() ||
        input.event.GetEventID() != selected.event.GetEventID()) {
      ++identity;
      example(entry, "run/event identity differs; tile comparison skipped");
      continue;
    }
    if (!same_event(input.event, selected.event)) {
      ++metadata;
      example(entry, "event metadata differs");
    }
    int previous_position = -1;
    bool reordered = false;
    for (auto* tile : expected) {
      const int id = tile->GetCellID();
      const auto found = selected_by_cell.find(id);
      if (found == selected_by_cell.end()) {
        ++counts[id].missing; ++missing;
        example(entry, "expected cell " + std::to_string(id) + " missing");
        continue;
      }
      if (found->second.second <= previous_position) reordered = true;
      previous_position = found->second.second;
      if (!same_tile(*tile, *found->second.first)) {
        ++counts[id].changed; ++changed;
        example(entry, "cell " + std::to_string(id) + " payload differs");
      }
    }
    if (reordered) { ++order; example(entry, "selected tile order differs"); }
    for (const auto& item : selected_by_cell) {
      const auto found = input_by_cell.find(item.first);
      if (found != input_by_cell.end() && found->second->GetLocalTriggerBit() == (char)1)
        continue;
      ++counts[item.first].unexpected; ++unexpected;
      example(entry, "unexpected cell " + std::to_string(item.first));
    }
    if (entry % 50000 == 0)
      std::cout << "Compared " << entry << " / " << input_events << '\n';
  }
  const bool passed = input_events == selected_events && identity == 0 &&
      metadata == 0 && order == 0 && missing == 0 && unexpected == 0 && changed == 0;
  std::ofstream csv(csv_path);
  require(bool(csv), "cannot create " + csv_path);
  csv << "cell_id,input_tiles,expected_selected_tiles,selected_tiles,missing_tiles,unexpected_tiles,changed_payloads\n";
  for (const auto& item : counts) {
    const auto& c = item.second;
    csv << item.first << ',' << c.input << ',' << c.expected << ',' << c.selected
        << ',' << c.missing << ',' << c.unexpected << ',' << c.changed << '\n';
  }
  csv.close();
  require(bool(csv), "write failed: " + csv_path);
  std::ofstream json(json_path);
  require(bool(json), "cannot create " + json_path);
  json << "{\n  \"passed\": " << (passed ? "true" : "false")
       << ",\n  \"input_file\": " << quoted(input_path)
       << ",\n  \"selected_file\": " << quoted(selected_path)
       << ",\n  \"input_events\": " << input_events
       << ",\n  \"selected_events\": " << selected_events
       << ",\n  \"input_tiles\": " << input_tiles
       << ",\n  \"expected_selected_tiles\": " << expected_tiles
       << ",\n  \"selected_tiles\": " << selected_tiles
       << ",\n  \"input_empty_events\": " << input_empty
       << ",\n  \"expected_empty_events\": " << expected_empty
       << ",\n  \"selected_empty_events\": " << selected_empty
       << ",\n  \"event_identity_mismatches\": " << identity
       << ",\n  \"event_metadata_mismatches\": " << metadata
       << ",\n  \"selected_tile_order_mismatches\": " << order
       << ",\n  \"missing_tiles\": " << missing
       << ",\n  \"unexpected_tiles\": " << unexpected
       << ",\n  \"changed_payloads\": " << changed
       << ",\n  \"notes\": \"Expected tiles are exactly input LocalTriggerBit == 1, in input order. "
          "Every input event must remain, including events with zero selected tiles. "
          "Tile mismatches are counted only for matching run/event IDs at the same entry. "
          "Floating values compare exactly, with two NaNs treated as unchanged.\""
       << ",\n  \"first_mismatches\": [";
  for (std::size_t i = 0; i < examples.size(); ++i) {
    if (i) json << ", ";
    json << quoted(examples[i]);
  }
  json << "]\n}\n";
  json.close();
  require(bool(json), "write failed: " + json_path);
  std::cout << (passed ? "PASS" : "FAIL") << ": events " << input_events << " -> "
            << selected_events << ", expected tiles " << expected_tiles
            << ", selected tiles " << selected_tiles << '\n'
            << "Reports: " << json_path << " and " << csv_path << '\n';
  return passed ? 0 : 1;
}
}  // namespace muon_skim_comparison

void compare_muon_skim(const char* input, const char* selected, const char* prefix) {
  int status = 2;
  try { status = muon_skim_comparison::run(input, selected, prefix); }
  catch (const std::exception& error) {
    std::cerr << "Muon skim comparison: " << error.what() << '\n';
  }
  gSystem->Exit(status);
}
