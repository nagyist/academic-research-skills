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


def test_p5_currently_emits_deictic_finding(tmp_path):
    """Mode 5 time-bomb: 'currently' triggers TEMPORAL-DEICTIC."""
    result = _run_audit(
        tmp_path,
        draft="Currently, the most recent edition prescribes annual review.\n",
        timeline={"schema_version": "1.0", "sources": [], "events": []},
    )
    deictic = [f for f in result["findings"] if f["finding_kind"] == "TEMPORAL-DEICTIC"]
    assert len(deictic) >= 1, f"expected >=1 TEMPORAL-DEICTIC, got: {result['findings']}"
    first = deictic[0]
    assert first["mode"] == 5
    assert first["severity"] == "LOW"
    assert first["matched_span"] is not None
    assert "currently" in first["matched_span"]["text"].lower()


def test_p5_anchored_phrase_no_finding(tmp_path):
    """Mode 5 legitimate: 'As of 2026-05-18, the 2024 edition prescribes' must NOT trigger."""
    result = _run_audit(
        tmp_path,
        draft="As of 2026-05-18, the 2024 edition prescribes annual review.\n",
        timeline={"schema_version": "1.0", "sources": [], "events": []},
    )
    deictic = [f for f in result["findings"] if f["finding_kind"] == "TEMPORAL-DEICTIC"]
    assert deictic == [], f"unexpected deictic findings: {deictic}"


def test_p1_future_as_past_emits_arithmetic_impossible(tmp_path):
    """Mode 1: 'As of March 2025, ... had already completed June 2025 deliverables' is physically impossible."""
    result = _run_audit(
        tmp_path,
        draft="As of March 2025, the report noted that the system had already completed June 2025 deliverables.\n",
        timeline={"schema_version": "1.0", "sources": [], "events": []},
    )
    arith = [f for f in result["findings"] if f["finding_kind"] == "TEMPORAL-ARITHMETIC-IMPOSSIBLE"]
    assert len(arith) == 1, f"expected 1 TEMPORAL-ARITHMETIC-IMPOSSIBLE, got: {result['findings']}"
    first = arith[0]
    assert first["mode"] == 1
    assert first["severity"] == "HIGH"
    assert first["bound_dates"] is not None
    # anchor=March 2025, event=June 2025; event > anchor
    assert first["bound_dates"]["left"]["role"] == "anchor"
    assert "2025-03" in first["bound_dates"]["left"]["value"]
    assert first["bound_dates"]["right"]["role"] == "event"
    assert "2025-06" in first["bound_dates"]["right"]["value"]


def test_p1_prospective_already_past(tmp_path):
    """Mode 1 Pattern B: forthcoming event but anchor is later than event date."""
    result = _run_audit(
        tmp_path,
        draft="The June 2025 delivery to be completed by the project team, as of December 2025 the project is unfinished.\n",
        timeline={"schema_version": "1.0", "sources": [], "events": []},
    )
    arith = [f for f in result["findings"] if f["finding_kind"] == "TEMPORAL-ARITHMETIC-IMPOSSIBLE"]
    assert len(arith) >= 1


def test_p2_2026_handbook_governing_2022_event(tmp_path):
    """Mode 2: 2026 handbook cited for 2022 review cycle → anachronism."""
    result = _run_audit(
        tmp_path,
        draft="The 2026 Handbook governed the 2022 review cycle.<!--ref:handbook-2026ed-->\n",
        timeline={
            "schema_version": "1.0",
            "sources": [{
                "citation_key": "handbook-2026ed",
                "type": "institutional-document",
                "published_date": {
                    "value": "2026-09-15", "precision": "day", "open_ended": False,
                    "provenance": {"method": "crossref_lookup", "confidence": "high"},
                },
                "effective_date_range": {
                    "start": {
                        "value": "2026-09-15", "precision": "day", "open_ended": False,
                        "provenance": {"method": "crossref_lookup", "confidence": "high"},
                    },
                    "end": {
                        "value": None, "precision": "unknown", "open_ended": True,
                        "provenance": {"method": "user_override", "confidence": "high"},
                    },
                },
            }],
            "events": [],
        },
    )
    anachronism = [f for f in result["findings"] if f["finding_kind"] == "TEMPORAL-ANACHRONISTIC-CITATION"]
    assert len(anachronism) == 1, f"expected 1 anachronism, got: {result['findings']}"
    f0 = anachronism[0]
    assert f0["mode"] == 2
    assert f0["bound_event"] is not None
    assert f0["bound_refs"][0]["ref_slug"] == "handbook-2026ed"


