import { copyOrShowLink } from '@/utils/copyOrShowLink';
import { useState, useEffect, useCallback, useMemo, memo, lazy, Suspense } from "react";
import { useNavigate } from "react-router-dom";

import { AnimatePresence } from "framer-motion";
import {
  X,
  PlusCircle,
  PenSquare,
  Phone,
  Send,
  ExternalLink,
  MapPin,
  ChevronRight,
  Lock,
  Archive,
} from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";

import { buildStageContainers, buildStagePickerOptions, readSystemHrTags } from "@/components/entities/candidateDetail/model";

import type { KanbanCard, KanbanColumn } from "@/services/api/candidates";
import { updateEntity, createCandidateShareLink, archiveEntity } from "@/services/api/entities";

import type { ApplicationStage } from "@/types";
import { APPLICATION_STAGE_LABELS, STATUS_TO_STAGE_MAP, type EntityStatus } from "@/types";
import { deleteApplication } from "@/services/api/vacancies";
import SendEmailModal from "@/components/entities/SendEmailModal";
import TakeCandidateButton from "@/components/entities/TakeCandidateButton";
import TagPicker from "@/components/entities/TagPicker";
import ShadowDuplicateBanner from "@/components/entities/ShadowDuplicateBanner";
import { useVisiblePriorRejections } from "@/components/candidates/priorRejection";
import { useAuthStore } from "@/stores/authStore";

import { HuntflowInfoRow as InfoRow } from "@/components/hr/HuntflowControls";
import { useFormBadgeStore } from "@/stores/formBadgeStore";
import {
  getEntityFormsUnreadCount,
  getEntityAllDispatches,
  markEntityDispatchesSeen,
  type FormDispatchInfo,
} from "@/services/api/forms";

import CandidateVacancyCard from "@/components/entities/CandidateVacancyCard";

import ResumeTab, { useResumeSources } from "@/components/entities/candidateDetail/ResumeTab";
import { readParticipations } from "@/components/entities/candidateDetail/ImportedParticipations";

import { useCardActions } from "@/components/entities/candidateDetail/useCardActions";
import { STAGE_CHIP_BRIGHT_BY_STAGE } from "@/constants/hrStages";
import { getInitials, formatPhoneDisplay, getVacancyStageLabel } from "@/components/candidates/candidateFormat";

import { AnketaTab } from "@/components/entities/candidateDetail/AnketaTab";
import { useCandidateActivity } from "@/components/entities/candidateDetail/useCandidateActivity";
import { type DetailSection, type StageContainer, resolveContainerStatusLabel } from "@/components/entities/candidateDetail/model";
const AnketaDrawer = lazy(() =>
  import("@/features/forms/AnketaDrawer").then((m) => ({ default: m.AnketaDrawer })),
);

// Панель кандидата справа на «Все кандидаты»: шапка, поля, стек воронок,
// резюме и анкеты (вынесена из AllCandidatesPage, 20.10.2026).

