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
	echo "Plots additional name: $7"
	echo "===================================================================="
	if [ $1 == "transfer" ]; then
		time ./DataPrep -d 1 -e -a -f -P $2 -i $3/raw_$5.root  -o $3/rawWithCalib_$5.root -O $6/PlotsFullCalibTransferBC_2024/Run_$5 -r $runNrFile
	elif [ $1 == "trigg" ]; then
		time ./DataPrep -f -d 1 -T $2 -i $3/raw_$5.root -o $3/rawWithLocTrigg_$5.root 
	elif [ $1 == "calibNoTrigg" ]; then
		time ./DataPrep -t -e -f -d 1 -a -C $2 -i $3/rawWithLocTrigg_$5.root -o $4/calibrated_Run_$5.root -O $6/$7$5 -r $runNrFile
	elif [ $1 == "full" ]; then
		time ./DataPrep -e -f -d 1 -a -C $2 -i $3/raw_$5.root -o $4/calibrated_Run_$5.root -O $6/$7$5 -r $runNrFile
	fi
}

dataDirCal=""
if [ $1 = "fbock" ]; then 
	dataDirCal=/home/fbock/EIC/Analysis/LFHCalTB2024/CAENdata
	dataDirIn=/media/fbock/Samsung_T5/LFHCAL_TB/202408_PST09/CAENdata/MuonRuns
	dataDirInE=/media/fbock/Samsung_T5/LFHCAL_TB/202408_PST09/CAENdata/ElectronRuns
	dataDirInH=/media/fbock/Samsung_T5/LFHCAL_TB/202408_PST09/CAENdata/HadronRuns
	dataDirOut=/home/fbock/EIC/Analysis/LFHCalTB2024/CAENdata/MuonRuns
	dataDirOutE=/home/fbock/EIC/Analysis/LFHCalTB2024/CAENdata/ElectronRuns
	dataDirOutH=/home/fbock/EIC/Analysis/LFHCalTB2024/CAENdata/HadronRuns
	PlotBaseDir=..
elif [ $1 = "fbockExt" ]; then 
	dataDirCal=/home/fbock/EIC/Analysis/LFHCalTB2024/CAENdata
	dataDirBase=/media/fbock/Samsung_T5/LFHCAL_TB/202408_PST09/CAENdata
	dataDirIn=$dataDirBase/MuonRuns
	dataDirInE=$dataDirBase/ElectronRuns
	dataDirInH=$dataDirBase/HadronRuns
	dataDirOut=$dataDirIn
	dataDirOutE=$dataDirInE
	dataDirOutH=$dataDirInH
	PlotBaseDir=..
elif [ $1 = "fbockExt2" ]; then 
	dataDirCal=/media/fbock/T7/202408_PST09/CAENData
	dataDirBase=/media/fbock/T7/202408_PST09/CAENData
	dataDirIn=$dataDirBase/MuonRuns
	dataDirInE=$dataDirBase/ElectronRuns
	dataDirInH=$dataDirBase/HadronRuns
	dataDirOut=$dataDirIn
	dataDirOutE=$dataDirInE
	dataDirOutH=$dataDirInH
	PlotBaseDir=/media/fbock/T7/202408_PST09
elif [ $1 = "eglimos" ]; then 
	dataDirCal=/home/ewa/EIC/test_beam2024/fullScanC/Output/MuonRuns
	dataDirIn=/home/ewa/EIC/test_beam2024/fullScanC
	dataDirInE=/home/ewa/EIC/test_beam2024/fullScanC
	dataDirInH=/home/ewa/EIC/test_beam2024/fullScanC
	dataDirOut=/home/ewa/EIC/test_beam2024/fullScanC/Output/MuonRuns
	dataDirOutE=/home/ewa/EIC/test_beam2024/fullScanC/Output/ElectronRuns
	dataDirOutH=/home/ewa/EIC/test_beam2024/fullScanC/Output/HadronRuns
	PlotBaseDir=..
else
	echo "Please select a known user name, otherwise I don't know where the data is"
	exit
fi

# apply calibration
if [ $2 == "ScanA" ]; then
	calibFile1=$dataDirCal/calib_muonScanA1.root
	calibFile2=$dataDirCal/calib_muonScanA1.root
	echo "running calibrate for 45V runs, campaing A1"
	
	#muon runs
	muonScanA_45V='244 250 282 283'
	pedScanA_45V='271 277'
	Calib $3 $calibFile1 $dataDirIn $dataDirOut muonScanA1_45V $PlotBaseDir PlotsMuonCalibrated_2024/Run_
	Calib $3 $calibFile2 $dataDirIn $dataDirOut muonScanA2_45V $PlotBaseDir PlotsMuonCalibrated_2024/Run_
	
 # 	electron runs
	runs='251 252 254 257 258 ' 
 # 	runs=' 251 258' 
	for runNr in $runs; do 
		Calib $3 $calibFile1 $dataDirInE $dataDirOutE $runNr $PlotBaseDir PlotsElectronCalibrated_2024/Run_
	done;
	
	#hadron runs
	runs='261 264 265 269 270 272 274 275 ' 
	for runNr in $runs; do 
		Calib $3 $calibFile1 $dataDirInH $dataDirOutH $runNr $PlotBaseDir PlotsHadronCalibrated_2024/Run_
	done;
