/**
 * Справочник этапов один на весь фронт (constants/hrStages.ts, 20.10.2026).
 * Раньше подписи и цвета были переписаны в семи местах и разъехались. Тест
 * держит прежние значения (их видят рекрутёры каждый день) и не даёт
 * появиться новой ручной копии.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import {
  APPLICATION_STAGE_COLORS,
  APPLICATION_STAGE_LABELS,
  STAGE_TO_STATUS_MAP,
  STATUS_LABELS,
  STATUS_TO_STAGE_MAP,
} from "@/types";
import { CANDIDATE_VACANCY_STAGE_LABELS } from "@/components/entities/candidateDetail/model";
import { FUNNEL_STAGE_ORDER, HR_STAGES } from "../hrStages";

describe("hrStages", () => {
  it("подписи этапов заявки прежние", () => {
    expect(APPLICATION_STAGE_LABELS).toEqual({
      applied: "Новый",
      screening: "Выполняет ТЗ",
      phone_screen: "Интервью с HR",
      interview: "Интервью с заказчиком",
      assessment: "Принятие решения",
      offer: "Выставлен оффер",
      hired: "Оффер принят",
      probation: "Практика",
      transferred: "Перешёл в отдел",
      rejected: "Отказ",
      withdrawn: "Отозван",
      reserve: "Резерв",
    });
    expect(CANDIDATE_VACANCY_STAGE_LABELS).toEqual(APPLICATION_STAGE_LABELS);
  });

  it("подписи статусов кандидата прежние, включая легаси", () => {
    expect(STATUS_LABELS.new).toBe("Новый");
    expect(STATUS_LABELS.practice).toBe("Интервью с HR");
    expect(STATUS_LABELS.tech_practice).toBe("Интервью с заказчиком");
    expect(STATUS_LABELS.is_interview).toBe("Принятие решения");
    expect(STATUS_LABELS.reserve).toBe("Резерв");
    expect(STATUS_LABELS.active).toBe("Активный");
    expect(STATUS_LABELS.applied).toBe("Новый");
    expect(STATUS_LABELS.phone_screen).toBe("Интервью с HR");
    expect(STATUS_LABELS.interview).toBe("Интервью с заказчиком");
    expect(STATUS_LABELS.assessment).toBe("Принятие решения");
  });

  it("статус кандидата ↔ этап заявки — как на сервере (STATUS_SYNC_MAP)", () => {
    expect(STATUS_TO_STAGE_MAP).toEqual({
      new: "applied",
      screening: "screening",
      practice: "phone_screen",
      tech_practice: "interview",
      is_interview: "assessment",
      offer: "offer",
      hired: "hired",
      probation: "probation",
      transferred: "transferred",
      rejected: "rejected",
      withdrawn: "withdrawn",
      reserve: "reserve",
      applied: "applied",
      phone_screen: "phone_screen",
      interview: "interview",
      assessment: "assessment",
    });
    for (const st of HR_STAGES) expect(STAGE_TO_STATUS_MAP[st.stage]).toBe(st.status);
  });

  it("цвет «Интервью с HR» один везде — фиолетовый", () => {
    expect(APPLICATION_STAGE_COLORS.phone_screen).toContain("--hf-status-purple");
    expect(APPLICATION_STAGE_COLORS.transferred).toContain("--hf-status-green");
  });

  it("вкладки воронки: всё, кроме «Отозван», «Резерв» последним", () => {
    expect(FUNNEL_STAGE_ORDER).toEqual([
      "applied", "screening", "phone_screen", "interview", "assessment",
      "offer", "hired", "probation", "transferred", "rejected", "reserve",
    ]);
  });

  it("ручных копий подписей больше нет", () => {
    const root = join(__dirname, "..", "..");
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) {
          if (name !== "__tests__" && name !== "node_modules") walk(path);
          continue;
        }
        if (!/\.(ts|tsx)$/.test(name) || name === "hrStages.ts") continue;
        const text = readFileSync(path, "utf-8");
        if (/["']Выполняет ТЗ["']\s*[,}]/.test(text)) offenders.push(relative(root, path));
      }
    };
    walk(root);
    expect(offenders).toEqual([]);
  });
});

describe("boardColumnOf — вкладка «Все кандидаты» по статусу", () => {
  it("этапы HR — своя вкладка; уволен/уволился — «Отказ» (как на сервере, board_column)", async () => {
    const { boardColumnOf, DEPARTED_LABELS } = await import("../hrStages");
    expect(boardColumnOf("probation")).toBe("probation");
    expect(boardColumnOf("dismissed")).toBe("rejected");
    expect(boardColumnOf("quit")).toBe("rejected");
    expect(boardColumnOf("active")).toBe("other");
    expect(DEPARTED_LABELS).toEqual({ dismissed: "Уволен", quit: "Уволился" });
  });
});
