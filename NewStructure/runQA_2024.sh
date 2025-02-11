#! /bin/bash
dataDirRaw=""
dataDirOut=""
if [ $1 = "fbock" ]; then 
	dataDirRaw=/media/fbock/Samsung_T5/LFHCAL_TB/202408_PST09/CAENdata/MuonRuns
	dataDirRawE=/media/fbock/Samsung_T5/LFHCAL_TB/202408_PST09/CAENdata/ElectronRuns
	dataDirRawH=/media/fbock/Samsung_T5/LFHCAL_TB/202408_PST09/CAENdata/HadronRuns
	dataDirOut=/home/fbock/EIC/Analysis/LFHCalTB2024/CAENdata/MuonRuns
	dataDirOutE=/home/fbock/EIC/Analysis/LFHCalTB2024/CAENdata/ElectronRuns
	dataDirOutH=/home/fbock/EIC/Analysis/LFHCalTB2024/CAENdata/HadronRuns
elif [ $1 = "eglimos" ]; then 
	dataDirOut=/home/ewa/EIC/test_beam2024/fullScanC/Output/MuonRuns
	dataDirOutE=/home/ewa/EIC/test_beam2024/fullScanC/Output/ElectronRuns
	dataDirOutH=/home/ewa/EIC/test_beam2024/fullScanC/Output/HadronRuns
else
	echo "Please select a known user name, otherwise I don't know where the data is"
	exit
fi

runNrFile='../configs/DataTakingDB_202409_CAEN.csv'
muonScanA_45V='244 250 282 283'
pedScanA_45V='271 277'
if [ $2 == "ScanA" ]; then
	# 192K events
	echo "running calibrate for 45V runs, campaing A1"
	runs='251 252 254 257 258 ' 
#   runs='258 ' 
	for runNr in $runs; do 
    time ./DataAna -d 1 -Q -i $dataDirOutE/calibrated_Run_$runNr.root -O $dataDirOutE/QAHists_Run_$runNr.root -a -f -r $runNrFile -P ../QAPlots/Run_$runNr
	done;
	runs='261 264 265 269 270 272 274 275 ' 
	for runNr in $runs; do 
    time ./DataAna -d 1 -Q -i $dataDirOutH/calibrated_Run_$runNr.root -O $dataDirOutH/QAHists_Run_$runNr.root -a -f -r $runNrFile -P ../QAPlots/Run_$runNr
	done;
  time ./DataAna -d 1 -Q -i $dataDirOut/calibratedMuon_muonScanA1_45V.root -O $dataDirOutE/QAHists_Run_muonScanA1_45V.root -a -f -r $runNrFile -P ../QAPlots/muonScanA1_45V
  time ./DataAna -d 1 -Q -i $dataDirOut/calibratedMuon_muonScanA2_45V.root -O $dataDirOutE/QAHists_Run_muonScanA2_45V.root -a -f -r $runNrFile -P ../QAPlots/muonScanA2_45V
fi

if [ $2 == "ScanC" ]; then
	echo "running calibrate for 43.5V runs, campaign C"
	
# 	#electron runs
	# runs='379 380 381 384 387' 
	runs='380' 
	for runNr in $runs; do 
    	time ./DataAna -d 1 -Q -i $dataDirOutE/calibrated_Run_$runNr.root -O $dataDirOutE/QAHists_Run_$runNr.root -a -f -r $runNrFile -P ../QAPlots/Run_$runNr
	done;
# 	
# 	#hadron runs
	# runs='397 398 399 401' 
	# for runNr in $runs; do 
	# 	Calib $3 $calibFile1 $dataDirRawH $dataDirOutH $runNr ../PlotsHadronCalibrated_2024/Run_
	# done;
fi

