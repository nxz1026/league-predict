@echo off
rem collector batch v1.2: every batch carries all 7 topics (B1) + manifest .done last (B2/G-A)
cd /d E:\2026Workplace\Code\collector-cn
set PY=C:\Python314\python.exe
if "%1"=="offer" goto offer
if "%1"=="night" goto night
echo usage: collect_batch.bat offer^|night
exit /b 1

:offer
%PY% collector.py --push-batch jczq_offer jclq_offer jczq_result jclq_result jc_issue jc_issue_result lottery_draw
exit /b 0

:night
%PY% collector.py --push-batch jczq_offer jclq_offer jczq_result jclq_result jc_issue jc_issue_result lottery_draw
exit /b 0