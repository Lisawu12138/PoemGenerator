// 诗的回声 · 前端交互

const $ = (sel) => document.querySelector(sel);

const els = {
  title: $("#title"),
  keywords: $("#keywords"),
  text: $("#text"),
  style: $("#style"),
  themeChips: $("#themeChips"),
  lengthGroup: $("#lengthGroup"),
  poetGroup: $("#poetGroup"),
  generateBtn: $("#generateBtn"),
  hint: $("#hint"),
  empty: $("#empty"),
  poemView: $("#poemView"),
  poemText: $("#poemText"),
  copyBtn: $("#copyBtn"),
  regenBtn: $("#regenBtn"),
  refView: $("#refView"),
  refList: $("#refList"),
  loading: $("#loading"),
  keyMode: $("#keyMode"),
  keyPanel: $("#keyPanel"),
  apiKey: $("#apiKey"),
  keySave: $("#keySave"),
  keyClear: $("#keyClear"),
  keyTip: $("#keyTip"),
};

// 已点选的主题词集合
const selectedThemes = new Set();
let lastPayload = null;

// --------------------------------------------------------------------- //
// API Key（两种模式）
//   default —— 用站点默认 key（后端环境变量），前端不发送 key
//   byo     —— 用户自带 DeepSeek key，仅存本机 localStorage，请求时通过 header 发送
// --------------------------------------------------------------------- //
const KEY_STORE = "poem_echo_api_key";
const MODE_STORE = "poem_echo_key_mode";

function getMode() {
  return localStorage.getItem(MODE_STORE) || "default";
}

// 只有“自带”模式才把 key 发给后端；默认模式发空串，后端用自己的 key
function getApiKey() {
  if (getMode() !== "byo") return "";
  return localStorage.getItem(KEY_STORE) || "";
}

function applyMode(mode) {
  localStorage.setItem(MODE_STORE, mode);
  els.keyMode.querySelectorAll(".key-opt").forEach((b) => {
    b.classList.toggle("active", b.dataset.mode === mode);
  });
  els.keyPanel.classList.toggle("hidden", mode !== "byo");
}

function initKeyBar() {
  els.apiKey.value = localStorage.getItem(KEY_STORE) || "";
  applyMode(getMode());
  refreshKeyTip();

  els.keyMode.addEventListener("click", (e) => {
    const btn = e.target.closest(".key-opt");
    if (!btn) return;
    applyMode(btn.dataset.mode);
    refreshKeyTip();
  });
  els.keySave.addEventListener("click", () => {
    const v = els.apiKey.value.trim();
    if (v) localStorage.setItem(KEY_STORE, v);
    else localStorage.removeItem(KEY_STORE);
    refreshKeyTip();
  });
  els.keyClear.addEventListener("click", () => {
    localStorage.removeItem(KEY_STORE);
    els.apiKey.value = "";
    refreshKeyTip();
  });
}

function refreshKeyTip() {
  if (getMode() !== "byo") {
    els.keyTip.textContent = "";
    return;
  }
  const has = !!(localStorage.getItem(KEY_STORE) || "").trim();
  els.keyTip.textContent = has ? "已保存（仅本机）" : "请填写并保存你的 DeepSeek Key";
}

// --------------------------------------------------------------------- //
// 初始化主题词
// --------------------------------------------------------------------- //
async function loadThemes() {
  try {
    const res = await fetch("/api/themes");
    const data = await res.json();
    renderChips(data.groups || {});
  } catch (e) {
    console.error("主题词加载失败", e);
  }
}

function renderChips(groups) {
  els.themeChips.innerHTML = "";
  Object.values(groups).forEach((words) => {
    words.forEach((w) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip";
      chip.textContent = w;
      chip.addEventListener("click", () => toggleChip(chip, w));
      els.themeChips.appendChild(chip);
    });
  });
}

function toggleChip(chip, word) {
  if (selectedThemes.has(word)) {
    selectedThemes.delete(word);
    chip.classList.remove("on");
  } else {
    selectedThemes.add(word);
    chip.classList.add("on");
  }
}

