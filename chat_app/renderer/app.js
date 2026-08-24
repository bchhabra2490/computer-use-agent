/* Electron renderer — talks to chat_bridge via preload. */

const state = {
  chats: [],
  chatId: null,
  messages: [],
  screenshotOn: false,
  busy: false,
  thinking: false,
  page: "chat", // chat | mcp
  mcp: [],
  avatars: {
    assistant: null,
    user: null,
    assistantId: null,
    userId: null,
  },
};

const $ = (id) => document.getElementById(id);

function relativeTime(iso) {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const secs = Math.floor((Date.now() - t) / 1000);
  if (secs < 45) return "Just now";
  if (secs < 3600) return `${Math.max(1, Math.floor(secs / 60))}m ago`;
  if (secs < 86400) return `${Math.max(1, Math.floor(secs / 3600))}h ago`;
  const days = Math.floor(secs / 86400);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  return new Date(t).toLocaleDateString();
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderSidebar() {
  const list = $("chat-list");
  list.innerHTML = "";
  for (const chat of state.chats) {
    const wrap = document.createElement("div");
    wrap.style.display = "flex";
    wrap.style.alignItems = "center";
    wrap.style.gap = "4px";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chat-row" + (chat.id === state.chatId ? " active" : "");
    btn.innerHTML = `
      <div class="chat-row-title">${esc(chat.title || "New chat")}</div>
      <div class="chat-row-meta"><span>${esc(relativeTime(chat.updated_at))}</span></div>
    `;
    btn.addEventListener("click", () => {
      showPage("chat");
      selectChat(chat.id);
    });
    const del = document.createElement("button");
    del.type = "button";
    del.className = "chat-row-del";
    del.title = "Delete";
    del.textContent = "×";
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteChat(chat.id);
    });
    wrap.append(btn, del);
    list.appendChild(wrap);
  }
}

function renderTranscript() {
  const el = $("transcript");
  el.innerHTML = "";
  if (!state.messages.length && !state.thinking) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.innerHTML = `<strong>Talk to Jarvis</strong>Send a message — same queue as wake-word voice.`;
    el.appendChild(empty);
    return;
  }
  for (const msg of state.messages) {
    const row = document.createElement("div");
    row.className = `row ${msg.role === "user" ? "user" : msg.role === "error" ? "error" : "assistant"}`;
    const avatar = document.createElement("img");
    avatar.className = "avatar";
    avatar.alt = "";
    const isUser = msg.role === "user";
    const src = isUser ? state.avatars.user : state.avatars.assistant;
    if (src) {
      avatar.src = src;
    } else {
      avatar.classList.add(isUser ? "avatar-fallback-user" : "avatar-fallback-assistant");
    }
    const col = document.createElement("div");
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = msg.content || "";
    col.appendChild(bubble);
    if (msg.screenshot_b64) {
      const img = document.createElement("img");
      img.className = "shot";
      img.alt = "Screenshot";
      img.src = `data:image/png;base64,${msg.screenshot_b64}`;
      img.addEventListener("click", () => {
        const w = window.open("");
        if (w) {
          w.document.write(`<img src="${img.src}" style="max-width:100%">`);
        }
      });
      col.appendChild(img);
    }
    row.append(avatar, col);
    el.appendChild(row);
  }
  if (state.thinking) {
    const t = document.createElement("div");
    t.className = "thinking";
    t.textContent = state.screenshotOn ? "Looking at the screen…" : "Working…";
    el.appendChild(t);
  }
  el.scrollTop = el.scrollHeight;
}

async function refreshChats() {
  const data = await window.cuaChat.get("/v1/chats");
  state.chats = data.chats || [];
  renderSidebar();
  if (!state.chatId && state.chats.length) {
    await selectChat(state.chats[0].id);
  } else if (!state.chats.length) {
    await newChat();
  } else if (state.chatId) {
    const cur = state.chats.find((c) => c.id === state.chatId);
    $("chat-title").textContent = (cur && cur.title) || "Chat";
  }
}

async function selectChat(id) {
  state.chatId = id;
  const data = await window.cuaChat.get(`/v1/chats/${id}/messages`);
  state.messages = data.messages || [];
  state.thinking = false;
  const cur = state.chats.find((c) => c.id === id);
  $("chat-title").textContent = (cur && cur.title) || "Chat";
  renderSidebar();
  renderTranscript();
}

async function newChat() {
  const data = await window.cuaChat.post("/v1/chats", { title: "New chat" });
  await refreshChats();
  if (data.chat) await selectChat(data.chat.id);
}

