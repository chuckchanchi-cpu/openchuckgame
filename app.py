"""《周星馳式：黐線大冒險》— Streamlit 互動小說 RPG 引擎 🎬

玩法：你開一個角色（名 + 職業），個引擎會派初始道具同能力俾你，
然後每一章都係 150-250 字場景 + 4 個選項（A 搞笑 / B 冒險神秘 / C 愛情 / D 自定）。
背後由 LLM（預設 DeepSeek）做故事引擎，隱藏數值（靈力 / 搞笑 / 心動）由引擎追蹤。

無 auto-refresh、無 polling —— 你撳掣，佢先講。
"""
import json
import os
import re
import urllib.error
import urllib.request

import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_FILE = os.path.join(HERE, "prompt.md")

APPENDIX = """

【技術規則（App 專用，玩家睇唔到）】
1. 每次回覆最尾一定要加一行狀態，格式如下（數字 = 你心入面三個數值嘅當前值，要隨劇情變化）：
【狀態】靈力:X｜搞笑:Y｜心動:Z
2. 呢行係畀 App 追蹤用嘅，唔算正文，玩家唔會見到。
3. 選項照舊用 A./B./C./D. 開頭，一個選項一行。
4. 玩家揀完之後，如果啱好係第 3 / 6 / 9... 個選擇，就係小結局 + 自動開下一章。
"""

STATUS_RE = re.compile(r"【狀態】\s*靈力\s*[:：]\s*(-?\d+)\s*｜?\s*搞笑\s*[:：]\s*(-?\d+)\s*｜?\s*心動\s*[:：]\s*(-?\d+)")
OPT_RE = re.compile(r"^([ABCD])[.、．)）]\s*(.+)$")


def load_spec():
    with open(SPEC_FILE, encoding="utf-8") as f:
        return f.read().strip() + APPENDIX


def call_llm(messages, base_url, api_key, model):
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.95,
        "max_tokens": 1000,
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=150) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def parse_status(text):
    m = STATUS_RE.search(text)
    if not m:
        return None
    return {"靈力": int(m.group(1)), "搞笑": int(m.group(2)), "心動": int(m.group(3))}


def parse_options(text):
    opts = {}
    for m in OPT_RE.finditer(text):
        if m.group(1) not in opts:
            opts[m.group(1)] = m.group(2).strip()
    return opts


def strip_status(text):
    return STATUS_RE.sub("", text).strip()


def boot_state():
    st.session_state.setdefault("game", {
        "character": None,          # {"name":..., "occupation":...}
        "history": [],              # [{"role","content"}]
        "stats": {"靈力": 0, "搞笑": 0, "心動": 0},
        "chapter": 1,
        "choices": 0,
        "last_opts": {},
        "busy": False,
    })


def api_config():
    secrets = st.secrets.get("game", {})
    return (
        secrets.get("base_url", "https://api.silra.cn/v1"),
        secrets.get("api_key", ""),
        secrets.get("model", "deepseek-chat"),
    )


def generate(messages, base_url, api_key, model):
    """Call the engine; returns (display_text, stats_delta, options) or raises."""
    content = call_llm(messages, base_url, api_key, model)
    stats = parse_status(content)
    opts = parse_options(content)
    return strip_status(content), stats, opts


def start_game(name, occupation, base_url, api_key, model):
    g = st.session_state["game"]
    g["character"] = {"name": name, "occupation": occupation}
    g["history"] = [{"role": "system", "content": load_spec()}]
    g["stats"] = {"靈力": 0, "搞笑": 0, "心動": 0}
    g["chapter"], g["choices"], g["last_opts"] = 1, 0, {}
    g["busy"] = True
    g["history"].append({
        "role": "user",
        "content": (
            f"遊戲開始。玩家自我介紹：我叫{name}，職業係{occupation}。\n"
            "請按規則：用廣東話同我打招呼、根據職業派一個初始道具同一個初始能力，"
            "然後直接開始第一章（150-250字場景 + 一個周星馳式笑位 + 4個選項）。"
        ),
    })
    try:
        text, stats, opts = generate(g["history"], base_url, api_key, model)
    except Exception as e:
        g["busy"] = False
        raise e
    g["history"].append({"role": "assistant", "content": text})
    if stats:
        g["stats"] = stats
    g["last_opts"] = opts
    g["busy"] = False


