/**
 * Фильтры доски «Штат»: у каждого условия пометка «или» / «и».
 *
 * История. 07.10.2026 — один режим на всю панель («любое / все сразу»).
 * 21.10.2026 — пометка у каждого условия, по умолчанию «и»: Мария отметила
 * четыре отдела и октябрь и ждала пересечения. 26.10.2026 Мария: «нужно, чтобы
 * всегда было ИЛИ» — доску фильтруют под массовую выгрузку, поэтому по
 * умолчанию «или», а «и» ставят руками там, где условие обязательное.
 */
import { describe, it, expect } from "vitest";
import {
  rowMatchesFilters, describeFilters, activeFilterKeys, readSavedFilters,
} from "../StatusesPage";
import type { BoardRow } from "@/services/api/staffBoard";

const row = (over: Partial<BoardRow>): BoardRow =>
  ({
    entity_id: 1,
    name: "Кандидат",
    status: "transferred",
    position: null,
    department_name: null,
    department_start_date: null,
    telegram: null,
    manager: null,
    sourcers: [],
    ...over,
  } as unknown as BoardRow);

const seo = row({ name: "Сеошник", department_name: "SEO", department_start_date: "2026-09-10" });
const push = row({ name: "Пушер", department_name: "Push", department_start_date: "2026-02-01" });
const twoConditions = {
  values: { department: ["SEO"] },
  dates: { department_start_date: { from: "2026-01-01", to: "2026-03-01" } },
};

describe("rowMatchesFilters", () => {
  it("без условий проходит всё", () => {
    expect(rowMatchesFilters(seo, { values: {}, dates: {} })).toBe(true);
  });

  it("по умолчанию условия складываются через «или» — Мария 26.10.2026", () => {
    const filters = { ...twoConditions } as any;
    // SEO подходит по отделу, Push — по дате: оба в выдаче.
    expect(rowMatchesFilters(seo, filters)).toBe(true);
    expect(rowMatchesFilters(push, filters)).toBe(true);
    // Не подошёл ни по одному условию — мимо.
    expect(rowMatchesFilters(row({ department_name: "BizDev" }), filters)).toBe(false);
  });

  it("условие с пометкой «и» обязательно", () => {
    const filters = { ...twoConditions, andKeys: ["department", "department_start_date"] } as any;
    expect(rowMatchesFilters(seo, filters)).toBe(false);   // дата не та
    expect(rowMatchesFilters(push, filters)).toBe(false);  // отдел не тот
    expect(
      rowMatchesFilters(row({ department_name: "SEO", department_start_date: "2026-02-10" }), filters)
    ).toBe(true);
  });

  it("смешанный случай: (отдел или уволенные) и вышел в окно дат", () => {
    const filters = {
      values: { department: ["SEO"], status: ["Уволен / уволился"] },
      dates: { department_start_date: { from: "2026-09-01", to: "2026-09-30" } },
      andKeys: ["department_start_date"],
    } as any;
    expect(rowMatchesFilters(seo, filters)).toBe(true);
    expect(
      rowMatchesFilters(row({ department_name: "BizDev", department_start_date: "2026-09-05" }), filters)
    ).toBe(false);
    expect(
      rowMatchesFilters(row({ department_name: "SEO", department_start_date: "2026-02-05" }), filters)
    ).toBe(false);
  });

  it("значения внутри одной колонки всегда складываются по «или»", () => {
    const filters = { values: { department: ["SEO", "Push"] }, dates: {}, andKeys: ["department"] } as any;
    expect(rowMatchesFilters(seo, filters)).toBe(true);
    expect(rowMatchesFilters(push, filters)).toBe(true);
    expect(rowMatchesFilters(row({ department_name: "BizDev" }), filters)).toBe(false);
  });

  it("пустая колонка ловится вариантом «Пусто»", () => {
    const filters = { values: { department: ["\u0000blank"] }, dates: {} } as any;
    expect(rowMatchesFilters(row({ department_name: null }), filters)).toBe(true);
    expect(rowMatchesFilters(seo, filters)).toBe(false);
  });
});

describe("readSavedFilters — сохранённый в браузере фильтр", () => {
  it("«и», стоявшее само по умолчанию (21–26.10), становится «или»", () => {
    const saved = readSavedFilters({ ...twoConditions, orKeys: [] });
    expect(saved.andKeys).toEqual([]);
    expect(rowMatchesFilters(push, saved)).toBe(true);
  });

  it("явный старый режим «все сразу» остаётся «и» у всех условий", () => {
    const saved = readSavedFilters({ ...twoConditions, mode: "all" });
    expect(saved.andKeys?.sort()).toEqual(["department", "department_start_date"]);
  });

  it("новый формат читается как есть", () => {
    const saved = readSavedFilters({ ...twoConditions, andKeys: ["department_start_date"] });
    expect(saved.andKeys).toEqual(["department_start_date"]);
  });

  it("мусор — пустой фильтр", () => {
    expect(readSavedFilters(null)).toEqual({ values: {}, dates: {}, andKeys: [] });
    expect(readSavedFilters("x")).toEqual({ values: {}, dates: {}, andKeys: [] });
  });
});

describe("describeFilters — панель объясняет словами", () => {
  it("без условий говорит, что показывает всех", () => {
    expect(describeFilters({ values: {}, dates: {} })).toBe("Ничего не отмечено — показываем всех.");
  });

  it("одни «или» — без скобок", () => {
    const text = describeFilters({ ...twoConditions } as any);
    expect(text).toBe(
      "Показываем тех, у кого Отдел — SEO или Выход в отдел — с 01.01.2026 по 01.03.2026.",
    );
  });

  it("«и» впереди, «или» в скобках", () => {
    const text = describeFilters({
      values: { department: ["SEO"], status: ["Уволен / уволился"] },
      dates: { department_start_date: { from: "2026-10-01", to: "" } },
      andKeys: ["department_start_date"],
    } as any);
    expect(text).toMatch(/^Показываем тех, у кого Выход в отдел — с 01\.10\.2026 и \(.+ или .+\)\.$/);
  });
});

describe("activeFilterKeys", () => {
  it("перечисляет колонки, по которым что-то отобрано", () => {
    expect(
      activeFilterKeys({
        values: { department: ["SEO"], position: [] },
        dates: { department_start_date: { from: "2026-10-01", to: "" }, w2: { from: "", to: "" } },
      } as any),
    ).toEqual(["department", "department_start_date"]);
  });
});
