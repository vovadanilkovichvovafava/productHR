// State
let serverUrl = '';
let authToken = '';
let refreshToken = '';
let parsedData = null;
let vacancies = [];

// Elements
const loginForm = document.getElementById('loginForm');
const parseForm = document.getElementById('parseForm');
const noData = document.getElementById('noData');
const resultView = document.getElementById('resultView');

// Password toggle
document.getElementById('togglePassword')?.addEventListener('click', () => {
  const input = document.getElementById('loginPassword');
  const btn = document.getElementById('togglePassword');
  if (input.type === 'password') {
    input.type = 'text';
    btn.textContent = '🙈';
  } else {
    input.type = 'password';
    btn.textContent = '👁';
  }
});

// Init
document.addEventListener('DOMContentLoaded', async () => {
  // Показать версию билда в футере — видно, что встал свежий extension.
  try {
    const verEl = document.getElementById('extVersion');
    if (verEl && chrome.runtime?.getManifest) verEl.textContent = 'v' + chrome.runtime.getManifest().version;
  } catch (_) {}
  // Load saved settings
  const stored = await chrome.storage.local.get(['serverUrl', 'authToken', 'refreshToken', 'userName']);
  showWho(stored.userName);
  // Актуальный прод-сервер один и тот же для всех. У старых пользователей в
  // chrome.storage мог остаться прежний адрес и «залипал» в поле входа —
  // поэтому всегда подставляем канонический сервер, кроме локальной разработки.
  // Канонический домен — enceladus.site (тот же бэк, что старый saturn.ac-сабдомен;
  // старый оставлен в host_permissions как фолбэк для уже залогиненных).
  // 24.09.2026: DNS починили, вернули канон (с 10.09 временно был saturn.ac).
  const DEFAULT_SERVER_URL = 'https://enceladus.site';
  const storedServer = stored.serverUrl || '';
  const isLocalDev = /localhost|127\.0\.0\.1/.test(storedServer);
  serverUrl = isLocalDev ? storedServer : DEFAULT_SERVER_URL;
  if (serverUrl !== storedServer) {
    await chrome.storage.local.set({ serverUrl });
  }
  authToken = stored.authToken || '';
  refreshToken = stored.refreshToken || '';

  document.getElementById('serverUrl').value = serverUrl;

  // Восстановление сессии живёт в background.js: он обновит свой токен либо
  // подхватит веб-сессию через chrome.cookies. Прежний вариант — fetch с
  // credentials:'include' прямо отсюда — не работал никогда: куки сессии стоят
  // с SameSite=Lax и на кросс-сайтовый запрос из chrome-extension:// не уходят.
  if (!authToken) {
    const ensured = await new Promise((r) =>
      chrome.runtime.sendMessage({ type: 'ENSURE_AUTH' }, (resp) => r(resp || {}))
    );
    if (ensured.authorized) {
      const fresh = await chrome.storage.local.get(['authToken', 'refreshToken']);
      authToken = fresh.authToken || '';
      refreshToken = fresh.refreshToken || '';
    }
  }

  if (!authToken) {
    showView('login');
    return;
  }

  checkExtensionUpdate();

  // Главное правило: кэш не доверяем. На каждом открытии попапа просим
  // content-скрипт перепарсить активную вкладку. Кэш используем только как
  // запасной вариант, если content-скрипт не отвечает (например, страница
  // ещё грузится или сайт не из списка).
  loadFromActiveTab();
});

function showWho(name) {
  const el = document.getElementById('whoAmI');
  if (el) el.textContent = name || '';
}

// Сравнение версий «1.9.2» > «1.9.1» по числам.
function isNewerVersion(remote, local) {
  const a = String(remote || '').split('.').map(Number);
  const b = String(local || '').split('.').map(Number);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) > (b[i] || 0);
  }
  return false;
}

// Расширение ставят из zip, само оно не обновляется — без этой плашки
// рекрутёры сидели на той версии, что когда-то скачали, и исправления в попапе
// до них не доходили (22.10.2026). Сервер отдаёт версию из своего manifest.json.
async function checkExtensionUpdate() {
  const note = document.getElementById('updateNote');
  if (!note || !chrome.runtime?.getManifest) return;
  const resp = await rawApiRequest('GET', '/api/extension/version', null, 10000);
  const remote = resp && resp.success && resp.data && resp.data.version;
  if (!remote || !isNewerVersion(remote, chrome.runtime.getManifest().version)) return;
  note.innerHTML = `<b>Вышла версия ${esc(remote)}</b> — скачайте и замените расширение · <u>открыть</u>`;
  note.style.display = 'block';
  note.onclick = () => chrome.tabs.create({ url: serverUrl + (resp.data.page || '/extension') });
}

