#include "TileTrend.h"
#include "TFitResult.h"
#include "TFitResultPtr.h"

ClassImp(TileTrend);

bool TileTrend::Fill(double x, const TileCalib& tc, int runNr){
  gTrendLGped   .AddPoint     (x,tc.PedestalMeanL);
  gTrendLGped   .SetPointError(gTrendLGped.GetN()-1,0.,tc.PedestalSigL);
  if(tc.PedestalMeanL<MinLGped && tc.PedestalMeanL > -100) MinLGped=tc.PedestalMeanL;
  if(tc.PedestalMeanL>MaxLGped) MaxLGped=tc.PedestalMeanL;
  
  gTrendHGped   .AddPoint     (x,tc.PedestalMeanH);
  gTrendHGped   .SetPointError(gTrendHGped.GetN()-1,0.,tc.PedestalSigH);
  if(tc.PedestalMeanH<MinHGped && tc.PedestalMeanH > -100) MinHGped=tc.PedestalMeanH;
  if(tc.PedestalMeanH>MaxHGped) MaxHGped=tc.PedestalMeanH;
  
  gTrendLGscale .AddPoint     (x,tc.ScaleL       );
  gTrendLGscale .SetPointError(gTrendLGscale.GetN()-1,0.,tc.ScaleWidthL);
  if(tc.ScaleL<MinLGscale && tc.ScaleL > 0) MinLGscale=tc.ScaleL;
  if(tc.ScaleL>MaxLGscale) MaxLGscale=tc.ScaleL;
  
  gTrendHGscale .AddPoint     (x,tc.ScaleH       );
  gTrendHGscale .SetPointError(gTrendHGscale.GetN()-1,0.,tc.ScaleWidthH);
  if(tc.ScaleH<MinHGscale  && tc.ScaleH > 0) MinHGscale=tc.ScaleH;
  if(tc.ScaleH>MaxHGscale) MaxHGscale=tc.ScaleH;
  
  gTrendHGLGcorr.AddPoint     (x,tc.HGLGCorr     );
  gTrendHGLGcorr.SetPointError(gTrendHGLGcorr.GetN()-1,0.,0.);
  if(tc.HGLGCorr<MinHGLGcorr && tc.HGLGCorr > 0) MinHGLGcorr=tc.HGLGCorr;
  if(tc.HGLGCorr>MaxHGLGcorr) MaxHGLGcorr=tc.HGLGCorr;
  
  gTrendLGHGcorr.AddPoint     (x,tc.LGHGCorr     );
  gTrendLGHGcorr.SetPointError(gTrendLGHGcorr.GetN()-1,0.,0.);
  if(tc.LGHGCorr<MinLGHGcorr && tc.LGHGCorr > 0) MinLGHGcorr=tc.LGHGCorr;
  if(tc.LGHGCorr>MaxLGHGcorr) MaxLGHGcorr=tc.LGHGCorr;
  
  runNrs.push_back(runNr);
  
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
bool TileTrend::DrawLGHGcorr(TString opt){
  gTrendLGHGcorr.Draw(opt.Data());
  return true;
}

bool TileTrend::SetLineColor(uint col){
  gTrendLGped    .SetLineColor(col);
  gTrendHGped    .SetLineColor(col);
  gTrendLGscale  .SetLineColor(col);
  gTrendHGscale  .SetLineColor(col);
  gTrendHGLGcorr .SetLineColor(col);
  gTrendLGHGcorr .SetLineColor(col);
  return true;
}
bool TileTrend::SetMarkerColor(uint col){
  gTrendLGped    .SetMarkerColor(col);
  gTrendHGped    .SetMarkerColor(col);
  gTrendLGscale  .SetMarkerColor(col);
  gTrendHGscale  .SetMarkerColor(col);
  gTrendHGLGcorr .SetMarkerColor(col);
  gTrendLGHGcorr .SetMarkerColor(col);
  return true;
}
bool TileTrend::SetMarkerStyle(uint col){
  gTrendLGped    .SetMarkerStyle(col);
  gTrendHGped    .SetMarkerStyle(col);
  gTrendLGscale  .SetMarkerStyle(col);
  gTrendHGscale  .SetMarkerStyle(col);
  gTrendHGLGcorr .SetMarkerStyle(col);
  gTrendLGHGcorr .SetMarkerStyle(col);
  return true;
}

bool TileTrend::SetXAxisTitle(TString title){
  gTrendLGped    .GetXaxis()->SetTitle(title.Data());
  gTrendHGped    .GetXaxis()->SetTitle(title.Data());
  gTrendLGscale  .GetXaxis()->SetTitle(title.Data());
  gTrendHGscale  .GetXaxis()->SetTitle(title.Data());
  gTrendHGLGcorr .GetXaxis()->SetTitle(title.Data());
  gTrendLGHGcorr .GetXaxis()->SetTitle(title.Data());
  return true;
}

bool TileTrend::AppendHistRun(int runNr, TH1D hgTrigg, TH1D lgTrigg ){
 HGTriggRuns[runNr] = hgTrigg;
 LGTriggRuns[runNr] = lgTrigg; 
 return true;
}


bool TileTrend::Write(TFile* f){
  f->cd();
  gTrendLGped    .Write();
  gTrendHGped    .Write();
  gTrendLGscale  .Write();
  gTrendHGscale  .Write();
  gTrendHGLGcorr .Write();
  gTrendLGHGcorr .Write();
  return true;
}
