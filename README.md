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
cd c:\Users\tianmacheng\Desktop\test\PoemGenerator
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

---

## 部署到 Netlify（无需自己租云 / 跑 server）

本项目同时提供了一套 **Netlify Serverless** 部署方案：前端是纯静态文件，
后端逻辑放在 `netlify/functions/generate.js`，由 Netlify 托管运行，你不必维护服务器。

### 涉及文件

```
netlify.toml                     发布目录 / 函数目录 / /api 重写规则
netlify/functions/generate.js    serverless 后端（检索 + 藏 key + 调 DeepSeek）
web/                             静态前端（publish 目录）
web/merged_theme_vocabulary.json 主题词表（/api/themes 重写到它）
assets/*.json                    诗歌数据（打包进函数）
```

### 两种生成模式

1. **默认**：用站点自己的 key（你在 Netlify 后台配置），用户看不到。
2. **自带**：用户在页面输入自己的 DeepSeek key，仅存其本机浏览器，
   通过请求头 `X-LLM-Key` 发送，函数优先使用它。

### 部署步骤

1. 把本项目推到 GitHub（建议让 `PoemGenerator` 作为仓库根；
   若放在子目录，则在 Netlify 里设置 **Base directory = PoemGenerator**）。
2. 在 Netlify 新建站点，连接该仓库；构建配置会自动读取 `netlify.toml`。
3. 在 **Site settings → Environment variables** 配置（用于“默认”模式）：
   - `LLM_API_KEY` = 你的 DeepSeek key（用户不可见）
   - `LLM_BASE_URL` = `https://api.deepseek.com`（可选）
   - `LLM_MODEL` = `deepseek-chat`（可选）
4. 部署完成即可访问。`/api/themes` 与 `/api/generate` 已由 `netlify.toml` 自动重写，
   前端代码无需改动。

> 安全提醒：开放“默认”模式意味着访客用的是你的额度。
> 公网上线建议加访问频率限制 / 简单口令，避免接口被刷。

### 本地预览 Netlify 版

```powershell
npm i -g netlify-cli
cd c:\Users\tianmacheng\Desktop\test\PoemGenerator
netlify dev
```

