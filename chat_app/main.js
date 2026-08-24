const { app, BrowserWindow, ipcMain, shell } = require("electron");
const fs = require("fs");
const path = require("path");
const http = require("http");

const BRIDGE_PORT = Number(process.env.CHAT_BRIDGE_PORT || 8743);
const RUNTIME_DIR =
  process.env.AGENT_RUNTIME_DIR ||
  path.join(path.dirname(__dirname), ".runtime");
const TOKEN_PATH = path.join(RUNTIME_DIR, "chat.token");

let mainWindow = null;

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
        timeout: 60000,
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

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 760,
    minWidth: 760,
    minHeight: 520,
    title: "CUA Chat",
    backgroundColor: "#121418",
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 16, y: 16 },
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

ipcMain.handle("bridge:get", async (_e, apiPath) => bridgeRequest("GET", apiPath));
ipcMain.handle("bridge:post", async (_e, apiPath, body) =>
  bridgeRequest("POST", apiPath, body)
);
ipcMain.handle("bridge:delete", async (_e, apiPath) =>
  bridgeRequest("DELETE", apiPath)
);
ipcMain.handle("open-external", async (_e, url) => {
  if (typeof url === "string" && url.startsWith("http")) {
    await shell.openExternal(url);
  }
});
ipcMain.handle("focus-window", async () => {
  if (!mainWindow) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
});
