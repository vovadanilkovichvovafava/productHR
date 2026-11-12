import { describe, expect, it } from "vitest";
import { rotationNote } from "../StatusesPage";

// Ротации в ячейке «Отдел»: видно ОТКУДА и КОГДА, без перегруза (Мария,
// 05.11.2026; «откуда и куда + дата перехода» — 12.11.2026).
describe("rotationNote", () => {
  it("ротаций не было — подписи нет", () => {
    expect(rotationNote(undefined, "SEO")).toBeNull();
    expect(rotationNote([], "SEO")).toBeNull();
  });

  it("одна ротация — откуда и дата перехода, путь целиком в шагах", () => {
    const note = rotationNote(
      [{ department_id: 1, name: "Продукт", date_from: "2026-08-12", date_to: "2026-10-03" }],
      "Байер FB",
    )!;
    expect(note.short).toBe("из Продукт · 3/10/26");
    expect(note.steps).toEqual([
      { name: "Продукт", when: "12/8/26 – 3/10/26", kind: "past" },
      { name: "Байер FB", when: "с 3/10/26 · сейчас", kind: "current" },
    ]);
    expect(note.title).toContain("→ Байер FB · с 3/10/26 · сейчас");
  });

  it("несколько — последний прежний, «ещё N», старые идут первыми", () => {
    const note = rotationNote(
      [
        { department_id: 1, name: "Продукт", date_from: null, date_to: "2026-09-01" },
        { department_id: 2, name: "Байер FB", date_from: "2026-09-01", date_to: "2026-10-01" },
      ],
      "SEO",
    )!;
    expect(note.short).toBe("из Байер FB · 1/10/26 · ещё 1");
    expect(note.steps.map((s) => s.name)).toEqual(["Продукт", "Байер FB", "SEO"]);
    expect(note.steps[0].when).toBe("до 1/9/26");
  });

  it("песочница — первым шагом и входит в «ещё N»: ничего не прячем", () => {
    const note = rotationNote(
      [{ department_id: 2, name: "HR team", date_from: "2026-09-01", date_to: "2026-10-16" }],
      "SEO team",
      "SANDBOX traffic",
    )!;
    expect(note.short).toBe("из HR team · 16/10/26 · ещё 1");
    expect(note.steps[0]).toEqual({ name: "SANDBOX traffic", when: "практика", kind: "sandbox" });
    expect(note.steps.at(-1)?.kind).toBe("current");
  });

  it("вернулся в тот же отдел (ошибочный отдел между ними удалён) — подписи нет", () => {
    expect(rotationNote(
      [{ department_id: 10, name: "SEO team", date_from: "2026-11-04", date_to: "2026-11-11" }],
      "SEO team",
    )).toBeNull();
  });

  it("настоящий возврат после другого отдела — подпись про тот отдел", () => {
    const note = rotationNote(
      [
        { department_id: 10, name: "SEO team", date_from: null, date_to: "2026-09-01" },
        { department_id: 2, name: "Продукт", date_from: "2026-09-01", date_to: "2026-10-01" },
      ],
      "SEO team",
    )!;
    expect(note.short).toBe("из Продукт · 1/10/26 · ещё 1");
  });
});
