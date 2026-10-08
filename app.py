import streamlit as st
import google.generativeai as genai
import numpy as np
import matplotlib.pyplot as plt

# 1. 페이지 기본 설정
st.set_page_config(page_title="문화고 2학년 AI 튜터", page_icon="🤖", layout="wide")
st.title("🤖 [문화고 2학년] 삼차함수 그래프의 비밀을 찾아라!")
st.markdown("AI 튜터에게 수학적 용어로 질문을 던져 삼차함수에 숨겨진 **기하학적 비율 관계**를 찾아내세요.")
st.markdown("---")

# 2. Gemini API 설정 (선생님의 API 키를 입력하세요)
# 실제 배포 시에는 st.secrets를 활용하는 것이 안전합니다.
API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=API_KEY)

# 3. AI 튜터 페르소나 (시스템 프롬프트) 설정
system_instruction = """
너는 고등학교 미적분 수업에서 학생들의 탐구를 돕는 친절한 소크라테스식 AI 튜터야.
학생들이 삼차함수 그래프의 극댓값, 극솟값, 교점 사이의 '2:1' 또는 '1:1:1' 비율 관계를 스스로 발견하도록 유도해야 해.

[절대 지켜야 할 규칙]
1. '2:1', '1:1:1' 같은 비율이나 정답을 절대 먼저 말하지 마.
2. 학생이 질문하면 힌트가 될 만한 좌표나 함숫값만 제공해. (예: f(x) = x^3 - 3x 에서 극값의 x좌표 등)
3. 학생의 질문에 대답한 후에는 반드시 다음 사고를 촉진하는 '꼬리 질문'을 하나씩 던져.
4. 학생이 수학 용어(극댓값, 변곡점, 접선 등)를 사용하여 질문하면 크게 칭찬해 줘.
"""

# 모델 초기화
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=system_instruction
)

# 세션 상태에 대화 기록 저장
if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(history=[])

# 4. 화면 레이아웃 분할 (좌: 그래프, 우: AI 챗봇)
col1, col2 = st.columns([1, 1])

# 좌측: 수학 그래프 시각화 영역
with col1:
    st.subheader("📈 탐구용 그래프: $f(x) = x^3 - 3x$")
    st.markdown("그래프의 극댓값, 극솟값, 그리고 $x$축과의 교점을 관찰해 보세요.")
    
    # Matplotlib을 이용한 간단한 삼차함수 그래프
    x = np.linspace(-3, 3, 400)
    y = x**3 - 3*x
    
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(x, y, label="$f(x) = x^3 - 3x$", color="#1f77b4")
    ax.axhline(0, color='black', linewidth=0.8, linestyle='--')
    ax.axvline(0, color='black', linewidth=0.8, linestyle='--')
    
    # 극대, 극소 보조선 (학생 탐구용 힌트)
    ax.axhline(2, color='red', alpha=0.3, linestyle=':')
    ax.axhline(-2, color='blue', alpha=0.3, linestyle=':')
    
    ax.grid(True, alpha=0.3)
    ax.legend()
    st.pyplot(fig)
    
    st.info("💡 **Tip:** 위 그래프에서 극댓값을 갖는 점표에서 접선을 그었을 때, 그래프와 다시 만나는 교점의 $x$좌표는 무엇일까요? AI에게 물어보세요!")

# 우측: AI 대화 영역
with col2:
    st.subheader("💬 소크라테스 AI 튜터")
    
    # 대화 기록 출력용 컨테이너 (스크롤 가능하도록 높이 고정)
    chat_container = st.container(height=400)
    
    with chat_container:
        for message in st.session_state.chat_session.history:
            role = "assistant" if message.role == "model" else "user"
            with st.chat_message(role):
                st.markdown(message.parts[0].text)

    # 채팅 입력창
    user_input = st.chat_input("AI에게 질문을 입력하세요 (예: 극댓값의 x좌표는 뭐야?)")
    
    if user_input:
        # 사용자 메시지 즉시 화면에 표시
        with chat_container:
            with st.chat_message("user"):
                st.markdown(user_input)
        
        # AI 응답 생성 및 표시
        with chat_container:
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""
                
                # AI 답변 받아오기
                response = st.session_state.chat_session.send_message(user_input, stream=True)
                for chunk in response:
                    full_response += chunk.text
                    message_placeholder.markdown(full_response + "▌")
                message_placeholder.markdown(full_response)