#ifndef LFHCAL_WAVEFORM_ANNOTATIONS_H
#define LFHCAL_WAVEFORM_ANNOTATIONS_H

// Display only. AnalyseWaveForm supplies the exact WaveformMeasurement objects
// that it writes to the summary histograms; this code never extracts or fits.
#include "TileSpectra.h"
#include <TCanvas.h>
#include <TBox.h>
#include <TArrow.h>
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
#include <map>
#include <numeric>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
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
    // Never clamp an off-scale guide to a false measured amplitude.
    if(amplitude>=ymin && amplitude<=ymax)
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
enum class WaveformScale { Global, Layer, RobustLayer, IsolatedLayer };

inline int WaveformLayer(int cell) { return cell&63; }
using WaveformPosition=std::tuple<int,int,int>; // module, row, column
inline WaveformPosition WaveformCellPosition(int cell) {
  return {cell>>9,(cell>>8)&1,(cell>>6)&3};
}
struct WaveformLayout {
  bool geometry=false;
  std::vector<size_t> order;
  std::vector<int> layers;
  std::vector<WaveformPosition> positions;
};
inline WaveformLayout WaveformGridLayout(const std::vector<WaveformAnnotationCell>& cells) {
  WaveformLayout layout;layout.order.resize(cells.size());
  std::iota(layout.order.begin(),layout.order.end(),0);
  if(cells.size()!=64) return layout;
  std::map<std::pair<WaveformPosition,int>,size_t> addresses;
  std::set<WaveformPosition> positions;std::set<int> layers;
  for(size_t i=0;i<cells.size();++i) {
    if(cells[i].cell<0) return layout;
    const auto position=WaveformCellPosition(cells[i].cell);
    const int layer=WaveformLayer(cells[i].cell);
    if(!addresses.emplace(std::make_pair(position,layer),i).second) return layout;
    positions.insert(position);layers.insert(layer);
  }
  if(positions.size()!=8 || layers.size()!=8) return layout;
  std::vector<size_t> order;
  for(const auto& position:positions)for(int layer:layers) {
    const auto found=addresses.find({position,layer});
    if(found==addresses.end()) return layout;
    order.push_back(found->second);
  }
  layout.geometry=true;layout.order=order;
  layout.layers.assign(layers.begin(),layers.end());
  layout.positions.assign(positions.begin(),positions.end());
  return layout;
}

inline double WaveformQuantile(std::vector<double> values,double q) {
  std::sort(values.begin(),values.end());
  const double at=q*(values.size()-1);
  const size_t lo=static_cast<size_t>(std::floor(at)),hi=static_cast<size_t>(std::ceil(at));
  return values[lo]+(values[hi]-values[lo])*(at-lo);
}
inline std::set<int> WaveformHighPeakOutliers(const std::vector<WaveformAnnotationCell>& cells) {
  std::vector<double> peaks;
  for(const auto& c:cells)if(c.profile&&c.measurement.hasPeak)peaks.push_back(c.measurement.amplitude);
  std::set<int> result;
  if(peaks.size()<4) return result;
  const double q1=WaveformQuantile(peaks,.25),q3=WaveformQuantile(peaks,.75);
  const double fence=q3+1.5*(q3-q1);
  for(const auto& c:cells)
    if(c.profile&&c.measurement.hasPeak&&c.measurement.amplitude>fence)result.insert(c.cell);
  return result;
}

inline WaveformDisplayRange WaveformGridRange(const std::vector<WaveformAnnotationCell>& cells,
                                              const std::set<int>& omitUpper={}) {
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
      if(std::isfinite(y)) {
        // Retain every negative excursion, even in the robust display.
        range.ymin=std::min(range.ymin,y);
        if(!omitUpper.count(c.cell))range.ymax=std::max(range.ymax,y);
      }
    }
    if(c.measurement.hasPeak&&!omitUpper.count(c.cell))range.ymax=std::max(range.ymax,c.measurement.amplitude);
  }
  const double pad=.12*(range.ymax-range.ymin);
  range.ymax+=pad; if(range.ymin<0.)range.ymin-=pad;
  return range;
}