def test_p3_unmaterialized_comparator(tmp_path):
    """Mode 3: prose mentions '1998 edition' but timeline only has 2020 edition."""
    result = _run_audit(
        tmp_path,
        draft="This differs from the 1998 edition of the standard.<!--ref:standard-2020ed-->\n",
        timeline={
            "schema_version": "1.0",
            "sources": [{
                "citation_key": "standard-2020ed",
                "type": "standard",
                "version_family_id": "standard-family",
                "published_date": {
                    "value": "2020-01-01", "precision": "year", "open_ended": False,
                    "provenance": {"method": "user_override", "confidence": "high"},
                },
            }],
            "events": [],
        },
    )
    comparator = [f for f in result["findings"] if f["finding_kind"] == "TEMPORAL-COMPARATOR-UNMATERIALIZED"]
    assert len(comparator) == 1, f"expected 1 comparator finding, got: {result['findings']}"
    assert comparator[0]["matched_span"] is not None
    assert "1998" in comparator[0]["matched_span"]["text"]


def test_p4_causal_inversion(tmp_path):
    """Mode 4: 'Policy A enabled Policy B' but timeline has A AFTER B."""
    result = _run_audit(
        tmp_path,
        draft="Policy A<!--ref:policy-a--> enabled Policy B<!--ref:policy-b-->.\n",
        timeline={
            "schema_version": "1.0",
            "sources": [
                {"citation_key": "policy-a", "type": "policy",
                 "published_date": {"value": "2026-03-01", "precision": "day", "open_ended": False,
                                    "provenance": {"method": "user_override", "confidence": "high"}}},
                {"citation_key": "policy-b", "type": "policy",
                 "published_date": {"value": "2020-05-15", "precision": "day", "open_ended": False,
                                    "provenance": {"method": "user_override", "confidence": "high"}}},
            ],
            "events": [],
        },
    )
    causal = [f for f in result["findings"] if f["finding_kind"] == "TEMPORAL-CAUSAL-INVERSION"]
    assert len(causal) == 1, f"expected 1 causal finding, got: {result['findings']}"
    f0 = causal[0]
    assert f0["bound_dates"] is not None
    assert f0["bound_dates"]["left"]["ref_slug"] == "policy-a"
    assert f0["bound_dates"]["right"]["ref_slug"] == "policy-b"


def test_audit_writes_markdown_report(tmp_path):
    """Audit must write phase4_composition/temporal_audit.md alongside the YAML."""
    (tmp_path / "draft.md").write_text("Currently, the framework is under review.\n")
    (tmp_path / "timeline.yaml").write_text(yaml.safe_dump(
        {"schema_version": "1.0", "sources": [], "events": []}))
    (tmp_path / "citation_provenance.yaml").write_text(yaml.safe_dump(
        {"schema_version": "1.0", "audit_run_id": "2026-05-18T12:34:56Z-a1b2", "entries": []}))
    out_yaml = tmp_path / "temporal_audit_results.yaml"
    out_md = tmp_path / "temporal_audit.md"

    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--draft", str(tmp_path / "draft.md"),
         "--timeline", str(tmp_path / "timeline.yaml"),
         "--citation-provenance", str(tmp_path / "citation_provenance.yaml"),
         "--output", str(out_yaml),
         "--markdown-output", str(out_md),
         "--report-reference-date", "2026-05-18",
         "--audit-run-id", "2026-05-18T12:34:56Z-a1b2"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    assert out_yaml.exists()
    assert out_md.exists()
    md = out_md.read_text()
    assert "# Temporal Audit Results" in md
    assert "TEMPORAL-DEICTIC" in md
