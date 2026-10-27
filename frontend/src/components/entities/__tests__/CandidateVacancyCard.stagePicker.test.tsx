/**
 * Окно «Сменить этап подбора» (23.09.2026, по видео Huntflow).
 *
 * Проверяем ровно то, что просил владелец:
 *  1) выбран текущий этап → серая плашка вместо поля комментария, «Сохранить» недоступно;
 *  2) при открытии помечен СЛЕДУЮЩИЙ этап;
 *  3) перевод не перезагружает карточку — onChangeStage зовётся с выбранным этапом,
 *     а комментарий уходит отдельным вызовом только если его написали;
 *  4) корзина у записи истории зовёт onDeleteHistory (откат этапа делает бэкенд).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CandidateVacancyCard from "../CandidateVacancyCard";
import type { KanbanCard } from "@/services/api/candidates";
import type { ActivityEvent } from "@/services/api/entities";

vi.mock("react-hot-toast", () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/stores/authStore", () => ({
  useAuthStore: () => ({ user: { id: 1, name: "Тестовый Рекрутёр", role: "hr" } }),
}));

vi.mock("@/services/api/entities", () => ({
  downloadEntityFile: vi.fn(),
}));

// Богатый редактор в jsdom не набирается — подменяем обычным textarea с тем же
// контрактом (value/onChange), чтобы проверять сам пикер, а не contenteditable.
vi.mock("@/components/hr/HuntflowRichInput", () => ({
  HuntflowRichInput: ({
    value,
    onChange,
    placeholder,
  }: {
    value: string;
    onChange: (v: string) => void;
    placeholder?: string;
  }) => (
    <textarea
      aria-label={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
}));

const STAGES = [
  { status: "new", label: "Новый" },
  { status: "screening", label: "Выполняет ТЗ" },
  { status: "practice", label: "Интервью с HR" },
  { status: "rejected", label: "Отказ" },
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
  comment: null,
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
    readonly: false,
    stageOptions: STAGES,
    getStageLabel: (s: string) =>
      STAGES.find((o) => o.status === s)?.label || s,
    onChangeStage: vi.fn().mockResolvedValue(true),
    onComment: vi.fn().mockResolvedValue(undefined),
    onDeleteHistory: vi.fn().mockResolvedValue(undefined),
    onUploadFile: vi.fn(),
    ...overrides,
  };
  render(<CandidateVacancyCard {...(props as never)} />);
  return props;
}

const openPicker = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(screen.getByRole("button", { name: "Сменить этап подбора" }));
};

const pickerOption = (label: string) =>
  screen
    .getAllByRole("button", { name: label })
    .find((el) => el.className.includes("hf-stage-picker-option"))!;

describe("Пикер этапа: серая плашка на текущем этапе", () => {
  beforeEach(() => vi.clearAllMocks());

  it("выбран текущий этап — вместо комментария плашка, «Сохранить» недоступно", async () => {
    const user = userEvent.setup();
    renderCard();
    await openPicker(user);

    await user.click(pickerOption("Выполняет ТЗ")); // это и есть текущий этап

    expect(
      screen.getByText("Кандидат сейчас находится на этом этапе подбора"),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Записать комментарий")).toBeNull();
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();
  });

  it("клик по «Сохранить» на текущем этапе ничего не отправляет", async () => {
    const user = userEvent.setup();
    const props = renderCard();
    await openPicker(user);
    await user.click(pickerOption("Выполняет ТЗ"));
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(props.onChangeStage).not.toHaveBeenCalled();
    expect(props.onComment).not.toHaveBeenCalled();
  });
});

describe("Пикер этапа: помечен следующий этап", () => {
  beforeEach(() => vi.clearAllMocks());

  it("при открытии подсвечен следующий этап, а не текущий", async () => {
    const user = userEvent.setup();
    renderCard();
    await openPicker(user);

    expect(pickerOption("Интервью с HR").className).toContain(
      "hf-stage-picker-option-active",
    );
    expect(pickerOption("Выполняет ТЗ").className).toContain(
      "hf-stage-picker-option-idle",
    );
    // Комментарий доступен сразу — переводить есть куда.
    expect(screen.getByLabelText("Записать комментарий")).toBeInTheDocument();
  });

  it("кандидат на последнем рабочем этапе — «Отказ» сам не подставляется", async () => {
    const user = userEvent.setup();
    renderCard({ currentStage: "practice" });
    await openPicker(user);

    expect(pickerOption("Интервью с HR").className).toContain(
      "hf-stage-picker-option-active",
    );
    expect(
      screen.getByText("Кандидат сейчас находится на этом этапе подбора"),
    ).toBeInTheDocument();
  });
});

describe("Пикер этапа: сохранение перевода", () => {
  beforeEach(() => vi.clearAllMocks());

  it("переводит на выбранный этап и закрывает пикер, комментарий не пишет", async () => {
    const user = userEvent.setup();
    const props = renderCard();
    await openPicker(user);
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() =>
      expect(props.onChangeStage).toHaveBeenCalledWith(42, "practice", undefined),
    );
    expect(props.onComment).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.queryByLabelText("Записать комментарий")).toBeNull(),
    );
  });

  it("комментарий уходит ВМЕСТЕ с переводом, отдельной заметкой не сохраняется", async () => {
    // Раньше он писался отдельной заметкой, и в ленте появлялись ДВЕ строки об
    // одном событии — на это и жаловались рекрутёры (24.09.2026).
    const user = userEvent.setup();
    const props = renderCard();
    await openPicker(user);
    await user.type(screen.getByLabelText("Записать комментарий"), "ок");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() =>
      expect(props.onChangeStage).toHaveBeenCalledWith(42, "practice", "ок"),
    );
    expect(props.onComment).not.toHaveBeenCalled();
  });

  it("перевод не применился — комментарий не сохраняется, пикер остаётся открытым", async () => {
    const user = userEvent.setup();
    const props = renderCard({ onChangeStage: vi.fn().mockResolvedValue(false) });
    await openPicker(user);
    await user.type(screen.getByLabelText("Записать комментарий"), "ок");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(props.onChangeStage).toHaveBeenCalled());
    expect(props.onComment).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Записать комментарий")).toBeInTheDocument();
  });
});

describe("Строка ленты: статус, комментарий и меню", () => {
  beforeEach(() => vi.clearAllMocks());

  const openRowMenu = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(screen.getAllByTitle("Действия с записью")[0]);
  };

  it("показывает статус и комментарий одной строкой, без стрелок", () => {
    renderCard({
      events: [{ ...moveEvent, comment: "созвон в четверг" }],
    });
    expect(screen.getByText("созвон в четверг")).toBeInTheDocument();
    // Ни стрелки «Новый → Выполняет ТЗ», ни приставки «Этап:» в ленте нет.
    expect(screen.queryByText(/→/)).toBeNull();
    expect(screen.queryByText(/Этап:/)).toBeNull();
  });

  it("прежний этап не пропал — он в подсказке при наведении", () => {
    renderCard();
    expect(screen.getByTitle("Перевели из этапа «Новый»")).toBeInTheDocument();
  });

  it("«Изменено» и своя подсказка с автором и временем правки", () => {
    // Подсказка СВОЯ, а не нативный title: браузерная всплывает через секунду,
    // а рекрутёру нужно сразу (24.09.2026).
    renderCard({
      events: [
        {
          ...moveEvent,
          comment: "правленый текст",
          edited_at: "2026-09-24T10:15:00",
          edited_by_name: "Настя",
        },
      ],
    });
    expect(screen.getByText("· Изменено")).toBeInTheDocument();
    const tip = screen.getByText(/Изменено: Настя/);
    expect(tip.textContent).toContain("GMT");
    expect(tip.className).toContain("group-hover/timeline:block");
  });

  it("удаление живёт в меню по шеврону", async () => {
    const user = userEvent.setup();
    const props = renderCard();
    await openRowMenu(user);
    await user.click(screen.getByRole("button", { name: /Удалить/ }));
    expect(props.onDeleteHistory).toHaveBeenCalledWith(42, 555);
  });

  it("закрепляет запись", async () => {
    const user = userEvent.setup();
    const props = renderCard({ onPin: vi.fn(), pinnedEntryKey: null });
    await openRowMenu(user);
    await user.click(screen.getByRole("button", { name: /Закрепить/ }));
    expect(props.onPin).toHaveBeenCalledWith(42, "e:555");
  });

  it("закреплённая помечена и откреплается тем же пунктом меню", async () => {
    const user = userEvent.setup();
    const props = renderCard({ onPin: vi.fn(), pinnedEntryKey: "e:555" });
    expect(screen.getByText("Закреплено")).toBeInTheDocument();
    await openRowMenu(user);
    await user.click(screen.getByRole("button", { name: /Открепить/ }));
    expect(props.onPin).toHaveBeenCalledWith(42, null);
  });

  it("правка записи о переводе уходит в onEditHistory", async () => {
    const user = userEvent.setup();
    const props = renderCard({
      onEditHistory: vi.fn(),
      events: [{ ...moveEvent, comment: "созвон в четверг" }],
    });
    await openRowMenu(user);
    await user.click(screen.getByRole("button", { name: /Редактировать/ }));
    const editor = screen.getByLabelText("Текст комментария");
    await user.clear(editor);
    await user.type(editor, "созвон в пятницу");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(props.onEditHistory).toHaveBeenCalledWith(42, 555, "созвон в пятницу"),
    );
  });
});
