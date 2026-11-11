import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { CatalogPicker, PICKER_COLORS, canLeaveDepartment, colorPill, menuPosFor, sourcerOptions } from "../StatusesPage";

// Окно-список доски «Штат» — одно на все выпадающие (11.11.2026). Сторожим
// мелочи, найденные при проверке: окно с несколькими значениями не
// закрывается, поэтому поиск надо чистить самим, а Enter на имени уже
// выбранного пункта должен снимать ЕГО, а не ставить первый из остальных.
const setup = (selected: string[] = ["1"]) => {
  const onPick = vi.fn();
  const onAdd = vi.fn();
  render(
    <CatalogPicker
      menuRef={createRef<HTMLDivElement>()}
      pos={{ top: 0, left: 0 }}
      placeholder="Найти или добавить…"
      groups={[{ label: "Сорсеры", options: [
        { key: "1", label: "Аня", editable: true },
        { key: "2", label: "Боря", editable: true },
      ] }]}
      taken={["Аня", "Боря"]}
      selected={selected}
      onPick={onPick}
      onAdd={onAdd}
      onRename={vi.fn()}
      onDelete={vi.fn()}
    />,
  );
  return { onPick, onAdd, input: screen.getByPlaceholderText("Найти или добавить…") as HTMLInputElement };
};

