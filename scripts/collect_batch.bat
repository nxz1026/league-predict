@echo off
rem collector batch v1.3 no-console (scheduled task via wscript collector_silent.vbs)
cd /d E:\2026Workplace\Code\collector-cn
if not exist logs mkdir logs
set PY=C:\Python314\python.exe
if "%1"=="offer" goto offer
if "%1"=="night" goto night
echo usage: collect_batch.bat offer^|night
exit /b 1

:offer
%PY% collector.py --push-batch jczq_offer jclq_offer jczq_result jclq_result jc_issue jc_issue_result lottery_draw >>logs\collector_offer.log 2>&1
exit /b 0

:night
%PY% collector.py --push-batch jczq_offer jclq_offer jczq_result jclq_result jc_issue jc_issue_result lottery_draw >>logs\collector_night.log 2>&1
exit /b 0