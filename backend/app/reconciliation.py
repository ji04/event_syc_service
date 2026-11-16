from __future__ import annotations

import re
import unicodedata
from datetime import datetime, date
from difflib import SequenceMatcher
from itertools import combinations
from typing import Any

from .config import AUTO_MATCH_THRESHOLD, REVIEW_THRESHOLD


def clean(value: Any) -> str:
    if value is None:
        return ""
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def similarity(a: Any, b: Any) -> float:
    aa, bb = clean(a), clean(b)
    if not aa or not bb:
        return 0.0
    if aa in bb or bb in aa:
        return 1.0
    return SequenceMatcher(None, aa, bb).ratio()


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m-%d/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def get_crm_datetime(record: dict) -> datetime | None:
    d = parse_date(record.get("meeting_date"))
    t = record.get("meeting_time")
    if not d or not t:
        return None
    try:
        parsed_time = datetime.strptime(str(t), "%H:%M").time()
        return datetime.combine(d, parsed_time)
    except ValueError:
        return None


def get_calendar_datetime(record: dict) -> datetime | None:
    return parse_datetime(record.get("start_time"))


def company_from_crm(record: dict) -> str:
    return clean(record.get("client_company"))


def calendar_external_domains(record: dict) -> set[str]:
    result = set()
    for attendee in record.get("attendees") or []:
        email = str(attendee).strip().lower()
        if "@" in email and not email.endswith("@firma.com"):
            result.add(email.split("@", 1)[1])
    return result


def company_signal(crm: dict, cal: dict) -> float:
    company = company_from_crm(crm)
    if not company:
        return 0.0
    haystack = clean(" ".join([
        str(cal.get("title") or ""),
        str(cal.get("description") or ""),
        " ".join(cal.get("attendees") or []),
    ]))
    if company and clean(company) in haystack:
        return 1.0
    # Compare company tokens with external attendee email domains and calendar title.
    tokens = [x for x in company.split() if len(x) > 3 and x not in {"partners", "capital", "group", "holdings", "wealth", "institutional"}]
    domain_text = " ".join(calendar_external_domains(cal))
    if tokens and any(token in haystack or token in domain_text for token in tokens):
        return 0.85
    client = clean(crm.get("client_name"))
    if client and client in haystack:
        return 0.85
    return 0.0


def title_signal(crm: dict, cal: dict) -> float:
    a = crm.get("subject")
    b = cal.get("title")
    return similarity(a, b)


def time_signal(crm: dict, cal: dict) -> float:
    cdt = get_crm_datetime(crm)
    adt = get_calendar_datetime(cal)
    if not cdt or not adt:
        return 0.35  # Missing time is unknown, not a hard mismatch.
    # Source A can be local-naive while Source B may be UTC-aware. Compare wall clock first;
    # a 5-hour offset is allowed with a reduced score to accommodate timezone representation.
    delta = abs((cdt.replace(tzinfo=None) - adt.replace(tzinfo=None)).total_seconds()) / 60
    if delta <= 15:
        return 1.0
    if delta <= 30:
        return 0.9
    if delta <= 60:
        return 0.75
    if delta <= 360:
        return 0.45
    return 0.0


def date_signal(crm: dict, cal: dict) -> float:
    cd = parse_date(crm.get("meeting_date"))
    ad = parse_date(cal.get("start_time"))
    return 1.0 if cd and ad and cd == ad else 0.0


def location_signal(crm: dict, cal: dict) -> float:
    a, b = crm.get("location"), cal.get("location")
    if not a or not b:
        return 0.35
    return similarity(a, b)


