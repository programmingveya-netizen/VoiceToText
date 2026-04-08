"""
Modul pro slovník oprav - načítání a aplikace.
"""

from pathlib import Path


def load_dictionary(base_dir: Path) -> dict[str, str]:
    """Načte slovník oprav z dictionary.txt"""
    dict_path = base_dir / "dictionary.txt"
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
