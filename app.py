import streamlit as st
import google.generativeai as genai
import numpy as np
import matplotlib.pyplot as plt
import edge_tts
import asyncio
import requests

# 1. 페이지 기본 설정
st.set_page_config(page_title="문화고 2학년 AI 튜터", page_icon="🤖", layout="wide")
st.title("🤖 [문화고등학교 2학년] 삼차함수 그래프의 비밀을 찾아라!")
st.markdown("AI 튜터에게 수학적 용어로 질문을 던져 삼차함수에 숨겨진 **기하학적 비율 관계**를 찾아내세요.")
st.markdown("---")

# 2. 사이드바 설정 (조 선택 및 참관교사 모드)
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
    st.caption("📌 **탐구 규칙:** 우리 조에서 합의한 질문을 태블릿으로 전송하고, 단서는 책상 위 종이 활동지에 기록하세요.")

# 3. 구글 시트 웹훅 전송 함수
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
            # 백그라운드 전송 (타임아웃 1.5초 설정으로 학생 화면 지연 차단)
            requests.post(WEBHOOK_URL, json=payload, timeout=1.5)
        except Exception:
            pass

# 4. 음성 가이드 영역 (Edge-TTS)
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
    if st.button("▶ 1단계: 미션 브리핑 듣기"):
        play_audio_guide("문화고등학교 2학년 여러분, 환영합니다. 오늘 여러분의 미션은 삼차함수 그래프 속에 숨겨진 거리 비율을 스스로 찾아내는 것입니다. 화면 왼쪽을 보세요. 위쪽 삼차함수와 아래쪽 도함수 그래프를 위아래로 훑어보며, 세로 점선들이 어떤 의미를 가지는지 관찰해 보세요.")

with btn2:
    if st.button("▶ 2단계: AI와 스무고개 시작하기"):
        play_audio_guide("관찰이 끝났다면, 이제 오른쪽 AI 튜터와 대결할 차례입니다! AI는 정답을 절대 먼저 알려주지 않습니다. 극댓값, 극솟값, 대칭축 같은 정확한 수학 용어로 질문해야 단서를 얻을 수 있습니다. 첫 질문이 막막하다면 극댓값과 극솟값의 x좌표를 먼저 물어보세요.")

with btn3:
    if st.button("▶ 3단계: 수학적 증명 도전하기"):
        play_audio_guide("비율의 비밀을 알아냈나요? 정말 훌륭합니다! 이제 책상 위의 활동지 3단계로 넘어가세요. 여러분이 발견한 그 규칙이 항상 성립하는지 도함수를 이용해 논리적으로 증명해 봅시다.")

st.markdown("---")

# 5. Gemini API 및 모델 설정
API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=API_KEY)

system_instruction = """
너는 고등학교 미적분Ⅰ 수업에서 학생들의 탐구를 돕는 친절한 소크라테스식 AI 튜터야.
학생들이 삼차함수 f(x) = x^3 - 3x 그래프의 극댓값(-1), 변곡점(0), 극솟값(1), 접선 교점(2) 사이의 '1:1:1' 및 '2:1' 비율 관계를 스스로 발견하도록 유도해야 해.

[절대 지켜야 할 규칙]
1. '2:1', '1:1:1' 같은 비율이나 정답을 절대 먼저 말하지 마.
2. 학생이 질문하면 힌트가 될 만한 좌표나 함숫값, 기하학적 대칭성만 간결하게 제공해.
3. 도함수 f'(x)가 이차함수라는 점과 그 대칭축(x=0)을 힌트로 주어, 삼차함수의 변곡점과 극값의 위치 관계를 추론하도록 이끌어.
4. 학생의 질문에 대답한 후에는 반드시 다음 생각을 유도하는 '꼬리 질문'을 하나씩 던져.
5. 학생이 수학 용어(극댓값, 변곡점, 대칭축, 접선 등)를 사용하면 적극적으로 칭찬해.

[자동 힌트 넛지(Nudge) 규칙]
- 학생의 누적 질문 수가 3회 이상이 되었는데도 단순 좌표 질문만 맴돈다면:
  답변 끝에 "👉 다음 질문 추천: '아래쪽 이차함수의 대칭축 x=0은 위 삼차함수 그래프에서 어떤 점이야?'라고 나에게 물어보세요!"를 덧붙여 질문을 견인해.
- 학생이 극값 좌표를 파악했으나 비율을 못 찾고 있다면:
  "👉 다음 질문 추천: '극댓값을 지나는 접선 y=2가 삼차함수 곡선과 다시 만나는 점의 x좌표는 뭐야?'라고 물어보세요!"를 제안해.
"""

# 모델 초기화
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=system_instruction
)

# 세션 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat" not in st.session_state:
    st.session_state.chat = model.start_chat(history=[])

