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
from datetime import date
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

PATTERN_B = re.compile(
    r"(?P<event>" + DATE_REGEX + r")"
    r".*?\b(?:will be|to be|scheduled for|forthcoming|upcoming|planned)\b.*?"
    r"(?:as of|in|by)\s+"
    r"(?P<anchor>" + DATE_REGEX + r")",
    re.IGNORECASE | re.DOTALL,
)

REF_MARKER_PATTERN = re.compile(r"<!--ref:([A-Za-z][A-Za-z0-9_:-]*)-->")

COMPARATOR_FORM_A = re.compile(
    r"(?P<adj>prior|previous|earlier|older|preceding)\s+"
    r"(?P<noun>edition|version|edition\s+\(\d{4}\)|version\s+\(\d{4}\))",
    re.IGNORECASE,
)
COMPARATOR_FORM_B = re.compile(
    r"\b(?P<year>(?:19|20)\d{2})\s+"
    r"(?P<noun>edition|version|standard|handbook|guideline)\b",
    re.IGNORECASE,
)
COMPARATOR_FORM_C = re.compile(
    r"(?P<noun>edition|version|standard)\s+(?:of|from)\s+"
    r"(?P<year>(?:19|20)\d{2})\b",
    re.IGNORECASE,
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


def _date_diff_days(a: str, b: str) -> int:
    """Days between two YYYY-MM-DD strings (a - b)."""
    da = date.fromisoformat(a)
    db = date.fromisoformat(b)
    return (da - db).days


def _sentence_around(draft: str, char_pos: int) -> str:
    """Extract the sentence containing char_pos."""
    pre = draft[:char_pos]
    post = draft[char_pos:]
    # Find last sentence terminator before char_pos
    m_pre = re.search(r"[.!?]\s+(?=\S)", pre[::-1])
    start = char_pos - m_pre.start() if m_pre else 0
    # Find next sentence terminator at/after char_pos
    m_post = re.search(r"[.!?](\s|$)", post)
    end = char_pos + m_post.end() if m_post else len(draft)
    return draft[start:end].strip()


def _next_finding_id(findings: list[dict]) -> int:
    """Compute the next sequential TF-NNN id (1-indexed) from existing findings."""
    counter = [int(f["finding_id"].split("-")[1]) for f in findings] or [0]
    return max(counter) + 1


def _pass_2_anachronism(draft: str, timeline: dict, findings: list[dict]) -> None:
    """P2 Mode 2 version-as-evidence-past anachronism.

    For each <!--ref:slug--> marker:
    1. Lookup slug in timeline sources. Absent → emit TEMPORAL-METADATA-MISSING.
    2. Lookup effective_date_range. Absent or start unverified/low → emit METADATA-MISSING.
    3. Find nearest event date in ±200 chars around the ref marker.
    4. Predicate: start > event.end → emit TEMPORAL-ANACHRONISTIC-CITATION.
    """
    sources_by_key = {s["citation_key"]: s for s in timeline.get("sources", [])}

    for m_ref in REF_MARKER_PATTERN.finditer(draft):
        slug = m_ref.group(1)
        source = sources_by_key.get(slug)

        next_id = _next_finding_id(findings)

        if source is None:
            findings.append({
                "finding_id": f"TF-{next_id:03d}",
                "finding_kind": "TEMPORAL-METADATA-MISSING",
                "severity": "LOW",
                "mode": None,
                "block_eligible": False,
                "draft_locator": {
                    "file": "phase4_composition/draft.md",
                    "line": 1,
                    "sentence": _sentence_around(draft, m_ref.start()),
                },
                "matched_span": None,
                "bound_refs": [{"ref_slug": slug, "timeline_entry": None}],
                "bound_event": None,
                "bound_dates": None,
                "rationale": f"<!--ref:{slug}--> has no entry in timeline.yaml; cannot verify temporal claims against this citation.",
                "suggested_fix": None,
            })
            continue

        edr = source.get("effective_date_range")
        if not edr:
            findings.append({
                "finding_id": f"TF-{next_id:03d}",
                "finding_kind": "TEMPORAL-METADATA-MISSING",
                "severity": "LOW",
                "mode": None,
                "block_eligible": False,
                "draft_locator": {
                    "file": "phase4_composition/draft.md", "line": 1,
                    "sentence": _sentence_around(draft, m_ref.start()),
                },
                "matched_span": None,
                "bound_refs": [{"ref_slug": slug, "timeline_entry": slug}],
                "bound_event": None,
                "bound_dates": None,
                "rationale": f"{slug} has no effective_date_range; anachronism check cannot run.",
                "suggested_fix": None,
            })
            continue

        start = edr["start"]
        start_conf = start.get("provenance", {}).get("confidence")
        if start.get("value") is None or start_conf in {"unverified", "low"}:
            findings.append({
                "finding_id": f"TF-{next_id:03d}",
                "finding_kind": "TEMPORAL-METADATA-MISSING",
                "severity": "LOW",
                "mode": None,
                "block_eligible": False,
                "draft_locator": {
                    "file": "phase4_composition/draft.md", "line": 1,
                    "sentence": _sentence_around(draft, m_ref.start()),
                },
                "matched_span": None,
                "bound_refs": [{"ref_slug": slug, "timeline_entry": slug}],
                "bound_event": None,
                "bound_dates": None,
                "rationale": f"{slug} effective_date_range.start absent or low/unverified confidence; cannot verify anachronism.",
                "suggested_fix": None,
            })
            continue

        # Find nearest event date in ±200 chars around ref marker
        # Exclude dates that overlap the ref marker itself (slug digits are not event dates)
        window_start = max(0, m_ref.start() - 200)
        window_end = min(len(draft), m_ref.end() + 200)
        window = draft[window_start:window_end]
        date_pattern = re.compile(DATE_REGEX, re.IGNORECASE)
        # Compute ref marker span relative to window
        ref_in_window_start = m_ref.start() - window_start
        ref_in_window_end = m_ref.end() - window_start
        event_dates = [
            d for d in date_pattern.finditer(window)
            if d.end() <= ref_in_window_start or d.start() >= ref_in_window_end
        ]
        if not event_dates:
            continue  # no event date → no finding

        # Pick closest to the ref marker position within the window
        rel_ref = m_ref.start() - window_start
        nearest = min(event_dates, key=lambda d: abs(d.start() - rel_ref))
        event_raw = nearest.group(0)
        try:
            event_start, event_end = _date_to_interval(event_raw)
            edr_start_start, _ = _date_to_interval(start["value"])
        except ValueError:
            continue

        # Future-version check: start > event.end
        if edr_start_start > event_end:
            findings.append({
                "finding_id": f"TF-{next_id:03d}",
                "finding_kind": "TEMPORAL-ANACHRONISTIC-CITATION",
                "severity": "HIGH",
                "mode": 2,
                "block_eligible": True,
                "draft_locator": {
                    "file": "phase4_composition/draft.md", "line": 1,
                    "sentence": _sentence_around(draft, m_ref.start()),
                },
                "matched_span": None,
                "bound_refs": [{"ref_slug": slug, "timeline_entry": slug}],
                "bound_event": {"event_id": None, "date": f"{event_start}..{event_end}"},
                "bound_dates": None,
                "rationale": (
                    f"{slug} effective_date_range starts {start['value']}, after cited "
                    f"event {event_raw} ({event_start}..{event_end}). Cited version postdates the event."
                ),
                "suggested_fix": f"Cite the version of the source that was in effect during {event_raw}.",
            })


def _pass_3_comparator(draft: str, timeline: dict, findings: list[dict]) -> None:
    """P3 Mode 3 comparator unmaterialized.

    Detects prose comparator framing (Form A: 'prior edition', Form B: 'YYYY edition',
    Form C: 'edition of YYYY'). For each match, binds version_family_id via the
    nearest <!--ref:slug--> in the sentence/paragraph. If no timeline entry in that
    family has a matching year, emits TEMPORAL-COMPARATOR-UNMATERIALIZED.
    """
    sources_by_key = {s["citation_key"]: s for s in timeline.get("sources", [])}
    sources_by_family: dict[str, list[dict]] = {}
    for s in timeline.get("sources", []):
        fam = s.get("version_family_id")
        if fam:
            sources_by_family.setdefault(fam, []).append(s)

    for sentence in re.split(r"(?<=[.!?])\s+", draft):
        sentence_emitted = False
        for pattern_name, pat in [("A", COMPARATOR_FORM_A), ("B", COMPARATOR_FORM_B), ("C", COMPARATOR_FORM_C)]:
            if sentence_emitted:
                break
            for m in pat.finditer(sentence):
                # Resolve version_family_id via ref marker in sentence
                refs_in_sentence = REF_MARKER_PATTERN.findall(sentence)
                if not refs_in_sentence:
                    continue  # binding ambiguous — emit no finding
                bound_slug = refs_in_sentence[0]
                bound_source = sources_by_key.get(bound_slug)
                if not bound_source or not bound_source.get("version_family_id"):
                    continue
                family = bound_source["version_family_id"]

                # Determine comparator year
                if pattern_name == "A":
                    year_match = re.search(
                        r"\b(?:19|20)\d{2}\b",
                        sentence[max(0, m.start() - 60):min(len(sentence), m.end() + 60)],
                    )
                    if not year_match:
                        continue
                    comparator_year = year_match.group(0)
                else:
                    comparator_year = m.group("year")

                # Check whether any source in this family has matching published_date year
                family_sources = sources_by_family.get(family, [])
                matched = False
                for s in family_sources:
                    pd = s.get("published_date")
                    if pd and pd.get("value") and comparator_year in pd["value"]:
                        matched = True
                        break

                if not matched:
                    next_id = _next_finding_id(findings)
                    findings.append({
                        "finding_id": f"TF-{next_id:03d}",
                        "finding_kind": "TEMPORAL-COMPARATOR-UNMATERIALIZED",
                        "severity": "MEDIUM",
                        "mode": 3,
                        "block_eligible": False,
                        "draft_locator": {
                            "file": "phase4_composition/draft.md", "line": 1,
                            "sentence": sentence.strip(),
                        },
                        "matched_span": {
                            "text": m.group(0),
                            "char_start": m.start(),
                            "char_end": m.end(),
                        },
                        "bound_refs": [{"ref_slug": bound_slug, "timeline_entry": bound_slug}],
                        "bound_event": None,
                        "bound_dates": None,
                        "rationale": (
                            f"Comparator '{m.group(0)}' (Form {pattern_name}, year={comparator_year}) "
                            f"references version family '{family}' but no timeline entry exists for that year. "
                            f"v3.9.4 reports this as claim-unsupported; v3.10 CC5 may escalate to phantom."
                        ),
                        "suggested_fix": (
                            f"Either add a timeline entry for the {comparator_year} version of {family}, "
                            f"or rewrite the prose to remove the comparator claim."
                        ),
                    })
                    sentence_emitted = True
                    break


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
    """P1 Mode 1 future-as-past arithmetic.

    Pattern A: retrospective claim '(as of X) ... had already (Y)'; violation when event Y > anchor X.
    Pattern B: prospective claim 'X (will be) ... (as of Y)'; violation when event X <= anchor Y.

    If multiple violations match in the same sentence, emit the one with the largest
    |event.start - anchor.end| gap (most clearly impossible).
    """
    next_id = _next_finding_id(findings)

    for sentence in re.split(r"(?<=[.!?])\s+", draft):
        violations = []
        m_a = PATTERN_A.search(sentence)
        if m_a:
            anchor_raw = m_a.group("anchor")
            event_raw = m_a.group("event")
            try:
                anchor_start, anchor_end = _date_to_interval(anchor_raw)
                event_start, event_end = _date_to_interval(event_raw)
            except ValueError:
                pass
            else:
                if event_start > anchor_end:
                    violations.append(("A", anchor_raw, event_raw,
                                       anchor_start, anchor_end, event_start, event_end))

        m_b = PATTERN_B.search(sentence)
        if m_b:
            event_raw = m_b.group("event")
            anchor_raw = m_b.group("anchor")
            try:
                anchor_start, anchor_end = _date_to_interval(anchor_raw)
                event_start, event_end = _date_to_interval(event_raw)
            except ValueError:
                pass
            else:
                # Pattern B violation: forthcoming event already past at anchor time
                if event_start <= anchor_end:
                    violations.append(("B", anchor_raw, event_raw,
                                       anchor_start, anchor_end, event_start, event_end))

        if not violations:
            continue

        # Emit one finding per sentence — pick the largest-gap violation.
        violations.sort(key=lambda v: abs(_date_diff_days(v[5], v[4])), reverse=True)
        which, anchor_raw, event_raw, anchor_start, anchor_end, event_start, event_end = violations[0]
        rationale = (
            f"Pattern {which}: anchor '{anchor_raw}' ({anchor_start}..{anchor_end}) "
            f"{'before' if which == 'A' else 'after'} event '{event_raw}' "
            f"({event_start}..{event_end}); "
            + ("event has not yet occurred at anchor time" if which == "A"
               else "forthcoming event already past at anchor time")
        )
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
                         "source": "draft_capture", "ref_slug": None},
                "right": {"role": "event",
                          "value": f"{event_start}..{event_end}",
                          "source": "draft_capture", "ref_slug": None},
            },
            "rationale": rationale,
            "suggested_fix": "Restate the claim to match the anchor's true time horizon, or hedge.",
        })
        next_id += 1


def audit(draft: str, timeline: dict, citation_provenance: dict,
          report_reference_date: str, audit_run_id: str) -> dict:
    """Run the 5-pass verifier. Returns an aggregate matching temporal_audit_results.schema.json."""
    findings: list[dict] = []
    _pass_1_arithmetic(draft, findings)
    _pass_2_anachronism(draft, timeline, findings)
    _pass_3_comparator(draft, timeline, findings)
    _pass_5_deictic(draft, findings)
    # P4 implemented in Task 16.
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
