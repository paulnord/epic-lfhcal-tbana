#! /bin/bash

function Calib()
{
	runNrFile='../configs/DataTakingDB_202409_CAEN.csv'
	echo "===================================================================="
	echo "option:  $1"
	echo "calib File:  $2"
	echo "raw data path:  $3"
	echo "out data path:  $4"
	echo "additional Name/runNr:  $5"
	echo "Plots Directory-Base: $6"
	echo "===================================================================="
	if [ $1 == "trigg" ]; then
		time ./DataPrep -f -d 1 -T $2 -i $3/raw_$5.root -o $3/rawWithLocTrigg_$5.root 
	elif [ $1 == "calibNoTrigg" ]; then
		time ./DataPrep -t -e -f -d 1 -a -C $2 -i $3/rawWithLocTrigg_$5.root -o $4/calibrated_Run_$5.root -O $6$5 -r $runNrFile
	elif [ $1 == "full" ]; then
		time ./DataPrep -e -f -d 1 -a -C $2 -i $3/raw_$5.root -o $4/calibrated_Run_$5.root -O $6$5 -r $runNrFile
	fi
}

dataDirRaw=""
dataDirOut=""
dataDirCal=""
if [ $1 = "fbock" ]; then 
	dataDirCal=/home/fbock/EIC/Analysis/LFHCalTB2024/CAENdata
	dataDirRaw=/media/fbock/Samsung_T5/LFHCAL_TB/202408_PST09/CAENdata/MuonRuns
	dataDirRawE=/media/fbock/Samsung_T5/LFHCAL_TB/202408_PST09/CAENdata/ElectronRuns
	dataDirRawH=/media/fbock/Samsung_T5/LFHCAL_TB/202408_PST09/CAENdata/HadronRuns
	dataDirOut=/home/fbock/EIC/Analysis/LFHCalTB2024/CAENdata/MuonRuns
	dataDirOutE=/home/fbock/EIC/Analysis/LFHCalTB2024/CAENdata/ElectronRuns
	dataDirOutH=/home/fbock/EIC/Analysis/LFHCalTB2024/CAENdata/HadronRuns
elif [ $1 = "eglimos" ]; then 
	dataDirCal=/home/ewa/EIC/test_beam2024/fullScanC/Output/MuonRuns
	dataDirRaw=/home/ewa/EIC/test_beam2024/fullScanC
	dataDirRawE=/home/ewa/EIC/test_beam2024/fullScanC
	dataDirRawH=/home/ewa/EIC/test_beam2024/fullScanC
	dataDirOut=/home/ewa/EIC/test_beam2024/fullScanC/Output/MuonRuns
	dataDirOutE=/home/ewa/EIC/test_beam2024/fullScanC/Output/ElectronRuns
	dataDirOutH=/home/ewa/EIC/test_beam2024/fullScanC/Output/HadronRuns
else
	echo "Please select a known user name, otherwise I don't know where the data is"
	exit
fi

# apply calibration
if [ $2 == "ScanA" ]; then
	calibFile1=$dataDirOut/rawPedAndMuonWBCImp4th_muonScanA1_45V.root
	calibFile2=$dataDirOut/rawPedAndMuonWBCImp3rd_muonScanA2_45V.root
	echo "running calibrate for 45V runs, campaing A1"
	
	#muon runs
	muonScanA_45V='244 250 282 283'
	pedScanA_45V='271 277'
	Calib $3 $calibFile1 $dataDirRaw $dataDirOut muonScanA1_45V ../PlotsMuonCalibrated_2024/Run_
	Calib $3 $calibFile2 $dataDirRaw $dataDirOut muonScanA2_45V ../PlotsMuonCalibrated_2024/Run_
	
	#electron runs
	runs='251 252 254 257 258 ' 
	for runNr in $runs; do 
		Calib $3 $calibFile1 $dataDirRawE $dataDirOutE $runNr ../PlotsElectronCalibrated_2024/Run_
	done;
	
	#hadron runs
	runs='261 264 265 269 270 272 274 275 ' 
	for runNr in $runs; do 
		Calib $3 $calibFile1 $dataDirRawH $dataDirOutH $runNr ../PlotsHadronCalibrated_2024/Run_
	done;
fi

if [ $2 == "ScanB" ]; then
	echo "running calibrate for 42V runs, campaign B"
	calibFile1=$dataDirCal/CalibFinal_muonScanB1_42V.root 
	calibFile2=$dataDirCal/CalibFinal_muonScanB2_42V.root

	#muon runs
	muonScanB1_42V='331 322'
	pedScanB1_42V='332'
	muonScanB2_42V='370 371 374'
	pedScanB2_42V='369'
# 	Calib $3 $calibFile1 $dataDirRaw $dataDirOut muonScanB1_42V ../PlotsMuonCalibrated_2024/Run_
# 	Calib $3 $calibFile2 $dataDirRaw $dataDirOut muonScanB2_42V ../PlotsMuonCalibrated_2024/Run_
	
# 	#electron runs
# 	runs='333 334 336 337 338 ' 
	runs='338 ' 
	for runNr in $runs; do 
		Calib $3 $calibFile1 $dataDirRawE $dataDirOutE $runNr ../PlotsElectronCalibrated_2024/Run_
	done;
# 	
# 	#hadron runs
# 	runs='340 349 346 350 357 360 362 367 368' 
# 	for runNr in $runs; do 
# 		Calib $3 $calibFile1 $dataDirRawH $dataDirOutH $runNr ../PlotsHadronCalibrated_2024/Run_
# 	done;
fi

if [ $2 == "ScanC" ]; then
	echo "running calibrate for 43.5V runs, campaign C"
	calibFile1=$dataDirCal/rawPedAndMuonWBCImp_muonScanC1_43_5V.root 
	calibFile2=$dataDirCal/rawPedAndMuonWBCImp_muonScanC2_43_5V.root

	#muon runs
	muonScanC1_43V='376 375'
	pedScanC1_43V='377'
	muonScanC2_43V='405 410 408'
	pedScanC2_43V='404'
# 	Calib $3 $calibFile1 $dataDirRaw $dataDirOut muonScanB1_42V ../PlotsMuonCalibrated_2024/Run_
# 	Calib $3 $calibFile2 $dataDirRaw $dataDirOut muonScanB2_42V ../PlotsMuonCalibrated_2024/Run_
	
# 	#electron runs
	runs='379 380 381 384 387' 
	for runNr in $runs; do 
		Calib $3 $calibFile1 $dataDirRawE $dataDirOutE $runNr ../PlotsElectronCalibrated_2024/Run_
	done;
# 	
# 	#hadron runs
	# runs='397 398 399 401' 
	# for runNr in $runs; do 
	# 	Calib $3 $calibFile1 $dataDirRawH $dataDirOutH $runNr ../PlotsHadronCalibrated_2024/Run_
	# done;
fi

