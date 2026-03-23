"""
opener-ultra-mvp / engine / agents / copywriter.py
====================================================
고밀도 카피라이팅 에이전트 — CopywriterAgent

설계 원칙
----------
1. 슬라이드 글자 수 엄격 통제
   - 각 슬라이드 타입별 CHAR_LIMITS Dict로 hard ceiling 관리
   - 초과 시 자동 트런케이션 + 경고 로그

2. 약속된 JSON 포맷 보장
   - SlidePayload dataclass → to_dict() → JSON 직렬화
   - Claude API 출력을 스키마 검증 후 재조립

3. 개인화 Hook 생성
   - 바이어 회사/직무/최근 뉴스를 조합한 이메일 훅
   - Pain Signal 기반 자동 선택

4. 전략 연계 (strategist.py ProposalBlueprint 입력)
   - 국가별 문화 스타일로 CTA·톤 자동 조정
   - 직무별 핵심 두려움을 바디카피에 반영

출력 포맷
----------
{
  "meta": { doc_id, buyer_company, buyer_name, buyer_role,
            product_name, culture_style, created_at, total_violations },
  "email": { subject, preview_text, body, cta_line, ps_line,
             char_count, violations },
  "slides": [
    { slide_num, type, headline, subheadline, body, bullets[],
      visual_note, speaker_note, char_count, violations[] }
    x5
  ]
}
"""

from __future__ import annotations

import json
import re
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════
# 1. 슬라이드 타입 & 글자 수 제한 규격
# ═══════════════════════════════════════════════════════════════════

class SlideType(str, Enum):
    COVER    = "cover"      # 슬라이드 1: 표지
    PAIN     = "pain"       # 슬라이드 2: 페인포인트
    SOLUTION = "solution"   # 슬라이드 3: 솔루션
    PROOF    = "proof"      # 슬라이드 4: 증거/사례
    CTA      = "cta"        # 슬라이드 5: Call-to-Action


# 타입별 글자 수 상한 (headline / subheadline / body / bullet 1개당)
CHAR_LIMITS: Dict[str, Dict[str, int]] = {
    "cover":    {"headline": 55, "subheadline": 90,  "body": 0,   "bullet": 0},
    "pain":     {"headline": 60, "subheadline": 100, "body": 220, "bullet": 80},
    "solution": {"headline": 60, "subheadline": 100, "body": 200, "bullet": 80},
    "proof":    {"headline": 60, "subheadline": 100, "body": 250, "bullet": 90},
    "cta":      {"headline": 55, "subheadline": 90,  "body": 160, "bullet": 70},
}

MAX_BULLETS = 3

EMAIL_LIMITS = {
    "subject":      65,
    "preview_text": 90,
    "body":         1800,
    "cta_line":     90,
    "ps_line":      130,
}


# ═══════════════════════════════════════════════════════════════════
# 2. 데이터 모델
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SlidePayload:
    slide_num:    int
    type:         str
    headline:     str
    subheadline:  str
    body:         str
    bullets:      List[str] = field(default_factory=list)
    visual_note:  str = ""
    speaker_note: str = ""
    violations:   List[str] = field(default_factory=list)

    def validate(self) -> "SlidePayload":
        lim = CHAR_LIMITS.get(self.type, CHAR_LIMITS["pain"])
        vios = []

        def trim(text: str, limit: int, name: str) -> str:
            if limit == 0:
                if text.strip():
                    vios.append(f"{name}: must be empty for {self.type}")
                return ""
            if len(text) > limit:
                vios.append(f"{name}: {len(text)}>{limit} chars — auto-trimmed")
                return text[: limit - 1].rstrip() + "\u2026"
            return text

        self.headline    = trim(self.headline,    lim["headline"],    "headline")
        self.subheadline = trim(self.subheadline, lim["subheadline"], "subheadline")
        self.body        = trim(self.body,        lim["body"],        "body")
        self.bullets     = [
            trim(b, lim["bullet"], f"bullet[{i}]")
            for i, b in enumerate(self.bullets[:MAX_BULLETS])
        ]
        self.violations  = vios
        return self

    def to_dict(self) -> dict:
        return {
            "slide_num":   self.slide_num,
            "type":        self.type,
            "headline":    self.headline,
            "subheadline": self.subheadline,
            "body":        self.body,
            "bullets":     self.bullets,
            "visual_note": self.visual_note,
            "speaker_note": self.speaker_note,
            "char_count": {
                "headline":    len(self.headline),
                "subheadline": len(self.subheadline),
                "body":        len(self.body),
            },
            "violations": self.violations,
        }


