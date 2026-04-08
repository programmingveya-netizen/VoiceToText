"""
Voice To Text - Hlavní aplikace
Routing a spuštění serveru. Logika je v samostatných modulech.
"""

import os
import io
import zipfile
import json
import time
import uuid
import threading
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask

import uvicorn

from translator import translate_segments, LANGUAGE_NAMES
from exporter import export_txt, export_pdf, export_srt
from dictionary_utils import load_dictionary
from jobs import jobs, process_file
from transcription import transcribe_file

# ── Konfigurace ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
PROJECTS_DIR = BASE_DIR / "projects"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
PROJECTS_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mkv", ".avi", ".mov"}

app = FastAPI(title="Voice To Text")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ── API Endpointy ────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/delete/{job_id}")
async def delete_job(job_id: str):
    if job_id in jobs:
        del jobs[job_id]
    for f in UPLOAD_DIR.glob(f"{job_id}.*"):
        f.unlink(missing_ok=True)
    return JSONResponse({"ok": True})


@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...), model: str = Form("small")):
    created_jobs = []

    for file in files:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue

        job_id = str(uuid.uuid4())[:8]
        file_path = UPLOAD_DIR / f"{job_id}{ext}"

        # Chunked upload - nečte celý soubor do RAM
        with open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)

        jobs[job_id] = {
            "id": job_id,
            "filename": file.filename,
            "status": "queued",
            "progress": 0,
            "segments": [],
            "health_claims": [],
            "error": None,
            "model": model,
        }

        t = threading.Thread(
            target=process_file,
            args=(str(file_path), file.filename, job_id, BASE_DIR),
            daemon=True,
        )
        t.start()
        created_jobs.append({"id": job_id, "filename": file.filename})

    return JSONResponse({"jobs": created_jobs})


@app.get("/status/{job_id}")
async def job_status(job_id: str):
    if job_id not in jobs:
        return JSONResponse({"error": "Úloha nenalezena"}, status_code=404)
    job = jobs[job_id]
    return JSONResponse({
        "id": job["id"],
        "filename": job["filename"],
        "status": job["status"],
        "progress": job["progress"],
        "error": job["error"],
        "segment_count": len(job["segments"]),
        "claim_count": len(job["health_claims"]),
    })


@app.get("/result/{job_id}")
async def job_result(job_id: str):
    if job_id not in jobs:
        return JSONResponse({"error": "Úloha nenalezena"}, status_code=404)
    job = jobs[job_id]
    if job["status"] != "done":
        return JSONResponse({"error": "Přepis ještě není dokončen"}, status_code=400)
    return JSONResponse({
        "segments": job["segments"],
        "health_claims": job["health_claims"],
    })


@app.post("/save/{job_id}")
async def save_segments(job_id: str, request: Request):
    if job_id not in jobs or jobs[job_id]["status"] != "done":
        return JSONResponse({"error": "Přepis není k dispozici"}, status_code=400)

    data = await request.json()
    segments = data.get("segments", [])
    jobs[job_id]["segments"] = segments

    # Zachovat ručně přidané claims
    custom_claims = jobs[job_id].get("custom_claims", [])
    jobs[job_id]["health_claims"] = custom_claims

    return JSONResponse({
        "ok": True,
        "claim_count": len(jobs[job_id]["health_claims"]),
        "health_claims": jobs[job_id]["health_claims"],
    })


@app.get("/dictionary")
async def get_dictionary():
    dict_path = BASE_DIR / "dictionary.txt"
    content = dict_path.read_text(encoding="utf-8") if dict_path.exists() else ""
    return JSONResponse({"content": content})


@app.post("/dictionary")
async def save_dictionary(request: Request):
    data = await request.json()
    (BASE_DIR / "dictionary.txt").write_text(data.get("content", ""), encoding="utf-8")
    return JSONResponse({"ok": True})


@app.get("/names")
async def get_names():
    names_path = BASE_DIR / "names.txt"
    content = names_path.read_text(encoding="utf-8") if names_path.exists() else ""
    return JSONResponse({"content": content})


@app.post("/names")
async def save_names(request: Request):
    data = await request.json()
    (BASE_DIR / "names.txt").write_text(data.get("content", ""), encoding="utf-8")
    return JSONResponse({"ok": True})


