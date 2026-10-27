import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { motion } from "framer-motion";
import toast from "react-hot-toast";
import { X } from "lucide-react";
import { sanitizeHtml } from "@/utils/sanitizeHtml";
import { formatSalary } from "@/utils/currency";
import { parseServerDate } from "@/utils/date";
import { hasPersonallyAccepted, isExplicitlyAssigned } from "@/utils/vacancy";
import { useAuthStore } from "@/stores/authStore";
import { useVacancyStore } from "@/stores/vacancyStore";
import { takeVacancy, declineVacancy } from "@/services/api/vacancies";
import type { Vacancy } from "@/types";
import { backdropClose } from '@/utils/backdropClose';

// Предпросмотр заявки из HR-сайдбара и раздела «Заявки» (вынесено из Layout,
// 20.10.2026).

function formatSidebarVacancyDate(date?: string | null) {
  if (!date) return "";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(parseServerDate(date));
}

function RequestPreviewBlock({
  title,
  children,
  html,
}: {
  title: string;
  children?: ReactNode;
  html?: string | null;
}) {
  // html — rich-text поле (обязанности/требования/условия) хранится как HTML.
  // Рендерим через санитайзер, иначе теги <ul>/<li>/<b> видны как текст.
  const hasHtml = typeof html === "string" && html.trim().length > 0;
  if (!children && !hasHtml) return null;
  return (
    <div className="hf-request-preview-block">
      <div className="hf-request-preview-label">{title}</div>
      {hasHtml ? (
        <div
          className="hf-request-preview-value prose prose-sm max-w-none"
          dangerouslySetInnerHTML={{ __html: sanitizeHtml(html) }}
        />
      ) : (
        <div className="hf-request-preview-value">{children}</div>
      )}
    </div>
  );
}

