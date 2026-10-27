import { pluralRu } from '@/utils/plural';
import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { X, Search, Briefcase, Plus, ChevronDown } from "lucide-react";
import toast from "react-hot-toast";
import { getErrorDetail } from "@/utils";
import clsx from "clsx";
import { getAllVacancies, createApplication, getEntityVacancies } from "@/services/api";
import type { Vacancy } from "@/types";
import { VACANCY_STATUS_LABELS, VACANCY_STATUS_COLORS } from "@/types";
import { formatSalary } from "@/utils";
import { isVacancyParticipant } from "@/utils/vacancy";
import { useAuthStore } from "@/stores/authStore";
import { backdropClose } from '@/utils/backdropClose';
import { usePriorRejectionGate } from '@/components/candidates/priorRejection';

interface AddToVacancyModalProps {
  entityId: number;
  entityName: string;
  onClose: () => void;
  onSuccess: () => void;
  bulkEntityIds?: number[];
  // Имена выбранных кандидатов (для именных тостов «уже в вакансии»).
  bulkEntities?: { id: number; name: string }[];
  // Воронки, которые НЕ показывать в списке назначений — обычно исходная воронка,
  // из которой перемещаем (перемещать в ту же воронку бессмысленно).
  excludeVacancyIds?: number[];
  anchorRect?: {
    left: number;
    bottom: number;
  } | null;
}