async function deleteChat(id) {
  if (!confirm("Delete this chat?")) return;
  await window.cuaChat.del(`/v1/chats/${id}`);
  state.chatId = null;
  state.messages = [];
  await refreshChats();
}

async function toggleShot() {
  state.screenshotOn = !state.screenshotOn;
  await window.cuaChat.post("/v1/prefs/screenshot", { on: state.screenshotOn });
  syncShotBtn();
}

function syncShotBtn() {
  const btn = $("btn-shot");
  btn.setAttribute("aria-pressed", state.screenshotOn ? "true" : "false");
  btn.title = state.screenshotOn ? "Screen attach on" : "Attach current screen";
}

async function send() {
  if (state.busy) return;
  const input = $("input");
  const text = input.value;
  if (!text.trim() && !state.screenshotOn) return;
  if (!state.chatId) await newChat();
  state.busy = true;
  state.thinking = true;
  $("btn-send").disabled = true;
  input.value = "";
  autosize();
  // Optimistic user bubble
  state.messages.push({
    role: "user",
    content: text.trim() || "(screenshot)",
    screenshot_b64: null,
  });
  renderTranscript();
  try {
    const res = await window.cuaChat.post("/v1/send", {
      chat_id: state.chatId,
      text,
      look_at_screen: state.screenshotOn,
    });
    if (res.warning) {
      state.messages.push({ role: "error", content: res.warning });
      state.thinking = false;
    }
    await refreshChats();
    const data = await window.cuaChat.get(`/v1/chats/${state.chatId}/messages`);
    state.messages = data.messages || [];
  } catch (err) {
    state.messages.push({ role: "error", content: String(err.message || err) });
    state.thinking = false;
  } finally {
    state.busy = false;
    $("btn-send").disabled = false;
    renderTranscript();
  }
}

async function loadAvatars() {
  try {
    const data = await window.cuaChat.get("/v1/avatars");
    if (data.assistant_b64) {
      state.avatars.assistant = `data:image/png;base64,${data.assistant_b64}`;
      state.avatars.assistantId = data.assistant_id;
    }
    if (data.user_b64) {
      state.avatars.user = `data:image/png;base64,${data.user_b64}`;
      state.avatars.userId = data.user_id;
    }
    renderTranscript();
  } catch {
    // Keep CSS fallbacks if bridge cannot render blobatars.
  }
}

async function pollStatus() {
  try {
    const st = await window.cuaChat.get("/v1/status");
    state.screenshotOn = !!st.screenshot_on;
    syncShotBtn();
    if (
      st.face_preset &&
      state.avatars.assistantId &&
      st.face_preset !== state.avatars.assistantId
    ) {
      await loadAvatars();
    }
    $("orch-status").textContent = st.orchestrator_alive
      ? "Orchestrator connected"
      : "Orchestrator not running";
    $("status-foot").textContent = st.orchestrator_alive
      ? "Ready · replies land here when spoken"
      : "Start: python orchestrator.py --auto";
    const inbox = st.inbox || [];
    if (inbox.length && state.chatId) {
      for (const line of inbox) {
        const text = String(line || "").trim();
        if (!text) continue;
        await window.cuaChat.post("/v1/assistant", {
          chat_id: state.chatId,
          text,
        });
      }
      state.thinking = false;
      const data = await window.cuaChat.get(`/v1/chats/${state.chatId}/messages`);
      state.messages = data.messages || [];
      await refreshChats();
      renderTranscript();
    }
  } catch (err) {
    $("status-foot").textContent = "Bridge offline — start chat from tray";
    $("orch-status").textContent = String(err.message || "offline");
  }
}

function autosize() {
  const input = $("input");
  input.style.height = "auto";
  input.style.height = `${Math.min(160, input.scrollHeight)}px`;
}

function showPage(page) {
  state.page = page;
  const chat = $("view-chat");
  const mcp = $("view-mcp");
  const mcpBtn = $("btn-mcp");
  if (page === "mcp") {
    chat.hidden = true;
    mcp.hidden = false;
    mcpBtn.classList.add("active");
    loadMcp();
  } else {
    chat.hidden = false;
    mcp.hidden = true;
    mcpBtn.classList.remove("active");
  }
}

