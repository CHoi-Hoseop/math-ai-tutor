import streamlit as st
import google.generativeai as genai
import numpy as np
import matplotlib.pyplot as plt
import edge_tts
import asyncio
import io

# 1. 페이지 기본 설정
st.set_page_config(page_title="문화고 2-5 AI 튜터", page_icon="🤖", layout="wide")
st.title("🤖 [문화고 2학년 5반] 삼차함수 그래프의 비밀을 찾아라!")
st.markdown("AI 튜터에게 수학적 용어로 질문을 던져 삼차함수에 숨겨진 **기하학적 비율 관계**를 찾아내세요.")
st.markdown("---")

# --- [음성 가이드 영역 (자연스러운 여성 목소리 '선희' 적용)] ---
st.markdown("### 🎧 AI 튜터 이용 가이드 (순서대로 재생 버튼을 눌러주세요)")

# 비동기 Edge TTS 음성 생성 및 재생 함수
def play_audio_guide(text):
    async def _generate_audio():
        # ko-KR-SunHiNeural: 마이크로소프트의 자연스러운 한국어 여성 목소리
        communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        return audio_bytes
    
    # Streamlit에서 안전하게 실행하기 위한 처리
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    audio_data = loop.run_until_complete(_generate_audio())
    loop.close()
    
    st.audio(audio_data, format='audio/mp3', autoplay=True)

btn_col1, btn_col2, btn_col3 = st.columns(3)

with btn_col1:
    if st.button("▶ 1단계: 미션 브리핑 듣기"):
        guide_text = "문화고 2학년 5반 여러분, 환영합니다. 오늘 여러분의 미션은 삼차함수 그래프 속에 숨겨진 놀라운 거리 비율을 스스로 찾아내는 것입니다. 먼저 화면 왼쪽을 보세요. 위쪽의 삼차함수와 아래쪽의 도함수 그래프를 위아래로 훑어보며, 세로 점선이 어떤 의미를 가지는지 관찰해 보세요."
        play_audio_guide(guide_text)

with btn_col2:
    if st.button("▶ 2단계: AI와 스무고개 시작하기"):
        guide_text = "관찰이 끝났다면, 이제 오른쪽 AI 튜터와 대결할 차례입니다! AI는 정답을 절대 알려주지 않습니다. 극댓값, 극솟값, 대칭축, 변곡점 같은 정확한 수학 용어를 써서 압박 질문을 던져야만 단서를 줍니다. 첫 질문이 막막하다면, '이 삼차함수의 극댓값과 극솟값의 x좌표는 뭐야?'라고 물어보며 대화를 시작해 보세요. 자, 지금 바로 채팅창에 여러분의 첫 번째 프롬프트를 입력하고 엔터를 쳐보세요!"
        play_audio_guide(guide_text)

with btn_col3:
    if st.button("▶ 3단계: 수학적 증명 도전하기"):
        guide_text = "결정적인 비율의 비밀을 알아냈나요? 정말 훌륭합니다! 하지만 눈으로 본 것을 진짜 수학이라고 할 순 없겠죠. 이제 책상 위의 활동지 3단계로 넘어가세요. 여러분이 발견한 그 규칙이 식에서도 항상 성립하는지, 도함수를 이용해 논리적으로 증명해 봅시다."
        play_audio_guide(guide_text)

st.markdown("---")

# 2. Gemini API 설정 (이하 기존 코드 그대로 유지)
API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=API_KEY)
# ... (아래로 쭈욱 기존 코드 유지)

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
    model_name="gemini-3.8-flash",
    system_instruction=system_instruction
)

# 세션 상태에 대화 기록 저장
if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(history=[])

# 4. 화면 레이아웃 분할
col1, col2 = st.columns([1, 1])

