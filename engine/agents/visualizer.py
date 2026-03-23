"""
opener-ultra-mvp / engine / agents / visualizer.py
====================================================
데이터 시각화 에이전트 — VisualizerAgent

핵심 설계
----------
바이어의 관심사(BuyerFocus)를 입력받아 4가지 차트 타입 중
가장 설득력 있는 시각화를 동적으로 선택·생성합니다.

Chart Types
-----------
  1. RadarChart      — 다차원 역량 비교 (바이어 관심 항목이 축이 됨)
  2. ComparisonBar   — 경쟁사 대비 항목별 수치 비교
  3. ROIWaterfall    — 투자 대비 순이익 누적 흐름
  4. AdoptionFunnel  — 도입 단계별 전환율/시간 시각화

동적 항목 선택 로직
--------------------
  BuyerFocus 카테고리 → 관련 Dimension 매핑 Dict →
  상위 N개 Dimension 선택 → 차트 데이터 생성

출력
----
  PNG 파일을 temp/ 폴더에 저장하고 절대 경로 반환.
  파일명: {chart_type}_{buyer_company}_{timestamp}.png

의존성
------
  pip install matplotlib numpy
"""

from __future__ import annotations

import os
import time
import uuid
import math
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # 헤드리스 렌더링 (서버 환경)
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, Wedge
import numpy as np


# ═══════════════════════════════════════════════════════════════════
# 1. 열거형 & 상수
# ═══════════════════════════════════════════════════════════════════

class ChartType(str, Enum):
    RADAR      = "radar"
    BAR        = "comparison_bar"
    WATERFALL  = "roi_waterfall"
    FUNNEL     = "adoption_funnel"


class BuyerFocus(str, Enum):
    """바이어의 핵심 관심사 카테고리."""
    COST_ROI       = "cost_roi"        # CFO, 구매 담당자
    PERFORMANCE    = "performance"     # CTO, VP Engineering
    EASE_OF_USE    = "ease_of_use"     # 실무 Manager, Sales Rep
    SECURITY       = "security"        # IT Manager, CISO
    SCALABILITY    = "scalability"     # CEO, VP Engineering
    SUPPORT        = "support"         # Operations, IT
    INNOVATION     = "innovation"      # CTO, CPO
    INTEGRATION    = "integration"     # IT Manager, Developer
    SALES_IMPACT   = "sales_impact"    # VP Sales, Sales Manager
    MARKETING_ROI  = "marketing_roi"   # VP Marketing, CMO


# 관심사별 레이더 차트 Dimension 매핑
FOCUS_DIMENSIONS: Dict[BuyerFocus, List[str]] = {
    BuyerFocus.COST_ROI:     ["TCO 절감율", "ROI 속도", "구현 비용", "운영 비용", "계약 유연성"],
    BuyerFocus.PERFORMANCE:  ["처리 속도", "정확도", "가용성(Uptime)", "레이턴시", "처리 용량"],
    BuyerFocus.EASE_OF_USE:  ["온보딩 속도", "UI 직관성", "학습 곡선", "모바일 지원", "자동화 수준"],
    BuyerFocus.SECURITY:     ["데이터 암호화", "접근 제어", "감사 로그", "인증 체계", "컴플라이언스"],
    BuyerFocus.SCALABILITY:  ["수평 확장성", "다국어 지원", "엔터프라이즈 준비도", "API 유연성", "커스텀 설정"],
    BuyerFocus.SUPPORT:      ["응답 시간", "전담 지원", "문서 품질", "커뮤니티", "교육 프로그램"],
    BuyerFocus.INNOVATION:   ["AI 활용도", "기능 출시 빈도", "기술 선도성", "파트너 생태계", "R&D 투자"],
    BuyerFocus.INTEGRATION:  ["API 완성도", "사전 통합 수", "웹훅 지원", "데이터 포맷", "마이그레이션 지원"],
    BuyerFocus.SALES_IMPACT: ["리드 품질", "세일즈 사이클 단축", "Win Rate 개선", "리서치 시간 절감", "파이프라인 가시성"],
    BuyerFocus.MARKETING_ROI:["MQL 전환율", "캠페인 ROI", "어트리뷰션 정확도", "리드 생성량", "브랜드 인지도"],
}

# 디자인 팔레트
PALETTE = {
    "bg":         "#0D0D14",
    "surface":    "#16161F",
    "surface2":   "#1E1E2C",
    "border":     "#2A2A3C",
    "text":       "#E8E6F0",
    "text2":      "#7C7A8E",
    "text3":      "#45434F",
    "accent":     "#7B61FF",
    "accent2":    "#A48FFF",
    "gold":       "#F0B429",
    "green":      "#34D399",
    "red":        "#F87171",
    "teal":       "#22D3EE",
    "product":    "#7B61FF",   # 우리 제품 색상
    "comp1":      "#F87171",   # 경쟁사 A
    "comp2":      "#F0B429",   # 경쟁사 B
    "comp3":      "#7C7A8E",   # 업계 평균
}