# 6. 화면 레이아웃 (좌측 그래프 / 우측 채팅)
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📈 탐구용 그래프")
    st.markdown("위쪽: 삼차함수 $f(x)$, 아래쪽: 도함수 $f'(x)$")
    
    x = np.linspace(-2.5, 2.5, 400)
    y = x**3 - 3*x
    dy = 3*x**2 - 3
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 7.5))
    plt.subplots_adjust(hspace=0.28)
    
    xticks = np.arange(-2, 3, 1)
    
    # [상단 그래프: f(x)]
    ax1.plot(x, y, label="$f(x) = x^3 - 3x$", color="#1f77b4", linewidth=2.2)
    ax1.spines['left'].set_position('zero')
    ax1.spines['bottom'].set_position('zero')
    ax1.spines['right'].set_color('none')
    ax1.spines['top'].set_color('none')
    
    ax1.set_xticks(xticks)
    ax1.set_xticklabels([str(i) if i != 0 else '' for i in xticks])
    yticks1 = np.arange(-4, 5, 1)
    ax1.set_yticks(yticks1)
    ax1.set_yticklabels([str(i) if i != 0 else '' for i in yticks1])
    ax1.set_xlim(-2.5, 2.5)
    ax1.set_ylim(-4.5, 4.5)
    ax1.text(-0.25, -0.45, 'O', fontsize=11, fontstyle='italic')
    
    # 극대/극소 접선
    ax1.axhline(2, color='red', alpha=0.45, linestyle=':', label="극대 접선 $y=2$")
    ax1.axhline(-2, color='blue', alpha=0.45, linestyle=':', label="극소 접선 $y=-2$")
    
    # 핵심 접선 교점 마커 표시 (2, 2) 및 (-2, -2)
    ax1.plot([2], [2], marker='o', markersize=6, color='red')
    ax1.plot([-2], [-2], marker='o', markersize=6, color='blue')
    
    ax1.grid(True, alpha=0.25, linestyle='--')
    ax1.legend(loc='upper left', fontsize=9)
    
    # [하단 그래프: f'(x)]
    ax2.plot(x, dy, label="$f'(x) = 3x^2 - 3$", color="#ff7f0e", linewidth=2.2)
    ax2.spines['left'].set_position('zero')
    ax2.spines['bottom'].set_position('zero')
    ax2.spines['right'].set_color('none')
    ax2.spines['top'].set_color('none')
    
    ax2.set_xticks(xticks)
    ax2.set_xticklabels([str(i) if i != 0 else '' for i in xticks])
    yticks2 = np.arange(-4, 10, 2)
    ax2.set_yticks(yticks2)
    ax2.set_yticklabels([str(i) if i != 0 else '' for i in yticks2])
    ax2.set_xlim(-2.5, 2.5)
    ax2.set_ylim(-4.5, 9.5)
    ax2.text(-0.25, -0.85, 'O', fontsize=11, fontstyle='italic')
    
    ax2.grid(True, alpha=0.25, linestyle='--')
    ax2.legend(loc='upper center', fontsize=9)
    
    # [핵심 수직 보조선: x = -2, -1, 0, 1, 2]
    # -1, 0, 1은 강조 회색 점선 / -2, 2는 확장 보조 점선
    for ax in [ax1, ax2]:
        ax.axvline(0, color='purple', alpha=0.6, linestyle='--', linewidth=1.2)  # 변곡/대칭축
        ax.axvline(-1, color='gray', alpha=0.6, linestyle='--', linewidth=1.2)  # 극대
        ax.axvline(1, color='gray', alpha=0.6, linestyle='--', linewidth=1.2)   # 극소
        ax.axvline(-2, color='blue', alpha=0.35, linestyle=':', linewidth=1.0)  # 교점 확장
        ax.axvline(2, color='red', alpha=0.35, linestyle=':', linewidth=1.0)    # 교점 확장
    
    st.pyplot(fig)
    st.info("💡 **관찰 포인트:** 보조선이 그어진 $x = -1, 0, 1, 2$ 사이의 간격에 어떤 규칙이 보이나요?")

with col2:
    st.subheader("💬 소크라테스 AI 튜터")
    
    chat_container = st.container(height=520)
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    st.caption("💡 **첫 질문 추천:** `이 삼차함수의 극댓값과 극솟값의 x좌표는 각각 뭐야?`")
    user_input = st.chat_input("AI 튜터에게 질문을 입력하세요")
    
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(user_input)
                
            with st.chat_message("assistant"):
                with st.spinner("🤔 문화고 2학년 학생의 질문을 분석하고 있습니다..."):
                    try:
                        res = st.session_state.chat.send_message(user_input)
                        bot_reply = res.text
                    except Exception as e:
                        bot_reply = f"일시적인 연결 지연이 발생했습니다: {e}"
                        
                    st.markdown(bot_reply)
                    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
                    
                    # 구글 시트로 조 이름, 질문, AI 답변 실시간 전송
                    log_to_google_sheet(team_name, user_input, bot_reply)