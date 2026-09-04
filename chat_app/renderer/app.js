/* Electron renderer — talks to chat_bridge via preload. */

const state = {
  chats: [],
  chatId: null,
  messages: [],
  screenshotOn: false,
  screenshotDisplays: null, // null = all, else number[]
  chatTtsOn: true,
  displays: [],
  shotMenuOpen: false,
  busy: false,
  pendingChatId: null,
  thinking: false,
  streamText: null,
  streamDone: false,
  page: "chat", // chat | mcp | speakers | systems
  mcp: [],
  speakers: [],
  passages: [],
  samples: [], // base64 wav per passage index
  recordingIndex: null,
  recorder: null,
  drafts: [],
  memories: [],
  editingMemory: null,
  observeRunning: false,
  faceEnabled: true,
  facePresets: [],
  faceCurrent: null,
  latency: null,
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
      closeSidebar();
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
      img.addEventListener("click", () => openShotLightbox(img.src));
      col.appendChild(img);
    }
    row.append(avatar, col);
    el.appendChild(row);
  }
  if (state.streamText) {
    const row = document.createElement("div");
    row.className = "row assistant";
    const avatar = document.createElement("img");
    avatar.className = "avatar";
    avatar.alt = "";
    if (state.avatars.assistant) {
      avatar.src = state.avatars.assistant;
    } else {
      avatar.classList.add("avatar-fallback-assistant");
    }
    const col = document.createElement("div");
    const bubble = document.createElement("div");
    bubble.className = "bubble streaming";
    bubble.textContent = state.streamText;
    col.appendChild(bubble);
    row.append(avatar, col);
    el.appendChild(row);
  } else if (state.thinking) {
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
  try {
    await window.cuaChat.post("/v1/prefs/active-chat", { chat_id: id });
  } catch {
    /* older bridge */
  }
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
  syncShotHint();
}

async function toggleTts() {
  state.chatTtsOn = !state.chatTtsOn;
  await window.cuaChat.post("/v1/prefs/tts", { on: state.chatTtsOn });
  syncTtsBtn();
  syncShotHint();
}

function syncShotBtn() {
  const btn = $("btn-shot");
  btn.setAttribute("aria-pressed", state.screenshotOn ? "true" : "false");
  btn.title = state.screenshotOn ? "Screen attach on" : "Attach current screen";
}

function syncTtsBtn() {
  const btn = $("btn-tts");
  if (!btn) return;
  const on = !!state.chatTtsOn;
  btn.setAttribute("aria-pressed", on ? "true" : "false");
  btn.title = on ? "Speak replies (on)" : "Speak replies (off)";
  const iconOn = btn.querySelector(".tts-icon-on");
  const iconOff = btn.querySelector(".tts-icon-off");
  if (iconOn) iconOn.hidden = !on;
  if (iconOff) iconOff.hidden = on;
}

function syncShotHint() {
  const hint = $("hint");
  if (!hint) return;
  const parts = ["Enter to send · Shift+Enter for newline"];
  if (state.screenshotOn) {
    parts.push(`Screen attach: ${screenshotDisplaysLabel()}`);
  }
  if (!state.chatTtsOn) {
    parts.push("TTS off");
  }
  hint.textContent = parts.join(" · ");
}

function screenshotDisplaysLabel() {
  if (!state.displays.length) return "all displays";
  if (state.screenshotDisplays == null) return "all displays";
  const selected = state.displays.filter((d) =>
    state.screenshotDisplays.includes(d.index)
  );
  if (!selected.length || selected.length === state.displays.length) return "all displays";
  if (selected.length === 1) {
    return selected[0].name || `screen ${selected[0].index}`;
  }
  return selected.map((d) => d.name || `screen ${d.index}`).join(", ");
}

function openShotLightbox(src) {
  const box = $("shot-lightbox");
  const img = $("shot-lightbox-img");
  if (!box || !img || !src) return;
  img.src = src;
  box.hidden = false;
}

function closeShotLightbox() {
  const box = $("shot-lightbox");
  const img = $("shot-lightbox-img");
  if (box) box.hidden = true;
  if (img) img.removeAttribute("src");
}

function closeShotMenu() {
  state.shotMenuOpen = false;
  const menu = $("shot-display-menu");
  const btn = $("btn-shot-menu");
  const backdrop = $("shot-menu-backdrop");
  if (menu) menu.hidden = true;
  if (backdrop) backdrop.hidden = true;
  if (btn) btn.setAttribute("aria-expanded", "false");
}

async function openShotMenu() {
  state.shotMenuOpen = true;
  const menu = $("shot-display-menu");
  const btn = $("btn-shot-menu");
  const backdrop = $("shot-menu-backdrop");
  if (menu) menu.hidden = false;
  if (backdrop) backdrop.hidden = false;
  if (btn) btn.setAttribute("aria-expanded", "true");
  await loadDisplays();
}

async function toggleShotMenu(e) {
  e?.stopPropagation?.();
  if (state.shotMenuOpen) closeShotMenu();
  else await openShotMenu();
}

function applyDisplaysPayload(data) {
  state.displays = data.displays || [];
  state.screenshotDisplays = data.all ? null : data.selected || null;
  renderDisplayMenu();
  syncShotHint();
}

function displayIsSelected(index) {
  if (state.screenshotDisplays == null) return true;
  return state.screenshotDisplays.includes(index);
}

