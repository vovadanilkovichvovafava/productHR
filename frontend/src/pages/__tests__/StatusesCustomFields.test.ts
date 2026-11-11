/** Свои поля «Штата» (клиент, 11.11.2026): колонка «cf:<id>», подпись,
 *  значение ячейки, фильтр — как у встроенных. */
import { afterEach, describe, expect, it } from "vitest";
import {
  allColumns, arrangeColumns, fieldLabel, newRule, opsFor, rowMatchesFilters, setCustomFields,
} from "../StatusesPage";
import type { BoardRow } from "@/services/api/staffBoard";

const FIELDS = [
  { id: "g1", name: "Грейд", type: "select" as const, options: ["Junior", "Middle"] },
  { id: "d1", name: "Ревью", type: "date" as const, options: [] },
  { id: "c1", name: "Ноутбук", type: "checkbox" as const, options: [] },
];
const row = (custom: Record<string, any>) => ({ entity_id: 1, name: "Иван", status: "transferred", custom } as unknown as BoardRow);

afterEach(() => setCustomFields([]));

describe("свои поля", () => {
  it("становятся колонками после встроенных, с названием поля", () => {
    setCustomFields(FIELDS);
    const keys = allColumns().map((c) => c.key);
    expect(keys.slice(-3)).toEqual(["cf:g1", "cf:d1", "cf:c1"]);
    expect(fieldLabel("cf:g1")).toBe("Грейд");
    expect(arrangeColumns({ hidden: ["cf:d1"] }).map((c) => c.key)).not.toContain("cf:d1");
  });

  it("фильтруются по своему типу", () => {
    setCustomFields(FIELDS);
    expect(opsFor("cf:d1")[0]).toBe("between");
    expect(opsFor("cf:c1")).toEqual(["not_empty", "empty"]);
    const mid = row({ g1: "Middle", d1: "2026-12-01", c1: true });
    const jun = row({ g1: "Junior" });
    const is = { join: "or" as const, rules: [{ ...newRule("cf:g1"), values: ["Middle"] }] };
    expect([mid, jun].map((r) => rowMatchesFilters(r, is))).toEqual([true, false]);
    const dec = { join: "or" as const, rules: [{ ...newRule("cf:d1"), op: "between" as const, from: "2026-12-01", to: "2026-12-31" }] };
    expect([mid, jun].map((r) => rowMatchesFilters(r, dec))).toEqual([true, false]);
    const laptop = { join: "or" as const, rules: [{ ...newRule("cf:c1"), op: "not_empty" as const }] };
    expect([mid, jun].map((r) => rowMatchesFilters(r, laptop))).toEqual([true, false]);
  });
});
