// Общая логика: настройки сопряжения, сбор данных со вкладки, отправка в приложение.
// Данные отправляются ТОЛЬКО на 127.0.0.1 и только по явному действию пользователя.

export const DEFAULT_PORT = 48731;
const MAX_TEXT = 200000;

export async function getConfig() {
  const { port = DEFAULT_PORT, token = "" } = await chrome.storage.local.get(["port", "token"]);
  return { port: Number(port) || DEFAULT_PORT, token: String(token || "") };
}

export class BridgeError extends Error {}
export class RestrictedPageError extends Error {}

async function call(path, payload) {
  const { port, token } = await getConfig();
  if (!token) throw new BridgeError("Не задан токен. Откройте настройки расширения и вставьте токен из программы.");
  let resp;
  try {
    resp = await fetch(`http://127.0.0.1:${port}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
      body: JSON.stringify(payload ?? {}),
      signal: AbortSignal.timeout(4000),
      credentials: "omit",
      cache: "no-store",
    });
  } catch (e) {
    throw new BridgeError("Программа «Быстрый помощник» не отвечает. Запустите её и проверьте порт.");
  }
  if (resp.status === 401) throw new BridgeError("Токен не подходит. Скопируйте актуальный токен из настроек программы.");
  if (resp.status === 403) throw new BridgeError("Программа отклонила расширение (проверьте «Разрешённый ID расширения»).");
  if (!resp.ok) throw new BridgeError(`Программа вернула ошибку ${resp.status}.`);
  return resp.json();
}

export const ping = () => call("/v1/ping", {});

export function sendContext(ctx) {
  let text = ctx.text || "";
  let truncated = false;
  if (text.length > MAX_TEXT) { text = text.slice(0, MAX_TEXT); truncated = true; }
  return call("/v1/context", {
    version: 1, kind: ctx.kind, url: (ctx.url || "").slice(0, 4096),
    title: (ctx.title || "").slice(0, 1000), text, truncated,
  });
}

// Функции ниже выполняются ВНУТРИ страницы через chrome.scripting.executeScript.
function pageSelection() {
  const el = document.activeElement;
  if (el && (el.tagName === "TEXTAREA" || (el.tagName === "INPUT" && /^(text|search|url|email)?$/i.test(el.type)))) {
    try {
      const v = el.value.substring(el.selectionStart, el.selectionEnd);
      if (v) return v;
    } catch (_) { /* у некоторых input нет selectionStart */ }
  }
  return String(window.getSelection ? window.getSelection() : "");
}

function pageText() {
  return document.body ? document.body.innerText : "";
}

async function runInTab(tabId, func) {
  try {
    const [res] = await chrome.scripting.executeScript({ target: { tabId }, func });
    return res ? res.result : "";
  } catch (e) {
    throw new RestrictedPageError(
      "На этой странице расширения не работают (служебные страницы, магазин расширений, PDF и т.п.). " +
      "Выделите текст, нажмите горячую клавишу помощника — он скопирует выделение сам.");
  }
}

export async function collect(tab, kind, fallbackSelection = "") {
  const base = { kind, url: tab.url || "", title: tab.title || "" };
  if (kind === "tab") return base;
  if (kind === "selection") {
    let text = "";
    try { text = await runInTab(tab.id, pageSelection); }
    catch (e) { if (!fallbackSelection) throw e; }
    text = (text || "").trim() ? text : fallbackSelection;
    if (!text.trim()) throw new BridgeError("Нет выделенного текста.");
    return { ...base, text };
  }
  const text = await runInTab(tab.id, pageText);
  if (!(text || "").trim()) throw new BridgeError("Не удалось получить текст страницы.");
  return { ...base, text };
}
