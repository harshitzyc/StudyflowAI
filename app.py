import streamlit as st
from services.pyq_service import PYQService
from services.planner_service import PlannerService
from pathlib import Path

# --- Page Config ---
st.set_page_config(page_title="StudyFlow AI", page_icon="🎓", layout="wide")

# --- Initialize Services (Cached so it only runs once) ---
@st.cache_resource
def load_services():
    base_dir = Path(__file__).resolve().parent
    pyq = PYQService(base_dir / "syllabus.pdf", base_dir / "pyq.pdf")
    planner = PlannerService(base_dir / "syllabus.pdf", base_dir / "pyq.pdf")
    planner.pyq_service = pyq  # Share the cache
    return pyq, planner

pyq_service, planner_service = load_services()

# --- Header ---
st.title("🎓 Study what the exam actually asks.")
st.markdown("""
StudyFlow reads your syllabus and previous-year papers, maps every question to its topic, 
and splits your study hours by real exam weightage — not by guesswork.
""")

# --- Sidebar Controls ---
with st.sidebar:
    st.header("⚙️ Settings")
    hours = st.slider("Total Study Hours", min_value=1, max_value=500, value=20, step=1)
    
    if st.button("🔄 Refresh Analysis", use_container_width=True):
        pyq_service.invalidate()
        st.cache_resource.clear()
        st.rerun()

# --- Main Dashboard Columns ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Unit Weightage Analysis")
    try:
        weightages = pyq_service.get_unit_weightage()
        if weightages:
            st.bar_chart(weightages, y_label="Question Count")
        else:
            st.info("No weightage data available yet.")
    except Exception as e:
        st.error(f"Failed to load weightages: {e}")

with col2:
    st.subheader("🎯 PYQ Topic Frequencies")
    try:
        frequencies = pyq_service.get_topic_frequencies()
        if frequencies:
            sorted_freq = dict(sorted(frequencies.items(), key=lambda x: x[1], reverse=True)[:10])
            st.bar_chart(sorted_freq, y_label="Frequency")
        else:
            st.info("No frequency data available yet.")
    except Exception as e:
        st.error(f"Failed to load frequencies: {e}")

# --- Study Plan Section ---
st.divider()
st.subheader(f"📅 Recommended Study Plan ({hours} Hours)")

try:
    plan = planner_service.generate_study_plan(total_study_hours=hours)
    if isinstance(plan, dict) and "message" not in plan:
        st.dataframe(
            plan, 
            column_config={
                "questions_appeared": st.column_config.NumberColumn("PYQs"),
                "weightage_percentage": st.column_config.NumberColumn("Weightage (%)", format="%.1f%%"),
                "recommended_hours": st.column_config.NumberColumn("Recommended Hours", format="%.1f h")
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.warning(plan.get("message", "Could not generate plan."))
except Exception as e:
    st.error(f"Failed to build plan: {e}")

# --- Footer ---
st.divider()
st.caption("Built with Streamlit • Gemini AI • pypdf • ReportLab")