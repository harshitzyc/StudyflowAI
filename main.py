from pathlib import Path
from datetime import date
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from services.pyq_service import PYQService
from services.planner_service import PlannerService
from services.report_service import ReportService

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Study Flow API", version="1.0")

# ── Frontend wiring (Member 2) ──────────────────────────────────────
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Absolute paths: the app works no matter which folder uvicorn is launched from.
pyq_service = PYQService(BASE_DIR / "syllabus.pdf", BASE_DIR / "pyq.pdf")
planner_service = PlannerService(BASE_DIR / "syllabus.pdf", BASE_DIR / "pyq.pdf")
report_service = ReportService(BASE_DIR / "syllabus.pdf", BASE_DIR / "pyq.pdf")

# Share ONE analysis cache across all services: 9 Gemini calls -> 3 on first load.
planner_service.pyq_service = pyq_service
report_service.planner = planner_service

def _guard(fn, *args, **kwargs):
    """Surface the real failure reason to the UI instead of a blank 500."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        import traceback
        print("\n" + "!"*60)
        print(f"!!! BACKEND ERROR: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        print("!"*60 + "\n")
        raise HTTPException(status_code=503, detail=f"{type(exc).__name__}: {exc}")


def _check_hours(hours: int) -> int:
    if not 1 <= hours <= 500:
        raise HTTPException(status_code=422, detail="hours must be between 1 and 500")
    return hours


# ── HTML pages (Member 2) ───────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"current_year": date.today().year})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {"current_year": date.today().year})


# ── JSON API ────────────────────────────────────────────────────────
@app.get("/api")
def read_root():
    return {
        "project": "Study Flow API",
        "status": "Active",
        "endpoints": ["/plan", "/weightages", "/frequencies", "/export-pdf", "/refresh"],
    }


@app.get("/frequencies")
def get_frequencies():
    return _guard(pyq_service.get_topic_frequencies)


@app.get("/weightages")
def get_weightages():
    return _guard(pyq_service.get_unit_weightage)


@app.get("/plan")
def get_study_plan(hours: int = 20):
    return _guard(planner_service.generate_study_plan, total_study_hours=_check_hours(hours))


@app.get("/export-pdf")
def export_pdf(hours: int = 25):
    _check_hours(hours)
    target = UPLOADS_DIR / f"study_plan_{hours}h.pdf"
    filename = _guard(report_service.generate_pdf_report, filename=str(target), total_hours=hours)
    if not os.path.exists(filename):
        raise HTTPException(status_code=500, detail="PDF generation failed.")
    return FileResponse(filename, media_type="application/pdf", filename=f"studyflow-plan-{hours}h.pdf")


@app.get("/refresh")
def refresh():
    """Clear the cached analysis after swapping the source PDFs."""
    if hasattr(pyq_service, "invalidate"):
        pyq_service.invalidate()
    else:
        pyq_service._cache = None
    return {"status": "cache cleared"}