function renderDisplayMenu() {
  const list = $("shot-display-list");
  const note = $("shot-display-note");
  if (!list) return;
  list.innerHTML = "";
  if (!state.displays.length) {
    if (note) note.textContent = "No displays detected.";
    return;
  }
  if (note) {
    note.textContent = "Tick the displays to include in the screenshot.";
  }
  for (const d of state.displays) {
    const label = document.createElement("label");
    label.className = "shot-menu-row";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = displayIsSelected(d.index);
    input.addEventListener("change", () => {
      void setDisplaySelectionFromChecks();
    });
    input.dataset.index = String(d.index);
    const text = document.createElement("span");
    text.innerHTML = `${esc(d.name || `Display ${d.index}`)}${
      d.main ? ' <span class="shot-menu-meta">main</span>' : ""
    }<span class="shot-menu-meta">screen ${d.index} · ${d.width}×${d.height}</span>`;
    label.append(input, text);
    list.appendChild(label);
  }
}

async function loadDisplays() {
  try {
    const data = await window.cuaChat.get("/v1/displays");
    applyDisplaysPayload(data);
  } catch (err) {
    const note = $("shot-display-note");
    if (note) note.textContent = String(err.message || err);
  }
}

async function saveDisplaySelection(indexes) {
  const data = await window.cuaChat.post("/v1/prefs/screenshot-displays", {
    displays: indexes,
  });
  applyDisplaysPayload(data);
}

async function setDisplaySelectionFromChecks() {
  const checked = Array.from(
    document.querySelectorAll("#shot-display-list input[type=checkbox]:checked")
  ).map((el) => Number(el.dataset.index));
  if (!checked.length) {
    // Keep at least one display selected.
    const fallback = state.displays.find((d) => d.main) || state.displays[0];
    if (fallback) await saveDisplaySelection([fallback.index]);
    else await saveDisplaySelection(state.displays.map((d) => d.index));
    return;
  }
  await saveDisplaySelection(checked);
}

async function send() {
  if (state.busy) return;
  const input = $("input");
  const text = input.value;
  if (!text.trim() && !state.screenshotOn) return;
  if (!state.chatId) await newChat();
  state.busy = true;
  state.pendingChatId = state.chatId;
  state.thinking = true;
  state.streamText = null;
  state.streamDone = false;
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
    // A successful POST only queues the turn. pollStatus unlocks sending after
    // the assistant reply is persisted, preserving user/assistant ordering.
    if (!state.thinking) {
      state.busy = false;
      state.pendingChatId = null;
      $("btn-send").disabled = false;
    }
    renderTranscript();
  }
}

