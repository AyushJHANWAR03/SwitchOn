"""Streamlit Dashboard UI."""
import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
import os

# Configuration
API_URL = os.getenv('API_URL', 'http://localhost:8000')

st.set_page_config(
    page_title="SwitchOn Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("📊 SwitchOn - Production Monitoring Dashboard")
st.markdown("---")

# Check API connection
try:
    health_response = requests.get(f"{API_URL}/health", timeout=2)
    if health_response.status_code != 200:
        st.error("⚠️ API is not responding correctly")
        st.stop()
except Exception as e:
    st.error(f"❌ Cannot connect to API at {API_URL}")
    st.info("Make sure the FastAPI backend is running on port 8000")
    st.stop()

# Auto-refresh
refresh_interval = st.sidebar.slider("Auto-refresh (seconds)", 5, 60, 10)
auto_refresh = st.sidebar.checkbox("Enable Auto-refresh", value=True)

# Fetch data
@st.cache_data(ttl=refresh_interval)
def fetch_alerts(status=None):
    """Fetch alerts from API."""
    params = {}
    if status:
        params["status"] = status
    response = requests.get(f"{API_URL}/api/alerts", params=params)
    if response.status_code == 200:
        return response.json()
    return []


@st.cache_data(ttl=refresh_interval)
def fetch_metrics_summary():
    """Fetch summary metrics."""
    response = requests.get(f"{API_URL}/api/metrics/summary")
    if response.status_code == 200:
        return response.json()
    return {}


# Main layout
st.subheader("🚨 Active Alerts")
alerts = fetch_alerts(status="active")

if alerts:
    for alert in alerts[:5]:  # Show top 5
        severity_color = {
            "info": "🔵",
            "warning": "🟡",
            "critical": "🔴"
        }.get(alert["severity"], "⚪")

        with st.expander(f"{severity_color} **{alert['severity'].upper()}** - Line {alert['line_id']} - Defect Rate: {alert['value']*100:.1f}%"):
            col1, col2, col3 = st.columns([2, 2, 1])

            with col1:
                st.markdown(f"**Reason:** {alert['reason']}")
                st.markdown(f"**Created:** {alert['created_at']}")
                st.markdown(f"**Baseline:** {alert.get('baseline', 0)*100:.1f}%")

            with col2:
                st.markdown(f"**Status:** {alert['status']}")
                if alert.get('acknowledged_by'):
                    st.markdown(f"**Acknowledged by:** {alert['acknowledged_by']}")
                if alert.get('assigned_to'):
                    st.markdown(f"**Assigned to:** {alert['assigned_to']}")

            with col3:
                if st.button("✅ Acknowledge", key=f"ack_{alert['alert_id']}"):
                    response = requests.post(
                        f"{API_URL}/api/alerts/{alert['alert_id']}/acknowledge",
                        json={"acknowledged_by": "operator1"}
                    )
                    if response.status_code == 200:
                        st.success("Acknowledged!")
                        st.rerun()

                if st.button("✔️ Resolve", key=f"resolve_{alert['alert_id']}"):
                    response = requests.post(
                        f"{API_URL}/api/alerts/{alert['alert_id']}/resolve",
                        json={"resolved_by": "operator1", "notes": "Fixed"}
                    )
                    if response.status_code == 200:
                        st.success("Resolved!")
                        st.rerun()
else:
    st.success("✅ No active alerts")

st.markdown("---")

# Line metrics
st.subheader("📈 Production Line Metrics")

metrics_summary = fetch_metrics_summary()

if metrics_summary:
    cols = st.columns(4)

    for idx, (line_id, metrics) in enumerate(metrics_summary.items()):
        with cols[idx % 4]:
            status_icon = "🟢" if metrics["status"] == "online" else "⚪"
            defect_rate = metrics["defect_rate"] * 100

            # Color based on defect rate
            if defect_rate > 10:
                color = "🔴"
            elif defect_rate > 5:
                color = "🟡"
            else:
                color = "🟢"

            st.metric(
                label=f"{status_icon} {line_id}",
                value=f"{defect_rate:.1f}%",
                delta=f"{metrics['total_inspected']} inspected"
            )

            st.caption(f"Status: {metrics['status']}")
else:
    st.info("No metrics data available yet")

st.markdown("---")

# Recent alerts history
st.subheader("📋 Alert History")

all_alerts = fetch_alerts()

if all_alerts:
    df = pd.DataFrame([
        {
            "Time": alert["created_at"][:19],
            "Line": alert["line_id"],
            "Severity": alert["severity"],
            "Defect Rate": f"{alert['value']*100:.1f}%",
            "Status": alert["status"]
        }
        for alert in all_alerts[:20]
    ])

    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No alerts in history")

# Sidebar
with st.sidebar:
    st.header("⚙️ Dashboard Controls")

    st.metric("Total Active Alerts", len(alerts))

    # Filter options
    st.markdown("---")
    st.subheader("🔍 Filters")

    severity_filter = st.multiselect(
        "Severity",
        options=["info", "warning", "critical"],
        default=[]
    )

    line_filter = st.multiselect(
        "Lines",
        options=["line-1", "line-2", "line-3", "line-4"],
        default=[]
    )

    st.markdown("---")
    st.markdown(f"**Last Updated:** {datetime.now().strftime('%H:%M:%S')}")

    if st.button("🔄 Refresh Now"):
        st.cache_data.clear()
        st.rerun()

# Auto-refresh
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
