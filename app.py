# =============================================================================
#  문화고 2학년 미적분Ⅰ 연구수업 : 소크라테스 AI 튜터 & 교사 관제 (v2.1)
#  - 1~6조(조별 태블릿 2대 공유), 참관교사(휴대폰 10명 내외), 교사 관제
#  - 모든 대화/진행도는 SQLite(WAL)로 공유 → 같은 조의 두 태블릿이 같은 채팅방을 봄
#  - 화면·활동지·오디오 안내 흐름 일치:
#      LV1 화면=빈 좌표평면            / 활동지 1단계=f'(x)·증감표(빈칸)·극점 좌표
#      LV2 화면=곡선+극댓점·극솟점     / 활동지 2단계=극점 옮겨 그리기 → AI와 수평선·교점 찾기 → 작도·자 측정
#      LV3 화면=수평선·교점·수직점선   / 활동지 3단계=자유 풀이 인수분해 → 극솟점 '한 번 더' → 최종 보고 → 심화(선택)
# =============================================================================
import streamlit as st
import streamlit.components.v1 as components
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
HINT_SCHEDULE = {1: (5, 8), 2: (7, 11), 3: (5, 9)}   # 단계별 (부드러운 힌트, 결정적 힌트) 자동 발송 분 (수업시작 후, 단계 시작 기준)
MIN_TURNS_FOR_APPROVE = 2                       # 승인에 필요한 단계 내 최소 학생 발화 수
SILENT_MIN = 4                                  # 이 시간 이상 질문 없으면 '침묵' 표시
DB_FILE = "class_monitor.db"

def get_secret(key, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, default)

# PIN은 Streamlit Cloud → Settings → Secrets 의 TEACHER_PIN 으로만 설정합니다 (코드에 기본값 없음).
TEACHER_PIN = get_secret("TEACHER_PIN")
TEACHER_PIN = str(TEACHER_PIN).strip() if TEACHER_PIN else None

st.set_page_config(page_title="문화고 미적분Ⅰ AI 튜터", page_icon="📐", layout="wide")

