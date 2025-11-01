"""Streamlit Mock Producer UI."""
import streamlit as st
import requests
import json
import os

# Configuration
API_URL = os.getenv('API_URL', 'http://localhost:8000')

st.set_page_config(
    page_title="SwitchOn Mock Producer",
    page_icon="🏭",
    layout="wide"
)

st.title("🏭 SwitchOn - Kafka Payload Mock Panel")
st.markdown("---")

# Metadata
try:
    meta_response = requests.get(f"{API_URL}/api/meta")
    if meta_response.status_code == 200:
        meta = meta_response.json()
        lines = meta["lines"]
        defect_types = meta["defect_types"]
        results = meta["results"]
        severities = meta["severities"]
    else:
        st.error("Failed to load metadata from API")
        st.stop()
except Exception as e:
    st.error(f"Cannot connect to API at {API_URL}: {e}")
    st.info("Make sure the FastAPI backend is running on port 8000")
    st.stop()

# Layout
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📋 Event Configuration")

    # Line selection
    line_id = st.selectbox(
        "Production Line",
        options=lines,
        help="Select which production line to simulate"
    )

    # Result
    result = st.selectbox(
        "Inspection Result",
        options=results,
        help="Pass or Fail"
    )

    # Confidence
    confidence = st.slider(
        "Confidence Score",
        min_value=0.0,
        max_value=1.0,
        value=0.90,
        step=0.01,
        help="AI model confidence (0.0 - 1.0)"
    )

    # Defect type (only if fail)
    defect_type = None
    severity = None
    if result == "fail":
        defect_type = st.selectbox(
            "Defect Type",
            options=[None] + defect_types,
            help="Type of defect detected"
        )
        severity = st.selectbox(
            "Severity Hint",
            options=[None] + severities,
            help="Optional severity hint"
        )

    # SKU (optional)
    sku = st.text_input(
        "SKU (Optional)",
        value="SKU-12345",
        help="Stock Keeping Unit"
    )

    st.markdown("---")

    # Burst mode
    st.subheader("🔥 Burst Mode")
    burst_count = st.number_input(
        "Number of Events to Send",
        min_value=1,
        max_value=1000,
        value=10,
        step=10,
        help="Send multiple events at once"
    )

with col2:
    st.subheader("🎯 Actions")

    # Send single
    if st.button("📤 Send Single Event", use_container_width=True, type="primary"):
        try:
            payload = {
                "line_id": line_id,
                "result": result,
                "confidence": confidence,
                "sku": sku if sku else None,
                "defect_type": defect_type,
                "severity": severity
            }

            response = requests.post(f"{API_URL}/api/produce", json=payload)

            if response.status_code == 200:
                data = response.json()
                st.success(f"✅ Event sent successfully!")
                with st.expander("View Response"):
                    st.json(data)
            else:
                st.error(f"❌ Failed: {response.status_code}")
                st.code(response.text)

        except Exception as e:
            st.error(f"❌ Error: {e}")

    # Send burst
    if st.button(f"💥 Send Burst ({burst_count} events)", use_container_width=True):
        try:
            payload = {
                "line_id": line_id,
                "result": result,
                "count": burst_count,
                "confidence": confidence,
                "defect_type": defect_type,
                "severity": severity
            }

            with st.spinner(f"Sending {burst_count} events..."):
                response = requests.post(f"{API_URL}/api/produce/batch", json=payload)

            if response.status_code == 200:
                data = response.json()
                st.success(f"✅ Burst sent: {data['sent']} events to {data['line_id']}")
            else:
                st.error(f"❌ Failed: {response.status_code}")
                st.code(response.text)

        except Exception as e:
            st.error(f"❌ Error: {e}")

    st.markdown("---")

    # Quick scenarios
    st.subheader("⚡ Quick Scenarios")

    if st.button("🟢 Normal Operation", use_container_width=True):
        try:
            payload = {
                "line_id": line_id,
                "result": "pass",
                "count": 50,
                "confidence": 0.95
            }
            response = requests.post(f"{API_URL}/api/produce/batch", json=payload)
            if response.status_code == 200:
                st.success("✅ Sent 50 PASS events")
        except Exception as e:
            st.error(f"❌ Error: {e}")

    if st.button("🟡 Minor Issues", use_container_width=True):
        try:
            # Send mostly pass with few fails
            requests.post(f"{API_URL}/api/produce/batch", json={
                "line_id": line_id,
                "result": "pass",
                "count": 45
            })
            requests.post(f"{API_URL}/api/produce/batch", json={
                "line_id": line_id,
                "result": "fail",
                "count": 5,
                "defect_type": "scratch"
            })
            st.success("✅ Sent 45 PASS + 5 FAIL events")
        except Exception as e:
            st.error(f"❌ Error: {e}")

    if st.button("🔴 Critical Spike", use_container_width=True):
        try:
            payload = {
                "line_id": line_id,
                "result": "fail",
                "count": 50,
                "confidence": 0.85,
                "defect_type": "scratch",
                "severity": "critical"
            }
            response = requests.post(f"{API_URL}/api/produce/batch", json=payload)
            if response.status_code == 200:
                st.success("✅ Sent 50 FAIL events (should trigger alert!)")
        except Exception as e:
            st.error(f"❌ Error: {e}")

# Footer
st.markdown("---")
st.markdown("""
### 💡 Tips
- **Normal Operation**: Sends mostly PASS events
- **Minor Issues**: Simulates occasional defects (5-10%)
- **Critical Spike**: Sends burst of failures to trigger alerts
- Use **Burst Mode** to quickly generate load for testing thresholds
""")

# Connection status
with st.sidebar:
    st.header("🔌 Connection Status")
    if st.button("🔄 Test API Connection"):
        try:
            response = requests.get(f"{API_URL}/health")
            if response.status_code == 200:
                st.success("✅ API Connected")
            else:
                st.error("❌ API Error")
        except:
            st.error("❌ Cannot connect to API")

    st.markdown("---")
    st.markdown(f"**API URL:** `{API_URL}`")
    st.markdown("**Selected Line:** `{}`".format(line_id))
