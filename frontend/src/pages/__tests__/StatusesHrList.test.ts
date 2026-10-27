/**
 * Кого «+ HR» предлагает на доске «Штат».
 *
 * Доску ведут не все HR организации (21.09.2026), с 15.10.2026 их трое:
 * Мария, Эльвира и Влада — «добавь плиз сюда Владу, она есть в базе, у нас
 * 3 HR». Отдельно сторожим, что «Влад» (наставник практики, другой человек)
 * в список не попадает.
 */
import { describe, it, expect } from "vitest";
import { isBoardHr } from "../StatusesPage";

describe("isBoardHr", () => {
  it("пускает троих, кто ведёт доску", () => {
    expect(isBoardHr("Мария Голикова")).toBe(true);
    expect(isBoardHr("Эльвира")).toBe(true);
    expect(isBoardHr("Влада Петрова")).toBe(true);
    expect(isBoardHr("vlada")).toBe(true);
  });

  it("«Влад» — не «Влада»", () => {
    expect(isBoardHr("Влад")).toBe(false);
    expect(isBoardHr("Влад Наставник")).toBe(false);
  });

  it("остальных в списке нет", () => {
    expect(isBoardHr("Валентина")).toBe(false);
    expect(isBoardHr("Егор")).toBe(false);
    expect(isBoardHr(null)).toBe(false);
    expect(isBoardHr("")).toBe(false);
  });
});
