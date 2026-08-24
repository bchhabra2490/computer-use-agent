const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("cuaChat", {
  get: (path) => ipcRenderer.invoke("bridge:get", path),
  post: (path, body) => ipcRenderer.invoke("bridge:post", path, body),
  del: (path) => ipcRenderer.invoke("bridge:delete", path),
  openExternal: (url) => ipcRenderer.invoke("open-external", url),
});
