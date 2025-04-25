#ifndef CALIBSUMMARY_H
#define CALIBSUMMARY_H

#include "TObject.h"
#include "TString.h"
#include "TH1D.h"
#include "TH2D.h"
#include "TProfile.h"
#include "TGraphErrors.h"
#include "TF1.h"
#include "TPad.h" 
#include "TCanvas.h"
#include "TLegend.h"
#include "TFile.h"
#include "Calib.h"

class CalibSummary: public TObject{

 public:
 CalibSummary():TObject(){}
 CalibSummary(int id):TObject()
 {
    RunNr             = id;
    hHGped            = TH1D(Form("hMeanPedHG_%i",id),"; #mu_{noise, HG} (arb. units); counts ", 500, -0.5, 500-0.5);
    hHGpedwidth       = TH1D(Form("hMeanPedHGwidth_%i",id),"; #sigma_{noise, HG} (arb. units); counts ", 200, -0.5, 50-0.5);
    hLGped            = TH1D(Form("hMeanPedLG_%i",id),"; #mu_{noise, LG} (arb. units); counts ", 500, -0.5, 500-0.5);
    hLGpedwidth       = TH1D(Form("hMeanPedLGwidth_%i",id),"; #sigma_{noise, LG} (arb. units); counts ", 200, -0.5, 50-0.5);
    hHGscale          = TH1D(Form("hHGScale_%i",id),";Max_{HG} (arb. units) ; counts ", 2000, -0.5, 2000-0.5);
    hHGscalewidth     = TH1D(Form("hHGScalewidth_%i",id),";Width_{HG} (arb. units) ; counts ", 2000, -0.5, 1000-0.5);
    hLGscale          = TH1D(Form("hLGScale_%i",id),";Max_{LG} (arb. units) ; counts ", 2000, -0.5, 500-0.5);
    hLGscalewidth     = TH1D(Form("hHGScalewidth_%i",id),";Width_{LG} (arb. units) ; counts ", 2000, -0.5, 250-0.5);
    hLGHGcorr         = TH1D(Form("hLGHGCorr_%i",id),"; a_{LG-HG} (arb. units) ; counts ", 400, -20, 20);
    hHGLGcorr         = TH1D(Form("hHGLGCorr_%i",id),"; a_{HG-LG} (arb. units) ; counts ", 400, -1., 1.);
  }
  ~CalibSummary(){}

  bool Fill(const TileCalib&);
  bool Write(TFile*);

  inline TH1D* GetHGped()         {return &hHGped;};
  inline TH1D* GetHGpedwidth()    {return &hHGpedwidth;};
  inline TH1D* GetLGped()         {return &hLGped;};
  inline TH1D* GetLGpedwidth()    {return &hLGpedwidth;};
  inline TH1D* GetHGScale()       {return &hHGscale;};
  inline TH1D* GetHGScalewidth()  {return &hHGscalewidth;};
  inline TH1D* GetLGScale()       {return &hLGscale;};
  inline TH1D* GetLGScalewidth()  {return &hLGscalewidth;};
  inline TH1D* GetLGHGcorr()      {return &hHGLGcorr;};
  inline TH1D* GetHGLGcorr()      {return &hLGHGcorr;};
  
 protected:
  int RunNr;
  TH1D hLGped             ;
  TH1D hLGpedwidth        ;
  TH1D hHGped             ;
  TH1D hHGpedwidth        ;
  TH1D hLGscale      ;
  TH1D hLGscalewidth ;
  TH1D hHGscale      ;
  TH1D hHGscalewidth ;
  TH1D hHGLGcorr     ;
  TH1D hLGHGcorr     ;
  
  ClassDef(CalibSummary,1);
};

#endif
