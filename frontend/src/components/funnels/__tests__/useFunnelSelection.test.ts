/**
 * Кто открыт в воронке и какая вкладка (useFunnelSelection, 20.10.2026).
 *
 * Правила ломались чаще всего и до выноса проверялись только руками:
 * «перехожу на статус — пустое окно» (Мария), «открывает последнюю, а не
 * первую», «ссылка на кандидата открыла другого», «F5 сбросил вкладку»,
 * «перемещённый кандидат пропал из списка».
 */
import { describe, it, expect } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useCallback, useState } from "react";

import { useFunnelSelection } from "../useFunnelSelection";
import { buildFunnelStagesConfig } from "../useFunnelStages";
import type { VacancyApplication } from "@/types";

const stages = buildFunnelStagesConfig(undefined, {});

const app = (id: number, entity: number, stage: string, changed: string) =>
  ({
    id,
    entity_id: entity,
    vacancy_id: 1,
    stage,
    applied_at: "2026-09-01T10:00:00",
    last_stage_change_at: changed,
  }) as unknown as VacancyApplication;

// Новый: Б свежее А. ТЗ: В.
const A = app(11, 101, "applied", "2026-10-01T10:00:00");
const B = app(12, 102, "applied", "2026-10-05T10:00:00");
const C = app(13, 103, "screening", "2026-10-03T10:00:00");
const ALL = [A, B, C];

type Props = { candidates: VacancyApplication[]; search?: string };

function setup(initialUrl: string, initial: Props) {
  let focused = 0;
  const hook = renderHook(
    (props: Props) => {
      const [sp, setSp] = useState(() => new URLSearchParams(initialUrl));
      const setSearchParams = useCallback(
        (next: URLSearchParams | ((prev: URLSearchParams) => URLSearchParams)) =>
          setSp((prev) => (typeof next === "function" ? next(prev) : next)),
        [],
      );
      const sel = useFunnelSelection({
        candidates: props.candidates,
        filteredCandidates: props.candidates,
        candidateSearch: props.search ?? "",
        stagesConfig: stages,
        selectedVacancyId: 1,
        searchParams: sp,
        setSearchParams: setSearchParams as never,
        onCandidateFocused: () => {
          focused += 1;
        },
      });
      return { ...sel, url: sp };
    },
    { initialProps: initial },
  );
  return { ...hook, focused: () => focused };
}

