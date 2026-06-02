// 诗的回声 · Netlify Serverless Function
// 职责：藏默认 key + 检索参考诗（含正文）+ 调用 DeepSeek，返回原创诗。
//
// 环境变量（在 Netlify 站点设置 → Environment variables 里配置）：
//   LLM_API_KEY   你自己的默认 key（用户不可见）。不设则走演示模式。
//   LLM_BASE_URL  可选，默认 https://api.deepseek.com
//   LLM_MODEL     可选，默认 deepseek-chat
//
// 两种模式：
//   1) 默认  —— 前端不传 key，函数使用 LLM_API_KEY
//   2) 自带  —— 前端通过请求头 X-LLM-Key 传入用户自己的 key（优先使用）

// 静态 require，确保数据被打包进函数
const guchengData = require("../../assets/gucheng_poems_annotated.json");
const haiziData = require("../../assets/haizi_poems_annotated.json");

const MAX_REF_CONTENT_CHARS = 600;
const DEFAULT_REF_LIMIT = 5;

// --------------------------------------------------------------------- //
// 数据准备
// --------------------------------------------------------------------- //
function loadPoems(raw, author) {
  return (raw.poems || [])
    .filter((p) => (p.content || "").trim())
    .map((p) => ({
      author,
      title: (p.title || "无题").trim(),
      content: (p.content || "").trim(),
      themes: p.themes || [],
      style_notes: (p.style_notes || "").trim(),
    }));
}

const GUCHENG = loadPoems(guchengData, "顾城");
const HAIZI = loadPoems(haiziData, "海子");

const POET_MODE_LABEL = {
  gucheng: "参考顾城",
  haizi: "参考海子",
  both: "同时参考顾城与海子",
  none: "自由创作",
};

// --------------------------------------------------------------------- //
// 检索
// --------------------------------------------------------------------- //
function tokenize(text) {
  if (!text) return [];
  const tokens = [];
  const re = /[\u4e00-\u9fff]+|[A-Za-z0-9]+/g;
  let m;
  while ((m = re.exec(text))) {
    const seg = m[0];
    if (/^[A-Za-z0-9]+$/.test(seg)) {
      tokens.push(seg.toLowerCase());
    } else if (seg.length <= 3) {
      tokens.push(seg);
    } else {
      for (let i = 0; i < seg.length - 1; i++) tokens.push(seg.slice(i, i + 2));
    }
  }
  return tokens;
}

function scorePoem(poem, selectedThemes, freeTerms, title) {
  let score = 0;
  for (const t of selectedThemes) {
    if (poem.themes.includes(t)) score += 5;
  }
  const terms = [...freeTerms, ...selectedThemes];
  if (title) terms.push(...tokenize(title));

  const seen = new Set();
  for (const term of terms) {
    if (!term || seen.has(term)) continue;
    seen.add(term);
    if (poem.title.includes(term)) score += 4;
    if (poem.content.includes(term)) score += 2;
    if (poem.style_notes.includes(term)) score += 2;
  }
  score += Math.random();
  return score;
}

function sample(arr, n) {
  const copy = [...arr];
  const out = [];
  for (let i = 0; i < n && copy.length; i++) {
    const idx = Math.floor(Math.random() * copy.length);
    out.push(copy.splice(idx, 1)[0]);
  }
  return out;
}

function retrieveReferences(title, keywords, freeText, poetMode, limit) {
  if (poetMode === "none") return [];

  let pool;
  if (poetMode === "gucheng") pool = GUCHENG;
  else if (poetMode === "haizi") pool = HAIZI;
  else pool = [...GUCHENG, ...HAIZI];

  const selectedThemes = (keywords || []).filter(Boolean);
  const freeTerms = tokenize(freeText);
  const hasQuery = selectedThemes.length || freeTerms.length || title;

  if (!hasQuery) return sample(pool, Math.min(limit, pool.length));

  const scored = pool.map((p) => [
    scorePoem(p, selectedThemes, freeTerms, title),
    p,
  ]);
  scored.sort((a, b) => b[0] - a[0]);

  let top = scored
    .slice(0, limit)
    .filter((x) => x[0] > 1)
    .map((x) => x[1]);
  if (!top.length) top = sample(pool, Math.min(limit, pool.length));
  return top;
}

// --------------------------------------------------------------------- //
// Prompt（按需求：参考内容包含正文）
// --------------------------------------------------------------------- //
function truncateContent(content) {
  if (content.length <= MAX_REF_CONTENT_CHARS) return content;
  return content.slice(0, MAX_REF_CONTENT_CHARS).replace(/\s+$/, "") + "……";
}

