/**
 * Действия карточки кандидата — одни на «Все кандидаты» и на воронку
 * (рефакторинг HR, 20.10.2026). Раньше у каждой страницы была своя копия, и
 * они разъехались: в воронке удаление записи истории без try/catch падало
 * молча, «Запись удалена» не показывалось, а правка комментария не
 * перечитывала ленту. Тест сторожит общие правила.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import toast from "react-hot-toast";

import { useCardActions, type CardActionsEnv } from "../useCardActions";
import * as entities from "@/services/api/entities";
import * as vacancies from "@/services/api/vacancies";
import * as candidates from "@/services/api/candidates";

vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/services/api/entities", () => ({
  addEntityNote: vi.fn(),
  deleteEntityFile: vi.fn(),
  deleteEntityNote: vi.fn(),
  getEntity: vi.fn(),
  setEntityPinnedEntry: vi.fn(),
  toggleTimelineReaction: vi.fn(),
  updateEntityNote: vi.fn(),
  uploadEntityFile: vi.fn(),
}));

vi.mock("@/services/api/vacancies", () => ({
  deleteApplicationHistory: vi.fn(),
  setPinnedEntry: vi.fn(),
  updateApplication: vi.fn(),
  updateApplicationHistory: vi.fn(),
}));

vi.mock("@/services/api/candidates", () => ({
  changeCandidateStatus: vi.fn(),
}));

const api = vi.mocked(entities);
const vac = vi.mocked(vacancies);
const cand = vi.mocked(candidates);

function setup(over: Partial<CardActionsEnv> = {}) {
  let extra: Record<string, unknown> = { notes: [] };
  const env: CardActionsEnv = {
    entityId: 7,
    patchExtra: vi.fn((u) => {
      extra = u(extra);
    }),
    replaceExtra: vi.fn((fresh) => {
      extra = fresh;
    }),
    refreshActivity: vi.fn(async () => {}),
    reloadFiles: vi.fn(),
    noteVacancyId: vi.fn(() => 185),
    onRolledBack: vi.fn(),
    ...over,
  };
  const { result } = renderHook(() => useCardActions(env));
  return { env, actions: () => result.current, extra: () => extra };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getEntity.mockResolvedValue({ extra_data: null } as never);
});

describe("comment", () => {
  it("сохранил — заметка сразу в ленте, привязана к воронке, true", async () => {
    api.addEntityNote.mockResolvedValue({ note: { id: "n1", text: "ок" } } as never);
    const { env, actions, extra } = setup();
    let ok: boolean | undefined;
    await act(async () => {
      ok = await actions().comment(1356, "interview", "Интервью", " ок ");
    });
    expect(ok).toBe(true);
    expect(api.addEntityNote).toHaveBeenCalledWith(
      7,
      expect.objectContaining({ text: "ок", vacancy_id: 185 }),
    );
    expect(extra().notes).toEqual([{ id: "n1", text: "ок" }]);
    expect(env.refreshActivity).toHaveBeenCalled();
  });

  it("сервер не принял — false (поле в карточке не очищается)", async () => {
    api.addEntityNote.mockRejectedValue({ response: { status: 500 } });
    const { actions } = setup();
    let ok: boolean | undefined;
    await act(async () => {
      ok = await actions().comment(1, "new", "Новый", "текст");
    });
    expect(ok).toBe(false);
    expect(toast.error).toHaveBeenCalledWith("Не удалось сохранить комментарий");
  });

  it("слишком длинный — понятное сообщение", async () => {
    api.addEntityNote.mockRejectedValue({
      response: { status: 400, data: { detail: "Comment too long" } },
    });
    const { actions } = setup();
    await act(async () => {
      await actions().comment(1, "new", "Новый", "текст");
    });
    expect(toast.error).toHaveBeenCalledWith("Комментарий слишком длинный — сократите текст");
  });

  it("пустой текст не уходит — кроме записи о переводе вне воронок", async () => {
    api.addEntityNote.mockResolvedValue({ note: { id: "n2", text: "" } } as never);
    const { actions } = setup();
    await act(async () => {
      expect(await actions().comment(0, "new", "Новый", "   ")).toBe(false);
    });
    expect(api.addEntityNote).not.toHaveBeenCalled();
    await act(async () => {
      await actions().comment(0, "practice", "Практика", "", { from_status: "new" });
    });
    expect(api.addEntityNote).toHaveBeenCalledWith(
      7,
      expect.objectContaining({ text: "", from_status: "new" }),
    );
  });

  it("кандидат не выбран — сообщение вместо молчаливого выхода", async () => {
    const { actions } = setup({ entityId: null });
    let ok: boolean | undefined;
    await act(async () => {
      ok = await actions().comment(1, "new", "Новый", "текст");
    });
    expect(ok).toBe(false);
    expect(toast.error).toHaveBeenCalledWith("Кандидат не выбран — обновите страницу и повторите");
  });

  it("архивная воронка (guard) — ничего не отправляем", async () => {
    const { actions } = setup({ isBlocked: () => true });
    await act(async () => {
      expect(await actions().comment(1, "new", "Новый", "текст")).toBe(false);
    });
    expect(api.addEntityNote).not.toHaveBeenCalled();
  });
});

describe("deleteHistory", () => {
  it("удалили последнюю запись — откат, страница переставляет карточку", async () => {
    vac.deleteApplicationHistory.mockResolvedValue({
      success: true,
      rolled_back: true,
      stage: "screening",
      entity_status: "practice",
    });
    const { env, actions } = setup({ onRolledBack: vi.fn(() => "своё сообщение") });
    await act(async () => {
      await actions().deleteHistory(1356, 9);
    });
    expect(env.onRolledBack).toHaveBeenCalledWith({
      appId: 1356,
      stage: "screening",
      entityStatus: "practice",
    });
    expect(toast.success).toHaveBeenCalledWith("своё сообщение");
    expect(env.refreshActivity).toHaveBeenCalled();
  });

  it("старая запись — просто «Запись удалена», этап не трогаем", async () => {
    vac.deleteApplicationHistory.mockResolvedValue({
      success: true,
      rolled_back: false,
      stage: null,
      entity_status: null,
    });
    const { env, actions } = setup();
    await act(async () => {
      await actions().deleteHistory(1356, 3);
    });
    expect(env.onRolledBack).not.toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith("Запись удалена");
  });

  it("сервер отказал — сообщение, а не тихое падение", async () => {
    vac.deleteApplicationHistory.mockRejectedValue(new Error("500"));
    const { env, actions } = setup();
    await act(async () => {
      await actions().deleteHistory(1356, 3);
    });
    expect(toast.error).toHaveBeenCalledWith("Не удалось удалить запись");
    expect(env.refreshActivity).toHaveBeenCalled();
  });
});

describe("deleteNote", () => {
  it("запись о переводе вне воронок — кандидат возвращается назад", async () => {
    api.deleteEntityNote.mockResolvedValue({
      success: true,
      total_notes: 0,
      rolled_back: true,
      entity_status: "new",
    });
    const { env, actions } = setup();
    await act(async () => {
      await actions().deleteNote(7, "n1");
    });
    expect(env.onRolledBack).toHaveBeenCalledWith({
      appId: null,
      stage: null,
      entityStatus: "new",
    });
  });
});

describe("pin", () => {
  it("в воронке — закреп на заявке, вне воронок — на карточке", async () => {
    vac.setPinnedEntry.mockResolvedValue({ pinned_entry_key: "e:1" });
    api.setEntityPinnedEntry.mockResolvedValue({ pinned_entry_key: "n:2" });
    const { actions, extra } = setup();
    await act(async () => {
      await actions().pin(1356, "e:1");
      await actions().pin(0, "n:2");
    });
    expect(vac.setPinnedEntry).toHaveBeenCalledWith(1356, "e:1");
    expect(api.setEntityPinnedEntry).toHaveBeenCalledWith(7, "n:2");
    expect(extra().pinned_entry_key).toBe("n:2");
  });
});

describe("uploadFile", () => {
  it("чип «Файл» везде грузит резюме (текст, дубли, OCR)", async () => {
    api.uploadEntityFile.mockResolvedValue({} as never);
    const { env, actions } = setup();
    const file = new File(["x"], "cv.pdf");
    await act(async () => {
      await actions().uploadFile(7, file);
    });
    expect(api.uploadEntityFile).toHaveBeenCalledWith(7, file, "resume");
    expect(env.reloadFiles).toHaveBeenCalledWith(7);
  });
});

describe("changeApplicationStage", () => {
  it("шлёт этап со сверкой кандидата и отдаёт статус, посчитанный сервером", async () => {
    vac.updateApplication.mockResolvedValue({ entity_status: "probation" } as never);
    const { actions } = setup();
    let res;
    await act(async () => {
      res = await actions().changeApplicationStage(1356, "probation", "вышел");
    });
    expect(vac.updateApplication).toHaveBeenCalledWith(1356, {
      stage: "probation",
      comment: "вышел",
      expected_entity_id: 7,
    });
    expect(res).toEqual({ ok: true, entityStatus: "probation" });
  });

  it("409 — текст сервера, перевода нет", async () => {
    vac.updateApplication.mockRejectedValue({
      response: { status: 409, data: { detail: "Карточка кандидата устарела — обновите страницу и повторите" } },
    });
    const { actions } = setup();
    let res;
    await act(async () => {
      res = await actions().changeApplicationStage(1356, "rejected");
    });
    expect(res).toEqual({ ok: false, entityStatus: null });
    expect(toast.error).toHaveBeenCalledWith("Карточка кандидата устарела — обновите страницу и повторите");
  });

  it("кандидат не выбран — запрос без сверки не уходит", async () => {
    const { actions } = setup({ entityId: null });
    await act(async () => {
      await actions().changeApplicationStage(1356, "rejected");
    });
    expect(vac.updateApplication).not.toHaveBeenCalled();
  });
});

describe("changeStatusOutOfFunnel", () => {
  it("один запрос: перевод и запись в ленте приходят вместе", async () => {
    const note = { id: "n9", text: "созвон", stage: "practice", from_status: "new" };
    cand.changeCandidateStatus.mockResolvedValue({
      success: true,
      entity_status: "practice",
      application_id: null,
      note,
    });
    const { actions, extra } = setup();
    let res;
    await act(async () => {
      res = await actions().changeStatusOutOfFunnel("practice", "Практика", " созвон ");
    });
    expect(cand.changeCandidateStatus).toHaveBeenCalledWith(7, "practice", {
      comment: "созвон",
      stage_label: "Практика",
    });
    expect(api.addEntityNote).not.toHaveBeenCalled();
    expect(extra().notes).toEqual([note]);
    expect(res).toEqual({ ok: true, entityStatus: "practice" });
  });

  it("сервер отказал — ни записи, ни перевода", async () => {
    cand.changeCandidateStatus.mockRejectedValue({ response: { status: 500 } });
    const { actions, extra } = setup();
    let res;
    await act(async () => {
      res = await actions().changeStatusOutOfFunnel("practice", "Практика");
    });
    expect(res).toEqual({ ok: false, entityStatus: null });
    expect(extra().notes).toEqual([]);
    expect(toast.error).toHaveBeenCalledWith("Не удалось сменить этап");
  });
});
