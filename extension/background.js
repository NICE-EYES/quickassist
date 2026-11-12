import { collect, sendContext } from "./common.js";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "qa-selection", title: "Отправить выделение в помощник", contexts: ["selection"] });
    chrome.contextMenus.create({ id: "qa-tab", title: "Отправить адрес страницы в помощник", contexts: ["page"] });
    chrome.contextMenus.create({ id: "qa-page", title: "Использовать текст страницы в помощнике", contexts: ["page"] });
  });
  chrome.storage.local.get("token").then(({ token }) => { if (!token) chrome.runtime.openOptionsPage(); });
});

// Обратная связь без дополнительных разрешений: значок на кнопке расширения.
async function feedback(ok, message) {
  await chrome.action.setBadgeBackgroundColor({ color: ok ? "#2e7d32" : "#c62828" });
  await chrome.action.setBadgeText({ text: ok ? "✓" : "!" });
  await chrome.action.setTitle({ title: ok ? "Быстрый помощник" : `Ошибка: ${message}` });
  setTimeout(() => {
    chrome.action.setBadgeText({ text: "" });
    if (ok) chrome.action.setTitle({ title: "Быстрый помощник" });
  }, ok ? 2500 : 8000);
}

async function handle(tab, kind, fallbackSelection = "") {
  try {
    const ctx = await collect(tab, kind, fallbackSelection);
    await sendContext(ctx);
    await feedback(true);
  } catch (e) {
    await feedback(false, e.message || String(e));
  }
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab) return;
  const kind = { "qa-selection": "selection", "qa-tab": "tab", "qa-page": "page" }[info.menuItemId];
  if (kind) handle(tab, kind, info.selectionText || "");
});

chrome.commands.onCommand.addListener((command, tab) => {
  if (command === "send-selection" && tab) handle(tab, "selection");
});