function renderMcpList() {
  const list = $("mcp-list");
  list.innerHTML = "";
  if (!state.mcp.length) {
    const empty = document.createElement("div");
    empty.className = "mcp-empty";
    empty.textContent = "No MCP servers in mcp.json yet. Add one on the right.";
    list.appendChild(empty);
    return;
  }
  for (const conn of state.mcp) {
    const card = document.createElement("article");
    card.className = "mcp-card";
    const top = document.createElement("div");
    top.className = "mcp-card-top";
    const name = document.createElement("div");
    name.className = "mcp-card-name";
    name.textContent = conn.name;
    const pill = document.createElement("span");
    pill.className = "mcp-pill";
    pill.textContent = conn.transport || "http";
    top.append(name, pill);
    const meta = document.createElement("div");
    meta.className = "mcp-card-meta";
    const bits = [];
    if (conn.url) bits.push(conn.url);
    if (conn.command) {
      bits.push([conn.command, ...(conn.args || [])].join(" "));
    }
    if (conn.auth) bits.push(`auth: ${conn.auth}`);
    if (!conn.enabled) bits.push("disabled");
    meta.textContent = bits.join(" · ") || "Configured";
    const actions = document.createElement("div");
    actions.className = "mcp-card-actions";
    const del = document.createElement("button");
    del.type = "button";
    del.className = "mcp-del";
    del.textContent = "Remove";
    del.addEventListener("click", () => removeMcp(conn.name));
    actions.appendChild(del);
    card.append(top, meta, actions);
    list.appendChild(card);
  }
}

async function loadMcp() {
  try {
    const data = await window.cuaChat.get("/v1/mcp");
    state.mcp = data.connections || [];
    if (data.path) $("mcp-path").textContent = data.path;
    renderMcpList();
  } catch (err) {
    $("mcp-path").textContent = String(err.message || err);
    state.mcp = [];
    renderMcpList();
  }
}

function syncMcpFormKind() {
  const kind = $("mcp-kind").value;
  const http = kind !== "stdio";
  $("mcp-http-fields").hidden = !http;
  $("mcp-stdio-fields").hidden = http;
  syncMcpAuthFields();
}

function syncMcpAuthFields() {
  $("mcp-token-wrap").hidden = $("mcp-auth").value !== "token";
}

async function saveMcp(e) {
  e.preventDefault();
  const note = $("mcp-form-note");
  const btn = $("mcp-save");
  const kind = $("mcp-kind").value;
  const payload = {
    name: $("mcp-name").value.trim(),
    kind,
  };
  if (kind === "stdio") {
    payload.command = $("mcp-command").value.trim();
    payload.args = $("mcp-args").value;
    const envRaw = $("mcp-env").value.trim();
    if (envRaw) payload.env = envRaw;
  } else {
    payload.url = $("mcp-url").value.trim();
    payload.auth = $("mcp-auth").value;
    const token = $("mcp-token").value.trim();
    if (token) payload.token = token;
  }
  btn.disabled = true;
  note.className = "mcp-note";
  note.textContent = "Saving…";
  try {
    const res = await window.cuaChat.post("/v1/mcp", payload);
    note.className = "mcp-note ok";
    note.textContent = res.note || "Saved to mcp.json.";
    $("mcp-form").reset();
    syncMcpFormKind();
    await loadMcp();
  } catch (err) {
    note.className = "mcp-note error";
    note.textContent = String(err.message || err);
  } finally {
    btn.disabled = false;
  }
}

async function removeMcp(name) {
  if (!confirm(`Remove MCP connection “${name}” from mcp.json?`)) return;
  try {
    await window.cuaChat.del(`/v1/mcp/${encodeURIComponent(name)}`);
    await loadMcp();
  } catch (err) {
    alert(String(err.message || err));
  }
}

function wire() {
  $("btn-new").addEventListener("click", () => {
    showPage("chat");
    newChat();
  });
  $("btn-mcp").addEventListener("click", () => showPage("mcp"));
  $("btn-back-chat").addEventListener("click", () => showPage("chat"));
  $("mcp-kind").addEventListener("change", syncMcpFormKind);
  $("mcp-auth").addEventListener("change", syncMcpAuthFields);
  $("mcp-form").addEventListener("submit", saveMcp);
  $("btn-shot").addEventListener("click", () => toggleShot());
  $("btn-send").addEventListener("click", () => send());
  $("input").addEventListener("input", autosize);
  $("input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
  syncMcpFormKind();
}

async function boot() {
  wire();
  try {
    await refreshChats();
  } catch (err) {
    $("status-foot").textContent = `Cannot reach bridge: ${err.message || err}`;
  }
  await loadAvatars();
  await pollStatus();
  setInterval(pollStatus, 800);
}

boot();
