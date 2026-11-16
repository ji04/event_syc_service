from backend.app.reconciliation import build_meetings, parse_date, score_pair


def test_malformed_date_is_supported():
    assert parse_date("03-15/2025").isoformat() == "2025-03-15"


def test_different_dates_do_not_match():
    crm = {"subject": "Follow up", "meeting_date": "2025-03-10", "meeting_time": "10:00"}
    cal = {"title": "Follow up", "start_time": "2025-03-11T10:00:00"}
    score, _ = score_pair(crm, cal)
    assert score == 0


def test_unmatched_records_are_preserved():
    meetings, _, _ = build_meetings(
        [{"crm_id": "C1", "subject": "Only CRM", "meeting_date": "2025-03-10"}],
        [{"event_id": "A1", "title": "Only Calendar", "start_time": "2025-03-11T10:00:00"}],
    )
    assert len(meetings) == 2
    assert {m["match_status"] for m in meetings} == {"crm_only", "calendar_only"}


def test_matching_preserves_conflicts():
    crm = [{
        "crm_id": "C1", "subject": "Portfolio Review", "client_name": "David Park",
        "client_company": "Meridian Capital", "meeting_date": "2025-03-10",
        "meeting_time": "14:00", "location": "In-Person", "status": "Completed"
    }]
    cal = [{
        "event_id": "A1", "title": "Portfolio Review - Meridian Capital",
        "attendees": ["david.park@meridiancap.com"], "start_time": "2025-03-10T14:00:00",
        "location": "Zoom", "status": "confirmed"
    }]
    meetings, _, _ = build_meetings(crm, cal)
    assert len(meetings) == 1
    assert meetings[0]["match_status"] == "matched"
    assert any(c["field"] == "location" for c in meetings[0]["conflicts"])
