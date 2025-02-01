#include "TileTrend.h"
#include "TFitResult.h"
#include "TFitResultPtr.h"

ClassImp(TileTrend);

bool TileTrend::Fill(double x, const TileCalib& tc){
  gTrendLGped   .AddPoint     (x,tc.PedestalMeanL);
  gTrendLGped   .SetPointError(gTrendLGped.GetN()-1,0.,tc.PedestalSigL);
  if(tc.PedestalMeanL<MinLGped) MinLGped=tc.PedestalMeanL;
  if(tc.PedestalMeanL>MaxLGped) MaxLGped=tc.PedestalMeanL;
  
  gTrendHGped   .AddPoint     (x,tc.PedestalMeanH);
  gTrendHGped   .SetPointError(gTrendHGped.GetN()-1,0.,tc.PedestalSigH);
  if(tc.PedestalMeanH<MinHGped) MinHGped=tc.PedestalMeanH;
  if(tc.PedestalMeanH>MaxHGped) MaxHGped=tc.PedestalMeanH;
  
  gTrendLGscale .AddPoint     (x,tc.ScaleL       );
  gTrendLGscale .SetPointError(gTrendLGscale.GetN()-1,0.,tc.ScaleWidthL);
  if(tc.ScaleL<MinLGscale) MinLGscale=tc.ScaleL;
  if(tc.ScaleL>MaxLGscale) MaxLGscale=tc.ScaleL;
  
  gTrendHGscale .AddPoint     (x,tc.ScaleH       );
  gTrendHGscale .SetPointError(gTrendHGscale.GetN()-1,0.,tc.ScaleWidthH);
  if(tc.ScaleH<MinHGscale) MinHGscale=tc.ScaleH;
  if(tc.ScaleH>MaxHGscale) MaxHGscale=tc.ScaleH;
  
  gTrendHGLGcorr.AddPoint     (x,tc.HGLGCorr     );
  gTrendHGLGcorr.SetPointError(gTrendHGLGcorr.GetN()-1,0.,tc.LGHGCorr);
  if(tc.HGLGCorr<MinHGLGcorr) MinHGLGcorr=tc.HGLGCorr;
  if(tc.HGLGCorr>MaxHGLGcorr) MaxHGLGcorr=tc.HGLGCorr;
  return true;
}


bool TileTrend::DrawLGped(TString opt){
  gTrendLGped.Draw(opt.Data());
  return true;
}
bool TileTrend::DrawHGped(TString opt){
  gTrendHGped.Draw(opt.Data());
  return true;
}

bool TileTrend::DrawLGscale(TString opt){
  gTrendLGscale.Draw(opt.Data());
  return true;
}
bool TileTrend::DrawHGscale(TString opt){
  gTrendHGscale.Draw(opt.Data());
  return true;
}
bool TileTrend::DrawHGLGcorr(TString opt){
  gTrendHGLGcorr.Draw(opt.Data());
  return true;
}

bool TileTrend::SetLineColor(uint col){
  gTrendLGped    .SetLineColor(col);
  gTrendHGped    .SetLineColor(col);
  gTrendLGscale  .SetLineColor(col);
  gTrendHGscale  .SetLineColor(col);
  gTrendHGLGcorr .SetLineColor(col);
  return true;
}
bool TileTrend::SetMarkerColor(uint col){
  gTrendLGped    .SetMarkerColor(col);
  gTrendHGped    .SetMarkerColor(col);
  gTrendLGscale  .SetMarkerColor(col);
  gTrendHGscale  .SetMarkerColor(col);
  gTrendHGLGcorr .SetMarkerColor(col);
  return true;
}
bool TileTrend::SetMarkerStyle(uint col){
  gTrendLGped    .SetMarkerStyle(col);
  gTrendHGped    .SetMarkerStyle(col);
  gTrendLGscale  .SetMarkerStyle(col);
  gTrendHGscale  .SetMarkerStyle(col);
  gTrendHGLGcorr .SetMarkerStyle(col);
  return true;
}

bool TileTrend::Write(TFile* f){
  f->cd();
  gTrendLGped    .Write();
  gTrendHGped    .Write();
  gTrendLGscale  .Write();
  gTrendHGscale  .Write();
  gTrendHGLGcorr .Write();
  return true;
}
