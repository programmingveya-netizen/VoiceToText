"""Testy pro modul transcription.py"""

from transcription import merge_into_sentences


def test_merge_single_segment():
    """Jeden segment zůstane nezměněný"""
    segments = [{"start": 0.0, "end": 5.0, "text": "Hello world."}]
    result = merge_into_sentences(segments)
    assert len(result) == 1
    assert result[0]["text"] == "Hello world."


def test_merge_sentences_by_period():
    """Segmenty končící tečkou se neslučují"""
    segments = [
        {"start": 0.0, "end": 3.0, "text": "First sentence."},
        {"start": 3.0, "end": 6.0, "text": "Second sentence."},
    ]
    result = merge_into_sentences(segments)
    assert len(result) == 2
    assert result[0]["text"] == "First sentence."
    assert result[1]["text"] == "Second sentence."


def test_merge_segments_without_period():
    """Segmenty bez tečky se sloučí do jednoho"""
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Hello"},
        {"start": 2.0, "end": 4.0, "text": "world"},
        {"start": 4.0, "end": 6.0, "text": "how are you."},
    ]
    result = merge_into_sentences(segments)
    assert len(result) == 1
    assert "Hello" in result[0]["text"]
    assert "world" in result[0]["text"]
    assert result[0]["start"] == 0.0
    assert result[0]["end"] == 6.0


def test_merge_by_pause():
    """Pauza > 2 sekundy rozdělí segmenty i bez tečky"""
    segments = [
        {"start": 0.0, "end": 3.0, "text": "Before pause"},
        {"start": 6.0, "end": 9.0, "text": "After pause"},
    ]
    result = merge_into_sentences(segments)
    assert len(result) == 2


def test_merge_empty_input():
    """Prázdný vstup vrátí prázdný výstup"""
    assert merge_into_sentences([]) == []


def test_merge_question_mark():
    """Otazník ukončuje větu"""
    segments = [
        {"start": 0.0, "end": 2.0, "text": "How are you?"},
        {"start": 2.0, "end": 4.0, "text": "I am fine."},
    ]
    result = merge_into_sentences(segments)
    assert len(result) == 2