// Finite extrema across the displayed time window, independent of peak validity.
inline WaveformDisplayRange WaveformVisibleRange(const WaveformAnnotationCell& c,
                                                 WaveformDisplayRange frame,bool& finite) {
  frame.ymin=0.;frame.ymax=0.;finite=false;
  if(!c.profile)return frame;
  const auto* axis=c.profile->GetXaxis();
  int first=axis->FindFixBin(frame.xmin),last=axis->FindFixBin(frame.xmax);
  // Match TAxis::SetRangeUser: a bin starting exactly at xmax is not visible.
  if(axis->GetBinUpEdge(first)<=frame.xmin)++first;
  if(axis->GetBinLowEdge(last)>=frame.xmax)--last;
  first=std::max(1,first);last=std::min(c.profile->GetNbinsX(),last);
  for(int b=first;b<=last;++b) {
    const double y=c.profile->GetBinContent(b);
    if(std::isfinite(y)){finite=true;frame.ymin=std::min(frame.ymin,y);frame.ymax=std::max(frame.ymax,y);}
  }
  return frame;
}

struct WaveformScalePlan {
  WaveformDisplayRange global;
  std::map<int,WaveformDisplayRange> layers;
  std::set<int> highPeakOutliers;
  std::map<int,WaveformDisplayRange> independent;
  std::map<int,std::string> outlierReasons;
};
inline WaveformScalePlan WaveformGridScalePlan(const std::vector<WaveformAnnotationCell>& cells,
                                               WaveformScale scale) {
  WaveformScalePlan plan;plan.global=WaveformGridRange(cells);
  std::map<int,std::vector<WaveformAnnotationCell>> groups;
  for(const auto& c:cells)groups[WaveformLayer(c.cell)].push_back(c);
  for(const auto& group:groups) {
    auto outliers=(scale==WaveformScale::RobustLayer||scale==WaveformScale::IsolatedLayer)?WaveformHighPeakOutliers(group.second):std::set<int>{};
    plan.highPeakOutliers.insert(outliers.begin(),outliers.end());
    if(scale==WaveformScale::IsolatedLayer) {
      std::map<int,WaveformDisplayRange> visible;
      std::vector<double> upper,lower;
      for(const auto& c:group.second) {
        bool finite=false;const auto local=WaveformVisibleRange(c,plan.global,finite);
        if(finite){visible[c.cell]=local;upper.push_back(local.ymax);lower.push_back(-local.ymin);}
        if(outliers.count(c.cell))plan.outlierReasons[c.cell]="high peak";
      }
      if(upper.size()>=4) {
        const double upperFence=WaveformQuantile(upper,.75)+1.5*(WaveformQuantile(upper,.75)-WaveformQuantile(upper,.25));
        const double lowerFence=WaveformQuantile(lower,.75)+1.5*(WaveformQuantile(lower,.75)-WaveformQuantile(lower,.25));
        for(const auto& item:visible) {
          const bool high=item.second.ymax>upperFence,low=-item.second.ymin>lowerFence;
          if(high||low) {
            outliers.insert(item.first);
            auto& reason=plan.outlierReasons[item.first];
            if(!reason.empty())reason+="; ";
            reason+=high&&low?"visible +/- excursion":high?"visible + excursion":"visible - excursion";
          }
        }
      }
      std::vector<WaveformAnnotationCell> shared;
      for(const auto& c:group.second) {
        if(!outliers.count(c.cell)){shared.push_back(c);continue;}
        bool finite=false;auto local=WaveformVisibleRange(c,plan.global,finite);
        local.ymax=std::max(1.,local.ymax);
        if(c.measurement.hasPeak)local.ymax=std::max(local.ymax,c.measurement.amplitude);
        const double pad=.12*(local.ymax-local.ymin);
        local.ymax+=pad;if(local.ymin<0.)local.ymin-=pad;
        plan.independent[c.cell]=local;
      }
      plan.layers[group.first]=WaveformGridRange(shared);
    } else plan.layers[group.first]=WaveformGridRange(group.second,outliers);
  }
  return plan;
}