export const InfoTab = memo(function InfoTab({
  card,
  status,
  columns,
  detailSection,
  onDetailSectionChange,
  onStatusChange,
  onAddToVacancy,
  onEdit,
  onMerged,
  onRemovedFromVacancy,
}: {
  card: KanbanCard;
  status: string;
  columns: KanbanColumn[];
  detailSection: DetailSection;
  onDetailSectionChange: (section: DetailSection) => void;
  onStatusChange: (s: string) => void;
  onAddToVacancy: (rect?: { left: number; bottom: number }) => void;
  onEdit: () => void;
  // Слияние дубля разрешено в баннере → родитель перечитывает выжившего и доску
  // (иначе объединённый профиль виден только после ручного обновления).
  onMerged?: () => void;
  // Снятие кандидата с воронки → родитель обновляет доску и сбрасывает выбор.
  onRemovedFromVacancy?: () => void;
}) {
  const { user: currentUser } = useAuthStore();
  const navigate = useNavigate();
  // «Наблюдатель» (read-only): все изменяющие действия карточки заблокированы.
  // Просмотр (анкета/резюме, клики по тг/почте/ссылкам) и «Поделиться» — доступны.
  const readonly = !!currentUser?.is_readonly;
  const roStyle = readonly ? { opacity: 0.45, cursor: "not-allowed" as const } : undefined;
  // Сохранён только сеттер: action-бар сбрасывает (закрывает) меню действий.
  const [, setShowActionMenu] = useState(false);
  const [anketaOpen, setAnketaOpen] = useState(false);
  const anketaCount = useFormBadgeStore((s) => s.counts[card.id] ?? 0);
  const priorRejections = useVisiblePriorRejections(card.id);
  const setAnketaCount = useFormBadgeStore((s) => s.setCount);
  const clearAnketaBadge = useFormBadgeStore((s) => s.clear);
  // Источники резюме: каждое резюме — отдельная вкладка верхнего уровня рядом
  // с «Личные заметки». resumeIndex — какая из них активна.
  // Бамп после загрузки файла → useResumeSources перечитывает файлы (вкладка
  // «Резюме» кэширует по card.id, который не меняется → иначе файл не виден).
  const [filesNonce, setFilesNonce] = useState(0);
  const { sources: resumeSources, files: allEntityFiles } = useResumeSources(
    card,
    filesNonce,
  );
  const [resumeIndex, setResumeIndex] = useState(0);
  useEffect(() => {
    setResumeIndex(0);
  }, [card.id]);
  // Импортированные прохождения (ClickUp-архив) — каждое СВОЯ вкладка «Анкета»
  // в том же ряду, что и «Резюме». Анкеты бывают длинными, поэтому не
  // складываем их простынёй, а переключаем чипами. anketaIndex — активное.
  const participations = readParticipations(card);
  const [anketaIndex, setAnketaIndex] = useState(0);
  useEffect(() => {
    setAnketaIndex(0);
  }, [card.id]);
  // Нативные заполненные форм-анкеты (FormDispatch) — отдельная вкладка «Анкета»
  // ПОСЛЕ вкладок импортных прохождений (индекс = participations.length), а не
  // дублируются под каждым прохождением. Фетчим здесь (в родителе), т.к. вкладке
  // нужно знать заранее, есть ли нативные анкеты, чтобы отрисовать саму вкладку.
  const [nativeDispatches, setNativeDispatches] = useState<
    (FormDispatchInfo & { source_entity_id?: number; source_name?: string | null })[]
  >([]);
  useEffect(() => {
    let alive = true;
    const fetchRows = async () => {
      try {
        const rows = await getEntityAllDispatches(card.id);
        if (alive) setNativeDispatches(rows);
      } catch {
        /* пустой/ошибка — покажем пустое состояние */
      }
    };
    fetchRows();
    // Поллинг: realtime по WebSocket на проде может не доходить (прокси/доставка),
    // поэтому раз в 15с подтягиваем ответы — заполненная анкета появляется без
    // перезагрузки страницы.
    const t = setInterval(fetchRows, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [card.id]);
  const hasNativeAnketa = nativeDispatches.length > 0;
  const nativeTabIndex = participations.length;
  // Открытие вкладки нативной анкеты — отмечаем прочитанной + сбрасываем бейдж
  // (раньше это делалось при любом открытии «Анкеты», теперь — только когда
  // видна именно нативная вкладка).
  useEffect(() => {
    if (detailSection === "anketa" && hasNativeAnketa && anketaIndex === nativeTabIndex) {
      markEntityDispatchesSeen(card.id).catch(() => {});
      clearAnketaBadge(card.id);
    }
  }, [detailSection, hasNativeAnketa, anketaIndex, nativeTabIndex, card.id, clearAnketaBadge]);
  // Доп. контакты после склейки: у человека из импорта могут быть РАЗНЫЕ
  // телефоны/телеграмы/почты из разных записей — показываем все, кроме уже
  // выведенного «основного» (дедуп по цифрам телефона / нижнему регистру).
  const _digits = (s: string) => (s || "").replace(/\D/g, "");
  const _tgKey = (s: string) => (s || "").replace(/^@/, "").toLowerCase();
  const extraPhones = Array.from(
    new Set((card.phones || []).map((p) => (p || "").trim()).filter(Boolean)),
  ).filter((p) => _digits(p) && _digits(p) !== _digits(card.phone || ""));
  const extraEmails = Array.from(
    new Set((card.emails || []).map((e) => (e || "").trim()).filter(Boolean)),
  ).filter((e) => e.toLowerCase() !== (card.email || "").trim().toLowerCase());
  const extraTelegrams = Array.from(
    new Set((card.telegram_usernames || []).map((t) => (t || "").trim()).filter(Boolean)),
  ).filter((t) => _tgKey(t) !== _tgKey(card.telegram_username || ""));
  // Ручное проставление меток убрано (метки «HR: … · воронка» ставит бэкенд
  // автоматически по воронке). localTags остаётся только для показа/удаления
  // уже существующих ручных меток — новые здесь не добавляются.
  const [localTags, setLocalTags] = useState<string[]>(card.tags || []);
  // Бейдж непрочитанных анкет (entity-уровень).
  useEffect(() => {
    if (!card.id) return;
    getEntityFormsUnreadCount(card.id)
      .then((r) => setAnketaCount(card.id, r.count))
      .catch(() => {});
  }, [card.id, setAnketaCount]);
  // Пикер собран из колонок доски, но «Вне воронки» (BOARD_OTHER_STATUS) —
  // НЕ этап: это служебная колонка «кандидат не в воронке». У заявки такого
  // этапа нет, поэтому её выбор ничего не сохранял, а карточка на экране всё
  // равно переезжала — «перевёл, а он остался на месте» (жалоба Марии,
  // Гром Виктор, 24.09.2026). Пикер её вообще не предлагает: после «Перешёл в
  // отдел» следующего этапа больше нет, и окно помечает текущий с плашкой
  // «Кандидат сейчас находится на этом этапе подбора».
  const stagePickerOptions = useMemo(() => buildStagePickerOptions(columns), [columns]);

  // ── Стек карточек по вакансиям: после слияния дубля у выжившего несколько
  // заявок. Тянем сквозную ленту активности (по заявке) и рендерим ОТДЕЛЬНУЮ
  // интерактивную карточку на каждую вакансию. Если заявок нет —
  // activityBlocks пуст и ниже рендерится одиночная карточка как раньше.
  const { activityBlocks, loadActivity, notesVersion, bumpNotes } = useCandidateActivity(card);

  // Лейбл статуса контейнера: сперва колонки доски (org-override), затем канон
  // STATUS_LABELS (EntityStatus), затем локальный CANDIDATE_VACANCY_STAGE_LABELS,
  // затем сам ключ. Resolve'ит и column-override'ы, и сырые EntityStatus.
  const getStackStageLabel = useCallback(
    (stage: string) => resolveContainerStatusLabel(stage, columns),
    [columns],
  );

  // Первичная заявка (та, что соответствует текущей вакансии кандидата) —
  // источник events (история переходов) и applicationId для ЖИВОГО контейнера.
  const primaryBlock = useMemo(() => {
    const primaryTitle = (card.vacancy_name || "").trim().toLowerCase();
    if (primaryTitle) {
      const match = activityBlocks.find(
        (b) => (b.vacancy_title || "").trim().toLowerCase() === primaryTitle,
      );
      if (match) return match;
    }
    return activityBlocks[0];
  }, [activityBlocks, card.vacancy_name]);

  // ── НОВАЯ МОДЕЛЬ СТЕКА: контейнеры = [ собственный живой ] + merged_from[].
  // Это НЕ вакансии. Живой контейнер — из самого кандидата (card); merged —
  // плоский массив смёрдженных дублей (транзитивные слияния уже подняты в корень
  // бэкендом, поэтому просто .map()). Порядок: живой первым, затем merged.
  // Стек контейнеров (живой + merged_from) — чистая логика вынесена в
  // candidateDetail/model.buildStageContainers (21 unit-тест). Здесь только
  // прокидываем вычисляемые поля живого контейнера (primaryBlock, лейбл вакансии).
  const containers = useMemo<StageContainer[]>(
    () =>
      buildStageContainers({
        card,
        status,
        liveApplicationId: primaryBlock?.application_id ?? 0,
        liveEvents: primaryBlock?.events,
        liveVacancyTitle: getVacancyStageLabel(card) ?? null,
        // Карточка на КАЖДУЮ воронку кандидата: свой этап, своя история, свои
        // комментарии. Иначе комментарии второй воронки тут не появлялись, а
        // смена этапа меняла только одну заявку (2026-09-17, Мария).
        liveBlocks: activityBlocks,
        allEntityFiles: allEntityFiles || [],
        // Кандидат вне воронок: закреп лежит на самой карточке.
        livePinnedEntryKey:
          (card.extra_data?.pinned_entry_key as string | undefined) ?? null,
      }),
    // notesVersion — форс-пересчёт после мутаций card.extra_data.notes (add/edit/delete),
    // которые меняют данные in-place без смены ссылки card.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [primaryBlock, status, card, allEntityFiles, notesVersion, activityBlocks]
  );

  // Карта vacancy_id → название воронки (все прохождения кандидата). Нужна, чтобы
  // в объединённом логе «Все кандидаты» пометить каждый коммент своей воронкой
  // (note.vacancy_id → бейдж «воронка «X»»). В самой воронке лог уже свой — там
  // резолвер НЕ передаётся, бейджа нет.
  const vacancyTitleById = useMemo(() => {
    const m = new Map<number, string>();
    for (const b of activityBlocks) {
      if (b.vacancy_id && b.vacancy_title) m.set(b.vacancy_id, b.vacancy_title);
    }
    return m;
  }, [activityBlocks]);
  const resolveNoteVacancyLabel = useCallback(
    (vacancyId?: number | null): string | null =>
      vacancyId != null ? vacancyTitleById.get(vacancyId) ?? null : null,
    [vacancyTitleById],
  );

  // Этапы по каждой воронке кандидата (для шапки живого контейнера, если он в
  // ≥2 воронках): вместо одного «общего» этапа — список «этап → воронка» цветными
  // чипами (цвет = как колонки воронки, APPLICATION_STAGE_COLORS).
  const funnelStages = useMemo(
    () =>
      activityBlocks
        .filter((b) => b.vacancy_id && b.vacancy_title)
        .map((b) => {
          const st = b.current_stage as ApplicationStage;
          return {
            vacancyId: b.vacancy_id,
            title: b.vacancy_title,
            stageLabel: APPLICATION_STAGE_LABELS[st] || b.current_stage,
            // Яркие чипы: СПЛОШНОЙ статус-цвет + тёмный текст той же гаммы (не
            // бледный badge-вариант APPLICATION_STAGE_COLORS).
            colorClass:
              STAGE_CHIP_BRIGHT_BY_STAGE[st] ||
              "bg-[var(--hf-status-gray)] text-[#111827]",
          };
        }),
    [activityBlocks],
  );

  // ── Тонкие обёртки для CandidateVacancyCard. Смену этапа делает ТОЛЬКО живой
  // (интерактивный) контейнер — его status это статус самого кандидата (entity),
  // поэтому меняем entity-статус через onStatusChange. Если у кандидата есть
  // реальная первичная заявка (appId>0) — синхронизируем и её стадию (воронка).
  // Чип этапа в СТРОКЕ списка рисуется из card.funnels (данные с сервера).
  // Без локальной правки строка ещё показывала старый этап, пока не
  // перезагрузишь доску — карточка справа уже «Перешёл в отдел», а в списке
  // «Практика» (ровно то расхождение, про которое правило в CLAUDE.md).
  const patchFunnelStage = useCallback(
    (appId: number, appStage: string) => {
      const title = activityBlocks.find(
        (b) => b.application_id === appId,
      )?.vacancy_title;
      if (!title || !Array.isArray(card.funnels)) return;
      card.funnels = card.funnels.map((f) =>
        f.vacancy_title === title ? { ...f, stage: appStage } : f,
      );
    },
    [activityBlocks, card],
  );

  // Действия карточки — общие с воронкой (useCardActions). Здесь только то,
  // чем «Все кандидаты» отличаются: extra_data живёт прямо в card (снимок
  // доски), а откат перевода переставляет карточку в колонках доски.
  const cardActions = useCardActions({
    entityId: card.id,
    patchExtra: (update) => {
      card.extra_data = update(card.extra_data || {});
      bumpNotes(); // мутация card не триггерит ре-рендер
    },
    replaceExtra: (fresh) => {
      card.extra_data = fresh;
      bumpNotes();
    },
    refreshActivity: loadActivity,
    // Перечитать файлы → обновится блок «Файлы» в плашке и вкладка «Резюме».
    reloadFiles: () => setFilesNonce((n) => n + 1),
    // Воронка, в которой написан коммент: без vacancy_id он становился
    // «Общим» и всплывал во ВСЕХ воронках кандидата. Без заявок — «Общий».
    noteVacancyId: (appId) =>
      activityBlocks.find((b) => b.application_id === appId)?.vacancy_id ??
      primaryBlock?.vacancy_id,
    // На сервере всё уже сделано — переставляем карточку на месте.
    onRolledBack: ({ appId, stage, entityStatus }) => {
      if (!entityStatus) return;
      if (appId != null && stage) patchFunnelStage(appId, stage);
      onStatusChange(entityStatus);
    },
  });

  const cardChangeStage = useCallback(
    async (appId: number, stage: string, comment?: string) => {
      // Пикер собран из КОЛОНОК доски, а там статусы кандидата (EntityStatus:
      // new / practice / tech_practice / is_interview…). У заявки свой набор
      // (ApplicationStage: applied / phone_screen / interview / assessment…), и
      // четыре значения в них называются по-разному — переводим по карте, а не
      // приведением типа (раньше «Новый», «Интервью с HR» и др. давали 422).
      const appStage = STATUS_TO_STAGE_MAP[stage as EntityStatus];
      if (appId > 0 && !appStage) {
        // Кандидат В ВОРОНКЕ, а у статуса нет пары среди этапов заявки
        // («Вне воронки»): применить некуда — честная ошибка и НИКАКОГО
        // движения карточки (Гром Виктор, 24.09.2026).
        console.warn('[stage] у статуса нет этапа заявки, перевод не применён:', stage);
        toast.error(
          `«${getStackStageLabel(stage)}» нельзя поставить заявке — кандидат остался на прежнем этапе`,
        );
        return false;
      }
      // Общий статус ПОСЛЕ перевода считает сервер, и он не всегда равен
      // выбранному: у кандидата в двух воронках отказ в одной оставляет статус
      // по живой второй. Карточку ставим в колонку по ответу сервера.
      const res =
        appId > 0 && appStage
          ? await cardActions.changeApplicationStage(appId, appStage, comment)
          : await cardActions.changeStatusOutOfFunnel(stage, getStackStageLabel(stage), comment);
      if (res.ok) {
        // Чип этапа в строке списка рисуется из card.funnels — правим и его,
        // иначе справа «Перешёл в отдел», а в списке ещё «Практика».
        if (appId > 0 && appStage) patchFunnelStage(appId, appStage);
        onStatusChange(res.entityStatus ?? stage);
      }
      await loadActivity();
      return res.ok;
    },
    [onStatusChange, loadActivity, patchFunnelStage, getStackStageLabel, cardActions],
  );

  const cardRemoveFromVacancy = useCallback(
    async (appId: number) => {
      // Нет активной заявки (appId 0) → кандидат не в воронке: дружелюбная
      // подсказка вместо ошибки «не удалось снять».
      if (!appId || appId <= 0) {
        toast("Кандидат не в активных воронках");
        return;
      }
      try {
        await deleteApplication(appId);
        toast.success("Кандидат снят с воронки");
        // Перечитываем историю + уведомляем родителя обновить доску.
        await loadActivity();
        onRemovedFromVacancy?.();
      } catch {
        toast.error("Не удалось снять кандидата с воронки");
      }
    },
    [loadActivity, onRemovedFromVacancy],
  );

  useEffect(() => {
    setLocalTags(card.tags || []);
  }, [card.id, card.tags]);

  // --- Action handlers ---

  const [showEmailModal, setShowEmailModal] = useState(false);
  const [emailAnchorRect, setEmailAnchorRect] = useState<DOMRect | null>(null);

  const handleEmail: React.MouseEventHandler<HTMLButtonElement> = (event) => {
    setEmailAnchorRect(event.currentTarget.getBoundingClientRect());
    setShowActionMenu(false);
    setShowEmailModal(true);
  };

  // Модуль 4: «Поделиться» — публичная ссылка предпросмотра кандидата для
  // заказчика (без авторизации, 30 дней), сразу в буфер — удобно кинуть в ТГ.
  const handleShareCandidate = async () => {
    try {
      const link = await createCandidateShareLink(card.id);
      await copyOrShowLink(`${window.location.origin}${link.url_path}`, 'Ссылка на предпросмотр скопирована — действует 30 дней');
    } catch {
      toast.error('Не удалось создать ссылку');
    }
  };

  // «В архив» (superadmin): кандидат уходит в теневую базу — исчезает из активных
  // списков/канбана/поиска, но остаётся для сверки дублей. Обратно — только с
  // superadmin-страницы «Архив кандидатов».
  const handleArchive = async () => {
    if (!window.confirm(`Отправить «${card.name || 'кандидата'}» в архив? Он исчезнет из активных списков, но будет участвовать в проверке дублей.`)) return;
    try {
      await archiveEntity(card.id);
      toast.success('Кандидат отправлен в архив');
      onRemovedFromVacancy?.();
    } catch {
      toast.error('Не удалось отправить в архив');
    }
  };

  const handleRemoveTag = async (tag: string) => {
    const newTags = localTags.filter((t) => t !== tag);
    try {
      await updateEntity(card.id, { tags: newTags });
      setLocalTags(newTags);
      toast.success(`Метка "${tag}" удалена`);
    } catch {
      toast.error("Ошибка удаления метки");
    }
  };

  return (
    <div className="p-[24px] max-w-[1200px]">
      {/* Send Email Modal */}
      <AnimatePresence>
        {showEmailModal && (
          <SendEmailModal
            entityId={card.id}
            entityName={card.name}
            entityEmail={card.email}
            anchorRect={emailAnchorRect}
            onClose={() => setShowEmailModal(false)}
          />
        )}
      </AnimatePresence>

      {/* Теневой дубль: баннер «Похожий кандидат есть в базе» над action-баром.
          Копипаст резюме (Feature B) теперь тоже идёт через этот же баннер
          (strength === "text") — отдельного серого бейджа больше нет. */}
      {/* Одна плашка: «Уже был у нас — отказ …» + дубль + «Сравнить»
          (владелец, 22.10.2026 — две плашки занимали полэкрана). */}
      <ShadowDuplicateBanner card={card} status={status} onResolved={onMerged} rejections={priorRejections} />

      {/* ---- Top action buttons (Huntflow: Взять на вакансию | Редактировать) ---- */}
      <div className="hf-profile-action-bar">
        <button
          onClick={(event) => {
            const rect = event.currentTarget.getBoundingClientRect();
            setShowEmailModal(false);
                    setShowActionMenu(false);
            onAddToVacancy({ left: rect.left, bottom: rect.bottom });
          }}
          className="hf-profile-action-btn"
          disabled={readonly}
          style={roStyle}
        >
          <PlusCircle className="hf-profile-action-icon" /> Взять на вакансию
        </button>
        {/* «Забрать» — выбрать воронку + рекрутёра, кому отдать кандидата.
            Показываем ТОЛЬКО если кандидат уже есть хотя бы в одной воронке
            (иначе забирать неоткуда — используют «Взять на вакансию»). */}
        {!readonly && activityBlocks.length > 0 && (
          <TakeCandidateButton
            entityId={card.id}
            onDone={() => onMerged?.()}
          />
        )}
        {/* «Удалить с воронки» имеет смысл ТОЛЬКО когда кандидат реально в воронке
            (есть application). На «Все кандидаты» пул-кандидат в воронку не входит —
            раньше кнопка висела всегда и слала application_id=0 (no-op). Маша: в пуле
            этой кнопки быть не должно. */}
        {primaryBlock?.application_id ? (
          <button
            onClick={() => cardRemoveFromVacancy(primaryBlock.application_id)}
            className="hf-profile-action-btn"
            disabled={readonly}
            style={roStyle}
          >
            <X className="hf-profile-action-icon" /> Удалить с воронки
          </button>
        ) : null}
        <button
          onClick={handleEmail}
          className="hf-profile-action-btn"
          disabled={readonly}
          style={roStyle}
        >
          <Send className="hf-profile-action-icon" /> Отправить
        </button>
        {/* «Поделиться» ВЫДАЁТ публичную ссылку (создаёт её на сервере) — это
            запись, наблюдателю недоступна. */}
        <button
          onClick={handleShareCandidate}
          className="hf-profile-action-btn"
          disabled={readonly}
          style={roStyle}
          title="Скопировать публичную ссылку предпросмотра для заказчика (действует 30 дней)"
        >
          <ExternalLink className="hf-profile-action-icon" /> Поделиться
        </button>
        <button
          onClick={onEdit}
          className="hf-profile-action-btn"
          disabled={readonly}
          style={roStyle}
        >
          <PenSquare className="hf-profile-action-icon" /> Редактировать
        </button>
        {currentUser?.role === 'superadmin' && (
          <button
            onClick={handleArchive}
            className="hf-profile-action-btn"
            title="Отправить кандидата в теневой архив (участвует в проверке дублей)"
          >
            <Archive className="hf-profile-action-icon" /> В архив
          </button>
        )}
      </div>

      {/* ---- Name + Contact info (left column) | Photo (right column) ---- */}
      <div className="hf-profile-summary">
        <div className="hf-profile-summary-copy">
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="hf-profile-title">
              {card.name}
            </h2>
            {/* Яркие ярлыки у ФИО. Раньше это был свободный текст в
                extra_data.headline_tags со своей палитрой, теперь — тот же
                справочник, что и «Метки» (variant='headline'): выпадающий
                список уже заведённых, выбор цвета, создание новой. Признак
                «показывать у имени» живёт на связи кандидат↔метка, поэтому одна
                метка у одного человека ярлык, у другого — обычная.
                Перетаскивание порядка убрано: в справочнике порядка нет,
                список сортируется по имени — как у меток. */}
            <TagPicker entityId={card.id} variant="headline" disabled={readonly} />
          </div>
          {(card.position || card.company) && (
            <p className="hf-profile-subtitle">
              {card.position}
              {card.position && card.company && (
                <span className="mx-1.5 text-[color:var(--hf-alpha-400)] hf-dark-disabled:text-[color:var(--hf-white-alpha-30)]">
                  &bull;
                </span>
              )}
              {card.company}
            </p>
          )}
          {card.phone && (
            <InfoRow label="Телефон">
              <div className="flex items-center gap-2">
                <a
                  href={`tel:${card.phone}`}
                  className="text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)] hover:text-[var(--hf-cyan-700)] hf-dark-disabled:hover:text-[var(--hf-white)] transition-colors"
                >
                  {formatPhoneDisplay(card.phone)}
                </a>
                {/* Messenger icons */}
                <a
                  href={`https://wa.me/${card.phone.replace(/\D/g, "")}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-[22px] h-[22px] rounded-full bg-[var(--hf-ui-social-whatsapp)] flex items-center justify-center hover:opacity-80"
                  title="WhatsApp"
                >
                  <Phone className="w-[11px] h-[11px] text-[var(--hf-white)]" />
                </a>
                {/* Telegram-иконка — только при реальном username: по номеру
                    телефона валидной публичной t.me-ссылки не существует. */}
                {card.telegram_username && (
                  <a
                    href={`https://t.me/${card.telegram_username.replace(/^@/, "")}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="w-[22px] h-[22px] rounded-full bg-[var(--hf-ui-social-telegram)] flex items-center justify-center hover:opacity-80"
                    title="Telegram"
                  >
                    <Send className="w-[11px] h-[11px] text-[var(--hf-white)]" />
                  </a>
                )}
              </div>
            </InfoRow>
          )}
          {extraPhones.map((ph) => (
            <InfoRow key={`ph-${ph}`} label="Ещё телефон">
              <div className="flex items-center gap-2">
                <a
                  href={`tel:${ph}`}
                  className="text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)] hover:text-[var(--hf-cyan-700)] hf-dark-disabled:hover:text-[var(--hf-white)] transition-colors"
                >
                  {formatPhoneDisplay(ph)}
                </a>
                <a
                  href={`https://wa.me/${ph.replace(/\D/g, "")}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-[22px] h-[22px] rounded-full bg-[var(--hf-ui-social-whatsapp)] flex items-center justify-center hover:opacity-80"
                  title="WhatsApp"
                >
                  <Phone className="w-[11px] h-[11px] text-[var(--hf-white)]" />
                </a>
              </div>
            </InfoRow>
          ))}
          {card.email && (
            <InfoRow label="Эл. почта">
              <a
                href={`mailto:${card.email}`}
                className="text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)] hover:text-[var(--hf-cyan-700)] hf-dark-disabled:hover:text-[var(--hf-white)] transition-colors"
              >
                {card.email}
              </a>
            </InfoRow>
          )}
          {extraEmails.map((em) => (
            <InfoRow key={`em-${em}`} label="Ещё почта">
              <a
                href={`mailto:${em}`}
                className="text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)] hover:text-[var(--hf-cyan-700)] hf-dark-disabled:hover:text-[var(--hf-white)] transition-colors"
              >
                {em}
              </a>
            </InfoRow>
          ))}
          {card.telegram_username && (
            <InfoRow label="Telegram">
              <a
                href={`https://t.me/${card.telegram_username.replace(/^@/, "")}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)] hover:text-[var(--hf-cyan-700)] hf-dark-disabled:hover:text-[var(--hf-white)] transition-colors"
              >
                {card.telegram_username}
              </a>
            </InfoRow>
          )}
          {extraTelegrams.map((tg) => (
            <InfoRow key={`tg-${tg}`} label="Ещё Telegram">
              <a
                href={`https://t.me/${tg.replace(/^@/, "")}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)] hover:text-[var(--hf-cyan-700)] hf-dark-disabled:hover:text-[var(--hf-white)] transition-colors"
              >
                {tg.startsWith("@") ? tg : `@${tg}`}
              </a>
            </InfoRow>
          ))}
          {card.age && (
            <InfoRow label="Возраст">
              <span className="text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)]">
                {card.age}
              </span>
            </InfoRow>
          )}
          {card.city && (
            <InfoRow label="Город">
              <span className="text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)] inline-flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5 text-[var(--hf-main-500)] hf-dark-disabled:text-[var(--hf-dark-500)]" />
                {card.city}
              </span>
            </InfoRow>
          )}
          {card.salary && (
            <InfoRow label="Зарплата">
              <span className="text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)]">
                {card.salary}
              </span>
            </InfoRow>
          )}
          {card.total_experience && (
            <InfoRow label="Опыт">
              <span className="text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)]">
                {card.total_experience}
              </span>
            </InfoRow>
          )}
          {(card.source || card.source_url) && (
            <InfoRow label="Источник">
              {card.source_url ? (
                <a
                  href={card.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[var(--hf-cyan-700)] hf-dark-disabled:text-[var(--hf-accent)] hover:text-[var(--hf-red-500)] hf-dark-disabled:hover:text-[var(--hf-accent-hover)] transition-colors inline-flex items-center gap-1"
                >
                  {card.source || "Ссылка"} <ExternalLink className="w-3 h-3" />
                </a>
              ) : (
                <span className="text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)]">
                  {card.source}
                </span>
              )}
            </InfoRow>
          )}
          {/* «О себе» — краткое описание кандидата (extra_data.summary), которое
              достаёт парсер резюме или пишет рекрутёр в модалке «Парсинг резюме».
              Раньше сохранялось «в никуда» (на карточке не показывалось). */}
          {typeof card.extra_data?.summary === "string" &&
            card.extra_data.summary.trim() && (
              <InfoRow label="О себе">
                <span className="whitespace-pre-wrap break-words text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-dark-200)]">
                  {card.extra_data.summary.trim()}
                </span>
              </InfoRow>
            )}

          {/* Tags row */}
          <InfoRow label="Метки">
            <div className="flex flex-wrap items-center gap-1.5">
              {/* Авто-метки HR: кто забрал кандидата в воронку. Проставляются
                  бэкендом (extra_data.system_hr_tags). Клик по метке ведёт прямо
                  в эту воронку конкретного рекрутёра (?v=…&recruiter=…&entity=…),
                  как будто её выбрали в сайдбаре вручную. Ручное проставление
                  меток здесь убрано — только авто HR + показ старых ручных. */}
              {readSystemHrTags(card.extra_data).map((hr) => {
                const label = `HR: ${hr.name}${hr.vacancy_title ? ` · ${hr.vacancy_title}` : ""}`;
                const chipBase =
                  "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-[var(--hf-bg-panel)] text-[var(--hf-main-900)] border border-[color:var(--hf-main-200)] hf-dark-disabled:bg-[var(--hf-white-alpha-06)] hf-dark-disabled:text-[var(--hf-dark-200)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)]";
                if (typeof hr.vacancy_id !== "number") {
                  return (
                    <span
                      key={`hr-${hr.hr_id}`}
                      title={
                        hr.source === "board"
                          ? "Ведущий HR — назначен на доске «Штат»"
                          : "Закреплённый HR — проставляется автоматически по воронке"
                      }
                      className={chipBase}
                    >
                      <Lock className="w-3 h-3 opacity-50" />
                      {label}
                    </span>
                  );
                }
                return (
                  <button
                    key={`hr-${hr.hr_id}`}
                    type="button"
                    title={`Открыть воронку «${hr.vacancy_title || ""}» — рекрутёр ${hr.name}`}
                    onClick={() =>
                      // stage=all — чтобы воронка показала ВСЕ этапы и подхватила
                      // кандидата на любом его этапе (без stage вкладка встаёт на
                      // первый этап, и кандидат с другого этапа не выбирается).
                      navigate(
                        `/my-funnels?v=${hr.vacancy_id}&recruiter=${hr.hr_id}&entity=${card.id}&stage=all`,
                      )
                    }
                    className={clsx(
                      chipBase,
                      "cursor-pointer transition-colors hover:border-[color:var(--hf-main-400)] hover:bg-[var(--hf-main-100)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-10)]",
                    )}
                  >
                    <Lock className="w-3 h-3 opacity-50" />
                    {label}
                    <ChevronRight className="w-3 h-3 opacity-60" />
                  </button>
                );
              })}
              {localTags.map((t) => (
                <span
                  key={t}
                  className="group inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-[var(--hf-cyan-50)] hf-dark-disabled:bg-[var(--hf-accent-bg-15)] text-[var(--hf-cyan-700)] hf-dark-disabled:text-[var(--hf-accent)] border border-[var(--hf-cyan-200)] hf-dark-disabled:border-[color:var(--hf-accent-border-20)]"
                >
                  {t}
                  <button
                    onClick={() => handleRemoveTag(t)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity hover:text-[var(--hf-status-red)]"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
              {/* Метки из справочника организации. Раньше их здесь можно было
                  только СМОТРЕТЬ: «+» жил лишь в воронке, и пометить кандидата
                  (например, кто его привёл) из общей базы было нельзя — а
                  ставят их чаще всего именно отсюда, когда кандидат ещё ни в
                  одной воронке. Компонент общий с воронкой. */}
              <TagPicker entityId={card.id} disabled={readonly} />
            </div>
          </InfoRow>
        </div>
        {/* Avatar photo (right column) */}
        {card.photo_url ? (
          <img
            src={card.photo_url}
            alt={card.name}
            referrerPolicy="no-referrer"
            className="hf-profile-photo"
            onError={(e) => {
              const el = e.currentTarget as HTMLImageElement;
              el.style.display = "none";
              el.nextElementSibling?.classList.remove("hidden");
            }}
          />
        ) : null}
        <div
          className={clsx(
            "hf-profile-photo",
            !card.photo_url && "hf-profile-photo-fallback",
            card.photo_url && "hidden",
          )}
        >
          {getInitials(card.name)}
        </div>
      </div>

      {/* Анкета теперь — чип в ряду действий живого контейнера (ниже), отдельной
          кнопки над стеком больше нет. Дровер остаётся здесь. */}
      {anketaOpen && (
        <Suspense fallback={null}>
          <AnketaDrawer
            open={anketaOpen}
            onOpenChange={setAnketaOpen}
            entityId={card.id}
            entityName={card.name}
          />
        </Suspense>
      )}

      {/* ── СТЕК ИСТОРИЧЕСКИХ КОНТЕЙНЕРОВ (новая модель): не вакансии, а
          [ собственный живой контейнер ] + extra_data.merged_from[]. Живой —
          первым, интерактивный (композер/чипы/смена этапа/«...»); merged —
          READ-ONLY (только статус + сабтайтл вакансии + лог из notes). Цвет
          каждого контейнера — СТРОГО по его собственному status (без правила
          «≥2 ⇒ серый»). vacancy_id nullable → сабтайтл только если есть. ── */}
      {containers.map((c) => (
        <CandidateVacancyCard
          key={`${c.origin}-${c.applicationId}`}
          card={card}
          applicationId={c.applicationId}
          vacancyTitle={c.vacancyTitle}
          currentStage={c.status}
          notes={c.notes}
          events={c.events}
          addedAt={c.addedAt}
          recruiter={c.recruiter}
          readonly={c.origin === "merged" || readonly}
          dimmed={c.origin === "merged"}
          // Лента наблюдателя — ПОЛНАЯ: snapshot только у влитого дубля.
          snapshot={c.origin === "merged"}
          stageOptions={stagePickerOptions}
          getStageLabel={getStackStageLabel}
          onChangeStage={cardChangeStage}
          onComment={cardActions.comment}
          onDeleteHistory={cardActions.deleteHistory}
          onEditHistory={cardActions.editHistory}
          onPin={cardActions.pin}
          pinnedEntryKey={c.pinnedEntryKey}
          onDeleteNote={cardActions.deleteNote}
          onEditNote={cardActions.editNote}
          onUploadFile={cardActions.uploadFile}
          onAnketa={c.origin === "live" ? () => setAnketaOpen(true) : undefined}
          onReact={c.origin === "live" ? cardActions.react : undefined}
          files={c.files}
          onDeleteFile={c.origin === "live" && !readonly ? cardActions.deleteFile : undefined}
          // Карточка теперь одна НА ВОРОНКУ, поэтому в шапке — её собственный
          // этап и название воронки. Список «этапы по воронкам» и бейдж воронки
          // у комментария остаются только в запасном виде (заявок нет).
          resolveNoteVacancyLabel={
            activityBlocks.length > 0 ? undefined : resolveNoteVacancyLabel
          }
          funnelStages={
            c.origin === "live" && activityBlocks.length === 0
              ? funnelStages
              : undefined
          }
        />
      ))}

      {/* Блок «Комментарии» (entity-уровень) убран: каждый контейнер показывает
          свой лог сам, а влитые заметки задваивались здесь (на «Новом» висела
          отказная заметка источника). Если нужен entity-уровень комментариев —
          они во вкладке «Личные заметки». */}

      <div className="mt-[30px]">
        <div className="flex h-[49.333px] items-start gap-[var(--hf-space-xxl)] overflow-x-auto no-scrollbar border-b border-[var(--hf-main-300)] pb-[20px] hf-dark-disabled:border-[color:var(--hf-white-alpha-06)]">
          {/* Одна вкладка «Анкета» на каждое прохождение (ClickUp-архив), затем —
              ОТДЕЛЬНАЯ вкладка «Анкета» под нативную заполненную форм-анкету
              (если она есть), а не дублирование нативной анкеты под каждым
              прохождением. Если нет ни прохождений, ни нативных анкет — одна
              вкладка-заглушка с пустым состоянием (с бейджем непрочитанных).
              Подсказка при наведении — «воронка · этап», чтобы длинный ряд
              одинаковых «Анкета» различать. */}
          {participations.map((p, i) => {
            const active = detailSection === "anketa" && anketaIndex === i;
            const hint =
              [p.vacancy_title, p.status].filter(Boolean).join(" · ") || undefined;
            return (
              <button
                key={`anketa-participation-${i}`}
                type="button"
                title={hint}
                onClick={() => {
                  onDetailSectionChange("anketa");
                  setAnketaIndex(i);
                }}
                className={clsx(
                  "relative h-[24px] shrink-0 border-b-[2px] text-[length:var(--hf-fs-xs)] leading-[var(--hf-lh-primary)] font-medium transition-colors",
                  active
                    ? "border-[var(--hf-main-900)] text-[var(--hf-main-900)] hf-dark-disabled:border-[color:var(--hf-white)] hf-dark-disabled:text-[var(--hf-white)]"
                    : "border-transparent text-[var(--hf-main-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)] hover:text-[var(--hf-main-900)] hf-dark-disabled:hover:text-[var(--hf-white)]",
                )}
              >
                Анкета
              </button>
            );
          })}
          {hasNativeAnketa && (
            <button
              key="anketa-native"
              type="button"
              title="Заполненная анкета"
              onClick={() => {
                onDetailSectionChange("anketa");
                setAnketaIndex(nativeTabIndex);
              }}
              className={clsx(
                "relative h-[24px] shrink-0 border-b-[2px] text-[length:var(--hf-fs-xs)] leading-[var(--hf-lh-primary)] font-medium transition-colors",
                detailSection === "anketa" && anketaIndex === nativeTabIndex
                  ? "border-[var(--hf-main-900)] text-[var(--hf-main-900)] hf-dark-disabled:border-[color:var(--hf-white)] hf-dark-disabled:text-[var(--hf-white)]"
                  : "border-transparent text-[var(--hf-main-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)] hover:text-[var(--hf-main-900)] hf-dark-disabled:hover:text-[var(--hf-white)]",
              )}
            >
              Анкета
              {anketaCount > 0 && (
                <span className="ml-1 inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full bg-[#e11d48] text-white text-[11px] leading-none align-middle">
                  {anketaCount > 9 ? "9+" : anketaCount}
                </span>
              )}
            </button>
          )}
          {participations.length === 0 && !hasNativeAnketa && (
            <button
              key="anketa-empty"
              type="button"
              onClick={() => {
                onDetailSectionChange("anketa");
                setAnketaIndex(0);
              }}
              className={clsx(
                "relative h-[24px] shrink-0 border-b-[2px] text-[length:var(--hf-fs-xs)] leading-[var(--hf-lh-primary)] font-medium transition-colors",
                detailSection === "anketa"
                  ? "border-[var(--hf-main-900)] text-[var(--hf-main-900)] hf-dark-disabled:border-[color:var(--hf-white)] hf-dark-disabled:text-[var(--hf-white)]"
                  : "border-transparent text-[var(--hf-main-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)] hover:text-[var(--hf-main-900)] hf-dark-disabled:hover:text-[var(--hf-white)]",
              )}
            >
              Анкета
              {anketaCount > 0 && (
                <span className="ml-1 inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full bg-[#e11d48] text-white text-[11px] leading-none align-middle">
                  {anketaCount > 9 ? "9+" : anketaCount}
                </span>
              )}
            </button>
          )}
          {/* По одной вкладке «Резюме» на каждый источник резюме. Если у
              кандидата резюме нет вовсе — одна вкладка-заглушка ([null]),
              чтобы показать пустое состояние. Вкладка «Личные заметки» убрана —
              заметки больше не используются. */}
          {(resumeSources.length > 0 ? resumeSources : [null]).map((_s, i) => (
            <button
              key={i}
              type="button"
              onClick={() => {
                onDetailSectionChange("resume");
                setResumeIndex(i);
              }}
              className={clsx(
                "h-[24px] shrink-0 border-b-[2px] text-[length:var(--hf-fs-xs)] leading-[var(--hf-lh-primary)] font-medium transition-colors",
                detailSection === "resume" && resumeIndex === i
                  ? "border-[var(--hf-main-900)] text-[var(--hf-main-900)] hf-dark-disabled:border-[color:var(--hf-white)] hf-dark-disabled:text-[var(--hf-white)]"
                  : "border-transparent text-[var(--hf-main-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)] hover:text-[var(--hf-main-900)] hf-dark-disabled:hover:text-[var(--hf-white)]",
              )}
            >
              Резюме
            </button>
          ))}
        </div>
        {detailSection === "resume" && (
          <ResumeTab
            key={`resume-${filesNonce}`}
            card={card}
            activeIndex={Math.min(
              resumeIndex,
              Math.max(0, resumeSources.length - 1),
            )}
          />
        )}
        {detailSection === "anketa" && (
          <AnketaTab
            activeIndex={anketaIndex}
            participations={participations}
            nativeDispatches={nativeDispatches}
            onDispatchDeleted={(id) => setNativeDispatches((prev) => prev.filter((d) => d.id !== id))}
          />
        )}
      </div>
    </div>
  );
});
