"""Tests for v3.9.4 temporal verification spec lint + schema conformance.

Per docs/design/2026-05-18-ars-v3.9.4-temporal-verification-spec.md §7.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = REPO_ROOT / "shared/contracts/passport"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text())


def test_timeline_schema_validates_canonical_example():
    schema = _load_schema("timeline.schema.json")
    example = {
        "schema_version": "1.0",
        "sources": [
            {
                "citation_key": "handbook-2024ed",
                "type": "institutional-document",
                "published_date": {
                    "value": "2024-09-15",
                    "precision": "day",
                    "open_ended": False,
                    "provenance": {
                        "method": "crossref_lookup",
                        "raw": "2024-09-15",
                        "source_locator": "doi:10.xxxx/handbook-2024",
                        "confidence": "high",
                    },
                },
                "effective_date_range": {
                    "start": {
                        "value": "2024-10-01",
                        "precision": "day",
                        "open_ended": False,
                        "provenance": {
                            "method": "pdftotext_cover",
                            "raw": "Effective from October 1, 2024",
                            "source_locator": "file:///path/handbook-2024.pdf:p3",
                            "confidence": "high",
                        },
                    },
                    "end": {
                        "value": None,
                        "precision": "unknown",
                        "open_ended": True,
                        "provenance": {
                            "method": "user_override",
                            "confidence": "high",
                        },
                    },
                },
                "supersedes": "handbook-2020ed",
                "superseded_by": None,
                "version_family_id": "handbook-family",
                "version_catalog_completeness": "partial",
            }
        ],
        "events": [
            {
                "event_id": "programme-X-cycle-2022",
                "description": "Programme X review cycle 2022",
                "date": {
                    "value": "2022-04-01..2022-12-31",
                    "precision": "interval",
                    "open_ended": False,
                    "provenance": {
                        "method": "user_override",
                        "confidence": "high",
                    },
                },
                "governed_by": "handbook-2020ed",
            }
        ],
    }
    jsonschema.validate(example, schema)


def test_timeline_open_ended_only_on_end():
    """open_ended:true on start date should be a schema violation per spec §3.1 date shape table."""
    schema = _load_schema("timeline.schema.json")
    bad = {
        "schema_version": "1.0",
        "sources": [
            {
                "citation_key": "x",
                "type": "doc",
                "effective_date_range": {
                    "start": {
                        "value": None,
                        "precision": "unknown",
                        "open_ended": True,
                        "provenance": {"method": "unknown", "confidence": "unverified"},
                    },
                    "end": {
                        "value": "2024-12-31",
                        "precision": "day",
                        "open_ended": False,
                        "provenance": {"method": "crossref_lookup", "confidence": "high"},
                    },
                },
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_citation_provenance_schema_validates_canonical_example():
    schema = _load_schema("citation_provenance.schema.json")
    example = {
        "schema_version": "1.0",
        "audit_run_id": "2026-05-18T12:34:56Z-a1b2",
        "entries": [
            {
                "citation_key": "handbook-2024ed",
                "crossref_issued": {
                    "value": "2024-09-15",
                    "precision": "day",
                    "verified_at": "2026-05-18T12:34:56Z",
                    "api_endpoint": "https://api.crossref.org/works/10.xxxx/handbook-2024",
                },
                "pdftotext_cover_first_line": {
                    "line": "Quality Assurance Handbook, 2024 Edition",
                    "published_date_candidate": {
                        "value": "2024",
                        "precision": "year",
                    },
                    "verified_at": "2026-05-18T12:34:56Z",
                    "pdf_path": "/path/handbook-2024.pdf",
                },
                "verification_method": "crossref_and_pdftotext",
                "confidence": "high",
                "notes": None,
            }
        ],
    }
    jsonschema.validate(example, schema)


def test_citation_provenance_high_requires_both_sources():
    """confidence:high MUST have both crossref_issued and pdftotext_cover_first_line populated (per spec §3.4 agreement table row 1)."""
    schema = _load_schema("citation_provenance.schema.json")
    bad = {
        "schema_version": "1.0",
        "audit_run_id": "2026-05-18T12:34:56Z-a1b2",
        "entries": [
            {
                "citation_key": "x",
                "crossref_issued": None,
                "pdftotext_cover_first_line": None,
                "verification_method": "crossref_and_pdftotext",
                "confidence": "high",
                "notes": None,
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
