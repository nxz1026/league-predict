@echo off
rem v1.3: 计划任务直接走 collector_silent.ps1（CreateNoWindow，无黑框）；本 bat 保留作手动调试入口
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