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
    h1 { font-size: 1.9rem !important; font-weight: 800 !important; }
    h2, h3 { font-weight: 700 !important; }
    
    .stChatMessage p, .stChatMessage li, .stChatMessage div {
        font-size: 1.12rem !important;
        line-height: 1.65 !important;
    }
    
    .badge-ok { background: #dcfce7; color: #15803d; padding: 3px 8px; border-radius: 6px; font-size: 0.78rem; font-weight: 700; }
    .badge-stuck { background: #fef3c7; color: #b45309; padding: 3px 8px; border-radius: 6px; font-size: 0.78rem; font-weight: 800; }
    .badge-troll { background: #fee2e2; color: #b91c1c; padding: 3px 8px; border-radius: 6px; font-size: 0.78rem; font-weight: 800; }
    .badge-time { background: #e0f2fe; color: #0369a1; padding: 3px 8px; border-radius: 6px; font-size: 0.78rem; font-weight: 700; margin-left: 5px; }

    .timeline-wrap { display: flex; gap: 8px; margin: 10px 0 14px 0; }
    .tl-step {
        flex: 1; padding: 8px 10px; border-radius: 8px;
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
    
    .primer-box {
        background: #f8fafc; border: 1.5px dashed #94a3b8; border-radius: 8px;
        padding: 10px 14px; margin-bottom: 10px;
    }

    .top-timer-bar {
        display: flex; justify-content: space-between; align-items: center;
        background: #0f172a; color: #f8fafc; padding: 10px 18px;
        border-radius: 10px; margin-bottom: 14px;
        border: 1px solid #334155;
    }

    .unlock-alert-box {
        background: #dcfce7;
        border: 3px solid #16a34a;
        border-radius: 12px;
        padding: 14px 18px;
        margin: 10px 0;
        color: #14532d;
        font-size: 1.1rem;
        font-weight: 800;
        text-align: center;
        box-shadow: 0 4px 12px rgba(22, 163, 74, 0.25);
    }

    button[kind="primary"] {
        background-color: #16a34a !important;
        border-color: #15803d !important;
        color: white !important;
        font-size: 1.15rem !important;
        font-weight: 800 !important;
        padding: 0.7rem 1.1rem !important;
        border-radius: 10px !important;
        box-shadow: 0 4px 10px rgba(22, 163, 74, 0.3) !important;
    }
    button[kind="primary"]:hover {
        background-color: #15803d !important;
        border-color: #14532d !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 로컬 SQLite 경량 공유 DB 모듈 (수업 시작 시간 전 기기 완벽 공유)
# ==========================================
DB_FILE = "class_monitor.db"

def get_kst_now():
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    return (utc_now + datetime.timedelta(hours=9)).replace(tzinfo=None)

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
            step2_approved INTEGER DEFAULT 0,
            stage_start_time TEXT,
            hint1_sent INTEGER DEFAULT 0,
            hint2_sent INTEGER DEFAULT 0
        )
    """)
    # 교사가 누른 '수업 시작 시간'을 모든 학생 태블릿과 참관교사 폰에 공유하기 위한 글로벌 상태 테이블
    c.execute("""
        CREATE TABLE IF NOT EXISTS class_state (
            key TEXT PRIMARY KEY,
            val TEXT
        )
    """)
    for col_def in [
        ("step1_approved", "INTEGER DEFAULT 0"),
        ("step2_approved", "INTEGER DEFAULT 0"),
        ("stage_start_time", "TEXT"),
        ("hint1_sent", "INTEGER DEFAULT 0"),
        ("hint2_sent", "INTEGER DEFAULT 0")
    ]:
        try:
            c.execute(f"ALTER TABLE team_progress ADD COLUMN {col_def[0]} {col_def[1]}")
        except Exception:
            pass
    conn.commit()
    conn.close()

def set_global_class_start(now_str):
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT 1 FROM class_state WHERE key = 'class_start_time'")
        if c.fetchone():
            c.execute("UPDATE class_state SET val = ? WHERE key = 'class_start_time'", (now_str,))
        else:
            c.execute("INSERT INTO class_state (key, val) VALUES ('class_start_time', ?)", (now_str,))
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_global_class_start():
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT val FROM class_state WHERE key = 'class_start_time'")
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None

def save_log(team, question, answer, is_troll=0):
    try:
        kst_time_str = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
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
    now_str = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("""
            SELECT level, step1_approved, step2_approved, stage_start_time, hint1_sent, hint2_sent 
            FROM team_progress WHERE team = ?
        """, (team,))
        row = c.fetchone()
        if not row:
            c.execute("""
                INSERT INTO team_progress (team, level, step1_approved, step2_approved, stage_start_time, hint1_sent, hint2_sent)
                VALUES (?, 1, 0, 0, ?, 0, 0)
            """, (team, now_str))
            conn.commit()
            conn.close()
            return {
                "level": 1, "step1_approved": 0, "step2_approved": 0,
                "stage_start_time": now_str, "hint1_sent": 0, "hint2_sent": 0
            }
        conn.close()
        return {
            "level": int(row[0]) if row[0] is not None else 1,
            "step1_approved": int(row[1]) if row[1] is not None else 0,
            "step2_approved": int(row[2]) if row[2] is not None else 0,
            "stage_start_time": row[3] if row[3] else now_str,
            "hint1_sent": int(row[4]) if row[4] is not None else 0,
            "hint2_sent": int(row[5]) if row[5] is not None else 0
        }
    except Exception:
        return {
            "level": 1, "step1_approved": 0, "step2_approved": 0,
            "stage_start_time": now_str, "hint1_sent": 0, "hint2_sent": 0
        }

def update_team_progress(team, level=None, step1_app=None, step2_app=None, reset_timer=False, hint1=None, hint2=None):
    # 참관교사는 공용 DB가 아닌 각자 스마트폰 메모리(세션)에만 개별 저장하여 화면 섞임 방지!
    if team == "참관교사":
        if level is not None:
            st.session_state["mem_lvl_참관교사"] = level
        if step1_app is not None:
            st.session_state["mem_s1_참관교사"] = step1_app
        if step2_app is not None:
            st.session_state["mem_s2_참관교사"] = step2_app
        return

    cur = get_team_progress(team)
    lvl = level if level is not None else cur["level"]
    s1 = step1_app if step1_app is not None else cur["step1_approved"]
    s2 = step2_app if step2_app is not None else cur["step2_approved"]
    st_time = get_kst_now().strftime("%Y-%m-%d %H:%M:%S") if reset_timer else cur["stage_start_time"]
    h1 = hint1 if hint1 is not None else cur["hint1_sent"]
    h2 = hint2 if hint2 is not None else cur["hint2_sent"]

    st.session_state[f"mem_lvl_{team}"] = lvl
    st.session_state[f"mem_s1_{team}"] = s1
    st.session_state[f"mem_s2_{team}"] = s2

    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT 1 FROM team_progress WHERE team = ?", (team,))
        if c.fetchone():
            c.execute("""
                UPDATE team_progress 
                SET level=?, step1_approved=?, step2_approved=?, stage_start_time=?, hint1_sent=?, hint2_sent=?
                WHERE team=?
            """, (lvl, s1, s2, st_time, h1, h2, team))
        else:
            c.execute("""
                INSERT INTO team_progress (team, level, step1_approved, step2_approved, stage_start_time, hint1_sent, hint2_sent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (team, lvl, s1, s2, st_time, h1, h2))
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_stage_elapsed_min(team):
    prog = get_team_progress(team)
    try:
        st_dt = pd.to_datetime(prog["stage_start_time"])
        diff_sec = (get_kst_now() - st_dt).total_seconds()
        return max(0, int(diff_sec // 60))
    except Exception:
        return 0

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
# 3. 문화고등학교 교시별 시간 & 수업 시작 타이머 모듈 (전 기기 동기화)
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
    kst_now = get_kst_now()
    
    # 1순위: 교사가 [🔔 수업시작] 버튼을 눌렀다면 DB에 기록된 시각 기준으로 전 기기 타이머 동기화!
    db_start_str = get_global_class_start()
    if db_start_str:
        try:
            start_dt = pd.to_datetime(db_start_str)
            diff_sec = (kst_now - start_dt).total_seconds()
            if 0 <= diff_sec <= 7200:  # 2시간 이내면 활성 수업으로 간주
                elapsed = int(diff_sec // 60)
                return "연구수업 진행중", elapsed
        except Exception:
            pass

    # 2순위: 정규 일과 시간표 자동 감지
    cur_time = kst_now.time()
    for period, start, end in SCHEDULE:
        if start <= cur_time <= end:
            start_dt = datetime.datetime.combine(kst_now.date(), start)
            elapsed = int((kst_now - start_dt).total_seconds() // 60)
            return f"{period}교시 수업중", elapsed
            
    return "수업 시작 전(대기)", 0

cur_period, elapsed_min = get_current_period_and_elapsed()

# ==========================================
# 4. 공통 팝업 모달 함수 (조별 전체 대화 크게 보기)
# ==========================================
@st.dialog("📋 모둠별 실시간 문답 전체 크게 보기", width="large")
def show_team_detail_modal(team_name):
    df_all = get_logs()
    team_data = df_all[df_all["team"] == team_name] if not df_all.empty else pd.DataFrame()
    t_prog = get_team_progress(team_name)
    st.markdown(f"### 🏷️ **{team_name} 전체 대화록** (현재 **LV.{t_prog['level']}** 단계 / 총 **{len(team_data)}회** 문답)")
    st.markdown("---")
    if team_data.empty:
        st.info(f"아직 {team_name}에서 전송된 질문이 없습니다.")
    else:
        for idx, row in team_data.iterrows():
            is_troll_log = row.get("is_troll", 0) == 1
            q_border = "#ef4444" if is_troll_log else "#2563eb"
            q_bg = "#fef2f2" if is_troll_log else "#eff6ff"
            st.markdown(f"""
            <div style="background:{q_bg}; border-left:6px solid {q_border}; padding:12px 16px; border-radius:8px; margin-bottom:8px;">
                <div style="font-size:0.9rem; color:#475569; font-weight:700;">질문 #{idx+1} [{row.get('timestamp', '')}]</div>
                <div style="font-size:1.3rem; font-weight:800; color:#0f172a; margin-top:4px;">🙋‍♂️ Q. {row.get('question', '-')}</div>
            </div>
            <div style="background:#f8fafc; border:1.5px solid #cbd5e1; border-radius:8px; padding:14px 18px; margin-bottom:20px;">
                <div style="font-size:0.95rem; color:#15803d; font-weight:800; margin-bottom:6px;">🤖 소크라테스 AI 튜터의 답변</div>
                <div style="font-size:1.15rem; color:#1e293b; line-height:1.7;">{row.get('answer', '-')}</div>
            </div>
            """, unsafe_allow_html=True)
    if st.button("✖ 창 닫기", use_container_width=True):
        st.rerun()

# ==========================================
# 5. 사이드바 및 권한 인증
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
    remain_total = max(0, 45 - elapsed_min)
    st.metric(
        label=f"⏱️ {cur_period}",
        value=f"{elapsed_min}분 경과",
        delta=f"남은 시간 {remain_total}분 (45분 기준)"
    )

# =========================================================================
# MODE A: 👨‍🏫 교사용 6분할 관제 전광판 + 조별 확대 보기 + 원격 마스터키
# =========================================================================
if user_mode == "👨‍🏫 교사용 실시간 관제" and is_teacher_authorized:
    h_col1, h_col2 = st.columns([2.6, 1.8])
    with h_col1:
        st.title("🖥️ [교단 관제 전광판] 6개 조 실시간 탐구 현황")
        st.caption("조별 [🔍 전체 대화 크게 보기] 버튼을 누르면 대화록이 크게 확대됩니다.")
    with h_col2:
        st.write("")
        auto_refresh = st.toggle("🔄 8초 자동갱신 켜기 (특정 조 발표·확대 시 끄면 편리합니다)", value=True)
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if st.button("🔔 수업시작", use_container_width=True, help="지금 시각을 0분으로 잡고 전 기기(학생·참관교사) 45분 타이머를 동시에 가동합니다."):
                now_str = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
                set_global_class_start(now_str)
                for t in ["1조", "2조", "3조", "4조", "5조", "6조", "참관교사"]:
                    update_team_progress(t, reset_timer=True)
                st.success("전 기기 타이머 동시 시작!")
                st.rerun()
        with col_b2:
            if st.button("🔄 수동갱신", use_container_width=True):
                st.rerun()
        with col_b3:
            if st.button("🧹 전체리셋", use_container_width=True, help="DB, 진행도, 수업시간, 모든 세션을 완전 초기화합니다."):
                conn = sqlite3.connect(DB_FILE, check_same_thread=False)
                c = conn.cursor()
                c.execute("DELETE FROM logs")
                c.execute("DELETE FROM sqlite_sequence WHERE name='logs'")
                c.execute("DELETE FROM team_progress")
                c.execute("DELETE FROM class_state")
                conn.commit()
                conn.close()
                for k in list(st.session_state.keys()):
                    if k.startswith("messages_") or k.startswith("chat_") or k.startswith("mem_"):
                        del st.session_state[k]
                st.success("완전 초기화 완료!")
                st.rerun()

    # 대시보드 렌더링 함수
    def draw_dashboard_content():
        kst_now = get_kst_now()
        time_display = kst_now.strftime("%H:%M:%S")
        cur_p, elap = get_current_period_and_elapsed()
        rem_min = max(0, 45 - elap)

        st.markdown(f"""
        <div class="top-timer-bar">
            <div style="font-size:1.1rem; font-weight:800; color:#e2e8f0;">
                🏫 문화고등학교 미적분Ⅰ 실시간 관제 센터
            </div>
            <div style="display:flex; align-items:center; gap:18px;">
                <div style="background:#1e3a8a; color:#93c5fd; padding:5px 14px; border-radius:8px; font-size:1.05rem; font-weight:800; border:1px solid #3b82f6;">
                    ⏳ 수업 경과: {elap}분 / 45분 (남은 시간: {rem_min}분)
                </div>
                <div style="background:#1e293b; color:#38bdf8; padding:5px 12px; border-radius:8px; font-family:monospace; font-size:1.25rem; font-weight:800; border:1px solid #334155;">
                    ⌚ {time_display}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 만약 선생님이 특정 조 확대 고정 보기를 선택했다면 화면 상단에 큼직하게 표시
        if "selected_zoom_team" in st.session_state and st.session_state["selected_zoom_team"]:
            z_team = st.session_state["selected_zoom_team"]
            df_all_z = get_logs()
            z_logs = df_all_z[df_all_z["team"] == z_team] if not df_all_z.empty else pd.DataFrame()
            st.markdown(f"""
            <div style="background:#eff6ff; border:3px solid #2563eb; border-radius:12px; padding:18px; margin-bottom:20px;">
                <h3 style="color:#1e3a8a; margin-top:0;">🔍 [{z_team} 문답 전체 확대 화면] (총 {len(z_logs)}회 대화)</h3>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"✖ [{z_team} 확대 화면 닫기]", type="primary", use_container_width=True):
                st.session_state["selected_zoom_team"] = None
                st.rerun()
            if z_logs.empty:
                st.warning(f"{z_team}은 아직 질문 내역이 없습니다.")
            else:
                for idx, row in z_logs.iterrows():
                    st.markdown(f"""
                    <div style="background:#ffffff; border-left:6px solid #2563eb; padding:14px 18px; border-radius:8px; margin-bottom:8px; box-shadow:0 2px 4px rgba(0,0,0,0.05);">
                        <div style="font-size:0.9rem; color:#64748b; font-weight:700;">질문 #{idx+1} [{row.get('timestamp', '')}]</div>
                        <div style="font-size:1.35rem; font-weight:800; color:#0f172a; margin-top:4px;">🙋‍♂️ Q. {row.get('question', '-')}</div>
                    </div>
                    <div style="background:#f8fafc; border:1.5px solid #cbd5e1; border-radius:8px; padding:16px 20px; margin-bottom:18px;">
                        <div style="font-size:0.95rem; color:#15803d; font-weight:800; margin-bottom:6px;">🤖 소크라테스 AI 피드백</div>
                        <div style="font-size:1.2rem; color:#1e293b; line-height:1.7;">{row.get('answer', '-')}</div>
                    </div>
                    """, unsafe_allow_html=True)
            st.markdown("---")

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
                <span class="tl-step-time">22~37분 (조립제법 지필증명)</span>
            </div>
            <div class="tl-step {s4_cls}">
                <b>4단계. 정리 및 심화</b>
                <span class="tl-step-time">37~45분 (참관 피드 공유 & 심화)</span>
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
            st_elap = get_stage_elapsed_min(t_name)
            
            with col:
                # 해당 조의 전체 대화 중 비수학 질문(is_troll == 1) 총 횟수 계산
                troll_cnt = int(t_logs["is_troll"].sum()) if (t_cnt > 0 and "is_troll" in t_logs.columns) else 0
                
                time_badge = f'<span class="badge-time">현단계 {st_elap}분째</span>'
                
                if t_level == 1:
                    app_txt = " (질문중)" if not t_prog["step1_approved"] else " (버튼대기)"
                    lvl_badge = f'<span style="background:#fee2e2; color:#991b1b; padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:700;">🔒 LV1{app_txt}</span>'
                elif t_level == 2:
                    app_txt = " (질문중)" if not t_prog["step2_approved"] else " (버튼대기)"
                    lvl_badge = f'<span style="background:#fef3c7; color:#92400e; padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:700;">🔓 LV2{app_txt}</span>'
                else:
                    lvl_badge = '<span style="background:#dcfce7; color:#166534; padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:700;">🏆 LV3(증명중)</span>'

                if troll_cnt > 0:
                    status_badge = f'<span class="badge-troll">🚨 비수학 {troll_cnt}건</span> <span class="badge-ok">문답 {t_cnt}회</span>'
                elif t_cnt == 0:
                    status_badge = '<span class="badge-stuck">🟡 대화 0회</span>'
                else:
                    status_badge = f'<span class="badge-ok">🟢 문답 {t_cnt}회</span>'

                st.markdown(f"""
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; padding:0 2px;">
                    <div>
                        <span style="font-size:1.3rem; font-weight:800; color:#0f172a;">{t_name}</span>
                        <span style="margin-left:5px;">{lvl_badge}</span>
                    </div>
                    <div>{status_badge}{time_badge}</div>
                </div>
                """, unsafe_allow_html=True)

                # ★ 조별 [전체 대화 크게 보기] 전용 버튼 + [강제 오픈] 버튼을 나란히 배치!
                b_col1, b_col2 = st.columns(2)
                with b_col1:
                    if st.button(f"🔍 {t_name} 크게 보기", key=f"zoom_modal_{t_name}", use_container_width=True, help="클릭 시 해당 조의 전체 문답을 큰 팝업창과 상단 확대 화면으로 봅니다."):
                        st.session_state["selected_zoom_team"] = t_name
                        show_team_detail_modal(t_name)
                with b_col2:
                    if t_level < 3:
                        next_lvl = t_level + 1
                        if st.button(f"⚡ LV{next_lvl} 강제오픈", key=f"force_{t_name}", use_container_width=True, help="하위권 조가 막혔을 때 교사 직권으로 다음 단계를 열어줍니다."):
                            update_team_progress(t_name, level=next_lvl, step1_app=1, step2_app=(1 if next_lvl==3 else 0), reset_timer=True)
                            st.rerun()
                    else:
                        st.button("🏆 최종단계 도달", key=f"done_{t_name}", disabled=True, use_container_width=True)

                card_box = st.container(height=210)
                with card_box:
                    if t_cnt == 0:
                        st.markdown("""
                        <div style="color:#94a3b8; text-align:center; padding-top:55px; font-size:0.9rem; line-height:1.6;">
                            아직 전송된 질문이 없습니다.<br>
                            도함수 증감표 작성을 위한 발문을 독려하세요.
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        for q_idx, r in t_logs.iterrows():
                            q_text = str(r.get('question', '-'))
                            a_text = str(r.get('answer', '-'))
                            if st.button(f"💬 Q{q_idx+1}. {q_text[:28]}", key=f"q_btn_{t_name}_{q_idx}", use_container_width=True):
                                st.session_state["selected_zoom_team"] = t_name
                                show_team_detail_modal(t_name)
                            st.markdown(f"""
                            <div style="background:#f8fafc; border-left:3px solid #cbd5e1; padding:6px 10px; border-radius:4px; font-size:0.84rem; color:#334155; margin-bottom:8px; line-height:1.45;">
                                <b>AI:</b> {a_text[:75]}...
                            </div>
                            """, unsafe_allow_html=True)

        t_guest_logs = df_all[df_all["team"] == "참관교사"] if not df_all.empty else pd.DataFrame()
        st.markdown("---")
        g_head1, g_head2 = st.columns([3, 1])
        with g_head1:
            st.markdown(f"### ☕ 참관 선생님들의 실시간 AI 질문 피드 <span style='font-size:0.95rem; color:#64748b; font-weight:600;'> (총 {len(t_guest_logs)}건 참여 중)</span>", unsafe_allow_html=True)
        with g_head2:
            if not t_guest_logs.empty:
                if st.button("🔍 참관교사 문답 전체 크게 보기", use_container_width=True):
                    st.session_state["selected_zoom_team"] = "참관교사"
                    show_team_detail_modal("참관교사")

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

    if auto_refresh:
        @st.fragment(run_every="8s")
        def render_auto_dashboard():
            draw_dashboard_content()
        render_auto_dashboard()
    else:
        draw_dashboard_content()
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

prog = get_team_progress(current_label)
cur_level = max(prog["level"], st.session_state.get(f"mem_lvl_{current_label}", 1))
step1_approved = (prog["step1_approved"] == 1) or (st.session_state.get(f"mem_s1_{current_label}", 0) == 1)
step2_approved = (prog["step2_approved"] == 1) or (st.session_state.get(f"mem_s2_{current_label}", 0) == 1)
stage_elapsed = get_stage_elapsed_min(current_label)
remain_class_min = max(0, 45 - elapsed_min)

# 15초마다 백그라운드 시간 체크 (교사 강제 오픈 및 마중물/선제 힌트 실시간 자동 반영)
@st.fragment(run_every="10s")
def sync_stage_timer():
    if not is_guest_mode:
        latest_p = get_team_progress(current_label)
        if (latest_p["level"] != cur_level) or (latest_p["step1_approved"] != int(step1_approved)) or (latest_p["step2_approved"] != int(step2_approved)):
            st.rerun()
sync_stage_timer()

# ★ [핵심 추가]: 학생(1~6조) 및 참관교사 화면 최상단에도 실시간 수업 경과 시간 & 단계 체류 시간 표시 바 탑재!
st.markdown(f"""
<div class="top-timer-bar">
    <div style="font-size:1.05rem; font-weight:800; color:#f8fafc;">
        📐 문화고 2학년 미적분Ⅰ 탐구 교실 &nbsp;|&nbsp; <span style="color:#38bdf8;">현재 접속: {user_mode} (LV.{cur_level} 단계)</span>
    </div>
    <div style="display:flex; align-items:center; gap:12px;">
        <div style="background:#1e3a8a; color:#bfdbfe; padding:4px 12px; border-radius:6px; font-size:0.92rem; font-weight:700;">
            ⏱️ 전체 수업 경과: <b>{elapsed_min}분 / 45분</b> (남은 시간 {remain_class_min}분)
        </div>
        <div style="background:#334155; color:#fde047; padding:4px 12px; border-radius:6px; font-size:0.92rem; font-weight:700;">
            ⏳ 현재 {cur_level}단계 탐구 시간: <b>{stage_elapsed}분 경과</b>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

if is_guest_mode:
    st.title("☕ [참관교사용] 소크라테스 AI 튜터 & 실시간 수업 참관")
    st.markdown("선생님 환영합니다! 학생들과 동일한 AI 튜터를 체험해 보시고, 아래 탭을 열어 **1~6조 학생들의 실시간 진행 현황과 문답**도 크게 확인해 보세요.")
    
    with st.expander("📊 [실시간 중계] 현재 1조 ~ 6조 학생들의 탐구 현황 및 대화 크게 보기 (클릭)", expanded=True):
        df_student_logs = get_logs()
        s_cols = st.columns(6)
        for idx, t_n in enumerate(["1조", "2조", "3조", "4조", "5조", "6조"]):
            tp = get_team_progress(t_n)
            tl = df_student_logs[df_student_logs["team"] == t_n] if not df_student_logs.empty else pd.DataFrame()
            st_min = get_stage_elapsed_min(t_n)
            last_q = tl.iloc[-1]["question"] if not tl.empty else "아직 질문 없음"
            with s_cols[idx]:
                st.markdown(f"""
                <div style="background:#f8fafc; border:1.5px solid #cbd5e1; border-radius:8px; padding:8px; text-align:center; margin-bottom:6px;">
                    <b style="font-size:1.05rem; color:#0f172a;">{t_n}</b><br>
                    <span style="font-size:0.82rem; color:#2563eb; font-weight:800;">LV.{tp['level']} 단계 ({st_min}분째)</span><br>
                    <span style="font-size:0.78rem; color:#15803d; font-weight:700;">문답 {len(tl)}회</span>
                    <hr style="margin:4px 0;">
                    <div style="font-size:0.75rem; color:#334155; text-align:left; height:36px; overflow:hidden;">최근: {last_q[:22]}..</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"🔍 {t_n} 대화보기", key=f"guest_zoom_{t_n}", use_container_width=True):
                    show_team_detail_modal(t_n)
else:
    st.title(f"🤖 [{user_mode}] 삼차함수 그래프의 비율 탐구")
    st.markdown("모둠원과 스스로 질문을 만들어 AI에게 던지고, **종이 활동지를 완성한 후 초록색 왕버튼을 눌러 잠금을 해제**하세요.")

def play_mission_sound(step_num, fallback_text):
    mp3_path = f"audio/step{step_num}.mp3"
    if os.path.exists(mp3_path):
        st.audio(mp3_path, format="audio/mp3", autoplay=True)
    else:
        st.info(f"🔊 [안내 음성] {fallback_text}")

if not is_guest_mode:
    if cur_level == 1:
        if st.button("▶ 1단계: 미션 듣기 (클릭하여 청취)", use_container_width=True):
            play_mission_sound(1, "문화고 2학년 여러분, AI에게 도함수를 질문하고 활동지 1단계를 완성해 1단계 그래프를 여세요.")
    elif cur_level == 2:
        if st.button("▶ 2단계: 탐구 팁 듣기 (클릭하여 청취)", use_container_width=True):
            play_mission_sound(2, "극댓점에서 오른쪽으로 그은 수평선이 곡선과 다시 만나는 점의 x좌표를 AI에게 캐내고 자로 거리를 재보세요.")
    else:
        if st.button("▶ 3단계: 지필 증명 안내 듣기 (클릭하여 청취)", use_container_width=True):
            play_mission_sound(3, "화면에 격자가 열렸습니다. 활동지 3단계에서 삼차방정식 인수분해로 완전 증명하세요!")

st.markdown("---")

API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=API_KEY)

session_key = f"messages_{current_label}"
if session_key not in st.session_state:
    if is_guest_mode:
        # 참관교사는 각자 스마트폰에서 깨끗한 개별 대화창으로 시작
        st.session_state[session_key] = []
    else:
        # 1~6조 학생들은 새로고침 시에도 우리 조의 DB 대화 내역을 그대로 복구
        df_prev = get_logs()
        team_prev = df_prev[df_prev["team"] == current_label] if not df_prev.empty else pd.DataFrame()
        recovered_msgs = []
        for _, r in team_prev.iterrows():
            recovered_msgs.append({"role": "user", "content": r["question"]})
            recovered_msgs.append({"role": "assistant", "content": r["answer"]})
        st.session_state[session_key] = recovered_msgs

if cur_level == 1 and not step1_approved and stage_elapsed >= 5 and prog["hint1_sent"] == 0 and not is_guest_mode:
    proactive_msg1 = (
        "🤖 **[AI 튜터의 선제 힌트 도착!]**\n\n"
        "모둠원들과 1단계 질문 만들기가 조금 어려웠나요? 제가 먼저 힌트를 드릴게요!\n"
        "삼차함수 $f(x) = x^3 - 3x$ 의 극값을 찾으려면 미분한 **도함수 $f'(x) = 0$** 을 풀어야 해요.\n\n"
        "👉 $f(x)$를 미분한 식과, 그 식이 $0$이 되는 **두 $x$좌표가 각각 얼마인지** 채팅창에 입력해 주면 바로 1단계 승인을 열어줄게요!"
    )
    st.session_state[session_key].append({"role": "assistant", "content": proactive_msg1})
    save_log(current_label, "[⏱️ 5분 경과: AI 선제 힌트 발송]", proactive_msg1, 0)
    update_team_progress(current_label, hint1=1)

if cur_level == 2 and not step2_approved and stage_elapsed >= 6 and prog["hint2_sent"] == 0 and not is_guest_mode:
    proactive_msg2 = (
        "🤖 **[AI 튜터의 선제 힌트 도착!]**\n\n"
        "2단계 교점 추적이 만만치 않죠? 핵심 단서를 드릴게요!\n"
        "극댓점 $(-1, 2)$ 에서 오른쪽으로 그은 수평선과 곡선 $y = x^3 - 3x$ 가 만나는 점을 구하려면 방정식 $x^3 - 3x - 2 = 0$ 을 세워야 해요.\n\n"
        "👉 $x = -1$ 에서 그래프가 접한다는 성질을 이용해 인수분해하면, 오른쪽에서 다시 만나는 **양수 교점의 $x$좌표**는 얼마일까요? 채팅창에 답해 보세요!"
    )
    st.session_state[session_key].append({"role": "assistant", "content": proactive_msg2})
    save_log(current_label, "[⏱️ 6분 경과: AI 선제 힌트 발송]", proactive_msg2, 0)
    update_team_progress(current_label, hint2=1)

system_instruction = f"""
너는 문화고등학교 2학년 미적분Ⅰ 연구수업의 소크라테스식 AI 튜터이자 탐구 심사관이야.
대상 함수: f(x) = x^3 - 3x, f'(x) = 3x^2 - 3.
현재 모둠 레벨: LV {cur_level} (현재 단계 체류 시간: {stage_elapsed}분 경과)

[장난 및 비수학적 질문 방어 철칙]
- 잡담, 급식, 게임, 장난, 욕설 등 수학과 무관한 질문에는 단호하게 "선생님의 실시간 관제 화면에 기록됩니다. 지금은 수학 탐구 시간입니다. 책상 위 활동지 질문으로 돌아오세요! [TROLL_DETECTED]"라고 답해.

[학생 답변 채점 및 시간별 유연성 원칙]
- 학생이 오타를 내거나("쁠마1", "x제곱", "2요"), 표현이 거칠더라도 수학적 맥락과 핵심 의미(도함수 근, 교점 x=2, 접선의 의미 등)가 올바르면 긍정적으로 수용하고 칭찬해 줘.
- 만약 현재 단계 체류 시간이 5분 이상 지났다면 학생이 어려움을 겪고 있는 것이므로, 까다롭게 되묻지 말고 친절하게 결정적 힌트를 주며 빠르게 승인 태그를 열어줘!

[소크라테스 티키타카 철칙]
1. '2:1', '1:1:1' 최종 비율 숫자를 학생보다 먼저 절대 언급하지 마.
2. [현재 LV 1 단계일 때]:
   - 학생이 극값이나 도함수를 물으면 직접 미분해서 f'(x)=0 을 풀도록 유도해. (처음부터 -1, 1을 먼저 말해주지 마!)
   - 학생이 x=-1, 1 (또는 쁠마1)을 찾아내면 칭찬하고 활동지 1단계 증감표 작성을 안내해.
   - 이때 답변 맨 마지막 줄에 정확히 다음 태그를 붙여: [APPROVE_STEP1]

3. [현재 LV 2 단계일 때]:
   - (질문 1단계) 학생이 극댓값에서 그은 선이나 교점을 물으면:
     "극댓점 (-1, 2)를 지나는 수평선의 방정식은 y=? 일까? 먼저 그 직선의 식을 모둠원과 확인해 봐!"
   - (질문 2단계) 학생이 "y=2"를 말하면:
     "맞아! 그럼 곡선과 직선이 만나는 교점을 찾으려면 어떤 삼차방정식을 세워야 하지? x=-1에서 접한다는 것은 이 방정식에서 어떤 근(힌트: 겹치는 근)을 의미할까?"
   - (질문 3단계) 학생이 "중근(또는 튕기는 근)"이나 "x^3 - 3x = 2"를 언급하면:
     "훌륭해! (x+1)^2 을 인수로 가지겠지. 그렇다면 오른쪽에서 새롭게 뚫고 지나는 다른 교점 (x > 0)의 x좌표는 얼마일까?"
   - (질문 4단계) 학생이 "x=2 (또는 2)"를 찾아내면 비로소:
     "완벽한 추론이야! 교점은 (2, 2)란다. 이제 활동지 2단계 그래프에 자를 대고 [극댓점], [변곡점], [극솟점], [교점] 사이의 수평 간격을 직접 재어보렴!"
     이때만 답변 맨 마지막 줄에 정확히 다음 태그를 붙여 승인해: [APPROVE_STEP2]

4. [현재 LV 3 단계일 때]:
   - 활동지 3단계에서 x^3-3x-2=0 조립제법 손증명을 친절히 안내하고, 완료한 조에게는 x축 교점과 극점 사이의 새로운 비율(1:루트3) 심화 탐구를 유도해.
"""

# ★ 모델 호출 이중 안전장치 (gemini-2.5-flash 기본, 오류 시 gemini-1.5-flash 자동 전환)
def get_safe_chat_session(history_list):
    for m_name in ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash"]:
        try:
            m_obj = genai.GenerativeModel(model_name=m_name, system_instruction=system_instruction)
            return m_obj.start_chat(history=history_list)
        except Exception:
            continue
    m_fallback = genai.GenerativeModel(model_name="gemini-1.5-flash")
    return m_fallback.start_chat(history=history_list)

chat_level_key = f"chat_lvl_{current_label}"
if f"chat_{current_label}" not in st.session_state or st.session_state.get(chat_level_key) != cur_level:
    gemini_history = []
    for m in st.session_state[session_key]:
        role_label = "user" if m["role"] == "user" else "model"
        gemini_history.append({"role": role_label, "parts": [m["content"]]})
    st.session_state[f"chat_{current_label}"] = get_safe_chat_session(gemini_history)
    st.session_state[chat_level_key] = cur_level

col_graph, col_chat = st.columns([1.15, 0.85], gap="medium")

# ================= 좌측: 탐구 안내 및 단계별 그래프 영역 =================
with col_graph:
    st.subheader("📈 탐구용 그래프")
    
    if cur_level == 1:
        st.markdown("""
        <div class="mission-card" style="border-left:5px solid #f97316; background:#fff7ed;">
            <b style="color:#9a3412; font-size:1.05rem;">🔒 [1단계 미션] 삼차함수 f(x) = x³ - 3x 개형 열기</b><br>
            <span style="font-size:0.9rem; color:#431407;">
                1. 모둠원들과 상의하여 우측 AI에게 <b>도함수와 극값이 생기는 위치</b>를 질문하세요.<br>
                2. 단서를 얻어 <b>책상 위 [종이 활동지 1단계 증감표]</b>를 연필로 채우세요.
            </span>
        </div>
        """, unsafe_allow_html=True)
        
        if step1_approved or is_guest_mode:
            st.markdown('<div class="unlock-alert-box">🎉 1단계 AI 탐구 인증 완료! 종이 활동지를 채웠다면 아래 초록색 왕버튼을 누르세요! 👇</div>', unsafe_allow_html=True)
            if st.button("🔓 [활동지 1단계 작성 완료] ➔ 2단계 그래프 열기 (클릭!)", key="unlock_btn_left_1", type="primary", use_container_width=True):
                st.session_state[f"step1_msg_cnt_{current_label}"] = sum(1 for m in st.session_state[session_key] if m["role"] == "user")
                update_team_progress(current_label, level=2, step1_app=1, reset_timer=True)
                st.balloons()
                st.rerun()
        else:
            st.info("💬 AI와의 문답을 통해 도함수와 극값의 위치를 검증받으면 여기에 초록색 잠금 해제 버튼이 열립니다.")

    elif cur_level == 2:
        st.markdown("""
        <div class="mission-card" style="border-left:5px solid #2563eb; background:#eff6ff;">
            <b style="color:#1e40af; font-size:1.05rem;">🔓 [2단계 미션] 극댓점에서의 수평선과 새로운 교점 추적</b><br>
            <span style="font-size:0.9rem; color:#1e293b;">
                1. AI와 대화하며 극댓점을 지나는 수평선의 방정식, 곡선과 접할 때 방정식의 근이 갖는 특징, 그리고 오른쪽에서 다시 만나는 교점의 좌표를 차례대로 밝혀내세요.<br>
                2. <b>[종이 활동지 2단계]</b> 그래프에 직접 자를 대고 점들 사이의 수평 간격을 측정해 기록하세요.
            </span>
        </div>
        """, unsafe_allow_html=True)
        
        if step2_approved or is_guest_mode:
            st.markdown('<div class="unlock-alert-box">🎉 2단계 AI 심층 검증 완료! 자로 간격을 확인했다면 아래 초록색 왕버튼을 누르세요! 👇</div>', unsafe_allow_html=True)
            if st.button("🔓 [활동지 2단계 작도 완료] ➔ 3단계 비율 격자 열기 (클릭!)", key="unlock_btn_left_2", type="primary", use_container_width=True):
                update_team_progress(current_label, level=3, step2_app=1, reset_timer=True)
                st.balloons()
                st.rerun()
        else:
            st.info("💬 AI의 단계별 질문(수평선 식 ➔ 접할 때 근의 특징 ➔ 교점의 x좌표)에 답하여 승인을 획득하세요.")

    else:
        st.markdown("""
        <div class="mission-card" style="border-left:5px solid #16a34a; background:#f0fdf4;">
            <b style="color:#166534; font-size:1.05rem;">🏆 [3단계 완성] 삼차함수 1:1:1 비율 격자 완성!</b><br>
            <span style="font-size:0.92rem; color:#14532d;">
                1. ✍️ <b>[종이 활동지 뒷면 3단계]</b>에서 방정식 <b>x³ - 3x - 2 = 0</b> 을 조립제법으로 인수분해하여 손증명을 완성하세요.<br>
                2. 📢 <b>[최종 보고]:</b> 증명을 마친 모둠은 <b>오늘 발견한 삼차함수 비율 법칙을 한 줄로 요약하여 우측 AI에게 최종 보고</b>하세요! (선생님 전광판에 실시간 게시됩니다)<br>
                3. 🌟 <b>[심화 퀘스트]:</b> 우측 마중물 버튼을 눌러 삼차함수에 숨겨진 <b>또 다른 새로운 비율</b>에도 도전해 보세요!
            </span>
        </div>
        """, unsafe_allow_html=True)

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
        ax1.set_title(r"$y = f(x) = x^3 - 3x$", fontsize=13, color="#1e40af", fontweight="bold")
        ax2.set_title(r"$y = f'(x)$", fontsize=13, color="#475569")
        ax1.plot([0], [0], marker='o', markersize=6, color='black')
        ax2.plot([0], [0], marker='o', markersize=6, color='black')

    elif cur_level == 2:
        ax1.set_title(r"$y = f(x) = x^3 - 3x$", fontsize=13, color="#1e40af", fontweight="bold")
        ax1.plot(x, y, color="#1f77b4", linewidth=2.5, label=r"$f(x)$")
        ax1.plot([-1], [2], marker='o', markersize=8, color='red', label=r"$(-1, 2)$")
        ax1.plot([1], [-2], marker='o', markersize=8, color='blue', label=r"$(1, -2)$")
        ax1.legend(loc='upper left', fontsize=10)

        ax2.set_title(r"$y = f'(x) = 3x^2 - 3$", fontsize=13, color="#c2410c", fontweight="bold")
        ax2.plot(x, dy, color="#ff7f0e", linewidth=2.2, label=r"$f'(x)$")
        ax2.axvline(0, color='purple', alpha=0.5, linestyle=':', label=r"$x = 0$")
        ax2.legend(loc='upper center', fontsize=10)

    else:
        # ★ 영문 'Ratio' 완전 제거! 순수 수학 수식 [1 : 1 : 1] 로만 표기!
        ax1.set_title(r"$y = f(x) = x^3 - 3x \quad [1 : 1 : 1]$", fontsize=13, color="#15803d", fontweight="bold")
        ax1.plot(x, y, color="#1f77b4", linewidth=2.5, label=r"$f(x)$")
        ax1.axhline(2, color='red', alpha=0.5, linestyle=':', label=r"$y = 2$")
        ax1.axhline(-2, color='blue', alpha=0.5, linestyle=':', label=r"$y = -2$")
        ax1.plot([-1, 2], [2, 2], marker='o', markersize=7, color='red')
        ax1.plot([-2, 1], [-2, -2], marker='o', markersize=7, color='blue')
        ax1.legend(loc='upper left', fontsize=10)

        ax2.set_title(r"$y = f'(x) = 3x^2 - 3$", fontsize=13, color="#c2410c", fontweight="bold")
        ax2.plot(x, dy, color="#ff7f0e", linewidth=2.2, label=r"$f'(x)$")
        ax2.axvline(0, color='purple', alpha=0.6, linestyle=':', label=r"$x = 0$")
        ax2.legend(loc='upper center', fontsize=10)

        for ax in [ax1, ax2]:
            for px in [-2, -1, 0, 1, 2]:
                ax.axvline(px, color='gray', alpha=0.45, linestyle='--', linewidth=1.3)

    st.pyplot(fig)
    if cur_level == 3:
        st.info("💡 **관찰 포인트:** $x = -2, -1, 0, 1, 2$ 수직 점선들의 간격이 정확히 **1 : 1 : 1** 로 일정함을 확인하세요!")

# ================= 우측: 소크라테스 AI 대화창 영역 =================
with col_chat:
    st.subheader(f"💬 소크라테스 AI ({current_label} - LV.{cur_level})")
    
    chat_box = st.container(height=420)
    with chat_box:
        for m in st.session_state[session_key]:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

    if cur_level == 1 and (step1_approved or is_guest_mode):
        st.markdown('<div class="unlock-alert-box">✅ 1단계 탐구 통과! 종이 활동지 1단계를 다 적었으면 아래 초록색 버튼을 누르세요! 👇</div>', unsafe_allow_html=True)
        if st.button("🔓 [활동지 1단계 작성 완료] ➔ 2단계 그래프 열기!", key="unlock_btn_right_1", type="primary", use_container_width=True):
            st.session_state[f"step1_msg_cnt_{current_label}"] = sum(1 for m in st.session_state[session_key] if m["role"] == "user")
            update_team_progress(current_label, level=2, step1_app=1, reset_timer=True)
            st.balloons()
            st.rerun()

    elif cur_level == 2 and (step2_approved or is_guest_mode):
        st.markdown('<div class="unlock-alert-box">✅ 2단계 탐구 통과! 종이 활동지 2단계에 자로 간격을 쟀으면 아래 초록색 버튼을 누르세요! 👇</div>', unsafe_allow_html=True)
        if st.button("🔓 [활동지 2단계 작도 완료] ➔ 3단계 비율 격자 열기!", key="unlock_btn_right_2", type="primary", use_container_width=True):
            update_team_progress(current_label, level=3, step2_app=1, reset_timer=True)
            st.balloons()
            st.rerun()

    preset_q = None
    show_primer = (stage_elapsed >= 3) or (cur_level == 3) or is_guest_mode
    
    if not show_primer:
        remain_primer = max(1, 3 - stage_elapsed)
        st.markdown(f"""
        <div class="primer-box">
            <span style="font-size:0.88rem; color:#475569; font-weight:600;">
                🤔 <b>스스로 질문 만들기 시간!</b> 모둠원들과 상의하여 아래 입력창에 직접 수학적 질문을 적어보세요.<br>
                <span style="font-size:0.8rem; color:#64748b;">(질문 작성이 막막한 모둠을 위한 <b>'마중물 질문 찬스'</b>는 <b>{remain_primer}분 뒤</b>에 열립니다.)</span>
            </span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="primer-box" style="background:#f0f9ff; border-color:#7dd3fc;">
            <span style="font-size:0.85rem; color:#0369a1;">
                🛟 <b>[마중물 질문 찬스 오픈!]</b> <b>'마중물 질문'</b>이란 어떻게 질문을 시작해야 할지 막막할 때 대화의 물꼬를 터주는 <b>예시 질문 버튼</b>입니다. 직접 질문하기 어렵다면 아래 버튼을 눌러 대화를 시작해 보세요!
            </span>
        </div>
        """, unsafe_allow_html=True)
        qc1, qc2 = st.columns(2)
        if cur_level == 1:
            with qc1:
                if st.button("📍 극값을 구하려면 무엇부터 해야 해?", use_container_width=True):
                    preset_q = "삼차함수 f(x)=x^3-3x의 극댓값과 극솟값을 구하려면 가장 먼저 무엇을 해야 해?"
            with qc2:
                if st.button("⚖️ 도함수가 0이 되는 점은 어떤 의미야?", use_container_width=True):
                    preset_q = "f(x)를 미분한 도함수 f'(x)=0 이 되는 x좌표를 찾으면 그래프에서 어떤 점을 알 수 있어?"
        elif cur_level == 2:
            with qc1:
                if st.button("📏 극댓점에서 오른쪽으로 수평선을 그으면?", use_container_width=True):
                    preset_q = "극댓점에서 오른쪽으로 수평선을 그었을 때 그 직선의 방정식은 어떻게 구해?"
            with qc2:
                if st.button("🔍 수평선과 다시 만나는 교점은 어떻게 구해?", use_container_width=True):
                    preset_q = "극댓점을 지나는 수평선이 삼차함수 곡선과 오른쪽에서 다시 만나는 교점의 x좌표는 어떻게 구할 수 있어?"
        else:
            with qc1:
                if st.button("📝 조립제법 인수분해 증명 힌트!", use_container_width=True):
                    preset_q = "활동지 3단계에서 삼차방정식을 어떻게 인수분해하면 접점과 교점의 위치가 대수적으로 증명돼?"
            with qc2:
                if st.button("🌟 [심화] 또 다른 비율 관계도 있어?", use_container_width=True):
                    preset_q = "방금 찾은 비율 말고, 삼차함수가 x축과 만나는 교점과 극점 사이에 성립하는 또 다른 비율 관계도 알려줘!"
                
    input_placeholder = "참관 선생님의 질문을 입력해 보세요!" if is_guest_mode else f"[{cur_level}단계] 모둠원들과 만든 질문이나 계산한 답을 입력하세요"
    user_q = st.chat_input(input_placeholder)
    final_q = preset_q if preset_q else user_q
    
    if final_q:
        is_troll = 1 if check_is_troll(final_q) else 0
        
        st.session_state[session_key].append({"role": "user", "content": final_q})
        with chat_box:
            with st.chat_message("user"):
                st.markdown(final_q)
            with st.chat_message("assistant"):
                with st.spinner("AI가 모둠의 질문을 분석 중입니다..."):
                    try:
                        if cur_level == 1:
                            remind_rule = (
                                " (철칙: 학생이 미분식 3x^2-3만 말한 상태라면 절대 승인하지 말고, 3x^2-3=0이 되는 두 x좌표가 얼마인지 되물어라! "
                                "오직 학생이 직접 '-1'과 '1'(또는 쁠마1, 마일과 일)을 입으로 말했을 때만 답변 맨 끝에 [APPROVE_STEP1] 을 출력할 것!)"
                            )
                        elif cur_level == 2:
                            remind_rule = (
                                " (철칙: 수평선 y=2나 중근만 말한 상태라면 절대 승인하지 말고, 오른쪽에서 다시 만나는 교점(x>0)의 x좌표가 얼마인지 끝까지 되물어라! "
                                "오직 학생이 직접 교점 'x=2' 또는 '(2, 2)'를 찾아서 말했을 때만 답변 맨 끝에 [APPROVE_STEP2] 를 출력할 것!)"
                            )
                        else:
                            remind_rule = ""

                        res = st.session_state[f"chat_{current_label}"].send_message(
                            f"[현재 LV{cur_level} 단계 ({stage_elapsed}분 경과) / {current_label} 발화]: {final_q}{remind_rule}"
                        )
                        raw_reply = res.text
                    except Exception as e:
                        try:
                            st.session_state[f"chat_{current_label}"] = get_safe_chat_session([])
                            res = st.session_state[f"chat_{current_label}"].send_message(final_q)
                            raw_reply = res.text
                        except Exception as e2:
                            raw_reply = f"일시적 연결 지연입니다. 다시 한 번 전송해 주세요: {e2}"
                    
                    # ★ [무결점 승인 검문소]: 횟수 자동 오픈 완전 삭제! 학생이 실제로 정답을 언급했는지 파이썬이 직접 검증!
                    new_approval = False
                    all_user_msgs = " ".join([m["content"] for m in st.session_state[session_key] if m["role"] == "user"]).replace(" ", "")
                    user_text_clean = final_q.replace(" ", "")
                    
                    if cur_level == 1 and not step1_approved:
                        # 학생의 누적 발화 안에 반드시 -1과 1(또는 쁠마1, 마일)이 실제로 존재해야만 승인! (3x^2-3만 백 번 쳐도 절대 안 열림)
                         check_s1 = all_user_msgs.replace("-1", "")
                        has_both_roots = ("-1" in all_user_msgs and "1" in check_s1) or ("쁠마1" in all_user_msgs) or ("+-1" in all_user_msgs) or ("±1" in all_user_msgs) or ("마일" in all_user_msgs)
                        if has_both_roots and not is_troll:
                            update_team_progress(current_label, step1_app=1)
                            new_approval = True
                            
                    elif cur_level == 2 and not step2_approved:
                        # 2단계 진입 후 나눈 대화 횟수 계산
                        user_turn_cnt = sum(1 for m in st.session_state[session_key] if m["role"] == "user")
                        step1_cnt = st.session_state.get(f"step1_msg_cnt_{current_label}", 1)
                        step2_turn_cnt = max(1, user_turn_cnt - step1_cnt)
                        
                        # 수평선 'y=2'나 제곱 'x^2', 극댓점 '(-1,2)'의 숫자 2를 모두 제거한 뒤에도 진짜 교점 '2'를 말했는지 검사!
                        cleaned_q = user_text_clean.replace("y=2", "").replace("x^2", "").replace("(-1,2)", "").replace("-2", "").replace("2단계", "")
                        said_x2 = ("x=2" in user_text_clean) or ("(2,2)" in user_text_clean) or ("2" in cleaned_q and step2_turn_cnt >= 2)
                        
                        # AI가 승인 태그를 줬더라도 학생이 '2' 관련 답을 안 했으면 절대 안 열어줌!
                        if (said_x2 or ("[APPROVE_STEP2]" in raw_reply and "2" in cleaned_q)) and not is_troll:
                            update_team_progress(current_label, step2_app=1)
                            new_approval = True
                    
                    # 금지어에 없었더라도 AI가 비수학 질문으로 판정했으면 즉시 경고(is_troll=1) 활성화!
                    if ("[TROLL_DETECTED]" in raw_reply) or ("관제 화면에 기록됩니다" in raw_reply):
                        is_troll = 1
                        
                    bot_reply = raw_reply.replace("[APPROVE_STEP1]", "").replace("[APPROVE_STEP2]", "").replace("[TROLL_DETECTED]", "").strip()
                    st.markdown(bot_reply)
                    st.session_state[session_key].append({"role": "assistant", "content": bot_reply})
                    save_log(current_label, final_q, bot_reply, is_troll)
                    
                    if new_approval:
                        st.rerun()