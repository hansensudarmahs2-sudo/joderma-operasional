"""Summary Harian sebagai PDF untuk diunduh (5 Okt 2026, permintaan product owner).

Isi sama dengan halaman Summary Harian: catatan Direktur lalu bagian-bagian `DailySummary.sections`.
Font Bitstream Vera bawaan ReportLab (tanpa font sistem, jalan di image python:slim); karakter yang
tidak ada di font diganti padanan ASCII supaya tidak tampil sebagai kotak hitam.
"""
from __future__ import annotations

import io
import os
from xml.sax.saxutils import escape

from django.utils import timezone

DAYS = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
MONTHS = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September",
          "Oktober", "November", "Desember")
TONE = {"ok": "#17734a", "warn": "#8a5a00", "err": "#a1231f", "info": "#0a5c5e"}
FALLBACK = {"→": "->", "←": "<-", "≤": "<=", "≥": ">=", "✓": "v", "✔": "v", "✗": "x", "•": "-",
            "…": "...", "‘": "'", "’": "'", "“": '"', "”": '"', "—": "-", "–": "-", "×": "x"}

_FONTS: dict | None = None


def _fonts() -> dict:
    """Daftarkan Vera sekali; kembalikan nama font dan himpunan karakter yang didukung."""
    global _FONTS
    if _FONTS is None:
        import reportlab
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        base = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
        regular = TTFont("Vera", os.path.join(base, "Vera.ttf"))
        pdfmetrics.registerFont(regular)
        pdfmetrics.registerFont(TTFont("Vera-Bold", os.path.join(base, "VeraBd.ttf")))
        pdfmetrics.registerFont(TTFont("Vera-Italic", os.path.join(base, "VeraIt.ttf")))
        from reportlab.lib.fonts import addMapping

        addMapping("Vera", 0, 0, "Vera")
        addMapping("Vera", 1, 0, "Vera-Bold")
        addMapping("Vera", 0, 1, "Vera-Italic")
        addMapping("Vera", 1, 1, "Vera-Bold")
        _FONTS = {"chars": set(regular.face.charToGlyph)}
    return _FONTS


def clean(text) -> str:
    """Teks aman untuk Paragraph: karakter di luar font diganti, lalu di-escape untuk markup."""
    chars = _fonts()["chars"]
    out = []
    for ch in str(text or ""):
        if ch in ("\n", "\t") or ord(ch) in chars:
            out.append(ch)
        elif ch in FALLBACK:
            out.append(FALLBACK[ch])
        elif ord(ch) >= 0x1F000:  # emoji
            continue
        else:
            out.append("?")
    return escape("".join(out)).replace("\n", "<br/>")


def long_date(day) -> str:
    return f"{DAYS[day.weekday()]}, {day.day} {MONTHS[day.month - 1]} {day.year}"


def build(summary) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    _fonts()
    ink, muted, line = colors.HexColor("#1c2426"), colors.HexColor("#5d6b6e"), colors.HexColor("#dde4e5")
    st = {
        "title": ParagraphStyle("t", fontName="Vera-Bold", fontSize=16, leading=20, textColor=ink),
        "sub": ParagraphStyle("s", fontName="Vera", fontSize=9, leading=12, textColor=muted),
        "h2": ParagraphStyle("h", fontName="Vera-Bold", fontSize=11.5, leading=15, textColor=ink, spaceBefore=8,
                             spaceAfter=3),
        "item": ParagraphStyle("i", fontName="Vera", fontSize=9.5, leading=12.5, textColor=ink),
        "meta": ParagraphStyle("m", fontName="Vera", fontSize=8, leading=10.5, textColor=muted),
        "tag": ParagraphStyle("g", fontName="Vera-Bold", fontSize=8, leading=10.5, alignment=2),
        "note": ParagraphStyle("n", fontName="Vera", fontSize=9.5, leading=13, textColor=ink),
    }
    when = timezone.localtime(summary.sent_at)
    sent = f"Dikirim {clean(summary.sent_by)} pukul {when:%H.%M}"
    if summary.send_count > 1:
        sent += f" · diperbarui {summary.send_count} kali, pertama pukul {timezone.localtime(summary.first_sent_at):%H.%M}"
    story = [
        Paragraph(f"Summary Harian · {clean(long_date(summary.date))}", st["title"]),
        Spacer(1, 2 * mm),
        Paragraph(sent, st["sub"]),
        Spacer(1, 4 * mm),
    ]
    width = A4[0] - 36 * mm
    if summary.note:
        box = Table([[Paragraph("<b>Catatan Direktur</b>", st["note"])], [Paragraph(clean(summary.note), st["note"])]],
                    colWidths=[width])
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e6f0f5")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
        ]))
        story += [box, Spacer(1, 2 * mm)]
    for section in summary.sections:
        head = Paragraph(clean(section.get("title")), st["h2"])
        items = section.get("items") or []
        if not items:
            story.append(KeepTogether([head, Paragraph(clean(section.get("empty") or "Tidak ada."), st["meta"])]))
            continue
        rows = []
        for it in items:
            cell = [Paragraph(clean(it.get("text")), st["item"])]
            if it.get("meta"):
                cell.append(Paragraph(clean(it["meta"]), st["meta"]))
            tag = it.get("tag") or ""
            color = TONE.get(it.get("tone") or "", "#5d6b6e")
            rows.append([cell, Paragraph(f'<font color="{color}">{clean(tag)}</font>', st["tag"]) if tag else ""])
        table = Table(rows, colWidths=[width - 34 * mm, 34 * mm])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, line),
            ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story += [head, table]

    printed = timezone.localtime()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Vera", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(18 * mm, 10 * mm, f"JoDerma Staff Ops · ops.joderma.id · diunduh {printed:%d/%m/%Y %H.%M}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Halaman {doc.page}")
        canvas.restoreState()

    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title=f"Summary Harian {summary.date:%d/%m/%Y}",
                            author="Direktur Operasional JoDerma")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