function detectTabState(tabUrl) {
  // 'wrong-site' | 'wrong-page' | 'resume-page'
  // rabota.by = HeadHunter Belarus, тот же DOM (data-qa атрибуты) и тот же
  // парсер content/hh.js — обрабатываем как hh.
  const isHh = tabUrl.includes('hh.ru') || tabUrl.includes('rabota.by');
  const isHabr = tabUrl.includes('career.habr.com');
  const isLinkedIn = tabUrl.includes('linkedin.com');
  if (!isHh && !isHabr && !isLinkedIn) return 'wrong-site';

  // Эвристика «это похоже на страницу конкретного резюме»:
  // hh.ru — /resume/ ИЛИ есть resumeId в query
  // habr — /<username>/ или /<username>/profile
  // linkedin — /in/<username>
  if (isHh) {
    if (/\/resume\//.test(tabUrl) || /[?&]resumeId=/.test(tabUrl)) return 'resume-page';
    return 'wrong-page';
  }
  if (isHabr) {
    if (/career\.habr\.com\/[^?#/]+/.test(tabUrl)) return 'resume-page';
    return 'wrong-page';
  }
  if (isLinkedIn) {
    if (/\/in\//.test(tabUrl)) return 'resume-page';
    return 'wrong-page';
  }
  return 'wrong-site';
}

function showNodata(state, tabUrl) {
  const wrong = document.getElementById('nodataWrongSite');
  const page = document.getElementById('nodataWrongPage');
  const noParse = document.getElementById('nodataNoParse');
  const example = document.getElementById('nodataExample');
  const urlEl = document.getElementById('nodataCurrentUrl');
  if (wrong) wrong.style.display = 'none';
  if (page) page.style.display = 'none';
  if (noParse) noParse.style.display = 'none';

  if (state === 'wrong-site' && wrong) wrong.style.display = 'block';
  if (state === 'wrong-page' && page) {
    page.style.display = 'block';
    // Подстраиваем пример URL под сайт
    if (example) {
      let host = 'hh.ru'; let path = '/resume/&lt;id&gt;';
      if (tabUrl.includes('career.habr.com')) { host = 'career.habr.com'; path = '/&lt;username&gt;'; }
      else if (tabUrl.includes('linkedin.com')) { host = 'linkedin.com'; path = '/in/&lt;username&gt;'; }
      example.innerHTML = `<b>Пример URL для ${host}:</b><br>` +
        `<span style="font-family:ui-monospace,monospace;">${host}${path}</span>`;
    }
  }
  if (state === 'no-parse' && noParse) noParse.style.display = 'block';

  if (urlEl) urlEl.textContent = tabUrl || 'нет вкладки';
  showView('nodata');
}

async function loadFromActiveTab() {
  const tabs = await new Promise((r) => chrome.tabs.query({ active: true, currentWindow: true }, r));
  const tabUrl = (tabs[0] && tabs[0].url) || '';
  const tabState = detectTabState(tabUrl);

  // Если вкладка не на сайте резюме — сразу контекстный nodata, без RE_PARSE.
  if (tabState === 'wrong-site') {
    // Кэш всё-таки попробуем — вдруг есть свежий парс с предыдущей вкладки
    chrome.runtime.sendMessage({ type: 'GET_PARSED_DATA' }, (data) => {
      if (data && data.full_name) {
        parsedData = data;
        showParsedData();
        loadVacancies();
        showView('parse');
      } else {
        showNodata('wrong-site', tabUrl);
      }
    });
    return;
  }

  if (tabState === 'wrong-page') {
    // На правильном сайте, но не на карточке резюме — конкретный месседж.
    showNodata('wrong-page', tabUrl);
    return;
  }

  // На резюме-странице. ВАЖНО про тайминг: hh/habr парсят DOM синхронно (быстро),
  // а LinkedIn догружает ОПЫТ работы в скрытый iframe — это 4.5–13 секунд. Раньше
  // popup опрашивал storage всего 200/400/800мс и сдавался → опыт LinkedIn не
  // успевал доехать, кандидат приезжал «только имя». Новая схема:
  //   1) мгновенно показываем кэш быстрого прохода (если он от ЭТОЙ же вкладки);
  //   2) дожидаемся ПОЛНОГО парса через прямой ответ RE_PARSE (он резолвится
  //      только когда content-скрипт закончил parseFull, включая iframe опыта);
  //   3) перерисовываем карточку финальными данными.

  const tryFetch = (delay) => new Promise((res) => {
    setTimeout(() => {
      chrome.runtime.sendMessage({ type: 'GET_PARSED_DATA' }, (data) => res(data || null));
    }, delay);
  });

  // 1) Мгновенный показ кэша быстрого прохода — чтобы рекрут сразу видел имя,
  //    пока тянется полный парс. Показываем ТОЛЬКО если кэш с этой же страницы
  //    (сверяем path), иначе рискуем показать чужого кандидата.
  const cached = await tryFetch(0);
  const cacheMatches = cached && cached.full_name &&
    sameResumePath(cached._captured_url || cached.source_url, tabUrl);
  let shownFromCache = false;
  if (cacheMatches) {
    parsedData = cached;
    showParsedData();
    loadVacancies();
    showView('parse');
    setParsingIndicator(true);
    shownFromCache = true;
  }

  // Если кэша от этой вкладки не было — показываем лёгкое состояние загрузки,
  // чтобы попап не висел пустым до 13с пока LinkedIn тянет опыт в iframe.
  if (!shownFromCache) {
    const nameEl = document.getElementById('parsedName');
    if (nameEl) nameEl.textContent = 'Читаем профиль…';
    const detailsEl = document.getElementById('parsedDetails');
    if (detailsEl) detailsEl.innerHTML = '';
    showView('parse');
    setParsingIndicator(true);
  }

  // 2) Полный перепарс. Ответ RE_PARSE содержит ФИНАЛЬНЫЕ данные (с опытом) —
  //    ждём его честно (content-скрипт держит порт открытым до конца parseFull).
  const reparseResp = await new Promise((r) =>
    chrome.runtime.sendMessage({ type: 'RE_PARSE_ACTIVE_TAB' }, r)
  );

  let data = null;
  // reparseResp.data = ответ content-скрипта на RE_PARSE = { success, data: <parsed> }.
  if (reparseResp && reparseResp.success && reparseResp.data &&
      reparseResp.data.data && reparseResp.data.data.full_name) {
    data = reparseResp.data.data;
  }
  // Фолбэк: программный инжект отдаёт результат через storage (PARSE_RESULT),
  // а не в ответе. Даём ему больше времени, чем раньше (LinkedIn медленный).
  if (!data) {
    for (const delay of [200, 500, 1000, 2000, 4000]) {
      const d = await tryFetch(delay);
      if (d && d.full_name) { data = d; break; }
    }
  }

  setParsingIndicator(false);

  if (data && data.full_name) {
    parsedData = data;
    showParsedData();
    if (!shownFromCache) loadVacancies();
    showView('parse');
    return;
  }

  // Полный парс ничего не дал. Если успели показать кэш — оставляем его
  // (лучше частичные данные, чем nodata).
  if (shownFromCache) return;

  // На правильной странице, но парсер ничего не нашёл (DOM не такой,
  // контакты под подпиской, и т.п.) — третий вариант nodata.
  if (reparseResp && reparseResp.success === false) {
    console.warn('[HR-Bot] RE_PARSE failed:', reparseResp.error);
  }
  showNodata('no-parse', tabUrl);
}

// Сверяем, что закэшированный парс относится к ТЕКУЩЕЙ вкладке: совпадает путь
// (query игнорируем — на hh он волатильный: ?t=…&vacancyId=…). Поддомен hh
// (saratov.hh.ru) сравниваем по базовому домену.
function sameResumePath(cachedUrl, tabUrl) {
  if (!cachedUrl || !tabUrl) return false;
  try {
    const a = new URL(cachedUrl), b = new URL(tabUrl);
    const base = (h) => h.replace(/^www\./, '').split('.').slice(-2).join('.');
    if (base(a.hostname) !== base(b.hostname)) return false;
    return a.pathname === b.pathname;
  } catch (_) {
    return false;
  }
}

// Индикатор «догружаем данные…» в карточке парса (виден пока тянется полный
// парс LinkedIn после мгновенного показа кэша).
function setParsingIndicator(on) {
  const el = document.getElementById('parsingIndicator');
  if (el) el.style.display = on ? 'block' : 'none';
}


function showView(view) {
  loginForm.classList.remove('active');
  parseForm.classList.remove('active');
  noData.style.display = 'none';
  resultView.classList.remove('active');

  if (view === 'login') loginForm.classList.add('active');
  if (view === 'parse') parseForm.classList.add('active');
  if (view === 'nodata') noData.style.display = 'block';
  if (view === 'result') resultView.classList.add('active');
}

// Подписи этапов присылает сервер (services/hr_stages.py): `status`/`stage` —
// уже подпись, `status_key`/`stage_key` — ключ. Свой словарь здесь только для
// цвета чипа. Прежний словарь попапа разошёлся с сайтом — «Интервью с HR»
// показывалось как «Практика» (22.10.2026).
const STAGE_TONE = {
  new: 'st-new', applied: 'st-new',
  hired: 'st-done', transferred: 'st-done', probation: 'st-done',
  rejected: 'st-off', withdrawn: 'st-off', dismissed: 'st-off', quit: 'st-off',
  reserve: 'st-muted', other: 'st-muted',
};

function formatDateShort(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('ru', { day: 'numeric', month: 'short', year: '2-digit' });
}

// Всё, что пришло со страницы резюме или с сервера, вставляем через esc():
// имя или название воронки с «<» иначе становилось разметкой попапа.
function esc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function initialsOf(name) {
  const parts = String(name || '').trim().split(/\s+/).filter((p) => /^[A-Za-zА-Яа-яЁё]/.test(p));
  return parts.slice(0, 2).map((p) => p[0].toUpperCase()).join('') || '?';
}

function stageChip(label, key) {
  return `<span class="stage-chip ${STAGE_TONE[key] || ''}">${esc(label || key)}</span>`;
}

function showParsedData() {
  document.getElementById('parsedName').textContent = parsedData.full_name || '\u2014';

  // If name is a placeholder (hh.ru closed contacts), prompt user to type it
  const nameField = document.getElementById('nameField');
  if (nameField) {
    if (parsedData.name_is_placeholder) {
      nameField.style.display = 'block';
      const nameInput = document.getElementById('manualName');
      if (nameInput && !nameInput.value) {
        nameInput.placeholder = 'Например: Иванов Иван';
        nameInput.focus();
      }
    } else {
      nameField.style.display = 'none';
    }
  }

  // Аватар: фото со страницы, иначе инициалы.
  const photoContainer = document.getElementById('parsedPhoto');
  if (photoContainer) {
    photoContainer.textContent = initialsOf(parsedData.full_name);
    if (parsedData.photo_url) {
      const img = document.createElement('img');
      img.alt = '';
      img.src = parsedData.photo_url;
      img.onerror = () => { photoContainer.textContent = initialsOf(parsedData.full_name); };
      photoContainer.textContent = '';
      photoContainer.appendChild(img);
    }
  }

  // Под именем — должность · город · возраст; ниже чипы и детали строками.
  const sub = [parsedData.position, parsedData.city, parsedData.age].filter(Boolean);
  document.getElementById('parsedSubline').textContent = sub.join(' · ');

  const chips = [];
  if (parsedData.total_experience) chips.push('Опыт ' + parsedData.total_experience);
  if (parsedData.salary) chips.push(parsedData.salary);
  if (parsedData.skills && parsedData.skills.length) chips.push(`Навыков: ${parsedData.skills.length}`);
  if (parsedData.languages && parsedData.languages.length) chips.push(`Языков: ${parsedData.languages.length}`);
  document.getElementById('parsedChips').innerHTML =
    chips.map((c) => `<span class="chip">${esc(c)}</span>`).join('') +
    (parsedData.source ? `<span class="chip src">${esc(parsedData.source)}</span>` : '');

  const details = [];
  const contacts = [parsedData.email, parsedData.phone, parsedData.telegram].filter(Boolean);
  if (contacts.length) details.push(contacts.join(' · '));
  if (parsedData.experience_summary) {
    details.push('Опыт: ' + parsedData.experience_summary.split('\n').slice(0, 2).join('; '));
  } else if (parsedData.company) {
    details.push('Компания: ' + parsedData.company);
  }
  if (parsedData.education && parsedData.education.length > 0) {
    details.push('Образование: ' + parsedData.education.slice(0, 2).join('; '));
  }
  if (parsedData.certifications && parsedData.certifications.length > 0) {
    details.push('Лицензии: ' + parsedData.certifications.slice(0, 3).join('; ') +
      (parsedData.certifications.length > 3 ? ` (+${parsedData.certifications.length - 3})` : ''));
  }
  document.getElementById('parsedDetails').innerHTML = details.map((d) => `<div>${esc(d)}</div>`).join('');
  document.getElementById('parsedSource').textContent = parsedData.source;

  // Show manual fields if соответствующий контакт не распознан автоматически
  const setFieldVisible = (id, show) => {
    const el = document.getElementById(id);
    if (el) el.style.display = show ? 'block' : 'none';
  };
  setFieldVisible('emailField', !parsedData.email);
  setFieldVisible('phoneField', !parsedData.phone);
  setFieldVisible('telegramField', !parsedData.telegram);

  // Show contacts-hidden note if no contacts at all
  const contactsNote = document.getElementById('contactsNote');
  if (contactsNote && !parsedData.email && !parsedData.phone && !parsedData.telegram) {
    contactsNote.style.display = 'block';
  } else if (contactsNote) {
    contactsNote.style.display = 'none';
  }

  // Auto-check duplicates
  checkDuplicatesOnLoad();
}

// «Был отказ 28 авг · «Трафик»» + кто и с каким текстом. Поля — как в
// services/prior_rejection.py. Пусто → ''.
function renderPriorRejection(pr, base) {
  if (!pr) return '';
  const d = pr.date ? new Date(/Z|[+-]\d\d:?\d\d$/.test(pr.date) ? pr.date : pr.date + 'Z') : null;
  const when = d && !isNaN(d) ? d.toLocaleDateString('ru', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
  const head = (pr.kind === 'no_show' ? 'Не пришёл' : 'Был отказ') + (when ? ' ' + when : '') +
    (pr.vacancy_title ? ` · «${pr.vacancy_title}»` : pr.source === 'card' ? ' · вне воронок' : '');
  const who = [
    pr.recruiter_name,
    pr.source === 'archive' ? `ClickUp: ${pr.from_stage || 'архив'}` : (pr.from_stage ? `с этапа «${pr.from_stage}»` : ''),
  ].filter(Boolean).join(' · ');
  const more = (pr.count || 0) > 1 ? ` · всего ${pr.count}` : '';
  const url = `${base}/all-candidates?entity=${Number(pr.entity_id)}${pr.archived ? '&archived=1' : ''}`;
  return `<div class="rej-block">
    <div class="rej-title">${esc(head)}${esc(more)}</div>
    ${who ? `<div class="rej-sub">${esc(who)}</div>` : ''}
    ${pr.comment ? `<div class="rej-sub">«${esc(pr.comment)}»</div>` : ''}
    ${pr.reason ? `<div class="rej-sub">Причина: ${esc(pr.reason)}</div>` : ''}
    <div class="rej-open" data-url="${url}">Открыть карточку</div>
  </div>`;
}

// Карточка рисуется дважды — быстрый показ кэша и потом полный разбор вкладки,
// — и раньше каждый раз уходила своя проверка дублей: два одинаковых запроса по
// 2–5 с на проде (22.10.2026). Повторяем, только если поменялось то, по чему
// ищем.
let lastDupSignature = null;

async function checkDuplicatesOnLoad() {
  const manualEmail = document.getElementById('manualEmail')?.value;
  const manualNameForCheck = document.getElementById('manualName')?.value?.trim();
  const signature = JSON.stringify([
    parsedData.full_name, manualNameForCheck, parsedData.email || manualEmail,
    parsedData.phone, parsedData.telegram, parsedData.source_url,
  ]);
  if (signature === lastDupSignature) return;
  lastDupSignature = signature;

  const dupStatus = document.getElementById('dupStatus');
  dupStatus.style.display = 'block';
  dupStatus.className = 'dup-status checking';
  dupStatus.textContent = 'Проверяем базу…';

  try {
    // Дубль-чек — некритичная фоновая проверка при открытии попапа. НЕ гоняем её
    // через refresh-ретрай apiRequest (иначе 401 увёл бы на экран входа прямо из
    // авто-проверки) и держим короткий таймаут 12с, чтобы спиннер «Проверяем
    // базу…» не висел. Авторизацию разрулит уже сам «Добавить».
    const dupPayload = {
      full_name: (parsedData.name_is_placeholder && manualNameForCheck) ? manualNameForCheck : parsedData.full_name,
      email: parsedData.email || manualEmail || null,
      phone: parsedData.phone || null,
      telegram: parsedData.telegram || null,
      source_url: parsedData.source_url || null,
    };
    // Протухший за 15 минут access-токен background.js обновит и повторит запрос
    // сам, поэтому ретрая здесь больше нет. rawApiRequest (в отличие от
    // apiRequest) не уводит на экран входа — это фоновая проверка, авторизацию
    // разрулит уже сам «Добавить».
    const checkResp = await rawApiRequest('POST', '/api/magic-button/check-duplicate', dupPayload, 20000);

    if (!checkResp.success) {
      // Проверка упала (сеть / нет refresh-токена) — НЕ выдаём ложное «дубликатов нет».
      dupStatus.className = 'dup-status checking';
      dupStatus.textContent = 'Не удалось проверить дубликаты';
      lastDupSignature = null;  // следующий показ карточки попробует снова
      return;
    }
    const res = checkResp.data;
    const base = serverUrl || document.getElementById('serverUrl').value;
    // Совпадение в архиве — только флаг и id ОДНОЙ карточки: список архива
    // закрыт (superadmin-only), но открыть совпавшего по id рекрутёр может.
    const archiveNote = res.has_archive_match
      ? `<div class="dup-link"${res.archive_match_id ? ` data-url="${base}/all-candidates?entity=${Number(res.archive_match_id)}&archived=1"` : ''}>Похожий кандидат есть в архиве${res.archive_match_id ? ' · <span class="open">открыть</span>' : ''}</div>`
      : '';
    // «Возможно тот же человек» — нет точного совпадения контакта, но сложилась
    // комбинация имя/ДР/частичный контакт. При точном дубле не показываем.
    const softNote = (res.soft_match && !res.is_duplicate)
      ? `<div class="dup-title">Возможно, тот же человек · ${Math.round(res.soft_confidence || 0)}%</div>` +
        (Array.isArray(res.soft_reasons) ? res.soft_reasons.map((r) => `<span class="reason">${esc(r)}</span>`).join('') : '') +
        (res.soft_match_id ? `<div class="dup-link" data-url="${base}/all-candidates?entity=${Number(res.soft_match_id)}">Открыть карточку</div>` : '')
      : '';

    // «Был отказ» (22.10.2026): человек уже отклонён — в воронке, вне воронок или
    // в архиве ClickUp. Самое важное, поэтому первым и красным.
    const rejNote = renderPriorRejection(res.prior_rejection, base);

    if (res.is_duplicate) {
      const dups = res.duplicates || [];
      dupStatus.className = 'dup-status found';
      dupStatus.innerHTML = rejNote + `<div class="dup-title">Уже в базе${dups.length > 1 ? ` · ${dups.length}` : ''}</div>` +
        dups.map((d) => {
          const info = [d.email, d.phone].filter(Boolean).join(' · ');
          const apps = d.applications || [];
          const rows = apps.length
            ? apps.map((a) => {
                const when = formatDateShort(a.last_stage_change_at || a.applied_at);
                return `<div class="dup-row"><span class="vac">${esc(a.vacancy_title)}</span>` +
                  stageChip(a.stage, a.stage_key) +
                  (when ? `<span class="date">${esc(when)}</span>` : '') + '</div>';
              }).join('')
            : '<div class="dup-empty">Ни в одной воронке</div>';
          return `<div class="dup-item">
            <div class="dup-head">
              <a href="#" class="dup-name" data-url="${base}/all-candidates?entity=${Number(d.entity_id)}">${esc(d.name)}</a>
              ${apps.length ? '' : stageChip(d.status, d.status_key)}
            </div>
            ${info ? `<div class="dup-info">${esc(info)}</div>` : ''}
            ${rows}
          </div>`;
        }).join('') + archiveNote;
    } else if (softNote || archiveNote || rejNote) {
      dupStatus.className = 'dup-status found';
      dupStatus.innerHTML = rejNote + softNote + archiveNote;
    } else {
      dupStatus.className = 'dup-status clean';
      dupStatus.textContent = 'Новый кандидат — в базе его нет';
    }

    // Любая ссылка в плашке открывает карточку новой вкладкой.
    dupStatus.querySelectorAll('[data-url]').forEach((el) => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        chrome.tabs.create({ url: el.dataset.url });
      });
    });
  } catch (e) {
    console.error('Duplicate check failed:', e);
    dupStatus.style.display = 'none';
  }
}

async function loadVacancies() {
  // Маша: иногда воронки пропадали и появлялись через 5 минут — это
  // совпадало с redeploy Railway / временным таймаутом сети. Раньше
  // молчаливо ловили catch и оставляли пустой селект. Теперь:
  //  • до 3 попыток с задержкой 1.5с / 3с
  //  • показываем явный disabled-option «не удалось загрузить» если все упали
  //  • показываем «нет открытых воронок» если API вернул пустой массив
  const select = document.getElementById('funnelSelect');
  select.innerHTML = '<option value="">Загружаем воронки…</option>';
  select.disabled = true;

  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const resp = await apiRequest('GET', '/api/magic-button/vacancies');
      if (resp.success && Array.isArray(resp.data)) {
        vacancies = resp.data;
        select.disabled = false;
        if (vacancies.length === 0) {
          select.innerHTML =
            '<option value="">Без воронки</option>' +
            '<option value="" disabled>— у вас нет открытых воронок —</option>';
        } else {
          select.innerHTML = '<option value="">Без воронки</option>';
          vacancies.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.id;
            opt.textContent = v.title;
            select.appendChild(opt);
          });
        }
        return;
      }
      lastError = resp && resp.error ? resp.error : 'unknown error';
      console.warn(`[HR-Bot] loadVacancies attempt ${attempt} failed:`, lastError);
    } catch (e) {
      lastError = e && e.message ? e.message : String(e);
      console.warn(`[HR-Bot] loadVacancies attempt ${attempt} threw:`, lastError);
    }
    if (attempt < 3) {
      await new Promise(r => setTimeout(r, attempt * 1500));
    }
  }

  // Все попытки упали — показываем явную ошибку, не пустой дропдаун.
  console.error('Failed to load vacancies after retries:', lastError);
  select.innerHTML =
    '<option value="">Без воронки</option>' +
    '<option value="" disabled>⚠ не удалось загрузить — нажмите «Перезагрузить»</option>';
  select.disabled = false;
}

