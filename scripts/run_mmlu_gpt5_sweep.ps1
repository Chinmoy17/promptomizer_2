<#
    MMLU simple_fdpo sweep, 6 subjects, gpt-5 as the optimizer.

    This run's arrangement (per the request):
      - NO budget cap        (--budget-usd 0)
      - 3 optimizer rounds   (--simple-max-rounds 3)
      - 2 seeds              (0, 1)
      - near-ceiling skip    (--skip-above-acc 0.92: only the ~92% subjects
                              auto-skip -- computer_security; biology ~88% now
                              optimizes)
      - larger validation    (--simple-val-frac 0.5: 25 mining / 25 val, so the
                              accept gate can actually distinguish 3 rounds
                              instead of saturating at a 7-item 100% tie)

    Runs sequentially (safe for one Azure deployment), CONTINUES past any
    failed run, writes a transcript log, and rolls up results/summary.json.

    Run from the repo root:
        .\scripts\run_mmlu_gpt5_sweep.ps1
    Override anything, e.g. 3 seeds or the old 0.35 val split:
        .\scripts\run_mmlu_gpt5_sweep.ps1 -Seeds 0,1,2 -ValFrac 0.35
#>
param(
    [int[]]  $Seeds        = @(0, 1),
    [int]    $Rounds       = 3,
    [string] $ValFrac      = "0.5",    # string keeps the decimal locale-safe
    [string] $SkipAboveAcc = "0.92",
    [int]    $NTrain       = 50,
    [int]    $NTest        = 66,
    [int]    $MaxWorkers   = 3
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
$log = "results\_logs\mmlu_gpt5_sweep_$stamp.log"

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
            "--method", "simple_fdpo", "--dataset", "mmlu",
            "--prompt-file", "prompts/mmlu_oneliner.md", "--subjects", $subj,
            "--n-train", $NTrain, "--n-test", $NTest,
            "--simple-max-rounds", $Rounds, "--simple-val-frac", $ValFrac,
            "--skip-above-acc", $SkipAboveAcc, "--tau", "3", "--seed", $seed,
            "--split-mode", "balanced", "--max-workers", $MaxWorkers,
            "--budget-usd", "0", "--phase", "mmlu_gpt5_$subj"
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
