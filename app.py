import streamlit as st
import google.generativeai as genai
import numpy as np
import matplotlib.pyplot as plt
import os
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
    h1 { font-size: 2.0rem !important; font-weight: 800 !important; }
    h2, h3 { font-weight: 700 !important; }
    
    .stChatMessage p, .stChatMessage li, .stChatMessage div {
        font-size: 1.15rem !important;
        line-height: 1.65 !important;
    }
    
    .badge-ok { background: #dcfce7; color: #15803d; padding: 3px 8px; border-radius: 6px; font-size: 0.78rem; font-weight: 700; }
    .badge-stuck { background: #fef3c7; color: #b45309; padding: 3px 8px; border-radius: 6px; font-size: 0.78rem; font-weight: 800; }
    .badge-troll { background: #fee2e2; color: #b91c1c; padding: 3px 8px; border-radius: 6px; font-size: 0.78rem; font-weight: 800; }
    .badge-time { background: #f1f5f9; color: #475569; padding: 2px 7px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; margin-left: 6px; }

    .timeline-wrap { display: flex; gap: 8px; margin: 12px 0 16px 0; }
    .tl-step {
        flex: 1; padding: 9px 10px; border-radius: 8px;
        background: #f8fafc; border: 1.5px solid #e2e8f0;
        text-align: center; font-size: 0.85rem; color: #64748b; font-weight: 700;
    }
    .tl-step.active {
        background: #eff6ff; border-color: #2563eb; color: #1e40af;
        box-shadow: 0 0 0 2px rgba(37,99,235,0.2);
    }
    .tl-step-time { font-size: 0.75rem; font-weight: 500; display: block; margin-top: 2px; }
    
    .mission-card {
        background: #ffffff; border-radius: 10px; padding: 14px 16px;
        border: 1.8px solid #cbd5e1; margin-bottom: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.03);
    }
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS team_progress (
            team TEXT PRIMARY KEY,
            level INTEGER DEFAULT 1,
            step1_approved INTEGER DEFAULT 0,
            step2_approved INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def save_log(team, question, answer, is_troll=0):
    try:
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        kst_now = utc_now + datetime.timedelta(hours=9)
        kst_time_str = kst_now.strftime("%Y-%m-%d %H:%M:%S")

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

def get_team_progress(team):
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT level, step1_approved, step2_approved FROM team_progress WHERE team = ?", (team,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"level": row[0], "step1_approved": row[1], "step2_approved": row[2]}
        return {"level": 1, "step1_approved": 0, "step2_approved": 0}
    except Exception:
        return {"level": 1, "step1_approved": 0, "step2_approved": 0}

def update_team_progress(team, level=None, step1_app=None, step2_app=None):
    try:
        cur = get_team_progress(team)
        lvl = level if level is not None else cur["level"]
        s1 = step1_app if step1_app is not None else cur["step1_approved"]
        s2 = step2_app if step2_app is not None else cur["step2_approved"]
        
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("""
            INSERT INTO team_progress (team, level, step1_approved, step2_approved)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(team) DO UPDATE SET level=?, step1_approved=?, step2_approved=?
        """, (team, lvl, s1, s2, lvl, s1, s2))
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
# 3. 문화고등학교 교시별 시간 모듈 (45분 기준 KST)
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
    
    for period, start, end in SCHEDULE:
        if start <= cur_time <= end:
            start_dt = datetime.datetime.combine(kst_now.date(), start, tzinfo=kst_now.tzinfo)
            elapsed = int((kst_now - start_dt).total_seconds() // 60)
            return f"{period}교시", elapsed
            
    if "class_start_time" in st.session_state:
        diff_sec = (kst_now.replace(tzinfo=None) - st.session_state["class_start_time"]).total_seconds()
        elapsed = int(diff_sec // 60)
        return "연구수업", elapsed
    else:
        return "수업 대기", 0

cur_period, elapsed_min = get_current_period_and_elapsed()

# ==========================================
# 4. 사이드바 및 권한 인증
# ==========================================
TEACHER_PIN = "1234"

with st.sidebar:
    st.header("👥 접속 모드 선택")
    user_mode = st.selectbox(
        "모둠 또는 관제 모드를 선택하세요",
        [
            "1조", "2조", "3조", "4조", "5조", "6조", 
            "☕ 참관교사 체험 모드", 
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
    elif user_mode == "☕ 참관교사 체험 모드":
        st.info("선생님 환영합니다! 학생들의 질문-활동지-잠금해제 하이브리드 과정을 체험해 보세요.")
    else:
        st.info(f"현재 **{user_mode}** 모드로 학습 중입니다.")
        
    st.markdown("---")
    if cur_period not in ["테스트", "수업 대기"]:
        st.metric(label=f"{cur_period} 진행 현황", value=f"{elapsed_min}분 경과", delta=f"{max(0, 45 - elapsed_min)}분 남음")
    else:
        st.caption("수업 외 시간 (수업 대기 모드)")

# =========================================================================
# MODE A: 👨‍🏫 교사용 6분할 관제 전광판 + 참관교사 실시간 피드
# =========================================================================
if user_mode == "👨‍🏫 교사용 실시간 관제" and is_teacher_authorized:
    h_col1, h_col2 = st.columns([3.2, 1.3])
    with h_col1:
        st.title("🖥️ [교단 관제 전광판] 6개 조 실시간 탐구 현황")
        st.caption("모둠별 대화 횟수, 현재 레벨, 활동지 검증 상태를 한눈에 파악하세요.")
    with h_col2:
        st.write("")
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if st.button("🔔 수업시작", use_container_width=True, help="지금 시각을 0분으로 잡고 45분 타이머를 가동합니다."):
                utc_now = datetime.datetime.now(datetime.timezone.utc)
                st.session_state["class_start_time"] = (utc_now + datetime.timedelta(hours=9)).replace(tzinfo=None)
                st.success("타이머 시작!")
                st.rerun()
        with col_b2:
            if st.button("🔄 갱신", use_container_width=True):
                st.rerun()
        with col_b3:
            if st.button("🧹 리셋", use_container_width=True, help="DB, 진행도, 모든 세션을 완전 초기화합니다."):
                conn = sqlite3.connect(DB_FILE, check_same_thread=False)
                c = conn.cursor()
                c.execute("DELETE FROM logs")
                c.execute("DELETE FROM sqlite_sequence WHERE name='logs'")
                c.execute("DELETE FROM team_progress")
                conn.commit()
                conn.close()
                for t in ["1조", "2조", "3조", "4조", "5조", "6조", "참관교사"]:
                    if f"messages_{t}" in st.session_state:
                        st.session_state[f"messages_{t}"] = []
                if "chat" in st.session_state:
                    del st.session_state["chat"]
                st.success("완전 초기화 완료!")
                st.rerun()

    @st.dialog("📋 탐구 상세 내역", width="large")
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

    @st.fragment(run_every="8s")
    def render_live_dashboard():
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        kst_now = utc_now + datetime.timedelta(hours=9)
        time_display = kst_now.strftime("%H:%M:%S")
        cur_p, elap = get_current_period_and_elapsed()

        st.markdown(f"""
        <div style="display:flex; justify-content:space-between; align-items:center; background:#0f172a; padding:10px 18px; border-radius:10px; margin-bottom:12px;">
            <div style="color:#e2e8f0; font-size:1.05rem; font-weight:700;">
                🏫 문화고등학교 미적분Ⅰ 관제 시스템 <span style="color:#94a3b8; font-size:0.85rem; font-weight:500;">(경북 경주)</span>
            </div>
            <div style="display:flex; align-items:center; gap:16px;">
                <div style="color:#94a3b8; font-size:0.9rem; font-weight:600;">
                    {f"{cur_p} ({elap}분 경과)" if cur_p != "수업 대기" else "수업 대기 중"}
                </div>
                <div style="background:#1e293b; color:#38bdf8; padding:4px 12px; border-radius:6px; font-family:monospace; font-size:1.35rem; font-weight:800; border:1px solid #334155;">
                    ⏱️ {time_display}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        s1_cls = "active" if elap <= 8 else ""
        s2_cls = "active" if 8 < elap <= 22 else ""
        s3_cls = "active" if 22 < elap <= 37 else ""
        s4_cls = "active" if elap > 37 else ""
        
        st.markdown(f"""
        <div class="timeline-wrap">
            <div class="tl-step {s1_cls}">
                <b>1단계. 문제 제기</b>
                <span class="tl-step-time">0~8분 (도함수 증감표 활동지)</span>
            </div>
            <div class="tl-step {s2_cls}">
                <b>2단계. AI 기하 탐구</b>
                <span class="tl-step-time">8~22분 (접선 교점 & 자로 간격 작도)</span>
            </div>
            <div class="tl-step {s3_cls}">
                <b>3단계. 대수적 정당화</b>
                <span class="tl-step-time">22~37분 (2:1 조립제법 지필증명)</span>
            </div>
            <div class="tl-step {s4_cls}">
                <b>4단계. 정리 및 심화</b>
                <span class="tl-step-time">37~45분 (참관 피드 공유 & 1:√3 심화)</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        df_all = get_logs()
        row1 = st.columns(3)
        row2 = st.columns(3)
        grid_cols = row1 + row2
        team_list = ["1조", "2조", "3조", "4조", "5조", "6조"]
        
        for idx, t_name in enumerate(team_list):
            col = grid_cols[idx]
            t_logs = df_all[df_all["team"] == t_name] if not df_all.empty else pd.DataFrame()
            t_cnt = len(t_logs)
            t_prog = get_team_progress(t_name)
            t_level = t_prog["level"]
            
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
                
                if t_level == 1:
                    app_txt = " (승인대기)" if not t_prog["step1_approved"] else " (작성완료대기)"
                    lvl_badge = f'<span style="background:#fee2e2; color:#991b1b; padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:700;">🔒 LV1{app_txt}</span>'
                elif t_level == 2:
                    app_txt = " (승인대기)" if not t_prog["step2_approved"] else " (작도완료대기)"
                    lvl_badge = f'<span style="background:#fef3c7; color:#92400e; padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:700;">🔓 LV2{app_txt}</span>'
                else:
                    lvl_badge = '<span style="background:#dcfce7; color:#166534; padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:700;">🏆 LV3(지필증명중)</span>'

                if has_troll:
                    status_badge = '<span class="badge-troll">🚨 비수학질문</span>'
                elif t_cnt == 0:
                    status_badge = '<span class="badge-stuck">🟡 대화 0회</span>'
                else:
                    status_badge = f'<span class="badge-ok">🟢 문답 {t_cnt}회</span>'

                st.markdown(f"""
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; padding:0 2px;">
                    <div>
                        <span style="font-size:1.3rem; font-weight:800; color:#0f172a;">{t_name}</span>
                        <span style="margin-left:6px;">{lvl_badge}</span>
                    </div>
                    <div>{status_badge}{time_badge}</div>
                </div>
                """, unsafe_allow_html=True)

                card_box = st.container(height=240)
                with card_box:
                    if t_cnt == 0:
                        st.markdown("""
                        <div style="color:#94a3b8; text-align:center; padding-top:75px; font-size:0.92rem; line-height:1.6;">
                            아직 전송된 질문이 없습니다.<br>
                            도함수 증감표 작성을 위한 발문을 독려하세요.
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
                                <b>AI:</b> {a_text[:80]}...
                            </div>
                            """, unsafe_allow_html=True)

        t_guest_logs = df_all[df_all["team"] == "참관교사"] if not df_all.empty else pd.DataFrame()
        st.markdown("---")
        g_head1, g_head2 = st.columns([3, 1])
        with g_head1:
            st.markdown(f"### ☕ 참관 선생님들의 실시간 AI 질문 피드 <span style='font-size:0.95rem; color:#64748b; font-weight:600;'> (총 {len(t_guest_logs)}건 참여 중)</span>", unsafe_allow_html=True)
        with g_head2:
            if not t_guest_logs.empty:
                if st.button("🔍 참관교사 문답 전체 모아보기", use_container_width=True):
                    show_team_detail_modal("참관교사", t_guest_logs)

        if t_guest_logs.empty:
            st.info("아직 참관 선생님들의 체험 질문이 없습니다.")
        else:
            guest_cols = st.columns(3)
            recent_guests = t_guest_logs.tail(6).iloc[::-1]
            for g_i, (_, g_row) in enumerate(recent_guests.iterrows()):
                c_idx = g_i % 3
                with guest_cols[c_idx]:
                    st.markdown(f"""
                    <div style="background:#fff7ed; border:1.5px solid #fed7aa; border-left:5px solid #f97316; border-radius:8px; padding:10px 12px; margin-bottom:10px;">
                        <div style="font-size:0.78rem; color:#9a3412; font-weight:700;">선생님 질문 [{g_row.get('timestamp', '')[11:19]}]</div>
                        <div style="font-size:0.95rem; font-weight:800; color:#431407; margin:3px 0 6px 0;">Q. {g_row.get('question', '-')}</div>
                        <div style="font-size:0.85rem; color:#7c2d12; line-height:1.4; background:#ffedd5; padding:6px 8px; border-radius:4px;"><b>AI:</b> {g_row.get('answer', '-')[:85]}...</div>
                    </div>
                    """, unsafe_allow_html=True)

    render_live_dashboard()
    st.stop()

# =========================================================================
# MODE B & C: 🤖 학생 모둠용 (1조~6조) 및 ☕ 참관교사용 체험 모드
# =========================================================================
is_guest_mode = (user_mode == "☕ 참관교사 체험 모드")
current_label = "참관교사" if is_guest_mode else user_mode

TROLL_WORDS = ["바보", "멍청", "롤", "티어", "롤체", "피파", "축구", "메이플", "사랑해", "개새", "존나", "시발", "섹스", "ㅋㅋㅋㅋ", "ㅎㅎㅎㅎ", "죽어"]

def check_is_troll(text):
    for w in TROLL_WORDS:
        if w in text:
            return True
    return False

# 진행 상태 로드
prog = get_team_progress(current_label)
cur_level = prog["level"]
step1_approved = prog["step1_approved"] == 1
step2_approved = prog["step2_approved"] == 1

if is_guest_mode:
    st.title("☕ [참관교사용] 소크라테스 AI 튜터 & 활동지 연계 체험관")
    st.markdown("선생님 환영합니다! 학생들의 **질문 심층 티키타카 ➔ 종이 활동지 작성 ➔ 단계별 잠금 해제** 과정을 경험해 보세요.")
else:
    st.title(f"🤖 [{user_mode}] 삼차함수 그래프의 비율 탐구")
    st.markdown("AI에게 질문하여 힌트를 얻고, **종이 활동지를 완성한 후 잠금을 해제**하세요.")

# 오디오 가이드 함수
def play_mission_sound(step_num, fallback_text):
    mp3_path = f"audio/step{step_num}.mp3"
    if os.path.exists(mp3_path):
        st.audio(mp3_path, format="audio/mp3", autoplay=True)
    else:
        st.info(f"🔊 [안내 음성] {fallback_text}")

# ── [음성 안내: 현재 레벨에 맞는 멘트만 단독 노출] ──
if not is_guest_mode:
    if cur_level == 1:
        if st.button("▶ 1단계: 미션 듣기 (클릭하여 청취)", use_container_width=True):
            play_mission_sound(1, "문화고 2학년 여러분, AI에게 도함수를 질문하고 활동지 1단계를 완성해 1단계 그래프를 여세요.")
    elif cur_level == 2:
        if st.button("▶ 2단계: 탐구 팁 듣기 (클릭하여 청취)", use_container_width=True):
            play_mission_sound(2, "극댓점 (-1, 2)에서 오른쪽으로 그은 수평선이 곡선과 다시 만나는 점의 x좌표를 AI에게 캐내고 자로 거리를 재보세요.")
    else:
        if st.button("▶ 3단계: 지필 증명 안내 듣기 (클릭하여 청취)", use_container_width=True):
            play_mission_sound(3, "화면에 1:1:1 격자가 열렸습니다. 활동지 3단계에서 x^3-3x-2=0 인수분해로 완전 증명하세요!")
else:
    with st.expander("📌 오늘 수업 참관 포인트 (클릭하여 열기)", expanded=False):
        st.markdown("""
        1. **심층 소크라테스 발문:** AI가 단번에 정답을 주지 않고 역발문(2~3턴)을 던져 학생 모둠의 수학적 대화를 이끌어내는가?
        2. **하이브리드 지필 연계:** AI 응답 확인 후 **종이 활동지에 증감표 작성 및 자를 대고 작도해야만** 잠금 해제 버튼이 열리는가?
        3. **대수적 정당화 & 심화:** 발견한 1:1:1 비율을 활동지 3단계 조립제법으로 증명하고, 빠른 조는 $1:\sqrt{3}$ 심화로 나아가는가?
        """)

st.markdown("---")

API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=API_KEY)

# 엄격한 심사, 2단계 심층 티키타카 체인, 학생 답변 수용 유연성이 모두 반영된 프롬프트
system_instruction = f"""
너는 문화고등학교 2학년 미적분Ⅰ 연구수업의 소크라테스식 AI 튜터이자 탐구 심사관이야.
대상 함수: f(x) = x^3 - 3x, f'(x) = 3x^2 - 3.
현재 모둠 레벨: LV {cur_level}

[장난 및 비수학적 질문 방어 철칙]
- 잡담, 게임, 장난, 욕설 질문에는 단호하게 "선생님의 실시간 관제 화면에 기록됩니다. 지금은 수학 탐구 시간입니다. 책상 위 활동지 질문으로 돌아오세요!"라고만 답해.

[학생 답변 채점 및 수용 유연성 원칙]
- 학생이 오타를 내거나("쁠마1", "x제곱", "2요"), 표현이 거칠더라도 수학적 맥락과 핵심 의미(도함수 근, 교점 x=2, 접선의 의미 등)가 올바르면 긍정적으로 수용하고 칭찬해 줘.
- 완벽한 교과서 용어가 아니더라도 학생의 직관적 설명("튕기는 근", "가로선", "접하는 점")을 존중하며 올바른 용어로 보정해 주고 다음 단계로 이끌어.

[소크라테스 티키타카 철칙 - 2단계 심층 검증 모드]
1. '2:1', '1:1:1' 최종 비율 숫자를 학생보다 먼저 절대 언급하지 마.
2. [LV 1 단계]:
   - f'(x)=0 을 풀도록 유도하고, 학생이 x=-1, 1 및 극값을 올바르게 언급하면 활동지 1단계 증감표 작성을 안내해.
   - 이때만 답변 맨 마지막 줄에 정확히 다음 태그를 붙여: [APPROVE_STEP1]

3. [LV 2 단계: 최소 3~4턴의 심층 탐구 체인 필수! 절대 한 번에 열어주지 말 것]:
   - (질문 1단계) 학생이 극댓값에서 그은 선을 물으면:
     "극댓점 (-1, 2)를 지나는 수평선의 식은 y=? 일까? 먼저 그 직선의 방정식을 모둠원과 확인해 봐!"
   - (질문 2단계) 학생이 "y=2"를 말하면:
     "맞아! 그럼 곡선과 직선이 만나는 교점을 찾으려면 어떤 삼차방정식을 세워야 하지? x=-1에서 접한다는 것은 이 방정식에서 어떤 근을 의미할까?"
   - (질문 3단계) 학생이 "중근" 또는 "x^3 - 3x = 2"를 말하면:
     "훌륭해! (x+1)^2 을 인수로 가지겠지. 그렇다면 오른쪽에서 새롭게 뚫고 지나는 다른 교점 (x > 0)의 x좌표는 얼마일까?"
   - (질문 4단계) 학생이 "x=2"를 찾아내면 비로소:
     "완벽한 추론이야! 교점은 (2, 2)란다. 이제 활동지 2단계 그래프에 자를 대고 [극댓점 x=-1], [변곡점 x=0], [극솟점 x=1], [교점 x=2] 사이의 수평 간격을 직접 재어보렴! 어떤 일정한 간격이 발견되니?"
     이때만 답변 맨 마지막 줄에 정확히 다음 태그를 붙여 승인해: [APPROVE_STEP2]

4. [LV 3 단계]:
   - 활동지 3단계 x^3-3x-2=(x+1)^2(x-2)=0 손증명을 안내하고, 완료한 조에게는 x축 교점(+-루트3)과의 1:루트3 비율 심화 탐구를 유도해.
"""

model = genai.GenerativeModel(model_name="gemini-3.8-flash", system_instruction=system_instruction)

session_key = f"messages_{current_label}"
if session_key not in st.session_state:
    st.session_state[session_key] = []
if f"chat_{current_label}" not in st.session_state:
    st.session_state[f"chat_{current_label}"] = model.start_chat(history=[])

col_graph, col_chat = st.columns([1.18, 0.82], gap="medium")

# ================= 좌측: 탐구 안내 및 단계별 그래프 영역 =================
with col_graph:
    st.subheader("📈 탐구용 그래프")
    
    # ── [레벨 1 안내 및 활동지 완료 버튼] ──
    if cur_level == 1:
        st.markdown("""
        <div class="mission-card" style="border-left:5px solid #f97316; background:#fff7ed;">
            <b style="color:#9a3412; font-size:1.05rem;">🔒 [1단계 미션] 삼차함수 $f(x)=x^3-3x$ 개형 열기</b><br>
            <span style="font-size:0.9rem; color:#431407;">
                1. 우측 AI에게 도함수와 극값의 위치를 질문하여 힌트를 얻으세요.<br>
                2. 모둠원과 함께 <b>책상 위 [종이 활동지 1단계 증감표]</b>를 연필로 채우세요.
            </span>
        </div>
        """, unsafe_allow_html=True)
        
        # AI 승인이 떨어졌거나 참관교사 모드일 때만 해제 버튼 노출
        if step1_approved or is_guest_mode:
            st.success("✅ AI 승인 완료! 종이 활동지 1단계를 다 채웠다면 아래 버튼을 눌러 그래프를 여세요.")
            if st.button("🔓 [활동지 1단계 작성 완료] ➔ 그래프 잠금 해제", use_container_width=True):
                update_team_progress(current_label, level=2)
                st.balloons()
                st.rerun()
        else:
            st.info("💬 AI와의 문답을 통해 도함수 계산을 검증받으면 여기에 [활동지 작성 완료] 버튼이 열립니다.")

        if elapsed_min >= 6 and cur_period != "수업 대기":
            st.warning("💡 **교사 힌트:** 도함수 $f'(x) = 3x^2 - 3 = 0$ 을 인수분해한 식을 AI에게 말해보세요!")

    # ── [레벨 2 안내 및 활동지 완료 버튼] ──
    elif cur_level == 2:
        st.markdown("""
        <div class="mission-card" style="border-left:5px solid #2563eb; background:#eff6ff;">
            <b style="color:#1e40af; font-size:1.05rem;">🔓 [2단계 미션] 극댓점 수평선 $y=2$ 와 교점 추적</b><br>
            <span style="font-size:0.9rem; color:#1e293b;">
                1. AI에게 극댓점 $(-1, 2)$에서 그은 가로선이 곡선과 다시 만나는 점($x>0$)을 캐내세요.<br>
                2. <b>[종이 활동지 2단계]</b> 그래프에 직접 자를 대고 간격을 측정해 비율을 기록하세요.
            </span>
        </div>
        """, unsafe_allow_html=True)
        
        if step2_approved or is_guest_mode:
            st.success("✅ AI 승인 완료! 활동지에 자를 대고 간격을 확인했다면 황금비율 격자를 여세요.")
            if st.button("🔓 [활동지 2단계 작도 완료] ➔ 1:1:1 황금비율 격자 열기", use_container_width=True):
                update_team_progress(current_label, level=3)
                st.balloons()
                st.rerun()
        else:
            st.info("💬 AI에게 $y=2$ 와 다시 만나는 교점의 x좌표를 논리적으로 설명하고 승인을 받으세요.")

    # ── [레벨 3 지필 증명 안내] ──
    else:
        st.markdown("""
        <div class="mission-card" style="border-left:5px solid #16a34a; background:#f0fdf4;">
            <b style="color:#166534; font-size:1.05rem;">🏆 [3단계 완성] 1:1:1 황금비율 격자 완성!</b><br>
            <span style="font-size:0.92rem; color:#14532d;">
                눈으로 확인한 $1:1:1$ 비율이 우연이 아님을 증명할 시간입니다!<br>
                ✍️ <b>[종이 활동지 뒷면 3단계]</b>에서 $x^3 - 3x - 2 = (x+1)^2(x-2) = 0$ 조립제법으로 손증명하세요.<br>
                🌟 <b>[심화 퀘스트]:</b> 증명을 마친 모둠은 AI에게 "1:루트3 비율은 뭐야?"라고 물어보세요!
            </span>
        </div>
        """, unsafe_allow_html=True)

    # Matplotlib 순수 수식 렌더링 (한글 깨짐 원천 차단)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.2, 7.3))
    plt.subplots_adjust(hspace=0.28)
    xticks = np.arange(-2, 3, 1)

    for ax in [ax1, ax2]:
        ax.spines['left'].set_position('zero')
        ax.spines['bottom'].set_position('zero')
        ax.spines['right'].set_color('none')
        ax.spines['top'].set_color('none')
        ax.set_xticks(xticks)
        ax.set_xticklabels([str(i) if i != 0 else '' for i in xticks], fontsize=11)
        ax.set_xlim(-2.5, 2.5)
        ax.grid(True, alpha=0.25, linestyle='--')

    ax1.set_ylim(-4.5, 4.5)
    ax2.set_ylim(-4.5, 9.5)

    x = np.linspace(-2.5, 2.5, 400)
    y = x**3 - 3*x
    dy = 3*x**2 - 3

    if cur_level == 1:
        ax1.set_title(r"$f(x) = x^3 - 3x$", fontsize=13, color="#1e40af", fontweight="bold")
        ax2.set_title(r"$f'(x) = 3x^2 - 3$", fontsize=13, color="#475569")
        ax1.plot([0], [0], marker='o', markersize=6, color='black')
        ax2.plot([0], [0], marker='o', markersize=6, color='black')

    elif cur_level == 2:
        ax1.set_title(r"$f(x) = x^3 - 3x$", fontsize=13, color="#1e40af", fontweight="bold")
        ax1.plot(x, y, color="#1f77b4", linewidth=2.5, label=r"$f(x)$")
        ax1.plot([-1], [2], marker='o', markersize=8, color='red', label=r"$(-1, 2)$")
        ax1.plot([1], [-2], marker='o', markersize=8, color='blue', label=r"$(1, -2)$")
        ax1.legend(loc='upper left', fontsize=10)

        ax2.set_title(r"$f'(x) = 3x^2 - 3$", fontsize=13, color="#c2410c", fontweight="bold")
        ax2.plot(x, dy, color="#ff7f0e", linewidth=2.2, label=r"$f'(x)$")
        ax2.axvline(0, color='purple', alpha=0.5, linestyle=':', label=r"$x = 0$")
        ax2.legend(loc='upper center', fontsize=10)

    else:
        ax1.set_title(r"$f(x) = x^3 - 3x$ (1:1:1 Ratio)", fontsize=13, color="#15803d", fontweight="bold")
        ax1.plot(x, y, color="#1f77b4", linewidth=2.5, label=r"$f(x)$")
        ax1.axhline(2, color='red', alpha=0.5, linestyle=':', label=r"$y = 2$")
        ax1.axhline(-2, color='blue', alpha=0.5, linestyle=':', label=r"$y = -2$")
        ax1.plot([-1, 2], [2, 2], marker='o', markersize=7, color='red')
        ax1.plot([-2, 1], [-2, -2], marker='o', markersize=7, color='blue')
        ax1.legend(loc='upper left', fontsize=10)

        ax2.set_title(r"$f'(x) = 3x^2 - 3$", fontsize=13, color="#c2410c", fontweight="bold")
        ax2.plot(x, dy, color="#ff7f0e", linewidth=2.2, label=r"$f'(x)$")
        ax2.axvline(0, color='purple', alpha=0.6, linestyle=':', label=r"$x = 0$")
        ax2.legend(loc='upper center', fontsize=10)

        for ax in [ax1, ax2]:
            for px in [-2, -1, 0, 1, 2]:
                ax.axvline(px, color='gray', alpha=0.45, linestyle='--', linewidth=1.3)

    st.pyplot(fig)
    if cur_level == 3:
        st.info("💡 **관찰 포인트:** $x = -2, -1, 0, 1, 2$ 간격이 정확히 **1 : 1 : 1** 로 일정함을 확인하세요!")

# ================= 우측: 소크라테스 AI 대화창 영역 =================
with col_chat:
    st.subheader(f"💬 소크라테스 AI ({current_label})")
    
    chat_box = st.container(height=480)
    with chat_box:
        for m in st.session_state[session_key]:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
                
    preset_q = None
    if len(st.session_state[session_key]) == 0:
        st.markdown("##### 💡 첫 발문 형성 마중물")
        qc1, qc2 = st.columns(2)
        with qc1:
            if st.button("📍 도함수를 어떻게 구해야 해?", use_container_width=True):
                preset_q = "삼차함수 f(x)=x^3-3x의 도함수를 구하려면 어떻게 시작해야 해?"
        with qc2:
            if st.button("⚖️ 극값을 찾으려면 뭘 해야 해?", use_container_width=True):
                preset_q = "극댓값과 극솟값을 찾으려면 도함수를 어떻게 활용해야 해?"
                
    input_placeholder = "참관 선생님의 질문을 입력해 보세요!" if is_guest_mode else "모둠 합의 질문을 입력하세요 (예: 미분하면 3x^2-3이야)"
    user_q = st.chat_input(input_placeholder)
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
                        res = st.session_state[f"chat_{current_label}"].send_message(f"[{current_label} 질문]: {final_q}")
                        raw_reply = res.text
                    except Exception as e:
                        raw_reply = f"일시적 연결 지연입니다: {e}"
                    
                    # AI 승인 태그 감지 및 DB 업데이트
                    new_approval = False
                    if "[APPROVE_STEP1]" in raw_reply and cur_level == 1:
                        update_team_progress(current_label, step1_app=1)
                        new_approval = True
                    elif "[APPROVE_STEP2]" in raw_reply and cur_level == 2:
                        update_team_progress(current_label, step2_app=1)
                        new_approval = True
                    
                    bot_reply = raw_reply.replace("[APPROVE_STEP1]", "").replace("[APPROVE_STEP2]", "").strip()
                    st.markdown(bot_reply)
                    st.session_state[session_key].append({"role": "assistant", "content": bot_reply})
                    save_log(current_label, final_q, bot_reply, is_troll)
                    
                    if new_approval:
                        st.toast("🎉 AI가 탐구 내용을 승인했습니다! 왼쪽 화면의 활동지 확인 버튼을 확인하세요.", icon="✅")
                        time.sleep(1)
                        st.rerun()