elif [ $2 == "ScanB" ]; then
	echo "running calibrate for 42V runs, campaign B"
	calibFile1=$dataDirCal/CalibFinal_muonScanB1_42V.root 
	calibFile2=$dataDirCal/CalibFinal_muonScanB2_42V.root

	#muon runs
	muonScanB1_42V='331 322'
	pedScanB1_42V='332'
	muonScanB2_42V='370 371 374'
	pedScanB2_42V='369'
# 	Calib $3 $calibFile1 $dataDirIn $dataDirOut muonScanB1_42V $PlotBaseDir PlotsMuonCalibrated_2024/Run_
	Calib $3 $calibFile2 $dataDirIn $dataDirOut muonScanB2_42V $PlotBaseDir PlotsMuonCalibrated_2024/Run_
	
# 	#electron runs
# 	runs='333 334 336 337 338 ' 
# 	runs='338 ' 
# 	for runNr in $runs; do 
# 		Calib $3 $calibFile1 $dataDirInE $dataDirOutE $runNr $PlotBaseDir PlotsElectronCalibrated_2024/Run_
# 	done;
# 	
# 	#hadron runs
# 	runs='340 349 346 350 357 360 362 367 368' 
# 	for runNr in $runs; do 
# 		Calib $3 $calibFile1 $dataDirInH $dataDirOutH $runNr $PlotBaseDir PlotsHadronCalibrated_2024/Run_
# 	done;

elif [ $2 == "ScanC" ]; then
	echo "running calibrate for 43.5V runs, campaign C"
	if [ $1 == "fbock" ] || [ $1 == "fbockExt" ]; then 
		calibFile1=$dataDirCal/CalibFinal_muonScanC1_43_5V.root
		calibFile2=$dataDirCal/CalibFinal_muonScanC2_43_5V.root
	else 
		calibFile1=$dataDirCal/rawPedAndMuonWBCImp_muonScanC1_43_5V.root 
		calibFile2=$dataDirCal/rawPedAndMuonWBCImp_muonScanC2_43_5V.root
	fi
	#muon runs
# 	muonScanC1_43V='376 375'
# 	pedScanC1_43V='377'
# 	muonScanC2_43V='405 410 408'
# 	pedScanC2_43V='404'
# 	Calib $3 $calibFile1 $dataDirIn $dataDirOut muonScanC1_43_5V $PlotBaseDir PlotsMuonCalibrated_2024/Run_
# 	Calib $3 $calibFile2 $dataDirIn $dataDirOut muonScanC2_43_5V $PlotBaseDir PlotsMuonCalibrated_2024/Run_
# 	
# # 	#electron runs
	runs='379 380 381 384 387' 
# # 	runs='380' 
	for runNr in $runs; do 
		Calib $3 $calibFile1 $dataDirInE $dataDirOutE $runNr $PlotBaseDir PlotsElectronCalibrated_2024/Run_
	done;
# 	
# 	hadron runs
# 	runs='397 398 399 401' 
# 	runs='390 392 393 394 397 398 399 401' 
# 	runs='397 398 399 401' 
# 	runs='398 399 401' 
# 	for runNr in $runs; do 
# 		Calib $3 $calibFile1 $dataDirInH $dataDirOutH $runNr $PlotBaseDir PlotsHadronCalibrated_2024/Run_
# 	done;
elif [ $2 == "ScanD" ]; then
# 	calibFile1=$dataDirCal/CalibFinal_muonScanB1_42V.root 
	calibFile2=$dataDirCal/CalibFinal_muonScanD2_45V.root
	echo "running calibrate for 45V runs, campaing A1"
	
	#muon runs
	muonScanD1_45V='412 417'		# these runs are messed up don't analyze
	pedScanD1_45V='420'
	# 29.3K events
	muonScanD2_45V='460 456 457'
	pedScanD2_45V='454'
	Calib $3 $calibFile2 $dataDirIn $dataDirOut muonScanD2_45V $PlotBaseDir PlotsMuonCalibrated_2024/Run_
	
# 	electron runs
	runs='421 422 429 430 432 ' 
	for runNr in $runs; do 
		Calib $3 $calibFile2 $dataDirInE $dataDirOutE $runNr $PlotBaseDir PlotsElectronCalibrated_2024/Run_
	done;
	
	#hadron runs
	runs='434 437 439 441 444 445 449 452 ' 
# 	runs='437 439 441 444 445 449 452 ' 
# 	runs='441 444 445 449 452 ' 
	for runNr in $runs; do 
		Calib $3 $calibFile2 $dataDirInH $dataDirOutH $runNr $PlotBaseDir PlotsHadronCalibrated_2024/Run_
	done;
fi