def score_pair(crm: dict, cal: dict) -> tuple[float, dict]:
    parts = {
        "date": date_signal(crm, cal),
        "client_or_attendee": company_signal(crm, cal),
        "title": title_signal(crm, cal),
        "time": time_signal(crm, cal),
        "location": location_signal(crm, cal),
    }
    weights = {"date": .25, "client_or_attendee": .30, "title": .20, "time": .17, "location": .08}
    score = sum(parts[k] * weights[k] for k in weights)
    # Internal meetings often have different shorthand titles across systems.
    # Exact date/time and room evidence is a strong secondary signal for these records.
    internal_context = bool(
        clean(crm.get("meeting_type")) == "internal"
        and parts["date"] == 1.0
        and parts["time"] == 1.0
        and parts["location"] >= 0.8
    )
    if internal_context:
        score = min(1.0, score + 0.18)
        parts["internal_context"] = 1.0
    # A different calendar date is a strong exclusion to avoid matching follow-ups.
    if parts["date"] == 0:
        score = 0.0
    return round(score, 4), parts


def source_fields(record: dict, source: str) -> dict:
    if source == "crm":
        return {
            "title": record.get("subject"),
            "client": record.get("client_name"),
            "company": record.get("client_company"),
            "owner": record.get("relationship_owner"),
            "date": record.get("meeting_date"),
            "time": record.get("meeting_time"),
            "meeting_type": record.get("meeting_type"),
            "location": record.get("location"),
            "notes": record.get("notes"),
            "status": record.get("status"),
        }
    return {
        "title": record.get("title"),
        "client": None,
        "company": None,
        "owner": record.get("organizer"),
        "date": record.get("start_time"),
        "time": record.get("start_time"),
        "meeting_type": None,
        "location": record.get("location"),
        "notes": record.get("description"),
        "status": record.get("status"),
        "attendees": record.get("attendees") or [],
        "end_time": record.get("end_time"),
        "is_recurring": record.get("is_recurring", False),
    }


def find_same_source_duplicates(records: list[dict], source: str) -> list[dict]:
    """Flag likely duplicates for review; never silently delete non-identical records."""
    candidates = []
    for left, right in combinations(records, 2):
        if source == "crm":
            ld, rd = parse_date(left.get("meeting_date")), parse_date(right.get("meeting_date"))
            lt, rt = get_crm_datetime(left), get_crm_datetime(right)
            ltitle, rtitle = left.get("subject"), right.get("subject")
            lkey, rkey = left.get("crm_id"), right.get("crm_id")
            la, ra = left.get("client_company"), right.get("client_company")
        else:
            ld, rd = parse_date(left.get("start_time")), parse_date(right.get("start_time"))
            lt, rt = get_calendar_datetime(left), get_calendar_datetime(right)
            ltitle, rtitle = left.get("title"), right.get("title")
            lkey, rkey = left.get("event_id"), right.get("event_id")
            la, ra = " ".join(left.get("attendees") or []), " ".join(right.get("attendees") or [])
        if not ld or ld != rd:
            continue
        title_score = similarity(ltitle, rtitle)
        entity_score = similarity(la, ra)
        minutes = abs((lt.replace(tzinfo=None) - rt.replace(tzinfo=None)).total_seconds()) / 60 if lt and rt else 9999
        if title_score >= .30 and entity_score >= .45 and minutes <= 60:
            candidates.append({
                "source": source, "record_ids": [lkey, rkey],
                "reason": "Similar title and attendee/client evidence on the same date with close start times; manual review required.",
                "confidence": round(.55 * title_score + .25 * entity_score + .20 * max(0, 1 - minutes / 90), 3),
                "action": "review_only",
            })
    return candidates


