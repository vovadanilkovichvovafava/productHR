/**
 * Фильтры «Штата» — правила как в ClickUp (клиент, 11.11.2026): «поле →
 * условие → значение», одна связка «И / ИЛИ» на все строки, по умолчанию ИЛИ
 * (Мария, 26.10.2026). Незаполненная строка не отбирает.
 */
import { describe, expect, it } from "vitest";
import {
  EMPTY_FILTERS, describeFilters, newRule, opsFor, readSavedFilters, rowMatchesFilters,
  ruleComplete, type BoardFilters,
} from "../StatusesPage";
import type { BoardRow } from "@/services/api/staffBoard";

const row = (over: Partial<BoardRow>): BoardRow => ({
  entity_id: 1, placement_id: null, name: "Иван", status: "transferred",
  department_id: null, department_name: null, position: null, telegram: null,
  sourcers: [], assignees: [], department_start_date: null,
  ...over,
} as unknown as BoardRow);

const seo = row({ department_name: "SEO team", department_start_date: "2026-10-05" });
const push = row({ department_name: "Push team", department_start_date: "2026-09-10" });
const none = row({ department_name: null });

const f = (join: "and" | "or", ...rules: any[]): BoardFilters =>
  ({ join, rules: rules.map((r) => ({ ...newRule(r.key), ...r })) });

describe("rowMatchesFilters", () => {
  it("без условий проходит всё; пустая строка не отбирает", () => {
    expect(rowMatchesFilters(seo, EMPTY_FILTERS)).toBe(true);
    expect(rowMatchesFilters(seo, { join: "or", rules: [newRule()] })).toBe(true);
    expect(ruleComplete(newRule("department"))).toBe(false);
  });

  it("является / не является / пусто / не пусто", () => {
    const is = f("or", { key: "department", op: "is", values: ["SEO team", "Push team"] });
    expect([seo, push, none].map((r) => rowMatchesFilters(r, is))).toEqual([true, true, false]);
    const not = f("or", { key: "department", op: "is_not", values: ["SEO team"] });
    expect([seo, push, none].map((r) => rowMatchesFilters(r, not))).toEqual([false, true, true]);
    expect(rowMatchesFilters(none, f("or", { key: "department", op: "empty" }))).toBe(true);
    expect(rowMatchesFilters(seo, f("or", { key: "department", op: "not_empty" }))).toBe(true);
  });

  it("дата в периоде", () => {
    const oct = f("or", { key: "department_start_date", op: "between", from: "2026-10-01", to: "2026-10-31" });
    expect([seo, push].map((r) => rowMatchesFilters(r, oct))).toEqual([true, false]);
  });

  it("ИЛИ — хотя бы одно, И — все", () => {
    const rules = [
      { key: "department", op: "is", values: ["Push team"] },
      { key: "department_start_date", op: "between", from: "2026-10-01", to: "2026-10-31" },
    ];
    expect([seo, push].map((r) => rowMatchesFilters(r, f("or", ...rules)))).toEqual([true, true]);
    expect([seo, push].map((r) => rowMatchesFilters(r, f("and", ...rules)))).toEqual([false, false]);
  });

  it("формула считается по порядку, слева направо: (Катя или Лиза) и ноябрь", () => {
    // Скрин владельца 12.11.2026: «вот так должно быть».
    const katya = row({ sourcers: [{ id: 1, name: "Катя", color: "#f6c844" }] as any, department_start_date: "2026-10-01" });
    const lizaNov = row({ sourcers: [{ id: 2, name: "Лиза", color: "#e8a9a9" }] as any, department_start_date: "2026-11-16" });
    const lizaOct = row({ sourcers: [{ id: 2, name: "Лиза", color: "#e8a9a9" }] as any, department_start_date: "2026-10-05" });
    const katyaNov = row({ sourcers: [{ id: 1, name: "Катя", color: "#f6c844" }] as any, department_start_date: "2026-11-03" });
    const formula: BoardFilters = { join: "or", rules: [
      { ...newRule("sourcer"), op: "is", values: ["Катя"] },
      { ...newRule("sourcer"), op: "is", values: ["Лиза"], join: "or" },
      { ...newRule("department_start_date"), op: "between", from: "2026-11-01", to: "2026-11-30", join: "and" },
    ] };
    expect([katya, lizaNov, lizaOct, katyaNov].map((r) => rowMatchesFilters(r, formula))).toEqual([false, true, false, true]);
    expect(describeFilters(formula)).toBe(
      "Показываем: (Сорсер: Катя или Сорсер: Лиза) и Выход в отдел: с 01.11.2026 по 30.11.2026.",
    );

    // И наоборот: «SEO и октябрь или Push» = (SEO и октябрь) или Push
    const other: BoardFilters = { join: "or", rules: [
      { ...newRule("department"), op: "is", values: ["SEO team"] },
      { ...newRule("department_start_date"), op: "between", from: "2026-10-01", to: "2026-10-31", join: "and" },
      { ...newRule("department"), op: "is", values: ["Push team"], join: "or" },
    ] };
    const seoSep = row({ department_name: "SEO team", department_start_date: "2026-09-01" });
    expect([seo, push, seoSep, none].map((r) => rowMatchesFilters(r, other))).toEqual([true, true, false, false]);
    expect(describeFilters(other)).toMatch(/^Показываем: \(Отдел: SEO team и .+\) или Отдел: Push team\.$/);
  });

  it("одна и та же связка подряд — без лишних скобок", () => {
    const allOr: BoardFilters = { join: "or", rules: [
      { ...newRule("department"), op: "is", values: ["SEO team"] },
      { ...newRule("department"), op: "is", values: ["Push team"], join: "or" },
      { ...newRule("department"), op: "empty", join: "or" },
    ] };
    expect(describeFilters(allOr)).toBe("Показываем: Отдел: SEO team или Отдел: Push team или Отдел пусто.");
  });

  it("незаполненная строка посередине формулу не ломает", () => {
    const withBlank: BoardFilters = { join: "or", rules: [
      { ...newRule("department"), op: "is", values: ["SEO team"] },
      { ...newRule(), join: "or" },
      { ...newRule("department_start_date"), op: "between", from: "2026-10-01", to: "2026-10-31", join: "and" },
    ] };
    expect([seo, push].map((r) => rowMatchesFilters(r, withBlank))).toEqual([true, false]);
  });

  it("сохранённые связки строк читаются; старые без связки — по общей", () => {
    const saved = { join: "and", rules: [
      { id: "a", key: "department", op: "is", values: ["SEO team"] },
      { id: "b", key: "department", op: "is", values: ["Push team"], join: "or" },
      { id: "c", key: "department", op: "is", values: ["X"] },
    ] };
    const r = readSavedFilters(saved);
    expect(r.rules.map((x) => x.join)).toEqual([undefined, "or", undefined]);
    // (SEO или Push) и X — третья строка без своей связки берёт общую «и»
    expect(rowMatchesFilters(seo, r)).toBe(false);
  });

  it("HR — по каждому человеку, а не по склеенной строке", () => {
    const two = row({ assignees: [{ user_id: 1, name: "Мария" }, { user_id: 2, name: "Эльвира" }] as any });
    expect(rowMatchesFilters(two, f("or", { key: "assignee", op: "is", values: ["Эльвира"] }))).toBe(true);
  });

  it("текст — «содержит»", () => {
    expect(opsFor("telegram")[0]).toBe("contains");
    const r = row({ telegram: "ivan_petrov" });
    expect(rowMatchesFilters(r, f("or", { key: "telegram", op: "contains", text: "PETR" }))).toBe(true);
  });
});