// --------------------------------------------------------------------- //
// 分段按钮（长度 / 参考对象）
// --------------------------------------------------------------------- //
function bindSegmented(group) {
  group.addEventListener("click", (e) => {
    const btn = e.target.closest(".seg");
    if (!btn) return;
    group.querySelectorAll(".seg").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
  });
}
function getSegValue(group) {
  const active = group.querySelector(".seg.active");
  return active ? active.dataset.value : "";
}

// --------------------------------------------------------------------- //
// 收集输入
// --------------------------------------------------------------------- //
function collectPayload() {
  // 关键词 = 输入框（空格/逗号分隔）+ 点选的主题词
  const typed = els.keywords.value
    .split(/[\s,，、]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const keywords = Array.from(new Set([...typed, ...selectedThemes]));

  return {
    title: els.title.value.trim(),
    keywords,
    text: els.text.value.trim(),
    style: els.style.value.trim(),
    length: getSegValue(els.lengthGroup),
    poetMode: getSegValue(els.poetGroup),
  };
}

// --------------------------------------------------------------------- //
// 生成
// --------------------------------------------------------------------- //
async function generate(payload) {
  setLoading(true);
  els.hint.textContent = "";
  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-LLM-Key": getApiKey(),
      },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "生成失败");
    }
    renderResult(data);
  } catch (e) {
    els.hint.textContent = "出错了：" + e.message;
  } finally {
    setLoading(false);
  }
}

function renderResult(data) {
  els.empty.classList.add("hidden");
  els.poemView.classList.remove("hidden");
  els.poemText.textContent = data.poem || "";

  renderRefs(data.references || []);
  els.poemView.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderRefs(refs) {
  if (!refs.length) {
    els.refView.classList.add("hidden");
    els.refList.innerHTML = "";
    return;
  }
  els.refView.classList.remove("hidden");
  els.refList.innerHTML = "";

  refs.forEach((r) => {
    const item = document.createElement("div");
    item.className = "ref-item";

    const themes = (r.themes || []).join("、");
    const head = document.createElement("div");
    head.className = "ref-head";
    head.innerHTML = `
      <span class="ref-name"><span class="author">${r.author}</span>《${escapeHtml(
      r.title
    )}》</span>
      <span class="ref-themes">${escapeHtml(themes)}</span>
      <span class="ref-toggle">展开 ▾</span>
    `;

    const body = document.createElement("div");
    body.className = "ref-body";
    body.innerHTML = `
      ${r.style_notes ? `<p class="ref-style">${escapeHtml(r.style_notes)}</p>` : ""}
      <pre class="ref-content">${escapeHtml(r.content || "")}</pre>
    `;

    head.addEventListener("click", () => {
      item.classList.toggle("open");
      const t = head.querySelector(".ref-toggle");
      t.textContent = item.classList.contains("open") ? "收起 ▴" : "展开 ▾";
    });

    item.appendChild(head);
    item.appendChild(body);
    els.refList.appendChild(item);
  });
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function setLoading(on) {
  els.loading.classList.toggle("hidden", !on);
  els.generateBtn.disabled = on;
}

// --------------------------------------------------------------------- //
// 事件
// --------------------------------------------------------------------- //
els.generateBtn.addEventListener("click", () => {
  lastPayload = collectPayload();
  generate(lastPayload);
});

els.regenBtn.addEventListener("click", () => {
  const payload = lastPayload || collectPayload();
  generate(payload);
});

els.copyBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(els.poemText.textContent);
    els.copyBtn.textContent = "已复制";
    setTimeout(() => (els.copyBtn.textContent = "复制"), 1500);
  } catch (e) {
    els.copyBtn.textContent = "复制失败";
    setTimeout(() => (els.copyBtn.textContent = "复制"), 1500);
  }
});

bindSegmented(els.lengthGroup);
bindSegmented(els.poetGroup);
initKeyBar();
loadThemes();
