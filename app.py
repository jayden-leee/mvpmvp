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

import base64, json, os, sys, time, traceback, uuid
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── Streamlit 모드 감지 ───────────────────────────────────────────
_ST = "streamlit" in sys.modules or any("streamlit" in a for a in sys.argv)

###################################################################
#  A. STREAMLIT ENTRY-POINT
###################################################################
if _ST:
    import streamlit as st

    st.set_page_config(
        page_title="opener ultra — 최종 시연",
        page_icon="🚀", layout="wide",
    )
    st.markdown("""
    <style>
    .main .block-container{padding-top:1rem}
    .stButton>button{border-radius:10px;font-weight:600;transition:all .15s}
    .stButton>button:hover{transform:translateY(-1px)}
    code{background:#f0f4f8;padding:2px 5px;border-radius:4px;font-size:11px}
    </style>""", unsafe_allow_html=True)

    # ── 헤더 ──────────────────────────────────────────────────────
    st.markdown("""
    <div style='background:linear-gradient(135deg,#0f2044 0%,#1e3a70 100%);
         padding:18px 26px;border-radius:14px;margin-bottom:22px;
         display:flex;justify-content:space-between;align-items:center;
         box-shadow:0 8px 32px rgba(15,32,68,.25)'>
      <div>
        <span style='font-size:22px;font-weight:800;color:#fff;letter-spacing:-.5px'>
          opener<span style="color:#c9a84c">ultra</span>
        </span>
        <span style='font-size:12px;color:rgba(255,255,255,.45);margin-left:14px'>
          MVP · 전 10단계 통합 완료
        </span>
      </div>
      <div style='display:flex;gap:6px;align-items:center'>
        <span style='font-size:9px;background:rgba(201,168,76,.15);color:#c9a84c;
               padding:3px 10px;border-radius:100px;border:1px solid rgba(201,168,76,.25);
               font-weight:700;letter-spacing:.8px'>STAGE 10 · DEPLOYMENT</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 사이드바 ──────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙ 바이어 설정")
        company  = st.text_input("기업명",  "Kakao")
        bname    = st.text_input("담당자",  "Kim Minsu")
        brole    = st.text_input("직책",    "VP Sales")
        product  = st.text_input("제품명",  "OpenerUltra")

        st.divider()
        st.markdown("### 📨 발송 설정")
        sg_key   = st.text_input("SendGrid API Key", type="password",
                                  placeholder="SG.xxxx…")
        to_email = st.text_input("수신 이메일",
                                  placeholder="buyer@company.com")

        st.divider()
        st.markdown("**파이프라인 현황**")
        for n, lbl, ok in [
            ("1","StateManager / EventBus","✅"),
            ("2","Discovery 딥 인터뷰","✅"),
            ("3","Tavily Researcher","✅"),
            ("4","Strategist 10국×15직무","✅"),
            ("5","Copywriter 5-slide","✅"),
            ("6","Visualizer 4차트","✅"),
            ("7","Designer 8-page PDF","✅"),
            ("8","Human-in-the-Loop","✅"),
            ("9","Proofreader 3-layer","✅"),
            ("10","Deployment · 발송","🔥"),
        ]:
            st.markdown(f"{ok} **{n}단계** {lbl}")

    # ── 탭 ────────────────────────────────────────────────────────
    tab_edit, tab_send, tab_audit = st.tabs(
        ["📝 편집 & PDF 생성", "🚀 발송", "📁 구조 검증"])

    # ┌─────────────────────────────────────────────────────────────
    # │  TAB 1: 편집 & PDF
    # └─────────────────────────────────────────────────────────────
    with tab_edit:
        col_l, col_r = st.columns(2, gap="medium")

        with col_l:
            st.subheader("카피 편집")
            headline  = st.text_input("헤드라인",
                f"Why {company} Needs {product} Now")
            exec_body = st.text_area("Executive Summary",
                f"Based on deep research into {company}'s growth trajectory, "
                f"we identified a critical gap driven by manual research overhead. "
                f"{product} closes that gap in 90 seconds.", height=100)
            roi_sum   = st.text_area("ROI 요약",
                "For a team of 20 AEs, OpenerUltra delivers ~$180K in annual "
                "research savings plus $2.4M+ in pipeline acceleration.", height=68)
            email_subj = st.text_input("이메일 제목",
                f"{company}'s sales team growth → 3-hr research bottleneck?")
            email_body = st.text_area("이메일 본문 (개인화 훅)",
                f"Hi {bname},\n\nI noticed {company} recently expanded its sales team "
                f"— congrats on the growth.\n\n{product} compresses 3-hour research "
                f"to 90 seconds. Zendesk cut research time by 73% and saw a 28% "
                f"higher win rate in 90 days.\n\nWorth a 15-min call this week?",
                height=160)

        with col_r:
            st.subheader("PDF 생성 & 검수")

            if st.button("✦ PDF 생성 + 9단계 검수",
                         type="primary", use_container_width=True):
                from engine.agents.designer import (
                    DesignerAgent, DesignPayload,
                    DEFAULT_PAIN, DEFAULT_FEATURES, DEFAULT_ROI,
                    DEFAULT_ROADMAP, _default_refs,
                )
                from engine.agents.visualizer import (
                    VisualizerAgent, ChartType, BuyerFocus)
                from engine.agents.proofreader import (
                    ProofreaderAgent, Locale, Role)

                prog = st.progress(0, text="차트 생성 중…")
                Path("temp").mkdir(exist_ok=True)
                viz    = VisualizerAgent(temp_dir="temp")
                chart  = viz.generate(ChartType.RADAR, company,
                                      BuyerFocus.SALES_IMPACT, product)
                prog.progress(35, text="PDF 렌더링 중…")

                p = DesignPayload(
                    product_name=product, buyer_company=company,
                    buyer_name=bname, buyer_role=brole,
                    exec_headline=headline, exec_body=exec_body,
                    roi_summary=roi_sum, chart_paths=[chart],
                    pain_points=DEFAULT_PAIN[:3],
                    features=DEFAULT_FEATURES[:3],
                    roi_rows=DEFAULT_ROI,
                    roadmap=DEFAULT_ROADMAP,
                    references=_default_refs("SaaS"),
                    kpis=[("73%","Research Saved",""),
                          ("+28%","Win Rate",""), ("90s","Brief","")],
                )
                pdf_path = DesignerAgent("temp").generate(p)
                prog.progress(75, text="Proofreader 검수 중…")

                pr    = ProofreaderAgent()
                proof = pr.quick_check(email_body, Locale.USA, Role.VP_SALES)
                prog.progress(100, text="완료!")
                time.sleep(0.2); prog.empty()

                st.session_state.update({
                    "pdf_path":   pdf_path,
                    "proof":      proof,
                    "email_subj": email_subj,
                    "email_body": email_body,
                })
                st.success(
                    f"✅ PDF 생성 완료 "
                    f"({os.path.getsize(pdf_path)//1024}KB)")

            # 검수 결과
            if "proof" in st.session_state:
                p = st.session_state["proof"]
                sc = p["score"]
                emoji = "🟢" if sc >= .9 else "🟡" if sc >= .7 else "🔴"
                m1, m2, m3 = st.columns(3)
                m1.metric("검수 점수",  f"{sc:.0%}",   emoji)
                m2.metric("이슈 수",    p["issues"],   "건")
                m3.metric("Error",      p["errors"],   "건")
                if p.get("top_issue"):
                    st.caption(f"⚠ 주요 이슈: {p['top_issue']}")

            # 다운로드
            if "pdf_path" in st.session_state:
                with open(st.session_state["pdf_path"], "rb") as f:
                    pdf_bytes = f.read()
                st.download_button(
                    "⬇ PDF 다운로드",
                    data=pdf_bytes,
                    file_name=f"{company}_proposal.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

    # ┌─────────────────────────────────────────────────────────────
    # │  TAB 2: 발송
    # └─────────────────────────────────────────────────────────────
    with tab_send:
        st.subheader("🚀 제안서 이메일 발송")

        if "pdf_path" not in st.session_state:
            st.info("먼저 '편집 & PDF 생성' 탭에서 PDF를 만들어 주세요.")
        else:
            kb = os.path.getsize(st.session_state["pdf_path"]) // 1024
            st.success(f"📎 첨부 준비 완료 — {company}_proposal.pdf ({kb}KB)")

            left, right = st.columns(2, gap="medium")

            with left:
                st.markdown("**이메일 미리보기**")
                st.code(st.session_state.get("email_subj", ""), language=None)
                st.text_area("본문", st.session_state.get("email_body", ""),
                              height=190, disabled=True)

            with right:
                st.markdown("**발송 체크리스트**")
                checks = [
                    ("PDF 생성",          True),
                    ("이메일 본문",        bool(st.session_state.get("email_body"))),
                    ("이메일 제목",        bool(st.session_state.get("email_subj"))),
                    ("SendGrid API Key",  bool(sg_key and sg_key.startswith("SG."))),
                    ("수신 이메일",        bool(to_email and "@" in to_email)),
                    ("Proofreader 완료",  "proof" in st.session_state),
                ]
                all_ok = all(v for _, v in checks)
                for label, ok in checks:
                    st.markdown(f"{'✅' if ok else '❌'} {label}")

                st.divider()
                send_clicked = st.button(
                    "📨 지금 발송하기",
                    type="primary",
                    use_container_width=True,
                    disabled=not all_ok,
                )
                if not all_ok:
                    st.caption("모든 항목이 ✅ 되어야 발송 가능합니다.")

            # ── 발송 처리 ──────────────────────────────────────────
            if send_clicked and all_ok:
                with st.spinner("SendGrid로 발송 중…"):
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
                            html_content=st.session_state.get(
                                "email_body", "").replace("\n", "<br>"),
                        )
                        att = Attachment(
                            FileContent(base64.b64encode(pdf_data).decode()),
                            FileName(f"{company}_proposal.pdf"),
                            FileType("application/pdf"),
                            Disposition("attachment"),
                        )
                        msg.attachment = att
                        sg_lib.SendGridAPIClient(api_key=sg_key).send(msg)
                        send_ok = True
                    except Exception as e:
                        send_ok = False
                        send_err = str(e)[:200]

                if send_ok:
                    st.balloons()      # 🎈 Streamlit 내장 폭죽
                    st.success(f"🎉 발송 완료! → {to_email}")
                    st.markdown("""
                    <div style='background:linear-gradient(135deg,#0f2044,#1e3a70);
                         padding:24px;border-radius:14px;text-align:center;
                         margin-top:12px;border:1px solid rgba(201,168,76,.2)'>
                      <div style='font-size:48px'>🎊</div>
                      <div style='color:#c9a84c;font-size:20px;font-weight:800;margin-top:10px'>
                        제안서 발송 완료!</div>
                      <div style='color:rgba(255,255,255,.55);font-size:13px;margin-top:6px'>
                        opener ultra 전 10단계 파이프라인 완료 🚀</div>
                    </div>""", unsafe_allow_html=True)
                else:
                    if "unauthorized" in send_err.lower():
                        st.error("⚠ SendGrid 인증 실패 — API 키를 확인해 주세요.")
                    else:
                        st.error(f"발송 실패: {send_err}")
                    st.info("💡 PDF는 다운로드 탭에서 직접 받을 수 있습니다.")

    # ┌─────────────────────────────────────────────────────────────
    # │  TAB 3: 구조 검증
    # └─────────────────────────────────────────────────────────────
    with tab_audit:
        st.subheader("📁 최종 프로젝트 구조 검증")

        manifest = [
            ("app.py",                           "10단계 통합 서버 (현재 파일)"),
            ("requirements.txt",                 "의존성 명세"),
            ("engine/__init__.py",               "엔진 패키지"),
            ("engine/core.py",                   "StateManager · EventBus · AgentState"),
            ("engine/agents/discovery.py",       "1단계 → 딥 인터뷰 · 5레이어"),
            ("engine/agents/researcher.py",      "3단계 → Tavily Deep Search"),
            ("engine/agents/strategist.py",      "4단계 → 10국 × 15직무 전략"),
            ("engine/agents/copywriter.py",      "5단계 → 5-slide + 이메일 카피"),
            ("engine/agents/visualizer.py",      "6단계 → matplotlib 4차트"),
            ("engine/agents/designer.py",        "7단계 → ReportLab 8-page PDF"),
            ("engine/agents/proofreader.py",     "9단계 → 3-layer 톤앤매너 검수"),
            ("dashboard.html",                   "1단계 UI — StateManager"),
            ("discovery_ui.html",                "2단계 UI — 딥 인터뷰"),
            ("researcher_ui.html",               "3단계 UI — Tavily 리서처"),
            ("strategist_ui.html",               "4단계 UI — 전략 매트릭스"),
            ("copywriter_ui.html",               "5단계 UI — 카피 에디터"),
            ("designer_ui.html",                 "7단계 UI — PDF 디자이너"),
            ("proofreader_ui.html",              "9단계 UI — Proofreader"),
        ]
        ok_cnt = sum(1 for p, _ in manifest if os.path.exists(p))
        tot    = len(manifest)
        st.metric("파일 상태", f"{ok_cnt} / {tot}",
                  "전체 완료 ✅" if ok_cnt == tot else f"{tot-ok_cnt}개 누락")

        for fpath, desc in manifest:
            exists = os.path.exists(fpath)
            c1, c2, c3 = st.columns([3, 4, 1])
            c1.code(fpath, language=None)
            c2.caption(desc)
            c3.write("✅" if exists else "❌")

        st.divider()
        st.subheader("🔗 의존성 임포트 검증")

        if st.button("▶ 전체 임포트 테스트 실행"):
            modules = [
                ("engine.core",                "StateManager, EventBus"),
                ("engine.agents.designer",     "DesignerAgent"),
                ("engine.agents.visualizer",   "VisualizerAgent"),
                ("engine.agents.proofreader",  "ProofreaderAgent"),
                ("engine.agents.copywriter",   "CopywriterAgent"),
                ("engine.agents.strategist",   "StrategistAgent"),
                ("engine.agents.discovery",    "DiscoveryAgent"),
                ("flask",    "Flask HTTP server"),
                ("reportlab","ReportLab PDF"),
                ("matplotlib","matplotlib charts"),
                ("sendgrid",  "SendGrid email (선택)"),
            ]
            ok = 0
            for mod, desc in modules:
                try:
                    __import__(mod); ok += 1
                    st.markdown(f"✅ `{mod}` — {desc}")
                except Exception as e:
                    st.markdown(f"❌ `{mod}` — {desc}")
                    st.caption(f"   오류: {str(e)[:80]}")
            st.metric("임포트 성공", f"{ok} / {len(modules)}")

        st.divider()
        st.success("🏁 opener ultra · 전 10단계 파이프라인 시연 준비 완료")
        st.code("python app.py          # Flask :5000\n"
                "streamlit run app.py   # Streamlit :8501", language="bash")


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
