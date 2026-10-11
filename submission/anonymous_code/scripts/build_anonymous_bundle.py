"""Export a results-free, sanitized source archive for anonymous review."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlsplit


BUNDLE_NAME = "anonymous_code"
ROOT_FILES = (
    "pyproject.toml", "uv.lock", ".python-version", ".gitignore",
    ".dockerignore", "Dockerfile", "docker-compose.yml", "Codebase.md",
    "oracle_leak_check.py",
)
SOURCE_TREES = {
    "src": {".py"},
    "scripts": {".py", ".ps1", ".sh"},
    "tests": {".py"},
    "prompts": {".md"},
    "_dl": {".py"},
}
TECHNICAL_DOCS = (
    "fdpo_mechanism.md", "running_on_local_gpu.md",
    "running_reflect_fdpo_local.md", "simple_fdpo_architecture.md",
)
EXCLUDED_PARTS = {
    "results", ".git", ".venv", ".claude", ".vscode", ".pytest_cache",
    "__pycache__", "Paper_COLING",
}
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
URL = re.compile(r"https?://[^\s\\\"'<>`)]+")
PRIVATE_CLOUD_SUFFIXES = (
    ".openai.azure.com", ".services.ai.azure.com", ".azurewebsites.net",
)
SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|passwd|access[_-]?token)"
        r"[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_+/=.-]{24,})"
    ),
)

ENV_TEMPLATE = """# Copy this template to .env and configure your own model endpoints.
# API_VERSION must be empty for ordinary OpenAI-compatible endpoints.
SOLVER_MODEL=gpt-4o-mini
SOLVER_BASE_URL=https://api.openai.com/v1
SOLVER_API_KEY=replace-me
SOLVER_API_VERSION=

OPTIMIZER_MODEL=gpt-5
OPTIMIZER_BASE_URL=https://api.openai.com/v1
OPTIMIZER_API_KEY=replace-me
OPTIMIZER_API_VERSION=

JUDGE_MODEL=gpt-5
JUDGE_BASE_URL=https://api.openai.com/v1
JUDGE_API_KEY=replace-me
JUDGE_API_VERSION=
"""

REVIEW_README = """# Anonymous Source Submission

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
uv run python -m scripts.run_experiment --method reflect_fdpo \\
  --dataset legalbench_hearsay --seed 0 --n-train 50 --n-test 49 \\
  --split-mode stratified --simple-val-frac 0.5 --simple-max-rounds 3 \\
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
"""

DATA_README = """# Dataset Files Excluded

