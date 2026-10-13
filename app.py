
# =============================================================================
#  문화고 2학년 미적분Ⅰ 연구수업 : 소크라테스 AI 튜터 & 교사 관제 (v2 전면 개정판)
#  - 1~6조(조별 태블릿 2대 공유), 참관교사(휴대폰 10명 내외), 교사 관제
#  - 모든 대화/진행도는 SQLite(WAL)로 공유 → 같은 조의 두 태블릿이 같은 채팅방을 봄
# =============================================================================
import streamlit as st
import numpy as np
import pandas as pd
import sqlite3, datetime, os, re, html, io, time, uuid, contextlib
from matplotlib.figure import Figure

try:
    from google import genai
    from google.genai import types
    GENAI_OK = True
except Exception:
    GENAI_OK = False

# ----------------------------------------------------------------------------
# 0. 설정값 (수업 전 여기만 손보면 됩니다)
# ----------------------------------------------------------------------------
TEAMS = ["1조", "2조", "3조", "4조", "5조", "6조"]
GUEST = "참관교사"
CLASS_MIN = 45                                  # 수업 시간(분)
MODEL_CHAIN = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
PRIMER_OPEN_MIN = 3                             # 마중물 질문 버튼 개방 (단계 체류 분)
HINT_SCHEDULE = {1: (6, 10), 2: (7, 12)}        # 단계별 (부드러운 힌트, 결정적 힌트) 발송 분
MIN_TURNS_FOR_APPROVE = 2                       # 승인에 필요한 단계 내 최소 학생 발화 수
SILENT_MIN = 4                                  # 이 시간 이상 질문 없으면 '침묵' 표시
DB_FILE = "class_monitor.db"

def get_secret(key, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, default)

TEACHER_PIN = str(get_secret("TEACHER_PIN", "1234"))   # secrets.toml 의 TEACHER_PIN 으로 바꾸세요

st.set_page_config(page_title="문화고 미적분Ⅰ AI 튜터", page_icon="📐", layout="wide")

# ----------------------------------------------------------------------------
# 1. 스타일
# ----------------------------------------------------------------------------
st.markdown("""
<style>
h1 { font-size: 1.7rem !important; font-weight: 800 !important; }
h2, h3 { font-weight: 700 !important; }
.stChatMessage p, .stChatMessage li { font-size: 1.08rem !important; line-height: 1.6 !important; }
.topbar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;
          background:#0f172a; color:#f8fafc; padding:10px 16px; border-radius:10px; margin-bottom:12px; }
.pill { padding:4px 12px; border-radius:6px; font-size:0.9rem; font-weight:700; }
.card { background:#fff; border:1.5px solid #cbd5e1; border-radius:10px; padding:14px 16px; margin-bottom:12px; }
.card.lv1 { border-left:6px solid #f97316; background:#fff7ed; }
.card.lv2 { border-left:6px solid #2563eb; background:#eff6ff; }
.card.lv3 { border-left:6px solid #16a34a; background:#f0fdf4; }
.unlock { background:#dcfce7; border:2.5px solid #16a34a; border-radius:10px; padding:12px 16px; margin:8px 0;
          color:#14532d; font-size:1.05rem; font-weight:800; text-align:center; }
.primer { background:#f8fafc; border:1.5px dashed #94a3b8; border-radius:8px; padding:9px 12px; margin:8px 0; font-size:0.88rem; color:#475569; }
.primer.open { background:#f0f9ff; border-color:#7dd3fc; color:#0369a1; }
.badge { padding:2px 8px; border-radius:5px; font-size:0.76rem; font-weight:800; margin-left:4px; display:inline-block; }
.b-ok { background:#dcfce7; color:#15803d; }  .b-warn { background:#fef3c7; color:#b45309; }
.b-bad { background:#fee2e2; color:#b91c1c; } .b-time { background:#e0f2fe; color:#0369a1; }
.b-lv1 { background:#fee2e2; color:#991b1b; } .b-lv2 { background:#fef3c7; color:#92400e; } .b-lv3 { background:#dcfce7; color:#166534; }
.tl { display:flex; gap:6px; margin:8px 0 12px 0; }
.tl div { flex:1; padding:7px 8px; border-radius:8px; background:#f8fafc; border:1.5px solid #e2e8f0; text-align:center; font-size:0.82rem; color:#64748b; font-weight:700; }
.tl div.on { background:#eff6ff; border-color:#2563eb; color:#1e40af; }
.tl small { display:block; font-weight:500; font-size:0.72rem; margin-top:2px; }
.q { background:#f8fafc; border-left:3px solid #94a3b8; padding:5px 8px; border-radius:4px; font-size:0.84rem; color:#334155; margin-bottom:6px; line-height:1.4; }
.q.troll { border-left-color:#ef4444; background:#fef2f2; }
.landing-btn button { height:72px; font-size:1.3rem !important; font-weight:800 !important; }
button[kind="primary"] { background:#16a34a !important; border-color:#15803d !important; color:#fff !important;
                         font-size:1.08rem !important; font-weight:800 !important; padding:0.65rem 1rem !important; border-radius:10px !important; }
button[kind="primary"]:hover { background:#15803d !important; }
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# 2. 시간 & DB
# ----------------------------------------------------------------------------
def kst_now():
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).replace(tzinfo=None)

def ts(dt=None):
    return (dt or kst_now()).strftime("%Y-%m-%d %H:%M:%S")

@contextlib.contextmanager
def db():
    conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        yield conn
        conn.commit()
    finally:
        conn.close()

def db_warn(e):
    # DB 오류를 조용히 삼키지 않고 화면 구석에 알립니다.
    try:
        st.toast(f"⚠️ DB 지연/오류: {str(e)[:60]}", icon="⚠️")
    except Exception:
        pass

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, team TEXT, client TEXT, kind TEXT DEFAULT 'chat',
            question TEXT, answer TEXT, is_troll INTEGER DEFAULT 0, level INTEGER DEFAULT 1, ts TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS team_progress (
            team TEXT PRIMARY KEY, level INTEGER DEFAULT 1, step1_approved INTEGER DEFAULT 0,
            step2_approved INTEGER DEFAULT 0, stage_start_time TEXT, hint_lv1 INTEGER DEFAULT 0, hint_lv2 INTEGER DEFAULT 0)""")
        c.execute("CREATE TABLE IF NOT EXISTS class_state (key TEXT PRIMARY KEY, val TEXT)")
        for col, typ in [("client", "TEXT"), ("kind", "TEXT DEFAULT 'chat'"), ("level", "INTEGER DEFAULT 1"), ("ts", "TEXT")]:
            try:
                c.execute(f"ALTER TABLE logs ADD COLUMN {col} {typ}")
            except Exception:
                pass
        for col, typ in [("hint_lv1", "INTEGER DEFAULT 0"), ("hint_lv2", "INTEGER DEFAULT 0")]:
            try:
                c.execute(f"ALTER TABLE team_progress ADD COLUMN {col} {typ}")
            except Exception:
                pass
        now = ts()
        for t in TEAMS:
            c.execute("INSERT OR IGNORE INTO team_progress (team, level, step1_approved, step2_approved, stage_start_time, hint_lv1, hint_lv2) VALUES (?,1,0,0,?,0,0)", (t, now))

