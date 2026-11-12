import { describe, expect, it } from "vitest";
import { resolveVacancyDirection, vacancyDirection } from "../vacancyDirection";

describe("направление вакансии по названию (значок в левой панели)", () => {
  it.each([
    // названия открытых вакансий прода (12.11.2026)
    ["Трафик (тест)", "traffic"],
    ["Head of User Acquisition", "traffic"],
    ["User Acquisition Manager", "traffic"],
    ["Video Editor", "video"],
    ["UGC-продюсер", "video"],
    ["Creative Production Manager", "design"],
    ["Аналитик данных (тест)", "analytics"],
    ["Product Analyst (Monetization)", "analytics"],
    ["Сорсер", "recruiting"],
    ["Billing Manager", "finance"],
    ["Персональный ассистент", "support"],
    ["Growth Manager", "growth"],
    ["Продажи B2B (тест)", "sales"],
    ["C P", "other"],
    ["Car", "other"],
    ["Машина", "other"],
    // расширенный словарь
    ["Медиабайер", "traffic"],
    ["Баер Facebook", "traffic"],
    ["Маркетолог", "traffic"],
    ["SEO-специалист", "traffic"],
    ["Таргетолог", "traffic"],
    ["Motion designer", "video"],
    ["Монтажёр", "video"],
    ["Продюсер YouTube", "video"],
    ["Графический дизайнер", "design"],
    ["Product Designer", "design"],
    ["UX/UI дизайнер", "design"],
    ["Контент-менеджер", "content"],
    ["SMM-менеджер", "content"],
    ["Копирайтер", "content"],
    ["Data Scientist", "analytics"],
    ["Python-разработчик", "dev"],
    ["Frontend developer", "dev"],
    ["QA-инженер", "dev"],
    ["Тимлид бэкенда", "dev"],
    ["DevOps", "dev"],
    ["HR-менеджер", "recruiting"],
    ["Рекрутер", "recruiting"],
    ["Юрист", "legal"],
    ["Бухгалтер", "finance"],
    ["Антифрод-аналитик", "analytics"],
    ["Оператор поддержки", "support"],
    ["Customer Success Manager", "support"],
    ["Офис-менеджер", "support"],
    ["Retention-маркетолог", "traffic"],
    ["CRM-менеджер", "growth"],
    ["Менеджер по продажам", "sales"],
    ["Account Manager", "sales"],
    ["Project Manager", "management"],
    ["Операционный директор", "management"],
    ["Руководитель отдела", "management"],
  ])("%s → %s", (title, dir) => {
    expect(vacancyDirection(title)).toBe(dir);
  });

  it("слова внутри других слов не срабатывают", () => {
    // «рост» внутри «простой», «лид» внутри «валидатор»
    expect(vacancyDirection("Простой стажёр")).toBe("other");
    expect(vacancyDirection("Валидатор")).toBe("other");
  });

  it("смотрит и на отдел, если по названию не понятно", () => {
    expect(vacancyDirection("Стажёр", "Отдел разработки")).toBe("dev");
  });

  it("выбранное в форме главнее угаданного; мусор — игнорируем", () => {
    expect(resolveVacancyDirection({ title: "Car", extra_data: { direction: "video" } })).toBe("video");
    expect(resolveVacancyDirection({ title: "Video Editor", extra_data: { direction: "nope" } })).toBe("video");
    expect(resolveVacancyDirection({ title: "Car", extra_data: null })).toBe("other");
  });
});