describe("readSavedFilters", () => {
  it("v3 читается как есть", () => {
    const saved = { join: "and", rules: [{ id: "x", key: "department", op: "is", values: ["SEO team"] }] };
    const r = readSavedFilters(saved);
    expect(r.join).toBe("and");
    expect(r.rules[0]).toMatchObject({ key: "department", op: "is", values: ["SEO team"] });
  });

  it("v2 (галочки) переводится в правила; по умолчанию ИЛИ", () => {
    const r = readSavedFilters({
      values: { department: ["SEO team"], position: ["\u0000blank"] },
      dates: { department_start_date: { from: "2026-10-01", to: "2026-10-31" } },
      andKeys: [],
    });
    expect(r.join).toBe("or");
    expect(r.rules.map((x) => [x.key, x.op])).toEqual([
      ["department", "is"], ["position", "empty"], ["department_start_date", "between"],
    ]);
  });

  it("v2 «все обязательные» → И; мусор → пусто", () => {
    const r = readSavedFilters({
      values: { department: ["SEO team"] },
      dates: { department_start_date: { from: "2026-10-01", to: "" } },
      andKeys: ["department", "department_start_date"],
    });
    expect(r.join).toBe("and");
    expect(readSavedFilters(null)).toEqual(EMPTY_FILTERS);
    expect(readSavedFilters({ rules: [{ key: "мусор" }] }).rules).toEqual([]);
  });
});

describe("describeFilters", () => {
  it("словами, со связкой", () => {
    expect(describeFilters(EMPTY_FILTERS)).toMatch(/показываем всех/);
    const text = describeFilters(f("and",
      { key: "department", op: "is", values: ["SEO team"] },
      { key: "position", op: "empty" },
    ));
    expect(text).toBe("Показываем: Отдел: SEO team и Должность пусто.");
  });
});
