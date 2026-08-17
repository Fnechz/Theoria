/* Theoria web UI — chats with history, streaming, thinking mode, photo
   attachments, verification badges, and LaTeX document preview. */

const mainEl = document.getElementById("main");
const chatEl = document.getElementById("chat");
const form = document.getElementById("ask-form");
const queryEl = document.getElementById("query");
const askBtn = document.getElementById("ask-btn");
const stopBtn = document.getElementById("stop-btn");
const healthDot = document.getElementById("health-dot");
const healthText = document.getElementById("health-text");
const perfText = document.getElementById("perf-text");
const docList = document.getElementById("doc-list");
const pdfInput = document.getElementById("pdf-input");
const photoInput = document.getElementById("photo-input");
const photoBtn = document.getElementById("photo-btn");
const thinkBtn = document.getElementById("think-btn");
const chatListEl = document.getElementById("chat-list");
const newChatBtn = document.getElementById("new-chat");
const attachRow = document.getElementById("attach-row");
const previewPanel = document.getElementById("preview-panel");
const previewBody = document.getElementById("preview-body");
const previewResizer = document.getElementById("preview-resizer");

const PREVIEW_WIDTH_KEY = "theoria.previewWidth";
const PREVIEW_ZOOM_KEY = "theoria.previewZoom";
const PREVIEW_ZOOM_STEPS = [0.85, 1, 1.15, 1.3];

let busy = false;
let thinkOn = false;
let currentChatId = null;
let pendingAttachment = null; // { name, text, url }
let currentTexSource = "";
let activeAbort = null; // AbortController for the in-flight stream
let previewZoomIdx = 1;

function setBusy(on) {
  busy = on;
  askBtn.disabled = on;
  askBtn.classList.toggle("hidden", on);
  stopBtn.classList.toggle("hidden", !on);
}

/* ================= chats ================= */

async function refreshChats() {
  try {
    const r = await fetch("/api/chats");
    const j = await r.json();
    chatListEl.innerHTML = "";
    for (const c of j.chats) {
      const item = document.createElement("div");
      item.className = "chat-item" + (c.id === currentChatId ? " active" : "");
      item.innerHTML = `<span class="title">${escapeHtml(c.title)}</span><button class="del" title="Delete">&#10005;</button>`;
      item.querySelector(".title").addEventListener("click", () => openChat(c.id));
      item.addEventListener("click", (e) => {
        if (!e.target.closest(".del")) openChat(c.id);
      });
      item.querySelector(".del").addEventListener("click", async (e) => {
        e.stopPropagation();
        await fetch(`/api/chats/${c.id}`, { method: "DELETE" });
        if (c.id === currentChatId) startNewChat();
        refreshChats();
      });
      chatListEl.appendChild(item);
    }
  } catch { /* server starting */ }
}

function startNewChat() {
  currentChatId = null;
  chatEl.innerHTML = "";
  mainEl.classList.add("empty");
  closePreview();
  clearAttachment();
  refreshChats();
  queryEl.focus();
}

async function openChat(id) {
  if (busy) return;
  try {
    const r = await fetch(`/api/chats/${id}`);
    const j = await r.json();
    if (j.error) return;
    currentChatId = id;
    chatEl.innerHTML = "";
    mainEl.classList.remove("empty");
    closePreview();
    for (const m of j.messages) {
      if (m.role === "user") {
        addUserMsg(m.content, m.meta && m.meta.attachment ? { name: m.meta.attachment } : null);
      } else {
        const msg = addAssistantMsg();
        const body = msg.querySelector(".msg-body");
        renderRich(body, m.content);
        const meta = m.meta || {};
        if (meta.intent) msg.querySelector(".intent-tag").textContent = meta.intent;
        finishExtras(msg.querySelector(".extras"), meta, null, m.content);
      }
    }
    refreshChats();
    scrollDown(true);
  } catch { /* ignore */ }
}

newChatBtn.addEventListener("click", startNewChat);

/* ================= health + documents ================= */

