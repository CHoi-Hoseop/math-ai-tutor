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
    
    .primer-box {
        background: #f8fafc; border: 1.5px dashed #94a3b8; border-radius: 8px;
        padding: 10px 14px; margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 로컬 SQLite 경량 공유 DB 모듈 (단계별 체류시간 & 힌트 상태 추적)
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
    # 기존 테이블에 신규 컬럼이 없을 경우 자동 추가 (마이그레이션 안전장치)
    for col_def in [
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
            "level": row[0],
            "step1_approved": row[1],
            "step2_approved": row[2],
            "stage_start_time": row[3] if row[3] else now_str,
            "hint1_sent": row[4] if row[4] is not None else 0,
            "hint2_sent": row[5] if row[5] is not None else 0
        }
    except Exception:
        return {
            "level": 1, "step1_approved": 0, "step2_approved": 0,
            "stage_start_time": now_str, "hint1_sent": 0, "hint2_sent": 0
        }

def update_team_progress(team, level=None, step1_app=None, step2_app=None, reset_timer=False, hint1=None, hint2=None):
    try:
        cur = get_team_progress(team)
        lvl = level if level is not None else cur["level"]
        s1 = step1_app if step1_app is not None else cur["step1_approved"]
        s2 = step2_app if step2_app is not None else cur["step2_approved"]
        st_time = get_kst_now().strftime("%Y-%m-%d %H:%M:%S") if reset_timer else cur["stage_start_time"]
        h1 = hint1 if hint1 is not None else cur["hint1_sent"]
        h2 = hint2 if hint2 is not None else cur["hint2_sent"]
        
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("""
            INSERT INTO team_progress (team, level, step1_approved, step2_approved, stage_start_time, hint1_sent, hint2_sent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team) DO UPDATE SET 
                level=?, step1_approved=?, step2_approved=?, stage_start_time=?, hint1_sent=?, hint2_sent=?
        """, (team, lvl, s1, s2, st_time, h1, h2, lvl, s1, s2, st_time, h1, h2))
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
    kst_now = get_kst_now()
    cur_time = kst_now.time()
    
    for period, start, end in SCHEDULE:
        if start <= cur_time <= end:
            start_dt = datetime.datetime.combine(kst_now.date(), start)
            elapsed = int((kst_now - start_dt).total_seconds() // 60)
            return f"{period}교시", elapsed
            
    if "class_start_time" in st.session_state:
        diff_sec = (kst_now - st.session_state["class_start_time"]).total_seconds()
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
# MODE A: 👨‍🏫 교사용 6분할 관제 전광판 + 원격 잠금해제 마스터키 + 참관교사 피드
# =========================================================================
if user_mode == "👨‍🏫 교사용 실시간 관제" and is_teacher_authorized:
    h_col1, h_col2 = st.columns([3.2, 1.3])
    with h_col1:
        st.title("🖥️ [교단 관제 전광판] 6개 조 실시간 탐구 현황")
        st.caption("모둠별 대화 내역 확인 및 [⚡ 강제 다음단계] 마스터키로 수업 진도를 조율하세요.")
    with h_col2:
        st.write("")
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if st.button("🔔 수업시작", use_container_width=True, help="지금 시각을 0분으로 잡고 45분 타이머 및 전 모둠 단계 타이머를 가동합니다."):
                now_dt = get_kst_now()
                st.session_state["class_start_time"] = now_dt
                for t in ["1조", "2조", "3조", "4조", "5조", "6조", "참관교사"]:
                    update_team_progress(t, reset_timer=True)
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
                for k in list(st.session_state.keys()):
                    if k.startswith("messages_") or k.startswith("chat_"):
                        del st.session_state[k]
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
                    <div style="font-size:0.85rem; color:#64748b; font-weight:700;">#{row.get('id', idx+1)} 발화 [{row.get('timestamp', '')}]</div>
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
        kst_now = get_kst_now()
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
            st_elap = get_stage_elapsed_min(t_name)
            
            with col:
                has_troll = False
                if t_cnt > 0:
                    last_row = t_logs.iloc[-1]
                    has_troll = (last_row.get("is_troll", 0) == 1)
                
                time_badge = f'<span class="badge-time">{st_elap}분째 체류</span>'
                
                if t_level == 1:
                    app_txt = " (질문중)" if not t_prog["step1_approved"] else " (활동지확인중)"
                    lvl_badge = f'<span style="background:#fee2e2; color:#991b1b; padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:700;">🔒 LV1{app_txt}</span>'
                elif t_level == 2:
                    app_txt = " (질문중)" if not t_prog["step2_approved"] else " (작도확인중)"
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
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; padding:0 2px;">
                    <div>
                        <span style="font-size:1.3rem; font-weight:800; color:#0f172a;">{t_name}</span>
                        <span style="margin-left:6px;">{lvl_badge}</span>
                    </div>
                    <div>{status_badge}{time_badge}</div>
                </div>
                """, unsafe_allow_html=True)

                # 👨‍🏫 교사용 원격 잠금해제 마스터키 버튼
                if t_level < 3:
                    next_lvl = t_level + 1
                    if st.button(f"⚡ {t_name} ➔ LV{next_lvl} 강제 오픈 (교사 직권)", key=f"force_{t_name}", use_container_width=True):
                        update_team_progress(t_name, level=next_lvl, step1_app=1, step2_app=(1 if next_lvl==3 else 0), reset_timer=True)
                        st.rerun()

                card_box = st.container(height=210)
                with card_box:
                    if t_cnt == 0:
                        st.markdown("""
                        <div style="color:#94a3b8; text-align:center; padding-top:60px; font-size:0.92rem; line-height:1.6;">
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

# 진행 상태 및 현재 단계 체류 시간(분) 로드
prog = get_team_progress(current_label)
cur_level = prog["level"]
step1_approved = prog["step1_approved"] == 1
step2_approved = prog["step2_approved"] == 1
stage_elapsed = get_stage_elapsed_min(current_label)

# 학생 화면에서도 시간 경과에 따른 마중물/자동 힌트가 저절로 열리도록 15초마다 백그라운드 시간 동기화
@st.fragment(run_every="15s")
def sync_stage_timer():
    pass
sync_stage_timer()

if is_guest_mode:
    st.title("☕ [참관교사용] 소크라테스 AI 튜터 & 실시간 수업 참관")
    st.markdown("선생님 환영합니다! 학생들과 동일한 AI 튜터를 체험해 보시고, 아래 탭을 열어 **1~6조 학생들의 실시간 진행 현황**도 확인해 보세요.")
    
    with st.expander("📊 [실시간 중계] 현재 1조 ~ 6조 학생들의 탐구 현황 보기 (클릭)", expanded=False):
        df_student_logs = get_logs()
        s_cols = st.columns(6)
        for idx, t_n in enumerate(["1조", "2조", "3조", "4조", "5조", "6조"]):
            tp = get_team_progress(t_n)
            tl = df_student_logs[df_student_logs["team"] == t_n] if not df_student_logs.empty else pd.DataFrame()
            last_q = tl.iloc[-1]["question"] if not tl.empty else "아직 질문 없음"
            with s_cols[idx]:
                st.markdown(f"""
                <div style="background:#f8fafc; border:1px solid #cbd5e1; border-radius:8px; padding:8px; text-align:center;">
                    <b style="font-size:1.05rem;">{t_n}</b><br>
                    <span style="font-size:0.8rem; color:#2563eb; font-weight:700;">LV {tp['level']} 단계</span><br>
                    <span style="font-size:0.75rem; color:#64748b;">문답 {len(tl)}회</span>
                    <hr style="margin:4px 0;">
                    <div style="font-size:0.75rem; color:#334155; text-align:left;">최근Q: {last_q[:22]}..</div>
                </div>
                """, unsafe_allow_html=True)
else:
    st.title(f"🤖 [{user_mode}] 삼차함수 그래프의 비율 탐구")
    st.markdown("모둠원과 스스로 질문을 만들어 AI에게 던지고, **종이 활동지를 완성한 후 잠금을 해제**하세요.")

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

st.markdown("---")

API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=API_KEY)

# 세션 대화 복구
session_key = f"messages_{current_label}"
if session_key not in st.session_state:
    df_prev = get_logs()
    team_prev = df_prev[df_prev["team"] == current_label] if not df_prev.empty else pd.DataFrame()
    recovered_msgs = []
    for _, r in team_prev.iterrows():
        recovered_msgs.append({"role": "user", "content": r["question"]})
        recovered_msgs.append({"role": "assistant", "content": r["answer"]})
    st.session_state[session_key] = recovered_msgs

# ★ [시간 경과에 따른 AI 튜터의 '선제적 힌트 톡' 자동 발송 시스템]
if cur_level == 1 and not step1_approved and stage_elapsed >= 5 and prog["hint1_sent"] == 0 and not is_guest_mode:
    proactive_msg1 = (
        "🤖 **[AI 튜터의 선제 힌트 도착!]**\n\n"
        "모둠원들과 1단계 질문 만들기가 조금 어려웠나요? 제가 먼저 힌트를 드릴게요!\n"
        "삼차함수 $f(x) = x^3 - 3x$ 의 극값을 찾으려면 미분한 **도함수 $f'(x) = 3x^2 - 3 = 0$** 을 풀어야 해요.\n\n"
        "👉 이 방정식을 만족하는 **두 $x$좌표가 각각 얼마인지** 채팅창에 입력해 주면 바로 1단계 승인을 열어줄게요!"
    )
    st.session_state[session_key].append({"role": "assistant", "content": proactive_msg1})
    save_log(current_label, "[⏱️ 5분 경과: AI 선제 힌트 발송]", proactive_msg1, 0)
    update_team_progress(current_label, hint1=1)

if cur_level == 2 and not step2_approved and stage_elapsed >= 6 and prog["hint2_sent"] == 0 and not is_guest_mode:
    proactive_msg2 = (
        "🤖 **[AI 튜터의 선제 힌트 도착!]**\n\n"
        "2단계 교점 추적이 만만치 않죠? 핵심 단서를 드릴게요!\n"
        "극댓점 $(-1, 2)$ 에서 오른쪽으로 그은 수평선은 **$y = 2$** 입니다. "
        "곡선과 만나는 점을 구하려고 $x^3 - 3x = 2$ 를 정리하면 **$(x+1)^2(x-2) = 0$** 으로 인수분해된답니다!\n\n"
        "👉 그렇다면 $x = -1$ 말고 오른쪽에서 다시 만나는 **양수 교점의 $x$좌표**는 얼마일까요? 채팅창에 답해 보세요!"
    )
    st.session_state[session_key].append({"role": "assistant", "content": proactive_msg2})
    save_log(current_label, "[⏱️ 6분 경과: AI 선제 힌트 발송]", proactive_msg2, 0)
    update_team_progress(current_label, hint2=1)

# 시스템 프롬프트 (체류 시간에 따라 힌트 강도를 유연하게 조절하도록 지시)
system_instruction = f"""
너는 문화고등학교 2학년 미적분Ⅰ 연구수업의 소크라테스식 AI 튜터이자 탐구 심사관이야.
대상 함수: f(x) = x^3 - 3x, f'(x) = 3x^2 - 3.
현재 모둠 레벨: LV {cur_level} (현재 단계 체류 시간: {stage_elapsed}분 경과)

[장난 및 비수학적 질문 방어 철칙]
- 잡담, 게임, 장난, 욕설 질문에는 단호하게 "선생님의 실시간 관제 화면에 기록됩니다. 지금은 수학 탐구 시간입니다. 책상 위 활동지 질문으로 돌아오세요!"라고만 답해.

[학생 답변 채점 및 시간별 유연성 원칙]
- 학생이 오타를 내거나("쁠마1", "x제곱", "2요"), 표현이 거칠더라도 수학적 맥락과 핵심 의미(도함수 근, 교점 x=2, 접선의 의미 등)가 올바르면 긍정적으로 수용하고 칭찬해 줘.
- 만약 현재 단계 체류 시간이 5분 이상 지났다면 학생이 어려움을 겪고 있는 것이므로, 까다롭게 되묻지 말고 친절하게 결정적 힌트를 주며 빠르게 승인 태그를 열어줘!

[소크라테스 티키타카 철칙]
1. '2:1', '1:1:1' 최종 비율 숫자를 학생보다 먼저 절대 언급하지 마.
2. [현재 LV 1 단계일 때]:
   - 학생이 극값이나 도함수를 물으면 f'(x)=3x^2-3=0 을 풀도록 유도해.
   - 학생이 x=-1, 1 (또는 쁠마1) 및 극댓점(-1, 2), 극솟점(1, -2)의 맥락을 언급하면 칭찬하고 활동지 1단계 증감표 작성을 안내해.
   - 이때 답변 맨 마지막 줄에 정확히 다음 태그를 붙여: [APPROVE_STEP1]

3. [현재 LV 2 단계일 때]:
   - (질문 1단계) 학생이 극댓값에서 그은 선이나 교점을 물으면:
     "극댓점 (-1, 2)를 지나는 수평선의 방정식은 y=? 일까? 먼저 그 직선의 식을 모둠원과 확인해 봐!"
   - (질문 2단계) 학생이 "y=2"를 말하면:
     "맞아! 그럼 곡선과 직선이 만나는 교점을 찾으려면 어떤 삼차방정식을 세워야 하지? x=-1에서 접한다는 것은 이 방정식에서 어떤 근(힌트: 겹치는 근)을 의미할까?"
   - (질문 3단계) 학생이 "중근(또는 튕기는 근)"이나 "x^3 - 3x = 2"를 언급하면:
     "훌륭해! (x+1)^2 을 인수로 가지겠지. 그렇다면 오른쪽에서 새롭게 뚫고 지나는 다른 교점 (x > 0)의 x좌표는 얼마일까?"
   - (질문 4단계) 학생이 "x=2 (또는 2)"를 찾아내면 비로소:
     "완벽한 추론이야! 교점은 (2, 2)란다. 이제 활동지 2단계 그래프에 자를 대고 [극댓점 x=-1], [변곡점 x=0], [극솟점 x=1], [교점 x=2] 사이의 수평 간격을 직접 재어보렴!"
     이때만 답변 맨 마지막 줄에 정확히 다음 태그를 붙여 승인해: [APPROVE_STEP2]

4. [현재 LV 3 단계일 때]:
   - 활동지 3단계 x^3-3x-2=(x+1)^2(x-2)=0 조립제법 손증명을 친절히 안내하고, 완료한 조에게는 x축 교점(+-루트3)과 극점 사이의 1:루트3 비율 심화 탐구를 유도해.
"""

model = genai.GenerativeModel(model_name="gemini-3.8-flash", system_instruction=system_instruction)

# 레벨 변경 감지 시 AI 세션 최신 프롬프트로 동기화
chat_level_key = f"chat_lvl_{current_label}"
if f"chat_{current_label}" not in st.session_state or st.session_state.get(chat_level_key) != cur_level:
    gemini_history = []
    for m in st.session_state[session_key]:
        role_label = "user" if m["role"] == "user" else "model"
        gemini_history.append({"role": role_label, "parts": [m["content"]]})
    st.session_state[f"chat_{current_label}"] = model.start_chat(history=gemini_history)
    st.session_state[chat_level_key] = cur_level

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
                1. 모둠원들과 상의하여 우측 AI에게 <b>도함수와 극값의 위치</b>를 직접 질문하세요.<br>
                2. 힌트를 얻어 <b>책상 위 [종이 활동지 1단계 증감표]</b>를 연필로 채우세요.
            </span>
        </div>
        """, unsafe_allow_html=True)
        
        if step1_approved or is_guest_mode:
            st.success("✅ AI 승인 완료! 종이 활동지 1단계를 다 채웠다면 아래 버튼을 눌러 그래프를 여세요.")
            if st.button("🔓 [활동지 1단계 작성 완료] ➔ 2단계 그래프 열기", use_container_width=True):
                update_team_progress(current_label, level=2, reset_timer=True)
                st.balloons()
                st.rerun()
        else:
            st.info("💬 AI와의 문답을 통해 도함수 계산($x=-1, 1$)을 검증받으면 여기에 해제 버튼이 열립니다.")

    # ── [레벨 2 안내 및 활동지 완료 버튼] ──
    elif cur_level == 2:
        st.markdown("""
        <div class="mission-card" style="border-left:5px solid #2563eb; background:#eff6ff;">
            <b style="color:#1e40af; font-size:1.05rem;">🔓 [2단계 미션] 극댓점 수평선 $y=2$ 와 교점 추적</b><br>
            <span style="font-size:0.9rem; color:#1e293b;">
                1. AI와 대화하며 극댓점 $(-1, 2)$의 수평선 식, 중근의 의미, 다른 교점($x>0$)을 차례대로 밝혀내세요.<br>
                2. <b>[종이 활동지 2단계]</b> 그래프에 직접 자를 대고 간격을 측정해 비율을 기록하세요.
            </span>
        </div>
        """, unsafe_allow_html=True)
        
        if step2_approved or is_guest_mode:
            st.success("✅ AI 심층 검증 완료! 활동지에 자를 대고 간격을 확인했다면 황금비율 격자를 여세요.")
            if st.button("🔓 [활동지 2단계 작도 완료] ➔ 1:1:1 황금비율 격자 열기", use_container_width=True):
                update_team_progress(current_label, level=3, reset_timer=True)
                st.balloons()
                st.rerun()
        else:
            st.info("💬 AI의 단계별 질문(수평선 식 ➔ 중근 ➔ 교점 x좌표)에 답하여 승인을 획득하세요.")

    # ── [레벨 3 지필 증명 안내] ──
    else:
        st.markdown("""
        <div class="mission-card" style="border-left:5px solid #16a34a; background:#f0fdf4;">
            <b style="color:#166534; font-size:1.05rem;">🏆 [3단계 완성] 1:1:1 황금비율 격자 완성!</b><br>
            <span style="font-size:0.92rem; color:#14532d;">
                눈으로 확인한 $1:1:1$ 비율이 우연이 아님을 증명할 시간입니다!<br>
                ✍️ <b>[종이 활동지 뒷면 3단계]</b>에서 $x^3 - 3x - 2 = (x+1)^2(x-2) = 0$ 조립제법으로 손증명하세요.<br>
                🌟 <b>[심화 퀘스트]:</b> 증명을 마친 모둠은 AI에게 $1:\sqrt{3}$ 비율에 대해 질문해 보세요!
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
    st.subheader(f"💬 소크라테스 AI ({current_label} - LV.{cur_level})")
    
    chat_box = st.container(height=430)
    with chat_box:
        for m in st.session_state[session_key]:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
                
    # ★ [시간차 마중물(질문 스타터) 오픈 시스템 & 마중물 설명 가이드]
    preset_q = None
    # 단계 시작 후 3분이 지났거나, 3단계(심화)이거나, 참관교사 모드일 때만 마중물 노출!
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
                if st.button("📍 도함수 f'(x)는 어떻게 돼?", use_container_width=True):
                    preset_q = "삼차함수 f(x)=x^3-3x를 미분한 도함수 식과 극값 구하는 법을 알려줘."
            with qc2:
                if st.button("⚖️ 미분하면 3x²-3=0 맞지?", use_container_width=True):
                    preset_q = "미분하면 3x^2-3=0 이니까 x=-1이랑 x=1에서 극값을 가지는 거 맞아?"
        elif cur_level == 2:
            with qc1:
                if st.button("📏 극댓점(-1, 2)에서 그은 가로선은?", use_container_width=True):
                    preset_q = "극댓점 (-1, 2)에서 오른쪽으로 수평선을 그으면 직선의 방정식이 뭐가 돼?"
            with qc2:
                if st.button("🔍 y=2랑 다시 만나는 점은 어떻게 구해?", use_container_width=True):
                    preset_q = "직선 y=2랑 삼차함수가 다시 만나는 교점의 x좌표를 구하려면 어떻게 식을 세워야 해?"
        else:
            with qc1:
                if st.button("📝 조립제법 인수분해 증명 힌트!", use_container_width=True):
                    preset_q = "활동지 3단계에서 x^3 - 3x - 2 = 0 을 어떻게 인수분해하면 중근과 교점이 증명돼?"
            with qc2:
                if st.button("🌟 [심화] 1:루트3 비율은 어디서 나와?", use_container_width=True):
                    preset_q = "1:1:1 말고 삼차함수에서 1 : 루트3 비율은 어떤 점들 사이에서 성립하는 거야?"
                
    input_placeholder = "참관 선생님의 질문을 입력해 보세요!" if is_guest_mode else f"[{cur_level}단계] 모둠원들과 만든 질문이나 답변을 입력하세요"
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
                        # 매 질문마다 현재 단계의 승인 태그 규칙을 강제로 리마인드하여 전송
                        remind_rule = (
                            " (주의: 학생이 도함수 근 -1, 1이나 극값을 언급했으면 답변 맨 끝에 반드시 [APPROVE_STEP1] 을 출력할 것!)"
                            if cur_level == 1 else
                            " (주의: 학생이 교점 2 또는 x=2를 언급했으면 답변 맨 끝에 반드시 [APPROVE_STEP2] 를 출력할 것!)"
                        )
                        res = st.session_state[f"chat_{current_label}"].send_message(
                            f"[현재 LV{cur_level} 단계 / {current_label} 발화]: {final_q}{remind_rule}"
                        )
                        raw_reply = res.text
                    except Exception as e:
                        raw_reply = f"일시적 연결 지연입니다. 다시 한 번 전송해 주세요: {e}"
                    
                    # ★ [이중 안전장치: AI 태그 감지 + 키워드/턴수 자동 판정]
                    new_approval = False
                    combined_text = (final_q + " " + raw_reply).replace(" ", "")
                    user_turn_cnt = sum(1 for m in st.session_state[session_key] if m["role"] == "user")
                    
                    if cur_level == 1 and not step1_approved:
                        # 1) 태그가 있거나, 2) -1과 1이 언급되었거나, 3) 2회 이상 문답 시 무조건 승인!
                        has_step1_kw = ("-1" in combined_text and "1" in combined_text) or ("증감표" in raw_reply) or ("활동지" in raw_reply)
                        if ("[APPROVE_STEP1]" in raw_reply) or has_step1_kw or (user_turn_cnt >= 2 and not is_troll):
                            update_team_progress(current_label, step1_app=1)
                            new_approval = True
                            
                    elif cur_level == 2 and not step2_approved:
                        # 1) 태그가 있거나, 2) 2턴 이상에서 x=2 관련 키워드가 나왔거나, 3) 3회 이상 문답 시 승인!
                        has_step2_kw = ("x=2" in combined_text) or ("(2,2)" in combined_text) or ("자로" in raw_reply) or ("2" in final_q and user_turn_cnt >= 2)
                        if ("[APPROVE_STEP2]" in raw_reply) or has_step2_kw or (user_turn_cnt >= 4 and not is_troll):
                            update_team_progress(current_label, step2_app=1)
                            new_approval = True
                    
                    bot_reply = raw_reply.replace("[APPROVE_STEP1]", "").replace("[APPROVE_STEP2]", "").strip()
                    st.markdown(bot_reply)
                    st.session_state[session_key].append({"role": "assistant", "content": bot_reply})
                    save_log(current_label, final_q, bot_reply, is_troll)
                    
                    if new_approval:
                        st.toast("🎉 탐구 인증 완료! 왼쪽 화면의 [활동지 작성 완료] 초록색 버튼을 눌러 그래프를 여세요!", icon="✅")
                        time.sleep(0.8)
                        st.rerun()