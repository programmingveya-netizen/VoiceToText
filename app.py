"""
Voice To Text - Hlavní aplikace
Přepis videa/audia na text s timestamps, překlad, detekce zdravotních tvrzení.
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

import uvicorn

from health_checker import find_health_claims
from translator import translate_segments, LANGUAGE_NAMES
from exporter import export_txt, export_pdf, export_srt

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

# ── Stav úloh ────────────────────────────────────────────────
jobs: dict[str, dict] = {}


def get_whisper_model(model_size: str = "small"):
    """Načte a cachuje Whisper model"""
    if not hasattr(get_whisper_model, "_cache"):
        get_whisper_model._cache = {}
    if model_size not in get_whisper_model._cache:
        import os
        os.environ["CT2_VERBOSE"] = "0"
        from faster_whisper import WhisperModel
        # Auto-detekce GPU: zkusit CUDA, pokud neni tak CPU
        try:
            import ctranslate2
            if "cuda" in ctranslate2.get_supported_compute_types("cuda"):
                model = WhisperModel(model_size, device="cuda", compute_type="float16")
                print(f"  [GPU] Model {model_size} nacten na CUDA (GPU)")
            else:
                raise RuntimeError("no cuda")
        except Exception:
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            print(f"  [CPU] Model {model_size} nacten na CPU")
        get_whisper_model._cache[model_size] = model
    return get_whisper_model._cache[model_size]


def load_dictionary() -> dict[str, str]:
    """Načte slovník oprav z dictionary.txt"""
    dict_path = BASE_DIR / "dictionary.txt"
    replacements = {}
    if dict_path.exists():
        for line in dict_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                wrong, correct = line.split("=", 1)
                replacements[wrong.strip()] = correct.strip()
    return replacements


def apply_dictionary(text: str, dictionary: dict[str, str]) -> str:
    """Aplikuje slovník oprav na text"""
    for wrong, correct in dictionary.items():
        text = text.replace(wrong, correct)
    return text


# Český prompt pro Whisper - zlepšuje kvalitu diakritiky a rozpoznávání
# Delší prompt s různorodou českou slovní zásobou pomáhá modelu lépe rozpoznávat
CZECH_PROMPT = (
    "Dobrý večer, tady Jiří Černota, zdravím všechny příznivce zdravého životního stylu, "
    "esenciálních olejů, super potravin a dalších věcí, které podporují naše těla. "
    "Dnes si povíme o přírodních produktech, doplňcích stravy, vitamínech a minerálech. "
    "Budeme mluvit o zdraví, imunitě, prevenci a o tom, jak se zbavit různých potíží. "
    "Můžete se ptát v komentářích, napište odkud jste. Děkuji za sledování."
)


def transcribe_file(file_path: str, job_id: str) -> list[dict]:
    """Přepíše audio/video soubor pomocí faster-whisper"""
    model_size = jobs[job_id].get("model", "small")
    model = get_whisper_model(model_size)

    # Větší beam = přesnější ale pomalejší
    beam = 5 if model_size in ("medium", "large-v3") else 3

    segments_iter, info = model.transcribe(
        file_path,
        language="cs",
        beam_size=beam,
        best_of=beam,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        initial_prompt=CZECH_PROMPT,
        condition_on_previous_text=True,
        temperature=0,
    )

    dictionary = load_dictionary()

    raw_segments = []
    for segment in segments_iter:
        text = segment.text.strip()
        if dictionary:
            text = apply_dictionary(text, dictionary)
        raw_segments.append({
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": text
        })
        # Aktualizovat progress
        if info.duration and info.duration > 0:
            progress = min(95, int((segment.end / info.duration) * 100))
            jobs[job_id]["progress"] = progress

    # Sloučit do vět
    return merge_into_sentences(raw_segments)


def merge_into_sentences(segments: list[dict]) -> list[dict]:
    """Sloučí krátké segmenty do větších celků (po větách)."""
    if not segments:
        return segments

    merged = []
    current = {
        "start": segments[0]["start"],
        "end": segments[0]["end"],
        "text": segments[0]["text"],
    }

    for seg in segments[1:]:
        text = current["text"]
        # Končí věta? (tečka, otazník, vykřičník, nebo pauza > 2s)
        ends_sentence = (
            text.rstrip().endswith((".", "!", "?", "...", "…"))
            or (seg["start"] - current["end"]) > 2.0
        )

        if ends_sentence:
            merged.append(current)
            current = {
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"],
            }
        else:
            # Spojit s předchozím
            current["end"] = seg["end"]
            current["text"] = current["text"].rstrip() + " " + seg["text"].lstrip()

    merged.append(current)
    return merged


def process_file(file_path: str, original_name: str, job_id: str):
    """Zpracuje jeden soubor - přepis + detekce zdravotních tvrzení (běží v threadu)"""
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["progress"] = 5

        segments = transcribe_file(file_path, job_id)

        jobs[job_id]["progress"] = 95

        # Detekce zdravotních tvrzení per-segment
        health_claims = []
        for seg in segments:
            seg_claims = find_health_claims(seg["text"])
            health_claims.extend(seg_claims)

        jobs[job_id]["segments"] = segments
        jobs[job_id]["health_claims"] = health_claims
        jobs[job_id]["status"] = "done"
        jobs[job_id]["progress"] = 100

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["progress"] = 0


# ── API Endpointy ────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/delete/{job_id}")
async def delete_job(job_id: str):
    """Smaže úlohu a její soubory"""
    if job_id in jobs:
        del jobs[job_id]
    # Smazat nahrané soubory
    for f in UPLOAD_DIR.glob(f"{job_id}.*"):
        f.unlink(missing_ok=True)
    return JSONResponse({"ok": True})


@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...), model: str = Form("small")):
    """Nahrání souborů (i dávkově) a spuštění přepisu"""
    created_jobs = []

    for file in files:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue

        job_id = str(uuid.uuid4())[:8]
        file_path = UPLOAD_DIR / f"{job_id}{ext}"

        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

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

        t = threading.Thread(target=process_file, args=(str(file_path), file.filename, job_id), daemon=True)
        t.start()
        created_jobs.append({"id": job_id, "filename": file.filename})

    return JSONResponse({"jobs": created_jobs})


@app.get("/status/{job_id}")
async def job_status(job_id: str):
    """Stav zpracování"""
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
    """Výsledky přepisu"""
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
    """Uloží editovaný text zpět do jobu"""
    if job_id not in jobs or jobs[job_id]["status"] != "done":
        return JSONResponse({"error": "Přepis není k dispozici"}, status_code=400)

    data = await request.json()
    segments = data.get("segments", [])
    jobs[job_id]["segments"] = segments

    # Přepočítat automatická zdravotní tvrzení po editaci (per-segment)
    auto_claims = []
    for seg in segments:
        auto_claims.extend(find_health_claims(seg["text"]))

    # Zachovat ručně přidané claims
    custom_claims = jobs[job_id].get("custom_claims", [])
    jobs[job_id]["health_claims"] = auto_claims + custom_claims

    return JSONResponse({
        "ok": True,
        "claim_count": len(jobs[job_id]["health_claims"]),
        "health_claims": jobs[job_id]["health_claims"],
    })


@app.get("/dictionary")
async def get_dictionary():
    """Vrátí obsah slovníku oprav"""
    dict_path = BASE_DIR / "dictionary.txt"
    content = dict_path.read_text(encoding="utf-8") if dict_path.exists() else ""
    return JSONResponse({"content": content})


@app.post("/dictionary")
async def save_dictionary(request: Request):
    """Uloží slovník oprav"""
    data = await request.json()
    dict_path = BASE_DIR / "dictionary.txt"
    dict_path.write_text(data.get("content", ""), encoding="utf-8")
    return JSONResponse({"ok": True})


@app.get("/names")
async def get_names():
    """Vrátí obsah seznamu jmen"""
    names_path = BASE_DIR / "names.txt"
    content = names_path.read_text(encoding="utf-8") if names_path.exists() else ""
    return JSONResponse({"content": content})


@app.post("/names")
async def save_names(request: Request):
    """Uloží seznam jmen"""
    data = await request.json()
    names_path = BASE_DIR / "names.txt"
    names_path.write_text(data.get("content", ""), encoding="utf-8")
    return JSONResponse({"ok": True})


@app.post("/translate/{job_id}")
async def translate_job(job_id: str, target_lang: str = Form(...)):
    """Přeloží přepis do zvoleného jazyka"""
    if job_id not in jobs or jobs[job_id]["status"] != "done":
        return JSONResponse({"error": "Přepis není k dispozici"}, status_code=400)

    segments = jobs[job_id]["segments"]
    translated = translate_segments(segments, target_lang, "cs")

    return JSONResponse({"segments": translated, "language": target_lang})


@app.get("/export/{job_id}")
async def export_job(job_id: str, format: str = "txt", lang: str = "original"):
    """Export přepisu do TXT, PDF nebo SRT"""
    if job_id not in jobs or jobs[job_id]["status"] != "done":
        return JSONResponse({"error": "Přepis není k dispozici"}, status_code=400)

    job = jobs[job_id]
    segments = job["segments"]
    filename_base = Path(job["filename"]).stem

    # Pokud je požadován překlad, přeložit
    if lang != "original" and lang != "cs":
        segments = translate_segments(segments, lang, "cs")
        filename_base += f"_{lang}"

    # Unikátní suffix aby se nevrátil cachovaný soubor
    uid = str(uuid.uuid4())[:6]

    if format == "txt":
        out_path = str(OUTPUT_DIR / f"{filename_base}_{uid}.txt")
        export_txt(segments, out_path)
        return FileResponse(out_path, filename=f"{filename_base}.txt",
                          media_type="text/plain; charset=utf-8")

    elif format == "pdf":
        out_path = str(OUTPUT_DIR / f"{filename_base}_{uid}.pdf")
        export_pdf(segments, out_path,
                  health_claims=job["health_claims"],
                  title=f"Přepis: {job['filename']}")
        return FileResponse(out_path, filename=f"{filename_base}.pdf",
                          media_type="application/pdf")

    elif format == "srt":
        out_path = str(OUTPUT_DIR / f"{filename_base}_{uid}.srt")
        export_srt(segments, out_path)
        return FileResponse(out_path, filename=f"{filename_base}.srt",
                          media_type="text/srt; charset=utf-8")

    return JSONResponse({"error": "Neznámý formát"}, status_code=400)


@app.get("/languages")
async def get_languages():
    return JSONResponse(LANGUAGE_NAMES)


@app.get("/export-zip/{job_id}")
async def export_zip(job_id: str, langs: str = ""):
    """Export přepisu jako ZIP obsahující TXT, PDF, SRT pro originál i překlady"""
    if job_id not in jobs or jobs[job_id]["status"] != "done":
        return JSONResponse({"error": "Přepis není k dispozici"}, status_code=400)

    job = jobs[job_id]
    segments = job["segments"]
    filename_base = Path(job["filename"]).stem

    # Prepare list of languages to include
    lang_codes = [l.strip() for l in langs.split(",") if l.strip()] if langs else []

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Original files
        txt_path = str(OUTPUT_DIR / f"{filename_base}.txt")
        export_txt(segments, txt_path)
        zf.write(txt_path, f"{filename_base}.txt")

        pdf_path = str(OUTPUT_DIR / f"{filename_base}.pdf")
        export_pdf(segments, pdf_path,
                   health_claims=job["health_claims"],
                   title=f"Přepis: {job['filename']}")
        zf.write(pdf_path, f"{filename_base}.pdf")

        srt_path = str(OUTPUT_DIR / f"{filename_base}.srt")
        export_srt(segments, srt_path)
        zf.write(srt_path, f"{filename_base}.srt")

        # Translated files
        for lang in lang_codes:
            translated = translate_segments(segments, lang, "cs")
            lang_base = f"{filename_base}_{lang}"

            txt_p = str(OUTPUT_DIR / f"{lang_base}.txt")
            export_txt(translated, txt_p)
            zf.write(txt_p, f"{lang_base}.txt")

            pdf_p = str(OUTPUT_DIR / f"{lang_base}.pdf")
            export_pdf(translated, pdf_p,
                       health_claims=job["health_claims"],
                       title=f"Přepis: {job['filename']} ({lang})")
            zf.write(pdf_p, f"{lang_base}.pdf")

            srt_p = str(OUTPUT_DIR / f"{lang_base}.srt")
            export_srt(translated, srt_p)
            zf.write(srt_p, f"{lang_base}.srt")

    buf.seek(0)
    zip_filename = f"{filename_base}_export.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )


@app.post("/project/save/{job_id}")
async def save_project(job_id: str):
    """Uloží projekt (segmenty, health_claims, filename, custom_claims) do JSON souboru"""
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
    """Vrátí seznam uložených projektů"""
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
    """Načte projekt z JSON souboru zpět do jobs"""
    data = await request.json()
    path = data.get("path")
    if not path or not Path(path).exists():
        return JSONResponse({"error": "Soubor nenalezen"}, status_code=404)

    project_data = json.loads(Path(path).read_text(encoding="utf-8"))
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

    return JSONResponse({"ok": True, "job_id": job_id})


@app.get("/report/{job_id}")
async def health_claims_report(job_id: str):
    """Generuje PDF report obsahující pouze zdravotní tvrzení s timestamps"""
    if job_id not in jobs or jobs[job_id]["status"] != "done":
        return JSONResponse({"error": "Přepis není k dispozici"}, status_code=400)

    job = jobs[job_id]
    claims = job["health_claims"]
    segments = job["segments"]
    filename_base = Path(job["filename"]).stem

    from fpdf import FPDF

    def _fmt_ts(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    pdf = FPDF()
    pdf.add_page()

    font_path = os.path.join(str(BASE_DIR), "static", "DejaVuSans.ttf")
    font_bold_path = os.path.join(str(BASE_DIR), "static", "DejaVuSans-Bold.ttf")
    if os.path.exists(font_path):
        pdf.add_font("DejaVu", "", font_path)
        pdf.add_font("DejaVu", "B", font_bold_path if os.path.exists(font_bold_path) else font_path)
        font_name = "DejaVu"
    else:
        font_name = "Helvetica"

    # Title
    pdf.set_font(font_name, "B", 16)
    pdf.cell(0, 10, f"Report zdravotnich tvrzeni: {job['filename']}",
             new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)

    # Summary
    pdf.set_font(font_name, "B", 12)
    pdf.set_text_color(200, 0, 0)
    pdf.cell(0, 8, f"Celkem nalezeno tvrzeni: {len(claims)}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)

    if not claims:
        pdf.set_font(font_name, "", 11)
        pdf.cell(0, 8, "Zadna zdravotni tvrzeni nebyla nalezena.",
                 new_x="LMARGIN", new_y="NEXT")
    else:
        for i, claim in enumerate(claims, 1):
            claim_text = claim["text"].lower()
            timestamp_str = ""
            for seg in segments:
                if claim_text in seg["text"].lower():
                    timestamp_str = f"[{_fmt_ts(seg['start'])} - {_fmt_ts(seg['end'])}]"
                    break

            pdf.set_font(font_name, "B", 11)
            pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 7, f"{i}. {timestamp_str}",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.set_font(font_name, "", 10)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(0, 6, f"   {claim['text']}",
                          new_x="LMARGIN", new_y="NEXT")
            pdf.set_font(font_name, "", 9)
            pdf.set_text_color(100, 100, 100)
            pdf.multi_cell(0, 5, f"   Duvod: {claim['reason']}",
                          new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(3)

    report_path = str(OUTPUT_DIR / f"{filename_base}_health_report.pdf")
    pdf.output(report_path)

    return FileResponse(report_path, filename=f"{filename_base}_health_report.pdf",
                        media_type="application/pdf")


@app.post("/mark-claim/{job_id}")
async def mark_claim(job_id: str, request: Request):
    """Přidá vlastní zdravotní tvrzení k úloze"""
    if job_id not in jobs:
        return JSONResponse({"error": "Úloha nenalezena"}, status_code=404)

    data = await request.json()
    text = data.get("text", "").strip()
    reason = data.get("reason", "").strip()

    if not text:
        return JSONResponse({"error": "Text tvrzení je povinný"}, status_code=400)

    claim = {"text": text, "start": 0, "end": len(text), "reason": reason or "rucne oznaceno"}

    # Nekopírovat pokud už existuje
    existing_texts = [c["text"].lower() for c in jobs[job_id]["health_claims"]]
    if text.lower() not in existing_texts:
        jobs[job_id]["health_claims"].append(claim)

    # Track custom claims separately
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
    """Odebere zdravotní tvrzení z úlohy"""
    if job_id not in jobs:
        return JSONResponse({"error": "Úloha nenalezena"}, status_code=404)

    data = await request.json()
    text = data.get("text", "").strip()

    if not text:
        return JSONResponse({"error": "Text tvrzení je povinný"}, status_code=400)

    # Remove from health_claims
    jobs[job_id]["health_claims"] = [
        c for c in jobs[job_id]["health_claims"]
        if c["text"].strip() != text
    ]

    # Remove from custom_claims if present
    if "custom_claims" in jobs[job_id]:
        jobs[job_id]["custom_claims"] = [
            c for c in jobs[job_id]["custom_claims"]
            if c["text"].strip() != text
        ]

    return JSONResponse({
        "ok": True,
        "claim_count": len(jobs[job_id]["health_claims"]),
        "health_claims": jobs[job_id]["health_claims"],
    })


# ── Spuštění ─────────────────────────────────────────────────

def run_server():
    """Spustí FastAPI server na pozadí"""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    import subprocess
    import threading
    import time
    import webbrowser

    # Spustit server v threadu
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    time.sleep(1.5)

    # Otevrit jako "app" okno v Edge/Chrome (bez adresniho radku)
    url = "http://127.0.0.1:8000"
    opened = False

    # Zkusit Edge v app modu
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for edge in edge_paths:
        if os.path.exists(edge):
            subprocess.Popen([edge, f"--app={url}", "--new-window"])
            opened = True
            break

    # Zkusit Chrome v app modu
    if not opened:
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for chrome in chrome_paths:
            if os.path.exists(chrome):
                subprocess.Popen([chrome, f"--app={url}", "--new-window"])
                opened = True
                break

    # Fallback - normalni prohlizec
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