// Низкоуровневый запрос через фоновый процесс (CORS bypass).
// Возвращает { success, data?, error?, status? }.
// Токен сюда не передаём: им владеет background.js — он же при 401 обновит его
// и повторит запрос сам. Поэтому запас по времени больше: худший случай —
// запрос + рефреш + повтор.
async function rawApiRequest(method, path, body, timeoutMs = 80000) {
  const url = (serverUrl || document.getElementById('serverUrl').value) + path;

  // MV3 service worker может заснуть посреди запроса и sendResponse теряется
  // → попап будет ждать вечно. Прикрываем явным таймаутом.
  return new Promise((resolve) => {
    let done = false;
    const timer = setTimeout(() => {
      if (done) return;
      done = true;
      console.warn('[HR-Bot] API_REQUEST timeout', { method, url });
      resolve({ success: false, error: 'Сервер не ответил. Попробуйте ещё раз.' });
    }, timeoutMs);

    chrome.runtime.sendMessage({
      type: 'API_REQUEST',
      url,
      method,
      body,
    }, (response) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      if (chrome.runtime.lastError) {
        console.warn('[HR-Bot] sendMessage error:', chrome.runtime.lastError);
        resolve({ success: false, error: chrome.runtime.lastError.message || 'Соединение с фоновым процессом потеряно' });
        return;
      }
      resolve(response || { success: false, error: 'Пустой ответ от фонового процесса' });
    });
  });
}

