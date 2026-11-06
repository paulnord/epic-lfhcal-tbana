#ifndef LFHCAL_WAVEFORM_ANNOTATIONS_H
#define LFHCAL_WAVEFORM_ANNOTATIONS_H

// Display only. AnalyseWaveForm supplies the exact WaveformMeasurement objects
// that it writes to the summary histograms; this code never extracts or fits.
#include "TileSpectra.h"
#include <TCanvas.h>
#include <TFile.h>
#include <TLatex.h>
#include <TLine.h>
#include <TPad.h>
#include <TSystem.h>
#include <TStyle.h>
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace lfhcal {
struct WaveformAnnotationCell {
  int cell;
  const TProfile* profile;
  WaveformMeasurement measurement;
};

inline void WaveformText(double x,double y,const TString& text,double size,int color=kBlack) {
  TLatex label; label.SetNDC(); label.SetTextFont(42); label.SetTextSize(size);
  label.SetTextColor(color); label.DrawLatex(x,y,text);
}

inline void WaveformGuide(const char* name,double x1,double y1,double x2,double y2,int color,int style) {
  auto* line=new TLine(x1,y1,x2,y2);
  line->SetUniqueID(TString(name).Hash()); line->SetBit(TObject::kCanDelete);
  line->SetLineColor(color); line->SetLineStyle(style); line->SetLineWidth(1);
  line->Draw();
}

// Exactly three vertical and one horizontal guide for a valid measurement.
// A missing width never acquires invented crossings. No midpoint, A/2 line,
// fit, interpolation, or extra 200 ns fence is drawn.
inline void DrawWaveformGuides(const WaveformMeasurement& m,
                              double xmin,double xmax,double ymin,double ymax,
                              bool normalized=false) {
  if (m.hasPeak) {
    WaveformGuide("waveform_peak_time",m.peakTime,ymin,m.peakTime,ymax,kRed+1,1);
    const double amplitude=normalized?1.:m.amplitude;
    WaveformGuide("waveform_peak_amplitude",xmin,amplitude,xmax,amplitude,kOrange+7,7);
  }
  if (m.hasFWHM) {
    WaveformGuide("waveform_left_boundary",m.leftCrossing,ymin,m.leftCrossing,ymax,kGreen+2,2);
    WaveformGuide("waveform_right_boundary",m.rightCrossing,ymin,m.rightCrossing,ymax,kMagenta+1,3);
  }
  if (!m.hasPeak || !m.hasFWHM)
    WaveformText(.18,.68,TileSpectra::WaveformMeasurementStatusName(m.status),.065,kRed+1);
}

inline void ValidateWaveformAnnotationCells(const std::vector<WaveformAnnotationCell>& cells) {
  if(cells.empty()) throw std::runtime_error("no selected waveform cells");
  std::set<int> seen;
  for(const auto& c:cells) {
    if(!seen.insert(c.cell).second) throw std::runtime_error("duplicate selected waveform cell");
    const auto& m=c.measurement;
    if(!c.profile && (m.hasPeak||m.hasFWHM)) throw std::runtime_error("measurement without profile");
    if(m.hasPeak && (!std::isfinite(m.amplitude)||m.amplitude<=0.||!std::isfinite(m.peakTime)))
      throw std::runtime_error("nonfinite/invalid supplied peak measurement");
    if(m.hasFWHM && (!m.hasPeak||!std::isfinite(m.leftCrossing)||!std::isfinite(m.rightCrossing)||
        !std::isfinite(m.fwhm)||m.fwhm<=0.||m.rightCrossing<=m.leftCrossing))
      throw std::runtime_error("nonfinite/invalid supplied width measurement");
  }
}

struct WaveformDisplayRange { double xmin=-20.,xmax=220.,ymin=0.,ymax=1.; };
inline WaveformDisplayRange WaveformGridRange(const std::vector<WaveformAnnotationCell>& cells) {
  WaveformDisplayRange range;
  for(const auto& c:cells) {
    if(!c.profile) continue;
    const auto& m=c.measurement;
    if(m.hasPeak) { range.xmin=std::min(range.xmin,m.peakTime-1.); range.xmax=std::max(range.xmax,m.peakTime+1.); }
    if(m.hasFWHM) { range.xmin=std::min(range.xmin,m.leftCrossing-1.); range.xmax=std::max(range.xmax,m.rightCrossing+1.); }
  }
  for(const auto& c:cells) {
    if(!c.profile) continue;
    const int first=std::max(1,c.profile->GetXaxis()->FindBin(range.xmin));
    // Match the saved 64-cell producer: late noise must not flatten all cells.
    const int last=std::min(c.profile->GetNbinsX(),c.profile->GetXaxis()->FindBin(200.));
    for(int b=first;b<=last;++b) {
      const double y=c.profile->GetBinContent(b);
      if(std::isfinite(y)){range.ymin=std::min(range.ymin,y);range.ymax=std::max(range.ymax,y);}
    }
    if(c.measurement.hasPeak) range.ymax=std::max(range.ymax,c.measurement.amplitude);
  }
  const double pad=.12*(range.ymax-range.ymin);
  range.ymax+=pad; if(range.ymin<0.)range.ymin-=pad;
  return range;
}

inline void DrawWaveformGridPage(TCanvas& canvas,const std::vector<WaveformAnnotationCell>& cells,
                                int run,size_t first,bool annotated,bool normalized,
                                const TString& label="") {
  ValidateWaveformAnnotationCells(cells);
  const auto range=WaveformGridRange(cells);
  const double ymin=normalized?-.08:range.ymin, ymax=normalized?1.12:range.ymax;
  canvas.Clear();canvas.cd();
  auto* header=new TPad("waveform_header","",0.,.93,1.,1.);
  header->SetBit(TObject::kCanDelete);header->SetMargin(0,0,0,0);header->Draw();header->cd();
  WaveformText(.015,.67,Form("%sRun %d | %s | %s | cells %zu-%zu",
    label.IsNull()?"":(label+" | ").Data(),run,normalized?"normalized mean profiles":"absolute mean profiles",
    annotated?"annotated":"unmarked",first+1,std::min(first+64,cells.size())),.28);
  WaveformText(.015,.34,annotated?
    "Vertical: #color[418]{left half-max}, #color[633]{peak time}, #color[617]{right half-max}; horizontal: #color[807]{peak amplitude}":
    "Same source profiles and axes as the annotated companion; no measurement guides",.23);
  WaveformText(.015,.08,normalized?
    "t (ns), amplitude / cell peak; maximum through bin containing 200 ns; bin-center boundaries; no fit":
    "t (ns), ADC above pedestal; scale excludes post-search noise; bin-center boundaries through 200 ns; no fit",.19);
  canvas.cd();auto* grid=new TPad("waveform_grid","",0.,0.,1.,.93);
  grid->SetBit(TObject::kCanDelete);grid->Draw();grid->Divide(8,8,.0008,.0008);
  for(size_t i=first;i<std::min(first+64,cells.size());++i) {
    grid->cd(static_cast<int>(i-first)+1);
    gPad->SetMargin(.15,.025,.15,.025);gPad->SetTicks(1,1);
    const auto& c=cells[i];const auto& m=c.measurement;
    if(!c.profile || (normalized&&!m.hasPeak)) {
      WaveformText(.20,.80,Form("%d",c.cell),.13);
      WaveformText(.19,.50,c.profile?"no positive peak":"missing profile",.09,kRed+1);continue;
    }
    auto* p=static_cast<TProfile*>(c.profile->Clone(Form("waveform_display_%zu",i)));
    p->SetDirectory(nullptr);p->SetBit(TObject::kCanDelete);
    if(normalized)p->Scale(1./m.amplitude);
    p->SetStats(false);p->SetTitle("");p->SetLineColor(kBlue+2);p->SetLineWidth(1);
    p->GetXaxis()->SetRangeUser(range.xmin,range.xmax);p->SetMinimum(ymin);p->SetMaximum(ymax);
    for(auto* axis:{p->GetXaxis(),p->GetYaxis()}) {axis->SetNdivisions(404);axis->SetLabelSize(.08);axis->SetLabelOffset(.006);axis->SetTitle("");}
    p->Draw("HIST");
    // ROOT can clamp the selected range on shorter input axes. Draw guides
    // inside the actual frame, not outside neighboring pads.
    gPad->Modified();gPad->Update();
    if(annotated)DrawWaveformGuides(m,gPad->GetUxmin(),gPad->GetUxmax(),ymin,ymax,normalized);
    TLatex cellLabel;cellLabel.SetNDC();cellLabel.SetTextFont(62);cellLabel.SetTextSize(.13);cellLabel.SetTextAlign(31);
    cellLabel.SetTextColor(m.peakAtSearchBoundary||!m.hasFWHM?kRed+1:kBlack);
    cellLabel.DrawLatex(.95,.82,Form("%d",c.cell));
  }
  canvas.cd();canvas.Modified();canvas.Update();
}

inline void WriteWaveformAnnotationGrid(const std::vector<WaveformAnnotationCell>& cells,int run,
                                       const std::string& base,const std::string& source,
                                       const TString& label="") {
  ValidateWaveformAnnotationCells(cells);
  const std::string original=base+"_Original.pdf", annotated=base+"_Annotated.pdf", csv=base+"_Measurements.csv";
  for(const auto& path:{original,annotated,csv})
    if(!gSystem->AccessPathName(path.c_str()))throw std::runtime_error("annotation output exists: "+path);
  std::ofstream out(csv);if(!out)throw std::runtime_error("cannot create annotation CSV");
  out<<std::setprecision(17)<<"run,cell,status,has_peak,has_fwhm,peak_bin,left_bin,right_bin,amplitude,peak_time_ns,left_ns,right_ns,fwhm_ns,source\n";
  std::string quotedSource="\"";for(char ch:source){if(ch=='\"')quotedSource+='\"';quotedSource+=ch;}quotedSource+='\"';
  for(const auto& c:cells) {
    const auto& m=c.measurement;
    out<<run<<','<<c.cell<<','<<static_cast<int>(m.status)<<','<<m.hasPeak<<','<<m.hasFWHM<<','<<m.peakBin<<','<<m.leftBin<<','<<m.rightBin<<',';
    if(m.hasPeak)out<<m.amplitude;
    out<<',';
    if(m.hasPeak)out<<m.peakTime;
    out<<',';
    if(m.hasFWHM)out<<m.leftCrossing;
    out<<',';
    if(m.hasFWHM)out<<m.rightCrossing;
    out<<',';
    if(m.hasFWHM)out<<m.fwhm;
    out<<','<<quotedSource<<'\n';
  }
  out.close();if(!out)throw std::runtime_error("failed writing annotation CSV");
  struct RestorePaperSize {
    Float_t x,y;
    RestorePaperSize(){gStyle->GetPaperSize(x,y);gStyle->SetPaperSize(26.,20.);}
    ~RestorePaperSize(){gStyle->SetPaperSize(x,y);}
  } restorePaperSize;
  TCanvas canvas("waveform_annotation_grid","",1600,1200);canvas.SetCanvasSize(1600,1200);
  for(bool marked:{false,true}) {
    const auto& pdf=marked?annotated:original;
    canvas.Print((pdf+"[").c_str());
    for(size_t first=0;first<cells.size();first+=64)for(bool normalized:{false,true}) {
      DrawWaveformGridPage(canvas,cells,run,first,marked,normalized,label);canvas.Print(pdf.c_str());
    }
    canvas.Print((pdf+"]").c_str());
    Long_t id=0,size=0,flags=0,mtime=0;
    if(gSystem->GetPathInfo(pdf.c_str(),&id,&size,&flags,&mtime)!=0||size==0)
      throw std::runtime_error("failed writing annotation PDF: "+pdf);
  }
}
} // namespace lfhcal
#endif
