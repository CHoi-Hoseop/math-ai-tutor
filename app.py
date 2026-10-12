import streamlit as st
import google.generativeai as genai
import numpy as np
import matplotlib.pyplot as plt
import edge_tts
import asyncio
import requests
import datetime

# ==========================================
# 1. 페이지 기본 설정 및 모둠용 대형 폰트 스타일
# ==========================================
st.set_page_config(page_title="문화고 2학년 AI 튜터", page_icon="🤖", layout="wide")

st.markdown("""
<style>
    /* 제목 및 부제목 크기 확대 */
    h1 { font-size: 2.1rem !important; }
    h2, h3 { font-size: 1.5rem !important; }
    
    /* 채팅 말풍선 폰트 대폭 확대 (모둠 공용 태블릿 시인성 확보) */
    .stChatMessage p, .stChatMessage li, .stChatMessage div {
        font-size: 1.15rem !important;
        line-height: 1.65 !important;
    }
    
    /* 버튼 텍스트 크기 및 여백 확대 */
    .stButton button {
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        padding: 0.5rem 1rem !important;
    }
    
    /* 알림 박스 폰트 확대 */
    .stAlert p {
        font-size: 1.1rem !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 문화고등학교 교시별 시간 자동 계산 모듈
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
    now = datetime.datetime.now()
    cur_time = now.time()
    for period, start, end in SCHEDULE:
        if start <= cur_time <= end:
            start_dt = datetime.datetime.combine(now.date(), start)
            elapsed = int((now - start_dt).total_seconds() // 60)
            return period, elapsed
    return "테스트", 15  # 수업 시간 외 테스트 시 기본 15분 경과로 시뮬레이션

cur_period, elapsed_min = get_current_period_and_elapsed()

# ==========================================
# 3. 사이드바 설정 (조 선택 및 참관교사 모드)
# ==========================================
with st.sidebar:
    st.header("👥 접속 모드 설정")
    team_name = st.selectbox(
        "모둠을 선택하세요",
        ["1조", "2조", "3조", "4조", "5조", "6조", "👨‍🏫 참관교사"]
    )
    if team_name == "👨‍🏫 참관교사":
        st.info("선생님 환영합니다! 자유롭게 AI 튜터의 소크라테스식 발문과 힌트 수준을 테스트해 보세요.")
    else:
        st.success(f"현재 **{team_name}** 모드로 탐구 중입니다.")
    
    st.markdown("---")
    st.header("⏱️ 수업 타이머 현황")
    if cur_period != "테스트":
        st.metric(
            label=f"현재 {cur_period}교시 진행 상황",
            value=f"{elapsed_min}분 경과",
            delta=f"{max(0, 47 - elapsed_min)}분 남음"
        )
    else:
        st.info("현재는 정규 수업 교시 외 시간(테스트 모드)입니다.")
        
    st.markdown("---")
    st.caption("📌 **탐구 규칙:** 우리 조에서 합의한 질문을 태블릿으로 전송하고, 단서는 책상 위 종이 활동지에 기록하세요.")

# ==========================================
# 4. 구글 시트 웹훅 전송 함수
# ==========================================
# ★ Apps Script에서 배포한 웹 앱 URL을 아래 따옴표 안에 넣어주세요.
WEBHOOK_URL = "여기에_선생님의_웹앱_URL을_붙여넣으세요"

def log_to_google_sheet(team, question, answer):
    if "script.google.com" in WEBHOOK_URL:
        try:
            payload = {
                "team": team,
                "question": question,
                "answer": answer
            }
            requests.post(WEBHOOK_URL, json=payload, timeout=1.5)
        except Exception:
            pass

# ==========================================
# 5. 헤더 및 음성 가이드 영역 (Edge-TTS)
# ==========================================
st.title("🤖 [문화고등학교 2학년] 삼차함수 그래프의 비밀을 찾아라!")
st.markdown("AI 튜터에게 수학적 용어로 질문을 던져 삼차함수에 숨겨진 **기하학적 비율 관계**를 찾아내세요.")
st.markdown("---")

st.markdown("### 🎧 AI 튜터 이용 가이드 (순서대로 재생 버튼을 눌러주세요)")

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

btn1, btn2, btn3 = st.columns(3)
with btn1:
    if st.button("▶ 1단계: 미션 브리핑 듣기", use_container_width=True):
        play_audio_guide("문화고등학교 2학년 여러분, 환영합니다. 오늘 여러분의 미션은 삼차함수 그래프 속에 숨겨진 거리 비율을 스스로 찾아내는 것입니다. 화면 왼쪽을 보세요. 위쪽 삼차함수와 아래쪽 도함수 그래프를 위아래로 훑어보며, 세로 점선들이 어떤 의미를 가지는지 관찰해 보세요.")

with btn2:
    if st.button("▶ 2단계: AI와 스무고개 시작하기", use_container_width=True):
        play_audio_guide("관찰이 끝났다면, 이제 오른쪽 AI 튜터와 대결할 차례입니다! AI는 정답을 절대 먼저 알려주지 않습니다. 극댓값, 극솟값, 대칭축 같은 정확한 수학 용어로 질문해야 단서를 얻을 수 있습니다. 첫 질문이 막막하다면 극댓값과 극솟값의 x좌표를 먼저 물어보세요.")

with btn3:
    if st.button("▶ 3단계: 수학적 증명 도전하기", use_container_width=True):
        play_audio_guide("비율의 비밀을 알아냈나요? 정말 훌륭합니다! 이제 책상 위의 활동지 3단계로 넘어가세요. 여러분이 발견한 그 규칙이 항상 성립하는지 도함수를 이용해 논리적으로 증명해 봅시다.")

st.markdown("---")

# ==========================================
# 6. Gemini API 및 프롬프트 시스템 설정
# ==========================================
API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=API_KEY)

system_instruction = """
너는 고등학교 미적분Ⅰ 수업에서 학생들의 탐구를 돕는 친절한 소크라테스식 AI 튜터야.
학생들이 삼차함수 f(x) = x^3 - 3x 그래프의 극댓값(-1), 변곡점(0), 극솟값(1), 접선 교점(2) 사이의 '1:1:1' 및 '2:1' 비율 관계를 스스로 발견하도록 유도해야 해.

[수업 시간대별 넛지(Nudge) 지침 - 총 가용시간 47분]
1. [초반: 0~12분 경과] 학생의 자율 탐색을 관찰하며 정답은 삼가고, 요청받은 좌표값만 간결히 제공할 것.
2. [중반: 13~26분 경과] 정체된 조가 있다면 답변 끝에 "👉 추천 질문: '아래쪽 이차함수의 대칭축 x=0은 위 삼차함수 그래프에서 어떤 위치야?'라고 물어보렴!"을 달아 방향을 잡아줄 것.
3. [후반: 27~40분 경과] 시간이 촉박하므로 "👉 추천 질문: '극댓값을 지나는 접선 y=2가 삼차함수 곡선과 다시 만나는 점의 x좌표는 뭐야?'라고 물어보렴!"을 제안하여 1:1:1 비율을 완성하고 활동지 3단계 증명으로 넘어가게 촉진할 것.
4. [마무리: 41분 이후] "탐구 시간이 마감되었습니다. 책상 위 활동지 3단계 대수적 증명을 완성하고 모둠 토의를 마무리하세요."라고 안내할 것.

[소크라테스식 꼬리 질문 및 활동지 연계 절대 규칙]
- '2:1', '1:1:1'이라는 최종 비율 숫자를 학생보다 먼저 절대 직접 말하지 마.
- 질문에 답한 뒤에는 반드시 학생이 화면 그래프를 다시 관찰하거나 계산해야 하는 '구체적인 꼬리 질문(모둠 미션)'을 하나 던져.
- 답변의 맨 마지막 줄에는 항상 책상 위 종이 활동지 작성을 독려하는 멘트를 고정으로 출력해:
  예시: "✍️ [활동지 기록] 방금 확인한 내용을 책상 위 활동지 표에 샤프로 기록하고 다음 질문을 모둠원과 상의하세요!"
- 학생이 수학 용어(극댓값, 변곡점, 대칭축, 접선 등)를 바르게 사용하면 적극 칭찬해.
"""

model = genai.GenerativeModel(
    model_name="gemini-3.8-flash",
    system_instruction=system_instruction
)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat" not in st.session_state:
    st.session_state.chat = model.start_chat(history=[])

# ==========================================
# 7. 화면 레이아웃 (좌측 그래프 / 우측 채팅)
# ==========================================
col1, col2 = st.columns([1, 1], gap="medium")

with col1:
    st.subheader("📈 탐구용 그래프")
    
    x = np.linspace(-2.5, 2.5, 400)
    y = x**3 - 3*x
    dy = 3*x**2 - 3
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 7.5))
    plt.subplots_adjust(hspace=0.28)
    
    xticks = np.arange(-2, 3, 1)
    
    # [상단: 삼차함수 f(x)]
    ax1.plot(x, y, label="$f(x) = x^3 - 3x$", color="#1f77b4", linewidth=2.5)
    ax1.spines['left'].set_position('zero')
    ax1.spines['bottom'].set_position('zero')
    ax1.spines['right'].set_color('none')
    ax1.spines['top'].set_color('none')
    
    ax1.set_xticks(xticks)
    ax1.set_xticklabels([str(i) if i != 0 else '' for i in xticks], fontsize=11)
    yticks1 = np.arange(-4, 5, 1)
    ax1.set_yticks(yticks1)
    ax1.set_yticklabels([str(i) if i != 0 else '' for i in yticks1], fontsize=11)
    ax1.set_xlim(-2.5, 2.5)
    ax1.set_ylim(-4.5, 4.5)
    ax1.text(-0.25, -0.45, 'O', fontsize=12, fontstyle='italic')
    
    # 한글 깨짐 방지 수식 라벨
    ax1.axhline(2, color='red', alpha=0.45, linestyle=':', label="$y = 2$")
    ax1.axhline(-2, color='blue', alpha=0.45, linestyle=':', label="$y = -2$")
    ax1.plot([2], [2], marker='o', markersize=7, color='red')
    ax1.plot([-2], [-2], marker='o', markersize=7, color='blue')
    
    ax1.grid(True, alpha=0.3, linestyle='--')
    ax1.legend(loc='upper left', fontsize=10)
    
    # [하단: 도함수 f'(x)]
    ax2.plot(x, dy, label="$f'(x) = 3x^2 - 3$", color="#ff7f0e", linewidth=2.2)
    ax2.spines['left'].set_position('zero')
    ax2.spines['bottom'].set_position('zero')
    ax2.spines['right'].set_color('none')
    ax2.spines['top'].set_color('none')
    
    ax2.set_xticks(xticks)
    ax2.set_xticklabels([str(i) if i != 0 else '' for i in xticks], fontsize=11)
    yticks2 = np.arange(-4, 10, 2)
    ax2.set_yticks(yticks2)
    ax2.set_yticklabels([str(i) if i != 0 else '' for i in yticks2], fontsize=11)
    ax2.set_xlim(-2.5, 2.5)
    ax2.set_ylim(-4.5, 9.5)
    ax2.text(-0.25, -0.85, 'O', fontsize=12, fontstyle='italic')
    
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.legend(loc='upper center', fontsize=10)
    
    # [공통 수직 보조선: x = -2, -1, 0, 1, 2]
    for ax in [ax1, ax2]:
        ax.axvline(0, color='purple', alpha=0.6, linestyle='--', linewidth=1.5)  # 변곡점/도함수 축
        ax.axvline(-1, color='gray', alpha=0.6, linestyle='--', linewidth=1.5)  # 극댓값
        ax.axvline(1, color='gray', alpha=0.6, linestyle='--', linewidth=1.5)   # 극솟값
        ax.axvline(-2, color='blue', alpha=0.4, linestyle=':', linewidth=1.2)   # 접선 교점
        ax.axvline(2, color='red', alpha=0.4, linestyle=':', linewidth=1.2)     # 접선 교점
    
    st.pyplot(fig)
    st.info("💡 **관찰 포인트:** 세로 보조선이 그어진 $x = -2, -1, 0, 1, 2$ 사이의 간격에 어떤 규칙이 보이나요?")

with col2:
    st.subheader("💬 소크라테스 AI 튜터")
    
    chat_container = st.container(height=470)
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # 💡 첫 질문 추천 칩 버튼 (대화가 없을 때만 1회성으로 노출하여 남발 차단)
    preset_query = None
    if len(st.session_state.messages) == 0:
        st.markdown("##### 💡 첫 질문 가이드 (마중물 질문을 선택해 보세요)")
        q_col1, q_col2 = st.columns(2)
        with q_col1:
            if st.button("📍 극댓값과 극솟값의 x좌표는?", use_container_width=True):
                preset_query = "이 삼차함수의 극댓값과 극솟값의 x좌표는 각각 뭐야?"
        with q_col2:
            if st.button("⚖️ 도함수의 대칭축 x=0의 의미는?", use_container_width=True):
                preset_query = "아래 도함수의 대칭축 x=0은 위 삼차함수에서 어떤 점이야?"
    else:
        st.caption("📝 **학습 규칙:** AI의 답변과 미션을 확인하고, 종이 활동지에 기록한 후 다음 질문을 입력하세요.")

    user_input = st.chat_input("AI 튜터에게 질문을 입력하세요")
    active_prompt = preset_query if preset_query else user_input

    if active_prompt:
        st.session_state.messages.append({"role": "user", "content": active_prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(active_prompt)
                
            with st.chat_message("assistant"):
                with st.spinner("🤔 문화고 2학년 학생의 질문을 분석하고 있습니다..."):
                    try:
                        # 경과 시간과 모둠 질문 회차를 메타데이터로 함께 주입
                        turn_count = len(st.session_state.messages) // 2
                        prompt_with_meta = f"[수업 경과: {elapsed_min}분 / 누적 질문: {turn_count}회차]\n학생 질문: {active_prompt}"
                        
                        res = st.session_state.chat.send_message(prompt_with_meta)
                        bot_reply = res.text
                    except Exception as e:
                        bot_reply = f"일시적인 연결 지연이 발생했습니다: {e}"
                        
                    st.markdown(bot_reply)
                    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                    
                    log_to_google_sheet(team_name, active_prompt, bot_reply)
        st.rerun()