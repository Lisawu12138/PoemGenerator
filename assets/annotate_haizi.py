#!/usr/bin/env python3
"""给 haizi_poems.json 逐首添加 themes 与 style_notes 标注。

逻辑与 annotate_poems.py 相同，区别在于主题词表换成海子的核心意象体系。

用法（PowerShell）：
    $env:LLM_API_KEY="sk-你的key"
    python annotate_haizi.py
"""

import json
import os
import re
import sys
import time
import io
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from openai import OpenAI  # pip install openai>=1.0

# ---------- 配置 ----------
INPUT_PATH = r"c:\Users\tianmacheng\Desktop\test\PoemGenerator\assets\haizi_poems.json"
OUTPUT_PATH = r"c:\Users\tianmacheng\Desktop\test\PoemGenerator\assets\haizi_poems_annotated.json"

API_KEY = os.environ.get("LLM_API_KEY", "")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

SAVE_EVERY = 10
MAX_RETRY = 3
WORKERS = 12

# 主题词表：从海子诗的核心意象与母题提炼
# 合并主题词表（顾城 + 海子，共 51 个）——单一真实来源见 merged_theme_vocabulary.json
THEMES = [
    # 自然·大地
    "麦地", "太阳", "村庄", "大地", "故乡", "河流", "天空", "海洋", "火焰", "自然", "农耕",
    # 时间·季节
    "时间", "春天", "夏天", "秋天", "冬天", "黎明", "童年",
    # 光明·黑暗
    "光明", "黑夜",
    # 情感·心绪
    "孤独", "爱情", "思念", "失落", "痛苦", "恐惧", "沉默", "希望", "纯真",
    # 生命·存在
    "生命", "死亡", "命运", "虚无", "自我",
    # 精神·理想
    "理想", "信仰", "梦想", "梦境", "自由", "远方", "英雄",
    # 漂泊·境遇
    "流浪", "逃亡", "旅途", "离别", "家园", "亲情",
    # 现实·其他
    "社会批判", "战争", "城市", "荒诞",
]

SYSTEM_PROMPT = "你是一位资深的中国现代诗歌研究专家，尤其精通海子的作品。"

USER_PROMPT_TMPL = """请分析下面这首海子的诗，输出严格的 JSON。

要求：
1. themes：从给定主题词表中选择 2-4 个最贴切的标签，必须原样使用词表中的词。
2. style_notes：用一句话（25 字左右）概括这首诗的风格特征，可涉及意象、节奏、情感基调、语言质地等。

主题词表：{themes}

诗歌标题：{title}
诗歌内容：
{content}

只输出 JSON，不要任何解释、不要 markdown 代码块，格式如下：
{{"themes": ["...", "..."], "style_notes": "..."}}"""


def build_client():
    if not API_KEY:
        print("错误：未设置 LLM_API_KEY 环境变量。", file=sys.stderr)
        sys.exit(1)
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


def parse_json_loose(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def annotate_one(client, poem):
    prompt = USER_PROMPT_TMPL.format(
        themes="、".join(THEMES),
        title=poem.get("title", ""),
        content=poem.get("content", ""),
    )
    last_err = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=300,
            )
            data = parse_json_loose(resp.choices[0].message.content)
            themes = [t for t in data.get("themes", []) if t in THEMES][:4]
            if len(themes) < 2:
                raise ValueError("themes 少于 2 个或不在词表内")
            return themes, str(data.get("style_notes", "")).strip()
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"    重试 {attempt}/{MAX_RETRY}：{e}", file=sys.stderr)
            time.sleep(2 * attempt)
    raise RuntimeError(f"标注失败：{last_err}")


def load_existing_output():
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save(data):
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    client = build_client()

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        src = json.load(f)

    out = load_existing_output() or src
    poems = out["poems"]
    out.setdefault("metadata", {})["theme_vocabulary"] = THEMES

    total = len(poems)
    todo = [i for i, p in enumerate(poems)
            if not (p.get("themes") and p.get("style_notes"))]
    already = total - len(todo)
    print(f"共 {total} 首，已标注 {already}，待标注 {len(todo)}，并发 {WORKERS}")

    lock = threading.Lock()
    counter = {"done": already, "fail": 0}

    def work(idx):
        poem = poems[idx]
        try:
            themes, style = annotate_one(client, poem)
        except Exception as e:  # noqa: BLE001
            with lock:
                counter["fail"] += 1
            print(f"    跳过[{idx + 1}]（失败）：{e}", file=sys.stderr)
            return
        with lock:
            poem["themes"] = themes
            poem["style_notes"] = style
            counter["done"] += 1
            d = counter["done"]
            if d % SAVE_EVERY == 0:
                save(out)
                print(f"  进度 {d}/{total}（最近：{poem.get('title', '')}）")

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(work, i) for i in todo]
        for _ in as_completed(futures):
            pass

    save(out)
    print(f"完成！已标注 {counter['done']}/{total} 首，失败 {counter['fail']} 首，输出：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
