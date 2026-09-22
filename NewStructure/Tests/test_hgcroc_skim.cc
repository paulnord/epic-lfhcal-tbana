// CTest runs this fixture writer, the real DataPrep -X command, and the
// verifier in separate processes. No beam data or raw decoder is required.
#include "Calib.h"
#include "Event.h"
#include "HGCROC.h"
#include "RootSetupWrapper.h"
#include "Setup.h"

#include <TFile.h>
#include <TTree.h>

#include <array>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void require(bool condition, const std::string& message) {
  if (!condition) throw std::runtime_error(message);
}

// Interleaving rejected events checks that an earlier event's trigger is not
// reused. TOA and local bit each trigger independently at all tile positions.
struct Fixture {
  int id;
  int trigger_position;
  int trigger_kind;  // 0: none; 1: positive raw TOA; 2: local trigger bit == 1
  int tiles;
};
const std::array<Fixture, 13> fixtures{{
    {100, -1, 0, 3}, {101, 0, 1, 3}, {102, -1, 0, 0},
    {103, 1, 1, 3}, {104, -1, 0, 3}, {105, 2, 1, 3},
    {106, 0, 2, 3}, {107, -1, 0, 3}, {108, 1, 2, 3},
    {109, 2, 2, 3}, {110, -1, 0, 3}, {111, 0, 1, 1},
    {112, 0, 2, 1}}};
const std::array<int, 3> cell_ids{{2, 0, 1}};  // Deliberately not map order.
const TTimeStamp begin_run(2026, 9, 22, 12, 34, 56, 0, true);

void fill_event(Event& event, const Fixture& fixture) {
  event.ClearTiles();
  event.SetRunNumber(731);
  event.SetEventID(fixture.id);
  event.SetROtype(ReadOut::Type::Hgcroc);
  event.SetBeamEnergy(120.);
  event.SetBeamID(13);
  event.SetBeamName("synthetic-muon");
  event.SetBeginRunTime(begin_run);
  event.SetTimeStamp(fixture.id + 0.25);
  event.SetVov(3.5);
  event.SetVop(44.);
  event.SetBeamPosX(-1.25);
  event.SetBeamPosY(2.5);
  for (int position = 0; position < fixture.tiles; ++position) {
    auto* tile = new Hgcroc();
    const int value = fixture.id + position;
    tile->SetCellID(cell_ids[position]);
    tile->SetNsample(3);
    tile->SetADCWaveform({value, value + 3, value + 1});
    tile->SetTOAWaveform({-7, 0, -1});
    tile->SetTOTWaveform({0, value + 5, 0});
    // Nonzero energy, trigger primitive, TOT, and Tile::TOA are not the
    // event-selection criteria. Neither bit 2 nor bit 255 is bit 1.
    tile->SetE(value + 0.125);
    tile->SetTOA(value + 0.5);
    tile->SetLocalTriggerPrimitive(value + 0.75);
    tile->SetLocalTriggerBit(position % 2 == 0 ? 2 : 255);
    if (position == fixture.trigger_position) {
      if (fixture.trigger_kind == 1)
        tile->SetTOAWaveform({0, 1, 0});  // Exercise the > 0 boundary.
      if (fixture.trigger_kind == 2) tile->SetLocalTriggerBit(1);
    }
    tile->SetCorrectedTOA(4);
    tile->SetCorrectedTOT(value + 7);
    tile->SetPedestal(17 + position);
    tile->SetIntegratedADC(value + 0.25);
    tile->SetIntegratedTOT(value + 0.5);
    tile->SetIntegratedValue(value + 0.75);
    event.AddTile(tile);
  }
}