# 좌측: 수학 그래프 시각화 영역 (삼차함수 & 도함수)
with col1:
    st.subheader("📈 탐구용 그래프")
    st.markdown("위쪽은 함수 $f(x)$, 아래쪽은 도함수 $f'(x)$입니다. 세로 점선을 따라 두 그래프의 관계를 관찰해 보세요.")
    
    x = np.linspace(-2.5, 2.5, 400)
    y = x**3 - 3*x       
    dy = 3*x**2 - 3      
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 7))
    plt.subplots_adjust(hspace=0.2) 
    
    # --- [상단 그래프] ---
    ax1.plot(x, y, label="$f(x) = x^3 - 3x$", color="#1f77b4", linewidth=2)
    ax1.spines['left'].set_position('zero')
    ax1.spines['bottom'].set_position('zero')
    ax1.spines['right'].set_color('none')
    ax1.spines['top'].set_color('none')
    
    # x축 눈금 (0은 글씨 숨김)
    xticks = np.arange(-2, 3, 1)
    ax1.set_xticks(xticks)
    ax1.set_xticklabels([str(i) if i != 0 else '' for i in xticks])
    
    # y축 눈금 (0은 글씨 숨김)
    yticks1 = np.arange(-4, 5, 1)
    ax1.set_yticks(yticks1)
    ax1.set_yticklabels([str(i) if i != 0 else '' for i in yticks1])
    
    ax1.set_xlim(-2.5, 2.5)
    ax1.set_ylim(-4.5, 4.5)
    
    # 교과서 스타일 원점(O) 추가
    ax1.text(-0.2, -0.4, 'O', fontsize=12, fontstyle='italic')
    
    ax1.axhline(2, color='red', alpha=0.4, linestyle=':')
    ax1.axhline(-2, color='blue', alpha=0.4, linestyle=':')
    ax1.grid(True, alpha=0.3, linestyle='--')
    ax1.legend(loc='upper left')
    
    # --- [하단 그래프] ---
    ax2.plot(x, dy, label="$f'(x) = 3x^2 - 3$", color="#ff7f0e", linewidth=2)
    ax2.spines['left'].set_position('zero')
    ax2.spines['bottom'].set_position('zero')
    ax2.spines['right'].set_color('none')
    ax2.spines['top'].set_color('none')
    
    # x축 눈금 (0은 글씨 숨김)
    ax2.set_xticks(xticks)
    ax2.set_xticklabels([str(i) if i != 0 else '' for i in xticks])
    
    # y축 눈금 (0은 글씨 숨김)
    yticks2 = np.arange(-4, 10, 2)
    ax2.set_yticks(yticks2)
    ax2.set_yticklabels([str(i) if i != 0 else '' for i in yticks2])
    
    ax2.set_xlim(-2.5, 2.5) 
    ax2.set_ylim(-4.5, 9.5)
    
    # 교과서 스타일 원점(O) 추가
    ax2.text(-0.2, -0.8, 'O', fontsize=12, fontstyle='italic')
    
    ax2.grid(True, alpha=0.3, linestyle='--')
    ax2.legend(loc='upper center')
    
    # --- [수직 보조선] ---
    for ax in [ax1, ax2]:
        ax.axvline(-1, color='gray', alpha=0.5, linestyle='--')
        ax.axvline(1, color='gray', alpha=0.5, linestyle='--')
        ax.axvline(0, color='gray', alpha=0.5, linestyle='--')
    
    st.pyplot(fig)
    st.info("💡 **Tip:** 아래쪽 이차함수의 '대칭축'이 위치한 $x=0$ 지점은 위쪽 삼차함수에서 어떤 모양(의미)을 가질까요? AI에게 물어보세요!")

# 우측: AI 대화 영역
with col2:
    st.subheader("💬 소크라테스 AI 튜터")
    
    chat_container = st.container(height=550)
    
    with chat_container:
        for message in st.session_state.chat_session.history:
            role = "assistant" if message.role == "model" else "user"
            with st.chat_message(role):
                st.markdown(message.parts[0].text)

    # 첫 질문 시각적 힌트 추가
    st.caption("💡 **어떻게 질문할지 막막하다면? 이렇게 시작해 보세요!**")
    st.info("👉 '이 삼차함수의 극댓값과 극솟값의 x좌표는 각각 뭐야?'")

    # 채팅 입력창
    user_input = st.chat_input("AI에게 질문을 입력하세요")
    
    if user_input:
        with chat_container:
            with st.chat_message("user"):
                st.markdown(user_input)
        
        with chat_container:
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""
                
                # --- [추가된 부분: 로딩 애니메이션] ---
                with st.spinner("🤔 AI 튜터가 2학년 5반 학생의 질문을 분석하고 있습니다..."):
                    response = st.session_state.chat_session.send_message(user_input, stream=True)
                # ------------------------------------
                
                for chunk in response:
                    full_response += chunk.text
                    message_placeholder.markdown(full_response + "▌")
                message_placeholder.markdown(full_response)