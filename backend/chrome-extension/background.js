// Канонический адрес — enceladus.site (24.09.2026: DNS починили, домен вернули;
// с 10.09 по 24.09 временно работали через saturn.ac, пока тот был в петле
// редиректов). Старый адрес продолжает отвечать на /api, поэтому расширения
// прошлых версий не ломаются — см. frontend/nginx.conf.
const DEFAULT_SERVER_URL = 'https://enceladus.site';
const REQUEST_TIMEOUT_MS = 25000;

// Один и тот же бэк отвечает на двух доменах, и куки у них РАЗНЫЕ. Канон —
// enceladus.site, но у рекрутёра вполне может остаться живая веб-сессия на
// старом saturn.ac (страницы оттуда теперь редиректят, а куки никуда не
// делись). Для фолбэка по куке перебираем оба, иначе он молча не найдёт
// сессию. JWT общий (один jwt_secret и одна база), поэтому токен с любого из
// доменов валиден на другом — смена адреса никого не разлогинивает.
const SESSION_ORIGINS = [
  'https://enceladus.site',
  'https://enceladus-7oylzk.saturn.ac',
];

// ---- Авторизация: единственный владелец токенов ----
// Токены живут в chrome.storage.local, и обновляет их ТОЛЬКО service worker.
// Раньше рефреш делал popup, а его JS-контекст Chrome убивает в момент закрытия
// попапа: ответ с новой парой токенов терялся, тогда как сервер уже сжёг старый
// refresh ротацией (auth.py rotate_refresh_token) — следующее открытие давало
// «Сессия истекла» на живой сессии. Worker переживает закрытие попапа, поэтому
// ротация здесь атомарна: получили новую пару — сразу записали в storage.

// Та же нормализация, что в popup.js: в chrome.storage у старых пользователей
// мог остаться прежний адрес (railway и т.п.). Без этого будильник продления
// сессии стучался бы в мёртвый домен у того, кто попап не открывает.
function normalizeServerUrl(raw) {
  const url = (raw || '').replace(/\/$/, '');
  if (!url) return DEFAULT_SERVER_URL;
  if (/localhost|127\.0\.0\.1/.test(url)) return url;
  // Прод-сервер у всех один, поэтому любой сохранённый прод-адрес (в т.ч.
  // старый saturn.ac или совсем древний railway) приводим к канону: иначе
  // будильник продления сессии годами стучался бы в прежний домен.
  return DEFAULT_SERVER_URL;
}

async function readAuth() {
  const s = await chrome.storage.local.get(['serverUrl', 'authToken', 'refreshToken']);
  return {
    serverUrl: normalizeServerUrl(s.serverUrl),
    authToken: s.authToken || '',
    refreshToken: s.refreshToken || '',
  };
}

// refreshToken не трогаем, если он не передан явно.
async function writeAuth(authToken, refreshToken) {
  const patch = { authToken };
  if (refreshToken !== undefined) patch.refreshToken = refreshToken;
  await chrome.storage.local.set(patch);
}

// Читаем куку веб-сессии напрямую из cookie store браузера.
// fetch(credentials:'include') для этого не годится: сессионные куки выставлены
// с SameSite=Lax (auth.py:154,165), а chrome-extension://<id> — кросс-сайтовый
// origin, поэтому Lax-куки к такому запросу не прикрепляются никогда. Через
// chrome.cookies они читаются, включая httpOnly.
async function readSessionCookie(serverUrl, name, path) {
  if (!chrome.cookies) return '';
  try {
    const c = await chrome.cookies.get({ url: serverUrl + (path || '/'), name });
    return (c && c.value) || '';
  } catch (_) {
    return '';
  }
}

// 'refreshed' — новая пара получена; 'auth_failed' — сервер сказал, что токен
// мёртв; 'transient' — сеть/таймаут, сессия скорее всего жива.
async function postRefresh(serverUrl, token) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const r = await fetch(serverUrl + '/api/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: token }),
      signal: controller.signal,
    });
    if (r.ok) {
      const data = await r.json().catch(() => null);
      if (data && data.access_token) return { outcome: 'refreshed', data };
      return { outcome: 'auth_failed' };
    }
    if (r.status === 401 || r.status === 403) return { outcome: 'auth_failed' };
    return { outcome: 'transient' };
  } catch (_) {
    return { outcome: 'transient' };
  } finally {
    clearTimeout(timer);
  }
}

