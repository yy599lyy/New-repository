import os
import json
import random
import pathlib
import time
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

# =========================
# 0) 基础配置
# =========================
load_dotenv()

# 云端部署用 st.secrets；本地用 .env 兜底
ARK_API_KEY = st.secrets.get("ARK_API_KEY") or os.getenv("ARK_API_KEY")
ARK_BASE_URL = st.secrets.get("ARK_BASE_URL") or os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
MODEL_NAME = st.secrets.get("ARK_MODEL") or os.getenv("ARK_MODEL")

client = OpenAI(api_key=ARK_API_KEY, base_url=ARK_BASE_URL)

# =========================
# 1) 读取牌库 cards.json
# =========================
BASE_DIR = pathlib.Path(__file__).parent
CARDS_PATH = BASE_DIR / "cards.json"
CARD_BACK_PATH = BASE_DIR / "card_back.png"

def load_cards():
    with open(CARDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CARDS = load_cards()

def draw_card():
    card = random.choice(CARDS)
    is_reversed = random.choice([True, False])
    meaning = card["reversed"] if is_reversed else card["upright"]
    return {
        "name": card["name"],
        "position": "逆位" if is_reversed else "正位",
        "meaning": meaning,
    }

# =========================
# 2) 牌阵配置
# =========================
SPREAD_POSITIONS = {
    "单牌（今日指引）": ["今日指引"],
    "圣三角（三牌：过去-现在-未来）": ["过去", "现在", "未来"],
}

def draw_spread(spread_name: str):
    positions = SPREAD_POSITIONS.get(spread_name, ["今日指引"])
    cards = []
    for p in positions:
        c = draw_card()
        c["pos_label"] = p
        cards.append(c)
    return cards

# =========================
# 3) AI 解读：严格输出 JSON
# =========================
def ai_reading(question: str, spread_name: str, drawn_cards: list, topic: str, tone: str) -> str:
    prompt = f"""
你是一位专业塔罗解读师。风格：{tone}。问题类型：{topic}。
请基于抽到的牌输出【严格JSON】，不要输出任何多余文字、不要markdown、不要代码块。

JSON字段要求（必须全部包含）：
- one_line: 一句话结论（<=20字）
- overall: 整体能量（2-4句，数组，每句一条）
- card_readings: 数组，长度等于抽到的牌数；每个元素包含：
    - position: 位置（如：过去/现在/未来/今日指引）
    - card: 牌名
    - orientation: 正位/逆位
    - meaning: 用你的话解释这张牌在该位置对问题的含义（2-3句）
- advice: 3条可执行建议（数组）
- caution: 1-2条提醒/盲点/风险（数组）

重要规则：
- 不做“必然预测”，用“倾向/可能/建议”
- 不编造牌面之外的细节（不凭空说具体人物/金额/日期）
- 不提供医疗/法律/投资具体指令；若涉及，给安全提示与建议寻求专业人士

用户问题：{question}
牌阵：{spread_name}
抽到的牌（含位置与基础牌义）：{json.dumps(drawn_cards, ensure_ascii=False)}
"""
    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
    )
    return resp.choices[0].message.content

def parse_json_safely(text: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end + 1])
        except Exception:
            return None
    return None

# =========================
# 4) UI + 样式（深色氛围 + 动画）
# =========================
st.set_page_config(page_title="塔罗占卜", page_icon="🔮")

