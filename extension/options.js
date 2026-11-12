import { DEFAULT_PORT, getConfig, ping } from "./common.js";

const port = document.getElementById("port");
const token = document.getElementById("token");
const status = document.getElementById("status");
document.getElementById("extid").textContent = chrome.runtime.id;

getConfig().then(cfg => { port.value = cfg.port; token.value = cfg.token; });

document.getElementById("save").addEventListener("click", async () => {
  const p = Number(port.value) || DEFAULT_PORT;
  if (p < 1024 || p > 65535) { status.textContent = "Порт должен быть от 1024 до 65535."; status.className = "err"; return; }
  await chrome.storage.local.set({ port: p, token: token.value.trim() });
  status.textContent = "Проверяю…"; status.className = "";
  try {
    await ping();
    status.textContent = "Подключение работает."; status.className = "ok";
  } catch (e) {
    status.textContent = e.message || String(e); status.className = "err";
  }
});
