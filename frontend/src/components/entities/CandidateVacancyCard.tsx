import { useState, useEffect, useMemo, useCallback, useRef, memo } from "react";
import type { CSSProperties } from "react";
import { createPortal } from "react-dom";
import {
  Search,
  Paperclip,
  Mail,
  Calendar,
  ThumbsUp,
  Phone,
  Check,
  Trash2,
  ChevronDown,
  ClipboardList,
  X,
} from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { HuntflowComposer } from "@/components/hr/HuntflowComposer";
import { HuntflowRichInput } from "@/components/hr/HuntflowRichInput";
import { HuntflowActionChip as ActionChip } from "@/components/hr/HuntflowControls";

import { downloadEntityFile } from "@/services/api/entities";
import type { ActivityEvent, EntityFile } from "@/services/api/entities";
import type { KanbanCard } from "@/services/api/candidates";
import {
  matchesTimelineFilter,
  TIMELINE_ACTION_FILTERS,
  isRejectedStage,
  nextStageStatus,
  type ContainerNote,
  type EntryReaction,
} from "@/components/entities/candidateDetail/model";
import { HfLoadingSpinner } from "@/components/ui/HfLoadingSpinner";
import { backdropClose } from '@/utils/backdropClose';
import { buildTimelineRows, pinTimelineRow } from "@/components/entities/candidateDetail/timeline";
import { useCommentDraft } from "@/components/entities/candidateDetail/useCommentDraft";
import { TimelineDot } from "@/components/entities/candidateDetail/timelineParts";
import { useTimelineRowActions } from "@/components/entities/candidateDetail/useTimelineRowActions";
import { TimelineEntry } from "@/components/entities/candidateDetail/TimelineEntry";

// ── Module-scope helpers/constants moved verbatim from AllCandidatesPage
//    (used only by CandidateVacancyCard). ──

const normalizeStageLabel = (value: string) =>
  value.toLowerCase().replace(/\s+/g, " ").trim();

const TIMELINE_EXPAND_DELAY_MS = 420;

// ── Цвет карточки этапа: ровно 2 варианта (по фидбэку Маши). ЗЕЛЁНАЯ для
// активного этапа одиночной карточки; СЕРАЯ для отказа ИЛИ для любой карточки
// объединённого кандидата (≥2 карточек = историческая/смёрдженная лента).
// Переопределяем CSS-переменные, которые читает .hf-stage-card.
const GREEN_STAGE_CARD_STYLE: CSSProperties = {
  "--hf-stage-accent": "#22c55e",
  "--hf-stage-card-bg": "rgba(34, 197, 94, 0.1)",
} as CSSProperties;
const GRAY_STAGE_CARD_STYLE: CSSProperties = {
  "--hf-stage-accent": "var(--hf-main-300)",
  "--hf-stage-card-bg": "var(--hf-bg-panel)",
} as CSSProperties;

