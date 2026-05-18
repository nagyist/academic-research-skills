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
