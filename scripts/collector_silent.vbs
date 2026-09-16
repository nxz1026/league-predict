' collector_silent.vbs - silent (no window) launcher for collect_batch.bat
' Plan-task action:
'   wscript.exe E:\2026Workplace\Code\collector-cn\scripts\collector_silent.vbs offer
'   wscript.exe E:\2026Workplace\Code\collector-cn\scripts\collector_silent.vbs night
' Output already redirected to logs\collector_<mode>.log inside the bat.
' This script only hides the window, passes the arg, and waits for the bat to finish.

Set args = WScript.Arguments
mode = "offer"
If args.Count >= 1 Then mode = args(0)

Set oShell = CreateObject("WScript.Shell")
batline = "E:\2026Workplace\Code\collector-cn\scripts\collect_batch.bat " & mode
' Run(batline, 0, True): 0 = hidden window, True = wait for exit (rc = bat exit code)
oShell.Run batline, 0, True
WScript.Quit 0
