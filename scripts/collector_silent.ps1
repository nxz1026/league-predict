# collector_silent.ps1 — 无窗口静默启动（计划任务专用）
# 用法：powershell -ExecutionPolicy Bypass -File collector_silent.ps1 offer|night
# 直接 Start python（不经 cmd，cmd /c 会带 conhost 闪框）；
# UseShellExecute=$false + CreateNoWindow=$true ⇒ 完全不分配 conhost，零黑框；
# 不 Redirect 标准流（CreateNoWindow 模式下 Redirect 易出 Null 流错），日志由 python 侧 --mode-log 写文件。
param([string]$mode = "offer")

$root = "E:\2026Workplace\Code\collector-cn"
$py   = "C:\Python314\python.exe"

$topics = "jczq_offer jclq_offer jczq_result jclq_result jc_issue jc_issue_result lottery_draw"

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName         = $py
$psi.Arguments        = "collector.py --push-batch jczq_offer jclq_offer jczq_result jclq_result jc_issue jc_issue_result lottery_draw --mode-log $mode"
$psi.WorkingDirectory = $root
$psi.UseShellExecute  = $false
$psi.CreateNoWindow   = $true
# 注意：UseShellExecute=$false 且 CreateNoWindow=$true 时【不可】设 RedirectStandard*，
# 否则 StandardOutput/StandardError 为 null（ReadToEnd 报"不能对 Null 值表达式调用方法"）。
# 日志全由 python 侧 --mode-log 写 logs\collector_<mode>.log。

$p = [System.Diagnostics.Process]::Start($psi)
$p.WaitForExit()
exit $p.ExitCode
