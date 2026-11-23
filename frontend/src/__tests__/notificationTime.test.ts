import { describe, expect, it } from "vitest";
import { formatNotificationTime } from "@/utils/date";

// Уведомление «Ответ на анкету» показывало 21:36, а сама анкета — 00:36
// следующего дня (Мария, 23.11.2026): время без пояса читалось как местное.
describe("formatNotificationTime", () => {
  const sameAs = (iso: string) =>
    new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

  it("время сервера без пояса считается UTC", () => {
    expect(formatNotificationTime("2026-11-19T21:36:00")).toBe(sameAs("2026-11-19T21:36:00Z"));
  });

  it("время с поясом не сдвигается второй раз", () => {
    expect(formatNotificationTime("2026-11-19T21:36:00+00:00")).toBe(sameAs("2026-11-19T21:36:00Z"));
  });

  it("пустое и мусор — пустая строка", () => {
    expect(formatNotificationTime(null)).toBe("");
    expect(formatNotificationTime("не дата")).toBe("");
  });
});
