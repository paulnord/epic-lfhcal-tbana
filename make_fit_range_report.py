#!/usr/bin/env python3
"""Build the concise review PDF from the completed frozen-histogram study."""
import json
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from matplotlib.font_manager import findfont,FontProperties
import argparse

pdfmetrics.registerFont(TTFont('StudySans',findfont(FontProperties(family='DejaVu Sans'))))
pdfmetrics.registerFont(TTFont('StudySans-Bold',findfont(FontProperties(family='DejaVu Sans',weight='bold'))))
pdfmetrics.registerFontFamily('StudySans',normal='StudySans',bold='StudySans-Bold',italic='StudySans',boldItalic='StudySans-Bold')

ap=argparse.ArgumentParser();ap.add_argument('--study',type=Path,required=True);args=ap.parse_args()
p=args.study.resolve();out=p/'output';s=json.loads((out/'summary.json').read_text());rows=json.loads((out/'all-fit-results.json').read_text())
prod=list(map(json.loads,(p/'production-candidate/production_candidate.jsonl').read_text().splitlines()));assert len(prod)==40
by={(r['dataset'],r['cell'],r['source']):r for r in s};fit={r['key']:r for r in rows}
validation=[]
for r in prod:
 k=f"{r['dataset']}:{r['cell_id']}:{r['histogram_source']}:valley_2.0";v=fit[k]
 validation.append(dict(key=r['key'],H=r['smooth_peak'][0],relative_H_change=(r['smooth_peak'][0]/v['smooth_peak'][0]-1),accepted=r['accepted_by_production_checks'],status=r['status'],calls=r['calls']))
