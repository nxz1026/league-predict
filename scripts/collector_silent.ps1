# collector_silent.ps1 — 无窗口静默启动（计划任务专用，会话 0 S4U）
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File collector_silent.ps1 offer|night
# 直接 Start python（不经 cmd，cmd /c 会带 conhost 闪框）；
# UseShellExecute=$false + CreateNoWindow=$true ⇒ 完全不分配 conhost，零黑框。
# 日志由 python 侧 --mode-log 写 logs\collector_<mode>.log。
param([string]$mode = "offer")

$root   = "E:\2026Workplace\Code\collector-cn"
$py     = "C:\Python314\python.exe"
$topics = "jczq_offer jclq_offer jczq_result jclq_result jc_issue jc_issue_result lottery_draw"

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName         = $py
$psi.Arguments        = "collector.py --push-batch $topics --mode-log $mode"
$psi.WorkingDirectory = $root
$psi.UseShellExecute  = $false
$psi.CreateNoWindow   = $true
$p = [System.Diagnostics.Process]::Start($psi)
$p.WaitForExit()
exit $p.ExitCode
