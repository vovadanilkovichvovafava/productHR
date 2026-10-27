import { describe, expect, it } from "vitest";
import { matchesFor } from "../CandidateHandoverModal";

// Куда сложить кандидатов уходящего у получателя (26.10.2026).
const funnel = (participants: number[], matches: { id: number; who: number[]; status?: string; n?: number }[]) => ({
  vacancy_id: 1, title: "Трафик", status: "open", candidates: 3, participants,
  matches: matches.map((m) => ({
    vacancy_id: m.id, title: "Трафик", status: m.status ?? "open", candidates: m.n ?? 0, participants: m.who,
  })),
});

describe("matchesFor", () => {
  it("предлагает такую же воронку, где работает получатель", () => {
    const f = funnel([5], [{ id: 2, who: [4] }, { id: 3, who: [7] }]);
    expect(matchesFor(f, 4).map((m) => m.vacancy_id)).toEqual([2]);
  });

  it("получатель уже работает в этой воронке — сливать нечего", () => {
    const f = funnel([5, 4], [{ id: 2, who: [4] }]);
    expect(matchesFor(f, 4)).toEqual([]);
  });

  it("открытые раньше закрытых, затем по числу кандидатов", () => {
    const f = funnel([5], [
      { id: 2, who: [4], status: "closed", n: 99 },
      { id: 3, who: [4], n: 1 },
      { id: 4, who: [4], n: 10 },
    ]);
    expect(matchesFor(f, 4).map((m) => m.vacancy_id)).toEqual([4, 3, 2]);
  });
});
