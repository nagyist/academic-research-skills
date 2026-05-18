#!/usr/bin/env python3
"""v3.9.4 Phase 4 → 5 boundary temporal integrity verifier.

5 passes per spec §3.2:
  P1 — Mode 1 future-as-past arithmetic (TEMPORAL-ARITHMETIC-IMPOSSIBLE)
  P2 — Mode 2 version-as-evidence-past anachronism (TEMPORAL-ANACHRONISTIC-CITATION)
  P3 — Mode 3 comparator unmaterialized (TEMPORAL-COMPARATOR-UNMATERIALIZED)
  P4 — Mode 4 causal inversion (TEMPORAL-CAUSAL-INVERSION)
  P5 — Mode 5 time-bomb deictic (TEMPORAL-DEICTIC)
  + TEMPORAL-METADATA-MISSING surfacing where ground truth is unavailable.

All findings advisory in v3.9.4 (CC1).
Inputs: finalized draft markdown with v3.7.3 <!--ref:slug--> markers, timeline.yaml, citation_provenance.yaml.
Output: phase4_composition/temporal_audit_results.yaml (machine-readable) + .md (human-readable, Task 17).

This Task 9 ships the scaffold. P1-P5 implementations land in Tasks 10-16. Markdown output in Task 17.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

DEICTIC_PATTERN = re.compile(
    r"\b(currently|now|at present|most recent|the latest|new(?:est)?|recently|"
    r"last\s+year|this\s+year|nowadays|presently|today|emerging|recent\s+cycle|"
    r"latest\s+available)\b",
    re.IGNORECASE,
)

MONTH_NAMES = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_REGEX = (
    r"\d{4}-\d{2}-\d{2}"
    r"|(?:" + MONTH_NAMES + r")\s+\d{4}"
    r"|(?:19|20)\d{2}"
)

PATTERN_A = re.compile(
    r"(?:as of|on|in|reported in|stated in|noted in)\s+"
    r"(?P<anchor>" + DATE_REGEX + r")"
    r".*?\b(?:had already|already|completed|finished|delivered)\b.*?"
    r"(?P<event>" + DATE_REGEX + r")",
    re.IGNORECASE | re.DOTALL,
)

MONTH_TO_NUM = {name.lower(): f"{i+1:02d}" for i, name in enumerate(MONTH_NAMES.split("|"))}
LAST_DAY = {"01": "31", "02": "28", "03": "31", "04": "30", "05": "31", "06": "30",
            "07": "31", "08": "31", "09": "30", "10": "31", "11": "30", "12": "31"}


def _date_to_interval(raw: str) -> tuple[str, str]:
    """Normalize a date capture into (start, end) ISO 8601 day strings.

    Handles 3 forms:
    - YYYY-MM-DD → (date, date) point interval
    - 'MonthName YYYY' → first of month .. last of month
    - YYYY → YYYY-01-01 .. YYYY-12-31
    """
    raw = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw, raw
    m = re.fullmatch(r"(" + MONTH_NAMES + r")\s+(\d{4})", raw, re.IGNORECASE)
    if m:
        mo = MONTH_TO_NUM[m.group(1).lower()]
        yr = m.group(2)
        return f"{yr}-{mo}-01", f"{yr}-{mo}-{LAST_DAY[mo]}"
    if re.fullmatch(r"(?:19|20)\d{2}", raw):
        return f"{raw}-01-01", f"{raw}-12-31"
    raise ValueError(f"unrecognized date format: {raw!r}")


def _next_finding_id(findings: list[dict]) -> int:
    """Compute the next sequential TF-NNN id (1-indexed) from existing findings."""
    counter = [int(f["finding_id"].split("-")[1]) for f in findings] or [0]
    return max(counter) + 1


def _pass_5_deictic(draft: str, findings: list[dict]) -> None:
    """P5 Mode 5 time-bomb deictic regex lint."""
    next_id = _next_finding_id(findings)

    # Build a line index for draft_locator
    lines = draft.splitlines(keepends=True)
    offsets: list[int] = []
    cur = 0
    for line in lines:
        offsets.append(cur)
        cur += len(line)

    for m in DEICTIC_PATTERN.finditer(draft):
        char_start = m.start()
        line_no = 0
        for i, off in enumerate(offsets):
            if off > char_start:
                break
            line_no = i
        line_text = lines[line_no].rstrip("\n") if line_no < len(lines) else ""

        findings.append({
            "finding_id": f"TF-{next_id:03d}",
            "finding_kind": "TEMPORAL-DEICTIC",
            "severity": "LOW",
            "mode": 5,
            "block_eligible": False,
            "draft_locator": {
                "file": "phase4_composition/draft.md",
                "line": line_no + 1,
                "sentence": line_text,
            },
            "matched_span": {
                "text": m.group(0),
                "char_start": m.start(),
                "char_end": m.end(),
            },
            "bound_refs": [],
            "bound_event": None,
            "bound_dates": None,
            "rationale": f"Deictic phrase '{m.group(0)}' anchors claim to writing time; rewrite to specific date or version identifier.",
            "suggested_fix": "Replace with 'as of YYYY-MM-DD' or a specific edition/year reference.",
        })
        next_id += 1


def _pass_1_arithmetic(draft: str, findings: list[dict]) -> None:
    """P1 Mode 1 future-as-past arithmetic. Pattern A only in Task 12; Pattern B in Task 13."""
    next_id = _next_finding_id(findings)

    for sentence in re.split(r"(?<=[.!?])\s+", draft):
        m = PATTERN_A.search(sentence)
        if not m:
            continue
        anchor_raw = m.group("anchor")
        event_raw = m.group("event")
        try:
            anchor_start, anchor_end = _date_to_interval(anchor_raw)
            event_start, event_end = _date_to_interval(event_raw)
        except ValueError:
            continue
        # Violation: event start strictly after anchor end
        if event_start > anchor_end:
            findings.append({
                "finding_id": f"TF-{next_id:03d}",
                "finding_kind": "TEMPORAL-ARITHMETIC-IMPOSSIBLE",
                "severity": "HIGH",
                "mode": 1,
                "block_eligible": True,
                "draft_locator": {
                    "file": "phase4_composition/draft.md",
                    "line": 1,
                    "sentence": sentence.strip(),
                },
                "matched_span": None,
                "bound_refs": [],
                "bound_event": None,
                "bound_dates": {
                    "left": {"role": "anchor",
                             "value": f"{anchor_start}..{anchor_end}",
                             "source": "draft_capture",
                             "ref_slug": None},
                    "right": {"role": "event",
                              "value": f"{event_start}..{event_end}",
                              "source": "draft_capture",
                              "ref_slug": None},
                },
                "rationale": (
                    f"Anchor '{anchor_raw}' ({anchor_start}..{anchor_end}) is before "
                    f"event '{event_raw}' ({event_start}..{event_end}); claim asserts event "
                    f"already complete at anchor time but event has not yet occurred."
                ),
                "suggested_fix": (
                    "Restate the claim to match the anchor's true time horizon, or hedge if the date is uncertain."
                ),
            })
            next_id += 1


def audit(draft: str, timeline: dict, citation_provenance: dict,
          report_reference_date: str, audit_run_id: str) -> dict:
    """Run the 5-pass verifier. Returns an aggregate matching temporal_audit_results.schema.json."""
    findings: list[dict] = []
    _pass_1_arithmetic(draft, findings)
    _pass_5_deictic(draft, findings)
    # P2-P4 implemented in subsequent tasks.
    return {
        "schema_version": "1.0",
        "audit_run_id": audit_run_id,
        "report_reference_date": report_reference_date,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v3.9.4 temporal integrity verifier (Phase 4 → 5 boundary)")
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--citation-provenance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-reference-date", required=True)
    parser.add_argument("--audit-run-id", required=True)
    args = parser.parse_args(argv)

    draft = args.draft.read_text()
    timeline = yaml.safe_load(args.timeline.read_text())
    citation_provenance = yaml.safe_load(args.citation_provenance.read_text())

    result = audit(draft, timeline, citation_provenance,
                   args.report_reference_date, args.audit_run_id)

    args.output.write_text(yaml.safe_dump(result, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