export function SidebarRequestPreviewModal({
  vacancy,
  onClose,
  onEdit,
  onTaken,
}: {
  vacancy: Vacancy;
  onClose: () => void;
  onEdit: () => void;
  onTaken: () => void;
}) {
  const { user } = useAuthStore();
  const { fetchVacancies } = useVacancyStore();
  const [taking, setTaking] = useState(false);
  const [declining, setDeclining] = useState(false);
  const isModalAdmin =
    user?.role === "superadmin" ||
    user?.org_role === "owner" ||
    user?.org_role === "admin";
  // «Отказаться» — рекрутёр снимает себя с заявки (backend /decline).
  const handleDecline = async () => {
    if (declining) return;
    setDeclining(true);
    try {
      await declineVacancy(vacancy.id);
      await fetchVacancies();
      toast.success("Вы отказались от заявки");
      onTaken();
    } catch {
      toast.error("Не удалось отказаться от заявки");
    } finally {
      setDeclining(false);
    }
  };
  // 2026-07-08: личное принятие (extra_data.accepted_by) — воронка общая, но
  // «Взять в работу» личное для каждого. Легаси-клоны (cloned_from_request_id)
  // больше не создаются, старая проверка всегда была бы false.
  const isTakenByMe = useMemo(() => {
    if (!user) return false;
    return hasPersonallyAccepted(vacancy, user.id);
  }, [user, vacancy]);
  const acceptedCount = useMemo(() => {
    const acceptedBy = (vacancy.extra_data as Record<string, unknown> | undefined)
      ?.accepted_by as number[] | undefined;
    return acceptedBy?.length || 0;
  }, [vacancy]);
  const requestDate = formatSidebarVacancyDate(
    vacancy.published_at || vacancy.created_at,
  );
  const customerName =
    vacancy.hiring_manager_name ||
    String((vacancy.extra_data as Record<string, unknown> | undefined)?.customer_name || "") ||
    "Не указан";
  const salaryText =
    vacancy.salary_min || vacancy.salary_max
      ? formatSalary(vacancy.salary_min, vacancy.salary_max, vacancy.salary_currency || "RUB")
      : null;
  const deadlineText = vacancy.closes_at
    ? formatSidebarVacancyDate(vacancy.closes_at)
    : null;
  const priorityLabel =
    vacancy.priority === 2 ? "Срочно" : vacancy.priority === 1 ? "Высокий" : "Обычный";
  const positionsCount =
    typeof vacancy.extra_data?.positions_count === "number"
      ? vacancy.extra_data.positions_count
      : 1;

  const handleTake = async () => {
    // Guard: повторный клик пока запрос ещё в полёте не должен
    // отправлять второй POST — иначе создавались дубли-клоны.
    if (taking) return;
    setTaking(true);

    try {
      await takeVacancy(vacancy.id);
      await fetchVacancies();
      toast.success('Заявка взята в работу — открыта в "Мои вакансии"');
      onTaken();
    } catch {
      // Раньше тут был вопрос «Создать дубликат?» на ответ duplicate_clone —
      // клонов вакансий больше нет, сервер такого ответа не даёт (20.10.2026).
      toast.error("Не удалось взять заявку");
    } finally {
      setTaking(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="hf-vacancy-modal-overlay hf-request-preview-overlay"
      // Не onClick={onClose}: выделение текста с отпусканием мыши за краем окна
      // закрывало его (жалоба 24.09.2026, см. backdropClose).
      {...backdropClose(onClose)}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        onClick={(event) => event.stopPropagation()}
        className="hf-vacancy-modal hf-request-preview-modal"
      >
        <div className="hf-vacancy-modal-header">
          <h2 className="hf-vacancy-modal-title">
            {vacancy.title?.trim() || "Заявка"}
          </h2>
          <div className="hf-vacancy-header-actions">
            <button
              type="button"
              onClick={onClose}
              className="hf-vacancy-close-btn"
              aria-label="Закрыть"
            >
              <X className="hf-request-preview-close-icon" />
            </button>
          </div>
        </div>

        <div className="hf-vacancy-form-scroll">
          <div className="hf-vacancy-modal-grid hf-request-preview-grid grid min-h-full">
            <div className="hf-vacancy-modal-main hf-request-preview-main">
              <RequestPreviewBlock
                title="Описание вакансии"
                html={vacancy.description}
              />
              <RequestPreviewBlock
                title="Обязанности кандидата"
                html={vacancy.responsibilities}
              />
              <RequestPreviewBlock
                title="Требования к кандидату"
                html={vacancy.requirements}
              />
            </div>

            <aside className="hf-vacancy-modal-aside hf-request-preview-aside">
              {salaryText && (
                <RequestPreviewBlock title="Зарплата">
                  {salaryText}
                </RequestPreviewBlock>
              )}
              <RequestPreviewBlock title="Приоритет">
                {priorityLabel}
              </RequestPreviewBlock>
              {deadlineText && (
                <RequestPreviewBlock title="Дедлайн">
                  {deadlineText}
                </RequestPreviewBlock>
              )}
              <RequestPreviewBlock title="Сколько человек нужно нанять">
                {positionsCount}
              </RequestPreviewBlock>
              <RequestPreviewBlock
                title={requestDate ? `Заказчик, ${requestDate}` : "Заказчик"}
              >
                {customerName}
              </RequestPreviewBlock>
              {requestDate && (
                <RequestPreviewBlock title="Заявка получена">
                  {requestDate}
                </RequestPreviewBlock>
              )}
              {acceptedCount > 0 && (
                <RequestPreviewBlock title="Заявка в работе">
                  {acceptedCount === 1
                    ? "Уже взята в работу 1 рекрутёром"
                    : `Уже взята в работу (${acceptedCount})`}
                </RequestPreviewBlock>
              )}
            </aside>
          </div>
        </div>

        <div className="hf-vacancy-footer hf-request-preview-footer">
          <button
            type="button"
            onClick={handleTake}
            disabled={taking || isTakenByMe}
            className="hf-vacancy-primary-btn"
          >
            {taking ? "Беру..." : isTakenByMe ? "Уже в работе" : "Взять в работу"}
          </button>
          <button type="button" onClick={onClose} className="hf-vacancy-secondary-btn">
            Закрыть
          </button>
          {/* Редактирование доступно и рекрутёрам (гейт снят 2026-07-02). */}
          <button type="button" onClick={onEdit} className="hf-vacancy-secondary-btn">
            Редактировать
          </button>
          {/* «Отказаться» — снимает себя с заявки: рекрутёр всегда, админ — если его
              ЯВНО назначили (раньше админ не мог отказаться вовсе, 2026-09-10). */}
          {(!isModalAdmin || isExplicitlyAssigned(vacancy, user?.id)) && (
            <button
              type="button"
              onClick={handleDecline}
              disabled={declining}
              className="hf-vacancy-secondary-btn"
              style={{ color: "var(--hf-status-red)", borderColor: "var(--hf-status-red)" }}
            >
              {declining ? "Отказ..." : "Отказаться"}
            </button>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
