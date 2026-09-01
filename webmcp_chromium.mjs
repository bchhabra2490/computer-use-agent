#!/usr/bin/env node
// Persistent isolated Chromium/CDP bridge for WebMCP discovery and execution.

import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";

const startup = JSON.parse(process.argv[2] || "{}");
const deadlineMs = Math.max(2000, Math.min(Number(startup.timeout_ms || 15000), 60000));
const profile = await mkdtemp(join(tmpdir(), "cua-webmcp-"));
let child, ws, nextId = 1;
const pending = new Map();

function serializableTool(tool, pageOrigin) {
  let schema = tool.inputSchema ?? {};
  if (typeof schema === "string") {
    try { schema = JSON.parse(schema); } catch { schema = {}; }
  }
  return {
    name: String(tool.name || ""), title: String(tool.title || ""),
    description: String(tool.description || ""), inputSchema: schema,
    annotations: {
      readOnlyHint: tool.annotations?.readOnlyHint === true,
      untrustedContentHint: tool.annotations?.untrustedContentHint === true,
    },
    origin: String(tool.origin || pageOrigin || ""),
  };
}

function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP ${method} timed out`)); }, deadlineMs);
    pending.set(id, {
      resolve: value => { clearTimeout(timer); resolve(value); },
      reject: error => { clearTimeout(timer); reject(error); },
    });
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function start() {
  if (!startup.chromium_bin || !startup.url) throw new Error("chromium_bin and url are required");
  child = spawn(startup.chromium_bin, [
    "--headless", "--disable-gpu", "--disable-extensions", "--disable-background-networking",
    "--disable-sync", "--no-first-run", "--no-default-browser-check", "--metrics-recording-only",
    "--enable-features=WebMCP", "--remote-debugging-port=0", `--user-data-dir=${profile}`, startup.url,
  ], { stdio: ["ignore", "ignore", "pipe"] });
  let stderr = "";
  const browserWs = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Chromium CDP endpoint timed out")), deadlineMs);
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", chunk => {
      stderr = (stderr + chunk).slice(-8000);
      const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) { clearTimeout(timer); resolve(match[1]); }
    });
    child.once("exit", code => {
      clearTimeout(timer);
      reject(new Error(`Chromium exited before CDP was ready (${code}): ${stderr.slice(-500)}`));
    });
  });
  const port = new URL(browserWs).port;
  let target;
  const targetUntil = Date.now() + deadlineMs;
  while (Date.now() < targetUntil) {
    const targets = await fetch(`http://127.0.0.1:${port}/json/list`).then(r => r.json());
    target = targets.find(item => item.type === "page" && item.url !== "about:blank") || targets.find(item => item.type === "page");
    if (target?.webSocketDebuggerUrl) break;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  if (!target?.webSocketDebuggerUrl) throw new Error("Chromium page target was not available");
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("CDP WebSocket timed out")), deadlineMs);
    ws.addEventListener("open", () => { clearTimeout(timer); resolve(); }, { once: true });
    ws.addEventListener("error", () => { clearTimeout(timer); reject(new Error("CDP WebSocket failed")); }, { once: true });
  });
  ws.addEventListener("message", event => {
    const message = JSON.parse(String(event.data));
    if (!message.id || !pending.has(message.id)) return;
    const handlers = pending.get(message.id); pending.delete(message.id);
    message.error ? handlers.reject(new Error(message.error.message)) : handlers.resolve(message.result);
  });
  await command("Runtime.enable");
  await command("Page.enable");
}

async function execute(input) {
  const operation = input.operation || "list";
  const waitMs = Math.max(0, Math.min(Number(input.wait_ms || 0), 30000));
  if (waitMs) await new Promise(resolve => setTimeout(resolve, waitMs));
  const expression = operation === "call"
    ? `(async () => {
        const mc = document.modelContext || navigator.modelContext;
        if (!mc || typeof mc.getTools !== 'function' || typeof mc.executeTool !== 'function')
          return {supported:false, url:location.href, title:document.title, origin:location.origin, tools:[]};
        const tools = await mc.getTools();
        const tool = tools.find(t => t.name === ${JSON.stringify(String(input.tool_name || ""))});
        if (!tool) return {error:'WebMCP tool not found'};
        const toolOrigin = String(tool.origin || location.origin);
        const readOnly = tool.annotations?.readOnlyHint === true;
        if (toolOrigin !== ${JSON.stringify(String(input.expected_origin || ""))} || readOnly !== ${JSON.stringify(input.expected_read_only === true)})
          return {error:'WebMCP tool identity changed before execution'};
        const before = location.href;
        const result = await mc.executeTool(tool, ${JSON.stringify(JSON.stringify(input.arguments || {}))});
        return {supported:true, url:location.href, previousUrl:before, title:document.title, origin:location.origin,
          tool:{name:String(tool.name || ''), title:String(tool.title || ''), description:String(tool.description || ''),
          annotations:{readOnlyHint:readOnly, untrustedContentHint:tool.annotations?.untrustedContentHint === true}, origin:toolOrigin},
          result:result ?? null, navigated:before !== location.href};
      })()`
    : `(async () => {
        const mc = document.modelContext || navigator.modelContext;
        if (!mc || typeof mc.getTools !== 'function')
          return {supported:false, url:location.href, title:document.title, origin:location.origin, tools:[]};
        const tools = await mc.getTools();
        return {supported:true, url:location.href, title:document.title, origin:location.origin,
          tools:tools.map(t => (${serializableTool.toString()})(t, location.origin))};
      })()`;
  const evaluated = await command("Runtime.evaluate", {
    expression, awaitPromise: true, returnByValue: true, userGesture: operation === "call",
  });
  if (evaluated.exceptionDetails) throw new Error(evaluated.exceptionDetails.text || "WebMCP evaluation failed");
  const value = evaluated.result?.value;
  if (!value) throw new Error("WebMCP evaluation returned no value");
  if (value.error) throw new Error(value.error);
  return value;
}

async function stop() {
  try { ws?.close(); } catch {}
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  child.kill("SIGTERM");
  await new Promise(resolve => {
    const timer = setTimeout(() => { child.kill("SIGKILL"); resolve(); }, 2000);
    child.once("exit", () => { clearTimeout(timer); resolve(); });
  });
}

async function run() {
  await start();
  if (!startup.session_server) {
    process.stdout.write(JSON.stringify(await execute(startup)));
    return;
  }
  const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const line of lines) {
    if (!line.trim()) continue;
    let request;
    try { request = JSON.parse(line); }
    catch (error) { process.stdout.write(JSON.stringify({ error: `Invalid request: ${error.message}` }) + "\n"); continue; }
    if (request.operation === "close") break;
    try {
      process.stdout.write(JSON.stringify({ request_id: request.request_id, result: await execute(request) }) + "\n");
    } catch (error) {
      process.stdout.write(JSON.stringify({ request_id: request.request_id, error: String(error?.message || error) }) + "\n");
    }
  }
}

try { await run(); }
catch (error) {
  const message = String(error?.message || error);
  process.stdout.write(startup.session_server ? JSON.stringify({ error: message }) + "\n" : JSON.stringify({ error: message }));
  if (!startup.session_server) process.exitCode = 1;
} finally {
  await stop();
  try { await rm(profile, { recursive: true, force: true, maxRetries: 8, retryDelay: 100 }); }
  catch (error) { process.stderr.write(`[webmcp] temporary profile cleanup warning: ${error?.message || error}\n`); }
}
