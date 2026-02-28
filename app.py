import os
import json
import random
import pathlib
import time
import re
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

@st.cache_data
def load_cards():
    with open(CARDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CARDS = load_cards()

def make_card(card_obj):
    is_reversed = random.choice([True, False])
    meaning = card_obj["reversed"] if is_reversed else card_obj["upright"]
    return {
        "name": card_obj["name"],
        "position": "逆位" if is_reversed else "正位",
        "meaning": meaning,
    }

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
# 3) AI 解读
# =========================
def ai_reading_specific(question: str, drawn_cards: list, topic: str, tone: str, followup_answers: dict) -> str:
    prompt = f"""
你是一位专业塔罗解读师。风格：{tone}。问题类型：{topic}。
你必须针对用户的【具体问题】给出【具体、可执行、可验证】的解读。
用户回答了两个澄清问题，你必须纳入解读逻辑，像真人一样贴近用户处境。

请输出【严格JSON】，不要输出任何多余文字、不要markdown、不要代码块。

必须做到：
1) 从用户问题中提炼 3-6 个关键词（keywords_used），并在输出中明确使用
2) 每张牌解读必须包含：影响点（impact）、可观察迹象/证据（signal）、可执行动作（action）
3) 给出 3 条“未来要观察的信号”（signals_to_watch）
4) 给出 2 条“如果...那么...”策略（if_then_plan）
5) 不做“必然预测”，用“倾向/可能/建议”
6) 不编造牌面之外细节（不凭空说具体人物/金额/日期）
7) 不提供医疗/法律/投资具体指令；若涉及，给安全提示与建议寻求专业人士

JSON字段（必须全部包含）：
- one_line: 一句话结论（<=22字，必须贴题）
- keywords_used: 数组（3-6个关键词）
- user_context: 1-2句复述处境（必须引用追问答案）
- overall: 数组（2句）
- card_readings: 数组(3个)，每个元素：
    - position: 过去/现在/未来
    - card: 牌名
    - orientation: 正位/逆位
    - impact: 1-2句
    - signal: 1-2句（可观察）
    - action: 1-2句（可执行）
- advice: 3条（数组）
- signals_to_watch: 3条（数组）
- if_then_plan: 2条（数组，必须“如果…那么…”）
- caution: 1-2条（数组）

用户问题：{question}

追问答案（必须使用）：
{json.dumps(followup_answers, ensure_ascii=False)}

抽到的牌（含位置与基础牌义）：
{json.dumps(drawn_cards, ensure_ascii=False)}
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
        pass
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
    except Exception:
        pass
    try:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return None

# =========================
# 4) UI 样式
# =========================
st.set_page_config(page_title="塔罗占卜", page_icon="🔮", initial_sidebar_state="collapsed")

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
.block-container { padding-top: 1.1rem; max-width: 980px; }
h1, h2, h3 { letter-spacing: 0.5px; }

.tarot-card {
  border: 1px solid rgba(255,255,255,0.16);
  border-radius: 18px;
  padding: 12px;
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

.card-back-placeholder {
  background: linear-gradient(135deg,#2a1b3d,#1a0f2a);
  border: 2px solid rgba(122,95,160,0.6);
  border-radius: 14px;
  height: 160px;
  display:flex;
  align-items:center;
  justify-content:center;
  color:#bbaadd;
  font-size:2.2rem;
}

/* “牌堆”视觉 */
.stack-wrap{ display:flex; justify-content:center; margin: 8px 0 0 0; }
.stack{ width: 210px; position:relative; }
.stack::before, .stack::after{
  content:""; position:absolute; inset:0;
  border-radius: 16px; background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.10);
  transform: translate(10px, 10px); z-index:0;
}
.stack::after{ transform: translate(6px,6px); z-index:1; }
.stack-inner{
  position:relative; z-index:2;
  border-radius:16px; overflow:hidden;
  border: 1px solid rgba(255,255,255,0.16);
  box-shadow: 0 18px 50px rgba(0,0,0,0.35);
}

@keyframes flipIn {
  0%   { transform: perspective(900px) rotateY(70deg) translateY(10px); opacity: 0; }
  60%  { transform: perspective(900px) rotateY(-10deg) translateY(0px); opacity: 1; }
  100% { transform: perspective(900px) rotateY(0deg) translateY(0px); opacity: 1; }
}
.revealed-anim { animation: flipIn 650ms ease; transform-origin: center; }

@media (max-width:600px){
  .stack{ width: 180px; }
  .card-back-placeholder{ height: 140px; font-size: 2rem; }
  .stButton>button{ padding: 9px 12px !important; font-size: 16px !important; }
}
</style>
""",
    unsafe_allow_html=True,
)

