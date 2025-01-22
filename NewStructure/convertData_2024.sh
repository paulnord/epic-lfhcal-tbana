#! /bin/bash

dataDir=""
if [ $1 = "fbock" ]; then 
	dataDir=/media/fbock/Samsung_T5/LFHCAL_TB/202408_PST09/CAENdata/MuonRuns
	dataRaw=/home/fbock/EIC/Analysis/LFHCalTB2024/CAENdata/MuonRuns
elif [ $1 = "fbockExt" ]; then 
	dataDir=/media/fbock/T7/CAEN_Sept24_TB_PS
	dataRaw=/media/fbock/Samsung_T5/LFHCAL_TB/202408_PST09/CAENdata
elif [ $1 = "eglimos" ]; then 
	dataDir=/home/ewa/EIC/test_beam2024/fullScanC
	dataRaw=/home/ewa/EIC/test_beam2024/fullScanC
else
	echo "Please select a known user name, otherwise I don't know where the data is"
	exit
fi

if [ $2 == "single" ]; then 
#   runs='244'
#   runs='271'
  runs='492 505'
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
elif [ $2 == "electronsA" ]; then 
  runs='251 252 254 257 258 ' 
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/ElectronRuns/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
elif [ $2 == "electronsB" ]; then 
  runs='333 334 336 337 338 ' 
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/ElectronRuns/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
elif [ $2 == "electronsC" ]; then 
  runs='379 380 381 384 387 ' 
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/electronRuns/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
elif [ $2 == "electronsD" ]; then 
  runs='421 422 429 430 432 ' 
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/ElectronRuns/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
elif [ $2 == "electronsE" ]; then 
  runs='466 467 468 471 472 ' 
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/ElectronRuns/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
elif [ $2 == "electronsF" ]; then 
  runs='494 495 497 502 504 ' 
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/ElectronRuns/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
elif [ $2 == "electronsG" ]; then 
  runs='513 514 516 517 520 ' 
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/ElectronRuns/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
elif [ $2 == "electronsH" ]; then 
  runs='529 530 533 535 538 541 '
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/ElectronRuns/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
elif [ $2 == "hadronsA" ]; then 
  runs='261 264 265 269 270 272 274 275 ' 
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/HadronRuns/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
elif [ $2 == "hadronsB" ]; then 
  runs='340 349 346 350 357 360 362 367 368' 
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/HadronRuns/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
elif [ $2 == "pedandmuD1" ]; then 
  runs='412 417 420 '
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/MuonRuns/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
elif [ $2 == "fullScanC" ]; then
  runs='375 376 377 379 380 381 384 387 390 392 393 394 397 398 399 401 404 405 408 410'
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
else 
  runs='244	250	271	277	282	283	303	305	306	307	308	309	311	312	315	316	322	331	332	369	370	371	374	375	376	377	404	405	408	410	412	417	420	454	456	457	460	463	464	465	476	478	481	486	489	492	505	506	507	508	510	511	521	524	525	526	527	528	552	553	554	559' 
  for runNr in $runs; do 
    ./Analyse -c $dataDir/Run$runNr\_list.txt -o $dataRaw/raw_$runNr.root -d 1 -f -m ../configs/mappingFile_202409_CAEN.txt -r ../configs/DataTakingDB_202409_CAEN.csv
  done;
fi