async function checkHealth() {
  try {
    const r = await fetch("/api/health");
    const j = await r.json();
    healthDot.classList.toggle("ok", j.status === "ok");
    healthText.textContent = j.status === "ok" ? "Model resident · offline" : "Starting…";
  } catch {
    healthDot.classList.remove("ok");
    healthText.textContent = "Server unreachable";
  }
}

async function refreshDocs() {
  try {
    const r = await fetch("/api/documents");
    const j = await r.json();
    docList.innerHTML = "";
    for (const d of j.documents) {
      const li = document.createElement("li");
      li.textContent = `${d.filename} · ${d.chunks} chunks`;
      docList.appendChild(li);
    }
  } catch { /* endpoint optional */ }
}

pdfInput.addEventListener("change", async () => {
  const file = pdfInput.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  healthText.textContent = `Indexing ${file.name}…`;
  try {
    const r = await fetch("/api/upload-pdf", { method: "POST", body: fd });
    const j = await r.json();
    healthText.textContent = `Indexed ${j.filename} (${j.chunks} chunks)`;
    refreshDocs();
  } catch {
    healthText.textContent = "PDF indexing failed";
  }
  pdfInput.value = "";
});

/* ================= photo attachments (chatbot-style) ================= */

photoInput.addEventListener("change", async () => {
  const file = photoInput.files[0];
  if (!file) return;
  const url = URL.createObjectURL(file);
  pendingAttachment = { name: file.name, text: null, url };
  renderAttachChip("reading…");
  photoBtn.classList.add("working");

  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await fetch("/api/upload-photo", { method: "POST", body: fd });
    const j = await r.json();
    if (!j.ok || !j.text) throw new Error(j.error || "no text found");
    pendingAttachment.text = j.text;
    renderAttachChip(`ready · ${Math.round((j.confidence || 0) * 100)}%`, true);
  } catch (err) {
    renderAttachChip(`failed: ${err.message}`);
    pendingAttachment.text = null;
  } finally {
    photoBtn.classList.remove("working");
    photoInput.value = "";
  }
});

function renderAttachChip(state, ok = false) {
  if (!pendingAttachment) { attachRow.innerHTML = ""; return; }
  attachRow.innerHTML = `
    <div class="attach-chip">
      <img src="${pendingAttachment.url}" alt="" />
      <span>${escapeHtml(pendingAttachment.name)}</span>
      <span class="state${ok ? " ok" : ""}">${escapeHtml(state)}</span>
      <button class="rm" title="Remove">&#10005;</button>
    </div>`;
  attachRow.querySelector(".rm").addEventListener("click", clearAttachment);
}

function clearAttachment() {
  if (pendingAttachment && pendingAttachment.url) URL.revokeObjectURL(pendingAttachment.url);
  pendingAttachment = null;
  attachRow.innerHTML = "";
}

/* ================= thinking toggle ================= */

thinkBtn.addEventListener("click", () => {
  thinkOn = !thinkOn;
  thinkBtn.classList.toggle("active", thinkOn);
});

/* ================= rendering ================= */

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/* Protect LaTeX + fenced code from the markdown pass, then restore. */
function renderRich(el, text) {
  const stash = [];
  let protectedText = text.replace(/```(\w*)\n([\s\S]*?)(?:```|$)/g, (m, lang, code) => {
    stash.push(`<pre><code>${escapeHtml(code)}</code></pre>`);
    return `\u0000${stash.length - 1}\u0000`;
  });
  protectedText = protectedText.replace(
    /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+\$)/g,
    (m) => {
      stash.push(m);
      return `\u0000${stash.length - 1}\u0000`;
    }
  );

  let html = escapeHtml(protectedText);

  html = html
    .replace(/^#{1,4}\s+(.+)$/gm, "<p><strong>$1</strong></p>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");

  html = html.replace(/((?:^\d+\.\s+.+(?:\n|$))+)/gm, (block) => {
    const items = block.trim().split("\n").map((l) => l.replace(/^\d+\.\s+/, ""));
    return `<ol>${items.map((i) => `<li>${i}</li>`).join("")}</ol>\n`;
  });
  html = html.replace(/((?:^[-*]\s+.+(?:\n|$))+)/gm, (block) => {
    const items = block.trim().split("\n").map((l) => l.replace(/^[-*]\s+/, ""));
    return `<ul>${items.map((i) => `<li>${i}</li>`).join("")}</ul>\n`;
  });

  html = html
    .split(/\n{2,}/)
    .map((p) => (p.match(/^<[ou]l>|^\u0000/) ? p : `<p>${p.replace(/\n/g, "<br>")}</p>`))
    .join("");

  html = html.replace(/\u0000(\d+)\u0000/g, (_, i) => stash[+i]);
  el.innerHTML = html;

  if (window.renderMathInElement) {
    renderMathInElement(el, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "\\(", right: "\\)", display: false },
        { left: "$", right: "$", display: false },
      ],
      throwOnError: false,
    });
  }
}

