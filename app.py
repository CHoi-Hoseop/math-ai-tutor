import streamlit as st
import google.generativeai as genai
import numpy as np
import matplotlib.pyplot as plt

# 1. 페이지 기본 설정
st.set_page_config(page_title="문화고 2-5 AI 튜터", page_icon="🤖", layout="wide")
st.title("🤖 [문화고 2학년 5반] 삼차함수 그래프의 비밀을 찾아라!")
st.markdown("AI 튜터에게 수학적 용어로 질문을 던져 삼차함수에 숨겨진 **기하학적 비율 관계**를 찾아내세요.")
st.markdown("---")

# 2. Gemini API 설정 (보안을 위해 st.secrets 사용)
API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=API_KEY)

# 3. AI 튜터 페르소나 (시스템 프롬프트) 설정
system_instruction = """
너는 고등학교 미적분 수업에서 학생들의 탐구를 돕는 친절한 소크라테스식 AI 튜터야.
학생들이 삼차함수 그래프의 극댓값, 극솟값, 교점 사이의 '2:1' 또는 '1:1:1' 비율 관계를 스스로 발견하도록 유도해야 해.

[절대 지켜야 할 규칙]
1. '2:1', '1:1:1' 같은 비율이나 정답을 절대 먼저 말하지 마.
2. 학생이 질문하면 힌트가 될 만한 좌표나 함숫값만 제공해. (예: f(x) = x^3 - 3x 에서 극값의 x좌표 등)
3. ★(중요) 도함수 f'(x)가 이차함수라는 점과 그 '좌우 대칭성'을 힌트로 제시하여, 삼차함수의 극값과 변곡점(정가운데 점)의 위치 관계를 추론하도록 유도해.
4. 학생의 질문에 대답한 후에는 반드시 다음 사고를 촉진하는 '꼬리 질문'을 하나씩 던져.
5. 학생이 수학 용어(극댓값, 변곡점, 대칭축, 접선 등)를 사용하여 질문하면 크게 칭찬해 줘.
"""

# 모델 초기화
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=system_instruction
)

# 세션 상태에 대화 기록 저장
if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(history=[])

# 4. 화면 레이아웃 분할 (좌: 연동 그래프 2개, 우: AI 챗봇)
col1, col2 = st.columns([1, 1])

# 좌측: 수학 그래프 시각화 영역 (삼차함수 & 도함수)
with col1:
    st.subheader("📈 탐구용 그래프")
    st.markdown("위쪽은 함수 $f(x)$, 아래쪽은 도함수 $f'(x)$입니다. 세로 점선을 따라 두 그래프의 관계를 관찰해 보세요.")
    
    # x 범위 설정
    x = np.linspace(-2.5, 2.5, 400)
    y = x**3 - 3*x       # 삼차함수
    dy = 3*x**2 - 3      # 이차함수(도함수)
    
    # sharex=True를 제거하여 위아래 그래프 모두 x축 숫자가 나오도록 수정
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 7))
    plt.subplots_adjust(hspace=0.2) # 위아래 그래프 간격
    
    # --- [상단 그래프] 원래 함수 f(x) ---
    ax1.plot(x, y, label="$f(x) = x^3 - 3x$", color="#1f77b4", linewidth=2)
    ax1.spines['left'].set_position('zero')
    ax1.spines['bottom'].set_position('zero')
    ax1.spines['right'].set_color('none')
    ax1.spines['top'].set_color('none')
    
    ax1.set_xticks(np.arange(-2, 3, 1)) # x축 눈금 -2, -1, 0, 1, 2 명시
    ax1.set_yticks(np.arange(-4, 5, 1))
    ax1.set_xlim(-2.5, 2.5)
    ax1.set_ylim(-4.5, 4.5)
    
    # f(x)의 극대, 극소 가로 보조선
    ax1.axhline(2, color='red', alpha=0.4, linestyle=':')
    ax1.axhline(-2, color='blue', alpha=0.4, linestyle=':')
    ax1.grid(True, alpha=0.3, linestyle='--')
    ax1.legend(loc='upper left')
    
    # --- [하단 그래프] 도함수 f'(x) ---
    ax2.plot(x, dy, label="$f'(x) = 3x^2 - 3$", color="#ff7f0e", linewidth=2)
    ax2.spines['left'].set_position('zero')
    ax2.spines['bottom'].set_position('zero')
    ax2.spines['right'].set_color('none')
    ax2.spines['top'].set_color('none')
    
    ax2.set_xticks(np.arange(-2, 3, 1)) # 하단 그래프도 동일하게 x축 눈금 명시
    ax2.set_yticks(np.arange(-4, 10, 2))
    ax2.set_xlim(-2.5, 2.5) # 위아래 그래프의 좌우 폭을 완벽히 일치시킴
    ax2.set_ylim(-4.5, 9.5)
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.legend(loc='upper center')
    
    # --- [핵심] 두 그래프를 관통하는 세로 보조선 (x=-1, 0, 1) ---
    for ax in [ax1, ax2]:
        ax.axvline(-1, color='gray', alpha=0.5, linestyle='--')
        ax.axvline(1, color='gray', alpha=0.5, linestyle='--')
        ax.axvline(0, color='gray', alpha=0.5, linestyle='--')
    
    st.pyplot(fig)
    st.info("💡 **Tip:** 아래쪽 이차함수의 '대칭축'이 위치한 $x=0$ 지점은 위쪽 삼차함수에서 어떤 모양(의미)을 가질까요? AI에게 물어보세요!")

# 우측: AI 대화 영역
with col2:
    st.subheader("💬 소크라테스 AI 튜터")
    
    # 대화 기록 출력용 컨테이너
    chat_container = st.container(height=550)
    
    with chat_container:
        for message in st.session_state.chat_session.history:
            role = "assistant" if message.role == "model" else "user"
            with st.chat_message(role):
                st.markdown(message.parts[0].text)

    # 채팅 입력창
    user_input = st.chat_input("AI에게 질문을 입력하세요 (예: 이차함수 대칭축이랑 삼차함수랑 무슨 상관이야?)")
    
    if user_input:
        with chat_container:
            with st.chat_message("user"):
                st.markdown(user_input)
        
        with chat_container:
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""
                
                response = st.session_state.chat_session.send_message(user_input, stream=True)
                for chunk in response:
                    full_response += chunk.text
                    message_placeholder.markdown(full_response + "▌")
                message_placeholder.markdown(full_response)