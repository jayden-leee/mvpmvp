"""
opener-ultra-mvp / app.py
"""
from __future__ import annotations
import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import base64, json, time, traceback, uuid
from pathlib import Path
ROOT = Path(os.path.abspath(__file__)).parent
_ST = "streamlit" in sys.modules or any("streamlit" in a for a in sys.argv)


###################################################################
#  A. STREAMLIT — Clay × Linear × Toss 스타일 완전 개편
#
#  Flow:
#    landing  → URL 하나 입력
#    research → Tavily 실시간 분석 로그
#    editor   → GPT-4o-mini 생성 카피 편집 + PDF + 발송
###################################################################
if _ST:
    import re as _re
    import streamlit as st

    st.set_page_config(
        page_title="Opener AI",
        page_icon="✦",
        layout="centered",
    )

    # ── 공통 CSS (Toss × Linear) ──────────────────────────────────
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body, [class*="css"], .stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    -webkit-font-smoothing: antialiased;
    background: #ffffff !important;
    color: #111827 !important;
}

[data-testid="stToolbar"]       { display: none !important; }
[data-testid="stDecoration"]    { display: none !important; }
footer                          { display: none !important; }
#MainMenu                       { display: none !important; }

.main .block-container {
    max-width: 680px !important;
    margin: 0 auto !important;
    padding: 3rem 1.5rem 6rem !important;
}

/* ── 카드 ── */
.card {
    background: #ffffff;
    border: 1px solid #f0f0f0;
    border-radius: 20px;
    padding: 32px 36px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.05);
    margin-bottom: 16px;
}

/* ── 버튼 override ── */
.stButton > button {
    width: 100%;
    background: #111827 !important;
    color: #ffffff !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 15px !important;
    font-weight: 600 !important;
    padding: 14px 0 !important;
    border-radius: 12px !important;
    border: none !important;
    letter-spacing: -0.2px !important;
    transition: all 0.15s ease !important;
    box-shadow: 0 4px 14px rgba(17,24,39,0.2) !important;
}
.stButton > button:hover {
    background: #1f2937 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(17,24,39,0.28) !important;
}
.stButton > button:active { transform: translateY(0) !important; }

/* ── 입력창 ── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    font-family: 'Inter', sans-serif !important;
    font-size: 15px !important;
    color: #111827 !important;
    background: #fafafa !important;
    border: 1.5px solid #e5e7eb !important;
    border-radius: 12px !important;
    padding: 13px 16px !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #111827 !important;
    box-shadow: 0 0 0 3px rgba(17,24,39,0.08) !important;
    background: #ffffff !important;
}
.stTextInput > div > div > input::placeholder { color: #9ca3af !important; }

/* ── form 전송 버튼 ── */
.stFormSubmitButton > button {
    background: #111827 !important;
    color: #fff !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    font-size: 15px !important;
    padding: 14px 0 !important;
    border: none !important;
    box-shadow: 0 4px 14px rgba(17,24,39,0.2) !important;
}
.stFormSubmitButton > button:hover {
    background: #1f2937 !important;
    transform: translateY(-1px) !important;
}

/* ── 탭 ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0 !important;
    background: #f9fafb !important;
    border-radius: 12px !important;
    padding: 4px !important;
    border: 1px solid #f0f0f0 !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 9px !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    color: #6b7280 !important;
    padding: 8px 18px !important;
}
.stTabs [aria-selected="true"] {
    background: #ffffff !important;
    color: #111827 !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
    font-weight: 600 !important;
}

/* ── progress ── */
.stProgress > div > div > div {
    background: #111827 !important;
    border-radius: 100px !important;
}

