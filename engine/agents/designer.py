"""
opener-ultra-mvp / engine / agents / designer.py
=================================================
기업용 PDF 디자이너 에이전트 — DesignerAgent

전체 구성 (A4 세로, 8페이지)
--------------------------------
  P1  Cover                    — 제목, 바이어명, 날짜
  P2  Executive Summary        — KPI 3개 + 핵심 포인트
  P3  Pain Analysis            — 페인포인트 카드 + 인용구
  P4  Solution                 — 기능 3개 + 아이콘 카드
  P5  Chart Insert             — 6단계 시각화 차트 삽입
  P6  ROI Projection           — 재무 테이블 + 요약
  P7  Implementation Roadmap   — 3단계 타임라인
  P8  Global Success Reference — 산업별 가상 PoC + 로고 배지

색상 시스템 — 세련된 네이비/그레이
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

W, H = A4  # 595.28 x 841.89 pt

# ── Palette ──────────────────────────────────────────────────────
class C:
    NAVY_DEEP   = colors.HexColor("#0D1B2A")
    NAVY_MID    = colors.HexColor("#1B3A5C")
    NAVY_LIGHT  = colors.HexColor("#2E6BAD")
    NAVY_PALE   = colors.HexColor("#E8F0FB")
    GRAY_DARK   = colors.HexColor("#2D3748")
    GRAY_MID    = colors.HexColor("#718096")
    GRAY_LIGHT  = colors.HexColor("#EDF2F7")
    GRAY_LINE   = colors.HexColor("#CBD5E0")
    WHITE       = colors.white
    GOLD        = colors.HexColor("#C9A84C")
    GOLD_LIGHT  = colors.HexColor("#F6E9C8")
    GREEN       = colors.HexColor("#276749")
    GREEN_LIGHT = colors.HexColor("#C6F6D5")
    RED_SOFT    = colors.HexColor("#C53030")
    RED_LIGHT   = colors.HexColor("#FED7D7")
    TEAL        = colors.HexColor("#2C7A7B")
    TEAL_LIGHT  = colors.HexColor("#E6FFFA")

FONT    = "Helvetica"
FONTB   = "Helvetica-Bold"
FONTI   = "Helvetica-Oblique"
M       = 36 * mm
M_TOP   = 28 * mm
SAFE_W  = W - M * 2


# ── Drawing primitives ───────────────────────────────────────────

def _rect(c, x, y, w, h, fill=None, stroke=None, radius=0, sw=0.5):
    c.saveState()
    if fill:   c.setFillColor(fill)
    if stroke: c.setStrokeColor(stroke); c.setLineWidth(sw)
    kw = dict(fill=1 if fill else 0, stroke=1 if stroke else 0)
    if radius: c.roundRect(x, y, w, h, radius, **kw)
    else:      c.rect(x, y, w, h, **kw)
    c.restoreState()

def _tx(c, x, y, text, font=FONT, size=10, color=C.GRAY_DARK,
        align="left", maxw=None):
    c.saveState()
    c.setFont(font, size)
    c.setFillColor(color)
    if maxw:
        while c.stringWidth(text, font, size) > maxw and len(text) > 3:
            text = text[:-1]
        if len(text) < len(text): text += "..."
    {"left": c.drawString, "center": c.drawCentredString,
     "right": c.drawRightString}[align](x, y, text)
    c.restoreState()

def _wrap(c, x, y, text, font=FONT, size=10, color=C.GRAY_DARK,
          maxw=None, lh=1.5) -> float:
    if not text: return y
    c.saveState(); c.setFont(font, size); c.setFillColor(color)
    mw = maxw or SAFE_W
    words = text.split(); lines, line = [], ""
    for w_ in words:
        t = (line + " " + w_).strip()
        if c.stringWidth(t, font, size) <= mw: line = t
        else:
            if line: lines.append(line)
            line = w_
    if line: lines.append(line)
    cy = y
    for ln in lines:
        c.drawString(x, cy, ln); cy -= size * lh
    c.restoreState(); return cy

def _hline(c, x, y, w, color=C.GRAY_LINE, lw=0.5):
    c.saveState(); c.setStrokeColor(color); c.setLineWidth(lw)
    c.line(x, y, x + w, y); c.restoreState()

def _footer(c, pg, total, product):
    _hline(c, M, 20 * mm, SAFE_W, C.NAVY_MID, 0.8)
    _tx(c, M, 13 * mm, product, FONT, 7.5, C.GRAY_MID)
    _tx(c, W - M, 13 * mm, f"{pg} / {total}", FONT, 7.5, C.GRAY_MID, "right")
    _tx(c, W/2, 13 * mm, "CONFIDENTIAL", FONTB, 7, C.NAVY_MID, "center")

def _chip(c, x, y, label):
    sw = c.stringWidth(label, FONTB, 7.5)
    pw = sw + 14
    _rect(c, x, y - 10, pw, 13, fill=C.NAVY_MID, radius=2.5)
    _tx(c, x + 7, y - 3.5, label, FONTB, 7.5, C.WHITE)

def _kpi(c, x, y, w, h, val, lbl, sub="", color=C.NAVY_MID, bg=C.NAVY_PALE):
    _rect(c, x, y, w, h, fill=bg, stroke=color, radius=5, sw=0.8)
    _rect(c, x, y + h - 4, w, 4, fill=color)
    vsize = 20 if len(val) < 5 else 16
    _tx(c, x + w/2, y + h*0.52, val, FONTB, vsize, color, "center")
    _tx(c, x + w/2, y + h*0.28, lbl, FONTB, 7.5, C.GRAY_MID, "center")
    if sub: _tx(c, x + w/2, y + h*0.13, sub, FONTI, 7, C.GRAY_MID, "center")

def _logo_badge(c, x, y, w, h, initials, company, sector, color=C.NAVY_MID):
    _rect(c, x, y, w, h, fill=C.WHITE, stroke=color, radius=5, sw=0.8)
    cx_, cy_ = x + 16, y + h/2
    r = 11
    _rect(c, cx_-r, cy_-r, r*2, r*2, fill=color, radius=r)
    _tx(c, cx_, cy_-4.5, initials[:2].upper(), FONTB, 9, C.WHITE, "center")
    _tx(c, x+33, y + h*0.64, company[:22], FONTB, 8.5, C.GRAY_DARK)
    _tx(c, x+33, y + h*0.32, sector[:26], FONT, 7, C.GRAY_MID)


# ── Data models ──────────────────────────────────────────────────

@dataclass
class PainPoint:
    headline: str; detail: str; icon: str = "!"

@dataclass
class Feature:
    title: str; body: str; icon: str = "#"; metric: str = ""

@dataclass
class RoiRow:
    label: str; before: str; after: str; delta: str; positive: bool = True

@dataclass
class RoadmapStep:
    phase: str; label: str; duration: str
    tasks: List[str] = field(default_factory=list)

@dataclass
class Reference:
    company: str; initials: str; sector: str
    poc_title: str
    results: List[Tuple[str, str]]
    quote: str = ""

@dataclass
class DesignPayload:
    product_name:   str
    buyer_company:  str
    buyer_name:     str
    buyer_role:     str
    tagline:        str = ""
    prepared_by:    str = "OpenerUltra AI"
    industry:       str = "B2B SaaS"
    exec_headline:  str = ""
    exec_body:      str = ""
    kpis:           List[Tuple[str, str, str]] = field(default_factory=list)
    pain_points:    List[PainPoint]            = field(default_factory=list)
    pain_quote:     str = ""
    features:       List[Feature]             = field(default_factory=list)
    roi_rows:       List[RoiRow]              = field(default_factory=list)
    roi_summary:    str = ""
    roi_period:     str = "12 months"
    roadmap:        List[RoadmapStep]         = field(default_factory=list)
    references:     List[Reference]           = field(default_factory=list)
    ref_headline:   str = "Global Success Reference"
    chart_paths:    List[str]                 = field(default_factory=list)
    chart_captions: List[str]                 = field(default_factory=list)


# ── Default data ─────────────────────────────────────────────────

DEFAULT_PAIN = [
    PainPoint("Manual Research Overhead",  "Reps spend 3+ hours per account on research instead of selling.", "!"),
    PainPoint("Missed Buying Signals",     "No systematic way to capture trigger events in real time.",       "?"),
    PainPoint("Low Personalization Rate",  "Generic outreach results in sub-10% reply rates.",                "x"),
    PainPoint("Pipeline Visibility Gap",   "Leadership lacks real-time view of signal-to-close correlation.", "~"),
]
DEFAULT_FEATURES = [
    Feature("AI-Powered Research",  "Scans 200+ sources in 90 seconds to surface key buyer signals.", "R", "90 sec"),
    Feature("Personalized Hooks",   "Generates culture-matched outreach copy via role psych mapping.",  "P", "3x reply"),
    Feature("Real-Time Intel",      "Monitors news, funding, hiring triggers to alert at best moment.", "I", "73% faster"),
]
DEFAULT_ROI = [
    RoiRow("Research Time per Rep",    "3.2 hrs/day",  "0.8 hrs/day",  "-75%",   True),
    RoiRow("Avg. Sales Cycle",         "67 days",      "43 days",      "-36%",   True),
    RoiRow("Win Rate",                 "18%",          "26%",          "+44%",   True),
    RoiRow("Outreach Reply Rate",      "6%",           "19%",          "+217%",  True),
    RoiRow("Rep Onboarding Time",      "14 weeks",     "6 weeks",      "-57%",   True),
    RoiRow("Annual Research Cost",     "$142K",        "$28K",         "-$114K", True),
]
DEFAULT_ROADMAP = [
    RoadmapStep("Phase 1", "Setup & Pilot",    "Days 1-14",
                ["Account kickoff & config", "5-rep pilot cohort", "First live briefings"]),
    RoadmapStep("Phase 2", "Team Rollout",     "Days 15-45",
                ["Full team deployment", "CRM/Slack integration", "Pipeline metrics review"]),
    RoadmapStep("Phase 3", "Optimize & Scale", "Days 46-90",
                ["A/B test outreach", "Quarterly ROI report", "Expand to more teams"]),
]

def _default_refs(industry: str) -> List[Reference]:
    refs = [
        Reference("Meridian Capital", "MC", "Financial Services · 850 emp.",
                  "Sales Intelligence PoC — Q2 2024",
                  [("Research time/rep", "2.8h → 0.6h"), ("Reply rate", "7% → 21%"),
                   ("Pipeline (90d)", "+$4.2M"), ("Time-to-close", "-38%")],
                  "Best ROI from any sales tool in 5 years."),
        Reference("Vertex Cloud", "VC", "Enterprise SaaS · 340 emp.",
                  "AI Researcher Deployment — Q3 2024",
                  [("Win rate", "22% → 34%"), ("Signal accuracy", "91% hit rate"),
                   ("Onboarding", "14w → 5w"), ("Revenue (yr 1)", "+$1.8M")],
                  "The personalization quality is genuinely remarkable."),
        Reference("NorthBridge Logistics", "NB", "Supply Chain · 1,200 emp.",
                  "Enterprise Rollout — Q4 2024",
                  [("Sales cycle", "72d → 41d"), ("Research savings", "$186K/yr"),
                   ("Rep NPS", "9.1 / 10"), ("Pipeline cov.", "3.4x improvement")],
                  "Transformed how our team preps for enterprise calls."),
        Reference("Solaris Health Tech", "SH", "HealthTech · 220 emp.",
                  "SMB Fast Deploy", [("Reply rate", "+180%"), ("Cycle", "-29%")]),
        Reference("Koda Retail Group",   "KR", "Retail Tech · 600 emp.",
                  "Mid-Market Scale",  [("Win rate", "+41%"), ("Savings", "$94K/yr")]),
        Reference("Prism Analytics",     "PA", "Data & Analytics · 180 emp.",
                  "Series B Growth",   [("Pipeline", "+$2.1M"), ("Onboard", "-60%")]),
    ]
    overrides = {
        "fintech":    ("Apex Fintech Group",  "AF", "Fintech · 450 emp."),
        "health":     ("CarePoint Systems",   "CP", "Healthcare IT · 780 emp."),
        "commerce":   ("ShopStream Global",   "SS", "E-Commerce · 1,100 emp."),
        "manufactur": ("Ironbridge Mfg.",     "IM", "Manufacturing · 2,400 emp."),
    }
    for key, (co, ini, sec) in overrides.items():
        if key in industry.lower():
            refs[0] = Reference(co, ini, sec, f"{industry} Pilot — Q1 2025",
                                refs[0].results, refs[0].quote)
            break
    return refs


# ── Page renderers ───────────────────────────────────────────────

def _page_cover(c, d: DesignPayload, total: int):
    _rect(c, 0, 0, W, H, fill=C.NAVY_DEEP)
    # right accent panel
    p = c.beginPath()
    p.moveTo(W*0.60, 0); p.lineTo(W, 0); p.lineTo(W, H); p.lineTo(W*0.74, H); p.close()
    c.saveState(); c.setFillColor(C.NAVY_MID); c.drawPath(p, fill=1, stroke=0); c.restoreState()
    # gold bar
    _rect(c, M, H - 22*mm, 52*mm, 3, fill=C.GOLD)
    # product name
    _tx(c, M, H - 44*mm, d.product_name.upper(), FONTB, 40, C.WHITE)
    if d.tagline:
        _tx(c, M, H - 57*mm, d.tagline, FONTI, 13, C.GRAY_MID)
    _hline(c, M, H - 67*mm, SAFE_W*0.50, C.NAVY_LIGHT, 1)
    _tx(c, M, H - 79*mm, "Prepared exclusively for", FONT, 9.5, C.GRAY_MID)
    _tx(c, M, H - 93*mm, d.buyer_company, FONTB, 22, C.WHITE)
    _tx(c, M, H - 106*mm, f"{d.buyer_name}  ·  {d.buyer_role}", FONT, 11, C.GRAY_MID)
    import datetime
    _tx(c, M, H - 121*mm, datetime.date.today().strftime("%B %d, %Y"), FONT, 9, C.GRAY_MID)
    # right panel labels
    for i, lbl in enumerate(["BUSINESS PROPOSAL", "─────────────────", d.industry]):
        _tx(c, W*0.63, H - 56*mm - i*18, lbl,
            FONTB if i == 0 else FONT, 10 if i == 0 else 9,
            C.NAVY_LIGHT if i == 1 else C.GRAY_MID)
    _tx(c, W/2, 16*mm, "STRICTLY CONFIDENTIAL", FONTB, 7.5, C.NAVY_LIGHT, "center")
    _tx(c, W/2, 10*mm, d.prepared_by, FONT, 7.5, C.GRAY_MID, "center")


def _page_exec(c, d: DesignPayload, pg, total):
    _footer(c, pg, total, d.product_name)
    _rect(c, 0, H - M_TOP - 18*mm, W, M_TOP + 18*mm, fill=C.NAVY_DEEP)
    _chip(c, M, H - M_TOP + 1*mm, "EXECUTIVE SUMMARY")
    _tx(c, M, H - M_TOP - 10*mm, d.exec_headline or "Key Value Proposition",
        FONTB, 18, C.WHITE, maxw=SAFE_W)
    y = H - M_TOP - 28*mm
    if d.exec_body:
        y = _wrap(c, M, y, d.exec_body, FONT, 10.5, C.GRAY_DARK, SAFE_W, 1.55)
        y -= 7*mm
    kpis = d.kpis[:3]
    if kpis:
        cw = (SAFE_W - 8*mm) / 3
        for i, (val, lbl, sub) in enumerate(kpis):
            _kpi(c, M + i*(cw + 4*mm), y - 30*mm, cw, 30*mm, val, lbl, sub)
        y -= 40*mm
    _hline(c, M, y - 5*mm, SAFE_W, C.GRAY_LINE)
    y -= 14*mm
    for i, (num, title, body) in enumerate([
        ("01", "Pain Identified",  "Deep buyer research confirms critical workflow gaps"),
        ("02", "Solution Fit",     "Direct feature-to-pain mapping across all priorities"),
        ("03", "Proven Results",   "PoC data validated across comparable deployments"),
    ]):
        bw = (SAFE_W - 8*mm) / 3
        bx = M + i*(bw + 4*mm)
        _rect(c, bx, y - 36*mm, bw, 36*mm, fill=C.GRAY_LIGHT, radius=5)
        _tx(c, bx+10, y - 8*mm, num, FONTB, 15, C.NAVY_LIGHT)
        _tx(c, bx+10, y - 18*mm, title, FONTB, 8.5, C.GRAY_DARK, maxw=bw-16)
        _wrap(c, bx+10, y - 27*mm, body, FONT, 8, C.GRAY_MID, bw-16, 1.4)


def _page_pain(c, d: DesignPayload, pg, total):
    _footer(c, pg, total, d.product_name)
    _rect(c, 0, H - M_TOP - 15*mm, W, M_TOP + 15*mm, fill=C.NAVY_DEEP)
    _chip(c, M, H - M_TOP + 1*mm, "PAIN ANALYSIS")
    _tx(c, M, H - M_TOP - 8*mm, "Current Challenges", FONTB, 17, C.WHITE)
    y = H - M_TOP - 28*mm
    pts = d.pain_points[:4] or DEFAULT_PAIN
    cw = (SAFE_W - 6*mm) / 2
    ch = 40*mm
    for i, pt in enumerate(pts):
        cx_ = M + (i%2)*(cw+6*mm)
        cy_ = y - (i//2)*(ch+5*mm) - ch
        _rect(c, cx_, cy_, cw, ch, fill=C.WHITE, stroke=C.GRAY_LINE, radius=5)
        _rect(c, cx_, cy_, 4, ch, fill=C.NAVY_MID)
        _rect(c, cx_+10, cy_+ch-17, 17, 17, fill=C.RED_LIGHT, radius=3)
        _tx(c, cx_+18.5, cy_+ch-10, pt.icon, FONTB, 9.5, C.RED_SOFT, "center")
        _tx(c, cx_+33, cy_+ch-10, pt.headline, FONTB, 9.5, C.GRAY_DARK, maxw=cw-42)
        _wrap(c, cx_+10, cy_+ch-23, pt.detail, FONT, 8, C.GRAY_MID, cw-18, 1.4)
    y -= (len(pts)//2 + len(pts)%2)*(ch+5*mm) + 8*mm
    if d.pain_quote:
        qh = 26*mm
        _rect(c, M, y-qh, SAFE_W, qh, fill=C.NAVY_PALE, stroke=C.NAVY_LIGHT, radius=5, sw=0.8)
        _rect(c, M, y-qh, 4, qh, fill=C.NAVY_LIGHT)
        _tx(c, M+12, y-7*mm, '"', FONTB, 26, C.NAVY_LIGHT)
        _wrap(c, M+26, y-9*mm, d.pain_quote, FONTI, 9.5, C.GRAY_DARK, SAFE_W-34, 1.5)


def _page_solution(c, d: DesignPayload, pg, total):
    _footer(c, pg, total, d.product_name)
    _rect(c, 0, H - M_TOP - 15*mm, W, M_TOP + 15*mm, fill=C.NAVY_DEEP)
    _chip(c, M, H - M_TOP + 1*mm, "SOLUTION")
    _tx(c, M, H - M_TOP - 8*mm, f"Why {d.product_name}", FONTB, 17, C.WHITE)
    y = H - M_TOP - 24*mm
    feats = d.features[:3] or DEFAULT_FEATURES
    icon_colors = [C.NAVY_LIGHT, C.TEAL, C.GREEN]
    fw = (SAFE_W - 8*mm) / 3
    for i, feat in enumerate(feats):
        fx = M + i*(fw+4*mm)
        _rect(c, fx, y-108*mm, fw, 108*mm, fill=C.WHITE, stroke=C.GRAY_LINE, radius=6, sw=0.8)
        sc = icon_colors[i]
        _rect(c, fx, y-15*mm, fw, 15*mm, fill=sc)
        # icon circle
        cx_, cy_ = fx+fw/2, y-7.5*mm
        c.saveState(); c.setFillColor(C.WHITE)
        c.circle(cx_, cy_, 12, fill=1, stroke=0)
        c.setFont(FONTB, 11); c.setFillColor(sc)
        c.drawCentredString(cx_, cy_-4.5, feat.icon[:1])
        c.restoreState()
        _tx(c, fx+fw/2, y-25*mm, feat.title, FONTB, 10.5, C.GRAY_DARK, "center", fw-12)
        if feat.metric:
            mw = c.stringWidth(feat.metric, FONTB, 8.5)+14
            _rect(c, fx+(fw-mw)/2, y-35*mm, mw, 13, fill=C.GREEN_LIGHT, radius=6)
            _tx(c, fx+fw/2, y-30*mm, feat.metric, FONTB, 8.5, C.GREEN, "center")
        _wrap(c, fx+10, y-46*mm, feat.body, FONT, 8.5, C.GRAY_DARK, fw-20, 1.5)
    y -= 118*mm
    _rect(c, M, y-18*mm, SAFE_W, 18*mm, fill=C.NAVY_DEEP, radius=4)
    for i, (lbl, col_) in enumerate([
        ("Enterprise-Ready", C.NAVY_LIGHT), ("SOC 2 Compliant", C.TEAL),
        ("99.9% Uptime SLA", C.GREEN),      ("24/7 Support", C.GOLD),
    ]):
        sw_ = SAFE_W / 4
        _tx(c, M + i*sw_ + sw_/2, y-9*mm, lbl, FONTB, 8.5, col_, "center")


def _page_chart(c, d: DesignPayload, pg, total):
    _footer(c, pg, total, d.product_name)
    _rect(c, 0, H - M_TOP - 15*mm, W, M_TOP + 15*mm, fill=C.NAVY_DEEP)
    _chip(c, M, H - M_TOP + 1*mm, "DATA VISUALIZATION")
    _tx(c, M, H - M_TOP - 8*mm, "Competitive Intelligence Dashboard", FONTB, 17, C.WHITE)
    chart_paths = [p for p in d.chart_paths if p and os.path.exists(p)]
    caps = d.chart_captions or []
    avail_h = H - M_TOP - 24*mm - M - 14*mm
    avail_y = H - M_TOP - 24*mm

    if not chart_paths:
        _rect(c, M, avail_y - avail_h, SAFE_W, avail_h, fill=C.GRAY_LIGHT, stroke=C.GRAY_LINE, radius=6)
        _tx(c, W/2, avail_y - avail_h/2 + 6, "[ Chart images inserted here ]", FONTI, 11, C.GRAY_MID, "center")
        _tx(c, W/2, avail_y - avail_h/2 - 8, "Pass chart_paths from VisualizerAgent", FONT, 8.5, C.GRAY_MID, "center")
        return

    def _insert(path, x, y, w, h, cap=""):
        _rect(c, x, y, w, h + (8*mm if cap else 0), fill=C.WHITE, stroke=C.GRAY_LINE, radius=5, sw=0.5)
        try:
            img = ImageReader(path)
            iw, ih = img.getSize()
            aspect = iw / ih
            if w/h > aspect: dh = h-4*mm; dw = dh*aspect
            else:            dw = w-4*mm; dh = dw/aspect
            c.drawImage(path, x+(w-dw)/2, y+(h-dh)/2+(3*mm if cap else 0), dw, dh, preserveAspectRatio=True)
        except:
            _tx(c, x+w/2, y+h/2, "Chart unavailable", FONTI, 8.5, C.GRAY_MID, "center")
        if cap:
            _tx(c, x+w/2, y+3*mm, cap, FONTI, 7.5, C.GRAY_MID, "center", w-8*mm)

    n = min(len(chart_paths), 4)
    if n == 1:
        _insert(chart_paths[0], M, avail_y-avail_h, SAFE_W, avail_h,
                caps[0] if caps else "")
    elif n == 2:
        hw = (SAFE_W - 5*mm) / 2
        for i in range(2):
            _insert(chart_paths[i], M+i*(hw+5*mm), avail_y-avail_h, hw, avail_h,
                    caps[i] if i < len(caps) else "")
    else:
        hw = (SAFE_W - 5*mm) / 2
        hh = (avail_h - 5*mm) / 2
        for i in range(min(n, 4)):
            col_ = i % 2; row_ = i // 2
            _insert(chart_paths[i],
                    M + col_*(hw+5*mm),
                    avail_y - row_*(hh+5*mm) - hh,
                    hw, hh, caps[i] if i < len(caps) else "")


def _page_roi(c, d: DesignPayload, pg, total):
    _footer(c, pg, total, d.product_name)
    _rect(c, 0, H - M_TOP - 15*mm, W, M_TOP + 15*mm, fill=C.NAVY_DEEP)
    _chip(c, M, H - M_TOP + 1*mm, "ROI PROJECTION")
    _tx(c, M, H - M_TOP - 8*mm, f"Financial Impact — {d.roi_period}", FONTB, 17, C.WHITE)
    y = H - M_TOP - 28*mm
    rows = d.roi_rows or DEFAULT_ROI
    cols = [SAFE_W*0.38, SAFE_W*0.22, SAFE_W*0.22, SAFE_W*0.18]
    hdrs = ["Metric", "Before", "After", "Delta"]
    _rect(c, M, y-12, SAFE_W, 14, fill=C.NAVY_DEEP)
    hx = M
    for hdr, cw in zip(hdrs, cols):
        _tx(c, hx+4, y-4.5, hdr, FONTB, 8, C.WHITE); hx += cw
    y -= 14; _hline(c, M, y, SAFE_W, C.NAVY_LIGHT, 0.8)
    for ri, row in enumerate(rows[:7]):
        rh = 14
        _rect(c, M, y-rh, SAFE_W, rh, fill=C.GRAY_LIGHT if ri%2==0 else C.WHITE)
        rx = M
        for i, (val, cw) in enumerate(zip([row.label, row.before, row.after, row.delta], cols)):
            col_ = (C.GREEN if row.positive else C.RED_SOFT) if i==3 else C.GRAY_DARK
            _tx(c, rx+4, y-rh+4, val,
                FONTB if i==3 else FONT, 8.5 if i in (0,3) else 8, col_, maxw=cw-8)
            rx += cw
        _hline(c, M, y-rh, SAFE_W, C.GRAY_LINE, 0.3); y -= rh
    y -= 7*mm
    if d.roi_summary:
        qh = 22*mm
        _rect(c, M, y-qh, SAFE_W, qh, fill=C.GREEN_LIGHT, stroke=C.GREEN, radius=5, sw=0.8)
        _tx(c, M+10, y-8*mm, "ROI Summary", FONTB, 9.5, C.GREEN)
        _wrap(c, M+10, y-17*mm, d.roi_summary, FONT, 8.5, C.GRAY_DARK, SAFE_W-20, 1.4)


def _page_roadmap(c, d: DesignPayload, pg, total):
    _footer(c, pg, total, d.product_name)
    _rect(c, 0, H - M_TOP - 15*mm, W, M_TOP + 15*mm, fill=C.NAVY_DEEP)
    _chip(c, M, H - M_TOP + 1*mm, "IMPLEMENTATION")
    _tx(c, M, H - M_TOP - 8*mm, "30-60-90 Day Roadmap", FONTB, 17, C.WHITE)
    y = H - M_TOP - 30*mm
    steps = d.roadmap or DEFAULT_ROADMAP
    step_colors = [C.NAVY_LIGHT, C.TEAL, C.GREEN]
    sw = (SAFE_W - (len(steps)-1)*8*mm) / len(steps)
    # dashed connector
    line_y = y - 35*mm
    for i in range(len(steps)-1):
        lx1 = M + i*(sw+8*mm) + sw
        lx2 = M + (i+1)*(sw+8*mm)
        c.saveState(); c.setStrokeColor(C.GRAY_LINE); c.setLineWidth(1)
        c.setDash(4, 3); c.line(lx1, line_y, lx2, line_y); c.restoreState()
    max_tasks = max(len(s.tasks) for s in steps)
    for i, step in enumerate(steps[:3]):
        sx = M + i*(sw+8*mm); sc = step_colors[i]
        cx_, cy_ = sx+sw/2, y-17*mm
        _rect(c, cx_-16, cy_-16, 32, 32, fill=sc, radius=16)
        _tx(c, cx_, cy_-6, f"0{i+1}", FONTB, 14, C.WHITE, "center")
        _tx(c, cx_, y-44*mm, step.phase,    FONTB, 7.5, sc, "center")
        _tx(c, cx_, y-52*mm, step.label,    FONTB, 10.5, C.GRAY_DARK, "center", sw)
        _tx(c, cx_, y-61*mm, step.duration, FONTI, 8, C.GRAY_MID, "center")
        card_top = y-67*mm
        card_h   = len(step.tasks)*15 + 8
        _rect(c, sx, card_top-card_h, sw, card_h, fill=C.GRAY_LIGHT, stroke=C.GRAY_LINE, radius=4, sw=0.5)
        for j, task in enumerate(step.tasks):
            ty = card_top - 13 - j*15
            c.saveState(); c.setFillColor(sc); c.circle(sx+10, ty+3, 3, fill=1, stroke=0); c.restoreState()
            _tx(c, sx+19, ty, task, FONT, 7.5, C.GRAY_DARK, maxw=sw-26)
    by = y - 67*mm - max_tasks*15 - 18*mm
    _rect(c, M, by-20*mm, SAFE_W, 20*mm, fill=C.NAVY_DEEP, radius=4)
    _tx(c, W/2, by-8*mm, "Expected: Measurable ROI within 30 days of full deployment",
        FONTB, 9.5, C.GOLD, "center")
    _tx(c, W/2, by-15*mm, "Dedicated Customer Success Manager assigned from Day 1",
        FONT, 8, C.GRAY_MID, "center")


def _page_reference(c, d: DesignPayload, pg, total):
    """P8: Global Success Reference — 핵심 신뢰도 페이지."""
    _footer(c, pg, total, d.product_name)
    # 헤더
    _rect(c, 0, H - M_TOP - 18*mm, W, M_TOP + 18*mm, fill=C.NAVY_DEEP)
    _rect(c, M, H - M_TOP - 18*mm, 3, 18*mm, fill=C.GOLD)
    _chip(c, M+10, H - M_TOP + 1*mm, "GLOBAL SUCCESS REFERENCE")
    _tx(c, M+10, H - M_TOP - 10*mm, d.ref_headline, FONTB, 18, C.WHITE)
    _tx(c, W-M, H - M_TOP - 10*mm, f"Industry: {d.industry}", FONTI, 8.5, C.GRAY_MID, "right")

    y = H - M_TOP - 30*mm
    refs = d.references or _default_refs(d.industry)

    # 상단 3개 카드
    top3 = refs[:3]
    card_w = (SAFE_W - 8*mm) / 3
    card_h = 92*mm
    for i, ref in enumerate(top3):
        rx = M + i*(card_w+4*mm)
        ry = y - card_h
        _rect(c, rx, ry, card_w, card_h, fill=C.WHITE, stroke=C.GRAY_LINE, radius=6, sw=0.8)
        sc = [C.NAVY_LIGHT, C.TEAL, C.GREEN][i]
        # 상단 컬러 바 + 로고 배지
        _rect(c, rx, ry+card_h-4, card_w, 4, fill=sc)
        _logo_badge(c, rx+5, ry+card_h-28, card_w-10, 22, ref.initials, ref.company, ref.sector, sc)
        # PoC 제목
        _tx(c, rx+7, ry+card_h-37, ref.poc_title, FONTB, 8.5, C.GRAY_DARK, maxw=card_w-14)
        _hline(c, rx+5, ry+card_h-41, card_w-10, C.GRAY_LINE)
        # 성과 지표
        my = ry+card_h-52
        for j, (metric, val) in enumerate(ref.results[:4]):
            _tx(c, rx+7,          my-j*12, metric, FONT,  7.5, C.GRAY_MID, maxw=card_w*0.55)
            _tx(c, rx+card_w-7,   my-j*12, val,    FONTB, 8.5, sc, "right")
        # 인용구
        if ref.quote:
            qy = ry + 16
            _rect(c, rx+5, qy-2, card_w-10, 15, fill=C.GRAY_LIGHT, radius=3)
            _tx(c, rx+12, qy+5, f'"{ref.quote}"', FONTI, 7, C.GRAY_DARK, maxw=card_w-22)

    y -= card_h + 7*mm

    # 추가 배지 행
    extra = refs[3:6]
    if extra:
        _tx(c, M, y, "Additional Verified Deployments", FONTB, 8.5, C.GRAY_MID)
        y -= 7*mm
        bw = (SAFE_W - (len(extra)-1)*5*mm) / len(extra)
        for i, ref in enumerate(extra):
            _logo_badge(c, M+i*(bw+5*mm), y-19*mm, bw, 19*mm, ref.initials, ref.company, ref.sector)
        y -= 26*mm

    y -= 4*mm

    # 신뢰 지표 바
    _rect(c, M, y-26*mm, SAFE_W, 26*mm, fill=C.NAVY_DEEP, radius=5)
    stats = [("500+","Enterprise\nDeployments"), ("98.7%","Customer\nRetention"),
             ("4.8/5","G2 Rating"),              ("<24h","Avg. Support\nResponse"),
             ("SOC 2","Type II\nCertified")]
    tw = SAFE_W / len(stats)
    for i, (val, lbl) in enumerate(stats):
        tx_ = M + i*tw + tw/2
        _tx(c, tx_, y-9*mm, val, FONTB, 13, C.GOLD, "center")
        for j, line in enumerate(lbl.split("\n")):
            _tx(c, tx_, y-17*mm-j*7, line, FONT, 6.5, C.GRAY_MID, "center")

    # CTA
    _tx(c, W/2, y-34*mm, "Ready to join these success stories?",
        FONTB, 11, C.NAVY_MID, "center")
    _tx(c, W/2, y-43*mm, "Schedule your personalized demo — results guaranteed within 30 days.",
        FONTI, 8.5, C.GRAY_MID, "center")


# ═══════════════════════════════════════════════════════════════════
# DesignerAgent
# ═══════════════════════════════════════════════════════════════════

class DesignerAgent:
    """
    기업용 PDF 제안서 생성기.

    path = DesignerAgent("temp").generate(payload)
    # or
    path = DesignerAgent("temp").quick_generate("OpenerUltra","Acme","John","VP Sales")
    """
    def __init__(self, output_dir: str = "temp"):
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def generate(self, payload: DesignPayload, filename: str = None) -> str:
        if not filename:
            safe = "".join(ch if ch.isalnum() else "_"
                           for ch in payload.buyer_company.lower())[:18]
            filename = f"proposal_{safe}_{int(time.time())%100000}.pdf"
        out = str(self._dir / filename)

        PAGE_RENDERERS = [
            ("cover",     lambda c, pg, tot: _page_cover(c, payload, tot)),
            ("exec",      lambda c, pg, tot: _page_exec(c, payload, pg, tot)),
            ("pain",      lambda c, pg, tot: _page_pain(c, payload, pg, tot)),
            ("solution",  lambda c, pg, tot: _page_solution(c, payload, pg, tot)),
            ("chart",     lambda c, pg, tot: _page_chart(c, payload, pg, tot)),
            ("roi",       lambda c, pg, tot: _page_roi(c, payload, pg, tot)),
            ("roadmap",   lambda c, pg, tot: _page_roadmap(c, payload, pg, tot)),
            ("reference", lambda c, pg, tot: _page_reference(c, payload, pg, tot)),
        ]
        total = len(PAGE_RENDERERS)
        cv = rl_canvas.Canvas(out, pagesize=A4)
        cv.setTitle(f"{payload.product_name} — Proposal for {payload.buyer_company}")
        cv.setAuthor(payload.prepared_by)
        for pg_num, (_, fn) in enumerate(PAGE_RENDERERS, 1):
            fn(cv, pg_num, total)
            cv.showPage()
        cv.save()
        return out

    def quick_generate(self, product_name, buyer_company, buyer_name,
                       buyer_role, chart_paths=None, industry="B2B SaaS") -> str:
        return self.generate(DesignPayload(
            product_name  = product_name,
            buyer_company = buyer_company,
            buyer_name    = buyer_name,
            buyer_role    = buyer_role,
            tagline       = f"AI-Powered Sales Intelligence for {buyer_company}",
            industry      = industry,
            chart_paths   = chart_paths or [],
            chart_captions= ["Competitive Capability Radar", "ROI Impact Analysis",
                             "Feature Comparison", "Adoption Funnel"],
            exec_headline = f"Why {buyer_company} Needs {product_name} Now",
            exec_body     = (
                f"Based on deep research into {buyer_company}'s growth trajectory, "
                f"we've identified a critical gap between sales potential and actual output "
                f"driven by manual research overhead. {product_name} closes that gap in 90 seconds."
            ),
            kpis = [("73%","Research Time Saved","Per account vs. manual"),
                    ("+28%","Win Rate Improvement","Avg. across deployments"),
                    ("90s","Time to Buyer Brief","Down from 3+ hours")],
            roi_summary = (
                f"For a team of 20 AEs, {product_name} delivers ~$180K in annual research "
                f"savings plus $2.4M+ in pipeline acceleration within 12 months."
            ),
        ))
