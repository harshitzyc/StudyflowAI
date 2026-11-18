import streamlit as st
from pathlib import Path
import pandas as pd
import json

# --- Universal Secret Loader ---
try:
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    model = st.secrets.get("GEMINI_MODEL", "gemini-flash-latest")
except Exception:
    from dotenv import load_dotenv
    import os
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "")
    model = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

if not api_key:
    st.error("🔑 GEMINI_API_KEY missing. Add it to .env or Streamlit Secrets.")
    st.stop()

os.environ["GEMINI_API_KEY"] = api_key
os.environ["GEMINI_MODEL"] = model

from services.pyq_service import PYQService
from services.planner_service import PlannerService

st.set_page_config(page_title="StudyFlow AI", page_icon="🎓", layout="wide")

# Inject Custom CSS to match your original branding
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    h1, h2, h3 { font-family: 'Fraunces', serif !important; color: #14213D !important; }
    .stMetric { background-color: white; border-radius: 10px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    div[data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e9ecef; }
    .stButton>button { background-color: #FFB703 !important; color: #14213D !important; font-weight: bold; border: none !important; }
    .stButton>button:hover { background-color: #e5a502 !important; }
</style>
""", unsafe_allow_html=True)

# --- Initialize Services ---
@st.cache_resource
def load_services():
    base_dir = Path(__file__).resolve().parent
    pyq = PYQService(base_dir / "syllabus.pdf", base_dir / "pyq.pdf")
    planner = PlannerService(base_dir / "syllabus.pdf", base_dir / "pyq.pdf")
    planner.pyq_service = pyq
    return pyq, planner

pyq_service, planner_service = load_services()

# --- Header ---
st.title("🎓 Study what the exam actually asks.")
st.caption("Maps previous-year questions to your syllabus and splits study hours by real weightage.")

# --- Sidebar Controls ---
with st.sidebar:
    st.header("⚙️ Settings")
    hours = st.slider("Total Study Hours", min_value=1, max_value=500, value=20, step=1)
    
    if st.button("🔄 Refresh Analysis", use_container_width=True):
        pyq_service.invalidate()
        st.cache_resource.clear()
        st.rerun()

# --- Fetch Live Data ---
try:
    weightages = pyq_service.get_unit_weightage()
    frequencies = pyq_service.get_topic_frequencies()
    plan = planner_service.generate_study_plan(total_study_hours=hours)
except Exception as e:
    st.error(f"❌ Failed to fetch data: {e}")
    st.stop()

# --- Dashboard Layout ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Unit Weightage Analysis")
    if weightages:
        df_w = pd.DataFrame(list(weightages.items()), columns=["Unit", "Question Count"])
        st.bar_chart(df_w.set_index("Unit"), height=300, color="#4A90E2")
    else:
        st.info("No weightage data available.")

with col2:
    st.subheader("🎯 PYQ Topic Frequencies")
    if frequencies:
        sorted_freq = dict(sorted(frequencies.items(), key=lambda x: x[1], reverse=True)[:8])
        df_f = pd.DataFrame(list(sorted_freq.items()), columns=["Topic", "Frequency"])
        st.bar_chart(df_f.set_index("Topic"), height=300, color="#FFB703")
    else:
        st.info("No frequency data available.")

st.divider()
st.subheader(f"📅 Recommended Study Plan ({hours} Hours)")

if isinstance(plan, dict) and "message" not in plan:
    df_plan = pd.DataFrame.from_dict(plan, orient='index').reset_index()
    df_plan.columns = ['Unit', 'PYQs', 'Weightage (%)', 'Recommended Hours']
    
    st.dataframe(
        df_plan, 
        column_config={
            "Unit": st.column_config.TextColumn("Unit", width="medium"),
            "PYQs": st.column_config.NumberColumn("PYQs", format="%d"),
            "Weightage (%)": st.column_config.NumberColumn("Weightage", format="%.1f%%"),
            "Recommended Hours": st.column_config.NumberColumn("Hours", format="%.1f h")
        },
        hide_index=True,
        use_container_width=True,
        height=400
    )
else:
    st.warning(plan.get("message", "Could not generate plan."))

st.caption("Built with Streamlit • Gemini AI • pypdf")