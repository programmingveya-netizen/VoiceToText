"""
Modul pro správu úloh (jobs) - přepis souborů na pozadí.
"""

from transcription import transcribe_file
from dictionary_utils import load_dictionary
from pathlib import Path

# Sdílený stav úloh
jobs: dict[str, dict] = {}


def process_file(file_path: str, original_name: str, job_id: str, base_dir: Path):
    """Zpracuje jeden soubor - přepis (běží v threadu)"""
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["progress"] = 5

        model_size = jobs[job_id].get("model", "small")
        input_language = jobs[job_id].get("input_language", "cs")
        dictionary = load_dictionary(base_dir)

        def on_progress(progress):
            jobs[job_id]["progress"] = progress

        segments = transcribe_file(file_path, model_size, dictionary, on_progress, input_language)

        jobs[job_id]["progress"] = 95

        jobs[job_id]["segments"] = segments
        jobs[job_id]["health_claims"] = []
        jobs[job_id]["status"] = "done"
        jobs[job_id]["progress"] = 100

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["progress"] = 0