# ── matplotlib 글로벌 스타일 세팅 ─────────────────────────────────
def _apply_global_style():
    plt.rcParams.update({
        "figure.facecolor":  PALETTE["bg"],
        "axes.facecolor":    PALETTE["surface"],
        "axes.edgecolor":    PALETTE["border"],
        "axes.labelcolor":   PALETTE["text2"],
        "xtick.color":       PALETTE["text2"],
        "ytick.color":       PALETTE["text2"],
        "text.color":        PALETTE["text"],
        "font.family":       "DejaVu Sans",
        "font.size":         10,
        "grid.color":        PALETTE["border"],
        "grid.alpha":        0.4,
        "figure.dpi":        150,
        "savefig.dpi":       150,
        "savefig.facecolor": PALETTE["bg"],
        "savefig.bbox":      "tight",
        "savefig.pad_inches":0.25,
    })

_apply_global_style()


# ═══════════════════════════════════════════════════════════════════
# 2. 차트 데이터 모델
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CompetitorData:
    name:   str
    color:  str
    scores: Dict[str, float]  # dimension → score (0-100)


@dataclass
class ChartContext:
    """차트 생성에 필요한 모든 컨텍스트."""
    chart_type:      ChartType
    buyer_company:   str
    buyer_focus:     BuyerFocus
    product_name:    str
    dimensions:      List[str]               # 선택된 축/항목

    # 점수 데이터
    product_scores:  Dict[str, float]         # 우리 제품
    competitors:     List[CompetitorData]     # 경쟁사들

    # 부가 정보
    title:           str = ""
    subtitle:        str = ""
    highlight_dim:   Optional[str] = None    # 강조할 차원
    annotations:     Dict[str, str] = field(default_factory=dict)

    # ROI Waterfall 전용
    roi_items:       List[Tuple[str, float]] = field(default_factory=list)
    roi_period_months: int = 12

    # Funnel 전용
    funnel_stages:   List[Tuple[str, float, str]] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# 3. 차트 생성기
# ═══════════════════════════════════════════════════════════════════

