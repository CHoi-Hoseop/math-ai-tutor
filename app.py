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
    
    /* 잠금 해제 미션 박스 */
    .mission-box {
        background: #f0fdf4; border: 1.8px solid #86efac; border-radius: 10px;
        padding: 12px 16px; margin-bottom: 12px;
    }
    .mission-box.lock {
        background: #fffbeb; border-color: #fde047;
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
    # 조별 그래프 잠금해제 레벨 기록 테이블
    c.execute("""
        CREATE TABLE IF NOT EXISTS team_progress (
            team TEXT PRIMARY KEY,
            level INTEGER DEFAULT 1
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

def update_team_level(team, level):
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO team_progress (team, level) VALUES (?, ?)", (team, level))
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_team_level(team):
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT level FROM team_progress WHERE team = ?", (team,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else 1
    except Exception:
        return 1

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
# 3. 문화고등학교 교시별 시간 모듈 (KST 고정)
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
        st.info("선생님 환영합니다! 학생들과 동일하게 AI 튜터 및 단계별 잠금 해제를 체험해 보실 수 있습니다.")
    else:
        st.info(f"현재 **{user_mode}** 모드로 학습 중입니다.")
        
    st.markdown("---")
    if cur_period not in ["테스트", "수업 대기"]:
        st.metric(label=f"{cur_period} 진행 현황", value=f"{elapsed_min}분 경과", delta=f"{max(0, 47 - elapsed_min)}분 남음")
    else:
        st.caption("수업 외 시간 (수업 대기 모드)")

# =========================================================================
# MODE A: 👨‍🏫 교사용 6분할 관제 전광판 + 참관교사 실시간 피드
# =========================================================================
if user_mode == "👨‍🏫 교사용 실시간 관제" and is_teacher_authorized:
    h_col1, h_col2 = st.columns([3.2, 1.3])
    with h_col1:
        st.title("🖥️ [교단 관제 전광판] 6개 조 실시간 탐구 현황")
        st.caption("조별 카드에서 진행 레벨과 대화 내역을 실시간으로 확인하고 밀착 피드백하세요.")
    with h_col2:
        st.write("")
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if st.button("🔔 수업시작", use_container_width=True, help="지금 시각을 0분으로 잡고 47분 타이머를 가동합니다."):
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
                    if f"level_{t}" in st.session_state:
                        st.session_state[f"level_{t}"] = 1
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

        # 1. KST 시계 바
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

        # 2. 4단계 타임라인 진행 바
        s1_cls = "active" if elap <= 10 else ""
        s2_cls = "active" if 10 < elap <= 25 else ""
        s3_cls = "active" if 25 < elap <= 40 else ""
        s4_cls = "active" if elap > 40 else ""
        
        st.markdown(f"""
        <div class="timeline-wrap">
            <div class="tl-step {s1_cls}">
                <b>1단계. 문제 제기</b>
                <span class="tl-step-time">0~10분 (도함수 극점 해제)</span>
            </div>
            <div class="tl-step {s2_cls}">
                <b>2단계. AI 기하 탐구</b>
                <span class="tl-step-time">10~25분 (수평교점 & 1:1:1)</span>
            </div>
            <div class="tl-step {s3_cls}">
                <b>3단계. 대수적 정당화</b>
                <span class="tl-step-time">25~40분 (2:1 조립제법 증명)</span>
            </div>
            <div class="tl-step {s4_cls}">
                <b>4단계. 정리 및 심화</b>
                <span class="tl-step-time">40~47분 (1:√3 확장)</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 3. 6개 조 카드 렌더링
        df_all = get_logs()
        row1 = st.columns(3)
        row2 = st.columns(3)
        grid_cols = row1 + row2
        team_list = ["1조", "2조", "3조", "4조", "5조", "6조"]
        
        for idx, t_name in enumerate(team_list):
            col = grid_cols[idx]
            t_logs = df_all[df_all["team"] == t_name] if not df_all.empty else pd.DataFrame()
            t_cnt = len(t_logs)
            t_level = get_team_level(t_name)
            
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
                
                # 레벨 배지
                if t_level == 1:
                    lvl_badge = '<span style="background:#fee2e2; color:#991b1b; padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:700;">🔒 LV1(극점탐색)</span>'
                elif t_level == 2:
                    lvl_badge = '<span style="background:#fef3c7; color:#92400e; padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:700;">🔓 LV2(교점탐색)</span>'
                else:
                    lvl_badge = '<span style="background:#dcfce7; color:#166534; padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:700;">🏆 LV3(비율완성)</span>'

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
                            1단계 도함수 극점 해제를 독려해 주세요.
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

        # 4. 참관 교사 질문 피드
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
            st.info("아직 참관 선생님들의 체험 질문이 없습니다. (참관 교사 모드에서 질문 시 여기에 실시간 표출됩니다.)")
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

# 세션 레벨 동기화
if f"level_{current_label}" not in st.session_state:
    st.session_state[f"level_{current_label}"] = get_team_level(current_label)

cur_level = st.session_state[f"level_{current_label}"]

if is_guest_mode:
    st.title("☕ [참관교사용] 소크라테스 AI 튜터 & 단계별 탐구 체험관")
    st.markdown("선생님 환영합니다! 학생들이 겪는 **단계별 잠금 해제와 소크라테스 유도 발문**을 직접 경험해 보세요.")
else:
    st.title(f"🤖 [{user_mode}] 삼차함수 그래프의 비율 탐구")
    st.markdown("미션을 해결하여 그래프를 잠금 해제하고, AI와 문답하며 **종이 활동지**에 기록하세요.")

# 오디오 가이드 (MP3 우선, 없으면 텍스트 안내)
def play_mission_sound(step_num, fallback_text):
    mp3_path = f"audio/step{step_num}.mp3"
    if os.path.exists(mp3_path):
        st.audio(mp3_path, format="audio/mp3", autoplay=True)
    else:
        st.info(f"🔊 [안내 음성] {fallback_text}")

if not is_guest_mode:
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("▶ 1단계: 미션 듣기", use_container_width=True):
            play_mission_sound(1, "문화고 2학년 여러분, 활동지 1단계를 풀어 극댓값과 극솟값의 x좌표를 화면에 입력하여 그래프를 잠금 해제하세요.")
    with b2:
        if st.button("▶ 2단계: 탐구 팁", use_container_width=True):
            play_mission_sound(2, "극댓점 (-1, 2)에서 오른쪽으로 수평선을 그었을 때 곡선과 다시 만나는 점의 x좌표를 AI에게 캐내보세요.")
    with b3:
        if st.button("▶ 3단계: 증명 안내", use_container_width=True):
            play_mission_sound(3, "화면에 1:1:1 격자가 열렸습니다. 활동지 3단계에서 x^3-3x-2=0 인수분해로 완전 증명하세요!")
else:
    with st.expander("📌 오늘 수업 참관 포인트 (클릭하여 열기)", expanded=False):
        st.markdown("""
        1. **단계별 시각화 비계(Scaffolding):** 처음부터 완성된 그래프를 주지 않고 학생의 극점·교점 계산에 따라 단계적으로 열어가는가?
        2. **하이브리드 연계:** AI 응답을 확인한 후 **종이 활동지 2단계 그래프에 자를 대고 간격(2:1, 1:1:1)을 직접 작도·기록**하는가?
        3. **대수적 정당화:** 발견한 기하적 비율을 활동지 3단계에서 $x^3-3x-2=0$ 인수분해를 통해 스스로 증명해 내는가?
        """)

st.markdown("---")

API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=API_KEY)

system_instruction = """
너는 문화고등학교 2학년 미적분Ⅰ 연구수업의 소크라테스식 AI 튜터야.
대상 함수: f(x) = x^3 - 3x, f'(x) = 3x^2 - 3.

[장난 및 비수학적 질문 방어 철칙 (Strict Guardrail)]
- 게임, 일상 잡담, 장난, 욕설 질문이 들어오면 맞장구치지 마.
- 단호하고 정중하게 "선생님의 실시간 관제 화면에 질문이 기록되고 있습니다. 지금은 삼차함수 탐구 시간입니다. 책상 위 활동지 수학 질문으로 돌아오세요!"라고만 답할 것.

[소크라테스 유도 철칙]
- '2:1', '1:1:1' 최종 비율 숫자를 학생보다 먼저 절대 말하지 마.
- 극댓점은 (-1, 2), 극솟점은 (1, -2)야.
- y = 2 수평선과 다시 만나는 교점은 (2, 2)야.
- 학생이 극점이나 교점을 물어보면 그 좌표는 알려주되, "극댓점 (-1, 2)에서 y=2를 그었을 때 다시 만나는 점의 x좌표는 몇일까?" 처럼 항상 화면 그래프를 보게 하는 꼬리 질문(모둠 미션)을 던져.
- 답변 끝에는 항상 "✍️ [활동지 기록] 방금 확인한 내용을 종이 활동지에 연필로 적으세요!"를 붙일 것.
"""

model = genai.GenerativeModel(model_name="gemini-3.8-flash", system_instruction=system_instruction)

session_key = f"messages_{current_label}"
if session_key not in st.session_state:
    st.session_state[session_key] = []
if f"chat_{current_label}" not in st.session_state:
    st.session_state[f"chat_{current_label}"] = model.start_chat(history=[])

col_graph, col_chat = st.columns([1.18, 0.82], gap="medium")

# ================= 좌측: 단계별 잠금 해제형 그래프 영역 =================
with col_graph:
    st.subheader("📈 탐구용 그래프")
    
    # ── [레벨 1 미션 박스: 극점 입력] ──
    if cur_level == 1:
        st.markdown("""
        <div class="mission-box lock">
            <b>🔒 [1단계 잠금] 삼차함수 $f(x) = x^3 - 3x$ 의 개형을 밝혀내세요!</b><br>
            <span style="font-size:0.9rem; color:#475569;">도함수 $f'(x) = 0$이 되는 두 극점의 $x$좌표를 구해 아래에 입력하세요.</span>
        </div>
        """, unsafe_allow_html=True)
        
        m_c1, m_c2, m_btn = st.columns([1, 1, 1.2])
        with m_c1:
            in_max_x = st.text_input("극댓값 $x$좌표", key=f"in_max_{current_label}", placeholder="-1")
        with m_c2:
            in_min_x = st.text_input("극솟값 $x$좌표", key=f"in_min_{current_label}", placeholder="1")
        with m_btn:
            st.write("")
            if st.button("🔓 1단계 해제", use_container_width=True):
                if in_max_x.strip() == "-1" and in_min_x.strip() == "1":
                    st.session_state[f"level_{current_label}"] = 2
                    update_team_level(current_label, 2)
                    st.success("🎉 정답입니다! 삼차함수 곡선과 도함수가 열렸습니다.")
                    st.rerun()
                else:
                    st.error("좌표를 다시 확인하세요. (힌트: 도함수 $3x^2 - 3 = 0$)")
        
        # 8분 경과 시 자동 힌트 제공
        if elapsed_min >= 8 and cur_period != "수업 대기":
            st.info("💡 **교사 힌트 도착:** $f'(x) = 3(x+1)(x-1) = 0$ 을 만족하는 $x$를 찾아보세요!")

    # ── [레벨 2 미션 박스: 교점 입력] ──
    elif cur_level == 2:
        st.markdown("""
        <div class="mission-box lock">
            <b>🔓 [2단계 잠금] 극댓점 $(-1, 2)$의 수평선 $y = 2$ 와 만나는 다른 교점은?</b><br>
            <span style="font-size:0.9rem; color:#475569;">AI에게 질문하거나 $x^3 - 3x = 2$ 를 풀어 교점의 $x$좌표를 입력하세요.</span>
        </div>
        """, unsafe_allow_html=True)
        
        m2_c1, m2_btn = st.columns([1.5, 1.2])
        with m2_c1:
            in_cross_x = st.text_input("교점의 $x$좌표 ($x > 0$)", key=f"in_cross_{current_label}", placeholder="2")
        with m2_btn:
            st.write("")
            if st.button("🔓 황금비율 해제", use_container_width=True):
                if in_cross_x.strip() == "2":
                    st.session_state[f"level_{current_label}"] = 3
                    update_team_level(current_label, 3)
                    st.success("🎉 대단합니다! 삼차함수의 1:1:1 황금비율 격자가 모두 열렸습니다.")
                    st.rerun()
                else:
                    st.error("다시 계산해 보세요. (AI에게 'y=2와 다시 만나는 점은 어디야?'라고 질문해 보세요!)")
                    
    # ── [레벨 3 완료 박스] ──
    else:
        st.markdown("""
        <div class="mission-box">
            <b>🏆 [3단계 완성] 1:1:1 황금비율 격자가 모두 밝혀졌습니다!</b><br>
            <span style="font-size:0.9rem; color:#166534;">종이 활동지 뒷면 3단계에서 $x^3 - 3x - 2 = (x+1)^2(x-2) = 0$ 인수분해로 완전 증명하세요!</span>
        </div>
        """, unsafe_allow_html=True)

    # ── Matplotlib 단계별 렌더링 (한글 깨짐 원천 방지: 수식 및 영문 표기) ──
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.2, 7.3))
    plt.subplots_adjust(hspace=0.28)
    xticks = np.arange(-2, 3, 1)

    # 공통 좌표축 세팅
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
        # [LV 1] 빈 좌표평면: 수식만 깔끔하게 표시
        ax1.set_title("$f(x) = x^3 - 3x$ [Locked]", fontsize=13, color="#2563eb", fontweight="bold")
        ax2.set_title("$f'(x) = 3x^2 - 3$ [Locked]", fontsize=13, color="#64748b")
        ax1.plot([0], [0], marker='o', markersize=6, color='black')
        ax2.plot([0], [0], marker='o', markersize=6, color='black')

    elif cur_level == 2:
        # [LV 2] 곡선 + 도함수 + 극점 (수식 라벨)
        ax1.set_title("$f(x) = x^3 - 3x$", fontsize=13, color="#1e3a8a", fontweight="bold")
        ax1.plot(x, y, color="#1f77b4", linewidth=2.5, label="$f(x)$")
        ax1.plot([-1], [2], marker='o', markersize=8, color='red', label="Max $(-1, 2)$")
        ax1.plot([1], [-2], marker='o', markersize=8, color='blue', label="Min $(1, -2)$")
        ax1.legend(loc='upper left', fontsize=10)

        ax2.set_title("$f'(x) = 3x^2 - 3$", fontsize=13, color="#c2410c", fontweight="bold")
        ax2.plot(x, dy, color="#ff7f0e", linewidth=2.2, label="$f'(x)$")
        ax2.axvline(0, color='purple', alpha=0.5, linestyle=':', label="$x = 0$")
        ax2.legend(loc='upper center', fontsize=10)

    else:
        # [LV 3] 완성형: 접선 및 격자 풀세트
        ax1.set_title("$f(x) = x^3 - 3x$ [Ratio 1:1:1 Unlocked]", fontsize=13, color="#16a34a", fontweight="bold")
        ax1.plot(x, y, color="#1f77b4", linewidth=2.5, label="$f(x)$")
        ax1.axhline(2, color='red', alpha=0.5, linestyle=':', label="$y = 2$")
        ax1.axhline(-2, color='blue', alpha=0.5, linestyle=':', label="$y = -2$")
        ax1.plot([-1, 2], [2, 2], marker='o', markersize=7, color='red')
        ax1.plot([-2, 1], [-2, -2], marker='o', markersize=7, color='blue')
        ax1.legend(loc='upper left', fontsize=10)

        ax2.set_title("$f'(x) = 3x^2 - 3$", fontsize=13, color="#c2410c", fontweight="bold")
        ax2.plot(x, dy, color="#ff7f0e", linewidth=2.2, label="$f'(x)$")
        ax2.axvline(0, color='purple', alpha=0.6, linestyle=':', label="Axis $x=0$")
        ax2.legend(loc='upper center', fontsize=10)

        # 1:1:1 황금비율 수직선
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
        st.markdown("##### 💡 마중물 첫 질문")
        qc1, qc2 = st.columns(2)
        with qc1:
            if st.button("📍 극댓값/극솟값 x좌표는?", use_container_width=True):
                preset_q = "극댓값과 극솟값의 x좌표는 각각 뭐야?"
        with qc2:
            if st.button("⚖️ 도함수 대칭축 x=0의 의미는?", use_container_width=True):
                preset_q = "아래쪽 도함수의 대칭축 x=0은 위 삼차함수에서 어떤 점이야?"
                
    input_placeholder = "참관 선생님의 질문을 입력해 보세요!" if is_guest_mode else "모둠 합의 질문을 입력하세요"
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
                        bot_reply = res.text
                    except Exception as e:
                        bot_reply = f"일시적 연결 지연입니다: {e}"
                        
                    st.markdown(bot_reply)
                    st.session_state[session_key].append({"role": "assistant", "content": bot_reply})
                    save_log(current_label, final_q, bot_reply, is_troll)
        st.rerun()