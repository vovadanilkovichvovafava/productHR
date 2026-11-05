import { describe, it, expect } from "vitest";
import { clearedValue } from "../EditCandidateModal";

// 05.11.2026: стёр текст резюме целиком — «Кандидат обновлён», а текст на
// месте. Пустое поле не уходило на сервер, и он оставлял старое значение.
describe("clearedValue — что окно «Редактировать» шлёт за пустое поле", () => {
  it("было заполнено, стало пустым → null (стереть)", () => {
    expect(clearedValue("РЕЗЮМЕ | РЕЗЮМЕ", "")).toBeNull();
    expect(clearedValue("Минск", "   ")).toBeNull();
  });
  it("пусто с самого начала → не шлём (в базе может быть производное значение)", () => {
    expect(clearedValue("", "")).toBeUndefined();
  });
  it("поле не пустое → решает само значение, не этот помощник", () => {
    expect(clearedValue("Минск", "Гродно")).toBeUndefined();
  });
});
