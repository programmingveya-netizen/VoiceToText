"""Testy pro modul dictionary_utils.py"""

import tempfile
from pathlib import Path
from dictionary_utils import load_dictionary, apply_dictionary


def test_apply_dictionary():
    """Slovník nahradí chybná slova správnými"""
    dictionary = {"zbevit": "zbavit", "velčí": "velké"}
    text = "Jak se zbevit velčí zrno?"
    result = apply_dictionary(text, dictionary)
    assert result == "Jak se zbavit velké zrno?"


def test_apply_empty_dictionary():
    """Prázdný slovník nezmění text"""
    text = "Original text"
    result = apply_dictionary(text, {})
    assert result == "Original text"


def test_load_dictionary_from_file():
    """Načte slovník ze souboru"""
    with tempfile.TemporaryDirectory() as tmpdir:
        dict_path = Path(tmpdir) / "dictionary.txt"
        dict_path.write_text("chybne = spravne\n# komentar\n\nbad = good\n", encoding="utf-8")
        result = load_dictionary(Path(tmpdir))
        assert result == {"chybne": "spravne", "bad": "good"}


def test_load_dictionary_missing_file():
    """Chybějící soubor vrátí prázdný slovník"""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = load_dictionary(Path(tmpdir))
        assert result == {}


def test_load_dictionary_skips_comments():
    """Komentáře a prázdné řádky se přeskočí"""
    with tempfile.TemporaryDirectory() as tmpdir:
        dict_path = Path(tmpdir) / "dictionary.txt"
        dict_path.write_text("# comment\n\n  \nfoo = bar\n", encoding="utf-8")
        result = load_dictionary(Path(tmpdir))
        assert result == {"foo": "bar"}
