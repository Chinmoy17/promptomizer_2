<#
    MMLU reflect_fdpo sweep, 6 subjects, solver model comes from .env
    (SOLVER_MODEL) -- point it at gpt-4o-mini before running this.

    Mirrors run_mmlu_gpt5_sweep.ps1's protocol but uses --method reflect_fdpo
    (uncapped failures/golds, full-effect-report reflection, last-round
    shipping) instead of simple_fdpo. Settings match the completed
    reflect_mmlu_econ_v1 Haiku run (see its config.json) so the 6-subject
    gpt-4o-mini batch is directly comparable to that one data point already
    in Docs/reflect_fdpo_report.md.

    Runs sequentially (safe for one Azure deployment), CONTINUES past any
    failed run, writes a transcript log, and rolls up results/summary.json.

    Run from the repo root (after switching .env's SOLVER_* block to
    gpt-4o-mini):
        .\scripts\run_mmlu_reflect_sweep.ps1
    Override anything, e.g. more seeds:
        .\scripts\run_mmlu_reflect_sweep.ps1 -Seeds 0,1,2
#>
param(
    [int[]]  $Seeds        = @(0),
    [int]    $Rounds       = 3,
    [string] $ValFrac      = "0.5",
    [string] $SkipAboveAcc = "0.95",
    [int]    $NTrain       = 50,
    [int]    $NTest        = 66,
    [int]    $MaxWorkers   = 3,
    [string] $BudgetUsd    = "4.0"
)

$ErrorActionPreference = "Continue"

$subjects = @(
    "college_mathematics",
    "philosophy",
    "econometrics",
    "high_school_biology",
    "professional_law",
    "computer_security"
)

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
New-Item -ItemType Directory -Force -Path "results\_logs" | Out-Null
$log = "results\_logs\mmlu_reflect_sweep_$stamp.log"

$transcribing = $false
try   { Start-Transcript -Path $log -Append -ErrorAction Stop | Out-Null; $transcribing = $true }
catch { Write-Warning "Transcript unavailable ($($_.Exception.Message)); continuing without it." }

$ok = 0; $fail = 0; $failed = @()
$total = $subjects.Count * $Seeds.Count
$i = 0
$swAll = [System.Diagnostics.Stopwatch]::StartNew()

foreach ($subj in $subjects) {
    foreach ($seed in $Seeds) {
        $i++
        Write-Host "`n=== [$i/$total] $subj  seed=$seed  rounds=$Rounds ===" -ForegroundColor Cyan
        $sw = [System.Diagnostics.Stopwatch]::StartNew()

        $runArgs = @(
            "run", "python", "-m", "scripts.run_experiment",
            "--method", "reflect_fdpo", "--dataset", "mmlu",
            "--prompt-file", "prompts/mmlu_oneliner.md", "--subjects", $subj,
            "--n-train", $NTrain, "--n-test", $NTest,
            "--simple-max-rounds", $Rounds, "--simple-val-frac", $ValFrac,
            "--skip-above-acc", $SkipAboveAcc, "--tau", "1", "--seed", $seed,
            "--accept-margin", "0.0",
            "--split-mode", "balanced", "--max-workers", $MaxWorkers,
            "--budget-usd", $BudgetUsd, "--phase", "mmlu_reflect_$subj"
        )
        uv @runArgs
        $sw.Stop()

        if ($LASTEXITCODE -eq 0) {
            $ok++
            Write-Host "    done in $([int]$sw.Elapsed.TotalSeconds)s" -ForegroundColor Green
        } else {
            $fail++; $failed += "$subj/seed$seed (exit $LASTEXITCODE)"
            Write-Warning "    FAILED: $subj seed $seed (exit $LASTEXITCODE) -- continuing"
        }
    }
}

$swAll.Stop()
Write-Host "`n=== sweep complete: $ok ok / $fail failed of $total in $([int]$swAll.Elapsed.TotalMinutes) min ===" -ForegroundColor Cyan
if ($failed.Count -gt 0) { Write-Warning ("failed runs: " + ($failed -join "; ")) }

Write-Host "`nRolling up results/summary.json ..."
uv run python -m scripts.build_results_summary

if ($transcribing) { try { Stop-Transcript | Out-Null } catch {} }
Write-Host "Log: $log"
