import { describe, expect, it } from "vitest";
import { rotationNote } from "../StatusesPage";

// Ротации в ячейке «Отдел» (Мария, 05.11.2026): видно, но без перегруза.
describe("rotationNote", () => {
  it("ротаций не было — подписи нет", () => {
    expect(rotationNote(undefined, "SEO")).toBeNull();
    expect(rotationNote([], "SEO")).toBeNull();
  });

  it("одна ротация — коротко прежний отдел, в подсказке путь целиком", () => {
    const note = rotationNote(
      [{ department_id: 1, name: "Продукт", date_from: "2026-08-12", date_to: "2026-10-03" }],
      "Байер FB",
    )!;
    expect(note.short).toBe("↻ Продукт");
    expect(note.title).toContain("Продукт · 12.08.2026 – 03.10.2026");
    expect(note.title).toContain("Сейчас: Байер FB");
  });

  it("несколько — последний прежний и «+N», старые идут первыми", () => {
    const note = rotationNote(
      [
        { department_id: 1, name: "Продукт", date_from: null, date_to: "2026-09-01" },
        { department_id: 2, name: "Байер FB", date_from: "2026-09-01", date_to: "2026-10-01" },
      ],
      "SEO",
    )!;
    expect(note.short).toBe("↻ Байер FB +1");
    expect(note.title.indexOf("Продукт")).toBeLessThan(note.title.indexOf("Байер FB"));
    expect(note.title).toContain("Продукт · 01.09.2026");
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
    expect(note.short).toBe("↻ Продукт +1");
  });
});