class ChartRenderer:
    """4가지 차트 타입을 렌더링하는 핵심 클래스."""

    # ── 1. 레이더 차트 ──────────────────────────────────────────────
    def render_radar(self, ctx: ChartContext, output_path: str) -> str:
        dims = ctx.dimensions
        N    = len(dims)
        angles = [n / float(N) * 2 * math.pi for n in range(N)]
        angles += angles[:1]   # 닫기

        fig = plt.figure(figsize=(11, 8))
        fig.patch.set_facecolor(PALETTE["bg"])

        # 메인 레이더 축
        ax = fig.add_subplot(111, polar=True)
        ax.set_facecolor(PALETTE["surface"])
        ax.set_theta_offset(math.pi / 2)
        ax.set_theta_direction(-1)

        # 그리드 라인 스타일
        ax.set_rlabel_position(30)
        plt.xticks(angles[:-1], dims, color=PALETTE["text2"], size=9, fontweight="500")
        ax.set_ylim(0, 100)
        ax.set_yticks([20, 40, 60, 80, 100])
        ax.set_yticklabels(["20", "40", "60", "80", "100"],
                           color=PALETTE["text3"], size=7)
        ax.tick_params(axis='x', pad=14)

        # 그리드 원형 스타일링
        for spine in ax.spines.values():
            spine.set_edgecolor(PALETTE["border"])
        ax.grid(color=PALETTE["border"], linewidth=0.8, alpha=0.5)

        # 동심원 채우기 (배경 zone)
        for r, alpha in [(100, 0.04), (60, 0.06)]:
            vals = [r] * N + [r]
            ax.fill(angles, vals, alpha=alpha, color=PALETTE["accent"])

        # ── 경쟁사 데이터 먼저 (뒤에 그리기)
        for comp in ctx.competitors:
            vals = [comp.scores.get(d, 50) for d in dims] + [comp.scores.get(dims[0], 50)]
            ax.plot(angles, vals, linewidth=1.2, linestyle="--",
                    color=comp.color, alpha=0.6, label=comp.name)
            ax.fill(angles, vals, alpha=0.05, color=comp.color)

        # ── 우리 제품 (앞에 그리기)
        prod_vals = [ctx.product_scores.get(d, 50) for d in dims]
        prod_vals_closed = prod_vals + prod_vals[:1]
        ax.plot(angles, prod_vals_closed, linewidth=2.5, linestyle="-",
                color=PALETTE["accent"], label=ctx.product_name)
        ax.fill(angles, prod_vals_closed, alpha=0.18, color=PALETTE["accent"])

        # 데이터 포인트 마커
        ax.scatter(angles[:-1], prod_vals, s=60, color=PALETTE["accent"],
                   zorder=5, edgecolors=PALETTE["bg"], linewidths=1.5)

        # 최고점 강조 어노테이션
        best_dim_idx = np.argmax(prod_vals)
        best_angle   = angles[best_dim_idx]
        best_val     = prod_vals[best_dim_idx]
        ax.annotate(
            f"  {best_val:.0f}",
            xy=(best_angle, best_val),
            fontsize=8, fontweight="700",
            color=PALETTE["accent2"],
            ha="center",
        )

        # 타이틀 & 서브타이틀
        fig.text(0.5, 0.96, ctx.title or f"{ctx.product_name} 역량 레이더",
                 ha="center", va="top", fontsize=16, fontweight="700",
                 color=PALETTE["text"])
        fig.text(0.5, 0.92, ctx.subtitle or f"{ctx.buyer_company} 맞춤 분석",
                 ha="center", va="top", fontsize=10, color=PALETTE["text2"])

        # 범례
        legend = ax.legend(
            loc="lower center", bbox_to_anchor=(0.5, -0.22),
            ncol=len(ctx.competitors) + 1,
            frameon=True,
            facecolor=PALETTE["surface2"],
            edgecolor=PALETTE["border"],
            labelcolor=PALETTE["text"],
            fontsize=9,
        )

        # 점수 요약 박스 (우측 하단)
        avg_score = np.mean(prod_vals)
        self._draw_score_box(fig, avg_score, ctx.product_name,
                             pos=(0.87, 0.15), w=0.11, h=0.14)

        plt.tight_layout(rect=[0, 0.05, 1, 0.90])
        plt.savefig(output_path)
        plt.close(fig)
        return output_path

    # ── 2. 비교 바 차트 ─────────────────────────────────────────────
    def render_comparison_bar(self, ctx: ChartContext, output_path: str) -> str:
        dims  = ctx.dimensions
        N     = len(dims)
        ncomp = len(ctx.competitors) + 1   # 우리 + 경쟁사들

        fig, ax = plt.subplots(figsize=(13, 7))
        fig.patch.set_facecolor(PALETTE["bg"])
        ax.set_facecolor(PALETTE["surface"])

        x         = np.arange(N)
        bar_width = 0.75 / ncomp
        offsets   = np.linspace(-(ncomp-1)/2 * bar_width,
                                 (ncomp-1)/2 * bar_width, ncomp)

        # 경쟁사 바
        for i, comp in enumerate(ctx.competitors):
            scores = [comp.scores.get(d, 50) for d in dims]
            bars = ax.bar(x + offsets[i], scores, bar_width * 0.88,
                          color=comp.color, alpha=0.65, label=comp.name,
                          zorder=3)
            for bar, score in zip(bars, scores):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
                        f"{score:.0f}", ha="center", va="bottom",
                        fontsize=7.5, color=comp.color, fontweight="600")

        # 우리 제품 바 (마지막, 가장 도드라지게)
        prod_scores = [ctx.product_scores.get(d, 50) for d in dims]
        bars = ax.bar(x + offsets[-1], prod_scores, bar_width * 0.88,
                      color=PALETTE["accent"], alpha=0.95,
                      label=ctx.product_name, zorder=4,
                      linewidth=0, edgecolor=PALETTE["accent2"])

        # 우리 제품 점수 라벨 + 글로우 효과
        for bar, score in zip(bars, prod_scores):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                    f"{score:.0f}", ha="center", va="bottom",
                    fontsize=9, color=PALETTE["accent2"], fontweight="800",
                    path_effects=[pe.withStroke(linewidth=2,
                                                foreground=PALETTE["bg"])])

        # 우리 제품 바에 상단 하이라이트 선
        for bar in bars:
            ax.plot([bar.get_x(), bar.get_x() + bar.get_width()],
                    [bar.get_height(), bar.get_height()],
                    color=PALETTE["accent2"], linewidth=2.5, solid_capstyle="round")

        # 우리 제품이 1위인 차원 강조 (배경 음영)
        for i, d in enumerate(dims):
            all_scores = [ctx.product_scores.get(d, 0)] + \
                         [c.scores.get(d, 0) for c in ctx.competitors]
            if ctx.product_scores.get(d, 0) == max(all_scores):
                ax.axvspan(i - 0.45, i + 0.45, alpha=0.07,
                           color=PALETTE["accent"], zorder=1)
                ax.text(i, 102, "★", ha="center", va="bottom",
                        fontsize=9, color=PALETTE["gold"])

        # 축 스타일링
        ax.set_xlim(-0.6, N - 0.4)
        ax.set_ylim(0, 115)
        ax.set_xticks(x)
        ax.set_xticklabels(
            [textwrap.fill(d, 10) for d in dims],
            fontsize=9, color=PALETTE["text"], fontweight="500"
        )
        ax.set_ylabel("점수 (100점 기준)", color=PALETTE["text2"], fontsize=9)
        ax.tick_params(axis="y", colors=PALETTE["text3"])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(PALETTE["border"])
        ax.spines["bottom"].set_color(PALETTE["border"])
        ax.yaxis.grid(True, color=PALETTE["border"], alpha=0.4, linewidth=0.8)
        ax.set_axisbelow(True)

        # 100점 기준선
        ax.axhline(y=100, color=PALETTE["border"], linewidth=1, alpha=0.6, linestyle="--")

        # 타이틀
        fig.text(0.5, 0.97, ctx.title or f"경쟁사 대비 항목별 비교",
                 ha="center", fontsize=15, fontweight="700", color=PALETTE["text"])
        fig.text(0.5, 0.93, ctx.subtitle or f"★ = {ctx.product_name} 1위 항목",
                 ha="center", fontsize=9, color=PALETTE["text2"])

        # 범례
        legend = ax.legend(
            loc="upper right", frameon=True,
            facecolor=PALETTE["surface2"], edgecolor=PALETTE["border"],
            labelcolor=PALETTE["text"], fontsize=9,
        )

        # 평균 점수 박스
        avg = np.mean(prod_scores)
        self._draw_score_box(fig, avg, ctx.product_name, pos=(0.02, 0.02), w=0.13, h=0.16)

        plt.tight_layout(rect=[0, 0, 1, 0.90])
        plt.savefig(output_path)
        plt.close(fig)
        return output_path

    # ── 3. ROI 워터폴 차트 ─────────────────────────────────────────
    def render_roi_waterfall(self, ctx: ChartContext, output_path: str) -> str:
        items  = ctx.roi_items   # [(레이블, 값), ...]
        if not items:
            items = [
                ("초기 구축 비용", -800),
                ("리서치 비용 절감", 1200),
                ("세일즈 사이클 단축", 900),
                ("Win Rate 향상", 1500),
                ("운영 효율화", 600),
                ("추가 매출", 2200),
            ]

        labels = [i[0] for i in items]
        values = [i[1] for i in items]
        N      = len(items)

        fig, ax = plt.subplots(figsize=(13, 7))
        fig.patch.set_facecolor(PALETTE["bg"])
        ax.set_facecolor(PALETTE["surface"])

        # 누적 계산
        running = 0
        bottoms = []
        for v in values:
            bottoms.append(running if v > 0 else running + v)
            running += v

        totals = []
        cum = 0
        for v in values:
            cum += v
            totals.append(cum)

        # 바 색상 결정
        bar_colors = []
        for v in values:
            if v > 0:
                bar_colors.append(PALETTE["green"])
            else:
                bar_colors.append(PALETTE["red"])

        # 연결선 (cascade 효과)
        cum_val = 0
        for i in range(N - 1):
            cum_val += values[i]
            ax.plot([i + 0.4, i + 0.6], [cum_val, cum_val],
                    color=PALETTE["border"], linewidth=1.2, zorder=5)

        # 바 그리기
        bars = ax.bar(range(N), [abs(v) for v in values], bottom=bottoms,
                      width=0.75, color=bar_colors, alpha=0.85,
                      edgecolor=PALETTE["bg"], linewidth=0.8, zorder=4)

        # 우측 그라데이션 효과 (마지막 바 하이라이트)
        last_bar = bars[-1]
        last_bar.set_facecolor(PALETTE["accent"])
        last_bar.set_alpha(0.95)

        # 바 상단 라벨
        cum_running = 0
        for i, (bar, v) in enumerate(zip(bars, values)):
            cum_running += v
            color = PALETTE["green"] if v > 0 else PALETTE["red"]
            sign  = "+" if v > 0 else ""
            ax.text(i, bar.get_y() + bar.get_height() + max(abs(v)*0.03, 30),
                    f"{sign}{v:,.0f}만", ha="center", va="bottom",
                    fontsize=8.5, color=color, fontweight="700",
                    path_effects=[pe.withStroke(linewidth=2, foreground=PALETTE["bg"])])

            # 누적 합계 라벨 (작게)
            ax.text(i, bar.get_y() - max(abs(v)*0.05, 60),
                    f"누계: {cum_running:+,.0f}",
                    ha="center", va="top", fontsize=7,
                    color=PALETTE["text3"])

        # 기준선 (0원)
        ax.axhline(y=0, color=PALETTE["border"], linewidth=1.2, zorder=3)

        # 최종 순이익 주석
        final_total = sum(values)
        ax.annotate(
            f"순이익 {final_total:+,.0f}만",
            xy=(N - 1, sum(bottoms[-1:]) + abs(values[-1])),
            xytext=(N - 2.2, sum(bottoms[-1:]) + abs(values[-1]) + 300),
            fontsize=10, fontweight="800",
            color=PALETTE["accent2"],
            arrowprops=dict(arrowstyle="->", color=PALETTE["accent"],
                            lw=1.5, connectionstyle="arc3,rad=0.2"),
        )

        # ROI 배수 박스
        initial_cost = abs(min(v for v in values if v < 0) or 1)
        roi_mult     = final_total / initial_cost if initial_cost else 0
        ax.text(0.01, 0.98, f"ROI {roi_mult:.1f}×",
                transform=ax.transAxes,
                fontsize=20, fontweight="900", color=PALETTE["gold"],
                va="top",
                path_effects=[pe.withStroke(linewidth=3, foreground=PALETTE["bg"])])
        ax.text(0.01, 0.89, f"{ctx.roi_period_months}개월 기준",
                transform=ax.transAxes, fontsize=9, color=PALETTE["text2"], va="top")

        # 축 스타일
        ax.set_xticks(range(N))
        ax.set_xticklabels([textwrap.fill(l, 8) for l in labels],
                           fontsize=9, color=PALETTE["text"])
        ax.set_ylabel("금액 (만원)", color=PALETTE["text2"], fontsize=9)
        ax.tick_params(axis="y", colors=PALETTE["text3"])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(PALETTE["border"])
        ax.spines["bottom"].set_color(PALETTE["border"])
        ax.yaxis.grid(True, color=PALETTE["border"], alpha=0.4, linewidth=0.7)
        ax.set_axisbelow(True)

        fig.text(0.5, 0.97, ctx.title or f"{ctx.product_name} 도입 ROI 분석",
                 ha="center", fontsize=15, fontweight="700", color=PALETTE["text"])
        fig.text(0.5, 0.93, ctx.subtitle or f"{ctx.buyer_company} 예상 {ctx.roi_period_months}개월 누적 수익",
                 ha="center", fontsize=9, color=PALETTE["text2"])

        plt.tight_layout(rect=[0, 0, 1, 0.90])
        plt.savefig(output_path)
        plt.close(fig)
        return output_path

    # ── 4. 도입 퍼널 차트 ──────────────────────────────────────────
    def render_adoption_funnel(self, ctx: ChartContext, output_path: str) -> str:
        stages = ctx.funnel_stages  # [(이름, 값%, 시간레이블), ...]
        if not stages:
            stages = [
                ("리드 발굴", 100, "Day 1"),
                ("리서치 완료", 85, "Day 2"),
                ("첫 미팅", 62, "Day 5"),
                ("데모 진행", 48, "Day 10"),
                ("제안서 발송", 35, "Day 15"),
                ("계약 성사", 22, "Day 30"),
            ]

        fig, (ax_funnel, ax_time) = plt.subplots(
            1, 2, figsize=(14, 8),
            gridspec_kw={"width_ratios": [2, 1]}
        )
        fig.patch.set_facecolor(PALETTE["bg"])

        # ── 퍼널 (좌측) ──
        ax_funnel.set_facecolor(PALETTE["surface"])
        N        = len(stages)
        max_w    = 1.0
        colors   = plt.cm.get_cmap("cool")(np.linspace(0.4, 0.9, N))

        y_positions = np.linspace(0, 1, N + 1)
        for i, (name, val, time_label) in enumerate(stages):
            width = max_w * (val / 100)
            y_top = y_positions[N - i]
            y_bot = y_positions[N - i - 1]
            h     = y_top - y_bot

            color = PALETTE["accent"] if i == 0 else (
                PALETTE["green"] if i == N - 1 else f"#{int(123-i*10):02x}{int(97+i*8):02x}{int(255-i*20):02x}"
            )

            # 사다리꼴 패치
            xs = [-(width/2), width/2, width/2 * 0.85, -(width/2 * 0.85)]
            ys = [y_top, y_top, y_bot, y_bot]
            ax_funnel.fill(xs, ys, color=color, alpha=0.8, zorder=3)
            ax_funnel.plot(xs + [xs[0]], ys + [ys[0]],
                           color=PALETTE["bg"], linewidth=1.5, zorder=4)

            # 단계 이름
            ax_funnel.text(0, (y_top + y_bot) / 2, f"{name}",
                           ha="center", va="center", fontsize=9.5,
                           fontweight="700", color="white", zorder=5,
                           path_effects=[pe.withStroke(linewidth=2,
                                                        foreground=PALETTE["bg"])])

            # 퍼센트 (우측)
            ax_funnel.text(width / 2 + 0.04, (y_top + y_bot) / 2,
                           f"{val}%",
                           ha="left", va="center", fontsize=10,
                           fontweight="800", color=color, zorder=5)

            # 전환율 표시 (단계 간)
            if i > 0:
                prev_val = stages[i-1][1]
                conv = val / prev_val * 100
                ax_funnel.text(-width/2 - 0.04, (y_top + y_bot) / 2,
                               f"↓{conv:.0f}%",
                               ha="right", va="center", fontsize=8,
                               color=PALETTE["text3"])

        ax_funnel.set_xlim(-0.7, 0.85)
        ax_funnel.set_ylim(-0.05, 1.1)
        ax_funnel.axis("off")
        ax_funnel.set_title("세일즈 퍼널 전환율", pad=14,
                             color=PALETTE["text"], fontsize=12, fontweight="700")

        # ── 타임라인 (우측) ──
        ax_time.set_facecolor(PALETTE["surface"])
        times     = [s[2] for s in stages]
        vals_pct  = [s[1] for s in stages]
        y_pos_t   = range(N)

        # 가로 바 (시간 기반)
        day_numbers = []
        for t in times:
            try:
                day_numbers.append(int(t.replace("Day ", "")))
            except ValueError:
                day_numbers.append(0)

        max_day = max(day_numbers) or 1
        for i, (day, val_p, (name, _, _)) in enumerate(
                zip(day_numbers, vals_pct, stages)):
            bar_len = day / max_day * 0.85
            color   = PALETTE["accent"] if i == 0 else (
                PALETTE["green"] if i == N-1 else PALETTE["text3"]
            )
            ax_time.barh(N - 1 - i, bar_len, height=0.55,
                         color=color, alpha=0.75, zorder=3)
            ax_time.text(bar_len + 0.02, N - 1 - i, times[i],
                         va="center", fontsize=8.5, color=color, fontweight="600")

        ax_time.set_xlim(0, 1.15)
        ax_time.set_yticks(range(N))
        ax_time.set_yticklabels([s[0] for s in reversed(stages)],
                                 fontsize=8.5, color=PALETTE["text2"])
        ax_time.set_xlabel("소요 기간 (상대값)", color=PALETTE["text2"], fontsize=8)
        ax_time.tick_params(axis="x", colors=PALETTE["text3"])
        ax_time.spines["top"].set_visible(False)
        ax_time.spines["right"].set_visible(False)
        ax_time.spines["left"].set_color(PALETTE["border"])
        ax_time.spines["bottom"].set_color(PALETTE["border"])
        ax_time.xaxis.grid(True, color=PALETTE["border"], alpha=0.4, linewidth=0.7)
        ax_time.set_axisbelow(True)
        ax_time.set_title("단계별 소요 기간", pad=14,
                           color=PALETTE["text"], fontsize=12, fontweight="700")

        # 전체 타이틀
        fig.text(0.5, 0.97, ctx.title or f"{ctx.product_name} 세일즈 전환 분석",
                 ha="center", fontsize=15, fontweight="700", color=PALETTE["text"])
        fig.text(0.5, 0.93, ctx.subtitle or f"{ctx.buyer_company} 예상 파이프라인",
                 ha="center", fontsize=9, color=PALETTE["text2"])

        plt.tight_layout(rect=[0, 0, 1, 0.91])
        plt.savefig(output_path)
        plt.close(fig)
        return output_path

    # ── 공통 헬퍼: 점수 요약 박스 ─────────────────────────────────
    def _draw_score_box(self, fig, avg_score: float, product_name: str,
                        pos: Tuple[float, float], w: float, h: float):
        ax_box = fig.add_axes([pos[0], pos[1], w, h])
        ax_box.set_facecolor(PALETTE["surface2"])
        ax_box.set_xlim(0, 1)
        ax_box.set_ylim(0, 1)
        ax_box.axis("off")
        for spine in ax_box.spines.values():
            spine.set_edgecolor(PALETTE["border"])
            spine.set_linewidth(0.8)
            spine.set_visible(True)

        ax_box.text(0.5, 0.72, f"{avg_score:.0f}", ha="center", va="center",
                    fontsize=22, fontweight="900", color=PALETTE["accent2"])
        ax_box.text(0.5, 0.38, "평균 점수", ha="center", va="center",
                    fontsize=7.5, color=PALETTE["text2"])
        ax_box.text(0.5, 0.14, product_name[:12], ha="center", va="center",
                    fontsize=6.5, color=PALETTE["text3"])


