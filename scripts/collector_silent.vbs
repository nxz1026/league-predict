' collector_silent.vbs - windowless launcher (wscript host, no console at all)
' Usage: wscript.exe E:\2026Workplace\Code\collector-cn\scripts\collector_silent.vbs offer
'        wscript.exe E:\2026Workplace\Code\collector-cn\scripts\collector_silent.vbs night
' Launches python directly (no cmd, no powershell, no conhost window).
' All diagnostic output goes to logs\collector_<mode>.log via --mode-log.

Set args = WScript.Arguments
mode = "offer"
If args.Count >= 1 Then mode = args(0)

Set oShell = CreateObject("WScript.Shell")
cmd = """C:\Python314\python.exe"" E:\2026Workplace\Code\collector-cn\collector.py --push-batch jczq_offer jclq_offer jczq_result jclq_result jc_issue jc_issue_result lottery_draw --mode-log " & mode
' Run(cmd, 0, True): 0 = SW_HIDE (no window), True = wait for python to finish
oShell.Run cmd, 0, True
WScript.Quit 0
