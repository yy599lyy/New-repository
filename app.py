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
ARK_API_KEY = st.secrets.get("ARK_API_KEY") or os.getenv("ARK_API_KEY")
ARK_BASE_URL = st.secrets.get("ARK_BASE_URL") or os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
MODEL_NAME = st.secrets.get("ARK_MODEL") or os.getenv("ARK_MODEL")

client = OpenAI(api_key=ARK_API_KEY, base_url=ARK_BASE_URL)

# =========================
# 1) 牌库
# =========================
BASE_DIR = pathlib.Path(__file__).parent
CARDS_PATH = BASE_DIR / "cards.json"
CARD_BACK_PATH = BASE_DIR / "card_back.png"

def load_cards():
    with open(CARDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CARDS = load_cards()

def make_card(card_obj):
    """给一张牌随机正逆位，并生成基础牌义"""
    is_reversed = random.choice([True, False])
    meaning = card_obj["reversed"] if is_reversed else card_obj["upright"]
    return {
        "name": card_obj["name"],
        "position": "逆位" if is_reversed else "正位",
        "meaning": meaning,
    }

# =========================
# 2) 解读：更具体的 JSON 结构
# =========================
def ai_reading_specific(question: str, spread_name: str, drawn_cards: list, topic: str, tone: str) -> str:
    prompt = f"""
你是一位专业塔罗解读师。风格：{tone}。问题类型：{topic}。
你必须针对用户的【具体问题】给出【具体、可执行、可验证】的解读。
请输出【严格JSON】，不要输出任何多余文字、不要markdown、不要代码块。

你需要做到：
1) 从用户问题中提炼 3-6 个关键词，并在输出中明确使用（keywords_used）
2) 每张牌解读必须包含：影响点（impact）、你建议关注的迹象/证据（signal）、可执行动作（action）
3) 给出 3 条“未来要观察的信号”（signals_to_watch）
4) 给出 2 条“如果...那么...”的应对策略（if_then_plan）
5) 不做“必然预测”，用“倾向/可能/建议”
6) 不编造牌面之外的细节（不凭空说具体人物/金额/日期）
7) 不提供医疗/法律/投资具体指令；若涉及，给安全提示与建议寻求专业人士

JSON字段（必须全部包含）：
- one_line: 一句话结论（<=22字，必须贴题）
- keywords_used: 数组（3-6个关键词）
- overall: 数组（2句即可，越凝练越好）
- card_readings: 数组，长度等于抽到的牌数；每个元素包含：
    - position: 位置（过去/现在/未来）
    - card: 牌名
    - orientation: 正位/逆位
    - impact: 这张牌对【该位置】与【该问题】意味着什么（1-2句）
    - signal: 你建议用户接下来观察的“迹象/证据”（1-2句，必须可观察）
    - action: 建议用户做的“具体动作”（1-2句，必须可执行）
- advice: 3条可执行建议（数组，每条尽量具体）
- signals_to_watch: 3条（数组，必须可观察）
- if_then_plan: 2条（数组，格式必须是“如果…那么…”）
- caution: 1-2条提醒（数组）

用户问题：{question}
牌阵：{spread_name}
抽到的牌（含基础牌义）：{json.dumps(drawn_cards, ensure_ascii=False)}
"""
    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.45,
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
# 3) UI 基础样式（保留沉浸感）
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
.block-container { padding-top: 1.4rem; max-width: 1020px; }
h1, h2, h3 { letter-spacing: 0.5px; }

section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.03));
  border-right: 1px solid rgba(255,255,255,0.10);
}
section[data-testid="stSidebar"] * { color: rgba(255,255,255,0.92) !important; }

