// ===== DSEE Buddy — frontend =====
const $ = (id) => document.getElementById(id);
const chatEl = $("chat"), inputEl = $("input"), formEl = $("form"), sendBtn = $("send");
const statusEl = $("status"), welcomeEl = $("welcome");
const fileInput = $("fileInput"), fileBar = $("fileBar"), fileLabel = $("fileLabel");

const PIN_KEY = "dsee-pin", DEVICE_KEY = "dsee-device", CONV_KEY = "dsee-conv";
let messages = [];            // ข้อความของบทสนทนาที่เปิดอยู่ [{role, content, route}]
let currentConv = null;       // id บทสนทนาปัจจุบัน (เก็บในฐานข้อมูลฝั่งเซิร์ฟเวอร์)
let attached = null;          // {name, text}
let controller = null;        // AbortController ของคำตอบที่กำลังสตรีม

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};

// รหัสเครื่อง: สร้างครั้งแรกแล้วจำไว้ในเบราว์เซอร์ ใช้แยกประวัติแชทของแต่ละเครื่อง (ไม่ต้องล็อกอิน)
const DEVICE = (() => {
  let d = store.get(DEVICE_KEY);
  if (!d || !/^[A-Za-z0-9_-]{8,64}$/.test(d)) {
    d = (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)).replace(/[^A-Za-z0-9_-]/g, "");
    store.set(DEVICE_KEY, d);
  }
  return d;
})();
currentConv = store.get(CONV_KEY);

