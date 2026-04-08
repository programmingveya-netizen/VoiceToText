"""Testy pro modul exporter.py"""

import tempfile
from pathlib import Path
from exporter import export_srt, export_txt, format_timestamp, format_srt_timestamp


def test_format_timestamp():
    """Formátování sekund na HH:MM:SS"""
    assert format_timestamp(0) == "00:00:00"
    assert format_timestamp(61) == "00:01:01"
    assert format_timestamp(3661) == "01:01:01"


def test_format_srt_timestamp():
    """Formátování sekund na SRT formát"""
    assert format_srt_timestamp(0) == "00:00:00,000"
    assert format_srt_timestamp(1.5) == "00:00:01,500"


def test_srt_numbering_no_gaps():
    """SRT číslování nemá díry při prázdných segmentech"""
    segments = [
        {"start": 0.0, "end": 2.0, "text": "First"},
        {"start": 2.0, "end": 4.0, "text": ""},
        {"start": 4.0, "end": 6.0, "text": "  "},
        {"start": 6.0, "end": 8.0, "text": "Second"},
        {"start": 8.0, "end": 10.0, "text": "Third"},
    ]
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w") as f:
        path = f.name

    export_srt(segments, path)
    content = Path(path).read_text(encoding="utf-8")
    lines = content.strip().split("\n")

    # Číslování musí být 1, 2, 3 (bez děr)
    numbers = [line for line in lines if line.strip().isdigit()]
    assert numbers == ["1", "2", "3"]

    Path(path).unlink()


def test_export_txt_with_timestamps():
    """TXT export obsahuje timestamps"""
    segments = [
        {"start": 0.0, "end": 5.0, "text": "Hello world"},
        {"start": 5.0, "end": 10.0, "text": "Second line"},
    ]
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        path = f.name

    export_txt(segments, path)
    content = Path(path).read_text(encoding="utf-8")

    assert "[00:00:00 - 00:00:05]" in content
    assert "Hello world" in content
    assert "Second line" in content

    Path(path).unlink()


def test_export_txt_empty_segments():
    """Prázdné segmenty se exportují bez chyby"""
    segments = []
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        path = f.name

    export_txt(segments, path)
    content = Path(path).read_text(encoding="utf-8")
    assert content == ""

    Path(path).unlink()