export default function AddToVacancyModal({
  entityId,
  entityName,
  onClose,
  onSuccess,
  bulkEntityIds,
  bulkEntities,
  excludeVacancyIds,
  anchorRect,
}: AddToVacancyModalProps) {
  const [loading, setLoading] = useState(false);
  const { user } = useAuthStore();
  const [searchQuery, setSearchQuery] = useState("");
  const [vacancies, setVacancies] = useState<Vacancy[]>([]);
  const [selectedVacancy, setSelectedVacancy] = useState<Vacancy | null>(null);
  const [loadingVacancies, setLoadingVacancies] = useState(false);
  // Воронки, в которых кандидат УЖЕ есть (для одиночного режима) — динамически
  // прячем их из списка, как при массовом перемещении.
  const [entityVacancyIds, setEntityVacancyIds] = useState<number[]>([]);
  const isBulk = !!bulkEntityIds?.length;
  const isHrAdmin =
    user?.role === "superadmin" ||
    user?.org_role === "owner" ||
    user?.org_role === "admin";
  const dropdownLeft = anchorRect
    ? Math.min(Math.max(anchorRect.left, 16), window.innerWidth - 616)
    : Math.max(16, window.innerWidth / 2 - 300);
  const dropdownTop = anchorRect
    ? Math.min(Math.max(anchorRect.bottom + 10, 16), window.innerHeight - 516)
    : 138;

  // Текущие воронки кандидата (одиночный режим) — чтобы исключить их из списка
  // (один кандидат = одна воронка; показывать ту, где он уже есть, бессмысленно).
  useEffect(() => {
    if (isBulk || !entityId) return;
    let cancelled = false;
    getEntityVacancies(entityId)
      .then((apps) => {
        if (!cancelled) setEntityVacancyIds(apps.map((a) => a.vacancy_id));
      })
      .catch(() => { /* не критично — просто не исключим */ });
    return () => { cancelled = true; };
  }, [entityId, isBulk]);

  // Load open vacancies
  useEffect(() => {
    const loadVacancies = async () => {
      setLoadingVacancies(true);
      try {
        const data = await getAllVacancies({
          status: "open",
        });
        // Заявка-оригинал после «Взять в работу» переходит в open и висит рядом
        // со своим клоном (рабочей вакансией) → дубль. Прячем оригиналы, у
        // которых уже есть клон — как это делает сайдбар в Layout.
        const clonedSourceIds = new Set<number>();
        data.forEach((v) => {
          const src = (v.extra_data as Record<string, unknown> | undefined)
            ?.cloned_from_request_id;
          if (typeof src === "number") clonedSourceIds.add(src);
        });
        const deduped = data.filter((v) => !clonedSourceIds.has(v.id));
        // Общая воронка без клонов: рекрутёру доступны воронки, где он УЧАСТНИК
        // (создатель ИЛИ назначенный, минус dismissed_by) — не только созданные им.
        const scoped =
          user && !isHrAdmin
            ? deduped.filter((v) => isVacancyParticipant(v, user.id))
            : deduped;
        // Динамика: прячем (а) исходную воронку, переданную родителем, и (б) те,
        // где кандидат уже есть — нельзя переместить в ту же воронку.
        const hideIds = new Set<number>([
          ...(excludeVacancyIds ?? []),
          ...entityVacancyIds,
        ]);
        const myVacancies = hideIds.size
          ? scoped.filter((v) => !hideIds.has(v.id))
          : scoped;
        const query = searchQuery.trim().toLowerCase();
        const filtered = query
          ? myVacancies.filter((v) =>
              [v.title, v.location, v.department_name]
                .filter(Boolean)
                .some((value) => value!.toLowerCase().includes(query)),
            )
          : myVacancies;
        setVacancies(filtered);
      } catch (error) {
        console.error("Failed to load vacancies:", error);
        toast.error("Не удалось загрузить вакансии");
      } finally {
        setLoadingVacancies(false);
      }
    };

    const debounce = setTimeout(loadVacancies, 300);
    return () => clearTimeout(debounce);
    // excludeKey (стабильная строка) вместо массива — иначе инлайн-массив от
    // родителя триггерил бы перезагрузку списка на каждый рендер.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isHrAdmin, searchQuery, user, (excludeVacancyIds ?? []).join(","), entityVacancyIds.join(",")]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !loading) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [loading, onClose]);

  const priorGate = usePriorRejectionGate();

  const handleSubmit = async () => {
    if (!selectedVacancy) {
      toast.error("Выберите вакансию");
      return;
    }
    // «Этот кандидат уже получал отказ» — спрашиваем по одному кандидату; при
    // массовом добавлении вопрос на каждого был бы пыткой, там метка видна в
    // строках списка (владелец, 22.10.2026: предупреждать, не запрещать).
    const isBulkAdd = (bulkEntities && bulkEntities.length > 0) || (bulkEntityIds && bulkEntityIds.length > 0);
    // Кнопка сразу в «Добавление…» — проверка на отказ идёт по сети.
    setLoading(true);
    if (!isBulkAdd && entityId && !(await priorGate.gate(entityId))) {
      setLoading(false);
      return;
    }

    // Кого добавляем (с именами для тостов): bulkEntities → bulkEntityIds →
    // одиночный entity.
    const entities =
      bulkEntities && bulkEntities.length > 0
        ? bulkEntities
        : bulkEntityIds && bulkEntityIds.length > 0
          ? bulkEntityIds.map((id) => ({ id, name: `#${id}` }))
          : [{ id: entityId, name: entityName }];

    // ADD-семантика (не MOVE): кандидат ДОБАВЛЯЕТСЯ в выбранную вакансию, НЕ
    // снимаясь с текущих — один кандидат может быть в нескольких воронках сразу
    // (по запросу HR). Это также убирает риск инцидента 2026-08-07 (массовый
    // перенос опустошал воронки): добавление неразрушительно и обратимо через
    // «Удалить с воронки», поэтому подтверждение больше не нужно.
    let okCount = 0;
    const alreadyIn: string[] = [];
    const failed: string[] = [];
    for (const ent of entities) {
      try {
        await createApplication(selectedVacancy.id, {
          vacancy_id: selectedVacancy.id,
          entity_id: ent.id,
          source: "manual_add",
        });
        okCount += 1;
      } catch (error) {
        const detail = getErrorDetail(error, "");
        if (/already applied|уже .*(добавлен|ваканс)/i.test(detail)) {
          alreadyIn.push(ent.name);
        } else {
          failed.push(ent.name);
        }
      }
    }
    setLoading(false);

    // Конфликты — отдельным красным тостом (с крестиком) на каждого по имени.
    alreadyIn.forEach((name) =>
      toast.error(`Кандидат ${name} уже есть в вакансии`),
    );
    failed.forEach((name) => toast.error(`Не удалось добавить: ${name}`));
    // Успех — один зелёный тост (с галочкой) с реальным числом добавленных.
    if (okCount > 0) {
      toast.success(
        okCount === 1
          ? "Кандидат добавлен в вакансию"
          : `Добавлено кандидатов: ${okCount}`,
      );
    }

    onSuccess();
  };

  // Format salary for display using utility function
  const getSalaryDisplay = (vacancy: Vacancy) => {
    if (!vacancy.salary_min && !vacancy.salary_max) return null;
    return formatSalary(
      vacancy.salary_min,
      vacancy.salary_max,
      vacancy.salary_currency,
    );
  };

  // Рендерим в портал на document.body: иначе position:fixed считается от
  // трансформированного предка (страница в framer-motion layout-анимациях) и
  // модалка съезжает по-разному у разных пользователей.
  // На фоне был ещё onMouseDown={onClose}: он закрывал окно по нажатию и
  // вдобавок перебивал спред backdropClose, стоя после него. Убран — закрытие
  // теперь по полноценному клику по фону, как во всех остальных модалках.
  return createPortal(
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className={clsx(
        "fixed inset-0 z-50",
        isBulk && "flex items-center justify-center p-4",
      )}
      style={isBulk ? { backgroundColor: 'rgba(0, 0, 0, 0.7)' } : undefined}
      {...backdropClose(onClose)}
    >
      <motion.div
        initial={
          isBulk
            ? { scale: 0.95, opacity: 0 }
            : { y: -6, scale: 0.98, opacity: 0 }
        }
        animate={{ y: 0, scale: 1, opacity: 1 }}
        exit={
          isBulk
            ? { scale: 0.95, opacity: 0 }
            : { y: -6, scale: 0.98, opacity: 0 }
        }
        transition={{ duration: 0.14, ease: [0.22, 1, 0.36, 1] }}
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
        className={clsx(
          "flex flex-col overflow-hidden rounded-[8px] bg-[var(--hf-white)] text-[var(--hf-main-900)] leading-[22px] shadow-[0_0_40px_var(--hf-alpha-300)] dark:bg-[var(--hf-bg-dark)] dark:text-[var(--hf-white)]",
          isBulk
            ? "relative max-h-[80vh] w-full max-w-[620px] border border-[var(--hf-ui-border)] dark:border-[color:var(--hf-white-alpha-10)]"
            : "fixed h-[500px] w-[600px]",
        )}
        style={
          isBulk
            ? undefined
            : {
                left: dropdownLeft,
                top: dropdownTop,
              }
        }
      >
        {isBulk ? (
          <div className="flex h-[64px] flex-shrink-0 items-center justify-between border-b border-[var(--hf-ui-divider)] px-[16px] dark:border-[color:var(--hf-white-alpha-10)]">
            <div className="flex items-center gap-3">
              <div className="flex h-[36px] w-[36px] items-center justify-center rounded-[8px] bg-[var(--hf-bg-muted)] text-[var(--hf-cyan-500)] dark:bg-[var(--hf-white-alpha-10)]">
                <Briefcase className="h-[20px] w-[20px]" />
              </div>
              <div>
                <h2 className="text-[20px] font-semibold leading-[26px]">
                  Добавить на вакансию
                </h2>
                <p className="text-[14px] leading-[20px] text-[var(--hf-main-600)] dark:text-[color:var(--hf-white-alpha-45)]">
                  {entityName}
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="inline-flex h-[36px] w-[36px] items-center justify-center rounded-[8px] text-[var(--hf-ui-text-strong)] transition-colors hover:bg-[var(--hf-black-alpha-04)] dark:text-[color:var(--hf-white-alpha-70)] dark:hover:bg-[var(--hf-white-alpha-06)]"
              aria-label="Закрыть"
            >
              <X className="h-[22px] w-[22px]" />
            </button>
          </div>
        ) : (
          <div className="flex h-[121px] flex-shrink-0 flex-col border-b border-[var(--hf-ui-divider-soft)] px-[16px] pt-[16px] dark:border-[color:var(--hf-white-alpha-10)]">
            <button
              type="button"
              className="inline-flex h-[40px] w-full items-center justify-between rounded-[8px] border border-[var(--hf-alpha-300)] bg-[var(--hf-white)] px-[16px] pr-[8px] text-[15px] font-normal leading-[24px] text-[var(--hf-main-900)] transition-colors hover:border-[var(--hf-input-border-strong-hover)] dark:border-[color:var(--hf-white-alpha-10)] dark:bg-transparent dark:text-[var(--hf-white)]"
            >
              Подразделение: Все
              <ChevronDown className="h-[16px] w-[16px] text-[var(--hf-main-600)]" />
            </button>
            <div className="relative mt-[8px]">
              <Search className="absolute left-[12px] top-1/2 h-[16px] w-[16px] -translate-y-1/2 text-[var(--hf-main-600)]" />
              <input
                type="text"
                placeholder="Поиск..."
                autoFocus
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-[40px] w-full rounded-[8px] border border-[var(--hf-ui-border)] bg-[var(--hf-white)] pl-[32px] pr-[16px] text-[15px] leading-[24px] text-[var(--hf-main-900)] outline-none placeholder:text-[var(--hf-main-600)] focus:border-[var(--hf-cyan-500)] dark:border-[color:var(--hf-white-alpha-10)] dark:bg-transparent dark:text-[var(--hf-white)]"
              />
            </div>
          </div>
        )}

        <div
          className={clsx(
            "flex flex-1 flex-col overflow-hidden",
            isBulk ? "p-[16px]" : "p-0",
          )}
        >
          {/* Search */}
          {isBulk && (
            <div className="relative mb-[12px]">
              <Search className="absolute left-[12px] top-1/2 h-[16px] w-[16px] -translate-y-1/2 text-[var(--hf-main-600)]" />
              <input
                type="text"
                placeholder="Поиск..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-[40px] w-full rounded-[8px] border border-[var(--hf-ui-border)] bg-[var(--hf-white)] pl-[32px] pr-[16px] text-[15px] leading-[24px] text-[var(--hf-main-900)] outline-none placeholder:text-[var(--hf-main-600)] focus:border-[var(--hf-cyan-500)] dark:border-[color:var(--hf-white-alpha-10)] dark:bg-transparent dark:text-[var(--hf-white)]"
              />
            </div>
          )}

          {/* Vacancies List */}
          <div
            className={clsx(
              "min-h-0 flex-1 overflow-y-auto",
              isBulk ? "space-y-[8px]" : "py-[8px]",
            )}
          >
            {loadingVacancies ? (
              <div className="flex items-center justify-center py-8">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--hf-cyan-500)] border-t-transparent" />
              </div>
            ) : vacancies.length === 0 ? (
              <div className="py-[20px] text-center text-[14px] leading-[20px] text-[var(--hf-main-600)] dark:text-[color:var(--hf-white-alpha-40)]">
                <Briefcase className="mx-auto mb-[8px] h-[34px] w-[34px]" />
                <p>Вакансии не найдены</p>
                <p className="mt-[4px] text-[13px]">Нет открытых вакансий</p>
              </div>
            ) : isBulk ? (
              vacancies.map((vacancy) => {
                const salary = getSalaryDisplay(vacancy);
                return (
                  <button
                    key={vacancy.id}
                    onClick={() => setSelectedVacancy(vacancy)}
                    className={clsx(
                      "w-full rounded-[8px] border p-[12px] text-left transition-colors",
                      selectedVacancy?.id === vacancy.id
                        ? "border-[var(--hf-cyan-500)] bg-[var(--hf-status-cyan-bg)]"
                        : "border-[var(--hf-ui-divider)] bg-[var(--hf-white)] hover:bg-[var(--hf-ui-hover)] dark:border-[color:var(--hf-white-alpha-10)] dark:bg-[var(--hf-white-alpha-03)] dark:hover:bg-[var(--hf-white-alpha-06)]",
                    )}
                  >
                    <div className="mb-1 flex items-center justify-between">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[15px] font-medium leading-[22px]">
                          {vacancy.title}
                        </p>
                      </div>
                      <span
                        className={clsx(
                          "ml-2 rounded-full px-2 py-0.5 text-xs",
                          VACANCY_STATUS_COLORS[vacancy.status],
                        )}
                      >
                        {VACANCY_STATUS_LABELS[vacancy.status]}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-[14px] leading-[20px] text-[var(--hf-ui-text-muted)] dark:text-[color:var(--hf-white-alpha-55)]">
                      {vacancy.location && <span>{vacancy.location}</span>}
                      {vacancy.location && salary && <span>•</span>}
                      {salary && <span>{salary}</span>}
                    </div>
                    {vacancy.department_name && (
                      <p className="mt-1 text-[13px] leading-[18px] text-[var(--hf-main-600)] dark:text-[color:var(--hf-white-alpha-40)]">
                        {vacancy.department_name}
                      </p>
                    )}
                    <div className="mt-2 flex items-center gap-2 text-[13px] leading-[18px] text-[var(--hf-main-600)] dark:text-[color:var(--hf-white-alpha-40)]">
                      <span>{vacancy.applications_count} {pluralRu(vacancy.applications_count, 'кандидат', 'кандидата', 'кандидатов')}</span>
                    </div>
                  </button>
                );
              })
            ) : (
              <>
                <div className="flex h-[49px] items-start px-[16px] pt-[8px] text-[15px] font-normal leading-[24px] text-[var(--hf-main-900)] dark:text-[var(--hf-white)]">
                  <span className="pt-[8px]">Мои вакансии</span>
                </div>
                {vacancies.map((vacancy) => (
                  <button
                    key={vacancy.id}
                    onClick={() => setSelectedVacancy(vacancy)}
                    className={clsx(
                      "group flex h-[65px] w-full items-center px-[8px] text-left transition-colors duration-[100ms]",
                      selectedVacancy?.id === vacancy.id
                        ? "bg-[var(--hf-ui-selected)] dark:bg-[var(--hf-white-alpha-10)]"
                        : "hover:bg-[var(--hf-bg-body)] dark:hover:bg-[var(--hf-white-alpha-06)]",
                    )}
                  >
                    <span className="flex min-w-0 flex-col pl-[32px] pr-[16px]">
                      <span className="truncate text-[15px] font-normal leading-[24px] text-[var(--hf-main-900)] dark:text-[var(--hf-white)]">
                        {vacancy.title}
                      </span>
                      <span className="truncate text-[15px] font-normal leading-[24px] text-[var(--hf-main-900)] dark:text-[var(--hf-white)]">
                        {vacancy.department_name ||
                          vacancy.location ||
                          VACANCY_STATUS_LABELS[vacancy.status]}
                      </span>
                    </span>
                  </button>
                ))}
              </>
            )}
          </div>
        </div>

        {/* Footer */}
        <div
          className={clsx(
            "flex flex-shrink-0 items-center border-t border-[var(--hf-ui-divider)] dark:border-[color:var(--hf-white-alpha-10)] dark:bg-[var(--hf-bg-dark)]",
            isBulk
              ? "h-[72px] justify-end gap-[12px] bg-[var(--hf-bg-muted)] px-[16px]"
              : "h-[53px] justify-between gap-[8px] bg-[var(--hf-white)] px-0",
          )}
        >
          {!isBulk && (
            <button
              type="button"
              onClick={() =>
                toast("Создание вакансии доступно в разделе “Мои вакансии”")
              }
              className="flex h-[53px] w-full items-center gap-[8px] px-[16px] py-[16px] text-[15px] font-normal leading-[19px] text-[var(--hf-cyan-700)] hover:bg-[var(--hf-bg-muted)] dark:text-[var(--hf-white)] dark:hover:bg-[var(--hf-white-alpha-06)]"
            >
              <Plus className="h-[16px] w-[16px]" />
              Новая вакансия
            </button>
          )}
          {(isBulk || selectedVacancy) && (
            <div className="ml-auto flex items-center gap-[8px]">
              <button
                onClick={onClose}
                className="inline-flex h-[36px] items-center rounded-[6px] px-[12px] text-[14px] font-medium text-[var(--hf-ui-text-soft)] transition-colors hover:bg-[var(--hf-black-alpha-04)] hover:text-[var(--hf-main-900)] dark:text-[color:var(--hf-white-alpha-55)] dark:hover:bg-[var(--hf-white-alpha-06)] dark:hover:text-[var(--hf-white)]"
              >
                Отмена
              </button>
              <button
                onClick={handleSubmit}
                disabled={loading || !selectedVacancy}
                className="inline-flex h-[36px] items-center gap-[8px] rounded-[6px] bg-[var(--hf-main-900)] px-[14px] text-[14px] font-semibold text-[var(--hf-white)] transition-colors duration-[100ms] hover:bg-[var(--hf-main-800)] disabled:cursor-not-allowed disabled:bg-[var(--hf-btn-disabled-bg)] disabled:text-[var(--hf-main-600)] disabled:opacity-100 disabled:hover:bg-[var(--hf-btn-disabled-bg)] dark:bg-[var(--hf-white)] dark:text-[var(--hf-main-900)] dark:hover:bg-[var(--hf-white-alpha-90)] dark:disabled:bg-[var(--hf-white-alpha-08)] dark:disabled:text-[color:var(--hf-white-alpha-35)]"
              >
                <Plus className="h-4 w-4" />
                {loading ? "Добавление..." : "Добавить"}
              </button>
            </div>
          )}
        </div>
      </motion.div>
      {priorGate.element}
    </motion.div>,
    document.body,
  );
}