# ═══════════════════════════════════════════════════════════════════
# 4. 컨텍스트 빌더 — 바이어 관심사 → 차트 데이터 자동 생성
# ═══════════════════════════════════════════════════════════════════

# 우리 제품 기본 점수 프로파일 (항목별 강점)
PRODUCT_BASE_SCORES: Dict[str, float] = {
    # 공통 강점
    "온보딩 속도": 94, "UI 직관성": 91, "자동화 수준": 96,
    "AI 활용도": 97, "기능 출시 빈도": 88,
    "API 완성도": 89, "사전 통합 수": 82,
    # 세일즈 특화
    "리서치 시간 절감": 96, "세일즈 사이클 단축": 88,
    "Win Rate 개선": 85, "리드 품질": 87, "파이프라인 가시성": 84,
    # 비용
    "TCO 절감율": 82, "ROI 속도": 90, "구현 비용": 78, "운영 비용": 85,
    "계약 유연성": 88,
    # 기술
    "처리 속도": 88, "정확도": 92, "가용성(Uptime)": 99,
    "레이턴시": 86, "처리 용량": 84,
    # 보안
    "데이터 암호화": 95, "접근 제어": 92, "감사 로그": 90,
    "인증 체계": 93, "컴플라이언스": 88,
    # 지원
    "응답 시간": 91, "전담 지원": 86, "문서 품질": 88,
    "커뮤니티": 75, "교육 프로그램": 83,
    # 확장성
    "수평 확장성": 87, "다국어 지원": 84,
    "엔터프라이즈 준비도": 85, "API 유연성": 90, "커스텀 설정": 88,
    # 마케팅
    "MQL 전환율": 86, "캠페인 ROI": 83, "어트리뷰션 정확도": 89,
    "리드 생성량": 84, "브랜드 인지도": 72,
    "학습 곡선": 90, "모바일 지원": 85,
    "웹훅 지원": 87, "데이터 포맷": 88, "마이그레이션 지원": 82,
    "기술 선도성": 91, "파트너 생태계": 78, "R&D 투자": 85,
}

