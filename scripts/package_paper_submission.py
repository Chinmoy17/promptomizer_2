"""Build and verify the manuscript upload and anonymous source ZIPs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

from build_anonymous_bundle import build_bundle


MANUSCRIPT_INPUTS = (
    "paper.tex", "custom.bib", "acl.sty", "acl_natbib.bst",
    "figures/fig_architecture.pdf", "figures/fig_metric.pdf",
    "figures/fig_recovered_regressed.pdf",
    "Artifacts/reported_results.json", "Artifacts/val_test_gap.json",
    "Artifacts/resource_usage.json",
)


def build_manuscript(root: Path, destination: Path) -> None:
    paper = root / "Paper_COLING"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in MANUSCRIPT_INPUTS:
            entry = zipfile.ZipInfo(relative, (2000, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, (paper / relative).read_bytes(),
                             compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(destination) as archive:
        if set(archive.namelist()) != set(MANUSCRIPT_INPUTS) or archive.testzip() is not None:
            raise ValueError("Manuscript ZIP integrity check failed")
        for relative in MANUSCRIPT_INPUTS:
            actual = hashlib.sha256(archive.read(relative)).digest()
            expected = hashlib.sha256((paper / relative).read_bytes()).digest()
            if actual != expected:
                raise ValueError(f"Manuscript source mismatch: {relative}")


def verify_source(archive_path: Path) -> int:
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Anonymous source ZIP integrity check failed")
        manifest = json.loads(archive.read("anonymous_code/ANONYMIZATION.json"))
        for record in manifest["files"]:
            content = archive.read("anonymous_code/" + record["path"])
            if hashlib.sha256(content).hexdigest() != record["sha256"]:
                raise ValueError(f"Anonymous source hash mismatch: {record['path']}")
    return len(manifest["files"]) + 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redact-term", action="append", default=[])
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    output = root / "submission"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".paper-package-", dir=output) as staging:
        upload = Path(staging) / "overleaf_upload.zip"
        build_manuscript(root, upload)
        source_archive = build_bundle(root, Path(staging) / "code",
                                      tuple(arguments.redact_term))[1]
        source_count = verify_source(source_archive)
        upload.replace(output / "overleaf_upload.zip")
        source_archive.replace(output / "anonymous_code.zip")
    print(f"PASS: Overleaf ZIP has {len(MANUSCRIPT_INPUTS)} hash-verified current files")
    print(f"PASS: anonymous source ZIP has {source_count} audited, hash-verified files")
    print("The manuscript is at the upload root. PDF compilation remains an Overleaf check.")


if __name__ == "__main__":
    main()