.tarot-card {
  border: 1px solid rgba(255,255,255,0.16);
  border-radius: 18px;
  padding: 12px 12px 10px 12px;
  background: rgba(255,255,255,0.04);
  box-shadow: 0 16px 45px rgba(0,0,0,0.30),
              0 0 0 1px rgba(180,120,255,0.06) inset;
  backdrop-filter: blur(8px);
}
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
</style>
""",
    unsafe_allow_html=True,
)

st.title("🔮 塔罗占卜（互动选牌版）")
st.caption("更接近线下：你从桌面牌背中挑选 3 张（过去/现在/未来），再生成更具体的解读。")

# =========================
# 4) 状态初始化
# =========================
if "history" not in st.session_state:
    st.session_state["history"] = []

if "table_cards" not in st.session_state:
    st.session_state["table_cards"] = None  # 桌面可选牌（列表）
if "picked_idx" not in st.session_state:
    st.session_state["picked_idx"] = []     # 已选索引（按顺序）
if "reading" not in st.session_state:
    st.session_state["reading"] = None

# =========================
# 5) 设置区
# =========================
st.sidebar.header("🧭 设置")
topic = st.sidebar.selectbox("问题类型", ["综合", "恋爱", "事业", "学业", "自我成长"])
tone = st.sidebar.selectbox("解读风格", ["温和", "直接", "治愈"])
show_base_meaning = st.sidebar.checkbox("显示基础牌义", value=True)

table_size = st.sidebar.slider("桌面牌数量（越大越像线下，但越难点）", 9, 24, 15)
shuffle_seconds = st.sidebar.slider("洗牌时长（秒）", 0, 5, 1)

st.info("📱 手机用户：如果侧边栏不明显，直接滚动操作即可。先输入问题 → 洗牌 → 依次选择 3 张。")

question = st.text_input("你想问什么？", placeholder="例如：我该不该换工作？这段关系未来一个月怎么走？")

# =========================
# 6) 洗牌：生成桌面牌
# =========================
col_a, col_b = st.columns([1, 1])

with col_a:
    if st.button("🌀 洗牌并铺牌"):
        if not question.strip():
            st.warning("先写下你的问题～")
        else:
            if shuffle_seconds > 0:
                with st.spinner("正在洗牌..."):
                    time.sleep(shuffle_seconds)

            # 从全牌库随机抽 table_size 张作为桌面候选牌（每张带正逆位）
            sampled = random.sample(CARDS, k=min(table_size, len(CARDS)))
            st.session_state["table_cards"] = [make_card(c) for c in sampled]
            st.session_state["picked_idx"] = []
            st.session_state["reading"] = None

with col_b:
    if st.button("🔄 重新开始（清空）"):
        st.session_state["table_cards"] = None
        st.session_state["picked_idx"] = []
        st.session_state["reading"] = None

# =========================
# 7) 选牌区（互动）
# =========================
st.subheader("🃏 选择你的三张牌（过去 / 现在 / 未来）")

pos_order = ["过去", "现在", "未来"]
pick_count = len(st.session_state["picked_idx"])
next_pos = pos_order[pick_count] if pick_count < 3 else None

if st.session_state["table_cards"] is None:
    st.caption("点击「🌀 洗牌并铺牌」后，会出现一桌牌背。你将按顺序选择 3 张。")
else:
    st.markdown(f"**当前进度：已选 {pick_count}/3**" + (f" ，下一张请选择：**{next_pos}**" if next_pos else " ✅ 已选满"))

    # 把桌面牌做成网格（3列/手机更好点）
    cols = st.columns(3, gap="small")
    for i, card in enumerate(st.session_state["table_cards"]):
        col = cols[i % 3]
        with col:
            picked = i in st.session_state["picked_idx"]

            # 已选：翻开显示
            if picked:
                order_idx = st.session_state["picked_idx"].index(i)
                pos_label = pos_order[order_idx]
                st.markdown(
                    f"""
<div class="tarot-card revealed-anim">
  <div><span class="badge">{pos_label}</span> {card['name']}（{card['position']}）</div>
  <div class="small">已选择</div>
