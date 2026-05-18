#!/usr/bin/env python3
"""v3.9.4 spec lint — temporal verification sidecar conformance.

Enforces 8 invariants from spec §7:
  1. timeline.yaml schema conformance against timeline.schema.json
  2. supersession chain has no cycles (Task 7)
  3. every date carries precision and provenance.method (implicit via schema)
  4. citation_provenance.yaml schema conformance
  5. temporal_audit_results.yaml schema conformance + finding_kind closed list + per-kind required-field map (via oneOf)
  6. M3 IRON RULE block present in report_compiler_agent.md and draft_writer_agent.md (Task 22 implements lint of this)
  7. M6 Citation Provenance Protocol section present in timeline_extraction_agent.md (Task 21+22 implements)
  8. bibliography_agent.md UNMODIFIED relative to v3.9.3 baseline (Task 8 implements sha256 guard)

This Task 6 scaffold implements invariants 1, 4, 5 (schema conformance). Invariants 2, 6-8 are added in later tasks.

Usage:
  python scripts/check_v3_9_4_temporal_verification.py \\
    --timeline phase2_investigation/timeline.yaml \\
    --citation-provenance phase2_investigation/citation_provenance.yaml \\
    --temporal-audit phase4_composition/temporal_audit_results.yaml

Exit codes:
  0 — all checks pass
  1 — one or more checks failed
  2 — invocation error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = REPO_ROOT / "shared/contracts/passport"


def _validate(yaml_path: Path, schema_path: Path) -> list[str]:
    if not yaml_path.exists():
        return [f"missing: {yaml_path}"]
    if not schema_path.exists():
        return [f"missing schema: {schema_path}"]
    try:
        data = yaml.safe_load(yaml_path.read_text())
        schema = json.loads(schema_path.read_text())
        jsonschema.validate(data, schema)
        return []
    except jsonschema.ValidationError as exc:
        return [f"{yaml_path.name}: {exc.message} at {list(exc.absolute_path)}"]
    except Exception as exc:
        return [f"{yaml_path.name}: {exc}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--citation-provenance", type=Path, required=True)
    parser.add_argument("--temporal-audit", type=Path, required=True)
    args = parser.parse_args(argv)

    errors: list[str] = []
    errors.extend(_validate(args.timeline, SCHEMAS / "timeline.schema.json"))
    errors.extend(_validate(args.citation_provenance, SCHEMAS / "citation_provenance.schema.json"))
    errors.extend(_validate(args.temporal_audit, SCHEMAS / "temporal_audit_results.schema.json"))

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
