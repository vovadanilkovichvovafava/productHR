import { describe, expect, it } from "vitest";
import { calculateAge, formatNotificationTime, parseServerDay } from "@/utils/date";

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

// Дата без времени — календарный день, одинаковый в любой стране
// (23.11.2026: западнее Лондона «20.11» показывалось как «19.11», а дедлайн
// «до 25.11» в Москве — как «26.11»).
describe("parseServerDay", () => {
  const day = (v: string) => parseServerDay(v).toLocaleDateString("ru-RU");

  it("дата, начало и конец дня — тот же день у любого смотрящего", () => {
    expect(day("2026-11-20")).toBe("20.11.2026");
    expect(day("2026-11-20T00:00:00")).toBe("20.11.2026");
    expect(day("2026-11-25T23:59:59")).toBe("25.11.2026");
  });

  it("момент времени с сервера переводится из UTC", () => {
    const d = parseServerDay("2026-11-19T21:36:00");
    expect(d.getTime()).toBe(Date.UTC(2026, 10, 19, 21, 36));
  });

  it("возраст не съезжает накануне дня рождения", () => {
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    const birth = `${now.getFullYear() - 30}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    expect(calculateAge(birth)).toBe(30);
  });
});