// Обновление токена и откат на веб-сессию живут в background.js — попап их
// больше не делает. Причина: Chrome убивает JS-контекст попапа в момент его
// закрытия, и если рефреш был в полёте, новая пара токенов терялась, тогда как
// сервер уже сжёг старый refresh ротацией. Это и давало «Сессия истекла» по
// нескольку раз в день на совершенно живой сессии.

async function handleAuthExpired() {
  authToken = '';
  refreshToken = '';
  await chrome.storage.local.remove(['authToken', 'refreshToken']);
  const le = document.getElementById('loginError');
  if (le) le.textContent = 'Сессия истекла — войдите снова';
  showView('login');
}

// Высокоуровневый запрос. Рефреш и откат на веб-сессию делает background.js;
// сюда возвращается authExpired === true ТОЛЬКО когда обновиться не удалось и
// сервер подтвердил, что сессия мертва. Сетевой сбой, таймаут или сон воркера
// сюда не попадают — на них попап больше не разлогинивает.
async function apiRequest(method, path, body, timeoutMs = 80000) {
  const resp = await rawApiRequest(method, path, body, timeoutMs);
  if (resp && resp.authExpired) await handleAuthExpired();
  return resp;
}

// Login
document.getElementById('loginBtn').addEventListener('click', async () => {
  const email = document.getElementById('loginEmail').value;
  const password = document.getElementById('loginPassword').value;
  serverUrl = document.getElementById('serverUrl').value.replace(/\/$/, '');

  if (!email || !password || !serverUrl) {
    document.getElementById('loginError').textContent = 'Заполните все поля';
    return;
  }

  document.getElementById('loginBtn').disabled = true;
  document.getElementById('loginBtn').textContent = 'Входим...';

  try {
    const resp = await fetch(serverUrl + '/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // include_refresh: расширению нужен refresh-токен в теле (silent-refresh) —
      // куки SameSite=Lax на кросс-сайтовый POST из расширения не уходят.
      body: JSON.stringify({ email, password, include_refresh: true }),
      credentials: 'include',
    });

    if (resp.ok) {
      const data = await resp.json();
      // Backend returns { access_token, refresh_token, token_type, user } in body
      authToken = data.access_token;
      refreshToken = data.refresh_token || '';
      await chrome.storage.local.set({ serverUrl, authToken, refreshToken, userName: data.user?.name || '' });
      showWho(data.user?.name || '');
      checkExtensionUpdate();

      document.getElementById('loginError').textContent = '';

      // Парсим активную вкладку, а не читаем кэш: после первого входа кэш пуст,
      // и рекрутёру на живой странице резюме показывалось «страница не
      // поддерживается», пока он вручную не жал «↻».
      await loadFromActiveTab();
    } else {
      document.getElementById('loginError').textContent = 'Неверный email или пароль';
    }
  } catch (e) {
    document.getElementById('loginError').textContent = 'Ошибка соединения: ' + e.message;
  }

  document.getElementById('loginBtn').disabled = false;
  document.getElementById('loginBtn').textContent = 'Войти';
});

