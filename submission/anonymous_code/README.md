# Anonymous Source Submission

This archive contains the experiment code, tests, seed prompts, analysis
scripts, dependency lock, and container setup. Author identity, Git history,
private environment files, run outputs, and dataset corpora are not included.
It is a source submission, not a release of the paper's per-item result traces.

## Setup

Python 3.12.10 and uv are used for the pinned environment.

```bash
uv sync --frozen
```

Copy .env.example to .env using `cp .env.example .env` on Linux/macOS or
`Copy-Item .env.example .env` in Windows PowerShell. Configure your own API
credentials and model endpoints; the distributed placeholders are not secrets.
For Azure OpenAI, configure the per-role API_VERSION and resource endpoint.
For a local OpenAI-compatible server, use its model identifier and base URL,
set a nonempty dummy API key, and leave API_VERSION empty.

## Data and Tests

Most integration tests require dataset files. Download the required public
benchmarks before running the complete suite:

```bash
uv run python -m scripts.download_datasets --dataset all
uv run python -m pytest
```

Dataset files are excluded from the submission because they are third-party
corpora, and PUPA includes personal information. Consult the datasets' original
licenses and data-use requirements before downloading, sharing, or sending
examples to hosted APIs. The tests use mock model clients, not paid inference.

## Experiments

```bash
uv run python -m scripts.run_experiment --help
uv run python -m scripts.run_experiment --method reflect_fdpo \
  --dataset legalbench_hearsay --seed 0 --n-train 50 --n-test 49 \
  --split-mode stratified --simple-val-frac 0.5 --simple-max-rounds 3 \
  --tau 1 --skip-above-acc 0.95 --budget-usd 4
```

On Windows, run the experiment command on one line, or use PowerShell backticks
instead of shell backslashes. For a dataset-backed offline smoke run, add
`--dry-run`; download its dataset first. Live runs invoke the configured APIs.

The solver executes task prompts, the optimizer rewrites them, and the judge
is used where the method or dataset requires it. Supported methods include
zeroshot_cot, fewshot_cot, monolithic, fdpo, simple_fdpo, and reflect_fdpo.
The current reflective implementation returns the best committed validation
candidate, breaking ties by mining accuracy. Returning an edited prompt is not
conditional on outperforming the seed. Historical runs used earlier variants;
this archive does not claim to freeze every historical experiment version.

## Containers

After configuring .env and downloading the data:

```bash
docker compose build
docker compose run --rm fdpo python -m scripts.run_experiment --help
```

The image is the orchestrator only, not a GPU model server. The compose setup
uses host networking intended for Linux; Docker Desktop users must configure
reachable endpoints appropriately. Runtime outputs are written to results/,
which starts absent from this submission.

## Contents

- src/fdpo: configuration, model clients, optimization loops, and evaluation.
- scripts: dataset download, experiment runners, and result inspection tools.
- tests: the original unit and integration tests.
- prompts: the starting task instructions and their variants.
- _dl: development/analysis code, not saved analysis outputs.
- Docs: selected technical implementation and local-execution documentation.
- ANONYMIZATION.json: neutral export scope, redaction counts, and file hashes.

Setup documentation and helper code may contain redacted placeholders. No
license or ownership claim has been invented for this review copy. Automated
checks address explicit identifiers and common secret formats; authors must
also review contextual clues and the final upload for double-blind compliance.