</div>
""",
                    unsafe_allow_html=True,
                )
                if show_base_meaning:
                    st.caption(f"基础牌义：{card['meaning']}")
            else:
                # 未选：显示牌背 + 选择按钮
                if CARD_BACK_PATH.exists():
                    st.image(str(CARD_BACK_PATH), use_container_width=True)
                else:
                    st.markdown("🂠 牌背（请放 card_back.png）")

                disabled = pick_count >= 3
                if st.button(f"选择第 {i+1} 张", key=f"pick_{i}", disabled=disabled):
                    st.session_state["picked_idx"].append(i)
                    st.session_state["reading"] = None
                    st.rerun()

    # 选满 3 张后，生成解读
    if len(st.session_state["picked_idx"]) == 3 and st.session_state["reading"] is None:
        chosen_cards = []
        for order, idx in enumerate(st.session_state["picked_idx"]):
            c = dict(st.session_state["table_cards"][idx])
            c["pos_label"] = pos_order[order]
            chosen_cards.append(c)

        st.divider()
        st.subheader("🔮 AI 解读（更具体）")
        with st.spinner("正在生成更具体的解读..."):
            try:
                txt = ai_reading_specific(question, "三牌（过去-现在-未来）", chosen_cards, topic, tone)
                data = parse_json_safely(txt)
            except Exception as e:
                data = None
                txt = f"解读失败：{e}"

        if not data:
            st.session_state["reading"] = {"raw": "（解析JSON失败，显示原始内容）\n\n" + (txt or "无返回")}
        else:
            st.session_state["reading"] = data
            st.session_state["history"].insert(0, {
                "question": question,
                "topic": topic,
                "tone": tone,
                "spread": "三牌（过去-现在-未来）",
                "cards": chosen_cards,
                "reading": data
            })

# =========================
# 8) 展示解读
# =========================
if st.session_state["reading"] is not None:
    rd = st.session_state["reading"]
    if isinstance(rd, dict) and "raw" in rd:
        st.write(rd["raw"])
    else:
        st.markdown(f"## {rd.get('one_line','') or ''}")

        kws = rd.get("keywords_used", [])
        if kws:
            st.caption("关键词：" + " / ".join(kws))

        overall = rd.get("overall", [])
        if overall:
            st.markdown("### 【整体能量】")
            for s in overall:
                st.markdown(f"- {s}")

        st.markdown("### 【逐牌解读：影响点 / 迹象 / 动作】")
        for item in rd.get("card_readings", []):
            st.markdown(f"**{item.get('position','')}｜{item.get('card','')}（{item.get('orientation','')}）**")
            st.markdown(f"- 影响点：{item.get('impact','')}")
            st.markdown(f"- 迹象：{item.get('signal','')}")
            st.markdown(f"- 动作：{item.get('action','')}")

        st.markdown("### 【建议】")
        for a in rd.get("advice", []):
            st.markdown(f"- {a}")

        st.markdown("### 【接下来观察什么】")
        for s in rd.get("signals_to_watch", []):
            st.markdown(f"- {s}")

        st.markdown("### 【如果…那么…】")
        for p in rd.get("if_then_plan", []):
            st.markdown(f"- {p}")

        st.markdown("### 【提醒】")
        for c in rd.get("caution", []):
            st.markdown(f"- {c}")

# =========================
# 9) 历史记录
# =========================
st.divider()
st.subheader("📜 抽牌记录（本次打开页面期间）")

col1, col2 = st.columns([1, 1])
with col1:
    if st.button("清空记录"):
        st.session_state["history"] = []
with col2:
    st.caption("提示：刷新页面记录会重置（后面可升级为永久保存）")

if st.session_state["history"]:
    for idx, h in enumerate(st.session_state["history"][:8], start=1):
        st.markdown(f"### 记录 {idx}")
        st.markdown(f"**问题：** {h['question']}")
        st.markdown(f"**类型：** {h.get('topic','综合')} | **风格：** {h.get('tone','温和')}")

        for c in h["cards"]:
            st.markdown(f"- {c.get('pos_label','')} {c['name']}（{c['position']}）")

        with st.expander("查看解读"):
            r = h["reading"]
            if isinstance(r, dict):
                st.markdown(f"**一句话结论：** {r.get('one_line','')}")
                st.markdown("**建议：**")
                for a in r.get("advice", []):
                    st.markdown(f"- {a}")
            else:
                st.write(r)
else:
    st.caption("还没有记录，先洗牌选一次～")