# 경쟁사 점수 오프셋 (우리 대비 -5 ~ -20 범위)
COMPETITOR_OFFSETS = {
    "Competitor A": -8,
    "Competitor B": -14,
    "Industry Avg": -22,
}


def _generate_scores(product_scores: Dict[str, float],
                     dims: List[str],
                     offset: float) -> Dict[str, float]:
    """경쟁사 점수 = 제품 점수 + offset + 소량의 랜덤 변동."""
    rng = np.random.default_rng(abs(int(offset * 100)))
    result = {}
    for d in dims:
        base  = product_scores.get(d, 70)
        noise = rng.uniform(-5, 5)
        result[d] = float(np.clip(base + offset + noise, 20, 98))
    return result


class ContextBuilder:
    """BuyerFocus + 사용자 입력 → ChartContext 자동 빌드."""

    def build(
        self,
        chart_type:      ChartType,
        buyer_company:   str,
        buyer_focus:     BuyerFocus,
        product_name:    str,
        n_dimensions:    int = 6,
        custom_dims:     Optional[List[str]] = None,
        competitors:     Optional[List[str]] = None,
        custom_scores:   Optional[Dict[str, float]] = None,
        roi_items:       Optional[List[Tuple[str, float]]] = None,
        funnel_stages:   Optional[List[Tuple[str, float, str]]] = None,
        title:           str = "",
        subtitle:        str = "",
    ) -> ChartContext:

        # 차원 선택
        dims = custom_dims or FOCUS_DIMENSIONS.get(buyer_focus, [])[:n_dimensions]
        if not dims:
            dims = ["성능", "가격", "지원", "통합", "보안", "확장성"]

        # 제품 점수
        prod_scores = {
            d: (custom_scores or PRODUCT_BASE_SCORES).get(d, 80.0)
            for d in dims
        }

        # 경쟁사 데이터
        comp_names  = competitors or ["Competitor A", "Competitor B", "Industry Avg"]
        comp_colors = [PALETTE["red"], PALETTE["gold"], PALETTE["text3"]]
        comp_data   = [
            CompetitorData(
                name=n,
                color=comp_colors[i % len(comp_colors)],
                scores=_generate_scores(
                    prod_scores, dims,
                    COMPETITOR_OFFSETS.get(n, -10 - i * 5)
                ),
            )
            for i, n in enumerate(comp_names[:3])
        ]

        return ChartContext(
            chart_type=chart_type,
            buyer_company=buyer_company,
            buyer_focus=buyer_focus,
            product_name=product_name,
            dimensions=dims,
            product_scores=prod_scores,
            competitors=comp_data,
            title=title,
            subtitle=subtitle,
            roi_items=roi_items or [],
            funnel_stages=funnel_stages or [],
        )


