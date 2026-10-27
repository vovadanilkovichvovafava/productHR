(function () {
  if (window.__hr_bot_habr_loaded__) return;
  window.__hr_bot_habr_loaded__ = true;

  const E = window.__ENC__ || {};

  function txt(sel) {
    const el = document.querySelector(sel);
    return el ? el.textContent.replace(/\s+/g, ' ').trim() : '';
  }

  // --- Маппинг встроенного JSON-профиля Habr (структура: skills[], age,
  // experience, location, salary, contacts.items[]). Узел ищем эвристикой. ---
  function findProfileNode(j) {
    const stack = [j]; let steps = 0;
    while (stack.length && steps < 20000) {
      steps++;
      const cur = stack.pop();
      if (cur && typeof cur === 'object' && !Array.isArray(cur)) {
        const k = Object.keys(cur);
        if ((k.includes('skills') && k.includes('experience')) ||
            (k.includes('age') && k.includes('location'))) return cur;
        for (const key of k) { const v = cur[key]; if (v && typeof v === 'object') stack.push(v); }
      } else if (Array.isArray(cur)) {
        for (const v of cur) if (v && typeof v === 'object') stack.push(v);
      }
    }
    return null;
  }

  // Узел с местами работы — он НЕ внутри профильного /user, а под /resume.
  function findCompanies(j) {
    const stack = [j]; let steps = 0;
    while (stack.length && steps < 20000) {
      steps++;
      const cur = stack.pop();
      if (cur && typeof cur === 'object' && !Array.isArray(cur)) {
        if (cur.companies && cur.companies.items) return cur.companies;
        for (const key of Object.keys(cur)) { const v = cur[key]; if (v && typeof v === 'object') stack.push(v); }
      } else if (Array.isArray(cur)) {
        for (const v of cur) if (v && typeof v === 'object') stack.push(v);
      }
    }
    return null;
  }

  function mapJson(j, data) {
    const n = findProfileNode(j);
    if (n) {
      if (!data.full_name && typeof n.title === 'string') data.full_name = n.title;
      // Должность: специализация ИЛИ роли из divisions[] (на многих профилях
      // specialization=null, а реальная роль лежит в divisions — напр.
      // «Менеджер проекта», «Менеджер по маркетингу»), затем грейд/квалификация.
      const spec = n.specialization && (typeof n.specialization === 'string' ? n.specialization : (n.specialization.title || ''));
      const qual = typeof n.qualification === 'string' ? n.qualification : (n.qualification && n.qualification.title || '');
      let roles = [];
      if (spec) roles = [spec];
      else if (Array.isArray(n.divisions)) roles = n.divisions.map(d => d && (d.title || d.name)).filter(Boolean);
      const pos = [roles.join(' / '), qual].filter(Boolean).join(' · ');
      if (pos && !data.position) data.position = pos;
      if (n.age != null) data.age = typeof n.age === 'string' ? n.age : String(n.age);
      if (n.location) data.city = typeof n.location === 'string' ? n.location : (n.location.title || '');
      if (n.experience != null) data.total_experience = typeof n.experience === 'string' ? n.experience : String(n.experience);
      if (Array.isArray(n.skills)) data.skills = n.skills.map(s => (s && (s.title || s.name)) || s).filter(v => typeof v === 'string');
      // Языки: foreignLanguages[] = [{title:"Английский С1"}, …]. Без этого
      // языки на Habr не приезжали (отдельной DOM-секции часто нет).
      if (Array.isArray(n.foreignLanguages) && !data.languages.length) {
        data.languages = n.foreignLanguages.map(l => (l && (l.title || l.name)) || l).filter(v => typeof v === 'string');
      }
      if (n.salary) data.salary = typeof n.salary === 'string' ? n.salary : (n.salary.amount ? (n.salary.amount + ' ' + (n.salary.currency || '')) : '');
      const items = n.contacts && n.contacts.items;
      if (Array.isArray(items)) items.forEach(c => {
        const kind = String(c.kind || c.type || '').toLowerCase();
        const val = c.value && (typeof c.value === 'string' ? c.value : (c.value.title || c.value.href)) || '';
        if (!val || typeof val !== 'string') return;
        if (/phone/.test(kind) && !data.phone) data.phone = val;
        else if (/telegram/.test(kind) && !data.telegram) data.telegram = val;
        else if (/mail/.test(kind) && !data.email) data.email = val;
      });
    }
    // Опыт работы: companies.items[].positions[] (title компании + должность + период).
    const companies = findCompanies(j);
    if (companies && Array.isArray(companies.items)) {
      const exp = [];
      companies.items.slice(0, 6).forEach(co => {
        const comp = (co && co.title) || '';
        ((co && co.positions) || []).forEach(p => {
          const parts = [p && p.title, comp, p && p.duration].filter(Boolean);
          if (parts.length) exp.push(parts.join(' | '));
        });
      });
      if (exp.length) {
        if (!data.experience_summary) data.experience_summary = exp.join('\n');
        if (!data.company && companies.items[0]) data.company = companies.items[0].title || '';
      }
    }
  }

  function parseHabr() {
    const data = {
      source: 'career.habr.com', source_url: window.location.href,
      full_name: '', email: '', phone: '', telegram: '', position: '',
      city: '', company: '', salary: '', age: '', gender: '',
      summary: '',
      experience_summary: '', experience_descriptions: [], total_experience: '', skills: [], languages: [], education: [],
    };

    // 1) JSON-остров (если есть) — чистые структурированные данные.
    if (E.extractProfileJson) {
      const pj = E.extractProfileJson(['skills', 'experience']) || E.extractProfileJson(['age', 'location']);
      if (pj) { try { mapJson(pj, data); } catch (e) { console.warn('[HR-Bot] Habr JSON map failed', e); } }
    }

    // 2) DOM — ТОЛЬКО точечные селекторы (никаких широких [class*=...]).
    if (!data.full_name) data.full_name = txt('.page-title__title') || txt('h1');
    if (!data.position) data.position = txt('.page-title__subtitle') || txt('.user-spec__title');
    if (!data.city) data.city = txt('.basic-section__location');
    if (!data.salary) data.salary = txt('.basic-section__salary');
    if (!data.age) data.age = txt('.basic-section__age');

    // --- Секции резюме Habr Career (актуальная вёрстка .content-section) ---
    // innerText, а не textContent: textContent склеивает соседние блоки без
    // пробела — «СПбГЭУСанкт-Петербург», «Telegram: @nickСсылка на резюме»
    // (сохранённый профиль, 22.10.2026).
    const clean = (el) => el ? (el.innerText || el.textContent || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim() : '';

    // Боковая колонка профиля: строки «Возраст: 32 года», «Опыт работы: 8 лет и
    // 6 месяцев», «Местоположение: Россия, Москва», «Зарплата: от …». Отдельных
    // классов у них нет — берём по подписи. Раньше город, стаж и возраст были
    // пустыми у всех кандидатов с Хабра.
    const sideLines = clean(document.querySelector('.user-page-sidebar')).split('\n').map((l) => l.trim());
    const sideValue = (re) => {
      const line = sideLines.find((l) => re.test(l));
      return line ? line.replace(re, '').replace(/^[:\s]+/, '').trim() : '';
    };
    if (!data.age) data.age = sideValue(/^Возраст/i);
    if (!data.total_experience) data.total_experience = sideValue(/^Опыт работы/i);
    if (!data.city) {
      const loc = sideValue(/^Местоположение/i);
      // «Россия, Москва» → «Москва» (город — последняя часть).
      data.city = loc.split(',').map((x) => x.trim()).filter(Boolean).pop() || '';
    }
    if (!data.salary) data.salary = sideValue(/^(Желаемая )?зарплата/i);
    // Специализации «Аналитик • Аналитик по данным • Старший (Senior)» —
    // запасная должность, если мест работы нет.
    const specLine = clean(document.querySelector('.user-page-sidebar__meta'));
    const sectionEl = (re) => {
      for (const s of document.querySelectorAll('.content-section')) {
        const t = s.querySelector('.content-section__title');
        if (t && re.test(t.textContent || '')) return s;
      }
      return null;
    };

    // «Обо мне» → summary (самоописание кандидата).
    if (!data.summary) {
      const ab = sectionEl(/Обо мне|О себе/i);
      if (ab) data.summary = clean(ab.querySelector('.style-ugc')) || '';
    }

    // Опыт работы: заголовки (должность | компания | период) + ПОЛНЫЕ описания
    // (.job-position__message). Старые .experience-section__item больше не работают —
    // Habr перешёл на .job-experience-item / .job-position.
    const expHeaders = [];
    let firstTitle = '';
    document.querySelectorAll('.job-experience-item').forEach((job, i) => {
      if (i >= 8) return;
      // Только название-ссылка компании: рядом в шапке её оценка («3.9»), и
      // раньше выходило «Яндекс Практикум3.9».
      const companyLink = job.querySelector('.job-experience-item__header a.link-comp, .job-experience-item__header a');
      const company = (clean(companyLink) || clean(job.querySelector('.job-experience-item__header')) || '').split('\n')[0].trim();
      if (i === 0 && company && !data.company) data.company = company;
      job.querySelectorAll('.job-position').forEach((p) => {
        const title = clean(p.querySelector('.job-position__title'));
        const dur = clean(p.querySelector('.job-position__duration'));
        const msg = clean(p.querySelector('.job-position__message'));
        if (!firstTitle && title) firstTitle = title;
        const head = [title, company, dur.replace(/\s+/g, ' ')].filter(Boolean).join(' | ');
        if (head) expHeaders.push(head);
        if (msg) data.experience_descriptions.push((head ? head + '\n' : '') + msg);
      });
    });
    // старая вёрстка как fallback
    if (!expHeaders.length) {
      document.querySelectorAll('.experience-section__item, .resume-experience__item').forEach((b, i) => {
        if (i >= 6) return;
        const pos = b.querySelector('.experience-section__title, .resume-experience__title, h3');
        const comp = b.querySelector('.experience-section__company, a[href*="/companies/"]');
        const per = b.querySelector('.experience-section__period, .resume-experience__period');
        const parts = [pos, comp, per].map((x) => clean(x)).filter(Boolean);
        if (parts.length) { expHeaders.push(parts.join(' | ')); if (i === 0 && comp && !data.company) data.company = clean(comp); }
      });
    }
    if (expHeaders.length && expHeaders.join('\n').length > data.experience_summary.length) {
      data.experience_summary = expHeaders.join('\n');
    }
    // Должность — текущее место работы (как у LinkedIn), иначе специализации без
    // грейда. До 22.10.2026 у сохранённого профиля должность была пустой.
    if (!data.position) {
      data.position = firstTitle || specLine.split('•').map((x) => x.trim())
        .filter((x) => x && !/^(Младший|Средний|Старший|Ведущий|Стажёр|Junior|Middle|Senior|Lead)/i.test(x))
        .slice(0, 2).join(' / ');
    }

    // Образование (Высшее + Дополнительное).
    if (!data.education.length) {
      const edus = [];
      ['Высшее образование', 'Дополнительное образование', 'Образование'].forEach((t) => {
        const s = sectionEl(new RegExp(t, 'i'));
        // По пункту на учебное заведение: «СПбГЭУ — Санкт-Петербург — Факультет
        // экономики — Сентябрь 2012 — Июль 2016». Служебное «1759 выпускников» и
        // разделители «•» выкидываем; описание курса (длинные строки) не берём.
        (s ? s.querySelectorAll('.resume-education-item') : []).forEach((item) => {
          // Без ссылок на сертификаты и строк-тегов «SQL • Python • …»: только
          // заведение, программа и период.
          const lines = clean(item).split('\n').map((l) => l.trim())
            .filter((l) => l && l !== '•' && !/выпускник/i.test(l) && !/^https?:/i.test(l)
              && !/\s•\s/.test(l) && l.length <= 120);
          const x = [...new Set(lines)].slice(0, 3).join(' — ');
          if (x) edus.push(x);
        });
      });
      if (edus.length) data.education = [...new Set(edus)];
    }

    // Языки.
    if (!data.languages.length) {
      const s = sectionEl(/язык/i);
      if (s) {
        const body = [...s.children].find((c) => !c.classList.contains('content-section__header'));
        const t = clean(body);
        if (t) data.languages = [t];
      }
    }

    // Навыки: актуальная секция .skills-list-show + старые селекторы.
    if (!data.skills.length) {
      const sk = new Set();
      const skSec = sectionEl(/Навыки/i);
      if (skSec) skSec.querySelectorAll('.skills-list-show a, .skills-list-show span, a[href*="/resumes?skills"]').forEach((el) => {
        const t = clean(el); if (t && t.length >= 2 && t.length <= 60 && !/^\d+$/.test(t)) sk.add(t);
      });
      document.querySelectorAll('a[href*="/resumes?skills"], .user-skills__item').forEach((el) => {
        const t = clean(el); if (t && t.length >= 2 && t.length <= 60) sk.add(t);
      });
      data.skills = [...sk].slice(0, 40);
    }

    // Контакты — из ссылок mailto/tel/t.me. Ссылки на каналы самого Хабра
    // (t.me/habr…) — не кандидат: раньше такая ссылка занимала поле, санитайзер
    // её выкидывал, и Telegram из «О себе» уже не подставлялся (22.10.2026).
    document.querySelectorAll('a[href]').forEach(a => {
      const href = a.href || '';
      if (!data.email && href.startsWith('mailto:')) data.email = href.slice(7).split('?')[0];
      if (!data.phone && href.startsWith('tel:')) data.phone = href.slice(4);
      if (!data.telegram && href.includes('t.me/') && !/t\.me\/(habr|share|joinchat)/i.test(href)) data.telegram = href;
    });

    // Контакты, вписанные в «О себе» («Telegram: @nick», почта текстом), — у
    // профиля без входа блок контактов размыт, а это единственное, что видно.
    if (data.summary) {
      const tg = data.summary.match(/(?:telegram|телеграм|tg)\s*[:\-–]?\s*@?([A-Za-z0-9_]{5,32})\b/i)
        || data.summary.match(/t\.me\/([A-Za-z0-9_]{5,32})/i);
      if (!data.telegram && tg) data.telegram = '@' + tg[1];
      const em = data.summary.match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/);
      if (!data.email && em) data.email = em[0];
    }

    if (!data.full_name) {
      const m = window.location.pathname.match(/career\.habr\.com\/([^/?#]+)/) || window.location.pathname.match(/\/([^/?#]+)$/);
      data.full_name = m ? 'Habr: ' + decodeURIComponent(m[1]) : 'Кандидат Habr';
      data.name_is_placeholder = true;
    }
    return data;
  }

  function runAndSend() {
    let data = parseHabr();
    if (E.sanitizeRecord) data = E.sanitizeRecord(data);
    console.log('[HR-Bot Magic Button] Habr parsed:', data);
    chrome.runtime.sendMessage({ type: 'PARSE_RESULT', data });
    return data;
  }
  runAndSend();

  chrome.runtime.onMessage.addListener((msg, _s, sendResponse) => {
    if (msg && msg.type === 'RE_PARSE') { sendResponse({ success: true, data: runAndSend() }); }
  });
})();