describe("CatalogPicker", () => {
  it("Enter на имени выбранного снимает его самого", () => {
    const { onPick, input } = setup();
    fireEvent.change(input, { target: { value: "аня" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onPick).toHaveBeenCalledWith("1");
  });

  it("у выбранного справа «×» — клик снимает его с человека", () => {
    const { onPick } = setup(["1"]);
    fireEvent.click(screen.getByLabelText("Снять"));
    expect(onPick).toHaveBeenCalledWith("1");
  });

  it("закрытый список (HR): без «Добавить» и без «…», свой заголовок выбранных", () => {
    const onPick = vi.fn();
    render(
      <CatalogPicker
        menuRef={createRef<HTMLDivElement>()}
        pos={{ top: 0, left: 0, maxHeight: 360 }}
        placeholder="Поиск…"
        groups={[{ label: "Люди", options: [
          { key: "1", label: "Эльвира", avatar: <span>Э</span> },
          { key: "2", label: "Мария", avatar: <span>М</span> },
        ] }]}
        taken={[]}
        selected={["1"]}
        selectedLabel="Назначены"
        onPick={onPick}
      />,
    );
    expect(screen.getByText("Назначены")).toBeTruthy();
    expect(screen.queryByText(/Добавить/)).toBeNull();
    expect(screen.queryByLabelText(/Настроить/)).toBeNull();
    const input = screen.getByPlaceholderText("Поиск…");
    fireEvent.change(input, { target: { value: "Новый человек" } });
    expect(screen.queryByText(/Добавить/)).toBeNull();
    expect(screen.getByText("Ничего не найдено")).toBeTruthy();
    fireEvent.change(input, { target: { value: "мар" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onPick).toHaveBeenCalledWith("2");
  });

  it("после «Добавить» поиск пустеет и остальные пункты снова видны", () => {
    const { onAdd, input } = setup();
    fireEvent.change(input, { target: { value: "Вера" } });
    expect(screen.queryByText("Боря")).toBeNull();
    fireEvent.click(screen.getByText(/Добавить «Вера»/));
    expect(onAdd).toHaveBeenCalledWith("Вера");
    expect(input.value).toBe("");
    expect(screen.getByText("Боря")).toBeTruthy();
  });

  it("после выбора пункта поиск тоже пустеет", () => {
    const { onPick, input } = setup([]);
    fireEvent.change(input, { target: { value: "бор" } });
    fireEvent.click(screen.getByText("Боря"));
    expect(onPick).toHaveBeenCalledWith("2");
    expect(input.value).toBe("");
  });

  it("«Добавить» видна всегда: без текста — подсказка, с текстом — над списком", () => {
    const { input } = setup([]);
    expect(screen.getByText(/введите название/)).toBeTruthy();
    fireEvent.change(input, { target: { value: "Вера" } });
    expect(screen.queryByText(/введите название/)).toBeNull();
    const add = screen.getByText(/Добавить «Вера»/);
    // Сразу под поиском — раньше, чем любой пункт списка.
    expect(input.nextElementSibling?.textContent).toContain("Добавить «Вера»");
    expect(add).toBeTruthy();
  });

  it("пустой список подсказывает, как добавить", () => {
    render(
      <CatalogPicker
        menuRef={createRef<HTMLDivElement>()}
        pos={{ top: 0, left: 0 }}
        placeholder="Найти…"
        groups={[{ label: "Руководители", options: [] }]}
        taken={[]}
        onPick={vi.fn()}
        onAdd={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/Список пуст/)).toBeTruthy();
  });
});

// Окошко «…» у пункта — как в ClickUp (скрин клиента, 11.11.2026): сразу
// поле с названием, палитра, «Мои цвета», «Удалить».
describe("окошко «…»", () => {
  const open = (extra: { noDelete?: boolean } = {}) => {
    const fns = { onRename: vi.fn(), onDelete: vi.fn(), onRecolor: vi.fn(), onReorder: vi.fn() };
    render(
      <CatalogPicker
        menuRef={createRef<HTMLDivElement>()}
        pos={{ top: 0, left: 0, maxHeight: 360 }}
        placeholder="Найти или добавить отдел…"
        groups={[{ label: "Отделы", options: [
          { key: "1", label: "SANDBOX", editable: true, ...extra },
          { key: "2", label: "SEO отдел", editable: true },
        ] }]}
        taken={["SANDBOX", "SEO отдел"]}
        onPick={vi.fn()}
        onAdd={vi.fn()}
        {...fns}
      />,
    );
    fireEvent.click(screen.getByLabelText("Настроить «SANDBOX»"));
    return { ...fns, name: screen.getByLabelText("Название") as HTMLInputElement };
  };

  it("сразу поле с названием; Enter — переименовать", async () => {
    const { onRename, name } = open();
    expect(name.value).toBe("SANDBOX");
    fireEvent.change(name, { target: { value: "SANDBOX 2" } });
    fireEvent.keyDown(name, { key: "Enter" });
    await vi.waitFor(() => expect(onRename).toHaveBeenCalledWith("1", "SANDBOX 2"));
    expect(screen.queryByLabelText("Название")).toBeNull();
  });

  it("Escape — закрыть без переименования", async () => {
    const { onRename, name } = open();
    fireEvent.change(name, { target: { value: "Другое" } });
    fireEvent.keyDown(name, { key: "Escape" });
    await Promise.resolve();
    expect(onRename).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Название")).toBeNull();
  });

  it("клик мимо окошка — название сохраняется", async () => {
    const { onRename, name } = open();
    fireEvent.change(name, { target: { value: "Песочница" } });
    fireEvent.mouseDown(document.body);
    await vi.waitFor(() => expect(onRename).toHaveBeenCalledWith("1", "Песочница"));
  });

  it("палитра 4×6: «без цвета» + 23 цвета; клик красит, окошко остаётся", () => {
    const { onRecolor } = open();
    expect(PICKER_COLORS).toHaveLength(23);
    fireEvent.click(screen.getByLabelText(`Цвет ${PICKER_COLORS[0]}`));
    expect(onRecolor).toHaveBeenCalledWith("1", PICKER_COLORS[0]);
    fireEvent.click(screen.getByLabelText("Без цвета"));
    expect(onRecolor).toHaveBeenLastCalledWith("1", null);
    expect(screen.getByLabelText("Название")).toBeTruthy();
    expect(screen.getByText("Мои цвета")).toBeTruthy();
  });

  it("«Удалить» — сначала окно «удаление из всей системы», удаляет только по подтверждению", () => {
    const { onDelete } = open();
    fireEvent.click(screen.getByText("Удалить"));
    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog").textContent).toContain("удаление из всей системы");
    fireEvent.click(screen.getByText("Отмена"));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(onDelete).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("Настроить «SANDBOX»"));
    fireEvent.click(screen.getByText("Удалить"));
    fireEvent.click(screen.getByText("Удалить из системы"));
    expect(onDelete).toHaveBeenCalledWith("1", "SANDBOX");
  });

  it("Escape в окне подтверждения — отмена, без удаления", () => {
    const { onDelete } = open();
    fireEvent.click(screen.getByText("Удалить"));
    fireEvent.keyDown(screen.getByText("Отмена"), { key: "Escape" });
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("у песочницы «Удалить» нет", () => {
    open({ noDelete: true });
    expect(screen.queryByText("Удалить")).toBeNull();
  });
});

describe("sourcerOptions", () => {
  const tag = (id: number, name: string, archived = false) =>
    ({ id, org_id: 1, name, color: "#d73f7b", created_by: null, created_at: null, archived_at: archived ? "2026-11-11" : null });

  it("сорсер у человека, которого нет в справочнике (архивный), всё равно в окне — его можно снять и удалить", () => {
    const opts = sourcerOptions([tag(1, "Валя")], [{ id: 7, name: "тестовый", color: "#d73f7b" }]);
    expect(opts.map((o) => o.label)).toEqual(["Валя", "тестовый"]);
    expect(opts.find((o) => o.key === "7")?.editable).toBe(true);
  });

  it("архивный, которого у человека нет, — не предлагается", () => {
    expect(sourcerOptions([tag(1, "Валя"), tag(2, "Старый", true)], []).map((o) => o.label)).toEqual(["Валя"]);
  });
});

describe("colorPill", () => {
  it("заливка цветом, текст тёмный на светлом и белый на тёмном", () => {
    expect(colorPill("#f6c844")).toMatchObject({ background: "#f6c844", color: "#1f2328" });
    expect(colorPill("#3f5ed8")).toMatchObject({ background: "#3f5ed8", color: "#ffffff" });
  });
});

// Строка «— убрать» в окне отдела (как «–» в ClickUp, 11.11.2026) — то же,
// что крестик на ячейке: из отдела можно, из песочницы — нет.
describe("canLeaveDepartment", () => {
  it("из отдела убрать может любой HR", () => {
    expect(canLeaveDepartment({ placement_id: 5, department_is_sandbox: false }, false)).toBe(true);
  });
  it("из песочницы — только админ", () => {
    expect(canLeaveDepartment({ placement_id: 5, department_is_sandbox: true }, false)).toBe(false);
    expect(canLeaveDepartment({ placement_id: 5, department_is_sandbox: true }, true)).toBe(true);
  });
  it("без отдела убирать нечего", () => {
    expect(canLeaveDepartment({ placement_id: null, department_is_sandbox: false }, true)).toBe(false);
  });
  it("строка «— убрать» стоит над списком и зовёт onClear", () => {
    const onClear = vi.fn();
    render(
      <CatalogPicker
        menuRef={createRef<HTMLDivElement>()}
        pos={{ top: 0, left: 0 }}
        placeholder="Найти или добавить отдел…"
        groups={[{ label: "Отделы", options: [{ key: "7", label: "SEO отдел", editable: true }] }]}
        taken={["SEO отдел"]}
        current="7"
        onPick={vi.fn()}
        onAdd={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onClear={onClear}
        clearLabel="— убрать из «SANDBOX»"
      />,
    );
    fireEvent.click(screen.getByText("— убрать из «SANDBOX»"));
    expect(onClear).toHaveBeenCalled();
  });
});

describe("menuPosFor", () => {
  it("места снизу хватает — под ячейкой", () => {
    expect(menuPosFor({ top: 100, bottom: 120, left: 50 }, 860)).toEqual({ top: 124, left: 50, maxHeight: 360 });
  });
  it("нижняя строка — окно открывается вверх и не уходит за экран", () => {
    const p = menuPosFor({ top: 760, bottom: 790, left: 50 }, 860);
    expect(p.top).toBeUndefined();
    expect(p.bottom).toBe(860 - 760 + 4);
    expect(p.maxHeight).toBe(360);
  });
});