// Inspect the displayed clone, not the source profile or a new extraction.
// Late samples may clip under the existing 200 ns range-selection convention.
inline void DrawWaveformClipping(const TProfile& p,const WaveformMeasurement& m,
                                 double ymin,double ymax,bool rangeOutlier) {
  double low=ymax,high=ymin;
  for(int b=p.GetXaxis()->GetFirst();b<=p.GetXaxis()->GetLast();++b) {
    const double value=p.GetBinContent(b);
    if(std::isfinite(value)){low=std::min(low,value);high=std::max(high,value);}
  }
  const bool above=high>ymax,below=low<ymin;
  if(!above&&!below&&!rangeOutlier) return;
  const double x=gPad->GetUxmin()+.70*(gPad->GetUxmax()-gPad->GetUxmin());
  const double span=ymax-ymin;
  for(bool up:{false,true})if(up?above:below) {
    auto* arrow=new TArrow(x,up?ymax-.16*span:ymin+.16*span,
                          x,up?ymax-.02*span:ymin+.02*span,.012,"|>");
    arrow->SetBit(TObject::kCanDelete);arrow->SetLineColor(kViolet+2);arrow->SetFillColor(kViolet+2);
    arrow->SetUniqueID(TString(up?"waveform_clip_high":"waveform_clip_low").Hash());arrow->Draw();
  }
  if(above)WaveformText(.18,.52,Form("#uparrow %.3g",high),.075,kViolet+2);
  if(below)WaveformText(.18,.41,Form("#downarrow %.3g",low),.075,kViolet+2);
  if(m.hasPeak)WaveformText(.18,.30,Form("A=%.5g ADC",m.amplitude),.070,kViolet+2);
  if(rangeOutlier)WaveformText(.18,.19,"high peak: scale only",.065,kViolet+2);
}

