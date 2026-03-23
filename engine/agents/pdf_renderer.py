"""
opener-ultra-mvp / engine / agents / pdf_renderer.py
=====================================================
CopyDocument → 고밀도 5-슬라이드 PDF 렌더러

reportlab을 사용해 제안서 PDF를 생성합니다.
각 슬라이드는 A4 가로(landscape) 포맷, 296 x 210 mm.
"""
from __future__ import annotations

import os
from typing import List, Optional
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black, Color
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

# ── 디자인 토큰 ────────────────────────────────────────────────────
PALETTE = {
    "cover_bg":   HexColor("#0A0A12"),
    "pain_bg":    HexColor("#12111A"),
    "solution_bg":HexColor("#0D1520"),
    "proof_bg":   HexColor("#0D1A14"),
    "cta_bg":     HexColor("#140D1A"),
    "accent":     HexColor("#7B61FF"),
    "accent2":    HexColor("#A48FFF"),
    "gold":       HexColor("#F0B429"),
    "green":      HexColor("#34D399"),
    "red":        HexColor("#F87171"),
    "text":       HexColor("#E8E6F0"),
    "text2":      HexColor("#9E9BB5"),
    "text3":      HexColor("#5A5870"),
    "surface":    HexColor("#1C1C2E"),
    "border":     HexColor("#2E2E48"),
}

PAGE_W, PAGE_H = landscape(A4)   # 841.89 x 595.28 pt
MARGIN = 48
SAFE_W = PAGE_W - MARGIN * 2
SLIDE_BG_BY_TYPE = {
    "cover":    "cover_bg",
    "pain":     "pain_bg",
    "solution": "solution_bg",
    "proof":    "proof_bg",
    "cta":      "cta_bg",
}


def _draw_bg(c: rl_canvas.Canvas, bg_color: Color):
    c.setFillColor(bg_color)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)


def _accent_bar(c: rl_canvas.Canvas, color: Color, y: float, w: float = 40, h: float = 3):
    c.setFillColor(color)
    c.roundRect(MARGIN, y, w, h, 1.5, fill=1, stroke=0)


def _slide_num(c: rl_canvas.Canvas, num: int, total: int):
    c.setFont("Helvetica", 8)
    c.setFillColor(PALETTE["text3"])
    label = f"{num} / {total}"
    c.drawRightString(PAGE_W - MARGIN, 18, label)


def _product_tag(c: rl_canvas.Canvas, product: str, accent: Color):
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(accent)
    c.drawString(MARGIN, 18, product.upper())


def _wrap_text(c: rl_canvas.Canvas, text: str, x: float, y: float,
               max_width: float, font: str, size: float,
               color: Color, line_height: float = 1.3) -> float:
    """텍스트를 max_width 안에서 줄바꿈해 그리고 최종 y를 반환."""
    c.setFont(font, size)
    c.setFillColor(color)
    words = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        if c.stringWidth(test, font, size) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)

    cur_y = y
    for ln in lines:
        c.drawString(x, cur_y, ln)
        cur_y -= size * line_height
    return cur_y


# ── 슬라이드별 레이아웃 ─────────────────────────────────────────────

def _render_cover(c: rl_canvas.Canvas, slide: dict, product: str, buyer: str):
    bg = PALETTE["cover_bg"]
    _draw_bg(c, bg)

    # 대각선 accent 사각형
    c.setFillColor(HexColor("#1A1530"))
    c.rect(PAGE_W * 0.58, 0, PAGE_W * 0.42, PAGE_H, fill=1, stroke=0)

    # accent bar
    _accent_bar(c, PALETTE["accent"], PAGE_H - MARGIN - 10, 60, 4)

    # Headline
    hl = slide.get("headline", "")
    y = PAGE_H - MARGIN - 36
    y = _wrap_text(c, hl, MARGIN, y, PAGE_W * 0.52,
                   "Helvetica-Bold", 34, PALETTE["text"], 1.25)

    # Subheadline
    shl = slide.get("subheadline", "")
    y -= 14
    _wrap_text(c, shl, MARGIN, y, PAGE_W * 0.50,
               "Helvetica", 14, PALETTE["text2"], 1.35)

    # Buyer tag
    c.setFont("Helvetica", 10)
    c.setFillColor(PALETTE["accent2"])
    c.drawString(MARGIN, MARGIN + 24, f"Prepared for {buyer}")
    c.setFillColor(PALETTE["text3"])
    c.drawString(MARGIN, MARGIN + 10, product)

    # Right side decoration — vertical line
    c.setStrokeColor(PALETTE["accent"])
    c.setLineWidth(1)
    c.line(PAGE_W * 0.58, 40, PAGE_W * 0.58, PAGE_H - 40)

    _slide_num(c, 1, 5)


