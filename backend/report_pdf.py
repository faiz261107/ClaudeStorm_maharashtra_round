"""Learner session report as a PDF (GET /api/report/{learner}/pdf). Uses reportlab."""

from __future__ import annotations

import io
import time

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor("#141a33"); MUTED = colors.HexColor("#6b7088"); LINE = colors.HexColor("#e2dccf")
PAPER = colors.HexColor("#f7f4ee"); AMBER = colors.HexColor("#f59e0b")
STATE_COL = {"active": "#92400e", "improving": "#0891b2", "resolved": "#15803d", "recurring": "#be123c"}

H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK, spaceAfter=4)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=INK, spaceBefore=12, spaceAfter=6)
BODY = ParagraphStyle("b", fontName="Helvetica", fontSize=9.8, leading=13.5, textColor=INK)
SMALL = ParagraphStyle("s", fontName="Helvetica", fontSize=8.5, leading=11, textColor=MUTED)
CELL = ParagraphStyle("c", fontName="Helvetica", fontSize=8.8, leading=11.5, textColor=INK)


def build_report_pdf(data: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"Re:Learn report — {data['learner']}")
    s = data["summary"]
    story = [Paragraph(f"Re:Learn — session report for {data['learner']}", H1),
             Paragraph(time.strftime("%d %B %Y, %H:%M") + f" · {s['sessions']} session(s) · "
                       f"{s['answered']} question(s) answered · {round((s['explained_share'] or 0) * 100)}% with an explanation", SMALL),
             Spacer(1, 6)]
    tiles = [["Right first time", "Found", "Fixed & verified", "Improving", "Still open", "Recurring", "Held across sessions"],
             [s["right_first_time"], s["found"], s["fixed"], s["improving"], s["still_open"], s["recurring"], s["held_across_sessions"]]]
    t = Table(tiles, colWidths=[174 / 7 * mm] * 7)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PAPER), ("FONTNAME", (0, 0), (-1, 0), "Helvetica"), ("FONTSIZE", (0, 0), (-1, 0), 7.5),
                           ("TEXTCOLOR", (0, 0), (-1, 0), MUTED), ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"), ("FONTSIZE", (0, 1), (-1, 1), 18),
                           ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                           ("LINEAFTER", (0, 0), (-2, -1), 0.5, colors.white)]))
    story += [t, Paragraph("What happened to each idea", H2)]
    if not data["misconceptions"]:
        story.append(Paragraph("No misconceptions were found — every answer came with sound reasoning.", BODY))
    rows = [["Misconception", "State", "Seen", "Probes", "Notes"]]
    for m in data["misconceptions"]:
        notes = []
        if m.get("confidently_held"): notes.append("held with certainty")
        if m.get("held_across_sessions"): notes.append("verified in a later session")
        elif m.get("recheck_pending"): notes.append("recheck pending")
        rows.append([Paragraph(f"<b>{m['name']}</b><br/><font size=8 color='#6b7088'>{m['short']}</font>", CELL),
                     Paragraph(f"<font color='{STATE_COL.get(m['state'], '#141a33')}'><b>{m['state']}</b></font>", CELL),
                     str(m["detected"]), f"{m['probes_passed']}/{m['probes_required']} passed, {m['probes_failed']} failed",
                     Paragraph(", ".join(notes) or "—", CELL)])
    if len(rows) > 1:
        tbl = Table(rows, colWidths=[62 * mm, 22 * mm, 12 * mm, 38 * mm, 40 * mm], repeatRows=1)
        tbl.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.8),
                                 ("TEXTCOLOR", (0, 0), (-1, 0), MUTED), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                                 ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story.append(tbl)
    story.append(Paragraph("What physics says", H2))
    for m in data["misconceptions"]:
        story.append(Paragraph(f"<b>{m['name']}.</b> {m['physics']}", BODY))
        story.append(Spacer(1, 4))
    story.append(Paragraph("Timeline", H2))
    tl = [["#", "Phase", "Item", "Status", "Label", "Conf.", "Result"]]
    for i, a in enumerate(data["timeline"], 1):
        res = "" if a["phase"] == "question" else ("passed" if a["resolved"] else ("inconclusive" if a["resolved"] is None else "failed"))
        tl.append([str(i), a["phase"], a["item_id"], a["status"], a["label"], f"{round(a['confidence'] * 100)}%", res])
    tbl = Table(tl, colWidths=[8 * mm, 18 * mm, 18 * mm, 32 * mm, 36 * mm, 14 * mm, 24 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
                             ("TEXTCOLOR", (0, 0), (-1, 0), MUTED), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
                             ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    story += [tbl, Spacer(1, 10),
              Paragraph("Resolved = right answer AND no trace of the misconception in the reasoning, in two contexts, plus a delayed recheck. "
                        "A correct follow-up alone is never counted as learning.", SMALL)]
    doc.build(story)
    return buf.getvalue()
