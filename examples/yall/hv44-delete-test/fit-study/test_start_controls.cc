// Exercise the actual parser and production setup without minimization. A
// start-only experiment must keep the objective's interval and limits frozen.
#define main cell903_application_main
#include "fit_cell903.cc"
#undef main
#include "TH1D.h"
#include <chrono>
#include <filesystem>
#include <initializer_list>

namespace {
void expect(bool ok, const char *message) {
  if (!ok) throw std::runtime_error(message);
}
Config args(std::initializer_list<std::string> options) {
  std::vector<std::string> text{"fit_cell903", "unused.root"};
  text.insert(text.end(), options.begin(), options.end());
  std::vector<char *> argv;
  for (auto &s : text) argv.push_back(s.data());
  return parse_args(static_cast<int>(argv.size()), argv.data());
}
template<class F> void must_throw(F f) {
  bool caught=false;
  try { f(); } catch (const std::runtime_error &) { caught=true; }
  expect(caught,"expected invalid starting value to be rejected");
}
using StartMember = std::optional<double> Config::*;
const StartMember members[]{&Config::start_width, &Config::start_mp,
                            &Config::start_area, &Config::start_gsigma};
const char *options[]{"--start-width", "--start-mp", "--start-area", "--start-gsigma"};

void same_problem(const FitSetup &a, const FitSetup &b) {
  expect(a.min_x==b.min_x && a.fit_low==b.fit_low &&
         a.fit_high==b.fit_high && a.int_area==b.int_area,
         "starting-value override changed the interval or normalization");
  for (int i=0; i<4; ++i) {
    expect(a.low[i]==b.low[i],"starting-value override changed a lower bound");
    expect(a.high[i]==b.high[i],"starting-value override changed an upper bound");
  }
}

void check_variations(TH1 &h, const Config &defaults, const Seed &seed) {
  const auto baseline=production_setup(h, defaults, seed);
  Config all=defaults;
  double values[4];
  for (int i=0; i<4; ++i) {
    values[i]=baseline.low[i] + 0.37*(baseline.high[i]-baseline.low[i]);
    Config variant=defaults;
    variant.*members[i]=values[i];
    all.*members[i]=values[i];
    const auto altered=production_setup(h, variant, seed);
    same_problem(baseline, altered);
    for (int j=0; j<4; ++j)
      expect(altered.start[j]==(j==i ? values[i] : baseline.start[j]),
             "override did not change exactly its own starting value");
    for (double invalid : {baseline.low[i]-1., baseline.low[i],
                           baseline.high[i], baseline.high[i]+1.,
                           std::numeric_limits<double>::quiet_NaN(),
                           std::numeric_limits<double>::infinity()}) {
      variant.*members[i]=invalid;
      must_throw([&]{ production_setup(h, variant, seed); });
    }
  }
  const auto simultaneous=production_setup(h, all, seed);
  same_problem(baseline, simultaneous);
  for (int i=0; i<4; ++i)
    expect(simultaneous.start[i]==values[i],"simultaneous start override lost a value");
}

struct TemporaryCalibration {
  std::filesystem::path directory;
  std::filesystem::path file;
  TemporaryCalibration() {
    const auto tick=std::chrono::high_resolution_clock::now().time_since_epoch().count();
    directory=std::filesystem::temp_directory_path()/
        ("cell903-start-controls-"+std::to_string(gSystem->GetPid())+"-"+std::to_string(tick));
    expect(std::filesystem::create_directory(directory),"cannot create test directory");
    file=directory/"calibration.txt";
    std::ofstream out(file);
    // Cell-specific pedestal sigmas differ; average MIP is over eligible cells.
    out << "903 0 0 0 0 0 0.6 0 0 40 0 0 0 0 0 0 0 3\n"
        << "1152 0 0 0 0 0 1.2 0 0 60 0 0 0 0 0 0 0 3\n"
        << "999 0 0 0 0 0 9.0 0 0 900 0 0 0 0 0 0 0 0\n";
    expect(static_cast<bool>(out),"cannot write test calibration");
  }
  ~TemporaryCalibration() {
    std::error_code ignored;
    std::filesystem::remove_all(directory,ignored);
  }
};
}

int main() {
  try {
    TH1D h("start_controls_test","",1124,-100,1024);
    h.SetDirectory(nullptr);
    for (int i=0; i<92; ++i) h.Fill(70.0+(i%10));
    const Config defaults=args({});
    for (auto member : members)
      expect(!(defaults.*member),"starting-value override unexpectedly enabled by default");

    const Seed seed{"test",52.1041078842105,0.581290,190};
    const auto baseline=production_setup(h,defaults,seed);
    expect(baseline.start[0]==3.*seed.ped_sigma && baseline.start[1]==seed.avmip &&
           baseline.start[2]==92. && baseline.start[3]==seed.ped_sigma,
           "default starting values changed");
    check_variations(h,defaults,seed);

    const auto parsed=args({"--start-width","2", "--start-mp","60",
                            "--start-area","100", "--start-gsigma","4"});
    const auto configured=production_setup(h,parsed,seed);
    same_problem(baseline,configured);
    const double wanted[]{2.,60.,100.,4.};
    for (int i=0; i<4; ++i) {
      expect(configured.start[i]==wanted[i],"CLI start option was not applied");
      for (const std::string value : {"nan","inf","-inf","bad","2x"})
        must_throw([&]{ args({options[i],value}); });
      must_throw([&]{ args({options[i]}); });
    }

    // Parameter-bound overrides take effect before explicit-start validation.
    Config bounds=args({"--mp-low","30", "--mp-high","40", "--start-mp","35",
                        "--gsigma-high","58.129", "--start-gsigma","40"});
    auto altered=production_setup(h,bounds,seed);
    expect(altered.start[1]==35. && altered.start[3]==40.,"final bounds were not used");
    bounds.start_mp=45.;
    must_throw([&]{ production_setup(h,bounds,seed); });
    bounds.start_mp=35.;
    bounds.start_gsigma=58.129;
    must_throw([&]{ production_setup(h,bounds,seed); });
    bounds.gsigma_high=seed.ped_sigma;
    bounds.start_gsigma=seed.ped_sigma/2.;
    must_throw([&]{ production_setup(h,bounds,seed); }); // Preserve cap-only validation.

    // Derive two actual target-cell seeds and exercise every segment/voltage
    // branch. Starts never change the target's pedestal, average MIP or bounds.
    const TemporaryCalibration calibration;
    for (int cell : {903,1152}) {
      const auto target=seed_from_calib(calibration.file.string(),cell,false,0.);
      expect(target.avmip==50. && target.active_channels==2,
             "target-cell selection changed the calibration average");
      expect(target.ped_sigma==(cell==903 ? 0.6 : 1.2),"wrong target-cell pedestal");
      for (int layers : {1,5,8}) for (double vov : {3.5,5.7,7.0}) {
        Config branch=defaults;
        branch.cell=cell;
        branch.layers_in_segment=layers;
        branch.vov=vov;
        check_variations(h,branch,target);
      }
    }
    std::cout << "PASS: start controls change only explicit starts; bounds, interval, "
                 "normalization, target-cell seeds and default behavior are preserved.\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "test_start_controls: " << e.what() << '\n';
    return 1;
  }
}
