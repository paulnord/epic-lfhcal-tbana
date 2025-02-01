#ifndef TILETREND_H
#define TILETREND_H

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

class TileTrend: public TObject{

 public:
 TileTrend():TObject(){}
 TileTrend(int id, int deb=0):TObject()
    {
    CellID         = id;
    debug          = deb;
    gTrendLGped    = TGraphErrors();
    gTrendHGped    = TGraphErrors();
    gTrendLGscale  = TGraphErrors();
    gTrendHGscale  = TGraphErrors();
    gTrendHGLGcorr = TGraphErrors();
    
    gTrendLGped    .SetName(Form("TrendLGpedCellID%d",CellID));
    gTrendHGped    .SetName(Form("TrendHGpedCellID%d",CellID));
    gTrendLGscale  .SetName(Form("TrendLGscaleCellID%d",CellID));
    gTrendHGscale  .SetName(Form("TrendHGscaleCellID%d",CellID));
    gTrendHGLGcorr .SetName(Form("TrendHGLGcorrCellID%d",CellID));
    
    gTrendLGped    .SetLineColor(kRed);
    gTrendHGped    .SetLineColor(kRed);
    gTrendLGscale  .SetLineColor(kRed);
    gTrendHGscale  .SetLineColor(kRed);
    gTrendHGLGcorr .SetLineColor(kRed);
    
    gTrendLGped    .SetMarkerColor(kRed);
    gTrendHGped    .SetMarkerColor(kRed);
    gTrendLGscale  .SetMarkerColor(kRed);
    gTrendHGscale  .SetMarkerColor(kRed);
    gTrendHGLGcorr .SetMarkerColor(kRed);
    
    gTrendLGped    .SetMarkerStyle(kFullCircle);
    gTrendHGped    .SetMarkerStyle(kFullCircle);
    gTrendLGscale  .SetMarkerStyle(kFullCircle);
    gTrendHGscale  .SetMarkerStyle(kFullCircle);
    gTrendHGLGcorr .SetMarkerStyle(kFullCircle);

    //gTrendLGped    .SetDirectory(0);
    //gTrendHGped    .SetDirectory(0);
    //gTrendLGscale  .SetDirectory(0);
    //gTrendHGscale  .SetDirectory(0);
    //gTrendHGLGcorr .SetDirectory(0);
    }
  ~TileTrend(){}

  bool Fill(double, const TileCalib&);
  bool DrawLGped(TString);
  bool DrawHGped(TString);
  bool DrawLGscale(TString);
  bool DrawHGscale(TString);
  bool DrawHGLGcorr(TString);
  bool SetLineColor(uint);
  bool SetMarkerColor(uint);
  bool SetMarkerStyle(uint);
  bool Write(TFile*);

  inline double GetMinLGped()   {return MinLGped;};
  inline double GetMaxLGped()   {return MaxLGped;};
  inline double GetMinHGped()   {return MinHGped;};
  inline double GetMaxHGped()   {return MaxHGped;};
  inline double GetMinLGscale() {return MinLGscale;};
  inline double GetMaxLGscale() {return MaxLGscale;};
  inline double GetMinHGscale() {return MinHGscale;};
  inline double GetMaxHGscale() {return MaxHGscale;};
  inline double GetMinHGHGcorr(){return MinHGLGcorr;};
  inline double GetMaxHGHGcorr(){return MaxHGLGcorr;};
  
 protected:
  int CellID;
  int debug;
  TGraphErrors gTrendLGped    ;
  TGraphErrors gTrendHGped    ;
  TGraphErrors gTrendLGscale  ;
  TGraphErrors gTrendHGscale  ;
  TGraphErrors gTrendHGLGcorr ;

  double MaxLGped    =0.;
  double MaxHGped    =0.;
  double MaxLGscale  =0.;
  double MaxHGscale  =0.;
  double MaxHGLGcorr =0.;
  
  double MinLGped    =9999.;
  double MinHGped    =9999.;
  double MinLGscale  =9999.;
  double MinHGscale  =9999.;
  double MinHGLGcorr =9999.;

  ClassDef(TileTrend,1);
};

#endif
