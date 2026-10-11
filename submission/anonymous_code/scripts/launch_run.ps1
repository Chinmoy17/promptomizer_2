# Launches one run_experiment.py invocation fully detached from this console:
# closing the window that launched it (or this Claude Code session) does NOT
# stop the run. Run this from the repo root, in your own PowerShell window.
#
# Usage (pass any scripts.run_experiment / run_smoke flags straight through):
#   .\scripts\launch_run.ps1 --method fdpo --dataset gsm8k --n-train 150 --n-test 200 --max-rounds 5 --budget-usd 3
#   .\scripts\launch_run.ps1 --smoke --budget-usd 25          # runs run_smoke instead
#
# After launching, use .\scripts\watch_run.ps1 in another window to follow
# progress live.

param(
    [switch]$Smoke,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$module = if ($Smoke) { "scripts.run_smoke" } else { "scripts.run_experiment" }
$argString = ($Args -join ' ')

New-Item -ItemType Directory -Force -Path "results" | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outLog = "results\launch_${stamp}_out.log"
$errLog = "results\launch_${stamp}_err.log"

$proc = Start-Process -FilePath "uv" `
    -ArgumentList "run python -m $module $argString" `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog

Write-Host "Launched detached, PID $($proc.Id)."
Write-Host "Bootstrap stdout/stderr (only useful if it fails before creating a run dir):"
Write-Host "  $outLog"
Write-Host "  $errLog"
Write-Host ""
Write-Host "Once it creates results\<phase>\<run_id>\, live progress is in that run's run.log."
Write-Host "Run .\scripts\watch_run.ps1 in another window to follow it automatically."
Write-Host ""
Write-Host "To check if it's still alive later:  Get-Process -Id $($proc.Id) -ErrorAction SilentlyContinue"
Write-Host "To stop it early:                     Stop-Process -Id $($proc.Id)"