@dataclass
class EmailPayload:
    subject:      str
    preview_text: str
    body:         str
    cta_line:     str
    ps_line:      str
    violations:   List[str] = field(default_factory=list)

    def validate(self) -> "EmailPayload":
        vios = []

        def trim(text: str, limit: int, name: str) -> str:
            if len(text) > limit:
                vios.append(f"{name}: {len(text)}>{limit} — trimmed")
                return text[: limit - 1].rstrip() + "\u2026"
            return text

        self.subject      = trim(self.subject,      EMAIL_LIMITS["subject"],      "subject")
        self.preview_text = trim(self.preview_text, EMAIL_LIMITS["preview_text"], "preview_text")
        self.body         = trim(self.body,         EMAIL_LIMITS["body"],         "body")
        self.cta_line     = trim(self.cta_line,     EMAIL_LIMITS["cta_line"],     "cta_line")
        self.ps_line      = trim(self.ps_line,      EMAIL_LIMITS["ps_line"],      "ps_line")
        self.violations   = vios
        return self

    def to_dict(self) -> dict:
        return {
            "subject":       self.subject,
            "preview_text":  self.preview_text,
            "body":          self.body,
            "cta_line":      self.cta_line,
            "ps_line":       self.ps_line,
            "char_count":    {"subject": len(self.subject), "body": len(self.body)},
            "violations":    self.violations,
        }


@dataclass
class CopyDocument:
    doc_id:        str   = field(default_factory=lambda: uuid.uuid4().hex[:10])
    buyer_company: str   = ""
    buyer_name:    str   = ""
    buyer_role:    str   = ""
    product_name:  str   = ""
    culture_style: str   = ""
    created_at:    float = field(default_factory=time.time)
    email:         Optional[EmailPayload]  = None
    slides:        List[SlidePayload]      = field(default_factory=list)
    total_violations: int = 0

    def compile(self) -> "CopyDocument":
        if self.email:
            self.email.validate()
        for s in self.slides:
            s.validate()
        self.total_violations = (
            sum(len(s.violations) for s in self.slides)
            + (len(self.email.violations) if self.email else 0)
        )
        return self

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_dict(self) -> dict:
        return {
            "meta": {
                "doc_id":           self.doc_id,
                "buyer_company":    self.buyer_company,
                "buyer_name":       self.buyer_name,
                "buyer_role":       self.buyer_role,
                "product_name":     self.product_name,
                "culture_style":    self.culture_style,
                "created_at":       self.created_at,
                "total_violations": self.total_violations,
            },
            "email":  self.email.to_dict() if self.email else None,
            "slides": [s.to_dict() for s in self.slides],
        }


# ═══════════════════════════════════════════════════════════════════
# 3. 프롬프트 빌더
# ═══════════════════════════════════════════════════════════════════