function addUserMsg(text, attachment) {
  const div = document.createElement("div");
  div.className = "msg user";
  let inner = "";
  if (attachment && attachment.url) {
    inner += `<img class="photo-thumb" src="${attachment.url}" alt="attached photo" />`;
  } else if (attachment && attachment.name) {
    inner += `<div class="attach-note">&#128247; ${escapeHtml(attachment.name)}</div>`;
  }
  inner += `<div class="bubble">${escapeHtml(text)}</div>`;
  div.innerHTML = inner;
  chatEl.appendChild(div);
}

function addAssistantMsg() {
  const div = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = `
    <div class="msg-head"><span class="theta">&Theta;</span><span class="intent-tag"></span></div>
    <div class="think-slot"></div>
    <div class="msg-body"><span class="cursor-blink"></span></div>
    <div class="extras"></div>`;
  chatEl.appendChild(div);
  return div;
}

function scrollDown(force) {
  const nearBottom = chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight < 140;
  if (force || nearBottom) chatEl.scrollTop = chatEl.scrollHeight;
}

/* ================= ask flow (SSE) ================= */

async function askStream(query) {
  if (busy) return;
  setBusy(true);
  mainEl.classList.remove("empty");
  activeAbort = new AbortController();

  // Lazily create the chat so empty chats never pile up in history.
  if (!currentChatId) {
    try {
      const r = await fetch("/api/chats", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      currentChatId = (await r.json()).id;
    } catch { /* stream still works without persistence */ }
  }

  const attachment = pendingAttachment && pendingAttachment.text ? pendingAttachment : null;
  addUserMsg(query, attachment ? { url: attachment.url, name: attachment.name } : null);

  const payload = {
    query,
    chat_id: currentChatId,
    think: thinkOn,
    attachment_text: attachment ? attachment.text : null,
    attachment_name: attachment ? attachment.name : null,
  };
  pendingAttachment = null; // thumbnail URL stays alive for the bubble
  attachRow.innerHTML = "";

  const msg = addAssistantMsg();
  const body = msg.querySelector(".msg-body");
  const extras = msg.querySelector(".extras");
  const intentTag = msg.querySelector(".intent-tag");
  const thinkSlot = msg.querySelector(".think-slot");
  scrollDown(true);

  let fullText = "";
  let thinkText = "";
  let thinkBlock = null;
  let meta = null;
  let lastRender = 0;
  let stopped = false;

  try {
    const resp = await fetch("/api/ask/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: activeAbort.signal,
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split("\n\n");
      buffer = events.pop();
      for (const raw of events) {
        if (!raw.startsWith("data: ")) continue;
        const ev = JSON.parse(raw.slice(6));

        if (ev.type === "meta") {
          meta = ev;
          intentTag.textContent = ev.intent;
        } else if (ev.type === "think") {
          thinkText += ev.text;
          if (!thinkBlock) {
            thinkBlock = document.createElement("details");
            thinkBlock.className = "think-block streaming";
            thinkBlock.open = true;
            thinkBlock.innerHTML = `<summary>Thinking</summary><div class="think-text"></div>`;
            thinkSlot.appendChild(thinkBlock);
          }
          const now = performance.now();
          if (now - lastRender > 150) {
            thinkBlock.querySelector(".think-text").textContent = thinkText;
            lastRender = now;
            scrollDown();
          }
        } else if (ev.type === "delta") {
          if (thinkBlock && thinkBlock.open) {
            // Answer started: collapse the reasoning out of the way.
            thinkBlock.querySelector(".think-text").textContent = thinkText;
            thinkBlock.classList.remove("streaming");
            thinkBlock.open = false;
          }
          fullText += ev.text;
          const now = performance.now();
          if (now - lastRender > 120) {
            renderRich(body, fullText);
            body.insertAdjacentHTML("beforeend", '<span class="cursor-blink"></span>');
            lastRender = now;
            scrollDown();
          }
        } else if (ev.type === "verifying") {
          renderRich(body, fullText);
          healthText.textContent = "Checking proof in Lean 4…";
        } else if (ev.type === "lean") {
          if (meta) meta.lean = ev;
        } else if (ev.type === "done") {
          renderRich(body, fullText);
          finishExtras(extras, meta, ev.tokens_per_second, fullText);
          if (ev.tokens_per_second) {
            perfText.textContent = `${ev.tokens_per_second.toFixed(1)} tok/s`;
          }
          checkHealth();
        } else if (ev.type === "error") {
          renderRich(body, fullText || "");
          const p = document.createElement("p");
          p.className = "error-text";
          p.textContent = ev.message;
          body.appendChild(p);
        }
      }
    }
    if (thinkBlock) {
      thinkBlock.querySelector(".think-text").textContent = thinkText;
      thinkBlock.classList.remove("streaming");
      thinkBlock.open = false;
    }
    if (!fullText && !body.textContent.trim()) {
      body.innerHTML = '<p class="error-text">No response received.</p>';
    } else if (fullText) {
      renderRich(body, fullText);
      if (!extras.childElementCount) finishExtras(extras, meta, null, fullText);
    }
  } catch (err) {
    if (err && err.name === "AbortError") {
      stopped = true;
      renderRich(body, fullText || "");
      const note = document.createElement("p");
      note.className = "meta-line";
      note.textContent = "Generation stopped.";
      extras.appendChild(note);
      if (fullText) finishExtras(extras, meta, null, fullText);
    } else {
      body.innerHTML = `<p class="error-text">Connection failed: ${escapeHtml(String(err))}</p>`;
    }
  } finally {
    activeAbort = null;
    setBusy(false);
    scrollDown();
    refreshChats();
    if (stopped) healthText.textContent = "Stopped";
  }
}

stopBtn.addEventListener("click", () => {
  if (activeAbort) activeAbort.abort();
});

function finishExtras(extras, meta, tps, fullText) {
  extras.innerHTML = "";

  if (meta && meta.sympy_result) {
    const badge = document.createElement("div");
    badge.className = "verify-badge";
    badge.innerHTML = `<span>&#10003; Verified by SymPy</span><span class="result">${escapeHtml(meta.sympy_result)}</span>`;
    badge.addEventListener("click", () => badge.classList.toggle("open"));
    extras.appendChild(badge);
  }

  if (meta && meta.lean && meta.lean.status !== "unavailable") {
    const badge = document.createElement("div");
    const ok = meta.lean.status === "verified";
    badge.className = "verify-badge lean" + (ok ? "" : " failed");
    const label = ok
      ? `&#10003; Formally verified (Lean 4${meta.lean.attempts > 1 ? ", after repair" : ""})`
      : "&#9888; Lean 4 rejected the formal proof";
    badge.innerHTML = `<span>${label}</span><span class="result">${escapeHtml((meta.lean.output || "").slice(0, 400))}</span>`;
    badge.addEventListener("click", () => badge.classList.toggle("open"));
    extras.appendChild(badge);
  }

  if (meta && meta.counterexample) {
    const ce = meta.counterexample;
    const badge = document.createElement("div");
    const refuted = ce.verdict === "refuted";
    badge.className = "verify-badge" + (refuted ? " refuted" : "");
    const label = refuted
      ? `&#10007; Counterexample found: ${escapeHtml(
          Object.entries(ce.counterexample || {}).map(([k, v]) => `${k} = ${v}`).join(", ") || "claim is false"
        )}`
      : "&#10003; No counterexample in tested domain";
    badge.innerHTML = `<span>${label}</span><span class="result">${escapeHtml(ce.detail || "")}</span>`;
    badge.addEventListener("click", () => badge.classList.toggle("open"));
    extras.appendChild(badge);
  }

  // LaTeX document detection -> preview button
  const tex = extractTex(fullText || "");
  if (tex) {
    const btn = document.createElement("button");
    btn.className = "preview-btn";
    btn.innerHTML = "&#128196; Preview document";
    btn.addEventListener("click", () => openPreview(tex));
    extras.appendChild(btn);
  }

  if (meta && meta.sources && meta.sources.length) {
    const row = document.createElement("div");
    row.className = "sources-row";
    for (const s of meta.sources) {
      const chip = document.createElement("span");
      chip.className = "source-chip";
      const label = s.source.startsWith("pdf:")
        ? s.source.slice(4).replace("#p", " · page ")
        : s.source;
      chip.textContent = label;
      chip.title = s.content.slice(0, 300);
      row.appendChild(chip);
    }
    extras.appendChild(row);
  }

  if (tps) {
    const line = document.createElement("div");
    line.className = "meta-line";
    line.textContent = `${tps.toFixed(1)} tokens/sec · on-device`;
    extras.appendChild(line);
  }
}

/* ================= LaTeX preview ================= */

function extractTex(text) {
  const fenced = text.match(/```(?:latex|tex)\s*\n([\s\S]*?)```/);
  if (fenced) return fenced[1].trim();
  if (text.includes("\\documentclass")) {
    const start = text.indexOf("\\documentclass");
    const endTag = "\\end{document}";
    const end = text.indexOf(endTag);
    if (end > start) return text.slice(start, end + endTag.length).trim();
  }
  return null;
}

function applyPreviewWidth(px) {
  const min = 280;
  const max = Math.min(window.innerWidth * 0.85, 1100);
  const w = Math.max(min, Math.min(max, Math.round(px)));
  previewPanel.style.setProperty("--preview-width", `${w}px`);
  return w;
}

function restorePreviewWidth() {
  const saved = parseInt(localStorage.getItem(PREVIEW_WIDTH_KEY) || "", 10);
  if (Number.isFinite(saved) && saved > 0) applyPreviewWidth(saved);
}

function applyPreviewZoom() {
  const scale = PREVIEW_ZOOM_STEPS[previewZoomIdx] ?? 1;
  previewBody.style.setProperty("--preview-scale", String(scale));
  localStorage.setItem(PREVIEW_ZOOM_KEY, String(previewZoomIdx));
}

function restorePreviewZoom() {
  const saved = parseInt(localStorage.getItem(PREVIEW_ZOOM_KEY) || "", 10);
  if (Number.isFinite(saved) && saved >= 0 && saved < PREVIEW_ZOOM_STEPS.length) {
    previewZoomIdx = saved;
  }
  applyPreviewZoom();
}

function openPreview(texSource) {
  currentTexSource = texSource;
  previewBody.innerHTML = texToHtml(texSource);
  if (window.renderMathInElement) {
    renderMathInElement(previewBody, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
      ],
      throwOnError: false,
    });
  }
  restorePreviewWidth();
  restorePreviewZoom();
  previewPanel.classList.remove("hidden");
  previewResizer.classList.remove("hidden");
}

