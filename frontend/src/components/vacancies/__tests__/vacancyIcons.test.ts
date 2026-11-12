import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { VACANCY_ICONS } from "../vacancyIcons";
import { DIRECTION_ICONS, vacancyMark } from "../VacancyDirectionIcon";

describe("значок вакансии от ИИ", () => {
  it("список значков совпадает с тем, из которого выбирает сервер", () => {
    const file = resolve(__dirname, "../../../../../backend/api/services/vacancy_icon_names.txt");
    const server = readFileSync(file, "utf-8")
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l && !l.startsWith("#"));
    expect(Object.keys(VACANCY_ICONS).sort()).toEqual([...server].sort());
  });

  it("порядок: выбрано руками → подобрано ИИ под это название → словарь", () => {
    const car = { title: "Car", extra_data: { icon: "car", icon_for: "Car" } };
    expect(vacancyMark(car).Icon).toBe(VACANCY_ICONS.car);
    // Переименовали, а ИИ ещё не пересчитал — старый значок не показываем.
    expect(vacancyMark({ ...car, title: "Video Editor" }).Icon).toBe(DIRECTION_ICONS.video.Icon);
    // Выбор в форме главнее ИИ.
    expect(vacancyMark({ title: "Car", extra_data: { icon: "car", icon_for: "Car", direction: "sales" } }).Icon)
      .toBe(DIRECTION_ICONS.sales.Icon);
    // Значок, которого нет в списке, — как будто его нет.
    expect(vacancyMark({ title: "Car", extra_data: { icon: "nope", icon_for: "Car" } }).Icon)
      .toBe(DIRECTION_ICONS.other.Icon);
  });
});