# ═══════════════════════════════════════════════════════════════════
# 5. VisualizerAgent 메인 클래스
# ═══════════════════════════════════════════════════════════════════

class VisualizerAgent:
    """
    바이어 관심사 기반 동적 데이터 시각화 에이전트.

    사용법
    ------
    agent = VisualizerAgent(temp_dir="temp")

    # 레이더 차트
    path = agent.generate(
        chart_type     = ChartType.RADAR,
        buyer_company  = "Acme Corp",
        buyer_focus    = BuyerFocus.SALES_IMPACT,
        product_name   = "OpenerUltra",
    )

    # 맞춤 비교 바 차트
    path = agent.generate(
        chart_type    = ChartType.BAR,
        buyer_company = "Kakao",
        buyer_focus   = BuyerFocus.COST_ROI,
        product_name  = "OpenerUltra",
        n_dimensions  = 5,
        competitors   = ["Salesforce", "HubSpot"],
    )
    """

    def __init__(self, temp_dir: str = "temp"):
        self._temp_dir = Path(temp_dir)
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._renderer = ChartRenderer()
        self._builder  = ContextBuilder()

    def generate(
        self,
        chart_type:    ChartType,
        buyer_company: str,
        buyer_focus:   BuyerFocus,
        product_name:  str,
        n_dimensions:  int = 6,
        custom_dims:   Optional[List[str]] = None,
        competitors:   Optional[List[str]] = None,
        custom_scores: Optional[Dict[str, float]] = None,
        roi_items:     Optional[List[Tuple[str, float]]] = None,
        funnel_stages: Optional[List[Tuple[str, float, str]]] = None,
        title:         str = "",
        subtitle:      str = "",
    ) -> str:
        """
        차트를 생성하고 PNG 파일 경로를 반환합니다.

        Returns:
            str — 생성된 PNG 파일의 절대 경로
        """
        ctx = self._builder.build(
            chart_type=chart_type,
            buyer_company=buyer_company,
            buyer_focus=buyer_focus,
            product_name=product_name,
            n_dimensions=n_dimensions,
            custom_dims=custom_dims,
            competitors=competitors,
            custom_scores=custom_scores,
            roi_items=roi_items,
            funnel_stages=funnel_stages,
            title=title,
            subtitle=subtitle,
        )

        filename = self._make_filename(chart_type, buyer_company)
        output_path = str(self._temp_dir / filename)

        RENDER_MAP = {
            ChartType.RADAR:     self._renderer.render_radar,
            ChartType.BAR:       self._renderer.render_comparison_bar,
            ChartType.WATERFALL: self._renderer.render_roi_waterfall,
            ChartType.FUNNEL:    self._renderer.render_adoption_funnel,
        }
        renderer_fn = RENDER_MAP.get(chart_type, self._renderer.render_radar)
        renderer_fn(ctx, output_path)

        return output_path

    def generate_all(
        self,
        buyer_company: str,
        buyer_focus:   BuyerFocus,
        product_name:  str,
        **kwargs,
    ) -> Dict[str, str]:
        """4가지 차트를 모두 생성하고 {chart_type: path} 딕셔너리를 반환합니다."""
        results = {}
        for ct in ChartType:
            try:
                path = self.generate(
                    chart_type=ct,
                    buyer_company=buyer_company,
                    buyer_focus=buyer_focus,
                    product_name=product_name,
                    **kwargs,
                )
                results[ct.value] = path
            except Exception as e:
                results[ct.value] = f"ERROR: {str(e)}"
        return results

    def auto_select_chart(self, buyer_focus: BuyerFocus) -> ChartType:
        """바이어 관심사에 따라 가장 설득력 있는 차트 타입을 자동 선택합니다."""
        mapping = {
            BuyerFocus.COST_ROI:       ChartType.WATERFALL,
            BuyerFocus.PERFORMANCE:    ChartType.BAR,
            BuyerFocus.EASE_OF_USE:    ChartType.FUNNEL,
            BuyerFocus.SECURITY:       ChartType.RADAR,
            BuyerFocus.SCALABILITY:    ChartType.RADAR,
            BuyerFocus.SUPPORT:        ChartType.BAR,
            BuyerFocus.INNOVATION:     ChartType.RADAR,
            BuyerFocus.INTEGRATION:    ChartType.BAR,
            BuyerFocus.SALES_IMPACT:   ChartType.FUNNEL,
            BuyerFocus.MARKETING_ROI:  ChartType.WATERFALL,
        }
        return mapping.get(buyer_focus, ChartType.RADAR)

    # ── 내부 헬퍼 ─────────────────────────────────────────────────

    def _make_filename(self, chart_type: ChartType, buyer_company: str) -> str:
        safe_company = re.sub(r"[^\w]", "_", buyer_company.lower())[:20]
        ts = int(time.time() * 1000) % 100000
        return f"{chart_type.value}_{safe_company}_{ts}.png"


# ── 정규표현식 임포트 (파일명 생성 등에서 사용) ─────────────────────
import re
