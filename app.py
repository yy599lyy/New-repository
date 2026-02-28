# app.py
import os
import json
import random
import pathlib
import time
import re
import datetime
import sqlite3
import uuid
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

# =========================
# 0) 配置读取（部署/本地都稳）
# =========================
load_dotenv()

def get_cfg(name: str, default: str = "") -> str:
    try:
        v = st.secrets.get(name, "")
        if v:
            return str(v)
    except Exception:
        pass
    return os.getenv(name, default)

ARK_API_KEY = get_cfg("ARK_API_KEY")
ARK_BASE_URL = get_cfg("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
MODEL_NAME = get_cfg("ARK_MODEL")

st.set_page_config(page_title="塔罗占卜", page_icon="🔮", initial_sidebar_state="collapsed")

if not ARK_API_KEY or not MODEL_NAME:
    st.error("缺少配置：请在 Streamlit Cloud 的 Secrets 里设置 ARK_API_KEY 与 ARK_MODEL。")
    st.code(
        'ARK_API_KEY="你的key"\n'
        'ARK_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"\n'
        'ARK_MODEL="你的模型名"\n',
        language="toml",
    )
    st.stop()

client = OpenAI(api_key=ARK_API_KEY, base_url=ARK_BASE_URL)

# =========================
# 1) 牌库
# =========================
BASE_DIR = pathlib.Path(__file__).parent
CARDS_PATH = BASE_DIR / "cards.json"
CARD_BACK_PATH = BASE_DIR / "card_back.png"

@st.cache_data
def load_cards():
    with open(CARDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CARDS = load_cards()

def make_card(card_obj):
    is_reversed = random.choice([True, False])
    meaning = card_obj["reversed"] if is_reversed else card_obj["upright"]
    return {"name": card_obj["name"], "position": "逆位" if is_reversed else "正位", "meaning": meaning}

# =========================
# 2) 追问题库
# =========================
FOLLOW_UP = {
    "综合": [
        ("你最想解决的是哪类困扰？", ["情绪/内耗", "关系", "工作/学业", "选择困难"]),
        ("你更希望得到哪种帮助？", ["明确方向", "具体行动建议", "风险提醒", "情绪安抚"]),
    ],
    "恋爱": [
        ("你目前的关系状态更像哪种？", ["暧昧/刚开始", "稳定交往", "冷淡/拉扯", "分手/断联后"]),
        ("你最在意的点是什么？", ["对方态度", "未来承诺", "沟通冲突", "安全感/信任"]),
    ],
    "事业": [
        ("你现在更像哪种处境？", ["想跳槽", "想升职/加薪", "工作倦怠", "转行/创业"]),
        ("你最看重的优先级是？", ["收入", "成长空间", "稳定", "自由/生活平衡"]),
    ],
    "学业": [
        ("你目前的学习目标是？", ["考试上岸", "提升成绩", "选专业/方向", "拖延/效率"]),
        ("你最大的阻力来自？", ["时间管理", "自信不足", "方法不对", "外部干扰"]),
    ],
    "自我成长": [
        ("你现在更想提升哪方面？", ["自信/表达", "边界感", "执行力", "情绪稳定"]),
        ("你更倾向的改变方式是？", ["慢慢调整", "立刻做决定", "先观察再动", "需要外部支持"]),
    ],
}

# =========================
# 3) 变现：SQLite（限免计数 + 一次性激活码 + 深度次数）
# =========================
FREE_PER_DAY = 1  # 每天免费次数（按 uid 计）

# 预置激活码：会 seed 到 DB（一次性）
VALID_CODES = {
    "TAROT9": True,
    "VIP001": True,
    "LOVE888": True,
}

DB_PATH = str((BASE_DIR / "tarot.db").resolve())

def db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def db_init():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS usage_daily (
        uid TEXT NOT NULL,
        day TEXT NOT NULL,
        used INT NOT NULL DEFAULT 0,
        PRIMARY KEY (uid, day)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_credits (
        uid TEXT PRIMARY KEY,
        deep_credits INT NOT NULL DEFAULT 0,
        updated_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS codes (
        code TEXT PRIMARY KEY,
        remaining INT NOT NULL DEFAULT 1,
        created_at TEXT,
        used_at TEXT,
        used_by TEXT
    )
    """)
    conn.commit()
    conn.close()

def today_key():
    return datetime.date.today().isoformat()

def get_or_create_uid():
    qp = st.query_params
    uid = (qp.get("uid") or "").strip()
    if not uid:
        uid = uuid.uuid4().hex[:16]
        st.query_params["uid"] = uid
        st.rerun()
    return uid

def seed_codes_if_needed(codes: dict):
    conn = db_conn()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    for code, enabled in (codes or {}).items():
        if not enabled:
            continue
        code = (code or "").strip()
        if not code:
            continue
        cur.execute("INSERT OR IGNORE INTO codes(code, remaining, created_at) VALUES(?,?,?)", (code, 1, now))
    conn.commit()
    conn.close()

def get_free_used(uid: str) -> int:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT used FROM usage_daily WHERE uid=? AND day=?", (uid, today_key()))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else 0

def inc_free_used(uid: str, n: int = 1):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO usage_daily(uid, day, used) VALUES(?,?,?)
    ON CONFLICT(uid, day) DO UPDATE SET used = used + ?
    """, (uid, today_key(), n, n))
    conn.commit()
    conn.close()

def can_use_free(uid: str) -> bool:
    return get_free_used(uid) < FREE_PER_DAY

def get_deep_credits(uid: str) -> int:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT deep_credits FROM user_credits WHERE uid=?", (uid,))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else 0

def add_deep_credits(uid: str, n: int = 1):
    now = datetime.datetime.utcnow().isoformat()
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO user_credits(uid, deep_credits, updated_at) VALUES(?,?,?)
    ON CONFLICT(uid) DO UPDATE SET deep_credits = deep_credits + ?, updated_at=?
    """, (uid, n, now, n, now))
    conn.commit()
    conn.close()

def consume_deep_credit(uid: str, n: int = 1) -> bool:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT deep_credits FROM user_credits WHERE uid=?", (uid,))
    row = cur.fetchone()
    cur_credits = int(row[0]) if row else 0
    if cur_credits < n:
        conn.close()
        return False
    now = datetime.datetime.utcnow().isoformat()
    cur.execute("UPDATE user_credits SET deep_credits = deep_credits - ?, updated_at=? WHERE uid=?", (n, now, uid))
    conn.commit()
    conn.close()
    return True

def redeem_code(uid: str, code: str) -> tuple[bool, str]:
    code = (code or "").strip()
    if not code:
        return False, "请输入激活码"
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT remaining FROM codes WHERE code=?", (code,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, "激活码不存在或无效"
    remaining = int(row[0])
    if remaining <= 0:
        conn.close()
        return False, "激活码已使用"
    now = datetime.datetime.utcnow().isoformat()
    cur.execute("""
    UPDATE codes
    SET remaining = remaining - 1, used_at=?, used_by=?
    WHERE code=? AND remaining > 0
    """, (now, uid, code))
    if cur.rowcount <= 0:
        conn.close()
        return False, "激活码已使用"
    conn.commit()
    conn.close()
    add_deep_credits(uid, 1)
    return True, "兑换成功：深度解读次数 +1"

# 初始化 DB & uid
db_init()
uid = get_or_create_uid()
seed_codes_if_needed(VALID_CODES)

# =========================
# 4) JSON 解析 + 修复（稳）
# =========================
def parse_json_safely(text: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        s = text.find("{")
        e = text.rfind("}")
        if s != -1 and e != -1 and e > s:
            return json.loads(text[s:e+1])
    except Exception:
        pass
    try:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return None

def repair_json_with_model(raw_text: str) -> dict | None:
    # 低成本“修 JSON”兜底：只要求输出严格 JSON
    prompt = f"""
你是 JSON 修复器。把下面内容修复为【严格JSON】。
要求：只输出JSON本体，不要任何多余文字/markdown/代码块。

内容：
{raw_text}
"""
    r = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    fixed = r.choices[0].message.content
    return parse_json_safely(fixed)

# =========================
# 5) AI：免费版/深度版（两套 prompt）
# =========================
def ai_free(question, cards, topic, tone, fu):
    prompt = f"""
你是专业塔罗解读师。风格：{tone}。类型：{topic}。
输出必须是【严格JSON】（不要多余文字/markdown/代码块）。

规则：
- 不做必然预测，用“倾向/可能/建议”
- 不编造牌面之外细节（不说具体人物/金额/日期）
- 不提供医疗/法律/投资具体指令；如涉及，给安全提示

字段必须包含：
- one_line: <=22字
- overall: 2句数组
- card_readings: 3项数组，每项包含 position/card/orientation/impact（impact 1句）
- advice: 1条数组（具体可执行）
- caution: 1条数组

用户问题：{question}
追问：{json.dumps(fu, ensure_ascii=False)}
牌：{json.dumps(cards, ensure_ascii=False)}
"""
    r = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.35,
    )
    return r.choices[0].message.content

def ai_deep(question, cards, topic, tone, fu):
    prompt = f"""
你是专业塔罗解读师。风格：{tone}。类型：{topic}。
你必须针对用户【具体问题】给出【具体、可执行、可验证】的解读。
输出必须是【严格JSON】（不要多余文字/markdown/代码块）。

必须包含：
- one_line: <=22字（贴题）
- keywords_used: 3-6关键词数组
- user_context: 1-2句复述处境（引用追问答案）
- overall: 2句数组
- card_readings: 3项数组，每项含 position/card/orientation/impact/signal/action
- advice: 3条数组
- signals_to_watch: 3条数组
- if_then_plan: 2条数组（必须“如果…那么…”）
- plan_7_days: 7条数组
- caution: 1-2条数组

规则：
- 不做必然预测；不编造细节；不提供医疗/法律/投资具体指令
- JSON 字段值不要出现多余前后说明文字

用户问题：{question}
追问：{json.dumps(fu, ensure_ascii=False)}
牌（含基础义）：{json.dumps(cards, ensure_ascii=False)}
"""
    r = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.45,
    )
    return r.choices[0].message.content

# =========================
# 6) UI：样式（手机友好）
# =========================
st.markdown(
    """
<style>
.stApp{
  background:
    radial-gradient(900px 600px at 10% 10%, rgba(140, 82, 255, 0.22), transparent 60%),
    radial-gradient(900px 600px at 90% 20%, rgba(0, 255, 210, 0.10), transparent 55%),
    radial-gradient(900px 600px at 30% 90%, rgba(255, 110, 199, 0.12), transparent 55%),
    linear-gradient(180deg, #0b0b14 0%, #080812 40%, #050510 100%);
  color: rgba(255,255,255,0.92);
}
.block-container{ padding-top: 1.1rem; max-width: 980px; }
h1,h2,h3{ letter-spacing: .5px; }

.tarot-card{
  border: 1px solid rgba(255,255,255,.16);
  border-radius: 18px;
  padding: 12px;
  background: rgba(255,255,255,.04);
  box-shadow: 0 16px 45px rgba(0,0,0,.30),
              0 0 0 1px rgba(180,120,255,.06) inset;
}
.badge{
  display:inline-block; font-size:.80rem; padding:3px 10px; border-radius:999px;
  border:1px solid rgba(255,255,255,.18); background: rgba(255,255,255,.06);
  margin-right:8px;
}
.small{ font-size:.88rem; opacity:.88; }

.card-back-placeholder{
  background: linear-gradient(135deg,#2a1b3d,#1a0f2a);
  border:2px solid rgba(122,95,160,.6);
  border-radius:14px;
  height:140px;
  display:flex; align-items:center; justify-content:center;
  color:#bbaadd; font-size:2rem;
}

/* 牌堆视觉 */
.stack-wrap{ display:flex; justify-content:center; margin: 8px 0 0 0; }
.stack{ width: 170px; position:relative; }
.stack::before, .stack::after{
  content:""; position:absolute; inset:0;
  border-radius: 16px; background: rgba(255,255,255,.03);
  border: 1px solid rgba(255,255,255,.10);
  transform: translate(10px, 10px); z-index:0;
}
.stack::after{ transform: translate(6px,6px); z-index:1; }
.stack-inner{
  position:relative; z-index:2;
  border-radius:16px; overflow:hidden;
  border: 1px solid rgba(255,255,255,.16);
  box-shadow: 0 18px 50px rgba(0,0,0,.35);
}

@keyframes flipIn{
  0%{ transform: perspective(900px) rotateY(70deg) translateY(10px); opacity:0; }
  60%{ transform: perspective(900px) rotateY(-10deg) translateY(0px); opacity:1; }
  100%{ transform: perspective(900px) rotateY(0deg) translateY(0px); opacity:1; }
}
.revealed-anim{ animation: flipIn 650ms ease; transform-origin:center; }

.paywall{
  border: 1px solid rgba(255,255,255,.18);
  border-radius: 16px;
  padding: 14px;
  background: rgba(255,255,255,.05);
}
</style>
""",
    unsafe_allow_html=True,
)

def render_card_back():
    if CARD_BACK_PATH.exists():
        st.image(str(CARD_BACK_PATH), use_container_width=True)
    else:
        st.markdown('<div class="card-back-placeholder">🂠</div>', unsafe_allow_html=True)

def do_shuffle(seconds: int):
    if seconds <= 0:
        return
    p = st.progress(0.0)
    steps = max(1, int(seconds * 10))
    for i in range(steps):
        time.sleep(seconds / steps)
        p.progress((i + 1) / steps)
    p.empty()

def show_paywall():
    st.markdown(
        """
<div class="paywall">
  <b>✨ 深度解读（¥9.9 / 次）</b><br/>
  ✔ 每张牌：影响点 + 迹象 + 行动（更具体）<br/>
  ✔ 3条观察信号 + 2条“如果…那么…”策略<br/>
  ✔ 7天行动计划<br/>
  <div style="opacity:.75;margin-top:8px;">
    支付后输入一次性激活码，即可获得「深度次数 +1」
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

def reading_to_text(rd: dict) -> str:
    if not isinstance(rd, dict):
        return str(rd)
    if "raw" in rd:
        return rd.get("raw", "")
    lines = []
    one = rd.get("one_line", "")
    if one:
        lines.append(f"一句话结论：{one}")
    kws = rd.get("keywords_used") or []
    if kws:
        lines.append("关键词：" + " / ".join(kws))
    uc = rd.get("user_context", "")
    if uc:
        lines.append("\n【我理解你的处境】\n" + uc)

    overall = rd.get("overall") or []
    if overall:
        lines.append("\n【整体能量】")
        for s in overall:
            lines.append(f"- {s}")

    cr = rd.get("card_readings") or []
    if cr:
        lines.append("\n【逐牌解读】")
        for item in cr:
            head = f"{item.get('position','')}｜{item.get('card','')}（{item.get('orientation','')}）"
            lines.append(head)
            if item.get("impact"):
                lines.append(f"  影响点：{item.get('impact')}")
            if item.get("signal"):
                lines.append(f"  迹象：{item.get('signal')}")
            if item.get("action"):
                lines.append(f"  动作：{item.get('action')}")

    advice = rd.get("advice") or []
    if advice:
        lines.append("\n【建议】")
        for a in advice:
            lines.append(f"- {a}")

    sig = rd.get("signals_to_watch") or []
    if sig:
        lines.append("\n【接下来观察什么】")
        for s in sig:
            lines.append(f"- {s}")

    itp = rd.get("if_then_plan") or []
    if itp:
        lines.append("\n【如果…那么…】")
        for p in itp:
            lines.append(f"- {p}")

    p7 = rd.get("plan_7_days") or []
    if p7:
        lines.append("\n【7天行动计划】")
        for i, x in enumerate(p7, start=1):
            lines.append(f"- Day {i}: {x}")

    caut = rd.get("caution") or []
    if caut:
        lines.append("\n【提醒】")
        for c in caut:
            lines.append(f"- {c}")

    return "\n".join(lines).strip()

# =========================
# 7) session_state（仅做流程状态，不做计数/付费）
# =========================
def init_state():
    defaults = {
        "stage": "ask",               # ask -> followup -> draw -> reading
        "followup_answers": {},
        "drawn_cards": [],
        "reveal_index": -1,
        "reading": None,
        "reading_is_deep": False,     # 本次结果是深度吗
        "history": [],
        "last_question": "",
        "last_topic": "综合",
        "last_tone": "温和",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# =========================
# 8) 顶部步骤条
# =========================
steps = ["写问题", "回答追问", "抽牌并翻牌", "查看解读"]
stage_map = {"ask": 0, "followup": 1, "draw": 2, "reading": 3}
cur = stage_map.get(st.session_state["stage"], 0)
st.markdown(f"**步骤：{cur+1}/{len(steps)} — {steps[cur]}**")
st.progress((cur + 1) / len(steps))

# =========================
# 9) 页面主体
# =========================
st.title("🔮 塔罗占卜（可盈利版）")
st.caption("免费每日 1 次（按UID）；深度解读 ¥9.9/次（一次性激活码兑换深度次数）。")
st.caption("免责声明：内容仅供娱乐与自我反思，不替代医疗/法律/财务等专业意见。")

# 侧边栏
st.sidebar.header("🧭 设置")
topic = st.sidebar.selectbox("问题类型", ["综合", "恋爱", "事业", "学业", "自我成长"], index=["综合","恋爱","事业","学业","自我成长"].index(st.session_state["last_topic"]) if st.session_state["last_topic"] in ["综合","恋爱","事业","学业","自我成长"] else 0)
tone = st.sidebar.selectbox("解读风格", ["温和", "直接", "治愈"], index=["温和","直接","治愈"].index(st.session_state["last_tone"]) if st.session_state["last_tone"] in ["温和","直接","治愈"] else 0)
show_base = st.sidebar.checkbox("显示基础牌义", value=True)
shuffle_seconds = st.sidebar.slider("洗牌动画时长（秒）", 0, 5, 1)

st.session_state["last_topic"] = topic
st.session_state["last_tone"] = tone

# 状态栏：按 UID & DB 统计
free_left = max(0, FREE_PER_DAY - get_free_used(uid))
deep_left = get_deep_credits(uid)
st.info(f"🆓 今日剩余免费：{free_left}/{FREE_PER_DAY}   |   💎 深度次数：{deep_left}")
st.caption(f"UID：{uid}（用于按天限免与次数保存）")

# 激活码入口（转化入口）
with st.expander("💳 输入一次性激活码兑换深度次数（¥9.9/次）", expanded=False):
    show_paywall()
    code = st.text_input("激活码（一次性）", key="code_input").strip()
    if st.button("兑换深度次数 +1"):
        ok, msg = redeem_code(uid, code)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

# 问题输入
question = st.text_input(
    "你想问什么？",
    placeholder="例如：我该不该换工作？这段关系未来一个月怎么走？",
    value=st.session_state.get("last_question", ""),
)
st.session_state["last_question"] = question

col1, col2 = st.columns([1, 1])
with col1:
    if st.button("➡️ 下一步：回答两个关键问题"):
        if not question.strip():
            st.warning("先写下你的问题～")
        else:
            st.session_state["stage"] = "followup"
            st.session_state["reading"] = None
            st.session_state["reading_is_deep"] = False
            st.session_state["drawn_cards"] = []
            st.session_state["reveal_index"] = -1
            st.session_state["followup_answers"] = {}
            st.rerun()
with col2:
    if st.button("🔄 重新开始（清空流程）"):
        for k in ["stage", "reading", "reading_is_deep", "drawn_cards", "reveal_index", "followup_answers"]:
            st.session_state[k] = {"stage":"ask","reading":None,"reading_is_deep":False,"drawn_cards":[],"reveal_index":-1,"followup_answers":{}}[k]
        st.rerun()

# 追问阶段
if st.session_state["stage"] in ["followup", "draw", "reading"]:
    st.subheader("✅ 第一步：回答两个关键问题")
    q1, opts1 = FOLLOW_UP.get(topic, FOLLOW_UP["综合"])[0]
    q2, opts2 = FOLLOW_UP.get(topic, FOLLOW_UP["综合"])[1]
    a1 = st.radio(q1, opts1, key="fu1")
    a2 = st.radio(q2, opts2, key="fu2")
    st.session_state["followup_answers"] = {q1: a1, q2: a2}

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("🃏 下一步：一键抽牌（生成3张）"):
            do_shuffle(shuffle_seconds)
            chosen = random.sample(CARDS, k=3)  # 更省
            deck = [make_card(c) for c in chosen]
            pos_order = ["过去", "现在", "未来"]
            drawn = []
            for i in range(3):
                card = dict(deck[i])
                card["pos_label"] = pos_order[i]
                drawn.append(card)
            st.session_state["drawn_cards"] = drawn
            st.session_state["reveal_index"] = -1
            st.session_state["reading"] = None
            st.session_state["reading_is_deep"] = False
            st.session_state["stage"] = "draw"
            st.rerun()
    with c2:
        if st.button("跳过追问并抽牌（可选）"):
            st.session_state["followup_answers"] = {}
            do_shuffle(shuffle_seconds)
            chosen = random.sample(CARDS, k=3)
            deck = [make_card(c) for c in chosen]
            pos_order = ["过去", "现在", "未来"]
            drawn = []
            for i in range(3):
                card = dict(deck[i])
                card["pos_label"] = pos_order[i]
                drawn.append(card)
            st.session_state["drawn_cards"] = drawn
            st.session_state["reveal_index"] = -1
            st.session_state["reading"] = None
            st.session_state["reading_is_deep"] = False
            st.session_state["stage"] = "draw"
            st.rerun()

# 翻牌阶段
if st.session_state["stage"] in ["draw", "reading"] and st.session_state["drawn_cards"]:
    st.subheader("🃏 第二步：逐张翻牌（过去 / 现在 / 未来）")
    drawn = st.session_state["drawn_cards"]
    reveal = st.session_state["reveal_index"]

    st.markdown('<div class="stack-wrap"><div class="stack"><div class="stack-inner">', unsafe_allow_html=True)
    render_card_back()
    st.markdown('</div></div></div>', unsafe_allow_html=True)

    b1, b2, b3 = st.columns([1, 1, 1])
    with b1:
        if st.button("翻开下一张"):
            if reveal < 2:
                st.session_state["reveal_index"] = reveal + 1
                st.session_state["reading"] = None
                st.session_state["reading_is_deep"] = False
                st.session_state["stage"] = "draw"
                st.rerun()
            else:
                st.info("已经全部翻开～")
    with b2:
        if st.button("↩️ 撤销上一张"):
            if reveal >= 0:
                st.session_state["reveal_index"] = reveal - 1
                st.session_state["reading"] = None
                st.session_state["reading_is_deep"] = False
                st.session_state["stage"] = "draw"
                st.rerun()
            else:
                st.info("还没有翻开任何牌～")
    with b3:
        if st.button("重新抽一组"):
            st.session_state["drawn_cards"] = []
            st.session_state["reveal_index"] = -1
            st.session_state["reading"] = None
            st.session_state["reading_is_deep"] = False
            st.session_state["stage"] = "followup"
            st.rerun()

    st.markdown("### 已翻开的牌")
    pos_names = ["过去", "现在", "未来"]
    for i in range(3):
        if i <= reveal:
            c = drawn[i]
            st.markdown(
                f"""<div class="tarot-card revealed-anim">
<span class="badge">{c.get('pos_label','')}</span><b>{c['name']}</b>（{c['position']}）
<div class="small">已翻开</div>
</div>""",
                unsafe_allow_html=True,
            )
            if show_base:
                st.caption(f"基础牌义：{c['meaning']}")
        else:
            st.markdown(
                f"""<div class="tarot-card">
<span class="badge">{pos_names[i]}</span>未翻开
<div class="small">点击「翻开下一张」</div>
</div>""",
                unsafe_allow_html=True,
            )

    # 翻完后生成解读（优先消耗深度次数；否则走每日免费）
    if reveal >= 2 and st.session_state["reading"] is None:
        st.divider()
        st.subheader("🔮 第三步：生成解读")

        deep_left = get_deep_credits(uid)
        want_deep = deep_left > 0

        if (not want_deep) and (not can_use_free(uid)):
            st.warning("你今日免费次数已用完，且没有深度次数。请兑换一次性激活码继续。")
            show_paywall()
        else:
            with st.spinner("正在生成解读..."):
                try:
                    if want_deep:
                        if not consume_deep_credit(uid, 1):
                            st.error("深度次数不足，请兑换激活码")
                            st.stop()
                        txt = ai_deep(question, drawn, topic, tone, st.session_state["followup_answers"])
                        reading_is_deep = True
                    else:
                        txt = ai_free(question, drawn, topic, tone, st.session_state["followup_answers"])
                        inc_free_used(uid, 1)
                        reading_is_deep = False

                    data = parse_json_safely(txt)
                    if not data:
                        data = repair_json_with_model(txt)

                except Exception as e:
                    data = None
                    txt = f"解读失败：{e}"

            st.session_state["reading"] = data if data else {"raw": "（解析JSON失败，显示原始内容）\n\n" + (txt or "无返回")}
            st.session_state["reading_is_deep"] = reading_is_deep

            # history（会话内）
            st.session_state["history"].insert(0, {
                "question": question,
                "topic": topic,
                "tone": tone,
                "paid": reading_is_deep,
                "followup": st.session_state["followup_answers"],
                "cards": drawn,
                "reading": st.session_state["reading"],
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            })

            st.session_state["stage"] = "reading"
            st.rerun()

# =========================
# 10) 展示解读 + “升级为深度”按钮 + 下载报告
# =========================
if st.session_state["reading"] is not None:
    rd = st.session_state["reading"]
    is_deep = bool(st.session_state.get("reading_is_deep", False))

    st.divider()
    st.subheader("✅ 第四步：查看解读")

    # 标题
    if isinstance(rd, dict) and "raw" in rd:
        st.write(rd["raw"])
    else:
        st.markdown(f"## {rd.get('one_line','') or ''}")

        kws = rd.get("keywords_used", [])
        if kws:
            st.caption("关键词：" + " / ".join(kws))

        uc = rd.get("user_context", "")
        if uc:
            st.markdown("### 【我理解你的处境】")
            st.write(uc)

        overall = rd.get("overall", [])
        if overall:
            st.markdown("### 【整体能量】")
            for s in overall:
                st.markdown(f"- {s}")

        st.markdown("### 【逐牌解读】")
        for item in rd.get("card_readings", []):
            st.markdown(f"**{item.get('position','')}｜{item.get('card','')}（{item.get('orientation','')}）**")
            if item.get("impact"):
                st.markdown(f"- 影响点：{item.get('impact','')}")
            if item.get("signal"):
                st.markdown(f"- 迹象：{item.get('signal','')}")
            if item.get("action"):
                st.markdown(f"- 动作：{item.get('action','')}")

        advice = rd.get("advice", [])
        if advice:
            st.markdown("### 【建议】")
            for a in advice:
                st.markdown(f"- {a}")

        signals = rd.get("signals_to_watch", [])
        if signals:
            st.markdown("### 【接下来观察什么】")
            for s in signals:
                st.markdown(f"- {s}")

        plans = rd.get("if_then_plan", [])
        if plans:
            st.markdown("### 【如果…那么…】")
            for p in plans:
                st.markdown(f"- {p}")

        plan7 = rd.get("plan_7_days", [])
        if plan7:
            st.markdown("### 【7天行动计划】")
            for i, x in enumerate(plan7, start=1):
                st.markdown(f"- Day {i}: {x}")

        caution = rd.get("caution", [])
        if caution:
            st.markdown("### 【提醒】")
            for c in caution:
                st.markdown(f"- {c}")

    # 下载报告（都要）
    st.divider()
    st.markdown("### 📥 下载报告")
    json_bytes = json.dumps(rd, ensure_ascii=False, indent=2).encode("utf-8")
    txt_bytes = reading_to_text(rd).encode("utf-8")
    st.download_button("下载 JSON（结构化）", data=json_bytes, file_name="tarot_reading.json", mime="application/json")
    st.download_button("下载 TXT（可读版）", data=txt_bytes, file_name="tarot_reading.txt", mime="text/plain")

    # ✅ “升级为深度解读”按钮（都要）
    # 只有当前结果非深度，并且用户有深度次数时才显示
    if (not is_deep) and (get_deep_credits(uid) > 0):
        st.divider()
        st.markdown("### 💎 升级本次为深度解读（不重抽牌）")
        st.caption("将使用同一组牌与同一问题，生成更具体的行动步骤 / 观察信号 / 7天计划。")
        if st.button("升级为深度解读（消耗 1 次深度）"):
            if not consume_deep_credit(uid, 1):
                st.error("深度次数不足，请先兑换激活码。")
            else:
                with st.spinner("正在升级为深度解读..."):
                    try:
                        cards = st.session_state.get("drawn_cards", [])
                        fu = st.session_state.get("followup_answers", {})
                        txt = ai_deep(question, cards, topic, tone, fu)
                        data = parse_json_safely(txt) or repair_json_with_model(txt)
                    except Exception as e:
                        data = {"raw": f"升级失败：{e}"}

                st.session_state["reading"] = data
                st.session_state["reading_is_deep"] = True
                st.session_state["history"].insert(0, {
                    "question": question,
                    "topic": topic,
                    "tone": tone,
                    "paid": True,
                    "followup": st.session_state.get("followup_answers", {}),
                    "cards": st.session_state.get("drawn_cards", []),
                    "reading": st.session_state["reading"],
                    "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                })
                st.success("已升级为深度解读 ✅")
                st.rerun()

    # 没有深度次数时的转化提示
    if (not is_deep) and (get_deep_credits(uid) <= 0):
        st.divider()
        st.markdown("### 🌙 想要更具体的深度解读？")
        st.write("兑换一次性激活码即可获得 **深度次数 +1**，并可直接升级本次结果（不重抽牌）。")
        show_paywall()

# =========================
# 11) 历史（会话内）
# =========================
st.divider()
st.subheader("📜 抽牌记录（本次打开页面期间）")
c1, c2 = st.columns([1, 2])
with c1:
    if st.button("清空记录"):
        st.session_state["history"] = []
        st.rerun()
with c2:
    st.caption("提示：记录仅在当前会话中显示；计费/限免/次数是写入SQLite的。")

if st.session_state["history"]:
    for idx, h in enumerate(st.session_state["history"][:8], start=1):
        tag = "💎深度" if h.get("paid") else "🆓免费"
        st.markdown(f"### 记录 {idx}  {tag}")
        st.markdown(f"**时间：** {h.get('ts','')}")
        st.markdown(f"**问题：** {h.get('question','')}")
        st.markdown(f"**类型/风格：** {h.get('topic','')} / {h.get('tone','')}")
        fu = h.get("followup", {})
        if fu:
            with st.expander("追问答案"):
                for k, v in fu.items():
                    st.markdown(f"- {k}：{v}")
        for c in h.get("cards", []):
            st.markdown(f"- {c.get('pos_label','')} {c.get('name','')}（{c.get('position','')}）")
        with st.expander("查看解读摘要"):
            r = h.get("reading", {})
            if isinstance(r, dict) and "raw" not in r:
                st.markdown(f"**一句话结论：** {r.get('one_line','')}")
                for a in (r.get("advice") or [])[:3]:
                    st.markdown(f"- {a}")
            else:
                st.write(reading_to_text(r))
else:
    st.caption("还没有记录，先按流程体验一次～")
