@echo off
rem collector batch: morning/noon/evening=offer snapshot, night=draw results
cd /d E:\2026Workplace\Code\collector-cn
set PY=C:\Python314\python.exe
if "%1"=="morning" goto offer
if "%1"=="noon" goto offer
if "%1"=="evening" goto offer
if "%1"=="night" goto night
echo usage: collect_batch.bat morning^|noon^|evening^|night
exit /b 1

:offer
%PY% collector.py --collect jczq_offer
%PY% collector.py --collect jclq_offer
if "%1"=="evening" %PY% collector.py --collect jc_issue
%PY% collector.py --push
exit /b 0

:night
%PY% collector.py --collect jczq_result
%PY% collector.py --collect jclq_result
%PY% collector.py --collect jc_issue_result
%PY% collector.py --collect lottery_draw
%PY% collector.py --push
exit /b 0