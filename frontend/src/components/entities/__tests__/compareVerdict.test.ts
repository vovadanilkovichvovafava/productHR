import { describe, expect, it } from "vitest";
import { compareVerdictText } from "../CandidateCompareCard";

// Вывод окна сравнения — связный текст, а не плашки-обрывки (24.10.2026).
describe("compareVerdictText", () => {
  it("совпадения и признаки сервера — одной фразой", () => {
    expect(
      compareVerdictText({
        same: ["ФИО", "возраст", "город", "должность", "стаж"],
        alike: [],
        extra: ["Та же компания + похожие навыки", "Текст резюме совпадает (100%)"],
        diff: [],
      }),
    ).toBe(
      "Совпадают ФИО, возраст, город, должность и стаж; та же компания и похожие навыки; текст резюме совпадает на 100%.",
    );
  });

  it("одно совпадение, похожее и отличия", () => {
    expect(compareVerdictText({ same: ["телефон"], alike: ["ФИО"], extra: [], diff: ["город", "стаж"] })).toBe(
      "Совпадает телефон; похоже: ФИО. Отличается: город и стаж.",
    );
  });

  it("пусто — без текста", () => {
    expect(compareVerdictText({ same: [], alike: [], extra: [], diff: [] })).toBe("");
    expect(compareVerdictText({ same: [], alike: [], extra: [], diff: ["город"] })).toBe("Отличается: город.");
  });
});