def do_shuffle(seconds: int):
    if seconds <= 0:
        return
    p = st.progress(0.0)
    steps = max(1, int(seconds * 10))
    for i in range(steps):
        time.sleep(seconds / steps)
        p.progress((i + 1) / steps)
    p.empty()

def render_card_back():
    if CARD_BACK_PATH.exists():
        st.image(str(CARD_BACK_PATH), use_container_width=True)
    else:
        st.markdown('<div class="card-back-placeholder">🂠</div>', unsafe_allow_html=True)

# =========================
# 5) 状态
# =========================
if "history" not in st.session_state:
    st.session_state["history"] = []
if "stage" not in st.session_state:
    st.session_state["stage"] = "ask"  # ask -> followup -> draw -> reading
if "followup_answers" not in st.session_state:
    st.session_state["followup_answers"] = {}
if "deck" not in st.session_state:
    st.session_state["deck"] = None
if "drawn_cards" not in st.session_state:
    st.session_state["drawn_cards"] = []
if "reveal_index" not in st.session_state:
    st.session_state["reveal_index"] = -1  # -1 表示还没翻开任何牌
if "reading" not in st.session_state:
    st.session_state["reading"] = None

# =========================
# 6) 顶部步骤条
# =========================
steps = ["写问题", "回答追问", "一键抽牌并翻牌", "查看解读"]
stage_map = {"ask": 0, "followup": 1, "draw": 2, "reading": 3}
cur = stage_map.get(st.session_state.get("stage", "ask"), 0)
st.markdown(f"**步骤：{cur+1}/{len(steps)} — {steps[cur]}**")
st.progress((cur + 1) / len(steps))

# =========================
# 7) 页面主体
# =========================
st.title("🔮 塔罗占卜（点击抽牌·逐张翻牌）")
st.caption("手机优化：不铺开大图卡墙，只显示一叠牌背 + 逐张翻开（过去/现在/未来）。")

# 侧边栏
st.sidebar.header("🧭 设置")
topic = st.sidebar.selectbox("问题类型", ["综合", "恋爱", "事业", "学业", "自我成长"])
tone = st.sidebar.selectbox("解读风格", ["温和", "直接", "治愈"])
show_base_meaning = st.sidebar.checkbox("显示基础牌义", value=True)
shuffle_seconds = st.sidebar.slider("洗牌动画时长（秒）", 0, 5, 1)

st.info("📱 手机用户：点“一键抽牌”后，再点“翻开下一张”，依次翻出过去/现在/未来。")

question = st.text_input("你想问什么？", placeholder="例如：我该不该换工作？这段关系未来一个月怎么走？")

colx, coly = st.columns([1, 1])
with colx:
    if st.button("➡️ 下一步：回答两个关键问题"):
        if not question.strip():
            st.warning("先写下你的问题～")
        else:
            st.session_state["stage"] = "followup"
            st.session_state["reading"] = None
            st.session_state["deck"] = None
            st.session_state["drawn_cards"] = []
            st.session_state["reveal_index"] = -1
            st.session_state["followup_answers"] = {}
            st.rerun()
with coly:
    if st.button("🔄 重新开始（清空）"):
        st.session_state["stage"] = "ask"
        st.session_state["reading"] = None
        st.session_state["deck"] = None
        st.session_state["drawn_cards"] = []
        st.session_state["reveal_index"] = -1
        st.session_state["followup_answers"] = {}
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
            # 洗牌并抽 3 张（不铺开）
            shuffled = random.sample(CARDS, k=len(CARDS))
            deck = [make_card(c) for c in shuffled]
            pos_order = ["过去", "现在", "未来"]
            drawn = []
            for i in range(3):
                card = dict(deck[i])
                card["pos_label"] = pos_order[i]
                drawn.append(card)
            st.session_state["deck"] = deck
            st.session_state["drawn_cards"] = drawn
            st.session_state["reveal_index"] = -1
            st.session_state["reading"] = None
            st.session_state["stage"] = "draw"
            st.rerun()
    with c2:
        if st.button("跳过追问并抽牌（可选）"):
            st.session_state["followup_answers"] = {}
            do_shuffle(shuffle_seconds)
            shuffled = random.sample(CARDS, k=len(CARDS))
            deck = [make_card(c) for c in shuffled]
            pos_order = ["过去", "现在", "未来"]
            drawn = []
            for i in range(3):
                card = dict(deck[i])
                card["pos_label"] = pos_order[i]
                drawn.append(card)
            st.session_state["deck"] = deck
            st.session_state["drawn_cards"] = drawn
            st.session_state["reveal_index"] = -1
            st.session_state["reading"] = None
            st.session_state["stage"] = "draw"
            st.rerun()