STYLE_VOICE = {
    "CONCLUSION_FIRST": "Direct, confident, lead with the payoff. Numbers first. No hedging.",
    "TRUST_FIRST":      "Warm, respectful, relationship-first. Use 'together', 'partnership'. No urgency pressure.",
    "VALUE_FIRST":      "Clarity over cleverness. Show price-to-value immediately. Use comparisons.",
    "STORY_FIRST":      "Open with a mini-story. Emotion before logic. Use 'imagine' and future-state language.",
    "DATA_FIRST":       "Every claim needs a source or metric. Precise language. No superlatives.",
    "RISK_FIRST":       "Acknowledge risk upfront then eliminate it. Use 'proven', 'guaranteed', 'zero-risk pilot'.",
    "HIERARCHY_FIRST":  "Lead with prestige and authority. Name-drop top-tier references. Strategic framing.",
    "RELATIONSHIP_FIRST": "Personal warmth, long-term framing. 'Our shared journey.' Partner language throughout.",
}

SLIDE_PROMPTS = {
    "cover": """
Write the COVER slide.
- headline (≤55 chars): A bold transformation promise for {role} at {company}.
  Must create curiosity or tension. NOT 'Welcome to {product}.'
- subheadline (≤90 chars): The specific business outcome they will get.
- body: MUST BE EMPTY STRING ""
- bullets: MUST BE EMPTY ARRAY []
- visual_note: Art direction for the designer (background mood, hero image concept).
- speaker_note: How to open the meeting using this slide (2 sentences).
""",
    "pain": """
Write the PAIN slide.
- headline (≤60 chars): Name the problem in the buyer's own language. Start with a verb or number.
- subheadline (≤100 chars): The cost of inaction — what happens if nothing changes.
- body (≤220 chars): 2 sentences expanding on the pain. Specific to {role}'s world.
- bullets (≤80 chars each, max 3): 3 concrete symptoms of the problem. No fluff.
- visual_note: A chart, graph, or visual metaphor that amplifies the pain.
- speaker_note: Pause-and-ask technique — a question to ask the buyer after this slide.
""",
    "solution": """
Write the SOLUTION slide.
- headline (≤60 chars): '{product} + transformation verb + outcome.' Lead with the 'after' state.
- subheadline (≤100 chars): HOW it works in one crisp line. Mechanism, not marketing.
- body (≤200 chars): Bridge from their pain to this solution. 2 sentences max.
- bullets (≤80 chars each, max 3): 3 capabilities — each framed as a buyer outcome, not a feature.
- visual_note: Product screenshot or 'before/after' flow diagram concept.
- speaker_note: The one demo moment that closes most deals. What to show live.
""",
    "proof": """
Write the PROOF / CASE STUDY slide.
- headline (≤60 chars): A specific result achieved by a real customer type. Use a number.
- subheadline (≤100 chars): Context — who this customer is and their situation before.
- body (≤250 chars): The 3-part story: situation → action → result. One customer example.
- bullets (≤90 chars each, max 3): 3 measurable outcomes with numbers (%, $, days, hours).
- visual_note: Customer logo placeholder + a pullquote visual.
- speaker_note: How to handle 'do you have a reference in our industry?' objection.
""",
    "cta": """
Write the CTA slide.
- headline (≤55 chars): The single ask — clear, low-friction. Start with an action verb.
- subheadline (≤90 chars): Why NOW — urgency or opportunity cost of waiting.
- body (≤160 chars): What happens in the next 14 days if they say yes. The fast path.
- bullets (≤70 chars each, max 3): 3 next-step options (from lowest to highest commitment).
- visual_note: Simple timeline graphic or calendar concept.
- speaker_note: How to handle 'let me think about it' and get a micro-commitment.
""",
}