def _render_pain(c: rl_canvas.Canvas, slide: dict, product: str):
    _draw_bg(c, PALETTE["pain_bg"])
    _accent_bar(c, PALETTE["red"], PAGE_H - MARGIN - 8, 44, 3)

    y = PAGE_H - MARGIN - 30
    y = _wrap_text(c, slide.get("headline", ""), MARGIN, y,
                   SAFE_W * 0.6, "Helvetica-Bold", 26, PALETTE["text"], 1.2)

    y -= 10
    y = _wrap_text(c, slide.get("subheadline", ""), MARGIN, y,
                   SAFE_W * 0.58, "Helvetica", 13, PALETTE["red"], 1.3)

    y -= 16
    y = _wrap_text(c, slide.get("body", ""), MARGIN, y,
                   SAFE_W * 0.58, "Helvetica", 11, PALETTE["text2"], 1.45)

    # Bullets
    bullets = slide.get("bullets", [])
    y -= 18
    for b in bullets:
        c.setFillColor(PALETTE["red"])
        c.circle(MARGIN + 5, y + 3, 3, fill=1, stroke=0)
        _wrap_text(c, b, MARGIN + 16, y, SAFE_W * 0.55,
                   "Helvetica", 11, PALETTE["text"], 1.35)
        y -= 22

    _product_tag(c, product, PALETTE["red"])
    _slide_num(c, 2, 5)


def _render_solution(c: rl_canvas.Canvas, slide: dict, product: str):
    _draw_bg(c, PALETTE["solution_bg"])

    # Split layout: left copy, right feature blocks
    col_split = PAGE_W * 0.52
    _accent_bar(c, PALETTE["accent"], PAGE_H - MARGIN - 8, 44, 3)

    y = PAGE_H - MARGIN - 30
    y = _wrap_text(c, slide.get("headline", ""), MARGIN, y,
                   col_split - MARGIN - 20, "Helvetica-Bold", 26, PALETTE["text"], 1.2)

    y -= 10
    y = _wrap_text(c, slide.get("subheadline", ""), MARGIN, y,
                   col_split - MARGIN - 20, "Helvetica", 12, PALETTE["accent2"], 1.3)

    y -= 14
    _wrap_text(c, slide.get("body", ""), MARGIN, y,
               col_split - MARGIN - 20, "Helvetica", 11, PALETTE["text2"], 1.45)

    # Right: feature bullet cards
    bullets = slide.get("bullets", [])
    rx = col_split + 20
    ry = PAGE_H - MARGIN - 20
    card_h = 58
    card_gap = 12
    for b in bullets:
        c.setFillColor(PALETTE["surface"])
        c.roundRect(rx, ry - card_h, PAGE_W - rx - MARGIN, card_h, 8, fill=1, stroke=0)
        c.setStrokeColor(PALETTE["accent"])
        c.setLineWidth(0.5)
        c.roundRect(rx, ry - card_h, PAGE_W - rx - MARGIN, card_h, 8, fill=0, stroke=1)

        # accent left bar
        c.setFillColor(PALETTE["accent"])
        c.roundRect(rx, ry - card_h, 3, card_h, 1.5, fill=1, stroke=0)

        _wrap_text(c, b, rx + 14, ry - 18,
                   PAGE_W - rx - MARGIN - 22, "Helvetica", 10, PALETTE["text"], 1.35)
        ry -= card_h + card_gap

    _product_tag(c, product, PALETTE["accent"])
    _slide_num(c, 3, 5)