function indent(text, prefix = "      ") {
  return text
    .split("\n")
    .map((line) => prefix + line)
    .join("\n");
}

function buildReferenceBlock(refs) {
  if (!refs.length) return "";
  return refs
    .map((r, i) => {
      const themes = r.themes.length ? r.themes.join("、") : "（未标注）";
      return (
        `${i + 1}. ${r.author}《${r.title}》\n` +
        `   主题: ${themes}\n` +
        `   风格: ${r.style_notes || "（未标注）"}\n` +
        `   正文:\n${indent(truncateContent(r.content))}`
      );
    })
    .join("\n\n");
}

function buildPrompt(req, refs) {
  const title = (req.title || "").trim();
  const keywords =
    (req.keywords || []).filter(Boolean).join("、") || "（未提供）";
  const freeText = (req.text || "").trim() || "（未提供）";
  const style = (req.style || "").trim() || "（未指定, 由你把握）";
  const length = (req.length || "").trim() || "（未指定, 由你把握）";
  const poetLabel = POET_MODE_LABEL[req.poetMode] || "自由创作";

  const refBlock = buildReferenceBlock(refs);
  const refSection = refBlock
    ? `\n以下是参考作品(含正文)。请仔细体会它们的意象选择、语感、节奏与气质, 但尽量不要照抄、改写、拼接其中诗句:\n\n${refBlock}\n`
    : "\n本次不提供参考作品, 请完全自由创作。\n";

  const titleRule = title
    ? `5. 标题使用「${title}」, 第一行只输出这个标题, 单独成行, 随后空一行再写正文。诗的内容要扣题。`
    : `5. 请自拟一个贴切的标题。第一行输出标题, 单独成行, 随后空一行再写正文。`;

  return `你是一位中文现代诗的诗人, 擅长写出克制、有画面感、有呼吸感的原创现代诗。

请根据输入创作一首原创现代诗。

要求:
1. 是全新的原创诗, 不要复述、改写、拼接已有诗句。
2. 可以学习参考作品的意象倾向、语感和气质, 最好不搬用其具体词句或意象组合。
3. 只输出诗歌本身, 不要任何解释、说明或前后缀。
${titleRule}

参考对象: ${poetLabel}

用户输入:
- 标题: ${title || "（未提供, 请自拟）"}
- 关键词/主题: ${keywords}
- 灵感文字: ${freeText}
- 期望风格: ${style}
- 期望长度: ${length}
${refSection}
现在, 请直接输出这首诗:`;
}

// --------------------------------------------------------------------- //
// 调用 LLM
// --------------------------------------------------------------------- //
async function callLLM(prompt, apiKey) {
  const key = (apiKey || "").trim() || process.env.LLM_API_KEY || "";
  if (!key) {
    return (
      "（演示模式 · 未配置 API Key）\n\n" +
      "在没有钥匙的门前\n" +
      "我把今天的光\n" +
      "折成一只很小的船\n" +
      "放进你还没醒来的河里"
    );
  }

  const base = (process.env.LLM_BASE_URL || "https://api.deepseek.com").replace(
    /\/$/,
    ""
  );
  const model = process.env.LLM_MODEL || "deepseek-chat";

  const resp = await fetch(`${base}/v1/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      messages: [
        {
          role: "system",
          content:
            "你是一位精于中文现代诗的诗人, 只输出诗歌正文, 不做任何解释。",
        },
        { role: "user", content: prompt },
      ],
      temperature: 1.0,
      max_tokens: 1200,
    }),
  });

  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`LLM ${resp.status}: ${t}`);
  }
  const data = await resp.json();
  return data.choices[0].message.content.trim();
}

// --------------------------------------------------------------------- //
// Handler
// --------------------------------------------------------------------- //
exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: JSON.stringify({ error: "Method Not Allowed" }) };
  }

  let req;
  try {
    req = JSON.parse(event.body || "{}");
  } catch (e) {
    req = {};
  }

  // Netlify 的 header 名是小写
  const userKey =
    event.headers["x-llm-key"] || event.headers["X-LLM-Key"] || "";

  const refs = retrieveReferences(
    req.title || "",
    req.keywords || [],
    req.text || "",
    req.poetMode || "both",
    DEFAULT_REF_LIMIT
  );

  try {
    const poem = await callLLM(buildPrompt(req, refs), userKey);
    const references = refs.map((r) => ({
      author: r.author,
      title: r.title,
      themes: r.themes,
      style_notes: r.style_notes,
      content: r.content,
    }));
    return {
      statusCode: 200,
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify({ poem, references }),
    };
  } catch (e) {
    return {
      statusCode: 502,
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify({ error: "生成失败: " + e.message }),
    };
  }
};
