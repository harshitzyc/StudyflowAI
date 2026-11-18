import streamlit as st
from pathlib import Path
import json
import os

# --- Universal Secret Loader (Works locally & on Streamlit Cloud) ---
try:
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    model = st.secrets.get("GEMINI_MODEL", "gemini-flash-latest")
except Exception:
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "")
    model = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

if not api_key:
    st.error("🔑 GEMINI_API_KEY missing. Add it to .env or Streamlit Secrets.")
    st.stop()

# Inject env vars so backend services work identically in both environments
os.environ["GEMINI_API_KEY"] = api_key
os.environ["GEMINI_MODEL"] = model

from services.pyq_service import PYQService
from services.planner_service import PlannerService

st.set_page_config(page_title="StudyFlow AI", page_icon="🎓", layout="wide")

# --- Initialize Services (Cached per session) ---
@st.cache_resource
def load_services():
    base_dir = Path(__file__).resolve().parent
    pyq = PYQService(base_dir / "syllabus.pdf", base_dir / "pyq.pdf")
    planner = PlannerService(base_dir / "syllabus.pdf", base_dir / "pyq.pdf")
    planner.pyq_service = pyq  # Share cache across services
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

# --- Fetch Live Data from Your Existing Backend Logic ---
weightages = pyq_service.get_unit_weightage()
frequencies = pyq_service.get_topic_frequencies()
plan = planner_service.generate_study_plan(total_study_hours=hours)

# --- Read Your Original Dashboard HTML ---
base_dir = Path(__file__).resolve().parent
dashboard_path = base_dir / "templates" / "dashboard.html"

if not dashboard_path.exists():
    st.error("❌ dashboard.html not found. Ensure templates/dashboard.html exists in repo.")
    st.stop()

with open(dashboard_path, "r", encoding="utf-8") as f:
    dashboard_html = f.read()

# --- Inject Live Data Directly Into Your Existing Frontend ---
data_script = f"""
<script>
// Override fetch ONLY for your API endpoints to serve live Python data
const LIVE_DATA = {{
    weightages: {json.dumps(weightages)},
    frequencies: {json.dumps(frequencies)},
    plan: {json.dumps(plan)},
    hours: {hours}
}};

const originalFetch = window.fetch;
window.fetch = async (url, opts) => {{
    const urlStr = typeof url === 'string' ? url : url.url;
    if (urlStr.includes('/weightages')) 
        return {{ ok: true, json: () => Promise.resolve(LIVE_DATA.weightages) }};
    if (urlStr.includes('/frequencies')) 
        return {{ ok: true, json: () => Promise.resolve(LIVE_DATA.frequencies) }};
    if (urlStr.includes('/plan')) 
        return {{ ok: true, json: () => Promise.resolve(LIVE_DATA.plan) }};
    return originalFetch(url, opts); // Let all other requests (CSS/JS/images) pass through normally
}};
</script>
"""

# Inject script BEFORE </head> so it loads before dashboard.js executes
final_html = dashboard_html.replace("</head>", f"{data_script}</head>")

# Render your EXACT frontend inside Streamlit
st.components.v1.html(final_html, height=1400, scrolling=True)

st.caption("Built with Streamlit • Gemini AI • pypdf")