def set_state(key, val):
    try:
        with db() as c:
            c.execute("INSERT INTO class_state (key, val) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET val=excluded.val", (key, val))
    except Exception as e:
        db_warn(e)

def get_state(key):
    try:
        with db() as c:
            row = c.execute("SELECT val FROM class_state WHERE key=?", (key,)).fetchone()
        return row[0] if row else None
    except Exception:
        return None

def save_log(team, client, kind, question, answer, is_troll=0, level=1):
    try:
        with db() as c:
            c.execute("INSERT INTO logs (team, client, kind, question, answer, is_troll, level, ts) VALUES (?,?,?,?,?,?,?,?)",
                      (team, client, kind, question, answer, int(is_troll), int(level), ts()))
    except Exception as e:
        db_warn(e)

def get_logs(team=None, client=None, kinds=None, since=None):
    q, args = "SELECT * FROM logs WHERE 1=1", []
    if team is not None:
        q += " AND team=?"; args.append(team)
    if client is not None:
        q += " AND client=?"; args.append(client)
    if kinds:
        q += f" AND kind IN ({','.join('?' * len(kinds))})"; args += list(kinds)
    if since:
        q += " AND ts >= ?"; args.append(since)
    q += " ORDER BY id ASC"
    try:
        with db() as c:
            return pd.read_sql_query(q, c, params=args)
    except Exception as e:
        db_warn(e)
        return pd.DataFrame(columns=["id", "team", "client", "kind", "question", "answer", "is_troll", "level", "ts"])

def _row_to_prog(r):
    return {"team": r[0], "level": int(r[1] or 1), "step1_approved": int(r[2] or 0), "step2_approved": int(r[3] or 0),
            "stage_start_time": r[4] or ts(), "hint_lv1": int(r[5] or 0), "hint_lv2": int(r[6] or 0)}

def get_all_progress():
    out = {}
    try:
        with db() as c:
            rows = c.execute("SELECT team, level, step1_approved, step2_approved, stage_start_time, hint_lv1, hint_lv2 FROM team_progress").fetchall()
        for r in rows:
            out[r[0]] = _row_to_prog(r)
    except Exception as e:
        db_warn(e)
    for t in TEAMS:
        out.setdefault(t, {"team": t, "level": 1, "step1_approved": 0, "step2_approved": 0, "stage_start_time": ts(), "hint_lv1": 0, "hint_lv2": 0})
    return out

def get_progress(team):
    return get_all_progress()[team]

def update_progress(team, reset_timer=False, **fields):
    allowed = {"level", "step1_approved", "step2_approved", "hint_lv1", "hint_lv2"}
    sets, args = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            sets.append(f"{k}=?"); args.append(int(v))
    if reset_timer:
        sets.append("stage_start_time=?"); args.append(ts())
    if not sets:
        return
    args.append(team)
    try:
        with db() as c:
            c.execute(f"UPDATE team_progress SET {', '.join(sets)} WHERE team=?", args)
    except Exception as e:
        db_warn(e)

