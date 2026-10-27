/**
 * Форма вакансии: проверка полей и данные для сохранения
 * (vacancyFormPayload.ts, 20.10.2026).
 */
import { describe, it, expect } from "vitest";
import { apiErrorDetail, buildVacancyPayload, validateVacancyForm, type VacancyFormData } from "../vacancyFormPayload";
import type { Vacancy } from "@/types";

const form = (over: Partial<VacancyFormData> = {}): VacancyFormData => ({
  title: "  Медиабайер ", description: " ", requirements: "", responsibilities: "Лить трафик",
  salary_min: "", salary_max: "", salary_currency: "RUB", location: "", employment_type: "",
  experience_level: "", status: "pending_review", priority: 0, tags: "fb, , google ",
  visible_to_all: true, closes_at: "", ...over,
});

describe("validateVacancyForm", () => {
  it("название обязательно и не короче трёх символов (как на сервере)", () => {
    expect(validateVacancyForm(form({ title: "   " }))).toBe("Введите название вакансии");
    expect(validateVacancyForm(form({ title: " QA " }))).toBe("Название должно содержать минимум 3 символа");
    expect(validateVacancyForm(form())).toBeNull();
  });
  it("зарплата: не отрицательная, «от» не больше «до»", () => {
    expect(validateVacancyForm(form({ salary_min: "-1" }))).toBe("Зарплата не может быть отрицательной");
    expect(validateVacancyForm(form({ salary_min: 200, salary_max: 100 }))).toBe('"Зарплата от" не может быть больше "Зарплата до"');
    expect(validateVacancyForm(form({ salary_min: 100, salary_max: 100 }))).toBeNull();
  });
});

describe("buildVacancyPayload", () => {
  it("пустое — undefined, теги без пустых, заказчик и дедлайн — явный null", () => {
    const p = buildVacancyPayload(form(), { customerText: "", sandboxId: "" });
    expect(p.title).toBe("Медиабайер");
    expect(p.description).toBeUndefined();
    expect(p.responsibilities).toBe("Лить трафик");
    expect(p.tags).toEqual(["fb", "google"]);
    expect(p.hiring_manager_id).toBeNull();
    expect(p.closes_at).toBeNull();
    expect(p.salary_min).toBeUndefined();
  });

  it("служебные ключи extra_data при правке не стираются", () => {
    const vacancy = { id: 1, extra_data: { cloned_from_request_id: 7, accepted_by: [2], customer_name: "старый" } } as unknown as Vacancy;
    const p = buildVacancyPayload(form(), { vacancy, customerText: " Влад — RND Facebook ", sandboxId: "12" });
    expect(p.extra_data).toEqual({
      cloned_from_request_id: 7, accepted_by: [2], customer_name: "Влад — RND Facebook", board_sandbox_id: 12,
    });
  });

  it("стёртый заказчик и снятая песочница уходят как пустые", () => {
    const vacancy = { id: 1, extra_data: { customer_name: "старый", board_sandbox_id: 3 } } as unknown as Vacancy;
    const p = buildVacancyPayload(form(), { vacancy, customerText: "  ", sandboxId: "" });
    expect(p.extra_data.customer_name).toBeUndefined();
    expect(p.extra_data.board_sandbox_id).toBeUndefined();
  });
});

describe("сколько человек нужно нанять", () => {
  it("сохраняется в extra_data.positions_count — там же, где его пишет бот", () => {
    const p = buildVacancyPayload(form(), { customerText: "", sandboxId: "", positionsCount: "3" });
    expect(p.extra_data.positions_count).toBe(3);
  });
  it("не число и меньше 1 — ошибка, а не молчаливая единица", () => {
    expect(validateVacancyForm({ ...form(), positionsCount: "0" })).toBe("Сколько человек нужно нанять — целое число от 1");
    expect(validateVacancyForm({ ...form(), positionsCount: "2.5" })).toBe("Сколько человек нужно нанять — целое число от 1");
    expect(validateVacancyForm({ ...form(), positionsCount: "2" })).toBeNull();
  });
});

describe("apiErrorDetail", () => {
  it("строка, первая ошибка валидации или общий текст", () => {
    expect(apiErrorDetail({ response: { data: { detail: "Нет прав" } } }, "x")).toBe("Нет прав");
    expect(apiErrorDetail({ response: { data: { detail: [{ msg: "closes_at cannot be in the past" }] } } }, "x")).toBe("closes_at cannot be in the past");
    expect(apiErrorDetail(new Error("network"), "Ошибка при создании")).toBe("Ошибка при создании");
  });
});
