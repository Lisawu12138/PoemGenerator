# -*- coding: utf-8 -*-
"""
诗的回声 —— LLM 辅助写诗后端

数据来源:
    assets/gucheng_poems_annotated.json
    assets/haizi_poems_annotated.json
    assets/merged_theme_vocabulary.json

运行:
    1. 安装依赖:  pip install -r requirements.txt
    2. 配置环境变量(任选一个 OpenAI 兼容服务, 以 DeepSeek 为例):
           Windows PowerShell:
               $env:LLM_API_KEY="你的key"
               $env:LLM_BASE_URL="https://api.deepseek.com"   # 可选, 默认 deepseek
               $env:LLM_MODEL="deepseek-chat"                  # 可选
       未配置 LLM_API_KEY 时, 会返回演示用的占位诗歌, 方便先把界面跑起来。
    3. 启动:  python server.py
    4. 打开:  http://127.0.0.1:8000
"""

import json
import os
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# --------------------------------------------------------------------------- #
# 路径与配置
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
WEB_DIR = BASE_DIR / "web"

LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

# 给 LLM 的单首参考诗正文最大字符数, 防止长诗撑爆上下文
MAX_REF_CONTENT_CHARS = 600
# 参考诗条数
DEFAULT_REF_LIMIT = 5


# --------------------------------------------------------------------------- #
# 数据加载
# --------------------------------------------------------------------------- #
def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_poems(path: Path, author: str) -> List[Dict[str, Any]]:
    """读取一份 annotated 文件, 返回带 author 字段的诗歌列表。"""
    data = _load_json(path)
    poems = []
    for p in data.get("poems", []):
        content = (p.get("content") or "").strip()
        if not content:
            continue
        poems.append(
            {
                "author": author,
                "title": (p.get("title") or "无题").strip(),
                "content": content,
                "date": p.get("date", ""),
                "section": p.get("section", ""),
                "themes": p.get("themes", []) or [],
                "style_notes": (p.get("style_notes") or "").strip(),
            }
        )
    return poems


GUCHENG_POEMS: List[Dict[str, Any]] = _load_poems(
    ASSETS_DIR / "gucheng_poems_annotated.json", "顾城"
)
HAIZI_POEMS: List[Dict[str, Any]] = _load_poems(
    ASSETS_DIR / "haizi_poems_annotated.json", "海子"
)
THEME_VOCAB: Dict[str, Any] = _load_json(ASSETS_DIR / "merged_theme_vocabulary.json")

print(f"[数据] 顾城 {len(GUCHENG_POEMS)} 首, 海子 {len(HAIZI_POEMS)} 首已加载。")


