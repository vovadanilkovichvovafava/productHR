// Общий модуль для всех парсеров (инжектится ПЕРВЫМ в каждом content_scripts).
// Изолированный мир content-скрипта НЕ видит page-глобалы (window.X страницы),
// поэтому JSON ищем только в DOM (script-теги).
(function () {
  if (window.__ENC__) return;

  // Лимиты длины по полям — режем раздувшиеся значения.
  const FIELD_MAX = {
    full_name: 80, position: 120, city: 60, age: 20, salary: 60,
    company: 120, total_experience: 60, gender: 20, birthday: 40,
    email: 120, phone: 40, telegram: 64,
  };
  const ARR_MAX = { skills: 30, languages: 15, education: 5 };
  const ARR_ITEM_MAX = 200;

  // Маркеры нав-мусора: если строка их содержит — это не значение поля,
  // а кусок навигации/служебного текста (частая болезнь Habr).
  const NAV_MARKERS = [
    'Все сервисы', 'Сообщество IT', 'Создать вакансию', 'Кабинет компании',
    'Подключи Бустер', 'Подними свой профиль', 'Избранные вакансии',
    'Лента вакансий', 'Регистрация', 'Профиль содержит', 'Рассылает спам',
    'Ведёт себя оскорбительно', 'Выдаёт себя за другого',
  ];

  // Похоже ли на технический мусор (код / JSON / разметку).
  function isGarbage(s) {
    if (typeof s !== 'string') return true;
    if (/[{}<>]/.test(s)) return true;
    if (/function\s*\(|=>|\bvar\s|\bwindow\.|\bdocument\./.test(s)) return true;
    if (/"[\w-]+"\s*:/.test(s)) return true;             // JSON-пары "key":
    if (/\}\s*,\s*\{|\]\s*,\s*"/.test(s)) return true;    // JSON-массивы/объекты
    for (const m of NAV_MARKERS) if (s.includes(m)) return true;
    return false;
  }

  function cleanText(s, maxLen) {
    if (s == null) return '';
    let t = String(s).replace(/\s+/g, ' ').trim();
    if (maxLen && t.length > maxLen) t = t.slice(0, maxLen).trim();
    return t;
  }

  function sanitizeStr(s, maxLen) {
    const t = cleanText(s, maxLen);
    if (!t || isGarbage(t)) return '';
    return t;
  }

  const EMAIL_RE = /^[\w.+-]+@[\w-]+\.[a-z]{2,}$/i;
  function isEmail(s) { return typeof s === 'string' && EMAIL_RE.test(s.trim()); }

  // Служебные ящики сайтов вакансий — не почта кандидата. На rabota.by, когда
  // кандидат почту не указал, в блоке контактов стоит support@rabota.by, и его
  // сохраняли как почту человека (22.09.2026). Тот же список — на бэкенде,
  // is_service_email в services/similarity.py.
  const JOB_SITE_EMAIL_DOMAINS = [
    'rabota.by', 'hh.ru', 'hh.kz', 'hh.uz', 'hh.by', 'headhunter.ru', 'headhunter.kz',
    'superjob.ru', 'rabota.ru', 'zarplata.ru', 'trudvsem.ru', 'praca.by',
    'work.ua', 'robota.ua', 'rabota.ua', 'djinni.co', 'getmatch.ru',
  ];
  const SERVICE_EMAIL_LOCALS = [
    'support', 'noreply', 'no-reply', 'donotreply', 'do-not-reply',
    'mailer-daemon', 'notifications', 'notification', 'robot',
  ];
  function isServiceEmail(s) {
    const e = String(s || '').trim().toLowerCase();
    const at = e.indexOf('@');
    if (at < 0) return false;
    const local = e.slice(0, at), domain = e.slice(at + 1);
    if (SERVICE_EMAIL_LOCALS.includes(local)) return true;
    // Адрес на домене самого сайта, с которого сохраняют анкету, — тоже его.
    const host = (location.hostname || '').toLowerCase().replace(/^www\./, '');
    const sameSite = host && (domain === host || host.endsWith('.' + domain) || domain.endsWith('.' + host));
    return sameSite || JOB_SITE_EMAIL_DOMAINS.some(d => domain === d || domain.endsWith('.' + d));
  }
  function isPhone(s) {
    if (typeof s !== 'string') return false;
    const d = s.replace(/\D/g, '');
    return d.length >= 7 && d.length <= 15;
  }
  // Чистим телеграм: @user / t.me/user. Отсекаем служебные ники ПЛОЩАДОК: в
  // промо/футере hh.ru и др. есть ссылка t.me/<канал> (напр. t.me/hh_b2b), и у
  // кандидата БЕЗ личного тг фолбэк-скан ссылок цеплял канал самой площадки как
  // «телеграм человека». Зеркало backend JUNK_TELEGRAM_USERNAMES (similarity.py).
  const TG_BLOCK = [
    'habrcareer_bot', 'share', 'joinchat', 'telegram', 'tg', 'telega',
    'hh', 'hh_b2b', 'hh_news', 'hh_news_hr', 'hhnews', 'hhbot', 'headhunter', 'hhru',
    'superjob', 'superjob_ru', 'avito', 'avito_official',
    'habr', 'habrcareer', 'linkedin', 'vk', 'vkontakte',
  ];
  function normalizeTelegram(s) {
    if (typeof s !== 'string') return '';
    let v = s.trim();
    const m = v.match(/t\.me\/([A-Za-z0-9_]{3,})/);
    if (m) v = m[1];
    v = v.replace(/^@/, '').trim();
    if (!/^[A-Za-z0-9_]{3,40}$/.test(v)) return '';
    if (TG_BLOCK.includes(v.toLowerCase())) return '';
    return '@' + v;
  }

  function dedupeClean(arr, maxItems) {
    const out = [], seen = new Set();
    for (const item of arr || []) {
      const t = sanitizeStr(item, ARR_ITEM_MAX);
      if (t && !seen.has(t)) { seen.add(t); out.push(t); }
      if (out.length >= maxItems) break;
    }
    return out;
  }

  // Финальная санитизация записи ПЕРЕД отправкой. Мусор не доходит до CRM.
  function sanitizeRecord(data) {
    const d = Object.assign({}, data);
    for (const f of Object.keys(FIELD_MAX)) {
      if (!(f in d)) continue;
      if (f === 'email') { const e = cleanText(d.email, FIELD_MAX.email); d.email = isEmail(e) && !isServiceEmail(e) ? e : ''; }
      else if (f === 'phone') { const p = cleanText(d.phone, FIELD_MAX.phone); d.phone = isPhone(p) ? p : ''; }
      else if (f === 'telegram') { d.telegram = normalizeTelegram(d.telegram); }
      else { d[f] = sanitizeStr(d[f], FIELD_MAX[f]); }
    }
    // experience_summary — построчно (одна грязная строка не убивает весь блок).
    if (d.experience_summary) {
      d.experience_summary = String(d.experience_summary).split('\n')
        .map(l => sanitizeStr(l, 300)).filter(Boolean).slice(0, 8).join('\n');
    }
    for (const f of Object.keys(ARR_MAX)) {
      if (Array.isArray(d[f])) d[f] = dedupeClean(d[f], ARR_MAX[f]);
    }
    return d;
  }

  // Поиск объекта с ВСЕМИ ключами needKeys (на любом уровне вложенности).
  function deepHasKeys(obj, keys) {
    const found = new Set();
    const stack = [obj]; let steps = 0;
    while (stack.length && steps < 20000) {
      steps++;
      const cur = stack.pop();
      if (cur && typeof cur === 'object') {
        for (const k of Object.keys(cur)) {
          if (keys.includes(k)) found.add(k);
          const v = cur[k];
          if (v && typeof v === 'object') stack.push(v);
        }
        if (found.size === keys.length) return true;
      }
    }
    return found.size === keys.length;
  }

  // Встроенный JSON-остров из DOM (typed script-теги). Возвращает первый объект,
  // содержащий все needKeys, либо null.
  function extractProfileJson(needKeys) {
    const sel = 'script[type="application/json"], script[type="application/ld+json"]';
    for (const sc of document.querySelectorAll(sel)) {
      const t = (sc.textContent || '').trim();
      if (!t || (t[0] !== '{' && t[0] !== '[')) continue;
      try {
        const o = JSON.parse(t);
        if (!needKeys || deepHasKeys(o, needKeys)) return o;
      } catch (_) {}
    }
    return null;
  }

  // ─────────── Фото кандидата ───────────
  // Баннеры на странице — тоже <img>, и у рекламного креатива бывает обычный
  // .webp/.jpg. Пока фото искали «по всей странице», у кандидата БЕЗ фото в
  // карточку уезжал кусок рекламы AdFox (жалоба Марии 08.10.2026: вместо людей
  // вебинар DreamJob). Поэтому два правила: берём картинку только с хостов hh
  // и только из блока резюме, рекламные контейнеры пропускаем.

  const PHOTO_HOSTS = ['hhcdn.ru', 'hh.ru', 'rabota.by', 'hhstatic.ru'];
  // Контейнеры, внутри которых картинка — ЗАВЕДОМО не кандидат.
  const PHOTO_SKIP_CONTAINERS = [
    'aside', 'header', 'footer', 'nav',
    '[class*="banner"]', '[class*="Banner"]', '[id*="AdFox"]', '[id*="adfox"]',
    '[class*="advert"]', '[class*="promo"]', '[data-qa*="banner"]',
    '[class*="company-logo"]', '[data-qa*="company-logo"]',
    '[data-qa="resume-experience-company-logo"]',
  ].join(',');

  function hostOf(url) {
    try {
      return new URL(url, location.href).hostname.toLowerCase();
    } catch (_) {
      return '';
    }
  }

  // Ссылка похожа на НАСТОЯЩЕЕ фото человека с hh, а не на заглушку/логотип/баннер.
  function isRealPhotoUrl(src) {
    if (!src || typeof src !== 'string') return false;
    if (!src.startsWith('http') && !src.startsWith('//')) return false;
    const url = src.startsWith('//') ? 'https:' + src : src;
    const host = hostOf(url);
    // Хост-аллоулист: реклама приезжает с adfox/yandex/mail.ru/avatars.mds и
    // раньше проходила все проверки, потому что кончалась на .webp.
    if (!PHOTO_HOSTS.some((h) => host === h || host.endsWith('.' + h))) return false;
    const lower = url.toLowerCase();
    if (lower.includes('placeholder') || lower.includes('empty-avatar') ||
        lower.includes('default-avatar') || lower.includes('silhouette') ||
        lower.includes('no-photo') || lower.includes('noavatar') ||
        lower.endsWith('.svg') ||
        lower.includes('/icons/') || lower.includes('logo') ||
        lower.includes('employer') ||
        lower.includes('sprite')) return false;
    return /\.(?:jpe?g|png|webp)(?:[?#]|$)/i.test(lower);
  }

  function insideSkipped(el) {
    return !!(el.closest && el.closest(PHOTO_SKIP_CONTAINERS));
  }

  /**
   * Фото кандидата со страницы резюме.
   * selectors — по порядку, от самого точного к общему; ищем внутри блока
   * резюме (root), рекламу и логотипы компаний пропускаем.
   */
  function pickResumePhoto(selectors, rootSelectors) {
    const roots = [];
    for (const sel of (rootSelectors || [])) {
      const el = document.querySelector(sel);
      if (el) roots.push(el);
    }
    if (!roots.length) roots.push(document.body || document);

    const fromImg = (el) => {
      if (!el || insideSkipped(el)) return '';
      const src = (el.currentSrc || el.src || el.getAttribute('src') || '').trim();
      const normalized = src.startsWith('//') ? 'https:' + src : src;
      return isRealPhotoUrl(normalized) ? normalized : '';
    };

    for (const sel of selectors) {
      for (const root of roots) {
        for (const el of root.querySelectorAll(sel)) {
          const found = fromImg(el);
          if (found) return found;
        }
      }
    }
    // Фон вместо <img> (встречалось в старой вёрстке) — тоже только внутри резюме.
    for (const root of roots) {
      const boxes = root.querySelectorAll(
        '[class*="photo"], [class*="avatar"], [data-qa*="photo"], [data-qa*="avatar"]'
      );
      for (const el of boxes) {
        if (insideSkipped(el)) continue;
        const bg = (getComputedStyle(el).backgroundImage || '');
        const m = bg.match(/url\(["']?([^"')]+)["']?\)/);
        if (!m) continue;
        const normalized = m[1].startsWith('//') ? 'https:' + m[1] : m[1];
        if (isRealPhotoUrl(normalized)) return normalized;
      }
    }
    return '';
  }

  window.__ENC__ = {
    sanitizeRecord, sanitizeStr, cleanText, isGarbage,
    isEmail, isServiceEmail, isPhone, normalizeTelegram, extractProfileJson, deepHasKeys,
    isRealPhotoUrl, pickResumePhoto,
  };
})();
