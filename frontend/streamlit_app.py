import os
import requests
import pandas as pd
import streamlit as st

API_URL = os.getenv("EVENT_SYNC_API_URL", "http://localhost:8000")

st.set_page_config(page_title="Event Sync Dashboard", page_icon="📅", layout="wide")
st.title("📅 Event Sync Dashboard")
st.caption("Unified meeting view across CRM and Calendar sources")

@st.cache_data(ttl=15)
def fetch_json(path, params=None):
    response = requests.get(f"{API_URL}{path}", params=params, timeout=10)
    response.raise_for_status()
    return response.json()

# left, right = st.columns([5, 1])
# with right:
#     if st.button("🔄 Sync now", use_container_width=True):
#         try:
#             r = requests.post(f"{API_URL}/api/sync", timeout=20)
#             r.raise_for_status()
#             fetch_json.clear()
#             st.success("Sync completed")
#             st.rerun()
#         except requests.RequestException as exc:
#             st.error(f"Could not sync: {exc}")

try:
    stats = fetch_json("/api/meetings/stats")
    meetings_payload = fetch_json("/api/meetings")
    meetings = meetings_payload["meetings"]
except requests.RequestException as exc:
    st.error(f"Cannot connect to the API at {API_URL}. Start FastAPI first. Details: {exc}")
    st.stop()

cols = st.columns(5)
for col, label, value in zip(
    cols,
    ["Total meetings", "Matched", "CRM only", "Calendar only", "Conflicts"],
    [stats["total_meetings"], stats["matched"], stats["crm_only"], stats["calendar_only"], stats["conflicts"]],
):
    col.metric(label, value)

st.divider()
f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
with f1:
    search = st.text_input("Search meetings", placeholder="Title, client, company, owner...")
with f2:
    match_filter = st.selectbox("Reconciliation", ["All", "Matched", "CRM only", "Calendar only"])
with f3:
    source_filter = st.selectbox("Source", ["All", "crm", "calendar"])
with f4:
    conflict_filter = st.selectbox("Conflicts", ["All", "With conflicts", "No conflicts"])

filtered = meetings
if search:
    s = search.casefold()
    filtered = [m for m in filtered if s in " ".join(str(m.get(k) or "") for k in ("title","client","company","owner","location")).casefold()]
if match_filter != "All":
    target = {"Matched":"matched", "CRM only":"crm_only", "Calendar only":"calendar_only"}[match_filter]
    filtered = [m for m in filtered if m["match_status"] == target]
if source_filter != "All":
    filtered = [m for m in filtered if source_filter in m["sources"]]
if conflict_filter != "All":
    has = conflict_filter == "With conflicts"
    filtered = [m for m in filtered if bool(m["conflicts"]) == has]

st.subheader(f"Meetings ({len(filtered)})")
if filtered:
    table = pd.DataFrame([{
        "Date": m.get("date"),
        "Time": m.get("time"),
        "Meeting": m.get("title"),
        "Client / Company": " / ".join(x for x in [m.get("client"), m.get("company")] if x) or "—",
        "Owner": m.get("owner") or "—",
        "Location": m.get("location") or "—",
        "Sources": " + ".join(m["sources"]),
        "Reconciliation": m["match_status"].replace("_", " ").title(),
        "Conflicts": len(m["conflicts"]),
    } for m in filtered])
    st.dataframe(table, use_container_width=True, hide_index=True)
    labels = {f'{m.get("date") or "Undated"} | {m["title"]} | {m["id"]}': m for m in filtered}
    selected_label = st.selectbox("Inspect a meeting", list(labels))
    selected = labels[selected_label]
    st.markdown("### Meeting details")
    a, b, c = st.columns(3)
    a.write(f"**CRM ID:** {selected.get('crm_id') or '—'}")
    b.write(f"**Calendar ID:** {selected.get('calendar_id') or '—'}")
    c.write(f"**Match confidence:** {f'{selected["match_confidence"]:.0%}' if selected.get('match_confidence') is not None else 'N/A'}")
    st.write(f"**Status:** {selected.get('status') or '—'}")
    st.write(f"**Notes:** {selected.get('notes') or '—'}")
    if selected["conflicts"]:
        st.warning("Source conflicts detected")
        st.dataframe(pd.DataFrame(selected["conflicts"]), use_container_width=True, hide_index=True)
    else:
        st.success("No field conflicts detected for this meeting.")
    with st.expander("Field-level source provenance"):
        st.json(selected["provenance"])
    with st.expander("Original source records"):
        st.json(selected["raw"])
else:
    st.info("No meetings match the selected filters.")

st.divider()
tab1, tab2, tab3 = st.tabs(["Potential matches to review", "Possible same-source duplicates", "Ingestion errors"])
with tab1:
    candidates = fetch_json("/api/meetings/review")["candidates"]
    st.write(f"{len(candidates)} possible match(es) below the automatic threshold.")
    if candidates:
        st.dataframe(pd.DataFrame(candidates), use_container_width=True, hide_index=True)
with tab2:
    duplicates = fetch_json("/api/meetings/duplicates")["duplicates"]
    st.write(f"{len(duplicates)} possible duplicate pair(s). These are flagged, not automatically deleted.")
    if duplicates:
        st.dataframe(pd.DataFrame(duplicates), use_container_width=True, hide_index=True)
with tab3:
    errors = fetch_json("/api/sync/errors")["errors"]
    st.write(f"{len(errors)} ingestion error(s).")
    if errors:
        st.json(errors)
    else:
        st.success("No ingestion errors.")
