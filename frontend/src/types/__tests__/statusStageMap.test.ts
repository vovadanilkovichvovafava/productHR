import { describe, it, expect } from "vitest";
import {
  STATUS_TO_STAGE_MAP,
  STAGE_TO_STATUS_MAP,
  type ApplicationStage,
  type EntityStatus,
} from "../index";

/**
 * У кандидата и у его заявки РАЗНЫЕ наборы значений: EntityStatus
 * (new/practice/tech_practice/is_interview…) и ApplicationStage
 * (applied/phone_screen/interview/assessment…). Совпадают они только частично,
 * и именно на этом обожглись: пикер этапов на «Все кандидаты» собран из колонок
 * доски (то есть из статусов), а значение уходило в заявку через
 * `stage as ApplicationStage` — приведение типа ничего не проверяет. Четыре
 * «переименованных» значения бэкенд не принимал, отвечая 422, и HR видел
 * «Не удалось изменить этап заявки». Остальные совпадали по имени и работали,
 * поэтому баг выглядел плавающим.
 */

// Колонки доски кандидатов. Держать в синхроне с KANBAN_STATUSES
// в backend/api/routes/candidate_search.py.
const KANBAN_STATUSES: EntityStatus[] = [
  "new", "screening", "practice", "tech_practice", "is_interview",
  "offer", "hired", "probation", "transferred", "rejected", "reserve",
];

const APPLICATION_STAGES: ApplicationStage[] = [
  "applied", "screening", "phone_screen", "interview", "assessment",
  "offer", "hired", "probation", "transferred", "rejected", "withdrawn", "reserve",
];

describe("STATUS_TO_STAGE_MAP", () => {
  it("покрывает каждую колонку доски кандидатов", () => {
    const missing = KANBAN_STATUSES.filter((s) => !STATUS_TO_STAGE_MAP[s]);
    expect(missing).toEqual([]);
  });

  it("отображает только в существующие этапы заявки", () => {
    const bad = KANBAN_STATUSES
      .map((s) => [s, STATUS_TO_STAGE_MAP[s]] as const)
      .filter(([, stage]) => !stage || !APPLICATION_STAGES.includes(stage));
    expect(bad).toEqual([]);
  });

  it("переименованные значения ведут к своему этапу, а не к себе же", () => {
    // Ровно эти четыре и ломались: их имена в двух наборах не совпадают.
    expect(STATUS_TO_STAGE_MAP.new).toBe("applied");
    expect(STATUS_TO_STAGE_MAP.practice).toBe("phone_screen");
    expect(STATUS_TO_STAGE_MAP.tech_practice).toBe("interview");
    expect(STATUS_TO_STAGE_MAP.is_interview).toBe("assessment");
  });

  it("сырой статус не является допустимым этапом — приведение типа не спасает", () => {
    // Защита от соблазна снова написать `stage as ApplicationStage`.
    for (const s of ["new", "practice", "tech_practice", "is_interview"]) {
      expect(APPLICATION_STAGES).not.toContain(s);
    }
  });

  it("обратное отображение согласовано с прямым", () => {
    for (const status of KANBAN_STATUSES) {
      const stage = STATUS_TO_STAGE_MAP[status];
      expect(stage, `нет этапа для статуса ${status}`).toBeTruthy();
      expect(STAGE_TO_STATUS_MAP[stage as ApplicationStage]).toBe(status);
    }
  });
});