inline void DrawWaveformGridPage(TCanvas& canvas,const std::vector<WaveformAnnotationCell>& cells,
                                int run,size_t first,bool annotated,bool normalized,
                                const TString& label="",WaveformScale scale=WaveformScale::Global,
                                int scanColor=kBlack,const TString& scanIdentifier="",const TString& settings="",int pageNumber=0,int pageCount=0,const TString& notice="") {
  ValidateWaveformAnnotationCells(cells);
  auto layout=WaveformGridLayout(cells);
  if(first!=0) {
    layout.geometry=false;
    std::iota(layout.order.begin(),layout.order.end(),0);
  }
  if(!layout.geometry)scale=WaveformScale::Global;
  const auto plan=WaveformGridScalePlan(cells,scale);
  const auto& range=plan.global;
  canvas.Clear();canvas.cd();
  auto* header=new TPad("waveform_header","",0.,.87,1.,1.);
  header->SetBit(TObject::kCanDelete);header->SetMargin(0,0,0,0);header->Draw();header->cd();
  const char* view=normalized?"normalized mean profiles":scale==WaveformScale::Layer?"absolute: shared scale per layer":
    scale==WaveformScale::IsolatedLayer?"absolute: shared layer axes; flagged cells use own ADC axes":
    scale==WaveformScale::RobustLayer?"absolute: robust scale per layer":"absolute: global full search-window range";
  if(!scanIdentifier.IsNull()) {
    auto* banner=new TBox(0.,.48,1.,1.);banner->SetBit(TObject::kCanDelete);
    banner->SetFillColor(scanColor);banner->SetLineColor(scanColor);banner->Draw();
    WaveformText(.015,.65,scanIdentifier,.30,kWhite);
    if(!notice.IsNull())WaveformText(.30,.84,notice,.12,kWhite);
    WaveformText(.30,.66,Form("Run %d | %s",run,label.Data()),.13,kWhite);
    WaveformText(.30,.51,settings,.12,kWhite);
    TLatex meta;meta.SetNDC();meta.SetTextFont(42);meta.SetTextColor(kWhite);
    meta.SetTextSize(.12);meta.SetTextAlign(31);
    meta.DrawLatex(.98,.84,pageCount>0?Form("%s | %d/%d",normalized?"Normalized":"Unnormalized",pageNumber,pageCount):
      normalized?"Normalized":"Unnormalized");
  } else WaveformText(.015,.75,Form("%s | Run %d",label.Data(),run),.21,scanColor);
  WaveformText(.015,.37,Form("%s | %s | cells %zu-%zu",view,annotated?"annotated":"unmarked",
    first+1,std::min(first+64,cells.size())),.115);
  WaveformText(.015,.20,annotated?
    "t (ns); vertical: #color[418]{left half-max}, #color[633]{peak time}, #color[617]{right half-max}; horizontal: #color[807]{peak amplitude}; arrows = clipped samples":
    "Same source profiles and axes as annotated companion; no measurement guides; arrows = clipped samples",.105);
  WaveformText(.015,.04,normalized?
    (scale==WaveformScale::IsolatedLayer?
    "Amplitude / cell peak; OUTLIER uses own normalized axis; layer Tukey flags: saved peak or visible +/- excursion (n >= 4); no data cuts":
    "Amplitude / cell peak; maximum through bin containing 200 ns; bin-center boundaries; no fit"):
    scale==WaveformScale::IsolatedLayer?
    "ADC above pedestal; OUTLIER: saved peak or visible +/- excursion > layer Q3 + 1.5 IQR (n >= 4); own axis; no data cuts":
    scale==WaveformScale::RobustLayer?
    "ADC above pedestal; peaks > layer Q3 + 1.5 IQR do not set upper axis (n >= 4); negatives retained; no data cuts":
    "ADC above pedestal; range uses bins through 200 ns; columns = cell-ID layer index, not physical depth; rows = module/row/column",.10);
  canvas.cd();
  const double left=layout.geometry?.09:0.,top=layout.geometry?.82:.86;
  if(layout.geometry) {
    for(size_t col=0;col<8;++col)
      WaveformText(left+(1.-left)*(col+.28)/8.,.835,Form("Layer %d",layout.layers[col]),.018);
    for(size_t row=0;row<8;++row) {
      const auto& pos=layout.positions[row];const double y=top*(1.-(row+.5)/8.);
      WaveformText(.008,y+.010,Form("Module %d",std::get<0>(pos)),.014);
      WaveformText(.008,y-.010,Form("r%d  c%d",std::get<1>(pos),std::get<2>(pos)),.014);
    }
  }
  auto* grid=new TPad("waveform_grid","",left,0.,1.,top);
  grid->SetBit(TObject::kCanDelete);grid->Draw();grid->Divide(8,8,.0008,.0008);
  for(size_t i=first;i<std::min(first+64,cells.size());++i) {
    grid->cd(static_cast<int>(i-first)+1);
    gPad->SetMargin(.15,.025,.15,.025);gPad->SetTicks(1,1);
    const auto& c=cells[layout.order[i]];const auto& m=c.measurement;
    const bool independent=plan.independent.count(c.cell);
    if(independent){gPad->SetFrameLineColor(kViolet+2);gPad->SetFrameLineWidth(2);}
    const auto& yrange=independent?plan.independent.at(c.cell):
      scale==WaveformScale::Global?range:plan.layers.at(WaveformLayer(c.cell));
    const double ymin=normalized?(independent&&m.hasPeak?std::min(-.08,yrange.ymin/m.amplitude):-.08):yrange.ymin,
      ymax=normalized?(independent&&m.hasPeak?std::max(1.12,yrange.ymax/m.amplitude):1.12):yrange.ymax;
    if(!c.profile || (normalized&&!m.hasPeak)) {
      WaveformText(.20,.80,Form("%d",c.cell),.13);
      WaveformText(.19,.50,c.profile?"no positive peak":"missing profile",.09,kRed+1);
      if(independent)WaveformText(.18,.32,"OUTLIER (absolute)",.08,kViolet+2);
      continue;
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
    DrawWaveformClipping(*p,m,ymin,ymax,!normalized&&!independent&&plan.highPeakOutliers.count(c.cell));
    if(independent) {
      WaveformText(.18,.56,"OUTLIER",.09,kViolet+2);
      WaveformText(.18,.20,plan.outlierReasons.at(c.cell).c_str(),.055,kViolet+2);
      WaveformText(.18,.44,normalized?"own A/peak axis":"own ADC axis",.08,kViolet+2);
      if(m.hasPeak)WaveformText(.18,.32,Form("A=%.5g ADC",m.amplitude),.075,kViolet+2);
    } else if(normalized&&plan.highPeakOutliers.count(c.cell))
      WaveformText(.18,.57,"high absolute peak",.065,kViolet+2);
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
    for(size_t first=0;first<cells.size();first+=64) {
      // Keep the original absolute/normalized page pair first; append audit views.
      DrawWaveformGridPage(canvas,cells,run,first,marked,false,label,WaveformScale::Layer);canvas.Print(pdf.c_str());
      DrawWaveformGridPage(canvas,cells,run,first,marked,true,label);canvas.Print(pdf.c_str());
      DrawWaveformGridPage(canvas,cells,run,first,marked,false,label,WaveformScale::RobustLayer);canvas.Print(pdf.c_str());
      DrawWaveformGridPage(canvas,cells,run,first,marked,false,label);canvas.Print(pdf.c_str());
    }
    canvas.Print((pdf+"]").c_str());
    Long_t id=0,size=0,flags=0,mtime=0;
    if(gSystem->GetPathInfo(pdf.c_str(),&id,&size,&flags,&mtime)!=0||size==0)
      throw std::runtime_error("failed writing annotation PDF: "+pdf);
  }
}
} // namespace lfhcal
#endif
