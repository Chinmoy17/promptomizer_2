# Follows the most recently-touched run's progress live, from your own
# PowerShell window -- no dependency on any other terminal/session.
# Run this from the repo root.
#
# Usage:
#   .\scripts\watch_run.ps1                # watches the latest run under results/, across ALL phases
#   .\scripts\watch_run.ps1 -Phase smoke   # restrict to results/smoke/
#   .\scripts\watch_run.ps1 -Phase main    # restrict to results/main/
#   Ctrl+C stops watching; the run itself keeps going either way.

param(
    [string]$ResultsRoot = "results",
    [string]$Phase = ""
)

if ($Phase) {
    $searchRoots = @(Join-Path $ResultsRoot $Phase)
    if (-not (Test-Path $searchRoots[0])) {
        Write-Host "No such phase folder: $($searchRoots[0])"
        exit 1
    }
} else {
    # any subdirectory of results/ that isn't a summary artifact
    $searchRoots = Get-ChildItem -Path $ResultsRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch '^\.' } |
        ForEach-Object { $_.FullName }
    if (-not $searchRoots) {
        Write-Host "No phase folders yet under $ResultsRoot"
        exit 1
    }
}

$runDir = $searchRoots |
    ForEach-Object { Get-ChildItem -Path $_ -Directory -ErrorAction SilentlyContinue } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $runDir) {
    Write-Host "No run directories found under: $($searchRoots -join ', ')"
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
