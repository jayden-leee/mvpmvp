"""
opener-ultra-mvp / engine / agents / strategist.py
====================================================
국가별·직무별 세일즈 프로토콜 엔진 — StrategistAgent

핵심 설계
---------
두 개의 독립 축(Axis)을 교차해 제안서 프로토콜을 결정합니다.

  Axis A — 국가 문화 프로파일 (CultureProfile)
    · 커뮤니케이션 스타일  : direct ↔ indirect
    · 의사결정 방식        : individual ↔ consensus
    · 신뢰 형성 방식       : task-based ↔ relationship-based
    · 리스크 감수도        : high ↔ low
    · 핵심 설득 동인       : ROI / 신뢰 / 가성비 / 혁신 / 체면 …

  Axis B — 담당자 직무 심리 프로파일 (RolePsychProfile)
    · 주요 KPI
    · 핵심 두려움 (Core Fear)
    · 구매 동기 프레임
    · 선호 메시지 포맷
    · 금기어

두 축이 교차하면 ProposalBlueprint가 생성됩니다.
Blueprint = 동적으로 조립된 제안서 목차 + 각 섹션의 톤·길이·증거 유형.

사용법
------
from engine.agents.strategist import StrategistAgent, Country, BuyerRole

agent = StrategistAgent()

blueprint = agent.build_blueprint(
    country      = Country.JAPAN,
    role         = BuyerRole.VP_SALES,
    product_name = "OpenerUltra",
    pain_signals = [...],          # researcher.py PainSignal 목록
    value_prop   = "...",
)
print(blueprint.to_markdown())
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════
# 1. 열거형 — 국가 & 직무
# ═══════════════════════════════════════════════════════════════════

class Country(str, Enum):
    USA            = "usa"
    JAPAN          = "japan"
    KOREA          = "korea"
    CHINA          = "china"
    GERMANY        = "germany"
    UK             = "uk"
    SOUTHEAST_ASIA = "southeast_asia"   # SG, TH, MY, ID, VN 묶음
    INDIA          = "india"
    MIDDLE_EAST    = "middle_east"      # UAE, SA 묶음
    LATAM          = "latam"            # BR, MX, CO 묶음


class BuyerRole(str, Enum):
    # C-Suite
    CEO            = "ceo"
    CFO            = "cfo"
    CTO            = "cto"
    COO            = "coo"
    # VP / 부문장
    VP_SALES       = "vp_sales"
    VP_MARKETING   = "vp_marketing"
    VP_ENGINEERING = "vp_engineering"
    VP_PRODUCT     = "vp_product"
    # 실무 Manager
    SALES_MANAGER  = "sales_manager"
    MARKETING_MANAGER = "marketing_manager"
    IT_MANAGER     = "it_manager"
    PROCUREMENT    = "procurement"      # 구매/조달
    # 실무 IC
    SALES_REP      = "sales_rep"
    DEVELOPER      = "developer"
    DATA_ANALYST   = "data_analyst"


class ProposalStyle(str, Enum):
    CONCLUSION_FIRST = "conclusion_first"   # 결론 → 근거 (미국식)
    TRUST_FIRST      = "trust_first"        # 신뢰 구축 → 제안 (일본식)
    VALUE_FIRST      = "value_first"        # 가성비 증명 → 도입 (동남아식)
    STORY_FIRST      = "story_first"        # 사례 스토리 → 적용 (중남미식)
    DATA_FIRST       = "data_first"         # 데이터/지표 → 논리 (독일식)
    RELATIONSHIP_FIRST = "relationship_first" # 관계 언급 → 제안 (중동식)
    HIERARCHY_FIRST  = "hierarchy_first"    # 권위·레퍼런스 → 제안 (중국식)
    RISK_FIRST       = "risk_first"         # 리스크 제거 증명 → 도입 (한국식)


# ═══════════════════════════════════════════════════════════════════
# 2. 문화 프로파일 DB
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CultureProfile:
    country:          Country
    display_name:     str
    flag:             str

    # 커뮤니케이션 특성
    communication:    str   # "direct" | "indirect" | "semi-direct"
    decision_style:   str   # "individual" | "consensus" | "hierarchical"
    trust_basis:      str   # "task" | "relationship" | "authority"
    risk_appetite:    str   # "high" | "medium" | "low"

    # 핵심 설득 동인 (우선순위 순)
    persuasion_drivers: List[str]

    # 제안서 스타일
    proposal_style:   ProposalStyle
    preferred_length: str   # "concise" | "moderate" | "thorough"

    # 언어·톤 가이드
    tone_keywords:    List[str]   # 사용 권장 표현
    taboo_keywords:   List[str]   # 절대 금기 표현

    # 미팅·이메일 프로토콜
    greeting_protocol: str
    email_subject_style: str
    meeting_opener:   str

    # 증거 선호도
    preferred_evidence: List[str]   # "case_study" | "data" | "testimonial" | "demo" | "authority"

    # 문화 인사이트 (한 문장 요약)
    insight:          str


CULTURE_DB: Dict[Country, CultureProfile] = {

    Country.USA: CultureProfile(
        country=Country.USA, display_name="미국", flag="🇺🇸",
        communication="direct", decision_style="individual",
        trust_basis="task", risk_appetite="high",
        persuasion_drivers=["ROI", "속도", "혁신", "경쟁 우위", "확장성"],
        proposal_style=ProposalStyle.CONCLUSION_FIRST,
        preferred_length="concise",
        tone_keywords=["game-changer", "ROI", "scale", "10x", "velocity",
                       "disrupt", "bottom line", "proven", "fast"],
        taboo_keywords=["may", "might consider", "in due course", "respectfully",
                        "if you don't mind"],
        greeting_protocol="이름(First Name) 직접 호칭. 바로 본론.",
        email_subject_style="[숫자] + 동사 + 결과: 'Cut CAC by 40% in 60 Days'",
        meeting_opener="'Let me cut to the chase—here's what we can do for you.'",
        preferred_evidence=["ROI 수치", "A/B 테스트 결과", "유사 고객 사례", "데모"],
        insight="결론을 먼저, 근거는 나중. 숫자가 설득한다."
    ),

    Country.JAPAN: CultureProfile(
        country=Country.JAPAN, display_name="일본", flag="🇯🇵",
        communication="indirect", decision_style="consensus",
        trust_basis="relationship", risk_appetite="low",
        persuasion_drivers=["신뢰", "안정성", "장기 파트너십", "리스크 회피", "체면"],
        proposal_style=ProposalStyle.TRUST_FIRST,
        preferred_length="thorough",
        tone_keywords=["안심", "신뢰", "실적", "안정적", "장기적",
                       "丁寧に", "ご安心", "実績", "信頼", "長期的"],
        taboo_keywords=["빨리", "즉시 결정", "limited time", "urgent", "aggressive"],
        greeting_protocol="성(Last Name) + 님/상. 명함 두 손으로. 회사 소개부터.",
        email_subject_style="회사명 + 제품명 + ご提案: '[OpenerUltra] セールス効率化のご提案'",
        meeting_opener="'弊社についてご説明させてください。まず信頼関係を築きたいと思います。'",
        preferred_evidence=["레퍼런스 기업 목록", "도입 사례집", "보증·인증서", "파일럿 제안"],
        insight="결론보다 관계가 먼저. 린지 과정(稟議)을 존중하고, 결정자보다 영향자를 설득하라."
    ),

    Country.KOREA: CultureProfile(
        country=Country.KOREA, display_name="한국", flag="🇰🇷",
        communication="semi-direct", decision_style="hierarchical",
        trust_basis="authority", risk_appetite="medium",
        persuasion_drivers=["리스크 제거", "레퍼런스", "경쟁사 도입 여부", "빠른 성과", "체면"],
        proposal_style=ProposalStyle.RISK_FIRST,
        preferred_length="moderate",
        tone_keywords=["검증된", "안전한", "레퍼런스", "빠른 도입", "경쟁사 대비",
                       "리스크 없는", "즉시 적용 가능"],
        taboo_keywords=["실험적", "검증 중", "베타", "아직 확인 안 됨"],
        greeting_protocol="직급 + 성함. 연차·직급 서열 확인. 결정권자 파악 필수.",
        email_subject_style="[긴급도 아닌 가치]: '[주요 레퍼런스사] 도입 사례 공유 드립니다'",
        meeting_opener="'저희가 비슷한 규모의 [경쟁사/레퍼런스]에서 어떤 성과를 냈는지 먼저 보여드리겠습니다.'",
        preferred_evidence=["국내 레퍼런스", "경쟁사 도입 사례", "ROI 수치", "POC 제안"],
        insight="'남들도 쓰는가'가 최강 설득 논리. 리스크 제거와 빠른 성과를 동시에 보여줘라."
    ),

    Country.CHINA: CultureProfile(
        country=Country.CHINA, display_name="중국", flag="🇨🇳",
        communication="indirect", decision_style="hierarchical",
        trust_basis="authority", risk_appetite="medium",
        persuasion_drivers=["체면(面子)", "권위 있는 레퍼런스", "관계(关系)", "가격", "규모"],
        proposal_style=ProposalStyle.HIERARCHY_FIRST,
        preferred_length="thorough",
        tone_keywords=["领先", "战略合作", "权威认证", "规模化", "面子",
                       "국가급", "선두", "전략 파트너십"],
        taboo_keywords=["소규모", "스타트업", "미검증", "작은 회사"],
        greeting_protocol="직급 명함 교환. 결정권자(最终决策人) 직접 접근 필수. 관계 형성에 투자.",
        email_subject_style="권위 레퍼런스 포함: '[Fortune 500 고객사] 전략 협력 제안'",
        meeting_opener="'我们与[권위있는 고객사]建立了战略合作关系…'",
        preferred_evidence=["권위 기관 인증", "글로벌 레퍼런스", "정부·대기업 도입 사례", "가격 경쟁력"],
        insight="체면과 관계가 계약보다 먼저다. 결정권자에게 직접 접근하고, 권위 있는 레퍼런스로 신뢰를 구축하라."
    ),

    Country.GERMANY: CultureProfile(
        country=Country.GERMANY, display_name="독일", flag="🇩🇪",
        communication="direct", decision_style="consensus",
        trust_basis="task", risk_appetite="low",
        persuasion_drivers=["기술적 우수성", "정밀성", "규정 준수", "장기 신뢰성", "데이터"],
        proposal_style=ProposalStyle.DATA_FIRST,
        preferred_length="thorough",
        tone_keywords=["präzise", "zuverlässig", "nachweislich", "Qualität",
                       "정밀한", "검증된", "데이터 기반", "규정 준수", "엔지니어링"],
        taboo_keywords=["빠른 결정", "대충", "개략적으로", "roughly", "approximately"],
        greeting_protocol="Herr/Frau + 성. 박사 학위 있으면 반드시 Dr. 포함. 시간 엄수.",
        email_subject_style="기능 명확화: 'Technische Spezifikation: OpenerUltra Integration'",
        meeting_opener="'Lassen Sie mich die technischen Details und Datenlage vorstellen.'",
        preferred_evidence=["기술 사양서", "독립 검증 데이터", "ISO/DIN 인증", "상세 케이스 스터디"],
        insight="감성이 아닌 논리로 설득하라. 데이터와 기술 사양이 신뢰의 증거다."
    ),

    Country.UK: CultureProfile(
        country=Country.UK, display_name="영국", flag="🇬🇧",
        communication="semi-direct", decision_style="individual",
        trust_basis="task", risk_appetite="medium",
        persuasion_drivers=["실용성", "유머·재치", "절제된 우수성", "ROI", "신사적 파트너십"],
        proposal_style=ProposalStyle.CONCLUSION_FIRST,
        preferred_length="moderate",
        tone_keywords=["rather impressive", "practical", "straightforward",
                       "solid", "proven track record", "sensible"],
        taboo_keywords=["amazing", "game-changing", "revolutionary", "crush",
                        "dominate", "kill", "disrupting"],
        greeting_protocol="적당한 격식체. 과장 금지. 영국식 절제된 유머 환영.",
        email_subject_style="절제된 명확성: 'A Thought on Improving Your Sales Pipeline'",
        meeting_opener="'I'll spare you the fanfare—here's what we've found works.'",
        preferred_evidence=["간결한 케이스 스터디", "업계 데이터", "ROI 계산서"],
        insight="과장은 신뢰를 죽인다. 절제된 자신감과 실용적 증거로 접근하라."
    ),

    Country.SOUTHEAST_ASIA: CultureProfile(
        country=Country.SOUTHEAST_ASIA, display_name="동남아시아", flag="🌏",
        communication="indirect", decision_style="consensus",
        trust_basis="relationship", risk_appetite="medium",
        persuasion_drivers=["가성비(Value for Money)", "관계", "현지화", "빠른 ROI", "유연성"],
        proposal_style=ProposalStyle.VALUE_FIRST,
        preferred_length="moderate",
        tone_keywords=["cost-effective", "flexible", "local support", "quick win",
                       "최적 가격", "현지 지원", "빠른 효과", "맞춤형"],
        taboo_keywords=["premium only", "no discount", "standard price", "take it or leave it"],
        greeting_protocol="관계 형성 먼저(Small talk). 공손한 어조. 현지어 인사 포함 시 호감 상승.",
        email_subject_style="가치 명시: 'How [Company] Can Save 40% with OpenerUltra'",
        meeting_opener="'Before we get into details, I'd love to understand your team's goals.'",
        preferred_evidence=["가격 비교표", "ROI 계산기", "현지 성공 사례", "무료 파일럿"],
        insight="가격 대비 가치가 핵심. 현지화된 지원과 유연한 조건이 계약을 만든다."
    ),

    Country.INDIA: CultureProfile(
        country=Country.INDIA, display_name="인도", flag="🇮🇳",
        communication="indirect", decision_style="hierarchical",
        trust_basis="relationship", risk_appetite="medium",
        persuasion_drivers=["가성비", "관계", "기술적 깊이", "확장성", "명성"],
        proposal_style=ProposalStyle.VALUE_FIRST,
        preferred_length="thorough",
        tone_keywords=["value", "scalable", "robust", "trusted partner",
                       "world-class", "proven", "cost-effective", "reliable"],
        taboo_keywords=["expensive", "premium pricing", "non-negotiable", "rigid"],
        greeting_protocol="Namaste 또는 Sir/Ma'am. 관계 구축에 시간 투자. 결정권자 파악 필수.",
        email_subject_style="가치 + 스케일: 'Enterprise-Grade Sales Intelligence at Startup Prices'",
        meeting_opener="'We've been following [company]'s impressive growth. Let me share how we've helped similar companies scale.'",
        preferred_evidence=["글로벌 레퍼런스", "기술 상세 문서", "가격 유연성", "ROI 계산"],
        insight="기술적 깊이와 가격 유연성을 동시에 준비하라. 결정은 느리지만 한번 신뢰하면 장기 파트너가 된다."
    ),

    Country.MIDDLE_EAST: CultureProfile(
        country=Country.MIDDLE_EAST, display_name="중동", flag="🌙",
        communication="indirect", decision_style="hierarchical",
        trust_basis="relationship", risk_appetite="medium",
        persuasion_drivers=["관계(Wasta)", "체면", "독점적 파트너십", "권위", "장기 신뢰"],
        proposal_style=ProposalStyle.RELATIONSHIP_FIRST,
        preferred_length="moderate",
        tone_keywords=["exclusive partner", "long-term vision", "trusted ally",
                       "prestigious", "strategic", "honor", "신뢰", "독점", "전략적"],
        taboo_keywords=["cheap", "discount", "budget option", "quick deal"],
        greeting_protocol="인샬라/마샬라 존중. 종교·문화 존중 필수. 결정권자(Sheik급) 직접 접근 선호.",
        email_subject_style="파트너십 프레임: 'Exclusive Strategic Partnership Proposal for [Company]'",
        meeting_opener="'It's an honor to meet with [company]. We see this as the beginning of a long-term strategic partnership.'",
        preferred_evidence=["독점 파트너십 제안", "글로벌 권위 레퍼런스", "장기 계약 옵션"],
        insight="관계가 계약보다 중요하다. 첫 미팅에서 팔려 하지 말고, 파트너가 되려 하라."
    ),

    Country.LATAM: CultureProfile(
        country=Country.LATAM, display_name="중남미", flag="🌎",
        communication="indirect", decision_style="individual",
        trust_basis="relationship", risk_appetite="high",
        persuasion_drivers=["관계(Simpatía)", "열정적 스토리", "빠른 ROI", "현지화", "유연성"],
        proposal_style=ProposalStyle.STORY_FIRST,
        preferred_length="moderate",
        tone_keywords=["pasión", "confianza", "éxito", "crecimiento", "asociación",
                       "성공 스토리", "파트너", "성장", "신뢰"],
        taboo_keywords=["rigid terms", "no flexibility", "standard package only", "formal only"],
        greeting_protocol="악수 + 허그(가까운 사이). 개인 안부 먼저. 관계·감정 중시.",
        email_subject_style="스토리 티저: 'How [Similar Company] Grew 3x—Your Story Could Be Next'",
        meeting_opener="'Let me tell you about a company just like yours that transformed their sales…'",
        preferred_evidence=["감성적 성공 스토리", "현지 고객 사례", "ROI 수치", "유연한 조건"],
        insight="스토리로 감동시키고, 관계로 계약한다. 열정과 유연성이 논리보다 강하다."
    ),
}


# ═══════════════════════════════════════════════════════════════════
# 3. 직무(Role) 심리 프로파일 DB
# ═══════════════════════════════════════════════════════════════════

@dataclass
class RolePsychProfile:
    role:              BuyerRole
    display_name:      str
    level:             str   # "c_suite" | "vp" | "manager" | "ic"

    # 핵심 KPI (이 사람이 평가받는 지표)
    core_kpis:         List[str]

    # 핵심 두려움 (Core Fear) — 가장 강력한 설득 레버
    core_fear:         str

    # 구매 동기 프레임
    buying_motivation: str   # "strategic" | "operational" | "political" | "technical"

    # 이 사람이 제안서에서 가장 먼저 보는 것
    first_attention:   str

    # 선호 메시지 포맷
    preferred_format:  List[str]

    # 금기 접근법
    taboo_approach:    str

    # 의사결정 속도
    decision_speed:    str   # "fast" | "medium" | "slow"

    # 심리 인사이트
    psych_insight:     str

    # 제안서에서 반드시 포함해야 할 요소
    must_include:      List[str]

    # 절대 포함하지 말아야 할 요소
    must_exclude:      List[str]


ROLE_DB: Dict[BuyerRole, RolePsychProfile] = {

    BuyerRole.CEO: RolePsychProfile(
        role=BuyerRole.CEO, display_name="CEO / 대표이사", level="c_suite",
        core_kpis=["매출 성장", "시장 점유율", "기업 가치(Valuation)", "투자자 신뢰"],
        core_fear="경쟁에서 뒤처지는 것. 잘못된 큰 베팅.",
        buying_motivation="strategic",
        first_attention="이게 회사의 방향과 맞는가? 경쟁 우위가 되는가?",
        preferred_format=["1-page Executive Summary", "3분 피치", "비전 스토리"],
        taboo_approach="운영 세부사항·기술 스펙으로 시작하는 것. 시간 낭비 느낌 주기.",
        decision_speed="fast",
        psych_insight="전략적 비전과 경쟁 우위에 반응한다. ROI보다 '이걸 안 하면 뒤처진다'는 FOMO가 더 강하다.",
        must_include=["경쟁 포지셔닝", "시장 기회 규모", "3-5년 비전 연계", "빠른 의사결정 경로"],
        must_exclude=["기술 아키텍처 다이어그램", "구현 세부 단계", "과도한 데이터 표"],
    ),

    BuyerRole.CFO: RolePsychProfile(
        role=BuyerRole.CFO, display_name="CFO / 최고재무책임자", level="c_suite",
        core_kpis=["EBITDA", "CAC·LTV 비율", "현금 흐름", "비용 절감", "투자 회수"],
        core_fear="ROI 없는 지출. 감사에서 설명 못 할 투자.",
        buying_motivation="operational",
        first_attention="Total Cost of Ownership. 언제 손익분기점을 넘는가.",
        preferred_format=["ROI 계산서", "TCO 비교표", "3년 재무 시뮬레이션"],
        taboo_approach="감성 스토리로만 접근. 숫자 없는 주장.",
        decision_speed="slow",
        psych_insight="모든 것을 숫자로 말하라. '비용 절감 X%'보다 '연간 Y억 원 절감'이 훨씬 강하다.",
        must_include=["상세 ROI 계산", "TCO 분석", "리스크 비용화", "계약 유연성 옵션"],
        must_exclude=["기능 목록", "디자인 요소 강조", "검증되지 않은 수치"],
    ),

    BuyerRole.CTO: RolePsychProfile(
        role=BuyerRole.CTO, display_name="CTO / 최고기술책임자", level="c_suite",
        core_kpis=["시스템 안정성", "개발 속도", "기술 부채", "보안·컴플라이언스", "팀 생산성"],
        core_fear="도입 후 기술 부채 증가. 보안 사고. 팀의 반발.",
        buying_motivation="technical",
        first_attention="기술 아키텍처. 기존 스택과의 통합 난이도. 보안.",
        preferred_format=["기술 아키텍처 다이어그램", "API 문서", "보안 화이트페이퍼"],
        taboo_approach="기술 질문에 불명확한 답변. '나중에 확인해 드릴게요.'",
        decision_speed="medium",
        psych_insight="기술적 깊이로 신뢰를 쌓아라. 통합 복잡도와 보안을 먼저 해결해 주면 챔피언이 된다.",
        must_include=["통합 아키텍처", "보안·컴플라이언스 문서", "SLA/Uptime", "마이그레이션 가이드"],
        must_exclude=["비즈니스 지표만", "기술 근거 없는 주장", "모호한 로드맵"],
    ),

    BuyerRole.VP_SALES: RolePsychProfile(
        role=BuyerRole.VP_SALES, display_name="VP Sales / 영업 부문장", level="vp",
        core_kpis=["파이프라인 규모", "쿼터 달성률", "세일즈 사이클 단축", "Win Rate", "팀 생산성"],
        core_fear="쿼터 미달. 팀 이탈. 경영진 앞에서의 실적 부진.",
        buying_motivation="operational",
        first_attention="이걸 도입하면 팀의 쿼터 달성률이 올라가는가?",
        preferred_format=["Before/After 지표 비교", "팀 적용 시나리오", "90일 성과 타임라인"],
        taboo_approach="팀 부담 증가처럼 보이게 하는 것. '추가 학습 필요'를 강조.",
        decision_speed="fast",
        psych_insight="개인 쿼터와 팀 성과에 직결되면 즉시 움직인다. '팀의 생산성'보다 '당신의 쿼터'로 말하라.",
        must_include=["쿼터 달성 임팩트", "팀 적용 용이성", "경쟁사 사용 여부", "빠른 POC"],
        must_exclude=["장기 구현 로드맵", "IT 승인 필요 강조", "복잡한 온보딩 절차"],
    ),

    BuyerRole.VP_MARKETING: RolePsychProfile(
        role=BuyerRole.VP_MARKETING, display_name="VP Marketing / 마케팅 부문장", level="vp",
        core_kpis=["MQL/SQL 전환율", "CAC", "브랜드 인지도", "콘텐츠 성과", "파이프라인 기여"],
        core_fear="세일즈팀에게 리드 품질 지적받는 것. 예산 정당화 실패.",
        buying_motivation="strategic",
        first_attention="세일즈 팀과의 정렬. 리드 품질 향상. 어트리뷰션.",
        preferred_format=["퍼널 임팩트 다이어그램", "캠페인 적용 사례", "ROI 어트리뷰션"],
        taboo_approach="기술적 구현에만 집중. 세일즈 도구처럼만 포지셔닝.",
        decision_speed="medium",
        psych_insight="'마케팅-세일즈 정렬'이라는 단어가 특효약이다. 마케팅이 세일즈 성과에 기여한다는 스토리를 주어라.",
        must_include=["리드 품질 향상 사례", "어트리뷰션 기능", "마케팅-세일즈 정렬", "콘텐츠 ROI"],
        must_exclude=["순수 영업 효율 지표만", "마케팅 역할 축소처럼 보이는 내용"],
    ),

    BuyerRole.VP_ENGINEERING: RolePsychProfile(
        role=BuyerRole.VP_ENGINEERING, display_name="VP Engineering / 개발 부문장", level="vp",
        core_kpis=["개발 속도", "배포 빈도", "버그율", "팀 번아웃", "기술 부채"],
        core_fear="운영 장애. 팀 과부하. 기술 부채 폭발.",
        buying_motivation="technical",
        first_attention="이게 팀의 부담을 줄이는가, 늘리는가.",
        preferred_format=["통합 복잡도 평가", "운영 오버헤드 분석", "팀 적용 사례"],
        taboo_approach="팀이 추가로 배워야 할 것을 강조. 마이그레이션 복잡도 과소평가.",
        decision_speed="medium",
        psych_insight="개발팀의 짐을 덜어주는 도구로 포지셔닝하라. 팀 자율성을 높여주는 것이 핵심 메시지.",
        must_include=["통합 용이성", "운영 오버헤드 최소화", "팀 생산성 지표", "마이그레이션 가이드"],
        must_exclude=["비즈니스 KPI만 강조", "기술 부채 없는 완벽한 주장"],
    ),

    BuyerRole.SALES_MANAGER: RolePsychProfile(
        role=BuyerRole.SALES_MANAGER, display_name="세일즈 매니저", level="manager",
        core_kpis=["팀 쿼터 달성", "파이프라인 관리", "신규 영업 건수", "팀원 코칭"],
        core_fear="팀 쿼터 미달로 인한 윗선 압박. 팀원 이탈.",
        buying_motivation="operational",
        first_attention="바로 현장에서 쓸 수 있는가? 팀 교육 부담은?",
        preferred_format=["현장 적용 시나리오", "빠른 온보딩 가이드", "팀 KPI 개선 수치"],
        taboo_approach="복잡한 설정 강조. IT 승인 필요 강조.",
        decision_speed="fast",
        psych_insight="현장 실무자이자 팀 책임자. 빠른 적용과 즉각적인 팀 성과가 핵심.",
        must_include=["즉시 적용 가능성", "팀 온보딩 시간", "현장 KPI 임팩트", "경쟁사 팀 사용 현황"],
        must_exclude=["장기 구현 계획", "고위 경영진 레벨 논의"],
    ),

    BuyerRole.IT_MANAGER: RolePsychProfile(
        role=BuyerRole.IT_MANAGER, display_name="IT 매니저", level="manager",
        core_kpis=["시스템 안정성", "보안 사고 제로", "사용자 만족도", "비용 효율"],
        core_fear="보안 사고. 시스템 다운. 감사 지적.",
        buying_motivation="technical",
        first_attention="보안 인증. 기존 시스템 호환성. 지원 체계.",
        preferred_format=["보안 체크리스트", "통합 사양서", "SLA 문서"],
        taboo_approach="보안 질문에 두루뭉술한 답변. 지원 부재 인상.",
        decision_speed="slow",
        psych_insight="'아무 일도 일어나지 않는 것'이 성공. 리스크 제거 언어로 말하라.",
        must_include=["보안 인증 목록", "기존 시스템 통합 사양", "24/7 지원 플랜", "컴플라이언스 준수"],
        must_exclude=["비즈니스 ROI 강조", "기술 근거 없는 약속"],
    ),

    BuyerRole.PROCUREMENT: RolePsychProfile(
        role=BuyerRole.PROCUREMENT, display_name="구매/조달 담당자", level="manager",
        core_kpis=["비용 절감", "벤더 리스크 관리", "계약 조건 최적화", "내부 프로세스 준수"],
        core_fear="비싼 가격에 계약. 내부 감사 지적. 벤더 리스크.",
        buying_motivation="operational",
        first_attention="가격. 계약 조건. 벤더 안정성.",
        preferred_format=["가격 비교표", "계약 조건 요약", "벤더 레퍼런스 목록"],
        taboo_approach="가격 투명성 부족. 숨겨진 비용. 경직된 계약 조건.",
        decision_speed="slow",
        psych_insight="경쟁사 가격보다 '이게 최선임'을 증명하라. 계약 유연성이 결정을 가속한다.",
        must_include=["총 비용 명세", "계약 유연성", "벤더 안정성 증명", "해지 조건"],
        must_exclude=["기능 자랑", "기술 용어", "모호한 가격 구조"],
    ),

    BuyerRole.DEVELOPER: RolePsychProfile(
        role=BuyerRole.DEVELOPER, display_name="개발자", level="ic",
        core_kpis=["개발 생산성", "코드 품질", "기술 부채 최소화", "도구 만족도"],
        core_fear="쓰기 불편한 도구 강제 도입. 기술 부채 증가.",
        buying_motivation="technical",
        first_attention="API 품질. 문서화 수준. 커뮤니티.",
        preferred_format=["API 문서", "코드 예시", "GitHub 스타/활동"],
        taboo_approach="영업 언어로 접근. 기술 질문에 비기술적 답변.",
        decision_speed="fast",
        psych_insight="개발자는 스스로 평가한다. 문서와 코드 품질이 피치보다 강하다. '해보세요'가 최강 영업.",
        must_include=["API 문서 링크", "샌드박스 접근 권한", "코드 예시", "개발자 커뮤니티"],
        must_exclude=["비기술적 마케팅 언어", "기능 이름만 나열", "강제 영업 느낌"],
    ),

    BuyerRole.DATA_ANALYST: RolePsychProfile(
        role=BuyerRole.DATA_ANALYST, display_name="데이터 분석가", level="ic",
        core_kpis=["데이터 정확도", "분석 속도", "인사이트 품질", "보고서 효율"],
        core_fear="잘못된 데이터로 의사결정 오류. 도구 학습 비용 과다.",
        buying_motivation="technical",
        first_attention="데이터 신뢰성. 분석 자유도. 통합 용이성.",
        preferred_format=["데이터 플로우 다이어그램", "분석 예시", "정확도 지표"],
        taboo_approach="데이터 정확도 질문 회피. 블랙박스 알고리즘 강조.",
        decision_speed="medium",
        psych_insight="데이터 품질과 투명성으로 신뢰를 쌓아라. 분석의 자유도를 제한하는 느낌을 주지 마라.",
        must_include=["데이터 소스 투명성", "정확도 검증 방법", "커스텀 분석 가능성", "API 접근"],
        must_exclude=["데이터 제한 조건 은폐", "블랙박스 설명"],
    ),
}


# ═══════════════════════════════════════════════════════════════════
# 4. 제안서 섹션 & 블루프린트
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ProposalSection:
    """제안서의 단일 섹션."""
    order:       int
    title:       str
    purpose:     str           # 이 섹션의 설득 목적
    tone:        str           # 권장 톤
    length:      str           # "short" | "medium" | "long"
    evidence_type: List[str]   # 사용할 증거 유형
    key_message: str           # 이 섹션의 핵심 한 문장
    writing_tip: str           # 작성 팁
    required:    bool = True


@dataclass
class ProposalBlueprint:
    """동적 생성된 제안서 프로토콜 전체."""
    blueprint_id:    str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    country:         Country = Country.USA
    role:            BuyerRole = BuyerRole.VP_SALES
    product_name:    str = ""
    proposal_style:  ProposalStyle = ProposalStyle.CONCLUSION_FIRST

    culture_profile: Optional[CultureProfile] = None
    role_profile:    Optional[RolePsychProfile] = None

    sections:        List[ProposalSection] = field(default_factory=list)

    # 합성 인사이트
    opening_hook:    str = ""   # 첫 문장 가이드
    closing_cta:     str = ""   # 마무리 CTA
    tone_guide:      str = ""   # 전체 톤 한 줄 가이드
    do_list:         List[str] = field(default_factory=list)
    dont_list:       List[str] = field(default_factory=list)
    cultural_tips:   List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        c = self.culture_profile
        r = self.role_profile
        lines = [
            f"# 제안서 프로토콜: {c.flag if c else ''} {self.country.value.upper()} × {r.display_name if r else self.role.value}",
            f"**스타일**: {self.proposal_style.value}  |  **제품**: {self.product_name}",
            "",
            f"## 🎯 핵심 인사이트",
            f"- **문화**: {c.insight if c else '—'}",
            f"- **심리**: {r.psych_insight if r else '—'}",
            f"- **첫 문장 가이드**: {self.opening_hook}",
            "",
            f"## 📋 제안서 목차",
        ]
        for s in self.sections:
            req = "" if s.required else " *(선택)*"
            lines.append(f"\n### {s.order}. {s.title}{req}")
            lines.append(f"- **목적**: {s.purpose}")
            lines.append(f"- **톤**: {s.tone} | **길이**: {s.length}")
            lines.append(f"- **핵심 메시지**: {s.key_message}")
            lines.append(f"- **사용 증거**: {', '.join(s.evidence_type)}")
            lines.append(f"- **작성 팁**: {s.writing_tip}")

        lines += [
            "",
            "## ✅ DO",
            *[f"- {d}" for d in self.do_list],
            "",
            "## ❌ DON'T",
            *[f"- {d}" for d in self.dont_list],
            "",
            "## 🌏 문화 팁",
            *[f"- {t}" for t in self.cultural_tips],
            "",
            f"## 📞 마무리 CTA",
            self.closing_cta,
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "blueprint_id":  self.blueprint_id,
            "country":       self.country.value,
            "role":          self.role.value,
            "product_name":  self.product_name,
            "proposal_style":self.proposal_style.value,
            "opening_hook":  self.opening_hook,
            "closing_cta":   self.closing_cta,
            "tone_guide":    self.tone_guide,
            "do_list":       self.do_list,
            "dont_list":     self.dont_list,
            "cultural_tips": self.cultural_tips,
            "sections": [
                {
                    "order":        s.order,
                    "title":        s.title,
                    "purpose":      s.purpose,
                    "tone":         s.tone,
                    "length":       s.length,
                    "key_message":  s.key_message,
                    "evidence_type":s.evidence_type,
                    "writing_tip":  s.writing_tip,
                    "required":     s.required,
                }
                for s in self.sections
            ],
            "culture_insight": self.culture_profile.insight if self.culture_profile else "",
            "role_insight":    self.role_profile.psych_insight if self.role_profile else "",
        }


# ═══════════════════════════════════════════════════════════════════
# 5. 섹션 어셈블러 — 스타일별 목차 동적 생성
# ═══════════════════════════════════════════════════════════════════

class SectionAssembler:
    """
    ProposalStyle + RolePsychProfile + CultureProfile을 조합해
    ProposalSection 목록을 동적으로 조립합니다.
    """

    def assemble(
        self,
        style:   ProposalStyle,
        culture: CultureProfile,
        role:    RolePsychProfile,
        product: str,
        pain_signals: Optional[List[str]] = None,
    ) -> List[ProposalSection]:

        # 스타일별 기본 목차 프레임
        frame = self._get_frame(style, product)

        # 직무별 섹션 커스터마이징
        frame = self._apply_role_customization(frame, role, product)

        # 문화별 섹션 커스터마이징
        frame = self._apply_culture_customization(frame, culture)

        return frame

    # ── 스타일별 기본 프레임 ─────────────────────────────────

    def _get_frame(self, style: ProposalStyle, product: str) -> List[ProposalSection]:

        if style == ProposalStyle.CONCLUSION_FIRST:
            return [
                ProposalSection(1, "Executive Summary", "결론을 3문장 안에 전달", "bold·direct", "short",
                    ["ROI 수치", "경쟁 우위"], f"{product}가 제공하는 비즈니스 임팩트 한 줄 요약",
                    "숫자로 시작하라. 'X% 성장, Y일 안에'"),
                ProposalSection(2, "The Problem We Solve", "바이어의 현재 페인포인트 공감", "empathetic", "short",
                    ["업계 데이터", "바이어 사례"], "지금 겪고 있는 이 문제, 우리가 안다",
                    "바이어의 언어로 문제를 정의하라. 그들이 고개를 끄덕이게"),
                ProposalSection(3, "Our Solution + Proof", "제품 기능 + 증거", "confident", "medium",
                    ["데모", "케이스 스터디", "A/B 테스트"], "이게 작동한다는 증거",
                    "기능 나열 금지. 결과(Outcome)로 말하라"),
                ProposalSection(4, "ROI & Business Case", "재무적 근거", "analytical", "medium",
                    ["ROI 계산서", "비교표"], "도입 안 하는 것이 더 비싸다",
                    "구체적인 숫자. 고객사 수치 활용"),
                ProposalSection(5, "Implementation Plan", "실행 가능성 증명", "practical", "short",
                    ["타임라인", "온보딩 가이드"], "빠르고 쉽게 시작할 수 있다",
                    "3단계 이하로 단순화. '90일 안에'"),
                ProposalSection(6, "Next Steps", "명확한 CTA", "direct", "short",
                    ["캘린더 링크", "파일럿 제안"], "지금 결정해야 할 이유",
                    "하나의 명확한 행동만 요청하라", True),
            ]

        elif style == ProposalStyle.TRUST_FIRST:
            return [
                ProposalSection(1, "会社紹介 · 회사 신뢰도", "파트너로서의 신뢰 구축", "formal·humble", "medium",
                    ["회사 연혁", "수상 이력", "인증서"], "저희는 이런 회사입니다—함께할 자격이 있습니다",
                    "과장하지 말고 실적을 나열하라. 겸손하되 자신감 있게"),
                ProposalSection(2, "お客様の現状理解 · 현황 이해", "바이어의 상황 깊이 이해하고 있음 증명", "attentive", "medium",
                    ["업계 리포트", "사전 리서치 결과"], "귀사의 상황을 깊이 공부했습니다",
                    "일반론 금지. 이 회사만을 위한 내용으로"),
                ProposalSection(3, "課題と解決策 · 과제와 해결책", "문제-해결 매핑", "collaborative", "medium",
                    ["유사 기업 사례", "데이터"], "함께 이 문제를 해결하고 싶습니다",
                    "제안이 아닌 '함께'의 언어를 사용하라"),
                ProposalSection(4, "導入実績 · 도입 실적", "레퍼런스로 신뢰 강화", "factual", "long",
                    ["고객사 목록", "사례집", "사용 후기"], "이미 검증된 솔루션입니다",
                    "일본/아시아 레퍼런스 우선. 숫자보다 스토리"),
                ProposalSection(5, "サポート体制 · 지원 체계", "도입 후 안심 보장", "reassuring", "medium",
                    ["SLA", "지원팀 소개", "온보딩 플랜"], "도입 후에도 함께하겠습니다",
                    "지원 인력 얼굴 소개까지 하면 최고"),
                ProposalSection(6, "ご提案内容 · 제안 내용", "구체적 제안 (마지막에)", "respectful", "medium",
                    ["맞춤 패키지", "파일럿 제안"], "귀사만을 위한 특별 제안",
                    "가격보다 가치를 먼저. 파일럿으로 시작 제안"),
                ProposalSection(7, "次のステップ · 다음 단계", "부드러운 CTA", "soft", "short",
                    ["미팅 일정"], "편하실 때 한 번 더 이야기 나눠보면 좋겠습니다",
                    "강요 금지. 선택권을 드리는 느낌"),
            ]

        elif style == ProposalStyle.VALUE_FIRST:
            return [
                ProposalSection(1, "The Value Snapshot", "핵심 가치/절감액 즉시 제시", "friendly·clear", "short",
                    ["가격 비교표", "절감 계산"], "얼마나 절약되는지 바로 보여드립니다",
                    "숫자를 크게. 비교가 핵심"),
                ProposalSection(2, "Your Situation", "공감과 이해", "warm", "short",
                    ["업계 현황", "현지 데이터"], "비슷한 상황의 기업들이 이 문제를 겪고 있습니다",
                    "현지화된 데이터 필수. 글로벌 숫자는 거리감"),
                ProposalSection(3, "What You Get", "기능·혜택 명확화", "simple·visual", "medium",
                    ["체크리스트", "비교표"], "이 가격에 이걸 다 드립니다",
                    "표와 아이콘 활용. 텍스트 최소화"),
                ProposalSection(4, "Proof It Works", "신뢰 증거", "factual", "medium",
                    ["현지 사례", "고객 후기", "ROI"], "같은 지역 고객이 이미 쓰고 있습니다",
                    "현지 언어 후기 최강. 얼굴 사진 포함이면 더 좋음"),
                ProposalSection(5, "Pricing & Options", "가격 투명성", "transparent", "medium",
                    ["가격표", "패키지 비교"], "숨겨진 비용 없습니다",
                    "티어별 옵션 제공. 가장 인기 있는 플랜 하이라이트"),
                ProposalSection(6, "Let's Start Small", "낮은 진입장벽 CTA", "encouraging", "short",
                    ["무료 파일럿", "30일 체험"], "부담 없이 먼저 써보세요",
                    "결정 압박 금지. 체험으로 시작"),
            ]

        elif style == ProposalStyle.STORY_FIRST:
            return [
                ProposalSection(1, "Una Historia Como la Tuya · 당신 같은 회사 이야기", "감성적 공감 스토리", "warm·narrative", "medium",
                    ["고객 스토리", "Before/After"], "비슷한 회사가 어떻게 변했는지 들어보세요",
                    "주인공이 있는 스토리. 감정선이 핵심"),
                ProposalSection(2, "El Desafío · 도전 과제", "문제 공감", "empathetic", "short",
                    ["업계 현황", "공감 데이터"], "이 문제, 당신만 겪는 게 아닙니다",
                    "숫자보다 이야기. '당신처럼' 언어 사용"),
                ProposalSection(3, "La Solución · 해결책", "제품 소개 (스토리 계속)", "inspiring", "medium",
                    ["데모", "비주얼"], "그래서 우리가 만들었습니다",
                    "기능이 아닌 변화(Transformation)로 설명"),
                ProposalSection(4, "Resultados Reales · 실제 결과", "증거", "proud", "medium",
                    ["고객 후기", "수치", "스토리"], "말이 아닌 결과로 증명합니다",
                    "고객의 목소리를 직접 인용. 사진 포함"),
                ProposalSection(5, "Tu Historia · 당신의 이야기", "맞춤 적용", "personal", "short",
                    ["맞춤 시나리오"], "당신의 이야기는 이렇게 펼쳐질 겁니다",
                    "미래 시점으로 묘사. '6개월 후, 당신은…'"),
                ProposalSection(6, "Empecemos · 시작합시다", "CTA", "enthusiastic", "short",
                    ["파일럿", "미팅"], "함께 이 이야기를 써 나갑시다",
                    "열정을 담아. 첫 걸음을 쉽게"),
            ]

        elif style == ProposalStyle.DATA_FIRST:
            return [
                ProposalSection(1, "Problemanalyse · 문제 분석", "데이터 기반 문제 정의", "precise·technical", "long",
                    ["업계 통계", "독립 연구", "벤치마크"], "데이터가 말하는 현재 상황",
                    "출처 명시 필수. 숫자는 소수점까지"),
                ProposalSection(2, "Technische Spezifikation · 기술 사양", "제품 기술 상세", "technical", "long",
                    ["기술 문서", "아키텍처 다이어그램"], "어떻게 작동하는가",
                    "다이어그램과 표 활용. 모호함 제거"),
                ProposalSection(3, "Qualitätsnachweise · 품질 증거", "검증 데이터", "factual", "medium",
                    ["독립 검증", "인증서", "테스트 결과"], "제3자 검증을 통과했습니다",
                    "자체 주장보다 외부 검증. ISO·DIN 인증 우선"),
                ProposalSection(4, "Wirtschaftlichkeitsanalyse · 경제성 분석", "ROI·TCO 상세", "analytical", "long",
                    ["TCO 분석", "ROI 계산서", "비교표"], "투자 대비 정확한 수익 계산",
                    "보수적 가정 사용. 최선/최악 시나리오 모두"),
                ProposalSection(5, "Implementierungsplan · 구현 계획", "단계별 실행 계획", "structured", "medium",
                    ["간트 차트", "마일스톤"], "정확한 일정과 책임 체계",
                    "불확실한 부분은 솔직히 언급. 신뢰도 높아짐"),
                ProposalSection(6, "Nächste Schritte · 다음 단계", "명확한 절차", "formal", "short",
                    ["계약 절차", "기술 검증 계획"], "다음 단계를 명확히 안내드립니다",
                    "한 가지 결정만 요청. 기술 검토 제안"),
            ]

        elif style == ProposalStyle.RISK_FIRST:
            return [
                ProposalSection(1, "업계 현황 & 위험 신호", "경쟁 환경과 리스크 공감", "analytical", "medium",
                    ["업계 데이터", "경쟁사 동향"], "지금 이 문제를 해결하지 않으면 어떻게 되는가",
                    "위기감을 주되 과장하지 않게. 팩트 기반"),
                ProposalSection(2, "레퍼런스 & 검증 현황", "국내 레퍼런스로 신뢰 구축", "authoritative", "medium",
                    ["국내 고객사 목록", "경쟁사 도입 현황"], "이미 검증된 솔루션—경쟁사도 씁니다",
                    "경쟁사가 도입했다는 사실이 최강 설득 도구"),
                ProposalSection(3, "솔루션 & 핵심 기능", "제품 기능 소개", "confident", "medium",
                    ["기능 비교표", "데모"], "이게 가능한 이유",
                    "기능 하나당 성과 하나. 기능 나열 금지"),
                ProposalSection(4, "도입 ROI & 성과 지표", "정량적 성과", "analytical", "medium",
                    ["ROI 수치", "사례 데이터"], "도입 후 이렇게 달라집니다",
                    "국내 사례 우선. 구체적 수치 필수"),
                ProposalSection(5, "리스크 제거 보장", "우려 해소", "reassuring", "short",
                    ["SLA", "환불 정책", "레퍼런스"], "혹시 걱정되시는 부분은 이렇게 해결됩니다",
                    "예상 반론을 먼저 꺼내서 해결하라"),
                ProposalSection(6, "도입 로드맵", "실행 계획", "practical", "short",
                    ["타임라인", "온보딩"], "이렇게 빠르게 시작할 수 있습니다",
                    "2주 파일럿 → 1개월 도입 패턴이 국내 선호"),
                ProposalSection(7, "다음 단계", "CTA", "direct", "short",
                    ["POC 제안", "미팅 요청"], "지금 바로 시작할 수 있는 방법",
                    "의사결정자를 직접 언급. '팀장님/대표님 보고용' 자료 제공 제안"),
            ]

        # 기본 fallback (RELATIONSHIP_FIRST, HIERARCHY_FIRST)
        else:
            return self._get_frame(ProposalStyle.TRUST_FIRST, product)

    # ── 직무별 커스터마이징 ──────────────────────────────────

    def _apply_role_customization(
        self,
        sections: List[ProposalSection],
        role: RolePsychProfile,
        product: str,
    ) -> List[ProposalSection]:
        """직무 프로파일에 따라 섹션 톤·길이·증거 타입을 조정합니다."""

        for s in sections:
            # CFO → 모든 섹션에 재무 수치 강화
            if role.role == BuyerRole.CFO:
                if "ROI" not in s.evidence_type:
                    s.evidence_type.append("ROI 수치")
                if "비용" not in s.tone:
                    s.writing_tip += " | CFO용: 모든 주장을 금액(원/달러)으로 환산하라."

            # CTO/개발자 → 기술 섹션 확장
            elif role.role in (BuyerRole.CTO, BuyerRole.VP_ENGINEERING, BuyerRole.DEVELOPER):
                if "기술 사양" not in s.evidence_type:
                    s.evidence_type.append("기술 사양")
                s.writing_tip += " | 기술직: 주장보다 코드/아키텍처로 증명하라."

            # CEO → 섹션 길이 단축
            elif role.role == BuyerRole.CEO:
                s.length = "short" if s.length == "long" else s.length
                s.writing_tip += " | CEO용: 각 섹션 3문장 이내 핵심만."

            # 조달 → 가격 투명성 강화
            elif role.role == BuyerRole.PROCUREMENT:
                if "가격 명세" not in s.evidence_type:
                    s.evidence_type.append("가격 명세")

        return sections

    # ── 문화별 커스터마이징 ──────────────────────────────────

    def _apply_culture_customization(
        self,
        sections: List[ProposalSection],
        culture: CultureProfile,
    ) -> List[ProposalSection]:
        """문화 프로파일에 따라 섹션 톤·형식을 조정합니다."""

        for s in sections:
            # 간접 문화권 → 단정적 표현 완화
            if culture.communication == "indirect":
                s.writing_tip += f" | {culture.display_name}: 단정적 표현 대신 제안형으로."

            # 관계 기반 신뢰 → 모든 섹션에 관계 언어 추가
            if culture.trust_basis == "relationship":
                s.writing_tip += " | 관계 언어 사용: '함께', '파트너', '장기적으로'."

            # 저위험 선호 → 리스크 제거 문구 추가
            if culture.risk_appetite == "low":
                if "SLA" not in s.evidence_type:
                    s.evidence_type.append("SLA·보증")
                s.writing_tip += " | 리스크 제거 보장 문구 추가."

        return sections


# ═══════════════════════════════════════════════════════════════════
# 6. StrategistAgent 메인 클래스
# ═══════════════════════════════════════════════════════════════════

class StrategistAgent:
    """
    국가 × 직무 교차 분석으로 최적 제안서 프로토콜을 생성하는 에이전트.

    핵심 메서드
    -----------
    build_blueprint(country, role, product_name, ...) → ProposalBlueprint
    get_culture(country) → CultureProfile
    get_role(role) → RolePsychProfile
    compare_cultures([country1, country2]) → dict
    """

    def __init__(self):
        self._assembler = SectionAssembler()

    def build_blueprint(
        self,
        country:      Country,
        role:         BuyerRole,
        product_name: str = "제품",
        pain_signals: Optional[List[str]] = None,
        value_prop:   str = "",
    ) -> ProposalBlueprint:
        """
        국가 + 직무 조합으로 완전한 제안서 프로토콜을 생성합니다.
        """
        culture = CULTURE_DB.get(country)
        role_p  = ROLE_DB.get(role)

        if not culture:
            raise ValueError(f"지원하지 않는 국가: {country}")
        if not role_p:
            raise ValueError(f"지원하지 않는 역할: {role}")

        # 섹션 조립
        sections = self._assembler.assemble(
            style=culture.proposal_style,
            culture=culture,
            role=role_p,
            product=product_name,
            pain_signals=pain_signals,
        )

        # 오프닝 훅 생성
        opening_hook = self._generate_opening_hook(culture, role_p, product_name)

        # CTA 생성
        closing_cta = self._generate_cta(culture, role_p, product_name)

        # DO/DON'T 합성
        do_list = list(dict.fromkeys(
            culture.tone_keywords[:4] +
            role_p.must_include[:3]
        ))
        dont_list = list(dict.fromkeys(
            culture.taboo_keywords[:3] +
            role_p.must_exclude[:3]
        ))

        cultural_tips = [
            f"인사법: {culture.greeting_protocol}",
            f"제목 스타일: {culture.email_subject_style}",
            f"미팅 오프너: {culture.meeting_opener}",
            f"선호 증거: {', '.join(culture.preferred_evidence[:3])}",
        ]

        return ProposalBlueprint(
            country=country,
            role=role,
            product_name=product_name,
            proposal_style=culture.proposal_style,
            culture_profile=culture,
            role_profile=role_p,
            sections=sections,
            opening_hook=opening_hook,
            closing_cta=closing_cta,
            tone_guide=f"{culture.display_name} × {role_p.display_name}: {culture.proposal_style.value} 스타일, '{culture.tone_keywords[0]}' 톤",
            do_list=do_list,
            dont_list=dont_list,
            cultural_tips=cultural_tips,
        )

    def get_culture(self, country: Country) -> CultureProfile:
        return CULTURE_DB[country]

    def get_role(self, role: BuyerRole) -> RolePsychProfile:
        return ROLE_DB[role]

    def list_countries(self) -> List[dict]:
        return [
            {"key": c.value, "name": p.display_name, "flag": p.flag,
             "style": p.proposal_style.value, "insight": p.insight}
            for c, p in CULTURE_DB.items()
        ]

    def list_roles(self) -> List[dict]:
        return [
            {"key": r.value, "name": p.display_name, "level": p.level,
             "core_fear": p.core_fear, "motivation": p.buying_motivation}
            for r, p in ROLE_DB.items()
        ]

    def compare_cultures(self, countries: List[Country]) -> dict:
        """여러 국가의 핵심 차이점을 비교합니다."""
        return {
            c.value: {
                "style":   CULTURE_DB[c].proposal_style.value,
                "drivers": CULTURE_DB[c].persuasion_drivers[:3],
                "taboos":  CULTURE_DB[c].taboo_keywords[:2],
                "insight": CULTURE_DB[c].insight,
            }
            for c in countries if c in CULTURE_DB
        }

    # ── 내부 헬퍼 ─────────────────────────────────────────────

    def _generate_opening_hook(
        self,
        culture: CultureProfile,
        role:    RolePsychProfile,
        product: str,
    ) -> str:
        style = culture.proposal_style
        fear  = role.core_fear.split(".")[0]

        hooks = {
            ProposalStyle.CONCLUSION_FIRST:
                f"{product}를 도입한 유사 기업은 {role.core_kpis[0]}를 평균 40% 개선했습니다—바로 보여드리겠습니다.",
            ProposalStyle.TRUST_FIRST:
                f"귀사의 {role.core_kpis[0]} 과제에 대해 사전에 깊이 공부했습니다. 저희가 어떻게 장기적 파트너가 될 수 있는지 말씀드리겠습니다.",
            ProposalStyle.VALUE_FIRST:
                f"비슷한 규모의 기업이 {product}로 월 X만 원을 절약하고 있습니다—어떻게 가능한지 3분 안에 설명드리겠습니다.",
            ProposalStyle.STORY_FIRST:
                f"6개월 전, 여러분과 똑같은 고민을 하던 회사가 있었습니다. 그들의 이야기를 먼저 들어보시겠어요?",
            ProposalStyle.DATA_FIRST:
                f"업계 데이터에 따르면 {role.core_kpis[0]} 미달의 주원인 3가지가 있습니다—{product}는 그 중 2가지를 완전히 제거합니다.",
            ProposalStyle.RISK_FIRST:
                f"경쟁사 중 이미 3곳이 {product}를 도입했습니다. {fear}에 대한 우려를 먼저 해소해 드리겠습니다.",
            ProposalStyle.RELATIONSHIP_FIRST:
                f"귀사와 장기적인 전략 파트너십을 목표로 이 자리를 준비했습니다. 먼저 저희를 소개해 드리겠습니다.",
            ProposalStyle.HIERARCHY_FIRST:
                f"[권위 레퍼런스]와의 전략적 협력 경험을 바탕으로, 귀사에 최적화된 솔루션을 제안드립니다.",
        }
        return hooks.get(style, f"{product}가 {role.core_kpis[0]}를 어떻게 개선하는지 보여드리겠습니다.")

    def _generate_cta(
        self,
        culture: CultureProfile,
        role:    RolePsychProfile,
        product: str,
    ) -> str:
        ctas = {
            ProposalStyle.CONCLUSION_FIRST:
                "이번 주 안에 30분 데모를 잡아드리겠습니다. 언제가 편하신가요?",
            ProposalStyle.TRUST_FIRST:
                "부담 없이 파일럿 프로그램으로 시작해 보시는 것은 어떠실까요? 일정을 조율해 드리겠습니다.",
            ProposalStyle.VALUE_FIRST:
                "14일 무료 체험을 바로 시작하실 수 있습니다. 신용카드 불필요, 언제든 취소 가능합니다.",
            ProposalStyle.STORY_FIRST:
                "당신의 이야기를 함께 써 나가고 싶습니다. 이번 주에 30분 커피챗 어떠세요?",
            ProposalStyle.DATA_FIRST:
                "기술 검토를 위한 상세 사양서와 POC 계획서를 보내드리겠습니다. 검토 후 다음 단계를 논의하시죠.",
            ProposalStyle.RISK_FIRST:
                "2주 POC를 제안드립니다. 성과가 없으면 비용 없이 종료—리스크 없이 시작하실 수 있습니다.",
            ProposalStyle.RELATIONSHIP_FIRST:
                "먼저 편하게 만나 뵙고 싶습니다. 식사 자리를 마련해도 될까요?",
            ProposalStyle.HIERARCHY_FIRST:
                "고위 경영진 간 전략 논의 자리를 제안드립니다. 일정을 조율해 드리겠습니다.",
        }
        return ctas.get(culture.proposal_style, "다음 단계를 논의하기 위해 미팅을 제안드립니다.")
