import { describe, expect, it } from "vitest";
import { vacancyDirection } from "../vacancyDirection";

describe("направление вакансии по названию (значок в левой панели)", () => {
  it.each([
    ["Трафик (тест)", "traffic"],
    ["Head of User Acquisition", "traffic"],
    ["User Acquisition Manager", "traffic"],
    ["Медиабайер", "traffic"],
    ["Video Editor", "video"],
    ["UGC-продюсер", "video"],
    ["Creative Production Manager", "design"],
    ["Product Designer", "design"],
    ["Контент-менеджер", "content"],
    ["Аналитик данных (тест)", "analytics"],
    ["Product Analyst (Monetization)", "analytics"],
    ["Python-разработчик", "dev"],
    ["Сорсер", "recruiting"],
    ["Billing Manager", "finance"],
    ["Персональный ассистент", "support"],
    ["Growth Manager", "growth"],
    ["Project Manager", "management"],
    ["Продажи B2B (тест)", "sales"],
    ["C P", "other"],
  ])("%s → %s", (title, dir) => {
    expect(vacancyDirection(title)).toBe(dir);
  });

  it("смотрит и на отдел, если по названию не понятно", () => {
    expect(vacancyDirection("Стажёр", "Отдел разработки")).toBe("dev");
  });
});