void check_event(Event& actual, const Fixture& fixture) {
  Event expected{};
  fill_event(expected, fixture);
  const std::string context = "event " + std::to_string(fixture.id) + ": ";
  require(actual.GetEventID() == fixture.id, context + "event order changed");
  require(actual.GetNTiles() == expected.GetNTiles(),
          context + "tile count changed: expected " +
              std::to_string(expected.GetNTiles()) + ", got " +
              std::to_string(actual.GetNTiles()));
  require(actual.GetRunNumber() == expected.GetRunNumber() &&
              actual.GetROtype() == expected.GetROtype() &&
              actual.GetBeamEnergy() == expected.GetBeamEnergy() &&
              actual.GetBeamID() == expected.GetBeamID() &&
              actual.GetBeamName() == expected.GetBeamName() &&
              *actual.GetBeginRunTime() == *expected.GetBeginRunTime() &&
              actual.GetTimeStamp() == expected.GetTimeStamp() &&
              actual.GetVov() == expected.GetVov() &&
              actual.GetVop() == expected.GetVop() &&
              actual.GetBeamPosX() == expected.GetBeamPosX() &&
              actual.GetBeamPosY() == expected.GetBeamPosY(),
          context + "event metadata changed");
  for (int position = 0; position < expected.GetNTiles(); ++position) {
    auto* a = dynamic_cast<Hgcroc*>(actual.GetTile(position));
    auto* e = dynamic_cast<Hgcroc*>(expected.GetTile(position));
    require(a != nullptr, context + "tile has wrong dynamic type");
    require(a->GetCellID() == e->GetCellID() &&
                actual.GetTileFromID(e->GetCellID()) == a,
            context + "tile identity/order changed");
    require(a->GetROClassName() == e->GetROClassName() &&
                a->GetNsample() == e->GetNsample() &&
                a->GetADCWaveform() == e->GetADCWaveform() &&
                a->GetTOAWaveform() == e->GetTOAWaveform() &&
                a->GetTOTWaveform() == e->GetTOTWaveform() &&
                a->GetRawTOA() == e->GetRawTOA() &&
                a->GetRawTOT() == e->GetRawTOT() &&
                a->GetCorrectedTOA() == e->GetCorrectedTOA() &&
                a->GetCorrectedTOT() == e->GetCorrectedTOT() &&
                a->GetPedestal() == e->GetPedestal() &&
                a->GetIntegratedADC() == e->GetIntegratedADC() &&
                a->GetIntegratedTOT() == e->GetIntegratedTOT() &&
                a->GetIntegratedValue() == e->GetIntegratedValue() &&
                a->GetE() == e->GetE() && a->GetTOA() == e->GetTOA() &&
                a->GetLocalTriggerPrimitive() == e->GetLocalTriggerPrimitive() &&
                a->GetLocalTriggerBit() == e->GetLocalTriggerBit(),
            context + "tile " + std::to_string(position) + " data changed");
  }
  expected.ClearTiles();
}

void write(const std::string& path) {
  const std::string mapping_path = path + ".mapping";
  {
    std::ofstream mapping(mapping_path);
    require(bool(mapping), "cannot create fixture mapping");
    mapping << "sumOpt 2\n";
    for (int cell = 0; cell < 3; ++cell)
      mapping << "0 " << cell << ' ' << cell
              << " F001 1 0 0 0 0 0 1\n";
  }
  Setup* setup = Setup::GetInstance();
  const bool initialized = setup->Initialize(mapping_path.c_str(), 0);
  std::filesystem::remove(mapping_path);
  require(initialized, "cannot initialize fixture mapping");
  TFile file(path.c_str(), "RECREATE");
  require(!file.IsZombie(), "cannot create skim input");
  {
    RootSetupWrapper wrapper(setup);
    TTree setup_tree("Setup", "Setup");
    setup_tree.Branch("setup", &wrapper);
    require(setup_tree.Fill() > 0 && setup_tree.Write() > 0,
            "cannot write fixture setup");
    Calib calibration;
    calibration.SetRunNumber(731);
    calibration.SetRunNumberPed(730);
    calibration.SetRunNumberMip(731);
    calibration.SetBeginRunTime(begin_run);
    calibration.SetBeginRunTimePed(begin_run);
    calibration.SetBeginRunTimeMip(begin_run);
    calibration.SetVov(3.5);
    calibration.SetVop(44.);
    calibration.SetBCCalib(true);
    for (int cell : cell_ids) {
      TileCalib* tile_calibration = calibration.GetTileCalib(cell);
      tile_calibration->ScaleH = 20. + cell;
      tile_calibration->ScaleWidthH = 8. + cell;
      tile_calibration->PedestalMeanH = 17. + cell;
      tile_calibration->BadChannel = 3;
    }
    TTree calibration_tree("Calib", "Calib");
    calibration_tree.Branch("calib", &calibration);
    require(calibration_tree.Fill() > 0 && calibration_tree.Write() > 0,
            "cannot write fixture calibration");
    Event event{};
    TTree data_tree("Data", "Data");
    data_tree.Branch("event", &event);
    for (const auto& fixture : fixtures) {
      fill_event(event, fixture);
      require(data_tree.Fill() > 0, "cannot write fixture event");
    }
    require(data_tree.Write() > 0, "cannot write fixture data tree");
    event.ClearTiles();
  }
  file.Close();
  require(!file.TestBit(TFile::kWriteError), "ROOT reported a fixture write error");
  std::cout << "Wrote 13 events: eight triggered, four noise, one empty\n";
}

