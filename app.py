import streamlit as st
import google.generativeai as genai
import numpy as np
import matplotlib.pyplot as plt
import edge_tts
import asyncio
import datetime
import time
import os
import sqlite3
import pandas as pd

# ==========================================
# 1. 페이지 설정 및 모둠/대시보드 CSS 스타일
# ==========================================
st.set_page_config(page_title="문화고 2학년 미적분Ⅰ AI 튜터 & 관제", page_icon="📐", layout="wide")

st.markdown("""
<style>
    h1 { font-size: 2.0rem !important; }
    h2, h3 { font-size: 1.4rem !important; }
    
    /* 태블릿 채팅 폰트 시인성 확보 */
    .stChatMessage p, .stChatMessage li, .stChatMessage div {
        font-size: 1.15rem !important;
        line-height: 1.65 !important;
    }
    
    /* 대시보드 조별 카드 */
    .dash-card {
        background: #ffffff;
        border-radius: 12px;
        border: 2px solid #e2e8f0;
        padding: 14px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.08);
        margin-bottom: 14px;
        min-height: 250px;
    }
    .dash-card.warn-stuck { border: 2.5px solid #f59e0b; background: #fffbeb; }
    .dash-card.warn-troll { border: 2.5px solid #ef4444; background: #fef2f2; }
    
    .dash-header {
        display: flex; justify-content: space-between; align-items: center;
        border-bottom: 1.5px solid #e2e8f0; padding-bottom: 6px; margin-bottom: 8px;
    }
    .dash-title { font-size: 1.25rem; font-weight: 800; color: #0f172a; }
    .badge-ok { background: #dcfce7; color: #15803d; padding: 2px 7px; border-radius: 6px; font-size: 0.75rem; font-weight: 700; }
    .badge-stuck { background: #fef3c7; color: #b45309; padding: 2px 7px; border-radius: 6px; font-size: 0.75rem; font-weight: 800; }
    .badge-troll { background: #fee2e2; color: #b91c1c; padding: 2px 7px; border-radius: 6px; font-size: 0.75rem; font-weight: 800; }
    
    .q-preview { font-size: 0.95rem; font-weight: 700; color: #1e40af; margin-bottom: 4px; line-height: 1.35; }
    .a-preview { font-size: 0.88rem; color: #334155; line-height: 1.45; background: #f8fafc; padding: 7px; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 로컬 SQLite 경량 공유 DB (태블릿 간 데이터 집계)
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
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT INTO logs (team, question, answer, is_troll) VALUES (?, ?, ?, ?)",
                  (team, question, answer, is_troll))
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
# 3. 문화고등학교 교시별 시간 모듈 (한국 표준시 KST 고정)
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
    # UTC 기준 서버 시각에 9시간을 더해 한국 시각(KST)으로 변환
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    kst_now = utc_now + datetime.timedelta(hours=9)
    cur_time = kst_now.time()
    
    for period, start, end in SCHEDULE:
        if start <= cur_time <= end:
            start_dt = datetime.datetime.combine(kst_now.date(), start, tzinfo=kst_now.tzinfo)
            elapsed = int((kst_now - start_dt).total_seconds() // 60)
            return period, elapsed
            
    return "테스트", 15

cur_period, elapsed_min = get_current_period_and_elapsed()

# ==========================================
# 4. 사이드바 및 모드 선택 (반드시 조건문보다 위에 위치!)
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
    if cur_period != "테스트":
        st.metric(label=f"{cur_period}교시 진행 시간", value=f"{elapsed_min}분 경과", delta=f"{max(0, 47 - elapsed_min)}분 남음")
    else:
        st.caption("수업 외 시간 (테스트 모드)")
# =========================================================================
# MODE C: 👀 참관교사용 실시간 수업 브리핑 & 관전 가이드 (무암호 오픈)
# =========================================================================
if user_mode == "👀 참관교사용 실시간 브리핑":
    st.title("📋 2026 문화고 연구수업 참관 가이드 & 실시간 관제")
    st.caption("2학년 미적분Ⅰ: 소크라테스 AI 튜터 기반 삼차함수 그래프의 비율 관계 탐구")
    
    # 1. 수업 개요 및 타임라인 배너
    t_col1, t_col2, t_col3 = st.columns([1.2, 1.8, 1])
    with t_col1:
        st.markdown("""
        **[수업 정보]**
        - **일시/장소:** 2학년 수학교실
        - **수업자:** 최호섭 선생님
        - **환경:** 모둠별 태블릿 + A4 양면 활동지
        """)
    with t_col2:
        st.markdown(f"""
        **[수업 진행 단계 (47분 가용)]**
        - 현재: **{cur_period}교시 ({elapsed_min}분 경과)**
        - 0~10분: 문제 제기 및 AI 프롬프트 첫 발문
        - 10~25분: 핵심 4개 x좌표 탐색 및 1:1:1 기하학적 발견
        - 25~40분: 조립제법 기반 2:1 대수적 정당화(증명)
        - 40~47분: 1:√3 확장 안내 및 모둠 자기평가
        """)
    with t_col3:
        if st.button("🔄 실시간 갱신", use_container_width=True):
            st.rerun()
            
    st.markdown("---")
    
    # 2. 참관 관전 포인트 3선
    st.subheader("💡 오늘의 참관 관전 포인트 (Focus Points)")
    p1, p2, p3 = st.columns(3)
    with p1:
        st.info("""
        **1. 수학적 발문의 정교화**  
        학생들이 단순히 "답 알려줘"가 아니라, *극댓값, 극솟값, 도함수의 대칭축(변곡점)* 등 정확한 교과 어휘로 AI에게 단서를 캐내는지 관찰해 주세요.
        """)
    with p2:
        st.success("""
        **2. 활동지 하이브리드 연계**  
        AI 답변을 보고 끝내는 것이 아니라, 모둠원과 토의하여 **종이 활동지 2단계 그래프에 직접 자를 대고 보조선과 1:1:1 간격을 채우는지** 확인해 주세요.
        """)
    with p3:
        st.warning("""
        **3. 기하학에서 대수로의 증명**  
        눈으로 본 2:1 비율을 $x^3 - 3x - 2 = 0$ 인수분해를 통해 **손으로 직접 증명해내는 정당화 과정**에 도달하는지 지켜봐 주세요.
        """)
        
    st.markdown("---")
    
    # 3. 실시간 모둠별 탐구 피드 (실시간 로그 열람)
    st.subheader("📡 모둠별 실시간 AI 대화 피드")
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
# MODE A: 👨‍🏫 교사용 6분할 실시간 관제 센터 (PIN 인증 시 활성화)
# =========================================================================
if user_mode == "👨‍🏫 교사용 실시간 관제" and is_teacher_authorized:
    h_col1, h_col2 = st.columns([3, 1])
    with h_col1:
        st.title("🖥️ [교단 관제 전광판] 6개 조 실시간 탐구 현황")
        st.caption("실시간으로 학생들의 질문을 분석하여 정체된 모둠이나 비수학적 장난 입력을 감지합니다.")
    with h_col2:
        st.write("")
        auto_refresh = st.checkbox("🔄 8초 자동 갱신", value=True)
        if st.button("즉시 갱신", use_container_width=True):
            st.rerun()
            
    st.markdown("---")
    
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
            # 상태 분석 (장난 감지 / 정체 조 감지)
            has_troll = False
            last_q = "-"
            last_a = "-"
            if t_cnt > 0:
                last_row = t_logs.iloc[-1]
                last_q = str(last_row.get("question", "-"))
                last_a = str(last_row.get("answer", "-"))
                has_troll = (last_row.get("is_troll", 0) == 1)
            
            if has_troll:
                card_style = "dash-card warn-troll"
                status_badge = '<span class="badge-troll">🚨 비수학적 장난 감지</span>'
            elif t_cnt == 0:
                card_style = "dash-card warn-stuck"
                status_badge = '<span class="badge-stuck">🟡 미참여 (순회 요망)</span>'
            else:
                card_style = "dash-card"
                status_badge = '<span class="badge-ok">🟢 순항 중</span>'
                
            st.markdown(f"""
            <div class="{card_style}">
                <div class="dash-header">
                    <span class="dash-title">{t_name}</span>
                    <div>
                        {status_badge}
                        <span style="font-size:0.8rem; font-weight:700; margin-left:4px; color:#475569;">({t_cnt}회 질문)</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            if t_cnt > 0:
                st.markdown(f"""
                    <div class="q-preview"><b>최근 질문:</b> {last_q}</div>
                    <div class="a-preview"><b>AI 답변 요약:</b> {last_a[:100]}...</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                    <div style="color:#94a3b8; text-align:center; padding:50px 0; font-size:0.9rem;">
                        아직 전송된 질문이 없습니다.<br>1단계 작성을 독려해 주세요.
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
    if auto_refresh:
        time.sleep(8)
        st.rerun()
        
    st.stop()  # 교사용 화면일 경우 학생 화면 렌더링 중단

# =========================================================================
# MODE B: 🤖 학생 모둠용 AI 튜터 화면 (1조 ~ 6조)
# =========================================================================

# 장난 방어 감지 키워드 리스트
TROLL_WORDS = ["바보", "멍청", "롤", "티어", "롤체", "피파", "축구", "메이플", "사랑해", "개새", "존나", "시발", "섹스", "ㅋㅋㅋㅋ", "ㅎㅎㅎㅎ", "죽어"]

def check_is_troll(text):
    for w in TROLL_WORDS:
        if w in text:
            return True
    return False

# 음성 가이드
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

# Gemini 모델 설정 및 강력한 가드레일 프롬프트
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

col_graph, col_chat = st.columns([1, 1], gap="medium")

# 좌측 그래프
with col_graph:
    st.subheader("📈 탐구용 그래프")
    x = np.linspace(-2.5, 2.5, 400)
    y = x**3 - 3*x
    dy = 3*x**2 - 3
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 7.5))
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
                    
                    # 로컬 관제 DB에 즉시 저장
                    save_log(user_mode, final_q, bot_reply, is_troll)
        st.rerun()