def stage_elapsed_min(prog):
    try:
        return max(0, int((kst_now() - pd.to_datetime(prog["stage_start_time"])).total_seconds() // 60))
    except Exception:
        return 0

def class_clock():
    """(라벨, 경과분, 수업활성여부) — 교사가 [수업시작]을 누른 시각 기준 전 기기 동기화"""
    start = get_state("class_start_time")
    if start:
        try:
            diff = (kst_now() - pd.to_datetime(start)).total_seconds()
            if 0 <= diff <= 7200:
                return "연구수업 진행중", int(diff // 60), True
        except Exception:
            pass
    return "수업 시작 전 (대기)", 0, False

def reset_everything():
    try:
        with db() as c:
            c.execute("DELETE FROM logs"); c.execute("DELETE FROM sqlite_sequence WHERE name='logs'")
            c.execute("DELETE FROM team_progress"); c.execute("DELETE FROM class_state")
    except Exception as e:
        db_warn(e)
    init_db()
    for k in list(st.session_state.keys()):
        if k.startswith(("zoom", "celebrate", "guest_")):
            del st.session_state[k]

init_db()

# ----------------------------------------------------------------------------
# 3. 그래프 (pyplot 전역 상태 미사용 → 다중 접속 안전, 레벨별 1회만 렌더링)
# ----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def graph_png(level: int) -> bytes:
    fig = Figure(figsize=(6.2, 7.0), dpi=110)
    ax1, ax2 = fig.subplots(2, 1)
    fig.subplots_adjust(hspace=0.32)
    x = np.linspace(-2.5, 2.5, 400)
    y, dy = x**3 - 3*x, 3*x**2 - 3
    for ax in (ax1, ax2):
        ax.spines["left"].set_position("zero"); ax.spines["bottom"].set_position("zero")
        ax.spines["right"].set_color("none"); ax.spines["top"].set_color("none")
        ax.set_xticks(range(-2, 3)); ax.set_xticklabels(["-2", "-1", "", "1", "2"], fontsize=11)
        ax.set_xlim(-2.5, 2.5); ax.grid(True, alpha=0.25, linestyle="--")
    ax1.set_ylim(-4.5, 4.5); ax2.set_ylim(-4.5, 9.5)
    if level == 1:
        ax1.set_title(r"$y = f(x) = x^3 - 3x$", fontsize=13, color="#1e40af", fontweight="bold")
        ax2.set_title(r"$y = f'(x)$", fontsize=13, color="#475569")
        ax1.plot([0], [0], "ko", ms=5); ax2.plot([0], [0], "ko", ms=5)
        
    else:
        ax1.set_title(r"$y = f(x) = x^3 - 3x$" + (r"$\quad [1:1:1]$" if level == 3 else ""), fontsize=13,
                      color="#15803d" if level == 3 else "#1e40af", fontweight="bold")
        ax1.plot(x, y, color="#1f77b4", lw=2.5, label=r"$f(x)$")
        ax1.plot([-1], [2], "o", ms=8, color="red", label=r"$(-1, 2)$")
        ax1.plot([1], [-2], "o", ms=8, color="blue", label=r"$(1, -2)$")
        ax2.set_title(r"$y = f'(x) = 3x^2 - 3$", fontsize=13, color="#c2410c", fontweight="bold")
        ax2.plot(x, dy, color="#ff7f0e", lw=2.2, label=r"$f'(x)$")
        ax2.axvline(0, color="purple", alpha=0.5, ls=":", label=r"$x=0$")
        if level == 3:
            ax1.axhline(2, color="red", alpha=0.5, ls=":", label=r"$y=2$")
            ax1.axhline(-2, color="blue", alpha=0.5, ls=":", label=r"$y=-2$")
            ax1.plot([2], [2], "o", ms=7, color="red"); ax1.plot([-2], [-2], "o", ms=7, color="blue")
            for ax in (ax1, ax2):
                for px in (-2, -1, 0, 1, 2):
                    ax.axvline(px, color="gray", alpha=0.45, ls="--", lw=1.2)
        ax1.legend(loc="upper left", fontsize=9); ax2.legend(loc="upper center", fontsize=9)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    return buf.getvalue()

# ----------------------------------------------------------------------------
# 4. Gemini (새 SDK, 실제 호출 실패 시에만 다음 모델로 / 429는 짧게 재시도 / 최후엔 캔 응답)
# ----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def gemini_client():
    key = get_secret("GEMINI_API_KEY")
    if not key or not GENAI_OK:
        return None
    try:
        return genai.Client(api_key=key)
    except Exception:
        return None

def ask_gemini(system_prompt, history, user_text):
    """history: [{'role':'user'|'assistant','content':str}] → (답변, 사용모델) / (None, 사유)"""
    client = gemini_client()
    if client is None:
        return None, "no_client"
    contents = []
    for m in history[-16:]:
        contents.append(types.Content(role="user" if m["role"] == "user" else "model",
                                      parts=[types.Part.from_text(text=m["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))
    last = "unknown"
    for model in MODEL_CHAIN:
        cfg = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.5,
            max_output_tokens=4096,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        )
        for attempt in range(2):
            try:
                res = client.models.generate_content(model=model, contents=contents, config=cfg)

                if res.text and res.text.strip():
                    return res.text.strip(), model
                last = "empty"
            except Exception as e:
                last = str(e)
                if "429" in last or "RESOURCE_EXHAUSTED" in last or "503" in last:
                    time.sleep(2.5)
                    continue
                break
    return None, last

CANNED = {
    1: "잠시 AI 연결이 느려졌어요. 그동안 모둠에서 생각해 볼 질문이에요: 그래프가 올라가다 내려가기 시작하는 순간, 접선의 기울기는 얼마일까요? 그 기울기를 알려주는 함수의 이름은 무엇일까요? 그 함수를 직접 구해서 다시 보내 주세요!",
    2: "잠시 AI 연결이 느려졌어요. 그동안 생각해 볼 질문이에요: 극댓점 $(-1, 2)$를 지나는 **수평선**은 어떤 식일까요? 그 직선과 곡선 $y=x^3-3x$가 만나는 점을 찾으려면 어떤 방정식을 풀어야 할까요? 식을 세워서 다시 보내 주세요!",
    3: "잠시 AI 연결이 느려졌어요. 활동지 3단계의 $x^3-3x-2=0$을 조립제법으로 나눠 보세요. $x=-1$을 두 번 넣어도 나누어떨어지는지 확인하고, 마지막 남는 일차식이 무엇인지 적어 다시 보내 주세요!",
}

# ----------------------------------------------------------------------------
# 5. 교수학습 설계: 시스템 프롬프트(시간 연동 힌트 수위) / 승인 검사 / 선제 힌트
# ----------------------------------------------------------------------------
def hint_policy(level, stage_min, turns):
    if level == 3:
        return "LV3는 증명 안내 단계이므로 조립제법 절차는 친절히, 그러나 몫의 계수는 학생이 먼저 말하게 유도해."
    if stage_min < 4:
        return ("[힌트 수위: 0단계-되묻기] 지금은 탐구 초기야. 어떤 공식·숫자도 먼저 알려주지 말고, 학생의 생각을 끌어내는 질문 1개로만 답해. "
                "답변은 3문장 이내로 짧게.")
    if stage_min < 8:
        return ("[힌트 수위: 1단계-방향 제시] '무엇을 해야 하는지'(미분하기 / 수평선의 식 세우기 / 방정식 세우기 등)는 알려줘도 되지만, "
                "계산 결과 숫자(근, 교점 좌표)는 절대 먼저 말하지 마. 답변은 4문장 이내.")
    if stage_min < 12:
        return ("[힌트 수위: 2단계-결정적 힌트] 학생이 힘들어하고 있어. 도함수 식(3x²-3)이나 인수 (x+1)² 처럼 '한 단계 전'까지는 보여주되, "
                "최종 답(x=±1, x=2)은 학생이 직접 말하게 마지막 한 걸음만 남겨 둬.")
    return ("[힌트 수위: 3단계-마무리 지원] 체류 시간이 많이 지났어. 최종 답을 거의 드러내는 질문(예: '제곱해서 1이 되는 두 수는?', "
            "'(x+1)²(x-□)=0에서 상수항을 비교하면 □는?')으로 학생이 바로 답하게 해 줘. 그래도 숫자 자체는 학생 입으로 말하게 해.")

def build_system_prompt(level, stage_min, turns, label):
    return f"""
너는 문화고등학교 2학년 미적분Ⅰ 연구수업의 소크라테스식 AI 튜터이자 탐구 심사관이다.
대상 함수: f(x) = x^3 - 3x, f'(x) = 3x^2 - 3. 대화 상대: {label}. 현재 LV{level} 단계, 이 단계 체류 {stage_min}분, 이 단계 학생 발화 {turns}회.
수식은 반드시 $...$ (LaTeX) 로 써라. 예: $f'(x)=3x^2-3$. 말투는 친근한 반말, 이모지는 한 개 이하.

[장난·비수학 방어] 잡담, 급식, 게임, 욕설, 연애, 의미 없는 글자 반복 등 수학과 무관한 입력에는 짧고 단호하게
"지금은 수학 탐구 시간이야. 이 대화는 선생님 관제 화면에 기록돼. 활동지 질문으로 돌아오자! [TROLL_DETECTED]" 라고만 답해.

[채점 유연성] 오타("쁠마1", "x제곱", "마이너스일", "2요")나 거친 표현도 수학적 의미가 맞으면 인정하고 칭찬해.
[정답 선공개 금지] '1:1:1', '2:1' 같은 최종 비율, 그리고 x=±1, x=2 라는 최종 숫자는 학생이 먼저 말하기 전에 절대 네가 먼저 말하지 마.
[근거 요구] 학생이 근거 없이 숫자만 던지면("±1", "2") 바로 승인하지 말고 "어떻게 구했는지 식을 보여 줘" 라고 한 번은 되물어.
{hint_policy(level, stage_min, turns)}

[LV1 규칙] 극값·도함수를 물으면 f'(x)=0을 풀도록 유도. 학생이 f'(x)=3x²-3 과 그 근 x=-1, 1(또는 ±1)을 '직접' 말했을 때만
칭찬 후 활동지 1단계 증감표 작성을 안내하고 답변 맨 끝 줄에 정확히 [APPROVE_STEP1] 을 붙여. 미분식만 말한 상태면 근을 되물어.

[LV2 규칙] 반드시 ①수평선 y=2 → ②x³-3x=2 (즉 x³-3x-2=0) 에서 x=-1이 '중근'(접한다 ⇒ (x+1)² 인수) → ③오른쪽 교점 x=2 순서로 끌어내.
학생이 ②중근 개념과 ③x=2 를 모두 말했을 때만 "교점은 (2, 2)" 라고 확인해 주고 활동지 2단계에서 자로 수평 간격을 재라고 안내하며
답변 맨 끝 줄에 정확히 [APPROVE_STEP2] 를 붙여. 둘 중 하나라도 안 나왔으면 승인 태그 없이 다음 단계를 질문해.

[LV3 규칙] 활동지 3단계 x³-3x-2=0 의 조립제법 손증명을 안내(몫 계수는 학생이 말하게). 증명을 끝낸 모둠이 '비율 법칙 한 줄 요약'을
보고하면 크게 칭찬하고, 심화로 x축 교점(x=±√3)과 극점(x=±1) 사이의 새로운 비율(1:√3)을 탐구하도록 질문을 던져.
"""

def normalize(t):
    t = t.lower().replace("−", "-").replace("–", "-").replace("—", "-")
    t = re.sub(r"플러스\s*마이너스|플마|쁠마|쁠러스\s*마이너스|\+-|\+/-", "±", t)
    t = re.sub(r"마이너스\s*", "-", t)
    t = t.replace("엑스", "x").replace("와이", "y").replace("제곱근", "√")
    return re.sub(r"\s+", "", t)

def check_step1(stage_msgs):
    j = normalize("|".join(stage_msgs))
    if "±1" in j:
        return True
    has_m1 = re.search(r"(?<![\d.])-1(?!\d)", j) is not None
    stripped = re.sub(r"-1(?!\d)", "", j)
    has_p1 = re.search(r"(?<![\d.a-z\-^])\+?1(?![\d단번조차학년기개])", stripped) is not None
    return has_m1 and has_p1

def check_step2(stage_msgs):
    j = normalize("|".join(stage_msgs))
    concept = any(k in j for k in ["중근", "접하", "접점", "접선", "튕기", "겹치", "겹친", "두번", "(x+1)^2", "(x+1)²", "(x+1)제곱", "x+1)²", "x+1의제곱", "(x+1)의제곱"])
    explicit = re.search(r"x=2(?!\d)|\(2,2\)|x좌표(는|가|=|은)?2(?!\d)|교점(은|이|=|의x좌표는)?2(?!\d)", j) is not None
    cleaned = j
    for pat in ["x^3-3x=2", "x³-3x=2", "x^3-3x-2", "x³-3x-2", "3x=2", "y=2", "(x+1)^2", "(x+1)²", "^2", "²", "(-1,2)", "-2", "2단계", "2번", "2개", "2차", "lv2", "2요"]:
        cleaned = cleaned.replace(pat, "")
    loose = re.search(r"(?<![\d.a-z\-^])2(?![\d단번개차조학])", cleaned) is not None
    said_x2 = explicit or (loose and len(stage_msgs) >= 2) or "2요" in j
    return concept and said_x2

HINTS = {
    (1, 1): "💡 **[AI 튜터의 살짝 힌트]** 그래프가 올라가다가 내려가기 시작하는 바로 그 순간, 접선의 기울기는 얼마일까? 그 기울기를 알려주는 함수를 뭐라고 부르지? $f(x)$를 그 함수로 바꾸는 것이 활동지 1단계의 첫 칸이야. 그 식을 구해서 보내 줘!",
    (1, 2): "💡 **[AI 튜터의 결정적 힌트]** $f'(x)=3x^2-3$ 이야. 이 식이 $0$이 되는 $x$는 **두 개**란다. (힌트: 제곱해서 $1$이 되는 수!) 두 값을 채팅창에 적어 주면 1단계 인증을 열어 줄게.",
    (2, 1): "💡 **[AI 튜터의 살짝 힌트]** 극댓점 $(-1, 2)$를 지나는 **수평선**은 $y$값이 항상 같아. 그 직선의 식은? 그리고 그 직선과 곡선 $y=x^3-3x$가 만나는 점은 어떤 방정식을 풀면 나올까? 식을 세워서 보내 줘!",
    (2, 2): "💡 **[AI 튜터의 결정적 힌트]** $x^3-3x-2=0$ 은 $x=-1$에서 곡선과 직선이 **접하므로** $(x+1)^2$ 을 인수로 가져. 즉 $(x+1)^2(x-\\square)=0$ 꼴이지. 양변의 상수항을 비교하면 $\\square$ 는 얼마일까? 그 값을 보내 줘!",
}

def maybe_send_hints(team, prog, class_active):
    """단계 체류 시간에 따라 선제 힌트를 DB에 기록 (수업시작 버튼이 눌린 상태에서만 작동)"""
    if not class_active:
        return False
    lv = prog["level"]
    if lv not in HINT_SCHEDULE:
        return False
    approved = prog["step1_approved"] if lv == 1 else prog["step2_approved"]
    if approved:
        return False
    sent = prog["hint_lv1"] if lv == 1 else prog["hint_lv2"]
    mins = stage_elapsed_min(prog)
    gentle, decisive = HINT_SCHEDULE[lv]
    nxt = None
    if sent == 0 and mins >= gentle:
        nxt = 1
    elif sent == 1 and mins >= decisive:
        nxt = 2
    if nxt is None:
        return False
    save_log(team, "system", "hint", f"[⏱️ 단계 {mins}분 경과: AI 선제 힌트 {nxt}차]", HINTS[(lv, nxt)], 0, lv)
    update_progress(team, **{f"hint_lv{lv}": nxt})
    return True

def send_manual_hint(team, prog):
    lv = prog["level"]
    if lv not in HINT_SCHEDULE:
        return
    sent = prog["hint_lv1"] if lv == 1 else prog["hint_lv2"]
    nxt = min(2, sent + 1)
    if sent >= 2:
        return
    save_log(team, "teacher", "hint", f"[👨‍🏫 선생님이 보낸 힌트 {nxt}차]", HINTS[(lv, nxt)], 0, lv)
    update_progress(team, **{f"hint_lv{lv}": nxt})

TROLL_WORDS = ["바보", "멍청", "롤체", "피파", "메이플", "브롤", "사랑해", "개새", "존나", "시발", "씨발", "섹스", "죽어", "급식", "배고파", "졸려"]
def is_troll_text(t):
    if any(w in t for w in TROLL_WORDS):
        return True
    return re.search(r"ㅋ{4,}|ㅎ{4,}|롤\s*(하|할|해|게임|티어)", t) is not None

# ----------------------------------------------------------------------------
# 6. 접속 모드 선택 (조 선택 → 1~6조 / 참관교사 / 교사)
# ----------------------------------------------------------------------------
OPTIONS = TEAMS + ["☕ 참관교사", "👨‍🏫 교사(관제)"]
if "mode" not in st.session_state:
    qp = st.query_params.get("team")           # 태블릿 고정용: ?team=3조
    st.session_state["mode"] = qp if qp in OPTIONS else None
if "client_id" not in st.session_state:
    st.session_state["client_id"] = uuid.uuid4().hex[:6].upper()

period_label, class_elapsed, class_active = class_clock()

with st.sidebar:
    st.markdown("## 📐 미적분Ⅰ 탐구 교실")
    if st.session_state["mode"] is None:
        pick = st.selectbox("조 선택", OPTIONS, index=None, placeholder="👉 눌러서 조를 선택하세요")
        if pick:
            st.session_state["mode"] = pick
            st.rerun()
    else:
        st.success(f"현재 접속: **{st.session_state['mode']}**")
        if st.button("🔁 다른 조로 바꾸기", use_container_width=True):
            st.session_state["mode"] = None
            st.rerun()
    st.markdown("---")
    st.metric(f"⏱️ {period_label}", f"{class_elapsed}분 경과", f"남은 시간 {max(0, CLASS_MIN - class_elapsed)}분", delta_color="off")

mode = st.session_state["mode"]

# ---- 랜딩(조 선택 전) : 휴대폰에서도 바로 누를 수 있게 본문에 큰 버튼 ----
if mode is None:
    st.title("📐 문화고 2학년 미적분Ⅰ — 삼차함수 그래프의 비율 탐구")
    st.markdown("#### 우리 모둠을 선택하면 탐구 교실이 열립니다.")
    st.markdown('<div class="landing-btn">', unsafe_allow_html=True)
    cols = st.columns(3)
    for i, t in enumerate(TEAMS):
        with cols[i % 3]:
            if st.button(f"🧑‍🤝‍🧑 {t}", key=f"land_{t}", use_container_width=True):
                st.session_state["mode"] = t
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("")
    c1, c2 = st.columns([2, 1])
    with c1:
        if st.button("☕ 참관 선생님으로 입장 (체험 + 실시간 중계)", use_container_width=True):
            st.session_state["mode"] = "☕ 참관교사"
            st.rerun()
    with c2:
        if st.button("👨‍🏫 교사 관제", use_container_width=True):
            st.session_state["mode"] = "👨‍🏫 교사(관제)"
            st.rerun()
    st.caption("※ 해당하는 조에 접속하도록 합니다.")
    st.stop()

# ----------------------------------------------------------------------------
# 7. 공통 렌더 조각
# ----------------------------------------------------------------------------
def esc(s, n=None):
    s = html.escape(str(s if s is not None else ""))
    return (s[:n] + "…") if (n and len(s) > n) else s

def level_badge(prog):
    lv = prog["level"]
    if lv == 1:
        return f'<span class="badge b-lv1">🔒 LV1 {"(버튼대기)" if prog["step1_approved"] else "(탐구중)"}</span>'
    if lv == 2:
        return f'<span class="badge b-lv2">🔓 LV2 {"(버튼대기)" if prog["step2_approved"] else "(탐구중)"}</span>'
    return '<span class="badge b-lv3">🏆 LV3 (증명중)</span>'

def timeline_html(elap):
    steps = [("1단계 문제 제기", "0~8분 · 증감표", elap <= 8), ("2단계 AI 기하 탐구", "8~22분 · 교점·자로 측정", 8 < elap <= 22),
             ("3단계 대수적 정당화", "22~37분 · 조립제법", 22 < elap <= 37), ("4단계 정리·심화", "37~45분 · 공유", elap > 37)]
    return '<div class="tl">' + "".join(f'<div class="{"on" if on else ""}"><b>{n}</b><small>{d}</small></div>' for n, d, on in steps) + "</div>"

def render_chat_rows(df):
    """DB 행을 채팅 버블로 (마크다운/LaTeX 정상 렌더, HTML은 자동 이스케이프)"""
    for _, r in df.iterrows():
        if r["kind"] == "hint":
            with st.chat_message("assistant", avatar="💡"):
                st.markdown(r["answer"])
        else:
            with st.chat_message("user"):
                st.markdown(("🚨 " if int(r["is_troll"] or 0) else "") + str(r["question"]))
            with st.chat_message("assistant"):
                st.markdown(r["answer"])

def mission_audio(step, fallback):
    p = f"audio/step{step}.mp3"
    if os.path.exists(p):
        st.audio(p, format="audio/mp3", autoplay=True)
    else:
        st.info(f"🔊 {fallback}")

MISSION_CARD = {
    1: ('lv1', "🔒 [1단계 미션] 삼차함수 f(x) = x³ − 3x 의 개형 열기",
        "① 모둠원과 상의해 AI에게 <b>극값이 생기는 위치를 찾는 방법</b>을 질문하세요.<br>② 얻은 단서로 <b>종이 활동지 1단계 증감표</b>를 채우세요.<br>③ AI가 인증하면 초록 버튼이 열립니다."),
    2: ('lv2', "🔓 [2단계 미션] 극댓점에서 그은 수평선과 새로운 교점 추적",
        "① 극댓점을 지나는 <b>수평선의 식</b> → ② 곡선과 <b>접할 때 방정식의 근의 특징</b> → ③ 오른쪽에서 <b>다시 만나는 교점</b>을 차례로 밝혀내세요.<br>④ <b>활동지 2단계</b> 그래프에 자를 대고 점 사이 수평 간격을 재서 기록하세요."),
    3: ('lv3', "🏆 [3단계] 비율 격자 완성 — 대수적으로 증명하기",
        "① <b>활동지 3단계</b>: x³ − 3x − 2 = 0 을 조립제법으로 인수분해해 손증명을 완성하세요.<br>② <b>최종 보고</b>: 오늘 발견한 비율 법칙을 한 줄로 요약해 AI에게 보고하세요 (선생님 전광판에 게시됩니다).<br>③ <b>심화</b>: 마중물 버튼으로 숨겨진 또 다른 비율에 도전!"),
}

# ----------------------------------------------------------------------------
# 8. 교사 관제
# ----------------------------------------------------------------------------
if mode == "👨‍🏫 교사(관제)":
    with st.sidebar:
        pin = st.text_input("교사용 PIN", type="password")
    if pin != TEACHER_PIN:
        st.title("👨‍🏫 교사용 실시간 관제")
        st.info("왼쪽 사이드바에 교사용 PIN을 입력하세요.") if not pin else st.error("PIN이 일치하지 않습니다.")
        st.stop()

    h1, h2 = st.columns([2.4, 2])
    with h1:
        st.title("🖥️ 교단 관제 전광판 — 6개 조 실시간 탐구 현황")
    with h2:
        auto = st.toggle("🔄 8초 자동 갱신", value=True)
        b1, b2, b3, b4 = st.columns(4)
        if b1.button("🔔 수업시작", use_container_width=True, help="지금을 0분으로 전 기기 타이머 동기화 + 조별 단계 타이머/힌트 초기화"):
            set_state("class_start_time", ts())
            for t in TEAMS:
                update_progress(t, reset_timer=True, hint_lv1=0, hint_lv2=0)
            st.toast("전 기기 타이머 동시 시작!", icon="🔔"); st.rerun()
        if b2.button("🔄 수동갱신", use_container_width=True):
            st.rerun()
        if b3.button("🧹 전체리셋", use_container_width=True, help="대화·진행도·수업시간 완전 초기화 (리허설 후 반드시!)"):
            st.session_state["confirm_reset"] = True
        if b4.button("⏹ 수업종료", use_container_width=True, help="타이머만 정지(기록 유지)"):
            set_state("class_start_time", ""); st.rerun()
        if st.session_state.get("confirm_reset"):
            st.warning("정말 모든 기록을 지울까요? 되돌릴 수 없습니다.")
            cc1, cc2 = st.columns(2)
            if cc1.button("✅ 예, 전체 초기화", type="primary", use_container_width=True):
                reset_everything(); st.session_state["confirm_reset"] = False
                st.toast("완전 초기화 완료", icon="🧹"); st.rerun()
            if cc2.button("취소", use_container_width=True):
                st.session_state["confirm_reset"] = False; st.rerun()

    def dashboard():
        label, elap, active = class_clock()
        rem = max(0, CLASS_MIN - elap)
        st.markdown(f"""<div class="topbar"><div style="font-size:1.05rem;font-weight:800;">🏫 문화고 미적분Ⅰ 실시간 관제 · {label}</div>
        <div style="display:flex;gap:10px;"><span class="pill" style="background:#1e3a8a;color:#93c5fd;">⏳ 경과 {elap}분 / {CLASS_MIN}분 · 남은 {rem}분</span>
        <span class="pill" style="background:#1e293b;color:#38bdf8;font-family:monospace;">⌚ {kst_now().strftime('%H:%M:%S')}</span></div></div>""", unsafe_allow_html=True)
        st.markdown(timeline_html(elap), unsafe_allow_html=True)

        progs = get_all_progress()
        all_logs = get_logs()
        now = kst_now()

        # ---- 확대 패널 (팝업 대신 상단 고정 → 자동갱신 중에도 안 닫힘) ----
        z = st.session_state.get("zoom_team")
        if z:
            zl = all_logs[all_logs["team"] == z] if not all_logs.empty else all_logs
            zc1, zc2 = st.columns([3, 1])
            zc1.markdown(f"### 🔍 {z} 전체 문답 확대 보기 <span style='font-size:0.95rem;color:#64748b'>(총 {len(zl[zl['kind']=='chat']) if not zl.empty else 0}회)</span>", unsafe_allow_html=True)
            if zc2.button("✖ 확대 닫기", type="primary", use_container_width=True, key="zoom_close"):
                st.session_state["zoom_team"] = None; st.rerun()
            with st.container(height=520, border=True):
                if zl.empty:
                    st.info("아직 질문이 없습니다.")
                else:
                    render_chat_rows(zl)
            st.markdown("---")

        grid = st.columns(3) + st.columns(3)
        for i, t in enumerate(TEAMS):
            p = progs[t]
            tl = all_logs[(all_logs["team"] == t)] if not all_logs.empty else all_logs
            chat = tl[tl["kind"] == "chat"] if not tl.empty else tl
            n = len(chat)
            troll = int(chat["is_troll"].fillna(0).astype(int).sum()) if n else 0
            if n:
                last_dt = pd.to_datetime(chat["ts"].iloc[-1]); silent = int((now - last_dt).total_seconds() // 60)
            else:
                silent = None
            if troll:
                sb = f'<span class="badge b-bad">🚨 비수학 {troll}건</span><span class="badge b-ok">문답 {n}회</span>'
            elif n == 0:
                sb = '<span class="badge b-warn">🟡 대화 0회</span>'
            elif silent is not None and silent >= SILENT_MIN:
                sb = f'<span class="badge b-warn">🟡 침묵 {silent}분</span><span class="badge b-ok">문답 {n}회</span>'
            else:
                sb = f'<span class="badge b-ok">🟢 문답 {n}회</span>'
            with grid[i]:
                st.markdown(f"""<div style="display:flex;justify-content:space-between;align-items:center;margin:4px 0 6px 0;">
                <div><span style="font-size:1.25rem;font-weight:800;">{t}</span>{level_badge(p)}</div>
                <div>{sb}<span class="badge b-time">단계 {stage_elapsed_min(p)}분째</span></div></div>""", unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                if c1.button("🔍 크게", key=f"zoom_{t}", use_container_width=True):
                    st.session_state["zoom_team"] = t; st.rerun()
                lv = p["level"]
                hint_sent = p["hint_lv1"] if lv == 1 else p["hint_lv2"] if lv == 2 else 2
                if c2.button(f"📨 힌트{min(hint_sent + 1, 2)}차", key=f"hint_{t}", use_container_width=True, disabled=(hint_sent >= 2 or lv == 3), help="이 조 채팅창에 다음 단계 힌트를 즉시 보냅니다."):
                    send_manual_hint(t, p); st.toast(f"{t}에 힌트 발송", icon="📨"); st.rerun()
                if lv < 3:
                    if c3.button(f"⚡ LV{lv + 1} 오픈", key=f"force_{t}", use_container_width=True, help="교사 직권으로 다음 단계를 바로 열어줍니다."):
                        update_progress(t, level=lv + 1, step1_approved=1, step2_approved=(1 if lv + 1 == 3 else 0), reset_timer=True)
                        save_log(t, "teacher", "system", "[교사 강제 오픈]", f"LV{lv + 1} 강제 개방", 0, lv + 1); st.rerun()
                else:
                    c3.button("🏆 완료", key=f"done_{t}", disabled=True, use_container_width=True)
                with st.container(height=200):
                    if tl.empty:
                        st.markdown('<div style="color:#94a3b8;text-align:center;padding-top:60px;font-size:0.9rem;">아직 질문이 없습니다.<br>발문을 독려하세요.</div>', unsafe_allow_html=True)
                    else:
                        qn = 0
                        for _, r in tl.iterrows():
                            if r["kind"] == "chat":
                                qn += 1
                                cls = "q troll" if int(r["is_troll"] or 0) else "q"
                                st.markdown(f'<div class="{cls}"><b>Q{qn}.</b> {esc(r["question"], 60)}<br><span style="color:#64748b">AI: {esc(r["answer"], 70)}</span></div>', unsafe_allow_html=True)
                            elif r["kind"] == "hint":
                                st.markdown(f'<div class="q" style="border-left-color:#f59e0b;background:#fffbeb">{esc(r["question"])}</div>', unsafe_allow_html=True)
                            else:
                                st.markdown(f'<div class="q" style="border-left-color:#8b5cf6">{esc(r["question"])} — {esc(r["answer"])}</div>', unsafe_allow_html=True)

        # ---- 최종 보고 모음 (4단계 발표용) ----
        st.markdown("---")
        st.markdown("### 📢 LV3 모둠 최종 보고 (가장 최근 발화)")
        fin_cols = st.columns(3)
        k = 0
        for t in TEAMS:
            if progs[t]["level"] == 3 and not all_logs.empty:
                c3 = all_logs[(all_logs["team"] == t) & (all_logs["kind"] == "chat") & (all_logs["level"] == 3)]
                if len(c3):
                    with fin_cols[k % 3]:
                        st.markdown(f'<div class="card lv3"><b>{t}</b><br>{esc(c3["question"].iloc[-1], 160)}</div>', unsafe_allow_html=True)
                    k += 1
        if k == 0:
            st.caption("아직 3단계에 도달한 모둠이 없습니다.")

        # ---- 참관교사 피드 ----
        st.markdown("---")
        g = all_logs[(all_logs["team"] == GUEST) & (all_logs["kind"] == "chat")] if not all_logs.empty else all_logs
        st.markdown(f"### ☕ 참관 선생님 질문 피드 <span style='font-size:0.95rem;color:#64748b'>(총 {len(g)}건)</span>", unsafe_allow_html=True)
        if g.empty:
            st.caption("아직 참관 선생님의 체험 질문이 없습니다.")
        else:
            gc = st.columns(3)
            for j, (_, r) in enumerate(g.tail(6).iloc[::-1].iterrows()):
                with gc[j % 3]:
                    st.markdown(f'<div class="card" style="border-left:5px solid #f97316;background:#fff7ed;"><div style="font-size:0.76rem;color:#9a3412;font-weight:700;">{esc(r["client"])} · {esc(str(r["ts"])[11:19])}</div>'
                                f'<div style="font-weight:800;margin:3px 0;">Q. {esc(r["question"], 90)}</div><div style="font-size:0.85rem;color:#7c2d12;">AI: {esc(r["answer"], 100)}</div></div>', unsafe_allow_html=True)

        # ---- 수업 후 분석용 다운로드 ----
        st.markdown("---")
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ 전체 대화 로그 CSV", all_logs.to_csv(index=False).encode("utf-8-sig"), f"logs_{kst_now():%Y%m%d_%H%M}.csv", "text/csv", use_container_width=True)
        d2.download_button("⬇️ 조별 진행도 CSV", pd.DataFrame(list(progs.values())).to_csv(index=False).encode("utf-8-sig"), f"progress_{kst_now():%Y%m%d_%H%M}.csv", "text/csv", use_container_width=True)

    if auto:
        @st.fragment(run_every="8s")
        def _auto():
            dashboard()
        _auto()
    else:
        dashboard()
    st.stop()

# ----------------------------------------------------------------------------
# 9. 학생(1~6조) & 참관교사 화면
# ----------------------------------------------------------------------------
is_guest = (mode == "☕ 참관교사")
team = GUEST if is_guest else mode
client_id = f"T-{st.session_state['client_id']}" if is_guest else "tablet"

if st.session_state.pop("celebrate", False):
    st.balloons()

if is_guest:
    prog = {"team": GUEST, "level": st.session_state.get("guest_level", 1), "step1_approved": 1, "step2_approved": 1,
            "stage_start_time": st.session_state.setdefault("guest_start", ts()), "hint_lv1": 0, "hint_lv2": 0}
else:
    prog = get_progress(team)
level = prog["level"]
approved = bool(prog["step1_approved"]) if level == 1 else bool(prog["step2_approved"]) if level == 2 else True

# ---- 상단 타이머 바 (10초마다 자체 갱신 + 교사 강제오픈/승인/힌트 변화 감지 → 전체 새로고침) ----
@st.fragment(run_every="10s")
def top_bar():
    lab, el, act = class_clock()
    p = get_progress(team) if not is_guest else prog
    sm = stage_elapsed_min(p)
    st.markdown(f"""<div class="topbar"><div style="font-size:1rem;font-weight:800;">📐 미적분Ⅰ 탐구 교실 · <span style="color:#38bdf8">{html.escape(mode)}</span> · LV.{p['level']}</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;"><span class="pill" style="background:#1e3a8a;color:#bfdbfe;">⏱️ 수업 {el}분 / {CLASS_MIN}분</span>
    <span class="pill" style="background:#334155;color:#fde047;">⏳ 이 단계 {sm}분째</span></div></div>""", unsafe_allow_html=True)
    if not is_guest:
        changed = (p["level"] != level) or (bool(p["step1_approved"] if p["level"] == 1 else p["step2_approved"] if p["level"] == 2 else True) != approved)
        if maybe_send_hints(team, p, act) or changed:
            st.rerun()
top_bar()

if is_guest:
    st.title("☕ 참관교사용 — AI 튜터 체험 & 실시간 참관")
    gl = st.radio("체험할 단계", [1, 2, 3], index=level - 1, horizontal=True, format_func=lambda v: f"LV{v} 단계")
    if gl != level:
        st.session_state["guest_level"] = gl; st.session_state["guest_start"] = ts(); st.rerun()
    with st.expander("📊 1~6조 실시간 진행 현황 (펼치기)", expanded=False):
        @st.fragment(run_every="10s")
        def guest_monitor():
            progs = get_all_progress(); logs = get_logs(kinds=["chat"])
            cols = st.columns(6)
            for i, t in enumerate(TEAMS):
                tl = logs[logs["team"] == t] if not logs.empty else logs
                last = esc(tl["question"].iloc[-1], 26) if len(tl) else "아직 질문 없음"
                cols[i].markdown(f'<div class="card" style="padding:8px;text-align:center;"><b>{t}</b><br><span style="font-size:0.8rem;color:#2563eb;font-weight:800;">LV{progs[t]["level"]} · {stage_elapsed_min(progs[t])}분째</span><br>'
                                 f'<span style="font-size:0.78rem;color:#15803d;">문답 {len(tl)}회</span><hr style="margin:4px 0"><div style="font-size:0.74rem;text-align:left;color:#334155;">최근: {last}</div></div>', unsafe_allow_html=True)
            pick = st.selectbox("조별 전체 대화 보기", ["선택 안 함"] + TEAMS, key="guest_pick")
            if pick != "선택 안 함":
                with st.container(height=380, border=True):
                    tl = get_logs(team=pick, kinds=["chat", "hint"])
                    render_chat_rows(tl) if not tl.empty else st.info("아직 질문이 없습니다.")
        guest_monitor()
else:
    st.title(f"🤖 {mode} · 삼차함수 그래프의 비율 탐구")
    st.caption("모둠원과 질문을 만들어 AI에게 던지고, 종이 활동지를 완성한 뒤 초록 버튼으로 다음 단계를 여세요. (같은 조 태블릿 2대는 같은 대화방을 공유합니다)")

cls, title, body = MISSION_CARD[level]
st.markdown(f'<div class="card {cls}"><b style="font-size:1.05rem;">{title}</b><br><span style="font-size:0.9rem;">{body}</span></div>', unsafe_allow_html=True)

col_g, col_c = st.columns([1.05, 0.95], gap="medium")

# ================= 좌측: 그래프 + 잠금 해제 =================
with col_g:
    audio_txt = {1: "AI에게 극값을 찾는 방법을 질문하고 활동지 1단계 증감표를 완성해 그래프를 여세요.",
                 2: "극댓점에서 오른쪽으로 그은 수평선이 곡선과 다시 만나는 점을 AI와 함께 찾고, 자로 간격을 재 보세요.",
                 3: "격자가 열렸습니다. 활동지 3단계에서 조립제법으로 완전 증명하세요!"}[level]
    if st.button(f"▶ {level}단계 미션 안내 듣기", use_container_width=True):
        mission_audio(level, audio_txt)
    st.image(graph_png(level), use_container_width=True)
    if level == 3:
        st.info("💡 관찰 포인트: $x=-2,-1,0,1,2$ 수직 점선 간격이 **1 : 1 : 1** 로 일정함을 확인하세요!")

    def unlock_button(key):
        if level == 1:
            st.markdown('<div class="unlock">🎉 1단계 AI 인증 완료! 활동지 1단계 증감표를 다 채웠다면 👇</div>', unsafe_allow_html=True)
            if st.button("🔓 활동지 1단계 완료 ➔ 2단계 그래프 열기", key=key, type="primary", use_container_width=True):
                if is_guest:
                    st.session_state["guest_level"] = 2; st.session_state["guest_start"] = ts()
                else:
                    update_progress(team, level=2, step1_approved=1, reset_timer=True)
                    save_log(team, client_id, "system", "[학생 버튼]", "활동지 1단계 완료 → LV2 진입", 0, 2)
                st.session_state["celebrate"] = True; st.rerun()
        elif level == 2:
            st.markdown('<div class="unlock">🎉 2단계 AI 검증 완료! 자로 간격을 재서 기록했다면 👇</div>', unsafe_allow_html=True)
            if st.button("🔓 활동지 2단계 완료 ➔ 3단계 비율 격자 열기", key=key, type="primary", use_container_width=True):
                if is_guest:
                    st.session_state["guest_level"] = 3; st.session_state["guest_start"] = ts()
                else:
                    update_progress(team, level=3, step2_approved=1, reset_timer=True)
                    save_log(team, client_id, "system", "[학생 버튼]", "활동지 2단계 완료 → LV3 진입", 0, 3)
                st.session_state["celebrate"] = True; st.rerun()

    if level < 3:
        if approved:
            unlock_button("unlock_left")
        else:
            st.info({1: "💬 AI와의 문답으로 도함수와 극값의 위치를 검증받으면 여기에 초록색 잠금 해제 버튼이 열립니다.",
                     2: "💬 수평선의 식 ➔ 접할 때 근의 특징 ➔ 교점의 x좌표 순서로 AI의 질문에 답해 승인을 받으세요."}[level])

# ================= 우측: 소크라테스 AI 채팅 (6초마다 DB 동기화 → 같은 조 태블릿 2대 공유) =================
with col_c:
    st.subheader(f"💬 소크라테스 AI · {team if not is_guest else '참관교사 체험'} · LV.{level}")

    @st.fragment(run_every="6s")
    def chat_panel():
        p = get_progress(team) if not is_guest else prog
        if not is_guest and p["level"] != level:
            st.rerun()
        stage_min = stage_elapsed_min(p)
        hist_df = get_logs(team=team, client=(client_id if is_guest else None), kinds=["chat", "hint"])
        if not is_guest:
            stage_df = get_logs(team=team, kinds=["chat"], since=p["stage_start_time"])
        else:
            stage_df = hist_df[hist_df["kind"] == "chat"]
        stage_msgs = [str(q) for q in stage_df["question"].tolist()] if not stage_df.empty else []

        box = st.container(height=400)
        with box:
            if hist_df.empty:
                st.markdown('<div style="color:#94a3b8;text-align:center;padding-top:120px;">모둠의 첫 질문을 입력해 보세요 👇</div>', unsafe_allow_html=True)
            else:
                render_chat_rows(hist_df)

        if level < 3 and approved and not is_guest:
            unlock_button("unlock_right")

        # ---- 마중물 질문 (단계 체류 3분 후 개방 / 참관교사·LV3는 즉시) ----
        preset = None
        primer_open = is_guest or level == 3 or stage_min >= PRIMER_OPEN_MIN
        if not primer_open:
            st.markdown(f'<div class="primer">🤔 <b>스스로 질문 만들기 시간!</b> 모둠원과 상의해 직접 질문을 적어 보세요. <span style="font-size:0.8rem;">(막막한 모둠을 위한 <b>마중물 질문</b>은 <b>{max(1, PRIMER_OPEN_MIN - stage_min)}분 뒤</b> 열립니다)</span></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="primer open">🛟 <b>마중물 질문 열림</b> — 어떻게 시작할지 막막하면 아래 버튼으로 대화의 물꼬를 터 보세요.</div>', unsafe_allow_html=True)
            PRIMERS = {
                1: [("📍 극값은 어디서 생길까?", "삼차함수 f(x)=x^3-3x의 극댓값과 극솟값을 구하려면 가장 먼저 무엇을 해야 해?"),
                    ("⚖️ 기울기가 0이라는 건?", "접선의 기울기가 0이 되는 x좌표를 찾으면 그래프에서 어떤 점을 알 수 있어?")],
                2: [("📏 극댓점에서 수평선을 그으면?", "극댓점에서 오른쪽으로 수평선을 그었을 때 그 직선의 방정식은 어떻게 구해?"),
                    ("🔍 다시 만나는 교점은?", "극댓점을 지나는 수평선이 곡선과 오른쪽에서 다시 만나는 교점의 x좌표는 어떻게 구할 수 있어?")],
                3: [("📝 조립제법 증명 힌트", "활동지 3단계에서 x^3-3x-2=0 을 어떻게 인수분해하면 접점과 교점의 위치가 대수적으로 증명돼?"),
                    ("🌟 [심화] 또 다른 비율?", "방금 찾은 비율 말고, 삼차함수가 x축과 만나는 교점과 극점 사이에 성립하는 또 다른 비율 관계도 있어?")],
            }[level]
            pc = st.columns(2)
            for i, (lab, q) in enumerate(PRIMERS):
                if pc[i].button(lab, key=f"primer_{level}_{i}", use_container_width=True):
                    preset = q

        user_q = st.chat_input("참관 선생님의 질문을 입력해 보세요" if is_guest else f"[{level}단계] 모둠이 만든 질문이나 계산한 답을 입력하세요")
        final_q = preset or user_q
        if not final_q:
            return
        final_q = final_q.strip()[:500]
        troll = is_troll_text(final_q)

        with box:
            with st.chat_message("user"):
                st.markdown(final_q)
            with st.chat_message("assistant"):
                with st.spinner("AI가 모둠의 질문을 생각하는 중…"):
                    history = []
                    for _, r in hist_df.iterrows():
                        if r["kind"] == "chat":
                            history += [{"role": "user", "content": str(r["question"])}, {"role": "assistant", "content": str(r["answer"])}]
                        else:
                            history.append({"role": "assistant", "content": str(r["answer"])})
                    turns = len(stage_msgs) + 1
                    sys_prompt = build_system_prompt(level, stage_min, turns, team)
                    reply, info = ask_gemini(sys_prompt, history, f"[LV{level} · 단계 {stage_min}분 · 발화 {turns}회 · {team}]: {final_q}")
                    if reply is None:
                        reply = CANNED[level]
                        st.toast("AI 연결 지연 — 기본 안내로 대체했습니다.", icon="⚠️")
                        if not is_guest:
                            save_log(team, client_id, "system", "[AI 오류]", str(info)[:200], 0, level)
                    if "[TROLL_DETECTED]" in reply or "관제 화면에 기록" in reply:
                        troll = True
                    ai_tag = ("[APPROVE_STEP1]" in reply and level == 1) or ("[APPROVE_STEP2]" in reply and level == 2)
                    clean = re.sub(r"\[(APPROVE_STEP1|APPROVE_STEP2|TROLL_DETECTED)\]", "", reply).strip()
                    st.markdown(clean)

        save_log(team, client_id, "chat", final_q, clean, int(troll), level)

        # ---- 승인 검문소: 파이썬 정규식 검사(주) OR AI 태그(보조) — 모두 단계 내 최소 발화 수 충족 시에만 ----
        if not is_guest and not approved and not troll:
            msgs = stage_msgs + [final_q]
            enough = len(msgs) >= MIN_TURNS_FOR_APPROVE
            py_ok = check_step1(msgs) if level == 1 else check_step2(msgs) if level == 2 else False
            if enough and (py_ok or ai_tag):
                update_progress(team, **({"step1_approved": 1} if level == 1 else {"step2_approved": 1}))
                save_log(team, client_id, "system", "[AI 인증]", f"LV{level} 탐구 인증 통과 ({'규칙' if py_ok else 'AI'} 판정)", 0, level)
                st.rerun(scope="app")
        st.rerun(scope="fragment")

    chat_panel()