// ---------------- Markdown แบบย่อ (ปลอดภัย: escape HTML ก่อนเสมอ) ----------------
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
function inline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s).,!?]|$)/g, "$1<i>$2</i>");
}
function renderMarkdown(text) {
  const out = [];
  const parts = text.split(/```/);
  parts.forEach((part, i) => {
    if (i % 2 === 1) {                       // บล็อกโค้ด
      const nl = part.indexOf("\n");
      const lang = nl > -1 ? part.slice(0, nl).trim() : "";
      const code = nl > -1 ? part.slice(nl + 1) : part;
      out.push(`<div class="codeblock"><div class="code-head"><span>${esc(lang || "code")}</span>` +
               `<button type="button" class="copy">คัดลอก</button></div>` +
               `<pre><code>${esc(code.replace(/\n$/, ""))}</code></pre></div>`);
      return;
    }
    let list = null;
    const flush = () => { if (list) { out.push(`<${list.t}>${list.items.join("")}</${list.t}>`); list = null; } };
    let para = [];
    const flushPara = () => { if (para.length) { out.push(`<p>${para.join("<br>")}</p>`); para = []; } };
    part.split("\n").forEach((line) => {
      const ul = line.match(/^\s*[-*•]\s+(.*)$/), ol = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
      const h = line.match(/^\s*#{1,4}\s+(.*)$/);
      if (ul || ol) {
        flushPara();
        const t = ul ? "ul" : "ol";
        if (!list || list.t !== t) { flush(); list = { t, items: [] }; }
        list.items.push(`<li>${inline(ul ? ul[1] : ol[2])}</li>`);
      } else if (h) {
        flushPara(); flush(); out.push(`<h4>${inline(h[1])}</h4>`);
      } else if (!line.trim()) {
        flushPara(); flush();
      } else {
        flush(); para.push(inline(line));
      }
    });
    flushPara(); flush();
  });
  return out.join("");
}

// ---------------- แสดงผล ----------------
const ROUTE_LABEL = {
  rule: "📘 ตอบจากข้อมูลหลักสูตรโดยตรง",
  curriculum: "🎓 โมเดล DSEE + ข้อมูลหลักสูตร",
  general: "💬 ผู้ช่วยทั่วไป",
  file: "📎 วิเคราะห์จากไฟล์",
};
function addRow(role, content, route) {
  welcomeEl.hidden = true;
  const row = document.createElement("div");
  row.className = `row ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "user") bubble.textContent = content;
  else bubble.innerHTML = content ? renderMarkdown(content) : '<span class="typing"><i></i><i></i><i></i></span>';
  row.appendChild(bubble);
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = route ? ROUTE_LABEL[route] || "" : "";
  if (role === "assistant") row.appendChild(meta);
  chatEl.appendChild(row);
  scrollDown();
  return { bubble, meta };
}
function scrollDown() { chatEl.scrollTop = chatEl.scrollHeight; }
function clearChat() {
  chatEl.querySelectorAll(".row").forEach((r) => r.remove());
  welcomeEl.hidden = false;
}
async function loadConversation(id) {
  try {
    const res = await fetch(`api/conversations/${encodeURIComponent(id)}`, { headers: authHeaders() });
    if (res.status === 401 && askPin()) return loadConversation(id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    currentConv = id; store.set(CONV_KEY, id);
    messages = data.messages.map(({ role, content, route }) => ({ role, content, route }));
    clearChat();
    messages.forEach((m) => addRow(m.role, m.content, m.route));
  } catch {
    currentConv = null; store.del(CONV_KEY); messages = []; clearChat();
  }
  highlightConv();
}
function newChat() {
  if (controller) controller.abort();
  currentConv = null; store.del(CONV_KEY); messages = [];
  clearChat(); clearFile(); highlightConv();
}

// ---------------- ลิ้นชักประวัติแชท ----------------
const drawer = $("drawer"), scrim = $("scrim"), convList = $("convList");
function openDrawer() { drawer.classList.add("open"); scrim.hidden = false; refreshConversations(); }
function closeDrawer() { drawer.classList.remove("open"); scrim.hidden = true; }
function fmtTime(t) {
  const d = new Date(t * 1000), now = new Date();
  return d.toDateString() === now.toDateString()
    ? d.toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("th-TH", { day: "numeric", month: "short" });
}
function highlightConv() {
  convList.querySelectorAll("li[data-id]").forEach((li) => li.classList.toggle("active", li.dataset.id === currentConv));
}
async function refreshConversations() {
  try {
    const res = await fetch("api/conversations", { headers: authHeaders() });
    if (!res.ok) throw new Error();
    const { conversations } = await res.json();
    convList.innerHTML = conversations.length ? "" : '<li class="conv-empty">ยังไม่มีประวัติแชท</li>';
    for (const c of conversations) {
      const li = document.createElement("li");
      li.dataset.id = c.id;
      li.innerHTML = `<div class="t"><b></b><small></small></div><button class="del" title="ลบ" aria-label="ลบ">🗑</button>`;
      li.querySelector("b").textContent = c.title;
      li.querySelector("small").textContent = `${fmtTime(c.updated_at)} · ${c.n} ข้อความ`;
      convList.appendChild(li);
    }
    highlightConv();
  } catch {
    convList.innerHTML = '<li class="conv-empty">โหลดประวัติไม่ได้</li>';
  }
}
convList.addEventListener("click", async (e) => {
  const li = e.target.closest("li[data-id]");
  if (!li) return;
  if (e.target.closest(".del")) {
    if (!confirm("ลบบทสนทนานี้?")) return;
    await fetch(`api/conversations/${encodeURIComponent(li.dataset.id)}`, { method: "DELETE", headers: authHeaders() });
    if (li.dataset.id === currentConv) newChat();
    return refreshConversations();
  }
  if (controller) controller.abort();
  await loadConversation(li.dataset.id);
  closeDrawer();
});
$("historyBtn").addEventListener("click", openDrawer);
$("closeDrawer").addEventListener("click", closeDrawer);
scrim.addEventListener("click", closeDrawer);
$("drawerNew").addEventListener("click", () => { newChat(); closeDrawer(); });

chatEl.addEventListener("click", (e) => {
  const btn = e.target.closest(".copy");
  if (btn) {
    const code = btn.closest(".codeblock").querySelector("code").textContent;
    navigator.clipboard?.writeText(code).then(() => {
      btn.textContent = "คัดลอกแล้ว ✓"; setTimeout(() => (btn.textContent = "คัดลอก"), 1500);
    });
  }
  const chip = e.target.closest(".chip");
  if (chip) { inputEl.value = chip.textContent; send(); }
});

// ---------------- ส่งข้อความ ----------------
function pinHeader() { const p = store.get(PIN_KEY); return p ? { "X-App-Pin": p } : {}; }
function authHeaders() { return { ...pinHeader(), "X-Device-Id": DEVICE }; }
function askPin() {
  const p = prompt("ใส่ PIN สำหรับเข้าใช้งาน (ดูได้จากหน้าจอคอมที่รันเซิร์ฟเวอร์)");
  if (p) store.set(PIN_KEY, p.trim());
  return !!p;
}
function setBusy(busy) {
  sendBtn.classList.toggle("stop", busy);
  sendBtn.setAttribute("aria-label", busy ? "หยุด" : "ส่ง");
  sendBtn.innerHTML = busy
    ? '<svg viewBox="0 0 24 24" width="18" height="18"><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/></svg>'
    : '<svg viewBox="0 0 24 24" width="20" height="20"><path fill="currentColor" d="M3.4 20.4 21 12 3.4 3.6 3.4 10l12.6 2-12.6 2z"/></svg>';
}

async function send() {
  if (controller) { controller.abort(); return; }          // ปุ่มเดียวกันใช้หยุดได้
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = ""; autosize();

  messages.push({ role: "user", content: text });
  addRow("user", attached ? `📎 ${attached.name}\n${text}` : text);
  const { bubble, meta } = addRow("assistant", "");
  const body = { message: text, conversation_id: currentConv, file_text: attached?.text || "", file_name: attached?.name || "" };

  controller = new AbortController();
  setBusy(true);
  let answer = "", route = "";
  const HB = /\u200b/g;                       // ตัวอักษรล่องหนที่เซิร์ฟเวอร์ส่งมากันสายหลุด
  const post = () => fetch("api/chat", {
    method: "POST", signal: controller.signal,
    headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify(body),
  });
  const RETRYABLE = new Set([502, 503, 504, 520, 521, 522, 523, 524, 530]);
  try {
    for (let attempt = 1; ; attempt++) {
      let raw = "";
      try {
        let res = await post();
        if (res.status === 401 && askPin()) res = await post();
        if (!res.ok) {
          const err = new Error(httpMessage(res.status, (await res.json().catch(() => ({}))).error));
          err.retry = RETRYABLE.has(res.status);
          throw err;
        }
        route = res.headers.get("X-Route") || "";
        const cid = res.headers.get("X-Conversation-Id");
        if (cid && cid !== currentConv) { currentConv = cid; body.conversation_id = cid; store.set(CONV_KEY, cid); }
        meta.textContent = ROUTE_LABEL[route] || "";
        const reader = res.body.getReader(), dec = new TextDecoder();
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          raw += dec.decode(value, { stream: true });
          answer = raw.replace(HB, "");
          if (answer.trim()) { bubble.innerHTML = renderMarkdown(answer); scrollDown(); }
        }
        break;
      } catch (err) {
        if (err.name === "AbortError") throw err;
        const canRetry = attempt < 2 && !answer.trim() && (err.retry || err instanceof TypeError);
        if (!canRetry) throw err;
        meta.textContent = "🔄 การเชื่อมต่อสะดุด กำลังลองใหม่…";
        await new Promise((r) => setTimeout(r, 3000));
      }
    }
    if (!answer.trim()) answer = "อืม… ตอนนี้ยังตอบไม่ได้ ลองถามใหม่อีกครั้งนะ";
  } catch (err) {
    if (err.name === "AbortError") answer += "\n\n_(หยุดแล้ว)_";
    else answer = `⚠️ ${err instanceof TypeError ? "สัญญาณเน็ตหลุด หรือเซิร์ฟเวอร์ที่คอมปิดอยู่ ลองส่งใหม่อีกครั้งนะ" : err.message}`;
  } finally {
    bubble.innerHTML = renderMarkdown(answer);
    messages.push({ role: "assistant", content: answer, route });
    if (drawer.classList.contains("open")) refreshConversations();
    controller = null;
    setBusy(false);
    scrollDown();
    checkHealth();
  }
}

