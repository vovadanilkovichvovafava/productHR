// Направление вакансии для значка в левой панели (владелец, 12.11.2026:
// карточки вакансий «не монотонные», вариант «значок направления»).
//
// Направление можно выбрать в форме вакансии (`extra_data.direction`);
// не выбрано — угадываем по словам в названии и отделе. Порядок правил
// важен: «Head of User Acquisition» — это трафик, а не руководство; «Billing
// Manager» — финансы; «Content manager» — контент. Не узнали — нейтральная
// папка. Всё считается в браузере: десяток регулярок на вакансию, нагрузки нет.
//
// В регулярках \b — только у латиницы: в JS граница слова не понимает
// кириллицу, и «\bпм» не сработал бы никогда.

export type VacancyDirection =
  | "traffic"
  | "video"
  | "design"
  | "content"
  | "analytics"
  | "dev"
  | "recruiting"
  | "legal"
  | "finance"
  | "support"
  | "growth"
  | "sales"
  | "management"
  | "other";

const RULES: ReadonlyArray<[VacancyDirection, RegExp]> = [
  ["traffic", new RegExp([
    "трафик", "traffic", "арбитраж", "arbitrage", "медиа ?ба[йе]", "media ?buy", "ба[йе]ер", "\\bbuyer",
    "таргет", "\\btarget", "\\bppc\\b", "\\bads\\b", "google ads", "facebook", "\\bfb\\b", "tiktok", "тикток",
    "user acquisition", "\\bua\\b", "закупк", "\\bseo\\b", "сео", "\\bsem\\b", "\\baso\\b", "\\bcpa\\b", "\\bcpl\\b",
    "affiliate", "аффилиат", "партн[её]рск(ая|ой|их) программ", "контекст", "performance", "перфоманс",
    "маркетолог", "marketing", "маркетинг", "in-?app", "apple search", "\\bpush\\b", "пуш",
    "influenc", "инфлюенс", "посев", "telegram ads", "tg ads", "лидоген", "lead ?gen", "retarget", "ретаргет",
    "programmatic", "\\bdsp\\b", "\\bsmm-?таргет",
  ].join("|"))],
  ["video", new RegExp([
    "видео", "video", "монтаж", "motion", "моушн", "\\bugc\\b", "ugc-", "клип", "reels", "рилс", "shorts",
    "youtube", "ютуб", "аниматор", "animator", "анимац", "animation", "\\b3d\\b", "3d-", "after effects",
    "premiere", "съ[её]мк", "режисс[её]р", "продюсер", "producer", "оператор-постановщик", "видеограф",
    "videograph", "сторисмейкер", "stories ?maker", "movie", "\\bfilm", "фильм", "(^|[^а-я])кино",
    "cinema", "кинемат", "ролик", "trailer", "трейлер", "\\bvfx\\b", "cgi", "стрим", "stream",
  ].join("|"))],
  ["design", new RegExp([
    "дизайн", "design", "\\bux\\b", "\\bui\\b", "ux/ui", "ui/ux", "креатив", "creative", "иллюстрат",
    "illustrat", "figma", "график", "graphic", "арт-директор", "art director", "брендинг", "branding",
    "веб-дизайн", "верстк[аи] макет",
  ].join("|"))],
  ["content", new RegExp([
    "контент", "content", "копирайт", "copywrit", "\\bcopy\\b", "\\bsmm\\b", "смм", "social media",
    "соцсет", "редактор", "editor", "писател", "writer", "сценарист", "script", "журналист", "journalist",
    "блог", "blog", "переводчик", "translator", "локализ", "localiz", "community", "комьюнити",
    "модератор", "moderator", "\\bpr\\b", "пиар", "пресс", "press",
  ].join("|"))],
  ["analytics", new RegExp([
    "аналитик", "analyst", "analytics", "\\bdata\\b", "данных", "\\bbi\\b", "power bi", "tableau",
    "\\bsql\\b", "data scien", "machine learning", "\\bml\\b", "машинн(ое|ого) обучен", "исследовател",
    "researcher", "research", "ресерч",
  ].join("|"))],
  ["dev", new RegExp([
    "разработ", "developer", "\\bdev\\b", "программ", "software", "\\bswe\\b", "python", "java", "kotlin",
    "swift", "flutter", "react", "\\bvue\\b", "angular", "node", "typescript", "javascript", "\\bjs\\b",
    "frontend", "front-end", "фронтенд", "backend", "back-end", "бэкенд", "бекенд", "fullstack", "full-stack",
    "фулстек", "\\bios\\b", "android", "golang", "\\bgo\\b", "\\bphp\\b", "ruby", "rust", "c\\+\\+", "c#",
    "\\.net", "1с", "\\b1c\\b", "битрикс", "bitrix", "wordpress", "верстальщ", "\\bhtml\\b", "\\bqa\\b",
    "тестировщ", "автотест", "\\btester\\b", "devops", "\\bsre\\b", "сисадмин", "sysadmin",
    "системн(ый|ого) администратор", "engineer", "инженер", "architect", "архитектор", "техлид",
    "tech ?lead", "\\bcto\\b", "security", "безопасност", "pentest", "blockchain", "блокчейн", "web3",
    "smart contract", "unity", "unreal", "gamedev", "геймдев",
  ].join("|"))],
  ["recruiting", new RegExp([
    "сорсер", "sourc", "рекрут", "recruit", "\\bhr\\b", "hr-", "эйчар", "подбор", "кадр", "talent",
    "\\bhrbp\\b", "hr bp", "people partner", "people ops", "онбординг", "onboarding", "хедхант",
    "headhunt",
  ].join("|"))],
  ["legal", new RegExp([
    "юрист", "lawyer", "legal", "юридич", "compliance", "комплаенс", "адвокат", "attorney", "нотари",
  ].join("|"))],
  ["finance", new RegExp([
    "billing", "биллинг", "финанс", "financ", "бухгалт", "accountant", "accounting", "платеж", "платёж",
    "payment", "казнач", "treasur", "экономист", "economist", "\\bcfo\\b", "финдир", "антифрод",
    "antifraud", "\\bfraud\\b", "фрод", "\\brisk", "риск", "аудит", "audit", "налог", "\\btax\\b",
  ].join("|"))],
  ["support", new RegExp([
    "ассистент", "assistant", "помощник", "поддержк", "support", "саппорт", "оператор", "колл-центр",
    "call ?cent", "customer success", "клиентск(ого|ий) (сервис|поддерж)", "секретар", "secretary",
    "офис-менеджер", "office manager", "администратор", "reception", "ресепшн", "консультант",
    "чат-менеджер", "\\bva\\b",
  ].join("|"))],
  ["growth", new RegExp([
    "growth", "(^|[^а-я])рост", "monetiz", "монетиз", "retention", "ретеншн", "\\bcrm\\b", "lifecycle", "\\bltv\\b",
    "конверс", "conversion", "\\bcro\\b",
  ].join("|"))],
  ["sales", new RegExp([
    "продаж", "продавец", "sales", "\\bb2b\\b", "\\bb2c\\b", "аккаунт", "account manager",
    "account executive", "key account", "business development", "бизнес-девелоп", "biz ?dev",
    "по работе с клиентами", "партн[её]рств", "partnership", "дилер", "торгов", "закупщик", "procurement",
    "менеджер по развитию",
  ].join("|"))],
  ["management", new RegExp([
    "head", "\\blead\\b", "(^|[^а-я])лид([^а-я]|$)", "руковод", "директор", "director", "manager", "менеджер", "product",
    "продакт", "project", "проджект", "\\bpm\\b", "\\bpo\\b", "\\bcpo\\b", "\\bceo\\b", "\\bcoo\\b",
    "\\bcmo\\b", "chief", "founder", "основател", "operations", "операционн", "\\bops\\b", "scrum",
    "agile", "delivery", "тимлид", "team ?lead", "супервайзер", "supervisor", "координатор",
    "coordinator", "управляющ",
  ].join("|"))],
];