async function loadAvatars() {
  try {
    const data = await window.cuaChat.get("/v1/avatars");
    if (data.assistant_b64) {
      state.avatars.assistant = `data:image/png;base64,${data.assistant_b64}`;
      state.avatars.assistantId = data.assistant_id;
      const mark = $("brand-mark");
      if (mark) {
        mark.src = state.avatars.assistant;
        mark.alt = data.assistant_id || "Jarvis";
        mark.title = data.assistant_id ? `Face: ${data.assistant_id}` : "Jarvis";
      }
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
    if ("screenshot_displays" in st) {
      state.screenshotDisplays = st.screenshot_displays == null ? null : st.screenshot_displays;
    }
    if ("chat_tts_on" in st) {
      state.chatTtsOn = !!st.chat_tts_on;
    }
    syncShotBtn();
    syncTtsBtn();
    syncShotHint();
    if (
      st.face_preset &&
      state.avatars.assistantId &&
      st.face_preset !== state.avatars.assistantId
    ) {
      await loadAvatars();
    }
    $("status-foot").textContent = st.orchestrator_alive
      ? "Orchestrator connected"
      : "Orchestrator not running — start: python orchestrator.py --auto";
    const appended = Number(st.assistant_appended || 0);
    const inbox = st.inbox || [];
    const stream = st.chat_stream;
    const streamChatId = stream && stream.chat_id ? String(stream.chat_id) : null;
    const streamText = stream && stream.text ? String(stream.text) : "";
    const streamDone = !!(stream && stream.done);
    let needRender = false;
    if (streamText && (!streamChatId || streamChatId === state.chatId)) {
      if (state.streamText !== streamText || state.streamDone !== streamDone) {
        state.streamText = streamText;
        state.streamDone = streamDone;
        state.thinking = false;
        needRender = true;
      }
    } else if (state.streamText && !streamDone) {
      // Stream cleared after persist — keep showing until messages reload.
    }
    // Legacy: older bridges returned inbox lines for the UI to save.
    if (inbox.length && state.chatId) {
      for (const line of inbox) {
        const text = String(line || "").trim();
        if (!text) continue;
        await window.cuaChat.post("/v1/assistant", {
          chat_id: state.chatId,
          text,
        });
      }
    }
    const appendedChatIds = (st.appended_chat_ids || []).map(String);
    const completedPending = appendedChatIds.length
      ? appendedChatIds.includes(String(state.pendingChatId || ""))
      : appended > 0;
    if (appended > 0 || inbox.length) {
      const visibleUpdated = appendedChatIds.length
        ? appendedChatIds.includes(String(state.chatId || ""))
        : true;
      if (visibleUpdated && state.chatId) {
        state.thinking = false;
        state.streamText = null;
        state.streamDone = false;
        const data = await window.cuaChat.get(`/v1/chats/${state.chatId}/messages`);
        state.messages = data.messages || [];
        renderTranscript();
        needRender = false;
      }
      await refreshChats();
      if (completedPending) {
        state.busy = false;
        state.pendingChatId = null;
        $("btn-send").disabled = false;
      }
    } else if (needRender) {
      renderTranscript();
    }
  } catch (err) {
    $("status-foot").textContent = "Bridge offline — start chat from tray";
  }
}

function autosize() {
  const input = $("input");
  input.style.height = "auto";
  input.style.height = `${Math.min(160, input.scrollHeight)}px`;
}

const PAGE_KEY = "cua-chat-page";
const PAGES = new Set(["chat", "mcp", "speakers", "systems"]);

function savedPage() {
  try {
    const page = sessionStorage.getItem(PAGE_KEY);
    if (page && PAGES.has(page)) return page;
  } catch {
    /* private mode / blocked storage */
  }
  return "chat";
}

function showPage(page) {
  if (!PAGES.has(page)) page = "chat";
  state.page = page;
  try {
    sessionStorage.setItem(PAGE_KEY, page);
  } catch {
    /* ignore */
  }
  closeSidebar();
  const chat = $("view-chat");
  const mcp = $("view-mcp");
  const speakers = $("view-speakers");
  const systems = $("view-systems");
  const mcpBtn = $("btn-mcp");
  const speakersBtn = $("btn-speakers");
  const systemsBtn = $("btn-systems");
  chat.hidden = page !== "chat";
  mcp.hidden = page !== "mcp";
  speakers.hidden = page !== "speakers";
  systems.hidden = page !== "systems";
  mcpBtn.classList.toggle("active", page === "mcp");
  speakersBtn.classList.toggle("active", page === "speakers");
  systemsBtn.classList.toggle("active", page === "systems");
  if (page === "mcp") loadMcp();
  if (page === "speakers") loadSpeakers();
  if (page === "systems") loadSystems();
  if (page !== "speakers") stopRecording(false);
}

const SIDEBAR_MQ = window.matchMedia("(max-width: 820px)");

function sidebarOpen() {
  return !!$("shell")?.classList.contains("sidebar-open");
}

function setSidebarOpen(open) {
  const shell = $("shell");
  if (!shell) return;
  const want = !!open && SIDEBAR_MQ.matches;
  shell.classList.toggle("sidebar-open", want);
  for (const btn of document.querySelectorAll("[data-menu-toggle]")) {
    btn.setAttribute("aria-expanded", want ? "true" : "false");
    btn.setAttribute("aria-label", want ? "Close menu" : "Open menu");
  }
}

function closeSidebar() {
  setSidebarOpen(false);
}

function toggleSidebar() {
  setSidebarOpen(!sidebarOpen());
}

function wireSidebar() {
  for (const btn of document.querySelectorAll("[data-menu-toggle]")) {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleSidebar();
    });
  }
  $("sidebar-backdrop")?.addEventListener("click", () => closeSidebar());
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && sidebarOpen()) closeSidebar();
  });
  const onMq = () => {
    if (!SIDEBAR_MQ.matches) closeSidebar();
  };
  if (typeof SIDEBAR_MQ.addEventListener === "function") {
    SIDEBAR_MQ.addEventListener("change", onMq);
  } else if (typeof SIDEBAR_MQ.addListener === "function") {
    SIDEBAR_MQ.addListener(onMq);
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
  wireSidebar();
  $("btn-new").addEventListener("click", () => {
    showPage("chat");
    newChat();
  });
  $("btn-mcp").addEventListener("click", () => showPage("mcp"));
  $("btn-speakers").addEventListener("click", () => showPage("speakers"));
  $("btn-systems").addEventListener("click", () => showPage("systems"));
  $("btn-back-chat").addEventListener("click", () => showPage("chat"));
  $("btn-back-chat-speakers").addEventListener("click", () => showPage("chat"));
  $("btn-back-chat-systems").addEventListener("click", () => showPage("chat"));
  $("mcp-kind").addEventListener("change", syncMcpFormKind);
  $("mcp-auth").addEventListener("change", syncMcpAuthFields);
  $("mcp-form").addEventListener("submit", saveMcp);
  $("speaker-save").addEventListener("click", saveSpeaker);
  $("speaker-name").addEventListener("input", syncSpeakerSaveEnabled);
  $("observe-toggle").addEventListener("change", toggleObserve);
  $("face-toggle").addEventListener("change", toggleFace);
  $("face-custom-form").addEventListener("submit", applyCustomFace);
  $("drafts-refresh").addEventListener("click", () => loadSystems());
  $("latency-refresh").addEventListener("click", () => loadLatency());
  $("drafts-accept-all").addEventListener("click", () => acceptDrafts({ all: true }));
  $("drafts-reject-all").addEventListener("click", () => rejectDrafts({ all: true }));
  $("drafts-collapse").addEventListener("click", toggleDraftsCollapsed);
  $("memories-collapse").addEventListener("click", toggleMemoriesCollapsed);
  $("memories-refresh").addEventListener("click", () => loadMemories());
  $("memory-save").addEventListener("click", saveMemoryEdit);
  $("memory-cancel").addEventListener("click", closeMemoryEditor);
  $("btn-shot").addEventListener("click", () => toggleShot());
  $("btn-tts").addEventListener("click", () => toggleTts());
  $("btn-shot-menu").addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    void toggleShotMenu(e);
  });
  const closeShotMenuFromBackdrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    closeShotMenu();
  };
  $("shot-menu-backdrop")?.addEventListener("pointerdown", closeShotMenuFromBackdrop);
  $("shot-menu-backdrop")?.addEventListener("click", closeShotMenuFromBackdrop);
  $("shot-lightbox")?.addEventListener("click", (e) => {
    if (e.target === $("shot-lightbox") || e.target === $("shot-lightbox-close")) {
      closeShotLightbox();
    }
  });
  $("shot-lightbox-close")?.addEventListener("click", () => closeShotLightbox());
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("shot-lightbox")?.hidden) {
      closeShotLightbox();
      return;
    }
    if (state.shotMenuOpen) closeShotMenu();
  });
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