def _render_proof(c: rl_canvas.Canvas, slide: dict, product: str):
    _draw_bg(c, PALETTE["proof_bg"])
    _accent_bar(c, PALETTE["green"], PAGE_H - MARGIN - 8, 44, 3)

    y = PAGE_H - MARGIN - 30
    y = _wrap_text(c, slide.get("headline", ""), MARGIN, y,
                   SAFE_W * 0.58, "Helvetica-Bold", 26, PALETTE["text"], 1.2)

    y -= 10
    y = _wrap_text(c, slide.get("subheadline", ""), MARGIN, y,
                   SAFE_W * 0.58, "Helvetica", 12, PALETTE["text2"], 1.3)

    # Story body in a quote box
    body = slide.get("body", "")
    if body:
        box_y = y - 14
        box_h = 72
        c.setFillColor(HexColor("#0D2018"))
        c.roundRect(MARGIN, box_y - box_h, SAFE_W * 0.6, box_h, 6, fill=1, stroke=0)
        c.setFillColor(PALETTE["green"])
        c.roundRect(MARGIN, box_y - box_h, 3, box_h, 1.5, fill=1, stroke=0)
        _wrap_text(c, body, MARGIN + 14, box_y - 14,
                   SAFE_W * 0.55, "Helvetica-Oblique", 10, PALETTE["text2"], 1.45)
        y = box_y - box_h - 16

    # Metric bullets
    bullets = slide.get("bullets", [])
    bx = PAGE_W * 0.68
    by = PAGE_H - MARGIN - 30
    for b in bullets:
        c.setFillColor(PALETTE["surface"])
        c.roundRect(bx, by - 44, PAGE_W - bx - MARGIN, 44, 8, fill=1, stroke=0)
        c.setFillColor(PALETTE["green"])
        c.roundRect(bx, by - 44, 3, 44, 1.5, fill=1, stroke=0)
        _wrap_text(c, b, bx + 12, by - 14,
                   PAGE_W - bx - MARGIN - 18, "Helvetica-Bold", 10, PALETTE["text"], 1.35)
        by -= 54

    _product_tag(c, product, PALETTE["green"])
    _slide_num(c, 4, 5)


def _render_cta(c: rl_canvas.Canvas, slide: dict, product: str):
    _draw_bg(c, PALETTE["cta_bg"])

    # Full-width gradient overlay on right
    c.setFillColor(HexColor("#1E0D30"))
    c.rect(PAGE_W * 0.55, 0, PAGE_W * 0.45, PAGE_H, fill=1, stroke=0)

    _accent_bar(c, PALETTE["gold"], PAGE_H - MARGIN - 8, 44, 4)

    y = PAGE_H - MARGIN - 30
    y = _wrap_text(c, slide.get("headline", ""), MARGIN, y,
                   SAFE_W * 0.50, "Helvetica-Bold", 30, PALETTE["text"], 1.2)

    y -= 10
    y = _wrap_text(c, slide.get("subheadline", ""), MARGIN, y,
                   SAFE_W * 0.50, "Helvetica", 13, PALETTE["gold"], 1.3)

    y -= 14
    _wrap_text(c, slide.get("body", ""), MARGIN, y,
               SAFE_W * 0.50, "Helvetica", 11, PALETTE["text2"], 1.45)

    # Next step bullets on right
    bullets = slide.get("bullets", [])
    rx = PAGE_W * 0.57
    ry = PAGE_H - MARGIN - 40
    for i, b in enumerate(bullets):
        num_label = f"0{i+1}"
        c.setFont("Helvetica-Bold", 20)
        c.setFillColor(PALETTE["accent"])
        c.drawString(rx, ry, num_label)
        _wrap_text(c, b, rx + 36, ry,
                   PAGE_W - rx - MARGIN - 36, "Helvetica", 11, PALETTE["text"], 1.35)
        ry -= 52

    _product_tag(c, product, PALETTE["gold"])
    _slide_num(c, 5, 5)


# ── 메인 렌더러 ────────────────────────────────────────────────────

def render_pdf(copy_doc: dict, output_path: str) -> str:
    """
    CopyDocument.to_dict() 결과를 받아 PDF 파일을 생성하고 경로를 반환합니다.
    """
    meta   = copy_doc.get("meta", {})
    slides = copy_doc.get("slides", [])
    product = meta.get("product_name", "Product")
    buyer   = meta.get("buyer_name",   "Valued Prospect")

    c = rl_canvas.Canvas(output_path, pagesize=landscape(A4))
    c.setTitle(f"{product} — Proposal for {buyer}")

    RENDERERS = {
        "cover":    _render_cover,
        "pain":     _render_pain,
        "solution": _render_solution,
        "proof":    _render_proof,
        "cta":      _render_cta,
    }

    for slide in slides:
        stype = slide.get("type", "pain")
        renderer = RENDERERS.get(stype, _render_pain)
        if stype == "cover":
            renderer(c, slide, product, buyer)
        else:
            renderer(c, slide, product)
        c.showPage()

    c.save()
    return output_path