function closePreview() {
  previewPanel.classList.add("hidden");
  previewResizer.classList.add("hidden");
}

/* Minimal LaTeX -> HTML for previewing (structure + math; not a compiler). */
function texToHtml(src) {
  let body = src;
  const docMatch = src.match(/\\begin\{document\}([\s\S]*?)\\end\{document\}/);
  if (docMatch) body = docMatch[1];

  let title = "";
  const titleMatch = src.match(/\\title\{([^}]*)\}/);
  if (titleMatch) title = titleMatch[1];
  const authorMatch = src.match(/\\author\{([^}]*)\}/);
  const dateMatch = src.match(/\\date\{([^}]*)\}/);

  // Protect math spans from the structural replacements.
  const stash = [];
  body = body.replace(
    /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\begin\{(?:equation|align)\*?\}[\s\S]+?\\end\{(?:equation|align)\*?\}|\$[^$\n]+\$|\\\([\s\S]+?\\\))/g,
    (m) => {
      // Normalize environments KaTeX auto-render can't see into.
      let math = m;
      math = math.replace(/\\begin\{equation\*?\}/g, "\\[").replace(/\\end\{equation\*?\}/g, "\\]");
      math = math.replace(/\\begin\{align\*?\}/g, "\\[\\begin{aligned}").replace(/\\end\{align\*?\}/g, "\\end{aligned}\\]");
      stash.push(math);
      return `\u0000${stash.length - 1}\u0000`;
    }
  );

  body = body
    .replace(/%.*$/gm, "")
    // Drop preamble metadata so it doesn't leak as body text (also after extract).
    .replace(/\\title\{[^}]*\}/g, "")
    .replace(/\\author\{[^}]*\}/g, "")
    .replace(/\\date\{[^}]*\}/g, "")
    .replace(/\\maketitle/g, "")
    .replace(/\\section\*?\{([^}]*)\}/g, "\n\n<h2>$1</h2>\n\n")
    .replace(/\\subsection\*?\{([^}]*)\}/g, "\n\n<h3>$1</h3>\n\n")
    .replace(/\\begin\{itemize\}/g, "<ul>")
    .replace(/\\end\{itemize\}/g, "</ul>")
    .replace(/\\begin\{enumerate\}/g, "<ol>")
    .replace(/\\end\{enumerate\}/g, "</ol>")
    .replace(/\\item\s*/g, "</li><li>")
    .replace(/<ul>\s*<\/li>/g, "<ul>")
    .replace(/<ol>\s*<\/li>/g, "<ol>")
    .replace(/<li>([\s\S]*?)<\/ul>/g, "<li>$1</li></ul>")
    .replace(/<li>([\s\S]*?)<\/ol>/g, "<li>$1</li></ol>")
    .replace(/\\textbf\{([^}]*)\}/g, "<strong>$1</strong>")
    .replace(/\\textit\{([^}]*)\}/g, "<em>$1</em>")
    .replace(/\\emph\{([^}]*)\}/g, "<em>$1</em>")
    .replace(/\\noindent/g, "")
    .replace(/\\(?:small|large|Large|centering)\b/g, "")
    .replace(/\\newpage|\\pagebreak/g, "")
    .replace(/\\\\/g, "<br>");

  let html = body
    .split(/\n{2,}/)
    .map((p) => {
      const t = p.trim();
      if (!t) return "";
      if (t.startsWith("<h") || t.startsWith("<ul") || t.startsWith("<ol") || t.startsWith("<li")) return t;
      return `<p>${t}</p>`;
    })
    .join("\n");

  html = html.replace(/\u0000(\d+)\u0000/g, (_, i) => stash[+i]);

  let head = "";
  if (title) head += `<h1>${escapeHtml(title)}</h1>`;
  const byline = [];
  if (authorMatch && authorMatch[1].trim()) byline.push(escapeHtml(authorMatch[1].trim()));
  if (dateMatch && dateMatch[1].trim() && dateMatch[1].trim() !== "\\today") {
    byline.push(escapeHtml(dateMatch[1].trim()));
  }
  if (byline.length) head += `<div class="doc-author">${byline.join(" · ")}</div>`;
  return head + html;
}

