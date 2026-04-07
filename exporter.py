"""
Modul pro export přepisu do TXT, PDF a SRT.
Zdravotní tvrzení jsou v PDF zvýrazněna červeně (pouze konkrétní fráze).
"""

import os
import re
from fpdf import FPDF


def format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_srt_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def find_claim_ranges(text: str, health_claims: list[dict] | None) -> list[dict]:
    """Najde pozice zdravotních frází v textu segmentu"""
    if not health_claims:
        return []

    ranges = []
    text_lower = text.lower()

    for claim in health_claims:
        claim_lower = claim["text"].lower()
        start = 0
        while True:
            idx = text_lower.find(claim_lower, start)
            if idx == -1:
                break
            # Zkontrolovat překryv
            overlap = any(idx < r["end"] and (idx + len(claim["text"])) > r["start"] for r in ranges)
            if not overlap:
                ranges.append({
                    "start": idx,
                    "end": idx + len(claim["text"]),
                    "reason": claim["reason"]
                })
            start = idx + 1

    ranges.sort(key=lambda r: r["start"])
    return ranges


def export_txt(segments: list[dict], output_path: str, with_timestamps: bool = True) -> str:
    lines = []
    for seg in segments:
        if with_timestamps:
            ts_start = format_timestamp(seg["start"])
            ts_end = format_timestamp(seg["end"])
            lines.append(f"[{ts_start} - {ts_end}] {seg['text']}")
        else:
            lines.append(seg["text"])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path


def export_pdf(segments: list[dict], output_path: str,
               with_timestamps: bool = True,
               health_claims: list[dict] | None = None,
               title: str = "Přepis") -> str:
    """Export do PDF - zdravotní fráze červeně inline"""
    pdf = FPDF()
    pdf.add_page()

    font_path = os.path.join(os.path.dirname(__file__), "static", "DejaVuSans.ttf")
    font_bold_path = os.path.join(os.path.dirname(__file__), "static", "DejaVuSans-Bold.ttf")

    if os.path.exists(font_path):
        pdf.add_font("DejaVu", "", font_path)
        pdf.add_font("DejaVu", "B", font_bold_path if os.path.exists(font_bold_path) else font_path)
        font_name = "DejaVu"
    else:
        font_name = "Helvetica"

    pdf.set_font(font_name, "B", 16)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)

    total_claims = 0

    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue

        # Timestamp
        if with_timestamps:
            ts_start = format_timestamp(seg["start"])
            ts_end = format_timestamp(seg["end"])
            pdf.set_font(font_name, "B", 8)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 5, f"[{ts_start} - {ts_end}]", new_x="LMARGIN", new_y="NEXT")

        # Najít zdravotní fráze v tomto segmentu
        ranges = find_claim_ranges(text, health_claims)

        if not ranges:
            # Žádné tvrzení - normální text
            pdf.set_text_color(0, 0, 0)
            pdf.set_font(font_name, "", 10)
            pdf.multi_cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")
        else:
            # Rozdělit text na části: normální a zvýrazněné
            total_claims += len(ranges)
            parts = []
            last_end = 0

            for r in ranges:
                if r["start"] > last_end:
                    parts.append({"text": text[last_end:r["start"]], "claim": False})
                parts.append({"text": text[r["start"]:r["end"]], "claim": True, "reason": r["reason"]})
                last_end = r["end"]

            if last_end < len(text):
                parts.append({"text": text[last_end:], "claim": False})

            # Sestavit markdown-style text pro multi_cell
            # fpdf2 podporuje write() pro inline formátování
            for part in parts:
                if part["claim"]:
                    pdf.set_text_color(200, 0, 0)
                    pdf.set_font(font_name, "B", 10)
                    pdf.write(5, f"[!]{part['text']}[!]")
                else:
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_font(font_name, "", 10)
                    pdf.write(5, part["text"])

            pdf.ln(5)

            # Vypsat důvody pod textem
            reasons = set(r["reason"] for r in ranges)
            pdf.set_font(font_name, "", 7)
            pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 4, f"    >> {', '.join(reasons)}", new_x="LMARGIN", new_y="NEXT")

        pdf.ln(2)

    # Souhrn
    if total_claims > 0:
        pdf.ln(8)
        pdf.set_fill_color(254, 226, 226)
        pdf.set_text_color(180, 0, 0)
        pdf.set_font(font_name, "B", 11)
        pdf.cell(0, 8, f"  Celkem nalezeno {total_claims} zdravotnich tvrzeni (oznaceno [!]...text...[!])",
                new_x="LMARGIN", new_y="NEXT", fill=True)

    pdf.output(output_path)
    return output_path


def export_srt(segments: list[dict], output_path: str) -> str:
    lines = []
    for i, seg in enumerate(segments, 1):
        text = seg["text"].strip()
        if not text:
            continue
        start = format_srt_timestamp(seg["start"])
        end = format_srt_timestamp(seg["end"])
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path
