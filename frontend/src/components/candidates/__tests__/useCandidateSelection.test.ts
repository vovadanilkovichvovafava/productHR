/**
 * Кто открыт справа на «Все кандидаты» (useCandidateSelection, 20.10.2026).
 *
 * Эти правила ломались чаще всего и до выноса проверялись только руками в
 * браузере: «справа чужая карточка после поиска» (Мария, 09.10), «ссылка из
 * расширения открыла не того» (Эльвира, 18.09), «фоновое обновление выкинуло
 * из карточки во время правки», «после добавления открыт прежний».
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useCallback, useState } from "react";
import toast from "react-hot-toast";

import { useCandidateSelection } from "../useCandidateSelection";
import type { KanbanBoardResponse, KanbanCard } from "@/services/api/candidates";
import type { VisibleCard } from "@/components/entities/candidateDetail/model";
import * as entities from "@/services/api/entities";

vi.mock("react-hot-toast", () => {
  const t = Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() });
  return { default: t };
});
vi.mock("@/services/api/entities", () => ({ getEntity: vi.fn() }));

const api = vi.mocked(entities);

const card = (id: number, name = `Кандидат ${id}`) =>
  ({ id, name, created_at: "2026-10-01T10:00:00" }) as unknown as KanbanCard;
const visible = (...cards: KanbanCard[]): VisibleCard[] =>
  cards.map((c) => ({ card: c, status: "new", label: "Новый" }));
// Новый объект доски = новый ответ сервера (поллинг, смена запроса).
const newBoard = () => ({ columns: [] }) as unknown as KanbanBoardResponse;

type Props = {
  board: KanbanBoardResponse | null;
  boardStale: boolean;
  filteredCards: VisibleCard[];
  activeTab: string;
  search: string;
};

function setup(initialUrl: string, initial: Props) {
  const onEdit = vi.fn();
  const onAnketa = vi.fn();
  const hook = renderHook(
    (props: Props) => {
      const [sp, setSp] = useState(() => new URLSearchParams(initialUrl));
      const setSearchParams = useCallback(
        (
          next: URLSearchParams | ((prev: URLSearchParams) => URLSearchParams),
        ) => setSp((prev) => (typeof next === "function" ? next(prev) : next)),
        [],
      );
      const sel = useCandidateSelection({
        ...props,
        scope: "all",
        searchParams: sp,
        setSearchParams,
        onEditRequested: onEdit,
        onAnketaRequested: onAnketa,
      });
      return { ...sel, url: sp.toString(), setUrl: setSp };
    },
    { initialProps: initial },
  );
  return { ...hook, onEdit, onAnketa };
}

const A = card(1, "Правдецкая");
const B = card(2, "Муравьёва");
const C = card(3, "Клементьев");

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useCandidateSelection", () => {
  it("первая загрузка без ссылки — открыт первый в списке, адрес ведёт на него", async () => {
    const { result } = setup("", {
      board: newBoard(), boardStale: false, filteredCards: visible(A, B), activeTab: "all", search: "",
    });
    expect(result.current.selectedCard?.id).toBe(A.id);
    await waitFor(() => expect(result.current.url).toBe("entity=1"));
  });

  it("ссылка ?entity= на кандидата с доски — открыт он", () => {
    const { result } = setup("entity=2", {
      board: newBoard(), boardStale: false, filteredCards: visible(A, B), activeTab: "all", search: "",
    });
    expect(result.current.selectedCard?.id).toBe(B.id);
  });

  it("ссылка на кандидата, которого нет на доске, — грузим и открываем ЕГО, не прошлого", async () => {
    api.getEntity.mockResolvedValue({ id: 3, name: "Клементьев", status: "transferred" } as never);
    const { result } = setup("entity=3", {
      board: newBoard(), boardStale: false, filteredCards: visible(A, B), activeTab: "all", search: "",
    });
    await waitFor(() => expect(result.current.selectedCard?.id).toBe(3));
    expect(api.getEntity).toHaveBeenCalledWith(3);
    expect(result.current.url).toBe("entity=3");
    expect(toast).toHaveBeenCalledWith(
      expect.stringContaining("Карточка открыта отдельно"),
      expect.anything(),
    );
  });

  it("только что добавленный — открываем без объяснения «открыта отдельно»", async () => {
    api.getEntity.mockResolvedValue({ id: 3, name: "Клементьев", status: "new" } as never);
    const { result, rerender } = setup("", {
      board: newBoard(), boardStale: false, filteredCards: visible(A), activeTab: "all", search: "",
    });
    act(() => {
      result.current.justCreatedRef.current = 3;
    });
    // Страница переписывает адрес на нового (openCandidateCard).
    act(() => {
      result.current.openCandidate(C, "new");
    });
    rerender({ board: newBoard(), boardStale: false, filteredCards: visible(A), activeTab: "all", search: "" });
    expect(result.current.selectedCard?.id).toBe(3);
    expect(toast).not.toHaveBeenCalled();
  });

  it("фоновое обновление доски не уводит с открытой карточки", () => {
    const { result, rerender } = setup("entity=2", {
      board: newBoard(), boardStale: false, filteredCards: visible(A, B), activeTab: "all", search: "",
    });
    expect(result.current.selectedCard?.id).toBe(B.id);
    // Поллинг 15с: та же вкладка и поиск, а кандидат уже не совпадает (правят имя).
    rerender({ board: newBoard(), boardStale: false, filteredCards: visible(A), activeTab: "all", search: "" });
    expect(result.current.selectedCard?.id).toBe(B.id);
  });

  it("поиск без находок закрывает открытую карточку (Мария, 09.10.2026)", async () => {
    const { result, rerender } = setup("", {
      board: newBoard(), boardStale: false, filteredCards: visible(A, B), activeTab: "all", search: "",
    });
    await waitFor(() => expect(result.current.url).toBe("entity=1"));
    // Набрали запрос — пока доска старая, ничего не трогаем.
    rerender({ board: newBoard(), boardStale: true, filteredCards: visible(A, B), activeTab: "all", search: "елизавета муравьева" });
    expect(result.current.selectedCard?.id).toBe(A.id);
    // Пришёл ответ: никого.
    rerender({ board: newBoard(), boardStale: false, filteredCards: [], activeTab: "all", search: "елизавета муравьева" });
    expect(result.current.selectedCard).toBeNull();
  });

  it("поиск с находками, где нет открытого, — открывается первая находка", async () => {
    const { result, rerender } = setup("", {
      board: newBoard(), boardStale: false, filteredCards: visible(A, B), activeTab: "all", search: "",
    });
    await waitFor(() => expect(result.current.url).toBe("entity=1"));
    rerender({ board: newBoard(), boardStale: false, filteredCards: visible(C, B), activeTab: "all", search: "клем" });
    expect(result.current.selectedCard?.id).toBe(C.id);
  });

  it("клик по кандидату — открыт он, и в адрес идёт его id", async () => {
    const { result } = setup("", {
      board: newBoard(), boardStale: false, filteredCards: visible(A, B), activeTab: "all", search: "",
    });
    act(() => {
      result.current.openCandidate(B, "new");
    });
    expect(result.current.selectedCard?.id).toBe(B.id);
    await waitFor(() => expect(result.current.url).toBe("entity=2"));
  });

  it("?edit=1 открывает окно правки и пропадает из адреса, ссылка остаётся", async () => {
    const { result, onEdit } = setup("entity=2&edit=1", {
      board: newBoard(), boardStale: false, filteredCards: visible(A, B), activeTab: "all", search: "",
    });
    expect(onEdit).toHaveBeenCalled();
    await waitFor(() => expect(result.current.url).toBe("entity=2"));
  });

  it("смена вкладки на пустую закрывает карточку", () => {
    const { result, rerender } = setup("entity=1", {
      board: newBoard(), boardStale: false, filteredCards: visible(A, B), activeTab: "all", search: "",
    });
    // Клик по вкладке в странице — одно действие: вкладка + ?stage= без
    // ?entity= (setActiveTab) + снятие выбора.
    act(() => {
      result.current.setUrl(new URLSearchParams("stage=reserve"));
      result.current.setSelectedCard(null);
      rerender({ board: newBoard(), boardStale: false, filteredCards: [], activeTab: "reserve", search: "" });
    });
    expect(result.current.selectedCard).toBeNull();
    expect(result.current.url).toBe("stage=reserve");
  });
});
