"""StudyFlow — FastAPI entrypoint with upload support."""
import io
import json
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services.pyq_service import PYQService

BASE = Path(__file__).resolve().parent

app = FastAPI(title="StudyFlow", description="Weightage-driven exam preparation from your syllabus and PYQs.")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

# Single shared analysis service
pyq_service = PYQService(BASE / "syllabus.pdf", BASE / "pyq.pdf")

# Import and mount the intake router AFTER pyq_service exists
from intake_routes import router as intake_router
app.include_router(intake_router)


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"{type(exc).__name__}: {exc}")


def _auto_analyse():
    if pyq_service.source == "sample":
        try:
            pyq_service.analyse_live()
        except Exception as e:
            print("background analysis failed:", e)


@app.on_event("startup")
def _start_background():
    threading.Thread(target=_auto_analyse, daemon=True).start()


def _ctx():
    return {"current_year": datetime.now().year}


# ---------------- pages ----------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context=_ctx())


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html", context=_ctx())


@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request):
    return templates.TemplateResponse(request=request, name="sources.html", context=_ctx())


# ---------------- analysis API ----------------
@app.get("/weightages")
def weightages():
    return _guard(pyq_service.get_unit_weightage)


@app.get("/frequencies")
def frequencies():
    return _guard(pyq_service.get_topic_frequencies)


@app.get("/status")
def status():
    return {"ready": pyq_service.source != "sample", "source": pyq_service.source}


@app.get("/refresh")
def refresh():
    pyq_service.invalidate()
    threading.Thread(target=pyq_service.analyse_live, daemon=True).start()
    return {"status": "re-analysis started in background; reload the dashboard in ~1 minute"}


def _allocate(hours: int):
    weights = pyq_service.get_unit_weightage()
    total = sum(weights.values())
    if not weights or total <= 0:
        return {}
    plan = {}
    for unit, count in weights.items():
        share = count / total
        plan[unit] = {
            "questions_appeared": int(count),
            "weightage_percentage": round(share * 100, 1),
            "recommended_hours": round(hours * share, 1),
        }
    return plan


@app.get("/plan")
def plan(hours: int = Query(20, ge=1, le=500)):
    return _guard(_allocate, hours)


# ---------------- PDF export ----------------
def _build_plan_pdf(hours: int) -> io.BytesIO:
    weights = pyq_service.get_unit_weightage()
    plan = _allocate(hours)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title="StudyFlow study plan", author="StudyFlow",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("SFTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                           fontSize=22, textColor=colors.HexColor("#14213D"), spaceAfter=4)
    sub = ParagraphStyle("SFSub", parent=styles["Normal"], fontSize=10,
                         textColor=colors.HexColor("#5C6478"), spaceAfter=14)
    head = ParagraphStyle("SFHead", parent=styles["Normal"], fontName="Helvetica-Bold",
                          fontSize=12, textColor=colors.HexColor("#14213D"), spaceBefore=10, spaceAfter=6)
    body = ParagraphStyle("SFBody", parent=styles["Normal"], fontSize=9.5,
                          textColor=colors.HexColor("#1D2D50"), leading=13)

    story = [
        Paragraph("StudyFlow — weighted study plan", title),
        Paragraph(f"Total study hours: {hours} · generated {datetime.now():%d %b %Y %H:%M} "
                  f"· source: syllabus.pdf + pyq.pdf", sub),
        Paragraph("Recommended hours per unit", head),
    ]

    rows = [["Unit", "PYQs", "Weightage", "Recommended hours"]]
    tq = tw = th = 0
    for unit, r in plan.items():
        rows.append([unit, str(r["questions_appeared"]), f"{r['weightage_percentage']}%", f"{r['recommended_hours']} h"])
        tq += r["questions_appeared"]
        tw += r["weightage_percentage"]
        th += r["recommended_hours"]
    rows.append(["Total", str(tq), f"{round(tw, 1)}%", f"{round(th, 1)} h"])

    tbl = Table(rows, colWidths=[60 * mm, 25 * mm, 35 * mm, 45 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14213D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#FFF3D6")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FAF7F2")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E7E0D4")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Hours are allocated proportionally to the number of previous-year questions mapped to each unit. "
        "Start with the highest-weightage unit and secure its high-mark questions first.", body))

    if weights:
        story.append(Paragraph("Unit weightage (mapped PYQ count)", head))
        wrows = [["Unit", "Questions"]] + [[u, str(c)] for u, c in weights.items()]
        wt = Table(wrows, colWidths=[100 * mm, 40 * mm], repeatRows=1)
        wt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FFB703")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E7E0D4")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(wt)

    doc.build(story)
    buf.seek(0)
    return buf


@app.get("/export-pdf")
def export_pdf(hours: int = Query(20, ge=1, le=500)):
    buf = _guard(_build_plan_pdf, hours)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="study_plan.pdf"'},
    )


from services import chat_service
from pydantic import BaseModel


class ChatBody(BaseModel):
    messages: list = []


@app.post("/chat/stream")
def chat_stream(body: ChatBody):
    def gen():
        for chunk in chat_service.stream_reply(body.messages):
            yield f"data: {json.dumps({'t': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )