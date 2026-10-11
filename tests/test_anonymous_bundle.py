"""Checks for anonymous submission export without reading live credentials."""

import json
import zipfile

import pytest

from scripts.build_anonymous_bundle import audit_text, build_bundle, sanitize_text


def test_export_excludes_private_files_and_preserves_originals(tmp_path):
    source = tmp_path / "private_project"
    (source / "src" / "fdpo").mkdir(parents=True)
    (source / "results").mkdir()
    (source / ".git").mkdir()
    code = "MODEL = 'gpt-4o-mini'\n"
    (source / "src" / "fdpo" / "example.py").write_text(code, encoding="utf-8")
    (source / ".env").write_text("API_KEY=synthetic-private-value\n", encoding="utf-8")
    (source / "results" / "metrics.json").write_text("{}", encoding="utf-8")
    (source / ".git" / "config").write_text("private history", encoding="utf-8")
    (source / "report.md").write_text("private notes", encoding="utf-8")
    bundle, archive = build_bundle(source, tmp_path / "export")
    assert (source / "src" / "fdpo" / "example.py").read_text(encoding="utf-8") == code
    assert (bundle / "src" / "fdpo" / "example.py").read_text(encoding="utf-8") == code
    assert not (bundle / ".env").exists()
    assert not (bundle / "results").exists()
    assert not (bundle / ".git").exists()
    assert not (bundle / "report.md").exists()
    assert (bundle / ".env.example").exists()
    assert (bundle / "Dataset" / "README.md").exists()
    manifest = json.loads((bundle / "ANONYMIZATION.json").read_text(encoding="utf-8"))
    assert manifest["checks"]["explicit_identifier_scan"] == "passed"
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        assert all(entry.date_time == (2000, 1, 1, 0, 0, 0) for entry in zipped.infolist())
        assert not any("synthetic-private-value" in zipped.read(entry).decode("utf-8")
                       for entry in zipped.namelist())


def test_sanitization_replaces_identity_but_keeps_example_addresses(tmp_path):
    private_address = "person@" + "researchlab.edu"
    private_endpoint = "https://private-resource" + ".openai.azure.com/"
    text = (
        f"contact={private_address}\n"
        f"sample=alice@example.com\n"
        f"endpoint={private_endpoint}\n"
        f"path=C:\\Users\\private_user\\project\n"
        f"location=ResearchLab\n"
    )
    sanitized, count = sanitize_text(text, tmp_path, ("ResearchLab", "private_user"))
    assert private_address not in sanitized
    assert "alice@example.com" in sanitized
    assert "private-resource" not in sanitized
    assert "private_user" not in sanitized
    assert count > 0
    assert audit_text(sanitized, ("ResearchLab", "private_user")) == []
    assert sanitized.count("\n") == text.count("\n")


def test_export_fails_closed_for_a_possible_hardcoded_secret(tmp_path):
    source = tmp_path / "source"
    (source / "src").mkdir(parents=True)
    secret = "sk-" + "x" * 32
    (source / "src" / "unsafe.py").write_text(f"API_KEY = '{secret}'\n", encoding="utf-8")
    output = tmp_path / "export"
    with pytest.raises(ValueError, match="values withheld") as error:
        build_bundle(source, output)
    assert secret not in str(error.value)
    assert not (output / "anonymous_code").exists()
    assert not (output / "anonymous_code.zip").exists()


def test_export_does_not_overwrite_an_existing_bundle(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "export"
    build_bundle(source, output)
    with pytest.raises(FileExistsError):
        build_bundle(source, output)