let _refreshing = null;

// Пытается добыть рабочий access-токен. Single-flight: параллельные 401 не
// должны рефрешить наперегонки и сжигать друг другу ротированный токен.
async function ensureFreshToken() {
  if (_refreshing) return _refreshing;
  _refreshing = (async () => {
    const auth = await readAuth();

    if (auth.refreshToken) {
      const r = await postRefresh(auth.serverUrl, auth.refreshToken);
      if (r.outcome === 'refreshed') {
        await writeAuth(r.data.access_token, r.data.refresh_token || auth.refreshToken);
        return 'refreshed';
      }
      if (r.outcome === 'transient') return 'transient';
    }

    // Фолбэк — живая веб-сессия в браузере. Берём ТОЛЬКО access_token: он
    // read-only и ничего не ломает. Refresh-куку веб-клиента трогать нельзя —
    // ротация сожгла бы её и разлогинила пользователя на самом сайте.
    // Текущий сервер проверяем первым, затем остальные известные домены.
    const origins = [auth.serverUrl, ...SESSION_ORIGINS.filter((o) => o !== auth.serverUrl)];
    for (const origin of origins) {
      const cookieAccess = await readSessionCookie(origin, 'access_token', '/');
      if (cookieAccess) {
        // Свой refresh-токен сюда доводит только отказ сервера — чистим, чтобы
        // не дёргать его впустую на каждом следующем обновлении.
        await writeAuth(cookieAccess, '');
        return 'refreshed';
      }
    }

    return 'auth_failed';
  })();
  try {
    return await _refreshing;
  } finally {
    _refreshing = null;
  }
}

function apiFetch(url, method, body, token) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  return fetch(url, {
    method: method || 'GET',
    headers,
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
    signal: controller.signal,
  })
    .then((r) => {
      clearTimeout(timeoutId);
      if (!r.ok) {
        return r.text().then((text) => {
          let detail = `HTTP ${r.status}`;
          try {
            const json = JSON.parse(text);
            detail = json.detail || detail;
          } catch (_) {}
          return { success: false, error: detail, status: r.status };
        });
      }
      const contentType = r.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        return r.json().then((data) => ({ success: true, data }));
      }
      return r.text().then((text) => ({
        success: false,
        error: 'Non-JSON response: ' + text.substring(0, 200),
      }));
    })
    .catch((err) => {
      clearTimeout(timeoutId);
      const msg = err && err.name === 'AbortError'
        ? 'Сервер не ответил за 25 сек. Проверь сеть и попробуй ещё раз.'
        : (err && err.message ? err.message : 'Сетевая ошибка');
      // transient: сеть/таймаут — это НЕ повод разлогинивать.
      return { success: false, error: msg };
    });
}

// Refresh-токен живёт 7 дней и продлевается только при обращении к серверу.
// Тот, кто открывает расширение реже раза в неделю, раньше каждый раз попадал
// на экран входа. Будим воркер раз в 6 часов и молча продлеваем сессию, чтобы
// окно всегда откатывалось вперёд.
const KEEPALIVE_ALARM = 'auth-keepalive';

// Создаём и при пробуждении воркера: onInstalled/onStartup не сработают у тех,
// у кого расширение уже стоит, а браузер не перезапускался.
chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 360 });
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 360 });
});
chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 360 });
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== KEEPALIVE_ALARM) return;
  const auth = await readAuth();
  // Без своего refresh-токена продлевать нечего: не трогаем куку веб-сессии и
  // не шлём лишних запросов.
  if (auth.refreshToken) await ensureFreshToken();
});

