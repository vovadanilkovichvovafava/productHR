/**
 * Тексты «Выйти» / «Закрыть» (utils/vacancyExitCopy.ts, 20.10.2026).
 * Раньше «Мои вакансии» и «Заявки» писали правило каждая сама; тексты
 * сверены дословно с прежними версиями страниц.
 */
import { describe, it, expect } from "vitest";
import { vacancyExitCopy } from "../vacancyExitCopy";
import type { Vacancy } from "@/types";

const vac = (over: Partial<Vacancy> = {}) =>
  ({ id: 1, title: "Трафик", created_by: 1, assigned_to: [], extra_data: {}, ...over }) as unknown as Vacancy;

// Я (2) и ещё двое участников.
const shared = vac({ created_by: 1, assigned_to: [2, 3] });
// Я — единственный участник.
const solo = vac({ created_by: 2, assigned_to: [] });

describe("vacancyExitCopy — только вопрос, без пояснений (владелец 20.10.2026)", () => {
  it("выйти", () => {
    expect(vacancyExitCopy("leave", shared, 2, "vacancy")).toEqual({
      title: "Вы действительно хотите выйти из вакансии?", text: "", confirmLabel: "Выйти",
    });
    expect(vacancyExitCopy("leave", shared, 2, "request").title).toBe("Вы действительно хотите выйти из заявки?");
  });

  it("закрыть общую — «для всех», в том числе админу, который сам её не ведёт", () => {
    for (const userId of [2, 99]) {
      expect(vacancyExitCopy("close", shared, userId, "vacancy")).toEqual({
        title: "Вы действительно хотите закрыть вакансию для всех?", text: "", confirmLabel: "Закрыть для всех",
      });
    }
    expect(vacancyExitCopy("close", shared, 2, "request").title).toBe("Вы действительно хотите закрыть заявку для всех?");
  });

  it("закрыть, где я один, — без «для всех»", () => {
    expect(vacancyExitCopy("close", solo, 2, "vacancy")).toEqual({
      title: "Вы действительно хотите закрыть вакансию?", text: "", confirmLabel: "Закрыть",
    });
    expect(vacancyExitCopy("close", solo, 2, "request").title).toBe("Вы действительно хотите закрыть заявку?");
  });

  it("тот, кто «закрыл у себя», участником не считается", () => {
    const v = vac({ created_by: 1, assigned_to: [2, 3], extra_data: { dismissed_by: [1, 3] } });
    expect(vacancyExitCopy("close", v, 2, "vacancy").confirmLabel).toBe("Закрыть");
  });
});
