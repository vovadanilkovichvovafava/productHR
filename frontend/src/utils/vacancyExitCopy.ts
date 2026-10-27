import type { Vacancy } from "@/types";
import { isVacancyParticipant, otherActiveParticipants } from "@/utils/vacancy";

// Вопросы подтверждения «Выйти» / «Закрыть» вакансии — одни на «Мои
// вакансии», форму вакансии и «Заявки»; раньше каждая страница писала свои
// (рефакторинг HR, 20.10.2026). Различаются только слова: в воронках —
// «вакансия», в разделе заявок — «заявка».

export type VacancyExitAction = "leave" | "close";
export type VacancyExitNoun = "vacancy" | "request";

export interface VacancyExitCopy {
  title: string;
  text: string;
  confirmLabel: string;
}

const WORDS: Record<VacancyExitNoun, { leave: string; closeAll: string; close: string }> = {
  vacancy: {
    leave: "Вы действительно хотите выйти из вакансии?",
    closeAll: "Вы действительно хотите закрыть вакансию для всех?",
    close: "Вы действительно хотите закрыть вакансию?",
  },
  request: {
    leave: "Вы действительно хотите выйти из заявки?",
    closeAll: "Вы действительно хотите закрыть заявку для всех?",
    close: "Вы действительно хотите закрыть заявку?",
  },
};

export function vacancyExitCopy(
  action: VacancyExitAction,
  vacancy: Vacancy,
  userId: number | undefined | null,
  noun: VacancyExitNoun,
): VacancyExitCopy {
  const w = WORDS[noun];
  // Только вопрос, без пояснений (владелец 20.10.2026: «слишком много
  // текста… надпись „Выйти из вакансии“ и так даёт понять»). Название
  // вакансии окно показывает само. «Для всех» остаётся в вопросе, когда в
  // вакансии работает кто-то кроме вас (или вы её не ведёте вовсе).
  if (action === "leave") return { title: w.leave, text: "", confirmLabel: "Выйти" };
  const total = otherActiveParticipants(vacancy, userId).length + (isVacancyParticipant(vacancy, userId) ? 1 : 0);
  return total > 1
    ? { title: w.closeAll, text: "", confirmLabel: "Закрыть для всех" }
    : { title: w.close, text: "", confirmLabel: "Закрыть" };
}
