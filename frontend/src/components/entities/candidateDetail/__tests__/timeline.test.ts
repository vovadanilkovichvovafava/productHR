/**
 * Лента карточки воронки (candidateDetail/timeline.ts, 20.10.2026).
 * Правила из разбора с Марией 24.09.2026: одна запись = одно событие
 * «СТАТУС — комментарий», без стрелок «из → в»; закреп — первым.
 */
import { describe, it, expect } from "vitest";
import { buildTimelineRows, pinTimelineRow } from "../timeline";
import type { ActivityEvent } from "@/services/api/entities";

const label = (s: string) =>
  ({ applied: "Новый", screening: "Выполняет ТЗ", probation: "Практика" })[s] || s;

const base = {
  notes: [],
  events: [] as ActivityEvent[],
  snapshot: false,
  getStageLabel: label,
  createdAt: "2026-10-01T09:00:00",
  recruiterName: "Мария",
};

describe("buildTimelineRows", () => {
  it("пустая лента — одна строка «Кандидат добавлен» с автором карточки", () => {
    const rows = buildTimelineRows(base);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ title: "Кандидат добавлен", author: "Мария", reactionKey: "created" });
  });

  it("снапшот влитого дубля без заметок — пусто, без синтетической строки", () => {
    expect(buildTimelineRows({ ...base, snapshot: true })).toEqual([]);
  });

  it("перевод: заголовок — новый этап, прежний — только в подсказке, комментарий — тело", () => {
    const rows = buildTimelineRows({
      ...base,
      events: [{ id: 7, from_stage: "applied", to_stage: "screening", comment: "ТЗ выдано", created_at: "2026-10-02T10:00:00", changed_by_name: "Влада" } as unknown as ActivityEvent],
    });
    expect(rows[0]).toMatchObject({
      title: "Выполняет ТЗ", fromLabel: "Новый", body: "ТЗ выдано", author: "Влада",
      historyId: 7, reactionKey: "e:7", kind: "stage",
    });
  });

  it("снапшот не показывает переходы живой заявки", () => {
    const rows = buildTimelineRows({
      ...base,
      snapshot: true,
      events: [{ id: 7, to_stage: "screening", created_at: "2026-10-02T10:00:00" } as unknown as ActivityEvent],
      notes: [{ id: "n1", text: "из дубля", date: "2026-09-01T10:00:00+00:00" }],
    });
    expect(rows.map((r) => r.reactionKey)).toEqual(["n:n1"]);
  });

  it("комментарий с этапом — «статус — текст», обычный — просто текст", () => {
    const rows = buildTimelineRows({
      ...base,
      notes: [
        { id: "a", text: "созвон", stage_label: "Практика", date: "2026-10-03T10:00:00+00:00" },
        { id: "b", text: "просто заметка", date: "2026-10-04T10:00:00+00:00" },
      ],
    });
    const byKey = Object.fromEntries(rows.map((r) => [r.reactionKey, r]));
    expect(byKey["n:a"]).toMatchObject({ title: "Практика", body: "созвон", kind: "comment" });
    expect(byKey["n:b"]).toMatchObject({ title: "просто заметка", body: undefined });
  });

  it("порядок — новые сверху, хотя у переходов и заметок разный формат времени", () => {
    // Переход: naive из БД (UTC без зоны), заметка: aware UTC. 12:00 UTC позже 11:30 UTC.
    const rows = buildTimelineRows({
      ...base,
      events: [{ id: 1, to_stage: "screening", created_at: "2026-10-05T12:00:00" } as unknown as ActivityEvent],
      notes: [{ id: "x", text: "раньше", date: "2026-10-05T11:30:00+00:00" }],
    });
    expect(rows.map((r) => r.reactionKey)).toEqual(["e:1", "n:x"]);
  });

  it("бейдж воронки у комментария — только если страница его просит", () => {
    const note = { id: "v", text: "в трафике", vacancy_id: 4, date: "2026-10-01T10:00:00+00:00" };
    expect(buildTimelineRows({ ...base, notes: [note] })[0].vacancyLabel).toBeNull();
    expect(
      buildTimelineRows({ ...base, notes: [note], resolveNoteVacancyLabel: (id) => (id === 4 ? "Трафик" : null) })[0].vacancyLabel,
    ).toBe("Трафик");
  });
});

describe("pinTimelineRow", () => {
  const rows = [{ reactionKey: "a", kind: "comment" as const }, { reactionKey: "b", kind: "stage" as const }];
  it("закреп — первым и только один раз", () => {
    expect(pinTimelineRow(rows, "b").map((r) => [r.reactionKey, !!r.pinned])).toEqual([["b", true], ["a", false]]);
  });
  it("закреп на удалённую запись — лента без изменений", () => {
    expect(pinTimelineRow(rows, "zzz")).toBe(rows);
  });
});