// ================================================================
// CANDIDATE VACANCY CARD — одна интерактивная карточка этапа на ОДНУ вакансию.
// Извлечена из singleton-карточки InfoTab; вся state — ПЕР-ИНСТАНС, поэтому
// N карточек (смёрдженный кандидат) работают независимо. Рендерит СВОИ events
// (история переходов именно этой заявки) в той же avatar/«Действия»-таймлайн-
// разметке, что и исходная карточка.
// ================================================================
const CandidateVacancyCard = memo(
function CandidateVacancyCard({
  card,
  applicationId,
  vacancyTitle,
  currentStage,
  notes,
  events,
  addedAt,
  readonly,
  dimmed,
  snapshot = false,
  stageOptions,
  getStageLabel,
  onChangeStage,
  onComment,
  onDeleteHistory,
  onEditHistory,
  onPin,
  pinnedEntryKey,
  onDeleteNote,
  onEditNote,
  onUploadFile,
  onAnketa,
  anketaCount,
  onReact,
  files,
  onDeleteFile,
  onRemoveFromVacancy,
  isPreviousSeries = false,
  recruiter,
  resolveNoteVacancyLabel,
  funnelStages,
  downloadFile,
  fileUrlOf,
}: {
  card: KanbanCard;
  applicationId: number;
  // vacancy_id может отсутствовать у контейнера → vacancyTitle nullable.
  vacancyTitle: string | null;
  currentStage: string;
  // Лог контейнера: его собственные комментарии (notes) → строки таймлайна.
  notes: ContainerNote[];
  // Только для живого контейнера: история переходов (StageTransition).
  events?: ActivityEvent[];
  // Дата добавления контейнера (live: card.created_at; merged: m.added_at).
  addedAt?: string;
  // READ-ONLY (merged-контейнеры): без композера/чипов/смены этапа/удаления.
  readonly: boolean;
  // ВИЗУАЛЬНОЕ приглушение (серая карточка) отдельно от readonly. Наблюдатель
  // (is_readonly) блокирует действия (readonly=true), но карточка при этом должна
  // оставаться ЦВЕТНОЙ/зелёной, а не серой — иначе всё сливается и не читается.
  // Серым красим только реально неактивное: merged-снапшот/архив. Если не передан
  // — падаем на readonly (старое поведение для воронок/архива не меняется).
  dimmed?: boolean;
  // СНАПШОТ влитого дубля (merged): его лог — только собственные заметки, без
  // переходов живой заявки и без синтетического «Кандидат добавлен». Отдельно от
  // readonly: у НАБЛЮДАТЕЛЯ readonly=true, но лента у него должна быть ПОЛНАЯ —
  // он «видит всё». Раньше это был один флаг, и наблюдатель открывал карточку с
  // пустой историей (01.10.2026).
  snapshot?: boolean;
  stageOptions: Array<{ status: string; label: string }>;
  getStageLabel: (stage: string) => string;
  // Возвращает false при неудачной смене этапа (или ничего/true — старые
  // колл-сайты) — нужно кнопке «Сохранить» в пикере, чтобы НЕ писать
  // комментарий-«обещание» («Этап: Отказ»), если сам перевод не применился.
  onChangeStage: (
    applicationId: number,
    stage: string,
    comment?: string,
  ) => Promise<boolean | void> | boolean | void;
  onComment: (
    applicationId: number,
    stage: string,
    stageLabel: string,
    text: string,
    // Дописка коммента к прошлой статусной записи: parent_key = reactionKey
    // родителя, stage_at_write_label = метка текущего этапа (плашка).
    opts?: { parent_key?: string; stage_at_write_label?: string },
    // false = сервер комментарий НЕ принял: поле очищать нельзя.
  ) => Promise<boolean | void> | boolean | void;
  onDeleteHistory: (
    applicationId: number,
    historyId: number,
  ) => Promise<void> | void;
  // Правка комментария у записи о переводе (сам этап не трогается).
  onEditHistory?: (
    applicationId: number,
    historyId: number,
    comment: string,
  ) => Promise<void> | void;
  // Закрепить запись наверху ленты воронки (null — снять закреп).
  onPin?: (applicationId: number, entryKey: string | null) => Promise<void> | void;
  // Ключ закреплённой записи этой воронки («e:<id>» / «n:<uuid>»).
  pinnedEntryKey?: string | null;
  // Удаление комментария (extra_data.notes) — отдельно от истории переходов,
  // т.к. это не StageTransition, а запись в JSON-поле кандидата.
  onDeleteNote?: (
    entityId: number,
    noteId: string,
  ) => Promise<void> | void;
  // Редактировать текст комментария (extra_data.notes) — бэк проставляет
  // edited_at, лента показывает «отредактировано» с таймстампом при наведении.
  onEditNote?: (
    entityId: number,
    noteId: string,
    text: string,
  ) => Promise<void> | void;
  onUploadFile: (entityId: number, file: File) => Promise<void> | void;
  // Только живой контейнер: открыть анкеты (чип в ряду действий) + бейдж кол-ва.
  onAnketa?: () => void;
  anketaCount?: number;
  // Тоггл эмодзи-реакции записи таймлайна (entry_key, emoji) → новый список.
  onReact?: (entryKey: string, emoji: string) => Promise<EntryReaction[] | null>;
  // Файлы, прикреплённые к этому контейнеру (показываются под логом, скачиваемы).
  files?: EntityFile[];
  /** Откуда качать файл, если не из живой карточки (корзина: из слепка). */
  downloadFile?: (fileId: number) => Promise<Blob>;
  /** Адрес файла для плеера видео — тот же случай. */
  fileUrlOf?: (fileId: number) => string;
  // Удалить файл (с подтверждением) — обновляет список после удаления.
  onDeleteFile?: (fileId: number) => void;
  // Убрать кандидата из воронки (снять заявку). Только живой контейнер.
  onRemoveFromVacancy?: (applicationId: number) => void;
  // «В предыдущих сериях»: отклик старше переоткрытия вакансии → карточка этапа
  // серая (как в референсе). Смена этапа снимает флаг → карточка зеленеет.
  isPreviousSeries?: boolean;
  // Импортированное прохождение (ClickUp-архив): рекрутёр (чип «HR: Имя»), read-only.
  recruiter?: string;
  // «Все кандидаты»: комменты со ВСЕХ воронок кандидата слиты в один лог, поэтому
  // у каждого нужно показать бейдж воронки (по note.vacancy_id). В воронке проп
  // НЕ передаётся — там лог уже отфильтрован по своей вакансии, бейдж лишний.
  // Возвращает название воронки или null (нет привязки → «Общий», без бейджа).
  resolveNoteVacancyLabel?: (vacancyId?: number | null) => string | null;
  // «Все кандидаты», живой контейнер: этапы кандидата по КАЖДОЙ его воронке. Если
  // воронок ≥2 — в шапке вместо одного «общего» этапа показываем список
  // «этап → воронка» (кандидат реально на разных этапах в разных воронках).
  funnelStages?: Array<{
    vacancyId: number;
    title: string;
    stageLabel: string;
    colorClass: string;
  }>;
}) {
  // --- per-instance UI state (раньше было singleton в InfoTab) ---
  const [showStageDD, setShowStageDD] = useState(false);
  const [pendingStage, setPendingStage] = useState(currentStage);
  const [stageChangeComment, setStageChangeComment] = useState("");
  const [showActionMenu, setShowActionMenu] = useState(false);
  // Видео из «Файлов» открываем в модальном плеере (закрывается X/фоном/Esc).
  const [videoModal, setVideoModal] = useState<{ url: string; name: string } | null>(null);
  const [actionMenuPlacement, setActionMenuPlacement] = useState<
    "above" | "below"
  >("above");
  const [actionSearch, setActionSearch] = useState("");
  const [timelineActionFilter, setTimelineActionFilter] = useState<
    string | null
  >(null);
  // Черновик комментария живёт ДОЛЬШЕ открытой карточки.
  //
  // Разбор случая Влады (07.10.2026): по логам прода её комментарий на сервер
  // не уходил вовсе — ни запроса, ни ошибки. Воспроизвелось просто: набрал
  // текст, переключился на другого кандидата (или ушёл добавить метку) — и
  // набранное исчезло молча, без предупреждения и без следа. Теперь черновик
  // привязан к паре «кандидат + воронка», переживает переключение карточек,
  // перезагрузку вкладки и стирается только после успешного сохранения.
  const [comment, setComment] = useCommentDraft(`${card.id}:${applicationId}`);
  const [commentComposerOpen, setCommentComposerOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  // Гейт от даблклика/медленной сети: без него «Сохранить» в дропдауне смены
  // этапа можно нажать второй раз до ответа сервера — и комментарий +
  // переход этапа создаются ДВАЖДЫ (дублируется вся пара строк в таймлайне).
  const [savingStageChange, setSavingStageChange] = useState(false);
  const [sendingComment, setSendingComment] = useState(false);
  const [showAllTimeline, setShowAllTimeline] = useState(false);
  const [timelineExpanding, setTimelineExpanding] = useState(false);

  const stageRef = useRef<HTMLDivElement>(null);
  const actionMenuRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const actionSearchRef = useRef<HTMLInputElement>(null);
  const timelineExpandTimerRef = useRef<number | null>(null);

  const statusLabel = getStageLabel(currentStage);
  const stageTitle = statusLabel;

  // Цвет карточки СТРОГО по СВОЕМУ статусу контейнера: серая если этап
  // отклонён (rejected/fired/archived), иначе зелёная. Слияние НЕ
  // перекрашивает живую карточку — каждый контейнер изолирован.
  // + «В предыдущих сериях»: пока отклик не тронут после переоткрытия — серая
  // (референс Huntflow: «Новые» серая → после взятия в работу зелёная).
  // + merged (readonly) — это исторический снапшот прошлого участия, не
  // текущая активность, поэтому всегда серая, а не зелёная.
  const grayed = isRejectedStage(currentStage) || isPreviousSeries || (dimmed ?? readonly);
  const stageCardStyle: CSSProperties = grayed
    ? GRAY_STAGE_CARD_STYLE
    : GREEN_STAGE_CARD_STYLE;

  // Таймлайн контейнера = его СОБСТВЕННЫЕ notes (комментарии) как строки лога,
  // плюс — только для живого контейнера — реальная история переходов (events).
  // Merged-контейнеры показывают строго свои notes (read-only).
  const timelineItems = useMemo(
    () =>
      buildTimelineRows({
        notes, events, snapshot, getStageLabel, addedAt,
        createdAt: card.created_at, recruiterName: card.recruiter_name,
        resolveNoteVacancyLabel,
      }),
    [notes, events, snapshot, getStageLabel, addedAt, card.created_at, card.recruiter_name, resolveNoteVacancyLabel],
  );

  const filteredTimelineItems = useMemo(() => {
    if (!timelineActionFilter) return timelineItems;
    return timelineItems.filter((event) =>
      matchesTimelineFilter(event, timelineActionFilter),
    );
  }, [timelineItems, timelineActionFilter]);
  // Закреплённая запись — первой (pinTimelineRow).
  const orderedTimelineItems = useMemo(
    () => pinTimelineRow(filteredTimelineItems, pinnedEntryKey),
    [filteredTimelineItems, pinnedEntryKey],
  );
  const visibleTimelineItems = showAllTimeline
    ? orderedTimelineItems
    : orderedTimelineItems.slice(0, 5);
  const hasHiddenTimelineItems = orderedTimelineItems.length > 5;
  // Показываем только фильтры, по которым в таймлайне реально ЕСТЬ записи (+ поиск).
  // Пустые (письмо/интервью/звонок/файл/оффер и пр.) скрыты.
  const visibleActionFilters = TIMELINE_ACTION_FILTERS.filter(
    (item) =>
      item.toLowerCase().includes(actionSearch.trim().toLowerCase()) &&
      timelineItems.some((it) => matchesTimelineFilter(it, item)),
  );
  const isCommentComposerOpen =
    commentComposerOpen || comment.trim().length > 0;

  // Строки ленты: правка, меню, реакции, закреп, копирование (useTimelineRowActions).
  const rowActions = useTimelineRowActions({
    card, applicationId, pinnedEntryKey, onReact, onEditHistory, onEditNote, onPin,
  });

  const stagePickerOptions = useMemo(
    () =>
      stageOptions.map((option) => ({
        label: option.label,
        status: option.status,
        isRealStage: true,
      })),
    [stageOptions],
  );

  // currentStage (сырой ключ этапа) не всегда дословно совпадает с каким-то
  // option.status (кастомные/устаревшие ключи) — тогда сверяем по лейблу.
  // Резолвим ОДИН РАЗ здесь и используем как единственный источник правды для
  // pendingStage, чтобы при рендере подсвечивался только реальный текущий/
  // выбранный вариант, а не оба сразу (баг «выбор не отлипает»).
  const resolvedCurrentStageStatus = useMemo(() => {
    const exact = stagePickerOptions.find((o) => o.status === currentStage);
    if (exact) return exact.status;
    const byLabel = stagePickerOptions.find(
      (o) => normalizeStageLabel(o.label) === normalizeStageLabel(statusLabel),
    );
    return byLabel ? byLabel.status : currentStage;
  }, [stagePickerOptions, currentStage, statusLabel]);

  useEffect(() => {
    setTimelineExpanding(false);
    if (timelineExpandTimerRef.current) {
      window.clearTimeout(timelineExpandTimerRef.current);
      timelineExpandTimerRef.current = null;
    }
    return () => {
      if (timelineExpandTimerRef.current) {
        window.clearTimeout(timelineExpandTimerRef.current);
        timelineExpandTimerRef.current = null;
      }
    };
  }, [applicationId, timelineActionFilter]);

  const handleTimelineMoreToggle = useCallback(() => {
    if (timelineExpanding) return;
    if (!hasHiddenTimelineItems) return;
    if (showAllTimeline) {
      setShowAllTimeline(false);
      return;
    }
    setTimelineExpanding(true);
    if (timelineExpandTimerRef.current) {
      window.clearTimeout(timelineExpandTimerRef.current);
    }
    timelineExpandTimerRef.current = window.setTimeout(() => {
      setShowAllTimeline(true);
      setTimelineExpanding(false);
      timelineExpandTimerRef.current = null;
    }, TIMELINE_EXPAND_DELAY_MS);
  }, [hasHiddenTimelineItems, showAllTimeline, timelineExpanding]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (stageRef.current && !stageRef.current.contains(e.target as Node))
        setShowStageDD(false);
      if (
        actionMenuRef.current &&
        !actionMenuRef.current.contains(e.target as Node)
      )
        setShowActionMenu(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Сидим pendingStage/комментарий ТОЛЬКО в момент ОТКРЫТИЯ дропдауна (переход
  // false→true), а не на каждый пересчёт resolvedCurrentStageStatus, пока он
  // открыт. Раньше resolvedCurrentStageStatus был в зависимостях эффекта
  // напрямую — если currentStage/stageOptions пересчитывались (напр. фоновый
  // поллинг активности) ПОКА пользователь уже выбрал новый этап и вводит
  // коммент, эффект тихо перезатирал выбор обратно на текущий этап. Юзер
  // жал «Сохранить» — коммент с меткой уходил, а реальная смена этапа
  // молча НЕ срабатывала (pendingStage===currentStage к моменту клика),
  // хотя выглядело, будто всё прошло. Баг был интермиттентным — ловился не
  // на каждой попытке, только если фоновое обновление успевало прилететь
  // ровно в окно между выбором этапа и сохранением.
  // Этап, который помечен при ОТКРЫТИИ пикера — следующий за текущим
  // (Huntflow: рекрутёр двигает кандидата вперёд, ему остаётся нажать
  // «Сохранить»). Отказ/резерв/архив авто-подстановкой не выбираются.
  const defaultPickerStage = useMemo(
    () => nextStageStatus(stagePickerOptions, resolvedCurrentStageStatus),
    [stagePickerOptions, resolvedCurrentStageStatus],
  );
  // Помечен этап, на котором кандидат уже стоит (или сам пикер не нашёл
  // следующего) — переводить некуда.
  const stageAlreadyCurrent = pendingStage === resolvedCurrentStageStatus;
  const stageDDWasOpenRef = useRef(false);
  useEffect(() => {
    if (showStageDD && !stageDDWasOpenRef.current) {
      setPendingStage(defaultPickerStage);
      setStageChangeComment("");
    }
    stageDDWasOpenRef.current = showStageDD;
  }, [showStageDD, defaultPickerStage]);

  useEffect(() => {
    if (showActionMenu) {
      requestAnimationFrame(() => actionSearchRef.current?.focus());
    }
  }, [showActionMenu]);

  // --- per-instance action handlers ---
  const handleComment = async () => {
    if (!comment.trim() || sendingComment) {
      if (!comment.trim()) toast.error("Введите комментарий");
      return;
    }
    setSendingComment(true);
    try {
      const ok = await onComment(
        applicationId,
        currentStage,
        statusLabel,
        comment.trim(),
      );
      // Поле чистим ТОЛЬКО когда сервер подтвердил. Раньше текст стирался
      // всегда, и неудачное сохранение выглядело как удачное: комментарий
      // исчезал из поля, в ленте его не было, набранное пропадало совсем
      // (жалоба Влады 07.10.2026: «написала коммент, сохранила… он исчез»).
      if (ok !== false) setComment("");
    } finally {
      setSendingComment(false);
    }
  };

  const saveStageChangeComment = async (): Promise<boolean> => {
    const text = stageChangeComment.trim();
    if (!text) return true;
    const targetOption = stagePickerOptions.find(
      (option) => option.status === pendingStage,
    );
    const ok = await onComment(
      applicationId,
      pendingStage,
      targetOption?.label || statusLabel,
      text,
    );
    // Не сохранилось — текст в окне остаётся, окно не закрываем.
    if (ok === false) return false;
    setStageChangeComment("");
    return true;
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await onUploadFile(card.id, file);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Скачать прикреплённый к контейнеру файл (работает и на read-only merged).
  const handleDownloadFile = async (fileId: number, fileName: string) => {
    try {
      const blob = downloadFile ? await downloadFile(fileId) : await downloadEntityFile(card.id, fileId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Ошибка при скачивании");
    }
  };

  return (
    <div className="hf-stage-card" style={stageCardStyle}>
      {/* Hidden file input (только живой контейнер — у merged нет действий) */}
      {!readonly && (
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          onChange={handleFileUpload}
          accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
        />
      )}

      {/* ---- Stage block (Huntflow: colored bg + vacancy name + change button) ---- */}
      <div className="hf-stage-card-head">
        <div className="hf-stage-card-head-row">
          <div>
            {funnelStages && funnelStages.length >= 2 ? (
              // Кандидат в ≥2 воронках и реально на разных этапах — единый «общий»
              // этап врёт. Показываем список «этап (цветной чип) → воронка».
              <div>
                <div className="mb-[4px] text-[length:var(--hf-fs-2xs)] text-[color:var(--hf-alpha-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
                  Этапы по воронкам
                </div>
                <div className="flex flex-col gap-[4px]">
                  {funnelStages.map((f) => (
                    <div
                      key={f.vacancyId}
                      className="flex items-center gap-[6px]"
                    >
                      <span
                        className={clsx(
                          "inline-flex w-fit shrink-0 items-center rounded-[20px] px-[8px] py-[2px] text-[length:var(--hf-fs-2xs)] font-semibold",
                          f.colorClass,
                        )}
                      >
                        {f.stageLabel}
                      </span>
                      <span className="truncate text-[length:var(--hf-fs-s)] font-medium text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
                        {f.title}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <>
                <div className="hf-stage-card-title">{stageTitle}</div>
                {vacancyTitle && (
                  <div className="hf-stage-card-subtitle">{vacancyTitle}</div>
                )}
              </>
            )}
            {recruiter && (
              <div className="mt-[2px] text-[length:var(--hf-fs-xxs)] text-[color:var(--hf-alpha-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
                HR: {recruiter}
              </div>
            )}
          </div>
          {/* «Сменить этап подбора» + пикер — только живой контейнер. */}
          {!readonly && (
          <div className="relative" ref={stageRef}>
            <button
              onClick={() => setShowStageDD(!showStageDD)}
              className="hf-stage-change-btn"
            >
              Сменить этап подбора
            </button>
            {showStageDD && (
              <div className="hf-stage-picker">
                <div className="hf-stage-picker-list huntflow-scrollbar">
                  {stagePickerOptions.map((option) => {
                    const isSelected = pendingStage === option.status;
                    return (
                      <button
                        type="button"
                        key={`${option.status}-${option.label}`}
                        onClick={() => setPendingStage(option.status)}
                        className={clsx(
                          "hf-stage-picker-option",
                          isSelected
                            ? "hf-stage-picker-option-active"
                            : "hf-stage-picker-option-idle",
                        )}
                      >
                        <span className="truncate">{option.label}</span>
                      </button>
                    );
                  })}
                </div>
                <div className="hf-stage-picker-editor-wrap">
                  {/* Выбран этап, на котором кандидат уже стоит: писать тут
                      нечего — комментарий к «переводу на тот же этап» только
                      мусорил ленту. Вместо поля — серая плашка (как в
                      Huntflow), «Сохранить» недоступно. */}
                  {stageAlreadyCurrent ? (
                    <div className="hf-stage-picker-current">
                      Кандидат сейчас находится на этом этапе подбора
                    </div>
                  ) : (
                  <div className="hf-stage-picker-editor">
                    <HuntflowRichInput
                      value={stageChangeComment}
                      onChange={setStageChangeComment}
                      placeholder="Записать комментарий"
                      showMention
                      toolbarClassName="hf-stage-picker-toolbar"
                      editableClassName="hf-stage-picker-textarea overflow-y-auto"
                    />
                  </div>
                  )}
                  <div className="hf-stage-picker-footer">
                    <button
                      type="button"
                      disabled={savingStageChange || stageAlreadyCurrent}
                      onClick={async () => {
                        if (savingStageChange || stageAlreadyCurrent) return;
                        setSavingStageChange(true);
                        try {
                          const selectedOption = stagePickerOptions.find(
                            (option) => option.status === pendingStage,
                          );
                          const needsStageChange =
                            pendingStage !== currentStage &&
                            selectedOption?.isRealStage;
                          // Сначала пробуем реально сменить этап — и только если
                          // это удалось (или менять было нечего), пишем комментарий.
                          // Раньше было наоборот (коммент → потом смена), и если
                          // смена этапа падала (сеть/гонка), рекрутёр получал
                          // висящий в старом этапе карточки комментарий вида
                          // «Этап: Отказ», который выглядел как принятое решение,
                          // хотя кандидат никуда не переехал.
                          const text = stageChangeComment.trim();
                          if (needsStageChange) {
                            // Комментарий уходит ВМЕСТЕ с переводом и живёт в
                            // самой записи истории. Раньше он сохранялся
                            // отдельной заметкой, и в ленте появлялись ДВЕ
                            // строки об одном событии — «Новый → Интервью с HR»
                            // и «Этап: Интервью с HR» с текстом. Именно это
                            // рекрутёры называли путаницей (24.09.2026).
                            const result = await onChangeStage(
                              applicationId,
                              pendingStage,
                              text || undefined,
                            );
                            if (result === false) {
                              toast.error(
                                "Не удалось сменить этап — комментарий не сохранён. Попробуйте ещё раз.",
                              );
                              return; // дропдаун остаётся открытым, текст коммента не теряется
                            }
                          } else if (text) {
                            const saved = await saveStageChangeComment();
                            if (!saved) return; // текст остаётся в окне
                          }
                          setStageChangeComment("");
                          setShowStageDD(false);
                        } finally {
                          setSavingStageChange(false);
                        }
                      }}
                      className="inline-flex h-[33px] min-w-[74px] items-center justify-center rounded-[var(--hf-radius-s)] border border-[var(--hf-main-900)] bg-[var(--hf-main-900)] px-[11px] text-[length:var(--hf-fs-xxs)] font-medium leading-[var(--hf-lh-secondary)] !text-[var(--hf-white)] transition-colors hover:bg-[var(--hf-main-800)] disabled:opacity-60"
                    >
                      Сохранить
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowStageDD(false)}
                      className="inline-flex h-[33px] min-w-[65px] items-center justify-center rounded-[var(--hf-radius-s)] border border-[var(--hf-alpha-200)] bg-[var(--hf-white)] px-[11px] text-[length:var(--hf-fs-xxs)] font-medium leading-[var(--hf-lh-secondary)] text-[var(--hf-main-900)] transition-colors hover:bg-[var(--hf-ui-hover)] hf-dark-disabled:border-[color:var(--hf-white-alpha-10)] hf-dark-disabled:bg-[var(--hf-white-alpha-05)] hf-dark-disabled:text-[var(--hf-white)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-10)]"
                    >
                      Отмена
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
          )}
        </div>
      </div>

      {/* ---- Comment textarea (Huntflow: "Написать комментарий") — только живой контейнер ---- */}
      {!readonly && (
      <HuntflowComposer
        wrapperClassName="px-[var(--hf-space-xxl)] pt-[var(--hf-space-xxl)] pb-[6px] relative"
        value={comment}
        onChange={setComment}
        open={commentComposerOpen}
        onOpenChange={setCommentComposerOpen}
        placeholder="Написать комментарий"
        onSubmit={handleComment}
        saving={sendingComment}
        onCancel={() => {
          setComment("");
          setCommentComposerOpen(false);
        }}
        showMention
        collapsedClassName="h-[58px] w-full resize-none rounded-[var(--hf-radius-s)] border border-[color:var(--hf-black-alpha-16)] bg-transparent px-[var(--hf-space-xxl)] py-[var(--hf-space-l)] pr-20 text-[length:var(--hf-fs-s)] leading-[var(--hf-lh-primary)] text-[var(--hf-main-900)] placeholder:text-[var(--hf-main-600)] focus:border-[var(--hf-cyan-500)] focus:outline-none hf-dark-disabled:border-[color:var(--hf-white-alpha-06)] hf-dark-disabled:text-[var(--hf-dark-200)] hf-dark-disabled:placeholder:text-[var(--hf-dark-500)] hf-dark-disabled:focus:border-[color:var(--hf-status-blue-badge)]"
        actions={[
          {
            icon: Paperclip,
            label: "Файл",
            onClick: () => fileInputRef.current?.click(),
            loading: uploading,
          },
        ]}
      />
      )}

      {/* ---- Action chips (Huntflow: Письмо | Интервью | Комментарий | Оффер | Файл) — только живой контейнер ---- */}
      {/* Весь ряд пишущий: «Файл», «Удалить с воронки», а «Анкета» открывает
          дровер СОЗДАНИЯ/отправки анкеты (ответы кандидата читаются во вкладке
          «Анкета» под карточкой). Наблюдателю ряд не показываем. */}
      {!snapshot && !readonly && (
      <div className="px-[var(--hf-space-xxl)] pb-hf-l flex items-center gap-[var(--hf-space-s)] border-b border-[color:var(--hf-main-200)] hf-dark-disabled:border-[color:var(--hf-white-alpha-06)] flex-wrap">
        {!isCommentComposerOpen && (
          <>
            <ActionChip
              icon={Paperclip}
              label="Файл"
              onClick={() => fileInputRef.current?.click()}
              loading={uploading}
            />
            {onAnketa && (
              <ActionChip
                icon={ClipboardList}
                label="Анкета"
                notificationCount={anketaCount}
                onClick={onAnketa}
              />
            )}
            {onRemoveFromVacancy && (
              <ActionChip
                icon={X}
                label="Удалить с воронки"
                onClick={() => onRemoveFromVacancy(applicationId)}
              />
            )}
          </>
        )}
      </div>
      )}

      {/* ---- История: лог контейнера (notes + переходы для живого) ---- */}
      <div className="px-[var(--hf-space-xxl)] pt-[7px]">
        {/* Фильтр «Действия» — он только ФИЛЬТРУЕТ ленту, ничего не меняет,
            поэтому наблюдателю нужен; нет его лишь у снапшота влитого дубля. */}
        {!snapshot && (
        <div className="relative mb-hf-l inline-block" ref={actionMenuRef}>
          <button
            type="button"
            onClick={() => {
              setActionMenuPlacement("above");
              setShowActionMenu((value) => !value);
            }}
            className="inline-flex h-[32px] items-center rounded-hf-s border border-transparent bg-[var(--hf-black-alpha-10)] pl-hf-m pr-[6px] text-hf-xxs font-medium leading-[var(--hf-lh-secondary)] text-[var(--hf-main-900)] transition-colors hover:bg-[var(--hf-black-alpha-10)] focus:outline-none focus-visible:outline-none active:bg-[var(--hf-black-alpha-14)] hf-dark-disabled:bg-[var(--hf-white-alpha-05)] hf-dark-disabled:text-[var(--hf-white)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-10)]"
            aria-expanded={showActionMenu}
          >
            Действия: {timelineActionFilter || "Все"}{" "}
            <ChevronDown
              className={clsx(
                "ml-[4px] h-[20px] w-[20px] transition-transform",
                showActionMenu && "rotate-180",
              )}
            />
          </button>
          {showActionMenu ? (
            <div
              className={clsx(
                "absolute left-0 z-[220] w-[400px] overflow-hidden rounded-[var(--hf-radius-s)] bg-[var(--hf-white)] leading-[var(--hf-lh-field)] shadow-[0_0_40px_var(--hf-alpha-300)] hf-dark-disabled:bg-[var(--hf-bg-dark)]",
                actionMenuPlacement === "below"
                  ? "top-full mt-[10px]"
                  : "bottom-full mb-[10px]",
              )}
            >
              <div className="p-[16px] pb-[8px]">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-[10px] top-1/2 h-[16px] w-[16px] -translate-y-1/2 text-[var(--hf-main-500)]" />
                  <input
                    ref={actionSearchRef}
                    value={actionSearch}
                    onChange={(event) => setActionSearch(event.target.value)}
                    placeholder="Поиск..."
                    className="h-[40px] w-full rounded-[var(--hf-radius-s)] border border-[var(--hf-cyan-500)] bg-[var(--hf-white)] pl-[32px] pr-[16px] text-[length:var(--hf-fs-xs)] leading-[var(--hf-lh-primary)] text-[var(--hf-main-900)] outline-none placeholder:text-[var(--hf-main-600)] hf-dark-disabled:bg-transparent hf-dark-disabled:text-[var(--hf-white)]"
                  />
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setTimelineActionFilter(null);
                  setActionSearch("");
                  setShowActionMenu(false);
                }}
                className="block h-[34px] w-full px-[var(--hf-space-xxl)] text-left text-[length:var(--hf-fs-xxs)] leading-[var(--hf-lh-secondary)] text-[var(--hf-main-600)] transition-colors hover:bg-[var(--hf-bg-panel)] hover:text-[var(--hf-main-700)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-05)]"
              >
                Сбросить выбор
              </button>
              <div className="h-[322px] overflow-y-auto border-t border-[var(--hf-main-200)] py-[6px] hf-dark-disabled:border-[color:var(--hf-white-alpha-06)]">
                {visibleActionFilters.length > 0 ? (
                  visibleActionFilters.map((item, index) => {
                    const isSelected = item === timelineActionFilter;
                    const isDefaultHighlighted =
                      !timelineActionFilter &&
                      actionSearch.trim().length === 0 &&
                      index === 0;
                    const iconClass = "h-[18px] w-[18px] shrink-0";
                    return (
                      <button
                        type="button"
                        key={item}
                        onClick={() => {
                          setTimelineActionFilter(item);
                          setActionSearch("");
                          setShowActionMenu(false);
                        }}
                        className="group flex h-[42px] w-full items-center px-[var(--hf-space-s)] text-left text-[length:var(--hf-fs-s)] leading-[var(--hf-lh-field)] text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]"
                      >
                        <span
                          className={clsx(
                            "flex h-[41.333px] w-full items-center transition-colors group-hover:bg-[var(--hf-black-alpha-07)] hf-dark-disabled:group-hover:bg-[var(--hf-white-alpha-10)]",
                            (isSelected || isDefaultHighlighted) &&
                              "bg-[var(--hf-black-alpha-07)] hf-dark-disabled:bg-[var(--hf-white-alpha-10)]",
                          )}
                        >
                          <span className="flex h-full w-[32px] shrink-0 items-center justify-center">
                            {isSelected ? (
                              <Check className="h-[16px] w-[16px]" />
                            ) : null}
                          </span>
                          <span className="flex h-full min-w-0 flex-1 items-center gap-[4px] py-[var(--hf-space-s)] pr-[8px]">
                            {item === "Письмо кандидату" ? (
                              <Mail className={iconClass} />
                            ) : null}
                            {item === "Интервью" ? (
                              <Calendar className={iconClass} />
                            ) : null}
                            {item === "Телефонный звонок" ? (
                              <Phone className={iconClass} />
                            ) : null}
                            {item === "Оффер" ? (
                              <ThumbsUp className={iconClass} />
                            ) : null}
                            {item === "Файл" ? (
                              <Paperclip className={iconClass} />
                            ) : null}
                            <span>{item}</span>
                          </span>
                        </span>
                      </button>
                    );
                  })
                ) : (
                  <div className="px-[var(--hf-space-xxl)] py-[10px] text-[length:var(--hf-fs-xxs)] leading-[var(--hf-lh-secondary)] text-[var(--hf-main-600)]">
                    Ничего не найдено
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </div>
        )}
        <div className="relative ml-[17px] w-[calc(100%-11px)] border-l border-[var(--hf-main-300)] pl-[38.667px] hf-dark-disabled:border-[color:var(--hf-white-alpha-08)]">
          {visibleTimelineItems.length > 0 ? (
            visibleTimelineItems.map((event, i) => (
              <TimelineEntry
                key={`${event.historyId ?? event.noteId ?? event.date ?? card.created_at}-${i}`}
                event={event}
                i={i}
                actions={rowActions}
                card={card}
                applicationId={applicationId}
                readonly={readonly}
                onDeleteHistory={onDeleteHistory}
                onDeleteNote={onDeleteNote}
                onEditHistory={onEditHistory}
                onEditNote={onEditNote}
                onPin={onPin}
                onReact={onReact}
              />
            ))
          ) : (
            <div className="relative text-[length:var(--hf-fs-xs)] leading-[var(--hf-lh-field)] text-[var(--hf-main-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
              <TimelineDot />
              {timelineActionFilter
                ? "Нет действий по выбранным фильтрам"
                : "Пока нет записей"}
            </div>
          )}
        </div>
      </div>
      {/* ── Файлы контейнера: под логом, скачиваемы. live — собственные файлы;
          merged — снапшот его file_ids. Скачивание работает и read-only. ── */}
      {files && files.length > 0 ? (
        <div className="px-[var(--hf-space-xxl)] pt-[14px]">
          <div className="mb-[8px] text-[length:var(--hf-fs-xxs)] font-medium leading-[var(--hf-lh-field)] text-[color:var(--hf-alpha-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
            Файлы
          </div>
          <div className="flex flex-col gap-[4px]">
            {files.map((f) => (
              <div
                key={f.id}
                className="group flex items-center gap-[2px] rounded-[var(--hf-radius-s)] transition-colors hover:bg-[var(--hf-black-alpha-04)] hf-dark-disabled:hover:bg-[var(--hf-white-alpha-06)]"
              >
                <button
                  type="button"
                  onClick={() =>
                    /\.(mp4|mov|avi|webm|m4v)$/i.test(f.file_name)
                      ? setVideoModal({ url: fileUrlOf ? fileUrlOf(f.id) : `/api/entities/${card.id}/files/${f.id}/download`, name: f.file_name })
                      : handleDownloadFile(f.id, f.file_name)
                  }
                  title={/\.(mp4|mov|avi|webm|m4v)$/i.test(f.file_name) ? "Смотреть видео" : "Скачать"}
                  className="flex min-w-0 flex-1 items-center gap-[6px] px-[6px] py-[4px] text-left text-[length:var(--hf-fs-s)] leading-[var(--hf-lh-field)] text-[var(--hf-main-700)] transition-colors hover:text-[var(--hf-main-900)] hf-dark-disabled:text-[color:var(--hf-white-alpha-55)] hf-dark-disabled:hover:text-[var(--hf-white)]"
                >
                  <Paperclip className="h-[13px] w-[13px] shrink-0 text-[var(--hf-ui-icon-light)] hf-dark-disabled:text-[color:var(--hf-white-alpha-25)]" />
                  <span className="truncate">{f.file_name}</span>
                </button>
                {onDeleteFile ? (
                  <button
                    type="button"
                    onClick={() => onDeleteFile(f.id)}
                    title="Удалить файл"
                    className="mr-[4px] inline-flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full text-[var(--hf-main-500)] opacity-0 transition-opacity hover:text-[var(--hf-status-red)] group-hover:opacity-100 focus:outline-none focus-visible:outline-none"
                  >
                    <Trash2 className="h-[13px] w-[13px]" />
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {videoModal && createPortal(
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 p-4"
          {...backdropClose(() => setVideoModal(null))}
        >
          <div className="relative w-full max-w-3xl" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              onClick={() => setVideoModal(null)}
              className="absolute -top-11 right-0 inline-flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20"
              title="Закрыть"
              aria-label="Закрыть"
            >
              <X className="h-5 w-5" />
            </button>
            {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
            <video src={videoModal.url} controls autoPlay className="max-h-[80vh] w-full rounded-lg bg-black" />
            <div className="mt-2 truncate text-center text-sm text-white/70">{videoModal.name}</div>
          </div>
        </div>,
        document.body,
      )}
      {hasHiddenTimelineItems ? (
        <button
          type="button"
          onClick={handleTimelineMoreToggle}
          disabled={timelineExpanding}
          aria-busy={timelineExpanding}
          className="mt-[25px] flex h-[49.333px] w-full items-center justify-center border-t border-[color:var(--hf-main-200)] hf-dark-disabled:border-[color:var(--hf-white-alpha-06)] text-[length:var(--hf-fs-xxs)] leading-[var(--hf-lh-field)] text-[var(--hf-main-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)] hover:text-[var(--hf-main-900)] hf-dark-disabled:hover:text-[var(--hf-white)] transition-colors"
        >
          {timelineExpanding ? (
            <HfLoadingSpinner
              className="hf-timeline-more-spinner"
              size="var(--hf-loading-spinner-size-sm)"
              stroke="var(--hf-loading-spinner-border)"
            />
          ) : (
            <>
              {showAllTimeline ? "Свернуть" : "Показать еще"}{" "}
              <ChevronDown
                className={clsx(
                  "ml-hf-xs h-3.5 w-3.5 transition-transform",
                  showAllTimeline && "rotate-180",
                )}
              />
            </>
          )}
        </button>
      ) : (
        <div className="mt-[25px] h-[49.333px] border-t border-[color:var(--hf-main-200)] hf-dark-disabled:border-[color:var(--hf-white-alpha-06)]" />
      )}
    </div>
  );
});

export default CandidateVacancyCard;
