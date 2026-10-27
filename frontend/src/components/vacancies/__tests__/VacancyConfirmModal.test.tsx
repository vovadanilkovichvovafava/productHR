/**
 * Окно «Выйти / Закрыть / Удалить» вакансию (VacancyConfirmModal, 20.10.2026).
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import VacancyConfirmModal from "../VacancyConfirmModal";
import type { Vacancy } from "@/types";

const shared = { id: 1, title: "Трафик", created_by: 1, assigned_to: [2, 3], extra_data: {} } as unknown as Vacancy;

describe("VacancyConfirmModal", () => {
  it("админ не участник закрывает общую вакансию — «для всех», а не «вы последний»", () => {
    render(<VacancyConfirmModal action="close" vacancy={shared} userId={99} busy={false} onCancel={() => {}} onConfirm={() => {}} />);
    expect(screen.getByText("Вы действительно хотите закрыть вакансию для всех?")).toBeTruthy();
    expect(screen.getByText("Закрыть для всех")).toBeTruthy();
    expect(screen.queryByText(/последний/)).toBeNull();
  });

  it("название вакансии в окне, кнопки работают, пока не занято", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<VacancyConfirmModal action="leave" vacancy={shared} userId={2} busy={false} onCancel={onCancel} onConfirm={onConfirm} />);
    expect(screen.getByText("Вы действительно хотите выйти из вакансии?")).toBeTruthy();
    expect(screen.getByText("«Трафик»")).toBeTruthy();
    fireEvent.click(screen.getByText("Выйти"));
    fireEvent.click(screen.getByText("Отмена"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("удаление предупреждает, что действие не отменить; во время запроса кнопки заблокированы", () => {
    render(<VacancyConfirmModal action="delete" vacancy={shared} userId={2} busy onCancel={() => {}} onConfirm={() => {}} />);
    expect(screen.getByText("Удалить вакансию?")).toBeTruthy();
    expect(screen.getByText(/нельзя отменить/)).toBeTruthy();
    expect((screen.getByText("Применяем…") as HTMLButtonElement).disabled).toBe(true);
  });
});