def make_choice(letter, text, base_url, api_key, model):
    g = st.session_state["game"]
    g["history"].append({"role": "user", "content": f"我揀 {letter}：{text}"})
    g["choices"] += 1
    g["busy"] = True
    try:
        reply, stats, opts = generate(g["history"], base_url, api_key, model)
    except Exception as e:
        g["busy"] = False
        raise e
    g["history"].append({"role": "assistant", "content": reply})
    if stats:
        g["stats"] = stats
    g["last_opts"] = opts
    if g["choices"] % 3 == 0:
        g["chapter"] += 1
    g["busy"] = False


# ---------------------------------------------------------------- UI
st.set_page_config(page_title="周星馳式：黐線大冒險", page_icon="🎬", layout="wide")
boot_state()
g = st.session_state["game"]
base_url, api_key, model = api_config()

st.markdown("# 🎬《周星馳式：黐線大冒險》")
st.caption("互動小說 RPG 引擎 · 100% 地道廣東話 · 無厘頭 × 深情 · 你揀，佢癲")

with st.sidebar:
    st.markdown("### ⚙️ 引擎設定")
    with st.expander("🔑 API（預設 DeepSeek）"):
        base_url = st.text_input("Base URL", value=base_url)
        api_key = st.text_input("API Key", value=api_key, type="password")
        model = st.text_input("Model", value=model)
    st.divider()
    st.markdown("### 🧠 隱藏數值")
    st.markdown(
        f"靈力：**{g['stats']['靈力']}** ｜ 搞笑：**{g['stats']['搞笑']}** ｜ 心動：**{g['stats']['心動']}**"
    )
    st.caption("（引擎心入面記住嘅數值，間中先會浮出嚟）")
    st.divider()
    st.markdown(f"📖 第 **{g['chapter']}** 章 · 已做 **{g['choices']}** 個選擇")
    if g["character"]:
        st.markdown(f"🧑 主角：**{g['character']['name']}**（{g['character']['occupation']}）")
        if st.button("🔄 重新開始", type="secondary"):
            st.session_state["game"] = None
            st.rerun()

if not api_key:
    st.warning("未設定 API Key —— 去左邊 sidebar「🔑 API」度貼你嘅 DeepSeek / OpenAI 兼容 key 先玩得。")
    st.stop()

if g["busy"]:
    with st.spinner("旁白諗緊對白……"):
        st.rerun()

# ---- 角色創建 ----
if not g["character"]:
    st.markdown("### 你係邊個？")
    c1, c2 = st.columns(2)
    name = c1.text_input("你叫咩名？", placeholder="例如：喪標")
    occupation = c2.text_input("你做咩職業？", placeholder="失業道士 / 塔羅牌占卜師 / 水電工")
    st.markdown("**職業諗唔到？可以試下：** 失業道士 · 塔羅牌占卜師 · 水電工 · 陰間外賣仔 · 驅鬼保險經紀")
    if st.button("🎮 開始遊戲", type="primary", disabled=not (name.strip() and occupation.strip())):
        try:
            start_game(name.strip(), occupation.strip(), base_url, api_key, model)
            st.rerun()
        except Exception as e:
            st.error(f"引擎撻唔着：{e}")
    st.stop()

# ---- 對白歷史 ----
for m in g["history"][1:]:
    if m["role"] == "user":
        with st.chat_message("user"):
            st.markdown(m["content"].replace("我揀 ", "**我揀** ", 1) if m["content"].startswith("我揀") else m["content"])
    else:
        with st.chat_message("assistant", avatar="🎬"):
            st.markdown(m["content"])

# ---- 選項 ----
if g["last_opts"]:
    st.markdown("### 【你點揀？】")
    labels = {k: f"{k}. {v}" for k, v in g["last_opts"].items()}
    order = [k for k in "ABCD" if k in labels]
    pick = st.radio("揀一個，或者自己作：", [labels[k] for k in order], label_visibility="collapsed")
    letter = pick[0]
    custom = ""
    if letter == "D":
        custom = st.text_input("✍️ 你自己諗到嘅癲嘢：", placeholder="夠癲就得……")
        can_go = bool(custom.strip())
    else:
        can_go = True
    if st.button("🚀 出招", type="primary", disabled=not can_go):
        text = custom.strip() if letter == "D" else labels[letter][3:]
        try:
            make_choice(letter, text, base_url, api_key, model)
            st.rerun()
        except Exception as e:
            st.error(f"引擎失靈：{e}")
else:
    st.markdown("### 【你點揀？】")
    free = st.text_input("✍️ 直接打你嘅選擇（例如：A）或者自定玩法：", placeholder="夠癲就得……")
    if st.button("🚀 出招", type="primary", disabled=not free.strip()):
        try:
            make_choice("D", free.strip(), base_url, api_key, model)
            st.rerun()
        except Exception as e:
            st.error(f"引擎失靈：{e}")