Populate this directory with the dataset downloader described in the root
README. No dataset text or personal-information corpus is distributed here.
"""


def source_files(source_root: Path) -> list[Path]:
    candidates = [source_root / name for name in ROOT_FILES]
    candidates += [source_root / "Docs" / name for name in TECHNICAL_DOCS]
    for folder, suffixes in SOURCE_TREES.items():
        candidates += [path for path in (source_root / folder).rglob("*")
                       if path.is_file() and path.suffix in suffixes]
    selected = []
    for path in candidates:
        if not path.is_file():
            continue
        relative = path.relative_to(source_root)
        if EXCLUDED_PARTS.intersection(relative.parts):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(source_root):
            raise ValueError(f"Refusing linked source file: {relative.as_posix()}")
        selected.append(path)
    return sorted(set(selected))


def private_email(address: str) -> bool:
    domain = address.rsplit("@", 1)[1].lower()
    return not (domain in {"example.com", "example.org", "example.net"}
                or domain.endswith((".invalid", ".test", ".example", ".local")))


def sanitize_text(text: str, source_root: Path, terms: tuple[str, ...]) -> tuple[str, int]:
    replacements = 0

    def replace(pattern: re.Pattern, replacement) -> None:
        nonlocal text, replacements
        text, count = pattern.subn(replacement, text)
        replacements += count

    for spelling in {str(source_root), source_root.as_posix()}:
        replace(re.compile(re.escape(spelling), re.IGNORECASE), ".")
    replace(re.compile(r"(?i)([A-Z]:[/\\]Users[/\\])[^/\\\s\"']+"), r"\1anonymous")
    replace(re.compile(r"/(?:home|Users)/[^/\s\"']+"), "/home/anonymous")

    def sanitize_url(match: re.Match) -> str:
        address = match.group()
        parsed = urlsplit(address)
        host = parsed.hostname or ""
        if host.endswith(PRIVATE_CLOUD_SUFFIXES):
            return "https://example-resource.openai.azure.com"
        if parsed.username or parsed.password:
            return f"{parsed.scheme}://{host}{parsed.path}"
        return address

    replace(URL, sanitize_url)
    replace(EMAIL, lambda match: "anonymous@example.invalid"
            if private_email(match.group()) else match.group())
    for term in sorted(set(terms), key=len, reverse=True):
        if len(term.strip()) < 3:
            continue
        pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(term)
                             + r"(?![A-Za-z0-9])", re.IGNORECASE)
        replace(pattern, "anonymous")
    return text, replacements


def audit_text(text: str, terms: tuple[str, ...]) -> list[str]:
    issues = []
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        issues.append("possible credential or private key")
    if any(private_email(match.group()) for match in EMAIL.finditer(text)):
        issues.append("non-placeholder email")
    for match in URL.finditer(text):
        parsed = urlsplit(match.group())
        host = parsed.hostname or ""
        if parsed.username or parsed.password:
            issues.append("URL credentials")
        if host.endswith(PRIVATE_CLOUD_SUFFIXES) and host != "example-resource.openai.azure.com":
            issues.append("private cloud resource")
    if any(re.search(r"(?<![A-Za-z0-9])" + re.escape(term)
                     + r"(?![A-Za-z0-9])", text, re.IGNORECASE)
           for term in terms if len(term.strip()) >= 3):
        issues.append("author-specific term")
    return sorted(set(issues))


def build_bundle(source_root: Path, output_parent: Path,
                 redact_terms: tuple[str, ...] = ()) -> tuple[Path, Path]:
    source_root = source_root.resolve()
    output_parent = output_parent.resolve()
    destination = output_parent / BUNDLE_NAME
    archive = output_parent / f"{BUNDLE_NAME}.zip"
    if destination.exists() or archive.exists():
        raise FileExistsError("Output already exists; choose a new output directory.")
    project_identifier = (source_root.name if source_root.name.lower() not in
                          {"source", "src", "project", "code", "repository", "repo", "workspace"}
                          else "")
    terms = tuple(term for term in (*redact_terms, project_identifier,
                  os.environ.get("USERNAME", "")) if term)
    output_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".review-export-", dir=output_parent) as staging:
        bundle = Path(staging) / BUNDLE_NAME
        bundle.mkdir()
        redacted_files = []
        for source_path in source_files(source_root):
            relative = source_path.relative_to(source_root)
            text, count = sanitize_text(source_path.read_text(encoding="utf-8-sig"),
                                        source_root, terms)
            target = bundle / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
            if count:
                redacted_files.append({"path": relative.as_posix(), "matches": count})
        for name, content in {"README.md": REVIEW_README, ".env.example": ENV_TEMPLATE,
                              "Dataset/README.md": DATA_README}.items():
            target = bundle / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        files = sorted(path for path in bundle.rglob("*") if path.is_file())
        findings = {path.relative_to(bundle).as_posix(): audit_text(
                    path.read_text(encoding="utf-8"), terms) for path in files}
        findings = {name: issues for name, issues in findings.items() if issues}
        if findings:
            raise ValueError("Export audit failed (values withheld): "
                             + json.dumps(findings, sort_keys=True))
        manifest = {
            "format_version": 1,
            "scope": "experiment source, tests, prompts, setup, and selected technical docs",
            "excluded": ["results and run traces", "dataset corpora", "private environment",
                         "Git/editor history", "manuscript and research reports", "caches"],
            "redacted_files": redacted_files,
            "files": [{"path": path.relative_to(bundle).as_posix(),
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                      for path in files],
            "checks": {"explicit_identifier_scan": "passed", "tests": "not run by exporter"},
        }
        (bundle / "ANONYMIZATION.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                                 encoding="utf-8")
        staged_archive = Path(staging) / archive.name
        with zipfile.ZipFile(staged_archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
            for path in sorted(path for path in bundle.rglob("*") if path.is_file()):
                relative = path.relative_to(bundle)
                info = zipfile.ZipInfo(f"{BUNDLE_NAME}/{relative.as_posix()}",
                                       date_time=(2000, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (0o100755 if path.suffix == ".sh" else 0o100644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                zipped.writestr(info, path.read_bytes())
        shutil.copytree(bundle, destination)
        staged_archive.replace(archive)
    return destination, archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--output-dir", type=Path, default=Path("submission"))
    parser.add_argument("--redact-term", action="append", default=[])
    args = parser.parse_args()
    destination, archive = build_bundle(args.source, args.output_dir, tuple(args.redact_term))
    manifest = json.loads((destination / "ANONYMIZATION.json").read_text(encoding="utf-8"))
    print(f"Created {archive.name}: {len(manifest['files']) + 1} files; "
          f"{len(manifest['redacted_files'])} source files sanitized.")
    print("Results, dataset corpora, private environment, and Git history excluded.")


if __name__ == "__main__":
    main()