# 抽牌&翻牌阶段（不铺开卡墙）
if st.session_state["stage"] in ["draw", "reading"] and st.session_state["drawn_cards"]:
    st.subheader("🃏 第二步：逐张翻牌（过去 / 现在 / 未来）")

    drawn = st.session_state["drawn_cards"]
    reveal = st.session_state["reveal_index"]

    # 牌堆展示（固定大小，手机不占屏）
    st.markdown('<div class="stack-wrap"><div class="stack"><div class="stack-inner">', unsafe_allow_html=True)
    render_card_back()
    st.markdown('</div></div></div>', unsafe_allow_html=True)

    # 控制按钮
    b1, b2, b3 = st.columns([1,1,1])
    with b1:
        if st.button("翻开下一张"):
            if reveal < 2:
                st.session_state["reveal_index"] = reveal + 1
                st.session_state["reading"] = None
                st.session_state["stage"] = "draw"
                st.rerun()
            else:
                st.info("已经全部翻开～")
    with b2:
        if st.button("↩️ 撤销上一张"):
            if reveal >= 0:
                st.session_state["reveal_index"] = reveal - 1
                st.session_state["reading"] = None
                st.session_state["stage"] = "draw"
                st.rerun()
            else:
                st.info("还没有翻开任何牌～")
    with b3:
        if st.button("重新抽一组"):
            st.session_state["drawn_cards"] = []
            st.session_state["reveal_index"] = -1
            st.session_state["reading"] = None
            st.session_state["stage"] = "followup"
            st.rerun()

    # 展示已翻开的牌
    st.markdown("### 已翻开的牌")
    for i in range(3):
        if i <= reveal:
            c = drawn[i]
            st.markdown(
                f"""
<div class="tarot-card revealed-anim">
  <div><span class="badge">{c.get('pos_label','')}</span> {c['name']}（{c['position']}）</div>
  <div class="small">已翻开</div>
</div>
""",
                unsafe_allow_html=True,
            )
            if show_base_meaning:
                st.caption(f"基础牌义：{c['meaning']}")
        else:
            st.markdown(
                f"""
<div class="tarot-card">
  <div><span class="badge">{['过去','现在','未来'][i]}</span> 未翻开</div>
  <div class="small">点击「翻开下一张」</div>
</div>
""",
                unsafe_allow_html=True,
            )

    # 翻完后生成解读
    if reveal >= 2 and st.session_state["reading"] is None:
        st.divider()
        st.subheader("🔮 第三步：生成解读")
        with st.spinner("正在生成更具体的解读..."):
            try:
                txt = ai_reading_specific(
                    question=question,
                    drawn_cards=drawn,
                    topic=topic,
                    tone=tone,
                    followup_answers=st.session_state["followup_answers"],
                )
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
                "spread": "点击抽牌三牌（过去-现在-未来）",
                "followup": st.session_state["followup_answers"],
                "cards": drawn,
                "reading": data
            })

        st.session_state["stage"] = "reading"
        st.rerun()

# 展示解读
if st.session_state["reading"] is not None:
    rd = st.session_state["reading"]
    st.divider()
    st.subheader("✅ 第四步：查看解读")

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

# 历史
st.divider()
st.subheader("📜 抽牌记录（本次打开页面期间）")
if st.button("清空记录"):
    st.session_state["history"] = []

if st.session_state["history"]:
    for idx, h in enumerate(st.session_state["history"][:6], start=1):
        st.markdown(f"### 记录 {idx}")
        st.markdown(f"**问题：** {h['question']}")
        fu = h.get("followup", {})
        if fu:
            st.markdown("**追问：**")
            for k, v in fu.items():
                st.markdown(f"- {k}：{v}")
        for c in h["cards"]:
            st.markdown(f"- {c.get('pos_label','')} {c['name']}（{c['position']}）")
        with st.expander("查看解读摘要"):
            r = h["reading"]
            if isinstance(r, dict):
                st.markdown(f"**一句话结论：** {r.get('one_line','')}")
                for a in r.get("advice", []):
                    st.markdown(f"- {a}")
            else:
                st.write(r)
else:
    st.caption("还没有记录，先按流程体验一次～")