EMAIL_PROMPT = """
Write a cold outreach email that gets replies.

CONTEXT:
- Buyer: {name} ({role}) at {company}
- Recent trigger / hook: {hook}
- Product: {product}
- Culture style: {style}
- Core pain: {pain}

OUTPUT a JSON object with EXACTLY these keys:

subject (≤65 chars):
  Use a pattern that creates curiosity or names a specific problem.
  Templates: "[Company]'s [problem]" / "Quick question, {first_name}" / "[Competitor] does X—you could too"

preview_text (≤90 chars):
  The sentence after the subject in Gmail preview. Must complete the thought.

body (≤1800 chars):
  PARAGRAPH 1 — THE HOOK (2 sentences max):
    Reference the specific trigger ({hook}). Make it unmistakably personal.
    Show you did research. Do NOT start with "I hope this finds you well."

  PARAGRAPH 2 — THE BRIDGE (2-3 sentences):
    Name the exact pain a {role} at {company} is likely feeling right now.
    Use the buyer's likely internal language, not product marketing language.

  PARAGRAPH 3 — THE PROOF (2 sentences):
    One concrete result from a similar company. Include a number.
    "{Product} helped [similar company type] [specific result] in [timeframe]."

  PARAGRAPH 4 — THE ASK (1 sentence):
    A single, frictionless question. NOT "Would you like a demo?"
    Use: "Worth a 15-min call?" / "Does [specific outcome] sound relevant for Q3?"

cta_line (≤90 chars):
  A calendar link sentence or reply prompt. Extremely low friction.

ps_line (≤130 chars):
  A P.S. that adds a second hook — either social proof, urgency, or a curiosity gap.
  P.S. lines get read. Make it count.
"""


# ═══════════════════════════════════════════════════════════════════
# 4. Claude API 호출 & JSON 파서
# ═══════════════════════════════════════════════════════════════════

class ClaudeAPIError(Exception):
    pass


def _call_claude(
    user_prompt: str,
    system_prompt: str,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 1200,
) -> str:
    """Claude API 동기 호출. 반환값: 텍스트 응답 문자열."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return msg.content[0].text


def _parse_json(raw: str) -> dict:
    """응답에서 JSON 블록 추출 및 파싱."""
    # 코드 펜스 제거
    cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
    # 첫 { ... } 블록 추출
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in response:\n{raw[:300]}")
    return json.loads(match.group())


# ═══════════════════════════════════════════════════════════════════
# 5. CopywriterAgent 메인 클래스
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are an elite B2B sales copywriter.
Rules:
1. Output ONLY valid JSON — no markdown fences, no explanation, no preamble.
2. NEVER exceed the character limits specified in the prompt.
3. Every claim must be specific — no vague adjectives like "powerful", "seamless", "robust".
4. Personalize to the buyer's company, role, and pain signal.
5. Match the cultural voice style exactly.
6. Bullets start with a strong verb or number. Never start with "Our" or "We"."""


