/**
 * Карточка кандидата у НАБЛЮДАТЕЛЯ (is_readonly), 01.10.2026.
 *
 * Раньше один флаг `readonly` означал сразу две разные вещи: «нельзя нажимать»
 * и «это снапшот влитого дубля, у него нет своей истории». Наблюдателю ставили
 * readonly=true — и он открывал карточку с ПУСТОЙ лентой («Нет действий…»),
 * хотя баннер обещает «вы видите всё». Теперь снапшот — отдельный проп
 * `snapshot`, а readonly только убирает кнопки.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import CandidateVacancyCard from "../CandidateVacancyCard";
import type { KanbanCard } from "@/services/api/candidates";
import type { ActivityEvent } from "@/services/api/entities";

vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/stores/authStore", () => ({
  useAuthStore: () => ({ user: { id: 1, name: "Наблюдатель", role: "member" } }),
}));

vi.mock("@/services/api/entities", () => ({
  downloadEntityFile: vi.fn(),
}));

const STAGES = [
  { status: "new", label: "Новый" },
  { status: "screening", label: "Выполняет ТЗ" },
];

const card = {
  id: 7,
  name: "Гилев Данила",
  created_at: "2026-09-01T10:00:00",
  extra_data: {},
} as unknown as KanbanCard;

const moveEvent: ActivityEvent = {
  id: 555,
  from_stage: "new",
  to_stage: "screening",
  comment: "созвон в четверг",
  changed_by_name: "Тестовый Рекрутёр",
  created_at: "2026-09-23T16:00:00",
};

function renderCard(overrides: Record<string, unknown> = {}) {
  const props = {
    card,
    applicationId: 42,
    vacancyTitle: "User Acquisition Manager",
    currentStage: "screening",
    notes: [],
    events: [moveEvent],
    readonly: true,
    stageOptions: STAGES,
    getStageLabel: (s: string) => STAGES.find((o) => o.status === s)?.label || s,
    onChangeStage: vi.fn(),
    onComment: vi.fn(),
    onDeleteHistory: vi.fn(),
    onUploadFile: vi.fn(),
    onAnketa: vi.fn(),
    ...overrides,
  };
  render(<CandidateVacancyCard {...(props as never)} />);
  return props;
}

describe("Наблюдатель видит ленту целиком", () => {
  beforeEach(() => vi.clearAllMocks());

  it("запись о переводе и её комментарий показываются", () => {
    renderCard();
    expect(screen.getByText("созвон в четверг")).toBeInTheDocument();
    expect(screen.queryByText("Нет действий по выбранным фильтрам")).toBeNull();
  });

  it("фильтр «Действия» остаётся — он только фильтрует ленту", () => {
    renderCard();
    expect(screen.getByRole("button", { name: /Действия: Все/ })).toBeInTheDocument();
  });

  it("менять нечем: ни смены этапа, ни композера, ни чипа «Файл»", () => {
    renderCard();
    expect(screen.queryByRole("button", { name: "Сменить этап подбора" })).toBeNull();
    expect(screen.queryByPlaceholderText("Написать комментарий")).toBeNull();
    expect(screen.queryByText("Файл")).toBeNull();
    // Чип «Анкета» — это окно СОЗДАНИЯ и отправки анкеты, тоже запись.
    expect(screen.queryByText("Анкета")).toBeNull();
    expect(screen.queryByTitle("Действия с записью")).toBeNull();
  });

  it("у живого контейнера без событий остаётся «Кандидат добавлен»", () => {
    renderCard({ events: [], notes: [] });
    expect(screen.getByText("Кандидат добавлен")).toBeInTheDocument();
  });
});

describe("Снапшот влитого дубля (snapshot) — история чужая", () => {
  beforeEach(() => vi.clearAllMocks());

  it("переходы живой заявки в снапшот не попадают", () => {
    renderCard({ snapshot: true, onAnketa: undefined });
    expect(screen.queryByText("созвон в четверг")).toBeNull();
    // И синтетического «Кандидат добавлен» у снапшота тоже нет.
    expect(screen.queryByText("Кандидат добавлен")).toBeNull();
    expect(screen.queryByRole("button", { name: /Действия: Все/ })).toBeNull();
    // Пустой снапшот говорит «Пока нет записей» — фильтров у него нет, и старый
    // текст «Нет действий по выбранным фильтрам» вводил в заблуждение.
    expect(screen.getByText("Пока нет записей")).toBeInTheDocument();
  });
});
