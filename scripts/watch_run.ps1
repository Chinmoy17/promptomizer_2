# Follows the most recently-touched run's progress live, from your own
# PowerShell window -- no dependency on any other terminal/session.
# Run this from the repo root.
#
# Usage:
#   .\scripts\watch_run.ps1                     # watches results\00_smoke\<latest>
#   .\scripts\watch_run.ps1 -Phase 01_full       # watch a different phase folder
#   Ctrl+C stops watching; the run itself keeps going either way.

param(
    [string]$ResultsRoot = "results",
    [string]$Phase = "00_smoke"
)

$phaseDir = Join-Path $ResultsRoot $Phase
if (-not (Test-Path $phaseDir)) {
    Write-Host "No runs yet under $phaseDir"
    exit 1
}

$runDir = Get-ChildItem -Path $phaseDir -Directory |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $runDir) {
    Write-Host "No run directories found under $phaseDir"
    exit 1
}

Write-Host "Watching: $($runDir.FullName)"
Write-Host ""

$logPath = Join-Path $runDir.FullName "run.log"
$ledgerPath = Join-Path $runDir.FullName "ledger.csv"

while (-not (Test-Path $logPath)) { Start-Sleep -Seconds 1 }

if (Test-Path $ledgerPath) {
    $spent = (Import-Csv $ledgerPath | Measure-Object -Property cost_usd -Sum).Sum
    Write-Host ("Spent so far: `${0:N4}" -f $spent)
    Write-Host ""
}

# Live-tail the run's own log -- same lines you'd see in the console:
# seed accuracy, per-round train accuracy, each COMMIT/REJECT, final accuracy.
Get-Content -Path $logPath -Wait -Tail 30
