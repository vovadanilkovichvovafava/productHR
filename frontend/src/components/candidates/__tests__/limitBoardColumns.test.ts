import { describe, expect, it } from "vitest";
import { limitBoardColumnsToStatuses } from "../CandidateStageTabs";
import type { KanbanColumn } from "@/services/api/candidates";

// «Все кандидаты» у человека со скоупом по этапам (09.11.2026): вкладками —
// только отмеченные этапы. Свёрнутые «7 этапов без кандидатов» читались как
// число людей.
const col = (status: string, count = 0): KanbanColumn =>
  ({ status, label: status, cards: [], count }) as KanbanColumn;
const board = ["new", "screening", "offer", "probation", "transferred", "rejected", "dismissed", "quit", "other"].map((s) => col(s));

describe("limitBoardColumnsToStatuses", () => {
  it("без ограничения — все вкладки", () => {
    expect(limitBoardColumnsToStatuses(board, undefined)).toBe(board);
    expect(limitBoardColumnsToStatuses(board, [])).toBe(board);
  });

  it("один этап — одна вкладка", () => {
    expect(limitBoardColumnsToStatuses(board, ["probation"]).map((c) => c.status)).toEqual(["probation"]);
  });

  it("два этапа — две вкладки, в порядке доски", () => {
    expect(limitBoardColumnsToStatuses(board, ["probation", "new"]).map((c) => c.status)).toEqual([
      "new",
      "probation",
    ]);
  });

  it("«Мы уволили» — своя вкладка (10.11.2026)", () => {
    expect(limitBoardColumnsToStatuses(board, ["dismissed"]).map((c) => c.status)).toEqual(["dismissed"]);
  });
});
