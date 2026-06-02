# 诗的回声 · LLM 辅助写诗

以顾城与海子的诗歌数据库为底，让用户输入标题 / 关键词 / 灵感文字 / 风格 / 长度，
选择参考顾城、海子、二者或不参考，由 LLM 生成一首原创现代诗，并展示本次检索到的参考诗（含正文）。

## 目录结构

```
PoemGenerator/
  assets/                         诗歌数据库（已存在）
    gucheng_poems_annotated.json
    haizi_poems_annotated.json
    merged_theme_vocabulary.json
  server.py                       FastAPI 后端
  requirements.txt
  web/
    index.html
    style.css
    app.js
```

## 安装

```powershell
pip install -r requirements.txt
```

## 配置 LLM（OpenAI 兼容接口，以 DeepSeek 为例）

```powershell
$env:LLM_API_KEY="你的key"
# 以下可选
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_MODEL="deepseek-chat"
```

> 未配置 `LLM_API_KEY` 时，会返回一首占位演示诗，方便先把界面跑通。
> 也可换用任意 OpenAI 兼容服务，只需改 `LLM_BASE_URL` 与 `LLM_MODEL`。

## 运行

```powershell
python server.py
```

浏览器打开：<http://127.0.0.1:8000>

## 说明

- 检索基于 `themes` / `title` / `content` / `style_notes` 的轻量打分，无需向量库。
- 按需求，给 LLM 的参考内容**包含诗歌正文**（单首正文上限约 600 字，超长自动截断），
  以保证生成气质统一；同时在提示词中明确禁止照抄、改写、拼接原句。


