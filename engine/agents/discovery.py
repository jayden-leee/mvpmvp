"""
opener-ultra-mvp / engine / agents / discovery.py
===================================================
딥 인터뷰 Discovery Agent

핵심 설계 철학
--------------
단순 Q&A가 아닌 '심리적 박리(Psychological Peeling)' 방식:
  Layer 0 → 표면 기술 (What)
  Layer 1 → 사용 맥락 (When / Where / Who)
  Layer 2 → 감정적 동기 (Why it matters)
  Layer 3 → 숨은 비교우위 (vs. 대안)
  Layer 4 → 바이어 언어 (타겟이 실제 쓰는 단어)

각 레이어가 충분히 채워지면 Value Proposition Canvas를 합성하고
인터뷰를 종료합니다.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── 1. 데이터 모델 ──────────────────────────────────────────────────

class InterviewLayer(int, Enum):
    SURFACE     = 0   # 제품/서비스 기본 기술
    CONTEXT     = 1   # 사용 맥락 (언제, 누가, 어디서)
    EMOTION     = 2   # 감정적 동기 & 페인포인트
    COMPETITIVE = 3   # 경쟁 대비 차별점
    BUYER_LANG  = 4   # 타겟 바이어의 언어
    SYNTHESIS   = 5   # 합성 완료


class InterviewStatus(str, Enum):
    IDLE        = "idle"
    IN_PROGRESS = "in_progress"
    SYNTHESIZING= "synthesizing"
    COMPLETE    = "complete"
    ABORTED     = "aborted"


@dataclass
class Message:
    role:      str           # "interviewer" | "user"
    content:   str
    layer:     InterviewLayer = InterviewLayer.SURFACE
    timestamp: float = field(default_factory=time.time)
    meta:      Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValueSignal:
    """인터뷰 중 포착된 가치 신호 하나."""
    signal_id:  str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    layer:      InterviewLayer = InterviewLayer.SURFACE
    raw_quote:  str = ""          # 유저의 원문
    abstracted: str = ""          # AI가 추상화한 가치 표현
    confidence: float = 0.0       # 0.0 – 1.0
    tags:       List[str] = field(default_factory=list)


@dataclass
class ValueProposition:
    """최종 합성된 Value Proposition Canvas."""
    vp_id:          str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    headline:       str = ""          # 원라이너 메시지
    target_persona: str = ""          # 타겟 바이어 페르소나
    core_pain:      str = ""          # 핵심 페인포인트
    gain:           str = ""          # 얻게 되는 혜택
    differentiator: str = ""          # 경쟁 대비 차별점
    proof_points:   List[str] = field(default_factory=list)
    buyer_keywords: List[str] = field(default_factory=list)
    signals:        List[ValueSignal] = field(default_factory=list)
    created_at:     float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "vp_id":          self.vp_id,
            "headline":       self.headline,
            "target_persona": self.target_persona,
            "core_pain":      self.core_pain,
            "gain":           self.gain,
            "differentiator": self.differentiator,
            "proof_points":   self.proof_points,
            "buyer_keywords": self.buyer_keywords,
            "signal_count":   len(self.signals),
        }


# ── 2. 분석 엔진 ──────────────────────────────────────────────────

class ResponseAnalyzer:
    """
    유저 답변을 분석해 Value Signal을 추출하고
    다음 질문 레이어를 결정하는 규칙 기반 + 패턴 엔진.

    프로덕션에서는 LLM 호출로 대체하거나 보강합니다.
    """

    # 감정/페인 신호 키워드
    PAIN_PATTERNS = re.compile(
        r'(불편|힘들|어렵|복잡|오래|느리|비싸|놓친|실수|잊|까먹|귀찮|번거|'
        r'painful|annoying|slow|expensive|manual|error|miss|forget|hard)',
        re.IGNORECASE
    )
    # 혜택/가치 신호 키워드
    GAIN_PATTERNS = re.compile(
        r'(빠르|쉽|자동|절약|효율|편리|정확|신뢰|안전|수익|성장|'
        r'fast|easy|auto|save|efficient|accurate|reliable|revenue|growth)',
        re.IGNORECASE
    )
    # 경쟁 비교 신호
    COMPETITIVE_PATTERNS = re.compile(
        r'(기존|원래|이전|다른|경쟁|비교|대신|대비|'
        r'before|instead|competitor|compared|alternative|replace)',
        re.IGNORECASE
    )
    # 바이어 역할 키워드
    PERSONA_PATTERNS = re.compile(
        r'(팀장|대표|담당자|개발자|마케터|디자이너|스타트업|중소기업|'
        r'manager|ceo|founder|developer|marketer|designer|startup|SMB|enterprise)',
        re.IGNORECASE
    )

    def analyze(self, text: str, current_layer: InterviewLayer) -> Tuple[List[ValueSignal], float]:
        """
        Returns:
            signals   — 발견된 ValueSignal 목록
            richness  — 답변의 풍부도 점수 (0.0–1.0)
        """
        signals: List[ValueSignal] = []
        richness = 0.0

        word_count = len(text.split())
        richness += min(word_count / 80, 0.4)   # 길이 기여 최대 0.4

        # 페인 시그널
        pain_hits = self.PAIN_PATTERNS.findall(text)
        if pain_hits:
            signals.append(ValueSignal(
                layer=InterviewLayer.EMOTION,
                raw_quote=text[:200],
                abstracted="사용자가 명시적 페인포인트를 언급: " + ", ".join(set(pain_hits)),
                confidence=min(len(pain_hits) * 0.2, 0.9),
                tags=["pain", "emotion"],
            ))
            richness += 0.2

        # 혜택 시그널
        gain_hits = self.GAIN_PATTERNS.findall(text)
        if gain_hits:
            signals.append(ValueSignal(
                layer=InterviewLayer.SURFACE,
                raw_quote=text[:200],
                abstracted="기능적 혜택 언급: " + ", ".join(set(gain_hits)),
                confidence=min(len(gain_hits) * 0.18, 0.85),
                tags=["gain", "feature"],
            ))
            richness += 0.2

        # 경쟁 시그널
        comp_hits = self.COMPETITIVE_PATTERNS.findall(text)
        if comp_hits:
            signals.append(ValueSignal(
                layer=InterviewLayer.COMPETITIVE,
                raw_quote=text[:200],
                abstracted="경쟁/대안 비교 발언 포착",
                confidence=min(len(comp_hits) * 0.25, 0.9),
                tags=["competitive", "differentiation"],
            ))
            richness += 0.15

        # 페르소나 시그널
        persona_hits = self.PERSONA_PATTERNS.findall(text)
        if persona_hits:
            signals.append(ValueSignal(
                layer=InterviewLayer.BUYER_LANG,
                raw_quote=text[:200],
                abstracted="타겟 페르소나 단서: " + ", ".join(set(persona_hits)),
                confidence=0.7,
                tags=["persona", "buyer"],
            ))
            richness += 0.05

        richness = min(richness, 1.0)
        return signals, richness


# ── 3. 질문 전략가 ────────────────────────────────────────────────

class QuestionStrategist:
    """
    현재 인터뷰 상태를 보고 다음에 물어야 할 질문을 선택합니다.

    각 레이어마다 'probe question bank'를 갖고 있으며,
    유저 답변의 키워드를 이용해 맞춤형 follow-up을 생성합니다.
    """

    OPENING = (
        "안녕하세요! 저는 여러분의 제품/서비스에서 "
        "타겟 바이어가 가장 매력을 느낄 핵심 가치를 찾아드리는 Discovery AI입니다. "
        "먼저, 지금 만들고 계신 제품이나 서비스를 한 문장으로 소개해 주실 수 있나요?"
    )

    LAYER_QUESTIONS: Dict[InterviewLayer, List[str]] = {
        InterviewLayer.SURFACE: [
            "그 기능이 실제로 어떻게 동작하는지 조금 더 구체적으로 설명해 주실 수 있나요?",
            "하루에 누가, 몇 번이나 그 기능을 사용하게 되나요?",
            "가장 자주 쓰이는 기능 TOP 3를 꼽는다면 무엇인가요?",
        ],
        InterviewLayer.CONTEXT: [
            "이 제품을 쓰게 되는 가장 전형적인 상황(시나리오)을 하나만 그려주세요. "
            "예: '월요일 아침, ○○이 ○○을 하다가 우리 서비스를 열었다'처럼요.",
            "이 제품을 처음 써보게 되는 계기가 주로 무엇인가요?",
            "주로 어떤 팀이나 직군이 가장 먼저 도입을 결정하나요?",
        ],
        InterviewLayer.EMOTION: [
            "이 제품이 없으면 고객이 가장 불편한 순간은 언제인가요?",
            "고객이 처음 성과를 경험했을 때 어떤 반응을 보였나요? "
            "실제 피드백 문장이 있다면 그대로 말씀해 주세요.",
            "이 제품을 쓰기 시작하면서 고객이 그만둔 행동이나 도구가 있나요?",
        ],
        InterviewLayer.COMPETITIVE: [
            "지금 고객들이 이 문제를 어떻게 해결하고 있나요? "
            "(엑셀? 타 SaaS? 직접 개발?) 우리 제품과 무엇이 다른가요?",
            "경쟁사 대비 가장 자신 있는 한 가지는 무엇인가요? "
            "그것을 느낀 구체적인 사례가 있나요?",
            "고객이 타 솔루션을 쓰다가 우리 제품으로 넘어온 결정적인 이유는 무엇이었나요?",
        ],
        InterviewLayer.BUYER_LANG: [
            "고객이 이 제품을 동료에게 추천할 때 실제로 어떤 표현을 쓰나요? "
            "기억나는 문장이 있으면 그대로 말씀해 주세요.",
            "만약 이 제품의 광고 카피를 고객에게 쓰게 한다면 뭐라고 쓸 것 같나요?",
            "세일즈 미팅에서 고객이 '이거 좋다'고 할 때 가장 자주 언급하는 단어나 표현은요?",
        ],
    }

    PROBING_FOLLOWUP = [
        "방금 말씀하신 '{keyword}'가 매우 흥미롭습니다. "
        "그 경험을 좀 더 구체적으로 이야기해 주실 수 있나요?",
        "'{keyword}'라고 표현하셨는데, 고객 입장에서는 이게 왜 중요한가요?",
        "'{keyword}' 덕분에 고객이 실제로 어떤 결과를 얻었나요?",
    ]

    THIN_ANSWER_PROBES = [
        "조금 더 구체적인 예시를 들어주실 수 있나요?",
        "실제로 그런 일이 있었던 사례를 하나만 들어주세요.",
        "수치나 시간, 돈으로 표현하면 어느 정도 차이인가요?",
    ]

    def next_question(
        self,
        layer: InterviewLayer,
        answer: str,
        signals: List[ValueSignal],
        richness: float,
        q_index: int,
    ) -> str:
        """다음 질문 문자열을 반환합니다."""

        # 답변이 너무 짧으면 구체화 요청
        if richness < 0.2 and len(answer.strip()) < 30:
            return self.THIN_ANSWER_PROBES[q_index % len(self.THIN_ANSWER_PROBES)]

        # 강한 키워드가 있으면 follow-up 우선
        if signals:
            keyword = signals[0].abstracted.split(":")[-1].strip().split(",")[0].strip()
            if keyword:
                template = self.PROBING_FOLLOWUP[q_index % len(self.PROBING_FOLLOWUP)]
                return template.replace("{keyword}", keyword)

        # 레이어별 기본 질문
        bank = self.LAYER_QUESTIONS.get(layer, [])
        if bank:
            return bank[q_index % len(bank)]

        return "조금 더 자세히 말씀해 주실 수 있나요?"


# ── 4. Value Proposition 합성기 ────────────────────────────────────

class VPSynthesizer:
    """
    수집된 ValueSignal 목록을 바탕으로
    최종 Value Proposition Canvas를 생성합니다.

    프로덕션: 이 메서드를 LLM 프롬프트 + 구조화된 출력으로 교체하면
    훨씬 풍부한 VP가 생성됩니다.
    """

    def synthesize(
        self,
        signals: List[ValueSignal],
        history: List[Message],
    ) -> ValueProposition:

        # ── 전체 대화에서 원문 텍스트 수집
        user_texts = " ".join(
            m.content for m in history if m.role == "user"
        )

        # ── 페르소나 추출
        persona_signals = [s for s in signals if "persona" in s.tags]
        persona = "의사결정권을 가진 비즈니스 리더"
        if persona_signals:
            persona = persona_signals[-1].abstracted.split(":")[-1].strip()

        # ── 페인포인트 추출
        pain_signals = [s for s in signals if "pain" in s.tags]
        core_pain = "현재 프로세스의 비효율과 높은 운영 비용"
        if pain_signals:
            core_pain = pain_signals[-1].abstracted

        # ── 혜택 추출
        gain_signals = [s for s in signals if "gain" in s.tags]
        gain = "더 빠르고 정확한 결과로 팀 생산성 향상"
        if gain_signals:
            gain = gain_signals[-1].abstracted

        # ── 경쟁 차별점
        comp_signals = [s for s in signals if "competitive" in s.tags]
        diff = "기존 솔루션 대비 압도적인 사용성과 속도"
        if comp_signals:
            diff = comp_signals[-1].abstracted

        # ── 바이어 키워드 추출 (고빈도 명사/형용사)
        buyer_keywords = self._extract_keywords(user_texts)

        # ── 헤드라인 생성
        headline = self._generate_headline(gain, persona, diff)

        # ── 증거 포인트 (구체적 언급 문장)
        proof_points = [
            s.raw_quote[:120] + "…" if len(s.raw_quote) > 120 else s.raw_quote
            for s in signals[:3]
            if s.confidence > 0.5
        ]

        return ValueProposition(
            headline=headline,
            target_persona=persona,
            core_pain=core_pain,
            gain=gain,
            differentiator=diff,
            proof_points=proof_points,
            buyer_keywords=buyer_keywords,
            signals=signals,
        )

    def _extract_keywords(self, text: str) -> List[str]:
        """간단한 고빈도 키워드 추출 (stopword 제거)."""
        stopwords = {
            "이", "그", "저", "것", "수", "를", "을", "에", "의", "가",
            "and", "the", "is", "to", "a", "in", "of", "for", "we", "our",
        }
        words = re.findall(r'[가-힣a-zA-Z]{2,}', text)
        freq: Dict[str, int] = {}
        for w in words:
            w = w.lower()
            if w not in stopwords:
                freq[w] = freq.get(w, 0) + 1
        sorted_words = sorted(freq.items(), key=lambda x: -x[1])
        return [w for w, _ in sorted_words[:8]]

    def _generate_headline(self, gain: str, persona: str, diff: str) -> str:
        gain_short = gain.split(":")[0][:30].strip()
        persona_short = persona.split(",")[0][:20].strip()
        return f"{persona_short}를 위한, {gain_short}"


# ── 5. DiscoveryAgent 메인 클래스 ─────────────────────────────────

class DiscoveryAgent:
    """
    이벤트 기반 딥 인터뷰 에이전트.

    사용 방법
    ---------
    agent = DiscoveryAgent()

    # 1) 인터뷰 시작 → 오프닝 메시지 반환
    opening = agent.start()

    # 2) 유저 답변 제출 → 다음 질문 또는 VP 반환
    result = await agent.respond("저희는 B2B SaaS로 ...")
    # result.type == "question" or "value_proposition"

    # 3) 이벤트 구독
    agent.on("layer_advance",    lambda e: ...)
    agent.on("signal_captured",  lambda e: ...)
    agent.on("vp_ready",         lambda e: ...)
    """

    MAX_QUESTIONS_PER_LAYER = 3
    MIN_SIGNALS_TO_ADVANCE  = 1
    LAYERS_REQUIRED         = [
        InterviewLayer.SURFACE,
        InterviewLayer.CONTEXT,
        InterviewLayer.EMOTION,
        InterviewLayer.COMPETITIVE,
        InterviewLayer.BUYER_LANG,
    ]

    def __init__(
        self,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ):
        self._analyzer    = ResponseAnalyzer()
        self._strategist  = QuestionStrategist()
        self._synthesizer = VPSynthesizer()

        self.history:         List[Message]     = []
        self.all_signals:     List[ValueSignal] = []
        self.layer_signals:   Dict[InterviewLayer, List[ValueSignal]] = {l: [] for l in InterviewLayer}
        self.layer_q_counts:  Dict[InterviewLayer, int] = {l: 0 for l in InterviewLayer}

        self.current_layer:   InterviewLayer = InterviewLayer.SURFACE
        self.status:          InterviewStatus = InterviewStatus.IDLE
        self.value_prop:      Optional[ValueProposition] = None

        self._listeners: Dict[str, List[Callable]] = {}
        if on_event:
            for ev in ["layer_advance", "signal_captured", "vp_ready", "question_asked"]:
                self.on(ev, lambda e, ev=ev: on_event(ev, e))

    # ── Public API ────────────────────────────────────────────────

    def start(self) -> str:
        """인터뷰를 시작하고 오프닝 메시지를 반환합니다."""
        self.status = InterviewStatus.IN_PROGRESS
        opening = self._strategist.OPENING
        self._add_message("interviewer", opening, InterviewLayer.SURFACE)
        return opening

    async def respond(self, user_input: str) -> dict:
        """
        유저 답변을 처리하고 다음 질문 또는 최종 VP를 반환합니다.

        Returns dict:
          { "type": "question", "content": str, "layer": int, "progress": float }
          or
          { "type": "value_proposition", "vp": ValueProposition.to_dict() }
        """
        if self.status != InterviewStatus.IN_PROGRESS:
            raise RuntimeError(f"Interview not in progress (status={self.status})")

        # 1. 유저 메시지 기록
        self._add_message("user", user_input, self.current_layer)

        # 2. 분석
        signals, richness = self._analyzer.analyze(user_input, self.current_layer)
        for sig in signals:
            self.all_signals.append(sig)
            self.layer_signals[sig.layer].append(sig)
            await self._emit("signal_captured", {
                "signal": sig.__dict__,
                "layer": self.current_layer.value,
            })

        self.layer_q_counts[self.current_layer] += 1

        # 3. 레이어 전진 여부 판단
        should_advance = self._should_advance_layer(signals, richness)
        if should_advance:
            next_layer = self._next_layer()
            if next_layer is None:
                # 모든 레이어 완료 → VP 합성
                return await self._synthesize()

            prev_layer = self.current_layer
            self.current_layer = next_layer
            self.layer_q_counts[next_layer] = 0
            await self._emit("layer_advance", {
                "from": prev_layer.value,
                "to":   next_layer.value,
            })

        # 4. 다음 질문 생성
        q_idx = self.layer_q_counts[self.current_layer]
        question = self._strategist.next_question(
            self.current_layer, user_input, signals, richness, q_idx
        )
        self._add_message("interviewer", question, self.current_layer)
        await self._emit("question_asked", {
            "question": question,
            "layer": self.current_layer.value,
        })

        progress = self._calc_progress()
        return {
            "type":     "question",
            "content":  question,
            "layer":    self.current_layer.value,
            "layer_name": self.current_layer.name,
            "progress": progress,
        }

    def snapshot(self) -> dict:
        """현재 인터뷰 상태 스냅샷."""
        return {
            "status":        self.status.value,
            "current_layer": self.current_layer.value,
            "layer_name":    self.current_layer.name,
            "progress":      self._calc_progress(),
            "signal_count":  len(self.all_signals),
            "turn_count":    sum(1 for m in self.history if m.role == "user"),
            "vp":            self.value_prop.to_dict() if self.value_prop else None,
        }

    # ── Event System ──────────────────────────────────────────────

    def on(self, event: str, handler: Callable) -> None:
        (self._listeners.setdefault(event, [])).append(handler)

    async def _emit(self, event: str, payload: dict) -> None:
        for h in self._listeners.get(event, []):
            if asyncio.iscoroutinefunction(h):
                await h(payload)
            else:
                h(payload)

    # ── Internal helpers ──────────────────────────────────────────

    def _add_message(self, role: str, content: str, layer: InterviewLayer) -> None:
        self.history.append(Message(role=role, content=content, layer=layer))

    def _should_advance_layer(
        self, new_signals: List[ValueSignal], richness: float
    ) -> bool:
        q_count  = self.layer_q_counts[self.current_layer]
        sig_count = len(self.layer_signals.get(self.current_layer, []))

        # 현재 레이어 시그널이 충분히 모였거나, 질문을 충분히 소진했으면 진행
        rich_enough = richness >= 0.4 and sig_count >= self.MIN_SIGNALS_TO_ADVANCE
        exhausted   = q_count >= self.MAX_QUESTIONS_PER_LAYER
        return rich_enough or exhausted

    def _next_layer(self) -> Optional[InterviewLayer]:
        idx = self.LAYERS_REQUIRED.index(self.current_layer)
        if idx + 1 < len(self.LAYERS_REQUIRED):
            return self.LAYERS_REQUIRED[idx + 1]
        return None  # 마지막 레이어 완료

    def _calc_progress(self) -> float:
        total = len(self.LAYERS_REQUIRED)
        done  = self.LAYERS_REQUIRED.index(self.current_layer)
        return round(done / total, 2)

    async def _synthesize(self) -> dict:
        self.status = InterviewStatus.SYNTHESIZING
        await asyncio.sleep(0)   # 비동기 양보

        vp = self._synthesizer.synthesize(self.all_signals, self.history)
        self.value_prop = vp
        self.status = InterviewStatus.COMPLETE

        await self._emit("vp_ready", {"vp": vp.to_dict()})
        return {
            "type": "value_proposition",
            "vp":   vp.to_dict(),
        }