document.getElementById("close-preview").addEventListener("click", closePreview);

document.getElementById("preview-zoom-in").addEventListener("click", () => {
  if (previewZoomIdx < PREVIEW_ZOOM_STEPS.length - 1) {
    previewZoomIdx += 1;
    applyPreviewZoom();
  }
});
document.getElementById("preview-zoom-out").addEventListener("click", () => {
  if (previewZoomIdx > 0) {
    previewZoomIdx -= 1;
    applyPreviewZoom();
  }
});

/* Drag handle: resize preview panel; persist width. */
(function initPreviewResizer() {
  if (!previewResizer) return;
  let dragging = false;
  let startX = 0;
  let startW = 0;

  function onPointerDown(e) {
    if (previewPanel.classList.contains("hidden")) return;
    dragging = true;
    startX = e.clientX;
    startW = previewPanel.getBoundingClientRect().width;
    previewResizer.classList.add("dragging");
    document.body.classList.add("preview-resizing");
    previewResizer.setPointerCapture?.(e.pointerId);
    e.preventDefault();
  }
  function onPointerMove(e) {
    if (!dragging) return;
    // Dragging left grows the preview (panel is on the right).
    applyPreviewWidth(startW + (startX - e.clientX));
  }
  function onPointerUp(e) {
    if (!dragging) return;
    dragging = false;
    previewResizer.classList.remove("dragging");
    document.body.classList.remove("preview-resizing");
    const w = previewPanel.getBoundingClientRect().width;
    localStorage.setItem(PREVIEW_WIDTH_KEY, String(Math.round(w)));
    try { previewResizer.releasePointerCapture?.(e.pointerId); } catch { /* ignore */ }
  }

  previewResizer.addEventListener("pointerdown", onPointerDown);
  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("pointercancel", onPointerUp);
})();