describe("useFunnelSelection", () => {
  it("открытие без ссылки: первая вкладка и самый свежий кандидат в ней", async () => {
    const { result } = setup("v=1", { candidates: ALL });
    await waitFor(() => expect(result.current.selectedCandidateId).toBe(B.id));
    expect(result.current.selectedTab).toBe("applied");
    await waitFor(() => expect(result.current.url.get("entity")).toBe("102"));
    expect(result.current.url.get("stage")).toBe("applied");
  });

  it("ссылка на кандидата — открыт именно он, а не первый", async () => {
    const { result } = setup("v=1&stage=applied&entity=101", { candidates: ALL });
    await waitFor(() => expect(result.current.selectedCandidateId).toBe(A.id));
    expect(result.current.url.get("entity")).toBe("101");
  });

  it("ссылка без ?stage= на кандидата другой вкладки — открывается вкладка «Все» с ним", async () => {
    // Как в странице: воронка открыта, кандидаты приходят отдельным запросом.
    const { result, rerender } = setup("v=1&entity=103", { candidates: [] });
    rerender({ candidates: ALL });
    await waitFor(() => expect(result.current.selectedCandidateId).toBe(C.id));
    expect(result.current.selectedTab).toBe("all");
  });

  it("та же ссылка, когда кандидаты уже загружены, — тоже он (раньше открывался первый «Нового»)", async () => {
    const { result } = setup("v=1&entity=103", { candidates: ALL });
    await waitFor(() => expect(result.current.selectedCandidateId).toBe(C.id));
    expect(result.current.url.get("entity")).toBe("103");
  });

  it("воронка из меню без кандидата в ссылке — первая рабочая вкладка, как раньше", async () => {
    const { result } = setup("v=1&recruiter=4", { candidates: ALL });
    await waitFor(() => expect(result.current.selectedTab).toBe("applied"));
  });

  it("устаревшая ссылка (вкладка ТЗ, кандидат из «Новый») — не пустая панель, а первый вкладки", async () => {
    const { result } = setup("v=1&stage=screening&entity=101", { candidates: ALL });
    await waitFor(() => expect(result.current.selectedCandidateId).toBe(C.id));
    expect(result.current.selectedTab).toBe("screening");
    await waitFor(() => expect(result.current.url.get("entity")).toBe("103"));
  });

  it("F5 на вкладке сохраняет вкладку", async () => {
    const { result } = setup("v=1&stage=screening", { candidates: ALL });
    await waitFor(() => expect(result.current.selectedTab).toBe("screening"));
    expect(result.current.selectedCandidateId).toBe(C.id);
  });

  it("клик по вкладке: открыт первый кандидат новой вкладки, адрес ведёт на него", async () => {
    const { result } = setup("v=1", { candidates: ALL });
    await waitFor(() => expect(result.current.selectedCandidateId).toBe(B.id));
    act(() => result.current.selectStageTab("screening"));
    await waitFor(() => expect(result.current.selectedCandidateId).toBe(C.id));
    expect(result.current.url.get("stage")).toBe("screening");
    await waitFor(() => expect(result.current.url.get("entity")).toBe("103"));
  });

  it("перемещённый кандидат остаётся в своей вкладке, пока рекрутёр не уйдёт", async () => {
    const { result, rerender } = setup("v=1&stage=applied&entity=102", { candidates: ALL });
    await waitFor(() => expect(result.current.selectedCandidateId).toBe(B.id));
    // Б перевели в ТЗ — страница ставит «липкость» и обновляет список.
    act(() => result.current.setStickyCandidateId(B.id));
    const moved = [A, { ...B, stage: "screening" } as VacancyApplication, C];
    rerender({ candidates: moved });
    expect(result.current.tabFilteredCandidates.map((c) => c.id)).toContain(B.id);
    expect(result.current.selectedCandidateId).toBe(B.id);
    // Ушёл на другую вкладку — липкость снимается.
    act(() => result.current.selectStageTab("applied"));
    await waitFor(() =>
      expect(result.current.tabFilteredCandidates.map((c) => c.id)).toEqual([A.id]),
    );
  });

  it("поиск ищет по всем вкладкам, а не внутри открытой", async () => {
    const { result, rerender } = setup("v=1&stage=applied", { candidates: ALL });
    await waitFor(() => expect(result.current.selectedTab).toBe("applied"));
    rerender({ candidates: [C], search: "клементьев" });
    expect(result.current.tabFilteredCandidates.map((c) => c.id)).toEqual([C.id]);
  });

  it("счётчики вкладок считают кандидата без колонки в первой колонке — он не пропадает", () => {
    const odd = app(14, 104, "unknown_stage", "2026-10-02T10:00:00");
    const { result } = setup("v=1", { candidates: [...ALL, odd] });
    expect(result.current.groupedByStageMap.applied.map((c) => c.id)).toContain(odd.id);
  });
});

describe("buildFunnelStagesConfig", () => {
  it("по умолчанию — вкладки воронки по общему справочнику", () => {
    expect(stages.keys[0]).toBe("applied");
    expect(stages.labels.screening).toBe("Выполняет ТЗ");
    expect(stages.keys).toContain("reserve");
  });

  it("подпись организации берётся через пару «этап → статус»", () => {
    const cfg = buildFunnelStagesConfig(undefined, { practice: "Созвон с HR" });
    expect(cfg.labels.phone_screen).toBe("Созвон с HR");
  });

  it("свои колонки вакансии: виртуальная колонка показывает этап через maps_to", () => {
    const cfg = buildFunnelStagesConfig(
      [
        { key: "applied", label: "Новый", visible: true },
        { key: "test_task", label: "Тестовое", visible: true, maps_to: "screening" },
        { key: "offer", label: "Оффер", visible: false },
      ],
      {},
    );
    expect(cfg.keys).toEqual(["applied", "test_task"]);
    expect(cfg.enumToKeys.screening).toEqual(["test_task"]);
  });
});
