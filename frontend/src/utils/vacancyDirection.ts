// Направление вакансии для значка в левой панели (владелец, 12.11.2026:
// карточки вакансий «не монотонные», вариант «значок направления»).
//
// Отдельного поля «направление» у вакансии нет — угадываем по словам в
// названии и отделе. Порядок правил важен: «Head of User Acquisition» — это
// трафик, а не руководство; «Billing Manager» — финансы; «Content manager» —
// контент. Не узнали — нейтральная папка.

export type VacancyDirection =
  | "traffic"
  | "design"
  | "video"
  | "content"
  | "dev"
  | "analytics"
  | "recruiting"
  | "finance"
  | "support"
  | "growth"
  | "sales"
  | "management"
  | "other";

const RULES: ReadonlyArray<[VacancyDirection, RegExp]> = [
  ["traffic", /трафик|арбитраж|медиа ?ба[йе]|media ?buy|таргет|target|\bppc\b|\bads?\b|ads\b|user acquisition|\bua\b|закупк|seo|\bcpa\b|affiliate|аффилиат/],
  ["video", /видео|video|монтаж|motion|моушн|ugc|клип|reels/],
  ["design", /дизайн|design|\bux\b|\bui\b|креатив|creative|иллюстрат|figma/],
  ["content", /контент|content|копирайт|copywrit|\bsmm\b|редактор|писател|writer|сценарист/],
  ["analytics", /аналитик|analyst|analytics|data|данных|\bbi\b/],
  ["dev", /разработ|developer|\bdev\b|программ|python|java|frontend|backend|fullstack|front-end|back-end|\bqa\b|тестировщ|devops|engineer|инженер|\bios\b|android|golang|\bphp\b|react/],
  ["recruiting", /сорсер|sourc|рекрут|recruit|\bhr\b|подбор|кадр/],
  ["finance", /billing|биллинг|финанс|financ|бухгалт|account(ant|ing)|платеж|payment|казнач/],
  ["support", /ассистент|assistant|поддержк|support|оператор|саппорт|секретар|офис-менедж/],
  ["growth", /growth|рост|monetiz|монетиз|retention|ретеншн/],
  ["sales", /продаж|sales|b2b|аккаунт-менедж|account manager|business development|бизнес-девелоп/],
  ["management", /head|lead|лид|руковод|директор|director|manager|менеджер|product|продакт|project|проджект|\bpm\b|\bcpo\b|\bcto\b|\bceo\b/],
];

export function vacancyDirection(title: string, department?: unknown): VacancyDirection {
  const text = `${title || ""} ${typeof department === "string" ? department : ""}`
    .toLowerCase()
    .replace(/ё/g, "е");
  for (const [dir, re] of RULES) {
    if (re.test(text)) return dir;
  }
  return "other";
}

export const DIRECTION_LABELS: Record<VacancyDirection, string> = {
  traffic: "Трафик и маркетинг",
  design: "Дизайн",
  video: "Видео",
  content: "Контент",
  dev: "Разработка",
  analytics: "Аналитика",
  recruiting: "Подбор",
  finance: "Финансы",
  support: "Поддержка и ассистенты",
  growth: "Рост и монетизация",
  sales: "Продажи",
  management: "Менеджмент",
  other: "Вакансия",
};