@app.post("/translate/{job_id}")
async def translate_job(job_id: str, target_lang: str = Form(...)):
    if job_id not in jobs or jobs[job_id]["status"] != "done":
        return JSONResponse({"error": "Přepis není k dispozici"}, status_code=400)
    segments = jobs[job_id]["segments"]
    translated = translate_segments(segments, target_lang, "cs")
    return JSONResponse({"segments": translated, "language": target_lang})


@app.get("/export/{job_id}")
async def export_job(job_id: str, format: str = "txt", lang: str = "original"):
    if job_id not in jobs or jobs[job_id]["status"] != "done":
        return JSONResponse({"error": "Přepis není k dispozici"}, status_code=400)

    job = jobs[job_id]
    segments = job["segments"]
    filename_base = Path(job["filename"]).stem

    if lang != "original" and lang != "cs":
        segments = translate_segments(segments, lang, "cs")
        filename_base += f"_{lang}"

    uid = str(uuid.uuid4())[:6]
    out_path = str(OUTPUT_DIR / f"{filename_base}_{uid}.{format}")

    if format == "txt":
        export_txt(segments, out_path)
        return FileResponse(out_path, filename=f"{filename_base}.txt",
                          media_type="text/plain; charset=utf-8",
                          background=BackgroundTask(os.unlink, out_path))

    elif format == "pdf":
        export_pdf(segments, out_path,
                  health_claims=job["health_claims"],
                  title=f"Přepis: {job['filename']}")
        return FileResponse(out_path, filename=f"{filename_base}.pdf",
                          media_type="application/pdf",
                          background=BackgroundTask(os.unlink, out_path))

    elif format == "srt":
        export_srt(segments, out_path)
        return FileResponse(out_path, filename=f"{filename_base}.srt",
                          media_type="text/srt; charset=utf-8",
                          background=BackgroundTask(os.unlink, out_path))

    return JSONResponse({"error": "Neznámý formát"}, status_code=400)


@app.get("/languages")
async def get_languages():
    return JSONResponse(LANGUAGE_NAMES)


@app.get("/export-zip/{job_id}")
async def export_zip(job_id: str, langs: str = ""):
    if job_id not in jobs or jobs[job_id]["status"] != "done":
        return JSONResponse({"error": "Přepis není k dispozici"}, status_code=400)

    job = jobs[job_id]
    segments = job["segments"]
    filename_base = Path(job["filename"]).stem
    lang_codes = [l.strip() for l in langs.split(",") if l.strip()] if langs else []
    temp_files = []

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for suffix, fn, args in [
            ("txt", export_txt, (segments,)),
            ("pdf", export_pdf, (segments,)),
            ("srt", export_srt, (segments,)),
        ]:
            p = str(OUTPUT_DIR / f"{filename_base}_zip.{suffix}")
            temp_files.append(p)
            if suffix == "pdf":
                export_pdf(segments, p, health_claims=job["health_claims"],
                          title=f"Přepis: {job['filename']}")
            else:
                fn(segments, p)
            zf.write(p, f"{filename_base}.{suffix}")

        for lang in lang_codes:
            translated = translate_segments(segments, lang, "cs")
            lang_base = f"{filename_base}_{lang}"
            for suffix, fn in [("txt", export_txt), ("pdf", export_pdf), ("srt", export_srt)]:
                p = str(OUTPUT_DIR / f"{lang_base}_zip.{suffix}")
                temp_files.append(p)
                if suffix == "pdf":
                    export_pdf(translated, p, health_claims=job["health_claims"],
                              title=f"Přepis: {job['filename']} ({lang})")
                else:
                    fn(translated, p)
                zf.write(p, f"{lang_base}.{suffix}")

    # Cleanup temp files
    for p in temp_files:
        try:
            os.unlink(p)
        except OSError:
            pass

    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename_base}_export.zip"'},
    )