function applyObserveStatus(data) {
  state.observeRunning = !!data.running;
  state.drafts = data.drafts || [];
  const mins = Math.round((data.draft_seconds || 600) / 60);
  $("observe-toggle").checked = state.observeRunning;
  $("observe-label").textContent = state.observeRunning ? "On" : "Off";
  $("observe-note").textContent = state.observeRunning
    ? `Watching clicks. Drafts appear after ~${mins} minutes of activity.`
    : `Watches your clicks and drafts memories/skills after ~${mins} minutes.`;
  $("drafts-note").textContent = state.drafts.length
    ? "Select items to accept, or accept the whole draft."
    : "No proposed drafts yet.";
  const count = $("drafts-count");
  if (count) count.textContent = state.drafts.length ? `(${state.drafts.length})` : "";
  renderDrafts();
}

function toggleDraftsCollapsed() {
  const card = $("drafts-card");
  const btn = $("drafts-collapse");
  const collapsed = !card.classList.contains("collapsed");
  card.classList.toggle("collapsed", collapsed);
  btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
}

async function loadSystems() {
  try {
    const data = await window.cuaChat.get("/v1/systems");
    applyObserveStatus(data);
  } catch (err) {
    const note = $("drafts-note");
    if (note) note.textContent = String(err.message || err);
    state.drafts = [];
    renderDrafts();
  }
  await Promise.all([loadMemories(), loadFace(), loadLatency()]);
}

function formatLatency(ms) {
  if (ms == null || !Number.isFinite(Number(ms))) return "—";
  const n = Number(ms);
  return n >= 1000 ? `${(n / 1000).toFixed(2)}s` : `${Math.round(n)}ms`;
}

function renderLatency(data) {
  state.latency = data;
  const primary = data.metrics?.voice_to_first_action || {};
  const summary = $("latency-summary");
  summary.innerHTML = `
    <div class="latency-stat latency-stat-primary">
      <span class="latency-value">${esc(formatLatency(primary.median_ms))}</span>
      <span class="latency-label">median voice → first action</span>
    </div>
    <div class="latency-stat">
      <span class="latency-value">${esc(formatLatency(primary.p90_ms))}</span>
      <span class="latency-label">P90</span>
    </div>
    <div class="latency-stat">
      <span class="latency-value">${esc(primary.count || 0)}</span>
      <span class="latency-label">measured tasks</span>
    </div>
  `;

  const stages = [
    ["Wake → transcript", "wake_to_transcript"],
    ["Transcript → plan", "transcript_to_plan"],
    ["Plan → agent", "plan_to_agent_start"],
    ["Agent → first action", "agent_start_to_first_action"],
  ];
  $("latency-breakdown").innerHTML = stages
    .map(([label, key]) => {
      const metric = data.metrics?.[key] || {};
      return `<div class="latency-stage"><span>${esc(label)}</span><strong>${esc(
        formatLatency(metric.median_ms)
      )}</strong></div>`;
    })
    .join("");

  const tbody = $("latency-recent");
  const recent = (data.recent || []).filter(
    (trace) => trace.durations_ms?.voice_to_first_action != null
  );
  tbody.innerHTML = recent.length
    ? recent
        .slice(0, 12)
        .map((trace) => {
          const d = trace.durations_ms || {};
          return `<tr>
            <td title="${esc(trace.task || "")}">${esc(trace.task || "Untitled task")}</td>
            <td>${esc(formatLatency(d.voice_to_first_action))}</td>
            <td>${esc(formatLatency(d.voice_to_task_complete))}</td>
            <td>${esc(relativeTime(trace.started_at))}</td>
          </tr>`;
        })
        .join("")
    : `<tr><td colspan="4" class="latency-empty">No voice-driven computer actions recorded yet.</td></tr>`;
  $("latency-note").textContent = data.report_path
    ? `Raw traces and Markdown report are stored in ${data.report_path}`
    : "End-to-end timing from wake detection to the first computer action.";
}

async function loadLatency() {
  const note = $("latency-note");
  try {
    const data = await window.cuaChat.get("/v1/latency");
    renderLatency(data);
  } catch (err) {
    note.textContent = String(err.message || err);
    $("latency-summary").innerHTML = "";
    $("latency-breakdown").innerHTML = "";
    $("latency-recent").innerHTML =
      '<tr><td colspan="4" class="latency-empty">Latency report unavailable.</td></tr>';
  }
}

