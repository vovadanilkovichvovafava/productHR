(function() {
  // Guard: при programmatic inject (chrome.scripting.executeScript) скрипт может
  // выполниться повторно поверх уже зарегистрированного listener'а. Без этого
  // на одно RE_PARSE приходило бы несколько ответов.
  if (window.__hr_bot_hh_loaded__) return;
  window.__hr_bot_hh_loaded__ = true;

  // rabota.by = HeadHunter Belarus — тот же DOM/data-qa, тот же парсер, но
  // источник и фолбэк-имя должны отражать реальный хост (для dedup по
  // source_url и понятной метки в карточке кандидата). Регистрируемый домен:
  // берём последние 2 лейбла (vitebsk.rabota.by → rabota.by, saratov.hh.ru → hh.ru).
  const SITE_HOST = window.location.hostname.replace(/^www\./, '').split('.').slice(-2).join('.') === 'rabota.by'
    ? 'rabota.by'
    : 'hh.ru';

  // Раньше тут был early-return если URL не /resume/* — но на страницах
  // работодателя hh.ru/employer/...?resumeId=... данные тоже есть, и нам
  // нужно их парсить. Если ничего не найдём — popup покажет nodata.

  // Helper: get text content from selector
  function getText(selector) {
    const el = document.querySelector(selector);
    return el ? el.textContent.trim() : '';
  }

  // Helper: get text from multiple selectors (first match wins)
  function getTextMulti(selectors) {
    for (const sel of selectors) {
      const text = getText(sel);
      if (text) return text;
    }
    return '';
  }

  // Helper: найти ФИО по ВИДУ текста, не завязываясь на конкретные data-qa/классы
  // (hh периодически меняет вёрстку, и точечные селекторы имени отваливаются).
  // ФИО = 2–3 слова кириллицей с заглавной (фамилия может быть через дефис).
  // Ищем только в ВЕРХНЕЙ части резюме (до блока опыта/образования), чтобы случайно
  // не принять за имя название компании из опыта работы, и не лезем в шапку сайта.
  function findFioByPattern() {
    // ФИО = 2–3 слова с заглавной (фамилия может быть через дефис). ЛАТИНИЦА И
    // кириллица: раньше regex был только кириллический, поэтому английские имена
    // (Olena Vsk, Lena Vasko) не ловились и кандидат приезжал с именем-плейсхолдером
    // «Должность, Город, Возраст». Допустимы оба алфавита, но в пределах одного
    // слова не смешиваем регистры алфавитов — снижает ложные срабатывания.
    const FIO_RE = /^[A-ZА-ЯЁ][a-zа-яё]+(?:-[A-ZА-ЯЁ][a-zа-яё]+)?\s+[A-ZА-ЯЁ][a-zа-яё]+(?:\s+[A-ZА-ЯЁ][a-zа-яё]+)?$/;

    // Читаем только ПРЯМЫЕ text-узлы элемента (не текст дочерних elements).
    // Нужно потому что hh.ru magritte оборачивает имя в span, внутри которого
    // могут быть дочерние элементы (кнопки редактирования, иконки, hidden-спаны) —
    // тогда el.children.length > 0 и листовая проверка пропускает элемент,
    // а el.textContent склеивает имя с текстом дочерних элементов. text-узлы дают
    // только видимый текст самого элемента.
    function ownText(el) {
      let t = '';
      for (const node of el.childNodes) {
        if (node.nodeType === 3) t += node.textContent; // TEXT_NODE
      }
      return t.replace(/ /g, ' ').trim();
    }

    // Быстрый путь: hh.ru magritte (2024–2025+) — имя кандидата в шапке резюме
    // [data-qa="resume-main-info__header"] h2 > span. Span может иметь дочерние
    // элементы, поэтому читаем text-узлы вместо обычного leaf-scan.
    // Имя «на вид»: полное ФИО (2–3 слова) ИЛИ анонимизированный формат hh.ru —
    // инициалы + имя, напр. «Н Станислав А», «Иван И.», «И. И. Иванов». Раньше в
    // шапке принимали только полное ФИО, поэтому анонимные резюме приезжали с
    // именем-плейсхолдером «Должность, Город, Возраст».
    function isLikelyName(s) {
      if (!s) return false;
      s = s.trim();
      if (s.length < 3 || s.length > 60) return false;
      if (/^\s*(кандидат|candidate)\s*$/i.test(s)) return false;
      if (FIO_RE.test(s)) return true;
      const tokens = s.split(/[\s.]+/).filter(Boolean);
      if (tokens.length < 2 || tokens.length > 4) return false;
      // Каждый токен — заглавная + опц. строчные (инициал «Н» или слово «Станислав»).
      if (!tokens.every((t) => /^[A-ZА-ЯЁ][a-zа-яё]*$/.test(t))) return false;
      // Хотя бы один «настоящий» токен (имя/фамилия ≥ 3 букв), не только инициалы.
      return tokens.some((t) => t.length >= 3);
    }

    const magritteH2 = document.querySelector('[data-qa="resume-main-info__header"] h2');
    if (magritteH2) {
      const h2txt = ownText(magritteH2);
      if (isLikelyName(h2txt)) return h2txt;
      for (const span of magritteH2.querySelectorAll('span')) {
        const stxt = ownText(span);
        if (isLikelyName(stxt)) return stxt;
      }
    }

    const boundary = document.querySelector(
      '[data-qa="resume-block-experience"], [data-qa*="experience"], [data-qa*="education"]'
    );
    const beforeBoundary = (el) =>
      !boundary || !!(el.compareDocumentPosition(boundary) & Node.DOCUMENT_POSITION_FOLLOWING);
    // НЕ исключаем по широкому [class*="header"]/[class*="menu"]: имя кандидата
    // лежит в ШАПКЕ РЕЗЮМЕ (class вроде resume-header…), и этот фильтр её убивал —
    // имя «в принципе не ловилось». Исключаем только реальный хром сайта hh
    // (supernova-навигация и аккаунт работодателя), а не блок резюме.
    const inSiteChrome = (el) => el.closest(
      'header[class*="supernova"], nav, footer, [data-qa*="mainmenu"], ' +
      '[data-qa*="applicantProfile"], [class*="supernova"], [role="navigation"]'
    );
    // hh (magritte) держит ФИО в шапке резюме data-qa="resume-main-info__header";
    // сначала ищем точечно в ней (надёжнее), затем — скан всего документа.
    const header = document.querySelector('[data-qa="resume-main-info__header"]');
    const scopes = header ? [header, document] : [document];
    for (const scope of scopes) {
      for (const el of scope.querySelectorAll('h1,h2,h3,span,div,a,p,strong,b')) {
        // Листовые узлы (нет дочерних elements) — textContent чистый.
        // Нелистовые — читаем только прямые text-узлы через ownText(), чтобы
        // не склеивать имя с текстом вложенных кнопок/иконок.
        let txt;
        if (el.children.length === 0) {
          txt = (el.textContent || '').trim();
        } else {
          txt = ownText(el);
        }
        if (!txt || txt.length < 5 || txt.length > 60 || !FIO_RE.test(txt)) continue;
        if (inSiteChrome(el) || !beforeBoundary(el)) continue;
        return txt;
      }
    }
    return '';
  }

  // Parse resume data from DOM
  function parseHHResume() {
    const data = {
      source: SITE_HOST,
      source_url: window.location.href,
      full_name: '',
      email: '',
      phone: '',
      telegram: '',
      photo_url: '',
      position: '',
      city: '',
      age: '',
      birthday: '',
      gender: '',
      salary: '',
      company: '',
      experience_summary: '',
      education: [],
    };

    // --- Name ---
    data.full_name = getTextMulti([
      '[data-qa="resume-personal-name"]',
      '.resume-header-name',
      'h1[class*="bloko-header"]',
      'h1[data-qa*="personal"]',
      'h2[data-qa="resume-personal-name"]',
    ]);
    // Точечные селекторы выше ломаются, когда hh меняет вёрстку (так имя кандидата
    // и приезжало как «Должность, Город, Возраст»). Фолбэк: ищем ФИО по виду текста
    // в шапке резюме — независимо от data-qa. Берём только если нашли настоящее ФИО.
    if (!data.full_name || /^\s*кандидат\s*$/i.test(data.full_name)) {
      const fio = findFioByPattern();
      if (fio) data.full_name = fio;
    }
    // Detect closed-contact placeholder: hh.ru renders heading as "Кандидат"
    // when contacts require paid unlock. Mark this so we build a better
    // placeholder AFTER we've parsed position/city/age below.
    const rawNameIsPlaceholder = !data.full_name || /^\s*кандидат\s*$/i.test(data.full_name);
    if (!data.full_name) {
      const headings = document.querySelectorAll('h1, h2');
      for (const h of headings) {
        const txt = h.textContent.trim();
        if (txt && txt.length < 80 && /кандидат|candidate/i.test(txt)) {
          data.full_name = txt;
          break;
        }
      }
    }
    // Final placeholder will be rebuilt after fields are parsed (see end of function)

    // --- Photo ---
    // Выбор фото общий для всех парсеров (content/common.js): только хосты hh,
    // только блок резюме, рекламные блоки и логотипы компаний пропускаются.
    // Раньше искали по ВСЕЙ странице, и у кандидата без фото в карточку
    // попадал рекламный креатив AdFox (жалоба Марии 08.10.2026).
    data.photo_url = (window.__ENC__ && window.__ENC__.pickResumePhoto)
      ? window.__ENC__.pickResumePhoto(
          [
            '[data-qa="resume-photo"] img',
            '[data-qa="resume-photo-image"]',
            '[data-qa="resume-personal-photo"] img',
            '.resume-photo img',
            '.resume-header-photo img',
            '[data-qa="resume-avatar"] img',
            '.resume-avatar img',
            // Вёрстка Magritte (hh.ru 2025+): фото лежит в аватаре шапки резюме
            '[data-qa="resume-main-info__content-wrapper"] img',
            '[class*="magritte-avatar"] img',
            '[class*="resume-photo"] img',
            '[class*="resume-header"] img',
            'img[data-qa="bloko-image"]',
            'img[src*="hhcdn"]',
          ],
          [
            '[data-qa="resume"]',
            '[data-qa="resume-block"]',
            '[class*="resume-applicant"]',
            '[data-qa="resume-main-info__content-wrapper"]',
            'main',
          ],
        )
      : '';
    console.log('[HR-Bot Magic Button] photo_url:', data.photo_url || '(not found)');

    // --- Position/title ---
    data.position = getTextMulti([
      '[data-qa="resume-position"] [data-qa="title"]',
      '[data-qa="resume-position"]',
      '[data-qa="resume-block-title-position"]',
      '.resume-block__title-text_sub',
    ]);

    // --- Contact info ---
    // Note: HH.ru contacts may be hidden behind a "show contacts" button that requires
    // employer access. If contacts are not visible, fields will remain empty - the extension
    // still allows adding the candidate without contacts.

    // Email - try multiple selectors and nested structures.
    // Известный список TLD — нужен чтобы regex не сожрал суффикс типа
    // 'gmail.comWhatsappViberTelegram' (когда лейблы мессенджеров склеены
    // с email в одном textContent). Жадный [\w.-]+ ловил бы всё подряд.
    // Список TLD-якорей. Regex берёт email ДО конца TLD и не лезет дальше,
    // поэтому 'gmail.comWhatsappViberTelegram' даст 'gmail.com'.
    const TLD_RE = /[\w.+-]+@[\w-]+(?:\.[a-z]{2,})*\.(?:com|ru|net|org|io|co|me|by|ua|kz|us|uk|de|fr|it|es|pl|email|edu|gov|biz|info|dev|app|pro|tech|cloud|online|store|site|name|ai|cc|tv|xyz)/i;
    const extractEmailFromText = (txt) => {
      if (!txt) return null;
      const m = txt.match(TLD_RE);
      return m ? m[0] : null;
    };

    const emailSelectors = [
      '[data-qa="resume-contact-email"]',
      '[data-qa="resume-contact-email"] a',
      '[data-qa="resume-contact-email"] span',
      '[data-qa="resume-serp__resume-contact-email"]',
    ];
    for (const sel of emailSelectors) {
      if (data.email) break;
      const els = document.querySelectorAll(sel);
      els.forEach(el => {
        if (data.email) return;
        // 1. Самое надёжное — есть ли внутри <a href="mailto:...">.
        //    href всегда чистый, без мусора из соседних span'ов.
        const mailtoEl = el.matches?.('a[href^="mailto:"]') ? el : el.querySelector?.('a[href^="mailto:"]');
        if (mailtoEl) {
          const href = mailtoEl.getAttribute('href') || '';
          if (href.startsWith('mailto:')) {
            data.email = href.slice(7).split('?')[0].trim();
            return;
          }
        }
        // 2. Прямой href самого элемента (если это <a>).
        const ownHref = el.getAttribute?.('href') || '';
        if (ownHref.startsWith('mailto:')) {
          data.email = ownHref.slice(7).split('?')[0].trim();
          return;
        }
        // 3. Fallback на text — но через строгий TLD-regex.
        const text = el.textContent.trim();
        const fromText = extractEmailFromText(text);
        if (fromText) data.email = fromText;
      });
    }

    // Phone - try multiple selectors, handle formatted numbers
    const phoneSelectors = [
      '[data-qa="resume-contact-phone"]',
      '[data-qa="resume-contact-phone"] a',
      '[data-qa="resume-serp__resume-contact-phone"]',
      '[data-qa="resume-contact-phone-value"]',
      // Новая разметка hh.ru (видна когда работодатель раскрыл контакты):
      // телефон сидит в resume-contact-preferred с href="tel:...".
      '[data-qa="resume-contact-preferred"][href*="tel:"]',
      'a[data-qa="resume-contact-preferred"][href^="tel:"]',
    ];
    for (const sel of phoneSelectors) {
      if (data.phone) break;
      const els = document.querySelectorAll(sel);
      els.forEach(el => {
        if (data.phone) return;
        const text = el.textContent.trim();
        const href = (el.href || el.getAttribute('href') || '');
        // Extract from tel: link
        if (href.includes('tel:')) {
          data.phone = href.replace('tel:', '').trim();
        }
        // Or from text that looks like a phone number
        else if (text.match(/[\+\d][\d\s\-\(\)]{6,}/)) {
          // Normalize: remove extra spaces but keep formatting
          data.phone = text.replace(/\s+/g, ' ').trim();
        }
      });
    }

    // Telegram - try multiple selectors
    const tgSelectors = [
      '[data-qa="resume-phone-deep-link-telegram-text"]',
      '[data-qa="resume-phone-deep-link-telegram"]',
      '[data-qa="resume-contact-preferred"][href*="t.me"]',
      // Новая разметка hh.ru — отдельный блок «способы связи» с
      // attribute resume-communication-method-telegram, плюс может
      // дублироваться в personalsite-personal как ссылка t.me.
      '[data-qa="resume-communication-method-telegram"]',
      'a[data-qa="resume-personalsite-personal"][href*="t.me"]',
    ];
    for (const sel of tgSelectors) {
      if (data.telegram) break;
      const el = document.querySelector(sel);
      if (el) {
        const text = el.textContent.trim();
        const href = (el.href || el.getAttribute('href') || '');
        if (href.includes('t.me/')) {
          const match = href.match(/t\.me\/([^\/?]+)/);
          if (match) data.telegram = '@' + match[1];
        } else if (text.startsWith('@') || text.includes('t.me')) {
          data.telegram = text.startsWith('@') ? text : '@' + text.replace(/.*t\.me\//, '');
        } else if (text && !text.includes(' ')) {
          // Plain username text in a telegram-specific element
          data.telegram = text.startsWith('@') ? text : '@' + text;
        }
      }
    }

    // Fallback: old preferred contact selectors
    if (!data.email || !data.phone || !data.telegram) {
      const contactEls = document.querySelectorAll('[data-qa="resume-contact-preferred"]');
      contactEls.forEach(el => {
        const text = el.textContent.trim();
        const href = el.href || '';
        if (!data.email && (href.includes('mailto:') || text.includes('@'))) {
          // mailto: чище чем text — если есть, используем его.
          if (href.startsWith('mailto:')) {
            data.email = href.slice(7).split('?')[0].trim();
          } else {
            const fromText = extractEmailFromText(text);
            if (fromText) data.email = fromText;
          }
        }
        else if (!data.phone && (href.includes('tel:') || text.match(/^\+?\d/))) data.phone = text;
        else if (!data.telegram && (text.includes('t.me') || text.startsWith('@'))) data.telegram = text;
      });
    }

    // Fallback: generic contact value selectors (older hh.ru layout)
    if (!data.email || !data.phone || !data.telegram) {
      const allContacts = document.querySelectorAll('.resume-contact-value');
      allContacts.forEach(el => {
        const text = el.textContent.trim();
        const link = el.querySelector('a');
        const href = link ? link.href : '';
        if (!data.email && href.includes('mailto:')) {
          // mailto-ссылка надёжнее текста — берём её напрямую.
          data.email = href.replace('mailto:', '').split('?')[0].trim();
        }
        else if (!data.phone && href.includes('tel:')) data.phone = text;
        else if (!data.telegram && (text.includes('t.me') || text.startsWith('@'))) {
          data.telegram = text.replace(/.*t\.me\//, '@');
        }
      });
    }

    // Fallback: scan all links on page for contact info (newest hh.ru layouts)
    if (!data.email || !data.phone || !data.telegram) {
      const allLinks = document.querySelectorAll('a[href]');
      allLinks.forEach(link => {
        const href = link.href || '';
        const text = link.textContent.trim();
        if (!data.email && href.includes('mailto:')) {
          data.email = href.replace('mailto:', '').split('?')[0].trim();
        }
        if (!data.phone && href.includes('tel:') && text.match(/[\+\d]/)) {
          data.phone = text.replace(/\s+/g, ' ').trim();
        }
        if (!data.telegram && href.includes('t.me/') && !href.includes('t.me/share')) {
          const match = href.match(/t\.me\/([^\/?]+)/);
          if (match) data.telegram = '@' + match[1];
        }
      });
    }

    // --- Personal info ---
    // Age - take only the first <span> inside (contains "34 года"), not the whole block
    const ageEl = document.querySelector('[data-qa="resume-personal-age"] > span');
    if (ageEl) data.age = ageEl.textContent.trim();

    // Birthday - direct child span
    const bdEl = document.querySelector('[data-qa="resume-personal-birthday"] > span');
    if (bdEl) data.birthday = bdEl.textContent.trim();
    else data.birthday = getText('[data-qa="resume-personal-birthday"]');

    // Gender - take only own text, not nested children
    const genderEl = document.querySelector('[data-qa="resume-personal-gender"]');
    if (genderEl) {
      // Get only the direct text node (e.g. "Мужчина"), not nested age/birthday
      const firstText = genderEl.childNodes[0];
      data.gender = firstText ? firstText.textContent.trim().replace(/,\s*$/, '') : '';
    }

    // City / Address
    data.city = getText('[data-qa="resume-personal-address"]');

    // --- Salary ---
    const salaryEl = document.querySelector('[data-qa="resume-salary-expectation"] [data-qa="title"]');
    if (salaryEl) {
      data.salary = salaryEl.textContent.trim();
    }

    // --- Experience summary (collect companies + positions) ---
    const experiences = [];
    const expPositions = document.querySelectorAll('[data-qa="resume-block-experience-position"]');
    const expCompanies = document.querySelectorAll('[data-qa="resume-experience-company-title"]');
    const expPeriods = document.querySelectorAll('[data-qa="resume-experience-period"]');

    // Должность бывает в несколько строк, период — «Сен 2025 -⏎сейчас»: без
    // склейки пробелов строка «должность | компания | период» рвалась на куски
    // (сохранённое резюме hh, 22.10.2026).
    const oneLine = (el) => (el?.textContent || '').replace(/\s+/g, ' ').trim();
    for (let i = 0; i < expPositions.length && i < 5; i++) {
      const pos = oneLine(expPositions[i]);
      const company = oneLine(expCompanies[i]);
      const period = oneLine(expPeriods[i]).replace(/\s*-\s*/, ' — ');
      if (pos || company) {
        experiences.push([pos, company, period].filter(Boolean).join(' | '));
      }
      // Extract current/last company
      if (i === 0 && company) {
        data.company = company;
      }
    }
    data.experience_summary = experiences.join('\n');

    // --- Total experience ---
    const expTitle = getText('[data-qa="resume-experience-block-title"] [data-qa="title"]');
    if (expTitle) {
      // e.g. "Опыт работы 12 лет 5 месяцев" or "Опыт работы: 14 лет 1 месяц"
      data.total_experience = expTitle.replace(/Опыт работы:?\s*/, '').trim();
    }

    // --- Experience descriptions (achievements at each job) ---
    const expDescEls = document.querySelectorAll('[data-qa="resume-block-experience-description"]');
    const expDescriptions = [];
    expDescEls.forEach((el, i) => {
      if (i < 3) { // first 3 jobs
        const text = el.textContent.trim();
        if (text) expDescriptions.push(text.substring(0, 500));
      }
    });
    data.experience_descriptions = expDescriptions;

    // --- Skills ---
    const skillsSection = document.querySelector('[data-qa="skills-table"]');
    if (skillsSection) {
      // Skills are in <span> tags inside magritte-card within skills-table
      const card = skillsSection.querySelector('[class*="magritte-card"]');
      if (card) {
        const skillSpans = card.querySelectorAll('span');
        const skills = [];
        skillSpans.forEach(span => {
          const text = span.textContent.trim();
          // Filter: real skills are short-ish text, not UI labels
          if (text && text.length >= 2 && text.length <= 80
              && !span.querySelector('span') // leaf nodes only
              && !text.includes('Свернуть') && !text.includes('Развернуть')) {
            skills.push(text);
          }
        });
        data.skills = [...new Set(skills)]; // deduplicate
      }
    }

    // --- Languages ---
    const langEls = document.querySelectorAll('[data-qa="resume-block-language-item"]');
    const languages = [];
    langEls.forEach(el => {
      const text = el.textContent.trim();
      if (text) languages.push(text);
    });
    data.languages = languages;

    // --- Education ---
    const eduNames = document.querySelectorAll('[data-qa="resume-block-education-name"]');
    const eduOrgs = document.querySelectorAll('[data-qa="resume-block-education-organization"]');
    const education = [];
    for (let i = 0; i < eduOrgs.length && i < 3; i++) {
      const org = eduOrgs[i]?.textContent?.trim() || '';
      const name = eduNames[i]?.textContent?.trim() || '';
      if (org || name) education.push([org, name].filter(Boolean).join(' — '));
    }
    // hh убрал data-qa у пунктов образования (новая разметка magritte): блок
    // `resume-education-block`, внутри — карточки без меток. С прода, 22.10.2026:
    // образование было пустым у ВСЕХ кандидатов из расширения. Берём текст каждой
    // карточки блока строками («Высшее образование», «2015 — МГУ — Журналистика»).
    if (!education.length) {
      const block = document.querySelector('[data-qa="resume-education-block"]');
      if (block) {
        const title = (block.querySelector('[data-qa="resume-education-block-title"]')?.innerText || '').trim();
        let cards = [...block.querySelectorAll('[class*="magritte-card"]')]
          .filter((c) => !c.parentElement.closest('[class*="magritte-card"]'));
        if (!cards.length) cards = [block];
        for (const card of cards) {
          // Строки-разделители «•» и повтор уровня («Высшее образование» стоит
          // и сверху, и в конце пункта) — выкидываем.
          const lines = [...new Set((card.innerText || '').split('\n').map((s) => s.trim())
            .filter((s) => s && s !== title && s !== 'Уровень' && s !== '•' && s.length <= 200))];
          if (lines.length) education.push(lines.join(' — '));
          if (education.length >= 3) break;
        }
      }
    }
    data.education = education;

    // ----- Build a more useful placeholder name when contacts are hidden -----
    // Real name is unknown; build one from what IS visible so each candidate
    // is distinguishable in the kanban and dedup can work by source_url.
    if (rawNameIsPlaceholder) {
      const parts = [];
      if (data.position) parts.push(data.position);
      if (data.city) parts.push(data.city);
      if (data.age) parts.push(data.age);
      if (parts.length > 0) {
        data.full_name = parts.join(', ');
      } else {
        const match = window.location.pathname.match(/\/resume\/([a-f0-9]+)/i);
        const shortId = match ? match[1].slice(0, 8) : '';
        data.full_name = shortId ? `Кандидат ${SITE_HOST}/${shortId}` : `Кандидат ${SITE_HOST}`;
      }
      data.name_is_placeholder = true;
    }

    return data;
  }

  // Parse and send to background
  function runAndSend() {
    let parsed = parseHHResume();
    // Подстраховка единым санитайзером (common.js инжектится первым).
    if (window.__ENC__ && window.__ENC__.sanitizeRecord) parsed = window.__ENC__.sanitizeRecord(parsed);
    console.log('[HR-Bot Magic Button] Parsed resume data:', parsed);
    chrome.runtime.sendMessage({ type: 'PARSE_RESULT', data: parsed });
    return parsed;
  }
  runAndSend();

  // Re-parse on demand (popup нажал 'Добавить ещё')
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg && msg.type === 'RE_PARSE') {
      const fresh = runAndSend();
      sendResponse({ success: true, data: fresh });
    }
  });
})();
