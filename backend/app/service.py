from functools import lru_cache
from .config import CRM_FILE, CALENDAR_FILE
from .ingestion import load_json_records
from .reconciliation import build_meetings


@lru_cache(maxsize=1)
def get_sync_result() -> dict:
    crm, crm_errors = load_json_records(CRM_FILE, "crm")
    calendar, calendar_errors = load_json_records(CALENDAR_FILE, "calendar")
    meetings, review_candidates, duplicates = build_meetings(crm, calendar)
    return {
        "meetings": meetings,
        "review_candidates": review_candidates,
        "potential_duplicates": duplicates,
        "ingestion_errors": crm_errors + calendar_errors,
        "source_counts": {"crm": len(crm), "calendar": len(calendar)},
    }


def refresh_sync_result() -> dict:
    get_sync_result.cache_clear()
    return get_sync_result()
