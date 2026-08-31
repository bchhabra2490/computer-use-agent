const { app, BrowserWindow, ipcMain, shell, session, systemPreferences } = require("electron");
const fs = require("fs");
const path = require("path");
const http = require("http");

const BRIDGE_PORT = Number(process.env.CHAT_BRIDGE_PORT || 8743);
const CONTROL_PORT = Number(process.env.CHAT_CONTROL_PORT || 8744);
const RUNTIME_DIR =
  process.env.AGENT_RUNTIME_DIR ||
  path.join(path.dirname(__dirname), ".runtime");
const TOKEN_PATH = path.join(RUNTIME_DIR, "chat.token");

let mainWindow = null;
let quitting = false;
let controlServer = null;

function showMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  applyOverlayBehavior(mainWindow);
  mainWindow.show();
  mainWindow.focus();
}

function hideMainWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.hide();
}

function startControlServer() {
  controlServer = http.createServer((req, res) => {
    const expected = readToken();
    const authorized =
      expected && req.headers.authorization === `Bearer ${expected}`;
    if (!authorized) {
      res.writeHead(401).end();
      return;
    }
    if (req.method === "POST" && req.url === "/show") {
      showMainWindow();
      res.writeHead(204).end();
      return;
    }
    if (req.method === "POST" && req.url === "/hide") {
      hideMainWindow();
      res.writeHead(204).end();
      return;
    }
    res.writeHead(404).end();
  });
  controlServer.on("error", (err) => {
    console.error("chat control server failed:", err);
  });
  controlServer.listen(CONTROL_PORT, "127.0.0.1");
}

function readToken() {
  try {
    if (process.env.CHAT_BRIDGE_TOKEN) {
      return String(process.env.CHAT_BRIDGE_TOKEN).trim();
    }
    return fs.readFileSync(TOKEN_PATH, "utf8").trim();
  } catch {
    return "";
  }
}

function bridgeRequest(method, apiPath, body) {
  const token = readToken();
  const payload = body == null ? null : JSON.stringify(body);
  const timeout = apiPath === "/v1/speakers" ? 180000 : 60000;
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        hostname: "127.0.0.1",
        port: BRIDGE_PORT,
        path: apiPath,
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          ...(payload ? { "Content-Length": Buffer.byteLength(payload) } : {}),
        },
        timeout,
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          const raw = Buffer.concat(chunks).toString("utf8");
          let data = null;
          try {
            data = raw ? JSON.parse(raw) : null;
          } catch {
            data = { ok: false, error: "bad json", raw };
          }
          if (res.statusCode >= 400) {
            reject(new Error((data && data.error) || `HTTP ${res.statusCode}`));
            return;
          }
          resolve(data);
        });
      }
    );
    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("bridge timeout"));
    });
    if (payload) req.write(payload);
    req.end();
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Float over other Spaces / fullscreen apps (macOS overlay behavior). */
function applyOverlayBehavior(win) {
  if (!win || win.isDestroyed()) return;
  try {
    if (process.platform === "darwin") {
      win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
      // "floating" keeps it above normal apps and fullscreen Spaces without
      // covering the menu bar the way "screen-saver" does.
      win.setAlwaysOnTop(true, "floating");
    } else {
      win.setAlwaysOnTop(true);
    }
  } catch {
    /* older Electron */
  }
}

async function withChatHiddenForCapture(fn) {
  const win = mainWindow;
  let wasVisible = false;
  if (win && !win.isDestroyed()) {
    wasVisible = win.isVisible();
    if (wasVisible) {
      win.hide();
      // Give WindowServer time to drop the frame before screencapture.
      await sleep(200);
    }
  }
  try {
    return await fn();
  } finally {
    if (wasVisible && win && !win.isDestroyed()) {
      applyOverlayBehavior(win);
      win.show();
      if (!win.isFocused()) win.focus();
    }
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 760,
    minWidth: 400,
    minHeight: 420,
    resizable: true,
    maximizable: true,
    title: "CUA Chat",
    backgroundColor: "#121418",
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 16, y: 16 },
    show: false,
    // NSPanel-style: can join fullscreen Spaces when combined with
    // setVisibleOnAllWorkspaces({ visibleOnFullScreen: true }).
    ...(process.platform === "darwin" ? { type: "panel" } : {}),
    alwaysOnTop: true,
    fullscreenable: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  applyOverlayBehavior(mainWindow);
  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  mainWindow.once("ready-to-show", () => {
    showMainWindow();
  });
  mainWindow.on("show", () => applyOverlayBehavior(mainWindow));
  mainWindow.on("close", (event) => {
    if (!quitting) {
      event.preventDefault();
      hideMainWindow();
    }
  });
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  startControlServer();
  createWindow();
  if (process.platform === "darwin") {
    try {
      const status = systemPreferences.getMediaAccessStatus("microphone");
      if (status !== "granted") {
        await systemPreferences.askForMediaAccess("microphone");
      }
    } catch {
      /* older Electron */
    }
  }
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    if (permission === "media" || permission === "microphone") {
      callback(true);
      return;
    }
    callback(false);
  });
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else showMainWindow();
  });
});

app.on("before-quit", () => {
  quitting = true;
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

ipcMain.handle("bridge:get", async (_e, apiPath) => bridgeRequest("GET", apiPath));
ipcMain.handle("bridge:post", async (_e, apiPath, body) => {
  if (apiPath === "/v1/send" && body && body.look_at_screen) {
    return withChatHiddenForCapture(() => bridgeRequest("POST", apiPath, body));
  }
  return bridgeRequest("POST", apiPath, body);
});
ipcMain.handle("bridge:delete", async (_e, apiPath) =>
  bridgeRequest("DELETE", apiPath)
);
ipcMain.handle("open-external", async (_e, url) => {
  if (typeof url === "string" && url.startsWith("http")) {
    await shell.openExternal(url);
  }
});
ipcMain.handle("focus-window", async () => {
  showMainWindow();
});
