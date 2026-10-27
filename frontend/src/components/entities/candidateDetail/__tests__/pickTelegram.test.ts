import { describe, it, expect } from "vitest";
import { entityToKanbanCard, pickTelegram } from "../model";

// hh_b2b — канал hh.ru, а не ник кандидата: карточка и окно сравнения
// показывали его, когда он стоял первым в списке (прод, 22.09.2026).
describe("pickTelegram", () => {
  it("пропускает канал портала и берёт настоящий ник", () => {
    expect(pickTelegram(["hh_b2b", "yrsrss"])).toBe("yrsrss");
    expect(pickTelegram(["@HH_B2B", "@ivan"])).toBe("@ivan");
  });
  it("пусто, если настоящего ника нет", () => {
    expect(pickTelegram(["hh_b2b"])).toBeUndefined();
    expect(pickTelegram(undefined)).toBeUndefined();
  });
  it("карточка из профиля показывает настоящий ник", () => {
    const card = entityToKanbanCard(
      { id: 1, name: "Филатов Ярослав", telegram_usernames: ["hh_b2b", "yrsrss"], extra_data: {} } as never,
      {},
    );
    expect(card.telegram_username).toBe("yrsrss");
  });
});