function httpMessage(status, detail) {
  if (detail) return detail;
  if (status === 530 || status === 1033) return "ลิงก์นี้หมดอายุหรือคอมที่เปิดเซิร์ฟเวอร์ปิดไปแล้ว — ขอลิงก์ใหม่จากหน้าต่าง run.py (HTTP 530)";
  if (status === 502 || status === 503) return "เซิร์ฟเวอร์ที่คอมยังไม่พร้อม/เพิ่งรีสตาร์ต รอสักครู่แล้วลองใหม่ (HTTP " + status + ")";
  if (status === 524 || status === 504) return "โมเดลใช้เวลาคิดนานเกินไป ลองถามใหม่อีกครั้ง หรือถามให้สั้นลง (HTTP " + status + ")";
  return `HTTP ${status}`;
}

formEl.addEventListener("submit", (e) => { e.preventDefault(); send(); });
inputEl.addEventListener("keydown", (e) => {
  // Enter = ส่ง (บนคอม) / Shift+Enter = ขึ้นบรรทัดใหม่ ; บนมือถือกดปุ่มส่งเอา
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && window.matchMedia("(pointer:fine)").matches) {
    e.preventDefault(); send();
  }
});
function autosize() { inputEl.style.height = "auto"; inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px"; }
inputEl.addEventListener("input", autosize);

$("newChat").addEventListener("click", newChat);

// ---------------- แนบไฟล์ ----------------
function clearFile() { attached = null; fileBar.hidden = true; fileInput.value = ""; }
$("fileClear").addEventListener("click", clearFile);
fileInput.addEventListener("change", async () => {
  const f = fileInput.files[0];
  if (!f) return;
  fileBar.hidden = false; fileLabel.textContent = `⏳ กำลังอ่าน ${f.name}…`;
  const fd = new FormData(); fd.append("file", f);
  try {
    let res = await fetch("api/upload", { method: "POST", body: fd, headers: pinHeader() });
    if (res.status === 401 && askPin()) res = await fetch("api/upload", { method: "POST", body: fd, headers: pinHeader() });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    attached = { name: f.name, text: data.content };
    fileLabel.textContent = `📎 ${f.name} — พร้อมแล้ว ถามเกี่ยวกับไฟล์นี้ได้เลย${data.truncated ? " (ไฟล์ยาว อ่านเฉพาะช่วงแรก)" : ""}`;
  } catch (err) {
    fileLabel.textContent = `❌ ${err.message}`; attached = null;
  }
});

// ---------------- สถานะเซิร์ฟเวอร์ ----------------
async function checkHealth() {
  try {
    const h = await (await fetch("api/health")).json();
    if (!h.ollama) { statusEl.textContent = "ยังไม่ได้เปิด Ollama ในเครื่อง"; statusEl.className = "status bad"; return; }
    if (!h.dsee_model) { statusEl.textContent = "ไม่พบโมเดล dsee-typhoon ใน Ollama"; statusEl.className = "status bad"; return; }
    statusEl.textContent = "ออนไลน์";
    statusEl.className = "status ok";
    if (h.pin_required && !store.get(PIN_KEY) && !checkHealth.asked) { checkHealth.asked = true; askPin(); }
  } catch {
    statusEl.textContent = "ต่อเซิร์ฟเวอร์ไม่ได้"; statusEl.className = "status bad";
  }
}

if (currentConv) loadConversation(currentConv);
checkHealth();
setInterval(checkHealth, 30000);   // อัปเดตจุดสถานะทุก 30 วินาที