class CopywriterAgent:
    """
    전략 블루프린트 + 바이어 컨텍스트 → 5-슬라이드 PDF 카피 + 개인화 이메일

    사용법
    ------
    agent = CopywriterAgent(api_key="sk-ant-...")

    doc = agent.generate(
        buyer_company   = "Acme Corp",
        buyer_name      = "Sarah Kim",
        buyer_role      = "VP Sales",
        product_name    = "OpenerUltra",
        culture_style   = "CONCLUSION_FIRST",
        pain_signal     = "Acme raised $30M Series B and is expanding their sales team 3x",
        value_prop      = "AI-powered sales research that eliminates 3 hours of manual prep per rep",
        on_progress     = lambda pct, msg: print(f"[{pct:.0%}] {msg}"),
    )

    print(doc.to_json())
    """

    def __init__(self, api_key: str):
        self._api_key = api_key

    def generate(
        self,
        buyer_company:  str,
        buyer_name:     str,
        buyer_role:     str,
        product_name:   str,
        culture_style:  str = "CONCLUSION_FIRST",
        pain_signal:    str = "",
        value_prop:     str = "",
        on_progress:    Optional[Callable[[float, str], None]] = None,
    ) -> CopyDocument:

        def _prog(pct: float, msg: str):
            if on_progress:
                on_progress(pct, msg)

        voice = STYLE_VOICE.get(culture_style, STYLE_VOICE["CONCLUSION_FIRST"])
        hook  = pain_signal or f"{buyer_company} is growing fast"

        doc = CopyDocument(
            buyer_company=buyer_company,
            buyer_name=buyer_name,
            buyer_role=buyer_role,
            product_name=product_name,
            culture_style=culture_style,
        )

        # ── 슬라이드 5장 생성 ─────────────────────────────────────
        slide_order = ["cover", "pain", "solution", "proof", "cta"]

        for i, stype in enumerate(slide_order):
            _prog((i / 6) * 0.8, f"슬라이드 {i+1}/5 생성 중: {stype.upper()}…")

            context = (
                f"Buyer: {buyer_name} ({buyer_role}) at {buyer_company}\n"
                f"Product: {product_name}\n"
                f"Cultural voice: {voice}\n"
                f"Core pain / hook: {hook}\n"
                f"Value proposition: {value_prop}\n"
            )

            slide_instruction = SLIDE_PROMPTS[stype].format(
                role=buyer_role,
                company=buyer_company,
                product=product_name,
                hook=hook,
            )

            user_prompt = (
                f"{context}\n\n"
                f"SLIDE INSTRUCTIONS:\n{slide_instruction}\n\n"
                "Respond with ONLY a JSON object using these exact keys:\n"
                '{"headline":"...","subheadline":"...","body":"...","bullets":["..."],"visual_note":"...","speaker_note":"..."}'
            )

            try:
                raw  = _call_claude(user_prompt, SYSTEM_PROMPT, self._api_key)
                data = _parse_json(raw)

                slide = SlidePayload(
                    slide_num=i + 1,
                    type=stype,
                    headline=data.get("headline", ""),
                    subheadline=data.get("subheadline", ""),
                    body=data.get("body", ""),
                    bullets=data.get("bullets", []),
                    visual_note=data.get("visual_note", ""),
                    speaker_note=data.get("speaker_note", ""),
                )
            except Exception as e:
                # 폴백: 빈 슬라이드로 대체
                slide = SlidePayload(
                    slide_num=i + 1, type=stype,
                    headline=f"[ERROR] {str(e)[:50]}",
                    subheadline="", body="", bullets=[],
                )

            doc.slides.append(slide)

        # ── 이메일 생성 ───────────────────────────────────────────
        _prog(0.85, "개인화 이메일 생성 중…")

        email_user_prompt = EMAIL_PROMPT.format(
            name=buyer_name,
            role=buyer_role,
            company=buyer_company,
            hook=hook,
            product=product_name,
            style=voice,
            pain=value_prop or hook,
        ) + (
            "\n\nRespond with ONLY a JSON object with keys: "
            "subject, preview_text, body, cta_line, ps_line"
        )

        try:
            raw_email  = _call_claude(email_user_prompt, SYSTEM_PROMPT, self._api_key, max_tokens=1800)
            email_data = _parse_json(raw_email)
            doc.email  = EmailPayload(
                subject=email_data.get("subject", ""),
                preview_text=email_data.get("preview_text", ""),
                body=email_data.get("body", ""),
                cta_line=email_data.get("cta_line", ""),
                ps_line=email_data.get("ps_line", ""),
            )
        except Exception as e:
            doc.email = EmailPayload(
                subject=f"[ERROR] {str(e)[:40]}",
                preview_text="", body="", cta_line="", ps_line="",
            )

        _prog(0.95, "글자 수 검증 중…")
        doc.compile()
        _prog(1.0, f"완료! 위반 {doc.total_violations}건")
        return doc


# ═══════════════════════════════════════════════════════════════════
# 6. 규격 상수 노출 (UI에서 참조용)
# ═══════════════════════════════════════════════════════════════════

SPEC = {
    "slides": CHAR_LIMITS,
    "email":  EMAIL_LIMITS,
    "max_bullets_per_slide": MAX_BULLETS,
    "slide_order": ["cover", "pain", "solution", "proof", "cta"],
}
