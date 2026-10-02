#ifndef LFHCAL_MIP_RANGE_FINDER_V1_H
#define LFHCAL_MIP_RANGE_FINDER_V1_H
// Frozen 2026-10-02 study rule. Smooth only a temporary count vector.
// Gaussian sigma=2 bins, truncate=4, reflect edges; peak distance=8 bins.
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <string>
#include <vector>
namespace lfhcal { namespace mip_range_v1 {
struct Result {
  bool usable=false;
  std::string reason="invalid_input";
  double lower=0., observed=std::numeric_limits<double>::quiet_NaN();
  double valley=std::numeric_limits<double>::quiet_NaN();
  double fraction=std::numeric_limits<double>::quiet_NaN();
};
inline Result choose(const std::vector<double>& x,const std::vector<double>& y,
                     double pedestalSigma,double average,double original) {
  Result r;r.lower=original;
  const int n=static_cast<int>(y.size());
  if(n<3 || x.size()!=y.size() || !std::isfinite(pedestalSigma) || pedestalSigma<=0 ||
     !std::isfinite(average) || average<=0 || !std::isfinite(original)) return r;
  for(int i=0;i<n;++i)
    if(!std::isfinite(x[i]) || !std::isfinite(y[i]) || y[i]<0 || (i && x[i]<=x[i-1]))return r;
  double kernel[17],norm=0.;
  for(int j=-8;j<=8;++j){kernel[j+8]=std::exp(-0.5*j*j/4.);norm+=kernel[j+8];}
  for(double& w:kernel)w/=norm;
  std::vector<double> smooth(n,0.);
  for(int i=0;i<n;++i)for(int j=-8;j<=8;++j){
    int k=i+j;while(k<0 || k>=n){if(k<0)k=-k-1;else k=2*n-k-1;}
    smooth[i]+=kernel[j+8]*y[k];
  }
  const double bandLow=std::max(3*pedestalSigma,.5*average),bandHigh=2.5*average;
  double bandMax=-1.;
  for(int i=0;i<n;++i)if(x[i]>=bandLow && x[i]<=bandHigh)bandMax=std::max(bandMax,smooth[i]);
  if(bandMax<0){r.reason="empty_peak_band";return r;}
  std::vector<int> peaks;
  for(int i=1;i<n-1;++i)if(smooth[i]>smooth[i-1]){
    int end=i;while(end+1<n && smooth[end+1]==smooth[i])++end;
    if(end<n-1 && smooth[end]>smooth[end+1])peaks.push_back((i+end)/2);
    i=end;
  }
  // Match scipy.signal.find_peaks ordering: distance before prominence.
  std::vector<int> priority=peaks;
  std::sort(priority.begin(),priority.end(),[&](int a,int b){return smooth[a]==smooth[b]?a>b:smooth[a]>smooth[b];});
  std::vector<int> kept;
  for(int p:priority){bool close=false;for(int k:kept)if(std::abs(p-k)<8){close=true;break;}if(!close)kept.push_back(p);}
  std::sort(kept.begin(),kept.end());
  int peak=-1;double best=-1.;
  for(int p:kept){
    double left=smooth[p],right=smooth[p];
    for(int i=p;i>=0 && smooth[i]<=smooth[p];--i)left=std::min(left,smooth[i]);
    for(int i=p;i<n && smooth[i]<=smooth[p];++i)right=std::min(right,smooth[i]);
    double prominence=smooth[p]-std::max(left,right);
    if(prominence>=.2*bandMax && x[p]>=bandLow && x[p]<=bandHigh && prominence>best){best=prominence;peak=p;}
  }
  if(peak<0){r.reason="no_prominent_peak";return r;}
  r.observed=x[peak];
  std::vector<int> interval;
  for(int i=0;i<n;++i)if(x[i]>=3*pedestalSigma && x[i]<=.8*x[peak])interval.push_back(i);
  if(interval.size()<3){r.reason="insufficient_space";return r;}
  int valley=interval.front();for(int i:interval)if(smooth[i]<smooth[valley])valley=i;
  r.valley=x[valley];r.fraction=smooth[valley]/smooth[peak];
  if(valley==interval.front() || valley==interval.back()){r.reason="minimum_at_boundary";return r;}
  if(r.fraction>.5){r.reason="shallow_valley";return r;}
  r.lower=std::max(original,r.valley);
  if(r.lower>=r.observed){r.lower=original;r.reason="range_excludes_peak";return r;}
  r.usable=true;r.reason=r.lower>original?"raised":"retained_original_floor";return r;
}
}}
#endif