// «Добавить в «Трафик»» — видно, куда уйдёт кандидат, не глядя на список.
function funnelSuffix() {
  const sel = document.getElementById('funnelSelect');
  return sel && sel.value ? ` в «${sel.options[sel.selectedIndex].textContent}»` : '';
}
function updateAddLabel() {
  const btn = document.getElementById('addBtn');
  if (!btn || btn.disabled) return;
  btn.textContent = btn.classList.contains('confirmed')
    ? 'Всё равно добавить' + funnelSuffix()
    : 'Добавить' + (funnelSuffix() || ' кандидата');
}
document.getElementById('funnelSelect').addEventListener('change', updateAddLabel);

// Add candidate
document.getElementById('addBtn').addEventListener('click', async () => {
  if (!parsedData) return;

  const manualEmail = document.getElementById('manualEmail').value.trim();
  const manualPhone = document.getElementById('manualPhone')?.value.trim() || '';
  const manualTelegramRaw = document.getElementById('manualTelegram')?.value.trim() || '';
  const manualTelegram = manualTelegramRaw
    ? (manualTelegramRaw.startsWith('@') ? manualTelegramRaw : '@' + manualTelegramRaw.replace(/.*t\.me\//, ''))
    : '';
  const vacancyId = document.getElementById('funnelSelect').value;
  const comment = document.getElementById('commentField').value;
  const dupStatus = document.getElementById('dupStatus');
  const hasDuplicates = dupStatus && dupStatus.classList.contains('found');

  const btn = document.getElementById('addBtn');

  // If duplicates were found and user hasn't confirmed yet — ask first
  if (hasDuplicates && !btn.classList.contains('confirmed')) {
    btn.textContent = 'Всё равно добавить' + funnelSuffix();
    btn.classList.add('warning', 'confirmed');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Добавляем…';

  try {
    const manualName = document.getElementById('manualName')?.value?.trim();
    const finalName = (parsedData.name_is_placeholder && manualName) ? manualName : parsedData.full_name;
    const resp = await apiRequest('POST', '/api/magic-button/parse', {
      full_name: finalName,
      email: parsedData.email || manualEmail || null,
      phone: parsedData.phone || manualPhone || null,
      telegram: parsedData.telegram || manualTelegram || null,
      photo_url: parsedData.photo_url || null,
      position: parsedData.position || null,
      source_url: parsedData.source_url,
      source: parsedData.source,
      vacancy_id: vacancyId ? parseInt(vacancyId) : null,
      comment: comment || null,
      city: parsedData.city || null,
      age: parsedData.age || null,
      birthday: parsedData.birthday || null,
      gender: parsedData.gender || null,
      salary: parsedData.salary || null,
      experience_summary: parsedData.experience_summary || null,
      total_experience: parsedData.total_experience || null,
      experience_descriptions: parsedData.experience_descriptions || null,
      skills: parsedData.skills || null,
      languages: parsedData.languages || null,
      company: parsedData.company || null,
      education: parsedData.education || null,
      certifications: parsedData.certifications || null,
    });

    if (resp.success) {
      try {
        const result = resp.data;
        const icon = document.getElementById('resultIcon');
        icon.textContent = result.is_duplicate ? '!' : '✓';
        icon.classList.toggle('warn', !!result.is_duplicate);
        document.getElementById('resultTitle').textContent = result.is_duplicate
          ? 'Добавлен — такой уже был в базе'
          : 'Кандидат добавлен';
        const funnelSel = document.getElementById('funnelSelect');
        const funnelName = funnelSel.value ? funnelSel.options[funnelSel.selectedIndex].textContent : '';
        document.getElementById('resultMessage').textContent = funnelName
          ? `В воронку «${funnelName}», этап «Новый»`
          : 'Без воронки — найдёте его в «Все кандидаты»';
        const hiddenDupEl = document.getElementById('hiddenDupWarning');
        if (hiddenDupEl) hiddenDupEl.style.display = result.has_hidden_duplicate ? 'block' : 'none';
        const linkEl = document.getElementById('resultLink');
        if (linkEl && result.entity_id) {
          const candidateUrl = `${serverUrl}/all-candidates?entity=${result.entity_id}`;
          linkEl.innerHTML = `<a href="#" class="candidate-link">Открыть карточку кандидата</a>`;
          linkEl.style.display = 'block';
          linkEl.querySelector('.candidate-link').addEventListener('click', (e) => {
            e.preventDefault();
            chrome.tabs.create({ url: candidateUrl });
          });
        }
        showView('result');
      } catch (renderErr) {
        // Сервер ответил OK, но что-то сломалось при рендере экрана успеха —
        // не оставляем юзера с залипшим 'Добавляем...'.
        console.error('[HR-Bot] Result render failed:', renderErr);
        document.getElementById('addError').textContent =
          'Кандидат сохранён, но не удалось показать экран. Обнови страницу.';
      }
    } else {
      document.getElementById('addError').textContent = resp.error || 'Ошибка добавления';
    }
  } catch (e) {
    console.error('[HR-Bot] Add failed:', e);
    document.getElementById('addError').textContent = 'Ошибка: ' + (e && e.message ? e.message : 'неизвестная');
  } finally {
    // Кнопка должна вернуться в исходное состояние ВСЕГДА — даже если
    // что-то упало в success-ветке или таймаут не сработал.
    btn.disabled = false;
    btn.classList.remove('warning', 'confirmed');
    updateAddLabel();
  }
});

// Кнопка «Копировать ссылку на форму» убрана по запросу.

// Add another — сбрасываем форму и подтягиваем активную вкладку через единый
// загрузчик loadFromActiveTab (он уже умеет re-parse + ретраи).
document.getElementById('addAnotherBtn').addEventListener('click', async () => {
  parsedData = null;
  document.getElementById('duplicateWarning').style.display = 'none';
  document.getElementById('addError').textContent = '';
  document.getElementById('addBtn').classList.remove('warning', 'confirmed');
  updateAddLabel();
  lastDupSignature = null;
  ['manualName', 'manualEmail', 'manualPhone', 'manualTelegram', 'commentField']
    .forEach((id) => { const el = document.getElementById(id); if (el) el.value = ''; });
  await loadFromActiveTab();
});

// Manual refresh — пользователь жмёт когда хочет принудительно перечитать
// текущую вкладку (страховка если auto-load промахнулся).
const refreshBtn = document.getElementById('refreshBtn');
if (refreshBtn) {
  refreshBtn.addEventListener('click', async () => {
    refreshBtn.disabled = true;
    parsedData = null;
    await loadFromActiveTab();
    refreshBtn.disabled = false;
  });
}

// Logout
document.getElementById('logoutLink').addEventListener('click', (e) => {
  e.preventDefault();
  chrome.storage.local.clear();
  authToken = '';
  showWho('');
  showView('login');
});
