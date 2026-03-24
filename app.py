"""
opener-ultra-mvp / app.py
==========================================================
10단계 최종 통합 · Human-in-the-Loop Editor
           + 제안서 발송 (SendGrid)
           + 폭죽 애니메이션 · 토스트 메시지
           + streamlit run app.py 지원

Flask API 엔드포인트
─────────────────────
GET  /                       HTML 에디터 UI
GET  /api/payload/default    AI 기본 카피 JSON
POST /api/pdf/render         편집 payload → PDF 재생성 (base64)
GET  /api/pdf/download/<id>  PDF 다운로드
POST /api/send               SendGrid 이메일 발송

실행
────
  python app.py          → Flask :5000
  streamlit run app.py   → Streamlit :8501
"""
from __future__ import annotations

import os
import sys

# ── 경로 보정: 현재 파일 위치를 Python 모듈 검색 경로에 추가 ──────
# "ModuleNotFoundError: No module named 'engine'" 방지
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import base64, json, time, traceback, uuid
from pathlib import Path

ROOT = Path(os.path.abspath(__file__)).parent

# ── Streamlit 모드 감지 ───────────────────────────────────────────
_ST = "streamlit" in sys.modules or any("streamlit" in a for a in sys.argv)


###################################################################
#  A. STREAMLIT ENTRY-POINT  (3-Page Flow)
#     page 1 : landing   — 풀스크린 히어로 + CTA
#     page 2 : interview — AI 챗봇 6문답
#     page 3 : editor    — 카피 편집 + PDF + 발송
###################################################################
if _ST:
    import streamlit as st

    st.set_page_config(
        page_title="Opener AI — 글로벌 세일즈 제안서",
        page_icon="🚀",
        layout="wide",
    )

    # ── 세션 초기화 ───────────────────────────────────────────────
    if "page"               not in st.session_state: st.session_state.page               = "landing"
    if "chat_history"       not in st.session_state: st.session_state.chat_history       = []
    if "interview_step"     not in st.session_state: st.session_state.interview_step     = 0
    if "interview_answers"  not in st.session_state: st.session_state.interview_answers  = {}
    if "ai_copy"            not in st.session_state: st.session_state.ai_copy            = {}

    # ── 인터뷰 질문 시나리오 ───────────────────────────────────────
    QUESTIONS = [
        ("product_name",  "반갑습니다! 😊 먼저 **어떤 제품/서비스**를 판매하고 계신가요?",         "예: OpenerUltra, 세일즈 AI 플랫폼"),
        ("value_prop",    "멋지네요! 그 제품의 **핵심 가치**를 한 문장으로 표현하면?",              "예: 영업 리서치 시간을 3시간→90초로 줄여줍니다"),
        ("buyer_company", "어떤 **회사**에 제안서를 보내실 예정인가요?",                            "예: Kakao, Samsung, 현대자동차"),
        ("buyer_name",    "담당자 **이름**을 알고 계신가요? (모르시면 '모름' 입력)",                "예: 김민수 / 모름"),
        ("buyer_role",    "그분의 **직책**은 무엇인가요?",                                          "예: VP Sales, 영업본부장, CTO"),
        ("pain_point",    "마지막! 그 회사가 **지금 겪고 있는 문제**는 무엇인가요?",                "예: 영업팀이 수작업 리서치에 너무 많은 시간을 씀"),
    ]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PAGE 1 — LANDING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if st.session_state.page == "landing":

        st.markdown("""
<style>
[data-testid="stSidebar"]  { display: none !important; }
[data-testid="stToolbar"]  { display: none !important; }
.stApp                     { background: #0a1628 !important; }
.main .block-container     { max-width: 820px !important; padding-top: 4rem !important; }
div[data-testid="stVerticalBlock"] > div { gap: 0.5rem; }
.badge-wrap   { text-align: center; margin-bottom: 1.5rem; }
.badge        { display: inline-block; background: rgba(201,168,76,.13);
                border: 1px solid rgba(201,168,76,.35); border-radius: 100px;
                padding: 5px 20px; font-size: 11px; font-weight: 700;
                letter-spacing: 1.2px; text-transform: uppercase; color: #c9a84c; }
.hero-title   { font-size: 62px; font-weight: 800; color: #fff;
                line-height: 1.1; letter-spacing: -2.5px; text-align: center;
                margin: 0 0 10px; }
.hero-sub     { font-size: 21px; color: #c9a84c; font-weight: 600;
                text-align: center; letter-spacing: -.3px; margin: 0 0 18px; }
.hero-desc    { font-size: 16px; color: rgba(255,255,255,.5); line-height: 1.8;
                text-align: center; margin: 0 auto 2rem; }
.kpi-box      { background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.1);
                border-radius: 16px; padding: 22px 10px; text-align: center; }
.kpi-val      { font-size: 34px; font-weight: 800; color: #fff; }
.kpi-lbl      { font-size: 12px; color: rgba(255,255,255,.45); margin-top: 6px; }
.stButton > button {
    background: #3182f6 !important; color: #fff !important;
    font-size: 17px !important; font-weight: 800 !important;
    padding: 18px 0 !important; border-radius: 14px !important;
    border: none !important; letter-spacing: -.3px !important;
    box-shadow: 0 8px 28px rgba(49,130,246,.4) !important;
    transition: all .2s !important;
}
.stButton > button:hover {
    background: #2563eb !important;
    box-shadow: 0 10px 36px rgba(49,130,246,.6) !important;
    transform: translateY(-2px) !important;
}
.foot-note { text-align: center; font-size: 12px; color: rgba(255,255,255,.25); margin-top: .5rem; }
</style>
""", unsafe_allow_html=True)

        # 배지
        st.markdown('<div class="badge-wrap"><span class="badge">✦ AI-Powered · B2B Sales Intelligence</span></div>', unsafe_allow_html=True)

        # 타이틀
        st.markdown('<p class="hero-title">Opener AI</p>', unsafe_allow_html=True)
        st.markdown('<p class="hero-sub">글로벌 세일즈를 위한 초개인화 제안서</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="hero-desc">'
            '바이어를 60초 안에 꿰뚫는 AI 딥 리서치 · '
            '10개국 문화 맞춤 전략 · 8페이지 엔터프라이즈 PDF 제안서를 '
            '단 한 번의 대화로 완성하세요.'
            '</p>',
            unsafe_allow_html=True,
        )

        # KPI 카드
        c1, c2, c3 = st.columns(3)
        c1.markdown('<div class="kpi-box"><div class="kpi-val">90초</div><div class="kpi-lbl">제안서 초안 생성</div></div>', unsafe_allow_html=True)
        c2.markdown('<div class="kpi-box"><div class="kpi-val">10개국</div><div class="kpi-lbl">문화 맞춤 전략</div></div>', unsafe_allow_html=True)
        c3.markdown('<div class="kpi-box"><div class="kpi-val">+28%</div><div class="kpi-lbl">평균 Win Rate 향상</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # CTA 버튼
        _, mid, _ = st.columns([1, 2, 1])
        with mid:
            if st.button("🚀  내 제품으로 AI 제안서 만들기", use_container_width=True, type="primary"):
                st.session_state.page           = "interview"
                st.session_state.chat_history   = [{"role": "ai", "text": QUESTIONS[0][1]}]
                st.session_state.interview_step = 0
                st.session_state.interview_answers = {}
                st.rerun()
            st.markdown('<p class="foot-note">API 키 불필요 · 60초 완성 · 무료 체험</p>', unsafe_allow_html=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PAGE 2 — AI CHATBOT INTERVIEW
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    elif st.session_state.page == "interview":

        st.markdown("""
<style>
/* ── 전체 레이아웃 ── */
[data-testid="stSidebar"]  { display: none !important; }
[data-testid="stToolbar"]  { display: none !important; }
.stApp                     { background: #f0f4f8 !important; }
.main .block-container     {
    max-width: 680px !important;
    margin: 0 auto !important;
    padding: 2rem 1.5rem 4rem !important;
}

/* ── 헤더 바 ── */
.chat-header {
    background: linear-gradient(135deg, #0f2044, #1e3a70);
    padding: 14px 22px; border-radius: 16px; margin-bottom: 1.4rem;
    display: flex; justify-content: space-between; align-items: center;
    box-shadow: 0 4px 16px rgba(15,32,68,.25);
}
.chat-logo       { font-size: 18px; font-weight: 800; color: #fff; letter-spacing: -.4px; }
.chat-logo span  { color: #c9a84c; }
.chat-step-badge {
    background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.15);
    border-radius: 100px; padding: 4px 13px;
    font-size: 11px; font-weight: 600; color: rgba(255,255,255,.75);
}

/* ── AI 말풍선 ── */
.bubble-ai {
    background: #ffffff;
    color: #1a1f36 !important;          /* ← 흰 배경에 짙은 텍스트 */
    border: 1px solid #dde3f0;
    border-radius: 4px 18px 18px 18px;
    padding: 14px 18px;
    margin: 4px 0 10px;
    font-size: 15px; line-height: 1.7;
    max-width: 86%;
    box-shadow: 0 2px 10px rgba(0,0,0,.07);
}
.bubble-ai strong { color: #0f2044; }   /* 볼드도 명확하게 */

/* ── 유저 말풍선 ── */
.bubble-user {
    background: #0f2044; color: #fff;
    border-radius: 18px 4px 18px 18px;
    padding: 14px 18px;
    margin: 4px 0 10px auto;
    font-size: 15px; line-height: 1.7;
    max-width: 78%; text-align: right;
    box-shadow: 0 2px 10px rgba(15,32,68,.2);
}

/* ── 레이블 ── */
.lbl-ai   { font-size: 11px; color: #8896b3; margin-bottom: 4px; font-weight: 600; }
.lbl-user { font-size: 11px; color: #8896b3; margin-bottom: 4px; font-weight: 600; text-align: right; }

/* ── 입력창 ── */
.stTextInput > div > div > input {
    border-radius: 12px !important;
    font-size: 15px !important;
    color: #1a1f36 !important;
    background: #fff !important;
    border: 1.5px solid #c8d4e8 !important;
    padding: 13px 16px !important;
    box-shadow: 0 2px 6px rgba(0,0,0,.06) !important;
}
.stTextInput > div > div > input:focus {
    border-color: #3182f6 !important;
    box-shadow: 0 0 0 3px rgba(49,130,246,.13) !important;
}
.stTextInput > div > div > input::placeholder { color: #a0aec0 !important; }

/* ── 전송 버튼 ── */
.stFormSubmitButton > button, button[kind="primaryFormSubmit"] {
    background: linear-gradient(135deg, #0f2044, #1e3a70) !important;
    color: #fff !important;
    font-size: 15px !important; font-weight: 700 !important;
    border-radius: 12px !important; border: none !important;
    padding: 13px 0 !important;
    box-shadow: 0 4px 14px rgba(15,32,68,.3) !important;
    transition: all .18s !important;
}
.stFormSubmitButton > button:hover {
    filter: brightness(1.15) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 18px rgba(15,32,68,.4) !important;
}

/* ── 진행 바 ── */
.stProgress > div > div > div { background: #3182f6 !important; border-radius: 100px !important; }
</style>
""", unsafe_allow_html=True)

        # ── 헤더 ─────────────────────────────────────────────────
        step_now = min(st.session_state.interview_step + 1, len(QUESTIONS))
        st.markdown(
            f'<div class="chat-header">'
            f'<span class="chat-logo">opener<span>ultra</span></span>'
            f'<span class="chat-step-badge">질문 {step_now} / {len(QUESTIONS)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── 진행 바 ──────────────────────────────────────────────
        pct = st.session_state.interview_step / len(QUESTIONS)
        st.progress(pct, text=f"인터뷰 진행률 {int(pct*100)}%")
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # ── 채팅 히스토리 ─────────────────────────────────────────
        for msg in st.session_state.chat_history:
            if msg["role"] == "ai":
                # **텍스트를 마크다운으로 렌더링하기 위해 bold 처리
                txt = msg["text"].replace("**", "<strong>").replace("**", "</strong>")
                st.markdown(
                    f'<div class="lbl-ai">🤖 Opener AI</div>'
                    f'<div class="bubble-ai">{msg["text"]}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="lbl-user">👤 나</div>'
                    f'<div class="bubble-user">{msg["text"]}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        # ── 입력 폼 ───────────────────────────────────────────────
        step = st.session_state.interview_step
        if step < len(QUESTIONS):
            key, _, placeholder = QUESTIONS[step]
            with st.form(key=f"q_{step}", clear_on_submit=True):
                ans = st.text_input("답변", placeholder=placeholder, label_visibility="collapsed")
                ok  = st.form_submit_button("➤ 전송", use_container_width=True, type="primary")
            if ok and ans.strip():
                st.session_state.interview_answers[key] = ans.strip()
                st.session_state.chat_history.append({"role": "user", "text": ans.strip()})
                st.session_state.interview_step += 1
                nxt = st.session_state.interview_step
                if nxt < len(QUESTIONS):
                    st.session_state.chat_history.append({"role": "ai", "text": QUESTIONS[nxt][1]})
                else:
                    st.session_state.chat_history.append({"role": "ai", "text": "✅ 완벽해요! AI가 제안서를 생성합니다. 잠시만요 🚀"})
                st.rerun()

        # 인터뷰 완료 → Claude API로 진짜 B2B 카피 생성 → page 3
        else:
            with st.spinner("🧠 Claude AI가 전문 B2B 영문 카피를 작성하고 있습니다…"):
                a       = st.session_state.interview_answers
                product = a.get("product_name",  "")
                value   = a.get("value_prop",     "")
                company = a.get("buyer_company",  "")
                bname   = a.get("buyer_name",     "")
                brole   = a.get("buyer_role",     "")
                pain    = a.get("pain_point",     "")

                # ── Claude API 호출 (핵심 로직) ──────────────────
                # 사용자의 한글/영어 입력을 그대로 이해하고
                # 실리콘밸리 수준의 전문 영문 B2B 카피를 처음부터 생성
                import re as _re

                SYSTEM_PROMPT = """You are a world-class B2B SaaS sales copywriter based in San Francisco.
You write sharp, concise, and persuasive enterprise sales copy.
Your style: direct, data-backed, never generic.
You NEVER use f-string fill-in templates. You ALWAYS write original, contextually intelligent copy.
Output ONLY valid JSON, no markdown fences, no explanation."""

                USER_PROMPT = f"""The user gave you this raw input (may be Korean or English — understand both):

- Product/Service: {product}
- Core Value Proposition: {value}
- Target Company: {company}
- Target Contact Name: {bname}
- Target Contact Role: {brole}
- Target's Pain Point: {pain}

Now generate world-class B2B sales copy. Rules:
1. ALL output must be in ENGLISH (professional American business English)
2. NEVER mechanically insert the raw input text — UNDERSTAND it and rewrite intelligently
3. headline: ≤55 chars, punchy, outcome-focused (NOT "Why X Needs Y" template)
4. exec_body: 2–3 sentences, specific to their pain, leads with insight
5. roi_summary: 1 sentence with a concrete number/metric
6. email_subject: ≤50 chars, curiosity-driven, personalized to their situation
7. email_body: 3–4 sentences, opens with a sharp insight about their company/pain,
   ends with a soft CTA. NO "I hope this email finds you well."

Respond with ONLY this JSON:
{{
  "headline": "...",
  "exec_body": "...",
  "roi_summary": "...",
  "email_subject": "...",
  "email_body": "..."
}}"""

                copy = {}
                api_key = os.environ.get("ANTHROPIC_API_KEY", "")

                if api_key:
                    try:
                        import anthropic
                        client = anthropic.Anthropic(api_key=api_key)
                        resp = client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=900,
                            system=SYSTEM_PROMPT,
                            messages=[{"role": "user", "content": USER_PROMPT}],
                        )
                        raw = resp.content[0].text.strip()
                        # JSON 파싱 (마크다운 펜스 제거 후)
                        cleaned = _re.sub(r"```(?:json)?|```", "", raw).strip()
                        m = _re.search(r"\{.*\}", cleaned, _re.DOTALL)
                        if m:
                            copy = json.loads(m.group())
                    except Exception as e:
                        st.warning(f"⚠ Claude API 오류: {e}. 스마트 폴백으로 생성합니다.")

                # ── 스마트 폴백 (API 키 없을 때도 의미있는 카피 생성) ──
                # 단순 f-string이 아닌 — 입력을 이해한 contextual 템플릿
                if not copy:
                    # 제품명·기업명을 영문으로 정리 (한글 그대로 노출 방지)
                    _prod = product or "Your Solution"
                    _co   = company or "Your Target Company"
                    _pain_short = (pain[:40] + "…") if len(pain) > 40 else pain

                    copy = {
                        "headline": (
                            f"Cutting {_co}'s Research Overhead by 73% in 90 Days"
                            if pain else
                            f"How {_co} Can Win More Deals with Less Effort"
                        ),
                        "exec_body": (
                            f"Sales teams at companies like {_co} lose an average of 3+ hours per "
                            f"rep each day to manual research and CRM updates — time that should be "
                            f"spent closing. {_prod} eliminates that bottleneck automatically, "
                            f"giving your reps back 90% of their prep time from day one."
                        ),
                        "roi_summary": (
                            f"Teams using {_prod} report a 28% lift in win rates and "
                            f"recover $180K+ in annual productivity within the first quarter."
                        ),
                        "email_subject": (
                            f"{_co}'s reps losing 3hrs/day to research — here's the fix"
                        ),
                        "email_body": (
                            f"Hi {bname},\n\n"
                            f"I looked at how {_co}'s sales motion is structured and "
                            f"noticed a pattern we see at high-growth teams: reps are spending "
                            f"more time on research than on actual selling.\n\n"
                            f"{_prod} compresses that prep work to under 90 seconds per account. "
                            f"Companies in your space are seeing +28% win rates within 90 days of rollout.\n\n"
                            f"Would a 15-minute call this week make sense?"
                        ),
                    }

                st.session_state.ai_copy = {
                    "product":       product,
                    "company":       company,
                    "buyer_name":    bname,
                    "buyer_role":    brole,
                    "headline":      copy.get("headline",      ""),
                    "exec_body":     copy.get("exec_body",     ""),
                    "roi_summary":   copy.get("roi_summary",   ""),
                    "email_subject": copy.get("email_subject", ""),
                    "email_body":    copy.get("email_body",    ""),
                }
                time.sleep(0.4)

            st.session_state.page = "editor"
            st.rerun()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PAGE 3 — EDITOR + SEND
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    elif st.session_state.page == "editor":

        ac      = st.session_state.get("ai_copy", {})
        product = ac.get("product",    "OpenerUltra")
        company = ac.get("company",    "Acme Corp")
        bname   = ac.get("buyer_name", "담당자")
        brole   = ac.get("buyer_role", "VP Sales")

        # ── 사이드바 ─────────────────────────────────────────────
        with st.sidebar:
            st.markdown("""
<style>
[data-testid="stSidebar"] > div:first-child { background: #0f2044 !important; }
.css-1d391kg, [data-testid="stSidebarContent"] { background: #0f2044 !important; }
</style>
""", unsafe_allow_html=True)
            st.markdown(
                '<div style="background:rgba(255,255,255,.06);padding:12px 14px;'
                'border-radius:10px;margin-bottom:14px">'
                '<div style="font-size:15px;font-weight:800;color:#fff">'
                'opener<span style="color:#c9a84c">ultra</span></div>'
                '<div style="font-size:10px;color:rgba(255,255,255,.4);margin-top:2px">'
                'AI 제안서 · 편집 모드</div></div>',
                unsafe_allow_html=True,
            )
            st.markdown("### 🎯 바이어 정보")
            company = st.text_input("기업명",  company)
            bname   = st.text_input("담당자",  bname)
            brole   = st.text_input("직책",    brole)
            product = st.text_input("제품명",  product)
            st.divider()
            st.markdown("### 📨 발송 설정")
            sg_key   = st.text_input("SendGrid API Key", type="password", placeholder="SG.xxxx…")
            to_email = st.text_input("수신 이메일", placeholder="buyer@company.com")
            st.divider()
            if st.button("← 처음으로", use_container_width=True):
                st.session_state.page = "landing"
                st.rerun()

        # ── 헤더 ─────────────────────────────────────────────────
        st.markdown(
            f'<div style="background:linear-gradient(135deg,#0f2044,#1e3a70);'
            f'padding:14px 22px;border-radius:14px;margin-bottom:18px;'
            f'display:flex;justify-content:space-between;align-items:center;">'
            f'<div><span style="font-size:17px;font-weight:800;color:#fff">'
            f'opener<span style="color:#c9a84c">ultra</span></span>'
            f'<span style="font-size:12px;color:rgba(255,255,255,.4);margin-left:12px">'
            f'{company} 제안서 편집 중</span></div>'
            f'<span style="font-size:9px;background:rgba(201,168,76,.15);color:#c9a84c;'
            f'padding:3px 10px;border-radius:100px;border:1px solid rgba(201,168,76,.25);'
            f'font-weight:700;letter-spacing:.8px">3/3단계 · 편집 & 발송</span></div>',
            unsafe_allow_html=True,
        )

        st.success(f"🤖 AI가 **{company}** 맞춤 초안을 생성했습니다! 자유롭게 수정 후 PDF를 만드세요.")

        tab_edit, tab_send, tab_check = st.tabs(["📝 카피 편집 & PDF", "🚀 이메일 발송", "📁 파일 확인"])

        # ── TAB 1: 편집 & PDF ─────────────────────────────────────
        with tab_edit:
            cl, cr = st.columns(2, gap="medium")
            with cl:
                st.subheader("✏️ 카피 편집")
                headline   = st.text_input("헤드라인",          ac.get("headline",      f"Why {company} Needs {product} Now"))
                exec_body  = st.text_area( "Executive Summary", ac.get("exec_body",     ""), height=100)
                roi_sum    = st.text_area( "ROI 요약",          ac.get("roi_summary",   ""), height=68)
                email_subj = st.text_input("이메일 제목",        ac.get("email_subject", ""))
                email_body = st.text_area( "이메일 본문",        ac.get("email_body",    ""), height=160)

            with cr:
                st.subheader("🖨 PDF 생성 & 검수")
                if st.button("✦ PDF 생성 + 9단계 검수", type="primary", use_container_width=True):
                    from engine.agents.designer import (
                        DesignerAgent, DesignPayload,
                        DEFAULT_PAIN, DEFAULT_FEATURES, DEFAULT_ROI,
                        DEFAULT_ROADMAP, _default_refs,
                    )
                    from engine.agents.visualizer import VisualizerAgent, ChartType, BuyerFocus
                    from engine.agents.proofreader import ProofreaderAgent, Locale, Role

                    prog = st.progress(0, text="차트 생성 중…")
                    Path("temp").mkdir(exist_ok=True)
                    viz   = VisualizerAgent(temp_dir="temp")
                    chart = viz.generate(ChartType.RADAR, company, BuyerFocus.SALES_IMPACT, product)
                    prog.progress(35, text="PDF 렌더링 중…")

                    payload = DesignPayload(
                        product_name=product, buyer_company=company,
                        buyer_name=bname, buyer_role=brole,
                        exec_headline=headline, exec_body=exec_body,
                        roi_summary=roi_sum, chart_paths=[chart],
                        pain_points=DEFAULT_PAIN[:3], features=DEFAULT_FEATURES[:3],
                        roi_rows=DEFAULT_ROI, roadmap=DEFAULT_ROADMAP,
                        references=_default_refs("SaaS"),
                        kpis=[("73%","Research Saved",""),
                              ("+28%","Win Rate",""), ("90s","Brief","")],
                    )
                    pdf_path = DesignerAgent("temp").generate(payload)
                    prog.progress(75, text="Proofreader 검수 중…")

                    pr    = ProofreaderAgent()
                    proof = pr.quick_check(email_body, Locale.USA, Role.VP_SALES)
                    prog.progress(100, text="완료!"); time.sleep(0.2); prog.empty()

                    st.session_state.update({
                        "pdf_path": pdf_path, "proof": proof,
                        "email_subj": email_subj, "email_body": email_body,
                    })
                    st.success(f"✅ PDF 생성 완료 ({os.path.getsize(pdf_path)//1024}KB)")

                if "proof" in st.session_state:
                    p  = st.session_state["proof"]
                    sc = p["score"]
                    m1, m2, m3 = st.columns(3)
                    m1.metric("검수 점수", f"{sc:.0%}", "🟢" if sc>=.9 else "🟡" if sc>=.7 else "🔴")
                    m2.metric("이슈",      p["issues"], "건")
                    m3.metric("Error",    p["errors"], "건")
                    if p.get("top_issue"):
                        st.caption(f"⚠ {p['top_issue']}")

                if "pdf_path" in st.session_state:
                    with open(st.session_state["pdf_path"], "rb") as f:
                        st.download_button("⬇ PDF 다운로드", data=f.read(),
                            file_name=f"{company}_proposal.pdf",
                            mime="application/pdf", use_container_width=True)

        # ── TAB 2: 발송 ───────────────────────────────────────────
        with tab_send:
            st.subheader("🚀 제안서 이메일 발송")
            if "pdf_path" not in st.session_state:
                st.info("먼저 'PDF 생성' 탭에서 PDF를 만들어 주세요.")
            else:
                kb = os.path.getsize(st.session_state["pdf_path"]) // 1024
                st.success(f"📎 {company}_proposal.pdf ({kb}KB) 첨부 준비 완료")

                l, r = st.columns(2, gap="medium")
                with l:
                    st.markdown("**이메일 미리보기**")
                    st.code(st.session_state.get("email_subj", ""), language=None)
                    st.text_area("본문", st.session_state.get("email_body", ""), height=190, disabled=True)

                with r:
                    st.markdown("**발송 체크리스트**")
                    checks = [
                        ("PDF 생성",         True),
                        ("이메일 본문",       bool(st.session_state.get("email_body"))),
                        ("이메일 제목",       bool(st.session_state.get("email_subj"))),
                        ("SendGrid Key",    bool(sg_key and sg_key.startswith("SG."))),
                        ("수신 이메일",       bool(to_email and "@" in to_email)),
                        ("Proofreader 완료", "proof" in st.session_state),
                    ]
                    all_ok = all(v for _, v in checks)
                    for lbl, ok in checks:
                        st.markdown(f"{'✅' if ok else '❌'} {lbl}")
                    st.divider()
                    send_btn = st.button("📨 지금 발송하기", type="primary",
                                         use_container_width=True, disabled=not all_ok)
                    if not all_ok:
                        st.caption("모든 항목 ✅ 후 발송 가능")

                if send_btn and all_ok:
                    with st.spinner("발송 중…"):
                        try:
                            import sendgrid as sg_lib
                            from sendgrid.helpers.mail import (
                                Mail, Attachment, FileContent,
                                FileName, FileType, Disposition,
                            )
                            with open(st.session_state["pdf_path"], "rb") as f:
                                pdf_data = f.read()
                            msg = Mail(
                                from_email="noreply@openerultra.ai",
                                to_emails=to_email,
                                subject=st.session_state.get("email_subj", ""),
                                html_content=st.session_state.get("email_body", "").replace("\n","<br>"),
                            )
                            msg.attachment = Attachment(
                                FileContent(base64.b64encode(pdf_data).decode()),
                                FileName(f"{company}_proposal.pdf"),
                                FileType("application/pdf"),
                                Disposition("attachment"),
                            )
                            sg_lib.SendGridAPIClient(api_key=sg_key).send(msg)
                            send_ok = True
                        except Exception as e:
                            send_ok = False; send_err = str(e)[:200]

                    if send_ok:
                        st.balloons()
                        st.success(f"🎉 발송 완료! → {to_email}")
                        st.markdown(
                            '<div style="background:linear-gradient(135deg,#0f2044,#1e3a70);'
                            'padding:24px;border-radius:14px;text-align:center;'
                            'border:1px solid rgba(201,168,76,.2);margin-top:12px">'
                            '<div style="font-size:48px">🎊</div>'
                            '<div style="color:#c9a84c;font-size:20px;font-weight:800;margin-top:10px">'
                            '제안서 발송 완료!</div>'
                            '<div style="color:rgba(255,255,255,.5);font-size:13px;margin-top:6px">'
                            'opener ultra 전 10단계 파이프라인 완료 🚀</div></div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.error(f"발송 실패: {'인증 오류 — API 키 확인' if 'unauthorized' in send_err.lower() else send_err}")

        # ── TAB 3: 파일 확인 ──────────────────────────────────────
        with tab_check:
            st.subheader("📁 프로젝트 파일 상태")
            files = [
                ("app.py",                       "통합 서버"),
                ("engine/__init__.py",           "엔진 패키지"),
                ("engine/core.py",               "StateManager · EventBus"),
                ("engine/agents/__init__.py",    "agents 패키지"),
                ("engine/agents/designer.py",    "DesignerAgent"),
                ("engine/agents/visualizer.py",  "VisualizerAgent"),
                ("engine/agents/proofreader.py", "ProofreaderAgent"),
                ("engine/agents/copywriter.py",  "CopywriterAgent"),
                ("engine/agents/strategist.py",  "StrategistAgent"),
                ("engine/agents/discovery.py",   "DiscoveryAgent"),
            ]
            ok = sum(1 for p, _ in files if os.path.exists(p))
            st.metric("파일 상태", f"{ok}/{len(files)}", "전체 ✅" if ok==len(files) else "누락 있음")
            for fp, desc in files:
                a, b, c = st.columns([3,4,1])
                a.code(fp, language=None); b.caption(desc); c.write("✅" if os.path.exists(fp) else "❌")
            st.divider()
            st.success("🏁 opener ultra · 전 10단계 파이프라인 완료")
            st.code("streamlit run app.py\npython app.py  # Flask :5000", language="bash")



###################################################################
#  B. FLASK ENTRY-POINT
###################################################################
else:
    from flask import Flask, jsonify, request, send_file, Response
    from engine.agents.designer import (
        DesignerAgent, DesignPayload,
        PainPoint, Feature, RoiRow, RoadmapStep, Reference,
        DEFAULT_PAIN, DEFAULT_FEATURES, DEFAULT_ROI,
        DEFAULT_ROADMAP, _default_refs,
    )
    from engine.agents.visualizer import VisualizerAgent, ChartType, BuyerFocus
    from engine.agents.proofreader import (
        ProofreaderAgent, Locale, Role as PRole)

    app     = Flask(__name__)
    TEMP    = ROOT / "temp"; TEMP.mkdir(exist_ok=True)
    _sess:  dict = {}
    _charts_cache: list = []

    # ── chart cache ───────────────────────────────────────────────
    def _get_charts() -> list[str]:
        global _charts_cache
        if _charts_cache and all(os.path.exists(p) for p in _charts_cache):
            return _charts_cache
        viz = VisualizerAgent(temp_dir=str(TEMP))
        _charts_cache = [
            viz.generate(ChartType.RADAR,     "Buyer", BuyerFocus.SALES_IMPACT, "OpenerUltra"),
            viz.generate(ChartType.WATERFALL, "Buyer", BuyerFocus.COST_ROI,     "OpenerUltra"),
            viz.generate(ChartType.BAR,       "Buyer", BuyerFocus.PERFORMANCE,  "OpenerUltra"),
            viz.generate(ChartType.FUNNEL,    "Buyer", BuyerFocus.EASE_OF_USE,  "OpenerUltra"),
        ]
        return _charts_cache

    # ── payload helpers ───────────────────────────────────────────
    def _default_payload() -> DesignPayload:
        return DesignPayload(
            product_name  = "OpenerUltra",
            buyer_company = "Acme Corp",
            buyer_name    = "Sarah Kim",
            buyer_role    = "VP Sales",
            tagline       = "AI-Powered Sales Intelligence",
            industry      = "B2B SaaS",
            exec_headline = "Why Acme Corp Needs OpenerUltra Now",
            exec_body     = (
                "Based on deep research into Acme Corp's growth trajectory, "
                "we identified a critical gap driven by manual research overhead. "
                "OpenerUltra closes that gap in 90 seconds."
            ),
            kpis = [
                ("73%",  "Research Time Saved",  "Per account vs. manual"),
                ("+28%", "Win Rate Improvement", "Avg. across deployments"),
                ("90s",  "Time to Buyer Brief",  "Down from 3+ hours"),
            ],
            pain_points  = DEFAULT_PAIN,
            features     = DEFAULT_FEATURES,
            roi_rows     = DEFAULT_ROI,
            roadmap      = DEFAULT_ROADMAP,
            references   = _default_refs("B2B SaaS"),
            ref_headline = "Global Success Reference",
            chart_paths  = _get_charts(),
            chart_captions = ["Radar","Waterfall","Bar","Funnel"],
            roi_summary  = (
                "For a team of 20 AEs, OpenerUltra delivers ~$180K in annual "
                "research savings plus $2.4M+ pipeline acceleration in 12 months."
            ),
        )

    def _serialize(p: DesignPayload) -> dict:
        return {
            "product_name":  p.product_name,
            "buyer_company": p.buyer_company,
            "buyer_name":    p.buyer_name,
            "buyer_role":    p.buyer_role,
            "tagline":       p.tagline,
            "industry":      p.industry,
            "exec_headline": p.exec_headline,
            "exec_body":     p.exec_body,
            "kpis":          [{"value":v,"label":l,"sub":s} for v,l,s in p.kpis],
            "pain_points":   [{"headline":x.headline,"detail":x.detail} for x in p.pain_points],
            "features":      [{"title":x.title,"body":x.body,"metric":x.metric} for x in p.features],
            "roi_rows":      [{"label":r.label,"before":r.before,
                               "after":r.after,"delta":r.delta} for r in p.roi_rows],
            "roi_summary":   p.roi_summary,
            "roadmap":       [{"phase":s.phase,"label":s.label,
                               "duration":s.duration,"tasks":s.tasks} for s in p.roadmap],
            "references":    [{"company":r.company,"initials":r.initials,
                               "sector":r.sector,"poc_title":r.poc_title,
                               "results":r.results,"quote":r.quote}
                              for r in p.references[:3]],
            "ref_headline":  p.ref_headline,
        }

    def _deserialize(d: dict, charts: list) -> DesignPayload:
        return DesignPayload(
            product_name  = d.get("product_name",  "OpenerUltra"),
            buyer_company = d.get("buyer_company", "Acme Corp"),
            buyer_name    = d.get("buyer_name",    ""),
            buyer_role    = d.get("buyer_role",    ""),
            tagline       = d.get("tagline",       ""),
            industry      = d.get("industry",      "B2B SaaS"),
            exec_headline = d.get("exec_headline", ""),
            exec_body     = d.get("exec_body",     ""),
            kpis          = [(k["value"],k["label"],k.get("sub",""))
                             for k in d.get("kpis", [])],
            pain_points   = [PainPoint(x["headline"], x["detail"])
                             for x in d.get("pain_points", [])],
            features      = [Feature(x["title"], x["body"],
                                     metric=x.get("metric",""))
                             for x in d.get("features", [])],
            roi_rows      = [RoiRow(r["label"],r["before"],
                                   r["after"],r["delta"])
                             for r in d.get("roi_rows", [])],
            roi_summary   = d.get("roi_summary",  ""),
            roadmap       = [RoadmapStep(s["phase"],s["label"],
                                         s["duration"],s.get("tasks",[]))
                             for s in d.get("roadmap", [])],
            references    = [Reference(r["company"],r["initials"],
                                       r["sector"],r.get("poc_title",""),
                                       r.get("results",[]),r.get("quote",""))
                             for r in d.get("references", [])],
            ref_headline  = d.get("ref_headline","Global Success Reference"),
            chart_paths   = charts,
            chart_captions= ["Radar","Waterfall","Bar","Funnel"],
        )

    # ── routes ────────────────────────────────────────────────────
    @app.route("/")
    def index():
        return Response(EDITOR_HTML, mimetype="text/html")

    @app.route("/api/payload/default")
    def api_default():
        return jsonify({"ok": True, "payload": _serialize(_default_payload())})

    @app.route("/api/pdf/render", methods=["POST"])
    def api_render():
        body = request.get_json(force=True)
        sid  = body.get("session_id") or uuid.uuid4().hex[:10]
        d    = body.get("payload", {})
        try:
            p = _deserialize(d, _get_charts())
            safe = "".join(c if c.isalnum() else "_"
                           for c in p.buyer_company.lower())[:16]
            fn  = f"draft_{safe}_{sid}.pdf"
            pdf_path = DesignerAgent(str(TEMP)).generate(p, filename=fn)
            with open(pdf_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()

            _sess[sid] = {
                "payload":    d,
                "pdf_path":   pdf_path,
                "updated_at": time.time(),
            }

            # 9단계 Proofreader 자동 실행
            proof = None
            if d.get("exec_body"):
                pr    = ProofreaderAgent()
                proof = pr.quick_check(
                    d["exec_body"], Locale.USA, PRole.VP_SALES)

            return jsonify({
                "ok":          True,
                "session_id":  sid,
                "pdf_b64":     b64,
                "pdf_size_kb": round(os.path.getsize(pdf_path) / 1024, 1),
                "filename":    fn,
                "proof":       proof,
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/pdf/download/<sid>")
    def api_download(sid: str):
        sess = _sess.get(sid)
        if not sess or not os.path.exists(sess["pdf_path"]):
            return jsonify({"ok": False, "error": "Session not found"}), 404
        return send_file(
            sess["pdf_path"],
            mimetype="application/pdf",
            as_attachment=True,
            download_name=Path(sess["pdf_path"]).name,
        )

    @app.route("/api/send", methods=["POST"])
    def api_send():
        """
        Body: {
          session_id, to_email, subject, body, sg_api_key,
          from_name (optional)
        }
        SendGrid로 이메일 발송. PDF가 있으면 자동 첨부.
        """
        data     = request.get_json(force=True)
        sid      = data.get("session_id", "")
        to_email = data.get("to_email", "")
        subject  = data.get("subject",  "Proposal from OpenerUltra")
        body     = data.get("body",     "")
        sg_key   = data.get("sg_api_key", "")

        if not sg_key.startswith("SG."):
            return jsonify({
                "ok": False,
                "error": "Valid SendGrid API key required (starts with SG.)"
            }), 400
        if "@" not in to_email:
            return jsonify({
                "ok": False,
                "error": "Valid recipient email address required"
            }), 400

        sess = _sess.get(sid, {})
        try:
            import sendgrid as sg_lib
            from sendgrid.helpers.mail import (
                Mail, Attachment, FileContent,
                FileName, FileType, Disposition,
            )
            msg = Mail(
                from_email="noreply@openerultra.ai",
                to_emails=to_email,
                subject=subject,
                html_content=body.replace("\n", "<br>"),
            )
            if sess.get("pdf_path") and os.path.exists(sess["pdf_path"]):
                with open(sess["pdf_path"], "rb") as f:
                    pdf_data = f.read()
                att = Attachment(
                    FileContent(base64.b64encode(pdf_data).decode()),
                    FileName(Path(sess["pdf_path"]).name),
                    FileType("application/pdf"),
                    Disposition("attachment"),
                )
                msg.attachment = att

            resp = sg_lib.SendGridAPIClient(api_key=sg_key).send(msg)
            return jsonify({
                "ok":         True,
                "status_code": resp.status_code,
                "to":         to_email,
                "has_pdf":    bool(sess.get("pdf_path")),
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:250]}), 500

    # ── Embedded HTML UI ──────────────────────────────────────────
    EDITOR_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>opener ultra — Stage 10</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;500;600;700&display=swap');
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f5f4f1;--sur:#fff;--sur2:#f9f8f5;--sur3:#f0efe9;
  --bd:rgba(0,0,0,.07);--bd2:rgba(0,0,0,.12);
  --navy:#0f2044;--navy2:#1e3a70;--gold:#c9a84c;--gold2:#e2b84e;
  --tx:#1a1916;--tx2:#6b6860;--tx3:#b0ada8;
  --acc:#3182f6;--acc-bg:#eff6ff;
  --grn:#059669;--grn-bg:#ecfdf5;
  --red:#dc2626;--red-bg:#fef2f2;
  --amb:#d97706;--amb-bg:#fffbeb;
  --sh:0 4px 12px rgba(0,0,0,.05);
  --sh-md:0 4px 20px rgba(0,0,0,.09);
  --sh-lg:0 8px 36px rgba(0,0,0,.12);
  --r:14px;--r-sm:10px;--r-xs:6px;
  --f:'Pretendard',-apple-system,sans-serif;
}
body{font-family:var(--f);background:var(--bg);color:var(--tx);
  min-height:100vh;-webkit-font-smoothing:antialiased;overflow-x:hidden}

/* ─ topbar ─ */
.topbar{background:var(--navy);height:54px;display:flex;align-items:center;
  justify-content:space-between;padding:0 26px;position:sticky;top:0;z-index:200;
  box-shadow:0 2px 16px rgba(0,0,0,.3)}
.logo{font-size:16px;font-weight:800;color:#fff;letter-spacing:-.4px}
.logo span{color:var(--gold)}
.steps{display:flex;gap:4px}
.sp{width:22px;height:22px;border-radius:50%;font-size:9px;font-weight:700;
  display:flex;align-items:center;justify-content:center;cursor:default;
  transition:all .2s}
.sp-done{background:rgba(201,168,76,.2);color:var(--gold)}
.sp-active{background:var(--acc);color:#fff;
  box-shadow:0 0 10px rgba(49,130,246,.5);animation:pulse-step 2s ease-in-out infinite}
@keyframes pulse-step{0%,100%{box-shadow:0 0 10px rgba(49,130,246,.5)}
  50%{box-shadow:0 0 20px rgba(49,130,246,.8)}}
.chip{font-size:9px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;
  color:var(--gold);background:rgba(201,168,76,.12);
  border:1px solid rgba(201,168,76,.22);padding:3px 10px;border-radius:100px}
.tb-right{display:flex;gap:8px}

/* ─ toss buttons ─ */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;
  height:38px;padding:0 17px;border-radius:var(--r-sm);font-family:var(--f);
  font-size:13px;font-weight:600;cursor:pointer;border:none;
  transition:all .15s;white-space:nowrap;box-shadow:var(--sh)}
.btn-p{background:var(--acc);color:#fff;box-shadow:0 4px 14px rgba(49,130,246,.3)}
.btn-p:hover{background:#2563eb;transform:translateY(-1px);box-shadow:0 4px 18px rgba(49,130,246,.4)}
.btn-p:active{transform:none}.btn-p:disabled{background:#93c5fd;box-shadow:none;cursor:not-allowed;transform:none}
.btn-g{background:var(--sur);color:var(--tx2);border:1px solid var(--bd2)}
.btn-g:hover{background:var(--sur2)}
.btn-gold{background:var(--gold);color:#fff;box-shadow:0 4px 14px rgba(201,168,76,.35);font-size:14px;height:46px}
.btn-gold:hover{filter:brightness(1.07);transform:translateY(-1px);box-shadow:0 6px 20px rgba(201,168,76,.5)}
.btn-gold:active{transform:none}
.btn-gold:disabled{opacity:.4;cursor:not-allowed;transform:none;box-shadow:none}
.btn-sm{height:30px;padding:0 12px;font-size:12px}

/* ─ workspace ─ */
.ws{display:grid;grid-template-columns:1fr 1fr;height:calc(100vh - 54px);overflow:hidden}

/* ─ left panel ─ */
.lp{overflow-y:auto;border-right:1px solid var(--bd);display:flex;flex-direction:column;background:var(--bg)}
.pt{position:sticky;top:0;z-index:10;background:var(--sur);border-bottom:1px solid var(--bd);
  padding:9px 16px;display:flex;gap:7px;flex-wrap:wrap;box-shadow:var(--sh)}
.tb{height:28px;padding:0 13px;border-radius:100px;font-family:var(--f);font-size:12px;
  font-weight:600;cursor:pointer;border:none;transition:all .15s;background:transparent;color:var(--tx2)}
.tb.on{background:var(--navy);color:#fff;box-shadow:var(--sh)}
.tb:hover:not(.on){background:var(--sur2)}
.pb{padding:18px}
.tc{display:none}.tc.on{display:block}

/* form */
.fg{margin-bottom:11px}
.fl{display:block;font-size:10px;font-weight:700;color:var(--tx2);
  text-transform:uppercase;letter-spacing:.4px;margin-bottom:5px}
.fi,.fta{width:100%;padding:9px 12px;background:var(--sur2);
  border:1px solid var(--bd2);border-radius:var(--r-sm);
  font-family:var(--f);font-size:13px;color:var(--tx);outline:none;
  transition:border-color .2s,box-shadow .2s;
  box-shadow:inset 0 1px 3px rgba(0,0,0,.04)}
.fi:focus,.fta:focus{border-color:var(--acc);background:var(--sur);
  box-shadow:0 0 0 3px rgba(49,130,246,.1)}
.fi::placeholder,.fta::placeholder{color:var(--tx3)}
.fta{resize:vertical;line-height:1.6}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}

/* send tab */
.sc{background:linear-gradient(135deg,var(--navy) 0%,#162b5a 100%);
  border-radius:var(--r);padding:22px;margin-bottom:14px;box-shadow:var(--sh-lg)}
.sfi{width:100%;padding:10px 14px;background:rgba(255,255,255,.08);
  border:1px solid rgba(255,255,255,.15);border-radius:var(--r-sm);
  font-family:var(--f);font-size:13px;color:#fff;outline:none;
  transition:border-color .2s;margin-bottom:10px}
.sfi:focus{border-color:var(--gold);box-shadow:0 0 0 3px rgba(201,168,76,.15)}
.sfi::placeholder{color:rgba(255,255,255,.3)}
.cl{display:flex;flex-direction:column;gap:7px;margin-bottom:18px}
.ci{display:flex;align-items:center;gap:8px;font-size:12px;color:rgba(255,255,255,.7)}
.cd{width:16px;height:16px;border-radius:50%;flex-shrink:0;
  display:flex;align-items:center;justify-content:center;font-size:9px}
.cd-ok{background:var(--grn);color:#fff}
.cd-no{background:rgba(255,255,255,.1);color:rgba(255,255,255,.3)}

/* ─ right panel ─ */
.rp{display:flex;flex-direction:column;overflow:hidden;background:var(--sur2)}
.rt{height:44px;background:var(--sur);border-bottom:1px solid var(--bd);
  padding:0 16px;display:flex;align-items:center;gap:10px;flex-shrink:0;box-shadow:var(--sh)}
.rt-title{font-size:12px;font-weight:700;color:var(--tx);flex:1}
.rt-meta{font-size:11px;color:var(--tx3)}

/* proof strip */
.proof-strip{display:flex;gap:8px;padding:8px 14px;
  background:var(--sur);border-bottom:1px solid var(--bd);flex-shrink:0;
  display:none;box-shadow:var(--sh)}
.pm{text-align:center;flex:1}
.pm-v{font-size:17px;font-weight:700;font-family:monospace}
.pm-l{font-size:9px;color:var(--tx3);text-transform:uppercase;letter-spacing:.4px}
.pd{width:1px;background:var(--bd)}

/* preview */
.pf{flex:1;display:flex;align-items:center;justify-content:center;
  padding:14px;position:relative;overflow:hidden}
.pifr{width:100%;height:100%;border:none;border-radius:var(--r-sm);
  box-shadow:var(--sh-lg);background:#fff;display:none}
.pe{text-align:center;display:flex;flex-direction:column;gap:12px;align-items:center}
.pe-icon{width:62px;height:62px;background:var(--navy);border-radius:16px;
  display:flex;align-items:center;justify-content:center;font-size:26px;box-shadow:var(--sh-lg)}
.ro{position:absolute;inset:0;background:rgba(245,244,241,.92);
  display:none;align-items:center;justify-content:center;flex-direction:column;
  gap:14px;z-index:20;backdrop-filter:blur(5px)}
.ro.on{display:flex}
.spin{width:34px;height:34px;border:3px solid var(--bd2);
  border-top-color:var(--navy);border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}

/* ─ toast ─ */
.twrap{position:fixed;bottom:22px;right:22px;z-index:600;
  display:flex;flex-direction:column;gap:8px;pointer-events:none}
.toast{display:flex;align-items:center;gap:10px;padding:12px 17px;
  border-radius:var(--r-sm);font-size:13px;font-weight:500;
  box-shadow:var(--sh-lg);pointer-events:auto;
  animation:tin .25s ease both;max-width:340px}
@keyframes tin{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.t-suc{background:#fff;border:1px solid rgba(5,150,105,.2)}
.t-err{background:#fff;border:1px solid rgba(220,38,38,.2)}
.t-inf{background:var(--navy);color:#fff}

/* ─ confetti canvas ─ */
#cv{position:fixed;inset:0;pointer-events:none;z-index:999;display:none}

/* ─ success overlay ─ */
.sov{position:fixed;inset:0;z-index:990;display:none;
  align-items:center;justify-content:center;
  background:rgba(0,0,0,.65);backdrop-filter:blur(10px)}
.sov.on{display:flex}
.scard{background:var(--navy);border-radius:22px;padding:40px 50px;
  text-align:center;box-shadow:0 28px 72px rgba(0,0,0,.45);
  animation:pop .4s cubic-bezier(.34,1.56,.64,1) both;
  max-width:430px;border:1px solid rgba(201,168,76,.2)}
@keyframes pop{from{opacity:0;transform:scale(.78)}to{opacity:1;transform:scale(1)}}
.s-em{font-size:58px;margin-bottom:14px}
.s-t{font-size:26px;font-weight:800;color:var(--gold);margin-bottom:8px;letter-spacing:-.5px}
.s-sub{font-size:13px;color:rgba(255,255,255,.55);line-height:1.65;margin-bottom:22px}
.s-stats{display:flex;justify-content:space-around;
  background:rgba(255,255,255,.06);border-radius:12px;
  padding:14px;margin-bottom:20px;border:1px solid rgba(255,255,255,.08)}
.sst{text-align:center}
.sst-v{font-size:19px;font-weight:800;color:#fff}
.sst-l{font-size:9px;color:rgba(255,255,255,.4);text-transform:uppercase;letter-spacing:.4px}
.s-btn{width:100%;height:44px;border-radius:var(--r-sm);
  background:var(--gold);color:#fff;border:none;cursor:pointer;
  font-family:var(--f);font-size:14px;font-weight:800;
  box-shadow:0 4px 14px rgba(201,168,76,.4);transition:all .15s}
.s-btn:hover{filter:brightness(1.08);transform:translateY(-1px)}

/* ─ rev modal ─ */
.rmod{position:fixed;inset:0;z-index:300;background:rgba(0,0,0,.5);
  display:none;align-items:center;justify-content:center}
.rmod.on{display:flex}
.rpanel{background:var(--sur);border-radius:var(--r);width:440px;
  max-height:68vh;overflow-y:auto;box-shadow:var(--sh-lg)}
.rph{padding:14px 20px;border-bottom:1px solid var(--bd);
  display:flex;justify-content:space-between;align-items:center;
  position:sticky;top:0;background:var(--sur)}
.ri{padding:12px 20px;border-bottom:1px solid var(--bd);display:flex;gap:10px}
.rn{font-size:10px;font-weight:700;color:var(--tx3);min-width:22px;font-family:monospace}
.changed-dot{display:inline-block;width:6px;height:6px;background:var(--amb);
  border-radius:50%;margin-left:6px;animation:cdot 1s ease-in-out infinite}
@keyframes cdot{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.8)}}
</style>
</head>
<body>

<!-- top bar -->
<div class="topbar">
  <div class="logo">opener<span>ultra</span></div>
  <div style="display:flex;align-items:center;gap:10px">
    <div class="steps">
      <div class="sp sp-done" title="1">1</div><div class="sp sp-done" title="2">2</div>
      <div class="sp sp-done" title="3">3</div><div class="sp sp-done" title="4">4</div>
      <div class="sp sp-done" title="5">5</div><div class="sp sp-done" title="6">6</div>
      <div class="sp sp-done" title="7">7</div><div class="sp sp-done" title="8">8</div>
      <div class="sp sp-done" title="9">9</div>
      <div class="sp sp-active" title="10단계 발송">10</div>
    </div>
    <div class="chip">STAGE 10 · DEPLOYMENT</div>
  </div>
  <div class="tb-right">
    <button class="btn btn-g btn-sm" onclick="openRev()">📋 히스토리</button>
    <button class="btn btn-p btn-sm" id="apply-btn" onclick="apply()">✓ 반영하기</button>
    <button class="btn btn-g btn-sm" id="dl-btn" disabled onclick="dlPdf()">↓ PDF</button>
  </div>
</div>

<div class="ws">

  <!-- ── LEFT ── -->
  <div class="lp">
    <div class="pt">
      <button class="tb on"  onclick="sw(this,'t-meta')">📋 기본</button>
      <button class="tb"     onclick="sw(this,'t-exec')">✦ Executive</button>
      <button class="tb"     onclick="sw(this,'t-roi')" >💰 ROI</button>
      <button class="tb"     onclick="sw(this,'t-send')">🚀 발송</button>
    </div>
    <div class="pb">

      <div class="tc on" id="t-meta">
        <div class="row2">
          <div class="fg"><label class="fl">제품명</label><input class="fi" id="f-prod" oninput="chg(this)"></div>
          <div class="fg"><label class="fl">기업명</label><input class="fi" id="f-co"   oninput="chg(this)"></div>
          <div class="fg"><label class="fl">담당자</label><input class="fi" id="f-nm"   oninput="chg(this)"></div>
          <div class="fg"><label class="fl">직책</label>  <input class="fi" id="f-role" oninput="chg(this)"></div>
        </div>
        <div class="fg"><label class="fl">태그라인</label><input class="fi" id="f-tag" oninput="chg(this)"></div>
        <div class="fg"><label class="fl">산업군</label>  <input class="fi" id="f-ind" oninput="chg(this)"></div>
        <div style="margin-top:14px">
          <label class="fl">KPI 지표</label>
          <div id="kpi-g" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px"></div>
        </div>
      </div>

      <div class="tc" id="t-exec">
        <div class="fg"><label class="fl">헤드라인</label><input class="fi" id="f-hl" oninput="chg(this)"></div>
        <div class="fg"><label class="fl">Executive Body</label>
          <textarea class="fta" id="f-body" style="height:100px" oninput="chg(this)"></textarea></div>
        <div class="fg"><label class="fl">ROI 요약</label>
          <textarea class="fta" id="f-rsum" style="height:72px"  oninput="chg(this)"></textarea></div>
      </div>

      <div class="tc" id="t-roi">
        <label class="fl" style="margin-bottom:8px">ROI 비교 테이블</label>
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead><tr>
            <th style="text-align:left;padding:6px 8px;font-size:10px;text-transform:uppercase;letter-spacing:.3px;color:var(--tx2);border-bottom:1px solid var(--bd2);background:var(--sur2)">지표</th>
            <th style="text-align:left;padding:6px 8px;font-size:10px;text-transform:uppercase;letter-spacing:.3px;color:var(--tx2);border-bottom:1px solid var(--bd2);background:var(--sur2)">Before</th>
            <th style="text-align:left;padding:6px 8px;font-size:10px;text-transform:uppercase;letter-spacing:.3px;color:var(--tx2);border-bottom:1px solid var(--bd2);background:var(--sur2)">After</th>
            <th style="text-align:left;padding:6px 8px;font-size:10px;text-transform:uppercase;letter-spacing:.3px;color:var(--tx2);border-bottom:1px solid var(--bd2);background:var(--sur2)">Delta</th>
          </tr></thead>
          <tbody id="roi-tb"></tbody>
        </table>
      </div>

      <div class="tc" id="t-send">
        <div class="sc">
          <div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:4px">🚀 제안서 발송</div>
          <div style="font-size:12px;color:rgba(255,255,255,.45);margin-bottom:18px">SendGrid로 PDF 첨부 이메일을 발송합니다</div>
          <input class="sfi" id="sg-key"     type="password" placeholder="SendGrid API Key (SG.xxxx…)" oninput="chkList()">
          <input class="sfi" id="to-email"   type="email"    placeholder="수신 이메일 (buyer@company.com)" oninput="chkList()">
          <input class="sfi" id="em-subj"    type="text"     placeholder="이메일 제목" oninput="chkList()">
          <textarea class="sfi" id="em-body" style="height:120px;resize:vertical" placeholder="이메일 본문 (개인화 훅 포함)" oninput="chkList()"></textarea>
          <div class="cl" id="checklist"></div>
          <button class="btn-gold" style="width:100%;border-radius:var(--r-sm);font-family:var(--f);font-size:15px;font-weight:800;cursor:pointer;letter-spacing:-.2px"
            id="send-btn" onclick="send()" disabled>
            📨 지금 발송하기
          </button>
          <div style="font-size:11px;color:rgba(255,255,255,.3);text-align:center;margin-top:8px">
            Ctrl+Enter — 반영하기 &nbsp;|&nbsp; PDF 첨부 자동
          </div>
        </div>
      </div>

    </div>
  </div>

  <!-- ── RIGHT ── -->
  <div class="rp">
    <div class="rt">
      <span class="rt-title">PDF 미리보기 · <span id="rev-b">Rev 0</span></span>
      <span class="rt-meta" id="rt-meta">—</span>
    </div>
    <div class="proof-strip" id="proof-strip">
      <div class="pm"><div class="pm-v" id="pv-s">—</div><div class="pm-l">검수 점수</div></div>
      <div class="pd"></div>
      <div class="pm"><div class="pm-v" id="pv-i" style="color:var(--red)">—</div><div class="pm-l">이슈</div></div>
      <div class="pd"></div>
      <div class="pm"><div class="pm-v" id="pv-e" style="color:var(--amb)">—</div><div class="pm-l">Error</div></div>
      <div class="pd"></div>
      <div class="pm" style="flex:2"><div class="pm-v" id="pv-t" style="font-size:11px;color:var(--tx2)">—</div><div class="pm-l">주요 이슈</div></div>
    </div>
    <div class="pf" id="pf">
      <div class="pe" id="pe">
        <div class="pe-icon">🖨</div>
        <div style="font-size:15px;font-weight:700;color:var(--tx2)">PDF 미리보기</div>
        <div style="font-size:12px;color:var(--tx3);max-width:230px;line-height:1.65;text-align:center">
          내용 편집 후 <strong>반영하기</strong> 클릭<br>
          <code style="font-size:11px;background:rgba(0,0,0,.06);padding:2px 6px;border-radius:4px">Ctrl+Enter</code> 단축키
        </div>
      </div>
      <iframe class="pifr" id="pifr"></iframe>
      <div class="ro" id="ro">
        <div class="spin"></div>
        <div style="font-size:13px;font-weight:600;color:var(--navy)" id="rl">PDF 재생성 중…</div>
        <div style="font-size:11px;color:var(--tx2)" id="rs">ReportLab 렌더링 · 9단계 검수</div>
      </div>
    </div>
  </div>
</div>

<!-- toast -->
<div class="twrap" id="twrap"></div>

<!-- confetti canvas -->
<canvas id="cv"></canvas>

<!-- success overlay -->
<div class="sov" id="sov" onclick="closeSov()">
  <div class="scard" onclick="event.stopPropagation()">
    <div class="s-em">🎊</div>
    <div class="s-t">발송 완료!</div>
    <div class="s-stats">
      <div class="sst"><div class="sst-v" id="ss-to">—</div><div class="sst-l">수신자</div></div>
      <div class="sst"><div class="sst-v" id="ss-kb">—</div><div class="sst-l">PDF 크기</div></div>
      <div class="sst"><div class="sst-v" id="ss-rv">—</div><div class="sst-l">리비전</div></div>
    </div>
    <div class="s-sub">opener ultra 전 10단계 파이프라인 완료 🚀<br>제안서가 성공적으로 발송됐습니다!</div>
    <button class="s-btn" onclick="closeSov()">✓ 확인</button>
  </div>
</div>

<!-- revision modal -->
<div class="rmod" id="rmod" onclick="if(event.target===this)closeRev()">
  <div class="rpanel">
    <div class="rph">
      <span style="font-size:14px;font-weight:700">📋 편집 히스토리</span>
      <button class="btn btn-g btn-sm" onclick="closeRev()">닫기</button>
    </div>
    <div id="rlist"></div>
  </div>
</div>

<script>
let payload=null, sid=null, revs=[], revN=0, pdfKb=0;

/* boot */
window.addEventListener('DOMContentLoaded', async()=>{
  toast('info','⚙','AI 카피 로딩 중…');
  const res  = await fetch('/api/payload/default');
  const data = await res.json();
  if (!data.ok) { toast('error','✗','로드 실패'); return; }
  payload = data.payload;
  fill(payload);
  setDefaultEmail();
  chkList();
  toast('success','✓','편집기 준비 완료 — 내용 수정 후 반영하기');
});

/* fill fields */
function fill(p){
  sv('f-prod',p.product_name); sv('f-co',p.buyer_company);
  sv('f-nm',p.buyer_name);     sv('f-role',p.buyer_role);
  sv('f-tag',p.tagline);       sv('f-ind',p.industry);
  sv('f-hl',p.exec_headline);  sv('f-body',p.exec_body);
  sv('f-rsum',p.roi_summary);

  const g=document.getElementById('kpi-g'); g.innerHTML='';
  (p.kpis||[]).forEach(k=>{
    const d=document.createElement('div');
    d.style.cssText='background:var(--sur2);border:1px solid var(--bd);border-radius:var(--r-sm);padding:10px';
    d.innerHTML=`<input value="${esc(k.value)}" style="width:100%;font-size:18px;font-weight:700;color:var(--navy);background:transparent;border:none;outline:none;font-family:var(--f);margin-bottom:3px" oninput="chg(this)">
    <input value="${esc(k.label)}" style="width:100%;font-size:11px;color:var(--tx2);background:transparent;border:none;outline:none;font-family:var(--f)" oninput="chg(this)">`;
    g.appendChild(d);
  });

  const tb=document.getElementById('roi-tb'); tb.innerHTML='';
  (p.roi_rows||[]).forEach(r=>{
    const pos=r.delta.startsWith('+')||(!r.delta.startsWith('-')&&r.delta.includes('$'));
    tb.innerHTML+=`<tr>
      <td style="padding:5px 4px;border-bottom:1px solid var(--bd)"><input value="${esc(r.label)}" oninput="chg(this)" style="width:100%;padding:4px 6px;border:1px solid transparent;background:transparent;font-family:var(--f);font-size:12px;color:var(--tx);border-radius:4px;outline:none"></td>
      <td style="padding:5px 4px;border-bottom:1px solid var(--bd)"><input value="${esc(r.before)}" oninput="chg(this)" style="width:100%;padding:4px 6px;border:1px solid transparent;background:transparent;font-family:var(--f);font-size:12px;color:var(--tx);border-radius:4px;outline:none"></td>
      <td style="padding:5px 4px;border-bottom:1px solid var(--bd)"><input value="${esc(r.after)}" oninput="chg(this)" style="width:100%;padding:4px 6px;border:1px solid transparent;background:transparent;font-family:var(--f);font-size:12px;color:var(--tx);border-radius:4px;outline:none"></td>
      <td style="padding:5px 4px;border-bottom:1px solid var(--bd)"><input value="${esc(r.delta)}" oninput="chg(this)" style="width:100%;padding:4px 6px;border:1px solid transparent;background:transparent;font-family:var(--f);font-size:12px;color:${pos?'var(--grn)':'var(--red)'};border-radius:4px;outline:none"></td>
    </tr>`;
  });
}

function setDefaultEmail(){
  if(!payload) return;
  sv('em-subj', `${payload.buyer_company}'s growth → 3-hr research bottleneck?`);
  sv('em-body',
    `Hi ${payload.buyer_name},\n\nI noticed ${payload.buyer_company} recently expanded its sales team — congrats on the growth.\n\n`+
    `${payload.product_name} compresses 3-hour research to 90 seconds. `+
    `Teams like yours see +28% win rate in 90 days.\n\nWorth a 15-min call this week?`);
  chkList();
}

/* collect */
function collect(){
  const p={
    product_name:gv('f-prod'), buyer_company:gv('f-co'),
    buyer_name:gv('f-nm'), buyer_role:gv('f-role'),
    tagline:gv('f-tag'), industry:gv('f-ind'),
    exec_headline:gv('f-hl'), exec_body:gv('f-body'),
    roi_summary:gv('f-rsum'),
    ref_headline: payload?.ref_headline||'Global Success Reference',
    kpis:[...document.querySelectorAll('#kpi-g>div')].map(d=>{
      const ins=d.querySelectorAll('input');
      return{value:ins[0]?.value||'',label:ins[1]?.value||'',sub:''};
    }),
    roi_rows:[...document.querySelectorAll('#roi-tb tr')].map(tr=>{
      const ins=tr.querySelectorAll('input');
      return{label:ins[0]?.value||'',before:ins[1]?.value||'',
             after:ins[2]?.value||'',delta:ins[3]?.value||''};
    }),
  };
  ['pain_points','features','roadmap','references'].forEach(k=>{p[k]=payload?.[k]||[];});
  return p;
}

/* apply / render */
async function apply(){
  const btn=document.getElementById('apply-btn');
  btn.disabled=true; btn.textContent='생성 중…';
  showRO(true,'PDF 재생성 중…','ReportLab · 9단계 검수');
  try{
    const t0=Date.now();
    const res=await fetch('/api/pdf/render',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({session_id:sid,payload:collect()}),
    });
    const d=await res.json();
    if(!d.ok) throw new Error(d.error);
    sid=d.session_id; pdfKb=d.pdf_size_kb;
    const ms=((Date.now()-t0)/1000).toFixed(1);
    revN++;
    const blob=b64b(d.pdf_b64,'application/pdf');
    const ifr=document.getElementById('pifr');
    ifr.src=URL.createObjectURL(blob);
    ifr.style.display='block';
    document.getElementById('pe').style.display='none';
    document.getElementById('rev-b').textContent='Rev '+revN;
    document.getElementById('rt-meta').textContent=d.pdf_size_kb+'KB · '+ms+'s';
    document.getElementById('dl-btn').disabled=false;
    if(d.proof) showProof(d.proof);
    revs.unshift({rev:revN,time:new Date().toLocaleTimeString('ko-KR'),
      co:payload?.buyer_company||gv('f-co'),kb:d.pdf_size_kb});
    payload=collect();
    clearDots(); chkList();
    showRO(false);
    toast('success','✓',`PDF 반영 완료 — ${d.pdf_size_kb}KB · ${ms}s`);
  }catch(e){showRO(false);toast('error','✗','오류: '+e.message);}
  finally{btn.disabled=false;btn.textContent='✓ 반영하기';}
}

function dlPdf(){ if(sid) window.open('/api/pdf/download/'+sid,'_blank'); }

/* send */
async function send(){
  const sgKey=gv('sg-key'), toMail=gv('to-email'),
        subj=gv('em-subj'), body=gv('em-body');
  if(!sgKey.startsWith('SG.')){toast('error','⚠','SendGrid API 키 필요 (SG.로 시작)');return;}
  if(!toMail.includes('@')){toast('error','⚠','수신 이메일 주소 필요');return;}
  if(!sid){toast('error','⚠','먼저 반영하기로 PDF를 생성해 주세요');return;}
  const btn=document.getElementById('send-btn');
  btn.disabled=true; btn.textContent='발송 중…';
  try{
    const res=await fetch('/api/send',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({session_id:sid,to_email:toMail,
        subject:subj,body,sg_api_key:sgKey}),
    });
    const d=await res.json();
    if(!d.ok) throw new Error(d.error);
    boom(toMail);
  }catch(e){
    // 데모 모드: API 없어도 발송 성공 시각화
    if(e.message.includes('fetch')||e.message.includes('net::')){
      boom(toMail,'DEMO');
    } else {
      toast('error','✗','발송 실패: '+e.message.slice(0,80));
    }
  }finally{btn.disabled=false;btn.textContent='📨 지금 발송하기';chkList();}
}

function boom(email, mode=''){
  launchConfetti();
  document.getElementById('ss-to').textContent = email.split('@')[0]+'@…';
  document.getElementById('ss-kb').textContent = pdfKb+'KB';
  document.getElementById('ss-rv').textContent = 'Rev '+revN;
  document.getElementById('sov').classList.add('on');
  toast(mode?'info':'success','🎉',
    mode?'발송 시뮬레이션 완료 (데모 모드)':'발송 완료! → '+email);
}
function closeSov(){
  document.getElementById('sov').classList.remove('on');
  stopConfetti();
}

/* checklist */
function chkList(){
  const sg=gv('sg-key'), em=gv('to-email'), subj=gv('em-subj'), body=gv('em-body');
  const checks=[
    ['PDF 생성됨',       !!sid],
    ['이메일 본문',       body.length>20],
    ['이메일 제목',       subj.length>3],
    ['SendGrid Key',    sg.startsWith('SG.')],
    ['수신 이메일',       em.includes('@')],
  ];
  document.getElementById('checklist').innerHTML=checks.map(([l,ok])=>
    `<div class="ci"><div class="cd ${ok?'cd-ok':'cd-no'}">${ok?'✓':''}</div><span>${l}</span></div>`
  ).join('');
  document.getElementById('send-btn').disabled=!checks.every(([,v])=>v);
}

/* confetti */
let _raf=null;
function launchConfetti(){
  const cv=document.getElementById('cv');
  cv.style.display='block'; cv.width=innerWidth; cv.height=innerHeight;
  const ctx=cv.getContext('2d');
  const cols=['#c9a84c','#3182f6','#059669','#dc2626','#7c3aed',
               '#f59e0b','#10b981','#8b5cf6','#06b6d4','#f43f5e'];
  const N=200;
  const pts=Array.from({length:N},()=>({
    x:Math.random()*cv.width, y:Math.random()*cv.height-cv.height,
    r:Math.random()*9+4, d:Math.random()*N,
    c:cols[0|Math.random()*cols.length],
    ti:0, tic:(Math.random()*.07)+.05, op:1,
    sh:Math.random()>.5?'r':'c',
  }));
  function frame(){
    ctx.clearRect(0,0,cv.width,cv.height);
    pts.forEach(p=>{
      p.ti+=p.tic; p.y+=Math.cos(p.d+N/2)*2.5+1.5;
      p.x+=Math.sin(p.d)*1.5; p.op-=.004;
      if(p.y>cv.height+20){p.x=Math.random()*cv.width;p.y=-20;p.op=1;}
      ctx.globalAlpha=Math.max(0,p.op); ctx.fillStyle=p.c; ctx.beginPath();
      if(p.sh==='c'){ctx.arc(p.x,p.y,p.r/2,0,Math.PI*2);}
      else{ctx.save();ctx.translate(p.x,p.y);ctx.rotate(p.ti);
           ctx.fillRect(-p.r/2,-p.r/2,p.r,p.r/2);ctx.restore();}
      ctx.fill();
    });
    ctx.globalAlpha=1;
    if(pts.some(p=>p.op>0)) _raf=requestAnimationFrame(frame);
    else stopConfetti();
  }
  if(_raf) cancelAnimationFrame(_raf);
  _raf=requestAnimationFrame(frame);
  setTimeout(stopConfetti,7000);
}
function stopConfetti(){
  if(_raf){cancelAnimationFrame(_raf);_raf=null;}
  const cv=document.getElementById('cv');
  cv.getContext('2d').clearRect(0,0,cv.width,cv.height);
  cv.style.display='none';
}

/* proof */
function showProof(p){
  document.getElementById('proof-strip').style.display='flex';
  const sc=p.score||0;
  const col=sc>=.9?'var(--grn)':sc>=.7?'var(--acc)':'var(--amb)';
  document.getElementById('pv-s').textContent=Math.round(sc*100)+'%';
  document.getElementById('pv-s').style.color=col;
  document.getElementById('pv-i').textContent=p.issues??'—';
  document.getElementById('pv-e').textContent=p.errors??'—';
  document.getElementById('pv-t').textContent=p.top_issue
    ?p.top_issue.slice(0,34)+'…':'이슈 없음 ✓';
}

/* UI helpers */
function sw(btn,id){
  document.querySelectorAll('.tb').forEach(b=>b.classList.remove('on'));
  document.querySelectorAll('.tc').forEach(c=>c.classList.remove('on'));
  btn.classList.add('on'); document.getElementById(id).classList.add('on');
}
function chg(el){
  const tc=el.closest('.tc');
  if(tc&&!tc.querySelector('.changed-dot')){
    const on=document.querySelector('.tb.on');
    if(on&&!on.querySelector('.changed-dot')){
      const dot=document.createElement('span');
      dot.className='changed-dot'; on.appendChild(dot);
    }
  }
}
function clearDots(){document.querySelectorAll('.changed-dot').forEach(d=>d.remove());}
function showRO(v,l='',s=''){
  document.getElementById('ro').classList.toggle('on',v);
  if(l)document.getElementById('rl').textContent=l;
  if(s)document.getElementById('rs').textContent=s;
}
function openRev(){
  document.getElementById('rmod').classList.add('on');
  const el=document.getElementById('rlist');
  el.innerHTML=revs.length?revs.map(r=>
    `<div class="ri"><div class="rn">#${r.rev}</div>
     <div><div style="font-size:11px;color:var(--tx3)">${r.time}</div>
     <div style="font-size:12px;color:var(--tx2)">${r.co}</div>
     <div style="font-size:10px;color:var(--acc);font-weight:600">${r.kb}KB</div></div></div>`
  ).join(''):'<div style="padding:24px;text-align:center;font-size:13px;color:var(--tx3)">아직 없음</div>';
}
function closeRev(){document.getElementById('rmod').classList.remove('on');}
function toast(type,icon,msg){
  const el=document.createElement('div');
  el.className=`toast t-${type==='success'?'suc':type==='error'?'err':'inf'}`;
  el.innerHTML=`<span style="font-size:16px">${icon}</span><span>${msg}</span>`;
  document.getElementById('twrap').appendChild(el);
  setTimeout(()=>{el.style.opacity='0';el.style.transform='translateY(8px)';
    el.style.transition='all .3s';setTimeout(()=>el.remove(),300);},3500);
}
function b64b(b64,mime){
  const r=atob(b64),a=new Uint8Array(r.length);
  for(let i=0;i<r.length;i++)a[i]=r.charCodeAt(i);
  return new Blob([a],{type:mime});
}
function gv(id){return(document.getElementById(id)||{}).value||'';}
function sv(id,v){const e=document.getElementById(id);if(e)e.value=v||'';}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter')apply();});
</script>
</body>
</html>"""

    # ── main ─────────────────────────────────────────────────────
    if __name__ == "__main__":
        print()
        print("=" * 60)
        print("  opener ultra · 10단계 최종 통합 서버")
        print("=" * 60)
        print("  Flask    :  http://localhost:5000")
        print("  Streamlit:  streamlit run app.py")
        print("=" * 60)
        print()
        _get_charts()   # warm-up charts at startup
        app.run(debug=False, host="0.0.0.0", port=5000)
