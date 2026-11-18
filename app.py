import streamlit as st
from pathlib import Path
import json

# Universal secret loader (Works locally & on Streamlit Cloud)
try:
    import streamlit as st
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    model = st.secrets.get("GEMINI_MODEL", "gemini-flash-latest")
except ImportError:
    from dotenv import load_dotenv
    import os
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "")
    model = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

if not api_key:
    st.error("GEMINI_API_KEY missing. Add it to .env or Streamlit Secrets.")
    st.stop()

# Inject env vars so services can use them
import os
os.environ["GEMINI_API_KEY"] = api_key
os.environ["GEMINI_MODEL"] = model

from services.pyq_service import PYQService
from services.planner_service import PlannerService
from pathlib import Path

st.set_page_config(page_title="StudyFlow AI", page_icon="🎓", layout="wide")

@st.cache_resource
def load_services():
    base_dir = Path(__file__).resolve().parent
    pyq = PYQService(base_dir / "syllabus.pdf", base_dir / "pyq.pdf")
    planner = PlannerService(base_dir / "syllabus.pdf", base_dir / "pyq.pdf")
    planner.pyq_service = pyq
    return pyq, planner

pyq_service, planner_service = load_services()

# --- Sidebar Controls ---
with st.sidebar:
    st.header("⚙️ Settings")
    hours = st.slider("Total Study Hours", min_value=1, max_value=500, value=20, step=1)
    
    if st.button("🔄 Refresh Analysis", use_container_width=True):
        pyq_service.invalidate()
        st.cache_resource.clear()
        st.rerun()

# --- Fetch Live Data ---
weightages = pyq_service.get_unit_weightage()
frequencies = pyq_service.get_topic_frequencies()
plan = planner_service.generate_study_plan(total_study_hours=hours)

# --- Read Original Dashboard HTML ---
base_dir = Path(__file__).resolve().parent
html_path = base_dir / "templates" / "dashboard.html"
if html_path.exists():
    with open(html_path, "r", encoding="utf-8") as f:
        dashboard_html = f.read()
else:
    dashboard_html = "<h1>Dashboard template not found</h1>"

# --- Inject Live Data into HTML & Render ---
# We replace placeholder comments in your HTML with actual JSON data
data_script = f"""
<script>
window.STUDYFLOW_DATA = {{
    weightages: {json.dumps(weightages)},
    frequencies: {json.dumps(frequencies)},
    plan: {json.dumps(plan)},
    hours: {hours}
}};
</script>
"""

final_html = dashboard_html.replace("</head>", f"{data_script}</head>")

st.components.v1.html(final_html, height=1200, scrolling=True)

st.caption("Built with Streamlit • Gemini AI • pypdf")