/** Порядок в форме вакансии. */
export const DIRECTION_ORDER: readonly VacancyDirection[] = [
  "traffic", "video", "design", "content", "analytics", "dev", "recruiting",
  "legal", "finance", "support", "growth", "sales", "management", "other",
];

export function isVacancyDirection(value: unknown): value is VacancyDirection {
  return typeof value === "string" && (DIRECTION_ORDER as readonly string[]).includes(value);
}

/** Угадать направление по названию и отделу. */
export function vacancyDirection(title: string, department?: unknown): VacancyDirection {
  const text = `${title || ""} ${typeof department === "string" ? department : ""}`
    .toLowerCase()
    .replace(/ё/g, "е");
  for (const [dir, re] of RULES) {
    if (re.test(text)) return dir;
  }
  return "other";
}

/** Направление вакансии: выбранное в форме главнее угаданного. */
export function resolveVacancyDirection(v: {
  title: string;
  extra_data?: Record<string, unknown> | null;
}): VacancyDirection {
  const chosen = v.extra_data?.direction;
  if (isVacancyDirection(chosen)) return chosen;
  return vacancyDirection(v.title, v.extra_data?.department);
}

export const DIRECTION_LABELS: Record<VacancyDirection, string> = {
  traffic: "Трафик и маркетинг",
  video: "Видео",
  design: "Дизайн",
  content: "Контент",
  analytics: "Аналитика",
  dev: "Разработка",
  recruiting: "Подбор (HR)",
  legal: "Юристы",
  finance: "Финансы",
  support: "Поддержка и ассистенты",
  growth: "Рост и монетизация",
  sales: "Продажи",
  management: "Менеджмент",
  other: "Другое",
};
