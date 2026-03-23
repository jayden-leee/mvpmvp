"""
opener-ultra-mvp / engine / agents / proofreader.py
=====================================================
현지인 수준 톤앤매너 검수 에이전트 — ProofreaderAgent

핵심 설계
----------
단순 문법 교정이 아닌 3-레이어 검수 파이프라인:

  Layer 1 — 규칙 기반 필터 (RuleEngine)
    · 번역기 냄새 패턴 탐지  (e.g. "I hope this email finds you well")
    · 금기어/금기 표현 차단
    · 과장 클리셰 경고         (e.g. "revolutionary", "game-changing")
    · 글자 수 재검증

  Layer 2 — 현지 재거(Jargon) 라이브러리 (LocalJargonDB)
    · 10개국 × 직무별 실무 용어 사전
    · 번역투 → 현지 관용구 치환 매핑
    · 국가별 금기 표현 → 권장 대체 표현

  Layer 3 — Claude API 최종 다듬기 (AIPolisher)
    · 국가/직무 컨텍스트를 담은 시스템 프롬프트
    · 수정 이유를 JSON으로 함께 반환
    · 글자 수 제한을 프롬프트에 명시하여 초과 방지

출력 포맷
----------
ProofreadResult {
    original:      str              # 원본 텍스트
    polished:      str              # 최종 다듬어진 텍스트
    rule_issues:   List[RuleIssue]  # Layer 1 발견 이슈
    substitutions: List[Sub]        # Layer 2 치환 목록
    ai_rationale:  str              # Layer 3 AI 수정 이유
    quality_score: float            # 0.0–1.0 (높을수록 좋음)
    locale:        str              # 적용된 로케일 코드
}

사용법
------
from engine.agents.proofreader import ProofreaderAgent, Locale, Role

agent = ProofreaderAgent(api_key="sk-ant-...")

result = agent.proof(
    text       = "I am pleased to reach out regarding our solution...",
    locale     = Locale.JAPAN,
    role       = Role.VP_SALES,
    field_name = "email_body",
    char_limit = 1800,
)
print(result.polished)
print(result.quality_score)

# 또는 CopyDocument 전체 일괄 검수
from engine.agents.copywriter import CopyDocument
doc = agent.proof_document(copy_doc, locale=Locale.USA, role=Role.VP_SALES)
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════
# 1. 열거형
# ═══════════════════════════════════════════════════════════════════

class Locale(str, Enum):
    USA            = "usa"
    UK             = "uk"
    JAPAN          = "japan"
    KOREA          = "korea"
    CHINA          = "china"
    GERMANY        = "germany"
    SOUTHEAST_ASIA = "southeast_asia"
    INDIA          = "india"
    MIDDLE_EAST    = "middle_east"
    LATAM          = "latam"


class Role(str, Enum):
    CEO            = "ceo"
    CFO            = "cfo"
    CTO            = "cto"
    VP_SALES       = "vp_sales"
    VP_MARKETING   = "vp_marketing"
    VP_ENGINEERING = "vp_engineering"
    SALES_MANAGER  = "sales_manager"
    IT_MANAGER     = "it_manager"
    PROCUREMENT    = "procurement"
    DEVELOPER      = "developer"
    GENERIC        = "generic"


class IssueLevel(str, Enum):
    ERROR   = "error"    # 반드시 수정
    WARNING = "warning"  # 수정 권장
    INFO    = "info"     # 참고


# ═══════════════════════════════════════════════════════════════════
# 2. 데이터 모델
# ═══════════════════════════════════════════════════════════════════

@dataclass
class RuleIssue:
    """Layer 1 규칙 기반 탐지 이슈."""
    issue_id:    str = field(default_factory=lambda: uuid.uuid4().hex[:6])
    level:       IssueLevel = IssueLevel.WARNING
    category:    str = ""          # "cliche" | "taboo" | "too_formal" | "too_casual" | "char_limit"
    matched_text: str = ""         # 원문에서 탐지된 텍스트
    suggestion:  str = ""          # 권장 대체 표현
    reason:      str = ""          # 이유 한 줄


@dataclass
class Substitution:
    """Layer 2 재거 치환 기록."""
    original: str
    replaced: str
    jargon_type: str   # "power_phrase" | "local_idiom" | "taboo_fix"


@dataclass
class ProofreadResult:
    """최종 검수 결과."""
    result_id:     str   = field(default_factory=lambda: uuid.uuid4().hex[:8])
    original:      str   = ""
    polished:      str   = ""
    rule_issues:   List[RuleIssue]   = field(default_factory=list)
    substitutions: List[Substitution] = field(default_factory=list)
    ai_rationale:  str   = ""
    quality_score: float = 0.0        # 0.0 나쁨 → 1.0 최고
    locale:        str   = ""
    role:          str   = ""
    field_name:    str   = ""
    char_limit:    int   = 0
    char_count:    int   = 0
    char_ok:       bool  = True

    def to_dict(self) -> dict:
        return {
            "result_id":   self.result_id,
            "original":    self.original,
            "polished":    self.polished,
            "quality_score": self.quality_score,
            "char_ok":     self.char_ok,
            "char_count":  self.char_count,
            "char_limit":  self.char_limit,
            "locale":      self.locale,
            "role":        self.role,
            "field_name":  self.field_name,
            "issues": [
                {"level": i.level.value, "category": i.category,
                 "matched": i.matched_text, "suggestion": i.suggestion,
                 "reason": i.reason}
                for i in self.rule_issues
            ],
            "substitutions": [
                {"original": s.original, "replaced": s.replaced, "type": s.jargon_type}
                for s in self.substitutions
            ],
            "ai_rationale": self.ai_rationale,
        }


@dataclass
class DocumentProofResult:
    """CopyDocument 전체 검수 결과."""
    doc_id:          str = ""
    locale:          str = ""
    role:            str = ""
    field_results:   Dict[str, ProofreadResult] = field(default_factory=dict)
    total_issues:    int = 0
    avg_quality:     float = 0.0
    summary:         str = ""

    def to_dict(self) -> dict:
        return {
            "doc_id":       self.doc_id,
            "locale":       self.locale,
            "role":         self.role,
            "avg_quality":  self.avg_quality,
            "total_issues": self.total_issues,
            "summary":      self.summary,
            "fields":       {k: v.to_dict() for k, v in self.field_results.items()},
        }


# ═══════════════════════════════════════════════════════════════════
# 3. Layer 1 — 규칙 기반 RuleEngine
# ═══════════════════════════════════════════════════════════════════

# 번역기 냄새 패턴 (영문) — Error level
TRANSLATOR_SMELL_EN = [
    (r"I hope this (email|message|letter) finds you well",
     "Hope you're having a great week!", "classic spam opener — never use in sales"),
    (r"I am (writing|reaching out) to (inform|let you know)",
     "Here's something worth your attention:", "passive, weak opener"),
    (r"Please do not hesitate to (contact|reach out)",
     "Ping me anytime:", "too formal, un-American"),
    (r"I would like to (take this opportunity|express my)",
     "(cut entirely)", "filler phrase, adds zero value"),
    (r"kindly (review|note|advise|find attached)",
     "quick look at this:", "SEA/Indian translator cue in English context"),
    (r"as per (your|our|the)",
     "per", "bureaucratic; native speakers say 'per'"),
    (r"revert back to (me|us)",
     "get back to me", "'revert' ≠ 'reply' — common non-native error"),
    (r"do the needful",
     "take care of this", "only used in South Asian internal emails"),
    (r"at the earliest",
     "as soon as possible / ASAP", "Indian English — sounds odd elsewhere"),
    (r"please (find|see) (attached|enclosed) (herewith|herein)",
     "attached:", "overly legalistic"),
]

# 과장 클리셰 — Warning level
CLICHE_PATTERNS_EN = [
    (r"\b(revolutionary|game.?changing|disruptive|paradigm.?shift)\b",
     "specific metric or proof point", "empty superlative — prove it instead"),
    (r"\b(best.?in.?class|best in breed|world.?class)\b",
     "specific ranking or data", "everyone claims it; no one believes it"),
    (r"\b(seamless(ly)?|frictionless(ly)?)\b",
     "specific UX metric or outcome", "'seamless' = marketing vague"),
    (r"\b(leverage|leveraging)\b",
     "use / apply / build on", "MBA jargon, now parody-level overused"),
    (r"\b(synergy|synergies)\b",
     "shared value / combined impact", "extinct corporate speak"),
    (r"\b(empower(ing|s)?)\b",
     "enable / give your team", "'empower' has been weaponized by HR"),
    (r"\b(holistic(ally)?)\b",
     "end-to-end / comprehensive", "vague; means nothing specific"),
    (r"\b(cutting.?edge|state.?of.?the.?art)\b",
     "current-generation / latest", "every product says this"),
    (r"\b(thought leader(ship)?)\b",
     "industry expert / practitioner", "self-awarded credential"),
    (r"\b(pivot(ing)?)\b",
     "shift focus / realign", "overused since 2010 startup era"),
]

# 일본어 메일 번역투 패턴
TRANSLATOR_SMELL_JA = [
    (r"ご連絡をいただき誠にありがとうございます",
     "いつもお世話になっております。", "テンプレ感が強い。自社紹介から入ると自然"),
    (r"お忙しいところ恐れ入りますが",
     "簡潔にご案内させてください。", "前置きが長い。本題を先に"),
    (r"ご検討のほどよろしくお願い申し上げます",
     "ご都合のよい日時をお聞かせいただけますか？", "行動喚起が曖昧。具体的な次のステップを提示"),
    (r"取り急ぎ",
     "(削除)", "急いでいるのに連絡する矛盾。使わない方が誠実"),
]

# 한국어 번역투 패턴
TRANSLATOR_SMELL_KO = [
    (r"귀하의 건강과 행복을 빕니다",
     "안녕하세요, [이름]님.", "한국 비즈니스 메일에서 어색한 표현"),
    (r"본 메일을 통해",
     "(삭제 후 바로 본론)", "불필요한 서문"),
    (r"적극적인 검토 부탁드립니다",
     "다음 주 30분 미팅이 가능하실까요?", "행동 유도가 없음"),
    (r"귀사의 무궁한 발전을 기원합니다",
     "감사합니다.", "과도한 격식; 현대 비즈니스에서 어색"),
    (r"상기 내용 참조 바랍니다",
     "위 내용 확인 부탁드립니다.", "공문서 말투"),
]

# 독일어 번역투 패턴
TRANSLATOR_SMELL_DE = [
    (r"Sehr geehrte(r|s)? Damen und Herren",
     "Sehr geehrte/r [Name],", "익명 수신은 스팸처럼 보임. 반드시 이름 명시"),
    (r"Mit freundlichen Grüßen",
     "Beste Grüße / Mit besten Grüßen,", "형식적. 라포 형성 후엔 더 간결하게"),
    (r"Hiermit möchte ich",
     "(삭제, 바로 본론)", "불필요한 도입부"),
]


class RuleEngine:
    """텍스트에서 번역투·클리셰·금기어 패턴을 탐지하는 규칙 기반 엔진."""

    # 로케일별 패턴 매핑
    LOCALE_PATTERNS: Dict[str, List[Tuple]] = {
        Locale.JAPAN:  TRANSLATOR_SMELL_JA,
        Locale.KOREA:  TRANSLATOR_SMELL_KO,
        Locale.GERMANY: TRANSLATOR_SMELL_DE,
    }

    def run(self, text: str, locale: Locale) -> List[RuleIssue]:
        issues: List[RuleIssue] = []

        # 1. 영문 번역투 (영어권 + 비영어권 영문 이메일)
        for pattern, suggestion, reason in TRANSLATOR_SMELL_EN:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                issues.append(RuleIssue(
                    level=IssueLevel.ERROR, category="translator_smell",
                    matched_text=m.group(), suggestion=suggestion, reason=reason,
                ))

        # 2. 과장 클리셰 (영문)
        for pattern, suggestion, reason in CLICHE_PATTERNS_EN:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                issues.append(RuleIssue(
                    level=IssueLevel.WARNING, category="cliche",
                    matched_text=m.group(), suggestion=suggestion, reason=reason,
                ))

        # 3. 로케일별 현지어 패턴
        locale_patterns = self.LOCALE_PATTERNS.get(locale, [])
        for pattern, suggestion, reason in locale_patterns:
            m = re.search(pattern, text)
            if m:
                issues.append(RuleIssue(
                    level=IssueLevel.ERROR, category="locale_taboo",
                    matched_text=m.group(), suggestion=suggestion, reason=reason,
                ))

        return issues

    @staticmethod
    def score_from_issues(issues: List[RuleIssue]) -> float:
        """이슈 목록으로 품질 점수 계산 (1.0 = 완벽)."""
        deductions = sum(
            0.15 if i.level == IssueLevel.ERROR else
            0.07 if i.level == IssueLevel.WARNING else 0.02
            for i in issues
        )
        return max(0.0, round(1.0 - deductions, 2))


# ═══════════════════════════════════════════════════════════════════
# 4. Layer 2 — 현지 재거(Jargon) 라이브러리
# ═══════════════════════════════════════════════════════════════════

@dataclass
class JargonProfile:
    """특정 로케일 × 직무 조합의 재거 프로파일."""
    locale:          str
    role_hints:      List[str]     # 이 직무에서 선호하는 표현들
    power_phrases:   List[str]     # 미팅·제안서 오프닝에서 신뢰도를 높이는 파워 문구
    local_idioms:    Dict[str, str] # {번역투 표현: 현지 관용구}
    taboo_phrases:   List[str]     # 절대 쓰면 안 되는 표현
    email_openers:   List[str]     # 첫 문장 옵션들
    cta_phrases:     List[str]     # CTA 권장 문구
    sign_offs:       List[str]     # 마무리 인사


JARGON_DB: Dict[str, JargonProfile] = {

    # ── 미국 ──────────────────────────────────────────────────────
    "usa_vp_sales": JargonProfile(
        locale="usa", role_hints=["quota", "pipeline", "close rate", "AE", "SDR", "rev ops"],
        power_phrases=[
            "Here's the short version:", "Bottom line:", "Net-net:",
            "I'll cut to the chase —", "Two numbers worth your attention:",
            "What this means for Q3:", "We've seen this work for teams like yours.",
        ],
        local_idioms={
            "I am writing to inform you": "Quick heads-up:",
            "Please find attached": "Dropping this in:",
            "We would like to propose": "Here's what we're thinking:",
            "leverage our solution": "put our tool to work for you",
            "utilize": "use",
        },
        taboo_phrases=["I hope this email finds you well", "per my last email",
                       "circle back", "let's hop on a call", "reach out"],
        email_openers=[
            "Saw {company} just {trigger} — worth a 15-min conversation?",
            "Your competitor just {signal}. Here's how you can counter it.",
            "Real talk: most {role}s I speak with are losing 2–3 hrs/rep/day to manual research.",
            "{Name}, noticed {company}'s Q{n} push into {market} — I have a relevant data point.",
        ],
        cta_phrases=[
            "Worth a 15-min call this week?",
            "Open to a quick look — no pitch, just numbers.",
            "I can have a custom brief on your desk by Thursday.",
            "What does your calendar look like Wednesday afternoon?",
        ],
        sign_offs=["Best,", "Cheers,", "Talk soon,", "—{name}"],
    ),

    "usa_cfo": JargonProfile(
        locale="usa", role_hints=["EBITDA", "burn rate", "CAC", "LTV", "payback period", "TCO"],
        power_phrases=[
            "The math is straightforward:", "Payback in under 90 days.",
            "Here's the P&L impact:", "Run rate savings in year one:",
            "We've modeled this for your team size:", "Conservative case:",
            "The CFO at {reference} put it this way:",
        ],
        local_idioms={
            "investment": "spend", "implementation cost": "one-time setup",
            "return on investment": "payback", "cost savings": "savings to the bottom line",
        },
        taboo_phrases=["trust us", "believe me", "we think", "roughly", "approximately"],
        email_openers=[
            "{name}, teams your size typically recover their investment in 60–90 days. Here's the model.",
            "One number: $180K. That's the annual research cost your team is carrying. We can cut it by 75%.",
        ],
        cta_phrases=[
            "I can send the full ROI model — takes 5 minutes to validate.",
            "Want the CFO-ready summary? I'll have it in your inbox by 9am.",
        ],
        sign_offs=["Best,", "Regards,"],
    ),

    "usa_cto": JargonProfile(
        locale="usa", role_hints=["API", "latency", "uptime", "SLA", "stack", "infra", "DevOps"],
        power_phrases=[
            "One API call.", "Setup time: under 2 hours.", "Here's the architecture:",
            "We're SOC 2 Type II certified.", "No new infra. Plugs into your existing stack.",
            "Average p99 latency: 180ms.", "Your eng team doesn't touch it.",
        ],
        local_idioms={
            "easy to implement": "drops into your stack in an afternoon",
            "user-friendly": "your team will adopt it without a training session",
            "powerful features": "here's what it does under the hood",
        },
        taboo_phrases=["trust us on this", "industry-leading", "best-in-class",
                       "AI-powered magic", "revolutionary algorithm"],
        email_openers=[
            "Quick technical note on how we handle {concern} — you've probably thought about this.",
            "Three things your eng team will care about before approving this:",
        ],
        cta_phrases=["Open to a 30-min technical deep-dive?", "I can share the API docs now."],
        sign_offs=["Best,", "Cheers,", "—{name}"],
    ),

    # ── 일본 ──────────────────────────────────────────────────────
    "japan_generic": JargonProfile(
        locale="japan",
        role_hints=["稟議", "上長", "担当者", "御社", "弊社", "ご確認", "ご検討"],
        power_phrases=[
            "先日のお打ち合わせでお聞きした課題について、具体的なご提案をご用意いたしました。",
            "御社の {課題} に対して、実績のある解決策をご紹介させてください。",
            "類似の規模感のお客様では、{期間}で{成果}を実現されています。",
            "まずは小さなパイロットからお試しいただくことをご提案いたします。",
            "稟議資料としてそのままお使いいただけるサマリーを添付しております。",
        ],
        local_idioms={
            "I hope this email finds you well": "いつもお世話になっております。",
            "Please let me know": "ご不明な点がございましたら、お気軽にお知らせください。",
            "Would you be available": "ご都合のよい日時をお聞かせいただけますか？",
            "Attached please find": "添付のとおりご確認いただけますと幸いです。",
            "Best regards": "何卒よろしくお願い申し上げます。",
            "I look forward to hearing from you": "ご返信をお待ちしております。",
        },
        taboo_phrases=["urgent", "immediately", "ASAP", "quick decision",
                       "deadline", "now or never", "limited time offer"],
        email_openers=[
            "いつもお世話になっております。{会社名}の{名前}でございます。",
            "先日は貴重なお時間をいただき、誠にありがとうございました。",
            "御社の{課題}に関連して、ご参考になる情報をお届けしたく、ご連絡差し上げました。",
        ],
        cta_phrases=[
            "ご都合のよろしい日時に、30分ほどお時間をいただけますでしょうか。",
            "まずはオンラインで概要をご説明させていただければ幸いです。",
            "パイロット導入について、一度ご検討いただけますでしょうか。",
        ],
        sign_offs=[
            "何卒よろしくお願い申し上げます。",
            "引き続きどうぞよろしくお願いいたします。",
        ],
    ),

    # ── 한국 ──────────────────────────────────────────────────────
    "korea_generic": JargonProfile(
        locale="korea",
        role_hints=["KPI", "실적", "레퍼런스", "POC", "도입 사례", "검토"],
        power_phrases=[
            "{경쟁사/유사기업}에서도 이미 도입하여 활용 중입니다.",
            "국내 {산업} 기업 {N}개사에서 검증된 솔루션입니다.",
            "POC 2주 만에 효과를 체감하실 수 있습니다.",
            "도입 리스크 없이 시작할 수 있는 방법이 있습니다.",
            "{직책}님 보고용 1페이지 요약 자료를 별도로 준비해 드릴 수 있습니다.",
            "구체적인 수치로 증명된 성과입니다.",
        ],
        local_idioms={
            "I hope this email finds you well": "안녕하세요, {이름}님.",
            "Please review": "검토 부탁드립니다.",
            "Looking forward to your reply": "연락 주시면 감사하겠습니다.",
            "Best regards": "감사합니다.",
            "Kind regards": "감사합니다.",
            "Please do not hesitate": "편하게 연락 주세요.",
        },
        taboo_phrases=["실험적인", "베타 버전", "아직 검증 중", "테스트 중"],
        email_openers=[
            "안녕하세요, {이름}님. {회사명}의 {발신자}입니다.",
            "{유사 기업}에서 {결과}를 달성한 사례를 공유드리고자 연락드렸습니다.",
            "{회사명}의 {최근 소식}을 보고 연락드리게 됐습니다.",
        ],
        cta_phrases=[
            "다음 주 30분 미팅이 가능하실까요?",
            "POC 제안서를 보내드려도 될까요?",
            "편하신 시간에 간단히 통화 가능하실지요?",
        ],
        sign_offs=["감사합니다.", "수고하세요.", "좋은 하루 되세요."],
    ),

    # ── 독일 ──────────────────────────────────────────────────────
    "germany_generic": JargonProfile(
        locale="germany",
        role_hints=["ROI", "Effizienz", "Datensicherheit", "DSGVO", "Schnittstelle", "KPIs"],
        power_phrases=[
            "Die Zahlen sprechen für sich:",
            "Unabhängig geprüfte Ergebnisse zeigen:",
            "ISO 27001 zertifiziert — Datenschutz-konform nach DSGVO.",
            "Technische Spezifikation im Anhang:",
            "Drei messbare Kennzahlen, die für Ihre Situation relevant sind:",
            "Eine konservative Schätzung des ROI:",
        ],
        local_idioms={
            "Best regards": "Mit freundlichen Grüßen",
            "I hope you are well": "Ich hoffe, Sie hatten eine produktive Woche.",
            "revolutionary": "nachweislich effektiv",
            "game-changing": "signifikant effizienzsteigernd",
        },
        taboo_phrases=["Vertrauen Sie uns", "glauben Sie mir", "ungefähr", "wahrscheinlich"],
        email_openers=[
            "Sehr geehrte/r Herr/Frau {Nachname},",
            "im Anschluss an unsere Korrespondenz vom {Datum} möchte ich Ihnen folgende Informationen zukommen lassen:",
            "drei Datenpunkte, die für Ihre aktuelle Situation relevant sein könnten:",
        ],
        cta_phrases=[
            "Wären Sie für ein 30-minütiges technisches Gespräch verfügbar?",
            "Ich sende Ihnen gerne die vollständigen technischen Spezifikationen.",
            "Ein Pilotprojekt würde Ihnen ermöglichen, die Ergebnisse selbst zu validieren.",
        ],
        sign_offs=["Mit freundlichen Grüßen,", "Beste Grüße,"],
    ),

    # ── 동남아 ─────────────────────────────────────────────────────
    "southeast_asia_generic": JargonProfile(
        locale="southeast_asia",
        role_hints=["cost-effective", "ROI", "local support", "flexible", "pilot"],
        power_phrases=[
            "Here's how much your team can save:",
            "No hidden costs. No long-term lock-in.",
            "We have a local support team in {country}.",
            "Teams your size in {country} are seeing results in under 30 days.",
            "Start with a free pilot — no credit card required.",
            "We're flexible on pricing. Let's find what works for you.",
        ],
        local_idioms={
            "This is a limited time offer": "We're onboarding a small cohort this quarter.",
            "You must act now": "Teams are moving fast on this — happy to hold a spot.",
            "Best regards": "Warm regards,",
        },
        taboo_phrases=["non-negotiable", "take it or leave it", "standard price",
                       "we don't do discounts"],
        email_openers=[
            "Hi {Name}, hope you're doing well!",
            "{Name}, I came across {company}'s recent {signal} and thought this would be relevant.",
            "Quick share — {similar_company} in {country} just hit {result} using this approach.",
        ],
        cta_phrases=[
            "Want to hop on a quick call this week?",
            "Happy to run a free 2-week pilot for your team.",
            "Let me know what works — I'm flexible.",
        ],
        sign_offs=["Warm regards,", "Cheers,", "Best,"],
    ),

    # ── 중동 ──────────────────────────────────────────────────────
    "middle_east_generic": JargonProfile(
        locale="middle_east",
        role_hints=["strategic partnership", "long-term", "exclusive", "trusted"],
        power_phrases=[
            "We see this as the beginning of a long-term strategic partnership.",
            "Our relationship with {reference} speaks to the trust we build.",
            "An exclusive arrangement tailored for {company}.",
            "We are committed to your success — not just the transaction.",
            "This is designed specifically for your vision in the region.",
        ],
        local_idioms={
            "cheap": "cost-optimized",
            "discount": "preferred partner pricing",
            "quick deal": "an arrangement that works for both sides",
            "sign today": "when you're ready to move forward",
        },
        taboo_phrases=["cheap", "budget option", "quick deal", "limited time",
                       "sign today", "act now"],
        email_openers=[
            "It was a pleasure connecting at {event}. I wanted to follow up personally.",
            "{Name}, your leadership of {company} in this region is truly impressive.",
            "On behalf of our team, I wanted to share something we believe aligns with {company}'s vision.",
        ],
        cta_phrases=[
            "I'd love to arrange a proper meeting at your convenience.",
            "Would you be open to a conversation over coffee or lunch?",
            "We'd be honoured to host you and your team for a briefing.",
        ],
        sign_offs=["With warm regards,", "Respectfully,", "With highest regards,"],
    ),

    # ── 중남미 ─────────────────────────────────────────────────────
    "latam_generic": JargonProfile(
        locale="latam",
        role_hints=["crecimiento", "éxito", "confianza", "socio", "resultado"],
        power_phrases=[
            "Le cuento una historia que le va a resonar:",
            "Un cliente muy similar a ustedes logró {resultado} en {tiempo}.",
            "Esto no es un producto, es una alianza estratégica.",
            "Hablemos con confianza — aquí están los números reales:",
            "Su historia de éxito puede ser la próxima.",
        ],
        local_idioms={
            "Best regards": "Un cordial saludo,",
            "I hope this email finds you well": "Espero que todo esté yendo muy bien por allá.",
            "Please review": "Les comparto esto para su consideración:",
            "ROI": "retorno real", "leverage": "aprovechar al máximo",
        },
        taboo_phrases=["rigid terms", "non-negotiable", "standard contract only"],
        email_openers=[
            "Hola {nombre}, ¿cómo están? Quería compartirles algo que creo que les va a interesar.",
            "{Nombre}, vi que {empresa} está creciendo fuerte en {mercado} — tengo algo relevante para compartir.",
        ],
        cta_phrases=[
            "¿Podemos agendar una llamada de 20 minutos esta semana?",
            "Estaría encantado/a de tomar un café virtual para contarles más.",
        ],
        sign_offs=["Un cordial saludo,", "¡Hasta pronto!", "Con cariño,"],
    ),
}


def _get_jargon_profile(locale: Locale, role: Role) -> JargonProfile:
    """로케일 × 직무 조합으로 재거 프로파일 반환. 없으면 로케일 기본값 사용."""
    key_specific = f"{locale.value}_{role.value}"
    key_generic  = f"{locale.value}_generic"
    # 직무 특화 → 로케일 기본 → 영문 기본
    return (JARGON_DB.get(key_specific)
            or JARGON_DB.get(key_generic)
            or JARGON_DB.get("usa_vp_sales"))


class JargonEngine:
    """Layer 2: 재거 치환 엔진."""

    def apply(
        self,
        text: str,
        profile: JargonProfile,
    ) -> Tuple[str, List[Substitution]]:
        """번역투 → 현지 관용구 치환 후 (수정 텍스트, 치환 목록) 반환."""
        subs: List[Substitution] = []
        result = text

        for orig, repl in profile.local_idioms.items():
            if orig.lower() in result.lower():
                new_result = re.sub(re.escape(orig), repl, result, flags=re.IGNORECASE)
                if new_result != result:
                    subs.append(Substitution(orig, repl, "local_idiom"))
                    result = new_result

        return result, subs


# ═══════════════════════════════════════════════════════════════════
# 5. Layer 3 — Claude API 최종 다듬기
# ═══════════════════════════════════════════════════════════════════

# 로케일별 시스템 프롬프트 컨텍스트
LOCALE_SYSTEM_CONTEXT: Dict[str, str] = {
    "usa": (
        "You are a senior US B2B sales writer at a top SaaS company. "
        "Your emails sound like they were written by a sharp, confident American sales pro — "
        "direct, punchy, data-backed. Never start with 'I hope this email finds you well.' "
        "Use contractions. Vary sentence length. Sound human, not corporate."
    ),
    "uk": (
        "You are a senior UK B2B sales writer. Your tone is dry, understated, and witty — "
        "never brash or over-the-top American. Understate wins, let data do the shouting. "
        "Avoid: 'game-changing', 'revolutionary', 'amazing'. Prefer: 'rather impressive', "
        "'solid', 'practical'. Use British spellings."
    ),
    "japan": (
        "あなたは日本の大手SaaS企業でキャリアを積んだトップセールスです。"
        "ビジネスメールは丁寧語・敬語を適切に使い、相手への配慮を示しながらも"
        "ダラダラした前置きは省きます。稟議を意識した構成で、"
        "具体的な数字と実績を盛り込み、次のアクションを明確に提示してください。"
        "翻訳ソフトが生成したような不自然な敬語表現は使わないこと。"
    ),
    "korea": (
        "당신은 대한민국 최고의 B2B 세일즈 전문가입니다. "
        "이메일은 간결하고 직접적이되, 상대방 직급에 맞는 존댓말을 사용합니다. "
        "레퍼런스(국내 유사 기업 사례)와 구체적 수치를 반드시 포함하세요. "
        "'POC 제안', '리스크 없이 시작' 같은 실무 언어를 씁니다. "
        "공문서처럼 딱딱하지 않고, 실제 세일즈 미팅에서 쓸 법한 자연스러운 한국어로 작성하세요."
    ),
    "germany": (
        "Sie sind ein erfahrener B2B-Vertriebsprofi bei einem deutschen Technologieunternehmen. "
        "Ihre Texte sind präzise, faktenbasiert und respektieren deutsche Geschäftsetikette: "
        "Siezen, korrekte Anrede (Herr/Frau + Nachname), keine übertriebenen Superlative. "
        "Zahlen, Zertifizierungen und unabhängige Belege sind Ihre stärksten Argumente. "
        "Verzichten Sie auf amerikanischen Enthusiasmus — Seriosität schlägt Begeisterung."
    ),
    "southeast_asia": (
        "You are a seasoned B2B sales professional working across Southeast Asia (SG, MY, TH, ID, VN). "
        "Your tone is warm, relationship-first, and value-focused. Always lead with cost savings "
        "or quick ROI. Mention local support and flexibility. "
        "Avoid aggressive closing tactics — build trust first, offer a low-barrier pilot. "
        "Use inclusive, friendly English that works across mixed-proficiency audiences."
    ),
    "india": (
        "You are a top B2B sales professional in India. Your writing is polished, professional, "
        "and technically precise. You use Indian business English naturally — confident, "
        "relationship-aware, and value-focused. "
        "Avoid South Asian English quirks that non-natives use: 'do the needful', 'revert back', "
        "'kindly', 'at the earliest', 'prepone'. Use standard business English with warmth."
    ),
    "middle_east": (
        "You are a senior enterprise sales executive working in the GCC region (UAE, Saudi Arabia). "
        "Your writing reflects Arabic business culture: respectful, relationship-first, "
        "never transactional or pushy. Build prestige, trust, and long-term vision. "
        "Reference major references where possible. Tone: warm but formal, never casual. "
        "Avoid: 'cheap', 'discount', 'act now', 'limited time'."
    ),
    "latam": (
        "Eres un profesional de ventas B2B de alto nivel en América Latina. "
        "Tu escritura combina calidez humana con datos concretos. "
        "Siempre abre con una historia o un insight relevante antes de proponer. "
        "Usa el idioma del comprador — habla de 'socios', 'confianza', 'crecimiento juntos'. "
        "Evita términos demasiado formales o robóticos. Sé auténtico, no corporativo."
    ),
}

ROLE_ADDENDUM: Dict[str, str] = {
    "ceo":       "The reader is a CEO. Lead with strategic impact and competitive edge. Skip tactical details.",
    "cfo":       "The reader is a CFO. Every claim needs a dollar figure or percentage. ROI and payback period first.",
    "cto":       "The reader is a CTO. Lead with technical credibility, security, and integration simplicity.",
    "vp_sales":  "The reader is a VP Sales. Speak quota, pipeline, win rate, ramp time. They care about their number.",
    "vp_marketing": "The reader is a VP Marketing. Lead with MQL quality, attribution, and pipeline contribution.",
    "sales_manager": "The reader is a Sales Manager. Immediate team impact, easy adoption, fast results.",
    "it_manager":    "The reader is an IT Manager. Security, compliance, integration complexity, support SLA.",
    "procurement":   "The reader is Procurement. Total cost transparency, contract flexibility, vendor stability.",
    "developer":     "The reader is a Developer. API quality, docs, sandbox access. Let them try it, not hear about it.",
    "generic":       "Adapt the tone for a professional business reader.",
}


class AIPolisher:
    """Layer 3: Claude API로 최종 다듬기."""

    MODEL = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def polish(
        self,
        text: str,
        locale: Locale,
        role: Role,
        field_name: str,
        char_limit: int,
        rule_issues: List[RuleIssue],
        jargon_profile: JargonProfile,
    ) -> Tuple[str, str]:
        """
        텍스트를 Claude로 최종 다듬고 (polished_text, rationale) 반환.
        """
        try:
            import anthropic
        except ImportError:
            raise ImportError("pip install anthropic")

        # 시스템 프롬프트 조립
        locale_ctx  = LOCALE_SYSTEM_CONTEXT.get(locale.value, LOCALE_SYSTEM_CONTEXT["usa"])
        role_ctx    = ROLE_ADDENDUM.get(role.value, ROLE_ADDENDUM["generic"])
        power_sample = "\n".join(f"  · {p}" for p in jargon_profile.power_phrases[:4])
        taboos       = ", ".join(f'"{t}"' for t in jargon_profile.taboo_phrases[:5])
        issues_summary = (
            "\n".join(f"  [{i.level.value.upper()}] '{i.matched_text}' → {i.suggestion}"
                      for i in rule_issues[:5])
            if rule_issues else "  No rule issues detected."
        )

        system = f"""{locale_ctx}