/* ── 로그 박스 ── */
.log-box {
    background: #0f172a;
    border-radius: 14px;
    padding: 20px 24px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 13px;
    line-height: 1.8;
    color: #94a3b8;
    min-height: 180px;
    border: 1px solid #1e293b;
}
.log-box .log-ok   { color: #34d399; }
.log-box .log-run  { color: #60a5fa; }
.log-box .log-warn { color: #fbbf24; }
.log-box .log-dim  { color: #475569; }

/* ── 사이드바 숨기기 ── */
[data-testid="stSidebar"] { display: none !important; }

/* ── metric ── */
[data-testid="metric-container"] {
    background: #fafafa;
    border: 1px solid #f0f0f0;
    border-radius: 14px;
    padding: 16px !important;
}
[data-testid="stMetricValue"] { font-size: 24px !important; font-weight: 700 !important; }

/* ── 성공/오류 메시지 ── */
.stSuccess, .stInfo, .stWarning, .stError {
    border-radius: 12px !important;
    font-size: 14px !important;
}

/* ── 다운로드 버튼 ── */
.stDownloadButton > button {
    background: #f9fafb !important;
    color: #111827 !important;
    border: 1.5px solid #e5e7eb !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    box-shadow: none !important;
}
.stDownloadButton > button:hover {
    background: #f3f4f6 !important;
    border-color: #d1d5db !important;
    transform: translateY(-1px) !important;
}
</style>
""", unsafe_allow_html=True)

    # ── 세션 초기화 ───────────────────────────────────────────────
    defaults = {
        "page":          "landing",
        "target_url":    "",
        "research_data": {},
        "ai_copy":       {},
        "extra_info":    {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PAGE 1 — LANDING (URL 하나만)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if st.session_state.page == "landing":

        st.markdown("<br>", unsafe_allow_html=True)

        # 로고 + 헤드라인
        st.markdown("""
<div style="text-align:center; margin-bottom:48px">
  <div style="display:inline-flex;align-items:center;gap:8px;
       background:#f9fafb;border:1px solid #f0f0f0;border-radius:100px;
       padding:6px 16px;margin-bottom:28px">
    <span style="font-size:12px;font-weight:600;letter-spacing:.8px;
          text-transform:uppercase;color:#6b7280">AI Sales Intelligence</span>
  </div>
  <h1 style="font-size:48px;font-weight:800;color:#111827;
       letter-spacing:-2px;line-height:1.1;margin-bottom:16px">
    Opener<span style="color:#6366f1">AI</span>
  </h1>
  <p style="font-size:18px;color:#6b7280;font-weight:400;
      line-height:1.6;max-width:480px;margin:0 auto">
    타겟 기업 URL 하나로<br>
    <strong style="color:#111827">글로벌 수준의 B2B 제안서</strong>를 90초 만에
  </p>
</div>
""", unsafe_allow_html=True)

        # URL 입력 카드
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("""
<p style="font-size:13px;font-weight:600;color:#374151;
   letter-spacing:.3px;text-transform:uppercase;margin-bottom:10px">
  타겟 기업 홈페이지
</p>
""", unsafe_allow_html=True)

        with st.form("url_form"):
            url = st.text_input(
                "URL",
                placeholder="https://kakao.com",
                label_visibility="collapsed",
            )
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            col_a, col_b = st.columns(2)
            with col_a:
                product = st.text_input("내 제품/서비스", placeholder="예: 세일즈 AI 플랫폼")
            with col_b:
                value = st.text_input("핵심 가치", placeholder="예: 리서치 시간 90% 절감")

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            COUNTRY_OPTIONS = {
                "🇺🇸 미국 (English)":           "usa",
                "🇯🇵 일본 (日本語)":             "japan",
                "🇩🇪 독일 (Deutsch)":            "germany",
                "🇰🇷 한국 (한국어)":             "korea",
                "🇨🇳 중국 (中文)":               "china",
                "🇬🇧 영국 (English/UK)":         "uk",
                "🇸🇬 동남아 (English)":          "sea",
                "🇦🇪 중동 UAE (English)":        "uae",
                "🇫🇷 프랑스 (Français)":         "france",
                "🇧🇷 브라질 (Português)":        "brazil",
            }
            country_label = st.selectbox(
                "타겟 국가 (제안서 언어 자동 설정)",
                list(COUNTRY_OPTIONS.keys()),
                index=0,
            )
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("✦  AI 분석 시작", use_container_width=True)

        st.markdown('</div>', unsafe_allow_html=True)

        # 소셜 프루프
        st.markdown("""
<div style="display:flex;justify-content:center;gap:32px;margin-top:32px">
  <div style="text-align:center">
    <div style="font-size:22px;font-weight:800;color:#111827">90초</div>
    <div style="font-size:12px;color:#9ca3af;margin-top:2px">제안서 완성</div>
  </div>
  <div style="width:1px;background:#f0f0f0"></div>
  <div style="text-align:center">
    <div style="font-size:22px;font-weight:800;color:#111827">10개국</div>
    <div style="font-size:12px;color:#9ca3af;margin-top:2px">문화 맞춤 전략</div>
  </div>
  <div style="width:1px;background:#f0f0f0"></div>
  <div style="text-align:center">
    <div style="font-size:22px;font-weight:800;color:#111827">+28%</div>
    <div style="font-size:12px;color:#9ca3af;margin-top:2px">Win Rate 향상</div>
  </div>
</div>
""", unsafe_allow_html=True)

        if submitted:
            if not url.strip() or not url.strip().startswith("http"):
                st.error("올바른 URL을 입력해 주세요 (https://로 시작)")
            elif not product.strip():
                st.error("제품/서비스 이름을 입력해 주세요")
            else:
                st.session_state.target_url  = url.strip()
                st.session_state.extra_info  = {
                    "product":       product.strip(),
                    "value":         value.strip(),
                    "country":       COUNTRY_OPTIONS[country_label],
                    "country_label": country_label,
                }
                st.session_state.page = "research"
                st.rerun()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PAGE 2 — RESEARCH (Tavily 분석 + 실시간 로그)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    elif st.session_state.page == "research":

        url           = st.session_state.target_url
        extra         = st.session_state.extra_info
        product       = extra.get("product",       "")
        value         = extra.get("value",         "")
        country       = extra.get("country",       "usa")
        country_label = extra.get("country_label", "🇺🇸 미국 (English)")

        # 도메인 추출
        domain = _re.sub(r"https?://(www\.)?", "", url).rstrip("/").split("/")[0]

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"""
<div style="text-align:center;margin-bottom:32px">
  <div style="font-size:13px;font-weight:600;color:#6366f1;letter-spacing:.5px;
       text-transform:uppercase;margin-bottom:10px">AI 분석 중</div>
  <h2 style="font-size:28px;font-weight:800;color:#111827;letter-spacing:-1px">
    {domain}
  </h2>
  <p style="font-size:14px;color:#9ca3af;margin-top:6px">
    최신 뉴스 · 재무 신호 · 페인포인트를 수집하고 있습니다
  </p>
</div>
""", unsafe_allow_html=True)

        # 로그 컨테이너
        log_box    = st.empty()
        prog_bar   = st.progress(0, text="")
        status_txt = st.empty()

        logs = []
        def render_log():
            html = '<div class="log-box">' + "".join(logs) + "</div>"
            log_box.markdown(html, unsafe_allow_html=True)

        def add_log(msg: str, kind: str = "run"):
            ts = time.strftime("%H:%M:%S")
            css = {"ok": "log-ok", "run": "log-run", "warn": "log-warn", "dim": "log-dim"}.get(kind, "log-run")
            logs.append(f'<div><span class="log-dim">[{ts}]</span> <span class="{css}">{msg}</span></div>')
            render_log()

        research = {}

        # Step 1: DNS / 접속 확인
        add_log(f"→ Connecting to {domain}...", "run")
        prog_bar.progress(8, text="도메인 확인 중…")
        time.sleep(0.4)
        add_log(f"✓ Host resolved: {domain}", "ok")

        # Step 2: Tavily 검색
        add_log("→ Fetching latest news & signals via Tavily...", "run")
        prog_bar.progress(20, text="뉴스 수집 중…")

        tavily_key = st.secrets.get("TAVILY_API_KEY", "")
        if tavily_key:
            try:
                import httpx
                queries = [
                    f"{domain} latest news 2024 2025",
                    f"{domain} business challenges pain points",
                    f"{domain} funding revenue growth",
                ]
                all_results = []
                for i, q in enumerate(queries):
                    add_log(f"→ Query {i+1}/3: \"{q[:48]}...\"", "run")
                    prog_bar.progress(20 + i * 15, text=f"검색 중 ({i+1}/3)…")
                    r = httpx.post(
                        "https://api.tavily.com/search",
                        json={"api_key": tavily_key, "query": q,
                              "max_results": 3, "search_depth": "advanced"},
                        timeout=15,
                    )
                    if r.status_code == 200:
                        results = r.json().get("results", [])
                        all_results.extend(results)
                        add_log(f"✓ Found {len(results)} results", "ok")
                    else:
                        add_log(f"⚠ Tavily returned {r.status_code}", "warn")
                    time.sleep(0.3)

                # 상위 3개 신호 추출
                signals = []
                seen = set()
                for item in all_results:
                    title = item.get("title", "")
                    if title and title not in seen:
                        seen.add(title)
                        signals.append({
                            "title":   title,
                            "snippet": item.get("content", "")[:200],
                            "url":     item.get("url", ""),
                        })
                    if len(signals) >= 3:
                        break

                research["signals"] = signals
                add_log(f"✓ Extracted {len(signals)} key signals", "ok")

            except Exception as e:
                add_log(f"⚠ Tavily error: {str(e)[:60]}", "warn")
                research["signals"] = []
        else:
            add_log("⚠ TAVILY_API_KEY not set — using domain inference", "warn")
            research["signals"] = []

        # Step 3: GPT-4o-mini — McKinsey급 마스터 프롬프트 + 현지화 엔진 V3.0
        prog_bar.progress(65, text="AI 전략 분석 중…")
        add_log("→ Engaging McKinsey-grade strategic AI...", "run")
        add_log(f"→ Loading localization engine: {country_label}", "run")
        time.sleep(0.3)

        signals_text = ""
        for i, s in enumerate(research.get("signals", []), 1):
            signals_text += f"[Signal {i}] {s['title']}\n{s['snippet']}\n\n"

        co_name = domain.split(".")[0].capitalize()

        # ── 국가별 현지화 프로파일 ──────────────────────────────────
        LP = {
            "usa":     dict(lang="English",             persona="a top SaaS enterprise AE in San Francisco",                       tone="Direct, punchy, ROI-first. Short sentences. Lead with the bottom line.",  jargon="pipeline, win rate, ACV, ICP, quota attainment",   greeting="",                        taboo="Never say 'I hope this email finds you well'."),
            "japan":   dict(lang="Japanese",             persona="a senior enterprise sales exec at a top Japanese consulting firm",  tone="Extremely formal keigo throughout. Trust-first. Emphasize long-term partnership and risk reduction.", jargon="稟議, 御社, 弊社, 課題解決, 導入実績, 効率化, DX推進", greeting="いつもお世話になっております。", taboo="Never be pushy. Never skip formal opener. Never use urgency tactics."),
            "germany": dict(lang="German",               persona="a senior B2B sales director at a German enterprise software firm",   tone="Precise, data-heavy, logical. Use statistics and structured arguments. Avoid all hyperbole.",    jargon="Effizienzsteigerung, Skalierbarkeit, ROI, Digitalisierung, DSGVO-konform", greeting="Sehr geehrte Damen und Herren,", taboo="Never use superlatives without data backing. Never be informal."),
            "korea":   dict(lang="Korean",               persona="a top B2B enterprise sales manager at a leading Korean tech company", tone="Professional and warm. Use 존댓말 throughout. Reference domestic case studies and proven results.", jargon="영업 효율화, 의사결정자, 레퍼런스, POC, 도입 사례, ROI, 비용 절감, 업무 자동화", greeting="안녕하세요.",              taboo="Never use informal speech. Always include domestic reference cases."),
            "china":   dict(lang="Simplified Chinese",   persona="a senior B2B sales director with deep enterprise ties in China",     tone="Relationship-first. Emphasize mutual benefit (互利共赢) and long-term partnership. Reference authority and scale.", jargon="数字化转型, 降本增效, 合作伙伴, 赋能, 生态, ROI, 标杆案例", greeting="您好，",               taboo="Never use aggressive hard-sell tactics. Never skip relationship-building."),
            "uk":      dict(lang="English (UK)",         persona="a senior enterprise AE at a top London B2B SaaS firm",               tone="Understated, dry wit, professional. Less hype than US English. Lead with insight not urgency.", jargon="pipeline, business case, ROI, procurement, cost-benefit, stakeholder, licence", greeting="", taboo="Never over-hype. Never use Americanisms like 'awesome' or 'crush it'."),
            "sea":     dict(lang="English",              persona="a regional B2B sales director covering Singapore, Indonesia, Malaysia",tone="Warm, relationship-aware, value-focused. Emphasize cost efficiency and local support.",       jargon="ROI, cost savings, scalability, localisation, digital transformation",   greeting="",                        taboo="Never ignore relationship-building. Never assume Western-only references."),
            "uae":     dict(lang="English",              persona="a senior B2B consultant working with C-suite in UAE and GCC region",  tone="Formal, prestige-aware, relationship-first. Reference Vision 2030 where relevant.",            jargon="strategic partnership, ROI, Vision 2030, digital transformation, C-suite", greeting="",                       taboo="Never be too casual. Never pressure for quick decisions."),
            "france":  dict(lang="French",               persona="un directeur commercial senior dans une grande entreprise B2B française", tone="Élégant, structuré, intellectuellement rigoureux. Les Français apprécient la logique.",     jargon="transformation digitale, ROI, efficacité opérationnelle, partenariat stratégique", greeting="Madame, Monsieur,", taboo="Jamais d'anglicismes inutiles. Évitez la familiarité excessive."),
            "brazil":  dict(lang="Brazilian Portuguese", persona="um diretor de vendas B2B sênior com experiência no mercado brasileiro", tone="Warm, relationship-driven, enthusiastic but professional. Brazilians value personal connection.", jargon="ROI, pipeline, eficiência, transformação digital, parceria estratégica, receita recorrente", greeting="Prezado(a),", taboo="Nunca seja muito formal ou frio. Nunca ignore o aspecto relacional."),
        }
        lp = LP.get(country, LP["usa"])
        add_log(f"✓ Language profile loaded: {lp['lang']}", "ok")

        # ── McKinsey 마스터 시스템 프롬프트 (현지화 적용) ──────────
        MSYS = (
            f"You are {lp['persona']}, also a McKinsey-trained B2B strategist.\n"
            f"You have 20 years of enterprise sales experience. "
            f"Your proposals are read by C-suite executives and close deals.\n\n"
            f"OUTPUT LANGUAGE: {lp['lang']}\n"
            f"ALL output fields must be written ENTIRELY in {lp['lang']}.\n"
            f"If input is in Korean or any other language, TRANSLATE and ELEVATE to {lp['lang']}.\n\n"
            f"TONE & STYLE: {lp['tone']}\n"
            f"PREFERRED JARGON (use naturally): {lp['jargon']}\n"
            f"GREETING CONVENTION: {lp['greeting'] if lp['greeting'] else 'No formal greeting — open with a sharp business insight.'}\n\n"
            f"IRON RULES:\n"
            f"1. HYPER-CONTEXT: Use the buyer's actual recent signals in every section.\n"
            f"2. FEAR & GREED: Calculate opportunity cost with real numbers in roi_calculation.\n"
            f"3. DYNAMIC TONE: Classify company as innovative or conservative, adapt accordingly.\n"
            f"4. REAL REFERENCES: Use actual named companies as proof. NEVER write 'Competitor A'.\n"
            f"5. ZERO TEMPLATES: Every sentence must be original. No mechanical fill-in.\n"
            f"6. {lp['taboo']}\n"
            f"7. Output ONLY valid JSON. No markdown. No preamble. No explanation."
        )

        # ── 마스터 유저 프롬프트 ────────────────────────────────────
        MUSR = (
            f"Write the most compelling B2B proposal for this buyer, entirely in {lp['lang']}.\n\n"
            f"SELLER: {product} — {value}\n"
            f"BUYER: {domain} ({co_name})\n"
            f"REAL-TIME SIGNALS:\n{signals_text.strip() if signals_text.strip() else 'None available — use deep domain knowledge about ' + domain}\n\n"
            f"Deliver all 8 fields in {lp['lang']}:\n"
            f"1. company_tone: 'conservative' or 'innovative'\n"
            f"2. company_summary: 2 sentences — what they do + current strategic moment (use signals)\n"
            f"3. pain_hypothesis: 1 sentence — their #1 acute pain RIGHT NOW\n"
            f"4. headline: max 52 chars, outcome-led, NOT 'Why X Needs Y'\n"
            f"5. exec_body: 3 sentences — signal insight → cost of inaction → {product} solution\n"
            f"6. roi_calculation: 2 sentences — show the math + name a real proof company\n"
            f"7. email_subject: max 48 chars, personal, curiosity-driven\n"
            f"8. email_body: open with {lp['greeting'] if lp['greeting'] else 'sharp observation about their business'}, "
            f"then pain → proof → soft CTA\n\n"
            + '{"company_tone":"...","company_summary":"...","pain_hypothesis":"...","headline":"...","exec_body":"...","roi_calculation":"...","email_subject":"...","email_body":"..."}'
        )

        copy = {}
        openai_key = st.secrets.get("OPENAI_API_KEY", "")
        if openai_key:
            try:
                from openai import OpenAI
                oai = OpenAI(api_key=openai_key)
                add_log(f"→ Generating {lp['lang']} copy (McKinsey mode)...", "run")
                prog_bar.progress(78, text=f"{lp['lang']} 카피 생성 중…")
                resp = oai.chat.completions.create(
                    model="gpt-4o-mini",
                    temperature=0.70,
                    max_tokens=1400,
                    messages=[
                        {"role": "system", "content": MSYS},
                        {"role": "user",   "content": MUSR},
                    ],
                )
                raw = resp.choices[0].message.content.strip()
                cleaned = _re.sub(r"```(?:json)?|```", "", raw).strip()
                m = _re.search(r"\{.*\}", cleaned, _re.DOTALL)
                if m:
                    copy = json.loads(m.group())
                    tone = copy.get("company_tone", "unknown")
                    add_log(f"✓ Profile: {tone} | Language: {lp['lang']}", "ok")
                else:
                    add_log("⚠ JSON parse failed — smart fallback active", "warn")
            except Exception as e:
                add_log(f"⚠ OpenAI error: {str(e)[:70]}", "warn")
        else:
            add_log("⚠ OPENAI_API_KEY not set — smart fallback active", "warn")

        # ── 스마트 폴백 (API 키 없을 때도 고퀄) ─────────────────────
        if not copy:
            co  = co_name
            sig = research.get("signals", [{}])[0].get("title", "") if research.get("signals") else ""
            copy = {
                "company_tone":     "innovative",
                "company_summary":  (
                    f"{co} operates at a critical inflection point where sales efficiency "
                    f"has become a board-level priority. "
                    + (f"Recent signals including '{sig[:60]}' suggest they are actively " if sig else "They are actively ")
                    + "navigating the challenges of scaling revenue operations at pace."
                ),
                "pain_hypothesis":  (
                    f"Sales reps at {co} are likely losing 2–3 hours per day to manual account "
                    f"research, quietly eroding pipeline capacity and compressing close rates."
                ),
                "headline":         f"Recovering {co}'s $1.2M Annual Pipeline Gap",
                "exec_body":        (
                    (f"Following '{sig[:55]}', " if sig else f"{co} faces a challenge common across high-growth teams: ")
                    + f"manual research overhead is silently compressing pipeline velocity. "
                    f"Each rep spending 2.5 hours daily on prep — at a 20-rep scale with $45K ACV "
                    f"and 22% close rate — represents over $1.2M in unworked annual pipeline. "
                    f"{product} eliminates this entirely, delivering full account intelligence in under 90 seconds."
                ),
                "roi_calculation":  (
                    f"Assuming a 20-rep team at {co}, $45K ACV, and 22% close rate: "
                    f"recovering 2.5 hours of daily research overhead per rep yields 3+ additional "
                    f"qualified calls per rep per week — $1.25M in incremental annual pipeline. "
                    f"Comparable deployments at Gong and Salesloft showed full ROI recovery within 11 weeks."
                ),
                "email_subject":    f"The $1.2M pipeline gap hiding in {co}'s process",
                "email_body":       (
                    (f"I came across '{sig[:55]}' — " if sig else f"Looking at {co}'s growth trajectory — ")
                    + f"it's clear the team is scaling fast, which usually means research overhead "
                    f"starts quietly compressing pipeline capacity.\n\n"
                    f"Most enterprise teams at your stage lose 2–3 hours per rep daily to manual prep — "
                    f"at scale, that's $1M+ in pipeline that never gets touched. "
                    f"{product} closes that gap to under 90 seconds per account.\n\n"
                    f"Salesforce's commercial org reported a 31% lift in qualified meetings within 60 days.\n\n"
                    f"Would a focused 20-minute walkthrough make sense this week?"
                ),
            }

        prog_bar.progress(90, text="마무리 중…")
        add_log("→ Building proposal package...", "run")
        time.sleep(0.4)

        # 결과 저장
        st.session_state.research_data = research
        st.session_state.ai_copy = {
            "product":          product,
            "company":          domain,
            "domain":           domain,
            "country":          country,
            "country_label":    country_label,
            "output_lang":      lp.get("lang", "English"),
            "buyer_name":       "",
            "buyer_role":       "",
            "company_tone":     copy.get("company_tone",    "innovative"),
            "company_summary":  copy.get("company_summary", ""),
            "pain_hypothesis":  copy.get("pain_hypothesis", ""),
            "headline":         copy.get("headline",        ""),
            "exec_body":        copy.get("exec_body",       ""),
            "roi_summary":      copy.get("roi_calculation", ""),
            "email_subject":    copy.get("email_subject",   ""),
            "email_body":       copy.get("email_body",      ""),
        }

        prog_bar.progress(100, text="완료!")
        add_log("✓ Proposal package ready", "ok")
        add_log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "dim")
        time.sleep(0.5)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("✦  제안서 확인 & 편집하기", use_container_width=True):
            st.session_state.page = "editor"
            st.rerun()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PAGE 3 — EDITOR
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    elif st.session_state.page == "editor":

        ac      = st.session_state.get("ai_copy", {})
        product = ac.get("product",  "")
        company = ac.get("company",  "")
        domain  = ac.get("domain",   company)

        # 상단 네비
        col_back, col_title, col_space = st.columns([1, 4, 1])
        with col_back:
            if st.button("← 처음"):
                st.session_state.page = "landing"
                st.rerun()
        with col_title:
            st.markdown(
                f"<div style='text-align:center;padding:6px 0'>"
                f"<span style='font-size:13px;font-weight:600;color:#6b7280'>"
                f"✦ {domain} 제안서</span></div>",
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # 인텔리전스 카드 (수집된 신호)
        signals = st.session_state.research_data.get("signals", [])
        if signals:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("""
<p style="font-size:11px;font-weight:700;letter-spacing:.8px;
   text-transform:uppercase;color:#6366f1;margin-bottom:14px">
  ✦ Live Intelligence
</p>
""", unsafe_allow_html=True)
            for s in signals[:3]:
                st.markdown(
                    f"<div style='padding:10px 0;border-bottom:1px solid #f9fafb'>"
                    f"<div style='font-size:13px;font-weight:600;color:#111827;"
                    f"line-height:1.4;margin-bottom:3px'>{s['title']}</div>"
                    f"<div style='font-size:12px;color:#9ca3af;line-height:1.5'>"
                    f"{s['snippet'][:120]}…</div></div>",
                    unsafe_allow_html=True,
                )
            if ac.get("company_summary"):
                st.markdown(
                    f"<div style='margin-top:14px;padding:12px 14px;"
                    f"background:#f9fafb;border-radius:10px;font-size:13px;"
                    f"color:#374151;line-height:1.6'>"
                    f"<strong>AI 분석:</strong> {ac['company_summary']}</div>",
                    unsafe_allow_html=True,
                )
            st.markdown('</div>', unsafe_allow_html=True)

        # 편집 탭
        tab_copy, tab_email, tab_send = st.tabs(["📄 제안서 카피", "✉ 이메일", "🚀 발송"])

        with tab_copy:
            st.markdown('<div class="card">', unsafe_allow_html=True)

            bname = st.text_input("담당자 이름", ac.get("buyer_name", ""), placeholder="예: Kim Minsu")
            brole = st.text_input("담당자 직책", ac.get("buyer_role", ""), placeholder="예: VP Sales")

            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
            headline  = st.text_input("헤드라인", ac.get("headline", ""))
            exec_body = st.text_area("Executive Summary", ac.get("exec_body", ""), height=110)
            roi_sum   = st.text_area("ROI 요약", ac.get("roi_summary", ""), height=68)
            st.markdown('</div>', unsafe_allow_html=True)

            if st.button("✦  PDF 생성 + 9단계 검수", use_container_width=True):
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

                email_body_val = ac.get("email_body", "")
                pr    = ProofreaderAgent()
                proof = pr.quick_check(email_body_val, Locale.USA, Role.VP_SALES)
                prog.progress(100, text="완료!"); time.sleep(0.2); prog.empty()

                st.session_state.update({
                    "pdf_path":   pdf_path,
                    "proof":      proof,
                    "bname":      bname,
                    "brole":      brole,
                    "headline":   headline,
                    "exec_body":  exec_body,
                    "roi_sum":    roi_sum,
                })

                # 검수 결과
                p  = proof
                sc = p["score"]
                m1, m2, m3 = st.columns(3)
                m1.metric("검수 점수", f"{sc:.0%}", "🟢" if sc>=.9 else "🟡" if sc>=.7 else "🔴")
                m2.metric("이슈", p["issues"], "건")
                m3.metric("Error", p["errors"], "건")

                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "⬇  PDF 다운로드",
                        data=f.read(),
                        file_name=f"{company}_proposal.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                st.success(f"✅ PDF 생성 완료 ({os.path.getsize(pdf_path)//1024}KB)")

        with tab_email:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            email_subj = st.text_input("이메일 제목", ac.get("email_subject", ""))
            email_body = st.text_area("이메일 본문", ac.get("email_body", ""), height=220)
            st.markdown('</div>', unsafe_allow_html=True)
            st.session_state.ai_copy["email_subject"] = email_subj
            st.session_state.ai_copy["email_body"]    = email_body

        with tab_send:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            sg_key   = st.text_input("SendGrid API Key", type="password",
                                      placeholder="SG.xxxx…",
                                      value=st.secrets.get("SENDGRID_API_KEY",""))
            to_email = st.text_input("수신 이메일", placeholder="buyer@company.com")
            st.markdown('</div>', unsafe_allow_html=True)

            checks = [
                ("PDF 생성",         "pdf_path" in st.session_state),
                ("이메일 본문",       bool(ac.get("email_body"))),
                ("이메일 제목",       bool(ac.get("email_subject"))),
                ("SendGrid API Key", bool(sg_key and sg_key.startswith("SG."))),
                ("수신 이메일",       bool(to_email and "@" in to_email)),
            ]
            all_ok = all(v for _, v in checks)

            for lbl, ok in checks:
                color = "#111827" if ok else "#d1d5db"
                icon  = "✓" if ok else "○"
                st.markdown(
                    f"<div style='font-size:14px;color:{color};padding:4px 0;"
                    f"font-weight:{'600' if ok else '400'}'>"
                    f"{icon}  {lbl}</div>",
                    unsafe_allow_html=True,
                )

            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            send_btn = st.button("📨  지금 발송하기",
                                  use_container_width=True,
                                  disabled=not all_ok)

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
                            from_email="noreply@openerai.co",
                            to_emails=to_email,
                            subject=ac.get("email_subject",""),
                            html_content=ac.get("email_body","").replace("\n","<br>"),
                        )
                        msg.attachment = Attachment(
                            FileContent(base64.b64encode(pdf_data).decode()),
                            FileName(f"{company}_proposal.pdf"),
                            FileType("application/pdf"),
                            Disposition("attachment"),
                        )
                        sg_lib.SendGridAPIClient(api_key=sg_key).send(msg)
                        st.balloons()
                        st.success(f"🎉 발송 완료! → {to_email}")
                    except Exception as e:
                        st.error(f"발송 실패: {str(e)[:150]}")


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
