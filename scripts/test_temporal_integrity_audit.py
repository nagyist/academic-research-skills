"""Tests for v3.9.4 temporal_integrity_audit.py 5-pass verifier."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/temporal_integrity_audit.py"


def _run_audit(tmp_path: Path, draft: str, timeline: dict, citation_provenance: dict | None = None,
               report_reference_date: str = "2026-05-18") -> dict:
    """Helper: write inputs, run audit, return parsed output."""
    (tmp_path / "draft.md").write_text(draft)
    (tmp_path / "timeline.yaml").write_text(yaml.safe_dump(timeline))
    (tmp_path / "citation_provenance.yaml").write_text(yaml.safe_dump(
        citation_provenance or {"schema_version": "1.0", "audit_run_id": "2026-05-18T12:34:56Z-a1b2", "entries": []}
    ))
    out = tmp_path / "temporal_audit_results.yaml"
    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--draft", str(tmp_path / "draft.md"),
         "--timeline", str(tmp_path / "timeline.yaml"),
         "--citation-provenance", str(tmp_path / "citation_provenance.yaml"),
         "--output", str(out),
         "--report-reference-date", report_reference_date,
         "--audit-run-id", "2026-05-18T12:34:56Z-a1b2"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"audit failed: stderr={result.stderr!r}"
    return yaml.safe_load(out.read_text())


def test_audit_scaffold_returns_empty_findings_on_empty_draft(tmp_path):
    """Scaffold sanity: empty draft → 0 findings, valid output shape."""
    result = _run_audit(tmp_path, draft="", timeline={"schema_version": "1.0", "sources": [], "events": []})
    assert result["schema_version"] == "1.0"
    assert result["audit_run_id"] == "2026-05-18T12:34:56Z-a1b2"
    assert result["report_reference_date"] == "2026-05-18"
    assert result["findings"] == []
