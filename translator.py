"""
Modul pro překlad textu s timestamps.
Vlastní jména jsou zachována bez překladu.
"""

import re
from pathlib import Path
from deep_translator import GoogleTranslator

LANGUAGE_MAP = {
    "cs": "cs",  # čeština
    "pl": "pl",  # polština
    "en": "en",  # angličtina
    "de": "de",  # němčina
    "sk": "sk",  # slovenština
    "hu": "hu",  # maďarština
    "ro": "ro",  # rumunština
}

LANGUAGE_NAMES = {
    "cs": "Čeština",
    "pl": "Polština",
    "en": "Angličtina",
    "de": "Němčina",
    "sk": "Slovenština",
    "hu": "Maďarština",
    "ro": "Rumunština",
}

# Běžná česká slova začínající velkým písmenem (ne jména)
COMMON_CZECH_WORDS = {
    "Dobrý", "Dobré", "Dobrá", "Dobře", "Dnes", "Děkuji", "Díky",
    "Pokud", "Prosím", "Proto", "Právě", "Přírodní", "Podle",
    "Každý", "Každá", "Každé", "Když", "Kde", "Kdo", "Který", "Která", "Které",
    "Také", "Takže", "Tady", "Tento", "Tato", "Toto", "Teď",
    "Jsem", "Jsou", "Jest", "Jak", "Jaký", "Jaká", "Jaké",
    "Ale", "Asi", "Ahoj",
    "Má", "Máme", "Mám", "Může", "Musí", "Musím", "Možná", "Myslím",
    "Na", "Naše", "Náš", "Není", "Nikdy", "Nic",
    "Od", "Ovšem", "Opravdu",
    "Samozřejmě", "Snad", "Stále",
    "Už", "Určitě",
    "Velký", "Velká", "Velmi", "Vlastně", "Víte", "Vidíte", "Vítejte",
    "Zdravím", "Zdá", "Zkuste", "Znamená",
    "Facebook", "Instagram", "YouTube",
    "Pardon", "Super",
}


def load_names_list() -> set[str]:
    """Načte seznam jmen ze souboru names.txt (jedno jméno/fráze na řádek)"""
    names_path = Path(__file__).parent / "names.txt"
    names = set()
    if names_path.exists():
        for line in names_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                names.add(line)
    return names


def detect_names(text: str, known_names: set[str]) -> list[str]:
    """Detekuje vlastní jména v textu"""
    names = []

    # Nejdřív přidat známá jména ze seznamu
    for name in known_names:
        if name in text:
            names.append(name)

    # Detekce dvouslovných jmen (Jiří Černota, Jan Novák, ...)
    pattern = r'\b([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]+)\s+([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]+)\b'
    for match in re.finditer(pattern, text):
        first, second = match.group(1), match.group(2)
        full = f"{first} {second}"
        if full in names:
            continue
        # Oba musí mít velké písmeno a nesmí být běžná česká slova
        if first not in COMMON_CZECH_WORDS and second not in COMMON_CZECH_WORDS:
            names.append(full)

    return names


def protect_names(text: str, names: list[str]) -> tuple[str, dict[str, str]]:
    """Nahradí jména placeholdery před překladem"""
    placeholders = {}
    # Seřadit od nejdelších - aby "Jan Novák" se nahradil dřív než "Jan"
    sorted_names = sorted(names, key=len, reverse=True)
    for i, name in enumerate(sorted_names):
        placeholder = f"NAMEPLACEHOLDER{i:03d}"
        if name in text:
            text = text.replace(name, placeholder)
            placeholders[placeholder] = name
    return text, placeholders


def restore_names(text: str, placeholders: dict[str, str]) -> str:
    """Obnoví jména z placeholderů po překladu"""
    for placeholder, name in placeholders.items():
        # Google Translate občas změní velikost nebo přidá mezery
        text = re.sub(
            re.escape(placeholder).replace("0", "[0O]?0?"),
            name,
            text,
            flags=re.IGNORECASE
        )
        # Přímá náhrada jako fallback
        text = text.replace(placeholder, name)
        text = text.replace(placeholder.lower(), name)
        text = text.replace(placeholder.upper(), name)
    return text


def translate_segments(segments: list[dict], target_lang: str, source_lang: str = "cs") -> list[dict]:
    """
    Přeloží segmenty (s timestamps) do cílového jazyka.
    Vlastní jména jsou zachována.
    """
    if target_lang == source_lang:
        return segments

    translator = GoogleTranslator(source=source_lang, target=target_lang)
    known_names = load_names_list()

    # Detekovat jména v celém textu
    full_text = " ".join(s["text"] for s in segments)
    detected_names = detect_names(full_text, known_names)

    translated = []

    batch_texts = []
    batch_placeholders = []
    batch_indices = []
    current_length = 0

    for i, seg in enumerate(segments):
        text = seg["text"].strip()
        if not text:
            translated.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": ""
            })
            continue

        # Ochránit jména
        protected_text, placeholders = protect_names(text, detected_names)

        if current_length + len(protected_text) + 1 > 4500 and batch_texts:
            _translate_batch(translator, segments, batch_texts, batch_placeholders,
                           batch_indices, translated)
            batch_texts = []
            batch_placeholders = []
            batch_indices = []
            current_length = 0

        batch_texts.append(protected_text)
        batch_placeholders.append(placeholders)
        batch_indices.append(i)
        current_length += len(protected_text) + 1

    # Přeložit zbytek
    if batch_texts:
        _translate_batch(translator, segments, batch_texts, batch_placeholders,
                       batch_indices, translated)

    translated.sort(key=lambda x: x["start"])
    return translated


def _translate_batch(translator, segments, batch_texts, batch_placeholders,
                    batch_indices, translated):
    """Přeloží dávku textů a obnoví jména"""
    combined = "\n".join(batch_texts)
    try:
        result = translator.translate(combined)
        parts = result.split("\n")
        for j, idx in enumerate(batch_indices):
            t = parts[j] if j < len(parts) else batch_texts[j]
            # Obnovit jména z placeholderů
            t = restore_names(t, batch_placeholders[j])
            translated.append({
                "start": segments[idx]["start"],
                "end": segments[idx]["end"],
                "text": t.strip()
            })
    except Exception:
        for j, idx in enumerate(batch_indices):
            translated.append({
                "start": segments[idx]["start"],
                "end": segments[idx]["end"],
                "text": segments[idx]["text"]
            })
