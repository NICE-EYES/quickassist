import { collect, sendContext } from "./common.js";

const status = document.getElementById("status");
const buttons = [...document.querySelectorAll("button")];

function show(text, cls) { status.textContent = text; status.className = cls || ""; }

async function run(kind) {
  buttons.forEach(b => (b.disabled = true));
  show("Отправляю…");
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) throw new Error("Нет активной вкладки.");
    await sendContext(await collect(tab, kind));
    show("Отправлено в помощник.", "ok");
    setTimeout(() => window.close(), 700);
  } catch (e) {
    show(e.message || String(e), "err");
  } finally {
    buttons.forEach(b => (b.disabled = false));
  }
}

document.getElementById("sel").addEventListener("click", () => run("selection"));
document.getElementById("tab").addEventListener("click", () => run("tab"));
document.getElementById("page").addEventListener("click", () => run("page"));
document.getElementById("opts").addEventListener("click", (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); });