st.markdown(
    """
<style>
.stApp {
  background:
    radial-gradient(900px 600px at 10% 10%, rgba(140, 82, 255, 0.22), transparent 60%),
    radial-gradient(900px 600px at 90% 20%, rgba(0, 255, 210, 0.10), transparent 55%),
    radial-gradient(900px 600px at 30% 90%, rgba(255, 110, 199, 0.12), transparent 55%),
    linear-gradient(180deg, #0b0b14 0%, #080812 40%, #050510 100%);
  color: rgba(255,255,255,0.92);
}
.block-container { padding-top: 1.6rem; max-width: 1020px; }
h1, h2, h3 { letter-spacing: 0.5px; }

section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.03));
  border-right: 1px solid rgba(255,255,255,0.10);
}
section[data-testid="stSidebar"] * { color: rgba(255,255,255,0.92) !important; }
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span { opacity: 1 !important; font-weight: 600 !important; }

div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div {
  background: rgba(255,255,255,0.06) !important;
  border: 1px solid rgba(255,255,255,0.16) !important;
}

.stButton > button {
  border-radius: 12px !important;
  border: 1px solid rgba(255,255,255,0.16) !important;
  background: linear-gradient(180deg, rgba(140,82,255,0.24), rgba(140,82,255,0.10)) !important;
  color: rgba(255,255,255,0.92) !important;
  box-shadow: 0 10px 30px rgba(0,0,0,0.25);
}
.stButton > button:hover {
  transform: translateY(-1px);
  box-shadow: 0 16px 42px rgba(0,0,0,0.35), 0 0 18px rgba(140,82,255,0.22);
}

div[data-testid="stProgressBar"] > div > div {
  background: linear-gradient(90deg, rgba(140,82,255,0.95), rgba(0,255,210,0.70)) !important;
}

.tarot-card {
  border: 1px solid rgba(255,255,255,0.16);
  border-radius: 18px;
  padding: 14px 14px 10px 14px;
  background: rgba(255,255,255,0.04);
  box-shadow: 0 16px 45px rgba(0,0,0,0.30),
              0 0 0 1px rgba(180,120,255,0.06) inset;
  backdrop-filter: blur(8px);
}
.tarot-title { font-weight: 800; font-size: 1.05rem; margin-bottom: 6px; }
.badge {
  display: inline-block;
  font-size: 0.80rem;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.18);
  background: rgba(255,255,255,0.06);
  margin-right: 8px;
}
.small { font-size: 0.88rem; opacity: 0.88; }

@keyframes flipIn {
  0%   { transform: perspective(900px) rotateY(70deg) translateY(10px); opacity: 0; }
  60%  { transform: perspective(900px) rotateY(-10deg) translateY(0px); opacity: 1; }
  100% { transform: perspective(900px) rotateY(0deg) translateY(0px); opacity: 1; }
}
.revealed-anim { animation: flipIn 650ms ease; transform-origin: center; }

@keyframes fadeIn {
  from { opacity: 0.25; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}
.back-anim { animation: fadeIn 450ms ease; }
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# 5) 页面内容
# =========================
st.title("🔮 塔罗占卜（沉浸版）")

# ✅ 手机引导提示（非常有效）
st.info("📱 手机用户：左上角有一个小箭头/菜单可以打开设置侧边栏；也可以直接用下面的「快速设置」。")

# ---- 会话状态初始化：把设置也放 session_state，保证同步 ----
DEFAULTS = {
    "topic": "综合",
    "spread": "圣三角（三牌：过去-现在-未来）",
    "tone": "温和",
    "show_base_meaning": True,
    "shuffle_seconds": 2,
    "flip_seconds": 1,
    "compact_mode": True,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

if "history" not in st.session_state:
    st.session_state["history"] = []
if "current_draw" not in st.session_state:
    st.session_state["current_draw"] = None
if "reveal_index" not in st.session_state:
    st.session_state["reveal_index"] = 0
if "temp_reading" not in st.session_state:
    st.session_state["temp_reading"] = None

# ---- 侧边栏设置（会写入 session_state） ----
st.sidebar.header("🧭 占卜设置（侧边栏）")
st.session_state["topic"] = st.sidebar.selectbox(
    "问题类型",
    ["综合", "恋爱", "事业", "学业", "自我成长"],
    index=["综合", "恋爱", "事业", "学业", "自我成长"].index(st.session_state["topic"]),
)
st.session_state["spread"] = st.sidebar.selectbox(
    "牌阵",
    ["单牌（今日指引）", "圣三角（三牌：过去-现在-未来）"],
    index=["单牌（今日指引）", "圣三角（三牌：过去-现在-未来）"].index(st.session_state["spread"]),
)
st.session_state["tone"] = st.sidebar.selectbox(
    "解读风格",
    ["温和", "直接", "治愈"],
    index=["温和", "直接", "治愈"].index(st.session_state["tone"]),
)
st.session_state["show_base_meaning"] = st.sidebar.checkbox("显示基础牌义", value=st.session_state["show_base_meaning"])

st.sidebar.divider()
st.session_state["shuffle_seconds"] = st.sidebar.slider("洗牌时长（秒）", 0, 5, st.session_state["shuffle_seconds"])
st.session_state["flip_seconds"] = st.sidebar.slider("翻牌停顿（秒）", 0, 3, st.session_state["flip_seconds"])
st.session_state["compact_mode"] = st.sidebar.checkbox("紧凑布局（更像卡片墙）", value=st.session_state["compact_mode"])

# ---- ✅ 主页面“快速设置”（手机友好） ----
with st.expander("⚙️ 快速设置（手机友好：这里也能选牌阵/风格）", expanded=True):
    c1, c2 = st.columns(2)
    with c1:
        st.session_state["topic"] = st.selectbox(
            "问题类型（快速）",
            ["综合", "恋爱", "事业", "学业", "自我成长"],
            index=["综合", "恋爱", "事业", "学业", "自我成长"].index(st.session_state["topic"]),
            key="topic_main",
        )
        st.session_state["tone"] = st.selectbox(
            "解读风格（快速）",
            ["温和", "直接", "治愈"],
            index=["温和", "直接", "治愈"].index(st.session_state["tone"]),
            key="tone_main",
        )
    with c2:
        st.session_state["spread"] = st.selectbox(
            "牌阵（快速）",
            ["单牌（今日指引）", "圣三角（三牌：过去-现在-未来）"],
            index=["单牌（今日指引）", "圣三角（三牌：过去-现在-未来）"].index(st.session_state["spread"]),
            key="spread_main",
        )
        st.session_state["show_base_meaning"] = st.checkbox(
            "显示基础牌义（快速）",
            value=st.session_state["show_base_meaning"],
            key="base_meaning_main",
        )

    st.session_state["shuffle_seconds"] = st.slider(
        "洗牌时长（秒）（快速）", 0, 5, st.session_state["shuffle_seconds"], key="shuffle_main"
    )
    st.session_state["flip_seconds"] = st.slider(
        "翻牌停顿（秒）（快速）", 0, 3, st.session_state["flip_seconds"], key="flip_main"
    )
    st.session_state["compact_mode"] = st.checkbox(
        "紧凑布局（快速）", value=st.session_state["compact_mode"], key="compact_main"
    )

# ---- 仪式提示 ----
st.markdown("### 🌙 小小仪式")
st.markdown("请先安静 10 秒，默念你的问题 3 次。准备好后再开始抽牌。")

question = st.text_input(
    "你想问什么？",
    placeholder="例如：我该不该换工作？这段关系未来三个月会怎样？"
)

# ---- 按钮 ----
col_start, col_next, col_reset = st.columns([1, 1, 1])

with col_start:
    if st.button("开始抽牌"):
        if not question.strip():
            st.warning("先写下你的问题～")
        else:
            # 洗牌进度条更明显
            s = st.session_state["shuffle_seconds"]
            if s > 0:
                p = st.progress(0.0)
                with st.spinner("正在洗牌..."):
                    steps = max(1, s * 10)
                    for i in range(steps):
                        time.sleep(s / steps)
                        p.progress((i + 1) / steps)
                p.empty()

            st.session_state["current_draw"] = draw_spread(st.session_state["spread"])
            st.session_state["reveal_index"] = 0
            st.session_state["temp_reading"] = None

with col_next:
    if st.button("翻开下一张"):
        if not st.session_state["current_draw"]:
            st.info("请先点击“开始抽牌”")
        else:
            fs = st.session_state["flip_seconds"]
            if fs > 0:
                with st.spinner("翻牌中..."):
                    time.sleep(fs)

            idx = st.session_state["reveal_index"]
            last = len(st.session_state["current_draw"]) - 1
            if idx < last:
                st.session_state["reveal_index"] = idx + 1
            else:
                st.warning("已经翻完所有牌，或点击“重新抽牌 / 重置”")

with col_reset:
    if st.button("重新抽牌 / 重置"):
        st.session_state["current_draw"] = None
        st.session_state["reveal_index"] = 0
        st.session_state["temp_reading"] = None

# ---- 牌桌 ----
st.subheader("🃏 你抽到的牌（逐张翻开）")

def render_card_back():
    if CARD_BACK_PATH.exists():
        st.image(str(CARD_BACK_PATH), use_container_width=True)
    else:
        st.markdown("🂠（请放置 card_back.png）")

if st.session_state["current_draw"]:
    cards_all = st.session_state["current_draw"]
    reveal_i = st.session_state["reveal_index"]

    total = len(cards_all)
    st.progress(min(1.0, (reveal_i + 1) / max(1, total)))

    cols = st.columns(total, gap="small" if st.session_state["compact_mode"] else "large")

    for i, c in enumerate(cards_all):
        with cols[i]:
            if i <= reveal_i:
                card_html = f"""
<div class="tarot-card revealed-anim">
  <div class="tarot-title">
    <span class="badge">{c.get('pos_label','')}</span>
    {c['name']}（{c['position']}）
  </div>
  <div class="small">已翻开</div>
</div>
"""
                st.markdown(card_html, unsafe_allow_html=True)
                if st.session_state["show_base_meaning"]:
                    st.caption(f"基础牌义：{c['meaning']}")
            else:
                card_html = f"""
<div class="tarot-card back-anim">
  <div class="tarot-title">
    <span class="badge">{i+1}</span> 未翻开
  </div>
  <div class="small">请点击「翻开下一张」</div>
</div>
"""
                st.markdown(card_html, unsafe_allow_html=True)
                render_card_back()

    # 翻完后调用 AI（只调用一次）
    if reveal_i >= len(cards_all) - 1 and st.session_state["temp_reading"] is None:
        with st.spinner("正在为你组合解读，请稍等..."):
            try:
                reading_text = ai_reading(
                    question,
                    st.session_state["spread"],
                    cards_all,
                    st.session_state["topic"],
                    st.session_state["tone"],
                )
                data = parse_json_safely(reading_text)
            except Exception as e:
                data = None
                reading_text = f"解读失败：{e}"

            if not data:
                st.session_state["temp_reading"] = {"raw": "（解析JSON失败，显示原始内容）\n\n" + (reading_text or "无返回")}
            else:
                st.session_state["temp_reading"] = data
                st.session_state["history"].insert(0, {
                    "question": question,
                    "topic": st.session_state["topic"],
                    "tone": st.session_state["tone"],
                    "spread": st.session_state["spread"],
                    "cards": cards_all,
                    "reading": data
                })

    # 显示解读
    if st.session_state["temp_reading"] is not None:
        st.subheader("🔮 AI 解读")
        rd = st.session_state["temp_reading"]

        if isinstance(rd, dict) and "raw" in rd:
            st.write(rd["raw"])
        else:
            st.markdown(f"## {rd.get('one_line','') or ''}")

            overall = rd.get("overall", [])
            if overall:
                st.markdown("### 【整体能量】")
                for s in overall:
                    st.markdown(f"- {s}")

            st.markdown("### 【逐牌解读】")
            for item in rd.get("card_readings", []):
                pos = item.get("position", "")
                card = item.get("card", "")
                ori = item.get("orientation", "")
                meaning = item.get("meaning", "")
                st.markdown(f"**{pos}｜{card}（{ori}）**")
                st.write(meaning)

            st.markdown("### 【建议】")
            for a in rd.get("advice", []):
                st.markdown(f"- {a}")

            st.markdown("### 【提醒】")
            for c in rd.get("caution", []):
                st.markdown(f"- {c}")
else:
    st.info("点击「开始抽牌」开始占卜。")

# ---- 历史 ----
st.divider()
st.subheader("📜 抽牌记录（本次打开页面期间）")

col1, col2 = st.columns([1, 1])
with col1:
    if st.button("清空记录"):
        st.session_state["history"] = []
with col2:
    st.caption("提示：刷新页面记录会重置（后面可升级为永久保存）")

if st.session_state["history"]:
    for idx, h in enumerate(st.session_state["history"][:10], start=1):
        st.markdown(f"### 记录 {idx}")
        st.markdown(f"**问题：** {h['question']}")
        st.markdown(f"**类型：** {h.get('topic','综合')} | **风格：** {h.get('tone','温和')} | **牌阵：** {h.get('spread')}")

        for c in h["cards"]:
            st.markdown(f"- {c.get('pos_label','')} {c['name']}（{c['position']}）：{c['meaning']}")

        with st.expander("查看解读"):
            r = h["reading"]
            if isinstance(r, dict):
                st.markdown(f"**一句话结论：** {r.get('one_line','')}")
                st.markdown("**建议：**")
                for a in r.get("advice", []):
                    st.markdown(f"- {a}")
                st.markdown("**提醒：**")
                for c in r.get("caution", []):
                    st.markdown(f"- {c}")
            else:
                st.write(r)
else:
    st.caption("还没有记录，先抽一次牌～")