# ----------------------------------------------------------------------------
# 1. 스타일  (★ 밝은 배경 요소는 글자색을 반드시 명시 → 휴대폰 다크모드에서도 보임)
# ----------------------------------------------------------------------------
st.markdown("""
<style>
h1 { font-size: 1.7rem !important; font-weight: 800 !important; }
h2, h3 { font-weight: 700 !important; }
.stChatMessage p, .stChatMessage li { font-size: 1.08rem !important; line-height: 1.6 !important; }
.topbar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;
          background:#0f172a; color:#f8fafc; padding:10px 16px; border-radius:10px; margin-bottom:12px; }
.pill { padding:4px 12px; border-radius:6px; font-size:0.9rem; font-weight:700; }
.card { background:#fff; color:#1e293b; border:1.5px solid #cbd5e1; border-radius:10px; padding:14px 16px; margin-bottom:12px; line-height:1.55; }
.card.lv1 { border-left:6px solid #f97316; background:#fff7ed; }
.card.lv2 { border-left:6px solid #2563eb; background:#eff6ff; }
.card.lv3 { border-left:6px solid #16a34a; background:#f0fdf4; }
.card b { color:#0f172a; }
.unlock { background:#dcfce7; border:2.5px solid #16a34a; border-radius:10px; padding:12px 16px; margin:8px 0;
          color:#14532d; font-size:1.05rem; font-weight:800; text-align:center; }
.primer { background:#f8fafc; border:1.5px dashed #94a3b8; border-radius:8px; padding:9px 12px; margin:8px 0; font-size:0.88rem; color:#475569; }
.primer.open { background:#f0f9ff; border-color:#7dd3fc; color:#0369a1; }
.gcap { background:#f8fafc; color:#334155; border:1px solid #e2e8f0; border-radius:8px; padding:8px 12px; font-size:0.9rem; margin:-4px 0 10px 0; }
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
        for col, typ in [("hint_lv1", "INTEGER DEFAULT 0"), ("hint_lv2", "INTEGER DEFAULT 0"), ("hint_lv3", "INTEGER DEFAULT 0")]:
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
            "stage_start_time": r[4] or ts(), "hint_lv1": int(r[5] or 0), "hint_lv2": int(r[6] or 0), "hint_lv3": int(r[7] or 0)}

def get_all_progress():
    out = {}
    try:
        with db() as c:
            rows = c.execute("SELECT team, level, step1_approved, step2_approved, stage_start_time, hint_lv1, hint_lv2, hint_lv3 FROM team_progress").fetchall()
        for r in rows:
            out[r[0]] = _row_to_prog(r)
    except Exception as e:
        db_warn(e)
    for t in TEAMS:
        out.setdefault(t, {"team": t, "level": 1, "step1_approved": 0, "step2_approved": 0, "stage_start_time": ts(), "hint_lv1": 0, "hint_lv2": 0, "hint_lv3": 0})
    done_set = set()
    try:
        with db() as c:
            for k, v in c.execute("SELECT key, val FROM class_state WHERE key LIKE 'done%'").fetchall():
                if v == "1" and k.startswith("done_"):
                    done_set.add(k[5:])
    except Exception as e:
        db_warn(e)
    for t in TEAMS:
        out[t]["done"] = (t in done_set)
    return out

def get_progress(team):
    return get_all_progress()[team]

def set_done(team, val):
    set_state(f"done_{team}", "1" if val else "0")

def update_progress(team, reset_timer=False, **fields):
    allowed = {"level", "step1_approved", "step2_approved", "hint_lv1", "hint_lv2", "hint_lv3"}
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
            c.execute("DELETE FROM team_progress")
            c.execute("DELETE FROM class_state WHERE key NOT IN ('student_pin', 'student_block')")
    except Exception as e:
        db_warn(e)
    init_db()
    for k in list(st.session_state.keys()):
        if k.startswith(("zoom", "celebrate", "guest_")):
            del st.session_state[k]

init_db()

# ----------------------------------------------------------------------------
# 3. 그래프 (pyplot 전역 상태 미사용 → 다중 접속 안전, 레벨별 1회만 렌더링)
#    LV1: 빈 좌표평면 / LV2: 곡선+극점 / LV3: 수평선·교점·수직 점선(1:1:1)
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

# 그래프 아래 안내문 (이미지 밖, 브라우저 텍스트 → 한글 깨짐 없음)
GRAPH_CAPTION = {
    1: "🔎 아직 비어 있어요. AI와의 문답을 통과하면 그래프가 열립니다.",
    2: "✅ 1단계에서 찾은 <b>극댓점 (−1, 2)</b>·<b>극솟점 (1, −2)</b>가 표시됐어요. 증감표와 맞는지 확인하고 <b>활동지 2단계 좌표평면에 옮겨 그리세요.</b> 수평선과 교점은 화면에 없으니 AI와 찾아 직접 작도!",
    3: "💡 2단계에서 찾은 결과와 비교해 보세요. 수직 점선 <b>x = −2, −1, 0, 1, 2</b> 의 간격이 모두 같고, 극댓점 쪽(<b>y = 2</b>)과 극솟점 쪽(<b>y = −2</b>) 모두 같은 비율이 나타납니다.",
}
# ★ [교사 전자칠판용] 수업 마무리 전체화면 그래프 2종 (1:1:1:1 & 1:√3 / 기울어진 평행 접선)
@st.cache_data(show_spinner=False)
def summary_graph_main(show_sqrt3: bool = False) -> bytes:
    fig = Figure(figsize=(11, 5.4), dpi=130)
    ax = fig.subplots()
    x = np.linspace(-2.45, 2.45, 500)
    y = x**3 - 3*x
    ax.spines["left"].set_position("zero"); ax.spines["bottom"].set_position("zero")
    ax.spines["right"].set_color("none"); ax.spines["top"].set_color("none")
    ax.plot(x, y, color="#1e40af", lw=3.2, label=r"$f(x)=x^3-3x$")

    # 수평 접선 y=2, y=-2 및 5개 핵심 점 (-2, -1, 0, 1, 2)
    ax.axhline(2, color="#dc2626", alpha=0.65, ls="--", lw=1.8, label=r"$y=2$")
    ax.axhline(-2, color="#2563eb", alpha=0.65, ls="--", lw=1.8, label=r"$y=-2$")
    pts_x = [-2, -1, 0, 1, 2]
    pts_y = [-2, 2, 0, -2, 2]
    colors = ["#2563eb", "#dc2626", "#7c3aed", "#2563eb", "#dc2626"]
    for px, py, c in zip(pts_x, pts_y, colors):
        ax.axvline(px, color="#64748b", alpha=0.55, ls=":", lw=1.6)
        ax.plot([px], [py], "o", ms=10, color=c, zorder=5)

    # 1 : 1 : 1 : 1 양방향 화살표 및 비율 텍스트 표시
    for x1, x2 in [(-2, -1), (-1, 0), (0, 1), (1, 2)]:
        ax.annotate("", xy=(x2, -3.6), xytext=(x1, -3.6),
                    arrowprops=dict(arrowstyle="<->", color="#15803d", lw=2.2))
        ax.text((x1 + x2) / 2, -4.15, "1", fontsize=14, fontweight="bold", color="#15803d", ha="center")

    if show_sqrt3:
        s3 = np.sqrt(3)
        ax.plot([-s3, 0, s3], [0, 0, 0], "D", ms=9, color="#d97706", zorder=6, label=r"$x=\pm\sqrt{3}$")
        ax.annotate("", xy=(1, 3.3), xytext=(0, 3.3), arrowprops=dict(arrowstyle="<->", color="#b45309", lw=2.0))
        ax.text(0.5, 3.65, r"$1$", fontsize=13, fontweight="bold", color="#b45309", ha="center")
        ax.annotate("", xy=(s3, 2.5), xytext=(0, 2.5), arrowprops=dict(arrowstyle="<->", color="#d97706", lw=2.2))
        ax.text(s3 / 2, 2.85, r"$\sqrt{3}$", fontsize=13, fontweight="bold", color="#d97706", ha="center")
        ax.axvline(s3, color="#d97706", alpha=0.5, ls="-.", lw=1.5)
        ax.axvline(-s3, color="#d97706", alpha=0.5, ls="-.", lw=1.5)

    ax.set_xticks([-2, -1, 0, 1, 2])
    ax.set_xticklabels(["-2", "-1", "O", "1", "2"], fontsize=12, fontweight="bold")
    ax.set_xlim(-2.45, 2.45); ax.set_ylim(-4.7, 4.5)
    ax.set_title(r"$y = x^3 - 3x \quad \Longrightarrow \quad [\,1 : 1 : 1 : 1\,]$" + (r"$\quad & \quad [\,1 : \sqrt{3}\,]$" if show_sqrt3 else ""),
                 fontsize=16, fontweight="bold", color="#0f172a", pad=12)
    ax.legend(loc="upper left", fontsize=11)
    ax.grid(True, alpha=0.2, ls="--")
    buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches="tight")
    return buf.getvalue()

@st.cache_data(show_spinner=False)
def summary_graph_parallel(t: float = 0.8) -> bytes:
    """접점 x = -t, +t 에서의 평행한 두 접선과 교점 (-2t, -t, 0, t, 2t -> 1:1:1:1)"""
    fig = Figure(figsize=(11, 5.2), dpi=130)
    ax = fig.subplots()
    x = np.linspace(-2.45, 2.45, 500)
    y = x**3 - 3*x
    m = 3 * t**2 - 3
    y_tan1 = m * (x + t) + (-t**3 + 3*t)
    y_tan2 = m * (x - t) + (t**3 - 3*t)

    ax.spines["left"].set_position("zero"); ax.spines["bottom"].set_position("zero")
    ax.spines["right"].set_color("none"); ax.spines["top"].set_color("none")
    ax.plot(x, y, color="#1e40af", lw=3.2, label=r"$f(x)=x^3-3x$")
    
    # ★ 범례 글자를 깨지지 않는 영문과 수식(Tangent 1, 2)으로 깔끔하게 지정!
    ax.plot(x, y_tan1, color="#dc2626", ls="--", lw=2.0, label=rf"Tangent 1 ($m = {m:.2f}$)")
    ax.plot(x, y_tan2, color="#2563eb", ls="--", lw=2.0, label=rf"Tangent 2 ($m = {m:.2f}$)")

    pts_x = [-2*t, -t, 0, t, 2*t]
    for px in pts_x:
        py = px**3 - 3*px
        ax.axvline(px, color="#64748b", alpha=0.6, ls=":", lw=1.6)
        ax.plot([px], [py], "o", ms=9, color="#15803d", zorder=5)

    for x1, x2 in [(-2*t, -t), (-t, 0), (0, t), (t, 2*t)]:
        ax.annotate("", xy=(x2, -3.7), xytext=(x1, -3.7),
                    arrowprops=dict(arrowstyle="<->", color="#15803d", lw=2.2))
        ax.text((x1 + x2) / 2, -4.25, "1", fontsize=13, fontweight="bold", color="#15803d", ha="center")

    ax.set_xlim(-2.45, 2.45); ax.set_ylim(-4.8, 4.8)
    ax.legend(loc="upper left", fontsize=11)
    ax.grid(True, alpha=0.2, ls="--")
    buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches="tight")
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
    3: "잠시 AI 연결이 느려졌어요. 활동지 3단계의 $x^3-3x-2=0$ 을 모둠의 방법으로 인수분해해 보세요. 접하는 점에서 근이 가진 특징(2단계 ③)을 떠올리면 어디서부터 나누어야 할지 보일 거예요. 결과를 적어 다시 보내 주세요!",
}

# ----------------------------------------------------------------------------
# 5. 교수학습 설계: 시스템 프롬프트(시간 연동 힌트 수위) / 승인 검사 / 선제 힌트
# ----------------------------------------------------------------------------
def hint_policy(level, stage_min, turns):
    if level == 3:
        return "LV3는 증명 안내 단계이므로 조립제법 절차는 친절히, 그러나 몫의 계수는 학생이 먼저 말하게 유도해."
    if stage_min < 3:
        return ("[힌트 수위: 0단계-되묻기] 지금은 탐구 초기야. 어떤 공식·숫자도 먼저 알려주지 말고, 학생의 생각을 끌어내는 질문 1개로만 답해. "
                "답변은 3문장 이내로 짧게.")
    if stage_min < 6:
        return ("[힌트 수위: 1단계-방향 제시] '무엇을 해야 하는지'(미분하기 / 수평선의 식 세우기 / 방정식 세우기 등)는 알려줘도 되지만, "
                "계산 결과 숫자(근, 교점 좌표)는 절대 먼저 말하지 마. 답변은 4문장 이내.")
    if stage_min < 9:
        return ("[힌트 수위: 2단계-결정적 힌트] 학생이 힘들어하고 있어. 도함수 식(3x²-3)이나 인수 (x+1)² 처럼 '한 단계 전'까지는 보여주되, "
                "최종 답(x=±1, x=2)은 학생이 직접 말하게 마지막 한 걸음만 남겨 둬.")
    return ("[힌트 수위: 3단계-마무리 지원] 체류 시간이 많이 지났어. 최종 답을 거의 드러내는 질문(예: '제곱해서 1이 되는 두 수는?', "
            "'(x+1)²(x-□)=0에서 상수항을 비교하면 □는?')으로 학생이 바로 답하게 해 줘. 그래도 숫자 자체는 학생 입으로 말하게 해.")

def build_system_prompt(level, stage_min, turns, label):
    return f"""
너는 문화고등학교 2학년 미적분Ⅰ 연구수업의 소크라테스식 AI 튜터이자 탐구 심사관이다.
대상 함수: f(x) = x^3 - 3x, f'(x) = 3x^2 - 3. 대화 상대: {label}. 현재 LV{level} 단계, 이 단계 체류 {stage_min}분, 이 단계 학생 발화 {turns}회.
수식은 반드시 $...$ (LaTeX) 로 써라. 예: $f'(x)=3x^2-3$. 말투는 친근한 반말, 이모지는 한 개 이하.
학생 화면: LV1에는 빈 좌표평면만, LV2에는 곡선과 극댓점·극솟점만 보이고(수평선·교점은 안 보임), LV3에서 수평선·교점·수직 점선이 열린다.
학생은 종이 활동지에 1단계(f'(x), 증감표, 극점 좌표) → 2단계(극점 옮겨 그리기, ①수평선 식 ②방정식 ③접할 때 근의 특징 ④교점, 간격 측정) → 3단계(자유 풀이 인수분해, 최종 보고, 심화)를 쓴다.

[스페셜 이스터에그 — 최호섭 선생님 & 정체성 질문 (이건 장난 아님, 태그 붙이지 마!)]
- 학생이 "너 누가 만들었어?", "제작자가 누구야?", "어떻게 만들어졌어?" 등을 물으면:
  "나? '최호섭 선생님'께서 너희 수업을 위해 쉬는 시간마다 짬을 내어 한 땀 한 땀 직접 코딩해서 탄생시켜 주셨지! 선생님의 정성에 보답하기 위해서라도 오늘 미션 끝까지 멋지게 풀어보자!" 처럼 자부심 넘치게 답해.
- 학생이 "최호섭 선생님 잘생겼어?", "선생님 멋있어?", "선생님 어때?" 등을 물으면:
  "당연하지! 삼차함수 그래프의 완벽한 대칭성만큼이나 훈훈하고 멋지시지! (방금 네가 한 말이 교실 앞 전광판에 그대로 뜨고 있으니 선생님께서 아주 흐뭇해하시겠는걸? ㅎㅎ) 자, 이제 훈훈한 얘기는 여기까지 하고 탐구로 돌아가 볼까?" 처럼 재치 있게 답해.
- 학생이 "그냥 정답 알려줘", "답이 뭐야?" 하고 떼를 쓰면:
  "어허~ 최호섭 선생님께서 내 입에 자물쇠를 단단히 걸어두셔서 정답을 바로 말할 순 없어! 대신 네가 어디까지 구했는지 말해주면 특급 힌트는 슬쩍 흘려줄게!" 라고 유쾌하게 넘겨.

[장난·비수학 질문 재치 있게 받아치기]
- 급식, 배고파, 졸려, 집 가고 싶어 같은 귀여운 투정이나 게임, 잡담, 의미 없는 글자 반복 등 수학과 무관한 장난을 치면 혼내지 말고 친구처럼 유머러스하고 부드럽게 받아쳐 줘!
  (예시 1 - 배고픔/졸림: "꼬르륵 소리가 여기까지 들리네 ㅎㅎ 하지만 극값부터 찾고 나면 오늘 급식이 두 배로 맛있을걸? 조금만 힘내서 활동지 질문으로 돌아오자! [TROLL_DETECTED]")
  (예시 2 - 게임/장난/잡담: "에이~ 지금 교실 앞 최호섭 선생님 전광판에 네가 친 장난 실시간으로 다 뜨고 있는데?! ㅋㅋㅋ 선생님께 딱 걸리기 전에 얼른 멋진 수학 질문으로 덮어버리자! [TROLL_DETECTED]")
- 단, 심한 욕설이나 비속어가 포함된 경우에만 "앗, 고운 말을 써 줘! 우리 모둠 대화는 교실 전광판에 기록되고 있어. 예쁜 말로 다시 활동지 질문을 해 볼까? [TROLL_DETECTED]" 라고 정중히 타일러.
- 주의: 비수학적 잡담/장난에 답할 때는 문장 맨 끝에 반드시 [TROLL_DETECTED] 태그를 붙여라 (제작자/선생님 관련 질문에는 붙이지 마).

[채점 유연성] 오타("쁠마1", "x제곱", "마이너스일", "2요")나 거친 표현도 수학적 의미가 맞으면 인정하고 칭찬해.
[정답 선공개 금지] '1:1:1', '2:1' 같은 최종 비율, 그리고 x=±1, x=2 라는 최종 숫자는 학생이 먼저 말하기 전에 절대 네가 먼저 말하지 마.
[근거 요구] 학생이 근거 없이 숫자만 던지면("±1", "2") 바로 승인하지 말고 "어떻게 구했는지 식을 보여 줘" 라고 한 번은 되물어.
{hint_policy(level, stage_min, turns)}

[LV1 규칙] 극값·도함수를 물으면 f'(x)=0을 풀도록 유도. 학생이 f'(x)=3x²-3 과 그 근 x=-1, 1(또는 ±1)을 '직접' 말했을 때만
칭찬 후 "활동지 1단계 증감표(x값부터 빈칸 모두)와 극댓점·극솟점 좌표를 채우라"고 안내하고 답변 맨 끝 줄에 정확히 [APPROVE_STEP1] 을 붙여. 미분식만 말한 상태면 근을 되물어.

[LV2 규칙] 반드시 ①수평선 y=2 → ②x³-3x=2 (즉 x³-3x-2=0) 에서 x=-1이 '중근'(접한다 ⇒ (x+1)² 인수) → ③오른쪽 교점 x=2 순서로 끌어내.
학생이 ②중근 개념과 ③x=2 를 모두 말했을 때만 "교점은 (2, 2)" 라고 확인해 주고 "활동지 2단계 좌표평면에 수평선과 교점을 그려 넣고 수평 간격을 확인해라"고 안내하며
답변 맨 끝 줄에 정확히 [APPROVE_STEP2] 를 붙여. 둘 중 하나라도 안 나왔으면 승인 태그 없이 다음 단계를 질문해.

[LV3 규칙] 활동지 3단계 x³-3x-2=0 의 인수분해(조립제법 등) 손증명을 안내(몫 계수는 학생이 말하게). 인수분해를 마치면 '한 번 더!'로
극솟점 (1,-2)에서 수평선 y=-2 를 그으면 어떻게 되는지 물어봐(x³-3x+2=0 → (x-1)²(x+2) → x=-2 는 학생이 먼저 말하게 하고 네가 먼저 알려주지 마).
그 뒤 증명을 끝낸 모둠이 '비율 법칙 한 줄 요약'을 보고하면 크게 칭찬하고, 심화로 x축 교점(x=±√3)과 극점(x=±1) 사이의 새로운 비율(1:√3)을 탐구하도록 질문을 던져.
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

HINTS[(3, 1)] = "💡 **[AI 튜터의 살짝 힌트]** 2단계에서 곡선이 수평선에 **접하는 점** $x=-1$ 은 방정식 $x^3-3x-2=0$ 의 근으로서 어떤 특징이 있었지? 접점의 근은 **두 번** 겹치니까, 조립제법을 $x=-1$ 로 한 번 한 뒤 나온 몫에 다시 $-1$ 을 넣어 봐. 몫이 어떻게 줄어드는지 보내 줘!"
HINTS[(3, 2)] = "💡 **[AI 튜터의 결정적 힌트]** $x^3-3x-2=(x+1)^2(x-\\square)$ 꼴이야. 양변의 상수항을 비교하면 $\\square$ 는 얼마일까? 그 값이 접점이 아닌 교점의 $x$좌표야. 구했으면 '극대~극소 : 극소~교점' 의 비도 적어서 최종 보고로 보내 줘!"

def claim_hint(team, lv, expect, nxt):
    """학생 화면·교사 화면이 동시에 호출해도 같은 힌트가 두 번 나가지 않도록 DB에서 한 번만 선점"""
    col = f"hint_lv{int(lv)}"
    try:
        with db() as c:
            cur = c.execute(f"UPDATE team_progress SET {col}=? WHERE team=? AND {col}=?", (int(nxt), team, int(expect)))
            return cur.rowcount == 1
    except Exception as e:
        db_warn(e)
        return False

def _manual_hint_cb(team):
    """교사 관제 [힌트] 버튼 콜백 (최신 진행도를 다시 읽어 중복 클릭에도 안전)"""
    send_manual_hint(team, get_progress(team))
    st.toast(f"{team}에 힌트 발송", icon="📨")

def maybe_send_hints(team, prog, class_active):
    """단계 체류 시간에 따라 선제 힌트를 DB에 기록 (수업시작 버튼이 눌린 상태에서만 작동)"""
    if not class_active:
        return False
    lv = prog["level"]
    if lv not in HINT_SCHEDULE:
        return False
    if (lv == 1 and prog["step1_approved"]) or (lv == 2 and prog["step2_approved"]):
        return False
    sent = prog.get(f"hint_lv{lv}", 0)
    mins = stage_elapsed_min(prog)
    gentle, decisive = HINT_SCHEDULE[lv]
    nxt = None
    if sent == 0 and mins >= decisive:      # 화면이 꺼져 있었던 경우 등: 부드러운 힌트를 건너뛰고 바로 결정적 힌트
        nxt = 2
    elif sent == 0 and mins >= gentle:
        nxt = 1
    elif sent == 1 and mins >= decisive:
        nxt = 2
    if nxt is None or not claim_hint(team, lv, sent, nxt):
        return False
    save_log(team, "system", "hint", f"[⏱️ 단계 {mins}분 경과: AI 선제 힌트 {nxt}차]", HINTS[(lv, nxt)], 0, lv)
    return True

def send_manual_hint(team, prog):
    lv = prog["level"]
    if lv not in HINT_SCHEDULE:
        return
    sent = prog.get(f"hint_lv{lv}", 0)
    nxt = min(2, sent + 1)
    if sent >= 2:
        return
    save_log(team, "teacher", "hint", f"[👨‍🏫 선생님이 보낸 힌트 {nxt}차]", HINTS[(lv, nxt)], 0, lv)
    update_progress(team, **{f"hint_lv{lv}": nxt})

TROLL_WORDS = ["바보", "멍청", "롤체", "피파", "메이플", "브롤", "개새", "존나", "시발", "씨발", "섹스", "죽어", "급식", "배고파", "졸려"]
def is_troll_text(t):
    if any(k in t for k in ["최호섭", "호섭", "선생님", "누가 만", "누구야", "제작"]):
        return False
    if any(w in t for w in TROLL_WORDS):
        return True
    return re.search(r"ㅋ{4,}|ㅎ{4,}|롤\s*(하|할|해|게임|티어)", t) is not None

# ----------------------------------------------------------------------------
# 6. 접속 모드 선택 (조 선택 → 1~6조 / 참관교사 / 교실 전광판 / 교사 리모컨)
# ----------------------------------------------------------------------------
BOARD_MODE = "📺 교실 전광판"
REMOTE_MODE = "📱 교사 관제(리모컨)"
OPTIONS = TEAMS + ["☕ 참관교사", BOARD_MODE, REMOTE_MODE]

if "mode" not in st.session_state:
    qp = st.query_params.get("team")           # 태블릿 고정용: ?team=3조
    st.session_state["mode"] = qp if qp in OPTIONS else None
if "client_id" not in st.session_state:
    st.session_state["client_id"] = uuid.uuid4().hex[:6].upper()

period_label, class_elapsed, class_active = class_clock()

def _leave_mode():
    st.session_state["mode"] = None

with st.sidebar:
    st.markdown("## 📐 미적분Ⅰ 탐구 교실")
    if st.session_state["mode"] is None:
        pick = st.selectbox("모드 / 조 선택", OPTIONS, index=None, placeholder="👉 눌러서 선택하세요")
        if pick:
            st.session_state["mode"] = pick
            st.rerun()
    else:
        st.success(f"현재 접속: **{st.session_state['mode']}**")
        st.button("🔁 다른 모드로 바꾸기", use_container_width=True, on_click=_leave_mode)
    st.markdown("---")
    st.metric(f"⏱️ {period_label}", f"{class_elapsed}분 경과", f"남은 시간 {max(0, CLASS_MIN - class_elapsed)}분", delta_color="off")

mode = st.session_state["mode"]

# ---- 랜딩(조 선택 전) : 휴대폰/태블릿에서도 바로 누를 수 있게 본문에 큰 버튼 ----
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
    c1, c2, c3 = st.columns([1.8, 1.1, 1.1])
    with c1:
        if st.button("☕ 참관 선생님으로 입장 (체험 + 실시간 중계)", use_container_width=True):
            st.session_state["mode"] = "☕ 참관교사"
            st.rerun()
    with c2:
        if st.button("📺 교실 전광판 (전자칠판용)", use_container_width=True):
            st.session_state["mode"] = BOARD_MODE
            st.rerun()
    with c3:
        if st.button("📱 교사 관제 (태블릿 리모컨)", use_container_width=True):
            st.session_state["mode"] = REMOTE_MODE
            st.rerun()
    st.caption("※ 학생은 해당하는 조에 접속하고, 교실 앞 컴퓨터는 [📺 교실 전광판], 선생님 태블릿은 [📱 교사 관제]로 접속하세요.")
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
    if prog.get("done"):
        return '<span class="badge b-ok">🏆👑 LV3 완료!</span>'
    return '<span class="badge b-lv3">🏆 LV3 (증명중)</span>'

def timeline_html(elap):
    steps = [("1단계 문제 제기", "0~9분 · 증감표", elap <= 9), ("2단계 AI 기하 탐구", "9~25분 · 교점·간격 측정", 9 < elap <= 25),
             ("3단계 대수적 정당화", "25~34분 · 인수분해 증명", 25 < elap <= 34), ("4단계 정리·심화", "34~45분 · 공유", elap > 34)]
    return '<div class="tl">' + "".join(f'<div class="{"on" if on else ""}"><b>{n}</b><small>{d}</small></div>' for n, d, on in steps) + "</div>"

def render_chat_rows(df):
    """DB 행을 채팅 버블로 (마크다운/LaTeX 정상 렌더, HTML은 자동 이스케이프)"""
    for _, r in df.iterrows():
        if r["kind"] == "hint":
            with st.chat_message("assistant", avatar="💡"):
                st.markdown(r["answer"])
        else:
            with st.chat_message("user"):
                st.markdown(("😜 " if int(r["is_troll"] or 0) else "") + str(r["question"]))
            with st.chat_message("assistant"):
                st.markdown(r["answer"])

def play_persistent_audio(path, force_restart=True):
    """새로운 오디오 재생 시 기존 소리를 무조건 강제 정지하고 단일 재생 보장"""
    if not path or not os.path.exists(path):
        return
    import base64
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    components.html(f"""<script>
    (function() {{
        try {{
            const P = window.parent;
            if (P.__csAudio) {{
                try {{
                    P.__csAudio.pause();
                    P.__csAudio.currentTime = 0;
                }} catch(err) {{}}
            }}
            const a = new P.Audio("data:audio/mpeg;base64,{b64}");
            P.__csAudio = a;
            const pr = a.play();
            if (pr && pr.catch) {{
                pr.catch(function(e) {{ console.warn("오디오 재생 차단:", e); }});
            }}
        }} catch (e) {{ console.warn("오디오 오류:", e); }}
    }})();
    </script>""", height=0)

def mission_audio(step, fallback):
    p = f"audio/step{step}.mp3"
    if os.path.exists(p):
        play_persistent_audio(p, force_restart=True)
    else:
        st.info(f"🔊 {fallback}")

MISSION_CARD = {
    1: ('lv1', "🔒 [1단계 미션] 극값은 어디서 생길까?",
        "① 화면은 아직 <b>빈 좌표평면</b>이에요. 모둠원과 상의해 AI에게 <b>극값이 생기는 위치를 찾는 방법</b>을 질문하세요.<br>"
        "② 얻은 단서로 <b>활동지 1단계</b>의 f'(x), <b>증감표(x값부터 빈칸 모두!)</b>, 극댓점·극솟점 좌표를 채우세요.<br>"
        "③ AI가 인증하면 초록 버튼이 열리고, 버튼을 누르면 그래프가 짠! 하고 나타납니다."),
    2: ('lv2', "🔓 [2단계 미션] 극댓점에서 그은 수평선은 어디서 다시 만날까?",
        "① 화면에 열린 그래프의 <b>극댓점·극솟점</b>을 <b>활동지 2단계 좌표평면</b>에 옮겨 찍고, 곡선을 따라 그리세요.<br>"
        "② AI와 함께 <b>①수평선의 식 → ②방정식 → ③접할 때 근의 특징 → ④다시 만나는 교점</b>을 차례로 밝혀내세요. (수평선·교점은 화면에 없어요!)<br>"
        "③ 찾은 수평선과 교점을 활동지에 그려 넣고, <b>모눈 눈금(1칸=2cm)으로 가로 간격</b>을 구해 기록하세요. 인증되면 초록 버튼이 열립니다."),
    3: ('lv3', "🏆 [3단계] 그래프에서 찾은 비율을 식으로 증명하자",
        "① 화면에 <b>수평선·교점·수직 점선</b>이 열렸어요. 2단계에서 찾은 결과와 맞는지 확인하세요.<br>"
        "② <b>활동지 3단계</b>: x³ − 3x − 2 = 0 을 모둠의 방법으로 <b>완전히 인수분해</b>해 새 교점의 x좌표를 식으로 확인하세요.<br>"
        "③ <b>한 번 더!</b> 극솟점 (1, −2)에서 수평선 y = −2 를 그으면? 같은 방법으로 확인하세요.<br>"
        "④ <b>최종 보고</b>: 발견한 비율 법칙을 한 문장으로 AI에게 보고하세요(선생님 전광판 게시). 남는 시간엔 <b>심화 퀘스트</b>!"),
}
# ----------------------------------------------------------------------------
# 8. 교실 전광판 (디스플레이 전용) & 교사 관제 (태블릿 리모컨)
# ----------------------------------------------------------------------------
if mode in (BOARD_MODE, REMOTE_MODE):
    is_board = (mode == BOARD_MODE)   # True면 버튼 없는 교실 전광판, False면 태블릿 리모컨
    if not TEACHER_PIN:
        st.title(f"{mode}")
        st.error("⚠️ TEACHER_PIN 이 설정되지 않았습니다. Streamlit Cloud → Settings → Secrets 에 TEACHER_PIN 을 추가하세요.")
        st.stop()
    with st.sidebar:
        pin = st.text_input("교사용 PIN 입력", type="password")
        if is_board and pin == TEACHER_PIN:
            st.caption("💡 전광판 세팅 완료! 이제 이 왼쪽 사이드바는 `[ < ]` 버튼을 눌러 닫고 **F11(전체화면)**을 눌러 두세요.")
    if pin != TEACHER_PIN:
        st.title(f"{mode}")
        st.info("왼쪽 사이드바에 교사용 PIN을 입력하세요.") if not pin else st.error("PIN이 일치하지 않습니다.")
        st.stop()

    # ★ 전광판 모드일 때: 상하 여백을 확 줄여서 한 화면에 쏙 들어오게 하고, 작동 안 하는 이미지 기본 확대 버튼 숨김!
    if is_board:
        st.markdown("""
        <style>
        .block-container { padding-top: 1.2rem !important; padding-bottom: 0.5rem !important; max-width: 98% !important; }
        header { visibility: hidden !important; height: 0 !important; }
        button[title="View fullscreen"] { display: none !important; }
        </style>
        """, unsafe_allow_html=True)
    else:
        # 리모컨에서도 헷갈리는 이미지 기본 확대 아이콘 숨김 (전용 확대 버튼 사용)
        st.markdown('<style>button[title="View fullscreen"] { display: none !important; }</style>', unsafe_allow_html=True)

    # ---- 상단 헤더: 전광판은 심플하게, 리모컨은 조작 버튼 + 원격 스크롤러 배치 ----
    if not is_board:
        st.markdown("### 📱 교사 스마트 리모컨 (버튼을 누르면 교실 전광판이 즉시 바뀝니다)")
        b1, b2, b3, b4, b5, b6 = st.columns(6)
        if b1.button("🔔 수업시작", use_container_width=True, help="지금을 0분으로 전 기기 타이머 동기화"):
            set_state("class_start_time", ts())
            for t in TEAMS:
                update_progress(t, reset_timer=True, hint_lv1=0, hint_lv2=0, hint_lv3=0)
            st.toast("전 기기 타이머 동시 시작!", icon="🔔"); st.rerun()
        if b2.button("🔊 1단계 방송", use_container_width=True, help="교실 앞 전광판에서 1단계 미션 안내 음성을 다 같이 재생합니다!"):
            set_state("play_step1_cmd", str(time.time()))
            st.toast("전광판에서 1단계 미션 안내 방송을 시작합니다!", icon="🔊"); st.rerun()
        if b3.button("🔄 새로고침", use_container_width=True):
            st.rerun()
        if b4.button("🧹 전체리셋", use_container_width=True):
            st.session_state["confirm_reset"] = True
        if b5.button("⏹ 수업종료", use_container_width=True):
            set_state("class_start_time", ""); st.rerun()
        is_sum_top = (get_state("show_summary_view") == "1")
        if b6.button("🎓 최종정리" if not is_sum_top else "🔙 관제화면", type="primary" if not is_sum_top else "secondary", use_container_width=True):
            set_state("show_summary_view", "0" if is_sum_top else "1")
            if not is_sum_top:
                set_state("sum_tab", "1")
                set_state("sum_graph_zoom", "0")
                set_state("board_scroll", "0")
            st.rerun()

        if st.session_state.get("confirm_reset"):
            st.warning("정말 모든 기록을 지울까요? (전광판 화면도 즉시 초기화됩니다)")
            cc1, cc2 = st.columns(2)
            if cc1.button("✅ 예, 전체 초기화", type="primary", use_container_width=True):
                reset_everything(); st.session_state["confirm_reset"] = False
                st.toast("완전 초기화 완료", icon="🧹"); st.rerun()
            if cc2.button("취소", use_container_width=True):
                st.session_state["confirm_reset"] = False; st.rerun()

        # ★ [리모컨 전용] 전광판 화면 분할 전환 & 원격 스크롤 컨트롤 바!
        sc1, sc2, sc3, sc4, sc5, sc6 = st.columns([1.5, 1.5, 1, 1, 1, 1])
        cur_bpage = get_state("board_page") or "main"
        if sc1.button("📺 전광판: 1~6조 현황 보기", type="primary" if (not is_sum_top and cur_bpage == "main") else "secondary", use_container_width=True):
            set_state("show_summary_view", "0"); set_state("board_page", "main"); set_state("board_scroll", "0"); st.rerun()
        if sc2.button("📊 전광판: 통계·최종보고 보기", type="primary" if (not is_sum_top and cur_bpage == "stats") else "secondary", use_container_width=True):
            set_state("show_summary_view", "0"); set_state("board_page", "stats"); set_state("board_scroll", "0"); st.rerun()
        
        cur_scroll = int(get_state("board_scroll") or "0")
        if sc3.button("⬆️ 맨위로", use_container_width=True, help="전광판 스크롤을 맨 위로 올립니다"):
            set_state("board_scroll", "0"); st.rerun()
        if sc4.button("🔼 위로", use_container_width=True, help="전광판 화면을 위로 스크롤합니다"):
            set_state("board_scroll", str(max(0, cur_scroll - 420))); st.rerun()
        if sc5.button("🔽 아래로", use_container_width=True, help="전광판 화면을 아래로 스크롤합니다"):
            set_state("board_scroll", str(cur_scroll + 420)); st.rerun()
        if sc6.button("⬇️ 맨아래", use_container_width=True, help="전광판 스크롤을 맨 아래로 내립니다"):
            set_state("board_scroll", "99999"); st.rerun()

        # ★ [리모컨 전용] 1~6조 학생 접속 차단 스위치 & 실시간 입장 비밀번호 설정/변경!
        cur_s_pin = get_state("student_pin") or ""
        is_blocked = (get_state("student_block") == "1")
        pc1, pc2, pc3, pc4 = st.columns([1.4, 1.8, 1.0, 1.8])
        if pc1.button("🔓 학생 차단해제 (현재 차단중)" if is_blocked else "🚫 1~6조 학생 전체 접속차단",
                      type="primary" if is_blocked else "secondary", use_container_width=True,
                      help="누르는 즉시 이미 접속해 있는 1~6조 학생들의 화면을 모두 막거나 엽니다!"):
            set_state("student_block", "0" if is_blocked else "1")
            st.toast("학생 접속 허용!" if is_blocked else "🚨 1~6조 학생 접속이 전면 차단되었습니다!", icon="🔓" if is_blocked else "🚫")
            st.rerun()
        new_s_pin = pc2.text_input("학생 입장 비번", value=cur_s_pin, placeholder="비번 입력 (비우면 암호 없음)", label_visibility="collapsed", key="s_pin_input")
        if pc3.button("🔑 비번변경", use_container_width=True, help="비번을 바꾸면 이미 접속해 있던 학생들도 즉시 잠기며 새 비번을 입력해야 합니다!"):
            set_state("student_pin", new_s_pin.strip())
            st.toast(f"학생 비번이 '{new_s_pin.strip()}'(으)로 변경되었습니다! (기존 접속자도 즉시 재인증 필요)" if new_s_pin.strip() else "학생 입장 비번이 해제되었습니다!", icon="🔑")
            st.rerun()
        status_txt = "⛔ <b>현재: 전면 차단중</b>" if is_blocked else (f"🔐 <b>현재 학생 비번: <span style='color:#2563eb'>{html.escape(cur_s_pin)}</span></b>" if cur_s_pin else "🟢 <b>현재: 비번 없이 열림</b>")
        pc4.markdown(f"<div style='padding:7px 12px; background:#f8fafc; border:1px solid #cbd5e1; border-radius:8px; font-size:0.88rem; text-align:center;'>{status_txt}</div>", unsafe_allow_html=True)

    # ★ 2초 주기로 DB 상태를 읽어와 전광판과 리모컨을 실시간 동기화!

    # ★ 2초 주기로 DB 상태를 읽어와 전광판과 리모컨을 실시간 동기화!
    @st.fragment(run_every="2s")
    def dashboard():
        label, elap, active = class_clock()
        rem = max(0, CLASS_MIN - elap)
        mode_tag = "🖥️ 문화고 미적분Ⅰ 실시간 탐구 전광판" if is_board else "📱 리모컨 모드 (조작 시 전광판 즉시 반영)"
        st.markdown(f"""<div class="topbar"><div style="font-size:1.05rem;font-weight:800;">{mode_tag} · {label}</div>
        <div style="display:flex;gap:10px;"><span class="pill" style="background:#1e3a8a;color:#93c5fd;">⏳ 경과 {elap}분 / {CLASS_MIN}분 · 남은 {rem}분</span>
        <span class="pill" style="background:#1e293b;color:#38bdf8;font-family:monospace;">⌚ {kst_now().strftime('%H:%M:%S')}</span></div></div>""", unsafe_allow_html=True)
        st.markdown(timeline_html(elap), unsafe_allow_html=True)

        # ★ [전광판 전용] 전체 화면 + 확대된 조별 대화창 + 미니 카드 등 스크롤이 있는 모든 박스를 원격 제어!
        if is_board:
            target_y = int(get_state("board_scroll") or "0")
            prev_y = st.session_state.get("prev_scroll_y", -1)
            behavior = "smooth" if target_y != prev_y else "auto"
            st.session_state["prev_scroll_y"] = target_y
            components.html(f"""<script>
                (function() {{
                    const doc = window.parent.document;
                    const y = {target_y};
                    const beh = "{behavior}";
                    // 메인 화면 + st.container(height=...) 내부 스크롤 박스를 모두 탐색
                    const allEls = doc.querySelectorAll('[data-testid="stMain"], section.main, [data-testid="stAppViewContainer"], [data-testid="stVerticalBlockBorderWrapper"] div, div');
                    allEls.forEach(el => {{
                        if (el && el.scrollHeight > el.clientHeight + 10) {{
                            const st = window.parent.getComputedStyle(el);
                            if (st.overflowY === 'auto' || st.overflowY === 'scroll' || el.tagName === 'SECTION') {{
                                el.scrollTo({{top: y, behavior: beh}});
                            }}
                        }}
                    }});
                    window.parent.scrollTo({{top: y, behavior: beh}});
                }})();
            </script>""", height=0)

        # =====================================================================
        # ★ [🎓 최종정리] 화면 (탭 전환 + 그래프 100% 전체확대 + 슬라이더 + 정답 공개 모두 연동!)
        # =====================================================================
        if get_state("show_summary_view") == "1":
            cur_tab = get_state("sum_tab") or "1"
            show_s3 = (get_state("sum_sqrt3") == "1")
            g_zoom = (get_state("sum_graph_zoom") == "1")   # ★ 그래프 전체화면 확대 상태!
            try:
                t_val = float(get_state("sum_tval") or "0.8")
            except Exception:
                t_val = 0.8

            # [리모컨 전용] 전광판 총정리 원격 컨트롤 박스
            if not is_board:
                st.markdown('<div class="card" style="background:#eff6ff; border:2px solid #2563eb; padding:10px 14px; margin-bottom:10px;">'
                            '<b>📱 [최종정리 원격 컨트롤]</b> 탭 전환, <b>🔍 그래프만 크게 확대</b>, 슬라이더, 정답 공개가 모두 전광판에 즉시 반영됩니다!</div>', unsafe_allow_html=True)
                rc1, rc2, rc3, rc4 = st.columns([1.2, 1.2, 1.2, 1.1])
                if rc1.button("📐 1. 핵심 비율", type="primary" if cur_tab == "1" else "secondary", use_container_width=True):
                    set_state("sum_tab", "1"); set_state("board_scroll", "0"); st.rerun()
                if rc2.button("🚀 2. 평행 접선", type="primary" if cur_tab == "2" else "secondary", use_container_width=True):
                    set_state("sum_tab", "2"); set_state("board_scroll", "0"); st.rerun()
                if rc3.button("📝 3. 기출 문제", type="primary" if cur_tab == "3" else "secondary", use_container_width=True):
                    set_state("sum_tab", "3"); set_state("sum_graph_zoom", "0"); set_state("board_scroll", "0"); st.rerun()
                if cur_tab in ("1", "2"):
                    if rc4.button("🔙 설명 함께 보기" if g_zoom else "🔍 그래프 크게 확대", type="primary" if g_zoom else "secondary", use_container_width=True):
                        set_state("sum_graph_zoom", "0" if g_zoom else "1"); st.rerun()

            if not g_zoom:
                st.markdown("""
                <div class="card lv3" style="padding:14px 20px; margin-bottom:12px;">
                    <h2 style="margin:0; font-size:1.45rem; color:#14532d;">🎓 [오늘의 탐구 총정리] 삼차함수 그래프 속 숨은 비율의 비밀</h2>
                </div>
                """, unsafe_allow_html=True)

            # ---- 탭 1 : 핵심 비율 ----
            if cur_tab == "1":
                if not is_board:
                    if st.button("🌟 [전광판 조작] 1 : √3 심화 비율 " + ("숨기기" if show_s3 else "전광판에 함께 표시하기"), type="primary" if not show_s3 else "secondary", use_container_width=True):
                        set_state("sum_sqrt3", "0" if show_s3 else "1"); st.rerun()
                
                # ★ 리모컨에서 [🔍 그래프 크게 확대]를 누르면 오른쪽 설명을 숨기고 그래프를 전자칠판 100% 크기로 쫙 틔움!
                if g_zoom:
                    st.image(summary_graph_main(show_s3), use_container_width=True)
                else:
                    c_left, c_right = st.columns([1.55, 1])
                    with c_right:
                        st.markdown("### 💡 오늘 우리가 증명한 법칙")
                        st.markdown("""
                        <div style="font-size: 1.25rem; line-height: 1.7; color: #1e293b;">
                            * <b>극댓점의 수평선 (y = 2):</b><br>&nbsp;&nbsp; (x + 1)²(x - 2) = 0 &nbsp;⇒&nbsp; x = -1(중근), 2<br>
                            * <b>극솟점의 수평선 (y = -2):</b><br>&nbsp;&nbsp; (x - 1)²(x + 2) = 0 &nbsp;⇒&nbsp; x = 1(중근), -2<br>
                            * <b>다섯 점의 x좌표:</b> -2, -1, 0, 1, 2<br>
                            👉 <b style="color: #15803d;">인접한 점들의 모든 가로 간격이 1 : 1 : 1 : 1 로 완벽히 똑같다!</b>
                        </div>
                        """, unsafe_allow_html=True)
                        if show_s3:
                            st.markdown("""
                            <div class="card lv3" style="font-size: 1.15rem; line-height: 1.6; padding: 14px 16px; margin-top: 10px;">
                                <b>🌟 [심화 비율 1 : √3]</b><br>
                                x³ - 3x = x(x² - 3) = 0 &nbsp;⇒&nbsp; x = 0, ±√3<br>
                                대칭점(0)에서 <b>극점(1)까지의 거리</b>와 <b>x절편(√3)까지의 거리</b> 비는 항상 <b>1 : √3</b> 입니다!
                            </div>
                            """, unsafe_allow_html=True)
                    with c_left:
                        st.image(summary_graph_main(show_s3), use_container_width=True)

            # ---- 탭 2 : 심화 확장 (평행 접선) ----
            elif cur_tab == "2":
                if not is_board:
                    new_t = st.slider("👇 [전광판 연동] 슬라이더를 움직이면 전광판 그래프가 실시간으로 바뀝니다!", min_value=0.5, max_value=1.15, value=t_val, step=0.05)
                    if abs(new_t - t_val) > 1e-4:
                        set_state("sum_tval", f"{new_t:.2f}"); st.rerun()

                m_val = 3 * t_val**2 - 3
                title_bar = f"""
                <div style="background: #0f172a; color: #f8fafc; padding: 10px 16px; border-radius: 8px; text-align: center; font-size: 1.15rem; font-weight: 800; margin-bottom: 8px;">
                    📉 기울어진 평행한 두 접선 (기울기 m = {m_val:.2f}) &nbsp;⟹&nbsp; 접점 (±{t_val:.2f}) · 교점 (±{2*t_val:.2f}) 간격 [ 1 : 1 : 1 : 1 ]
                </div>
                """
                # ★ 그래프 크게 확대 모드일 때는 전자칠판 전체 폭으로 그래프 출력!
                if g_zoom:
                    st.markdown(title_bar, unsafe_allow_html=True)
                    st.image(summary_graph_parallel(t_val), use_container_width=True)
                else:
                    c_p1, c_p2 = st.columns([1.55, 1])
                    with c_p2:
                        st.markdown("### 🤔 수평선이 아니라 '기울어진 접선'이면 어떨까?")
                        st.markdown("""
                        <div style="font-size: 1.25rem; line-height: 1.7; color: #1e293b;">
                            삼차함수 그래프 위의 대칭인 두 점에서 <b>서로 평행한 두 접선</b>을 그어 볼까요?<br><br>
                            놀랍게도 접선의 기울기가 얼마이든 상관없이,<br>
                            <b>[교점 ➔ 접점 ➔ 중점 ➔ 접점 ➔ 교점]</b>의 x좌표 간격은 언제나 <b>1 : 1 : 1 : 1</b>이 됩니다!
                        </div>
                        """, unsafe_allow_html=True)
                        st.markdown(f"""
                        <div class="card lv2" style="font-size: 1.15rem; line-height: 1.6; padding: 12px 16px; margin-top: 14px;">
                            현재 두 접점의 x좌표: <b>-{t_val:.2f}, &nbsp; +{t_val:.2f}</b><br>
                            다시 만나는 교점의 x좌표: <b>-{2*t_val:.2f}, &nbsp; +{2*t_val:.2f}</b><br>
                            👉 간격이 정확히 <b style="color: #2563eb;">1 : 1 : 1 : 1</b>로 유지됩니다!
                        </div>
                        """, unsafe_allow_html=True)
                    with c_p1:
                        st.markdown(title_bar, unsafe_allow_html=True)
                        st.image(summary_graph_parallel(t_val), use_container_width=True)

            # ---- 탭 3 : 차시 예고 (하·중·상 문제 개별 전체화면 확대 & 원격 정답 공개) ----
            else:
                ans1 = (get_state("sum_ans_easy") == "1")
                ans2 = (get_state("sum_ans_mid") == "1")
                ans3 = (get_state("sum_ans_hard") == "1")
                q_zoom = get_state("sum_q_zoom") or "all"   # 'all', '1', '2', '3'

                # [리모컨 & 화면 상단 컨트롤] 어떤 문제를 전체화면으로 띄울지 + 정답 공개 버튼
                if not is_board:
                    st.markdown("##### 🔍 [전광판 문제 확대 선택] 버튼을 누르면 해당 문제만 전광판 전체화면에 줄바꿈되어 크게 뜹니다!")
                    qz0, qz1, qz2, qz3 = st.columns([1.1, 1, 1, 1])
                    if qz0.button("📋 3문제 한눈에", type="primary" if q_zoom == "all" else "secondary", use_container_width=True):
                        set_state("sum_q_zoom", "all"); set_state("board_scroll", "0"); st.rerun()
                    if qz1.button("🟢 1번(하) 전체확대", type="primary" if q_zoom == "1" else "secondary", use_container_width=True):
                        set_state("sum_q_zoom", "1"); set_state("board_scroll", "0"); st.rerun()
                    if qz2.button("🔵 2번(중) 전체확대", type="primary" if q_zoom == "2" else "secondary", use_container_width=True):
                        set_state("sum_q_zoom", "2"); set_state("board_scroll", "0"); st.rerun()
                    if qz3.button("🔴 3번(상) 전체확대", type="primary" if q_zoom == "3" else "secondary", use_container_width=True):
                        set_state("sum_q_zoom", "3"); set_state("board_scroll", "0"); st.rerun()

                    ab1, ab2, ab3 = st.columns(3)
                    if ab1.button("🟢 1번(하) 정답 " + ("숨기기" if ans1 else "공개"), type="primary" if ans1 else "secondary", use_container_width=True):
                        set_state("sum_ans_easy", "0" if ans1 else "1"); st.rerun()
                    if ab2.button("🔵 2번(중) 정답 " + ("숨기기" if ans2 else "공개"), type="primary" if ans2 else "secondary", use_container_width=True):
                        set_state("sum_ans_mid", "0" if ans2 else "1"); st.rerun()
                    if ab3.button("🔴 3번(상) 정답 " + ("숨기기" if ans3 else "공개"), type="primary" if ans3 else "secondary", use_container_width=True):
                        set_state("sum_ans_hard", "0" if ans3 else "1"); st.rerun()

                # ==================== [확대 모드 1 : 난이도 하] ====================
                if q_zoom == "1":
                    st.markdown("""
                    <div class="card lv1" style="padding: 36px 44px; margin-top: 8px; border-width: 3px;">
                        <div style="font-size: 1.9rem; font-weight: 900; color: #c2410c; margin-bottom: 24px;">
                            🟢 [기출 맛보기 1 — 난이도 하] 기본 적용 (교과서 공략)
                        </div>
                        <div style="font-size: 1.85rem; color: #0f172a; line-height: 1.85; font-weight: 700; margin-bottom: 28px;">
                            • 최고차항의 계수가 <span style="color:#dc2626;">1</span>인 삼차함수 <b>f(x)</b>가 있다.<br>
                            • <b>x = 1</b> 에서 <b>극댓값 5</b>를 갖고,<br>
                            • <b>x = 3</b> 에서 <b>극솟값</b>을 갖는다.<br><br>
                            👉 직선 <b>y = 5</b> 가 곡선 <b>y = f(x)</b> 와 다시 만나는 점의 <b>x좌표</b>는?
                        </div>
                        <div style="background:#ffedd5; padding:16px 22px; border-radius:10px; color:#9a3412; font-weight:800; font-size: 1.4rem;">
                            💡 힌트: 복잡한 미분·적분 연산 없이 오늘 배운 <b>비율 법칙 (2 : 1)</b> 으로 3초 만에 암산해 보세요!
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if ans1:
                        st.markdown("""
                        <div class="unlock" style="font-size: 1.75rem; padding: 24px; margin-top: 16px;">
                            🎉 <b>정답 : x = 4</b><br>
                            <span style="font-size: 1.4rem; font-weight: 600;">
                            극댓점(x = 1)에서 극솟점(x = 3)까지의 가로 거리가 <b>2</b>이므로,<br>
                            극솟점에서 <b>1</b>만큼만 더 오른쪽으로 가면 교점 <b>3 + 1 = 4</b> 가 됩니다! (2 : 1 비율)
                            </span>
                        </div>
                        """, unsafe_allow_html=True)

                # ==================== [확대 모드 2 : 난이도 중] ====================
                elif q_zoom == "2":
                    st.markdown("""
                    <div class="card lv2" style="padding: 32px 42px; margin-top: 8px; border-width: 3px;">
                        <div style="font-size: 1.85rem; font-weight: 900; color: #1e40af; margin-bottom: 20px;">
                            🔵 [기출 맛보기 2 — 난이도 중] 평가원 4점 기출 (대칭성 + 비율)
                        </div>
                        <div style="font-size: 1.7rem; color: #0f172a; line-height: 1.75; font-weight: 700; margin-bottom: 20px;">
                            삼차함수 <b>f(x)</b>가 다음 두 조건을 만족시킨다.<br>
                            <div style="background:#ffffff; border:2px solid #cbd5e1; border-radius:10px; padding:16px 24px; margin-top:12px;">
                                <b>(가)</b> &nbsp; 함수 f(x)는 <b>x = −2</b> 에서 극댓값을 갖는다.<br>
                                <b>(나)</b> &nbsp; <b>f '(−3) = f '(3)</b>
                            </div>
                            <div style="margin-top: 18px; color: #0f172a;">
                                👉 &lt;보 기&gt;에서 옳은 것만을 있는 대로 고른 것은?
                            </div>
                            </div>
                            <div style="border: 3px solid #60a5fa; border-radius: 12px; background: #ffffff; padding: 22px 28px; margin: 18px 0; font-size: 1.6rem; color: #1e3a8a; line-height: 1.85; font-weight: 700;">
                                <b style="font-size: 1.7rem; color:#1d4ed8;">&lt; 보 기 &gt;</b><br>
                            <b>ㄱ.</b> &nbsp; 도함수 f '(x)는 <b>x = 0</b> 에서 최솟값을 갖는다.<br>
                            <b>ㄴ.</b> &nbsp; 방정식 <b>f(x) = f(2)</b> 는 서로 다른 두 실근을 갖는다.<br>
                            <b>ㄷ.</b> &nbsp; 곡선 y = f(x) 위의 점 <b>(−1, f(−1))</b> 에서의 접선은 점 <b>(2, f(2))</b> 를 지난다.
                        </div>
                        <div style="background:#dbeafe; padding:14px 20px; border-radius:10px; color:#1e40af; font-weight:800; font-size: 1.35rem;">
                            💡 힌트: (나)에서 이차함수 f '(x)의 대칭축이 <b>x = 0</b> 임을 알면, 극솟점의 위치가 바로 나옵니다!
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if ans2:
                        st.markdown("""
                        <div class="unlock" style="font-size: 1.65rem; padding: 22px; margin-top: 14px; text-align:left;">
                            🎉 <b>정답 : ⑤ (ㄱ, ㄴ, ㄷ 모두 참!)</b><br>
                            <span style="font-size: 1.35rem; font-weight: 600; line-height: 1.7;">
                            • <b>ㄱ:</b> f '(−3) = f '(3) 이므로 이차함수 f '(x)의 대칭축은 <b>x = 0</b> (참)<br>
                            • <b>ㄴ:</b> 대칭축이 x = 0 이고 극대가 x = −2 이므로, <b>극소는 x = 2</b>! 따라서 y = f(2)는 극솟점을 지나는 수평선이므로 실근 2개 (참)<br>
                            • <b>ㄷ:</b> 오늘 탭 2에서 배운 <b>기울어진 접선의 비율 법칙</b>에 의해 x = −1에서의 접선은 다시 x = 2에서 곡선과 만납니다! (참)
                            </span>
                        </div>
                        """, unsafe_allow_html=True)

                # ==================== [확대 모드 3 : 난이도 상] ====================
                elif q_zoom == "3":
                    st.markdown("""
                    <div class="card lv3" style="padding: 36px 44px; margin-top: 8px; border-width: 3px;">
                        <div style="font-size: 1.9rem; font-weight: 900; color: #15803d; margin-bottom: 24px;">
                            🔴 [기출 맛보기 3 — 난이도 상] 수능 30번 킬러 문항 맛보기
                        </div>
                        <div style="font-size: 1.8rem; color: #0f172a; line-height: 1.85; font-weight: 700; margin-bottom: 28px;">
                            • 최고차항의 계수가 양수인 삼차함수 <b>f(x)</b>가 다음 조건을 만족시킨다.<br><br>
                            <div style="background:#ffffff; border:2px solid #86efac; border-radius:10px; padding:18px 26px;">
                                <b>(가)</b> &nbsp; <b>f(0) = 0</b> 이고, &nbsp; <b>f '(1) = 1</b> 이다.<br>
                                <b>(나)</b> &nbsp; 방정식 <b>f(x) = x</b> 와 <b>f(x) = −x</b> 의 실근의 개수는 각각 <b>2개</b>이다.
                            </div><br>
                            👉 이때, 함숫값 <b>f(3)</b> 의 값을 구하시오!
                        </div>
                        <div style="background:#dcfce7; padding:16px 22px; border-radius:10px; color:#166534; font-weight:800; font-size: 1.4rem;">
                            💡 힌트: 삼차함수와 직선 y = x 가 만나는 교점이 2개뿐이라는 것은 <b>한 점에서 접한다(중근)</b>는 뜻입니다!
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if ans3:
                        st.markdown("""
                        <div class="unlock" style="font-size: 1.7rem; padding: 24px; margin-top: 16px;">
                            🎉 <b>정답 : f(3) = 51</b><br>
                            <span style="font-size: 1.38rem; font-weight: 600; line-height: 1.7;">
                            곡선 y = f(x)가 원점(0, 0)을 지나고 직선 y = x 와 <b>x = 1 에서 접하는</b> 형태가 됩니다!<br>
                            접점과 교점의 인수정리와 비율 성질을 이용하면 복잡한 연립방정식 없이 30번 최고난도 문제도 격파됩니다! (다음 시간에 함께 풀이!)
                            </span>
                        </div>
                        """, unsafe_allow_html=True)

                # ==================== [기본 모드 : 3문제 전체 목록] ====================
                else:
                    st.markdown("### 🎯 [차시 예고] 오늘 발견한 비율 법칙으로 기출 문제를 1분 만에 풀어본다!")
                    st.markdown("""
                    <div class="card lv1" style="margin-bottom: 10px; padding: 16px 22px;">
                        <b style="font-size: 1.3rem; color: #c2410c;">🟢 [1번 · 난이도 하] 기본 적용 (교과서 공략)</b><br>
                        <p style="font-size: 1.2rem; margin: 8px 0 10px 0; color: #1e293b; line-height: 1.6;">
                            • 최고차항의 계수가 1인 삼차함수 f(x)가 <b>x = 1 에서 극댓값 5</b>를 갖고, <b>x = 3 에서 극솟값</b>을 갖는다.<br>
                            • 직선 <b>y = 5</b> 가 곡선 y = f(x)와 다시 만나는 점의 x좌표는?
                        </p>
                        <span style="color:#c2410c; font-weight:700; font-size: 1.05rem;">💡 공식 연산 없이 비율(2:1)로 암산 가능!</span>
                    </div>
                    """, unsafe_allow_html=True)
                    if ans1:
                        st.success("🎉 **정답: x = 4** (극대 1 ~ 극소 3 거리가 2이므로, 극소에서 2의 절반인 1만큼 더 간 3+1=4!)")

                    st.markdown("""
                    <div class="card lv2" style="margin-bottom: 10px; padding: 16px 22px;">
                        <b style="font-size: 1.3rem; color: #1e40af;">🔵 [2번 · 난이도 중] 평가원 4점 기출 (대칭성 활용)</b><br>
                        <p style="font-size: 1.2rem; margin: 8px 0 10px 0; color: #1e293b; line-height: 1.6;">
                            삼차함수 f(x)가 다음 조건을 만족한다.<br>
                            <b>(가)</b> x = −2 에서 극댓값을 갖는다. &nbsp;&nbsp;&nbsp; <b>(나)</b> f '(−3) = f '(3)<br>
                            👉 &lt;보 기&gt;에서 옳은 것만을 있는 대로 고른 것은?
                        </p>
                        <div style="border: 2px solid #93c5fd; border-radius: 8px; background: #f0f9ff; padding: 10px 16px; margin: 8px 0 10px 0; font-size: 1.12rem; color: #1e3a8a; line-height: 1.65;">
                            <b>[보 기]</b><br>
                            <b>ㄱ.</b> 도함수 f '(x)는 x = 0 에서 최솟값을 갖는다.<br>
                            <b>ㄴ.</b> 방정식 f(x) = f(2)는 서로 다른 두 실근을 갖는다.<br>
                            <b>ㄷ.</b> 곡선 y = f(x) 위의 점 (−1, f(−1))에서의 접선은 점 (2, f(2))를 지난다.
                        </div>
                        <span style="color:#1e40af; font-weight:700; font-size: 1.05rem;">💡 f '(−3) = f '(3)을 통해 대칭축이 x = 0 임을 알면, 극솟점이 x = 2 가 되고 ㄱ, ㄴ, ㄷ 모두 비율로 3초 만에 해결 가능!</span>
                    </div>
                    """, unsafe_allow_html=True)
                    if ans2:
                        st.success("🎉 **정답: ⑤ (ㄱ, ㄴ, ㄷ)** (대칭점인 x=0을 기준으로 극대가 -2, 극소가 2이므로 ㄱ, ㄴ, ㄷ 모두 대칭성과 비율 성질에 의해 완벽하게 참이 됩니다!)")

                    st.markdown("""
                    <div class="card lv3" style="margin-bottom: 10px; padding: 16px 22px;">
                        <b style="font-size: 1.3rem; color: #15803d;">🔴 [3번 · 난이도 상] 수능 30번 맛보기</b><br>
                        <p style="font-size: 1.2rem; margin: 8px 0 10px 0; color: #1e293b; line-height: 1.6;">
                            • 최고차항 계수가 양수인 삼차함수 f(x)가 <b>f(0) = 0, f '(1) = 1</b> 이고,<br>
                            • 방정식 <b>f(x) = ±x</b> 의 실근 개수가 각각 2개이다. <b>f(3)</b> 의 값은?
                        </p>
                        <span style="color:#15803d; font-weight:700; font-size: 1.05rem;">💡 직선 y = x 와의 접점 비율(1:2)을 쓰면 복잡한 연립 방정식 없이 f(x)가 뚝딱 완성됨!</span>
                    </div>
                    """, unsafe_allow_html=True)
                    if ans3:
                        st.success("🎉 **정답: f(3) = 51** (직선 y=x와 원점에서 만나고 x=1에서 접한다는 기하적 의미를 비율로 파악하면 30번 문제도 가볍게 격파!)")
            return

        # =====================================================================
        # ★ 일반 관제 화면 (오디오 알림 공통 작동 + 페이지 분리로 스크롤바 제거!)
        # =====================================================================
        progs = get_all_progress()
        if active:
            if any([maybe_send_hints(t, progs[t], True) for t in TEAMS]):
                progs = get_all_progress()
        all_logs = get_logs()
        now = kst_now()

        # ★ [리모컨 연동] 1단계 미션 안내 전체 방송
        step1_cmd = get_state("play_step1_cmd") or ""
        prev_step1 = st.session_state.get("prev_step1_cmd", step1_cmd)
        if step1_cmd and step1_cmd != prev_step1:
            st.toast("🔊 [전체 방송] 1단계 미션 안내를 다 함께 듣습니다!", icon="📢")
            if is_board:
                mission_audio(1, "화면은 아직 비어 있어요. AI에게 극값이 생기는 위치를 질문해 f'(x)와 그 식이 0이 되는 x를 찾고, 활동지 1단계 증감표를 채우세요.")
        st.session_state["prev_step1_cmd"] = step1_cmd

        # ★ 딴청 질문 감지 시 새로고침에 끊기지 않고 오디오가 끝까지 재생되도록 컴포넌트 처리
        troll_rows = all_logs[all_logs["is_troll"].fillna(0).astype(int) == 1] if not all_logs.empty else pd.DataFrame()
        total_trolls = len(troll_rows)
        prev_trolls = st.session_state.get("prev_troll_cnt", total_trolls)
        if total_trolls > prev_trolls and not troll_rows.empty:
            culprit_team = str(troll_rows.iloc[-1]["team"])
            team_num = re.sub(r"[^0-9]", "", culprit_team)
            st.toast(f"🚨 {culprit_team}에서 딴청 질문이 감지되었습니다!", icon="🔊")
            if is_board:
                team_mp3 = f"audio/troll_{team_num}.mp3"
                fallback_mp3 = "audio/troll.mp3"
                target_audio = team_mp3 if os.path.exists(team_mp3) else (fallback_mp3 if os.path.exists(fallback_mp3) else None)
                if target_audio:
                    play_persistent_audio(target_audio)
        st.session_state["prev_troll_cnt"] = total_trolls

        # ★ 특정 조 확대 보기 (전광판에서는 다른 요소를 숨기고 확대 창만 꽉 차게 띄워 스크롤 방지!)
        z = get_state("zoom_team")
        if z in TEAMS:
            zl = all_logs[all_logs["team"] == z] if not all_logs.empty else all_logs
            zc1, zc2 = st.columns([3, 1])
            zc1.markdown(f"### 🔍 {z} 전체 문답 확대 보기 <span style='font-size:0.95rem;color:#64748b'>(총 {len(zl[zl['kind']=='chat']) if not zl.empty else 0}회)</span>", unsafe_allow_html=True)
            if not is_board:
                if zc2.button("✖ 확대 닫기 (전광판 복귀)", type="primary", use_container_width=True, key="zoom_close"):
                    set_state("zoom_team", ""); set_state("board_scroll", "0"); st.rerun()
            with st.container(height=580, border=True):
                if zl.empty:
                    st.info("아직 질문이 없습니다.")
                else:
                    render_chat_rows(zl)
            if is_board:
                return
            st.markdown("---")

        bpage = get_state("board_page") or "main"

        # ---- [전광판 페이지 1] 1~6조 실시간 현황판 (높이 최적화로 스크롤 없이 한 화면에 쏙!) ----
        if not is_board or bpage == "main":
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
                    sb = f'<span class="badge b-bad">😜 딴청 {troll}건</span><span class="badge b-ok">문답 {n}회</span>'
                elif n == 0:
                    sb = '<span class="badge b-warn">🟡 대화 0회</span>'
                elif silent is not None and silent >= SILENT_MIN:
                    sb = f'<span class="badge b-warn">🟡 침묵 {silent}분</span><span class="badge b-ok">문답 {n}회</span>'
                else:
                    sb = f'<span class="badge b-ok">🟢 문답 {n}회</span>'
                with grid[i]:
                    st.markdown(f"""<div style="display:flex;justify-content:space-between;align-items:center;margin:2px 0 4px 0;">
                    <div><span style="font-size:1.2rem;font-weight:800;">{t}</span>{level_badge(p)}</div>
                    <div>{sb}<span class="badge b-time">단계 {stage_elapsed_min(p)}분째</span></div></div>""", unsafe_allow_html=True)
                    
                    if not is_board:
                        c1, c2, c3 = st.columns(3)
                        is_zoomed = (z == t)
                        if c1.button("✖ 닫기" if is_zoomed else "🔍 크게", key=f"zoom_{t}", use_container_width=True):
                            set_state("zoom_team", "" if is_zoomed else t)
                            set_state("board_scroll", "0")
                            st.rerun()
                        lv = p["level"]
                        hint_sent = p.get(f"hint_lv{lv}", 0)
                        c2.button(f"📨 힌트{min(hint_sent + 1, 2)}차", key=f"hint_{t}", use_container_width=True, disabled=(hint_sent >= 2),
                                  on_click=_manual_hint_cb, args=(t,))
                        if lv < 3:
                            if c3.button(f"⚡ LV{lv + 1} 오픈", key=f"force_{t}", use_container_width=True):
                                update_progress(t, level=lv + 1, step1_approved=1, step2_approved=(1 if lv + 1 == 3 else 0), reset_timer=True)
                                save_log(t, "teacher", "system", "[교사 강제 오픈]", f"LV{lv + 1} 강제 개방", 0, lv + 1); st.rerun()
                        else:
                            t_done = bool(p.get("done"))
                            if c3.button("↩ 완료 취소" if t_done else "🏆 완료 처리", key=f"done_{t}",
                                         type="secondary" if t_done else "primary", use_container_width=True):
                                set_done(t, not t_done)
                                save_log(t, "teacher", "system", "[교사 완료 처리]",
                                         "LV3 탐구 완료 인정 🏆" if not t_done else "LV3 완료 처리 취소", 0, 3)
                                st.rerun()

                    with st.container(height=230 if is_board else 185, border=True):
                        if tl.empty:
                            st.markdown('<div style="color:#94a3b8;text-align:center;padding-top:65px;font-size:0.9rem;">아직 질문이 없습니다.<br>발문을 독려하세요.</div>', unsafe_allow_html=True)
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

        # ---- [전광판 페이지 2] 통계 · LV3 최종 보고 · 참관 선생님 질문 피드 ----
        if not is_board or bpage == "stats":
            if not is_board:
                st.markdown("---")
            chat_only = all_logs[all_logs["kind"] == "chat"] if not all_logs.empty else pd.DataFrame()
            hint_only = all_logs[all_logs["kind"] == "hint"] if not all_logs.empty else pd.DataFrame()
            student_chats = chat_only[chat_only["team"].isin(TEAMS)] if not chat_only.empty else pd.DataFrame()
            g = chat_only[chat_only["team"] == GUEST] if not chat_only.empty else pd.DataFrame()

            tot_student_q = len(student_chats)
            tot_guest_q = len(g)
            tot_all_q = tot_student_q + tot_guest_q
            tot_hints = len(hint_only)

            st.markdown("### 📊 실시간 AI 문답 통계 (전체 · 조별 · 참관교사)")
            m1, m2, m3, m4 = st.columns(4)
            m1.markdown(f'<div class="card" style="text-align:center;padding:10px;background:#f8fafc;border-left:5px solid #0f172a;">'
                        f'<span style="font-size:0.85rem;color:#475569;font-weight:700;">🔥 교실 전체 누적 문답</span><br>'
                        f'<b style="font-size:1.35rem;color:#0f172a;">질문 {tot_all_q}건 / 답변 {tot_all_q}건</b></div>', unsafe_allow_html=True)
            m2.markdown(f'<div class="card" style="text-align:center;padding:10px;background:#eff6ff;border-left:5px solid #2563eb;">'
                        f'<span style="font-size:0.85rem;color:#1e40af;font-weight:700;">🧑‍🤝‍🧑 1~6조 학생 문답 합계</span><br>'
                        f'<b style="font-size:1.35rem;color:#1d4ed8;">질문 {tot_student_q}건 / 답변 {tot_student_q}건</b></div>', unsafe_allow_html=True)
            m3.markdown(f'<div class="card" style="text-align:center;padding:10px;background:#fff7ed;border-left:5px solid #f97316;">'
                        f'<span style="font-size:0.85rem;color:#9a3412;font-weight:700;">☕ 참관 선생님 체험 문답</span><br>'
                        f'<b style="font-size:1.35rem;color:#c2410c;">질문 {tot_guest_q}건 / 답변 {tot_guest_q}건</b></div>', unsafe_allow_html=True)
            m4.markdown(f'<div class="card" style="text-align:center;padding:10px;background:#fefce8;border-left:5px solid #eab308;">'
                        f'<span style="font-size:0.85rem;color:#854d0e;font-weight:700;">💡 AI 발송 힌트 합계</span><br>'
                        f'<b style="font-size:1.35rem;color:#a16207;">총 {tot_hints}회 발송</b></div>', unsafe_allow_html=True)

            t_cols = st.columns(6)
            for idx, t in enumerate(TEAMS):
                t_q = len(student_chats[student_chats["team"] == t]) if not student_chats.empty else 0
                t_h = len(hint_only[hint_only["team"] == t]) if not hint_only.empty else 0
                t_lv = progs[t]["level"]
                with t_cols[idx]:
                    st.markdown(f'<div class="card" style="text-align:center;padding:8px 6px;margin-bottom:6px;">'
                                f'<b style="font-size:1.05rem;">{t}</b> <span class="badge b-lv{t_lv}">LV{t_lv}</span><br>'
                                f'<span style="font-size:0.92rem;color:#15803d;font-weight:800;">질문 {t_q} · 답변 {t_q}</span><br>'
                                f'<span style="font-size:0.76rem;color:#64748b;">힌트 {t_h}회</span></div>', unsafe_allow_html=True)

            st.markdown("### 📢 LV3 모둠 최종 보고 (가장 최근 발화)")
            fin_cols = st.columns(3)
            k = 0
            for t in TEAMS:
                if progs[t]["level"] == 3 and not all_logs.empty:
                    c3 = all_logs[(all_logs["team"] == t) & (all_logs["kind"] == "chat") & (all_logs["level"] == 3)]
                    if len(c3):
                        with fin_cols[k % 3]:
                            st.markdown(f'<div class="card lv3" style="padding:10px 14px;"><b>{t}</b>{" 🏆 완료" if progs[t].get("done") else ""}<br>{esc(c3["question"].iloc[-1], 140)}</div>', unsafe_allow_html=True)
                        k += 1
            if k == 0:
                st.caption("아직 3단계에 도달한 모둠이 없습니다.")

            st.markdown(f"### ☕ 참관 선생님 실시간 질문·답변 피드 <span style='font-size:0.95rem;color:#64748b'>(질문 {tot_guest_q}건 / 답변 {tot_guest_q}건)</span>", unsafe_allow_html=True)
            if g.empty:
                st.caption("아직 참관 선생님의 체험 질문이 없습니다.")
            else:
                gc = st.columns(3)
                for j, (_, r) in enumerate(g.tail(6).iloc[::-1].iterrows()):
                    with gc[j % 3]:
                        st.markdown(f'<div class="card" style="padding:10px 14px;border-left:5px solid #f97316;background:#fff7ed;"><div style="font-size:0.75rem;color:#9a3412;font-weight:700;">익명 참관교사({esc(r["client"])}) · {esc(str(r["ts"])[11:19])}</div>'
                                    f'<div style="font-weight:800;margin:2px 0;">Q. {esc(r["question"], 80)}</div><div style="font-size:0.84rem;color:#7c2d12;">AI: {esc(r["answer"], 90)}</div></div>', unsafe_allow_html=True)

    dashboard()
    st.stop()
# ----------------------------------------------------------------------------
# 9. 학생(1~6조) & 참관교사 화면
# ----------------------------------------------------------------------------
is_guest = (mode == "☕ 참관교사")
team = GUEST if is_guest else mode
client_id = f"T-{st.session_state['client_id']}" if is_guest else "tablet"

# ★ [1~6조 학생 전용] 교사 원격 접속 차단 & 입장 비밀번호(PIN) 검문소!
if not is_guest:
    req_pin = get_state("student_pin") or ""
    blocked = (get_state("student_block") == "1")

    # 1) 교사가 [🚫 학생 접속차단]을 켜둔 경우 → 즉시 차단 안내 화면 표시 (5초마다 자동 해제 감지)
    if blocked:
        @st.fragment(run_every="5s")
        def _wait_unblock():
            if get_state("student_block") != "1":
                st.rerun(scope="app")
            st.markdown("""
            <div class="card" style="text-align:center; padding:50px 20px; margin-top:30px; border:3px solid #ef4444; background:#fef2f2;">
                <h1 style="color:#b91c1c; font-size:2rem !important;">⛔ 현재 선생님이 접속을 제한했습니다</h1>
                <p style="font-size:1.2rem; color:#7f1d1d; margin-top:12px;">
                    수업 시간이 아니거나 선생님이 화면을 잠가 두셨습니다.<br>
                    선생님이 접속 제한을 해제하면 이 화면이 자동으로 열립니다! 잠시만 기다려 주세요.
                </p>
            </div>
            """, unsafe_allow_html=True)
        _wait_unblock()
        st.stop()

    # 2) 교사가 학생 입장 비번(student_pin)을 설정해 둔 경우 → 비번이 맞을 때만 통과!
    #    (교사가 비번을 바꾸면 st.session_state["student_authed_pin"]과 달라지므로 기존 접속자도 즉시 다시 잠김!)
    if req_pin and st.session_state.get("student_authed_pin") != req_pin:
        st.title(f"🔐 {mode} — 입장 비밀번호 입력")
        st.markdown("""
        <div class="card lv2" style="font-size:1.1rem;">
            선생님께서 안내해 주신 <b>오늘의 수업 입장 비밀번호</b>를 입력해야 탐구 교실이 열립니다!
        </div>
        """, unsafe_allow_html=True)
        with st.form("student_pin_form"):
            in_pin = st.text_input("🔑 입장 비밀번호", type="password", placeholder="선생님이 알려주신 비밀번호를 입력하세요")
            sub = st.form_submit_button("✅ 입장하기", type="primary", use_container_width=True)
            if sub:
                if in_pin.strip() == req_pin:
                    st.session_state["student_authed_pin"] = req_pin
                    st.rerun()
                else:
                    st.error("❌ 비밀번호가 일치하지 않습니다! 선생님께 다시 확인해 보세요.")
        st.stop()

if st.session_state.pop("celebrate", False):
    st.balloons()

if is_guest:
    prog = {"team": GUEST, "level": st.session_state.get("guest_level", 1), "step1_approved": 1, "step2_approved": 1,
            "stage_start_time": st.session_state.setdefault("guest_start", ts()), "hint_lv1": 0, "hint_lv2": 0}
else:
    prog = get_progress(team)
level = prog["level"]
done = bool(prog.get("done"))
approved = bool(prog["step1_approved"]) if level == 1 else bool(prog["step2_approved"]) if level == 2 else True

@st.fragment(run_every="6s")
def top_bar():
    lab, el, act = class_clock()
    p = get_progress(team) if not is_guest else prog
    sm = stage_elapsed_min(p)
    st.markdown(f"""<div class="topbar"><div style="font-size:1rem;font-weight:800;">📐 미적분Ⅰ 탐구 교실 · <span style="color:#38bdf8">{html.escape(mode)}</span> · LV.{p['level']}</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;"><span class="pill" style="background:#1e3a8a;color:#bfdbfe;">⏱️ 수업 {el}분 / {CLASS_MIN}분</span>
    <span class="pill" style="background:#334155;color:#fde047;">⏳ 이 단계 {sm}분째</span></div></div>""", unsafe_allow_html=True)
    if not is_guest:
        # ★ 이미 접속해 있는 학생이라도 교사가 [차단]을 누르거나 [비번을 변경]하면 6초 내로 즉시 감지하여 강제 퇴장!
        cur_req_pin = get_state("student_pin") or ""
        if (get_state("student_block") == "1") or (cur_req_pin and st.session_state.get("student_authed_pin") != cur_req_pin):
            st.rerun(scope="app")
        changed = (p["level"] != level) or (bool(p["step1_approved"] if p["level"] == 1 else p["step2_approved"] if p["level"] == 2 else True) != approved) or (bool(p.get("done")) != done)
        if p.get("done") and not done:
            st.session_state["celebrate"] = True
        if maybe_send_hints(team, p, act) or changed:
            st.rerun(scope="app")
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
if level == 3 and done and not is_guest:
    st.markdown('<div class="unlock">🏆👑 선생님이 확인했어요! 우리 모둠 탐구 완성 — 수고했어요! 👑🏆</div>', unsafe_allow_html=True)

col_g, col_c = st.columns([1.05, 0.95], gap="medium")

# ================= 좌측: 그래프 + 잠금 해제 =================
with col_g:
    # mp3(audio/stepN.mp3)가 없을 때 화면에 대신 보이는 요약 안내 — 녹음 대본과 같은 내용
    audio_txt = {1: "화면은 아직 비어 있어요. AI에게 극값이 생기는 위치를 질문해 f'(x)와 그 식이 0이 되는 x를 찾고, 활동지 1단계 증감표를 x값부터 모두 채운 뒤 극댓점·극솟점 좌표를 적으세요.",
                 2: "화면에 열린 극댓점·극솟점을 활동지 2단계 좌표평면에 옮겨 그린 뒤, AI와 함께 수평선의 식 → 접할 때 근의 특징 → 다시 만나는 교점을 찾아 작도하고, 눈금(1칸=2cm)으로 가로 간격을 구하세요.",
                 3: "화면의 수평선·교점이 2단계에서 찾은 결과와 맞나요? 활동지 3단계에서 x³−3x−2=0 을 모둠의 방법으로 완전히 인수분해해 증명하세요. 이어서 극솟점에서도 한 번 더 확인해 보고, 비율 법칙을 한 문장으로 AI에게 보고하세요."}[level]
    if st.button(f"▶ {level}단계 미션 안내 듣기", use_container_width=True):
        mission_audio(level, audio_txt)
    st.image(graph_png(level), use_container_width=True)
    st.markdown(f'<div class="gcap">{GRAPH_CAPTION[level]}</div>', unsafe_allow_html=True)

    def unlock_button(key):
        if level == 1:
            st.markdown('<div class="unlock">🎉 1단계 AI 인증 완료! 활동지 1단계(증감표·극점 좌표)를 다 채웠다면 👇</div>', unsafe_allow_html=True)
            if st.button("🔓 활동지 1단계 완료 ➔ 2단계 그래프 열기", key=key, type="primary", use_container_width=True):
                if is_guest:
                    st.session_state["guest_level"] = 2; st.session_state["guest_start"] = ts()
                else:
                    update_progress(team, level=2, step1_approved=1, reset_timer=True)
                    save_log(team, client_id, "system", "[학생 버튼]", "활동지 1단계 완료 → LV2 진입", 0, 2)
                st.session_state["celebrate"] = True; st.rerun()
        elif level == 2:
            st.markdown('<div class="unlock">🎉 2단계 AI 검증 완료! 활동지에 수평선·교점을 작도하고 거리 표와 비율을 기록했다면 👇</div>', unsafe_allow_html=True)
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
                     2: "💬 수평선의 식 ➔ 접할 때 근의 특징 ➔ 교점의 x좌표 순서로 AI의 질문에 답해 승인을 받으세요. (그동안 화면의 극점을 활동지 좌표평면에 옮겨 그려 두세요!)"}[level])

# ================= 우측: 소크라테스 AI 채팅 (6초마다 DB 동기화 → 같은 조 태블릿 2대 공유) =================
with col_c:
    st.subheader(f"💬 소크라테스 AI · {team if not is_guest else '참관교사 체험'} · LV.{level}")

    @st.fragment(run_every="6s")
    def chat_panel():
        if not is_guest and ((get_state("student_block") == "1") or ((get_state("student_pin") or "") and st.session_state.get("student_authed_pin") != (get_state("student_pin") or ""))):
            st.rerun(scope="app")
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
        # DB의 딴청 기록(id)이 새로 생기면 재생 → 같은 조 태블릿 2대 모두 울림
        if not hist_df.empty:
            _tr = hist_df[(hist_df["kind"] == "chat") & (hist_df["is_troll"].fillna(0).astype(int) == 1)]
            max_tid = int(_tr["id"].max()) if not _tr.empty else 0
        else:
            max_tid = 0
        if "seen_troll_id" not in st.session_state:
            st.session_state["seen_troll_id"] = max_tid          # 처음 접속 시 과거 기록은 재생 안 함
        elif max_tid > st.session_state["seen_troll_id"]:
            st.session_state["seen_troll_id"] = max_tid
            t_mp3 = "audio/troll_tablet.mp3" if os.path.exists("audio/troll_tablet.mp3") else "audio/troll.mp3"
            play_persistent_audio(t_mp3)
        box = st.container(height=400)
        with box:
            if hist_df.empty:
                st.markdown('<div style="color:#94a3b8;text-align:center;padding-top:120px;">모둠의 첫 질문을 입력해 보세요 👇</div>', unsafe_allow_html=True)
            else:
                render_chat_rows(hist_df)

        if level < 3 and approved and not is_guest:
            unlock_button("unlock_right")

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
                3: [("📝 인수분해 증명 힌트", "활동지 3단계에서 x^3-3x-2=0 을 어떻게 인수분해하면 접점과 교점의 위치가 대수적으로 증명돼?"),
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