@app.post("/project/save/{job_id}")
async def save_project(job_id: str):
    if job_id not in jobs:
        return JSONResponse({"error": "Úloha nenalezena"}, status_code=404)

    job = jobs[job_id]
    safe_name = Path(job["filename"]).stem
    project_path = PROJECTS_DIR / f"{safe_name}.json"

    project_data = {
        "filename": job["filename"],
        "segments": job["segments"],
        "health_claims": job["health_claims"],
        "custom_claims": job.get("custom_claims", []),
        "saved_date": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    project_path.write_text(json.dumps(project_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return JSONResponse({"ok": True, "path": str(project_path)})


@app.get("/projects")
async def list_projects():
    projects = []
    for p in sorted(PROJECTS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            projects.append({
                "filename": data.get("filename", p.stem),
                "saved_date": data.get("saved_date", ""),
                "path": str(p),
            })
        except Exception:
            continue
    return JSONResponse({"projects": projects})


@app.post("/project/load")
async def load_project(request: Request):
    data = await request.json()
    path = data.get("path")
    if not path:
        return JSONResponse({"error": "Soubor nenalezen"}, status_code=404)

    # Path traversal fix - ověřit že cesta je uvnitř PROJECTS_DIR
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(PROJECTS_DIR.resolve()):
        return JSONResponse({"error": "Neplatná cesta"}, status_code=403)

    if not resolved.exists():
        return JSONResponse({"error": "Soubor nenalezen"}, status_code=404)

    project_data = json.loads(resolved.read_text(encoding="utf-8"))
    job_id = str(uuid.uuid4())[:8]

    jobs[job_id] = {
        "id": job_id,
        "filename": project_data.get("filename", "unknown"),
        "status": "done",
        "progress": 100,
        "segments": project_data.get("segments", []),
        "health_claims": project_data.get("health_claims", []),
        "custom_claims": project_data.get("custom_claims", []),
        "error": None,
        "model": "unknown",
    }

    return JSONResponse({"ok": True, "job_id": job_id, "filename": jobs[job_id]["filename"]})


@app.post("/mark-claim/{job_id}")
async def mark_claim(job_id: str, request: Request):
    if job_id not in jobs:
        return JSONResponse({"error": "Úloha nenalezena"}, status_code=404)

    data = await request.json()
    text = data.get("text", "").strip()
    reason = data.get("reason", "").strip()

    if not text:
        return JSONResponse({"error": "Text tvrzení je povinný"}, status_code=400)

    claim = {"text": text, "start": 0, "end": len(text), "reason": reason or "rucne oznaceno"}

    existing_texts = [c["text"].lower() for c in jobs[job_id]["health_claims"]]
    if text.lower() not in existing_texts:
        jobs[job_id]["health_claims"].append(claim)

    if "custom_claims" not in jobs[job_id]:
        jobs[job_id]["custom_claims"] = []
    jobs[job_id]["custom_claims"].append(claim)

    return JSONResponse({
        "ok": True,
        "claim_count": len(jobs[job_id]["health_claims"]),
        "health_claims": jobs[job_id]["health_claims"],
    })


@app.post("/unmark-claim/{job_id}")
async def unmark_claim(job_id: str, request: Request):
    if job_id not in jobs:
        return JSONResponse({"error": "Úloha nenalezena"}, status_code=404)

    data = await request.json()
    text = data.get("text", "").strip()

    if not text:
        return JSONResponse({"error": "Text tvrzení je povinný"}, status_code=400)

    jobs[job_id]["health_claims"] = [
        c for c in jobs[job_id]["health_claims"] if c["text"].strip() != text
    ]
    if "custom_claims" in jobs[job_id]:
        jobs[job_id]["custom_claims"] = [
            c for c in jobs[job_id]["custom_claims"] if c["text"].strip() != text
        ]

    return JSONResponse({
        "ok": True,
        "claim_count": len(jobs[job_id]["health_claims"]),
        "health_claims": jobs[job_id]["health_claims"],
    })


# ── Spuštění ─────────────────────────────────────────────────

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    import subprocess
    import webbrowser

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1.5)

    url = "http://127.0.0.1:8000"
    opened = False

    for browser_path in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]:
        if os.path.exists(browser_path):
            subprocess.Popen([browser_path, f"--app={url}", "--new-window"])
            opened = True
            break

    if not opened:
        webbrowser.open(url)

    print()
    print("  Voice To Text - aplikace bezi")
    print(f"  {url}")
    print("  Pro ukonceni zavrete toto okno.")
    print()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
