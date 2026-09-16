# collector_silent.ps1 — 无窗口启动 collect_batch.bat（PowerShell 版，避开 VBS 文件类型关联弹框）
# 用法：powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File collector_silent.ps1 offer
param(
    [string]$mode = "offer"
)

$bat = "E:\2026Workplace\Code\collector-cn\scripts\collect_batch.bat"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cmd.exe"
$psi.Arguments = "/c `"$bat $mode`""
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true          # 不分配 conhost 窗口（彻底无黑框）
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.WorkingDirectory = "E:\2026Workplace\Code\collector-cn"

$p = [System.Diagnostics.Process]::Start($psi)
# 让 bat 内的 python 跑完（bat 已把输出写 logs\collector_<mode>.log，这里再兜底收一次防丢）
$null = $p.StandardOutput.ReadToEnd()
$null = $p.StandardError.ReadToEnd()
$p.WaitForExit()
exit $p.ExitCode