function applyFaceStatus(data) {
  state.faceEnabled = !!data.enabled;
  state.facePresets = data.presets || [];
  state.faceCurrent = data.current || null;
  const toggle = $("face-toggle");
  const label = $("face-label");
  if (toggle) {
    toggle.checked = state.faceEnabled;
    toggle.disabled = !!data.env_disabled;
  }
  if (label) label.textContent = state.faceEnabled ? "On" : "Off";
  const note = $("face-note");
  if (note) {
    note.textContent = data.env_disabled
      ? "FACE_OVERLAY=0 in the environment — overlay stays off."
      : state.faceEnabled
        ? "Visible at the top center of the main display (click-through)."
        : "Hidden. Turn on to show the blobatar overlay.";
  }
  const cur = state.faceCurrent || {};
  const curEl = $("face-current");
  const blurbEl = $("face-current-blurb");
  if (curEl) curEl.textContent = cur.title || cur.id || "—";
  if (blurbEl) blurbEl.textContent = cur.blurb || (cur.id ? `Seed: ${cur.id}` : "");
  const preview = $("face-preview");
  if (preview) {
    if (data.preview_b64) {
      preview.src = `data:image/png;base64,${data.preview_b64}`;
      preview.hidden = false;
      preview.alt = cur.id || "blobatar";
    } else {
      preview.hidden = true;
    }
  }
  const seedInput = $("face-custom-seed");
  if (seedInput && cur.id && !state.facePresets.some((p) => p.id === cur.id && !p.custom)) {
    seedInput.value = cur.id;
  }
  renderBlobatarGrid();
}

function renderBlobatarGrid() {
  const grid = $("blobatar-grid");
  if (!grid) return;
  grid.innerHTML = "";
  if (!state.facePresets.length) {
    const empty = document.createElement("div");
    empty.className = "mcp-empty";
    empty.textContent = "No blobatar presets loaded.";
    grid.appendChild(empty);
    return;
  }
  for (const preset of state.facePresets) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "blobatar-option" + (preset.selected ? " selected" : "");
    btn.setAttribute("role", "option");
    btn.setAttribute("aria-selected", preset.selected ? "true" : "false");
    btn.title = preset.blurb || preset.id;
    const img = document.createElement("img");
    img.alt = "";
    img.width = 56;
    img.height = 56;
    if (preset.b64) img.src = `data:image/png;base64,${preset.b64}`;
    const name = document.createElement("div");
    name.className = "blobatar-option-name";
    name.textContent = preset.title || preset.id;
    const blurb = document.createElement("div");
    blurb.className = "blobatar-option-blurb";
    blurb.textContent = preset.custom ? "custom seed" : preset.blurb || "";
    btn.append(img, name, blurb);
    btn.addEventListener("click", () => selectFacePreset(preset.id));
    grid.appendChild(btn);
  }
}

async function loadFace() {
  const formNote = $("face-form-note");
  try {
    const data = await window.cuaChat.get("/v1/face");
    applyFaceStatus(data);
    if (formNote) {
      formNote.className = "mcp-note";
      formNote.textContent = "";
    }
  } catch (err) {
    if (formNote) {
      formNote.className = "mcp-note error";
      formNote.textContent = String(err.message || err);
    }
  }
}

async function toggleFace() {
  const on = $("face-toggle").checked;
  $("face-label").textContent = on ? "On" : "Off";
  const formNote = $("face-form-note");
  try {
    const data = await window.cuaChat.post("/v1/face", { enabled: on });
    applyFaceStatus(data);
    if (formNote) {
      formNote.className = "mcp-note ok";
      formNote.textContent = on ? "Face overlay on." : "Face overlay off.";
    }
  } catch (err) {
    $("face-toggle").checked = !on;
    $("face-label").textContent = !on ? "On" : "Off";
    if (formNote) {
      formNote.className = "mcp-note error";
      formNote.textContent = String(err.message || err);
    }
  }
}

async function selectFacePreset(id) {
  const formNote = $("face-form-note");
  try {
    const data = await window.cuaChat.post("/v1/face", { preset: id });
    applyFaceStatus(data);
    await loadAvatars();
    if (formNote) {
      formNote.className = "mcp-note ok";
      formNote.textContent = `Blobatar set to ${data.current?.id || id}.`;
    }
  } catch (err) {
    if (formNote) {
      formNote.className = "mcp-note error";
      formNote.textContent = String(err.message || err);
    }
  }
}

async function applyCustomFace(e) {
  e.preventDefault();
  const seed = ($("face-custom-seed").value || "").trim();
  const formNote = $("face-form-note");
  if (!seed) {
    if (formNote) {
      formNote.className = "mcp-note error";
      formNote.textContent = "Enter a seed name first.";
    }
    return;
  }
  await selectFacePreset(seed);
}

function toggleMemoriesCollapsed() {
  const card = $("memories-card");
  const btn = $("memories-collapse");
  const collapsed = !card.classList.contains("collapsed");
  card.classList.toggle("collapsed", collapsed);
  btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
}

async function loadMemories() {
  try {
    const data = await window.cuaChat.get("/v1/memories");
    state.memories = data.memories || [];
    const count = $("memories-count");
    if (count) count.textContent = state.memories.length ? `(${state.memories.length})` : "";
    $("memories-note").textContent = state.memories.length
      ? "Click a memory to edit its markdown."
      : "No saved memories yet.";
    renderMemories();
    if (state.editingMemory) {
      const still = state.memories.find(
        (m) => m.kind === state.editingMemory.kind && m.name === state.editingMemory.name
      );
      if (still) openMemoryEditor(still, { keepText: true });
      else closeMemoryEditor();
    }
  } catch (err) {
    $("memories-note").textContent = String(err.message || err);
    state.memories = [];
    renderMemories();
  }
}