// Handle messages from content scripts and popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'PARSE_RESULT') {
    // Store parsed data for popup to read; включаем URL-тег и timestamp,
    // чтобы popup мог отличить свежий парс от устаревшего после нав-ии.
    const tagged = Object.assign({}, message.data, {
      _captured_url: (sender && sender.tab && sender.tab.url) || message.data.source_url || '',
      _captured_at: Date.now(),
    });
    chrome.storage.local.set({ parsedData: tagged });
  }
  if (message.type === 'GET_PARSED_DATA') {
    chrome.storage.local.get('parsedData', (result) => {
      sendResponse(result.parsedData || null);
    });
    return true; // async response
  }
  if (message.type === 'CLEAR_PARSED_DATA') {
    chrome.storage.local.remove('parsedData', () => sendResponse({ success: true }));
    return true;
  }
  if (message.type === 'RE_PARSE_ACTIVE_TAB') {
    // Просим content-скрипт активной вкладки перепарсить DOM повторно.
    // Если он не зарегистрирован (страница не подходит под matches в манифесте)
    // — инжектим программно через chrome.scripting. Это покрывает кейсы вроде
    // hh.ru/employer/vacancy?...resumeId=... где manifest matches не сработал.
    chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
      const tab = tabs[0];
      if (!tab || !tab.id) { sendResponse({ success: false, error: 'no active tab' }); return; }

      const sendRePerse = () => new Promise((resolve) => {
        chrome.tabs.sendMessage(tab.id, { type: 'RE_PARSE' }, (resp) => {
          if (chrome.runtime.lastError) {
            resolve({ ok: false, err: chrome.runtime.lastError.message });
          } else {
            resolve({ ok: true, data: resp });
          }
        });
      });

      // Первая попытка — может скрипт уже зарегистрирован
      let result = await sendRePerse();

      if (!result.ok && result.err && /Receiving end does not exist/i.test(result.err)) {
        // Контент-скрипт не на странице — определяем какой инжектить по URL.
        const url = tab.url || '';
        let scriptFile = null;
        if (url.includes('hh.ru')) scriptFile = 'content/hh.js';
        else if (url.includes('career.habr.com')) scriptFile = 'content/habr.js';
        else if (url.includes('linkedin.com')) scriptFile = 'content/linkedin.js';

        if (!scriptFile || !chrome.scripting) {
          sendResponse({ success: false, error: result.err });
          return;
        }

        try {
          await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            // common.js первым — парсеры зависят от window.__ENC__.
            files: ['content/common.js', scriptFile],
          });
          // После инжекта content-скрипт сам вызовет PARSE_RESULT, либо
          // RE_PARSE listener зарегистрируется и ответит на повторный запрос.
          // Даём ему 200мс чтобы листенер был готов.
          await new Promise((r) => setTimeout(r, 200));
          result = await sendRePerse();
        } catch (injectErr) {
          sendResponse({
            success: false,
            error: 'Не удалось внедрить парсер: ' + (injectErr && injectErr.message),
          });
          return;
        }
      }

      if (result.ok) {
        sendResponse({ success: true, data: result.data });
      } else {
        sendResponse({ success: false, error: result.err || 'unknown' });
      }
    });
    return true;
  }
  // Восстановить авторизацию до открытия попапа: обновить свой токен либо
  // подхватить живую веб-сессию из куки. Возвращает { authorized }.
  if (message.type === 'ENSURE_AUTH') {
    (async () => {
      const auth = await readAuth();
      if (auth.authToken) { sendResponse({ authorized: true }); return; }
      const outcome = await ensureFreshToken();
      // 'transient' — сеть подвела; не считаем сессию мёртвой, но и токена нет.
      sendResponse({ authorized: outcome === 'refreshed', outcome });
    })();
    return true;
  }

  if (message.type === 'API_REQUEST') {
    // Запрос идёт отсюда: у service worker нет CORS-ограничений попапа, и он
    // переживает закрытие попапа, поэтому обновление токена не теряется.
    (async () => {
      const { url, method, body } = message;
      let auth = await readAuth();
      let resp = await apiFetch(url, method, body, auth.authToken);

      if (resp.status !== 401) { sendResponse(resp); return; }

      const outcome = await ensureFreshToken();
      if (outcome === 'refreshed') {
        auth = await readAuth();
        resp = await apiFetch(url, method, body, auth.authToken);
        // Свежий токен, и всё равно 401 → сессия действительно мертва.
        if (resp.status === 401) {
          await chrome.storage.local.remove(['authToken', 'refreshToken']);
          resp.authExpired = true;
        }
      } else if (outcome === 'auth_failed') {
        await chrome.storage.local.remove(['authToken', 'refreshToken']);
        resp.authExpired = true;
      }
      // outcome === 'transient': рефреш сорвался на сети/таймауте/сне воркера.
      // Сессия скорее всего жива — НЕ разлогиниваем, попап просто покажет
      // ошибку запроса, а следующий вызов повторит попытку.
      sendResponse(resp);
    })();
    return true;
  }
});
