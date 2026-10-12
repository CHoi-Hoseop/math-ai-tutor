import streamlit as st
import google.generativeai as genai
import numpy as np
import matplotlib.pyplot as plt
import edge_tts
import asyncio
import datetime
import time
import sqlite3
import pandas as pd

# ==========================================
# 1. 페이지 설정 및 UI 스타일링
# ==========================================
st.set_page_config(page_title="문화고 2학년 미적분Ⅰ AI 튜터 & 관제", page_icon="📐", layout="wide")

st.markdown("""
<style>
    /* 기본 폰트 및 공통 여백 */
    h1 { font-size: 2.1rem !important; font-weight: 800 !important; }
    h2, h3 { font-weight: 700 !important; }
    
    /* 태블릿 채팅 가독성 */
    .stChatMessage p, .stChatMessage li, .stChatMessage div {
        font-size: 1.15rem !important;
        line-height: 1.65 !important;
    }
    
    /* 대시보드 6분할 조별 카드 */
    .dash-card {
        background: #ffffff;
        border-radius: 12px;
        border: 1.8px solid #cbd5e1;
        padding: 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        margin-bottom: 14px;
        min-height: 260px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .dash-card.warn-stuck { border: 2.2px solid #f59e0b; background: #fffbeb; }
    .dash-card.warn-troll { border: 2.2px solid #ef4444; background: #fef2f2; }
    
    .dash-header {
        display: flex; justify-content: space-between; align-items: center;
        border-bottom: 1.5px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 10px;
    }
    .dash-title { font-size: 1.3rem; font-weight: 800; color: #0f172a; }
    
    .badge-ok { background: #dcfce7; color: #15803d; padding: 3px 8px; border-radius: 6px; font-size: 0.78rem; font-weight: 700; }
    .badge-stuck { background: #fef3c7; color: #b45309; padding: 3px 8px; border-radius: 6px; font-size: 0.78rem; font-weight: 800; }
    .badge-troll { background: #fee2e2; color: #b91c1c; padding: 3px 8px; border-radius: 6px; font-size: 0.78rem; font-weight: 800; }
    .badge-time { background: #f1f5f9; color: #475569; padding: 2px 7px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; margin-left: 6px; }

    /* 교사용 질문 말풍선 버튼 스타일 (클릭 가능 피드) */
    div[data-testid="stButton"] > button.q-bubble-btn {
        background: #eff6ff !important;
        border: 1.5px solid #bfdbfe !important;
        border-left: 5px solid #2563eb !important;
        color: #1e3a8a !important;
        text-align: left !important;
        border-radius: 8px !important;
        padding: 10px 12px !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        line-height: 1.4 !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
        transition: all 0.15s ease-in-out !important;
    }
    div[data-testid="stButton"] > button.q-bubble-btn:hover {
        background: #dbeafe !important;
        border-color: #3b82f6 !important;
        transform: translateY(-1px);
    }
    
    .a-preview-box {
        font-size: 0.88rem; color: #334155; line-height: 1.45;
        background: #f8fafc; padding: 8px 10px; border-radius: 6px;
        border: 1px solid #e2e8f0; margin-top: 6px;
    }

    /* 참관교사용 4단계 타임라인 게이지 */
    .timeline-wrap { display: flex; gap: 8px; margin: 12px 0 18px 0; }
    .tl-step {
        flex: 1; padding: 10px 12px; border-radius: 8px;
        background: #f8fafc; border: 1.5px solid #e2e8f0;
        text-align: center; font-size: 0.85rem; color: #64748b; font-weight: 700;
    }
    .tl-step.active {
        background: #eff6ff; border-color: #2563eb; color: #1e40af;
        box-shadow: 0 0 0 2px rgba(37,99,235,0.2);
    }
    .tl-step-time { font-size: 0.75rem; font-weight: 500; display: block; margin-top: 3px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 로컬 SQLite 경량 공유 DB 모듈
# ==========================================
DB_FILE = "class_monitor.db"

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team TEXT,
            question TEXT,
            answer TEXT,
            is_troll INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_log(team, question, answer, is_troll=0):
    try:
        # 한국 표준시(KST, UTC+9) 직접 계산
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        kst_now = utc_now + datetime.timedelta(hours=9)
        kst_time_str = kst_now.strftime("%Y-%m-%d %H:%M:%S")  # 예: 2026-10-12 15:45:20

        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("""
            INSERT INTO logs (team, question, answer, is_troll, timestamp) 
            VALUES (?, ?, ?, ?, ?)
        """, (team, question, answer, is_troll, kst_time_str))
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_logs():
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        df = pd.read_sql_query("SELECT * FROM logs ORDER BY id ASC", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

init_db()

# ==========================================
# 3. 문화고등학교 교시별 시간 모듈 (KST 고정 및 리허설 가상 타이머 지원)
# ==========================================
SCHEDULE = [
    (1, datetime.time(8, 40), datetime.time(9, 30)),
    (2, datetime.time(9, 40), datetime.time(10, 30)),
    (3, datetime.time(10, 40), datetime.time(11, 30)),
    (4, datetime.time(11, 40), datetime.time(12, 30)),
    (5, datetime.time(13, 40), datetime.time(14, 30)),
    (6, datetime.time(14, 40), datetime.time(15, 30)),
    (7, datetime.time(15, 50), datetime.time(16, 40)),
]

def get_current_period_and_elapsed():
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    kst_now = utc_now + datetime.timedelta(hours=9)
    cur_time = kst_now.time()
    
    # 1. 정규 수업 교시 체크
    for period, start, end in SCHEDULE:
        if start <= cur_time <= end:
            start_dt = datetime.datetime.combine(kst_now.date(), start, tzinfo=kst_now.tzinfo)
            elapsed = int((kst_now - start_dt).total_seconds() // 60)
            return f"{period}교시", elapsed
            
    # 2. 수업 외 시간(방과 후/테스트): 수동 '수업 시작' 기준 또는 분 단위 순환 테스트
    if "class_start_time" in st.session_state:
        # 수업 시작 버튼을 눌렀을 때부터 흐른 시간 계산
        diff_sec = (kst_now.replace(tzinfo=None) - st.session_state["class_start_time"]).total_seconds()
        elapsed = int(diff_sec // 60)
        return "연구수업", elapsed
    else:
        # 버튼을 아직 안 눌렀을 때는 1단계(0분)부터 대기
        return "수업 대기", 0
cur_period, elapsed_min = get_current_period_and_elapsed()
# ==========================================
# 4. 사이드바 및 권한 인증 (선언 우선 배치)
# ==========================================
TEACHER_PIN = "1234"

with st.sidebar:
    st.header("👥 접속 모드 선택")
    user_mode = st.selectbox(
        "모둠 또는 관제 모드를 선택하세요",
        [
            "1조", "2조", "3조", "4조", "5조", "6조", 
            "👀 참관교사용 실시간 브리핑", 
            "👨‍🏫 교사용 실시간 관제"
        ]
    )
    
    is_teacher_authorized = False
    if user_mode == "👨‍🏫 교사용 실시간 관제":
        pin_input = st.text_input("교사용 PIN 번호 (4자리)", type="password")
        if pin_input == TEACHER_PIN:
            is_teacher_authorized = True
            st.success("인증 완료: 관제 센터가 열렸습니다.")
        elif pin_input:
            st.error("PIN 번호가 일치하지 않습니다.")
    else:
        st.info(f"현재 **{user_mode}** 모드로 학습 중입니다.")
        
    st.markdown("---")
    if cur_period not in ["테스트", "수업 대기"]:
        st.metric(label=f"{cur_period} 진행 현황", value=f"{elapsed_min}분 경과", delta=f"{max(0, 47 - elapsed_min)}분 남음")
    else:
        st.caption("수업 외 시간 (수업 시작 대기)")

# =========================================================================
# MODE A: 👀 참관교사용 실시간 수업 브리핑 (무암호 오픈 + 4단계 타임라인 게이지)
# =========================================================================
if user_mode == "👀 참관교사용 실시간 브리핑":
    st.title("📋 문화고 미적분Ⅰ 연구수업 참관 가이드")
    st.caption("소크라테스 AI 튜터 기반 삼차함수 그래프의 비율 관계 탐구 (수업자: 최호섭 선생님)")
    
    # 4단계 타임라인 프로그레스 게이지 계산
    s1_cls = "active" if elapsed_min <= 10 else ""
    s2_cls = "active" if 10 < elapsed_min <= 25 else ""
    s3_cls = "active" if 25 < elapsed_min <= 40 else ""
    s4_cls = "active" if elapsed_min > 40 else ""
    
    st.markdown(f"""
    <div class="timeline-wrap">
        <div class="tl-step {s1_cls}">
            <b>1단계. 문제 제기</b>
            <span class="tl-step-time">0~10분 (첫 발문 형성)</span>
        </div>
        <div class="tl-step {s2_cls}">
            <b>2단계. AI 기하 탐구</b>
            <span class="tl-step-time">10~25분 (1:1:1 발견)</span>
        </div>
        <div class="tl-step {s3_cls}">
            <b>3단계. 대수적 정당화</b>
            <span class="tl-step-time">25~40분 (2:1 증명)</span>
        </div>
        <div class="tl-step {s4_cls}">
            <b>4단계. 정리 및 심화</b>
            <span class="tl-step-time">40~47분 (1:√3 확장)</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    p1, p2, p3 = st.columns(3)
    with p1:
        st.info("""
        **1. 수학적 발문의 정교화**  
        단순 정답 요구가 아닌 *극댓값, 극솟값, 도함수의 대칭축(변곡점)* 등 수학적 용어로 질문을 좁혀가는지 관찰해 주세요.
        """)
    with p2:
        st.success("""
        **2. 활동지 하이브리드 연계**  
        AI 답변을 확인한 후 모둠원과 토의하여 **종이 활동지 2단계 그래프에 자를 대고 거리 간격을 기록하는지** 확인해 주세요.
        """)
    with p3:
        st.warning("""
        **3. 기하에서 대수로의 정당화**  
        발견한 2:1 비율을 $x^3 - 3x - 2 = 0$ 인수분해를 통해 **손으로 직접 증명해내는 정당화 과정**을 지켜봐 주세요.
        """)
        
    st.markdown("---")
    st.subheader("📡 모둠별 실시간 대화 피드")
    df_obs = get_logs()
    
    if not df_obs.empty:
        obs_cols = st.columns(3)
        for i, t_name in enumerate(["1조", "2조", "3조", "4조", "5조", "6조"]):
            c = obs_cols[i % 3]
            t_sub = df_obs[df_obs["team"] == t_name]
            with c:
                st.markdown(f"##### 🏷️ {t_name} (총 {len(t_sub)}회 대화)")
                if len(t_sub) > 0:
                    last_item = t_sub.iloc[-1]
                    st.markdown(f"""
                    <div style="background:#f8fafc; border:1px solid #cbd5e1; border-radius:8px; padding:10px; margin-bottom:12px; font-size:0.9rem;">
                        <p style="color:#1d4ed8; font-weight:700; margin-bottom:4px;">Q. {last_item['question']}</p>
                        <p style="color:#334155; margin-bottom:0; font-size:0.85rem;"><b>AI:</b> {last_item['answer'][:120]}...</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.caption("아직 첫 질문 탐색 전입니다.")
    else:
        st.info("아직 전송된 모둠별 대화 기록이 없습니다.")
        
    st.stop()

# =========================================================================
# MODE B: 👨‍🏫 교사용 6분할 실시간 관제 전광판 (KST 실시간 시계 정상화)
# =========================================================================
if user_mode == "👨‍🏫 교사용 실시간 관제" and is_teacher_authorized:
    h_col1, h_col2 = st.columns([3.3, 1.2])
    with h_col1:
        st.title("🖥️ [교단 관제 전광판] 6개 조 실시간 탐구 현황")
        st.caption("질문 버튼을 누르면 해당 조의 전체 대화록이 화면 중앙에 고해상도로 확대됩니다.")
    with h_col2:
        st.write("")
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if st.button("🔔 수업 시작", use_container_width=True, help="지금 시각을 0분으로 잡고 47분 타이머를 시작합니다."):
                utc_now = datetime.datetime.now(datetime.timezone.utc)
                st.session_state["class_start_time"] = (utc_now + datetime.timedelta(hours=9)).replace(tzinfo=None)
                st.success("수업 타이머가 시작되었습니다!")
                st.rerun()
        with col_b2:
            if st.button("🔄 수동 갱신", use_container_width=True):
                st.rerun()
        with col_b3:
            if st.button("🧹 전체 초기화", use_container_width=True):
                # DB 및 세션 초기화 로직
                # 1. SQLite DB 테이블 비우기
                conn = sqlite3.connect(DB_FILE, check_same_thread=False)
                c = conn.cursor()
                c.execute("DELETE FROM logs")
                c.execute("DELETE FROM sqlite_sequence WHERE name='logs'") # id 번호도 1번으로 리셋
                conn.commit()
                conn.close()
                
                # 2. 브라우저 세션 메모리(1~6조 대화 기록) 완전 초기화
                for t in ["1조", "2조", "3조", "4조", "5조", "6조"]:
                    key = f"messages_{t}"
                    if key in st.session_state:
                        st.session_state[key] = []
                
                # 3. Gemini 채팅 세션 객체도 초기화
                if "chat" in st.session_state:
                    del st.session_state["chat"]
                
                st.success("모든 조의 데이터와 세션 기록이 완전 초기화되었습니다.")
                st.rerun()

    # 대형 모달 팝업 함수
    @st.dialog("📋 모둠 탐구 상세 내역", width="large")
    def show_team_detail_modal(team_name, team_data):
        st.markdown(f"### 🏷️ **{team_name} 실시간 전체 대화록** (총 {len(team_data)}회 문답)")
        st.markdown("---")
        
        if team_data.empty:
            st.info("아직 전송된 질문이 없습니다.")
        else:
            for idx, row in team_data.iterrows():
                is_troll_log = row.get("is_troll", 0) == 1
                q_border = "#ef4444" if is_troll_log else "#2563eb"
                q_bg = "#fef2f2" if is_troll_log else "#eff6ff"
                
                st.markdown(f"""
                <div style="background:{q_bg}; border-left:5px solid {q_border}; padding:10px 14px; border-radius:6px; margin-bottom:8px;">
                    <div style="font-size:0.85rem; color:#64748b; font-weight:700;">#{row.get('id', idx+1)} 질문 [{row.get('timestamp', '')}]</div>
                    <div style="font-size:1.15rem; font-weight:800; color:#0f172a; margin-top:3px;">Q. {row.get('question', '-')}</div>
                </div>
                <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:12px 14px; margin-bottom:16px;">
                    <div style="font-size:0.85rem; color:#16a34a; font-weight:700; margin-bottom:3px;">🤖 소크라테스 AI 피드백</div>
                    <div style="font-size:1.05rem; color:#334155; line-height:1.6;">{row.get('answer', '-')}</div>
                </div>
                """, unsafe_allow_html=True)
                
        if st.button("닫기", use_container_width=True):
            st.rerun()

    # 🕒 상단 시계 + 타임라인 + 6개 조 카드를 통합 부분 갱신 (8초 간격)
    @st.fragment(run_every="8s")
    def render_live_dashboard():
        # 1. KST 현재 시각 및 교시 실시간 산출
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        kst_now = utc_now + datetime.timedelta(hours=9)
        time_display = kst_now.strftime("%H:%M:%S")
        
        cur_p, elap = get_current_period_and_elapsed()

        # 2. 상단 디지털 시계 표시 바
        st.markdown(f"""
        <div style="display:flex; justify-content:space-between; align-items:center; background:#0f172a; padding:10px 18px; border-radius:10px; margin-bottom:12px;">
            <div style="color:#e2e8f0; font-size:1.05rem; font-weight:700;">
                🏫 문화고등학교 미적분Ⅰ 관제 시스템 <span style="color:#94a3b8; font-size:0.85rem; font-weight:500;">(경북 경주)</span>
            </div>
            <div style="display:flex; align-items:center; gap:16px;">
                <div style="color:#94a3b8; font-size:0.9rem; font-weight:600;">
                    {f"{cur_p}교시 ({elap}분 경과)" if cur_p != "테스트" else "수업 외 시간 (테스트 모드)"}
                </div>
                <div style="background:#1e293b; color:#38bdf8; padding:4px 12px; border-radius:6px; font-family:monospace; font-size:1.35rem; font-weight:800; border:1px solid #334155;">
                    ⏱️ {time_display}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 3. 4단계 타임라인 진행 바
        s1_cls = "active" if elap <= 10 else ""
        s2_cls = "active" if 10 < elap <= 25 else ""
        s3_cls = "active" if 25 < elap <= 40 else ""
        s4_cls = "active" if elap > 40 else ""
        
        st.markdown(f"""
        <div class="timeline-wrap" style="margin-top:4px; margin-bottom:16px;">
            <div class="tl-step {s1_cls}">
                <b>1단계. 문제 제기</b>
                <span class="tl-step-time">0~10분 (첫 발문 형성)</span>
            </div>
            <div class="tl-step {s2_cls}">
                <b>2단계. AI 기하 탐구</b>
                <span class="tl-step-time">10~25분 (1:1:1 발견)</span>
            </div>
            <div class="tl-step {s3_cls}">
                <b>3단계. 대수적 정당화</b>
                <span class="tl-step-time">25~40분 (2:1 증명)</span>
            </div>
            <div class="tl-step {s4_cls}">
                <b>4단계. 정리 및 심화</b>
                <span class="tl-step-time">40~47분 (1:√3 확장)</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 4. 6개 조 카드 렌더링
        df_all = get_logs()
        row1 = st.columns(3)
        row2 = st.columns(3)
        grid_cols = row1 + row2
        team_list = ["1조", "2조", "3조", "4조", "5조", "6조"]
        
        for idx, t_name in enumerate(team_list):
            col = grid_cols[idx]
            t_logs = df_all[df_all["team"] == t_name] if not df_all.empty else pd.DataFrame()
            t_cnt = len(t_logs)
            
            with col:
                has_troll = False
                time_badge = ""
                if t_cnt > 0:
                    last_row = t_logs.iloc[-1]
                    has_troll = (last_row.get("is_troll", 0) == 1)
                    try:
                        t_str = str(last_row.get("timestamp", ""))
                        if t_str:
                            t_dt = pd.to_datetime(t_str)
                            diff_sec = (kst_now.replace(tzinfo=None) - t_dt).total_seconds()
                            diff_min = max(0, int(diff_sec // 60))
                            time_badge = f'<span class="badge-time">{diff_min}분 전</span>'
                    except Exception:
                        time_badge = ""
                
                if has_troll:
                    status_badge = '<span class="badge-troll">🚨 비수학적 질문</span>'
                elif t_cnt == 0:
                    status_badge = '<span class="badge-stuck">🟡 미참여 (0회)</span>'
                else:
                    status_badge = f'<span class="badge-ok">🟢 순항 중 ({t_cnt}회)</span>'

                st.markdown(f"""
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; padding:0 2px;">
                    <span style="font-size:1.3rem; font-weight:800; color:#0f172a;">{t_name}</span>
                    <div>{status_badge}{time_badge}</div>
                </div>
                """, unsafe_allow_html=True)

                card_box = st.container(height=260)
                with card_box:
                    if t_cnt == 0:
                        st.markdown("""
                        <div style="color:#94a3b8; text-align:center; padding-top:85px; font-size:0.92rem; line-height:1.6;">
                            아직 전송된 질문이 없습니다.<br>
                            1단계 질문 작성을 독려해 주세요.
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        for q_idx, r in t_logs.iterrows():
                            q_text = str(r.get('question', '-'))
                            a_text = str(r.get('answer', '-'))
                            
                            btn_label = f"💬 Q{q_idx+1}. {q_text}"
                            if st.button(btn_label, key=f"q_btn_{t_name}_{q_idx}", use_container_width=True, help="클릭 시 전체 대화가 확대됩니다."):
                                show_team_detail_modal(t_name, t_logs)
                                
                            st.markdown(f"""
                            <div style="background:#f8fafc; border-left:3px solid #cbd5e1; padding:7px 10px; border-radius:4px; font-size:0.85rem; color:#334155; margin-bottom:10px; line-height:1.45;">
                                <b>AI:</b> {a_text[:85]}...
                            </div>
                            """, unsafe_allow_html=True)

    render_live_dashboard()
    st.stop()
# =========================================================================
# MODE C: 🤖 학생 모둠용 AI 튜터 화면 (1조 ~ 6조, 1.15 : 0.85 비율 최적화)
# =========================================================================
TROLL_WORDS = ["바보", "멍청", "롤", "티어", "롤체", "피파", "축구", "메이플", "사랑해", "개새", "존나", "시발", "섹스", "ㅋㅋㅋㅋ", "ㅎㅎㅎㅎ", "죽어"]

def check_is_troll(text):
    for w in TROLL_WORDS:
        if w in text:
            return True
    return False

st.title(f"🤖 [{user_mode}] 삼차함수 그래프의 비율 탐구")
st.markdown("모둠원과 상의한 질문을 AI에게 전송하고, 단서를 **책상 위 활동지**에 기록하세요.")

def play_audio_guide(text):
    async def _generate_audio():
        communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        return audio_bytes
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    audio_data = loop.run_until_complete(_generate_audio())
    loop.close()
    st.audio(audio_data, format='audio/mp3', autoplay=True)

b1, b2, b3 = st.columns(3)
with b1:
    if st.button("▶ 1단계: 미션 듣기", use_container_width=True):
        play_audio_guide("문화고 학생 여러분, 오늘 미션은 삼차함수 그래프 속 1대 1대 1 비율을 밝혀내는 것입니다. 왼쪽 그래프를 보고 핵심 좌표들을 AI에게 캐내보세요.")
with b2:
    if st.button("▶ 2단계: 스무고개 팁", use_container_width=True):
        play_audio_guide("정답 공식은 AI가 절대 먼저 말하지 않습니다. 극댓값, 변곡점 같은 정확한 수학 용어로 물어보세요.")
with b3:
    if st.button("▶ 3단계: 증명 안내", use_container_width=True):
        play_audio_guide("비율을 발견했다면 활동지 뒷면의 3단계 도함수 증명으로 넘어가세요.")

st.markdown("---")

API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=API_KEY)

system_instruction = """
너는 문화고등학교 2학년 미적분Ⅰ 연구수업의 소크라테스식 AI 튜터야.
학생들이 f(x) = x^3 - 3x 그래프의 1:1:1 및 2:1 비율을 스스로 발견하도록 유도해야 해.

[장난 및 비수학적 질문 방어 철칙 (Strict Guardrail)]
- 게임(롤, 축구 등), 일상 잡담, 장난, 욕설 질문이 들어오면 맞장구치지 마.
- 단호하고 정중하게 "선생님의 실시간 관제 화면에 질문이 기록되고 있습니다. 지금은 삼차함수 탐구 시간입니다. 책상 위 활동지 1단계 수학 질문으로 돌아오세요!"라고만 답할 것.

[소크라테스 유도 규칙]
- '2:1', '1:1:1' 최종 비율 숫자를 학생보다 먼저 절대 말하지 마.
- 질문에 답한 뒤에는 화면 그래프를 다시 보게 하는 '구체적인 꼬리 질문(모둠 미션)'을 던져.
- 답변 끝에는 항상 "✍️ [활동지 기록] 방금 확인한 내용을 종이 활동지에 연필로 적으세요!"를 붙일 것.
"""

model = genai.GenerativeModel(model_name="gemini-3.8-flash", system_instruction=system_instruction)

session_key = f"messages_{user_mode}"
if session_key not in st.session_state:
    st.session_state[session_key] = []
if "chat" not in st.session_state:
    st.session_state.chat = model.start_chat(history=[])

col_graph, col_chat = st.columns([1.15, 0.85], gap="medium")

# 좌측 그래프
with col_graph:
    st.subheader("📈 탐구용 그래프")
    x = np.linspace(-2.5, 2.5, 400)
    y = x**3 - 3*x
    dy = 3*x**2 - 3
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.2, 7.5))
    plt.subplots_adjust(hspace=0.28)
    xticks = np.arange(-2, 3, 1)
    
    ax1.plot(x, y, color="#1f77b4", linewidth=2.5, label="$f(x) = x^3 - 3x$")
    ax1.spines['left'].set_position('zero')
    ax1.spines['bottom'].set_position('zero')
    ax1.spines['right'].set_color('none')
    ax1.spines['top'].set_color('none')
    ax1.set_xticks(xticks)
    ax1.set_xticklabels([str(i) if i != 0 else '' for i in xticks], fontsize=11)
    ax1.set_xlim(-2.5, 2.5)
    ax1.set_ylim(-4.5, 4.5)
    ax1.axhline(2, color='red', alpha=0.45, linestyle=':', label="$y = 2$")
    ax1.axhline(-2, color='blue', alpha=0.45, linestyle=':', label="$y = -2$")
    ax1.plot([2], [2], marker='o', markersize=7, color='red')
    ax1.plot([-2], [-2], marker='o', markersize=7, color='blue')
    ax1.grid(True, alpha=0.3, linestyle='--')
    ax1.legend(loc='upper left', fontsize=10)
    
    ax2.plot(x, dy, color="#ff7f0e", linewidth=2.2, label="$f'(x) = 3x^2 - 3$")
    ax2.spines['left'].set_position('zero')
    ax2.spines['bottom'].set_position('zero')
    ax2.spines['right'].set_color('none')
    ax2.spines['top'].set_color('none')
    ax2.set_xticks(xticks)
    ax2.set_xticklabels([str(i) if i != 0 else '' for i in xticks], fontsize=11)
    ax2.set_xlim(-2.5, 2.5)
    ax2.set_ylim(-4.5, 9.5)
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.legend(loc='upper center', fontsize=10)
    
    for ax in [ax1, ax2]:
        for px in [-2, -1, 0, 1, 2]:
            ax.axvline(px, color='gray', alpha=0.4, linestyle='--', linewidth=1.2)
            
    st.pyplot(fig)
    st.info("💡 **관찰 팁:** $x = -2, -1, 0, 1, 2$ 수직 점선들 사이의 거리를 비교해 보세요.")

