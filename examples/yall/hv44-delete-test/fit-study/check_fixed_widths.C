// Read existing np100/np1000/np10000 CSVs. Hold every fit parameter fixed.
// ROOT: env CELL903_CSV_DIR=/path/to/fit-resolution root -l -b -q check_fixed_widths.C
// No histogram, no fit, no writes to source CSVs or calibration files.
#include "fixed_width_numerics.h"
#include "TMath.h"
#include "TROOT.h"
#include "TSystem.h"
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <string>

namespace cell903_fixed_check {
using namespace fixed_width;
using Row = std::map<std::string,std::string>;

std::vector<std::string> split_csv(std::string line) {
  if (!line.empty() && line.back()=='\r') line.pop_back();
  std::vector<std::string> result;
  std::string item;
  bool quoted=false;
  for (size_t i=0;i<line.size();++i) {
    char c=line[i];
    if (c=='"') {
      if (quoted && i+1<line.size() && line[i+1]=='"') {item+='"';++i;}
      else quoted=!quoted;
    } else if (c==',' && !quoted) {result.push_back(item); item.clear();}
    else item+=c;
  }
  require(!quoted,"unterminated CSV quote");
  result.push_back(item);
  return result;
}
std::string csv_quote(const std::string &s) {
  std::string out="\"";
  for(char c:s) {out+=c; if(c=='"') out+='"';}
  return out+'"';
}
const std::string &field(const Row &r,const char *name) {
  auto it=r.find(name);
  if (it==r.end()) throw std::runtime_error(std::string("missing CSV field: ")+name);
  return it->second;
}
double number(const Row &r,const char *name) {
  size_t used=0;
  const auto &s=field(r,name);
  const double x=std::stod(s,&used);
  require(used==s.size() && std::isfinite(x),"invalid or nonfinite parameter in CSV");
  return x;
}
std::vector<Row> read_rows(const std::string &path) {
  std::ifstream in(path);
  if(!in) throw std::runtime_error("cannot read "+path);
  std::string line;
  require(bool(std::getline(in,line)),"empty CSV file");
  const auto names=split_csv(line);
  std::vector<Row> rows;
  int lineno=1;
  while(std::getline(in,line)) {
    ++lineno;
    if(line.empty()) continue;
    const auto fields=split_csv(line);
    if(fields.size()!=names.size()) throw std::runtime_error(path+":"+std::to_string(lineno)+": CSV column count mismatch");
    Row row;
    for(size_t i=0;i<names.size();++i)
      require(row.emplace(names[i],fields[i]).second,"duplicate CSV column name");
    row["source_file"]=path;
    row["source_row"]=std::to_string(lineno-1);
    rows.push_back(row);
  }
  require(!rows.empty(),"CSV contains no fitted parameter rows");
  return rows;
}
// Legacy fixed-grid evaluation, used only to compare curves, never to fit
// or find the new width. Preserve its constants and symmetric summation.
double legacy(double x,const Parameters &p,int np) {
  const double mpc=p.mp+.22278298*p.width;
  const double low=x-5*p.sigma, high=x+5*p.sigma, step=(high-low)/np;
  double sum=0;
  for(double i=1;i<=np/2.;++i) {
    double t=low+(i-.5)*step;
    sum+=TMath::Landau(t,mpc,p.width)/p.width*TMath::Gaus(x,t,p.sigma);
    t=high-(i-.5)*step;
    sum+=TMath::Landau(t,mpc,p.width)/p.width*TMath::Gaus(x,t,p.sigma);
  }
  return p.area*step*sum*.3989422804014/p.sigma;
}
void run() {
  self_test();
  std::cout<<"PASS: 4 Gaussian FWHM controls; 20 analytic finite-interval Gaussian convolution controls.\n";
  const char *dir=std::getenv("CELL903_CSV_DIR");
  require(dir && *dir,"set CELL903_CSV_DIR to the directory containing np100.csv, np1000.csv, np10000.csv");
  std::vector<Row> rows;
  for(const char *name:{"np100.csv","np1000.csv","np10000.csv"}) {
    auto more=read_rows(std::string(dir)+"/"+name);
    rows.insert(rows.end(),more.begin(),more.end());
  }
  const char *custom=std::getenv("CELL903_WIDTH_REPORT");
  const std::string outpath=(custom && *custom)?custom:std::string(dir)+"/fixed-width-check.csv";
  require(gSystem->AccessPathName(outpath.c_str()),"output already exists; choose a new CELL903_WIDTH_REPORT path");
  std::ofstream out(outpath);
  require(bool(out),"cannot create width-check report");
  out<<"source_file,seed,source_row,source_np,source_fit_status,source_limits_reached,source_gate,source_langau_status,source_peak,source_fwhm,"
     <<"width,mp,area,gsigma,adaptive_peak,adaptive_left,adaptive_right,adaptive_fwhm,left_fraction,right_fraction,"
     <<"peak_change_tighter,fwhm_change_tighter,curve_change_tighter_over_peak,legacy_curve_max_error_over_peak,"
     <<"peak_change_span8,fwhm_change_span8,curve_change_span8_over_peak,quad_max_error_estimate,quad_max_evaluations,numerics_pass\n";
  out<<std::setprecision(17);
  std::cout<<"ROOT "<<gROOT->GetVersion()<<"; compiler "<<__VERSION__<<'\n'
    <<"Fixed parameter vectors; no fit. Main calculation keeps the original +/-5 sigma interval.\n"
    <<"Adaptive split Gauss-Legendre integration at relative tolerances 1e-8 and 1e-10.\n"
    <<"The +/-8 sigma result is a separate truncation-sensitivity check.\n"
    <<"np row old_status old_FWHM new_peak new_FWHM left/peak right/peak numeric_check source_gate\n";
  int failed=0;
  for (const Row &r:rows) {
    const Parameters p{number(r,"width"),number(r,"mp"),number(r,"area"),number(r,"gsigma")};
    const double npvalue=number(r,"np");
    require(npvalue>=2 && npvalue<=1000000 && npvalue==std::floor(npvalue) &&
            static_cast<int>(npvalue)%2==0,"invalid source integration step count");
    const int np=static_cast<int>(npvalue);
    const double scale=std::max(p.width,p.sigma);
    Function pdf=[](double u){return TMath::Landau(u,0.,1.);};
    Convolution loose(p,pdf,1e-8,5), tight(p,pdf,1e-10,5), wide(p,pdf,1e-10,8);
    auto ml=measure(std::ref(loose),p.mp,scale);
    auto mt=measure(std::ref(tight),p.mp,scale);
    auto mw=measure(std::ref(wide),p.mp,scale);
    double dcurve=0, dold=0, dtail=0;
    std::vector<double> grid{mt.left,mt.peak,mt.right,p.mp,p.mp+1};
    for(int k=0;k<=128;++k) grid.push_back(p.mp+scale*(-4.+12.*k/128.));
    for(double x:grid) {
      const double ft=tight(x);
      dcurve=std::max(dcurve,std::abs(loose(x)-ft)/mt.height);
      dold=std::max(dold,std::abs(legacy(x,p,np)-ft)/mt.height);
      dtail=std::max(dtail,std::abs(wide(x)-ft)/mt.height);
    }
    const double dp=mt.peak-ml.peak, dw=mt.fwhm-ml.fwhm;
    // Explicit diagnostic thresholds, in ADC units. Not fit-acceptance rules.
    const bool pass=std::abs(dp)<1e-3 && std::abs(dw)<1e-4 && dcurve<1e-7;
    if(!pass) ++failed;
    out<<csv_quote(field(r,"source_file"))<<','<<csv_quote(field(r,"seed"))<<','
       <<field(r,"source_row")<<','<<np<<','<<field(r,"fit_status")<<','
       <<field(r,"limits_reached")<<','<<field(r,"legacy_fit_gate_pass")<<','
       <<field(r,"langau_status")<<','<<field(r,"peak")<<','<<field(r,"fwhm")<<','
       <<p.width<<','<<p.mp<<','<<p.area<<','<<p.sigma<<','
       <<mt.peak<<','<<mt.left<<','<<mt.right<<','<<mt.fwhm<<','
       <<mt.left_fraction<<','<<mt.right_fraction<<','<<dp<<','<<dw<<','<<dcurve<<','<<dold<<','
       <<mw.peak-mt.peak<<','<<mw.fwhm-mt.fwhm<<','<<dtail<<','
       <<tight.max_estimated_error()<<','<<tight.max_calls()<<','<<int(pass)<<'\n';
    out.flush();
    require(bool(out),"failed to write report");
    std::cout<<np<<' '<<field(r,"source_row")<<' '<<field(r,"langau_status")<<' '
             <<field(r,"fwhm")<<' '<<std::fixed<<std::setprecision(8)
             <<mt.peak<<' '<<mt.fwhm<<' '<<mt.left_fraction<<' '<<mt.right_fraction<<' '
             <<(pass?"PASS":"CHECK")<<' '<<field(r,"legacy_fit_gate_pass")<<'\n';
  }
  out.close();
  std::cout<<"Report: "<<outpath<<'\n'
           <<"Source parameters, statuses and NaNs are preserved. Numerics PASS does not accept a fit.\n";
  require(failed==0,"one or more tolerance checks failed; inspect report before interpreting widths");
}
} // namespace cell903_fixed_check

void check_fixed_widths() {
  try {cell903_fixed_check::run();}
  catch(const std::exception &e) {
    std::cerr<<"check_fixed_widths: "<<e.what()<<'\n';
    gSystem->Exit(2);
  }
}
