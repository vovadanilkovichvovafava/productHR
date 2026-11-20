import { describe, expect, it, vi } from "vitest";

import {
  applyTransitionFields,
  isTransitionStage,
  nextWorkday,
  transitionDefaults,
  transitionReady,
} from "@/utils/stageTransition";

describe("stageTransition", () => {
  it("next workday skips the weekend", () => {
    expect(nextWorkday(new Date(2026, 10, 18))).toBe("2026-11-19"); // ср → чт
    expect(nextWorkday(new Date(2026, 10, 20))).toBe("2026-11-23"); // пт → пн
    expect(nextWorkday(new Date(2026, 10, 22))).toBe("2026-11-23"); // вс → пн
  });

  it("only practice and transfer have fields", () => {
    expect(isTransitionStage("probation")).toBe(true);
    expect(isTransitionStage("transferred")).toBe(true);
    expect(isTransitionStage("rejected")).toBe(false);
  });

  it("prefills the stored date, otherwise tomorrow / today", () => {
    const today = new Date(2026, 10, 18);
    expect(transitionDefaults("probation", {}, today).date).toBe("2026-11-19");
    expect(transitionDefaults("probation", { practice_start_date: "2026-11-25" }, today).date).toBe("2026-11-25");
    expect(transitionDefaults("transferred", undefined, today).date).toBe("2026-11-18");
    expect(
      transitionDefaults("transferred", { department_transfer_date: "2026-12-01T00:00:00" }, today).date,
    ).toBe("2026-12-01");
  });

  it("date is required", () => {
    expect(transitionReady({ date: "2026-11-19", mentor: "", departmentId: null })).toBe(true);
    expect(transitionReady({ date: "", mentor: "", departmentId: null })).toBe(false);
    expect(transitionReady(null)).toBe(false);
  });

  it("writes department, date, mentor — in that order, only what was chosen", async () => {
    const calls: string[] = [];
    const api = {
      updateRow: vi.fn(async (_id: number, patch: Record<string, string>) => calls.push(`row ${JSON.stringify(patch)}`)),
      setMentor: vi.fn(async (_id: number, name: string) => calls.push(`mentor ${name}`)),
      addPlacement: vi.fn(async (_id: number, dept: number) => calls.push(`dept ${dept}`)),
    };
    await applyTransitionFields(7, "probation", { date: "2026-11-19", mentor: "Егор", departmentId: null }, api);
    await applyTransitionFields(7, "transferred", { date: "2026-11-24", mentor: "", departmentId: 3 }, api);
    await applyTransitionFields(7, "probation", { date: "2026-11-20", mentor: "", departmentId: null }, api);
    expect(calls).toEqual([
      'row {"practice_start_date":"2026-11-19"}',
      "mentor Егор",
      "dept 3",
      'row {"department_start_date":"2026-11-24"}',
      'row {"practice_start_date":"2026-11-20"}',
    ]);
  });
});
