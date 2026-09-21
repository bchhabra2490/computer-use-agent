/* Browser shim for the same chat UI Electron loads via preload.

No-op when window.cuaChat already exists (Electron). Otherwise talks to
chat_bridge on this origin. Pi / CHAT_BROWSER mode needs no token.
*/
(function () {
  if (window.cuaChat) return;

  async function req(method, path, body) {
    const headers = {};
    const opts = { method, headers };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    const raw = await res.text();
    let data = null;
    if (raw) {
      try {
        data = JSON.parse(raw);
      } catch {
        data = { ok: false, error: "bad json", raw };
      }
    }
    if (!res.ok) {
      throw new Error((data && data.error) || "HTTP " + res.status);
    }
    return data;
  }

  window.cuaChat = {
    get: (path) => req("GET", path),
    post: (path, body) => req("POST", path, body ?? {}),
    del: (path) => req("DELETE", path),
    openExternal: (url) => {
      window.open(url, "_blank", "noopener");
    },
  };
})();