function renderMemories() {
  const list = $("memories-list");
  list.innerHTML = "";
  if (!state.memories.length) {
    const empty = document.createElement("div");
    empty.className = "mcp-empty";
    empty.textContent = "No memories under memory/ yet.";
    list.appendChild(empty);
    return;
  }
  for (const mem of state.memories) {
    const btn = document.createElement("button");
    btn.type = "button";
    const active =
      state.editingMemory &&
      state.editingMemory.kind === mem.kind &&
      state.editingMemory.name === mem.name;
    btn.className = "memory-row" + (active ? " active" : "");
    btn.innerHTML = `
      <div class="memory-row-title">${esc(mem.kind)} / ${esc(mem.name)}</div>
      <div class="memory-row-meta">${esc(mem.rel || "")}</div>
      <div class="memory-row-preview">${esc(mem.preview || "")}</div>
    `;
    btn.addEventListener("click", () => openMemoryEditor(mem));
    list.appendChild(btn);
  }
}

function openMemoryEditor(mem, { keepText = false } = {}) {
  state.editingMemory = { kind: mem.kind, name: mem.name, rel: mem.rel };
  const editor = $("memory-editor");
  editor.hidden = false;
  $("memory-edit-title").textContent = `${mem.kind} / ${mem.name}`;
  $("memory-edit-rel").textContent = mem.rel || "";
  if (!keepText) {
    $("memory-edit-text").value = mem.text || "";
  }
  $("memory-edit-note").className = "mcp-note";
  $("memory-edit-note").textContent = "";
  renderMemories();
}

function closeMemoryEditor() {
  state.editingMemory = null;
  $("memory-editor").hidden = true;
  $("memory-edit-text").value = "";
  $("memory-edit-note").textContent = "";
  renderMemories();
}

async function saveMemoryEdit() {
  if (!state.editingMemory) return;
  const note = $("memory-edit-note");
  const btn = $("memory-save");
  btn.disabled = true;
  note.className = "mcp-note";
  note.textContent = "Saving…";
  try {
    const data = await window.cuaChat.post("/v1/memories", {
      kind: state.editingMemory.kind,
      name: state.editingMemory.name,
      text: $("memory-edit-text").value,
    });
    state.memories = data.memories || [];
    const count = $("memories-count");
    if (count) count.textContent = state.memories.length ? `(${state.memories.length})` : "";
    note.className = "mcp-note ok";
    note.textContent = `Saved ${data.rel || state.editingMemory.rel}.`;
    const updated = state.memories.find(
      (m) => m.kind === state.editingMemory.kind && m.name === state.editingMemory.name
    );
    if (updated) {
      $("memory-edit-text").value = updated.text || "";
      openMemoryEditor(updated, { keepText: true });
    }
    renderMemories();
  } catch (err) {
    note.className = "mcp-note error";
    note.textContent = String(err.message || err);
  } finally {
    btn.disabled = false;
  }
}

async function toggleObserve() {
  const on = $("observe-toggle").checked;
  $("observe-label").textContent = on ? "Starting…" : "Stopping…";
  try {
    const data = await window.cuaChat.post("/v1/observe", { enabled: on });
    applyObserveStatus(data);
  } catch (err) {
    $("observe-toggle").checked = !on;
    $("observe-label").textContent = !on ? "On" : "Off";
    alert(String(err.message || err));
  }
}

function selectedDraftItems(draftId) {
  return Array.from(
    document.querySelectorAll(`input[data-draft="${CSS.escape(draftId)}"]:checked`)
  ).map((el) => el.value);
}

function renderDrafts() {
  const list = $("drafts-list");
  list.innerHTML = "";
  if (!state.drafts.length) {
    const empty = document.createElement("div");
    empty.className = "mcp-empty";
    empty.textContent = "No drafts waiting. Turn on observe and use the Mac normally.";
    list.appendChild(empty);
    return;
  }
  for (const draft of state.drafts) {
    const card = document.createElement("article");
    card.className = "draft-card";
    const top = document.createElement("div");
    top.className = "mcp-card-top";
    const name = document.createElement("div");
    name.className = "mcp-card-name";
    name.textContent = draft.app || draft.id;
    const pill = document.createElement("span");
    pill.className = "mcp-pill";
    pill.textContent = draft.id;
    top.append(name, pill);
    card.appendChild(top);
    if (draft.url) {
      const meta = document.createElement("div");
      meta.className = "mcp-card-meta";
      meta.textContent = draft.url;
      card.appendChild(meta);
    }
    for (const item of draft.memories || []) {
      card.appendChild(draftItemEl(draft.id, item.ref, `Memory · ${item.kind}/${item.name}`, item.text));
    }
    for (const item of draft.skills || []) {
      card.appendChild(
        draftItemEl(
          draft.id,
          item.ref,
          `Skill · ${item.name}`,
          item.description || item.body
        )
      );
    }
    const actions = document.createElement("div");
    actions.className = "draft-actions";
    const acceptSel = document.createElement("button");
    acceptSel.type = "button";
    acceptSel.className = "accept";
    acceptSel.textContent = "Accept selected";
    acceptSel.addEventListener("click", () => {
      const items = selectedDraftItems(draft.id);
      if (!items.length) {
        alert("Select at least one item, or use Accept draft.");
        return;
      }
      acceptDrafts({ id: draft.id, items });
    });
    const acceptAll = document.createElement("button");
    acceptAll.type = "button";
    acceptAll.className = "accept";
    acceptAll.textContent = "Accept draft";
    acceptAll.addEventListener("click", () => acceptDrafts({ id: draft.id }));
    const reject = document.createElement("button");
    reject.type = "button";
    reject.textContent = "Reject draft";
    reject.addEventListener("click", () => rejectDrafts({ id: draft.id }));
    actions.append(acceptSel, acceptAll, reject);
    card.appendChild(actions);
    list.appendChild(card);
  }
}