TTree* tree(TFile& file, const char* name) {
  TTree* result = nullptr;
  file.GetObject(name, result);
  require(result != nullptr, std::string("missing ") + name + " tree");
  return result;
}

void check_file(const std::string& path, bool skimmed) {
  TFile file(path.c_str(), "READ");
  require(!file.IsZombie(), "cannot read " + path);
  TTree* setup_tree = tree(file, "Setup");
  require(setup_tree->GetEntries() == 1, "setup entry count changed");
  RootSetupWrapper wrapper;
  RootSetupWrapper* wrapper_ptr = &wrapper;
  require(setup_tree->SetBranchAddress("setup", &wrapper_ptr) >= 0 &&
              setup_tree->GetEntry(0) > 0, "cannot read saved setup");
  Setup* setup = Setup::GetInstance();
  require(setup->Initialize(wrapper) && setup->GetNActiveCells() == 3,
          "saved setup changed");
  for (int cell : cell_ids)
    require(setup->GetCellID(0, cell) == cell &&
                setup->GetAssemblyID(cell) == "F001" &&
                setup->GetLayersInSegment(cell) == 1,
            "saved tile mapping changed");
  setup_tree->ResetBranchAddresses();
  TTree* calibration_tree = tree(file, "Calib");
  require(calibration_tree->GetEntries() == 1, "calibration entry count changed");
  Calib calibration;
  Calib* calibration_ptr = &calibration;
  require(calibration_tree->SetBranchAddress("calib", &calibration_ptr) >= 0 &&
              calibration_tree->GetEntry(0) > 0, "cannot read saved calibration");
  require(calibration.GetRunNumber() == 731 &&
              calibration.GetRunNumberPed() == 730 &&
              calibration.GetRunNumberMip() == 731 &&
              *calibration.GetBeginRunTime() == begin_run &&
              *calibration.GetBeginRunTimePed() == begin_run &&
              *calibration.GetBeginRunTimeMip() == begin_run &&
              calibration.GetVov() == 3.5 && calibration.GetVop() == 44. &&
              calibration.GetBCCalib(), "calibration metadata changed");
  for (int cell : cell_ids)
    require(calibration.GetScaleHigh(cell) == 20. + cell &&
                calibration.GetScaleWidthHigh(cell) == 8. + cell &&
                calibration.GetPedestalMeanH(cell) == 17. + cell &&
                calibration.GetBadChannel(cell) == 3,
            "tile calibration changed");
  calibration_tree->ResetBranchAddresses();
  TTree* data_tree = tree(file, "Data");
  require(data_tree->GetEntries() == (skimmed ? 8 : 13),
          "unexpected event count in " + path);
  Event event{};
  Event* event_ptr = &event;
  require(data_tree->SetBranchAddress("event", &event_ptr) >= 0,
          "cannot read event branch");
  int entry = 0;
  for (const auto& fixture : fixtures) {
    if (skimmed && fixture.trigger_kind == 0) continue;
    event.ClearTiles();
    require(data_tree->GetEntry(entry++) > 0, "cannot read fixture event");
    check_event(event, fixture);
  }
  data_tree->ResetBranchAddresses();
  event.ClearTiles();
}
}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc == 3 && std::string(argv[1]) == "--write") {
      write(argv[2]);
    } else if (argc == 4 && std::string(argv[1]) == "--read") {
      check_file(argv[2], false);
      check_file(argv[3], true);
      std::cout << "Whole-event skim preserved all accepted tile data and order\n";
    } else {
      throw std::runtime_error("usage: test_hgcroc_skim --write INPUT | --read INPUT OUTPUT");
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "HGCROC skim regression: " << error.what() << '\n';
    return 1;
  }
}
