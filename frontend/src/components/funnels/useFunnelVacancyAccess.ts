import { useEffect, useState } from "react";
import { getVacancy } from "@/services/api/vacancies";
import type { Vacancy } from "@/types";

// Воронка, открытая по адресу (?v=), — вынесено из RecruiterFunnelsPage
// (20.10.2026) без изменения поведения.

export function useFunnelVacancyAccess(
  selectedVacancyId: number | null,
  listedVacancy: Vacancy | undefined,
) {
  // ДИПЛИНК НА ВОРОНКУ, КОТОРОЙ НЕТ В СПИСКЕ (?v=<чужая/закрытая/удалённая>).
  // Раньше selectedVacancy молча оставался undefined → страница рисовала обзор
  // СВОИХ воронок с прежним URL, и это читалось как «меня перекинуло на мои же
  // вакансии» (обратная связь Эльвиры, 2026-09-07): отличить «нет прав» от
  // «сломалось» было невозможно, 403 глотался пустым catch в loadCandidates.
  // Теперь спрашиваем воронку точечно (GET /vacancies/{id}):
  //   200 → берём её как fallback (в списке её могло не быть из-за фильтров
  //         стора/пагинации — воронка доступна, просто не попала в выборку);
  //   403 → явный экран «Нет доступа к этой воронке»;
  //   404 → «Воронка не найдена» (удалена или чужая орг).
  // Пока запрос летит, показываем лоадер, а НЕ обзор своих воронок — иначе
  // прежний «отскок на свои ваки» просто мигал бы перед экраном ошибки.
  const [probedVacancy, setProbedVacancy] = useState<Vacancy | null>(null);
  const [vacancyAccessError, setVacancyAccessError] = useState<'forbidden' | 'missing' | null>(null);
  const [vacancyProbing, setVacancyProbing] = useState(false);

  useEffect(() => {
    if (!selectedVacancyId || listedVacancy) {
      setProbedVacancy(null);
      setVacancyAccessError(null);
      setVacancyProbing(false);
      return;
    }
    // Уже разрешили этот id — не долбим бэк на каждый ре-рендер.
    if (probedVacancy?.id === selectedVacancyId) return;
    let cancelled = false;
    setVacancyProbing(true);
    setVacancyAccessError(null);
    getVacancy(selectedVacancyId)
      .then((v) => {
        if (cancelled) return;
        setProbedVacancy(v);
        setVacancyAccessError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const status = (err as { response?: { status?: number } })?.response?.status;
        setProbedVacancy(null);
        // Сетевую ошибку не выдаём за отказ в доступе — для неё остаётся
        // прежнее поведение (обзор воронок), иначе оффлайн выглядел бы как
        // отобранные права.
        setVacancyAccessError(status === 403 ? 'forbidden' : status === 404 ? 'missing' : null);
      })
      .finally(() => {
        if (!cancelled) setVacancyProbing(false);
      });
    return () => { cancelled = true; };
  }, [selectedVacancyId, listedVacancy, probedVacancy?.id]);

  const selectedVacancy = listedVacancy ?? (probedVacancy?.id === selectedVacancyId ? probedVacancy : undefined);
  // Воронка запрошена в URL, но недоступна — рисуем экран отказа вместо обзора.
  const funnelBlocked = !!selectedVacancyId && !selectedVacancy && vacancyAccessError !== null;

  return { selectedVacancy, funnelBlocked, vacancyAccessError, vacancyProbing };
}