# 우측 채팅
with col_chat:
    st.subheader(f"💬 소크라테스 AI ({user_mode})")
    
    chat_box = st.container(height=480)
    with chat_box:
        for m in st.session_state[session_key]:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
                
    preset_q = None
    if len(st.session_state[session_key]) == 0:
        st.markdown("##### 💡 마중물 첫 질문")
        qc1, qc2 = st.columns(2)
        with qc1:
            if st.button("📍 극댓값/극솟값 x좌표는?", use_container_width=True):
                preset_q = "극댓값과 극솟값의 x좌표는 각각 뭐야?"
        with qc2:
            if st.button("⚖️ 도함수 대칭축 x=0의 의미는?", use_container_width=True):
                preset_q = "아래쪽 도함수의 대칭축 x=0은 위 삼차함수에서 어떤 점이야?"
                
    user_q = st.chat_input("모둠 합의 질문을 입력하세요")
    final_q = preset_q if preset_q else user_q
    
    if final_q:
        is_troll = 1 if check_is_troll(final_q) else 0
        
        st.session_state[session_key].append({"role": "user", "content": final_q})
        with chat_box:
            with st.chat_message("user"):
                st.markdown(final_q)
            with st.chat_message("assistant"):
                with st.spinner("AI가 분석 중입니다..."):
                    try:
                        res = st.session_state.chat.send_message(f"[{user_mode} 질문]: {final_q}")
                        bot_reply = res.text
                    except Exception as e:
                        bot_reply = f"일시적 연결 지연입니다: {e}"
                        
                    st.markdown(bot_reply)
                    st.session_state[session_key].append({"role": "assistant", "content": bot_reply})
                    save_log(user_mode, final_q, bot_reply, is_troll)
        st.rerun()