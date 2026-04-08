"""
Modul pro přepis audia/videa na text pomocí faster-whisper.
"""


# Český prompt pro Whisper - zlepšuje kvalitu diakritiky a rozpoznávání
CZECH_PROMPT = (
    "Dobrý večer, tady Jiří Černota, zdravím všechny příznivce zdravého životního stylu, "
    "esenciálních olejů, super potravin a dalších věcí, které podporují naše těla. "
    "Dnes si povíme o přírodních produktech, doplňcích stravy, vitamínech a minerálech. "
    "Budeme mluvit o zdraví, imunitě, prevenci a o tom, jak se zbavit různých potíží. "
    "Můžete se ptát v komentářích, napište odkud jste. Děkuji za sledování."
)


def get_whisper_model(model_size: str = "small"):
    """Načte a cachuje Whisper model"""
    if not hasattr(get_whisper_model, "_cache"):
        get_whisper_model._cache = {}
    if model_size not in get_whisper_model._cache:
        import os
        os.environ["CT2_VERBOSE"] = "0"
        from faster_whisper import WhisperModel
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
            current["end"] = seg["end"]
            current["text"] = current["text"].rstrip() + " " + seg["text"].lstrip()

    merged.append(current)
    return merged


INPUT_LANGUAGE_PROMPTS = {
    "cs": CZECH_PROMPT,
    "en": "Good evening, welcome to another episode. Today we will talk about health, natural products and essential oils.",
    "de": "Guten Abend, willkommen zu einer weiteren Folge. Heute sprechen wir über Gesundheit und natürliche Produkte.",
    "sk": "Dobrý večer, vitajte pri ďalšom diele. Dnes si povieme o zdraví a prírodných produktoch.",
    "pl": "Dobry wieczór, witamy w kolejnym odcinku. Dziś porozmawiamy o zdrowiu i naturalnych produktach.",
    "hu": "Jó estét, üdvözöljük a következő epizódban. Ma az egészségről és a természetes termékekről beszélünk.",
    "ro": "Bună seara, bine ați venit la un nou episod. Astăzi vom vorbi despre sănătate și produse naturale.",
}


def transcribe_file(file_path: str, model_size: str, dictionary: dict[str, str],
                    progress_callback=None, input_language: str = "cs") -> list[dict]:
    """Přepíše audio/video soubor pomocí faster-whisper"""
    from dictionary_utils import apply_dictionary

    model = get_whisper_model(model_size)
    beam = 5 if model_size in ("medium", "large-v3") else 3

    # Auto-detect nebo specifický jazyk
    lang_param = None if input_language == "auto" else input_language
    prompt = INPUT_LANGUAGE_PROMPTS.get(input_language, "")

    segments_iter, info = model.transcribe(
        file_path,
        language=lang_param,
        beam_size=beam,
        best_of=beam,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        initial_prompt=prompt if prompt else None,
        condition_on_previous_text=True,
        temperature=0,
    )

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
        if progress_callback and info.duration and info.duration > 0:
            progress = min(95, int((segment.end / info.duration) * 100))
            progress_callback(progress)

    return merge_into_sentences(raw_segments)
