from pydantic import BaseModel
from typing import Any


class SyncResponse(BaseModel):
    total_meetings: int
    matched: int
    crm_only: int
    calendar_only: int
    conflicts: int
    review_candidates: int
    potential_duplicates: int
    ingestion_errors: int


class MeetingListResponse(BaseModel):
    count: int
    meetings: list[dict[str, Any]]