function draftItemEl(draftId, ref, title, body) {
  const row = document.createElement("div");
  row.className = "draft-item";
  const label = document.createElement("label");
  const box = document.createElement("input");
  box.type = "checkbox";
  box.value = ref;
  box.dataset.draft = draftId;
  box.checked = true;
  const meta = document.createElement("div");
  meta.className = "draft-item-meta";
  const t = document.createElement("div");
  t.className = "draft-item-title";
  t.textContent = `${ref} · ${title}`;
  const b = document.createElement("div");
  b.className = "draft-item-body";
  b.textContent = body || "";
  meta.append(t, b);
  label.append(box, meta);
  row.appendChild(label);
  return row;
}

async function acceptDrafts({ id, items, all } = {}) {
  const note = $("drafts-note");
  note.className = "mcp-note";
  note.textContent = "Accepting…";
  try {
    const data = await window.cuaChat.post("/v1/observe/accept", {
      id: id || "",
      items: items || [],
      all: !!all,
    });
    applyObserveStatus(data);
    note.className = "mcp-note ok";
    const n = (data.written || []).length;
    note.textContent = n ? `Wrote ${n} item(s) to memory/skills.` : "Draft accepted.";
  } catch (err) {
    note.className = "mcp-note error";
    note.textContent = String(err.message || err);
  }
}

async function rejectDrafts({ id, all } = {}) {
  if (!confirm(all ? "Reject every proposed draft?" : `Reject draft “${id}”?`)) return;
  const note = $("drafts-note");
  note.className = "mcp-note";
  note.textContent = "Rejecting…";
  try {
    const data = await window.cuaChat.post("/v1/observe/reject", {
      id: id || "",
      all: !!all,
    });
    applyObserveStatus(data);
    note.className = "mcp-note ok";
    note.textContent = all ? "All drafts rejected." : "Draft rejected.";
  } catch (err) {
    note.className = "mcp-note error";
    note.textContent = String(err.message || err);
  }
}

