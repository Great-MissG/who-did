import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone

API_BASE = "https://isp.beans.ai/enterprise/v1/lists/status_logs"
API_RAW = "https://isp.beans.ai/enterprise/v1/lists/items/{list_item_id}/raw_status_logs"
AUTH = st.secrets["AUTH"]
FIELDS = ["time", "type", "description", "status"]
ROW_HEIGHT = 35
HEADER_HEIGHT = 38


def ts_to_time(ms):
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone()
    tz_full = dt.strftime("%Z")
    tz_abbr = tz_full if len(tz_full) <= 5 else "".join(w[0] for w in tz_full.split())
    return dt.strftime(f"%m-%d %H:%M ") + tz_abbr


def extract_rows(data):
    if isinstance(data, list):
        rows = []
        for item in data:
            if isinstance(item, dict):
                row = {}
                if "tsMillis" in item:
                    row["tsMillis"] = item["tsMillis"]
                    row["time"] = ts_to_time(item["tsMillis"])
                for f in ["type", "description"]:
                    if f in item:
                        row[f] = item[f]
                log = item.get("log", {})
                if isinstance(log, dict):
                    for f in ["listItemId", "status"]:
                        if f in log:
                            row[f] = log[f]
                if row:
                    rows.append(row)
        if rows:
            return rows
    if isinstance(data, dict):
        for v in data.values():
            result = extract_rows(v)
            if result:
                return result
    return []


st.markdown("""
<style>
div[data-testid="stButton"] button {
    background-color: #4A90D9;
    color: white;
    border: none;
}
div[data-testid="stButton"] button:hover {
    background-color: #357ABD;
    color: white;
}
</style>
""", unsafe_allow_html=True)

st.title("Tracking Status Lookup")

with st.form("search_form"):
    tracking_id = st.text_input("Enter Tracking ID", placeholder="e.g. ABC123456")
    submitted = st.form_submit_button("Search")

if submitted and tracking_id:
    with st.spinner("Fetching status..."):
        try:
            resp = requests.get(
                API_BASE,
                params={"tracking_id": tracking_id, "readable": "true"},
                headers={"Authorization": AUTH},
                timeout=15,
            )
            resp.raise_for_status()
            rows = extract_rows(resp.json())
            if rows:
                df = pd.DataFrame(rows)
                for col in FIELDS + ["listItemId", "tsMillis"]:
                    if col not in df.columns:
                        df[col] = ""
                st.session_state["df"] = df
            else:
                st.warning("No data found.")
        except requests.exceptions.HTTPError as e:
            st.error(f"HTTP error: {e.response.status_code} — {e.response.text}")
        except requests.exceptions.RequestException as e:
            st.error(f"Request failed: {e}")

def fetch_tags(list_item_id, selected_ts):
    try:
        raw_resp = requests.get(
            API_RAW.format(list_item_id=list_item_id),
            headers={"Authorization": AUTH},
            timeout=15,
        )
        raw_resp.raise_for_status()
        items = raw_resp.json().get("listItemStatusLogs", [])
        for item in items:
            if isinstance(item, dict) and item.get("tsMillis") == int(selected_ts):
                return item.get("tags", [])
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Request failed: {e}")
        return None


if "df" in st.session_state:
    df = st.session_state["df"]

    COL_W = [2, 1.2, 3.5, 1.2, 1]
    header = st.columns(COL_W)
    for col, label in zip(header, ["Time", "Type", "Description", "Status", ""]):
        col.markdown(f"<span style='font-weight:600;color:#888;font-size:0.8em'>{label}</span>", unsafe_allow_html=True)

    for i, row in df.iterrows():
        cols = st.columns(COL_W)
        cols[0].write(row.get("time", ""))
        cols[1].write(row.get("type", ""))
        cols[2].write(row.get("description", ""))
        cols[3].write(row.get("status", ""))
        if cols[4].button("Who Did", key=f"who_did_{i}", use_container_width=True):
            st.session_state["selected_row"] = row

    if "selected_row" in st.session_state:
        st.divider()
        row = st.session_state["selected_row"]
        list_item_id = row.get("listItemId", "")
        selected_ts = row.get("tsMillis", "")
        if list_item_id:
            st.markdown(f"**Tags** · `{list_item_id}`")
            with st.spinner("Fetching..."):
                tags = fetch_tags(list_item_id, selected_ts)
            if tags is not None:
                st.table(pd.DataFrame(tags))
            else:
                st.warning("No matching tags found.")
