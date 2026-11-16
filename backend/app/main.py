from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from .service import get_sync_result, refresh_sync_result

app = FastAPI(
    title="Event Sync Service",
    description="Reconciles CRM and calendar meeting records with source provenance and conflict visibility.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/meetings")
def list_meetings(
    q: str | None = Query(default=None, description="Search title, client, company, owner or location"),
    source: str | None = Query(default=None, description="crm or calendar"),
    status: str | None = Query(default=None, description="matched, crm_only, calendar_only, review"),
    has_conflicts: bool | None = None,
):
    meetings = get_sync_result()["meetings"]
    if q:
        needle = q.casefold()
        meetings = [m for m in meetings if needle in " ".join(str(m.get(k) or "") for k in ("title","client","company","owner","location")).casefold()]
    if source:
        meetings = [m for m in meetings if source.lower() in m["sources"]]
    if status:
        meetings = [m for m in meetings if m["match_status"] == status]
    if has_conflicts is not None:
        meetings = [m for m in meetings if bool(m["conflicts"]) == has_conflicts]
    return {"count": len(meetings), "meetings": meetings}


@app.get("/api/meetings/conflicts")
def conflicts():
    meetings = get_sync_result()["meetings"]
    return {"count": sum(bool(m["conflicts"]) for m in meetings),
            "meetings": [m for m in meetings if m["conflicts"]]}


@app.get("/api/meetings/review")
def review_candidates():
    result = get_sync_result()
    return {"count": len(result["review_candidates"]), "candidates": result["review_candidates"]}


@app.get("/api/meetings/duplicates")
def potential_duplicates():
    result = get_sync_result()
    return {"count": len(result["potential_duplicates"]), "duplicates": result["potential_duplicates"]}


@app.get("/api/meetings/stats")
def stats():
    result = get_sync_result()
    meetings = result["meetings"]
    return {
        "total_meetings": len(meetings),
        "matched": sum(m["match_status"] == "matched" for m in meetings),
        "crm_only": sum(m["match_status"] == "crm_only" for m in meetings),
        "calendar_only": sum(m["match_status"] == "calendar_only" for m in meetings),
        "conflicts": sum(bool(m["conflicts"]) for m in meetings),
        "review_candidates": len(result["review_candidates"]),
        "potential_duplicates": len(result["potential_duplicates"]),
        "source_counts": result["source_counts"],
        "ingestion_errors": len(result["ingestion_errors"]),
    }


@app.get("/api/sync/errors")
def sync_errors():
    return {"errors": get_sync_result()["ingestion_errors"]}


@app.post("/api/sync")
def sync():
    result = refresh_sync_result()
    meetings = result["meetings"]
    return {
        "total_meetings": len(meetings),
        "matched": sum(m["match_status"] == "matched" for m in meetings),
        "crm_only": sum(m["match_status"] == "crm_only" for m in meetings),
        "calendar_only": sum(m["match_status"] == "calendar_only" for m in meetings),
        "conflicts": sum(bool(m["conflicts"]) for m in meetings),
        "review_candidates": len(result["review_candidates"]),
        "potential_duplicates": len(result["potential_duplicates"]),
        "ingestion_errors": len(result["ingestion_errors"]),
    }


@app.get("/api/meetings/{meeting_id}")
def meeting_detail(meeting_id: str):
    for meeting in get_sync_result()["meetings"]:
        if meeting["id"] == meeting_id:
            return meeting
    raise HTTPException(status_code=404, detail="Meeting not found")

