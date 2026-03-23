"""
opener-ultra-mvp / engine / agents / researcher.py
====================================================
Tavily Deep Search 기반 바이어 리서처

설계 철학
----------
단순 키워드 검색이 아닌 '정보 계층 드릴다운(Signal Cascade)':

  Round 1 — 기업 홈페이지 + 공식 채널 (About, News, IR)
  Round 2 — 최근 6개월 미디어 (뉴스, 보도자료, 언론 인터뷰)
  Round 3 — 업계 컨텍스트 (경쟁사 동향, 시장 리포트)
  Round 4 — 소셜/커뮤니티 시그널 (Reddit, LinkedIn, Twitter 언급)

각 Round 결과를 분석해 PainSignal → ConnectionBridge를 생성합니다.
ConnectionBridge = 바이어의 상황 + 우리 제품 기능의 연결 논거.

의존성
------
  pip install tavily-python httpx tenacity

환경변수
--------
  TAVILY_API_KEY  — Tavily API 키 (필수)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


# ─────────────────────────────────────────────────────────────────────
# 1. 데이터 모델
# ─────────────────────────────────────────────────────────────────────

class SignalCategory(str, Enum):
    GROWTH          = "growth"          # 신규 투자, 확장 계획
    CRISIS          = "crisis"          # 위기, 규제, 소송, 이슈
    STRATEGY_SHIFT  = "strategy_shift"  # 전략 전환, 피벗
    HIRING          = "hiring"          # 대규모 채용 (수요 신호)
    TECH_ADOPTION   = "tech_adoption"   # 신기술 도입 의지
    COMPETITIVE     = "competitive"     # 경쟁 심화 압박
    LEADERSHIP      = "leadership"      # 경영진 교체, 구조 변화
    FINANCIAL       = "financial"       # 실적 발표, 재무 이슈
    PARTNERSHIP     = "partnership"     # 파트너십, M&A
    REGULATORY      = "regulatory"      # 규제, 컴플라이언스


@dataclass
class RawSearchResult:
    """Tavily 검색 결과 하나."""
    result_id:   str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    title:       str = ""
    url:         str = ""
    content:     str = ""
    score:       float = 0.0
    published:   Optional[str] = None
    source_type: str = "web"          # web | news | ir | social


@dataclass
class PainSignal:
    """바이어의 상황에서 추출된 페인/기회 신호."""
    signal_id:   str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    category:    SignalCategory = SignalCategory.GROWTH
    headline:    str = ""              # 한 줄 요약
    detail:      str = ""              # 상세 설명
    evidence:    str = ""              # 원문 발췌
    source_url:  str = ""
    published:   Optional[str] = None
    urgency:     float = 0.5          # 0.0 – 1.0 (세일즈 타이밍 급박도)
    confidence:  float = 0.5


@dataclass
class ConnectionBridge:
    """
    바이어 상황(PainSignal) + 제품 기능의 연결 논거.
    세일즈 미팅 오프닝 멘트, 이메일 훅, 제안서 도입부로 바로 사용 가능.
    """
    bridge_id:       str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    pain_signal_id:  str = ""
    buyer_situation: str = ""          # 바이어가 처한 상황 (1-2문장)
    product_hook:    str = ""          # 제품 기능과의 연결 논거
    opening_line:    str = ""          # 콜드 이메일/콜 오프닝 한 줄
    talk_track:      str = ""          # 세일즈 토크트랙 (2-3문장)
    relevance_score: float = 0.0      # 연결 강도 0.0 – 1.0
    category:        SignalCategory = SignalCategory.GROWTH


@dataclass
class ResearchReport:
    """전체 리서치 결과물."""
    report_id:       str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    company_name:    str = ""
    company_domain:  str = ""
    researched_at:   float = field(default_factory=time.time)
    raw_results:     List[RawSearchResult] = field(default_factory=list)
    pain_signals:    List[PainSignal]      = field(default_factory=list)
    bridges:         List[ConnectionBridge] = field(default_factory=list)
    exec_summary:    str = ""
    top_hooks:       List[str] = field(default_factory=list)  # 즉시 사용 가능한 오프닝 3선

    def to_dict(self) -> dict:
        return {
            "report_id":    self.report_id,
            "company_name": self.company_name,
            "researched_at":self.researched_at,
            "signal_count": len(self.pain_signals),
            "bridge_count": len(self.bridges),
            "exec_summary": self.exec_summary,
            "top_hooks":    self.top_hooks,
            "pain_signals": [
                {
                    "category": s.category.value,
                    "headline": s.headline,
                    "detail":   s.detail,
                    "urgency":  s.urgency,
                    "confidence": s.confidence,
                    "source_url": s.source_url,
                }
                for s in self.pain_signals
            ],
            "bridges": [
                {
                    "buyer_situation": b.buyer_situation,
                    "product_hook":    b.product_hook,
                    "opening_line":    b.opening_line,
                    "talk_track":      b.talk_track,
                    "relevance_score": b.relevance_score,
                    "category":        b.category.value,
                }
                for b in self.bridges
            ],
        }


# ─────────────────────────────────────────────────────────────────────
# 2. Tavily 클라이언트 래퍼
# ─────────────────────────────────────────────────────────────────────

class TavilyClient:
    """
    Tavily Search API 비동기 래퍼.
    - search()      : 일반 검색 (topic=general)
    - news_search() : 뉴스 한정 (topic=news, recent_days=180)
    - deep_search() : topic=general + search_depth=advanced (더 많은 결과)
    """

    BASE_URL = "https://api.tavily.com"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "TAVILY_API_KEY 환경변수가 설정되지 않았습니다. "
                "https://tavily.com 에서 API 키를 발급받으세요."
            )
        self._client = httpx.AsyncClient(timeout=30.0)

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def _post(self, endpoint: str, payload: dict) -> dict:
        payload["api_key"] = self.api_key
        resp = await self._client.post(f"{self.BASE_URL}{endpoint}", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def search(
        self,
        query: str,
        max_results: int = 5,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
    ) -> List[RawSearchResult]:
        payload = {
            "query":        query,
            "max_results":  max_results,
            "search_depth": "basic",
            "topic":        "general",
            "include_answer": False,
        }
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains

        data = await self._post("/search", payload)
        return self._parse(data, "web")

    async def news_search(
        self,
        query: str,
        max_results: int = 7,
        days: int = 180,
    ) -> List[RawSearchResult]:
        """최근 N일 뉴스 전용 검색."""
        payload = {
            "query":        query,
            "max_results":  max_results,
            "search_depth": "basic",
            "topic":        "news",
            "days":         days,
            "include_answer": False,
        }
        data = await self._post("/search", payload)
        return self._parse(data, "news")

    async def deep_search(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[RawSearchResult]:
        """고비용이지만 고품질의 advanced 검색."""
        payload = {
            "query":        query,
            "max_results":  max_results,
            "search_depth": "advanced",
            "topic":        "general",
            "include_answer": True,
            "include_raw_content": False,
        }
        data = await self._post("/search", payload)
        return self._parse(data, "web")

    @staticmethod
    def _parse(data: dict, source_type: str) -> List[RawSearchResult]:
        results = []
        for r in data.get("results", []):
            results.append(RawSearchResult(
                title       = r.get("title", ""),
                url         = r.get("url",   ""),
                content     = r.get("content", "")[:800],   # 토큰 절약
                score       = r.get("score",  0.0),
                published   = r.get("published_date"),
                source_type = source_type,
            ))
        return results

    async def aclose(self):
        await self._client.aclose()


# ─────────────────────────────────────────────────────────────────────
# 3. 신호 분석기
# ─────────────────────────────────────────────────────────────────────

class SignalExtractor:
    """
    검색 결과 텍스트에서 PainSignal을 추출하는 규칙 기반 엔진.
    프로덕션에서는 LLM(Claude/GPT) 프롬프트로 보강하세요.
    """

    PATTERNS: Dict[SignalCategory, re.Pattern] = {
        SignalCategory.GROWTH: re.compile(
            r'투자|시리즈[ABC]|펀딩|상장|IPO|확장|신규 사업|신사업|'
            r'series [abc]|funding|ipo|expansion|launch|raised|hiring spree',
            re.IGNORECASE,
        ),
        SignalCategory.CRISIS: re.compile(
            r'소송|제재|규제|적자|손실|구조조정|감원|위기|리콜|사고|'
            r'lawsuit|sanction|regulation|loss|layoff|crisis|recall|incident',
            re.IGNORECASE,
        ),
        SignalCategory.STRATEGY_SHIFT: re.compile(
            r'전략 변경|피벗|재편|디지털 전환|DX|AI 도입|클라우드 전환|'
            r'pivot|digital transformation|restructure|new strategy|shift',
            re.IGNORECASE,
        ),
        SignalCategory.HIRING: re.compile(
            r'채용|구인|대규모 고용|인재 확보|헤드카운트|'
            r'hiring|headcount|talent acquisition|open position|recruit',
            re.IGNORECASE,
        ),
        SignalCategory.TECH_ADOPTION: re.compile(
            r'AI|머신러닝|자동화|SaaS|플랫폼 도입|IT 투자|'
            r'machine learning|automation|platform|cloud|IT investment',
            re.IGNORECASE,
        ),
        SignalCategory.FINANCIAL: re.compile(
            r'실적|매출|영업이익|흑자|적자|어닝|주가|'
            r'revenue|earnings|profit|loss|quarterly|fiscal',
            re.IGNORECASE,
        ),
        SignalCategory.PARTNERSHIP: re.compile(
            r'파트너십|제휴|MOU|인수|합병|협력|'
            r'partnership|acquisition|merger|MOU|collaboration|alliance',
            re.IGNORECASE,
        ),
        SignalCategory.LEADERSHIP: re.compile(
            r'대표이사 교체|임원 변경|CEO 취임|CTO|CFO|새 경영진|'
            r'new CEO|CTO|CFO|leadership change|executive|appointment',
            re.IGNORECASE,
        ),
    }

    URGENCY_BOOST: Dict[SignalCategory, float] = {
        SignalCategory.CRISIS:         0.35,
        SignalCategory.STRATEGY_SHIFT: 0.25,
        SignalCategory.HIRING:         0.20,
        SignalCategory.LEADERSHIP:     0.20,
        SignalCategory.GROWTH:         0.15,
        SignalCategory.TECH_ADOPTION:  0.15,
    }

    def extract(
        self, results: List[RawSearchResult], company_name: str
    ) -> List[PainSignal]:
        seen: set[str] = set()
        signals: List[PainSignal] = []

        for r in results:
            text = f"{r.title} {r.content}"
            for category, pattern in self.PATTERNS.items():
                hits = pattern.findall(text)
                if not hits:
                    continue

                # 중복 제거 (동일 제목)
                key = hashlib.md5(r.title.encode()).hexdigest()[:10]
                if key in seen:
                    continue
                seen.add(key)

                urgency   = min(0.3 + self.URGENCY_BOOST.get(category, 0.1) + r.score * 0.2, 1.0)
                confidence = min(0.4 + len(hits) * 0.1 + r.score * 0.3, 0.95)

                headline = self._extract_headline(r.title, company_name, category)
                detail   = r.content[:300].strip()

                signals.append(PainSignal(
                    category   = category,
                    headline   = headline,
                    detail     = detail,
                    evidence   = r.content[:200],
                    source_url = r.url,
                    published  = r.published,
                    urgency    = round(urgency, 2),
                    confidence = round(confidence, 2),
                ))

        # urgency 내림차순 정렬
        return sorted(signals, key=lambda s: -s.urgency)

    def _extract_headline(
        self, title: str, company: str, category: SignalCategory
    ) -> str:
        prefix_map = {
            SignalCategory.GROWTH:         f"{company}, ",
            SignalCategory.CRISIS:         f"[위기] {company} ",
            SignalCategory.STRATEGY_SHIFT: f"[전략 전환] {company} ",
            SignalCategory.HIRING:         f"[채용 확대] {company} ",
            SignalCategory.TECH_ADOPTION:  f"[기술 도입] {company} ",
            SignalCategory.FINANCIAL:      f"[재무] {company} ",
            SignalCategory.PARTNERSHIP:    f"[파트너십] {company} ",
            SignalCategory.LEADERSHIP:     f"[인사] {company} ",
        }
        prefix = prefix_map.get(category, f"{company}: ")
        clean_title = title.replace(company, "").strip(" -|·")
        return (prefix + clean_title)[:120]


# ─────────────────────────────────────────────────────────────────────
# 4. 연결고리 생성기 (ConnectionBridge Factory)
# ─────────────────────────────────────────────────────────────────────

class BridgeFactory:
    """
    PainSignal + ProductContext → ConnectionBridge 생성.

    product_context 예시:
      {
        "name": "OpenerUltra",
        "features": ["AI 세일즈 인텔리전스", "자동 리서치", "개인화 이메일"],
        "value_prop": "세일즈 팀이 리서치 없이 바로 미팅을 잡을 수 있도록"
      }
    """

    # 카테고리별 연결 논거 템플릿
    BRIDGE_TEMPLATES: Dict[SignalCategory, dict] = {
        SignalCategory.GROWTH: {
            "situation_tpl": "{company}이(가) {headline_detail} 상황에서 "
                             "세일즈 파이프라인을 빠르게 확장해야 하는 압박을 받고 있습니다.",
            "hook_tpl":      "신규 투자 유치 이후 영업 효율을 2배 높인 사례를 공유드릴 수 있습니다.",
            "opening_tpl":   "{company}의 최근 {signal_summary} 소식을 보고 연락드렸습니다—"
                             "빠른 성장 국면에서 {product}이(가) 어떤 역할을 할 수 있는지 10분 이야기 나눌 수 있을까요?",
        },
        SignalCategory.CRISIS: {
            "situation_tpl": "{company}이(가) {headline_detail} 상황에 직면해 있어, "
                             "운영 효율화와 리스크 대응이 최우선 과제일 것입니다.",
            "hook_tpl":      "유사한 위기 상황에서 운영 비용을 30% 절감한 고객 사례가 있습니다.",
            "opening_tpl":   "최근 {signal_summary} 관련 기사를 접하고, "
                             "비슷한 상황의 고객사를 어떻게 도왔는지 나눠드리고 싶어 연락드렸습니다.",
        },
        SignalCategory.STRATEGY_SHIFT: {
            "situation_tpl": "{company}이(가) {headline_detail}을(를) 추진하고 있어 "
                             "새로운 파트너십과 솔루션 도입에 열려 있을 시점입니다.",
            "hook_tpl":      "디지털 전환 초기 6개월이 골든타임—빠르게 움직인 팀이 시장을 선점합니다.",
            "opening_tpl":   "{company}의 {signal_summary} 방향에 맞춰 "
                             "{product}를 어떻게 연계할 수 있는지 구체적인 방안을 갖고 있습니다.",
        },
        SignalCategory.HIRING: {
            "situation_tpl": "{company}이(가) 대규모 채용을 진행 중이라는 것은 "
                             "팀 규모 확장에 따른 온보딩·생산성 문제가 발생할 수 있다는 신호입니다.",
            "hook_tpl":      "인력 2배 확장 시 세일즈 생산성을 유지하는 방법이 있습니다.",
            "opening_tpl":   "{company}이(가) {signal_summary}을(를) 보고 연락드렸어요. "
                             "팀 규모가 커질수록 {product}의 자동화가 더 빛을 발합니다.",
        },
        SignalCategory.TECH_ADOPTION: {
            "situation_tpl": "{company}이(가) {headline_detail}에 관심을 보이고 있어 "
                             "신규 기술 솔루션 도입 검토 시기임을 알 수 있습니다.",
            "hook_tpl":      "이미 검토 중인 기술 스택과 자연스럽게 통합되는 방법이 있습니다.",
            "opening_tpl":   "{company}의 {signal_summary} 관련 움직임을 보고 "
                             "{product}와 어떻게 시너지를 낼 수 있는지 아이디어를 드리고 싶습니다.",
        },
        SignalCategory.FINANCIAL: {
            "situation_tpl": "{company}의 최근 재무 지표를 보면 "
                             "효율화 압박 혹은 성장 투자 여력이 생긴 상황으로 분석됩니다.",
            "hook_tpl":      "투자 대비 ROI를 90일 안에 증명해 드릴 수 있습니다.",
            "opening_tpl":   "{company}의 최근 실적 발표 내용을 읽고 "
                             "{product}가 구체적으로 어떤 재무적 임팩트를 만들 수 있는지 이야기 나눠보고 싶습니다.",
        },
        SignalCategory.PARTNERSHIP: {
            "situation_tpl": "{company}이(가) {headline_detail}를 체결하면서 "
                             "새로운 사업 영역에서 솔루션 수요가 생겼을 가능성이 높습니다.",
            "hook_tpl":      "파트너십 직후가 신규 솔루션 논의의 최적 타이밍입니다.",
            "opening_tpl":   "최근 {company}의 {signal_summary} 뉴스를 접하고 "
                             "새로운 사업 방향과 {product}를 어떻게 연결할 수 있을지 여쭤보고 싶습니다.",
        },
        SignalCategory.LEADERSHIP: {
            "situation_tpl": "{company}에 새 경영진이 합류하면서 "
                             "기존 벤더 검토 및 신규 솔루션 도입 논의가 활발해질 시점입니다.",
            "hook_tpl":      "새 리더가 취임 후 90일은 새 파트너를 찾는 황금 기회입니다.",
            "opening_tpl":   "{company}의 {signal_summary} 관련 소식을 접했습니다. "
                             "새 경영진이 세우는 전략에 {product}가 어떻게 기여할 수 있는지 공유드리고 싶습니다.",
        },
    }

    def generate(
        self,
        signals: List[PainSignal],
        product_context: dict,
        company_name: str,
        top_n: int = 5,
    ) -> List[ConnectionBridge]:
        product_name = product_context.get("name", "우리 제품")
        bridges: List[ConnectionBridge] = []

        for sig in signals[:top_n]:
            tpl = self.BRIDGE_TEMPLATES.get(
                sig.category,
                self.BRIDGE_TEMPLATES[SignalCategory.GROWTH],
            )

            signal_summary = sig.headline.split(",")[-1].strip()[:60]
            headline_detail = sig.headline.replace(company_name, "").strip(" ,-[]")

            situation = tpl["situation_tpl"].format(
                company=company_name,
                headline_detail=headline_detail,
                signal_summary=signal_summary,
                product=product_name,
            )
            hook = tpl["hook_tpl"].format(
                company=company_name,
                product=product_name,
            )
            opening = tpl["opening_tpl"].format(
                company=company_name,
                signal_summary=signal_summary,
                product=product_name,
            )

            # 토크트랙 조합
            features = product_context.get("features", [])
            value_prop = product_context.get("value_prop", "")
            feature_str = ", ".join(features[:2]) if features else "핵심 기능"
            talk_track = (
                f"{situation} "
                f"{product_name}의 {feature_str}을(를) 통해 이 상황을 어떻게 활용할 수 있는지 "
                f"구체적인 방안을 갖고 있습니다. {value_prop}"
            )

            relevance = round(
                sig.urgency * 0.5 + sig.confidence * 0.5, 2
            )

            bridges.append(ConnectionBridge(
                pain_signal_id  = sig.signal_id,
                buyer_situation = situation,
                product_hook    = hook,
                opening_line    = opening,
                talk_track      = talk_track,
                relevance_score = relevance,
                category        = sig.category,
            ))

        return sorted(bridges, key=lambda b: -b.relevance_score)


# ─────────────────────────────────────────────────────────────────────
# 5. ResearcherAgent 메인 클래스
# ─────────────────────────────────────────────────────────────────────

class ResearcherAgent:
    """
    Tavily Deep Search 기반 바이어 리서처.

    사용법
    ------
    agent = ResearcherAgent(tavily_api_key="tvly-...")

    report = await agent.research(
        company_name   = "카카오",
        company_domain = "kakao.com",
        product_context = {
            "name": "OpenerUltra",
            "features": ["AI 세일즈 인텔리전스", "자동 딥 리서치", "개인화 이메일"],
            "value_prop": "세일즈팀이 리서치 없이 바로 미팅을 잡을 수 있도록",
        },
        on_progress = lambda pct, msg: print(f"[{pct:.0%}] {msg}"),
    )
    print(report.to_dict())
    """

    # 검색 쿼리 템플릿 (Round별)
    QUERY_TEMPLATES = {
        "company_profile": [
            "{company} 회사 소개 사업 영역 2024 2025",
            "{company} 최근 뉴스",
        ],
        "investment_growth": [
            "{company} 투자 유치 펀딩 2024 2025",
            "{company} 신규 사업 확장 계획",
            "{company} 시리즈 funding raised",
        ],
        "crisis_risk": [
            "{company} 위기 소송 규제 문제 2024 2025",
            "{company} 감원 구조조정 적자",
            "{company} crisis lawsuit regulation fine 2024",
        ],
        "strategy": [
            "{company} 전략 디지털 전환 AI 도입 2024 2025",
            "{company} strategy digital transformation roadmap",
        ],
        "leadership": [
            "{company} CEO CTO CFO 신임 교체 2024 2025",
            "{company} new executive leadership appointment",
        ],
        "market_context": [
            "{company} 업계 경쟁사 시장 동향",
            "{domain} industry trend competitor analysis",
        ],
    }

    def __init__(
        self,
        tavily_api_key: Optional[str] = None,
        max_concurrent: int = 3,
    ):
        self._tavily = TavilyClient(api_key=tavily_api_key)
        self._extractor = SignalExtractor()
        self._bridge_factory = BridgeFactory()
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def research(
        self,
        company_name:    str,
        company_domain:  str = "",
        product_context: Optional[dict] = None,
        on_progress:     Optional[Any] = None,
        top_bridges:     int = 5,
    ) -> ResearchReport:
        """
        풀 리서치 파이프라인 실행.
        on_progress(percent: float, message: str) 콜백으로 진행 상황 전달.
        """
        if product_context is None:
            product_context = {"name": "제품", "features": [], "value_prop": ""}

        report = ResearchReport(
            company_name   = company_name,
            company_domain = company_domain,
        )

        async def _progress(pct: float, msg: str):
            if on_progress:
                if asyncio.iscoroutinefunction(on_progress):
                    await on_progress(pct, msg)
                else:
                    on_progress(pct, msg)

        # ── Round 1: 병렬 검색 실행 ───────────────────────────────
        await _progress(0.05, f"'{company_name}' 정보 수집 시작...")
        all_results = await self._run_all_searches(company_name, company_domain, _progress)
        report.raw_results = all_results

        await _progress(0.70, f"검색 완료 — 총 {len(all_results)}개 결과, 신호 분석 중...")

        # ── Round 2: 신호 추출 ────────────────────────────────────
        signals = self._extractor.extract(all_results, company_name)
        report.pain_signals = signals[:10]   # 상위 10개

        await _progress(0.85, f"{len(signals)}개 페인 신호 추출 완료, 연결고리 생성 중...")

        # ── Round 3: 연결고리 생성 ────────────────────────────────
        bridges = self._bridge_factory.generate(
            signals, product_context, company_name, top_n=top_bridges
        )
        report.bridges = bridges

        # ── Round 4: 요약 합성 ────────────────────────────────────
        report.exec_summary = self._synthesize_summary(signals, bridges, company_name)
        report.top_hooks    = [b.opening_line for b in bridges[:3]]

        await _progress(1.0, "리서치 완료!")
        return report

    # ── 내부: 병렬 검색 ───────────────────────────────────────────

    async def _run_all_searches(
        self,
        company: str,
        domain:  str,
        progress_cb,
    ) -> List[RawSearchResult]:
        tasks = []
        queries_flat: List[Tuple[str, str]] = []   # (query, search_type)

        for group, templates in self.QUERY_TEMPLATES.items():
            for tpl in templates:
                q = tpl.format(company=company, domain=domain or company)
                search_type = "news" if group in ("investment_growth", "crisis_risk") else "general"
                queries_flat.append((q, search_type))

        total = len(queries_flat)
        completed = 0

        async def _run_one(q: str, stype: str) -> List[RawSearchResult]:
            nonlocal completed
            async with self._semaphore:
                try:
                    if stype == "news":
                        results = await self._tavily.news_search(q, max_results=5, days=180)
                    else:
                        results = await self._tavily.search(q, max_results=5)
                    completed += 1
                    pct = 0.05 + (completed / total) * 0.60
                    await progress_cb(pct, f"검색 중 ({completed}/{total}): {q[:40]}…")
                    return results
                except Exception as e:
                    completed += 1
                    return []

        nested = await asyncio.gather(*[_run_one(q, st) for q, st in queries_flat])
        # 평탄화 + 중복 URL 제거
        seen_urls: set[str] = set()
        flat: List[RawSearchResult] = []
        for batch in nested:
            for r in batch:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    flat.append(r)
        return flat

    # ── 내부: 요약 합성 ───────────────────────────────────────────

    @staticmethod
    def _synthesize_summary(
        signals: List[PainSignal],
        bridges: List[ConnectionBridge],
        company: str,
    ) -> str:
        if not signals:
            return f"{company}에 대한 유의미한 신호를 찾지 못했습니다."

        top_cats = [s.category.value for s in signals[:3]]
        top_headlines = "; ".join(s.headline[:60] for s in signals[:3])
        top_hook = bridges[0].opening_line if bridges else ""

        return (
            f"【{company} 리서치 요약】\n"
            f"주요 신호 카테고리: {', '.join(top_cats)}\n"
            f"핵심 발견: {top_headlines}\n"
            f"권장 오프닝: {top_hook}\n"
            f"총 {len(signals)}개 신호, {len(bridges)}개 연결고리 생성 완료."
        )

    async def aclose(self):
        await self._tavily.aclose()
