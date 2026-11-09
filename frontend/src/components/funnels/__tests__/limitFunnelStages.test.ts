import { describe, expect, it } from "vitest";
import { buildFunnelStagesConfig, limitFunnelStagesToStatuses } from "../useFunnelStages";

// Наставники (Влад, Егор) видят только «Практику» (09.11.2026): в воронке у
// них остаются только разрешённые вкладки, иначе она открывалась на пустом
// «Новом».
describe("limitFunnelStagesToStatuses", () => {
  const base = buildFunnelStagesConfig(undefined, {});

  it("без ограничения — всё как было", () => {
    expect(limitFunnelStagesToStatuses(base, undefined)).toBe(base);
    expect(limitFunnelStagesToStatuses(base, [])).toBe(base);
  });

  it("оставляет только вкладку «Практика»", () => {
    const cfg = limitFunnelStagesToStatuses(base, ["probation"]);
    expect(cfg.keys).toEqual(["probation"]);
    expect(cfg.enumToKeys).toEqual({ probation: ["probation"] });
  });

  it("свои колонки вакансии — по этапу, на который они смотрят", () => {
    const custom = buildFunnelStagesConfig(
      [
        { key: "applied", label: "Новый", visible: true },
        { key: "trial", label: "Испытание", visible: true, maps_to: "probation" },
      ],
      {},
    );
    expect(limitFunnelStagesToStatuses(custom, ["probation"]).keys).toEqual(["trial"]);
  });

  it("если разрешённых вкладок нет, воронку не ломаем", () => {
    const custom = buildFunnelStagesConfig([{ key: "applied", label: "Новый", visible: true }], {});
    expect(limitFunnelStagesToStatuses(custom, ["probation"])).toBe(custom);
  });
});
