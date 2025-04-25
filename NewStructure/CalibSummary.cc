#include "CalibSummary.h"
#include "TFitResult.h"
#include "TFitResultPtr.h"

ClassImp(CalibSummary);

bool CalibSummary::Fill(const TileCalib& tc){
  hLGped        .Fill(tc.PedestalMeanL);
  hLGpedwidth   .Fill(tc.PedestalSigL);
  hHGped        .Fill(tc.PedestalMeanH);
  hHGpedwidth   .Fill(tc.PedestalSigH);
  hLGscale      .Fill(tc.ScaleL);
  hLGscalewidth .Fill(tc.ScaleWidthL);
  hHGscale      .Fill(tc.ScaleH);
  hHGscalewidth .Fill(tc.ScaleWidthH);
  hHGLGcorr     .Fill(tc.HGLGCorr);
  hLGHGcorr     .Fill(tc.LGHGCorr);
  return true;
}

bool CalibSummary::Write(TFile* f){
  f->cd();
  hLGped          .Write();
  hLGpedwidth     .Write();
  hHGped          .Write();
  hHGpedwidth     .Write();
  hLGscale        .Write();
  hLGscalewidth   .Write();
  hHGscale        .Write();
  hHGscalewidth   .Write();
  hHGLGcorr       .Write();
  hLGHGcorr       .Write();
  return true;
}
