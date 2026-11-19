"""Document intake: upload, preview, select and reset the PDFs the AI reads."""
import json
import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from services.pdf_service import extract_text

BASE = Path(__file__).resolve().parent
UPLOADS = BASE / "uploads"
TRASH = UPLOADS / ".trash"
HISTORY = UPLOADS / "history.json"
CURRENT = UPLOADS / "current.json"
ROOT_DOCS = {"syllabus": BASE / "syllabus.pdf", "pyq": BASE / "pyq.pdf"}
MAX_BYTES = 15 * 1024 * 1024

router = APIRouter(prefix="/sources", tags=["intake"])
_busy = {"flag": False}
_lock = threading.Lock()


def _dirs():
    UPLOADS.mkdir(exist_ok=True)
    TRASH.mkdir(exist_ok=True)


def _read_json(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(p, data):
    _dirs()
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _history():
    return _read_json(HISTORY, [])


def _current():
    cur = _read_json(CURRENT, {})
    return {
        "syllabus": cur.get("syllabus") or str(ROOT_DOCS["syllabus"]),
        "pyq": cur.get("pyq") or str(ROOT_DOCS["pyq"]),
    }


def _allowed(path_str):
    p = Path(path_str).resolve()
    roots = [BASE.resolve(), UPLOADS.resolve(), TRASH.resolve()]
    if not any(str(p).startswith(str(r)) for r in roots):
        raise HTTPException(400, "Path outside allowed document folders.")
    if p.suffix.lower() != ".pdf" or not p.exists():
        raise HTTPException(404, "Document not found.")
    return p


def _stats(p):
    from pypdf import PdfReader
    try:
        pages = len(PdfReader(str(p)).pages)
    except Exception:
        pages = 0
    try:
        text = extract_text(str(p))
    except Exception:
        text = ""
    clean = " ".join(text.split())
    return {
        "name": p.name,
        "path": str(p),
        "size": p.stat().st_size,
        "pages": pages,
        "words": len(clean.split()),
        "chars": len(clean),
        "excerpt": clean[:420],
        "readable": len(clean) > 40,
    }


def _services():
    import main as app_module
    return app_module.pyq_service


def _point_and_analyse():
    cur = _current()
    svc = _services()
    svc.syllabus_pdf_path = cur["syllabus"]
    svc.pyq_pdf_path = cur["pyq"]
    svc.invalidate()
    _start_analysis()


def _start_analysis():
    with _lock:
        if _busy["flag"]:
            return
        _busy["flag"] = True

    def run():
        try:
            _services().analyse_live()
        except Exception as e:
            print("intake analysis failed:", e)
        finally:
            with _lock:
                _busy["flag"] = False

    threading.Thread(target=run, daemon=True).start()


def _meta():
    cur = _current()
    hist = [h for h in _history() if not h.get("trashed")]
    hist.sort(key=lambda h: h.get("ts", 0), reverse=True)
    return {
        "current": {k: _stats(Path(v)) for k, v in cur.items()},
        "history": hist,
        "busy": _busy["flag"],
        "ready": _services().source != "sample",
        "source": _services().source,
    }


@router.get("/meta")
def meta():
    return _meta()


@router.post("/upload")
async def upload(syllabus: UploadFile = File(None), pyq: UploadFile = File(None)):
    _dirs()
    if not syllabus and not pyq:
        raise HTTPException(400, "Attach at least one PDF.")
    cur = _current()
    hist = _history()
    for kind, uf in (("syllabus", syllabus), ("pyq", pyq)):
        if uf is None:
            continue
        raw = await uf.read()
        if not raw.startswith(b"%PDF"):
            raise HTTPException(415, f"{uf.filename}: not a PDF (missing %PDF header).")
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, f"{uf.filename}: larger than 15 MB.")
        dest = UPLOADS / f"{kind}-{int(time.time())}-{uuid.uuid4().hex[:6]}.pdf"
        dest.write_bytes(raw)
        hist.append({
            "id": dest.stem, "name": uf.filename or dest.name, "kind": kind,
            "size": len(raw), "ts": int(time.time() * 1000), "path": str(dest), "trashed": False,
        })
        cur[kind] = str(dest)
    _write_json(HISTORY, hist)
    _write_json(CURRENT, cur)
    _point_and_analyse()
    return _meta()


class SelectBody(BaseModel):
    syllabus: str
    pyq: str


@router.post("/select")
def select(body: SelectBody):
    _allowed(body.syllabus)
    _allowed(body.pyq)
    _write_json(CURRENT, {"syllabus": body.syllabus, "pyq": body.pyq})
    _point_and_analyse()
    return _meta()


class DeleteBody(BaseModel):
    id: str


@router.post("/delete")
def delete(body: DeleteBody):
    hist = _history()
    entry = next((h for h in hist if h["id"] == body.id), None)
    if not entry:
        raise HTTPException(404, "Upload not found.")
    src = Path(entry["path"])
    if src.exists():
        shutil.move(str(src), str(TRASH / src.name))
        entry["path"] = str(TRASH / src.name)
    entry["trashed"] = True
    _write_json(HISTORY, hist)
    cur = _current()
    changed = False
    for kind in ("syllabus", "pyq"):
        if cur[kind] == entry["path"] or Path(cur[kind]).name == src.name:
            cur[kind] = str(ROOT_DOCS[kind])
            changed = True
    if changed:
        _write_json(CURRENT, cur)
        _point_and_analyse()
    return _meta()


@router.post("/restore")
def restore(body: DeleteBody):
    hist = _history()
    entry = next((h for h in hist if h["id"] == body.id), None)
    if not entry:
        raise HTTPException(404, "Upload not found.")
    src = Path(entry["path"])
    if src.exists() and src.parent == TRASH:
        dest = UPLOADS / src.name
        shutil.move(str(src), str(dest))
        entry["path"] = str(dest)
    entry["trashed"] = False
    _write_json(HISTORY, hist)
    return _meta()


@router.post("/reset")
def reset():
    _write_json(CURRENT, {k: str(v) for k, v in ROOT_DOCS.items()})
    _point_and_analyse()
    return _meta()


@router.post("/analyse")
def analyse():
    _start_analysis()
    return {"started": True, "busy": _busy["flag"]}


@router.get("/preview")
def preview(path: str):
    p = _allowed(path)
    text = extract_text(str(p))
    clean = " ".join(text.split())
    return {
        "name": p.name, "text": text, "words": len(clean.split()),
        "chars": len(clean), "pages": _stats(p)["pages"],
    }


@router.get("/download-text")
def download_text(path: str):
    p = _allowed(path)
    return PlainTextResponse(
        extract_text(str(p)),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{p.stem}.txt"'},
    )


# Re-apply a previously chosen pair on boot so uploads survive restarts.
try:
    if CURRENT.exists():
        _cur = _current()
        _svc = _services()
        _svc.syllabus_pdf_path = _cur["syllabus"]
        _svc.pyq_pdf_path = _cur["pyq"]
except Exception:
    pass