# --------------------------------------------------------------------------- #
# 检索
# --------------------------------------------------------------------------- #
def _tokenize(text: str) -> List[str]:
    """从自由文本里粗略抽取中文词/英文词作为检索线索。"""
    if not text:
        return []
    # 连续中文按 2 字滑窗 + 整段; 英文/数字按单词
    tokens: List[str] = []
    for seg in re.findall(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+", text):
        if re.match(r"[A-Za-z0-9]+", seg):
            tokens.append(seg.lower())
        else:
            if len(seg) <= 3:
                tokens.append(seg)
            else:
                for i in range(len(seg) - 1):
                    tokens.append(seg[i : i + 2])
    return tokens


def _score_poem(
    poem: Dict[str, Any],
    selected_themes: List[str],
    free_terms: List[str],
    title: str,
) -> float:
    score = 0.0
    themes = poem["themes"]
    content = poem["content"]
    style = poem["style_notes"]
    p_title = poem["title"]

    # 1. 主题词命中 themes
    for t in selected_themes:
        if t in themes:
            score += 5

    # 2. 标题/关键词/自由文本 在各字段中的命中
    terms = list(free_terms)
    for t in selected_themes:
        terms.append(t)
    if title:
        terms.extend(_tokenize(title))

    seen = set()
    for term in terms:
        if not term or term in seen:
            continue
        seen.add(term)
        if term in p_title:
            score += 4
        if term in content:
            score += 2
        if term in style:
            score += 2

    # 3. 轻微随机扰动, 避免每次结果都一样
    score += random.uniform(0, 1)
    return score


def retrieve_references(
    title: str,
    keywords: List[str],
    free_text: str,
    poet_mode: str,
    limit: int = DEFAULT_REF_LIMIT,
) -> List[Dict[str, Any]]:
    """根据用户输入与参考对象, 返回最相关的若干首诗。"""
    if poet_mode == "none":
        return []

    if poet_mode == "gucheng":
        pool = GUCHENG_POEMS
    elif poet_mode == "haizi":
        pool = HAIZI_POEMS
    else:  # both
        pool = GUCHENG_POEMS + HAIZI_POEMS

    selected_themes = [k for k in keywords if k]
    free_terms = _tokenize(free_text)

    scored = [
        (_score_poem(p, selected_themes, free_terms, title), p) for p in pool
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    # 如果完全没有任何有效输入, 随机给一些种子诗
    has_query = bool(selected_themes or free_terms or title)
    if not has_query:
        sample = random.sample(pool, min(limit, len(pool)))
        return sample

    top = [p for s, p in scored[:limit] if s > 1]
    if not top:  # 兜底
        top = random.sample(pool, min(limit, len(pool)))
    return top


def _truncate_content(content: str) -> str:
    if len(content) <= MAX_REF_CONTENT_CHARS:
        return content
    return content[:MAX_REF_CONTENT_CHARS].rstrip() + "……"


# --------------------------------------------------------------------------- #
# Prompt 构造
# --------------------------------------------------------------------------- #
POET_MODE_LABEL = {
    "gucheng": "参考顾城",
    "haizi": "参考海子",
    "both": "同时参考顾城与海子",
    "none": "不参考任何诗人, 自由创作",
}

WRITING_GUIDE = """现代诗写作方法参考（仅作辅助, 不要机械套用）:
- 先定调: 明确整首诗的情绪、思想与声音, 情感要真, 避免空泛煽情。
- 再取象: 用具体的物、动作、景色、细节承载情思, 不要只讲道理。
- 重寄寓: 让情感附着在意象上, 多用借景抒情、托物言志、缘事抒情。
- 会抒情: 用画面、反衬、象征、节奏变化形成含蓄和张力。
- 要升华: 结尾留出回响、转折或境界打开, 避免口号式总结。
- 注意分行和呼吸: 现代诗不拘格律, 但要有节奏、停顿、留白和画面感。"""


def _build_length_rule(length: str) -> str:
    if length == "短诗":
        return "正文写成一段左右, 约 2 到 8 句/行以内, 宁短勿长。"
    if length in {"中诗", "中等"}:
        return "正文写成中等长度,  约 6 到 16 句/行, 保持克制和完整。"
    if length == "长诗":
        return "文可以适度展开为长诗, 约 10 句以上, 允许分段推进, 但不要冗长拖沓。"
    return "长度由你把握, 但整体保持克制, 不要无故写得冗长。"


def _build_reference_block(refs: List[Dict[str, Any]]) -> str:
    """按用户要求: 参考内容中带上正文, 以保证气质统一、不至于不伦不类。"""
    if not refs:
        return ""
    lines = []
    for i, r in enumerate(refs, 1):
        themes = "、".join(r["themes"]) if r["themes"] else "（未标注）"
        lines.append(
            f"{i}. {r['author']}《{r['title']}》\n"
            f"   主题: {themes}\n"
            f"   风格: {r['style_notes'] or '（未标注）'}\n"
            f"   正文:\n{_indent(_truncate_content(r['content']))}"
        )
    return "\n\n".join(lines)


def _indent(text: str, prefix: str = "      ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def build_prompt(payload: "GenerateRequest", refs: List[Dict[str, Any]]) -> str:
    title = payload.title.strip()
    keywords = "、".join([k for k in payload.keywords if k]) or "（未提供）"
    free_text = payload.text.strip() or "（未提供）"
    style = payload.style.strip() or "（未指定, 由你把握）"
    length = payload.length.strip() or "（未指定, 由你把握）"
    poet_label = POET_MODE_LABEL.get(payload.poetMode, "自由创作")
    length_rule = _build_length_rule(length)

    ref_block = _build_reference_block(refs)
    ref_section = (
        f"\n以下是从诗歌数据库中检索到的参考作品(含正文)。"
        f"请仔细体会它们的意象选择、语感、节奏与气质, "
        f"尽量不要照抄、改写、拼接其中任何诗句:\n\n{ref_block}\n"
        if ref_block
        else "\n本次不提供参考作品, 请完全自由创作。\n"
    )

    title_rule = (
        f"标题使用「{title}」, 第一行只输出这个标题, 单独成行, 随后空一行再写正文。诗的内容要扣题。"
        if title
        else "用户未提供标题, 请自拟一个贴切的标题。第一行输出标题, 单独成行, 随后空一行再写正文。"
    )

    prompt = f"""你是一位中文现代诗的诗人, 擅长写出克制、有画面感、有呼吸感的原创现代诗。

请根据输入创作一首原创现代诗。

要求:
1. 是全新的原创诗, 不要复述、改写、拼接已有诗句。
2. 可以学习参考作品的意象倾向、语感和气质, 最好不搬用其具体词句或意象组合。
3. 只输出诗歌本身, 不要任何解释、说明或前后缀。
4. {length_rule}
{title_rule}

{WRITING_GUIDE}

参考对象: {poet_label}

用户输入:
- 标题: {title or "（未提供, 请自拟）"}
- 关键词/主题: {keywords}
- 灵感文字: {free_text}
- 期望风格: {style}
- 期望长度: {length}
{ref_section}
现在, 请直接输出这首诗:"""
    return prompt


# --------------------------------------------------------------------------- #
# LLM 调用
# --------------------------------------------------------------------------- #
async def call_llm(prompt: str, api_key: str = "") -> str:
    # 优先用前端传入的 key, 否则回退到环境变量
    key = (api_key or "").strip() or LLM_API_KEY
    if not key:
        # 未配置 key 时的占位输出, 让前端流程可用
        return (
            "（演示模式 · 未配置 LLM_API_KEY）\n\n"
            "在没有钥匙的门前\n"
            "我把今天的光\n"
            "折成一只很小的船\n"
            "放进你还没醒来的河里"
        )

    url = f"{LLM_BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一位精于中文现代诗的诗人, 只输出诗歌正文, 不做任何解释。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 1.0,
        "max_tokens": 1200,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


# --------------------------------------------------------------------------- #
# FastAPI
# --------------------------------------------------------------------------- #
app = FastAPI(title="诗的回声")


class GenerateRequest(BaseModel):
    title: str = ""
    keywords: List[str] = []
    text: str = ""
    style: str = ""
    length: str = ""
    poetMode: str = "both"  # gucheng | haizi | both | none


@app.get("/api/themes")
async def get_themes() -> JSONResponse:
    return JSONResponse(
        {
            "groups": THEME_VOCAB.get("groups", {}),
            "theme_vocabulary": THEME_VOCAB.get("theme_vocabulary", []),
        }
    )


@app.post("/api/generate")
async def generate(req: GenerateRequest, request: Request) -> JSONResponse:
    refs = retrieve_references(
        title=req.title,
        keywords=req.keywords,
        free_text=req.text,
        poet_mode=req.poetMode,
        limit=DEFAULT_REF_LIMIT,
    )
    prompt = build_prompt(req, refs)
    user_key = request.headers.get("X-LLM-Key", "")
    try:
        poem = await call_llm(prompt, api_key=user_key)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(
            status_code=502,
            content={"error": f"生成失败: {e}"},
        )

    references = [
        {
            "author": r["author"],
            "title": r["title"],
            "themes": r["themes"],
            "style_notes": r["style_notes"],
            "content": r["content"],
        }
        for r in refs
    ]
    return JSONResponse({"poem": poem, "references": references})


# --------------------------------------------------------------------------- #
# 静态前端
# --------------------------------------------------------------------------- #
@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=str(WEB_DIR)), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