function floatTo16BitPCM(float32) {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function encodeWavMono(float32, sampleRate) {
  const pcm = floatTo16BitPCM(float32);
  const buffer = new ArrayBuffer(44 + pcm.length * 2);
  const view = new DataView(buffer);
  const writeStr = (offset, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + pcm.length * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, pcm.length * 2, true);
  let offset = 44;
  for (let i = 0; i < pcm.length; i++, offset += 2) {
    view.setInt16(offset, pcm[i], true);
  }
  return buffer;
}

function bufferToBase64(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function downsampleTo16k(float32, inputRate) {
  if (inputRate === 16000) return float32;
  const ratio = inputRate / 16000;
  const outLen = Math.floor(float32.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    out[i] = float32[Math.floor(i * ratio)] || 0;
  }
  return out;
}

async function stopRecording(save) {
  const rec = state.recorder;
  if (!rec) return;
  state.recorder = null;
  const idx = state.recordingIndex;
  state.recordingIndex = null;
  try {
    rec.processor.disconnect();
    rec.source.disconnect();
    rec.stream.getTracks().forEach((t) => t.stop());
    await rec.context.close();
  } catch {
    /* ignore */
  }
  if (save && idx != null) {
    const samples = downsampleTo16k(Float32Array.from(rec.chunks), rec.sampleRate);
    if (samples.length < 16000 * 0.2) {
      const note = $("speaker-form-note");
      note.className = "mcp-note error";
      note.textContent = "Recording too short — try again.";
    } else {
      const wav = encodeWavMono(samples, 16000);
      state.samples[idx] = bufferToBase64(wav);
    }
  }
  renderPassages();
  syncSpeakerSaveEnabled();
}

async function startRecording(index) {
  if (state.recordingIndex != null) {
    await stopRecording(false);
  }
  try {
    await window.cuaChat.post("/v1/speakers/prepare", {});
  } catch {
    /* optional */
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
  } catch (err) {
    const note = $("speaker-form-note");
    note.className = "mcp-note error";
    note.textContent = `Mic permission failed: ${err.message || err}`;
    return;
  }
  const context = new AudioContext();
  const source = context.createMediaStreamSource(stream);
  const processor = context.createScriptProcessor(4096, 1, 1);
  const chunks = [];
  processor.onaudioprocess = (e) => {
    chunks.push(...e.inputBuffer.getChannelData(0));
  };
  const silent = context.createGain();
  silent.gain.value = 0;
  source.connect(processor);
  processor.connect(silent);
  silent.connect(context.destination);
  state.recordingIndex = index;
  state.recorder = {
    stream,
    context,
    source,
    processor,
    chunks,
    sampleRate: context.sampleRate,
  };
  renderPassages();
}

function syncSpeakerSaveEnabled() {
  const name = ($("speaker-name").value || "").trim();
  const need = state.passages.length || 5;
  const ready =
    name &&
    state.samples.length >= need &&
    state.samples.slice(0, need).every(Boolean);
  $("speaker-save").disabled = !ready || state.recordingIndex != null;
}

function renderSpeakersList() {
  const list = $("speakers-list");
  list.innerHTML = "";
  if (!state.speakers.length) {
    const empty = document.createElement("div");
    empty.className = "mcp-empty";
    empty.textContent = "No enrolled speakers yet. Record the passages on the right.";
    list.appendChild(empty);
    return;
  }
  for (const sp of state.speakers) {
    const card = document.createElement("article");
    card.className = "mcp-card";
    const top = document.createElement("div");
    top.className = "mcp-card-top";
    const name = document.createElement("div");
    name.className = "mcp-card-name";
    name.textContent = sp.display_name || sp.slug;
    const pill = document.createElement("span");
    pill.className = "mcp-pill";
    pill.textContent = sp.slug || "speaker";
    top.append(name, pill);
    const meta = document.createElement("div");
    meta.className = "mcp-card-meta";
    const bits = [];
    if (sp.enrolled_at) bits.push(String(sp.enrolled_at).slice(0, 19));
    if (sp.threshold != null) bits.push(`threshold ${sp.threshold}`);
    if (sp.sample_count) bits.push(`${sp.sample_count} samples`);
    meta.textContent = bits.join(" · ") || "Enrolled";
    const actions = document.createElement("div");
    actions.className = "mcp-card-actions";
    const del = document.createElement("button");
    del.type = "button";
    del.className = "mcp-del";
    del.textContent = "Remove";
    del.addEventListener("click", () => removeSpeaker(sp.slug || sp.display_name));
    actions.appendChild(del);
    card.append(top, meta, actions);
    list.appendChild(card);
  }
}

function renderPassages() {
  const list = $("passage-list");
  list.innerHTML = "";
  state.passages.forEach((p, index) => {
    const card = document.createElement("article");
    card.className = "passage-card" + (state.samples[index] ? " done" : "");
    const title = document.createElement("div");
    title.className = "passage-title";
    title.textContent = p.title + (p.short ? " · short" : "");
    const text = document.createElement("div");
    text.className = "passage-text";
    text.textContent = p.text;
    const actions = document.createElement("div");
    actions.className = "passage-actions";
    const btn = document.createElement("button");
    btn.type = "button";
    const recording = state.recordingIndex === index;
    btn.textContent = recording ? "Stop" : state.samples[index] ? "Re-record" : "Record";
    if (recording) btn.classList.add("recording");
    btn.addEventListener("click", async () => {
      if (state.recordingIndex === index) await stopRecording(true);
      else await startRecording(index);
    });
    const status = document.createElement("span");
    status.className = "passage-status" + (state.samples[index] ? " ok" : "");
    status.textContent = recording
      ? "Listening…"
      : state.samples[index]
        ? "Recorded"
        : "Not recorded";
    actions.append(btn, status);
    card.append(title, text, actions);
    list.appendChild(card);
  });
}

async function loadSpeakers() {
  const note = $("speaker-form-note");
  note.className = "mcp-note";
  note.textContent = "";
  try {
    const data = await window.cuaChat.get("/v1/speakers");
    state.speakers = data.speakers || [];
    state.passages = data.passages || [];
    if (!state.samples.length || state.samples.length !== state.passages.length) {
      state.samples = new Array(state.passages.length).fill(null);
    }
    $("speakers-sub").textContent = data.enabled
      ? `Model ${data.model || "speaker"} · ${state.speakers.length} enrolled`
      : "Speaker ID disabled (set SPEAKER_ID=1 in .env)";
    renderSpeakersList();
    renderPassages();
    syncSpeakerSaveEnabled();
  } catch (err) {
    $("speakers-sub").textContent = String(err.message || err);
    state.speakers = [];
    renderSpeakersList();
  }
}

async function removeSpeaker(name) {
  if (!confirm(`Remove speaker “${name}”?`)) return;
  try {
    await window.cuaChat.del(`/v1/speakers/${encodeURIComponent(name)}`);
    await loadSpeakers();
  } catch (err) {
    alert(String(err.message || err));
  }
}

async function saveSpeaker() {
  const name = ($("speaker-name").value || "").trim();
  const note = $("speaker-form-note");
  const btn = $("speaker-save");
  if (!name) return;
  btn.disabled = true;
  note.className = "mcp-note";
  note.textContent = "Saving profile…";
  try {
    const res = await window.cuaChat.post("/v1/speakers", {
      name,
      samples: state.samples,
    });
    note.className = "mcp-note ok";
    note.textContent = res.note || `Saved ${res.display_name || name}.`;
    $("speaker-name").value = "";
    state.samples = new Array(state.passages.length).fill(null);
    await loadSpeakers();
  } catch (err) {
    note.className = "mcp-note error";
    note.textContent = String(err.message || err);
  } finally {
    syncSpeakerSaveEnabled();
  }
}

async function boot() {
  wire();
  closeShotMenu();
  showPage(savedPage());
  try {
    await refreshChats();
  } catch (err) {
    $("status-foot").textContent = `Cannot reach bridge: ${err.message || err}`;
  }
  await loadAvatars();
  await pollStatus();
  setInterval(pollStatus, 250);
}

boot();
