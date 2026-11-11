import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { CatalogPicker, menuPosFor } from "../StatusesPage";

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