def build_meetings(crm_records: list[dict], calendar_records: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Greedy one-to-one reconciliation with explicit review candidates and field provenance."""
    pairings = []
    review_candidates = []
    for ci, crm in enumerate(crm_records):
        for ai, cal in enumerate(calendar_records):
            score, breakdown = score_pair(crm, cal)
            if score >= REVIEW_THRESHOLD:
                pairings.append((score, ci, ai, breakdown))
                if score < AUTO_MATCH_THRESHOLD:
                    review_candidates.append({
                        "crm_id": crm.get("crm_id"),
                        "calendar_id": cal.get("event_id"),
                        "confidence": score,
                        "score_breakdown": breakdown,
                        "reason": "Possible match below automatic matching threshold.",
                    })

    # Highest confidence first; each source record can be assigned only once.
    pairings.sort(reverse=True, key=lambda x: x[0])
    used_crm, used_cal, matched = set(), set(), {}
    for score, ci, ai, breakdown in pairings:
        if ci in used_crm or ai in used_cal:
            continue
        if score < AUTO_MATCH_THRESHOLD:
            continue
        used_crm.add(ci)
        used_cal.add(ai)
        matched[ci] = (ai, score, breakdown)

    meetings = []
    for ci, crm in enumerate(crm_records):
        crm_id = crm.get("crm_id") or f"CRM-INDEX-{ci}"
        if ci in matched:
            ai, score, breakdown = matched[ci]
            cal = calendar_records[ai]
            meetings.append(make_meeting(crm, cal, score, breakdown))
        else:
            meetings.append(make_meeting(crm, None, None, None))

    for ai, cal in enumerate(calendar_records):
        if ai not in used_cal:
            meetings.append(make_meeting(None, cal, None, None))

    duplicates = find_same_source_duplicates(crm_records, "crm") + find_same_source_duplicates(calendar_records, "calendar")
    # Sort by normalized date, malformed dates last.
    meetings.sort(key=lambda m: (m.get("date") or "9999-99-99", m.get("time") or "99:99", m["id"]))
    return meetings, review_candidates, duplicates


def make_meeting(crm: dict | None, cal: dict | None, confidence: float | None, breakdown: dict | None) -> dict:
    crm_fields = source_fields(crm, "crm") if crm else {}
    cal_fields = source_fields(cal, "calendar") if cal else {}
    conflicts = []
    # Display CRM's value when present, but preserve both values and flag disagreement.
    field_map = {}
    keys = ["title", "location", "status", "notes"]
    for key in keys:
        cv, av = crm_fields.get(key), cal_fields.get(key)
        if cv not in (None, "") and av not in (None, "") and clean(cv) != clean(av):
            conflicts.append({"field": key, "crm_value": cv, "calendar_value": av})
        field_map[key] = cv if cv not in (None, "") else av

    raw_date = crm_fields.get("date") or cal_fields.get("date")
    normalized = parse_date(raw_date)
    date_value = normalized.isoformat() if normalized else (str(raw_date)[:10] if raw_date else None)
    raw_time = crm_fields.get("time")
    if not raw_time and cal_fields.get("time"):
        raw_time = str(cal_fields["time"])[11:16]
    crm_id = crm.get("crm_id") if crm else None
    cal_id = cal.get("event_id") if cal else None
    source_list = [s for s, record in (("crm", crm), ("calendar", cal)) if record]
    meeting_id = f"{crm_id or 'NOCRM'}__{cal_id or 'NOCAL'}"
    if crm and cal:
        match_status = "matched" if (confidence or 0) >= AUTO_MATCH_THRESHOLD else "review"
    else:
        match_status = "crm_only" if crm else "calendar_only"

    provenance = {}
    for key in set(crm_fields) | set(cal_fields):
        provenance[key] = {
            "crm": crm_fields.get(key),
            "calendar": cal_fields.get(key),
            "selected": "crm" if crm_fields.get(key) not in (None, "") else ("calendar" if cal_fields.get(key) not in (None, "") else None),
        }

    return {
        "id": meeting_id,
        "crm_id": crm_id,
        "calendar_id": cal_id,
        "title": field_map.get("title") or "Untitled meeting",
        "client": crm_fields.get("client"),
        "company": crm_fields.get("company"),
        "owner": crm_fields.get("owner") or cal_fields.get("owner"),
        "date": date_value,
        "time": raw_time,
        "location": field_map.get("location"),
        "status": field_map.get("status"),
        "notes": field_map.get("notes"),
        "sources": source_list,
        "match_status": match_status,
        "match_confidence": confidence,
        "score_breakdown": breakdown or {},
        "conflicts": conflicts,
        "provenance": provenance,
        "raw": {"crm": crm, "calendar": cal},
        "is_recurring": bool(cal_fields.get("is_recurring", False)),
        "attendees": cal_fields.get("attendees", []),
    }