ROLE CONTEXT: {role_ctx}

POWER PHRASES for this locale/role (weave naturally if appropriate):
{power_sample}

TABOO phrases — NEVER use: {taboos}

CHARACTER LIMIT: {char_limit if char_limit else 'none'} characters max. 
FIELD: {field_name}

RULE ENGINE flagged these issues you MUST fix:
{issues_summary}

OUTPUT FORMAT (JSON only, no markdown fences):
{{
  "polished": "<final text>",
  "rationale": "<2-3 sentences explaining key changes made>"
}}"""

        user = f"""Please proofread and polish the following {field_name} text.
Fix all flagged issues. Make it sound like it was written by a native {locale.value} sales professional.
Keep the meaning and length close to the original (within ±15%).

TEXT TO POLISH:
{text}"""

        client = anthropic.Anthropic(api_key=self._api_key)
        msg = client.messages.create(
            model=self.MODEL,
            max_tokens=1200,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = msg.content[0].text.strip()

        # JSON 파싱
        cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            # 폴백: 원문 반환
            return text, "AI polishing failed — original preserved."

        data = json.loads(match.group())
        return data.get("polished", text), data.get("rationale", "")


# ═══════════════════════════════════════════════════════════════════
# 6. ProofreaderAgent 메인 클래스
# ═══════════════════════════════════════════════════════════════════

class ProofreaderAgent:
    """
    현지인 수준 톤앤매너 검수 에이전트.

    Layer 1 → Layer 2 → Layer 3 순서로 파이프라인 실행.
    Layer 3 (Claude AI)은 api_key가 없으면 자동으로 스킵.

    사용법
    ------
    # API 없이 규칙 기반만 사용
    agent = ProofreaderAgent()
    result = agent.proof("Your revolutionary solution...", Locale.USA, Role.VP_SALES)

    # API 포함 풀 파이프라인
    agent = ProofreaderAgent(api_key="sk-ant-...")
    result = agent.proof(text, Locale.JAPAN, Role.VP_SALES, "email_body", char_limit=1800)

    # CopyDocument 전체 일괄 검수
    doc_result = agent.proof_document(copy_doc_dict, Locale.USA, Role.VP_SALES)
    """

    def __init__(self, api_key: Optional[str] = None):
        self._rule_engine   = RuleEngine()
        self._jargon_engine = JargonEngine()
        self._ai_polisher   = AIPolisher(api_key) if api_key else None

    # ── 단일 텍스트 검수 ─────────────────────────────────────────

    def proof(
        self,
        text:       str,
        locale:     Locale,
        role:       Role = Role.GENERIC,
        field_name: str  = "text",
        char_limit: int  = 0,
        skip_ai:    bool = False,
    ) -> ProofreadResult:
        """
        단일 텍스트를 3-레이어 파이프라인으로 검수합니다.

        Returns:
            ProofreadResult — 최종 다듬어진 텍스트 + 상세 보고서
        """
        if not text or not text.strip():
            return ProofreadResult(original=text, polished=text, locale=locale.value)

        profile = _get_jargon_profile(locale, role)

        # Layer 1: 규칙 기반 탐지
        issues = self._rule_engine.run(text, locale)
        base_score = self._rule_engine.score_from_issues(issues)

        # Layer 2: 재거 치환
        step2_text, subs = self._jargon_engine.apply(text, profile)

        # Layer 3: AI 다듬기 (선택)
        polished = step2_text
        rationale = ""
        if self._ai_polisher and not skip_ai:
            try:
                polished, rationale = self._ai_polisher.polish(
                    step2_text, locale, role, field_name, char_limit,
                    issues, profile,
                )
            except Exception as e:
                rationale = f"AI polishing skipped: {str(e)[:80]}"
                polished  = step2_text

        # 글자 수 검증
        char_count = len(polished)
        char_ok    = (char_limit == 0) or (char_count <= char_limit)
        if not char_ok:
            issues.append(RuleIssue(
                level=IssueLevel.ERROR, category="char_limit",
                matched_text=f"{char_count} chars",
                suggestion=f"≤ {char_limit} chars required",
                reason=f"Exceeds limit by {char_count - char_limit} chars",
            ))

        # 최종 점수 (AI 다듬기 이후 클리닉 이슈 재탐지)
        post_issues = self._rule_engine.run(polished, locale)
        final_score = max(base_score, self._rule_engine.score_from_issues(post_issues))
        if rationale and not post_issues:
            final_score = min(1.0, final_score + 0.05)  # AI 성공 보너스

        return ProofreadResult(
            original      = text,
            polished      = polished,
            rule_issues   = issues,
            substitutions = subs,
            ai_rationale  = rationale,
            quality_score = final_score,
            locale        = locale.value,
            role          = role.value,
            field_name    = field_name,
            char_limit    = char_limit,
            char_count    = char_count,
            char_ok       = char_ok,
        )

    # ── CopyDocument 전체 일괄 검수 ──────────────────────────────

    def proof_document(
        self,
        copy_doc: dict,
        locale:   Locale,
        role:     Role = Role.GENERIC,
        skip_ai:  bool = False,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> DocumentProofResult:
        """
        copywriter.py의 CopyDocument.to_dict() 출력 전체를 검수합니다.

        Args:
            copy_doc: CopyDocument.to_dict() 결과
            locale:   타겟 국가
            role:     바이어 직무
            skip_ai:  True이면 Layer 3 스킵 (빠르게)

        Returns:
            DocumentProofResult
        """
        def _prog(pct: float, msg: str):
            if on_progress:
                on_progress(pct, msg)

        result = DocumentProofResult(
            doc_id = copy_doc.get("meta", {}).get("doc_id", ""),
            locale = locale.value,
            role   = role.value,
        )

        fields_to_proof: List[Tuple[str, str, int]] = []  # (field_name, text, char_limit)

        # Email fields
        email = copy_doc.get("email", {})
        if email:
            from engine.agents.copywriter import EMAIL_LIMITS
            fields_to_proof += [
                ("email_subject",      email.get("subject",      ""), EMAIL_LIMITS["subject"]),
                ("email_preview_text", email.get("preview_text", ""), EMAIL_LIMITS["preview_text"]),
                ("email_body",         email.get("body",         ""), EMAIL_LIMITS["body"]),
                ("email_cta_line",     email.get("cta_line",     ""), EMAIL_LIMITS["cta_line"]),
                ("email_ps_line",      email.get("ps_line",      ""), EMAIL_LIMITS["ps_line"]),
            ]

        # Slide fields
        from engine.agents.copywriter import CHAR_LIMITS
        for slide in copy_doc.get("slides", []):
            stype = slide.get("type", "pain")
            lim   = CHAR_LIMITS.get(stype, {})
            num   = slide.get("slide_num", "?")
            fields_to_proof += [
                (f"slide{num}_headline",    slide.get("headline",    ""), lim.get("headline", 0)),
                (f"slide{num}_subheadline", slide.get("subheadline", ""), lim.get("subheadline", 0)),
                (f"slide{num}_body",        slide.get("body",        ""), lim.get("body", 0)),
            ]
            for i, b in enumerate(slide.get("bullets", [])):
                fields_to_proof.append((f"slide{num}_bullet{i}", b, lim.get("bullet", 0)))

        total = len(fields_to_proof)
        all_issues = 0
        scores = []

        for idx, (fname, text, climit) in enumerate(fields_to_proof):
            _prog(idx / total, f"검수 중: {fname}")
            if not text.strip():
                continue

            field_result = self.proof(
                text=text, locale=locale, role=role,
                field_name=fname, char_limit=climit, skip_ai=skip_ai,
            )
            result.field_results[fname] = field_result
            all_issues += len(field_result.rule_issues)
            scores.append(field_result.quality_score)

        result.total_issues = all_issues
        result.avg_quality  = round(sum(scores) / len(scores), 2) if scores else 0.0
        result.summary = self._build_summary(result, locale, role)
        _prog(1.0, "검수 완료")
        return result

    # ── 빠른 단일 필드 검수 (API 없이) ──────────────────────────

    def quick_check(self, text: str, locale: Locale, role: Role = Role.GENERIC) -> dict:
        """
        경량 검수 — Layer 1+2만 실행, 결과를 간단한 dict로 반환.
        API 키 없이도 즉시 사용 가능.
        """
        result = self.proof(text, locale, role, skip_ai=True)
        return {
            "score": result.quality_score,
            "issues": len(result.rule_issues),
            "errors": sum(1 for i in result.rule_issues if i.level == IssueLevel.ERROR),
            "warnings": sum(1 for i in result.rule_issues if i.level == IssueLevel.WARNING),
            "top_issue": result.rule_issues[0].reason if result.rule_issues else None,
            "polished": result.polished,
        }

    # ── 내부 헬퍼 ────────────────────────────────────────────────

    @staticmethod
    def _build_summary(result: DocumentProofResult, locale: Locale, role: Role) -> str:
        level = (
            "현지인 수준 (바로 발송 가능)" if result.avg_quality >= 0.90 else
            "양호 (소수 표현 개선 권장)"  if result.avg_quality >= 0.75 else
            "보통 (번역투 수정 필요)"      if result.avg_quality >= 0.55 else
            "개선 필요 (전반적 재작성 권장)"
        )
        return (
            f"【검수 결과 요약】 로케일: {locale.value.upper()} × 직무: {role.value}\n"
            f"품질 점수: {result.avg_quality:.0%}  |  {level}\n"
            f"발견된 이슈: {result.total_issues}건  |  검수 필드: {len(result.field_results)}개\n"
            f"주요 권고: {'이슈 없음 — 즉시 발송 가능' if result.total_issues == 0 else '상세 결과 field_results 참조'}"
        )

    @staticmethod
    def list_locales() -> List[dict]:
        return [{"key": l.value, "name": l.value.replace("_", " ").title()} for l in Locale]

    @staticmethod
    def list_roles() -> List[dict]:
        return [{"key": r.value, "name": r.value.replace("_", " ").title()} for r in Role]