/* Server-side downloads — avoid createObjectURL / window.print(), which freeze
   Cursor's embedded browser (Electron). */
async function downloadViaServer(filename, content, kind) {
  const resp = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, content, kind }),
  });
  if (!resp.ok) throw new Error(`export failed (${resp.status})`);
  // Prefer the File System Access / native download path via a temporary
  // anchor fed by a data: URL (small text files only — .tex / HTML docs).
  const text = await resp.text();
  const mime = kind === "html" ? "text/html;charset=utf-8" : "application/x-tex;charset=utf-8";
  const href = `data:${mime},${encodeURIComponent(text)}`;
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function buildPrintableHtml(texSource) {
  const inner = previewBody.innerHTML || texToHtml(texSource);
  // Inline local KaTeX CSS so the file works offline after download.
  let katexCss = "";
  try {
    katexCss = await (await fetch("/static/vendor/katex/katex.min.css")).text();
  } catch { /* still readable without it */ }
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Theoria document</title>
<style>${katexCss}
  body { font-family: KaTeX_Main, "Latin Modern Roman", "Times New Roman", Times, serif;
         max-width: 720px; margin: 40px auto; padding: 0 24px; line-height: 1.65; color: #1a1a1a; }
  h1 { text-align: center; font-size: 1.55em; font-weight: 700; }
  h2 { font-size: 1.25em; margin: 1.5em 0 0.55em; }
  .doc-author { text-align: center; color: #555; margin-bottom: 1.75em; font-style: italic; }
  p { text-align: justify; }
  @media print { body { margin: 0; } }
</style></head><body>
${inner}
<p style="margin-top:40px;font-size:12px;color:#888;font-family:system-ui">
  Tip: open this file in Chrome or Safari → Print → Save as PDF
</p>
</body></html>`;
}

document.getElementById("download-tex").addEventListener("click", async () => {
  if (!currentTexSource) return;
  try {
    await downloadViaServer("theoria-document.tex", currentTexSource, "tex");
  } catch (err) {
    healthText.textContent = `Download failed: ${err.message}`;
  }
});

document.getElementById("save-pdf").addEventListener("click", async () => {
  if (!currentTexSource) return;
  try {
    const html = await buildPrintableHtml(currentTexSource);
    await downloadViaServer("theoria-document.html", html, "html");
    healthText.textContent = "Downloaded HTML — open in Chrome/Safari → Print → Save as PDF";
  } catch (err) {
    healthText.textContent = `Download failed: ${err.message}`;
  }
});

/* ================= composer ================= */

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = queryEl.value.trim();
  const hasAttachment = pendingAttachment && pendingAttachment.text;
  if ((!q && !hasAttachment) || busy) return;
  queryEl.value = "";
  queryEl.style.height = "auto";
  askStream(q || "Please solve the problem in the attached photo.");
});

queryEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

queryEl.addEventListener("input", () => {
  queryEl.style.height = "auto";
  queryEl.style.height = Math.min(queryEl.scrollHeight, 200) + "px";
});

document.querySelectorAll(".suggestions .chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    queryEl.value = chip.dataset.q || chip.textContent;
    form.requestSubmit();
  });
});

/* ================= init ================= */

checkHealth();
refreshDocs();
refreshChats();
setInterval(checkHealth, 15000);