(out/'production-validation.json').write_text(json.dumps(validation,indent=2)+'\n')
max_shift=max(abs(r['relative_H_change']) for r in validation)
styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='Main',fontName='StudySans',fontSize=9.5,leading=13,spaceAfter=8))
styles.add(ParagraphStyle(name='SmallNote',fontName='StudySans',fontSize=7.6,leading=10,spaceAfter=6,textColor=colors.HexColor('#44515e')))
styles['Title'].fontName='StudySans-Bold';styles['Title'].fontSize=21;styles['Title'].leading=26;styles['Title'].alignment=TA_LEFT
styles['Heading2'].fontName='StudySans-Bold';styles['Heading2'].fontSize=12;styles['Heading2'].spaceBefore=10;styles['Heading2'].spaceAfter=7
story=[]
def para(text,style='Main'):story.append(Paragraph(text,styles[style]))
def table(data,widths):
 t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([
 ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5eef5')),('FONTNAME',(0,0),(-1,0),'StudySans-Bold'),
 ('FONTNAME',(0,1),(-1,-1),'StudySans'),('FONTSIZE',(0,0),(-1,-1),8.0),('LEADING',(0,0),(-1,-1),11),
 ('BOTTOMPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),
 ('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#8a9eac')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f7f9')])]))
 story.append(t);story.append(Spacer(1,9))
para('LFHCal: fit the peak,\nnot the low-ADC component'.replace('\n','<br/>'),'Title')
para('Frozen-histogram range study | B1 R5, B2 R8, E1 R5, E2 R5 | 1 October 2026','SmallNote')
para('<b>A smoothed-valley lower boundary is a promising candidate.</b> It isolates the higher B2 peak in cells 263, 775 and 1478, sharpens cell 1991, and makes the E1 cell 1223 fit converge. A universal higher cutoff is unsafe: it can cut through otherwise good spectra and yield a peak outside the fitted interval.')
para('Main changes on adaptive-selected spectra','Heading2')
data=[['Case','Lower edge (ADC)','H: old / new','Gaussian sigma: old / new']]
for ds,cell in [('b2',263),('b2',775),('b2',1478),('b2',1991),('e1',1223)]:
 r=by[ds,cell,'adaptive'];old=f"{r['baseline_H']:.2f}"+('*' if not r['old_accepted'] else '')
 data.append([f'{ds.upper()} / {cell}',f"{r['old_lower']:.1f}  /  {r['new_lower']:.1f}",f"{old}  /  {r['candidate_H']:.2f}",f"{r['old_sigma']:.2f}  /  {r['new_sigma']:.2f}"])
table(data,[75,125,125,175])
para('* An unsuccessful local baseline attempt, not a saved calibration. H is the peak of the continuous convolved model, not its Landau MPV. All values are ADC units. Both columns use the adaptive evaluator on the same histogram.','SmallNote')
para('What remains unresolved','Heading2')
para('<b>B2 cell 67:</b> no prominent peak in the expected search band. The procedure proposes no new range. Its existing low, broad solution remains questionable.<br/><b>B2 cell 706:</b> almost no gain; its valley is not stable under the smoothing check.<br/><b>E2 cell 1344:</b> the legacy wiggles are numerical, but smoothing the evaluator does not remove the data\'s comb-like structure. No resolved valley is found by this rule.')
para('Recommendation','Heading2')
para('Keep the adaptive evaluator. Trial one explicit valley-based range rule and flag ambiguous spectra. Validate it on additional cells before changing a full calibration chain. No production calibration or campaign was modified in this study.')
story.append(PageBreak())
para('Controls and evidence','Title')
para('All eight B1 cells remain fitted. The cleaner controls change little, while several broader B1 spectra shift by a few percent. That is useful evidence of range sensitivity, not proof that the new calibration is correct.')
data=[['B1 cell','H: original window','H: valley window','Change']]
for cell in (67,263,706,775,1478,1538,1991,2051):
 r=by['b1',cell,'adaptive'];data.append([str(cell),f"{r['baseline_H']:.3f}",f"{r['candidate_H']:.3f}",f"{r['change_percent']:+.2f}%"])
table(data,[75,145,145,135])
para('E1 cell 640 and E2 cell 68 retain their original ranges and results on adaptive-selected input. B2 control cells 1538 and 2051 move by -1.86% and -0.51%. Varying the smoothing width from 1.5 to 3 original bins changes H by at most 1.24% across the 40 histogram records; this is a sensitivity check, not an uncertainty estimate.')
para('Comparison on a fixed set of peak bins','Heading2')
para('For each identifiable peak, all variants are also evaluated over the same interval: 0.7 to 1.6 times the observed smoothed peak position. This avoids comparing fit statistics from different windows. The metric below is Poisson deviance per bin, not a reduced chi-square or a p-value.')
data=[['Case','Original window','Valley window']]
for ds,cell in [('b2',263),('b2',775),('b2',1478),('b2',1991),('e1',1223),('b2',706)]:
 r=by[ds,cell,'adaptive'];data.append([f'{ds.upper()} / {cell}',f"{r['core_old']['deviance_per_bin']:.2f}",f"{r['core_new']['deviance_per_bin']:.2f}"])
table(data,[110,195,195])
para('The major B2 examples improve substantially in their peak region. Cell 706 slightly worsens. Absolute deviances remain large in many spectra because a smooth single-component model does not describe the bin-to-bin structure. These are deliberately selected examples, not an unbiased or held-out validation sample.','SmallNote')
story.append(PageBreak())
para('Exactly what was tested','Title')
para('<b>Input verification.</b> All 493 copied context/source files match their recorded hashes, and the ROOT file matches its SHA-256. The 40 spectra cover 20 dataset/cell cases, each with legacy-selected and adaptive-selected counts. No rebinning, event selection or normalization was performed.')
para('<b>Baseline reproduction.</b> The archived C++ evaluators were compiled and fitted with ROOT. Local ROOT is 6.40.00; the source campaigns used 6.40.04. All 37 saved fits reproduce within 1.6 x 10<super>-7</super> in parameter difference scaled by max(|parameter|, 1). The same three cases are rejected: B2/263 adaptive and E1/640 legacy reach the Landau-width limit; E1/1223 adaptive fails minimization.')
para('<b>Controlled tests.</b> 80 baseline/error checks; 320 lower-bound trials; 120 valley trials with three smoothing widths. Original seeds, parameter limits, upper boundary and Poisson-likelihood objective are fixed within the range comparison. Each trial starts independently. The fit uses QRLMN0S and Minuit / MigradImproved, with the IMPROVE seed fixed at 12345. The scans use 10,000 calls and 1,000 iterations; baseline reproduction uses 1,000 calls and 100 iterations.')
para(f'<b>Production-style cross-check.</b> Another 40 fits restore the original 1,000-call/100-iteration limits and recompute the area seed and its upper limit from the proposed window, as production would. {sum(r["accepted"] for r in validation)}/40 pass the existing numerical checks; the largest change in H from the controlled valley trial is {100*max_shift:.4f}%. Passing these checks does not establish physical validity, especially for flagged spectra.')
para('Candidate rule, applied before fitting','Heading2')
para('1. Smooth a temporary copy of the counts with a Gaussian of sigma = 2 original bins.<br/>2. Find the most prominent peak between max(3 pedestal sigmas, 0.5 dataset-average MIP scale) and 2.5 dataset-average MIP scale. Require prominence at least 20% of the largest smoothed count in that band; separate detected peaks by at least 8 bins.<br/>3. Find the smoothed minimum between 3 pedestal sigmas and 0.8 times that peak position. Reject a boundary minimum or a valley above half the peak height.<br/>4. Raise the original lower fit edge to that valley if necessary. Fit the original unsmoothed histogram. If no suitable peak/valley exists, retain the baseline for comparison and flag the case.')
para('Empty-bin error bug','Heading2')
para('All 27,891 nonfinite error entries belong to empty regular bins. The source computes n sqrt(0.15<super>2</super> + (error/n)<super>2</super>), which gives 0/0 at n=0. The finite equivalent is hypot(error, 0.15 n). Replacing only those NaNs with zero leaves fit parameters unchanged to about 1.6 x 10<super>-7</super>. A patch is provided separately; it has not been applied to production.')
para('The existing L option fits a Poisson likelihood, so the stored 15% error inflation is not a 15% systematic model in the fit objective. The model and residual structure still need physical assessment. A simple before/after ROOT rendering did not reproduce the earlier giant vertical lines, so their cause is not established.','SmallNote')
para('Reference: ROOT TH1 fitting documentation, https://root.cern.ch/doc/v640/classTH1.html. Source evidence: archived Analyses.cc (error calculation and average-scale caller), TileSpectra.cc (range, seeds, limits, fit options), AdaptiveLangau.h (continuous evaluator). Full records and source hashes accompany the results.','SmallNote')
def footer(canvas,doc):
 canvas.setFont('StudySans',7.5);canvas.setFillColor(colors.HexColor('#526271'));canvas.drawString(48,27,'LFHCal frozen-histogram study | Research candidate, no production changes');canvas.drawRightString(564,27,str(doc.page))
doc=SimpleDocTemplate(str(out/'lfhcal-fit-range-report.pdf'),pagesize=letter,rightMargin=48,leftMargin=48,topMargin=42,bottomMargin=42,title='LFHCal frozen-histogram fit-range study',author='Paul Nord / Codex')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print('Report written. Production H shift:',100*max_shift,'%')
